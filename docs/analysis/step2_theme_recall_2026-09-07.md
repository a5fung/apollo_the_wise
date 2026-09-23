# Step 2 — RECALL: are the themeless EP alerts blind spots of the theme engine? (2026-09-07)

**Read-only, $0, nothing changed.** Judged on relative strength only — never on trade returns
(operator ruling). Probe: `scripts/probes/_step2_theme_recall.py`; every number below is in
`scripts/probes/_step2_theme_recall_out.txt`, one row per subject in `_step2_theme_recall_rows.tsv`.
Data: prod exports frozen 2026-09-07 (`_step2_*.tsv`, captured once, git-ignored) plus step 1's
frozen RS / theme exports. Plan: `~/.claude/plans/plan-this-out-with-hidden-bentley.md` §2. Step 1's
helpers (calendar, open-gap read, the down-day hold leg, the velocity / turner mirrors) are imported
from `_step1_theme_precision.py`, not rewritten. **Grind and co-gap are reported separately
everywhere**; a blended number would be a failed analysis.

**The bar was ruled by the operator on 2026-09-07 and is not re-opened here:** G1 (subtle strength
among industry peers) is the recall bar; G2 (residual correlation ≥ 0.85) is not, and is retained
only as a membership check (§9).

## Method — population, window, and how each set was derived

**The decision this serves.** 82% of EP alerts carry no theme. Is that because the market was
genuinely themeless around them, or because the engine is blind to groups that were there? The
answer decides whether recall work (widening discovery) is worth doing.

**What would change the decision — declared before the probe ran (plan §2):** grind rate on themeless
alerts minus grind rate on the sub-bar controls ≥ 15 points, at grind ≥ 30% → the engine is blind.
Grind < 10% → the themeless names are genuinely themeless. 10–30%, or a margin under 15 points → no
verdict from the number alone. Co-gap large but grind small → themes are downstream of EPs (Lane 2).

**Alert population.** `mi_theme_axis_shadow`, **all 592 rows**, `alert_date` 2026-03-24 → 2026-09-04:
every scored HIGH/MODERATE survivor the shadow captured (HIGH-only before 2026-07-13; MODERATE has not
existed live since 2026-08-22 — 567 HIGH / 25 MODERATE). This is used instead of `mi_ep_alerts`
because that table starts 2026-05-11 and is missing 254 of the shadow's rows (236 of them before
2026-05-08). "Themeless" is **recomputed** from `mi_themes` with one uniform anchor (alert_date − 1,
the newest theme snapshot that existed on the morning of the alert; `get_theme_heat_asof`'s exact
predicate) and compared to the stored flag (§1). The headline uses alerts dated ≥ 2026-04-13 so that a
control exists for every alert.

**Control population — the sub-bar names.** Every `mi_ep_scan_log` (scan_date, ticker) whose LAST
state that day (`ORDER BY scan_time_et DESC NULLS LAST, id DESC`, the table's canonical collapse) is a
reject stage past the gap floor: `db.UNSCORED_THEME_AXIS_REJECT_STAGES` = shortlist_cap, rvol_gate,
cooldown, extension, quality_filter, post_grade_filter, score_bar. Pre-2026-08-31 rows carry no
`reject_stage`; their free-text `filter_reason` is mapped by the shipped
`theme_axis_shadow.effective_reject_stage` (unmatched tail: **0**). universe_floor, gap_floor and
duplicate are excluded. This is the probe's own read-only derivation of the same population step 4's
recorder writes — the recorder and its backfill are built and committed but **await deploy**, so the
control here is not the recorder's stored rows. The derivation reproduces the backfill's own count
exactly (**2,708 ticker-days**, 2026-04-13 → 2026-09-04, 1,502 tickers). **199 of those are the same
(ticker, day) as an alert row** — scored HIGH at one scan, killed at a later one — which the recorder's
`ON CONFLICT DO NOTHING` would skip; the **pure control used throughout is 2,509 ticker-days**, of
which 2,122 (84.6%) are themeless on the same anchor.

**The measure, per (ticker, date), as of date − 1, no engine involvement.** Peers = other names with
the same `mi_ticker_overrides.industry` (sector fallback from `mi_stock_scores.sector` when the subject
has no industry — reported on its own line, never blended). Per peer: **rising** = the
`db.get_rs_velocity` row predicate (front-weighted 4-week RS acceleration, last week rising, RS ≥ 50);
**turning** = the `db.get_rs_turners` predicate; **holding up** = the new leg — median of (name − SPY)
daily return on the SPY-down sessions of the 20 sessions ending date − 1, > 0 = held up better. RS
snapshots resolve exactly as `db._resolve_weekly_snapshots`. **G1** = ≥ 3 peers with any subtle leg.
**Level** = ≥ 3 peers with RS ≥ 70 (`ASSIGN_POOL_RS_FLOOR`). **Grind** = ≥ 3 subtly-strong peers that
did NOT gap (open / prior close − 1 ≥ 9%, `_MIN_GAP_PCT_DEFAULT`, the uniform read step 1 validated at
91.8% against the scan log) in those 20 sessions; **co-gap** = G1 but not grind. **G3** = ≥ 2 other
same-industry names in the scan log the same day (same-day co-gap). **Strict** = the engine's actual
nightly top-30 velocity / top-30 turner pools instead of the row predicate.

**Coverage, stated before any cohort number.** `mi_ticker_overrides` has 2,885 rows, 2,430 with an
industry (84.2%; 137 industries; median industry 11 members, p90 32, max 251). **Alert tickers with an
industry: 379 of 491 (77.2%). Control tickers: 997 of 1,502 (66.4%).** Sector coverage is identical to
industry coverage (both columns are populated together), and `mi_stock_scores.sector` exists only on
top-300-by-rank rows — so the sector fallback reached **one** subject in 3,101. Every rate below is
over industry-covered subjects; uncomputable ones (< 3 data-bearing peers) are listed, not hidden.
The covered subsets are not random halves: a name is in `mi_ticker_overrides` because something
(theme engine, EP scan) once looked it up.

**Era.** The scan log's gap floor moved 8% (Apr 13–May) → 10% (Jun–Jul) → 9% with 5% capture (Aug),
and the EP cutline changed 2026-08-22. Tagged in §6, never used as a cut.

**Nothing was tuned.** Every threshold is one the system already owns or the plan fixed in advance
(≥ 3 peers = `_PROMOTE_MIN_MEMBERS`; ≥ 2 same-day = plan G3; RS 70; gap 9%; 20 sessions). Where a
constant turned out to mean something other than what the plan assumed, that is reported as a finding
(§3, §10) — no constant was moved, and agreement with the operator's labels is reported, not fitted.

⚖ **THE LINE.** Read-only evidence. No detection criterion, grade, alert, entry, exit, sizing or
safeguard was changed or proposed as changed. The one open question at the end is the operator's
ruling, not a recommendation acted on.

## The answer

- **No verdict from the pre-declared number — and the reason is the instrument, not the market.**
  G1 as ruled ("≥ 3 industry peers subtly strong") fires on **299 of 321 themeless alerts (93.1%)**,
  on **1,299 of 1,401 themeless names that never alerted (92.7%)**, and on **99 of 108 alerts the
  engine DID theme (91.7%)**. Grind: **295 of 321 (91.9%) vs 1,279 of 1,401 (91.3%) — margin +0.6
  points**. The bar needs ≥ 15; it cannot be crossed in either direction because the read is
  saturated: with a median 29–30 data-bearing peers and 29% of names rising / 44% holding up on any
  day, three strong peers exist by arithmetic in every industry above ~10 names (§3, §4 size buckets).
- **The grind / co-gap CLASS collapses to "grind" by the same arithmetic** (a 30-peer industry
  almost always has 3 un-gapped strong names, so the class reads grind 295 of 321 / co-gap 4 whatever
  the gapped count is) — so the reflexivity read has to be continuous. **Share of a subject's strong
  peers that had gapped ≥ 9% in the prior month: themeless alerts median 14% (p75 24%), never-alerted
  controls 11% (p75 20%), engine-themed alerts 13%, his yes-labels 24%, his no-labels 11%** (§8).
  Read plainly: about one strong peer in seven around a themeless alert is an echo of an earlier gap,
  one in nine around a name that never alerted, one in four around the names he labelled real —
  reflexivity is present and measurable, and it is heaviest exactly where he sees themes. Same-day
  co-gap is the same on both sides (G3 33.3% vs 32.1%; uniform open-gap read 18.7% vs 17.8%), so the
  "themes are downstream of EPs" bar is not crossed by alerts co-gapping more than non-alerts.
  **§11 tests the 24%-vs-11% gap:** it is not the calendar (same-date controls stay at 11%), but it
  is industry mix — within the same industry his no-labels read the same as his yes-labels (0 of 3
  pairs separate) — so at 18 yes-cells it cannot be settled as a recall signal.
- **Threshold-free, the populations are indistinguishable (§8).** Share of peers subtly strong and
  un-gapped: themeless alerts median **46%**, never-alerted controls **47%**, engine-themed alerts
  **47%**, his yes-labels **50%**, his no-labels **53%**. A measure that cannot separate the engine's
  own themed alerts from names that never alerted is not a recall instrument in this tape.
- **Agreement with his 31 labels: G1 fires on 21 of 21 of his yes-rows — and on 6 of his 7 no-rows**
  (28 of 31 covered; agreement 22 of 28 = 78.6%). His no-rows sit in the same industries on the same
  days as his yes-rows (PI vs NXPI/SIMO in Semiconductors, BAND/PAY vs FIVN/TWLO/BB in Software —
  Infrastructure, TTMI vs OUST/FLEX in Electronic Components). **His labels judge whether the NAME
  belongs to the group — the membership job G2 was kept for — not whether a group existed.** The
  plain RS ≥ 70 cut agrees 19 of 28 (67.9%); G1 − level on alerts is +7.8 points, which is what a level
  gate misses, but both are saturated.
- **What the number does settle:** the "82%" is real on every denominator (stored 481/592 = 81.2%;
  recomputed 484/592 = 81.8%; 7-day bounded 520/592 = 87.8%; not in an Accelerating/Mainstream theme
  93.4%; live `in_active_theme` true on 25 of 424 = 5.9%). And the market around those alerts was
  **not** themeless in the sense of absent peer strength — it was broadly strong, which is the
  opposite of a theme signal. Whether recall should be measured against a bar relative to the industry
  (share, or the engine's own top-30 pools — §4 "strict": 19.6% vs 17.9%) is the operator's to set;
  nothing was moved here.

## 1. The alert population and its four themeless denominators (n = 592)

| denominator | definition | themeless |
|---|---|---|
| D1 stored | `mi_theme_axis_shadow.themeless_flag` as written (unbounded read) | 481 / 592 = 81.2% |
| D1′ recomputed | same read, one anchor for every row (alert_date − 1) — **used below** | 484 / 592 = 81.8% |
| D2 | 7-day bounded, any stage (anchor − 6) | 520 / 592 = 87.8% |
| D3 | no Accelerating/Mainstream theme within 7 days = the live `in_active_theme` definition | 553 / 592 = 93.4% |
| D4 | `mi_ep_alerts.in_active_theme` (n = 424 rows; 333 non-NULL) | true 25 → 94.1% / 92.5% themeless |

- Stored vs recomputed disagree on **3 of 592**: POET 05-14, ALAB 05-20, GFS 05-21 — each joined its
  theme **on the alert day itself** (the stored row was backfilled with the alert day's own evening
  snapshot visible). The uniform anchor is the correct as-of; the disagreement is the Lane-2 case, not
  a flag defect.
- By era (alerts / themeless): before 04-13 50/47 · Apr13–May 357/322 · Jun–Jul 87/58 · Aug 1–21 88/54
  · Aug 22+ 10/3. Shadow rows absent from `mi_ep_alerts`: 254; `mi_ep_alerts` rows absent from the
  shadow: 40.
- Scan-log last state of the 542 alert rows dated ≥ 04-13: duplicate 207 · **no scan-log row 84** ·
  alert-final 54 · a reject stage 196 · gap_floor 1. The 84 are Apr 13 → Jun 5 rows (24 / 51 / 9 by
  month): 37 carry `source = historical_scan` in `mi_ep_alerts`, 43 have no `mi_ep_alerts` row at all,
  4 are `live` — backfilled / historical shadow rows from the scan log's first weeks, not a live hole.

## 2. The control — sub-bar names (probe's derivation; recorder awaits deploy)

| stage (last state that day) | derived | pure (not an alert row) |
|---|---|---|
| shortlist_cap | 791 | 746 |
| quality_filter | 595 | 562 |
| rvol_gate | 368 | 324 |
| score_bar | 331 | 290 |
| post_grade_filter | 323 | 303 |
| extension | 182 | 175 |
| cooldown | 118 | 109 |
| **total** | **2,708** (= the backfill's count) | **2,509** |

- 53,432 scan-log rows collapse to 5,118 last states; unmatched free-text tail 0.
- Pure-control themeless (same anchor): 2,122 of 2,509 (84.6%) — the same rate as the alerts, so a
  themed/themeless split is not a property of alerting.
- **One command later:** `python3 scripts/probes/_step2_theme_recall.py --control-source shadow`
  reads the deployed recorder's `source='eod_unscored'` rows (pull with
  `scripts/probes/_step2_x_shadow_unscored.sql`) and diffs them against this derivation — row set,
  stage and themeless flag. That diff is also the recorder's fidelity check.

## 3. Why an absolute "≥ 3 peers" bar saturates — the peer-level base rates

Over the **68,836 (peer, date) evaluations** the probe made: 80.4% had an RS row; of those, **44.4% sat
at RS ≥ 70, 29.4% were rising, 1.3% turning**; of 64,307 with computable holds, **43.9% held up better
than SPY** on the prior month's down days. `mi_stock_scores` keeps ~3,600 rows a day of a ~9,700
universe (29.9% of kept rows ≥ 70), and the peer pool is stronger still because overrides names were
looked up by the engine. With those rates, three strong names among 30 is near-certain: G1 fires 53% /
63% (alerts / controls) in industries under 10 data-bearing peers, **97% / 97%** at 10–30, **99% /
97%** above 30. The bar was not moved; this is what the constant means in this tape.

## 4. Headline — themeless alerts (≥ 04-13) vs themeless pure controls

| read (as of date − 1) | themeless alerts (n = 321 covered of 437) | themeless controls (n = 1,401 covered of 2,122) | margin |
|---|---|---|---|
| uncomputable (< 3 data-bearing peers) | 3 | 8 | |
| **G1** subtle ≥ 3 peers | 299 = 93.1% | 1,299 = 92.7% | +0.4 |
| **GRIND** ≥ 3 strong, no gap in window | **295 = 91.9%** | **1,279 = 91.3%** | **+0.6** |
| co-gap via window-gapped peers | 4 = 1.2% | 20 = 1.4% | −0.2 |
| G3 same-day co-gap (scan log ≥ 2) | 107 = 33.3% | 450 = 32.1% | +1.2 |
| same-day co-gap, uniform open-gap read (≥ 2 peers gapped ≥ 9% that day) | 60 = 18.7% | 249 = 17.8% | +0.9 |
| co-gap class (window or same-day, not grind) | 4 = 1.2% | 56 = 4.0% | −2.8 |
| LEVEL RS ≥ 70 ≥ 3 peers | 274 = 85.4% | 1,169 = 83.4% | +2.0 |
| level-grind (no gap) | 262 = 81.6% | 1,122 = 80.1% | +1.5 |
| rising / turning only ≥ 3 | 260 = 81.0% | 1,087 = 77.6% | +3.4 |
| hold-up leg only ≥ 3 | 285 = 88.8% | 1,226 = 87.5% | +1.3 |
| STRICT: ≥ 3 peers in the engine's top-30 pools | 63 = 19.6% | 251 = 17.9% | +1.7 |
| strict-grind | 31 = 9.7% | 146 = 10.4% | −0.7 |
| class: grind / co-gap / none | 295 / 4 / 22 | 1,279 / 56 / 66 | |
| no industry at all (excluded from the rates) | 116 of 437 = 26.5% | 721 of 2,122 = 34.0% | |

- Pre-declared bar, covered denominators: **no verdict** (grind 91.9%, margin +0.6). Computable-only:
  92.8% vs 91.8%, margin +1.0 — same.
- G1 − LEVEL on alerts: **+7.8 points** — the share a level gate would miss. Both reads are saturated,
  so the gap is small by construction here (step 1 §4 measured it at +28 points on theme founders,
  where the population is selected).
- Of the 299 alert G1 fires, **39 fire only through the hold-up leg** (212 of 1,299 on controls).
  Median peer hold-up is **negative** on both sides (−0.32% / −0.19% per down day): most peers fell
  more than SPY on down days; the leg's "> 0" is the operator's definition and reads ~44% of names.
- All 2,509 controls (themed + themeless, 1,777 covered): G1 91.0%, grind 89.1%, G3 36.0%.

## 5. Same read on the other alert denominators (full window, n = 592)

| population | n | covered | G1 | grind | G3 same-day | level | strict |
|---|---|---|---|---|---|---|---|
| all shadow alerts | 592 | 460 (77.7%) | 425 = 92.4% | 418 = 90.9% | 153 = 33.3% | 397 = 86.3% | 86 = 18.7% |
| **themed** (engine named them) | 108 | 108 (100%) | 99 = 91.7% | 96 = 88.9% | 46 = 42.6% | 99 = 91.7% | 21 = 19.4% |
| 7-day themeless (D2) | 520 | 388 (74.6%) | 357 = 92.0% | 351 = 90.5% | 121 = 31.2% | 329 = 84.8% | 72 = 18.6% |
| not-active (D3) | 553 | 421 (76.1%) | 386 = 91.7% | 379 = 90.0% | 130 = 30.9% | 358 = 85.0% | 75 = 17.8% |

- Themed alerts are 100% industry-covered vs 74–78% for the rest — the coverage confound in one row:
  the engine's lookups are what populate the industry cache.
- Themed alerts co-gap the same day more (42.6% vs 33%) — consistent with Lane-2 seeding — but their
  peer-strength read is otherwise identical to the themeless rows.

## 6. Era and reject-stage cuts (tags, never cuts)

| era | themeless alerts n | G1 | grind | themeless controls n | G1 | grind |
|---|---|---|---|---|---|---|
| Apr 13–May 31 (floor 8%) | 225 | 92.0% | 90.2% | 719 | 93.6% | 92.1% |
| Jun–Jul (floor 10%) | 47 | 95.7% | 95.7% | 493 | 90.7% | 89.5% |
| Aug 1–21 (floor 9%, 5% capture) | 46 | 95.7% | 95.7% | 157 | 94.3% | 92.4% |
| Aug 22+ (cutline) | 3 | 100% | 100% | 32 | 96.9% | 96.9% |

Controls by stage (themeless, covered): shortlist_cap n = 399 G1 86.5% grind 84.7% co-gap 9.5% ·
quality_filter 317 / 94.3 / 93.1 / 1.6 · rvol_gate 178 / 96.1 / 93.8 / 2.8 · post_grade_filter 185 /
94.6 / 93.5 / 1.1 · score_bar 174 / 95.4 / 94.8 / 2.3 · extension 98 / 96.9 / 94.9 / 2.0 · cooldown 50
/ 96.0 / 96.0 / 0.0. The stage closest to the alerts (score_bar — scored, under the bar) reads 94.8%
grind; the only stage that co-gaps materially is shortlist_cap (names cut for gap rank on busy days).

## 7. Agreement with the operator's 31 labelled themeless-winner rows (22 yes / 9 no)

28 of 31 have an industry (uncovered: BBBY n, FTAI y, ISPC n). Reported, never tuned.

| read | his YES (n = 21): fires / silent | his NO (n = 7): fires / silent | agreement (n = 28) |
|---|---|---|---|
| G1 subtle (any leg) | 21 / 0 | 6 / 1 | 22 = 78.6% |
| G1 grind | 19 / 2 | 6 / 1 | 20 = 71.4% |
| co-gap class | 2 / 19 | 0 / 7 | 9 = 32.1% |
| LEVEL RS ≥ 70 | 18 / 3 | 6 / 1 | 19 = 67.9% |
| rising / turning only | 17 / 4 | 6 / 1 | 18 = 64.3% |
| STRICT top-30 pools | 4 / 17 | 1 / 6 | 10 = 35.7% |

- The one no-row G1 is silent on: GPK (Packaging & Containers, 2 strong of 11 peers). The other six
  no-rows have 7–61 strong peers — the same industries as his yes-rows on the same days.
- The two yes-rows grind misses: ICLR and NEO (Diagnostics & Research, 4 strong of 30, two gapped) —
  his note "Biotech related" names a broader group than the industry label.
- **Two limits, stated so they are not quietly used:** the 31 were selected on forward 5-day return ≥
  +5%, so 22-of-31 is an upper bound on a good day and not a recall rate (returns are ruled out of this
  work); and his notes are sector-level ("AI Semi", "Biotech related") while G1 is peer-level.

## 8. Threshold-free read — share of data-bearing peers subtly strong and un-gapped (no bar invented)

| population | n | strong & no-gap: p25 / median / p75 | rising/turning & no-gap | RS ≥ 70 & no-gap | **reflexivity: share of STRONG peers that gapped in the window** (p25 / median / p75) | peers gapping ON the day (median) |
|---|---|---|---|---|---|---|
| themeless alerts (≥ 04-13) | 318 | 31% / **46%** / 57% | 12 / 20 / 30 | 18 / 30 / 45 | 7% / **14%** / 24% (n = 316) | 0% |
| themeless pure controls | 1,393 | 32% / **47%** / 62% | 10 / 19 / 29 | 18 / 29 / 43 | 0% / **11%** / 20% (n = 1,363) | 0% |
| themed alerts (engine named them) | 107 | 29% / **47%** / 58% | 9 / 19 / 27 | 18 / 31 / 47 | 4% / **13%** / 29% (n = 106) | 2% |
| his 22 yes-labels | 21 | 18% / **50%** / 59% | 8 / 17 / 38 | 17 / 30 / 46 | 9% / **24%** / 31% (n = 21) | 1% |
| his 9 no-labels | 7 | 27% / **53%** / 69% | 14 / 31 / 44 | 23 / 37 / 59 | 0% / **11%** / 14% (n = 7) | 0% |

- On strength, every population sits at the same place; the strongest peer groups in the sample are
  his **no**-rows.
- On reflexivity the populations DO differ, modestly: one strong peer in seven around a themeless
  alert had gapped in the prior month, one in nine around a never-alerted name, one in four around his
  yes-labels (late-April / early-May biotech and semis, where EPs were dense: MANE 18 of 69 strong peers
  had gapped, NXPI 15 of 48, AVTX 21 of 88). This is the reflexive echo made measurable — and it is
  invisible to the class split, which reads all of these as "grind".

## 9. G2 in its one remaining role — membership

Not computed in this step: recall does not use it (operator ruling). Its membership finding from step
1 §6 stands unchanged — the two genuine membership errors are the two lowest fits of all nine (BATL
−0.13, KYTX 0.07). §7 above is the reason that role matters: his no-labels on themeless rows are
membership judgements too, and no peer-strength read can make them.

## 10. Things found false or unusable (flag, not fix)

1. **The plan's "≥ 3 peers" bar saturates above ~10 industry members** by arithmetic (§3) — and so
   does the grind / co-gap class built on it (≥ 3 un-gapped strong peers is nearly always true, so
   "co-gap" reads 1–4% however many strong peers gapped; the continuous share in §8 is the usable
   reflexivity read). The bar was inherited from `_PROMOTE_MIN_MEMBERS` (a theme needs 3 members),
   which is a floor on a cohort, not a test against an industry of 30–250. Not moved; reported.
1b. **The brief's "live flag reads ~4%"** measures 25 of 424 = 5.9% on `mi_ep_alerts.in_active_theme`
   (7.5% of the 333 non-NULL rows); 6.6% on the shadow's 7-day Accelerating/Mainstream read (39 of 592).
2. **A quarter of the themeless alerts cannot be measured at all:** 116 of 437 (26.5%) have no
   industry, and the sector fallback reaches none of them — `mi_ticker_overrides.sector` is populated
   only alongside `industry`, and `mi_stock_scores.sector` exists only on top-300 rows. 721 of 2,122
   controls (34.0%) likewise.
3. **199 of the backfill's 2,708 control ticker-days are the same (ticker, day) as an alert row** —
   scored HIGH at one scan, killed at a later scan. The recorder's `ON CONFLICT DO NOTHING` would skip
   them, so the deployed control will be ~2,509, not 2,708. The `--control-source shadow` diff will
   confirm.
4. **The stored `themeless_flag` disagrees with a uniform as-of read on 3 rows** (POET, ALAB, GFS),
   each a name that joined a theme on its alert day — the backfilled read saw that evening's snapshot.
5. **84 of the 542 shadow alert rows dated ≥ 04-13 have no scan-log row** for that (ticker, day) —
   historical / backfilled rows from Apr 13 – Jun 5 (§1), so a scan-log join undercounts alerts in
   that era on top of the `mi_ep_alerts` gap the brief already names.
6. **The hold-up leg's "> 0" reads 44% of all names** and the median peer held up *worse* than SPY —
   it is the operator's definition, not a calibrated threshold; it carries 39 of 299 alert G1 fires on
   its own.
7. Verified true, no change: the derivation reproduces the backfill's 2,708 exactly; the legacy
   `filter_reason` classifier leaves an unmatched tail of 0; `mi_themes.score` is never used as
   evidence of movement; every read is as of date − 1 with no engine call.

## What this does not answer

- **Whether the engine is blind.** The ruled instrument cannot separate blind from broadly-strong,
  and it cannot separate the engine's own themed alerts from names that never alerted — so this step
  neither confirms nor clears the engine. A bar relative to the industry (share of peers, or rank in
  the engine's own pools) would be a different instrument; whether to adopt one is the operator's
  ruling, not this document's.
- **The 26.5% of themeless alerts with no industry** — unmeasured, not "no".
- **The control is the probe's derivation, not the recorder's rows.** The recorder awaits deploy; its
  rows may differ (the 199-row overlap, any live-vs-backfill drift). Rerun with
  `--control-source shadow` once it lands.
- **Coverage is not random:** industry-covered alerts (77%) and controls (66%) are the names some
  engine already looked up; the comparison is on those subsets only.
- **Whether an earlier theme would have been worth anything** — that is step 3 (runway), not recall.
- **Returns.** Nothing here is judged on a trade outcome; the 31 labels' +5% selection is the only
  place a return touches the population, and it is flagged where it does.

## 11. Follow-up — is the 24%-vs-11% reflexivity gap the calendar, the industry, or the label?

Asked after the first read (coordinator, 2026-09-07): his 31 labels come from one fortnight
(2026-04-27 → 05-06), and the examples carrying the 24% are late-April biotech and semis — so the gap
might be a property of that fortnight, with the control diluted by five quieter months. Checked from
the probe's own rows, nothing re-measured: `scripts/probes/_step2_reflexivity_datematch.py` →
`_step2_reflexivity_datematch_out.txt`. **The measure is a property of the (industry, date) cell, not
the name** — it is computed on the subject's industry peers as of date − 1, so NXPI and SIMO (same
day, same industry) carry the identical 15 of 48. Every comparison is therefore shown per labelled row
AND per distinct cell, and a same-date same-industry control is equal to the label by construction.

| population (share of strong peers that gapped in the prior month) | rows: p25 / median / p75 (n) | cells: median (n) |
|---|---|---|
| his yes-labels | 9% / **24%** / 31% (n = 21) | **24%** (n = 18) |
| his no-labels | 0% / **11%** / 14% (n = 7) | **11%** (n = 7) |
| themeless controls, **same 8 sessions** | 0% / 13% / 25% (n = 229) | **11%** (n = 150) |
| themeless controls, ± 1 week (04-20 → 05-13) | — | 12% (n = 314) |
| themeless alerts, same sessions, excluding the 31 | 0% / 16% / 25% (n = 31) | 12% (n = 28) |
| themeless controls, whole span (§8) | 0% / 11% / 20% (n = 1,363) | — |
| his yes-labels without MANE, NXPI, AVTX | 9% / **18%** / 33% (n = 18) | 18% (n = 16) |

- **The calendar is not the explanation.** Same-date control cells sit at **11%** (n = 150), the
  same as the whole-span 11%; his yes-cells at 24% are above the same-date control p75 (20%). Nor was
  the fortnight unusually dense: control-cell medians by week were 8% (w/o 04-27) and 14% (w/o 05-04),
  while mid-May ran **19–20%** and July ~0%. Paired by day, **13 of 21 yes-rows sit above their
  same-day control median** (6 below, 2 tie; median +11 points); no-rows 4 above / 3 below (+1 point).
- **But it does not survive the within-industry test — 0 of 3.** In the three industries that carry
  both labels, his no's read the same as his yes's: Semiconductors — PI (no, 04-30) **34%** vs
  NXPI/SIMO (yes, 04-29) 31%; Software – Infrastructure — BAND 5% / PAY 11% (no) vs FIVN/TWLO 9% /
  BB 11% (yes); Electronic Components — TTMI 12% (no) vs OUST 8% / FLEX 9% (yes). The pooled 24-vs-11
  is **industry mix**: his yes-rows are biotech / med-devices / diagnostics (median 26%, n = 9) and
  semis / hardware (31%, n = 5); his no-rows are auto dealers, packaging, restaurants (0%, 0%, 14%) and
  software (5%, 11%) — and his software **yes**-rows are just as low (8–11%, n = 4).
- **What is left is an industry-level reading, on a sample too small to call:** the industries where
  he named a theme were the ones where roughly a quarter of the strong peers had gapped in the prior
  month (biotech 04-27: 26% vs a same-day control median of 3%; semis 04-29: 31% vs 6%), and that is
  his own mechanism — a theme announcing itself through a cluster of peer gaps. It says "a gapped
  cluster exists in this industry", never "this name belongs to it" — the same G1-vs-G2 division as §7.
  At 18 yes-cells (9 of them one family), 7 no-cells and 3 within-industry pairs, **this cannot be
  settled as a recall signal**; it is a candidate to re-test when the deployed recorder and more
  labels exist, not a finding.

## Files

- `scripts/probes/_step2_reflexivity_datematch.py` → `_step2_reflexivity_datematch_out.txt` — the §11
  follow-up (reads the rows file only).
- `scripts/probes/_step2_theme_recall.py` — the probe (read-only; imports step 1's helpers, the
  shipped `effective_reject_stage`, and `UNSCORED_THEME_AXIS_REJECT_STAGES`).
- `scripts/probes/_step2_theme_recall_out.txt` · `_rows.tsv` — outputs (one row per subject, 3,101 +
  31 labelled).
- `scripts/probes/_step2_x_{shadow,alerts,overrides,scan,closes}.sql` → `_step2_*.tsv` — frozen
  exports 2026-09-07 (~23 MB, git-ignored); `_step2_x_census.sql` / `_step2_census_out.txt` — the
  one-shot census; `_step2_x_shadow_unscored.sql` — the future control pull.
