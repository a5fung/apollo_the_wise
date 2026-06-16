"""/ideas unified trade-ideas front door.

Pins the renderer contract: "Stocks in Play" is ONE curated list of the BEST ACTIONABLE
ideas — consolidated across detectors, deduped per ticker (combined tags), priority-ranked.
The sugar-baby cohort is the UNIVERSE (operator 2026-06-16: "9M = universe, not entry"), so
it's a /sugarbabies pointer, NEVER the actionable list. Only caps-safe tickers + fixed tags
are emitted (no raw source_detector underscores). The interactive button→edit→back nav is a
live-smoke, not unit-testable.
"""
from datetime import date

from agents.market_intelligence.ideas_board import render_ideas_summary

_TODAY = date(2026, 6, 16)


def _render(**kw):
    base = dict(today=_TODAY, sip_rows=None, magna53=None, ninem_intraday=None,
                ninem_day2=None, flags=None, fishhook=None)
    base.update(kw)
    return render_ideas_summary(**base)


def test_empty_renders_zero_actionable():
    out = _render()
    assert "Apollo Ideas" in out
    assert "🎯 *Stocks in Play* — best actionable now (0)" in out
    assert "nothing actionable right now" in out
    assert "/sugarbabies" not in out          # no universe line when substrate empty


def test_consolidates_dedups_and_ranks_best_first():
    magna53 = [{"ticker": "RXT", "score_tier": "HIGH", "ep_score": 70}]
    ninem = [{"ticker": "RXT"}, {"ticker": "CRVO"}]      # RXT is ALSO a 9M
    flags = [{"ticker": "WSC", "stage": "COILED"}]
    fishhook = [{"ticker": "AUGO", "state": "promoted"}]
    out = _render(magna53=magna53, ninem_intraday=ninem, flags=flags, fishhook=fishhook)
    assert "🎯 *Stocks in Play* — best actionable now (4)" in out   # RXT deduped
    rxt_line = next(l for l in out.splitlines() if "`RXT`" in l)
    assert "MAGNA53 HIGH" in rxt_line and "9M" in rxt_line          # combined tags, one row
    assert out.count("`RXT`") == 1
    # tier ranking: RXT(0 HIGH) < CRVO(1 9M) < WSC(2 coiled) < AUGO(3 fishhook)
    assert out.index("`RXT`") < out.index("`CRVO`") < out.index("`WSC`") < out.index("`AUGO`")


def test_flag_tightening_is_not_actionable():
    flags = [{"ticker": "TGT", "stage": "TIGHTENING"}, {"ticker": "COI", "stage": "COILED"}]
    out = _render(flags=flags)
    assert "`COI`" in out                      # coiled = actionable
    assert "`TGT`" not in out                   # tightening = still forming, excluded
    assert "best actionable now (1)" in out


def test_sugar_baby_cohort_is_universe_not_in_play():
    sip = [{"ticker": "SBA", "automation_class": "informational", "source_detector": "sugar_baby_cohort"},
           {"ticker": "SBB", "automation_class": "informational", "source_detector": "sugar_baby_cohort"}]
    out = _render(sip_rows=sip)
    assert "best actionable now (0)" in out      # informational is NOT actionable
    assert "universe: 2 on the watchlist → /sugarbabies" in out
    assert "`SBA`" not in out                    # universe names are not listed as in-play


def test_substrate_actionable_tag_shown_without_source_leak():
    sip = [{"ticker": "RDY", "automation_class": "operator_only",
            "source_detector": "delayed_ep_reentry",
            "reason": "anticipation reclaim ready — awaiting entry"}]
    out = _render(sip_rows=sip)
    assert "`RDY` anticipation reclaim ready" in out   # reason-head tag, em-dash tail dropped
    assert "delayed_ep_reentry" not in out             # raw source_detector never leaks
    assert "awaiting entry" not in out                 # tail trimmed


def test_ideas_strategies_is_single_source_for_keyboard_and_taskmap():
    from channels.telegram import TelegramChannel
    strategies = TelegramChannel._IDEAS_STRATEGIES
    keys = [k for k, _l, _t in strategies]
    assert keys == ["magna53", "9m", "flags", "fishhook", "anticipation"]
    assert len(set(keys)) == len(keys)
    for _k, label, task in strategies:
        assert task.startswith("/")
        assert label
