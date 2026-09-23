#!/usr/bin/env python3
"""#327 audit — per-name dump of the settled arms, to sanity-check the head-to-head edge
isn't a settlement bug (distinct tickers, sane entry<stop direction, plausible R)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import _327_replay as R  # noqa: E402

cohort = R.load_cohort()
daily = R.load_daily()
minute = R.load_minute()
rows = [R.analyze_name(c, daily) for c in cohort]

print("ARM 2 consolidation fills (ticker | 9M-day | coil | breakout | runup | entry | stop | R):")
a2 = []
for r in rows:
    if r["arm2_idx"] is None or not r["arm2_fwd_ok"]:
        continue
    raw = minute.get((r["ticker"], r["arm2_breakout"]))
    if not raw:
        continue
    rth = R.de.polygon_to_rth_minutes(raw, r["arm2_breakout"])
    s = R.settle_arm2(rth, r["base_high"], R._daily_forward(daily[r["ticker"]], r["arm2_idx"]))
    if s and s[0] != 0.0:
        a2.append((r["ticker"], r["alert_date"], r["arm2_coil"], r["arm2_breakout"],
                   r["runup"], s[1], s[2], s[0]))
for t, ad, co, bo, ru, e, st, rr in sorted(a2, key=lambda x: -x[7]):
    print(f"  {t:<6} {ad}  {co}  {bo}  ru{ru}  e{e:.2f}/s{st:.2f}  {rr:+.2f}R")
print(f"  -> {len(a2)} fills, {len(set(x[0] for x in a2))} distinct tickers")

print("\nARM 1 Day-2 ORB fills (ticker | day2 | entry | stop | R), top & bottom:")
a1 = []
for r in rows:
    if r["arm1_idx"] is None or not r["arm1_fwd_ok"]:
        continue
    raw = minute.get((r["ticker"], r["arm1_day"]))
    if not raw:
        continue
    rth = R.de.polygon_to_rth_minutes(raw, r["arm1_day"])
    s = R.settle_arm1(rth, r["prior_low"], R._daily_forward(daily[r["ticker"]], r["arm1_idx"]))
    if s and s[0] != 0.0:
        a1.append((r["ticker"], r["arm1_day"], s[1], s[2], s[0]))
a1.sort(key=lambda x: -x[4])
for t, d, e, st, rr in a1[:5] + a1[-5:]:
    print(f"  {t:<6} {d}  e{e:.2f}/s{st:.2f}  {rr:+.2f}R")
print(f"  -> {len(a1)} fills, {len(set(x[0] for x in a1))} distinct tickers")
