"""#327 Track-2 Step 2 — quantify the operator's structural signature (a HYPOTHESIS, not a gate).

Step 1 is COMPLETE (operator 2026-06-27): the positive set + the signature ("prior runup → tight flat
basing → range tightens → volume contracts → undercut but rally back quickly") are fixed. This script
computes the agreed 5-metric feature matrix for the POSITIVE set vs the POOR batch, all measured on the
BASING as-of date (pre-breakout — hindsight discipline) with the #389 corrected base-start anchor. We are
LOOKING FOR a clean separator, NOT asserting one (ADR 0013: no invented thresholds). n≈5/5 is too small to
calibrate — this shapes the Step-3 operator conversation + the forward-shadow hypothesis.

Feature matrix (coil hypothesis in parens):
  1. base_flatness     slope(base closes)/mean-price           (≈ 0)
  2. band_width_pct    (max_high − min_low)/mean_close × 100   (< X% absolute tightness)
  3. shakeout_streak   max consecutive base closes < floor     (≤ 1: one undercut, then reclaim)
  4. contraction       ATR(recent half)/ATR(early half)        (< 1.0 actively coiling)
  5. vol_exhaustion    mean(vol recent half)/SMA(vol,50)       (< 0.7 dry-up into the base)

READ-ONLY. Runs where mi_daily_closes is reachable (market-agent container / prod DB):

  docker exec apollo-market python /app/scripts/_anticipation_step2_features.py --asof 2026-06-19
"""
import argparse
import asyncio
import sys
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from agents.market_intelligence import anticipation as de
from agents.market_intelligence.db import get_anticipation_ohlcv
from _anticipation_shortlist import stable_anchor_idx   # #389 corrected anchor — single source

POSITIVE = ["GH", "HNGE", "CRWD", "FTNT", "DDOG"]              # operator's known-good coils (Step 1)
POOR = ["OSCR", "GPGI", "UAL", "PTGX", "TVTX"]                 # fired-but-bad batch
OUT = "docs/analysis/anticipation_step2_features_2026-06-27.md"


def _slope(ys):
    """OLS slope of ys vs index 0..n-1 (pure python, no numpy)."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def _atr(bars):
    """Average true range over `bars` (needs a prior bar for the gap term; uses each bar's own range
    for the first)."""
    if not bars:
        return None
    trs = []
    for k, b in enumerate(bars):
        if k == 0:
            trs.append(b["h"] - b["l"])
        else:
            pc = bars[k - 1]["c"]
            trs.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    return sum(trs) / len(trs)


def features(bars):
    """The 5-metric structural record for one name's base, or None if no qualifying anchor/base."""
    if len(bars) < 30:
        return None
    ai = stable_anchor_idx(bars)
    if ai is None or ai < 10:
        return None
    peak = bars[ai]["c"]
    runup = peak / min(bars[j]["c"] for j in range(ai - 10, ai + 1))
    if runup < 1.15:
        return None
    base = bars[ai + 1:]
    if len(base) < 4:
        return None

    closes = [b["c"] for b in base]
    mean_c = sum(closes) / len(closes)
    # 1. base flatness — normalized slope (per-bar drift as a fraction of price)
    flatness = _slope(closes) / mean_c if mean_c else None
    # 2. absolute band width %
    band = (max(b["h"] for b in base) - min(b["l"] for b in base)) / mean_c * 100 if mean_c else None
    # 3. shakeout-tolerant floor: floor = min low of the base's FIRST half (the established support
    #    before any shakeout); count the longest run of consecutive closes that dip below it.
    half = max(len(base) // 2, 1)
    floor = min(b["l"] for b in base[:half])
    streak = run = 0
    for c in closes:
        run = run + 1 if c < floor else 0
        streak = max(streak, run)
    # 4. contraction ratio — ATR(recent half)/ATR(early half) of the base
    early, recent = base[:half], base[half:]
    atr_e, atr_r = _atr(early), _atr(recent)
    contraction = (atr_r / atr_e) if (atr_e and atr_r) else None
    # 5. volume exhaustion — mean(vol recent half of base) / SMA(vol, 50) ending at the as-of bar
    vol50 = [b["v"] for b in bars[-50:]]
    sma_vol50 = sum(vol50) / len(vol50) if vol50 else None
    recent_vol = [b["v"] for b in recent]
    mean_recent_vol = sum(recent_vol) / len(recent_vol) if recent_vol else None
    vol_exh = (mean_recent_vol / sma_vol50) if (sma_vol50 and mean_recent_vol) else None

    return {
        "anchor": bars[ai]["date"], "baseD": len(base), "runup": round(runup, 2),
        "flatness": flatness, "band_pct": band, "shakeout": streak,
        "contraction": contraction, "vol_exh": vol_exh,
    }


def _f(v, nd=4):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "–"


async def main(asof: date, lookback_days: int):
    out_rows = []
    for label, names in (("POSITIVE (good coils)", POSITIVE), ("POOR (fired-but-bad)", POOR)):
        for tk in names:
            bars = de.db_rows_to_bars(await get_anticipation_ohlcv(tk, asof, lookback_days))
            fr = features(bars)
            out_rows.append((label, tk, fr))

    lines = [
        f"# #327 Track-2 Step 2 — structural feature matrix (as-of {asof.isoformat()}, basing/pre-breakout)\n",
        "Operator signature: prior runup → tight flat basing → range tightens → volume contracts → "
        "undercut but rally back quickly. Anchor = #389 base-start peak. **Hypothesis, NOT a gate** — "
        "looking for a clean separator across the n=5/5 sets; Step 3 shapes thresholds WITH the operator, "
        "forward shadow validates.\n",
        "| set | ticker | anchor | baseD | runup | flatness(≈0) | band% | shakeout(≤1) | contraction(<1) | vol_exh(<0.7) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, tk, fr in out_rows:
        if fr is None:
            lines.append(f"| {label} | {tk} | — | — | — | NO QUALIFYING ANCHOR/BASE | | | | |")
            continue
        lines.append(
            f"| {label} | {tk} | {fr['anchor']} | {fr['baseD']} | {fr['runup']} | "
            f"{_f(fr['flatness'])} | {_f(fr['band_pct'], 1)} | {fr['shakeout']} | "
            f"{_f(fr['contraction'], 2)} | {_f(fr['vol_exh'], 2)} |")
    lines.append("\n_Failure branch (pre-committed): if these five don't separate, add a breakout-context "
                 "column and re-test ONCE; fallback = operator-curated watchlist while iterating._\n")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote feature matrix ({len(out_rows)} names) → {OUT}")
    for label, tk, fr in out_rows:
        print(f"  {tk:6} {'OK' if fr else 'NO-ANCHOR':10} "
              + (f"flat={_f(fr['flatness'])} band={_f(fr['band_pct'],1)} shake={fr['shakeout']} "
                 f"contr={_f(fr['contraction'],2)} volx={_f(fr['vol_exh'],2)}" if fr else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", type=date.fromisoformat, required=True,
                    help="basing as-of date YYYY-MM-DD (pre-breakout, ~2026-06-19)")
    ap.add_argument("--lookback-days", type=int, default=340)
    args = ap.parse_args()
    asyncio.run(main(args.asof, args.lookback_days))
