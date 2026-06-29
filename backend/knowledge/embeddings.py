"""
Dual-mode embedding backend.

  ENVIRONMENT=development  →  local sentence-transformers (model cached in ~/.cache/huggingface)
  ENVIRONMENT=production   →  HuggingFace Inference API   (HTTP, HF_TOKEN, no Docker size cost)

Both modes produce L2-normalised 384-dim vectors from all-MiniLM-L6-v2,
matching the vectors already stored in ChromaDB.

Thread-safety note
------------------
`init_embeddings()` may be called from a background daemon thread (see
prewarm in agent_session.py) to avoid blocking the LiveKit SDK's process
initialization IPC timeout.  `_embed_local` waits for `_model_ready` so
any call that arrives before the model finishes loading blocks in a thread
pool rather than failing immediately.
"""
import asyncio
import logging
import math
import os
import threading
from functools import partial

import httpx

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM   = 384
_HF_API_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{EMBED_MODEL}"

# Populated by init_embeddings() — may be called from a background thread.
_model     = None   # SentenceTransformer instance (dev only)
_hf_token  = None   # HF bearer token (prod only)
_use_api   = False  # True when running in production
_model_ready   = threading.Event()   # set once the model is usable
_init_lock     = threading.Lock()    # prevents duplicate initialization


def init_embeddings(_openai_client=None) -> None:
    """
    Initialize the embedding backend.  Safe to call from any thread; the
    second call is a no-op.  _openai_client accepted for compatibility.
    """
    global _model, _hf_token, _use_api

    with _init_lock:
        if _model_ready.is_set():
            return  # already done

        environment = os.getenv("ENVIRONMENT", "development").lower()

        if environment == "production":
            _hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
            if not _hf_token:
                raise RuntimeError(
                    "ENVIRONMENT=production but HF_TOKEN is not set. "
                    "Add it as a secret in HuggingFace Space settings."
                )
            _use_api = True
            logger.info("Embeddings: HF Inference API (production) — model=%s", EMBED_MODEL)
        else:
            try:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(EMBED_MODEL.split("/")[-1])
                _use_api = False
                logger.info(
                    "Embeddings: local sentence-transformers (dev) — model=%s, dim=%d",
                    EMBED_MODEL, EMBED_DIM,
                )
            except ImportError:
                _hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
                if not _hf_token:
                    raise RuntimeError(
                        "sentence-transformers is not installed and HF_TOKEN is not set. "
                        "Either: pip install sentence-transformers  OR  set HF_TOKEN."
                    )
                _use_api = True
                logger.warning("sentence-transformers not installed; using HF Inference API as fallback")

        _model_ready.set()


def init_embeddings_background() -> None:
    """Start model loading in a daemon thread so the caller returns immediately.

    Useful in prewarm() where blocking would exceed the LiveKit SDK's process
    initialization IPC timeout (~10s).  By the time the first user utterance
    arrives the model will already be loaded.
    """
    if _model_ready.is_set():
        return
    t = threading.Thread(target=init_embeddings, daemon=True, name="embed-init")
    t.start()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return L2-normalised 384-dim embeddings for a batch of texts."""
    if not texts:
        return []

    if _use_api:
        return await _embed_via_hf_api(texts)
    else:
        return await _embed_local(texts)


async def embed_single(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]


# ── Local inference (dev) ─────────────────────────────────────────────────────

def _wait_for_model(timeout: float = 60.0) -> None:
    """Block the calling thread until the model is ready (or timeout expires)."""
    if not _model_ready.wait(timeout):
        raise RuntimeError(
            f"Embedding model not ready after {timeout}s. "
            "Call init_embeddings() or init_embeddings_background() at startup."
        )


async def _embed_local(texts: list[str]) -> list[list[float]]:
    loop = asyncio.get_running_loop()

    # If the model is still loading (background thread), wait in the executor
    # so the event loop is not blocked.
    if not _model_ready.is_set():
        await loop.run_in_executor(None, _wait_for_model)

    if _model is None:
        raise RuntimeError("Local embedding model not loaded — call init_embeddings() first")

    embeddings = await loop.run_in_executor(
        None,
        partial(_model.encode, texts, normalize_embeddings=True),
    )
    return embeddings.tolist()


# ── HF Inference API (production) ────────────────────────────────────────────

async def _embed_via_hf_api(texts: list[str]) -> list[list[float]]:
    """
    Calls the HF feature-extraction pipeline API and L2-normalises the result
    to match the vectors stored by local sentence-transformers (normalize_embeddings=True).
    Retries up to 3 times with exponential backoff for transient DNS/network failures.
    """
    headers = {"Authorization": f"Bearer {_hf_token}"}
    payload = {"inputs": texts, "options": {"wait_for_model": True}}

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(_HF_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
            break
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s
    else:
        raise last_exc  # type: ignore[misc]

    raw: list[list[float]] = resp.json()

    if raw and isinstance(raw[0], float):
        raw = [raw]

    return [_l2_normalize(vec) for vec in raw]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]
