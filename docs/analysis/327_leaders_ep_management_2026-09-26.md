# #327 — leaders plus EP-style management on the delayed-entry lane: does any cell keep the winners while limiting losses? NO — no lift

**2026-09-26 (Saturday build slot, after Block 5 and its addendum).** **0 of 122 cells clear the pre-registered
bar at session 20 and 0 of 122 at session 10; not one cell has a positive mean R — on all fires or on
leaders, on any of 3 stops × 20 management arms, on the recorded or the fillable entry.** The leader
filter (≥ $5, above a rising 50-day and above the 20-day) makes the lane WORSE, not better: its fires lose
−0.48 to −0.84R per fire under every arm (n = 73–130 at s10; −0.49 to −1.06R at s20, n = 18–33) and keep ≥ 3R on
at most 2.8% of them.
EP-style management does what he described — holding with a breakeven stop keeps ≥ 3R on 21–26% of the
fires in stocks that went on to run +50% (n = 320), against 5.6% for the lane's own exit (n = 267) — but
those fires are 9% of the lane, and each of the other 91% then costs −0.60 to −0.70R against −0.55R
today, so the whole lane still nets −0.32 to −0.35R per fire. The Method section below was committed
before any cell was computed (`2868bdc2`); nothing in it changed. Nothing is picked here — no stop, no
target, no selection rule (THE LINE).

## The question it serves

Block 5 (`327_exit_determination_2026-09-26.md`) found no stop × target × FULL-exit cell pays on the
lane's whole population, and its addendum found the lane was IN about 70% of the stocks that ran +50%
within 15 sessions and was stopped out of most while they were up several R. His response, 2026-09-26:
*"Pick better plus like our EP, we take partials and adjust stops, so there's various things in play"*
— and earlier the same day: *"any EP related trades are low winrate by default, what we want is always
to catch big winners while limiting losses."* Block 5 never tested EP-style management (partial profit,
stop moved to breakeven, remainder trailed) and never a leader-only selection. This day tests exactly
those two, tail first, against the same bars, with a matched control.

## Method and population

Fixed before any number; the probe is `scripts/probes/_327_block5/p6_leaders_mgmt.py`, its docstring
is the pre-registration of record.

**Population.** Every row of `mi_delayed_entry_trigger` in the Block 5 extract (3,767 fires on 700
tickers, fire_date 2026-08-25 → 09-25), the same `mi_daily_closes` pull (2025-12-01 → 09-25, one
adjusted price scale; every fire-time price rescaled by `close(fire_date) / trigger.day_close`), the
same day-0 minute bars, the same ADR$ (`compute_ep_adr_dollar`). Population per checkpoint = SESSIONS
ELAPSED by 09-25, never settlement status: session 20 → fire_date ≤ 08-27, n = 1,214 fires; session 10 →
n = 3,398 fires.

**Selection ("leader") — evaluated at the fire, from bars strictly before the fire date, on the daily
table's scale:** prior close ≥ $5 · above its 50-day SMA · that 50-day SMA above the 50-day SMA ending
ten sessions earlier (rising) · above its 20-day SMA. Under 60 prior closes = unclassifiable, not a
leader. Sized before any result: **s10: 143 of 3,398 fires (52 of 693 names); s20: 37 of 1,214 fires
(21 of 463 names).** Every result is reported for all fires and for leaders side by side.

**Management arms (the declared family, 20 walked arms + M0):**

| arm | rule |
|---|---|
| M0 | the lane's own recorded settlement: incumbent stop, trail on max(SMA10, SMA20) close-below, s20 time exit (`r_trail_sK`); its no-exit arm (`r_none_sK`) beside it. House convention (a stop is exactly −1.00R), settled rows only. |
| M1_orb2 | the LIVE MAGNA53 exit stack as of the fire date (`rule_eras.exit_rules_as_of(fire_date, "magna53")` → `stack_walk_inputs` → `walk_arm(harvest="live_ladder")`, never re-implemented), with the lane's stop playing the live stop (ORB-R = half the stop distance): era D (fires ≥ 09-06) partial 1/3 at +4R, breakeven armed at +1.5R; era C (fires < 09-06) partial at +1R, breakeven at the partial. Trail max(SMA10, SMA20). |
| M1_orb1 | the same stack with ORB-R = the whole stop distance: era D partial at +8R, breakeven at +3R; era C partial at +2R, breakeven at the partial. |
| M2..M19 | partial 1/3 at {+2R, +3R} × breakeven at {+1R, +2R, after the partial} × remainder {10-day SMA close, 20-day SMA close, held to s20}. R = the cell's own stop distance. The breakeven raise takes effect from the next bar (an end-of-session order change). The trail governs whatever is open, from day 0, line includes the session's own close. |

⚠ Most fires with 20 sessions elapsed fired under **era C — the retired +2R rule**; M1's n per era
sits beside every M1 cell. `walk_arm` has no daily path: day 0 is walked on real 1-minute bars where
`mi_intraday_bars` has them, else on a synthetic two-bar day (fill point, then one excursion bar in the
production `day0_pseudo_bars` shape: cached post-fire low/high for a minute fire, the whole fire-day
range for a level-priced fire, {high = entry, low = day low} for a minute fire with no source; a day
low at/below the stop with no source abstains, as in P3). `walk_arm`'s own abstains (a bar holding both
the stop and the target or the breakeven trigger) are counted per stop; M1's scored population is
expected to be smaller than M2..M19's.

**Stops (3):** the incumbent stop · entry − 0.5×ADR$ · entry − 1.0×ADR$. A stop at/above the entry
kills the fire. **Within a bar:** stop (low) first, then partial / breakeven (high), then trail
(close). **Every walked arm is read GAP-CHARGED** — a session that opens below the resting stop fills at
the open (walk_arm's rule) — which is what makes "losses limited" a testable leg; M0 as recorded is
house convention (P3 measured the gap effect at 0.03R on the incumbent cell). **Width floor** ≥ 0.5% in
the cell's own stop units (Block 5's rule), unfloored n reported.

**Draws:** per checkpoint 2 selections × (M0 + 3 stops × 20 arms) = **122**; two checkpoints = 244, on
the recorded entry. Noise band scaled from the block's 1–3 of 294: **≤ 1 of 122 per checkpoint is
noise; ≥ 10 is a family.** The fillable entry (max(level, fire-day open) for level-priced fires) is run
on every cell and reported beside — a robustness read, not extra draws.

**Checkpoints:** session 20 is the bar (open positions marked at the s20 close). Because the leader
filter at s20 (37 fires, 21 names) is below the n floor by construction, the identical bar is applied
at session 10 beside it — declared now, not after a result.

**Pass bar (tail first), a cell is a CANDIDATE only if ALL hold:** mean R > 0 · kept ≥ 3R rate ≥ 3.0%
(3× the incumbent's 1.01%) · average loss (mean R over losers, gap-charged) no worse than −1.0R · mean
R > 0 after dropping the single best NAME by summed R · n ≥ 100 fires over ≥ 40 names · positive mean
in both time halves (s20: split at 08-27, so the second half is ONE fire date; s10: split at 09-08,
four fire dates). The count of clearing cells is judged against the draws before any cell is named.

**Control:** the same selection and management on the matched non-fire sessions from P2 — every
non-fire session inside the 20-session window of each campaign where the lane fired, entered at that
session's close (no day 0), leader flag evaluated at that session, stops 0.5×/1.0×ADR$ (the incumbent
stop has no non-fire analogue). Fire minus control on mean R and kept-3R per cell.

**Big runners:** re-derived (the addendum's script was not committed) — watched (ticker, EP date) with
EP date ≤ 09-04 and ≥ 10 later sessions of bars; base = the EP-day close; "ran" = highest high within
15 sessions ≥ +50% over base (the addendum counted 142, 24 at ≥ $5 — reproduced or the difference
stated). Per arm and stop: fires in runner campaigns kept ≥ 3R (fires and campaigns) versus M0, and the
arm's mean R on every non-runner fire versus M0's on the same fires. Runner fires with under 20
sessions elapsed are marked at their last available close.

**Validation before any cell is read:** (a) the probe's own walker with no partial, no breakeven,
remainder ∈ {hold, max(SMA10, SMA20)} reproduces the recorded `realized_r` / `realized_r_trail` on
settled rows a $0 day-0 source can walk (P3's cross-check (a)); (b) the same walker against
`walk_arm(harvest="trail_only")` on identical synthetic bars, R within 0.001.

$0 throughout: no prod write, no toggle, no table, no PLAN.md line; the lane keeps observing exactly as
it did yesterday.

## RESULT, tail first — the grid at both checkpoints (recorded entry)

| | session 20 (the bar) | session 10 (beside it) |
|---|---:|---:|
| draws | 122 | 122 |
| cells clearing every leg | **0** | **0** |
| cells with mean R > 0 (either selection) | **0** | **0** |
| cells with kept-≥3R ≥ 3% — all fires | 7 (all with mean −0.27 to −0.40) | 7 (mean −0.23 to −0.43) |
| cells with kept-≥3R ≥ 3% — leaders | 6 (n = 19 each, mean −0.49 to −0.80) | **0** |
| best mean R, all fires | −0.07 (`0.5×ADR / partial +2R, BE +1R, SMA20 trail`, n = 864, kept ≥3R 1.7%) | −0.20 (`incumbent / +2R, BE +1R, SMA10`, n = 1,316, 2.4%) |
| best kept-≥3R, all fires | 4.4% (`1.0×ADR / partial +3R, BE after, hold`, n = 1,107, mean −0.34) | 3.6% (`0.5×ADR / +3R, BE after, hold`, n = 2,555, mean −0.43) |
| the lane's own arm M0 (incumbent stop, trail) | n = 1,171 on 455 names: mean −0.32, kept ≥3R 2.4%, stop rate 94.7% | n = 3,032 on 673 names: −0.47, 1.9%, stopped 98.0% |
| fillable entry, cells clearing | 0 | 0 |

Every cell fails the first leg (mean R > 0), so the noise band (≤ 1 of 122) is never reached — this is a null,
not a near-miss. One honesty note on the tail bar: it was set at 3.0% as "3× the incumbent's 1.01%", the 09-22
whole-population read; on THIS checkpoint's population the incumbent's own arms read 2.4% (trail) and 2.65%
(no exit), n = 1,171, so the bar is ~1.2× the incumbent here, not 3×. The verdict does not rest on it — every
cell fails on mean before the tail leg is reached. The average-loss leg is met by 83 of 122 cells at s20 (on all fires the trails keep the average loss to
−0.48 to −0.89R); the 39 that fail it are the hold arms (−0.95 to −1.07R on all fires, gap-charged) and
the thinner leader cells — losses can be limited, but not while also keeping the runners.

### All fires, session 20, stop = entry − 1.0×ADR$ — what each management arm did (n = 1,096–1,120 fires on 429–435 names)

| arm | mean R | kept ≥ 3R | avg loss | win rate | partial fired | stopped | trailed out | control mean / kept ≥3R (n = 367–378 non-fire sessions) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| M0 — the lane's own trail (incumbent stop, n = 1,171) | −0.32 | 2.4% | −0.87 (house) | 22% | — | 95% | — | — |
| M1 — the LIVE MAGNA53 stack, lane stop = live stop (era C: partial +1R, BE at partial) | −0.21 | 0.6% | −0.58 | 34% | 18% | 45%* | 55% | −0.09 / 0.8% |
| M1 — the live stack, ORB-R = stop distance (era C: partial +2R) | −0.22 | 1.2% | −0.58 | 30% | 8% | 43%* | 57% | −0.05 / 1.4% |
| partial +2R · BE at +1R · SMA10 trail | −0.18 | 1.2% | −0.48 | 25% | 7% | 25% | 75% | −0.06 / 1.6% |
| partial +2R · BE at +1R · SMA20 trail | −0.15 | 1.4% | −0.54 | 27% | 7% | 30% | 69% | **+0.18 / 3.4%** |
| partial +2R · BE at +1R · hold to s20 | −0.28 | 3.6% | −1.00 | 16% | 15% | 90% | — | −0.07 / 3.7% |
| partial +2R · BE after the partial · hold | −0.33 | 4.2% | −1.02 | 21% | 19% | 84% | — | −0.11 / 4.3% |
| partial +3R · BE at +2R · hold | −0.32 | 4.3% | −1.01 | 17% | 12% | 84% | — | −0.10 / 4.6% |
| partial +3R · BE after the partial · hold | −0.34 | 4.4% | −1.01 | 18% | 13% | 83% | — | −0.06 / 5.1% |

\* under the live ladder "stopped" is a hit of the RESTING stop on the low — the hard stop, or that stop after the ladder raised it to the trail line or to breakeven (`walk_arm` ratchets it after every session, see Validation); "trailed out" is a close below the line. The two sum to 100% with the 0.1% still open.

The pattern is the same as Block 5's: **every trail raises the mean and cuts the tail; every hold keeps the
tail and pays −1R on the rest.** No arm does both. The matched control — the same rule on a random non-fire
session of the same names, same window — beats the all-fires cells on mean in **40 of 40** cells at s20
(n = 342–378 control sessions) and **40 of 40** at s10 (n = 7,101–7,910), and is itself positive in 16 of
40 cells at s20. On leaders the control (n = 314–371 at s10) also beats the fires in 40 of 40; at s20 the
leader control is 20 sessions and the fires beat it in 9 of 40 — too thin to read. The fire session is a worse entry than a random session of the same stock, which is P2's finding
again, now under management.

### Leaders — the selection makes it worse, at every stop and under every arm

| leaders (≥ $5, above a rising 50-day, above the 20-day) | session 10 (n floor reachable) | session 20 |
|---|---|---|
| fires / names in the population | 143 / 52 (of 3,398 / 693; 143 unclassifiable) | 37 / 21 (of 1,214 / 463) |
| cells with a positive mean | 0 of 60 | 0 of 60 |
| cells with kept-≥3R ≥ 3% | 0 of 60 (best 2.8% = 3 of 106, `0.5×ADR / +2R BE +2R`) | 6 of 60, each 1 of 19 |
| mean R range across the 60 cells | −0.48 to −0.84 (n = 73–130) | −0.49 to −1.06 (n = 18–33) |
| M0 — the lane's own arm on leaders | n = 117 on 47 names: −0.84, kept ≥3R 0.9%, **stopped 99.2%** | n = 33: −0.91, 0%, stopped 97% |
| matched non-fire control on leaders | n = 314–371: −0.25 to −0.52, kept 1.1–5.7% | n = 20 (thin) |
| leader fires inside a +50% runner campaign | 7 of 143 (BUUU, RDIB) | — |
| leader fires that ever reached +3R open (recorded MFE) | 13 of 128 with a recorded excursion | — |

The leaders' median entry is $20.99 and their incumbent stop is 3.0% wide (median), against a population
whose median entry is $1.70: **the filter keeps the well-behaved stocks and drops the ones that run.** Of
the 120 runner campaigns, 18 had an EP-day close ≥ $5, and of the 143 leader fires only 7 (two names) sit inside
a runner campaign.
Whether a different "better" (his EP labels, the catalyst rubric, a theme) would do otherwise is not
measured here — this filter is the one he described on the marked charts, and on this lane it removes the
tail rather than the losers.

### Did we keep the winners? — the big runners, and what keeping them costs (his question)

Runners re-derived on the addendum's rule: **120 watched campaigns ran +50% within 15 sessions (18 with an
EP-day close ≥ $5); the lane fired in 102 of them — the addendum's 102 exactly** (the addendum's 142 / 24
counted 196 campaigns whose tickers are not in the Block 5 daily extract because the lane never fired on
them; the fired set is identical). Marked at session 20 or the last available close; recorded entry.

| arm (stop) | runner fires kept ≥ 3R | runner campaigns kept ≥ 3R | runner fires' mean R | every OTHER fire, same rows as M0: this arm vs M0 | net mean R, all fires |
|---|---:|---:|---:|---|---:|
| M0 — the lane's own trail (incumbent) | **15 of 267 (5.6%)** | 14 of 96 | +0.15 | −0.57 vs −0.57 (n = 2,927) | −0.51 |
| M0 — no exit, s20 (incumbent) | 17 of 267 (6.4%) | 14 of 96 | +1.02 | −0.90 vs −0.57 (n = 2,927) | −0.74 |
| M1 — the live stack (1.0×ADR) | 18 of 288 (6.3%) | 13 of 96 | +0.48 | −0.35 vs −0.55 (n = 2,649) | −0.25 |
| partial +2R · BE +1R · SMA10 trail (1.0×ADR) | 25 of 320 (7.8%) | 18 of 98 | +0.39 | −0.33 vs −0.55 (n = 2,719) | −0.24 |
| partial +2R · BE +1R · hold (1.0×ADR) | 68 of 320 (21%) | 26 of 98 | +1.75 | −0.60 vs −0.55 (n = 2,719) | −0.32 |
| partial +3R · BE +2R · hold (1.0×ADR) | **82 of 320 (26%)** | **32 of 98** | **+2.15** | −0.69 vs −0.55 (n = 2,719) | −0.35 |
| partial +3R · BE after · hold (0.5×ADR) | 52 of 267 (19%) | 28 of 93 | +2.50 | −0.79 vs −0.53 (n = 2,219) | −0.40 |

So yes: **a breakeven stop plus a held remainder keeps four to five times as many of the runners as the
lane's trail does (26% vs 5.6% of runner fires; 32 vs 14 campaigns) and the runner fires average +2.15R.**
And it costs: the runner fires are 320 of 3,483 (9.2%); every other fire under that arm loses −0.69R
against −0.55R under M0, and ten of them arrive for each runner. The arithmetic that would flip it is
plain — at +2.15R on runners and −0.69R on the rest, the lane nets positive only when runners are more
than 24% of fires (they are 9%) — and it is a selection number, not an exit number. The trails do the
opposite: they hold the non-runner cost to −0.33R and keep 8% of the runners. Nothing nets positive.

### M1 — the live MAGNA53 stack, per era, and what it actually does

Fires with 20 sessions elapsed are all **era C** (the retired +2R partial, breakeven only at the partial):
n = 1,096–1,104 on the 1.0×ADR stop, mean −0.21 to −0.22, kept ≥ 3R 0.6–1.2%. **Era D** (today's +8R / breakeven at
+3R) governs only the 09-08 → 09-11 fires at s10: n = 180–246, mean −0.51 to −0.71, kept ≥ 3R 0% — and
that is the second time half, which is worse for every arm (the incumbent M0 reads −0.62 there, n = 193),
so it is the tape, not the rule. Under either frame the live stack sits between the trails and the holds
on this lane and clears nothing. One mechanism fact surfaced by wiring it: **the live ladder ratchets the
broker's resting stop up to the trail line after every session, so a LOW touching yesterday's
max(SMA10, SMA20) stops the position out at that level** — `compute_settlement` (and this probe's M2..M19)
exit only on a close below the line. That is how "our EP" manages today; it is not what the lane records. And the one positive thread Block 5
found returns unchanged: under M1 on the 0.5×ADR stop, `ep_high_break` reads +0.31R with 6.6% kept ≥ 3R
(n = 76, recorded level entry) and **−0.15R with 2.8% on the fillable entry (n = 71)** — the level-priced head
start P2 measured, not the pattern.

### Validation — both checks pass, every difference named

- **(a) the walker vs the recorded settlement** (incumbent stop, house R, settled rows a $0 day-0 source can
  walk): no-exit arm **1,296 of 1,297**, trail arm **1,295 of 1,297** — P3's numbers; the misses are AIXI and
  NRSN, the two reverse-split rounding rows.
- **(b) the walker vs `walk_arm(harvest="trail_only")`** on identical synthetic day-0 bars (1.0×ADR stop,
  n = 1,033): **784 exact within 0.001R; 235 differ because the live ladder's resting stop ratchets to the
  trail line and is hit on the low (every one a stop booked above the hard stop); 11 differ by the day-0
  close that `walk_arm`'s SMA window excludes** (verified on TC 08-27: line 2.109 without it, 2.085 with it,
  close 2.09); 3 pending at a data hole. All 1,033 accounted for; the M1 path is wired as intended.
- `walk_arm`'s own abstains on M1 (a bar holding both the stop and the target or the breakeven trigger):
  12–58 per stop and frame at s20, named in `p6_summary.json`; M1's scored n is 2–7% below the grid arms', as declared.
- Degenerate stops: 5 fires on 1.0×ADR and 1 on 0.5×ADR had a stop below zero (an ADR$ wider than the
  price on a split-rescaled name) and 3 incumbent stops sat at/above the entry — killed and counted.

## What this does not answer

- **One month, one regime.** Fires 08-25 → 09-11 at s10 and 08-25 → 08-27 at s20; the s20 "second
  half" is a single fire date. Nothing here says what these rules do in a different tape.
- **The leader filter is thin by construction at s20 (37 fires, 21 names)** — a leader cell cannot
  clear the n floor there; s10 is the only checkpoint where it can, and s10 truncates a runner.
- **M1 is mostly the retired rule.** Fires before 09-06 are era C (+2R partial); today's live stack
  (era D) governs only the 09-08 → 09-11 fires at s10 and none at s20.
- **The ORB-R frame for M1 is declared, not the lane's.** The lane has no ORB; two mappings are run
  and both are conventions.
- **Day 0 for `walk_arm` is synthetic where minutes are missing**, and its own same-bar abstains
  shrink M1's scored population; M2..M19 resolve those pessimistically instead.

- **"Pick better" was tested as ONE rule.** The trend-leader filter is the shape of his marked charts; it is
  not his EP labels, the catalyst rubric or a theme filter, and its failure here says nothing about those.
  It does say the lane's runners are sub-$5 names (102 of 120 runner campaigns).
- **The control's stop is the ADR stop; the incumbent stop has no non-fire analogue** (stated, not
  substituted). At s20 the control is 342–378 sessions for all fires and 20 for leaders.
- **The runner read marks fires with under 20 sessions at their last close** (said in the table), and
  "ran" uses highs — a price nobody was sure to get.
- **Gap charging is one-sided.** A stop that gaps through is filled at the open; a partial or a trail exit
  is filled at the level or the close with no slippage. Real fills on $1.70 stocks would be worse on both.
- **Nothing here re-prices the EP alert itself** (day-1 entry, #482 / `545_entry_exit_program` §7). This is
  the delayed-entry watch lane only.

## THE FORK — determined by the bars, stated neutrally

The task allowed exactly one of three, chosen by the pass bars:

- **A candidate exists (he picks, under CHANGE_PROCESS)** — requires a cell clearing every leg. **None does:
  0 of 122 at s20, 0 of 122 at s10, 0 on the fillable entry; no cell has a positive mean under any
  selection, stop, arm, checkpoint or entry.** Off the table.
- **Selection helps but no management clears** — requires the leader cells to read better than the
  all-fires cells. **They read worse in every cell** (s10: −0.48 to −0.84R vs −0.20 to −0.47R; s20: −0.49 to
  −1.06R vs −0.07 to −0.50R; kept ≥ 3R at most 2.8% vs up to 4.4%; the lane's own arm stops 99.2% of leader
  fires, n = 117). Off the table.
- **No lift.** This is where the bars land. The winners are there and management keeps four to five times
  more of them than the lane's trail (26% vs 5.6% of runner fires, 32 vs 14 campaigns); they are 9% of the
  lane and the other 91% pay −0.60 to −0.70R each for holding, so nothing nets positive and the matched
  control beats the all-fires cells in 40 of 40 cells at both checkpoints.

**What would change the answer** (candidates for his ruling — nothing here is a change):

1. **A selection that finds runners at better than ~24% of fires** (they are 9%; the trend-leader filter
   moves them to 2%). That is a selection question under CHANGE_PROCESS; the $0 way to ask it is to score
   the runner campaigns against what the lane already records (his EP labels, catalyst grade, theme,
   price, ADR) before any new filter is proposed.
2. **Another month.** Era D (today's +8R / +3R stack) has 203–246 fires here, all in the weakest four fire
   dates; the s20 leader read is 37 fires.
3. **Not a management change on this lane.** Twenty arms, three stops, two selections, two checkpoints and
   two entry conventions — 488 cells in all — and the best mean any of them reached was −0.07R.

⚖ **THE LINE.** This day produced measured cells, a runner read and the fork above. It picked no stop, no
target, no selection rule; no toggle, table, PLAN.md line or strategy was changed; the lane keeps observing
exactly as it did yesterday.

## Files

- `scripts/probes/_327_block5/p6_leaders_mgmt.py` — the probe; its docstring is the pre-registration of
  record (committed before any result in `2868bdc2`).
- `p6_summary.json` (selection sizes, validation counts, every abstain reason, the control cells, the
  runner read, the verdict) and `p6_cells.tsv` (all 488 cells: both conventions × both checkpoints × both
  selections × 3 stops × 20 arms + M0, every leg, per pattern, per era, per half, the matched control
  beside each) — committed. `p6_events.csv` (324,380 per-row × stop × arm outcomes) — gitignored, regenerable.
- Block 5's extract and README: `scripts/probes/_327_block5/README.md`.
