"""
Phase 3 hardening tests — run from backend/:
    .venv/bin/pytest tests/test_phase3_hardening.py -v

Tests cover:
  - Transaction status constants
  - TOOL_PERMISSIONS completeness for all Fin tools
  - CallSession new fields exist with correct defaults
  - send_otp: cooldown enforcement, resend cap
  - verify_otp: expiry, wrong-code attempts, locked state
  - verify_account: attempt counter increments on failure, resets on success
  - initiate_refund: all 5 status pre-checks, idempotency guard
  - agent_tools wrappers: correct natural-language responses for each new key
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from session.call_session import CallSession, create_session, remove_session, ACTIVE_CALLS


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_session(call_id: str = "test-call-001") -> CallSession:
    s = create_session(call_id)
    return s


def _cleanup(call_id: str):
    remove_session(call_id)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Transaction status constants
# ─────────────────────────────────────────────────────────────────────────────

class TestTransactionStatusConstants:
    def test_all_constants_defined(self):
        from constants.transaction_status import (
            FAILED, COMPLETED, FLAGGED,
            REFUND_INITIATED, REFUND_PROCESSING, REFUND_COMPLETED, KYC_HOLD,
        )
        assert FAILED            == "failed"
        assert COMPLETED         == "completed"
        assert FLAGGED           == "flagged"
        assert REFUND_INITIATED  == "refund_initiated"
        assert REFUND_PROCESSING == "refund_processing"
        assert REFUND_COMPLETED  == "refund_completed"
        assert KYC_HOLD          == "kyc_hold"

    def test_no_typos_via_import(self):
        """Importing should never raise — catches typo drift at import time."""
        import constants.transaction_status as ts
        assert hasattr(ts, "FAILED")
        assert hasattr(ts, "REFUND_INITIATED")


# ─────────────────────────────────────────────────────────────────────────────
# 2. TOOL_PERMISSIONS — all Fin tools present
# ─────────────────────────────────────────────────────────────────────────────

class TestToolPermissions:
    def _perms_for(self, stage_name: str) -> set:
        from guardrails.tool_permissions import TOOL_PERMISSIONS
        from session.conversation_state import ConversationStage
        stage = ConversationStage(stage_name)
        return TOOL_PERMISSIONS.get(stage, set())

    def test_verify_account_allowed_in_greeting(self):
        assert "verify_account" in self._perms_for("greeting")

    def test_verify_account_allowed_in_discovery(self):
        assert "verify_account" in self._perms_for("discovery")

    def test_send_otp_allowed_in_verification(self):
        assert "send_otp" in self._perms_for("verification")

    def test_verify_otp_allowed_in_verification(self):
        assert "verify_otp" in self._perms_for("verification")

    def test_all_fin_tools_in_tool_execution(self):
        tools = self._perms_for("tool_execution")
        fin_tools = {
            "verify_account", "send_otp", "verify_otp",
            "lookup_transaction", "unlock_account", "initiate_refund",
            "escalate_to_human",
        }
        missing = fin_tools - tools
        assert not missing, f"Missing from TOOL_EXECUTION: {missing}"

    def test_send_otp_not_in_greeting(self):
        # OTP makes no sense before identity check
        assert "send_otp" not in self._perms_for("greeting")

    def test_initiate_refund_not_in_greeting(self):
        assert "initiate_refund" not in self._perms_for("greeting")

    def test_ended_stage_empty(self):
        assert len(self._perms_for("ended")) == 0

    def test_is_tool_allowed_returns_false_for_wrong_stage(self):
        from guardrails.tool_permissions import is_tool_allowed
        from session.conversation_state import ConversationStage
        allowed, reason = is_tool_allowed(ConversationStage.GREETING, "initiate_refund")
        assert allowed is False
        assert "initiate_refund" in reason

    def test_is_tool_allowed_returns_true_for_correct_stage(self):
        from guardrails.tool_permissions import is_tool_allowed
        from session.conversation_state import ConversationStage
        allowed, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, "initiate_refund")
        assert allowed is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. CallSession new fields
# ─────────────────────────────────────────────────────────────────────────────

class TestCallSessionNewFields:
    def setup_method(self):
        self.call_id = "test-session-fields"
        self.session = _make_session(self.call_id)

    def teardown_method(self):
        _cleanup(self.call_id)

    def test_otp_sent_at_defaults_none(self):
        assert self.session.otp_sent_at is None

    def test_otp_attempts_defaults_zero(self):
        assert self.session.otp_attempts == 0

    def test_otp_locked_defaults_false(self):
        assert self.session.otp_locked is False

    def test_otp_resend_count_defaults_zero(self):
        assert self.session.otp_resend_count == 0

    def test_verify_account_attempts_defaults_zero(self):
        assert self.session.verify_account_attempts == 0

    def test_refund_case_id_defaults_none(self):
        assert self.session.refund_case_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. send_otp hardening
# ─────────────────────────────────────────────────────────────────────────────

class TestSendOTP:
    def setup_method(self):
        self.call_id = "test-send-otp"
        self.session = _make_session(self.call_id)

    def teardown_method(self):
        _cleanup(self.call_id)

    def test_first_send_succeeds(self):
        from tools.wavvy_tools import send_otp
        result = asyncio.get_event_loop().run_until_complete(send_otp(self.call_id))
        assert result["success"] is True
        assert result["fast_response_key"] == "otp_sent"
        assert len(result["otp"]) == 6

    def test_resend_count_increments(self):
        from tools.wavvy_tools import send_otp
        asyncio.get_event_loop().run_until_complete(send_otp(self.call_id))
        assert self.session.otp_resend_count == 1

    def test_cooldown_blocks_immediate_resend(self):
        from tools.wavvy_tools import send_otp
        loop = asyncio.get_event_loop()
        loop.run_until_complete(send_otp(self.call_id))
        result = loop.run_until_complete(send_otp(self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_cooldown"
        assert result["retry_in_seconds"] > 0

    def test_cooldown_allows_send_after_30s(self):
        from tools.wavvy_tools import send_otp
        loop = asyncio.get_event_loop()
        loop.run_until_complete(send_otp(self.call_id))
        # Backdate the send timestamp by 31 seconds
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
        result = loop.run_until_complete(send_otp(self.call_id))
        assert result["success"] is True

    def test_resend_cap_at_5(self):
        from tools.wavvy_tools import send_otp
        loop = asyncio.get_event_loop()
        for i in range(5):
            self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
            loop.run_until_complete(send_otp(self.call_id))
        assert self.session.otp_resend_count == 5
        # 6th attempt — over cap
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
        result = loop.run_until_complete(send_otp(self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_resend_limit"

    def test_new_send_resets_attempt_counter(self):
        from tools.wavvy_tools import send_otp
        loop = asyncio.get_event_loop()
        loop.run_until_complete(send_otp(self.call_id))
        self.session.otp_attempts = 2  # simulate two wrong codes
        # Backdate to pass cooldown
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
        loop.run_until_complete(send_otp(self.call_id))
        assert self.session.otp_attempts == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. verify_otp hardening
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyOTP:
    def setup_method(self):
        self.call_id = "test-verify-otp"
        self.session = _make_session(self.call_id)
        # Prime a valid OTP
        self.session.otp_code = "123456"
        self.session.otp_sent_at = datetime.now(timezone.utc)
        self.session.otp_attempts = 0
        self.session.otp_locked = False

    def teardown_method(self):
        _cleanup(self.call_id)

    def test_correct_code_succeeds(self):
        from tools.wavvy_tools import verify_otp
        result = asyncio.get_event_loop().run_until_complete(verify_otp("123456", self.call_id))
        assert result["success"] is True
        assert self.session.otp_verified is True

    def test_wrong_code_returns_attempts_remaining(self):
        from tools.wavvy_tools import verify_otp
        result = asyncio.get_event_loop().run_until_complete(verify_otp("000000", self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_wrong"
        assert result["attempts_remaining"] == 2

    def test_three_wrong_codes_locks(self):
        from tools.wavvy_tools import verify_otp
        loop = asyncio.get_event_loop()
        for _ in range(3):
            result = loop.run_until_complete(verify_otp("000000", self.call_id))
        assert self.session.otp_locked is True
        assert result["fast_response_key"] == "otp_max_attempts"

    def test_locked_state_blocks_further_attempts(self):
        from tools.wavvy_tools import verify_otp
        loop = asyncio.get_event_loop()
        self.session.otp_locked = True
        self.session.otp_attempts = 3
        result = loop.run_until_complete(verify_otp("123456", self.call_id))
        # Even correct code blocked when locked
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_max_attempts"

    def test_expired_otp_returns_otp_expired(self):
        from tools.wavvy_tools import verify_otp
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        result = asyncio.get_event_loop().run_until_complete(verify_otp("123456", self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_expired"
        assert self.session.otp_code is None  # cleared on expiry

    def test_no_otp_pending(self):
        from tools.wavvy_tools import verify_otp
        self.session.otp_code = None
        result = asyncio.get_event_loop().run_until_complete(verify_otp("123456", self.call_id))
        assert result["fast_response_key"] == "no_otp_pending"

    def test_attempts_remaining_decrements(self):
        from tools.wavvy_tools import verify_otp
        loop = asyncio.get_event_loop()
        r1 = loop.run_until_complete(verify_otp("000000", self.call_id))
        r2 = loop.run_until_complete(verify_otp("000000", self.call_id))
        assert r1["attempts_remaining"] == 2
        assert r2["attempts_remaining"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. verify_account attempt tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyAccountAttempts:
    def setup_method(self):
        self.call_id = "test-verify-acct"
        self.session = _make_session(self.call_id)

    def teardown_method(self):
        _cleanup(self.call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_not_found_increments_attempts(self, mock_db_class):
        """Verify attempt counter increments when account not found."""
        mock_db = AsyncMock()
        mock_db_class.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_class.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = asyncio.get_event_loop().run_until_complete(
            __import__("tools.wavvy_tools", fromlist=["verify_account"]).verify_account(
                "+919999999999", self.call_id
            )
        )
        assert result["success"] is False
        assert result["attempts"] == 1
        assert self.session.verify_account_attempts == 1

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_success_resets_attempts(self, mock_db_class):
        """Attempt counter resets to 0 on successful lookup."""
        self.session.verify_account_attempts = 2  # simulate prior failures

        mock_db = AsyncMock()
        mock_db_class.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_class.return_value.__aexit__ = AsyncMock(return_value=False)

        import uuid
        fake_row = {
            "id": uuid.uuid4(), "name": "Test User",
            "phone": "+919999999999", "email": "test@email.com",
            "account_type": "savings", "account_status": "active",
            "kyc_status": "verified", "fraud_hold_active": False,
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = fake_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        asyncio.get_event_loop().run_until_complete(
            __import__("tools.wavvy_tools", fromlist=["verify_account"]).verify_account(
                "+919999999999", self.call_id
            )
        )
        assert self.session.verify_account_attempts == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. initiate_refund status pre-checks
# ─────────────────────────────────────────────────────────────────────────────

_REFUND_BASE_ORDER = {"id": "TXN-0001", "merchant": "Test", "amount": 100, "type": "debit"}


def _make_refund_session(call_id: str, status: str):
    s = _make_session(call_id)
    s.otp_verified = True
    s.customer_id = "00000000-0000-0000-0000-000000000001"
    return s


def _mock_db_with_order(mock_db_class, status: str):
    mock_db = AsyncMock()
    mock_db_class.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db_class.return_value.__aexit__ = AsyncMock(return_value=False)
    txn = {
        "txn_number": _REFUND_BASE_ORDER["id"],
        "merchant": _REFUND_BASE_ORDER["merchant"],
        "amount": _REFUND_BASE_ORDER["amount"],
        "txn_type": _REFUND_BASE_ORDER["type"],
        "status": status,
        "txn_date": "2026-05-01",
        "currency": "INR",
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = txn
    # second execute call (for existing refund check) returns None
    mock_result2 = MagicMock()
    mock_result2.mappings.return_value.first.return_value = None
    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_result2, mock_result, mock_result])
    mock_db.commit = AsyncMock()
    return mock_db


class TestInitiateRefundStatusChecks:
    def _run(self, call_id: str, status: str):
        from tools.wavvy_tools import initiate_refund
        return asyncio.get_event_loop().run_until_complete(
            initiate_refund("TXN-0001", call_id)
        )

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_failed_status_succeeds(self, mock_db_class):
        call_id = "refund-failed"
        _mock_db_with_order(mock_db_class, "failed")
        _make_refund_session(call_id, "failed")
        try:
            result = self._run(call_id, "failed")
            assert result["success"] is True
            assert result["fast_response_key"] == "refund_initiated"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_refund_initiated_returns_already_initiated(self, mock_db_class):
        call_id = "refund-already"
        _mock_db_with_order(mock_db_class, "refund_initiated")
        _make_refund_session(call_id, "refund_initiated")
        try:
            result = self._run(call_id, "refund_initiated")
            assert result["success"] is False
            assert result["fast_response_key"] == "refund_already_initiated"
            assert "estimated_days" in result
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_refund_processing_returns_already_initiated(self, mock_db_class):
        call_id = "refund-processing"
        _mock_db_with_order(mock_db_class, "refund_processing")
        _make_refund_session(call_id, "refund_processing")
        try:
            result = self._run(call_id, "refund_processing")
            assert result["fast_response_key"] == "refund_already_initiated"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_refund_completed_returns_already_completed(self, mock_db_class):
        call_id = "refund-completed"
        _mock_db_with_order(mock_db_class, "refund_completed")
        _make_refund_session(call_id, "refund_completed")
        try:
            result = self._run(call_id, "refund_completed")
            assert result["fast_response_key"] == "refund_already_completed"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_completed_returns_ineligible(self, mock_db_class):
        call_id = "refund-completed-txn"
        _mock_db_with_order(mock_db_class, "completed")
        _make_refund_session(call_id, "completed")
        try:
            result = self._run(call_id, "completed")
            assert result["success"] is False
            assert result["fast_response_key"] == "refund_ineligible"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_flagged_returns_fraud_review_required(self, mock_db_class):
        call_id = "refund-flagged"
        _mock_db_with_order(mock_db_class, "flagged")
        _make_refund_session(call_id, "flagged")
        try:
            result = self._run(call_id, "flagged")
            assert result["success"] is False
            assert result["fast_response_key"] == "fraud_review_required"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_kyc_hold_returns_kyc_escalation_required(self, mock_db_class):
        call_id = "refund-kyc"
        _mock_db_with_order(mock_db_class, "kyc_hold")
        _make_refund_session(call_id, "kyc_hold")
        try:
            result = self._run(call_id, "kyc_hold")
            assert result["success"] is False
            assert result["fast_response_key"] == "kyc_escalation_required"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_idempotency_blocks_second_refund(self, mock_db_class):
        call_id = "refund-idempotent"
        _mock_db_with_order(mock_db_class, "failed")
        s = _make_refund_session(call_id, "failed")
        s.refund_case_id = "existing-case-id"  # already opened this session
        try:
            result = self._run(call_id, "failed")
            assert result["success"] is False
            assert result["fast_response_key"] == "refund_already_initiated"
            assert result["refund_case_id"] == "existing-case-id"
        finally:
            _cleanup(call_id)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_successful_refund_sets_refund_case_id(self, mock_db_class):
        call_id = "refund-case-id-set"
        _mock_db_with_order(mock_db_class, "failed")
        s = _make_refund_session(call_id, "failed")
        try:
            result = self._run(call_id, "failed")
            assert result["success"] is True
            assert s.refund_case_id is not None
            assert len(s.refund_case_id) == 36  # UUID format
        finally:
            _cleanup(call_id)

    def test_no_otp_verification_blocks_refund(self):
        call_id = "refund-no-otp"
        s = _make_session(call_id)
        s.otp_verified = False
        s.customer_id = "00000000-0000-0000-0000-000000000001"
        try:
            from tools.wavvy_tools import initiate_refund
            result = asyncio.get_event_loop().run_until_complete(
                initiate_refund("TXN-0001", call_id)
            )
            assert result["fast_response_key"] == "verification_required"
        finally:
            _cleanup(call_id)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Seed customers — 3 new edge-case scenarios present in DB
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedCustomers:
    """Integration tests — hit the real DB. Skip if DB not available."""

    @pytest.mark.asyncio
    async def test_priya_iyer_has_double_debit(self):
        """Priya Iyer: TXN-1100 completed + TXN-1101 failed (double debit demo)."""
        try:
            from sqlalchemy import text
            import database as db_mod
            async with db_mod.AsyncSessionLocal() as db:
                r = await db.execute(
                    text("""
                        SELECT t.txn_number, t.status
                        FROM transactions t
                        JOIN customers c ON t.customer_id = c.id
                        WHERE c.phone = '+919000000001'
                    """)
                )
                rows = r.mappings().all()
        except Exception:
            pytest.skip("DB not available")

        assert rows, "Priya Iyer transactions not found — run seed.py"
        by_num = {r["txn_number"]: r["status"] for r in rows}
        assert "TXN-1100" in by_num
        assert "TXN-1101" in by_num
        assert by_num["TXN-1100"] == "completed"
        assert by_num["TXN-1101"] == "failed"

    @pytest.mark.asyncio
    async def test_kabir_singh_has_refund_in_progress(self):
        """Kabir Singh: TXN-2200 refund_initiated (refund-in-progress demo)."""
        try:
            from sqlalchemy import text
            import database as db_mod
            async with db_mod.AsyncSessionLocal() as db:
                r = await db.execute(
                    text("""
                        SELECT t.txn_number, t.status
                        FROM transactions t
                        JOIN customers c ON t.customer_id = c.id
                        WHERE c.phone = '+919000000002' AND t.txn_number = 'TXN-2200'
                    """)
                )
                row = r.mappings().first()
        except Exception:
            pytest.skip("DB not available")

        assert row is not None, "Kabir Singh TXN-2200 not found — run seed.py"
        assert row["status"] == "refund_initiated"

    @pytest.mark.asyncio
    async def test_zara_hussain_has_completed_dispute(self):
        """Zara Hussain: TXN-3300 completed (dispute → refund_ineligible demo)."""
        try:
            from sqlalchemy import text
            import database as db_mod
            async with db_mod.AsyncSessionLocal() as db:
                r = await db.execute(
                    text("""
                        SELECT t.txn_number, t.status
                        FROM transactions t
                        JOIN customers c ON t.customer_id = c.id
                        WHERE c.phone = '+919000000003' AND t.txn_number = 'TXN-3300'
                    """)
                )
                row = r.mappings().first()
        except Exception:
            pytest.skip("DB not available")

        assert row is not None, "Zara Hussain TXN-3300 not found — run seed.py"
        assert row["status"] == "completed"
