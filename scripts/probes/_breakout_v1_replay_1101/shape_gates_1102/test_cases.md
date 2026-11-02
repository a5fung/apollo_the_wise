# Unit-test cases for the three shape gates (gates_patch.py)

Runnable: `python3 scripts/probes/_breakout_v1_replay_1101/shape_gates_1102/test_cases_check.py` — 8/8 as expected
(2026-11-02). Synthetic bars: 60 sessions, volume flat, P (the pole top) set to session 30, D = session 59.

| # | Case | Bars | G1 riding | G2 rising lows | G3 no failed attempt |
|---|---|---|---|---|---|
| 1 | MTW 2026-10-30 (his "not a breakout") | real, `_mtw_1102/mtw_bars.csv` to 10-30 | FAIL (10-day: 1 close under, 4 lows > 0.5 ADR under; 20-day: 3 closes under) | FAIL (block lows 21.28 / 21.05 / 21.99) | FAIL (ceiling 23.114; 10-29 high 23.875; close 23.03) |
| 2 | Clean rider | close +0.5% a day, high/low = close +/- 2% | PASS | PASS | PASS |
| 3 | Chopper | close alternates 10.3 / 9.7 around a flat 10 | FAIL (closes under both averages) | FAIL | PASS (no attempt) |
| 4 | Rising-lows base | flat close 10; block lows 9.0 / 9.3 / 9.6 | — | PASS | — |
| 4b | Middle block undercuts (MTW's shape) | block lows 9.3 / 9.0 / 9.6 | — | FAIL | — |
| 5 | Failed-attempt retest | base highs <= 11.0 after P; D-2 trades 11.3; close(D) 10.8 | — | — | FAIL |
| 5b | Attempt that HOLDS | as 5, close(D) 11.2 (above the 11.0 ceiling) | — | — | PASS |
| 5c | No attempt yet (a first breakout) | last 5 highs stay <= 10.9 | — | — | PASS |

For the live test file (`tests/test_breakout_v1*.py`) the main loop would port 2-5c as fixtures and pin case 1 on the
MTW bars; real-data anchors from labels.txt: OPK-2 2020-07-16 and HL 2020-08-03 pass all three (his good setups).
