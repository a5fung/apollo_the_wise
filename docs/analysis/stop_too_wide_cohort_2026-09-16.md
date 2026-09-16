# The stop-too-wide filter — first cohort read, and its decision matrix cannot fail (2026-09-16)

**Answer first: the rejected names are indistinguishable from the ones we admit (p = 0.49, n = 20).
There is no evidence the filter sheds winners — and no evidence it sorts well either. The review's
own REVISIT bar fires, but it fires on absolute numbers that the ADMITTED population clears by
more, so the bar does not mean what it says.**

MEASURE-ONLY, $0. No threshold proposed. The stop filter is entry discipline = THE LINE.

## Population — declared before the first measuring query

| | |
|---|---|
| **Cohort** | every `setup:stop_too_wide` rejection with `signal_type = 'magna53'`, `alert_date >= 2026-05-05`. **n = 20**, all 20 carrying settled forward outcomes |
| **Scope, deliberate** | `9m_day2` shares the skip-reason prefix and is a DIFFERENT filter — excluded, per the entry's own 2026-08-17 fix. `account_mode` is **not** filtered: these are SKIPS, no position was taken, so the stock's forward path is account-independent |
| **Control** | magna53 HIGH alerts over the same dates that were **not** rejected for a wide stop — **n = 400**. The review's matrix does not ask for this; it is the comparison that decides the question |
| **Statistic** | `max_high_5d` = max favourable excursion over 5 sessions, and `ret_5d` |

## ⚠ Units — the first reading was wrong and would have inverted the verdict

`max_high_5d` and `ret_5d` are **fractions measured from `open_d0`**, not percentages. Reconciled
against raw bars rather than assumed: SDOT 2026-06-26 stores `8.2174` against a $106.00 high;
RETO 2026-09-10 stores `48.2908` against a $20.85 high off a ~$0.42 open.

Read naively, the matrix's "+10% hit" becomes `max_high_5d >= 10` — i.e. **+1000%** — and the cohort
returns a **0.0% hit rate**, which reads as a clean KEEP. That is the opposite of what the data says.

## The result

| | n | hit rate (MFE ≥ +10%) | median MFE 5d | median return 5d |
|---|---|---|---|---|
| **rejected for a wide stop** | 20 | **40.0%** | +9.3% | **−2.2%** |
| **admitted HIGHs (control)** | 400 | **50.3%** | +10.1% | **+0.8%** |

**The rejected names are worse on all three measures, and none of it is distinguishable.**
Fisher on the hit rate: **p = 0.493**. At the admitted rate, 20 names expect 10.1 hits; we saw 8.

## 🔴 The finding that outlives the numbers: this matrix could only ever say REVISIT

The pre-registered decision rule was:

- **REVISIT** if 5d hit-rate ≥ 30% **and** median MFE ≥ +8%
- **KEEP** if 5d hit-rate < 20% **or** median MFE < +3%

**The admitted population reads 50.3% and +10.1% — it clears the REVISIT bar by a wide margin.**
So any cohort that merely resembles a normal EP population fires REVISIT, and the KEEP arm requires
the rejected names to be less than half as good as everything else we alert on. The bars were set in
2026-05 from two anomalies (STRL, AIP) without ever asking what the base rate was.

This is the third instance of one defect in seven days: **a rejection cohort's absolute numbers mean
nothing; the comparison that decides a filter is against what it ADMITS.** The HTF ADR floor was the
same shape on 2026-09-10 — 8,976 excluded ticker-days looked damning until the admitted population
turned out to convert at 4.91% against the band's 2.38%.

## Recommendation — keep as-is, and re-gate on a bar that can fail

1. **Keep the 1.5× multiple.** Nothing here supports widening it; the rejected cohort is not better
   than what we take, and at n = 20 it is not measurably worse either.
2. **Do not test options (a) widen to 2.0× / (b) change the stop anchor / (c) tier by score** on this
   evidence. They were written for a "filter sheds winners" finding that did not materialise.
3. **Re-gate to n = 40 with CONTROL-RELATIVE bars** — the rejected cohort must beat the admitted
   population's hit rate by a stated margin, not clear an absolute number. Bars that any healthy
   population clears are not bars.

## What this does not answer

- **Whether a wide stop is the right reason to reject.** This measures what the stock DID, never what
  the trade would have returned at a 2× stop. A name can run +15% and still be a bad bet if the stop
  is three times as far away — that is the whole premise of the filter and it is untested here.
- **n = 20 against n = 400.** The control is twenty times larger; every comparison above is
  underpowered on the cohort side, which is why the verdict is "cannot tell", not "no difference".
- **The median 5d return gap (−2.2% vs +0.8%) is the most suggestive number here and the least
  tested** — no significance was computed for it, because a median difference on n = 20 with this
  spread would not survive one either.
