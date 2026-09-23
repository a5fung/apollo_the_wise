#!/usr/bin/env python3
"""#270 step 1 (gate-free replay) — delayed-EP re-entry composition, validated vs MNTS.

The fragments already fire (EP gap, flag watch, 9M pings); the MISSING layer is
COMPOSITION into one lifecycle (case study docs/analysis/mnts_delayed_ep_case_study).
This replays that state machine from daily bars and checks it reproduces the known
MNTS case (WATCHED 5/26 → ARMED 6/08 undercut → TRIGGERED 6/11 reclaim, +43% day).

STATE MACHINE (all from daily OHLCV):
  WATCHED   gap day: close >= (1+GAP)·prev_close, close > SMA200, vol >= VOLX·ADV20.
            Records gap_day_low (the U&R reference) + gap_day_vol.
  ARMED     within ARM_WINDOW trading days: low < gap_day_low (UNDERCUT of the
            gap-day low — the event the flag detector wrongly INVALIDATES on), on
            volume below the burst (pullback contraction).
  TRIGGERED after armed: close > gap_day_low AND close > SMA20 (reclaim BOTH refs)
            AND vol > EXPANSION · avg(pullback vol) (the explosive R-leg signature).

Thresholds are TEMPLATE-grounded defaults for OPERATOR CALIBRATION — they are NOT
self-certified. The replay prints the actual values so the operator can tune.
Read-only (a pulled bar snapshot); gate-free — touches nothing executable.

Usage: python scripts/_270_delayed_ep_replay.py [bars.tsv]
       (TSV cols: trade_date<TAB>open<TAB>high<TAB>low<TAB>close<TAB>volume)
"""
import sys
from pathlib import Path

# ── tunable thresholds (template-grounded; OPERATOR to calibrate) ────────────
GAP = 0.40          # gap-day close >= +40% vs prior close (MNTS was +110%)
VOLX = 3.0          # gap-day volume >= 3x ADV20 (mirrors the 9M 3x-ADV gate)
ARM_WINDOW = 15     # undercut must land within 15 trading days of the gap
EXPANSION = 1.5     # trigger volume > 1.5x the pullback's average volume

TSV = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "_270_bars_mnts.tsv"


def load(tsv: Path):
    bars = []
    for line in tsv.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        if "\t" not in line:
            continue
        d, o, h, l, c, v = line.split("\t")
        bars.append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                     "c": float(c), "v": float(v)})
    return bars


def sma(vals, i, n):
    if i + 1 < n:
        return None
    return sum(vals[i - n + 1:i + 1]) / n


def ema_series(vals, n):
    k = 2 / (n + 1)
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    seed = sum(vals[:n]) / n
    out[n - 1] = seed
    for i in range(n, len(vals)):
        out[i] = vals[i] * k + out[i - 1] * (1 - k)
    return out


def replay(bars):
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    ema21 = ema_series(closes, 21)
    events = []
    state = "NONE"
    g = {}          # active WATCHED context
    pull_vols = []  # volumes observed during the pullback (for expansion baseline)

    for i, b in enumerate(bars):
        sma200 = sma(closes, i, 200)
        sma20 = sma(closes, i, 20)
        adv20 = sma(vols, i, 20)
        prev_c = closes[i - 1] if i > 0 else None

        if state in ("NONE", "TRIGGERED"):
            if prev_c and adv20 and sma200:
                gap = b["c"] / prev_c - 1
                if gap >= GAP and b["c"] > sma200 and b["v"] >= VOLX * adv20:
                    state = "WATCHED"
                    g = {"date": b["date"], "low": b["l"], "vol": b["v"],
                         "gap": gap, "i": i}
                    pull_vols = []
                    events.append((b["date"], "WATCHED",
                                   f"gap +{gap*100:.0f}% close {b['c']:.2f} > SMA200 "
                                   f"{sma200:.2f}; vol {b['v']/1e6:.1f}M = {b['v']/adv20:.1f}x ADV20; "
                                   f"gap_day_low={b['l']:.2f}"))
            continue

        # in WATCHED or ARMED: accumulate pullback volume (days after the gap)
        if i > g["i"]:
            pull_vols.append(b["v"])

        if state == "WATCHED":
            if i - g["i"] > ARM_WINDOW:
                events.append((b["date"], "EXPIRED",
                               f"no undercut within {ARM_WINDOW}d of gap"))
                state, g = "NONE", {}
                continue
            if b["l"] < g["low"] and b["v"] < g["vol"]:
                state = "ARMED"
                events.append((b["date"], "ARMED",
                               f"UNDERCUT gap_day_low {g['low']:.2f}: low {b['l']:.2f}; "
                               f"vol {b['v']/1e6:.1f}M < burst {g['vol']/1e6:.0f}M (contraction)"))
            continue

        if state == "ARMED":
            base = sum(pull_vols[:-1]) / max(len(pull_vols) - 1, 1) if len(pull_vols) > 1 else g["vol"]
            reclaim = b["c"] > g["low"] and (sma20 is None or b["c"] > sma20)
            expand = b["v"] > EXPANSION * base
            ema_ok = ema21[i] is None or b["c"] > ema21[i]
            if reclaim and expand:
                events.append((b["date"], "TRIGGERED",
                               f"RECLAIM close {b['c']:.2f} > gap_day_low {g['low']:.2f}"
                               f"{' & > SMA20 '+format(sma20,'.2f') if sma20 else ''}"
                               f"{' & > EMA21' if ema_ok else ' (BELOW EMA21!)'}; "
                               f"vol {b['v']/1e6:.1f}M = {b['v']/base:.1f}x pullback-avg (expansion)"))
                state = "TRIGGERED"
            continue
    return events


def main():
    bars = load(TSV)
    print(f"bars: {TSV.name}  ({len(bars)} rows, {bars[0]['date']}..{bars[-1]['date']})")
    print(f"thresholds: GAP>={GAP:.0%}  VOLX>={VOLX}x  ARM_WINDOW={ARM_WINDOW}d  EXPANSION>{EXPANSION}x  "
          "(template-grounded; operator to calibrate)\n")
    events = replay(bars)
    for date, state, detail in events:
        print(f"  {date}  {state:<9} {detail}")
    seen = [e[1] for e in events]
    # MNTS known-good validation
    if TSV.name == "_270_bars_mnts.tsv":
        exp = {"WATCHED": "2026-05-26", "ARMED": "2026-06-08", "TRIGGERED": "2026-06-11"}
        print("\nVALIDATION vs known MNTS lifecycle:")
        ok = True
        for st, want in exp.items():
            got = next((d for d, s, _ in events if s == st), None)
            mark = "OK " if got == want else "XX "
            if got != want:
                ok = False
            print(f"  {mark}{st}: expected {want}, got {got}")
        print("\nRESULT:", "PASS - composition reproduces the MNTS lifecycle"
              if ok else "FAIL - logic does not match the known case (tune/fix)")
    else:
        print(f"\nstates reached: {seen}")


if __name__ == "__main__":
    main()
