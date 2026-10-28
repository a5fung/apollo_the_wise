# 2020-08-10 review — his graded setups dated on daily bars, and breakout v1's starting thresholds (2026-10-28)

Two blind Opus daters + an Opus reconcile (`DATING_PROMPT.md`; raw `dating_result_raw.json`). Bars: `cb702_pre_v2/daily_closes_all.csv.gz`, nothing after 2020-08-10.

## Agreement

86 setup rows (A's 86; all 82 of B's map onto them). 67 agree: 57 on the same date, 2 within one session (LVGO-4 7/06 vs 7/07 and OPK-1 6/29 vs 6/30, both settled by one rule: the session whose high first clears the base high, the reading both daters used on ARCT), and 8 undatable for both (still forming on 8/10: BLNK-now, OPK later-this-week, VXRT, WKHS, HG, BILI, ONTX, AVNW). 19 disputed: 7 went to A, 4 to B, 8 to undatable.
Disputed calls that rest on a reason, not a guess:
- TRVN -> 7/15 (A). As-traded prices put 8/03 at 2.50-2.96, so B's "high = 1.85" came from a wrong split guess; 7/15 fits his "sub 1.85 entry, low ~1.72 + 16-cent ATR".
- INO-3 and INO-4: the daters SWAPPED them. "Support on the 20-day" is April (4/20, 28 sessions on the 20-day) and "first bounce of the 50-day ... breakout candle" is June (6/23, +41% on 5.4x); A both times.
- CLSK -> 7/22 (B): 8 sessions of rising lows on the 10-day and a wide day before it, against A's 3-session base.
- ACMR-2 -> 8/03 (A, low). His words: "didn't have much follow through ... small gainer". Walking his sell rule, 7/06 nets +11% and the stock rose +59% within a month; 8/03 nets 0-4%.
- IDEX -> 6/17, MARK -> 5/22, LVGO-1 -> 4/23 (all low): his setups need a prior move, and the other candidate had none.
- IBIO-3 -> 7/17 (B, low): the second breakout, right before the 7/20 run.
Undatable after the dispute: the unnamed 5.5-star chart (the daters disagree on the ticker); CVNA-2 (generic words, and the order of his walk conflicts with the fit); IBIO-2 (may be setup 1 restated); INO-1 (intraday cue, five candidate days); MCRB, NLS-3 and RDFN-1 (no cue words); FSLY/EXPI "this one" (no cue; may be EXPI, which has no bars).
Final confidence over the 86 rows: 14 high, 25 medium, 31 low, 16 undatable. 15 dated rows rest partly on his after-the-day words (flagged in why).
Measures: my own code (rlib.py) matches BOTH daters exactly on every row where they used my final date: every surf run at every k, tightening last-5 vs prev-5, both volume ratios and ADR, with 0 diffs. Three fields depend on the base (higher_lows, last-5 vs first-5, prior_move). They use dater A's mechanical base rule, re-implemented. B set its bases by hand, so those fields differ from B on many rows.
Files are in /private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qm0810_reconcile/:
- results.json: per setup, final dates and all measures
- calibration.txt: every distribution and the per-row values
- baserate.txt and baserate.py
- decisions.py: each call and its reason
- rlib.py: the measurement code
- calib.py, check.py (the 0-diff cross-check), acmr_walk.py and summary.txt

## Calibration

n first. PRIMARY set = both daters on the same date (or within one session) AND final confidence high/medium, his teaching setups only (SPG is out by his own words, "not what I'm trying to teach you"; TTOO and QUMU each count once). n = 33:
- tier A (4.5 stars or more, perfect, really good, very good): 14
- tier B (good, decent, 3.5-4 stars, "a setup"): 10
- tier C (okay, maybe, potential, 3-star, c-star, secondary): 9
His good setups = A+B, n = 24. SECONDARY = the 4 disputed rows I settled at medium (CLSK, INO-3, INO-4, TRVN), which make A+B n = 28; no share below moves by more than 3 points with them.
Grades: tier A and tier B do not separate on any measure at n 14 vs 10 (medians: surf 8 vs 9.5 sessions, tightening 0.86 vs 0.84, volume 1.60x vs 1.44x). Tier C, n = 9, is too small to set anything. So there are no per-grade numbers, only one set for A+B.

1) SURF. The longest run of consecutive sessions, ending the day before the breakout, whose LOW sat within k ADR (above or below) of ONE average.
- k=1.0, A+B (n=24): min 3 | q1 6.75 | median 9 | q3 16 | max 48. The average ridden longest: 10-day 17 times, 20-day 6, 50-day 1 (CWH-2).
- k=0.5, A+B: min 0 | q1 2 | median 3 | q3 5 | max 12. Too tight: >=3 sessions passes only 16/24.
- Share passing at k=1.0: >=3 sessions 24/24 (100%), >=4 23/24, >=5 21/24 (88%), >=6 19/24 (79%), >=8 16/24 (67%).
- PROPOSED v1: >=5 consecutive sessions with the low within 1.0 ADR of the 10-, 20- or 50-day (the same average for the whole run). Passes 21/24 (88%), or 25/28 with the secondary rows. It misses OSTK-2 (3 sessions; graded "really good"; rode the 10-day, then lifted off), OPK-3 (4) and RUN (4; he "would have preferred a few more days").
- Looser variant, where the run may switch between averages (his CODX words: "goes from surfing the 10-day to surfing the 20"): >=5 at k=1.0 passes 24/24 (100%), including OSTK-2 (43 sessions).
- k=1.5 is not proposed. It reads 47 sessions on ARCT (any average) and 63 on OSTK-2 (10-day), longer than either base, so at k=1.5 the run measures the trend, not the base.

2) TIGHTENING. The mean daily range of the last 5 sessions divided by that of the 5 before them.
- A+B (n=24): min 0.47 | q1 0.70 | median 0.86 | q3 0.93 | max 1.16.
- Share passing: <=0.8 10/24 (42%), <=0.9 17/24 (71%), <=1.0 19/24 (79%), <=1.1 22/24 (92%), <=1.2 24/24.
- PROPOSED v1: <=1.1. Passes 22/24 (92%), or 26/28 with the secondary rows. It misses OPK-1 (1.16) and RUN (1.16). At <=1.0 it passes 19/24 (79%).
- The last 5 sessions against the base's first 5 depend on the base rule (bases of 10+ sessions, n=20): median 0.68, q3 0.84, max 1.16. Higher lows held in 20/24.

3) BREAKOUT-DAY VOLUME divided by the 50-day average volume (ending the day before).
- A+B (n=24): min 0.80 | q1 1.24 | median 1.58 | q3 2.00 | max 6.22. Without the four 8/10 rows (full-day volume he never saw while speaking), n=21, median 1.60.
- Share passing: >=1.0 20/24 (83%), >=1.2 19/24 (79%), >=1.5 13/24 (54%), >=2.0 6/24 (25%). Without the 8/10 rows: >=1.2 17/21 (81%), >=1.5 12/21 (57%).
- PROPOSED v1: >=1.2x. Passes 19/24 (79%), 17/21 (81%) without the 8/10 rows, or 22/28 with the secondary rows.
- The SSoT's provisional 1.5x passes only 13/24 (54%). It fails 11 of his 24 good setups, 5 of them tier A: NVAX ("perfect", 0.90), SRNE-2 (five-star, 0.92), OSTK-2 (1.36), DFS (1.24), QUMU (1.28).
- Four good setups broke out on below-average volume (NVAX 0.90, SRNE-2 0.92, OPK-3 0.90, NAIL 0.80), so no volume gate passes all of them.
- In both pairs dated one session apart, the volume came the session AFTER the first break of the base high (LVGO-4 1.6x then 4.3x; OPK-1 1.1x then 2.1x). A gate read only on that first day will miss some setups.

HIS SETUPS vs ORDINARY SESSIONS, at the proposed values:
- surf >=5 at k=1.0: 88% of his good setups vs 43% of ordinary sessions (the any-average variant: 100% vs 52%)
- tightening <=1.1: 92% vs 67%
- volume >=1.2x: 79% vs 29%
- all three together: 75% (18/24, or 21/28 with the secondary rows) vs 5.6%
Ordinary sessions = every session from Mar-Aug 2020 of 1,366 sampled tickers with ADR >=4% and >=$5M traded a day; they are not failed breakouts near a base high. Dollar volume uses split-adjusted prices, so names that later did reverse splits read as more liquid than they were.

## Caveats

- Small and narrow: 24 good setups from ONE stream and one market (the 2020 momentum run), dated by hand from captions. Treat the values as starting points to refine on paper, not fitted thresholds.
- Selection on outcome: he picked these setups in hindsight, several because they worked, and 15 dated rows lean on his after-the-day words (+260%, a double, stopped you out, no follow-through). The pass shares say nothing about false positives. The ordinary-session comparison covers all sessions, not failed breakouts near a base high.
- The four 8/10 rows (NAIL, LAZY-now, TTOO, QUMU) carry full-day volume he could not see when he spoke.
- Surf is a strict consecutive run. One session outside the band resets it, and a tight range sitting above the band also breaks it (OSTK-2 reads 3 at k=1.0; NVAX and OPK-3 read 0-1 at k=0.5). This is a v1 weakness to watch on paper; I did not redesign the measure here.
- Base-dependent fields (higher_lows, last-5 vs first-5, prior_move) change with the mechanical base rule. CODX-1's base spans the March crash (prior_move 22), and OSTK-2's higher_lows flips depending on the base chosen. None of them feeds the proposed values.
- The tie rule for the two pairs one session apart (the first session whose high clears the base high) is mine. LVGO-4 and OPK-1 read differently on the other session; each row's why gives that session's volume.
- The tiers are my mapping of his words. The TSV gave the 0:59:29 "this one / this one too" lines to FSLY, but the captions put them right after "xpi", so they may be EXPI, which has no bars. Both rows are low or undatable and stay out of the calibration.
- Data: split-adjusted bars, nothing after 2020-08-10. Price cues were checked against as-traded closes via the raw/adjusted factor. OSTK is stored as NXH and WTRH as ASAP; CLSK starts 2020-01-24.
- Rules: no network, no subagents, no git. One stray scratch file was briefly written to /tmp/claude-501/p2.txt and deleted at once; everything else is under qm0810_reconcile/.
