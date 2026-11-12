#!/usr/bin/env python3
"""#717 PRECISION OF THE PICKS — the ~5 names a day the paper book would actually take, not every fire (2026-11-12;
offline, $0, read-only, ERA A ONLY — same store and seal as 01_precision.py; nothing here changes a rule).

HOW THE LIVE SLOTS FILL (read from `broker/breakout_v1_entry.py`, the module docstring + PASS 1/2): from 09:35 ET, each
minute, the names whose state permits a buy are taken in LIST-RANK order (`breakout_v1_list.rank_rows`: order score =
the mean of the within-night percentile of the 6-month run in daily ranges and of the 10-close tightness) into the free
slots (5 - every paper strategy's open / resting rows). A RESTING buy holds its slot (hold-only, no displacement). Since
2026-11-11 the volume pace is NOT a gate, so a buy rests for every name that is not too wide — the slots go to the TOP
OF THE LIST at 09:35, broken out or not; a later breakout waits unless a slot frees.

TWO DAILY-BAR MODELS (no minute bars are read; each is an approximation, declared):
  A "live-like"   walk the night's list in rank order; a name too wide on the day (level - low(E) > ADR20 x level, the
                  DAILY low: look-ahead on the cancel minute) is skipped as cancelled; the first `free` names REST; a
                  resting name is a BUY only if high(E) > level. free = 5 - positions still held; a buy is held H
                  sessions (H = 0: all 5 free every morning, the upper bound; H = 5: a flat 5-session hold — the real
                  exit is not replayed). One open position per ticker.
  B "top-5 fires" the day's fires, the best 5 by order score (what the slots WOULD hold if only breakers took them — the
                  11-02 behaviour, when the pace gate kept a buy from resting before the break; all 5 free daily).
The 11-02 column ranks inside the 11-02 list and uses its fire (high > the 5-day high AND 1.2 x the 10-day volume).

QULLAMAGGIE: HELD / BOUGHT within +-5 sessions as in 01_precision.py (covered days only); and how many of his
scorecard buys (tests/fixtures/qm_breakout_scorecard: dated = on E; widened = any session of lo..hi) a model takes.

    python3 scripts/probes/_717_precision_1112/02_picks.py build
    python3 scripts/probes/_717_precision_1112/02_picks.py report > scripts/probes/_717_precision_1112/02_picks.out
"""
import argparse, importlib.util, os, sys, time
from datetime import date
from multiprocessing import get_context

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("p01", os.path.join(HERE, "01_precision.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
bv, cb, R, runner, G = P.bv, P.cb, P.R, P.runner, P.G
CAPTURE = "/Users/alvinfung/apollo_data/bv1_precision_1112/list_eraA.parquet"    # captured ONCE, outside git
CAL = P.CAPTURE + ".cal.txt"
FX = os.path.join(P.REPO, "tests/fixtures/qm_breakout_scorecard")
WIN, SLOTS = P.WIN, P.SLOTS
COLS = ["ci", "ticker", "rs_best", "old_ok", "has_e", "new_fire", "old_fire", "level", "level5", "adr20", "close", "hE", "lE", "oE",
        "prior_move", "depth_adr", "vs_ema21_adr", "dollar_vol20", "runup6m_adr", "spread10_adr"]


def work(chunk):
    S, facts, rows_at = G["S"], G["facts"], G["rows_at"]
    D = S.D
    cache, rows = {}, []
    for ci in chunk:
        members, _ = R.night_members(S, facts, ci, rows_at)
        rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                     [m["r126"] for m in members], [None] * len(members))
        for m, rb in zip(members, rs_best):
            if rb is None or rb < bv.RS_MIN or not m["listable"] or not m["history"]:
                continue
            k = m["k"]
            if k not in cache:
                cache[k] = runner.bars_for(D, k)
            bars, cidx = cache[k]
            Di = m["i"] - facts[k]["a"]
            g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            if not g["ok"]:
                continue                                   # the 11-02 list is a subset of the 11-11 list (01 `check`)
            old_ok = P.old_ok_from(g)
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1
            hE, lE, oE, vE = ((float(x[Di + 1]) for x in (bars.h, bars.l, bars.o, bars.v)) if has_e else (np.nan,) * 4)
            oi = bv.order_inputs(bars, Di, g["adr20"])     # the live order-score inputs
            gg = g["gates"]
            rows.append((ci, m["ticker"], float(rb), old_ok, has_e,
                         bool(has_e and bv.breakout_triggered({"h": hE, "v": vE}, g)["fired"]),
                         bool(old_ok and has_e and hE > g["level5"] and vE >= bv.VOL_X * g["vol10"]),
                         g["level"], g["level5"], g["adr20"], g["close"], hE, lE, oE,
                         g["prior_move"], gg["base_depth"]["value"]["depth_adr"], gg["ema21"]["value"]["vs_ema21_adr"],
                         gg["universe"]["value"]["dollar_vol20"], oi["runup6m_adr"], oi["spread10_adr"]))
    return rows


def stage_build(a):
    assert not os.path.exists(CAPTURE), "captured once — delete by hand to rebuild"
    S, nights = P.setup()
    t = time.time()
    chunks = [nights[i::a.workers * 4] for i in range(a.workers * 4)]
    with get_context("fork").Pool(a.workers) as pool:
        parts = pool.map(work, chunks)
    df = pd.DataFrame([r for p in parts for r in p], columns=COLS).sort_values(["ci", "ticker"])
    df.to_parquet(CAPTURE, index=False)
    print(f"build: {len(nights)} nights, {len(df)} list rows in {time.time() - t:.0f}s -> {CAPTURE}")


# ───────────────────────────────────────────────── report ─────────────────────────────────────────────────
def order_score(d):
    """`rank_rows` in pandas: pct rank (average ties) of the run (bigger first) and the spread (tighter first)."""
    pr = d.groupby("ci").runup6m_adr.rank(pct=True, ascending=True)
    pt = d.groupby("ci").spread10_adr.rank(pct=True, ascending=False)
    return (pr + pt) / 2


def top_k(d, score, k=SLOTS, ascending=False):
    """The best k rows a day by `score` (ties by ticker; a missing score ranks last)."""
    x = d.assign(_s=score).sort_values(["ci", "_s", "ticker"], ascending=[True, ascending, True], na_position="last")
    return x[x.groupby("ci").cumcount() < k].drop(columns="_s")


def live_like(d, score, fire_col, hold):
    """Model A. -> (the BUYS, the count of RESTING seats)."""
    x = d.assign(_s=score).sort_values(["ci", "_s", "ticker"], ascending=[True, False, True], na_position="last")
    wide = ((x.level - x.lE) > x.adr20 * x.level).to_numpy()
    ci, tk, fire, has = x.ci.to_numpy(), x.ticker.to_numpy(), x[fire_col].to_numpy(), x.has_e.to_numpy()
    bounds = np.flatnonzero(np.r_[True, ci[1:] != ci[:-1], True])
    openp, keep, seats = {}, [], 0                       # ticker -> the last calendar index it is held through
    for a0, a1 in zip(bounds[:-1], bounds[1:]):
        e = ci[a0] + 1
        openp = {t: u for t, u in openp.items() if u >= e}
        free = SLOTS - len(openp)
        for i in range(a0, a1):
            if free <= 0:
                break
            if not has[i] or wide[i] or tk[i] in openp:
                continue
            free -= 1; seats += 1
            if fire[i]:
                keep.append(i)
                if hold:
                    openp[tk[i]] = e + hold
    return x.iloc[keep].drop(columns="_s"), seats


def stage_report(a):
    df = pd.read_parquet(CAPTURE)
    cal = [date.fromisoformat(s) for s in open(CAL).read().split()]
    nights = sorted(df.ci.unique()); nN = len(nights)
    df["E"] = [cal[c + 1].isoformat() for c in df.ci]
    df["dist_adr"] = (df.level / df.close - 1) / df.adr20
    df["score_new"] = order_score(df)
    old = df[df.old_ok].copy(); old["score_old"] = order_score(old)
    df["score_old"] = old.score_old
    print(f"#717 picks — ERA A ONLY, {nN} watch nights {cal[nights[0]]} .. {cal[nights[-1]]}; 11-11 list rows {len(df):,} "
          f"({len(df) / nN:.0f} a night), 11-02 {len(old):,}; fires a day: 11-11 {df.new_fire.sum() / nN:.0f}, 11-02 {df.old_fire.sum() / nN:.0f} (means)")
    print("NOT MEASURED: 2022-04 .. 2024 (its bar store holds 2025-26 rows; not opened). No minute bars: see the docstring's two models.")
    print(f"rows with no order score (ranked last): {int(df.score_new.isna().sum())}")

    # ── Qullamaggie: the panel (as 01) and the scorecard buys
    e = pd.read_csv(f"{P.HOLD}/entries.tsv", sep="\t", dtype=str, keep_default_na=False)
    snaps = pd.read_csv(f"{P.HOLD}/snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
    snap_ci = np.array(sorted({np.searchsorted(cal, date.fromisoformat(x)) for x in snaps.date if x and date.fromisoformat(x) <= cal[-1]}))
    def ci_at(s, side):
        d = date.fromisoformat(s); i = int(np.searchsorted(cal, d, "left"))
        return i if (i < len(cal) and cal[i] == d) or side == "lo" else i - 1
    held, bought = {}, {}
    for r in e.itertuples():
        t = r.sym_a or r.sym
        start, end = r.E or r.lo or r.first_date, r.exit_hi or r.first_date
        if not start or date.fromisoformat(start) > cal[-1]:
            continue
        a0 = ci_at(min(start, r.lo or start), "lo")
        a1 = len(cal) - 1 if (r.still_held == "True" or date.fromisoformat(end) > cal[-1]) else ci_at(end, "hi")
        held.setdefault(t, []).append((a0 - WIN, a1 + WIN))
        if r.initial == "True":
            continue
        if r.E:
            b0 = b1 = ci_at(r.E, "lo")
        elif r.lo and r.hi and int(r.window_len or 99) <= 10:
            b0, b1 = ci_at(r.lo, "lo"), ci_at(r.hi, "hi")
        else:
            continue
        bought.setdefault(t, []).append((b0 - WIN, b1 + WIN))
    hit = lambda tab, t, c: any(x0 <= c <= x1 for x0, x1 in tab.get(t, ()))
    eci = df.ci.to_numpy() + 1
    df["held"] = [hit(held, t, c) for t, c in zip(df.ticker, eci)]
    df["bought"] = [hit(bought, t, c) for t, c in zip(df.ticker, eci)]
    pos = np.searchsorted(snap_ci, eci)
    df["covered"] = np.minimum(np.abs(snap_ci[np.clip(pos, 0, len(snap_ci) - 1)] - eci), np.abs(snap_ci[np.clip(pos - 1, 0, len(snap_ci) - 1)] - eci)) <= WIN
    # the scorecard: buy id -> (ticker, first E, last E), era A
    buys = []
    b = pd.read_csv(f"{FX}/buys.tsv", sep="\t", dtype=str, keep_default_na=False)
    buys += [("d" + r.eid, r.ticker, r.E, r.E, r.big_winner == "1") for r in b.itertuples()]
    w = pd.read_csv(f"{FX}/buys_undated_widened.tsv", sep="\t", dtype=str, keep_default_na=False)
    buys += [("w" + r.eid, r.ticker, r.lo, r.hi, False) for r in w.itertuples()]
    last_e = cal[nights[-1] + 1].isoformat()
    buys = [x for x in buys if x[3] <= last_e]
    by_t = {}
    for bid, t, lo, hi, big in buys:
        by_t.setdefault(t, []).append((bid, lo, hi))
    big_ids = {x[0] for x in buys if x[4]}
    def qm_ids(t, E):
        return [bid for bid, lo, hi in by_t.get(t, ()) if lo <= E <= hi]
    df["qm"] = [qm_ids(t, E) for t, E in zip(df.ticker, df.E)]
    df["is_qm"] = df.qm.map(bool)
    def taken(x):
        s = {i for l in x.qm for i in l}
        return len(s), len(s & big_ids)
    nl, _ = taken(df); nf, bf = taken(df[df.new_fire]); of, ob = taken(df[df.old_fire])
    print(f"\nQullamaggie's scorecard buys inside era A: {len(buys)} of 757 ({len(big_ids)} big winners); on the 11-11 list {nl}; "
          f"FIRED under 11-11: {nf} ({bf} big) — the era-A part of the 465; fired under 11-02: {of} ({ob} big)")
    old = df[df.old_ok]

    def line(name, x, seats=None):
        c = x[x.covered]; n, nb = taken(x)
        s = f"  {name:52s} buys/day {len(x) / nN:5.2f}  n={len(x):>6,d} | held {c.held.mean():6.2%}  bought {c.bought.mean():6.2%} (n={len(c):,}) | Qullamaggie buys taken {n:>3d} ({nb} big)"
        if seats is not None:
            s += f" | resting seats/day {seats / nN:.2f}, {len(x) / max(1, seats):.0%} of them broke out"
        print(s)

    print("\n== 1+2. THE PICKS (order score; held / bought on covered days; buys taken = distinct scorecard buys) ==")
    print("reference — ALL fires:")
    line("11-02 all fires", old[old.old_fire]); line("11-11 all fires", df[df.new_fire])
    print("Model A, live-like (the top of the LIST rests in the slots from 09:35; a buy only if it breaks):")
    for h in (0, 5):
        x, s = live_like(old, old.score_old, "old_fire", h); line(f"11-02 list, hold {h} sessions", x, s)
        x, s = live_like(df, df.score_new, "new_fire", h); line(f"11-11 list, hold {h} sessions", x, s)
    print("Model B, the day's top 5 FIRES by order score (all 5 slots free daily):")
    fo, fn = old[old.old_fire], df[df.new_fire]
    line("11-02 fires, top 5 by order score", top_k(fo, fo.score_old)); line("11-11 fires, top 5 by order score", top_k(fn, fn.score_new))
    rng = np.random.default_rng(717)
    line("11-11 fires, 5 at RANDOM (seed 717)", top_k(fn, pd.Series(rng.random(len(fn)), index=fn.index)))
    line("11-02 fires, 5 at RANDOM (seed 717)", top_k(fo, pd.Series(rng.random(len(fo)), index=fo.index)))

    print("\n== 3. ONE FEATURE AT A TIME: re-rank the day's 11-11 FIRES, take the top 5 (descriptive; no tuning, no combination) ==")
    print(f"  {'feature (direction)':44s} {'QM buys taken':>14s} {'big':>4s} | {'bought +-5':>10s} {'held +-5':>9s} | {'A: list top-5 rests (hold 0): buys/day, QM buys taken':>55s}")
    feats = [("order score (live)", "score_new"), ("strength rank", "rs_best"), ("6-month run in daily ranges", "runup6m_adr"),
             ("10-close spread in daily ranges", "spread10_adr"), ("prior move", "prior_move"), ("daily range (ADR20)", "adr20"),
             ("base depth in daily ranges", "depth_adr"), ("distance to the level in daily ranges", "dist_adr"),
             ("dollar volume (20-day median)", "dollar_vol20"), ("close vs 21-day EMA in daily ranges", "vs_ema21_adr")]
    out = []
    for name, col in feats:
        for asc, lab in ((False, "high first"), (True, "low first")):
            if col == "score_new" and asc:
                continue
            x = top_k(fn, fn[col], ascending=asc); c = x[x.covered]; n, nb = taken(x)
            xa, _ = live_like(df, df[col] if not asc else -df[col], "new_fire", 0); na, _b = taken(xa)
            out.append((n, f"  {name + ' (' + lab + ')':44s} {n:>14d} {nb:>4d} | {c.bought.mean():>10.2%} {c.held.mean():>9.2%} | {len(xa) / nN:>24.2f} buys/day, {na:>3d} taken"))
    for _, s in sorted(out, key=lambda z: -z[0]):
        print(s)
    cap = df[df.new_fire & df.is_qm].groupby("ci").size().clip(upper=SLOTS)
    print(f"  ceiling: {nf} Qullamaggie buys fire under 11-11; the most on one day is {int(df[df.new_fire & df.is_qm].groupby('ci').size().max())}, so 5 slots a day could hold nearly all of them ({int(cap.sum())} of {int(df[df.new_fire & df.is_qm].groupby('ci').size().sum())} name-days)")
    print("  note: a widened buy counts when the pick lands on ANY session of its window (same reading as the head to head).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("build", "report"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    {"build": stage_build, "report": stage_report}[a.stage](a)
