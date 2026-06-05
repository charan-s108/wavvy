"""
/api/calls — Call history and live dashboard endpoints.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from database import AsyncSessionLocal
from session.call_session import ACTIVE_CALLS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["calls"])


class FeedbackBody(BaseModel):
    rating: int
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("rating must be between 1 and 5")
        return v

    @field_validator("comment", mode="before")
    @classmethod
    def sanitize_comment(cls, v):
        if v is None:
            return None
        stripped = str(v).strip()[:1000]
        return stripped if stripped else None


@router.post("/calls/{call_id}/feedback")
async def submit_feedback(call_id: str, body: FeedbackBody):
    """
    Post-call star rating + optional comment from the visitor.
    Duplicate submissions overwrite previous values (idempotent).
    """
    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid call_id format")

    async with AsyncSessionLocal() as db:
        exists = await db.execute(
            text("SELECT id FROM calls WHERE id = :id"),
            {"id": call_uuid},
        )
        if not exists.first():
            raise HTTPException(status_code=404, detail="Call not found")

        await db.execute(
            text("""UPDATE calls
                    SET customer_rating = :rating,
                        customer_feedback = :comment,
                        feedback_submitted_at = NOW()
                    WHERE id = :id"""),
            {"id": call_uuid, "rating": body.rating, "comment": body.comment},
        )
        await db.commit()

    try:
        from routers.ws_supervisor import broadcast_supervisor_event
        from datetime import datetime, timezone
        await broadcast_supervisor_event({
            "type":         "feedback_submitted",
            "call_id":      call_id,
            "rating":       body.rating,
            "comment":      body.comment,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    return {"ok": True}


@router.post("/calls/{call_id}/end")
async def end_call(call_id: str):
    """Terminate an active call. Called by the agent desktop when clicking End Call."""
    import livekit.api as lk_api
    from config import settings as _settings

    session = ACTIVE_CALLS.get(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call not found")

    # Delete the room — causes all participants to disconnect and triggers
    # agent cleanup in agent_session.entrypoint's wait_for_participant path.
    room_name = f"call-{call_id}"
    lk = lk_api.LiveKitAPI(_settings.livekit_url, _settings.livekit_api_key, _settings.livekit_api_secret)
    try:
        await lk.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    except Exception as exc:
        logger.warning("[%s] room delete failed (may already be gone): %s", call_id, exc)
    finally:
        await lk.aclose()

    return {"status": "ending", "call_id": call_id}


@router.post("/calls/{call_id}/request-human")
async def request_human_agent(call_id: str, request: Request):
    """
    Customer-initiated escalation via the 'Talk to Human' UI button.

    Reuses the same escalation pipeline as voice-triggered escalation:
    - escalate_to_human tool → DB update + EscalationPacket build
    - TTS speaks the escalation phrase via the active pipeline_task
    - Delivers handoff bundle to any connected agent desktop
    """
    from voice.tool_recovery import execute_with_recovery
    from voice.deterministic_responses import WAVVY_DEMO, get_fast_response

    session = ACTIVE_CALLS.get(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call not found")

    if session.escalated:
        return {"status": "already_escalated", "call_id": call_id}

    if session.escalation_failed:
        raise HTTPException(status_code=503, detail="Escalation temporarily unavailable")

    result = await execute_with_recovery(
        tool_name="escalate_to_human",
        args={
            "reason": "manual_button_request",
            "lead_summary": "Customer clicked Talk to Human button",
        },
        call_id=call_id,
        turn_id=0,
        step_id="request_human_button",
        session=session,
    )

    if not result.success:
        raise HTTPException(status_code=500, detail="Escalation failed")

    # Speak the escalation phrase through the live agent session
    if session.agent_session:
        msg = get_fast_response("escalating", WAVVY_DEMO)
        if msg:
            try:
                await session.agent_session.say(msg)
            except Exception:
                pass

    # Store handoff bundle on session (same as voice-triggered escalation)
    handoff = result.data.get("handoff_bundle", {})
    session.handoff_bundle = handoff

    # Deliver to agent desktop — reuses the same delivery path as TranscriptProcessor
    delivered = False
    try:
        from routers.ws_agent import deliver_incoming_call
        voice_transcript = [
            {"speaker": m["role"], "text": m["content"]}
            for m in session.conversation_history
            if m.get("content")
        ]
        delivered = await deliver_incoming_call(
            request.app.state, call_id, {}, handoff, voice_transcript,
        )
    except Exception as exc:
        logger.warning("[%s] deliver_incoming_call failed for button escalation: %s",
                       call_id, exc)

    if not delivered:
        # No agents available — cancel immediately and return to AI
        asyncio.create_task(_cancel_to_ai(call_id, session))
        return {"status": "no_agents", "call_id": call_id}

    return {"status": "ok", "call_id": call_id}


async def _cancel_to_ai(call_id: str, session) -> None:
    """Revert a just-triggered escalation when no agents are available."""
    import json
    import livekit.api as lk_api
    from config import settings as _s

    session.escalated = False
    session.handoff_bundle = {}

    room_name = f"call-{call_id}"
    lk = lk_api.LiveKitAPI(_s.livekit_url, _s.livekit_api_key, _s.livekit_api_secret)
    try:
        await lk.room.send_data(lk_api.SendDataRequest(
            room=room_name,
            data=json.dumps({"type": "escalation_cancelled"}).encode(),
        ))
    except Exception as exc:
        logger.warning("[%s] no-agents escalation_cancelled send failed: %s", call_id, exc)
    finally:
        await lk.aclose()

    from routers.livekit_router import _AGENTS_BUSY_MSG
    if session.agent_session:
        try:
            await session.agent_session.say(_AGENTS_BUSY_MSG, allow_interruptions=True)
        except Exception as exc:
            logger.warning("[%s] no-agents say() failed: %s", call_id, exc)


@router.get("/calls")
async def list_calls(limit: int = 50):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""SELECT c.id, c.started_at, c.ended_at, c.duration_secs,
                           c.call_type, c.resolution, c.escalated,
                           c.voice_ai_summary, c.acw_summary, c.status,
                           cu.name  AS customer_name,
                           cu.phone AS customer_phone,
                           cu.account_type
                    FROM calls c
                    LEFT JOIN customers cu ON cu.id = c.customer_id
                    ORDER BY c.started_at DESC
                    LIMIT :lim"""),
            {"lim": limit},
        )
        rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
            "duration_secs": row["duration_secs"],
            "call_type": row["call_type"],
            "resolution": row["resolution"],
            "escalated": row["escalated"],
            "voice_ai_summary": row["voice_ai_summary"],
            "acw_summary": row["acw_summary"],
            "status": row["status"],
            "customer_name": row["customer_name"],
            "customer_phone": row["customer_phone"],
            "account_type": row["account_type"],
        }
        for row in rows
    ]


@router.get("/dashboard/live-calls")
async def live_calls():
    """Returns currently active calls from ACTIVE_CALLS in-memory dict."""
    result = []
    for call_id, session in ACTIVE_CALLS.items():
        # WorkflowProgress has steps_taken, not intent — derive intent from conv_context
        intent = None
        conv_ctx = getattr(session, "conv_context", None)
        if conv_ctx is not None:
            ci = getattr(conv_ctx, "conversation_intent", None)
            if ci is not None:
                intent = ci.value if hasattr(ci, "value") else str(ci)
        result.append({
            "call_id": call_id,
            "customer_name": getattr(session, "confirmed_name", None),
            "call_type": "escalated" if session.escalated else "voice_ai",
            "started_at": session.started_at.isoformat() if hasattr(session, "started_at") else None,
            "stage": session.conv_state.stage.value if hasattr(session, "conv_state") else "unknown",
            "intent": intent,
        })
    return result


@router.get("/dashboard/kpis")
async def dashboard_kpis():
    """Today's aggregate KPIs."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""SELECT
                    COUNT(*) as total_calls,
                    COUNT(*) FILTER (WHERE resolution='resolved') as resolved,
                    COUNT(*) FILTER (WHERE escalated=TRUE) as escalated,
                    ROUND(AVG(duration_secs)) as avg_duration,
                    COUNT(*) FILTER (WHERE call_type='voice_ai' AND resolution='resolved') as contained
                 FROM calls
                 WHERE started_at >= NOW() - INTERVAL '24 hours'""")
        )
        row = result.mappings().first()

    total = row["total_calls"] or 0
    contained = row["contained"] or 0
    containment_rate = round((contained / total * 100), 1) if total > 0 else 0

    # Avg QA score from eval_scores today
    async with AsyncSessionLocal() as db:
        eq = await db.execute(
            text("""SELECT ROUND(AVG(overall_score)) as avg_score
                 FROM eval_scores
                 WHERE created_at >= NOW() - INTERVAL '24 hours'""")
        )
        eq_row = eq.mappings().first()

    return {
        "total_calls": total,
        "resolved": row["resolved"] or 0,
        "escalated": row["escalated"] or 0,
        "avg_duration": row["avg_duration"] or 0,
        "avg_score": eq_row["avg_score"] if eq_row and eq_row["avg_score"] else None,
        "containment_rate": containment_rate,
    }
