# #482 — No stop geometry fixes EP, because the stop was never the problem

**Date:** 2026-08-29 (PT) · **Task:** #482 · **Status:** read-only counterfactual. Nothing
changed, nothing proposed. **This corrects a claim I made earlier the same day.**

---

## Why this replay, and not the existing shadow lane

`mi_orb_shadow_trades` holds 5-minute-ORB shadows — but it is a **differently gated population**
from our live trades, so comparing the two answers a question nobody asked: a difference in
gating would read as a difference in geometry.

Instead this replays **our own real trades**: same names, same days, same entries, **only the
stop moves.** Every variant is scored against the same set, so any gap between them is geometry
and nothing else.

**Scored in R, where R is each variant's OWN risk** (`entry − its stop`). That matters — a wider
stop is not free, it buys fewer shares for the same dollar risk. Expressing everything in R is
what stops the widest stop from looking best by construction.

Walked minute-by-minute in sequence, first touch decides, +2R half-off applied (live since
2026-08-16), held to the 5th session's close with the stop still live.

## 🔴 CORRECTION — the first pass did not include the live stop at all

The operator: *"but we didn't compare this with 2R stop which is live now, so you're saying 2R
we have now is best?"*

**No — I had not tested it.** Since **2026-08-16** (operator-signed) the protective stop is
`entry − 2R` at half size, where `R = entry − orb_low`. The ORB low still *defines* R; it stopped
being the exit. My first table labelled `orb_low` as "live_1min (the control)" — a geometry
retired two weeks before this analysis ran. Every variant was therefore measured against the
wrong baseline.

Re-run with the real live stop included:

## The result

| variant | n | expectancy | win% | total |
|---|---|---|---|---|
| **LIVE — `entry − 2R`, half size** | 57 | **−0.13R** | **35%** | **−7.2R** |
| `orb_low` (the pre-08-16 stop) | 58 | −0.34R | 21% | −20.0R |
| orb_5min | 59 | −0.36R | 20% | −21.0R |
| low_of_day | 59 | −0.39R | 19% | −23.0R |
| atr_100 (entry − 1.0×ATR) | 57 | −0.41R | 21% | −23.5R |
| atr_50 (entry − 0.5×ATR) | 57 | −0.42R | 23% | −23.9R |

**The live 2R stop is the best of the six by a wide margin — and it is not a small margin.** It
roughly **halves the loss rate** (−0.13R against −0.34R), lifts the win rate from 21% to 35%, and
cuts the total from −20.0R to −7.2R across the same trades.

**So the answer to his question is yes, and the first version of this document was wrong about
what "live" meant.** The five alternatives cluster within 0.08R of each other *below* the pre-08-16
stop; the 08-16 change is the only geometry move in the set that did anything, and it is already
shipped.

**Still negative, though.** −0.13R is a smaller loss, not a profit.

### The model is calibrated against reality

| | n | avg R | win% |
|---|---|---|---|
| replay, `live_1min` | 58 | −0.34R | 21% |
| **actual closed trades** | 58 | **−0.46R** | 24% |

Close enough to trust the comparison. The replay runs slightly *better* than reality because it
applies the +2R half-off rule to every trade, including the ones that closed before that rule
shipped on 2026-08-16.

---

## ⚠ This corrects what I told the operator this morning

On the extension-cap re-run I wrote that five blocked names ran 2.9R–15.2R and still paid −1R,
and concluded: *"the lever is bracket geometry (#482), not admission."*

**The first half is true. The conclusion does not follow.** Those names were shaken out — but
widening the stop does not recover them, because a wider stop earns proportionally less per unit
of move, and the trades give it all back anyway. Five different geometries land within 0.08R of
each other and all of them lose.

**Neither admission nor geometry is the lever. The trades themselves are.** Across 58 real closed
trades: **−0.46R average, 24% win rate, −$10,849 realised.** A losing edge cannot be re-plumbed
into a winning one by moving the stop.

That points back at selection — which is where the operator has already said the priority sits
(*making existing EP profitable is critical*), and what #533's within-day ranking question is
actually about.

## 🔴 OPERATOR CORRECTION, same day — this evidence base is stale by construction

> *"april-may is stale, stop using old data when our system has evolved significantly week to
> week and especially month to month, until we are completely locked down then stale data is not
> valid. The tactic we used is to just use raw data to run our analysis given we have minute bars
> stored, that is the path we should go."*

**He is right, and it applies to every number above.** The 58 trades span 2026-04-16 → 08-28. In
August alone the rules changed at least six times: the 2R half-off stop (08-16), the gap floor
10%→9% (08-19), the catalyst lattice + separation scoring + shortlist (08-22), real-time
admission (08-25), real-time volume and gap authority (08-27), rubric v4 (08-27). **An average
across that window measures a system that never existed.**

That does not overturn the geometry *ranking* — the five variants were replayed against the same
trades, so era-mixing hits all of them equally and the −0.34R-to-−0.42R spread stands. **It does
invalidate the level.** "EP runs −0.46R, 24% win, −$10,849" is an average over a dozen different
systems and must not be quoted as current expectancy, including by me — I quoted it exactly that
way earlier in this session.

**The method he named is the one to use:** replay from `mi_intraday_bars` (608 tickers, from
2026-04-13) and `mi_daily_closes` under TODAY's rules, fetching missing bars from Alpaca. That is
what the extension-band replay did; the geometry work fell back to reading trade rows because
they were there. Historical rows remain useful as a *calibration check on a replay* — which is
how they were used here — never as the answer.

## What this does not answer

- **38 of the 97 eligible trades were skipped** for having fewer than 6 minute bars — thin,
  illiquid names. If they behave differently the ranking could shift, though it would take a
  large effect to close a gap this uniform.
- **Only stop PLACEMENT was varied.** Not the entry, not the target, not re-entry after a stop,
  not time-based exits. A geometry conclusion is not an exit-management conclusion — #306 is a
  separate question and untouched here.
- **The +2R rule is applied uniformly**, including to trades that closed before it existed. That
  flatters every variant equally, so it does not change the ranking.
- **Nothing here says the extension cap revert was wrong** — that decision rested on the band
  being −1.00R on 15 of 15, which stands.
