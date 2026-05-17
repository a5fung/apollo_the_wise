# Theme Context Score — Phase 1 prototype validation

_Computes a theme_context_score (0-10) per labeled alert. Score = membership (0/5) + stage bonus (0-3) + size bonus (0-2). This is ONE INPUT to the eventual meta-rubric — NOT shipped as a filter._

## Score distribution by user label

| User label | N | Median score | Avg score | Range |
|---|---:|---:|---:|---|
| game_changer | 3 | 0.0 | 2.67 | 0-8 |
| game_changer, but Delayed EP | 1 | 8.0 | 8.00 | 8-8 |
| strong | 30 | 0.0 | 2.37 | 0-10 |
| strong, delayed EP | 1 | 7.0 | 7.00 | 7-7 |
| routine_correct | 1 | 0.0 | 0.00 | 0-0 |
| routine_mislabeled | 56 | 0.0 | 0.46 | 0-8 |
| other | 2 | 0.0 | 0.00 | 0-0 |
| No EP | 1 | 0.0 | 0.00 | 0-0 |
| N/A | 2 | 0.0 | 0.00 | 0-0 |

Higher median = operator labeled those names higher AND they had stronger theme context. If `strong` and `game_changer` have meaningfully higher median scores than `routine_mislabeled`, the theme_context input is a useful discriminator.

## Theme context score × forward outcome

| Theme score bucket | N | Wins | Losses | Pending | Win rate | Median ret 5d |
|---|---:|---:|---:|---:|---:|---:|
| 0 (uncovered) | 81 | 24 | 21 | 36 | 53.3% | +5.0% |
| 5-7 (in fading/nascent) | 8 | 3 | 2 | 3 | 60.0% | +5.2% |
| 8-10 (strong theme) | 8 | 5 | 2 | 1 | 71.4% | +13.0% |

## Hypothetical meta-rubric composition (just an illustration)

If we combined catalyst_rubric_score (0-39) + theme_context_score (0-10) at 4:1 weighting, alerts would score 0-49. Final label thresholds would need calibration against operator labels — that's a Phase 2 exercise.

**Critical**: this is a sketch. The meta-rubric also needs technical_structure_score (gap-through-MAs, base shape, distance from 52w high) and gap_alignment_score before it's complete. Those build in a future session.

## Score component breakdown by user label

| User label | Median membership | Median stage | Median size | Total median |
|---|---:|---:|---:|---:|
| game_changer | 0.0 | 0.0 | 0.0 | 0.0 |
| game_changer, but Delayed EP | 5.0 | 3.0 | 0.0 | 8.0 |
| strong | 0.0 | 0.0 | 0.0 | 0.0 |
| strong, delayed EP | 5.0 | 2.0 | 0.0 | 7.0 |
| routine_correct | 0.0 | 0.0 | 0.0 | 0.0 |
| routine_mislabeled | 0.0 | 0.0 | 0.0 | 0.0 |
| other | 0.0 | 0.0 | 0.0 | 0.0 |
| No EP | 0.0 | 0.0 | 0.0 | 0.0 |
| N/A | 0.0 | 0.0 | 0.0 | 0.0 |
