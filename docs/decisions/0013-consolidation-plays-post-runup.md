# ADR 0013 — Consolidation plays post a runup (Family A) + deletion of the #270 +40% phantom

**Status:** §2 **SIGNED** (operator, 2026-06-16/17 — "approved … and signed off"). **Phase 1 BUILT**
2026-06-17 (SHADOW recorder — new `mi_anticipation_consolidation` table + `evaluate_consolidation` +
the paused `_consolidation_readiness_job`); jobs stay PAUSED until the anchor-stability invariant is
verified live (see §4 Phase 1). Phases 2–5 described, not committed. The immediate contamination-stop
(both gap-anchored shadow jobs un-registered) shipped 2026-06-16.
**Date:** 2026-06-16 (created); 2026-06-17 (§2 signed + Phase 1 built).
**Driver:** operator reset of #270 after catching a phantom criterion; relayed Gemini review folded in.
**Source of truth for every threshold here:** `docs/methodology/operator_shared_notes.md` (the verbatim
Pradeep Bonde thread + the 6/16 verification probes). **Provenance rule (this ADR's core discipline):**
every cohort-shaping criterion must cite a source in that file; a number with no source may record
telemetry but may NOT gate or shape the cohort, shadow or not.
**Enforcement (2026-07-17, #358):** this rule is now MECHANICAL, not prose — `scripts/
gate_provenance_registry.py` (the enumerated, extensible Family-A/detection gate list) +
`scripts/check_gate_provenance.py` (STALE/DRIFT always hard-fail; UNCITED is a ratchet — a NEW
uncited gate fails the commit, legacy ones are tracked, named debt in `scripts/
gate_provenance_baseline.json`), wired into `.githooks/pre-commit` (Gate 5) + `tests/
test_gate_provenance.py`. First-pass enforcement found 3 currently-uncited cohort gates (operator
findings, NOT fixed by this build — THE LINE): `db.get_anticipation_universe`'s `dvol_min=$20M`
(this ADR's own §2.3 already flags it "sign off the exact number"), `flag_detector.
_HTF_MIN_ADR_PCT=0.04` (code comment admits "NOT canonical"), and `ep_detector.MAX_EXTENSION_PCT
=50.0` (no source ties the "50% in 5 days" form to a methodology thread — the SSoT documents a
different extension rule entirely, `prev_close ≤ 1.50×SMA-10` — worth a look at which is live).
Honest limit: this catches MISSING/broken/stale citations, not semantic drift (a citation can be
present and resolve yet still describe the wrong conclusion) — it forces the human checkpoint, not
a substitute for reading what the source actually says.
**Tasks:** #12 (re-scoped to "Family A consolidation rebuild"); #15 folds into Phase 2; new FAMILY-B task.
**Supersedes:** the #270 "anticipation" universe gate (`anticipation.GAP=0.40` /
`db.get_anticipation_gap_seeds` `close ≥ 1.40·prev_close`) and the undercut-required ARMED gate.

---

## Context — what broke (root-caused 2026-06-16)

#270 "anticipation" gated its universe on a **+40% one-day gap** (`anticipation.GAP=0.40`;
`db.get_anticipation_gap_seeds`: `close ≥ 1.40·prev_close AND volume ≥ 3·adv20 AND close ≥ $5 AND
dollar_vol ≥ $20M`). That +40% number was **reverse-engineered from ONE stock** — commit `37a5b63`'s
own comment reads *"MNTS was +110%"*. It was never the operator's methodology, was never surfaced in
plain words for sign-off, **survived a module rename**, and additionally hard-gated the ARMED state on a
gap-low **undercut** (one shape treated as a requirement). It is a **phantom**: a self-picked
"pending-calibration" default that silently shaped the entire cohort.

Two compounding failures made it worse than a bad guess:
1. **Transparency.** A load-bearing universe gate lived as a buried constant labeled "default pending
   calibration" and was never put to the operator in plain terms. → fix: the provenance rule above +
   §2 states every gate in plain words.
2. **Diagnosed, then ignored.** On 6/15 (commit `6c6afee`) we documented in writing that the +40% seed
   catches **none** of Pradeep's 5 example picks, and that the fix was a loose post-runup universe +
   ranking. It was filed as an "open fork" (#15) and the readiness job shipped the +40% seed anyway.

**MNTS was MISCONSTRUED, not a bad example.** MNTS is a legitimate instance of the setup — it KEEPS its
place as a validation case the corrected definition must still admit. The error was extracting its gap
**magnitude** (+110%) instead of its **shape** (run-up → tighten → enter at the tight spot). MNTS is in
fact a *delayed-EP* (there is an EP, then a valid later entry) — i.e. it belongs to **Family B**, not the
generic Family-A core. Anchoring a whole entry methodology on one stock at one point in time is the
reasoning failure this ADR exists to prevent.

## The reconception (operator)

> **"Anticipation = entry at a tight spot after a run-up."** And more generally, **all of these are
> "consolidation plays post a runup" (FAMILY A)**: runup → consolidation (tight coil) → entry.

They **share ONE universe and ONE coil detection** (undercut ALLOWED — it is one shape among several, not
a requirement). They differ ONLY by **when you enter** — the entry mode. The EP-required setups
(delayed-EP, fishhook, MAGNA53, 9M) are a **separate family (FAMILY B)**, the next rework, out of scope.

---

## 1. Decision — the architecture

### Family A taxonomy
**"Consolidation plays post a runup."** Shared substrate + three entry modes. EP is NOT required for
Family A (an EP run-up is just one way the run-up can happen — that subset is Family B's delayed-EP).

### Shared substrate (built once, reused by all three modes)
- **Universe:** post-run-up, then liquidity, then a today-compression qualifier → a SHORTLIST surfaced
  for operator judgment (NOT an auto-selected top-N). See §2 for the exact, sourced thresholds.
- **Coil detection:** volatility-relative tightness (ATR-normalized + RMV), **undercut ALLOWED**. Reuse
  `flag_detector._compute_rmv`, `_compute_fresh_tightening`, `_atr_14` (already adapted via
  `anticipation.compute_fresh_tightening` / `bars_to_ft_rows`).

### The three entry modes (differ ONLY by WHEN you enter)
**STATUS (operator 2026-08-09 — "stop the shadow, we have data but don't kill the setup"):** the
live shadow now generates **CONFIRM ONLY**. Anticipate is PARKED, not deleted — `de.entry_signal_at`
itself stays defined + tested; the fire call in `scheduler.py::_consolidation_readiness_scan` was
removed, and the comment left at that spot carries the full provenance (git history has the exact
removed block, same as the 6/29 Confirm un-wire it mirrors). See the 2026-08-09 change-log entry
below for the evidence. **Reversion**: re-add the anticipate fire block in
`_consolidation_readiness_scan` from git history — needs an operator ruling, not a fresh
CHANGE_PROCESS N≥10 backtest (detection criteria are not changing, only whether the write happens).

**Prior state (superseded by the row above):** Confirm was UN-WIRED 6/29 (a 2nd entry mode then
muddied the Anticipate-only measurement) and RE-WIRED 2026-07-14 (#327 shadow-fix pack, operator-
signed) as a control arm — that re-wire was never reflected in this table until now (found while
parking Anticipate 2026-08-09; this doc had been stale on that point for 3+ weeks). U&R was never
wired.

| Mode | When you enter | Stop | Wired? |
|---|---|---|---|
| **Anticipate** | IN the coil, BEFORE the break | tight-range low | ❌ PARKED 2026-08-09 (data-gathering done; entry/exit dig comes after HTF) |
| **Confirm / flag** | on the CONFIRMED breakout (base_high + volume) | base / breakout low | ✅ LIVE (control arm, re-wired 7/14) |
| **U&R** (undercut & rally) | undercut the base low → reclaim it | undercut low (tightest → biggest cushion: the "U&R paradox") | ❌ never wired (concept) |

### U&R is a GENERIC mechanic, not a Family-A-owned setup
U&R = "price falls below some reference level, then reclaims it." Here the reference is the base low.
The **same mechanic is reusable across families** — e.g. Family B's delayed-EP can undercut the **EP low**
then reclaim. So U&R is implemented as a reusable mechanic (reuse `anticipation.detect_gdl_reclaim` +
the `fishhook_detector` reclaim state machine), parameterized by the reference level — not hard-bound to
the base low.

### Stops, modes never blended
Realized-R is tagged by entry mode and **never blended** — each mode is evaluated on its own cohort.

---

## 2. Criteria to ratify (sign-off REQUIRED before Phase 1) — stated in plain words

Each line cites its source. Gemini-reviewed defaults are marked. **Nothing below gates anything until the
operator signs off on this section.**

1. **Run-up gate = `MAX(close) / MIN(close) ≥ 1.15` over a rolling 10-session window.**
   Source: Pradeep thread — *"+15% in 10 days or less"* (`operator_shared_notes.md`). Gemini ruling:
   lock at 15% as the **wide-net baseline**; bigger thrusts surface via tightness/RMV ranking, not by
   raising this floor. **COO-on-border (its leg was exactly 15.0%) → IN.** This is the **canary**: the
   Phase-1 re-run MUST show COO in the universe; if it drops, the operationalization is wrong, not COO.
   (Two 6/16 probes measured "+15%/≤10d" differently — per-ticker best ≤10-bar return vs. funnel `LAG 10`
   in a 20-cal-day window. Lock the exact window/measurement HERE so it reproduces.)

2. **Today-compression (inclusion gate) = `|close %chg today| ≤ 1.0%`** → ~153 names.
   Source: Pradeep "series of tight days." Gemini ruling: cast the **wide** net at ≤1.0%; **0.4% is
   demoted to a ranking / "ideal-tight" marker, NOT the gate.** (Funnel 6/16: 1478 → 751 at ≥$20M/day →
   **153** at ≤1.0% / 64 at ≤0.4%.) Was leaning Pradeep-strict 0.4%; loosened on review.

3. **Liquidity floor** ≈ ≥$20M/day dollar-volume (probe value). Source: sanity floor, not a selection
   edge — sign off the exact number.

4. **Tightness = volatility-relative** (ATR-normalized + RMV). The ≤0.4% tight-close streak is a
   **ranking input, not a gate.** Source: 6/16 probe (absolute tightness is meaningless across names of
   different ATR; must be relative to the stock's own character).
   **HONEST LIMIT — ranking stays ordering-only:** the 6/16 probe showed tightness-ranking does NOT sort
   the known-good picks to the top (ALHC ranked dead-last; APPS/NTAP top-8%). Gemini suggested leaning on
   RMV/tightness to "surface the best ones"; the operator decides. Until a backtest proves ranking sorts
   winners up, ranking is **cosmetic ordering only** — it is NOT asserted as a selection mechanism.

5. **The deliverable is a SHORTLIST surfaced for operator judgment, not an auto-selected top-N.** Source:
   Pradeep narrows the watchlist by discretion / buzz, not a single mechanical score.

6. **Linearity note (discretionary, NOT coded yet).** Prefer an orderly / linear run-up (an
   institutional "march") over a single chaotic high-volume day. Source: Gemini review + methodology.
   Surface enough of the run-up shape for operator review; defer any coded linearity filter to a later,
   separately-justified change.

---

## 3. Immediate action (SHIPPED 2026-06-16, NOT sign-off-gated)

Pausing a contaminating shadow job is not a detection-criterion change, so it is not gated behind §2.
Both #270 Step-3 shadow jobs — `_anticipation_readiness_job` (17:35 ET) and `_anticipation_3b_job`
(16:20 ET) — were UN-REGISTERED in `scheduler.py` (the `add_job` blocks commented out, the job functions
left defined). They were writing `mi_anticipation_lifecycle` rows off the phantom universe nightly. The
IDs stay in `INTELLIGENCE_OWNED_JOB_IDS` (the partition guard is one-directional: a
classified-but-unregistered id is harmless), so Phase 1 re-registration is a one-block uncomment.
Deployed via `deploy.sh market-agent`. Verify: no new `anticipation_readiness` / `anticipation_3b` rows
in `mi_job_runs` after the deploy.

---

## 4. Phases 1–5

### Phase 1 — BUILT 2026-06-17 (SHADOW recorder; jobs PAUSED pending anchor-stability verify)

Two architectural corrections from the advisor (6/17) re-shaped the literal plan; §2 criteria are
**unchanged** (this is implementation, not methodology):

1. **`replay()` is the gap-anchored FAMILY-B machine — left UNTOUCHED.** The plan's "delete
   `GAP=0.40` + the undercut gate in `replay()`" was incoherent: `replay()` / `evaluate_candidate` /
   `mi_anticipation_lifecycle` ARE the gap→undercut→reclaim delayed-EP machine the golden test pins.
   That machine + its phantom rows now belong to **#297 (Family B)** to reclaim. Family A gets a
   **NEW, separate** lifecycle — not a re-key of the shared gap-anchored table (its columns are
   runup+coil, not gap-sense; nothing is shared but the tightness primitives).
2. **The HARD-DELETE is DECOUPLED from Phase 1.** The phantom `mi_anticipation_lifecycle` rows are
   #297's to archive/clean (prefer archive over delete — look-before-you-delete). Phase 1 does NOT
   touch that table; it writes only the new one. No destructive prod op gates this build.

**What Phase 1 actually shipped (all SHADOW, all PAUSED):**
- `db.get_anticipation_universe(scan_date)` — the signed §2 universe proposer (`MAX/MIN ≥ 1.15` over a
  rolling 10-session window, best over last 12 · `last_close ≥ $5` · `dvol_med ≥ $20M` · `|today %chg|
  ≤ 1.0%`). Emits the **ABSOLUTE anchor** = earliest date of the MAX close in the last 15 sessions
  (deterministic on ties → a scan-stable key).
- `anticipation.evaluate_consolidation(bars, anchor_date)` — pure: re-confirms the runup over the
  anchor-ending window (the authoritative COO canary gate), records the coil/tightness telemetry
  (reusing `compute_fresh_tightening` / `compute_rmv` / `tight_close_streak`, NOT the gap-anchored
  `detect_pullback_shape`), states `coiled | post_runup | aged`. **Scope = the RECORDER + the
  shortlist; the 3 entry modes + realized-R settlement are deferred** (the signed deliverable is the
  shortlist for judgment; tightness is ordering-only).
- `anticipation.select_consolidation_keys` — the CARRY-FORWARD: unions the fresh §2 proposer with
  existing non-aged rows so a base's anchor stays its ORIGINAL key when the rolling window drifts (a
  lesser-peak re-anchor is carried; only a new higher high seeds a new leg). The fix for the 7/71
  live drift below.
- `mi_anticipation_consolidation` (new table, PK `(ticker, anchor_date)`) + `upsert_consolidation` +
  `get_consolidation_state_map` (carries `runup_high`/`dvol_med` for the carry-forward) +
  `get_consolidation_board`.
- `_consolidation_readiness_job` (17:35 ET, seed∪live union via `select_consolidation_keys`) —
  written, **un-registered (paused)**.
- Tests: `tests/test_anticipation_consolidation.py` (runup canary · the absolute-anchor invariance
  property · states · Family-A-shapes-never-gap-undercut). The Family-B golden test stays green.

**Boundary discipline (advisor 6/17):** §2 membership stays EXACTLY as signed (the rolling MAX/MIN
universe gate). Key-stability is a SEPARATE job-layer concern — the carry-forward changes WHICH
`(ticker, anchor)` the job evaluates, not WHAT qualifies. It is implementation / inform-and-proceed,
not a re-sign; the stability fix does not leak into the gate.

**The anchor-drift trap — FOUND live, FIXED, and proven (6/17).** The 6/17 probe run showed the
rolling-window anchor drifts for **7/71** names in a single day (6/15→6/16), all off the aging-out
`2026-05-26` peak: when the true peak ages out of the 15-session window the anchor jumps to a lesser
peak → a duplicate lifecycle row for the SAME leg. Fix = `anticipation.select_consolidation_keys`
(CARRY-FORWARD): the job unions the fresh §2 proposer with existing non-aged rows (mirrors Family-B's
seed∪live union) and keeps a base's ORIGINAL anchor unless today's runup_high is a genuinely new
higher high (a new leg). Proven on the REAL two snapshots in
`tests/test_anticipation_consolidation.py::test_carry_forward_absorbs_real_615_to_616_drift` (all 7
carry their original anchor, exactly one key each — no duplicate). The proposer-vs-confirmer
cross-check also PASSED clean (COO IN on the pure gate at 1.153; zero divergence).

**THE GATE before un-pausing.** (a) The carry-forward unit test green (real-snapshot fixture
`scripts/_familyA_drift_snapshots.json`); (b) `scripts/probes/_familyA_universe_probe.py` shows COO IN on the
PURE gate + the proposer/confirmer agree (raw SQL drift is now EXPECTED and absorbed — informational
only); (c) uncomment the `add_job` block; (d) add `consolidation_readiness` to
`INTELLIGENCE_OWNED_JOB_IDS`; (e) rewire the `/anticipation` board reader `mi_anticipation_lifecycle →
mi_anticipation_consolidation`; (f) after the first live run, confirm no ticker has two non-aged rows.
SSoT = this ADR (NOT `delayed_ep_reentry.md`, which is Family B's).
- **Phase 2 — Shared universe + coil** (reuse the flag substrate). Output = the shortlist (gates produce
  it; tightness orders it, ordering-only). All 6 known-good names already appear in `mi_flag_candidates`.
  **#15 folds in here.**
- **Phase 3 — Three entry modes, realized-R tagged by mode.** Anticipate = `anticipation` coil-close;
  Confirm = `_flag_break_scan_job` (#94); U&R = the reclaim mechanic applied to the BASE low.
  **U&R stop nuance (Gemini):** U&R can trigger INTRADAY the moment the base low is reclaimed; the stop
  respects the **new, lower intraday wick** of the undercut, not a close-based level — differentiate
  intraday-wick vs. closing undercut.
- **Phase 4 — Undercut-OK fix to the flag detector (DECOUPLED, its own live change, sequence LAST).** This
  is the ONE live-behavior change (flag_detector drives `/flags`, #94, the digest — load-bearing).
  `flag_detector.py:513` (`close_today < base_low_close` → INVALIDATED): an undercut no longer
  invalidates. **Do not merely suppress INVALIDATED — route to a NEW `WATCH_UR` state/tag** whose trigger
  is the reclaim of the base low (not the breakout of base high). **Own sign-off + N≥10 backtest**; SSoT
  `docs/setups/flag_continuation.md` in the same commit. Does NOT ride the shadow work's coattails.
- **Phase 5 — Feed Stocks in Play (ADR-0004).** Family A's ready/triggered candidates feed
  `mi_stocks_in_play` (reuse `_feed_anticipation_sip` / `stocks_in_play_sources.py`), tagged by entry
  mode. Family A is ONE input to the consolidated SiP — not SiP itself.

---

## 5. Out of scope (explicit)

**FAMILY B — the EP family (delayed-EP, fishhook, MAGNA53, 9M).** EP-required. Next, separate rework
(new #-task). Fishhook = EP-gated U&R = delayed-EP. U&R's generic mechanic (a reference-level reclaim) is
the bridge Family B reuses, but Family B's universe, gating, and stops are its own decision.
Any live / paper sizing for Family A — evidence-gated, no date. Mode stays SHADOW (no submit, no
trade-state) throughout Phases 1–5.

---

## Reuse map (search-before-build)

Tightness: `flag_detector._compute_rmv`, `_compute_fresh_tightening`, `_atr_14` (+ the `anticipation.py`
adapters). U&R: `anticipation.detect_gdl_reclaim`, the `fishhook_detector` reclaim machine. Flag-break:
`scheduler._flag_break_scan_job` (#94). Settlement: `anticipation.settle_row` / `simulate`. SiP:
`_feed_anticipation_sip`, `mi_stocks_in_play`.

## Verification (end-to-end, shadow) — claims must match the data

- **Immediate pause confirmed:** no new `anticipation_readiness` / `anticipation_3b` rows in
  `mi_job_runs` after the deploy.
- **Provenance:** every §2 gate cites a source; `grep` shows no `0.40` / `1.40·prev_close` after Phase 1.
- **Known-good = picks are IN the shortlist (NOT "rank at top"):** ALHC / APPS / HYLN / NTAP present
  as-of 6/15; **COO IN under the locked `MAX/MIN ≥ 1.15` gate (the canary)**. Reproduce the funnel
  (1478 → 751 → 153) from a captured `mi_daily_closes` fixture snapshot (data-dependent — pin it).
- **No contaminated seed:** phantom-era `mi_anticipation_lifecycle` rows hard-deleted (or archived).
- **Flag fix (Phase 4, separate):** a base_low undercut no longer flips INVALIDATED → routes to
  `WATCH_UR`; an undercut→reclaim surfaces (test a known U&R case). N≥10 backtest before deploy.
- **No trade-state touched;** preflight green; `deploy.sh market-agent`.

---

## Change log

### 2026-06-27 — RMV recalibration (min-max → ratio-to-baseline) + #327 entry gate moved to `rmv_15d`

**What & why.** The RMV tightness primitive (`flag_detector._compute_rmv`) was rewritten from min-max
normalization to the **creator-confirmed ratio-to-baseline** form (`SMA(NTR,3)/SMA(NTR,15)`, gap-aware
NTR = TR÷close, floor 0.4 / ceiling 1.5 → 0–100). The old min-max let a single wide runup bar own the
denominator, so any quiet follow-through read ~0 ("max coil") — it detected *runup exhaust*, not a coil.
The operator's labeling worksheet (`anticipation_shortlist_to_label_2026-06-22.md`) surfaced it: the
top-sorted `rmv≈0` names were all garbage (volatile/trending, no base). Root-cause confirmed by the
indicator's creator (a walkthrough the operator relayed, 6/27).

**The one gate change.** #327's **Anticipate** entry signal (`is_entry_tight` / `entry_signal_at`)
gated on `rmv_5d ≤ 40`. The ratio form only reads "contracted" against the long baseline (a 5-bar window
overlaps the recent run → ~50 for a real coil), so the gate **moved to `rmv_15d ≤ 30`** (creator's
"<30 = getting tight"). The `30` is **PROVISIONAL** — the operator's labeling pass supplies the N≥10
calibration evidence (CHANGE_PROCESS). Both `rmv_5d` and `rmv_15d` are recorded
(`mi_consolidation_entry_shadow` gains an `rmv_15d` column).

**Why no pre-deploy backtest gate.** #327 is **SHADOW** (zero execution — no paper, no live). The old
metric was *known-wrong*; keeping it stable only poisoned the shadow data the gate exists to collect.
Operator-signed 2026-06-27 ("we are not trading this setup yet … why keep something we know is wrong").
Empirical threshold calibration still comes from the labeling pass.

**Touched:** `flag_detector._compute_rmv` (+ `anticipation.compute_rmv` wrapper), `anticipation`
(`is_entry_tight` gate, `entry_signal_at`/`confirm_signal_at` record both readings), `db` (entry-shadow
`rmv_15d` column + migration + insert), `scheduler` (caller), `scripts/_anticipation_shortlist.py`
(lookback→15), `docs/methodology/primitives.md` (RMV row). Telemetry-only elsewhere — formula improved,
no gate.

### 2026-06-27 — Coil-finder SHADOW logger (#391, parallel to #327; NEW detector, no existing-gate change)

**Trigger.** The operator's 6/27 labeling pass + chart reads showed the peak-anchored base detection
(`evaluate_consolidation`, base = peak..now) swallows the post-runup *pullback* — CRWD read a 24% "band"
because its 6/01 spike + a −21% pullback sat inside the "base." The operator re-anchored the model:
**runup → pullback (any depth/shape; no fixed MA — CRWD's 20MA kiss was incidental) → coil**, with a HARD
hold gate: the consolidation must hold above the **~50% retrace of the runup leg** (give back more than half
= the runup is negated, not basing, *regardless of tightness*); tightness then *ranks* what survives.

**What ships (NEW, additive — NOT a change to the #327 gate).** A new pure detector
`anticipation.find_coil_setup(bars, i)` (runup leg → give-back `retrace` → recent-coil band/slope/adr +
full-base duration) and a daily SHADOW logger `scheduler._coil_finder_shadow_job` (17:40 ET mon-fri,
parallel to `consolidation_readiness`) that scans the signed-§2 universe, keeps coils that held
≤ `COIL_HOLD_LIMIT` (=0.50, soft / operator-tunable), and writes `mi_anticipation_coil_shadow` + one digest.
The existing #327 Anticipate/Confirm gate, `mi_consolidation_entry_shadow`, and all trade state are
**untouched**.

**Evidence.** Daily-replay validation over the prod DB (`scripts/_anticipation_coil_finder.py`,
`docs/analysis/anticipation_coil_finder_validation_2026-06-27.md`): finds all 5 operator-named coils
(GH/HNGE/CRWD/FTNT/DDOG) incl. HNGE's real May 6–28 base, and rejects GPGI (retraced 199% of its runup).
The "poor" 4 (OSCR/UAL/PTGX/TVTX) read as valid/marginal coils per the operator's chart reads — confirming
structure is a clean SCREEN, not a winner-picker (the catalyst layer selects). N=10 cohort.

**Anticipated effect.** ~1–5 rows/day to `mi_anticipation_coil_shadow` (held tight coils on the ~150-name
§2 universe); one `🔍 Coil-finder candidates` Telegram digest/day. No trade impact; no change to existing
shadow counts.

**Quality rankers deferred.** Duration (too-long) + orderliness (gappy) first cuts missed (peak-placement +
gap-vs-range definitions); they live in full-base character and need forward-shadow data, not n=5 fitting.
Recorded as ranking columns (`base_len_days`, `coil_adr_pct`) for later calibration.

**Reversion-flag:** NEW (a parallel detector; does not modify or revert any prior #327 decision).

**Status:** shipped-shadow 2026-06-27, awaiting forward-shadow validation. Operator-signed ("go", 6/27). The
~50% hold cap + the rankers calibrate against the forward stream; whether the coil-finder becomes the
load-bearing #327 gate is a *later* operator decision (CHANGE_PROCESS + N≥10 + sign-off).

**Touched:** `anticipation.find_coil_setup` (+ `COIL_*` constants), `db` (`mi_anticipation_coil_shadow`
table + `insert_anticipation_coil_shadow`), `scheduler` (`_coil_finder_shadow_job` + registration +
`INTELLIGENCE_OWNED_JOB_IDS`), `tests/test_anticipation_coil_finder.py`. Validated logic:
`scripts/_anticipation_coil_finder.py`.

### 2026-06-27 (same day) — INTEGRATED: coil-finder becomes the LIVE #327 base; old peak-anchor + the parallel shadow DELETED

**Trigger.** Operator (emphatic, 2× interrupt): do NOT run the new detector parallel to a proven-broken
one "to compare" — the old peak-anchored base is *known* broken (swallows the post-runup pullback; CRWD
read 24%), so the parallel had zero value and was garbage-hoarding. Ship the replacement in days, not weeks.

**What ships (REPLACEMENT, same day as the shadow above).** `anticipation.evaluate_coil_consolidation`
(find_coil_setup → HOLD-≤50% gate → the SAME tightness telemetry + lifecycle state, anchored on the
*corrected* coil peak) REPLACES the `de.evaluate_consolidation(bars, anchor_date)` call inside
`scheduler._consolidation_readiness_job`. The coil's peak becomes the anchor for the entry-signals
(`entry_signal_at`/`confirm_signal_at`), `upsert_consolidation`, the `🪙 Consolidation plays` digest, and
the `/anticipation` board — all UNCHANGED (only the base detector swapped; the entry-apex timing + outcome
settlement were never broken). The carry-forward key is now just the candidate seed.

**Deleted** (no garbage kept): the parallel `_coil_finder_shadow_job` + its registration + the
`INTELLIGENCE_OWNED_JOB_IDS` entry + the separate `🔍` digest; the `mi_anticipation_coil_shadow` table +
`insert_anticipation_coil_shadow`. KEPT: `find_coil_setup` + `COIL_*` (now the live base) +
`tests/test_anticipation_coil_finder.py`. The old `evaluate_consolidation` function was DELETED
(proven-broken, no live callers) along with `tests/test_anticipation_consolidation.py` and the
`scripts/_consolidation_acceptance_test.py` dual-anchor harness (both built on the broken model); the
GOOD/GARBAGE acceptance intent is covered by `tests/test_anticipation_coil_finder.py` + the validation doc.

**Anticipated effect.** ONE anticipation surface again (the `🪙` digest now reflects the corrected coils;
no second digest). The forward shadow (`mi_consolidation_entry_shadow`) entry-signals now fire off correct
bases. First run after deploy re-baselines anchors from old (buggy) keys to coil peaks — a one-time
re-key, self-heals via carry-forward.

**Reversion-flag:** REFINEMENT of the 2026-06-27 shadow entry above (parallel shadow → INTEGRATED as the
live base; old peak-anchor base detection retired). **Status:** shipped, awaiting forward shadow. #327 is
SHADOW (no trade state / money). Operator-signed the replacement.

### 2026-08-09 — Anticipate PARKED (data-gathering done; dig into entry/exit comes after HTF)

**Trigger**: operator, verbatim: *"on anticipate, let's stop the shadow, we have data but don't kill
the setup, we need to dig into it more to see what's wrong with it and where the real setup is. this
is all part of consolidation, we just need to find if there's proper entry and exit, save for later
after we complete htf."*

**Evidence**: split at 2026-07-12 (the #327 shadow-fix / Confirm re-wire point). Pre: 32 trades over
3 days, -1.23R average. Post: 92 trades over 8 days, -0.08R average — but the TYPICAL trade stayed
-0.84R with only a 29% win rate; the mean only rose because a handful of large winners pulled it. The
leg carrying ~90% of the volume never flipped sign in any way that matters. 136 settled rows is
enough to answer "does the anticipate edge exist as currently specified" (no); more fires would only
add noise to the same answer, not new evidence.

**Anticipated effect**: zero new `mi_consolidation_entry_shadow` rows with `entry_mode='anticipate'`
going forward. The ~136 already-settled rows are untouched — they ARE the evidence for the later dig.
OPEN anticipate rows already on the board still settle normally (`_run_entry_shadow_settlement` is
mode-agnostic, unchanged). Confirm (control arm) is unaffected — a separate entry mode, never part of
this ruling. Downstream checked and unaffected: the `/anticipation` board, the daily digest (its
Anticipate section simply goes empty, code untouched by design), `get_consolidation_entry_shadow_summary`
(GROUP BY handles fewer/no rows), the #521 inert-sweep check on this table (existing rows already prove
variation; freezing new anticipate writes doesn't retroactively erase that), and the row-count-drift
sweep (`consolidation_readiness`'s job-run row never reports `rows_written`, so it isn't tracked by that
sweep at all). `evaluate_narrative_themes` does NOT read this table (checked — the "theme consolidation"
it references is the unrelated theme-engine Phase-1 birth-gate concept).

**Reversion-flag**: PAUSE of the 2026-07-14 re-wire's Anticipate half (Confirm stays live) — not a
REVERSAL (the `entry_signal_at` in-coil timing logic is not judged wrong here, only parked pending the
entry/exit dig this ruling calls for) and not a DELETION (`entry_signal_at` itself stays defined +
tested; only the fire call at the scan's call site was removed — the comment left there carries the
provenance and git history has the exact removed block, the same pattern as the 6/29 Confirm un-wire
above). Re-wiring needs an operator ruling, same pattern as 6/29→7/14 — no fresh CHANGE_PROCESS N≥10 is
required to restore it, since detection criteria are not changing.

**Status**: prepared 2026-08-09 as a reviewed, NOT-YET-APPLIED patch (code + this doc + the one
scan-integration test that pinned dual-arm wiring) — held per the operator's "don't flip it yourself"
instruction pending his or the session's explicit apply. Once applied: verify-live = the next 17:35 ET
`consolidation_readiness` digest shows zero `🎯 Anticipate entry fired today` lines while `✅ Confirm
entry fired today` keeps appearing normally on nights Confirm fires.
