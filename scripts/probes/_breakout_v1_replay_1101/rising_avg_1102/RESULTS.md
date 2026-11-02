# G4 rising averages — RESULTS (2026-11-02)

**Verdict (by the bar fixed in DEFINITIONS.md, commit 512a5bef, before this ran): FAILS — not a candidate list rule.**
It matches every labelled case (MTW out; all 12 of Qullamaggie's caught setups kept at every threshold 3-7%), but the
trades it removes are NOT worse than the ones it keeps, and in 2017-21 random thinning does as well.

| Threshold | (a) MTW out | (b) QM 12 kept | (c1) 5-slot 2017-21 / 2022-24 (need >= -0.139 / -0.340) | (c2) removed worse than kept | (c4) random beats it, 2017-21 / 2022-24 (need < 25% both) |
|---|---|---|---|---|---|
| 3% | PASS | 12 | -0.084 / -0.173 | PASS (-0.124 vs -0.112) | 32% / 0% — FAIL |
| 4% | PASS | 12 | -0.102 / -0.183 | FAIL (-0.108 vs -0.115) | 40% / 2% — FAIL |
| **5%** | PASS | 12 | -0.090 / -0.185 | FAIL (-0.081 vs -0.122) | 42% / 2% — FAIL |
| 6% | PASS | 12 | -0.116 / -0.127 | FAIL (-0.104 vs -0.117) | 68% / 2% — FAIL |
| 7% | PASS | 12 | -0.134 / -0.139 | FAIL (-0.090 vs -0.122) | 72% / 1% — FAIL |

- Floor-only baseline reproduced exactly (983 at -0.139; 556 at -0.340). Parity: 61,071/61,071 pole tops match the
  frozen list; 62/62 look-ahead cuts identical.
- Era split, stated: in 2022-24 the gate beats random thinning at every threshold (random beats it in 0-2% of draws);
  in 2017-21 it does not. The same split as the prior-move bands (prior_move_1102). Two eras disagreeing = no rule.
- Anchors: MTW +2.7%; PENN-2 +8.3% (lowest of the 12); CODX-1 +68.4% at v1's pole top (02-28).
- Code: rising_avg_effect.py; rows rise_rows.tsv.gz; log run.log.
