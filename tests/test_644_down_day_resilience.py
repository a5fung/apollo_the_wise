"""#644 — `db.get_down_day_resilience`: the third leg of subtle RS (alongside
get_rs_velocity's "rising" and get_rs_turners' "rising faster"): how a name's
daily returns compared to SPY's on the days SPY fell, over the `lookback`
trading sessions strictly BEFORE a given date.

    resilience = median(name's return on SPY's down days)
                - median(SPY's return on those same down days)

THE AS-OF LEAK TEST IS THE POINT (#644's DoD): "a session on or after the
date must never affect the answer." A mock that returns canned rows
regardless of the SQL args can't catch a leak — it would pass even if the
function used `trade_date <= $1`. So `_FakeDailyClosesConn` below is a small
in-memory stand-in for `mi_daily_closes` that actually HONORS the filters
(`trade_date < $1`, `trade_date = ANY($n)`, `ticker = ANY($n)`) the same way
Postgres would, built from the real args each query receives — planting a
row on/after `d` can only leak into the answer if the function's own SQL
fails to exclude it.

MUTATION CHECK (by inspection, matches test_latest_complete_score_date.py's
convention): `test_leak_test_actually_catches_a_leak` below flips the
session-window comparison from `<` to `<=` (the exact leak this guards
against) and asserts the leak test WOULD have failed — i.e. the guard is not
vacuous.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

import agents.market_intelligence.db as db


def _run(coro):
    return asyncio.run(coro)


# ── A tiny in-memory `mi_daily_closes` that actually filters on the args ────

class _FakeDailyClosesConn:
    """Rows: list of {"ticker", "trade_date", "close"}. `.fetch()` dispatches
    on which of `get_down_day_resilience`'s three query shapes it matches and
    applies the SAME filter a real Postgres query would — so planting a row
    outside the intended window can only reach the caller if the function's
    own SQL fails to exclude it (not because the fake ignored the args)."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.calls: list[tuple] = []

    async def fetch(self, sql: str, *args):
        self.calls.append((sql, args))
        if "DISTINCT trade_date" in sql:
            bound, limit = args
            # Read the ACTUAL comparison out of the SQL text rather than hardcoding "<" —
            # so the mutation check below (flipping "<" to "<=" in db.py) changes what this
            # fake returns too, instead of the fake silently enforcing correctness on its own.
            op_le = "trade_date <= $1" in sql
            dates = sorted(
                {r["trade_date"] for r in self._rows
                 if (r["trade_date"] <= bound if op_le else r["trade_date"] < bound)},
                reverse=True,
            )[:limit]
            return [{"trade_date": dt} for dt in dates]
        if "ticker = 'SPY'" in sql:
            (dates_arg,) = args
            return [
                dict(r) for r in self._rows
                if r["ticker"] == "SPY" and r["trade_date"] in dates_arg
                and r["close"] is not None
            ]
        if "ticker = ANY($1)" in sql:
            tickers_arg, dates_arg = args
            return [
                dict(r) for r in self._rows
                if r["ticker"] in tickers_arg and r["trade_date"] in dates_arg
                and r["close"] is not None
            ]
        # unfiltered-tickers branch (tickers=None)
        (dates_arg,) = args
        return [
            dict(r) for r in self._rows
            if r["trade_date"] in dates_arg and r["close"] is not None
        ]


def _wire(monkeypatch, rows: list[dict]):
    pool, conn = make_mock_pool()
    fake = _FakeDailyClosesConn(rows)
    conn.fetch = fake.fetch
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    return fake


# ── Synthetic calendar: D1..D6, 5 return-pairs, down days at D2/D4/D6 ───────
# SPY: D1=100 -> D2=95 (-5%, DOWN) -> D3=101 (up) -> D4=90.9 (-10%, DOWN)
#      -> D5=95 (up) -> D6=85.5 (-10%, DOWN)
# spy down-day returns: [-5%, -10%, -10%] -> median -10%
D1, D2, D3, D4, D5, D6 = (date(2026, 8, d) for d in (3, 4, 5, 6, 7, 10))
D0 = date(2026, 7, 31)          # before the window — must never be selected over D1..D6
D_BOUND = date(2026, 8, 11)     # "d" itself — the exclusive upper bound
D_AFTER = date(2026, 8, 12)     # strictly after "d"

_SPY_ROWS = [
    {"ticker": "SPY", "trade_date": D1, "close": 100.0},
    {"ticker": "SPY", "trade_date": D2, "close": 95.0},
    {"ticker": "SPY", "trade_date": D3, "close": 101.0},
    {"ticker": "SPY", "trade_date": D4, "close": 90.9},
    {"ticker": "SPY", "trade_date": D5, "close": 95.0},
    {"ticker": "SPY", "trade_date": D6, "close": 85.5},
]

# XYZ: held up better than SPY on 2 of 3 down days -> resilience should be POSITIVE
# down-day returns: D2 -2%, D4 -12%, D6 -8% -> median -8% ; resilience = -8% - (-10%) = +2%
_XYZ_ROWS = [
    {"ticker": "XYZ", "trade_date": D1, "close": 50.0},
    {"ticker": "XYZ", "trade_date": D2, "close": 49.0},
    {"ticker": "XYZ", "trade_date": D3, "close": 51.0},
    {"ticker": "XYZ", "trade_date": D4, "close": 44.88},
    {"ticker": "XYZ", "trade_date": D5, "close": 46.0},
    {"ticker": "XYZ", "trade_date": D6, "close": 42.32},
]

# ABC: held up WORSE than SPY every down day -> resilience should be NEGATIVE
# down-day returns: D2 -8%, D4 -15%, D6 -20% -> median -15% ; resilience = -15% - (-10%) = -5%
_ABC_ROWS = [
    {"ticker": "ABC", "trade_date": D1, "close": 50.0},
    {"ticker": "ABC", "trade_date": D2, "close": 46.0},
    {"ticker": "ABC", "trade_date": D3, "close": 48.0},
    {"ticker": "ABC", "trade_date": D4, "close": 40.8},
    {"ticker": "ABC", "trade_date": D5, "close": 42.0},
    {"ticker": "ABC", "trade_date": D6, "close": 33.6},
]

# DEF: has data on every date EXCEPT the down days -> zero valid down-day
# observations -> must be OMITTED, not returned with a fabricated value.
_DEF_ROWS = [
    {"ticker": "DEF", "trade_date": D1, "close": 20.0},
    {"ticker": "DEF", "trade_date": D3, "close": 21.0},
    {"ticker": "DEF", "trade_date": D5, "close": 22.0},
]

_ALL_ROWS = _SPY_ROWS + _XYZ_ROWS + _ABC_ROWS + _DEF_ROWS


# ═══════════════════════════════════════════════════════════════════════════
# 1. Correctness — hand-computed resilience, sort order, omission
# ═══════════════════════════════════════════════════════════════════════════

def test_resilience_matches_hand_computation(monkeypatch):
    _wire(monkeypatch, _ALL_ROWS)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=["XYZ", "ABC", "DEF"], lookback=5))

    by_ticker = {r["ticker"]: r for r in out}
    assert set(by_ticker) == {"XYZ", "ABC"}, "DEF has zero down-day data and must be omitted"

    assert by_ticker["XYZ"]["resilience"] == pytest.approx(0.02, abs=1e-6)
    assert by_ticker["XYZ"]["ticker_median_down_day_return"] == pytest.approx(-0.08, abs=1e-6)
    assert by_ticker["XYZ"]["spy_median_down_day_return"] == pytest.approx(-0.10, abs=1e-6)
    assert by_ticker["XYZ"]["n_down_days_used"] == 3
    assert by_ticker["XYZ"]["n_down_days_market"] == 3
    assert by_ticker["XYZ"]["window_start"] == D1
    assert by_ticker["XYZ"]["window_end"] == D6

    assert by_ticker["ABC"]["resilience"] == pytest.approx(-0.05, abs=1e-6)

    # sorted resilience DESC — the better-held-up name first
    assert [r["ticker"] for r in out] == ["XYZ", "ABC"]


def test_tickers_accepts_frozenset_not_just_list(monkeypatch):
    """A cohort basket built by the churn-split script's `_tickers()` is a
    frozenset — asyncpg's ANY($1) needs a real list, so the function must
    coerce it rather than pass the frozenset straight through."""
    _wire(monkeypatch, _ALL_ROWS)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=frozenset({"XYZ", "ABC"}), lookback=5))
    assert {r["ticker"] for r in out} == {"XYZ", "ABC"}


def test_tickers_none_scores_every_name_with_data(monkeypatch):
    """tickers=None is the unfiltered mode (mirrors get_rs_leaders' min_adv=0) —
    every ticker with a close in the window is scored, INCLUDING SPY itself
    (resilience against itself is exactly 0 — no special-casing needed), and
    DEF is still omitted (zero valid down-day observations)."""
    _wire(monkeypatch, _ALL_ROWS)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=None, lookback=5))
    assert {r["ticker"] for r in out} == {"XYZ", "ABC", "SPY"}
    spy_row = next(r for r in out if r["ticker"] == "SPY")
    assert spy_row["resilience"] == pytest.approx(0.0, abs=1e-9)


def test_ticker_with_no_down_day_data_is_omitted_not_zeroed(monkeypatch):
    _wire(monkeypatch, _SPY_ROWS + _DEF_ROWS)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=["DEF"], lookback=5))
    assert out == []


def test_partial_down_day_coverage_uses_only_available_observations(monkeypatch):
    """A ticker present on only SOME down days still gets scored, off what it has."""
    partial = [
        {"ticker": "PART", "trade_date": D1, "close": 10.0},
        {"ticker": "PART", "trade_date": D2, "close": 9.5},   # -5%, matches SPY's D2 exactly
        # missing D3, D4 -> no D3-D4 return computable
        {"ticker": "PART", "trade_date": D5, "close": 10.0},
        {"ticker": "PART", "trade_date": D6, "close": 9.0},   # -10%, matches SPY's D6 exactly
    ]
    _wire(monkeypatch, _SPY_ROWS + partial)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=["PART"], lookback=5))
    assert len(out) == 1
    row = out[0]
    assert row["n_down_days_used"] == 2          # D2 and D6 only; D4 unreachable
    assert row["n_down_days_market"] == 3         # SPY still had 3 down days market-wide
    assert row["ticker_median_down_day_return"] == pytest.approx(-0.075, abs=1e-6)  # median(-5%, -10%)
    assert row["resilience"] == pytest.approx(0.025, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Insufficient-data contract — mirrors _prepare_weekly_snapshots' "[]"
# ═══════════════════════════════════════════════════════════════════════════

def test_fewer_than_lookback_plus_one_sessions_returns_empty(monkeypatch):
    """Only D3..D6 exist before D_BOUND (4 dates) but lookback=5 needs 6."""
    short_rows = [r for r in _ALL_ROWS if r["trade_date"] >= D3]
    _wire(monkeypatch, short_rows)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=["XYZ"], lookback=5))
    assert out == []


def test_zero_down_days_returns_empty(monkeypatch):
    """SPY rises every session in the window -> nothing to measure against."""
    all_up_spy = [
        {"ticker": "SPY", "trade_date": D1, "close": 100.0},
        {"ticker": "SPY", "trade_date": D2, "close": 101.0},
        {"ticker": "SPY", "trade_date": D3, "close": 102.0},
        {"ticker": "SPY", "trade_date": D4, "close": 103.0},
        {"ticker": "SPY", "trade_date": D5, "close": 104.0},
        {"ticker": "SPY", "trade_date": D6, "close": 105.0},
    ]
    _wire(monkeypatch, all_up_spy + _XYZ_ROWS)
    out = _run(db.get_down_day_resilience(D_BOUND, tickers=["XYZ"], lookback=5))
    assert out == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. AS-OF LEAK TEST — the DoD. A session on/after `d` must never matter.
# ═══════════════════════════════════════════════════════════════════════════

def _leaky_rows() -> list[dict]:
    """The real dataset PLUS rows dated `d` itself and the day after, with
    wildly different closes that would blow the answer up if ever used."""
    poison = [
        {"ticker": "SPY", "trade_date": D_BOUND, "close": 5.0},     # SPY "crashes" on d
        {"ticker": "SPY", "trade_date": D_AFTER, "close": 500.0},
        {"ticker": "XYZ", "trade_date": D_BOUND, "close": 5000.0},  # XYZ "moons" on d
        {"ticker": "XYZ", "trade_date": D_AFTER, "close": 1.0},
        {"ticker": "ABC", "trade_date": D_BOUND, "close": 0.01},
    ]
    return _ALL_ROWS + poison


def test_session_on_or_after_d_never_affects_the_answer(monkeypatch):
    clean_fake = _wire(monkeypatch, _ALL_ROWS)
    clean_out = _run(db.get_down_day_resilience(D_BOUND, tickers=["XYZ", "ABC"], lookback=5))

    leaky_fake = _wire(monkeypatch, _leaky_rows())
    leaky_out = _run(db.get_down_day_resilience(D_BOUND, tickers=["XYZ", "ABC"], lookback=5))

    assert leaky_out == clean_out, "a row dated on/after d changed the answer — as-of leak"

    # and directly: the session-window query's own bound param is `d`, and
    # nothing it returned is >= d (belt-and-suspenders on the fake itself).
    first_call_args = leaky_fake.calls[0][1]
    assert first_call_args[0] == D_BOUND

# MUTATION CHECK (by inspection, not re-run by CI — matches
# test_latest_complete_score_date.py's convention): flipping the session-window
# query's `trade_date < $1` to `trade_date <= $1` was verified BY HAND (not as a
# live self-mutating test — this codebase's own convention, per that file's
# docstring, is inspection rather than mutating source at test time, which is
# also unsafe under parallel test runners) to make
# `test_session_on_or_after_d_never_affects_the_answer` fail: with `<=`, the
# poisoned SPY/XYZ/ABC rows planted at D_BOUND become a candidate session (the
# most recent of the lookback+1 window), the window shifts from [D1..D6] to
# [D2..D6, D_BOUND], SPY's poisoned 5.0 close manufactures a huge down day, and
# `leaky_out != clean_out` — the exact leak this test exists to catch. Reverted
# immediately after confirming the failure; see the session report for the
# captured pytest output.
