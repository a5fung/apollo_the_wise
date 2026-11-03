# Feature 3 re-defined — "the pullbacks held the top of the base it broke out of" (PRE-REGISTERED 2026-11-03)

Written BEFORE any score on populations A, B or C is computed. The only data looked at before this was
written is KOD's own chart (the calibration case, below). Implementation: `f3_def.py` (the only copy; the
scorer and the KOD check both import it). Everything else — loaders, populations A/B/C, day pools, the
composite, bars (i)-(iii) — is the 11-03 run's own code (`../build/rank_v2.py`, executed verbatim via `rv2.py`).

**Why.** The 11-03 pre-registration's feature 3 measured the pullbacks against "the highest high of sessions
41-250 before D". On KOD that is the 2026-04-22 $47.84 peak — the TOP OF THE RUN, not the base. His read
(KOD 2026-09-28, 11-02): *"the two pull back is into the previous base high (around end of Dec '25)"* — the
~$30 shelf at the top of the Dec 2025-Mar 2026 base KOD broke out of before its run, now acting as support.
So the 11-03 window is kept, but read as what it found: the high that ENDED the run. The new step walks back
from it to the base before the run.

## The definition (all from daily bars <= D, sliced to the 5 calendar years before D, as rank_v2.py)

1. **P — the high before the current base** = the highest high of sessions 41..250 before D (index D-250 ..
   D-41; latest on ties). Unchanged from the 11-03 window; on KOD it is the run's peak.
2. **S — the start of the run that set P** = the lowest low of the 60 sessions before P (P included; latest on
   ties).
3. **The base before the run** = the 45 sessions ending at S (S included). **The shelf** = its highest high
   (latest on ties).
4. **The run must be real** (else the structure is absent): high(P) / low(S) - 1 >= 30%, AND high(P) > the
   shelf (the run broke out above the base's top).
5. **Swing low** (unchanged, rank_v2.py R3) = a session whose low is <= the lows of the 2 sessions before it
   and < the lows of the 2 sessions after it (the encoder's PIVOT_WING = 2, mirrored); the pivot lies in the
   40 sessions before D and both wings lie in bars before D (so the last 2 sessions before D can never be one).
   The pullbacks = **the 2 lowest swing lows** of those 40 sessions.
6. **Distance** of each pullback low from the shelf, in ADR20 units: d = (low / shelf - 1) x 100 / ADR20%,
   ADR20 = the encoder's `adr20_pct` (the same one feature 1 uses).
7. **held = 1** when BOTH d >= -1.0 — each pullback low sits above the shelf, or at most 1 ADR below it
   (the 11-03 R3 reading of "within 1 ADR above it or above it", carried over unchanged). Otherwise 0.

**When the structure is absent** (step 4 fails): **held = 0** — "the pullbacks held an old base high" is
answered *no* when there is no base the stock broke out of. It stays in its day pool (a 0, not a NULL).
**NULL** (leaves its day pool under rank_v2.py R7) only for missing data: fewer than 250 sessions of history,
a run or shelf window that would start before the first bar, no ADR, or fewer than 2 swing lows (R3's rule,
which takes precedence over step 4).

**Sub-read, NOT composite-eligible** (rank_v2.py R1's rule for sub-reads): **into = 1** when BOTH |d| <= 1.0 —
the pullbacks actually reached the shelf (his word "into"), not merely stayed above it. The old
(41-250 peak) feature is carried as a sub-read `held_old` for comparison only. The continuous `dmin` = the
lower of d1, d2 is reported descriptively (chance a yes > a no), never eligible.

## Where each number comes from

| Threshold | Value | Source |
|---|---|---|
| P window | sessions 41-250 before D | the 11-03 pre-registration's own windows (40 / 41-250), unchanged |
| Pullback window, swing low, 2 lowest | 40 sessions, +-2 wing | 11-03 pre-registration + rank_v2.py R3, unchanged |
| Band | 1.0 ADR20 | 11-03 pre-registration, unchanged |
| Run size | >= 30% | Qullamaggie's prior move *"anywhere from 30-100%+"* (operator_shared_notes 2026-10-17); `consolidation_breakout.md` `PRIOR_MOVE_MIN` |
| Shelf window | 45 sessions | his consolidation *"usually 2 weeks to 2 months"*; `consolidation_breakout.md` `BASE_MAX_SESSIONS` = 45 (~2 months) |
| Run window | 60 sessions | **set with KOD's chart in view — the calibration.** The repo's breakout pole window is 40; at 40, KOD's run start is its 2026-03-24 $21.00 low and a 45-session base window reaches back only to mid-Jan (a ~$29.5 shelf, not his end-of-Dec high). 60 (~3 months, the article's "past 1-3 months" outer edge) lets S land on the base's deeper 2026-02-05 $20.88 low, from which the 45-session window reaches 2025-12-24. |

## The scoring (exactly the 11-03 pre-registration's, unchanged)

- **A** (his outcome-blind chart rulings, 17 yes / 37 no): the chance a yes ranks above a no, with n and the
  90% bootstrap interval. Qualifies for the composite at >= 0.65 (direction as A says).
- **B** (his 8 labelled real EPs): how many read held = 1 (all 8 read 0 under the 11-03 definition).
- **C** (the 63 shadow rows): held = 1 vs held = 0 on the matured rows, by the running read's tail test
  (>= 8 x ADR at 5 and 20 sessions, `score_both_directions`).
- **The v2 composite** = the 11-03 rule: the mean of within-day ranks of the features scoring >= 0.65 on A.
  Bar (i) >= 0.70 on A; (ii) >= 80% of B's rankable EPs in the top half of their day; (iii) on C, beat the old
  composite on the tail in both directions. (i)-(ii) pass with (iii) failing = "his eye, not the tail". If the
  new feature misses 0.65, the composite is the 11-03 one (zones cleared alone) and its FAIL stands.
- **Plateau**: each of the six thresholds above at -50% / +50%, one at a time (shelf window 22 / 68, run
  window 30 / 90, P-window end 125 / 375, pullback window 20 / 60, band 0.5 / 1.5 ADR, run size 15% / 45%).
  A result that holds only at the stated value is reported as fragile. The KOD check is re-run at each.
- **No retuning after A is scored.** A miss is reported as a miss.

## KOD check — the only calibration used

Run 2026-11-03 by `kod_check.py` (KOD bars only; output `kod_check.txt`), before any population was scored:

- **Reproduces his read: YES.** P = 2026-04-22 $47.84 (the run's peak) -> S = 2026-02-05 $20.88 (the base's low)
  -> **shelf = 2025-12-24 $31.18** ("around end of Dec '25"); run +129%, above the shelf.
- Pullback lows (the 2 lowest swing lows of the 40 sessions before D): 2026-09-18 $31.54 and 2026-09-11 $32.31
  = +0.21 and +0.66 ADR above the shelf (ADR20 5.52%) -> **held = 1**, into = 1.
- Every +-50% variant keeps held = 1. Two variants move the shelf to 2026-01-22 $29.49 (still ~$30, still held;
  `into` turns 0 because the lows then sit 1.3-1.7 ADR above it): run window 30 and shelf window 22 — the exact
  end-of-December date depends on the 60-session run window, as disclosed in the table above.
- Stated plainly: the 2026-09-24 $29.81 low is not counted (it is 2 sessions before D, so it cannot be a swing
  low under R3); and the 40-session window sees only KOD's SEPTEMBER pullback, not the June one (~$29.2) — "the
  two pull back" in his read are likely both. Kept unchanged on purpose: only the shelf was misdefined.
- **This is the only calibration used.** No other ticker's feature value was looked at before scoring.

## RESULT — 2026-11-03 (written after scoring; `rank_v2_f3.txt`, `f3_features.tsv`; nothing above was changed)

**FAIL as pre-registered.** The re-defined feature 3 reads **0.607 on his rulings** (16 yes / 28 no; 90% interval
0.49-0.73) — under 0.65, so it does not enter, the v2 composite stays zones-cleared alone, and the 11-03 FAIL stands
((i) 0.555 FAIL · (ii) 6 of 6 PASS · (iii) FAIL at 5 and 20 sessions). Untouched features reproduce 11-03 exactly.
- **A:** held = 1 on 8 of 16 yes vs 8 of 28 no. Sub-read `into` (pullbacks actually reached the shelf, his word) 0.50.
- **B:** 1 of his 7 scoreable EPs reads held (PENG — its lows sit 16.5 ADR ABOVE the shelf, never pulled back to it);
  MRNA's lows sit 2 ADR under its shelf; HTFL is NULL (short history). Was 0 of 8.
- **C:** held = 1 vs 0 — 5 sessions: 1 tail winner each, more losers with held (67% vs 61%) -> LOSS; 20 sessions:
  1 vs 2 winners, fewer losers (62% vs 67%) -> MIXED.
- **Plateau:** 0.572-0.670 across the 13 settings; it reaches 0.65 only at the 22-session shelf window (-50%) ->
  fragile. Even there the composite fails (i) (0.54) and (iii) -> FAIL at every setting. Forced in beside zones
  cleared (not the bar): (i) 0.53, (ii) 5 of 5, (iii) LOSS both horizons -> FAIL.
- **Descriptive only (pre-declared above as never eligible):** the continuous distance of the lower pullback low
  from the shelf reads 0.688 (yes median -0.4 ADR, no median -3.4). A lead, not a result: it would need its own
  pre-registration and labels not yet seen.
