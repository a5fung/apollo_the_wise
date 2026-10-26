#!/usr/bin/env python3
"""#705 v2 re-run, B9 - the degraded-walk report (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §6, B9). A REPORT: it decides nothing.

The runner marks a walk `degraded` (mature = 0, dropped from the published lists) when its forward bars run out before it exits - for two reasons the
one count mixes: the ticker's last bar falls inside the hold (an ENDING: a delisting, a merger, a collapse; `fwd_hole` = 0) or the walk hit a gap in
the ticker's bars (a HOLE; `fwd_hole` = 1, the ticker prints again later). On the C0 / tl rows of one arm of a stage's trades table - the exit read's
`trades_pre_exitpb` (entry orh5, arm `pp`; the default) and the pre-read's `trades_pre_p5` (arm c3_p33_t20_cut3, the S1-S4 headline; the old file's
"5 of 13,368" is this table) - it prints:
  - degraded walks split ending / hole (and by restored / shared ticker, B8);
  - each ending classed by the data standard's C1 rule: COLLAPSE = the last close under $1 (the RAW close when the raw file is given) or -50% or worse
    over the last 60 sessions - SESSIONS of the one calendar (sessions.txt), never the ticker's own bars: the reference close is the ticker's
    close on the session 60 sessions before its last bar (its last bar at or before that session when it has a hole there; its first bar when it
    began printing later); DEAL-LIKE = the last 10 closes within a 1% spread ((max - min) / min <= 1%); OTHER;
  - C0 mean R three ways: degraded walks OUT (the headline, as the old reads); IN, marked at the last close (the walk's own mark); IN, with collapse
    endings marked at the last close less a 30% DELISTING HAIRCUT (the exit price of the remaining position = 0.7 x the last close; deal-like and other
    endings and holes stay at their mark). The haircut is the registration's stated convention; it decides nothing.

    python3 v2_degraded.py --trades T.tsv.gz --export daily_closes_all.csv.gz --sessions sessions.txt [--raw daily_raw_close.csv.gz] [--guard-new G --guard-old G]
                           [--arm pp --entry orh5 | --arm c3_p33_t20_cut3 --entry ''] [--label L]
The mark of an ENDING is the ticker's last close (the walk ran out of bars there): a table without `exit_px` (trades_pre_p5) takes it from the export;
a table with it is CHECKED against it (a mismatch is printed - the ending reading would then be wrong). Both arms sell a third (PARTIAL_FRAC).
Reads the trades table, and the export rows of the ENDING tickers only. Writes nothing (stdout is the console).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import sys

import numpy as np
import pandas as pd

HAIRCUT = 0.30                     # the registration's delisting haircut (§6)
PARTIAL_FRAC = 1.0 / 3.0           # the third the `pp` family sells (runner EXITPB_BASE.partial_frac; asserted in the tests)
COLLAPSE_PX, COLLAPSE_DROP, COLLAPSE_N = 1.0, -0.50, 60
DEAL_N, DEAL_SPREAD = 10, 0.01
ARM, ENTRY, LEVEL, CELL = "pp", "orh5", "tl", "C0"
ARMS_ONE_THIRD = ("pp", "c3_p33_t20_cut3")         # the arms this report is run on: each sells a third at its partial (asserted in the tests)
MARK_TOL = 1e-6


def headline_rows(trades: pd.DataFrame, arm: str = ARM, entry: str = ENTRY) -> pd.DataFrame:
    t = trades
    keep = (t["arm"].astype(str) == arm) & (t["K"].astype(str) == LEVEL) & (t[CELL] == 1)
    if entry:
        keep &= t["entry"].astype(str) == entry
    return t[keep].copy()


def ticker_closes(export, tickers: set, raw=None) -> dict:
    """{ticker: (dates, adjusted closes, raw closes or None)} for `tickers`, read in chunks (no other ticker is kept)."""
    out = {}
    parts = []
    for ch in pd.read_csv(export, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str}, keep_default_na=False,
                          na_values=[""], chunksize=2_000_000):
        parts.append(ch[ch["t"].isin(tickers)][["t", "d", "c"]])
    df = pd.concat(parts) if parts else pd.DataFrame(columns=["t", "d", "c"])
    rawmap = {}
    if raw is not None:
        rp = []
        for ch in pd.read_csv(raw, header=None, names=["t", "d", "rc"], dtype={"t": str, "d": str}, keep_default_na=False, na_values=[""], chunksize=2_000_000):
            rp.append(ch[ch["t"].isin(tickers)])
        if rp:
            r = pd.concat(rp)
            rawmap = {(a, b): float(c) for a, b, c in r[["t", "d", "rc"]].itertuples(index=False)}
    for t, g in df.sort_values(["t", "d"]).groupby("t"):
        d, c = g["d"].to_list(), g["c"].to_numpy(dtype=float)
        out[t] = (d, c, (np.array([rawmap.get((t, x), np.nan) for x in d]) if raw is not None else None))
    return out


def ref_close(dates: list, closes: np.ndarray, sessions: list, pos: "dict | None" = None) -> float:
    """The ticker's close COLLAPSE_N sessions (of `sessions`, the one calendar) before its last bar: its bar on that session, else its last bar
    before it (a hole), else its first bar (it began printing later). A last bar off the calendar raises (one calendar per record)."""
    pos = pos if pos is not None else {d: k for k, d in enumerate(sessions)}
    if dates[-1] not in pos:
        raise ValueError(f"the ticker's last bar {dates[-1]} is not a session of the calendar")
    j = pos[dates[-1]] - COLLAPSE_N
    if j < 0:
        return float(closes[0])
    k = bisect.bisect_right(dates, sessions[j]) - 1
    return float(closes[k]) if k >= 0 else float(closes[0])


def ending_class(dates: list, closes: np.ndarray, raw: "np.ndarray | None", sessions: list, pos: "dict | None" = None) -> str:
    """The data standard's C1 rule on the ticker's LAST bars: collapse / deal-like / other."""
    last = float(raw[-1]) if raw is not None and np.isfinite(raw[-1]) else float(closes[-1])
    ref = ref_close(dates, closes, sessions, pos)
    if last < COLLAPSE_PX or (ref > 0 and closes[-1] / ref - 1.0 <= COLLAPSE_DROP):
        return "collapse"
    tail = closes[-DEAL_N:]
    if len(tail) >= DEAL_N and tail.min() > 0 and (tail.max() - tail.min()) / tail.min() <= DEAL_SPREAD:
        return "deal-like"
    return "other"


def haircut_r(row) -> float:
    """realized R with the remaining position's exit at (1 - HAIRCUT) x the mark."""
    rem = 1.0 - PARTIAL_FRAC if (isinstance(row["partial_kind"], str) and row["partial_kind"]) else 1.0
    risk = float(row["fill"]) - float(row["stop"])
    return float(row["realized_r"]) - rem * HAIRCUT * float(row["exit_px"]) / risk


def report(trades: pd.DataFrame, export, raw=None, restored: "set | None" = None, export_last: "str | None" = None, arm: str = ARM,
           entry: str = ENTRY, sessions: "list | None" = None) -> dict:
    if not sessions:
        raise ValueError("sessions (the one calendar, sessions.txt) is required: the 60-session window is counted in sessions, not in the ticker's bars")
    pos = {d: k for k, d in enumerate(sessions)}
    if arm not in ARMS_ONE_THIRD:
        raise ValueError(f"arm {arm!r}: the haircut assumes a third sold at the partial; known arms {ARMS_ONE_THIRD}")
    h = headline_rows(trades, arm, entry)
    deg = h[(h["status"].astype(str) == "degraded") & (h["mature"] == 0)].copy()
    mature = h[h["mature"] == 1]
    deg["cause"] = np.where(deg["fwd_hole"].astype(int) == 1, "hole", "ending")
    closes = ticker_closes(export, set(deg.loc[deg["cause"] == "ending", "ticker"]), raw)
    last_session = export_last
    if last_session is None and len(closes):
        last_session = max(v[0][-1] for v in closes.values())
    klass, marks, mark_bad = [], [], []
    has_px = "exit_px" in deg.columns
    for r in deg.itertuples():
        px = float(r.exit_px) if has_px and pd.notna(r.exit_px) else float("nan")
        if r.cause == "hole":
            klass.append("")
            marks.append(px)
            continue
        d, c, rw = closes[r.ticker]
        klass.append(ending_class(d, c, rw, sessions, pos) if not (export_last and d[-1] >= export_last) else "file end")
        last = float(c[-1])
        if np.isfinite(px) and abs(px - last) > MARK_TOL * max(1.0, abs(last)):
            mark_bad.append(f"{r.ticker} E {r.E}: exit_px {px} is not the ticker's last close {last}")
        marks.append(px if np.isfinite(px) else last)
    deg["klass"] = klass
    deg["exit_px"] = marks
    deg["r_haircut"] = [haircut_r(r) if k == "collapse" else float(r["realized_r"]) for k, (_i, r) in zip(deg["klass"], deg.iterrows())]
    rest = restored or set()
    deg["side"] = np.where(deg["ticker"].isin(rest), "restored", "shared")
    r_out = mature["realized_r"].to_numpy(dtype=float)
    r_in = np.concatenate([r_out, deg["realized_r"].to_numpy(dtype=float)])
    r_hc = np.concatenate([r_out, deg["r_haircut"].to_numpy(dtype=float)])
    return {"n_rows": int(len(h)), "n_mature": int(len(mature)), "n_degraded": int(len(deg)),
            "by_cause": {c: int((deg["cause"] == c).sum()) for c in ("ending", "hole")},
            "by_class": {k: int((deg["klass"] == k).sum()) for k in ("collapse", "deal-like", "other", "file end")},
            "by_side": {s: {c: int(((deg["side"] == s) & (deg["cause"] == c)).sum()) for c in ("ending", "hole")} for s in ("restored", "shared")},
            "mean_r_out": float(r_out.mean()) if len(r_out) else None, "mean_r_in_last_close": float(r_in.mean()) if len(r_in) else None,
            "mean_r_in_haircut": float(r_hc.mean()) if len(r_hc) else None, "rows": deg, "mark_problems": mark_bad, "arm": arm, "entry": entry or "-"}


def text(rep: dict) -> str:
    L = [f"B9 DEGRADED-WALK REPORT (C0 / {LEVEL} / {rep['entry']} / {rep['arm']}; decides nothing): {rep['n_rows']:,} rows, {rep['n_mature']:,} mature, "
         f"{rep['n_degraded']:,} degraded = {rep['by_cause']['ending']:,} endings (the ticker's last bar inside the hold) + {rep['by_cause']['hole']:,} holes (a gap "
         f"inside the walk)",
         f"  endings by class: collapse {rep['by_class']['collapse']}, deal-like {rep['by_class']['deal-like']}, other {rep['by_class']['other']}"
         + (f", file end {rep['by_class']['file end']} (not a delisting - the export's own last session)" if rep['by_class']['file end'] else ""),
         f"  by ticker side (B8): restored {rep['by_side']['restored']}, shared {rep['by_side']['shared']}",
         f"  C0 mean R: degraded OUT (the headline) {rep['mean_r_out']:+.4f}; IN at the last close {rep['mean_r_in_last_close']:+.4f}; IN with collapse endings "
         f"at a {HAIRCUT:.0%} haircut {rep['mean_r_in_haircut']:+.4f}",
         f"  MARK CHECK (an ending's mark = the ticker's last close): " + ("ok" if not rep["mark_problems"] else
                                                                           f"{len(rep['mark_problems'])} MISMATCH(ES): " + "; ".join(rep["mark_problems"][:10]))]
    for r in rep["rows"].itertuples():
        L.append(f"    {r.ticker} E {r.E}: {r.cause}{(' / ' + r.klass) if r.klass else ''}; {r.side}; R {float(r.realized_r):+.3f}"
                 + (f" -> {float(r.r_haircut):+.3f} at the haircut" if r.klass == "collapse" else "") + f"; held {int(r.sessions_held)} sessions")
    return "\n".join(L)


def guard_symbols(p) -> set:
    with open(p, newline="") as fh:
        return {r["symbol"] for r in csv.DictReader(fh, delimiter="\t")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--export", required=True)
    ap.add_argument("--raw")
    ap.add_argument("--sessions", required=True, help="sessions.txt - the one calendar the 60-session collapse window is counted on")
    ap.add_argument("--guard-new")
    ap.add_argument("--guard-old")
    ap.add_argument("--export-last", help="the export's last session (an 'ending' whose last bar is that session is the file end, not a delisting)")
    ap.add_argument("--arm", default=ARM, choices=ARMS_ONE_THIRD)
    ap.add_argument("--entry", default=ENTRY, help="the entry column's value ('' = the table has no entry column: trades_pre_p5)")
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    rest = guard_symbols(a.guard_new) - guard_symbols(a.guard_old) if a.guard_new and a.guard_old else None
    t = pd.read_csv(a.trades, sep="\t", low_memory=False)
    if a.label:
        print(f"== {a.label}: {a.trades}")
    sessions = [ln.strip() for ln in open(a.sessions) if ln.strip()]
    print(text(report(t, a.export, a.raw, rest, a.export_last, arm=a.arm, entry=a.entry, sessions=sessions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
