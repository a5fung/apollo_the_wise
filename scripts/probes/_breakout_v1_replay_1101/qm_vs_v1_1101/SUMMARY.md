# Qullamaggie's 28 biggest trades vs breakout v1: what v1 misses (2026-11-01)

**The answer:** with today's 5-slot limit, v1 took none of Qullamaggie's 28 trades of 5R or more to 5R. On the night before he bought, only 4 of the 28 were on v1's list. Most of what kept them off (the strength cut and the base-shape checks) shows up just as often on his losing trades, so loosening those checks would mostly add losers. One pattern is more common on his winners: v1's buy level sits well above his buy point.

- R = profit per share divided by the risk per share.
- "His R" = his buy (dates from his positions panel) replayed with our entry and exit. It is not his own profit and loss.
- Window: 2020-01-27 to 2022-06-14. Local files only, $0, nothing from 2025 or later.

## What v1 did on his buy day (the two readers reconciled)

| what v1 did | trades | detail |
|---|---|---|
| Not on the list the night before | 19 | strength under 98: 15 · tightening: 2 · riding a moving average: 1 · higher lows: 1 |
| Bought the same stock on a different day (10 sessions before his buy up to his sell) | 8 | Judged on the buy nearest his day, 5 lost money. The one big gain was NIO: +16.5R, bought 11 sessions after him at a 27% higher price, and turned away because all 5 slots were full |
| Bought his exact day, sold too early | 1 | NVAX: same day, same price. v1 made +0.6R, he made +5.9R |
| Matched (5R or more) | 0 | |

- Two of the 28 were news-gap buys (BE 2020-06-30, VXRT 2020-07-13). A breakout list is not built to catch those.
- SI 2021-01-22 is not a real miss. v1 held SI from 2020-11-17 to 2021-01-21 for +13.7R and sold the day before he bought.

## Did the two readers agree?

| measure | agreement |
|---|---|
| Same class label | 15 of 28 (54%) |
| Listed or not, and which check failed, on his buy night | 28 of 28; one refusal reason corrected (CODX 07-16: volume, not price) |

All 13 label differences come from the two readers' rules, not from different facts:

| why the labels differed | trades | settled as |
|---|---|---|
| The builder counted any listed night within 20 sessions; the blind reader counted only the night before his buy | 7 (APT 02-21, BE 06-30, BE 08-13, JMIA 11-18, SKLZ, APHA, TLRY) | Not listed on his night. The other listed nights were other days, refused as "stop too wide" or "low volume" |
| The builder counted v1 buys 14–20 sessions away or after his sell | 3 (PDD, APT 06-17, BE 01-06) | Not listed. Those buys were a different base |
| The builder counted a buy that v1's one-stock-at-a-time rule had blocked | 2 (SHOP, SI) | Not listed. v1 already held the stock (SHOP +0.2R, SI +13.7R) |
| The builder called a late re-entry a match | 1 (NIO) | Bought later. The 5-slot book refused it |

- CODX 2020-07-16: the daily bars show his day's high did cross v1's level. The day traded only 0.63× its average volume, so the volume check, not price, kept the order off.

## What v1 is missing: the short list

Each pattern is counted three ways, so that a fix which catches his winners can be checked for how many losers it adds. His 205 trades split into 28 winners (5R or more), 129 losers (0R or worse) and 48 in between.

| # | pattern | his 28 winners | his 129 losers | v1's own trades (1,884 in the window) | next test |
|---|---|---|---|---|---|
| 1 | **v1's buy level is above his buy point.** v1 buys over the 5-day high; his buy point was more than 3% lower | 12 (43%) | 36 (28%) | Not supported on v1's side. Its trades with a level more than 3% above the prior day's high did better (average +0.29R vs +0.03R) | Set the level at the prior day's high. Re-run the entries on the 98 list, then count his 205 caught and v1 losers added. It only helps names already on the list |
| 2 | **Strength under 98 the night before** | 17 (61%) | 80 (62%) | The cut at 90 was already run (5-slot book, all years 2017–24): +77 trades, +47 losers, +2 at 10R+. It failed on 2022–24 | No test on strength alone, because it looks the same on his winners and losers. Re-try the 90 cut only together with test 1 |
| 3 | **Base-shape checks reject his base** (riding a moving average, higher lows, tightening) | 15 (54%); 7 (25%) with strength fine | 62 (48%); 19 (15%) with strength fine | Not measurable yet: every v1 trade passed these checks | Re-list without the moving-average check, the biggest single blocker (9 winners). On its own it adds 2 of his winners and 6 of his losers |
| 4 | **Buy-day volume under 1.2× the 50-day average** | 10 (36%) | 59 (46%) | Full-day volume is higher on v1's winners too (48% of its losers were under 1.2× vs 27% of its 5R+ winners). Part of that is the move itself bringing the volume, and full-day volume is only known at the close | No case for lowering the bar. A fair test would use the intraday volume pace at the minute of the order |
| 5 | **Buying the day after a wide up day** (that day's range above one average daily range) | 5 (18%) | 22 (17%) | 489 trades: 68% lost, average −0.12R vs +0.14R for all other trades; 16 of its 67 5R+ winners | Skip the buy on the day after a wide up day. It mostly removes v1 losers, and it blocks his winners and losers at the same rate |

- Left off the list: today's exit selling early. NVAX is the only case. On v1's 77 trades that sold a third at +2R and were then stopped at cost the same day, holding with the speed trail would have lost on 74.
- Left off the list: the 5-slot limit, which turned away NIO's +16.5R. The slot-order test was already approved on 11-01.

## Action

None. Each next test is a candidate for the operator's ruling; no rule is changed.

## Files (`/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/qm_vs_v1_1101/reconcile/`)

- `agreement.tsv`: per trade, the builder's class, the blind reader's class, the reconciled class and a one-line resolution.
- `patterns.txt`: every pattern count, for his 205 trades by group and for v1's 1,884 trades in the window.
- `his205_nights.tsv`: v1's checks on the night before each of his 205 buys. They match the frozen list files on all 205 nights.
- `v1_fills_window.tsv`: v1's trades in the window, with buy-day facts.
- `01_his205_and_v1_fills.py`, `02_patterns.py`, `03_agreement.py`, `01_run.log`

(Written by the main loop from the reconcile step's return — the subagent could not write report files. Builder: build/; blind second reader: blind/ (rule.txt written before any trade was classified); reconcile: reconcile/.)
