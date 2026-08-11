# Theme flow and the 09:31 seam — mapping (2026-08-11)

> Operator, 2026-08-11: *"what's the proper thing to do here w.r.t the themes, let's not jump the
> gun until we have full understanding of the proper flow here."*
>
> **This is a MAPPING document, not a change.** Nothing in production was modified. Every number
> below was measured against prod (`apollo-postgres`) on 2026-08-11; the query or code path is
> cited next to it. The forks in §8 are the operator's decisions — none is pre-selected.
>
> Terminology (CLAUDE.md, HARD): a theme here is a **FAMILY** — a chart condition/context that can
> host setups — never a SETUP. The only setup in this document is MAGNA53 EP (buy ORB high, stop
> ORB low). The entry-path grouping key is deliberately named `exposure_family`, never bare
> "family" (register R5) and never "setup".

---

## 1. The incident, verified against prod (2026-08-04)

All timestamps ET (prod stores UTC; ET = UTC−4 in August). Sources: `mi_ep_alerts`,
`mi_audit_log`, `mi_live_trades`, `mi_themes` (queries in Appendix A).

| ET | What happened | Source |
|---|---|---|
| 07:00:00 | PLTR HIGH alert (ep 96, gap +16.0%) · BLZE HIGH (ep 80) | `mi_ep_alerts.detected_at` |
| 08:10 / 08:20 | VOYG HIGH (ep 80, gap +17.0%) · BTDR HIGH (ep 80) | same |
| 07:04 / 07:55 | Judge-inferred intraday stubs written: "Judge: Technology" {BTDR,PLTR,TSAT} · "Judge: Industrials" {AEIS,AMRC,CAT,VOYG} — sector-binned, story split | `mi_theme_candidates_shadow.created_at` |
| 09:31:00–:11 | ORB entries: BLZE order :00.85 · BTDR :10.90 · CAT :10.91 · LIFE :11.25 · **PLTR order placed :11.263** · AEIS + ZBRA **blocked `block:max_positions: 5/5`** :11.28/.31 · **VOYG skipped :11.456 `setup:zero_range: open=high=low=$33.99`** | `mi_audit_log` (`orb_*` events) |
| 09:45 / 09:56 | AMRC and TSAT alerts detected — both `window:out_of_orb`, never entry candidates | `mi_ep_alerts`, `mi_live_trades.skip_reason` |
| 17:00:32 | Nightly theme pipeline pass 1 begins (`theme_load_state`) | `mi_audit_log` |
| **17:06:39** | **"U.S. Government/Defense Spending Surge" born** — `source='shadow_promoted'`, {PLTR,TSAT,VOYG,AMRC} — **7h35m after PLTR's fill** | `mi_themes.created_at` (id 5407) |
| 17:13:20 | Duplicate "U.S. Government/Defense Contract Surge" born, identical ticker set (§7) | `mi_themes.created_at` (id 5611) |

Confirmed context:

- **The board at entry time held NO theme containing ANY of the four.** Latest non-Retired
  snapshot per name over `theme_date` 2026-07-28→08-03 (the exact view the entry-path check
  reads, §3-R3): **0 rows** contain PLTR, TSAT, VOYG, or AMRC. Stage 2b finding "no shared
  family" was correct against its source.
- PLTR and VOYG were evaluated within the same second (09:31:11.263 vs .456). VOYG stayed out
  on a bad bar (`setup:zero_range`), not on any correlation control.
- **The incident is wider than PLTR/VOYG**: the book that morning took BLZE *and* BTDR — both
  members of the *other* same-evening co-gap theme ("AI Data Center Infrastructure Buildout"
  {BTDR,AMRC,BLZE}, promoted 17:06:39). So 3 of the 5 slots (PLTR + BLZE + BTDR) were in two
  same-session co-gap cohorts and no mechanism saw either link. The only thing that limited
  further concentration was the position cap (AEIS, ZBRA blocked 5/5).

---

## 2. Flow map — every way a theme is born or updated

Verified against code (paths+lines below) and against prod write clocks
(`mi_themes` `created_at` by source, last 14d — Appendix A Q13: `source='live'` rows land
17:04–17:14 ET, `shadow_promoted` 17:06–17:20 ET; the 17:00 cron is the trigger, writes land
minutes later).

### Writers of live `mi_themes`

| # | Path | Trigger / clock (ET) | Reads | Writes |
|---|---|---|---|---|
| W1 | **Lane-1 nightly engine** `run_theme_engine` (`theme_engine.py:6350`) | Step 5 of `_nightly_data_pull`, cron **17:00** (`scheduler.py:5064-5066`); writes land ~17:04 | RS scores, correlation clusters, existing board, seeded-pool admissions (#491 M2) | `source='live'` rows for today: rescore, assignment, discovery, merge/split, canonicalize, save |
| W2 | **Nightly auto-promote** `promote_shadow_themes` (`theme_engine.py:2237`) | Step 5d, same job, ~17:06 | `mi_theme_candidates_shadow`, last **3 days** (`_PROMOTE_WINDOW_DAYS=3`), sources on the allowlist only, **≥3 members** (`_PROMOTE_MIN_MEMBERS=3`) | `source='shadow_promoted'` rows. **← the 08-04 birth path** |
| W3 | **Operator `/promotetheme`** `promote_candidate_by_name` (`theme_engine.py:2441`) | On demand | any shadow candidate incl. non-allowlisted | `source='shadow_promoted'` row |
| W4 | **Operator `/teach`** → `seed_theme` (`agent.py:508`, `db.py:7841`) | On demand, any hour | operator input | immediate Nascent row (or ticker-union into a similar row) |

Auto-promote allowlist (`db.AUTO_PROMOTE_THEME_SOURCES`, `db.py:6506`): `shadow_v2`,
`narrative_cogap`, `rs_slope_synthesis`. Everything else (`coverage_probe`, `judge_inferred`,
`ecosystem_reactivation`, `narrative_seed`, backfills) is operator-promote-only by construction.
`resolve_auto_promote_sources` (`db.py:6526`) removes `shadow_v2` only when the birth gate is
`'on'` — it is `'observe'` in prod (below), so the full allowlist is live today.

### Candidate writers (feed W2/W3, and the judge's context — never live themes directly)

| # | Path | Trigger / clock (ET) | Input | Note |
|---|---|---|---|---|
| C1 | **Lane-2 narrative co-gap** `discover_narrative_themes` (`theme_engine.py:804`) | Step 5c, ~17:05 nightly | **TODAY's EP alerts** (`get_today_ep_alerts`, ep_score ≥ 50 + catalyst text) | The exact mechanism that linked {PLTR,TSAT,VOYG,AMRC}; runs 7.5h after the alerts it reads. ⚠ v2 REGISTRY mode is **ON in prod since 2026-08-09** (`mi_safeguard_state.lane2_grouping_v2='on'`, first `lane2_decision_record` 08-10) — the SSoT (`docs/architecture/theme_engine.md`) still says "flag OFF", stale |
| C2 | **shadow_v2 correlation lane** `run_theme_discovery_shadow` (`theme_engine.py:1175`) | Step 5b, ~17:04 nightly | RS accelerators/recovery + clusters | On the allowlist; retired only at gate mode `'on'` |
| C3 | **rs_slope_synthesis** `run_theme_synthesis` | Cron **18:05** (`scheduler.py:5727-5729`) | coordinated RS-slope cohorts, ≥3 members | On the allowlist — its rows graduate the NEXT nightly promote at the earliest |
| C4 | **judge_inferred** (#322, `judge_theme_gap.py`) | **INTRADAY**, at judge-grade time inside the EP scan | judge fire_axes on untracked tickers | The only intraday theme-shaped write in the system. Sector-binned stub names. Never auto-promotes (anti-circularity wall) |
| C5 | **ecosystem_reactivation** (#534) | 17:30 nightly (`_post_nightly_audit_job`) | ≥3 HIGH EPs in 5 sessions vs a dormant ecosystem | Seed + Telegram only; never auto-promotes. Fires ~1/66 sessions (its own derivation; E-DEF 08-04 was the one incident) |

### Gates and read-side identity (not writers)

- **Birth gate** (`theme_birth_gate`, Phase 1): prod mode **`'observe'` since 2026-07-30**
  (`mi_safeguard_state`) — records verdicts, acts on nothing. ⚠ The SSoT's Phase-1 section still
  calls `'off'` "today's production state"; stale. **Interaction that matters here**: its 08-04
  observe verdict on the promote lane was `0 birth / 3 join / 3 awaiting-2nd-sighting` — had the
  gate been `'on'`, the defense theme would NOT have been born even at 17:06; it would have waited
  for a second sighting. **The planned flip moves theme birth LATER, widening this seam by
  design.** (§8 F-E.)
- **Dashboard canonicalization** (`portfolio-app2/theme_data.py::dedup_themes` /
  `canonicalize_themes`, #553/#555): display-side cohort identity for Rank Flow/Grid etc. Reads
  snapshots, never writes `mi_themes`, runs on the dashboard, not in this loop. The
  "Spending/Contract Surge" pair is its true-duplicate regression case; the pair's ORIGIN is §7.
- `mi_theme_exclusions`: operator bans, read by validation. Not a birth/update path.

---

## 3. Every consumer that reads theme membership for a MONEY decision — and its as-of date

| # | Reader | Where | When it reads | What it reads | **As-of** |
|---|---|---|---|---|---|
| R1 | **R4 in-theme bonus** (+10 ep_score) | `ep_detector._score_ep` (`ep_detector.py:1281-1285`); set built per scan tick at `:2485-2495` | every EP scan tick (premarket → close) | `get_active_themes(stale_after_days=7)` (`db.py:7713`) — latest snapshot per name, ≤7 calendar days | **previous session's board** (nightly writes ~17:04; nothing fresher exists intraday) |
| R2 | **Holistic Grade Judge** — LOAD-BEARING: judge tier drives HIGH/MODERATE/none, i.e. whether an entry fires at all | `_resolve_grade_authority` (`ep_detector.py:385-397`); authority read `:4371`; payload `ep_grade_judge.py:219-235,298` | per graded alert, intraday | `in_active_theme` (same set as R1) + theme stage "heat" + `in_narrative_cohort` + `active_narratives` = `get_narrative_theme_candidates(days=5)` (`db.py:6314`) | **previous sessions only** — narrative rows are written nightly ~17:05 |
| R3 | **Exposure-family check, entry pipeline stage 2b** (#452, SHADOW — observe-only, never blocks) | `entry_pipeline.py:523-532` → `exposure_family.check_family_exposure` (`exposure_family.py:47-86`) | at order-submit time (09:31 ORB, on apollo-execution) | `mi_themes` non-Retired, `theme_date ≥ CURRENT_DATE−7`, latest per name — same shape as R1 | **previous session's board** |

Prod state of the three (verified 2026-08-11): `holistic_judge_enabled = 'on'` since 06-10
(`mi_safeguard_state`) — R2 is live authority. `R4_THEME_BONUS_ENABLED` is unset in every
container env → code default **enabled** (`ep_detector.py:1281`); its own docstring calls the
+10 decorative at threshold 70 (a 2026-05-17 60-day check — dated, not re-verified here).
R3 has emitted **zero** `exposure_family_breach` events in 60 days (Appendix A Q12); its
under-threshold reads go to container logs only, so absence of breaches is the only durable
record.

**NOT theme consumers** (checked): position sizing (`prepare_orb_order` — regime/ATR-based, no
theme reference in `order_manager.py`), all safeguards (`_check_safeguards`: cap, daily loss,
breakers), the 9M path (`ninem_detector` — no `get_active_themes` call).

**Answer to "is the 09:31-vs-17:06 gap one path or several":** it is **ONE seam expressed
through three readers.** All three money-relevant readers consume the same upstream — the
nightly-written board and nightly-written narrative rows. There is NO path, anywhere, by which
same-session co-occurrence reaches any money decision. The earliest a link formed today can be
consumed is tomorrow's scan.

---

## 4. What already exists at 09:31 that the nightly later uses

- **The EP alerts themselves** (`mi_ep_alerts`, written at detection, with catalyst text,
  grades, gap/vol). Lane-2's nightly input is exactly these rows, ~7.5h later.
- **Judge-inferred stubs** (C4) are written intraday — on 08-04 at 07:04 and 07:55 ET, before
  the open. But they are sector-keyed, not story-keyed: the defense story was split across
  "Technology" {BTDR,PLTR,TSAT} and "Industrials" {AEIS,AMRC,CAT,VOYG}, each mixing unrelated
  names. Signal exists; granularity is wrong for a correlated-book decision.
- **⚠ The cohort is only PARTIALLY visible at 09:31 — measured on all three co-gap days**
  (Appendix A Q17):

| Day | Cohort (eventual theme) | Alerted by 09:31 | After 09:31 |
|---|---|---|---|
| 07-30 | ARM, LRCX, SIMO (semis) | ARM 08:55, SIMO 09:10 → **2/3** | LRCX 09:50 |
| 07-31 | BLZE, FLNC, MPWR (AI-DC) | FLNC 07:00 → **1/3** | MPWR 09:35, BLZE 09:55 |
| 08-04 | PLTR, TSAT, VOYG, AMRC (defense) | PLTR 07:00, VOYG 08:10 → **2/4** | AMRC 09:45, TSAT 09:56 |
| 08-04 | BTDR, AMRC, BLZE (AI-DC) | BTDR 08:20, BLZE 07:00 → **2/3** | AMRC 09:45 |

  **No co-gap cohort in the 60-day window was fully visible by 09:31.** Any "form the theme at
  entry time" design can at best see the premarket subset. (Note the subset was still enough to
  matter on 08-04: PLTR+VOYG premarket for defense; BLZE+BTDR premarket for AI-DC — and BLZE+BTDR
  both filled.)

---

## 5. Measured: same-session multi-EP co-gaps, last 60 days

Window: `alert_date ≥ CURRENT_DATE − 60` = 2026-06-12 → 08-10, run 2026-08-11. Base population:
same-day alert pairs at `ep_score ≥ 50` (Lane-2's floor; Lane-2 additionally requires catalyst
text — not applied here, so this is the slightly wider population). Full SQL: Appendix A Q8.

| Measure | Value |
|---|---|
| Days with any EP alert | **36** |
| Days with ≥2 same-day alerts | **28** |
| Same-day alert pairs | **372** |
| Pairs that later shared a theme (`theme_date` within D..D+5) | **15** |
| Pairs whose shared theme ALREADY existed on the prior board (what 09:31 sees) | **0** |
| Sessions where a same-day group later shared a theme ("seam sessions") | **3** (07-30, 07-31, 08-04) — all pairs HIGH/HIGH |
| Of the 15 linking themes: born that same evening (name's first-ever `mi_themes` row = D) | **15 of 15** |

- Frequency: **3 seam sessions per 36 alert days ≈ 1 in 12 sessions (~11% of multi-alert
  days).** Caveat: for D after ~08-05 the D+5 look-ahead window is truncated at 08-10, so the
  last few days can only under-count.
- **The invisibility is structural, not bad luck**: in 60 days, not one same-day co-gap pair
  had a pre-existing shared theme. Co-gap links are, by construction of the clocks, always born
  after the entries they describe.
- **A second, quieter gap — the 3-member promote floor**: Lane-2 produced co-gap groups on only
  5 nights in 60d (Q7); the two 2-member groups (06-25 "AI memory", 07-20 "Bitcoin miners
  pivoting to AI data centers") never promoted (`_PROMOTE_MIN_MEMBERS=3`) and never reached the
  board via this lane at all — the #491 ex-miner story died exactly there.
- **Money contact on the 3 seam sessions** (Q11): 07-30 — ARM order placed then cancelled,
  LRCX/SIMO skipped. 07-31 — all three skipped. 08-04 — PLTR filled; BTDR and BLZE filled (later
  closed); AMRC/TSAT/VOYG skipped. **Only 08-04 produced multiple same-cohort fills**, and those
  fills (BLZE+BTDR) were the AI-DC cohort, not the defense one the incident was noticed on.

---

## 6. Where the true seam is

**The seam is a CLOCK mismatch: every mechanism that can LINK co-gapping names runs on the
17:00-ET nightly clock; every money decision that would consume the link runs at scan/entry
time reading the previous session's output.** Measured: 0 of 372 same-day pairs in 60 days were
visible to the entry path; 15 of 15 linking themes were born the same evening.

Against the prompt's taxonomy:

- **(a) themes born too late** — TRUE but incomplete. Birth is late relative to the entry, yet
  even instant birth machinery could not have shown the FULL cohort at 09:31 (§4: 1/3–2/4
  visibility). "Earlier birth" helps only for the premarket subset — which, on 08-04, did
  contain both pairs that mattered (PLTR+VOYG; BLZE+BTDR).
- **(b) entry check reading the wrong source** — NO, in the sense that no better source exists:
  there is today no earlier surface carrying story-granularity links. The one intraday surface
  (judge_inferred) is sector-binned and was measured splitting the defense story across two bins
  while mixing three unrelated names. The entry check reads the best link surface the system has;
  the surface is empty at that hour.
- **(c) a missing real-time grouping signal** — YES, this is the buildable gap if the operator
  wants one: the alert rows + catalyst text exist intraday; nothing groups them before 17:05.
- **(d) something else** — two compounders, both measured: the 3-member promote floor silently
  drops 2-member stories forever (§5), and the birth gate at `'on'` will hold first-sighting
  cohorts to a second sighting — the roadmap's own next step moves birth LATER (§2).

Bounding fact for judging urgency: the realized exposure so far is capped by book size —
`max_positions 5/5` blocked further adds on 08-04, and the 60-day book has rarely held >2
positions at once (the #452 threshold-lowering measurement, `exposure_family.py:26-38`).

---

## 7. Bonus finding — where the duplicate pair actually came from (#553/#555 context)

The near-duplicate "Spending Surge"/"Contract Surge" is not a Lane-2 wording coin-flip alone;
it took a re-run to mint. Measured from `mi_audit_log` 2026-08-04 17:00–17:15 ET (Appendix A Q3):

- The FULL theme pipeline (engine → shadow_v2 → Lane-2 → promote) ran **three times** that
  evening: passes starting 17:00:32, ~17:08, ~17:10 (three `theme_load_state` + three
  `narrative_theme_discovery_ran` + three `shadow_themes_promoted` events).
- Pass 1's Lane-2 named the cohort "…Spending Surge" → promoted 17:06:39. Pass 2's Lane-2
  re-derived the SAME cohort with fresh wording "…Contract Surge" → promote 17:13:20 wrote it as
  a NEW theme, because `_canonicalize_theme_names` only converges against PRIOR-day rows
  (`theme_date >= $1::date - 14 AND theme_date < $1::date`, `theme_engine.py:1886`) — same-day
  duplicates are invisible to it. Pass 3 re-worded back to "Spending Surge" (upsert; no third
  row) — which is why the surviving candidate row says "Spending Surge" while the duplicate
  live row says "Contract Surge".
- **What triggered passes 2 and 3 could not be determined from the DB** (§9). Candidate
  re-entry points exist (`/data/refresh`, `/theme/run` in `agent.py:424-447`, the "refresh"
  task route); no job-source audit row distinguishes them.
- Implication, stated not planned: same-day duplicate protection does not exist in the engine's
  canonicalizer; #553's dashboard matcher merges the pair downstream on some days and not others
  (its own verify-failure note). Any re-run of the nightly while Lane-2 has a live cohort can
  mint another duplicate.

---

## 8. The forks — the operator's decisions

Stated neutrally; costs and risks measured where possible. **⚠ LINE flags per fork.** No fork
is pre-selected.

### F-A · Leave it alone
- **What**: entry path keeps reading the previous session's board; book cap remains the only
  concentration control.
- **Cost**: ~1 in 12 sessions a same-day co-gap cohort is invisible at entry (§5); on the one
  session with multiple same-cohort fills (08-04) the exposure was 3/5 slots across two stories.
- **Risk**: the premortem-R1 shape (5 slots = one bet) remains possible on a large co-gap day;
  base rate says rare, cap says bounded.
- **LINE**: not touched.

### F-B · Entry check also consults same-session EP alerts (extend stage 2b)
- **What**: at submit time, additionally group TODAY's already-fired alerts (deterministic
  co-text/catalyst match, or an LLM pass) and count same-story opens. Two rungs: observe-only
  emit (the existing #452 shadow pattern), or blocking.
- **Cost**: sees only the premarket subset (§4 — but that subset covered both 08-04 pairs);
  deterministic sector-proxy grouping is exactly the pseudo-cluster trap #534's derivation
  measured and rejected; an LLM in the 09:31 hot path is new latency/failure surface on the
  money path.
- **Risk**: false same-story links blocking real entries (if ever blocking); at threshold-1
  semantics one bad link = one lost entry.
- **LINE**: **YES — both rungs.** Anything that changes what the entry path consults is entry
  discipline. The blocking flip is additionally the already-parked
  `exposure_family_cap_promotion` operator fork.

### F-C · Move link-formation earlier (premarket / intraday Lane-2 pass)
- **What**: run the co-gap grouping (or a registry `join` pass) at e.g. 09:15 over premarket
  alerts, and/or midday; links land in shadow rows (and optionally the board) same-session.
- **Cost**: still partial cohorts at 09:31 (§4); extra LLM runs (~$0.08–0.11/run at the #167
  v1 measurement; v2 registry cheaper per its design); if results reach the LIVE board or the
  judge's `active_narratives`, the grade surface drifts → the ADR-0030 judge-eval preflight
  gate fires by design (never suppress).
- **Risk**: morning-clock LLM dependency; more churn on the board the operator reads.
- **LINE**: detection-surface change → CHANGE_PROCESS + operator sign-off (grade-affecting via
  R2). Becomes entry discipline TOO the moment the entry path is expected to act on it.
- **Interaction**: directly opposed by F-E below — decide them together.

### F-D · Consume alert-time signals that already exist (judge_inferred / raw alert co-text)
- **What**: entry path reads the intraday stubs or raw alert rows instead of waiting for themes.
- **Cost**: measured wrong granularity today (§4 — the defense story split across two
  sector bins, 3 unrelated names mixed in). Fixing the stub naming is a #322-surface redesign.
- **Risk**: acting on sector-binned stubs ≈ acting on sector labels — the pseudo-cluster trap.
- **LINE**: **YES** — changes what the entry path consults.

### F-E · The birth-gate flip (already queued) — rule on its seam interaction knowingly
- **What**: not a new build. The Phase-1 gate's graduation path (observe → on) is already in
  flight (`theme_birth_gate_observe_calibration`). At `'on'`, first-sighting cohorts wait for a
  second sighting: the 08-04 defense theme would not have been born on 08-04 at all (its
  observe-mode verdict that night was `awaiting-2nd-sighting`).
- **Cost of flipping without ruling here**: this seam widens from ~7.5h to 1+ sessions for
  first-sighting cohorts, silently.
- **LINE**: the gate itself was operator-ruled 2026-07-27; the ask here is only that the
  observe-calibration ruling weigh this measured interaction.

### Recommendation (labeled as such, evidence-bounded)
No build fork clearly dominates on this evidence: base rate 3 sessions/60d, realized cost so
far bounded by the position cap, and every "act at 09:31" design is limited to the premarket
subset. If the operator wants one measured step, the cheapest information-first move is
**F-B's observe-only rung** (emit-only, the same pattern #452 already runs) — it would have
produced a same-second telemetry line on 08-04 for both PLTR+VOYG and BLZE+BTDR. It still
touches what the entry path consults, so it is explicitly the operator's call, not a plan.

---

## 9. What could NOT be determined

- **What triggered nightly passes 2 and 3 on 08-04 evening** (§7). No job-source audit exists;
  container logs from 08-04 have rotated.
- **Whether the judge's tier was counterfactually swung by theme/narrative context on any
  seam-day alert** — `fire_axes` and rationales are logged per decision, but a counterfactual
  re-grade without the context was not run (paid eval; out of a mapping task's scope).
- **Per-entry proof that the stage-2b check executed on every 08-04 submission** — it is
  error-wrapped and its under-threshold path logs to container logs only (rotated). The durable
  record is only "zero breach events in 60d".
- **Lane-2 v2 (registry mode)'s behavior on a co-gap day** — v2 has been ON only since 08-09;
  its first decision record (08-10) was a 5-seed night with no co-gap. All measurements in §5
  are v1-era mechanics; v2 keeps the same nightly clock, so the seam is unchanged, but join/seed
  behavior on the next real co-gap day is unobserved.
- **Paper-account parallels** — not examined; all trade-side numbers here are `account_mode='live'`.

---

## 10. Doc-staleness found while verifying (fix in the SSoT's next touch, not here)

- `docs/architecture/theme_engine.md` — says `lane2_grouping_v2` is "FAIL-CLOSED OFF" / "built
  dark": prod flag is **`'on'` since 2026-08-09**. Says birth-gate `'off'` is "today's
  production state": prod is **`'observe'` since 2026-07-30**.
- `CLAUDE.md` architecture sketch shows orchestrator + market agent only; the entry pipeline
  actually executes on **apollo-execution** (container verified; `trigger_orb_entry` →
  `execution_client`, `scheduler.py:1037-1046`) — consistent with the existing memory note, but
  absent from the diagram.

---

## 11. Measured: the 3-member promote floor's cost, precisely (2026-08-11 addendum)

> Operator, 2026-08-11: *"are we sufficiently using the EP gap stocks to find new themes early"* —
> not the position cap. This section measures the **member floor** (`_PROMOTE_MIN_MEMBERS = 3`,
> `theme_engine.py:2099,2272`) in isolation from the clock (§5–§6 above), against
> `mi_theme_candidates_shadow` directly — the population the floor filters, read BEFORE the
> `>= _PROMOTE_MIN_MEMBERS` line runs. Read-only, $0, queries Q18–Q21 (Appendix A).

**Scope**: the three sources `resolve_auto_promote_sources` actually admits
(`db.py:6570-6586`) — `shadow_v2`, `narrative_cogap`, `rs_slope_synthesis`. Confirmed the gate
mode has been `'observe'` continuously since 2026-07-30 with no `'on'` transition on record
(`mi_safeguard_state`, single row) — 'off' and 'observe' resolve to the identical full allowlist,
so this is the correct set for the ENTIRE window, not just part of it. A 2-member row from
`coverage_probe` / `judge_inferred` / `narrative_cogap_backfill` / `narrative_seed` /
`ecosystem_reactivation` was excluded — those sources were never auto-promote-eligible regardless
of member count.

**⚠ Data-start caveat (not a retention purge — checked)**: `purge_old_data()` (`db.py:8035-8076`)
does not list `mi_theme_candidates_shadow` among its retention targets, and the table holds
`narrative_cogap_backfill` rows back to 2026-05-06 — so nothing is being deleted. But the three
scoped sources' OWN oldest rows in prod are 2026-06-24 (`rs_slope_synthesis`), 06-25
(`narrative_cogap`), 06-26 (`shadow_v2`) — these lanes simply were not producing rows that far
back. Effective window is **~47–48 days of the nominal 60** (2026-06-24/25/26 → 08-10), not the
full 60. Stated plainly per instruction, not adjusted for.

### 11.1 The discard count

| Source | 2-member rows (discarded) | Distinct sessions | ≥3-member rows (cleared floor) | Distinct sessions |
|---|---|---|---|---|
| `shadow_v2` | **84** | 20 | 71 | 18 |
| `narrative_cogap` (the literal EP-gap-alert lane, C1) | **5** | 5 | 4 | 3 |
| `rs_slope_synthesis` | **0** | 0 | 11 | 8 |
| **Total** | **89** | **23** (of ~34 trading days in the effective window) | **86** | — |

- **89 candidate-cohort rows discarded at the 2-member floor in 23 distinct sessions** — this is
  N=23 sessions, not N=89; some sessions produced multiple discarded cohorts same-night (max 9,
  on 08-10; per-session counts in Appendix A Q18 — no single-day count dominates the total).
- **89 discarded vs 86 that cleared the floor: essentially a 51/49 split of everything the three
  lanes produce.** The floor is discarding roughly HALF of all shadow-lane candidate output by
  row count — a large volume, independent of whether any given discard was later worth it (11.2).
  Total (89+86=175) reconciles exactly against the raw row count for these 3 sources in-window.
- **83 distinct ticker pairs** among the 89 rows (6 pairs recurred on a second night with a fresh
  auto-generated name, same 2 tickers, still capped at 2 — none of the 6 ever grew a 3rd member:
  ALLE/BCO, BLZE/P, DLB/IDCC, EFX/NIQ, PHR/WAY, WAB/WNC).
- **1-member cohorts: zero, ever**, in any of the three sources' full history (not just this
  window) — nothing to report separately.
- Correction to §5's own earlier count: §5 named "the two 2-member groups" for `narrative_cogap`
  (06-25, 07-20) — that was an undercount from an aggregate-only query (Q7 summed cardinality per
  night, not per cohort). The precise count is **5** 2-member `narrative_cogap` rows across 5
  nights (06-25, 07-20, 07-30, 07-31, 08-04) — Q7's "5 nights produced groups" was correct; not
  every group on those nights was 2-member, some nights carried a viable ≥3 cohort alongside a
  discarded one.

### 11.2 Did any discarded pair later become a real theme — the number that answers the question

Method: for each of the 89 discarded rows, search `mi_themes` (ANY source, ANY later
`theme_date`) for a row whose tickers are a superset of the discarded pair AND has ≥3 members —
a genuine family, not a re-listing of the same 2 tickers. Full query: Q19.

**5 of 89 rows (5 of 83 distinct pairs) eventually appear inside a real ≥3-member theme.** But
only **3 of those 5 reached `mi_themes` via the SAME shadow lane** (`source='shadow_promoted'`,
i.e., the correlation cluster itself grew a 3rd member on a later night and cleared the floor
then) — those 3 are the floor's genuine, attributable cost. The other 2 reached `mi_themes` via
`source='live'` — Lane-1's OWN independent nightly discovery found the same pair (plus others) on
its own, a completely different, floor-free mechanism (W1, not W2) — the floor cost those 2
**nothing**, since Lane-1 would have surfaced them regardless of what the shadow floor was set to.

| Pair | Source | Discarded | Became real theme | Days earlier we'd have seen it | Attributable to the floor? |
|---|---|---|---|---|---|
| LQDA, NAMS | shadow_v2 | 07-01 | 07-07, "Rare Cardiometabolic & Endocrine Specialty Pharma" (shadow_promoted, {CRNX,LQDA,MLYS,NAMS}) | **6 days** | **Yes** |
| NSP, FA | shadow_v2 | 07-06 | 07-07, "SMB & Workforce Business Services Platforms" (shadow_promoted, {NSP,FA,LZ}) | **1 day** | **Yes** |
| RGNX, SRPT | shadow_v2 | 07-07 | 07-08, "In Vivo Gene & Engineered Cell Therapy Clinical Re-Rating" (shadow_promoted, {RGNX,SRPT,IMMX,SRRK,VOR}) | **1 day** | **Yes** |
| KNSL, PLMR | shadow_v2 | 07-01 | 07-02, "Specialty Insurance Underwriting & Brokerage" (**live**, {PLMR,KNSL,RYAN,WTW}) | 1 day | No — Lane-1 found it independently |
| MLKN, BOBS | shadow_v2 | 07-14 | 08-03, "Commercial, Office & Home Furniture..." (**live**, {MLKN,HNI,BOBS}) | 20 days | No — Lane-1 found it independently |

- **`narrative_cogap` — the literal EP-gap-alert lane the operator asked about — has ZERO
  confirmed cases.** None of its 5 discarded pairs (MU/SNX, HUT/IREN, EME/PWR, COHU/MPWR,
  AEIS/ZBRA) ever reappear in `mi_themes` with a 3rd member, in this window. 06-25 and 07-20 have
  30+ days of forward-looking data and are solid true negatives (matches §5's "#491 ex-miner
  story died exactly there"); 07-31 and 08-04 have only 11 and 7 days of forward window
  respectively — right-censored, genuinely unresolved, not "no" for certain.
- The 3 floor-attributable cases are all `shadow_v2` — the RS-correlation lane (built from RS
  accelerators/recovery clusters, `theme_engine.py:1175`), **not** the EP-gap-alert lane (C1,
  `narrative_cogap`, built from `get_today_ep_alerts`). Worth being precise about since the
  operator's question names EP gap stocks specifically.
- Right-censoring caveat applies generally to discards from the last ~2 weeks (through 08-10) —
  insufficient forward window to know if they'll join a later theme; treat 11.2's "5 of 89" as a
  floor, not a final count.

### 11.3 Verdict: floor vs clock

**The clock is the dominant, structural cost; the floor's measured cost is real but small, and
for the EP-gap population specifically, unconfirmed in 60 days.**

- Clock (§5–§6, already measured): **0 of 372** same-day EP-alert pairs visible to the entry path
  in 60 days; **15 of 15** linking themes born the same evening as promotion; 3 seam sessions
  with actual same-cohort fills. Structural — every co-gap link is born after the trades it would
  describe, by construction of the clocks, on every one of 36 alert days.
  Ordering follows the operator’s framing directly: EP-gap themes (C1/`narrative_cogap`) are
  gated ENTIRELY by the clock in this data — the floor never had a confirmed opportunity to cost
  anything there (0/5 attributable cases).
- Floor (this section, newly measured): **3 confirmed cases in 60 days**, all outside the EP-gap
  lane, 1–6 days earlier each. Volume discarded is large (89 rows, ~half of all shadow-lane
  output) but the validated hit rate is low (3 of 83 distinct pairs, ≈4%) and zero of that 3 sits
  in the population the operator asked about.
- Both mechanisms gate ONLY the shadow→live promote path (W2); neither gates Lane-1's own nightly
  discovery (W1) — 2 of the 5 "later became real" matches prove Lane-1 gets there anyway,
  independent of the floor, so those 2 were never actually at risk from the floor setting.

---

## Appendix A — the queries (all read-only, run 2026-08-11 against apollo-postgres)

Raw captured output: session scratchpad `theme_seam_probe{,2,3}.out` (not committed).

```sql
-- Q2/Q2b: the two duplicate themes + every row ever holding all four
SELECT id, theme_date, name, stage, source, tickers, created_at
FROM mi_themes WHERE theme_date='2026-08-04' AND 'PLTR' = ANY(tickers);
SELECT theme_date, name, source, stage, created_at
FROM mi_themes WHERE tickers @> ARRAY['PLTR','TSAT','VOYG','AMRC'];

-- Q3: trades; Q4: alert clocks; Q5: the 09:31 audit window
SELECT ticker, status, skip_reason, proposed_at FROM mi_live_trades
WHERE alert_date='2026-08-04' AND ticker IN ('PLTR','TSAT','VOYG','AMRC');
SELECT ticker, ep_score, score_tier, gap_pct, detected_at FROM mi_ep_alerts
WHERE alert_date='2026-08-04' AND ticker IN ('PLTR','TSAT','VOYG','AMRC');
SELECT created_at, event_type, summary FROM mi_audit_log
WHERE created_at BETWEEN '2026-08-04 13:25+00' AND '2026-08-04 13:45+00'
  AND event_type ILIKE '%orb%';

-- Q16: the board the entry path saw (its exact read shape, exposure_family.py:60-69)
SELECT name, stage, theme_date, tickers FROM (
  SELECT DISTINCT ON (name) name, stage, tickers, theme_date FROM mi_themes
  WHERE theme_date BETWEEN '2026-07-28' AND '2026-08-03'
  ORDER BY name, theme_date DESC) l
WHERE stage != 'Retired' AND l.tickers && ARRAY['PLTR','TSAT','VOYG','AMRC'];
-- → 0 rows

-- Q8: the 60-day seam measurement (§5's table comes from _seam)
CREATE TEMP TABLE _seam AS
WITH alerts AS (
  SELECT DISTINCT alert_date AS d, ticker, score_tier FROM mi_ep_alerts
  WHERE alert_date >= CURRENT_DATE - 60 AND ep_score >= 50),
pairs AS (
  SELECT a.d, a.ticker t1, b.ticker t2,
         (a.score_tier='HIGH' AND b.score_tier='HIGH') AS both_high
  FROM alerts a JOIN alerts b ON a.d=b.d AND a.ticker < b.ticker)
SELECT p.*,
  EXISTS (SELECT 1 FROM mi_themes th WHERE th.theme_date BETWEEN p.d AND p.d+5
            AND th.tickers @> ARRAY[p.t1,p.t2])                    AS shared_after,
  EXISTS (SELECT 1 FROM (
      SELECT DISTINCT ON (name) name, tickers, stage FROM mi_themes
      WHERE theme_date BETWEEN p.d-7 AND p.d-1
      ORDER BY name, theme_date DESC) latest
    WHERE latest.stage != 'Retired'
      AND latest.tickers @> ARRAY[p.t1,p.t2])                      AS shared_before
FROM pairs p;
-- totals: 372 pairs / 15 shared_after / 0 shared_before / 3 seam days
-- Q10 (born-same-day): min(theme_date) per linking theme name >= d for all 15 pairs
-- Q11 (money contact): join _seam to mi_live_trades on (alert_date, ticker)

-- Q7: Lane-2 co-gap nights in the window (5 nights; the 2-member groups never promote)
SELECT run_date, count(*), sum(cardinality(tickers)) FROM mi_theme_candidates_shadow
WHERE source='narrative_cogap' AND run_date >= CURRENT_DATE-60 GROUP BY run_date;

-- Q12: exposure-family shadow firings, 60d → 0 rows
SELECT * FROM mi_audit_log WHERE event_type ILIKE 'exposure_family%'
  AND created_at >= NOW() - INTERVAL '60 days';

-- Q13: write clocks by source, 14d (17:04–17:20 ET) — see §2
SELECT theme_date, source, count(*), min(created_at), max(created_at)
FROM mi_themes WHERE theme_date >= CURRENT_DATE-14 GROUP BY 1,2 ORDER BY 1,2;

-- Q18 (§11.1): the 2-member discard count, by source and by session
SELECT source, cardinality(tickers) AS n_members, COUNT(*) AS n_rows,
       COUNT(DISTINCT run_date) AS n_sessions
FROM mi_theme_candidates_shadow
WHERE source IN ('shadow_v2','narrative_cogap','rs_slope_synthesis')
  AND run_date >= CURRENT_DATE - 60
GROUP BY 1,2 ORDER BY 1,2;
-- per-session breakdown (burst check):
SELECT run_date, COUNT(*) FILTER (WHERE source='shadow_v2') AS shadow_v2,
       COUNT(*) FILTER (WHERE source='narrative_cogap') AS narrative_cogap,
       COUNT(*) FILTER (WHERE source='rs_slope_synthesis') AS rs_slope_synthesis,
       COUNT(*) AS total
FROM mi_theme_candidates_shadow
WHERE source IN ('shadow_v2','narrative_cogap','rs_slope_synthesis')
  AND run_date >= CURRENT_DATE - 60 AND cardinality(tickers) = 2
GROUP BY run_date ORDER BY run_date;
-- → 89 rows / 23 sessions / 83 distinct unordered pairs (source breakdown: shadow_v2 84/20,
--   narrative_cogap 5/5, rs_slope_synthesis 0/0); ≥3-member rows same window: 86 (71/4/11)

-- Q19 (§11.2): for each discarded 2-member row, the first LATER real (≥3-member) theme
-- containing both tickers, any source, any later theme_date
WITH discarded AS (
  SELECT source, run_date, name, tickers
  FROM mi_theme_candidates_shadow
  WHERE source IN ('shadow_v2','narrative_cogap','rs_slope_synthesis')
    AND run_date >= CURRENT_DATE - 60 AND cardinality(tickers) = 2)
SELECT d.source, d.run_date, d.name, d.tickers,
  (SELECT MIN(theme_date) FROM mi_themes t WHERE t.theme_date > d.run_date
     AND t.tickers @> d.tickers AND cardinality(t.tickers) >= 3) AS first_real_theme_date,
  (SELECT string_agg(DISTINCT t.name, ' | ') FROM mi_themes t WHERE t.theme_date > d.run_date
     AND t.tickers @> d.tickers AND cardinality(t.tickers) >= 3) AS theme_names
FROM discarded d ORDER BY d.source, d.run_date;
-- → 5 of 89 rows match; full mi_themes rows for the 5 pairs pulled separately (Q20) to check
--   `source` (shadow_promoted = floor-attributable vs live = Lane-1 independent discovery)

-- Q20: full mi_themes history for the 5 matched pairs, to read `source` + full ticker set
SELECT theme_date, name, source, stage, tickers, created_at FROM mi_themes
WHERE tickers @> ARRAY['LQDA','NAMS'] OR tickers @> ARRAY['KNSL','PLMR']
   OR tickers @> ARRAY['NSP','FA'] OR tickers @> ARRAY['RGNX','SRPT']
   OR tickers @> ARRAY['MLKN','BOBS']
ORDER BY theme_date;

-- Q21: birth-gate mode history (confirms full allowlist for the entire window)
SELECT safeguard, account_mode, state, last_transition_at, updated_at
FROM mi_safeguard_state WHERE safeguard='theme_birth_gate';
-- → one row, state='observe', last_transition_at 2026-07-30 — no 'on' transition on record;
--   'off'/'observe' resolve to the identical full allowlist (db.py:6570-6586)

-- Data-start check (§11 caveat): confirms mi_theme_candidates_shadow is NOT in the retention
-- purge list (db.py:8035-8076 purge_old_data) — the 06-24/25/26 floor is production history,
-- not a deletion:
SELECT source, MIN(run_date), MAX(run_date), COUNT(*) FROM mi_theme_candidates_shadow
GROUP BY source ORDER BY 1;
```

## Appendix B — code pointers (repo @ main, 2026-08-11)

- Entry funnel + stage 2b: `agents/market_intelligence/broker/entry_pipeline.py:523-532`
- Family check + threshold history: `agents/market_intelligence/exposure_family.py:26-86`
- R4 bonus: `agents/market_intelligence/ep_detector.py:1281-1285`; per-tick theme set `:2485-2495`
- Judge authority: `ep_detector.py:385-397, 4371`; theme/narrative inputs `ep_grade_judge.py:219-235, 298`
- Board reader: `db.py:7713` (`get_active_themes`); narrative reader: `db.py:6314`
- Allowlist: `db.py:6506` (`AUTO_PROMOTE_THEME_SOURCES`), `db.py:6526` (`resolve_auto_promote_sources`)
- Nightly sequence: `scheduler.py:540-680` (steps 4.5–5d), cron `scheduler.py:5064-5066`
- Promote: `theme_engine.py:2237` (`_PROMOTE_WINDOW_DAYS=3`, `_PROMOTE_MIN_MEMBERS=3` at `:2098-2099`)
- Same-day-blind canonicalizer: `theme_engine.py:1848-1887` (window `theme_date < $1::date`)
- Lane-2: `theme_engine.py:804` (`discover_narrative_themes`); synthesis cron `scheduler.py:5727-5729`
- Operator writes: `agent.py:508` (`/teach` → `seed_theme`), `theme_engine.py:2441` (`/promotetheme`)
- Re-run entry points (§7): `agent.py:424-447` (`/data/refresh`, `/theme/run`)
