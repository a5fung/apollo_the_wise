"""#655 (c) — a theme the OPERATOR promotes is not absorbed by Pass 1.5 for its first 3 theme nights.

His ruling 2026-10-17 ("go with rec"). The case: his 10-12 promotion 'Capital Markets & Deal-Flow
Re-Rating' (PWP, PAX, CBOE) was absorbed by Pass 1.5 on 10-13 and again on 10-15 into a theme it shares
CBOE with; by 10-16 PWP and PAX sat in no theme. Base rate: 4 of 9 operator promotions since 09-01 were
absorbed within 3 nights (scripts/probes/_655_churn_1017/TABLE_FILLED.md row c).

What is pinned here:
  * the window is ENGINE nights (distinct source='live' theme_dates strictly after the promotion's ET
    date and strictly before tonight), not calendar days — a weekend does not use it up;
  * the exemption is by EXACT name; a promotion row for a different name exempts nothing;
  * Pass 1.5 inside the window leaves the theme alone and writes ONE `theme_pass1_5_operator_exempt`
    row naming the would-be absorber and the night; from night 4 it absorbs exactly as before;
  * with no exemption set (every pre-existing caller) Pass 1.5 is byte-identical;
  * ONE query per run, fail-open to today's behaviour with an error row;
  * every `_merge_overlapping_themes` call in the engine passes the set (derived, not hand-listed).

Run: pytest tests/test_655c_operator_promoted_exempt.py -v
"""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest

from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.audit_events import (
    THEME_PASS1_5_OPERATOR_EXEMPT, THEME_PASS1_5_OPERATOR_EXEMPT_ERROR,
)

PROMO = "Capital Markets & Deal-Flow Re-Rating"
BIG = "Exchange, Options Trading & Alternative Consumer Credit Financials"
EXEMPT_EVENT = "theme_pass1_5_operator_exempt"
ABSORB_EVENT = "theme_pass1_5_absorption"


def _themes() -> list[dict]:
    """The 10-13 shape: a 3-stock promoted theme whose members mostly sit in a bigger, higher-scored
    theme. Only 2 are shared (< MIN_SHARED_FOR_MERGE), so Pass 1 leaves them alone and Pass 1.5 is the
    only mechanism that can take the small one (1 unique member <= 1)."""
    return [
        {"name": BIG, "tickers": ["CBOE", "PWP", "CME", "ICE", "SEZL", "TW"], "score": 80.0, "stage": "Fading"},
        {"name": PROMO, "tickers": ["PWP", "CBOE", "PAX"], "score": 60.0, "stage": "Nascent"},
    ]


@pytest.fixture
def audit(monkeypatch):
    from unittest.mock import AsyncMock
    mock = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", mock)
    return mock


def _rows(audit, event):
    return [c for c in audit.await_args_list if c.args and c.args[0] == event]


def _kw(call, key):
    return call.kwargs.get(key)


async def _run(themes=None, exempt=None):
    return await te._merge_overlapping_themes(
        themes if themes is not None else _themes(), {},
        protected_names={BIG, PROMO},            # prod: both are existing (protected) themes
        operator_exempt=exempt)


def _by_name(out):
    return {t["name"]: set(t["tickers"]) for t in out}


def test_fixture_shape_is_a_pass_1_5_only_case():
    """Guards the fixture: Pass 1 must not fire and no sector cap applies, or the tests below would
    pass/fail for the wrong mechanism."""
    assert te._sector_group(PROMO) is None and te._sector_group(BIG) is None
    shared = set(_themes()[0]["tickers"]) & set(_themes()[1]["tickers"])
    assert len(shared) < te.MIN_SHARED_FOR_MERGE


# ── the merge layer ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unexempt_theme_is_absorbed_as_today(audit):
    """Control: no exemption set -> Pass 1.5 absorbs the small theme (the 10-13 behaviour)."""
    out = await _run(exempt=None)
    by = _by_name(out)
    assert PROMO not in by and "PAX" in by[BIG]
    assert len(_rows(audit, ABSORB_EVENT)) == 1 and _rows(audit, EXEMPT_EVENT) == []


@pytest.mark.asyncio
async def test_empty_exemption_set_is_byte_identical_to_none(audit):
    a = await _run(exempt=None)
    audit.reset_mock()
    b = await _run(exempt=te.OperatorExempt())
    assert _by_name(a) == _by_name(b)
    assert len(_rows(audit, ABSORB_EVENT)) == 1 and _rows(audit, EXEMPT_EVENT) == []


@pytest.mark.asyncio
async def test_promoted_theme_inside_window_is_not_absorbed_and_writes_one_row(audit):
    out = await _run(exempt=te.OperatorExempt(nights_left={PROMO: 3}))
    by = _by_name(out)
    assert by[PROMO] == {"PWP", "CBOE", "PAX"}                         # survives with its own roster
    assert by[BIG] == {"CBOE", "PWP", "CME", "ICE", "SEZL", "TW"}      # nothing was unioned in
    assert _rows(audit, ABSORB_EVENT) == []                            # not absorbed
    assert [c.args[0] for c in audit.await_args_list if c.args[0] == "theme_pass1_5_skip"] == []
    rows = _rows(audit, EXEMPT_EVENT)
    assert len(rows) == 1
    summary, detail = _kw(rows[0], "summary"), _kw(rows[0], "detail")
    assert PROMO in summary and BIG in summary and "night 1 of 3" in summary
    assert f"t='{PROMO}'" in detail and f"would_be_absorber='{BIG}'" in detail
    assert "night=1 of 3" in detail and "nights_left_after_tonight=2" in detail


@pytest.mark.asyncio
async def test_last_exempt_night_says_night_3_and_none_left(audit):
    await _run(exempt=te.OperatorExempt(nights_left={PROMO: 1}))
    d = _kw(_rows(audit, EXEMPT_EVENT)[0], "detail")
    assert "night=3 of 3" in d and "nights_left_after_tonight=0" in d


@pytest.mark.asyncio
async def test_the_row_is_one_per_theme_per_run_across_both_merge_passes(audit):
    """run_theme_engine calls the merge twice a night with ONE exemption object: the second pass must
    still skip the theme but must not write a second row."""
    ex = te.OperatorExempt(nights_left={PROMO: 2})
    await _run(exempt=ex)
    out2 = await _run(exempt=ex)
    assert PROMO in _by_name(out2)
    assert len(_rows(audit, EXEMPT_EVENT)) == 1


@pytest.mark.asyncio
async def test_non_promoted_theme_with_the_same_shape_is_absorbed_as_today(audit):
    """The exemption is for the promoted NAME. Another small theme of the same shape, in a set that
    exempts something else, is absorbed and writes no exempt row."""
    other = "Some Other Three-Stock Cohort"
    themes = _themes()
    themes[1] = {**themes[1], "name": other}
    out = await te._merge_overlapping_themes(
        themes, {}, protected_names={BIG, other},
        operator_exempt=te.OperatorExempt(nights_left={PROMO: 3}))
    assert other not in _by_name(out)
    assert len(_rows(audit, ABSORB_EVENT)) == 1 and _rows(audit, EXEMPT_EVENT) == []


@pytest.mark.asyncio
async def test_an_exempt_theme_that_was_not_eligible_writes_nothing(audit):
    """The row records an absorption that WOULD have happened. A promoted 3-stock theme with 2 unique
    members is not Pass-1.5-eligible, so the exemption did not fire and no row is written."""
    themes = _themes()
    themes[1]["tickers"] = ["PWP", "PAX", "QQQ"]        # PAX, QQQ unique -> 2 > 1 -> not eligible
    out = await _run(themes=themes, exempt=te.OperatorExempt(nights_left={PROMO: 3}))
    assert PROMO in _by_name(out)
    assert _rows(audit, EXEMPT_EVENT) == [] and _rows(audit, ABSORB_EVENT) == []


# ── the window: engine nights, exact names (pure core) ───────────────────────────────────────────

def _summary(name, n=3, tail=""):
    return f"Operator promoted '{name}' ({n} members){tail}"


def test_the_writers_summary_and_the_readers_regex_are_one_definition():
    """`promote_candidate_by_name` writes the summary from `_OPERATOR_PROMOTED_SUMMARY`; the exemption reads the
    name back with a regex BUILT FROM that format. A reworded summary therefore cannot silently empty the
    exemption, and the wording the operator sees is pinned here as a literal."""
    assert te._OPERATOR_PROMOTED_EVENT == "theme_operator_promoted"
    assert te._OPERATOR_PROMOTED_SUMMARY.format(name="X", n=3) == "Operator promoted 'X' (3 members)" == _summary("X")
    for name in (PROMO, BIG, "Gold & Silver (Miners)", "O'Reilly-style 'quoted' theme", "AI Capex: Power + Cooling"):
        for tail in ("", " — already a live theme, left intact"):
            written = te._OPERATOR_PROMOTED_SUMMARY.format(name=name, n=12) + tail
            assert te._OPERATOR_PROMOTED_SUMMARY_RE.match(written).group(1) == name
    assert te._OPERATOR_PROMOTED_SUMMARY_RE.match("Operator promoted 'X' (many members)") is None      # n is a number
    assert te._OPERATOR_PROMOTED_SUMMARY_RE.match("Operator PROMOTED 'X' (3 members)") is None         # the wording is exact
    # and the exemption's own SQL asks for exactly the event the writer logs
    assert f"event_type = '{te._OPERATOR_PROMOTED_EVENT}'" in te._OPERATOR_EXEMPT_SQL


MON, TUE, WED, THU, FRI = (date(2026, 10, d) for d in (12, 13, 14, 15, 16))
SAT, SUN, NEXT_MON = date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19)


def _left(promos, nights, today):
    return te._operator_exempt_nights_left(promos, nights, today)


def test_the_real_case_nights_1_to_3_exempt_and_night_4_absorbed():
    """His 10-12 promotion (after that night's run): engine nights 10-13, 10-14, 10-15 exempt; 10-16 not."""
    promos = [(_summary(PROMO), MON)]
    nights = [MON, TUE, WED, THU, FRI]
    assert _left(promos, nights, TUE) == {PROMO: 3}     # night 1
    assert _left(promos, nights, WED) == {PROMO: 2}     # night 2
    assert _left(promos, nights, THU) == {PROMO: 1}     # night 3
    assert _left(promos, nights, FRI) == {}             # night 4: absorbed as today


def test_window_counts_engine_nights_not_calendar_days():
    """Promoted Fri 10-09: its 3 nights are Mon 10-12, Tue 10-13, Wed 10-14 — the Thursday of the NEXT
    week is the 4th. A calendar-day window (promo + 3 days = Mon 10-12) would have closed on night 1."""
    fri = date(2026, 10, 9)
    promos = [(_summary(PROMO), fri)]
    nights = [fri, MON, TUE, WED, THU]                   # no Sat/Sun rows: the engine does not run
    assert _left(promos, nights, MON) == {PROMO: 3}
    assert _left(promos, nights, TUE) == {PROMO: 2}
    assert _left(promos, nights, WED) == {PROMO: 1}
    assert _left(promos, nights, THU) == {}
    assert (THU - fri).days == 6 and (MON - fri).days == 3


def test_a_same_evening_rerun_and_tonights_own_rows_do_not_use_the_window():
    """Tonight's date in `night_dates` (a re-run: the earlier run already wrote tonight's rows) and the
    promotion's own date are both outside the open interval."""
    promos = [(_summary(PROMO), MON)]
    assert _left(promos, [MON, TUE], TUE) == {PROMO: 3}          # TUE row exists (re-run) — not counted
    assert _left(promos, [MON], MON) == {PROMO: 3}               # promoted pre-run: tonight is night 1


def test_a_promotion_row_for_a_different_name_exempts_nothing():
    promos = [(_summary("Cruise Lines & Leisure Travel Rebound"), MON)]
    out = _left(promos, [MON], TUE)
    assert PROMO not in out and out == {"Cruise Lines & Leisure Travel Rebound": 3}


@pytest.mark.parametrize("near", [PROMO + " Plus", PROMO[:-3], PROMO.lower(), "Re-Rating"])
def test_the_name_must_match_exactly(near):
    promos = [(_summary(near), MON)]
    assert PROMO not in _left(promos, [MON], TUE)


def test_a_noop_promotion_row_and_an_apostrophe_name_parse():
    """'left intact' (already a live theme) still carries the operator's name; a name with an
    apostrophe survives the greedy parse."""
    tail = " — already a live theme, left intact"
    tricky = "Women's Apparel & Children's Retail"
    out = _left([(_summary(PROMO, tail=tail), MON), (_summary(tricky, 4), MON)], [MON], TUE)
    assert out == {PROMO: 3, tricky: 3}


def test_a_re_promotion_renews_the_window_and_a_future_row_does_nothing():
    promos = [(_summary(PROMO), MON), (_summary(PROMO), WED)]
    assert _left(promos, [MON, TUE, WED], THU) == {PROMO: 3}      # latest promotion wins
    # back-dated engine run (replay for 10-13) must not see a promotion made on 10-15
    assert _left([(_summary(PROMO), THU)], [MON], TUE) == {}


def test_an_unparseable_summary_is_skipped_not_guessed():
    assert _left([("Operator promoted something", MON), (None, MON), ("", MON)], [MON], TUE) == {}


# ── the loader: ONE query, fail-open ─────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self, rows=None, exc=None):
        self.rows, self.exc, self.calls = rows or [], exc, []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if self.exc:
            raise self.exc
        return self.rows


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False
        return _Ctx()


def _patch_pool(monkeypatch, conn):
    async def get_pool():
        return _Pool(conn)
    monkeypatch.setattr(te, "get_pool", get_pool)


@pytest.mark.asyncio
async def test_loader_makes_one_query_and_reads_both_row_kinds(monkeypatch, audit):
    conn = _Conn(rows=[
        {"kind": "promo", "summary": _summary(PROMO), "d": MON},
        {"kind": "night", "summary": None, "d": MON},
        {"kind": "night", "summary": None, "d": TUE},
    ])
    _patch_pool(monkeypatch, conn)
    ex = await te._load_operator_exempt(WED)
    assert ex.nights_left == {PROMO: 2} and ex.logged == set()      # TUE done -> night 2 tonight
    assert len(conn.calls) == 1                                      # one query for the whole run
    sql, args = conn.calls[0]
    assert "source = 'live'" in sql and "theme_operator_promoted" in sql
    assert args[0] == WED and args[1] == date(2026, 9, 14)           # tonight, tonight - 30 days
    assert _rows(audit, THEME_PASS1_5_OPERATOR_EXEMPT_ERROR) == []


@pytest.mark.asyncio
async def test_loader_failure_exempts_nothing_and_says_so(monkeypatch, audit):
    _patch_pool(monkeypatch, _Conn(exc=RuntimeError("pool exhausted")))
    ex = await te._load_operator_exempt(WED)
    assert ex.nights_left == {}
    err = _rows(audit, THEME_PASS1_5_OPERATOR_EXEMPT_ERROR)
    assert len(err) == 1 and "pool exhausted" in _kw(err[0], "detail")


# ── wiring + constants ───────────────────────────────────────────────────────────────────────────

def test_event_names_are_the_registered_constants():
    assert THEME_PASS1_5_OPERATOR_EXEMPT == EXEMPT_EVENT
    assert THEME_PASS1_5_OPERATOR_EXEMPT_ERROR == "theme_pass1_5_operator_exempt_error"


def test_every_merge_call_in_the_engine_passes_the_exemption_set():
    """Derived, not hand-listed: ANY `_merge_overlapping_themes(...)` call in theme_engine.py must pass
    `operator_exempt=`, or that merge pass silently absorbs his promotion (merge 1 AND merge 2 run
    every night)."""
    src = Path(te.__file__).read_text()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_merge_overlapping_themes"]
    assert len(calls) >= 2, "expected the two nightly merge passes"
    missing = [c.lineno for c in calls if "operator_exempt" not in {k.arg for k in c.keywords}]
    assert missing == [], f"_merge_overlapping_themes calls without operator_exempt: lines {missing}"
