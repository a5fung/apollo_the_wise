# EP alert ranking v2 — built from his chart reads (PRE-REGISTERED 2026-11-03, before any data is read)

**Why.** The shadow ranking (`agents/market_intelligence/alert_rank_shadow.py`: the mean of three within-day
percentile ranks — smaller gap, tighter gap-day range, less MA-distance extension) reached decision grade on
2026-11-03 (32 out-of-sample sessions, `scripts/probes/_rank_shadow_running_read_1103/score.txt`) and does not
pick the tail: its top quartile held 0 of the ≥ 8×ADR winners at 5 sessions, 1 of 3 at 20. Two of its three
features score his best EPs as defects — MRNA 2026-08-19 (his reference EP; the gap-day extension IS the event,
#569) sat near the bottom of its day. His words (operator_shared_notes 2026-11-03): *"yes, we should keep
tightness as i think it may still be relevant"* — and on 11-02, KOD 2026-09-28 (his "good" on the long chart):
*"1) the two pull back is into the previous base high ... 2) the gap up cleared all time high, but more
importantly, clear the congestion areas 3) volume is higest ever"*; ASPN 2026-08-06 (bad): *"failed to clear a
major gap down"*.

**What this is NOT.** No live change; the ranking stays a recorded shadow. Any use of it is his call (THE LINE:
selection). Returns are read only as the tail test the running read already uses; his labels come first.

## The features (exact definitions, all from bars ≤ the gap day D; daily bars, up to 5 years before D)
1. **Zones cleared** — the supply-ladder count (`docs/methodology/structure_model.md`; code
   `scripts/probes/_533_supply_ladder_probe.py`, reused, not rewritten): congestion zones whose price band lies
   between the prior close and the gap-day OPEN (cleared by the gap), and the zones left between the open and
   the 5-year high (remaining overhead). Plus `cleared_ath` = the open is above every prior high.
2. **Volume against its own history** — gap-day volume ÷ the highest daily volume of the 252 sessions before D,
   and `vol_highest_ever` = gap-day volume above every prior day in the 5 years.
3. **Pullbacks held an old base high** — the 2 lowest swing lows of the 40 sessions before D, each measured in
   ADR20 against the highest high of the prior base (the 41st-250th sessions before D); held = both within
   1 ADR above it or above it. (His KOD reason 1; the definition is fixed here and judged on the labels.)
4. **Tightness (kept, his 11-03)** — the shadow's own `tightness_pct_eod` and `tightness_pct_asof0945`, unchanged.

## Populations (labels before outcomes)
- **A. His outcome-blind chart rulings** — `tests/fixtures/must_not_trade_charts.py`: GOOD_CHART / OKISH_CHART
  = yes, BAD_CHART = no (other verdicts excluded and counted).
- **B. His labelled real EPs** — `docs/methodology/operator_labelled_eps.md` (yes; no negatives in it).
- **C. The shadow population** — every `mi_alert_rank_shadow` row since 2026-08-17 (63 rows, 32 sessions on
  11-03), scored by the running read's own tail test (≥ 8×ADR at 5 and 20 sessions, both directions).

## The bar (fixed now)
- Each feature: the chance a yes ranks above a no on A (0.5 = nothing); reported with n.
- The v2 composite = the mean of the within-day percentile ranks of the features that score ≥ 0.65 on A
  (direction as A says). It must: (i) score ≥ 0.70 on A; (ii) rank ≥ 80% of B's EPs in the top half of their
  day (where the day has ≥ 2 alerts); (iii) on C, beat the old composite on the tail in BOTH directions
  (`score_both_directions`: more tail winners in the top quartile, losers admitted no higher). Failing (iii)
  with (i)-(ii) passing is reported as "his eye, not the tail" — never tuned until it passes.
- Plateau: each threshold above (1 ADR, 252 sessions, the 40/41-250 windows) is re-run at ±50%; a result that
  holds only at the stated value is reported as fragile.

## What this does not answer
- Whether the ranking makes money; how to enter or exit; any population before 2026-08-17 for C.

## RESULT — 2026-11-03 (Opus build + blind Opus recount; `scripts/probes/_ep_rank_v2_1103/build/rank_v2.txt`, `verify/verify_v2.txt`)

**FAIL as pre-registered.** On his rulings (17 yes / 37 no): zones cleared 0.67 (the only feature over 0.65); EOD tightness 0.64 (tighter = yes, just under); volume vs its own year 0.62; pullbacks-held 0.51. The composite (zones cleared alone) reads 0.56 within the day (bar 0.70); his 6 rankable labelled EPs all land in the top half (bar met, thin); on the shadow tail it does not beat the old ranking (5 sessions: more winners and more losers; 20: no change). Verifier: every number reproduces; population A/B/C correct; no look-ahead.
- **Tightness, both ways:** on his rulings tighter gap days lean yes (0.64), but his labelled real EPs had WIDE gap days (MRNA 35%, CHPT 28%, BFLY 21%, HTFL 16%); forcing tightness in fails every bar by more.
- **Feature 3 misdefined:** 'the previous base high' as the highest high of sessions 41-250 picked KOD's April $47.84 peak; his read was the Dec-Feb ~$30 shelf. It read 0 on all 8 of his EPs — needs a new definition and a new pre-registration.
- **Coverage, stated:** the bars were pulled for the labelled names only, so many of A's day pools are partial; the raw feature (0.67) is under 0.70 before any ranking, so more bars cannot pass bar (i).

## RESULT 2 — feature 3 re-defined as the shelf before the run (2026-11-03, his "Yes"; `scripts/probes/_ep_rank_v2_1103/build_f3/`, blind recount `build_f3_verify/`)

**FAIL as pre-registered.** The definition (`build_f3/F3_DEFINITION.md`, written before any score; KOD the only calibration — it finds his Dec-2025 ~$31.18 shelf and reads held) scores **0.607** on his rulings (16 yes / 28 no), under the 0.65 entry line; the composite is unchanged (zones cleared alone: (i) 0.555 FAIL, (ii) 6 of 6, (iii) FAIL). Plateau 0.57-0.67 (0.65 at one setting only — fragile). **A lead, not a result:** the continuous distance of the lower pullback low from the shelf reads 0.688 (his yes median -0.4 daily ranges, no median -3.4) — declared ineligible in advance; it needs its own pre-registration on labels not yet seen.

## PRE-REGISTRATION 3 — the shelf-distance lead on labels not yet seen (written 2026-11-04, BEFORE it is computed on them)

- **The lead (RESULT 2):** `dmin` = the lower of the two pullback lows' distances from the shelf, in daily ranges (ADR20), from `scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py::f3_new` with `STATED` — **unchanged, imported, not copied**; ADR20 = `_533_nbis_structure_encoder.adr20_pct`, as RESULT 2. Higher (closer to or above the shelf) = yes, the direction RESULT 2 read (0.688).
- **Fresh labels:** his #594 sample 6 rulings (2026-11-04, outcome-blind, `tests/fixtures/must_not_trade_charts.py` ruling_date 2026-11-04) — none was in RESULT 2's population. yes = GOOD_CHART / OKISH_CHART (5: NTRA, KMT, BLMN, NESR, RSKD); no = BAD_CHART (7). Bars: `scripts/probes/_594_sample6_1104/q2_bars.out` (the 504 daily bars the page was drawn from, ending on D).
- **Statistic:** the chance a yes's `dmin` is above a no's (ties 0.5), over the 35 pairs; a NULL `dmin` (missing structure data) is dropped and counted. Also shown: `held`, `into`, `structure` per chart.
- **The bar:** ≥ 0.65 → the lead holds on fresh labels (DIRECTIONAL ONLY: 12 charts, 35 pairs); < 0.65 → it does not replicate, and it is reported as a failed lead, not re-tuned. No threshold is fitted, so there is no plateau.
- **What this does not answer:** whether a ranking that uses it picks the tail; anything about returns (his eye is the label); n is far too small for a verdict either way.

## RESULT 3 — the shelf-distance lead on sample 6 (2026-11-04; `scripts/probes/_594_shelf_lead_1104/score_shelf_lead.py` → `score_shelf_lead.txt`)

**HOLDS on fresh labels, as pre-registered — DIRECTIONAL ONLY.** On his 12 sample-6 rulings (5 yes / 7 no, 35 pairs, none dropped) the chance a yes's lower pullback low sits closer to (or above) the shelf than a no's is **0.829** (bar 0.65); median yes −2.5 daily ranges from the shelf, no −7.1 (RESULT 2 on the older labels: 0.688, −0.4 vs −3.4). It is the first chart-read measure in this series to hold on labels it was not found on. Only NTRA reads `held` = 1 (the 1-range band is tighter than the separation), so the continuous distance, not the yes/no flag, carries it. n = 12 is far from a verdict; it earns a place as a candidate, re-scored on each new sample, never a filter on its own.

## PRE-REGISTRATION 4 — the shelf-distance lead on sample 7 (written 2026-11-07, BEFORE it is computed on them)

- **The lead and the statistic: unchanged from PRE-REGISTRATION 3** — `dmin` from `f3_def.py::f3_new` with `STATED`, imported not copied; ADR20 from `_533_nbis_structure_encoder.adr20_pct`; the chance a yes's `dmin` is above a no's (ties 0.5); a NULL `dmin` dropped and counted.
- **Fresh labels:** his #594 sample 7 rulings (2026-11-07, outcome-blind, `tests/fixtures/must_not_trade_charts.py` ruling_date 2026-11-07) — drawn at random, none in RESULT 2 or 3's population. yes = GOOD_CHART / OKISH_CHART (7: NX, MGNI, AMLX, MED, CODI, SNOW, BULL); no = BAD_CHART (5: AFYA, PLAB, SAIC, KODK, BIRK) → 35 pairs. Bars: `scripts/probes/_594_sample7_1107/q2_bars.out` (pulled before the grades, the gap day the last bar).
- **The bar:** ≥ 0.65 → holds again (DIRECTIONAL ONLY); < 0.65 → it does not replicate on this sample, reported as such, not re-tuned. Also reported: the pooled figure over samples 6 + 7 (24 charts) beside it, as a description, not a second test.
- **What this does not answer:** whether a ranking using it picks the tail; anything about returns; n is far too small for a verdict.


## RESULT 4 — the shelf-distance lead on sample 7 (2026-11-07; `scripts/probes/_594_shelf_lead_1107/score_shelf_lead.py` → `score_shelf_lead.txt`)

**HOLDS again, as pre-registered (34e02d42) — DIRECTIONAL ONLY.** On his 12 sample-7 rulings (7 yes / 5 no, 35 pairs, none dropped) the chance a yes's lower pullback low sits closer to (or above) the shelf than a no's is **0.686** (bar 0.65), weaker than sample 6's 0.829; median yes +0.25 daily ranges from the shelf, no −7.83. Pooled over samples 6 + 7 (24 charts, 144 pairs, description only): 0.750.
- Against the lead: SAIC (bad, "choppy") held the shelf (+2.6); MED (good) and BULL (ok) sat far below it (−10.2, −15.3) — a choppy base can hold a shelf, and two of his yes calls had no clean run or breakout for the shelf to come from (`structure` = no_run / no_breakout).
- **What this does not answer:** unchanged from PRE-REGISTRATION 4 — the tail, returns, and any verdict on 24 charts.

## PRE-REGISTRATION 5 — the shelf-distance lead on sample 8 (written 2026-11-09, BEFORE it is computed on them)

- **Method unchanged from PRE-REGISTRATION 3/4** (`f3_def.py::f3_new`, `STATED`, imported; ADR20 from `_533_nbis_structure_encoder.adr20_pct`; the chance a yes's `dmin` is above a no's, ties 0.5; NULLs dropped and counted).
- **Fresh labels:** his #594 sample 8 rulings (2026-11-09, outcome-blind, ruling_date 2026-11-09): yes = GOOD / OKISH (5: ATRO, WPP, SITM, EFXT, PICS); no = BAD (7: FLR, CRK, YEXT, WOR, AMRC, VOYG, CNH) → 35 pairs. Bars: `scripts/probes/_594_sample8_1109/q2_bars.out`.
- **Bar:** ≥ 0.65 → holds (directional only); < 0.65 → does not replicate on this sample, reported as such. The pooled figure over samples 6-8 (36 charts) beside it, description only.

## RESULT 5 — the shelf-distance lead on sample 8 (2026-11-09; `scripts/probes/_594_shelf_lead_1109/score_shelf_lead.py` → `.txt`)

**HOLDS a third time, as pre-registered (`f87ddfdf`) — DIRECTIONAL ONLY.** 0.714 on 28 pairs (4 yes / 7 no; PICS dropped, no structure data — counted); median yes −1.13 daily ranges from the shelf, no −4.20. Pooled over samples 6-8 (35 charts, 304 pairs, description only): 0.734.
- **What this does not answer:** the tail, returns, and any verdict on 35 charts.

## RESULT 6 — the shelf-distance lead on sample 9 (2026-11-15 rulings, scored 2026-11-21; `scripts/probes/_594_shelf_lead_1121/score_shelf_lead.txt`)
**HOLDS, directional only.** 5 yes / 4 no, 20 pairs: P = 0.700 ≥ 0.65. Median dmin yes −3.16 ADR, no −5.18. Pooled samples 6-9 (description only): 21 yes / 23 no, P = 0.729.

## RESULT 7 — the shelf-distance lead on sample 10 (2026-11-21 rulings; `scripts/probes/_594_shelf_lead_s10_1121/score_shelf_lead.txt`)
**HOLDS, directional only.** 7 yes / 4 no, 28 pairs (his "maybe" on INSM not filed): P = 0.750. Median dmin yes −1.68 ADR, no −11.87. Pooled samples 6-10 (description only): 28 yes / 27 no, 756 pairs, P = 0.738. Five fresh samples, all at or above the bar. **Still unanswered: outcomes and the tail** → PRE-REGISTRATIONS 6 and 7 (his "can we test it? and also compare with qullamaggies trades", 2026-11-21).

## PRE-REGISTRATION 6 — does the shelf distance pick EPs that WORK? (written 2026-11-21, BEFORE any outcome is read)
- **Feature, unchanged:** `dmin` from `f3_def.py::f3_new` with `STATED` and ADR20 from `_533_nbis_structure_encoder.adr20_pct`, imported not copied. The gap day E is the LAST bar passed (`ia` = E's index), days sliced to the 5 calendar years before E. Verified by reading the code: neither reads the gap-day bar (`swing_lows` uses `days[:ia]` with both wings before E; the base high stops at `ia−pw−1`; ADR20 uses `days[ia−20:ia]`), so the feature is **knowable before the 09:30 open**.
- **Loader check first:** the shared loader must reproduce sample 10's P = 0.750 exactly before it touches the historical files.
- **Population:** every `primary == True` row of `ep_events_A.tsv.gz` / `ep_events_B.tsv.gz` (`/Users/alvinfung/apollo_data/cb702/qm_streams/ep_join_1023/`, the outcome-free EP list built 10-23), dropping `flag_adj` / `flag_adj_Dm1` events (a split in the lookback fakes a shelf), counted. Bars from the same adjusted daily files and loaders `01_ep_join.py` uses. **Sealed data (#710):** every era-B row dated after 2024-12-31 is dropped AT READ and asserted; E ≤ 2024-09-30 so the 60-session forward window never crosses that date. Print events per year, per security type, and NULL-dmin counts (with their outcome rates, to show whether the drop is neutral) BEFORE the result.
- **Outcome (entry = open of E, the 09:31 proxy):** PRIMARY, the tail: **big winner** = the highest close over sessions E..E+60 ≥ 1.5 × open(E). SECONDARY (description only): close(E+60)/open(E) − 1, and close(E+5) < open(E).
- **Regime control:** dmin is ranked into terciles WITHIN each calendar month (months with ≥ 6 scored events; the others are counted and dropped), so a strong market cannot make the feature look good.
- **The bar (fixed now):** the big-winner rate of the top tercile (closest to or above the shelf) is **≥ 1.5 × the bottom tercile's**, AND a within-month permutation of dmin (2,000 shuffles, seed 1121) puts the observed ratio at p ≤ 0.05, AND the direction is the same in era A and era B. All three pass → **the lead predicts the tail**. The ratio alone with p > 0.05 → **directional, not proven**. Ratio < 1.0 → **does not pick winners**. Reported per era and per year as well (never pooled across eras without the split beside it).
- **What this does not answer:** whether a LIVE ranking using it would change which trades were taken (the slot / position cap is a separate simulation); any 2025-26 number (sealed).

## PRE-REGISTRATION 7 — do Qullamaggie's EP buys sit near the shelf? (written 2026-11-21, BEFORE it is computed)
- **His EP buys:** `holdings_1024/entries.tsv` rows with `setup` ∈ {EP, both}, `flicker == False`, `has_bars == True` (62 positions, 2017-02 .. 2023-12, dated by the EP event E). Each must match a `primary` row of the same (ticker, E) in the event list; matched n is printed first. **If matched n < 20, the result is description only.**
- **Comparison, within day:** his buy against every OTHER primary EP event on the same E (the names he could have bought that morning). Statistic: the chance his dmin is above a same-day other's (ties 0.5), averaged over all within-day pairs; days with no other event are counted and dropped. **Bar: ≥ 0.60, and a within-day label permutation (2,000 shuffles, seed 1121) at p ≤ 0.05.** Also printed: his buys' dmin percentile within their own month, and how many of his buys are big winners under PRE-REG 6's definition (description).
- **What this does not answer:** why he bought (the panel shows holdings, not reasons); his exits.

## RESULT 8 — PRE-REG 6, shelf distance vs EP outcomes 2017-2024 (2026-11-21; build `scripts/probes/_594_outcome_qm_1121/build/run.txt`, blind recount `verify/recount.txt`, adversarial review `review/`)
**NO PRE-REGISTERED VERDICT COVERS THIS — a real but modest lean.** 3,671 EPs ranked within 87 months: big-winner rate (highest close within 60 sessions ≥ 1.5 × gap-day open) bottom / middle / top tercile = 9.6% / 11.3% / 12.9% → ratio **1.36** (bar 1.5: not met), within-month permutation **p = 0.0035** (bar 0.05: met), top above bottom in both eras (A 1.48, B 1.08 — B weak and not monotone). Secondary (description): mean 60-session return +2.5% → +5.6%; share below the open 5 sessions later 52% → 45%. ⚠ The pre-registration's verdict words had a hole (ratio < 1.5 with p ≤ 0.05) — named here, NOT filled after the fact. The recount's 1.407 came from an unregistered survivorship drop (names with < 60 forward bars, which win less); the review confirmed the build's 1.355 on every check (feature never reads the gap-day bar, sealed rows dropped and asserted, terciles and permutation reproduced). The ratio stays under 1.5 on every reading tried (1.355-1.407).

## RESULT 9 — PRE-REG 7, Qullamaggie's EP buys vs same-day EPs (2026-11-21, same files)
**BAR NOT MET.** 62 of 62 of his EP buys matched; 40 on 38 days have same-day scored alternatives (131 pairs): P = **0.603** (bar 0.60, met by about one pair), permutation **p = 0.089** (bar 0.05: not met; 0.078-0.110 across readings). Description: his buys sit higher than their month (median percentile 0.69; 74% above the month median; median dmin −0.1 ADR vs −4.8 for all EPs), and 20 of 62 (32%) were big winners against an 11% base — most of his edge on these is selection the shelf distance does not capture.
