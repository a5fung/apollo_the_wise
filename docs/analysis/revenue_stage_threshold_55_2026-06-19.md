# #55 — revenue-stage threshold review (REVENUE_STAGE_MIN_USD)

**Date:** 2026-06-19 · read-only backward-check, no code change.
**Decision owner:** operator (HARD gate — the agent surfaces evidence + applies the
script's documented decision matrix, but does NOT self-certify a filter list).
**Evidence tool:** `scripts/_b50_revenue_stage_threshold_backward_check.py` (prod, 60d).

## What the threshold actually gates (corrected mechanism)

`REVENUE_STAGE_MIN_USD` is NOT an alert-blocker. It gates the **earnings-day
routine→strong catalyst BOOST** (`ep_detector.py:2020`): on an earnings day, a
`routine`/None catalyst is boosted to `strong` ONLY if `is_revenue_stage(ticker)` is
True (`earnings_calendar.py:145`). Pre-revenue (rev < threshold) → boost skipped
(`catalyst_earnings_boost_skipped`), grade stays at Claude's verdict.

- `is_revenue_stage` uses yfinance `calendar["Revenue Average"]` (a **forward analyst
  estimate**, not trailing actual). **Fails SOFT**: missing calendar / `None` rev → True
  (revenue-stage). So only companies with a *known* sub-threshold revenue are gated.
- Current pin **`REVENUE_STAGE_MIN_USD=0.01`** (env override; code default $5M): only
  true-`$0` (rev_avg == 0.0) companies are excluded from the boost. The `$5M` default
  would additionally exclude the entire `$0–5M` clinical-stage band.

## Evidence — 60d HIGH alerts by forward-revenue band (forward 5d return)

| Revenue band | N | % | avg 5d | median | winners >+5% |
|---|---:|---:|---:|---:|---:|
| `$0` (true pre-revenue) | 26 | 8.2% | **−7.71%** | −12.0% | 7/26 (27%) |
| `$0–$5M` (clinical-stage) | 15 | 4.7% | **+4.34%** | −4.2% | 3/13 (23%) |
| `$5–$10M` | 11 | 3.5% | +7.69% | +13.8% | 6/10 (60%) |
| `$10–$25M` | 15 | 4.7% | +3.84% | +0.2% | 5/15 (33%) |
| `$25–$100M` | 39 | 12.3% | −1.27% | −1.8% | 12/37 (32%) |
| `$100–$500M` | 84 | 26.5% | +3.53% | −0.9% | 30/84 (36%) |
| `$500M+` | 103 | 32.5% | +2.81% | +0.5% | 33/100 (33%) |
| `N/A` (no yf data) | 24 | 7.6% | −17.26% | −15.6% | 4/24 (17%) |

*(Proxy caveat: this is ALL HIGH alerts by band, not the narrower earnings-day-boosted
subset the gate actually touches — directional, not the exact boost cohort.)*

## Reading against the script's decision matrix

The script's pre-committed matrix: *"if the `$0–5M` band has POSITIVE-edge winners →
don't raise above $5M (we'd over-block real EPs)."*

- The **`$0–5M` band IS positive-edge**: +4.34% avg, carried by real tail winners —
  ALOY +50.9%, QBTS +38.5%, ASPI +30.6%, REPL... → **raising to $5M would over-block
  these.** Matrix → **do NOT ratchet to $5M.**
- The **`$0` true-pre-revenue band** is the clear net loser (−7.71% / −12% median / 27%
  win) — but it is **already excluded** by the current `0.01` pin (rev_avg == 0 → not
  revenue-stage → no boost). So the worst band is already handled.
- The `N/A` band (−17.26%) is the other weak cohort, but it **fails soft to True** (no
  data → boosted). Tightening *that* (treat unknown-revenue as pre-revenue) is a
  separate, riskier change — unknown ≠ pre-revenue, and it would catch legit names with
  thin yfinance coverage. NOT recommended here; flagged for the quarterly sweep.

## Recommendation (for operator ratification)

**Keep `REVENUE_STAGE_MIN_USD=0.01` — the evidence does NOT support the $5M ratchet.**
The clinical-stage `$0–5M` band has genuine positive-edge tail winners; the only clearly
bad band (`$0`) is already excluded; and the gate touches only the earnings boost, a
narrow surface. This is consistent with the prior "still below ship threshold" reads
(2026-05-20/21 N=2 ratchet rolled back). No code change.

**Open thread for the next quarterly sweep (Aug 1):** the `N/A`/no-data fail-soft (−17%
cohort flows through as boost-eligible) is the more interesting lever than the $0–5M
ratchet — but distinguishing "no data" from "pre-revenue" needs a second source, not a
threshold move. Re-evaluate with a larger, boost-isolated cohort.
