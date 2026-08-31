"""#606 (2026-08-31) — D-1 universe floor dollar-volume shadow.

WHY THIS EXISTS. docs/analysis/606_d1_floor_2026-08-31.md found the live D-1
universe floor (prior close >= $5 AND prior-day volume >= 50,000 shares) has a
weaker SHAPE than a single dollar-volume floor, but only 5 trading days of
evidence — not enough to change a live detection criterion (THE LINE). This
records the comparison beside the acting floor so evidence accrues at full
scan speed. universe_floor_shadow.py owns the row shape (pure, no I/O);
db.py owns the INSERT (agents/market_intelligence/db.py's
insert_universe_floor_shadow_rows).

MUTATION DISCIPLINE (operator, repeated): every assertion below is on
BEHAVIOUR (the returned dict's values, the exact SQL sent, the exact call
count) — never on a comment or docstring string.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import universe_floor_shadow as ufs
from agents.market_intelligence import db
from agents.market_intelligence import ep_detector

_PRICE_FLOOR = 5.0
_VOLUME_FLOOR = 50_000


# ── build_universe_floor_shadow_row: the pure row-shape (mock-free) ──────────


def test_computes_dollar_volume_as_price_times_volume():
    row = ufs.build_universe_floor_shadow_row(
        "DAIC", 3.0, 5_000_000, 12.0, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    assert row["prev_day_dollar_volume"] == 3.0 * 5_000_000


def test_flags_price_floor_failure_only():
    row = ufs.build_universe_floor_shadow_row(
        "CELU", 3.50, 200_000, 15.0, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    assert row["failed_price_floor"] is True
    assert row["failed_volume_floor"] is False


def test_flags_volume_floor_failure_only():
    row = ufs.build_universe_floor_shadow_row(
        "PMI", 12.0, 10_000, 15.0, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    assert row["failed_price_floor"] is False
    assert row["failed_volume_floor"] is True


def test_flags_both_floors_independently_when_both_fail():
    """MUTATION TARGET: `_universe_floor_skip`'s reason string reports only the
    FIRST floor a ticker hits (price checked before volume, via if/elif) — a
    name failing BOTH would silently read as failing only the price floor if
    this function were written the same way (copy-paste of that early-return
    shape). A ticker priced under $5 trading under 50k shares must show BOTH
    flags True, independently computed.
    MUTATION RESULT (verified by hand): changing failed_volume_floor to
    short-circuit off failed_price_floor (`False if <price fails> else
    <volume check>`) flips exactly this test — everything else in this file
    stays green."""
    row = ufs.build_universe_floor_shadow_row(
        "JUNK", 2.00, 10_000, 20.0, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    assert row["failed_price_floor"] is True
    assert row["failed_volume_floor"] is True


def test_flags_neither_when_both_floors_pass():
    row = ufs.build_universe_floor_shadow_row(
        "ETON", 20.0, 500_000, 9.5, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    assert row["failed_price_floor"] is False
    assert row["failed_volume_floor"] is False


def test_missing_prev_close_yields_null_dollar_volume_and_fails_price_floor():
    row = ufs.build_universe_floor_shadow_row(
        "XXXX", None, 500_000, 20.0, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    assert row["prev_day_dollar_volume"] is None
    assert row["failed_price_floor"] is True


def test_stamps_the_acting_floor_values_it_was_given_verbatim():
    """A future reader must never infer the acting floor from a date — the row
    carries whatever values the caller (ep_detector.py, reading its own live
    constants) passed in, not a value this function invents."""
    row = ufs.build_universe_floor_shadow_row(
        "ETON", 20.0, 500_000, 9.5, 4.25, 60_000, date(2026, 8, 31))
    assert row["acting_price_floor"] == 4.25
    assert row["acting_volume_floor"] == 60_000


def test_carries_the_single_tick_reading_the_writer_reconciles():
    """The pure builder hands over exactly what THIS tick saw — reconciling
    into first/at_open/last observation slots is db.py's job (ON CONFLICT),
    not this function's."""
    row = ufs.build_universe_floor_shadow_row(
        "ETON", 20.0, 500_000, 9.5, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31),
        minutes_since_open=5, seen_et=datetime(2026, 8, 31, 9, 35))
    assert row["gap_pct"] == 9.5
    assert row["minutes_since_open"] == 5
    assert row["seen_et"] == datetime(2026, 8, 31, 9, 35)


def test_never_stores_a_hypothetical_threshold_verdict():
    """#583 stale-derived-value class: the row must hold RAW INPUTS + facts
    about the ALREADY-ACTING floor only — never a verdict against some
    not-yet-chosen dollar-volume level (that would go stale the moment a
    level is swept)."""
    row = ufs.build_universe_floor_shadow_row(
        "ETON", 20.0, 500_000, 9.5, _PRICE_FLOOR, _VOLUME_FLOOR, date(2026, 8, 31))
    banned_substrings = ("passes_", "admit", "verdict", "would_")
    for key in row:
        low = key.lower()
        assert not any(b in low for b in banned_substrings), \
            f"column {key!r} looks like a stored verdict against a swept level"


# ── insert_universe_floor_shadow_rows (db.py): the batch writer ─────────────


_ROW = {
    "scan_date": date(2026, 8, 31), "ticker": "DAIC", "seen_et": datetime(2026, 8, 31, 9, 35),
    "gap_pct": 34.0, "minutes_since_open": 5, "prev_close": 3.0, "prev_day_volume": 5_000_000,
    "prev_day_dollar_volume": 15_000_000.0, "failed_price_floor": False,
    "failed_volume_floor": False, "acting_price_floor": 5.0, "acting_volume_floor": 50_000,
}


@pytest.mark.asyncio
async def test_writer_writes_only_the_shadow_table(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    executed = []

    async def _executemany(sql, argrows):
        executed.append((sql, argrows))
    conn.executemany = _executemany
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    n = await db.insert_universe_floor_shadow_rows([_ROW])
    assert n == 1 and len(executed) == 1
    sql, argrows = executed[0]
    assert "INSERT INTO mi_universe_floor_shadow" in sql
    assert "ON CONFLICT (scan_date, ticker) DO UPDATE" in sql
    assert "mi_ep_alerts" not in sql and "mi_live_trades" not in sql
    assert argrows[0][1] == "DAIC"


@pytest.mark.asyncio
async def test_writer_never_freezes_a_faded_premarket_print():
    """The #595 class this design exists to avoid: ON CONFLICT must be DO
    UPDATE, not DO NOTHING, so a later post-open tick can still be recovered
    via gap_pct_at_open / minutes_since_open_at_open even when the ticker's
    FIRST tick was pre-market."""
    src = inspect.getsource(db.insert_universe_floor_shadow_rows)
    assert "ON CONFLICT (scan_date, ticker) DO NOTHING" not in src
    assert "DO UPDATE SET" in src
    assert "gap_pct_at_open" in src and "minutes_since_open_at_open" in src
    assert "COALESCE(" in src  # at_open is set once, never overwritten


@pytest.mark.asyncio
async def test_writer_batches_many_rows_into_one_round_trip(monkeypatch):
    """The latency guard this card cares about: the floor's rejects alone run
    ~700/week — this must be ONE executemany call regardless of row count,
    never one execute() per row."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    calls = []

    async def _executemany(sql, argrows):
        calls.append(argrows)
    conn.executemany = _executemany
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    rows = [{**_ROW, "ticker": f"T{i}"} for i in range(50)]
    n = await db.insert_universe_floor_shadow_rows(rows)
    assert n == 50
    assert len(calls) == 1  # exactly one round trip
    assert len(calls[0]) == 50


@pytest.mark.asyncio
async def test_writer_is_fail_open_on_pool_failure(monkeypatch):
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    n = await db.insert_universe_floor_shadow_rows([_ROW])
    assert n == 0  # never raises — telemetry must never jeopardize the scan


@pytest.mark.asyncio
async def test_writer_empty_inputs_is_a_noop():
    assert await db.insert_universe_floor_shadow_rows([]) == 0


@pytest.mark.asyncio
async def test_record_universe_floor_shadow_delegates_to_db(monkeypatch):
    """universe_floor_shadow.py is the table's single writer but the SQL lives
    in db.py — this pins the delegation itself."""
    called = {}

    async def _fake_insert(rows):
        called["rows"] = rows
        return len(rows)
    monkeypatch.setattr(ufs, "insert_universe_floor_shadow_rows", _fake_insert)
    n = await ufs.record_universe_floor_shadow([_ROW])
    assert n == 1 and called["rows"] == [_ROW]


def test_ddl_stores_raw_inputs_never_computed_verdicts():
    db_src = inspect.getsource(db)
    assert "CREATE TABLE IF NOT EXISTS mi_universe_floor_shadow" in db_src
    ddl = db_src.split("CREATE TABLE IF NOT EXISTS mi_universe_floor_shadow", 1)[1]
    ddl = ddl.split(");", 1)[0]
    for col in ("scan_date", "ticker", "gap_pct_first", "gap_pct_at_open", "gap_pct_last",
                "minutes_since_open_first", "minutes_since_open_at_open", "minutes_since_open_last",
                "prev_close", "prev_day_volume", "prev_day_dollar_volume",
                "failed_price_floor", "failed_volume_floor",
                "acting_price_floor", "acting_volume_floor"):
        assert col in ddl, f"missing raw-input column {col!r}"
    for banned in ("dollar_volume_tier", "passes_floor", "verdict"):
        assert banned not in ddl


# ── wiring inside run_ep_scan (test_570 source-inspection pattern) ──────────


def _scan_src() -> str:
    return inspect.getsource(ep_detector.run_ep_scan)


def test_run_ep_scan_records_the_shadow_row_on_both_reject_branches_and_admit():
    src = _scan_src()
    n = src.count("build_universe_floor_shadow_row(")
    assert n >= 3, (
        "expected a call at the close-floor branch, the volume-floor branch, "
        "and the admitted-candidate site (both directions of the comparison)"
    )


def test_admitted_side_shadow_call_cannot_un_admit_a_candidate():
    """THE LINE guard: the shadow append for an ADMITTED candidate must sit
    AFTER candidates.append (so a raise in the shadow builder can never drop a
    real candidate from admission) and be its own try/except (so the loop's
    outer except can't turn a telemetry bug into a dropped ticker either)."""
    src = _scan_src()
    append_idx = src.index("candidates.append(_snap_candidate(")
    admit_shadow_idx = src.index("build_universe_floor_shadow_row(", append_idx)
    assert admit_shadow_idx > append_idx, \
        "the admitted-side shadow call must come AFTER candidates.append"
    window = src[append_idx:admit_shadow_idx]
    assert "try:" in window  # the shadow append is wrapped, not bare
    after = src[admit_shadow_idx:admit_shadow_idx + 400]
    assert "except Exception" in after and "logger.warning" in after, \
        "a caught failure here must be logged, not a bare silent pass (no-silent-failures gate)"


def test_universe_floor_shadow_write_is_fire_and_forget_not_blocking():
    """Latency guard: the write must not sit in the scan's own await chain —
    it is dispatched via asyncio.create_task with a strong ref (the
    _WATCHDOG_BG_TASKS idiom), never `await record_universe_floor_shadow(`."""
    src = _scan_src()
    assert "await record_universe_floor_shadow(" not in src
    idx = src.index("record_universe_floor_shadow(_dv_floor_shadow_rows)")
    window = src[max(0, idx - 200):idx]
    assert "asyncio.create_task(" in window
    assert "_WATCHDOG_BG_TASKS.add" in src[idx:idx + 200]
