"""#610 — the HTF detector's FOUR-READING OBSERVER (2026-09-19).

Operator ruling 2026-09-18 (docs/setups/htf.md change log): do not pick a depth reading yet —
*"we should be able to observe multiple parameters since we're just collecting data and
refining the setup"*. So `compute_flag_metrics` now RECORDS, per candidate-day, the margin
under each reading still on the table, and the live admission gate is UNCHANGED (flag LOW ÷
pole high ≥ 0.75). Four new keys on the metrics dict → four columns on `mi_flag_candidates`:

  depth_on_low     flag's lowest LOW   ÷ pole high   (the LIVE reading; gate fires < 0.75)
  depth_on_close   flag's lowest CLOSE ÷ pole high   (the spec's literal `Close ≥ 0.75 × High`)
  sma20_margin     (close − sma_20) / sma_20          SIGNED: negative = the SMA20 stop fires
  ma_stack_margin  min of the 10≥20 and 20≥50 legs   SIGNED: negative = the MA-stack gate fires

OBSERVATION IS NOT ADMISSION. The tests below pin (1) the four hand-measured MRNA values from
PLAN #610's EXPECT on the day they were measured, against the REAL fixture bars (N=8 corpus,
`tests/fixtures/htf_labelled.py`), (2) that each reading agrees with the gate it shadows on
every replayed corpus row, (3) that a reading is NULL until its inputs exist, and (4) that
`db.insert_flag_candidate` actually carries the four values to the row. The observer-is-not-a-
gate proof over PROD data (12,657 stored candidate-days 2026-08-17 → 09-17, old function vs new,
byte-identical stage/reason/score/held_from_stage) is `scripts/probes/_610_four_reading_observer_
replay.py`; inside the suite, `test_htf_labelled_corpus.py` pins every member's recorded verdict
and would go RED if the observer moved one.

MUTATION-PROVEN (each run RED against the mutation named, then restored and re-run green):
  - depth_on_low computed from `base_low_close` instead of `base_low`
      → test_mrna_four_hand_measured_readings RED (75.5 ≠ 72.8)
      → test_observer_agrees_with_the_gate_it_shadows RED (MRNA 08-25 `flag_low_` row reads ≥ 0.75)
      → test_readings_are_null_until_their_inputs_exist RED (depth_on_low ≠ 1 − flag_depth_pct).
  - sma20_margin sign flipped (`sma_20 - close_today`)
      → test_mrna_four_hand_measured_readings RED (+0.035 vs −0.03 ± 0.01)
      → test_observer_agrees_with_the_gate_it_shadows RED (CDNA 07-30 TIGHTENING reads < 0).
  - ma_stack_margin reduced to the 20≥50 leg only
      → test_mrna_four_hand_measured_readings RED (+49.93 ≠ −0.24)
      → test_observer_agrees_with_the_gate_it_shadows RED (MRNA 09-17 `ma_stack_not_stage2` reads > 0).
  - the depth pair's assignment deleted → test_readings_are_null_until_their_inputs_exist RED
      (`None is not None` on the runup-rejected row); the two corpus tests RED with TypeError.
  - the SMA pair's assignment moved ABOVE the runup gate → test_readings_are_null_until_their_
      inputs_exist RED (the runup-rejected row carried sma20_margin = 0.0021, not None).
  - `record.get("ma_stack_margin")` dropped from insert_flag_candidate's args
      → test_insert_flag_candidate_carries_the_four_readings RED (39 args, sentinel missing).
  - `ma_stack_margin = EXCLUDED.ma_stack_margin` dropped from the ON CONFLICT clause
      → same test RED (the upsert would leave a re-scanned row's reading stale).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool
from tests.fixtures.htf_labelled import HTF_LABELLED
from tests.test_htf_criteria import _htf_rows
from tests.test_htf_labelled_corpus import _ACTIONABLE, _load_bars, _replay

_FOUR = ("depth_on_low", "depth_on_close", "sma20_margin", "ma_stack_margin")
_THROUGH = date(2026, 9, 17)     # MRNA's breakout day — the last bar in the fixture


@pytest.fixture(scope="module")
def corpus() -> dict[str, dict[date, dict]]:
    """Every labelled member replayed through the SHIPPED detector, prod-style state threading."""
    bars = _load_bars()
    return {m.ticker: _replay(m.ticker, bars[m.ticker], through=_THROUGH) for m in HTF_LABELLED}


# ── 1. The day-one check: MRNA's four hand-measured values (PLAN #610 EXPECT) ────────────────

def test_mrna_four_hand_measured_readings(corpus):
    """PLAN #610 EXPECT: on the 2026-09-17 MRNA bars the columns read depth-on-low 72.8%,
    depth-on-close 75.5%, SMA20 margin 0.03% (measured 09-16), MA-stack margin 0.24% (09-17).
    Margins are stored SIGNED (negative = the gate fires), so the last two assert as −0.03 / −0.24.

    The SMA20 tolerance is ±0.01 percentage points, not 2-dp rounding: the hand figure came from
    the reason string's 2-dp SMA (145.62 vs 145.67 → 0.034%); the exact fixture value is
    −0.0350% (sma_20 = 145.671), which 2-dp rounding would print as −0.04. ±0.01 pp still
    rejects a flipped sign (+0.035) or the wrong SMA (sma_10 → +1.28%).

    And the acting stage/reason on both days are the rows prod actually stored (read 2026-09-19),
    byte for byte — the observer records these margins WITHOUT moving the verdict.
    """
    r16 = corpus["MRNA"][date(2026, 9, 16)]
    r17 = corpus["MRNA"][date(2026, 9, 17)]

    assert round(r17["depth_on_low"] * 100, 1) == 72.8
    assert round(r17["depth_on_close"] * 100, 1) == 75.5
    assert abs(r16["sma20_margin"] * 100 - (-0.03)) <= 0.01
    assert round(r17["ma_stack_margin"] * 100, 2) == -0.24

    assert (r16["stage"], r16["reason"]) == ("INVALIDATED", "close_145.62_below_sma20_145.67")
    assert (r17["stage"], r17["reason"]) == ("unqualified", "ma_stack_not_stage2_144.5/144.9/96.6")
    # the depth pair is a property of the flag, not the day: identical on both days
    assert r16["depth_on_low"] == r17["depth_on_low"]
    assert r16["depth_on_close"] == r17["depth_on_close"]


# ── 2. Each reading agrees with the gate it shadows, on every replayed corpus row ────────────

def test_observer_agrees_with_the_gate_it_shadows(corpus):
    """For every (member, scan_date) the corpus replays: a `flag_low_` reject carries
    depth_on_low < 0.75; a `_below_sma20_` INVALIDATED carries sma20_margin < 0; a
    `ma_stack_not_stage2` reject carries ma_stack_margin < 0; and an ACTIONABLE row carries all
    three on the passing side. Each family must be seen at least once (non-vacuous)."""
    seen = {"flag_low": 0, "sma20": 0, "ma_stack": 0, "actionable": 0}
    for ticker, by_date in corpus.items():
        for d, m in by_date.items():
            reason = m["reason"] or ""
            tag = f"{ticker} {d} {m['stage']} {reason}"
            if reason.startswith("flag_low_"):
                seen["flag_low"] += 1
                assert m["depth_on_low"] is not None and m["depth_on_low"] < fd._FLAG_DEPTH_MIN, tag
            if "_below_sma20_" in reason:
                seen["sma20"] += 1
                assert m["sma20_margin"] is not None and m["sma20_margin"] < 0, tag
            if reason.startswith("ma_stack_not_stage2"):
                seen["ma_stack"] += 1
                assert m["ma_stack_margin"] is not None and m["ma_stack_margin"] < 0, tag
            if m["stage"] in _ACTIONABLE:
                seen["actionable"] += 1
                assert m["depth_on_low"] >= fd._FLAG_DEPTH_MIN - 1e-12, tag
                assert m["sma20_margin"] is not None and m["sma20_margin"] >= 0, tag
                if m["ma_stack_margin"] is not None:
                    assert m["ma_stack_margin"] >= 0, tag
    assert all(v > 0 for v in seen.values()), seen


# ── 3. A reading is NULL until its inputs exist — and never before ──────────────────────────

def test_readings_are_null_until_their_inputs_exist():
    """Liquidity reject (before the pivot): all four None. Runup reject (base window exists,
    SMAs not yet computed): the depth pair set, the SMA pair None. A qualified flag: all four
    set, depth_on_low == 1 − flag_depth_pct, and the row is still actionable."""
    thin = _htf_rows(runup_ratio=2.0, flag_depth=0.10)
    for r in thin:
        r["volume"] = 100_000
    out = fd.compute_flag_metrics(thin, ticker="THIN", recent_stages=[])
    assert out["reason"].startswith("adv_")
    assert all(out[k] is None for k in _FOUR), {k: out[k] for k in _FOUR}

    out = fd.compute_flag_metrics(_htf_rows(runup_ratio=1.6), ticker="LOW", recent_stages=[])
    assert out["reason"].startswith("runup_")
    assert out["depth_on_low"] is not None and out["depth_on_close"] is not None
    assert out["sma20_margin"] is None and out["ma_stack_margin"] is None

    out = fd.compute_flag_metrics(_htf_rows(runup_ratio=2.0, flag_depth=0.10),
                                  ticker="HTF", recent_stages=[])
    assert out["stage"] in _ACTIONABLE, out["reason"]
    assert all(out[k] is not None for k in _FOUR), {k: out[k] for k in _FOUR}
    assert out["depth_on_low"] == pytest.approx(1.0 - out["flag_depth_pct"], abs=1e-12)
    assert out["depth_on_close"] >= out["depth_on_low"]      # a close can never sit under the low


# ── 4. The row actually carries the readings — pinned at the real producer ──────────────────

@pytest.mark.asyncio
async def test_insert_flag_candidate_carries_the_four_readings(monkeypatch):
    """Runs the ACTUAL `db.insert_flag_candidate` against a mocked asyncpg connection and reads
    back what it sent: the INSERT names all four columns, the ON CONFLICT clause updates all
    four (a re-scan must not leave a stale reading), and the four sentinel values arrive as the
    last four positional parameters ($37–$40), in column order."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    sentinel = {"depth_on_low": 0.728, "depth_on_close": 0.7547,
                "sma20_margin": -0.00035, "ma_stack_margin": -0.00239}
    record = {"ticker": "MRNA", "scan_date": "2026-09-17", "stage": "unqualified",
              "reason": "ma_stack_not_stage2_144.5/144.9/96.6", **sentinel}
    await db.insert_flag_candidate(record)

    conn.execute.assert_awaited_once()
    sql, *params = conn.execute.await_args.args
    insert_cols = sql.split("VALUES")[0]
    on_conflict = sql.split("ON CONFLICT")[1]
    for col in _FOUR:
        assert col in insert_cols, col
        assert f"{col} = EXCLUDED.{col}".replace(" ", "") in on_conflict.replace(" ", ""), col
    assert sql.count("$") == len(params) == 40
    assert params[-4:] == [sentinel[k] for k in _FOUR]
    assert params[0] == "MRNA" and params[1] == date(2026, 9, 17)
