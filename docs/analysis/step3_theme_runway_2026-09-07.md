# Step 3 — TIMELINESS / RUNWAY: how much runway was left when we named the theme? (2026-09-07)

**Read-only, $0, nothing changed.** Judged on EP-grade gaps and relative strength only — never on
trade returns (operator ruling). Probe: `scripts/probes/_step3_theme_runway.py`; every number below
is in `scripts/probes/_step3_theme_runway_out.txt`, per-lineage rows in `_step3_theme_runway_lineages.tsv`,
per-member rows in `_step3_theme_runway_members.tsv`, per-cluster rows in `_step3_theme_runway_clusters.tsv`.
Data: step 1's and step 2's frozen prod exports plus ONE new pull (`_step3_clusters.tsv` =
`mi_correlation_clusters`, captured once 2026-09-07, git-ignored). Plan:
`~/.claude/plans/plan-this-out-with-hidden-bentley.md` §3 and §"HIS POINT — reflexive". Step 1's
helpers and its 398-lineage table are **reused, not re-derived**. Grind and co-gap are reported
**separately everywhere**.

**The operator's framing, which this step measures against:** a gap manufactures relative strength, so
a theme named after the first EP is **not** late — that is the normal causal order. The question is
**how much runway was left**: at naming, what share of the theme's eventual members had not yet had
their EP. Not measured against the stage clock (Mainstream is age-gated, `theme_engine.py:3784`).

## Method — population, window, and how each set was derived

**The decision this serves.** Whether naming themes earlier is worth anything. Bars fixed in the plan
before the probe ran: **runway ≈ 0 → an earlier theme buys nothing, stop chasing "early" on this
axis; runway large AND clusters convert → naming can move earlier for free, and the target is the
operator's to set** (his answer when asked how many days: "I'm not sure").

**Population.** The **398 lineages** step 1 built from the 513 `mi_themes` names (rename table +
tombstone notes + mass-flag audit + Jaccard ≥ 0.4; births 2026-03-19 → 2026-09-04), with step 1's
birth class (**325 grind / 73 co-gap**) and maturity (**164 reached Mainstream**). **Eventual members**
= every ticker in ANY non-Retired snapshot of ANY name in the lineage (median 4 per lineage, p75 7;
founders median 3) — not the birth row, which would make a co-gap-born theme's runway zero by
construction. Per member, its **first-join snapshot date**; a `theme_date = D` row is written ~17:07
ET on D, so a name is on the list from D + 1.

**"Had an EP" — three legs, each reported.** *Primary* = an alert row (`mi_ep_alerts` UNION
`mi_theme_axis_shadow`, 632 ticker-days — the shadow is the fuller record: `mi_ep_alerts` starts 05-11
and lacks 254 shadow rows) OR a `mi_ep_scan_log` row at/above **that day's acting gap floor**. The
floor is derived per scan day from the log itself: **8% from 04-13, 10% from 05-18, 9% from 08-20**
(the SSoT's 05-17 R2 ship, confirmed on the tape). Rows the log tags `universe_floor` / `gap_floor`
(11,755) and the **22,551 universe-stage rejects** (`filter:universe_prev_close_too_low` /
`_illiquid` — from 08-24 the log records ~1,500 rows a day of 5–9% gaps under the capture floor with
NO reject stage) are excluded: they never entered the EP funnel. Primary = **3,192 ticker-days**; note
it counts sub-bar funnel gaps (a name scored 25 and killed still "had its EP-grade gap"). *+Open-gap*
adds the uniform `open / prior close − 1 ≥ 9%` read from `mi_daily_closes` (step 1 validated it at
91.8% against the scan log) — the only pre-birth EP read for births whose pre-window predates the scan
log. *Alerts-only* = names the system actually alerted on.

**Windows.** Pre = the 20 sessions before birth **through birth day** (the birth row is written after
the close, so a birth-day gap happened before naming). Post = the 20 sessions after birth; 40/40 as
sensitivity. Data ends 2026-09-04, so **143 of 398 births are post-censored** (birth + 20 sessions
past the data) — every headline row is given on the uncensored subset too. **Runway** = post-only
EPers ÷ all EPers. A lineage with **no EPer in either window is its own class**, never 0%.
**Delivered** = a post-naming EP on a name whose first-join snapshot is strictly before its gap day
(the theme pointed at it before it moved); **post-hoc** = the name joined on/after its gap.

**Era.** E0 = the pre-window starts before the scan log (70 births, 2026-03-19 → 05-08): the primary
leg is blind to their pre-birth gaps by construction, so only the +open-gap read is quoted for them.
E1+ = pre-window fully scan-covered (328 births from 05-11; the uncensored headline subset is the 185
born 05-14 → 08-05).

**Ignition** (secondary). Per lineage, in [birth − 40, birth + 20] sessions: **RS** = members' mean RS
≥ 70 (`ASSIGN_POOL_RS_FLOOR`) on 3 consecutive `mi_stock_scores` dates · **CL** = ≥ half the members in
ONE stored cluster (the `_dedup_against_themes` 50% convention) · **EP** = first primary EP among
members. Each leg's fire rate is reported before any "which fired first" tally, with founders variants
and the continuous max-cluster-share alongside (the saturation check step 2 taught).

**Cluster → theme conversion.** 1,938 stored clusters over 144 dates (2025-12-02 → 2026-09-04), chained
into **775 cluster-lineages** (≥ 50% of a later cluster inside the prior stored day's, ≤ 7 calendar
days apart). A cluster converts if a theme lineage is born within 20 sessions whose **founders** cover
≥ 50% of it (loose variant: eventual members). Lead = birth − first cluster day. ⚠ **Two biases,
stated wherever the numbers are used:** (1) `_dedup_against_themes` drops clusters ≥ 50% covered by an
active theme **before the write**, so stored history is uncovered clusters only — the conversion rate
is a **floor** and the CL ignition leg can only fire pre-birth; (2) clusters are handed to the
discovery prompt **the same night** ("propose it as a Nascent theme"), so a lead-0 conversion is the
engine naming its own seed, not a cluster that preceded a birth. Live consumption began **2026-04-17**
(commit `f70bf9ab`); the 296 cluster-lineages before that are a backfill the engine never saw.

**Contamination, stated as a constraint.** `theme_engine.py:4567` passes no `thesis` to post-assignment
membership validation. This step counts **lifetime** membership — exactly what that bug can hold
wrongly — so, unlike step 1 (founders only), it is mildly contaminated: the post-hoc class and the
eventual-member denominators can carry wrongly-held names. Nothing here re-validates membership.

**Nothing was tuned.** Every threshold is one the system owns (RS 70, cluster coverage 0.5, gap 9%,
20 sessions) or the plan fixed in advance. Where a constant meant something other than the plan
assumed, it is a finding (§4), not a knob.

⚖ **THE LINE.** Read-only evidence. No detection criterion, grade, alert, entry, exit, sizing or
safeguard was changed or proposed as changed. The target ("how early") is the operator's to set.

## The answer

- **Runway is real but thin — neither bar is met cleanly.** On the scan-covered, uncensored births
  (n = 185 lineages, born 2026-05-14 → 2026-08-05): **90 of the 241 member EP-grade gaps in the month
  around naming (37%) came AFTER naming, and 51 of 241 (21%) landed on a name the theme had already
  listed** — the other 39 were names added only after they gapped. Per theme: **79 of 185 (43%) had
  no member gap at all** within a month either side, **56 (30%) had at least one still ahead, 41
  (22%) delivered one on a listed name.** Across every name the engine put in a theme, **about 1 in 10
  gapped in the 20 sessions after naming** (208 of 2,035 on the 255 uncensored lineages; at least 8%
  on all 398 — grind 190 of 2,337, co-gap 37 of 663).
- **What naming earlier would have bought — the target curve (founders only, the honest proxy; an
  earlier theme's later joiners are unknowable).** Of 354 founder gaps in the window, 103 (29%) came
  after naming and were therefore delivered. Had every theme been named **5 sessions earlier, 90 more
  founder gaps would have been ahead of the list (55% delivered); 10 sessions earlier → 68%; 15 → 81%**
  (headline population: 29% → 61% / 71% / 84%, n = 161). 31 of the 251 pre-naming founder gaps fell on
  the birth day itself. **The number of sessions is the operator's to set** — this curve is what he
  asked for and did not have.
- **Robust to the EP definition.** Funnel gaps 37% / 21%; +open-gap 38% / 22% (n = 247); **alerts
  only 45% / 23% (n = 75 alerts, 142 of 185 lineages with no member alert at all)**; 40/40 windows on
  the 80 early-enough births 26% / 15% (n = 163). The per-lineage median is unusable: 94 lineages have
  exactly one EPer (0% or 100% by arithmetic), 171 have none — the pooled member-level share is the
  measure.
- **Grind vs co-gap, as the reflexivity argument predicts.** Grind-born: **55% of member gaps after
  naming, 31% delivered** (82 and 46 of 148). Co-gap-born: **9% / 5%** (8 and 5 of 93) — mechanically
  low, since ≥ 2 founders gapped before birth by definition; a co-gap theme is named after its gaps.
- **Which ignition fires first is a tie between strength and gaps** (births ≥ 04-13 with ≥ 2 legs, n =
  240): **first EP 90, RS-held 87, cluster 49**. But the RS leg is nearly saturated (fires 77%, 46
  at the 40-session edge — themes are assembled from RS ≥ 70 names) and the cluster leg under-fires on
  big lineages (28% at 9+ members vs 62% at 5–8). Whatever the leg, **the engine names a group a
  median 30 sessions (~6 weeks) after its first signal** (p25 12; p90 at the 40-session edge); only
  6 of 331 were named before any signal.
- **Clusters convert — but the engine already names them at once.** Since June (live consumption
  with births flowing): **171 of 353 cluster-lineages (48%; uncensored 117 of 216 = 54%) became a
  theme within 20 sessions, vs 41% of themes maturing** — the plan's "convert at least as often as
  themes mature" holds. Yet **64 of 171 (37%) converted the same night** and the median lead is 2
  sessions: there is no unused "cluster time" to move naming to. The unused window is on the birth
  side: **140 of 398 themes (35%) had a stored cluster holding ≥ half their founders a median 26
  sessions before the birth** — a group the engine had in hand for ~5 weeks and did not name. Those
  matured at 37% (52 of 140), the same as the rest.
- **Found false:** "12,631 clusters" is 12,631 ticker-rows = 1,938 clusters; 296 of 775 cluster-lineages
  predate live consumption and a 42-day hole (02-27 → 04-10) covers every March birth's lookback; the
  scan log's 10% floor starts 05-18 (step 2's era table said June); and from 08-24 the log carries
  ~1,500 untagged sub-floor rows a day that a naive "gap ≥ floor" join counts as EPs (§4).

## 1. Runway — share of member EP-grade gaps that were still ahead at naming

All rows: 20 sessions pre (through birth day) / 20 post; "no EPer" = lineages with no member gap in
either window; "=0 / =1" = lineages at exactly 0% / 100%; pooled = member-level.

| population | lineages (n) | no EPer | runway per lineage p25 / p50 / p75 (n defined) | =0 | =1 | pooled post ÷ EPers | pooled DELIVERED | post-hoc | ≥1 post | ≥1 delivered |
|---|---|---|---|---|---|---|---|---|---|---|
| **E1+ & uncensored (headline)** | n = 185 | 79 | 0% / 21% / 100% (n = 106) | 50 | 32 | **90 / 241 = 37.3%** | **51 / 241 = 21.2%** | 39 | 56 | 41 |
| … grind-born | n = 165 | 79 | 0% / 50% / 100% (n = 86) | 34 | 32 | 82 / 148 = 55.4% | 46 / 148 = 31.1% | 36 | 52 | 37 |
| … co-gap-born | n = 20 | 0 | 0% / 0% / 0% (n = 20) | 16 | 0 | 8 / 93 = 8.6% | 5 / 93 = 5.4% | 3 | 4 | 4 |
| … matured | n = 92 | 39 | 0% / 50% / 100% (n = 53) | 20 | 19 | 64 / 118 = 54.2% | 28 / 118 = 23.7% | 36 | 33 | 20 |
| … never matured | n = 93 | 40 | 0% / 0% / 50% (n = 53) | 30 | 13 | 26 / 123 = 21.1% | 23 / 123 = 18.7% | 3 | 23 | 21 |
| all 398, primary legs | n = 398 | 171 | 0% / 25% / 100% (n = 227) | 108 | 72 | 227 / 600 = 37.8% | 147 / 600 = 24.5% | 80 | 119 | 98 |
| all 398, +open-gap | n = 398 | 152 | 0% / 0% / 60% (n = 246) | 127 | 49 | 232 / 769 = 30.2% | 150 / 769 = 19.5% | 82 | 119 | 100 |
| … grind-born, +open-gap | n = 325 | 152 | 0% / 38% / 100% (n = 173) | 66 | 49 | 208 / 445 = 46.7% | 133 / 445 = 29.9% | 75 | 107 | 89 |
| … co-gap-born, +open-gap | n = 73 | 0 | 0% / 0% / 0% (n = 73) | 61 | 0 | 24 / 324 = 7.4% | 17 / 324 = 5.2% | 7 | 12 | 11 |
| E0 births, +open-gap (primary is blind pre-birth here) | n = 70 | 7 | 0% / 33% / 71% (n = 63) | 17 | 11 | 119 / 298 = 39.9% | 81 / 298 = 27.2% | 38 | 46 | 45 |
| E1+ & uncensored, ALERTS ONLY | n = 185 | 142 | 0% / 0% / 100% (n = 43) | 23 | 15 | 34 / 75 = 45.3% | 17 / 75 = 22.7% | 17 | 20 | 13 |
| E1+ & uncensored, 40 / 40 windows | n = 80 | 19 | 0% / 0% / 50% (n = 61) | 37 | 8 | 42 / 163 = 25.8% | 25 / 163 = 15.3% | 17 | — | — |

- **When runway exists, it arrives fast:** post-naming gaps come a median **11 sessions** after naming
  (delivered ones 13; n = 227 / 147). Pre-naming gaps sit a median 8 sessions before birth (n = 373,
  251 of them founders). 39 of the 227 post-naming gaps came after the lineage's last live snapshot.
- **Target curve, from the founder rows of `_step3_theme_runway_members.tsv`** (pre-naming founder gaps
  by sessions before birth: 0 → 31, 1 → 12, 2 → 18, 3 → 14, 4 → 15, 5–9 → 47, 10–14 → 48, 15–19 → 54,
  20 → 12; n = 251). Naming k sessions earlier turns every pre-gap with lag < k into a delivered one:
  k = 1 → +31 (38% of 354 founder gaps delivered), k = 3 → +61 (46%), **k = 5 → +90 (55%), k = 10 →
  +137 (68%), k = 15 → +185 (81%)**; base 103 of 354 = 29%. Capped at 15 — the pre-window is 20, so 20
  is degenerate. Founders only: what an earlier theme's eventual list would have held is unknowable.
- **Maturing themes absorb the gappers; non-maturers deliver but rarely.** Among matured E1+
  uncensored themes 36 of 64 post-naming gaps are post-hoc additions (the theme grew by adding names
  after they moved — reflexive membership, and the class the `:4567` bug touches); among non-maturers
  23 of 26 are delivered but only 23 lineages of 93 have one.
- **Post-hoc is not the same-night Lane-2 add:** of 80 post-hoc joiners, 6 joined on their gap day and
  74 later — the engine assigned them days after the gap, once the gap had made them strong.
- **Era matters more than the window.** By birth month (lineages / EPers / post / delivered): Apr
  25/89/66/50 · May 3/9/2/1 · **Jun 41/49/6/4** · **Jul 116/133/66/37** · Aug 144/254/37/25
  (censored). June births (10% floor, quiet tape) had almost no runway; July births met August's
  dense EP tape. Runway is a property of the following month's tape as much as of the naming.
- **The 40/40 read (n = 163) is lower (26% / 15%) because its population is the June-dominated early
  births and a longer pre-window finds more prior gaps** — not a different answer.

## 2. Ignition — what fired first, and how long before naming

Births ≥ 2026-04-13 (stored clusters and scan log both exist in the window), n = 337. Lag = birth −
ignition in sessions; positive = the signal preceded naming.

| leg | fires (n = 337) | lag p25 / med / p75 | before / on / after birth | at the −40 edge |
|---|---|---|---|---|
| RS: members' mean RS ≥ 70 held 3 score dates | 258 = 76.6% | 1 / 11 / 35 | 209 / 9 / 40 | 46 |
| RS, founders | 263 = 78.0% | 1 / 11 / 35 | 213 / 20 / 30 | 48 |
| RS, 20-session lookback only | 235 = 69.7% | 1 / 5 / 16 | 179 / 14 / 42 | 0 |
| CL: ≥ half of eventual members in one stored cluster | 156 = 46.3% | 1 / 14 / 32 | 118 / 32 / 6 | 18 |
| CL, ≥ half of founders | 182 = 54.0% | 0 / 14 / 32 | 133 / 36 / 13 | 18 |
| EP: first primary EP among members | 217 = 64.4% | 5 / 25 / 36 | 181 / 9 / 27 | 18 |
| EP, +open-gap | 223 = 66.2% | 6 / 26 / 36 | 188 / 8 / 27 | 21 |

- **Which fired first**, lineages with ≥ 2 legs (n = 240): **EP 90 · RS 87 · CL 49**, ties 14. Grind
  (n = 214): RS 87, EP 69, CL 45. Co-gap (n = 63): RS 30, EP 24, CL 5 — even co-gap themes often had
  a strength signal before their gaps, at the window's edge. Matured (n = 133): RS 56, EP 49, CL 21.
- **Lag from the earliest signal to naming: p10 / p25 / median / p75 / p90 = 1 / 12 / 30 / 39 / 40**
  (n = 331); named before any signal **6**, same day 19, after 306. The median is boundary-censored —
  "at least" 30 sessions.
- **Saturation checks.** The RS leg fires for 77% and for 46 lineages at the lookback edge — RS level is
  what themes are assembled from, so it is a weak ignition read (and the contaminated one: a gap
  manufactures it). The cluster leg has the size dependence step 2 warned about, in reverse: fires
  **42.6% at ≤ 4 members, 62.4% at 5–8, 28.3% at 9+** (n = 183 / 101 / 53) — half of a 20-name lineage
  in one size-4-to-8 cluster is impossible. Continuous read: max share of members ever together in one
  stored cluster, median **33%** (founders 50%; n = 337). Every lineage had stored-cluster days in its
  window (median 61).
- The EP leg among co-gap births fires 96% with median lag 18 sessions; among grind births 57%,
  median lag 14 — a grind-born theme's first member gap is, half the time, still 3 weeks before naming.

## 3. Cluster → theme conversion (a floor, by construction)

| cluster-lineages | n | converted (founders cover ≥ 50%, birth ≤ 20 sessions) | lead 0 (same night) | lead p25 / med / p75 | converted themes matured |
|---|---|---|---|---|---|
| all | n = 775 | 175 = 22.6% (loose 202 = 26.1%) | 64 | 0 / 2 / 9 | 57 / 175 = 32.6% |
| backfill, first day < 04-17 | n = 296 | 0 = 0.0% | — | — | — |
| live, 04-17 → 05-31 | n = 126 | 4 = 3.2% | 0 | 22 / 24 / 30 | 2 / 4 |
| **live, 06-01 onward** | n = 353 | **171 = 48.4%** | 64 = 37.4% | 0 / 2 / 9 | 55 / 171 = 32.2% |
| live, 06-01 onward, uncensored | n = 216 | **117 = 54.2%** | 27 | 1 / 4 / 12 | 46 / 117 = 39.3% |
| themes maturing (the comparison) | n = 398 | 164 = 41.2% | | | |

- **The backfill converts 0 of 296 because no theme existed before 03-19 and the engine never saw those
  rows; April–May converts 4 of 126 because May had 3 theme births in total.** The live June-onward rate
  is the only one that means anything: **about half of stored clusters become a theme, at or above the
  rate themes mature** — the plan's condition holds. Per cluster-day: 418 of 1,938 = 21.6%.
- **But the lead is ~0.** 37% of conversions are same-night (the discovery prompt is handed the
  cluster with "propose it as a Nascent theme"), median 2 sessions, only 7 of 175 beyond 20 sessions.
  Stored history cannot show a cluster "preceding" a birth by much: the engine names it at once, and
  the dedup stops storing it the moment a theme covers it.
- **The birth-side view is the usable one:** 176 of 398 lineages (44%; 169 of 337 = 50% among births
  ≥ 04-13) had ≥ half their founders in one stored cluster in the 40 sessions before birth, and for
  **140 of them the cluster was stored strictly before the birth day — median 26 sessions early (p25
  10, p75 35).** These 140 matured at 37.1% (52), the population at 41.2%.
- Size: size-4 cluster-lineages convert 18.3% (n = 393), 5–8 27.5% (n = 291), 9+ 25.3% (n = 91). Live
  June-onward, clusters with avg RS ≥ 70 convert **23.3% (14 of 60)** vs 53.6% (157 of 293) below
  70 — the strongest clusters are the ones least often named.
- Cluster-lineages are short-lived: median 1 stored day, 418 of 775 single-day — clusters churn day to
  day even when the group persists, which is why the reverse view finds early clusters the forward
  chaining does not.

## 4. Things found false or unusable (flag, not fix)

1. **"12,631 clusters over 144 days"** (plan) = 12,631 **ticker-rows** = **1,938 clusters**; 889 are
   size 4. **296 of 775 cluster-lineages predate live consumption** (2026-04-17, `f70bf9ab`; `avg_rs`
   = 0 on 169 of them — the default, not a score) and there is a **42-day hole 02-27 → 04-10** that
   covers every March birth's lookback.
2. **The scan log's acting floor moved 8% → 10% on 05-18 (not June) and 10% → 9% on 08-20**, read
   from the tape (step 2's era table put both ~2 weeks later). One day, 07-13, logged 38 rows all
   ≥ 35% — a near-empty scan day, not a floor.
3. **From 08-24 the scan log carries ~1,500 rows a day of 5–9% gaps with NO `reject_stage`** and a
   `filter:universe_prev_close_too_low` / `_illiquid` reason (22,551 rows by 09-04). A literal
   "scan-log gap ≥ the era's floor" join — the brief's definition — counts them as EPs. Excluded here;
   any future join must exclude `filter:universe_*` rows too, not only the tagged `universe_floor` /
   `gap_floor` stages.
4. **The per-lineage runway median cannot carry the answer:** 171 of 398 lineages have no EPer, 94
   have exactly one. The pooled member share is the measure; the median is reported for the record.
5. **The "≥ half the members in one stored cluster" ignition leg is size-dependent** (§2) — the
   absolute-share bar under-fires on exactly the big lineages; the continuous max-share is given.
6. **The RS-held leg is boundary-censored and near-saturated** — "RS first" is partly by construction.
7. **"Clusters precede births by N sessions" is structurally ~0 in stored history** (same-night
   consumption + dedup-before-write); only the birth-side reverse view reads it.
8. Verified true, no change: Mainstream is age-gated and the stage clock is not used; `mi_themes.score`
   is never used as evidence of movement; the primary leg undercounts pre-04-13 EPs (E0 quoted on the
   open-gap read only); the `:4567` contamination is stated, not corrected.

## What this does not answer

- **Whether an earlier-named theme would have turned those post-naming gaps into trades.** The EP
  detector's own gates decide alerts, not theme membership, and returns are ruled out of this work. "A
  listed name gapped" is the ceiling of what a theme can deliver on this axis, not a trade.
- **Whether naming the 140 early-visible clusters would have cost noise.** The non-converting half of
  live clusters were never named, so their quality is unmeasured; conversion is a floor twice over
  (dedup-before-write, same-night consumption). "At no extra cost" is not established.
- **Pre-birth gaps for the 70 E0 births** (Mar–mid-Apr): only the open-gap read exists there.
- **The post window for 143 August births is censored**; the headline uses the uncensored 185, whose
  tape (June quiet, July → August dense) is not a neutral sample of future months.
- **RS runway.** Only EP runway is measured; whether members' relative strength kept rising after
  naming (the subtle-RS view) is a different measure, not taken here.
- **Membership correctness.** Lifetime membership is read as written, including any names the
  no-thesis validation held wrongly; the post-hoc class in particular could shrink under a
  re-validation that cannot be run without paying for LLM calls.
- **Names the scan never saw.** A member with no scan row, no alert and no ≥ 9% open gap reads "no
  EP" — true for E1+ under the funnel's own definition, but a name below the $5 / liquidity universe
  screen could gap unseen.

## Files

- `scripts/probes/_step3_theme_runway.py` — the probe (read-only; imports step 1's helpers, no engine call).
- `scripts/probes/_step3_theme_runway_out.txt` · `_lineages.tsv` · `_members.tsv` · `_clusters.tsv` — outputs.
- `scripts/probes/_step3_x_clusters.sql` → `_step3_clusters.tsv` (12,631 rows, git-ignored); `_step3_x_census.sql` → `_step3_census_out.txt` — the one-shot pull and its census, 2026-09-07.
- Reused frozen exports: `_step1_{themes,closes,scores_all}.tsv`, `_step1_theme_precision_lineages.tsv`, `_step2_{alerts,shadow,scan}.tsv`.
