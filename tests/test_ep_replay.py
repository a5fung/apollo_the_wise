"""Tests for scripts/ep_replay.py — the raw-bar replay harness.

WHY THIS FILE EXISTS: the harness is quotable evidence — its numbers will steer
entry/exit forks the operator rules on (#482 option b). A replay that silently
fabricates a fill, guesses an intra-bar ordering, or falls back to coarser bars is
WORSE than no replay (the #482 lesson: every positive number in the retracted read
was a daily-bar artifact). Each test below pins one honesty rule and names the
MUTATION it exists to catch. The agreement numbers against real mi_live_trades
fills are produced by `python scripts/ep_replay.py validate` (needs the prod
captures); these tests cover the pure mechanics that run everywhere.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from scripts.ep_replay import (
    RULESETS,
    RuleSetRequired,
    entry_walk,
    get_ruleset,
    rescore_alert,
    ruleset_as_of,
    walk_campaign,
)

import scripts.ep_replay as ep_replay_mod

_ET = ZoneInfo("America/New_York")
DAY = date(2026, 8, 3)  # a Monday inside the captured window, well before the horizon


@pytest.fixture(autouse=True)
def _real_orb_validation(monkeypatch):
    """tests/conftest.py stubs agents.market_intelligence.backtester.filters with
    MagicMocks (the real module drags heavy deps into the test env), so the harness's
    imported validate_orb_entry is a mock under pytest. Patch in a faithful copy of the
    real contract (backtester/filters.py::validate_orb_entry — zero-range reject,
    range > 1.5x ATR reject) so these tests exercise real admission behaviour. The
    LIVE function itself is covered by its own tests and by `ep_replay.py validate`
    against prod fills."""
    def _validate(orb_high, orb_low, atr_14):
        orb_range = orb_high - orb_low
        if orb_range <= 0:
            return False, "setup:zero_range"
        if atr_14 and atr_14 > 0 and orb_range > 1.5 * atr_14:
            return False, f"setup:stop_too_wide: {orb_range:.2f} > 1.5x ATR {atr_14:.2f}"
        return True, None
    monkeypatch.setattr(ep_replay_mod, "validate_orb_entry", _validate)


def _bar(hhmm: str, o, h, l, c):
    hh, mm = map(int, hhmm.split(":"))
    return {"m": datetime(DAY.year, DAY.month, DAY.day, hh, mm, tzinfo=_ET),
            "o": o, "h": h, "l": l, "c": c}


def _flat_window(o=9.5, h=9.6, l=9.4, c=9.5, start=time(9, 31), n=29):
    out = []
    t = datetime.combine(DAY, start, tzinfo=_ET)
    for _ in range(n):
        out.append({"m": t, "o": o, "h": h, "l": l, "c": c})
        t += timedelta(minutes=1)
    return out


def _daily(**by_date):
    """daily dict for ticker 'T': _daily(**{'2026-08-04': (o,h,l,c)})"""
    return {"T": {date.fromisoformat(k): {"o": v[0], "h": v[1], "l": v[2],
                                          "c": v[3], "v": 1e6}
                  for k, v in by_date.items()}}


def _walk(bars0, daily=None, rs=RULESETS["era_c"], **kw):
    minutes = {("T", DAY): bars0}
    return walk_campaign(ticker="T", alert_date=DAY, rs=rs, minutes=minutes,
                         daily=daily or {"T": {}}, orb_high=10.0, orb_low=9.0, **kw)


# ── rule-set discipline ──────────────────────────────────────────────────────────────

def test_refuses_unspecified_ruleset():
    """MUTATION TARGET: someone giving get_ruleset a default ('current') so a replay
    can run without stating its rules — era-mixing by accident, the cardinal sin."""
    with pytest.raises(RuleSetRequired):
        get_ruleset(None)
    with pytest.raises(RuleSetRequired):
        get_ruleset("")
    with pytest.raises(RuleSetRequired):
        get_ruleset("no_such_ruleset")


def test_stop_formula_per_ruleset():
    """MUTATION TARGET: stop-mode mixup — era A/B stop is the ORB low; era C is
    entry − 2R = 2*orb_low − orb_high (order_manager ~L498). Validated against all
    52 stored hard_stops by the validate phase; pinned here for free."""
    assert RULESETS["era_a"].stop_price(10.0, 9.0) == 9.0
    assert RULESETS["era_b"].stop_price(10.0, 9.0) == 9.0
    assert RULESETS["era_c"].stop_price(10.0, 9.0) == pytest.approx(8.0)
    assert RULESETS["current"].stop_mode == "entry_minus_2r"


def test_ruleset_as_of_composes_the_dated_switches():
    """MUTATION TARGET: an edited switch date silently rewriting history. 2026-07-01
    is era A shape; 2026-08-10 is era B with #548 on; 2026-08-25 is the full era C."""
    a = ruleset_as_of(date(2026, 7, 1))
    assert (a.stop_mode, a.intraday_partial_r, a.score_separation) == ("orb_low", None, False)
    b = ruleset_as_of(date(2026, 8, 10))
    assert (b.stop_mode, b.intraday_partial_r, b.breakeven_at_partial) == ("orb_low", 2.0, True)
    c = ruleset_as_of(date(2026, 8, 25))
    assert (c.stop_mode, c.score_separation, c.trail_prior_closes) == ("entry_minus_2r", True, True)


# ── entry reconstruction ─────────────────────────────────────────────────────────────

def test_entry_intrabar_cross_fills_at_orb_high():
    """MUTATION TARGET: filling at the bar's high/close instead of the stop price —
    a stop-buy triggered intra-bar fills AT orb_high."""
    bars = [_bar("09:31", 9.8, 10.05, 9.7, 10.0)]
    fill = entry_walk(bars, 10.0, time(9, 31), time(10, 0))
    assert fill["status"] == "filled" and fill["px"] == 10.0


def test_entry_open_above_limit_never_fills_at_untraded_price():
    """MUTATION TARGET: fabricating a fill above the limit cap. stop_limit_buy_price(10)
    = 10.05; a bar OPENING at 10.50 cannot fill — the order rests as a limit and fills
    at the LIMIT only when price trades back down to it."""
    bars = [_bar("09:31", 10.50, 10.60, 10.40, 10.55),
            _bar("09:32", 10.30, 10.35, 10.02, 10.10)]
    fill = entry_walk(bars, 10.0, time(9, 31), time(10, 0))
    assert fill["status"] == "filled" and fill["px"] == pytest.approx(10.05)
    # and with no trade back to the limit: NO entry, never a fill at the open
    no = entry_walk(bars[:1], 10.0, time(9, 31), time(10, 0))
    assert no["status"] == "no_entry"


def test_no_entry_claim_requires_full_window_coverage():
    """MUTATION TARGET: claiming no_entry off gappy minute data — a missing bar could
    hide the cross, so no-cross + gaps must ABSTAIN (the honest-coverage rule)."""
    full = _flat_window()                      # 29 bars = full 9:31->10:00 window
    assert entry_walk(full, 10.0, time(9, 31), time(10, 0))["status"] == "no_entry"
    gappy = full[:10] + full[12:]              # two minutes missing
    res = entry_walk(gappy, 10.0, time(9, 31), time(10, 0))
    assert res["status"] == "abstain" and "entry_window_gaps" in res["reason"]


def test_missing_day0_bars_abstain_never_daily_fallback():
    """MUTATION TARGET: the #482 sin — a campaign with no stored minute bars quietly
    replayed from daily bars. It must ABSTAIN and be counted."""
    res = _walk([])
    assert res["status"] == "abstain" and res["reason"] == "no_day0_minute_bars"
    assert res["entered"] is False and res["realized_r"] is None


# ── day-0 walk honesty ───────────────────────────────────────────────────────────────

def test_day0_stop_and_target_in_one_bar_abstains():
    """MUTATION TARGET: fabricating the intra-bar ORDER of a stop touch vs a target
    touch — unknowable at 1-minute grain, so the campaign is unscoreable."""
    bars = [_bar("09:31", 9.8, 10.05, 9.7, 10.0),   # entry at 10.0, era_c stop 8, target 12
            _bar("09:32", 10.0, 12.10, 7.90, 9.0)]  # both sides inside one bar
    res = _walk(bars)
    assert res["status"] == "abstain" and res["reason"] == "day0_stop_and_target_same_bar"


def test_day0_stop_out_is_exactly_minus_one_r():
    """MUTATION TARGET: R-denominator drift. With normalized sizing, a clean day-0
    stop-out at the era-C 2R stop is −1.0R by construction (denominator = entry−stop)."""
    bars = [_bar("09:31", 9.8, 10.05, 9.7, 10.0),
            _bar("09:32", 9.5, 9.6, 7.95, 8.2)]     # low pierces the 8.0 stop, close < stop is irrelevant post-entry
    res = _walk(bars)
    assert res["status"] == "settled" and res["final_reason"] == "stop_hit"
    assert res["realized_r"] == pytest.approx(-1.0)


def test_partial_books_at_target_then_breakeven_stops_remainder():
    """MUTATION TARGET: partial double-fire, wrong fill price, or the #548 breakeven
    never arming. Era C: entry 10, R-frame = entry−orb_low = 1, target 12; partial 1/3
    AT 12; stop moves to entry; a later dip to 9.9 stops the remaining 2/3 at 10.0.
    Realized R = (2R × 1/3 + 0R × 2/3) / (entry−stop=2) = +1/3."""
    bars = [_bar("09:31", 9.8, 10.05, 9.7, 10.0),
            _bar("09:32", 11.0, 12.10, 10.9, 11.9),   # target touch, no stop touch
            _bar("09:33", 10.5, 10.6, 9.90, 10.1)]    # dips below breakeven, not orig stop
    res = _walk(bars)
    assert res["status"] == "settled"
    assert res["partial_fired"] is True
    partials = [e for e in res["exits"] if e["reason"] == "partial_profit"]
    assert len(partials) == 1 and partials[0]["price"] == pytest.approx(12.0)
    assert res["exits"][-1]["price"] == pytest.approx(10.0)     # breakeven, not 8.0
    assert res["realized_r"] == pytest.approx(1 / 3, abs=1e-6)
    # era B (no broker breakeven same-day): stop stays at orb_low 9.0, so the 9.90 dip
    # does NOT stop the remainder — the campaign survives day 0 (FIGS-vs-ETON evidence)
    res_b = _walk(bars, rs=RULESETS["era_b"])
    assert res_b["partial_fired"] is True
    assert res_b["status"] == "open_at_horizon"    # no daily bars supplied -> stays open
    assert [e["reason"] for e in res_b["exits"]] == ["partial_profit"]


def test_forward_gap_through_fills_at_open_not_stop():
    """MUTATION TARGET: the SYRE-class phantom — a later-day open BELOW the resting
    stop must fill at the OPEN, never at the stop price the market never traded."""
    bars0 = _flat_window(o=10.2, h=10.3, l=10.1, c=10.2, n=29)
    bars0[0] = _bar("09:31", 9.8, 10.05, 9.7, 10.0)   # entry at 10.0, survives day 0
    daily = _daily(**{"2026-08-04": (7.0, 7.5, 6.9, 7.2)})  # gaps far below the 8.0 stop
    res = _walk(bars0, daily=daily)
    assert res["status"] == "settled" and res["final_reason"] == "stop_hit"
    assert res["gap_through"] is True
    assert res["exits"][-1]["price"] == pytest.approx(7.0)
    assert res["realized_r"] == pytest.approx((7.0 - 10.0) / 2.0)


def test_missing_forward_daily_bar_is_counted_abstained_session():
    """MUTATION TARGET: silently skipping a missing daily bar without counting it —
    abstain accounting is a first-class output."""
    bars0 = _flat_window(o=10.2, h=10.3, l=10.1, c=10.2, n=29)
    bars0[0] = _bar("09:31", 9.8, 10.05, 9.7, 10.0)
    # Tue 08-04 missing entirely; Wed 08-05 gaps through the stop
    daily = _daily(**{"2026-08-05": (7.0, 7.5, 6.9, 7.2)})
    res = _walk(bars0, daily=daily)
    assert res["status"] == "settled"
    assert res["sessions_abstained"] == 1


# ── re-score honesty ─────────────────────────────────────────────────────────────────

def test_float_band_straddling_the_bar_abstains_admission():
    """MUTATION TARGET: assuming a float value for the unstored floatShares fact.
    When score-without-float < bar <= score-with-float, admission must ABSTAIN."""
    alert = {"gap_pct": "12.0", "rel_volume": "1.0", "catalyst_quality": "strong",
             "vol_percentile": "80", "in_active_theme": "f",
             "confidence_multiplier": "1.0"}
    rs = RULESETS["current"]
    # hunt a straddle by scanning adv values — the band is 6.25 presented points wide,
    # so some input in this sweep must straddle the bar unless banding is broken
    found = None
    for adv in range(1, 60):
        r = rescore_alert(alert, rs, adv * 1e6, 10.0, "Bear", 70)
        assert r["score_hi"] >= r["score_lo"]
        if r["score_lo"] < r["bar"] <= r["score_hi"]:
            found = r
            break
    assert found is not None, "no straddle found — float banding is not being applied"
    assert found["admit"] == "abstain_float_band_straddles_bar"


def test_walk_campaign_states_its_ruleset_on_every_row():
    """MUTATION TARGET: dropping the rule-set stamp from output rows — every result
    must say which rules produced it."""
    res = _walk([])
    assert res["ruleset"] == "era_c"


# ── the validation bar (advisor review 2026-09-01) ───────────────────────────────────


def test_the_validation_baseline_is_recorded_and_dated():
    """WHY THIS EXISTS. This harness is built to be RE-RUN and CITED, and its authority rests
    entirely on reproducing what really happened. When it was built that was measured — and the
    numbers lived only in a card's return message and a PLAN note, where nothing would fail if
    the agreement quietly degraded. This repo's recent history is findings that were true when
    written and cited long after they stopped being true.

    MUTATION TARGET: deleting the baseline, or letting it go undated so nobody can tell how old
    the claim is."""
    from scripts.ep_replay import VALIDATION_BASELINE as B

    assert B["as_of"], "the baseline must carry the date it was measured"
    assert B["cohort"], "and what it was measured against"
    for key in ("stop_formula_exact", "entry_decision_exact", "exit_class_agree",
                "current_era_within_0p16"):
        hit, total = B[key]
        assert total > 0 and 0 <= hit <= total, f"{key} is not a real ratio: {B[key]}"


def test_a_degraded_rerun_FAILS_rather_than_being_quoted():
    """The whole point. A harness whose agreement has rotted must stop being authoritative on its
    own, not wait for someone to notice a number looks odd.

    MUTATION TARGET: loosening a floor to 0, or making validation_verdict return ok on missing
    measurements — both of which would make the bar decorative."""
    from scripts.ep_replay import validation_verdict

    good = {"stop_formula_rate": 1.0, "entry_decision_rate": 1.0, "exit_class_rate": 0.97,
            "realized_r_rate": 0.83, "abstain_rate": 0.17}
    assert validation_verdict(good)["ok"]

    for key, bad in (("exit_class_rate", 0.60), ("stop_formula_rate", 0.98),
                     ("entry_decision_rate", 0.80), ("realized_r_rate", 0.50)):
        v = validation_verdict({**good, key: bad})
        assert not v["ok"], f"a degraded {key} must fail the bar"
        assert any(key.split('_')[0] in f for f in v["failures"])

    assert not validation_verdict({**good, "abstain_rate": 0.45})["ok"], (
        "beyond the abstain ceiling the sample is not a sample")
    assert not validation_verdict({})["ok"], (
        "an unmeasured re-run must FAIL, not pass by silence — that is how a stale claim survives")


def test_the_floors_are_not_vacuous():
    """A bar set at zero is worse than no bar: it reads as validated and asserts nothing.
    MUTATION TARGET: zeroing a floor to make a failing re-run pass."""
    from scripts.ep_replay import VALIDATION_MIN

    assert VALIDATION_MIN["stop_formula_rate"] == 1.00, (
        "the stop is a formula, not an estimate — anything below exact is a defect")
    for key, floor in VALIDATION_MIN.items():
        if key == "max_abstain_rate":
            assert 0 < floor < 0.5, "an abstain ceiling above half makes the sample meaningless"
        else:
            assert floor >= 0.75, f"{key}'s floor {floor} is too loose to catch real degradation"
