"""#490 §6.1 — NOT-YET-AVAILABLE is not a measured zero (root-caused 2026-08-27).

The EP scan's 09:30 tick fires 5-25 s after the bell. No minute bar timestamped >= 09:30 has
been published yet (the 09:30 bar only closes at 09:31:00), so the real-time read's SESSION
bucket sums zero bars to 0 while its PM bucket, from the same successful call, is full and
correct. Under `ep_rt_volume_authoritative` that 0 would reach the RVOL@T gate as a 0.00x
session pace and reject the name on an artefact.

Evidence the mechanism is exactly this and not a failed call / a feed gap / an off-by-one:
155/155 recorded rt=0.00x shadow rows sit at the 09:30 tick with session_vol == 0 and a large
pm_vol; 0/523 rows at any other tick (07:00->09:55, including 09:31) have a zero acting bucket;
0/678 have both buckets zero. A failed batch returns {} and the symbol is simply absent.

These tests pin the distinction that fixes it: bars-present-but-zero-volume is a REAL
measurement and keeps acting; zero-bars is no data and falls back to the delayed read.
"""
import ast
import asyncio
import inspect
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import patch
from zoneinfo import ZoneInfo

from agents.market_intelligence import collector
from agents.market_intelligence import ep_detector as ep

_ET = ZoneInfo("America/New_York")
_T0930 = datetime(2026, 8, 27, 9, 30, 6, tzinfo=_ET)   # the observed artefact tick
_T0935 = datetime(2026, 8, 27, 9, 35, 6, tzinfo=_ET)
_T0700 = datetime(2026, 8, 27, 7, 0, 3, tzinfo=_ET)    # pre-open -> pm anchor


def _env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)


def _bars_client(payload):
    class _C:
        def __init__(self, api_key=None, secret_key=None):
            pass

        def get_stock_bars(self, req):
            return NS(data=payload)
    return _C


def _bar(hh, mm, vol):
    return NS(timestamp=_T0930.replace(hour=hh, minute=mm, second=0), volume=vol)


# ── collector: the counts that carry the distinction ───────────────────────────────

def test_collector_reports_bar_counts_per_bucket(monkeypatch):
    _env(monkeypatch)
    payload = {"AAA": [_bar(9, 15, 1_000), _bar(9, 31, 2_000), _bar(9, 35, 3_000)]}
    with patch("alpaca.data.historical.StockHistoricalDataClient", _bars_client(payload)):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["AAA"], _T0935))
    assert out == {"AAA": {"pm_vol": 1_000, "session_vol": 5_000,
                           "pm_bars": 1, "session_bars": 2}}


def test_collector_0930_shape_pm_full_session_has_no_bars(monkeypatch):
    """The observed prod shape: premarket measured, session not yet published."""
    _env(monkeypatch)
    payload = {"OKTA": [_bar(8, 0, 400_000), _bar(9, 29, 239_396)]}
    with patch("alpaca.data.historical.StockHistoricalDataClient", _bars_client(payload)):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["OKTA"], _T0930))
    assert out["OKTA"]["pm_vol"] == 639_396 and out["OKTA"]["pm_bars"] == 2
    assert out["OKTA"]["session_vol"] == 0 and out["OKTA"]["session_bars"] == 0


def test_collector_empty_bar_list_is_kept_with_zero_counts(monkeypatch):
    """Present-but-empty stays in the map (0 counts) — an ABSENT key means Alpaca returned
    nothing for the symbol. Both route to the delayed read; only the counts tell them apart."""
    _env(monkeypatch)
    with patch("alpaca.data.historical.StockHistoricalDataClient", _bars_client({"AAA": []})):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["AAA"], _T0935))
    assert out == {"AAA": {"pm_vol": 0, "session_vol": 0, "pm_bars": 0, "session_bars": 0}}


def test_collector_bars_present_but_all_zero_volume_is_a_measurement(monkeypatch):
    """THE load-bearing case: real bars whose volume is genuinely 0. Counts stay > 0, so this
    is NOT no-data — it must keep acting. Distinguishes the fix from `if vol == 0: fall back`."""
    _env(monkeypatch)
    payload = {"AAA": [_bar(9, 31, 0), _bar(9, 32, 0)]}
    with patch("alpaca.data.historical.StockHistoricalDataClient", _bars_client(payload)):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["AAA"], _T0935))
    assert out == {"AAA": {"pm_vol": 0, "session_vol": 0, "pm_bars": 0, "session_bars": 2}}


def test_collector_partial_batch_omits_only_the_missing_symbol(monkeypatch):
    """Degradation is per-symbol, never batch-wide: A measured, B absent, same call."""
    _env(monkeypatch)
    payload = {"AAA": [_bar(9, 31, 5_000)]}          # "BBB" requested, not returned
    with patch("alpaca.data.historical.StockHistoricalDataClient", _bars_client(payload)):
        out = asyncio.run(collector.get_alpaca_minute_cum_volumes(["AAA", "BBB"], _T0935))
    assert set(out) == {"AAA"}
    assert out["AAA"]["session_bars"] == 1 and "BBB" not in out


# ── caller: no-data vs measured-zero ───────────────────────────────────────────────

def test_anchor_measured_rejects_zero_bars_accepts_zero_volume():
    zero_bars = {"pm_vol": 639_396, "session_vol": 0, "pm_bars": 2, "session_bars": 0}
    zero_vol = {"pm_vol": 0, "session_vol": 0, "pm_bars": 0, "session_bars": 2}
    # session anchor (>= 09:30): zero BARS is no data; zero VOLUME with bars is a measurement
    assert ep._rt_anchor_measured(zero_bars, _T0930) is False
    assert ep._rt_anchor_measured(zero_vol, _T0930) is True
    # pm anchor (< 09:30) reads the other bucket — same rule, other key
    assert ep._rt_anchor_measured(zero_bars, _T0700) is True
    assert ep._rt_anchor_measured(zero_vol, _T0700) is False


def test_anchor_measured_fails_closed_to_the_delayed_read():
    assert ep._rt_anchor_measured(None, _T0935) is False          # symbol absent (partial map)
    assert ep._rt_anchor_measured({}, _T0935) is False            # empty entry
    assert ep._rt_anchor_measured({"pm_vol": 1, "session_vol": 1}, _T0935) is False  # old shape
    assert ep._rt_anchor_measured({"session_bars": None}, _T0935) is False
    assert ep._rt_anchor_measured({"session_bars": "x"}, _T0935) is False


def _cand():
    return {"today_volume": 458_710, "adv": 1_000_000, "rel_volume": 0.46,
            "projected_vol_multiple": 3.0}


def test_apply_rt_volume_declines_on_the_0930_shape_and_touches_nothing():
    """The whole §6.2 cascade stays off — not just the two anchor variables."""
    c = _cand()
    before = dict(c)
    out = ep._apply_rt_volume(
        c, {"pm_vol": 639_396, "session_vol": 0, "pm_bars": 2, "session_bars": 0},
        _T0930, 0)
    assert out is None
    assert c == before                      # today_volume / rel_volume / projection untouched
    assert "vol_delayed" not in c and "volume_source" not in c


def test_apply_rt_volume_declines_on_absent_symbol_and_on_empty_bars():
    for rt in (None,
               {"pm_vol": 0, "session_vol": 0, "pm_bars": 0, "session_bars": 0}):
        c = _cand()
        before = dict(c)
        assert ep._apply_rt_volume(c, rt, _T0935, 20) is None
        assert c == before


def test_apply_rt_volume_acts_when_bars_exist_even_at_zero_volume():
    """Bars present, volume genuinely 0 -> RT ACTS. The substitution must happen, and the
    derived figures must follow it down to 0 rather than keeping the stale delayed number."""
    c = _cand()
    out = ep._apply_rt_volume(
        c, {"pm_vol": 0, "session_vol": 0, "pm_bars": 0, "session_bars": 3}, _T0935, 20)
    assert out == (0, 0)
    assert c["vol_delayed"] == 458_710 and c["today_volume"] == 0
    assert c["volume_source"] == "alpaca_sip_minute" and c["rel_volume"] == 0.0
    assert c["projected_vol_multiple"] == 3.0   # untouched: guarded on today_volume > 0


def test_apply_rt_volume_full_cascade_when_measured():
    c = _cand()
    out = ep._apply_rt_volume(
        c, {"pm_vol": 24_412, "session_vol": 278_578, "pm_bars": 40, "session_bars": 5},
        _T0935, 20)
    assert out == (24_412, 278_578)
    assert c["vol_delayed"] == 458_710
    assert c["today_volume"] == 302_990
    assert c["volume_source"] == "alpaca_sip_minute"
    assert c["rel_volume"] == 0.3
    assert c["projected_vol_multiple"] == round(0.3 * (390 / 20), 1)


def test_partial_map_degrades_per_symbol_not_batch_wide():
    """One batch, one tick: A measured -> RT acts; B absent -> delayed, untouched."""
    rt_map = {"AAA": {"pm_vol": 1_000, "session_vol": 50_000,
                      "pm_bars": 3, "session_bars": 5}}
    a, b = _cand(), _cand()
    assert ep._apply_rt_volume(a, rt_map.get("AAA"), _T0935, 20) == (1_000, 50_000)
    assert a["today_volume"] == 51_000
    b_before = dict(b)
    assert ep._apply_rt_volume(b, rt_map.get("BBB"), _T0935, 20) is None
    assert b == b_before


# ── freezes: the toggle stays the only switch, and the flip list stays the operator's ──

def _ep_tree():
    return ast.parse(inspect.getsource(inspect.getmodule(ep)))


def test_toggle_off_makes_the_rt_substitution_unreachable():
    """Byte-identical with `ep_rt_volume_authoritative` OFF: the ONE call to `_apply_rt_volume`
    is nested inside `if _rt_vol_authoritative:`, so with the toggle off the rt map is never
    consulted for the gate inputs no matter what it holds."""
    tree = _ep_tree()
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) \
                and node.test.id == "_rt_vol_authoritative":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "_apply_rt_volume":
                    guarded.add(sub.lineno)
    all_calls = {n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_apply_rt_volume"}
    assert all_calls, "the authoritative substitution call vanished"
    assert all_calls == guarded, f"ungated _apply_rt_volume call(s) at {sorted(all_calls - guarded)}"


def test_shadow_flip_list_is_not_self_classified():
    """CHANGE_PROCESS rule 3 — the recorded flip list is the operator's to reclassify. The
    no-data fallback is ADDITIVE: the event type and `would_rvol_gate_flip` still key off the
    untouched `_would_flip`; the corrected reading rides alongside in its own fields."""
    src = inspect.getsource(inspect.getmodule(ep))
    assert '_vol_ev = "ep_rt_rvol_gate_flip" if _would_flip else "ep_rt_volume_shadow"' in src
    assert '"would_rvol_gate_flip": _would_flip,' in src
    assert '"would_rvol_gate_flip_measured": _would_flip_measured,' in src
    assert '"measured" if _rt_measured else "no_bars_for_anchor"' in src
    assert "_would_flip_measured = _would_flip and _rt_measured" in src
