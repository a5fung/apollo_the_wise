# The stop-too-wide filter — first cohort read, and its decision matrix cannot fail (2026-09-16)

**Answer first: at n = 11 the rejected names cannot be separated from the ones we admit (p = 0.14),
though they run at about HALF the admitted hit rate. There is no evidence the filter sheds winners.
The review's own REVISIT bar fires — but it fires on absolute numbers that a cohort running at half
the admitted rate still clears, so the bar does not mean what it says.**

🔴 **This doc was corrected the same evening it was written, after an advisor pass. Two population
errors, and one of them is this doc's own thesis committed against itself — see
"Corrections" below. The verdict and the recommendation survive; three numbers did not.**

MEASURE-ONLY, $0. No threshold proposed. The stop filter is entry discipline = THE LINE.

## Population — declared before the first measuring query

| | |
|---|---|
| **Cohort** | every `setup:stop_too_wide` rejection with `signal_type = 'magna53'`, `alert_date >= 2026-05-05`. **n = 11 distinct ticker-days** (first reported as 20 — see Corrections) |
| **Scope, deliberate** | `9m_day2` shares the skip-reason prefix and is a DIFFERENT filter — excluded, per the entry's own 2026-08-17 fix. `account_mode` is **not** filtered: these are SKIPS, no position was taken, so the stock's forward path is account-independent |
| **Control** | magna53 trade rows that **actually entered** (no `skip_reason`, status not cancelled/skipped), same dates — **n = 25**. The review's matrix does not ask for this; it is the comparison that decides the question |
| **Statistic** | max high over d+1..d+5 against the gap-day open, from `mi_daily_closes` — **both cohorts scored identically** |

## ⚠ Units — the first reading was wrong and would have inverted the verdict

`max_high_5d` and `ret_5d` are **fractions measured from `open_d0`**, not percentages. Reconciled
against raw bars rather than assumed: SDOT 2026-06-26 stores `8.2174` against a $106.00 high;
RETO 2026-09-10 stores `48.2908` against a $20.85 high off a ~$0.42 open.

Read naively, the matrix's "+10% hit" becomes `max_high_5d >= 10` — i.e. **+1000%** — and the cohort
returns a **0.0% hit rate**, which reads as a clean KEEP. That is the opposite of what the data says.

## The result

| | n | hit rate (MFE ≥ +10%) | median MFE 5d |
|---|---|---|---|
| **rejected for a wide stop** | 11 | **36.4%** | +8.6% |
| **admitted — actually entered** | 25 | **68.0%** | **+14.6%** |

**The rejected names run at roughly half the admitted hit rate — and it is still not callable.**
Fisher on the hit rate: **p = 0.141**. The direction points toward the filter doing its job rather
than shedding winners; at n = 11 that is a direction, not evidence.

## 🔴 The finding that outlives the numbers: this matrix could only ever say REVISIT

The pre-registered decision rule was:

- **REVISIT** if 5d hit-rate ≥ 30% **and** median MFE ≥ +8%
- **KEEP** if 5d hit-rate < 20% **or** median MFE < +3%

**The rejected cohort reads 36.4% and +8.6% — it clears BOTH REVISIT bars while running at half the
rate of what we actually take (68.0% / +14.6%).** So a cohort can be materially worse than the
admitted book and still fire REVISIT, because the bars are absolute. The KEEP arm would require the
rejected names to be less than a third as good as what we trade. The bars were set in 2026-05 from
two anomalies (STRL, AIP) without ever asking what the base rate was.

**The true control makes this sharper than the first version of this doc did.** Against the
mislabelled 50.3% control the gap looked like noise; against the real 68.0% it is a visible gap that
the matrix is structurally unable to react to.

This is the third instance of one defect in seven days: **a rejection cohort's absolute numbers mean
nothing; the comparison that decides a filter is against what it ADMITS.** The HTF ADR floor was the
same shape on 2026-09-10 — 8,976 excluded ticker-days looked damning until the admitted population
turned out to convert at 4.91% against the band's 2.38%.

## Recommendation — keep as-is, and re-gate on a bar that can fail

1. **Keep the 1.5× multiple.** Nothing here supports widening it. The rejected cohort is not better
   than what we take — it is running at about half the admitted hit rate — and at n = 11 even that
   gap is not callable (p = 0.14).
2. **Do not test options (a) widen to 2.0× / (b) change the stop anchor / (c) tier by score** on this
   evidence. They were written for a "filter sheds winners" finding that did not materialise.
3. **Re-gate to n = 20 with CONTROL-RELATIVE bars** — the rejected cohort must beat the admitted
   population's hit rate by a stated margin, not clear an absolute number. Bars that any healthy
   population clears are not bars. **The control is now specified, not merely demanded:** entered
   magna53 trade rows, MFE from `mi_daily_closes` over d+1..d+5 — never from
   `mi_ep_missed_outcomes`, which cannot contain an admitted name. **20 is power-justified, not
   guessed:** if the observed 36.4% / 68.0% rates hold, rejected n = 20 against admitted n = 40 gives
   Fisher p = 0.027. ⚠ It was set to **40** earlier the same day, against a cohort I believed stood
   at 20. The predicate returns **10**, and rejections accrue about 2.4 a month (5 May, 0 Jun, 1 Jul,
   4 Aug, 1 Sep) — so 40 was roughly twelve more months, a parking date wearing a threshold's
   clothes. 20 is a true doubling, about four months out.

## What this does not answer

- **Whether a wide stop is the right reason to reject.** This measures what the stock DID, never what
  the trade would have returned at a 2× stop. A name can run +15% and still be a bad bet if the stop
  is three times as far away — that is the whole premise of the filter and it is untested here.
- **n = 11 against n = 25.** Both cohorts are small; the comparison is underpowered, which is why the
  verdict is "cannot tell", not "no difference".
- **The two cohorts are not random halves.** Admitted names entered *because* their stop was tight,
  so they differ in ORB range by construction. Raw MFE% does not depend on the stop, so the measure
  is fair — but whatever else a tight ORB range predicts rides along with the comparison.

## Corrections — made the same evening, after an advisor pass

1. 🔴 **The original control, "admitted HIGHs (n = 400)", contained ZERO admitted names.** It was
   built as *HIGH alerts with no stop_too_wide skip row* and joined to `mi_ep_missed_outcomes` — a
   table that by construction only records names we did **not** enter. Every one of the 400 carries a
   skip category: `duplicate_scan` 122, `high_unentered` 56, `window_missed` 43, `score_below_50` 29,
   `outside_top20` 18, `mcap_low` 15, `cooldown` 8, and more. **So this doc compared one rejection
   cohort against another and called it "what the filter admits" — in the same paragraph that warns
   the comparison must be against what the filter ADMITS.** Fourth instance of that defect in seven
   days, and the first one I committed while writing about it.
2. **n was 11, not 20.** `mi_live_trades` holds 11 distinct ticker-days rejected for
   `setup:stop_too_wide`; the LEFT JOIN to the missed-outcomes table fanned them to 20 rows, because
   that table carries several rows per ticker-day (one per source/skip category). The review's n ≥ 10
   bar is still met at 11 — but "twice its bar" was false.
3. **The p of 0.493 was computed on those wrong cohorts** and is replaced by 0.141 above.
5. **The predicate returns 10, not 20** — the 20 was the joined query's row count. So this review
   fired at *exactly* its n ≥ 10 bar, not at twice it, and the re-gate was sized off the wrong
   number (see Recommendation 3).
4. The median 5-day *return* comparison is dropped rather than restated: it was only computable from
   the missed-outcomes table, which the admitted cohort is not in.
