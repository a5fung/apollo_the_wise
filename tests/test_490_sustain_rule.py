"""#490 — the SUSTAIN rule (operator-signed 2026-08-02, N=3 consecutive bars).

A price level that holds across N consecutive minutes is a LEVEL; a level touched in one minute and
gone is a PRINT. Same reasoning as the existing Q3 print-corroboration guard, one level up.

**The load-bearing invariant here is FAIL-OPEN on an undecidable verdict.** Pre-market bars are
genuinely sparse — SCL had no 09:30 bar at all — and a rule that silently converted "no data" into
"reject" would become "reject everything pre-market", a far bigger change than the one signed. The
operator raised that case himself; these tests are what stop it happening by accident.

Evidence + the overfitting caveat he also raised:
`docs/analysis/490_change_proposal_sustain_rule_2026-08-02.md`.

2026-09-13 (#653 cleanup): the 7 wiring pins below now call the REAL
`_apply_rt_universe_overlay` / `_apply_realtime_pass2` (both plain, standalone functions --
NOT closures inside run_ep_scan) against fake Alpaca fetches, reusing the existing end-to-end
harnesses in test_490_rt_universe.py and test_490_gap_down_authority.py, instead of grepping
ep_detector.py's source text. Every conversion is mutation-proven."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import collector, ep_detector as ep
from tests.test_490_gap_down_authority import _all_three
from tests.test_490_gap_down_authority import _cand as _cand_pass2
from tests.test_490_gap_down_authority import _run as _run_pass2
from tests.test_490_gap_down_authority import _SNAPS as _SNAPS_PASS2
from tests.test_490_gap_down_authority import _tickers as _tickers_pass2
from tests.test_490_gap_down_authority import _wire as _wire_pass2
from tests.test_490_rt_universe import _now as _rtu_now
from tests.test_490_rt_universe import _POLY_SNAP, _PREV
from tests.test_490_rt_universe import _sn as _rtu_sn

_ET = ZoneInfo("America/New_York")

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


def test_signed_value_is_three():
    assert ep.EP_RT_SUSTAIN_BARS == 3, "operator signed N=3 on 2026-08-02"


# ── wiring: the gate must actually be consulted, and be off by default ───────────────────────
#
# `_apply_rt_universe_overlay` is a plain, standalone async function (not a closure inside
# run_ep_scan) -- these tests call the REAL thing against a fake Alpaca snapshot + fake minute
# bars, reusing `_sn`/`_now`/`_POLY_SNAP`/`_PREV` from test_490_rt_universe.py.

def _wire(monkeypatch, snaps, *, sustain_on=None, sustain_bars=3, minute_closes=None):
    """`sustain_on=None` deliberately leaves the `ep_rt_sustain_enabled` toggle UNSET in this
    fake -- the real `get_runtime_toggle("ep_rt_sustain_enabled", ..., default=False)` call then
    falls through to whatever `default` the REAL CODE passed, which is exactly the claim
    test_default_is_off_so_the_change_ships_inert pins."""
    monkeypatch.setattr(ep, "EP_RT_UNIVERSE_ENABLED", True)
    monkeypatch.setattr(ep, "EP_RT_PASS2_ENABLED", True)
    monkeypatch.setattr(ep, "EP_RT_SUSTAIN_BARS", sustain_bars)

    async def _toggle(name, env, default=True):
        if name == "ep_rt_universe_authoritative":
            return True   # irrelevant here: authoritative only changes ADMISSION, never whether
                           # the sustain gate itself runs
        if name == "ep_rt_sustain_enabled" and sustain_on is not None:
            return sustain_on
        return default
    monkeypatch.setattr(ep, "get_runtime_toggle", _toggle)

    async def _snaps_fn(tickers, timeout_s=4.0, concurrency=1, stats=None):
        if stats is not None:
            stats.update({"batches_total": 1, "batches_failed": 0})
        return snaps
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", _snaps_fn)

    async def _holds(today):
        return set()
    monkeypatch.setattr(ep, "_corp_action_holds_today", _holds)
    monkeypatch.setattr(ep, "_audit_dedupe_check", lambda *a, **k: True)
    monkeypatch.setattr(ep, "_rt_fresh_seen", set())
    monkeypatch.setattr(ep, "_rt_fresh_seen_date", None)

    closes_calls = []

    async def _closes(tickers, now_et, lookback_min=15):
        closes_calls.append(list(tickers))
        return {t: minute_closes[t] for t in tickers if minute_closes and t in minute_closes}
    monkeypatch.setattr(collector, "get_alpaca_minute_closes", _closes)

    logged = []

    async def _log(event_type, summary, detail=""):
        logged.append(event_type)
    monkeypatch.setattr(ep, "log_audit_event", _log)
    return logged, closes_calls


def _overlay(cands, now, rt_universe):
    return asyncio.run(ep._apply_rt_universe_overlay(
        cands, rt_universe, _POLY_SNAP, {}, None, now, _PREV))


def test_default_is_off_so_the_change_ships_inert(monkeypatch):
    """MUTATION TARGET: flip the `default=False` argument of the
    `get_runtime_toggle("ep_rt_sustain_enabled", ...)` call in ep_detector.py to `default=True`
    -- a fresh deploy whose runtime-toggle table has not yet been seeded with this row would
    start evaluating the sustain gate instead of shipping inert."""
    now = _rtu_now()
    logged, closes_calls = _wire(monkeypatch, {"NVVE": _rtu_sn(now, 10.0)}, sustain_on=None)
    out, _ = _overlay([], now, [("NVVE", 10.0)])
    assert len(out) == 1, "the guard-passing crosser is still admitted -- sustain OFF is a no-op"
    assert closes_calls == [], "the minute-bars fetch must never happen when the toggle defaults off"


def test_gate_runs_BEFORE_the_catch_is_logged(monkeypatch):
    """If it ran after, a rejected name would still be recorded as a catch and the rule would be
    cosmetic.
    MUTATION TARGET: move the sustain-gate block to AFTER the ep_rt_universe_catch log call --
    a rejected level would then still emit a catch event."""
    now = _rtu_now()
    # 3 bars vs prev_close 10.0 (9% floor = 10.9): the middle bar dips well under -> does not hold.
    reject_bars = [("09:25", 10.95), ("09:26", 10.0), ("09:27", 10.95)]
    logged, _ = _wire(monkeypatch, {"NVVE": _rtu_sn(now, 10.0)}, sustain_on=True,
                       minute_closes={"NVVE": reject_bars})
    out, _ = _overlay([], now, [("NVVE", 10.0)])
    assert out == []
    assert "ep_rt_sustain_reject" in logged
    assert "ep_rt_universe_catch" not in logged, (
        "a rejected level must never also emit a catch -- proves the gate runs before, not after")


def test_rejects_and_undecidables_are_both_logged_by_name(monkeypatch):
    """A rule whose rejects are invisible cannot be judged later — that is the exact
    instrumentation trap that made gate 1 unanswerable. And 'rule is on' must not look identical
    to 'rule never had data'.
    MUTATION TARGET: rename the ep_rt_sustain_undecidable event to reuse the reject event's own
    name -- a genuinely sparse pre-market tick would then be indistinguishable in the audit log
    from a real rejection, exactly the trap this docstring describes."""
    now = _rtu_now()
    reject_bars = [("09:25", 10.95), ("09:26", 10.0), ("09:27", 10.95)]
    logged_reject, _ = _wire(monkeypatch, {"NVVE": _rtu_sn(now, 10.0)}, sustain_on=True,
                              minute_closes={"NVVE": reject_bars})
    _overlay([], now, [("NVVE", 10.0)])
    assert "ep_rt_sustain_reject" in logged_reject

    logged_undecidable, _ = _wire(monkeypatch, {"NVVE": _rtu_sn(now, 10.0)}, sustain_on=True,
                                   minute_closes={})   # no bars at all -> undecidable
    _overlay([], now, [("NVVE", 10.0)])
    assert "ep_rt_sustain_undecidable" in logged_undecidable
    assert "ep_rt_sustain_reject" not in logged_undecidable


def test_bars_are_memoised_per_tick(monkeypatch):
    """One bar request per ticker per tick, not one per check — this sits in the scan path.
    MUTATION TARGET: remove the `if tkr not in _sustain_bars:` memo guard -- a second reference
    to the same ticker within one tick would then re-fetch bars instead of reusing the memo."""
    now = _rtu_now()
    holding_bars = [("09:25", 10.95), ("09:26", 10.95), ("09:27", 10.95)]  # holds -> falls through
    logged, closes_calls = _wire(monkeypatch, {"NVVE": _rtu_sn(now, 10.0)}, sustain_on=True,
                                  minute_closes={"NVVE": holding_bars})
    # NVVE listed twice in one tick's rt_universe is the only way to observe the per-TICK memo
    # from outside the function -- `in_candidates` is computed once before the loop, so both
    # occurrences reach the sustain gate.
    _overlay([], now, [("NVVE", 10.0), ("NVVE", 10.0)])
    assert closes_calls == [["NVVE"]], (
        "a second reference to the same ticker in one tick must reuse the tick's own memo, "
        "not issue a second bars request")


# ── #490 leg 2: the overlay must record AGREEMENT, not only disagreement (2026-08-03) ────────
#
# `_apply_realtime_pass2` is a SEPARATE plain, standalone function from the overlay above --
# these reuse test_490_gap_down_authority.py's `_wire`/`_cand`/`_run`/`_all_three`/`_SNAPS`
# harness, which already drives it end to end with the two existing (flip-up/flip-down)
# branches under independent toggle control.

def test_the_overlay_logs_when_rt_AGREES_with_the_admit(monkeypatch):
    """Verify-live leg 2 was UNANSWERABLE on 2026-08-03, which is worse than failing — it reads as
    a pass. FTK flipped DOWN at 07:25, alerted at 08:45 on a delayed 10.45%, flipped DOWN again at
    09:20. The overlay ran at 08:45 and did not remove it (consistent with a genuine recovery), but
    only DISAGREEMENT was ever logged, so the passing value did not exist anywhere.
    MUTATION TARGET: delete the third `elif rt_gap >= MIN_GAP_PCT and dl >= MIN_GAP_PCT` branch
    -- the CLEAN case (both rt and delayed clear the floor, the FTK-recovery shape) would once
    again log nothing at all."""
    events = _wire_pass2(monkeypatch, full=False, down=False)
    out = _run_pass2([_cand_pass2("CLEAN", 12.0)], {"CLEAN": {"price": 112.0}})
    assert "CLEAN" in _tickers_pass2(out)
    assert "ep_rt_admit" in [e for e, *_ in events]


def test_the_admit_event_is_a_THIRD_arm_not_a_rewrite(monkeypatch):
    """The two existing branches are money-path control flow. The new telemetry must hang off the
    end of the same chain, leaving them byte-identical. `_all_three()` (STALE/FLIPUP/CLEAN) fires
    all three arms of the SAME if/elif chain in one call — proving them mutually exclusive rather
    than a rewrite of the first two.
    MUTATION TARGET: delete the third `elif ... ep_rt_admit` branch entirely -- CLEAN would then
    fall through the chain unrecorded while STALE/FLIPUP's existing events (unchanged, "byte-
    identical") keep firing exactly as before, which is exactly what this test would need to
    catch to be worth having."""
    events = _wire_pass2(monkeypatch, full=False, down=False)
    out = _run_pass2(_all_three(), _SNAPS_PASS2)
    types = [e for e, *_ in events]
    assert types.count("ep_rt_floor_flip_down") == 1   # STALE — untouched by the new arm
    assert types.count("ep_rt_floor_flip_up") == 1      # FLIPUP — untouched by the new arm
    assert types.count("ep_rt_admit") == 1              # CLEAN — the new third arm


def test_the_admit_event_is_deduped_per_ticker_per_day(monkeypatch):
    """Unbounded it would fire for every admitted candidate on every 5-minute tick.
    MUTATION TARGET: key `_audit_dedupe_check` on something tick-specific (e.g. the HH:MM) for
    this event instead of the plain 'ep_rt_admit' key -- it would then re-fire every tick instead
    of once per ticker per day."""
    events = _wire_pass2(monkeypatch, full=False, down=False, real_dedupe=True)
    snaps = {"CLEAN": {"price": 112.0}}
    # Two ticks HOURS apart on the SAME calendar day -- calls the real function directly (not
    # the fixed-_NOW _run_pass2 wrapper) so the dedupe key's DATE component is genuinely held
    # constant while the TIME component varies, proving the key is (ticker, date, event), not
    # (ticker, tick, event).
    t1 = datetime(2026, 7, 31, 9, 35, 0, tzinfo=_ET)
    t2 = datetime(2026, 7, 31, 14, 10, 0, tzinfo=_ET)
    asyncio.run(ep._apply_realtime_pass2([_cand_pass2("CLEAN", 12.0)], t1,
                                          prev_trade_date=_PREV, snaps=dict(snaps)))
    asyncio.run(ep._apply_realtime_pass2([_cand_pass2("CLEAN", 12.0)], t2,
                                          prev_trade_date=_PREV, snaps=dict(snaps)))
    types = [e for e, *_ in events]
    assert types.count("ep_rt_admit") == 1, "must fire once per ticker per day, not once per tick"
