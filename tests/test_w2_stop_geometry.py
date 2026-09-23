"""W2 study #2 (#276) — pin the day-1 stop-geometry resolver. The replay arms are only comparable
if resolve_entry_stop has the exact min/max semantics: atr_floor ONLY widens too-tight ORBs,
atr_cap ONLY tightens wide ones, day_low is structural, and degenerate stops fall back to orb_low
(never a non-positive risk). lower price = wider stop."""
import importlib
import sys

# tests/conftest.py installs a STUB backtester(.filters) (only 3 mocked names) for minimal dev
# envs; this study needs the REAL pure resolver. Drop the stubs, import the real module, then
# RESTORE the stubs so no other test (ep_detector imports the 3 stubbed names) is affected.
_saved = {k: sys.modules.pop(k, None) for k in (
    "agents.market_intelligence.backtester",
    "agents.market_intelligence.backtester.filters")}
try:
    resolve_entry_stop = importlib.import_module(
        "agents.market_intelligence.backtester.filters").resolve_entry_stop
finally:
    for _k, _v in _saved.items():
        if _v is not None:
            sys.modules[_k] = _v

ENTRY, ATR = 100.0, 4.0


def _r(orb_low, model, k=1.0, pdl=None, atr=ATR):
    return resolve_entry_stop(ENTRY, orb_low, atr, pdl, model, k)


def test_orb_low_is_baseline():
    assert _r(98.0, "orb_low") == 98.0


def test_atr_floor_widens_a_too_tight_orb():
    # orb_low 2pt below entry, k*ATR=4 → widen to entry-4=96 (the wider of the two)
    assert _r(98.0, "atr_floor", k=1.0) == 96.0


def test_atr_floor_keeps_an_already_wide_orb():
    # orb_low 6pt below entry (wider than k*ATR=4) → unchanged (only widens)
    assert _r(94.0, "atr_floor", k=1.0) == 94.0


def test_atr_cap_tightens_a_wide_orb():
    # orb_low 6pt below entry, cap at k*ATR=4 → tighten to entry-4=96
    assert _r(94.0, "atr_cap", k=1.0) == 96.0


def test_atr_cap_keeps_an_already_tight_orb():
    # orb_low 2pt below entry (tighter than k*ATR=4) → unchanged (only tightens)
    assert _r(98.0, "atr_cap", k=1.0) == 98.0


def test_day_low_uses_prior_day_low():
    assert _r(98.0, "day_low", pdl=92.0) == 92.0


def test_day_low_above_entry_falls_back_to_orb_low():
    # gap-down: prior low above entry would be a non-positive risk → fall back to orb_low
    assert _r(98.0, "day_low", pdl=105.0) == 98.0


def test_missing_atr_falls_back_to_orb_low():
    assert _r(98.0, "atr_floor", k=1.0, atr=None) == 98.0


def test_k_scales_the_floor_distance():
    assert _r(99.0, "atr_floor", k=0.5) == 98.0   # entry - 0.5*4 = 98
    assert _r(99.0, "atr_floor", k=1.5) == 94.0   # entry - 1.5*4 = 94
