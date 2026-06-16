"""/ideas unified trade-ideas front door (ADR 0004 consolidation).

Pins the renderer's contract: top-N NAMED tickers per strategy (the operator's
"top ideas", not a count dashboard), HIGH/stage ordering, the substrate-only
Stocks-in-Play block, and — the advisor's catch — that an underscore-bearing
source_detector NEVER leaks into the Markdown body (only caps-safe tickers do).
The interactive button→edit→back nav can't be unit-tested; that's a live-smoke gate.
"""
from datetime import date

from agents.market_intelligence.ideas_board import render_ideas_summary

_TODAY = date(2026, 6, 16)


def _render(**kw):
    base = dict(today=_TODAY, sip_rows=None, magna53=None, ninem_intraday=None,
                ninem_day2=None, flags=None, fishhook=None)
    base.update(kw)
    return render_ideas_summary(**base)


def test_empty_renders_placeholders_not_crash():
    out = _render()
    assert "Apollo Ideas" in out
    assert "🎯 *Stocks in Play* — 0 actionable" in out
    assert "substrate empty" in out                  # empty substrate placeholder
    assert "MAGNA53: _none today_" in out
    assert "Fishhook: _none active_" in out


def test_magna53_top3_high_first():
    alerts = [
        {"ticker": "MODA", "score_tier": "MODERATE", "ep_score": 60},
        {"ticker": "HIA",  "score_tier": "HIGH",     "ep_score": 71},
        {"ticker": "HIB",  "score_tier": "HIGH",     "ep_score": 80},
        {"ticker": "MODB", "score_tier": "MODERATE", "ep_score": 55},  # 4th → excluded
    ]
    out = _render(magna53=alerts)
    line = next(l for l in out.splitlines() if l.startswith("🎯 MAGNA53"))
    # HIGH first, ordered by ep_score desc within tier; capped at 3
    assert line.index("`HIB`") < line.index("`HIA`") < line.index("`MODA`")
    assert "`MODB`" not in line
    assert "(H)" in line and "(M)" in line


def test_flags_stage_priority_order():
    rows = [
        {"ticker": "TGT", "stage": "TIGHTENING", "base_age": 4},
        {"ticker": "TRG", "stage": "TRIGGERED",  "base_age": 6},
        {"ticker": "COI", "stage": "COILED",     "base_age": 9},
    ]
    line = next(l for l in _render(flags=rows).splitlines() if l.startswith("🚩 Flags"))
    assert line.index("`TRG`") < line.index("`COI`") < line.index("`TGT`")


def test_stocks_in_play_actionable_first_watchlist_collapsed_dedup():
    rows = [
        {"ticker": "AAA", "automation_class": "apollo_eligible", "source_detector": "magna53_ep_high"},
        {"ticker": "BBB", "automation_class": "operator_only",   "source_detector": "flag_coiled"},
        {"ticker": "BBB", "automation_class": "operator_only",   "source_detector": "fishhook_v3"},  # dup ticker
        {"ticker": "CCC", "automation_class": "informational",   "source_detector": "sugar_baby_cohort"},
    ]
    out = _render(sip_rows=rows)
    # 2 actionable (AAA apollo + BBB operator, deduped) · 1 watchlist (CCC informational)
    assert "🎯 *Stocks in Play* — 2 actionable · 1 watchlist" in out
    sip_block = out.split("Top ideas per strategy")[0]
    assert sip_block.count("`BBB`") == 1                  # multi-detector deduped
    assert "🚨 `AAA`" in out                              # apollo_eligible leads
    assert "ℹ️ watchlist:" in out and "`CCC`" in out      # informational collapsed to watchlist


def test_stocks_in_play_shows_stage_from_reason_head():
    # the operator's ask: tell the STAGE at a glance. The reason head is the stage;
    # the informational sugar-baby row is collapsed to watchlist, not mixed in.
    rows = [
        {"ticker": "RDY", "automation_class": "operator_only",
         "source_detector": "delayed_ep_reentry", "reason": "delayed-EP reclaim ready — awaiting 3b entry"},
        {"ticker": "SBC", "automation_class": "informational",
         "source_detector": "sugar_baby_cohort", "reason": "Pradeep persistent cohort — 5× 9M+ prints"},
    ]
    out = _render(sip_rows=rows)
    assert "👤 `RDY` delayed-EP reclaim ready" in out     # stage shown, em-dash tail dropped
    assert "ℹ️ watchlist: `SBC`" in out                   # cohort collapsed, not an actionable row
    assert "awaiting 3b entry" not in out                 # reason tail trimmed for the summary


def test_source_detector_with_underscores_never_leaks():
    # advisor catch: only caps-safe tickers are interpolated; the underscore-bearing
    # source_detector/reason would desync Telegram Markdown if surfaced.
    rows = [{"ticker": "ABCD", "automation_class": "operator_only",
             "source_detector": "delayed_ep_reentry", "reason": "delayed-EP reclaim ready"}]
    out = _render(sip_rows=rows)
    assert "delayed_ep_reentry" not in out
    assert "`ABCD`" in out


def test_ideas_strategies_is_single_source_for_keyboard_and_taskmap():
    # the keyboard buttons AND the callback task-map both derive from _IDEAS_STRATEGIES,
    # so they cannot drift. Assert its shape + that every drill-down target is a slash cmd.
    from channels.telegram import TelegramChannel
    strategies = TelegramChannel._IDEAS_STRATEGIES
    keys = [k for k, _l, _t in strategies]
    assert keys == ["magna53", "9m", "flags", "fishhook", "sip"]
    assert len(set(keys)) == len(keys)                       # unique callback keys
    for _k, label, task in strategies:
        assert task.startswith("/")                          # routes to an existing board
        assert label                                         # has a button label
