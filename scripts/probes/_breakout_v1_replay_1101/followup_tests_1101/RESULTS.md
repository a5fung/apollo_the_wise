# Breakout v1 paper replay — two follow-up tests on the frozen outcomes — RESULTS (2026-11-01)

Registration: `PREREG.md` (this folder), written before any number below. Code: `followup.py` (stages tick | select |
judge). Raw outputs: `selection_2017_21.txt`, `judge_2022_24.txt`, `tick_facts.tsv.gz`, `chosen.json`.
Offline research on the frozen file `../out/trades.tsv.gz`; nothing live changed; any rule change is the operator's call.
R = profit per share divided by risk per share (fill minus stop). All numbers at 2 cents a share each way, the capped
paper book (same-ticker guard + 5 slots), admitted + filled + decisive trades, exactly as the frozen primary row.

## The answer in one line

**Both book fixes help and together they take back about four fifths of the 2022-24 loss (-0.41R a trade -> -0.08R),
but the verdict stays FAIL: the share of trades reaching 3R moves only from 3.6% to 4.9%, far under the 8% bar.** The
book was costing money; fixing it does not make the setup pay as built.

## Gates passed before any read

- Parity: the book re-run by import on the frozen rows reproduced `adm_cap` on all 18,094 placed rows, the blocked
  counts (11,808 / 1,260) and both era lines (2017-21 n 1,058 -0.153; 2022-24 n 581 -0.412).
- The placement tick re-evaluated on the minute bars for all 18,094 placed rows: level and ORH5 equal the frozen
  row on every one; the day-low stop equals the frozen placed stop on every filled, un-re-priced row.
- Lever check: today's order expressed through the synthetic rank = the frozen book on every placed row.

## Test 1 — SLOT ORDER (which name gets a slot when several break out in the same minute)

Selection evidence, **2017-21** (in-sample for this choice):

| order (within a placement tick) | trades | mean R | 95% interval | win | 3R+ share | 10R+ | sum R |
|---|---|---|---|---|---|---|---|
| **today's: strongest first (list rank)** | 1,058 | -0.153 | [-0.34, +0.06] | 34.8% | 5.1% | 1.0% | -162 |
| weakest RS percentile first | 1,028 | -0.128 | [-0.31, +0.08] | 36.5% | 4.9% | 1.3% | -131 |
| **list rank 11+ before 1-10 (CHOSEN)** | 1,071 | **-0.090** | [-0.32, +0.18] | 35.3% | 4.9% | 1.6% | -97 |
| highest volume pace at placement first | 1,122 | -0.203 | [-0.35, -0.03] | 34.0% | 4.5% | 1.2% | -228 |
| tightest stop (share of price) first | 1,146 | -0.182 | [-0.37, +0.06] | 34.1% | 4.5% | 1.2% | -208 |
| random order, 20 seeds (noise floor) | 1,038..1,106 | -0.290 .. -0.129 (median -0.179, sd 0.042) | | | 3.9%..5.1% | | |

Chosen by the rule (highest 2017-21 mean): **rank 11+ first**, -0.090 vs today's -0.153. It sits just outside the
20-seed random range (its top is -0.129) — about one random-spread above it, so a modest separation, not a strong one.
Today's order sits inside the random range on 2017-21.

Judged, **2022-24** (one era, the registration's bar):

| order | trades | mean R | 95% interval | win | 3R+ share | 10R+ | sum R | verdict |
|---|---|---|---|---|---|---|---|---|
| today's: strongest first | 581 | -0.412 | [-0.57, -0.22] | 29.9% | 3.6% | 0.7% | -239 | **FAIL** |
| rank 11+ first (chosen) | 540 | -0.204 | [-0.40, +0.01] | 32.2% | 5.0% | 1.5% | -110 | **FAIL** |
| random order, 20 seeds (reference) | | -0.307 .. -0.079 (median -0.221) | | | | | | |

- Pre-declared read: the chosen order's gain over today's on 2022-24 (+0.21R a trade) is just under the random range
  width there (0.23), so by the rule written in advance it **does not beat today's beyond noise**; it lands at the random
  median. A post-hoc observation from the reference row (not a registered read): **today's strongest-first order did
  worse in 2022-24 than every one of the 20 random orders** (-0.41 vs the worst random -0.31) — the top-ranked names
  are the problem, not the order picked to replace them.

## Test 2 — MINIMUM STOP (refuse a breakout whose planned stop sits too close under the buy level)

Width = buy level minus the day-low stop at the moment the order is placed (what a live rule can check); a refused row
is never placed and holds no slot. Selection evidence, **2017-21**:

| floor | trades | mean R | 95% interval | win | 3R+ share | 10R+ | sum R | placed rows refused |
|---|---|---|---|---|---|---|---|---|
| none (today) | 1,058 | -0.153 | [-0.34, +0.06] | 34.8% | 5.1% | 1.0% | -162 | 0 |
| under 5 cents | 1,035 | -0.088 | [-0.28, +0.14] | 35.9% | 5.2% | 1.1% | -91 | 373 |
| under 10 cents | 989 | -0.011 | [-0.22, +0.21] | 37.1% | 5.3% | 1.2% | -11 | 1,082 |
| **under 15 cents (CHOSEN)** | 986 | **+0.021** | [-0.20, +0.28] | 36.4% | 5.1% | 1.2% | +21 | 1,911 |
| under 20 cents | 971 | -0.013 | [-0.21, +0.21] | 36.4% | 5.0% | 1.3% | -13 | 2,798 |
| under 0.5% of price | 1,045 | -0.093 | [-0.30, +0.13] | 35.1% | 5.2% | 1.1% | -97 | 779 |
| under 1.0% of price | 1,010 | -0.055 | [-0.26, +0.17] | 35.5% | 5.3% | 1.2% | -56 | 1,494 |
| under 1.5% of price | 958 | -0.100 | [-0.28, +0.11] | 35.7% | 5.0% | 1.3% | -96 | 2,615 |

Chosen by the rule: **under 15 cents**. The 10 / 15 / 20-cent floors are within 0.03R of each other — the cents family
clearly beats no floor on 2017-21 (+0.14 to +0.17R a trade), the exact cent is noise. The percent-of-price floors help
less: the damage is in the literal cents (a stop 8 cents away is where 2 cents of cost each way eats the trade).

Judged, **2022-24**:

| floor | trades | mean R | 95% interval | win | 3R+ share | 10R+ | sum R | verdict |
|---|---|---|---|---|---|---|---|---|
| none (today) | 581 | -0.412 | [-0.57, -0.22] | 29.9% | 3.6% | 0.7% | -239 | **FAIL** |
| under 15 cents (chosen) | 520 | -0.209 | [-0.40, +0.01] | 32.5% | 4.6% | 1.0% | -109 | **FAIL** |

- Same sign in both eras: +0.17R a trade on 2017-21, +0.20R on 2022-24. By the pre-declared yardstick (the random
  ORDER range width, 0.23 — a conservative stick for a floor, declared as such) it **does not beat today's beyond noise**;
  the consistency across both eras is the stronger evidence for it.

## The two together (chosen order + chosen floor; read last, not separately selected)

| era | trades | mean R | 95% interval | win | 3R+ share | 10R+ | sum R | verdict |
|---|---|---|---|---|---|---|---|---|
| 2017-21 (in-sample) | 1,003 | +0.008 | [-0.21, +0.26] | 36.8% | 5.0% | 1.6% | +8 | — |
| **2022-24 (judged)** | 506 | **-0.075** | [-0.30, +0.20] | 34.6% | 4.9% | 1.8% | -38 | **FAIL** |

- The combined rule clears the pre-declared "beats today's" read (+0.34R a trade on 2022-24, above the 0.23 random
  width, and +0.16R on 2017-21) — **the book itself was costing about a third of a risk unit per trade**.
- Read it with care: on 2017-21 the two together (+0.008) sit BELOW the floor alone (+0.021) — once the floor is on,
  the order bought nothing in-sample. The combined 2022-24 gain is the floor's +0.20 plus an order effect that shows
  only out of sample, in one era.
- It still **FAILs** the bar: the whole interval is under +0.25R and the 3R+ share is 4.9% against the 8% bar. A move
  from FAIL to CAN'T TELL would have been reported as CAN'T TELL; there was none.

## Verdicts

- **Slot order:** rank 11+ first beats today's on both eras but not beyond the random-order noise; on 2022-24 the
  live strongest-first order is worse than every random order (post-hoc observation). 2022-24 verdict: **FAIL**.
- **Minimum stop:** refuse stops under 15 cents; +0.17R / +0.20R a trade in the two eras, not beyond the declared noise
  stick. 2022-24 verdict: **FAIL**.
- **Both together:** 2022-24 -0.075R [-0.30, +0.20], 3R+ share 4.9%: **FAIL**. Fixing the book removes about four
  fifths of the loss (the floor carries the part that holds in both eras); it does not produce the big winners the
  bar demands.

## What this read cannot say

- The 2017-21 choices are in-sample there; the 10 / 15 / 20-cent floors are indistinguishable, so "15" is a label for
  "about a dime or more", not a tuned number.
- 2022-24 is one era of about 500-580 trades; the replay registration's calibration says a +0.30R population passes
  under a third of the time at any n, so a modest real gain reads CAN'T TELL or FAIL here. None of these rows reached
  even CAN'T TELL.
- The slot order only re-orders names breaking out in the same minute (60% of placements are at the 09:35 tick); a
  different placement policy (waiting, batching, more slots) was not tested.
- Pace and width are read at placement, not at the fill (declared; the two readings differ on 28 of the 218 rows the
  15-cent floor refuses among today's admitted trades).
- The noise floor was measured for the ORDER lever only; the floor lever was judged against it as declared, which is
  conservative.
- Entry, exit, list and costs are the frozen replay's; the tail (about 5% of trades at 3R or better, in every row) is
  untouched by any book rule — that is a selection / entry / exit question, not a book question.
- Paper book effects only; nothing here is a recommendation about live money.

## Disclosed events

- The first draft of the rank lever ranked names per TICK, which broke the book's same-minute cancel tie-break (today's
  order admitted 1,051 instead of the frozen 1,058). Fixed to one order per day (the live job iterates the list in one
  order at every tick), after which today's order reproduces the frozen book exactly. The draft's 2017-21 selection
  file is kept at the scratch path `Cfollow/followup_1101/selection_2017_21_draft1_pertick_rank.txt`; under the draft
  the floor pick was 10 cents (-0.010) rather than 15 (+0.021) — the same "about a dime" family. No 2022-24 number
  had been computed before the fix.

## Independent check (Opus, 2026-11-01) — every number MATCHES; one correction to the READING
- The slot-order idea ("rank 11+ first") came from the audit's finding that ranks 1-5 read worst — pooled 2017-24, so it included 2022-24; split by era, ranks 1-5 were the BEST band in 2017-21 (-0.092) and the worst only in 2022-24 (-0.633). With 100 extra random seeds the 2017-21 random range reaches -0.056, so the chosen order (-0.090) is not separable from random on the selection years. CORRECTED READING: **the minimum stop helps in both eras (stops under 10c lose -1.41R a trade on 2017-21 and -1.82R on 2022-24); the slot order is UNPROVEN.** The verdict stays FAIL in every row. (Files: the checker's recount in the workflow scratch, `Cfollow/`.)
