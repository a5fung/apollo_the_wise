# #593 fresh read (2026-09-01) — does the SIGNED revert condition trip today, and is the +20% real?

**MEASUREMENT ONLY. Nothing was changed.** No rule, threshold, filter, toggle or trade state was
touched. Any change implied below is the operator's fork (THE LINE).

## The decision this serves

The task handed to this card restated the sustain rule's **original, superseded** trigger —
*"a rejected name running ≥+20% once is a review, twice a revert"* — as though it were still the
live condition and as though it had just tripped again. **It has not: that raw-count condition
was replaced on 2026-08-28** (`docs/analysis/sustain_revert_rebased_2026-08-28.md`), operator-signed,
with a rate-based condition:

> Review when **tradeable misses exceed 10% of scoreable declined names** over a **rolling 30
> trading days**, evaluated only when that window holds **≥30** scoreable declines. It raises a
> review; it never reverts on its own. A tradeable miss requires all four: ran ≥+20% above the
> **declined price**, still held the 9% gap floor at the d0 close, cleared a $50M dollar-volume
> floor, and traded above the declined level intraday on d0.

**That condition has never been re-read since the day it was signed.** This card is the first
re-read, using the full current rolling window (2026-08-03 → 2026-09-01, the sustain rule's whole
life to date fits inside 30 trading days). Two questions decide whether a review is due:

1. Does the signed condition trip on today's data?
2. Is its own "+20%" measured on a settled price or on a high-watermark (MFE) — the same
   measurement-artifact class that misread #482 and #233 elsewhere today?

## Method / population

- **One read-only production capture**, `scripts/probes` pattern (SSH → psql `-A`, SELECT-only),
  pulled once to `/tmp/593/capture_out.psv` and read from there. $0, no paid calls.
- **Population: every `ep_rt_sustain_reject` audit event 2026-08-03 → 2026-09-01** (the rule's
  entire life; `ep_rt_sustain_enabled` on since 2026-08-02 09:53 ET), net of same-day catches
  (a ticker rejected then admitted later the same tick session cost nothing — the 2026-08-24
  doc's own established rule, reproduced here: it reduced 66 raw ticker-days to the same 66
  through 08-24 when checked against my independently-rebuilt pipeline, which is the validation
  that this replication is sound).
- **Window: the last 30 trading days in `mi_daily_closes`, 2026-07-22 → 2026-09-01** — the exact
  rolling window the signed condition specifies. The sustain rule only has events from 08-03
  onward, so the effective population starts there.
- **Declined level** (the signed condition's own baseline) = `prev_close × (1 + rt_gap / 100)`,
  `rt_gap` read from each reject event's own audit detail — never the day's open (that was the
  2026-08-24 defect this already fixed).
- **d0 dollar volume** = `volume_d0 × close_d0` from `mi_daily_closes`, computed directly rather
  than trusting the scan-log `adv` column, whose units did not visibly resolve to a "$50M" scale
  for names checked by hand (e.g. IPST's scan-log `adv` reads 17,622 — clearly not dollars; its
  d0 volume × close is $73.7M). Stated so the floor is auditable. **This is more PERMISSIVE than
  whatever floor produced the 08-28 reading** — gap-day volume is naturally inflated (5-20x a
  trailing average), so a single-day dollar-volume floor lets more names through than a trailing
  ADV floor would. The data confirms the direction: 08-28's funnel killed 85% of MFE-basis
  breaches on liquidity (13→2); this card's funnel kills 65% (26→9, raw population). **Every
  tradeable-miss rate below is therefore an UPPER BOUND — a stricter, ADV-based floor can only
  lower it, never raise it.**
- **Era matters and is reported separately.** `ep_rt_universe_authoritative` — the toggle that
  makes the sustain rule's rejects actually bind admission, per the 2026-08-24 doc's Result 1 —
  went **ON 2026-08-25 11:02 ET**. Every decline before that date was **SHADOW**: it could not
  have cost a trade no matter what the stock did. Of the 87 declines in the window, **66 are
  shadow-era (08-03→08-24) and 21 are live-era (08-25→09-01, 6 trading days)**.
- Suite not run (read-only research card, no code touched).

## The numbers

**n = 87 net-declined ticker-days, the full rolling-30-trading-day window.** (A robustness check
using the *raw* reject count — not netting out same-day catches, closer to how the 08-28 doc's
"128" may have been built — gives n = 133; every number below is reported on both populations and
the conclusion does not change either way.)

| cut | n | share |
|---|---|---|
| declined names, current 30-trading-day window | 87 | — |
| …faded BELOW the gap floor by the d0 CLOSE (rule correct on its own terms) | 50/87 | 57.5% |
| …HELD the gap floor at the d0 close | 37/87 | 42.5% |
| …of those, too illiquid (<$50M d0 dollar volume) to have been tradeable | 21/37 | 57% |
| …of those, liquid enough to matter | 16/37 | — |

**57.5% is not a worse number than the 88% on record from 2026-08-24 — it is a different point in
time.** The 08-24 figure checked the gap **at the open**; the signed tradeable-miss definition
checks it **at the d0 close**, which is what this card reports. Some names that faded below the
floor pre-market recover part of the gap intraday, so the close-basis "held" share is naturally
higher than the open-basis one. Not a trend, a different clock.

**The +20% breach count, MFE (high-watermark) basis vs. a settled (close) basis, same 87 rows,
same declined-level baseline:**

| basis | ≥+20% breaches | of 87 |
|---|---|---|
| **MFE** — max HIGH over d0..d0+5 vs. declined level (what the signed condition's own text does not rule out, and what both prior analyses on this task used) | 18 | 20.7% |
| **SETTLED** — CLOSE on the last bar of the 0–5 window vs. declined level | 8 | 9.2% |

**MFE overstates the breach count by roughly 2.3×.** This is the same class of defect flagged
today on `mi_ep_scan_outcomes.fwd_5d_pct` and #482/#233: a running maximum over a forward window
is structurally larger than a settled price, and "≥+20%" on it counts wicks the market gave back
before anyone could have sold into them.

**Walking each basis through the full signed tradeable-miss funnel** (held the floor at d0 close
AND cleared $50M d0 dollar volume AND traded above the declined level intraday on d0):

| basis | tradeable misses | rate | vs. the 10% trigger |
|---|---|---|---|
| MFE (net-declined, n=87) | 4 | **4.6%** | below |
| SETTLED (net-declined, n=87) | 1 | **1.1%** | below |
| MFE (raw reject count, n=133) | 9 | 6.8% | below |
| SETTLED (raw reject count, n=133) | 2 | 1.5% | below |

**The condition does not trip today under any combination of the two unresolved choices** (basis:
MFE vs. settled; denominator: net-declined vs. raw reject count) — the reading ranges 1.1%–6.8%,
every one of them below the 10% trigger. n=87 (net-declined) clears the ≥30-scoreable minimum
comfortably; **it would take a denominator under ~40 for today's 4 MFE hits alone to reach 10%.**

**The breach RATE reproduces the 08-28 reading almost exactly once the same population is used**:
08-28's declined-level breach rate was 13/65 = 20.0%; this card's raw-reject-count population
(not netting same-day catches, the closer match to how "128" was likely built) gives 26/133 =
19.5%. **The 3% → 4.6% headline shift is a denominator difference (65 scoreable-of-raw vs. 87
net-declined), not new signal** — net-declined is the more rigorous population (a name caught
later the same day cost nothing regardless of price, per the 2026-08-24 doc's own established
rule), and it is used throughout this card.

### The names — what each of the 4 MFE-basis candidates actually did

| ticker | date | MFE peak | close on peak day | close, day-5 (settled) | what actually happened |
|---|---|---|---|---|---|
| **BRUN** 08-12 | shadow era | +30.4% (08-14) | +11.2% | **-7.8%** | Gave the whole move back; a name that HELD to +30% intraday closed the 5th session BELOW the declined level. **Alerted anyway via the delayed path** — cost is zero regardless of the price path. |
| **AVAH** 08-13 | shadow era | +32.6% (08-20) | +28.4% | **+28.4%** | The one real, held gain. But scan-log shows it was **independently killed**: `score 30 < 50 (catalyst=routine)` — the score/catalyst gate, not the sustain rule, is why this name was never a trade. |
| **IPST** 08-20 | shadow era | +65.1% (same day) | +11.5% | **-49.1%** | A same-day parabolic wick that round-tripped into a large loss by settlement. Independently flagged `already up 342% in prior 5 days (extended)` — the live extension cap would have blocked it regardless. |
| **WETO** 08-20 | shadow era | +59.6% (same day) | +21.0% | **-49.4%** | Same shape as IPST: same-day spike, deep settled loss. Independently `already up 475% in 5 days (extended)` — extension-cap kill. |

**All four are shadow-era** (before 08-25, when a decline could not have cost anything). **Zero
of the 21 live-era declines (08-25→09-01) reach the MFE ≥20% bar under the full tradeable-miss
funnel.** Four live-era names did touch MFE ≥20% before the funnel (GRML, MOVE ×2, TJGC) —
every one fails the $50M liquidity floor outright (d0 dollar volume $0.5M–$23M; GRML's own
scan-log row independently reads `adv_too_low: $533,390`). Two of the four (MOVE 08-27, TJGC
08-28) have not yet settled 5 sessions and remain open, but their disqualification is on
liquidity, which does not change as the price settles.

**Net measured cost of the sustain rule, current 30-trading-day window: zero names.** Of the one
genuinely-held gain (AVAH), a different signed gate is the actual reason it was never traded.

## The fork — his call, not pre-decided

- **Leaving the rule as written costs nothing measured**, today, on either the loose MFE reading
  it has always used (4.6%) or a fair settled reading (1.1%) — both well under the signed 10%
  trigger, and the walk-through finds zero names where the sustain rule is the operative cause of
  a missed winner.
- **Tightening it would not recover anything** — there is no real miss to recover — **and would
  weaken the safety net** on the 57.5% of declines that correctly fade back below the floor by
  the close, cutting against P1 (never miss a real EP) for no offsetting benefit shown here.
- **The open question is measurement, not the threshold**: the signed condition's own "+20%"
  text pins neither the STATISTIC (settled close vs. MFE/high-watermark) nor the HORIZON (both
  prior reads used 5 sessions forward). It has been read on MFE-over-5-sessions both times this
  task has been scored. Settling it on the close basis (1.1% today) is more defensible and still
  clears the trigger by a wide margin — this is a proposed refinement to a revert condition on a
  live admission gate, **THE LINE**, and is not applied here.

**Recommendation: no review is due. Leave the sustain rule and its signed condition as they
are.** If the standing predicate is wired up (#593's one remaining scope item), pin BOTH the
statistic (settled close, not MFE) and the horizon (5 sessions) explicitly — operator sign-off
required before either becomes the acting definition.

## What this does not answer

1. **Only the pre-registered ≥20%/tradeable-miss condition is scored here**, not the sustain
   rule's overall recall of real EPs below that bar. A name declined and never reaching +20% could
   still have been a smaller real winner; this card, like the 08-24 and 08-28 cards before it,
   only rules on the condition as written.
2. **Right-censoring**: 2 of the 4 MFE-basis candidates in the tail of the window (MOVE 08-27,
   TJGC 08-28) have not settled 5 sessions as of 2026-09-01; their disqualification here rests on
   the $50M liquidity floor, which will not change as they settle, but their eventual price path
   is not yet known.
3. **The $50M dollar-volume floor is self-computed and known to be MORE PERMISSIVE than whatever
   produced the 08-28 reading** (see Method) — it lets more names through than a trailing-ADV
   floor would. Every tradeable-miss rate in this card is therefore an upper bound; a stricter,
   ADV-based floor can only lower it. Not cross-checked against a canonical dollar-volume source
   in the live pipeline.
4. **Live-era evidence is thin by construction**: only 6 trading days (08-25→09-01, 21 declines)
   have existed since the rule's rejects could bind a real admission at all. The 10%-over-30-days
   condition will not be evaluated on a fully live-era population until late September.
5. **No realized R anywhere in this card.** None of these names entered; every number is an
   unrealized excursion (MFE or settled) on a name that was never traded.
6. **Only the pinned-down denominator/basis combinations above were checked.** The signed
   condition's "+20%" text does not fix the horizon (5 sessions, matching both prior reads, is
   assumed) or the statistic; other reasonable choices were not swept.
