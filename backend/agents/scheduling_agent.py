"""
Scheduling agent — production-ready for hackathon/demo.

Responsibilities:
  - Natural language time parsing via dateparser (regex fallback for speed)
  - Parse confidence scoring: high / medium / low → clarification when low
  - Business hours + slot conflict checking (DB-backed)
  - UTC storage; user timezone for display labels
  - Slot race condition prevention via slot_key UNIQUE constraint
  - Cancellation + rescheduling with history tracking
  - Email confirmation (no misleading "calendar invite" wording)
  - Structured JSON logging for every booking event

AI never commits bookings — all DB mutations happen here, deterministically.
"""
import asyncio
import json
import logging
import re
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from zoneinfo import ZoneInfo

import dateparser

from config import settings
from database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


# ── Scheduling policy ─────────────────────────────────────────────────────────

@dataclass
class SchedulingPolicy:
    """Lightweight configurable scheduling rules. All times in local TZ."""
    timezone:           str          = "Asia/Kolkata"
    working_days:       frozenset    = field(default_factory=lambda: frozenset({0, 1, 2, 3, 4}))
    slot_start_hour:    int          = 9     # 9 AM
    slot_end_hour:      int          = 17    # 5 PM
    min_notice_hours:   int          = 1     # must book at least 1h ahead
    max_advance_days:   int          = 30    # can't book more than 30 days out
    slot_duration_hours: int         = 1

DEFAULT_POLICY = SchedulingPolicy()


# ── Parse result ──────────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    dt:         Optional[datetime]   # UTC tz-aware, or None if unparseable
    confidence: float                # 0.0 – 1.0
    ambiguous:  bool                 # True → ask for clarification
    raw_text:   str
    partial:    dict = field(default_factory=dict)  # e.g. {"day": "thursday"}


# ── Confidence scoring ────────────────────────────────────────────────────────

_VAGUE_WORDS = frozenset({
    "sometime", "maybe", "probably", "perhaps", "around", "ish",
    "later", "soon", "whenever", "flexible", "roughly", "approximately",
})
_PERIOD_WORDS = frozenset({"morning", "afternoon", "evening", "noon", "lunchtime"})
_DAY_WORDS = frozenset({
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "tomorrow", "today",
})
_EXPLICIT_TIME_RE = re.compile(
    r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b', re.IGNORECASE
)
_DATE_RE = re.compile(
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}'
    r'|\b\d{1,2}(?:st|nd|rd|th)\b',
    re.IGNORECASE,
)
_DAY_RE = re.compile(
    r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today)\b',
    re.IGNORECASE,
)


def _score_confidence(text: str, dt: Optional[datetime]) -> tuple[float, bool]:
    """
    Returns (confidence 0.0–1.0, is_ambiguous).

    High   ≥0.80: specific day + explicit time, dateparser succeeded
    Medium  0.55–0.79: day known but time unclear, or dateparser inferred
    Low    <0.55: no clear reference, dateparser failed or very vague
    """
    if dt is None:
        return 0.25, True

    t = text.lower()
    words = set(t.split())

    has_vague        = bool(words & _VAGUE_WORDS)
    has_explicit_time = bool(_EXPLICIT_TIME_RE.search(t))
    has_day          = bool(_DAY_RE.search(t))
    has_date         = bool(_DATE_RE.search(t))
    has_period       = any(w in t for w in _PERIOD_WORDS)
    has_period_only  = has_period and not has_day and not has_date

    # Vague modifier always pulls confidence down
    if has_vague:
        if has_explicit_time and (has_day or has_date):
            return 0.62, True   # "maybe tuesday at 3pm" — parseable but hedged
        return 0.38, True

    if has_period_only:
        return 0.48, True       # "afternoon" — need a day

    if (has_explicit_time or has_date) and (has_day or has_date):
        return 0.92, False      # "tuesday at 3pm", "May 27th at 10am"

    if has_explicit_time:
        return 0.74, False      # "3pm" alone — day inferred from context

    if has_day and has_period:
        return 0.72, False      # "friday afternoon", "tuesday morning" — clear enough

    if has_day:
        return 0.57, True       # "thursday" — day known, time unclear

    if has_date:
        return 0.68, True       # "May 27th" — date known, time unclear

    return 0.42, True


# ── Natural language parser ───────────────────────────────────────────────────

_PARTIAL_DAY_RE = re.compile(
    r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today)\b',
    re.IGNORECASE,
)


def _parse_preferred_time(text: str, user_tz: str = "Asia/Kolkata") -> ParseResult:
    """
    Parse a natural language time expression to a UTC-aware datetime.
    Primary: dateparser. Confidence scoring decides if clarification is needed.
    """
    raw = text.strip()

    try:
        dt = dateparser.parse(raw, settings={
            "TIMEZONE": user_tz,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
            "PREFER_DAY_OF_MONTH": "first",
            "PARSERS": [
                "relative-time", "absolute-time",
                "custom-formats", "no-spaces-time",
            ],
        })
    except Exception:
        dt = None

    # Convert to UTC for internal storage
    if dt is not None:
        dt = dt.astimezone(UTC)

    confidence, ambiguous = _score_confidence(raw, dt)

    partial: dict = {}
    m = _PARTIAL_DAY_RE.search(raw)
    if m:
        partial["day"] = m.group(1).lower()

    _log("slot_parse", preferred_time=raw,
         parsed_dt=dt.isoformat() if dt else None,
         confidence=round(confidence, 2), ambiguous=ambiguous)

    return ParseResult(dt=dt, confidence=confidence,
                       ambiguous=ambiguous, raw_text=raw, partial=partial)


# ── Business hours helpers ────────────────────────────────────────────────────

def _is_business_slot(dt: datetime, policy: SchedulingPolicy = DEFAULT_POLICY) -> bool:
    local = dt.astimezone(ZoneInfo(policy.timezone))
    return (
        local.weekday() in policy.working_days
        and policy.slot_start_hour <= local.hour < policy.slot_end_hour
    )


def _is_within_booking_window(
    dt: datetime, policy: SchedulingPolicy = DEFAULT_POLICY
) -> bool:
    now = datetime.now(UTC)
    return (
        now + timedelta(hours=policy.min_notice_hours) <= dt
        <= now + timedelta(days=policy.max_advance_days)
    )


def _next_business_slot(
    from_dt: datetime, policy: SchedulingPolicy = DEFAULT_POLICY
) -> datetime:
    """First valid business slot strictly after from_dt."""
    tz = ZoneInfo(policy.timezone)
    local = from_dt.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    local = local + timedelta(hours=1)

    for _ in range(policy.max_advance_days * 24):
        candidate = local.astimezone(UTC)
        if _is_business_slot(candidate, policy) and _is_within_booking_window(candidate, policy):
            return candidate
        local += timedelta(hours=1)

    raise RuntimeError("No available slot found within booking window")


# ── Slot labels ───────────────────────────────────────────────────────────────

def _fmt_hour(h: int) -> str:
    suf = "AM" if h < 12 else "PM"
    h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    return f"{h12} {suf}"


def slot_label(dt: datetime, tz_name: str = "Asia/Kolkata") -> str:
    """e.g. 'Monday, May 26 at 2 PM IST'"""
    local = dt.astimezone(ZoneInfo(tz_name))
    tz_abbr = "IST" if tz_name == "Asia/Kolkata" else local.strftime("%Z")
    return f"{local.strftime('%A, %b %d')} at {_fmt_hour(local.hour)} {tz_abbr}"


def slot_label_short(dt: datetime, tz_name: str = "Asia/Kolkata") -> str:
    """e.g. 'Monday at 2 PM'"""
    local = dt.astimezone(ZoneInfo(tz_name))
    return f"{local.strftime('%A')} at {_fmt_hour(local.hour)}"


def _slot_key(dt: datetime) -> str:
    """UTC 1-hour bucket key: 'YYYY-MM-DD-HH'. Used for UNIQUE constraint."""
    return dt.astimezone(UTC).strftime("%Y-%m-%d-%H")


# ── DB availability ───────────────────────────────────────────────────────────

async def _booked_slot_keys(start: datetime, policy: SchedulingPolicy = DEFAULT_POLICY) -> set[str]:
    """Returns slot_keys currently confirmed in DB, from start + max_advance_days window."""
    end = start.astimezone(UTC) + timedelta(days=policy.max_advance_days)
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text("""
                    SELECT slot_key FROM demo_appointments
                    WHERE status = 'confirmed'
                      AND confirmed_time >= :start
                      AND confirmed_time <  :end
                      AND slot_key IS NOT NULL
                """),
                {"start": start.astimezone(UTC), "end": end},
            )
            return {r[0] for r in rows.fetchall() if r[0]}
    except Exception as exc:
        logger.warning(_log_str("booked_slots_error", error=str(exc)))
        return set()


# ── Clarification response selection ─────────────────────────────────────────

def _clarification_response(parse: ParseResult) -> tuple[str, dict]:
    """Pick the right clarification fast-response key + template vars."""
    if parse.partial.get("day"):
        return "clarify_time_on_day", {"day": parse.partial["day"].capitalize()}
    if parse.dt is not None:
        # Has a time but no recognizable day
        return "clarify_day_of_week", {}
    return "clarify_vague_time", {}


# ── Main resolve entry point ──────────────────────────────────────────────────

async def resolve_slot(
    preferred_time_str: str,
    user_tz: str = "Asia/Kolkata",
    policy: SchedulingPolicy = DEFAULT_POLICY,
) -> dict:
    """
    Resolve a natural language time expression to a bookable slot.

    Returns:
        confirmed_time      : UTC datetime | None
        slot_label          : str | None
        slot_label_short    : str | None
        is_alternative      : bool
        alt_reason          : "out_of_hours" | "conflict" | "too_soon" | None
        needs_clarification : bool  — True when confidence too low to proceed
        clarification_key   : str | None — fast-response key
        clarification_vars  : dict
        parse_confidence    : float
    """
    parse = _parse_preferred_time(preferred_time_str, user_tz)

    # Low confidence or ambiguous without specific enough info → ask
    clarify_threshold = 0.55
    if parse.confidence < clarify_threshold or (parse.ambiguous and parse.confidence < 0.65):
        ckey, cvars = _clarification_response(parse)
        _log("clarification_requested", preferred_time=preferred_time_str,
             confidence=round(parse.confidence, 2), key=ckey)
        return {
            "confirmed_time":      None,
            "slot_label":          None,
            "slot_label_short":    None,
            "is_alternative":      False,
            "alt_reason":          None,
            "needs_clarification": True,
            "clarification_key":   ckey,
            "clarification_vars":  cvars,
            "parse_confidence":    parse.confidence,
        }

    # "anytime" / unparseable but medium-confidence → pick next free slot
    if parse.dt is None:
        requested = _next_business_slot(datetime.now(UTC), policy)
        is_alt, alt_reason = False, None
    else:
        requested = parse.dt

    # --- Booking window checks ---
    now = datetime.now(UTC)
    too_soon = requested < now + timedelta(hours=policy.min_notice_hours)
    too_far  = requested > now + timedelta(days=policy.max_advance_days)

    if too_soon or not _is_business_slot(requested, policy):
        snapped    = _next_business_slot(requested if not too_soon else now, policy)
        is_alt     = True
        alt_reason = "too_soon" if too_soon else "out_of_hours"
    elif too_far:
        snapped    = now + timedelta(days=policy.max_advance_days - 1)
        snapped    = _next_business_slot(snapped, policy)
        is_alt     = True
        alt_reason = "too_far"
    else:
        snapped    = requested
        is_alt     = False
        alt_reason = None

    # --- Conflict check against DB ---
    booked = await _booked_slot_keys(snapped, policy)
    key    = _slot_key(snapped)

    if key in booked:
        # Scan forward for up to 2 free alternatives
        candidate = snapped + timedelta(hours=policy.slot_duration_hours)
        alts = []
        for _ in range(policy.max_advance_days * 8):
            if (_is_business_slot(candidate, policy)
                    and _slot_key(candidate) not in booked
                    and _is_within_booking_window(candidate, policy)):
                alts.append(candidate)
                if len(alts) == 2:
                    break
            candidate += timedelta(hours=1)

        if not alts:
            _log("booking_conflict", original_key=key, result="no_slots")
            return {
                "confirmed_time":      None, "slot_label": None, "slot_label_short": None,
                "is_alternative":      True,  "alt_reason": "no_slots",
                "needs_clarification": False, "clarification_key": None,
                "clarification_vars":  {},    "parse_confidence": parse.confidence,
            }

        _log("booking_conflict", original_key=key, chosen=_slot_key(alts[0]))
        snapped    = alts[0]
        is_alt     = True
        alt_reason = "conflict"

    _log("slot_resolved", slot_key=_slot_key(snapped),
         is_alternative=is_alt, alt_reason=alt_reason,
         confidence=round(parse.confidence, 2))

    return {
        "confirmed_time":      snapped,
        "slot_label":          slot_label(snapped, user_tz),
        "slot_label_short":    slot_label_short(snapped, user_tz),
        "is_alternative":      is_alt,
        "alt_reason":          alt_reason,
        "needs_clarification": False,
        "clarification_key":   None,
        "clarification_vars":  {},
        "parse_confidence":    parse.confidence,
    }


# ── Cancellation ─────────────────────────────────────────────────────────────

async def cancel_appointment(call_id: str) -> dict:
    """
    Mark the most recent confirmed appointment for this call as cancelled.
    Sends cancellation email if address is available.
    """
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text("""
                SELECT da.id, da.slot_label, da.confirmed_time,
                       l.email, l.name
                FROM demo_appointments da
                JOIN leads l ON l.id = da.lead_id
                WHERE da.call_id = :call_id
                  AND da.status  = 'confirmed'
                ORDER BY da.created_at DESC
                LIMIT 1
            """),
            {"call_id": call_id},
        )
        appt = row.mappings().first()

    if not appt:
        _log("cancel_not_found", call_id=call_id)
        return {"success": False, "reason": "no_active_appointment"}

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE demo_appointments SET status = 'cancelled' WHERE id = :id"),
            {"id": appt["id"]},
        )
        await db.commit()

    _log("booking_cancelled", call_id=call_id, appointment_id=str(appt["id"]))

    if appt.get("email"):
        asyncio.create_task(
            send_cancellation_email(
                appt["name"] or "", appt["email"],
                appt["slot_label"] or "your demo", call_id,
            )
        )

    return {
        "success":        True,
        "appointment_id": str(appt["id"]),
        "slot_label":     appt.get("slot_label") or "",
        "name":           appt.get("name") or "",
        "email":          appt.get("email"),
    }


# ── Rescheduling ─────────────────────────────────────────────────────────────

async def reschedule_appointment(
    call_id: str,
    new_preferred_time: str,
    user_tz: str = "Asia/Kolkata",
    policy: SchedulingPolicy = DEFAULT_POLICY,
    force_slot: dict | None = None,
) -> dict:
    """
    Cancel the current confirmed appointment and book a replacement.

    If force_slot is provided (user already confirmed an alternative),
    bypass resolve_slot and book the pre-resolved slot directly.

    Returns a result dict compatible with schedule_demo return shape.
    """
    # Find current confirmed appointment
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text("""
                SELECT da.id, da.confirmed_time, da.slot_label,
                       da.lead_id, da.reschedule_count, l.name, l.email
                FROM demo_appointments da
                JOIN leads l ON l.id = da.lead_id
                WHERE da.call_id = :call_id
                  AND da.status  = 'confirmed'
                ORDER BY da.created_at DESC
                LIMIT 1
            """),
            {"call_id": call_id},
        )
        appt = row.mappings().first()

    if not appt:
        return {"success": False, "reason": "no_active_appointment"}

    # Resolve the new slot
    if force_slot:
        from datetime import datetime as _dt
        new_confirmed = _dt.fromisoformat(force_slot["confirmed_time_iso"])
        lbl           = force_slot["slot_label"]
        lbl_short     = force_slot["slot_label_short"]
        needs_conf    = False
        alt_reason    = None
    else:
        slot_info = await resolve_slot(new_preferred_time, user_tz, policy)

        if slot_info.get("needs_clarification"):
            return {
                "success":             True,
                "needs_clarification": True,
                "clarification_key":   slot_info["clarification_key"],
                "clarification_vars":  slot_info["clarification_vars"],
            }
        if slot_info.get("alt_reason") == "no_slots":
            return {"success": False, "reason": "no_slots"}

        new_confirmed = slot_info["confirmed_time"]
        lbl           = slot_info["slot_label"]
        lbl_short     = slot_info["slot_label_short"]
        needs_conf    = slot_info["is_alternative"]
        alt_reason    = slot_info.get("alt_reason")

    if needs_conf:
        suggest_key = (
            "demo_slot_suggest_out_of_hours"
            if alt_reason == "out_of_hours"
            else "demo_slot_suggest_conflict"
        )
        return {
            "success":           True,
            "needs_confirmation": True,
            "pending_slot": {
                "confirmed_time_iso": new_confirmed.isoformat(),
                "slot_label":         lbl,
                "slot_label_short":   lbl_short,
                "alt_reason":         alt_reason,
                "is_reschedule":      True,
                "old_appointment_id": str(appt["id"]),
            },
            "fast_response_key": suggest_key,
            "template_vars":     {"slot_label": lbl_short},
        }

    # Commit: mark old as rescheduled, insert new
    new_appt_id = await _commit_reschedule(appt, new_confirmed, lbl, new_preferred_time,
                                            user_tz, call_id)

    _log("rescheduled", call_id=call_id,
         old_id=str(appt["id"]), new_id=new_appt_id,
         new_slot_key=_slot_key(new_confirmed))

    if appt.get("email"):
        asyncio.create_task(
            send_confirmation_email(
                appt["name"] or "", appt["email"], lbl, call_id, is_reschedule=True
            )
        )

    return {
        "success":           True,
        "appointment_id":    new_appt_id,
        "fast_response_key": "demo_rescheduled",
        "template_vars": {
            "name":       appt.get("name") or "",
            "email":      appt.get("email") or "your email",
            "slot_label": lbl_short,
        },
    }


async def _commit_reschedule(appt, new_confirmed, lbl, raw_time, user_tz, call_id) -> str:
    """Cancel old appointment + insert new one in a single transaction."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE demo_appointments SET status = 'rescheduled' WHERE id = :id"),
            {"id": appt["id"]},
        )
        result = await db.execute(
            text("""
                INSERT INTO demo_appointments
                    (lead_id, call_id, requested_time, confirmed_time, slot_label,
                     slot_key, user_timezone, previous_confirmed_time,
                     rescheduled_at, reschedule_count, status)
                VALUES
                    (:lead_id, :call_id, :req, :confirmed, :lbl,
                     :slot_key, :tz, :prev, NOW(), :rcount, 'confirmed')
                RETURNING id
            """),
            {
                "lead_id":   appt["lead_id"],
                "call_id":   call_id,
                "req":       raw_time,
                "confirmed": new_confirmed,
                "lbl":       lbl,
                "slot_key":  _slot_key(new_confirmed),
                "tz":        user_tz,
                "prev":      appt["confirmed_time"],
                "rcount":    (appt.get("reschedule_count") or 0) + 1,
            },
        )
        new_id = str(result.scalar())
        await db.commit()
    return new_id


# ── Email ─────────────────────────────────────────────────────────────────────

async def send_confirmation_email(
    name: str, to_email: str, slot_lbl: str, call_id: str,
    is_reschedule: bool = False,
) -> bool:
    action  = "rescheduled" if is_reschedule else "confirmed"
    subject = f"Your Wavvy Demo is {action.capitalize()}"
    body = (
        f"Hi {name},\n\n"
        f"Your Wavvy demo has been {action} for {slot_lbl}.\n\n"
        f"We'll send the meeting details before your scheduled demo.\n\n"
        f"Need to reschedule? Join another call at wavvy.ai or reply to this email.\n"
        f"To cancel, reply with 'CANCEL' in the subject.\n\n"
        f"Looking forward to connecting!\n\n"
        f"The Wavvy Team"
    )
    return await _send_email(subject, body, to_email, call_id)


async def send_cancellation_email(
    name: str, to_email: str, slot_lbl: str, call_id: str
) -> bool:
    subject = "Your Wavvy Demo Has Been Cancelled"
    body = (
        f"Hi {name},\n\n"
        f"Your Wavvy demo scheduled for {slot_lbl} has been cancelled.\n\n"
        f"To book again, visit wavvy.ai or start a new call.\n\n"
        f"The Wavvy Team"
    )
    return await _send_email(subject, body, to_email, call_id)


async def send_reminder_email(
    name: str, to_email: str, slot_lbl: str, call_id: str, hours_until: int
) -> bool:
    label   = "in 1 hour" if hours_until <= 1 else "tomorrow"
    subject = f"Reminder: Your Wavvy Demo is {label}"
    body = (
        f"Hi {name},\n\n"
        f"Just a reminder — your Wavvy demo is scheduled for {slot_lbl}.\n\n"
        f"Our team will reach out with the meeting link shortly.\n\n"
        f"The Wavvy Team"
    )
    return await _send_email(subject, body, to_email, call_id)


async def _send_email(subject: str, body: str, to_email: str, call_id: str) -> bool:
    smtp_host = getattr(settings, "smtp_host", "")
    smtp_user = getattr(settings, "smtp_user", "")
    smtp_pass = getattr(settings, "smtp_pass", "")
    from_addr = getattr(settings, "smtp_from", smtp_user or "wavvy@wavvy.ai")

    if not smtp_host or not smtp_user:
        logger.info(f"[{call_id}] Email (SMTP not configured) → {to_email}: {subject}")
        return True

    try:
        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        msg_str = msg.as_string()

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _smtp_send(smtp_host, smtp_user, smtp_pass, from_addr, to_email, msg_str),
        )
        _log("email_sent", call_id=call_id, to=to_email, subject=subject)
        return True
    except Exception as exc:
        logger.warning(_log_str("email_failed", call_id=call_id, error=str(exc)))
        return False


def _smtp_send(host, user, password, from_addr, to_addr, msg_str):
    with smtplib.SMTP_SSL(host, 465) as srv:
        srv.login(user, password)
        srv.sendmail(from_addr, to_addr, msg_str)


# ── Structured logging helpers ────────────────────────────────────────────────

def _log(event: str, **kwargs) -> None:
    logger.info(json.dumps({"event": event, **kwargs}))


def _log_str(event: str, **kwargs) -> str:
    return json.dumps({"event": event, **kwargs})
