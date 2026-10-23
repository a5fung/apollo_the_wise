#!/usr/bin/env python3
"""#705 Track A — 01: join Qullamaggie's stream grades to our breakout events. OUTCOME-FREE.

What it does: every ATTRIBUTED label (his words + the on-screen chart + our bars agree) is placed against our
consolidation-breakout events (K = `tl`, the registered trendline level; `com` and the horizontal levels beside) of the
same stock near the screen date. It answers WHERE his labels sit relative to our breakout day E (before / on / after),
whether the stock was in one of our bases that night with no break yet, which of the matched events are R1 / R2 under his
definition (base-high close / expansion day), and how many OTHER breakouts shared each matched event's day (the "which
breakout to pick" denominator). No forward return, R, P&L, stop, exit or any bar after E is read; the only E-day-or-later
information is the R1 / R2 MEMBERSHIP FLAGS of the breakout-definition tables (bdef), carried as descriptive columns only.

EVERY CHOICE BELOW WAS FIXED BEFORE THE FIRST RUN (this header is the record):
- SIGN: delta = session index of E minus the session index of the label's session. delta > 0 = the label came BEFORE our
  breakout day (he spoke of the base before the line broke); delta = 0 = the screen date IS the breakout day; delta < 0 = the
  label came AFTER the breakout. Printed on every table in words.
- LABEL SESSION s0 = the last session <= screen_date on the era's SPY calendar (9 labels fall on a weekend; the frame check
  found the on-screen ADR matched the screen-date session and the prior session about half each, so "on" is reported both as
  delta = 0 and as the band [-1, +1]).
- WINDOW: E in [s0 - 10, s0 + 20] sessions. Why: "bought" is said at or soon after the entry (ten sessions back covers "I
  bought last week"); "not yet / needs a few more days" is a base that should break within about a month if it breaks (20
  sessions, roughly half the longest base our rule allows, 45); our tl trigger is known to fire EARLY relative to his
  base-high breakout (the base high is cleared after our fill on 70-76% of fills, cb_breakout_definition_2026-10-22.md), so the
  window reaches further forward than back. The full nearest-event distribution over [-60, +60] is printed beside so the window
  can be judged; it was NOT re-tuned after the run.
- MATCH: the nearest event by |delta| among the stock's tl rows (first breaks AND retriggers — every day the high cleared the
  line is a day in the stream he would see); ties (one before, one after at the same distance) go to the LATER E (the
  pre-breakout reading). The count of labels with more than one event in the window is printed. The nearest FIRST BREAK
  (retrigger = 0) is reported beside, and the same join under `com` (both eras) and `k5` / `k10` / `full` (2022-24 only).
- ERA: screen_date <= 2022-01-03 (era A's last E) -> era A (cb702_pre_v2, the rebuilt 2017-21 file); later -> era B
  (cb702, 2022-24, discovery rows only, every row with a date after 2024-12-31 dropped AT READ and asserted). A label whose
  window does not fully sit inside the era's E range [first E, last E] is `coverage = partial`; one whose window does not
  touch it is `coverage = none` (the 6 labels of 2017-01, before the first E 2017-03-02; the 13 of 2022-01..02, the gap
  between the eras). Join rates are quoted over full + partial coverage, with full-only beside. `none` is a coverage fact,
  never a miss.
- DISTINCT EVENTS (round 2 wording of the round-1 rule): an event carrying several labels takes, for the position table, the
  delta of the label CLOSEST to E (|delta| smallest, the later label on a tie); round 1 printed the first label in file order
  (reported beside). Neither reaches 60% on any arm, so the target rule's verdict does not depend on it.
- PLACEBO (the round-1 code's three conditions, written out in round 2 after the recount could not reproduce the n from the
  prose): the symbols are those with a BOUGHT label and coverage != none in era A (200); t runs over the sessions whose whole
  window [t-10, t+20] sits inside the era's E range (indices Emin+10 .. Emax-20); t is excluded when it is within +-20
  sessions of ANY attributed label of that symbol, any grade; t needs a watch row of the symbol in [t-10, t+20] and a tl
  event in the same window (the nearest one, same tie rule, is the delta).
- WATCH STATE "same base NOT yet broken at s0" (round 2 wording): round 1 keyed the base on the candidate rows' `pole_date`
  column equal to the watch row's pole_date; a drifted pole (the module re-dates a pole by a day) makes the same base look
  unbroken under that key. Round 2 prints BOTH: the pole_date key (round 1) and the drift-robust `base_id` key.
- ADDED IN ROUND 2 (2026-10-23, after the two checkers' reports; outcome-free; no choice of the round-1 join changed — these
  are counts the registration needs that the round-1 output did not print): (11) the label TIMING of every positive event
  (bought or best) — at least one positive label said ON OR BEFORE E, only after E, at least one strictly before; the
  2017-20 / 2021 split; (12) the same-day NEGATIVES on the graded dates, with the rows that belong to a LABELLED base
  excluded and counted; (13) the readiness contrast's populations at the label date s0; (14) where the grade phrase sits —
  in the ticker's own caption line or only in the surrounding window (reads `graded_moments.tsv`, pinned).
- TARGET DECISION RULE (applied to the joined BOUGHT labels, era A, full + partial coverage; thresholds fixed now):
  * >= 60% with delta >= +1  -> the filter's target is a PRE-BREAKOUT STATE (decision time = the watch night D);
  * >= 60% with delta in [-2, +1] -> the target is the BREAKOUT DAY (decision time = E);
  * otherwise both are reported and the registration takes the breakout-day target with state features read at D.
  The same split is printed against the R1 day (his definition: the first close above the base high) as a second anchor;
  if the two anchors disagree the doc says so.
- SYMBOL RESOLUTION (era A; the export is keyed by today's symbol): the screen ticker itself if it has rows in the v2 export;
  else, in order, dedupe_applied.tsv (dropped -> kept), refetch_dropped.tsv (symbol -> the X in "..._of_X"),
  rename_map.tsv (polygon_ticker -> alpaca_symbol) — the frame check's order; the count resolved through each is printed.
  Era B labels are Polygon-keyed and are used as read.
- WATCH STATE at s0: a watch row (symbol, watch_date = s0) exists (the stock passed the C0 structural gates that night);
  `no_break_yet` = no tl event of the same base (same pole_date) with E <= s0. "In a base in the window" = any watch row of
  the symbol with watch_date in [s0 - 10, s0 + 20].
- R1 / R2 (descriptive only, bdef tables; era A's were built on the OLD export cb702_pre, so era A membership is THREE-VALUED:
  R1 / fill-without-R1 / not in the old fill population): published fill = (ticker, E) in bdef_fills; R1 = in bdef_r1
  (a close above the base high within 60 sessions of E — a FORWARD flag by construction); R2 = bdef_r1.r2_exp; the R1 day's
  offset from E and the label's delta to the R1 day are printed. Columns read from bdef: ticker, D, E, t, entry_date, r2_exp.
- SAME-DAY POPULATION: for a matched event, the number of OTHER tl events (all rows; first breaks) with the same E in the
  era, and the number in E's ISO week.
- OUTPUTS (apollo_data/cb702/qm_streams/track_a_1023/): labels_joined.tsv (one row per label), matched_events.tsv (one row
  per distinct (era, symbol, E) matched by any label); the printed summary is saved beside this script as 01_join_labels.txt.
  Pins (sha256) of every input and of this file are printed last.

Run:  python3 scripts/probes/_705_track_a_1023/01_join_labels.py > scripts/probes/_705_track_a_1023/01_join_labels.txt
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

import numpy as np
import pandas as pd

DATA = "/Users/alvinfung/apollo_data"
A = f"{DATA}/cb702_pre_v2"
A_OLD = f"{DATA}/cb702_pre"          # the OLD 2017-21 export: only its bdef (R1 / R2) tables are read here
B = f"{DATA}/cb702"
OUT = f"{B}/qm_streams/track_a_1023"
LABELS = f"{B}/qm_streams/vision/grades_labels.tsv"
FRAMES = f"{B}/qm_streams/vision/frames_grades"
ALIASES = [f"{A}/dedupe_applied.tsv",
           f"{A_OLD}/survivorship_1023/merged_trial2/refetch_dropped.tsv",
           f"{B}/qm_streams/ext_2016_2022/rename_map.tsv"]
CAL_A = f"{A}/sessions.txt"
CAL_B = f"{OUT}/spy_sessions_eraB_le_2024-12-31.txt"   # SPY's dates in the cb702 export, kept only <= 2024-12-31
CAND_A = f"{A}/out/candidates_tl_com.tsv"
CAND_B = f"{B}/out/candidates.tsv"
CAND_B_COM = f"{B}/out/candidates_com.tsv"
WATCH_A = f"{A}/out/watch_tl_com.tsv.gz"
WATCH_B = f"{B}/out/watch.tsv.gz"
BDEF_R1 = {"A": f"{A_OLD}/out/bdef_r1_2017-21.tsv.gz", "B": f"{B}/out/bdef_r1_2022-24.tsv.gz"}
BDEF_FILLS = {"A": f"{A_OLD}/out/bdef_fills_2017-21.tsv.gz", "B": f"{B}/out/bdef_fills_2022-24.tsv.gz"}
EXPORT_A = f"{A}/daily_closes_all.csv.gz"
SIC = {"A": f"{A}/cb702_sic.psv", "B": f"{B}/cb702_sic.psv"}
MOMENTS = f"{B}/qm_streams/vision/graded_moments.tsv"   # round 2: the caption line (`quote`, 220 chars) per graded moment
# the grade phrases exactly as 02_graded_moments.py matched them over the caption WINDOW; here re-applied to the ticker's own
# caption line only (section 14) — an upper bound on "the phrase is in the window only", since the quote is cut at 220 chars
GRADE_RX = {"best": r"\b(best|perfect|textbook|beautiful) (setup|set up|chart|flag|base)s?\b|\ba[ -]?plus\b",
            "bought": r"\bi (bought|added|got in|took a (starter|position)|entered)\b|\bi'?m (long|in it)\b",
            "not_yet": r"\bneeds? (a )?(few |couple )?(more )?(days|weeks)\b|\bneeds? to tighten\b|\bnot (quite )?ready\b|\btoo (loose|wide|extended)\b"}
FIT_LAST_E = "2020-12-31"            # the fit set's last E (era A); 2021 is the hold-out

CUT_B = "2024-12-31"                 # nothing dated after this is kept from any era-B file
ERA_A_LAST_E = "2022-01-03"          # era A's last breakout day; a later screen date is era B
W_BACK, W_FWD = 10, 20               # the window, sessions
WIDE = 60                            # the beside distribution
ON_BAND = (-1, 1)
ON_BAND_WIDE = (-2, 1)
TARGET_SHARE = 0.60

CAND_COLS = ["ticker", "D", "E", "K", "pole_date", "pole_ci", "retrigger", "retrigger_chain", "base_id", "split", "C1"]
WATCH_COLS = ["ticker", "watch_date", "pole_date", "base_len", "C0_tl", "split"]
BDEF_R1_COLS = ["ticker", "D", "E", "t", "entry_date", "r2_exp"]
BDEF_FILL_COLS = ["ticker", "D", "E"]

STR = {c: str for c in ["ticker", "D", "E", "K", "pole_date", "base_id", "split", "watch_date", "entry_date"]}


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_cal(path: str, cut: str | None = None) -> np.ndarray:
    d = [ln.strip() for ln in open(path) if ln.strip()]
    if cut:
        d = [x for x in d if x <= cut]
    arr = np.array(sorted(d), dtype="U10")
    assert len(np.unique(arr)) == len(arr)
    return arr


def s_idx(cal: np.ndarray, day: str) -> int:
    """index of the last session <= day (-1 when before the calendar)."""
    return int(np.searchsorted(cal, day, "right")) - 1


def read_tsv_filtered(path: str, usecols: list[str], keep, chunksize: int = 100_000) -> pd.DataFrame:
    parts = []
    for ch in pd.read_csv(path, sep="\t", usecols=usecols, dtype=STR, keep_default_na=False, chunksize=chunksize):
        parts.append(keep(ch))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=usecols)


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100.0 * a / b:.1f}%)" if b else f"{a}/0"


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    print("# #705 Track A — 01_join_labels (outcome-free). Choices fixed in the script header before the first run.")
    print(f"# window E in [s0-{W_BACK}, s0+{W_FWD}] sessions; delta = idx(E) - idx(s0): >0 label BEFORE our breakout day, 0 ON it, <0 AFTER it")

    # ------------------------------------------------------------------ labels
    lab = pd.read_csv(LABELS, sep="\t", dtype=str, keep_default_na=False)
    lab = lab[lab.status == "attributed"].reset_index(drop=True)
    lab["is_bought"] = lab.grade.str.contains("bought")
    lab["is_not_yet"] = lab.grade.str.contains("not_yet")
    lab["is_best"] = lab.grade.str.contains("best")
    print(f"\n## 0. Labels: attributed {len(lab)} | grade strings {dict(Counter(lab.grade))}")
    print(f"- exploded: bought {int(lab.is_bought.sum())} | not_yet {int(lab.is_not_yet.sum())} | best {int(lab.is_best.sum())}"
          f" | distinct tickers {lab.screen_ticker.nunique()} | distinct (ticker, screen_date) {len(lab.drop_duplicates(['screen_ticker', 'screen_date']))}")
    lab["era"] = np.where(lab.screen_date <= ERA_A_LAST_E, "A", "B")
    print(f"- era by screen date (<= {ERA_A_LAST_E} -> A): {dict(Counter(lab.era))}")

    # ------------------------------------------------------------------ calendars
    cal = {"A": read_cal(CAL_A), "B": read_cal(CAL_B, CUT_B)}
    assert cal["B"][-1] <= CUT_B and cal["A"][-1] == "2022-06-30"
    print(f"- calendars: A {len(cal['A'])} sessions {cal['A'][0]}..{cal['A'][-1]} | B {len(cal['B'])} sessions {cal['B'][0]}..{cal['B'][-1]}")

    # ------------------------------------------------------------------ era A export symbols + aliases
    sym_a = set(pd.read_csv(EXPORT_A, header=None, usecols=[0], dtype=str, keep_default_na=False)[0].unique())
    print(f"- era A export symbols {len(sym_a)}")
    alias_maps = []
    for f in ALIASES:
        m = {}
        for r in csv.DictReader(open(f), delimiter="\t"):
            drop = r.get("dropped_symbol") or r.get("symbol") or r.get("polygon_ticker")
            keep = r.get("kept_symbol") or r.get("alpaca_symbol") or (r.get("reason", "").split("_of_")[-1].split("(")[0] if "_of_" in r.get("reason", "") else "")
            if drop and keep:
                m[drop] = keep
        alias_maps.append((os.path.basename(f), m))

    def resolve_a(t: str) -> tuple[str, str]:
        if t in sym_a:
            return t, "own"
        for name, m in alias_maps:
            k = m.get(t)
            if k and k in sym_a:
                return k, name
        return t, "unresolved"

    res = [resolve_a(t) if e == "A" else (t, "own") for t, e in zip(lab.screen_ticker, lab.era)]
    lab["sym"] = [r[0] for r in res]
    lab["resolved_via"] = [r[1] for r in res]
    print(f"- era A symbol resolution: {dict(Counter(lab.loc[lab.era == 'A', 'resolved_via']))}")
    for t, s, v in lab.loc[(lab.era == "A") & (lab.resolved_via != "own"), ["screen_ticker", "sym", "resolved_via"]].drop_duplicates().itertuples(index=False):
        print(f"    {t} -> {s} via {v}")

    # ------------------------------------------------------------------ candidates (breakout events)
    cand = {}
    ca = pd.read_csv(CAND_A, sep="\t", usecols=CAND_COLS, dtype=STR, keep_default_na=False)
    assert (ca.split == "pre").all() and ca.E.max() == ERA_A_LAST_E and ca.E.min() >= "2017-03-02"
    cand["A"] = ca
    dropped_b = Counter()

    def keep_b(ch):
        n0 = len(ch)
        ch = ch[ch.split == "discovery"]
        dropped_b["not_discovery"] += n0 - len(ch)
        n1 = len(ch)
        ch = ch[(ch.E <= CUT_B) & (ch.D <= CUT_B)]
        dropped_b["dated_after_cut"] += n1 - len(ch)
        return ch

    cb = pd.concat([read_tsv_filtered(CAND_B, CAND_COLS, keep_b), read_tsv_filtered(CAND_B_COM, CAND_COLS, keep_b)], ignore_index=True)
    assert cb.E.max() <= CUT_B and cb.D.max() <= CUT_B
    cand["B"] = cb
    print(f"- era B candidate rows dropped at read: {dict(dropped_b)} (holdout rows and the 2025-01-02 breakouts); kept {len(cb)} with max E {cb.E.max()}")
    for e in ("A", "B"):
        c = cand[e]
        c["iE"] = [s_idx(cal[e], x) for x in c.E]
        assert (cal[e][c.iE.to_numpy()] == c.E.to_numpy()).all(), f"era {e}: an E off the SPY calendar"
        c["retrigger"] = c.retrigger.astype(int)
        print(f"- era {e} candidates by K (rows; first breaks): " + " | ".join(
            f"{k} {len(g)}; {int((g.retrigger == 0).sum())}" for k, g in c.groupby("K")) + f"; E range {c.E.min()}..{c.E.max()}")
    e_range = {e: (int(cand[e].loc[cand[e].K == "tl", "iE"].min()), int(cand[e].loc[cand[e].K == "tl", "iE"].max())) for e in ("A", "B")}

    # per-era, per-K same-day and same-week counts (the denominators)
    day_all, day_first, wk_all, wk_first = {}, {}, {}, {}
    for e in ("A", "B"):
        for k, g in cand[e].groupby("K"):
            day_all[(e, k)] = Counter(g.E)
            day_first[(e, k)] = Counter(g.loc[g.retrigger == 0, "E"])
            iso = g.E.map(lambda s: date.fromisoformat(s).isocalendar()[:2])
            wk_all[(e, k)] = Counter(iso)
            wk_first[(e, k)] = Counter(iso[g.retrigger == 0])
    # per (era, K, symbol): arrays of iE and row positions
    ev = {}
    for e in ("A", "B"):
        for (k, t), g in cand[e].groupby(["K", "ticker"]):
            g = g.sort_values("iE")
            ev[(e, k, t)] = (g.iE.to_numpy(), g.index.to_numpy())

    # ------------------------------------------------------------------ watch rows of the label symbols
    label_syms = set(lab.sym)
    watch_syms = {}
    watch = {}
    for e, path in (("A", WATCH_A), ("B", WATCH_B)):
        seen = set()
        wdrop = Counter()

        def keep_w(ch, e=e, seen=seen, wdrop=wdrop):
            if e == "B":                                   # the cut FIRST: no name, no date from a holdout row reaches any set
                n0 = len(ch)
                ch = ch[(ch.split == "discovery") & (ch.watch_date <= CUT_B)]
                wdrop["dropped_after_cut_or_holdout"] += n0 - len(ch)
            seen.update(ch.ticker.unique())
            return ch[ch.ticker.isin(label_syms)]

        w = read_tsv_filtered(path, WATCH_COLS, keep_w)
        if e == "B":
            assert w.watch_date.max() <= CUT_B
        watch_syms[e] = seen
        w["iD"] = [s_idx(cal[e], x) for x in w.watch_date]
        watch[e] = w
        print(f"- era {e} watch: tickers ever watched {len(seen)}; rows kept for the {len(label_syms)} label symbols {len(w)}"
              + (f"; dropped at read {dict(wdrop)}" if wdrop else "") + f"; dates {w.watch_date.min()}..{w.watch_date.max()}")
    wrows = {e: {(t, i): r for t, i, r in zip(watch[e].ticker, watch[e].iD, watch[e].index)} for e in ("A", "B")}
    wdates = {e: defaultdict(set) for e in ("A", "B")}
    for e in ("A", "B"):
        for t, i in zip(watch[e].ticker, watch[e].iD):
            wdates[e][t].add(i)

    # ------------------------------------------------------------------ bdef membership (R1 / R2 flags only)
    fills, r1 = {}, {}
    for e in ("A", "B"):
        f = pd.read_csv(BDEF_FILLS[e], sep="\t", usecols=BDEF_FILL_COLS, dtype=STR, keep_default_na=False)
        r = pd.read_csv(BDEF_R1[e], sep="\t", usecols=BDEF_R1_COLS, dtype=STR, keep_default_na=False)
        if e == "B":
            assert f.E.max() <= CUT_B and r.E.max() <= CUT_B and r.entry_date.max() <= CUT_B
        fills[e] = set(zip(f.ticker, f.E))
        r1[e] = {(t, E): (ed, int(x)) for t, E, ed, x in zip(r.ticker, r.E, r.entry_date, r.r2_exp)}
        print(f"- era {e} bdef: published fills {len(fills[e])} (ticker, E) | R1 rows {len(r1[e])} | R2 {sum(v[1] for v in r1[e].values())}"
              + ("  [era A bdef tables were built on the OLD export cb702_pre: membership is three-valued]" if e == "A" else ""))

    typed = {}
    for e in ("A", "B"):
        typed[e] = {ln.split("|")[0] for ln in open(SIC[e])}

    # ------------------------------------------------------------------ the join, per label
    rows = []
    for L in lab.itertuples(index=False):
        e = L.era
        c = cal[e]
        i0 = s_idx(c, L.screen_date)
        s0 = c[i0] if i0 >= 0 else ""
        lo, hi = i0 - W_BACK, i0 + W_FWD
        emin, emax = e_range[e]
        if hi < emin or lo > emax:
            cov = "none"
        elif lo >= emin and hi <= emax:
            cov = "full"
        else:
            cov = "partial"
        rec = dict(vid=L.vid, ts=L.ts, frame_id=L.frame_id, screen_ticker=L.screen_ticker, sym=L.sym, resolved_via=L.resolved_via,
                   screen_date=L.screen_date, s0=s0, s0_mapped=int(s0 != L.screen_date), era=e, coverage=cov, grade=L.grade,
                   is_bought=int(L.is_bought), is_not_yet=int(L.is_not_yet), is_best=int(L.is_best),
                   typed=int(L.sym in typed[e]), watched_ever=int(L.sym in watch_syms[e]))
        # watch state at s0 and in the window
        rec["watch_in_window"] = int(any(lo <= i <= hi for i in wdates[e].get(L.sym, ())))
        wr = wrows[e].get((L.sym, i0))
        rec["watch_at_s0"] = int(wr is not None)
        rec["c0_tl_at_s0"] = int(watch[e].at[wr, "C0_tl"]) if wr is not None else -1
        rec["base_len_at_s0"] = watch[e].at[wr, "base_len"] if wr is not None else ""
        rec["no_break_yet"] = -1
        rec["no_break_yet_base"] = -1
        if wr is not None:
            pd_ = watch[e].at[wr, "pole_date"]
            arr = ev.get((e, "tl", L.sym))
            broke = False
            broke_base = False
            if arr is not None:
                ie, pos = arr
                m = ie <= i0
                broke = bool((cand[e].loc[pos[m], "pole_date"] == pd_).any())
                # round 2, the drift-robust key: the base_ids any tl row of the symbol carries under this pole_date, then any
                # tl event of those base_ids with E <= s0 (a pole re-dated by a day keeps its base_id)
                bids = set(cand[e].loc[pos[cand[e].loc[pos, "pole_date"].to_numpy() == pd_], "base_id"])
                broke_base = bool(cand[e].loc[pos[m], "base_id"].isin(bids).any()) if bids else broke
            rec["no_break_yet"] = int(not broke)
            rec["no_break_yet_base"] = int(not broke_base)
        # nearest event per K
        for k in (("tl", "com") if e == "A" else ("tl", "com", "k5", "k10", "full")):
            arr = ev.get((e, k, L.sym))
            rec[f"n_win_{k}"] = 0
            rec[f"delta_{k}"] = ""
            rec[f"E_{k}"] = ""
            rec[f"delta_first_{k}"] = ""
            rec[f"delta_wide_{k}"] = ""
            if arr is None:
                continue
            ie, pos = arr
            d = ie - i0
            inwin = (d >= -W_BACK) & (d <= W_FWD)
            rec[f"n_win_{k}"] = int(inwin.sum())

            def nearest(mask):
                if not mask.any():
                    return None
                dd = d[mask]
                pp = pos[mask]
                order = np.lexsort((-dd, np.abs(dd)))        # |delta| ascending, then the LATER E first on a tie
                return int(dd[order[0]]), int(pp[order[0]])

            nb = nearest(inwin)
            if nb is not None:
                rec[f"delta_{k}"], p = nb
                rec[f"E_{k}"] = cand[e].at[p, "E"]
                if k == "tl":
                    rec["retrigger_tl"] = int(cand[e].at[p, "retrigger"])
                    rec["chain_tl"] = cand[e].at[p, "retrigger_chain"]
                    rec["base_id_tl"] = cand[e].at[p, "base_id"]
                    rec["pole_date_tl"] = cand[e].at[p, "pole_date"]
                    rec["C1_tl"] = int(cand[e].at[p, "C1"])
                    rec["D_tl"] = cand[e].at[p, "D"]
            nf = nearest(inwin & (cand[e].loc[pos, "retrigger"].to_numpy() == 0))
            if nf is not None:
                rec[f"delta_first_{k}"] = nf[0]
            nw = nearest((d >= -WIDE) & (d <= WIDE))
            if nw is not None:
                rec[f"delta_wide_{k}"] = nw[0]
        # R1 / R2 membership + same-day population of the matched tl event
        if rec["E_tl"]:
            key = (L.sym, rec["E_tl"])
            if key in r1[e]:
                ed, r2 = r1[e][key]
                rec["r1_status"] = "R1"
                rec["r2"] = r2
                ir = s_idx(c, ed)
                rec["r1_off_from_E"] = ir - rec["delta_tl"] - i0
                rec["delta_r1"] = ir - i0
            elif key in fills[e]:
                rec["r1_status"] = "fill_no_R1"
                rec["r2"] = 0
                rec["r1_off_from_E"] = ""
                rec["delta_r1"] = ""
            else:
                rec["r1_status"] = "not_in_fill_population"
                rec["r2"] = -1
                rec["r1_off_from_E"] = ""
                rec["delta_r1"] = ""
            iso = date.fromisoformat(rec["E_tl"]).isocalendar()[:2]
            rec["sameday_other_all"] = day_all[(e, "tl")][rec["E_tl"]] - 1
            rec["sameday_other_first"] = day_first[(e, "tl")][rec["E_tl"]] - (1 if rec["retrigger_tl"] == 0 else 0)
            rec["week_all"] = wk_all[(e, "tl")][iso]
            rec["week_first"] = wk_first[(e, "tl")][iso]
        rows.append(rec)
    J = pd.DataFrame(rows)
    J.to_csv(f"{OUT}/labels_joined.tsv", sep="\t", index=False)
    J["matched"] = J.E_tl.ne("")
    Jc = J[J.coverage != "none"]

    # ------------------------------------------------------------------ 1. funnel
    print("\n## 1. Funnel per era (labels -> coverage -> symbol -> watched -> in a base in the window -> matched to a tl event)")
    for e in ("A", "B"):
        g = J[J.era == e]
        gc = g[g.coverage != "none"]
        print(f"- era {e}: labels {len(g)} | coverage none {int((g.coverage == 'none').sum())} / partial {int((g.coverage == 'partial').sum())} / full {int((g.coverage == 'full').sum())}"
              f" | s0 mapped from a non-session date {int(g.s0_mapped.sum())}")
        print(f"    of the {len(gc)} with coverage: symbol unresolved {int((gc.resolved_via == 'unresolved').sum())} | never in our watch table {int((gc.watched_ever == 0).sum())}"
              f" (untyped in the SIC file, likely ETF/ETN/unknown: {int(((gc.watched_ever == 0) & (gc.typed == 0)).sum())})"
              f" | watched ever but no watch row in the window {int(((gc.watched_ever == 1) & (gc.watch_in_window == 0)).sum())}"
              f" | watch row in the window but no tl event in it {int(((gc.watch_in_window == 1) & ~gc.matched).sum())}"
              f" | MATCHED {int(gc.matched.sum())}")
        nn = g[g.coverage == "none"]
        if len(nn):
            print(f"    coverage none: {sorted(Counter(nn.screen_date.str[:7]).items())}")
    never = Jc[Jc.watched_ever == 0]
    print(f"- never-watched symbols (coverage != none): {sorted(Counter(never.sym).items(), key=lambda x: -x[1])}")

    # ------------------------------------------------------------------ 2. join rate per grade x era
    print(f"\n## 2. Join rate — a tl event within [s0-{W_BACK}, s0+{W_FWD}] (denominator = labels with full + partial coverage; full-only beside)")
    for e in ("A", "B"):
        for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet"), ("best", "is_best")):
            g = Jc[(Jc.era == e) & (Jc[col] == 1)]
            gf = g[g.coverage == "full"]
            print(f"- era {e} {name:8s}: matched {pct(int(g.matched.sum()), len(g))} | full-only {pct(int(gf.matched.sum()), len(gf))}"
                  f" | >1 event in window {int((g.n_win_tl > 1).sum())} | nearest is a retrigger {int((g.matched & (g.retrigger_tl == 1)).sum())}"
                  f" | first-break in window {int(g.delta_first_tl.ne('').sum())}")
    print(f"- all grades: era A {pct(int(Jc[Jc.era == 'A'].matched.sum()), int((Jc.era == 'A').sum()))} | era B {pct(int(Jc[Jc.era == 'B'].matched.sum()), int((Jc.era == 'B').sum()))}")

    # ------------------------------------------------------------------ 3. position
    print("\n## 3. Position of the matched labels relative to our breakout day E (delta = idx(E) - idx(s0); >0 = label BEFORE the breakout)")

    def split(d: pd.Series, title: str):
        d = d.astype(int)
        n = len(d)
        if n == 0:
            print(f"- {title}: n = 0")
            return
        before = int((d >= 1).sum()); on = int((d == 0).sum()); after = int((d <= -1).sum())
        band = int(((d >= ON_BAND[0]) & (d <= ON_BAND[1])).sum()); band2 = int(((d >= ON_BAND_WIDE[0]) & (d <= ON_BAND_WIDE[1])).sum())
        print(f"- {title}: n = {n} | label BEFORE the breakout (delta >= +1) {pct(before, n)} | ON it (delta = 0) {pct(on, n)} | AFTER it (delta <= -1) {pct(after, n)}"
              f" | within [-1, +1] {pct(band, n)} | within [-2, +1] {pct(band2, n)} | median delta {float(d.median()):+.1f} | quartiles {float(d.quantile(.25)):+.1f}..{float(d.quantile(.75)):+.1f}")
        print(f"    histogram (delta: n): " + " ".join(f"{k:+d}:{v}" for k, v in sorted(Counter(d).items())))

    for e in ("A", "B"):
        for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet"), ("best", "is_best")):
            g = Jc[(Jc.era == e) & (Jc[col] == 1) & Jc.matched]
            split(g.delta_tl, f"era {e} {name} vs nearest tl event (first breaks and retriggers)")
            g2 = g[g.delta_first_tl.ne("")]
            split(g2.delta_first_tl, f"era {e} {name} vs nearest FIRST BREAK (retrigger = 0) in the window")
    print("- the same for the distinct (era, sym, E) events (a label-dense stock counts once per event); the event's delta = the label"
          " CLOSEST to E (|delta| smallest, the later label on a tie); round 1's 'first label in file order' beside:")
    for e in ("A", "B"):
        g = Jc[(Jc.era == e) & (Jc.is_bought == 1) & Jc.matched].copy()
        g["_d"] = g.delta_tl.astype(int)
        g["_a"] = g._d.abs()
        g["_n"] = -g._d
        gc = g.sort_values(["_a", "_n"], kind="stable").drop_duplicates(["sym", "E_tl"])
        split(gc.delta_tl, f"era {e} bought, distinct events (closest label)")
        split(g.drop_duplicates(["sym", "E_tl"]).delta_tl, f"era {e} bought, distinct events (first label in file order, round 1)")

    # 3b. placebo: the same symbols on every OTHER session near one of their bases — what a random "near a base" date reads
    print(f"\n## 3b. PLACEBO — every session t of the same symbols (era A) with a watch row in [t-{W_BACK}, t+{W_FWD}] and a tl event in that window,"
          f" excluding sessions within +-{W_FWD} of any label of that symbol: the delta of the nearest tl event (what a random near-a-base date reads;"
          f" the labels' 'on' share is signal only if it exceeds this)")
    for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet")):
        g = Jc[(Jc.era == "A") & (Jc[col] == 1)]
        syms = sorted(set(g.sym))
        lab_idx = defaultdict(list)
        for s, i in zip(J.loc[J.era == "A", "sym"], J.loc[J.era == "A", "s0"]):
            if i:
                lab_idx[s].append(s_idx(cal["A"], i))
        deltas = []
        n_sessions = 0
        n_syms_used = 0
        for s in syms:
            arr = ev.get(("A", "tl", s))
            wd = wdates["A"].get(s)
            if arr is None or not wd:
                continue
            n_syms_used += 1
            ie, _ = arr
            li = np.array(lab_idx[s])
            for t in range(e_range["A"][0] + W_BACK, e_range["A"][1] - W_FWD + 1):
                if (np.abs(li - t) <= W_FWD).any():
                    continue
                if not any(t - W_BACK <= i <= t + W_FWD for i in wd):
                    continue
                n_sessions += 1
                d = ie - t
                m = (d >= -W_BACK) & (d <= W_FWD)
                if m.any():
                    dd = d[m]
                    order = np.lexsort((-dd, np.abs(dd)))
                    deltas.append(int(dd[order[0]]))
        if deltas:
            split(pd.Series(deltas), f"placebo for the {name} symbols' near-a-base sessions ({len(syms)} symbols with a {name} label and coverage, {n_syms_used} with a watch row and a tl event;"
                  f" t in [Emin+{W_BACK}, Emax-{W_FWD}], t not within +-{W_FWD} of ANY attributed label of the symbol; {n_sessions} sessions, {len(deltas)} with a tl event in the window)")
            if name == "bought":
                placebo_hist = Counter(deltas)
                placebo_n = len(deltas)

    # the target decision rule
    print(f"\n## 4. TARGET DECISION RULE (fixed in the header; applied to era A bought labels, full + partial coverage)")
    g = Jc[(Jc.era == "A") & (Jc.is_bought == 1) & Jc.matched]
    d = g.delta_tl.astype(int)
    n = len(d)
    sh_before = float((d >= 1).mean()) if n else float("nan")
    sh_on = float(((d >= ON_BAND_WIDE[0]) & (d <= ON_BAND_WIDE[1])).mean()) if n else float("nan")
    if sh_before >= TARGET_SHARE:
        verdict = "PRE-BREAKOUT STATE (decision time = the watch night D)"
    elif sh_on >= TARGET_SHARE:
        verdict = "BREAKOUT DAY (decision time = E)"
    else:
        verdict = "NEITHER reaches 60% -> both reported; the registration takes the breakout-day target with state features read at D"
    print(f"- n = {n} | share with delta >= +1 (label before our breakout) {sh_before:.1%} | share in [-2, +1] (on the breakout day) {sh_on:.1%} -> {verdict}")
    # round 2: the labels' excess over the placebo, per delta (what the timing actually shows beyond a random near-a-base date)
    hist = Counter(d)
    exp = {k: placebo_hist.get(k, 0) / placebo_n * n for k in range(-W_BACK, W_FWD + 1)}
    print(f"- against the placebo (expected = placebo share x {n}): before (delta >= +1) {int((d >= 1).sum())} vs {sum(v for k, v in exp.items() if k >= 1):.1f} expected"
          f" | on (0) {hist.get(0, 0)} vs {exp[0]:.1f} | after (<= -1) {int((d <= -1).sum())} vs {sum(v for k, v in exp.items() if k <= -1):.1f}"
          f" | one session early (+1) {hist.get(1, 0)} vs {exp[1]:.1f} | two early (+2) {hist.get(2, 0)} vs {exp[2]:.1f}"
          f" | the excess sits at delta 0 only: {hist.get(0, 0) - exp[0]:+.1f} labels")
    gr = g[g.delta_r1.ne("")]
    if len(gr):
        dr = gr.delta_r1.astype(int)
        print(f"- second anchor, the R1 day (his definition: the first close above the base high; n = {len(gr)} of the {n} with an R1 row): "
              f"label before the R1 day {float((dr >= 1).mean()):.1%} | in [-2, +1] {float(((dr >= -2) & (dr <= 1)).mean()):.1%} | after {float((dr <= -1).mean()):.1%}"
              f" | median delta to the R1 day {float(dr.median()):+.1f}")
        print(f"    histogram (delta to the R1 day: n): " + " ".join(f"{k:+d}:{v}" for k, v in sorted(Counter(dr).items())))
        off = gr.r1_off_from_E.astype(int)
        print(f"    R1 day's offset from our E (sessions; 0 = the base high was closed above on E itself): 0: {int((off == 0).sum())} | 1-5: {int(((off >= 1) & (off <= 5)).sum())} | 6-20: {int(((off >= 6) & (off <= 20)).sum())} | >20: {int((off > 20).sum())}")

    # ------------------------------------------------------------------ 5. watch state
    print("\n## 5. Watch state on the screen date (a watch row = the stock passed our C0 structural gates that night)")
    for e in ("A", "B"):
        for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet"), ("best", "is_best")):
            g = Jc[(Jc.era == e) & (Jc[col] == 1)]
            n = len(g)
            w0 = int((g.watch_at_s0 == 1).sum())
            nb = int(((g.watch_at_s0 == 1) & (g.no_break_yet == 1)).sum())
            nbb = int(((g.watch_at_s0 == 1) & (g.no_break_yet_base == 1)).sum())
            c0 = int(((g.watch_at_s0 == 1) & (g.c0_tl_at_s0 == 1)).sum())
            print(f"- era {e} {name:8s}: n = {n} | watch row AT s0 {pct(w0, n)} | of those: a tl line exists (C0_tl = 1) {c0}; same base NOT yet broken at s0 {pct(nb, n)} (pole_date key, round 1)"
                  f" / {pct(nbb, n)} (base_id key, drift-robust)"
                  f" | watch row anywhere in the window {pct(int((g.watch_in_window == 1).sum()), n)} | unmatched but in a base in the window {int(((g.watch_in_window == 1) & ~g.matched).sum())}")
            dr = g[(g.watch_at_s0 == 1) & (g.no_break_yet == 1) & (g.no_break_yet_base == 0)]
            if len(dr):
                print(f"    unbroken under the pole_date key but already broken under base_id (a drifted pole): {sorted(zip(dr.frame_id, dr.sym))}")

    # ------------------------------------------------------------------ 6. R1 / R2 membership of the matched events
    print("\n## 6. R1 / R2 membership of the matched tl events (bdef flags, descriptive; era A's bdef is on the OLD export -> three-valued)")
    for e in ("A", "B"):
        for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet"), ("best", "is_best")):
            g = Jc[(Jc.era == e) & (Jc[col] == 1) & Jc.matched]
            ge = g.drop_duplicates(["sym", "E_tl"])
            st = Counter(ge.r1_status)
            r2 = int((ge.r2 == 1).sum())
            print(f"- era {e} {name:8s}: distinct events {len(ge)} | R1 {st.get('R1', 0)} | published fill without R1 within 60 {st.get('fill_no_R1', 0)} | not in the fill population {st.get('not_in_fill_population', 0)}"
                  f" | R2 (expansion day) {r2} | labels {len(g)}")
    # the era-wide base rates of the same flags, for reference (fills -> R1 -> R2 over every published fill)
    for e in ("A", "B"):
        nf = len(fills[e]); nr = len(r1[e]); nr2 = sum(v[1] for v in r1[e].values())
        print(f"- era {e} base rate over every published fill: R1 {pct(nr, nf)} | R2 {pct(nr2, nf)}")

    # ------------------------------------------------------------------ 7. distinct events and the same-day population
    print("\n## 7. Distinct breakout events marked, and the same-day population (the 'which breakout to pick' denominator)")
    M = Jc[Jc.matched]
    me = M.groupby(["era", "sym", "E_tl"]).agg(labels=("frame_id", "size"), bought=("is_bought", "sum"), not_yet=("is_not_yet", "sum"), best=("is_best", "sum"),
                                                 retrigger=("retrigger_tl", "first"), chain=("chain_tl", "first"), base_id=("base_id_tl", "first"), D=("D_tl", "first"),
                                                 C1=("C1_tl", "first"), r1_status=("r1_status", "first"), r2=("r2", "first"),
                                                 sameday_other_all=("sameday_other_all", "first"), sameday_other_first=("sameday_other_first", "first"),
                                                 week_all=("week_all", "first"), week_first=("week_first", "first"),
                                                 delta_min=("delta_tl", "min"), delta_max=("delta_tl", "max")).reset_index()
    me.to_csv(f"{OUT}/matched_events.tsv", sep="\t", index=False)
    for e in ("A", "B"):
        g = me[me.era == e]
        gb = g[g.bought > 0]
        print(f"- era {e}: distinct (sym, E) events {len(g)} (bought {len(gb)}, not_yet {int((g.not_yet > 0).sum())}, best {int((g.best > 0).sum())})"
              f" | distinct bases (sym, base_id — the drift-robust key) {len(g.drop_duplicates(['sym', 'base_id']))}"
              f" | distinct symbols {g.sym.nunique()} | labels per event: 1: {int((g.labels == 1).sum())}, 2: {int((g.labels == 2).sum())}, 3+: {int((g.labels >= 3).sum())}"
              f" | C1 among bought events {int(gb.C1.sum())}")
        for name, gg in (("bought events", gb), ("not_yet events", g[g.not_yet > 0])):
            if len(gg) == 0:
                continue
            print(f"    {name} (n = {len(gg)}): OTHER tl events the same day — all rows median {float(gg.sameday_other_all.median()):.0f} (mean {float(gg.sameday_other_all.mean()):.1f});"
                  f" first breaks median {float(gg.sameday_other_first.median()):.0f} (mean {float(gg.sameday_other_first.mean()):.1f})"
                  f" | tl events in the ISO week — all rows median {float(gg.week_all.median()):.0f}, first breaks median {float(gg.week_first.median()):.0f}")
        # era-wide weekly stream for reference
        wa = wk_all[(e, "tl")]; wf = wk_first[(e, "tl")]
        print(f"    era {e} weekly stream over every ISO week with an event: all tl rows median {float(np.median(list(wa.values()))):.0f} a week (n = {len(wa)} weeks); first breaks median {float(np.median(list(wf.values()))):.0f}")

    # ------------------------------------------------------------------ 8. per-K join rates
    print("\n## 8. Join rate by breakout level K (same window; tl is the registered level; the others are read beside)")
    for e in ("A", "B"):
        for k in (("tl", "com") if e == "A" else ("tl", "com", "k5", "k10", "full")):
            col = f"E_{k}"
            if col not in Jc:
                continue
            for name, gcol in (("bought", "is_bought"), ("not_yet", "is_not_yet")):
                g = Jc[(Jc.era == e) & (Jc[gcol] == 1)]
                m = g[col].ne("")
                dd = g.loc[m, f"delta_{k}"].astype(int)
                print(f"- era {e} K={k:4s} {name:8s}: matched {pct(int(m.sum()), len(g))} | before {int((dd >= 1).sum())} / on {int((dd == 0).sum())} / after {int((dd <= -1).sum())} | median delta {float(dd.median()) if len(dd) else float('nan'):+.1f}")

    # ------------------------------------------------------------------ 9. wide distribution (beside; the window was not re-tuned)
    print(f"\n## 9. Nearest tl event within [-{WIDE}, +{WIDE}] for EVERY label with coverage (beside; the window above was fixed first)")
    for e in ("A", "B"):
        for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet")):
            g = Jc[(Jc.era == e) & (Jc[col] == 1)]
            m = g.delta_wide_tl.ne("")
            dd = g.loc[m, "delta_wide_tl"].astype(int)
            bins = [(-60, -21), (-20, -11), (-10, -3), (-2, 1), (2, 5), (6, 10), (11, 20), (21, 40), (41, 60)]
            print(f"- era {e} {name:8s}: any tl event within +-{WIDE} {pct(int(m.sum()), len(g))} | " + " ".join(f"[{a:+d},{b:+d}]:{int(((dd >= a) & (dd <= b)).sum())}" for a, b in bins))

    # ------------------------------------------------------------------ 10. positive controls
    print("\n## 10. Positive controls — three labels to check by hand on the frame (ticker, screen date, matched E, delta, frame)")
    picks = []
    # picked by rule, not by eye: the lowest frame id of (a) a pure 'bought' era-A label whose matched tl event is a FIRST break on the
    # screen date, (b) a pure 'not_yet' label matched to an event AFTER the screen date, (c) the era-B label g_0957 (MDGL 2023-01-26)
    ga = Jc[(Jc.era == "A") & (Jc.grade == "bought") & Jc.matched & (Jc.delta_tl == 0) & (Jc.retrigger_tl == 0)].sort_values("frame_id")
    if len(ga):
        picks.append(ga.iloc[0])
    gn = Jc[(Jc.grade == "not_yet") & Jc.matched & (Jc.delta_tl.apply(lambda x: x != "" and int(x) >= 1))].sort_values("frame_id")
    if len(gn):
        picks.append(gn.iloc[0])
    gb = Jc[(Jc.frame_id == "g_0957")]
    if len(gb):
        picks.append(gb.iloc[0])
    for p in picks:
        print(f"- {p.frame_id}: {p.screen_ticker} ({p.sym}) screen {p.screen_date} (s0 {p.s0}) grade {p.grade} era {p.era} | matched E {p.E_tl or '-'} delta {p.delta_tl if p.E_tl else '-'}"
              f" | retrigger {int(p.retrigger_tl) if p.E_tl else '-'} | watch at s0 {p.watch_at_s0} no_break_yet {p.no_break_yet} | R1 {p.r1_status if p.E_tl else '-'} R2 {int(p.r2) if p.E_tl else '-'}"
              f" | D {p.D_tl if p.E_tl else '-'} pole {p.pole_date_tl if p.E_tl else '-'}"
              f" | frame {FRAMES if not p.frame_id.startswith('b1_') else f'{B}/qm_streams/vision/frames'}/{p.frame_id}.png")

    # ================================================================== ROUND 2 (2026-10-23) — counts the registration needs
    # ------------------------------------------------------------------ 11. label timing per POSITIVE event (bought or best)
    print("\n## 11. Label timing per POSITIVE event (bought or best; the positive labels' deltas only — a not_yet label on the same event does not count)"
          f"\n#     ON OR BEFORE = at least one positive label with delta >= 0 (said on or before E); POST-E ONLY = every positive label after E (hindsight);"
          f"\n#     STRICTLY BEFORE = at least one positive label with delta >= +1. Fit = E <= {FIT_LAST_E}; hold-out = 2021 (era A); era B = the 2022-23 check")
    Jp = Jc[Jc.matched & ((Jc.is_bought == 1) | (Jc.is_best == 1))].copy()
    Jp["_d"] = Jp.delta_tl.astype(int)
    Jp["_z"] = (Jp._d == 0).astype(int)
    tim = Jp.groupby(["era", "sym", "E_tl"]).agg(dmin=("_d", "min"), dmax=("_d", "max"), at0=("_z", "max")).reset_index()
    tim["fit"] = tim.E_tl <= FIT_LAST_E
    timing_keys = {}
    for e in ("A", "B"):
        g = tim[tim.era == e]
        onb, post, strict = g.dmax >= 0, g.dmax < 0, g.dmax >= 1
        f = g.fit
        sp = (lambda m: f" ({int((m & f).sum())} fit / {int((m & ~f).sum())} 2021)") if e == "A" else (lambda m: "")
        print(f"- era {e}: positive events {len(g)}{sp(g.dmax == g.dmax) if e == 'A' else ' (all in the 2022-23 check)'}"
              f" | ON OR BEFORE E {int(onb.sum())}{sp(onb)} | POST-E ONLY {int(post.sum())}{sp(post)} | STRICTLY BEFORE {int(strict.sum())}{sp(strict)}"
              f" | a positive label exactly AT delta 0 {int(g.at0.sum())}")
        timing_keys[e] = {"onb": set(zip(g.sym[onb], g.E_tl[onb])), "post": set(zip(g.sym[post], g.E_tl[post]))}
    # bought-only, for the record
    gb_ = Jp[Jp.is_bought == 1].groupby(["era", "sym", "E_tl"])._d.max().reset_index()
    print(f"- bought-only events: era A {int((gb_.era == 'A').sum())}, on-or-before {int(((gb_.era == 'A') & (gb_._d >= 0)).sum())}, post-E only {int(((gb_.era == 'A') & (gb_._d < 0)).sum())}"
          f" | era B {int((gb_.era == 'B').sum())}, on-or-before {int(((gb_.era == 'B') & (gb_._d >= 0)).sum())}")

    # ------------------------------------------------------------------ 12. the same-day NEGATIVES on the graded dates, labelled bases excluded
    print("\n## 12. Same-day negatives: every OTHER tl row on the dates of the positive events. ROUND 3 RULE (registered): a row is EXCLUDED only if its"
          "\n#     (sym, base_id) carries a matched label of any grade said ON OR BEFORE that row's own E (s0 <= E) - a label said later would drop the row"
          "\n#     because of what happened after its breakout day (hindsight). The round-2 rule (a label at any time) is printed beside, not used.")
    lab_bases = {e: set(zip(me.loc[me.era == e, "sym"], me.loc[me.era == e, "base_id"])) for e in ("A", "B")}
    lab_first = {}                                         # (era, sym, base_id) -> the earliest session date a matched label was said on that base
    for r in M.itertuples():
        k = (r.era, r.sym, r.base_id_tl)
        lab_first[k] = min(lab_first.get(k, r.s0), r.s0)
    ny_keys = {e: set(zip(me.loc[(me.era == e) & (me.not_yet > 0), "sym"], me.loc[(me.era == e) & (me.not_yet > 0), "E_tl"])) for e in ("A", "B")}
    for e in ("A", "B"):
        c = cand[e][cand[e].K == "tl"]
        for title, poskeys in (("ALL positive events (round 1's GRADED)", timing_keys[e]["onb"] | timing_keys[e]["post"]),
                               ("positive events ON OR BEFORE E (the GRADED arm)", timing_keys[e]["onb"])):
            dates = {E for _, E in poskeys}
            on = c[c.E.isin(dates)]
            isp = np.array([(t, E) in poskeys for t, E in zip(on.ticker, on.E)])
            oth = on[~isp]
            lb_any = np.array([(t, b) in lab_bases[e] for t, b in zip(oth.ticker, oth.base_id)]) if len(oth) else np.array([], dtype=bool)
            lb = np.array([lab_first.get((e, t, b), "9999") <= E for t, b, E in zip(oth.ticker, oth.base_id, oth.E)]) if len(oth) else np.array([], dtype=bool)
            isny = np.array([(t, E) in ny_keys[e] for t, E in zip(oth.ticker, oth.E)]) if len(oth) else np.array([], dtype=bool)
            ispost = np.array([(t, E) in timing_keys[e]["post"] for t, E in zip(oth.ticker, oth.E)]) if len(oth) else np.array([], dtype=bool)
            fitm = (oth.E <= FIT_LAST_E).to_numpy() if len(oth) else np.array([], dtype=bool)
            sp = (lambda m: f" (fit {int((m & fitm).sum())} / 2021 {int((m & ~fitm).sum())})") if e == "A" else (lambda m: "")
            print(f"- era {e}, {title}: {len(poskeys)} events on {len(dates)} dates | other tl rows on those dates {len(oth)}{sp(np.ones(len(oth), dtype=bool))}"
                  f" | on a LABELLED base, excluded {int(lb.sum())}{sp(lb)}; of them not_yet events {int((lb & isny).sum())},"
                  f" post-E-only positive events {int((lb & ispost).sum())}"
                  f" | NEGATIVES {int((~lb).sum())}{sp(~lb)}"
                  f" || beside, the round-2 rule (a label at ANY time): excluded {int(lb_any.sum())}{sp(lb_any)}, negatives {int((~lb_any).sum())}{sp(~lb_any)};"
                  f" rows excluded under it only because of a LATER label {int((lb_any & ~lb).sum())}{sp(lb_any & ~lb)}")

    # ------------------------------------------------------------------ 13. the readiness contrast's populations (state at the label date s0)
    print("\n## 13. Readiness contrast populations (the state he was looking at = the watch row at s0; a label with no watch row at s0 cannot be scored there)")
    for e in ("A", "B"):
        for name, col in (("bought", "is_bought"), ("not_yet", "is_not_yet"), ("best", "is_best")):
            g = Jc[(Jc.era == e) & (Jc[col] == 1)]
            if len(g) == 0:
                continue
            print(f"- era {e} {name:8s}: labels with coverage {len(g)} | a watch row at s0 {int((g.watch_at_s0 == 1).sum())} (with a tl line {int(((g.watch_at_s0 == 1) & (g.c0_tl_at_s0 == 1)).sum())})"
                  f" | matched labels {int(g.matched.sum())}, of which delta in {{0, +1}} (scorable at D of the matched event with at most one session of drift) {int(g.loc[g.matched, 'delta_tl'].astype(int).isin([0, 1]).sum())}")
    ga = me[me.era == "A"]
    bb = set(zip(ga.loc[ga.bought > 0, "sym"], ga.loc[ga.bought > 0, "base_id"]))
    ny = ga[ga.not_yet > 0]
    print(f"- era A not_yet events {len(ny)}: share a base (sym, base_id) with a bought event {sum((s, b) in bb for s, b in zip(ny.sym, ny.base_id))}")
    both = ga[(ga.bought > 0) & (ga.not_yet > 0)]
    print(f"- era A events carrying BOTH a bought and a not_yet label: {len(both)} — the order of the two labels (screen date, stream time):")
    order = Counter()

    def secs(ts: str) -> int:
        p = [int(x) for x in ts.split(":")]
        return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]

    for r in both.itertuples():
        g = Jc[(Jc.era == "A") & (Jc.sym == r.sym) & (Jc.E_tl == r.E_tl)]
        nyl = g[g.is_not_yet == 1]
        bl = g[g.is_bought == 1]
        same_frame = bool(set(nyl.frame_id) & set(bl.frame_id))
        same_moment = any(x.vid == y.vid and abs(secs(x.ts) - secs(y.ts)) <= 300 for x in nyl.itertuples() for y in bl.itertuples())
        first_ny_date = min(nyl.screen_date)
        later_buy = any(x.screen_date > first_ny_date for x in bl.itertuples())
        kind = ("one caption window graded both (mixed)" if same_frame else "the same stream moment (within 5 min)" if same_moment
                else "a bought label on a LATER date than the not_yet call" if later_buy else "not_yet after every bought label")
        order[kind] += 1
        print(f"    {r.sym} E {r.E_tl}: not_yet {[(x.screen_date, x.ts) for x in nyl.itertuples()]} | bought {[(x.screen_date, x.ts) for x in bl.itertuples()]} -> {kind}")
    print(f"    summary: {dict(order)}")

    # ------------------------------------------------------------------ 14. where the grade phrase sits
    print("\n## 14. Grade-phrase attribution: 02_graded_moments.py matched the phrase over the caption WINDOW around the ticker's line; here the same"
          " regex is re-applied to the ticker's OWN caption line (`quote`, cut at 220 chars) — 'window only' is therefore an UPPER bound")
    mo = pd.read_csv(MOMENTS, sep="\t", dtype=str, keep_default_na=False)
    assert not mo.duplicated(["video", "ts", "ticker"]).any()
    qmap = {(v, t, c): q for v, t, c, q in zip(mo.video, mo.ts, mo.ticker, mo.quote)}
    att = pd.read_csv(LABELS, sep="\t", dtype=str, keep_default_na=False)
    att = att[att.status == "attributed"]
    inq = {g: [0, 0, 0] for g in GRADE_RX}
    for v, t, c, gr in zip(att.vid, att.ts, att.caption_ticker, att.grade):
        q = qmap.get((v, t, c))
        for g in gr.split(","):
            inq[g][0] += 1
            if q is None:
                inq[g][2] += 1
            elif re.search(GRADE_RX[g], q.lower()):
                inq[g][1] += 1
    for g in ("bought", "not_yet", "best"):
        n_, q_, miss = inq[g]
        print(f"- {g:8s}: labels {n_} | phrase in the ticker's own caption line {q_} ({100.0 * q_ / n_:.1f}%) | only in the surrounding window (upper bound) {n_ - q_ - miss} | no moment row {miss}")

    # ------------------------------------------------------------------ pins
    print("\n## Pins (sha256)")
    for name, path in [("labels", LABELS), ("moments", MOMENTS), ("cal_A", CAL_A), ("cal_B", CAL_B), ("cand_A", CAND_A), ("cand_B", CAND_B), ("cand_B_com", CAND_B_COM),
                       ("watch_A", WATCH_A), ("watch_B", WATCH_B), ("bdef_r1_A", BDEF_R1["A"]), ("bdef_r1_B", BDEF_R1["B"]),
                       ("bdef_fills_A", BDEF_FILLS["A"]), ("bdef_fills_B", BDEF_FILLS["B"]), ("export_A", EXPORT_A)] + [(f"alias_{i}", f) for i, f in enumerate(ALIASES)] + [("this_script", __file__)]:
        print(f"- {name}: {sha(path)}  {path}")
    print(f"- out labels_joined.tsv: {sha(f'{OUT}/labels_joined.tsv')}")
    print(f"- out matched_events.tsv: {sha(f'{OUT}/matched_events.tsv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
