"""
Wavvy demo test suite — run from backend/:
    .venv/bin/pytest tests/test_wavvy.py -v

Covers each module independently:
  1. Session   — CallSession creation, defaults, ACTIVE_CALLS isolation
  2. ConvState — stage transitions (valid + blocked)
  3. Orchestrator — ExecutionMode transitions, entity slots, workflow exit
  4. Guardrails   — tool permissions per stage, rate limits
  5. IntentRouter — three-tier classify_tier (TRANSACTIONAL / CONVERSATIONAL / RECOVERY)
  6. WorkflowRunner — STEP_TRANSITIONS table coverage for key paths
  7. OTP flow  — send_otp cooldown/cap, verify_otp expiry/lock (unit, no DB)
  8. Refund    — initiate_refund status pre-checks + idempotency (unit, mocked DB)
  9. Constants — transaction status constants present and correct
 10. DB seed   — integration checks (skipped when DB unavailable)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session.call_session import CallSession, create_session, remove_session, ACTIVE_CALLS


# ── helpers ───────────────────────────────────────────────────────────────────

def _mk(call_id: str = "t-001") -> CallSession:
    return create_session(call_id)


def _rm(call_id: str):
    remove_session(call_id)


# =============================================================================
# 1. SESSION
# =============================================================================

class TestSession:
    def test_create_adds_to_active_calls(self):
        s = _mk("s-001")
        assert "s-001" in ACTIVE_CALLS
        _rm("s-001")

    def test_remove_clears_active_calls(self):
        _mk("s-002")
        _rm("s-002")
        assert "s-002" not in ACTIVE_CALLS

    def test_two_sessions_are_isolated(self):
        a = _mk("s-a")
        b = _mk("s-b")
        a.turn_count = 5
        assert b.turn_count == 0
        _rm("s-a"); _rm("s-b")

    def test_default_otp_fields(self):
        s = _mk("s-003")
        assert s.otp_code is None
        assert s.otp_verified is False
        assert s.otp_sent_at is None
        assert s.otp_attempts == 0
        assert s.otp_locked is False
        assert s.otp_resend_count == 0
        _rm("s-003")

    def test_default_refund_and_lead(self):
        s = _mk("s-004")
        assert s.refund_case_id is None
        assert s.lead_id is None
        assert s.customer_id is None
        _rm("s-004")

    def test_escalation_defaults(self):
        s = _mk("s-005")
        assert s.escalated is False
        assert s.escalation_reason is None
        _rm("s-005")


# =============================================================================
# 2. CONVERSATION STATE
# =============================================================================

class TestConversationState:
    def test_starts_in_greeting(self):
        from session.conversation_state import ConversationStateManager, ConversationStage
        m = ConversationStateManager()
        assert m.stage == ConversationStage.GREETING

    def test_valid_transition_greeting_to_discovery(self):
        from session.conversation_state import ConversationStateManager, ConversationStage
        m = ConversationStateManager()
        assert m.transition_to(ConversationStage.DISCOVERY) is True
        assert m.stage == ConversationStage.DISCOVERY

    def test_invalid_transition_blocked(self):
        from session.conversation_state import ConversationStateManager, ConversationStage
        m = ConversationStateManager()
        assert m.transition_to(ConversationStage.RESOLUTION) is False
        assert m.stage == ConversationStage.GREETING  # unchanged

    def test_ended_has_no_valid_transitions(self):
        from session.conversation_state import ConversationStateManager, ConversationStage
        m = ConversationStateManager()
        m.stage = ConversationStage.ENDED
        for stage in ConversationStage:
            assert m.transition_to(stage) is False

    def test_mark_escalated_sets_flag_and_stage(self):
        from session.conversation_state import ConversationStateManager, ConversationStage
        m = ConversationStateManager()
        m.mark_escalated()
        assert m.escalated is True
        assert m.stage == ConversationStage.ESCALATION

    def test_full_happy_path(self):
        from session.conversation_state import ConversationStateManager, ConversationStage
        m = ConversationStateManager()
        assert m.transition_to(ConversationStage.DISCOVERY)
        assert m.transition_to(ConversationStage.VERIFICATION)
        assert m.transition_to(ConversationStage.TOOL_EXECUTION)
        assert m.transition_to(ConversationStage.RESOLUTION)
        assert m.transition_to(ConversationStage.ENDED)
        assert m.stage == ConversationStage.ENDED


# =============================================================================
# 3. ORCHESTRATOR STATE
# =============================================================================

class TestOrchestratorState:
    def test_default_mode_is_general(self):
        from session.orchestrator_state import OrchestratorState, ExecutionMode
        s = OrchestratorState()
        assert s.mode == ExecutionMode.GENERAL

    def test_enter_workflow_sets_mode_and_ids(self):
        from session.orchestrator_state import OrchestratorState, ExecutionMode
        s = OrchestratorState()
        s.enter_workflow("wf-refund", "node-collect-phone")
        assert s.mode == ExecutionMode.WORKFLOW
        assert s.active_workflow_id == "wf-refund"
        assert s.active_node_id == "node-collect-phone"

    def test_exit_workflow_returns_to_general(self):
        from session.orchestrator_state import OrchestratorState, ExecutionMode
        s = OrchestratorState()
        s.enter_workflow("wf-refund", "node-1")
        s.exit_workflow()
        assert s.mode == ExecutionMode.GENERAL
        assert s.active_workflow_id is None

    def test_exit_workflow_records_completed_id(self):
        from session.orchestrator_state import OrchestratorState
        s = OrchestratorState()
        s.enter_workflow("wf-refund", "node-1")
        s.exit_workflow()
        assert "wf-refund" in s.completed_workflow_ids

    def test_exit_workflow_clears_entity_slots(self):
        from session.orchestrator_state import OrchestratorState
        s = OrchestratorState()
        s.enter_workflow("wf-refund", "node-1")
        s.entity_slots.phone = "+91987654321"
        s.entity_slots.otp = "123456"
        s.exit_workflow()
        assert s.entity_slots.phone is None
        assert s.entity_slots.otp is None

    def test_enter_escalation(self):
        from session.orchestrator_state import OrchestratorState, ExecutionMode
        s = OrchestratorState()
        s.enter_escalation()
        assert s.mode == ExecutionMode.ESCALATION

    def test_advance_to_node_resets_attempts(self):
        from session.orchestrator_state import OrchestratorState
        s = OrchestratorState()
        s.enter_workflow("wf-1", "node-1")
        s.node_attempts = 3
        s.advance_to_node("node-2")
        assert s.active_node_id == "node-2"
        assert s.node_attempts == 0

    def test_is_in_workflow(self):
        from session.orchestrator_state import OrchestratorState
        s = OrchestratorState()
        assert s.is_in_workflow() is False
        s.enter_workflow("wf-1", "n-1")
        assert s.is_in_workflow() is True


# =============================================================================
# 4. GUARDRAILS
# =============================================================================

class TestToolPermissions:
    def _allowed(self, stage_val: str, tool: str) -> bool:
        from guardrails.tool_permissions import is_tool_allowed
        from session.conversation_state import ConversationStage
        ok, _ = is_tool_allowed(ConversationStage(stage_val), tool)
        return ok

    def test_verify_account_allowed_at_greeting(self):
        assert self._allowed("greeting", "verify_account")

    def test_send_otp_blocked_at_greeting(self):
        assert not self._allowed("greeting", "send_otp")

    def test_initiate_refund_blocked_at_greeting(self):
        assert not self._allowed("greeting", "initiate_refund")

    def test_send_otp_allowed_at_verification(self):
        assert self._allowed("verification", "send_otp")

    def test_verify_otp_allowed_at_verification(self):
        assert self._allowed("verification", "verify_otp")

    def test_all_fin_tools_allowed_at_tool_execution(self):
        fin_tools = {
            "verify_account", "send_otp", "verify_otp",
            "lookup_transaction", "unlock_account", "initiate_refund",
            "escalate_to_human",
        }
        for t in fin_tools:
            assert self._allowed("tool_execution", t), f"{t} not allowed at tool_execution"

    def test_ended_stage_allows_nothing(self):
        from guardrails.tool_permissions import TOOL_PERMISSIONS
        from session.conversation_state import ConversationStage
        assert len(TOOL_PERMISSIONS.get(ConversationStage.ENDED, set())) == 0

    def test_reason_returned_when_blocked(self):
        from guardrails.tool_permissions import is_tool_allowed
        from session.conversation_state import ConversationStage
        ok, reason = is_tool_allowed(ConversationStage.GREETING, "initiate_refund")
        assert ok is False
        assert "initiate_refund" in reason

    def test_escalated_session_blocks_all_except_escalate(self):
        from guardrails.tool_permissions import is_tool_allowed
        from session.conversation_state import ConversationStage
        ok, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, "lookup_transaction", escalated=True)
        assert ok is False
        ok2, _ = is_tool_allowed(ConversationStage.TOOL_EXECUTION, "escalate_to_human", escalated=True)
        assert ok2 is True


class TestRateLimiter:
    def setup_method(self):
        self.call_id = "rl-test"
        self.session = _mk(self.call_id)

    def teardown_method(self):
        _rm(self.call_id)

    def test_fresh_session_allowed(self):
        from guardrails.rate_limiter import check_rate_limits
        r = check_rate_limits(self.call_id)
        assert r.allowed is True

    def test_turn_limit_blocks(self):
        from guardrails.rate_limiter import check_rate_limits, MAX_TURNS_PER_CALL
        self.session.turn_count = MAX_TURNS_PER_CALL
        r = check_rate_limits(self.call_id)
        assert r.allowed is False
        assert r.action == "force_end_call"

    def test_tool_calls_per_turn_blocks(self):
        from guardrails.rate_limiter import check_rate_limits, MAX_TOOL_CALLS_PER_TURN
        self.session.tool_calls_this_turn = MAX_TOOL_CALLS_PER_TURN
        r = check_rate_limits(self.call_id)
        assert r.allowed is False

    def test_token_budget_blocks(self):
        from guardrails.rate_limiter import check_rate_limits, MAX_TOKENS_PER_CALL
        self.session.cumulative_tokens = MAX_TOKENS_PER_CALL
        r = check_rate_limits(self.call_id)
        assert r.allowed is False
        assert r.action == "force_end_call"

    def test_increment_turn_resets_tool_count(self):
        from guardrails.rate_limiter import increment_turn, increment_tool_call
        increment_tool_call(self.call_id)
        increment_tool_call(self.call_id)
        increment_turn(self.call_id, tokens_used=100)
        assert self.session.tool_calls_this_turn == 0
        assert self.session.turn_count == 1
        assert self.session.cumulative_tokens == 100

    def test_no_session_returns_blocked(self):
        from guardrails.rate_limiter import check_rate_limits
        r = check_rate_limits("nonexistent-call")
        assert r.allowed is False


# =============================================================================
# 5. INTENT ROUTER
# =============================================================================

class TestIntentRouter:
    def _tier(self, text: str, conf: float = 1.0):
        from voice.intent_router import classify_tier
        return classify_tier(text, conf)

    def test_filler_is_recovery(self):
        from voice.intent_router import RoutingTier
        tier, intent = self._tier("uh")
        assert tier == RoutingTier.RECOVERY
        assert intent is None

    def test_okay_is_recovery(self):
        from voice.intent_router import RoutingTier
        tier, _ = self._tier("okay")
        assert tier == RoutingTier.RECOVERY

    def test_hello_is_conversational(self):
        from voice.intent_router import RoutingTier
        tier, intent = self._tier("hello")
        assert tier == RoutingTier.CONVERSATIONAL
        assert intent is None

    def test_demo_request_is_transactional(self):
        from voice.intent_router import RoutingTier, TransactionalIntent
        tier, intent = self._tier("I'd like to book a demo please", 0.9)
        assert tier == RoutingTier.TRANSACTIONAL
        assert intent == TransactionalIntent.DEMO_REQUEST

    def test_human_agent_request_is_transactional(self):
        from voice.intent_router import RoutingTier, TransactionalIntent
        tier, intent = self._tier("I want to speak to a human agent", 0.9)
        assert tier == RoutingTier.TRANSACTIONAL
        assert intent == TransactionalIntent.HUMAN_AGENT

    def test_low_confidence_short_utterance_is_recovery(self):
        # < 0.4 confidence + ≤ 3 words → RECOVERY by design (don't act on noisy STT)
        from voice.intent_router import RoutingTier
        tier, _ = self._tier("book a demo", 0.3)
        assert tier == RoutingTier.RECOVERY

    def test_low_confidence_long_utterance_is_conversational(self):
        # ≥ 4 words bypasses the confidence gate even at low confidence
        from voice.intent_router import RoutingTier
        tier, _ = self._tier("I would like to schedule a product demo please", 0.3)
        assert tier == RoutingTier.CONVERSATIONAL

    def test_general_question_is_conversational(self):
        from voice.intent_router import RoutingTier
        tier, _ = self._tier("what does Wavvy do exactly?")
        assert tier == RoutingTier.CONVERSATIONAL


# =============================================================================
# 6. WORKFLOW RUNNER (STEP_TRANSITIONS)
# =============================================================================

class TestWorkflowRunner:
    def _make_runner(self, call_id: str = "wf-run-001"):
        from workflow.engine import WorkflowRunner
        s = _mk(call_id)
        return WorkflowRunner(s), call_id

    def teardown_method(self):
        # clean any sessions created in this class
        for cid in list(ACTIVE_CALLS.keys()):
            _rm(cid)

    def test_verify_account_not_found_first_attempt(self):
        runner, cid = self._make_runner("wf-001")
        outcome = runner.advance("verify_account", "not_found_1")
        assert "verify_account" in outcome.message.lower() or "account" in outcome.message.lower()
        assert outcome.is_terminal is False

    def test_verify_account_max_attempts_requires_consent(self):
        runner, cid = self._make_runner("wf-002")
        outcome = runner.advance("verify_account", "not_found_max")
        assert outcome.requires_consent is True
        assert outcome.escalation_team is not None

    def test_account_found_message_not_empty(self):
        runner, cid = self._make_runner("wf-003")
        outcome = runner.advance("verify_account", "account_found")
        assert outcome.message  # must have a directive

    def test_otp_sent_success(self):
        runner, cid = self._make_runner("wf-004")
        outcome = runner.advance("send_otp", "otp_sent")
        assert outcome.message

    def test_otp_verify_success(self):
        runner, cid = self._make_runner("wf-005")
        outcome = runner.advance("verify_otp", "otp_verified")
        assert outcome.message

    def test_otp_wrong_gives_retry_directive(self):
        runner, cid = self._make_runner("wf-006")
        outcome = runner.advance("verify_otp", "otp_wrong")
        assert outcome.message

    def test_otp_expired_is_non_terminal(self):
        runner, cid = self._make_runner("wf-007")
        outcome = runner.advance("verify_otp", "otp_expired")
        assert outcome.is_terminal is False

    def test_otp_max_attempts_is_terminal(self):
        runner, cid = self._make_runner("wf-008")
        outcome = runner.advance("verify_otp", "otp_max_attempts")
        assert outcome.is_terminal is True

    def test_refund_initiated(self):
        runner, cid = self._make_runner("wf-009")
        outcome = runner.advance("initiate_refund", "refund_initiated")
        assert outcome.message

    def test_refund_already_initiated(self):
        runner, cid = self._make_runner("wf-010")
        outcome = runner.advance("initiate_refund", "refund_already_initiated")
        assert outcome.message

    def test_fraud_review_required(self):
        runner, cid = self._make_runner("wf-011")
        outcome = runner.advance("initiate_refund", "fraud_review_required")
        assert outcome.is_terminal is True or outcome.requires_consent is True

    def test_unknown_key_returns_fallback_message(self):
        runner, cid = self._make_runner("wf-012")
        outcome = runner.advance("verify_otp", "completely_made_up_key")
        assert "unexpected" in outcome.message.lower() or outcome.message

    def test_steps_taken_audit_trail(self):
        runner, cid = self._make_runner("wf-013")
        runner.advance("verify_account", "account_found")
        runner.advance("send_otp", "otp_sent")
        assert len(runner.progress.steps_taken) == 2
        assert runner.progress.steps_taken[0]["step"] == "verify_account"


# =============================================================================
# 7. OTP FLOW (unit — no DB)
# =============================================================================

class TestSendOTP:
    def setup_method(self):
        self.call_id = "otp-send-001"
        self.session = _mk(self.call_id)

    def teardown_method(self):
        _rm(self.call_id)

    def test_first_send_succeeds(self):
        from tools.wavvy_tools import send_otp
        result = asyncio.run(send_otp(self.call_id))
        assert result["success"] is True
        assert result["fast_response_key"] == "otp_sent"
        assert len(result["otp"]) == 6

    def test_resend_count_increments(self):
        from tools.wavvy_tools import send_otp
        asyncio.run(send_otp(self.call_id))
        assert self.session.otp_resend_count == 1

    def test_immediate_resend_blocked_by_cooldown(self):
        from tools.wavvy_tools import send_otp
        asyncio.run(send_otp(self.call_id))
        result = asyncio.run(send_otp(self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_cooldown"

    def test_resend_allowed_after_cooldown_expires(self):
        from tools.wavvy_tools import send_otp
        asyncio.run(send_otp(self.call_id))
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
        result = asyncio.run(send_otp(self.call_id))
        assert result["success"] is True

    def test_resend_cap_at_5(self):
        from tools.wavvy_tools import send_otp
        for _ in range(5):
            self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
            asyncio.run(send_otp(self.call_id))
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
        result = asyncio.run(send_otp(self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_resend_limit"

    def test_new_send_resets_attempt_counter(self):
        from tools.wavvy_tools import send_otp
        asyncio.run(send_otp(self.call_id))
        self.session.otp_attempts = 2
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(seconds=31)
        asyncio.run(send_otp(self.call_id))
        assert self.session.otp_attempts == 0


class TestVerifyOTP:
    def setup_method(self):
        self.call_id = "otp-verify-001"
        self.session = _mk(self.call_id)
        self.session.otp_code = "123456"
        self.session.otp_sent_at = datetime.now(timezone.utc)
        self.session.otp_attempts = 0
        self.session.otp_locked = False

    def teardown_method(self):
        _rm(self.call_id)

    def test_correct_code_succeeds(self):
        from tools.wavvy_tools import verify_otp
        result = asyncio.run(verify_otp("123456", self.call_id))
        assert result["success"] is True
        assert self.session.otp_verified is True

    def test_wrong_code_decrements_attempts(self):
        from tools.wavvy_tools import verify_otp
        result = asyncio.run(verify_otp("000000", self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_wrong"
        assert result["attempts_remaining"] == 2

    def test_three_failures_lock_session(self):
        from tools.wavvy_tools import verify_otp
        for _ in range(3):
            result = asyncio.run(verify_otp("000000", self.call_id))
        assert self.session.otp_locked is True
        assert result["fast_response_key"] == "otp_max_attempts"

    def test_locked_blocks_correct_code(self):
        from tools.wavvy_tools import verify_otp
        self.session.otp_locked = True
        self.session.otp_attempts = 3
        result = asyncio.run(verify_otp("123456", self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_max_attempts"

    def test_expired_otp_clears_code(self):
        from tools.wavvy_tools import verify_otp
        self.session.otp_sent_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        result = asyncio.run(verify_otp("123456", self.call_id))
        assert result["success"] is False
        assert result["fast_response_key"] == "otp_expired"
        assert self.session.otp_code is None

    def test_no_pending_otp(self):
        from tools.wavvy_tools import verify_otp
        self.session.otp_code = None
        result = asyncio.run(verify_otp("123456", self.call_id))
        assert result["fast_response_key"] == "no_otp_pending"


# =============================================================================
# 8. REFUND FLOW (unit — mocked DB)
# =============================================================================

def _stub_db(mock_db_class, status: str):
    """Wire AsyncSessionLocal mock to return a transaction row with the given status.

    initiate_refund opens 3 separate AsyncSessionLocal() contexts:
      ctx 1: SELECT transactions  (1 execute)
      ctx 2: SELECT refunds       (1 execute — must return None = no prior refund)
      ctx 3: sequence + UPDATE + INSERT  (3 executes, write path only)
    All contexts share the same mock_db (same return_value), so the execute
    side_effect list is consumed sequentially across all three contexts.
    """
    mock_db = AsyncMock()
    mock_db_class.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db_class.return_value.__aexit__ = AsyncMock(return_value=False)

    txn = {
        "id": "00000000-0000-0000-0000-000000000099",
        "txn_number": "TXN-0001",
        "merchant": "Test Merchant",
        "amount": 100,
        "txn_type": "debit",
        "status": status,
        "txn_date": "2026-05-01",
        "currency": "INR",
    }
    # ctx 1: transaction lookup
    mock_txn = MagicMock()
    mock_txn.mappings.return_value.first.return_value = txn

    # ctx 2: refunds table check — None means no prior refund exists
    mock_refunds_check = MagicMock()
    mock_refunds_check.mappings.return_value.first.return_value = None

    # ctx 3 (write path only): rfn sequence number
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 1

    mock_db.execute = AsyncMock(
        side_effect=[mock_txn, mock_refunds_check, mock_seq, MagicMock(), MagicMock()]
    )
    mock_db.commit = AsyncMock()
    return mock_db


def _refund_session(call_id: str) -> CallSession:
    s = _mk(call_id)
    s.otp_verified = True
    s.customer_id = "00000000-0000-0000-0000-000000000001"
    return s


class TestInitiateRefund:
    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_failed_txn_succeeds(self, mock_db_class):
        cid = "rf-001"
        _stub_db(mock_db_class, "failed")
        _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is True
            assert r["fast_response_key"] == "refund_initiated"
        finally:
            _rm(cid)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_refund_initiated_status_blocks(self, mock_db_class):
        cid = "rf-002"
        _stub_db(mock_db_class, "refund_initiated")
        _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is False
            assert r["fast_response_key"] == "refund_already_initiated"
        finally:
            _rm(cid)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_refund_completed_blocks(self, mock_db_class):
        cid = "rf-003"
        _stub_db(mock_db_class, "refund_completed")
        _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["fast_response_key"] == "refund_already_completed"
        finally:
            _rm(cid)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_completed_txn_ineligible(self, mock_db_class):
        cid = "rf-004"
        _stub_db(mock_db_class, "completed")
        _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is False
            assert r["fast_response_key"] == "refund_ineligible"
        finally:
            _rm(cid)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_flagged_txn_fraud_review(self, mock_db_class):
        cid = "rf-005"
        _stub_db(mock_db_class, "flagged")
        _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is False
            assert r["fast_response_key"] == "fraud_review_required"
        finally:
            _rm(cid)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_kyc_hold_escalates(self, mock_db_class):
        cid = "rf-006"
        _stub_db(mock_db_class, "kyc_hold")
        _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is False
            assert r["fast_response_key"] == "kyc_escalation_required"
        finally:
            _rm(cid)

    def test_idempotency_blocks_second_call(self):
        cid = "rf-007"
        s = _refund_session(cid)
        s.refund_case_id = "RFN-20260101-0001"
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is False
            assert r["fast_response_key"] == "refund_already_initiated"
            assert r["refund_case_id"] == "RFN-20260101-0001"
        finally:
            _rm(cid)

    def test_unverified_session_blocked(self):
        cid = "rf-008"
        s = _mk(cid)
        s.otp_verified = False
        s.customer_id = "00000000-0000-0000-0000-000000000001"
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["fast_response_key"] == "verification_required"
        finally:
            _rm(cid)

    @patch("tools.wavvy_tools._db_module.AsyncSessionLocal")
    def test_successful_refund_sets_case_id(self, mock_db_class):
        cid = "rf-009"
        _stub_db(mock_db_class, "failed")
        s = _refund_session(cid)
        try:
            from tools.wavvy_tools import initiate_refund
            r = asyncio.run(initiate_refund("TXN-0001", cid))
            assert r["success"] is True
            assert s.refund_case_id is not None
            assert s.refund_case_id.startswith("RFN-")
        finally:
            _rm(cid)


# =============================================================================
# 9. TRANSACTION STATUS CONSTANTS
# =============================================================================

class TestTransactionConstants:
    def test_core_statuses_defined(self):
        from constants.transaction_status import (
            FAILED, COMPLETED, FLAGGED,
            REFUND_INITIATED, REFUND_PROCESSING, REFUND_COMPLETED,
            KYC_HOLD,
        )
        assert FAILED            == "failed"
        assert COMPLETED         == "completed"
        assert FLAGGED           == "flagged"
        assert REFUND_INITIATED  == "refund_initiated"
        assert REFUND_PROCESSING == "refund_processing"
        assert REFUND_COMPLETED  == "refund_completed"
        assert KYC_HOLD          == "kyc_hold"

    def test_module_imports_cleanly(self):
        import constants.transaction_status as ts
        for attr in ("FAILED", "COMPLETED", "FLAGGED", "REFUND_INITIATED",
                     "REFUND_PROCESSING", "REFUND_COMPLETED", "KYC_HOLD"):
            assert hasattr(ts, attr), f"Missing constant: {attr}"


# =============================================================================
# 10. DB SEED (integration — skip when DB unavailable)
# =============================================================================

class TestSeedData:
    """Hits the real DB. Auto-skipped if the DB isn't reachable."""

    @pytest.mark.asyncio
    async def test_priya_iyer_double_debit_transactions(self):
        try:
            from sqlalchemy import text
            import database as db_mod
            async with db_mod.AsyncSessionLocal() as db:
                r = await db.execute(text("""
                    SELECT t.txn_number, t.status FROM transactions t
                    JOIN customers c ON t.customer_id = c.id
                    WHERE c.phone = '+919812345601'
                """))
                rows = r.mappings().all()
        except Exception:
            pytest.skip("DB not available")
        by_num = {r["txn_number"]: r["status"] for r in rows}
        assert "TXN-1100" in by_num and "TXN-1101" in by_num
        assert by_num["TXN-1100"] == "completed"
        assert by_num["TXN-1101"] == "failed"

    @pytest.mark.asyncio
    async def test_kabir_singh_refund_in_progress(self):
        try:
            from sqlalchemy import text
            import database as db_mod
            async with db_mod.AsyncSessionLocal() as db:
                r = await db.execute(text("""
                    SELECT t.status FROM transactions t
                    JOIN customers c ON t.customer_id = c.id
                    WHERE c.phone = '+918812345602' AND t.txn_number = 'TXN-2200'
                """))
                row = r.mappings().first()
        except Exception:
            pytest.skip("DB not available")
        assert row is not None, "Kabir Singh TXN-2200 missing — run seed.py"
        assert row["status"] == "refund_initiated"

    @pytest.mark.asyncio
    async def test_zara_hussain_completed_dispute(self):
        try:
            from sqlalchemy import text
            import database as db_mod
            async with db_mod.AsyncSessionLocal() as db:
                r = await db.execute(text("""
                    SELECT t.status FROM transactions t
                    JOIN customers c ON t.customer_id = c.id
                    WHERE c.phone = '+917712345603' AND t.txn_number = 'TXN-3300'
                """))
                row = r.mappings().first()
        except Exception:
            pytest.skip("DB not available")
        assert row is not None, "Zara Hussain TXN-3300 missing — run seed.py"
        assert row["status"] == "completed"
