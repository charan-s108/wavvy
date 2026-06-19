import logging
from fastapi import APIRouter, HTTPException

from coaching import coaching_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Voice AI coaching (primary) ───────────────────────────────────────────────

@router.get("/api/coaching/voice-ai/stats")
async def voice_ai_stats():
    """Aggregate performance stats for all Voice AI scored calls."""
    try:
        return await coaching_manager.get_voice_ai_stats()
    except Exception as e:
        logger.error(f"Error fetching Voice AI coaching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/coaching/voice-ai/packs")
async def voice_ai_packs():
    """Return all Voice AI coaching packs, newest first."""
    try:
        return await coaching_manager.get_voice_ai_packs()
    except Exception as e:
        logger.error(f"Error fetching Voice AI coaching packs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/coaching/voice-ai/generate")
async def generate_voice_ai_pack():
    """
    Generate a new Voice AI coaching pack from the most recent scored calls.
    Requires >= 3 scored Voice AI calls (agent_id IS NULL in eval_scores).
    """
    try:
        return await coaching_manager.generate_voice_ai_pack()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating Voice AI coaching pack: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/coaching/pack/{pack_id}")
async def get_coaching_pack(pack_id: str):
    """Return a single coaching pack by ID."""
    pack = await coaching_manager.get_pack_by_id(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Coaching pack not found")
    return pack
