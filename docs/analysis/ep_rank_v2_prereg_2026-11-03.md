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
