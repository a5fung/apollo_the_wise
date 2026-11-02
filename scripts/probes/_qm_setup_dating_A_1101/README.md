# Task A — dating the setups Qullamaggie grades in his streams (BACKLOG, next weekend 11-07/08 on his word)

Goal: turn his stream-graded setups into dated examples (this stock, this breakout day, his grade) — grows breakout v1's labelled check set from 24 (the 2020-08-10 stream) to ~420 across the 31 streams with 10+ graded mentions (`apollo_data/cb702/qm_streams/ext_2016_2022/labelled_candidates_ext.tsv`).

State 2026-11-01:
- `calib_v1/`: one reader with `READER_PROMPT.md` (v1.1 has five fixes from the misses, marked [v1.1]) + `bar_check.py`, scored against the 08-10 two-reader reconcile with `score.py`: 66% of the 59 agreed rows within one session (bar 85%) -> NO-GO.
- `calib_optionC/`: one reader + a blind second read of its low-confidence rows + a reconcile: 76% (79% net of join artefacts) -> NO-GO; ~940k tokens for ONE stream. Its weak point: reader 1's high/medium rows that were wrong are never re-read.
- The reliable method (two blind readers + a reconcile, as on 08-10) ~5M tokens for the 31 streams.
- Decide after the spot-check of his 5R+ winners (`scripts/probes/_breakout_v1_replay_1101/qm_vs_v1_1101/`): if selection is the gap, A is worth the cost.
