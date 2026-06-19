import logging
import uuid
from datetime import datetime, timezone

from database import AsyncSessionLocal
from models.coaching_pack import CoachingPack
from models.eval_score import EvalScore
from sqlalchemy import select, text

logger = logging.getLogger(__name__)

MIN_CALLS_REQUIRED = 3


# ── Voice AI eval fetching ────────────────────────────────────────────────────

async def get_voice_ai_evals(limit: int = 20) -> list[dict]:
    """Fetch the last `limit` scored Voice AI calls (agent_id IS NULL = AI-handled)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EvalScore)
            .where(EvalScore.agent_id == None)
            .order_by(EvalScore.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {
                "call_id":            str(r.call_id),
                "guardrail_adherence": r.guardrail_adherence,
                "resolution_rate":    r.resolution_rate,
                "containment":        r.containment,
                "caller_satisfaction": r.caller_satisfaction,
                "handle_time_score":  r.handle_time_score,
                "disclosure_score":   r.disclosure_score,
                "overall_score":      r.overall_score,
                "pass_fail":          r.pass_fail,
                "violations":         r.violations,
                "strengths":          r.strengths,
                "coaching_note":      r.coaching_note,
                "created_at":         r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


async def get_voice_ai_stats() -> dict:
    """Aggregate performance stats for the Voice AI coaching overview panel."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("""
                SELECT
                    COUNT(*)                                                                   AS total_scored,
                    ROUND(AVG(overall_score))                                                  AS avg_score,
                    ROUND(AVG(CASE WHEN pass_fail = 'PASS' THEN 1 ELSE 0 END)::NUMERIC, 2)    AS pass_rate,
                    ROUND(AVG(guardrail_adherence))                                            AS avg_guardrail,
                    ROUND(AVG(resolution_rate))                                                AS avg_resolution,
                    ROUND(AVG(containment))                                                    AS avg_containment,
                    ROUND(AVG(caller_satisfaction)::NUMERIC, 2)                                AS avg_satisfaction,
                    ROUND(AVG(CASE WHEN created_at >= NOW() - INTERVAL '7 days'
                                   THEN overall_score END))                                    AS avg_score_7d,
                    ROUND(AVG(CASE WHEN created_at >= NOW() - INTERVAL '14 days'
                                    AND created_at <  NOW() - INTERVAL '7 days'
                                   THEN overall_score END))                                    AS avg_score_prev_7d
                FROM eval_scores
                WHERE agent_id IS NULL
            """)
        )
        row = r.mappings().first()

    total_scored    = int(row["total_scored"] or 0)
    avg_score       = int(row["avg_score"])       if row["avg_score"]       else None
    pass_rate       = float(row["pass_rate"])     if row["pass_rate"]       else 0.0
    avg_guardrail   = int(row["avg_guardrail"])   if row["avg_guardrail"]   else None
    avg_resolution  = int(row["avg_resolution"])  if row["avg_resolution"]  else None
    avg_containment = int(row["avg_containment"]) if row["avg_containment"] else None
    avg_satisfaction = float(row["avg_satisfaction"]) if row["avg_satisfaction"] else None
    avg_7d          = int(row["avg_score_7d"])      if row["avg_score_7d"]      else None
    avg_prev_7d     = int(row["avg_score_prev_7d"]) if row["avg_score_prev_7d"] else None

    trend = "stable"
    if avg_7d is not None and avg_prev_7d is not None:
        diff = avg_7d - avg_prev_7d
        if diff >= 3:
            trend = "improving"
        elif diff <= -3:
            trend = "declining"

    return {
        "total_scored":     total_scored,
        "avg_score":        avg_score,
        "pass_rate":        pass_rate,
        "avg_guardrail":    avg_guardrail,
        "avg_resolution":   avg_resolution,
        "avg_containment":  avg_containment,
        "avg_satisfaction": avg_satisfaction,
        "avg_score_7d":     avg_7d,
        "trend":            trend,
        "can_generate":     total_scored >= MIN_CALLS_REQUIRED,
        "calls_needed":     max(0, MIN_CALLS_REQUIRED - total_scored),
    }


# ── Pack generation ───────────────────────────────────────────────────────────

async def generate_voice_ai_pack() -> dict:
    """
    Generate a coaching pack analyzing Voice AI performance.
    Requires >= 3 scored AI calls. agent_id is NULL for Voice AI packs.
    """
    from agents.coaching_agent import generate_coaching_pack

    evals = await get_voice_ai_evals()
    if len(evals) < MIN_CALLS_REQUIRED:
        raise ValueError(
            f"Not enough scored Voice AI calls. "
            f"Need at least {MIN_CALLS_REQUIRED}, found {len(evals)}."
        )

    pack_data = await generate_coaching_pack("Voice AI", evals)

    pack = CoachingPack(
        agent_id=None,
        calls_analyzed=pack_data["score_summary"]["calls_analyzed"],
        overall_trend=pack_data.get("overall_trend", "stable"),
        strengths=pack_data.get("strengths", []),
        improvements=pack_data.get("improvements", []),
        action_items=pack_data.get("action_items", []),
        score_summary=pack_data.get("score_summary", {}),
    )

    async with AsyncSessionLocal() as db:
        db.add(pack)
        await db.commit()
        await db.refresh(pack)

    return {
        "pack_id":      str(pack.id),
        "generated_at": pack.generated_at.isoformat(),
        **pack_data,
    }


async def get_voice_ai_packs() -> list[dict]:
    """Return all Voice AI coaching packs (agent_id IS NULL), newest first."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CoachingPack)
            .where(CoachingPack.agent_id == None)
            .order_by(CoachingPack.generated_at.desc())
        )
        rows = result.scalars().all()
        return [
            {
                "pack_id":        str(r.id),
                "generated_at":   r.generated_at.isoformat() if r.generated_at else None,
                "calls_analyzed": r.calls_analyzed,
                "overall_trend":  r.overall_trend,
                "strengths":      r.strengths,
                "improvements":   r.improvements,
                "action_items":   r.action_items,
                "score_summary":  r.score_summary,
            }
            for r in rows
        ]


async def get_pack_by_id(pack_id: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CoachingPack).where(CoachingPack.id == uuid.UUID(pack_id))
        )
        pack = result.scalar_one_or_none()
        if not pack:
            return None
        return {
            "pack_id":        str(pack.id),
            "generated_at":   pack.generated_at.isoformat() if pack.generated_at else None,
            "calls_analyzed": pack.calls_analyzed,
            "overall_trend":  pack.overall_trend,
            "strengths":      pack.strengths,
            "improvements":   pack.improvements,
            "action_items":   pack.action_items,
            "score_summary":  pack.score_summary,
        }
