"""#655 (2026-09-27): the signed theme-correctness test's nightly scorer.

(a) ANCHOR — the pure G1-G4 functions run on scripts/probes/_655/grouping/'s captured inputs and
    must reproduce the probe's own numbers (G1 534/589, G2 20/589, G3 103/118, G4 10/118) — the
    numbers the operator signed the bars against. closes.psv is gitignored; if it is absent on
    this machine the G1-G3 half is skipped with a stated reason (G4 needs only live_themes.psv and
    always runs).
(b) Small hand-built fixtures that RED-prove each bar's DIRECTION (a clean board passes, a single
    mutation fails it) — G1/G2 (a "traitor" ticker), G3 (a themed group vs an unstructured one),
    G4 (a 2-member theme), and the latency read (a fast birth passes, a slow one fails, a re-mint
    is excluded from the median).
(c) The nightly runner writes ONE audit row on a working load, survives a failing one (error row +
    notify_job_failure, never raises), and is registered in the detector-liveness registry.
"""
import asyncio
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from unittest.mock import AsyncMock

import numpy as np
import pytest

import agents.market_intelligence.theme_correctness as tc
from agents.market_intelligence import market_adjusted_correlation as mac

GROUPING_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "probes", "_655", "grouping")


def _d(s: str) -> date:
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def _load_live_themes() -> list[dict]:
    path = os.path.join(GROUPING_DIR, "live_themes.psv")
    themes = []
    with open(path) as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            themes.append({"name": p[0], "stage": p[1],
                          "tickers": [t for t in p[4].split(",") if t]})
    return themes


def _load_closes() -> dict[str, dict[date, float]]:
    path = os.path.join(GROUPING_DIR, "closes.psv")
    closes: dict[str, dict[date, float]] = defaultdict(dict)
    with open(path) as f:
        for line in f:
            t, dt, c = line.rstrip("\n").split("|")
            if c:
                closes[t][_d(dt)] = float(c)
    return closes


def _load_scores() -> dict[str, dict]:
    path = os.path.join(GROUPING_DIR, "scores_0925.psv")
    scores = {}
    with open(path) as f:
        for line in f:
            t, rank, comp, sec, adv, mcap, cl = line.rstrip("\n").split("|")
            scores[t] = {"rs": float(comp) if comp else None, "sector": sec or None}
    return scores


def _load_sector(scores: dict[str, dict]) -> dict[str, str]:
    path = os.path.join(GROUPING_DIR, "overrides.psv")
    sector = {}
    with open(path) as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) >= 2 and p[1]:
                sector[p[0]] = p[1]
    for t, s in scores.items():
        if s.get("sector"):
            sector[t] = s["sector"]
    return sector


def _load_theme_history() -> dict[str, dict[date, set]]:
    path = os.path.join(GROUPING_DIR, "theme_history.psv")
    hist: dict[str, dict[date, set]] = defaultdict(dict)
    with open(path) as f:
        for line in f:
            dt, name, stage, tk = line.rstrip("\n").split("|")
            if stage == "Retired":
                continue
            hist[name][_d(dt)] = set(t for t in tk.split(",") if t)
    return hist


# ── (a) ANCHOR ──────────────────────────────────────────────────────────────────────────────────
def test_anchor_g4_reproduces_the_probe_without_closes():
    """G4 needs only live_themes.psv (always committed) — no closes, no skip condition."""
    themes = _load_live_themes()
    g4 = tc.compute_g4(themes)
    assert (g4["small"], g4["n_board"]) == (10, 118)


@pytest.mark.skipif(
    not os.path.exists(os.path.join(GROUPING_DIR, "closes.psv")),
    reason="scripts/probes/_655/grouping/closes.psv is gitignored (4.7MB price capture) — "
          "absent on this machine, so the G1-G3 anchor (which needs excess returns) is skipped.")
def test_anchor_g1_g2_g3_reproduce_the_probes_signed_numbers():
    themes = _load_live_themes()
    closes = _load_closes()
    scores = _load_scores()
    sector = _load_sector(scores)

    run_date = date(2026, 9, 26)  # closes.psv's own capture convention (through 2026-09-25)
    sessions = mac.session_index(closes["SPY"], run_date)
    spy_r = mac.log_returns(closes["SPY"], sessions)
    excess = mac.excess_returns({t: c for t, c in closes.items() if t != "SPY"}, sessions, spy_r)
    usable = tc.usable_set(excess)

    g1g2 = tc.compute_g1_g2(themes, excess)
    assert (g1g2["g1"]["pass"], g1g2["g1"]["n"]) == (534, 589), \
        "G1 must reproduce the probe's signed 534 of 589 — the number the 90% bar was set against"
    assert (g1g2["g2"]["flagged"], g1g2["g2"]["n"]) == (20, 589), \
        "G2 must reproduce the probe's signed 20 of 589"

    g3 = tc.compute_g3(themes, excess, usable, scores, sector)
    assert (g3["pass"], g3["n_judgeable"]) == (103, 118), \
        "G3 must reproduce the probe's signed 103 of 118 (RNG-stream-sensitive — see module docstring)"


def test_g1_bar_pinned_to_the_engines_own_admission_bar():
    """G1_BAR is kept as a literal (theme_engine.py pulls in anthropic at import time — these are
    pure functions that must stay light) — pin it so it can never silently drift from the live
    engine's ASSIGN_COMOVE_BAR."""
    from agents.market_intelligence import theme_engine
    assert tc.G1_BAR == theme_engine.ASSIGN_COMOVE_BAR


# ── (b) hand-built RED-proof fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def factor_excess():
    """Two independent 'factors' (40 sessions, >= the 30-session judge floor) and small-noise
    members riding each — a clean group ties ~0.9+ to itself and ~0 to the other."""
    rng = np.random.default_rng(42)
    n = 40
    fa = rng.normal(0, 1.0, n)
    fb = rng.normal(0, 1.0, n)
    excess = {}
    for t in ["A1", "A2", "A3", "A4"]:
        excess[t] = fa + rng.normal(0, 0.15, n)
    for t in ["B0", "B1", "B2", "B3"]:
        excess[t] = fb + rng.normal(0, 0.15, n)
    excess["B4"] = fa + rng.normal(0, 0.15, n)  # a traitor: lives under B, moves like A
    return excess


def test_g1_g2_pass_on_a_clean_board_and_fail_on_one_traitor(factor_excess):
    clean = [
        {"name": "Theme A", "stage": "Mainstream", "tickers": ["A1", "A2", "A3", "A4"]},
        {"name": "Theme B", "stage": "Mainstream", "tickers": ["B0", "B1", "B2", "B3"]},
    ]
    good = tc.compute_g1_g2(clean, factor_excess)
    assert good["g1"]["pass_bar"] is True and good["g1"]["rate_pct"] == 100.0
    assert good["g2"]["pass_bar"] is True and good["g2"]["flagged"] == 0

    traitor = [
        {"name": "Theme A", "stage": "Mainstream", "tickers": ["A1", "A2", "A3", "A4"]},
        {"name": "Theme B", "stage": "Mainstream", "tickers": ["B0", "B1", "B2", "B4"]},  # B3 -> B4
    ]
    bad = tc.compute_g1_g2(traitor, factor_excess)
    assert bad["g1"]["pass_bar"] is False and bad["g1"]["rate_pct"] < 90.0
    assert bad["g2"]["pass_bar"] is False
    assert ("B4", "Theme B", "Theme A") in bad["g2"]["list"]


def test_g4_passes_at_zero_small_themes_and_fails_on_one_two_member_theme():
    board = [
        {"name": "T1", "stage": "Mainstream", "tickers": ["A", "B", "C"]},
        {"name": "T2", "stage": "Mainstream", "tickers": ["D", "E", "F"]},
    ]
    ok = tc.compute_g4(board)
    assert ok["pass_bar"] is True and ok["small"] == 0

    board_small = board + [{"name": "Tiny", "stage": "Nascent", "tickers": ["G", "H"]}]
    bad = tc.compute_g4(board_small)
    assert bad["pass_bar"] is False and bad["list"] == ["Tiny"]



# ── G4 settled (operator 2026-10-08: keep rule B's wait, report G4 two ways) ─────────────────────
_TONIGHT = date(2026, 10, 8)


def _row(name, n, *, stage="Fading", rs_avg=None, d=_TONIGHT):
    return {"name": name, "stage": stage, "rs_avg": rs_avg, "theme_date": d,
            "tickers": [f"{name}{i}" for i in range(n)]}


def _hist(name, n, d):
    return {"date": d, "name": name, "tickers": [f"{name}{i}" for i in range(n)]}


def test_waiting_night_holds_only_a_newly_shrunk_weak_fading_theme():
    board = [
        _row("Shrunk", 2),                              # 4 last night -> held tonight
        _row("New", 1),                                 # no previous night -> held
        _row("StaleOnly", 2),                           # previous row 9 days back -> no prior -> held
        _row("AlreadySmall", 2),                        # 2 last night -> retire-eligible, not waiting
        _row("Scored", 2, rs_avg=71.0),                 # numeric rs_avg -> the scored path, never held
        _row("Live", 2, stage="Nascent"),               # not Fading
        _row("Big", 3),                                 # not under 3
    ]
    yday = _TONIGHT - timedelta(days=1)
    history = [
        _hist("Shrunk", 4, yday), _hist("Shrunk", 2, _TONIGHT),   # tonight's own row is not "prior"
        _hist("StaleOnly", 2, _TONIGHT - timedelta(days=9)),
        _hist("AlreadySmall", 5, _TONIGHT - timedelta(days=3)), _hist("AlreadySmall", 2, yday),
        _hist("Scored", 5, yday), _hist("Live", 5, yday), _hist("Big", 5, yday),
    ]
    assert tc.waiting_night_names(board, history) == {"Shrunk", "New", "StaleOnly"}


def test_waiting_night_agrees_with_rule_b_itself():
    """Same verdict as the engine's own predicate on the same rows: held = the weak-Fading shape
    AND NOT already waited a night — computed by theme_engine, not re-derived here."""
    import agents.market_intelligence.theme_engine as te
    yday = _TONIGHT - timedelta(days=1)
    cases = [(2, 4), (1, None), (2, 2), (1, 1), (2, 3), (3, 2)]
    board = [_row(f"T{i}", n) for i, (n, _p) in enumerate(cases)]
    history = [_hist(f"T{i}", p, yday) for i, (_n, p) in enumerate(cases) if p is not None]
    prior = te._prior_member_counts(
        [{"name": h["name"], "tickers": h["tickers"], "theme_date": h["date"]} for h in history],
        _TONIGHT)
    expect = {th["name"] for th in board
              if te._is_weak_fading_shape(th) and not te._waited_a_night(prior.get(th["name"]))}
    assert tc.waiting_night_names(board, history) == expect == {"T0", "T1", "T4"}


def test_g4_settled_drops_the_held_themes_and_leaves_the_signed_bar_alone():
    board = [{"name": f"T{i}", "stage": "Mainstream", "tickers": ["A", "B", "C"]} for i in range(8)]
    board += [{"name": "Held", "stage": "Fading", "tickers": ["X"]},
              {"name": "Tiny", "stage": "Nascent", "tickers": ["Y", "Z"]}]
    g4 = tc.compute_g4(board, waiting={"Held", "NotOnBoard"})
    assert (g4["small"], g4["n_board"], g4["rate_pct"], g4["pass_bar"]) == (2, 10, 20.0, False)
    st = g4["settled"]
    assert (st["small"], st["n_board"], st["rate_pct"], st["pass_bar"]) == (1, 9, 11.1, False)
    assert st["list"] == ["Tiny"] and st["waiting"] == ["Held"]
    assert tc.compute_g4(board)["settled"]["small"] == 2      # nothing held -> same as the bar


def test_wait_literals_match_the_engine():
    import inspect
    import agents.market_intelligence.db as db
    import agents.market_intelligence.theme_engine as te
    assert tc.WAIT_SMALL_MIN_MEMBERS == te.SMALL_FADING_RETIRE_MIN_MEMBERS
    assert tc.WAIT_PRIOR_WINDOW_DAYS == (
        inspect.signature(db.get_active_themes).parameters["stale_after_days"].default)


def test_g3_passes_a_real_group_and_fails_an_unstructured_one(factor_excess):
    rng = np.random.default_rng(7)
    excess = dict(factor_excess)
    for i in range(30):
        excess[f"F{i}"] = rng.normal(0, 1.0, 40)  # filler universe, no shared factor
    usable = tc.usable_set(excess)
    scores = {t: {"rs": 50.0} for t in excess}
    themes = [
        {"name": "Theme A", "stage": "Mainstream", "tickers": ["A1", "A2", "A3", "A4"]},
        {"name": "Fake Theme", "stage": "Nascent", "tickers": ["F0", "F1", "F2", "F3"]},
    ]
    g3 = tc.compute_g3(themes, excess, usable, scores, {}, n_draws=200)
    by_name = {r["name"]: r for r in g3["themes"]}
    assert by_name["Theme A"]["pass_g3"] is True
    assert by_name["Fake Theme"]["pass_g3"] is False


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_latency_bar_direction_and_remint_exclusion():
    session_dates = _weekdays(date(2026, 7, 1), 90)

    def sess(i):
        return session_dates[i]

    run_date = sess(80)

    # a FAST birth (lag 8, <= the 10-session bar) alone -> passes
    fast_hist = [{"date": run_date, "name": "New Group", "stage": "Nascent",
                 "tickers": ["X1", "X2", "X3"]}]
    fast_clusters = {sess(80 - 8): {"clA": {"X1", "X2"}}}
    fast = tc.compute_theme_latency(fast_hist, [], fast_clusters, session_dates, run_date)
    assert fast["median_sessions"] == 8 and fast["pass_bar"] is True
    assert fast["tonight_births"] == [{"name": "New Group", "lag": 8, "remint": False}]

    # a SLOW birth (lag 15, > the bar) alone -> fails
    slow_date = sess(77)
    slow_hist = [{"date": slow_date, "name": "Late Group", "stage": "Nascent",
                 "tickers": ["Y1", "Y2", "Y3"]}]
    slow_clusters = {sess(77 - 15): {"clB": {"Y1", "Y2"}}}
    slow = tc.compute_theme_latency(slow_hist, [], slow_clusters, session_dates, run_date)
    assert slow["median_sessions"] == 15 and slow["pass_bar"] is False

    # a RE-MINT: founders Z1/Z2/Z3 already sat >= half in a live theme ("Old Home", 5 members so
    # its Jaccard overlap with the birth stays < 0.4 — this must go through `held_between`, not
    # the rename-continuity merge) on a board night between first sighting and birth -> excluded
    # from the median even though it has a measured (short) lag.
    remint_date = sess(75)
    remint_hist = [{"date": remint_date, "name": "Remint Group", "stage": "Nascent",
                   "tickers": ["Z1", "Z2", "Z3"]}]
    for k in range(75 - 8, 75 - 2):
        remint_hist.append({"date": sess(k), "name": "Old Home", "stage": "Nascent",
                            "tickers": ["Z1", "Z2", "Q1", "Q2", "Q3"]})
    remint_clusters = {sess(75 - 9): {"clC": {"Z1", "Z2"}}}
    combined = fast_hist + slow_hist + remint_hist
    combined_clusters = {**fast_clusters, **slow_clusters, **remint_clusters}
    out = tc.compute_theme_latency(combined, [], combined_clusters, session_dates, run_date)
    assert out["remints"] == 1
    # the median must be over {New Group=8, Late Group=15} ONLY — Remint Group's own lag (9) is
    # excluded despite having a measured pre-birth cluster.
    assert out["new_n"] == 2 and out["median_sessions"] == 11.5 and out["pass_bar"] is False


# ── (c) the nightly runner ───────────────────────────────────────────────────────────────────────
class _FakeConn:
    def __init__(self, scores_rows=(), hist_rows=(), rename_rows=(), cluster_rows=(),
                score_date=None):
        self.scores_rows, self.hist_rows = list(scores_rows), list(hist_rows)
        self.rename_rows, self.cluster_rows = list(rename_rows), list(cluster_rows)
        self.score_date = score_date

    async def fetchrow(self, sql, *args):
        if "MAX(score_date)" in sql:
            return {"d": self.score_date}
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetch(self, sql, *args):
        if "mi_stock_scores" in sql:
            return self.scores_rows
        if "mi_theme_renames" in sql:
            return self.rename_rows
        if "mi_correlation_clusters" in sql:
            return self.cluster_rows
        if "mi_themes" in sql:
            return self.hist_rows
        raise AssertionError(f"unexpected fetch: {sql}")


@pytest.fixture
def wired(monkeypatch):
    import agents.market_intelligence.db as db
    import core.notifications as cn
    log, fail = AsyncMock(), AsyncMock()
    monkeypatch.setattr(db, "log_audit_event", log)
    monkeypatch.setattr(cn, "notify_job_failure", fail)
    return log, fail


def test_a_failed_board_load_writes_an_error_row_and_pages(wired, monkeypatch):
    log, fail = wired
    import agents.market_intelligence.db as db

    async def _boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "get_active_themes", _boom)
    out = asyncio.run(tc.run_theme_correctness_check(conn=_FakeConn()))
    assert out["errors"] and out["report"] is None
    fail.assert_awaited_once()
    detail = json.loads(log.await_args.args[2])
    assert detail["status"] == "error"


def test_a_working_night_writes_one_audit_row_with_the_report(wired, monkeypatch):
    log, fail = wired
    import agents.market_intelligence.db as db
    import agents.market_intelligence.ep_theme_belonging as etb
    import shared.dates as shared_dates

    today = date(2026, 9, 26)
    monkeypatch.setattr(shared_dates, "et_today", lambda: today)

    board = [{"name": "Tiny Theme", "stage": "Nascent", "tickers": ["AAA", "BBB"]}]
    monkeypatch.setattr(db, "get_active_themes", AsyncMock(return_value=board))

    spy_closes = {today - timedelta(days=i): 100.0 + i * 0.1 for i in range(1, 40)}

    async def _fake_fetch_closes(tickers, start, end):
        return {"SPY": spy_closes}, len(spy_closes)

    monkeypatch.setattr(etb, "fetch_closes", _fake_fetch_closes)

    out = asyncio.run(tc.run_theme_correctness_check(conn=_FakeConn(score_date=today)))
    assert not out["errors"], out["errors"]
    assert out["report"] is not None
    fail.assert_not_awaited()
    log.assert_awaited_once()
    assert log.await_args.args[0] == "theme_correctness_check"
    detail = json.loads(log.await_args.args[2])
    assert "g1" in detail and "g2" in detail and "g3" in detail and "g4" in detail
    assert "latency" in detail
    assert detail["g4"]["settled"]["waiting"] == []
    assert "settled 1/1" in log.await_args.args[1]


def test_the_check_is_in_the_liveness_registry():
    from agents.market_intelligence import health_checks as hc
    labels = [e[1] for e in hc._DETECTOR_LIVENESS_TABLES]
    assert "theme correctness check (#655)" in labels
