"""
Runtime tenant config loader.

Loads the single active TenantConfig row at startup and caches it in memory.
All voice/agent/tool code calls get_config() synchronously — no per-call DB hit.
"""
import logging

from sqlalchemy import select

from database import AsyncSessionLocal
from models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)

_config: TenantConfig | None = None


async def load_active_config() -> TenantConfig:
    """Load the is_active=true row from tenant_configs. Cache in module-level variable."""
    global _config
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TenantConfig).where(TenantConfig.is_active == True)  # noqa: E712
        )
        cfg = result.scalar_one_or_none()
        if cfg is None:
            raise RuntimeError(
                "No active tenant config found in tenant_configs table. "
                "Run seed.py to populate the initial config."
            )
        _config = cfg
        logger.info("Loaded tenant config: %s (%s)", cfg.agent_name, cfg.tenant_id)
    return _config


def get_config() -> TenantConfig:
    """Synchronous accessor. Returns cached config. Raises if not loaded."""
    if _config is None:
        raise RuntimeError(
            "Tenant config not loaded — call await load_active_config() at startup."
        )
    return _config


async def reload_config() -> TenantConfig:
    """Bust in-memory cache and reload from DB. Called by the reload endpoint."""
    global _config
    _config = None
    logger.info("Reloading tenant config from DB...")
    return await load_active_config()
