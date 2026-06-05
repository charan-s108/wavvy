import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from coaching import coaching_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/coaching/packs/{agent_id}")
async def get_coaching_packs(agent_id: str):
    """Return all coaching packs for an agent, newest first."""
    try:
        packs = await coaching_manager.get_packs_for_agent(agent_id)
        return packs
    except Exception as e:
        logger.error(f"Error fetching coaching packs for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/coaching/generate/{agent_id}")
async def generate_coaching_pack(agent_id: str):
    """
    Generate a new coaching pack for an agent.
    Requires >= 3 scored calls. Runs synchronously so the result is returned immediately.
    """
    try:
        pack = await coaching_manager.generate_pack(agent_id)
        return pack
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating coaching pack for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/coaching/pack/{pack_id}")
async def get_coaching_pack(pack_id: str):
    """Return a single coaching pack by ID."""
    pack = await coaching_manager.get_pack_by_id(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Coaching pack not found")
    return pack


@router.get("/api/agents")
async def list_agents():
    """Return all agent profiles — used by AgentSelector in supervisor."""
    try:
        from database import AsyncSessionLocal
        from models.agent_profile import AgentProfile
        from models.eval_score import EvalScore
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AgentProfile).order_by(AgentProfile.name)
            )
            agents = result.scalars().all()

            agent_list = []
            for a in agents:
                # Count scored calls for this agent
                count_result = await db.execute(
                    select(func.count()).where(EvalScore.agent_id == a.id)
                )
                scored_calls = count_result.scalar() or 0

                agent_list.append({
                    "agent_id": str(a.id),
                    "name": a.name,
                    "email": a.email,
                    "team": a.team,
                    "status": a.status,
                    "scored_calls": scored_calls,
                })

        return agent_list
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
