# ADR 0026 — Consolidation-family unification: flag_continuation → Confirm entry (b) + the TRIGGERED gate fix

**Date**: 2026-07-11
**Status**: **DESIGN — awaiting operator sign-off** (Fable weekend block 1; #354 + #146). Amends
ADR 0013 (the signed consolidation model) and `docs/setups/flag_continuation.md`; both SSoTs update
in the same commit as any code flip (CHANGE_PROCESS). Detection-criterion changes here are
**shadow-measurable pre-flip** — the backtests below are the N≥10 gates.
**Authors**: Fable (operator-triggered weekend block, 2026-07-11)
**Relates**: ADR 0013 (three entry modes, Phase 2-4), ADR 0005 (intraday flag-break + the #145
idempotency guard), docs/setups/htf.md (the 90/40 runup successor), operator 6/22 directive
("flag_continuation = one and the same as the consolidation play").

## 1. Context — one family, three entries, one stale standalone

ADR 0013 signed ONE consolidation family with three entry modes: **Anticipate** (in-coil, live),
**Confirm** (breakout, `confirm_signal_at` left un-wired 6/29), **U&R** (undercut-reclaim, never
wired). `flag_continuation` still exists as a standalone `mi_strategies` row carrying pre-0013
params the family has since superseded (runup 50%/60d → HTF 90/40 for HTF-class; family runup
15%/10d; pivot-walk anchor; ratio tightness gates vs RMV/ATR). Its state machine
(`flag_detector.py` WATCH→TIGHTENING→COILED→TRIGGERED→INVALIDATED) is the shared substrate all
three modes read — it stays; the *strategy identity* merges.

Two defects block the merge from being a rename:
- **Undercut invalidates** (`flag_detector.py:801-804`, close < base_low_close → INVALIDATED) —
  operator-vetoed semantics ("undercut is OK"); ADR 0013 §Phase-4 routes it to **WATCH_UR**.
- **The COILED prerequisite starves TRIGGERED** (`flag_detector.py:952`): breakout+volume alone
  can't trigger from TIGHTENING. Evidence: ADR 0005 §5 backward-check — TRIGGERED N=5 avg
  **−2.66%, 0% WR** vs TIGHTENING N=104 **+1.73%, 28.8% WR**; the 2026-05-28 cohort shows
  **9/92 (~10%)** names broke their range while stuck in TIGHTENING (ADTN/IREN/TVTX/UCTT/WULF/
  ARCB/QS/PAYS/PLPC) — promoted only by the intraday guard's workaround, never by the machine.

## 2. Decision — three coupled changes, one state machine

### D1 (#354) — retire `flag_continuation` as a strategy; its breakout logic becomes **Confirm (b)**

- `mi_strategies`: retire the `flag_continuation` row (phase → `deprecated`, the 9M-day2 pattern);
  the family's single consolidation strategy owns all three entry modes, distinguished by
  `mi_consolidation_entry_shadow.entry_mode` (`db.py:1725` — 'anticipate' | 'confirm' | 'ur';
  realized-R **never blended across modes**, ADR 0013:91).
- Param reconciliation (flag params → the SIGNED family model — no new thresholds invented):
  runup gate = family 15%/10d (HTF-class keeps its sourced 90/40 in `htf.md` — HTF is the
  *setup*, Confirm is the *entry*); anchor = runup-peak-close (ANCHOR-STABILITY invariant,
  `anticipation.py:606-611`), retiring the pivot-walk; tightness = volatility-relative RMV/ATR
  (the shared primitives `_compute_rmv`/`_compute_fresh_tightening` already imported by
  anticipation.py — no dup); 0.4% tight-close stays **ranking-only** (operator veto intact).
- Wiring: `confirm_signal_at` fires on the EXISTING #94 intraday flag-break event (price >
  base_high + ADV gate + the #145 idempotency guard) → writes an `entry_mode='confirm'` shadow
  row via the same settlement machinery Anticipate uses. **Shadow-only at merge** — Confirm
  entering the live entry pipeline is a separate, later promotion with its own gate (money).
- What must NOT break (regression pins): the #94 scan keeps reading `mi_flag_candidates` stages;
  HTF detection (#356) keeps consuming the same state machine; `test_execute_task_routing`
  freezes `/flags` routing.

### D2 (#146) — direct TIGHTENING→TRIGGERED (drop the COILED prerequisite), gated on the N≥10 backtest

- **Proposed gate** (`flag_detector.py:947-959`): `TRIGGERED = close > base_high_close AND
  breakout_vol_ratio ≥ 1.5` from EITHER TIGHTENING or COILED (the `coiled_today or
  was_coiled_recent` conjunct is removed; COILED remains a *quality stage* for
  ranking/anticipate-fire, not a trigger gate). Rationale = the operator's own principle
  (flag_continuation.md:88): "a flag is a tight trading range; if it breaks that range, it's a
  flag break."
- **Backtest (the flip gate)** — `scripts/probes/_146_triggered_gate_backtest.py`, read-only:
  cohort = all TIGHTENING days with `close > base_high_close AND vol ≥ 1.5×` that did NOT carry
  coiled/was_coiled (the 9/92 set + everything since = expect N≥15). For each: settle forward
  R via the family settlement (`entry=base_high`, stop=breakout-day low — the HTF Phase-3
  fill-nuance, break-day-inclusive). Compare vs the COILED-triggered cohort. **Ship rule:**
  direct-trigger cohort forward stats ≥ COILED-triggered cohort's (which is currently negative
  at N=5 — the bar is honest, not soft) AND no blow-up tail (max single -R bounded). HARD-gate
  rule (CHANGE_PROCESS §3): the full promoted-name list goes to the operator with the sign-off.
- Interaction: the #145 idempotency guard STAYS post-fix (belt-and-suspenders, per ADR 0005:92).

### D3 (ADR 0013 Phase-4) — undercut routes to **WATCH_UR**, not INVALIDATED

- `flag_detector.py:801-804`: close < base_low_close → new stage **WATCH_UR** (base retained,
  age clock keeps running toward the 25d cap) instead of INVALIDATED. WATCH_UR's own trigger =
  **base-low reclaim** (close back above base_low_close) → routes to the **U&R entry (c)**
  machinery (reuse `anticipation.detect_gdl_reclaim`'s reclaim shape per ADR 0013:86-88),
  writing `entry_mode='ur'` shadow rows. All other INVALIDATED gates (MA stack, 52w-high
  distance, depth, age) unchanged.
- **Post-reclaim stage:** the name returns to **TIGHTENING** (base intact, same anchor, age
  clock uninterrupted) — the U&R signal is an *entry event*, not a terminal state; a later
  base-high breakout from the resumed base is a legitimate Confirm. A second undercut re-enters
  WATCH_UR (no oscillation cap needed — the 25d age cap bounds the loop, and each U&R entry row
  is idempotent on its undercut-low anchor).
- **Backtest (its own gate, decoupled per ADR 0013:222-223)** — same probe script, second
  cohort: historical INVALIDATED-by-undercut bases (query `mi_flag_candidates` stage history);
  measure (i) how many later reclaimed within the age window, (ii) forward R from the reclaim
  close with stop = undercut low. Ship rule: reclaim-cohort forward R positive at N≥10 and the
  false-revival rate (reclaim → immediate re-undercut) < 40%.

## 3. Rollout, sequencing + the built-in go-live triggers

1. **Card order:** C1 (probe script, both cohorts — it needs no code change) → operator reviews
   both cohort printouts → sign-off per decision → C2 (D2 gate change) + C3 (D3 WATCH_UR) land
   behind the family flag; C4 (D1 merge/retire + param reconciliation + SSoT rewrite) last —
   it renames the world and is easiest to review once the machine's semantics are final.
2. All three land **shadow-visible** (stage changes + entry_mode rows are observable in
   `mi_flag_candidates`/`mi_consolidation_entry_shadow` — no live money path exists in this
   family yet; the #397 shadow→paper money gate is untouched).
3. **Built-in triggers (the operator's standing dark-needs-a-trigger rule):** a data-gated
   review `consolidation_unification_review` — predicate: ≥10 settled `entry_mode='confirm'`
   OR `'ur'` shadow rows; earliest +14d — surfaces the first settled-R readout per mode and
   drives the next promotion decision (paper). The #146/#D3 backtest cohorts are pre-flip
   gates, not post-hoc.
4. SSoT rewrite (C4, same commit): `flag_continuation.md` gains a header pointing at ADR 0026 +
   "merged into the consolidation family; entry (b)"; ADR 0013's Phase 2-4 marked delivered;
   change-log entries per CHANGE_PROCESS (fields incl. reversion-flag: D3 reverses the 5/01
   undercut rule — the *why it was wrong*: it encoded invalidation semantics the operator never
   held; the U&R evidence base was absent when written).

## 4. Card decomposition (Opus/Sonnet-executable)

- **C1 — `_146_triggered_gate_backtest.py`** (both cohorts: direct-trigger + undercut-reclaim;
  settlement via the family fill-nuance; prints ship-rule verdicts + full name lists). Read-only.
- **C2 — TRIGGERED gate change** (remove the COILED conjunct; keep #145 guard; 6 tests incl.
  TIGHTENING+breakout+vol→TRIGGERED · no-vol stays · COILED path byte-identical · stage-history
  freeze updated).
- **C3 — WATCH_UR stage + reclaim routing** (new stage enum + transition + U&R signal writer;
  8 tests incl. undercut→WATCH_UR-not-INVALIDATED · reclaim→ur-entry-row · age-cap still kills ·
  other INVALIDATED gates untouched).
- **C4 — strategy merge + param reconciliation + SSoT rewrite** (retire row, entry_mode wiring
  for confirm via #94, params → family model, both SSoTs; regression pins listed in D1).
- **C5 — `consolidation_unification_review` gated review** (the go-live trigger).

## 5. Operator forks

- **F1 (D2 bar):** rec = ship if, at N≥10: direct-trigger cohort **median ≥ −0.25R AND win-rate
  ≥ 25% AND mean ≥ 0R** — the mean alone is fat-tail-carriable (the #290 lesson: −1R medians
  under a positive mean = a lottery, not an edge); the median+WR floor makes the bar
  distribution-honest. The incumbent COILED gate is *negative* at N=5, so this still demands the
  challenger beat both the incumbent and zero. Alternative: mean-only (weaker — rejected).
- **F2 (D3 scope):** rec = WATCH_UR keeps ALL other invalidation gates live (undercut-only
  carve-out). Alternative (defer any invalidation while WATCH_UR) — NOT recommended (turns a
  20MA-loss zombie into a watched name).
- **F3 (D1 timing):** rec = C4 lands with C2+C3 in one flip (one SSoT rewrite, one review).
  Alternative: merge first, gates later — more churn, two reviews.
