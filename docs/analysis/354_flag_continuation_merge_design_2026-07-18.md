# #354 — flag_continuation → Confirm entry (b) of the consolidation play: merge design (2026-07-18)

**Status:** DESIGN — reconciliation + remaining-scope card for the already-signed merge.
**Signed basis:** ADR 0013 §2 (operator 6/16-17) · **ADR 0026 D1+D3 SIGNED at the 7/12 sitting**
(`docs/analysis/lane1_sitting_pack_2026-07-13.md` §B2; **D2 PARKED** — premise reversed by the #146
probe, reopens only with a faithful harness, Block 4 T3) · the 7/14 shadow-fix pack §3
(`docs/analysis/327_shadow_fix_proposal_2026-07-14.md`, operator-signed — the Confirm re-wire).
**THE LINE:** no code or live-param change ships from this doc; every flip below names its operator
gate. All of Family A is shadow/no-money today (audit in §5).

---

## 0. What changed since the original 6/22 card (read this first)

The 6/22 #354 card described a merge of a *stale-param* flag_continuation into the consolidation
play. Two later, operator-signed events already executed most of it — this doc reconciles the papers
to the machinery and names the strictly-remaining scope:

1. **The 6/27 HTF rebuild** (`docs/setups/htf.md`) replaced flag_continuation's stale n=1 params
   (runup 50%/60d, proximity ≤20% + #80 scaling) with the SOURCED HTF spec (90%/40d, ≤25%
   absolute-low depth, Stage-2 trend gates). The stale values **no longer exist in code**. Per ADR
   0026 D1: *"HTF-class keeps its sourced 90/40 — HTF is the setup, Confirm is the entry."* So the
   merge involves **zero param edits to `flag_detector.py`** — its params now belong to HTF (#356).
2. **The 7/14 signed re-wire** put the Confirm arm LIVE (shadow) in
   `_consolidation_readiness_job` (17:35 ET): `anticipation.confirm_signal_at` fires dual-mode
   beside Anticipate on the signed §2 universe (`scheduler.py:3474-3501`), reversing the operator's
   6/29 anticipate-only un-wire and obsoleting #404 (removal). Verified wiring comment at
   `scheduler.py:3477-3479`: *"Both modes are recorded into the ONE shadow lifecycle, tagged by
   entry_mode (#354 ADR 0013 §1 · re-wired dual-mode per the signed 7/14 proposal §3) … NOT the
   live #94 path."*
3. **The strategy row is already retired:** `mi_strategies.flag_continuation` is `phase='deprecated'`
   on prod (premortem-verified 7/11, PLAN #354 line) — 0026-D1's retire step is pre-done.

**Remaining #354 scope** = (a) ratify one wiring divergence between ADR 0026 D1 and the signed 7/14
implementation (§3 below); (b) the SSoT/identity consolidation (C4 paper-work); (c) D3 (undercut →
WATCH_UR → U&R arm) — signed but **not yet built**, carrying its own pre-flip backtest gate; (d) file
the C5 gated review (absent from `data_gated_reviews.yaml`, verified 7/18).

---

## 1. Param enumeration — flag_continuation vs the consolidation play's SIGNED model

Legend: **[HTF]** = the param survives as HTF's (sourced, untouched by this merge) · **[FAMILY]** =
the Confirm arm uses the signed family model · **[CARRIED]** = the one flag param the Confirm arm
keeps · **[GATED]** = signed, flip gated on its own backtest.

| Param | flag_continuation (stale / where it lives now) | Consolidation play SIGNED model | Ruling |
|---|---|---|---|
| **Runup gate** | 50%/60d — RETIRED 6/27; now `_RUNUP_MIN_RATIO=1.90` / `_RUNUP_LOOKBACK_DAYS=40` (`flag_detector.py:64-65`) | `RUNUP_MIN=1.15` / `RUNUP_WINDOW=10` (`anticipation.py:618-619`; ADR 0013 §2.1 SIGNED — Pradeep "+15% in 10 days"; COO canary) | **[FAMILY]** for Confirm (fires off the §2 universe + coil-finder). **[HTF]** keeps 90/40 — different setup, not a conflict (ADR 0026 D1). |
| **Anchor** | pivot-walk: `_find_pivot_high` (`flag_detector.py:540-608`), `_PIVOT_HIGH_BAND=0.02` (`:39`), `_PIVOT_WALK_THRESHOLD=0.01` (`:47`) | runup-peak-close, ANCHOR-STABILITY invariant (`anticipation.py:606-611`); coil-finder `find_coil_setup` (`:687-734`) + carry-forward `select_consolidation_keys` | **[FAMILY]** — Confirm's `anchor_idx` is the coil's runup peak (`scheduler.py:3480-3482`). Pivot-walk stays **[HTF]**-internal. |
| **Tightness** | ratio gates: range/vol contraction + bodies + fresh-tightening stage math (`flag_detector.py:856-942`) | volatility-relative: `is_entry_tight` = rmv_15d ≤ `ENTRY_RMV_MAX=30` · range ≤ `ENTRY_RANGE_MAX=0.07` · vol ≤ `ENTRY_VOL_MAX=1.0`×ADV20 (`anticipation.py:860-868, 897-914`; ADR 0013 §2.4 SIGNED) | **[FAMILY]** for the family lifecycle; the stage machinery stays **[HTF]**'s display substrate. **Shared primitives stay single-source:** `_compute_rmv` (`flag_detector.py:415`) + `_compute_fresh_tightening` (`:472`) imported at `anticipation.py:24-25` — no dup, per the card. |
| **Breakout volume** | `_BREAKOUT_VOL_RATIO=1.50` (`flag_detector.py:293`) | `ENTRY_CONFIRM_VOL_MIN=1.5` (`anticipation.py:962`) | **[CARRIED]** — the one flag param the Confirm arm keeps (it IS the "confirmed breakout + volume" definition, ADR 0013 §1 table). Same value both sides — nothing to reconcile. |
| **Stop** | breakout logic: stop below base | `confirm_signal_at`: stop = base_low (`anticipation.py:981, 994-996`; ADR 0013 §1 "base / breakout low") | **[FAMILY]** — implemented as designed. |
| **0.4% tight-close** | — | `TIGHT_CLOSE_PCT=0.004` (`anticipation.py:57`) — **ranking/telemetry ONLY** (ADR 0013 §2.2: "0.4% is demoted to a ranking marker, NOT the gate" — operator veto) | **KEPT ranking-only.** Veto intact; nothing gates on it anywhere. |
| **Universe** | `get_flag_universe`: top-200 RS / rs_1m ≥ 80 / burst, $5M ADV (`flag_continuation.md:19-29`) | `get_anticipation_universe` (`db.py:7165-7175`): price ≥ $5, **median $20M/day** dollar-vol (§2.3), ≤1.0% today-compression inclusion (§2.2), CS/ADRC-only | **[FAMILY]** for Confirm — this is the load-bearing choice (§3): gating Confirm by flag/HTF-cohort membership would under-detect on exactly the §2 names (#270-phantom in miniature). Flag universe stays **[HTF]**'s. |
| **Undercut** | `close < base_low_close → INVALIDATED` (`flag_detector.py:798-801`; the card's `:513` and 0026's `:801-804` are drifted line refs, same gate) | undercut **ALLOWED** (ADR 0013 §1, operator veto of undercut-as-gate); the family coil-finder already has no undercut invalidation (hold gate = ≤50% leg retrace, `anticipation.py:795-815`) | **[GATED]** = **D3, SIGNED 7/12**: route to `WATCH_UR`, reclaim → `entry_mode='ur'` rows. NOT YET BUILT; flip gated on its own N≥10 reclaim backtest + false-revival <40% (ADR 0026 D3) + HARD-gate list review (CHANGE_PROCESS §3) — it changes the live `/flags` board's stage semantics. |
| **TRIGGERED gate** | COILED-prerequisite (`flag_detector.py:944-950`) | (D2 proposed direct TIGHTENING→TRIGGERED) | **PARKED** (7/12 sitting B2): the #146 probe showed the incumbent gate is tail-positive (+0.78R mean, +14.9R total) and the replay was only 4/21-faithful. Do not build; reopens only with the Block-4 T3 faithful harness. **Not part of this merge.** |

### The reconciliation in one breath
Confirm entry (b) = the family's SIGNED §2 model end-to-end (15%/10d runup · runup-peak-close anchor
· $20M universe · RMV/ATR volatility-relative tightness · 0.4% ranking-only) + the one carried flag
param (breakout ≥1.5×ADV20) + stop=base_low. `flag_detector.py` is edited **zero times**: its 90/40
world is HTF's (a different, sourced setup), and the two stale defects (undercut-INVALIDATED, COILED
prerequisite) resolve as D3-gated and D2-parked respectively — neither is a merge blocker.

---

## 2. One Family-A play, three arms — the shape after the merge

ONE consolidation strategy (ADR 0013 §1), entries distinguished by
`mi_consolidation_entry_shadow.entry_mode` (`db.py:1838`, CHECK at `:1873`, 3-col open-dedup index
at `:1882`), realized-R **never blended across modes** (ADR 0013 §1 "Stops, modes never blended";
the 7/12 register R2: **each entry mode earns its own N≥10**):

| Arm | Entry | Stop | Status 7/18 |
|---|---|---|---|
| **(a) Anticipate** (#327) | IN the coil, N=3 tight days post-peak (`entry_signal_at`, `anticipation.py:917-950`) | structural_low headline w/ sub-1% floor flag (7/14 pack §2); coiled_low recorded | LIVE shadow since 6/18; −1.23R N=34 June diagnostic → quality/regime flags recording, forward-validating |
| **(b) Confirm** (**this merge**) | ON the confirmed base_high breakout + ≥1.5×ADV20 volume (`confirm_signal_at`, `anticipation.py:965-998`) | base_low | LIVE shadow since the 7/14 re-wire — the tagged **control arm** (~85% of anticipated coils never broke out; Confirm is structurally shielded from paying for false coils) |
| **(c) U&R** (D3) | undercut base_low → reclaim (reuse `detect_gdl_reclaim` shape, ADR 0026 D3) | undercut low | SIGNED, **not built**; needs the WATCH_UR stage (C3), `'ur'` added to the DB CHECK (`db.py:1873`), and its own pre-flip backtest |
| — HTF (#356) | NOT an arm — its **own setup** on `flag_detector.py` (90/40, `/flags`, #94 scan) | per `htf.md` | Shadow/telemetry-only; untouched by this merge |

**flag_continuation the STRATEGY is dead** (row deprecated on prod); **flag_detector the MACHINE
lives on** as HTF's substrate + the `/flags` board + the #94 intraday scan. Regression pins (ADR
0026 D1): #94 keeps reading `mi_flag_candidates` stages · HTF keeps consuming the state machine ·
`test_execute_task_routing` freezes `/flags` routing · Confirm's own pins live in
`tests/test_consolidation_entry_signal.py:156-200` + `test_anticipation_volume_dryup.py:116`.

---

## 3. The one divergence needing a ruling — ADR 0026 D1's wiring clause vs the signed 7/14 implementation

- **ADR 0026 D1 (designed 7/11, signed 7/12)** says: *"`confirm_signal_at` fires on the EXISTING #94
  intraday flag-break event."*
- **The signed 7/14 pack §3 and the code as-deployed** do the opposite — a pure EOD detector on the
  §2 universe daily bars, *"deliberately NOT the live #94 path"* (`anticipation.py:953-961`,
  `scheduler.py:3479`).

Both are operator-signed; the 7/14 signature is later and is what runs. The 7/14 wiring is also the
better design on the merits, and post-6/27 the case is *stronger* than when 0026 was drafted:
1. **Cohort integrity** — the #94 event fires only on flag-detector-cohort names, which since 6/27
   is the *narrower* 90/40 HTF universe. Gating the family's Confirm arm by HTF membership would
   silently under-detect on exactly the §2 names we measure (the #270 phantom in miniature).
2. **Isolation** — the #94 scan is a load-bearing live alert surface; the EOD detector touches
   nothing on it.
3. **Evidence** — the #327 Phase-B replay showed intraday-first-break re-timing *de-rated* the
   consolidation edge (daily-close selection was the artifact); "confirmed breakout" = the daily
   close is the honest reading of ADR 0013 §1's "CONFIRMED breakout."

**Rec (operator ratifies):** amend ADR 0026 D1's wiring clause to record the 7/14 EOD-§2
`confirm_signal_at` wiring as the implemented Confirm arm. An intraday-confirm variant off the #94
event stays a *possible future arm* — if ever wanted, it is its own entry mode earning its own N≥10
(register R2), not a swap.

---

## 4. Migration / shadow plan (what remains, in order)

All items below are shadow/no-money (audit §5) → under the no-money-ships-full rule they ship full;
the only CHANGE_PROCESS-gated item is D3's flip (it changes a live operator surface's detection
semantics — discipline applies even with no money attached).

1. **M1 — ratify the §3 wiring amendment** (operator, one line). Then update ADR 0026's stale
   status header ("DESIGN — awaiting sign-off" → D1+D3 signed 7/12, D2 parked) in the same
   commit as the first merge-scoped code/SSoT change (SSoT-same-commit rule).
2. **M2 — C4 identity/SSoT consolidation** (paper-work + cosmetic code, one card):
   `flag_continuation.md` header → "merged into the consolidation family; entry (b); detector
   superseded by htf.md" with a CHANGE_PROCESS change-log entry (reversion-flag: the D3 entry, when
   it lands, reverses the 5/01 undercut rule — *why it was wrong, not just incomplete*: it encoded
   invalidation semantics the operator never held; the U&R evidence base was absent when written).
   Optional, operator's call: rename the `flag_continuation_scan` job id (`scheduler.py:66`, also in
   the watched-jobs list `:135`) and the `flag_continuation` adapter id (`strategies/adapters.py:277,
   308, 336`) to HTF-named ids — cosmetic; the adapter feeds telemetry surfaces only. Rec: defer
   renames to the next time those files are touched (churn > value now).
3. **M3 — file C5**, the `consolidation_unification_review` gated review (predicate: ≥10 settled
   `entry_mode='confirm'` OR `'ur'` rows; earliest +14d) — ADR 0026 §3.3's built-in go-live trigger;
   **not yet in `data_gated_reviews.yaml`** (verified 7/18). This is the dark-needs-a-trigger rule:
   the first per-mode settled-R readout drives the next promotion decision.
4. **M4 — build D3 (C3 card)**: WATCH_UR stage + base-low-reclaim → `entry_mode='ur'` shadow rows
   (extend the DB CHECK `db.py:1873` to include `'ur'`); post-reclaim returns to TIGHTENING (0026
   D3). **Flip gate before it lands on `/flags`:** the C1 reclaim-cohort backtest (reclaim-rate +
   forward R from reclaim close, stop=undercut low; ship rule: positive at N≥10 AND false-revival
   <40%) + the HARD-gate promoted/demoted name list to the operator (CHANGE_PROCESS §3).
5. **NOT in scope:** D2 (parked) · any paper/live promotion of Confirm — that is a separate money
   gate (#353, currently blocked on the #327 edge read; #395's 7/12 NO-GO on real entries stands;
   promotion would ride `entry_pipeline.submit_trade_entry` + `mi_strategies` registration, none of
   which this merge touches).

---

## 5. Live-path audit — is any of this money-touching?

**No. Every surface in this merge is shadow or operator-display; zero execution authority.**

- `mi_consolidation_entry_shadow` rows are recorder-only — the job *"RECORDS the row, never
  submits"* (`anticipation.py:923, 961`; `scheduler.py:3474` "SHADOW recorder").
- `entry_pipeline.py` and `ep_detector.py` import nothing from `anticipation.py` (re-verified
  7/18; the 6/22 isolation check holds). The consolidation play is not even a registered
  `mi_strategies` strategy (absent from `/status` — #353's build step 1).
- `flag_detector.py` is telemetry/alert-only (`htf.md`: "NO order fires from the detector") — the
  `/flags` board + #94 alerts are operator-facing but no money. D3 changes what the operator SEES
  (stage semantics on a load-bearing board), hence its CHANGE_PROCESS gate, but no order path exists.
- The `flag_continuation` mi_strategies row is deprecated; its outcome adapter feeds telemetry
  surfaces only (`adapters.py:277-337`).

Therefore: the param reconciliation + Confirm-arm merge **ships full as shadow** (no-money rule);
the only gated flip is D3 (operator surface + detection-criterion discipline), and any future
live/paper promotion is a separately-signed money gate.

---

## 6. Operator sign-offs — in hand vs outstanding

**In hand:** ADR 0013 §2 model (6/16-17) · ADR 0026 **D1+D3** (7/12 sitting; D2 parked) · the 7/14
pack §3 Confirm re-wire · `flag_continuation` row deprecation (live on prod).

**Outstanding (the asks):**
1. **Ratify the D1 wiring amendment** (§3): Confirm = the EOD §2-universe `confirm_signal_at` as
   implemented; the #94-event clause recorded as superseded. (One line; reconciles ADR to code.)
2. **D3 pre-flip gate** (when C3 is ready): the C1 reclaim-cohort backtest table + the HARD-gate
   name list (CHANGE_PROCESS §3) before WATCH_UR lands on `/flags`.
3. **C5 review filing** (M3) — approve adding the gated review (routine, but it sets the promotion
   trigger's predicate).
4. **Cosmetic renames** (M2) — do-now vs defer-to-next-touch (rec: defer).

*(Any future Confirm paper/live promotion = its own sitting, not asked here.)*
