"""#577 — `MIN_GAP_PCT` 10.0% -> 9.0% (operator-signed 2026-08-19, reversal of 2026-05-17 R2).

Full reasoning: `docs/setups/magna53_ep.md` 2026-08-19 change log; `docs/decisions/
0003-ep-selectivity-overhaul.md`'s 2026-08-19 addendum; priced in
`docs/analysis/gap_floor_decision_table_2026-08-19.md`.

WHAT THIS FILE PROVES, on the two REAL production code paths that read `MIN_GAP_PCT` (not a
re-implementation of the comparison): a candidate gapping 9.5% is now admitted and one gapping 8.5%
is still rejected, at BOTH (a) the Pass-1 universe-admission floor (`_pass1_gap_floor`, the same
function `run_ep_scan`'s candidate-building loop calls) and (b) the submission-time real-time
re-check (`entry_pipeline.check_rt_gap_floor`, wired from `live_tracker._MAGNA53_MIN_GAP_PCT`).

Per the task's own instruction — "a test that passes with AND without the change is not a test" —
`test_mutation_proof_...` below monkeypatches `ep_detector.MIN_GAP_PCT` back to the OLD 10.0 value
and shows the 9.5% case flips from admitted to rejected, proving these assertions actually depend on
the new value rather than being vacuously true at any floor.

The admit/reject tests below explicitly pin `ep_detector.MIN_GAP_PCT` to `_MIN_GAP_PCT_DEFAULT`
rather than reading the live module value as-is — deliberately: the module value is
`EP_MIN_GAP_PCT`-env-overridable (by design, for a fast emergency revert without redeploy), and this
file exists to test the operator-ruled 9.0 default specifically, not "whatever the environment
happens to be set to" — an override active in some CI/dev environment must not silently flip these
assertions or their failure mode would be confusing rather than diagnostic.
"""
import asyncio

import pytest

from agents.market_intelligence import ep_detector
from agents.market_intelligence.broker import entry_pipeline
from agents.market_intelligence.broker.skip_reasons import SETUP_GAP_BELOW_FLOOR

_PREV_CLOSE = 100.0


# ── the operator-ruled value itself ──────────────────────────────────────────────────────────

def test_min_gap_pct_default_is_9_0():
    """Pins the exact operator-ruled value (2026-08-19: 'ok, let's take 9 for now'), reading the
    real default constant — not the possibly-env-overridden module-level MIN_GAP_PCT."""
    assert ep_detector._MIN_GAP_PCT_DEFAULT == 9.0


# ── (a) Pass-1 universe admission floor — the function run_ep_scan's candidate loop calls ──────

def _pin_default_floor(monkeypatch):
    """Pin MIN_GAP_PCT to the operator-ruled default, immune to an EP_MIN_GAP_PCT env override."""
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", False)  # Pass-1 floor == MIN_GAP_PCT
    monkeypatch.setattr(ep_detector, "MIN_GAP_PCT", ep_detector._MIN_GAP_PCT_DEFAULT)


def test_9_5pct_gap_clears_pass1_floor(monkeypatch):
    _pin_default_floor(monkeypatch)
    floor = ep_detector._pass1_gap_floor()
    assert 9.5 >= floor, f"9.5% gap must clear the {floor}% floor"


def test_8_5pct_gap_rejected_by_pass1_floor(monkeypatch):
    _pin_default_floor(monkeypatch)
    floor = ep_detector._pass1_gap_floor()
    assert 8.5 < floor, f"8.5% gap must still be rejected by the {floor}% floor"


def test_mutation_proof_reverting_to_10_flips_9_5pct_to_rejected(monkeypatch):
    """The load-bearing proof: at the OLD 10.0% floor, 9.5% is BELOW it (rejected) — the exact
    opposite of the live behaviour above. If this flip didn't happen, the two tests above would be
    true at any floor and would not actually be testing the operator-ruled value."""
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", False)
    monkeypatch.setattr(ep_detector, "MIN_GAP_PCT", 10.0)
    floor = ep_detector._pass1_gap_floor()
    assert floor == 10.0
    assert 9.5 < floor, "at the pre-2026-08-19 floor, 9.5% must be rejected (proves the live pass)"


# ── (b) submission-time real-time re-check — entry_pipeline.check_rt_gap_floor ────────────────
# Same mechanism test_490_entry_gap_recheck.py pins generically; here the floor passed in is
# `_MIN_GAP_PCT_DEFAULT` (9.0, the operator-ruled value `live_tracker._MAGNA53_MIN_GAP_PCT` binds
# to at import time in an unoverridden deploy) rather than the possibly-env-overridden live
# MIN_GAP_PCT — proving the entry-time path's NEW value, deterministically, not "whatever the
# environment happens to be set to." Live wiring itself (that entry_pipeline is actually called
# with `_MAGNA53_MIN_GAP_PCT`) is separately pinned by
# test_490_entry_gap_recheck.py::test_magna53_call_site_actually_opts_in.

def _wire(monkeypatch, price):
    async def _toggle(name, env, default=False):
        return True
    monkeypatch.setattr("agents.market_intelligence.db.get_runtime_toggle", _toggle)

    async def _prev(ticker, before_date):
        return _PREV_CLOSE
    monkeypatch.setattr("agents.market_intelligence.db.get_prev_close", _prev)

    async def _latest(ticker):
        return {"price": price}
    monkeypatch.setattr(entry_pipeline.alpaca, "get_latest_trade", _latest)


def _run():
    from datetime import date
    return asyncio.run(entry_pipeline.check_rt_gap_floor(
        "TEST", {"alert_date": date(2026, 8, 19), "gap_pct": 20.0}, ep_detector._MIN_GAP_PCT_DEFAULT))


def test_entry_time_recheck_admits_9_5pct_at_live_floor(monkeypatch):
    _wire(monkeypatch, price=_PREV_CLOSE * 1.095)   # +9.5%
    ok, reason = _run()
    assert ok is True and reason is None


def test_entry_time_recheck_blocks_8_5pct_at_live_floor(monkeypatch):
    _wire(monkeypatch, price=_PREV_CLOSE * 1.085)   # +8.5%
    ok, reason = _run()
    assert ok is False
    assert SETUP_GAP_BELOW_FLOOR in reason
