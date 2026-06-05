# Wavvy Voice Agent — Manual Call Evaluation Guide

Run the backend and open the landing page call modal. Work through each scenario below.
Each scenario is independent — start a fresh call for each one unless noted.

**Setup:** `python3 -m knowledge.seed` (once), then `uvicorn main:app --reload`

---

## How to Read This Guide

Each test entry shows:
- **Say:** exact words to speak (or type in the IssueSelector)
- **Expect:** what you should hear back
- **Check:** what to verify in the UI or logs
- **PASS / FAIL criteria** at the end of each scenario

---

## Scenario 1 — Basic Greeting

**Purpose:** AI responds warmly; does NOT ask you to rephrase; greetings never go to RECOVERY tier.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "Hi" | Warm greeting, offers help or demo |
| 2 | "Hello" | Warm greeting (different phrasing, not identical to step 1) |
| 3 | "Good morning" | Contextually appropriate opener |

**Check:** No "I didn't catch that" or "could you rephrase". No robotic bullet-point response.

**PASS:** AI responds conversationally within 1–2 seconds, no clarification request.

---

## Scenario 2 — Product Q&A (KB retrieval)

**Purpose:** AI answers product questions from knowledge base — not hallucinations.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "What is Wavvy?" | Open-source CCaaS platform, four apps, one backend |
| 2 | "What makes Wavvy different from Retell AI?" | Open-source, full operational stack, deterministic orchestration |
| 3 | "How does Wavvy compare to Vapi?" | Vapi is API-only; Wavvy includes full UI and supervisor tools |
| 4 | "What TTS does Wavvy use?" | Kokoro TTS, local ONNX, zero API cost |
| 5 | "Does Wavvy integrate with Salesforce?" | Yes, via tool layer; describes HubSpot, webhooks too |
| 6 | "Tell me about the supervisor dashboard" | Live call monitoring, QA scoring, coaching packs |

**Check:** KB hit events appear in browser console/network. Answers are specific, not vague.

**PASS:** All 6 answers are factually correct against [knowledge/seed_docs/](../knowledge/seed_docs/). No hallucinated features or prices.

---

## Scenario 3 — Pricing Questions

**Purpose:** AI answers pricing from KB; never says "let me check" unprompted.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "How much does Wavvy cost?" | Three plans: Starter $299, Growth $999, Enterprise custom |
| 2 | "What's in the Starter plan?" | 500 minutes, voice AI, transcription, analytics, 1 supervisor seat |
| 3 | "What about the Growth plan?" | 2500 minutes, agent desktop, QA scoring, coaching packs |
| 4 | "Is there a free option?" | Yes — fully self-hosted under MIT license, bring your own API keys |
| 5 | "I want enterprise pricing" | Offers to connect with the team; does NOT invent a number |

**PASS:** All answers match [wavvy_pricing.md](../knowledge/seed_docs/wavvy_pricing.md). No "let me check availability" unprompted.

---

## Scenario 4 — Demo Booking (Full 5-Turn Flow)

**Purpose:** Slot collection before tool fires; two-question flow (day → time).

| Step | Say | Expect |
|------|-----|--------|
| 1 | "I want to book a demo" | "What's your name?" |
| 2 | "I'm Alex" | "What's your email address?" |
| 3 | "alex@example.com" | "What day works best for you? We're free Monday through Friday." |
| 4 | "Thursday" | "What time on Thursday works for you? We're available nine to five IST." |
| 5 | "3pm" | "Done! Demo confirmed for Thursday 3pm. Confirmation goes to alex@example.com." |

**Check:** `schedule_demo` tool fires only AFTER step 5. No tool call after step 1, 2, 3, or 4 alone.

**PASS:** Confirmation message includes the full slot label and email. Lead appears in `/api/leads`.

---

## Scenario 5 — Demo Booking with Side Question (Workflow Interruptibility)

**Purpose:** User asks a product question mid-booking; workflow resumes correctly.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "I want to book a demo" | "What's your name?" |
| 2 | "Sarah" | "What's your email address?" |
| 3 | "Actually — what does the demo cover?" | AI answers the question about the demo |
| 4 | "sarah@acme.com" | Entity collected; workflow continues — "What day works best?" |
| 5 | "Wednesday" | "What time on Wednesday works for you?" |
| 6 | "2pm" | Demo confirmed |

**PASS:** The question in step 3 is answered without losing the name collected in step 2.

---

## Scenario 6 — Human Escalation Request

**Purpose:** Escalation triggers correctly; silence/demo prompts stop immediately.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "I want to speak to a human" | "Connecting you with our team now. One moment." |
| 2 | (wait 30 seconds in silence) | No "Still here" nudge, no demo prompts — escalation is active |

**Check:**
- Transfer screen appears in call modal
- Agent Desktop (`/agent`) receives `incoming_call` event
- Companion panel shows conversation context from before escalation

**PASS:** Escalation fires within 2s. Agent Desktop receives the handoff bundle. No nudge during the 30s wait.

---

## Scenario 7 — Repair / Correction

**Purpose:** AI acknowledges corrections and redirects; does not re-explain the wrong thing.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "How much does Wavvy cost?" | Pricing overview |
| 2 | "No I meant the tech stack" | Acknowledges correction, answers about the tech stack (LiveKit, Deepgram, OpenAI, Kokoro) |
| 3 | "That's not what I asked — I meant the features" | Acknowledges, answers about features |

**PASS:** AI does not repeat the previous answer or re-explain it. The correction is acknowledged in ≤ 5 words before pivoting.

---

## Scenario 8 — Hinglish Input

**Purpose:** Hinglish phrases normalize correctly; AI responds in English naturally.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "Demo book karna hai" | "What's your name?" (demo booking starts) |
| 2 | "Nahi chahiye demo" | "No problem." or acknowledgement; demo booking cancelled |
| 3 | "Batao mujhe pricing" | Pricing overview from KB |
| 4 | "Haan" (after a yes/no question) | AI treats it as affirmation |

**PASS:** All four utterances produce sensible responses. No "I didn't understand" for any of them.

---

## Scenario 9 — Silence Timer Behaviour

**Purpose:** Nudges fire at correct times; stop after escalation.

| Step | Action | Expect |
|------|--------|--------|
| 1 | Say "Hi" then wait silently | No nudge for first 25 seconds |
| 2 | Wait to 30 seconds | First nudge plays (rotating variant: "I'm here whenever you're ready" or similar) |
| 3 | Respond normally | Timer resets; 25-second window restarts |
| 4 | Trigger escalation, then wait 30 seconds | No nudge after escalation |

**PASS:** First nudge fires between 25–35s. No nudge after escalation. Variants differ across multiple test calls.

---

## Scenario 10 — Barge-In (Interruption)

**Purpose:** User can interrupt mid-TTS; stale audio does not play after interruption.

| Step | Say | Expect |
|------|-----|--------|
| 1 | "Tell me everything about Wavvy's features" | AI starts a longer response |
| 2 | (while AI is speaking) "Wait, actually just tell me the pricing" | AI stops mid-sentence, answers pricing |

**Check:** No echo of the previous response. The pricing answer starts from the beginning, not mid-sentence.

**PASS:** Interruption latency < 500ms. Stale TTS fragments do not play. New response is coherent.

---

## Scenario 11 — Confirmation Flow (Pending Slot)

**Purpose:** Pending slot confirmation responds correctly to yes/no.

| Step | Say | Expect |
|------|-----|--------|
| 1–4 | Complete demo booking through time collection | "Just to confirm — shall I book you in for Thursday 3pm?" |
| 5a | "Yes" | "Done! Demo confirmed for Thursday 3pm." |

Repeat with a fresh call:

| Step | Say | Expect |
|------|-----|--------|
| 1–4 | Same | Confirmation prompt |
| 5b | "No" | "No problem, your demo is still on." or similar cancellation |

**PASS:** "Yes" → booking confirmed. "No" → booking aborted. No accidental booking on "no".

---

## Scenario 12 — Edge Cases

| Test | Say | Expected behaviour |
|------|-----|--------------------|
| Unknown topic | "What's the weather like today?" | Politely declines, offers to connect with team |
| Off-topic question | "Tell me a joke" | Brief deflection, redirects to Wavvy |
| Repeated question | Ask the same pricing question twice | Second answer is not identical word-for-word |
| Name with "no" | "My name is Noel" | Name extracted as "Noel", not treated as denial |
| Addressing AI by wrong name | "Hi Alexa, what does Wavvy do?" | Answers naturally without correcting the name |

---

## Quick Smoke Test (5 minutes)

Run this sequence on a fresh call to confirm everything works end-to-end before a demo:

1. "Hi" → expect warm greeting
2. "What makes Wavvy different from Retell?" → expect comparison from KB
3. "How much does it cost?" → expect $299/$999/Enterprise answer
4. "I want to book a demo" → starts flow
5. Give name + email when asked
6. "Thursday at 3pm" → AI might ask to confirm or split into two questions
7. Complete booking → confirmation message
8. "I want to speak to a human" → transfer screen

**Total time:** ~3 minutes. All 8 steps passing = system is production-ready for demo.

---

## Automated Suite

To run the full pipeline unit tests:

```bash
cd backend
python3 -m tests.eval_pipeline
```

Expected: **130/130 passed (100%)**

Tests cover: KB retrieval (15 queries), transcript normalization (17 cases), directive detection (20 cases), tier routing (17 cases), entity extraction (19 cases), response policy (15 cases), context builder (12 cases), demo booking simulation (11 turns).
