"""
/api/eval — QA score retrieval and manual trigger.

GET  /api/eval/{call_id}          — fetch scores for a call
POST /api/eval/trigger/{call_id}  — manually re-trigger QA scoring
GET  /api/eval/agent/{agent_id}   — all scores for an agent
"""
import uuid
import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlalchemy import text

from database import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.get("/{call_id}")
async def get_eval(call_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""SELECT e.*, c.started_at, c.duration_secs, c.resolution
                    FROM eval_scores e
                    JOIN calls c ON c.id = e.call_id
                    WHERE e.call_id = :cid
                    ORDER BY e.created_at DESC
                    LIMIT 1"""),
            {"cid": uuid.UUID(call_id)},
        )
        row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="No eval score found for this call")

    return {
        "call_id": call_id,
        "guardrail_adherence": row["guardrail_adherence"],
        "resolution_rate":     row["resolution_rate"],
        "containment":         row["containment"],
        "caller_satisfaction": float(row["caller_satisfaction"]) if row["caller_satisfaction"] else None,
        "handle_time_score":   row["handle_time_score"],
        "disclosure_score":    row["disclosure_score"],
        "overall_score":       row["overall_score"],
        "pass_fail":           row["pass_fail"],
        "violations":          row["violations"] or [],
        "coaching_note":       row["coaching_note"],
        "strengths":           row["strengths"] or [],
        "created_at":          row["created_at"].isoformat() if row["created_at"] else None,
        "call_started_at":     row["started_at"].isoformat() if row["started_at"] else None,
        "call_duration_secs":  row["duration_secs"],
        "call_resolution":     row["resolution"],
    }


@router.post("/trigger/{call_id}")
async def trigger_eval(call_id: str, background_tasks: BackgroundTasks):
    """Manually re-trigger QA scoring for a call."""
    from agents.qa_agent import score_call
    background_tasks.add_task(score_call, call_id)
    return {"status": "triggered", "call_id": call_id}


@router.get("/agent/{agent_id}")
async def agent_evals(agent_id: str, limit: int = 20):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""SELECT e.call_id, e.overall_score, e.pass_fail,
                           e.guardrail_adherence, e.resolution_rate, e.containment,
                           e.caller_satisfaction, e.coaching_note, e.violations,
                           e.strengths, e.created_at,
                           c.started_at, c.duration_secs
                    FROM eval_scores e
                    JOIN calls c ON c.id = e.call_id
                    WHERE e.agent_id = :aid
                    ORDER BY e.created_at DESC
                    LIMIT :lim"""),
            {"aid": uuid.UUID(agent_id), "lim": limit},
        )
        rows = result.mappings().all()

    return [
        {
            "call_id":            str(r["call_id"]),
            "overall_score":      r["overall_score"],
            "pass_fail":          r["pass_fail"],
            "guardrail_adherence": r["guardrail_adherence"],
            "resolution_rate":    r["resolution_rate"],
            "containment":        r["containment"],
            "caller_satisfaction": float(r["caller_satisfaction"]) if r["caller_satisfaction"] else None,
            "coaching_note":      r["coaching_note"],
            "violations":         r["violations"] or [],
            "strengths":          r["strengths"] or [],
            "created_at":         r["created_at"].isoformat() if r["created_at"] else None,
            "call_started_at":    r["started_at"].isoformat() if r["started_at"] else None,
            "call_duration_secs": r["duration_secs"],
        }
        for r in rows
    ]


@router.get("/recent/all")
async def recent_evals(limit: int = 30):
    """All recent eval scores across all calls — used by admin QA page."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""SELECT e.call_id, e.overall_score, e.pass_fail,
                           e.guardrail_adherence, e.resolution_rate, e.containment,
                           e.caller_satisfaction, e.coaching_note, e.violations,
                           e.strengths, e.created_at,
                           c.started_at, c.duration_secs, c.resolution,
                           cu.name AS customer_name, cu.account_type
                    FROM eval_scores e
                    JOIN calls c ON c.id = e.call_id
                    LEFT JOIN customers cu ON cu.id = c.customer_id
                    ORDER BY e.created_at DESC
                    LIMIT :lim"""),
            {"lim": limit},
        )
        rows = result.mappings().all()

    return [
        {
            "call_id":            str(r["call_id"]),
            "customer_name":      r["customer_name"],
            "overall_score":      r["overall_score"],
            "pass_fail":          r["pass_fail"],
            "guardrail_adherence": r["guardrail_adherence"],
            "resolution_rate":    r["resolution_rate"],
            "containment":        r["containment"],
            "caller_satisfaction": float(r["caller_satisfaction"]) if r["caller_satisfaction"] else None,
            "coaching_note":      r["coaching_note"],
            "violations":         r["violations"] or [],
            "strengths":          r["strengths"] or [],
            "created_at":         r["created_at"].isoformat() if r["created_at"] else None,
            "call_started_at":    r["started_at"].isoformat() if r["started_at"] else None,
            "call_duration_secs": r["duration_secs"],
            "call_resolution":    r["resolution"],
        }
        for r in rows
    ]
