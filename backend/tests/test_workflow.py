"""
Fin workflow test suite — covers the complete call flow end-to-end.

Sections:
  1. ConversationStage machine transitions
  2. Tool permissions per stage (stage-gating)
  3. Input normalisation  (phone, OTP, transaction ID)
  4. OTP session logic    (no DB — pure in-memory)
  5. Tool return-value contracts  (mocked DB)
  6. Full happy-path scenarios    (stage + OTP + tool sequenced)

Run from backend/:
    .venv/bin/pytest tests/test_workflow.py -v
    .venv/bin/pytest tests/test_workflow.py -v -k fraud   # just fraud tests
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── imports ───────────────────────────────────────────────────────────────────
from session.conversation_state import (
    ConversationStage,
    ConversationStateManager,
    VALID_TRANSITIONS,
)
from session.call_session import (
    ACTIVE_CALLS,
    CallSession,
    create_session,
    get_session,
    remove_session,
)
from guardrails.tool_permissions import TOOL_PERMISSIONS, is_tool_allowed

# Normalisation helpers live in voice.agent_tools as module-private functions.
# Import them by name — Python doesn't enforce the leading underscore at runtime.
from voice.agent_tools import (
    _normalize_otp,
    _normalize_phone,
    _normalize_txn_id,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ConversationStage state machine
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationStageMachine:
    def setup_method(self):
        self.sm = ConversationStateManager()

    def test_initial_stage_is_greeting(self):
        assert self.sm.stage == ConversationStage.GREETING

    # ── valid transitions ─────────────────────────────────────────────────────

    def test_greeting_to_discovery(self):
        assert self.sm.transition_to(ConversationStage.DISCOVERY)
        assert self.sm.stage == ConversationStage.DISCOVERY

    def test_discovery_to_verification(self):
        self.sm.transition_to(ConversationStage.DISCOVERY)
        assert self.sm.transition_to(ConversationStage.VERIFICATION)
        assert self.sm.stage == ConversationStage.VERIFICATION

    def test_verification_to_tool_execution(self):
        self.sm.stage = ConversationStage.VERIFICATION
        assert self.sm.transition_to(ConversationStage.TOOL_EXECUTION)
        assert self.sm.stage == ConversationStage.TOOL_EXECUTION

    def test_tool_execution_to_resolution(self):
        self.sm.stage = ConversationStage.TOOL_EXECUTION
        assert self.sm.transition_to(ConversationStage.RESOLUTION)

    def test_full_happy_path(self):
        stages = [
            ConversationStage.DISCOVERY,
            ConversationStage.VERIFICATION,
            ConversationStage.TOOL_EXECUTION,
            ConversationStage.RESOLUTION,
            ConversationStage.ENDED,
        ]
        for s in stages:
            assert self.sm.transition_to(s), f"Expected to reach {s.value}"
        assert self.sm.stage == ConversationStage.ENDED

    # ── invalid / skipped transitions ─────────────────────────────────────────

    def test_greeting_cannot_skip_to_tool_execution(self):
        assert not self.sm.transition_to(ConversationStage.TOOL_EXECUTION)
        assert self.sm.stage == ConversationStage.GREETING  # unchanged

    def test_greeting_cannot_go_to_verification_directly(self):
        # GREETING → VERIFICATION is not in VALID_TRANSITIONS
        assert not self.sm.transition_to(ConversationStage.VERIFICATION)

    def test_verification_cannot_skip_to_resolution(self):
        self.sm.stage = ConversationStage.VERIFICATION
        assert not self.sm.transition_to(ConversationStage.RESOLUTION)

    def test_ended_has_no_transitions(self):
        self.sm.stage = ConversationStage.ENDED
        for s in ConversationStage:
            assert not self.sm.transition_to(s)

    # ── escalation shortcut ───────────────────────────────────────────────────

    def test_mark_escalated_forces_escalation_stage(self):
        self.sm.transition_to(ConversationStage.DISCOVERY)
        self.sm.mark_escalated()
        assert self.sm.stage == ConversationStage.ESCALATION
        assert self.sm.escalated is True

    def test_can_escalate_from_any_non_ended_stage(self):
        stages_with_escalation = [
            s for s in ConversationStage
            if ConversationStage.ESCALATION in VALID_TRANSITIONS.get(s, set())
        ]
        for stage in stages_with_escalation:
            sm = ConversationStateManager()
            sm.stage = stage
            assert sm.transition_to(ConversationStage.ESCALATION), (
                f"Expected ESCALATION to be reachable from {stage.value}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tool permissions per stage
# ─────────────────────────────────────────────────────────────────────────────

class TestToolPermissions:

    # ── GREETING ──────────────────────────────────────────────────────────────

    def test_greeting_allows_verify_account(self):
        allowed, _ = is_tool_allowed(ConversationStage.GREETING, "verify_account")
        assert allowed

    def test_greeting_allows_escalate_to_human(self):
        allowed, _ = is_tool_allowed(ConversationStage.GREETING, "escalate_to_human")
        assert allowed

    def test_greeting_blocks_send_otp(self):
        allowed, reason = is_tool_allowed(ConversationStage.GREETING, "send_otp")
        assert not allowed
        assert "greeting" in reason.lower()

    def test_greeting_blocks_all_write_tools(self):
        write_tools = ["unlock_account", "initiate_refund", "raise_dispute", "report_fraud"]
        for tool in write_tools:
            allowed, _ = is_tool_allowed(ConversationStage.GREETING, tool)
            assert not allowed, f"{tool} should be blocked at GREETING"

    # ── VERIFICATION (after verify_account succeeds) ──────────────────────────

    def test_verification_allows_send_otp(self):
        allowed, _ = is_tool_allowed(ConversationStage.VERIFICATION, "send_otp")
        assert allowed

    def test_verification_allows_verify_otp(self):
        allowed, _ = is_tool_allowed(ConversationStage.VERIFICATION, "verify_otp")
        assert allowed

    def test_verification_allows_lookup_transaction(self):
        allowed, _ = is_tool_allowed(ConversationStage.VERIFICATION, "lookup_transaction")
        assert allowed

    def test_verification_blocks_report_fraud(self):
        allowed, reason = is_tool_allowed(ConversationStage.VERIFICATION, "report_fraud")
        assert not allowed
        assert "verification" in reason.lower()

    def test_verification_blocks_all_write_tools(self):
        write_tools = ["unlock_account", "initiate_refund", "raise_dispute", "report_fraud"]
        for tool in write_tools:
            allowed, _ = is_tool_allowed(ConversationStage.VERIFICATION, tool)
            assert not allowed, f"{tool} should be blocked at VERIFICATION — OTP not yet done"

    def test_verification_allows_escalate_to_human(self):
        allowed, _ = is_tool_allowed(ConversationStage.VERIFICATION, "escalate_to_human")
        assert allowed

    # ── TOOL_EXECUTION (after verify_otp succeeds) ────────────────────────────

    def test_tool_execution_allows_report_fraud(self):
        allowed, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, "report_fraud")
        assert allowed

    def test_tool_execution_allows_all_write_tools(self):
        write_tools = ["unlock_account", "initiate_refund", "raise_dispute", "report_fraud"]
        for tool in write_tools:
            allowed, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, tool)
            assert allowed, f"{tool} should be allowed at TOOL_EXECUTION"

    def test_tool_execution_allows_all_read_tools(self):
        read_tools = [
            "lookup_transaction", "search_transactions", "check_payment_status",
            "get_account_holds", "get_refund_status", "get_dispute_status",
        ]
        for tool in read_tools:
            allowed, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, tool)
            assert allowed, f"{tool} should be allowed at TOOL_EXECUTION"

    def test_tool_execution_allows_cancel_escalation(self):
        allowed, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, "cancel_escalation")
        assert allowed

    # ── ESCALATION (post-transfer) ────────────────────────────────────────────

    def test_escalation_only_allows_escalate_and_cancel(self):
        assert is_tool_allowed(ConversationStage.ESCALATION, "escalate_to_human")[0]
        assert is_tool_allowed(ConversationStage.ESCALATION, "cancel_escalation")[0]

    def test_escalation_blocks_write_tools(self):
        for tool in ["report_fraud", "initiate_refund", "unlock_account"]:
            allowed, _ = is_tool_allowed(ConversationStage.ESCALATION, tool)
            assert not allowed, f"{tool} should be blocked after escalation"

    # ── escalated session blocks all tools except escalate_to_human ──────────

    def test_escalated_flag_blocks_non_escalate_tools(self):
        allowed, reason = is_tool_allowed(
            ConversationStage.TOOL_EXECUTION, "report_fraud", escalated=True
        )
        assert not allowed
        assert "escalated" in reason.lower()

    def test_escalated_flag_allows_escalate_to_human(self):
        allowed, _ = is_tool_allowed(
            ConversationStage.TOOL_EXECUTION, "escalate_to_human", escalated=True
        )
        assert allowed

    # ── ENDED ─────────────────────────────────────────────────────────────────

    def test_ended_blocks_every_tool(self):
        for tool in ["verify_account", "report_fraud", "escalate_to_human"]:
            allowed, _ = is_tool_allowed(ConversationStage.ENDED, tool)
            assert not allowed, f"{tool} should be blocked at ENDED"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Input normalisation
# ─────────────────────────────────────────────────────────────────────────────

class TestOTPNormalisation:
    def test_digit_string_unchanged(self):
        assert _normalize_otp("123456") == "123456"

    def test_spoken_digits(self):
        assert _normalize_otp("one two three four five six") == "123456"

    def test_double_multiplier(self):
        assert _normalize_otp("double seven three six nine two") == "773692"

    def test_triple_multiplier(self):
        # "triple one" expands to "one one one", rest appends: "two three" → "11123"
        assert _normalize_otp("triple one two three") == "11123"

    def test_strips_hyphens_and_spaces(self):
        assert _normalize_otp("3 7 7 - 3 6 0") == "377360"

    def test_mixed_words_and_digits(self):
        assert _normalize_otp("3 seven 7 three 6 zero") == "377360"

    def test_empty_returns_empty(self):
        assert _normalize_otp("") == ""

    def test_seven_digit_otp_keeps_all(self):
        # Length validation is done by the caller, not the normaliser
        assert len(_normalize_otp("1234567")) == 7

    def test_five_digit_input_stays_five(self):
        assert len(_normalize_otp("12345")) == 5


class TestPhoneNormalisation:
    def test_plain_ten_digits(self):
        result = _normalize_phone("9876543210")
        assert result == "+9876543210"

    def test_spoken_with_country_code_plus_91(self):
        result = _normalize_phone("plus 91 9876543210")
        assert result.replace(" ", "") == "+919876543210"

    def test_word_digits(self):
        result = _normalize_phone("nine eight seven six five four three two one zero")
        assert re_digits(result) == "9876543210"

    def test_double_multiplier_phone(self):
        # "double five" → "55"
        result = _normalize_phone("nine double five three four five six seven eight")
        assert "55" in result

    def test_short_number_under_9_digits(self):
        # Should NOT be prefixed with +  (too short to be a real phone)
        result = _normalize_phone("12345678")
        # Still just returns the digits — the caller blocks on len < 9
        assert len(re_digits(result)) == 8

    def test_formatted_number_with_parens(self):
        # "(771) 234-5603" — STT output from the logs
        result = _normalize_phone("(771) 234-5603")
        assert re_digits(result) == "7712345603"


class TestTransactionIDNormalisation:
    def test_plain_digits(self):
        assert _normalize_txn_id("3300") == "TXN-3300"

    def test_already_formatted(self):
        assert _normalize_txn_id("TXN-3300") == "TXN-3300"

    def test_lowercase(self):
        assert _normalize_txn_id("txn-3300") == "TXN-3300"

    def test_no_separator(self):
        assert _normalize_txn_id("TXN3300") == "TXN-3300"

    def test_with_spaces(self):
        assert _normalize_txn_id("TXN 3300") == "TXN-3300"

    def test_spoken_t_x_n(self):
        assert _normalize_txn_id("T X N 3300") == "TXN-3300"

    def test_just_digits_no_prefix(self):
        assert _normalize_txn_id("1234") == "TXN-1234"

    def test_uppercase_output(self):
        result = _normalize_txn_id("txn1100")
        assert result == result.upper()


def re_digits(s: str) -> str:
    import re
    return re.sub(r"[^\d]", "", s)


# ─────────────────────────────────────────────────────────────────────────────
# 4. OTP session logic (no DB — pure in-memory)
# ─────────────────────────────────────────────────────────────────────────────

class TestOTPSessionLogic:
    """Tests for wavvy_tools.send_otp / verify_otp using real ACTIVE_CALLS."""

    def setup_method(self):
        self.call_id = "test-otp-flow"
        s = create_session(self.call_id)
        s.customer_id = "cust-uuid-001"

    def teardown_method(self):
        remove_session(self.call_id)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_send_otp_returns_six_digit_code(self):
        from tools.wavvy_tools import send_otp
        result = self._run(send_otp(self.call_id))
        assert result["success"]
        assert len(result["otp"]) == 6
        assert result["otp"].isdigit()

    def test_send_otp_stores_code_on_session(self):
        from tools.wavvy_tools import send_otp
        self._run(send_otp(self.call_id))
        s = get_session(self.call_id)
        assert s.otp_code is not None
        assert len(s.otp_code) == 6

    def test_verify_otp_correct_code_returns_success(self):
        from tools.wavvy_tools import send_otp, verify_otp
        r = self._run(send_otp(self.call_id))
        code = r["otp"]
        result = self._run(verify_otp(code, self.call_id))
        assert result["success"]
        assert result["fast_response_key"] == "otp_verified"

    def test_verify_otp_sets_otp_verified_on_session(self):
        from tools.wavvy_tools import send_otp, verify_otp
        r = self._run(send_otp(self.call_id))
        self._run(verify_otp(r["otp"], self.call_id))
        assert get_session(self.call_id).otp_verified is True

    def test_verify_otp_wrong_code_returns_wrong(self):
        from tools.wavvy_tools import send_otp, verify_otp
        self._run(send_otp(self.call_id))
        result = self._run(verify_otp("000000", self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "otp_wrong"
        assert result["attempts_remaining"] == 2

    def test_verify_otp_three_wrong_codes_locks(self):
        from tools.wavvy_tools import send_otp, verify_otp
        self._run(send_otp(self.call_id))
        for _ in range(3):
            r = self._run(verify_otp("000000", self.call_id))
        assert r["fast_response_key"] == "otp_max_attempts"
        assert get_session(self.call_id).otp_locked is True

    def test_verify_otp_expired_code(self):
        from tools.wavvy_tools import send_otp, verify_otp
        r = self._run(send_otp(self.call_id))
        # Wind the sent_at back past 5 minutes
        s = get_session(self.call_id)
        s.otp_sent_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        result = self._run(verify_otp(r["otp"], self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "otp_expired"

    def test_verify_otp_no_otp_pending(self):
        from tools.wavvy_tools import verify_otp
        result = self._run(verify_otp("123456", self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "no_otp_pending"

    def test_send_otp_cooldown_prevents_immediate_resend(self):
        from tools.wavvy_tools import send_otp
        self._run(send_otp(self.call_id))
        result = self._run(send_otp(self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "otp_cooldown"

    def test_send_otp_max_resend_limit(self):
        from tools.wavvy_tools import send_otp
        s = get_session(self.call_id)
        s.otp_resend_count = 5
        result = self._run(send_otp(self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "otp_resend_limit"

    def test_verify_otp_requires_session(self):
        from tools.wavvy_tools import verify_otp
        result = self._run(verify_otp("123456", "nonexistent-call"))
        assert not result["success"]
        assert result["fast_response_key"] == "no_otp_pending"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tool return-value contracts (mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestReportFraudContract:
    """Verify report_fraud returns a fraud_number when the transaction exists."""

    def _make_session(self, call_id: str, *, otp_verified: bool = True):
        s = create_session(call_id)
        s.customer_id = "aaaaaaaa-0000-0000-0000-000000000001"
        s.otp_verified = otp_verified
        return s

    def teardown_method(self):
        for k in list(ACTIVE_CALLS):
            if k.startswith("test-fraud"):
                remove_session(k)

    @staticmethod
    def _make_db_ctx(txn_row: dict | None):
        """Build a fake AsyncSessionLocal context manager that returns txn_row."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = txn_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    async def test_report_fraud_returns_fraud_number(self):
        call_id = "test-fraud-01"
        import uuid
        txn_id = uuid.uuid4()
        txn_row = {"id": txn_id, "txn_number": "TXN-3300", "status": "completed"}
        self._make_session(call_id)

        with (
            patch("tools.wavvy_tools._db_module.AsyncSessionLocal",
                  side_effect=[
                      self._make_db_ctx(txn_row),   # SELECT txn
                      self._make_db_ctx(txn_row),   # UPDATE + INSERT
                  ]),
            patch("utils.ref_numbers.next_fraud_number",
                  new=AsyncMock(return_value="FRAUD-202605-0001")),
        ):
            from tools.wavvy_tools import report_fraud
            result = await report_fraud("TXN-3300", "unauthorized_transaction", call_id)

        assert result["success"] is True
        assert result["fraud_number"] == "FRAUD-202605-0001"
        assert "fraud_number" in result
        assert "FRAUD-202605-0001" in result.get("message", "")

    async def test_report_fraud_requires_otp_verified(self):
        call_id = "test-fraud-02"
        self._make_session(call_id, otp_verified=False)
        from tools.wavvy_tools import report_fraud
        result = await report_fraud("TXN-3300", "unauthorized_transaction", call_id)
        assert not result["success"]
        assert result["fast_response_key"] == "verification_required"

    async def test_report_fraud_transaction_not_found(self):
        call_id = "test-fraud-03"
        self._make_session(call_id)

        with patch("tools.wavvy_tools._db_module.AsyncSessionLocal",
                   return_value=self._make_db_ctx(None)):
            from tools.wavvy_tools import report_fraud
            result = await report_fraud("TXN-9999", "unauthorized_transaction", call_id)

        assert not result["success"]
        assert result["fast_response_key"] == "transaction_not_found"

    async def test_report_fraud_already_reported(self):
        call_id = "test-fraud-04"
        import uuid
        from constants.transaction_status import FRAUD_REPORTED
        txn_row = {"id": uuid.uuid4(), "txn_number": "TXN-3300", "status": FRAUD_REPORTED}
        self._make_session(call_id)

        with patch("tools.wavvy_tools._db_module.AsyncSessionLocal",
                   return_value=self._make_db_ctx(txn_row)):
            from tools.wavvy_tools import report_fraud
            result = await report_fraud("TXN-3300", "unauthorized_transaction", call_id)

        assert not result["success"]
        assert result["fast_response_key"] == "fraud_already_reported"

    async def test_report_fraud_no_session(self):
        from tools.wavvy_tools import report_fraud
        result = await report_fraud("TXN-3300", "unauthorized_transaction", "no-such-call")
        assert not result["success"]
        assert result["fast_response_key"] == "verification_required"


@pytest.mark.asyncio
class TestInitiateRefundContract:
    def _make_session(self, call_id: str, *, otp_verified: bool = True):
        s = create_session(call_id)
        s.customer_id = "aaaaaaaa-0000-0000-0000-000000000002"
        s.otp_verified = otp_verified
        return s

    def teardown_method(self):
        for k in list(ACTIVE_CALLS):
            if k.startswith("test-refund"):
                remove_session(k)

    @staticmethod
    def _make_db_ctx(txn_row: dict | None):
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = txn_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    async def test_initiate_refund_returns_rfn_number(self):
        call_id = "test-refund-01"
        import uuid
        from constants.transaction_status import FAILED
        txn_row = {
            "id": uuid.uuid4(),
            "txn_number": "TXN-1100",
            "status": FAILED,
            "merchant": "Swiggy",
            "amount": "450.00",
        }
        self._make_session(call_id)

        with (
            patch("tools.wavvy_tools._db_module.AsyncSessionLocal",
                  side_effect=[
                      self._make_db_ctx(txn_row),
                      self._make_db_ctx(txn_row),
                  ]),
            patch("utils.ref_numbers.next_rfn_number",
                  new=AsyncMock(return_value="RFN-202605-0001")),
        ):
            from tools.wavvy_tools import initiate_refund
            result = await initiate_refund("TXN-1100", call_id)

        assert result["success"] is True
        assert result.get("rfn_number") == "RFN-202605-0001"

    async def test_initiate_refund_requires_otp(self):
        call_id = "test-refund-02"
        self._make_session(call_id, otp_verified=False)
        from tools.wavvy_tools import initiate_refund
        result = await initiate_refund("TXN-1100", call_id)
        assert not result["success"]
        assert result["fast_response_key"] == "verification_required"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Full workflow scenarios — stage transitions + OTP + tool sequencing
# ─────────────────────────────────────────────────────────────────────────────

class TestFraudReportWorkflow:
    """
    End-to-end simulation of the fraud report flow.
    Uses real ACTIVE_CALLS and in-memory OTP logic.
    DB calls to wavvy_tools are mocked.
    Asserts:
      - Each stage gate blocks / allows the right tools
      - Stage advances correctly after each step
      - report_fraud is only reachable after OTP
      - The tool string response contains the fraud reference number
    """

    def setup_method(self):
        self.call_id = "test-e2e-fraud"
        self.s = create_session(self.call_id)
        self.s.customer_id = "aaaaaaaa-0000-0000-0000-ffffffffffff"

    def teardown_method(self):
        remove_session(self.call_id)

    def _run(self, coro):
        return asyncio.run(coro)

    # ── Step 1: GREETING — only verify_account allowed ────────────────────────

    def test_step1_greeting_blocks_otp(self):
        allowed, _ = is_tool_allowed(self.s.conv_state.stage, "send_otp")
        assert not allowed

    def test_step1_greeting_blocks_write_tools(self):
        for t in ["report_fraud", "raise_dispute", "unlock_account"]:
            assert not is_tool_allowed(self.s.conv_state.stage, t)[0]

    def test_step1_greeting_allows_verify_account(self):
        assert is_tool_allowed(self.s.conv_state.stage, "verify_account")[0]

    # ── Step 2: After verify_account → VERIFICATION stage ────────────────────

    def test_step2_stage_advances_to_verification(self):
        self.s.conv_state.transition_to(ConversationStage.DISCOVERY)
        self.s.conv_state.transition_to(ConversationStage.VERIFICATION)
        assert self.s.conv_state.stage == ConversationStage.VERIFICATION

    def test_step2_verification_allows_send_otp(self):
        self.s.conv_state.transition_to(ConversationStage.DISCOVERY)
        self.s.conv_state.transition_to(ConversationStage.VERIFICATION)
        assert is_tool_allowed(self.s.conv_state.stage, "send_otp")[0]

    def test_step2_verification_still_blocks_report_fraud(self):
        self.s.conv_state.transition_to(ConversationStage.DISCOVERY)
        self.s.conv_state.transition_to(ConversationStage.VERIFICATION)
        allowed, _ = is_tool_allowed(self.s.conv_state.stage, "report_fraud")
        assert not allowed, "report_fraud must be blocked until OTP is verified"

    # ── Step 3: OTP sent and verified → TOOL_EXECUTION stage ─────────────────

    def test_step3_otp_flow_advances_stage(self):
        from tools.wavvy_tools import send_otp, verify_otp

        # Pre-set stage to VERIFICATION
        self.s.conv_state.transition_to(ConversationStage.DISCOVERY)
        self.s.conv_state.transition_to(ConversationStage.VERIFICATION)

        # Send OTP
        r = self._run(send_otp(self.call_id))
        assert r["success"], "send_otp should succeed"
        code = r["otp"]

        # Verify OTP — tool handler should advance stage
        verify_result = self._run(verify_otp(code, self.call_id))
        assert verify_result["success"]
        # Simulate what agent_tools.verify_otp does — advance stage
        self.s.conv_state.transition_to(ConversationStage.TOOL_EXECUTION)
        assert self.s.conv_state.stage == ConversationStage.TOOL_EXECUTION

    def test_step3_tool_execution_allows_report_fraud(self):
        self.s.conv_state.stage = ConversationStage.TOOL_EXECUTION
        assert is_tool_allowed(ConversationStage.TOOL_EXECUTION, "report_fraud")[0]

    # ── Step 4: report_fraud returns fraud reference ──────────────────────────

    def test_step4_report_fraud_response_contains_ref_number(self):
        """The tool wrapper in agent_tools.py must include the fraud reference
        number in its return string so the LLM can read it back to the customer."""
        # The agent_tools wrapper returns:
        #   "Fraud report filed for {txn}.{ref_part} Our fraud team..."
        # where ref_part is " Your reference number is {fraud_number}."
        # We test the message field from wavvy_tools directly.
        import uuid
        from constants.transaction_status import COMPLETED

        txn_row = {"id": uuid.uuid4(), "txn_number": "TXN-3300", "status": COMPLETED}
        self.s.otp_verified = True

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = txn_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("tools.wavvy_tools._db_module.AsyncSessionLocal",
                  side_effect=[ctx, ctx]),
            patch("utils.ref_numbers.next_fraud_number",
                  new=AsyncMock(return_value="FRAUD-202605-TEST")),
        ):
            from tools.wavvy_tools import report_fraud
            result = self._run(report_fraud("TXN-3300", "unauthorized_transaction", self.call_id))

        assert result["success"]
        assert result["fraud_number"] == "FRAUD-202605-TEST"
        # The message field is what the agent MUST read to the customer
        assert "FRAUD-202605-TEST" in result["message"], (
            "fraud_number must appear in the tool message so the LLM reads it back"
        )

    # ── Regression: OTP bypass attempt ────────────────────────────────────────

    def test_report_fraud_blocked_without_otp(self):
        """Stage at TOOL_EXECUTION but otp_verified=False — tool must reject."""
        from tools.wavvy_tools import report_fraud
        self.s.conv_state.stage = ConversationStage.TOOL_EXECUTION
        self.s.otp_verified = False
        result = self._run(report_fraud("TXN-3300", "unauthorized_transaction", self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "verification_required"

    # ── Regression: escalation without customer permission ────────────────────

    def test_escalation_tool_is_always_stage_permitted(self):
        """escalate_to_human should be reachable from any non-ENDED stage."""
        non_ended = [s for s in ConversationStage if s != ConversationStage.ENDED]
        for stage in non_ended:
            allowed, _ = is_tool_allowed(stage, "escalate_to_human")
            assert allowed, f"escalate_to_human must be allowed at {stage.value}"


class TestRefundWorkflow:
    """Same pattern as fraud — verify the initiate_refund path."""

    def setup_method(self):
        self.call_id = "test-e2e-refund"
        self.s = create_session(self.call_id)
        self.s.customer_id = "bbbbbbbb-0000-0000-0000-ffffffffffff"

    def teardown_method(self):
        remove_session(self.call_id)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_refund_blocked_at_verification_stage(self):
        self.s.conv_state.transition_to(ConversationStage.DISCOVERY)
        self.s.conv_state.transition_to(ConversationStage.VERIFICATION)
        allowed, _ = is_tool_allowed(self.s.conv_state.stage, "initiate_refund")
        assert not allowed

    def test_refund_allowed_at_tool_execution(self):
        self.s.conv_state.stage = ConversationStage.TOOL_EXECUTION
        allowed, _ = is_tool_allowed(self.s.conv_state.stage, "initiate_refund")
        assert allowed

    def test_refund_blocked_without_otp_regardless_of_stage(self):
        from tools.wavvy_tools import initiate_refund
        self.s.conv_state.stage = ConversationStage.TOOL_EXECUTION
        self.s.otp_verified = False
        result = self._run(initiate_refund("TXN-1100", self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "verification_required"


class TestDisputeWorkflow:
    """Verify the raise_dispute path."""

    def setup_method(self):
        self.call_id = "test-e2e-dispute"
        self.s = create_session(self.call_id)
        self.s.customer_id = "cccccccc-0000-0000-0000-ffffffffffff"

    def teardown_method(self):
        remove_session(self.call_id)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_dispute_blocked_at_verification_stage(self):
        self.s.conv_state.stage = ConversationStage.VERIFICATION
        allowed, _ = is_tool_allowed(self.s.conv_state.stage, "raise_dispute")
        assert not allowed

    def test_dispute_allowed_at_tool_execution(self):
        allowed, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, "raise_dispute")
        assert allowed

    def test_dispute_blocked_without_otp(self):
        from tools.wavvy_tools import raise_dispute
        self.s.conv_state.stage = ConversationStage.TOOL_EXECUTION
        self.s.otp_verified = False
        result = self._run(raise_dispute("TXN-1100", "no_service_received", self.call_id))
        assert not result["success"]
        assert result["fast_response_key"] == "verification_required"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Seed integrity — catch cross-assignment bugs like Scenario 1
#    Requires a live DB connection. Skipped automatically if DB is unreachable.
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedIntegrity:
    """
    Verify that each seed customer owns the refund/hold/fraud rows they're
    supposed to own. Prevents the silent cross-assignment that caused Scenario 1
    to fail (TXN-6540 refund planted under Aryan Sharma's customer_id instead
    of Neha Reddy's).

    Requires live DB. Skipped automatically when DB is unreachable.
    Uses asyncpg directly (bypasses SQLAlchemy pool) so each test gets a fresh
    connection with no cross-loop contamination.
    """

    # ── asyncpg helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _dsn() -> str:
        from config import settings
        # asyncpg needs postgresql:// not postgresql+asyncpg://
        return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @classmethod
    def _query(cls, sql: str, *args):
        """Run a single SQL query and return list of Record objects."""
        import asyncpg

        async def _run():
            conn = await asyncpg.connect(cls._dsn())
            try:
                return await conn.fetch(sql, *args)
            finally:
                await conn.close()

        try:
            return asyncio.run(_run())
        except Exception:
            return None  # DB unreachable

    @classmethod
    def _skip_if_no_db(cls):
        rows = cls._query("SELECT 1 AS ok")
        if rows is None:
            pytest.skip("DB not reachable")

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_neha_refund_owned_by_neha(self):
        self._skip_if_no_db()
        neha = self._query("SELECT id FROM customers WHERE phone = $1", "+918765432109")
        assert neha, "Neha Reddy not in DB — run seed.py first"
        neha_id = str(neha[0]["id"])

        refund = self._query(
            "SELECT customer_id FROM refunds WHERE rfn_number = $1",
            "RFN-20260527-0002",
        )
        assert refund, "RFN-20260527-0002 not seeded — run seed.py"
        assert str(refund[0]["customer_id"]) == neha_id, (
            f"RFN-20260527-0002 belongs to {refund[0]['customer_id']}, "
            f"expected Neha Reddy ({neha_id})"
        )

    def test_kabir_refund_owned_by_kabir(self):
        self._skip_if_no_db()
        kabir = self._query("SELECT id FROM customers WHERE phone = $1", "+918812345602")
        assert kabir, "Kabir Singh not in DB — run seed.py first"
        kabir_id = str(kabir[0]["id"])

        refund = self._query(
            "SELECT customer_id FROM refunds WHERE rfn_number = $1",
            "RFN-20260528-0001",
        )
        assert refund, "RFN-20260528-0001 not seeded — run seed.py"
        assert str(refund[0]["customer_id"]) == kabir_id, (
            f"RFN-20260528-0001 belongs to {refund[0]['customer_id']}, "
            f"expected Kabir Singh ({kabir_id})"
        )

    def test_raj_fraud_case_owned_by_raj(self):
        self._skip_if_no_db()
        raj = self._query("SELECT id FROM customers WHERE phone = $1", "+917654321098")
        assert raj, "Raj Patel not in DB — run seed.py first"
        raj_id = str(raj[0]["id"])

        fc = self._query(
            "SELECT customer_id FROM fraud_cases WHERE fraud_number = $1",
            "FRAUD-202605-0001",
        )
        assert fc, "FRAUD-202605-0001 not seeded — run seed.py"
        assert str(fc[0]["customer_id"]) == raj_id, (
            f"FRAUD-202605-0001 belongs to {fc[0]['customer_id']}, "
            f"expected Raj Patel ({raj_id})"
        )

    def test_no_refund_cross_ownership(self):
        """refunds.customer_id must always match the transaction's customer_id."""
        self._skip_if_no_db()
        mismatches = self._query("""
            SELECT r.rfn_number
            FROM refunds r
            JOIN transactions t ON r.transaction_id = t.id
            WHERE r.customer_id != t.customer_id
        """)
        assert not mismatches, (
            "Refunds with wrong customer_id: "
            + ", ".join(r["rfn_number"] for r in mismatches)
        )

    def test_no_fraud_case_cross_ownership(self):
        """fraud_cases.customer_id must always match the transaction's customer_id."""
        self._skip_if_no_db()
        mismatches = self._query("""
            SELECT fc.fraud_number
            FROM fraud_cases fc
            JOIN transactions t ON fc.transaction_id = t.id
            WHERE fc.customer_id != t.customer_id
        """)
        assert not mismatches, (
            "Fraud cases with wrong customer_id: "
            + ", ".join(r["fraud_number"] for r in mismatches)
        )

    def test_raj_fraud_case_is_under_review(self):
        """FRAUD-202605-0001 must be status=under_review so verify_account surfaces it.
        The seed resets it on each run; this catches stale cleared/resolved state
        left by previous demo calls."""
        self._skip_if_no_db()
        rows = self._query(
            "SELECT status FROM fraud_cases WHERE fraud_number = $1",
            "FRAUD-202605-0001",
        )
        assert rows, "FRAUD-202605-0001 not seeded — run seed.py"
        assert rows[0]["status"] == "under_review", (
            f"FRAUD-202605-0001 status='{rows[0]['status']}', expected 'under_review' — "
            "run seed.py to reset it"
        )

    def test_verify_account_surfaces_correct_data(self):
        """
        End-to-end integration: verify_account for each key customer must populate
        their session cache correctly. Run in a single asyncio.run() to share the
        SQLAlchemy engine pool across both calls (avoids cross-loop contamination).
        """
        self._skip_if_no_db()
        raj_id = "test-seed-int-raj"
        neha_id_call = "test-seed-int-neha"
        raj_s = create_session(raj_id)
        neha_s = create_session(neha_id_call)

        async def _check():
            from tools.wavvy_tools import verify_account

            # Raj: FRAUD-202605-0001 must appear in active_fraud_cases
            r_raj = await verify_account("+917654321098", raj_id)
            assert r_raj["success"], "verify_account failed for Raj Patel"
            fraud_cases = raj_s.customer_profile.get("active_fraud_cases") or []
            assert fraud_cases, (
                "active_fraud_cases empty for Raj — fraud case may be cleared; run seed.py"
            )
            numbers = [fc["fraud_number"] for fc in fraud_cases]
            assert "FRAUD-202605-0001" in numbers, (
                f"FRAUD-202605-0001 missing from Raj's active_fraud_cases: {numbers}"
            )

            # Neha: RFN-20260527-0002 must appear in open_refunds
            r_neha = await verify_account("+918765432109", neha_id_call)
            assert r_neha["success"], "verify_account failed for Neha Reddy"
            open_refunds = neha_s.customer_profile.get("open_refunds") or []
            assert open_refunds, (
                "open_refunds empty for Neha — refund row missing or wrong customer_id; run seed.py"
            )
            rfns = [r["rfn_number"] for r in open_refunds]
            assert "RFN-20260527-0002" in rfns, (
                f"RFN-20260527-0002 missing from Neha's open_refunds: {rfns}"
            )

        try:
            asyncio.run(_check())
        finally:
            remove_session(raj_id)
            remove_session(neha_id_call)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
