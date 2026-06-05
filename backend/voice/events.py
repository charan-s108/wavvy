"""
In-process async event bus — Kafka-ready interface.
Implementation: simple async callbacks (dict of event_type → list[handler]).
Swap emit() internals for a queue producer when horizontal scaling requires it.
Do NOT add Kafka/Redis now.

All handlers fire via asyncio.create_task() — a failing handler never blocks
the call or affects other handlers.
"""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)

# ── Event types ───────────────────────────────────────────────────────────────

from dataclasses import dataclass


@dataclass
class LeadCapturedEvent:
    call_id: str
    lead_id: str
    name: str
    email: str | None
    intent: str

@dataclass
class DemoScheduledEvent:
    call_id: str
    lead_id: str
    name: str
    email: str | None
    requested_time: str

@dataclass
class EscalationRequestedEvent:
    call_id: str
    reason: str
    packet: object     # EscalationPacket — typed at runtime to avoid circular import

@dataclass
class ActionExpiredEvent:
    call_id: str
    tool: str          # the tool that was pending when action expired

@dataclass
class CallStartedEvent:
    call_id: str
    call_mode: str

@dataclass
class CallCompletedEvent:
    call_id: str
    resolution: str
    duration_sec: int

@dataclass
class CallFailedEvent:
    call_id: str
    reason: str

# ── Bus internals ─────────────────────────────────────────────────────────────

_HANDLERS: dict[type, list[Callable]] = defaultdict(list)


def register(event_type: type, handler: Callable) -> None:
    """Register an async handler for an event type."""
    _HANDLERS[event_type].append(handler)


async def _safe_call(handler: Callable, event) -> None:
    """Each handler runs in isolation — failures never propagate."""
    try:
        await handler(event)
    except Exception as exc:
        logger.error(f"Event handler {handler.__name__} failed for "
                     f"{type(event).__name__}: {exc}")


async def emit(event) -> None:
    """
    Fire-and-forget: dispatches to all registered handlers for the event type.
    Each handler runs in its own asyncio task — isolated from the call flow.
    """
    handlers = _HANDLERS.get(type(event), [])
    for handler in handlers:
        asyncio.create_task(_safe_call(handler, event))


# ── Built-in lifecycle handlers ───────────────────────────────────────────────
# Registered at app startup in main.py. Each handler is individually try/excepted.

async def _on_call_started(event: CallStartedEvent) -> None:
    logger.info(f"[{event.call_id}] Call started mode={event.call_mode}")

async def _on_call_completed(event: CallCompletedEvent) -> None:
    logger.info(f"[{event.call_id}] Call completed resolution={event.resolution} "
                f"duration={event.duration_sec}s")

async def _on_call_failed(event: CallFailedEvent) -> None:
    logger.error(f"[{event.call_id}] Call failed reason={event.reason}")

async def _on_escalation_requested(event: EscalationRequestedEvent) -> None:
    logger.info(f"[{event.call_id}] Escalation requested reason={event.reason}")

async def _on_lead_captured(event: LeadCapturedEvent) -> None:
    logger.info(f"[{event.call_id}] Lead captured name={event.name} intent={event.intent}")

async def _on_demo_scheduled(event: DemoScheduledEvent) -> None:
    logger.info(f"[{event.call_id}] Demo scheduled name={event.name} time={event.requested_time}")

async def _on_action_expired(event: ActionExpiredEvent) -> None:
    logger.info(f"[{event.call_id}] Pending action expired tool={event.tool}")


def register_lifecycle_handlers() -> None:
    """Called once at app startup (main.py lifespan)."""
    register(CallStartedEvent,         _on_call_started)
    register(CallCompletedEvent,       _on_call_completed)
    register(CallFailedEvent,          _on_call_failed)
    register(EscalationRequestedEvent, _on_escalation_requested)
    register(LeadCapturedEvent,        _on_lead_captured)
    register(DemoScheduledEvent,       _on_demo_scheduled)
    register(ActionExpiredEvent,       _on_action_expired)
