"""/ideas unified trade-ideas front door.

Pins the renderer contract: "Stocks in Play" = GRADUATED entries ONLY (≥paper) — today just
MAGNA53 EP HIGH (+ any apollo_eligible substrate row). Shadow/in-development entries (coil/
flag, fishhook, anticipation) and the 9M universe are NOT in play — they're observed via the
drill-down buttons / /9m / /sugarbabies. The board is small / sometimes empty by design.
The interactive button→edit→back nav is a live-smoke, not unit-testable.
"""
from datetime import date

from agents.market_intelligence.ideas_board import render_ideas_summary

_TODAY = date(2026, 6, 16)


def _render(**kw):
    base = dict(today=_TODAY, magna53=None, sip_rows=None)
    base.update(kw)
    return render_ideas_summary(**base)


def test_empty_renders_zero_and_in_development():
    out = _render()
    assert "🎯 *Stocks in Play* — graduated · tradeable now (0)" in out
    assert "no graduated entry firing right now" in out
    assert "In development" in out and "anticipation" in out   # shadow entries surfaced here


def test_magna53_high_is_the_graduated_entry():
    out = _render(magna53=[{"ticker": "RXT", "score_tier": "HIGH", "ep_score": 70}])
    assert "🎯 *Stocks in Play* — graduated · tradeable now (1)" in out
    assert "🚨 `RXT` MAGNA53 EP HIGH" in out


def test_magna53_moderate_is_not_in_play():
    out = _render(magna53=[{"ticker": "MOD", "score_tier": "MODERATE", "ep_score": 55}])
    assert "`MOD`" not in out                                  # only HIGH is the graduated entry
    assert "graduated · tradeable now (0)" in out


def test_apollo_eligible_substrate_row_is_in_play_but_not_shadow_tiers():
    sip = [
        {"ticker": "AUTO", "automation_class": "apollo_eligible", "reason": "9M Day-2 ORB"},
        {"ticker": "ANTIC", "automation_class": "operator_only", "reason": "anticipation reclaim ready — x"},
        {"ticker": "SBC", "automation_class": "informational", "source_detector": "sugar_baby_cohort"},
    ]
    out = _render(sip_rows=sip)
    assert "🚨 `AUTO` 9M Day-2 ORB" in out                     # graduated apollo_eligible → in play
    assert "`ANTIC`" not in out                                # operator_only (shadow) NOT in play
    assert "`SBC`" not in out                                  # informational (universe) NOT in play
    assert "graduated · tradeable now (1)" in out


def test_in_development_section_lists_the_shadow_entries():
    out = _render()
    dev = out.split("In development")[1]
    assert "anticipation" in dev and "flag" in dev and "fishhook" in dev
    assert "9M = stock filter" in out                          # 9M framed as filter, not a play


def test_ideas_strategies_is_single_source_for_keyboard_and_taskmap():
    from channels.telegram import TelegramChannel
    strategies = TelegramChannel._IDEAS_STRATEGIES
    keys = [k for k, _l, _t in strategies]
    assert keys == ["magna53", "9m", "flags", "fishhook", "anticipation"]
    assert len(set(keys)) == len(keys)
    for _k, label, task in strategies:
        assert task.startswith("/")
        assert label
