# Step 1 — PRECISION: when the engine names a theme, is it real? (2026-09-07)

**Read-only, $0, nothing changed.** Judged on relative strength and price coherence only — never on
trade returns (operator ruling). Probe: `scripts/probes/_step1_theme_precision.py`; every number
below is in `scripts/probes/_step1_theme_precision_out.txt`, per-lineage rows in
`_step1_theme_precision_lineages.tsv`, per-founder rows in `_step1_theme_precision_founders.tsv`.
Data: prod exports frozen 2026-09-07 (`_step1_*.tsv`, captured once). Plan:
`~/.claude/plans/plan-this-out-with-hidden-bentley.md` §1. Grind and co-gap are reported
**separately everywhere**; a blended number would be a failed analysis.

## Method — population, era, and how it was derived

**The decision this serves.** Whether the theme engine names real themes, judged only on relative
strength and price behaviour. The operator's framing: *"getting themes right and returns are separate
things for now. We have to get themes right, but we haven't yet perfected trading system yet to meet
returns."* And his definition of a real theme: *"it shows up in the strongest names first."*

**Population.** Every theme in `mi_themes` — **513 distinct names**, all rows, `theme_date`
2025-12-02 → 2026-09-04 — collapsed into **398 lineages** by rename (`mi_theme_renames`, 2 rows),
Jaccard ≥ 0.4 on member sets, and the #534 rebirth rule (≥50% overlap with a later theme within 14
days). The lineage, not the name-day row, is the unit of analysis throughout.

**Windows.** Coherence is measured over the 20 trading sessions ending birth − 1 (pre) and the 20
after (post), from `mi_daily_closes`. Founder strength is read from `mi_stock_scores` (135 daily RS
snapshots). Birth class comes from `mi_ep_scan_log`, which starts **2026-04-13** — so births before
that date are classified from the open-gap in `mi_daily_closes` instead (91.8% agreement where both
are available), and that substitution is what the co-gap count rests on for the earlier era.

**Era.** The scan log's gap floor moved 8% → 10% → 5% across the window, and the EP scoring cutline
changed 2026-08-22. Neither is used as a cut here; both are recorded because they bound how
comparable the early and late births are.

**Exclusions, and what they cost.** The engine's own coherence helper returns nothing under 4
founders (`_MIN_CLUSTER_SIZE`), and **233 of 398 lineages are born with 2-3 members** — so the native
coherence panel speaks for 165 lineages, not 398, and every coherence figure below carries which
panel it came from. Absorbed lineages are a **floor**, not a count: retirement tombstones only exist
from 2026-05-26.

**Nothing was tuned.** Every threshold is a constant the system already owns (`_MEAN_CORR_MIN` 0.80,
`_CORR_THRESHOLD` 0.85, `ASSIGN_POOL_RS_FLOOR` 70, `_PROMOTE_MIN_MEMBERS` 3), and the pass/fail bars
were fixed in the plan before the probe ran. Where a constant turned out to mean something other than
what the plan assumed, that is reported as a finding — no constant was moved.

⚖ **THE LINE.** This is read-only evidence. No detection criterion, grade, alert, entry, exit,
sizing or safeguard was changed or proposed as changed. The two open questions at the end are the
operator's rulings, not recommendations acted on.

## The answer

- **Bar A is crossed under the pre-declared definition: 73 of the 147 grind-born themes that never
  matured and could be classified (49.7%) dissolved** — the pre-declared reading is "discovery mints
  noise; the birth bar is the defect". Bar B (churn ≥60%) is not crossed: churn is **70 of 147
  (47.6%)** (absorbed 45, reborn 13, killed-healthy 12).
- **That verdict rests on one arm of the definition.** Only **48 of 147 (32.7%)** dissolved because
  members' RS actually fell under 50 — under the bar. The other 25 count as dissolved solely because
  coherence slipped below its pre-birth level, and 16 of those 25 still had mean RS ≥70 at death.
  Post-birth coherence sits below pre-birth in **62% of all readable lineages, including 63% of the
  ones that matured** (155 of 249; post-birth used as the proxy since maturers have no death) — as
  written, that arm barely separates noise from real. **Whether a coherence slip counts is the
  operator's ruling**; both readings are reported, neither was chosen here.
- **With subtle-healthy folded in** (the operator's scope addition: healthy at death = coherence held
  and ≥half the members rising / turning / holding up, at any RS level) churn rises to **81 of 147
  (55.1%)** and dissolved falls to **66 (44.9%)** — Bar A still crossed, Bar B still not. Eleven
  grind lineages move (7 from "RS <50", 4 from the undefined RS-50–70 bucket).
- **Plain reading: about a third of grind-born non-maturers are genuine noise; about half are
  lifecycle churn.** Precision is middling, not broken.
- **The engine's own coherence bar (0.80) is not a theme-reality bar.** Of the operator's 47
  yes-labelled themed alerts, **1** sits in a cohort ≥0.80; his real themes have median coherence
  **0.36**. And **233 of 398 lineages (58.5%) are born with fewer founders than the engine's own
  instrument can read** (`_MIN_CLUSTER_SIZE` = 4; themes are born at 2). Both are the "constant
  looks wrong → report" case; neither was moved.
- **Subtle RS changes the strength read materially:** 374 of 1,185 grind founders (31.6%) are
  rising / turning / holding up on down days while sitting under RS 70; at death, 23 grind lineages
  were subtly healthy vs 12 by the RS-70 level cut. The RS-70 assignment floor is **not** what
  discards them — rising-RS names above the floor reach a theme at 26.5%, below it at 21.9%.

## 1. Lineages — 398 from 513 names

| rule (engine's own identity) | edges |
|---|---|
| `mi_theme_renames` (2 rows) | 2 |
| Retired tombstone note "renamed to" | 11 |
| `theme_renamed_on_mass_flag` audit | 4 |
| `_get_theme_history` Jaccard ≥0.4 vs any name's most recent row in the prior 10 days | 102 |

- **398 lineages**; 69 carry more than one name. 12 names whose first row is a tombstone are not births.
- **#534 rebirth rule** (≥50% of a newborn's founders came from a lineage dead ≤14 days earlier —
  the `_dedup_against_themes` "share of the new cohort" convention): **32 links**. Kept as a
  directed link, not a union — merging it at dedup would empty the "reborn" class by construction.
  Collapsing them too gives **366** lineages.
- 34 names were born wearing a non-Nascent stage (inherited history); the Jaccard rule attaches only
  7 of them to a prior name — the rest are same-name revivals or inherited from >10 days back.

## 2. Birth class — grind 325 · co-gap 73 (of 398)

Co-gap = ≥2 founders gapped ≥ `MIN_GAP_PCT` (9%) in the 20 sessions up to and including birth day;
grind = 0 or 1.

- **Scan log covers the full window for 328 of 398 births (82.4%)** — it starts 2026-04-13 and is
  floor-censored by era (8% Apr–May, 10% Jun–Jul, 5% capture from Aug). Uncovered births use the
  uniform open-gap read from `mi_daily_closes` (`open / prior close − 1`). The two classifiers agree
  on **301 of 328 (91.8%)** of the overlap, which justifies the substitution.
- Under the open-gap read alone (uniform, all births): grind 348 · co-gap 50.
- 93 grind births have exactly one gapper (the boundary). Co-gap births by sessions from the latest
  founder gap to birth: same day 16 · 1–5 sessions 27 · 6–10 15 · 11–20 15. Only **13** co-gap births
  had ≥2 founders gapping on birth day or the day before — the "same-day co-gap" case is rarer than
  the plan's framing implied.
- By birth month (grind/co-gap): Mar 35/8 · Apr 22/3 · May 3/0 · Jun 35/6 · Jul 111/5 · **Aug 99/45**
  · Sep 20/6. August is where co-gap births concentrate (the 5% capture floor + Lane 2 seeding).
- **Founder count: 1 (1) · 2 (127) · 3 (105) · 4 (72) · 5 (42) · 6 (22) · 7 (8) · 8+ (21).**

## 3. Coherence — mean pairwise SPY-residual correlation of the founders

Computed by `correlation_engine._compute_residual_correlations` (no correlation maths written here).
Pre = 20 returns ending birth−1; post = 20 returns starting birth+1 (birth-day return excluded from
both). Bar = `_MEAN_CORR_MIN` 0.80. NATIVE panel = the helper as-is (returns nothing under 4
founders); RELAXED = instrument floor lowered to 2 **in this process only**. Where both panels read,
they disagree on the bar **0 of 165** times (same maths, floor only).

| panel | class | n | pre median | pre ≥0.80 | post median | post ≥0.80 | post > pre |
|---|---|---|---|---|---|---|---|
| NATIVE (≥4 founders) | grind | 132 | **0.807** | 69/132 = 52.3% | 0.583 | 11/83 = 13.3% | 21/83 = 25.3% |
| NATIVE (≥4 founders) | co-gap | 33 | 0.638 | 10/33 = 30.3% | 0.546 | 3/12 = 25.0% | 6/12 = 50.0% |
| RELAXED (floor 2) | grind | 320 | 0.644 | 99/320 = 30.9% | 0.506 | 26/219 = 11.9% | 76/219 = 34.7% |
| RELAXED (floor 2) | co-gap | 73 | 0.391 | 16/73 = 21.9% | 0.518 | 4/30 = 13.3% | 18/30 = 60.0% |

- **228 births the native instrument cannot read at all** (2–3 founders); 5 unreadable in both.
- Grind births with ≥4 founders are tight before naming (median 0.81 — discovery is seeded from
  ≥0.85 correlation clusters, so this is partly by construction) and **loosen after** (median 0.58).
  Co-gap births are loose before (0.39–0.64) — as the reflexivity argument predicts — and, unlike
  grind, tend to tighten after (post > pre in 60%).
- Maturers vs non-maturers look the same on pre-birth coherence (native grind 0.815 vs 0.804).
  Tighter-at-birth grind lineages matured **less** (pre ≥0.80: 37 of 99 = 37.4%; pre <0.80: 104 of
  221 = 47.1%) — a timeliness hint for step 3, not a step-1 finding.
- Caveat: a shared gap day inside the pre window inflates a pair's correlation; the co-gap class is
  reported, not judged, for exactly that reason.

## 4. Strength of founders at birth — RS level vs subtle RS (operator scope addition)

Legs: **rising** = `db.get_rs_velocity` row predicate (front-weighted 4-week acceleration, last week
still rising); **turning** = `db.get_rs_turners` predicate (RS ≤30 four weeks ago, ≥3 consecutive
weekly gains, +10 points); **holding up** = NEW — median of (name − SPY) daily return on the SPY-down
sessions in the 20 sessions before the date, positive = held up better. Weekly snapshots resolve
exactly as `db._resolve_weekly_snapshots` / `_pick_latest_complete_score_date`.

| class | founders | RS ≥70 | subtle (any leg) | rising | turning | holding up (median) | subtle but RS <70 | RS ≥70, no subtle leg |
|---|---|---|---|---|---|---|---|---|
| grind | 1,185 | 632 = 53.3% | **962 = 81.2%** | 629 = 53.1% | 121 = 10.2% | 779 = 65.7% (+0.6%/down day) | **374 = 31.6%** | 44 = 3.7% |
| co-gap | 326 | 184 = 56.4% | 208 = 63.8% | 175 = 53.7% | 34 = 10.4% | 136 = 41.7% (−0.4%/down day) | 35 = 10.7% | 11 = 3.4% |

- **The gap between the two cuts is the finding:** a level gate calls 53% of grind founders strong;
  the subtle read calls 81%. 76 grind lineages (of 325) are subtle-majority but not level-majority;
  13 the reverse. Caveat: "any leg" is carried mostly by holding-up (65.7%), whose ">0" threshold
  is the operator's definition and close to a coin flip for an arbitrary name; rising alone (53.1%)
  is the tighter leg.
- **Holding up on down days separates the classes the way the operator described:** grind founders
  that did not gap held up (+0.6% vs SPY per down day, 66.8% positive); co-gap founders that gapped
  did not (34.8% positive, median negative). A gap manufactures the RS level; it does not manufacture
  down-day resilience measured before the gap existed.
- Maturity by birth strength (grind): level-majority 105/214 = 49.1% · subtle-majority 130/277 =
  46.9% · neither 7/35 = 20.0%. Co-gap: 21/52 = 40.4% · 21/57 = 36.8% · **0/14 = 0.0%**.
- Turning is rare (10%) partly by construction: `get_rs_turners` requires a sector, and only the top
  ~300 RS ranks carry one in `mi_stock_scores` — a "not highest RS but turning" name is excluded from
  that pool unless it is already near the top. Reported, not changed.

## 5. Non-maturer split — 234 of 398 lineages (58.8%) never reached Mainstream

Mainstream is age-gated (`theme_engine.py:3784`), so this is a floor count, not an earliness measure.
Order: still-live (censored) → absorbed (tombstone "absorbed/superseded" pointer, or the lost side of
a `pass1_5_absorption` / `protect_strip` (summary's stripped name) / `thesis_merged` /
`auto_retired`-with-successor audit row) → reborn (#534 link) → health split at the last live row:
members' mean RS from `mi_stock_scores` (rs_avg is NULL on weak-branch rows) + post-death coherence
of the **founders** (same cohort as pre-birth) vs pre-birth.

Absorption is keyed on the name that actually ended the lineage (an any-name rule would have
called 4 more lineages absorbed whose ending name has no absorption record).

| class | n | dissolved | absorbed | reborn | killed-healthy | RS 50–70, coh held (undefined) | still-live | post-window censored |
|---|---|---|---|---|---|---|---|---|
| grind | 183 | 73 | 45 | 13 | 12 | 4 | 25 | 11 |
| co-gap | 51 | 12 | 13 | 5 | 3 | 1 | 9 | 8 |

- **Grind, classifiable 147: churn 70 (47.6%) · dissolved 73 (49.7%) · undefined 4.** Dissolved by:
  RS <50 alone 31 · coherence slipped alone 25 · both 17. **Of the 25 coherence-only, 16 still had
  mean RS ≥70 at death** (e.g. "Physical AI & Robotics", pre 0.04 → post-death 0.03 — a trivial slip
  on near-zero coherence counts as "fell").
- **Co-gap, classifiable 34 (reported, not judged): churn 21 (61.8%) · dissolved 12 (35.3%).**
- **Bar A** (dissolved ≥40% within grind): pre-declared definition 73/147 = **49.7% → crossed**;
  RS arm alone 48/147 = **32.7% → not crossed**. **Bar B** (churn ≥60%): 91/181 = 50.3% → not
  crossed. The coherence arm's base rate: post-birth coherence below pre-birth in 155/249 = 62.2% of
  all readable lineages and 77/123 = 62.6% of maturers (post-birth is the proxy — maturers have no
  death to test). Whether a slip counts is **the operator's call**, flagged rather than resolved here.
- **Healthy-at-death, level vs subtle (grind, 89 health-split lineages):** level (mean RS ≥70 &
  coherence held) **12** · subtle (≥half members rising/turning/holding up & coherence held) **23** ·
  both 12 · subtle-only 11 · level-only 0. The level cut misses 11 healthy deaths the subtle read
  sees — with the caveat that the subtle call is carried mostly by the holding-up leg, whose ">0"
  threshold is permissive (§4, Limits).
- **Split with subtle-healthy folded in (scope item 3):** grind churn **81/147 = 55.1%**, dissolved
  **66/147 = 44.9%**, killed-healthy 23 (11 moved: 7 from dissolved-on-RS <50, 4 from the undefined
  bucket) → Bar A still crossed, Bar B still not (103/181 = 56.9%). Co-gap: churn 22/34 = 64.7%,
  dissolved 12/34 = 35.3%.
- Death mechanisms on record cover only part of the class (grind: absorbed-with-successor 45 —
  tombstone pointer 34, pass1.5 absorption 4, protect-strip 6, auto-retire 1 — Arm-A validation
  dissolve 6, cap-drop 2, reborn 13). **Tombstones exist only from
  2026-05-26 and the absorption audit from 04-30**, so early deaths carry no trail: **absorbed is a
  floor**, and the March/April rows in the health split include silent merges. Median life of a
  classifiable grind non-maturer: **7 days**.
- By birth month, grind classifiable — dissolved: Mar 5 · Apr 6 · Jun 15 · **Jul 29** · Aug 17 ·
  Sep 1; absorbed: Mar 6 · Apr 2 · May 3 · Jun 1 · Jul 6 · **Aug 25** · Sep 2. July births dissolve;
  August births get absorbed (the merge arm went live 07-27).

## 6. Agreement with the operator's 90 labels

Ground truth `docs/analysis/368_labeling_sheet.tsv` reproduces prod exactly (themed: 49 yes / 9 no
/ 1 unsure; overall 71 / 18 / 1). Themed precision **49 of 58 = 84.5%** stands. Detectable ceiling
stated first: **5 of the 9 errors are one scope mistake** (crypto miners converting to AI — HUT ×2,
WULF, CLSK, IREN: a coherent cohort under the wrong name, invisible to price coherence by
construction); **2 are membership errors** (BATL, KYTX); **2 near-misses** (LUNR, CRCL). Price
coherence can catch at most 4 of 9.

Measured over the 20 sessions ending alert_date−1, on the board row within 10 days that carried the
ticker (else the latest prior row; 55 of 58 resolved, 48 with the ticker a member — the sheet's
theme column is the shadow's attribution and can name a theme the ticker never joined).

| measure | Y median (n) | N median (n) | share of (Y,N) pairs where Y scores higher | Y ≥0.80 | N ≥0.80 |
|---|---|---|---|---|---|
| cohort coherence | 0.359 (47) | 0.693 (8) | **0.29** | 1/47 = 2.1% | 3/8 = 37.5% |
| ticker's own fit to its cohort | 0.344 (47) | 0.667 (8) | **0.29** | 1/47 = 2.1% | 2/8 = 25.0% |

- **Direction NOT reproduced in aggregate — it points the other way,** and for the pre-declared
  reason: his no-labels are dominated by the crypto→AI cohort, which moved together tightly
  (fit 0.54–0.87) under a name he rejects. Coherence measures the cohort; his label judged the name.
- **The two membership errors are the two lowest fits of all nine:** BATL **−0.13**, KYTX **0.07**
  (his yes-rows' 10th percentile is 0.07). LUNR 0.57, CRCL unresolvable (no board row for "CLO &
  Structured Credit Income" within 10 days of 07-10).
- **His real themes sit far below the engine's bar:** yes-row fit quartiles p10/p25/p50/p75/p90 =
  0.07 / 0.19 / 0.34 / 0.49 / 0.69. A 0.80 theme-reality bar would reject 46 of his 47 real themes.
  Nothing was tuned to his labels; this is reported as the constant's meaning, not a knob.

## 7. Funnel — are subtle names discovered and then dropped at the assignment floor?

- Source reads `THEME_RS_MIN = 50` (the scope note said 40) — flagged. Pools reconstructed from the
  universe export with the engine's own predicates; against the engine's nightly `theme_engine_funnel`
  rows (54 nights): velocity count exact 25/54, within 3 on 50/54; turners exact 19/54, within 3 on
  43/54. Faithful enough to count.
- **Velocity-pool names under RS 70 and not already themed: 315 ticker-nights over 120 runs; 69
  (21.9%) reached any theme within 14 days, 246 (78.1%) never did.** Turner pool: 37; 25 (67.6%)
  reached a theme.
- **Control — the same pools at/above RS 70: velocity 2,417 ticker-nights, 640 (26.5%) reached a
  theme; turners 871, 203 (23.3%).** The floor is not the gate: rising-RS names mostly never get a
  theme at any RS level, because the only door for an uncovered name is discovery forming a new theme
  around it, and discovery does that for roughly one in four regardless of level. The dropped-under-70
  sample is telling in itself: MS, JPM, GS, SCHW, AAPL, ASML — rising mega-caps the engine never
  grouped.

## Things in the plan found false or unusable (flag, not fix)

1. **"Check `mi_ep_scan_log` for pre-birth gaps" cannot be followed literally for two months** —
   the log starts 2026-04-13 and its floor moved 8 → 10 → 5 by era; every March birth would read
   "grind" by construction. The open-gap read from `mi_daily_closes.open_price` (fully populated) is
   the uniform substitute, validated at 91.8% agreement on the overlap.
2. **The engine's coherence instrument cannot read the engine's own births:** `_MIN_CLUSTER_SIZE` = 4
   while themes are born at 2 (`PRUNE_MIN_TICKERS`) — 233 of 398 lineages sit below the floor.
3. **Tombstones only exist from 2026-05-26** (`theme_auto_retired`) and the absorption audit from
   04-30 — "absorbed (Retired with `parent_theme`)" under-counts early deaths; absorbed is a floor.
4. **The #534 rebirth rule cannot be both a dedup input and the "reborn" class** — used as a link.
5. **`THEME_RS_MIN` is 50, not 40.**
6. **The "dissolved" definition's coherence arm** (post-death coherence below pre-birth): its proxy
   (post-birth below pre-birth) holds for 62% of all lineages including maturers — as written it
   does not separate noise from real.
7. **The 0.80 bar is a cluster-mining threshold, not a theme-reality bar** (§6).
8. Minor, on record: the engine-drop block seeds protect-strip successor pointers as `j` = lost /
   `i` = successor regardless of which side was stripped (`theme_engine.py` ~7860); on 6 of 156
   emptying strips the *kept* theme got a same-day tombstone pointing at the stripped one (66 correct).
9. Verified true, no change: Mainstream is age-gated (`:3784`); `mi_correlation_clusters` = uncovered
   clusters only; `mi_themes.score` never used as evidence of movement; birth validation reads clean.

## Limits

- Post-birth / post-death windows need 20 sessions after the event: 11 grind + 8 co-gap non-maturers
  are censored, and August births (144 of 398) dominate the censored set — the split is Mar–Jul-weighted.
- "Founders" = the earliest name's first row; later joiners are not measured (step 3's contamination,
  not step 1's).
- Co-gap pre-birth coherence is mechanically depressed (members had not moved together yet) and can
  be inflated by a shared gap day inside the window — reported, never judged.
- The turner leg is under-read by the sector requirement (§4); the hold measure is new and has no
  history in the engine — its threshold (>0) is the operator's definition, not a calibrated one.

## Files

- `scripts/probes/_step1_theme_precision.py` — the probe (read-only; imports only `correlation_engine`).
- `scripts/probes/_step1_theme_precision_out.txt` · `_lineages.tsv` · `_founders.tsv` — outputs.
- `scripts/probes/_step1_theme_precision_shape.sql` / `_shape_out.txt` — the one-shot table census.
- `scripts/probes/_step1_x_*.sql` → `_step1_{themes,scan,closes,scores,scores_all,audit,audit2,audit3,cohort}.tsv` — frozen exports (2026-09-07, ~30 MB uncommitted; keep/ignore is the parent's call).
