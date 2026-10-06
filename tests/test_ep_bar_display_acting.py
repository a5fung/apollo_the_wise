"""Operator-facing surfaces must show the EP bar that ACTS, not the regime row's (2026-10-06).

THE DEFECT: the operator saw "regime Choppy, EP bar 75" while a live EP (CEG) traded at score 65.
Since #533 (2026-08-22) the bar that acts is `ep_rubric.resolve_ep_bar(separation_on, regime_bar)`:
SEPARATION_BAR (65) in EVERY regime while the `ep_score_separation` toggle is ON (default); the
per-regime bar (`mi_market_regime.ep_threshold` 65/70/75/80) acts only while it is OFF. Several
display surfaces printed the stored regime bar as "the EP bar" / "EP filter", and the regime
description said "raise EP bar".

DISPLAY ONLY: these tests pin what the surfaces SAY. Nothing here scores, gates or sizes.
Each surface is exercised with the toggle ON (shows 65, never the regime's 70/75) and OFF (the
revert path still shows the per-regime bar — the old text must stay truthful).
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db as mi_db
from agents.market_intelligence import ep_rubric
from agents.market_intelligence.ep_rubric import (
    SEPARATION_BAR, acting_bar_of, acting_ep_bar, annotate_acting_bar,
)
from agents.market_intelligence.brief_composer import (
    BriefData, _regime_material, _regime_state_line,
)
from agents.market_intelligence.briefing import (
    _ep_threshold_context, _format_morning_briefing, _format_regime_section,
)
from agents.market_intelligence.regime import _determine_regime, _regime_change_ep_text


def _toggle(monkeypatch, value):
    """Patch the ONE toggle read the display helper uses; return the mock for call inspection."""
    mock = AsyncMock(return_value=value)
    monkeypatch.setattr(mi_db, "get_runtime_toggle", mock)
    return mock


def _choppy(**over):
    # regime.py's stored Choppy bar is 70; Correcting's is 75 — neither may be shown while ON.
    row = {"regime": "Choppy", "vix": 17.0, "ep_threshold": 75,
           "description": "verdict\nNet score +1  (2 bullish · 1 bearish · 0 neutral)"}
    row.update(over)
    return row


# ── the helper itself ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("regime_bar", [65, 70, 75, 80])
def test_toggle_on_the_acting_bar_is_the_separation_bar_in_every_regime(monkeypatch, regime_bar):
    _toggle(monkeypatch, True)
    assert asyncio.run(acting_ep_bar(regime_bar)) == (SEPARATION_BAR, True)
    assert SEPARATION_BAR == 65


@pytest.mark.parametrize("regime_bar", [65, 70, 75, 80])
def test_toggle_off_the_acting_bar_is_the_regime_bar(monkeypatch, regime_bar):
    _toggle(monkeypatch, False)
    assert asyncio.run(acting_ep_bar(regime_bar)) == (regime_bar, False)


def test_reads_the_same_toggle_the_scanner_reads_with_the_same_default(monkeypatch):
    mock = _toggle(monkeypatch, True)
    asyncio.run(acting_ep_bar(70))
    mock.assert_awaited_once_with("ep_score_separation", "EP_SCORE_SEPARATION_ENABLED", default=True)


def test_a_toggle_read_error_fails_open_to_on_like_the_scanner(monkeypatch):
    monkeypatch.setattr(mi_db, "get_runtime_toggle", AsyncMock(side_effect=RuntimeError("db down")))
    assert asyncio.run(acting_ep_bar(75)) == (SEPARATION_BAR, True)


def test_annotate_stamps_a_copy_and_never_mutates_the_db_row(monkeypatch):
    _toggle(monkeypatch, True)
    row = _choppy()
    out = asyncio.run(annotate_acting_bar(row))
    assert out["acting_ep_bar"] == 65 and out["separation_on"] is True
    assert out["ep_threshold"] == 75                      # the stored row's field is untouched
    assert "acting_ep_bar" not in row and "separation_on" not in row


def test_a_bare_unannotated_row_renders_the_legacy_bar():
    assert acting_bar_of({"regime": "Choppy", "ep_threshold": 70}) == (70, False)
    assert acting_bar_of({}) == (70, False)


# ── briefing: the regime block + the morning line ────────────────────────────────────────────

def test_regime_section_shows_65_not_the_regime_bar_when_separation_is_on(monkeypatch):
    _toggle(monkeypatch, True)
    out = _format_regime_section(asyncio.run(annotate_acting_bar(_choppy())))
    assert "filter ≥65 — same bar in every regime" in out
    assert "75" not in out and "raise your bar" not in out


def test_regime_section_shows_the_regime_bar_when_separation_is_off(monkeypatch):
    _toggle(monkeypatch, False)
    out = _format_regime_section(asyncio.run(annotate_acting_bar(_choppy(ep_threshold=70))))
    assert "filter ≥70 — choppy, raise your bar" in out
    assert "same bar in every regime" not in out


def test_morning_briefing_line_follows_the_toggle(monkeypatch):
    on, off = [], []
    for value, sink in ((True, on), (False, off)):
        _toggle(monkeypatch, value)
        regime = asyncio.run(annotate_acting_bar(_choppy(ep_threshold=70)))
        sink.append(_format_morning_briefing(regime=regime, ep_alerts=[], briefing_date="2026-10-06"))
    assert "EP filter ≥65 — same bar in every regime" in on[0] and "≥70" not in on[0]
    assert "EP filter ≥70 — choppy, raise your bar" in off[0]


def test_ep_threshold_context_off_side_is_byte_identical_to_the_old_bands():
    assert _ep_threshold_context(80) == "≥80 — crisis, very selective"
    assert _ep_threshold_context(75) == "≥75 — correcting, exceptional only"
    assert _ep_threshold_context(70) == "≥70 — choppy, raise your bar"
    assert _ep_threshold_context(65) == "≥65 — standard (bull)"


# ── delta brief (brief_composer) ─────────────────────────────────────────────────────────────

THU = date(2026, 7, 23)


def _hist(labels, thresholds):
    return [
        {"regime_date": THU - timedelta(days=i), "regime": labels[i], "vix": 16.6,
         "ep_threshold": thresholds[i],
         "description": "x\nNet score +0 (3 bullish · 3 bearish)"}
        for i in range(len(labels))
    ]


def _data(regime_row, labels, thresholds):
    return BriefData(briefing_date=THU, regime=regime_row, regime_history=_hist(labels, thresholds),
                     size_mult=0.5)


def test_delta_brief_flip_says_the_bar_is_unchanged_when_separation_is_on(monkeypatch):
    _toggle(monkeypatch, True)
    row = asyncio.run(annotate_acting_bar(_choppy(ep_threshold=75)))
    lines, flipped = _regime_material(_data(row, ["Correcting", "Choppy"], [75, 70]))
    text = "\n".join(lines)
    assert flipped
    assert "EP bar ≥65 (same in every regime) · size ≈0.50×" in text
    assert "tightened" not in text and "EP filter" not in text


def test_delta_brief_flip_keeps_the_filter_move_when_separation_is_off(monkeypatch):
    _toggle(monkeypatch, False)
    row = asyncio.run(annotate_acting_bar(_choppy(ep_threshold=75)))
    lines, flipped = _regime_material(_data(row, ["Correcting", "Choppy"], [75, 70]))
    assert "EP filter 70 → 75 (tightened)" in "\n".join(lines)


def test_a_stored_threshold_change_alone_is_not_material_when_separation_is_on(monkeypatch):
    """Same label, the stored per-regime threshold moved: with separation ON the acting bar did
    not move, so this must not fire a 'REGIME — EP filter x → y' block."""
    _toggle(monkeypatch, True)
    row = asyncio.run(annotate_acting_bar(_choppy(ep_threshold=75)))
    lines, flipped = _regime_material(_data(row, ["Choppy", "Choppy"], [75, 70]))
    assert lines is None and not flipped
    _toggle(monkeypatch, False)
    row = asyncio.run(annotate_acting_bar(_choppy(ep_threshold=75)))
    lines, _ = _regime_material(_data(row, ["Choppy", "Choppy"], [75, 70]))
    assert lines is not None and "EP filter 70 → 75" in "\n".join(lines)


def test_delta_brief_state_line_follows_the_toggle(monkeypatch):
    _toggle(monkeypatch, True)
    on = _regime_state_line(_data(asyncio.run(annotate_acting_bar(_choppy())), ["Choppy"] * 3, [75] * 3))
    _toggle(monkeypatch, False)
    off = _regime_state_line(_data(asyncio.run(annotate_acting_bar(_choppy())), ["Choppy"] * 3, [75] * 3))
    assert "EP bar ≥65" in on and "filter" not in on and "75" not in on
    assert "filter ≥75" in off and "EP bar" not in off


# ── regime engine: description + change message ──────────────────────────────────────────────

_CHOPPY_INPUTS = dict(spy_vs_50ma=0.5, spy_vs_200ma=2.0, qqq_vs_50ma=1.0, vix=22.0, breadth_pct=50.0,
                      pct4_ratio_5d=1.1, pct4_ratio_10d=1.1)


def _choppy_verdict(**kw):
    regime, description, bar = _determine_regime(**_CHOPPY_INPUTS, **kw)
    assert regime == "Choppy" and bar == 70      # the stored legacy-side bar is untouched either way
    return description.splitlines()[0]


def test_choppy_verdict_does_not_claim_the_bar_rises_when_separation_is_on():
    on = _choppy_verdict(separation_on=True)
    assert "EP bar" not in on and "size down" in on


def test_choppy_verdict_keeps_the_legacy_wording_when_separation_is_off_or_unspecified():
    assert _choppy_verdict(separation_on=False) == "Market choppy — raise EP bar, size down."
    assert _choppy_verdict() == "Market choppy — raise EP bar, size down."


def test_regime_change_message_says_what_actually_changes_with_separation_on():
    audit, tg = _regime_change_ep_text("Bull", "Choppy", 65, 70, separation_on=True,
                                       bar=65, prev_mult=1.0, mult=0.75)
    assert "EP bar 65" in tg and "same in every regime" in tg
    assert "size 1.00× → 0.75×" in tg and "lose the ×1.2 Bull boost" in tg
    assert "EP threshold" not in tg and "70" not in tg
    assert "EP threshold" not in audit and "size 1.00× → 0.75×" in audit
    _, tg_in = _regime_change_ep_text("Choppy", "Bull", 70, 65, separation_on=True,
                                      bar=65, prev_mult=0.75, mult=1.0)
    assert "EP scores ×1.2 in Bull" in tg_in
    _, tg_mid = _regime_change_ep_text("Choppy", "Correcting", 70, 75, separation_on=True,
                                       bar=65, prev_mult=0.75, mult=0.5)
    assert "Bull" not in tg_mid and "size 0.75× → 0.50×" in tg_mid


def test_regime_change_message_with_unknown_multipliers_still_states_the_bar():
    _, tg = _regime_change_ep_text("Choppy", "Correcting", 70, 75, separation_on=True,
                                   bar=65, prev_mult=None, mult=None)
    assert tg == "EP bar 65 — same in every regime (unchanged)"


def test_regime_change_message_keeps_the_per_regime_text_when_separation_is_off():
    audit, tg = _regime_change_ep_text("Choppy", "Correcting", 70, 75, separation_on=False,
                                       bar=75, prev_mult=0.75, mult=0.5)
    assert tg == "EP threshold 70 → 75"
    assert audit == "EP threshold 70 -> 75"


# ── agent.py surfaces ────────────────────────────────────────────────────────────────────────

def test_why_rs_lines_name_the_acting_bar_not_a_per_regime_one():
    from agents.market_intelligence.agent import _rs_vs_bar_lines
    on = "\n".join(_rs_vs_bar_lines(60.0, 65, "Choppy", True))
    assert "(EP bar: 65+)" in on and "below the 65 EP bar" in on and "for Choppy regime" not in on
    off = "\n".join(_rs_vs_bar_lines(60.0, 75, "Correcting", False))
    assert "(EP bar: 75+)" in off and "below the 75 threshold for Correcting regime" in off


def _hud_patches(monkeypatch, regime):
    import agents.market_intelligence.agent as agent_mod
    monkeypatch.setattr(agent_mod, "get_latest_regime", AsyncMock(return_value=regime))
    monkeypatch.setattr(agent_mod, "get_today_ep_alerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(agent_mod, "get_correlation_clusters", AsyncMock(return_value=[]))
    monkeypatch.setattr(mi_db, "get_active_themes", AsyncMock(return_value=[]))
    monkeypatch.setattr(mi_db, "get_today_9m_ep_alerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(mi_db, "get_all_9m_sugar_babies", AsyncMock(return_value=[]))
    # another test file can leave a stub `_scheduler` behind — never depend on the real one
    from agents.market_intelligence import scheduler as _sched
    monkeypatch.setattr(_sched, "get_scheduler_status", lambda: {"scheduler_running": True})
    return agent_mod


def test_hud_regime_line_shows_the_acting_bar(monkeypatch):
    agent_mod = _hud_patches(monkeypatch, {"regime": "Choppy", "ep_threshold": 75, "qqq_ema_bullish": True})
    _toggle(monkeypatch, True)
    assert "EP bar: 65" in asyncio.run(agent_mod._build_hud_text())
    _toggle(monkeypatch, False)
    off = asyncio.run(agent_mod._build_hud_text())
    assert "EP bar: 75" in off


def test_ep_query_with_no_alerts_shows_the_acting_bar(monkeypatch):
    import agents.market_intelligence.agent as agent_mod
    from shared.models import AgentRequest
    monkeypatch.setattr(agent_mod, "get_today_ep_alerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(agent_mod, "get_current_regime",
                        AsyncMock(return_value={"regime": "Choppy", "ep_threshold": 75}))
    monkeypatch.setattr(mi_db, "latest_market_data_date", AsyncMock(return_value=None))
    req = AgentRequest(task="/ep", user_id=1, conversation_id="t")
    agent = agent_mod.MarketIntelligenceAgent()
    _toggle(monkeypatch, True)
    on = asyncio.run(agent._handle_ep_query(req)).result
    assert "(EP bar: 65+)" in on and "75" not in on
    _toggle(monkeypatch, False)
    assert "(EP bar: 75+)" in asyncio.run(agent._handle_ep_query(req)).result


# ── postmortem (historical: the bar that acted on that tick, from the scan log) ───────────────

def test_postmortem_fallback_prefers_the_recorded_acting_bar():
    from agents.market_intelligence.postmortem import _fallback_narrative
    base = {"ticker": "CEG", "alert_date": "2026-10-05", "trade": {}, "alert": {}, "outcome": {}, "themes": []}
    new = _fallback_narrative({**base, "regime": {"regime": "Choppy", "ep_bar": 65.0, "qqq_ema_bullish": True}})
    assert "EP bar 65," in new
    old = _fallback_narrative({**base, "regime": {"regime": "Choppy", "ep_threshold": 75, "qqq_ema_bullish": True}})
    assert "EP bar 75," in old   # pre-scan-log-bar rows keep the regime row's bar (it acted then)


def _postmortem_pool(scan_bar_row):
    """conn.fetchrow routed by SQL text: trade / regime / scan-log bar (everything else None)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    trade = {"alert_date": date(2026, 10, 5), "status": "closed", "entry_price": 100.0}
    regime = {"regime": "Choppy", "ep_threshold": 75, "qqq_ema_bullish": True, "spy_vs_50ma": 1.0,
              "breadth_pct_above_40ma": 50.0, "vix": 17.0, "description": "x"}

    async def _fetchrow(sql, *args):
        if "FROM mi_live_trades" in sql:
            return trade
        if "FROM mi_market_regime" in sql:
            return regime
        if "FROM mi_ep_scan_log" in sql:
            return scan_bar_row
        return None
    conn.fetchrow = _fetchrow
    conn.fetch = AsyncMock(return_value=[])
    return pool


def test_postmortem_context_replaces_the_regime_bar_with_the_bar_that_acted(monkeypatch):
    from agents.market_intelligence import postmortem
    monkeypatch.setattr(postmortem, "get_pool",
                        AsyncMock(return_value=_postmortem_pool({"ep_bar": 65.0})))
    ctx = asyncio.run(postmortem.build_postmortem_context("CEG", date(2026, 10, 5)))
    assert ctx["regime"]["ep_bar"] == 65.0
    assert "ep_threshold" not in ctx["regime"]      # the LLM must not read 75 as the deciding bar


def test_postmortem_context_keeps_the_regime_bar_when_the_scan_log_has_none(monkeypatch):
    from agents.market_intelligence import postmortem
    monkeypatch.setattr(postmortem, "get_pool", AsyncMock(return_value=_postmortem_pool(None)))
    ctx = asyncio.run(postmortem.build_postmortem_context("CEG", date(2026, 10, 5)))
    assert ctx["regime"]["ep_threshold"] == 75 and "ep_bar" not in ctx["regime"]


# ── wiring: every async entry point that renders the regime bar annotates the row first ───────

def test_every_async_regime_renderer_annotates_the_acting_bar():
    """The sync formatters read the stamped keys; an entry point that forgets to annotate silently
    renders the legacy bar again. The population is DERIVED (async callers of the three formatters
    in briefing.py / agent.py), then named so a missing member fails loudly."""
    import ast
    root = pathlib.Path(__file__).resolve().parent.parent / "agents" / "market_intelligence"
    renderers = {"_format_regime_section", "_format_morning_briefing", "_format_evening_briefing"}
    found: dict[str, bool] = {}
    for fname in ("briefing.py", "agent.py"):
        # source-pin-ok: send_morning/evening_briefing need a ~12-table DB gather to stand up, so
        # the annotate call is only checkable structurally; the formatters' behaviour is tested above
        tree = ast.parse((root / fname).read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            calls = {n.func.id for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            if calls & renderers:
                found[fn.name] = "annotate_acting_bar" in calls
    assert set(found) == {"send_evening_briefing", "send_morning_briefing", "_handle_regime_query"}, found
    assert all(found.values()), [k for k, v in found.items() if not v]
