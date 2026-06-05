"""
Turn-scoped cancellation tree for backpressure control.

Each turn in _orchestrate() creates a TurnExecutionContext. Every child task
(KB prefetch, LLM stream, TTS, silence callbacks) registers into it.
On barge-in, cancel_all() kills all orphaned async work for that turn,
preventing: stale KB cache poisoning, ghost TTS frames, duplicate speech.

Phase 1: additive — class created but not yet wired into _orchestrate().
Phase 3: _orchestrate() rewrite uses TurnExecutionContext throughout.
"""
import asyncio
from dataclasses import dataclass, field


@dataclass
class TurnExecutionContext:
    """
    Cancellation scope for a single orchestration turn.
    All async work launched during a turn must register here.
    """
    turn_id:      str
    _cancelled:   asyncio.Event   = field(default_factory=asyncio.Event)
    child_tasks:  list            = field(default_factory=list)

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel_all(self) -> None:
        """Signal cancellation and cancel all registered child tasks."""
        self._cancelled.set()
        for t in self.child_tasks:
            if not t.done():
                t.cancel()

    def spawn(self, coro) -> asyncio.Task:
        """Create a child task registered to this turn."""
        task = asyncio.create_task(coro)
        self.child_tasks.append(task)
        return task

    async def run_or_cancel(self, coro):
        """Run coro; return None immediately if this turn has been cancelled."""
        if self.is_cancelled():
            return None
        task = self.spawn(coro)
        try:
            return await task
        except asyncio.CancelledError:
            return None
