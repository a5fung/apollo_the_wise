# #644 correction test - outcome A (bounce 11-20 -> 11-27)
Prereg: docs/analysis/644_correction_resilience_prereg_2026-11-28.md (ab77a4d9). Script: score.py. Raw: results_A.json.

## Verdict A: FAIL (gap < 0 and p = 1.0)
- Population: 130 themes (all themes with >=3 tickers in week 2026-11-16; every one also had >=3 tickers with scores and closes on 11-20 and 11-27). Thirds of 43 / 44 / 43.
- SPY bounce 11-20 -> 11-27: +5.58%. Lookback = 33 sessions (SPY sessions 10-07..11-20). Seed 644, 10,000 shuffles, one-sided.

| third | median score | median excess vs SPY |
|---|---|---|
| top (held up best on down days) | +0.92% | -1.52 pp |
| middle (not judged) | - | -0.21 pp |
| bottom | -0.27% | +2.68 pp |

- Top minus bottom gap: -4.20 pp; permutation p = 1.0 (one-sided).
- Overlap-dropped variant (drop themes sharing >50% of tickers with a higher-ranked theme): nothing was dropped (130 themes), result identical.
- Board share (top-30 board): week 11-23: top third 25.6%, middle 6.8%, bottom 25.6%. Week 11-30: not in the grid yet.
- Per the prereg, the bounce favouring high-beta names (low resilience) is the expected failure mode, so A alone decides nothing; B decides.

## Deviation to flag (disclosed, not substituted)
- Prereg says `as_of=2026-11-20` with the window 10-07..11-20 inclusive. The real function uses sessions STRICTLY BEFORE as_of, so as_of=11-20 scores 10-05..11-19 (11-20 excluded, two sessions before the window included). The verdict above follows the literal as_of=11-20.
- Sensitivity (as_of=11-23, covers exactly 10-07..11-20): gap -3.32 pp, p = 1.0, FAIL; overlap-dropped (129 themes) gap -3.09 pp, FAIL. Same verdict either way.

## B
- Reads 2026-12-11: re-pull closes.out (SQL through 12-11), then `python3 score.py B` (window 11-27 -> 12-11, same population and scores).
- Resilience is called predictive only if B passes and A is not a FAIL. A is a FAIL, so B cannot make it pass by the prereg's rule; B is still reported.
