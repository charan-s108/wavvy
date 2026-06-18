"""
Barge-in manager: handles user speech interrupting ongoing TTS playback.
Cancels in-flight TTS frames, preserves workflow state.
Stale audio drop rule: discard any TTS audio where turn_id < session.active_turn_id.
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class BargeInManager:
    """
    Coordinates barge-in across the LiveKit Agents pipeline.
    """

    def __init__(self):
        self._active = False

    async def on_user_speech_start(self, task: Any, session: Any) -> None:
        """
        Called immediately when VAD detects user speech start.
        - Signals the agent to cancel in-flight TTS frames
        - Clears pending audio queue
        - Preserves workflow_session state (does NOT reset pending_action)
        - Only cancels audio — not orchestration state
        """
        if self._active:
            return

        self._active = True
        session.turn_counter += 1
        session.active_turn_id = session.turn_counter

        logger.debug(
            f"[{session.call_id}] Barge-in detected — "
            f"new turn_id={session.active_turn_id}"
        )

        # Record barge-in state on session (Phase 1 fields)
        import time as _t
        session.last_barge_in_at = _t.monotonic()
        session.barge_in_count += 1

        # Ghost speech guard: invalidate the current LLM response stream
        session.current_response_id = None

        # Cancel active turn context (KB prefetch, LLM stream, silence callbacks)
        if session.current_turn_ctx is not None:
            session.current_turn_ctx.cancel_all()

        # Update turn state machine
        from session.call_session import TurnState
        session.turn_state = TurnState.INTERRUPTED

        # Cancel in-flight TTS via agent task
        if task:
            try:
                await task.cancel_task()
            except Exception:
                pass

    async def on_user_speech_end(self, text: str, session: Any) -> None:
        """
        Latest utterance is now fully available.
        Resets barge-in flag so next speech cycle can trigger again.
        """
        self._active = False
        from session.call_session import TurnState
        session.turn_state = TurnState.USER_SPEAKING


def is_stale_turn(turn_id: int, session: Any) -> bool:
    """
    Returns True if this turn_id is older than the session's active turn.
    Used to discard TTS audio and tool results from superseded turns.

    Usage: before any TTS audio frame is queued:
        if is_stale_turn(turn_id, session):
            discard frame
    """
    return turn_id < session.active_turn_id


def should_pause_silence_timer(turn_state: Any) -> bool:
    """
    Returns True when the silence timer should pause (not advance elapsed time).
    Prevents the timer firing while the assistant is speaking or processing.
    """
    try:
        from session.call_session import TurnState
        return turn_state in (TurnState.ASSISTANT_SPEAKING, TurnState.PROCESSING)
    except Exception:
        return False


class SilenceTimer:
    """
    Tracks silence duration after prompts.
    Fires callbacks at configurable thresholds (default 12s / 25s / 40s).
    Pauses elapsed time during ASSISTANT_SPEAKING and PROCESSING turns.
    Supports weighted resets: FULL (reset to 0), PARTIAL (halve elapsed), NONE (no change).
    """

    def __init__(self, call_id: str, callbacks: dict, session: Any = None):
        self._call_id = call_id
        self._callbacks = callbacks   # {12: fn, 25: fn, 40: fn}
        self._task: asyncio.Task | None = None
        self._elapsed: float = 0.0
        self._session = session   # optional — enables turn_state pause check

    def reset(self) -> None:
        """Full reset — call when substantive user speech arrives."""
        if self._task:
            self._task.cancel()
        self._task = None
        self._elapsed = 0.0

    def apply_weighted_reset(self, strength: str) -> None:
        """
        Weighted reset to prevent fillers/acks from restarting the full lifecycle.
        strength: "full" | "partial" | "none"
        """
        if strength == "full":
            self._elapsed = 0.0
        elif strength == "partial":
            self._elapsed = max(0.0, self._elapsed * 0.5)
        # "none": no change

    def start(self) -> None:
        """Start tracking silence. Call after AI finishes speaking."""
        if self._task:
            self._task.cancel()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        thresholds = sorted(self._callbacks.keys())
        TICK = 0.25   # resolution: 250ms
        try:
            next_threshold_idx = 0
            while next_threshold_idx < len(thresholds):
                threshold = thresholds[next_threshold_idx]
                while self._elapsed < threshold:
                    # Pause during assistant speech — don't advance elapsed
                    turn_state = (
                        getattr(self._session, "turn_state", None)
                        if self._session else None
                    )
                    if turn_state is not None and should_pause_silence_timer(turn_state):
                        await asyncio.sleep(TICK)
                        continue
                    await asyncio.sleep(TICK)
                    self._elapsed += TICK
                self._elapsed = threshold
                fn = self._callbacks.get(threshold)
                if fn:
                    try:
                        await fn()
                    except Exception as e:
                        logger.error(f"[{self._call_id}] SilenceTimer callback error: {e}")
                next_threshold_idx += 1
        except asyncio.CancelledError:
            pass
