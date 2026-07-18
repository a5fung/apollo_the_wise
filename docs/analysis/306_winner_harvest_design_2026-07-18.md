# #306 — v1.1-W3 winner-harvest tune: DESIGN (2026-07-18)

**⛔ THE LINE — this is SELL / EXIT DISCIPLINE. This document is DESIGN ONLY.** Nothing here
changes live behavior. Every proposed change requires, in order: **operator sign-off on the
specific parameterization → CHANGE_PROCESS entry in `docs/setups/` → the named N≥10
backtest/validation below → #151 integration harness / paper exercise → deploy.** Where a
direction has ALREADY been operator-ruled (Axis A, 7/9), this doc restates the ruling and its
gate — it does not re-decide or extend it.

**Inputs:** STEP-0 (`docs/analysis/w3_winner_harvest_step0_2026-07-04.md`, N=10 winners = 18%
MFE capture) · STEP-2 sweep (`docs/analysis/306_step2_sweep_2026-07-08.md`, 28-trade replay,
lock-attributable +$8,075) · premortem R3 (`docs/analysis/premortem_450_2026-07-11.md`) ·
ADR 0023 (exit-stop mechanics) · ADR 0031 (pivot structure-stops) · live code as of `aa13607`.

---

## 1. Current exit/management behavior (file:line-anchored)

The daily management spine (all ET, mon-fri):

| Time | Job | What it does | Anchor |
|---|---|---|---|
| 9:35 | `morning_stop_refresh` | re-places expired DAY stops as GTC for every Day 2+ position (protection continuity, no level change) | `broker/live_tracker.py:789-833`; registered `scheduler.py:5153` |
| 15:45 | `run_partial_exits` | the Day 3-5 partial-profit decision, mid-session so the stop-replace settles same-day (#361) | `broker/live_tracker.py:656-783`; registered `scheduler.py:5740` |
| 16:45 | `update_open_positions_live` | SMA trail + stop ladder on the settled close (`skip_partial_decision=True` — never double-partials) | `broker/live_tracker.py:444-654` (calls at :518-519, :570-572); registered `scheduler.py:5767` |
| 16:55 | `_time_stop_scan_job` | #91 time-stop candidates (9M Day 2 only) — **alert-only**, operator confirms via `/timestop` | `scheduler.py:1188-1318`; registered `scheduler.py:5199` |
| 17:38 | `_giveback_shadow_job` + pivot-stop shadow | log-only counterfactuals on newly-closed live trades (Axis A / Axis B evidence accrual) | `scheduler.py:4913-4921`, `pivot_stop_shadow.py:82-127` |

All decision logic is the ONE pure ladder — `broker/exit_logic.apply_daily_exit_step`
(`exit_logic.py:137-389`). The rules the live callers actually exercise today:

- **Hard stop** = ORB low (MAGNA53 bracket) / prior-day low (9M Day 2) — the resting Alpaca
  stop is the real intraday mechanism; the ladder's step-1 close is backtest-pure semantics
  (`exit_logic.py:224-246`; live passes `skip_hard_stop_close=True`, `live_tracker.py:746-761`).
- **Partial**: fires once, on `hold_days >= 3` AND (`hold_days <= 4` requires `close > entry`,
  `hold_days >= 5` unconditional) — `exit_logic.py:300-304`. **`hold_days` is CALENDAR days**
  (`exit_logic.py:217`), not trading days.
- **Partial SIZE = ⅓ of remaining** — live callers pass `scale_fraction=None`, so the sizing is
  the hardcoded `int(remaining) // 3` (`exit_logic.py:306-311`; the 0.33-0.50 `scale_fraction`
  hook exists but **no live caller passes it**, `exit_logic.py:177-181`).
- **Breakeven arms ONLY after the partial** (`exit_logic.py:330-331` → `:337-338`).
- **Trail = max(SMA10, SMA20) of post-entry closes**, exit on **close below** it
  (`exit_logic.py:289-293`, close branch `:350-373`). Live callers use `trail_mode` default
  `"sma"`; `ema_10_20` / `sma_10_20_handoff` / `pivot_swing` / `character_ma` are all
  opt-in with **zero live callers**. **Critical: SMA10 needs 10 post-entry closes → the trail
  is `None` for roughly the first 9 trading days** (`exit_logic.py:277-278`).
- **Effective stop = max(hard_stop, active_sma, breakeven-if-armed[, giveback floor])** —
  `exit_logic.py:333-348`. The `giveback_floor` peak-lock hook (`exit_logic.py:78-134`) is
  DEFAULT-OFF; **live exit callers pass zero giveback kwargs** (verified 7/9, advisor).
- **#91 time-stop (current)**: `signal_type='9m_day2'` only · ≥5 **trading** days since fill ·
  `highest_price_seen` excursion < +3% · alert-only, `/timestop` submits OPG
  (`scheduler.py:1192-1203`, gate at `:1235`).

## 2. WHERE the $ leaks — the specific mechanism

**The number:** N=10 partial-taken winners kept $5,942 of $32,775 peak = **18% aggregate MFE
capture** (STEP-0). At the v2.0 tier-one bar (>50%) the same trades keep ~$16.4k — a **~$10.5k
management leak**, larger than the entry leak (11 day-0 stop-outs ≈ −$6.1k, the W2/#414 lane).

**The mechanism is a structural hole in the ladder's early-trade coverage, not a mis-tuned
parameter:**

1. **Days ~1-9 have NO trail.** `active_sma` is `None` until 10 post-entry closes exist
   (`exit_logic.py:277-278`), so between fill and ~day 10 the only protections are the
   ORB-low/prior-low hard stop (well below entry) and breakeven — which arms only after a
   day-3-5 partial. A spike that peaks on day 1-4 and fades has **nothing above the hard stop**
   watching it.
2. **Nothing anywhere references the PEAK.** Both stop inputs (hard stop, breakeven) are
   entry-anchored; the trail is a lagging mean. A +11.7% run (SMCI) writes
   `highest_price_seen` but no exit rule reads it — the trade round-trips to a **−$639 close**
   through a peak that was never locked. PURR (+13.4% → $3) and CRSR (gave back 85% of +52.5%)
   are the same shape.
3. **The partial is late, small, and conditionally blocked.** Day 3-4 requires `close > entry`
   — a fast fader takes NO partial until day 5 (then unconditionally, possibly underwater,
   arming a breakeven stop that is instantly above market → same-close trail exit at a loss:
   the SMCI anatomy). And ⅓ leaves ⅔ of the position exposed to holes 1-2.

**Sweep attribution (STEP-2, 28-trade replay):** the peak-lock (Axis A, arm +6% / floor 60%)
is the load-bearing fix — **+$8,075 lock-attributable** (cohort capture 23% → 52%), the
marginal concentrated exactly in the round-trippers (SMCI +$1.2k, CRSR +$3.2k, RCAT +$1.5k),
losers untouched (control Δ≈0), clean runners GOOGL/PURR untouched. The global-trail choice
(Axis B: sma vs ema vs handoff) made **zero difference** on this cohort; partial size (Axis C)
is second-order (+$612 standalone; +$1,180 stacked on the lock).

## 3. The tune — four axes, calibrated

### Axis A — peak-lock giveback floor, arm +6% / floor 60% (RULED 7/9 — restated, not re-decided)

The operator picked this direction 7/9 and chose **shadow validation before any flip**;
`giveback_shadow.py` is deployed and logging the counterfactual on every newly-closed live
MAGNA53 trade (`mi_giveback_shadow`, 17:38 ET). This doc's only additions:

- **It is the load-bearing capture fix** — the sweep attributes ~all of the recoverable leak to
  it. Axes B/C/D below are sequenced BEHIND it, not alongside.
- **Live semantics constraint (7/12 composition red-team ruling): the floor is a CLOSE-BELOW
  DECISION LINE evaluated in the EOD ladder — NOT a resting broker stop.** The sweep's +$8,075
  was computed on close-below semantics; wiring it as a resting intraday stop would be a
  different (unvalidated) rule. Implementation at flip time = pass the giveback kwargs into the
  16:45 job's existing `apply_daily_exit_step` call — the `max()` composition and close branch
  already exist (`exit_logic.py:339-348`).
- **Flip gate (unchanged):** `giveback_shadow_review` predicate ≥10 rows (earliest 8/06) →
  shadow confirms the offline finding forward → CHANGE_PROCESS + SSoT + #151 + operator
  sign-off + the `harvest_rule_flipped` audit + standing `harvest_rule_effectiveness` review.

### Axis B — trail-by-character (inherit ADR 0031; the global-MA sub-axis is DEAD)

The sweep killed the "which global MA" question: sma / ema_10_20 / handoff were
indistinguishable on the cohort. The live trail-by-character bet is **ADR 0031's per-ticker
character arms**, already built and accruing shadow evidence (`pivot_stop_shadow.py`,
`mi_pivot_stop_shadow`, gated review `pivot_stop_shadow_review`). **"Character" is defined
exactly as ADR 0031 §2 — do not invent a second measure:**

- Per ticker, over min(trend-window, 120 trading days) of daily bars, detect
  **pullback episodes** against each MA in {SMA10, EMA21, SMA20, SMA50}: episode begins on
  `low ≤ MA×1.02` after ≥5 closes above; RESPECTED if close reclaims the pre-episode 20d swing
  high, BROKEN on 3 closes below (or 20d stale).
- **home_MA** = shortest MA with respect_rate ≥ ⅔ over ≥3 episodes; **undercut_p80** = 80th-pct
  undercut depth on respected episodes. Exit line = `home_MA × (1 − undercut_p80)`
  (arm P2, `exit_logic.py:265-275`); arm P1 = ratcheting confirmed swing-low
  (`exit_logic.py:258-264`). **ABSTAIN** (no qualifying MA / <3 episodes) → stay on the global
  trail. Computed by `pivot_analysis.character_profile` (`pivot_analysis.py:56`).
- **Decision rule** (ADR 0031 §5): per-arm vs baseline at ≥10 non-abstained shadow rows —
  capture% + mean/median exit R + the **tail-clip test** (any arm that exits a still-running
  winner early loses regardless of mean).
- **Hard sequencing (ADR 0031 §0/§6, premortem attribution-hygiene): the character-trail live
  fork may not even reach a sitting until giveback F1 is adopted-or-killed. Never two
  concurrent live stop changes.**

### Axis C — partial size ⅓ → ½ (propose; bundle the decision with the Axis A flip sitting)

- **Evidence:** sweep Axis C — 0.5 fraction = +$612 standalone over the ⅓ baseline; **+$1,180
  incremental stacked on the lock** (best cell $8,693 vs lock-at-⅓ $7,513). Direction-setting
  at N=11, second-order vs the lock. ½ is inside the sourced 0.33-0.50 range
  (`docs/setups/htf.md`; hook already live-safe: `scale_fraction`, `exit_logic.py:312-317`).
- **Rationale beyond the sweep:** with the lock guarding the remainder, a bigger partial
  banks more at the day-3-5 strength window without re-exposing the tail (the lock, not the
  partial, is what protects the runner).
- **Proposal:** present ⅓ vs ½ as ONE fork at the same STEP-3b sitting that flips the lock —
  a single CHANGE_PROCESS entry either way. If the operator wants them separated for
  attribution, flip the lock first, hold ½ for the next review cycle.
- **Not proposed:** changing the day-3-5 timing or the `close > entry` day-3-4 condition —
  no sweep cell tested timing; any timing change needs its own replay first (§5).

### Axis D — #91 time-stop refinement (alert-only stays; scope + inputs widen)

Current scan (`scheduler.py:1188-1318`) is 9M-Day-2-only by design (5/23: "MAGNA53 has
different hold dynamics — BW at day 11 still working"). Refinements proposed:

1. **D1 — MAGNA53 dead-money alert tier**: extend the scan with a second, LOOSER discriminator
   for `signal_type='magna53'`: **≥10 trading days since fill · peak excursion < +3% ·
   `partial_taken = false`**. Same alert-only surface, same `/timestop` operator confirm
   (ADR 0004 `operator_only` class — **never auto-exit**). Rationale: at a 5-slot cap
   (`MAX_CONCURRENT_LIVE_POSITIONS`), a never-ran name is paying slot opportunity cost the
   ladder cannot see (the trail only exists from ~day 10, and a sub-entry meanderer never
   partials before day 5 / never trails until the SMA rises to it). The ≥10-day/no-partial
   gate is deliberately wider than BW's day-11-working shape — BW had `partial_taken=true`
   and a real excursion, so it would NOT flag.
2. **D2 — trading-day alignment (candidate, evidence-gated)**: the partial window uses
   CALENDAR `hold_days` (`exit_logic.py:217`) while #91 correctly counts TRADING days
   (`scheduler.py:1215-1219`). A Friday fill's "day 3" is Monday; a Wednesday fill's is
   Saturday (→ partial effectively Monday, day 5, unconditional). This asymmetry randomizes
   which trades get the `close>entry` day-3-4 test. Fix is a one-line semantic change with
   real behavior shift → **replay-gated** (§5), filed as a candidate only.
3. **D3 — mgmt-judge input (shadow)**: feed `time_stop_eligible` (hold trading-days + peak
   excursion) into the position-mgmt judge inputs — the deferred part-2 note at
   `mgmt_judge.py:85` already names #91 as the source. Shadow/readout only, no authority.

### capture_pct — target and failure trigger

The KPI is live (STEP-1: `system_review._aggregate_mfe_capture`, Sunday digest, cumulative
cohort). Proposed target ladder, measured on the ROLLING post-flip cohort (new partial-taken
winners only, not the frozen 18% history):

- **Interim target: ≥35% aggregate capture at N≥10 post-lock winners.** (The sweep's
  retrospective 52% is in-sample on the cohort that motivated the rule; forward degradation is
  expected — 35% ≈ doubling today's realized capture, well short of claiming the bar.)
- **v2.0 tier-one bar: >50%** (roadmap PART II) — assessed at N≥20.
- **Failure trigger:** if rolling capture at N≥10 is **<35%**, or the lock's realized marginal
  in `harvest_rule_effectiveness` turns ≤0, the rule goes BACK to a sitting (revert is a named
  outcome, per CHANGE_PROCESS reversion discipline).

## 4. Validation plan — BEFORE any flip (all N≥10, all read-only)

| Axis | Validation | N / gate | Status |
|---|---|---|---|
| A lock +6%/60% | offline: STEP-2 sweep (done) · forward: `giveback_shadow_review` — shadow marginal confirms sign + order of magnitude of +$8,075 | ≥10 shadow rows (earliest 8/06) | shadow LIVE, accruing |
| A live semantics | #151 paper exercise of the decision-line wiring (16:45 job path) before deploy | 1 full paper cycle | at flip time |
| B character trail | `pivot_stop_shadow_review`: per-arm capture/R + tail-clip test, abstention rate | ≥10 non-abstained rows, +21d | shadow LIVE, accruing; **sequenced behind A** |
| C partial ½ | re-run `scripts/_306_harvest_sweep.py` on the GROWN closed cohort at sitting time (script + bars cached/reproducible) — confirm the ½ cell still ranks ≥ ⅓ with the lock on | cohort ≥15 harvest names preferred; ≥11 minimum | script exists |
| D1 MAGNA53 time-stop | offline replay over `mi_live_trades` closed history: count would-flag instances, per-flag PnL-after-flag-date (saved vs foregone $) + slot-days freed; BW-class must NOT flag | ≥10 flagged instances before any alert ships | to run (read-only SQL + bars) |
| D2 trading-day alignment | replay the closed cohort with trading-day `hold_days`: diff which partials move + capture delta | full closed cohort | to run before filing as a change |
| capture_pct target | nothing to validate — it is the measurement; the weekly KPI already prints it | — | LIVE |

## 5. Operator decision surface (nothing moves without these signatures)

1. **A (when `giveback_shadow_review` surfaces, ~8/06):** flip the +6%/60% lock live as a
   close-below decision line — or extend the shadow — or kill. *(The 7/9 ruling covers the
   direction; the flip itself is a fresh signature.)*
2. **C (same sitting, rec):** partial ⅓ vs ½ — one fork, bundled or explicitly deferred for
   attribution.
3. **D1:** approve the MAGNA53 dead-money alert tier AFTER its replay table is on the desk
   (alert-only; `/timestop` remains the only exit path).
4. **D2:** calendar→trading-day `hold_days` — only reaches a sitting with its replay diff.
5. **B (later, hard-sequenced):** character-trail arm choice at the `pivot_stop_shadow_review`
   sitting — **only after A is adopted-or-killed** (ADR 0031 §0 gate).
6. **capture_pct target ladder** (≥35% @ N≥10 interim / >50% @ N≥20 bar / <35% revert-trigger)
   — sign as the standing success criterion for the whole tune.

**Every flip above:** CHANGE_PROCESS entry + SSoT update in the same commit
(`docs/setups/safeguards.md` management section / `magna53_ep.md` / `ninem.md` as applicable) +
#151 harness + operator sign-off. **SELL DISCIPLINE = THE LINE.** This document changes nothing.
