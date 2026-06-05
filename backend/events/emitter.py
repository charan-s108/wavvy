"""
Lightweight event emitter for observability events.
Handlers subscribe at startup; events are fire-and-forget asyncio tasks.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_handlers: list = []


def subscribe(handler) -> None:
    """Register a handler coroutine to receive all events."""
    _handlers.append(handler)


async def emit(event_type: str, payload: dict, call_id: str | None = None) -> None:
    """Emit an event to all registered handlers. Non-blocking."""
    event = {
        "type": event_type,
        "call_id": call_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    for handler in _handlers:
        asyncio.create_task(handler(event))
    logger.debug("event %s call=%s", event_type, call_id)
