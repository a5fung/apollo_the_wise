# #170 — EP cooldown re-setup admission: design + backtest spec (Fable block 1, 2026-07-11)

**Status: DESIGN — flip gated on the C1 backtest table + operator sign-off (CHANGE_PROCESS).**
Amends `docs/setups/magna53_ep.md` (cooldown section, same commit as the code change). The
existing shadow classifier + backward-check are the evidence base; this turns them into an
admission rule with a pre-flip backtest and a post-ship effectiveness trigger.

## 1. Current state (anchors)

- `EP_COOLDOWN_DAYS = 60` hard filter (`ep_detector.py:100`) — any ticker alerted ≤60d ago is
  skipped before grading. One carve-out ships: `gap ≥15% AND is_earnings_day` (5/08, HIMX;
  `ep_cooldown_bypassed_earnings` audit).
- Shadow classifier `_is_cooldown_resetup()` (`ep_detector.py:109-119`, live, fail-open):
  marks `days_since_prior_alert ≥ 10 AND gap ≥ 15%` as re-SETUP vs re-fire; audit
  `cooldown_resetup_admit_shadow`; changes nothing live.
- Backward-check (6/01, in the #170 gated-review entry `data_gated_reviews.yaml:4886-4920`):
  55 cooldown-suppressed ticker-days / 90d; 22 with gap ≥15%; the `days_since ≥10` split shows
  **median +17% fwd-max vs +8.8% baseline (~2× hit-rate at ≥+15% forward)**. Review READY since
  6/08.

## 2. The admission rule (design)

**Admit through the cooldown** (i.e. do NOT suppress; the candidate proceeds through the FULL
normal pipeline — grade → judge → threshold — admission is *evaluation*, never an auto-alert):

> `days_since_prior_alert ≥ 10 AND gap_pct ≥ 15%` — any catalyst class.

- The earnings carve-out **stays as-is** (no days-floor: a fresh earnings print is its own
  re-set event; it's now the special case of a general rule rather than the only door).
- `< 10 days` stays suppressed regardless of gap (the backward-check's own boundary:
  extended-continuation, not re-setup). ≥60d unchanged (no cooldown).
- Every admission emits `cooldown_resetup_admitted` (audit) and the alert row (if one results)
  carries a `resetup_admitted` marker — post-ship quality is measurable per-cohort, never
  blended into baseline EP stats.
- Cost bound: ~3-4 admissions/week (the backward-check rate) × one grade each — trivial; the
  #405 catalyst cache applies to these like any candidate.

**Why this shape:** the discriminator is exactly what the live shadow classifier already
computes — the flip is `continue` → `pass-through + tag` on an already-validated predicate. No
new thresholds are invented; 10d/15% came from the 6/01 cohort and get re-confirmed by C1 below.

## 3. C1 — the pre-flip backtest (the N≥10 gate)

`scripts/probes/_170_resetup_backtest.py` (read-only, prod): pull ALL cooldown-suppressed
scan-log rows (`mi_ep_scan_log.filter_reason ILIKE 'EP cooldown%'`, full history — expect
N≈55+ ticker-days, ≥22 at gap≥15) → classify each with the admission predicate → join forward
returns (`mi_daily_closes`: fwd-max-close-5d, fwd-5d) → print:
1. Admitted-cohort vs suppressed-cohort forward distributions (median/mean/hit-rate ≥+15%).
2. The would-be-admitted name list, dated (the CHANGE_PROCESS hard-gate list for sign-off).
3. Sensitivity: the FULL {7,10,14} × {12%,15%,20%} joint grid (all 9 cells, not two marginal
   sweeps — days and gap plausibly interact: a 20% gap at day 8 may be a re-setup while a 15%
   gap at day 8 is continuation). Confirm 10/15 sits on a plateau of the joint surface; if the
   plateau moves, the RULE moves to the plateau (thresholds-are-outputs).
**Ship rule:** admitted-cohort median fwd-max ≥ 1.5× the suppressed baseline at N≥10 (the 6/01
readout was ~2×) AND no admitted-cohort left-tail worse than baseline. Below bar → stay shadow,
re-arm the review +30d.

## 4. Rollout + the built-in effectiveness trigger

1. C1 runs → operator signs the table+list → C2 flips the admission (+SSoT same commit:
   magna53_ep.md cooldown section rewritten to the tiered rule, change-log entry with the
   backward-check + C1 citations; reversion-flag: loosens 60d — why the 60d blanket was *wrong*:
   it encoded "any recent alert = extended" which the 6/01 cohort disproves at ≥10d+15%).
2. `data_gated_reviews.yaml` → `cooldown_resetup_effectiveness`: predicate = ≥10 alerts carrying
   `resetup_admitted`; action = compare their judge-tier mix + fwd returns vs the baseline EP
   cohort; regression → tighten (raise the days floor) or revert via CHANGE_PROCESS. The #170
   review entry itself → `done` on flip (this new review is its successor).
3. The old `#170` shadow classifier audit (`cooldown_resetup_admit_shadow`) retires with the
   flip (its telemetry is superseded by the admitted marker).

## 5. Cards

- **C1** — the backtest probe (read-only; ship-rule verdict + name list + sensitivity grid).
- **C2** — the admission flip (`ep_detector.py` cooldown filter: add the predicate branch +
  audit + alert marker; 5 tests: admit-at-10d/15% · suppress-at-9d · suppress-at-14%-gap ·
  earnings carve-out unchanged · marker rides the alert row) + SSoT amendment (same commit).
- **C3** — the effectiveness review entry + retire the shadow audit.

## 6. Operator fork

- **F1 — admission scope:** rec = evaluation-only admission (as designed; the full grade/judge
  bar still stands between an admitted candidate and an alert). Alternative — admit straight to
  the old scoring path with a re-setup penalty — NOT recommended (invents a new penalty with no
  evidence base).
