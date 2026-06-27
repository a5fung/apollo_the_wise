"""#327 Anticipation — COIL finder (operator-locked model, 2026-06-27).

Setup gates (operator-confirmed):
  1. RUNUP   — a leg up >=15% (prior swing low -> peak).
  2. HOLD    — the consolidation low stays above the ~50% retrace of that runup leg. Give back more
               than half and the runup is NEGATED -> not basing, regardless of tightness. HARD gate.
               (50% is the operator's rough cap; shallower is better; the exact limit is to be TESTED,
               so retrace is REPORTED, not silently hardcoded.)
  3. TIGHT   — within the holding zone, a tight, flat coil. This RANKS what survives the hold gate.
  NOT gates: pullback depth/duration/shape, or touching a specific MA (CRWD's 20MA kiss was incidental).

No peak-anchored "base = peak..now" (that swallowed the pullback and read CRWD at 24%). We detect the
runup leg, measure the give-back, and measure tightness over the RECENT coil window separately.

  docker exec -i -w /app apollo-market python -   < this file
"""
import asyncio
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from agents.market_intelligence import anticipation as de
from agents.market_intelligence.db import get_anticipation_ohlcv

POSITIVE = ["GH", "HNGE", "CRWD", "FTNT", "DDOG"]
POOR = ["OSCR", "GPGI", "UAL", "PTGX", "TVTX"]
START = date(2026, 4, 15)
END = date(2026, 6, 26)

RUNUP_LB = 45        # window to locate the runup peak
RUNUP_MIN = 1.15     # >=15% leg
PRE_LB = 30          # look back this far before the peak for the runup-leg base (prior swing low)
MIN_CONS = 4         # min consolidation length after the peak
COIL_WIN = 12        # tightness measured over the recent N days of the consolidation
HOLD_LIMIT = 0.50    # SOFT reference (operator ~50%, shallower better) — reported + tuned, not hard law


def find_setup(bars, i):
    """As-of bar i: runup leg -> consolidation give-back (retrace) -> recent coil tightness."""
    closes = [b["c"] for b in bars]
    if i < RUNUP_LB + 5:
        return None
    pk = max(range(i - RUNUP_LB, i + 1), key=lambda k: closes[k])   # runup peak
    cons_len = i - pk
    if cons_len < MIN_CONS:                                          # need a consolidation after the peak
        return None
    peak = closes[pk]
    pre = min(range(max(0, pk - PRE_LB), pk + 1), key=lambda k: closes[k])
    prelow = closes[pre]
    leg = peak - prelow
    if leg <= 0 or peak / prelow < RUNUP_MIN:
        return None
    cons = bars[pk + 1:i + 1]
    retrace = (peak - min(b["l"] for b in cons)) / leg              # fraction of the runup given back
    win = cons[-min(len(cons), COIL_WIN):]                          # the recent coil
    hi = max(b["h"] for b in win); lo = min(b["l"] for b in win); mc = sum(b["c"] for b in win) / len(win)
    band = (hi - lo) / mc
    ys = [b["c"] for b in win]; nx = len(ys); xs = list(range(nx))
    mxx = sum(xs) / nx; myy = sum(ys) / nx
    den = sum((x - mxx) ** 2 for x in xs)
    slope = (sum((x - mxx) * (y - myy) for x, y in zip(xs, ys)) / den / mc) if den else 0.0
    # DURATION: how far back the close stays inside the coil [lo, hi] = the FULL base (not just the
    # recent coil window). PTGX-style months-long bases are "too long to wait" (Pradeep 3-20d, sweet 4-10).
    base_len = 0
    for k in range(i, -1, -1):
        if lo <= bars[k]["c"] <= hi:
            base_len += 1
        else:
            break
    # ORDERLINESS: mean daily range % over the coil. Gappy / drunken-man-walk = high; tight orderly = low.
    adr = sum((b["h"] - b["l"]) / b["c"] for b in win) / len(win) * 100
    return {"peak": bars[pk]["date"], "runup": peak / prelow, "consD": cons_len, "retrace": retrace,
            "coilD": len(win), "baseLen": base_len, "band": band, "slope": slope, "adr": adr}


async def main():
    print(f"HOLD_LIMIT (soft, testable) = {HOLD_LIMIT*100:.0f}% retrace of the runup leg\n")
    for label, names in (("POSITIVE (good coils)", POSITIVE), ("POOR (reject set)", POOR)):
        print(f"=== {label} ===")
        for tk in names:
            try:
                allb = de.db_rows_to_bars(await get_anticipation_ohlcv(tk, END, 340))
            except Exception as e:
                print(f"  {tk:6} FETCH-ERR {e}")
                continue
            setups = []
            d = START
            while d <= END:
                ds = d.isoformat()
                asof = [b for b in allb if b["date"] <= ds]
                if len(asof) >= RUNUP_LB + 5:
                    s = find_setup(asof, len(asof) - 1)
                    if s:
                        setups.append((ds, s))
                d += timedelta(days=1)
            if not setups:
                print(f"  {tk:6} no runup->consolidation found")
                continue
            held = [x for x in setups if x[1]["retrace"] <= HOLD_LIMIT]
            if held:
                ds, s = min(held, key=lambda x: x[1]["band"])          # tightest coil that HELD <=50%
                print(f"  {tk:6} as-of {ds}: peak={s['peak']} runup={s['runup']:.2f} "
                      f"retrace={s['retrace']*100:4.0f}% baseLen={s['baseLen']:3} coilD={s['coilD']:2} "
                      f"band={s['band']*100:4.1f}% adr={s['adr']:4.1f}% slope={s['slope']:+.4f}")
            else:
                sh = min(setups, key=lambda x: x[1]["retrace"])
                print(f"  {tk:6} NEVER held <={HOLD_LIMIT*100:.0f}% (min retrace {sh[1]['retrace']*100:.0f}%) "
                      f"-> runup negated, not basing")


if __name__ == "__main__":
    asyncio.run(main())
