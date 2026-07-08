# M1-c — rubric amendment + theme-axis weighting sheet (DRAFT for the M1-d sitting)

**2026-07-08 · ADR 0024 M1-c · #335 · DRAFT — not applied.** The turnkey prep for the M1-d
operator sitting (~7/18): what you sign → then flip `composite_authority` (the M1-a flag,
default-off today) **atomically** with this amendment. M1 is **theme-axis ONLY** (fork F3,
core-first); structure/gap/neg join later via the SAME `compose_final_tier`, no new mechanism.

---

## 1. The problem this fixes (double-count)

Today the load-bearing judge is told (ADR 0011 clause 4 / `ep_grade_judge.py:143` clause 5):
> "Theme heat + technical structure + gap alignment **modulate** the grade **up or down**."

So the judge ALREADY moves its tier on theme heat — *qualitatively, invisibly, inconsistently*.
If the scored theme axis (ADR 0015) also adds credit on top, the same signal is counted **twice**.
ADR 0024 §3 resolves it by DOMAIN split: **the judge owns the CATALYST verdict; the scored axes
own the CONTEXT credit; the final tier is their capped arithmetic composition** (`compose_final_tier`,
built dark in M1-a, commit `c9d0caa`).

---

## 2. The rubric amendment (the exact text to sign — rides the flip commit, CHANGE_PROCESS)

Amend BOTH mirrors in the same commit as the flip (they must not drift):
- `docs/decisions/0011-ep-holistic-grade-judge.md` clause 4
- `agents/market_intelligence/ep_grade_judge.py:143` clause 5 (the live judge prompt)

**OLD:** "Theme heat + technical structure + gap alignment modulate the grade up or down (a
strong theme can lift a routine catalyst; a fading one can temper it)."

**NEW (proposed):** "Theme heat, technical structure, and gap alignment **inform your CATALYST
ATTRIBUTION** — e.g. *does the theme explain this gap?* — but they do **NOT** move your tier.
**Your tier = the catalyst verdict alone.** The scored context axes own their credit and apply
it OUTSIDE, after your verdict (`compose_final_tier`, capped ±1 step). Cite theme/structure/gap
freely in your rationale — legibility is unchanged; you simply stop double-counting them in the
tier."

**Atomicity (ADR 0024 §3):** the amendment + the composition go live TOGETHER — never a window
where theme is *neither* judge-weighed *nor* axis-credited, and never *both*. Pre-flip nothing
changes (axes stay shadow; the judge keeps qualitatively weighing).

---

## 3. The theme-axis weighting sheet — v1 (THE sign-off surface)

The credit table `theme_axis_credit(membership, coverage_state) → {credit_steps, marker, reason}`
(ADR 0015, operator-signed 2026-07-04; boost-only — **never negative**):

| Theme stage | credit_steps | rationale |
|---|:--:|---|
| **Accelerating** | **+1** (routine→strong, strong→game_changer) | Pradeep #1 driver; the NBIS case |
| **Nascent** | **+1 ONLY within the near-miss band** (composite ~≤10% under the tier boundary) | early = real but unproven |
| **Mainstream** | **boundary tie-break upward only** | sustain, don't chase — *⚠ open Q, see §5* |
| **Fading / Retired** | **0** | not poison, just not special — never penalize |
| **Stands-alone** (#319) | **0**, marker `standalone` | no credit, NO penalty (may be an undiscovered-theme blind spot) |

**Compose mechanics** (`compose_final_tier`, M1-a): `final = clamp( base_tier + Σ credit_steps )`
with **Σ capped to net ±1 total** (fork F2), on the lattice `none < MODERATE < HIGH`. base_tier =
the judge tier (authority=judge) or the floor tier (fallback) — one function, no separate path.
For M1 (theme-only) the sum is just the theme credit, so the cap is not yet binding — it becomes
load-bearing when structure/gap/neg join.

**STEP-0 calibration evidence (ADR 0015, N=386 relaxed-history — direction holds, not contradicted):**

| stage | fwd-return (adj) | vs themeless | win% |
|---|--:|--:|--:|
| Accelerating | **+18.0%** | +9.6% | **77%** |
| Mainstream | +14.0% | — | 67% |
| Fading | +11.1% | — | 67% |
| Nascent | +5.4% (N=4, no signal) | — | 2/4 |

Accelerating full credit is strongly supported; Fading-at-zero validated as conservative; Nascent
near-miss-only caution stands (N=4).

---

## 4. Worked examples (through `compose_final_tier`, for `/why`)

| case | base (catalyst) | theme credit | net (capped) | → final | render |
|---|---|---|:--:|---|---|
| **NBIS** | MODERATE | Accelerating +1 | +1 | **HIGH** | "judge strong (catalyst) + theme Accelerating (+1) → HIGH" |
| Fading name | HIGH | Fading 0 | 0 | HIGH | "judge strong + theme Fading (0) → HIGH" |
| ceiling | HIGH | Accelerating +1 | +1 (clamped) | HIGH | can't compose above HIGH |
| standalone | MODERATE | standalone 0 | 0 | MODERATE | no credit, no penalty |

---

## 5. What you sign at M1-d (the checklist)

1. **The credit table (§3)** — accept as v1, OR resolve the **open question: upgrade Mainstream
   from tie-break → +1?** STEP-0 shows Mainstream +14.0%/67% — more than tie-break implies, but
   below Accelerating; 0015 deferred it to this checkpoint. *Rec: keep tie-break v1 (anti-chase;
   the +1 is Accelerating's edge), revisit with the M1-b regrade deltas.*
2. **The ±1 net stacking cap** (fork F2) — confirm.
3. **The amendment wording (§2)** — confirm both mirrors.
4. **Then flip** `COMPOSITE_AUTHORITY=true` (M1-a flag) in the SAME commit as the amendment.

**Gates (non-negotiable):** CHANGE_PROCESS + the M1-b batched-regrade verdict-delta table (ONE
paid run) + operator labels + a DB/env toggle for instant revert + the recurring
`composite_effectiveness` review + the authority-registry row (M1-e). This is an **L2 bounded**
authority (arithmetic, capped) per ADR 0024 §5 — not an unbounded veto.

---

## 6. Scope note
Theme-only for M1. Structure (0016), gap-alignment (#331), and the neg/dilution axis (0021) compose
in later through the SAME `compose_final_tier` — at that point the ±1 net cap becomes binding and
the weighting sheet grows those rows. This draft covers ONLY the theme axis + the amendment.
