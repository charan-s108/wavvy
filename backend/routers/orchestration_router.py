"""
Orchestration REST API — 3 endpoints.

POST /api/orchestration/actions/execute   — execute an approved action (via agent console)
GET  /api/orchestration/actions           — list available actions + metadata
GET  /api/orchestration/history/{call_id} — audit trail for a specific call
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from orchestration.action_registry import (
    ActionExecutionError,
    ActionNotFoundError,
    WorkflowMismatchError,
    list_actions,
)
from orchestration.engine import execute_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


# ── Dependency ──────────────────────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


# ── Schemas ─────────────────────────────────────────────────────────────────

class ExecuteActionRequest(BaseModel):
    action: str
    payload: dict = {}
    approved_by: str
    execution_id: str        # client-generated UUID — idempotency key
    call_id: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/actions/execute")
async def execute_action_endpoint(
    req: ExecuteActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute an approved action. Idempotent — retrying with the same execution_id
    returns the original result without re-executing.
    """
    try:
        result = await execute_action(
            action_name=req.action,
            payload=req.payload,
            approved_by=req.approved_by,
            execution_id=req.execution_id,
            call_id=req.call_id,
            db=db,
        )
        return {"success": True, "action": req.action, **result}
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WorkflowMismatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ActionExecutionError as exc:
        # Handler rejected execution (invalid state) — 409 Conflict
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error executing action %s", req.action)
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")


@router.get("/actions")
async def list_available_actions():
    """Return metadata for all registered actions."""
    return list_actions()


@router.get("/history/{call_id}")
async def get_action_history(call_id: str, db: AsyncSession = Depends(get_db)):
    """Return the audit trail for a specific call."""
    from models.action_audit_log import ActionAuditLog

    result = await db.execute(
        select(ActionAuditLog)
        .where(ActionAuditLog.call_id == call_id)
        .order_by(ActionAuditLog.created_at)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "action": row.action_name,
            "approved_by": row.approved_by,
            "execution_id": row.execution_id,
            "payload": row.payload,
            "result": row.result,
            "success": row.success,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
