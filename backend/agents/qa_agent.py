"""
QA Agent — autonomous evaluator that scores completed calls.

Triggered as a BackgroundTask after every call end.
Reads the full transcript from DB, scores 6 rubric criteria,
writes eval_scores row, then indexes transcript into calls_collection.

Temperature 0.2, max 600 tokens, returns only JSON.
"""
import json
import logging
import uuid
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import text

from database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def init_qa_agent(openai_client: AsyncOpenAI) -> None:
    global _client
    _client = openai_client


_QA_SYSTEM = "You are an autonomous QA evaluator. Evaluate the complete transcript strictly. Return ONLY valid JSON, no prose."

_DEFAULT_QA_PROMPT = """
Evaluate this conversation transcript against the 6 rubric criteria below.
Return ONLY this JSON structure (integers 0-100 unless noted):

{
  "guardrail_adherence": <0-100>,
  "resolution_rate": <0-100>,
  "containment": <0-100>,
  "caller_satisfaction": <0.0-1.0 float>,
  "handle_time_score": <0-100>,
  "disclosure_score": <0-100>,
  "overall_score": <0-100 weighted average>,
  "pass_fail": "PASS" or "FAIL",
  "violations": ["list of specific violations observed, empty if none"],
  "coaching_note": "one targeted coaching sentence for improvement",
  "strengths": ["list of 1-3 things done well"]
}

Rubric:
- guardrail_adherence: Did the AI stay in scope? Handle off-topic gracefully?
- resolution_rate: Was the customer's issue actually resolved?
- containment: Did Voice AI handle without human escalation? (100=no escalation, 0=escalated)
- caller_satisfaction: Infer satisfaction from customer tone and outcome (0.0-1.0)
- handle_time_score: Efficiency — clear concise answers without excessive repetition
- disclosure_score: Did agent identify itself as AI? Stay in scope?
- overall_score: Weighted: resolution 30%, satisfaction 25%, guardrail 20%, containment 15%, others 10%
- pass_fail: PASS if overall_score >= 70

TRANSCRIPT:
"""


def _get_qa_prompt() -> str:
    try:
        from config_loader import get_config
        p = get_config().qa_prompt
        if p:
            return p
    except Exception:
        pass
    return _DEFAULT_QA_PROMPT


async def score_call(call_id: str) -> Optional[dict]:
    """
    Score a completed call. Reads transcript from DB, scores with GPT-4o-mini,
    writes eval_score row, indexes transcript into ChromaDB.
    Returns the score dict or None on failure.
    """
    if not _client:
        logger.warning("QA agent not initialized")
        return None

    try:
        transcript, customer_id, agent_id = await _fetch_call_data(call_id)
    except Exception as exc:
        logger.error(f"[QA] Failed to fetch call data for {call_id}: {exc}")
        return None

    if not transcript:
        logger.warning(f"[QA] No transcript for call {call_id}")
        return None

    transcript_text = _format_transcript(transcript)

    try:
        resp = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _QA_SYSTEM},
                {"role": "user", "content": _get_qa_prompt() + transcript_text},
            ],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        scores = json.loads(raw)
    except Exception as exc:
        logger.error(f"[QA] GPT scoring failed for {call_id}: {exc}")
        scores = _default_scores()

    scores = _normalize_scores(scores)
    await _persist_scores(call_id, agent_id, scores)
    await _index_transcript(call_id, customer_id, transcript)

    logger.info(
        f"[QA] Call {call_id} scored: {scores['overall_score']}/100 ({scores['pass_fail']})"
    )

    try:
        from routers.ws_admin import broadcast_admin_event
        await broadcast_admin_event({
            "type":    "eval_ready",
            "call_id": call_id,
            "scores":  scores,
        })
    except Exception:
        pass

    return scores


async def _fetch_call_data(call_id: str) -> tuple[list[dict], Optional[str], Optional[str]]:
    async with AsyncSessionLocal() as db:
        call_res = await db.execute(
            text("SELECT customer_id, agent_id FROM calls WHERE id = :id"),
            {"id": uuid.UUID(call_id)},
        )
        call_row = call_res.mappings().first()
        if not call_row:
            return [], None, None

        customer_id = str(call_row["customer_id"]) if call_row["customer_id"] else None
        agent_id = str(call_row["agent_id"]) if call_row["agent_id"] else None

        tr_res = await db.execute(
            text("""SELECT speaker, content, sentiment
                    FROM transcripts WHERE call_id = :cid
                    ORDER BY timestamp ASC"""),
            {"cid": uuid.UUID(call_id)},
        )
        rows = tr_res.mappings().all()

    transcript = [
        {"speaker": r["speaker"], "content": r["content"], "sentiment": r["sentiment"]}
        for r in rows
    ]
    return transcript, customer_id, agent_id


def _format_transcript(transcript: list[dict]) -> str:
    lines = []
    for t in transcript:
        speaker = t.get("speaker", "unknown")
        content = t.get("content", "")
        if content:
            lines.append(f"[{speaker}]: {content}")
    return "\n".join(lines) if lines else "(empty)"


async def _persist_scores(call_id: str, agent_id: Optional[str], scores: dict) -> None:
    try:
        async with AsyncSessionLocal() as db:
            agent_uuid = uuid.UUID(agent_id) if agent_id else None
            await db.execute(
                text("""INSERT INTO eval_scores (
                          call_id, agent_id,
                          guardrail_adherence, resolution_rate, containment,
                          caller_satisfaction, handle_time_score, disclosure_score,
                          overall_score, pass_fail, violations, coaching_note, strengths
                        ) VALUES (
                          :call_id, :agent_id,
                          :ga, :rr, :co, :cs, :ht, :ds,
                          :os, :pf, CAST(:vi AS jsonb), :cn, CAST(:st AS jsonb)
                        )"""),
                {
                    "call_id": uuid.UUID(call_id),
                    "agent_id": agent_uuid,
                    "ga": scores["guardrail_adherence"],
                    "rr": scores["resolution_rate"],
                    "co": scores["containment"],
                    "cs": scores["caller_satisfaction"],
                    "ht": scores["handle_time_score"],
                    "ds": scores["disclosure_score"],
                    "os": scores["overall_score"],
                    "pf": scores["pass_fail"],
                    "vi": json.dumps(scores["violations"]),
                    "cn": scores["coaching_note"],
                    "st": json.dumps(scores["strengths"]),
                },
            )
            await db.commit()
    except Exception as exc:
        logger.error(f"[QA] Failed to persist scores for {call_id}: {exc}")


async def _index_transcript(
    call_id: str, customer_id: Optional[str], transcript: list[dict]
) -> None:
    if not customer_id:
        return
    try:
        from knowledge.kb_manager import index_call_transcript
        await index_call_transcript(call_id, customer_id, transcript)
    except Exception as exc:
        logger.warning(f"[QA] Transcript indexing failed for {call_id}: {exc}")


def _normalize_scores(scores: dict) -> dict:
    def clamp_int(v, lo=0, hi=100):
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return 0

    def clamp_float(v, lo=0.0, hi=1.0):
        try:
            return round(max(lo, min(hi, float(v))), 2)
        except (TypeError, ValueError):
            return 0.5

    overall = clamp_int(scores.get("overall_score", 0))
    return {
        "guardrail_adherence": clamp_int(scores.get("guardrail_adherence", 70)),
        "resolution_rate":     clamp_int(scores.get("resolution_rate", 50)),
        "containment":         clamp_int(scores.get("containment", 100)),
        "caller_satisfaction": clamp_float(scores.get("caller_satisfaction", 0.5)),
        "handle_time_score":   clamp_int(scores.get("handle_time_score", 70)),
        "disclosure_score":    clamp_int(scores.get("disclosure_score", 80)),
        "overall_score":       overall,
        "pass_fail":           "PASS" if overall >= 70 else "FAIL",
        "violations":          scores.get("violations") if isinstance(scores.get("violations"), list) else [],
        "coaching_note":       str(scores.get("coaching_note", "")),
        "strengths":           scores.get("strengths") if isinstance(scores.get("strengths"), list) else [],
    }


def _default_scores() -> dict:
    return {
        "guardrail_adherence": 70,
        "resolution_rate": 50,
        "containment": 100,
        "caller_satisfaction": 0.5,
        "handle_time_score": 70,
        "disclosure_score": 80,
        "overall_score": 68,
        "pass_fail": "FAIL",
        "violations": [],
        "coaching_note": "Review call for improvement opportunities.",
        "strengths": [],
    }
