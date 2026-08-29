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

## The result

| variant | n | expectancy | median | win% | total |
|---|---|---|---|---|---|
| **live_1min** (the control) | 58 | **−0.34R** | −1.00R | 21% | −20.0R |
| orb_5min | 59 | −0.36R | −1.00R | 20% | −21.0R |
| low_of_day | 59 | −0.39R | −1.00R | 19% | −23.0R |
| atr_100 (entry − 1.0×ATR) | 57 | −0.41R | −1.00R | 21% | −23.5R |
| atr_50 (entry − 0.5×ATR) | 57 | −0.42R | −1.00R | 23% | −23.9R |

**Every variant is negative, all five sit within 0.08R of each other, and the geometry we
already run is the best of them.**

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
