# ADR 0029 — Entry-bracket mechanics (#414): stop ownership + the gap-through entry fork

**Date**: 2026-07-11
**Status**: **DESIGN — awaiting operator sign-off** (Fable block-1 extension). REAL-MONEY entry
path (MAGNA53 live) — nothing here ships without the C1 backtest table + operator sign-off +
CHANGE_PROCESS; the SSoT (`docs/setups/magna53_ep.md` entry-mechanics section +
`docs/setups/safeguards.md` if the cap moves) updates in the flip commit.
**Authors**: Fable (operator-triggered, 2026-07-11)
**Relates**: the CLOSED `alpaca_stop_trigger_reliability` review (its evidence base), #180
would-have-filled classifier (the standing measurement), #182 (paper-under-fills-vs-live),
#433 (the false-naked alarm fix on this conflict), #184b/ADR-0008 (R1 stop-pointer ingest — the
healing leg), ADR 0023 (exit ladder — the settlement engine for the backtest).

## 1. Context — one incident, two different problems

**Problem 1 (architecture, deterministic):** entry day, ~9:31-9:34 fill → the OTO child stop is
live and holds the shares. At 9:35 `morning_stop_refresh` runs with **no same-day exclusion**
(`live_tracker.py:772-813`: `status='filled' AND remaining_shares>0`, no alert_date filter). When
the `stop_order_id` pointer is NULL/stale (OTO leg capture missed), `update_stop` places a second
stop → broker rejects insufficient-qty (shares held by the OTO leg) → the retry dance
(`order_manager.py:921-954`) usually wins on attempt 2 — **works but fragile**, and it was the
source of the false-naked alarm class #433 had to paper over. WULF 7/6 is the live exhibit.

**Problem 2 (methodology, statistical):** the stop-limit entry (trigger=orb_high,
limit=`max(orb_high×1.005, orb_high+$0.02)`, `order_manager.py:42-58`) misses fills. The closed
review's own evidence splits this class in two — and the split is load-bearing:
- **`would_have_filled`** (trigger hit, a later print ≤ limit): on paper this failed because the
  IEX feed never printed the trigger (AVAV 5/28, LYG #214) — **on live/SIP money these fill**
  (#182-confirmed). NOT a reason to change live mechanics; it is a paper-telemetry artifact.
- **`gap_through`** (trigger hit, price never came back to the limit): a REAL live miss — the
  0.5%/$0.02 buffer can't catch a fast tape. This is the only cohort the #414 fork is about.

## 2. Decision

### D1 — explicit stop-ownership contract (ships first; independent of D2)

The ownership is currently implicit and its seam is the bug. Make it explicit, three legs:
1. **Entry day = the OTO child owns the stop, by construction.** `morning_stop_refresh` gains a
   same-day exclusion: skip trades with `alert_date = today` (their protection is the OTO leg;
   the refresh exists to replace *overnight-expired DAY stops*, which cannot apply to a
   same-morning fill). This removes the 9:35 collision **at the root** — the #433 retry
   machinery STAYS as belt-and-suspenders, expected to go quiet.
2. **A NULL/stale pointer is a MIRROR defect, not a refresh trigger**: healing belongs to the
   existing remediation stack — the 3-source capture at fill, `sync_positions` Path-C naked
   remediation, and (once enabled) #184b R1 ingest repointing within 15 min. The refresh job
   never "discovers" stops; it only replaces known-expired ones.
3. **Day 2+ = refresh/`update_stop` owns the stop** (unchanged): 9:35 replaces the expired DAY
   stop with GTC; all later trail/partial updates go through `update_stop`.
**Day-1 re-entry carve-in (advisor 7/11):** `attempt_day1_reentry` places a FRESH OTO bracket on
the same `alert_date` after a stop-out — the same-day exclusion covers it by the same logic (its
protection is its own OTO child, placed atomically), but the rationale must be stated on the
re-entry case explicitly and C2's tests pin it: a re-entered same-day trade is (i) skipped by
the 9:35 refresh, (ii) still healed by sync_positions/R1-ingest if its pointer capture missed.
Risk framing: D1 *narrows* a live job (it does strictly less, on a cohort whose protection
already exists). Tests pin: same-day skip (fresh entry AND day-1 re-entry) · day-2 refresh
unchanged · a genuinely-naked same-day trade still caught by sync_positions (NOT silently
skipped forever).

### D2 — the gap-through entry fork: measured first, decided by R (not fill-rate)

Three candidate mechanics; **the ADR pre-commits the measurement and the bar, NOT the winner**:
- **(a) Wider limit offset** — {1.0%, 1.5%} vs today's 0.5%: fills more gap-throughs at a worse,
  *bounded* price; risk-per-share widens by the same bound.
- **(b) Stop-MARKET + chase cap** — market on trigger, entry ≈ next print; a **chase cap**
  auto-cancels if the projected fill exceeds `orb_high × (1 + cap)`, cap ∈ {0.5%, 1%, 2%}.
- **(c) Status quo** — gap-throughs stay missed; their forgone R is the measured cost of doing
  nothing.
**Fill-rate is vanity; the question is realized R at the degraded entry.** A gap-through is by
definition the fastest tape — chasing it buys the worst fills of the day, and the #290 lesson
(fat-tail-carried means over −1R medians) applies squarely. Hence the bar in C1.

### D3 — the chase cap is ALSO the sizing-integrity bound (design fact, either mechanic)

Shares are computed at `orb_high` (`risk = shares × (orb_high − orb_low)`, VIX-scaled budget,
20% position cap — `order_manager.py:100-135`). Any fill above `orb_high` overruns the planned
risk by `shares × overshoot` with no re-size possible mid-fill. So the cap value is not a
preference — it bounds the risk overrun: cap ≤ 1% keeps the overrun ≤ ~1% of position value
(≪ the risk budget's own VIX-band granularity). **Rule: whatever D2 picks, the effective entry
bound (limit offset or chase cap) is ALSO recorded as the max sizing overrun in
`safeguards.md`.** A wider-than-2% anything fails this test by construction — 2% is the design
ceiling for any candidate.

## 3. C1 — the backtest (the decision artifact)

`scripts/probes/_414_entry_mechanics_backtest.py` (read-only, prod): cohort = cancelled entries
with EOD reclassification (`orb_cancellation_reclassified` audit, the authoritative SIP-complete
labels; 90d+ history — the join is already specced in the #414 brief). Then:
1. **Report the split first**: would_have_filled (paper artifact — counted, excluded from
   mechanics decisions, with the #182 citation) vs gap_through vs clean_miss. If gap_through
   N < 10 → **park**: no live-mechanics change on thin evidence; re-arm the measurement as a
   gated review (predicate: gap_through count ≥10) and stop. (The honest possible outcome is
   "the real problem is too rare to justify touching the live entry path.")
2. For each gap_through: simulate (a) at 1.0%/1.5% limits — filled iff a SIP bar's low ≤ the
   wider limit after trigger, entry = that limit; (b) stop-market — entry = first print after
   trigger, capped at each chase value (cap-exceeded = no entry); (c) = 0R (missed).
   **Fidelity label (load-bearing):** minute-bar "first print after trigger" UNDERSTATES market
   slippage in exactly the fast tape gap-throughs select for (intra-bar the true fill can be
   several prints worse) — mechanic (b)'s results are an **optimistic bound** (the #290
   upper-bound honesty rule); a (b) verdict that only marginally clears the bar does NOT ship.
   For cohort inputs, read the submitted limit from `mi_live_orders.limit_price` (the wire
   truth) — `mi_live_trades.entry_price` on a cancelled row is the *planned* value, not a fill.
3. **Settle every simulated fill through the real exit ladder** — stop at orb_low, forward
   daily bars via `apply_daily_exit_step` (the giveback-shadow replay shape) → realized R at
   the degraded entry, per mechanic per parameter.
4. **Ship bar (distribution-honest, the 0026-F1 shape):** a mechanic ships only if its
   gap-through cohort shows **median R > 0 AND win-rate ≥ 35% AND mean R > 0 at N ≥ 10** —
   chasing must *earn*, not just fill — AND it beats (c)'s 0R baseline after the D3 overrun is
   charged. Report the do-nothing cost (Σ forgone positive R) alongside, so "keep (c)" is a
   priced decision, not a default.
5. Sensitivity: the full parameter grid (2 limits × 3 caps), plateau rule — a knife-edge winner
   parks the decision (thresholds-are-outputs).

## 4. Rollout + built-in triggers

1. **C2 (D1 refresh exclusion)** ships on sign-off, independent of D2 — it is the fragility
   fix and needs no backtest (deterministic semantics). Verify-live = next same-day fill
   produces ZERO insufficient-qty retries (the #433 audit goes quiet on entry days).
2. **C1 runs → the table + name lists go to the operator** → D2 is decided ON the table
   (including legitimately "keep (c)"). Any mechanic flip = CHANGE_PROCESS + SSoT + the #151
   paper exercise (a real paper entry through the new mechanic) before live.
3. **Standing measurement:** #180's reclassifier keeps emitting; a gated review
   `entry_mechanics_effectiveness` (≥10 post-flip entries via the new mechanic, or +60d)
   compares realized entry slippage + R vs the C1 prediction — the revert trigger.
4. PLAN: #414 carries this ADR; #433's "messaging-verify" item gains the D1 note (the alarm
   class it papers over is expected to stop occurring on entry days).

## 5. Cards

- **C1 — the backtest probe** (cohort split + simulations + settlement + the ship-bar verdict
  + sensitivity grid; read-only).
- **C2 — D1 same-day refresh exclusion** (live_tracker morning_stop_refresh + 5 tests:
  same-day-skip · day2-unchanged · NULL-pointer-same-day-not-touched · sync_positions-still-
  remediates · refresh-count-telemetry).
- **C3 — the D2 mechanic** (gated on C1 + sign-off; whichever wins: the limit constant change
  OR the stop-market submit path + chase-cap check in `prepare_orb_order`/`submit_entry` + the
  #151 paper exercise + SSoT/safeguards amendments).
- **C4 — `entry_mechanics_effectiveness` gated review** (the post-flip revert trigger).

## 6. Operator forks

- **F1 — D2 winner:** deliberately NOT pre-decided — C1's table decides; the rec is the BAR
  (§3.4), not the mechanic. If nothing clears the bar, (c) status-quo wins and the cost is on
  record.
- **F2 — D1 timing:** rec = ship C2 with the next execution deploy (it removes a live fragility
  and risks strictly less than today's behavior). Alternative: hold for the D2 flip — couples
  an independent fix to a slower decision for no benefit.
- **F3 — the chase-cap/overrun ceiling:** rec = 2% hard design ceiling (D3). Anything wider is
  a sizing-integrity change, which is a different (bigger) conversation.
