"""
Supervisor WebSocket — replaces dashboard polling with push events.

Events pushed to connected tabs:
  init         — sent on connect; current live calls
  call_started — new call began
  call_ended   — call finished (triggers client to refetch KPIs + history)
  eval_ready   — QA score available for a call_id

Single-process asyncio: module-level list is safe.
Multi-worker upgrade path: swap _supervisor_sockets for Redis pub/sub.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from session.call_session import ACTIVE_CALLS

logger = logging.getLogger(__name__)
router = APIRouter()

_supervisor_sockets: list[WebSocket] = []


async def broadcast_supervisor_event(event: dict) -> None:
    """Push to all connected supervisor tabs. Never raises."""
    if not _supervisor_sockets:
        return
    payload = json.dumps(event)
    dead: list[WebSocket] = []
    for ws in _supervisor_sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _supervisor_sockets.remove(ws)
        except ValueError:
            pass


@router.websocket("/ws/supervisor")
async def supervisor_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _supervisor_sockets.append(websocket)
    logger.info("Supervisor connected (%d total)", len(_supervisor_sockets))

    try:
        live = [
            {"call_id": cid, "started_at": s.started_at.isoformat()}
            for cid, s in ACTIVE_CALLS.items()
        ]
        await websocket.send_text(json.dumps({
            "type":        "init",
            "live_calls":  live,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }))

        while True:
            await websocket.receive_text()   # drain client pings / keep-alive

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Supervisor WS error: %s", exc)
    finally:
        try:
            _supervisor_sockets.remove(websocket)
        except ValueError:
            pass
        logger.info("Supervisor disconnected (%d remaining)", len(_supervisor_sockets))
