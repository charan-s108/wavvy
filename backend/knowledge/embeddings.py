"""
Embeddings via HuggingFace Inference API — sentence-transformers/all-MiniLM-L6-v2.
384-dim vectors. Zero local GPU/CPU cost. Model is already hosted on HuggingFace.
"""
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
_HF_API_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{EMBED_MODEL}"


def init_embeddings(_openai_client=None) -> None:
    """No-op — embeddings are served by HF Inference API, always ready."""
    logger.info("Embeddings ready: %s (HuggingFace Inference API)", EMBED_MODEL)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via HF Inference API. Returns list of 384-dim vectors."""
    if not texts:
        return []
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _embed_via_api(texts, client)


async def embed_single(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]


async def _embed_via_api(texts: list[str], client: httpx.AsyncClient) -> list[list[float]]:
    headers = {"Content-Type": "application/json"}
    if settings.hf_token:
        headers["Authorization"] = f"Bearer {settings.hf_token}"

    resp = await client.post(
        _HF_API_URL,
        headers=headers,
        json={"inputs": texts},
    )
    resp.raise_for_status()
    result = resp.json()

    # HF returns shape [n, dim] for batch — normalise any 3-D response
    if result and isinstance(result[0][0], list):
        result = [row[0] for row in result]
    return result
