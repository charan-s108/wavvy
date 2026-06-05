"""
Per-turn structured timing logs. Emitted as JSON after every turn.
Consumed by supervisor dashboard KPI aggregation.
Auto-logs latency_violation=True when any stage exceeds its budget.
"""
import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# ── Per-stage latency budgets (milliseconds) ──────────────────────────────────
LATENCY_BUDGETS_MS: dict[str, float] = {
    "stt":            300.0,
    "normalize":        5.0,
    "layer1":          20.0,  # identity + directive + intent + entity combined
    "workflow":        15.0,
    "tool":           100.0,
    "llm":            700.0,
    "tts_first":      300.0,
    "total":         2000.0,
}


@dataclass
class TurnTrace:
    call_id: str
    turn_id: int
    intent: str
    intent_ms: float
    entity_ms: float
    workflow_ms: float
    tool_name: Optional[str] = None
    tool_ms: Optional[float] = None
    db_ms: Optional[float] = None
    context_build_ms: float = 0.0
    llm_ms: Optional[float] = None       # None = LLM skipped
    llm_tokens: Optional[int] = None
    tts_first_packet_ms: float = 0.0
    total_ms: float = 0.0
    fast_response_key: Optional[str] = None
    llm_skipped: bool = True             # True whenever fast_response_key is set
    kb_injected: bool = False
    kb_relevance: Optional[float] = None
    fallback_level: int = 0              
    latency_violation: bool = False      # True if any stage exceeded its budget
    violated_stages: list = field(default_factory=list)


class TurnTracer:
    """Context manager for measuring per-stage timings within a turn."""

    def __init__(self, call_id: str, turn_id: int):
        self._call_id = call_id
        self._turn_id = turn_id
        self._timings: dict[str, float] = {}
        self._start: float = time.monotonic()
        self._trace_data: dict = {}

    @contextmanager
    def measure(self, stage: str):
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._timings[stage] = elapsed_ms
            budget = LATENCY_BUDGETS_MS.get(stage)
            if budget and elapsed_ms > budget:
                logger.warning(
                    f"[{self._call_id}] Latency violation: {stage}={elapsed_ms:.1f}ms "
                    f"(budget={budget}ms)"
                )

    def set(self, **kwargs) -> None:
        self._trace_data.update(kwargs)

    def emit(self) -> TurnTrace:
        total_ms = (time.monotonic() - self._start) * 1000
        violated = [
            s for s, ms in self._timings.items()
            if LATENCY_BUDGETS_MS.get(s, float("inf")) < ms
        ]
        if total_ms > LATENCY_BUDGETS_MS["total"]:
            violated.append("total")

        trace = TurnTrace(
            call_id=self._call_id,
            turn_id=self._turn_id,
            intent=self._trace_data.get("intent", "unknown"),
            intent_ms=self._timings.get("layer1", 0.0),
            entity_ms=self._timings.get("layer1", 0.0),
            workflow_ms=self._timings.get("workflow", 0.0),
            tool_name=self._trace_data.get("tool_name"),
            tool_ms=self._timings.get("tool"),
            db_ms=self._timings.get("db"),
            context_build_ms=self._timings.get("context_build", 0.0),
            llm_ms=self._timings.get("llm"),
            llm_tokens=self._trace_data.get("llm_tokens"),
            tts_first_packet_ms=self._timings.get("tts_first", 0.0),
            total_ms=total_ms,
            fast_response_key=self._trace_data.get("fast_response_key"),
            llm_skipped=self._trace_data.get("llm_skipped", True),
            kb_injected=self._trace_data.get("kb_injected", False),
            kb_relevance=self._trace_data.get("kb_relevance"),
            fallback_level=self._trace_data.get("fallback_level", 0),
            latency_violation=bool(violated),
            violated_stages=violated,
        )

        try:
            logger.info(json.dumps({"turn_trace": asdict(trace)}))
        except Exception:
            pass  # tracer failure must never block call flow

        return trace
