"""
Workflow transition table — single source of truth for all tool-outcome routing.

Structure: STEP_TRANSITIONS[tool_name][fast_response_key] → StepTransition

Each StepTransition holds:
  message          — directive returned to the LLM wrapper (what to say / do next)
  requires_consent — if True, wrapper must ask "shall I transfer you?" before escalating
  escalation_team  — team label passed to escalate_to_human reason
  is_terminal      — step cannot be retried; call flow must end or escalate

Coverage across payment industry workflows:
  Identity verification         — account lookup, multi-attempt lock
  OTP authentication            — expiry, wrong code, rate limits
  Transaction status routing    — all 12+ status states
  Refund processing             — all status pre-checks, idempotency
  Account unlock                — regular lock, fraud lock, compliance hold
  Dispute filing                — completed-txn disputes, duplicate, ineligible, high-value
  Fraud reporting               — unauthorized charges, already-reported, reversed
  Payment status checks         — pending, delayed, gateway error, post-debit failure
  Cross-session signals         — high frustration, repeated failures, legal queries
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class StepTransition:
    message: str                           # directive returned to agent_tools wrapper
    requires_consent: bool = False         # if True, ask "shall I transfer?" before escalating
    escalation_team: Optional[str] = None  # label for escalate_to_human reason
    is_terminal: bool = False              # step cannot be retried after this outcome


# ─────────────────────────────────────────────────────────────────────────────
# STEP_TRANSITIONS
# ─────────────────────────────────────────────────────────────────────────────

STEP_TRANSITIONS: dict[str, dict[str, StepTransition]] = {

    # ══════════════════════════════════════════════════════════════════════════
    # IDENTITY VERIFICATION
    # ══════════════════════════════════════════════════════════════════════════
    "verify_account": {
        # First failed lookup — ask customer to confirm number
        "not_found_1": StepTransition(
            message=(
                "Account not found. Tell the customer you couldn't find their account "
                "and ask them to provide their registered phone number again. "
                "As soon as they say any number, call verify_account with it immediately."
            ),
        ),
        # Second failed lookup — offer specialist
        "not_found_max": StepTransition(
            message=(
                "Account not found after two attempts. "
                "Ask: 'I wasn't able to locate your account — would you like me to "
                "connect you with a specialist who can help?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="account-specialist",
        ),
        # Account exists but is suspended (compliance/legal)
        "account_suspended": StepTransition(
            message=(
                "Account is suspended. This requires a manual review. "
                "Ask: 'Your account is currently suspended — I need to connect you "
                "with our compliance team to resolve this. Would you like me to "
                "transfer you now?' Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="compliance-team",
            is_terminal=True,
        ),
        # Account frozen due to suspected security breach
        "account_frozen": StepTransition(
            message=(
                "Account is frozen due to a security hold. "
                "Ask: 'Your account has been temporarily frozen for your protection. "
                "I need to connect you with our security team to assist you directly "
                "— would you like me to transfer you now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="security-team",
            is_terminal=True,
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # OTP AUTHENTICATION
    # ══════════════════════════════════════════════════════════════════════════
    "send_otp": {
        # Resend too soon — code already sent
        "otp_cooldown": StepTransition(
            message=(
                "OTP just sent — cooldown active. Tell the customer: "
                "'I sent that a moment ago — it can take a few seconds to arrive. "
                "Please check your messages.' "
                "Do NOT say you are resending. Do NOT call send_otp again."
            ),
        ),
        # Total send limit for this session reached
        "otp_resend_limit": StepTransition(
            message=(
                "OTP send limit reached for this session. "
                "Ask: 'I've reached the OTP limit — would you like me to connect "
                "you with a specialist who can verify your identity another way?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="identity-specialist",
        ),
    },

    "verify_otp": {
        # Code expired after 5 minutes
        "otp_expired": StepTransition(
            message=(
                "OTP has expired. Tell the customer: 'That code has expired — "
                "I'll send you a fresh one now.' Then call send_otp immediately."
            ),
        ),
        # Wrong code entered — attempts remaining
        "otp_wrong": StepTransition(
            message=(
                "Wrong OTP code. Tell the customer how many attempts remain "
                "and ask them to try again."
            ),
        ),
        # 3 wrong attempts — locked, consent required before escalating
        "otp_max_attempts": StepTransition(
            message=(
                "Three OTP attempts failed. "
                "Ask: 'For your protection, I'd need to connect you with a specialist "
                "who can verify your identity another way — would you like me to "
                "transfer you now?' "
                "Only call escalate_to_human if they say yes. "
                "Do not attempt further OTP sends or verifications."
            ),
            requires_consent=True,
            escalation_team="identity-specialist",
            is_terminal=True,
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # TRANSACTION STATUS ROUTING
    # Status-based outcomes from lookup_transaction.
    # The wrapper maps txn["status"] → "status_{status}" key.
    # ══════════════════════════════════════════════════════════════════════════
    "lookup_transaction": {
        # Transaction not found on this account
        "not_found": StepTransition(
            message=(
                "Transaction not found on this account. Ask the customer to confirm "
                "the ID, or use search_transactions to find it by merchant, amount, or date."
            ),
        ),

        # ── In-flight states ─────────────────────────────────────────────────
        "status_pending": StepTransition(
            message=(
                "Payment is currently being processed. Tell the customer: "
                "'This payment is being processed by the gateway — it typically "
                "takes 30 minutes to 2 hours. If it hasn't cleared by end of day, "
                "call back and we can investigate further.'"
            ),
        ),
        "status_processing": StepTransition(
            message=(
                "Payment is in the final settlement stage. Tell the customer: "
                "'Your payment has been accepted and is in the final settlement "
                "stage — funds should reach the merchant within the next hour.'"
            ),
        ),

        # ── Terminal states ──────────────────────────────────────────────────
        "status_failed": StepTransition(
            message=(
                "Transaction failed — amount may have been deducted but not credited. "
                "Confirm the issue with the customer. "
                "If they confirm the debit, proceed with OTP verification and "
                "then call initiate_refund."
            ),
        ),
        "status_completed": StepTransition(
            message=(
                "Transaction completed successfully. If the customer disputes this charge, "
                "ask: 'Would you like me to file a dispute with our disputes team? "
                "They can investigate whether you received the service.' "
                "Only call raise_dispute if they say yes."
            ),
        ),
        "status_cancelled": StepTransition(
            message=(
                "Transaction was cancelled before settlement. Tell the customer: "
                "'This transaction was cancelled. If any amount was debited, "
                "it will be automatically reversed within 3–5 business days. "
                "If it was debited more than 5 days ago, let me know and I can "
                "escalate for manual review.'"
            ),
        ),
        "status_expired": StepTransition(
            message=(
                "Payment link or session expired before the transaction completed. "
                "Tell the customer: 'This payment session expired before it could "
                "complete. If any amount was debited, it will be reversed automatically "
                "within 3–5 business days. Please initiate a fresh payment.'"
            ),
        ),

        # ── Refund lifecycle ─────────────────────────────────────────────────
        "status_refund_initiated": StepTransition(
            message=(
                "Refund is already in progress. Tell the customer: "
                "'Good news — a refund is already being processed for this transaction. "
                "It typically takes 3–5 business days to appear in your account.'"
            ),
        ),
        "status_refund_processing": StepTransition(
            message=(
                "Refund is currently being transferred back to the account. "
                "Tell the customer: 'Your refund is being transferred right now — "
                "it should reflect in your account within 1–2 business days.'"
            ),
        ),
        "status_refund_completed": StepTransition(
            message=(
                "Refund has already been credited. Tell the customer: "
                "'This refund was processed and credited. If you haven't seen it, "
                "please check with your bank — it can take an extra day to reflect.'"
            ),
        ),

        # ── Hold / review states ─────────────────────────────────────────────
        "status_flagged": StepTransition(
            message=(
                "Transaction is flagged for fraud review. "
                "Ask: 'This transaction is currently under our fraud review process — "
                "I need to connect you with our fraud team to handle this safely. "
                "Shall I transfer you now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="fraud-team",
            is_terminal=True,
        ),
        "status_kyc_hold": StepTransition(
            message=(
                "Transaction is on hold due to a pending KYC verification. "
                "Ask: 'There's a KYC verification hold on your account that's "
                "preventing this transaction from processing. I'd need to connect "
                "you with our KYC specialist to resolve it — would you like me to "
                "transfer you now?' Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="kyc-team",
        ),
        "status_compliance_hold": StepTransition(
            message=(
                "Transaction is under a regulatory/compliance review. "
                "Ask: 'This transaction is under a compliance review that requires "
                "our compliance team to handle directly. Would you like me to "
                "connect you with them now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="compliance-team",
            is_terminal=True,
        ),

        # ── Dispute / chargeback states ──────────────────────────────────────
        "status_disputed": StepTransition(
            message=(
                "A dispute is already open for this transaction. Tell the customer: "
                "'A dispute case is already in progress for this transaction. "
                "Our disputes team will contact you within 5–7 business days with "
                "an update.'"
            ),
        ),
        "status_chargeback_initiated": StepTransition(
            message=(
                "A chargeback has been initiated with the bank or card network. "
                "Ask: 'A chargeback is currently in process for this transaction — "
                "I'd need to connect you with our disputes team who is handling it. "
                "Would you like me to transfer you?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="disputes-team",
        ),
        "status_chargeback_won": StepTransition(
            message=(
                "Chargeback was resolved in the customer's favour. Tell the customer: "
                "'Your chargeback was successful — the funds should have been credited "
                "back to your account. If you haven't received them, please let me know.'"
            ),
        ),
        "status_chargeback_lost": StepTransition(
            message=(
                "Chargeback was denied by the bank. "
                "Ask: 'Unfortunately, the chargeback was not upheld. "
                "I can connect you with our disputes team to discuss your options — "
                "would you like me to transfer you?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="disputes-team",
        ),

        # ── Fraud states ─────────────────────────────────────────────────────
        "status_fraud_reported": StepTransition(
            message=(
                "A fraud report is already filed for this transaction. Tell the customer: "
                "'A fraud investigation is already open for this transaction. "
                "Our fraud team will contact you within 24 hours.'"
            ),
        ),
        "status_fraud_confirmed": StepTransition(
            message=(
                "Fraud has been confirmed on this transaction. Tell the customer: "
                "'Our fraud team has confirmed this as a fraudulent transaction. "
                "The reversal process has been initiated — funds should be credited "
                "within 5–7 business days.'"
            ),
        ),
        "status_fraud_reversed": StepTransition(
            message=(
                "Fraudulent transaction has already been reversed. Tell the customer: "
                "'This fraudulent charge has already been reversed and the funds "
                "credited back. If you haven't seen them, please check with your bank.'"
            ),
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # REFUND PROCESSING
    # ══════════════════════════════════════════════════════════════════════════
    "initiate_refund": {
        # Refund already in progress
        "refund_already_initiated": StepTransition(
            message=(
                "A refund is already underway for this transaction. "
                "Tell the customer: 'Good news — a refund is already being processed. "
                "It typically takes 3–5 business days to appear in your account.'"
            ),
        ),
        # Refund already completed
        "refund_already_completed": StepTransition(
            message=(
                "This refund has already been completed. "
                "Tell the customer: 'This refund was already processed. "
                "If you haven't seen it, please check with your bank — "
                "it may take an extra day to reflect.'"
            ),
        ),
        # Completed transaction — not auto-refundable
        "refund_ineligible": StepTransition(
            message=(
                "Transaction completed successfully — not eligible for an automatic refund. "
                "Tell the customer: 'This payment completed successfully on our end. "
                "For disputes on completed transactions, our disputes team handles these.' "
                "Ask: 'Would you like me to connect you with the disputes team now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="disputes-team",
        ),
        # Flagged transaction — fraud team must clear first
        "fraud_review_required": StepTransition(
            message=(
                "Transaction is under fraud review — cannot process refund until cleared. "
                "Ask: 'This transaction is currently under fraud review. "
                "I need to connect you with our fraud team to handle this safely. "
                "Shall I transfer you now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="fraud-team",
            is_terminal=True,
        ),
        # KYC hold blocking refund
        "kyc_escalation_required": StepTransition(
            message=(
                "Account has an active KYC hold — cannot process refund. "
                "Ask: 'There is a KYC verification hold on this account. "
                "Our KYC team needs to assist you directly before we can proceed. "
                "Would you like me to transfer you now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="kyc-team",
            is_terminal=True,
        ),
        # Duplicate refund attempt in same session
        "session_duplicate": StepTransition(
            message=(
                "A refund was already opened this session. "
                "Tell the customer: 'I've already initiated a refund for this "
                "transaction — it's being processed and should appear in 3–5 "
                "business days.'"
            ),
        ),
        # High-value transaction — needs manual approval
        "high_value_review_required": StepTransition(
            message=(
                "This refund exceeds the automated processing limit and requires "
                "manual approval. Ask: 'Refunds above our automated threshold need "
                "a manual review by a senior specialist. Would you like me to "
                "connect you with them now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="senior-support",
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # ACCOUNT UNLOCK
    # ══════════════════════════════════════════════════════════════════════════
    "unlock_account": {
        # Account is actually already active — might be a password issue
        "already_unlocked": StepTransition(
            message=(
                "Account is already active and unlocked. Tell the customer: "
                "'Your account is currently active. If you're having trouble "
                "logging in, it may be a password issue — would you like me to "
                "help with a password reset, or connect you with technical support?'"
            ),
        ),
        # Account locked due to fraud investigation
        "fraud_lock": StepTransition(
            message=(
                "Account is locked by the fraud team. This requires human review. "
                "Ask: 'Your account has a security hold that requires our security "
                "team to review directly — I cannot lift this through AI support. "
                "Would you like me to connect you with them now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="security-team",
            is_terminal=True,
        ),
        # Account under compliance/AML hold
        "compliance_hold": StepTransition(
            message=(
                "Account is under a compliance hold. "
                "Ask: 'Your account has a regulatory hold that our compliance team "
                "needs to handle directly. Shall I connect you with them now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="compliance-team",
            is_terminal=True,
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # DISPUTE FILING
    # For completed transactions the customer doesn't recognise or received
    # no service for.
    # ══════════════════════════════════════════════════════════════════════════
    "raise_dispute": {
        # Dispute successfully filed
        "dispute_filed": StepTransition(
            message=(
                "Dispute has been filed. Tell the customer: "
                "'Your dispute case has been opened. Our disputes team will "
                "review it within 5–7 business days and contact you on your "
                "registered email. Please note your dispute reference number "
                "for follow-up.'"
            ),
        ),
        # Dispute already filed for this transaction
        "dispute_duplicate": StepTransition(
            message=(
                "A dispute is already open for this transaction. Tell the customer: "
                "'A dispute case is already in progress. Our team will contact you "
                "within 5–7 business days.'"
            ),
        ),
        # Outside the 90-day dispute window
        "dispute_window_expired": StepTransition(
            message=(
                "The dispute window for this transaction has expired. "
                "Ask: 'Unfortunately the standard 90-day dispute window for this "
                "transaction has passed. Our disputes team may have options for "
                "exceptional cases — would you like me to connect you with them?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="disputes-team",
        ),
        # Transaction type or status not eligible for dispute
        "dispute_ineligible": StepTransition(
            message=(
                "This transaction is not eligible for a dispute through this channel. "
                "Ask: 'I'd need to connect you with our disputes team who can explain "
                "the specific reason and explore your options — would you like me to "
                "transfer you?' Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="disputes-team",
        ),
        # High-value dispute needs senior team
        "high_value_manual_required": StepTransition(
            message=(
                "This dispute requires manual review due to the transaction amount. "
                "Ask: 'Disputes above a certain value require review by our senior "
                "disputes team for your protection — would you like me to connect "
                "you with them now?' Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="senior-disputes",
        ),
        # Fraud review in progress — dispute not appropriate yet
        "fraud_review_required": StepTransition(
            message=(
                "Transaction is under active fraud review — a dispute cannot be filed "
                "while fraud review is in progress. "
                "Ask: 'This transaction is already being reviewed by our fraud team — "
                "I need to connect you there for the right resolution. Shall I transfer you?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="fraud-team",
            is_terminal=True,
        ),
        # Refund already in progress — dispute not needed
        "refund_already_initiated": StepTransition(
            message=(
                "A refund is already in progress for this transaction. Tell the customer: "
                "'A refund is already being processed — it should appear within "
                "3–5 business days. A separate dispute isn't needed.'"
            ),
        ),
        # Refund already done — nothing to dispute
        "refund_already_completed": StepTransition(
            message=(
                "Refund already completed for this transaction. Tell the customer: "
                "'This transaction was already refunded. If you have a separate "
                "concern, please let me know and I can help further.'"
            ),
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # FRAUD REPORTING
    # For unauthorised transactions the customer didn't initiate.
    # ══════════════════════════════════════════════════════════════════════════
    "report_fraud": {
        # Case successfully opened
        "fraud_case_opened": StepTransition(
            message=(
                "Fraud report filed. Tell the customer: "
                "'I've opened a fraud investigation for this transaction. "
                "Our fraud team will review your account within 24 hours and "
                "contact you if additional information is needed. "
                "For your safety, consider changing your PIN and reviewing "
                "recent transactions on your account.'"
            ),
        ),
        # Already reported
        "fraud_already_reported": StepTransition(
            message=(
                "This transaction has already been reported as fraud. Tell the customer: "
                "'A fraud case is already open for this transaction. Our fraud team "
                "will contact you within 24 hours.'"
            ),
        ),
        # Already reversed — no action needed
        "fraud_transaction_reversed": StepTransition(
            message=(
                "The fraudulent transaction has already been reversed. Tell the customer: "
                "'Good news — this transaction has already been reversed and the funds "
                "should be back in your account. If you don't see them yet, please "
                "check with your bank as it may take an extra business day to reflect.'"
            ),
        ),
        # Transaction not found
        "transaction_not_found": StepTransition(
            message=(
                "Transaction not found on this account. Ask the customer to confirm "
                "the transaction ID or provide the merchant name, amount, and date "
                "so you can search for it."
            ),
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PAYMENT STATUS CHECK
    # Used when customer says "payment stuck", "money not credited", etc.
    # ══════════════════════════════════════════════════════════════════════════
    "check_payment_status": {
        # Normal processing — within SLA window
        "payment_processing": StepTransition(
            message=(
                "Payment is currently being processed. Tell the customer: "
                "'Your payment is being processed by the payment gateway — "
                "this typically takes 30 minutes to 2 hours. Please check again "
                "after some time. If it still hasn't settled by end of day, "
                "call back and we can investigate further.'"
            ),
        ),
        # Processing but beyond normal SLA — needs investigation
        "payment_processing_delayed": StepTransition(
            message=(
                "Payment has been processing longer than the standard SLA. "
                "Ask: 'This payment has been processing longer than expected — "
                "I'd need to connect you with our payments team to investigate "
                "and ensure the funds are accounted for. Would you like me to "
                "transfer you now?' Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="payments-team",
        ),
        # Payment settled — merchant received funds
        "payment_settled": StepTransition(
            message=(
                "Payment has settled successfully. Tell the customer: "
                "'This payment was successfully settled — the merchant has received "
                "the funds. If you haven't received the service or goods, I can "
                "help you file a dispute.'"
            ),
        ),
        # Amount debited but payment failed — refund eligible
        "payment_failed_post_debit": StepTransition(
            message=(
                "Payment failed after the debit — amount was deducted but didn't "
                "reach the merchant. This is refund-eligible. "
                "Tell the customer: 'Your account was debited but the payment failed "
                "before reaching the merchant — this qualifies for a refund. "
                "Let me verify your identity and process that for you.' "
                "Proceed with send_otp → verify_otp → initiate_refund."
            ),
        ),
        # Amount returned — either cancelled, expired, or bank reversal
        "payment_returned": StepTransition(
            message=(
                "Payment was returned or reversed. Tell the customer: "
                "'This payment was returned — the funds should be back in your "
                "account within 1–2 business days. If they're not reflected, "
                "please call back and we can raise a manual reversal request.'"
            ),
        ),
        # Gateway or technical error
        "gateway_error": StepTransition(
            message=(
                "Payment encountered a technical/gateway error. "
                "Ask: 'There was a technical error during this payment. "
                "I'd like to connect you with our payments team to investigate "
                "and ensure a refund is processed if the amount was deducted. "
                "Would you like me to transfer you now?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="payments-team",
        ),
        # Transaction ID not found
        "transaction_not_found": StepTransition(
            message=(
                "Transaction not found on this account. Ask the customer to confirm "
                "the ID, or use search_transactions to find it by merchant or amount."
            ),
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # CROSS-SESSION SIGNALS
    # Used by the agent when escalation is warranted by session state rather
    # than a specific tool outcome.
    # ══════════════════════════════════════════════════════════════════════════
    "session": {
        # Sentiment-based escalation — customer clearly frustrated
        "high_frustration": StepTransition(
            message=(
                "Customer is showing high frustration. Acknowledge it before anything else. "
                "Say: 'I completely understand how frustrating this is, and I'm sorry "
                "you're going through this.' "
                "Ask: 'Would you like me to connect you with a senior specialist who "
                "can prioritise your case?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="senior-support",
        ),
        # Multiple tool failures in same session
        "repeated_tool_failure": StepTransition(
            message=(
                "Multiple tool failures detected in this session. "
                "Ask: 'I'm running into a technical issue that's preventing me from "
                "resolving this quickly. Would you like me to connect you with a "
                "specialist who has direct system access?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="technical-support",
        ),
        # Legal or regulatory question — out of scope for AI
        "legal_or_regulatory_query": StepTransition(
            message=(
                "Query involves legal or regulatory matters outside AI support scope. "
                "Ask: 'Questions about legal or regulatory matters need to be "
                "handled by our compliance team. Would you like me to connect you "
                "with them?' Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="compliance-team",
            is_terminal=True,
        ),
        # Unusually high-value transaction — enhanced security warranted
        "high_value_transaction_query": StepTransition(
            message=(
                "High-value transaction query. For the customer's security, route to "
                "senior support. Ask: 'Queries involving high-value transactions are "
                "handled by our senior support team for enhanced security — would you "
                "like me to connect you with them?' "
                "Only call escalate_to_human if they say yes."
            ),
            requires_consent=True,
            escalation_team="senior-support",
        ),
        # Customer explicitly requested a human agent
        "customer_requested_human": StepTransition(
            message=(
                "Customer has explicitly asked to speak with a human agent. "
                "Acknowledge and proceed: 'Of course — let me connect you with one "
                "of our specialists right away.' Then call escalate_to_human immediately."
            ),
            escalation_team="support-agent",
            is_terminal=True,
        ),
    },
}
