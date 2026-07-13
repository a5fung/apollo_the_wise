# Composition red-team — giveback F1 × pivot stops (0031) × allocator/ladder (0022) on the LIVE stack

**Fable, 2026-07-12 (adversarial design pass — DESIGN ONLY, THE LINE intact: every fix below is a
PROPOSAL routed to an operator decision + CHANGE_PROCESS; nothing here changes code or trade state.)**

> **VERIFICATION (Opus, against code — 2026-07-12).** Each RED checked against primary source before
> reaching the operator:
> - **RED-1 — CONFIRMED (strongest).** `giveback_shadow.py` validates on `l=c` bars (touch≡close-below);
>   live enforcement is a resting Alpaca stop via `live_tracker.py:573` → `update_stop` (intraday-touch).
>   The intraday-wick behavior is genuinely un-validated, in the tail-clip direction. Gates the 8/06 flip.
> - **RED-2 — DOWNGRADED to YELLOW.** The failure-path NULL is a *deliberate fail-safe*
>   (`order_manager.py` ~998-1005: fires only if the retry ALSO fails, NULLs `stop_order_id` so Path C
>   orphan-check detects+remediates), with a retry + backstop — NOT an accidental clobber-to-naked as
>   framed. Legit residual: no advisory lock / no in-function never-lower guard on `update_stop` —
>   defense-in-depth hardening before 0031 adds a 2nd stop authority, not a currently-broken hole.
> - **RED-3 — CONFIRMED (mechanism), latent.** Composite multiplier applies after cap-derived shares
>   (`entry_pipeline.py:418`) with no upper re-cap → a >1.0 allocator step sizes through the 20%/1%
>   safeguards. Not exploitable today (all multipliers ≤1.0); real the moment 0022's allocator flips.
>   (The "3 writers, no ownership" sub-claim was not code-verified — the write-site grep failed; treat
>   as unconfirmed pending a check.)

**Scope:** the UNKNOWN interactions when the three signed trade-state designs compose live in the
planned sequence — giveback F1 (~8/06) → ADR 0031 pivot structure-stops (~8/09) → ADR 0022
allocator/ladder (post-8/4) — layered on ADR 0017 (management judge), ADR 0020 §5 (regime_matrix),
ADR 0029 (stop ownership), and the real stop path (`exit_logic.py` / `live_tracker.py` /
`order_manager.py` / `trade_stream.py`).

**Not re-reported** (already on the record): block3_t4 register R8 (max(arm_stop, giveback_floor)
precedence + serialized flips) and R4 (shared settlement driver); premortem #450 R4 (intraday
portfolio blindness) and R5 (LLM authority creep); the #433 WULF false-naked retry class as a known
incident. This pass goes past those.

Verification basis: code read at HEAD (a1b738a) — `exit_logic.apply_daily_exit_step` (step-4/4b
max() composition; `pivot_swing`/`character_ma` shadow modes), `live_tracker.py:424-810`
(EOD trail job, 3:45 partials, 9:35 refresh, `_check_safeguards`), `order_manager.py:789-1085`
(`set_stop_order_id`, `update_stop`), `:1249-` (`execute_partial_exit` + advisory lock), `:1984-`
(`execute_full_exit`), `:3472-` (`track_open_position_extremes`), `entry_pipeline.py:406-439`
(composite sizing), `giveback_shadow.py`, `pivot_stop_shadow.py`, `pivot_analysis.py`.

---

## 🔴 RED-1 — Enforcement-surface conflation: every close-below design silently becomes an intraday-touch resting stop when wired live

**Class:** design gap + evidence-vs-implementation mismatch. **Hits: giveback F1 (8/06) AND the pivot flip (8/09).**

The live EOD job pushes the ladder's **decision line** to the broker as a **resting stop-market**:
`live_tracker.py:573` — `if step.effective_stop > current_stop + 0.01: update_stop(...)`, where
`effective_stop` is the step-4 max() that will include the giveback floor (step 4b) and, under the
pivot modes, the P1/P2 line as `active_sma`. So the natural wiring for BOTH flips (pass the new
params/mode to the live callers) makes the floor/line a live intraday stop.

But the entire evidence base is **close-below** semantics:
- ADR 0023 A3 + the sweep + `giveback_shadow.py` measure the floor via the step-5
  `bar_close < effective_stop` branch, on `l=c` bars ("the giveback lock surfaces as an
  `sma_trail_stop` close" — exit_logic docstring). The +$8,075 F1 evidence and the running shadow
  marginal are close-below numbers.
- ADR 0031 §3 defines P2 as "**exit on close below** home_MA × (1 − undercut_p80)"; the P1 shadow
  even records "close-below semantics, not intraday touch — conservative for the arm"
  (`exit_logic.py:258-264`) — for the SHADOW. The LIVE semantics are stated nowhere.

**Concrete failing state (giveback):** entry $10.00, peak close $11.00 → armed (+10% > +6%), floor
= 10 + 0.60×1.00 = $10.60. EOD job raises the broker stop to $10.60. Next day the tape wicks $10.55
intraday and closes $11.40. LIVE (as-wired): stopped out at $10.60 — the runner is clipped.
MEASURED (sweep + shadow): the close never printed below the floor → position survives and the
evidence credits the floor with keeping the runner. The rule that was validated and the rule that
will execute are different rules; the flip's realized deltas will NOT match the shadow's promised
deltas, in the tail-clipping direction (the §5 "poison test" direction).

**For P2 it is worse than a delta:** the character line's entire purpose is wick tolerance (the
NBIS-class habitual undercutter). A resting stop AT the tolerance line re-introduces the exact
shakeout the design exists to prevent — the design self-defeats when wired through line 573.

Note: this seam is pre-existing — today's SMA trail is also a close-below ladder whose value gets
parked as a touch stop (and the ladder's trail line is not even monotone across days, while the
broker stop is ratcheted — the live exit is already tighter than the modeled ladder). The 18%
capture baseline absorbed that silently; the flips are the moment it stops being absorbable,
because from 8/06 an evidence table is the justification for a real-money rule.

**Proposed fix (operator ruling required BEFORE the 8/06 F1 flip; one fork, two honest options):**
- **(a) Decision-line enforcement (matches the evidence):** the giveback floor / pivot line
  participates in the close-check (step 5) and in exit decisions only; it is EXCLUDED from the
  broker-stop raise at `live_tracker.py:573` (mechanical hard stop / BE remain the resting stop).
  Costs: an intraday collapse through the floor exits EOD/next-open, not at the floor.
- **(b) Resting-stop enforcement (tighter, deliberate):** the floor/line rests at the broker — but
  then the F1/pivot evidence MUST be re-derived under touch semantics (re-run the sweep + shadows
  with real lows, `l=low`) before either flip; the current tables do not support option (b).
Whichever is picked, record it in ADR 0023 §A3 and ADR 0031 §3/§6 in the flip commit (SSoT rule),
and the same ruling binds the 0017 L2 TRAIL_TIGHTEN executor (it must know which surface it is
tightening).

---

## 🔴 RED-2 — "No two concurrent live stop changes, ever" is enforced by cron spacing, not by code; `update_stop` sits entirely outside the advisory-lock regime

**Class:** code-vs-design mismatch (the invariant is stated in R8/0031 §0; nothing enforces it at
runtime). **Hits: all three flips — each adds a stop-mover.**

Verified facts:
1. `order_manager.update_stop` (`:853-1085`) takes **no** `_trade_advisory_lock`, has **no
   never-lower guard** (it places whatever price it is given — the "a live stop never moves down"
   invariant lives only in each caller's `>` check), and its cancel→place sequence has a real open
   window (3s retry sleep; today's `stop_update_failed` qty-settlement transient on the 9:35
   refresh is this window firing).
2. Its double-failure path **unconditionally NULLs** `stop_order_id`
   (`set_stop_order_id(trade_id, None, reason="stop_update_failed")` at `:1008` — no
   `expected_prior` CAS, though the helper supports it) — it will clobber a pointer a concurrent
   writer just set to a LIVE stop.
3. The 15-min reconciler's `_ensure_stop_coverage` defends via **try-lock** (`:2824`) — which only
   protects against lock-HOLDING writers (partials/finalizers). It cannot see an `update_stop` in
   flight; during update_stop's cancel-gap it reads "uncovered" and places a remediation stop.
4. Today serialization is real but accidental: the only two `update_stop` callers
   (`live_tracker.py:574` EOD, `:800` 9:35 refresh) are cron jobs scheduled hours apart, each a
   sequential loop.
5. The 0017 L2 TRAIL_TIGHTEN executor is specced to use **`replace_order`** (§5) — a THIRD stop
   mutation mechanism (Alpaca replace ≠ cancel+place), trigger-driven at any market minute (T2
   rides the 5-min extremes poll).

**Concrete failing state (post-flips):** 9:34:58 the L2 judge fires TRAIL_TIGHTEN →
`replace_order` retires stop X, creates stop Y, writes pointer Y. 9:35:00 `morning_stop_refresh`
(which loaded the trade row seconds earlier) checks stale pointer X → `get_order(X)` → replaced/
dead → calls `update_stop`: cancel X fails (`cancel_ok=False` — **it proceeds anyway**, by
design), places stop Z → insufficient-qty (Y holds the shares) → 3s retry → still held → both
attempts fail → **NULLs the pointer to the judge's live stop Y** → `naked_position_detected` +
🚨 NAKED Telegram (false — Y is live) → stop-ACK watchdog sees NULL → fallback placement →
insufficient-qty again → CRITICAL escalation. Net: DB pointer wrong, two escalating false alarms,
and if Y meanwhile fills, the WS handler's pointer-match (`stop_order_id = $1`) misses. The system
fails NOISY rather than naked — but the invariant every design cites is demonstrably not held, and
the WULF 7/6 + today's transient show the window is real at today's LOW writer count.

**Proposed fix (operator decision; natural home = ADR 0029-D1, which should land these as its
concrete content BEFORE any second stop authority goes live):**
1. `update_stop` acquires the #151 advisory lock for its full cancel→place→persist sequence (the
   partial path already proves the pattern on prod).
2. A **never-lower guard inside `update_stop`** (reject `new_stop < current stop_price` on longs
   absent an explicit reviewed flag) — makes the monotonic invariant mechanical at the single
   chokepoint instead of N caller conventions.
3. The failure-path NULL uses `expected_prior` CAS (the helper already supports it — one-arg change).
4. **One mutation mechanism:** the L2 executor routes through the same locked chokepoint (or
   `update_stop` migrates to replace-order internally) — not a parallel path. R8's "no two
   concurrent live stop changes" becomes a property of code, not of the crontab.

---

## 🔴 RED-3 — Three signed designs write one column: `mi_strategies.position_size_multiplier`; and the composed multiplier has no ceiling and bypasses the caps it multiplies

**Class:** cross-ADR design conflict + a code seam. **Hits: the allocator bind (post-8/4) and the
0017 conviction-sizing promotion.**

The collision (doc-verified, no composition rule exists anywhere):
- ADR 0022 §2: allocator budgets "become the per-strategy `position_size_multiplier` + cap set" —
  bound by **operator signature**.
- ADR 0017 §4: conviction sizing = "grade-judge tier → `position_size_multiplier` (plumbing
  exists, #65)" — a per-ENTRY conviction concept pointed at a per-STRATEGY column.
- ADR 0001 (older, still open): dynamic tuning proposes writing the same column
  (`∈ [0.25, 2.0]`).

**Failing state:** 8/4+ the operator signs an allocator budget (say 0.75×) → it binds as the
multiplier. Conviction sizing later promotes and writes its tier factor (say 1.25× game_changer)
to the same row → the **operator-signed budget is silently gone** (or, implemented per-entry, it
cannot live in that column at all and someone improvises at build time). This directly violates
0022's own contract ("operator signs → budgets bind") without any single ADR being wrong.

**The code seam that makes the high extreme dangerous:** `entry_pipeline.py:413-430` applies
`composite_multiplier = strategy_multiplier × drawdown_multiplier` **AFTER** `spec_builder` — i.e.
after the 20%-of-capital position cap and the 1%-risk budget are computed
(`order_manager.py:100-135`). The composite is **unbounded above**. Today it never exceeds 1.0 in
practice, so the seam is invisible. The allocator's step band explicitly allows **2.0×**; the
regime_matrix (0020 §5) multiplies at the same point; a conviction factor >1 is unspecified. A 2.0
composite = a 40%-of-equity position and 2% risk/trade on the $4.9k account — 5 ORB fills in one
window = ~10% correlated open risk, sized THROUGH the caps rather than by them, with the
daily-loss gate (realized-only, next-entry-evaluated) and the drawdown breaker (16:12 snapshot)
both structurally behind it. This is 0029-D3's overrun argument (which capped entry overshoot at
2%) recurring at 100× the magnitude, one layer up. **Low extreme is handled** (composite → 0
shares → loud `setup:size_too_small` skip, `entry_pipeline.py:419-425`) but see Y7.

**Proposed fix (operator decision, must precede the allocator bind):**
1. **Declare ownership:** `position_size_multiplier` belongs to the ALLOCATOR (strategy-scoped,
   signature-bound). Conviction sizing gets its OWN per-entry factor with a signed bounded range,
   composed explicitly in the entry-pipeline 5b step and audit-rowed (the
   `per_strategy_sizing_applied` event already prints the factorization — extend it).
2. **A signed composite ceiling:** rec composite ≤ 1.0 until an explicit sizing-up decision; at
   minimum, re-apply the 20% position cap + risk re-check POST-multiplier so no multiplier stack
   can exceed what the safeguards were calibrated against.
3. ADR 0001 is subsumed or explicitly re-scoped under the allocator (two tuners of one knob is the
   same bug at slower speed). Record the line in 0022's L3 card notes.

---

## 🟡 YELLOW findings

**Y1 — A loosening mode cannot compose with the broker-stop ratchet: P2 is inert-or-violating on
the open book.** `live_tracker.py:573` only raises. Any position whose resting stop already
ratcheted above its character line makes P2 undeliverable (the promised undercut tolerance cannot
take effect without LOWERING a live stop — forbidden). Failing state: pre-flip position, SMA-era
stop $50, character line $48 → flip to P2 → next wick to $49.50 stops it out; the readout says
"P2 live" and the attribution is garbage. *Ruling needed at the pivot fork:* flip scope = **new
fills only** (rec), and state explicitly that a loosening mode never lowers an existing resting
stop — deliberate, not accidental. (Design fact worth writing down once: **max() composition is
total and safe for tighteners only**; every future loosening design hits this same wall.)

**Y2 — Giveback live arming basis ≠ evidence basis.** ADR 0023 A3's live-wiring note names
`mi_live_trades.highest_price_seen` — intraday minute-bar highs, wick-inclusive
(`order_manager.py:3543`). The sweep + shadow arm on **peak CLOSE** (`max(running_closes)`).
Wick-armed floors arm earlier and sit higher than anything measured → extra clipping stacked on
RED-1. *Rec:* live wiring arms on peak close (byte-consistent with the evidence); one line in the
F1 flip spec.

**Y3 — The two shadows that will jointly justify the composed stop measure under different bar
semantics.** `giveback_shadow` settles on `l=c` bars (marginal-cancel logic, valid WITHIN the
shadow); `pivot_stop_shadow` settles on real lows (`low_price`). Cross-shadow comparisons ("P1
beats the giveback floor") are apples/oranges, and the eventual composed rule
(`max(arm_stop, giveback_floor)`) has NO joint evidence run. *Rec:* pre-declare no cross-shadow
ranking; before composing both live, one joint replay through the #445 driver with both hooks on
(cheap — the driver takes both param sets already).

**Y4 — Auto-demotion (0022) latency + soft holes around open positions.** The mechanical core is
clean (see G2), but: (i) `ladder_watchdog` is nightly and rides the post-EOD audit job — a
`harmful_auto_action` at 10:00 keeps L2 authority all session; if the host job dies, demotion
silently stops (fail-open) and no freshness monitor is specced for the watchdog itself.
(ii) Demotion of a STRATEGY does not revoke the 0017 judge's L2 authority over that strategy's
still-open positions — 0017 demotes its lane on harmful action, 0022 demotes the strategy; neither
document claims the cross-product. (iii) `attempt_day1_reentry` checks the kill switch + /pause
(R2 fix) but NOT strategy phase — latent while `R3_DAY1_REENTRY_ENABLED=false`, a re-entry-enabled
future would let a just-demoted strategy re-enter live same-day. (iv) A signed allocator
multiplier survives demotion→re-promotion (stale budget rebinds silently; only the PENDING
proposal is zeroed). *Rec for the L2 card:* demotion also freezes judge auto-actions on that
strategy's positions (advisory-only), resets the multiplier to the rung default pending a fresh
proposal, and the watchdog gets the backup-check-style staleness Telegram.

**Y5 — Regime-unknown sizes at FULL (fail-open vs the matrix's intent).** `regime_record` is
fetched best-effort and entries proceed with None (`live_tracker.py:298-302`); 0020 B4's NULL=1.0
rule means a missing/unreadable regime row → 1.0× in exactly the risk-off states the matrix exists
to damp. *Rec at J3 signing:* the matrix carries an explicit `unknown` key (operator-set; rec 0.6)
and a regime-read failure emits an audit row.

**Y6 — One bad giveback/pivot param bricks the whole book's EOD management (loud, but
whole-book).** `giveback_floor()` and the `trail_mode` guard fail LOUD (ValueError) inside
`apply_daily_exit_step`; `update_open_positions_live` has no per-trade try — a misconfigured live
param or one malformed per-ticker profile aborts the loop for ALL positions (no trail advance, no
trail closes; resting stops keep the mechanical floor; `notify_job_failure` fires). Also the one
SILENT case in the family: `character_undercut` has no range validation — a corrupt profile with
undercut ≥ 1 yields a line ≤ 0 → that name's trail silently OFF (effective_stop falls back to
hard stop/BE). *Rec for the flip cards:* per-position try/except in the live loop + params
validated at boot/deploy (not first-use) + an undercut ∈ [0, 0.5) guard.

**Y7 — The composed LOW extreme is a de-facto strategy halt by rounding.** Allocator floor 0.25×
× REDUCE 0.5× × risk-off 0.3 ≈ 0.04× → on $4.9k every entry rounds to 0 shares → per-entry
`size_too_small` skips forever. Surfaced per-entry (not silent) but nobody has DECIDED that
"multiplier stack < ~0.2 on this account size = the strategy is off." *Rec:* state it in the
allocator digest (proposal math trace prints the projected shares at current equity; a 0-share
projection flags "this budget = OFF at current account size" for the operator to sign eyes-open).

---

## 🟢 GREEN — verified clean (with the reason)

**G1 — The stop-precedence state space is total for tighteners.** Enumerated: hard stop, BE floor,
SMA/EMA trail, giveback floor (armed ⇒ floor > entry by construction, `giveback_floor()`
validated fail-loud), P1 pivot (ratchet-up-only verified in `annotate_pivot_stops`), judge
TRAIL_TIGHTEN (bounded ≥ current stop by spec). All compose through one `max()` (step 4/4b) +
caller-side raise-only broker updates; no reachable state lowers a resting stop. The only
unresolved direction is LOOSENING — which is RED-1/Y1, not a max() defect.

**G2 — Auto-demotion does not mechanically orphan open positions.** Verified: every management
surface (EOD trail job, 3:45 partials, 9:35 refresh, sync/watchdogs, trade_stream finalizers) keys
on `mi_live_trades` rows + `account_mode`, never `strategy.phase`; broker stops rest GTC
regardless. A demoted strategy's open live position keeps its stop, trail, partials, and close
paths. (Residual soft holes are Y4, not orphaning.)

**G3 — Judge-vs-mechanical authority is total; no un-adjudicated tie found at L0–L2.** The
mechanical layer executes regardless of a HOLD (floor-not-ceiling holds in both docs and code
paths); TRAIL_TIGHTEN is bounded; the judge-partial vs 3:45-mechanical-partial race is bounded by
the advisory lock + the under-lock pending-exit-order dedup (verified in `execute_partial_exit`)
— worst case is a second partial after the first FILLED and before its finalize commits
(seconds), which reduces exposure and cannot oversell (pending-exit qty subtraction in
`update_stop`/sizing). L3 FORCE_EXIT vs a same-moment stop fill resolves at the broker
(close-remaining after a fill is a no-op).

**G4 — The shadows' own failure modes are fail-safe.** Both are read-only counterfactuals over
CLOSED trades, disjoint tables, NOT-EXISTS dedup, per-row try/except with error audit rows
(pivot), gated reviews wired against silent 0-rows, job failures Telegram via `notify_job_failure`.
Pivot ABSTAIN → name stays on the global trail, verified first-class in `pivot_analysis` +
`pivot_stop_shadow` (`abstained`/`abstain_reason` columns).

**G5 — Allocator outage direction is safe.** A dead proposals job leaves last-SIGNED budgets in
force (no drift toward risk); a demotion zeroes the pending proposal per §2. Residual: budget
staleness is unmonitored (folded into Y4(iv)).

---

## Verdict

The composed stack is **not yet safe to flip in the planned sequence as-specified — but it is one
operator sitting away from safe**, because none of the three REDs is a flaw in the signed
mechanisms themselves: the precedence math is clean (G1), demotion doesn't orphan positions (G2),
and the authority ladder is total (G3). What's missing is three rulings that no ADR currently
owns: **(1)** declare the enforcement surface for close-below designs — decision-line vs
resting-stop — before the 8/06 giveback flip, or the flip ships different semantics than its
evidence measured (RED-1, also binds the 8/09 pivot fork and Y1/Y2); **(2)** make the
"no-two-concurrent-stop-changes" invariant mechanical (lock + never-lower guard + CAS in
`update_stop`, one mutation path) as the concrete content of ADR 0029-D1, landed before any second
live stop authority (RED-2); **(3)** assign ownership of `position_size_multiplier` and sign a
composite sizing ceiling before the allocator binds budgets (RED-3). If those three land in order,
the planned sequence giveback → pivot → allocator is sound; if any flip proceeds without its
ruling, the failure is not hypothetical — it is the WULF/#433 class with real dollars (RED-2), or
a real-money rule justified by evidence measured under a different rule (RED-1).
