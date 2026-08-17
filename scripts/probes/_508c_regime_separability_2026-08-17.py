#!/usr/bin/env python3
"""exit_regime_separability review (data_gated_reviews.yaml) — run 2026-08-17.

THE LINE: read-only, offline replay. Reports evidence only. No exit rule changes,
no live/strategy code touched. Any exit change is CHANGE_PROCESS + operator
sign-off + backtest.

WHAT THIS SCRIPT DOES
  1. Re-imports the tested `_508_exit_rule_replay.py` engine UNCHANGED (fill
     model, breakeven scan, ambiguity handling, the 34-candidate grid) rather
     than reimplementing any of it.
  2. Points it at a FRESH prod snapshot (pulled 2026-08-17, read-only COPY TO
     STDOUT, same shape as the 2026-07-30 snapshot) instead of the stale
     43-row one. The live/magna53 cohort grew 12 -> 20 since 07-30.
  3. Fixes the regime field to be ENTRY-STAMPED (`mi_live_trades.regime`,
     joined on trade_id) instead of the DATE-JOINED reconstruction
     (`mi_market_regime ON regime_date = alert_date`) that the original
     TSVs and the parent script's docstring use. This is not a new idea —
     it is the rule the operator's #508 verification adopted on 2026-08-08
     after finding the two joins disagree on 5 of 17 live trades (WULF,
     TSEM, FTNT, BTDR, BLZE — a day whose regime got REVISED after entry).
     `sell_discipline.py` (agents/market_intelligence, NOT touched by this
     script) already carries that fix for the operator-facing surface; this
     review inherited the SAME question and gets the SAME fix. Verified on
     this snapshot: date-join reads live-Bull=9, entry-stamp reads
     live-Bull=6 (Correcting 7, Choppy 6, Crisis 1) — the review's own
     predicate (data_gated_reviews.yaml, date-joined) fired on the INFLATED
     number, but the entry-stamped number (6) still clears its own n>=4
     floor, so the fire was not a false trigger even though its count was
     off by 3.
  4. Adds a LIVE-ONLY Bull vs Correcting cut (the parent script's per-regime
     table pools live+paper together, which reintroduces the exact
     paper-vs-live confound this review exists to remove) with tail stats
     (P90, share reaching +1R/+2R/+3R) and ADR20-normalised distance
     alongside the R-multiple figures.

Run:  python3 scripts/probes/_508c_regime_separability_2026-08-17.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT_DIR = Path(
    "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
    "6bd49b80-0683-4b68-be72-adb54075b1c4/scratchpad"
)

spec = importlib.util.spec_from_file_location(
    "replay508", HERE / "_508_exit_rule_replay.py"
)
replay = importlib.util.module_from_spec(spec)
sys.modules["replay508"] = replay  # dataclass() needs the module registered to resolve types
spec.loader.exec_module(replay)
replay.HERE = SNAPSHOT_DIR  # redirect the 4 TSV reads to the fresh 08-17 snapshot


def fmt(v, w=7, d=2):
    return replay.fmt(v, w, d)


def pctile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def run():
    trades = replay.load()
    cands = replay.candidates()
    results = {}
    for name, fn in cands.items():
        if name == "actual":
            results[name] = {
                t.rec["trade_id"]: replay.Result(t.rec["realized_r"], t.rec["realized_r"])
                for t in trades
            }
        else:
            results[name] = {
                t.rec["trade_id"]: r
                for t in trades
                if (r := fn(t)) is not None
            }

    mag = [t for t in trades if t.rec["signal_type"] == "magna53"]
    live_mag = [t for t in mag if t.rec["account_mode"] == "live"]
    paper_mag = [t for t in mag if t.rec["account_mode"] == "paper"]

    print("=" * 100)
    print("exit_regime_separability — 2026-08-17 run, entry-stamped regime, fresh snapshot")
    print("=" * 100)

    print("\n--- SNAPSHOT HONESTY ------------------------------------------------------")
    print(f"  pulled: 2026-08-17 (prod, read-only COPY). Total sell-discipline rows: {len(trades)}")
    for co in ("live/magna53", "paper/magna53", "paper/9m_day2"):
        n = len([t for t in trades if t.cohort == co])
        print(f"  {co:<16} n={n}")

    print("\n--- REGIME-JOIN METHODOLOGY CHECK ------------------------------------------")
    from collections import Counter
    entry_regime_live = Counter(t.rec["regime"] for t in live_mag)
    print(f"  live/magna53 by ENTRY-STAMPED regime (mi_live_trades.regime, this script): "
          + " · ".join(f"{k} {v}" for k, v in entry_regime_live.most_common()))
    print("  live/magna53 by DATE-JOINED regime (data_gated_reviews.yaml predicate, "
          "mi_market_regime ON regime_date=alert_date): Bull 9 · Correcting 7 · Choppy 4 "
          "(measured directly against prod 2026-08-17, not from this snapshot)")
    print("  The predicate fired on the date-joined count (9). Using the entry-stamped count "
          "instead (the rule this analysis follows, per #508 2026-08-08), live-Bull is 6 — "
          "still clears the review's own n>=4 floor, so the fire stands; the number it used "
          "to fire was inflated by regime revisions AFTER entry, not by extra trades.")

    # ── live-only regime breakdown, all 4 cells (Bull/Choppy/Correcting/Crisis) ──
    print("\n--- LIVE/MAGNA53 ONLY, BY ENTRY-STAMPED REGIME (the whole point: no paper mixed in) ---")
    regimes = ["Bull", "Choppy", "Correcting", "Crisis"]
    for rg in regimes:
        sub = [t for t in live_mag if t.rec["regime"] == rg]
        n = len(sub)
        if n == 0:
            print(f"  {rg:<11} n=0")
            continue
        realized = [t.rec["realized_r"] for t in sub]
        peaks = [t.rec["peak_r"] for t in sub if t.rec["peak_r"] is not None]
        adr_realized = [t.rec["realized_adr"] for t in sub if t.rec["realized_adr"] is not None]
        adr_peak = [t.rec["peak_adr"] for t in sub if t.rec["peak_adr"] is not None]
        wins = sum(1 for r in realized if r > 0)
        mean_r = sum(realized) / n
        readable = "  <-- n<4, NOT a result" if n < 4 else ""
        print(f"  {rg:<11} n={n:<2} tickers={[t.rec['ticker'] for t in sub]}{readable}")
        print(f"      realized_r  mean {fmt(mean_r)}  wins {wins}/{n}  "
              f"values {[round(r,2) for r in realized]}")
        if peaks:
            p90 = pctile(peaks, 0.90)
            share1 = sum(1 for p in peaks if p >= 1.0) / len(peaks)
            share2 = sum(1 for p in peaks if p >= 2.0) / len(peaks)
            print(f"      peak_r(reached) mean {fmt(sum(peaks)/len(peaks))}  P90 {fmt(p90)}  "
                  f"reached>=1R {share1*100:.0f}%  reached>=2R {share2*100:.0f}%  n_peak={len(peaks)}")
        if adr_realized:
            print(f"      realized_adr (ADR20-normalised, distance in own daily ranges) "
                  f"mean {fmt(sum(adr_realized)/len(adr_realized))}  "
                  f"P90 {fmt(pctile(adr_realized, 0.90))}  n={len(adr_realized)}")
        if adr_peak:
            print(f"      peak_adr (reached, ADR20-normalised) "
                  f"mean {fmt(sum(adr_peak)/len(adr_peak))}  "
                  f"P90 {fmt(pctile(adr_peak, 0.90))}  n={len(adr_peak)}")

    # ── the actual ask: live-Bull vs live-Correcting, head to head ──
    print("\n--- LIVE-BULL vs LIVE-CORRECTING, HEAD TO HEAD (removes the paper-vs-live axis) ---")
    bull = [t for t in live_mag if t.rec["regime"] == "Bull"]
    corr = [t for t in live_mag if t.rec["regime"] == "Correcting"]
    print(f"  live-Bull      n={len(bull)}   live-Correcting n={len(corr)}")
    for label, sub in (("live-Bull", bull), ("live-Correcting", corr)):
        n = len(sub)
        if n < 4:
            print(f"  {label:<16} n={n} — BELOW the n>=4 floor this probe's own table enforces. "
                  f"Not read as a result.")
            continue
        realized = [t.rec["realized_r"] for t in sub]
        peaks = [t.rec["peak_r"] for t in sub if t.rec["peak_r"] is not None]
        hold = [t.rec["hold_trading_days"] for t in sub if t.rec["hold_trading_days"] is not None]
        wins = sum(1 for r in realized if r > 0)
        print(f"  {label:<16} n={n}  realized_r mean {fmt(sum(realized)/n)}  wins {wins}/{n}  "
              f"hold_days mean {fmt(sum(hold)/len(hold) if hold else float('nan'), 5, 2)}")
        if peaks:
            print(f"      {'':<16} peak_r reached mean {fmt(sum(peaks)/len(peaks))}  "
                  f"P90 {fmt(pctile(peaks, 0.90))}  max {fmt(max(peaks))}  "
                  f"share reaching >=2R {sum(1 for p in peaks if p>=2.0)/len(peaks)*100:.0f}%")

    # ── candidate grid, live-only, Bull vs Correcting ──
    print("\n--- CANDIDATE GRID, LIVE-ONLY, Bull vs Correcting (n<4 cells suppressed) -----")
    names = [n for n in cands if n != "nothing"]
    hdr = f"  {'candidate':<30}{'live-Bull (n='+str(len(bull))+')':>22}{'live-Correcting (n='+str(len(corr))+')':>25}"
    print(hdr)
    show_readable = len(bull) >= 4 and len(corr) >= 4
    if not show_readable:
        print("  (suppressed — at least one live-regime cell is still below n=4)")
    else:
        for name in names:
            row = f"  {name:<30}"
            for sub in (bull, corr):
                vals = [results[name][t.rec["trade_id"]].kept_r
                        for t in sub if t.rec["trade_id"] in results[name]]
                cell = f"{sum(vals)/len(vals):+.2f} (n{len(vals)})" if vals else "n/a"
                row += f"{cell:>22}" if sub is bull else f"{cell:>25}"
            print(row)

    # ── the regime-conditional "let runners go in Bull" arms, live cells only ──
    print("\n--- REGIME-CONDITIONAL ARMS (rgm_*), LIVE-ONLY cells --------------------------")
    rgm_names = [n for n in cands if n.startswith("rgm_")]
    for name in rgm_names:
        row = f"  {name:<28}"
        for label, sub in (("Bull", bull), ("Choppy", [t for t in live_mag if t.rec["regime"]=="Choppy"]),
                            ("Corr", corr)):
            vals = [results[name][t.rec["trade_id"]].kept_r
                    for t in sub if t.rec["trade_id"] in results[name]]
            cell = f"{label}={sum(vals)/len(vals):+.2f}(n{len(vals)})" if vals else f"{label}=n/a"
            row += f"  {cell}"
        print(row)

    print("\n--- PAPER CELLS (labelled, reported separately, NEVER mixed into the live read) ---")
    for rg in ["Bull", "Choppy", "Correcting"]:
        sub = [t for t in paper_mag if t.rec["regime"] == rg]
        if not sub:
            print(f"  paper/magna53 {rg:<11} n=0")
            continue
        realized = [t.rec["realized_r"] for t in sub]
        wins = sum(1 for r in realized if r > 0)
        print(f"  paper/magna53 {rg:<11} n={len(sub)}  realized_r mean {fmt(sum(realized)/len(sub))}  "
              f"wins {wins}/{len(sub)}")

    print()


if __name__ == "__main__":
    run()
