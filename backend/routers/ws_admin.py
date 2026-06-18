"""
Admin WebSocket — replaces dashboard polling with push events.

Events pushed to connected tabs:
  init         — sent on connect; current live calls
  call_started — new call began
  call_ended   — call finished (triggers client to refetch KPIs + history)
  eval_ready   — QA score available for a call_id

Single-process asyncio: module-level list is safe.
Multi-worker upgrade path: swap _admin_sockets for Redis pub/sub.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from session.call_session import ACTIVE_CALLS

logger = logging.getLogger(__name__)
router = APIRouter()

_admin_sockets: list[WebSocket] = []


async def broadcast_admin_event(event: dict) -> None:
    """Push to all connected admin tabs. Never raises."""
    if not _admin_sockets:
        return
    payload = json.dumps(event)
    dead: list[WebSocket] = []
    for ws in _admin_sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _admin_sockets.remove(ws)
        except ValueError:
            pass


@router.websocket("/ws/admin")
async def admin_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _admin_sockets.append(websocket)
    logger.info("Admin connected (%d total)", len(_admin_sockets))

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
        logger.warning("Admin WS error: %s", exc)
    finally:
        try:
            _admin_sockets.remove(websocket)
        except ValueError:
            pass
        logger.info("Admin disconnected (%d remaining)", len(_admin_sockets))
