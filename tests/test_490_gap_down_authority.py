"""#490 — the DOWN-ONLY gap authority split (2026-08-01).

`ep_rt_gap_authoritative` does two things at once: it ADMITS flip-ups (rt >= floor > delayed) and
REMOVES flip-downs (rt < floor <= delayed). The admit half adds ~+25 candidates/day to the LLM
grading path, which eats the margin the 09:45 ORB cutoff depends on; the remove half is a pure
quality gain that shrinks the cohort. `ep_rt_gap_down_authoritative` splits the remove half out so
it can run alone.

**The load-bearing invariant this file exists to pin: the down toggle can only ever REMOVE.**
If it can be made to admit a single candidate the split is unsafe, because "never loosen detection"
is the property that lets it ship without the latency budget the admit half needs.

Evidence for the split: docs/analysis/490_delay_missed_eps_2026-08-01.md §6.
"""
import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence import ep_detector

_ET = ZoneInfo("America/New_York")
_PREV = date(2026, 7, 30)
_NOW = datetime(2026, 7, 31, 9, 35, 0, tzinfo=_ET)
_PC = 100.0          # prev_close — keeps gap arithmetic readable: price 108 => +8%, 112 => +12%


def _wire(monkeypatch, *, full=False, down=False):
    """Wire Pass-2 with the two gap toggles set INDEPENDENTLY.

    The pre-existing helpers in test_490_prev_close_datekey.py return one value for every toggle
    name, which cannot express "full off, down on" — the exact combination under test here.
    """
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)

    async def _toggle(name, env, default=True):
        if name == "ep_rt_gap_authoritative":
            return full
        if name == "ep_rt_gap_down_authoritative":
            return down
        return default
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)
    monkeypatch.setattr(ep_detector, "_audit_dedupe_check", lambda *a, **k: True)
    monkeypatch.setattr(ep_detector, "_rt_fresh_seen", set())
    monkeypatch.setattr(ep_detector, "_rt_fresh_seen_date", None)
    events = []

    async def _log(event_type, summary, detail=""):
        events.append((event_type, summary, detail))
    monkeypatch.setattr(ep_detector, "log_audit_event", _log)
    return events


def _cand(ticker, delayed_gap):
    return {"ticker": ticker, "gap_pct": delayed_gap, "prev_close": _PC,
            "gap_pct_delayed": delayed_gap, "current_price": _PC * (1 + delayed_gap / 100),
            "price_source": "polygon_delayed"}


def _run(cands, snaps):
    return asyncio.run(ep_detector._apply_realtime_pass2(
        cands, _NOW, prev_trade_date=_PREV, snaps=snaps))


def _tickers(out):
    return {c["ticker"] for c in out}


# ── the three candidate classes, by (delayed, rt) vs the 10% floor ────────────────────────────
# STALE   delayed 12% / rt 8%   -> admitted today, the false-admit the split targets
# FLIPUP  delayed  8% / rt 12%  -> dropped today, the expansion the split must NOT enable
# CLEAN   delayed 12% / rt 12%  -> admitted today and legitimately so
_SNAPS = {"STALE": {"price": 108.0}, "FLIPUP": {"price": 112.0}, "CLEAN": {"price": 112.0}}


def _all_three():
    return [_cand("STALE", 12.0), _cand("FLIPUP", 8.0), _cand("CLEAN", 12.0)]


def test_down_toggle_removes_the_stale_false_admit(monkeypatch):
    _wire(monkeypatch, full=False, down=True)
    out = _run(_all_three(), _SNAPS)
    assert "STALE" not in _tickers(out)


def test_down_toggle_can_NEVER_admit_a_flip_up(monkeypatch):
    """The safety property. Down-only must leave the admit half exactly as it is today."""
    _wire(monkeypatch, full=False, down=True)
    out = _run(_all_three(), _SNAPS)
    assert "FLIPUP" not in _tickers(out)


def test_down_toggle_keeps_a_legitimate_candidate(monkeypatch):
    _wire(monkeypatch, full=False, down=True)
    out = _run(_all_three(), _SNAPS)
    assert "CLEAN" in _tickers(out)


def test_down_toggle_off_is_byte_identical_to_today(monkeypatch):
    """Deploy default: the stale admit survives, exactly as it does in production now."""
    _wire(monkeypatch, full=False, down=False)
    out = _run(_all_three(), _SNAPS)
    assert _tickers(out) == {"STALE", "CLEAN"}


def test_full_authority_still_removes_stale(monkeypatch):
    """With full gap authority the remove half behaves as before the split.

    ⚠ FLIPUP is absent here too, and that is CORRECT — not the split's doing. These snaps carry no
    Alpaca daily bars, so `prev_close` is UNVERIFIED (`a_ref is None`) and the §2.1 never-loosen
    guard sets `_rt_admit_block="no_bar_confirm"`, which `_floor` honours. An RT-only admit needs
    either a date-keyed prev_close match or Q3 bar corroboration. My first version of this test
    asserted FLIPUP would be admitted; the code was right and the expectation was wrong.
    `test_flip_up_still_admitted_when_prev_close_verified` covers the admit path properly.
    """
    _wire(monkeypatch, full=True, down=False)
    out = _run(_all_three(), _SNAPS)
    assert "STALE" not in _tickers(out)
    assert "CLEAN" in _tickers(out)


def _verified_snap(price, prev_close=_PC):
    """A snap whose date-keyed daily bar matches the known prev trading date, so
    `_alpaca_ref_close` verifies the Polygon denominator and the never-loosen guard stands down.

    Keys are the FLAT ones `_alpaca_ref_close` actually reads (`daily_bar_close`/`daily_bar_ts`,
    `prev_close`/`prev_daily_bar_ts`) — a nested `previous_daily_bar` dict is silently ignored and
    leaves prev_close unverified, which is how my first version of this helper failed.
    """
    return {"price": price,
            "daily_bar_close": prev_close,
            "daily_bar_ts": datetime(_PREV.year, _PREV.month, _PREV.day, 0, 0, tzinfo=_ET)}


def test_flip_up_still_admitted_when_prev_close_verified(monkeypatch):
    """The admit half, exercised on the path that can actually reach it — and the contrast that
    makes the split meaningful: same input, full authority admits, down-only does not."""
    snaps = {"FLIPUP": _verified_snap(112.0)}
    _wire(monkeypatch, full=True, down=False)
    assert "FLIPUP" in _tickers(_run([_cand("FLIPUP", 8.0)], snaps))

    _wire(monkeypatch, full=False, down=True)
    assert "FLIPUP" not in _tickers(_run([_cand("FLIPUP", 8.0)], snaps))


def test_down_toggle_removes_stale_on_the_verified_path_too(monkeypatch):
    """The cleanup must not depend on prev_close being unverified."""
    _wire(monkeypatch, full=False, down=True)
    out = _run([_cand("STALE", 12.0)], {"STALE": _verified_snap(108.0)})
    assert _tickers(out) == set()


def test_down_toggle_is_subsumed_not_additive(monkeypatch):
    """Both toggles on == full authority alone. The down branch must not fight the full branch."""
    _wire(monkeypatch, full=True, down=True)
    both = _tickers(_run(_all_three(), _SNAPS))
    _wire(monkeypatch, full=True, down=False)
    full_only = _tickers(_run(_all_three(), _SNAPS))
    assert both == full_only


def test_flip_down_event_distinguishes_acted_from_shadow(monkeypatch):
    """Without this the event reads identically in both modes and verify-live cannot tell whether
    the cleanup is actually running."""
    ev = _wire(monkeypatch, full=False, down=True)
    _run([_cand("STALE", 12.0)], _SNAPS)
    down_ev = [e for e in ev if e[0] == "ep_rt_floor_flip_down"]
    assert down_ev and '"acted": true' in down_ev[0][2] and "REMOVED" in down_ev[0][1]

    ev2 = _wire(monkeypatch, full=False, down=False)
    _run([_cand("STALE", 12.0)], _SNAPS)
    down_ev2 = [e for e in ev2 if e[0] == "ep_rt_floor_flip_down"]
    assert down_ev2 and '"acted": false' in down_ev2[0][2] and "SHADOW" in down_ev2[0][1]


def test_down_toggle_never_admits_across_the_gap_range(monkeypatch):
    """Sweep rather than spot-check: for every (delayed, rt) pair around the floor, the down
    toggle's admitted set must be a SUBSET of today's. Any pair that admits something new fails."""
    grid = [4.0, 8.0, 9.9, 10.0, 12.0, 25.0]
    checked = 0
    for dl in grid:
        for rt in grid:
            # Both snap flavours: unverified prev_close (guard armed) AND verified (guard down).
            # The unverified path alone would let the never-loosen guard mask an admit bug.
            for snap in ({"price": _PC * (1 + rt / 100)}, _verified_snap(_PC * (1 + rt / 100))):
                snaps = {"T": snap}
                _wire(monkeypatch, full=False, down=False)
                today = _tickers(_run([_cand("T", dl)], snaps))
                _wire(monkeypatch, full=False, down=True)
                with_down = _tickers(_run([_cand("T", dl)], snaps))
                assert with_down <= today, f"down toggle ADMITTED at delayed={dl} rt={rt}"
                checked += 1
    assert checked == len(grid) * len(grid) * 2
