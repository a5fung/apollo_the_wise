# Block 3 T6 — v2.0 gap-hunt + methodology extraction (Fable, 2026-07-11 eve)

## T6a — the gap-hunt verdict: **no undesigned rock — the program is execution-shaped**

Deep read of `apollo-v1.1-v2.0.md` (P1–P6, M-milestones, D-series, E-lanes) against the ADR
shelf. Every named Phase-2 rock carries a design to execution depth: P3 management judge (0017) ·
P1 experience stack (0018) · sourcing backbone (0019) · P4 book incl. **regime-adaptive
selection** (0020 §5 `regime_matrix` + B4 card — the one I suspected was missing; it isn't) ·
P2 sight (0021) · P5/P6 allocator + replay-CI (0022) — plus this weekend's 0023–0031. **The
roadmap said "none — it's all execution" would itself be the finding; that is the finding.**
The scarce resource ahead is build/verify bandwidth and evidence accrual, not design.

Three SECOND-ORDER seams surfaced (named so they don't become silent gaps; none is a rock):

1. **The sizing-stack composition rule.** Conviction sizing (judge-tier) × `regime_matrix`
   (0020) × drawdown multiplier × allocator budgets (0022) will eventually multiply together.
   0020 partially composes (one multiplier in the sizing step; regime-halving = outer floor),
   but no single precedence note owns the FULL stack — the same class as the stop-surface
   precedence T4-R8 fixed for stops. *Disposition:* one composition paragraph added to 0022 at
   its sign-off (P5 is where the last factor arrives); until then only two factors are live and
   already composed. No task needed now; recorded here + register-style.
2. **The program-KPI loop has metrics but no owner surface.** §governance lists the success
   metrics (replayed expectancy, live-vs-replay R, MFE capture, judge precision, fail-open rate,
   miss-rate) — computed today across scattered docs/reviews. *Disposition:* make the M3 monthly
   ride-along's FIRST agenda item "the six metrics, one table" (a checklist line for the 8/1
   sitting, not a build).
3. **E2 (dev-session reasoning ≠ deployed tooling)** stays the honest capability gap; it rides
   absorbed tasks (#167/#212) with its closure called out. No action beyond the E-lane's own note.

## T6b — methodology extraction: what the notes still hold that the system doesn't

Mined `operator_shared_notes.md` (the Pradeep threads, the 6/16 verification, layering, RMVP,
build-implications) against what got encoded. Most of it HAS been routed (volatility-relative
tightness → the primitives + 0031's character profile · thrust-gate/universe → #354's rebuild ·
RMVP/ADR reconciliation → #54 · catalyst-conditional exit leash → filed, reopens with #210/#211).
**One rule remains genuinely un-encoded, and one hygiene note:**

### The extraction — Pradeep's concrete catalyst-quality bar (un-encoded)

`operator_shared_notes.md:394-395`: **"2× 39%+ sales growth + 39%+ projected"** — Pradeep's
explicit materiality bar for an earnings catalyst (two consecutive quarters of ≥39% sales growth
plus ≥39% projected). The rubric scores revenue *acceleration* generically (axis 1/6 deltas);
this NAMED absolute bar — the "explosive-growth regime" flag — exists nowhere in
`catalyst_rubric.py`, the judge rubric, or the 0028 profile hypotheses. It is exactly the kind
of operator-corpus rule T6b exists to surface (the tail-dependence principle's sibling).

**Candidate encoding (evidence-gated, not hardcoded — the notes' own "verify, don't gate"
instruction):** a boolean `pradeep_explosive_growth` feature (q0 ≥39% AND q-1 ≥39% AND projected
≥39%, all from already-extracted deltas) → measured first, wired only if it separates.
**The evidence gate is nearly FREE:** the #448 b6 session (7/16) already re-derives every
axis input deterministically over the N=96 cohort (the no-LLM path) — adding one boolean column
+ its outcome-crosstab line to that session costs minutes and answers "does the 39%-bar cohort
outperform the generic-acceleration cohort?" If it separates → it becomes a 0028
`pradeep_explosive` profile feature (P1 tests salience DIRECTIONS — this is one, with a source)
+ an axis-6/milestone input candidate via CHANGE_PROCESS. If not → recorded as
checked-and-refuted, the phantom-criterion discipline.

### The hygiene note — SiP layering (recurring operator correction)

"Anticipation is ONE tactic; Stocks-in-Play is the CONSOLIDATED list across ALL tactics"
(`:348-353` — "I've conflated these multiple times — stop"). Encoded in ADR-0004
`mi_stocks_in_play`, but the correction recurs, which usually means a SURFACE still conflates
them. *Disposition:* one-line audit at the next SiP-touching build (does any consumer label a
single tactic's output "Stocks in Play"?) — a grep-level check, riding whichever card touches
SiP next; recorded here so it isn't lost.

## Dispositions summary (nothing new filed as a task)

- Sizing-stack composition ¶ → **rides the 0022 sign-off** (noted for the sitting).
- Six-metrics table → **M3 8/1 agenda line**.
- **39%-bar backward-check → rides the #448 7/16 session** (one boolean column + one crosstab
  line; its PLAN line gains the add-on).
- SiP-conflation grep → rides the next SiP-touching card.
