"""
Lightweight demo reminder service.

Sends T-24h and T-1h email reminders for confirmed demo appointments.
Runs as a periodic background asyncio task — no external queue needed.

Usage (called from main.py lifespan):
    asyncio.create_task(start_reminder_loop())
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from database import AsyncSessionLocal

logger = logging.getLogger(__name__)

UTC = timezone.utc

# How often to poll for upcoming appointments (seconds)
REMINDER_CHECK_INTERVAL = 600   # every 10 minutes

# Windows: send reminder if appointment is within [now+X-buffer, now+X+buffer]
_WINDOWS = [
    (timedelta(hours=24), timedelta(minutes=10), 24),
    (timedelta(hours=1),  timedelta(minutes=5),  1),
]


async def _check_and_send() -> None:
    """Find appointments due for a reminder and send emails.

    Only runs when the active tenant config has schedule_demo enabled.
    Silently skips for Fin (fintech) tenants where demo_appointments was dropped.
    """
    try:
        from config_loader import get_config
        cfg = get_config()
        if not cfg.tool_configs.get("schedule_demo", {}).get("enabled", False):
            return
    except Exception:
        return  # config not loaded yet — skip silently

    now = datetime.now(UTC)

    for target_offset, tolerance, hours_label in _WINDOWS:
        window_start = now + target_offset - tolerance
        window_end   = now + target_offset + tolerance

        try:
            async with AsyncSessionLocal() as db:
                rows = await db.execute(
                    text("""
                        SELECT da.id, da.confirmed_time, da.slot_label,
                               da.call_id, l.name, l.email
                        FROM demo_appointments da
                        JOIN leads l ON l.id = da.lead_id
                        WHERE da.status      = 'confirmed'
                          AND da.confirmed_time >= :ws
                          AND da.confirmed_time <  :we
                          AND l.email IS NOT NULL
                    """),
                    {"ws": window_start, "we": window_end},
                )
                appointments = rows.mappings().all()
        except Exception as exc:
            logger.warning(f"Reminder check DB error: {exc}")
            continue

        for appt in appointments:
            try:
                from agents.scheduling_agent import send_reminder_email
                await send_reminder_email(
                    name        = appt["name"] or "there",
                    to_email    = appt["email"],
                    slot_lbl    = appt["slot_label"] or str(appt["confirmed_time"]),
                    call_id     = str(appt["call_id"] or ""),
                    hours_until = hours_label,
                )
                logger.info(
                    f"Reminder sent: appt={appt['id']} hours={hours_label} "
                    f"to={appt['email']}"
                )
            except Exception as exc:
                logger.warning(f"Reminder email failed for appt {appt['id']}: {exc}")


async def start_reminder_loop() -> None:
    """Runs forever, checking for reminders every REMINDER_CHECK_INTERVAL seconds."""
    logger.info("Reminder service started")
    while True:
        try:
            await _check_and_send()
        except Exception as exc:
            logger.error(f"Reminder loop error: {exc}")
        await asyncio.sleep(REMINDER_CHECK_INTERVAL)
