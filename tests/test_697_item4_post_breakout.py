"""#697 item 4 (htf_scope G3, 2026-10-16) - the board no longer forgets a flag the night it breaks out.

THE PROBLEM. When a name CLOSES above the pole top of a formed flag, the next scan re-anchors the pivot on the
breakout bar and the row reads a bare `base_age_0_below_3` - no state says "broke out of a flag N days ago"
(CDNA 08-26, MRNA 09-23; 11 pushable ticker-days in 60, `docs/analysis/htf_scope_2026-10-10.md` G3).

THE CHANGE (telemetry only): two nullable columns on `mi_flag_candidates` -
  post_breakout_from   the date of the OLD pivot / pole-high bar the name broke out of
  days_since_breakout  trading sessions from the breakout bar (the first close above that pole top once the flag
                       had >= 3 sessions of base) to this scan; 1 = the first row after the breakout bar
set on the rows after the re-anchor and carried for `_PIVOT_LOOKBACK_DAYS` (25) sessions, NULL otherwise.

NO STAGE RULE MOVES. The strongest proof is the `*_equivalence` tests: every corpus member replayed with the real
computation and with it switched off produces the SAME value in every other field of every row. The
before/after-the-commit proof (7,586 replayed rows, byte-identical) is `scripts/probes/_697_item4/`.

Real bars: the labelled corpus (`tests/fixtures/htf_labelled_bars.psv`) plus MRNA 09-18 -> 10-09
(`tests/fixtures/htf_post_breakout_bars.psv`, lifted from the committed prod capture
`scripts/probes/_697/q6_extra_bars.out`; the corpus file itself is NOT touched - other tests pin MRNA's last bar
at 09-17). The replay threads state the way `run_flag_scan` does (`scripts/probes/_697_item4/replay_equiv.py`).
"""
from __future__ import annotations

import importlib.util
import re
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool
from tests.test_697_one_day_hold import table  # noqa: F401  (the in-memory mi_flag_candidates fixture)
from tests.test_htf_criteria import _htf_rows, _pole_top, _row

_ROOT = Path(__file__).resolve().parents[1]
_NEW_KEYS = ("post_breakout_from", "days_since_breakout")


def _harness():
    spec = importlib.util.spec_from_file_location(
        "replay_equiv_697_item4", _ROOT / "scripts" / "probes" / "_697_item4" / "replay_equiv.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _harness()


@pytest.fixture(scope="module")
def corpus_bars():
    """The labelled corpus + MRNA's extension (09-18 -> 10-09), as {ticker: [bars]}."""
    bars = R.load_corpus()
    ext = [ln.split("|") for ln in (_ROOT / "tests" / "fixtures" / "htf_post_breakout_bars.psv").read_text().splitlines()
           if ln.strip()]
    for t, d, o, h, lo, c, v in ext:
        bars[t].append(R._bar(d, o, h, lo, c, v))
    return {t: sorted(b, key=lambda r: r["trade_date"]) for t, b in bars.items()}


@pytest.fixture(scope="module")
def replays(corpus_bars):
    return {t: R.replay(t, b) for t, b in corpus_bars.items()}


# ── 1. the geometry, on synthetic bars ──────────────────────────────────────────────────────────────────────────

def _flag_then_breakout(n_flag=8, runup_ratio=2.0):
    """A pole, an `n_flag`-bar flag under it, a breakout bar that CLOSES above the pole top, then 'today'."""
    rows = _htf_rows(runup_ratio=runup_ratio, flag_depth=0.10, n_flag=n_flag)
    piv_date, piv_high = _pole_top(rows)
    flag_price, d = rows[-1]["close"], rows[-1]["trade_date"]
    rows.append(_row(d + timedelta(days=1), flag_price, piv_high * 1.02, flag_price, piv_high * 1.01, 2_000_000))
    rows.append(_row(d + timedelta(days=2), piv_high, piv_high * 1.015, piv_high * 0.99, piv_high, 800_000))
    return rows, piv_date, piv_high


def test_a_close_above_a_formed_flags_pole_top_stamps_the_row_after_the_reanchor():
    rows, piv_date, piv_high = _flag_then_breakout()
    out = fd.compute_flag_metrics(rows, ticker="BRK", recent_stages=[], prior_pivot_date=piv_date,
                                  prior_pivot_high=piv_high)
    assert out["pivot_high_date"] == rows[-2]["trade_date"], "the pivot re-anchored on the breakout bar"
    assert out["reason"].startswith("base_age_0_below_3"), "the bare base_age_0 the stamp exists to explain"
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (piv_date, 1)


def test_the_night_of_the_breakout_itself_carries_no_stamp_the_flag_is_still_the_flag():
    rows, piv_date, piv_high = _flag_then_breakout()
    out = fd.compute_flag_metrics(rows[:-1], ticker="BRK", recent_stages=[], prior_pivot_date=piv_date,
                                  prior_pivot_high=piv_high)
    assert out["pivot_high_date"] == piv_date
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (None, None)


def test_a_wick_over_the_top_that_closes_inside_is_not_a_breakout():
    rows = _htf_rows(runup_ratio=2.0, flag_depth=0.10, n_flag=8)
    piv_date, piv_high = _pole_top(rows)
    fp, d = rows[-1]["close"], rows[-1]["trade_date"]
    rows.append(_row(d + timedelta(days=1), fp, piv_high * 1.02, fp * 0.975, fp, 800_000))
    rows.append(_row(d + timedelta(days=2), fp, fp * 1.025, fp * 0.975, fp, 800_000))
    out = fd.compute_flag_metrics(rows, ticker="WICK", recent_stages=[], prior_pivot_date=piv_date,
                                  prior_pivot_high=piv_high)
    assert out["pivot_high_date"] == piv_date, "#592: the pivot did not move"
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (None, None)


def test_a_pole_still_extending_is_not_a_flag_breaking_out():
    """Fewer than `_BASE_AGE_MIN_WATCH` sessions under the top is a pole that is still running (`_flag_resolved_by`'s
    own line): the pivot walks, and that is not the board forgetting a flag."""
    rows, piv_date, piv_high = _flag_then_breakout(n_flag=2)
    out = fd.compute_flag_metrics(rows, ticker="EXT", recent_stages=[], prior_pivot_date=piv_date,
                                  prior_pivot_high=piv_high)
    assert out["pivot_high_date"] != piv_date, "the pivot did walk"
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (None, None)


def test_the_flag_must_have_formed_by_the_breakout_bar_exactly_at_the_watch_minimum():
    """`_BASE_AGE_MIN_WATCH` sessions of base under the top is a flag; one fewer is not."""
    for n_flag, expect in ((fd._BASE_AGE_MIN_WATCH, 1), (fd._BASE_AGE_MIN_WATCH - 1, None)):
        rows, piv_date, piv_high = _flag_then_breakout(n_flag=n_flag)
        out = fd.compute_flag_metrics(rows, ticker="EDGE", recent_stages=[], prior_pivot_date=piv_date,
                                      prior_pivot_high=piv_high)
        assert out["days_since_breakout"] == expect, n_flag


def test_a_pole_under_the_runup_gate_is_not_a_flag():
    """The pole must be a pole by the detector's own runup gate (`_RUNUP_MIN_RATIO` over `_RUNUP_LOOKBACK_DAYS`)."""
    rows, piv_date, piv_high = _flag_then_breakout(runup_ratio=1.6)
    out = fd.compute_flag_metrics(rows, ticker="LOW", recent_stages=[], prior_pivot_date=piv_date,
                                  prior_pivot_high=piv_high)
    assert out["pivot_high_date"] != piv_date, "the pivot did re-anchor (that is the old behaviour)"
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (None, None)


def test_a_pole_top_that_aged_out_of_the_lookback_is_not_a_breakout():
    """HNGE 08-18: the 07-13 top aged out of the 25-session lookback and the anchor was re-chosen inside the old flag.
    That is a re-anchor with no close above anything: no stamp (and the finder cannot use the aged prior pivot)."""
    rows, piv_date, piv_high = _flag_then_breakout()
    idx = next(i for i, r in enumerate(rows) if r["trade_date"] == piv_date)
    today = len(rows) - 1
    assert today - idx < fd._PIVOT_LOOKBACK_DAYS
    # push 'today' far enough forward that the old top is outside the lookback
    d = rows[-1]["trade_date"]
    for k in range(1, fd._PIVOT_LOOKBACK_DAYS + 1):
        rows.append(_row(d + timedelta(days=k), piv_high, piv_high * 1.01, piv_high * 0.99, piv_high, 800_000))
    today = len(rows) - 1
    assert today - idx > fd._PIVOT_LOOKBACK_DAYS
    pivot_idx, _ = fd._find_pivot_high(rows, today)
    assert fd._post_breakout_state(rows, today, pivot_idx, piv_date, None) == (None, None)


# ── 2. the carry: derived from the bars every night, newest breakout wins, lapses at 25 sessions ───────────────────

def test_days_come_from_the_bars_not_from_incrementing_yesterdays_row(corpus_bars):
    """Hand MRNA's 10-05 scan only the carried DATE (no prior row at all for 09-23 -> 10-02): the count is still
    right, because it is re-derived from the bars. A skipped scan cannot drift it."""
    bars = [r for r in corpus_bars["MRNA"] if r["trade_date"] <= date(2026, 10, 5)]
    out = fd.compute_flag_metrics(bars, ticker="MRNA", prior_post_breakout=date(2026, 8, 19))
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (date(2026, 8, 19), 9)


def test_a_carried_claim_the_bars_do_not_support_lapses_to_null(corpus_bars):
    bars = [r for r in corpus_bars["MRNA"] if r["trade_date"] <= date(2026, 10, 5)]
    for bogus in (date(2026, 9, 19),     # a Saturday: no bar
                  date(2026, 7, 1),      # a bar, but no pole and no formed close above it
                  date(2026, 9, 29)):    # a real bar whose flag has not yet been closed above
        out = fd.compute_flag_metrics(bars, ticker="MRNA", prior_post_breakout=bogus)
        assert (out["post_breakout_from"], out["days_since_breakout"]) == (None, None), bogus


def test_no_stamp_without_a_breakout_on_record():
    rows = _htf_rows(runup_ratio=2.0, flag_depth=0.10, n_flag=8)
    out = fd.compute_flag_metrics(rows, ticker="FLAT", recent_stages=[])
    assert (out["post_breakout_from"], out["days_since_breakout"]) == (None, None)
    assert set(_NEW_KEYS) <= set(out), "the keys exist on every row (None), so the insert never KeyErrors"


# ── 3. the real names: CDNA, MRNA (his top-rated example), a lapse, and the names that never broke out ─────────────

def test_cdna_08_26_reads_a_post_breakout_row_instead_of_a_bare_base_age_0(replays):
    r = replays["CDNA"]
    day0 = r[date(2026, 8, 25)]                      # the breakout day itself (close 50.80 over the 08-03 pivot's 49.76)
    assert day0["pivot_high_date"] == date(2026, 8, 3) and day0["post_breakout_from"] == date(2026, 7, 16), (
        "08-25 still carries the EARLIER breakout (07-31, out of the 07-16 flag)")
    row = r[date(2026, 8, 26)]
    assert row["reason"].startswith("base_age_0_below_3") and row["pivot_high_date"] == date(2026, 8, 25)
    assert (row["post_breakout_from"], row["days_since_breakout"]) == (date(2026, 8, 3), 1), (
        "the newest breakout replaces the carried one")
    follow = [(d, m["days_since_breakout"]) for d, m in sorted(r.items()) if date(2026, 8, 26) <= d <= date(2026, 9, 4)]
    assert [n for _, n in follow] == list(range(1, len(follow) + 1)), "one more session each row, 08-26 -> 09-04"
    assert all(r[d]["post_breakout_from"] == date(2026, 8, 3) for d, _ in follow)


def test_mrna_the_flag_is_remembered_after_the_09_22_reanchor(replays):
    """MRNA was `unqualified` (flag depth on the low) on every row of its flag and still broke out of it: close 182.56
    on 09-22 over the 08-19 pole top's high of 176.66. Prod stored 09-23 as `base_age_0_below_3`, pivot 09-22 $187.20
    (scripts/probes/_697/q6_extra_bars.out) - the replay reproduces that row, and now it also says what it was."""
    r = replays["MRNA"]
    assert r[date(2026, 9, 22)]["post_breakout_from"] is None, "the breakout day itself: the old flag is still the flag"
    first = r[date(2026, 9, 23)]
    assert first["stage"] == "unqualified" and first["reason"] == "base_age_0_below_3"
    assert first["pivot_high_date"] == date(2026, 9, 22) and first["pivot_high_price"] == 187.2    # = prod's stored row
    sessions = [d for d in sorted(r) if d >= date(2026, 9, 23)]
    assert len(sessions) == 13 and sessions[-1] == date(2026, 10, 9)
    for n, d in enumerate(sessions, start=1):
        assert (r[d]["post_breakout_from"], r[d]["days_since_breakout"]) == (date(2026, 8, 19), n), d
    # the stamp does not depend on the stage: unqualified -> WATCH -> INVALIDATED -> WATCH, still stamped
    assert {r[d]["stage"] for d in sessions} >= {"unqualified", "WATCH", "INVALIDATED"}


def test_the_stamp_lapses_after_the_pivot_lookback(replays):
    """HNGE (June, retired-rule era): broke out 06-15, stamped 06-16 -> day 25 on 07-22, NULL the next session."""
    r = replays["HNGE"]
    assert r[date(2026, 7, 22)]["days_since_breakout"] == fd._PIVOT_LOOKBACK_DAYS == 25
    nxt = r[date(2026, 7, 23)]
    assert (nxt["post_breakout_from"], nxt["days_since_breakout"]) == (None, None)


def test_hnge_august_the_aged_out_top_is_not_called_a_breakout(replays):
    """08-18: the 07-13 top left the 25-session lookback and the anchor moved - no close above it, so no stamp."""
    r = replays["HNGE"]
    for d in (date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19)):
        assert r[d]["post_breakout_from"] is None, d


def test_names_that_never_broke_out_keep_nulls(replays):
    """GH / HPE / NCI / SHAZ / ATAI: every replayed row of every one of them, NULL in both columns."""
    for t in ("GH", "HPE", "NCI", "SHAZ", "ATAI"):
        assert replays[t], t
        assert all(m["post_breakout_from"] is None and m["days_since_breakout"] is None for m in replays[t].values()), t


def test_both_columns_are_set_together_and_only_within_the_horizon(replays):
    for t, res in replays.items():
        for d, m in res.items():
            a, b = m["post_breakout_from"], m["days_since_breakout"]
            assert (a is None) == (b is None), (t, d)
            if a is not None:
                assert 1 <= b <= fd._PIVOT_LOOKBACK_DAYS and a < d, (t, d)


# ── 4. NO STAGE RULE MOVES ───────────────────────────────────────────────────────────────────────────────────────────

def test_switching_the_stamp_off_changes_nothing_else_on_any_corpus_row_equivalence(corpus_bars, replays, monkeypatch):
    """The two columns are written and read by nothing in the detector: replay every corpus member (and MRNA's
    extension) with `_post_breakout_state` stubbed to (None, None) and every OTHER field of every row - stage,
    held_from_stage, reason, score, the pivot, the base, triggered_from, the failure telemetry, all of it - is
    identical to the real run."""
    monkeypatch.setattr(fd, "_post_breakout_state", lambda *a, **k: (None, None))
    n_rows = 0
    for t, bars in corpus_bars.items():
        off = R.replay(t, bars)
        assert off.keys() == replays[t].keys(), t
        for d, m in replays[t].items():
            a = {k: v for k, v in m.items() if k not in _NEW_KEYS}
            b = {k: v for k, v in off[d].items() if k not in _NEW_KEYS}
            assert a == b, (t, d)
            n_rows += 1
    assert n_rows > 800


def test_a_failure_inside_the_stamp_costs_the_ticker_nothing(corpus_bars, monkeypatch):
    """Telemetry is never load-bearing: if the stamp cannot be computed the row is still scored, stage and all."""
    bars = [r for r in corpus_bars["CDNA"] if r["trade_date"] <= date(2026, 8, 26)]
    want = fd.compute_flag_metrics(bars, ticker="CDNA")

    def boom(*a, **k):
        raise TypeError("a bar with a missing field")
    monkeypatch.setattr(fd, "_post_breakout_state", boom)
    got = fd.compute_flag_metrics(bars, ticker="CDNA")
    assert (got["post_breakout_from"], got["days_since_breakout"]) == (None, None)
    assert {k: v for k, v in got.items() if k not in _NEW_KEYS} == {k: v for k, v in want.items() if k not in _NEW_KEYS}


# ── 5. persistence: columns, insert, reader ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_flag_candidate_writes_both_columns_in_their_own_places(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    rec = {"ticker": "MRNA", "scan_date": date(2026, 9, 23), "stage": "unqualified", "reason": "base_age_0_below_3",
           "post_breakout_from": date(2026, 8, 19), "days_since_breakout": 1}
    await db.insert_flag_candidate(rec)
    sql, *args = conn.execute.call_args.args
    names = [c.strip() for c in re.search(r"INSERT INTO mi_flag_candidates\s*\((.*?)\)\s*VALUES", sql, re.S).group(1).split(",")]
    n_values = len([p for p in re.search(r"VALUES\s*\((.*?)\)\s*ON CONFLICT", sql, re.S).group(1).split(",") if p.strip()])
    assert len(names) == n_values == len(args), "columns, placeholders and arguments must line up"
    assert args[names.index("post_breakout_from")] == date(2026, 8, 19)
    assert args[names.index("days_since_breakout")] == 1
    update = re.sub(r"\s+", " ", sql.split("DO UPDATE SET")[1])
    assert "post_breakout_from = EXCLUDED.post_breakout_from" in update
    assert "days_since_breakout = EXCLUDED.days_since_breakout" in update


@pytest.mark.asyncio
async def test_a_record_with_no_breakout_writes_nulls(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    await db.insert_flag_candidate({"ticker": "X", "scan_date": date(2026, 9, 23), "stage": "WATCH"})
    assert conn.execute.call_args.args[-2:] == (None, None)


@pytest.mark.asyncio
async def test_the_schema_step_adds_both_columns_additively_with_no_backfill(monkeypatch):
    """The REAL `initialize_schema` against a recording connection: declared in CREATE TABLE (fresh databases) and as
    idempotent `ADD COLUMN IF NOT EXISTS` (prod's table predates them). No UPDATE ever touches them - history stays
    NULL, which means 'not recorded', not 'no breakout'."""
    pool, conn = make_mock_pool()
    sent = []

    async def _execute(q, *a, **kw):
        sent.append(q)

    conn.execute = _execute
    conn.executemany = AsyncMock()
    for m in ("fetch", "fetchval", "fetchrow"):
        setattr(conn, m, AsyncMock(return_value=None))
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    await db.initialize_schema()
    ddl = next(q for q in sent if "CREATE TABLE IF NOT EXISTS mi_flag_candidates" in q)
    create = ddl[ddl.index("CREATE TABLE IF NOT EXISTS mi_flag_candidates"):]
    create = create[:create.index(");")]
    assert re.search(r"^\s+post_breakout_from\s+DATE,", create, re.M)
    assert re.search(r"^\s+days_since_breakout\s+INT,", create, re.M)
    assert "ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS post_breakout_from DATE;" in ddl
    assert "ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS days_since_breakout INT;" in ddl
    assert not re.search(r"UPDATE\s+mi_flag_candidates[^;]*(post_breakout_from|days_since_breakout)", ddl, re.S)


@pytest.mark.asyncio
async def test_the_history_reader_selects_both_columns(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    await db.get_ticker_flag_history("MRNA", 14)
    sql = conn.fetch.call_args.args[0]
    assert "post_breakout_from" in sql and "days_since_breakout" in sql


@pytest.mark.asyncio
async def test_the_carry_reader_returns_the_latest_stamp_per_ticker_inside_the_window(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"ticker": "MRNA", "post_breakout_from": date(2026, 8, 19)}])
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    out = await db.get_flag_post_breakout_carry(date(2026, 10, 12), carry_days=fd._PIVOT_CARRY_DAYS)
    assert out == {"MRNA": date(2026, 8, 19)}
    sql, scan_date, days = conn.fetch.await_args.args
    flat = " ".join(sql.split())
    assert "DISTINCT ON (ticker)" in flat and "post_breakout_from IS NOT NULL" in flat and "ORDER BY ticker, scan_date DESC" in flat
    assert scan_date == date(2026, 10, 12) and days == fd._PIVOT_CARRY_DAYS == 40


@pytest.mark.asyncio
async def test_a_failed_carry_read_returns_empty_and_never_stops_the_scan(monkeypatch):
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=ConnectionError("db down")))
    assert await db.get_flag_post_breakout_carry(date(2026, 10, 12), carry_days=40) == {}


# ── 6. the wiring through run_flag_scan ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_flag_scan_hands_each_ticker_its_carried_stamp_and_stores_what_comes_back(table, monkeypatch):  # noqa: F811
    d = date(2026, 10, 12)
    seen, stored = {}, {}

    def _metrics(history, ticker=None, **kw):
        seen[ticker] = kw.get("prior_post_breakout")
        stamped = ticker == "AAA"
        return {"ticker": ticker, "stage": "WATCH", "held_from_stage": None, "reason": "x", "runup_pct": 1.3,
                "pivot_high_price": 50.0, "base_age": 10, "range_contraction_ratio": 0.9, "vol_contraction_ratio": 0.9,
                "fresh_tight_fires": False,
                "post_breakout_from": date(2026, 9, 16) if stamped else None,
                "days_since_breakout": 4 if stamped else None}

    async def _insert(m):
        stored[m["ticker"]] = (m.get("post_breakout_from"), m.get("days_since_breakout"))

    monkeypatch.setattr(fd, "compute_flag_metrics", _metrics)
    monkeypatch.setattr(db, "insert_flag_candidate", _insert)
    monkeypatch.setattr(db, "get_flag_universe", AsyncMock(return_value={"AAA": ["rs_top200"], "BBB": ["rs_top200"]}))
    monkeypatch.setattr(db, "get_flag_post_breakout_carry", AsyncMock(return_value={"AAA": date(2026, 9, 16)}))
    await fd.run_flag_scan(d)
    assert seen == {"AAA": date(2026, 9, 16), "BBB": None}
    assert stored == {"AAA": (date(2026, 9, 16), 4), "BBB": (None, None)}
    db.get_flag_post_breakout_carry.assert_awaited_once()
    assert db.get_flag_post_breakout_carry.await_args.kwargs == {"carry_days": fd._PIVOT_CARRY_DAYS}


# ── 7. what the operator reads: /flags TICKER ───────────────────────────────────────────────────────────────────────

def test_the_label_is_plain_words_and_markdown_safe():
    assert fd.post_breakout_label({"post_breakout_from": date(2026, 9, 16), "days_since_breakout": 4}) == \
        "broke out of the 09-16 flag · day 4"
    assert fd.post_breakout_label({"post_breakout_from": "2026-08-19", "days_since_breakout": 13}) == \
        "broke out of the 08-19 flag · day 13"
    for r in ({}, {"post_breakout_from": None, "days_since_breakout": None},
              {"post_breakout_from": date(2026, 9, 16), "days_since_breakout": None},
              {"post_breakout_from": "not-a-date", "days_since_breakout": 3}):
        assert fd.post_breakout_label(r) == "", r
    text = fd.post_breakout_label({"post_breakout_from": date(2026, 9, 16), "days_since_breakout": 4})
    assert not re.search(r"[_*`\[\]|]", text), "legacy Markdown would eat these characters"


@pytest.mark.asyncio
async def test_flags_ticker_shows_the_post_breakout_state_on_those_rows_only(monkeypatch):
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest

    def _h(d, stage, age, pbf=None, n=None):
        return {"scan_date": d, "stage": stage, "base_age": age, "range_contraction_ratio": None,
                "vol_contraction_ratio": None, "held_from_stage": None, "triggered_from": None,
                "fresh_tight_fires": False, "fresh_2bar_tr_pct": None, "atr14_pct": None,
                "post_breakout_from": pbf, "days_since_breakout": n}

    hist = [_h("2026-09-26", "unqualified", 1, date(2026, 9, 16), 4),
            _h("2026-09-23", "unqualified", 0, date(2026, 9, 16), 1),
            _h("2026-09-22", "unqualified", 25)]
    monkeypatch.setattr(db, "get_ticker_flag_history", AsyncMock(return_value=hist))
    res = await MarketIntelligenceAgent()._handle_flag_query(
        AgentRequest(task="/flags MRNA", user_id=1, conversation_id="t"))
    lines = {ln.split()[0]: ln for ln in res.result.splitlines() if ln.strip().startswith("2026-")}
    assert lines["2026-09-26"].endswith("broke out of the 09-16 flag · day 4")
    assert lines["2026-09-23"].endswith("broke out of the 09-16 flag · day 1")
    assert "broke out" not in lines["2026-09-22"]
    assert "|" not in res.result
