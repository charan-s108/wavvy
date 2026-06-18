import logging
import warnings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s — %(message)s")
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

warnings.filterwarnings(
    "ignore",
    message="resource_tracker: There appear to be",
    category=UserWarning,
)

from contextlib import asynccontextmanager

import chromadb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from sqlalchemy import text

from config import settings
from config_loader import load_active_config
from database import AsyncSessionLocal
from voice import sentiment as sentiment_module
from tools import crm_query as crm_query_module
from agents import companion_agent as companion_module
from agents import qa_agent as qa_agent_module
from agents import coaching_agent as coaching_agent_module
from agents import investigation_agent as investigation_module
from knowledge import embeddings as embeddings_module
from knowledge import kb_manager as kb_manager_module


logger = logging.getLogger(__name__)


async def _backfill_workflow_embeddings() -> None:
    """Compute and persist intent embeddings for workflows seeded with NULL vectors.

    Called once at startup as a background task.  Any workflow whose
    intent_embedding column is NULL gets an embedding computed from its
    intent_definition + few_shot_examples and stored in the DB.  The in-memory
    workflow cache is reloaded afterward so /api/workflows/internal/match can
    start matching immediately.
    """
    try:
        from config_loader import get_active_workflows, reload_workflows
        from knowledge.embeddings import embed_texts
        from database import AsyncSessionLocal
        from sqlalchemy import text as _text
        import json as _json

        workflows = get_active_workflows()
        missing = [wf for wf in workflows if not wf.intent_embedding]
        if not missing:
            logger.info("workflow embeddings: all %d workflows already embedded", len(workflows))
            return

        logger.info("workflow embeddings: backfilling %d workflow(s) with NULL embedding", len(missing))
        updated = 0
        async with AsyncSessionLocal() as db:
            for wf in missing:
                texts = [t for t in ([wf.intent_definition] + wf.few_shot_examples) if t.strip()]
                if not texts:
                    continue
                try:
                    vectors = await embed_texts(texts)
                    if not vectors:
                        continue
                    n   = len(vectors)
                    dim = len(vectors[0])
                    avg = [sum(v[i] for v in vectors) / n for i in range(dim)]
                    await db.execute(
                        _text(
                            "UPDATE workflow_definitions "
                            "SET intent_embedding = CAST(:emb AS jsonb), updated_at = NOW() "
                            "WHERE id = :id"
                        ),
                        {"emb": _json.dumps(avg), "id": wf.id},
                    )
                    updated += 1
                    logger.info("workflow embeddings: embedded '%s' (id=%s)", wf.name, wf.id)
                except Exception:
                    logger.exception("workflow embeddings: failed for workflow %s", wf.id)

            await db.commit()

        if updated:
            await reload_workflows()
            logger.info(
                "workflow embeddings: backfilled %d/%d; cache reloaded",
                updated, len(missing),
            )
    except Exception:
        logger.exception("_backfill_workflow_embeddings: unexpected error (non-fatal)")


async def _backfill_kb_postgres(collections: dict) -> None:
    """
    Sync kb_documents (PostgreSQL) from ChromaDB at startup.

    Documents ingested directly (seed scripts, ingest_document() calls that
    bypassed the upload endpoint) exist in ChromaDB but have no PostgreSQL row.
    GET /api/kb/documents reads from PostgreSQL, so the frontend shows nothing.
    This inserts any missing rows with status='ready'.

    Deduplicates by filename — when the same file appears in multiple collections
    (e.g. kb_collection + fin_support both seeded from the same source), only one
    row is written per unique filename.
    """
    import uuid as _uuid

    # Collect unique docs by filename (first-seen wins across all collections)
    # key: filename → {doc_id, file_type, category, chunk_count}
    by_filename: dict[str, dict] = {}
    for col_name, col in collections.items():
        try:
            if col.count() == 0:
                continue
            results = col.get(include=["metadatas"])
            for meta in (results.get("metadatas") or []):
                doc_id   = meta.get("doc_id", "")
                filename = meta.get("filename", "")
                if not doc_id or not filename:
                    continue
                if filename not in by_filename:
                    by_filename[filename] = {
                        "doc_id":     doc_id,
                        "file_type":  meta.get("file_type", ""),
                        "category":   meta.get("category", "general"),
                        "chunk_count": 0,
                    }
                if by_filename[filename]["doc_id"] == doc_id:
                    by_filename[filename]["chunk_count"] += 1
        except Exception as exc:
            logger.warning("KB backfill: could not read collection %s: %s", col_name, exc)

    if not by_filename:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT filename FROM kb_documents"))
        existing_filenames = {str(row[0]) for row in result.fetchall()}

        inserted = 0
        for filename, info in by_filename.items():
            if filename in existing_filenames:
                continue
            try:
                await db.execute(
                    text("""
                        INSERT INTO kb_documents (id, filename, file_type, category, chunk_count, status)
                        VALUES (:id, :fn, :ft, :cat, :cc, 'ready')
                        ON CONFLICT (id) DO UPDATE SET
                            chunk_count = EXCLUDED.chunk_count,
                            status      = 'ready'
                    """),
                    {
                        "id":  _uuid.UUID(info["doc_id"]),
                        "fn":  filename,
                        "ft":  info["file_type"],
                        "cat": info["category"],
                        "cc":  info["chunk_count"],
                    },
                )
                inserted += 1
            except Exception as exc:
                logger.warning("KB backfill: failed to insert %s: %s", filename, exc)

        await db.commit()

    if inserted:
        logger.info("KB backfill: synced %d doc(s) from ChromaDB → kb_documents", inserted)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed DB on startup — idempotent upserts, safe to call every time.
    # Ensures agents + tenant config exist on a fresh Supabase instance.
    try:
        from seed import run_seed
        await run_seed()
    except Exception as _seed_err:
        logger.warning("Startup seed failed (non-fatal): %s", _seed_err)

    # Load active tenant config first — all voice/agent code depends on it
    await load_active_config()

    # Shared AsyncOpenAI client — one instance, async-safe
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Backfill missing intent embeddings for seeded workflows.
    # Workflows are seeded with intent_embedding=NULL (no embedding model at seed time).
    # Without embeddings, /api/workflows/internal/match returns {"matched": false} for every
    # utterance and no workflow ever triggers.  This one-time pass ensures every active
    # workflow has a valid vector before the first call arrives.
    import asyncio as _asyncio
    _asyncio.create_task(_backfill_workflow_embeddings())
    app.state.openai_client = openai_client
    sentiment_module.init_openai_client(openai_client)

    # ChromaDB — persistent collections (default + all tenant KB collections)
    chroma_client = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    app.state.chroma_client = chroma_client
    kb_collection = chroma_client.get_or_create_collection("kb_collection")
    fin_collection = chroma_client.get_or_create_collection("fin_support")
    calls_collection = chroma_client.get_or_create_collection("calls_collection")
    app.state.kb_collection = kb_collection
    app.state.calls_collection = calls_collection

    collections_dict = {
        "kb_collection": kb_collection,
        "fin_support": fin_collection,
    }

    # CRM query module needs the OpenAI client + ChromaDB collections
    crm_query_module.init_crm_query(openai_client, kb_collection, calls_collection)

    # Companion + QA + Investigation agents
    companion_module.init_companion_agent(openai_client)
    qa_agent_module.init_qa_agent(openai_client)
    coaching_agent_module.init_coaching_agent(openai_client)
    investigation_module.init_investigation_agent(openai_client)

    # Embeddings + KB manager
    embeddings_module.init_embeddings(openai_client)
    kb_manager_module.init_kb_manager(kb_collection, calls_collection, collections_dict=collections_dict)

    # Backfill PostgreSQL from ChromaDB — docs seeded directly into ChromaDB
    # (e.g. via seed scripts) never wrote a row to kb_documents, so the
    # frontend sees an empty list even though RAG has content.
    await _backfill_kb_postgres(collections_dict)

    # Agent connection registry
    app.state.connected_agents = {}

    # Start reminder loop — T-24h and T-1h email reminders for confirmed demos
    import asyncio as _asyncio
    from voice.reminder_service import start_reminder_loop
    reminder_task = _asyncio.create_task(start_reminder_loop())

    yield

    reminder_task.cancel()
    try:
        await reminder_task
    except _asyncio.CancelledError:
        pass

    await openai_client.close()


app = FastAPI(title="Wavvy API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from routers.livekit_router import router as livekit_router
from routers.ws_agent import router as agent_router
from routers.ws_admin import router as admin_ws_router
from routers.knowledge import router as knowledge_router
from routers.calls import router as calls_router
from routers.eval import router as eval_router
from routers.coaching import router as coaching_router
from routers.auth_router import router as auth_router
from routers.tenant_router import router as tenant_router
from routers.debug_router import router as debug_router
from routers.orchestration_router import router as orchestration_router
from routers.workflows_router import router as workflows_router

app.include_router(auth_router)
app.include_router(livekit_router)
app.include_router(agent_router)
app.include_router(admin_ws_router)
app.include_router(knowledge_router)
app.include_router(calls_router)
app.include_router(eval_router)
app.include_router(coaching_router)
app.include_router(tenant_router)
app.include_router(debug_router)
app.include_router(orchestration_router)
app.include_router(workflows_router)


@app.get("/api/health")
async def health():
    db_status = "disconnected"
    customer_count = 0
    agent_count = 0

    customer_count = 0
    agent_count = 0
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM customers"))
            customer_count = result.scalar()
            result = await session.execute(text("SELECT COUNT(*) FROM agent_profiles"))
            agent_count = result.scalar()
            db_status = "connected"
    except Exception:
        db_status = "disconnected"

    chroma_status = "disconnected"
    try:
        _ = app.state.kb_collection
        _ = app.state.calls_collection
        chroma_status = "connected"
    except Exception:
        pass

    return {
        "status": "ok",
        "db": db_status,
        "chroma": chroma_status,
        "customers_seeded": customer_count,
        "agents_seeded": agent_count,
    }
