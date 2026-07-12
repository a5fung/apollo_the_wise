# Block 3 T4 — cross-ADR conflict/compose register (Fable, 2026-07-11 eve)

**What:** ADRs 0025–0029 were designed independently in one weekend; 0030–0031 landed tonight;
the Lane-1 probes landed fresh evidence the same day. This sweeps them against each other +
0011–0024 + tonight's evidence. **Every line carries a resolution; a card that builds into any
of these areas MUST honor its line.** Severity: 🔴 evidence/design conflict · 🟠 build-order or
shared-machinery constraint · 🟢 compose-fine, note recorded.

---

## 🔴 R1 — 0026-D2 (drop COILED) is EVIDENCE-CONTRADICTED by tonight's #146 probe

0026-D2's loosening premise was "TRIGGERED N=5 −2.66%/0%WR — the incumbent gate is already
negative, loosening can't hurt." The 7/11 probe (`146_triggered_gate_backtest_table`) settled the
incumbent properly: **+0.78R mean / +14.9R total / avg-winner +5.62R over N=19 — tail-positive.**
The premise is reversed; the drop-COILED replay is only 4/21-faithful (no rule-grade evidence FOR
the change).
**Resolution:** 0026 **F1(D2) goes to the sitting WITH the 146 table; the D2 card is PARKED**
(not built) pending a faithful direct-trigger harness. D1 (retire flag_continuation) and D3
(WATCH_UR) are UNAFFECTED — their evidence is independent; they may land without D2. This line
supersedes 0026's internal D2 sequencing.

## 🔴 R2 — #395 NO-GO reshapes what 0026's unification is FOR

The live shadow retired the Anticipate real-entry path (−1.23R/N=34). 0026's 3-entry unification
survives as MACHINERY consolidation (one universe, one coil, one lifecycle) — but its live-trade
ambition now rests entirely on Confirm/U&R evidence that has NOT accrued (confirm N=7 −0.11R;
U&R unbuilt).
**Resolution:** proceed with 0026 as machinery + shadow; **no entry mode of the family is
live-eligible on Anticipate's old Phase-A evidence** — each mode earns its own N≥10 gate. The
sitting rules 0026 F1–F3 with the `395_go_nogo_evidence` doc open.

## 🟠 R3 — ONE reclaim primitive, two consumers (0026-D3 × 0027-D3)

0026-D3 routes WATCH_UR's base-low reclaim through "`anticipation.detect_gdl_reclaim`'s reclaim
shape"; 0027-D3's Family-B trigger IS gdl reclaim. Two cards building two variants = drift in the
one shape (volume-confirm rule, close-vs-intraday semantics).
**Resolution:** `detect_gdl_reclaim` is generalized ONCE (parameterized by anchor level +
volume-confirm) in anticipation.py; **both** the 0026-C3 and 0027-C3 cards import it; neither
re-implements. Whichever card lands first does the generalization; the second card's DoD cites it.

## 🟠 R4 — ONE settlement driver for every new shadow (0023/0026/0027/0031 × #445)

#445 (replay-driver debt) exists because shadow settlements multiplied hand-rolled replay math
(the l=c-class misread 0027 §D3 itself flags). Tonight added another consumer (0031's two arms);
0026's confirm/UR rows and 0027's gdl_reclaim settle too.
**Resolution:** every new shadow settles through the SHARED driver (`apply_daily_exit_step` /
the family fill-nuance settle) — no per-shadow bar-walk math. **#445's consolidation is the
enabling card and should land BEFORE 0026-C3/0027-C3/0031-C3**, or those cards inherit the bug
class. Gap-through-stop semantics inside shadows use the conservative gap-fill rule (#290) until
0029-D2 defines the live semantics — then shadows adopt 0029's rule (one definition).

## 🟠 R5 — "family" means two things (0025 × #452); and #452 must reuse fork-B's predicate

0025 Stage-A "family" = narrative-stem cluster (for MERGING themes). #452 (pre-mortem R1) needs
a family for the CORRELATED-EXPOSURE slot cap. Same word, different objects — two hand-rolled
definitions will drift.
**Resolution:** #452's v1 grouping key = canonical THEME/narrative membership (post-0025-merge,
which makes 0025 a *prerequisite-for-quality* not a blocker), named **`exposure_family`** (never
bare "family"). AND: #452's cap counts positions via **`db.OPEN_POSITION_STATUSES`** (tonight's
fork B) — never a fourth hand-rolled open-position vocabulary.

## 🟠 R6 — 0028 adds a THIRD versioned grade surface; the 0030 gate must key on it

0030's pass-record keys = (RUBRIC_HASH, CATALYST_GRADE_PROMPT_VERSION, JUDGE_MODEL,
corpus_version). 0028 ships per-class salience profiles = a new versioned surface that changes
grade outcomes without touching either prompt.
**Resolution:** when 0028 lands, (a) its profile set carries a version/hash, (b) the 0030
pass-record tuple EXTENDS with it, (c) judge-corpus cases gain a `setup_class` field so
per-class regressions are visible. Recorded in both ADRs' card notes; the 0030 C2 gate reads the
key tuple from ONE place so extending it is a one-line change.

## 🟠 R7 — 0025 merges shift baselines + axis inputs; pre-declare or eat false alarms

The merge arm will drop `theme_count_active` (an L2-banded metric — the 7/8 anomaly metric!) and
flip `in_active_theme`/theme-stage inputs for absorbed members (judge axis, #328–331, T2c's
judge metrics).
**Resolution:** 0025-C3's deploy note PRE-DECLARES the expected L2 level shift (the same idiom as
a rubric-era boundary); the merge audit row carries before/after membership so any judge-axis
movement is attributable to the merge, not the market. Same pre-declaration discipline applies to
the T2c judge metrics at the 7/18 authority flip and at 0028's ship.

## 🟢 R8 — 0031 × 0023 × 0029: already composed at design time (inherit)

Stop-surface precedence: pivots (0031) propose WHAT level; 0029-D1 owns WHO moves stops; if
giveback (0023) and a pivot arm are BOTH live: `live stop = max(arm_stop, giveback_floor)` — the
one precedence rule, stated in 0031 §4. Live flips serialize: giveback F1 → (0029-D1) → pivot
fork. No two concurrent live stop changes, ever.

## 🟢 R9 — 0027 seeding must not become a cooldown bypass (#170)

#170's NO-GO says re-gaps after suppression are anti-selective. 0027's Family-B lifecycle rows
are observational (fine), but a lifecycle row on a cooldown-suppressed name could route around
the cooldown via the shadow-entry path.
**Resolution:** Family-B rows on cooldown-suppressed names are tagged (`cooldown_suppressed`)
at seed time; the gdl_reclaim shadow readout segments on it; no alert/entry surface consumes an
untagged row. One column + one WHERE clause in 0027-C2/C3.

## 🟢 R10 — naming: "character profile" (0031, per-ticker) ≠ "conviction/salience profile"
(0028, per-setup-class). Distinct concepts; keep the distinct names everywhere (incl. columns).

## 🟢 R11 — #332 classifier feeds #357's credit (compose-as-designed)

The sugar Stage-2 axis credit (direction confirmed 7/11, N-gated) routes through the 0028/#332
classifier machinery when it clears N≥15 — never a bespoke bump. Already noted on #357's line;
recorded here so the 0028 build reserves the input.

---

**Meta:** one true design-vs-evidence conflict (R1) — found because the probes ran BEFORE the
build phase; the sweep's purpose worked. Build-order constraints extracted: **#445 → before
0026-C3/0027-C3/0031-C3** (R4) · reclaim generalization rides the first of 0026-C3/0027-C3 (R3)
· 0025 precedes #452-quality (R5). No line blocks Sunday's T5/T6.
