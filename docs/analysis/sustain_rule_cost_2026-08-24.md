# Is the real-time sustain rule costing us anything? (2026-08-24)

**MEASUREMENT ONLY. Nothing was changed. No rule, threshold, filter, toggle or trade state was
touched, and nothing here is a recommendation — any change it implies is the operator's fork
(THE LINE).**

## The answer in one line

**No. Zero alerts, zero trades, zero dollars — and it holds on two independent grounds.**
Structurally, the layer the rule gates is still SHADOW, so a decline removes a shadow catch that
was going to be discarded anyway. On the merits, **58 of the 66 names it declined had already
faded back below the gap floor by the opening bell** — the rule was right about them on its own
terms. Of the eight that did hold the floor and the three of those that then ran, **one was
alerted anyway through the delayed path and the other two were independently killed by different
signed gates.** Net cost across 16 trading days: **zero names**.

**Recommendation: leave it alone.** The rise in its decline rate is a filter doing its job on a
noisier pool, exactly as the framing anticipated. The one thing that genuinely needs saying is in
Result 7 — the rule's own pre-registered ≥+20% revert condition is literally met on the raw count,
and this study shows why that count is an artifact rather than a fault.

## The question

The alert-volume study (`docs/analysis/alert_volume_collapse_2026-08-24.md`, Result 5) found the
sustain rule declining ~10 names/day in the burst week and ~5/day since — flat in absolute terms
while the board halved, and flagged it as "quietly costing more than it was measured to cost."
**This study narrows that sentence.** The per-day counts reproduce exactly; the word "costing"
does not survive either the toggle read or the open-price control.

The rule is the #490 real-time admission gate, operator-signed 2026-08-02 at N=3: a level failing
to hold three consecutive minute bars at or above the gap floor is not admitted. Rejects are
logged by name as `ep_rt_sustain_reject`.

## Data

- **One read-only production capture**, pulled once and read many (cost rule), $0, no paid calls:
  `scripts/probes/_sustain_cost_capture.sql` → `_sustain_cost_capture_out.psv` (15,427 rows) — the
  `ep_rt_%` toggle rows; every `ep_rt_sustain_reject`, `ep_rt_sustain_undecidable` and
  `ep_rt_universe_catch` with its full detail JSON; `mi_ep_alerts`; the deduped `mi_ep_scan_log`;
  `mi_ep_missed_outcomes` with `last_refreshed_at`; and `mi_daily_closes` for every ticker in any
  cohort back to 2026-06-20.
- Arithmetic: `scripts/probes/_sustain_cost_analysis.py` → `_sustain_cost_analysis_out.txt`.
- **Metric definitions are copied from the canonical sources, not re-derived.** Forward returns use
  `missed_outcomes.refresh_missed_outcomes`' own SQL basis: `open_d0` = the gap day's open,
  `max_high_5d` = MAX(high) over d0..d0+5, `ret_5d` = close of the 5th session after d0, all against
  `open_d0`. The tail statistic is `_552_missed_why_cohort.sql`'s `tailx` — 20-day ADR from the 20
  sessions preceding d0, forward high over d0+1..d0+20, in the name's own ADR units — identical to
  the delayed-screen and silent-floors studies, so the numbers are comparable across them.
- **Both cohorts measured off `mi_daily_closes`, same basis, same dates, same censoring.**
  `mi_ep_missed_outcomes` is a cross-check only, under the #583 freshness guard (`_outcome_is_fresh`,
  reused not re-derived). Across the 144 ticker-days where a fresh outcome row and a recomputed bar
  series both exist, the two agree to **0.000 percentage points**.
- **No realized R exists anywhere here.** None of these names entered; there is no ORB fill, no
  bracket, no stop. Everything below is an unrealized excursion on a name we did not trade.
- ⚠ `mi_ep_missed_outcomes` covers only 21 of the 66 declined ticker-days — most declined names
  never entered the missed pipeline. Reported, not routed around.
- Suite green at **6181 passed / 7 skipped**. Nothing was committed or deployed.

## Result 1 — the gate is shadow, verified live, not read off a doc

`mi_safeguard_state`, every `ep_rt%` row that exists, read from prod 2026-08-24 19:14 ET:

```
ep_rt_entry_gap_recheck        on    since 2026-08-01 20:34
ep_rt_gap_down_authoritative   on    since 2026-08-01 20:00
ep_rt_sustain_enabled          on    since 2026-08-02 09:53
ep_rt_universe_authoritative   NO ROW  -> False
ep_rt_gap_authoritative        NO ROW  -> False
```

`_sustain_ok` has **exactly one call site** (`ep_detector.py:2215`), inside
`_apply_rt_universe_overlay` at the would-be-catch — and 41 lines later that function reaches
`if not authoritative: continue`. `ep_rt_admit`, the only other event in the window that could have
hidden an acting path, is emitted from `_apply_rt_gap_overlay`, is labelled telemetry-only in its
own comment, and has no sustain gate.

**So the rule cannot have cost a single alert or trade**, exactly as the 2026-08-02 change-log entry
says ("its blast radius today is telemetry, not trading").

## Result 2 — "one in three, up from one in seven" is two separate overstatements

106 reject events, 2026-08-03 → 2026-08-24, 16 trading days. The collapse study's per-day counts
reproduce exactly (51/5 = 10.2 in the burst week, 22/5 = 4.4, 27/5 = 5.4). Two corrections:

**(a) 40 of the 106 rejects were caught later the same day.** The audit dedupe is per ticker-day per
event type, so a name can be rejected at 08:15 and caught at 09:20 once the level holds. Those were
**delayed by the rule, not declined by it**. Net declined = **66 ticker-days**, not 106.

**(b) The 73 `ep_rt_sustain_undecidable` ticker-days belong in the denominator.** Undecidable FAILS
OPEN — those names were admitted.

| week | reject events | net declined | merely delayed | passed | undecidable | rejects / arrivals | **declined / arrivals** |
|---|---|---|---|---|---|---|---|
| 08-03 → 08-07 | 51 | 28 | 23 | 89 | 39 | 28.5% | **17.9%** |
| 08-10 → 08-14 | 22 | 15 | 7 | 51 | 17 | 24.4% | **18.1%** |
| 08-17 → 08-21 | 27 | 19 | 8 | 41 | 16 | 32.1% | **25.0%** |
| 08-24 (1 day) | 6 | 4 | 2 | 4 | 1 | 54.5% | 44.4% |

Arrivals = rejects + passed + undecidable. **The true decline rate went from about one in five and a
half to about one in four** — it rose, and the direction in the collapse study is right, but it is
not one in seven to one in three. The earlier ratio mixed two funnels: sustain rejects come off the
real-time overlay's would-be-catch set, while "candidates the scan saw" is the delayed scan log's
population.

## Result 3 — the control that decides it: did the level actually HOLD at the open?

The rule's claim is that a level touched once and gone is a **print**, not a **level**. That claim is
directly testable against the next data point nobody had checked: where the stock actually opened.
`gap_at_open = (open − prior session close) / prior session close`, against the floor in force that
day (10.0% through 08-19, 9.0% from 08-20 — both from `mi_daily_closes`, already in the capture).

| cohort | held the floor at the open | median gap at open |
|---|---|---|
| **declined** | **8 / 66 = 12%** | +4.2% |
| passed | 53 / 185 = 29% | +5.3% |
| rejected-then-caught same day | 10 / 40 = 25% | +4.8% |

**58 of the 66 declined names had faded back under the gap floor before the opening bell.** They
were not EPs we missed; they were pre-market prints that did not survive to the open. On its own
stated terms the rule was correct about 88% of what it declined.

🔴 **This also exposes a denominator artifact that runs straight through the naive comparison.** A
name whose spike faded opens *lower*, so `max_high_5d / open_d0` is mechanically inflated for
exactly the population the rule rejects. Measured without the control, the declined cohort looks
*better* than the kept cohort on settled rows — median 5-session max high +16.8% vs +12.3%, reaching
≥+20% 40% of the time vs 23% (Fisher p = 0.036). **That result is the artifact, not a finding.** It
is the same faded-then-crossed population `docs/analysis/490b_faded_crossed_timing_2026-08-18.md`
already concluded is unreachable, re-entering through a different door. It is recorded here because
it is what the numbers say before the control, and burying it would leave the next reader to
rediscover it.

Inside the held-at-open subset the comparison **cannot be run**: 8 declined names, 5 of them with
five settled sessions, against 45 passed. n=5 is anecdote-grade and no p-value computed on it should
be cited. **That thinness is itself the answer** — there is barely anything left to compare once the
faded prints come out.

## Result 4 — no reachable tail winner was declined

Every name in either cohort reaching the program's ≥8×ADR tail bar, with the control applied:

| name | cohort | tailx | gap at open | floor that day | verdict |
|---|---|---|---|---|---|
| ARCT 08-07 | declined | 20.2× | **+6.4%** | 10% | did not hold — rule was right |
| TNON 08-11 | declined | 16.5× | **+1.7%** | 10% | did not hold — rule was right |
| ZLAB 08-06 | declined | 9.0× | **+3.7%** | 10% | did not hold — rule was right |
| SDOT 08-21 | passed | 11.4× | **−2.4%** | 9% | did not hold (and was admitted) |

**All three declined tail names opened far below the floor.** ARCT did run 6.47 → 14.53 over the
following 11 sessions, but it opened at +6.4% against a 10% floor — it was never an EP that morning
by our own criterion, and it is separately `filter:mcap_too_small: $233M < $500M` in the scan log.
TNON is `filter:adv_too_low: $159,684`. Their later multi-session trends are a different phenomenon
from a missed gap, and treating them as declined EPs would be the error this control exists to
prevent.

**Answer to "was any large runner declined": no — not one that held the level it was declined for.**

## Result 5 — the net cost, name by name: zero

Applying both filters — held the floor at the open, then ran ≥+20% over five sessions — leaves
**three** candidates out of 66 declines. Every one of them resolves to no cost:

| name | gap at open | 5-session max high | what actually happened to it |
|---|---|---|---|
| **DCTH 08-06** | +11.1% | +24.2% | **alerted anyway** through the delayed path — cost zero |
| **AVAH 08-13** | +11.5% | +32.8% | scan log killed it independently: `score 30 < 50 (catalyst=routine)` |
| **MATV 08-06** | +12.2% | +26.2% | scan log killed it independently: `outside top-20 gap cap (gap 12.3%)` |

**Not one name reaching the ≥+20% bar in 16 trading days is a cost attributable to the sustain rule** — and that is before
Result 1, under which none of them could have been admitted anyway. Nine names in the *passed*
cohort clear the same two filters, so the rule is not starving a pool that has nothing in it.

## Result 6 — the mechanism, and it vindicates the operator's premise

`_sustain_ok` reads the last three minute closes oldest→newest and rejects unless **all three** sit
at or above the floor. Classifying all 66 declines by the shape of the bar series in their own audit
detail, and then asking the control question of each shape:

| shape of the three bars | share of declines | held the floor at the open |
|---|---|---|
| **RISING into the level** (newest bar is the high) | 53/66 = 80% | **5/53 = 9%** |
| flat / mixed | 9/66 = 14% | 2/9 = 22% |
| FADING off the level | 4/66 = 6% | 1/4 = 25% |

Four out of five declines are a name climbing *through* the floor in the last minute — not the
spike-then-crash shape of MYGN 07-30 and QURE 07-29 that prompted the rule. Straight from the audit
rows: `BOW 08-03 [9.51, 9.84, 10.20]`, `CRWV 08-03 [7.66, 9.11, 10.00]`,
`LUNR 08-04 [3.80, 3.81, 10.23]`.

**That looked like the rule mis-firing until the control was run. It is not.** Only 9% of those
risers still held the floor at the open. A single accelerating bar tagging the level is precisely
the operator's *"just a single 1min bar touching >10% may be too loose"* — and the open confirms it
nine times out of ten. **The rule is measuring the right thing.**

## Result 7 — the pre-registered watch conditions, stated honestly

`docs/setups/magna53_ep.md`, 2026-08-02, pre-committed at signing:

> **Watch for**: first 30 live catches vs the replay's prediction — materially worse means the
> replay was fitted, revert; **a rejected name running ≥+20% once is a review, twice a revert.**

**Arm 1 — literally met, and the literal count is misleading.** 20 declined names reached ≥+20% on
5-session max high vs the gap-day open. **But 17 of the 20 had faded below the floor at the open**
(Result 3), so their ≥+20% is measured off the depressed open the fade itself created. The three
that held are the Result 5 table, and all three cost nothing. Surfaced because it is his
pre-registered condition and it is his call — with the note that the condition, as written, counts
the artifact.

**Arm 2 — the rule is roughly neutral on the pool, not a lift.** Recomputed with the 73 undecidables
on both sides, since they are admitted under either regime:

| | median open → close | win ≥ +5% |
|---|---|---|
| replay's 2026-08-02 prediction for the admits | +5.0% | 50% |
| rule ON (admitted: passed + undecidable), n=258 | +2.8% | 40% |
| rule OFF (all arrivals), n=324 | +3.1% | 41% |

The replay predicted the rule would lift the pool above the unfiltered baseline. Live it sits
**0.3 points below** it — i.e. flat, well inside noise. ⚠ The replay's cohort was 07-27 → 08-02 and
this one is 08-03 → 08-24, a different tape, so this is not a like-for-like refutation. The fair
reading is that **the lift the replay forecast has not shown up, and no harm has either.**
"Materially worse" is his threshold to apply, not mine.

## The fork — his call, not pre-decided

⚖ **Admission criteria are the operator's sole authority. No threshold is proposed here and no rule
was touched.** What the evidence puts in front of him:

- The rule costs **nothing today** and will keep costing nothing while `ep_rt_universe_authoritative`
  stays off. It also costs nothing on the merits: zero names in 16 trading days.
- Its ≥+20% revert condition is met on the raw count (20 names) and the count is an artifact of the
  fade it correctly rejected. **Whether to leave the condition as written is a real question** — as
  worded it will keep firing on faded prints.
- The lift the 2026-08-02 replay predicted has not appeared; the rule is neutral, not harmful.
- **Input to #559 (whether to flip real-time admission on):** the sustain rule removes about one in
  four of the pool that flip would admit, and this study says that quarter contains **no reachable
  tail winner and no recoverable name**. That is a point in favour of the flip being *cheaper* than
  feared on this axis, not a reason to touch the sustain rule itself.
- ⚠ **The sharper #559 number, from the same control: only 53 of the 185 names the rule ADMITS
  (29%) held the gap floor at the open either.** The rule lifts the hold rate from 12% to 29% —
  real, but the pool RT-3 would admit is dominated by pre-market prints that do not survive to the
  bell, sustain rule or not. That is a fact about the pool, not a proposal about the flip.

## What this does NOT answer

1. **It cannot say what the rule would cost after the RT-3 flip, only what it removes.** Everything
   is measured on a shadow population. Post-flip the declined names would still face the catalyst
   grader, the market-cap and ADV floors, the cooldown, the extension cap and the top-20 rank cap —
   Results 4 and 5 show those gates already killing every candidate the sustain rule dropped.
2. **No realized R exists anywhere in this study, and none was manufactured.** These are excursions
   from the gap-day open on names that never entered. Under our own mechanics — 09:31 ORB entry,
   stop at `entry − 2R` — the realized outcome of any of them is unknown and is not estimated here.
3. **Right-censoring is heavy.** 21 of 66 declined and 35 of 185 passed rows lack five settled
   sessions; the ≥8×ADR statistic wants 20 forward sessions and the deepest row here has 15. **Every
   tail share above is a FLOOR.** ARCT was at its high on the last bar of the window. **Re-read after
   2026-09-22**, when the last cohort day settles 20 sessions. The control (open price) is *not*
   censored, so Results 3-6 are stable under a re-read; only the tail magnitudes can move.
4. **The held-at-open subset is too thin to compare, and that is stated rather than papered over.**
   8 declined names, 5 settled. No conclusion is drawn from it beyond the named three.
5. **The real-time layer remains upstream of the scan log** — the blind spot the collapse study
   flagged as its own limitation 1. Only 21 of 66 declined names ever appear in `mi_ep_scan_log`, so
   for the other 45 there is no funnel record of why they would or would not have survived. This
   study inherits that blind spot rather than closing it.
6. **It says nothing about the undecidable class.** 73 ticker-days fail open and are admitted with no
   verdict. Whether the fail-open direction is right was not measured; it is a separate question.
7. **16 trading days.** The open-price control is decisive within them, but the rule has been live
   for three weeks and no longer than that.
