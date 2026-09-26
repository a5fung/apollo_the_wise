# #327 — leaders plus EP-style management on the delayed-entry lane: does any cell keep the winners while limiting losses?

**2026-09-26 (Saturday build slot, after Block 5 and its addendum).** RESULT PENDING — this file was
committed with its Method section fixed BEFORE any cell was computed (the probe's docstring carries the
same pre-registration, verbatim). The result section is filled in by the next commit and never edits
this one.

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

## RESULT — pending (filled by the next commit)

## What this does not answer — known before the run (the result adds its own)

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

## THE FORK — pending
