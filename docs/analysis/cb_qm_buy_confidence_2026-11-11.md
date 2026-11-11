# #717 — how confident are we that each Qullamaggie buy was a breakout, and where was the buy point (2026-11-11)

Operator's ask: *"rate each buy with how confident we know it's a breakout and where the buy point is, then let's
first focus on the high confidence ones to craft initial rules, then expand as needed"*.

**This section (the METHOD) is committed BEFORE the rating is run.** Results are appended below it afterwards.
Nothing here changes a gate; every rule change at the end is a proposal for his sign-off.

## Method and population — the buys (n = 757)
- **269 dated** (n = 269, 2017-2023) — `tests/fixtures/qm_breakout_scorecard/buys.tsv`; the window is the one buy day E. Dated by OUR
  detector, so pre-filtered by our own definition.
- **488 widened** (n = 488, 2017-2022; how it was derived from the 1,040 undated positions is in the fixture README) — `buys_undated_widened.tsv`; the window `lo..hi` (1-5 sessions) comes from his stream panel.
- Bars: the two fixtures only; nothing after `hi` exists in them. Strength rank for the widened nights comes from
  `apollo_data/qm_breakouts_1102/features_eraA.parquet` (ends 2022-03-31), as `20_widened_set.py` read it.
  `features_eraB.parquet` and every 2025-26 store are NOT opened.

## The rating — per buy, bars up to `hi` only
For each session `t` of the window:
1. **The levels it took out.** Walk back from `t-1` (at most 126 sessions). Every bar whose high is above all the
   highs between it and `t`, and below `high[t]`, is a candidate: `level` = that high, `p` = its session, the
   **range** = `p .. t-1`, **range length** = `t - p`. (A flat range gives its top; a down-sloping flag gives its last
   lower high; nested levels are all candidates.) Candidates shorter than 5 sessions are dropped.
2. **Holds its gains** (a run, then a range that keeps it): `level - lowest low of the range` is no more than HALF of
   `level - lowest low of the 60 sessions before p`. A shape ratio, no % and no daily-range number.
3. **Closed above it**: `close[t] > level`. **Volume up**: `volume[t]` above the mean of the 20 sessions before `t`.
4. **Close path** (his "centre of mass, ignore a 1-3 bar spike"): the same walk on CLOSES — `close[t]` above the
   highest close of a range of 10+ sessions, holds-its-gains measured from that close level, volume up. Medium at most.

Tier of the session, first match:
| Tier | Rule |
|---|---|
| **High** | a level with range >= 10 sessions, holds its gains, closed above it, volume up |
| **Medium** | range >= 10 + holds gains but missing the close above OR the volume; or range 5-9 with all three; or the close path |
| **Low** | anything else (see reasons) |
The buy gets its best session's tier (earliest session on a tie). **Buy point** = the LOWEST level that earns that
tier on that session (the first one price crosses). Low buys record the longest level taken out, if any.

Overrides, checked first, in this order (the night `n` = the session before the chosen day, or `lo-1`):
| Category | Tier | Rule |
|---|---|---|
| `fund` | Not-a-breakout | ticker in the hand-marked list below (leveraged / index / sector / volatility funds) |
| `ipo` | Not-a-breakout | fewer than 60 sessions of bars before `lo` |
| `ep_gap` | Not-a-breakout | a window session opens >= 9% over the prior close (the widened set's own screen, applied to the 269 too) |
| `downtrend` | Low | close[n] under the 50-day average AND that average lower than 20 sessions earlier |
| `bounce` | Low | the 126-session low was set in the last 20 sessions AND close[n] is under the midpoint of the 126-session range |
Low reasons otherwise: `no_level` (nothing of 5+ sessions taken out), `gives_back` (a level, but the range gave back
more than half the run), `weak_pivot` (range 5-9 missing the close or volume), `broke_before` (no Medium/High in the
window, but a High on `lo-1` or `lo-2`).

**Fund list (hand-marked from all 276 tickers of the two sets; the fixtures carry no fund names so `fund_rule`
cannot run):** AGQ BOIL BRZU CWEB ERX FAS GUSH IWN JETS KWEB UVXY VXX XRT YINN. SLV and BITO are single-asset funds
our fund rule admits; they are rated on their chart like a stock.

## What is circular (stated before the run)
The rating must not reuse the list gates, but three pieces lean toward gates under test, so those gates' High-tier
miss counts read LOW by construction:
- `downtrend` overlaps `sma50` / `ema21`; "holds its gains" overlaps `base_depth`; "a run before the range" overlaps
  `prior_move`. None uses a % or a daily-range threshold. Step 2 prints how many buys each demoted out of High or
  Medium, beside the miss table.
- Not used at all: strength rank, prior-move %, base depth in daily ranges, ADR, price / dollar-volume floors.

## Checks, declared now
1. **Named examples (main-loop eye, 12-chart sample):** BILI 2021-01-20, ALB 2021-05-27, AXSM 2019-12-27, AAPL
   2020-07-23 must NOT be Low / Not; GAN, ABNB, AGQ, BA, GPOR, VSTM, FCEL (the widened misses) must NOT be High.
2. **His labels on the 269 (cross-check, never a fit target):** tier by good / ok vs no.
3. **Two outcome-blind sheets** (charts end on `hi`, buy point dashed, seed 1111): 12 High (4 dated + 8 widened),
   12 Low / Not (4 dated + 8 widened). I count each chart yes / no: "a run, a sideways range, price leaving it".
   **Pass: High sheet >= 9 of 12 yes AND Low sheet <= 3 of 12 yes.** A miss on check 1 or 3 triggers the ONE
   amendment (dated, written here before the re-run). After it, whatever the sheets show is reported as is.
4. **Sensitivity, reported and not picked from:** range length 8 / 10 / 15; holds-gains ratio 1/3, 1/2, 2/3.

## Step 2 — the High tier against the list (declared now)
- Reproduce first, row by row: 263 of 269 on the list at D; 192 of 488 on any night `lo-1..hi-1` (the fixture has no
  calendar index, so a `history` hole-check difference is explained before anything else).
- High tier: held the night before (dated: D; widened: any night `lo-1..hi-1`, and the night before the chosen
  break day beside it). The two sets are reported SEPARATELY — the 269 hold ~98% by construction.
- Per-gate miss table on High (blocks = fails every night; alone = the only failure on the best night), with names.
- Proposal: per gate keep / loosen / drop, a sweep around each value (plateau, not a peak), recall on High, and the
  cost = how many more Low / Not buys get on the list, plus the pinned labels (26 big winners, his 6 NOs, the 16
  known negatives). **Not measurable here: the list's size over the whole market** — reported as unverified.

## What this does not answer
- Whether a buy MADE money — no bar after `hi` is read; this rates the chart at the buy, not the trade.
- Where he actually bought: the buy point is the most plausible level by rule, not his fill.
- What a rule change does to the list's size over the whole market — only his own 757 buys are scored here.
- Anything after 2022-03-31 for the widened set (era-B bars sit in the store that holds 2025-26; not opened).
- The setup of each widened position is unknown from the panel; the tier is our reading, not his label.
