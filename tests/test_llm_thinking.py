"""shared/llm_thinking.py — the `thinking=` explicit-per-caller fix (#575, 2026-08-21).

ROOT CAUSE (proven, not re-litigated here): on sonnet-5 the extended-thinking block
SHARES `max_tokens` with the text/tool output. Left unset, the SDK defaults to
adaptive thinking, so a hard call can burn the ENTIRE (shared) output ceiling on
thinking and return zero text — the decisive 2026-08-19 row: `theme_validation`
consumed 1000/1000 output tokens and came back with `blocks=['thinking']`, no text
at all. `budget_tokens` is REJECTED on sonnet-5 — `{"type": "disabled"}` vs leaving
`thinking` unset (adaptive) is the only lever.

These tests pin:
  1. registry integrity — every THINKING_DISABLED name is a real output_ceilings
     caller;
  2. call-site pins — the five schema-bounded callers explicitly disable thinking,
     and the two freeform callers (theme_discovery, system_review_weekly) leave it
     on the model default for their FIRST attempt but disable it on the recovery
     retry;
  3. behavior — a fake Anthropic client records the kwargs each caller actually
     sends, so a future edit that silently drops the kwarg breaks a test instead
     of rotting quietly (the exact failure class #575 exists to stop);
  4. `_call_advisor` truncation honesty — a truncated/empty advisor response must
     return the same explicit "use your best judgment" fallback the except-path
     already uses, never a silent empty string a caller could read as "no
     objection."
"""
from __future__ import annotations

import json
import pathlib
from datetime import date
from types import SimpleNamespace

import pytest

from shared import llm_thinking
from shared import output_ceilings as oc

REPO = pathlib.Path(__file__).resolve().parents[1]
_TE = REPO / "agents/market_intelligence/theme_engine.py"
_TS = REPO / "agents/market_intelligence/theme_synthesis.py"
_SR = REPO / "agents/market_intelligence/system_review.py"


# ── 1. registry integrity ────────────────────────────────────────────────────

def test_disabled_constant_shape():
    assert llm_thinking.DISABLED == {"type": "disabled"}


def test_every_disabled_caller_is_a_registered_ceiling():
    for caller in llm_thinking.THINKING_DISABLED:
        assert caller in oc.CEILINGS, (
            f"{caller} is in THINKING_DISABLED but not registered in "
            "shared/output_ceilings.py — thinking config must track a real caller")


def test_expected_five_schema_bounded_callers():
    """Pin the classification itself, not just its shape — a caller silently
    added or removed here is a criterion change to the fix, worth a red test."""
    assert llm_thinking.THINKING_DISABLED == {
        "theme_validation", "theme_assignment", "theme_split",
        "narrative_theme_discovery", "theme_synthesis",
    }


# ── 2. call-site pins (source scan — catches a silent revert) ───────────────

def test_five_always_disabled_call_sites_pinned_in_theme_engine():
    src = _TE.read_text(encoding="utf-8")
    # theme_validation, theme_assignment, theme_split, narrative_theme_discovery x2
    assert src.count("thinking=llm_thinking.DISABLED") == 5, (
        "expected exactly 5 unconditional thinking=llm_thinking.DISABLED call sites "
        "in theme_engine.py (theme_validation, theme_assignment, theme_split, "
        "narrative_theme_discovery x2 lane1/lane2)")


def test_theme_synthesis_call_site_pinned():
    src = _TS.read_text(encoding="utf-8")
    assert "thinking=llm_thinking.DISABLED" in src


def test_theme_discovery_conditional_thinking_pinned():
    """theme_discovery stays on the model default for tool_choice=auto (genuinely
    open-ended advisor-or-report judgment) and only disables thinking once
    force_report has fired — reusing the EXISTING truncation-recovery retry loop
    rather than adding a new one."""
    src = _TE.read_text(encoding="utf-8")
    assert '**({"thinking": llm_thinking.DISABLED} if force_report else {})' in src


def test_system_review_conditional_thinking_pinned():
    """system_review_weekly stays on the model default for its first attempt
    (freeform operator-facing digest) and gets a NEW one-shot retry with thinking
    disabled if that attempt truncates — it had zero truncation handling before
    #575 despite three prior truncations."""
    src = _SR.read_text(encoding="utf-8")
    assert '{"thinking": llm_thinking.DISABLED} if attempt == 1 else {}' in src


def test_call_advisor_truncation_honesty_pinned():
    """_call_advisor stays freeform (senior judgment call, no fixed schema) but
    must never let a truncated/empty response read as a real verdict."""
    src = _TE.read_text(encoding="utf-8")
    assert "if is_truncated(resp) or not verdict.strip():" in src
    assert 'verdict = "Advisor unavailable — use your best judgment."' in src


# ── 3. behavior: the five always-disabled callers ────────────────────────────

@pytest.mark.asyncio
async def test_theme_validation_disables_thinking(monkeypatch):
    from agents.market_intelligence import theme_engine

    class _Block:
        type = "text"
        text = json.dumps({"remove": []})

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    captured: dict = {}

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    class _Client:
        messages = _Messages()

    async def fake_protected():
        return set()

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _Client())
    monkeypatch.setattr(theme_engine, "get_operator_protected_set", fake_protected)

    await theme_engine._validate_theme_membership(
        "Test Theme", ["AAA", "BBB", "CCC", "DDD", "EEE"], changelog=[])

    assert captured.get("thinking") == llm_thinking.DISABLED


@pytest.mark.asyncio
async def test_theme_assignment_disables_thinking(monkeypatch):
    from agents.market_intelligence import theme_engine

    class _Block:
        def __init__(self, type_, name=None, input_=None, id="b1"):
            self.type = type_
            self.name = name
            self.input = input_ or {}
            self.id = id

    class _Resp:
        def __init__(self, blocks):
            self.content = blocks
            self.stop_reason = "tool_use"

    captured: dict = {}

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp([_Block("tool_use", name="assign_stocks_to_themes",
                                  input_={"assignments": []})])

    class _Client:
        messages = _Messages()

    await theme_engine._propose_assignment_batch(
        _Client(),
        [{"ticker": "AAA", "rs_composite": 90, "sector": "Technology"}],
        shared_prefix="Existing themes: (none)",
        cooldown_note="",
        advisor_state={"calls": 0},
        batch_no=1, n_batches=1, pool_size=1,
    )

    assert captured.get("thinking") == llm_thinking.DISABLED


@pytest.mark.asyncio
async def test_theme_split_disables_thinking(monkeypatch):
    from agents.market_intelligence import theme_engine

    class _Block:
        def __init__(self, type_, name=None, input_=None, id="b1"):
            self.type = type_
            self.name = name
            self.input = input_ or {}
            self.id = id

    class _Resp:
        def __init__(self, blocks):
            self.content = blocks
            self.stop_reason = "tool_use"

    captured: dict = {}

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            # Decline: split=None
            return _Resp([_Block("tool_use", name="propose_split", input_={"split": None})])

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _Client())

    theme = {"name": "Fat Theme", "tickers": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]}
    await theme_engine._split_fat_theme(theme, {}, advisor_calls_used=0)

    assert captured.get("thinking") == llm_thinking.DISABLED


@pytest.mark.asyncio
async def test_narrative_theme_discovery_lane1_disables_thinking(monkeypatch):
    from agents.market_intelligence import theme_engine
    import agents.market_intelligence.db as db_mod
    import agents.market_intelligence.spend_tracker as spend_tracker

    class _Msg:
        def __init__(self, payload):
            self.content = [SimpleNamespace(type="tool_use", name="report_narrative_themes",
                                            input=payload, id="t1")]
            self.usage = None
            self.stop_reason = "tool_use"

    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _Msg({"themes": [], "seeds": []})

    client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: client)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(spend_tracker, "log_anthropic_call_safe", _noop)
    monkeypatch.setattr(db_mod, "log_audit_event", _noop)

    async def _false():
        return False

    async def _alerts(*a, **k):
        return [
            {"ticker": "AAA", "ep_score": 80.0, "gap_pct": 10.0, "catalyst": "AI data center lease"},
            {"ticker": "BBB", "ep_score": 75.0, "gap_pct": 8.0, "catalyst": "AI data center lease"},
        ]

    monkeypatch.setattr(db_mod, "get_lane2_grouping_v2_enabled", _false)
    monkeypatch.setattr(db_mod, "get_today_ep_alerts", _alerts)

    await theme_engine.discover_narrative_themes(date(2026, 8, 21), persist=False)

    assert captured.get("thinking") == llm_thinking.DISABLED


@pytest.mark.asyncio
async def test_theme_synthesis_disables_thinking(monkeypatch):
    from agents.market_intelligence import theme_synthesis
    import agents.market_intelligence.briefing as briefing_mod
    import agents.market_intelligence.collector as collector_mod
    import agents.market_intelligence.db as db_mod
    from agents.market_intelligence import theme_engine as theme_engine_mod

    monkeypatch.setattr(collector_mod, "et_today", lambda: date(2026, 8, 21))
    monkeypatch.setattr(collector_mod, "last_trading_day", lambda: date(2026, 8, 21))

    async def _velocity(d, limit=30):
        return [{"ticker": f"T{i}", "rs_composite": 95.0} for i in range(8)]

    async def _turners(d, limit=40):
        return []

    async def _descs(tickers):
        return {}

    async def _themes():
        return []

    async def _persist(rd, kept):
        return len(kept)

    async def _audit(event_type, summary, detail=""):
        return None

    async def _send(*a, **k):
        return True

    monkeypatch.setattr(db_mod, "get_rs_velocity", _velocity)
    monkeypatch.setattr(db_mod, "get_rs_turners", _turners)
    monkeypatch.setattr(db_mod, "get_descriptions_batch", _descs)
    monkeypatch.setattr(db_mod, "get_active_themes", _themes)
    monkeypatch.setattr(db_mod, "persist_synthesis_theme_candidates", _persist)
    monkeypatch.setattr(db_mod, "log_audit_event", _audit)
    monkeypatch.setattr(briefing_mod, "send_telegram_message", _send)

    captured: dict = {}

    class _Block:
        def __init__(self, type_, input_=None):
            self.type = type_
            self.input = input_ or {}

    class _Resp:
        content = [_Block("tool_use", {"cohorts": []})]
        stop_reason = "tool_use"

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(theme_engine_mod, "_get_anthropic_client", lambda: _Client())

    await theme_synthesis.run_theme_synthesis()

    assert captured.get("thinking") == llm_thinking.DISABLED


# ── 4. behavior: the two recoverable freeform callers ────────────────────────

@pytest.mark.asyncio
async def test_theme_discovery_first_attempt_leaves_thinking_on_default(monkeypatch):
    """The healthy path (no truncation): thinking is NOT set at all on the
    tool_choice=auto attempt — the model default (adaptive) applies."""
    from agents.market_intelligence import theme_engine as te
    from agents.market_intelligence import universe

    monkeypatch.setitem(universe.TICKER_DESC, "MU", "DRAM and NAND memory maker")
    monkeypatch.setitem(universe.TICKER_DESC, "SNDK", "NAND flash storage maker")
    monkeypatch.setitem(universe.TICKER_DESC, "WDC", "hard drive and flash storage maker")
    stocks = [{"ticker": tk, "rs_composite": 95, "sector": "Technology"}
              for tk in ("MU", "SNDK", "WDC")]
    sbt = {s["ticker"]: s for s in stocks}

    theme_block = SimpleNamespace(
        type="tool_use", name="report_themes",
        input={"analysis_scratchpad": "memory", "themes": [
            {"name": "AI Memory & HBM", "thesis": "HBM demand.",
             "tickers": ["MU", "SNDK", "WDC"]}]},
        id="b1")
    resp = SimpleNamespace(content=[theme_block], stop_reason="tool_use",
                           usage=SimpleNamespace(output_tokens=200))

    calls = []

    async def _create(**kwargs):
        calls.append(kwargs)
        return resp

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    await te._discover_new_themes(stocks, [], sbt)

    assert len(calls) == 1
    assert "thinking" not in calls[0], (
        "first (tool_choice=auto) attempt must leave thinking unset — the model "
        "default is deliberately preserved for this genuinely open-ended call")


@pytest.mark.asyncio
async def test_theme_discovery_forced_retry_disables_thinking(monkeypatch):
    """Truncation-recovery path: the first call truncates, the existing
    force_report retry fires, and that retry now ALSO disables thinking."""
    from agents.market_intelligence import theme_engine as te
    from agents.market_intelligence import universe

    monkeypatch.setitem(universe.TICKER_DESC, "MU", "DRAM and NAND memory maker")
    monkeypatch.setitem(universe.TICKER_DESC, "SNDK", "NAND flash storage maker")
    monkeypatch.setitem(universe.TICKER_DESC, "WDC", "hard drive and flash storage maker")
    stocks = [{"ticker": tk, "rs_composite": 95, "sector": "Technology"}
              for tk in ("MU", "SNDK", "WDC")]
    sbt = {s["ticker"]: s for s in stocks}

    truncated = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="")],
        stop_reason="max_tokens", usage=SimpleNamespace(output_tokens=8000))
    theme_block = SimpleNamespace(
        type="tool_use", name="report_themes",
        input={"analysis_scratchpad": "memory", "themes": [
            {"name": "AI Memory & HBM", "thesis": "HBM demand.",
             "tickers": ["MU", "SNDK", "WDC"]}]},
        id="b1")
    forced = SimpleNamespace(content=[theme_block], stop_reason="tool_use",
                             usage=SimpleNamespace(output_tokens=200))

    calls = []
    responses = [truncated, forced]

    async def _create(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = await te._discover_new_themes(stocks, [], sbt)

    assert len(calls) == 2
    assert "thinking" not in calls[0]
    assert calls[1]["thinking"] == llm_thinking.DISABLED
    assert [t["name"] for t in out] == ["AI Memory & HBM"]


@pytest.mark.asyncio
async def test_system_review_first_attempt_leaves_thinking_on_default(monkeypatch):
    from agents.market_intelligence import system_review as sr

    resp = SimpleNamespace(
        content=[SimpleNamespace(text="Weekly review text.")],
        stop_reason="end_turn")

    calls = []

    async def _create(**kwargs):
        calls.append(kwargs)
        return resp

    class _FakeClient:
        def __init__(self, api_key=""):
            self.messages = SimpleNamespace(create=_create)

    monkeypatch.setattr(sr.anthropic, "AsyncAnthropic", _FakeClient)

    metrics = {"window": {"days": 7, "start": "2026-08-14", "end": "2026-08-21"}}
    out = await sr._synthesize(metrics, None)

    assert len(calls) == 1
    assert "thinking" not in calls[0]
    assert out == "Weekly review text."


@pytest.mark.asyncio
async def test_system_review_retries_once_with_thinking_disabled_on_truncation(monkeypatch):
    from agents.market_intelligence import system_review as sr

    truncated = SimpleNamespace(content=[SimpleNamespace(text="")], stop_reason="max_tokens")
    completed = SimpleNamespace(
        content=[SimpleNamespace(text="Recovered weekly review.")],
        stop_reason="end_turn")

    calls = []
    responses = [truncated, completed]

    async def _create(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    class _FakeClient:
        def __init__(self, api_key=""):
            self.messages = SimpleNamespace(create=_create)

    monkeypatch.setattr(sr.anthropic, "AsyncAnthropic", _FakeClient)

    metrics = {"window": {"days": 7, "start": "2026-08-14", "end": "2026-08-21"}}
    out = await sr._synthesize(metrics, None)

    assert len(calls) == 2
    assert "thinking" not in calls[0]
    assert calls[1]["thinking"] == llm_thinking.DISABLED
    assert out == "Recovered weekly review."


@pytest.mark.asyncio
async def test_system_review_gives_up_after_one_retry_no_infinite_loop(monkeypatch):
    """Both attempts truncate: exactly 2 calls total (never loops forever), and
    whatever partial text came back is still returned rather than raising."""
    from agents.market_intelligence import system_review as sr

    truncated1 = SimpleNamespace(content=[SimpleNamespace(text="")], stop_reason="max_tokens")
    truncated2 = SimpleNamespace(content=[SimpleNamespace(text="partial")], stop_reason="max_tokens")

    calls = []
    responses = [truncated1, truncated2]

    async def _create(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    class _FakeClient:
        def __init__(self, api_key=""):
            self.messages = SimpleNamespace(create=_create)

    monkeypatch.setattr(sr.anthropic, "AsyncAnthropic", _FakeClient)

    metrics = {"window": {"days": 7, "start": "2026-08-14", "end": "2026-08-21"}}
    out = await sr._synthesize(metrics, None)

    assert len(calls) == 2, "must give up after one retry, never loop forever"
    assert out == "partial"


# ── 5. behavior: _call_advisor truncation honesty ────────────────────────────

@pytest.mark.asyncio
async def test_call_advisor_returns_fallback_on_truncated_empty_response(monkeypatch):
    from agents.market_intelligence import theme_engine as te

    # blocks=['thinking'], zero text — the exact shape that hit theme_validation
    # 2026-08-19, reproduced here for the advisor (which tripped the live alarm
    # 2026-08-12).
    resp = SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking="deliberating...")],
        stop_reason="max_tokens")

    async def _create(**kwargs):
        return resp

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    verdict = await te._call_advisor("is this a real cluster?", "AAA, BBB", caller="discovery")

    assert verdict == "Advisor unavailable — use your best judgment.", (
        "a truncated/empty advisor response must never surface as '' — a caller "
        "could read that as 'no objection' rather than 'the advisor never answered'")


@pytest.mark.asyncio
async def test_call_advisor_returns_real_verdict_on_healthy_response(monkeypatch):
    from agents.market_intelligence import theme_engine as te

    resp = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Yes — this is a real cluster.")],
        stop_reason="end_turn")

    async def _create(**kwargs):
        return resp

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    verdict = await te._call_advisor("is this a real cluster?", "AAA, BBB", caller="discovery")

    assert verdict == "Yes — this is a real cluster."
