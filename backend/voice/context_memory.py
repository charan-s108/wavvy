"""
ContextMemoryManager — tracks injected KB chunks, prevents duplicates,
enforces a rolling token budget, and expires stale context slots.
"""
import json
import logging
import tiktoken

logger = logging.getLogger(__name__)

MAX_CONTEXT_TOKENS = 12_000
MAX_KB_SLOTS = 5
KB_TTL_TURNS = 3


class ContextMemoryManager:
    def __init__(self):
        self._kb_slots: list[dict] = []        # {id, content, added_turn, ttl}
        self._injected_ids: set[str] = set()   # dedup guard
        self._customer_ctx: str | None = None
        self._turn_count: int = 0
        try:
            self._enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._enc = None

    # ── Turn lifecycle ────────────────────────────────────────────────────────

    def on_new_turn(self):
        self._turn_count += 1
        self._cleanup_expired()

    def _cleanup_expired(self):
        self._kb_slots = [
            s for s in self._kb_slots
            if self._turn_count - s["added_turn"] < s["ttl"]
        ]

    # ── Injection ─────────────────────────────────────────────────────────────

    def add_kb_context(self, kb_id: str, content: str, ttl_turns: int = KB_TTL_TURNS):
        """Add a KB chunk. Silently skips if already injected this session."""
        if kb_id in self._injected_ids:
            return
        self._injected_ids.add(kb_id)
        self._kb_slots.append({
            "id": kb_id,
            "content": content,
            "added_turn": self._turn_count,
            "ttl": ttl_turns,
        })
        # Trim oldest if over max slots
        if len(self._kb_slots) > MAX_KB_SLOTS:
            self._kb_slots.pop(0)

    def add_customer_context(self, content: str):
        """Set the sanitized customer profile. Overwrites previous."""
        self._customer_ctx = content

    # ── Context building ──────────────────────────────────────────────────────

    def _estimate_tokens(self, messages: list[dict]) -> int:
        if not self._enc:
            return sum(len((m.get("content") or "").split()) for m in messages)
        return sum(
            len(self._enc.encode(m.get("content") or ""))
            for m in messages
        )

    def build_messages(self, base_messages: list[dict]) -> list[dict]:
        """
        Return base_messages plus injected context blocks.
        Trims oldest KB slots if the token budget is exceeded.
        """
        injections: list[dict] = []

        if self._customer_ctx:
            injections.append({
                "role": "system",
                "content": self._customer_ctx,
            })

        kb_injections = [
            {"role": "system", "content": f"[KB] {s['content']}"}
            for s in self._kb_slots
        ]
        injections.extend(kb_injections)

        combined = base_messages + injections

        # Trim KB slots one-by-one until within budget
        while (self._estimate_tokens(combined) > MAX_CONTEXT_TOKENS
               and self._kb_slots):
            self._kb_slots.pop(0)
            kb_injections = [
                {"role": "system", "content": f"[KB] {s['content']}"}
                for s in self._kb_slots
            ]
            injections = ([{"role": "system", "content": self._customer_ctx}]
                          if self._customer_ctx else []) + kb_injections
            combined = base_messages + injections

        return combined
