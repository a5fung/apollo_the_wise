# ADR 0023 — Exit & stop mechanics: winner-harvest sweep, single stop authority, gap classes

**2026-07-07 · #438 (Fable design block) · Status: ACTIVE — operator-signed 2026-07-07 (§7)**
Covers #306 STEP-2 (the sweep design) and #414 (stop authority + gap/no-trigger). **THE LINE:
this ADR measures and designs; NOTHING here changes live behavior. Every live change routes
through its named fork in §6 → CHANGE_PROCESS + #151 exercise + operator sign-off.**

Inputs: `w3_winner_harvest_step0_2026-07-04.md` (N=10 winners, 18% capture, ~$10.5k leak vs the
>50% bar) · the WULF 7/6 false-naked incident (#433 fixed the UX half) · the SYRE −4.57R 6/24
gap (verified: stop-market FILLED at 82.54 vs stop 95 at the open — a gap FILL, not a
no-trigger) · `exit_logic.apply_daily_exit_step` (pure; `trail_mode` + `scale_fraction` hooks
already exist from #396) · `live_tracker.morning_stop_refresh` + `order_manager.update_stop`.

---

## PART A — #306 STEP-2: the winner-harvest axis sweep (evidence lane, zero trade-state)

### A1. Harness
New `scripts/_306_harvest_sweep.py` (probe-class, read-only): replays each closed cohort trade
through `apply_daily_exit_step` bar-by-bar from its REAL fill (entry_price, fill date, shares,
original ORB stop from `mi_live_trades`), sweeping the axes. NOT the backtester engine (that
simulates entries; we replay known fills). Daily bars: Polygon grouped daily `adjusted=true`;
**fingerprint every run** (symbol·feed·adjustment·range — `eval_alpaca_skills` discipline);
cache to `scripts/eval_data/306_bars_<fingerprint>.csv`.

Cohort: the 25 closed trades 5/01–7/02 (10 partial-taken winners = the harvest set; the 11
same-day −1R losers re-run as an interaction control — they should be ~unaffected).

### A2. The axes (grid deliberately COARSE — rank, don't fine-tune)
| Axis | Values | Hook | Motivating cases |
|---|---|---|---|
| A. Giveback peak-lock | arm ∈ {+6%, +8%, +10%, +2R} × floor ∈ {40%, 50%, 60%} of peak gain | **NEW (A3)** | SMCI +11.7%→−$639 · PURR +13.4%→$3 |
| B. Trail | `sma` (current max(10,20)) vs `ema_10_20` (#396) vs `sma_10_20_handoff` (NEW: SMA10 until partial_taken, then SMA20) | `trail_mode` exists; handoff = 1 new mode | CRSR gave back 85% of +52.5% |
| C. Partial size | None (⅓ current) vs 0.40 vs 0.50 | `scale_fraction` exists | IBM 8-of-26 class |

### A3. The ONE new hook — peak-lock floor in `apply_daily_exit_step` (Card 1)
Pure, opt-in, default-off (no caller change → zero live effect):
- New params: `giveback_arm_gain: float|None = None` (fraction, e.g. 0.08; or `giveback_arm_r`
  with risk/share) and `giveback_floor_frac: float|None = None`.
- State: `peak_close = max(running_closes)` (derivable — no schema change; live wiring later
  would use the existing `mi_live_trades.highest_price_seen`).
- Mechanics: when armed (`peak_close ≥ entry × (1+arm)`) the floor
  `entry + floor_frac × (peak_close − entry)` feeds the EXISTING `effective_stop = max(...)`
  composition (step 4). One new max() input; the close-below-effective-stop branch is unchanged.
- Tests: arm-boundary, floor math, never lowers effective_stop, default-off byte-identical.

### A4. Outputs + overfit guardrails
Per cell: cohort `capture_pct`, total kept $, per-trade table; the A×B interaction grid; the
loser-cohort control. Guardrails: (1) coarse grids only, RANK not tune (N=10 is
direction-setting); (2) reject a best-cell whose neighbors collapse (spike = artifact — require
a plateau); (3) the pick must be mechanism-justified against its named cases, not just
table-best; (4) report GOOGL/BW-class cost — a lock that clips the best runner is a fail; (5)
fingerprint + committed CSV so the run reproduces. Deliverable:
`docs/analysis/306_step2_sweep_2026-07-08.md` + decision sheet.

**STEP-3 (fork F1)**: operator picks a parameterization (or none). Exit discipline = THE LINE.

### A5. Standing effectiveness review (operator requirement at signature, 7/7)
The harvest rule is re-checked REGULARLY for as long as it is live — never set-and-forget:
- The flip (STEP-3 execution) MUST emit a `harvest_rule_flipped` audit event — the review
  predicate keys off it.
- `data_gated_reviews.yaml :: harvest_rule_effectiveness` (added 7/7) surfaces in the Sunday
  digest at ≥10 post-flip partial-taken closes (or quarterly, whichever first): post-flip
  capture_pct vs the 18% baseline vs the sweep's predicted cell, plus the clipped-runner cost
  check. Keep / retune / revert is an operator decision via CHANGE_PROCESS. The entry RE-ARMS
  after every review (recurring, per the quarterly rule-review discipline).
- Ambient monitor between reviews: the weekly-review MFE-capture KPI (STEP-1, live since 7/5).

## PART B — #414(i): single stop authority (the WULF class)

### B1. Current state = THREE placers, no owner
(1) OTO bracket stop leg at entry · (2) `morning_stop_refresh` 9:35 — **its query has NO Day-2+
filter despite the label**: `status='filled' AND remaining_shares>0` picks up a Day-1 fill from
9:31 four minutes later; its only guard is the DB `stop_order_id` pointer being readable+active
· (3) `update_stop` (trail/partial; cancel-then-place + #433 retry). WULF 7/6: the pointer
check missed the OTO leg → refresh placed a 2nd stop → insufficient-qty → false alarms.

### B2. The authority model (fork F2 — rec below)
**Birth: the OTO leg IS the stop. Management: the first `update_stop` takes ownership (it
already cancels the prior order). Refresh: demoted from PLACER to RECONCILER.**
Concretely (Card 4, trade-state — gated):
1. `morning_stop_refresh` places ONLY after a **broker-confirmed absence**: reuse the #128
   `_covered_by_broker` sweep (any live sell-side stop covering remaining qty — order-form
   agnostic, catches OTO legs the DB pointer missed). Covered + pointer wrong → repair the
   pointer (same no-overwrite predicate as #184b R1 — one mechanism, shared card surface),
   emit `stop_refresh_reconciled`. Covered + pointer right → skip (today's behavior). NOT
   covered → place (today's behavior, now guaranteed-single).
2. `update_stop` unchanged (cancel-then-place + retry is correct; the cancel-gap window is
   already alarmed by #433's fixed messaging).
3. DoD/tests: Day-1 fresh OTO leg → refresh does NOT double-place; NULL pointer + live leg →
   repair not place; dead stop → places exactly one; #151 paper exercise before deploy.

## PART C — #414(ii): the gap classes (honest split — they are TWO classes)

- **C1 — ENTRY stop-limit no-trigger** (the original #414): fast open blows through the buy
  stop-limit's offset → no fill / missed winner. Fix candidates: widen limit offset vs
  stop-market entry + chase cap (abort if fill would exceed trigger×(1+cap)). **Evidence first
  (Card 6):** N≥10 via the #180 SIP would-have-filled replay; entry mechanics = methodology →
  fork F3 with the backtested proposal. No pre-decision here.
- **C2 — EXIT overnight gap-through** (SYRE −4.57R, DELL −1.43R): the stop-market FILLED — the
  instrument is already correct (a stop-limit would have sat unfilled while it kept falling).
  This is market gap risk, not order mechanics. Actions: (a) accept — it's inherent to
  overnight holds, sizing already caps intended risk at 1R; (b) **Card 5 (telemetry, ships
  ungated): 9:00 ET premarket gap-risk alert** — any open position with premarket quote below
  its stop Telegrams a heads-up before the open (read-only); (c) any overnight de-risk RULE
  (ATR/event-based trimming) = sell-discipline methodology → **parked as fork F5**, evidence
  gate = the monthly sweep counting gap-through events + cost (today N=2, −$1.9k total).

## §5. Card decomposition (pure execution — Opus/Sonnet)
| Card | Lane | What | Gate |
|---|---|---|---|
| 1 | evidence | peak-lock hook in `exit_logic.py` (A3) + tests, default-off | none (dark) |
| 2 | evidence | `_306_harvest_sweep.py` + fingerprinted bars + grid run | none (read-only) |
| 3 | evidence | sweep results doc + STEP-3 decision sheet | → F1 sitting |
| 4 | trade-state | refresh-as-reconciler (B2) + tests + #151 exercise | **F2 sign-off** |
| 5 | telemetry | 9:00 premarket gap-risk alert | none (alert-only) |
| 6 | evidence | C1 entry no-trigger backtest (#180 replay) → proposal | → F3 sitting |
Sequence: Cards 1+2+5 Wed 7/8 → Card 3 Wed EOD → F1+F2 operator sitting Thu 7/9 → Card 4 (post-F2)
Thu/Fri → Card 6 Fri 7/10. Nothing deploys to live trade-state without its fork signed.

## §6. Fork list (operator) + recommendations
- **F1 (STEP-3)**: pick the harvest parameterization after Card 3 — or none. *Rec: decide at the
  Thu sitting off the ranked table; peak-lock (axis A) is the mechanism the round-trippers name.*
- **F2 (authority)**: adopt B2 (refresh → reconciler). *Rec: YES — it removes the double-placer
  class at the root; behavior when no stop exists is unchanged.* CHANGE_PROCESS + #151.
- **F3 (C1 entry mechanics)**: offset-widen vs stop-market+cap — decide on Card 6's backtest.
- **F5 (C2 overnight de-risk rule)**: parked; revisit when the monthly sweep shows the class
  costs more than N=2/−$1.9k. *Rec: park.*

## §7. Sign-off
- [x] ADR accepted (design + fork list): **operator, 2026-07-07** — with the standing
  requirement that the harvest rule be reviewed regularly for continued effectiveness (§A5:
  the recurring `harvest_rule_effectiveness` data-gated review + the weekly capture_pct KPI).
