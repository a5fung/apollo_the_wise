"""#594 (operator 2026-11-21: "Aligned, but we should keep testing this idea") — the
shelf distance as the SEVENTH recorded ranking of the #533 slot-rank watch.
RECORDS ONLY: no slot allocation, order, entry or size may change.

Pins here:
  1. ONE definition — the analysis scripts' `f3_new` / `adr20_pct` ARE the production
     objects in agents/market_intelligence/shelf_distance.py (identity, not equality);
  2. parity with the evidence — the production entry point, fed the bars BEFORE the gap
     day, reproduces the 11 dmin values of the 2026-11-21 labelled sample (RESULT 7,
     read from the analysis run's own output file) and its P = 0.750;
  3. no look-ahead — the gap day's own bar, present or dropped or corrupted, changes
     nothing; history deeper than 355 sessions changes nothing;
  4. the ranking: dmin DESC, no reading last, ticker ASC tiebreak; an all-NULL board
     is not ranked; stale / missing / bad bars give a reason, never a number;
  5. THE LINE — the board order, the submit order and the returned results are
     identical with the shelf step working, raising, or hanging past its timeout, on
     both sides of the #533 toggle; the row's INSERT does not carry a shelf column;
     the step starts only after the last entry and is never awaited (the schema side
     is held by tests/test_schema_alter_create_parity.py);
  6. fail-open — an error or the timeout leaves NULL, loudly (audit row), never raises.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import re
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import ep_slot_rank_shadow as esr
from agents.market_intelligence import shelf_distance as sd
from agents.market_intelligence.broker import live_tracker as lt
from tests.conftest import make_mock_pool
from tests.fixtures.must_not_trade_charts import CHART_RULINGS, GOOD_CHART, OKISH_CHART
from tests.test_533_slot_ranking import _BOARD_ROWS, _RS_ROWS, _TODAY, _drive

REPO = Path(__file__).resolve().parents[1]
BARS = REPO / "scripts/probes/_594_sample10_1121/q2_bars.out"
RESULT7 = REPO / "scripts/probes/_594_shelf_lead_s10_1121/score_shelf_lead.txt"
_ET = ZoneInfo("America/New_York")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _read_bars() -> dict[tuple[str, str], list]:
    out: dict[tuple[str, str], list] = {}
    cur = None
    for line in BARS.read_text().splitlines():
        if line.startswith("== "):
            t, d = line[3:].split()
            cur = (t, d)
            out[cur] = []
        elif cur and line and line[0].isdigit() and "|" in line:
            td, o, h, l, c, v = line.split("|")
            out[cur].append((td, float(o), float(h), float(l), float(c), float(v)))
    return out


def _read_result7() -> tuple[dict[tuple[str, str], dict], float]:
    rows: dict[tuple[str, str], dict] = {}
    p = None
    for line in RESULT7.read_text().splitlines():
        f = line.split("|")
        if len(f) == 12 and f[0] != "ticker":
            rows[(f[0], f[1])] = dict(
                yes=f[3] == "True", dmin=float(f[4]), structure=f[7],
                shelf_date=f[9], shelf=float(f[10]), adr=float(f[11]))
        m = re.match(r"P\(yes dmin > no dmin\) = ([0-9.]+)", line)
        if m:
            p = float(m.group(1))
    return rows, p


# ── 1. one definition ─────────────────────────────────────────────────────────


def test_the_analysis_scripts_use_the_production_definition():
    f3 = _load("f3_def_594", "scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
    assert f3.f3_new is sd.f3_new
    assert f3.swing_lows is sd.swing_lows
    assert f3.STATED is sd.STATED
    assert f3.PIVOT_WING == sd.PIVOT_WING == 2
    # f3_def.py re-exports: every function it exposes is the production object
    own = [n for n, v in vars(f3).items()
           if inspect.isfunction(v) and v.__module__ != sd.__name__]
    assert own == []
    enc = _load("nbis_594", "scripts/probes/_533_nbis_structure_encoder.py")
    assert enc.adr20_pct is sd.adr20_pct


def test_the_feature_module_is_standard_library_only():
    """The analysis scripts import it offline, and production must never import them."""
    import types
    mods = {v.__name__ for v in vars(sd).values() if isinstance(v, types.ModuleType)}
    assert mods == {"statistics"}
    assert all(getattr(v, "__module__", sd.__name__) in (sd.__name__, "__future__")
               for v in vars(sd).values() if inspect.isfunction(v) or inspect.isclass(v))


# ── 2. parity with RESULT 7 through the production entry point ────────────────


def test_prior_day_bars_reproduce_result_7():
    bars, (expected, p_expected) = _read_bars(), _read_result7()
    assert len(expected) == 11 and p_expected == 0.750
    rulings = [r for r in CHART_RULINGS if r.ruling_date == "2026-11-21"]
    assert {(r.ticker, r.alert_date) for r in rulings} == set(expected)

    got: dict[tuple[str, str], float] = {}
    for key, exp in expected.items():
        days = bars[key]
        assert days[-1][0] == key[1], "the file's last bar is the gap day itself"
        res = sd.shelf_distance_from_prior_days(days[:-1])   # production: no gap-day bar
        assert res["null"] is None
        assert f"{res['dmin']:.3f}" == f"{exp['dmin']:.3f}", key
        assert res["structure"] == exp["structure"]
        assert res["shelf_date"] == exp["shelf_date"]
        assert f"{res['shelf']:.3f}" == f"{exp['shelf']:.3f}"
        assert f"{res['adr']:.3f}" == f"{exp['adr']:.3f}"
        assert res["asof"] == days[-2][0]
        got[key] = res["dmin"]

    yes = [got[(r.ticker, r.alert_date)] for r in rulings
           if r.verdict in (GOOD_CHART, OKISH_CHART)]
    no = [got[(r.ticker, r.alert_date)] for r in rulings
          if r.verdict not in (GOOD_CHART, OKISH_CHART)]
    pairs = [(y, n) for y in yes for n in no]
    p = sum(1.0 if y > n else 0.5 if y == n else 0.0 for y, n in pairs) / len(pairs)
    assert (len(yes), len(no), len(pairs)) == (7, 4, 28)
    assert p == pytest.approx(0.750)


# ── 3. no look-ahead; depth beyond 355 sessions is never read ─────────────────


def test_the_gap_day_bar_is_never_read():
    for key, days in _read_bars().items():
        ia = len(days) - 1
        with_e = sd.f3_new(days, ia, sd.adr20_pct(days, ia))          # analysis convention
        without_e = sd.shelf_distance_from_prior_days(days[:-1])      # production
        junk = days[:-1] + [(days[-1][0], 1e9, 1e9, 1e-9, 1e-9, 0.0)]  # a corrupted gap day
        with_junk = sd.f3_new(junk, ia, sd.adr20_pct(junk, ia))
        for k in ("dmin", "d1", "d2", "shelf", "shelf_date", "structure", "null",
                  "held", "into", "p_date", "s_date", "run_pct", "lows"):
            assert with_e[k] == without_e[k] == with_junk[k], (key, k)


def test_history_deeper_than_355_sessions_changes_nothing():
    assert sd.MAX_SESSIONS_READ == 355
    for key, days in _read_bars().items():
        prior = days[:-1]
        full = sd.shelf_distance_from_prior_days(prior)
        cut = sd.shelf_distance_from_prior_days(prior[-sd.MAX_SESSIONS_READ:])
        for k in ("dmin", "shelf", "shelf_date", "structure", "null"):
            assert full[k] == cut[k], (key, k)
    # and the live fetch window is deeper than that on any calendar
    assert esr.SHELF_BARS_LOOKBACK_DAYS * 5 / 7 * 0.95 > sd.MAX_SESSIONS_READ


def test_thin_history_and_bad_bars_give_a_reason_never_a_number():
    days = next(iter(_read_bars().values()))[:-1]
    thin = sd.shelf_distance_from_prior_days(days[-200:])
    assert thin["dmin"] is None and thin["null"] == "history<250(200)"
    empty = sd.shelf_distance_from_prior_days([])
    assert empty["dmin"] is None and empty["null"] and empty["asof"] is None
    for bad_val in (None, 0.0):
        bad = list(days)
        d = bad[-30]
        bad[-30] = (d[0], d[1], d[2], bad_val, d[4], d[5])
        res = sd.shelf_distance_from_prior_days(bad)
        assert res["dmin"] is None and res["null"] == f"bad_bar({d[0]})"


# ── 4. the ranking ────────────────────────────────────────────────────────────


def test_rank_is_dmin_desc_nulls_last_ticker_tiebreak():
    r = esr.rank_board_by_shelf(
        ["ZZZ", "AAA", "MMM", "BBB", "NUL"],
        {"ZZZ": 2.0, "AAA": -3.0, "MMM": 2.0, "BBB": 5.5, "NUL": None})
    assert r == {"BBB": 1, "MMM": 2, "ZZZ": 3, "AAA": 4, "NUL": 5}
    # input order never decides; it is a permutation (never an admission change)
    r2 = esr.rank_board_by_shelf(
        ["NUL", "BBB", "MMM", "AAA", "ZZZ"],
        {"ZZZ": 2.0, "AAA": -3.0, "MMM": 2.0, "BBB": 5.5})
    assert r2 == r and sorted(r.values()) == [1, 2, 3, 4, 5]


def test_an_all_null_board_is_not_ranked():
    assert esr.rank_board_by_shelf(["B", "A"], {}) == {"B": None, "A": None}


def test_compute_rows_stale_missing_and_real():
    bars = _read_bars()
    twlo = bars[("TWLO", "2026-08-07")][:-1]
    hele = bars[("HELE", "2026-10-08")][:-1]
    latest = twlo[-1][0]
    rows = esr.compute_shelf_rows(
        ["GONE", "HELE", "TWLO"], {"TWLO": twlo, "HELE": hele}, latest)
    by = {r["ticker"]: r for r in rows}
    assert by["TWLO"]["rank_shelf"] == 1 and f"{by['TWLO']['shelf_dmin']:.3f}" == "5.924"
    assert by["TWLO"]["shelf_structure"] == "ok" and by["TWLO"]["shelf_asof"] == latest
    assert by["TWLO"]["shelf_price"] == 139.0 and by["TWLO"]["shelf_null"] is None
    # HELE's own bars end on a different day than the table's latest session
    assert by["HELE"]["shelf_dmin"] is None
    assert by["HELE"]["shelf_null"].startswith("stale_last_bar(")
    assert by["GONE"]["shelf_dmin"] is None and by["GONE"]["shelf_null"] == "no_bars"
    assert (by["GONE"]["rank_shelf"], by["HELE"]["rank_shelf"]) == (2, 3)  # nulls last, ticker ASC


# ── 5. THE LINE: nothing the entry path does can change ───────────────────────


def _bar_rows(ticker: str, days: list, upto: date) -> list[dict]:
    """q2 bars re-dated so the last one is the session before `upto` (asyncpg-like rows)."""
    from datetime import timedelta
    out, d = [], upto
    for b in reversed(days):
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        out.append({"ticker": ticker, "trade_date": d, "open_price": b[1],
                    "high_price": b[2], "low_price": b[3], "close": b[4], "volume": b[5]})
    return list(reversed(out))


def _good_shelf_bars() -> list[dict]:
    bars = _read_bars()
    return (_bar_rows("BTDR", bars[("TWLO", "2026-08-07")][:-1], _TODAY)
            + _bar_rows("LIFE", bars[("CRMD", "2026-08-13")][:-1], _TODAY)
            + _bar_rows("ZBRA", bars[("PCVX", "2026-10-05")][:-1], _TODAY))


async def _hang():
    await asyncio.sleep(3600)


@pytest.mark.asyncio
@pytest.mark.parametrize("toggle", [True, False])
async def test_acting_order_is_identical_with_and_without_the_shelf_step(monkeypatch, toggle):
    monkeypatch.setattr(esr, "SHELF_STEP_TIMEOUT_SEC", 0.05)
    runs = {}
    variants = {
        "no_step": None,                       # the step never starts (pre-#594 behaviour)
        "ok": _good_shelf_bars(),
        "no_bars": (),
        "raises": RuntimeError("bars backend down"),
        "hangs": _hang,
    }
    for name, shelf_bars in variants.items():
        with monkeypatch.context() as mp:
            if shelf_bars is None:
                mp.setattr(lt, "schedule_shelf_ranks", lambda *a, **k: None)
                shelf_bars = ()
            detail: dict = {}
            board, events, inserts = await _drive(
                mp, toggle=toggle, alerts_rows=_BOARD_ROWS, rs_rows=_RS_ROWS,
                shelf_bars=shelf_bars, shelf_latest=date(2026, 8, 27), detail=detail)
            runs[name] = dict(
                board=board, submit=detail["submit_order"], results=detail["results"],
                insert_rows=[tuple(x for i, x in enumerate(r) if i != 2)  # drop recorded_at
                             for r in inserts[0].args[1]],
                events=events, detail=detail)

    base = runs["no_step"]
    assert base["board"] == (["LIFE", "ZBRA", "BTDR"] if toggle else ["BTDR", "LIFE", "ZBRA"])
    assert not base["detail"]["shelf_tasks"]
    for name in ("ok", "no_bars", "raises", "hangs"):
        r = runs[name]
        assert r["board"] == base["board"], name
        assert r["submit"] == base["submit"] == base["board"], name
        assert r["results"] == base["results"], name
        assert r["insert_rows"] == base["insert_rows"], name     # the six-way row is untouched
        assert len(r["detail"]["shelf_tasks"]) == 1, name
        failed = [e for e, _ in r["events"] if e == "slot_rank_shelf_failed"]
        assert len(failed) == (1 if name in ("raises", "hangs") else 0), name
        updates = [c for c in r["detail"]["executemany"] if "UPDATE mi_ep_slot_rank_shadow" in c.args[0]]
        assert len(updates) == (1 if name in ("ok", "no_bars") else 0), name

    # the working step wrote real numbers, ranked on dmin whatever the structure says
    upd = [c for c in runs["ok"]["detail"]["executemany"]
           if "UPDATE mi_ep_slot_rank_shadow" in c.args[0]][0].args[1]
    by = {u[1]: u for u in upd}
    assert {t: f"{by[t][3]:.3f}" for t in by} == {"BTDR": "5.924", "LIFE": "-14.159", "ZBRA": "2.692"}
    assert by["LIFE"][6] == "no_breakout(P<=shelf)"
    assert {t: by[t][10] for t in by} == {"BTDR": 1, "ZBRA": 2, "LIFE": 3}
    # … on exactly the rows the INSERT wrote: same alert_date + recorded_at stamp
    ins = [c for c in runs["ok"]["detail"]["executemany"]
           if "INSERT INTO mi_ep_slot_rank_shadow" in c.args[0]][0].args[1]
    assert {(r[0], r[1], r[2]) for r in ins} == {(u[0], u[1], u[2]) for u in upd}
    assert ins[0][2].tzinfo is not None
    # no-bars board: reasons recorded, no rank invented
    nb = [c for c in runs["no_bars"]["detail"]["executemany"]
          if "UPDATE mi_ep_slot_rank_shadow" in c.args[0]][0].args[1]
    assert all(u[3] is None and u[7] == "no_bars" and u[10] is None for u in nb)


@pytest.mark.asyncio
async def test_the_step_starts_after_the_last_entry_and_is_never_waited_on(monkeypatch):
    """Behavioural placement pin: when the step is started every entry has been
    submitted and the skip digest has run; the function returns while the step is
    still unfinished (a hanging bars read does not hold the return)."""
    monkeypatch.setattr(esr, "SHELF_STEP_TIMEOUT_SEC", 0.3)
    seq: list = []
    detail: dict = {}
    real_schedule = lt.schedule_shelf_ranks

    async def _digest(*a, **k):
        seq.append("digest")

    def _schedule(*a, **k):
        seq.append(("shelf_start", list(detail["submit_order"])))
        task = real_schedule(*a, **k)
        seq.append(("task", task))
        return task

    monkeypatch.setattr(lt, "_send_skip_digest", _digest)
    monkeypatch.setattr(lt, "schedule_shelf_ranks", _schedule)
    done_at_return: list = []
    real_fn = lt.process_new_alerts_live

    async def _wrapped(*a, **k):
        out = await real_fn(*a, **k)
        done_at_return.extend(t.done() for t in esr._SHELF_TASKS)
        return out

    monkeypatch.setattr(lt, "process_new_alerts_live", _wrapped)
    board, events, _ins = await _drive(
        monkeypatch, toggle=True, alerts_rows=_BOARD_ROWS, rs_rows=_RS_ROWS,
        shelf_bars=_hang, shelf_latest=date(2026, 8, 27), detail=detail)
    assert seq[0] == "digest"
    assert seq[1] == ("shelf_start", board) and len(board) == 3   # all three already submitted
    assert done_at_return == [False]                              # returned without waiting
    assert [e for e, _ in events].count("slot_rank_shelf_failed") == 1   # then cut off, loudly


def test_the_rows_insert_carries_no_shelf_column_and_the_update_only_shelf_columns():
    assert "shelf" not in esr._INSERT_SQL          # a shelf fault cannot cost the six-way row
    set_clause = esr._SHELF_UPDATE_SQL.split("SET")[1].split("WHERE")[0]
    assert set(re.findall(r"(\w+) = \$", set_clause)) == {
        "shelf_dmin", "shelf_price", "shelf_date", "shelf_structure", "shelf_null",
        "shelf_adr20_pct", "shelf_asof", "rank_shelf"}
    assert "WHERE alert_date = $1 AND ticker = $2 AND recorded_at = $3" in esr._SHELF_UPDATE_SQL
    assert not inspect.iscoroutinefunction(esr.schedule_shelf_ranks)


def test_bars_are_prior_day_only_and_date_bounded():
    assert "trade_date < $2" in esr._SHELF_BARS_SQL and "trade_date >= $3" in esr._SHELF_BARS_SQL
    assert "<=" not in esr._SHELF_BARS_SQL
    assert "trade_date < $1" in esr._SHELF_LATEST_SESSION_SQL


# ── 6. fail-open ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_step_never_raises_and_audits_on_failure(monkeypatch):
    events = []

    async def _audit(event, msg, *a, **k):
        events.append((event, msg))

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "log_audit_event", _audit)
    pool = MagicMock()
    pool.acquire = MagicMock(side_effect=RuntimeError("pool down"))
    n = await esr.record_shelf_ranks(
        pool, ["AAA"], _TODAY, datetime(2026, 8, 28, 9, 31, tzinfo=_ET), "cron_9_31")
    assert n == 0
    assert [e for e, _ in events] == ["slot_rank_shelf_failed"]
    assert "cron_9_31" in events[0][1] and "pool down" in events[0][1]


@pytest.mark.asyncio
async def test_step_is_cut_off_at_its_timeout(monkeypatch):
    monkeypatch.setattr(esr, "SHELF_STEP_TIMEOUT_SEC", 0.05)
    events = []

    async def _audit(event, msg, *a, **k):
        events.append(event)

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "log_audit_event", _audit)
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)

    async def _slow(*a, **k):
        await asyncio.sleep(3600)

    conn.fetch = AsyncMock(side_effect=_slow)
    conn.executemany = AsyncMock()
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    n = await esr.record_shelf_ranks(
        pool, ["AAA"], _TODAY, datetime(2026, 8, 28, 9, 31, tzinfo=_ET), "bar_stream")
    assert n == 0 and loop.time() - t0 < 2.0
    assert events == ["slot_rank_shelf_failed"]
    conn.executemany.assert_not_called()


@pytest.mark.asyncio
async def test_empty_board_touches_nothing():
    pool = MagicMock()
    assert await esr.record_shelf_ranks(pool, [], _TODAY, datetime.now(_ET)) == 0
    pool.acquire.assert_not_called()


def test_the_default_timeout_is_a_few_seconds():
    assert 0 < esr.SHELF_STEP_TIMEOUT_SEC <= 10
