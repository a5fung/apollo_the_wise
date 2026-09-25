# #519 option A — the result, read against the rules declared before it ran (2026-09-25)

**The one sentence: the model's chart read leans the right way but too weakly to support a decision
(bad on 75% of his condemned charts vs 44% of the charts that worked — a 1.7× lean against a 3× bar),
the book examples made it worse, and only the "really bad" flag cleared its bar — just, with the book
examples, at 3 of 12 and one real EP flagged.**

Pre-registration: `docs/analysis/519_paid_run_scoping_2026-09-24.md` §Option A (rules fixed 09-24,
revised the same day on his notes, before any call). Nothing here was re-scored or re-cut after seeing it.

## Method and population

- **Population:** 64 labelled dates derived from `tests/fixtures/must_not_miss_eps.py` (30 real EPs) and
  `tests/fixtures/must_not_trade_charts.py` (9 approved, 21 condemned, 4 other rejected shown not scored);
  QH 2026-06-18 n/a (39 clean sessions, under the 60 floor). "The 12 the run-up rule misses" derived from
  bars by ANCHOR-75, unchanged from the free read.
- **Run:** `scripts/probes/_519_option_a.py --paid --max-usd 20` in `apollo-market`, 2026-09-25 12:05 ET,
  claude-opus-5-5, anonymised point-in-time charts (daily to the prior close + the alert-day open, weekly
  view on five-year bars), 3 reads × 2 arms (plain; with his 24 book charts) = 384 calls, 0 errors,
  0 truncated. **Spend $13.82** (`api_usage` caller `eval_519_option_a`); the 6-call first batch re-priced
  the run at $16.76 before the rest ran.
- Captured once: `scripts/probes/_519_option_a_out/` (scorecard, reads, run metadata, all 384 raw calls).

## Result, line by line

| line | plain arm | books arm | bar |
|---|---|---|---|
| 1. "bad" on his condemned (n=20 scored) | 15 of 20 | 16 of 20 | — |
| 2. "bad" on the charts that worked (n=39) | 17 of 39 | 24 of 39 | — |
| 3. the lean | **1.72×** | **1.30×** | 3× |
| 4. the lean on the 12 the run-up rule misses | 1.53× | 1.22× | 2× |
| 5. "good" on worked vs condemned | 2 of 39 vs 1 of 20 | 1 of 39 vs 1 of 20 | reported |
| 6. stable reads (all 3 agree, n=63) | 53 | 51 | 42 |
| 8. "garbage" 3/3 on the 12 misses / on the 39 | 2 (ABVX, IPCX) / 0 | **3 (MRLN, ABVX, IPCX) / 1 (QBTS 2026-04-08)** | ≥3 / ≤1 |
| **decision** | **WEAK** | **NO LEAN** | |

- **The lean is real but small.** 1.72× beats the best rule from the books in the free read (~1.5×) and
  is well under the 3× bar. It calls 44% of the charts that worked "bad" — as a filter it would lose
  nearly half the real EPs, which is why the rules scored it as a lean and never as a filter.
- **The book examples hurt.** With them the model called 24 of 39 working charts bad (was 17): it learned
  "what a leader's clean base looks like" and marked everything messier as bad.
- **The "really bad" flag cleared its bar only with the books, and only just:** exactly 3 of the 12, and
  the one working chart it called garbage is QBTS on the 04-08 market-bottom day — the risk named in advance.

## What the pre-registered rules say happens next

- Plain arm WEAK → reported plainly; his call; no automatic next step.
- Books arm NO LEAN → stop; no ~$65 corpus run.
- Line 8 met (books arm) → *"a 'really bad' flag is worth running beside each new alert as data
  collection; whether it ever demotes or removes an alert is his call."* Cost at the tested shape (3 reads
  with the book prefix): about $0.65 per alert — roughly $13 a month at the last month's ~1 alert a day.

## What this does not answer

- **n is small:** 20 condemned, 39 that worked, 12 run-up misses. A 1.7× lean at these counts has a wide
  margin; the flag's pass rests on one chart either way.
- **Returns and the live judge:** the model saw no catalyst text and no outcome; nothing here says what
  the flag would do to results.
- **Other prompts or models:** one prompt, one model, fixed in advance. A different prompt could read
  differently; testing that would be a new, separately priced question.
