"""A split re-fetch must cover the ticker's WHOLE stored history, not a fixed 250 days.

2026-09-24: the five-year reload put ~1,260 sessions per ticker in mi_daily_closes while
`_apply_one` re-fetched only 250 calendar days on a split — so every older row stayed in
pre-split units and the series carried a cliff (QH read in the tens of thousands before
2025-11-10). These tests pin the window to the earliest stored row.
"""
import asyncio
from datetime import date, timedelta

from agents.market_intelligence import splits_ingest as si


class _Conn:
    def __init__(self, earliest):
        self.earliest = earliest

    async def fetchval(self, sql, *args):
        assert "min(trade_date)" in sql
        return self.earliest


class _Pool:
    def __init__(self, earliest):
        self.conn = _Conn(earliest)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def _patch(monkeypatch, earliest, today=date(2026, 9, 24)):
    import agents.market_intelligence.db as db

    async def _get_pool():
        return _Pool(earliest)
    monkeypatch.setattr(db, "get_pool", _get_pool)
    monkeypatch.setattr(si, "et_today", lambda: today)


def test_window_reaches_the_earliest_stored_row(monkeypatch):
    earliest = date(2021, 9, 27)
    _patch(monkeypatch, earliest)
    days = asyncio.run(si._stored_history_days("QH"))
    assert date(2026, 9, 24) - timedelta(days=days) <= earliest
    assert days > si.HISTORY_DAYS


def test_short_history_keeps_the_minimum_window(monkeypatch):
    _patch(monkeypatch, date(2026, 8, 1))
    assert asyncio.run(si._stored_history_days("NEWCO")) == si.HISTORY_DAYS


def test_no_rows_keeps_the_minimum_window(monkeypatch):
    _patch(monkeypatch, None)
    assert asyncio.run(si._stored_history_days("NONE")) == si.HISTORY_DAYS


def test_apply_one_requests_the_stored_history_window(monkeypatch):
    """The call site, not just the helper: `_apply_one` must pass the stored-history window."""
    earliest = date(2021, 9, 27)
    _patch(monkeypatch, earliest)
    seen = {}

    async def _fetch(ticker, days=si.HISTORY_DAYS):
        seen["days"] = days
        return []   # no bars → the skip branch; the window is what is under test

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(si, "fetch_ticker_history", _fetch)
    monkeypatch.setattr(si, "log_audit_event", _noop)
    monkeypatch.setattr(si, "mark_split_applied", _noop)
    asyncio.run(si._apply_one({"ticker": "QH", "execution_date": date(2026, 7, 1),
                               "split_from": 1, "split_to": 10}))
    assert date(2026, 9, 24) - timedelta(days=seen["days"]) <= earliest


def test_split_pagination_sends_the_cursor_as_a_param_and_stops_on_a_repeat(monkeypatch):
    """2026-09-24: next_url passed as the PATH lost its cursor (httpx `params=` replaces a URL's own
    query string), so page 2 was Polygon's unfiltered default with its own next_url — forever."""
    calls = []
    pages = {
        None: {"results": [{"ticker": "A"}], "next_url": "https://api.polygon.io/v3/reference/splits?cursor=C1&apiKey=k"},
        "C1": {"results": [{"ticker": "B"}], "next_url": "https://api.polygon.io/v3/reference/splits?cursor=C2&apiKey=k"},
        "C2": {"results": [{"ticker": "C"}]},
    }

    async def _get(path, params=None):
        calls.append((path, dict(params or {})))
        assert path == "/v3/reference/splits"
        return pages[(params or {}).get("cursor")]
    monkeypatch.setattr(si, "_polygon_get", _get)
    out = asyncio.run(si.fetch_splits(date(2025, 8, 18)))
    assert [r["ticker"] for r in out] == ["A", "B", "C"]
    assert [c[1].get("cursor") for c in calls] == [None, "C1", "C2"]

    loop = {"results": [{"ticker": "X"}], "next_url": "https://api.polygon.io/v3/reference/splits?cursor=SAME&apiKey=k"}

    async def _loop(path, params=None):
        calls.append(params)
        return loop
    calls.clear()
    monkeypatch.setattr(si, "_polygon_get", _loop)
    asyncio.run(si.fetch_splits(date(2025, 8, 18)))
    assert len(calls) == 2   # first page + one follow; the repeated cursor stops it


# ═══ #704: the ingest RECORDS what it decided - and applies exactly what it applied before ═════════════════
#
# `_apply_one` stays behaviour-neutral for the bars: the same list object reaches `upsert_ticker_history`, the same
# tuple comes back, the same audit events fire. What is new is only the keyword arguments on `mark_split_applied`.
import copy
from datetime import datetime, timezone

import pytest


def _epoch_ms(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _bars(close_pre, exec_date=date(2026, 7, 2)):
    """Polygon's adjusted=true history around a split: a few pre-split bars (the last, 07-01, closes `close_pre`) and
    the split day itself. Shape is Polygon's aggregates: t (epoch ms), o/h/l/c/v."""
    out = []
    for k, d in enumerate([date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), exec_date]):
        c = close_pre if d == date(2026, 7, 1) else close_pre * (1.0 + 0.01 * k)
        out.append({"t": _epoch_ms(d), "o": c, "h": c * 1.02, "l": c * 0.98, "c": c, "v": 1000 * (k + 1)})
    return out


class _Recorder:
    def __init__(self, monkeypatch, bars, old_close):
        self.upserts, self.marks, self.audits = [], [], []

        async def _fetch(ticker, days=si.HISTORY_DAYS):
            return bars

        async def _hist_days(ticker):
            return si.HISTORY_DAYS

        async def _old(ticker, d):
            return old_close

        async def _upsert(ticker, b):
            self.upserts.append((ticker, b))
            return len(b)

        async def _mark(ticker, exec_date, **kw):
            self.marks.append((ticker, exec_date, kw))

        async def _audit(event, summary, *a, **k):
            self.audits.append(event)
        monkeypatch.setattr(si, "fetch_ticker_history", _fetch)
        monkeypatch.setattr(si, "_stored_history_days", _hist_days)
        monkeypatch.setattr(si, "_get_old_close", _old)
        monkeypatch.setattr(si, "upsert_ticker_history", _upsert)
        monkeypatch.setattr(si, "mark_split_applied", _mark)
        monkeypatch.setattr(si, "log_audit_event", _audit)


def _split(split_from, split_to):
    return {"ticker": "ZZZ", "execution_date": date(2026, 7, 2), "split_from": split_from, "split_to": split_to}


@pytest.mark.parametrize("split_from,split_to,new_close_pre,old_close_pre,want_factor", [
    (1, 4, 187.5, 750.0, 0.25),        # a real FORWARD split: the stored 750 becomes 187.5
    (4, 1, 8.0, 2.0, 4.0),             # a real REVERSE split: the stored 2.00 becomes 8.00
], ids=["forward_1_for_4", "reverse_4_for_1"])
def test_a_real_split_applies_the_same_bars_and_records_applied_with_its_factor(
        monkeypatch, split_from, split_to, new_close_pre, old_close_pre, want_factor):
    bars = _bars(new_close_pre)
    snapshot = copy.deepcopy(bars)
    rec = _Recorder(monkeypatch, bars, old_close_pre)
    out = asyncio.run(si._apply_one(_split(split_from, split_to)))
    assert out == ("ZZZ", True, len(bars))                         # the return value is what it always was
    assert len(rec.upserts) == 1 and rec.upserts[0][0] == "ZZZ"
    assert rec.upserts[0][1] is bars and bars == snapshot          # the bars Polygon returned, written untouched
    assert rec.marks == [("ZZZ", date(2026, 7, 2), {"outcome": "applied", "factor": want_factor})]
    assert rec.audits == ["split_applied"]


def test_a_phantom_split_writes_no_bar_and_records_phantom(monkeypatch):
    bars = _bars(50.2)                                             # Polygon left the history un-adjusted ...
    rec = _Recorder(monkeypatch, bars, 50.0)                       # ... so it matches what is stored (+0.4%)
    out = asyncio.run(si._apply_one(_split(1, 4)))
    assert out == ("ZZZ", False, 0) and rec.upserts == []
    assert rec.marks == [("ZZZ", date(2026, 7, 2), {"outcome": "phantom"})]
    assert rec.audits == ["split_phantom_detected"]


def test_no_bars_from_polygon_writes_nothing_and_records_skipped_no_data(monkeypatch):
    rec = _Recorder(monkeypatch, [], 50.0)
    out = asyncio.run(si._apply_one(_split(1, 4)))
    assert out == ("ZZZ", False, 0) and rec.upserts == []
    assert rec.marks == [("ZZZ", date(2026, 7, 2), {"outcome": "skipped_no_data"})]
    assert rec.audits == ["split_apply_skipped_no_data"]


def test_a_first_ever_apply_with_nothing_stored_to_compare_trusts_polygon_and_records_the_table_ratio(monkeypatch):
    bars = _bars(187.5)
    rec = _Recorder(monkeypatch, bars, None)                       # no stored close for 07-01
    out = asyncio.run(si._apply_one(_split(1, 4)))
    assert out == ("ZZZ", True, len(bars)) and rec.upserts[0][1] is bars
    assert rec.marks[0][2] == {"outcome": "applied", "factor": 0.25}


@pytest.mark.parametrize("old_close,want", [
    (750.0 * 0.9988, 0.25),            # measured 0.2503: within 2% of the table -> the table's ratio, exactly
    (625.0, 0.30),                     # measured 0.30 (20% off the table): the measurement is the truth
], ids=["snaps_to_the_table", "keeps_a_far_off_measurement"])
def test_the_recorded_factor_snaps_to_the_table_only_inside_the_tolerance(monkeypatch, old_close, want):
    rec = _Recorder(monkeypatch, _bars(187.5), old_close)
    asyncio.run(si._apply_one(_split(1, 4)))
    assert rec.marks[0][2]["outcome"] == "applied"
    assert rec.marks[0][2]["factor"] == pytest.approx(want, rel=1e-9)
    assert (rec.marks[0][2]["factor"] == 0.25) is (want == 0.25)    # exact 0.25 only when snapped


def test_a_degenerate_ratio_row_still_applies_recording_must_never_stop_the_apply(monkeypatch):
    """The pre-2026-07-24 truncation class left `split_to = 0` rows. They applied then; they must still apply."""
    bars = _bars(187.5)
    rec = _Recorder(monkeypatch, bars, 750.0)
    out = asyncio.run(si._apply_one(_split(1, 0)))
    assert out == ("ZZZ", True, len(bars)) and rec.upserts[0][1] is bars
    assert rec.marks[0][2]["outcome"] == "applied" and rec.marks[0][2]["factor"] == pytest.approx(0.25)   # the measurement
