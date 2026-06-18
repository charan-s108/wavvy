"""
Workflow CRUD router — POST/GET/PUT/DELETE /api/workflows

On POST and PUT: if intent_definition or few_shot_examples changed,
embed (intent_definition + few_shot_examples) and store the averaged vector
as intent_embedding.  The in-memory workflow cache is reloaded after every
mutating operation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ── Request / response models ─────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name:              str
    description:       Optional[str] = ""
    intent_definition: Optional[str] = ""
    few_shot_examples: list[str] = []
    intent_threshold:  float = 0.72
    definition:        dict         # serialized WorkflowDefinition node graph
    is_active:         bool = True


class WorkflowUpdate(BaseModel):
    name:              Optional[str]       = None
    description:       Optional[str]       = None
    intent_definition: Optional[str]       = None
    few_shot_examples: Optional[list[str]] = None
    intent_threshold:  Optional[float]     = None
    definition:        Optional[dict]      = None
    is_active:         Optional[bool]      = None


class WorkflowSummary(BaseModel):
    id:                str
    name:              str
    description:       Optional[str]
    intent_definition: Optional[str]
    intent_threshold:  float
    is_active:         bool
    version:           int
    node_count:        int
    updated_at:        str


class WorkflowDetail(WorkflowSummary):
    few_shot_examples: list[str]
    definition:        dict
    has_embedding:     bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tenant_id() -> str:
    try:
        from config_loader import get_config
        return get_config().tenant_id
    except Exception:
        return "default"


async def _compute_embedding(intent_definition: str, few_shot_examples: list[str]) -> Optional[list[float]]:
    """Embed intent_definition + few_shot_examples; return averaged vector."""
    texts = [t for t in ([intent_definition] + few_shot_examples) if t.strip()]
    if not texts:
        return None
    try:
        from knowledge.embeddings import embed_texts
        vectors = await embed_texts(texts)
        if not vectors:
            return None
        n = len(vectors)
        dim = len(vectors[0])
        averaged = [sum(v[i] for v in vectors) / n for i in range(dim)]
        return averaged
    except Exception:
        logger.exception("workflows_router: embedding failed")
        return None


async def _reload_cache() -> None:
    try:
        from config_loader import reload_workflows
        await reload_workflows()
    except Exception:
        logger.exception("workflows_router: cache reload failed (non-fatal)")


def _row_to_summary(row) -> WorkflowSummary:
    defn = row["definition"] or {}
    nodes = defn.get("nodes", {})
    return WorkflowSummary(
        id=str(row["id"]),
        name=row["name"],
        description=row["description"],
        intent_definition=row["intent_definition"],
        intent_threshold=float(row["intent_threshold"] or 0.72),
        is_active=bool(row["is_active"]),
        version=int(row["version"] or 1),
        node_count=len(nodes),
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
    )


def _row_to_detail(row) -> WorkflowDetail:
    summary = _row_to_summary(row)
    return WorkflowDetail(
        **summary.model_dump(),
        few_shot_examples=list(row["few_shot_examples"] or []),
        definition=dict(row["definition"] or {}),
        has_embedding=bool(row["intent_embedding"]),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WorkflowSummary])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        sa_text(
            "SELECT id, name, description, intent_definition, intent_threshold, "
            "is_active, version, definition, intent_embedding, few_shot_examples, updated_at "
            "FROM workflow_definitions WHERE tenant_id = :tid ORDER BY created_at"
        ),
        {"tid": _tenant_id()},
    )
    return [_row_to_summary(r) for r in rows.mappings()]


@router.post("", response_model=WorkflowDetail, status_code=201)
async def create_workflow(body: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    wf_id = str(uuid.uuid4())
    embedding = await _compute_embedding(
        body.intent_definition or "", body.few_shot_examples
    )

    # Ensure the definition carries the canonical id
    defn = dict(body.definition)
    defn["id"]   = wf_id
    defn["name"] = body.name

    await db.execute(
        sa_text(
            "INSERT INTO workflow_definitions "
            "(id, tenant_id, name, description, intent_definition, few_shot_examples, "
            " intent_embedding, intent_threshold, definition, is_active) "
            "VALUES (:id, :tid, :name, :desc, :idef, :fse, :emb, :thr, :defn, :active)"
        ),
        {
            "id":     wf_id,
            "tid":    _tenant_id(),
            "name":   body.name,
            "desc":   body.description or "",
            "idef":   body.intent_definition or "",
            "fse":    body.few_shot_examples,
            "emb":    embedding,
            "thr":    body.intent_threshold,
            "defn":   defn,
            "active": body.is_active,
        },
    )
    await db.commit()
    await _reload_cache()

    row = (await db.execute(
        sa_text("SELECT * FROM workflow_definitions WHERE id = :id"),
        {"id": wf_id},
    )).mappings().one()
    return _row_to_detail(row)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        sa_text("SELECT * FROM workflow_definitions WHERE id = :id AND tenant_id = :tid"),
        {"id": workflow_id, "tid": _tenant_id()},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Workflow not found")
    return _row_to_detail(row)


@router.put("/{workflow_id}", response_model=WorkflowDetail)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        sa_text("SELECT * FROM workflow_definitions WHERE id = :id AND tenant_id = :tid"),
        {"id": workflow_id, "tid": _tenant_id()},
    )).mappings().one_or_none()
    if existing is None:
        raise HTTPException(404, "Workflow not found")

    # Determine if embedding needs recompute
    new_idef = body.intent_definition if body.intent_definition is not None else existing["intent_definition"]
    new_fse  = body.few_shot_examples  if body.few_shot_examples  is not None else list(existing["few_shot_examples"] or [])
    intent_changed = (
        body.intent_definition is not None or body.few_shot_examples is not None
    )
    embedding = (
        await _compute_embedding(new_idef or "", new_fse)
        if intent_changed
        else existing["intent_embedding"]
    )

    new_defn = dict(body.definition) if body.definition is not None else dict(existing["definition"] or {})
    new_name = body.name or existing["name"]
    new_defn.setdefault("id",   workflow_id)
    new_defn["name"] = new_name

    await db.execute(
        sa_text(
            "UPDATE workflow_definitions SET "
            "name = :name, description = :desc, intent_definition = :idef, "
            "few_shot_examples = :fse, intent_embedding = :emb, "
            "intent_threshold = :thr, definition = :defn, "
            "is_active = :active, version = version + 1, updated_at = :now "
            "WHERE id = :id"
        ),
        {
            "id":     workflow_id,
            "name":   new_name,
            "desc":   body.description if body.description is not None else existing["description"],
            "idef":   new_idef,
            "fse":    new_fse,
            "emb":    embedding,
            "thr":    body.intent_threshold if body.intent_threshold is not None else existing["intent_threshold"],
            "defn":   new_defn,
            "active": body.is_active if body.is_active is not None else existing["is_active"],
            "now":    datetime.now(timezone.utc),
        },
    )
    await db.commit()
    await _reload_cache()

    row = (await db.execute(
        sa_text("SELECT * FROM workflow_definitions WHERE id = :id"),
        {"id": workflow_id},
    )).mappings().one()
    return _row_to_detail(row)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        sa_text(
            "UPDATE workflow_definitions SET is_active = false "
            "WHERE id = :id AND tenant_id = :tid"
        ),
        {"id": workflow_id, "tid": _tenant_id()},
    )
    await db.commit()
    await _reload_cache()
    if result.rowcount == 0:
        raise HTTPException(404, "Workflow not found")


@router.post("/{workflow_id}/activate", response_model=WorkflowDetail)
async def activate_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        sa_text(
            "UPDATE workflow_definitions SET is_active = true, updated_at = :now "
            "WHERE id = :id AND tenant_id = :tid"
        ),
        {"id": workflow_id, "tid": _tenant_id(), "now": datetime.now(timezone.utc)},
    )
    await db.commit()
    await _reload_cache()

    row = (await db.execute(
        sa_text("SELECT * FROM workflow_definitions WHERE id = :id"),
        {"id": workflow_id},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Workflow not found")
    return _row_to_detail(row)


@router.get("/{workflow_id}/versions")
async def list_versions(workflow_id: str):
    """Stub — version history is a future feature."""
    return {"workflow_id": workflow_id, "versions": [], "note": "version history not yet implemented"}


# ── Internal endpoint used by the LiveKit worker ──────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import math
    dot   = sum(ai * bi for ai, bi in zip(a, b))
    mag_a = math.sqrt(sum(ai * ai for ai in a))
    mag_b = math.sqrt(sum(bi * bi for bi in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class _MatchRequest(BaseModel):
    text: str


@router.post("/internal/match", include_in_schema=False)  # mounts as /api/workflows/internal/match
async def match_workflow_intent(body: _MatchRequest):
    """Called by the LiveKit worker on every utterance (GENERAL mode only).

    Embeds the utterance text and cosine-compares against all active workflow
    intent embeddings cached in memory.  Returns the best match or
    {"matched": false} so the worker stays in GENERAL mode.

    The worker must NOT load sentence-transformers — all embedding lives here.
    """
    from config_loader import get_active_workflows
    from knowledge.embeddings import embed_single

    text = (body.text or "").strip()
    if not text:
        return {"matched": False}

    workflows = get_active_workflows()
    candidates = [wf for wf in workflows if wf.intent_embedding]
    if not candidates:
        return {"matched": False}

    try:
        utterance_vec = await embed_single(text)
    except Exception:
        logger.exception("workflow/internal/match: embed failed")
        return {"matched": False}

    best_wf    = None
    best_score = -1.0
    all_scores: list[dict] = []
    for wf in candidates:
        score = _cosine_similarity(utterance_vec, wf.intent_embedding)
        all_scores.append({"name": wf.name, "score": round(score, 4), "threshold": wf.intent_threshold, "matched": score >= wf.intent_threshold})
        if score >= wf.intent_threshold and score > best_score:
            best_score = score
            best_wf    = wf

    logger.info(
        "workflow/match utterance=%r scores=%s",
        text[:80],
        [{s["name"]: f"{s['score']:.3f}/{s['threshold']:.2f}{'✓' if s['matched'] else '✗'}"} for s in all_scores],
    )

    if best_wf is None:
        return {"matched": False}

    return {
        "matched":          True,
        "id":               best_wf.id,
        "name":             best_wf.name,
        "description":      best_wf.description,
        "intent_definition": best_wf.intent_definition,
        "intent_threshold": best_wf.intent_threshold,
        "entry_node_id":    best_wf.entry_node_id,
    }
