# W3 winner-harvest STEP-0 — MFE capture on the closed cohort (#306)

**2026-07-04 (Sat eve, read-only).** First quantification of the v1.1 diagnosis-#2 claim
("winners under-harvested vs their excursions") on the full closed paper cohort —
`mi_live_trades` status='closed', N=25 (5/01–7/02), using `highest_price_seen` as the MFE proxy.
`capture_pct = total_pnl / ((highest_price_seen − entry) × shares)`.

## Headline

| Cohort | N | MFE sum | PnL kept | Aggregate capture |
|---|---|---|---|---|
| Partial-taken winners | 10 | $32,775 | $5,942 | **18%** |

The v2.0 tier-one bar (roadmap PART II) is **>50% MFE capture**. At 50%, the same 10 trades keep
~$16.4k — the management leak on this small cohort is **~$10.5k vs the bar**, which is larger than
the entry-mechanics leak (11 day-0 stop-outs ≈ −$6.1k total, the W2/#276 lane).

## The three round-trippers (the acute failure shape)

| Ticker | MFE | Kept | Capture | What happened |
|---|---|---|---|---|
| CRSR | +52.5% / $9,545 | $1,391 | 15% | monster peak, trail gave back 85% |
| SMCI | +11.7% / $2,327 | **−$639** | −27% | peaked double-digits, closed a LOSS |
| PURR | +13.4% / $1,024 | $3 | 0% | full round-trip to breakeven |

FPS (+24.3% → $160, 7%) and FTRE (+8.0% → $138, 9%) are the same shape, milder. IBM (the
known case from the 6/10 critique: 30% peak → +3.5% exit) sits at 20%. Best in cohort:
GOOGL 47% — still below the bar.

## Loser side (context, not W3's scope)

- 11 of 25 closed same-day at ≈ −1R (the W2 opening-noise class — KLAR/DELL/NVTS all present).
- **SYRE −4.57R** (6/22–6/24): loss far beyond −1R — the gap-through/stop-integrity class.
  Direct corroboration for **#414** (entry/stop-trigger tuning, filed 7/4). DELL −1.43R milder same class.

## Data caveats

- `highest_price_seen` is the high-water mark AFTER fill — a fair MFE proxy, but intraday
  granularity depends on the sync cadence (it can UNDERSTATE MFE; capture is if anything better
  than reality shows... i.e. the true leak is ≥ this).
- `r_mult` from current `stop_price` is unusable on partial-taken rows (breakeven moves make
  init-risk ≈ 0 → CRSR "277R"). Use capture_pct; recompute R from entry−ORB-low at study time.
- N=10 winners = direction-setting, not a tuning cohort. The W3 changes still go through
  backtest-on-closed-history + replay per the roadmap gate.

## What this pre-bakes for #306 (the W3 build, Sun 7/5+)

1. **Promote `capture_pct` to the weekly review as THE management KPI** (roadmap says this
   verbatim; zero trade-state risk — read-only surface first).
2. The tuning axes, now with a target shape: partial SIZE (IBM's 8-of-26 class), trail
   selection (10 vs 20MA by character — CRSR/SMCI are the test cases), and giveback guard
   (peak-lock: the SMCI −27% case is the motivating pattern).
3. Any live change = trade-state → CHANGE_PROCESS + #151 integration discipline + operator
   sign-off. THE LINE: this doc changes nothing; it measures.
