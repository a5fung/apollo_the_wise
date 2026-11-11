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

## AMENDMENT 1 (2026-11-11, the ONE allowed; written before the re-run)
**Why:** the first run (`01_rate_first.out`) failed check 1 — BILI, AXSM and AAPL rated Low `no_level` — and put 21 of
his 37 good / ok dated buys in Low (n = 37). Reading the bars showed a defect in the method, not in those charts:
- **Range length was the AGE OF THE HIGHEST HIGH, not how long price went sideways.** NVAX 2020-02-24 took out 18
  sessions of highs, but the top of that range was printed 4 sessions earlier, so it counted as a 4-session range and
  was dropped. A flat range touches its top several times; the last touch is not its start.
- **Many buys are a short pivot INSIDE a range** (TSLA 2020-09-21, AMD 2021-08-23, MARA 2021-11-30 — the down-sloping
  line, "a lower entry than what we call a breakout"). The method had no place for them.
What the first run also showed and is NOT changed: AAPL 2020-07-23's only window day fell 4.5% and took out no prior
high; BILI 2021-01-20 was making a new high almost daily with no range behind it. If they stay Low, that is reported.

**Changes (everything else as above):**
1. **Range start.** For a candidate level, the range starts at the EARLIEST session, among the sessions whose highs it
   stands above, whose high came within one average daily range of the level (mean of high - low over the 20
   sessions before `t`, in price — a unit of measure, not a threshold on the stock). Range length = `t` - that start.
   Holds-its-gains is measured on this range (its low vs the 60 sessions before its start).
2. **New Medium path `inside_range`:** the highest high of the 60 sessions before `t` is 10+ sessions old, the stretch
   since it holds its gains (same half rule), and `t` takes out the highs of 3+ sessions and closes above them.
   Buy point = the highest of those highs. Checked after the other Medium paths.
Check 1 keeps its wording; the sheets' pass bar is unchanged; sensitivity grid unchanged.

---
# RESULTS (after amendment 1; `01_rate.out`, `ratings.tsv`, `03_high_vs_list.out`, `04_run_measure.out`, `05_missed_high_sheet.out`)

## Tier counts (n = 757)
| Set | n | High | Medium | Low | Not-a-breakout |
|---|---|---|---|---|---|
| dated (our detector's) | 269 | 53 | 65 | 125 | 26 (all `ep_gap`) |
| widened (his panel) | 488 | 31 | 51 | 349 | 57 (`fund` 35, `ipo` 22) |
- Low, widened (n = 349): `no_level` 195, `downtrend` 71, `gives_back` 40, `weak_pivot` 34, `broke_before` 5, `bounce` 4.
- Low, dated (n = 125): `weak_pivot` 57, `no_level` 33, `gives_back` 27, `broke_before` 5, `bounce` 3.
- Buy point, the day it was taken out and the range length are in `ratings.tsv` for every buy that cleared a level.

## The declared checks — the rating does NOT pass them; reported as is (the one amendment is spent)
1. **Named examples: FAIL.** ALB High (ok). BILI, AXSM, AAPL stay Low `no_level`: AAPL's only window day fell 4.5% and
   took out no prior high; BILI was at a new high almost daily with no range behind it; AXSM is a 4-session flag after
   a gap. FCEL 2020-02-10 came out High (a 12-session flag after a tenfold run on the adjusted chart).
2. **His labels (dated, cross-check):** his `no` (n = 19): 0 High, 1 Medium. His good / ok (n = 37): 8 High, 10 Medium,
   17 Low, 2 Not. Big winners (n = 26): 11 High, 6 Medium, 9 Low. So High is clean of his NOs but holds under a
   quarter of what he calls good.
3. **Sheets (my count, "a run, a sideways range, price leaving it"):**
   - `sheet_high.png`: **8 of 12 yes** (bar was 9). The four no — SLV, HEXO, AVLR, BNGO — are range breaks with no
     run before them (a fund in a flat year, two fallen stocks, a weak recovery).
   - `sheet_low.png`: **5 of 12 yes** (bar was 3 or fewer). TSLA 2020-05-08, CCL 2021-03-12, PDD 2020-09-01 (short or
     unconfirmed pivots at the top of a real base), XPEV (`ipo`, a run and a flag), MARA 2021-02-08 (`ep_gap`, a base
     broken by a gap).
   - **Plainly: High mostly looks like breakouts; Low is NOT "not breakouts".** Low means the daily bars of the window
     do not confirm a range break by this rule — a mix of non-breakouts and real setups bought early, on a short
     pivot, or on a day that never closed through.
4. **Sensitivity (High, dated / widened):** range 8 / 10 / 15 sessions at the half rule: 65 / 37, 53 / 31, 36 / 18;
   give-back 1/3, 1/2, 2/3 at 10 sessions: 34 / 15, 53 / 31, 67 / 46. The tier is not stable to these choices.

## Step 2 — the High tier against the current list
Reproduced first: 263 of 269 dated on the list at D; 192 of 488 widened on any night; 0 row mismatches.
| Set | Tier | n | On the current list |
|---|---|---|---|
| dated | High | 53 | 53 (by construction — our detector dated them) |
| widened | High | 31 | **10** (the night before the rated break day: also 10) |
| widened | Medium | 51 | 33 |
| widened | Low | 349 | 149 |
| widened | Not | 57 | 0 |

**Per-gate misses, widened High (n = 31, 21 missed; blocks = fails every night, alone = the only failure):**
| Gate | Blocks | Alone | Names |
|---|---|---|---|
| prior move >= 32% | 9 | 7 | PBR 2019-10-22 (two rows), BYND 2020-09-29, ALB 2021-05-27, ALB 2021-07-09, ABNB 2021-11-05, NUE 2022-01-05 (21-30%); + AVLR, SLV |
| close above the 50-day | 9 | 6 | DHT 2019-12-19 (-0.6%), BCRX 2020-06-26 (-0.1%), DKNG 2020-08-18 (-1.7%), FSLY 2020-09-21 (-2.2%), AMD 2021-10-13 (-1.5%), LCID 2022-01-10 (-10%); + AVLR, HEXO, NVAX |
| strength rank | 5 | 1 | FCEL alone; BNGO, INO, HEXO, SLV — all UNRANKED that night (not in the 11-02 cross-section), none ranked under 35 |
| price / dollar volume | 3 | 0 | BNGO, INO, HEXO |
| base depth | 1 | 0 | HEXO |
| history (86 sessions) | 1 | 1 | PLTR 2021-01-22 |
| 21-day EMA | 1 | 0 | NVAX |
- Circularity control (widened High under looser ratings): holds-its-gains OFF n = 61, base depth still blocks 1;
  both leaning pieces OFF n = 86, base depth blocks 3, prior move 31, the 50-day 31. **Base depth is not what drops
  the confirmed range breaks**, with or without the piece that overlaps it.
- My eye on all 21 missed (`sheet_high_missed.png`): the 6 dropped by the 50-day alone all look like breakouts (a
  flag pulled back to the 50-day); the prior-move 7 are multi-month base breaks with no recent run (PBR no; ALB, NUE,
  ABNB, BYND marginal); BNGO, HEXO, SLV, AVLR, NVAX no; INO, PLTR, FCEL yes.

## Proposed initial rules (NOT wired — each needs his sign-off; counts are on the list / n)
| Gate | Proposal | Widened High (n = 31) | Widened Low on the list (n = 349) | Pinned labels |
|---|---|---|---|---|
| close above the 50-day | **LOOSEN to "no more than 3% under the 50-day"** | 10 -> 16 | 149 -> 164 | 26 / 26 big winners; none of his 6 NOs back; 16 / 16 known negatives (already on) |
| prior move >= 32% | **KEEP — his call** (loosening to 20% gives 10 -> 17) | 17 | 149 -> 178 | **4 of his 6 NOs come back (W, DOCU x2, SQM)** |
| base depth 1.5-9 daily ranges | keep | 10 (no change at any cap) | 149 -> 150 | dropping the cap brings back YPF, MRNA |
| strength rank >= 35 | keep | 10 (30, 20: no change; dropped: 11) | dropped: 17 funds / young listings get on | none |
| 21-day EMA, ADR, pinned, universe, history | keep | 0-1 each | - | - |
- **Plateau, the 50-day:** -2% 14, -3% 16, -5% 16, -10% 16, dropped 16 of 31; Low 160, 164, 167, 173, 179 of 349.
- **Plateau, prior move:** 30% 11, 25% 13, 20% 17, 15% 17, 10% 17, dropped 17 of 31; his NOs back at every step (4).
- **No second run measure separates them:** "prior move >= 32% OR the 6-month run-up >= X" returns W and DOCU at
  every X from 30% to 100% (their 6-month run-ups are 252% and 156%; ALB's is 109%, NUE's 47%, PBR's 27%).
- Both together (50-day -3%, prior move 20%): 24 of 31 High; Low 202 of 349; 4 of his 6 NOs back.
- **The fork for him:** the prior-move gate is the one place the High tier and his own NOs disagree. ALB / NUE / ABNB
  (clean range breaks, 22-30% run) sit on the same side of every run measure tried as W / DOCU / SQM.

## Not verified
- What "3% under the 50-day" adds to the list over the whole market per night — not measurable on his buys alone.
- The rating failed its own eye bars (8 of 12, 5 of 12) and is unstable to its two knobs; the High tier is a usable
  clean core (0 of his 19 NOs), not a complete census of his breakouts. n = 31 widened High (PBR counted twice).
- The fund list is hand-marked. My eye is not his: `sheet_high_missed.png` is the sheet for him to grade.

## What this does not answer
- Whether a buy MADE money — no bar after `hi` is read; this rates the chart at the buy, not the trade.
- Where he actually bought: the buy point is the most plausible level by rule, not his fill.
- What a rule change does to the list's size over the whole market — only his own 757 buys are scored here.
- Anything after 2022-03-31 for the widened set (era-B bars sit in the store that holds 2025-26; not opened).
- The setup of each widened position is unknown from the panel; the tier is our reading, not his label.
