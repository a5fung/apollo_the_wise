# The 620-Chart — Gil Morales' intraday timing tool

**Status: OPERATOR METHODOLOGY, not implemented anywhere in Apollo.** Nothing in the codebase reads
it. Recorded because it was shared in an earlier session, never captured, and was lost — asked for
again 2026-08-07 and found nowhere in memory or the repo.

Source: Gil Morales, *"Tools of the Trade – the 620-Chart"*, theowltrader.com, 2023-05-25
(full article + comments supplied by the operator 2026-08-07).

## The setup

- **5-minute intraday candlestick chart.**
- **6-period EMA** (orange) and **20-period EMA** (blue).
- **MACD** on the same periods: 6-period fast line, 20-period slow line.
- eSignal string `(6,20,C,9)` — 6 and 20 are the MACD periods, `C` is close, and **the trailing 9
  is an eSignal auto-fill the author explicitly does not tune** (he confirmed in the comments:
  *"That's just an auto-fill from eSignal. Sometimes it shows up as 9, sometimes 10, I do not
  fiddle with it."*). Do not read meaning into it.

Origin: adapted from the 5-minute 9/27 moving-average convention common in Forex, re-tuned to 6/20
with a matching MACD.

## ⚠ It is a TOOL, not a system — the author says so twice

> *"the 620-Chart is not a trading system or a precise timing mechanism. It is a tool, and it is
> best used in combination with what you are seeing on the daily and weekly charts."*

> *"This emphasizes that the 620-chart is a chart like any other chart, and functions primarily as
> a tool, NOT a trading system."*

**Parameter sensitivity, measured by the author**: he compares `(6,20)`, `(8,24)` and `(12,26)` and
reports the signals are *roughly similar with slight variations in timing* — **the lower the
setting, the earlier the signal, and the greater the chance it is false.** So 6/20 is a
speed/false-positive choice, not a magic pair. Any sweep should treat the periods as an axis.

## How it is used

**The MACD cross is the SIGNAL. The moving-average cross is CONFIRMATION, never the entry.**

- A **bullish MACD cross** issues the long entry.
- The **6-over-20 EMA cross** follows roughly an hour later. The author's reason for ignoring it as
  a trigger is explicit: by then *"AGQ is well up and away from the original entry"* — the MA cross
  confirms a move you should already be in.
- A **bearish MACD cross** is a selling guide — alone, or paired with a break of the 20-DEMA on the
  **daily** chart, depending on trade plan and risk preference.

**MACD stretch** — the fast orange line pulling away from the slow blue line. Marks an extending
move; the author uses it as a take-profit signal.

**The 20-period EMA is the intraday guide rail.**

- Bounce into it from below → resistance, a short-sale re-entry, with the line as the covering guide.
- Pullback into it from above → watch for the MACD to turn bullish; that is the long entry.
- Position stays intact *"as long as AGQ does not break down significantly below the blue 20-period
  exponential moving average"*.

## Example 1 — AGQ, 2023-05-05 (the simple case)

- A hot BLS jobs number sent silver down pre-market; AGQ pulled into its **daily** 20-DEMA at the open.
- On the **620-chart**, the MACD turned bullish at that test → long entry.
- The bullish 6-over-20 cross came ~an hour later, well above the entry.
- Exit guide: bearish MACD cross on the 620, or a break of the daily 20-DEMA.
- AGQ closed at its intraday highs.

The pairing is the point: the **daily** chart says *where* (pullback to the 20-DEMA), the
**620-chart** says *when* (the MACD turn at that level).

⚠ The author notes the same entry was available *without* the 620 — simply "AGQ pulled into its
20-DEMA, use the 20-DEMA as a selling guide". The tool sharpened an entry that price alone already
justified.

## Example 2 — NVDA, 2023-05-25 (the case where price outranks the indicator)

- Day after earnings. The reference level was **price**: the $400 Century Mark (Livermore), also
  all-time highs. Pre-open high 399.50.
- Opened 385.23 and broke lower; the fast MACD line **stretched** away from the slow line.
- Intraday low 366.35, then a bounce **into the blue 20-period EMA** → short-sale re-entry, with
  that line as the covering guide.
- **The short entry came from the $400 Century Mark on price alone.** The pre-open bearish MACD
  cross served only as confirmation.

> *"it was not necessary to use the MACD and/or moving averages to generate short-sale entries
> since the $400 Century Mark short-sale entry point was clear on the basis of price only."*

**That is the most important line in the article for us.** The 620 is subordinate to a clear price
reference. Modelling it as an independent signal generator would misrepresent how it is used.

## Why this is recorded here

The operator used it on 2026-08-07 to enter TEAM at $144.39 — the same stock Apollo was stopped out
of at $143.21 that morning — describing his method as *"looking at the low forming, turn back up, I
also look at some other technicals… no hard rule so hard to copy."* The 620-chart is part of that
"other technicals".

⚠ **Relevant to PLAN #545 (entry/exit tactics program)**, whose stated risk is that any mechanical
proxy for "base, then turn" will not be faithful to what the operator actually does. A 6/20 MACD
cross on 5-minute bars **is** computable from `mi_intraday_bars`, unlike "it looked like it turned"
— so this is the one specifiable piece of that signal.

⚠ **But it is NOT a complete description of his entry, and the article argues against treating it
as one.** He also reads the low forming, the turn, and the daily chart; the author subordinates the
tool to price and to the daily/weekly picture. Sweep it as one factor among several, and expect
that a 620-only proxy will underperform what he actually does.

## What testing it would need

- 5-minute bars per ticker — `mi_intraday_bars` holds 1-minute bars from the #306 path recorder
  (2026-07-25 onward), resampleable.
- 6/20 EMA and 6/20 MACD on that series. No new data; pure computation.
- Sweep the periods, not just 6/20 — the author's own comparison says lower settings fire earlier
  and falser, which is exactly the trade-off a sweep should price.
- The #545 question: on the Day-1 stop-out set, does a bullish 620 MACD cross *after* the stop-out
  mark a re-entry that beats doing nothing?

Nothing above is implemented. This file is a record, not a spec.
