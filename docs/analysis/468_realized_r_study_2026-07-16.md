# #468 MODERATE-vs-HIGH realized-R study — 2026-07-16

Cohort: 834 alerts (mi_ep_alerts, all-time), bracket-sim on daily-proxy bars (entry open×1.005, stop −3.5% = the median REAL fill stop distance n=71, exit stop-or-close-d5, no partials). Day-0 stop-touch counts −1R (conservative, both tiers). The COMPARISON is the deliverable; absolute R is understated.

## HIGH
- alerts 676 · day-0 bar found 670 · triggered 623 (93%) · stopped 483/623 (78%)
- realized-R: n=623  mean +0.55R  med -1.00R  win  21%  expectancy +0.55R

## MODERATE
- alerts 158 · day-0 bar found 157 · triggered 146 (93%) · stopped 109/146 (75%)
- realized-R: n=146  mean +0.88R  med -1.00R  win  22%  expectancy +0.88R

## Raw ep_score bands (tier-agnostic, same sim)
- score 80+     n=295  mean +0.87R  med -1.00R  win  23%  expectancy +0.87R
- score 70-79   n= 66  mean -0.26R  med -1.00R  win  12%  expectancy -0.26R
- score 60-69   n= 97  mean +0.90R  med -1.00R  win  25%  expectancy +0.90R
- score 50-59   n=208  mean +0.55R  med -1.00R  win  21%  expectancy +0.55R

## Read

**The tier boundary does NOT separate tradeable outcomes.** On an identical
bracket simulation:

1. **MODERATE ≥ HIGH**: final-tier MODERATE expectancy +0.88R vs HIGH +0.55R,
   equal trigger and win rates — the briefing-only tier carries at least as
   much bracket edge as the auto-trade tier (proxy-level evidence that
   MODERATE holds uncaptured edge; Q4's raw-return parity survives the
   translation to realized-R).
2. **The 70-79 score band is a HOLE**: −0.26R, 12% win (n=66) — the worst band
   in the study, sitting exactly at/above the HIGH boundary, while 60-69 (the
   band the boundary excludes) is the BEST (+0.90R, 25% win, n=97). 80+ is
   healthy (+0.87R, n=295). Non-monotone: marginal names pushed over the line
   underperform names just under it. This RHYMES with the same-day #448 B6
   finding (the catalyst-composite gate inverted on forward outcomes): the
   scoring's marginal region systematically selects faders.
3. **Implication**: the lever is NOT the threshold (moving 70 up or down can't
   fix a non-monotone score) — it's score COMPOSITION (the #368/#328-331
   meta-rubric work) and possibly a gated MODERATE→entry experiment.
   Both are operator decisions (THE LINE).

Confidence: comparative read robust to the proxy (identical mechanics both
tiers); absolute R understated by the conservative day-0 rule. If acting on
it, run the polygon_minute precision pass first (the bars-source seam).

Limitations: daily-proxy (no true ORB range; day-0 ordering conservative); yfinance adjusted-history quirks on delistings; re-run with bars_source=polygon_minute for the precise version if the read is borderline.