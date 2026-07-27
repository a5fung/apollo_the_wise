# Volume-Profile Context for the EP Alert — Design + Measurement (2026-07-27)

**Status: DESIGN + MEASUREMENT ONLY.** No production code changed, nothing deployed. This is
display/telemetry-first by construction — the proposal mirrors the #498 TQS Stage-1 contract
exactly (annotate-after-grade, `vol_*` columns only, nothing in grading/entry/sizing reads it).
Anything that would touch a GRADE or an ENTRY is explicitly out of scope here and requires
CHANGE_PROCESS + operator sign-off + backtest (THE LINE).

Operator ask (7/24, from the QBTS alert): *"let's look at 50d which is typically what ppl use on
volume profile (along with things like HVE — highest vol ever, highest vol in 1 year, etc.)"*

---

## 1. Why — the QBTS case, and what the current alert can't show

QBTS 7/27 HIGH alert (detected 7:20 AM ET). Verified against `mi_daily_closes`:

- Last volume close ≥ its 50d average: **2026-06-23 at 1.28×** — **22 sessions ago**
  (operator's hand-read: 6/23, 1.29×, 22 td — reproduced).
- 5-session avg volume = **0.46× the 50d base** — the **driest of all 221 cohort alerts**
  (percentile 0).
- Its TAPE line that morning: **`tape_clean`** (bmr2 1.41, ADR ~6%).

That last point is the whole card: the tape/NTR axis measures **range structure** (tightness,
spike reversals) and the sparkline plots **range**. Participation is a separate axis — QBTS reads
*clean and lively* on the existing display while volume says the crowd left a month ago. NTR↔vol
correlation on QBTS since April is 0.674: a loose proxy, and this is precisely a divergence case.
The alert's only volume numbers (RVOL, pm RVOL, intensity) are **alert-day vs a 20d ADV** — the
operator's 50d frame and any pre-alert participation trend appear nowhere.

## 2. Data constraint — the honest ceiling (verified on prod)

`mi_daily_closes` holds **2025-06-23 → 2026-07-24** (3.21M rows, 14,503 tickers, volume on every
row; 400-day retention). Consequences:

- **"Highest volume EVER" is NOT computable from the DB. Verdict: do not render "HVE" from
  `mi_daily_closes` — ever.** The honest cheap path to true HVE exists though: the per-ticker
  Polygon daily-aggs helper (`collector.py:469`, `/v2/aggs/ticker/{t}/range/1/day/...`) returns
  ~20y of daily bars in **one API call**; at the observed alert rate (225 alerts / 63 trading
  days ≈ 3.5/day) an on-alert fetch is negligible (paid key, 0.2s courtesy delay). No backfill
  of the 14.5k-ticker table needed (that would be ~70M rows — rejected).
- **"Highest volume in 1 year" barely fits and mostly doesn't**: only **34/221 (15%)** of cohort
  alerts had a full 252 pre-alert sessions (median 225). Rule: a "1y" label requires ≥252
  pre-alert live sessions; otherwise the label states the actual depth — `#1 vol day in 10mo` —
  never "1y", never "ever". (Repo convention: explicit unknown/short-labels, per
  `tape_quality.py` `_MIN_LIVE_BARS` handling.)
- **50d base minimum-history rule**: ≥50 live pre-alert sessions, else the line renders
  `VOL: unseasoned (N sessions < 50 — no 50d base)` — mirrors TAPE "unseasoned", never a silent
  junk value. Only 3/224 cohort alerts fail this.

## 3. The metric set

Conventions: all windows use sessions **strictly before** alert_date (the alert day never scores
itself — same no-lookahead rule as TQS); "live bar" = volume>0 and close>0; the 50d SMA at a
session is the trailing-50 inclusive mean (what a chart's volume-MA overlay shows at that bar).

**KEEP — measured and earning their space:**

| # | Metric | Definition | Short-data render |
|---|---|---|---|
| V1 | **r5_50** | mean(vol, last 5 pre-alert sessions) ÷ 50d SMA | `unseasoned` if <50 live bars |
| V2 | **LAB50** | sessions since volume last closed ≥ its as-of-that-day 50d SMA, + the ratio that day | segment hidden if <50 bars; shown only when ≥3 (18% of alerts — noise budget) |
| V3 | **VOL sparkline** | last 20 pre-alert sessions' vol ÷ as-of-day 50d SMA, **fixed scale** 0→2× (▁=0, ~▄=1.0×, █=≥2×), same window-selection code as the NTR spark | rendered for whatever live bars exist (same as NTR spark) |
| V4 | **Alert-day landmark** (EOD recap, not the alert) | alert-day EOD volume ÷ max pre-alert volume over min(252, available) sessions; fires at ≥1.0 with a depth-honest label | depth stated in the label; "1y" only at ≥252; "HVE" only via the Polygon fetch (Slice 2) |

**DROP — measured, didn't earn a segment:**

- *Fresh 1y-high volume day inside the last 20 pre-alert sessions* — fired on 16/210 (7.6%),
  fwd_1w median −3.0% vs +0.5% (weak, small n, wrong sign for a "landmark = good" display). Cut.
- *Alert-day vol ÷ 50d as a number* — redundant with the existing RVOL/intensity (20d base);
  terciles showed no separation (med1w +1.4 / +0.1 / −0.7, no pattern worth a token). Cut.
- *r1_50 (yesterday only ÷ 50d)* — same story as r5_50 but noisier; near-duplicate. Cut.

Lineage note: 50d volume MA is the standard volume-profile base in the Qullamaggie/Bonde
tradition; HVE / highest-vol-in-1y are Stockbee (Bonde) landmark-day concepts — a
highest-volume-ever/1y day marks an institutional participation event. Nothing here is invented;
the only adaptation is honest depth-labelling given a 13-month store.

## 4. Measurements — the full live EP-alert cohort

Cohort: **224** deduped live alerts (2026-04-27 → 2026-07-27; 152 HIGH / 67 MODERATE / 6 none;
90-day `mi_ep_alerts` retention bounds it). **221 computable** (≥50 pre-alert live bars).
Outcomes joined from `mi_signal_outcomes`: fwd_1w on 213, fwd_1m on 191. Pipeline sanity: QBTS
reproduces the operator's hand-read (22 sessions / 1.28×).

### V1 r5_50 — recent participation vs 50d base

Distribution: p5 0.65 · p25 0.84 · **p50 1.05** · p75 1.33 · p95 1.94. QBTS 7/27 = 0.46
(percentile 0). Orthogonal to what the alert already shows: corr vs gap_pct −0.01, vs ep_score
+0.02 — this is genuinely new information on the alert, not a re-render of the score.

```
HIGH tier (n=142 with fwd_1w)     med1w   win1w  ≥+10%1w  med1m
 r5_50 ≤0.89  (quiet base)        +2.0%    58%     20%    −1.7%
 0.89–1.21    (normal)            +2.4%    62%     28%    +8.0%
 >1.21        (already hot)       −2.6%    44%     14%    −0.2%
```

The one directional finding of the study: **alerts on an already-hot tape underperform** (hot
tercile vs rest, fwd_1w Mann-Whitney p=0.028 HIGH-only, p=0.048 all-tier). The classic EP logic
holds in the data — surprise out of neglect beats piling onto a crowded tape. Honesty caveat:
~15 comparisons were run in this study; nominal p≈0.03–0.05 does **not** survive a multiplicity
correction. This is telemetry-grade direction, **not** gate-grade evidence — which is fine,
because the card is display-first.

Note the polarity: the naive reading of QBTS ("volume dried up = warning") is NOT what the cohort
shows as a general rule — dry/normal bases *outperform* at 1w. What distinguishes QBTS is the
**divergence**: dry volume + wide range. Measured directly:

```
r5_50 low tercile (dry), split by tape width (median pre-alert NTR vs cohort med 5.0%):
 dry + TIGHT  n=31   med1w +1.1%   ≥+10%1w  6%    med1m −2.8%
 dry + WIDE   n=36   med1w +2.0%   ≥+10%1w 31%    med1m −6.4%   ← QBTS class
```

Dry+wide is a **barbell**, not a death sentence: fattest 1-week right tail of any cell (31%) and
the worst 1-month median (−6.4%). The operator's "warning" read is right at the 1-month horizon;
at 1 week these are lottery tickets. n=36 — suggestive only. This is why the recommendation is to
show **both** axes side by side and let the operator read the pair, not to editorialize.

### V2 LAB50 — sessions since the last ≥50d-avg volume day

Distribution: p50 **0** · p75 1 · p90 6 · p95 12 · max 39. 83% of alerts had an above-average
volume day within 2 sessions (EP alerts fire on gaps that usually follow building volume), so the
segment renders only at ≥3 (18% of alerts) — same "no zero-noise" precedent as the TAPE line's
held/rev breakdown.

Outcome buckets (all-tier, n with fwd_1w): 0–2 → med −0.4% (n=175); 3–9 → −1.9% (n=24); 10–19 →
**+6.6%, 7/7 winners** (n=7: PCT +38.6, CLSK +14.4, VG +11.4, BW +6.6…); ≥20 (the QBTS profile) →
n=4 resolved, mixed (AEHR −15.5, DYN +3.4, IBRX −2.0, PHR +2.5). **No separation claim** —
the interesting buckets have n=7 and n=4. LAB50's value is that it is *the operator's own chart
read, computed exactly* (verified to the day and the ratio on QBTS), rare enough to be signal-shaped
when it appears, and honest context either way. Keep as display + accruing telemetry.

### V4 Alert-day landmark (EOD truth over 220 alerts)

`alert-day vol ≥ max(pre-alert vol, up to 252 sessions)` fired on **50/220 alerts (23%)**.

```
HIGH tier (n=142)                 med1d   med1w  ≥+10%1w  med1m
 landmark day (n=37)              +2.4%   +2.1%    30%    −1.4%
 0.5–1.0× of max (n=51)           −2.1%   −0.6%    12%    +3.0%
 <0.5× (n=54)                     +0.8%   +2.0%    22%    +2.6%
```

The landmark **fattens the right tail** (≥+10%/1w: 30% vs 17% rest, z-p=0.10 HIGH; 26% vs 15%,
z-p=0.075 all-tier) without moving the median (MW p=0.55) — consistent with Bonde lore: a
highest-volume-day-in-history print is an institutional event that resolves big, both ways. Also
note the *middle* is the worst cell — big-but-not-landmark volume is the weakest class. Suggestive,
not significant; worth displaying as fact ("#1 vol day in Xmo"), not as a recommendation.

Timing constraint: **128/196 alerts fire pre-9:45** — before the existing intensity-projection
gate, where an "on pace for #1" claim would be premarket noise. So v1 puts the landmark verdict in
the **EOD EP recap** (16:xx chain), where EOD volume is exact. An alert-time "on pace" segment for
post-9:45 alerts can reuse the intensity projection discipline later if wanted.

## 5. Proposed render (Telegram, monospace, no pipe tables)

**EP alert — one new line + one new sparkline row**, adjacent to the existing TAPE block
(`briefing.py` `send_ep_alert`; both sparklines gain a 4-char label so two rows stay readable):

```
TAPE: clean · 0 spikes · 2nd-widest 1.4× · ADR 6.6%
VOL: 5d avg 0.46× of 50d · last ≥avg vol day 22 sess ago (1.3×)
NTR ▆▅▄▄█▄▇▄▂▆▄▁▆▅▆▃▃▁▄▃
VOL ▄▃▃▃▃▃▃▂▂▂▃▂▂▃▃▂▃▂▂▂
```

— that is QBTS 7/27, real data. The two rows are column-aligned per session; the divergence
(range lively, volume flat-low, everything under the ▄ midline = below-average) is visible at a
glance. Contrast, ABSI 6/24 (fwd_1w +10.3%):

```
VOL: 5d avg 1.31× of 50d
NTR ▁▁▆█▁▁▃█▅▁▃▅▂▃▅▂▄▁▄▄
VOL ▃▃▇█▅▄▅█▅▃▄▅▄▄▆▄▆▇▇▅
```

Segment rules: LAB50 segment only when ≥3 sessions (18% of alerts); `unseasoned` render when
<50 live bars (3/224); VOL spark fixed-scaled 0→2× (▄≈1.0× — cross-ticker comparable, unlike the
min-max NTR spark, which stays exactly as validated).

**EOD EP recap — landmark line, when it fires (23% of alerts).** Real case, ABSI 6/24
(252 pre-alert sessions — earns the "1y" label; went +10.3% the next week):

```
ABSI  vol 38.1M — #1 vol day in 1y (1.6× prior max, 7.4× 50d avg)
```

("1y" only at ≥252 sessions, else the actual depth — "#1 in 10mo"; "HVE / highest ever" only
once Slice 2's Polygon fetch confirms it.)

### Relationship to the existing sparkline — recommendation

**Add a second, labeled sparkline; change nothing about the first.** The NTR spark + the 20-window
tape metrics were validated at `_WIN = 20` (`tape_quality.py:61`) — that constant is shared and
stays untouched. The VOL spark uses its own display constant (`_VOL_SPARK_WIN = 20`, deliberately
equal so the rows column-align; decoupled so neither can silently move the other). Numeric-only
was considered and rejected: the QBTS failure mode is a *divergence between two time series*, and
a single number can't show co-movement — the aligned pair is the actual deliverable.

## 6. Cost + first slice

**Slice 1 — cheap (display + telemetry, no new data source):**
- Bars: already fetched — `get_tape_bars_asof` (db.py:8515) pulls 380 days for TQS; the VOL
  metrics compute from the same rows in the same annotator pass. **Zero new queries.**
- Code: a sibling of `tape_quality.annotate_ep_alerts_tape_quality` (or an extension of it),
  `format_vol_line`, the fixed-scale spark, the EOD-recap landmark line.
- Telemetry: mirror the `tape_*` pattern — `vol_r5_50, vol_lab50, vol_lab50_ratio, vol_hist_n,
  vol_alert_vs_max` columns on `mi_ep_alerts`, SET-clause pinned to `vol_*` only (same THE-LINE
  contract as `update_ep_alert_tape_quality`, db.py:2807). This is what turns today's N≈220 into
  N≈450 by late October for any future CHANGE_PROCESS case.
- No new tables, no schema beyond columns, no Polygon calls.

**Slice 2 — true HVE/HV1y (small):** on-alert Polygon fetch via the existing per-ticker daily-aggs
helper (`collector.py:469`), ~2004→today, one call per alerted ticker (~3.5/day), cached in a
small `mi_vol_landmarks` row (ticker, hve_vol, hve_date, hv1y_vol, fetched_at); on fetch failure
the label falls back to the depth-honest DB form. This is the only path to saying "HVE" truthfully.

**Not proposed:** extending `mi_daily_closes` retention for HVE (~70M rows), widening `_WIN`,
touching RVOL/intensity, or any read of `vol_*` by grading/entry/sizing.

## 7. Open questions for the operator (1-line recs)

1. **Second sparkline vs numeric-only?** — Rec: second spark, fixed 0–2× scale, labeled rows;
   the QBTS read is a divergence and needs both series visible.
2. **Landmark verdict at alert time or EOD recap only?** — Rec: EOD recap only in v1 — 65% of
   alerts fire pre-9:45 where "on pace" would be premarket noise.
3. **Ship Slice 2 (Polygon true-HVE) with Slice 1 or later?** — Rec: with Slice 1 — one API call
   per alert, and it's the difference between "HVE" and a hedged 13-month label.
4. **Should hot-tape (r5_50 > ~1.2×) ever feed the grade?** — Rec: not now — nominal p≈0.03 dies
   under multiplicity at N≈210; let the `vol_*` telemetry accrue (~+220 alerts by late Oct) and
   bring it back through CHANGE_PROCESS if it holds.
5. **Is `VOL:` the right label next to `TAPE:`?** — Rec: yes; plain words per the 7/24 TAPE-line
   readability ruling ("5d avg 0.46× of 50d", "22 sess ago" — no bare metric names).

## Appendix — provenance

Prod reads (SELECT-only): `mi_ep_alerts` (live source, DISTINCT ON ticker+alert_date — the
`get_ep_outcomes` dedup), `mi_signal_outcomes` (signal_type='ep_alert'), `mi_daily_closes` (full
history for the 219 cohort tickers, 56.6k rows). Analysis scripts + per-alert metric dump
(vp_measure.py, vp_sig.py, vp_render.py, vp_metrics.tsv) in the session scratchpad; the per-alert
TSV can be re-derived from the two extracts deterministically. QBTS ratio-convention note: the
operator's 0.58–0.77× band divides each day by the *current* 50d SMA; this doc divides by the
as-of-that-day SMA (chart-overlay convention) giving 0.42–0.51× — both conventions agree on the
read (far below average); the display uses the chart-overlay convention and says so here once.
