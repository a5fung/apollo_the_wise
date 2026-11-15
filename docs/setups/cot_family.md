# COT family — crowded-positioning fades (Jason Shapiro's CMR method)

**Owner of:** the COT family's definition, its setups, their buy and stop, findings and change log.
**Phase:** research (no detector job, no strategy row, no orders). Futures; Alpaca cannot trade futures yet.
**Operator's framing (2026-11-15):** *"This is part of Apollo, we can't trade futures with it yet, but this is just
another setup for Apollo. The long term plan is that Apollo trades many strategies with ultimate goal it being about
to trade several uncorrelated strategies successfully."* — and *"Let's make this the cot setup family."*

Research workspace: `~/cmr_lab` (private; the newsletter text stays out of every git repo — its licence forbids
building a database from it). This file holds only the method and the measured results.

## FAMILY vs SETUPS (CLAUDE.md definition)

The FAMILY is the **condition**: a futures market whose three trader groups are at opposite crowded extremes on the
COT index. It is not tradeable alone — Shapiro "will never enter a trade based on a market becoming max crowded".
The SETUPS inside it each have a buy point and a stop:

| Setup | Trigger (on a set-up market) | Buy | Stop |
|---|---|---|---|
| **COT news failure** | scheduled news that should move the market WITH the crowd; first reaction goes that way; the day closes AGAINST the crowd | that session's close (or the next open when posted after the close / over a weekend) | a CLOSE beyond that day's high (shorts) / low (longs); never trailed |
| **COT correlation failure** | the market closes against the crowd while a closely tied peer closes strongly the crowd's way (e.g. Soybean Oil red, Crude green) | same | same |
| **COT Friday confirmation** | the failure happened earlier in the week; Friday's new COT data completes the set up | next open (Sunday night) | a close beyond the failure day's high / low |

**Exit (all three):** a close beyond the stop, or when the relevant group's index returns to ~50 (Commercials for
equity indices; any group otherwise). No targets. **Size:** 0.7% of the account at risk; half size when the signal is
weaker or a correlated position is already on.

## The COT index (rebuilt exactly, 2026-11-15)

- Data: CFTC legacy Futures-Only report; nets of Commercials, Non-commercial (Large Specs), Non-reportable (Small Specs).
- Index per group = 100 × (net − min) / (max − min) over a market-specific lookback of N weekly reports back,
  inclusive of the current week; rounded half up. 0 = max crowded short, 100 = max crowded long.
- Set up: Commercials ≤ 5 and both speculator groups ≥ 95 (short), or the mirror (long); equity indices on
  Commercials alone.
- Lookbacks (weeks): equities 26–27; Pound / Yen / CAD / Swiss 30; AUD / NZD ~80; Euro / Dollar Index 90; bonds ~97;
  Crude / Heating Oil / Gasoline 40; Natural Gas 68; Gold 24, Silver 23, Platinum 16, Copper 86; Coffee / OJ 8,
  Cocoa 10, Cotton 40, Sugar 131; Wheat 10, Meal 30, Bean Oil 34, Corn 86, Soybeans 127; Hogs / Cattle 13;
  Bitcoin / Ether 89. Full table: `~/cmr_lab/data/lookback_final.csv`.
- Verified: our formula reproduces his unadjusted index on 126 of 129 cells for 2026-11-08 (misses = Oats, no longer
  reported by the CFTC). His published index adds a small adjustment for Tuesday→Friday price / open-interest moves
  (usually 0–3 points). The set-up rule on his official index reproduces his newsletter set-up list at 92% precision /
  98% recall.
- Open: lookbacks drift over 2021–2026 (some re-tuned in 2025).

## Findings (research, 2023-08 → 2026-11; his 69 eligible trades)

| Feed | Alerts / month | His trades caught (strict / ±1 day) | Notes |
|---|---|---|---|
| A: event day closes against the crowd, or peer divergence | 11.7 | 43% / 51% | pre-registered; PARTIAL vs a 60% bar |
| A + Friday confirmation | 13.0 | 48% / 55% | Friday alert exploratory |
| First tick read on HOURLY bars | 1.8 | 13% | too coarse: the hourly bar matches the first 5 minutes 2 times in 3 |

- Precision counting trades he took OR said he missed: ~15% of alerts.
- His 5 timed labelled news failures: the first hour moved the way he described in all 5.
- Open: a true first-tick (1-minute) test; the news's own bullish/bearish read vs expectations (consensus) before
  watching for the failure — the operator's point, 2026-11-15.

## Change log

### 2026-11-15 — family created (operator)
- Trigger: his words above. Evidence: the research in `~/cmr_lab/docs/` (method.md, index_rebuild.md, step5*.md).
- Nothing runs; no detector, no alerts, no orders.
