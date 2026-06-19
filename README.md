# Wavvy — Sense Intent. Drive Resolution.

> **Live demo:** [landing-seven-eta-51.vercel.app](https://landing-seven-eta-51.vercel.app) · Agent Desktop: [wavvy-agent.vercel.app](https://wavvy-agent.vercel.app) · Admin: [wavvy-admin-mu.vercel.app](https://wavvy-admin-mu.vercel.app) · Backend: [brocode12-wavvy.hf.space](https://brocode12-wavvy.hf.space)

Wavvy is a real-time voice AI CCaaS platform — LiveKit WebRTC · Deepgram STT · OpenAI LLM · Deepgram TTS · RAG. It ships with **Fin**, a fintech voice agent demo that showcases the full platform: OTP-gated tool execution, hybrid knowledge retrieval, Companion AI for human agents, and human-in-the-loop escalation.

Wavvy is the infrastructure. Fin is the demo. Swap the system prompt, tools, and KB — you have a new product for any domain.

---

## Four Applications, One Backend

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  WAVVY PLATFORM                                                              │
│                                                                              │
│  App 1  Landing + Voice     :5173   Customer entry — speak to Fin            │
│  App 2  Agent Desktop       :5174   Human agents receive escalated calls     │
│  App 3  Admin          :5175   QA scores, coaching packs, KB upload     │
│  Backend FastAPI + asyncio  :8000   Shared by all three frontends            │
│                                                                              │
│  LIVE CALL FLOW                                                              │
│                                                                              │
│  Customer speaks  →  LiveKit WebRTC room  →  voice AI worker (asyncio task) │
│  Worker: Deepgram STT → gpt-4o-mini LLM → Deepgram Aura TTS                │
│                                                                              │
│  Escalation:                                                                 │
│  Voice AI triggers handoff  →  Agent Desktop receives incoming_call event   │
│  Human agent joins LiveKit room  →  AI goes silent  →  agent handles call   │
│                                                                              │
│  Post-call (background task):                                                │
│  QA agent scores transcript  →  Admin dashboard updates                │
└──────────────────────────────────────────────────────────────────────────────┘
```

Each call is an isolated asyncio task. No shared mutable state between calls. 100+ concurrent calls never block each other.

---

## Voice Pipeline

```
Customer speaks
      │  WebRTC audio
      ▼
LiveKit Cloud room
      │
      ▼
LiveKit Agents SDK worker (per call)
  ├── Silero VAD           — voice activity detection, barge-in
  ├── Deepgram nova-2 STT  — streaming transcription, endpointing_ms=400
  ├── WavvyAgent (LLM)     — gpt-4o-mini, stage-gated tools, KB injection
  └── Deepgram Aura-2 TTS  — aura-2-thalia-en, sentence-chunked streaming
```

The LLM layer (`voice/wavvy_agent.py`) applies five optimizations on every turn before calling OpenAI:

| Optimization | What it does |
|---|---|
| Stage-gated tools | Only the tools valid for the current conversation stage are sent to the LLM — no opportunity to call write tools before OTP |
| History compression | Last 20 turns kept; summary injected as a compact context string |
| Stage-aware customer context | Customer profile injected in full at VERIFICATION; trimmed to hints at other stages |
| On-demand RAG | KB search runs in parallel with VAD; result awaited only when needed |
| Semantic KB dedup | Same chunk fingerprint is never injected twice in one call |

---

## Conversation State Machine

Every call progresses through server-authoritative stages. The LLM never decides stage transitions — it only talks.

```
GREETING  →  DISCOVERY  →  VERIFICATION  →  TOOL_EXECUTION  →  RESOLUTION  →  ENDED
                                  ↓
                            ESCALATION  (any stage → escalation if triggered)
```

**Stage gates enforce:**
- `send_otp` / `verify_otp` only callable from VERIFICATION
- Write tools (`initiate_refund`, `raise_dispute`, `report_fraud`, `unlock_account`) only callable after OTP verified (TOOL_EXECUTION)
- `escalate_to_human` always available, but blocked until customer identity is collected

---

## OTP Flow

Authentication is a deterministic server-side state machine. The LLM cannot skip, fake, or bypass it.

```
DISCOVERY  →  send_otp()  →  CODE_SENT
                                  │  verify_otp() — 6-digit, max 3 attempts, 5-min expiry
                                  ▼
                            VERIFIED  →  write tools unlock
                                  │  3 failures
                                  ▼
                            LOCKED  →  escalate_to_human() forced
```

After `verify_otp` succeeds, the session transitions to `TOOL_EXECUTION` and the action tool the customer originally requested is called immediately without a second verbal confirmation.

---

## Tools Available to Fin

All 15 tools pass through stage permission checks before execution:

| Tool | Stage required | Purpose |
|---|---|---|
| `verify_account` | GREETING | Look up customer by phone, load profile + transactions |
| `lookup_transaction` | VERIFICATION+ | Exact TXN-XXXX lookup |
| `search_transactions` | VERIFICATION+ | Natural language transaction search |
| `send_otp` | VERIFICATION | Send 6-digit OTP |
| `verify_otp` | VERIFICATION | Verify OTP, unlock write tools |
| `initiate_refund` | TOOL_EXECUTION | Refund a failed transaction |
| `raise_dispute` | TOOL_EXECUTION | Dispute a completed transaction |
| `report_fraud` | TOOL_EXECUTION | Flag an unauthorized transaction |
| `unlock_account` | TOOL_EXECUTION | Remove a manual account hold |
| `check_payment_status` | VERIFICATION+ | Check if a payment is stuck |
| `get_account_holds` | VERIFICATION+ | List active holds on the account |
| `get_refund_status` | VERIFICATION+ | Check status of an in-progress refund |
| `get_dispute_status` | VERIFICATION+ | Check status of a filed dispute |
| `escalate_to_human` | always | Transfer to human agent with full context |
| `cancel_escalation` | after escalation | Cancel a pending escalation |

---

## Agent Desktop — Escalation Handoff

When `escalate_to_human` fires:

1. FastAPI emits an `EscalationRequestedEvent` over `/ws/agent` to all connected agents
2. The agent desktop receives `incoming_call` with a full handoff bundle (customer profile, transcript, transaction data, holds, refund/dispute history)
3. Human agent clicks **Join** → POSTs to `/api/livekit/agent-join` → joins the LiveKit room
4. Fin detects the agent participant → `session.human_joined = True` → `llm_node` returns empty → Fin goes completely silent
5. STT continues running — agent console shows customer speech in real time
6. Human agent types responses → `/api/calls/{id}/agent-say` → text-to-TTS via Deepgram Aura → customer hears the agent
7. Call ends → ACW summary generated → QA auto-scores within 5s

---

## Hybrid Knowledge Base

```
/api/kb/upload  →  document_parser  →  tiktoken chunker
                                             │
                          ┌──────────────────┼──────────────────┐
                          ▼                  ▼                  ▼
                    Dense index       BM25 index        Entity pair index
                  (ChromaDB +       (BM25Okapi,       (regex extraction,
                all-MiniLM-L6-v2)   in-memory)          co-occurrence)
```

At query time, all three scores are fused with Reciprocal Rank Fusion (k=60 for dense/BM25, k=40 for entity hits — entity matches score ~1.5× higher). Results injected into the LLM context only when relevance exceeds the threshold.

Local embeddings (`all-MiniLM-L6-v2`, 384-dim) run on CPU via `asyncio.run_in_executor` — the async event loop is never blocked. Zero API cost, loaded once at startup.

---

## Post-Call QA

Every call is auto-scored on 6 rubric dimensions within 5 seconds of ending:

- **Guardrail adherence** — did the AI stay in scope?
- **Resolution rate** — was the customer's issue resolved?
- **Containment** — resolved without human escalation?
- **Caller satisfaction** — inferred from transcript tone
- **Handle time** — efficient, no excessive repetition?
- **Disclosure** — did Fin identify itself as AI?

Scores appear in the Admin dashboard. Coaching packs are generated from real scored calls (minimum 3 calls per agent).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice transport | LiveKit Cloud (WebRTC, free tier: 5k min/mo) |
| STT | Deepgram nova-2 (`endpointing_ms=400`) |
| VAD | Silero (via LiveKit Agents SDK plugin) |
| LLM | OpenAI gpt-4o-mini |
| TTS | Deepgram Aura-2 `aura-2-thalia-en` |
| Voice framework | LiveKit Agents SDK v1.5 |
| Backend | FastAPI + asyncio, uvicorn |
| Database | PostgreSQL via asyncpg + SQLAlchemy async |
| Migrations | Alembic |
| Vector DB | ChromaDB (PersistentClient, local) |
| Embeddings | all-MiniLM-L6-v2 (local CPU, zero cost) |
| Frontend | React 18 + Vite + Tailwind CSS |
| Auth | JWT (PyJWT) + bcrypt |
| Orchestration | Custom action registry + incident/resolution logging |

---

## Quick Start

### Prerequisites

- Python 3.11+, Node 18+, Docker (PostgreSQL only)
- LiveKit Cloud account (free) — [cloud.livekit.io](https://cloud.livekit.io)
- Deepgram account (free) — [deepgram.com](https://deepgram.com)
- OpenAI API key

### 1. PostgreSQL

```bash
docker compose up -d
# Postgres runs on port 5433 (5432 may be taken by a local instance)
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in OPENAI_API_KEY, LIVEKIT_*, DEEPGRAM_API_KEY

alembic upgrade head
python seed.py            # seed 10 demo customers + 2 agents

uvicorn main:app --port 8000 --reload

# LiveKit Agents worker (separate terminal)
python -m voice.agent_worker dev     # local dev (auto-reloads)
```

### 3. Frontend — three terminals

```bash
cd frontend/landing    && npm install && npm run dev   # :5173
cd frontend/agent      && npm install && npm run dev   # :5174
cd frontend/admin && npm install && npm run dev   # :5175
```

### 4. Agent console login

| Email | Password |
|---|---|
| `ananya@fin.ai` | `wavvy2026` |
| `david@fin.ai` | `wavvy2026` |

---

## Deploy to Production

### Backend → HuggingFace Space (`brocode12/wavvy`)

The HF Space only needs the `backend/` folder. Push it as a subtree so the MP4
demo videos in `frontend/` never touch HF:

```bash
# First time or after any backend change
git push hf $(git subtree split --prefix=backend main):main --force
```

After pushing, update HF secrets (picks up any new values from `backend/.env`):

```bash
backend/.venv/bin/python push_hf_secrets.py
```

### Frontends → Vercel

Each frontend is a separate Vercel project. Re-deploy all three after any
frontend change (env vars are baked in at build time):

```bash
# Landing page  →  https://landing-seven-eta-51.vercel.app
cd frontend/landing
VITE_BACKEND_HTTP_URL=https://brocode12-wavvy.hf.space \
VITE_LIVEKIT_URL=wss://wavvy-prod.livekit.cloud \
vercel build --prod && vercel deploy --prebuilt --prod

# Agent Desktop  →  https://wavvy-agent.vercel.app
cd frontend/agent
VITE_BACKEND_HTTP_URL=https://brocode12-wavvy.hf.space \
VITE_BACKEND_WS_URL=wss://brocode12-wavvy.hf.space \
vercel build --prod && vercel deploy --prebuilt --prod

# Admin Console  →  https://wavvy-admin-mu.vercel.app
cd frontend/admin
VITE_BACKEND_HTTP_URL=https://brocode12-wavvy.hf.space \
VITE_BACKEND_WS_URL=wss://brocode12-wavvy.hf.space \
vercel build --prod && vercel deploy --prebuilt --prod
```

> **Note:** `vercel pull --yes --environment production` must have been run once
> in each frontend directory to link it to the Vercel project. This is already
> done — the `.vercel/project.json` files are gitignored locally.

---

## Environment Variables

`backend/.env`:

```env
# LLM
OPENAI_API_KEY=sk-...

# Voice pipeline
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxx
LIVEKIT_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPGRAM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# TTS (optional — Deepgram Aura used if not set)
ELEVENLABS_API_KEY=sk_...

# Database
DATABASE_URL=postgresql+asyncpg://wavvy:wavvy@localhost:5433/wavvy
CHROMA_PERSIST_DIR=./chroma_db

# CORS
FRONTEND_LANDING_URL=http://localhost:5173
FRONTEND_AGENT_URL=http://localhost:5174
FRONTEND_ADMIN_URL=http://localhost:5175

ENVIRONMENT=development
SECRET_KEY=change-in-production
```

`frontend/*/.env`:

```env
VITE_BACKEND_WS_URL=ws://localhost:8000
VITE_BACKEND_HTTP_URL=http://localhost:8000
```

---

## Demo Seed Data

10 customers covering every supported scenario:

| Customer | Phone | Scenario |
|---|---|---|
| Neha Reddy | +918765432109 | Amazon refund already in progress (TXN-6540) |
| Raj Patel | +917654321098 | Active fraud case FRAUD-202605-0001 |
| Mike Torres | +12126543210 | Account locked — manual hold, unlock flow |
| Sarah Chen | +14086543210 | KYC hold, cannot self-serve — escalate |
| Priya Iyer | +919812345601 | Two identical Swiggy ₹450 charges — disambiguation |
| Kabir Singh | +918812345602 | Refund flow (Kabir-owned transactions) |
| Zara Hussain | +917712345603 | Unauthorized charge — fraud report flow |
| Aryan Sharma | +919911223344 | Fraud report then escalation in one session |
| Maya Patel | +918855667788 | Multiple issues: pending payment + failed charge |
| Ayaan Khan | +919876543210 | Failed Flipkart payment — check payment status |

Reset to clean state before any demo:

```bash
python seed.py --reset   # truncates all tables, re-seeds fresh
python seed.py           # upsert-only (safe mid-session)
```

---

## API Reference

```
GET   /api/health

# Voice
POST  /api/livekit/start-call          Create room + issue JWT + start agent worker
POST  /api/livekit/agent-join          Human agent joins escalated call room
POST  /api/calls/{id}/agent-say        Human agent text → TTS → customer hears

# Auth
POST  /api/auth/agent-login            Returns JWT for agent console

# Calls
GET   /api/calls                       Call history
GET   /api/calls/{id}                  Call detail + transcript
POST  /api/calls/{id}/end              Mark call ended

# Knowledge Base
POST  /api/kb/upload                   Upload PDF / DOCX / TXT
GET   /api/kb/documents                List indexed documents
GET   /api/kb/search?q=query           Test search
DELETE /api/kb/documents/{doc_id}      Remove document

# QA + Coaching
GET   /api/eval/{call_id}              QA scores for a call
POST  /api/eval/trigger/{call_id}      Manually trigger QA scoring
GET   /api/coaching/packs/{agent_id}   Coaching packs
POST  /api/coaching/generate/{agent_id} Generate coaching pack (min 3 scored calls)

# Dashboard
GET   /api/dashboard/live-calls        Active calls + agent status
GET   /api/dashboard/kpis              Today's aggregate metrics

# Orchestration
POST  /api/orchestration/action        Human agent executes an action (approve refund, mark KYC verified, etc.)

# WebSockets
WS    /ws/agent                        Agent desktop real-time events
WS    /ws/admin                   Admin dashboard real-time events
```

---

## Project Structure

```
wavvy/
├── docker-compose.yml              PostgreSQL for local dev
│
├── backend/
│   ├── main.py                     FastAPI app, CORS, startup
│   ├── config.py                   pydantic-settings from .env
│   ├── config_loader.py            Multi-tenant config (Fin / Wavvy demo)
│   ├── database.py                 Async engine, pool_size=20
│   ├── seed.py                     Demo data + --reset flag
│   │
│   ├── voice/
│   │   ├── agent_session.py        LiveKit Agents job entrypoint, AgentSession setup
│   │   ├── wavvy_agent.py          WavvyAgent: llm_node with 5 optimizations
│   │   ├── agent_tools.py          15 function_tool definitions, OTP normalizer
│   │   ├── agent_worker.py         LiveKit worker process entrypoint
│   │   ├── context_builder.py      System prompt + context assembly per turn
│   │   ├── intent_router.py        Conversation stage + intent detection
│   │   └── ...                     sentiment, barge-in, reminder service, tracer
│   │
│   ├── session/
│   │   ├── call_session.py         CallSession dataclass + ACTIVE_CALLS dict
│   │   ├── conversation_state.py   ConversationStage state machine
│   │   └── auth_state.py           OTP / TwoFactorState machine
│   │
│   ├── tools/
│   │   ├── wavvy_tools.py          15 tool implementations (DB queries)
│   │   └── crm_query.py            KB hybrid search helper
│   │
│   ├── orchestration/
│   │   ├── engine.py               Human agent action execution + audit log
│   │   └── action_registry.py      Supported actions (mark_kyc_verified, etc.)
│   │
│   ├── agents/
│   │   ├── qa_agent.py             Post-call QA scoring (gpt-4o-mini)
│   │   ├── companion_agent.py      Real-time coaching for human agents
│   │   └── coaching_agent.py       Batch coaching pack generator
│   │
│   ├── knowledge/
│   │   ├── kb_manager.py           Ingest + hybrid search (dense+BM25+entity)
│   │   ├── embeddings.py           all-MiniLM-L6-v2 local embeddings
│   │   └── document_parser.py      PDF, DOCX, TXT parser
│   │
│   ├── guardrails/                 Tool permission checks, rate limits, scope
│   ├── security/                   PII sanitizer
│   ├── models/                     SQLAlchemy ORM models
│   ├── migrations/                 Alembic versions
│   └── routers/                    FastAPI route handlers
│
└── frontend/
    ├── landing/                    App 1 — React + Vite (:5173)
    ├── agent/                      App 2 — React + Vite (:5174)
    └── admin/                     App 3 — React + Vite (:5175)
```

---

## Agent Desktop — Simulation Mode

The Agent Desktop ships with a built-in simulation mode for offline demos. Press **Space** or **Enter** to advance through 11 pre-scripted steps (incoming call → investigation → OTP → refund/unlock → ACW). No backend or LiveKit connection required.

Enable/disable: `frontend/agent/src/simulation.js` + the three `// SIM` blocks in `App.jsx`.

---

## Contributing

Issues and PRs are welcome. When contributing:

- Backend: all handlers must be `async def`. No sync DB calls.
- Tools: every new tool must be registered in `guardrails/tool_permissions.py` with stage requirements.
- Frontend: keep all three apps as separate Vite projects — no shared bundling.
- Tests: `cd backend && .venv/bin/pytest tests/test_wavvy.py -v` before opening a PR.

---

## License

MIT

---

<div align="center">

**Wavvy** · Sense Intent. Drive Resolution.

Built with [LiveKit](https://livekit.io) · [Deepgram](https://deepgram.com) · [OpenAI](https://openai.com) · [ChromaDB](https://trychroma.com) · [FastAPI](https://fastapi.tiangolo.com) · [React](https://react.dev)

</div>
