# #357 — Persistent Sugar Babies: role decision memo (Fable block 1, 2026-07-11)

**Status: DECISION MEMO — the role call is the operator's** (methodology, THE LINE). This frames
the fork, designs both branches to execution depth (thin on the non-rec), and specs the STEP-0
calibration that makes the call evidence-based instead of taste-based.

## 1. What a sugar baby is (as-built)

A stock **CONDITION**, not a setup (operator 6/22, `family_a_setups_split_2026-06-22.md:83-91`):
≥3 9M EOD prints in 180d → `mi_sugar_babies_cohort` (`db.py:652-667`, daily refresh). Surfaced
today as a top-10 brief section + `/sugarbabies`; **consumed by nothing** — no grade input, no
judge-payload slot, no axis (`ep_detector._score_ep` and the judge payload are both blind to it).

## 2. The fork

**A — confluence input** (operator's 6/22 lean: "any setup can include a sugar-baby or not →
likely an additional confluence/score input on a stock already in a setup, not a standalone play")
**vs B — standalone watchlist** (keep it observational; a brief surface only).

### Recommendation: **A**, staged with the axis discipline the judge system already enforces

The thesis (a name that repeatedly prints 9M moves is a *recurring-momentum* name — its next
setup deserves credit) is exactly the shape of the theme/structure axes: a **context credit**,
which under ADR 0024's F1 split belongs to the **axes, not the judge's catalyst verdict**. So A
implements as:

1. **Stage 1 — visibility (ship now, no authority):** a `sugar_baby: {count_180d, last_print}`
   field in the judge DecisionContext + one line on the EP alert card. The judge *sees* it;
   nothing re-weights. Zero-risk, makes every future readout interpretable.
2. **Stage 2 — a meta-rubric axis credit, ONLY if STEP-0 proves direction** (the ADR 0015/0016
   gate): boost-only, +1 step through `compose_final_tier` under the existing NET_CAP=1 —
   composes with theme/structure, cannot stack past the cap, never penalizes non-members.
   If STEP-0 is flat → Stage 2 never builds and A gracefully degrades to Stage 1 (visibility).

### STEP-0 calibration (runnable now, read-only — the decision input)

`scripts/probes/_357_sugar_step0.py`: join `mi_ep_alerts` (post-3/16, the trustworthy window) ×
cohort membership *as of the alert date* (the cohort table is dated — no lookahead) × forward
returns (`mi_daily_closes` fwd-5d / fwd-max). Output: member vs non-member alert forward stats
(median/mean/win%), split by tier. **Ship-Stage-2 rule:** member-cohort ≥ theme-axis-grade
separation (the ADR 0015 STEP-0 showed +18.0% vs +9.6%; sugar needs a comparable, not
necessarily equal, spread) at N≥15 member-alerts. Below bar → Stage 1 only.

### Branch B (thin, for completeness)

Keep observational; fold the two brief sections into one and stop. Costs nothing, learns nothing
— and leaves the operator's own 6/22 lean unbuilt. Only right if STEP-0 comes back flat, which
is exactly what STEP-0 exists to find out — so **B is not a fork to pick now; it's the automatic
fallback encoded in the Stage-2 gate.** (This is why the memo recommends A without needing the
operator to bet: the evidence gate decides.)

## 3. Surface re-frame (both branches; independent of the fork)

The persistent-cohort brief section re-frames as **Family-B/EP universe context** (per the 6/22
roadmap): cohort names annotated with their CURRENT setup stage if any — HTF/flag stage from
`mi_flag_candidates`, active EP/9M lifecycle (ADR 0027's `origin='family_b_*'` rows once live).
One section, one sort (most-recent print first), stage column. The single-day
`mi_9m_day2_candidates` section is unchanged (different object: today's prints).

## 4. Cards

- **C1 — STEP-0 probe** (read-only; member-vs-non-member table + the Stage-2 verdict line).
- **C2 — Stage-1 visibility** (DecisionContext field + alert-card line; 3 tests; no authority).
- **C3 — surface re-frame** (brief section merge + stage overlay; 3 tests).
- **C4 (gated on C1's verdict + operator sign-off) — the axis credit** (boost-only, NET_CAP-
  capped, shadow-logged like theme_axis_shadow before any authority; the ADR 0015 rollout shape).

**Sequencing:** C1 now → operator reads the table and rules the fork → C2+C3 ship regardless of
the ruling (visibility + surface are role-neutral) → C4 only on a green STEP-0 + sign-off.

## 5. What this closes

#357's DoD ("role decided + surface re-framed") = the operator ruling on §2 + C3 shipped. The
Stage-2 axis, if it happens, is a NEW tracked item under the meta-rubric program (it composes
with #332's setup-class work — a sugar-baby credit is class-relevant for the Pradeep
small-cap-explosive class specifically).
