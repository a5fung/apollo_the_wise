#!/usr/bin/env python3
"""EP big-winner chart study — STAGE 1 shared code (pre-registration docs/analysis/ep_winner_study_prereg_2026-11-21.md, FROZEN v2).

OUTCOME-FREE BY CONSTRUCTION: nothing in this folder computes a return after E. Every feature is produced by
`features.event_features`, which is handed ONLY the ticker's bars with calendar index < ci(E) plus open(E).
Sealed data (#710): every era-B row dated after 2024-12-31 is dropped AT READ and asserted.
NOT imported / NOT opened: scripts/probes/_594_outcome_qm_1121/build/ outputs (events_scored.tsv.gz, run.txt).

COPIED (not imported — run.py runs its whole pipeline, and prints outcomes, at module level; prereg §1):
  * `_load`               <- scripts/probes/_594_outcome_qm_1121/build/run.py lines 59-63
  * `DAILY`, `CAL`, CUT_B <- run.py lines 72-74
  * `five_years_before`   <- run.py lines 84-89
  * `score_one`           <- run.py lines 92-103
  * the bar loader        <- run.py lines 164-196 (chunked read of DAILY[era], era B cut at read, date -> calendar index `ci`,
                             bars[(era, ticker)] = (d, ci, o, h, l, c, v))
  Only those line ranges of run.py were read (sed -n '42,104p;160,200p'); the rest of that file was not opened.
  `read_cal`, the flag / symbol-guard parsing <- scripts/probes/_705_ep_join_1023/01_ep_join.py lines 193-199, 439-456.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import pickle
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
assert (REPO / "PLAN.md").exists(), REPO
CACHE = HERE / "cache"


def _load(name, path):                                   # run.py 59-63, verbatim
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


f3 = _load("f3_def", REPO / "scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
nbis = _load("nbis", REPO / "scripts/probes/_533_nbis_structure_encoder.py")

DATA = "/Users/alvinfung/apollo_data"
EVDIR = f"{DATA}/cb702/qm_streams/ep_join_1023"
DAILY = {"A": f"{DATA}/cb702_pre_v2/daily_closes_all.csv.gz", "B": f"{DATA}/cb702/daily_closes_all.csv.gz"}          # run.py 72
CAL = {"A": f"{DATA}/cb702_pre_v2/sessions.txt", "B": f"{DATA}/cb702/qm_streams/track_a_1023/spy_sessions_eraB_le_2024-12-31.txt"}  # run.py 73
CUT_B = "2024-12-31"                                     # run.py 74
E_MAX_B = "2024-09-30"                                   # prereg §1 drop 2 (PRE-REG 6 R2)
E_MAX_A = "2022-04-04"                                   # prereg §1 drop 2 / 3
DISC_LAST = "2020-12-31"                                 # prereg §3
FLAGS = {"A": f"{DATA}/cb702_pre_v2/audit_1023/price/A_flags.tsv", "B": f"{DATA}/audit_runs_2026-10-23/B_flags.tsv"}   # 01_ep_join FILES
GUARD = {"A": f"{DATA}/cb702_pre_v2/audit_1023/universe/symbol_guard_A.tsv",
         "B": str(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")}
FLAG_KLASSES = {"known_adjustment_event", "discontinuous_across_known_adjustment"}
PREREG = REPO / "docs/analysis/ep_winner_study_prereg_2026-11-21.md"
SEED = 1121


def sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def five_years_before(d: str) -> str:                    # run.py 84-89, verbatim
    y, m, dd = (int(x) for x in d.split("-"))
    try:
        return date(y - 5, m, dd).isoformat()
    except ValueError:
        return date(y - 5, m, 28).isoformat()


def score_one(days, ia):                                 # run.py 92-103, verbatim
    """THE feature path, shared by the loader check and the history: days sliced to 5 calendar years before E, E = last bar."""
    lo = 0
    cut = five_years_before(days[ia][0])
    while lo < ia and days[lo][0] < cut:
        lo += 1
    sl = days[lo:ia + 1]
    j = len(sl) - 1
    adr = nbis.adr20_pct(sl, j)
    res = f3.f3_new(sl, j, adr, f3.STATED)
    return res, adr


def read_cal(path: str, cut: str | None = None) -> np.ndarray:   # 01_ep_join.py 193-199
    d = [ln.strip() for ln in open(path) if ln.strip()]
    if cut:
        d = [x for x in d if x <= cut]
    arr = np.array(sorted(d), dtype="U10")
    assert len(np.unique(arr)) == len(arr)
    return arr


def calendars() -> dict:
    cal = {"A": read_cal(CAL["A"]), "B": read_cal(CAL["B"], CUT_B)}
    assert cal["A"][0] == "2016-01-04" and cal["A"][-1] == "2022-06-30"
    assert cal["B"][0] == "2021-09-27" and cal["B"][-1] <= CUT_B
    return cal


def load_flags() -> dict:
    """{era: {ticker: sorted list of flagged dates}} — the two klasses only; era B cut at 2024-12-31 (01_ep_join.py 439-446)."""
    out = {}
    for e in "AB":
        f = pd.read_csv(FLAGS[e], sep="\t", usecols=["klass", "ticker", "date"], dtype=str, keep_default_na=False)
        f = f[f.klass.isin(FLAG_KLASSES)]
        assert set(f.klass) <= FLAG_KLASSES
        if e == "B":
            f = f[f.date <= CUT_B]
            assert f.date.max() <= CUT_B
        d = defaultdict(set)
        for t, dt in zip(f.ticker, f.date):
            d[t].add(dt)
        out[e] = {t: sorted(v) for t, v in d.items()}
    return out


def load_breaks() -> dict:
    """{era: {ticker: sorted list of identity-break dates}} (01_ep_join.py 447-454). Era B breaks after the cut are dropped."""
    out = {}
    for e in "AB":
        g = pd.read_csv(GUARD[e], sep="\t", dtype=str, keep_default_na=False)
        d = defaultdict(set)
        for tkr, br in zip(g.symbol, g.breaks):
            for item in br.split(";"):
                if ":" in item:
                    dt = item.split(":")[0]
                    if e == "B" and dt > CUT_B:
                        continue
                    d[tkr].add(dt)
        out[e] = {t: sorted(v) for t, v in d.items()}
    return out


def read_events_raw() -> pd.DataFrame:
    parts = []
    for e in "AB":
        d = pd.read_csv(f"{EVDIR}/ep_events_{e}.tsv.gz", sep="\t", keep_default_na=False,
                        dtype={"ticker": str, "E": str, "D": str, "sectype": str, "era": str})
        assert (d.era == e).all()
        parts.append(d)
    ev = pd.concat(parts, ignore_index=True)
    for col in ("primary", "flag_adj", "flag_adj_Dm1", "b_hist130", "b_gap10"):
        if ev[col].dtype != bool:
            ev[col] = ev[col].astype(str).str.lower().eq("true")
    return ev


def build_population(verbose=print) -> pd.DataFrame:
    """Prereg §1: the drops in order, every count asserted. Returns the 4,665 events sorted (era, E, ticker)."""
    ev = read_events_raw()
    ev = ev[ev.primary].copy()
    nA, nB = int((ev.era == "A").sum()), int((ev.era == "B").sum())
    verbose(f"source primary rows: {len(ev)} (A {nA}, B {nB})")
    assert (len(ev), nA, nB) == (5342, 3378, 1964), (len(ev), nA, nB)
    assert ev[ev.era == "B"].E.max() <= CUT_B                         # sealed: no event after the cut
    # drop 1
    m1 = ev.flag_adj | ev.flag_adj_Dm1
    verbose(f"drop 1 flag_adj / flag_adj_Dm1: {int(m1.sum())} (A {int((m1 & (ev.era == 'A')).sum())}, B {int((m1 & (ev.era == 'B')).sum())})")
    assert int(m1.sum()) == 2
    ev = ev[~m1]
    # drop 2
    m2b = (ev.era == "B") & (ev.E > E_MAX_B)
    m2a = (ev.era == "A") & (ev.E > E_MAX_A)
    verbose(f"drop 2 forward window: era B E > {E_MAX_B}: {int(m2b.sum())} | era A E > {E_MAX_A}: {int(m2a.sum())}")
    assert int(m2b.sum()) == 270 and int(m2a.sum()) == 95, (int(m2b.sum()), int(m2a.sum()))
    ev = ev[~(m2a | m2b)]
    # drop 3
    m3 = (ev.era == "B") & (ev.E <= E_MAX_A)
    akeys = set(zip(ev.loc[ev.era == "A", "ticker"], ev.loc[ev.era == "A", "E"]))
    twin = np.array([(t, e_) in akeys for t, e_ in zip(ev.ticker, ev.E)]) & m3.to_numpy()
    verbose(f"drop 3 era overlap (every era-B event E <= {E_MAX_A}): {int(m3.sum())} "
            f"({int(twin.sum())} with a same-(ticker, E) era-A copy, {int(m3.sum()) - int(twin.sum())} without)")
    assert int(m3.sum()) == 310 and int(twin.sum()) == 273, (int(m3.sum()), int(twin.sum()))
    ev = ev[~m3]
    ev = ev.sort_values(["era", "E", "ticker"], kind="mergesort").reset_index(drop=True)
    nA, nB = int((ev.era == "A").sum()), int((ev.era == "B").sum())
    verbose(f"STUDY POPULATION: {len(ev)} (era A {nA}, era B {nB}); era B first E {ev[ev.era == 'B'].E.min()}")
    assert (len(ev), nA, nB) == (4665, 3281, 1384) and ev[ev.era == "B"].E.min() == "2022-04-05"
    assert not ev.duplicated(["era", "ticker", "E"]).any()
    ev["set"] = np.where(ev.E <= DISC_LAST, "DISC", "CONF")
    ev["year"] = ev.E.str[:4]
    ev["month"] = ev.E.str[:7]
    ev["quarter"] = ev.year + "Q" + ((ev.E.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    return ev


def load_bars(need: dict, cal: dict, verbose=print) -> dict:
    """run.py 164-196 (copied): ALL bars of every needed ticker; era B cut at read; bars[(era, t)] = (d, ci, o, h, l, c, v)."""
    bars = {}
    for era in "AB":
        cnt = Counter()
        parts = []
        for ch in pd.read_csv(DAILY[era], header=None, names=["t", "d", "o", "h", "l", "c", "v"],
                              dtype={"t": str, "d": str, "o": "float64", "h": "float64", "l": "float64", "c": "float64", "v": "float64"},
                              keep_default_na=False, chunksize=2_000_000):
            cnt["rows_read"] += len(ch)
            if era == "B":
                m = ch.d <= CUT_B
                cnt["rows_dropped_after_2024-12-31"] += int((~m).sum())
                ch = ch[m]
            ch = ch[ch.t.isin(need[era])]
            parts.append(ch)
        df = pd.concat(parts, ignore_index=True)
        del parts
        if era == "B":
            assert df.d.max() <= CUT_B, df.d.max()          # SEALED (#710): nothing after 2024-12-31 survives the read
        dv = df.d.to_numpy(dtype="U10")
        ci = np.searchsorted(cal[era], dv)
        on = (ci < len(cal[era])) & (cal[era][np.minimum(ci, len(cal[era]) - 1)] == dv)
        cnt["rows_off_calendar_dropped"] = int((~on).sum())
        df = df[on].copy()
        df["ci"] = ci[on]
        df.sort_values(["t", "ci"], inplace=True, kind="mergesort")
        assert not df.duplicated(["t", "ci"]).any()
        for t, g in df.groupby("t", sort=False):
            bars[(era, t)] = (g.d.tolist(), g.ci.to_numpy(), g.o.to_numpy(), g.h.to_numpy(), g.l.to_numpy(), g.c.to_numpy(), g.v.to_numpy())
        cnt["rows_kept(needed tickers)"] = len(df)
        verbose(f"era {era} daily read: {dict(cnt)}")
        del df
    return bars


def bars_cached(ev: pd.DataFrame, cal: dict, verbose=print) -> dict:
    """Event tickers + SPY (feature 14), per era. Cache holds nothing after 2024-12-31 (asserted on load)."""
    p = CACHE / "bars_event_tickers.pkl"
    if p.exists():
        bars = pickle.load(open(p, "rb"))
        verbose(f"bars loaded from cache {p} ({len(bars)} (era, ticker) series)")
    else:
        need = {e: set(ev.loc[ev.era == e, "ticker"]) | {"SPY"} for e in "AB"}
        bars = load_bars(need, cal, verbose)
        pickle.dump(bars, open(p, "wb"), protocol=4)
    mx = max(b[0][-1] for (e, _), b in bars.items() if e == "B")
    assert mx <= CUT_B, mx
    return bars
