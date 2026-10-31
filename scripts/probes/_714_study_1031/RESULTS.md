# #714 — float points and neglect, read on his EPs and on the tail (stage 2, 2026-10-31 PT)

Measurement only, $0. Score changes are his (THE LINE): this is a table and the pre-registered recommendation, nothing else.
Plan: `docs/analysis/ep_float_neglect_prereg_2026-10-31.md` (frozen; two dated post-freeze addenda at its end).
Code: `s2_read.py`; full printout: `s2_read_printout.txt`.

## Answer first

- **Float +5 points: NO RECOMMENDATION (the pre-registered rule returns "can't tell").** Nothing supports keeping them and nothing yet proves dropping them.
  - Across all 791 alert-days, under-50M-share names ran big LESS often (9.9% vs 11.1%); his EPs are mostly BIGGER-float than their rivals (5 of 7).
  - The only positive read is the 144 alert-days with a float stored at the time (+11 points), and it comes from one small group (6 of 35 vs 1 of 38). Three alerts exist only because of the +5.
- **Neglect: none of the three new definitions separates real EPs from the pack.** Price-quiet is the only lean, and only on his labelled EPs (not on the tail): "label-only", inside the range chance can produce at 5 readable EPs.
- **One calibration check was mis-written (C3b) and is corrected under a disclosed addendum. The main loop / operator should ratify it (see Section 6); if not ratified, treat every outcome number below as withheld.**

## 1. Who was measured (stated before any outcome)

- **Tail (Population B):** 798 alert-days (scored rows, 2026-05-01 to 10-09; 629 tickers; blocks 327 / 296 / 175). One is censored (short forward window) and one has no dollar-volume, so the tail reads use 791-792.
- **Neglect set:** 662 of the 669 alert-days with 2+ years of price history (7 dropped for gaps in the window); 129 short-history alert-days are excluded from every neglect read.
- **Float known:** 793 of 798 (792 usable after dropping the one alert-day with no dollar-volume). 145 carry a float stored at the time (all from 08-31 on); 648 use a 2026-10-31 yfinance snapshot (same field the live score reads); 5 unknown.
- **His 8 EPs sit on 7 same-day boards of 4 / 26 / 20 / 10 / 10 / 7 / 1 rivals** (ABNB and TEAM share one board, so they are not independent). Readable EPs: float 7, neglect 5 (BFLY thin; HTFL and PENG have under 504 days of history).
- **"Ran big"** = the 15-session high reached at least 5 times the stock's normal daily range above the alert-day close: **86 of 797 (10.8%); by block 15.0% / 6.4% / 10.3%.**

## 2. The table

Tail = does the favourable group run big more often (gap in percentage points; p = the chance of a gap this large by luck alone, one-sided). His EPs = average place among same-day rivals (0.5 = coin flip; 90% chance band shown) and how many readable EPs are above 0.5.

| Definition | Tail: ran big, favourable vs rest (n) | Gap, p | His EPs: mean place (readable) | EPs above 0.5 | Combined word | Plain meaning |
|---|---|---|---|---|---|---|
| **Float under 50M** (all rows) | 9.9% (25 of 252) vs 11.1% (60 of 539) | -2.4 pt, p 0.86 | 0.30 (7), band 0.30-0.70 | 1 of 7 (5 below, 1 level) | **CAN'T TELL (drift)** | Small floats did not run more; his EPs are mostly larger-float names. The stored-float era disagrees (below) |
| Float, stored-float era only (08-31 on) | 15.6% (7 of 45) vs 10.1% (10 of 99) | +11.0 pt, p 0.059 | n/a | n/a | not powered | Positive but 17 runners in 144 rows. The plan's own robustness rule (positive in 2 of 3 time blocks) can never be met by a set that sits entirely in the last block, so no effect size could confirm it: a nominal read the rule cannot elevate |
| **Price neglect** (no big rally in ~2 yrs) | 8.9% (20 of 224) vs 10.5% (46 of 437) | -1.6 pt, p 0.79 | 0.68 (5), band 0.27-0.73 | 4 of 5 | **LABEL-ONLY** | His EPs lean toward quiet price histories, the tail does not; the lean is inside chance |
| **Volume neglect** (quiet volume ~1 yr) | 9.5% (21 of 222) vs 10.3% (45 of 439) | -0.8 pt, p 0.68 | 0.69 (5), band 0.27-0.73 | 3 of 5 | **NULL** | No separation either way |
| **Attention neglect** (few spike-and-move days; a bar-based PROXY for "no news") | 8.2% (19 of 233) vs 11.0% (47 of 428) | -2.8 pt, p 0.90 | 0.69 (5), band 0.27-0.73 | 3 of 5 | **NULL** | Quiet-news names ran big slightly LESS (-2.8 misses the -3.0 "backwards" bar) |

- **Biggest-winner tail (no verdict):** typical top-10% 15-day gain, favourable vs rest. Float 32% vs 32%. Price neglect **19% vs 32%**. Attention neglect **20% vs 32%**. Volume neglect 26% vs 28%. The quiet groups have smaller big-winner tails, partly because quiet stocks move less in raw percent by construction.
- **Robustness the plan required:** none of the four reached PASS or even LEAD. Blocks with a positive gap: float 1 of 3, price 1 of 3, volume 1 of 3, attention 0 of 3. The four companion encodings (price/volume/attention variants) are all negative (-0.3 to -3.6 pt), so none could rescue a read.
- **What a NULL means here (power):** the test would have read a real +10-point effect about 80-84% of the time at the registered 15% base rate (float pooled sat exactly on the 80% line) and 90-94% at the real 10.8% rate. The 90% intervals for the neglect gaps run about -6 to +2/+3 points, so any real benefit is small; effects under about 7-10 points are invisible.

## 3. Float: the pre-registered keep/drop line

- **Separation (his EPs):** mean place 0.30 on "smaller float is better" over 7 readable EPs (PLTR 0.00, ABNB 0.00, TEAM 0.10, MRNA 0.20, HTFL 0.44, BFLY 0.50, CHPT 0.86; PENG thin). Registered word **L?** (5 of 7 below the middle is 71%; the rule needs 75%). The wider-board sensitivity (R2) reads backwards, but only scored rivals have floats, so it is mostly the same rivals. Caveat: his EPs are liquid, large names and bigger names have bigger floats (rank correlation 0.57), so part of this is "bigger company".
- **Tail:** pooled gap -2.4 points (90% interval -6.2 to +1.5); by block B1 -6.9, B2 -2.0, B3 +8.2. Stored-float era alone +11.0 points (p 0.059; every one of its 145 rows is in the last block, so the plan's 2-of-3-blocks rule makes a confirming read impossible whatever the effect), and it rests on the under-$50M-volume group (6 of 35 vs 1 of 38); the same group in the pooled data shows +0.9 (13.3% vs 12.4%, n 350), and the more liquid groups are negative (low-float 2 of 79 vs rest 38 of 362).
- **Alerts that exist only because of the +5: 3** (of 146 alert-days in the window; the +5 was paid on 46). AGX 09-03 (65.0 -> 58.8 without it), VICR 09-17 (65.0 -> 58.8), TLN 10-06 (67.5 -> 61.2). All three were HIGH alerts; **1 of 3 ran big (VICR)**. There is no tier below HIGH on the current table, so the "one tier down" count does not exist.
- **Rule result: NO-REC.** A plain NULL with 3 alerts changed would have meant DROP; the stored-float read (positive, p 0.059) turns the verdict into "can't tell". Float drift check: 47 alert-days with both numbers, median ratio 1.000, none crossed the 50M line.
- **What would settle it:** 102 of the 103 scored alert-days from 10-12 to 10-30 carry a stored float and become readable on 11-21 (an extension of the stored-float read, a new registration, not part of this one).

## 4. Context rows (descriptive, no verdict)

- **D1 stored "episodic_neglect" tag** (alerted rows): 19 tagged, 3 ran big (15.8%) vs 9.1% of the other 275. None of his EPs carries the tag (PLTR, TEAM, MRNA = mature_leader; HTFL, PENG unclassified; BFLY, ABNB, CHPT never alerted).
- **D2 unscheduled catalyst** (alerted rows): 88 unscheduled ran big 12.5% vs 8.3% of 206 scheduled. Of his EPs only MRNA is unscheduled.
- **D3 relative strength:** his EPs were NOT at the bottom before the gap: mean place 0.32 on "weaker is better" (5 of 7 had stronger RS than most rivals); share of the prior ~120 sessions in the bottom 30% of RS: mean place 0.43 (L0).
- **D4 analyst-estimate count:** not measurable; the capture returned no stored estimates for any row (0 of 2,772).
- **D5 Qullamaggie combination** (quiet price history AND gap-day volume 5x its 50-day average): 1 of 6 readable EPs (CHPT) vs 6 of 68 rivals (8.8%); on the tail 57 alert-days, 12.3% ran big vs 9.8% (7 runners, too few to read).
- **D6 float:** cut at 20M +4.3 points (p 0.25), 100M -4.9; runner rate by float fifth 11.3% / 7.6% / 10.8% / 12.7% / 11.4% (n about 158 each); turnover thirds 10.2% / 11.8% / 10.2%. Nothing.

## 5. Still untried

| Candidate | Ran? | Why / result |
|---|---|---|
| Analyst rating-change pace (his corollary: no / slowing upgrades) | **Ran, NOT READ** | yfinance events for 86 tickers. Only 4 of his 8 EPs have 4+ same-size rivals (all large caps), under the 5 needed. Descriptively ABNB, TEAM and PLTR had MORE rating changes in the prior year (73 / 67 / 62) than same-size rivals (medians 49 / 49 / 27), the opposite of "ignored by analysts". `s2_x2_printout.txt` |
| Thin analyst coverage | No | Stored estimates empty in this capture; he ruled it out alone (tiny caps) |
| Headline counts (no news for months) | No | No headline history is stored and there are no Alpaca credentials on this machine. Attention neglect above is only a bar-based stand-in |
| Fund ownership under 20-30 | No | Needs an SEC 13F build (free, heavy) |
| Financial neglect (long flat, then acceleration) | No | Needs SEC company facts with filing dates; lives with #333 |
| Quiet-base shape / beaten-down | Not re-run | Already null or backwards three times (#569, #684/#686, #533) |

## 6. Calibration checks (run before any verdict)

- **C3, the outcome bridge, needed a correction.** C3a (gap-day close in bars = stored baseline close) read 100.0% of 798. C3b as registered (a bar-derived 10-session close-to-close return vs the stored `fwd_10d_pct`) read **2.0% of 797 and failed**. Cause, from the writer (`outcome_tracker._compute_ep_scan_outcomes`): `fwd_10d_pct` is a HIGH-WATERMARK return (max high over the first n sessions vs baseline close), not close-to-close; the registration mis-described it. On the column's own definition the bridge reads **99.9% of 798 (bar 90%)**, a stronger check of the same construction the "ran big" label uses. The freeze text says an addendum cannot alter a check; I applied the correction as a disclosed defect rerun (Addendum 1). **Ratify it or discard the outcome numbers.**
- **Disclosure:** the first attempt (`s2_step3_first_attempt_printout.txt`) printed the overall runner counts (86 of 797, by block 49/327, 19/296, 18/174) before the gate fired. No feature-by-outcome table existed then. `s2_step2_printout.txt` was saved before any outcome was attached; the rerun's STEP 0-2 block is identical to it.
- **C0** look-ahead: 1,822 feature computations, 0 violations. **C1** coverage: neglect 99.0% of eligible, float 99.2% (floor 85%).
- **C2** (registered 15% base rate; false-positive rate at 0 points / power at +10): float pooled 2.5% / 80.0%, float stored-only 0% / 0%, price 0% / 81.5%, volume 0% / 84.0%, attention 0.5% / 81.5%. Size passes (all under 3%). Post-hoc at the observed 10.8%: 91.5% / 0% / 91.5% / 90.5% / 93.5%.
- **C4** positive control: his EPs' dollar volume sits at mean place 0.66 among rivals (7 readable; 0.70 with all 8): passes the 0.60 bar.
- **C5** counterfactual: rebuild reproduces the stored score on 146 of 146 era rows and the conviction-floor part on 146 of 146. Weak spots: the rebuild is circular by construction (the multiplier is worked back from the score), and there was no Bull day in the window (every multiplier is 1.0), so the Bull-day x1.2 path is unexercised.
- **Independent recomputation** (plain loops, own parser) of price, volume and attention neglect plus dollar volume for ABNB, CHPT, MRNA and TEAM matched the pipeline exactly.

## 7. What the data cannot answer

- **Float at the time** for 648 of 793 rows: only a 2026-10-31 snapshot exists. Drift probably biases AGAINST small floats (names that ran often raised equity), so the pooled -2.4 is, if anything, too low; the stored-float era is too small to say.
- **His EPs are a thin test:** 5-7 readable EPs on 4-6 independent boards; the chance band is 0.27-0.73 for neglect and 0.30-0.70 for float. Leg L alone can never produce "separates".
- **Neglect measured only through bars.** Headlines, upgrades, fund counts and multi-year financials were not available (Section 5).
- **Not trading profit:** every number is "how often it ran big", not return under our entry and stop.
- **EPs the system never admitted** have no board at all (ABNB and CHPT appear only because he named them).
- **Block 2 ran big only 6.4% of the time versus 15.0% in block 1**, so "positive in 2 of 3 blocks" is a demanding bar here.
- **The 10-12 to 10-30 fresh block** was not read (it is gated to 2026-11-21 and only applies to a definition that reached PASS or LEAD; none did).

## 8. Files (all in `scripts/probes/_714_study_1031/`)

`s2_read.py` · `s2_read_printout.txt` (the one full run) · `s2_results.json` · `s2_step2_printout.txt` (pre-outcome) · `s2_step3_first_attempt_printout.txt` · `c3_diag.py` (why C3b failed) · `s1b_fetch_float.py` + `out/x1_float.jsonl` (541 tickers, fetched 2026-10-31 20:08-20:19 UTC) · `s1b_fetch_upgrades.py` + `out/x2_upgrades.jsonl` + `s2_x2.py` + `s2_x2_printout.txt` · `s2_f1_strata.py` + `s2_f1_strata_printout.txt` (post-hoc) · `work/dry_run_SYNTHETIC_OUTCOMES_code_test_only.txt` (code test on random outcomes, not a result).
