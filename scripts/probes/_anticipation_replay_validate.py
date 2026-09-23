"""#327 Anticipation — daily-replay validation (the real Step 2/3).

The detector is supposed to FIND the base, daily, like the live shadow. So we replay it
day-by-day over history and ask, for each known-good coil and each junk name: on which days
does the detector flag a runup->base, and what is the base structure at that flag-day? The
detector's own flag-date is the per-name as-of (operator supplies NAMES, not windows).

Validates: does it flag HNGE during its real May base and NOT the June uptrend? does it
flag the poor batch (and can the structure features tell them apart)? Reuses the deployed
detector logic (features() = #389 anchor + runup/base gate + the 5 structure metrics).

  docker exec -i -w /app apollo-market python -   < this file
"""
import asyncio
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from agents.market_intelligence import anticipation as de
from agents.market_intelligence.db import get_anticipation_ohlcv
from _anticipation_step2_features import features   # #389 anchor + gate + 5-metric structure

POSITIVE = ["GH", "HNGE", "CRWD", "FTNT", "DDOG"]    # operator's known-good coils (names only)
POOR = ["OSCR", "GPGI", "UAL", "PTGX", "TVTX"]        # the reject set
START = date(2026, 4, 15)
END = date(2026, 6, 26)


def f4(v):
    return f"{v:.4f}" if isinstance(v, (int, float)) else "-"


# Pradeep DEPTH gate (operator_shared_notes 6/22): a valid consolidation holds NEAR the high.
RETRACE_MAX = 0.15      # max drop from the anchor peak (upper-third "holds the gains")
BREAKDOWN_MAX = 1       # max daily >=4% breakdowns inside the base (one-strike rule)


def depth(asof_bars, fr):
    """Retrace-from-peak + count of >=4% daily breakdowns over the base. None if anchor missing."""
    ai = next((k for k, b in enumerate(asof_bars) if b["date"] == fr["anchor"]), None)
    if ai is None:
        return None
    peak = asof_bars[ai]["c"]
    base = asof_bars[ai + 1:]
    if not base or peak <= 0:
        return None
    retrace = (peak - min(b["l"] for b in base)) / peak
    bd = sum(1 for k in range(1, len(base)) if base[k]["c"] / base[k - 1]["c"] - 1 <= -0.04)
    return retrace, bd


async def main():
    for label, names in (("POSITIVE (good coils)", POSITIVE), ("POOR (reject set)", POOR)):
        print(f"\n=== {label} ===")
        for tk in names:
            try:
                allb = de.db_rows_to_bars(await get_anticipation_ohlcv(tk, END, 340))
            except Exception as e:
                print(f"  {tk:6} FETCH-ERR {e}")
                continue
            flags = []
            d = START
            while d <= END:
                ds = d.isoformat()
                asof = [b for b in allb if b["date"] <= ds]
                fr = features(asof) if len(asof) >= 30 else None
                if fr:
                    flags.append((ds, fr))
                d += timedelta(days=1)
            if not flags:
                print(f"  {tk:6} NEVER flagged {START}..{END} (no runup->base detected)")
                continue
            # PRIME coil = the flagged day with the tightest band (the operator enters the
            # quietest pocket). Compare good vs poor AT THEIR PRIMES — like-for-like.
            def band_of(x):
                b = x[1]["band_pct"]
                return b if isinstance(b, (int, float)) else 1e9
            ds, fr = min(flags, key=band_of)
            print(f"  {tk:6} {len(flags):2}d flagged.  PRIME(tightest)={ds}  "
                  f"anchor={fr['anchor']} baseD={fr['baseD']:2} runup={fr['runup']}  "
                  f"flat={f4(fr['flatness'])} band={f4(fr['band_pct'])} "
                  f"contr={f4(fr['contraction'])} volx={f4(fr['vol_exh'])} shake={fr['shakeout']}")


if __name__ == "__main__":
    asyncio.run(main())
