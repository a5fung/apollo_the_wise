"""#490 — the SUSTAIN rule (operator-signed 2026-08-02, N=3 consecutive bars).

A price level that holds across N consecutive minutes is a LEVEL; a level touched in one minute and
gone is a PRINT. Same reasoning as the existing Q3 print-corroboration guard, one level up.

**The load-bearing invariant here is FAIL-OPEN on an undecidable verdict.** Pre-market bars are
genuinely sparse — SCL had no 09:30 bar at all — and a rule that silently converted "no data" into
"reject" would become "reject everything pre-market", a far bigger change than the one signed. The
operator raised that case himself; these tests are what stop it happening by accident.

Evidence + the overfitting caveat he also raised:
`docs/analysis/490_change_proposal_sustain_rule_2026-08-02.md`.
"""
import pytest

from agents.market_intelligence import ep_detector as ep

PC = 100.0          # prev close — a close of 109.0 is exactly the 9% floor (MIN_GAP_PCT,
                    # 9.0% since 2026-08-19, was 10.0%)


def _series(*closes):
    """(HH:MM, close) oldest->newest, minute-spaced. Minutes are cosmetic; order is what matters."""
    return [(f"09:{30 + i:02d}", c) for i, c in enumerate(closes)]


# ── holds / does not hold ────────────────────────────────────────────────────────────────────

def test_holds_when_every_bar_in_the_window_is_above(monkeypatch):
    ok, d = ep._sustain_ok(_series(111.0, 112.0, 111.5), PC, 3)
    assert ok is True and d["gaps"] == [11.0, 12.0, 11.5]


def test_does_not_hold_when_one_bar_dips_under(monkeypatch):
    """The MYGN case the operator ruled a good avoid: over on one bar, straight back under."""
    ok, _ = ep._sustain_ok(_series(113.0, 108.0, 109.0), PC, 3)
    assert ok is False


def test_only_the_LAST_n_bars_count():
    """Backward-looking from the tick. An earlier spike must not rescue a level that has since
    failed — otherwise the rule measures history rather than the level it is admitting on."""
    ok, _ = ep._sustain_ok(_series(120.0, 121.0, 122.0, 105.0, 104.0, 103.0), PC, 3)
    assert ok is False


def test_exactly_at_the_floor_counts_as_holding():
    ok, _ = ep._sustain_ok(_series(109.0, 109.0, 109.0), PC, 3)
    assert ok is True


def test_a_hair_under_the_floor_does_not():
    ok, _ = ep._sustain_ok(_series(109.0, 108.99, 109.0), PC, 3)
    assert ok is False


# ── FAIL-OPEN: undecidable is NOT a rejection ────────────────────────────────────────────────

def test_no_bars_is_undecidable_not_a_rejection():
    ok, d = ep._sustain_ok(None, PC, 3)
    assert ok is None and d["reason"] == "no_bars"


def test_empty_series_is_undecidable():
    ok, d = ep._sustain_ok([], PC, 3)
    assert ok is None and d["reason"] == "no_bars"


@pytest.mark.parametrize("n_bars", [1, 2])
def test_too_few_bars_is_undecidable_the_premarket_case(n_bars):
    """THE case the operator flagged. Fewer real bars than the rule needs must NOT reject —
    pre-market genuinely has gaps, and rejecting on absence would silently kill pre-open detection.
    Note the bars present are all comfortably ABOVE the floor: even a 'good' name must not be
    rejected merely because the data to judge it does not exist."""
    ok, d = ep._sustain_ok(_series(*([115.0] * n_bars)), PC, 3)
    assert ok is None, "sparse bars must fail OPEN, never closed"
    assert d["reason"] == "too_few_bars" and d["need"] == 3 and d["have"] == n_bars


def test_disabled_when_bars_is_one_or_less():
    """N<=1 is today's behaviour — the rule must report itself off, not silently evaluate."""
    for n in (0, 1):
        ok, d = ep._sustain_ok(_series(105.0), PC, n)
        assert ok is None and d["reason"] == "disabled"


# ── wiring: the gate must actually be consulted, and be off by default ───────────────────────

def test_default_is_off_so_the_change_ships_inert():
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert '"ep_rt_sustain_enabled", "EP_RT_SUSTAIN_ENABLED", default=False' in src


def test_signed_value_is_three():
    assert ep.EP_RT_SUSTAIN_BARS == 3, "operator signed N=3 on 2026-08-02"


def test_gate_runs_BEFORE_the_catch_is_logged():
    """If it ran after, a rejected name would still be recorded as a catch and the rule would be
    cosmetic."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert src.index("_sustain_ok(_sustain_bars.get(tkr)") < src.index('"ep_rt_universe_catch"')


def test_rejects_and_undecidables_are_both_logged_by_name():
    """A rule whose rejects are invisible cannot be judged later — that is the exact
    instrumentation trap that made gate 1 unanswerable. And 'rule is on' must not look identical
    to 'rule never had data'."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert '"ep_rt_sustain_reject"' in src and '"ep_rt_sustain_undecidable"' in src


def test_bars_are_memoised_per_tick():
    """One bar request per ticker per tick, not one per check — this sits in the scan path."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert "if tkr not in _sustain_bars:" in src


# ── #490 leg 2: the overlay must record AGREEMENT, not only disagreement (2026-08-03) ────────

def test_the_overlay_logs_when_rt_AGREES_with_the_admit():
    """Verify-live leg 2 was UNANSWERABLE on 2026-08-03, which is worse than failing — it reads as
    a pass. FTK flipped DOWN at 07:25, alerted at 08:45 on a delayed 10.45%, flipped DOWN again at
    09:20. The overlay ran at 08:45 and did not remove it (consistent with a genuine recovery), but
    only DISAGREEMENT was ever logged, so the passing value did not exist anywhere."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    assert '"ep_rt_admit"' in src


def test_the_admit_event_is_a_THIRD_arm_not_a_rewrite():
    """The two existing branches are money-path control flow. The new telemetry must hang off the
    end of the same chain, leaving them byte-identical."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    up = src.index('"ep_rt_floor_flip_up"')
    down = src.index('"ep_rt_floor_flip_down"', up)
    admit = src.index('"ep_rt_admit"', down)
    assert up < down < admit, "ep_rt_admit must come after both existing branches"
    assert "elif rt_gap >= MIN_GAP_PCT and dl >= MIN_GAP_PCT" in src


def test_the_admit_event_is_deduped_per_ticker_per_day():
    """Unbounded it would fire for every admitted candidate on every 5-minute tick."""
    src = open("agents/market_intelligence/ep_detector.py").read()
    i = src.index('"ep_rt_admit"')
    assert "_audit_dedupe_check(" in src[max(0, i - 400):i + 400]
