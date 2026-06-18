"""
Runtime tenant config loader.

Loads the single active TenantConfig row at startup and caches it in memory.
All voice/agent/tool code calls get_config() synchronously — no per-call DB hit.

Also caches all is_active=true WorkflowDefinitions from workflow_definitions table.
get_active_workflows() returns the in-memory list — zero DB hit per call.
"""
import logging
from typing import Optional

from sqlalchemy import select

from models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)

_config: Optional[TenantConfig] = None
_active_workflows: Optional[list] = None   # list[WorkflowDefinition]; None = not yet loaded


async def load_active_config() -> TenantConfig:
    """Load the is_active=true row from tenant_configs. Cache in module-level variable."""
    global _config
    from database import AsyncSessionLocal  # late import picks up post-reinit session factory
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

    await _load_workflows()
    return _config


def get_config() -> TenantConfig:
    """Synchronous accessor. Returns cached config. Raises if not loaded."""
    if _config is None:
        raise RuntimeError(
            "Tenant config not loaded — call await load_active_config() at startup."
        )
    return _config


def get_active_workflows() -> list:
    """Synchronous accessor. Returns cached list[WorkflowDefinition].

    Returns [] (not None) if the table does not exist yet (pre-migration).
    Never raises.
    """
    if _active_workflows is None:
        return []
    return _active_workflows


async def reload_config() -> TenantConfig:
    """Bust in-memory cache and reload from DB. Called by the reload endpoint."""
    global _config, _active_workflows
    _config = None
    _active_workflows = None
    logger.info("Reloading tenant config from DB...")
    return await load_active_config()


async def reload_workflows() -> list:
    """Reload only the workflow cache — called after PUT /api/workflows/{id}."""
    global _active_workflows
    _active_workflows = None
    await _load_workflows()
    return _active_workflows or []


# ── Workflow cache loader ─────────────────────────────────────────────────────

async def _load_workflows() -> None:
    """Populate _active_workflows from workflow_definitions table.

    Silently skips if the table does not yet exist (pre-migration state) so that
    the server can start without requiring the migration to have been run first.
    """
    global _active_workflows
    try:
        from workflow.node_schema import workflow_from_dict
        from sqlalchemy import text as sa_text
        from database import AsyncSessionLocal  # late import picks up post-reinit session factory

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                sa_text(
                    "SELECT id, name, description, intent_definition, "
                    "few_shot_examples, intent_embedding, intent_threshold, "
                    "definition, is_active "
                    "FROM workflow_definitions WHERE is_active = true "
                    "ORDER BY created_at"
                )
            )
            definitions = []
            for row in rows.mappings():
                try:
                    wf_data = dict(row["definition"]) if row["definition"] else {}
                    wf_data.setdefault("id",                str(row["id"]))
                    wf_data.setdefault("name",              row["name"])
                    wf_data.setdefault("description",       row["description"] or "")
                    wf_data.setdefault("intent_definition", row["intent_definition"] or "")
                    wf_data.setdefault("few_shot_examples", list(row["few_shot_examples"] or []))
                    wf_data["intent_embedding"]  = list(row["intent_embedding"]) if row["intent_embedding"] else None
                    wf_data["intent_threshold"]  = float(row["intent_threshold"] or 0.72)
                    wf_data["is_active"]         = bool(row["is_active"])
                    definitions.append(workflow_from_dict(wf_data))
                except Exception:
                    logger.exception("_load_workflows: skipping malformed row id=%s", row.get("id"))

        _active_workflows = definitions
        logger.info("Loaded %d active workflow(s)", len(definitions))

    except Exception as exc:
        if "workflow_definitions" in str(exc).lower() or "does not exist" in str(exc).lower():
            logger.info("workflow_definitions table not yet created; workflow cache empty")
            _active_workflows = []
        else:
            logger.exception("_load_workflows: unexpected error; workflow cache empty")
            _active_workflows = []
