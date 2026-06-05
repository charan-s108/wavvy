import asyncio
import json
import logging
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from agents.companion_agent import run_mid_call_companion, run_acw_agent
from routers.auth_router import verify_agent_token
from session.call_session import ACTIVE_CALLS
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# agent_id → WebSocket (one per agent desktop session)
# Stored on app.state.connected_agents so ws_voice can access it
# app.state.agent_statuses: agent_id → "active" | "busy" | "inactive"


def _get_statuses(app_state) -> dict:
    if not hasattr(app_state, "agent_statuses"):
        app_state.agent_statuses = {}
    return app_state.agent_statuses


def get_active_agent_count(app_state) -> int:
    """Count agents currently in 'active' status."""
    connected = getattr(app_state, "connected_agents", {})
    statuses  = _get_statuses(app_state)
    return sum(1 for aid in connected if statuses.get(aid, "active") == "active")


@router.get("/api/agents/availability")
async def agent_availability(request: Request):
    count = get_active_agent_count(request.app.state)
    return {"available": count > 0, "active_count": count}


async def route_event_to_agent(app_state, event: dict) -> bool:
    """Send an event to any connected agent. Returns True if delivered."""
    connected: dict = getattr(app_state, "connected_agents", {})
    if not connected:
        return False
    # Broadcast to all connected agents (demo: single agent scenario)
    payload = json.dumps(event)
    dead = []
    for agent_id, ws in connected.items():
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(agent_id)
    for agent_id in dead:
        connected.pop(agent_id, None)
    return len(connected) > 0


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket, token: str = ""):
    # Validate JWT — accept first so we can send a readable error to the client
    try:
        claims = verify_agent_token(token)
    except Exception as exc:
        logger.warning("Agent WS rejected — invalid token: %s", exc)
        await websocket.accept()
        await websocket.send_text(json.dumps({
            "type":   "auth_error",
            "reason": "invalid_or_expired_token",
        }))
        await websocket.close(code=4401)
        return

    agent_name  = claims.get("name", "Agent")
    agent_email = claims.get("email", "")

    await websocket.accept()

    # Register this agent connection
    app_state = websocket.app.state
    if not hasattr(app_state, "connected_agents"):
        app_state.connected_agents = {}

    agent_id = f"agent_{id(websocket)}"
    app_state.connected_agents[agent_id] = websocket
    # Default to active when they connect
    _get_statuses(app_state)[agent_id] = "active"
    logger.info(f"Agent connected: {agent_id} ({agent_name})")

    # Flush any queued escalations that arrived while no agent was connected
    pending: list = getattr(app_state, "pending_escalations", [])
    if pending:
        app_state.pending_escalations = []
        for item in pending:
            asyncio.create_task(
                _send_escalation_to_agent(app_state, app_state.connected_agents, item)
            )

    # Re-deliver escalated calls whose assigned agent WebSocket is no longer connected.
    # This handles the race where escalation was sent to a WebSocket that disconnected
    # before the frontend could render the incoming_call UI.
    active_sockets = set(app_state.connected_agents.values())
    for call_id, sess in list(ACTIVE_CALLS.items()):
        if not (sess.escalated and sess.handoff_bundle):
            continue
        # Only re-deliver if the previously assigned socket is gone
        if sess.agent_ws is not None and sess.agent_ws in active_sockets:
            continue
        _role_map = {"user": "customer", "assistant": "voice_ai"}
        voice_transcript = [
            {
                "speaker": _role_map.get(m.get("role", ""), "customer"),
                "text": m.get("content", ""),
            }
            for m in sess.conversation_history
            if m.get("content")
        ]
        logger.info(f"Re-delivering escalated call {call_id} to newly connected agent {agent_id}")
        asyncio.create_task(
            _send_escalation_to_agent(
                app_state,
                {agent_id: websocket},
                {
                    "call_id": call_id,
                    "customer": {},
                    "handoff_bundle": sess.handoff_bundle,
                    "voice_transcript": voice_transcript,
                },
            )
        )

    # Track state for this agent session
    current_call_id: str | None = None
    current_customer: dict = {}
    transcript_buffer: list[dict] = []
    previous_mood: str = "calm"

    def _find_call_id_for_ws() -> str | None:
        """Find the active call_id that assigned this websocket as its agent."""
        for cid, sess in ACTIVE_CALLS.items():
            if getattr(sess, "agent_ws", None) is websocket:
                return cid
        return current_call_id  # fallback to locally tracked value

    try:
        while True:
            raw = await websocket.receive()

            if raw.get("type") == "websocket.disconnect":
                break

            text = raw.get("text")
            if not text:
                continue

            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "agent_ready":
                # Agent desktop signals it's ready — honour any initial status
                initial_status = msg.get("status", "active")
                if initial_status in ("active", "busy", "inactive"):
                    _get_statuses(app_state)[agent_id] = initial_status
                await websocket.send_text(json.dumps({
                    "type": "agent_ready_ack",
                    "agent_name": agent_name,
                    "agent_email": agent_email,
                    "status": _get_statuses(app_state).get(agent_id, "active"),
                }))

            elif msg_type == "set_status":
                new_status = msg.get("status", "active")
                if new_status in ("active", "busy", "inactive"):
                    _get_statuses(app_state)[agent_id] = new_status
                    logger.info(f"Agent {agent_name} status → {new_status}")
                await websocket.send_text(json.dumps({
                    "type": "status_updated",
                    "status": _get_statuses(app_state).get(agent_id, "active"),
                }))

            elif msg_type == "transcript_line":
                # Agent sends their own spoken words (typed or mic STT).
                # The frontend adds the line directly to liveTx — no echo needed here.
                # We only buffer it for companion context and ACW generation.
                line = {
                    "speaker": "agent",
                    "text": msg.get("text", ""),
                }
                transcript_buffer.append(line)

                # Trigger companion update after agent speech — include handoff_bundle context
                resolved_call_id = msg.get("call_id") or _find_call_id_for_ws()
                if resolved_call_id:
                    current_call_id = resolved_call_id
                    sess = ACTIVE_CALLS.get(resolved_call_id)
                    asyncio.create_task(
                        _send_companion_update(
                            websocket,
                            transcript_buffer,
                            current_customer,
                            sess.handoff_bundle if sess else None,
                            previous_mood=previous_mood,
                            workflow_type=_get_workflow_type(sess),
                            completed_actions=sess.completed_actions if sess else None,
                        )
                    )

            elif msg_type == "decline_call":
                # Agent actively declines — cancel escalation and return customer to AI
                declined_call_id = msg.get("call_id") or _find_call_id_for_ws()
                if declined_call_id:
                    asyncio.create_task(_decline_escalation(declined_call_id))
                    logger.info(f"Agent {agent_name} declined call {declined_call_id}")
                current_call_id = None
                current_customer = {}
                transcript_buffer = []

            elif msg_type == "end_call":
                resolved_call_id = _find_call_id_for_ws()
                if resolved_call_id:
                    sess = ACTIVE_CALLS.get(resolved_call_id)
                    # Always use the full session history as the authoritative transcript.
                    # transcript_buffer only has agent-side lines typed via Web Speech API;
                    # it is missing all customer utterances that arrived via deliver_transcript_line.
                    # session.conversation_history has every turn from both sides.
                    if sess and sess.conversation_history:
                        acw_transcript = [
                            {"speaker": m.get("role", "user"), "text": m.get("content", "")}
                            for m in sess.conversation_history
                            if m.get("content")
                        ]
                        # Append any agent lines from transcript_buffer that occurred
                        # after the last session history entry (most-recent human speech).
                        for line in transcript_buffer:
                            if line not in acw_transcript:
                                acw_transcript.append(line)
                    else:
                        acw_transcript = list(transcript_buffer)
                    asyncio.create_task(
                        _send_acw(websocket, acw_transcript, current_customer, resolved_call_id)
                    )

            elif msg_type == "acw_submit":
                resolved_call_id = _find_call_id_for_ws()
                if resolved_call_id:
                    asyncio.create_task(
                        _persist_acw(resolved_call_id, msg.get("acw", {}))
                    )
                    await websocket.send_text(json.dumps({
                        "type": "call_closed",
                        "call_id": resolved_call_id,
                    }))
                    current_call_id = None
                    current_customer = {}
                    transcript_buffer = []

            elif msg_type == "action_approved":
                action_name  = msg.get("action")
                payload      = msg.get("payload", {})
                execution_id = msg.get("execution_id", "")
                resolved_call_id = msg.get("call_id") or _find_call_id_for_ws()
                if resolved_call_id:
                    current_call_id = resolved_call_id
                if action_name and resolved_call_id and execution_id:
                    asyncio.create_task(
                        _execute_approved_action(
                            websocket, action_name, payload,
                            execution_id, agent_id, resolved_call_id,
                        )
                    )
                elif action_name and not resolved_call_id:
                    logger.warning(
                        "action_approved for '%s' dropped — could not resolve call_id",
                        action_name,
                    )

            elif msg_type == "action_rejected":
                action_name = msg.get("action", "unknown")
                resolved_call_id = msg.get("call_id") or _find_call_id_for_ws()
                if resolved_call_id:
                    current_call_id = resolved_call_id
                logger.info(
                    "Agent %s rejected action '%s' for call %s",
                    agent_name, action_name, resolved_call_id,
                )
                # Emit rejection to timeline
                await websocket.send_text(json.dumps({
                    "type": "activity_event",
                    "kind": "action_rejected",
                    "action": action_name,
                    "message": f"Agent rejected: {action_name.replace('_', ' ').title()}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Agent WS error: {e}")
    finally:
        app_state.connected_agents.pop(agent_id, None)
        _get_statuses(app_state).pop(agent_id, None)
        logger.info(f"Agent disconnected: {agent_id} ({agent_name})")


async def deliver_incoming_call(
    app_state,
    call_id: str,
    customer: dict,
    handoff_bundle: dict,
    voice_transcript: list[dict],
    escalation_token: str | None = None,
    esc_room_name: str | None = None,
    livekit_url: str | None = None,
) -> bool:
    """Called from ws_voice when a call is escalated. Delivers to first active agent.
    Queues the escalation (never drops) if no active agent is available right now."""
    connected: dict = getattr(app_state, "connected_agents", {})

    pending_item = {
        "call_id": call_id,
        "customer": customer,
        "handoff_bundle": handoff_bundle,
        "voice_transcript": voice_transcript,
        "escalation_token": escalation_token,
        "esc_room_name": esc_room_name,
        "livekit_url": livekit_url,
    }

    if not connected or get_active_agent_count(app_state) == 0:
        # No active agent right now — queue and deliver when one connects/reconnects.
        # Do NOT drop: the re-delivery hook on WS connect will flush this queue.
        if not hasattr(app_state, "pending_escalations"):
            app_state.pending_escalations = []
        app_state.pending_escalations.append(pending_item)
        logger.warning(f"Escalation for {call_id} queued — no active agents connected")
        return True

    await _send_escalation_to_agent(app_state, connected, pending_item)
    return True


async def _send_escalation_to_agent(app_state, connected: dict, item: dict) -> None:
    """Send one pending escalation item to the first active agent."""
    call_id          = item["call_id"]
    customer         = item["customer"]
    handoff_bundle   = item["handoff_bundle"]
    voice_transcript = item["voice_transcript"]
    escalation_token = item.get("escalation_token")
    esc_room_name    = item.get("esc_room_name")
    livekit_url      = item.get("livekit_url")
    statuses = _get_statuses(app_state)

    payload_dict = {
        "type": "incoming_call",
        "call_id": call_id,
        "customer": customer,
        "handoff_bundle": handoff_bundle,
        "voice_transcript": voice_transcript,
    }
    if escalation_token:
        payload_dict["escalation_token"] = escalation_token
    if esc_room_name:
        payload_dict["esc_room_name"] = esc_room_name
    if livekit_url:
        payload_dict["livekit_url"] = livekit_url
    payload = json.dumps(payload_dict)

    for agent_id, ws in list(connected.items()):
        if statuses.get(agent_id, "active") != "active":
            continue  # skip busy/inactive agents
        try:
            await ws.send_text(payload)
            session = ACTIVE_CALLS.get(call_id)
            if session:
                session.agent_ws = ws
            asyncio.create_task(
                _send_companion_update(
                    ws,
                    voice_transcript,
                    customer,
                    handoff_bundle,
                    workflow_type=_get_workflow_type(session),
                    completed_actions=session.completed_actions if session else None,
                )
            )
            logger.info(f"Escalated call {call_id} delivered to agent {agent_id}")
            return
        except Exception as e:
            logger.error(f"Failed to deliver to agent {agent_id}: {e}")
            connected.pop(agent_id, None)

    # All agents failed — re-queue
    if not hasattr(app_state, "pending_escalations"):
        app_state.pending_escalations = []
    app_state.pending_escalations.append(item)
    logger.warning(f"Escalation for {call_id} re-queued — all agents unreachable")


async def _decline_escalation(call_id: str) -> None:
    """Called when an agent clicks Decline — cancels escalation and returns customer to AI."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.backend_internal_url}/api/calls/{call_id}/cancel-escalation"
            )
    except Exception as exc:
        logger.warning("[%s] _decline_escalation cancel request failed: %s", call_id, exc)


async def deliver_transcript_line(app_state, speaker: str, text: str, call_id: str) -> None:
    """Forward live transcript lines to the agent desktop during an escalated call.

    Also fires a companion_update so the agent receives nudges and KB hits
    immediately after the customer speaks — not just after the agent speaks.
    """
    session = ACTIVE_CALLS.get(call_id)
    if not session or not session.agent_ws:
        return

    ws = session.agent_ws

    # Push transcript events for both customer AND agent speech.
    # The frontend deduplicates within a 3s window so Web Speech API + Deepgram don't double-print.
    if speaker in ("customer", "agent"):
        try:
            await ws.send_text(json.dumps({
                "type": "transcript",
                "speaker": speaker,
                "text": text,
                "is_final": True,
                "source": "deepgram",  # tag so frontend can deduplicate against Web Speech API
            }))
        except Exception:
            return  # WS is dead — nothing else to do

    # Fire companion updates on both customer AND agent speech.
    if speaker not in ("customer", "agent"):
        return

    transcript = [
        {"speaker": m.get("role", "user"), "text": m.get("content", "")}
        for m in session.conversation_history
        if m.get("content")
    ]
    transcript.append({"speaker": speaker, "text": text})

    asyncio.create_task(
        _send_companion_update(
            ws,
            transcript,
            {},
            session.handoff_bundle,
            workflow_type=_get_workflow_type(session),
            completed_actions=session.completed_actions,
        )
    )


async def deliver_otp_to_agent(app_state, call_id: str, otp_code: str) -> None:
    """Forward an OTP generated by the voice AI to the agent console activity timeline."""
    session = ACTIVE_CALLS.get(call_id)
    if not session or not session.agent_ws:
        return
    ws = session.agent_ws
    try:
        await ws.send_text(json.dumps({
            "type": "activity_event",
            "kind": "otp_sent_by_ai",
            "action": "send_otp",
            "message": f"Fin AI sent OTP: {otp_code} — customer will read this back.",
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }))
    except Exception:
        pass


def _get_workflow_type(session) -> str | None:
    if not session:
        return None
    wf = getattr(session, "workflow", None)
    if wf:
        return getattr(wf, "workflow_type", None) or getattr(wf, "intent", None)
    return getattr(session, "workflow_type", None)


async def _send_companion_update(
    ws: WebSocket,
    transcript: list[dict],
    customer: dict,
    handoff_bundle: dict | None = None,
    previous_mood: str = "calm",
    workflow_type: str | None = None,
    completed_actions: set | None = None,
) -> dict:
    try:
        update = await run_mid_call_companion(
            transcript,
            customer,
            handoff_bundle,
            workflow_type=workflow_type,
            previous_mood=previous_mood,
            completed_actions=completed_actions,
        )
        await ws.send_text(json.dumps({"type": "companion_update", **update}))
        return update
    except Exception as e:
        logger.error(f"Companion update error: {e}")
        return {}


async def _execute_approved_action(
    ws: WebSocket,
    action_name: str,
    payload: dict,
    execution_id: str,
    approved_by: str,
    call_id: str,
) -> None:
    """Execute an approved action: validate, run handler, audit log, notify frontend."""
    from orchestration.engine import execute_action
    from orchestration.action_registry import ActionExecutionError, ActionNotFoundError, WorkflowMismatchError
    from database import AsyncSessionLocal

    ts = datetime.now(timezone.utc).isoformat()

    # Emit "activity_event: approved" before execution (timeline UX)
    try:
        await ws.send_text(json.dumps({
            "type": "activity_event",
            "kind": "action_approved",
            "action": action_name,
            "message": f"Agent approved: {action_name.replace('_', ' ').title()}",
            "timestamp": ts,
        }))
    except Exception:
        pass

    # Enrich payload with customer_id from session if the LLM omitted it
    payload = dict(payload)
    if not payload.get("customer_id"):
        sess = ACTIVE_CALLS.get(call_id)
        if sess:
            profile = sess.customer_profile or {}
            cid = sess.customer_id or profile.get("customer_id")
            if cid:
                payload["customer_id"] = cid

    try:
        async with AsyncSessionLocal() as db:
            result = await execute_action(
                action_name=action_name,
                payload=payload,
                approved_by=approved_by,
                execution_id=execution_id,
                call_id=call_id,
                db=db,
            )

        # Mark action completed in session so companion won't re-suggest it
        sess = ACTIVE_CALLS.get(call_id)
        if sess:
            sess.completed_actions.add(action_name)

        # Notify frontend: success
        await ws.send_text(json.dumps({
            "type": "action_result",
            "action": action_name,
            "success": True,
            "message": result.get("message", "Action completed successfully."),
            "updated_entities": result.get("updated_entities", {}),
        }))

        # Emit executed event to activity timeline
        await ws.send_text(json.dumps({
            "type": "activity_event",
            "kind": "action_executed",
            "action": action_name,
            "message": result.get("message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))

        logger.info("[%s] Action '%s' executed by %s", call_id, action_name, approved_by)

    except (ActionNotFoundError, WorkflowMismatchError, ActionExecutionError) as exc:
        await ws.send_text(json.dumps({
            "type": "action_result",
            "action": action_name,
            "success": False,
            "message": str(exc),
        }))
        logger.warning("[%s] Action '%s' failed: %s", call_id, action_name, exc)
    except Exception as exc:
        await ws.send_text(json.dumps({
            "type": "action_result",
            "action": action_name,
            "success": False,
            "message": f"Unexpected error — please try again.",
        }))
        logger.exception("[%s] Unexpected error in action '%s'", call_id, action_name)


async def _send_acw(
    ws: WebSocket,
    transcript: list[dict],
    customer: dict,
    call_id: str,
) -> None:
    try:
        acw = await run_acw_agent(transcript, customer, call_id)
        await ws.send_text(json.dumps({"type": "acw_ready", **acw}))
    except Exception as e:
        logger.error(f"ACW generation error: {e}")


async def _persist_acw(call_id: str, acw: dict) -> None:
    """Persist ACW data — updates calls.acw_summary and resolution."""
    try:
        from database import AsyncSessionLocal
        from models.call import Call
        from sqlalchemy import update as sql_update
        import uuid

        async with AsyncSessionLocal() as db:
            await db.execute(
                sql_update(Call)
                .where(Call.id == uuid.UUID(call_id))
                .values(
                    acw_summary=acw.get("summary", ""),
                    resolution=acw.get("resolution", "unresolved"),
                    crm_updated=True,
                )
            )
            await db.commit()
        logger.info(f"ACW persisted for call {call_id}")
    except Exception as e:
        logger.error(f"ACW persist error: {e}")
