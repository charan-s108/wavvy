"""
Local embeddings via sentence-transformers all-MiniLM-L6-v2.
Zero API cost. 384-dim vectors. Runs on CPU in a thread pool so the
async event loop is never blocked.
"""
import asyncio
import functools
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_model = None
EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384


def init_embeddings(_openai_client=None) -> None:
    """Load the local model once at startup. Signature compatible with old init_embeddings(openai_client)."""
    global _model
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading local embedding model: {EMBED_MODEL}")
    _model = SentenceTransformer(EMBED_MODEL)
    logger.info(f"Embeddings initialized: {EMBED_MODEL} ({EMBED_DIM}-dim, local, zero API cost)")


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns list of float vectors. Non-blocking."""
    if not _model:
        raise RuntimeError("embeddings not initialized — call init_embeddings() first")
    if not texts:
        return []
    loop = asyncio.get_event_loop()
    vectors = await loop.run_in_executor(
        None,
        functools.partial(_model.encode, texts, convert_to_numpy=True, show_progress_bar=False)
    )
    return vectors.tolist()


async def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    results = await embed_texts([text])
    return results[0]
