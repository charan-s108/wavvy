"""
@function_tool implementations — config-driven, one factory per call.

make_agent_tools() reads the active tenant config and returns only the tools
that are enabled. Concurrent calls are isolated via closures.
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

from config import settings
from config_loader import get_config
from livekit.agents import function_tool
from voice.tool_recovery import execute_with_recovery

logger = logging.getLogger(__name__)

_PLACEHOLDER_FRAGMENTS = {
    "your name", "your email", "your preferred time", "preferred time",
    "your time", "name here", "email here", "example.com", "test@",
    "placeholder", "unknown", "n/a", "none",
}


def _is_placeholder(value: str) -> bool:
    v = value.lower().strip()
    if not v:
        return True
    for fragment in _PLACEHOLDER_FRAGMENTS:
        if fragment in v:
            return True
    return False


def _is_valid_email(value: str) -> bool:
    at = value.find("@")
    return at > 0 and "." in value[at:]


def _normalize_email(raw: str) -> str:
    v = raw.strip()
    v = re.sub(r'\bat\s+the\s+rate\b', '@', v, flags=re.I)
    v = re.sub(r'\battherate\b', '@', v, flags=re.I)
    v = re.sub(r'@(?:at)?therate', '@', v, flags=re.I)
    v = re.sub(r'(\w)attherate(\w)', r'\1@\2', v, flags=re.I)
    v = re.sub(r'(\w)\s+at\s+(\w)', r'\1@\2', v, flags=re.I)
    v = re.sub(r'(\w)\s+dot\s+(\w)', r'\1.\2', v, flags=re.I)
    v = re.sub(r'\s*@\s*', '@', v)
    v = re.sub(r'\s*\.\s*', '.', v)
    return v.lower().strip()


def _name_is_confirmed(name: str, history: list) -> bool:
    name_l = name.lower().strip()
    if not name_l or len(name_l) < 2:
        return False
    for i, msg in enumerate(history):
        if msg.get("role") != "user":
            continue
        if name_l not in msg.get("content", "").lower():
            continue
        for j in range(i - 1, -1, -1):
            prev = history[j]
            if prev.get("role") == "assistant":
                if "name" in prev.get("content", "").lower():
                    return True
                break
    return False


def _ai_asked_for_name(history: list) -> bool:
    return any(
        "name" in m.get("content", "").lower()
        for m in history
        if m.get("role") == "assistant"
    )


_PHONE_WORD_MAP = {
    'zero': '0', 'oh': '0',
    'one': '1', 'two': '2', 'three': '3',
    'four': '4', 'five': '5', 'six': '6',
    'seven': '7', 'eight': '8', 'nine': '9',
}


def _normalize_otp(raw: str) -> str:
    """Convert spoken OTP to a clean digit string.

    Handles: word digits ("three seven"), multipliers ("double seven" → "77"),
    hyphens, spaces. Returns digits only — caller validates length.
    """
    v = raw.lower().strip()
    # Expand multipliers before word→digit pass
    v = re.sub(r'\bdouble\s+(\w+)', lambda m: m.group(1) + ' ' + m.group(1), v)
    v = re.sub(r'\btriple\s+(\w+)', lambda m: ' '.join([m.group(1)] * 3), v)
    # Word-to-digit (reuse phone map — same vocabulary)
    for word, digit in _PHONE_WORD_MAP.items():
        v = re.sub(r'\b' + word + r'\b', digit, v)
    return re.sub(r'[^\d]', '', v)


def _normalize_txn_id(raw: str) -> str:
    """Normalize spoken/typed transaction ID to TXN-XXXX format.

    Handles: "1100", "TXN1100", "txn-1100", "TXN 1100", "T X N 1100", etc.
    Strips everything except the trailing digits and prefixes with "TXN-".
    """
    v = raw.strip().upper()
    # Remove any existing TXN prefix (with or without separator)
    v = re.sub(r'^T[\s\-_]?X[\s\-_]?N[\s\-_]?', '', v)
    # Keep only the digits
    digits = re.sub(r'[^\d]', '', v)
    if digits:
        return f"TXN-{digits}"
    return raw.upper()


def _normalize_phone(raw: str) -> str:
    """Convert spoken/written phone number to digit string with optional + prefix.

    Handles: word digits ("one two three"), multipliers ("double five", "triple six"),
    spoken country codes ("plus one"), and standard formatted strings.
    """
    v = raw.lower().strip()

    # Spoken "plus" prefix → "+"
    v = re.sub(r'^plus\s*', '+', v)

    # Expand multipliers before word→digit conversion
    v = re.sub(r'\bdouble\s+(\w+)', lambda m: m.group(1) + ' ' + m.group(1), v)
    v = re.sub(r'\btriple\s+(\w+)', lambda m: ' '.join([m.group(1)] * 3), v)

    # Word-to-digit conversion
    for word, digit in _PHONE_WORD_MAP.items():
        v = re.sub(r'\b' + word + r'\b', digit, v)

    # Preserve leading +, strip everything else non-digit
    has_plus = v.startswith('+')
    digits = re.sub(r'[^\d]', '', v)

    if has_plus:
        return '+' + digits
    if len(digits) >= 10:
        return '+' + digits
    return digits


def make_agent_tools(call_id: str, session, publish_event) -> list:
    """Return function_tool list for this call based on the active tenant config."""
    try:
        cfg = get_config()
        enabled: set[str] = {
            name for name, tcfg in cfg.tool_configs.items()
            if tcfg.get("enabled", True)
        }
    except Exception:
        # Fallback: no tools except escalation
        enabled = {"escalate_to_human"}

    tools: list = []

    # One WorkflowRunner per call — all tool closures below share it.
    # Records every (step, result_key) pair in session.workflow.steps_taken
    # so the full resolution path is auditable after the call.
    from workflow.engine import WorkflowRunner
    runner = WorkflowRunner(session)

    # ── capture_lead ─────────────────────────────────────────────────────────
    if "capture_lead" in enabled:
        @function_tool
        async def capture_lead(
            name: str,
            email: str,
            company: str | None = None,
            intent: str = "general_inquiry",
        ) -> str:
            """Save visitor name and email."""
            if session.confirmed_name:
                name = session.confirmed_name
            if session.confirmed_email:
                email = session.confirmed_email

            if _is_placeholder(name):
                return "I need the visitor's real name. Please ask them: 'What's your name?'"

            if not session.confirmed_name and not _name_is_confirmed(name, session.conversation_history):
                return "Please ask the visitor their name first: 'What's your name?'"

            email = _normalize_email(email)
            if _is_placeholder(email) or not _is_valid_email(email):
                return "I need a real email address with @. Please ask the visitor for their email."

            result = await execute_with_recovery(
                tool_name="capture_lead",
                args={"name": name, "email": email, "company": company or "",
                      "intent": intent, "call_id": call_id},
                call_id=call_id,
                turn_id=session.turn_count,
                step_id="capture_lead",
                session=session,
            )
            if result.success and result.data.get("lead_id"):
                session.lead_id = result.data["lead_id"]
                session.confirmed_name = name
                session.confirmed_email = email

            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "capture_lead",
                "status": "done", "result": {"success": result.success},
            }))
            return "Contact info saved." if result.success else "Unable to save info right now."

        tools.append(capture_lead)

    # ── schedule_demo ─────────────────────────────────────────────────────────
    if "schedule_demo" in enabled:
        @function_tool
        async def schedule_demo(
            name: str,
            email: str,
            preferred_time: str,
            confirm_pending: bool = False,
        ) -> str:
            """Book a Wavvy demo. preferred_time: specific day + hour e.g. 'Thursday 2pm'. Set confirm_pending=True only when visitor says yes to a suggested alternative slot."""
            effective_name  = session.confirmed_name  or name
            effective_email = session.confirmed_email or email

            if _is_placeholder(effective_name):
                return "I need the visitor's real name before booking. Ask them: 'What's your name?'"

            if not session.confirmed_name and not _name_is_confirmed(effective_name, session.conversation_history):
                return "Please ask the visitor their name first: 'What's your name?'"

            effective_email = _normalize_email(effective_email)
            if _is_placeholder(effective_email) or not _is_valid_email(effective_email):
                return "I need a real email address before booking. Ask the visitor: 'What's your email address?'"

            if not confirm_pending and _is_placeholder(preferred_time):
                return "I need a specific time before booking. Ask: 'We're available Monday to Friday, 9am to 5pm IST. What day and time works for you?'"

            args = {
                "name": effective_name, "email": effective_email,
                "preferred_time": preferred_time, "lead_id": session.lead_id,
                "call_id": call_id, "user_timezone": "Asia/Kolkata",
            }
            if confirm_pending and session.pending_slot:
                args["force_slot"] = session.pending_slot
                session.pending_slot = None
            else:
                session.pending_slot = None

            result = await execute_with_recovery(
                tool_name="schedule_demo", args=args, call_id=call_id,
                turn_id=session.turn_count, step_id="schedule_demo", session=session,
            )
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "schedule_demo",
                "status": "done", "result": result.data,
            }))

            if result.data.get("needs_clarification"):
                return "That time isn't specific enough. Ask: 'We're available Monday to Friday, 9am to 5pm IST. What day and time works for you?'"
            if result.data.get("needs_confirmation"):
                session.pending_slot = result.data.get("pending_slot")
                tv = result.template_vars or {}
                slot_short = tv.get("slot_label") or preferred_time
                return f"That slot is taken. The next available time is {slot_short}. Does that work for you?"
            if result.success:
                tv = result.template_vars or {}
                slot = tv.get("slot_label") or preferred_time
                return f"Demo booked for {slot}. Confirmation sent to {effective_email}."
            return "Unable to schedule that slot. Would you like to try a different time?"

        tools.append(schedule_demo)

    # ── verify_account ────────────────────────────────────────────────────────
    if "verify_account" in enabled:
        @function_tool
        async def verify_account(phone: str) -> str:
            """Verify the caller's identity by phone number.
            phone: pass exactly what the customer said — digits only, no formatting.
            Example: customer says '9 8 7 6 5 4 3 2 1 0', pass '9876543210'.
            Include country code if spoken (e.g. '+91' prefix is fine)."""
            if getattr(session, 'verify_account_attempts', 0) >= 3:
                return runner.advance("verify_account", "not_found_max").message
            from tools.wavvy_tools import verify_account as _verify
            normalized = _normalize_phone(phone)
            # Guard against partial utterances: require at least 9 digits.
            # The suffix-match in the DB handles 10-digit numbers without country code.
            # The LLM sometimes fires on streaming partials — block those short calls.
            digits_only = re.sub(r'[^\d]', '', normalized)
            if len(digits_only) < 9:
                return (
                    "I didn't catch the full number. Please say your 10-digit mobile number "
                    "one digit at a time — for example: nine, eight, one, two, three…"
                )
            result = await _verify(normalized or phone, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "verify_account",
                "status": "done", "result": {"success": result.get("success")},
            }))
            if result.get("success"):
                name = result.get("first_name", "there")
                acct = result.get("account_type", "standard")
                session.confirmed_name = name
                profile = getattr(session, "customer_profile", {}) or {}

                # Build a grounded context summary from the eagerly-loaded data
                hints: list[str] = []
                txn_count = len(profile.get("transactions") or [])
                if txn_count:
                    hints.append(
                        f"{txn_count} transaction{'s' if txn_count != 1 else ''} on file"
                    )
                else:
                    hints.append("no transactions on file")

                holds = profile.get("account_holds") or []
                if holds:
                    hold_types = ", ".join(h.get("hold_type", "?") for h in holds)
                    hints.append(
                        f"{len(holds)} active hold{'s' if len(holds) != 1 else ''} "
                        f"({hold_types}) — use get_account_holds for details"
                    )

                refunds = profile.get("open_refunds") or []
                if refunds:
                    hints.append(
                        f"{len(refunds)} in-progress refund{'s' if len(refunds) != 1 else ''} "
                        f"— use get_refund_status"
                    )

                disputes = profile.get("open_disputes") or []
                if disputes:
                    hints.append(
                        f"{len(disputes)} open dispute{'s' if len(disputes) != 1 else ''} "
                        f"— use get_dispute_status"
                    )

                fraud_cases = profile.get("active_fraud_cases") or []
                if fraud_cases:
                    case_refs = ", ".join(fc["fraud_number"] for fc in fraud_cases)
                    hints.append(
                        f"{len(fraud_cases)} fraud case{'s' if len(fraud_cases) != 1 else ''} under review: "
                        f"{case_refs} — read this reference number to the customer immediately, do NOT call any tool"
                    )

                account_status = profile.get("account_status", "active")
                kyc_status = profile.get("kyc_status", "pending")
                status_note = ""
                if account_status != "active":
                    status_note = f" Account status: {account_status}."
                if kyc_status != "verified":
                    status_note += f" KYC status: {kyc_status}."

                context_line = " | ".join(hints)

                from session.conversation_state import ConversationStage
                from session.call_session import get_session as _get_session
                _s = _get_session(call_id)
                if _s:
                    if _s.conv_state.stage == ConversationStage.GREETING:
                        _s.conv_state.transition_to(ConversationStage.DISCOVERY)
                    ok = _s.conv_state.transition_to(ConversationStage.VERIFICATION)
                    logger.info(
                        "[%s] verify_account: VERIFICATION transition=%s stage=%s",
                        call_id, ok, _s.conv_state.stage.value,
                    )
                return (
                    f"Verified: {name} ({acct}).{status_note} "
                    f"{context_line}. "
                    f"Ask what you can help with — do not search transactions yet."
                )
            effective_key = "not_found_max" if result.get("attempts", 0) >= 2 else "not_found_1"
            return runner.advance("verify_account", effective_key).message

        tools.append(verify_account)

    # ── lookup_transaction ────────────────────────────────────────────────────
    if "lookup_transaction" in enabled:
        @function_tool
        async def lookup_transaction(transaction_id: str) -> str:
            """Look up a transaction by ID (format: TXN-XXXX). Requires verify_account first."""
            from tools.wavvy_tools import lookup_transaction as _lookup
            normalized_txn = _normalize_txn_id(transaction_id)
            result = await _lookup(normalized_txn, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "lookup_transaction",
                "status": "done", "result": {"found": result.get("found")},
            }))
            if result.get("fast_response_key") == "verification_required":
                return "I need to verify the customer's identity first. Please call verify_account."
            if not result.get("found"):
                return runner.advance("lookup_transaction", "not_found").message
            # Route through runner based on transaction status
            status = result.get("status", "")
            status_key = f"status_{status}" if status else None
            if status_key and status_key in (
                "status_pending", "status_processing",
                "status_failed", "status_completed", "status_cancelled", "status_expired",
                "status_refund_initiated", "status_refund_processing", "status_refund_completed",
                "status_flagged", "status_kyc_hold", "status_compliance_hold",
                "status_disputed", "status_chargeback_initiated",
                "status_chargeback_won", "status_chargeback_lost",
                "status_fraud_reported", "status_fraud_confirmed", "status_fraud_reversed",
            ):
                return runner.advance("lookup_transaction", status_key).message
            # Unrecognised status — surface raw info
            return (
                f"Transaction {normalized_txn}: "
                f"{result.get('merchant', 'unknown merchant')}, "
                f"amount {result.get('amount')}, status is {status or 'unknown'}."
            )

        tools.append(lookup_transaction)

    # ── search_transactions ───────────────────────────────────────────────────
    # Enabled whenever lookup_transaction is — same auth tier, same data source.
    if "lookup_transaction" in enabled:
        @function_tool
        async def search_transactions(query: str) -> str:
            """Search the customer's transactions from session cache by merchant, amount, status, or date.
            Use when customer describes a transaction without knowing the exact ID.
            query: free-text keyword, e.g. 'Swiggy', 'failed', '450', '2026-05-26'."""
            if not session.customer_id:
                return "Account not verified yet. Call verify_account first."
            profile = getattr(session, "customer_profile", None) or {}
            txns = profile.get("transactions") or []
            if not txns:
                return "No transactions found on this account."

            tokens = [tok for tok in query.lower().strip().split() if len(tok) >= 2]
            if not tokens:
                tokens = [query.lower().strip()]

            def _amounts_match(query_tok: str, txn_amount) -> bool:
                """STT often formats '450 rupees' as '4.50' — check rounded variants."""
                try:
                    q = float(query_tok.replace(',', ''))
                    a = float(str(txn_amount))
                    # Direct match OR ×100 match (4.50 ↔ 450)
                    return abs(q - a) < 0.5 or abs(q * 100 - a) < 0.5 or abs(q - a * 100) < 0.5
                except (ValueError, TypeError):
                    return False

            def _txn_matches(t: dict) -> bool:
                haystack = " ".join([
                    str(t.get("merchant", "")),
                    str(t.get("amount", "")),
                    str(t.get("status", "")),
                    str(t.get("txn_date", "")),
                    str(t.get("txn_number", "")),
                    str(t.get("txn_type", "")),
                ]).lower()
                if any(tok in haystack for tok in tokens):
                    return True
                # Amount-specific fuzzy match for STT decimal misparse (₹450 → 4.50)
                return any(_amounts_match(tok, t.get("amount")) for tok in tokens)

            matches = [t for t in txns if _txn_matches(t)]
            if not matches:
                # Semantically related: if query implies failure/refund/dispute,
                # surface transactions with adjacent statuses so the LLM can map
                # the customer's description to the right transaction.
                FAILURE_ADJACENT = {"refund_initiated", "refund_processing", "disputed",
                                     "flagged", "fraud_reported", "fraud_confirmed",
                                     "kyc_hold", "compliance_hold"}
                FAILURE_QUERY_TERMS = {"fail", "failed", "failure", "refund", "dispute",
                                       "fraud", "stuck", "pending", "not", "issue"}
                is_failure_query = any(t in FAILURE_QUERY_TERMS for t in tokens)
                related = [t for t in txns if t.get("status", "") in FAILURE_ADJACENT] if is_failure_query else []
                if related:
                    lines = [
                        f"{t.get('txn_number')}: {t.get('merchant','?')}, "
                        f"₹{t.get('amount','?')}, status={t.get('status','?')}"
                        for t in related
                    ]
                    return f"No exact match. Related: " + " | ".join(lines)
                all_ids = ", ".join(str(t.get("txn_number")) for t in txns)
                return f"No match for '{query}'. IDs on file: {all_ids}"
            lines = [
                f"{t.get('txn_number')}: {t.get('merchant','?')}, ₹{t.get('amount','?')}, "
                f"status={t.get('status','?')}, date={t.get('txn_date','?')}"
                for t in matches
            ]
            return f"Found: " + " | ".join(lines)

        tools.append(search_transactions)

    # ── send_otp ──────────────────────────────────────────────────────────────
    if "send_otp" in enabled:
        @function_tool
        async def send_otp() -> str:
            """Send a one-time password to the customer's registered contact for stronger verification. Call after verify_account when an account action (unlock, refund) is needed."""
            if session.escalated:
                return (
                    "A transfer to a specialist is already in progress. "
                    "Tell the customer: 'I've already connected you with our specialist — "
                    "they'll handle this for you directly. No need to re-verify.'"
                )
            from tools.wavvy_tools import send_otp as _send
            result = await _send(call_id)
            key = result.get("fast_response_key")
            if key in ("otp_cooldown", "otp_resend_limit"):
                return runner.advance("send_otp", key).message
            if result.get("success"):
                otp_val = result["otp"]
                await publish_event({"type": "otp_sent", "otp": otp_val})
                await publish_event({
                    "type": "tool_call", "tool": "send_otp",
                    "status": "done", "result": {"otp_sent": True},
                })
                # Forward to agent console so it shows in the HITL activity timeline
                asyncio.create_task(_notify_fastapi(call_id, "otp_sent", {"otp": otp_val}))
                logger.info("[%s] otp_sent event published", call_id)
                return "OTP sent to your registered phone and email. Please share the 6-digit code."
            return "Unable to send OTP right now. Please try again in a moment."

        tools.append(send_otp)

    # ── verify_otp ────────────────────────────────────────────────────────────
    if "verify_otp" in enabled:
        @function_tool
        async def verify_otp(otp_code: str) -> str:
            """Verify the 6-digit OTP the customer provides. otp_code: the digits the customer spoke or typed."""
            from tools.wavvy_tools import verify_otp as _verify

            # Normalize spoken patterns ("double seven" → "77", "three" → "3", etc.)
            normalized = _normalize_otp(otp_code)
            if len(normalized) != 6:
                return (
                    f"I need exactly 6 digits. I heard '{otp_code}' but got {len(normalized)} digit{'s' if len(normalized) != 1 else ''}. "
                    "Ask the customer to say each digit separately — for example: three, seven, seven, three, six, zero."
                )

            result = await _verify(normalized, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "verify_otp",
                "status": "done", "result": {"success": result.get("success")},
            }))
            if result.get("success"):
                from session.conversation_state import ConversationStage
                from session.call_session import get_session as _get_session
                _s = _get_session(call_id)
                if _s:
                    ok = _s.conv_state.transition_to(ConversationStage.TOOL_EXECUTION)
                    logger.info(
                        "[%s] verify_otp: TOOL_EXECUTION transition=%s stage=%s",
                        call_id, ok, _s.conv_state.stage.value,
                    )
                return (
                    "OTP verified. Customer identity confirmed. "
                    "Proceed with the action the customer originally requested — "
                    "call the appropriate tool immediately without speaking first."
                )
            key = result.get("fast_response_key")
            if key == "no_otp_pending":
                return "No OTP has been sent yet. Call send_otp first."
            if key in ("otp_expired", "otp_max_attempts"):
                return runner.advance("verify_otp", key).message
            if key == "otp_wrong":
                remaining = result.get("attempts_remaining", 0)
                plural = "attempts" if remaining != 1 else "attempt"
                runner.advance("verify_otp", key, extras={"attempts_remaining": remaining})
                return f"That code doesn't match. You have {remaining} {plural} remaining."
            return "That OTP doesn't match. Please check the code and try again, or ask me to resend it."

        tools.append(verify_otp)

    # ── unlock_account ────────────────────────────────────────────────────────
    if "unlock_account" in enabled:
        @function_tool
        async def unlock_account() -> str:
            """Unlock the customer's account. Requires verify_account + verify_otp to have succeeded first."""
            from tools.wavvy_tools import unlock_account as _unlock
            result = await _unlock(call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "unlock_account",
                "status": "done", "result": {"success": result.get("success")},
            }))
            if result.get("success"):
                return "Account unlocked successfully. The customer should now be able to log in."
            if result.get("fast_response_key") == "verification_required":
                return "Cannot unlock — OTP verification required first. Please call send_otp and verify_otp."
            return "Unable to unlock account right now. Escalating to a specialist."

        tools.append(unlock_account)

    # ── initiate_refund ───────────────────────────────────────────────────────
    if "initiate_refund" in enabled:
        @function_tool
        async def initiate_refund(transaction_id: str) -> str:
            """Initiate a refund for a failed transaction. Requires verify_account + verify_otp. transaction_id: format TXN-XXXX."""
            from tools.wavvy_tools import initiate_refund as _refund
            result = await _refund(transaction_id.upper(), call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "initiate_refund",
                "status": "done", "result": {"success": result.get("success")},
            }))
            if result.get("success"):
                rfn = result.get("rfn_number", "")
                rfn_part = f" Your reference number is {rfn}." if rfn else ""
                return f"Refund initiated for {transaction_id}.{rfn_part} Funds will appear within 3 to 5 business days."
            key = result.get("fast_response_key")
            if key == "verification_required":
                return "Cannot initiate refund — OTP verification required first."
            if key == "transaction_not_found":
                return f"Transaction {transaction_id} not found on this account. Please confirm the ID."
            if key in ("refund_already_initiated", "refund_already_completed",
                       "refund_ineligible", "fraud_review_required",
                       "kyc_escalation_required", "session_duplicate"):
                return runner.advance("initiate_refund", key).message
            return "Unable to initiate refund right now. Let me connect you with a specialist."

        tools.append(initiate_refund)

    # ── raise_dispute ─────────────────────────────────────────────────────────
    if "raise_dispute" in enabled:
        @function_tool
        async def raise_dispute(
            transaction_id: str,
            reason: str = "unrecognised_transaction",
        ) -> str:
            """File a dispute for a completed transaction the customer doesn't recognise or received no service for. Requires verify_account + verify_otp. reason: e.g. 'no_service_received', 'unrecognised_transaction', 'wrong_amount'."""
            from tools.wavvy_tools import raise_dispute as _dispute
            normalized_txn = _normalize_txn_id(transaction_id)
            result = await _dispute(normalized_txn, reason, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "raise_dispute",
                "status": "done", "result": {"success": result.get("success")},
            }))
            if result.get("success"):
                ref = result.get("dsp_number", "")
                ref_part = f" Your reference number is {ref}." if ref else ""
                return f"Dispute filed for {normalized_txn}.{ref_part} Our disputes team will review within 5–7 business days."
            key = result.get("fast_response_key")
            if key == "verification_required":
                return "Cannot file dispute — OTP verification required first. Call send_otp then verify_otp."
            if key == "transaction_not_found":
                return f"Transaction {normalized_txn} not found. Please confirm the ID."
            if key in ("dispute_duplicate", "dispute_window_expired", "dispute_ineligible",
                       "high_value_manual_required", "fraud_review_required",
                       "refund_already_initiated", "refund_already_completed"):
                return runner.advance("raise_dispute", key).message
            return "Unable to file dispute right now. Let me connect you with our disputes team."

        tools.append(raise_dispute)

    # ── report_fraud ──────────────────────────────────────────────────────────
    if "report_fraud" in enabled:
        @function_tool
        async def report_fraud(
            transaction_id: str,
            fraud_type: str = "unauthorized_transaction",
        ) -> str:
            """Report an unauthorised transaction as fraud. Requires verify_account + verify_otp. fraud_type: 'unauthorized_transaction', 'phishing', 'lost_stolen_card', 'account_takeover'."""
            from tools.wavvy_tools import report_fraud as _fraud
            normalized_txn = _normalize_txn_id(transaction_id)
            result = await _fraud(normalized_txn, fraud_type, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "report_fraud",
                "status": "done", "result": {"success": result.get("success")},
            }))
            if result.get("success"):
                ref = result.get("fraud_number", "")
                ref_part = f" Your reference number is {ref}." if ref else ""
                return f"Fraud report filed for {normalized_txn}.{ref_part} Our fraud team will review within 24 hours."
            key = result.get("fast_response_key")
            if key == "verification_required":
                return "Cannot file fraud report — OTP verification required first."
            if key in ("fraud_already_reported", "fraud_transaction_reversed", "transaction_not_found"):
                return runner.advance("report_fraud", key).message
            return "Unable to file fraud report right now. Let me connect you with our fraud team."

        tools.append(report_fraud)

    # ── check_payment_status ──────────────────────────────────────────────────
    if "check_payment_status" in enabled:
        @function_tool
        async def check_payment_status(transaction_id: str) -> str:
            """Check detailed payment status with SLA context. Use when customer says payment is stuck, pending too long, or money not credited. Requires verify_account."""
            from tools.wavvy_tools import check_payment_status as _status
            normalized_txn = _normalize_txn_id(transaction_id)
            result = await _status(normalized_txn, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "check_payment_status",
                "status": "done", "result": {"status": result.get("status")},
            }))
            key = result.get("fast_response_key")
            if key == "verification_required":
                return "Cannot check payment status — verify_account required first."
            if key == "transaction_not_found":
                return f"Transaction {normalized_txn} not found. Please confirm the ID."
            if key in ("payment_processing", "payment_processing_delayed",
                       "payment_settled", "payment_failed_post_debit",
                       "payment_returned", "gateway_error"):
                return runner.advance("check_payment_status", key).message
            return f"Payment status for {normalized_txn}: {result.get('status', 'unknown')}."

        tools.append(check_payment_status)

    # ── get_account_holds ─────────────────────────────────────────────────────
    if "get_account_holds" in enabled:
        @function_tool
        async def get_account_holds() -> str:
            """Check why the customer's account has a hold or restriction. Returns hold type and reason from verified session data. Call when customer asks why their account is locked, frozen, or restricted."""
            if not session.customer_id:
                return "Account not verified yet. Call verify_account first."
            from tools.wavvy_tools import get_account_holds as _holds
            result = await _holds(call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "get_account_holds",
                "status": "done", "result": {"count": result.get("count", 0)},
            }))
            if result.get("fast_response_key") == "verification_required":
                return "Account not verified yet. Call verify_account first."
            holds = result.get("holds") or []
            if not holds:
                return "No active holds on this account."
            lines = [
                f"{h.get('hold_type', 'unknown')} hold"
                + (f": {h['reason']}" if h.get("reason") else "")
                for h in holds
            ]
            return f"Active account hold{'s' if len(lines) != 1 else ''}: {'; '.join(lines)}."

        tools.append(get_account_holds)

    # ── get_refund_status ─────────────────────────────────────────────────────
    if "get_refund_status" in enabled:
        @function_tool
        async def get_refund_status(transaction_id: str | None = None) -> str:
            """Check the status of an existing refund. Returns RFN reference, current status and expected timeline. Call when customer asks about a refund they've already initiated. transaction_id: optional TXN-XXXX to filter by specific transaction."""
            if not session.customer_id:
                return "Account not verified yet. Call verify_account first."
            from tools.wavvy_tools import get_refund_status as _refund_status
            result = await _refund_status(transaction_id, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "get_refund_status",
                "status": "done", "result": {"count": result.get("count", 0)},
            }))
            if result.get("fast_response_key") == "verification_required":
                return "Account not verified yet. Call verify_account first."
            refunds = result.get("refunds") or []
            if not refunds:
                msg = "No in-progress refunds"
                if transaction_id:
                    msg += f" for {transaction_id.upper()}"
                return msg + "."
            lines = [
                f"{r.get('rfn_number','?')} for {r.get('merchant','?')} "
                f"₹{r.get('amount','?')} — status: {r.get('status','?')}"
                for r in refunds
            ]
            return (
                f"Refund{'s' if len(lines) != 1 else ''} in progress: "
                + "; ".join(lines)
                + ". Refunds typically arrive within 3–5 business days of initiation."
            )

        tools.append(get_refund_status)

    # ── get_dispute_status ────────────────────────────────────────────────────
    if "get_dispute_status" in enabled:
        @function_tool
        async def get_dispute_status(transaction_id: str | None = None) -> str:
            """Check the status of an open dispute. Returns DSP reference, current status and next steps. Call when customer asks about a dispute they've filed. transaction_id: optional TXN-XXXX to filter by specific transaction."""
            if not session.customer_id:
                return "Account not verified yet. Call verify_account first."
            from tools.wavvy_tools import get_dispute_status as _dispute_status
            result = await _dispute_status(transaction_id, call_id)
            asyncio.create_task(publish_event({
                "type": "tool_call", "tool": "get_dispute_status",
                "status": "done", "result": {"count": result.get("count", 0)},
            }))
            if result.get("fast_response_key") == "verification_required":
                return "Account not verified yet. Call verify_account first."
            disputes = result.get("disputes") or []
            if not disputes:
                msg = "No open disputes"
                if transaction_id:
                    msg += f" for {transaction_id.upper()}"
                return msg + "."
            lines = [
                f"{d.get('dsp_number','?')} for {d.get('merchant','?')} "
                f"₹{d.get('amount','?')} — reason: {d.get('reason','?')}, status: {d.get('status','?')}"
                for d in disputes
            ]
            return (
                f"Open dispute{'s' if len(lines) != 1 else ''}: "
                + "; ".join(lines)
                + ". Our disputes team reviews within 5–7 business days."
            )

        tools.append(get_dispute_status)

    # ── escalate_to_human ─────────────────────────────────────────────────────
    # Always available regardless of config.
    @function_tool
    async def escalate_to_human(reason: str = "customer_request") -> str:
        """Transfer the caller to a human support agent. Only call this when the customer has explicitly asked to speak with a human in this turn AND you have confirmed their permission. Never call this to avoid doing a support task — always try send_otp → verify_otp → the action tool first."""
        if session.escalated:
            return "Already transferring to a human agent."

        # For Fin (verify_account flow): no name required before escalation.
        # For Wavvy (capture_lead flow): require name first.
        if "capture_lead" in enabled:
            if not session.confirmed_name and not _ai_asked_for_name(session.conversation_history):
                return "Please ask the visitor their name first before transferring: 'What's your name?'"

        async def _check_availability() -> dict:
            try:
                async with httpx.AsyncClient(timeout=3.0) as _c:
                    _r = await _c.get(f"{settings.backend_internal_url}/api/agents/availability")
                    return _r.json() if _r.status_code == 200 else {}
            except Exception:
                return {"available": True}

        _avail = await _check_availability()
        if not _avail.get("available", True):
            # Retry once after 700ms — handles the reconnect window after backend reload
            # (agent desktop reconnects after ~1s backoff; first check may land during the gap)
            await asyncio.sleep(0.7)
            _avail = await _check_availability()

        if not _avail.get("available", True):
            return (
                "I'm sorry, all our specialists are currently busy. "
                "I'm right here to keep helping you — what would you like to do?"
            )

        parts = []
        for m in session.conversation_history[-6:]:
            role = "Customer" if m.get("role") == "user" else "Agent"
            parts.append(f"{role}: {m.get('content', '')[:120]}")
        summary = " | ".join(parts) or "support inquiry"

        result = await execute_with_recovery(
            tool_name="escalate_to_human",
            args={"reason": reason, "transcript_summary": summary, "call_id": call_id},
            call_id=call_id,
            turn_id=session.turn_count,
            step_id="escalate",
            session=session,
        )
        if result.success:
            session.escalated = True
            session.conv_state.mark_escalated()
            handoff = result.data.get("handoff_bundle", {})
            session.handoff_bundle = handoff
            esc_room_name      = result.data.get("esc_room_name")
            customer_esc_token = result.data.get("customer_esc_token")
            agent_esc_token    = result.data.get("agent_esc_token")
            livekit_url        = result.data.get("livekit_url", settings.livekit_url)
            if esc_room_name:
                session.esc_room_name   = esc_room_name
            if agent_esc_token:
                session.agent_esc_token = agent_esc_token
            asyncio.create_task(publish_event({
                "type": "escalation",
                "handoff_bundle": handoff,
                "esc_room_name": esc_room_name,
                "customer_esc_token": customer_esc_token,
                "livekit_url": livekit_url,
            }))
            asyncio.create_task(_notify_fastapi(call_id, "escalation", {
                "handoff_bundle": handoff,
                "conversation_history": session.conversation_history,
                "agent_esc_token": agent_esc_token,
                "esc_room_name": esc_room_name,
                "livekit_url": livekit_url,
                "customer_id": session.customer_id,
            }))
            return "Transferring you to a support specialist now."

        # Blocked escalation — surface the exact guidance returned by the tool
        # instead of a generic "unable to connect" message.
        say_this = (result.data or {}).get("say_this")
        if say_this:
            return say_this
        return "Unable to connect right now. Please try again in a moment."

    tools.append(escalate_to_human)

    # ── cancel_escalation ─────────────────────────────────────────────────────
    @function_tool
    async def cancel_escalation() -> str:
        """Revert to AI when caller explicitly asks to stay with AI before a human joins."""
        if not session.escalated:
            return "I'm already here with you!"
        if session.human_joined:
            return "A human agent has already joined — I can't take back over right now."
        session.escalated = False
        asyncio.create_task(publish_event({"type": "escalation_cancelled"}))
        return "I'm back! Happy to keep helping you."

    tools.append(cancel_escalation)

    logger.info("[%s] tools registered: %s", call_id, [t.info.name for t in tools])
    return tools


async def _notify_fastapi(call_id: str, event_type: str, data: dict) -> None:
    url = f"{settings.backend_internal_url}/api/internal/worker-event"
    payload = {"call_id": call_id, "event_type": event_type, "data": data}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning("[%s] worker→fastapi notify failed (%s): %s", call_id, event_type, exc)
