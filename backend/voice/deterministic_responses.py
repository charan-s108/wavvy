"""
FAST_RESPONSES: Pre-written voice templates that bypass LLM completely.
All keys sent directly to Response Policy → TTS.

Single call mode: WAVVY_DEMO (Wavvy as its own demo client).
FAST_RESPONSES precedence: always wins over LLM when a key is found.
Target: >80% of tool-bound turns never reach the LLM.
"""


WAVVY_DEMO = "wavvy_demo"

FAST_RESPONSES: dict[str, dict[str, str]] = {
    WAVVY_DEMO: {
        # ── Greeting ──────────────────────────────────────────────────────────
        "greeting":              "Hi! I'm Wavvy's AI assistant — ask me anything or book a demo.",

        # ── Lead capture ──────────────────────────────────────────────────────
        "ask_name":              "What's your name?",
        "ask_email":             "What's your email address?",
        "ask_phone":             "And your phone number?",
        "ask_company":           "Which company are you with?",
        "lead_captured":         "Got it, {name}.",
        "email_updated":         "Updated. ",

        # ── Demo scheduling ───────────────────────────────────────────────────
        # Wavvy is available Mon–Fri, 9 AM – 5 PM IST.
        # Two-step slot collection: ask day first, then time on that day.
        "ask_demo_day":                    "What day works best for you? We're free Monday through Friday.",
        "ask_demo_time":                   "And what time works for you? We're available nine to five IST.",
        "demo_scheduled":                  "Done! Demo confirmed for {slot_label}. Confirmation goes to {email}.",
        "demo_slot_suggest_out_of_hours":  "That's outside our hours. How about {slot_label}? Does that work for you?",
        "demo_slot_suggest_conflict":      "That slot is taken. How about {slot_label}? Does that work for you?",
        "demo_slot_repeat":                "Just to confirm — shall I book you in for {slot_label}?",
        "demo_confirm":                    "I'll book {name} for {slot_label}. Shall I go ahead?",

        # ── Pricing ───────────────────────────────────────────────────────────
        "pricing_overview":      "Three plans: Starter at $299, Growth at $999, Enterprise custom. Which interests you?",
        "pricing_starter":       "Starter is $299 per month — 500 minutes, voice AI, transcription, analytics.",
        "pricing_growth":        "Growth is $999 per month — 2,500 minutes, agent desktop, QA, priority support.",
        "pricing_enterprise":    "Enterprise is custom pricing. Want me to connect you with our team?",
        "pricing_opensource":    "Wavvy is open-source. Self-host free, or managed plans start at $299.",

        # ── Escalation ────────────────────────────────────────────────────────
        "escalating":            "Connecting you with our team now. One moment.",
        "already_escalated":     "Already connecting you. One moment.",
        "escalate_cooldown":     "Transfer in progress. Please hold.",

        # ── Clarification (low parse confidence) ─────────────────────────────
        "clarify_time_on_day":   "What time on {day} works best for you?",
        "clarify_day_of_week":   "Which day works? We're free Monday through Friday.",
        "clarify_vague_time":    "When works best? We're free Monday to Friday, nine to five.",

        # ── Cancellation ──────────────────────────────────────────────────────
        "cancel_confirm_prompt": "I'll cancel your demo for {slot_label}. Shall I go ahead?",
        "demo_cancelled":        "Done — your demo has been cancelled.",
        "cancel_aborted":        "No problem, your demo is still on.",
        "no_appointment_found":  "I don't see an upcoming demo scheduled for you.",

        # ── Rescheduling ──────────────────────────────────────────────────────
        "reschedule_ask_time":   "Sure! When would you like to rebook? We're free Monday to Friday, nine to five.",
        "demo_rescheduled":      "Done! Your demo has been moved to {slot_label}.",

        # ── Edge cases ────────────────────────────────────────────────────────
        "slot_offer_expired":    "That offer expired. When would you like to schedule?",
        "slot_just_taken":       "That slot was just taken. Let me find you another.",
        "no_slots_available":    "No slots free right now. Let me connect you with the team.",

        # ── Digression nudges (workflow paused to answer a question) ─────────
        "nudge_name":            "By the way — what's your name so I can get your demo set up?",
        "nudge_email":           "One thing — what's your email so I can confirm your demo?",
        "nudge_day":             "And what day works best for your demo?",
        "nudge_time":            "What time on that day works for you?",

        # ── Recovery ─────────────────────────────────────────────────────────
        "hearing_error":         "Sorry, could you say that again?",
        "tool_error":            "Hit a brief issue. One moment.",
        "escalation_unavailable": "Human escalation is temporarily unavailable. Our team will reach out to you shortly.",
        "silence_reprompt":      "Still here — take your time.",
        "action_expired":        "We timed out. Want to continue?",
        "unknown_escalate":      "Let me connect you with our team.",
        "confirm_reprompt":      "Shall I go ahead?",
    },
}


def get_fast_response(
    key: str,
    call_mode: str = WAVVY_DEMO,
    **kwargs,
) -> str | None:
    """
    Returns formatted response string for the given key + call_mode,
    or None if the key is not found in this mode.
    Template variables are filled via kwargs (e.g., name="Arjun").
    """
    mode_responses = FAST_RESPONSES.get(call_mode, {})
    template = mode_responses.get(key)
    if not template:
        return None
    try:
        return template.format(**kwargs)
    except KeyError:
        # Return unformatted template rather than crashing
        return template
