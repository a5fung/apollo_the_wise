"""Block 5 / P6 — leaders + EP-style management on the delayed-entry lane. $0, read-only.

THE QUESTION (operator, 2026-09-26, after Block 5 found no full-exit cell pays): "Pick better plus
like our EP, we take partials and adjust stops, so there's various things in play" — and earlier the
same day: "any EP related trades are low winrate by default, what we want is always to catch big
winners while limiting losses". Block 5's grid used FULL exits only and admitted every EP name. This
probe adds (1) a leader-only SELECTION and (2) EP-style MANAGEMENT (partial, stop to breakeven,
remainder trailed) and asks, tail first, whether any cell keeps the winners while limiting losses.
Nothing is deployed; nothing here picks a stop, a target or a selection rule (THE LINE).

═══════════════════════════════ PRE-REGISTRATION ═══════════════════════════════
Everything in this block was written BEFORE the first cell was computed and is never changed after.
Population COUNTS (fires, names, sessions elapsed) were read to size the draws; no outcome was.

1. SELECTION — "leader" at the fire, from bars STRICTLY BEFORE the fire date, on `mi_daily_closes`'
   (adjusted) scale: prior close >= $5 · prior close > its 50-day SMA · that 50-day SMA > the 50-day
   SMA ending 10 sessions earlier (rising) · prior close > its 20-day SMA. Fewer than 60 prior closes
   → unclassifiable (counted, NOT a leader). Every result is reported for (a) ALL fires and (b)
   LEADERS, side by side, with the filter's size (fires, names) per checkpoint and per stop.
   Sized before any result: at s10 the filter keeps 143 of 3,398 fires (52 of 693 names); at s20,
   37 of 1,214 fires (21 of 463 names).

2. MANAGEMENT ARMS (the declared family):
   M0        the lane's incumbent settlement AS RECORDED — its own trail arm (`r_trail_sK`,
             stop → max(SMA10, SMA20) close-below, s20 time exit) on the incumbent stop; the
             no-exit arm (`r_none_sK`) is reported beside it. M0 is house-convention (a stop is
             exactly −1.00R) and is read on settled rows only.
   M1        the LIVE MAGNA53 EP exit stack as of each fire date, walked with the repo's own tools:
             `rule_eras.exit_rules_as_of(fire_date, "magna53")` → `stack_walk_inputs` →
             `walk_arm(harvest="live_ladder", trail_mode="sma")` — never re-implemented. The lane
             has no ORB, so the ORB-R frame is DECLARED, two ways, each its own draw:
               M1_orb2  ORB-R = half the arm's stop distance (the live stop IS entry − 2×ORB-R, so
                        the lane's stop plays the live stop): era D (fire >= 09-06) partial 1/3 at
                        +4R(stop units), breakeven armed at +1.5R; era C (fire < 09-06) partial at
                        +1R, breakeven only at the partial.
               M1_orb1  ORB-R = the whole stop distance: era D partial at +8R, breakeven at +3R;
                        era C partial at +2R, breakeven at the partial.
             ⚠ Most fires with 20 sessions elapsed are ERA C (08-25..08-27) — the RETIRED +2R rule;
             M1's n per era is reported beside every M1 cell so an era-C read is never taken for
             today's rule. Day 0 for `walk_arm` (it has no daily path): real 1-min bars from
             `intraday_day0_raw.csv` when they exist (fill bar = the last 1-min bar of the fire's
             5-min bucket for a minute fire; the first bar whose high reaches the level for a
             level-priced fire); otherwise a SYNTHETIC two-bar day — a fill point at the entry,
             then ONE excursion bar (the production `day0_pseudo_bars` shape) carrying the cached
             post-fire low/high for a minute fire, the whole fire-day range for a daily-grade fire,
             or {high = entry, low = day low} for a minute fire with no source (the day-0 high is
             never credited; a day low at/below the stop with no source ABSTAINS, as in P3). The
             excursion bar's open is None so the gap-through charge cannot fire on a level entry.
             `walk_arm`'s own abstains (same-bar stop+target, stop+breakeven) are counted per stop
             and named — M1's scored population is expected to be smaller than M2..Mk's.
             prior_closes = the 40 calendar days before the fire (the live tracker's window);
             walk_arm's trail starts at session 1 (the fire-day close is not in it — a known
             difference from compute_settlement, which counts day 0 as the first close).
   M2..M19   a small grid, walked by this probe's own daily-grain walker (validated below):
               partial   1/3 of the position at +2R or +3R (R = the cell's OWN stop distance),
                         sold AT the level on the first bar whose high reaches it;
               breakeven the stop moves to the entry when the high reaches +1R, or +2R, or right
                         after the partial ("part") — the raise takes effect from the NEXT bar
                         (an end-of-session order change; a raise can never be hit on the bar
                         that armed it);
               remainder whatever is open is trailed on the 10-day SMA close, the 20-day SMA close
                         (the line includes the session's own close, needs N closes, checked from
                         day 0 as compute_settlement does), or HELD to session 20 (no trail).
             2 × 3 × 3 = 18 arms.
   Stops (3) the incumbent stop · entry − 0.5×ADR$ · entry − 1.0×ADR$ (ADR$ = the real
             `compute_ep_adr_dollar`, Block 5's unit). A stop at/above the entry kills the fire.
   Within a bar: stop (low) first, then partial/breakeven (high), then trail (close) — the
   pessimistic order Block 5 used. A stop is filled at the stop level, EXCEPT a session that OPENS
   below the resting stop fills at the open (walk_arm's gap-through rule) — every walked arm is read
   GAP-CHARGED, which is what makes "losses limited" testable; M0 as recorded is not (P3 measured
   the difference at 0.03R on the incumbent cell). A breakeven stop is a resting order at the entry,
   filled on the low (or the open when it gaps below).
   DRAWS: per checkpoint = 2 selections × (M0 + 3 stops × 20 arms) = 122; two checkpoints = 244
   (recorded entry). Noise band scaled from the block's 1–3 of 294: ≤1 of 122 per checkpoint is
   noise; ≥10 is a family. The FILLABLE entry convention (entry = max(level, fire-day open) for
   level-priced fires) is run on every cell and reported BESIDE the recorded one — a robustness
   read, not extra draws.

3. CHECKPOINTS — session 20 is the bar (open positions marked at the s20 close); population =
   fires with >= 20 sessions elapsed by 2026-09-25 (fire_date <= 08-27: 1,214 fires). Because the
   leader filter at s20 (37 fires / 21 names) is below the n floor BY CONSTRUCTION, the same six-leg
   bar is applied at session 10 beside it (3,398 fires; leaders 143 / 52) — declared now, not after a
   result. Width floor: rows whose stop is >= 0.5% wide in the cell's own units (Block 5's rule);
   unfloored n reported.

4. PASS BAR (tail first) — a cell is a CANDIDATE only if ALL hold: mean R > 0 · kept >= 3R rate
   >= 3.0% · average loss (mean R over losers, gap-charged) no worse than −1.0R · mean R > 0 after
   dropping the single best NAME by summed R · n >= 100 fires over >= 40 names · positive mean in
   both time halves (s20: split at fire_date 08-27 — H2 is ONE fire date, said plainly; s10: split at
   09-08, Block 5's line — H2 is four fire dates). The COUNT of clearing cells is judged against the
   draws before any cell is named.

5. CONTROL — the same selection and management on the matched NON-FIRE sessions from P2: every
   non-fire session inside the 20-session window of each campaign where the lane fired, entered at
   that session's close (no day 0), leader flag evaluated at that session, stops 0.5×/1.0×ADR$ only
   (the incumbent stop has no non-fire analogue — stated, not substituted). Fire minus control on
   mean R and kept-3R rate per cell, so a positive cell cannot be regime drift.

6. BIG RUNNERS — re-derived (the addendum's script was not committed): every watched (ticker, EP
   date) with EP date <= 09-04 and >= 10 later sessions of bars; base = the EP-day close on the daily
   table's scale; "ran" = the highest high within 15 sessions >= +50% over base (the addendum
   counted 142, 24 at >= $5 — reproduced or the difference stated). For each arm and stop: of the
   fires in runner campaigns, how many KEEP >= 3R (fires and campaigns) versus M0, and the same
   arm's mean R on every NON-runner fire versus M0's on the same fires — the "did we keep the
   winners, and what did it cost" read. Runner fires with fewer than 20 sessions elapsed are marked
   at their last available close (said in the table).

7. VALIDATION before any cell is read: (a) this probe's walker with no partial, no breakeven and
   remainder ∈ {hold, max(SMA10,SMA20)} must reproduce the recorded `realized_r` / `realized_r_trail`
   (house-convention R) on settled rows a $0 day-0 source can walk — P3's cross-check (a); (b) the
   same walker (trail = max10_20, day-0 close excluded from the trail) against
   `walk_arm(harvest="trail_only")` on identical synthetic bars, R within 0.001 — the wiring check
   for M1's path. Both counts go in the doc.
═════════════════════════════════════════════════════════════════════════════════

Outputs: p6_summary.json + p6_cells.tsv (committed); p6_events.csv (per row × stop × arm, gitignored
with the other bulk files). Regenerate: python3 p6_leaders_mgmt.py (needs the extract_p0.sh /
extract_p3.sh pulls in this folder).
"""
