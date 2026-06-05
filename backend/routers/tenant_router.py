"""
Tenant config admin endpoints.
GET  /api/tenant/config        → TenantConfigMeta (no prompts, safe to expose)
GET  /api/tenant/config/full   → TenantConfigFull (prompts included)
PUT  /api/tenant/config        → update any field(s), save to DB
POST /api/tenant/config/reload → reload config cache from DB
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from config_loader import get_config, reload_config
from database import AsyncSessionLocal
from models.tenant_config import TenantConfig, TenantConfigFull, TenantConfigMeta, TenantConfigUpdate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tenant"])


@router.get("/api/tenant/config", response_model=TenantConfigMeta)
async def get_tenant_config_meta():
    """Return active tenant config without prompt fields (safe for client consumption)."""
    try:
        cfg = get_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return TenantConfigMeta.model_validate(cfg)


@router.get("/api/tenant/config/full", response_model=TenantConfigFull)
async def get_tenant_config_full():
    """Return active tenant config with all prompt fields (admin use)."""
    try:
        cfg = get_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return TenantConfigFull.model_validate(cfg)


@router.put("/api/tenant/config", response_model=TenantConfigMeta)
async def update_tenant_config(body: TenantConfigUpdate):
    """Update any field(s) on the active tenant config row."""
    updates: dict[str, Any] = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        cfg = get_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(TenantConfig)
            .where(TenantConfig.id == cfg.id)
            .values(**updates)
        )
        await db.commit()
        logger.info("Tenant config updated: %s", list(updates.keys()))

    # Reload so the in-memory cache reflects the change
    updated = await reload_config()
    return TenantConfigMeta.model_validate(updated)


@router.post("/api/tenant/config/reload", response_model=TenantConfigMeta)
async def reload_tenant_config():
    """Bust in-memory config cache and reload from DB."""
    try:
        cfg = await reload_config()
        logger.info("Tenant config reloaded: %s", cfg.agent_name)
        return TenantConfigMeta.model_validate(cfg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
