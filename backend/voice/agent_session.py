"""
AgentSession setup for Wavvy — full voice pipeline per call.

Pipeline:
  Deepgram nova-2 STT
  → Silero VAD + multilingual turn detector
  → OpenAI gpt-4o-mini LLM (OpenAI-compatible)
  → Deepgram Aura-2 TTS aura-2-thalia-en (Cartesia quota exhausted — revert when credits reset)

Workers run independently from FastAPI. Each call is isolated.
Cleanup (DB persist, QA score trigger) runs via HTTP callback to FastAPI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

import livekit.rtc as rtc
from livekit.agents import AgentSession, JobContext, JobProcess, function_tool
from livekit.agents.stt import SpeechEventType
from voice.wavvy_agent import WavvyAgent
from livekit.agents.voice import ConversationItemAddedEvent, UserInputTranscribedEvent
from livekit.plugins import cartesia, deepgram, silero
from livekit.plugins import openai as lk_openai
# MultilingualModel removed — Deepgram endpointing_ms=400 is the primary EOU signal.
# The ML inference server was timing out and causing AssertionError cascades that
# triggered preemptive generation on partial utterances.

from config import settings
from config_loader import get_config, load_active_config
from session.call_session import TurnState, create_session, get_session, remove_session
from voice.agent_tools import make_agent_tools, _notify_fastapi
from voice.barge_in_manager import SilenceTimer

logger = logging.getLogger(__name__)


async def _strip_function_tags(text):
    """Filter llama <function=name>args</function> tags from the TTS text stream.

    Llama-3.3 embeds tool calls as inline text tokens rather than structured
    tool-call responses. This transform drops everything between <function=...> and
    the closing tag before the audio is synthesised.
    """
    from collections.abc import AsyncIterable
    buffer = ""
    in_fn = False
    OPEN = "<function="
    TAIL = len(OPEN)

    async for chunk in text:
        buffer += chunk

        if in_fn:
            # Scan for either </function> (canonical) or bare <function> (llama quirk)
            for close in ("</function>", "<function>"):
                idx = buffer.find(close)
                if idx != -1:
                    buffer = buffer[idx + len(close):]
                    in_fn = False
                    break
            continue

        idx = buffer.find(OPEN)
        if idx != -1:
            if idx > 0:
                yield buffer[:idx]
            buffer = buffer[idx:]
            end = buffer.find(">")
            if end != -1:
                buffer = buffer[end + 1:]
                in_fn = True
            continue

        # No tag detected — flush everything except a tail that might be a partial tag
        if len(buffer) > TAIL:
            yield buffer[:-TAIL]
            buffer = buffer[-TAIL:]

    if buffer and not in_fn:
        yield buffer


def _make_tts():
    # Deepgram Aura-2: ~200ms TTFB, reliable.
    # Cartesia quota exhausted (402) — switch back once credits reset.
    return deepgram.TTS(
        model="aura-2-thalia-en",
        api_key=settings.deepgram_api_key,
    )


def prewarm(proc: JobProcess) -> None:
    """Pre-load Silero VAD and initialize shared clients once per worker subprocess."""
    import asyncio as _asyncio

    # Reinitialize DB engine in this subprocess's event loop.
    # The module-level engine in database.py was created in the parent loop;
    # asyncpg connections are loop-bound and will fail without this.
    from database import reinit_engine
    reinit_engine()

    _asyncio.get_event_loop().run_until_complete(load_active_config())

    proc.userdata["vad"] = silero.VAD.load()

    proc.userdata["tts"] = _make_tts()

    # Initialize OpenAI client for QA agent (used in post-call scoring)
    try:
        from openai import AsyncOpenAI
        from agents import qa_agent as qa_module
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        proc.userdata["openai_client"] = client
        qa_module.init_qa_agent(client)
        logger.info("QA agent initialized in worker")
    except Exception as exc:
        logger.warning("QA agent init skipped: %s", exc)



async def entrypoint(ctx: JobContext) -> None:
    """
    Entry point for each dispatched job (one room = one call).

    Lifecycle:
      connect → start AgentSession → wait for customer → call_ready →
      wait for customer disconnect → DB persist → QA trigger
    """
    room_name = ctx.room.name

    # Escalation rooms are no longer used — text-to-TTS model replaced voice bridging.
    if room_name.startswith("esc-"):
        logger.info("[%s] ESC room job ignored (text-to-TTS escalation model active)", room_name)
        ctx.shutdown()
        return

    call_id = room_name.removeprefix("call-")

    logger.info("[%s] Agent job started — room: %s", call_id, room_name)

    await ctx.connect()

    # Session is pre-created by POST /api/livekit/start-call; create if missing
    session = get_session(call_id)
    if not session:
        session = create_session(call_id)
        logger.warning("[%s] No pre-existing CallSession — created one", call_id)

    # ── Publish events to browser via LiveKit data channel ──────────────
    async def publish_event(payload: dict) -> None:
        try:
            data = json.dumps(payload).encode()
            await ctx.room.local_participant.publish_data(data, reliable=True)
        except Exception as exc:
            logger.debug("[%s] publish_event failed: %s", call_id, exc)

    # ── Agent tools (closures bound to this call) ────────────────────────
    tools = make_agent_tools(call_id, session, publish_event)

    # ── Agent instructions (loaded from active tenant config) ───────────
    cfg = get_config()
    instructions = cfg.voice_system_prompt
    if session.initial_topic:
        instructions += (
            f"\n\nOPENING TOPIC: The visitor selected '{session.initial_topic}'. "
            f"Begin by greeting them and immediately addressing this topic."
        )

    agent = WavvyAgent(
        session=session,
        instructions=instructions,
        tools=tools,
    )

    # ── AgentSession: STT / LLM / TTS / VAD ─────────────────────────────
    tts_instance = ctx.proc.userdata.get("tts") or _make_tts()
    # max_completion_tokens=250: caps each agent reply at ~180 words — keeps voice responses
    # short, reducing OpenAI TTS audio generation time significantly.
    # temperature=0.3: low randomness for consistent support responses.
    _llm_kwargs = dict(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        max_completion_tokens=250,
        temperature=0.3,
    )
    agent_session = session.agent_session = AgentSession(
        stt=deepgram.STT(
            model="nova-2",
            language="en-US",
            api_key=settings.deepgram_api_key,
            endpointing_ms=400,
            smart_format=True,
        ),
        llm=lk_openai.LLM(**_llm_kwargs),
        tts=tts_instance,
        vad=ctx.proc.userdata.get("vad") or silero.VAD.load(),
        tts_text_transforms=[_strip_function_tags],
    )

    # ── Call-end signal (set by disconnect handler or silence 90s timeout) ─
    call_done = asyncio.Event()
    # ── Human-takeover signal (set when human-agent identity joins room) ──
    human_took_over = asyncio.Event()

    # ── Silence timer — 25s nudge, 55s follow-up, 90s goodbye + close ───
    async def _on_silence_25() -> None:
        await agent_session.say("Are you still there? I'm here to help whenever you're ready.")

    async def _on_silence_55() -> None:
        await agent_session.say(
            "I'm still here if you'd like to continue. Just say something to resume."
        )

    async def _on_silence_90() -> None:
        await agent_session.say(
            "It seems you've stepped away. I'll close the call now — feel free to call back anytime."
        )
        call_done.set()

    silence_timer = SilenceTimer(
        call_id=call_id,
        callbacks={25: _on_silence_25, 55: _on_silence_55, 90: _on_silence_90},
        session=session,   # pauses elapsed time during ASSISTANT_SPEAKING / PROCESSING
    )

    # ── Event: user transcript finalized ────────────────────────────────
    @agent_session.on("user_input_transcribed")
    def on_user_transcribed(ev: UserInputTranscribedEvent) -> None:
        if ev.is_final and ev.transcript.strip():
            session.turn_state = TurnState.USER_SPEAKING
            silence_timer.reset()
            asyncio.create_task(publish_event({
                "type": "transcript",
                "speaker": "customer",
                "text": ev.transcript,
                "is_final": True,
            }))
            # After escalation the agent is in the esc room, not this room.
            # Forward customer speech to the agent console via FastAPI WebSocket.
            if session.escalated:
                asyncio.create_task(_notify_fastapi(call_id, "transcript", {
                    "speaker": "customer",
                    "text": ev.transcript,
                }))
                # Kill any preemptive generation immediately — the turn detector
                # fires before on_item_added so without this interrupt(), the LLM
                # starts speculatively and TTS begins streaming before the assistant
                # guard can fire. Escalated = Fin is deaf and mute.
                agent_session.interrupt()

    # ── Event: conversation item added (user or agent turn) ──────────────
    @agent_session.on("conversation_item_added")
    def on_item_added(ev: ConversationItemAddedEvent) -> None:
        from livekit.agents.llm import ChatMessage
        if not isinstance(ev.item, ChatMessage):
            return
        role = str(ev.item.role)
        text = ev.item.text_content or ""
        if not text.strip():
            return

        if role == "assistant":
            # Human agent has taken over
            if session.human_joined:
                # human_agent_say_active: set by agent_say_text data handler so typed
                # TTS is not interrupted before it plays.
                if not session.human_agent_say_active:
                    agent_session.interrupt()
                return  # skip normal assistant handling regardless
            # Escalation announced — AI waits silently for human to join
            if session.escalated:
                agent_session.interrupt()
                return
            session.turn_state = TurnState.ASSISTANT_SPEAKING
            # Restart silence timer — fires if user goes quiet after agent speaks
            silence_timer.start()
            # (e.g. "<function=schedule_demo>...</function>") before displaying
            clean_text = re.sub(r'<function[^>]*>.*?(?:</function>|<function>)', '', text, flags=re.DOTALL).strip()
            asyncio.create_task(publish_event({
                "type": "agent_done",
                "full_text": clean_text or text,
            }))
            session.conversation_history.append({"role": "assistant", "content": text})
            if len(session.conversation_history) > 20:
                session.conversation_history = (
                    session.conversation_history[:2]
                    + session.conversation_history[-18:]
                )
        elif role == "user":
            # Belt-and-suspenders: block pipeline from proceeding to LLM when escalated.
            # on_user_transcribed already called interrupt() but on_item_added fires in
            # the same async cycle — calling it again ensures preemptive generation is
            # fully cancelled before any new LLM call can be enqueued.
            if session.escalated or session.human_joined:
                agent_session.interrupt()
                return
            session.turn_state = TurnState.USER_SPEAKING
            session.conversation_history.append({"role": "user", "content": text})
            session.turn_count += 1

    # ── Event: per-turn latency metrics → push to supervisor ────────────
    @agent_session.on("metrics_collected")
    def on_metrics(ev) -> None:
        m = ev.metrics
        metric_data: dict = {}
        if m.type == "llm_metrics":
            metric_data = {
                "llm_ttft_ms": round(m.ttft * 1000, 1),
                "llm_tokens": m.total_tokens,
            }
        elif m.type == "tts_metrics":
            metric_data = {
                "tts_ttfb_ms": round(m.ttfb * 1000, 1),
                "tts_chars": m.characters_count,
            }
        elif m.type == "eou_metrics":
            metric_data = {
                "eou_delay_ms": round(m.end_of_utterance_delay * 1000, 1),
                "transcription_delay_ms": round(m.transcription_delay * 1000, 1),
            }
        if metric_data:
            asyncio.create_task(
                _notify_fastapi(call_id, "turn_metrics", metric_data)
            )

    # ── Handle keypad / quick-option input from browser ──────────────────
    @ctx.room.on("data_received")
    def on_data(data_packet) -> None:
        # Human agent has taken over — ignore browser keypad/text input
        if session.human_joined:
            return
        try:
            payload = json.loads(
                data_packet.data.decode() if isinstance(data_packet.data, bytes)
                else data_packet.data
            )
            # FastAPI sends this when the human agent clicks "ANSWER CALL"
            # (agent-join endpoint sends a data message to this room)
            if payload.get("type") == "human_agent_accepted":
                session.human_joined = True
                silence_timer.reset()
                asyncio.create_task(publish_event({
                    "type": "human_agent_joined",
                    "call_id": call_id,
                }))
                human_took_over.set()
                return
            if payload.get("type") == "agent_say_text":
                # Human agent typed a message → play it as TTS to the customer.
                text = payload.get("text", "").strip()
                if text and session.human_joined:
                    session.human_agent_say_active = True
                    agent_session.say(text, allow_interruptions=True)
                    # Reset flag after a short delay so future interrupts work normally.
                    asyncio.get_event_loop().call_later(
                        0.3, lambda: setattr(session, "human_agent_say_active", False)
                    )
                return

            if payload.get("type") == "keypad_input" and payload.get("is_final"):
                text = payload.get("text", "").strip()
                if text:
                    agent_session.generate_reply(user_input=text)
        except Exception:
            pass

    # ── Human-agent takeover — silence AI when human joins ───────────────
    @ctx.room.on("participant_connected")
    def on_participant_connected(p) -> None:
        if p.identity == "human-agent":
            session.human_joined = True
            silence_timer.reset()
            asyncio.create_task(publish_event({
                "type": "human_agent_joined",
                "call_id": call_id,
            }))
            human_took_over.set()

    # ── Disconnect tracking ───────────────────────────────────────────────
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(p) -> None:
        # End the call when the customer leaves (not when human agent joins/leaves)
        if p.identity == "customer":
            silence_timer.reset()
            call_done.set()

    # ── Start the agent session (non-blocking) ────────────────────────────
    await agent_session.start(agent, room=ctx.room)

    # ── Wait for customer to join, then signal browser ────────────────────
    try:
        customer = await asyncio.wait_for(
            ctx.wait_for_participant(identity="customer"),
            timeout=120.0,  # 2 min timeout — abandon if nobody joins
        )
        logger.info("[%s] Customer joined: %s", call_id, customer.identity)
    except asyncio.TimeoutError:
        logger.warning("[%s] No customer joined within 120s — aborting", call_id)
        silence_timer.reset()
        await agent_session.aclose()
        remove_session(call_id)
        return

    # Notify browser: agent is ready, browser transitions CONNECTING → CALLING
    asyncio.create_task(publish_event({"type": "call_ready", "call_id": call_id}))

    # ── Greeting via say() — skips LLM entirely, goes straight to TTS ────
    # deterministic so we use say() which goes straight to Cartesia (~200ms).
    try:
        _cfg = get_config()
        _agent_name = _cfg.agent_name or "Fin"
    except Exception:
        _agent_name = "Fin"

    if session.initial_topic:
        greeting = (
            f"Hey there! This is {_agent_name}. "
            f"I see you're looking into {session.initial_topic} — happy to help with that. "
            f"Can I get your name first?"
        )
    else:
        greeting = (
            f"Hey! Thanks for calling. This is {_agent_name}, your support assistant. "
            f"What can I help you with today?"
        )
    agent_session.say(greeting)

    # ── Wait for customer disconnect OR human takeover ───────────────────
    t_call  = asyncio.create_task(call_done.wait())
    t_human = asyncio.create_task(human_took_over.wait())
    _done, _pending = await asyncio.wait(
        [t_call, t_human], return_when=asyncio.FIRST_COMPLETED
    )
    for t in _pending:
        t.cancel()

    if human_took_over.is_set() and not call_done.is_set():
        # Human agent took over — stop current TTS but keep Deepgram STT alive so
        # customer speech keeps flowing as transcript events to the agent console.
        # on_item_added guards against any further AI speech.
        logger.info("[%s] Human agent joined — silencing AI, keeping STT", call_id)
        try:
            agent_session.interrupt()
        except Exception:
            pass
        await call_done.wait()
        # Customer disconnected — now safe to close the session
        try:
            await agent_session.aclose()
        except Exception:
            pass

    logger.info("[%s] Customer disconnected — running cleanup", call_id)

    # ── End-of-call cleanup ───────────────────────────────────────────────
    try:
        is_esc_room = room_name.startswith("esc-")
        if not is_esc_room:
            from routers.livekit_router import _persist_call_end
            await _persist_call_end(call_id, session.conversation_history)
        remove_session(call_id)

        # Notify FastAPI to broadcast call_ended + trigger QA scoring (main room only)
        if not is_esc_room:
            await _notify_fastapi(call_id, "call_ended", {})
            asyncio.create_task(publish_event({"type": "call_ended", "call_id": call_id}))

    except Exception as exc:
        logger.error("[%s] Cleanup failed: %s", call_id, exc, exc_info=True)
