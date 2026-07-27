"""#167 Lane-2 grouping v2 (operator-ruled 2026-07-27) — flag-gated behavior pins.

The four load-bearing contracts:
1. Flag OFF ⇒ discover_narrative_themes is BYTE-IDENTICAL to the pre-flag v1
   behavior — the prompt is compared against a FROZEN copy of the original v1
   template (any drift of the shared _LANE2_NARRATIVE_RULES / contract strings
   breaks this test), and the window fetch is never touched.
2. The rolling window is 10 TRADING days (weekend-skipping) — the operator's
   measured chain WULF 07-06 → HUT/IREN 07-20 must fit exactly.
3. Cross-day dedup: per ticker keep highest ep_score, tie → latest date; the
   same-day anchor set is computed BEFORE dedup.
4. Missing grounded_text degrades gracefully (grounded → claude_analysis →
   catalyst), never crashes, and the fallback mix is VISIBLE in the audit
   summary.

GRADE-AFFECTING context: Lane-2 proposals feed the judge's active_narratives
(ep_detector → assemble_judge_inputs), so the OFF-is-identical pin is a money
-path safety, not a style preference.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.db as db
import agents.market_intelligence.spend_tracker as spend_tracker
from agents.market_intelligence import theme_engine
from agents.market_intelligence.theme_engine import (
    LANE2_WINDOW_TRADING_DAYS,
    _build_lane2_v2_prompt,
    _dedupe_lane2_pool,
    _lane2_input_text,
    _lane2_window_start,
    discover_narrative_themes,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

_LONG_CATALYST = ("WULF gapped up because the company announced a transformative agreement. " * 10)[:500]
_GROUNDED = (
    "8-K: TeraWulf entered a 20-year lease with a global technology company for "
    "AI data center campus capacity at its Lake Mariner facility, with expected "
    "revenue of approximately $3.7 billion over the initial term. " * 20
)


def _alert(ticker, d, ep=80.0, gap=12.0, catalyst=_LONG_CATALYST,
           analysis="Grounded analysis: AI data-center capacity lease.",
           grounded=_GROUNDED):
    return {
        "ticker": ticker, "alert_date": d, "ep_score": ep, "gap_pct": gap,
        "catalyst": catalyst, "claude_analysis": analysis, "grounded_text": grounded,
    }


class _FakeMsg:
    def __init__(self, text):
        self.content = [SimpleNamespace(text=text)]
        self.usage = None


def _wire(monkeypatch, *, flag_on, today_alerts=(), window_alerts=(),
          llm_response='{"themes": []}'):
    """Patch every side-effecting dependency; return (captured_kwargs, mocks)."""
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeMsg(llm_response)

    client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: client)

    async def _noop_spend(**kwargs):
        return None

    monkeypatch.setattr(spend_tracker, "log_anthropic_call_safe", _noop_spend)

    mocks = SimpleNamespace(
        flag=AsyncMock(return_value=flag_on),
        today=AsyncMock(return_value=list(today_alerts)),
        window=AsyncMock(return_value=list(window_alerts)),
        persist=AsyncMock(side_effect=lambda d, themes, backfilled=False: len(themes)),
        audit=AsyncMock(),
    )
    monkeypatch.setattr(db, "get_lane2_grouping_v2_enabled", mocks.flag)
    monkeypatch.setattr(db, "get_today_ep_alerts", mocks.today)
    monkeypatch.setattr(db, "get_ep_alerts_window", mocks.window)
    monkeypatch.setattr(db, "persist_narrative_theme_candidates", mocks.persist)
    monkeypatch.setattr(db, "log_audit_event", mocks.audit)
    return captured, mocks


# ── 1. flag OFF ⇒ byte-identical v1 ──────────────────────────────────────────

def _v1_frozen_prompt(cand):
    """VERBATIM copy of the pre-flag v1 prompt construction (git d8f0ef3 era).
    Do NOT 'refactor' this to reuse theme_engine constants — its entire point
    is to be an independent frozen reference the shared constants are checked
    against."""
    lines = []
    for a in cand:
        cat = (a.get("catalyst") or a.get("claude_analysis") or "")[:280]
        lines.append(f"- {a['ticker']} (gap {a.get('gap_pct','?')}%, ep {a.get('ep_score')}): {cat}")
    return (
        "Below are today's gap-up momentum stocks and their catalysts. Identify EMERGING "
        "NARRATIVE THEMES that 2 OR MORE of them genuinely SHARE. Themes MAY span sectors and "
        "RS levels (e.g. a government-policy theme spanning Industrials + Tech + Defense). A theme "
        "must be a real shared story/catalyst, NOT a generic sector label.\n"
        "CRITICAL: a theme is a SPECIFIC shared NARRATIVE / DRIVER (a technology cycle, a "
        "government policy, a supply shortage, a product category, a specific industry catalyst) "
        "— NOT a generic CATALYST-TYPE that names coincidentally share because of the calendar. "
        "'They all beat Q1 earnings', 'broad earnings-beat momentum', 'raised guidance', or "
        "'relief rally' are NOT themes (those are catalyst categories, not narratives). A bare "
        "one-word catchall ('AI', 'software', 'tech') is also too generic — BUT a SPECIFIC "
        "AI/tech-DRIVEN narrative IS a valid theme (e.g. 'AI-native/vertical SaaS adoption', "
        "'AI data-center buildout', 'edge-AI silicon'). Group ONLY when the names share a SPECIFIC "
        "emerging story a trader would name as a theme (e.g. 'nuclear/AI power demand', 'defense "
        "drone expansion', 'quantum computing', 'GLP-1 obesity', 'edge-AI silicon', 'AI-native SaaS'). "
        "If there is NO genuine shared narrative across 2+ of these names, return an EMPTY "
        "list — do NOT force groupings.\n\n"
        "Stocks:\n" + "\n".join(lines) + "\n\n"
        'Return ONLY JSON: {"themes":[{"name":"<=6 words","catalyst_type":"theme|govt_policy|shortage|'
        'sales_acceleration|new_product|management_change|other","tickers":["TICK","TICK"],"thesis":"one sentence"}]}. '
        "Include a theme ONLY if 2+ of the listed tickers truly share it; otherwise themes=[]. "
        "The name's breadth must match the group: every grouped ticker must individually fit the name."
    )


@pytest.mark.asyncio
async def test_flag_off_is_byte_identical_v1(monkeypatch):
    d = date(2026, 7, 14)
    cand = [_alert("CLSK", d, ep=61.0), _alert("TSEM", d, ep=55.0)]
    captured, mocks = _wire(
        monkeypatch, flag_on=False, today_alerts=cand,
        llm_response='{"themes": [{"name": "AI data-center buildout", '
                     '"catalyst_type": "theme", "tickers": ["CLSK", "TSEM"], '
                     '"thesis": "Both add AI DC capacity."}]}')

    out = await discover_narrative_themes(d)

    # Exact prompt bytes of the pre-flag implementation — grounded_text unread,
    # 280-char truncation intact, no dates/TODAY markers.
    assert captured["messages"][0]["content"] == _v1_frozen_prompt(cand)
    assert captured["model"] == theme_engine.THEME_MODEL
    assert captured["max_tokens"] == 1500
    # v1 path never touches the window fetch or the anchor rule.
    mocks.window.assert_not_awaited()
    mocks.today.assert_awaited_once()
    assert out["themes"] == 1 and out["names"] == ["AI data-center buildout"]
    assert "pool" not in out and "input_sources" not in out
    # v1 audit summary format unchanged.
    assert mocks.audit.await_args.args[1] == \
        "2026-07-14: 2 alerts -> 1 narrative theme(s): ['AI data-center buildout']"


@pytest.mark.asyncio
async def test_flag_off_below_two_gate_unchanged(monkeypatch):
    d = date(2026, 7, 6)
    captured, mocks = _wire(monkeypatch, flag_on=False,
                            today_alerts=[_alert("WULF", d, ep=96.0)])
    out = await discover_narrative_themes(d)
    assert out["alerts"] == 1 and out["themes"] == 0
    assert not captured  # no LLM call
    assert mocks.audit.await_args.args[1] == \
        "2026-07-06: 1 qualifying alert(s) (<2) — no grouping"


@pytest.mark.asyncio
async def test_flag_fail_closed_on_db_error(monkeypatch):
    # The toggle read failing must select the v1 lane, never raise.
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert await db.get_lane2_grouping_v2_enabled() is False


# ── 2. ten TRADING days, not calendar ────────────────────────────────────────

def test_window_start_ten_trading_days_across_weekends():
    # Operator-measured chain: from Mon 2026-07-20, ten trading days back is
    # Mon 2026-07-06 — the window must reach WULF (07-06) and CLSK (07-14).
    assert LANE2_WINDOW_TRADING_DAYS == 10
    assert _lane2_window_start(date(2026, 7, 20)) == date(2026, 7, 6)
    # Mid-week anchor crossing two weekends.
    assert _lane2_window_start(date(2026, 6, 17)) == date(2026, 6, 3)
    # A 14-calendar-day window would be wrong: calendar arithmetic from 07-20
    # lands on 07-10 after 10 days — trading-day math is what reaches 07-06.
    assert (date(2026, 7, 20) - _lane2_window_start(date(2026, 7, 20))).days == 14


# ── 3. cross-day dedup + anchor set ──────────────────────────────────────────

def test_dedupe_highest_ep_wins_tie_latest_and_anchor_precedes_dedup():
    today = date(2026, 7, 14)
    rows = [
        # WULF: strongest alert 07-06 (ep 96) beats a weak 07-13 re-alert.
        _alert("WULF", date(2026, 7, 6), ep=96.0),
        _alert("WULF", date(2026, 7, 13), ep=55.0),
        # CLSK: alerted TODAY with ep 61, but an older ep-80 row wins the text —
        # CLSK must STILL be a same-day anchor (anchor set precedes dedup).
        _alert("CLSK", date(2026, 7, 9), ep=80.0),
        _alert("CLSK", today, ep=61.0),
        # TSEM: ep tie across two days → latest wins.
        _alert("TSEM", date(2026, 7, 10), ep=70.0),
        _alert("TSEM", today, ep=70.0),
        # Non-qualifying rows are invisible to pool AND anchors.
        _alert("JUNK", today, ep=42.0),
        _alert("BLNK", today, ep=88.0, catalyst=None, analysis=None),
    ]
    pool, anchors = _dedupe_lane2_pool(rows, today)
    kept = {a["ticker"]: a for a in pool}
    assert set(kept) == {"WULF", "CLSK", "TSEM"}
    assert kept["WULF"]["alert_date"] == date(2026, 7, 6) and kept["WULF"]["ep_score"] == 96.0
    assert kept["CLSK"]["alert_date"] == date(2026, 7, 9) and kept["CLSK"]["ep_score"] == 80.0
    assert kept["TSEM"]["alert_date"] == today  # tie → latest
    assert anchors == {"CLSK", "TSEM"}
    # Pool ordering is deterministic (date, ticker) — stable prompts replay-compare cleanly.
    assert [a["ticker"] for a in pool] == ["WULF", "CLSK", "TSEM"]


# ── 4. input fallback chain + degraded-day visibility ────────────────────────

def test_input_text_fallback_chain_budgets_and_flattening():
    d = date(2026, 7, 14)
    # Mid-doc evidence beyond any head-slice must survive: the replay pull
    # falsified a 2.5k head budget (SEC boilerplate head; CLSK 'AI'@6394,
    # JBL 'AI'@4430) — the budget is a >=10k safety ceiling, full-doc in
    # practice (era max grounded_text = 9,615 chars).
    assert theme_engine.LANE2_GROUNDED_BUDGET >= 9615
    rich = _alert("WULF", d, grounded="  line one\nline two  " + "x" * 6300 + " AI data-center lease " + "y" * 2000)
    text, tag = _lane2_input_text(rich)
    assert tag == "grounded"
    assert len(text) <= theme_engine.LANE2_GROUNDED_BUDGET
    assert "AI data-center lease" in text  # deep-in-doc evidence retained
    assert "\n" not in text and text.startswith("line one line two")

    no_grounded = _alert("CLSK", d, grounded=None)
    text, tag = _lane2_input_text(no_grounded)
    assert tag == "analysis" and text.startswith("Grounded analysis:")

    catalyst_only = _alert("TSEM", d, grounded="   ", analysis=None)
    text, tag = _lane2_input_text(catalyst_only)
    assert tag == "catalyst" and len(text) <= theme_engine.LANE2_CATALYST_BUDGET

    barren = _alert("HQ", d, grounded=None, analysis=None, catalyst=None)
    assert _lane2_input_text(barren) == ("", "none")  # never crashes


@pytest.mark.asyncio
async def test_v2_degraded_day_visible_in_audit_summary(monkeypatch):
    today = date(2026, 7, 14)
    window = [
        _alert("WULF", date(2026, 7, 6), ep=96.0),                       # grounded
        _alert("CLSK", today, ep=61.0, grounded=None),                    # → analysis
        _alert("TSEM", today, ep=55.0, grounded=None, analysis=None),     # → catalyst
    ]
    captured, mocks = _wire(monkeypatch, flag_on=True, window_alerts=window)
    out = await discover_narrative_themes(today)
    assert out["input_sources"] == {"grounded": 1, "analysis": 1, "catalyst": 1, "none": 0}
    summary = mocks.audit.await_args.args[1]
    assert "input grounded=1 analysis=1 catalyst=1" in summary
    assert f"v2({LANE2_WINDOW_TRADING_DAYS}td)" in summary


# ── v2 gate, prompt shape, anchor enforcement ────────────────────────────────

@pytest.mark.asyncio
async def test_v2_gate_requires_today_anchor(monkeypatch):
    today = date(2026, 7, 20)
    # A rich pool with NO same-day qualifying alert must not call the LLM —
    # nothing to anchor a new proposal on.
    window = [_alert("WULF", date(2026, 7, 6)), _alert("CLSK", date(2026, 7, 14))]
    captured, mocks = _wire(monkeypatch, flag_on=True, window_alerts=window)
    out = await discover_narrative_themes(today)
    assert not captured and out["themes"] == 0
    assert out["pool"] == 2 and out["alerts"] == 0
    assert "below gate" in mocks.audit.await_args.args[1]
    mocks.window.assert_awaited_once_with(date(2026, 7, 6), today)


@pytest.mark.asyncio
async def test_v2_lone_today_alert_groups_against_pool(monkeypatch):
    # The audit's §4 fix: a lone same-day alert (v1 killed the whole run) now
    # groups against the rolling pool.
    today = date(2026, 7, 14)
    window = [_alert("WULF", date(2026, 7, 6), ep=96.0), _alert("CLSK", today, ep=61.0)]
    captured, mocks = _wire(
        monkeypatch, flag_on=True, window_alerts=window,
        llm_response='{"themes": [{"name": "Bitcoin miners pivot to AI", '
                     '"catalyst_type": "theme", "tickers": ["WULF", "CLSK"], '
                     '"thesis": "Miners lease HPC capacity to AI tenants."}]}')
    out = await discover_narrative_themes(today)
    assert out["themes"] == 1 and out["names"] == ["Bitcoin miners pivot to AI"]
    prompt = captured["messages"][0]["content"]
    assert "- WULF [2026-07-06]" in prompt
    assert "- CLSK [TODAY]" in prompt
    assert "last 10 trading days" in prompt
    assert _GROUNDED[:80].strip().split()[0] in prompt  # grounded body, not catalyst[:280]


@pytest.mark.asyncio
async def test_v2_anchor_rule_enforced_on_output(monkeypatch):
    # Even if the model proposes a cohort of only prior-day names, it is dropped
    # mechanically — the anchor rule is code, not just prompt.
    today = date(2026, 7, 20)
    window = [
        _alert("WULF", date(2026, 7, 6), ep=96.0),
        _alert("CLSK", date(2026, 7, 14), ep=61.0),
        _alert("HUT", today, ep=75.0),
        _alert("IREN", today, ep=72.0),
    ]
    captured, mocks = _wire(
        monkeypatch, flag_on=True, window_alerts=window,
        llm_response='{"themes": ['
                     '{"name": "Stale prior-day pair", "catalyst_type": "theme", '
                     '"tickers": ["WULF", "CLSK"], "thesis": "no anchor"}, '
                     '{"name": "Miners to AI data centers", "catalyst_type": "theme", '
                     '"tickers": ["WULF", "CLSK", "HUT", "IREN"], "thesis": "anchored"}]}')
    out = await discover_narrative_themes(today)
    assert out["names"] == ["Miners to AI data centers"]
    persisted = mocks.persist.await_args.args[1]
    assert [t["name"] for t in persisted] == ["Miners to AI data centers"]
    assert persisted[0]["tickers"] == ["WULF", "CLSK", "HUT", "IREN"]
