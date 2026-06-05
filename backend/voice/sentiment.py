"""
Per-turn sentiment scoring via GPT-4o-mini.
Returns a float 0.0 (very negative) to 1.0 (very positive).
"""
import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Shared AsyncOpenAI client — instantiated once in main.py and stored on app.state
# This module uses a module-level reference set at startup.
_client: AsyncOpenAI | None = None


def init_openai_client(client: AsyncOpenAI) -> None:
    global _client
    _client = client


async def score_sentiment(text: str) -> float:
    if not _client:
        return 0.7  # neutral-positive default when client not ready

    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": 'Score this customer message 0.0–1.0. Return ONLY: {"score": 0.0}',
                },
                {"role": "user", "content": text},
            ],
            max_tokens=10,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        return float(json.loads(raw)["score"])
    except Exception as exc:
        logger.warning(f"Sentiment scoring failed: {exc}")
        return 0.7
