"""
LiveKit call management: create room, issue JWT for the browser.

Agent launch is handled by the LiveKit Agents worker (voice/agent_worker.py).
When a room is created here, LiveKit Cloud auto-dispatches a job to the worker.
This router only manages room lifecycle and JWT issuance.
"""
import asyncio
import logging
import uuid
from datetime import timedelta

import livekit.api as lk_api
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from agents import qa_agent as qa_agent_module
from config import settings
from database import AsyncSessionLocal
from session.call_session import create_session, remove_session

logger = logging.getLogger(__name__)
router = APIRouter()


class StartCallRequest(BaseModel):
    initial_topic: str | None = None


class AgentJoinRequest(BaseModel):
    call_id: str


async def _create_db_call(call_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""INSERT INTO calls (id, call_type, status)
                        VALUES (:id, 'voice_ai', 'active')"""),
                {"id": uuid.UUID(call_id)},
            )
            await db.commit()
    except Exception as exc:
        logger.error(f"[{call_id}] DB call insert failed: {exc}")


async def _persist_call_end(call_id: str, conversation_history: list, session=None) -> None:
    try:
        turns = [
            m for m in conversation_history
            if m.get("content") and m.get("role") in ("user", "assistant")
        ]
        full_text = " ".join(m["content"] for m in turns)
        speaker_map = {"user": "customer", "assistant": "voice_ai"}

        escalated   = getattr(session, "escalated",   False) if session else False
        customer_id = getattr(session, "customer_id", None)  if session else None
        resolution  = "escalated" if escalated else "resolved"

        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""UPDATE calls
                        SET status = 'completed', ended_at = NOW(),
                            voice_ai_summary = :s,
                            resolution = :resolution,
                            duration_secs = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER,
                            customer_id = COALESCE(customer_id, :cid)
                        WHERE id = :id"""),
                {
                    "id":  uuid.UUID(call_id),
                    "s":   full_text[:2000] if full_text else None,
                    "resolution": resolution,
                    "cid": uuid.UUID(customer_id) if customer_id else None,
                },
            )
            for m in turns:
                await db.execute(
                    text("""INSERT INTO transcripts (call_id, speaker, content)
                            VALUES (:cid, :sp, :ct)"""),
                    {
                        "cid": uuid.UUID(call_id),
                        "sp":  speaker_map[m["role"]],
                        "ct":  m["content"],
                    },
                )
            await db.commit()
    except Exception as exc:
        logger.error(f"[{call_id}] DB call end persist failed: {exc}")


@router.post("/api/livekit/start-call")
async def start_call(body: StartCallRequest, request: Request):
    call_id = str(uuid.uuid4())
    room_name = f"call-{call_id}"

    lk = lk_api.LiveKitAPI(
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    )
    try:
        await lk.room.create_room(
            lk_api.CreateRoomRequest(name=room_name, empty_timeout=600)
        )
    finally:
        await lk.aclose()

    customer_token = (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity("customer")
        .with_name("Visitor")
        .with_ttl(timedelta(hours=4))
        .with_grants(lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
        .to_jwt()
    )

    session = create_session(call_id)
    if body.initial_topic:
        session.initial_topic = body.initial_topic.strip()
    await _create_db_call(call_id)

    from routers.ws_admin import broadcast_admin_event
    asyncio.create_task(broadcast_admin_event({
        "type": "call_started",
        "call_id": call_id,
        "started_at": session.started_at.isoformat(),
    }))

    # Agent is auto-dispatched by LiveKit Cloud to the worker process.
    # No manual background task needed.

    return {
        "token": customer_token,
        "room_name": room_name,
        "livekit_url": settings.livekit_url,
        "call_id": call_id,
    }


@router.post("/api/livekit/sip-inbound")
async def sip_inbound_webhook(request: Request):
    """
    LiveKit fires this on room_started events for SIP/PSTN inbound calls.
    Configured as the webhook URL in the LiveKit dashboard or via setup_sip.py.
    LiveKit signs the body with a JWT — we verify it before launching the agent.
    """
    raw_body = await request.body()
    auth_token = request.headers.get("Authorization", "")

    # Verify LiveKit webhook signature
    try:
        receiver = lk_api.WebhookReceiver(
            lk_api.TokenVerifier(settings.livekit_api_key, settings.livekit_api_secret)
        )
        event = receiver.receive(raw_body.decode(), auth_token)
    except Exception as exc:
        logger.warning(f"SIP webhook signature verification failed: {exc}")
        from fastapi import Response
        return Response(status_code=200)  # return 200 to prevent LiveKit retry storms

    # Only start an agent on room_started for sip-call-* rooms
    if event.event != "room_started":
        return {"status": "ignored", "event": event.event}

    room_name = event.room.name
    if not room_name.startswith("sip-call-"):
        return {"status": "ignored", "room": room_name}

    call_id = room_name.removeprefix("sip-call-")

    # Deduplicate: agent already running for this call
    from session.call_session import ACTIVE_CALLS
    if call_id in ACTIVE_CALLS:
        return {"status": "duplicate", "call_id": call_id}

    session = create_session(call_id)
    await _create_db_call(call_id)
    # Agent dispatched automatically by LiveKit Cloud to the worker process.
    logger.info(f"SIP inbound call started: call_id={call_id} room={room_name}")
    return {"status": "accepted", "call_id": call_id}


@router.post("/api/internal/worker-event")
async def worker_event(request: Request):
    """
    Called by the LiveKit Agents worker process (separate subprocess) to deliver
    events that require FastAPI WebSocket access — admin push, agent desktop
    incoming_call. The worker cannot access FastAPI's in-memory WebSocket state
    directly, so it POSTs here and we forward to the right connections.
    """
    body = await request.json()
    call_id = body.get("call_id", "")
    event_type = body.get("event_type", "")
    data = body.get("data", {})

    from routers.ws_admin import broadcast_admin_event

    if event_type == "escalation":
        handoff = data.get("handoff_bundle", {})
        conversation_history = data.get("conversation_history", [])
        agent_esc_token = data.get("agent_esc_token")
        esc_room_name   = data.get("esc_room_name")
        livekit_url     = data.get("livekit_url", settings.livekit_url)

        # Sync FastAPI's own ACTIVE_CALLS session — the worker set these on its
        # own process copy. Without this, the re-delivery check on agent reconnect
        # sees escalated=False / handoff_bundle=None and silently skips the call.
        from session.call_session import get_session as _get_session
        _sess = _get_session(call_id)
        if _sess:
            _sess.escalated       = True
            _sess.handoff_bundle  = handoff
            _sess.esc_room_name   = esc_room_name
            _sess.agent_esc_token = agent_esc_token
            if conversation_history:
                _sess.conversation_history = conversation_history
            customer_id = data.get("customer_id")
            if customer_id:
                _sess.customer_id = customer_id

        asyncio.create_task(broadcast_admin_event({
            "type": "call_escalated", "call_id": call_id,
        }))
        # Deliver to any connected agent desktop
        try:
            from routers.ws_agent import deliver_incoming_call
            _role_map = {"user": "customer", "assistant": "voice_ai"}
            voice_transcript = [
                {
                    "speaker": _role_map.get(m.get("role", ""), m.get("role", "customer")),
                    "text": m.get("content", ""),
                }
                for m in conversation_history if m.get("content")
            ]
            asyncio.create_task(deliver_incoming_call(
                request.app.state, call_id, {}, handoff, voice_transcript,
                escalation_token=agent_esc_token,
                esc_room_name=esc_room_name,
                livekit_url=livekit_url,
            ))
        except Exception as exc:
            logger.warning("[%s] worker-event escalation deliver failed: %s", call_id, exc)

    elif event_type == "call_started":
        asyncio.create_task(broadcast_admin_event({
            "type": "call_started", "call_id": call_id, **data,
        }))

    elif event_type == "call_ended":
        asyncio.create_task(broadcast_admin_event({
            "type": "call_ended", "call_id": call_id,
        }))
        # Trigger QA scoring in the FastAPI process (has the OpenAI client)
        try:
            from agents import qa_agent as _qa
            asyncio.create_task(_qa.score_call(call_id))
        except Exception as exc:
            logger.warning("[%s] QA score trigger failed: %s", call_id, exc)

    elif event_type == "transcript":
        # Customer speech forwarded from the worker after escalation.
        # The agent is in the esc room so they can't receive LiveKit data channel
        # events from the original call room — route through the agent WS instead.
        try:
            from routers.ws_agent import deliver_transcript_line
            asyncio.create_task(deliver_transcript_line(
                request.app.state,
                data.get("speaker", "customer"),
                data.get("text", ""),
                call_id,
            ))
        except Exception as exc:
            logger.warning("[%s] transcript ws-forward failed: %s", call_id, exc)

    elif event_type == "otp_sent":
        # Voice AI sent an OTP — forward to the agent console so it's visible in the timeline
        try:
            from routers.ws_agent import deliver_otp_to_agent
            asyncio.create_task(deliver_otp_to_agent(request.app.state, call_id, data.get("otp", "")))
        except Exception as exc:
            logger.warning("[%s] otp_sent ws-forward failed: %s", call_id, exc)

    elif event_type == "turn_metrics":
        # Per-turn latency metrics from the worker — push to admin dashboard
        asyncio.create_task(broadcast_admin_event({
            "type": "turn_metrics", "call_id": call_id, **data,
        }))

    return {"ok": True}


_AGENTS_BUSY_MSG = (
    "I'm sorry, all our support specialists are currently busy. "
    "I'm right here and happy to keep helping you — "
    "is there anything else I can assist you with today?"
)


@router.post("/api/calls/{call_id}/cancel-escalation")
async def cancel_escalation(call_id: str):
    """Cancel a pending escalation and return control to the AI agent."""
    import json
    from session.call_session import get_session
    session = get_session(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call not found")
    if session.human_joined:
        raise HTTPException(status_code=409, detail="Human agent already joined — cannot revert")

    session.escalated = False

    # Push escalation_cancelled event to the customer's browser via LiveKit data channel
    room_name = f"call-{call_id}"
    lk = lk_api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)
    try:
        await lk.room.send_data(lk_api.SendDataRequest(
            room=room_name,
            data=json.dumps({"type": "escalation_cancelled"}).encode(),
        ))
    except Exception as exc:
        logger.warning("[%s] cancel-escalation data send failed: %s", call_id, exc)
    finally:
        await lk.aclose()

    # Make the AI speak the "agents busy" message so the customer isn't left in silence
    if session.agent_session:
        try:
            await session.agent_session.say(_AGENTS_BUSY_MSG, allow_interruptions=True)
        except Exception as exc:
            logger.warning("[%s] cancel-escalation say() failed: %s", call_id, exc)

    return {"ok": True}


@router.post("/api/livekit/create-escalation-room")
async def create_escalation_room(request: Request):
    """Text-to-TTS model: no separate room needed. Returns stub for backward compat."""
    body = await request.json()
    call_id = body.get("call_id", "")
    return {
        "room_name":      f"call-{call_id}",
        "customer_token": None,
        "agent_token":    None,
        "livekit_url":    settings.livekit_url,
    }


class AgentSayRequest(BaseModel):
    text: str


@router.post("/api/calls/{call_id}/agent-say")
async def agent_say(call_id: str, body: AgentSayRequest, request: Request):
    """Human agent types a message → played as TTS to the customer via the call room.

    Flow: FastAPI sends a LiveKit data message to call-{call_id}. The worker's
    on_data handler receives it, sets human_agent_say_active=True, and calls
    agent_session.say(text) so the customer hears the specialist's words.
    """
    import json as _json
    from session.call_session import get_session

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    session = get_session(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call not found")

    # Forward transcript to agent desktop WS (companion + transcript feed)
    try:
        from routers.ws_agent import deliver_transcript_line
        asyncio.create_task(deliver_transcript_line(request.app.state, "agent", text, call_id))
    except Exception as exc:
        logger.warning("[%s] agent-say transcript forward failed: %s", call_id, exc)

    # Send text to the Fin AI worker via LiveKit data channel
    lk = lk_api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)
    try:
        await lk.room.send_data(lk_api.SendDataRequest(
            room=f"call-{call_id}",
            data=_json.dumps({"type": "agent_say_text", "text": text}).encode(),
        ))
    except Exception as exc:
        logger.warning("[%s] agent-say send_data failed: %s", call_id, exc)
    finally:
        await lk.aclose()

    return {"ok": True}


@router.post("/api/livekit/agent-join")
async def agent_join(body: AgentJoinRequest):
    """Issues a LiveKit JWT for a human agent to (re-)join the escalation room.

    The pre-generated agent_esc_token is sent with the incoming_call WebSocket event;
    this endpoint is the fallback for agents who reconnect after the initial delivery.
    """
    from session.call_session import get_session
    session = get_session(body.call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call not found")

    # Same-room escalation: human agent always joins the original call room
    room_name = session.esc_room_name or f"call-{body.call_id}"
    # esc_room_name is now set to call-{call_id} by create-escalation-room so both branches land here

    token = (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity("human-agent")
        .with_name("Specialist")
        .with_ttl(timedelta(hours=4))
        .with_grants(lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
        .to_jwt()
    )
    session.human_joined = True

    # Notify the Fin AI worker (separate process) that the human has accepted.
    # The worker is listening on data_received in the original call-{call_id} room.
    # This fires human_took_over.set() in the worker so the AI fully stops speaking.
    import json as _json
    lk_notify = lk_api.LiveKitAPI(
        settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret
    )
    try:
        await lk_notify.room.send_data(lk_api.SendDataRequest(
            room=f"call-{body.call_id}",
            data=_json.dumps({"type": "human_agent_accepted"}).encode(),
        ))
    except Exception as exc:
        logger.warning("[%s] human_agent_accepted notify failed: %s", body.call_id, exc)
    finally:
        await lk_notify.aclose()

    return {"token": token, "room_name": room_name, "livekit_url": settings.livekit_url}
