"""#354 Sunday shadow sub-piece (2026-09-13) — failure telemetry on
mi_flag_candidates: `failed_at` / `low_after_breakout` / `undercut_after_breakout`.

SCOPE: this is the telemetry-only piece pulled into Sunday, NOT the five-item
flag_continuation -> Family A merge that is #354's actual headline DoD (that
merge changes detection criteria / stage transitions and stays gated on
operator sign-off + CHANGE_PROCESS + a backtest). These three columns RECORD
when a TRIGGERED breakout later closed back under the base it broke out of,
and how far it fell. They change no entry, no exit, no sizing, no stage
transition, no alert, no board.

Every test below also asserts `stage`/`reason`/`score`/`held_from_stage` are
byte-identical with and without `prior_failure` on the SAME rows — proving
the new columns cannot change what the live board (or any other consumer)
sees.

CONTRACT PINNED AT THE REAL PRODUCER: `db.get_flag_failure_carry`'s actual
row -> dict shaping code runs (against a mocked asyncpg connection, per
tests/conftest.py::make_mock_pool) in test_carry_shapes_rows_from_the_real_producer,
and its OWN return value (not a hand-invented dict) is what the
compute_flag_metrics tests below build their `prior_failure` inputs to match —
the #649 lesson ("a fixture that invents the caller's input is a claim about
the caller, not a test of it").

MUTATION-PROVEN (each confirmed RED against the CORRECT code, then reverted):
  - drop the pivot_high_date match guard (`pf = prior_failure or {}` instead of
    the conditional) -> test_stale_pivot_does_not_leak_into_a_new_base RED
    (asserted None, got the stale failed_at/low/undercut instead).
  - drop the `base["failed_at"] is None` guard (unconditionally re-stamp)
    -> test_failed_at_is_the_first_day_not_the_latest RED (failed_at moved
    to the later undercut day instead of staying pinned to the first failure).
  - change `min(base["low_after_breakout"], close_today)` to plain
    `close_today` -> test_low_after_breakout_tracks_the_running_minimum RED
    (the recorded low rose back up on a bounce day instead of staying at
    the worst close).
  - delete the `if anchor_high is not None:` guard entirely -> every test
    that passes prior_failure=None RED with a TypeError (comparing a float
    close to a None anchor) instead of leaving the columns None.
  - flip `close_today < anchor_low` to `<=` -> test_undercut_requires_strictly_below_anchor_low
    RED (fired True on a close sitting exactly ON the anchor low).
  - drop `anchor_high = min(anchor_high, anchor_breakout_close)` (an advisor-review
    finding: `base_high` alone is too strict a threshold — see the tightening's own
    comment) -> test_close_between_base_high_close_and_base_high_is_not_a_failure RED
    (fired True on a close still ABOVE the actual breakout close).
  - narrow `get_flag_failure_carry`'s `except Exception` to `except ValueError`
    -> test_carry_survives_a_db_error RED (the RuntimeError propagated instead of
    degrading to {} — exactly what must never happen to `run_flag_scan`).

test_never_changes_stage_or_reason is a structural regression guard rather
than independently mutation-provable within the new block: every later
stage-classification line in compute_flag_metrics unconditionally reasserts
stage/reason/score/held_from_stage, so the new block physically cannot leak
into them today (tried stamping `reason` inside the block as a mutation —
downstream classification code silently overwrote it back, no red). It stays
in place to catch a FUTURE refactor that moves the block past that point.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool


# ── Fixture builders (same shape as tests/test_htf_criteria.py's _htf_rows) ──

def _row(d, o, h, l, c, v):
    return {"trade_date": d, "open_price": o, "high_price": h,
            "low_price": l, "close": c, "volume": v}


def _base_pole_flag(base_price=10.0, n_base=42, n_pole=20, n_flag=8,
                     runup_ratio=2.2, flag_depth=0.10):
    """base(flat) -> pole(ramp) -> flag(consolidate). `today` = the last row."""
    rows, d0, di = [], date(2026, 1, 1), 0
    for _ in range(n_base):
        rows.append(_row(d0 + timedelta(days=di), base_price, base_price * 1.01,
                          base_price * 0.99, base_price, 1_000_000))
        di += 1
    peak = base_price * runup_ratio
    for j in range(n_pole):
        p = base_price + (peak - base_price) * ((j + 1) / n_pole)
        v = 3_000_000 if j == n_pole // 2 else 1_000_000
        rows.append(_row(d0 + timedelta(days=di), p * 0.99, p * 1.025,
                          p * 0.975, p, v))
        di += 1
    flag_price = peak * (1 - flag_depth)
    for _ in range(n_flag):
        rows.append(_row(d0 + timedelta(days=di), flag_price, flag_price * 1.025,
                          flag_price * 0.975, flag_price, 800_000))
        di += 1
    return rows, d0, di


def _triggered_fixture():
    """A real TRIGGERED breakout, reached the same way run_flag_scan would
    see it (was-COILED-recent bypasses the same-day coiled_today requirement,
    mirroring a genuinely COILED-then-broke-out ticker)."""
    rows, d0, di = _base_pole_flag()
    pre = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=[])
    flag_price = rows[-1]["close"]
    breakout_close = pre["base_high"] * 1.03
    rows = rows + [_row(d0 + timedelta(days=di), flag_price, breakout_close * 1.01,
                         flag_price * 0.99, breakout_close, 5_000_000)]
    di += 1
    day0 = fd.compute_flag_metrics(
        rows, ticker="TST", recent_stages=["COILED"] * 5,
        prior_pivot_date=pre["pivot_high_date"], prior_pivot_high=pre["pivot_high_price"],
    )
    assert day0["stage"] == "TRIGGERED", f"fixture didn't reach TRIGGERED: {day0['reason']}"
    return rows, d0, di, day0


def _append_close(rows, d0, di, close):
    """One more session at `close` (small, symmetric intraday range)."""
    return rows + [_row(d0 + timedelta(days=di), close, close * 1.01, close * 0.99, close, 900_000)]


# ── 1. Day of breakout: no anchor exists yet, columns stay None ─────────────

def test_no_anchor_on_the_breakout_day_itself():
    """The anchor query (db.get_flag_failure_carry) only sees YESTERDAY's
    persisted rows — on the day a breakout first fires, there is no anchor
    on record yet (it's written moments later). Mirrors run_flag_scan calling
    compute_flag_metrics with prior_failure=None on that first day."""
    _rows, _d0, _di, day0 = _triggered_fixture()
    assert day0["failed_at"] is None
    assert day0["low_after_breakout"] is None
    assert day0["undercut_after_breakout"] is None


# ── 2. Never triggered at all: no rows, no anchor -> everything None ───────

def test_never_triggered_stays_null():
    rows, _d0, _di = _base_pole_flag()
    out = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=[])
    assert out["stage"] != "TRIGGERED"
    assert out["failed_at"] is None
    assert out["low_after_breakout"] is None
    assert out["undercut_after_breakout"] is None


# ── 3. Guard against a TypeError if the anchor is absent (mutation: delete
#      the `if anchor_high is not None:` guard) ─────────────────────────────

def test_no_anchor_yet_does_not_crash():
    rows, d0, di, day0 = _triggered_fixture()
    rows2 = _append_close(rows, d0, di, day0["base_high"] * 1.02)
    out = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=None,
    )
    assert out["failed_at"] is None
    assert out["low_after_breakout"] is None
    assert out["undercut_after_breakout"] is None


# ── 4. End-to-end: holding -> fails -> undercuts, across real day-by-day
#      compute_flag_metrics calls, carrying prior_failure forward exactly as
#      run_flag_scan would (each day's output feeds the next day's input) ──

def _chain(day0):
    """Build the holding / failed / undercut day-by-day scenario off a real
    TRIGGERED day0. Returns (rows, d0, di, out1, out2, out3, out4) where
    out1=holding, out2=fails (closes under anchor_base_high, above
    anchor_base_low), out3=undercuts (closes under anchor_base_low too),
    out4=one more day so failed_at's "first day, not latest" is provable."""
    anchor_high, anchor_low = day0["base_high"], day0["base_low"]
    assert day0["breakout_close"] > anchor_high, (
        "fixture assumption: breakout_close is the larger bound here, so "
        "min(anchor_base_high, anchor_breakout_close) == anchor_base_high — "
        "the tightening in test_close_between_base_high_close_and_base_high_is_not_a_failure "
        "covers the case where it is the SMALLER bound instead"
    )

    def _carry(prior_out):
        return {
            "pivot_high_date": prior_out["pivot_high_date"],
            "failed_at": prior_out["failed_at"],
            "low_after_breakout": prior_out["low_after_breakout"],
            "undercut_after_breakout": prior_out["undercut_after_breakout"],
            "anchor_base_high": anchor_high,
            "anchor_base_low": anchor_low,
            "anchor_breakout_close": day0["breakout_close"],
        }

    return anchor_high, anchor_low, _carry


def test_holding_above_anchor_tracks_low_but_does_not_fail():
    rows, d0, di, day0 = _triggered_fixture()
    anchor_high, anchor_low, _carry = _chain(day0)
    rows1 = _append_close(rows, d0, di, anchor_high * 1.01)  # still above the breakout level
    out1 = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["COILED", "TRIGGERED", "TRIGGERED", "TRIGGERED", "TRIGGERED"],
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=_carry(day0),
    )
    assert out1["failed_at"] is None, "still holding above the breakout level — must not fail"
    assert out1["undercut_after_breakout"] is False
    assert out1["low_after_breakout"] == pytest.approx(anchor_high * 1.01), (
        "low_after_breakout must start tracking as soon as the anchor exists, "
        "even before a failure — the name's own close is the first observation"
    )


def test_failed_at_fires_the_first_day_close_gives_back_the_level():
    rows, d0, di, day0 = _triggered_fixture()
    anchor_high, anchor_low, _carry = _chain(day0)
    rows1 = _append_close(rows, d0, di, anchor_high * 1.01)
    out1 = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["COILED", "TRIGGERED", "TRIGGERED", "TRIGGERED", "TRIGGERED"],
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=_carry(day0),
    )
    fail_close = (anchor_high + anchor_low) / 2.0  # under anchor_high, still above anchor_low
    rows2 = _append_close(rows1, d0, di + 1, fail_close)
    out2 = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out1["pivot_high_date"], prior_pivot_high=out1["pivot_high_price"],
        prior_failure=_carry(out1),
    )
    assert out2["failed_at"] == out2["scan_date"], "must stamp the day it gave back the level"
    assert out2["undercut_after_breakout"] is False, "gave back base_high, not base_low yet"
    assert out2["low_after_breakout"] == pytest.approx(fail_close)


def test_failed_at_is_the_first_day_not_the_latest():
    """Once set, failed_at must never move to a later day — even when a
    DEEPER failure (the undercut) happens after it. Proves the "first day"
    semantics the column is named for."""
    rows, d0, di, day0 = _triggered_fixture()
    anchor_high, anchor_low, _carry = _chain(day0)
    rows1 = _append_close(rows, d0, di, anchor_high * 1.01)
    out1 = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["COILED", "TRIGGERED", "TRIGGERED", "TRIGGERED", "TRIGGERED"],
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=_carry(day0),
    )
    fail_close = (anchor_high + anchor_low) / 2.0
    rows2 = _append_close(rows1, d0, di + 1, fail_close)
    out2 = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out1["pivot_high_date"], prior_pivot_high=out1["pivot_high_price"],
        prior_failure=_carry(out1),
    )
    first_failed_at = out2["failed_at"]

    undercut_close = anchor_low * 0.95
    rows3 = _append_close(rows2, d0, di + 2, undercut_close)
    out3 = fd.compute_flag_metrics(
        rows3, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out2["pivot_high_date"], prior_pivot_high=out2["pivot_high_price"],
        prior_failure=_carry(out2),
    )
    assert out3["failed_at"] == first_failed_at, "failed_at must stay pinned to the FIRST failure day"
    assert out3["undercut_after_breakout"] is True
    assert out3["scan_date"] != first_failed_at, "sanity: the undercut day is a later day"


def test_low_after_breakout_tracks_the_running_minimum():
    """A bounce day after the failure must not erase the earlier, worse low."""
    rows, d0, di, day0 = _triggered_fixture()
    anchor_high, anchor_low, _carry = _chain(day0)
    rows1 = _append_close(rows, d0, di, anchor_high * 1.01)
    out1 = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["COILED", "TRIGGERED", "TRIGGERED", "TRIGGERED", "TRIGGERED"],
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=_carry(day0),
    )
    worst_close = anchor_low * 0.90
    rows2 = _append_close(rows1, d0, di + 1, worst_close)
    out2 = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out1["pivot_high_date"], prior_pivot_high=out1["pivot_high_price"],
        prior_failure=_carry(out1),
    )
    assert out2["low_after_breakout"] == pytest.approx(worst_close)

    bounce_close = anchor_low * 1.05  # a partial recovery, still below anchor_high
    rows3 = _append_close(rows2, d0, di + 2, bounce_close)
    out3 = fd.compute_flag_metrics(
        rows3, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out2["pivot_high_date"], prior_pivot_high=out2["pivot_high_price"],
        prior_failure=_carry(out2),
    )
    assert out3["low_after_breakout"] == pytest.approx(worst_close), (
        "a bounce day must not erase the earlier, worse low — the column "
        "records the running MINIMUM, not the latest close"
    )


def test_undercut_requires_strictly_below_anchor_low():
    """Sitting exactly ON the anchor low is a support test, not an undercut."""
    rows, d0, di, day0 = _triggered_fixture()
    anchor_high, anchor_low, _carry = _chain(day0)
    on_the_level = _append_close(rows, d0, di, anchor_low)
    out = fd.compute_flag_metrics(
        on_the_level, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=_carry(day0),
    )
    assert out["undercut_after_breakout"] is False, "a close AT the anchor low is not an undercut"


def test_close_between_base_high_close_and_base_high_is_not_a_failure():
    """`base_high` (persisted) is the max INTRADAY HIGH over the base window —
    always >= the max-CLOSE level (`base_high_close`) that actually gated
    TRIGGERED. A close sitting strictly BETWEEN the two is still above the
    level that triggered the breakout and must not read as failed, even
    though it is below the persisted `base_high`. Caught by an advisor
    review of this card: the day-0 fixture's breakout always cleared
    `base_high` itself, so this gap never showed."""
    rows, d0, di = _base_pole_flag()
    pre = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=[])
    base_high_close = rows[-1]["close"]           # the flat flag's own close level
    assert pre["base_high"] > base_high_close, "fixture assumption: base_high (intraday) > base_high_close"

    # Breakout closes just above base_high_close but BELOW base_high.
    breakout_close = (base_high_close + pre["base_high"]) / 2.0
    assert base_high_close < breakout_close < pre["base_high"]
    rows2 = rows + [_row(d0 + timedelta(days=di), rows[-1]["close"], breakout_close * 1.005,
                          rows[-1]["close"] * 0.995, breakout_close, 5_000_000)]
    day0 = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["COILED"] * 5,
        prior_pivot_date=pre["pivot_high_date"], prior_pivot_high=pre["pivot_high_price"],
    )
    assert day0["stage"] == "TRIGGERED", f"fixture didn't reach TRIGGERED: {day0['reason']}"
    assert day0["breakout_close"] == pytest.approx(breakout_close)

    # Day+1 closes just above the ACTUAL breakout close (still climbing) but
    # below the persisted base_high — the exact counterexample.
    day1_close = breakout_close * 1.01
    assert day1_close < day0["base_high"]
    rows3 = _append_close(rows2, d0, di + 1, day1_close)
    prior_failure = {
        "pivot_high_date": day0["pivot_high_date"],
        "failed_at": None, "low_after_breakout": None, "undercut_after_breakout": None,
        "anchor_base_high": day0["base_high"], "anchor_base_low": day0["base_low"],
        "anchor_breakout_close": day0["breakout_close"],
    }
    out = fd.compute_flag_metrics(
        rows3, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=prior_failure,
    )
    assert out["failed_at"] is None, (
        f"closed at {day1_close:.4f}, ABOVE breakout_close {breakout_close:.4f} — "
        "still climbing, must not read as failed even though it's below the "
        f"intraday base_high {day0['base_high']:.4f}"
    )


# ── 5. Stale-pivot guard: a prior base's failure state must not leak into a
#      brand-new pivot cycle for the same ticker ────────────────────────────

def test_stale_pivot_does_not_leak_into_a_new_base():
    rows, d0, di, day0 = _triggered_fixture()
    stale = {
        "pivot_high_date": date(2020, 1, 1),   # does NOT match today's pivot_high_date
        "failed_at": date(2020, 2, 1),
        "low_after_breakout": 1.0,
        "undercut_after_breakout": True,
        "anchor_base_high": 999.0,
        "anchor_base_low": 1.0,
    }
    rows1 = _append_close(rows, d0, di, day0["base_high"] * 1.01)
    out = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=stale,
    )
    assert out["failed_at"] is None
    assert out["low_after_breakout"] is None
    assert out["undercut_after_breakout"] is None


# ── 6. Scope guard: these columns can never change what the board sees ─────

def test_never_changes_stage_or_reason():
    rows, d0, di, day0 = _triggered_fixture()
    anchor_high, anchor_low, _carry = _chain(day0)
    rows1 = _append_close(rows, d0, di, anchor_high * 1.01)
    out1 = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["COILED", "TRIGGERED", "TRIGGERED", "TRIGGERED", "TRIGGERED"],
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=_carry(day0),
    )
    fail_close = (anchor_high + anchor_low) / 2.0
    rows2 = _append_close(rows1, d0, di + 1, fail_close)

    with_prior = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out1["pivot_high_date"], prior_pivot_high=out1["pivot_high_price"],
        prior_failure=_carry(out1),
    )
    without_prior = fd.compute_flag_metrics(
        rows2, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=out1["pivot_high_date"], prior_pivot_high=out1["pivot_high_price"],
        prior_failure=None,
    )
    for key in ("stage", "reason", "score", "held_from_stage"):
        assert with_prior[key] == without_prior[key], (
            f"{key} differs between prior_failure states — the failure "
            "telemetry must never influence stage classification"
        )
    # and it actually DID fire, so this isn't a vacuous comparison
    assert with_prior["failed_at"] is not None
    assert without_prior["failed_at"] is None


# ── 7. Contract pinned at the real producer: db.get_flag_failure_carry ─────

@pytest.mark.asyncio
async def test_carry_shapes_rows_from_the_real_producer(monkeypatch):
    """Exercises the ACTUAL get_flag_failure_carry code (row -> dict shaping,
    float coercion, key names) against a mocked asyncpg connection, rather
    than hand-inventing the dict compute_flag_metrics expects — the #649
    lesson: a fixture that invents the caller's input is a claim about the
    caller, not a test of it."""
    fake_rows = [
        {
            "ticker": "ABCD",
            "pivot_high_date": date(2026, 3, 3),
            "failed_at": date(2026, 3, 14),
            "low_after_breakout": 19.8,
            "undercut_after_breakout": False,
            "anchor_base_high": 20.295,
            "anchor_base_low": 19.305,
            "anchor_breakout_close": 20.90,
        },
        {
            # a ticker with a prior row but no breakout on record yet
            "ticker": "NOBRK",
            "pivot_high_date": date(2026, 3, 5),
            "failed_at": None,
            "low_after_breakout": None,
            "undercut_after_breakout": None,
            "anchor_base_high": None,
            "anchor_base_low": None,
            "anchor_breakout_close": None,
        },
    ]
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=fake_rows)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    out = await db.get_flag_failure_carry(date(2026, 3, 15))

    assert set(out.keys()) == {"ABCD", "NOBRK"}
    abcd = out["ABCD"]
    assert abcd["pivot_high_date"] == date(2026, 3, 3)
    assert abcd["failed_at"] == date(2026, 3, 14)
    assert abcd["low_after_breakout"] == pytest.approx(19.8)
    assert abcd["undercut_after_breakout"] is False
    assert abcd["anchor_base_high"] == pytest.approx(20.295)
    assert abcd["anchor_base_low"] == pytest.approx(19.305)
    assert abcd["anchor_breakout_close"] == pytest.approx(20.90)
    assert isinstance(abcd["low_after_breakout"], float)  # real coercion ran, not a passthrough

    nobrk = out["NOBRK"]
    assert nobrk["anchor_base_high"] is None and nobrk["anchor_base_low"] is None
    assert nobrk["anchor_breakout_close"] is None
    assert nobrk["failed_at"] is None


@pytest.mark.asyncio
async def test_carry_survives_a_db_error(monkeypatch):
    """Telemetry must never be load-bearing for the live scan (the 2026-08-03
    lesson flag_detector.py's own history warns about — a detector-adjacent
    write failing silently starved the whole board). A DB error here must
    degrade to {} (every ticker reads as "no carry that day"), not raise
    and take down run_flag_scan."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=RuntimeError("connection reset"))
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    out = await db.get_flag_failure_carry(date(2026, 3, 15))
    assert out == {}


@pytest.mark.asyncio
async def test_carry_feeds_compute_flag_metrics_end_to_end(monkeypatch):
    """The real producer's output, fed directly into compute_flag_metrics
    (no hand-authored prior_failure dict at all)."""
    rows, d0, di, day0 = _triggered_fixture()
    fake_rows = [{
        "ticker": "TST",
        "pivot_high_date": day0["pivot_high_date"],
        "failed_at": None,
        "low_after_breakout": None,
        "undercut_after_breakout": None,
        "anchor_base_high": day0["base_high"],
        "anchor_base_low": day0["base_low"],
        "anchor_breakout_close": day0["breakout_close"],
    }]
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=fake_rows)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    carry = await db.get_flag_failure_carry(day0["scan_date"] + timedelta(days=1))

    fail_close = (day0["base_high"] + day0["base_low"]) / 2.0
    rows1 = _append_close(rows, d0, di, fail_close)
    out1 = fd.compute_flag_metrics(
        rows1, ticker="TST", recent_stages=["TRIGGERED"] * 5,
        prior_pivot_date=day0["pivot_high_date"], prior_pivot_high=day0["pivot_high_price"],
        prior_failure=carry.get("TST"),
    )
    assert out1["failed_at"] == out1["scan_date"]
    assert out1["undercut_after_breakout"] is False
