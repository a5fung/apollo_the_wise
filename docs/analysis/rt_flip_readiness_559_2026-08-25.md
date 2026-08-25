# #559 — Is it time to trust the live price feed for admission? (2026-08-25)

**MEASUREMENT ONLY. Nothing was changed. No rule, threshold, filter, toggle, or trade state was
touched.** Admission criteria are the operator's sole authority (THE LINE). This document measures;
he rules.

## The answer in one line

**Flipping it adds about half an alert a day and, on 17 trading days of evidence, zero extra real
EPs — the "nine more catches a day" is really about three a day the delayed feed never sees, and
all but one a day of those die on liquidity, size or volatility before anything grades them.**

## The two numbers he asked for

| | per trading day |
|---|---|
| **Extra ALERTS** (the cost) | **0.30 to 0.62**, hard ceiling **1.59** |
| **Extra REAL EPs** (the benefit) | **0 measured** — and this window could not have seen a rate below about 1.3 a month |

For scale, the raw shadow line he is reading says 11.4 catches a day, and the live alert rate over
the same 17 days was 4.06 a day — though that 4.06 was produced by the *old* rubric (every alert row
in this window was written before the 08-22 rebuild), so it is not a clean denominator. Re-scored on
today's rubric, only 19 of the 25 alerts in this population would still fire.

## Why 11.4 catches a day is not 11.4 alerts a day

Every catch still faces liquidity, size, volatility, extension, cooldown, the 20-name grading
shortlist, the catalyst grade and the score bar of 65. Over **17 trading days (2026-08-03 to
2026-08-25, 194 catches)**:

| | count | per day | what it means |
|---|---|---|---|
| Caught by the live feed | 194 | 11.4 | the raw shadow line |
| **Already alerted that same day anyway** | 25 | 1.5 | the delayed feed caught up; flipping only makes the alert **earlier**, not extra |
| Seen by the delayed scan, killed on the merits | 107 | 6.3 | they got their shot and lost it |
| **Never seen by the delayed feed at all** | **62** | **3.6** | the only class the flip actually adds |
| …of those, surviving liquidity / size / volatility / extension / cooldown | 27 | 1.6 | |
| …of those, expected to clear the score bar of 65 | 5 to 10.5 | **0.30–0.62** | **the extra alerts** |
| …of those, still gapping 9%+ at the open (i.e. enterable) | 3 | 0.18 | an alert is not a trade |

What kills the 35 rt-only names that do not survive: **11 trade under $1M a day, 11 are under $500M
market cap, 5 are inside the 60-day cooldown, 4 are already up 75%+ in the prior five days, 4 are
too volatile (ATR over 15%)**. This is a small, thin, illiquid population — the delayed feed is not
hiding large liquid names from us.

## The benefit side, measured honestly

- **Zero** of the 27 gate-surviving rt-only names has run 8× its own daily range in the next 20
  sessions. The best is RIGL at 3.9× with 13 of 20 sessions run. Every forward window is still
  incomplete, so every count here is a floor.
- Across all 62 rt-only names there is exactly **one** 8×-plus mover — SDOT on 08-21, 11.4× — and it
  was killed by the **ATR over 15% gate, not by the data feed**. Flipping the feed would not have
  caught it; loosening ATR would.
- **The two operator-labelled real EPs the shadow caught in this window — MRNA (08-19) and MRVL
  (08-19) — both alerted through the normal delayed path anyway.** They are the only two names from
  the 26-name must-not-miss list that appear at all. On this window, the delayed feed is not losing
  the ones that matter.

## The counter-intuitive part: the rebuild did not make this population safer to admit

His premise is "the filters are tighter now, so admitting more is safer." For **this** population the
rebuild moved the other way — it made these names **easier**, not harder, to alert:

| if the catalyst grades… | cleared the OLD rubric + per-regime bar | clears the NEW rubric at 65 |
|---|---|---|
| game changer | 19 | **27** |
| strong | 4 | **19** |

The reason is the rescale plus the flat gap credit: a thin 11% gapper used to need the old gap ladder
and conviction floors to reach a bar of 70–80, and now clears a flat 65. So the tightening he is
thinking of (gap size no longer buying a grading slot, liquidity becoming dominant) tightened the
**ranking**, not the **bar** — for a small-cap 11% gapper the bar got easier to reach. That does not
make the flip wrong; it means "our filters are tighter now" is not by itself the argument for it.

## The effect that is not "more alerts" — smaller than it first looks

**19 HIGH alerts in these 17 days (1.1 a day) arrived at 09:45 ET or later, after the order window
closed.** They logged `window:out_of_orb` and no order was ever placed. They cost attention and
bought nothing.

Six of those 19 had already crossed on the live feed inside the 09:31–09:44 window. **But those alert
rows are old-rubric — they were all written before the 08-22 rebuild — so they had to be re-scored
before any of them could be called a rescue.** Re-scored on today's rubric:

| | caught | alerted | catalyst | today's score | still an alert? |
|---|---|---|---|---|---|
| TSAT 08-04 | 07:45 | 09:56 | game changer | 105 | **yes** |
| HGTY 08-05 | 09:40 | 09:55 | strong | 52–68 | only on the generous read |
| NMAX 08-14 | 09:35 | 09:50 | strong | 52–68 | only on the generous read |
| LIND 08-03 | 09:40 | 09:55 | strong | 46–59 | no |
| MTW 08-07 | 08:35 | 09:52 | routine | 30–45 | no |
| ACHR 08-10 | 08:05 | 09:45 | routine | 45–60 | no |

**So the honest rescue count is 1 certain and 3 at best over 17 trading days — 0.06 to 0.18 a day,
not the 0.35 the raw count suggested.** Three of the six were routine-catalyst or thin-liquidity
alerts that today's rubric would not raise at all.

Across all 25 names that were caught and alerted anyway, the median alert would have arrived **15
minutes earlier**, and 20 of the 25 at least 15 minutes earlier — several of them hours earlier
(TSAT +131 min, ATRO +125 min, KMT +115 min, ACHR +100 min). Two of the 25 (ARGX, SLN) alerted
*before* the shadow caught them, so the flip would have changed nothing for those.

⚠ **Not established:** whether each would still have scored HIGH at the earlier tick. The catalyst
grade and the volume pace both move through the morning, and an earlier look is a look at less
information. This is a plausible benefit, not a measured one.

## His nine names from today (2026-08-25), through the same gates

| ticker | live gap | tick | class | outcome |
|---|---|---|---|---|
| APMD | 9.2% | 07:05 | the delayed scan saw it | already had its shot |
| SPAI | 10.4% | 07:25 | the delayed scan saw it | already had its shot |
| MEI | 10.3% | 08:05 | the delayed scan saw it | already had its shot |
| **HMN** | 17.2% | 08:20 | **rt-only** | **survives every mechanical gate** |
| NBBK | 24.4% | 08:40 | the delayed scan saw it | already had its shot |
| OESX | 13.8% | 09:45 | the delayed scan saw it | already had its shot |
| ABCL | 9.6% | 09:45 | rt-only | inside the 60-day cooldown |
| PSQH | 9.9% | 09:45 | rt-only | trades under $1M a day |
| **CRML** | 12.1% | 09:45 | **rt-only** | **survives every mechanical gate** |

Five of the nine were not invisible at all — the delayed scan saw them the same day. Two of the four
genuinely new names die on cooldown and liquidity. **Two survive to grading, and both would still
have to clear the bar of 65.** Note also that OESX, ABCL, PSQH and CRML were all caught at 09:45 —
after the order window closed — so even a HIGH would have produced no trade today.

## The plumbing — verified on production 2026-08-25

- `ep_rt_universe_authoritative` has **no row** in `mi_safeguard_state` → default off → **the layer is
  still pure shadow.** Every catch is logged and none is admitted.
- Master flags are ON in the container: `EP_RT_UNIVERSE_ENABLED=true`, `EP_RT_PASS2_ENABLED=true`.
  The overlay runs and fetches the universe every tick today; only the admission is withheld.
- **The flip is one row and about 60 seconds, no redeploy.** `get_runtime_toggle`
  (`agents/market_intelligence/db.py`) reads `mi_safeguard_state` with a 60-second cache; the flip is
  a single upsert of `('ep_rt_universe_authoritative','global','on')`. **The revert is the identical
  statement with `'off'`** — same 60 seconds, no deploy, and the code path returns to byte-identical
  shadow behaviour. Fail direction on any error is the delayed path.
- **The shadow has recorded continuously and completely.** 37–38 scan ticks every trading day from
  08-03 to 08-25, **100% real-time snapshot coverage on every single day, zero symbols missing, zero
  degraded batches.** The sample is not thinned by instrumentation gaps.
- **The #490 sustain rule sits UPSTREAM of the authority flip**, inside the same overlay function and
  before the catch is even emitted. It has been on since 08-02. So every catch counted here has
  already passed it, and flipping the authority does not bypass it.
- **The real-time VOLUME flip is a separate toggle and is still off** (`ep_rt_volume_authoritative`,
  no row). A newly admitted name would be graded on **delayed** volume. See the gap below.
- Two related toggles are already on and only ever REMOVE candidates:
  `ep_rt_gap_down_authoritative` and `ep_rt_entry_gap_recheck` (both since 08-02). The latter is why
  only 3 of the 27 survivors were actually enterable — the rest had faded back under 9% by the open.

## Both directions (P14)

- **Over-admission** (admit junk): visible and survivable. Worst case is roughly **+1.6 alerts a day**
  — a 40% increase in alert volume — and the 20-name grading shortlist would compete harder (it
  already binds: 25 of the caught names were logged "outside the graded shortlist"). Every extra
  admission also costs an LLM catalyst grade. The 5-position cap is not reached: only 3 names in 17
  days were enterable at all.
- **Under-admission** (miss a real EP): invisible and fatal to the edge, and **this window has no
  power to rule it out.** 27 gate-surviving rt-only names over 17 days produced zero tail winners; a
  true rate below roughly one winner per 17 trading days simply cannot be distinguished from zero
  here. "Zero measured" is **not** "zero". The one genuine 8×-plus mover in the rt-only pool was lost
  to the ATR gate, not to the feed — which points at a different fork entirely.

## What could go wrong if he flips it

1. **The volume gate is unmeasured on this population, by design.** A newly admitted name is graded
   on delayed volume, which has not yet seen the session volume the live price implies. Nine of the
   caught names the delayed scan did see died on "volume pace below normal". The real-time volume
   flip is a *deliberately later* step — the design has it as RT-5, at least three market days after
   the gap flip — so gap-first-then-volume is the planned sequence, not an inconsistent half-state.
   The honest gap is that the real-time volume shadow only ever runs on names that are already
   candidates, so it has **never once observed this population**. If the delayed-volume gate kills
   most of the new admissions, the flip does less than the numbers above; if not, slightly more.
2. **The catalyst grade is a guess in these numbers.** None of the 27 survivors was ever graded, so
   the extra-alert band is derived from the measured grade mix of everything the scan did grade in
   this window (game changer 17%, strong 28%, routine 55%, n=192). That base rate comes from names
   that made the top-20 shortlist of *delayed* candidates — liquid, larger, real news. The 27
   rt-only survivors are thin pre-market prints by construction, so their true mix is almost
   certainly more routine-heavy, which pushes the expected extra alerts toward or below the 0.30
   floor rather than up.
3. **Cost.** Every extra admission is an LLM catalyst grade plus an FMP profile fetch, at up to ~1.6
   extra names a day.
4. **Market caps.** Seven of the 62 rt-only names have no market cap on record; the live path lets an
   unreadable market cap through, so they are counted as survivors here. Given that 11 of the 36
   names with a readable market cap failed the $500M gate, several of those 7 would probably fail it live — the survivor
   count is more likely an over-count than an under-count.

## Is the evidence strong enough?

**For the cost side: yes.** 17 trading days, 194 catches, complete instrumentation, and the funnel is
mechanical. The alert-volume answer is solid: this adds well under one alert a day.

**For the benefit side: not yet.** Every forward window is incomplete — the median catch has run 11
of its 20 sessions. **2026-09-22 is when the last cohort day (08-25) completes its 20-session
window**, and the 08-18 read on the same population pinned 2026-09-15 for its own cohort. Until then
"zero extra real EPs" is a floor with no power behind it, not a finding.

**And two market days of post-rebuild live evidence is nothing.** The rebuild landed Saturday 08-22;
08-24 and 08-25 were both zero-alert days on a thin tape. Everything above is replay, not observation.

## The fork, as his decision

**Flip `ep_rt_universe_authoritative` on now, or wait for 2026-09-22?**

- **Flip now:** costs about half an alert a day (worst case 1.6), reverts in 60 seconds with one
  toggle, and buys the chance that the six-a-month late alerts start arriving inside the order
  window. Best justified as *starting the clock on real evidence* — a live flip would put these names
  through the actual catalyst grade and the actual volume gate, which is the only way to close the
  two unmeasured gaps above.
- **Wait:** costs nothing except the same handful of names staying invisible for four more weeks, and
  by 2026-09-22 the forward windows settle and the "does it add a real EP" question becomes
  answerable on the shadow record alone, at zero risk.

**Recommendation, one line:** wait for 2026-09-22 — the measured benefit is zero, the late-alert
rescue shrinks to one name in 17 days once today's rubric is applied, and waiting costs almost
nothing while making the question actually answerable.

## What this does NOT answer

1. **Whether the volume gate kills the new admissions.** The real-time volume shadow has never
   observed this population, and the real-time volume flip is a separate toggle that is still off.
2. **What any of these names would actually be graded.** No LLM was run (the $0 constraint); the
   catalyst term is a base-rate estimate.
3. **Whether an earlier alert would still have been a HIGH.** Grades and volume pace both move
   through the morning; an earlier look is a look at less information.
4. **Whether any of this converts to money.** This is selection only — no entry quality, no exit, no
   realized R.
5. **The 107 names the delayed scan saw and killed.** Roughly 30 of them died on gates the timing of
   the flip could in principle move (shortlist rank, volume pace, pre-market share floor). Whether an
   earlier look rescues any of them is a separate question this replay does not settle.
6. **Anything about the fade class.** Names that crossed on the live feed and then opened below the
   floor are excluded by the entry re-check regardless of which feed we admit on — that is the
   floor-timing fork, not this one.
7. **How the delayed path would treat those 107 today.** Every alert and scan-log row in this window
   was written under the pre-08-22 rubric, so "the delayed scan killed it on the merits" is an
   old-rubric verdict. It does not affect the headline — the 62 rt-only names have no grade under
   either rubric — but the 25/107 split between "alerted anyway" and "killed" would look different
   if the whole window were re-run today (19 of the 25 would still alert; 6 would not).
8. **The pre-08-03 record.** 96 catches from 07-27 to 07-31 are excluded: they predate the sustain
   rule, which sits upstream, so they are not the population a flip would admit today. Coverage
   telemetry also does not exist before 08-03.

## Reproduction

- One read-only production capture, 2026-08-25, $0: `scripts/probes/_559_rt_flip_capture.sql` and
  `_559_rt_flip_capture2.sql` → `scripts/probes/_559_*.tsv`. Never re-run to re-read.
- Arithmetic: `python3 scripts/probes/_559_rt_flip_analysis.py` (deterministic, offline). Full
  stdout saved at `scripts/probes/_559_rt_flip_out.txt`.
- The score and shortlist maths **import `agents.market_intelligence.ep_rubric` directly** — the same
  weights, bar, conviction floor and output scale the live scan uses — rather than re-implementing
  them. Gate thresholds are mirrored from `backtester/filters.py` and `ep_detector.py` and named in
  the script.
- Market caps reuse the yfinance fill already paid for by the 2026-08-18 #490 capture
  (`_490cost_mcaps_yf.tsv`); no new paid calls.
