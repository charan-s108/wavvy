"""
Orchestration Execution Engine.

Responsibilities:
  1. Idempotency check — replay cached result if execution_id already seen
  2. Action lookup + workflow compatibility validation
  3. Handler execution with error capture
  4. INC + RES ticket creation for every successful action
  5. Immutable audit log write (always, even on failure)

Usage:
    result = await execute_action(
        action_name="unlock_account",
        payload={"customer_id": "CUST-1001"},
        approved_by="agent_882",
        execution_id="<uuid>",
        call_id="CALL-123",
        db=async_session,
    )
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestration.action_registry import (
    ACTION_REGISTRY,
    ActionDefinition,
    ActionExecutionError,
    ActionNotFoundError,
    WorkflowMismatchError,
    get_action,
)

logger = logging.getLogger(__name__)

# Map action name → INC incident type
_ACTION_INC_TYPE: dict[str, str] = {
    "unlock_account":     "account_access",
    "freeze_account":     "account_access",
    "remove_fraud_hold":  "fraud_report",
    "mark_kyc_verified":  "kyc_issue",
    "issue_refund":       "payment_failure",
    "reopen_dispute":     "payment_failure",
    "reset_2fa":          "account_access",
    "escalate_fraud_team": "fraud_report",
}


async def execute_action(
    action_name: str,
    payload: dict,
    approved_by: str,
    execution_id: str,
    call_id: str,
    db: AsyncSession,
) -> dict:
    """
    Execute an approved orchestration action.

    Returns the execution result dict on success.
    Raises ActionNotFoundError, WorkflowMismatchError, or ActionExecutionError on failure.
    The audit log is written in all cases (success AND failure).
    """
    from models.action_audit_log import ActionAuditLog

    # 1. Idempotency check — return cached result if execution_id already used
    existing = await db.execute(
        select(ActionAuditLog).where(ActionAuditLog.execution_id == execution_id)
    )
    prior = existing.scalar_one_or_none()
    if prior:
        logger.info("[%s] Replaying idempotent result for execution_id %s", call_id, execution_id)
        return prior.result

    # 2. Validate action exists
    defn = get_action(action_name)   # raises ActionNotFoundError if missing

    # 3. Validate workflow compatibility
    from session.call_session import ACTIVE_CALLS
    session = ACTIVE_CALLS.get(call_id)
    if session:
        workflow_type = getattr(session, "workflow_type", None) or _infer_workflow(session)
        if (
            workflow_type
            and defn.allowed_workflows
            and workflow_type not in defn.allowed_workflows
        ):
            raise WorkflowMismatchError(
                f"Action '{action_name}' is not allowed in workflow '{workflow_type}'. "
                f"Allowed: {defn.allowed_workflows}"
            )

    # 4. Execute handler
    result: dict = {}
    success = True
    error_msg: str | None = None
    try:
        result = await defn.handler(payload, call_id)
        result.setdefault("success", True)
    except ActionExecutionError as exc:
        success = False
        error_msg = str(exc)
        result = {"success": False, "message": error_msg}
        logger.warning("[%s] Action %s failed validation: %s", call_id, action_name, exc)
    except Exception as exc:
        success = False
        error_msg = f"Unexpected error: {exc}"
        result = {"success": False, "message": error_msg}
        logger.exception("[%s] Action %s raised unexpectedly", call_id, action_name)

    # 5. Create INC + RES tickets for successful actions
    inc_number: str | None = None
    res_number: str | None = None
    if success:
        try:
            inc_number, res_number = await _create_inc_res(
                db=db,
                action_name=action_name,
                payload=payload,
                approved_by=approved_by,
                call_id=call_id,
                action_result=result,
            )
            result["inc_number"] = inc_number
            result["res_number"] = res_number
        except Exception as ticket_err:
            logger.warning("[%s] INC/RES creation failed (non-fatal): %s", call_id, ticket_err)

    # 6. Write immutable audit log (always)
    log_entry = ActionAuditLog(
        call_id=call_id,
        action_name=action_name,
        approved_by=approved_by,
        execution_id=execution_id,
        payload=payload,
        result=result,
        success=success,
    )
    db.add(log_entry)
    try:
        await db.commit()
    except Exception as commit_err:
        logger.error("[%s] Failed to write audit log: %s", call_id, commit_err)
        await db.rollback()

    # 7. Re-raise on failure so the router/ws handler returns error to frontend
    if not success:
        raise ActionExecutionError(error_msg or "Action failed")

    return result


def _infer_workflow(session) -> str | None:
    """
    Infer workflow type from session state when not explicitly set.
    Looks at the workflow object if present, otherwise returns None.
    """
    if not session:
        return None
    wf = getattr(session, "workflow", None)
    if wf:
        return getattr(wf, "workflow_type", None) or getattr(wf, "intent", None)
    return None


async def _create_inc_res(
    db: AsyncSession,
    action_name: str,
    payload: dict,
    approved_by: str,
    call_id: str,
    action_result: dict,
) -> tuple[str, str]:
    """
    Create one Incident (INC-XXXX) and one Resolution (RES-YYYY-NNNN) for
    an approved action execution. Both are committed inside execute_action's
    outer commit so they are always consistent with the audit log.

    Returns (inc_number, res_number).
    """
    from models.agent_profile import AgentProfile
    from models.customer import Customer
    from models.incident import Incident
    from models.resolution import Resolution
    from utils.ref_numbers import next_inc_number, next_res_number

    now = datetime.now(timezone.utc)

    # Resolve customer UUID from payload (may be UUID string or phone)
    customer_id_raw = payload.get("customer_id")
    customer_uuid: uuid.UUID | None = None
    if customer_id_raw:
        try:
            customer_uuid = uuid.UUID(customer_id_raw)
        except ValueError:
            # phone number — look up
            r = await db.execute(
                select(Customer).where(Customer.phone == customer_id_raw)
            )
            c = r.scalar_one_or_none()
            if c:
                customer_uuid = c.id

    # Resolve agent UUID from approved_by (email)
    agent_uuid: uuid.UUID | None = None
    if approved_by and "@" in approved_by:
        r = await db.execute(
            select(AgentProfile).where(AgentProfile.email == approved_by)
        )
        a = r.scalar_one_or_none()
        if a:
            agent_uuid = a.id

    inc_type = _ACTION_INC_TYPE.get(action_name, "general")
    inc_number = await next_inc_number(db)

    incident = Incident(
        inc_number=inc_number,
        customer_id=customer_uuid,
        call_id=call_id,
        inc_type=inc_type,
        status="resolved",
        priority="medium",
        description=action_result.get("message", action_name),
        resolved_at=now,
    )
    db.add(incident)
    # Flush to get incident.id before creating the Resolution FK
    await db.flush()

    res_number = await next_res_number(db)
    resolution = Resolution(
        res_number=res_number,
        call_id=call_id,
        customer_id=customer_uuid,
        incident_id=incident.id,
        agent_id=agent_uuid,
        action_taken=action_result.get("message", action_name),
        action_types=[action_name],
        resolved_at=now,
    )
    db.add(resolution)

    # Update the Incident with the resolution reference
    incident.resolution_ref = res_number

    logger.info(
        "[%s] Created %s + %s for action=%s approved_by=%s",
        call_id, inc_number, res_number, action_name, approved_by,
    )
    return inc_number, res_number
