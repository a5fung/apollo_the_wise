# ADR 0007 — Theme-engine nascent-discovery fix

**Date**: 2026-05-31
**Status**: **DESIGN** (build gated). Design produced 2026-05-31 on operator direction ("do it now"). Build is gated on: advisor sign-off + SSoT/CHANGE_PROCESS + read-only replay validating against BOTH the drone and software-AI cohorts + the anti-noise check below. **Decoupled from the 6/22 trading cutover** — this is a standalone-intelligence (evening brief) product defect, not the order path.
**Authors**: Apollo Assistant (with operator direction 2026-05-31)
**Relates**: `data_gated_reviews.yaml::theme_engine_narrative_blindness` (the pinned mechanism); ADR 0006 (catalyst-discovery loop — the cross-ticker narrative layer, of which vector (e) here is the minimal seed).

## 1. Context — the pinned mechanism

Read-only prod trace of the 5/28 drone ignition (UMAC rank 933→50→23 over 5/26–5/29, ONDS 2772→412, RCAT 3751→1619, SWMR 165→57; `rs_1m` 95–100 / `rs_6m` ~0 = textbook nascent) confirmed the engine **never received the igniting cohort at discovery**. Three gates, all keyed to *already-established* status:

1. **Candidate selection is RS-rank-capped.** `uncovered = leaders[:40]` (`theme_engine.py:3239`). On 5/28 **zero** drone names cleared the top-40 (best UMAC 50, SWMR 57). The velocity (`get_rs_velocity` min_rs=50, top-30) and turners (`get_rs_turners`, "was rs≤30 four weeks ago", top-30) pools have shapes the igniting leaders didn't fit (UMAC was `rs_composite` 76 four days earlier, not ≤30).
2. **Stale Fading fragments "cover" the laggards.** Two 2-member fragments — `{KYTX,SWMR}` (Fading, score 1.1) and `{ISSC,KTOS}` (Fading, score 0) — and `covered_tickers` includes **all** stages incl. Fading (`theme_engine.py:3207-3210`), so those members are stripped from every discovery pool. The stub both *blocks* the real theme and decays.
3. **Correlation pre-pass is blind to nascent.** 0 drone clusters on 5/28 (14–19 existed) — the ≥0.85 / 20-day / ≥4-member bar (`correlation_engine.py:26-28`) only fires on *established* tight co-movement.

The names were caught individually (RCAT EP HIGH 101, AVAV 72, UMAC 9M +32.8%) — only the **theme** was missed. Plus a confirmed **lifecycle-inversion** bug: "Fading" while member `rs_1m=100`.

**Net:** the engine structurally surfaces the obvious and misses the nascent — the inverse of its purpose as a discovery-edge tool.

## 2. Design — five vectors

### (a) Add a rank-acceleration candidate pool to discovery
**Why:** nascent names are mid-pack on *absolute* RS by definition; their signal is *acceleration*. UMAC 933→23 in 3 days is invisible to a top-40 absolute gate.
**Design:** new `db.get_rs_accelerators(today, lookback_days, ...)` — stocks whose `rs_rank` / `rs_composite` improved sharply over a short lookback. Add to the `asyncio.gather` at `theme_engine.py:3126`, filter out `covered_tickers` + `globally_banned`, feed into `_discover_new_themes` as a peer pool to velocity/turners; cap by acceleration to bound cost.
**All thresholds (lookback, rank-improvement, current-RS floor, cap) are OUTPUTS of the §4 replay — NOT pre-committed.** Worked example of why a static RS floor fails: on 5/28 **RCAT's `rs_composite` was 59.4** — excluded by any `≥60` floor — yet it fired an EP HIGH (101) and got an ORB order the same day. RCAT also improved ~2,100 rank places in 2 days (passes a rank test but fails a 60-floor), so the two sub-criteria **conflict on the live case** → the replay must tune them jointly and likely **OR-combine** (rank-acceleration OR RS-level), not AND.
**Touchpoints:** `db.py` (new query off `mi_stock_scores` self-join on a prior `score_date`), `theme_engine.py:3126` + `:3260-3265` + the `has_enough` / `_discover_new_themes` call.

### (a2) Recovery-slope selector — a DISTINCT signal (replay-discovered 2026-05-31)
**Why:** the §4 step-1 replay showed the software-AI cohort is **not** a rank-acceleration cohort. Its members are either already-established (CRWD/DDOG/PANW/FTNT: `rs_6m` 93–97 — not accelerating) or recovering (NOW `rs_1m`97/`rs_6m`33, ESTC 95/28, TEAM 92/17, MDB 88/20). The unifying *price* signal is **`rs_1m` ≫ `rs_6m`** (re-rating off a low base), not a rank delta. So discovery needs a **second nascent selector** — a recovery-slope pool (high `rs_1m`, low `rs_6m`, liquid) — alongside (a1) rank-acceleration. The already-established members (high `rs_6m`) come from **no** price selector at all — they need narrative/theme-membership (vector (e) / ADR-0006). **Two cohorts, two different signals; (a) is really (a1)+(a2).**

### (b) Don't let stale Fading fragments block igniting leaders — revive/absorb
**Why:** the laggards being "covered" by a decaying stub removed them from discovery; the leaders couldn't merge in.
**Design:** in `_rescore_existing_theme`, if a Fading theme's members show renewed momentum (member `rs_1m` surge or rank-acceleration over threshold), **re-promote** it (Fading→Nascent/Accelerating) instead of letting it decay — and allow the accelerating uncovered leaders to be assigned into it (the existing `_assign_uncovered_to_themes` path) rather than being blocked. Keep the `revalidated_out` exclusion intact (don't re-admit validation-removed tickers).
**Oscillation guard (required — this codebase has documented fade→revive scars: parabolic ship→revert→restore, theme bans):** the re-promote must use hysteresis — a one-way latch or cooldown (e.g. re-promote at most once per N trading days, and only on a momentum margin clearly *above* the fade threshold) so it cannot fade→revive→fade loop.
**Churn interaction:** loosening the covered-incl-Fading exclusion interacts with existing constituent churn — the 5/27 audit showed `theme_constituent_churn` 19 high-churn pairs incl. SWMR/KYTX; §4.4 must confirm revive does not amplify it.
This is the "absorb/revive" path and also fixes (d).
**Touchpoints:** `_rescore_existing_theme` (lifecycle stage decision), the `covered_tickers` construction (`:3207-3210`) — narrow so a *re-accelerating* Fading theme doesn't permanently fence its members.

### (c) Enrich sector for ALL discovery candidates, not just `leaders[:60]`
**Why:** `_enrich_sector` (`theme_engine.py:3139-3144`) runs only on `leaders` (top-60). ONDS/RCAT/AVAV (ranks 412/1619/1433 on 5/28) were below top-60 → stayed `(blank)` → unclusterable.
**Design:** run sector enrichment over the union of all candidate pools (uncovered + velocity + turners + accelerators) via the persistent `mi_ticker_overrides` cache + `_get_sector` fallback (cheap, cached). **Necessary-not-sufficient** — it removes blindness, but a cross-sector theme still won't group by sector alone; that needs (e).
**Touchpoints:** `theme_engine.py:3139-3144` (widen the enrichment set).

### (d) Fix the lifecycle-inversion bug
**Why:** a theme at `rs_1m=100` member momentum was labeled Fading (score 1.1).
**Design:** stage must be driven by member RS momentum, not only score-decay/recency. Folded into (b)'s re-promote rule: surging members ⇒ cannot be Fading.

### (e) Nascent cohort signal (co-gap / co-acceleration) — minimal ADR-0006 seed
**Why:** the correlation pre-pass only sees established clusters. The drone cohort co-accelerated and co-gapped without yet being 0.85-correlated.
**Design:** a sector-agnostic cohort detector — names that (i) co-gapped same-day (join `mi_ep_alerts` by date) OR (ii) co-accelerated in rank over N days — surfaced as candidate cohorts to the existing `_discover_new_themes` prompt (same slot correlation clusters use today, `theme_engine.py:2453-2473`). This is the minimal nascent-sensitive complement; the full LLM narrative-synthesis + investigator/advisor version is ADR-0006 (C2/C3).

### (c2) Fetch descriptions for new candidates (assembly trap 3 — replay-confirmed 2026-05-31)
`_discover_new_themes` hard-drops any candidate with no `TICKER_DESC` (theme_engine.py:2356). Prod: RCAT/AVAV have no description row, ONDS's is blank — so even after (a) selects them they'd be dropped before grouping. Fix: trigger `_ensure_descriptions` for the new accelerator/recovery candidates (as it already does for `leaders`).

### (f) Ignition-aware discovery prompt (grouping trap 4 — replay-found 2026-05-31)
Step-2 replay: the LLM groups cross-sector fine but drops igniting members whose *composite* RS lags (RCAT/AVAV flip out, KTOS dropped). Fix: surface the ignition signal (rank-acceleration / today's gap) in the candidate lines and tell discovery that a nascent theme legitimately includes recently-igniting members whose composite RS hasn't caught up. Cheap prompt change — no new subsystem. This is the grouping-stage twin of the selection-stage rank bias (a).

## 3. The anti-noise principle (load-bearing)
Raising sensitivity (lower rank bar, looser cohort signal) **will** surface more candidates — and a discovery tool that floods the evening brief with spurious themes is *worse* than one that misses some. So every newly-surfaced candidate/cohort must still pass:
- the existing **LLM thesis-grounding** ("if the reason is unclear, do NOT force a theme — leave uncovered", `theme_engine.py:2472-2473`), and
- the existing **theme validation** (`_validate_theme_membership`, Haiku member-fit) + the 2-member coherence guard (#125/#126).

The sensitivity change is in *candidate selection*; the precision guard stays in *theme formation/validation*. That split is the whole design.

## 4. Validation plan (read-only, before any build)

**STEP 1 RUN 2026-05-31 (read-only, drone + software):**
- **Drone recall ✓** via rank-acceleration: ONDS +2360, RCAT +2132, AVAV +1230, UMAC +883 ranks over 5/26→5/28 (KYTX/ISSC, the dead laggards, did NOT accelerate — the signal cleanly separates leaders from the Fading-fragment dead weight). RCAT at `rs_composite` **59.4** confirms the floor must be ≤50 / OR-combined (a ≥60 floor drops it).
- **Software needs (a2):** rank-acceleration does NOT catch the software cohort (its established members CRWD/DDOG/PANW/FTNT aren't accelerating; NOW/ESTC/TEAM/MDB show the recovery slope). → added vector (a2).
- **Anti-noise:** the `impr≥800 ∧ rs≥50 ∧ liquid` set = **84 names** (strong-bull window, regime-dependent; `impr≥1200 ∧ rs≥50` = 42), but only ~2 are drones — **selection RECALLS but does NOT ISOLATE.** The cohesion signal (e / co-movement) + the LLM grouping step do the isolation, NOT the candidate filter. So (a) is necessary-not-sufficient and the grouping leg (step 2) is the real crux. `impr≥800 OR rs≥80` = 520 (floods — a naive OR with an absolute-RS arm is wrong).
**STEP 2 RUN 2026-05-31 (isolated grouping test — real prompt + tool + Sonnet, faithful descriptions; `scripts/_replay_theme_discovery_grouping.py`):** fed the 6 drone leaders (cross-sector Tech+Industrials) + 10 unrelated bull-bounce accelerators to the REAL discovery prompt/tool/model.
- **Cross-sector grouping WORKS:** Sonnet formed ONE "Military & Defense Autonomous Drone Systems" theme across Tech+Industrials by business driver and left the noise (KSS/DLTR/HOOD/RDDT/ICLR/AMPX…) uncovered. **Candidate #2 (LLM fragments by sector) is NOT the failure mode** — once ASSEMBLED, the LLM groups correctly and rejects noise. (It also surfaced UPST/QFIN as a plausible AI-consumer-credit nascent cluster — a reasonable real find.)
- **ASSEMBLY TRAP 3 (description gate) confirmed:** prod check — RCAT/AVAV have NO `mi_ticker_overrides` description row and ONDS's is blank; `_discover_new_themes` hard-drops no-description candidates (theme_engine.py:2356). So even after (a) selects them, they'd be dropped pre-grouping → new vector (c2).
- **GROUPING TRAP 4 found:** the prompt's "RS LEADER / what the market is pricing as leaders" framing makes Sonnet drop igniting-but-low-COMPOSITE-RS members. Across two runs RCAT/AVAV (rs_composite 59/64 — but EP-HIGH-firing +16%/+10% gaps on 5/28) flipped IN/OUT; KTOS (rs 33) consistently dropped. The PARTIAL theme excludes exactly the names we traded (RCAT EP HIGH 101). Root cause: composite RS (1/3/6-mo blend) LAGS the intraday ignition and the prompt defers to it → new vector (f).
- **SCOPE-REDUCING:** the heavy ADR-0006 narrative layer is NOT required for the drone case — the existing LLM groups cross-sector fine. Drone fix = ASSEMBLY (a/b/c + (c2) description-fetch) + (f) ignition-aware prompt. (Software-AI re-rating may still need the narrative layer — its members are established, not igniting.)
- **Caveat:** isolated test (forced report_themes, hand-built pool, supplied RCAT/AVAV/ONDS descriptions); run-to-run variance real → directional, not definitive. Full-pipeline run + steps 3–4 (lifecycle/oscillation) NOT yet run.

1. **Recall replay (selection):** ✅ done (above). Re-run the proposed candidate selection against stored `mi_stock_scores` for both windows. Pass = both cohorts' leaders **enter the candidate set**. This leg *sets* the (a1)/(a2) thresholds — they are its output, not its input.
2. **End-to-end grouping — the leg that actually answers Q1:** feed those candidates through the **real `_discover_new_themes` prompt** and assert **a single cross-sector theme forms** (drone: UMAC/ONDS/RCAT/AVAV/SWMR/KTOS spanning Tech/Industrials/Healthcare/blank; software-AI likewise). Selection (a)+(c) fixes *entry*, not *grouping*: if the LLM still splits by sector that's **candidate #2** (previously parked as residual) — this leg converts it into pass/fail. If it fragments, vector (e) / the ADR-0006 narrative pass is **required**, not optional.
3. **Anti-noise / precision check — measured at the RIGHT stage:** count **themes FORMED + validated** (post LLM-thesis-grounding, post `_validate_theme_membership`), NOT candidates surfaced. Operator-visible noise is themes in the brief, not candidates entered; counting candidates overcounts noise and tempts over-tightening selection (which reintroduces the recall miss). A large jump in *validated themes/day* vs today = real noise → tighten.
4. **Lifecycle / oscillation check:** confirm the (b) revive rule re-promotes the drone fragments given member `rs_1m` on 5/28 **without** oscillating (run across several consecutive days) or reviving genuinely-dead themes, and **without amplifying** the existing constituent churn.

## 5. Sequencing (smallest-viable first)
- **(c) blank-sector enrichment of all candidates** — smallest, lowest-risk, near-isolated; ship first.
- **(a) rank-acceleration pool** — the core recall fix; ship after the §4 anti-noise replay passes.
- **(b)+(d) Fading revive / lifecycle-from-momentum** — medium; pairs together.
- **(e) co-gap/co-acceleration cohort signal** — overlaps ADR-0006; the minimal version here, full version there.

## 6. Discipline / gates (build, not design)
Per `feedback_methodology_fidelity_over_stability` + `feedback_sample_size_discipline` + CLAUDE.md Trading-Setup-Changes: advisor sign-off, SSoT update (CLAUDE.md Theme Engine section / this ADR), and the §4 replay green against **both** cohorts before any code ships. Shadow/observe before it changes what the operator sees in the brief. **Design is done now; build ships when §4 passes.**

## 7. Cross-references
- `data_gated_reviews.yaml::theme_engine_narrative_blindness` — pinned mechanism + the five vectors as review fix-vectors; `earliest_review_date` pulled to 2026-06-01.
- ADR 0006 — catalyst-discovery loop; vector (e) is its minimal seed, the full narrative synthesis is there.
- `correlation_engine.py:24-28` — the established-only thresholds (e) complements.
- `theme_engine.py:3126` (pool gather), `:3239` (top-40 uncovered), `:3207-3210` (covered incl. Fading), `:3139-3144` (sector enrichment), `:2453-2473` (discovery prompt cohort slot).
