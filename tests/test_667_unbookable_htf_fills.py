"""#667 — the HTF outcome table recorded trades we could not have taken, and its ONLY winner was one.

FOUND 2026-09-10, measured on prod 2026-09-16, fixed 2026-09-18 on the operator's *"When are we
fixing it"*. Two defects, 2 of 18 rows — and 2 of the 10 SETTLED ones, so 20% of the usable
evidence:

  (1) UNFILLABLE ENTRY — CDNA 2026-07-31, the table's only `capture`. Entry booked at 40.47 when
      the break day's LOW was 40.67. The HTF entry is a stop-limit BUY at base_high; the stock
      gapped straight over the order and a stop-limit buy cannot fill above its limit.
      `_htf_settle_from_bars` passed `include_entry_bar=True` and never compared the entry to that
      bar's low, so the single win in the evidence base was a trade nobody could have entered.

  (2) SPLIT DRIFT — CRWD 2026-07-01, entry stored 778.82 against a break-day low of 191.25;
      `mi_splits` carries a 1:4 on 2026-07-02. The shadow keeps RAW prices and `mi_daily_closes`
      is retro-ADJUSTED, so any join across a split is nonsense.

⚠ THE ABSTAIN IS PERMANENT, AND THAT DISTINCTION IS THE DESIGN. `None` already meant "the forward
window is not complete yet, retry next run". Neither of these ever becomes bookable, so they get a
THIRD shape — `{"outcome": None, "abstain_reason": ...}` — which the job MARKS rather than settles.
Collapsing the two would either re-mark the same rows forever or silently drop them.

⚠ AND THE ROWS MUST NOT SIMPLY VANISH INTO "open". `outcome` stays NULL so nothing counts them as
results, but `unbookable_n` is its own line in the readout and is EXCLUDED from `open_n` — an
unbookable row is not "still waiting". Leaving it inside `open_n` would overstate the pipeline the
same way the impossible capture overstated the win rate.

⚖ NOT a detection criterion and NOT an entry rule: this is shadow TELEMETRY and
`prepare_htf_breakout_order` is untouched. A recorder that credits impossible fills is a bug fix.
[[classify-before-applying-evidence-gates]]
"""
from __future__ import annotations

import pytest

from agents.market_intelligence.flag_detector import _htf_settle_from_bars


def _bars(rows):
    """db_rows_to_bars shape: date/o/h/l/c dicts."""
    return [{"date": d, "o": o, "h": h, "l": l, "c": c} for d, o, h, l, c in rows]


# ── guard 1: the fill itself ────────────────────────────────────────────────────────────

def test_cdna_the_real_row_is_refused():
    """CDNA 2026-07-31 verbatim: entry 40.47, break-day low 40.67. RED-proven — before the guard
    this returned outcome='capture' and it was the only winner in the table."""
    bars = _bars([
        ("2026-07-31", 41.00, 44.00, 40.67, 43.50),   # the break day — LOW is ABOVE our entry
        ("2026-08-03", 43.60, 52.00, 43.00, 51.00),   # would have run to +3R on a fill we never got
        ("2026-08-04", 51.00, 55.00, 50.00, 54.00),
    ])
    res = _htf_settle_from_bars(bars, 0, entry_price=40.47, stop=38.00, target_r=3.0, window=2)
    assert res is not None, "a permanent abstain must not be confused with 'retry next run'"
    assert res["outcome"] is None, (
        "the settler booked an outcome on a bar whose LOW (40.67) is above the stop-limit entry "
        "(40.47) — a buy cannot fill above its limit. This is the CDNA row, the table's only win."
    )
    assert "unfillable_entry" in res["abstain_reason"]
    assert "40.47" in res["abstain_reason"] and "40.67" in res["abstain_reason"], (
        "the reason must carry BOTH numbers — a reader has to see the fill was impossible, "
        "not just be told so"
    )


def test_a_fill_that_was_reachable_still_settles():
    """The other direction, and without it the guard could just refuse everything: when the break
    day trades AT or BELOW the entry, the order fills and the row settles exactly as before."""
    bars = _bars([
        ("2026-07-31", 41.00, 44.00, 40.00, 43.50),   # low 40.00 <= entry 40.47 — reachable
        ("2026-08-03", 43.60, 52.00, 43.00, 51.00),
        ("2026-08-04", 51.00, 55.00, 50.00, 54.00),
    ])
    res = _htf_settle_from_bars(bars, 0, entry_price=40.47, stop=38.00, target_r=3.0, window=2)
    assert res["outcome"] == "capture"
    assert res.get("abstain_reason") is None


def test_a_low_exactly_at_the_entry_fills():
    """The boundary, pinned deliberately: a stop-limit buy at X fills if the tape prints X. Only
    a low STRICTLY above the entry is impossible, so `>` is the correct comparison, not `>=`."""
    bars = _bars([
        ("2026-07-31", 41.00, 44.00, 40.47, 43.50),   # low == entry
        ("2026-08-03", 43.60, 52.00, 43.00, 51.00),
        ("2026-08-04", 51.00, 55.00, 50.00, 54.00),
    ])
    res = _htf_settle_from_bars(bars, 0, entry_price=40.47, stop=38.00, target_r=3.0, window=2)
    assert res["outcome"] == "capture", "a low exactly at the limit is a fill, not an abstain"


def test_the_temporary_abstain_is_still_a_bare_none():
    """The pre-existing contract must survive: an incomplete forward window returns None, NOT the
    new dict. The job treats them differently — None retries, the dict marks the row forever."""
    bars = _bars([("2026-07-31", 41.00, 44.00, 40.00, 43.50)])
    assert _htf_settle_from_bars(bars, 0, entry_price=40.47, stop=38.00,
                                 target_r=3.0, window=12) is None


# ── guard 2: the split, and the readout ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_split_between_break_and_settle_is_marked_and_the_bars_are_never_fetched(monkeypatch):
    """CRWD 2026-07-01: entry stored 778.82 against a break-day low of 191.25, because a 1:4 split
    executed 2026-07-02. The shadow keeps RAW prices and `mi_daily_closes` is retro-ADJUSTED, so the
    comparison is meaningless — and the old job made it anyway.

    Exercised through the real job rather than pinned as source text: it asserts the row is MARKED,
    never SETTLED, and that the bars are **not fetched at all**, which is the part a text pin cannot
    see (the split check could be called and its result ignored)."""
    from datetime import date
    from agents.market_intelligence import db as dbmod, scheduler as sch

    row = {"id": 42, "ticker": "CRWD", "break_date": date(2026, 7, 1), "entry_price": 778.82,
           "base_high": 778.82, "stop_loss_price": 720.0, "target_r": 3.0}
    calls = {"bars": 0, "settled": [], "marked": []}

    async def _ripe(_cutoff):
        return [row]

    async def _splits(ticker, after):
        assert ticker == "CRWD" and after == date(2026, 7, 1)
        return [{"execution_date": date(2026, 7, 2), "split_from": 1, "split_to": 4}]

    async def _bars(*a, **k):
        calls["bars"] += 1
        raise AssertionError("bars were fetched despite a known split across the window")

    async def _mark(row_id, reason):
        calls["marked"].append((row_id, reason)); return True

    async def _settle(*a, **k):
        calls["settled"].append(a); return True

    monkeypatch.setattr(dbmod, "get_settleable_htf_breakout_shadows", _ripe)
    monkeypatch.setattr(dbmod, "get_split_dates_after", _splits)
    monkeypatch.setattr(dbmod, "get_anticipation_ohlcv", _bars)
    monkeypatch.setattr(dbmod, "mark_htf_breakout_shadow_unbookable", _mark)
    monkeypatch.setattr(dbmod, "settle_htf_breakout_shadow", _settle)

    settled = await sch._htf_breakout_settle_job(date(2026, 9, 18))

    assert calls["bars"] == 0, "the job fetched adjusted bars to compare against a raw entry"
    assert calls["settled"] == [], "a row spanning a split was settled"
    assert len(calls["marked"]) == 1
    row_id, reason = calls["marked"][0]
    assert row_id == 42
    assert "split" in reason and "2026-07-02" in reason, (
        f"the reason must name the split and its date so a reader can check it: {reason!r}")
    assert settled == []


@pytest.mark.asyncio
async def test_an_unfillable_row_is_marked_not_settled(monkeypatch):
    """The other guard, end to end through the job: no split, bars fetched, and the settler refuses
    the fill. The row must be MARKED — not settled, and not silently skipped, which would leave it
    re-considered on every run forever."""
    from datetime import date
    from agents.market_intelligence import db as dbmod, scheduler as sch

    row = {"id": 7, "ticker": "CDNA", "break_date": date(2026, 7, 31), "entry_price": 40.47,
           "base_high": 40.47, "stop_loss_price": 38.0, "target_r": 3.0}
    marked, settled_calls = [], []

    async def _ripe(_c):
        return [row]

    async def _splits(*a, **k):
        return []

    async def _ohlcv(*a, **k):
        # db_rows_to_bars input shape — the break day's LOW (40.67) is ABOVE the entry (40.47).
        return [{"trade_date": "2026-07-31", "open_price": 41.0, "high_price": 44.0,
                 "low_price": 40.67, "close": 43.5, "volume": 1_000_000},
                {"trade_date": "2026-08-03", "open_price": 43.6, "high_price": 52.0,
                 "low_price": 43.0, "close": 51.0, "volume": 1_000_000},
                {"trade_date": "2026-08-04", "open_price": 51.0, "high_price": 55.0,
                 "low_price": 50.0, "close": 54.0, "volume": 1_000_000}]

    async def _mark(row_id, reason):
        marked.append((row_id, reason)); return True

    async def _settle(*a, **k):
        settled_calls.append(a); return True

    monkeypatch.setattr(dbmod, "get_settleable_htf_breakout_shadows", _ripe)
    monkeypatch.setattr(dbmod, "get_split_dates_after", _splits)
    monkeypatch.setattr(dbmod, "get_anticipation_ohlcv", _ohlcv)
    monkeypatch.setattr(dbmod, "mark_htf_breakout_shadow_unbookable", _mark)
    monkeypatch.setattr(dbmod, "settle_htf_breakout_shadow", _settle)

    await sch._htf_breakout_settle_job(date(2026, 9, 18))

    assert settled_calls == [], (
        "CDNA was settled again — this is the row that produced the table's only `capture` on a "
        "fill that could not have happened")
    assert len(marked) == 1 and marked[0][0] == 7
    assert "unfillable_entry" in marked[0][1]


@pytest.mark.parametrize("getter", ["get_htf_breakout_shadow_summary",
                                   "get_htf_management_shadow_summary"])
def test_the_readouts_count_unbookable_separately(getter):
    """`outcome` staying NULL is what stops a bad row being counted as a RESULT; this is what
    stops it being counted as a row still WAITING.

    BOTH readouts, under one pin: Phase 3's (the fixed-3R bet) and Phase 4's (#396's management
    protocol). Phase 4 was added 2026-09-19 when review found it had been reporting CDNA's
    impossible +1.96R trail-exit as one of its four winners — the consumer half of #667."""
    # source-pin-ok: each summary is one SQL string against a live pool with no injectable seam;
    # what must not regress is that open_n excludes the abstained rows and that the count is
    # surfaced at all, both of which live only in that query's text.
    import inspect
    from agents.market_intelligence import db
    src = inspect.getsource(getattr(db, getter))
    assert "unbookable_n" in src, f"{getter} does not surface the unbookable count at all"
    open_clause = src[src.index("AS open_n") - 260:src.index("AS open_n")]
    assert "settle_abstain_reason IS NULL" in open_clause or " ok " in open_clause, (
        f"{getter}.open_n still counts unbookable rows — they are not 'still waiting', and "
        f"folding them in overstates the pipeline the way the impossible capture overstated "
        f"the win rate"
    )


# ─────────────────────────────────────────────────────────────────────────────────────────
# #667, THE SECOND HALF — the CONSUMERS, found by review hours after the first half shipped
# ─────────────────────────────────────────────────────────────────────────────────────────
#
# The first half stopped Phase 3 SETTLING an unbookable row. It did not stop anything else
# READING one. `get_htf_management_shadow_candidates` (#396 Phase 4) selects on
# `would_reject_reason IS NULL AND m.status = 'open'` — no mention of the new column — so CDNA,
# the 40.47 entry against a 40.67 break-day low, was carried through the management replay to
# `closed_trail_exit` at **+1.96R**. A winner, on a fill that could not have happened, in the
# readout that answers "what would the sourced management protocol have done".
#
# That is the day's own defect class one layer out: the deal-pin fix filtered one of six RS
# POOLS; this filtered one of four CONSUMERS. So the guard below does not name them — it
# DERIVES the set from source and fails the day a new one appears.
# [[derive-the-population-never-hand-list-it]]


def _shadow_readers() -> dict:
    """Every place in the codebase that READS mi_htf_breakout_shadow, derived. Writers
    (INSERT/UPDATE) are excluded by construction: `FROM`/`JOIN` is what a read looks like."""
    import re
    from pathlib import Path
    out = {}
    root = Path(__file__).resolve().parents[1]
    for path in sorted((root / "agents").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "mi_htf_breakout_shadow" not in src:
            continue
        for m in re.finditer(r"(?:FROM|JOIN)\s+mi_htf_breakout_shadow\b", src):
            # the enclosing SQL string: back to the opening triple-quote, forward to the close
            start = src.rfind('"""', 0, m.start())
            end = src.find('"""', m.end())
            if start == -1 or end == -1:
                start, end = max(0, m.start() - 400), m.end() + 400
            out[f"{path.relative_to(root)}:{src[:m.start()].count(chr(10)) + 1}"] = src[start:end]
    return out


def test_no_reader_of_the_shadow_table_can_count_an_unbookable_row():
    """The gate. A read is SAFE if it either excludes the abstained rows outright, or filters on
    a POSITIVE outcome — an unbookable row's `outcome` stays NULL forever, so `outcome IN (...)`
    and `outcome IS NOT NULL` already cannot reach it. Anything else counts a position that was
    never takeable.

    WOULD-FAIL-IF: a new consumer joins the table with a bare `WHERE outcome IS NULL` — which is
    exactly the predicate `get_htf_management_shadow_candidates` was using through `m.status`."""
    # source-pin-ok: the population this asserts over is "which SQL statements exist", which is
    # only readable from source. The list itself is DERIVED (never hand-written) — that is the
    # property the day's lesson is about, and a behavioural test of the four readers we know
    # about would have passed cleanly while Phase 4 was booking CDNA's impossible +1.96R.
    readers = _shadow_readers()
    assert len(readers) >= 4, (
        f"only {len(readers)} reader(s) of mi_htf_breakout_shadow found — the derivation broke, "
        f"and a gate that finds nothing passes exactly like one that finds everything clean")
    unsafe = {
        where: sql for where, sql in readers.items()
        if "settle_abstain_reason" not in sql
        and "outcome IS NOT NULL" not in sql
        and "outcome IN (" not in sql
    }
    assert not unsafe, (
        "these reads of mi_htf_breakout_shadow can reach an UNBOOKABLE row — a Phase-3 entry we "
        "could not have filled — and treat it as a real position:\n  " + "\n  ".join(unsafe))


