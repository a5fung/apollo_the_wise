#!/usr/bin/env python3
"""#314 replay — the plan's executable positive controls that run on SYNTHETIC bars (plan §Parity): the walk goldens through the
runner's own loader, and the seal-safe synthetic detector golden (one climax series + four one-gate-off copies). The EXPECTED values
of the detector golden live in tests/test_parabolic_short_replay.py (`DETECTOR_GOLDEN_EXPECTED`, written before it was first run);
the runner reads them from that file and refuses STEP 0 / the walk on any mismatch. Nothing here reads a real bar.

READINGS (continued; the main loop decides):
  R41 The walk goldens' fixture lives in tests/test_parabolic_short_shadow.py (pinned) and is dated 2026 (after the seal). The runner
      maps the fixture's 48 weekdays one-for-one onto the 48 weekdays from 2023-07-03 (R5; era A's copy from 2019-07-01, inside its
      file's span) on BOTH sides, writes them in the export's
      layout (headerless ticker,date,o,h,l,c,v; the fixture's own weekdays as SPY), reads them back through `ps_population.load_era`
      (era B's loader: the split list empty) and compares `replay_episode` on the loaded dicts with `replay_episode` on the fixture
      dicts with every number made a float (the export holds floats) — `repr` equality, i.e. byte-equal. The scenarios are DERIVED by
      running the four test classes with `replay_episode` / `trigger_fill` / `arm_geometry` recorded (tests/..._replay.py), never
      hand-listed; the runner's own refusal check runs the two registered goldens (time stop 5 and 3).
  R42 The two golden numbers are checked on the fixture as it is (31 history rows) AND through `ps_walk.walk_one` on the fixture padded
      to 120 history rows with the same flat bar (ATR14 reads only the last 14 bars, so the numbers cannot move) — the walk path the
      replay uses, not only the pure function.
  R43 The detector golden's "failing checks" of a night that passed the qualifying gates are the climax conditions it misses:
      burst_score < 3, not gapped_today, not climax_volume_flag, days_up_streak < 3, is_earnings_today. A night stopped at a
      qualifying gate fails exactly that gate (`ps_population.gate_of`).
"""
from __future__ import annotations

import gzip
import importlib.util
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402

GuardStop = X.GuardStop
SHADOW_TESTS = os.path.join(X.REPO, "tests", "test_parabolic_short_shadow.py")
REPLAY_TESTS = os.path.join(X.REPO, "tests", "test_parabolic_short_replay.py")
GOLDEN_R5, GOLDEN_R3 = 1.200260078, 0.969079613          # the plan's walk goldens (computed 10-22 from the pure function)
GOLDEN_TOL = 1e-9
REDATE_START = date(2023, 7, 3)
REDATE_START_A = date(2019, 7, 1)                        # era A's loader cuts at its own file end (2022-06-30): its copy is dated 2019


def bdays(start: date, n: int) -> list:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def shadow_tests_module():
    """tests/test_parabolic_short_shadow.py loaded by path (its fixtures: DAYS, market, TRIGGER_THEN_TIME_STOP, STOP, N_HIST, D)."""
    name = "_ps314_shadow_tests"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SHADOW_TESTS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def redate_map(T) -> dict:
    """R41: the fixture's weekdays -> the same count of weekdays from 2023-07-03."""
    return dict(zip(T.DAYS, bdays(REDATE_START, len(T.DAYS))))


def redate_rows(rows: list, dmap: dict) -> list:
    """Re-dated copies with every number a float (the export's layout holds floats); a None price stays None."""
    out = []
    for r in rows:
        q = dict(r)
        q["trade_date"] = dmap[r["trade_date"]]
        for k in ("open_price", "high_price", "low_price", "close", "volume"):
            if q.get(k) is not None:
                q[k] = float(q[k])
        out.append(q)
    return out


def redate_kwargs(kw: dict, dmap: dict) -> dict:
    out = dict(kw)
    if isinstance(out.get("armed_on"), date):
        out["armed_on"] = dmap[out["armed_on"]]
    if out.get("earnings_after"):
        out["earnings_after"] = frozenset(dmap[d] for d in out["earnings_after"])
    return out


def write_export(path: str, series: dict, spy_dates: list) -> None:
    """Headerless ticker,date,o,h,l,c,v (the export's layout), gzip; SPY on every calendar date (flat 100)."""
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for d in spy_dates:
            fh.write(f"SPY,{d.isoformat()},100.0,100.0,100.0,100.0,1000000.0\n")
        for tk, rows in series.items():
            for r in rows:
                fh.write(f"{tk},{r['trade_date'].isoformat()},{float(r['open_price'])!r},{float(r['high_price'])!r},"
                         f"{float(r['low_price'])!r},{float(r['close'])!r},{float(r['volume'])!r}\n")


def roundtrip(rows: list, tmpdir: str, spy_dates: list, ticker: str = "GOLD", era: str = "B") -> list:
    """`rows` written in the export layout and read back through the era's loader (`ps_population.load_era`; era A with its sessions
    file and a raw-close companion equal to the close) -> the detector / walk dicts."""
    import ps_population as PP
    os.makedirs(tmpdir, exist_ok=True)
    exp = os.path.join(tmpdir, "daily_closes_all.csv.gz")
    keep = [r for r in rows if r.get("low_price") is not None]
    write_export(exp, {ticker: keep}, spy_dates)
    if era == "B":
        spl = os.path.join(tmpdir, "cb702_splits.psv")
        open(spl, "w").close()
        P = X.Paths(data=tmpdir, out=os.path.join(tmpdir, "out"), here=tmpdir, export_B=exp, splits_B=spl)
    else:
        raw = os.path.join(tmpdir, "daily_raw_close.csv.gz")
        with gzip.open(raw, "wt", encoding="utf-8") as fh:
            for d in spy_dates:
                fh.write(f"SPY,{d.isoformat()},100.0\n")
            for r in keep:
                fh.write(f"{ticker},{r['trade_date'].isoformat()},{float(r['close'])!r}\n")
        sess = os.path.join(tmpdir, "sessions.txt")
        with open(sess, "w") as fh:
            fh.write("\n".join(d.isoformat() for d in spy_dates) + "\n")
        P = X.Paths(data=tmpdir, out=os.path.join(tmpdir, "out"), here=tmpdir, export_A=exp, raw_A=raw, sessions_A=sess)
    e = PP.load_era(P, era)
    return PP.ticker_dicts(e, e.tid[ticker])


def golden_rows(T, dmap: dict, pad_to: int = 0) -> tuple:
    """(rows, ci, kwargs) of TRIGGER_THEN_TIME_STOP re-dated; `pad_to` prepends flat history bars (100, 101, 99, 100) on earlier weekdays."""
    rows = redate_rows(T.market(T.TRIGGER_THEN_TIME_STOP), dmap)
    ci = T.N_HIST
    if pad_to and ci + 1 < pad_to:
        extra = pad_to - (ci + 1)
        first = rows[0]["trade_date"]
        days, d = [], first - timedelta(days=1)
        while len(days) < extra:
            if d.weekday() < 5:
                days.append(d)
            d -= timedelta(days=1)
        pre = [{"trade_date": dd, "open_price": 100.0, "high_price": 101.0, "low_price": 99.0, "close": 100.0, "volume": 2_000_000.0}
               for dd in reversed(days)]
        rows = pre + rows
        ci += extra
    return rows, ci, {"stop_price": T.STOP, "armed_on": rows[ci]["trade_date"]}


def walk_goldens(tmpdir: str, say=print) -> list:
    """The two registered walk goldens (time stop 5: 1.200260078 on D5; time stop 3: 0.969079613 on D3), on the fixture as it is,
    through the export layout + loader, and through `walk_one` on 120 history rows (R42). -> the problems (empty = pass)."""
    import ps_walk as W
    from agents.market_intelligence import parabolic_short_shadow as psh
    T = shadow_tests_module()
    dmap = redate_map(T)
    problems = []
    rows, ci, kw = golden_rows(T, dmap)
    for ts, want, d_want in ((5, GOLDEN_R5, T.D[5]), (3, GOLDEN_R3, T.D[3])):
        r = psh.replay_episode(rows, ci, time_stop=ts, **kw)
        o = r.get("outcome") or {}
        got = o.get("realized_r")
        ok = o.get("status") == "settled" and o.get("reason") == "time_stop" and got is not None and abs(got - want) <= GOLDEN_TOL \
            and o.get("date") == dmap[d_want] and r["trigger"]["entry_price"] == 140.0 and r["trigger"]["kind"] == "intraday"
        say(f"  walk golden time_stop={ts}: {o.get('status')} {o.get('reason')} on {o.get('date')}, entry {r['trigger']['entry_price']} "
            f"{r['trigger']['kind']}, R {got!r} (registered {want}) -> {'OK' if ok else 'MISMATCH'}")
        if not ok:
            problems.append(f"walk golden time_stop={ts}: R {got!r} != {want}")
        if ts == 5 and abs((o.get("flush_price") or 0) - 116.93) > 1e-9:
            problems.append(f"walk golden: flush price {o.get('flush_price')} != 116.93")
    spy = sorted(dmap.values())
    for era, start in (("A", REDATE_START_A), ("B", REDATE_START)):     # era-agnostic: both files share the layout; each era's loader
        dm = dict(zip(T.DAYS, bdays(start, len(T.DAYS))))
        rows_e, ci_e, kw_e = golden_rows(T, dm)
        loaded = roundtrip(rows_e, os.path.join(tmpdir, f"golden_rt_{era}"), sorted(dm.values()), era=era)
        for ts in (5, 3):
            a = psh.replay_episode(rows_e, ci_e, time_stop=ts, **kw_e)
            b = psh.replay_episode(loaded, ci_e, time_stop=ts, **kw_e)
            if repr(a) != repr(b):
                problems.append(f"walk golden time_stop={ts}: era {era}'s loader gives a different replay")
    say(f"  walk goldens through the export layout and both eras' loaders: {'byte-equal' if not any('loader' in p for p in problems) else 'DIFFER'}")
    prow, pci, pkw = golden_rows(T, dmap, pad_to=X.HISTORY)
    spy_p = sorted({r["trade_date"] for r in prow} | set(spy))
    loaded_p = roundtrip(prow, os.path.join(tmpdir, "golden_rt120"), spy_p)
    ci_arr = list(range(len(loaded_p)))
    ep = W.walk_one(loaded_p, ci_arr, pci, loaded_p[pci]["trade_date"].isoformat(), [d.isoformat() for d in spy_p],
                    spy_p[-1].isoformat(), None, None)
    for lab, want in (("r5", GOLDEN_R5), ("r3", GOLDEN_R3)):
        got = ep.get(f"{lab}_r")
        ok = ep.get(f"{lab}_status") == "settled" and got is not None and abs(got - want) <= GOLDEN_TOL
        say(f"  walk golden through walk_one on 120 history rows ({lab}): R {got!r} -> {'OK' if ok else 'MISMATCH'}")
        if not ok:
            problems.append(f"walk_one golden {lab}: {got!r} != {want}")
    return problems


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the synthetic detector golden (plan §Parity: the seal-safe REFUSING detector check)
# ═════════════════════════════════════════════════════════════════════════════════════════════
GOLDEN_CAP = 5_000_000_000
COPIES = ("climax", "streak_2", "earnings_today", "gap_1_9pct", "volume_one_under")


def detector_series(copy: str = "climax") -> tuple:
    """(rows, is_earnings_today) — 100 flat sessions then a 20-session accelerating run with a 3% gap up every day, rising range and
    rising volume; the copies change ONE thing: `streak_2` puts a small down close three sessions before the climax day (the AGL
    class), `earnings_today` passes is_earnings_today=True (the XMTR class), `gap_1_9pct` opens the climax day 1.9% over the prior
    close (under the 2% `gapped_today` cut), `volume_one_under` gives the climax day one share under its 20-session high."""
    if copy not in COPIES:
        raise ValueError(copy)
    days = bdays(date(2019, 1, 2), X.HISTORY)
    rows = []
    for i in range(100):
        rows.append({"trade_date": days[i], "open_price": 10.0, "high_price": 10.2, "low_price": 9.8, "close": 10.0, "volume": 1_000_000.0})
    close = 10.0
    for k in range(20):
        i = 100 + k
        growth = 0.03 + 0.006 * k                       # the daily rate accelerates: velocity 5d >> 20d
        prev = close
        open_ = round(prev * 1.03, 4)                   # a 3% gap every day (gap_count_3d = 3, gapped_today)
        close = round(prev * (1.0 + growth + 0.03), 4)
        if copy == "streak_2" and i == 117:
            close = round(prev * 0.995, 4)              # one small down close: days_up_streak on the climax day = 2
        if copy == "gap_1_9pct" and i == 119:
            open_ = round(prev * 1.019, 4)
        rng = 0.02 * prev * (1.0 + 0.15 * k)            # widening range (range_expansion_count_3d = 3)
        high = round(max(open_, close) + rng / 2, 4)
        low = round(min(open_, close) - rng / 2, 4)
        vol = 2_000_000.0 + 400_000.0 * k               # rising volume: the climax day is the 20-session high
        rows.append({"trade_date": days[i], "open_price": open_, "high_price": high, "low_price": low, "close": close, "volume": vol})
    if copy == "volume_one_under":
        rows[-1]["volume"] = max(r["volume"] for r in rows[-20:-1]) - 1.0
    return rows, (copy == "earnings_today")


def failing_checks(res: dict) -> set:
    """R43: the checks a night misses on the way to `climax`."""
    import ps_population as PP
    if res.get("stage") == "climax":
        return set()
    if res.get("stage") == "unqualified":
        return {PP.gate_of(res)}
    out = set()
    if (res.get("score") or 0) < 3:
        out.add("burst_score")
    if not res.get("gapped_today"):
        out.add("gapped_today")
    if not res.get("climax_volume_flag"):
        out.add("climax_volume")
    if (res.get("days_up_streak") or 0) < 3:
        out.add("days_up_streak")
    if res.get("is_earnings_today"):
        out.add("earnings")
    return out


def detector_golden_results() -> dict:
    """{copy: (stage, sorted failing checks, days_up_streak)} under the PINNED module at market_cap = 5,000,000,000."""
    from agents.market_intelligence import parabolic_detector as pdm
    out = {}
    for copy in COPIES:
        rows, earn = detector_series(copy)
        res = pdm.compute_parabolic_metrics(rows, market_cap=GOLDEN_CAP, is_earnings_today=earn)
        out[copy] = (res.get("stage"), tuple(sorted(failing_checks(res))), res.get("days_up_streak"))
    return out


def detector_golden_expected() -> dict:
    """`DETECTOR_GOLDEN_EXPECTED` read from the runner's test file (the plan: written in the test before it was first run)."""
    name = "_ps314_replay_tests_expected"
    spec = importlib.util.spec_from_file_location(name, REPLAY_TESTS)
    src = open(REPLAY_TESTS, encoding="utf-8").read()
    marker = "DETECTOR_GOLDEN_EXPECTED = "
    if marker not in src:
        raise GuardStop(f"{REPLAY_TESTS} carries no DETECTOR_GOLDEN_EXPECTED")
    import ast
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "DETECTOR_GOLDEN_EXPECTED" for t in node.targets):
            return ast.literal_eval(node.value)
    raise GuardStop("DETECTOR_GOLDEN_EXPECTED is not a literal")


def detector_golden_check(say=print) -> list:
    """-> the problems: every copy's stage and failing set against the test's expected values (a mismatch refuses the run)."""
    want = detector_golden_expected()
    got = detector_golden_results()
    problems = []
    for copy in COPIES:
        w = want.get(copy)
        g = got[copy]
        ok = w is not None and tuple(w[0:2]) == (g[0], g[1]) and (len(w) < 3 or w[2] == g[2])
        say(f"  detector golden {copy}: stage {g[0]}, failing {list(g[1])}, days_up_streak {g[2]} (expected {w}) -> {'OK' if ok else 'MISMATCH'}")
        if not ok:
            problems.append(f"detector golden {copy}: got {g}, expected {w}")
    return problems
