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
from knowledge import embeddings as embeddings_module
from knowledge import kb_manager as kb_manager_module


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load active tenant config first — all voice/agent code depends on it
    await load_active_config()

    # Shared AsyncOpenAI client — one instance, async-safe
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
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

    # Companion + QA agents
    companion_module.init_companion_agent(openai_client)
    qa_agent_module.init_qa_agent(openai_client)
    coaching_agent_module.init_coaching_agent(openai_client)

    # Embeddings + KB manager
    embeddings_module.init_embeddings(openai_client)
    kb_manager_module.init_kb_manager(kb_collection, calls_collection, collections_dict=collections_dict)

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
from routers.ws_supervisor import router as supervisor_router
from routers.knowledge import router as knowledge_router
from routers.calls import router as calls_router
from routers.eval import router as eval_router
from routers.coaching import router as coaching_router
from routers.auth_router import router as auth_router
from routers.tenant_router import router as tenant_router
from routers.debug_router import router as debug_router
from routers.orchestration_router import router as orchestration_router

app.include_router(auth_router)
app.include_router(livekit_router)
app.include_router(agent_router)
app.include_router(supervisor_router)
app.include_router(knowledge_router)
app.include_router(calls_router)
app.include_router(eval_router)
app.include_router(coaching_router)
app.include_router(tenant_router)
app.include_router(debug_router)
app.include_router(orchestration_router)


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
