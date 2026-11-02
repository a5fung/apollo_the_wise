# Breakout v1 rebuilt from Qullamaggie's trades — the spec for his sign-off (2026-11-02)

**Status: PROPOSED — waiting on his sign-off. Build: Sat 2026-11-07 (his "Yes", 11-02). Paper stays OFF until he turns it on.**
Owner when shipped: `docs/setups/consolidation_breakout.md` (this file is the finding; the SSoT gets the change-log entry with the code).
Work folder (every number below is printed there): `scripts/probes/_qm_breakouts_vs_v1_1102/`.

## Why
- v1's first paper buy (MTW, 11-02) was not a setup by his read. His method, verbatim in `docs/methodology/operator_shared_notes.md` (2026-11-02):
  - *"we have all the winner trades from qullamaggie already, it's proven, we need to trade those and that's it"*
  - *"if you don't trade his setups then it's a gap, if you don't include his big winners than it's a gap ... stick to the rules"*
  - *"get as close as possible, that is the starting point and then work backwards from there to define our rules. If there's still gaps to the remaining few, I will review their charts manually"*
- So the **scorecard** is Qullamaggie's 269 dated breakout buys (`holdings_1024/entries.tsv`, setup breakout|both, 2017-2023, all before the seal) and the 26 big winners among them (5R+ in his replay). **No R, book mean or win rate decided any rule below.**
- v1 today lists **60 of the 269** the night before (22%) and **4 of the 26** big winners (`01_gate_misses.txt`, parity 269/269 with the frozen list files).

## Method and population
- **Rows:** every listable name-night with strength rank >= 30, on every watch night of the frozen replay window (D 2016-12-30 .. 2024-12-30; 2,012 nights; n = 4,227,440 rows), built from bars <= D by `10_feature_table.py` with the live `breakout_v1.v1_gates`. Parity: v1's own rules on this table reproduce the frozen list files exactly (61,071 = 61,071).
- **Qullamaggie's buys:** n = 269 dated breakout buys (2017-2023; 251 era A, 18 era B), each joined to its night D (269/269); n = 26 big winners. Era-A-only measures (the 6-month run-up, tightness, the buy day): n = 245 of his buys on the list.
- **His labels:** n = 95 name-nights (48 ok-or-better, 47 no) — the labelled sets above, never sampled on outcomes.
- **Nothing dated 2025 or later** was read except MTW's own 2026 bars (`_mtw_1102`), as a check only. No trade result (R, P&L, win rate) was read for any rule.

## What this does not answer
- **Whether the rebuilt list makes money.** Deliberately: the job is to list Qullamaggie's setups; returns are a separate, later question (his ruling 11-02).
- **Which of ~250 names a night are setups by his eye** beyond the 95 labels — the order score separates his yes from no only 70% of the time (n = 83 labelled names on the list).
- **2022-24** for the run-up, tightness and buy-day counts (era A only so far; open item 2).
- **The intraday buy:** the buy-day counts use full-day volume; the live rule is an intraday pace (open item 1).
- **The stop and exit**, unchanged from v1.

## The labels behind the rules
- His chart labels, all verbatim in operator_shared_notes 2026-11-02: the 11 buys the first backward pass dropped; 3 blind sample nights (2020-05-07, 2020-09-24, 2021-10-22 — 12 names each, one of them Qullamaggie's buy); the 9 buys an EMA21 rule dropped; the 23 sub-70% run-up buys; the 29 loose-into-the-buy buys.
- In total **95 labelled name-nights** (48 ok-or-better, 47 no). He also called ~15 of Qullamaggie's logged breakout buys "no" or "EP-like" (e.g. YPF, DOCU x2, SQM, W, MRNA 2021-11-29, STNE, ZS, MDB, ANET, TDOC, FEAC, FCX; EP: UPST, NVAX 05-12, EXEL, MU) — they leave the scorecard.
- He picked Qullamaggie's own buy blind on night 1 (PDD); on nights 2 and 3 he did not pick it (NVDA, LCID) — those stay on the list as Qullamaggie's trades.

## 1. The list (nightly, bars up to the watch night D)
| # | Rule | Source | v1 today |
|---|---|---|---|
| 1 | Universe + history unchanged (raw close >= $2, 20-day median dollar volume >= $5M, enough bars) | v1 | same |
| 2 | Strength rank (best of 1/3/6-month) **>= 35** | his buys' lowest: 35.3 | >= 98 (blocked 175 of the 269) |
| 3 | Daily range (ADR20) **>= 2.1%** | his good EW 2.11%, LMT 2.6% | 4.26% floor + 1% pinned gate (11-02 ruling) — the floor would cut EW + LMT, so it is replaced; deal targets under 1% stay out |
| 4 | Base depth from the pole top **1.5 to 9.0 daily ranges** | backward step; low end moved to his good LRN (1.51) | none |
| 5 | Run-up into the pole (v1's measure) **>= 32.1%** | backward step; dropped only his NOs (W, DOCU x2, SQM) | >= 30% |
| 6 | Close **no more than 0.6335 daily ranges under the 21-day EMA** (pin -0.6335: TSLA 2022-04-21's value; -0.63 drops it — stage 0 verifier) | his picks; loosened to keep the 7 buys he rated ok (TSLA 2022-04 lowest) | none |
| 7 | Close **at or above the 50-day SMA** | his picks; drops none of Qullamaggie's buys | none |
| — | REMOVED: higher-lows, riding-an-average, tightening and breakdown as v1 wrote them | his CODX/PENN charts showed the old definitions misread his pattern | all on |

**Effect:** 263 of the 269 kept (the 6 out are exactly his 6 NOs), **26 of 26 big winners**; the list holds **~250 names a night** (median, 2017-2024; ~220 in 2017-22). MTW 2026-10-30 is off (run-up 30.8%). Known miss: MRNA and INO on 2020-08-07 (his "breaking down") still pass.

## 2. The order inside the list (who gets the 5 paper slots first)
- Score = the mean of two within-night ranks: the **6-month run-up in daily ranges** (bigger first) and the **spread of the last 10 closes in daily ranges** (tighter first — his ruling: *"the chart should tighten leading to the breakout, not the full base"*).
- On his 95 labels a yes ranks above a no **70%** of the time. It ORDERS; it never removes (as a cut it would lose most of Qullamaggie's buys: a nightly top 50 keeps 88 of 245).
- v1's 6-month run-up note: v1's pole measure undercounts his moves (225 of 253 of Qullamaggie's buys ran >= 70% over six months; only 149 on v1's measure).

## 3. The buy (the session after the list night)
- Price: the high goes **above the 5-day high** (v1's level, unchanged — the prior day's high adds only 8 of his buys for 6 more breakouts a day).
- Volume: **1.2x the average of the last 10 sessions** (his ruling 11-02, "Yes"; was 1.2x the 50-day average, which carries the run-up's heavy volume). Live it stays the F1 intraday pace curve, against the new bar.
- On daily bars (2017-22): **~24 breakouts a day**; **145 of Qullamaggie's 245 buys fire on his buy day** (was 116), **21 of 26 big winners** (was 15) (`36_trigger_vol10.txt`, `37_buy_level.txt`).
- Stop and exit: unchanged (v1's stop at the day's low, the `pp` exit). Not part of this rebuild.

## Stage 0 results (2026-11-02, Opus build + blind Opus recount; `scripts/probes/_qm_breakouts_vs_v1_1102/stage0/s0.txt`)
- **Live entry replayed minute by minute on his buy days** (all 269 have minute bars in the sealed stores): the NEW volume bar buys **154 of his 263 listed buys** (OLD bar 143), **17 of 26 big winners** (OLD 15); median buy minute 09:41. What stops the rest under NEW: the stop too wide for the 1-daily-range width rule **54**, the pace lapsed and the order was cancelled **25**, the pace never met **18**, the chase cap **6**, the price never reached the level **6**. With no volume rule at all: 193.
- **2022-24:** list median 310 a night; all 18 of his era-B buys on it; 11 fire. **2017-24 combined:** 249 names a night, ~25 breakouts a day (92% of days more than 5), 156 of 263 fire on his day (daily bars), 21 of 26 big winners.
- **The 5 slots:** of his 156 firing buys, **52 rank in their day's top 5** by the order score (78 in the top 10); big winners 8 of 21. His buys rank a median 10th of ~58 firing names that day. The order score picks only a third of his firing buys.
- These three are now his decisions (entry and sizing rules are his): the stop-width rule (54 of his buys), the pace-keep-live cancel (25), and the slot count or a better order.

## Open before the Saturday build (each is free, local data)
1. **Intraday volume pace on his buy days** — ~90 of his buys fail the volume bar on FULL-DAY volume; he bought in the opening minutes, so the fair test is the F1 pace at his buy minute (minute bars `apollo_data/cb702/minutes_rev_1024/`). Decides whether the 1.2x bar holds.
2. **2022-24 (era B) for rules 2-3 and the trigger** — the run-up, tightness and trigger counts above are 2017-22 only; compute on the sealed < 2025 copy before the freeze.
3. **24 breakouts a day vs 5 slots** — the order (section 2) picks; report how many of his buys land in the first 5 of their day.

## Build plan — Sat 2026-11-07 (weekend: deploy windows open)
- `agents/market_intelligence/breakout_v1.py`: the 7 list rules (constants + gates), the removed gates, the order score; `breakout_v1_list.py` writes the score; `broker/breakout_v1_entry.py`: the F1 bar = 1.2x the last 10 sessions (an `execution` deploy).
- Tests: every constant pinned; a scorecard test — Qullamaggie's 263 on the list on their nights, 26/26 big winners (fixtures from this folder); MTW 10-30 off.
- SSoT change log + CHANGE_PROCESS fields; deploy market-agent, then execution, one at a time, polling the box.
- The paper switch `breakout_v1_paper` stays **off**; it turns on only on his word.

## Expectations for the live list (declared before it ships)
- **EXPECT:** the 17:55 ET list holds ~150-350 names (today's v1: ~22-30); each row carries the order score; 0 names under 2.1% daily range; MTW-like slow movers (run-up < 32%) absent.
- **DONE-WHEN:** 5 trading nights of lists with the counts in range and his spot check of one night's top 12 by the order score.
- **WOULD-FAIL-IF:** the list stays ~22-30 a night (old gates still running), or any name under 2.1% daily range appears.
