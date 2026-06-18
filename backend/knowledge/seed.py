"""
Seed fin_support KB collection from backend/knowledge/seed_docs/fin/*.md

Usage (from backend/):
    python -m knowledge.seed

kb_collection is reserved for user-uploaded policies via the Admin Dashboard.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def main() -> None:
    # Bootstrap: DB engine + OpenAI client + ChromaDB + kb_manager
    from database import reinit_engine
    reinit_engine()

    import chromadb
    from openai import AsyncOpenAI
    from config import settings
    from knowledge import embeddings as embeddings_module
    from knowledge import kb_manager as kb_manager_module

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    embeddings_module.init_embeddings(openai_client)

    chroma_client = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    kb_collection   = chroma_client.get_or_create_collection("kb_collection")
    fin_collection  = chroma_client.get_or_create_collection("fin_support")
    calls_collection = chroma_client.get_or_create_collection("calls_collection")

    kb_manager_module.init_kb_manager(
        kb_col=kb_collection,
        calls_col=calls_collection,
        _openai_client=openai_client,
        collections_dict={"kb_collection": kb_collection, "fin_support": fin_collection},
    )

    fin_dir = Path(__file__).parent / "seed_docs" / "fin"
    fin_docs = sorted(fin_dir.glob("*.md"))
    if not fin_docs:
        print("ERROR: No .md files found in seed_docs/fin/ — nothing to seed.")
        sys.exit(1)

    print(f"\nSeeding {len(fin_docs)} Fin docs → fin_support:")

    # Clear existing chunks so re-seeding is idempotent
    existing = fin_collection.count()
    if existing > 0:
        all_ids = fin_collection.get(include=[])["ids"]
        fin_collection.delete(ids=all_ids)
        print(f"  (cleared {existing} existing chunks)")

    total_chunks = 0
    for doc_path in fin_docs:
        doc_id, n_chunks = await kb_manager_module.ingest_document(
            file_path=doc_path,
            filename=doc_path.name,
            file_type="md",
            category="fin_support",
            collection_name="fin_support",
        )
        print(f"  [{total_chunks + 1}..{total_chunks + n_chunks}]  {doc_path.name}  ({n_chunks} chunks)")
        total_chunks += n_chunks

    print(f"\nKB seed complete — {total_chunks} chunks in fin_support.")
    print("Note: kb_collection is reserved for user-uploaded policies via the Admin Dashboard.")


if __name__ == "__main__":
    asyncio.run(main())
