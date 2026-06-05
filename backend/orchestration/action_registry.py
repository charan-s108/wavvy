"""
Action Registry — all executable operational actions for the HITL orchestration layer.

Each action:
  - validates current state before mutating (raises ActionExecutionError on bad state)
  - updates the relevant DB entity / normalized table
  - returns {"message": str, "updated_entities": dict}
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import select, update as sql_update, text

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────

class ActionExecutionError(Exception):
    """Raised when a handler detects an invalid state or constraint violation."""


class ActionNotFoundError(Exception):
    """Raised when action_name is not in ACTION_REGISTRY."""


class WorkflowMismatchError(Exception):
    """Raised when action is not permitted in the current workflow."""


# ── Action definition ───────────────────────────────────────────────────────

@dataclass
class ActionDefinition:
    name: str
    handler: Callable[[dict, str], Awaitable[dict]]
    requires_approval: bool = True
    risk_level: str = "medium"                    # low | medium | high
    allowed_workflows: list = field(default_factory=list)


# ── Customer lookup helper ───────────────────────────────────────────────────

async def _get_customer(db, customer_id: str):
    from models.customer import Customer
    try:
        cid = uuid.UUID(customer_id)
    except ValueError:
        result = await db.execute(
            select(Customer).where(Customer.phone == customer_id)
        )
        c = result.scalar_one_or_none()
        if not c:
            raise ActionExecutionError(f"Customer not found: {customer_id}")
        return c

    c = await db.get(Customer, cid)
    if not c:
        raise ActionExecutionError(f"Customer not found: {customer_id}")
    return c


# ── Handlers ────────────────────────────────────────────────────────────────

async def _unlock_account(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    if not customer_id:
        raise ActionExecutionError("customer_id required")

    from database import AsyncSessionLocal
    from models.account_hold import AccountHold

    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        if c.account_status == "frozen":
            raise ActionExecutionError(
                "Account has a regulatory freeze — cannot unlock from this console. "
                "Please escalate to compliance team."
            )
        if c.account_status == "active":
            raise ActionExecutionError("Account is already active — no unlock needed.")

        c.account_status = "active"
        c.account_locked_at = None
        c.account_locked_reason = None

        # Lift any active account holds
        await db.execute(
            sql_update(AccountHold)
            .where(AccountHold.customer_id == c.id)
            .where(AccountHold.status == "active")
            .where(AccountHold.hold_type == "manual")
            .values(status="lifted", lifted_at=datetime.now(timezone.utc), lifted_by=f"agent_call_{call_id}")
        )
        await db.commit()

    return {
        "message": f"Account for {c.name} unlocked successfully.",
        "updated_entities": {"account_status": "active", "account_locked": False},
    }


async def _freeze_account(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    reason = payload.get("reason", "fraud_report")
    if not customer_id:
        raise ActionExecutionError("customer_id required")

    from database import AsyncSessionLocal
    from models.account_hold import AccountHold

    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        if c.account_status == "frozen":
            raise ActionExecutionError("Account is already frozen.")

        now = datetime.now(timezone.utc)
        c.account_status = "frozen"
        c.account_locked_at = now
        c.account_locked_reason = reason

        hold = AccountHold(
            customer_id=c.id,
            hold_type="manual",
            status="active",
            reason=reason,
            placed_by=f"agent_call_{call_id}",
            placed_at=now,
            call_id=call_id,
        )
        db.add(hold)
        await db.commit()

    return {
        "message": f"Account for {c.name} frozen. Reason: {reason}.",
        "updated_entities": {"account_status": "frozen", "reason": reason},
    }


async def _remove_fraud_hold(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    if not customer_id:
        raise ActionExecutionError("customer_id required")

    from database import AsyncSessionLocal
    from models.account_hold import AccountHold
    from models.fraud_case import FraudCase

    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        if not c.fraud_hold_active:
            raise ActionExecutionError("No active fraud hold found on this account.")

        now = datetime.now(timezone.utc)
        c.fraud_hold_active = False
        c.fraud_hold_placed_at = None

        # Clear any under_review fraud cases
        await db.execute(
            sql_update(FraudCase)
            .where(FraudCase.customer_id == c.id)
            .where(FraudCase.status == "under_review")
            .values(status="cleared", cleared_at=now, cleared_by=f"agent_call_{call_id}")
        )

        # Lift active fraud holds
        await db.execute(
            sql_update(AccountHold)
            .where(AccountHold.customer_id == c.id)
            .where(AccountHold.status == "active")
            .where(AccountHold.hold_type == "fraud")
            .values(status="lifted", lifted_at=now, lifted_by=f"agent_call_{call_id}")
        )
        await db.commit()

    return {
        "message": f"Fraud hold removed from {c.name}'s account.",
        "updated_entities": {"fraud_hold_active": False},
    }


async def _mark_kyc_verified(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    if not customer_id:
        raise ActionExecutionError("customer_id required")

    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        if c.kyc_status == "verified":
            raise ActionExecutionError("KYC already verified for this customer.")

        c.kyc_status = "verified"
        c.kyc_verified_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "message": f"KYC verified for {c.name}.",
        "updated_entities": {"kyc_status": "verified"},
    }


async def _issue_refund(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    txn_number  = payload.get("order_id") or payload.get("txn_number")
    amount      = payload.get("amount")
    if not customer_id or not txn_number:
        raise ActionExecutionError("customer_id and txn_number (or order_id) required")

    from database import AsyncSessionLocal
    from models.transaction import Transaction
    from models.refund import Refund
    from utils.ref_numbers import next_rfn_number

    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        # Find the transaction
        result = await db.execute(
            select(Transaction)
            .where(Transaction.customer_id == c.id)
            .where(Transaction.txn_number == txn_number.upper())
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise ActionExecutionError(f"Transaction {txn_number} not found for this customer.")

        # Check for existing refund
        result = await db.execute(
            select(Refund).where(Refund.transaction_id == txn.id)
        )
        existing_refund = result.scalar_one_or_none()
        if existing_refund:
            raise ActionExecutionError(
                f"Transaction {txn_number} already has a refund ({existing_refund.rfn_number})."
            )

        refund_amount = amount or float(txn.amount)
        rfn_number = await next_rfn_number(db)

        txn.status = "refund_initiated"

        refund = Refund(
            rfn_number=rfn_number,
            transaction_id=txn.id,
            customer_id=c.id,
            amount=refund_amount,
            reason="agent_approved_refund",
            status="initiated",
            initiated_by=f"agent_call_{call_id}",
            call_id=call_id,
        )
        db.add(refund)
        await db.commit()

    return {
        "message": f"Refund of ₹{refund_amount} issued for {txn_number}. Reference: {rfn_number}.",
        "updated_entities": {"txn_number": txn_number, "rfn_number": rfn_number, "refunded": True},
    }


async def _reopen_dispute(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    txn_number  = payload.get("order_id") or payload.get("txn_number")
    if not customer_id or not txn_number:
        raise ActionExecutionError("customer_id and txn_number (or order_id) required")

    from database import AsyncSessionLocal
    from models.transaction import Transaction
    from models.dispute import Dispute
    from utils.ref_numbers import next_dsp_number

    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        result = await db.execute(
            select(Transaction)
            .where(Transaction.customer_id == c.id)
            .where(Transaction.txn_number == txn_number.upper())
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise ActionExecutionError(f"Transaction {txn_number} not found.")

        # Check existing open dispute
        result = await db.execute(
            select(Dispute)
            .where(Dispute.transaction_id == txn.id)
            .where(Dispute.status == "open")
        )
        if result.scalar_one_or_none():
            raise ActionExecutionError(f"Dispute already open for {txn_number}.")

        dsp_number = await next_dsp_number(db)
        txn.status = "disputed"

        dispute = Dispute(
            dsp_number=dsp_number,
            transaction_id=txn.id,
            customer_id=c.id,
            reason="agent_reopened_dispute",
            status="open",
            filed_via=f"agent_call_{call_id}",
            call_id=call_id,
        )
        db.add(dispute)
        await db.commit()

    return {
        "message": f"Dispute reopened for {txn_number}. Reference: {dsp_number}.",
        "updated_entities": {"txn_number": txn_number, "dsp_number": dsp_number, "dispute_open": True},
    }


async def _reset_2fa(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    if not customer_id:
        raise ActionExecutionError("customer_id required")

    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)
        c.two_fa_last_reset_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "message": f"2FA reset for {c.name}. They will need to re-enroll on next login.",
        "updated_entities": {"two_fa_reset": True},
    }


async def _escalate_fraud_team(payload: dict, call_id: str) -> dict:
    customer_id = payload.get("customer_id")
    reason      = payload.get("reason", "Unresolved fraud concern")
    txn_number  = payload.get("txn_number")
    if not customer_id:
        raise ActionExecutionError("customer_id required")

    from database import AsyncSessionLocal
    from models.fraud_case import FraudCase
    from models.transaction import Transaction
    from utils.ref_numbers import next_fraud_number

    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)

        if c.fraud_team_escalated:
            raise ActionExecutionError("Case already escalated to fraud team.")

        now = datetime.now(timezone.utc)
        c.fraud_team_escalated = True
        c.fraud_team_escalated_at = now

        # Resolve optional transaction reference
        txn_id = None
        if txn_number:
            result = await db.execute(
                select(Transaction)
                .where(Transaction.customer_id == c.id)
                .where(Transaction.txn_number == txn_number.upper())
            )
            txn = result.scalar_one_or_none()
            if txn:
                txn_id = txn.id

        fraud_number = await next_fraud_number(db)
        fraud_case = FraudCase(
            fraud_number=fraud_number,
            customer_id=c.id,
            transaction_id=txn_id,
            fraud_type="unresolved_concern",
            status="under_review",
            risk_level="high",
            reported_via=f"agent_call_{call_id}",
            call_id=call_id,
            notes=reason,
        )
        db.add(fraud_case)
        await db.commit()

    return {
        "message": f"Case escalated to fraud team for {c.name}. Reference: {fraud_number}. Reason: {reason}.",
        "updated_entities": {"fraud_team_escalated": True, "fraud_number": fraud_number},
    }


async def _send_otp_to_customer(payload: dict, call_id: str) -> dict:
    """Send OTP to the verified customer's phone. Reuses the voice-pipeline OTP mechanism."""
    from tools.wavvy_tools import send_otp
    result = await send_otp(call_id)
    if not result.get("success"):
        key = result.get("fast_response_key", "error")
        if key == "otp_cooldown":
            raise ActionExecutionError("OTP was sent recently — wait 60 seconds before resending.")
        if key == "otp_resend_limit":
            raise ActionExecutionError("Max OTP resend attempts reached for this call.")
        raise ActionExecutionError(f"Could not send OTP: {key}")
    otp_code = result.get("otp", "")
    return {
        "message": f"OTP sent. Code: {otp_code} — ask the customer to read this back to you to verify identity.",
        "otp_code": otp_code,
        "updated_entities": {"otp_status": "sent"},
    }


async def _verify_customer_otp(payload: dict, call_id: str) -> dict:
    """Verify OTP code entered by the specialist after the customer reads it aloud."""
    from tools.wavvy_tools import verify_otp
    otp_code = str(payload.get("otp_code", "")).strip()
    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        raise ActionExecutionError("OTP code must be exactly 6 digits.")
    result = await verify_otp(otp_code, call_id)
    if result.get("success"):
        return {
            "message": "Customer identity verified via OTP. Sensitive actions are now unlocked for this call.",
            "updated_entities": {"otp_verified": True},
        }
    key = result.get("fast_response_key", "error")
    if key == "otp_wrong":
        raise ActionExecutionError(f"Incorrect OTP. {result.get('attempts_left', 0)} attempt(s) left.")
    if key == "otp_max_attempts":
        raise ActionExecutionError("Max OTP attempts reached. Send a new OTP to try again.")
    if key == "otp_expired":
        raise ActionExecutionError("OTP expired. Send a new OTP.")
    raise ActionExecutionError(f"OTP verification failed: {key}")


async def _update_account_info(payload: dict, call_id: str) -> dict:
    """Update a customer's account information. Allowed fields: email, name."""
    customer_id = payload.get("customer_id")
    field = payload.get("field", "").strip().lower()
    value = payload.get("value", "").strip()
    if not customer_id:
        raise ActionExecutionError("customer_id required")
    if field not in {"email", "name"}:
        raise ActionExecutionError(f"Cannot update '{field}'. Only 'email' and 'name' are allowed.")
    if not value:
        raise ActionExecutionError("Value cannot be empty.")

    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        c = await _get_customer(db, customer_id)
        old_value = getattr(c, field, None)
        setattr(c, field, value)
        await db.commit()
        await db.refresh(c)

    return {
        "message": f"Account {field} updated from '{old_value}' to '{value}' for {c.name}.",
        "updated_entities": {"customer": {field: value}},
    }


# ── Registry ────────────────────────────────────────────────────────────────

ACTION_REGISTRY: dict[str, ActionDefinition] = {
    "unlock_account": ActionDefinition(
        name="unlock_account",
        handler=_unlock_account,
        risk_level="low",
        allowed_workflows=["account_access", "fraud_report"],
    ),
    "freeze_account": ActionDefinition(
        name="freeze_account",
        handler=_freeze_account,
        risk_level="high",
        allowed_workflows=["fraud_report"],
    ),
    "remove_fraud_hold": ActionDefinition(
        name="remove_fraud_hold",
        handler=_remove_fraud_hold,
        risk_level="medium",
        allowed_workflows=["fraud_report"],
    ),
    "mark_kyc_verified": ActionDefinition(
        name="mark_kyc_verified",
        handler=_mark_kyc_verified,
        risk_level="medium",
        allowed_workflows=["kyc_issue"],
    ),
    "issue_refund": ActionDefinition(
        name="issue_refund",
        handler=_issue_refund,
        risk_level="high",
        allowed_workflows=["payment_failure"],
    ),
    "reopen_dispute": ActionDefinition(
        name="reopen_dispute",
        handler=_reopen_dispute,
        risk_level="medium",
        allowed_workflows=["payment_failure", "fraud_report"],
    ),
    "reset_2fa": ActionDefinition(
        name="reset_2fa",
        handler=_reset_2fa,
        risk_level="medium",
        allowed_workflows=["account_access"],
    ),
    "escalate_fraud_team": ActionDefinition(
        name="escalate_fraud_team",
        handler=_escalate_fraud_team,
        risk_level="low",
        allowed_workflows=["fraud_report"],
    ),
    "send_otp_to_customer": ActionDefinition(
        name="send_otp_to_customer",
        handler=_send_otp_to_customer,
        requires_approval=False,
        risk_level="low",
        allowed_workflows=["account_access", "payment_failure", "fraud_report", "kyc_issue"],
    ),
    "verify_customer_otp": ActionDefinition(
        name="verify_customer_otp",
        handler=_verify_customer_otp,
        requires_approval=False,
        risk_level="low",
        allowed_workflows=["account_access", "payment_failure", "fraud_report", "kyc_issue"],
    ),
    "update_account_info": ActionDefinition(
        name="update_account_info",
        handler=_update_account_info,
        requires_approval=True,
        risk_level="medium",
        allowed_workflows=["account_access", "general_inquiry"],
    ),
}


def get_action(name: str) -> ActionDefinition:
    defn = ACTION_REGISTRY.get(name)
    if not defn:
        raise ActionNotFoundError(f"Unknown action: {name!r}")
    return defn


def list_actions() -> list[dict]:
    return [
        {
            "name": d.name,
            "risk": d.risk_level,
            "requires_approval": d.requires_approval,
            "workflows": d.allowed_workflows,
        }
        for d in ACTION_REGISTRY.values()
    ]
