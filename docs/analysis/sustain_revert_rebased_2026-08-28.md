# Re-basing the sustain rule's revert condition — the operator's ruling, and what it exposes

**Date:** 2026-08-28 (PT) · **Task:** #593 · **Ruling:** operator, *"yes, it's more accurate"* —
measure the +20% run from **the level the rule declined**, not from the day's open.

---

## What was wrong with the old measurement

The sustain rule (operator's own ask, 2026-08-02) requires a name to hold above the gap level
for three consecutive bars before admission — *"a single 1min bar touching >10% may be too
loose."* Its pre-registered revert condition: **a rejected name running ≥+20% once is a review,
twice a revert.**

That +20% was measured **from the day's open**. A name that fades in pre-market opens
*depressed*, so the fade itself manufactures the +20% the rule is then charged with. The
baseline was never named in the condition, and the open is the wrong one.

**The right baseline is recorded already.** Every `ep_rt_sustain_reject` event carries `rt_gap`
— the gap the rule saw and declined — so the declined price is
`prev_close × (1 + rt_gap/100)`. The honest question is: *we passed at X; did it trade 20% above
X?*

## The re-based count

All `ep_rt_sustain_reject` events, **2026-08-03 → 2026-08-28, 19 trading days**, deduped to
ticker-days, max high over the 5 sessions from the rejection day:

| | count |
|---|---|
| rejections (ticker-days) | 128 |
| scoreable (have `prev_close` and bars) | 65 |
| **≥+20% from the OPEN** — the artefact basis | **39** |
| **≥+20% from the DECLINED LEVEL** — the ruling | **13** |

**The ruling removes two-thirds of the breaches.** It confirms the artefact was real and large.

## The operator's two further refinements — applied, and they finish the answer

Same message, 2026-08-28: *"those stocks that we turned away has to be theoretically traded
before we count them vs just admitted in that stage. Also, 2nd eval check is ratio, if it's 1 of
100 then it's small vs 1 of 5."*

**Both are right, and the first is what the count was missing.** A name we declined only costs
us something if it would actually have become a TRADE — clearing the gap floor is admission, not
an entry. Walking the 13 through the rest of the funnel:

| filter | left |
|---|---|
| breaches on the declined-level basis | **13** |
| …still held the 9% gap floor at the d0 close | 13 |
| …**and** cleared the $50M dollar-volume floor | **2** |
| …**and** traded above the declined level on d0, so an ORB entry was reachable | **2** |

**Eleven of the thirteen were too illiquid to trade.** They were never a cost — they could not
have been entered whatever the sustain rule did.

### The answer, with both refinements

**2 theoretically tradeable misses out of 65 declined names = a 3% miss rate over 19 trading
days.** Not 20 breaches, and not 20%.

## ⚠ The condition still trips — which is the remaining defect

2 is still ≥ 2. **Even at a 3% miss rate the rule trips its own revert trigger**, because the
trigger counts events rather than measuring a rate — which is precisely the operator's second
point.

**The deeper problem: the condition is a raw COUNT with no window and no rate.** "Twice a
revert" over 19 trading days and 128 rejections is not a threshold — it is a certainty. Any
gate that declines anything will accumulate two counter-examples given enough time, so the
condition as written can only ever fire, never clear. It cannot distinguish a rule that is
wrong from a rule that is working and occasionally costly.

**2 of 65 is a 3% miss rate** — his "1 of 100 vs 1 of 5" test, and it lands nearer the 1-in-100
end. Against the 2026-08-24 finding that 88% of declines had already faded below the gap floor by
the bell and the measured cost was **zero admitted names**, the rule looks cheap and working.

## What this does not answer

- **Not the same population as the 2026-08-24 read** (which reported 20 breaches, 17 artefact,
  3 real). That cut applied a further filter — names that still held the gap floor. This one
  does not, so 39-vs-13 is the artefact size on the *whole* rejection set, not a restatement of
  the earlier three.
- **Whether the 13 were tradeable.** Max-high-over-5-sessions is not an entry; several would
  have died at the score, catalyst or ADV gates as the earlier three did.
- **No behaviour changed.** This is a read.

## Recommendation

Re-state the revert condition as a **rate over a window, counted only on TRADEABLE misses** —
both of the operator's refinements, e.g. *"review if tradeable misses exceed X% of declined names
over a rolling 30 trading days."* Today that reads 3%. Pick X against the measured cost. ⚖ That is a change to a pre-registered revert condition on a live admission
gate: **THE LINE, operator's sign-off.** Not taken.
