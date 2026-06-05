"""
Wavvy Voice Agent — Pipeline Evaluation Suite
Run: python3 -m tests.eval_pipeline

Tests the full pipeline stack without a live voice call:
  1. KB Retrieval        — correct doc surfaces for each query
  2. Transcript Norm     — Hinglish + affirmative/denial normalization
  3. Directive Detection — CONFIRM / CANCEL / ESCALATE / REPAIR / ACKNOWLEDGE
  4. Intent Routing      — tier classification (TRANSACTIONAL / CONVERSATIONAL / RECOVERY)
  5. Entity Extraction   — name, email, preferred_day, preferred_time
  6. Response Policy     — chunking, filtering, None on empty
  7. Context Builder     — LLM message structure and content guards
  8. Demo Booking Flow   — full 5-turn workflow simulation
"""
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_pass = _fail = 0
_failures: list[str] = []


def _check(label: str, actual, expected, *, contains: bool = False):
    global _pass, _fail
    ok = (expected in str(actual)) if contains else (actual == expected)
    if ok:
        _pass += 1
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        _fail += 1
        _failures.append(label)
        print(f"  {RED}✗{RESET} {label}")
        print(f"      expected: {expected!r}")
        print(f"      got:      {actual!r}")


def _section(title: str):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. KB Retrieval
# ═══════════════════════════════════════════════════════════════════════════════

async def _test_kb_retrieval(kb_mod):
    _section("1 · KB Retrieval — correct document surfaces")
    cases = [
        ("what is wavvy",                        "wavvy_overview.md"),
        ("how much does wavvy cost",              "wavvy_pricing.md"),
        ("starter plan features",                 "wavvy_pricing.md"),
        ("enterprise pricing custom contract",    "wavvy_pricing.md"),
        ("wavvy vs retell ai",                    "wavvy_vs_competitors.md"),
        ("how does wavvy compare to vapi",        "wavvy_vs_competitors.md"),
        ("what TTS does wavvy use",               "wavvy_tech_stack.md"),
        ("barge in interruption silero vad",      "wavvy_tech_stack.md"),
        ("deepgram nova stt endpointing",         "wavvy_tech_stack.md"),
        ("does wavvy integrate with salesforce",  "wavvy_integration.md"),
        ("how to install wavvy API",              "wavvy_integration.md"),
        ("live call monitoring supervisor",       "wavvy_features.md"),
        ("companion ai agent desktop",            "wavvy_features.md"),
        ("food delivery contact center",          "wavvy_use_cases.md"),
        ("open source MIT license self host",     "wavvy_integration.md"),
    ]
    for query, expected_source in cases:
        hits = await kb_mod.search_kb(query, n_results=2)
        top_src = hits[0]["source"] if hits else "NONE"
        _check(f'search_kb("{query}")', top_src, expected_source, contains=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Transcript Normalization
# ═══════════════════════════════════════════════════════════════════════════════

def _test_normalization():
    _section("2 · Transcript Normalization")
    from voice.transcript_normalizer import normalize_transcript

    cases = [
        # Hinglish — compound before component (ordering fix)
        ("nahi chahiye",              "do not want"),
        ("demo book karna hai",       "demo book want to"),
        ("kya hai wavvy",             "what is wavvy"),
        ("haan",                      "yes"),
        ("thik hai",                  "okay"),
        ("batao mujhe pricing",       "tell me pricing"),
        ("acha ji",                   "okay"),
        # Affirmatives/denials — only 1–2 word utterances are collapsed
        ("yeah",                      "yes"),
        ("yep",                       "yes"),
        ("nope",                      "no"),
        # Multi-word phrases must NOT be collapsed (repair signal must survive)
        ("no I meant pricing",        "no i meant pricing"),
        ("no that's not right",       "no that's not right"),  # "right" no longer stripped
        ("yes please go ahead",       "yes please go ahead"),
        # Filler word removal (uh/um but NOT right/like)
        ("uh wavvy",                  "wavvy"),
        ("um let me think",           "let me think"),
        ("I like wavvy",              "i like wavvy"),          # "like" preserved
        # Basic: lowercase + strip
        ("  WHAT IS WAVVY  ",         "what is wavvy"),
    ]
    for raw, expected in cases:
        result = normalize_transcript(raw)
        _check(f'normalize("{raw}")', result, expected)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Directive Detection
# ═══════════════════════════════════════════════════════════════════════════════

def _test_directives():
    _section("3 · Directive Detection")
    from voice.directive_detector import detect_directive, ConversationalDirective
    from voice.transcript_normalizer import normalize_transcript

    def _dir(text: str):
        norm = normalize_transcript(text)
        r = detect_directive(norm)
        return r.directive.value if r else None, r.confidence if r else 0.0

    # CONFIRM — must pass 0.75 threshold
    for text in ["yes", "yep", "yes please go ahead", "go ahead"]:
        d, c = _dir(text)
        _check(f'CONFIRM "{text}"', d == "confirm" and c >= 0.75, True)

    # CANCEL_PENDING
    for text in ["no cancel that", "no stop"]:
        d, c = _dir(text)
        _check(f'CANCEL "{text}"', d == "cancel_pending" and c >= 0.75, True)

    # ESCALATE
    for text in ["I want to speak to a human", "transfer me to an agent",
                 "connect me with someone"]:
        d, c = _dir(text)
        _check(f'ESCALATE "{text}"', d == "escalate" and c >= 0.75, True)

    # REPAIR — uses lower threshold 0.65
    for text in ["no I meant pricing", "actually I wanted features",
                 "that's not what I said", "that is not what I said"]:
        d, c = _dir(text)
        _check(f'REPAIR "{text}"', d == "repair" and c >= 0.65, True)

    # ACKNOWLEDGEMENT — whole-utterance only
    for text in ["got it", "makes sense", "okay cool", "sounds good"]:
        d, c = _dir(text)
        _check(f'ACK "{text}"', d == "acknowledgement" and c >= 0.75, True)

    # No directive — product queries must NOT be caught by CLARIFY
    for text in ["what is wavvy", "how much does it cost", "book a demo"]:
        d, _ = _dir(text)
        from voice.directive_detector import ConversationalDirective as CD
        _check(f'no-directive "{text}"',
               d in (None, CD.NONE.value, "none"), True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Intent Routing (Tier Classification)
# ═══════════════════════════════════════════════════════════════════════════════

def _test_routing():
    _section("4 · Intent Routing (Tier Classification)")
    from voice.intent_router import classify_tier, RoutingTier

    cases = [
        # TRANSACTIONAL — high-confidence keyword + high STT
        ("book a demo",                 RoutingTier.TRANSACTIONAL, 0.85),
        ("I want to book a demo",       RoutingTier.TRANSACTIONAL, 0.85),
        ("schedule a demo please",      RoutingTier.TRANSACTIONAL, 0.85),
        ("I need to speak to a human",  RoutingTier.TRANSACTIONAL, 0.85),
        ("transfer me to an agent",     RoutingTier.TRANSACTIONAL, 0.85),
        # CONVERSATIONAL — LLM path; greetings are CONVERSATIONAL not RECOVERY
        ("what is wavvy",               RoutingTier.CONVERSATIONAL, 0.90),
        ("how much does it cost",       RoutingTier.CONVERSATIONAL, 0.90),
        ("hi",                          RoutingTier.CONVERSATIONAL, 0.90),
        ("hello",                       RoutingTier.CONVERSATIONAL, 0.90),
        ("good morning",                RoutingTier.CONVERSATIONAL, 0.90),
        ("how does wavvy compare to retell", RoutingTier.CONVERSATIONAL, 0.90),
        # RECOVERY — filler and channel checks
        ("um",                          RoutingTier.RECOVERY, 0.90),
        ("uh",                          RoutingTier.RECOVERY, 0.90),
        ("hmm",                         RoutingTier.RECOVERY, 0.90),
        ("hello?",                      RoutingTier.RECOVERY, 0.90),
        ("are you there",               RoutingTier.RECOVERY, 0.90),
    ]
    for text, expected_tier, stt_conf in cases:
        tier, _ = classify_tier(text, stt_conf)
        _check(f'classify_tier("{text}")', tier, expected_tier)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Entity Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _test_entities():
    _section("5 · Entity Extraction")
    from voice.intent_router import extract_entities

    day_time_cases = [
        # preferred_day only
        ("Thursday",             "preferred_day", "thursday"),
        ("this friday",          "preferred_day", "this friday"),
        ("next monday",          "preferred_day", "next monday"),
        ("tomorrow",             "preferred_day", "tomorrow"),
        # preferred_time only
        ("3pm",                  "preferred_time", "3pm"),
        ("afternoon",            "preferred_time", "afternoon"),
        ("morning",              "preferred_time", "morning"),
        ("noon",                 "preferred_time", "noon"),
        ("10am",                 "preferred_time", "10am"),
        # combined
        ("Thursday at 3pm",      "preferred_day",  "thursday"),
        ("Thursday at 3pm",      "preferred_time", "3pm"),
        ("tomorrow afternoon",   "preferred_day",  "tomorrow"),
        ("tomorrow afternoon",   "preferred_time", "afternoon"),
        ("next friday morning",  "preferred_day",  "next friday"),
        ("next friday morning",  "preferred_time", "morning"),
    ]
    for text, key, expected_val in day_time_cases:
        result = extract_entities(text)
        _check(f'extract("{text}")[{key}]', result.get(key), expected_val)

    # email
    for raw_email, expected_email in [
        ("my email is john@example.com", "john@example.com"),
        ("john at example dot com",      "john@example.com"),
    ]:
        result = extract_entities(raw_email)
        _check(f'extract email "{raw_email}"', result.get("email"), expected_email)

    # no entities from pure intent phrases
    for text in ["I want to book a demo", "what is wavvy"]:
        result = extract_entities(text)
        useful = {k: v for k, v in result.items()
                  if k in ("preferred_day", "preferred_time", "email", "name")}
        _check(f'extract("{text}") → no key entities', bool(useful), False)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Response Policy
# ═══════════════════════════════════════════════════════════════════════════════

def _test_response_policy():
    _section("6 · Response Policy (chunking + filtering)")
    from voice.response_policy import speech_chunking_policy, apply_response_policy

    # speech_chunking_policy: (buffer, expected_phrase, expected_rest, is_final)
    chunking_cases = [
        ("Wavvy supports CRMs. Let me know what else.",
         "Wavvy supports CRMs.", "Let me know what else.", False),
        ("That's exactly right.",        "That's exactly right.", "",                 False),
        ("Great choice! We'll get set up.", "Great choice!",      "We'll get set up.", False),
        ("Wavvy works with",             "",                      "Wavvy works with",  False),
        ("Pricing starts at",            "",                      "Pricing starts at", False),
        ("Ready when you are",           "Ready when you are",    "",                  True),
    ]
    for i, (buf, exp_phrase, exp_rest, is_fin) in enumerate(chunking_cases):
        phrase, rest = speech_chunking_policy(buf, is_final=is_fin)
        _check(f'chunking[{i}] phrase', phrase, exp_phrase)
        _check(f'chunking[{i}] rest',   rest,   exp_rest)

    # apply_response_policy: empty/whitespace → None
    _check("apply_policy('')",   apply_response_policy(""),    None)
    _check("apply_policy('  ')", apply_response_policy("   "), None)
    result = apply_response_policy("Wavvy costs $299.")
    _check("apply_policy(text) → non-None", result is not None, True)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Context Builder
# ═══════════════════════════════════════════════════════════════════════════════

def _test_context_builder():
    _section("7 · Context Builder — LLM message structure")
    from voice.context_builder import build_llm_messages, SYSTEM_PROMPT, KB_RELEVANCE_THRESHOLD
    from voice.conversational_context import ConversationalContext
    from unittest.mock import MagicMock

    def _make_session(transcript="what is wavvy"):
        s = MagicMock()
        s._last_transcript = transcript
        s._last_transcript_hash = None
        s._seen_transcripts = set()
        s.conv_context = ConversationalContext()
        s.memory = None
        s.workflow = None
        return s

    session = _make_session()

    # 1. System prompt is always the first message
    msgs = build_llm_messages(session, kb_snippet=None)
    _check("system prompt is first + role=system", msgs[0]["role"], "system")
    _check("system prompt content matches SYSTEM_PROMPT", msgs[0]["content"], SYSTEM_PROMPT)

    # 2. User utterance is always last
    _check("user utterance is last",      msgs[-1]["role"],    "user")
    _check("user utterance matches text", msgs[-1]["content"], "what is wavvy")

    # 3. No KB → low-confidence hint injected
    has_hint = any("Knowledge confidence: low" in m["content"] for m in msgs)
    _check("no KB snippet → low-confidence hint injected", has_hint, True)

    # 4. High-relevance KB → snippet injected, no hint
    msgs_hi = build_llm_messages(session, kb_snippet="Wavvy is open source.", kb_relevance=0.8)
    _check("high KB → Knowledge: message present",
           any("Knowledge:" in m["content"] for m in msgs_hi), True)
    _check("high KB → no confidence hint",
           any("Knowledge confidence: low" in m["content"] for m in msgs_hi), False)

    # 5. KB below threshold → treated as low confidence
    msgs_lo = build_llm_messages(session, kb_snippet="...", kb_relevance=KB_RELEVANCE_THRESHOLD - 0.1)
    _check("kb below threshold → hint injected",
           any("Knowledge confidence: low" in m["content"] for m in msgs_lo), True)

    # 6. System prompt guardrails
    sp = SYSTEM_PROMPT.lower()
    _check("DEMO BOOKING guard in system prompt",  "let me check availability" in sp, True)
    _check("REPAIR instruction in system prompt",  "repair" in sp,                    True)
    _check("INTERRUPTION instruction in prompt",   "interruption" in sp,              True)
    _check("TONE limit in prompt",                 "25 words" in sp,                  True)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Demo Booking Workflow — 5-Turn Simulation
# ═══════════════════════════════════════════════════════════════════════════════

def _test_demo_booking_flow():
    _section("8 · Demo Booking Workflow — 5-turn simulation")
    from voice.workflow_engine import (
        WorkflowSession, WorkflowStepId, get_current_node,
        missing_entities, next_missing_entity_prompt, is_workflow_active,
    )
    from voice.intent_router import Intent, extract_entities

    wf = WorkflowSession()
    wf.intent = Intent.DEMO_REQUEST
    wf.current_step = WorkflowStepId.CAPTURE_LEAD

    # Turn 1: "I want to book a demo" → workflow starts, ask for name
    node = get_current_node(wf)
    _check("T1: node = CAPTURE_LEAD",          node.id,                         WorkflowStepId.CAPTURE_LEAD)
    _check("T1: missing = name + email",        set(missing_entities(node, wf.entities)), {"name", "email"})
    _check("T1: first prompt = ask_name",       next_missing_entity_prompt(node, wf.entities), "ask_name")

    # Turn 2: name provided
    wf.entities["name"] = "John Smith"
    _check("T2: missing = email only",          set(missing_entities(node, wf.entities)), {"email"})
    _check("T2: next prompt = ask_email",       next_missing_entity_prompt(node, wf.entities), "ask_email")

    # Turn 3: email provided → CAPTURE_LEAD done, advance to SCHEDULE_DEMO
    wf.entities.update(extract_entities("john@example.com"))
    _check("T3: no missing for CAPTURE_LEAD",   missing_entities(node, wf.entities), [])

    wf.current_step = WorkflowStepId.SCHEDULE_DEMO
    node = get_current_node(wf)
    _check("T3: node = SCHEDULE_DEMO",          node.id,                         WorkflowStepId.SCHEDULE_DEMO)
    _check("T3: workflow active",               is_workflow_active(wf),           True)
    _check("T3: missing = day + time",
           set(missing_entities(node, wf.entities)), {"preferred_day", "preferred_time"})
    _check("T3: first prompt = ask_demo_day",   next_missing_entity_prompt(node, wf.entities), "ask_demo_day")

    # Turn 4: day provided
    wf.entities.update(extract_entities("Thursday"))
    _check("T4: preferred_day = thursday",      wf.entities.get("preferred_day"), "thursday")
    _check("T4: time still missing",
           set(missing_entities(node, wf.entities)), {"preferred_time"})
    _check("T4: next prompt = ask_demo_time",   next_missing_entity_prompt(node, wf.entities), "ask_demo_time")

    # Turn 5: time provided → tool can fire
    wf.entities.update(extract_entities("3pm"))
    _check("T5: preferred_time = 3pm",         wf.entities.get("preferred_time"), "3pm")
    _check("T5: no missing → schedule fires",   missing_entities(node, wf.entities), [])

    # Combined arg construction
    day  = wf.entities.get("preferred_day", "")
    time = wf.entities.get("preferred_time", "")
    combined = f"{day} {time}".strip() if day and time else day or time
    _check("T5: combined arg = 'thursday 3pm'", combined, "thursday 3pm")


# ═══════════════════════════════════════════════════════════════════════════════
# Main runner
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    print(f"\n{BOLD}Wavvy Voice Agent — Pipeline Evaluation Suite{RESET}")
    print(f"Backend: {BACKEND}\n")

    import logging
    logging.getLogger("chromadb").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

    import chromadb
    from config import settings
    from knowledge import embeddings as emb_mod
    from knowledge import kb_manager as kb_mod

    chroma = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    kb_col    = chroma.get_or_create_collection("kb_collection")
    calls_col = chroma.get_or_create_collection("calls_collection")
    emb_mod.init_embeddings()
    kb_mod.init_kb_manager(kb_col, calls_col)

    chunk_count = kb_col.count()
    print(f"KB: {chunk_count} chunks loaded")
    if chunk_count == 0:
        print(f"{YELLOW}  ⚠ KB is empty — run: python3 -m knowledge.seed{RESET}")

    await _test_kb_retrieval(kb_mod)
    _test_normalization()
    _test_directives()
    _test_routing()
    _test_entities()
    _test_response_policy()
    _test_context_builder()
    _test_demo_booking_flow()

    total = _pass + _fail
    pct   = round(_pass / total * 100) if total else 0
    colour = GREEN if _fail == 0 else (YELLOW if _fail <= 3 else RED)
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}{colour}  {_pass}/{total} passed ({pct}%){RESET}")

    if _failures:
        print(f"\n{RED}  Failed:{RESET}")
        for f in _failures:
            print(f"    · {f}")
    print()
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
