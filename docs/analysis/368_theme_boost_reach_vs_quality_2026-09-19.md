# #368 — letting young themes pay: the reach is real, the quality is not there (2026-09-19)

**The answer in one line: there is NO quality evidence for the Nascent change, and none against the
existing boost either — because the buckets that already pay are too small to read. Alerts in a
Nascent theme perform the same as alerts in NO theme (10.66% vs 10.46% at 5 days, 13.34% vs 13.45%
at 10 days). The reach argument gains nothing from outcomes.**

He flagged this gap himself on 2026-09-14: *"the evidence above is reach, NOT quality — it says how
many alerts WOULD be boosted, not that paying Nascent improves selection."* This is that check.

## Method and population — which rows, over what window, and how the set was derived

**Window:** EP alerts with `alert_date >= 2026-04-01` (the full period `mi_ep_scan_outcomes`
covers for this cohort), distinct on `(ticker, alert_date)`.

**The bucket, DERIVED not hand-listed.** For each alert, the theme stage the ticker actually sat in
**on its own alert date** — `mi_themes` joined on `theme_date = alert_date` with the ticker in
`tickers`. ⚠ A ticker can sit in several themes at once, so a `LATERAL ... LIMIT 1` takes the stage
that would pay MOST (Mainstream → Accelerating → Nascent → Fading → other). Without that, one alert
lands in two buckets and the counts fan out — the same join fan-out that turned 32 rows into 48 on
the ranking-shadow read two days ago.

⚠ **I did NOT use the eleven tickers named on the PLAN line** (IREN, RIOT, COHU, HUT, ALAB, MPWR,
CAMT, CLF, KTOS, MTW, PHVS). That list is a hand-built example; re-deriving the population from the
board is the whole point, and the derived Nascent bucket is **28 alerts**, not 11.

**Outcomes:** `mi_ep_scan_outcomes.fwd_5d_pct` / `fwd_10d_pct`, left-joined on
`(ticker, scan_date = alert_date)`. Alerts without a settled outcome are counted in `alerts` and
excluded from the averages, so `with_outcome` is the real denominator.

## The read

| stage at alert | pays today? | alerts | with outcome | avg fwd 5d | avg fwd 10d | reached +10% |
|---|---|---|---|---|---|---|
| **(no theme)** | no — the control | 336 | 293 | **10.46%** | **13.45%** | 125 (43%) |
| **Nascent** | **no — would newly pay** | 28 | 27 | **10.66%** | **13.34%** | 16 (59%) |
| Mainstream | **yes** | 25 | 23 | 8.88% | 9.74% | 8 (35%) |
| Accelerating | **yes** | 5 | 5 | 18.49% | 22.43% | 2 (40%) |
| Fading | no | 7 | 7 | 9.54% | 10.47% | 3 |
| Retired | no | 1 | 1 | 7.64% | 7.64% | 0 |

**What it says:**

1. **Nascent is indistinguishable from themeless.** 10.66 vs 10.46 at five days and 13.34 vs 13.45
   at ten is a difference of two-tenths of a point on n=27 against n=293 — noise, in both
   directions. **Sitting in a young theme predicts nothing about the forward move.**
2. **The +10% hit rate hints the other way** (59% vs 43%) but on 27 rows that is ~4 alerts of
   swing. It is a thing to watch, not a thing to weight.
3. **The buckets that ALREADY pay cannot be read.** Mainstream is 23 outcomes and Accelerating is
   5. Mainstream looks worse than the control and Accelerating looks much better; at those counts
   neither is a finding.

## What we do at each outcome

- **As measured — do not raise the magnitude on this evidence, and do not extend the boost to
  Nascent on it either.** Reach was never the question; quality is, and quality is absent.
- **If the operator still wants Nascent to pay** (he ruled yes in principle on 2026-09-14), that is
  his call and it should ship as its own change with its own read — but it should ship knowing this
  table shows no outcome support, rather than on the 11 → 22 reach count alone.
- **The honest next measurement is not a bigger cohort of the same thing.** Accelerating at n=5 is
  the bucket most likely to carry real signal and the one we know least about; it accrues on its
  own and is worth re-reading at n≈25.

## What this does not answer

- ⚠ **Whether the themes are RIGHT.** His standing rule: *getting themes right and getting returns
  are separate questions until the engine is fixed; a returns number on today's themes is a
  baseline, never an answer* [[themes-not-judged-on-returns-yet]]. **This table is a baseline.** It
  says the Nascent reach argument has no outcome support — it does NOT say the theme engine is
  wrong, or that themes do not matter.
- **Whether the boost changes any GRADE.** This measures forward returns by bucket, not what the
  judge did. The theme boost was separately measured decorative in June (zero MODERATE-in-theme
  alerts crossed to HIGH because of it over 60 days) and that is a different claim from this one.
- **Selection quality.** Forward return on alerts that FIRED says nothing about the alerts that did
  not. The names a boost would have promoted into existence are not in this table at all.
- **Anything at n=5.** Accelerating's 18.49% is the most eye-catching number here and the least
  trustworthy; it is reported so it is not quietly dropped, not so it can be quoted.
- **Whether a bigger boost would change outcomes.** Nothing here is causal — the buckets differ in
  what kind of stock lands in them, not only in what the grader did.
