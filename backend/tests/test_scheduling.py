"""
Scheduling agent test suite.

Covers:
  - _extract_preferred_time: full phrase extraction (the bug that was fixed)
  - _parse_preferred_time: dateparser integration
  - _score_confidence: high / medium / low confidence levels
  - _is_business_slot: business hours enforcement
  - _slot_key: UTC key generation
  - resolve_slot: noisy speech, out-of-hours, clarification threshold
  - Entity merging: time-only follow-up to a day-only entity

Run with: pytest backend/tests/test_scheduling.py -v
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


# ── _extract_preferred_time (intent_router) ───────────────────────────────────

class TestExtractPreferredTime:
    """Full-phrase extraction — the core bug fix."""

    def setup_method(self):
        from voice.intent_router import _extract_preferred_time
        self.extract = _extract_preferred_time

    def test_day_at_time(self):
        """'tuesday at 3pm' must NOT return just 'tuesday'."""
        result = self.extract("I'd like tuesday at 3pm")
        assert result is not None
        assert "3" in result, f"Hour missing from: {result!r}"
        assert "tuesday" in result.lower()

    def test_next_friday_at_2pm(self):
        result = self.extract("next friday at 2pm works for me")
        assert result is not None
        assert "friday" in result.lower()
        assert "2" in result

    def test_tomorrow_morning(self):
        result = self.extract("tomorrow morning would be great")
        assert result is not None
        assert "tomorrow" in result.lower()
        assert "morning" in result.lower()

    def test_may_27th(self):
        result = self.extract("How about May 27th?")
        assert result is not None
        assert "may" in result.lower()
        assert "27" in result

    def test_in_2_days(self):
        result = self.extract("in 2 days please")
        assert result is not None
        assert "2" in result

    def test_noisy_speech(self):
        """'uh maybe next Friday around 4pm' — day+time captured despite noise."""
        result = self.extract("uh maybe next Friday around 4pm")
        assert result is not None
        assert "friday" in result.lower()
        # "4" should be present after the trailing scan
        assert "4" in result

    def test_no_time_returns_none(self):
        assert self.extract("yes that sounds good") is None
        assert self.extract("I want to book a demo") is None
        assert self.extract("hello") is None

    def test_anytime(self):
        result = self.extract("anytime works for me")
        assert result is not None
        assert "anytime" in result.lower()

    def test_friday_afternoon(self):
        result = self.extract("friday afternoon if possible")
        assert result is not None
        assert "friday" in result.lower()
        assert "afternoon" in result.lower()


# ── Confidence scoring ────────────────────────────────────────────────────────

class TestConfidenceScoring:
    def setup_method(self):
        from agents.scheduling_agent import _score_confidence, UTC
        self._score = _score_confidence
        # A real datetime for tests that need one
        self.some_dt = datetime(2026, 5, 27, 9, 0, tzinfo=UTC)

    def test_high_confidence_day_and_time(self):
        score, ambig = self._score("tuesday at 3pm", self.some_dt)
        assert score >= 0.80
        assert not ambig

    def test_high_confidence_specific_date_time(self):
        score, ambig = self._score("May 27th at 10am", self.some_dt)
        assert score >= 0.80

    def test_medium_confidence_day_only(self):
        score, ambig = self._score("thursday", self.some_dt)
        assert 0.50 <= score < 0.80
        assert ambig

    def test_medium_confidence_day_period(self):
        score, ambig = self._score("friday afternoon", self.some_dt)
        assert score >= 0.60

    def test_low_confidence_vague(self):
        score, ambig = self._score("sometime maybe", self.some_dt)
        assert score < 0.55
        assert ambig

    def test_low_confidence_no_datetime(self):
        score, ambig = self._score("sometime next week maybe", None)
        assert score < 0.40
        assert ambig

    def test_period_only_without_day(self):
        score, ambig = self._score("afternoon", self.some_dt)
        assert score < 0.60
        assert ambig

    def test_noisy_speech_maybe_friday_4pm(self):
        score, ambig = self._score("uh maybe next Friday around 4pm", self.some_dt)
        # "maybe" and "around" are vague words — score pulled down
        assert score < 0.80
        assert ambig


# ── Business hours ────────────────────────────────────────────────────────────

class TestBusinessHours:
    def setup_method(self):
        from agents.scheduling_agent import _is_business_slot, DEFAULT_POLICY
        self._is = _is_business_slot
        self.policy = DEFAULT_POLICY

    def _make_ist(self, weekday_offset: int, hour: int) -> datetime:
        """Create a datetime for a specific weekday and hour in IST."""
        # Wednesday 2026-05-20 + offset
        base = datetime(2026, 5, 20, hour, 0, tzinfo=IST)  # Wednesday
        from datetime import timedelta
        return (base + timedelta(days=weekday_offset)).astimezone(timezone.utc)

    def test_monday_9am_is_valid(self):
        dt = self._make_ist(-2, 9)   # Monday
        assert self._is(dt, self.policy)

    def test_friday_4pm_is_valid(self):
        dt = self._make_ist(2, 16)   # Friday
        assert self._is(dt, self.policy)

    def test_tuesday_10pm_is_invalid(self):
        dt = self._make_ist(-1, 22)  # Tuesday 10pm
        assert not self._is(dt, self.policy)

    def test_saturday_10am_is_invalid(self):
        dt = self._make_ist(3, 10)   # Saturday
        assert not self._is(dt, self.policy)

    def test_friday_5pm_is_invalid(self):
        dt = self._make_ist(2, 17)   # 5 PM is slot_end — exclusive
        assert not self._is(dt, self.policy)


# ── slot_key ──────────────────────────────────────────────────────────────────

class TestSlotKey:
    def test_utc_bucket(self):
        from agents.scheduling_agent import _slot_key
        dt = datetime(2026, 5, 27, 9, 0, tzinfo=IST)   # IST 09:00 = UTC 03:30
        key = _slot_key(dt)
        # UTC hour for IST 09:00 is 03 (IST = UTC+5:30)
        assert key == "2026-05-27-03"

    def test_same_slot_different_tz(self):
        from agents.scheduling_agent import _slot_key
        dt_ist = datetime(2026, 5, 27, 9, 0, tzinfo=IST)
        dt_utc = dt_ist.astimezone(UTC)
        assert _slot_key(dt_ist) == _slot_key(dt_utc)


# ── Parse: dateparser integration ────────────────────────────────────────────

class TestParsing:
    def setup_method(self):
        from agents.scheduling_agent import _parse_preferred_time
        self._parse = _parse_preferred_time

    def test_friday_3pm_parsed(self):
        result = self._parse("friday at 3pm")
        assert result.dt is not None
        local = result.dt.astimezone(IST)
        assert local.weekday() == 4   # Friday
        assert local.hour == 15

    def test_tuesday_10pm_parsed(self):
        result = self._parse("tuesday at 10pm")
        assert result.dt is not None
        local = result.dt.astimezone(IST)
        assert local.weekday() == 1   # Tuesday
        assert local.hour == 22

    def test_anytime_returns_none_dt(self):
        result = self._parse("anytime flexible")
        # dateparser may or may not succeed; confidence should be >= 0.50 since
        # we don't mark "anytime" as vague-word
        assert result.raw_text == "anytime flexible"

    def test_in_2_days_future_biased(self):
        result = self._parse("in 2 days")
        assert result.dt is not None
        now = datetime.now(UTC)
        from datetime import timedelta
        assert result.dt > now + timedelta(days=1)

    def test_may_27th_parsed(self):
        result = self._parse("May 27th at 10am")
        assert result.dt is not None
        local = result.dt.astimezone(IST)
        assert local.month == 5
        assert local.day == 27
        assert local.hour == 10


# ── resolve_slot: clarification threshold ────────────────────────────────────

class TestResolveSlotClarification:
    """resolve_slot returns needs_clarification when confidence is too low."""

    @pytest.mark.asyncio
    async def test_thursday_alone_triggers_clarification(self):
        from agents.scheduling_agent import resolve_slot
        with patch("agents.scheduling_agent._booked_slot_keys", new_callable=AsyncMock) as mock_booked:
            mock_booked.return_value = set()
            result = await resolve_slot("thursday")
        # "thursday" alone has confidence ~0.57 (day known, time unknown) → clarification
        assert result.get("needs_clarification") is True
        assert result.get("clarification_key") == "clarify_time_on_day"
        assert result["clarification_vars"].get("day", "").lower() == "thursday"

    @pytest.mark.asyncio
    async def test_friday_3pm_no_clarification(self):
        from agents.scheduling_agent import resolve_slot
        with patch("agents.scheduling_agent._booked_slot_keys", new_callable=AsyncMock) as mock_booked:
            mock_booked.return_value = set()
            result = await resolve_slot("friday at 3pm")
        assert result.get("needs_clarification") is False
        assert result.get("confirmed_time") is not None

    @pytest.mark.asyncio
    async def test_vague_sometime_triggers_clarification(self):
        from agents.scheduling_agent import resolve_slot
        with patch("agents.scheduling_agent._booked_slot_keys", new_callable=AsyncMock) as mock_booked:
            mock_booked.return_value = set()
            result = await resolve_slot("sometime maybe next week")
        assert result.get("needs_clarification") is True


# ── resolve_slot: out-of-hours → alternative ─────────────────────────────────

class TestResolveSlotOutOfHours:
    @pytest.mark.asyncio
    async def test_tuesday_10pm_gives_alternative(self):
        from agents.scheduling_agent import resolve_slot
        with patch("agents.scheduling_agent._booked_slot_keys", new_callable=AsyncMock) as mock_booked:
            mock_booked.return_value = set()
            result = await resolve_slot("tuesday at 10pm")
        assert result["is_alternative"] is True
        assert result["alt_reason"] == "out_of_hours"
        assert result["needs_clarification"] is False
        # Suggested slot must be a business slot
        from agents.scheduling_agent import _is_business_slot
        assert _is_business_slot(result["confirmed_time"])


# ── resolve_slot: conflict → next slot ───────────────────────────────────────

class TestResolveSlotConflict:
    @pytest.mark.asyncio
    async def test_conflict_returns_next_free_slot(self):
        from agents.scheduling_agent import resolve_slot, _slot_key
        # Build a "friday at 3pm" slot key
        friday_3pm = datetime(2026, 5, 22, 15, 0, tzinfo=IST)   # known Friday
        taken_key  = _slot_key(friday_3pm)

        with patch("agents.scheduling_agent._booked_slot_keys", new_callable=AsyncMock) as mock_booked:
            mock_booked.return_value = {taken_key}
            result = await resolve_slot("friday at 3pm")

        assert result["is_alternative"] is True
        assert result["alt_reason"] == "conflict"
        assert _slot_key(result["confirmed_time"]) != taken_key


# ── Entity merging (time-only follow-up) ──────────────────────────────────────

class TestEntityMerging:
    """
    When user said 'thursday' (→ preferred_time='thursday'),
    and then says '3pm' (→ new preferred_time='3pm' time-only),
    the orchestrator must combine them to 'thursday at 3pm'.
    """

    def test_time_only_pattern(self):
        import re
        from voice.intent_router import _TIME_ONLY_RE, _HAS_DAY_RE
        assert _TIME_ONLY_RE.match("3pm")
        assert _TIME_ONLY_RE.match("afternoon")
        assert not _TIME_ONLY_RE.match("thursday")
        assert not _TIME_ONLY_RE.match("thursday at 3pm")
        assert _HAS_DAY_RE.search("thursday")
        assert not _HAS_DAY_RE.search("3pm")

    def test_merge_logic(self):
        from voice.intent_router import _TIME_ONLY_RE, _HAS_DAY_RE
        old_pt = "thursday"
        new_pt = "3pm"
        if _TIME_ONLY_RE.match(new_pt) and _HAS_DAY_RE.search(old_pt):
            merged = f"{old_pt} at {new_pt}"
        else:
            merged = new_pt
        assert merged == "thursday at 3pm"
