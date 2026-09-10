# The HTF ADR floor discards 8,976 ticker-days, and the band just under it holds 82 of the 89 big movers

**2026-09-10 · read-only · $0 · #610 — the measurement half only. The threshold itself is not proposed here.**

## Method / population — which rows, over what window

On 2026-06-28, commit `dd23cf3b` added two per-ticker liquidity floors to `compute_flag_metrics`:

| constant | value | how the code itself describes it |
|---|---|---|
| `_HTF_MIN_ADV_SHARES` | 500,000 shares | "a standard liquidity floor (**firm**)" |
| `_HTF_MIN_ADR_PCT` | 0.04 | "a **STARTING** value — 4% is **NOT canonical** (sources run 3-6%), data-gated tune" |

HTF breakouts then fell ~91%. The task has been open since 2026-08-31 on the theory that a
provisional threshold, never measured, is starving the detector.

⚠ **The reason this is measurable at all — and the contrast with the rel_volume floor retracted
this morning.** The gate is an EARLY REJECT that still writes a `mi_flag_candidates` row, and the
reason string carries the value that failed (`adr_3.1pct_below_4pct`). So the excluded population
is on disk with its own numbers. The large-cap rel_volume shadow, by contrast, wrote nothing above
its threshold, which is why counting its rows could only ever restate the threshold. **Same shape of
question, opposite data situation.**

**Population.** All `mi_flag_candidates` rows from 2026-06-29 — the first scan after the gate shipped —
to 2026-09-09, **n=28,608 ticker-days across 1,096 distinct tickers**. Buckets come from the stored
`reason` string, so membership is the detector's own recorded verdict rather than a re-derivation.
Finding 3 narrows to 2026-07-01 → 08-20 (**n=6,055 with prices on both ends**) so every row has ten
settled sessions; forward prices join from `mi_daily_closes`.

## Finding 1 — which gate does the cutting

| bucket | n (ticker-days) | distinct tickers |
|---|---|---|
| excluded by **ADR 4%** | **8,976** | 1,052 |
| excluded by **ADV 500k shares** | 4,466 | 524 |
| rejected for some other reason | 15,166 | 1,096 |

**The provisional gate cuts twice as much as the firm one.** ADR is also the one the code flags as
non-canonical, so the larger cut is being made by the less-supported number.

## Finding 2 — most of the cut sits just under the bar

Parsed from the reason strings of all 8,976 excluded rows:

| | n (ticker-days) | distinct tickers |
|---|---|---|
| would pass at **ADR ≥ 3.0%** (low end of the sourced range) | **5,190 (58%)** | 696 |
| would pass at ADR ≥ 3.5% | 2,755 (31%) | 482 |
| still excluded at 3.0% | 3,786 | 557 |

**Median excluded ADR is 3.10%** (min 0.20, max 4.00). So the typical name this gate rejects misses
by less than one point, against a bar the code calls a starting value inside a 3-6% range.

## Finding 3 — the excluded 3.0-4.0 band is where the movers are

Forward 10-session return from scan date, rows 2026-07-01 → 08-20 (bounded so every row settles):

| excluded band | n | mean fwd-10d | median | names that ran **≥ +20%** |
|---|---|---|---|---|
| **ADR 3.0-4.0** (a 3% floor admits these) | 3,443 | **+1.03%** | +0.43% | **82** |
| ADR < 3.0 | 2,612 | +0.44% | +0.33% | **7** |

82 of the 89 big movers among all excluded names sit in the band a sourced 3% floor would admit —
2.4% of that band versus 0.27% below it.

## ⚠ The confound, stated first rather than buried

**ADR mechanically predicts large moves.** A name with a 3.5% average daily range is more likely to
post a 20% ten-day move than one at 2%, by the definition of the measure. So Finding 3 does **not**
establish that these would have been profitable HTF trades. What it establishes is narrower and
still useful: **the 4% gate is discarding the part of its rejected population that actually moves**,
and it is doing so on a threshold the code itself never claimed to have derived.

## What this does NOT answer

- **Whether any of these would have become an HTF breakout.** They failed the ADR gate early, so they
  never reached flagpole/base/breakout logic. The count of movers is not a count of setups.
- **Forward return from a scan date is not a trade** — no ORB entry, no stop, no position sizing.
- **What the threshold should BE.** That needs the excluded rows replayed through the full detector
  and settled as breakouts, which is the analysis half, not this.
- **The ADV 500k floor is not questioned here.** The code calls it firm and standard; nothing
  measured today contradicts that.

## What happens next — and what does not

⛔ **No threshold is proposed and nothing is changed.** `_HTF_MIN_ADR_PCT` is a detection criterion:
CHANGE_PROCESS + N≥10 backtest + operator sign-off, and the sign-off is his alone.

The next step is a replay of the 5,190 excluded-but-≥3.0% ticker-days through the HTF detector with
the ADR floor lifted to 3.0%, settled as breakouts, and compared against the breakouts the current
gate admits. That is a real analysis with a real population, and it is now known to be possible —
which was the open question this measurement answers.
