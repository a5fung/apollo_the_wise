# Class A/B/C/Chop/Dead — Classifier Summary

_N=117 HIGH alerts over 60d cohort._

## Distribution + per-class outcomes

| Class | N | Share | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|---:|
| CLASS_A | 58 | 49.6% | 58.3% | +6.3% | +5.9% | 22 |
| CLASS_B | 5 | 4.3% | 100.0% | +8.9% | +8.9% | 4 |
| CLASS_C | 43 | 36.8% | 53.6% | +6.2% | +5.2% | 15 |
| AMBIGUOUS_CHOP | 11 | 9.4% | 12.5% | -2.1% | -4.1% | 3 |
| AMBIGUOUS_DEAD | 0 | 0.0% | — | — | — | — |

**Ambiguous-share** (Chop + Dead) = 9.4%

## Fixture verification

| Ticker | Date | Expected | Got | Match |
|---|---|---|---|:---:|
| TRT | 2026-04-23 | CLASS_B | NOT_IN_COHORT | ✗ |
| ONDS | 2026-05-14 | CLASS_B | NOT_IN_COHORT | ✗ |
| KLAR | 2026-05-14 | CLASS_B | AMBIGUOUS_CHOP | ✗ |
| CPA | 2026-05-14 | CLASS_B | CLASS_A | ✗ |
| CSCO | 2026-05-14 | CLASS_A | CLASS_A | ✓ |

## Class × catalyst quality (proxy for D1)

| Class | game_changer | routine | strong | unknown | total |
|---|---|---|---|---|---|
| CLASS_A | 4 | 3 | 48 | 3 | 58 |
| CLASS_B | 0 | 0 | 4 | 1 | 5 |
| CLASS_C | 2 | 0 | 35 | 6 | 43 |
| AMBIGUOUS_CHOP | 2 | 0 | 8 | 1 | 11 |
| AMBIGUOUS_DEAD | 0 | 0 | 0 | 0 | 0 |
