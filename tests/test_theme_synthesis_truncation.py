"""Theme-synthesis truncation handling (advisor flag, 2026-06-24).

The fix that unblocked theme discovery — `max_tokens` 2000→4000 + capturing `stop_reason` in the
`theme_synthesis_run` telemetry — shipped untested. The exact failure it cures: a forced tool call
that TRUNCATES (`stop_reason='max_tokens'`) returns an incomplete / missing tool_use block, so
`tool_input.get('cohorts')` is empty → 0 cohorts proposed, SILENTLY — indistinguishable in the logs
from a genuine "no emerging cohorts" unless the stop_reason is recorded. (Discovery proposed 0 for
3 days straight, 6/22–24, because of this.) These tests pin: a truncated response proposes 0
gracefully AND records `max_tokens`; a normal response parses the cohorts AND records `tool_use`.
"""
from datetime import date

import pytest

import agents.market_intelligence.briefing as briefing_mod
import agents.market_intelligence.collector as collector_mod
import agents.market_intelligence.db as db_mod
import agents.market_intelligence.theme_engine as theme_engine_mod
from agents.market_intelligence import theme_synthesis


class _Block:
    def __init__(self, type_, input_=None):
        self.type = type_
        self.input = input_ or {}


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _Messages:
    def __init__(self, resp):
        self._resp = resp

    async def create(self, **kwargs):
        return self._resp


class _Client:
    def __init__(self, resp):
        self.messages = _Messages(resp)


def _setup(monkeypatch, resp):
    """Mock run_theme_synthesis's deps so it reaches the LLM call and returns the given response."""
    monkeypatch.setattr(collector_mod, "et_today", lambda: date(2026, 6, 24))
    monkeypatch.setattr(collector_mod, "last_trading_day", lambda: date(2026, 6, 24))

    async def _velocity(d, limit=30):
        # >= _MIN_MEMBERS*2 candidates so the function doesn't short-circuit before the LLM.
        return [{"ticker": f"T{i}", "rs_composite": 95.0} for i in range(8)]

    async def _turners(d, limit=40):
        return []

    async def _descs(tickers):
        return {}

    async def _themes(*a, **k):
        return []

    async def _persist(rd, kept):
        return len(kept)

    monkeypatch.setattr(db_mod, "get_rs_velocity", _velocity)
    monkeypatch.setattr(db_mod, "get_rs_turners", _turners)
    monkeypatch.setattr(db_mod, "get_descriptions_batch", _descs)
    monkeypatch.setattr(db_mod, "get_active_themes", _themes)
    monkeypatch.setattr(db_mod, "persist_synthesis_theme_candidates", _persist)

    captured: list[tuple[str, str]] = []

    async def _audit(event_type, summary, detail=""):
        captured.append((event_type, detail))

    monkeypatch.setattr(db_mod, "log_audit_event", _audit)
    monkeypatch.setattr(theme_engine_mod, "_get_anthropic_client", lambda: _Client(resp))

    async def _send(*a, **k):
        return True

    monkeypatch.setattr(briefing_mod, "send_telegram_message", _send)
    return captured


@pytest.mark.asyncio
async def test_truncated_response_proposes_zero_and_records_stop_reason(monkeypatch):
    # stop_reason='max_tokens' + NO tool_use block (truncated before the tool JSON) -> proposes 0.
    captured = _setup(monkeypatch, _Resp("max_tokens", [_Block("text")]))
    result = await theme_synthesis.run_theme_synthesis()
    assert result["n_proposed"] == 0  # graceful — no crash on the truncated/empty tool input
    runs = [d for et, d in captured if et == "theme_synthesis_run"]
    # the silent-truncation tell must be recorded (this is what made the 6/22-24 zeros legible)
    assert runs and '"stop_reason": "max_tokens"' in runs[-1]


@pytest.mark.asyncio
async def test_normal_response_parses_cohorts_and_records_stop_reason(monkeypatch):
    cohorts = [{"name": "Test Cohort", "tickers": ["T1", "T2", "T3"],
                "confidence": "high", "thesis": "a coherent cross-ticker thesis"}]
    captured = _setup(monkeypatch, _Resp("tool_use", [_Block("tool_use", {"cohorts": cohorts})]))
    result = await theme_synthesis.run_theme_synthesis()
    assert result["n_proposed"] == 1  # the cohort was parsed from the completed tool call
    runs = [d for et, d in captured if et == "theme_synthesis_run"]
    assert runs and '"stop_reason": "tool_use"' in runs[-1]
