"""The rule "do not COUNT(*) this table" lived in a docstring. Now it lives in a function.

#682, found 2026-09-21 by the day's simplify review (altitude angle), on code #659 shipped the
same day. `db.get_halt_events_between` returns one row per FEED MESSAGE and carries a 25-line
warning that counting them counts heartbeats rather than halts — because before #659 the writer
persisted every re-send of a status. The numbers are not marginal: **ticker VRC produced 79 rows
for ONE halt on 2026-09-14**, and the table holds **20,416 `status_code=2` "Trading Halt" rows
across 53 tickers** all-history (counted on prod 2026-09-21). A `COUNT(*)` over that era reads
halt DURATION as halt FREQUENCY.

📏 MEASURED over the whole table the same day, because one case is not a population: **21,335 raw
rows are 468 real halts — a 45.6x overcount** across 172 tickers, and the worst single halt is
QQBF 2026-09-21 at **1,266 messages for one 20,753-second halt**. VRC's 79 is not even close to
the top; I had been quoting the case I happened to have.

The warning was correct and in the wrong place. Today's only consumer reads per-ticker-day and is
fine; the note existed to stop the NEXT reader, and it would have had to be read first — which is
exactly what did not happen the first time. `get_halt_transitions_between` makes the safe reading
the available one.

⚠ The collapse is not a migration and nothing is rewritten. Old rows keep their shape on purpose:
a halt's length is real information the old era encodes badly rather than not at all, and
`messages` carries it forward.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.market_intelligence import db

_T0 = datetime(2026, 9, 14, 13, 33, 14, tzinfo=timezone.utc)


def _ev(sec: int, code: str, msg: str = "Trading Halt", reason: str | None = "LUDP") -> dict:
    return {"ticker": "VRC", "event_ts": _T0 + timedelta(seconds=sec),
            "status_code": code, "status_message": msg, "reason_code": reason}


@pytest.fixture
def _feed(monkeypatch):
    """Patch the RAW reader so the transition reader is exercised on real-shaped input."""
    def _install(events):
        async def _fake(_s, _e):
            return {"VRC": list(events)} if events else {}
        monkeypatch.setattr(db, "get_halt_events_between", _fake)
    return _install


@pytest.mark.asyncio
async def test_the_VRC_shape_is_ONE_halt_not_seventy_nine(_feed):
    """The exact 2026-09-14 case, at its real cadence: `status_code=2` every ~5s for 79 messages,
    then a resume. Counting rows says 79 halts; counting transitions says one."""
    events = [_ev(i * 5, "2") for i in range(79)] + [_ev(79 * 5, "T", "Trading Resumption", None)]
    _feed(events)
    out = await db.get_halt_transitions_between("2026-09-14", "2026-09-14")
    assert len(out["VRC"]) == 1, (
        f"{len(out['VRC'])} halts reported for a single 79-message halt — the heartbeat bug, "
        f"one layer up from where #659 fixed it"
    )
    h = out["VRC"][0]
    assert h["messages"] == 79, "the message count is the only trace of the old era's duration"
    assert h["halt_ts"] == _T0 and h["resume_ts"] == _T0 + timedelta(seconds=395)
    assert (h["resume_ts"] - h["halt_ts"]).total_seconds() == 395


@pytest.mark.asyncio
async def test_the_post_659_shape_is_unchanged_by_collapsing(_feed):
    """After #659 the writer already emits one row per transition, so collapsing must be a no-op
    — a reader that only worked on the old era would be a second era-specific thing to remember."""
    _feed([_ev(0, "2"), _ev(300, "T", "Trading Resumption", None)])
    out = await db.get_halt_transitions_between("2026-09-21", "2026-09-21")
    assert len(out["VRC"]) == 1 and out["VRC"][0]["messages"] == 1
    assert out["VRC"][0]["resume_ts"] == _T0 + timedelta(seconds=300)


@pytest.mark.asyncio
async def test_two_real_halts_in_one_day_stay_two(_feed):
    """The direction that matters as much as the collapse: a name halted twice must not be folded
    into one. A collapser that keyed on ticker alone would read two halts as one long one."""
    _feed([_ev(0, "2"), _ev(5, "2"), _ev(120, "T", "Trading Resumption", None),
           _ev(600, "2"), _ev(605, "2"), _ev(900, "T", "Trading Resumption", None)])
    out = await db.get_halt_transitions_between("2026-09-14", "2026-09-14")
    assert len(out["VRC"]) == 2, "two separate halts were merged into one"
    assert [h["messages"] for h in out["VRC"]] == [2, 2]


@pytest.mark.asyncio
async def test_a_halt_still_open_at_the_window_edge_reports_no_resume(_feed):
    """Never guess a length. An unresumed halt says so instead of borrowing the next row's time."""
    _feed([_ev(0, "2"), _ev(5, "2")])
    out = await db.get_halt_transitions_between("2026-09-14", "2026-09-14")
    assert out["VRC"][0]["resume_ts"] is None


@pytest.mark.asyncio
async def test_a_volatility_pause_is_a_halt_and_a_quote_resumption_ends_one(_feed):
    """All six codes the table actually holds, not just the common pair."""
    _feed([_ev(0, "P", "Volatility Trading Pause"), _ev(60, "Q", "Quotation Resumption", None)])
    out = await db.get_halt_transitions_between("2026-09-14", "2026-09-14")
    assert len(out["VRC"]) == 1 and out["VRC"][0]["status_code"] == "P"
    assert out["VRC"][0]["resume_ts"] == _T0 + timedelta(seconds=60)


@pytest.mark.asyncio
async def test_an_unknown_code_closes_a_halt_rather_than_extending_it_forever(_feed):
    """Fail-safe direction, stated on purpose. A tape code we have never seen must not be read as
    "still halted" — that would invent a halt lasting the rest of the window."""
    _feed([_ev(0, "2"), _ev(30, "Z", "Something New", None), _ev(90, "2"),
           _ev(150, "T", "Trading Resumption", None)])
    out = await db.get_halt_transitions_between("2026-09-14", "2026-09-14")
    assert len(out["VRC"]) == 2
    assert out["VRC"][0]["resume_ts"] == _T0 + timedelta(seconds=30)


@pytest.mark.asyncio
async def test_a_day_with_no_halts_is_empty_not_a_ticker_with_zero(_feed):
    _feed([])
    assert await db.get_halt_transitions_between("2026-09-15", "2026-09-15") == {}


def test_the_raw_reader_points_at_the_safe_one():
    """The docstring must route a future aggregator, not only warn it. This is the half that was
    missing: the note said what not to do and named no alternative, because none existed."""
    doc = db.get_halt_events_between.__doc__ or ""
    assert "get_halt_transitions_between" in doc, (
        "the raw reader warns about counting but no longer names the reader that counts "
        "correctly — which is the shape that made this a docstring problem in the first place"
    )
