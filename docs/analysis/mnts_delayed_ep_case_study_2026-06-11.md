# Case study: MNTS delayed-EP re-entry (2026-05-26 → 2026-06-11)

**Why this document exists** (operator, 6/11): every detector picked up a piece of
this over the week — *"this is exactly how it should be, but our system is
fragmented and the chart reading pulls it all together."* The case is the
blueprint for per-ticker SIGNAL COMPOSITION: a Stocks-in-Play name should be
**watched → armed → triggered, with tight risk management at the trigger** — as
one lifecycle, not five disconnected pings. Drives #270 (the composed detector),
#267 (chart-vision — the operator read the entire setup from one daily chart),
and the SiP state-machine direction (v2.0 P4).

## The chart story (operator read, daily bars)

1. **5/26 — the EP**: ~100% gap above the 200d MA on the highest volume ever,
   inside the defense/space theme. $74M micro-cap "fast runner" class — the
   one-pays-for-ten-losers tail.
2. **Burst**: day-2 continuation (the 3–5 day momentum-burst expectation,
   Pradeep framing).
3. **Pullback**: multi-day, on clearly LOWER volume, into the 21EMA/20MA —
   including an **undercut of the gap-day low**.
4. **The two-fold U&R** (operator refinement): the rally reclaims BOTH the
   moving averages AND the gap-day low — two undercut-and-rally references
   resolving in one move. The R-leg is **explosive on higher volume** vs the
   pullback's contraction — the volume signature IS the confirmation.
5. **Trigger day (6/11)**: first-minute high/low held after entry → **+46% day**.
   Structural stop = the reclaimed gap-day low; the prior consolidation is the
   cushion (the U&R paradox: feels riskiest, actually the tightest risk).
6. **Management nuance**: tiny-cap fast runners derisk FASTER — partials earlier
   and more often than the standard ladder (P3/W3 input).

## What Apollo saw, leg by leg (prod trace)

| Leg | Apollo's view | Verdict |
|---|---|---|
| 5/26 EP | Live scan SAW the 42% premarket gap → **filtered: `mcap_too_small $74M < $500M`** | Deliberate auto-trade policy; a coverage hole for the WATCH lane |
| 5/26 judge (replay, #268 Phase A) | floor HIGH → grounded grade "routine" (thin tiny-cap corpus) → **judge none/demote** — theme axis DARK (MNTS fell out of its satellite theme 5/11, reassigned ~6/05) | The RCAT class writ large: theme + record-volume structure carried it, corpus-only judging can't see either. Chart-vision (#267) + Lane-2 are the fixes; prime `/spotted` ground-truth injection |
| 5/27 | Extension filter ("already up 166% in 5d") | By design |
| Pullback week | Flag detector: WATCH 6/04–6/09 → **INVALIDATED 6/08 + 6/10 on the undercut** | **The irony at the heart of #270**: the undercut that IS the setup is what disqualified it — so the U&R scanner (which exists for exactly this) never looked |
| 6/04, 6/05, 6/11 | 9M detector pinged each (universe admission working); 6/05 EP path muted by pm-RVOL filters | The fragments firing correctly, separately |
| 6/11 trigger | 9M ping at the 3.6% open gap — blind to the +46% day it became; U&R/MA-pullback tables: zero MNTS rows | No composition layer = no trigger |

## Lessons (each filed)

1. **Composition is the missing layer, not detection** — the fragments fired;
   nothing assembled "EP'd 11d ago + burst + low-vol pullback at 21EMA +
   undercut → ARMED; reclaim on volume expansion → TRIGGERED." → **#270**
   (shadow-first composed state machine; universe includes sub-$500M for
   observation).
2. **Undercut ≠ invalidation on post-EP names** — it's the arming event. The
   flag-rule universe and the delayed-EP universe need separate state tracks.
3. **The volume signature is two-sided**: contraction through the pullback,
   expansion on the R-leg. Both are detectable from daily bars.
4. **The mcap floor splits cleanly**: keep it for auto-trading; drop it for the
   watch/observe/theme lanes (operator policy review, costs nothing in safety).
5. **Chart-vision earns its pillar**: one daily chart carried the entire
   composed read that five tables couldn't assemble (#267).
6. **Judge ground truth**: the 5/26 demote-of-a-+239%-runner is a labeled
   counter-case for the theme/structure axes (probe library + `/spotted`).
