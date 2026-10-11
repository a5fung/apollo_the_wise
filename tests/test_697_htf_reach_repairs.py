"""#697 item 1 (2026-10-11) — HTF REACH repairs: the Friday 'Flag Bases' section and the digest's send record.

WHAT WAS BROKEN (docs/analysis/htf_scope_2026-10-10.md §4, gap G7):
  (a) the Friday watchlist's 'Flag Bases' section rendered EMPTY from 2026-08-02. `_fetch_flag` returned
      [] when `should_run("flag_continuation")` was false, and that strategy row was correctly disabled
      on 08-02 — the SAME switch that once silenced the DAILY DETECTOR (tests/test_flag_detector_not_
      strategy_gated.py). The last Friday that carried a FLAG row was 2026-07-31 (prod, q3_friday_flag.out).
  (b) a digest send left no trace anywhere: only a stage TRANSITION wrote a row, so "did we tell him about
      X" could not be answered from prod.
  (c) the same section printed `r1.00` for a base of 5 sessions or fewer — a number that is 1.00 by
      construction there (#598 / wk1010), the Friday copy of a bug already fixed on /flags and the digest.

Display / record only: nothing here touches a stage, threshold, order, entry, sizing or safeguard.
"""
from __future__ import annotations

import json
import re
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import briefing, db
from agents.market_intelligence import flag_detector as fd
from agents.market_intelligence import friday_watchlist as fw
from tests.conftest import make_mock_pool

D1 = date(2026, 8, 18)

# The Friday 2026-10-09 board's only name, as stored (prod, scripts/probes/_697/q3_friday_flag.out):
# KOD, COILED, base 5 sessions -> both ratios are 1.000 by construction; the real tightness is the
# last-two-bars measure 6.639 / 10.533 = 0.63.
KOD = {
    "ticker": "KOD", "stage": "COILED", "base_age": 5, "runup_pct": 1.04,
    "range_contraction_ratio": 1.0, "vol_contraction_ratio": 1.0,
    "breakout_close": None, "base_high": 12.0,
    "fresh_tight_fires": False, "fresh_2bar_tr_pct": 6.639, "atr14_pct": 10.533,
}


def _flag_row(ticker, stage, *, age=12, rr=0.45, vr=0.80, runup=1.30, fires=False, tr=None, atr=None):
    return {
        "ticker": ticker, "stage": stage, "base_age": age, "runup_pct": runup,
        "range_contraction_ratio": rr, "vol_contraction_ratio": vr,
        "breakout_close": None, "base_high": 50.0,
        "fresh_tight_fires": fires, "fresh_2bar_tr_pct": tr, "atr14_pct": atr,
    }


# ── (a) the Friday section no longer reads the retired strategy row ─────────────────────────────

@pytest.mark.asyncio
async def test_fetch_flag_never_consults_the_strategy_registry(monkeypatch):
    """BEHAVIOUR, not source text: every route into the strategy registry raises if touched. A future
    'tidy' that re-adds any registry gate to the section fails here, whatever it is called."""
    from agents.market_intelligence.strategies import registry

    def _touched(*a, **k):
        raise AssertionError("the Friday flag section consulted the strategy registry - a disabled "
                             "flag_continuation row would blank it again, as it did from 2026-08-02")

    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=date(2026, 10, 9))
    conn.fetch = AsyncMock(return_value=[_flag_row("AAA", "COILED")])
    monkeypatch.setattr(fw, "get_pool", AsyncMock(return_value=pool))
    for name in ("should_run", "get_strategy", "load_strategies"):
        monkeypatch.setattr(registry, name, AsyncMock(side_effect=_touched))
    monkeypatch.setattr(fw, "should_run", AsyncMock(side_effect=_touched))
    out = await fw._fetch_flag(7)
    assert [r["ticker"] for r in out] == ["AAA"]


@pytest.fixture
def friday(monkeypatch):
    """The Friday fetch against a fake pool, with the flag_continuation strategy DISABLED."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=date(2026, 10, 9))
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(fw, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(fw, "should_run", AsyncMock(return_value=False))   # deprecated / enabled=false
    return conn


@pytest.mark.asyncio
async def test_section_renders_with_the_strategy_row_disabled(friday):
    """THE regression: the registry says 'flag_continuation' is off; the section still has its names."""
    friday.fetch.return_value = [
        _flag_row("AAA", "COILED"), _flag_row("BBB", "TIGHTENING"), _flag_row("CCC", "TIGHTENING"),
    ]
    out = await fw._fetch_flag(7)
    assert [(r["ticker"], r["source_tag"]) for r in out] == [
        ("AAA", "FLAG"), ("BBB", "FLAG"), ("CCC", "FLAG")]


@pytest.mark.asyncio
async def test_empty_board_is_still_an_empty_section(friday):
    """The positive check is CONDITIONAL on a non-empty board; an empty board stays empty."""
    friday.fetchval.return_value = None
    assert await fw._fetch_flag(7) == []
    friday.fetchval.return_value = date(2026, 10, 9)
    friday.fetch.return_value = []
    assert await fw._fetch_flag(7) == []


@pytest.mark.asyncio
async def test_five_coiled_three_tightening_cap_is_unchanged(friday):
    friday.fetch.return_value = (
        [_flag_row(f"C{i}", "COILED") for i in range(7)] + [_flag_row(f"T{i}", "TIGHTENING") for i in range(5)])
    out = await fw._fetch_flag(7)
    assert [r["ticker"] for r in out] == ["C0", "C1", "C2", "C3", "C4", "T0", "T1", "T2"]


# ── (c) a short base prints the tightness measure that means something, not `r1.00` ─────────────

@pytest.mark.asyncio
async def test_select_pulls_the_three_columns_the_short_base_measure_needs(friday):
    """Without them `board_tightness` prints `tightness n/a` for EVERY short base."""
    await fw._fetch_flag(7)
    sql = friday.fetch.await_args.args[0]
    for col in ("fresh_tight_fires", "fresh_2bar_tr_pct", "atr14_pct"):
        assert col in sql, f"{col} missing from the flag SELECT"


@pytest.mark.asyncio
async def test_friday_2026_10_09_kod_renders_the_two_bar_measure_not_r_1_00(friday):
    """The real stored row from the last Friday: base 5, ratios 1.000 / 1.000."""
    friday.fetch.return_value = [dict(KOD)]
    (row,) = await fw._fetch_flag(7)
    assert row["reason"] == "COILED · base 5d · runup +104% · last 2 bars 0.63× usual range"
    assert "r1.00" not in row["reason"] and "v1.00" not in row["reason"]


@pytest.mark.asyncio
async def test_short_base_with_a_firing_fresh_path_says_tight(friday):
    friday.fetch.return_value = [_flag_row("AAA", "TIGHTENING", age=4, rr=1.0, vr=1.0, fires=True, tr=3.0, atr=6.0)]
    (row,) = await fw._fetch_flag(7)
    assert row["reason"] == "TIGHTENING · base 4d · last 2 bars tight (0.50× usual range)"


@pytest.mark.asyncio
async def test_short_base_with_no_atr_says_n_a_rather_than_1_00(friday):
    friday.fetch.return_value = [_flag_row("AAA", "COILED", age=3, rr=1.0, vr=1.0)]
    (row,) = await fw._fetch_flag(7)
    assert row["reason"].endswith("tightness n/a")
    assert "1.00" not in row["reason"]


@pytest.mark.asyncio
async def test_a_base_of_six_or_more_keeps_the_real_ratios(friday):
    """Six sessions is where the first-5 / last-5 windows stop being the same bars."""
    friday.fetch.return_value = [
        _flag_row("AAA", "COILED", age=6, rr=0.45, vr=0.80, runup=1.20),
        _flag_row("BBB", "TIGHTENING", age=9, rr=0.62, vr=0.91),
    ]
    a, b = await fw._fetch_flag(7)
    assert a["reason"] == "COILED · base 6d · runup +120% · r0.45 v0.80"
    assert b["reason"] == "TIGHTENING · base 9d · r0.62 v0.91"


# ── (b) one `flag_digest_sent` audit row per digest send ────────────────────────────────────────

def _row(ticker, stage, *, runup=1.30, pivot=49.76, rr=0.95, vr=0.65, age=10, **extra):
    return {"ticker": ticker, "stage": stage, "runup_pct": runup, "pivot_high_price": pivot,
            "range_contraction_ratio": rr, "vol_contraction_ratio": vr, "base_age": age,
            "fresh_tight_fires": False, "reason": None, **extra}


def _board(*rows):
    out = {s: [] for s in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH", "INVALIDATED", "unqualified")}
    for r in rows:
        out[r["stage"]].append(r)
    return out


class _World:
    def __init__(self):
        self.sent: list[tuple[str, object]] = []
        self.audit: list[tuple[str, str, str]] = []
        self.telegram_ok = True


@pytest.fixture
def world(monkeypatch):
    w = _World()

    async def _send(text, chat_id=None, parse_mode=None, reply_markup=None):
        w.sent.append((text, parse_mode))
        return w.telegram_ok

    async def _audit(event_type, summary, detail="", *, conn=None):
        w.audit.append((event_type, summary, detail))

    pool, conn = make_mock_pool()

    async def _fetch(sql, event_type, keys):      # the transition dedupe lookup
        return [{"summary": s} for (ev, s, _d) in w.audit if ev == event_type and s in keys]

    conn.fetch = AsyncMock(side_effect=_fetch)
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    monkeypatch.setattr(db, "log_audit_event", _audit)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    return w


def _digest_rows(w):
    return [a for a in w.audit if a[0] == "flag_digest_sent"]


def _codes(text):
    return set(re.findall(r"<code>([A-Z0-9]+)</code>", text))


@pytest.mark.asyncio
async def test_a_send_writes_one_row_listing_the_tickers_per_section(world):
    board = _board(
        _row("NEW1", "TIGHTENING"), _row("NEW2", "COILED", rr=0.6, vr=0.5),
        _row("OLD1", "COILED", rr=0.5, vr=0.5), _row("TRG1", "TRIGGERED", breakout_close=51.0, base_high=50.0,
                                                    breakout_volume_ratio=2.1),
        _row("DROP", "INVALIDATED"), _row("W1", "WATCH"),
    )
    await fd.send_flag_digest(board, D1, yesterday_map={"NEW1": "WATCH", "NEW2": "TIGHTENING", "OLD1": "COILED"})
    assert len(world.sent) == 1
    (row,) = _digest_rows(world)
    assert row[1] == "flag digest 2026-08-18 (sent)"
    d = json.loads(row[2])
    assert d["scan_date"] == "2026-08-18" and d["telegram"] == "sent"
    assert sorted(d["new_today"]) == ["NEW1", "NEW2"]
    assert d["triggered"] == ["TRG1"]
    assert d["coiled"] == ["OLD1"]                 # NEW2 is listed under NEW TODAY, not the roster
    assert d["coiled_not_shown"] == []
    assert d["dropped_out"] == 1


@pytest.mark.asyncio
async def test_the_record_matches_the_message_ticker_for_ticker(world):
    """The record is worthless if it can drift from what was sent: every ticker the message names is in
    exactly the sections the row names, and nothing the row names is missing from the message."""
    board = _board(_row("NEW1", "TIGHTENING"), _row("OLD1", "COILED", rr=0.5, vr=0.5),
                   _row("TRG1", "TRIGGERED", breakout_close=51.0, base_high=50.0, breakout_volume_ratio=2.1))
    await fd.send_flag_digest(board, D1, yesterday_map={"NEW1": "WATCH", "OLD1": "COILED"})
    text = world.sent[0][0]
    d = json.loads(_digest_rows(world)[0][2])
    listed = set(d["new_today"]) | set(d["triggered"]) | set(d["coiled"])
    assert listed == _codes(text) == {"NEW1", "OLD1", "TRG1"}


@pytest.mark.asyncio
async def test_a_failed_telegram_still_writes_the_row_marked_not_delivered(world):
    world.telegram_ok = False
    await fd.send_flag_digest(_board(_row("OLD1", "COILED", rr=0.5, vr=0.5)), D1, yesterday_map={"OLD1": "COILED"})
    (row,) = _digest_rows(world)
    assert row[1] == "flag digest 2026-08-18 (not delivered)"
    assert json.loads(row[2])["telegram"] == "not delivered"
    assert json.loads(row[2])["coiled"] == ["OLD1"]


@pytest.mark.asyncio
async def test_a_suppressed_quiet_day_writes_no_row(world):
    """No send, no row: the DoD counts rows = sends."""
    await fd.send_flag_digest(_board(_row("W1", "WATCH"), _row("DROP", "INVALIDATED")), D1, yesterday_map={})
    assert world.sent == [] and _digest_rows(world) == []


@pytest.mark.asyncio
async def test_roster_truncation_is_visible_in_the_record(world):
    """Only 8 standing COILED names are printed ('…N more'); 'did we tell him about X' is only answerable
    if the 3 that were NOT shown are named too."""
    names = [f"C{i:02d}" for i in range(11)]
    board = _board(*[_row(n, "COILED", rr=0.40 + i * 0.01, vr=0.5) for i, n in enumerate(names)])
    await fd.send_flag_digest(board, D1, yesterday_map={n: "COILED" for n in names})
    text = world.sent[0][0]
    d = json.loads(_digest_rows(world)[0][2])
    assert d["coiled"] == names[:8] and d["coiled_not_shown"] == names[8:]
    assert _codes(text) == set(names[:8])
    assert "3 more" in text


@pytest.mark.asyncio
async def test_a_broken_transition_step_does_not_lose_the_send_record(world, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("transition step broke")
    monkeypatch.setattr(fd, "stage_transitions", _boom)
    await fd.send_flag_digest(_board(_row("OLD1", "COILED", rr=0.5, vr=0.5)), D1, yesterday_map={})
    assert len(world.sent) == 1
    (row,) = _digest_rows(world)
    assert json.loads(row[2])["coiled"] == ["OLD1"]
    assert [a for a in world.audit if a[0] == "flag_stage_transition_error"]


@pytest.mark.asyncio
async def test_a_rerun_of_the_same_scan_is_a_second_row_not_a_dedupe(world):
    """A #672 recovery re-run sends a second message; the record says so (the summary carries the SCAN
    date, the audit row its own timestamp) instead of silently eating it."""
    board = _board(_row("OLD1", "COILED", rr=0.5, vr=0.5))
    await fd.send_flag_digest(board, D1, yesterday_map={"OLD1": "COILED"})
    await fd.send_flag_digest(board, D1, yesterday_map={"OLD1": "COILED"})
    assert len(world.sent) == 2 and len(_digest_rows(world)) == 2


@pytest.mark.asyncio
async def test_a_failing_audit_write_never_breaks_the_scan(world, monkeypatch):
    async def _raises(*a, **k):
        raise RuntimeError("audit down")
    monkeypatch.setattr(db, "log_audit_event", _raises)
    # must not raise: the digest already reached the operator
    await fd.send_flag_digest(_board(_row("OLD1", "COILED", rr=0.5, vr=0.5)), D1, yesterday_map={"OLD1": "COILED"})
    assert len(world.sent) == 1


@pytest.mark.asyncio
async def test_a_record_build_failure_is_named_by_the_error_event_and_never_breaks_the_scan(world, monkeypatch):
    """What `flag_digest_sent_error` actually means (review fix 2026-10-11): the record could not be BUILT (the detail
    JSON), not that the audit INSERT failed - `db.log_audit_event` swallows its own errors and never raises, so a
    failed write leaves only a logged warning and the MISSING `flag_digest_sent` row is the signal."""
    def _boom(*a, **k):
        raise TypeError("detail JSON could not be built")
    monkeypatch.setattr(fd, "_digest_record", _boom)
    await fd.send_flag_digest(_board(_row("OLD1", "COILED", rr=0.5, vr=0.5)), D1, yesterday_map={"OLD1": "COILED"})
    assert len(world.sent) == 1                       # the digest still went out
    assert _digest_rows(world) == []                  # no send record...
    (err,) = [a for a in world.audit if a[0] == "flag_digest_sent_error"]
    assert "TypeError" in err[1]                      # ...and the error row names why


def test_build_flag_digest_is_still_pure_and_unchanged_in_signature():
    """test_598 calls it directly; the record helper is additive."""
    msg = fd.build_flag_digest(_board(_row("OLD1", "COILED", rr=0.5, vr=0.5)), D1, [])
    assert msg and "OLD1" in msg
