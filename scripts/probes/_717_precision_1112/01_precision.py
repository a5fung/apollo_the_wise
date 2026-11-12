#!/usr/bin/env python3
"""#717 PRECISION of the breakout v1 list, the 2026-11-02 rules against the wired 2026-11-11 rules, over every watch
night of the frozen whole-universe replay's ERA A (2026-11-12; offline, $0, read-only; nothing here changes a rule).

WHAT IT MEASURES (per watch night D, E = the next session):
  * names on the list (every gate in GATES passes; the pool + strength rank exactly as `10_feature_table.py` /
    `v1_replay.night_members` build them — the frozen replay's population);
  * names that FIRE on E — the daily-bar proxy of the buy, not the live intraday entry:
        11-11 wired : high(E) > level (the lower of the range high and the 5-day level after the wick rule); no volume
        11-02       : high(E) > the 5-day high AND volume(E) >= 1.2 x the 10-session mean (its trigger then);
                      also printed WITHOUT the volume bar (the brief's plain proxy);
  * the share of fires that are names Qullamaggie HELD within +-5 sessions of E (his positions panel,
    `holdings_1024/entries.tsv`), and the tighter share he BOUGHT within +-5 sessions; with the base rate over the whole
    rank >= 35 pool and over listed-not-fired names;
  * fires per day against the paper account's 5 slots.

THE 11-02 RULES are derived post hoc from ONE `v1_gates` call at the live settings: every 11-02 threshold is tighter
(prior move 0.3213, base depth <= 8.98, EMA21 >= -0.6335, the 50-day gate) and every value is in the call's output; the
`check` stage asserts this equals `13_head_to_head.py`'s monkeypatched OLD spec row by row on sampled nights.

THE SEAL: ERA A ONLY. Bars = `cb702_pre_v2/daily_closes_all.csv.gz` (2016-01-04 .. 2022-06-30; asserted < 2025).
`cb702/daily_closes_all.csv.gz` runs to 2026-10-16 (it HOLDS 2025-26 rows) and no sealed copy exists -> NOT OPENED, so
watch nights 2022-04-01 .. 2024-12-30 are NOT measured here.

Stages:  check [--nights N] | build [--workers W] | report
    python3 scripts/probes/_717_precision_1112/01_precision.py report > scripts/probes/_717_precision_1112/01_precision.out
"""
import argparse, hashlib, os, subprocess, sys, time
from collections import Counter
from datetime import date
from multiprocessing import get_context

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCR = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/prec1112"
os.environ["BV1_SCRATCH"] = SCR
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_breakout_v1_replay_1101")); sys.path.insert(0, REPO)
import v1_replay as R  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv  # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from scripts.probes._cb_backtest import runner  # noqa: E402

CAPTURE = "/Users/alvinfung/apollo_data/bv1_precision_1112/pool_eraA.parquet"   # captured ONCE, outside git
HOLD = "/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024"
OLD = dict(PRIOR_MOVE_MIN=0.3213536987121892, BASE_DEPTH_ADR_MAX=8.979719460898997, EMA21_ADR_MIN=-0.6335)
OLD_GATES = ("history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21", "sma50")
WIN = 5            # +-5 sessions
SLOTS = 5
G = {}


def nights_of(cal):
    d_lo = max(R.E_FIRST - pd.Timedelta(days=10).to_pytimedelta(), cal[0])
    return [ci for ci, d in enumerate(cal) if d_lo <= d <= R.ERA_A_D_LAST and ci + 1 < len(cal) and R.E_FIRST <= cal[ci + 1] <= R.E_LAST]


def old_ok_from(g):
    gg = g["gates"]
    if not all(gg[k]["pass"] for k in ("history", "universe", "pinned", "adr", "rs")):
        return False
    pm, dp, v21 = gg["prior_move"]["value"]["prior_move"], gg["base_depth"]["value"]["depth_adr"], gg["ema21"]["value"]["vs_ema21_adr"]
    return bool(pm is not None and pm >= OLD["PRIOR_MOVE_MIN"] and dp is not None and bv.BASE_DEPTH_ADR_MIN <= dp <= OLD["BASE_DEPTH_ADR_MAX"]
                and v21 is not None and v21 >= OLD["EMA21_ADR_MIN"] and g["sma50"]["pass"])


def work(chunk):
    S, facts, rows_at, check = G["S"], G["facts"], G["rows_at"], G.get("check", False)
    D = S.D; cal = D.cal
    cache, rows, bad = {}, [], 0
    for ci in chunk:
        members, _ = R.night_members(S, facts, ci, rows_at)
        rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                     [m["r126"] for m in members], [None] * len(members))
        for m, rb in zip(members, rs_best):
            if rb is None or rb < bv.RS_MIN or not m["listable"] or not m["history"]:
                continue                                   # fails rs / history / the fund rule under BOTH rule sets
            k = m["k"]
            if k not in cache:
                cache[k] = runner.bars_for(D, k)
            bars, cidx = cache[k]
            Di = m["i"] - facts[k]["a"]
            g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            new_ok, old_ok = bool(g["ok"]), old_ok_from(g)
            if check:                                      # the monkeypatched OLD spec of 13_head_to_head.py
                keep = {kk: getattr(bv, kk) for kk in (*OLD, "GATES")}
                for kk, vv in OLD.items():
                    setattr(bv, kk, vv)
                bv.GATES = OLD_GATES
                try:
                    g0 = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
                finally:
                    for kk, vv in keep.items():
                        setattr(bv, kk, vv)
                bad += int(bool(g0["ok"]) != old_ok or (g0["ok"] and (g0["level5"] != g["level5"] or g0["vol10"] != g["vol10"])))
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1     # the name's next bar IS the next session
            hE = float(bars.h[Di + 1]) if has_e else np.nan
            vE = float(bars.v[Di + 1]) if has_e else np.nan
            lvl, l5, v10 = g.get("level"), g.get("level5"), g.get("vol10")
            rows.append((ci, m["ticker"], float(rb), new_ok, old_ok, has_e,
                         bool(new_ok and has_e and bv.breakout_triggered({"h": hE, "v": vE}, g)["fired"]),
                         bool(old_ok and has_e and hE > l5 and vE >= bv.VOL_X * v10),
                         bool(old_ok and has_e and hE > l5),
                         g.get("level_source") or "", m["is_etv"]))
    return rows, bad


def setup():
    S = R.load_store("A"); D = S.D
    assert D.cal[-1] < R.SEAL, D.cal[-1]
    facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
    row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
    order = np.argsort(D.ci, kind="stable")
    G.update(S=S, facts=facts, rows_at=R._RowsAt(order, D.ci[order], row_tid))
    return S, nights_of(D.cal)


COLS = ["ci", "ticker", "rs_best", "new_ok", "old_ok", "has_e", "new_fire", "old_fire", "old_fire_novol", "level_source", "is_etv"]


def run(nights, workers):
    chunks = [nights[i::workers * 4] for i in range(workers * 4)]
    with get_context("fork").Pool(workers) as pool:
        parts = pool.map(work, chunks)
    rows = [r for p, _ in parts for r in p]
    return pd.DataFrame(rows, columns=COLS), sum(b for _, b in parts)


def stage_check(a):
    S, nights = setup(); G["check"] = True
    sub = nights[::max(1, len(nights) // a.nights)][:a.nights]
    t = time.time(); df, bad = run(sub, a.workers)
    print(f"check: {len(sub)} nights, {len(df)} rows, {time.time() - t:.0f}s; derived 11-02 != monkeypatched 11-02 on {bad} rows; "
          f"new listed/night {df.new_ok.sum() / len(sub):.0f}, old {df.old_ok.sum() / len(sub):.0f}")
    assert bad == 0


def stage_build(a):
    assert not os.path.exists(CAPTURE), "captured once — delete by hand to rebuild"
    S, nights = setup()
    t = time.time(); df, _ = run(nights, a.workers)
    cal = S.D.cal
    df["D"] = [cal[c].isoformat() for c in df.ci]; df["E"] = [cal[c + 1].isoformat() for c in df.ci]
    os.makedirs(os.path.dirname(CAPTURE), exist_ok=True)
    df.sort_values(["ci", "ticker"]).to_parquet(CAPTURE, index=False)
    pd.Series([d.isoformat() for d in cal]).to_csv(CAPTURE + ".cal.txt", index=False, header=False)
    print(f"build: {len(nights)} nights, {len(df)} rows in {time.time() - t:.0f}s -> {CAPTURE}")


# ─────────────────────────────────────────── report (post-processing only) ───────────────────────────────────────────
def q(s, p):
    return float(np.percentile(s, p)) if len(s) else float("nan")


def stage_report(a):
    df = pd.read_parquet(CAPTURE)
    cal = [date.fromisoformat(x) for x in open(CAPTURE + ".cal.txt").read().split()]
    ci_of = {d: i for i, d in enumerate(cal)}
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(open(os.path.join(REPO, "agents/market_intelligence/breakout_v1.py"), "rb").read()).hexdigest()[:16]
    nights = sorted(df.ci.unique())
    print(f"#717 precision — HEAD {head}, breakout_v1.py sha256 {sha}; GATES {bv.GATES}")
    print(f"ERA A ONLY: {len(nights)} watch nights {cal[nights[0]]} .. {cal[nights[-1]]} (breakout days to {cal[nights[-1] + 1]}); "
          f"{len(df):,} pool rows (rank >= {bv.RS_MIN:.0f}, listable, 86 sessions), {len(df) / len(nights):.0f} a night")
    print("NOT MEASURED: watch nights 2022-04-01 .. 2024-12-30 — their bar store (cb702/daily_closes_all.csv.gz) holds 2025-26 rows; not opened.")
    print(f"names with no bar on the next session (cannot fire): new-listed {int((df.new_ok & ~df.has_e).sum())}, old-listed {int((df.old_ok & ~df.has_e).sum())}")
    df["year"] = [cal[c + 1].year for c in df.ci]
    per = df.groupby("ci").agg(new_l=("new_ok", "sum"), old_l=("old_ok", "sum"), new_f=("new_fire", "sum"), old_f=("old_fire", "sum"),
                               old_fn=("old_fire_novol", "sum"), year=("year", "first")).reindex(nights).fillna(0)

    print("\n== 1. PER NIGHT: names listed, and names that fire the next session (daily proxy) ==")
    print("anchor (SSoT, stage 0, 11-02 rules, 2017-24): 'a median 249 names a night, ~25 breakouts a day'")
    hdr = f"{'':10s}{'nights':>7s} | {'11-02 listed':>14s} {'fired(1.2x vol)':>17s} {'fired(no vol)':>15s} | {'11-11 listed':>14s} {'fired':>13s} | fired x"
    print(hdr); print(f"{'':10s}{'':>7s} | {'med / p90':>14s} {'med / p90':>17s} {'med / p90':>15s} | {'med / p90':>14s} {'med / p90':>13s} |")
    def row(name, p):
        f = lambda c: f"{q(p[c], 50):.0f} / {q(p[c], 90):.0f}"
        x = p.new_f.sum() / max(1, p.old_f.sum())
        print(f"{name:10s}{len(p):7d} | {f('old_l'):>14s} {f('old_f'):>17s} {f('old_fn'):>15s} | {f('new_l'):>14s} {f('new_f'):>13s} | {x:.1f}")
    row("ALL", per)
    for y, p in per.groupby("year"):
        row(str(int(y)), p)
    print(f"means a night: 11-02 listed {per.old_l.mean():.0f}, fired {per.old_f.mean():.1f} (no vol {per.old_fn.mean():.1f}); "
          f"11-11 listed {per.new_l.mean():.0f}, fired {per.new_f.mean():.1f}")
    print(f"share of the list that fires next day: 11-02 {per.old_f.sum() / per.old_l.sum():.1%} (no vol {per.old_fn.sum() / per.old_l.sum():.1%}); "
          f"11-11 {per.new_f.sum() / per.new_l.sum():.1%}")
    print(f"11-11 fires by level source: {dict(Counter(df[df.new_fire].level_source))}")
    print(f"11-11 LISTED names by level source: {dict(Counter(df[df.new_ok].level_source))} (the range high is never the lower level, as in 13_head_to_head_fixup.out)")
    print(f"11-02 fires that the 11-11 rules also fire: {int((df.old_fire & df.new_fire).sum())} of {int(df.old_fire.sum())}; "
          f"11-11 fires not fired by 11-02: {int((df.new_fire & ~df.old_fire).sum())} of {int(df.new_fire.sum())}")
    print(f"funds (single-asset ETVs) among fires: 11-02 {df[df.old_fire].is_etv.mean():.1%}, 11-11 {df[df.new_fire].is_etv.mean():.1%}")

    # ── Qullamaggie's positions panel
    e = pd.read_csv(f"{HOLD}/entries.tsv", sep="\t", dtype=str, keep_default_na=False)
    snaps = pd.read_csv(f"{HOLD}/snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
    snap_ci = np.array(sorted({np.searchsorted(cal, date.fromisoformat(x)) for x in snaps.date if x and date.fromisoformat(x) <= cal[-1]}))
    def ci_at(s, side):                        # a date -> calendar index (a non-session date snaps inward)
        d = date.fromisoformat(s)
        i = int(np.searchsorted(cal, d, "left"))
        return i if (i < len(cal) and cal[i] == d) or side == "lo" else i - 1
    held, bought, bought_bo = {}, {}, {}
    n_used = 0
    for r in e.itertuples():
        t = r.sym_a or r.sym                    # the bar-store ticker, as 20_widened_set.py joins it
        start = r.E or r.lo or r.first_date
        end = r.exit_hi or r.first_date
        if not start or date.fromisoformat(start) > cal[-1]:
            continue
        n_used += 1
        a0, a1 = ci_at(min(start, r.lo or start), "lo"), min(len(cal) - 1, ci_at(end, "hi")) if date.fromisoformat(end) <= cal[-1] else len(cal) - 1
        if r.still_held == "True":
            a1 = len(cal) - 1
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
        if r.E and r.setup in ("breakout", "both"):
            bought_bo.setdefault(t, []).append((b0 - WIN, b1 + WIN))
    def hit(tab, t, c):
        return any(a0 <= c <= a1 for a0, a1 in tab.get(t, ()))
    eci = df.ci.to_numpy() + 1
    tk = df.ticker.to_numpy()
    df["held"] = [hit(held, t, c) for t, c in zip(tk, eci)]
    df["bought"] = [hit(bought, t, c) for t, c in zip(tk, eci)]
    df["bought_bo"] = [hit(bought_bo, t, c) for t, c in zip(tk, eci)]
    pos = np.searchsorted(snap_ci, eci)
    near = np.minimum(np.abs(snap_ci[np.clip(pos, 0, len(snap_ci) - 1)] - eci), np.abs(snap_ci[np.clip(pos - 1, 0, len(snap_ci) - 1)] - eci))
    df["covered"] = near <= WIN                 # a positions snapshot within +-5 sessions of E: the panel could see it

    print(f"\n== 2. PRECISION AGAINST QULLAMAGGIE (his positions panel: {n_used} entries to {cal[-1]}, {len(snap_ci)} snapshot days) ==")
    print(f"HELD = a name in his panel at any point within +-{WIN} sessions of the fire day (includes names held for months and his EP buys);")
    print(f"BOUGHT = his entry (dated, or an entry window <= 10 sessions) within +-{WIN} sessions; BREAKOUT BUY = a dated breakout buy within +-{WIN}.")
    cov_days = df.groupby("ci").covered.first()
    print(f"fire days with a positions snapshot within +-{WIN} sessions: {int(cov_days.sum())} of {len(cov_days)} — the shares below use ONLY those days")
    c = df[df.covered]
    def prow(name, x):
        n = len(x)
        print(f"  {name:44s} n={n:>9,d}  held {x.held.sum():>6,d} = {x.held.mean():6.2%}   bought {x.bought.sum():>5,d} = {x.bought.mean():6.2%}   "
              f"breakout buy {x.bought_bo.sum():>4,d} = {x.bought_bo.mean():6.2%}")
    prow("11-02 fired (1.2x volume)", c[c.old_fire]); prow("11-02 fired (no volume bar)", c[c.old_fire_novol])
    prow("11-11 fired", c[c.new_fire]); prow("11-11 fired, NOT fired by 11-02", c[c.new_fire & ~c.old_fire])
    prow("11-02 listed, did not fire", c[c.old_ok & ~c.old_fire]); prow("11-11 listed, did not fire", c[c.new_ok & ~c.new_fire])
    prow("11-02 listed (all)", c[c.old_ok]); prow("11-11 listed (all)", c[c.new_ok])
    prow("BASE RATE: the whole rank >= 35 pool", c); prow("BASE RATE: pool, rank >= 90", c[c.rs_best >= 90])
    b = c.held.mean()
    print(f"  lift over the pool base rate (held): 11-02 fired {c[c.old_fire].held.mean() / b:.1f}x, 11-11 fired {c[c.new_fire].held.mean() / b:.1f}x, "
          f"11-11-only fires {c[c.new_fire & ~c.old_fire].held.mean() / b:.1f}x")
    print("  per year (held share of fires, covered days):")
    for y, x in c.groupby("year"):
        o, n = x[x.old_fire], x[x.new_fire]
        print(f"    {int(y)}  11-02 {o.held.sum():>4d}/{len(o):<6d} = {o.held.mean() if len(o) else float('nan'):6.2%}   "
              f"11-11 {n.held.sum():>4d}/{len(n):<6d} = {n.held.mean() if len(n) else float('nan'):6.2%}   pool {x.held.mean():6.2%}")
    # his side: names in the panel per covered day (the ceiling on any day's hits)
    hd = c[c.held].groupby("ci").ticker.nunique().reindex(sorted(c.ci.unique())).fillna(0)
    print(f"  CEILING / base-rate caveat: pool names he held (+-{WIN}) per covered day: median {q(hd, 50):.0f}, p90 {q(hd, 90):.0f} — "
          f"against {per.new_f.median():.0f} fires a day, precision vs holdings cannot exceed ~{q(hd, 50) / max(1, per.new_f.median()):.0%} on a median day")
    hb = c[c.bought]
    print(f"  his BOUGHT pool rows (name x day within +-{WIN} of an entry): {len(hb):,}; on the 11-02 list {hb.old_ok.mean():.1%}, fired {hb.old_fire.mean():.1%}; "
          f"on the 11-11 list {hb.new_ok.mean():.1%}, fired {hb.new_fire.mean():.1%} (a day-level recall view, not the 757-buy scorecard)")

    print(f"\n== 3. PAPER CAPACITY: fires a day against {SLOTS} slots ==")
    for name, col in (("11-02 (1.2x volume)", "old_f"), ("11-02 (no volume bar)", "old_fn"), ("11-11", "new_f")):
        s = per[col]
        print(f"  {name:22s} median {q(s, 50):.0f}, p10 {q(s, 10):.0f}, p90 {q(s, 90):.0f}, max {s.max():.0f}; days with more than {SLOTS} fires {np.mean(s > SLOTS):.1%}; "
              f"days with 0 fires {np.mean(s == 0):.1%}; a full 5 slots takes {SLOTS / max(1e-9, q(s, 50)):.0%} of a median day's fires")
    print("  caveat: slots are HELD for days, so fewer than 5 are free on a typical morning; and the live entry needs an intraday break")
    print("  (ORH5 / width), so real fires run under this daily-bar proxy. The paper book fills by ORDER SCORE — not replayed here.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("check", "build", "report"))
    ap.add_argument("--nights", type=int, default=12)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    {"check": stage_check, "build": stage_build, "report": stage_report}[a.stage](a)
