"""
Workflow Trigger — calls the backend to match an utterance against active workflows.

The backend holds the embedding model and the active workflow cache.
The worker sends the utterance text and receives back the best-matching workflow
(name, id, entry_node_id) or null.  No sentence-transformers in the worker.
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import httpx
from config import settings

if TYPE_CHECKING:
    from workflow.node_schema import WorkflowDefinition

logger = logging.getLogger(__name__)


async def detect_workflow_trigger(
    text: str,
    active_workflows: list,   # kept for API compatibility; backend owns the actual list
) -> Optional["WorkflowDefinition"]:
    """Ask the backend which workflow (if any) matches this utterance.

    Returns a lightweight WorkflowDefinition-like object with enough fields
    for the orchestrator to enter workflow mode, or None to stay in GENERAL.

    Never raises — caller continues in GENERAL mode on any error.
    """
    try:
        url = f"{settings.backend_internal_url}/api/workflows/internal/match"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json={"text": text})
            resp.raise_for_status()
            data = resp.json()

        if not data or not data.get("matched"):
            return None

        # Return a minimal object the orchestrator can use directly
        from workflow.node_schema import WorkflowDefinition
        return WorkflowDefinition(
            id               = data["id"],
            name             = data["name"],
            description      = data.get("description", ""),
            intent_definition= data.get("intent_definition", ""),
            few_shot_examples= [],
            intent_embedding = None,   # not needed at runtime
            intent_threshold = data.get("intent_threshold", 0.70),
            entry_node_id    = data["entry_node_id"],
            nodes            = {},     # node detail fetched separately by node_executor
            is_active        = True,
        )
    except Exception:
        logger.exception("workflow_trigger: backend call failed; staying in GENERAL")
        return None
