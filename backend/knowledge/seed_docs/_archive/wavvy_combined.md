# Wavvy Demo KB — Archived

> **This file is an archive.** These documents were the original Wavvy product KB used during
> the Wavvy self-demo phase. They are no longer seeded into
> any ChromaDB collection. Kept here for reference only.
>
> Active KB is in `../fin/` — fintech support SOPs for the Fin agent.

---

<!-- SOURCE: wavvy_overview.md -->

# Wavvy — Open-Source CCaaS Platform

## What Is Wavvy?

Wavvy is an open-source Contact Center as a Service (CCaaS) platform. Any business can integrate Wavvy to deploy AI-powered customer workflows — voice AI agents, escalation routing, QA scoring, and supervisor analytics — within hours, not months.

Wavvy platform demonstrates how modern AI can power enterprise-grade contact centers using fully open-source infrastructure.

## The Core Idea

The demo you are experiencing right now IS Wavvy in action. The voice AI you are speaking with, the real-time knowledge retrieval happening in the background, the escalation handoff to a human agent — all of this is exactly what your contact center would provide to your customers after integrating Wavvy.

**The pitch:** "This call is Wavvy. What you are experiencing right now — you can deploy this for your contact center today."

## Four Applications, One Backend

Wavvy consists of four applications sharing a single FastAPI backend:

**App 1 — Landing Page (wavvy.vercel.app)**
Public marketing page with a pulsing call button. Clicking it opens a voice call modal where visitors speak directly to the Wavvy AI. This is the customer-facing layer of any CCaaS deployment.

**App 2 — Agent Desktop (wavvy-agent.vercel.app)**
Human agents receive escalated calls here. The Companion AI panel pre-loads context from the Voice AI conversation, shows a checklist of talking points, and surfaces relevant KB snippets. Agents pick up exactly where the AI left off.

**App 3 — Supervisor Dashboard (wavvy-supervisor.vercel.app)**
Quality assurance, live call monitoring, knowledge base management, agent coaching packs, and analytics. Supervisors see every call in real time and receive automated QA scores within seconds of call completion.

**Backend — FastAPI (Railway)**
REST API and WebSocket endpoints. Handles LiveKit room creation, Pipecat agent orchestration, ChromaDB knowledge retrieval, PostgreSQL persistence, and QA scoring. Fully async, 4-worker uvicorn, handles 100+ concurrent calls.

## Open-Source Commitment

Wavvy is fully open-source under MIT license. The complete codebase — pipeline, guardrails, KB system, agent prompts, and all four apps — is available on GitHub. Businesses can:
- Self-host for free (bring your own API keys)
- Use managed hosting starting at $299/month
- Customize every layer of the stack

## Who Uses Wavvy?

Wavvy is designed for:
- **Contact center operators** replacing legacy IVR with AI-powered automation
- **SaaS companies** adding a voice AI layer to their existing product
- **Developers** building custom voice agents without starting from scratch
- **Operations teams** needing real-time QA scoring and agent coaching

---

<!-- SOURCE: wavvy_features.md -->

# Wavvy Features

## Customer AI — Voice Agent

The Voice AI is the front line of every Wavvy deployment. It handles inbound calls end-to-end without human intervention for the majority of interactions.

**Deterministic Orchestration**
The LLM never decides what to do next. A Workflow Engine is the single source of truth. Intent classification, entity extraction, and tool dispatch are all deterministic. The LLM only polishes language — it never controls flow. This eliminates hallucinated actions and unpredictable behavior.

**FAST_RESPONSES (>80% of turns bypass LLM)**
Pricing questions, greetings, lead capture prompts, and confirmation messages are pre-written templates served in under 50ms. The LLM is only called for open-ended product Q&A and competitor comparisons.

**RAG-Powered Knowledge Base**
Every LLM turn is preceded by a KB search. Relevant documentation snippets are injected into context automatically. The KB uses a three-signal retrieval system: dense vector search (ChromaDB), BM25 keyword matching, and entity graph lookup — fused via Reciprocal Rank Fusion for higher precision.

**Lead Capture (Conversational)**
When a prospect wants a demo or to speak with the team, the AI asks for details one field at a time: name, email, phone, company. It never asks for multiple fields at once. Once collected, details are saved to the leads database and the workflow continues.

**Barge-In Interruption**
Users can interrupt the AI mid-sentence. VAD detects speech start, cancels in-flight TTS frames, and processes the new utterance. Turn IDs prevent stale audio from playing after interruption.

**Escalation to Human**
When a caller wants a human, the AI captures lead context and hands off seamlessly. The Agent Desktop receives: caller's name, email, company, intent, conversation summary, and key interests. The human agent picks up exactly where the AI left off.

## Frontline AI — Companion Agent

The Companion AI assists human agents during escalated calls.

**Context Pre-Load**
On escalation, the Companion AI immediately analyzes the full Voice AI conversation and generates: a checklist of unresolved items, suggested next actions, customer mood assessment, and relevant KB snippets.

**Real-Time Nudges**
As the conversation continues, the Companion updates in real time via WebSocket. It surfaces objection handlers, product talking points, and pricing guidance based on what's being discussed.

**ACW Summary (After-Call Work)**
When the call ends, the Companion generates an automated wrap-up: resolution summary, action items, CRM fields to update, and a coaching note for the supervisor.

## Operations AI — Supervisor Tools

**Automated QA Scoring**
Within seconds of a call ending, the QA Agent scores the transcript on six rubrics: guardrail adherence, resolution rate, containment, caller satisfaction, handle time, and disclosure compliance. Overall score and pass/fail are stored to the database.

**Live Call Monitoring**
The supervisor dashboard shows all active calls in a real-time table (polling every 5 seconds): caller intent, duration, escalation status, and current workflow stage.

**Knowledge Base Management**
Supervisors upload PDF, DOCX, or Markdown documents. The system parses, chunks, embeds, and indexes them into ChromaDB. Documents surface in the next live call's KB retrieval automatically.

**Coaching Pack Generation**
After any agent accumulates 3 or more scored calls, a coaching pack can be generated. It references specific transcript moments, identifies strengths and improvement areas, and generates action items tailored to that agent's performance patterns.

**Analytics Dashboard**
KPI strip: total calls today, average QA score, escalation rate, resolution rate. Trend chart: 7-day QA score history per agent. All backed by PostgreSQL aggregation queries.

## AI Workflow Automation

Wavvy treats contact center workflows as directed graphs. Each intent maps to a workflow: a sequence of tool calls and wait states that the AI executes deterministically. Businesses integrate Wavvy by defining their workflows — the AI follows them without deviation.

Example workflows available out of the box:
- Demo scheduling: capture name + email → ask for preferred time → schedule appointment
- Human escalation: capture name → escalate with full context
- Product Q&A: KB retrieval → LLM renders answer → speak
- Pricing inquiry: serve deterministic tier information

---

<!-- SOURCE: wavvy_use_cases.md -->

# Wavvy Use Cases

## Who Integrates Wavvy?

Wavvy is built for any business running a contact center that handles repetitive inbound inquiries and wants to automate the majority of interactions while keeping human agents available for complex cases.

## Food Delivery & On-Demand Services

Contact centers for food delivery platforms handle thousands of calls daily: order status, address changes, cancellations, and refund requests. Wavvy can:
- Answer "where is my order?" using real-time order data via API
- Capture cancellation requests and route to the right workflow
- Escalate frustrated customers to human agents based on sentiment scoring
- Score every call for QA automatically

Estimated containment rate: 70-80% of calls resolved without human intervention.

## Banking & Financial Services

Banks and credit unions face high call volumes for account inquiries, card disputes, and authentication. Wavvy provides:
- Two-factor authentication flow (configurable, server-authoritative — LLM never decides if auth passed)
- Account lookup and balance inquiry via CRM integration
- Fraud dispute escalation with full context handoff
- Automated compliance scoring (disclosure, guardrail adherence) on every call

Wavvy's guardrail system ensures sensitive operations never execute without proper authorization. All tool calls pass through a multi-stage permission check before execution.

## Telecommunications

Telecom providers handle billing inquiries, plan changes, and technical support. Wavvy can:
- Identify the caller and their current plan via CRM lookup
- Answer plan comparison questions from the KB
- Process plan upgrade/downgrade requests
- Escalate complex technical issues to Level 2 support

## E-Commerce & Retail

Online retailers use Wavvy for post-purchase support: returns, exchanges, shipping updates. Wavvy can:
- Look up order history and provide status
- Initiate return workflows and capture reason codes
- Answer product questions from the KB
- Route high-value customer complaints to senior agents

## Healthcare & Appointment Scheduling

Healthcare providers use Wavvy for appointment booking and general inquiries:
- Schedule appointments by capturing patient name, preferred time, and reason for visit
- Answer FAQ from the KB (hours, locations, insurance accepted)
- Route urgent medical questions immediately to a human
- HIPAA-compliant logging and audit trail

## SaaS & B2B

SaaS companies use Wavvy for sales and onboarding:
- Answer product Q&A from the KB (pricing, features, integrations)
- Capture demo requests and schedule meetings
- Route enterprise inquiries to sales team
- Score demo calls for quality and train the sales team

This is exactly the use case Wavvy demonstrates on its own platform — you are experiencing it right now.

## The Common Pattern

Every use case follows the same pattern:

1. **Caller speaks** — Voice AI handles intent classification and entity extraction
2. **KB answers** — Product documentation surfaces automatically for open-ended Q&A
3. **Workflow executes** — Deterministic tool calls handle transactional requests
4. **Human escalates** — Agent Desktop receives full context on complex cases
5. **Supervisor scores** — QA automation closes the feedback loop on every call

The only thing that changes between deployments is the KB content, the workflow definitions, and the CRM integration. The core platform remains constant.

---

<!-- SOURCE: wavvy_tech_stack.md -->

# Wavvy Technology Stack

## Voice Pipeline (Real-Time)

Wavvy's voice pipeline is built on production-grade open-source components:

**LiveKit Cloud** — WebRTC transport layer. Handles browser audio in/out, room management, and the data channel used for real-time events (transcripts, tool calls, escalation signals). Free tier: 5,000 minutes/month.

**Pipecat (pipecat-ai 1.2.1)** — Voice pipeline orchestration framework. Connects all pipeline stages: STT → processing → LLM → TTS. Handles interruption detection, frame cancellation on barge-in, and pipeline lifecycle.

**Silero VAD** — Voice Activity Detection. Runs locally, detects user speech start/stop, enables barge-in interruption of in-flight TTS audio. No API cost, unlimited usage.

**Deepgram Nova-2** — Speech-to-Text. Streaming transcription with 300ms endpointing (full utterance arrives as one chunk before processing begins). Free tier: 12,000 minutes/month.

**Groq llama-3.3-70b-versatile** — Primary LLM. OpenAI-compatible API endpoint. Used for language polishing on KB-grounded Q&A turns. Temperature 0.3, max 300 tokens per turn. Free tier: 14,400 requests/day.

**Kokoro TTS** — Local text-to-speech via ONNX model. Zero API cost, unlimited usage. 24kHz audio, voice "af_heart". Runs in-process, ~80MB model download on first run.

## Backend Infrastructure

**FastAPI** — Fully async Python web framework. 4-worker uvicorn deployment. Handles REST API, WebSocket connections, and Pipecat agent task launch as background tasks.

**PostgreSQL + asyncpg** — Primary database. Connection pool: pool_size=20, max_overflow=10. Tables: calls, transcripts, leads, demo_appointments, eval_scores, agent_profiles, kb_documents, coaching_packs.

**ChromaDB (PersistentClient)** — Vector database for knowledge base retrieval. Collections: product_kb (Wavvy documentation), calls_collection (transcript history). Dense retrieval + BM25 + entity graph fused via Reciprocal Rank Fusion.

**SQLAlchemy async** — ORM with asyncpg driver. Alembic for migrations.

## AI Models

**OpenAI text-embedding-3-small** — Embedding model for KB chunks and call transcripts. 1536-dim vectors.

**OpenAI gpt-4o-mini** — Post-call QA scoring, coaching pack generation, ACW summaries. Used sparingly (post-call only) to stay within free tier.

**Groq llama-3.3-70b-versatile (fallback: gpt-4o-mini)** — Live call LLM. Groq's free tier is the primary path; falls back to OpenAI if GROQ_API_KEY is absent.

## Frontend

Three separate React 18 + Vite applications:
- Landing page (livekit-client JS for WebRTC)
- Agent desktop (WebSocket to /ws/agent for real-time events)
- Supervisor dashboard (polling + Recharts for analytics)


## Deployment

**Backend:** Railway — 4-worker uvicorn, PostgreSQL addon, ChromaDB on persistent volume.
**Frontend:** Vercel — three separate projects, each with its own deployment URL.
**No Docker for local dev** — docker-compose for PostgreSQL only, all other services run natively.

## Text-to-Speech (TTS) Details

Wavvy uses **Kokoro TTS** as its voice synthesis engine. Key facts:

- **Engine:** Kokoro (local ONNX model, runs in-process)
- **Cost:** Zero — no API calls, no per-character pricing
- **Quality:** 24kHz audio output, voice profile "af_heart"
- **Setup:** ~80MB model download on first run, then unlimited local usage
- **Latency:** TTS starts within milliseconds of LLM first token — no round-trip to external API
- **Streaming:** Phrase-by-phrase output (each sentence queued as a separate TTS frame)

Wavvy does NOT use ElevenLabs, Azure Speech, Google TTS, or Deepgram TTS for live calls. Kokoro provides comparable voice quality at zero marginal cost.

## Speech-to-Text (STT) Details

Wavvy uses **Deepgram Nova-2** for speech recognition:

- Streaming transcription — audio is transcribed in real time
- 300ms endpointing — Deepgram waits 300ms of silence before emitting a final transcript
- This means a full phone number or sentence arrives as one utterance, not fragmented
- Free tier: 12,000 STT minutes/month (enough for ~200 hours of calls)
- Confidence scores available per utterance — used to gate recovery routing

## Architecture Decision: No Redis, No Message Queue

At hackathon scale, in-memory state per FastAPI worker is sufficient. Each call is fully isolated within a single asyncio task. Scaling to production would add Redis for distributed session state and a message queue for cross-worker call events.

---

<!-- SOURCE: wavvy_integration.md -->

# Wavvy Integration Guide

## Self-Hosting Overview

Wavvy is fully self-hostable at zero cost. You bring your own API keys for LiveKit, Deepgram, and Groq (all have free tiers). The full platform — voice AI, Agent Desktop, Supervisor Dashboard, and all backend services — runs on your own infrastructure with no vendor lock-in.

Self-hosting requires: Python 3.11+, PostgreSQL 16, Node.js 20+, and a Linux/Mac server or cloud VM. Typical setup time: under one hour. No Docker required except for local PostgreSQL.

The managed cloud plans ($299/month Starter, $999/month Growth, Enterprise custom) are available if you prefer not to manage infrastructure. Self-hosting and managed plans have identical features — the only difference is who runs the servers.

## Getting Started (Self-Hosted)

### Prerequisites

- Python 3.11+
- PostgreSQL 16 (docker-compose provided)
- Node.js 20+ (for frontend apps)
- API keys: LiveKit Cloud, Deepgram, Groq (all have free tiers)

### Quick Start

```bash
git clone https://github.com/yourusername/wavvy.git
cd wavvy/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker-compose up -d           # PostgreSQL on port 5433
alembic upgrade head           # run migrations
python -m knowledge.seed       # seed KB
uvicorn main:app --port 8000   # start backend
```

## REST API Reference

Key endpoints:

- `POST /api/livekit/start-call` — create LiveKit room + launch Pipecat agent
- `GET /api/leads` — all captured leads
- `POST /api/kb/upload` — upload PDF/DOCX/MD to knowledge base
- `GET /api/calls` — all calls with QA status
- `POST /api/coaching/generate/{agent_id}` — generate coaching pack

Full API docs at `/docs` (Swagger UI).

## Adding Custom Tools

1. Define in `tools/registry.py` (OpenAI function format)
2. Implement in `tools/wavvy_tools.py` (async function → dict)
3. Add to `execute_tool()` dispatcher
4. Register in relevant workflow entry

## CRM Integrations

Wavvy connects to Salesforce, HubSpot, and any REST API via its tool layer. Built-in leads database (PostgreSQL) is available out of the box with no external CRM required.

---

<!-- SOURCE: wavvy_pricing.md -->

# Wavvy Pricing

## Managed Hosting Plans

### Starter — $299/month
- Up to 500 call minutes/month
- Core voice AI, intent routing, KB retrieval
- Basic analytics, 1 supervisor seat, email support

### Growth — $999/month
- Up to 2,500 call minutes/month
- Agent Desktop + Companion AI
- Full supervisor dashboard (QA, coaching, live monitoring)
- Up to 5 supervisor seats, priority Slack support

### Enterprise — Custom pricing
- Unlimited call minutes (SLA-backed)
- Custom workflow definitions and tool integrations
- On-premises or private cloud option
- Dedicated solutions engineer, 99.9% uptime SLA

## Self-Hosted (Free)

MIT license — no usage fees. Bring your own API keys:
- LiveKit Cloud: 5,000 WebRTC min/month free
- Deepgram: 12,000 STT min/month free
- Groq: 14,400 LLM requests/day free
- Kokoro TTS: unlimited (local ONNX)

---

<!-- SOURCE: wavvy_vs_competitors.md -->

# Wavvy vs. Competitors

## Wavvy vs. Retell AI

| | Wavvy | Retell AI |
|---|---|---|
| Open-source | Yes (MIT) | No |
| Agent Desktop | Yes (Companion AI) | No |
| Supervisor Dashboard | Yes (QA, coaching) | Limited |
| Deterministic orchestration | Yes (Workflow Engine) | Prompt-based |
| QA scoring | Yes (automated) | No |

## Wavvy vs. Vapi

Vapi is a developer-focused voice AI API. Wavvy is a complete platform (three apps + backend). Vapi gives building blocks; Wavvy gives a full contact center stack. Wavvy includes KB management, QA automation, and Agent Desktop that Vapi does not have.

## Wavvy vs. Bland AI

Bland AI focuses on outbound calling campaigns. Wavvy is inbound-first with full human escalation support. Wavvy has Agent Desktop, Supervisor Dashboard, and QA automation that Bland does not.

## Wavvy vs. ElevenLabs

ElevenLabs is a TTS API, not a contact center platform. Wavvy uses Kokoro TTS (local ONNX, zero cost). ElevenLabs provides no orchestration, KB retrieval, escalation routing, or operational stack.

## Wavvy vs. Twilio Flex

| | Wavvy | Twilio Flex |
|---|---|---|
| Time to deploy | Hours | Weeks to months |
| Open-source | Yes | No |
| AI-native | Yes | Bolt-on |
| Pricing | From $299/mo | Per agent seat + usage |

## Key Wavvy Differentiators

1. Deterministic orchestration — LLM never decides what to do
2. Three-app operational stack — Landing + Voice AI, Agent Desktop, Supervisor
3. Open-source and self-hostable — no vendor lock-in
4. Automatic QA — every call scored within 5 seconds
5. Companion AI — human agents get full context on escalation
