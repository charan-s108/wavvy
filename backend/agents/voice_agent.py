"""
Voice agent system prompt — Wavvy self-demo CCaaS platform.
LLM is a response renderer only. Used by context_builder.build_llm_messages().
Keep in sync with context_builder.SYSTEM_PROMPT — single source of truth is context_builder.
"""
from voice.context_builder import SYSTEM_PROMPT  # noqa: F401 — re-export for legacy callers
