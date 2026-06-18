"""
Node graph schema — data classes for configurable workflow definitions.

Stored as JSONB in workflow_definitions.definition. Loaded into memory at
startup via config_loader.get_active_workflows(). All voice pipeline code
reads from the in-memory cache — zero DB hits per call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class AgentProfile:
    """Optional per-node persona override.

    When set, the node's persona string is appended to the base system prompt
    for the duration of that node. Lets Fraud Investigation nodes sound like
    fraud specialists while Refund nodes stay empathetic — same runtime,
    different voice.
    """
    name:           str                                           # "Fraud Specialist"
    persona:        str                                           # appended to system prompt
    response_style: Literal["brief", "medium", "detailed"] = "medium"


@dataclass
class NodeVariableDef:
    """Defines a slot that must be filled before the node can complete."""
    type:       Literal["phone", "otp", "txn_id", "text", "bool", "email"]
    required:   bool = True
    min_length: Optional[int] = None


@dataclass
class NodeEdge:
    """A conditional transition from one node to another."""
    condition:      str   # fast_response_key, "success", "failure", or "timeout"
    target_node_id: str   # "__end__" signals workflow completion


@dataclass
class WorkflowNode:
    """A single node in a workflow graph.

    node_type semantics:
      collect  — gather structured data from the customer (slots must fill)
      inform   — deliver information; no slots; transitions on LLM completion signal
      action   — execute a business action; auto_actions fire on node entry or slot complete
      branch   — evaluate a condition; forward-only; no LLM turn
      end      — terminal node (success or failure)
    """
    id:                   str
    name:                 str
    node_type:            Literal["collect", "inform", "action", "branch", "end"]
    directive:            str                          # injected into LLM as developer note
    allowed_tools:        list[str]                    # LLM-callable tools restricted to this node
    auto_actions:         list[str]                    # tools the orchestrator fires (not LLM)
    variables:            dict[str, NodeVariableDef]   # slots to fill; keyed by slot name
    completion_condition: str                          # human-readable label; evaluated by node_executor
    edges:                list[NodeEdge]
    max_attempts:         int = 3
    on_timeout_edge:      Optional[str] = None         # condition string for timeout edge
    agent_profile:        Optional[AgentProfile] = None

    def get_required_slots(self) -> list[str]:
        return [name for name, v in self.variables.items() if v.required]

    def get_edge_target(self, condition: str) -> Optional[str]:
        """Return target node id for the given condition, or None if no match."""
        for edge in self.edges:
            if edge.condition == condition:
                return edge.target_node_id
        # Fallback: check for a "success" or "failure" catch-all
        for edge in self.edges:
            if edge.condition in ("success", "default"):
                return edge.target_node_id
        return None


@dataclass
class WorkflowDefinition:
    """A complete workflow graph with intent matching metadata.

    intent_definition + few_shot_examples are embedded at save time (by the
    workflows router). At runtime detect_workflow_trigger() compares an
    incoming utterance embedding against intent_embedding via cosine similarity.
    """
    id:                str
    name:              str
    description:       str
    intent_definition: str           # "Customer wants to check status of an existing transaction"
    few_shot_examples: list[str]     # 3–5 representative utterances embedded at save time
    entry_node_id:     str
    nodes:             dict[str, WorkflowNode]
    intent_embedding:  Optional[list[float]] = None   # cached; recomputed on every PUT
    intent_threshold:  float = 0.72
    is_active:         bool = True

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        return self.nodes.get(node_id)

    def get_entry_node(self) -> Optional[WorkflowNode]:
        return self.nodes.get(self.entry_node_id)


# ── Serialization helpers ────────────────────────────────────────────────────

def node_from_dict(d: dict) -> WorkflowNode:
    variables = {
        k: NodeVariableDef(**v) for k, v in d.get("variables", {}).items()
    }
    edges = [NodeEdge(**e) for e in d.get("edges", [])]
    ap = None
    if d.get("agent_profile"):
        ap = AgentProfile(**d["agent_profile"])
    return WorkflowNode(
        id=d["id"],
        name=d["name"],
        node_type=d["node_type"],
        directive=d.get("directive", ""),
        allowed_tools=d.get("allowed_tools", []),
        auto_actions=d.get("auto_actions", []),
        variables=variables,
        completion_condition=d.get("completion_condition", ""),
        edges=edges,
        max_attempts=d.get("max_attempts", 3),
        on_timeout_edge=d.get("on_timeout_edge"),
        agent_profile=ap,
    )


def workflow_from_dict(d: dict) -> WorkflowDefinition:
    nodes = {nid: node_from_dict(n) for nid, n in d.get("nodes", {}).items()}
    return WorkflowDefinition(
        id=d["id"],
        name=d["name"],
        description=d.get("description", ""),
        intent_definition=d.get("intent_definition", ""),
        few_shot_examples=d.get("few_shot_examples", []),
        entry_node_id=d["entry_node_id"],
        nodes=nodes,
        intent_embedding=d.get("intent_embedding"),
        intent_threshold=d.get("intent_threshold", 0.72),
        is_active=d.get("is_active", True),
    )


def node_to_dict(n: WorkflowNode) -> dict:
    return {
        "id":                   n.id,
        "name":                 n.name,
        "node_type":            n.node_type,
        "directive":            n.directive,
        "allowed_tools":        n.allowed_tools,
        "auto_actions":         n.auto_actions,
        "variables":            {k: {"type": v.type, "required": v.required, "min_length": v.min_length}
                                 for k, v in n.variables.items()},
        "completion_condition": n.completion_condition,
        "edges":                [{"condition": e.condition, "target_node_id": e.target_node_id}
                                 for e in n.edges],
        "max_attempts":         n.max_attempts,
        "on_timeout_edge":      n.on_timeout_edge,
        "agent_profile":        {"name": n.agent_profile.name, "persona": n.agent_profile.persona,
                                 "response_style": n.agent_profile.response_style}
                                if n.agent_profile else None,
    }


def workflow_to_dict(wf: WorkflowDefinition) -> dict:
    return {
        "id":                wf.id,
        "name":              wf.name,
        "description":       wf.description,
        "intent_definition": wf.intent_definition,
        "few_shot_examples": wf.few_shot_examples,
        "entry_node_id":     wf.entry_node_id,
        "nodes":             {nid: node_to_dict(n) for nid, n in wf.nodes.items()},
        "intent_embedding":  wf.intent_embedding,
        "intent_threshold":  wf.intent_threshold,
        "is_active":         wf.is_active,
    }
