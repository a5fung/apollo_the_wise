#!/usr/bin/env python3
"""exit_tune_cohort_review — run 1 at n=22 closed live trades (2026-08-22).

THE LINE: read-only, offline replay. Evidence + recommendation only. No exit rule,
stop width, profit-take level or sizing is changed here — operator sole authority.

Reuses the tested _508_exit_rule_replay.py engine UNCHANGED (fill model, breakeven
scan, ambiguity handling, 34-candidate grid), pointed at a FRESH prod snapshot
pulled 2026-08-22 (read-only COPY TO STDOUT). Regime is ENTRY-STAMPED
(mi_live_trades.regime joined on trade_id) per the #508 2026-08-08 rule.

ERA SEGMENTATION (the exit stack changed under this cohort — never average across):
  A  fills <= 2026-08-04: ORB-low stop, +2R partial DEPLOYED 08-01 but structurally
     unable to execute on MAGNA53 OTO brackets until the leg-safe path (18ce574f,
     shipped 08-04 17:02 ET -> live 08-05).  PLTR filled 08-04 but LIVED into era B
     (partial fired + trail) — flagged as the era-spanner, reported both ways.
  B  fills 2026-08-05..08-14: ORB-low stop + executable +2R partial (1/3, BE after).
  C  fills >= 2026-08-17: entry−2R stop at half size, +2R target PINNED to the
     ORB-based price (operator-signed, live 2026-08-16 evening).

Run:  python3 scripts/probes/_508d_exit_tune_cohort_n22_2026-08-22.py
"""
from __future__ import annotations

import importlib.util
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT_DIR = Path(
    "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
    "6b173ac9-86a7-4492-b734-12cc49146c1b/scratchpad"
)

spec = importlib.util.spec_from_file_location("replay508", HERE / "_508_exit_rule_replay.py")
replay = importlib.util.module_from_spec(spec)
sys.modules["replay508"] = replay
spec.loader.exec_module(replay)
replay.HERE = SNAPSHOT_DIR  # redirect the 4 TSV reads to the fresh 08-22 snapshot

ERA_B_START = date(2026, 8, 5)
ERA_C_START = date(2026, 8, 17)


def era_of(t):
    fd = t.rec["fill_day"]
    if fd >= ERA_C_START:
        return "C"
    if fd >= ERA_B_START:
        return "B"
    return "A"


def fmt(v, w=7, d=2):
    return replay.fmt(v, w, d)


def pctile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def block(label, sub, show_vals=True):
    n = len(sub)
    if n == 0:
        print(f"  {label:<26} n=0  — SAID, NOT SMOOTHED")
        return
    rr = [t.rec["realized_r"] for t in sub]
    wins = sum(1 for r in rr if r > 0)
    peaks = [t.rec["peak_r"] for t in sub if t.rec["peak_r"] is not None]
    padr = [t.rec["peak_adr"] for t in sub if t.rec["peak_adr"] is not None]
    sadr = [t.rec["stop_per_adr"] for t in sub if t.rec["stop_per_adr"] is not None]
    hold = [t.rec["hold_trading_days"] for t in sub if t.rec["hold_trading_days"] is not None]
    d0 = sum(1 for t in sub if t.rec["fill_day"] == t.rec["close_day"])
    print(f"  {label:<26} n={n:<3} sumR {fmt(sum(rr))}  meanR {fmt(sum(rr)/n)}  wins {wins}/{n}  "
          f"day0-exit {d0}/{n}")
    if peaks:
        print(f"  {'':<26} peakR mean {fmt(sum(peaks)/len(peaks))} max {fmt(max(peaks))}  "
              f">=2R {sum(1 for p in peaks if p >= 2)}/{len(peaks)}  "
              f"peakADR med {fmt(statistics.median(padr) if padr else None)}  "
              f"stop/ADR med {fmt(statistics.median(sadr) if sadr else None)}  "
              f"hold med {statistics.median(hold) if hold else '—'}d")
    if show_vals:
        vals = " ".join(f"{t.rec['ticker']}{t.rec['realized_r']:+.2f}" for t in sub)
        print(f"  {'':<26} {vals}")


def main():
    trades = replay.load()
    cands = replay.candidates()

    mag = [t for t in trades if t.rec["signal_type"] == "magna53"]
    live = sorted([t for t in mag if t.rec["account_mode"] == "live"],
                  key=lambda t: t.rec["fill_day"])
    paper = [t for t in mag if t.rec["account_mode"] == "paper"]

    print("=" * 100)
    print("exit_tune_cohort_review run 1 — n=22 closed live magna53, snapshot 2026-08-22")
    print("=" * 100)
    print(f"\nsnapshot rows total {len(trades)}  live/magna53 {len(live)}  "
          f"paper/magna53 {len(paper)}  other {len(trades)-len(live)-len(paper)}")

    # ── era segmentation ────────────────────────────────────────────────────
    print("\n--- (era) EXIT-STACK ERAS — n per era, never averaged across -------------")
    eras = {"A": [], "B": [], "C": []}
    for t in live:
        eras[era_of(t)].append(t)
    block("A  ORB-low stop, no partial", eras["A"])
    block("B  ORB-low stop + 2R partial", eras["B"])
    block("C  2R stop half size", eras["C"])
    print("  ⚠ PLTR filled 08-04 (era A) but lived 12 sessions into era B: its partial FIRED"
          " and its stop TRAILED under era-B mechanics. Era A excl. PLTR:")
    block("A' era A excl PLTR", [t for t in eras["A"] if t.rec["ticker"] != "PLTR"])

    # ── holding-period distribution (method d) ──────────────────────────────
    print("\n--- (d) HOLDING PERIOD, live --------------------------------------------")
    hc = Counter(t.rec["hold_trading_days"] for t in live)
    print("  hold_trading_days:", " ".join(f"{k}d×{v}" for k, v in sorted(hc.items())))
    print(f"  closed on entry day: {sum(1 for t in live if t.rec['fill_day']==t.rec['close_day'])}/22"
          f"   max hold {max(hc)}d   nothing has reached 20 sessions")

    # ── regime cells, live only (method c0) ─────────────────────────────────
    print("\n--- (c0) REGIME, LIVE-ONLY, ENTRY-STAMPED — with the NEW confound said ---")
    for rg in ("Bull", "Choppy", "Correcting", "Crisis"):
        sub = [t for t in live if t.rec["regime"] == rg]
        block(rg, sub)
        if sub:
            ec = Counter(era_of(t) for t in sub)
            print(f"  {'':<26} eras: {dict(sorted(ec.items()))}")
    print("\n  ⚠ REGIME IS NOW CONFOUNDED WITH ERA inside the live cohort: every live-Bull")
    print("    trade is era B/C (post-partial / post-2R-stop) and every non-Bull trade is")
    print("    era A (no partial; PLTR the spanner). A realized-R regime comparison is a")
    print("    comparison of exit stacks as much as of tapes. Peak-based columns are less")
    print("    era-sensitive but BE-scratches truncate holds, so even peaks are not clean.")

    # ── character (ADR20) segmentation (method c) ───────────────────────────
    print("\n--- (c) CHARACTER — ADR20 tiers (ADR20% = stop_pct / stop_per_adr) -------")
    for lo, hi, lab in ((0, 3.5, "slow  <3.5%"), (3.5, 6.5, "mid 3.5-6.5%"), (6.5, 99, "fast  >6.5%")):
        sub = [t for t in live
               if t.rec["stop_per_adr"] and (t.rec["stop_pct"] / t.rec["stop_per_adr"]) >= lo
               and (t.rec["stop_pct"] / t.rec["stop_per_adr"]) < hi]
        block(lab, sub)

    # ── stop geometry (method e) ────────────────────────────────────────────
    print("\n--- (e) STOP GEOMETRY — width vs the stock's own daily range -------------")
    old = [t for t in live if era_of(t) != "C"]
    sw = sorted((t.rec["stop_per_adr"], t.rec["ticker"]) for t in old if t.rec["stop_per_adr"])
    v = [x[0] for x in sw]
    print(f"  ORB-low-stop trades (eras A+B, n={len(v)}): stop width / ADR20")
    print(f"    min {v[0]:.2f}  P25 {pctile(v,0.25):.2f}  median {statistics.median(v):.2f}  "
          f"P75 {pctile(v,0.75):.2f}  max {v[-1]:.2f}   (<1.0 ADR: {sum(1 for x in v if x<1)}/{len(v)})")
    for t in eras["C"]:
        print(f"  era-C 2R-stop trade: {t.rec['ticker']} stop/ADR {t.rec['stop_per_adr']:.2f} "
              f"(ORB-low width would have been ~{t.rec['stop_per_adr']/2:.2f})")
    runners = [(t.rec["ticker"], t.rec["peak_adr"]) for t in live
               if t.rec["peak_adr"] and t.rec["peak_adr"] >= 1.0]
    print(f"  trades whose peak ran >= 1.0 ADR: "
          + " ".join(f"{tk} {p:.2f}" for tk, p in sorted(runners, key=lambda x: -x[1])))

    # ── the runner laboratory: every trade that reached >= +2R ──────────────
    print("\n--- RUNNERS >= +2R — what each era's stack kept of them ------------------")
    print(f"  {'tkr':<6}{'era':<4}{'peakR':>7}{'keptR':>8}{'capture':>9}   note")
    for t in sorted(live, key=lambda t: -(t.rec["peak_r"] or 0)):
        if (t.rec["peak_r"] or 0) >= 2.0:
            r = t.rec
            cap = f"{r['realized_r']/r['peak_r']*100:+.0f}%" if r["peak_r"] else "—"
            note = {"PLTR": "era-A entry, era-B management: partial fired, stop trailed",
                    "ETON": "partial fired same day, BE held -> banked",
                    "FIGS": "partial fired, remainder lost more than the bank",
                    }.get(r["ticker"], "no partial existed — gave it all back")
            print(f"  {r['ticker']:<6}{era_of(t):<4}{r['peak_r']:>7.2f}{r['realized_r']:>8.2f}"
                  f"{cap:>9}   {note}")

    # ── candidate grid (methods b + c0), era A only and full, live ──────────
    results = {}
    for name, fn in cands.items():
        if name == "actual":
            results[name] = {t.rec["trade_id"]: replay.Result(t.rec["realized_r"],
                                                              t.rec["realized_r"])
                             for t in trades}
        else:
            results[name] = {t.rec["trade_id"]: r for t in trades if (r := fn(t)) is not None}

    def grid(sub, label):
        print(f"\n--- (b) CANDIDATE GRID, {label} (mean kept R per trade; engine unchanged) ---")
        rows = []
        for name in cands:
            vals = [results[name][t.rec["trade_id"]].kept_r
                    for t in sub if t.rec["trade_id"] in results[name]]
            if vals:
                rows.append((sum(vals) / len(vals), name, len(vals)))
        for mean, name, n in sorted(rows, reverse=True):
            print(f"  {name:<32}{mean:+7.2f}  (n={n})")

    grid(eras["A"], f"ERA A ONLY n={len(eras['A'])} — the only era where candidates cleanly "
                    f"REPLACE the deployed rule")
    print("\n  ⚠ era-B/C trades already ran WITH a live partial/BE — a candidate replay on top"
          "\n    of them replaces a rule that already acted, so the full-cohort grid mixes eras;"
          "\n    shown for continuity with the 07-30/08-17 runs, read era A for the clean read.")
    grid(live, "FULL LIVE COHORT n=22 (era-mixed — continuity only)")

    # ── regime-conditional arms, live cells ─────────────────────────────────
    print("\n--- (c0) REGIME-CONDITIONAL ARMS (rgm_*), LIVE cells — era caveat applies ---")
    cells = {rg: [t for t in live if t.rec["regime"] == rg] for rg in ("Bull", "Choppy", "Correcting")}
    for name in cands:
        if not name.startswith("rgm_"):
            continue
        row = f"  {name:<28}"
        for rg, sub in cells.items():
            vals = [results[name][t.rec["trade_id"]].kept_r
                    for t in sub if t.rec["trade_id"] in results[name]]
            row += f"  {rg[:4]}={sum(vals)/len(vals):+.2f}(n{len(vals)})" if vals else f"  {rg[:4]}=n/a"
        print(row)

    # ── paper cells for reference, never blended ────────────────────────────
    print("\n--- PAPER magna53 (separate, NEVER blended: old entry mechanics + regime confound) ---")
    rr = [t.rec["realized_r"] for t in paper]
    print(f"  n={len(paper)}  sumR {fmt(sum(rr))}  wins {sum(1 for r in rr if r>0)}/{len(paper)}")

    print("\nDone. THE LINE: nothing above changes any rule.")


if __name__ == "__main__":
    main()
