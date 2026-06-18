"""
One-shot script: compute and store intent_embedding for all workflows that have NULL.

Run from backend/ with the venv active:
  python scripts/compute_workflow_embeddings.py
"""
import asyncio
import json
import os
import sys

# Add backend to path so relative imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import AsyncSessionLocal
from knowledge.embeddings import init_embeddings
from sqlalchemy import text

init_embeddings()


async def _embed(texts: list[str]) -> list[float]:
    from knowledge.embeddings import embed_texts
    vecs = await embed_texts(texts)
    if not vecs:
        raise ValueError("embed_texts returned no vectors")
    # Average all vectors into one
    dim = len(vecs[0])
    avg = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
    return avg


async def main() -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            text("SELECT id, name, intent_definition, few_shot_examples "
                 "FROM workflow_definitions WHERE intent_embedding IS NULL ORDER BY name")
        )).mappings().all()

    if not rows:
        print("All workflows already have embeddings — nothing to do.")
        return

    print(f"Computing embeddings for {len(rows)} workflow(s)...")
    for row in rows:
        wf_id   = row["id"]
        name    = row["name"]
        idef    = row["intent_definition"] or ""
        fse     = row["few_shot_examples"] or []
        if isinstance(fse, str):
            fse = json.loads(fse)

        texts = [idef] + fse
        texts = [t for t in texts if t.strip()]
        if not texts:
            print(f"  SKIP  {name!r} — no text to embed")
            continue

        try:
            vec = await _embed(texts)
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("UPDATE workflow_definitions "
                         "SET intent_embedding = CAST(:emb AS jsonb), updated_at = NOW() "
                         "WHERE id = :id"),
                    {"emb": json.dumps(vec), "id": wf_id},
                )
                await db.commit()
            print(f"  OK    {name!r} — {len(vec)}-dim vector stored")
        except Exception as exc:
            print(f"  FAIL  {name!r} — {exc}")

    print("Done. Restart the agent worker (or it will reload on next call) to pick up new embeddings.")


if __name__ == "__main__":
    asyncio.run(main())
