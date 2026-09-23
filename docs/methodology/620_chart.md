# The 620-Chart — Gil Morales' intraday timing tool

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions. Two cards ran on this subject without it on 2026-08-29 and returned nothing new. Kept complete by `tests/test_delayed_entry_ledger_complete.py`.


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

## ⚠ WHERE IT SITS IN THE PROCESS — operator, 2026-08-07, and this governs how it may be tested

> *"it's critical to note that 620 is used to fine-tune entry, not stock selection or only entry
> tool. In TEAM's case, it's already an EP, it already has the fundamentals, the software theme
> and daily chart etc. I used 620 to pick entry after all this already lined up."*

**The 620 is the LAST step, not a signal in its own right.** By the time it is consulted the name
is already a decision — it answers *when*, never *whether*.

The stack on TEAM, in order:

1. EP alert (the setup qualifies at all)
2. Fundamentals (record revenue +43% YoY, net income +496%)
3. Theme (software cohort gapping together on rising sector RS)
4. Daily chart
5. **620-chart → entry timing only**

⇒ **Sweeping the 620 standalone across all names would measure something the operator never does.**
The correct population is names that have ALREADY passed everything upstream. For Apollo that is
the Day-1 stop-out set: stocks we already wanted, already entered, and got shaken out of.

⇒ The narrow, honest question for #545: *given a stock we already qualified, does the 620 find a
better second entry than the opening break did?*

This also explains the two TEAM entries without either being wrong: Apollo bought the opening break
on one timing rule with no second look; the operator bought the same conviction four hours later at
a better price, off a chart saying the turn was in. Same stock, same thesis, different timing layer.

## Worked example — TEAM, 2026-08-07 (computed, not recalled)

5-minute bars, 6/20 EMA and 6/20 MACD with the eSignal 9-period signal line:

| ET | close | MACD | signal | event |
|---|---|---|---|---|
| 11:10 | 144.00 | −1.86 | −1.28 | MACD stretched to its low |
| 11:15 | 144.49 | −1.72 | −1.37 | **turns up** (the hook) |
| 11:40 | 143.68 | −1.54 | −1.58 | **bullish MACD cross** |
| ~12:05 | 144.40 | −0.89 | −1.27 | **operator entry ≈ $144.39** |
| 12:25 | 145.94 | +0.09 | −0.67 | 6/20 EMA cross (confirmation) |

- Price based $143.06–143.69 for ~40 minutes beneath the turning MACD — his "price chart also
  forming bottom".
- He entered ~25 min after the MACD signal and **~20 min before the EMA cross** — i.e. inside the
  exact window the source says to use, and ahead of the confirmation that arrives too late.
- Apollo, by contrast, entered the opening break at $147.13 and was stopped at $143.21 within
  20 minutes. Low of day was $141.51 at 13:55 ET, after his entry.

His stated rule — *"I waited for the 6 period stretched and turning while price chart also forming
bottom"* — is therefore **three computable conditions**: MACD extended below its recent floor, the
first up-tick out of it, and a basing price range. Not a judgement call, and all of it derivable
from `mi_intraday_bars`.

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
