import logging
import uuid
from datetime import datetime, timezone

from database import AsyncSessionLocal
from models.coaching_pack import CoachingPack
from models.eval_score import EvalScore
from models.agent_profile import AgentProfile
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

MIN_CALLS_REQUIRED = 3


async def get_agent_evals(agent_id: str, limit: int = 20) -> list[dict]:
    """Fetch the last `limit` scored calls for an agent."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EvalScore)
            .where(EvalScore.agent_id == uuid.UUID(agent_id))
            .order_by(EvalScore.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {
                "call_id": str(r.call_id),
                "guardrail_adherence": r.guardrail_adherence,
                "resolution_rate": r.resolution_rate,
                "containment": r.containment,
                "caller_satisfaction": r.caller_satisfaction,
                "handle_time_score": r.handle_time_score,
                "disclosure_score": r.disclosure_score,
                "overall_score": r.overall_score,
                "pass_fail": r.pass_fail,
                "violations": r.violations,
                "strengths": r.strengths,
                "coaching_note": r.coaching_note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


async def get_agent_name(agent_id: str) -> str:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.id == uuid.UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        return agent.name if agent else "Unknown Agent"


async def generate_pack(agent_id: str) -> dict:
    """
    Generate a coaching pack for an agent.
    Requires >= 3 scored calls. Returns the saved pack as a dict.
    """
    from agents.coaching_agent import generate_coaching_pack

    evals = await get_agent_evals(agent_id)
    if len(evals) < MIN_CALLS_REQUIRED:
        raise ValueError(
            f"Not enough scored calls to generate a coaching pack. "
            f"Need at least {MIN_CALLS_REQUIRED}, found {len(evals)}."
        )

    agent_name = await get_agent_name(agent_id)
    pack_data = await generate_coaching_pack(agent_name, evals)

    # Persist to DB
    pack = CoachingPack(
        agent_id=uuid.UUID(agent_id),
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
        "pack_id": str(pack.id),
        "agent_id": agent_id,
        "agent_name": agent_name,
        "generated_at": pack.generated_at.isoformat(),
        **pack_data,
    }


async def get_packs_for_agent(agent_id: str) -> list[dict]:
    """Return all coaching packs for an agent, newest first."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CoachingPack)
            .where(CoachingPack.agent_id == uuid.UUID(agent_id))
            .order_by(CoachingPack.generated_at.desc())
        )
        rows = result.scalars().all()
        agent_name = await get_agent_name(agent_id)
        return [
            {
                "pack_id": str(r.id),
                "agent_id": agent_id,
                "agent_name": agent_name,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "calls_analyzed": r.calls_analyzed,
                "overall_trend": r.overall_trend,
                "strengths": r.strengths,
                "improvements": r.improvements,
                "action_items": r.action_items,
                "score_summary": r.score_summary,
            }
            for r in rows
        ]


async def get_pack_by_id(pack_id: str) -> dict | None:
    """Return a single coaching pack by ID."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CoachingPack).where(CoachingPack.id == uuid.UUID(pack_id))
        )
        pack = result.scalar_one_or_none()
        if not pack:
            return None
        agent_name = await get_agent_name(str(pack.agent_id))
        return {
            "pack_id": str(pack.id),
            "agent_id": str(pack.agent_id),
            "agent_name": agent_name,
            "generated_at": pack.generated_at.isoformat() if pack.generated_at else None,
            "calls_analyzed": pack.calls_analyzed,
            "overall_trend": pack.overall_trend,
            "strengths": pack.strengths,
            "improvements": pack.improvements,
            "action_items": pack.action_items,
            "score_summary": pack.score_summary,
        }
