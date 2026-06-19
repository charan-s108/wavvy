import json
import logging

logger = logging.getLogger(__name__)

_client = None

_DEFAULT_COACHING_PROMPT = """You are a Voice AI performance analyst.
You will receive a list of completed call evaluations for a Voice AI agent.
Generate an optimization coaching pack that helps the product team improve the Voice AI's performance.

Be specific — identify recurring patterns across calls:
- Which rubric criteria consistently score low?
- What violations appear most often?
- Where does the AI fail to resolve before escalating?
- What types of calls show the worst satisfaction scores?

Output actionable recommendations for the team: prompt tuning, workflow node adjustments, KB content gaps.
Never be generic. Every recommendation must be grounded in the evaluation data provided.

Return ONLY valid JSON in this exact schema:
{
  "overall_trend": "improving" | "declining" | "stable",
  "strengths": ["what the Voice AI consistently does well — pattern-based, specific"],
  "improvements": ["specific failure pattern with data backing — e.g. 'resolution_rate averages 52% — AI fails to confirm outcomes before ending calls'"],
  "action_items": [
    {"priority": "high" | "medium" | "low", "action": "specific optimization step for the team", "metric": "what to measure to confirm improvement"},
    {"priority": "high" | "medium" | "low", "action": "specific optimization step for the team", "metric": "what to measure to confirm improvement"}
  ],
  "score_summary": {
    "avg_overall": 75,
    "avg_guardrail": 80,
    "avg_resolution": 70,
    "avg_containment": 65,
    "avg_satisfaction": 0.72,
    "pass_rate": 0.67,
    "calls_analyzed": 3
  },
  "coaching_note": "One paragraph analysis for the team: what patterns emerged, what to prioritize in the next iteration of the Voice AI."
}

Temperature 0.4. Ground every finding in the evaluation data provided."""


def _get_coaching_prompt() -> str:
    try:
        from config_loader import get_config
        p = get_config().coaching_prompt
        if p:
            return p
    except Exception:
        pass
    return _DEFAULT_COACHING_PROMPT


def init_coaching_agent(openai_client):
    global _client
    _client = openai_client


async def generate_coaching_pack(agent_name: str, eval_records: list[dict]) -> dict:
    """
    Generate a coaching pack from >= 3 eval records for an agent.
    Returns the parsed coaching pack dict.
    """
    if not _client:
        logger.warning("Coaching agent not initialized — returning default")
        return _default_pack(agent_name, eval_records)

    eval_summary = json.dumps(eval_records, indent=2, default=str)
    user_content = (
        f"Agent: {agent_name}\n"
        f"Number of calls evaluated: {len(eval_records)}\n\n"
        f"Evaluation records:\n{eval_summary}"
    )

    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=900,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _get_coaching_prompt()},
                {"role": "user", "content": user_content},
            ],
        )
        pack = json.loads(response.choices[0].message.content)
        return _normalize_pack(pack, eval_records)
    except Exception as e:
        logger.error(f"Coaching agent error: {e}")
        return _default_pack(agent_name, eval_records)


def _normalize_pack(pack: dict, eval_records: list[dict]) -> dict:
    n = len(eval_records)
    scores = [r.get("overall_score", 0) for r in eval_records]
    pass_count = sum(1 for r in eval_records if r.get("pass_fail") == "PASS")

    # Ensure score_summary is populated with real averages
    def avg(key):
        vals = [r.get(key, 0) or 0 for r in eval_records]
        return round(sum(vals) / n, 1) if n else 0

    pack["score_summary"] = {
        "avg_overall": round(sum(scores) / n, 1) if n else 0,
        "avg_guardrail": avg("guardrail_adherence"),
        "avg_resolution": avg("resolution_rate"),
        "avg_containment": avg("containment"),
        "avg_satisfaction": round(avg("caller_satisfaction"), 2),
        "pass_rate": round(pass_count / n, 2) if n else 0,
        "calls_analyzed": n,
    }

    # Ensure required list fields exist
    pack.setdefault("strengths", [])
    pack.setdefault("improvements", [])
    pack.setdefault("action_items", [])
    pack.setdefault("overall_trend", "stable")
    pack.setdefault("coaching_note", "Keep working on consistency across all rubric criteria.")

    return pack


def _default_pack(agent_name: str, eval_records: list[dict]) -> dict:
    return _normalize_pack({
        "overall_trend": "stable",
        "strengths": ["Maintained professional tone", "Followed escalation protocol"],
        "improvements": ["Improve resolution rate", "Reduce average handle time"],
        "action_items": [
            {"priority": "high", "action": "Practice refund resolution scripts", "metric": "resolution_rate >= 80"},
            {"priority": "medium", "action": "Review KB articles before shifts", "metric": "kb_hit rate"},
        ],
        "coaching_note": f"{agent_name} shows consistent effort. Focus on boosting resolution rate.",
    }, eval_records)
