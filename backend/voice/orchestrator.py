"""
Orchestrator — top-level call lifetime dispatcher.

Called once per user turn from WavvyAgent.llm_node(), before the LLM receives
any context.  Returns an OrchestratorDecision that tells llm_node() exactly:
  - which tools the LLM may call
  - what directive to prepend to the messages
  - what context additions (FAQ answers, action results) to inject
  - which agent persona (if any) applies at the current workflow node

Execution order per turn:
  1. Entity extraction (sync, <1ms)
  2. Global intent monitor (escalation / cancel keywords; sync)
  3. FAQ capability (async, KB embed + lookup; any mode)
  4. Mode dispatch:
       GENERAL   → workflow trigger (embed, intent match) → enter WORKFLOW if matched
       WORKFLOW  → node executor (slot monitor + auto-actions)
       ESCALATION → terminal; no further routing

Never raises.  All errors are caught and surfaced as safe GENERAL-mode fallbacks.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

from session.orchestrator_state import ExecutionMode

if TYPE_CHECKING:
    from session.call_session import CallSession
    from workflow.node_schema import AgentProfile

logger = logging.getLogger(__name__)

# Tools available in GENERAL mode (open-ended conversation, no business actions).
# escalate_to_human is intentionally absent — the LLM must never self-initiate
# escalation.  It is only offered once the customer has explicitly requested it
# AND confirmed (mode = ESCALATION, handled separately in _process).
GENERAL_MODE_TOOLS: frozenset[str] = frozenset([
    "capture_lead",
    "schedule_demo",
    "cancel_demo",
])

# Escalation keywords — first occurrence triggers a confirmation ask; second confirms.
# Includes role names (specialist, manager, supervisor) and "connect to/with" phrasing.
#
# NOTE: Deepgram VAD sometimes splits a single sentence across two STT chunks, e.g.
# "I would like to connect with" arrives first, "specialist." arrives second.
# Patterns ending mid-sentence (no role word) are intentionally included to catch
# the first fragment so escalation_pending is set before the role word arrives.
_ESCALATION_PATTERNS = [
    # "woman" included — Deepgram frequently mishears "human" as "woman"
    r'\btalk to (a |an )?(human|woman|person|agent|someone|real person|team member|specialist|supervisor|manager|representative|rep|expert)\b',
    r'\bspeak (with|to) (a |an )?(human|woman|agent|person|someone|real|specialist|manager|supervisor|representative)\b',
    r'\bconnect\w* (me )?(to|with) (a |an )?(human|agent|person|specialist|supervisor|manager|team|someone)\b',
    r'\bconnect me\b',
    r'\btransfer (me|my call|the call|this call)\b',
    r'\bcan (i|you) (please )?transfer\b',
    r'\blike to be (transferred|connected|put through)\b',
    r'\bescalate\b',
    r'\bwant (a |an )?(human|agent|person|specialist|manager|supervisor)\b',
    r'\bget me (a |an )?(human|agent|person|specialist|manager)\b',
    r'\bneed (a |an )?(human|agent|specialist|supervisor|manager)\b',
    r'\bsomeone who can help\b',
    r'\bspeak with (a |an )?(specialist|agent|human|manager|supervisor)\b',
    r'\bare you (transferring|connecting|escalating)\b',
    r'\bsomeone who can (fix|help|resolve|sort|handle|deal)\b',
    # Partial-sentence patterns — catch the FIRST STT chunk when VAD splits the sentence
    r'\bwould like to (speak|talk|connect) (to|with)\b',
    r'\bi.d like to (speak|talk|connect)\b',
    r'\bcan (i|you) (speak|talk) (to|with)\b',
    r'\bput me (through|in touch)\b',
    # "I want to speak to" — VAD often cuts here before "someone/specialist" arrives
    r'\bi want to (speak|talk|chat) (to|with)?\b',
    r'\bwant to (speak|talk) (to|with)\b',
    r'\bi need to (speak|talk) (to|with)\b',
]

# Role words — used to accept a SECOND Deepgram chunk ("specialist.") as confirmation
# when escalation_pending is already True from the first chunk ("I would like to connect with").
_ROLE_WORD_RE = re.compile(
    # "woman" included — Deepgram frequently mishears "human" as "woman"
    r'\b(specialist|agent|human|woman|person|manager|supervisor|representative|rep|expert|team member|someone)\b'
)

# Affirmative confirmation patterns (used to confirm a pending escalation).
# Only strong, unambiguous affirmatives — "okay" and bare "please" are excluded
# because they appear mid-sentence too often to be reliable.
_AFFIRMATIVE_PATTERNS = [
    r'\byes\b', r'\byep\b', r'\byeah\b', r'\bsure\b',
    r'\bgo ahead\b', r'\bdo it\b', r'\bconfirm\b', r'\bproceed\b',
    r'\byes please\b', r'\bplease (do|go ahead|transfer|connect)\b',
    # Restatement / emphatic affirmatives — customer says one of these after agent asks
    r'\bexactly\b', r'\babsolutely\b', r'\bcorrect\b',
    r'\bthat.s (right|correct|what i said)\b',
    r'\bthat is (right|correct|what i)\b',   # "that is what I said", "that is what I want"
    r'\bof course\b',
    r'\bplease\b',                            # standalone "please" is unambiguous after a direct question
]

# Negative decline patterns (used to cancel a pending escalation)
_NEGATIVE_PATTERNS = [
    r'\bno\b', r'\bnope\b', r'\bno thanks\b', r'\bdon.t\b',
    r'\bnot now\b', r'\bforget it\b', r'\bcancel\b',
]

# Workflow cancel keywords — exit WORKFLOW and return to GENERAL
_CANCEL_PATTERNS = [
    r'\bcancel\b',
    r'\bstop\b',
    r'\bforget it\b',
    r'\bnever mind\b',
    r'\bnot now\b',
    r'\bgo back\b',
]


_CALL_REASON_PATTERNS: list[tuple[str, list[str]]] = [
    # Fraud checked first — "unauthorized transaction" must map to Fraud, not Payment.
    ("Fraud Concern",   [r'\bfraud\b', r'\bunauthorized\b', r'\bstolen\b', r'\bhack\w*\b',
                         r'\bscam\b', r'\bsuspicious\b', r'\bcompromised\b']),
    # Dispute before Payment — "dispute about a charge" must map to Dispute, not Payment.
    ("Dispute",         [r'\bdispute\b', r'\bcomplaint\b', r'\bovercharge\b',
                         r'\bwrong charge\b', r'\bincorrect charge\b']),
    ("Account Access",  [r'\baccount\b', r'\block\w*\b', r'\bfrozen\b', r'\bkyc\b',
                         r'\bverif\w*\b', r'\bpassword\b', r'\blogin\b', r'\baccess\b', r'\bblock\w*\b']),
    # Payment last among specific categories — broadest keyword set.
    ("Payment Issue",   [r'\bpay\w*\b', r'\btransaction\b', r'\brefund\b', r'\bcharge\b',
                         r'\bbill\b', r'\binvoice\b', r'\btransfer\b', r'\bamount\b', r'\bmoney\b']),
]


def _extract_call_reason(text: str) -> str:
    """Map customer's free-form reason utterance to a standard label."""
    lower = text.lower()
    for label, patterns in _CALL_REASON_PATTERNS:
        if any(re.search(p, lower) for p in patterns):
            return label
    return "General Inquiry"


_BARE_AFFIRMATIVES = frozenset({
    "sure", "yes", "yeah", "yep", "okay", "ok", "of course",
    "please", "go ahead", "absolutely", "correct", "exactly",
})


def _extract_caller_name(text: str) -> str:
    """Strip common intro phrases and return a clean caller name.

    "My name is Priya Sharma" → "Priya Sharma"
    "This is Ayan."           → "Ayan"
    "I'm Raj"                 → "Raj"
    "Sure, call me Sam"       → "Sam"
    "Ayan."                   → "Ayan"
    "Sure."                   → ""  (bare affirmative — not a name)

    Multi-pass so compound phrases like "Sure, call me …" work correctly.
    """
    t = text.strip().rstrip('.').strip()
    lower = t.lower()

    # Bare affirmative with no additional content — never a name
    if lower in _BARE_AFFIRMATIVES:
        return ""
    # Ordered: affirmative prefix first, then intro phrases
    prefixes = [
        r"^(yes[,\s]+|yeah[,\s]+|sure[,\s]+|okay[,\s]+|of course[,\s]+)",
        r"^my name[\'s]*\s*(?:is\s*)?",
        r"^this is\s+",
        r"^i[\'']?m\s+",
        r"^it[\'']?s\s+",
        r"^call me\s+",
    ]
    for _ in range(3):  # at most 3 passes (affirmative + intro phrase + cleanup)
        changed = False
        for p in prefixes:
            stripped = re.sub(p, '', lower)
            if stripped != lower:
                t = t[len(lower) - len(stripped):].strip().rstrip('.').strip()
                lower = t.lower()
                changed = True
                break
        if not changed:
            break
    return t.title() if t else ""


@dataclass
class OrchestratorDecision:
    mode:                   ExecutionMode
    directive:              str
    context_additions:      list[dict]         = field(default_factory=list)
    tools_for_llm:          list               = field(default_factory=list)
    agent_profile_override: Optional["AgentProfile"] = None
    workflow_done:          bool = False
    # When True, wavvy_agent should rewrite the last N messages of conversation
    # history to replace the phone/OTP exchange with a single clean identity summary.
    compress_verification_history: bool = False
    # When set, llm_node yields this text verbatim and returns — no LLM call made.
    # Used for deterministic prompts (name collection, OTP request) where LLM drift
    # would corrupt the flow.
    bypass_llm_text: str | None = None


async def process_utterance(
    text: str,
    session: "CallSession",
    all_tools: list,
    publish_event: Callable,
) -> OrchestratorDecision:
    """Main dispatch function.  One call per user turn."""
    try:
        return await _process(text, session, all_tools, publish_event)
    except Exception:
        logger.exception("orchestrator: unhandled error; falling back to GENERAL")
        return _general_fallback(session, all_tools)


async def _process(
    text: str,
    session: "CallSession",
    all_tools: list,
    publish_event: Callable,
) -> OrchestratorDecision:
    state = session.orchestrator_state

    # ── Step 1: Entity extraction (sync, always) ─────────────────────────────
    from voice.entity_extractor import extract_entities
    extract_entities(text, state.entity_slots)

    # ── Step 2: Global intent monitor ────────────────────────────────────────
    lower = text.lower()

    if state.mode != ExecutionMode.ESCALATION:
        escalation_intent = _is_escalation_request(lower)

        if state.escalation_pending:
            if getattr(state, 'escalation_needs_reason', False):
                # Reason collection phase — any non-negative response = call reason given.
                if _is_negative(lower):
                    state.escalation_call_reason = "General Inquiry"
                else:
                    state.escalation_call_reason = _extract_call_reason(text)
                state.escalation_needs_reason = False
                state.escalation_pending = False
                state.enter_escalation()
                logger.info("orchestrator: call reason collected ('%s'); entering ESCALATION mode", state.escalation_call_reason)
                return OrchestratorDecision(
                    mode=ExecutionMode.ESCALATION,
                    directive="",
                    context_additions=[],
                    tools_for_llm=_scoped_tools(all_tools, {"escalate_to_human"}),
                )

            elif getattr(state, 'escalation_needs_name', False):
                # Name collection phase — any non-negative response = name given.
                # After name, ask for the reason before escalating.
                if _is_negative(lower):
                    state.escalation_pending = False
                    state.escalation_needs_name = False
                    logger.info("orchestrator: escalation declined during name collection")
                    # Fall through — normal dispatch continues
                else:
                    caller_name = _extract_caller_name(text)
                    state.escalation_caller_name = caller_name
                    state.escalation_needs_name = False
                    state.escalation_needs_reason = True   # ask for reason next
                    name_display = caller_name or "there"
                    bypass_text = (
                        f"Thank you {name_display}! Just so our team can help you right away — "
                        "is this about a payment issue, fraud concern, account access, or something else?"
                    )
                    logger.info("orchestrator: name collected ('%s'); requesting call reason", caller_name or text.strip()[:40])
                    return OrchestratorDecision(
                        mode=state.mode,
                        directive="",
                        bypass_llm_text=bypass_text,
                        context_additions=[],
                        tools_for_llm=_scoped_tools(all_tools, GENERAL_MODE_TOOLS),
                    )
            else:
                # Standard confirmation phase.
                # Accept: explicit escalation intent, affirmatives, OR standalone role words.
                # The role-word check handles split STT: "I would like to connect with"
                # sets escalation_pending, then "specialist." arrives and confirms.
                role_word_match = bool(_ROLE_WORD_RE.search(lower))
                if escalation_intent or _is_affirmative(lower) or role_word_match:
                    state.escalation_pending = False
                    state.enter_escalation()
                    logger.info("orchestrator: escalation confirmed (role_word=%s); entering ESCALATION mode", role_word_match)
                    return OrchestratorDecision(
                        mode=ExecutionMode.ESCALATION,
                        directive="",
                        context_additions=[],
                        tools_for_llm=_scoped_tools(all_tools, {"escalate_to_human"}),
                    )
                elif _is_negative(lower):
                    state.escalation_pending = False
                    logger.info("orchestrator: escalation declined; returning to normal flow")
                    # Fall through — normal FAQ + mode dispatch continues

        elif escalation_intent:
            # First escalation signal — single confirmation step regardless of verification.
            # The agent console receives the full conversation transcript, so there is no need
            # to pre-collect a name or call reason here.  Collecting them adds turns that
            # confuse bare affirmatives ("Sure") with names and cause the tool to never fire.
            state.escalation_pending = True
            logger.info("orchestrator: escalation intent detected; requesting confirmation")
            return OrchestratorDecision(
                mode=state.mode,
                directive="",
                bypass_llm_text="I can connect you with a specialist right now. Would you like me to go ahead?",
                context_additions=[],
                tools_for_llm=_scoped_tools(all_tools, GENERAL_MODE_TOOLS),
            )

    if _is_cancel_request(lower) and state.mode == ExecutionMode.WORKFLOW:
        logger.info("orchestrator: cancel request in WORKFLOW mode; returning to GENERAL")
        state.exit_workflow()

    # ── Step 3: Session verification guardrail ───────────────────────────────
    # Injected on EVERY turn once the customer has been verified.
    # Prevents the LLM from verbally asking for phone/OTP again regardless of
    # which workflow it's in or which tools are available.
    context_additions: list[dict] = []
    if state.session_verified:
        context_additions.append({
            "role": "developer",
            "content": (
                "[Session verified — identity already confirmed]: "
                "This customer's phone number and OTP were verified earlier this call. "
                "NEVER ask for their phone number, registered mobile number, OTP, "
                "account number, or any identity proof again under any circumstances. "
                "Their identity is confirmed for the entire call — proceed directly with their request."
            ),
        })

    # ── Step 4: FAQ capability (node-aware suppression) ──────────────────────
    # Suppress FAQ during WORKFLOW mode when the agent is collecting data (collect
    # nodes) or executing a deterministic auto_action (action nodes with auto_actions).
    # In those cases KB policy content pollutes context and causes hallucinations.
    # FAQ IS allowed on informational action nodes (e.g. check_status) where the
    # agent is about to respond to a customer question — "how long do refunds take?"
    # is a legitimate FAQ mid-workflow on an open LLM turn.
    _VERIFICATION_NODES = frozenset({"collect_phone", "send_otp", "verify_otp"})
    _suppress_faq = False
    if state.mode == ExecutionMode.WORKFLOW:
        _active_node = _get_active_node(state)
        _suppress_faq = (
            _active_node is None                       # unknown node → safe fallback
            or _active_node.node_type == "collect"    # gathering digits/references
            or bool(_active_node.auto_actions)         # deterministic action in flight
            or state.active_node_id in _VERIFICATION_NODES  # belt-and-suspenders
        )
    if not _suppress_faq:
        try:
            from voice.faq_capability import resolve as faq_resolve
            faq = await faq_resolve(text, session)
            if faq.is_faq and faq.answer:
                state.last_faq_chunk_id = faq.chunk_id
                context_additions.append({
                    "role":    "developer",
                    "content": f"[Knowledge base context]: {faq.answer}",
                })
                logger.debug(
                    "orchestrator: FAQ answer injected (confidence=%.3f)", faq.confidence
                )
        except Exception:
            logger.exception("orchestrator: FAQ capability error; continuing without FAQ")

    # ── Step 5: Mode dispatch ─────────────────────────────────────────────────
    if state.mode == ExecutionMode.ESCALATION:
        return OrchestratorDecision(
            mode=ExecutionMode.ESCALATION,
            directive="",
            context_additions=context_additions,
            tools_for_llm=_scoped_tools(all_tools, {"escalate_to_human"}),
        )

    if state.mode == ExecutionMode.GENERAL:
        # Routing: keyword classifier first (deterministic, <1ms), embedding as fallback.
        # If the keyword classifier matches with confidence ≥ 0.75 we skip the embed
        # HTTP call entirely — it's slower (~200ms) and less reliable for known issue types.
        matched_wf = None
        no_workflow_match = False

        # Step A: keyword classifier (deterministic)
        try:
            from voice.issue_classifier import classify_issue, get_workflow_id_for_issue
            _cls = classify_issue(text)
            if _cls is not None and _cls.confidence >= 0.75:
                _target_id = get_workflow_id_for_issue(_cls.issue_type)
                if _target_id and _target_id not in getattr(state, 'completed_workflow_ids', set()):
                    from config_loader import get_active_workflows
                    for _wf in get_active_workflows():
                        if _wf.id == _target_id and _wf.is_active:
                            matched_wf = _wf
                            logger.info(
                                "orchestrator: keyword router → workflow='%s' "
                                "(issue=%s confidence=%.2f) — skipping embed",
                                _wf.name, _cls.issue_type.value, _cls.confidence,
                            )
                            break
        except Exception:
            logger.exception("orchestrator: issue classifier failed; falling through to embed")

        # Step B: embedding trigger (only when keyword confidence < 0.75 or no match)
        if matched_wf is None:
            try:
                from voice.workflow_trigger import detect_workflow_trigger
                matched_wf = await detect_workflow_trigger(text, [])
                if matched_wf is None:
                    no_workflow_match = True
            except Exception:
                logger.exception("orchestrator: workflow trigger error; staying in GENERAL")
                no_workflow_match = True

        if matched_wf:
            # Guard: suppress re-entry when the workflow or its terminal tool is already
            # completed this call.  Applies to both the keyword and embedding paths.
            _c_wfs   = getattr(state, 'completed_workflow_ids', set())
            _c_tools = getattr(state, 'completed_terminal_tools', set())
            _t_tool  = _WORKFLOW_TERMINAL_TOOL.get(matched_wf.id)
            if matched_wf.id in _c_wfs:
                logger.info(
                    "orchestrator: general-mode entry suppressed — workflow '%s' already completed this call",
                    matched_wf.name,
                )
                matched_wf = None
            elif _t_tool and _t_tool in _c_tools:
                logger.info(
                    "orchestrator: general-mode entry suppressed — terminal tool '%s' already completed this call (workflow: %s)",
                    _t_tool, matched_wf.name,
                )
                matched_wf = None

        if matched_wf:
            entry_node = _resolve_entry_node(matched_wf, state)
            state.enter_workflow(matched_wf.id, entry_node)
            logger.info(
                "orchestrator: entered workflow '%s' (id=%s) at node='%s'%s",
                matched_wf.name, matched_wf.id, entry_node,
                " [verification skipped — session already verified]" if state.session_verified else "",
            )
            # Fall through immediately to WORKFLOW branch

    if state.mode == ExecutionMode.WORKFLOW:
        # Cross-workflow pivot: if the already-verified customer clearly expresses
        # a different issue type, exit the current workflow and enter the matching
        # one — skipping re-verification since session_verified=True.
        if state.session_verified:
            pivot_wf_id = _detect_workflow_pivot(text, state)
            if pivot_wf_id:
                from config_loader import get_active_workflows
                for _pwf in get_active_workflows():
                    if _pwf.id == pivot_wf_id and _pwf.is_active:
                        _old_name = state.active_workflow_id
                        state.exit_workflow()
                        _pivot_entry = _resolve_entry_node(_pwf, state)
                        state.enter_workflow(_pwf.id, _pivot_entry)
                        logger.info(
                            "orchestrator: cross-workflow pivot %s → '%s' at node='%s' [session verified]",
                            _old_name, _pwf.name, _pivot_entry,
                        )
                        context_additions.append({
                            "role": "developer",
                            "content": (
                                f"[Workflow transition to: {_pwf.name}]: "
                                "The customer is pivoting to a new request. "
                                "Their identity is already confirmed — do NOT ask for phone, OTP, or any identity proof. "
                                "Continue seamlessly from where you left off."
                            ),
                        })
                        break

        try:
            from workflow.node_executor import advance
            result = await advance(text, session, all_tools, publish_event)
        except Exception:
            logger.exception("orchestrator: node_executor error; exiting workflow")
            state.exit_workflow()
            return _general_fallback(session, all_tools, context_additions)

        context_additions.extend(result.context_additions)

        if result.workflow_done or state.mode != ExecutionMode.WORKFLOW:
            # Workflow completed or exited (escalation inside node_executor)
            if state.mode == ExecutionMode.ESCALATION:
                return OrchestratorDecision(
                    mode=ExecutionMode.ESCALATION,
                    directive=result.directive,
                    context_additions=context_additions,
                    tools_for_llm=_scoped_tools(all_tools, {"escalate_to_human"}),
                )
            return OrchestratorDecision(
                mode=ExecutionMode.GENERAL,
                directive=result.directive,
                context_additions=context_additions,
                tools_for_llm=_scoped_tools(all_tools, GENERAL_MODE_TOOLS),
                workflow_done=True,
            )

        return OrchestratorDecision(
            mode=ExecutionMode.WORKFLOW,
            directive=result.directive,
            context_additions=context_additions,
            tools_for_llm=result.tools_for_llm,
            agent_profile_override=result.agent_profile,
            compress_verification_history=result.compress_verification_history,
        )

    # GENERAL mode default — escalate_to_human is never in GENERAL_MODE_TOOLS;
    # it only appears in ESCALATION mode after the customer explicitly confirms.
    #
    # When FAQ context was injected and there is NO pending phone verification,
    # constrain the LLM to stay on the informational topic — do NOT push toward
    # phone collection or escalation, which caused the KYC FAQ failure where
    # "I don't think I have a [document]" was misread as a transactional request
    # and triggered an unwanted escalation offer.
    #
    # Skip this constraint when phone is pending verification — in that case the
    # verify_account directive below takes priority over any FAQ context.
    account_verified = getattr(session, "customer_profile", None) is not None
    phone_pending = state.entity_slots.phone is not None and not account_verified
    if context_additions and not phone_pending:
        context_additions.append({
            "role": "developer",
            "content": (
                "[Mode constraint]: Answer ONLY using the KB context above. "
                "Stay on the informational topic. Do NOT ask for phone numbers, account details, "
                "or offer to connect with a human unless the customer explicitly requests it."
            ),
        })

    # Both keyword router and embedding trigger missed — give the LLM a clear
    # directive to collect the phone number if the utterance looks transactional.
    # Keyword router already ran at confidence < 0.75; no second classifier call needed.
    transactional_keywords = frozenset([
        "payment", "transaction", "transfer", "refund", "charge", "deduct", "deducted",
        "failed", "pending", "blocked", "locked", "fraud", "unauthorized", "dispute",
        "money", "amount", "balance", "account", "otp", "verify",
        "kyc", "hold", "frozen", "freeze", "compliance", "verification",
    ])
    lower_text = text.lower()
    looks_transactional = any(kw in lower_text for kw in transactional_keywords)
    if no_workflow_match and looks_transactional and not context_additions:
        context_additions.append({
            "role": "developer",
            "content": (
                "[No workflow matched yet — GENERAL mode]: The customer appears to have a "
                "transactional issue. You have NO account lookup tools right now. "
                "Do NOT ask for a transaction ID, account number, or any detail you cannot act on. "
                "Acknowledge their issue briefly, then ask for their registered mobile number "
                "to locate their account — for example: 'I can help with that. "
                "Could I get your registered mobile number?' "
                "Do not describe what you are going to do — just ask for the number."
            ),
        })

    general_tools = GENERAL_MODE_TOOLS

    # Phone captured but account not yet verified — AUTO-FIRE verify_account
    # deterministically.  Do NOT rely on the LLM to choose to call the tool;
    # when conversation context suggests escalation (e.g. "KYC hold"), the LLM
    # ignores the directive and verbally offers to transfer instead.
    # Deterministic auto-fire matches what WORKFLOW mode auto_actions do.
    # (account_verified and phone_pending computed above before FAQ constraint check)
    if phone_pending:
        try:
            from tools.wavvy_tools import verify_account as _verify_account
            verify_result = await _verify_account(state.entity_slots.phone, session.call_id)
            fast_key = verify_result.get("fast_response_key", "")
            if fast_key == "account_verified":
                # Verification succeeded — inject lean identity block + expose account tools
                from workflow.node_executor import _build_customer_context_message
                profile = getattr(session, "customer_profile", None) or {}
                context_additions.append({
                    "role":    "developer",
                    "content": _build_customer_context_message(profile),
                })
                # Expose account-level tools so the LLM can act on the customer's issue
                general_tools = general_tools | {
                    "send_otp", "search_transactions", "lookup_transaction",
                    "get_account_holds", "get_refund_status", "get_dispute_status",
                    "escalate_to_human",
                }
            elif fast_key in ("not_found", "lookup_failed"):
                context_additions.append({
                    "role":    "developer",
                    "content": (
                        "[Account not found]: No account was found for that number. "
                        "Apologise briefly and ask the customer to double-check their "
                        "registered mobile number."
                    ),
                })
                state.entity_slots.clear_phone()  # let them retry with correct number
            else:
                # Unexpected failure — let LLM handle gracefully
                context_additions.append({
                    "role":    "developer",
                    "content": f"[Verification error]: {verify_result.get('message', 'Lookup failed.')} Ask the customer to try again.",
                })
                state.entity_slots.clear_phone()
        except Exception:
            logger.exception("orchestrator: verify_account auto-fire failed")
            context_additions.append({
                "role":    "developer",
                "content": "[System error]: Account lookup is temporarily unavailable. Apologise and ask the customer to try again shortly.",
            })
            state.entity_slots.clear_phone()
    elif state.escalation_pending:
        if getattr(state, 'escalation_needs_name', False):
            context_additions.append({
                "role": "developer",
                "content": (
                    "[Reminder — name still needed]: You asked the customer for their name "
                    "before transferring. After answering their question, ask again: "
                    "'Could I get your name so I can connect you with a team member?'"
                ),
            })
        else:
            context_additions.append({
                "role": "developer",
                "content": (
                    "[Reminder]: You previously asked if the customer wants a transfer. "
                    "After answering their question, ask again: 'Would you like me to "
                    "connect you with a team member now?'"
                ),
            })
    return OrchestratorDecision(
        mode=ExecutionMode.GENERAL,
        directive="",
        context_additions=context_additions,
        tools_for_llm=_scoped_tools(all_tools, general_tools),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_active_node(state: "OrchestratorState"):
    """Return the active WorkflowNode from the in-memory workflow cache, or None."""
    if not state.active_workflow_id or not state.active_node_id:
        return None
    try:
        from config_loader import get_active_workflows
        for wf in get_active_workflows():
            if wf.id == state.active_workflow_id:
                return wf.get_node(state.active_node_id)
    except Exception:
        logger.debug("_get_active_node: could not resolve node %s", state.active_node_id)
    return None


def _is_escalation_request(lower: str) -> bool:
    return any(re.search(p, lower) for p in _ESCALATION_PATTERNS)


def _is_affirmative(lower: str) -> bool:
    return any(re.search(p, lower) for p in _AFFIRMATIVE_PATTERNS)


def _is_negative(lower: str) -> bool:
    return any(re.search(p, lower) for p in _NEGATIVE_PATTERNS)


def _is_cancel_request(lower: str) -> bool:
    return any(re.search(p, lower) for p in _CANCEL_PATTERNS)


def _scoped_tools(all_tools: list, allowed_names: frozenset | set) -> list:
    result = []
    for t in all_tools:
        try:
            name = t.info.name
        except AttributeError:
            try:
                name = t.__name__
            except AttributeError:
                continue
        if name in allowed_names:
            result.append(t)
    return result



# Maps workflow UUID → the terminal tool that signals its goal is achieved.
# When that tool returns success (even via LLM tool path, not auto_action),
# the workflow goal is considered complete and no pivot back to it is allowed.
_WORKFLOW_TERMINAL_TOOL: dict[str, str] = {
    "00000000-0000-0000-0000-000000000003": "initiate_refund",   # Refund Request
    "00000000-0000-0000-0000-000000000004": "raise_dispute",     # Dispute Filing
    "00000000-0000-0000-0000-000000000005": "report_fraud",      # Fraud Report
    "00000000-0000-0000-0000-000000000006": "unlock_account",    # Account Unlock
}


def _detect_workflow_pivot(text: str, state) -> str | None:
    """Return a new workflow ID when the customer clearly pivots to a different issue.

    Only triggers at confidence >= 0.75 and only when the target workflow differs
    from the current one and hasn't already been completed this call.
    Also suppressed when the target workflow's terminal tool already succeeded
    this call (even if exit_workflow() was never called — covers the LLM tool path).
    """
    try:
        from voice.issue_classifier import classify_issue, get_workflow_id_for_issue
        result = classify_issue(text)
        if result is None or result.confidence < 0.75:
            return None
        target_id = get_workflow_id_for_issue(result.issue_type)
        if not target_id:
            return None
        if target_id == state.active_workflow_id:
            return None
        if target_id in getattr(state, 'completed_workflow_ids', set()):
            return None
        # Suppress if the goal was already achieved via an LLM tool call this call
        terminal_tool = _WORKFLOW_TERMINAL_TOOL.get(target_id)
        if terminal_tool and terminal_tool in getattr(state, 'completed_terminal_tools', set()):
            logger.debug(
                "orchestrator: pivot suppressed — terminal tool '%s' already completed this call",
                terminal_tool,
            )
            return None
        logger.debug(
            "orchestrator: pivot candidate issue=%s confidence=%.2f → workflow %s",
            result.issue_type.value, result.confidence, target_id,
        )
        return target_id
    except Exception:
        logger.exception("orchestrator: _detect_workflow_pivot error")
    return None


def _resolve_entry_node(wf_def, state) -> str:
    """Return the correct entry node for a workflow given the current session state.

    If the customer has already been verified this call (session_verified=True),
    skip the collect_phone → send_otp → verify_otp chain and enter at the first
    post-verification node (the success edge target of verify_otp).
    Falls back to the workflow's normal entry_node_id if no verify_otp node exists.
    """
    if not state.session_verified:
        return wf_def.entry_node_id

    # Find verify_otp node and follow its success edge to the first real task node
    verify_otp_node = wf_def.nodes.get("verify_otp") if hasattr(wf_def, "nodes") else None
    if verify_otp_node is not None:
        post_verify = verify_otp_node.get_edge_target("success")
        if post_verify and post_verify != "__end__":
            return post_verify

    # Workflow has no verify_otp node (no identity gate) — use its normal entry
    return wf_def.entry_node_id


def _general_fallback(
    session: "CallSession",
    all_tools: list,
    context_additions: list[dict] | None = None,
) -> OrchestratorDecision:
    return OrchestratorDecision(
        mode=ExecutionMode.GENERAL,
        directive="",
        context_additions=context_additions or [],
        tools_for_llm=_scoped_tools(all_tools, GENERAL_MODE_TOOLS),
    )
