# Decision digest — 2026-07-18 (weekend push, day 2)

Sign-ready items the push produced today. Each = the fork + a 1-line rec. Nothing
below is applied — all await your ruling (money-adjacent / SSoT / safeguard).

## Immediate rulings (quick)

1. **#481 — MAX_EXTENSION SSoT-vs-code drift** (money-adjacent, detection criterion).
   Finding (`docs/analysis/481_extension_provenance_2026-07-18.md`): the live code has
   enforced "skip if prev_close ≥ 50% above the 5-day MIN close" **since inception**
   (ep_detector.py:99, gate :1858-66) + a −25/−15 score penalty at 3-mo +50%/+30%. The
   SSoT (`magna53_ep.md`) claims `prev_close ≤ 1.50×SMA-10` — a rule that has **never
   existed in any commit** (birth transcription error). **Fork:** (a) the live 50%/5-day
   rule is intended → I correct the SSoT to match the code (transcription fix, NOT a
   criterion change) + cite it; or (b) you actually want the SMA-10 rule → that's a real
   criterion change (CHANGE_PROCESS + N≥10 backtest). **Rec: (a)** — the code is the
   long-standing authority; the SSoT is simply wrong. Confirm and I fix the doc.

2. **#481 — `dvol_min=$20M` anticipation floor** (ADR 0013 §2.3's own deferred ask).
   Sourced as an explicit "probe value"; the 6/16 funnel ran on it. **Fork:** sign $20M
   as-is, or name a replacement. **Rec: sign as-is** (no evidence it's wrong; revisit at
   the next Family-A calibration). [`_HTF_MIN_ADR_PCT=0.04` needs no ruling — already
   sourced in operator_shared_notes; I'll just add the citation.]
   → On your ruling of #1+#2, `check_gate_provenance` baseline shrinks 3 → 1 (or 0).

3. **#461 — position-cap TOCTOU fix** (SAFEGUARD — sign-then-build).
   Design: `docs/decisions/461_toctou_cap_design_2026-07-18.md`. Notable: the race isn't
   "+1" — with `Semaphore(5)` fan-out + cross-process HTTP execution, the live cap can be
   exceeded by up to **+4**. Fix = per-`account_mode` `pg_advisory_xact_lock` around an
   authoritative recount+insert (~30 lines, no cap-value/behavior change, per-mode
   isolation preserved). **Fork:** approve the build now, or defer (the race is real but
   low-probability). **Rec: approve** — it's a clean correctness fix on the safety
   backbone; I build it behind the same tests, you review the diff before deploy.

## Designs delivered — sign at their own gate (not immediate)

- **#331 gap-vs-structure alignment axis** — **ADR 0033** delivered. Boost-only, reuses
  #330's primitives, STEP-0 includes a magnitude-independence table (proves it's not gap
  magnitude in disguise). You sign the credit table + STEP-0 before the shadow ships.
- **#306 winner-harvest exit-tune** — `docs/analysis/306_winner_harvest_design_2026-07-18.md`.
  Builds on the already-ruled F1 (peak-lock +6%/60%, 7/9). Axes B/C/D each gated on their
  own shadow review (earliest ~8/06) + your signature. Targets the ~$10.5k mgmt leak.
- **#461 design** (above) is itself the deliverable; the build is what needs your sign.

## Carried over (from `decision_digest_2026-07-17.md`)
F2b DONE. Still needs you: #197 (N-27), #416 (close), #306 (fold), #269 (scope), #299
(funding), #357 (role) · account-minutes #195/#280/#420/#384/#194.
