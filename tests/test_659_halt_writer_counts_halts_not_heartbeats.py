"""#659 — `mi_halt_status_events` must count HALTS, not feed heartbeats.

FOUND closing #488 on 2026-09-14: ticker VRC produced **79 rows for ONE halt** — `status_code=2`
/ `Trading Halt`, one every ~5 seconds from 13:33:14Z — because `_handle_trading_status` wrote on
every status message the feed repeated rather than on a status TRANSITION.

⚠ WHY THAT WAS DANGEROUS RATHER THAN MERELY UNTIDY, and it is the whole point: every one of the
79 rows was individually ACCURATE. Nothing was wrong with any single row. The defect lived in
what a READER would conclude — any count over this table reads halt DURATION as halt FREQUENCY,
and the #488 dead-data-guard compare is exactly such a reader. A correct row in a shape that
makes the obvious query wrong is worse than a wrong row, because nothing looks broken.

⚠ DURATION IS NOT LOST. One row on entry plus one on the resume transition encodes length as
`resume_ts - halt_ts`, instead of an implicit row-count times an assumed feed cadence. The task
line warns against dropping the historical repeats retroactively for exactly this reason — the
old rows keep their old shape, and readers must know which era they are reading.

⚖ Shadow writer only — no money path, no detection criterion.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence.broker import halt_status_shadow as H


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    H._reset_status_cache()
    monkeypatch.setattr(
        "agents.market_intelligence.execution_client.get_data_feed_name", lambda: "test", raising=False)
    yield
    H._reset_status_cache()


def _writes(monkeypatch) -> list[dict]:
    got: list[dict] = []

    async def _fake_insert(**kw):
        got.append(kw)

    monkeypatch.setattr("agents.market_intelligence.db.insert_halt_status_event",
                        _fake_insert, raising=False)
    return got


def _msg(sym="VRC", code=2, msg="Trading Halt", ts="2026-09-14T13:33:14Z"):
    return {"symbol": sym, "status_code": code, "status_message": msg, "timestamp": ts,
            "reason_code": "LUDP", "reason_message": "Volatility", "tape": "C"}


@pytest.mark.asyncio
async def test_one_halt_repeated_by_the_feed_writes_ONE_row(monkeypatch):
    """THE REGRESSION, at the real observed scale: VRC's 79 messages were one halt."""
    got = _writes(monkeypatch)
    for i in range(79):
        await H._handle_trading_status(_msg(ts=f"2026-09-14T13:{33 + i // 12:02d}:14Z"))
    assert len(got) == 1, (
        f"{len(got)} rows for ONE halt — the writer is counting feed heartbeats again, and any "
        f"count over mi_halt_status_events will read duration as frequency."
    )
    assert got[0]["ticker"] == "VRC" and got[0]["status_code"] == 2


@pytest.mark.asyncio
async def test_the_resume_transition_DOES_write(monkeypatch):
    """Dedupe must not swallow the state change — without the resume row there is no duration."""
    got = _writes(monkeypatch)
    for _ in range(5):
        await H._handle_trading_status(_msg(code=2, msg="Trading Halt"))
    for _ in range(5):
        await H._handle_trading_status(_msg(code=3, msg="Resumed"))
    assert [g["status_code"] for g in got] == [2, 3], (
        f"expected exactly one halt row then one resume row, got {[g['status_code'] for g in got]}")


@pytest.mark.asyncio
async def test_two_tickers_do_not_mask_each_other(monkeypatch):
    """The cache is keyed per ticker. A single shared 'last code' would drop VRC's halt because
    AAPL happened to report the same status first."""
    got = _writes(monkeypatch)
    await H._handle_trading_status(_msg(sym="AAPL", code=2))
    await H._handle_trading_status(_msg(sym="VRC", code=2))
    await H._handle_trading_status(_msg(sym="AAPL", code=2))
    assert sorted(g["ticker"] for g in got) == ["AAPL", "VRC"]


@pytest.mark.asyncio
async def test_a_feed_sending_2_and_str_2_is_not_a_transition(monkeypatch):
    """A type change is not a state change. Without normalising, alternating int/str codes would
    write a row on every single message — the original bug wearing a different hat."""
    got = _writes(monkeypatch)
    for code in (2, "2", 2, "2", 2):
        await H._handle_trading_status(_msg(code=code))
    assert len(got) == 1, f"{len(got)} rows from one halt reported as int and str"


@pytest.mark.asyncio
async def test_a_write_failure_is_still_swallowed(monkeypatch):
    """The shadow-only contract is unchanged: this handler runs on the same dispatch loop that
    delivers ORB bars, so it must never raise. Pinned because the dedupe added an early return
    and a future edit could restructure the try block around it."""
    async def _boom(**kw):
        raise RuntimeError("db down")
    monkeypatch.setattr("agents.market_intelligence.db.insert_halt_status_event",
                        _boom, raising=False)
    await H._handle_trading_status(_msg())      # must not raise


@pytest.mark.asyncio
async def test_a_message_with_no_symbol_is_dropped_before_the_cache(monkeypatch):
    got = _writes(monkeypatch)
    await H._handle_trading_status({"status_code": 2})
    assert got == []
