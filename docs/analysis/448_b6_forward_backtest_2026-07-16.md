# #448 B6 forward backtest — rubric composite_min=22 vs forward outcomes

Cohort: 100 alerts (2026-05-19 → 2026-07-16), re-scored with the CURRENT rubric via the live path (no LLM). Outcome join coverage: 87/100.
As-of alignment: {'value_match': 52, 'n/a': 40, 'date_heuristic': 8} (value_match = exact q0 column identified; date_heuristic rows are the residual-risk subset).

## Fidelity gate (vs 44 live downgrade anchors)
- matched 44 anchors; 28/44 within ±2.0 composite points
- mismatch direction: rederived HIGHER than live in 6, LOWER in 10 (HIGHER-skew ⇒ live-time yfinance fetch failures scored fewer axes — live operational degradation, not replay error)
  - UMAC 2026-05-28: live=12.3 rederived=24.6 Δ=12.3  ⚠
  - AVAV 2026-06-30: live=17.9 rederived=26.9 Δ=9.0  ⚠
  - SNDK 2026-06-25: live=19.5 rederived=26.0 Δ=6.5  ⚠
  - PHR 2026-05-28: live=15.0 rederived=9.4 Δ=5.6  ⚠
  - AVAH 2026-06-02: live=18.8 rederived=13.4 Δ=5.4  ⚠
  - ALNY 2026-07-09: live=20.2 rederived=25.6 Δ=5.4  ⚠
  - GME 2026-06-03: live=17.5 rederived=12.3 Δ=5.2  ⚠
  - ASAN 2026-05-29: live=18.0 rederived=13.4 Δ=4.6  ⚠

## PRIMARY — crosstab on LIVE verdicts (replay-free)
- live PASS       ret_5d: n=  7  mean=  -6.3%  med=  -5.1%  win=  29%   maxhi5d: n=  7  mean=  +9.0%  med=  +5.9%  win=  86%
- live DOWNGRADE  ret_5d: n= 40  mean=  +0.0%  med=  +0.0%  win=  50%   maxhi5d: n= 40  mean= +11.6%  med=  +8.1%  win= 100%
- live downgrade-precision (loser = ret_5d ≤ 0): 50%
- REPLAY LIMITATION (why live-verdict is primary): the as-of column slice leaves ~4 historical quarters where live scoring saw ~5-6, so q1-YoY/accel axes are unavailable in replay more often than live — re-derived composites skew LOW (matches the 10-low/6-high fidelity skew). A full-parity replay needs deeper history (FMP quarterlies).

## Crosstab — REPLAYED verdict at composite_min=22 × forward returns

### PASS (≥22)
- ret_1d       n=  6  mean=  +0.0%  med=  -7.4%  win=  33%
- ret_5d       n=  6  mean=  -6.6%  med= -14.5%  win=  33%
- ret_20d      n=  1  mean= -23.6%  med= -23.6%  win=   0%
- max_high_5d  n=  6  mean= +14.8%  med=  +8.3%  win= 100%
- max_high_20d n=  6  mean= +15.4%  med= +10.2%  win= 100%

### DOWNGRADE (<22)
- ret_1d       n= 41  mean=  +1.7%  med=  +0.4%  win=  51%
- ret_5d       n= 41  mean=  -0.1%  med=  -0.9%  win=  49%
- ret_20d      n= 19  mean=  -0.2%  med=  -0.4%  win=  47%
- max_high_5d  n= 41  mean= +10.7%  med=  +8.1%  win=  98%
- max_high_20d n= 41  mean= +13.4%  med=  +9.5%  win= 100%

**Downgrade precision** (loser = ret_5d ≤ 0): 21/41 = **51%**
**PASS − DOWNGRADE edge (ret_5d)**: mean -6.5pp · median -13.6pp (1R operationalized ≈ 5pp — a typical EP ORB stop; operator may re-cut)

UNSCORED (rubric couldn't score — non-earnings catalysts, safety-net path; NOT gated by the composite): 40 rows. Reference outcome: n= 36  mean=  -3.8%  med=  -0.8%  win=  42%
First 12: IMVT 2026-05-20, ROIV 2026-05-20, TATT 2026-05-20, RL 2026-05-21, LION 2026-05-22, ESLT 2026-05-26, JOYY 2026-05-26, MOD 2026-05-26, BBWI 2026-05-27, QFIN 2026-05-27, IMOS 2026-05-28, SNOW 2026-05-28

## Downgraded WINNERS (the cost side — what 22 threw away)
- WDAY 2026-05-22: comp=13.8 ret_5d=+22.1% ret_20d=? maxhi5d=+23.2%
- BB 2026-06-25: comp=20.0 ret_5d=+18.4% ret_20d=? maxhi5d=+39.8%
- MLKN 2026-06-25: comp=12.0 ret_5d=+17.4% ret_20d=? maxhi5d=+17.8%
- PRGS 2026-07-01: comp=16.0 ret_5d=+16.4% ret_20d=? maxhi5d=+22.5%
- AVO 2026-06-09: comp=0.0 ret_5d=+14.5% ret_20d=+32.0% maxhi5d=+16.8%
- VSAT 2026-06-29: comp=10.8 ret_5d=+13.8% ret_20d=? maxhi5d=+38.0%
- OKTA 2026-05-29: comp=16.0 ret_5d=+10.4% ret_20d=? maxhi5d=+32.4%
- ACLS 2026-06-09: comp=16.1 ret_5d=+10.3% ret_20d=-10.9% maxhi5d=+20.8%
- WGO 2026-06-25: comp=2.0 ret_5d=+9.3% ret_20d=? maxhi5d=+12.4%
- KBH 2026-06-24: comp=0.0 ret_5d=+6.9% ret_20d=? maxhi5d=+12.2%

## Passed LOSERS (the leniency side)
- ALNY 2026-07-09: comp=25.6 ret_5d=-25.2%
- SNDK 2026-06-25: comp=26.0 ret_5d=-22.0%
- MU 2026-06-25: comp=28.2 ret_5d=-20.9%
- AGX 2026-06-05: comp=28.7 ret_5d=-8.0%

## Threshold sensitivity (ret_5d by verdict at each cut)
| cut | PASS | DOWNGRADE |
|---|---|---|
| 16 | n= 19  mean=  -2.8%  med=  -5.1%  win=  37% | n= 28  mean=  +0.4%  med=  +1.1%  win=  54% |
| 18 | n= 13  mean=  -5.9%  med=  -8.0%  win=  31% | n= 34  mean=  +1.0%  med=  +1.1%  win=  53% |
| 20 | n= 11  mean=  -5.6%  med=  -8.0%  win=  36% | n= 36  mean=  +0.5%  med=  +0.0%  win=  50% |
| 22 | n=  6  mean=  -6.6%  med= -14.5%  win=  33% | n= 41  mean=  -0.1%  med=  -0.9%  win=  49% |
| 24 | n=  6  mean=  -6.6%  med= -14.5%  win=  33% | n= 41  mean=  -0.1%  med=  -0.9%  win=  49% |
| 26 | n=  3  mean= -17.0%  med= -20.9%  win=   0% | n= 44  mean=  +0.2%  med=  +0.0%  win=  50% |
| 28 | n=  2  mean= -14.5%  med= -14.5%  win=   0% | n= 45  mean=  -0.3%  med=  -0.9%  win=  49% |
| 30 | n=0 | n= 47  mean=  -0.9%  med=  -0.9%  win=  47% |

## Pradeep explosive-growth bar (T6b add-on: q0≥39% ∧ q1≥39% ∧ guidance≥39%)
- TRUE : n=0   (—)
- FALSE: n= 83  mean=  -2.2%  med=  -0.9%  win=  45%
- projected≥39% uses FY-guidance midpoint YoY as the proxy (the note's 'projected sales'); rows lacking guidance default FALSE.
- leg diagnostics: q0≥39% n=13; of those, q1-YoY KNOWN in replay for 0 (the as-of slice's history-depth gap — see REPLAY LIMITATION above); rows with ANY FY guidance = 4/100. q0∧q1≥39% n=0 (—); outcome: n=0
- VERDICT ON THE BAR: NOT evaluable on this cohort — q1 unavailable in the as-of replay (needs the deeper FMP quarterly pull) and FY guidance is extracted for only a handful of rows. Checked-and-BLOCKED-ON-DATA, not checked-and-refuted.

## Decision matrix (from #448 — the call is the operator's)
- downgrade-precision >80% AND PASS-edge > DOWNGRADE-edge by ≥1R → rubric sound, keep 22
- downgrade-precision <60% → dropping winners, lower the threshold
- PASS-edge ≤ DOWNGRADE-edge → too lenient, raise to 25-28