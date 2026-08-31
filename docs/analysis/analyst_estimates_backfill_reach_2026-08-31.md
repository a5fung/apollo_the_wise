# #333 analyst-estimates backfill — measured honest reach (2026-08-31)

## The decision it serves

When does #333 (catalyst-durability forward axis) become buildable? Its gate is the
sourcing backbone (shipped this date: `analyst_estimates_recorder.py`) plus >=60 days of
stored estimates (review `analyst_estimates_60d_accrual_333`). The operator identified a
bounded backfill — an estimate for a future period persists until that period's results
land, so today's read stood on any date since THAT ticker's last filing — and estimated
it buys ~45 days. This measures what it actually buys, on the real alert population.

## Method / population

- **Population: every distinct ticker in `mi_ep_alerts` (all history, both live and
  historical_scan sources), n=335 tickers / 420 alert rows, alert_date 2026-05-11 →
  2026-08-28** — the prod snapshot captured 2026-08-29 for #327 Stage 1
  (`~/.claude/jobs/6b173ac9/tmp/327s1_alerts_out.psv`; prod was not re-queried).
- Anchor per ticker: most recent 10-Q/10-K (or 20-F/6-K) **filing date from SEC EDGAR
  submissions** (keyless, $0) — the same anchor semantics the recorder stores from FMP's
  `filingDate`. Resolved 306/335; the 29 unresolved are ETFs/preferreds/non-filers,
  which buy zero days BY DESIGN (no anchor → no claimed history) and would score None
  on any estimates axis anyway.
- Reach per ticker = 2026-08-31 minus its last filing date. Raw capture:
  `333_reach_raw.json`, scripts `333_reach_measure.py` / `333_reach_stats.py` (same dir).

## The numbers

| population | n | mean reach (days) | median | p25–p75 |
|---|---|---|---|---|
| all resolved alert tickers | 305 | **28.3** | 25 | 18–28 |
| tickers alerted since 2026-07-01 | 139 | 24.4 | 25 | 19–27 |
| tickers alerted since 2026-08-01 | 99 | 21.8 | 24 | 18–26 |

- Distribution (n=305): 48 tickers <15 days, 185 at 15–29, 39 at 30–44, only 33 at 45+.
- Historical-alert coverage: **111/386 resolvable alert rows (29%)** have their alert
  date inside the ticker's honest window — i.e. today's estimates honestly cover only
  29% of past alerts; the rest predate the ticker's latest filing (contaminated by the
  revision the filing caused).

**The average is ~28 days, materially below the ~45-day estimate.** The cause is
timing, not the design: measured just past earnings season, most tickers filed 2–4
weeks ago. The reach is cyclical — it grows toward ~45+ mid-cycle and shrinks again
each season. Practical consequence: the backfill starts the per-ticker history ~4 weeks
deep on average, and the 60-day accrual gate is then paced by the forward recorder at
one day per day.

## What this does not answer

- Whether estimates truly persist unrevised from filing to read date — the operator's
  persistence rule is the design's premise; mid-window revisions (guidance cuts,
  analyst moves off news) are invisible to a single snapshot. The forward recorder's
  daily series is what makes revisions observable; the backfill rows cannot.
- EDGAR filing dates vs FMP `filingDate` can differ by a day on edge cases; the
  recorder stores FMP's value, so prod reach may differ marginally from this measure.
- Whether `analyst-estimates?period=quarter` is in our FMP plan (annual is verified;
  quarter degrades gracefully if 402) — Pradeep's 4-projected-QUARTERS shape needs the
  quarter periods, or an annual-based variant; unresolved until the first prod run.
- Coverage of the estimates themselves (how many alert tickers have >=3 analysts) —
  unknowable until the first snapshot lands; n_analysts is stored per row for exactly
  this question.

## ⚖ THE LINE

Data capture only. No rubric axis, no scoring, no admission change ships here; the #333
axis needs operator sign-off + CHANGE_PROCESS after STEP-0, long after this backbone.
