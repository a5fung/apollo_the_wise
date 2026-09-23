# EP↔Theme Coverage Loop — ADR-ready design (2026-07-13)

**Status: DRAFT — operator review. DESIGN ONLY** — nothing here changes code, thresholds,
grades, or theme assignment. Every live-touching item is explicitly gated (§6) on operator
sign-off + CHANGE_PROCESS; sizing evidence (§5) runs before any commitment. THE LINE holds.

**North star (operator's framing):** two coupled goals — get into the RIGHT EPs, track the
RIGHT themes — joined by ONE shared spine: the theme-coverage/membership layer. An EP can
reveal a theme the engine doesn't track; that blind spot then blocks the theme credit the
grade path would have paid. Better coverage → correct credit → better EP selection; and EPs
are themselves the earliest theme sensor. This doc designs the loop, not any one component.

---

## 1. The loop, precisely — and the four places it breaks

**Membership is consumed by the grade path at three points** (all verified in code):
1. **R4 bonus** — `in_active_theme` (Accelerating/Mainstream only, `ep_detector.py:1416-1424`)
   adds +10 to `ep_score` (`:1179`). Decorative under threshold 70 (pre-ship SQL: 0 flips).
2. **Judge context** — the judge payload carries theme/narrative context incl. the shadow
   narrative cohorts (`active_narratives`, `:1443-1449`); the judge weighs it qualitatively
   (live authority today).
3. **M1-d deterministic credit** (DARK) — `get_theme_membership` → `theme_axis_credit` →
   `resolve_composite_tier` (`ep_detector.py:3198-3237`). The ONLY place a mechanical grade
   *increase* can ride, and only on a MODERATE (+1 on HIGH clamps).

**Membership is produced by one engine** whose candidate universe is **RS-gated**: top-60 RS
leaders + velocity (RS≥50) + turners (`run_theme_engine`, `theme_engine.py:4352-4356`).

**The reverse arrow exists but is thin:** the only EP→theme feed is the #167 narrative co-gap
shadow lane (`discover_narrative_themes` — groups the DAY's EP alerts by shared narrative,
needs ≥2 qualifying same-day alerts, writes `mi_theme_candidates_shadow`
source='narrative_cogap'), plus the promote lane (`promote_shadow_themes` nightly ≥3 members
in 3d / `/promotetheme` one-tap) that graduates shadow cohorts into live `mi_themes` at
Nascent, `source='shadow_promoted'`.

**The four breaks:**

| # | Break | Where |
|---|---|---|
| B1 | **Detection**: a single-name EP in an untracked theme has NO detector. Discovery is RS-gated (day-one gappers usually aren't RS leaders yet); the co-gap lane needs ≥2 same-day alerts. | theme_engine.py:4352, 359-386 |
| B2 | **Measurement**: the shadow that would size the gap is HIGH-only (`ep_detector.py:3316`), and — critically — its independent signals (name-attribution, co-movement) are computed ONLY for tracked-theme members; themeless rows are zeroed (`theme_axis_shadow.py:324-328`). The blind-spot population carries no independent evidence at all. | see §2-C1 |
| B3 | **Credit**: `blind_spot` marker = 0 credit by design (correct — unknown ≠ member). A real missed membership earns nothing until the engine actually tracks it. There is no path from "detected" to "tracked." | catalyst_rubric_runtime.py:654 |
| B4 | **Timing**: even when the co-gap lane catches a cohort, it's EOD + shadow + ≥3-member promote bar — the second-wave EP alert next morning still grades themeless. | promote_shadow_themes |

**The coupling, stated once:** fixing B1+B3 (detect → track) makes B2's credit path (already
built, dark or live) fire correctly for every *subsequent* alert in the cohort. The payoff is
**pay-forward**: the alert that reveals the blind spot never benefits from its own detection —
the NEXT cohort member does. That temporal decoupling is also the structural anti-circularity
guarantee (§3.4).

---

## 2. What the code actually says (corrections to the tasking frame — verified)

- **C1 — "independent signals already exist in `mi_theme_axis_shadow`" is only half true.**
  The *columns* exist (`matched_terms`, `name_attributable`, `co_moving`, `cohort_move`,
  `structural_attributable`) and the *pure functions* exist and are reusable
  (`compute_name_attribution`, `compute_co_movement`, `compute_structural_attribution`,
  `compute_step1_signals`). But the writer computes them **only when the ticker is in a
  tracked theme** — for themeless rows everything is written as 0/False/NULL
  (`theme_axis_shadow.py:324-328`). The blind-spot rows have no independent data today; the
  design below reuses the FUNCTIONS against *candidate* cohorts.
- **C2 — the shadow's stage is `get_theme_heat_asof`, not `get_theme_membership`.** The
  as-of read (`db.py:5561`) has **no 7-day recency floor** (only `theme_date <= alert_date`,
  stage != Retired); the live credit path's `get_theme_membership`
  (`catalyst_rubric_runtime.py:390`) is 7d-bounded and reads as-of *today*. They can disagree
  on stale themes. §5's queries run both variants so the sizing isn't quietly instrument-biased.
- **C3 — ADR 0015's rollout intent was never fully built.** 0015 step-3 says "accrue incl.
  sub-HIGH tiers" and its STEP-0 caveat says tier-step effects are "unmeasurable until the
  shadow accrues sub-HIGH rows." The deployed gate is `score_tier == "HIGH"` only
  (`ep_detector.py:3316`). Widening the gate to MODERATE **completes the signed ADR**, it
  does not extend it. (This is S1 in §6 — the single cheapest evidence unlock.)
- **C4 — the judge's blind-spot flag is not 100% "judge opinion."** The judge payload includes
  the prior-5d shadow narrative cohorts, and its prompt lights theme/narrative for a catalyst
  that *joins* an active narrative even if the ticker isn't a member (`ep_grade_judge.py:254`).
  So some judge-lit blind spots are shadow-lane-detected real cohorts the live engine lacks.
  Doesn't change the rule (confirmation must still be independent), but the 22 aren't pure
  circularity either.
- **C5 — two lattices in the M1-d mechanism.** `theme_axis_credit`'s Nascent/Mainstream bands
  are computed on the RUBRIC label lattice (weak→game_changer, `LABEL_BANDS`), but the wire-in
  applies `credit_steps` to the TIER lattice (none→MODERATE→HIGH). For a MODERATE alert,
  Accelerating (+1 unconditional) always composes to HIGH; a Nascent "near-miss" is near a
  *rubric* boundary, not near the MODERATE→HIGH boundary. Not a bug, but the M1 sitting should
  see this stated once.
- **C6 — the promote lane would auto-adopt any new candidate source.**
  `get_shadow_theme_candidates` has NO source filter (`db.py:5446-5451`), so probe-written
  cohorts with ≥3 members inside 3 days would auto-promote nightly. Conversely
  `get_narrative_theme_candidates` (what feeds the JUDGE payload) filters to
  `narrative_cogap`/`rs_slope_synthesis` — a new `coverage_probe` source is **structurally
  invisible to the judge** until it graduates into a real validated theme. Both facts are
  load-bearing in §4/§6.

---

## 3. The independent blind-spot detector (design)

**One EOD shadow job ("coverage probe")** — deterministic, zero-LLM, no hot-path latency.
Runs after the EOD chain on the day's **themeless EP alerts, HIGH + MODERATE**
(themeless = no `get_theme_heat_asof` hit, 7d-bounded variant).

### 3.1 Trigger — unconditional, never judge-gated
Run on ALL themeless alerts. Rejected alternative: trigger on judge `fire_axes`
theme/narrative — cheaper but re-imports the judge into the loop's front door AND misses the
judge-silent population (81/265 clean HIGH rows). The probe is cheap enough (no LLM) that the
trigger question shouldn't exist.

### 3.2 Candidate cohort generation (independent evidence only)
For each themeless alert, build a candidate peer set from three deterministic sources:
- **P1 — named entities (structural):** invert `compute_name_attribution` — match the cached
  company names (`mi_ticker_overrides.company_name`, same normalization
  `_normalize_company_name`) of a bounded peer universe against the alert's `grounded_text`.
  Peer universe v1: all tickers that EP-alerted (any tier) or appeared in `mi_ep_scan_log`
  within trailing 10 sessions, plus the subject's industry peers from `mi_ticker_overrides`.
  The catalyst naming a peer company = the strongest theme-as-driver evidence (the #369 finding).
- **P2 — co-gap (tape):** other alerts on the same alert_date (any tier), tagged same-sector
  or not. This generalizes the #167 lane's ≥2-same-day idea to per-name evidence.
- **P3 — co-movement (tape):** for P1∪P2 candidates, `compute_co_movement` vs the subject on
  alert day (existing `get_daily_moves`, |cohort median| ≥ 1% floor), **market-adjusted**
  (subtract SPY's same-day open→close move — kills the everything-rallies confound; fork F-D).

### 3.3 Confirmation bar (what counts as a REAL missed member/theme)
A candidate cohort is **confirmed** only when ALL of:
1. **≥2 signal families agree** — at least one P1 structural hit AND P3 co-movement true
   (P2 co-gap alone never confirms — calendar coincidence).
2. **Persistence** — the same cohort (≥50% ticker overlap) re-confirms on ≥2 distinct days
   within 5 sessions (mirrors the promote lane's own 3-day window; kills one-day wonders).
3. **Not excluded** — respects `mi_theme_exclusions` + validation cooldowns, same as any
   assignment.
Below the bar → the row is still logged (evidence accrual), marked unconfirmed.

**The judge appears nowhere in 3.2/3.3.** Judge `fire_axes` is stored on the probe row as a
*calibration column only* — "does independent evidence agree with the judge's blind-spot
flag" is a health gauge (the same discipline as #329's disagreement-rate rule), never an input.

### 3.4 Anti-circularity, by construction (the three walls)
1. **Signal wall:** attribution = named-entity ∩ candidate tickers + tape co-movement +
   persistence. No LLM theme opinion anywhere in detect/confirm.
2. **Source wall (C6):** probe cohorts write `source='coverage_probe'` — invisible to the
   judge's `active_narratives` (filtered source list). A cohort reaches the judge only after
   graduating into a validated live theme, through the same door as every organic theme.
3. **Time wall:** membership is never applied retroactively. The revealing alert keeps its
   grade; only later alerts in the (now tracked) cohort earn credit. The
   judge→discover→boost-my-own-grade loop is impossible even in the worst case.

### 3.5 Storage
Per-alert probe rows (new shadow table `mi_coverage_probe`: subject, alert_date, tier,
candidate_tickers, per-signal scores/matches, confirmed flag, judge_fire_axes-at-alert for
calibration) + confirmed cohorts upserted into the existing `mi_theme_candidates_shadow`
(source='coverage_probe', name = deterministic stub e.g. dominant-industry + date; the theme
engine's own canonicalization/validation names it properly if promoted). No new lifecycle
machinery — the existing lanes own promotion, validation, merge (ADR 0025), aging.

---

## 4. How detection feeds BOTH goals

### 4a. Theme tracking (right themes)
Two blind-spot flavors, two existing paths — **no new promotion machinery**:
- **Theme-gap** (no cohort exists): confirmed cohort → `mi_theme_candidates_shadow` → the
  existing promote lane. Surfaces in `/themes` + `/promotetheme` immediately; nightly
  auto-promote inclusion is fork F-C (it's automatic today per C6 — the fork is whether to
  *keep* that or carve probe rows out until §5 evidence returns). Promoted themes enter at
  **Nascent** → no R4 effect, no Accelerating credit until the engine's own lifecycle promotes
  the stage organically — the engine stays the sole authority on theme heat.
- **Member-gap** (theme tracked, ticker missing from `tickers`): confirmed (ticker, theme)
  pair → injected as a candidate into the engine's existing assignment pass
  (`_assign_uncovered_to_themes`), which today only sees RS≥50 uncovered stocks — the EP
  ticker rides in with a probe tag but passes the SAME LLM assignment judgment, exclusions,
  cooldowns, and Mon/Wed/Fri + birth validation as any other member. Fork F-B.
Stability guards already in place and inherited: birth validation (#266), ADR 0025
dissolve/merge arms, 14d cooldowns, `mi_theme_exclusions`, 7d recency aging.

### 4b. EP grade (right EPs)
**Deliberately NO new grade mechanism.** Once tracked, the three existing consumption points
(§1) do all the work: judge context line, R4 (if/when hot), and — when the operator flips
M1-d — `theme_axis_credit` composing MODERATE→HIGH for an Accelerating-cohort name. The
MODERATE→HIGH case is exactly the second-wave name: theme revealed on day D by one EP,
tracked by D+1, the next cohort member's MODERATE alert composes to HIGH → immediate alert +
ORB path instead of the morning briefing. `blind_spot` stays 0-credit forever (unknown ≠
member); the probe changes how fast unknown *becomes* member, not what unknown is worth.

---

## 5. Evidence first — the to-run sizing spec (for the parent to run on prod, read-only)

All queries: read-only, segment clean (`alert_date < '2026-05-11' OR > '2026-06-24'`) vs
polluted, MODERATE-inclusive, judge-independent where sizing (judge used only as a comparison
column). `a.source='live'` excludes backfill rows; report Q0 with and without if counts differ.

**Q0 — instrument coverage on MODERATEs** (how much of the population each instrument can see):
```sql
SELECT CASE WHEN a.alert_date < DATE '2026-05-11' OR a.alert_date > DATE '2026-06-24'
            THEN 'clean' ELSE 'polluted' END AS period,
       COUNT(*)                                            AS n_moderate,
       COUNT(*) FILTER (WHERE a.grounded_text IS NOT NULL) AS with_corpus,
       COUNT(*) FILTER (WHERE a.fire_axes IS NOT NULL)     AS with_judge_verdict,
       COUNT(*) FILTER (WHERE a.in_active_theme IS NULL)   AS legacy_flag_null
FROM mi_ep_alerts a
WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
GROUP BY 1 ORDER BY 1;
```

**Q1 — MODERATE theme membership + stage mix (the M1-d boostable population, tracked half).**
Run TWICE: once as written (7d-bounded = live `get_theme_membership` parity), once with the
marked line removed (unbounded = `get_theme_heat_asof` / shadow parity) — per C2:
```sql
SELECT CASE WHEN a.alert_date < DATE '2026-05-11' OR a.alert_date > DATE '2026-06-24'
            THEN 'clean' ELSE 'polluted' END AS period,
       COALESCE(t.stage, 'NONE') AS stage,
       COUNT(*) AS n
FROM mi_ep_alerts a
LEFT JOIN LATERAL (
    SELECT th.stage
    FROM mi_themes th
    WHERE a.ticker = ANY(th.tickers)
      AND th.stage != 'Retired'
      AND th.theme_date <= a.alert_date
      AND th.theme_date >= a.alert_date - INTERVAL '7 days'   -- REMOVE for unbounded variant
    ORDER BY th.theme_date DESC, th.score DESC NULLS LAST
    LIMIT 1
) t ON TRUE
WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
GROUP BY 1, 2 ORDER BY 1, 2;
```

**Q2 — the judge-vs-engine 2×2 on MODERATE** (extends the investigation's HIGH-only Part-2
table; this is the judge-defined UPPER bound, kept for continuity — not the decision number):
```sql
SELECT CASE WHEN a.alert_date < DATE '2026-05-11' OR a.alert_date > DATE '2026-06-24'
            THEN 'clean' ELSE 'polluted' END AS period,
       (t.stage IS NOT NULL) AS engine_tracks,
       CASE WHEN a.fire_axes IS NULL THEN 'judge_silent'
            WHEN a.fire_axes && ARRAY['theme','narrative'] THEN 'judge_lit'
            ELSE 'judge_no' END AS judge_theme,
       COUNT(*) AS n
FROM mi_ep_alerts a
LEFT JOIN LATERAL (
    SELECT th.stage FROM mi_themes th
    WHERE a.ticker = ANY(th.tickers) AND th.stage != 'Retired'
      AND th.theme_date <= a.alert_date
      AND th.theme_date >= a.alert_date - INTERVAL '7 days'
    ORDER BY th.theme_date DESC, th.score DESC NULLS LAST LIMIT 1
) t ON TRUE
WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
```

**Q3a — the INDEPENDENT re-size (the decision number): themeless MODERATEs whose catalyst
corpus names another EP-alerted company** (judge-free; crude SQL normalization of company
names — treat as first-order size, not a member list; the Python `_normalize_company_name`
is the real instrument and runs in the S2 probe):
```sql
WITH themeless_mod AS (
    SELECT a.ticker, a.alert_date, lower(a.grounded_text) AS corpus,
           CASE WHEN a.alert_date < DATE '2026-05-11' OR a.alert_date > DATE '2026-06-24'
                THEN 'clean' ELSE 'polluted' END AS period,
           CASE WHEN a.fire_axes IS NULL THEN 'judge_silent'
                WHEN a.fire_axes && ARRAY['theme','narrative'] THEN 'judge_lit'
                ELSE 'judge_no' END AS judge_theme
    FROM mi_ep_alerts a
    WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
      AND a.grounded_text IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM mi_themes th
          WHERE a.ticker = ANY(th.tickers) AND th.stage != 'Retired'
            AND th.theme_date <= a.alert_date
            AND th.theme_date >= a.alert_date - INTERVAL '7 days')
),
peer_names AS (
    SELECT DISTINCT a2.ticker, a2.alert_date,
           lower(regexp_replace(regexp_replace(ov.company_name, '[.,'']', '', 'g'),
                 '\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|sa|nv|ag)\s*$',
                 '', 'i')) AS norm_name
    FROM mi_ep_alerts a2
    JOIN mi_ticker_overrides ov ON ov.ticker = a2.ticker
    WHERE ov.company_name IS NOT NULL AND a2.source = 'live'
)
SELECT tm.period, tm.judge_theme,
       COUNT(*) AS n_themeless_mod,
       COUNT(*) FILTER (WHERE hit.n_peers > 0)  AS n_with_peer_mention,
       COUNT(*) FILTER (WHERE hit.n_peers >= 2) AS n_with_2plus_peers
FROM themeless_mod tm
LEFT JOIN LATERAL (
    SELECT COUNT(DISTINCT pn.ticker) AS n_peers
    FROM peer_names pn
    WHERE pn.ticker <> tm.ticker
      AND pn.alert_date BETWEEN tm.alert_date - 5 AND tm.alert_date + 5
      AND length(pn.norm_name) >= 6
      AND position(pn.norm_name IN tm.corpus) > 0
) hit ON TRUE
GROUP BY 1, 2 ORDER BY 1, 2;
```
*(Also run once with `WHERE a.score_tier = 'HIGH'` in `themeless_mod` — Q3a-HIGH calibrates
how much of the judge's 22-row blind-spot claim survives independent evidence, on the bigger N.)*

**Q3b — tape-only co-gap on the same population** (no text matching — same-day same-sector
co-alerts):
```sql
WITH themeless_mod AS ( /* identical CTE to Q3a, corpus not needed */
    SELECT a.ticker, a.alert_date,
           CASE WHEN a.alert_date < DATE '2026-05-11' OR a.alert_date > DATE '2026-06-24'
                THEN 'clean' ELSE 'polluted' END AS period
    FROM mi_ep_alerts a
    WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
      AND NOT EXISTS (
          SELECT 1 FROM mi_themes th
          WHERE a.ticker = ANY(th.tickers) AND th.stage != 'Retired'
            AND th.theme_date <= a.alert_date
            AND th.theme_date >= a.alert_date - INTERVAL '7 days')
)
SELECT tm.period,
       COUNT(*) AS n_themeless_mod,
       COUNT(*) FILTER (WHERE cg.same_sector >= 1) AS with_1plus_same_sector_cogap,
       COUNT(*) FILTER (WHERE cg.same_sector >= 2) AS with_2plus
FROM themeless_mod tm
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS same_sector
    FROM mi_ep_alerts a2
    JOIN mi_ticker_overrides o2 ON o2.ticker = a2.ticker
    JOIN mi_ticker_overrides o1 ON o1.ticker = tm.ticker
    WHERE a2.alert_date = tm.alert_date AND a2.ticker <> tm.ticker
      AND a2.source = 'live'
      AND o1.sector IS NOT NULL AND o2.sector = o1.sector
) cg ON TRUE
GROUP BY 1 ORDER BY 1;
```

**Q4 — outcome check: do the would-be-promoted MODERATEs behave like HIGHs?**
```sql
WITH pops AS (
    -- A: MODERATE + tracked Accelerating as-of membership (M1-d's unconditional trigger)
    SELECT 'A_accel_tracked' AS pop, a.ticker, a.alert_date
    FROM mi_ep_alerts a
    WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
      AND EXISTS (SELECT 1 FROM mi_themes th
                  WHERE a.ticker = ANY(th.tickers) AND th.stage = 'Accelerating'
                    AND th.theme_date <= a.alert_date
                    AND th.theme_date >= a.alert_date - INTERVAL '7 days')
    UNION ALL
    -- B: themeless MODERATE with an independent peer-mention (the Q3a hit population)
    SELECT 'B_indep_blindspot', tm.ticker, tm.alert_date
    FROM ( SELECT a.ticker, a.alert_date, lower(a.grounded_text) AS corpus
           FROM mi_ep_alerts a
           WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
             AND a.grounded_text IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM mi_themes th
                             WHERE a.ticker = ANY(th.tickers) AND th.stage != 'Retired'
                               AND th.theme_date <= a.alert_date
                               AND th.theme_date >= a.alert_date - INTERVAL '7 days') ) tm
    WHERE EXISTS (
        SELECT 1 FROM mi_ep_alerts a2
        JOIN mi_ticker_overrides ov ON ov.ticker = a2.ticker
        WHERE a2.ticker <> tm.ticker AND a2.source = 'live'
          AND a2.alert_date BETWEEN tm.alert_date - 5 AND tm.alert_date + 5
          AND ov.company_name IS NOT NULL
          AND length(lower(regexp_replace(regexp_replace(ov.company_name, '[.,'']', '', 'g'),
                '\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|sa|nv|ag)\s*$',
                '', 'i'))) >= 6
          AND position(lower(regexp_replace(regexp_replace(ov.company_name, '[.,'']', '', 'g'),
                '\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|sa|nv|ag)\s*$',
                '', 'i')) IN tm.corpus) > 0 )
    UNION ALL
    SELECT 'C_all_moderate', a.ticker, a.alert_date
    FROM mi_ep_alerts a WHERE a.score_tier = 'MODERATE' AND a.source = 'live'
    UNION ALL
    SELECT 'D_all_high', a.ticker, a.alert_date
    FROM mi_ep_alerts a WHERE a.score_tier = 'HIGH' AND a.source = 'live'
)
SELECT p.pop, COUNT(*) AS n, COUNT(o.fwd_5d_pct) AS settled,
       ROUND(AVG(o.fwd_5d_pct)::numeric, 2) AS avg_5d,
       ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY o.fwd_5d_pct))::numeric, 2) AS med_5d,
       COUNT(*) FILTER (WHERE o.fwd_5d_pct >= 5.0) AS wins_ge_5pct
FROM pops p
LEFT JOIN mi_ep_scan_outcomes o
       ON o.ticker = p.ticker AND o.scan_date = p.alert_date
GROUP BY 1 ORDER BY 1;
```

**Pre-committed reading (kill/keep — decided BEFORE seeing the numbers):**
- **Kill the grade half** if clean-period `B_indep_blindspot` is < ~5% of clean MODERATEs
  (≈ ≤1/month) **or** its settled 5d outcomes don't beat the `C_all_moderate` baseline.
  Then only S1 telemetry + the coverage-quality surfaces (briefing/`/why`/right-themes)
  survive; the detector shrinks to a thin operator-surface probe.
- **Proceed to the G-lane** if it clears both. Note the honest scale: even 10% ≈ 3/month of
  direct MODERATE boosts — the direct-boost number is the FLOOR of the loop's value (every
  later alert in a newly-tracked cohort also gets correct judge context/R4/credit), but the
  floor is what's measurable, so the floor decides.

---

## 6. Sequencing — shadow now vs operator-gated

**SHADOW NOW** (no money, no grade effect, evidence-accruing; themes/detectors = ship full
per working rules — each is a small code change riding normal review):
- **S1 — widen the two theme shadows to MODERATE** (`ep_detector.py:3316` gate →
  `in ("HIGH","MODERATE")`). Completes ADR 0015's signed accrual intent (C3); starts logging
  the exact population M1-d acts on. Cost: ~1-3 extra rows/day, one cached-rubric recompute
  each (once/day dedupe guard already exists).
- **S2 — the coverage probe** (§3): EOD job, new `mi_coverage_probe` table, reuses the
  existing pure functions. Pure telemetry; also runs the Python-grade version of Q3a nightly
  going forward (the SQL above is the historical first-order size; the probe is the real
  instrument).
- **S3 — probe→candidate feed**: confirmed cohorts into `mi_theme_candidates_shadow`
  (source='coverage_probe') → visible in `/themes`, promotable via `/promotetheme`. Judge
  payload untouched (C6 source filter — deliberate, documented in code).
- **S4 — run §5** (parent/operator) → the magnitude verdict against the pre-committed bar.

**GATED (operator sign-off; CHANGE_PROCESS where grade/membership methodology changes):**
- **G1 — M1-d flip** (`composite_authority`): unchanged, stays dark; its evidence base now
  accrues via S1. Not signable before MODERATE shadow rows + the 7/18-or-later sitting.
- **G2 — member-gap auto-feed** into the assignment pass (§4a): changes membership
  methodology → operator sign-off; probe-tagged, LLM-assignment + validation still gate every
  member.
- **G3 — nightly auto-promote for coverage_probe cohorts** (fork F-C): today's lane would
  auto-promote them (C6); operator decides inherit vs carve-out-until-S4-evidence.
- **G4 — any grade-path use of probe output beyond tracked membership** (e.g. crediting
  `blind_spot` directly): explicitly NOT proposed; listed only to pin it shut.

---

## 7. Risks + what makes this NOT worth building

1. **Circularity re-entry through side doors.** The front door is walled (§3.4), but watch:
   (a) probe cohorts leaking into the judge payload if someone later widens
   `get_narrative_theme_candidates`' source list — pin with a test; (b) judge-informed
   narrative_cogap cohorts feeding the same promote lane (pre-existing, accepted — they carry
   ≥2-name tape evidence); (c) using probe *confirmation* stats to tune the judge. Mitigation:
   the source-filter pin test + the calibration column stays read-only.
2. **Theme-engine destabilization / fragmentation.** ADR 0025 exists because 43% of themes
   are already 2-member fragments; a new birth source adds pressure. Mitigations: the §3.3
   two-family + persistence bar, canonicalization against existing themes at promote,
   ADR 0025's dissolve/merge arms, Nascent entry (no heat authority), 7d self-clean. Residual:
   if probe births still flood, cap promotions/week — an easy later knob.
3. **False members from name matching.** Generic/short company names false-positive; SQL
   sizing (Q3a) is cruder than the Python normalizer — expect the probe's true rate to come
   in BELOW Q3a. Mitigations: conservative normalizer (existing), co-movement requirement,
   LLM assignment validation as the final gate, cooldowns/exclusions. Accept: the sizing
   numbers are first-order.
4. **Confirmation-bias loop in co-movement.** Hot tape → everything co-moves → cohorts
   "confirm" everywhere. Mitigation: market-adjusted moves (F-D) + the structural-AND-tape
   requirement (correlation alone never confirms).
5. **Not worth building** if: Q3a/Q4 land under the kill bar (§5) — the grade half dies and
   the build shrinks to S1 + surfaces; or if operator review judges the second-wave
   MODERATE→HIGH promotions strategically unwanted regardless of size (more HIGHs = more ORB
   entries — a selectivity philosophy call, not an evidence call; flagging it as the
   operator's, per ADR 0003's selectivity direction).

---

## 8. Forks for the operator (each: fork + 1-line rec)

- **F-A — probe trigger**: all themeless alerts vs judge-flagged only. **Rec: all** (judge-free
  front door + covers judge-silent; cost ~zero).
- **F-B — member-gap feed (G2)**: auto-inject probe-confirmed tickers into the assignment pass
  vs operator-tap per member. **Rec: auto-inject** — it's LLM-validated, cooldown-guarded,
  reversible, no money; operator-tap doesn't scale to the daily cadence.
- **F-C — auto-promote inheritance (G3)**: let coverage_probe cohorts ride the existing
  nightly ≥3-member auto-promote vs surface-only until S4 evidence. **Rec: surface-only for
  the first 2 weeks, then inherit** — the one place I'd sequence on evidence: it's the single
  fastest path from probe-noise to live `mi_themes`, and 2 weeks of side-by-side costs nothing.
- **F-D — market-adjusted co-movement**: subtract SPY same-day move before the 1% floor.
  **Rec: yes in v1** (one extra `get_daily_moves` call; kills the rally confound).
- **F-E — the kill bar (§5)**: sign the pre-committed thresholds before the numbers come back.
  **Rec: sign as written** — that's what makes the sizing evidence-first instead of
  post-hoc-rationalized.

## 5-RESULTS — sizing run on prod 2026-07-13 (Opus; read-only) + verdict

**Q0 — the decisive result: the historical instrument is BLIND to MODERATE.** Clean: 47 MODERATE,
but only **4 have `grounded_text`** (9%) and **6 a judge verdict** (13%); 41/47 have NULL
`in_active_theme`. Polluted: 36, 3 corpus, 6 judge. **MODERATE alerts were never instrumented**
(corpus/judge/shadow are all effectively HIGH-gated) — confirms Fable's uncertainty #7 as the
binding constraint.

**Q1 — MODERATE tracked membership is ~nil:** clean = 1 Mainstream + 46 NONE; polluted = 2 Fading
+ 1 Mainstream + 33 NONE. **Zero Accelerating MODERATE in either period** (Accelerating is M1-d's
only clean trigger). So the tracked-half boostable population ≈ 0 historically.

**Q3a — un-sizable:** of the ~7 corpus-visible themeless MODERATEs, **0 had a peer-mention**. This
is NOT a true zero — it's the Q0 blindness (only 9% have the corpus the instrument reads).

**Q4 — outcomes (the informative one):**
| pop | n | settled | avg 5d | med 5d | wins ≥5% |
|---|---|---|---|---|---|
| A_accel_tracked (MOD+Accel) | 1 | 1 | +32.3% | +32.3% | 1 |
| B_indep_blindspot | 0 | – | – | – | – (instrument blind) |
| C_all_moderate | 83 | 63 | **+13.2%** | +6.2% | 40 (63%) |
| D_all_high | 157 | 129 | **+10.4%** | +7.0% | 74 (57%) |

**MODERATE alerts perform ≈ HIGH on raw 5d forward return** (a separate, arguably bigger "right
EPs" signal — but raw forward return, not realized-R; needs an entry/stop/exit study before it's
actionable).

### Verdict (corrected by the evidence)
1. **The kill bar (F-E) is UN-EVALUABLE on history** — `B_indep_blindspot`=0 is instrument
   blindness (9% corpus), not the true rate. Applying the literal "< 5% → kill" to a blind
   instrument would misread absence-of-measurement as absence-of-gap. **Do not kill on this.**
2. **S1 is not just "cheapest evidence unlock" — it is the ONLY path to ANY MODERATE evidence.**
   You cannot size or decide the grade half from history; the instruments must run FORWARD on
   MODERATE first. **⚠ S1 as written (widen the shadow gate) is necessary but NOT sufficient:
   Q0 shows MODERATE alerts also lack `grounded_text`** (the probe's name-match corpus) **and the
   judge verdict** — so S1 must also ensure the corpus (and ideally the judge shadow) is built for
   MODERATE, or the probe stays blind. This is a design amendment, not a blocker.
3. **The tracked-Accelerating half is ~empty historically (Q1) and stays dark (M1-d).** The loop's
   value, if any, is the pay-forward instrumented forward — which only S1+S2 can reveal.

**Bottom line:** the design is sound and safety-verified (source wall confirmed in code), but the
evidence-first step proves the decision cannot be made from history — MODERATE is un-instrumented.
The honest next step is the SAFE forward instrumentation (S1 corrected to include the MODERATE
corpus + S2 probe), accrue, then decide the grade half against the kill bar on real forward data.
Separately, Q4's MODERATE≈HIGH forward-return finding merits its own realized-R study.

## 9. Sign-off
- [ ] Forks F-A…F-E ruled
- [x] §5 queries run (parent) 2026-07-13 → results above; kill-bar un-evaluable on history (instrument blind) → S1-first
- [ ] S1–S3 build authorized / redirected
