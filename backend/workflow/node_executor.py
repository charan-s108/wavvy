"""
Node Executor — per-turn logic for a single workflow node.

Called by the orchestrator when session mode == WORKFLOW.  Decides between two paths:

  A. Slots complete → fire auto_actions via execute_with_recovery → evaluate edges
                     → advance node or end workflow.
                     LLM receives only a confirmation directive (no business tools).

  B. Slots incomplete → inject missing-slots directive and node-scoped tool list.
                        LLM collects the remaining variables conversationally.

Auto-actions fire through the existing execute_with_recovery + execute_tool pipeline,
keeping idempotency, retry, and timeout semantics intact.

Edge evaluation uses WorkflowNode.get_edge_target(fast_response_key) — the node graph
edges are the new replacement for the flat STEP_TRANSITIONS table.  The flat table
remains untouched and used by the legacy fintech workflow.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from session.call_session import CallSession
    from workflow.node_schema import AgentProfile, WorkflowNode, WorkflowDefinition

logger = logging.getLogger(__name__)

_WORKFLOW_END_SENTINEL = "__end__"

# Map granular tool fast_response_keys to canonical edge conditions.
# Edge conditions in workflow definitions use short readable names (success,
# not_found, invalid_otp…). Tools return more specific keys (account_verified,
# otp_wrong…). This table normalizes them before edge lookup so every workflow
# definition can use the same canonical set without knowing tool internals.
_FAST_KEY_ALIASES: dict[str, str] = {
    # verify_account
    "account_verified":      "success",
    "account_not_found":     "not_found",
    # send_otp
    "otp_sent":              "success",
    # verify_otp
    "otp_verified":          "success",
    "otp_wrong":             "invalid_otp",
    "otp_expired":           "invalid_otp",
    "otp_max_attempts":      "otp_locked",
    # lookup_transaction / search_transactions
    "transaction_found":     "success",
    "transaction_not_found": "not_found",
    # initiate_refund
    "refund_initiated":           "success",
    "refund_ineligible":          "failure",
    "refund_already_initiated":   "already_refunded",
    "refund_already_completed":   "already_refunded",
    # raise_dispute
    "dispute_filed":              "success",
    "dispute_duplicate":          "already_filed",
    # report_fraud
    "fraud_reported":             "success",
    "fraud_already_open":         "success",
    "fraud_already_reported":     "success",
    # shared escalation triggers
    "fraud_review_required":      "escalate",
    "kyc_escalation_required":    "escalate",
    "verification_required":      "escalate",
    # unlock_account
    "account_unlocked":           "success",
    # escalate_to_human
    "escalating":                 "escalate",
    "already_escalated":          "escalate",
}


def _normalize_fast_key(key: str) -> str:
    """Return canonical edge condition for a given tool fast_response_key."""
    return _FAST_KEY_ALIASES.get(key, key)


# ── Slot type validators ───────────────────────────────────────────────────────
# Hard guards that prevent cross-slot contamination (OTP used as TXN, etc.).
# Keyed by slot name; value is compiled regex that the slot value must fully match.

_SLOT_VALIDATORS: dict[str, re.Pattern] = {
    "phone":  re.compile(r"^\+?\d{10,13}$"),
    "otp":    re.compile(r"^\d{4,8}$"),
    "txn_id": re.compile(r"^TXN-\d{4,}$", re.IGNORECASE),
}

# Human-readable prompts the agent gives when a slot fails validation
_SLOT_REPROMPT: dict[str, str] = {
    "phone":  "I didn't catch a valid mobile number — could you repeat your 10-digit registered number?",
    "otp":    "I didn't catch a valid verification code — could you read out the digits again?",
    "txn_id": "I didn't catch a valid transaction reference — could you give me the TXN number? It starts with TXN followed by digits.",
}


def _validate_slots(slots, node: "WorkflowNode") -> Optional[str]:
    """Validate slot values against their expected formats.

    Returns a corrective directive string if any required slot is malformed,
    or None if all slots pass.  On failure, the caller should clear the bad
    slot and return the directive without firing the auto_action.
    """
    # Map slot name to current value
    slot_values = {
        "phone":  slots.phone,
        "otp":    slots.otp,
        "txn_id": slots.txn_id,
    }
    for slot_name, pattern in _SLOT_VALIDATORS.items():
        value = slot_values.get(slot_name)
        if value is None:
            continue  # slot not set — skip (slots_complete already checked required slots)
        if not pattern.fullmatch(str(value)):
            logger.warning(
                "node_executor: slot_validator rejected %s=%r — clearing and re-prompting",
                slot_name, value,
            )
            # Clear the bad value so the extractor doesn't re-use it
            if slot_name == "phone":
                slots.clear_phone()
            elif slot_name == "otp":
                slots.clear_otp()
            elif slot_name == "txn_id":
                slots.clear_txn_id()
            return _SLOT_REPROMPT.get(slot_name, "Could you repeat that?")
    return None


@dataclass
class NodeAdvanceResult:
    directive:          str
    tools_for_llm:      list                 # empty list when auto-action already fired
    context_additions:  list[dict]           # action result messages injected into LLM ctx
    agent_profile:      Optional["AgentProfile"] = None
    workflow_done:      bool = False
    # When True, the caller should compress the verification exchange (phone + OTP turns)
    # in conversation history down to a single clean "[Identity confirmed: Name]" turn.
    compress_verification_history: bool = False


async def advance(
    text: str,
    session: "CallSession",
    all_tools: list,
    publish_event: Callable,
) -> NodeAdvanceResult:
    """Single entry point called by the orchestrator per user turn."""
    state = session.orchestrator_state

    wf_def  = _load_workflow(state.active_workflow_id)
    if wf_def is None:
        logger.error("node_executor: workflow %s not found; exiting workflow", state.active_workflow_id)
        state.exit_workflow()
        return NodeAdvanceResult(
            directive="I've encountered an internal issue. Let me help you in a moment.",
            tools_for_llm=[],
            context_additions=[],
            workflow_done=True,
        )

    node = wf_def.get_node(state.active_node_id)
    if node is None:
        logger.error(
            "node_executor: node %s not in workflow %s; exiting",
            state.active_node_id, state.active_workflow_id,
        )
        state.exit_workflow()
        return NodeAdvanceResult(
            directive="Something went wrong navigating the workflow.",
            tools_for_llm=[],
            context_additions=[],
            workflow_done=True,
        )

    # Branch / end nodes: pure routing, no LLM turn needed, but we still surface
    # the directive so the LLM can acknowledge in natural speech.
    if node.node_type == "end":
        state.exit_workflow()
        return NodeAdvanceResult(
            directive=node.directive or "We're all set.",
            tools_for_llm=[],
            context_additions=[],
            workflow_done=True,
        )

    slots = state.entity_slots

    # Pre-fill txn_id from customer profile when the node needs one but the entity
    # extractor hasn't captured one from speech yet.  Fires when the customer has
    # exactly ONE failed/refund-eligible transaction — avoids making them speak
    # "TXN-XXXX" explicitly when the account lookup already identified it.
    # Multiple candidates: returns None → agent asks customer to clarify which one.
    if "txn_id" in node.variables and not slots.txn_id:
        inferred = _infer_txn_from_profile(session)
        if inferred:
            slots.txn_id = inferred
            logger.debug(
                "node_executor: pre-filled txn_id=%s from customer profile (single eligible txn)",
                inferred,
            )

    # LLM-action node advancement: if a prior LLM tool call stored a fast_response_key,
    # try to advance using it.  Only advance if the key maps to an EXISTING edge on the
    # current node — unmatched keys (e.g. query tools like get_refund_status) are
    # silently dropped and the node stays active so the LLM can continue the conversation.
    if state.pending_tool_result is not None:
        tool_name, raw_key = state.pending_tool_result
        state.pending_tool_result = None
        fast_key     = _normalize_fast_key(raw_key)
        # Use STRICT edge lookup (no fallback) — only advance if there's an exact match.
        # The catch-all "success" fallback in get_edge_target() is too aggressive here:
        # query tools (get_refund_status, search_transactions) return keys like
        # "refund_processing" that have no defined edge and should keep the node alive.
        next_node_id = _get_edge_exact(node, fast_key)
        logger.info(
            "node_executor: pending_tool_result tool=%s key=%s→%s next=%s",
            tool_name, raw_key, fast_key, next_node_id,
        )
        if next_node_id is not None:
            # Matched edge — advance to next node or end workflow
            if next_node_id == _WORKFLOW_END_SENTINEL:
                state.exit_workflow()
                return NodeAdvanceResult(
                    directive=_resolve_outcome_directive(node, fast_key),
                    tools_for_llm=[],
                    context_additions=[],
                    workflow_done=True,
                )
            state.advance_to_node(next_node_id)
            next_node = wf_def.get_node(next_node_id)
            if next_node and next_node.node_type == "collect":
                for slot_name in next_node.variables:
                    _clear_slot(slot_name, state.entity_slots)
            directive    = next_node.directive if next_node else _resolve_outcome_directive(node, fast_key)
            scoped_tools = (
                [t for t in all_tools if _tool_name(t) in next_node.allowed_tools]
                if next_node else []
            )
            return NodeAdvanceResult(
                directive=directive,
                tools_for_llm=scoped_tools,
                context_additions=[],
                agent_profile=next_node.agent_profile if next_node else None,
            )
        # No matching edge — query tool result; fall through so LLM stays at this node

    # Path A: all required slots filled AND auto_actions defined → fire auto-actions
    # Nodes with no auto_actions are LLM-driven (Path B always) — do not auto-advance.
    if _slots_complete(node, slots) and node.auto_actions:
        return await _handle_auto_actions(node, wf_def, session, all_tools, publish_event)

    # Path B: waiting for slots → provide directive + node-scoped tools
    state.node_attempts += 1
    if node.max_attempts and state.node_attempts > node.max_attempts:
        timeout_edge = node.on_timeout_edge or "timeout"
        next_node_id = node.get_edge_target(timeout_edge)
        if next_node_id and next_node_id != _WORKFLOW_END_SENTINEL:
            state.advance_to_node(next_node_id)
            return NodeAdvanceResult(
                directive="We weren't able to collect the required information. Let me assist you differently.",
                tools_for_llm=[],
                context_additions=[],
            )
        state.exit_workflow()
        return NodeAdvanceResult(
            directive="We weren't able to complete this step. Is there anything else I can help you with?",
            tools_for_llm=[],
            context_additions=[],
            workflow_done=True,
        )

    missing  = _missing_slot_names(node, slots)
    directive = node.directive
    if missing:
        directive = f"{directive} (still need: {', '.join(missing)})"

    scoped_tools = [t for t in all_tools if _tool_name(t) in node.allowed_tools]

    return NodeAdvanceResult(
        directive=directive,
        tools_for_llm=scoped_tools,
        context_additions=[],
        agent_profile=node.agent_profile,
    )


# ── Auto-action path ──────────────────────────────────────────────────────────

async def _handle_auto_actions(
    node: "WorkflowNode",
    wf_def: "WorkflowDefinition",
    session: "CallSession",
    all_tools: list,
    publish_event: Callable,
    _depth: int = 0,
) -> NodeAdvanceResult:
    from voice.tool_recovery import execute_with_recovery

    state   = session.orchestrator_state
    slots   = state.entity_slots
    context_additions: list[dict] = []
    last_fast_key = "success"
    _compress_verification = False
    _directive_template_vars: dict[str, str] = {}  # filled by action handlers, applied to directive

    # Validate slot formats before firing any auto_action.
    # Prevents cross-slot contamination (OTP digits used as TXN ID, etc.).
    _validation_error = _validate_slots(slots, node)
    if _validation_error:
        return NodeAdvanceResult(
            directive=_validation_error,
            tools_for_llm=[],
            context_additions=[],
        )

    for action_name in node.auto_actions:
        args = _build_action_args(action_name, slots, state.node_variables, session)
        logger.info(
            "node_executor: firing auto_action=%s node=%s",
            action_name, node.id,
        )

        tool_result = await execute_with_recovery(
            tool_name=action_name,
            args=args,
            call_id=session.call_id,
            turn_id=session.turn_counter,
            step_id=f"{node.id}/{action_name}",
            session=session,
        )

        raw_key    = tool_result.fast_response_key or ("success" if tool_result.success else "failure")
        fast_key   = _normalize_fast_key(raw_key)
        last_fast_key = fast_key
        if raw_key != fast_key:
            logger.debug(
                "node_executor: fast_key normalized %r → %r (node=%s)",
                raw_key, fast_key, node.id,
            )

        # Publish tool_call event so browser UI reflects the action
        try:
            await publish_event({
                "type":   "tool_call",
                "tool":   action_name,
                "status": "done",
                "result": {"fast_response_key": fast_key},
            })
        except Exception:
            pass

        # Publish otp_sent event so the frontend can surface the OTP code to the customer
        if action_name == "send_otp" and fast_key == "success":
            otp_code = tool_result.data.get("otp")
            if otp_code:
                try:
                    await publish_event({"type": "otp_sent", "otp": otp_code})
                except Exception:
                    pass

        # Publish otp_verified so the frontend clears the displayed OTP code.
        # Also mark the session as verified so subsequent workflows in this call
        # skip the collect_phone → send_otp → verify_otp nodes entirely.
        if action_name == "verify_otp" and fast_key == "success":
            state.session_verified = True
            _compress_verification = True   # signal to caller to rewrite history
            logger.info(
                "node_executor: session_verified=True — identity confirmed for this call",
            )
            try:
                await publish_event({"type": "otp_verified"})
            except Exception:
                pass

        # After verify_account succeeds, inject the full customer profile into
        # LLM context so the agent uses the DB-stored name and data immediately —
        # never the name the customer stated — and never needs to re-query the DB.
        if action_name == "verify_account" and fast_key == "success":
            profile = getattr(session, "customer_profile", None) or {}
            if profile:
                context_additions.append({
                    "role": "developer",
                    "content": _build_customer_context_message(profile),
                })
        elif action_name == "send_otp" and fast_key == "success":
            # Phone number was just accepted and OTP dispatched.
            # Give one clear, prescriptive response — no numbered instructions that
            # the LLM might try to reconcile with the phone digits in chat history.
            context_additions.append({
                "role": "developer",
                "content": (
                    "[Account found — OTP sent]: Account located. "
                    "A 6-digit code was sent to their registered number. "
                    "Say exactly: 'I found your account — I've sent a 6-digit verification code "
                    "to your registered number. Please read it out when you receive it.' "
                    "Say nothing else. Do not reference the digits the customer just provided."
                ),
            })
        elif action_name == "initiate_refund":
            rfn = tool_result.data.get("rfn_number", "")
            if fast_key == "success" and rfn:
                _directive_template_vars["rfn_number"] = rfn
                context_additions.append({
                    "role": "developer",
                    "content": (
                        f"[REFERENCE CONFIRMED — READ VERBATIM]: {rfn}. "
                        f"Say exactly: 'Your refund reference is {rfn}.' "
                        f"Do not rephrase, abbreviate, or generate a different reference number. "
                        f"Add: 'It should arrive within 3 to 5 business days.'"
                    ),
                })
            elif fast_key == "already_refunded":
                existing = tool_result.data.get("refund_case_id", "")
                context_additions.append({
                    "role": "developer",
                    "content": (
                        "[Refund already exists"
                        + (f" — reference: {existing}" if existing else "")
                        + "]: A refund for this transaction is already in progress. "
                        "Tell the customer their refund is already being processed and "
                        "give them the existing reference number if available."
                    ),
                })
            elif fast_key in ("failure", "ineligible"):
                reason = tool_result.data.get("reason", "")
                context_additions.append({
                    "role": "developer",
                    "content": (
                        "[Refund not eligible"
                        + (f": {reason}" if reason else "")
                        + "]: This transaction cannot be refunded. "
                        "Briefly explain and offer to connect the customer with a specialist."
                    ),
                })
            elif tool_result.data:
                context_additions.append({
                    "role":    "developer",
                    "content": f"[auto_action:{action_name}] result_key={fast_key}",
                })
        elif action_name == "raise_dispute":
            dsp = tool_result.data.get("dsp_number", "")
            if fast_key == "dispute_filed" and dsp:
                _directive_template_vars["dsp_number"] = dsp
                context_additions.append({
                    "role": "developer",
                    "content": (
                        f"[REFERENCE CONFIRMED — READ VERBATIM]: {dsp}. "
                        f"Say exactly: 'Your dispute reference is {dsp}.' "
                        f"Do not rephrase, abbreviate, or generate a different reference number. "
                        f"Add: 'Our team will investigate within 3 to 5 business days.'"
                    ),
                })
            elif tool_result.data:
                context_additions.append({
                    "role":    "developer",
                    "content": f"[auto_action:{action_name}] result_key={fast_key}",
                })
        elif action_name == "report_fraud":
            fraud_num = tool_result.data.get("fraud_number", "")
            if fast_key == "fraud_case_opened" and fraud_num:
                _directive_template_vars["fraud_number"] = fraud_num
                context_additions.append({
                    "role": "developer",
                    "content": (
                        f"[REFERENCE CONFIRMED — READ VERBATIM]: {fraud_num}. "
                        f"Say exactly: 'Your fraud case reference is {fraud_num}.' "
                        f"Do not rephrase, abbreviate, or generate a different reference number. "
                        f"Add: 'Our fraud team will review this within 24 hours.'"
                    ),
                })
            elif tool_result.data:
                context_additions.append({
                    "role":    "developer",
                    "content": f"[auto_action:{action_name}] result_key={fast_key}",
                })
        elif tool_result.data:
            context_additions.append({
                "role":    "developer",
                "content": f"[auto_action:{action_name}] result_key={fast_key}",
            })

        # If the action indicates the call should escalate, honour it immediately
        if fast_key == "escalate":
            state.enter_escalation()
            return NodeAdvanceResult(
                directive="Let me connect you with a specialist right away.",
                tools_for_llm=[],
                context_additions=context_additions,
                workflow_done=False,
            )

    # Edge evaluation: which node do we move to?
    next_node_id = node.get_edge_target(last_fast_key)

    if next_node_id is None or next_node_id == _WORKFLOW_END_SENTINEL:
        # Workflow complete — prefer the node's own directive (it describes the outcome)
        # over the generic _resolve_outcome_directive fallback.
        state.exit_workflow()
        directive = node.directive or _resolve_outcome_directive(node, last_fast_key)
        # Substitute any [placeholder] tokens that were populated by action handlers
        # (e.g. [dsp_number], [rfn_number], [fraud_number]).  Without this the LLM
        # sees the literal placeholder and invents a value by pattern-matching against
        # known IDs in its context (e.g. TXN-3300 → DSP-3300).
        for key, val in _directive_template_vars.items():
            directive = directive.replace(f"[{key}]", val)
        return NodeAdvanceResult(
            directive=directive,
            tools_for_llm=[],
            context_additions=context_additions,
            workflow_done=True,
        )

    # Advance to next node within the same workflow
    state.advance_to_node(next_node_id)
    next_node = wf_def.get_node(next_node_id)

    # When retrying a collect node (e.g. wrong phone / wrong OTP), clear the
    # slot the node collects so _slots_complete doesn't fire again immediately
    # with the bad value.
    if next_node and next_node.node_type == "collect":
        for slot_name in next_node.variables:
            _clear_slot(slot_name, state.entity_slots)
            logger.debug(
                "node_executor: cleared slot %r for retry at node %s",
                slot_name, next_node_id,
            )

    # Cascade: if the new node is also immediately auto-completable (action/inform node
    # with no required variables and has auto_actions), fire it in the SAME turn instead
    # of waiting for the next customer utterance.  This is what makes send_otp fire
    # immediately after verify_account rather than waiting 26 seconds for the customer
    # to ask "Have you sent the OTP?".  Depth guard prevents runaway chains.
    if (
        _depth < 3
        and next_node is not None
        and next_node.auto_actions
        and next_node.node_type not in ("collect", "end")
        and _slots_complete(next_node, state.entity_slots)
    ):
        logger.info(
            "node_executor: cascading into node=%s depth=%d",
            next_node_id, _depth + 1,
        )
        cascade = await _handle_auto_actions(
            next_node, wf_def, session, all_tools, publish_event, _depth + 1
        )
        cascade.context_additions = context_additions + cascade.context_additions
        if _compress_verification:
            cascade.compress_verification_history = True
        return cascade

    directive    = next_node.directive if next_node else _resolve_outcome_directive(node, last_fast_key)
    scoped_tools = (
        [t for t in all_tools if _tool_name(t) in next_node.allowed_tools]
        if next_node else []
    )
    return NodeAdvanceResult(
        directive=directive,
        tools_for_llm=scoped_tools,
        context_additions=context_additions,
        agent_profile=next_node.agent_profile if next_node else None,
        compress_verification_history=_compress_verification,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_edge_exact(node: "WorkflowNode", condition: str) -> Optional[str]:
    """Strict edge lookup — only returns a target if an EXACT condition match exists.

    Unlike WorkflowNode.get_edge_target(), this never falls back to the 'success'
    catch-all.  Used for LLM-action node advancement so that query tools whose
    fast_response_key has no declared edge keep the node alive instead of
    accidentally matching the generic success→__end__ edge.
    """
    for edge in node.edges:
        if edge.condition == condition:
            return edge.target_node_id
    return None


def _slots_complete(node: "WorkflowNode", slots) -> bool:
    for slot_name, var_def in node.variables.items():
        if not var_def.required:
            continue
        value = _get_slot_value(slot_name, slots)
        if not value:
            return False
        if var_def.min_length and len(str(value)) < var_def.min_length:
            return False
    return True


def _missing_slot_names(node: "WorkflowNode", slots) -> list[str]:
    missing = []
    for slot_name, var_def in node.variables.items():
        if not var_def.required:
            continue
        if not _get_slot_value(slot_name, slots):
            missing.append(slot_name)
    return missing


def _get_slot_value(slot_name: str, slots) -> Optional[str]:
    """Map canonical slot names to EntitySlots fields."""
    if slot_name == "phone":
        return slots.phone
    if slot_name == "otp":
        return slots.otp
    if slot_name in ("txn_id", "transaction_id"):
        return slots.txn_id
    return None


def _clear_slot(slot_name: str, slots) -> None:
    """Clear a slot so the entity extractor can re-fill it on the next utterance."""
    if slot_name == "phone":
        slots.phone = None
    elif slot_name == "otp":
        slots.otp = None
    elif slot_name in ("txn_id", "transaction_id"):
        slots.txn_id = None


def _build_action_args(
    action_name: str,
    slots,
    node_variables: dict,
    session: "CallSession",
) -> dict:
    """Construct the args dict for the tool call from accumulated entity slots."""
    base: dict = {}

    # Standard slot mapping
    if slots.phone:
        base["phone"] = slots.phone
    if slots.otp:
        base["otp_code"] = slots.otp
    if slots.txn_id:
        base["transaction_id"] = slots.txn_id

    # Session-level overrides
    if session.customer_id:
        base["customer_id"] = session.customer_id

    # Action-specific defaults (parameters the entity extractor doesn't collect)
    if action_name == "raise_dispute" and "reason" not in base:
        base["reason"] = node_variables.get("dispute_reason", "Customer disputed the charge")
    if action_name == "report_fraud" and "fraud_type" not in base:
        base["fraud_type"] = node_variables.get("fraud_type", "unauthorized_transaction")

    # Merge any additional node-level variables collected by LLM tools
    base.update(node_variables)

    return base


def _resolve_outcome_directive(node: "WorkflowNode", fast_key: str) -> str:
    if fast_key == "success":
        return (
            "The issue has been resolved. Wrap up warmly using the customer's first name "
            "(e.g. 'All sorted, Ayaan — is there anything else I can help you with today?'). "
            "If they say no / goodbye / thank you, wish them well and end naturally. "
            "Do NOT offer to connect them with a specialist or agent."
        )
    if fast_key == "failure":
        return "I wasn't able to complete that step. Let me know how else I can help."
    if fast_key == "not_found":
        return "I couldn't find the information needed. Can you double-check the details?"
    return "We've reached the end of this process. How else can I assist you?"


def _tool_name(tool) -> str:
    """Extract the tool name from whatever the LiveKit SDK tool object looks like."""
    try:
        return tool.info.name
    except AttributeError:
        try:
            return tool.__name__
        except AttributeError:
            return str(tool)


_PROBLEMATIC_TXN_STATUSES = frozenset({
    "failed", "kyc_hold", "compliance_hold", "flagged",
    "fraud_reported", "fraud_confirmed",
    "disputed", "chargeback_initiated",
    "refund_initiated", "refund_processing",
    "pending", "processing",
})

# Statuses that a customer would legitimately want to refund.
# Subset of _PROBLEMATIC_TXN_STATUSES — only statuses where a new refund can be raised.
_REFUND_ELIGIBLE_STATUSES = frozenset({"failed", "kyc_hold", "compliance_hold"})


def _infer_txn_from_profile(session: "CallSession") -> Optional[str]:
    """Return the TXN number if the customer profile has exactly ONE refund-eligible transaction.

    Used to auto-fill the txn_id slot so the customer doesn't need to say "TXN-XXXX"
    when the account lookup already identified the only problematic transaction.
    Returns None when zero or multiple candidates exist — agent must ask the customer.
    """
    profile = getattr(session, "customer_profile", None)
    if not profile:
        return None
    transactions = profile.get("transactions") or []
    candidates = [
        t for t in transactions
        if t.get("status") in _REFUND_ELIGIBLE_STATUSES and t.get("txn_number")
    ]
    if len(candidates) == 1:
        return candidates[0]["txn_number"]
    return None


def _build_customer_context_message(profile: dict) -> str:
    """Inject customer identity + account diagnostic block after verify_account.

    Includes problematic transaction statuses, holds, and fraud cases so the LLM
    can immediately address the customer's issue without an extra tool call.
    Specific records (amounts, merchants) are surfaced here; full details available
    on demand via search_transactions / get_refund_status / get_dispute_status.
    """
    name        = profile.get("name", "")
    first_name  = profile.get("first_name", name.split()[0] if name else "customer")
    acct_type   = profile.get("account_type", "standard")
    acct_status = profile.get("account_status", "active")
    kyc         = profile.get("kyc_status", "pending")

    transactions    = profile.get("transactions") or []
    open_refunds    = profile.get("open_refunds") or []
    open_disputes   = profile.get("open_disputes") or []
    account_holds   = profile.get("account_holds") or []
    fraud_cases     = profile.get("active_fraud_cases") or []

    lines = [
        f"MANDATORY NAME RULE: Call this customer '{first_name}' in EVERY response — no exceptions.",
        "[Account data — identity already confirmed; do NOT say 'you are verified' or 'verification complete']",
        f"Name on account: {name} (use first name '{first_name}' in all speech).",
        f"Account: {acct_type} | status: {acct_status} | KYC: {kyc}",
    ]

    # Surface account-level alerts first (locked/frozen/fraud hold)
    if acct_status in ("locked", "frozen", "suspended"):
        lock_reason = profile.get("account_locked_reason", "")
        lines.append(
            f"ACCOUNT IS {acct_status.upper()}"
            + (f": {lock_reason}" if lock_reason else "") + "."
        )

    if profile.get("fraud_hold_active"):
        lines.append("FRAUD HOLD IS ACTIVE on this account.")

    if kyc in ("rejected", "pending"):
        lines.append(f"KYC status is {kyc.upper()} — some transactions may be on hold pending verification.")

    # Active account-level holds
    if account_holds:
        for h in account_holds:
            reason = h.get("reason", "")
            lines.append(
                f"Account hold [{h.get('hold_type', 'unknown')}]"
                + (f": {reason}" if reason else "") + "."
            )

    # Problematic transactions (surface these explicitly so LLM can address without a tool call)
    problematic = [t for t in transactions if t.get("status") in _PROBLEMATIC_TXN_STATUSES]
    all_count   = len(transactions)
    prob_count  = len(problematic)

    if problematic:
        lines.append(f"Issue(s) detected — {prob_count} of {all_count} transaction(s) need attention:")
        for t in problematic[:5]:
            currency = t.get("currency", "INR")
            symbol   = "₹" if "INR" in currency else ("$" if "USD" in currency else f"{currency} ")
            amt_str  = f"{symbol}{t['amount']:,.0f}" if t.get("amount") is not None else ""
            lines.append(f"  {t['txn_number']} — {t.get('merchant', '?')} {amt_str} — {t['status']}")
    else:
        clean = all_count - prob_count
        lines.append(f"No problematic transactions ({clean} transaction(s) all clear).")

    # Refunds and disputes
    if open_refunds:
        lines.append(f"Open refund(s): {len(open_refunds)}")
        for r in open_refunds[:3]:
            lines.append(f"  {r.get('rfn_number')} — {r.get('merchant', '?')} — {r.get('status')}")

    if open_disputes:
        lines.append(f"Open dispute(s): {len(open_disputes)}")
        for d in open_disputes[:3]:
            lines.append(f"  {d.get('dsp_number')} — {d.get('merchant', '?')} — {d.get('status')}")

    # Fraud cases
    if fraud_cases:
        lines.append(f"Active fraud case(s): {len(fraud_cases)} — handle with care.")
        for fc in fraud_cases[:2]:
            lines.append(f"  {fc.get('fraud_number')} — {fc.get('fraud_type')} risk:{fc.get('risk_level')}")
    else:
        lines.append("No active fraud cases. Do not mention or invent any fraud reference.")

    lines.append("Use search_transactions, get_refund_status, or get_dispute_status to retrieve full records when needed.")
    return "\n".join(lines)


def _load_workflow(workflow_id: Optional[str]) -> Optional["WorkflowDefinition"]:
    if not workflow_id:
        return None
    try:
        from config_loader import get_active_workflows
        for wf in get_active_workflows():
            if wf.id == workflow_id:
                return wf
    except Exception:
        logger.exception("node_executor: failed to load workflow %s", workflow_id)
    return None
