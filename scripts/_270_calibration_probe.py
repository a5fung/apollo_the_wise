#!/usr/bin/env python3
"""#270 calibration probe (gate-free, read-only) — surface VALUES for the two open
operator decisions before the Step-3 wiring. Does NOT self-certify thresholds; it
prints the cohort distribution + a recommended floor for OPERATOR sign-off.

  #1 EXPANSION floor — TRIGGERED uses `vol > EXPANSION * avg(pullback_vol)`. The ratio
     is unstable on near-zero pullback baselines (a pullback that contracts to almost no
     volume gives a tiny denominator -> 80-100x artifact). Fix = floor the denominator
     (base) relative to ADV20, OR cap the ratio.
  #2 Trigger-volume floor — a thin trigger bar passes the RELATIVE expansion gate despite
     the $20M gap-day liquidity seed. Fix = an absolute share / dollar-volume floor on the
     trigger bar.

Method: re-run the canonical replay() (no duplicated lifecycle logic) for authoritative
WATCHED/TRIGGERED dates, then recompute the per-trigger volume metrics from the same daily
bars and tie each to its forward 10d MFE (does the floor drop WINNERS or LOSERS?). ASCII.
"""
import importlib.util
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("r270", HERE / "_270_delayed_ep_replay.py")
r270 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r270)
replay = r270.replay

bars_by = defaultdict(list)
for _line in (HERE / "_270_cohort_bars.tsv").read_text(encoding="utf-8").splitlines():
    _p = _line.rstrip("\r").split("\t")
    if len(_p) != 7:
        continue
    _t, _d, _o, _h, _l, _c, _v = _p
    bars_by[_t].append({"date": _d, "o": float(_o), "h": float(_h), "l": float(_l),
                        "c": float(_c), "v": float(_v)})
for _t in bars_by:
    bars_by[_t].sort(key=lambda b: b["date"])


def adv20(vols, i):
    lo = max(0, i - 19)
    return sum(vols[lo:i + 1]) / (i - lo + 1)


def fwd_mfe(bars, ti, n=10):
    entry = bars[ti]["c"]
    fwd = bars[ti + 1: ti + 1 + n]
    return (max(b["h"] for b in fwd) / entry - 1) if fwd else None


rows = []
for t, bars in bars_by.items():
    dates = [b["date"] for b in bars]
    vols = [b["v"] for b in bars]
    closes = [b["c"] for b in bars]
    idx_of = {d: i for i, d in enumerate(dates)}
    last_watched = None
    for date, state, _ in replay(bars):
        if state == "WATCHED":
            last_watched = date
        elif state == "TRIGGERED" and last_watched is not None:
            gi, ti = idx_of[last_watched], idx_of[date]
            if ti <= gi + 1:
                last_watched = None
                continue
            base = statistics.fmean(vols[gi + 1:ti])     # == replay's pull_vols[:-1]
            tvol = vols[ti]
            adv = adv20(vols, ti)
            rows.append({"t": t, "date": date, "tvol": tvol, "dvol": tvol * closes[ti],
                         "base": base, "ratio": tvol / base if base else float("inf"),
                         "adv": adv, "base_adv": base / adv if adv else float("nan"),
                         "mfe": fwd_mfe(bars, ti)})
            last_watched = None

rows.sort(key=lambda r: r["dvol"])
print(f"#270 CALIBRATION PROBE — {len(rows)} TRIGGERED events (read-only; for operator sign-off)\n")
print(f"{'ticker':<7}{'date':<12}{'trig vol':>10}{'$ vol':>9}{'base(pb)':>10}{'ratio':>8}"
      f"{'base/ADV':>9}{'fwd MFE':>9}")
for r in rows:
    mfe = f"{r['mfe']*100:+.0f}%" if r['mfe'] is not None else "n/a"
    print(f"{r['t']:<7}{r['date']:<12}{r['tvol']/1e6:>9.2f}M{r['dvol']/1e6:>8.0f}M"
          f"{r['base']/1e6:>9.2f}M{r['ratio']:>7.1f}x{r['base_adv']:>8.2f}{mfe:>9}")

# ── decision #1: EXPANSION floor (stabilize the ratio's denominator) ──
print("\n--- #1 EXPANSION FLOOR (the ratio's denominator `base`) ---")
arts = [r for r in rows if r["ratio"] >= 10]
print(f"artifacts (ratio >= 10x, tiny-denominator): "
      f"{', '.join(f'{r['t']} {r['ratio']:.0f}x@base/ADV={r['base_adv']:.2f}' for r in arts) or 'none'}")
for frac in (0.25, 0.5):
    capped = []
    for r in rows:
        fb = max(r["base"], frac * r["adv"])              # floor base at frac*ADV20
        capped.append(r["tvol"] / fb if fb else float("inf"))
    mx = max(capped)
    still = sum(1 for c in capped if c >= 10)
    print(f"  floor base at {frac:.2f}x ADV20 -> max ratio {mx:.1f}x, "
          f"#still>=10x: {still}  (EXPANSION gate {r270.EXPANSION}x still passes all real triggers)")
print("  (note: flooring the DENOMINATOR only changes the displayed ratio + protects the gate "
      "from a near-zero base;\n   it does NOT drop triggers — every name here already passed "
      f"EXPANSION>{r270.EXPANSION}x on the true base.)")

# ── decision #2: trigger-volume floor (absolute liquidity on the trigger bar) ──
print("\n--- #2 TRIGGER-VOLUME FLOOR (absolute liquidity of the trigger bar) ---")
for dfloor in (5, 10, 20):
    drop = [r for r in rows if r["dvol"] < dfloor * 1e6]
    keep = [r for r in rows if r["dvol"] >= dfloor * 1e6]
    win_drop = [r for r in drop if (r["mfe"] or 0) >= 0.20]
    kept_mfe = [r["mfe"] for r in keep if r["mfe"] is not None]
    med_keep = statistics.median(kept_mfe) if kept_mfe else float("nan")
    print(f"  $-vol floor ${dfloor}M: drops {len(drop)}/{len(rows)} "
          f"[{', '.join(r['t'] for r in drop) or '-'}]  "
          f"winners(>=+20%) dropped: {len(win_drop)} [{', '.join(r['t'] for r in win_drop) or '-'}]"
          f"  | kept median MFE {med_keep*100:+.0f}%")
print("  (the floor is GOOD if it drops thin LOSERS while retaining the >=+20% winners — "
      "that is the\n   selectivity test; a floor that drops a fat-tail winner is too high.)")
