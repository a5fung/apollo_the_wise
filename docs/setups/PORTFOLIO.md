# Stocks in Play — Project Master

> **The umbrella for ALL setup/entry work (operator-named 2026-05-31).** One idea: we surface
> **stocks in play** from any setup; some Apollo **auto-trades**, some **inform the operator**
> to act; each stock-in-play can combine multiple setups. This project **unifies** the prior
> Stocks-in-Play workstream (ADR 0004 — the `mi_stocks_in_play` table + 3-axis maturity model)
> with the setup/entry **taxonomy + relationship map** below. `automation_class` (apollo-traded
> vs inform-operator) is the ADR-0004 axis; **SELECTION ≠ ENTRY ≠ QUALIFIER** is the anatomy.
>
> **STATUS:** framing AGREED (operator "aligned", 2026-05-31); per-item decisions OPEN.
> **NOT change-authorizing** — actual setup changes follow `docs/setups/CHANGE_PROCESS.md`.
> Kickoff = task #167; tracks + dates in §Workstreams. Phases verified vs `mi_strategies`
> 2026-05-31.

---

## ✅ KICKOFF DECISIONS — 2026-06-02 (#167, accelerated)

Operator decisions locked this session. **Ships follow their gates; nothing deployed today.**

1. **#65 — 9M Day-2: add the revenue-stage gate now.** Mirror MAGNA53's `is_revenue_stage` on `9m_day2` → kills the clinical-biotech class (ROIV/PURR) the mechanical ORB wrongly enters, keeps the rest of the cohort accruing toward the #65 evidence gate (N≥10, ~7/15). De-risk without freezing. **NOT** (c) demote-to-shadow (that would freeze the cohort at N=4 forever). → **Ship: next session via CHANGE_PROCESS** (read `ninem.md` SSoT + `safeguards.md`, N-evidence, advisor sign-off, SSoT-in-same-commit). *(Resolves redline agenda item 1.)*

2. **#150 — entry-fill reliability IS a 6/22 cutover gate.** The default 1m-ORB entry silently under-fills ~18% of cancelled entries, winner-skewed (CADL +17%, three +8% missed). Likely a paper-sim artifact (live routes to the real exchange) — but it corrupts the paper Gate-3 realized-R the cutover rests on. **Before 6/22:** (a) run the elect-vs-fill diagnostic (confirm paper-sim, not a live-path defect); (b) correct Gate-3 realized-R for the under-filled winners via #180's would-have-filled cohort. Don't decide the flip on the uncorrected, winner-skewed sample. → **adds a 4th hard cutover gate** alongside Gate-1 / Gate-3 / #151.

3. **Flag/consolidation class → paper at 7/15, gated on #168.** When the first tight-range technique (#94–98) hits N≥10 (~7/15), spin a paper strategy — but only behind the #168 selection-quality overlay (high-RS / theme-backed / 9M-cohort / liquid / catalyst) so only *buyable* names trade, not raw pattern fires. *(Resolves redline item 3; threads item 7/#168.)*

**New axis folded into Layer 2 — entry-execution RELIABILITY.** The doc asked *which* entry technique; #150 showed the *chosen* entry can silently fail to execute. Layer 2 now has two axes: **(i) technique-fit** (which entry the stock's shape calls for) and **(ii) execution-reliability** (does it actually fill, and is the fill measured). The entry-execution-observability thread = #150 (diagnosis + elect-vs-fill mitigation), #177 (fill-shadow settle fixed 6/2), #180 (unified EOD would-have-filled pass — uses the LIMIT not the trigger), #178 (`/setup`+`/why` merge).

**Still open (next pass, not urgent):** naming (MAGNA53 → gap-momentum scorer, redline item 5) · RMV-Phase-2 sequencing vs 9M re-arch (6/9, item 6) · the #168 filter's quality-dim selection (telemetry-first — measure which dims separate forward-winners before filtering).

---

## The organizing principle: SELECTION ≠ ENTRY ≠ QUALIFIER

The single most useful reframe (your own framing, made explicit): a setup is one of **three different kinds of thing**, and we've been conflating them.

- **SELECTION** — *what stock to watch.* Generates a cohort/watchlist. (EP, 9M, themes, parabolic-short universe.)
- **ENTRY** — *how/when to get in*, on an already-selected stock. (ORB, flag-breakout, support-test, MA-pullback, U&R, fishhook, wick-fill, low-vol-rest.)
- **QUALIFIER** — *a score/filter that gates or ranks* selection or entry, never traded alone. (catalyst_type, theme membership, RMV, regime.)

**The core defect this exposes:** today MAGNA53 and 9M each hardcode ONE entry (1-min ORB; Day-2 ORB w/ prior-low stop). The methodology says selection should produce a watch-cohort, and entry should be *chosen* from the entry layer based on how the stock sets up. That mismatch **is** the 9M problem (#65) and is why the entry-technique detectors exist but only run in shadow today (the 9M cohort IS wired into their universe via P7.3b — see the relationship map — they just don't *trade* yet).

---

## Workstreams, priority & dates (the project tracks)

One mental model — **stocks in play, surfaced from any setup; some Apollo auto-trades, some inform the operator; each can combine setups** — across these tracks:

| WS | Track | What | Priority | Key dates / gates |
|---|---|---|---|---|
| **A** | **SIP infrastructure** | Make `mi_stocks_in_play` ingest ALL selection signals + carry `automation_class` (apollo-traded vs inform-operator). TODAY it holds only `sugar_baby_cohort` (193, all `informational`) — ADR 0004's multi-source/3-axis vision is under-built. The literal "combine the two." | **P1 (enabler)** | scope in #167 |
| **B** | **Selection** (Layer 1) | MAGNA53 EP · 9M EP · themes · parabolic — cohort generators | P1: MAGNA53 + theme/narrative (North Star) | MAGNA53 cutover 6/22; theme gate ~Q4 |
| **C** | **Entry techniques** (Layer 2) | the 5 tight-range (#94–98) + ORB variants + fishhook + wick | **P2** (your #2-to-trade = flag/consolidation class) | graduation N≥10 **7/15** |
| **D** | **9M re-architecture** (#65) | standing 9M-entry telemetry + Day-2-ORB-legacy → flag-path decision | P2 | telemetry build in #167; gate 7/15 |
| **E** | **Qualifiers** (Layer 3) | catalyst_type · RMV · theme-membership-gating | P2/P3 | RMV Phase-2 **6/9**; theme gate ~Q4 |

**Kickoff** = the #167 session (deep prioritization + relationship map + per-WS task breakdown). **Reminders** ride the data-gated-review dates above — the Sunday weekly review surfaces ripe items automatically. Existing tasks bucket in: #65→D · #97/#98/#134/#146→C · #160-166 (theme/U&R)→B/C · #149/#152→B-quality · #167 = kickoff.

---

## Layer 1 — SELECTION (what to watch)

| Setup | Table | Phase / treatment | Graduation intent | Priority |
|---|---|---|---|---|
| **MAGNA53 EP** (gap + catalyst-enum + conviction floor) | `mi_ep_alerts` | **paper** (auto 1m-ORB) | → live (6/22 gate) | **P1** — the live-$ candidate. *But* theme/narrative-blind (North Star defect) → admits beta gappers. Naming is wrong (it's a gap-momentum scorer, not "EP"). |
| **9M EP** (Pradeep volume anomaly) | `mi_9m_ep_alerts` (intraday) → `mi_9m_day2_candidates` (EOD sugar baby) | **paper** (auto Day-2 ORB, prior-low stop) | **re-architect (#65)** | **P2/P3** — *selection is good; the hardcoded Day-2 ORB entry is the problem.* |
| **Persistent 9M-volume cohort** | `mi_sugar_babies_cohort` (41) | **inform-only** (observational) | stays a watch-universe | P2 — the watch-universe. **ALREADY wired into the flag universe (P7.3b, shadow):** every 9M EP enters `mi_flag_candidates` tagged `ninem_universe_watch` (today: 18 WATCH / 7 TIGHTENING). The entry-techniques that would trade them are shadow (graduate 7/15). |
| **Theme engine** (RS + sector clustering) | `mi_themes` (+ shadow `mi_theme_candidates_shadow`) | live (feeds EP +10) + **shadow** (nascent discovery, ADR 0007) | advisory → **gating** (Phase 6, ~Q4) | **P1-adjacent** — North Star; theme = Pradeep's #1 catalyst. |
| **Parabolic short** (TI1) | (shadow telemetry) | **shadow** | → paper on its own evidence | P-low (short-side; separate track) |

## Layer 2 — ENTRY (how to get in, on a selected stock)

| Entry mechanic | Table / strategy | Phase | Graduation | Notes |
|---|---|---|---|---|
| **1-min ORB** | magna53 / 9m_day2 | **paper** | → live | The current default entry for BOTH EP + 9M. |
| **5-min ORB** | `shadow_orb_5m` | shadow | N≥30 paired | Selectivity variant of ORB (sheds bar-1 noise; costs gap-and-go winners). |
| **Flag breakout** (#94) | `mi_flag_breaks` | shadow | N≥10 (7/15) | Break above `base_high` + vol. Entry #1 of the tight-range taxonomy. |
| **Support-test** (#95) | `mi_flag_support_tests` | shadow | N≥10 (7/15) | Bounce off `base_low` (≤2% touch). Tightest stop. |
| **MA-pullback** (#96) | `mi_flag_ma_pullbacks` | shadow | N≥10 (7/15) | Pull back to SMA10/20, light volume. |
| **U&R Undercut & Rally** (#98) | `mi_flag_undercut_rally` | **shadow (new 5/31)** | N≥10 (7/15) | Undercut `base_low` (2–8%) → reclaim. Morales/OWL. |
| **Low-vol rest** (#97) | — | **NOT BUILT** | — | Entry #4; unbuilt gap. |
| **Fishhook** (TI3) | `fishhook_v3` | shadow | N≥10 (6/15→7/15) | **Delayed entry for failed-day-1 EPs** — pullback/reclaim on subsequent days. |
| **Wick-fill** (P22/TI2) | `wick_fill` | shadow | N≥30 fills, fill-rate≥0.5 | Fill on an intraday wick + ride recovery. Execution edge, not a pattern. |

## Layer 3 — QUALIFIERS (score/filter; never traded alone)

| Qualifier | Where | Phase | Graduation |
|---|---|---|---|
| **catalyst_type** (C1, fire-identity) | `mi_ep_alerts.catalyst_type` | **advisory (live)** | → input to meta-rubric (Phase 5) |
| **RMV** (relative measured volatility = tightness) | `mi_flag_candidates.rmv_5d/15d` | **Phase-1 telemetry** | Phase-2 eval **6/9**; → flag-entry trigger qualifier |
| **Theme membership** | EP score (+10) | live (decorative) | → load-bearing gate (Phase 6) |
| **Regime** | `mi_regime` | live | calibration input |

## Unifying surface — the project spine
- **Stocks-in-Play** (`mi_stocks_in_play`, ADR 0004) — the methodology-wide watchlist that surfaces a *stock* (from any Layer-1 signal); the *entry technique* (Layer 2) is the orthogonal axis, and `automation_class` marks **apollo-traded vs inform-operator**. This IS the project's spine — the table that resolves the selection≠entry conflation. **But it's barely built: today it ingests only `sugar_baby_cohort` (193 rows, all `informational`).** Wiring all selection signals + the entry layer into it, with the automation_class axis = **WS-A** (the literal "combine the two prior workstreams").

---

## Relationship map (how setups feed each other)

```
                    ┌─────────────── SELECTION ───────────────┐
   MAGNA53 EP        9M EP            Theme engine      Parabolic
   (gap+cat)         (vol anomaly)    (RS+sector)       (short)
      │                 │                 │                │
      │            ┌────┴────┐            │                │
      │         EOD sugar   persistent    │ (+10 / future  │
      │         baby        9M cohort     │  gating;        │
      │         (Day-2)     (watch, 41)   │  nascent disc.) │
      │            │            │         │                │
      ▼            ▼            ▼         ▼                ▼
   ┌──────────────────── STOCKS-IN-PLAY (watch) ──────────────┐
   │   a selected stock now needs an ENTRY (how to get in)     │
   └───────────────────────────┬──────────────────────────────┘
       consolidates / tightens  │  (RMV-low qualifies tightness)
                                 ▼
            ┌─────────────── ENTRY LAYER ───────────────┐
   1m/5m ORB · Flag-breakout · Support-test · MA-pullback ·
   U&R · Low-vol-rest(unbuilt) · Wick-fill
                                 ▲
   failed day-1 EP ─────► FISHHOOK (delayed re-entry on later days)
```

**Worked examples (yours):**
- **9M EP → watch-cohort → consolidation (low RMV) → flag-breakout entry.** This path is **ALREADY wired (P7.3b, shadow)** — 9M EPs enter the flag universe and some progress to TIGHTENING. The mechanical **Day-2 ORB is a LEGACY/BRIDGE** entry running in *parallel* (paper). #65 = *which mechanism trades the cohort, and when* (the entry-techniques graduate 7/15) — NOT a missing wire.
- **Fishhook = delayed EP entry** — for EPs that failed day 1; the entry comes on a later-day pullback/reclaim. Tied to the EP setup, not standalone.
- **MAGNA53 EP** currently = selection **and** entry (1m ORB) fused. Same conflation as 9M.

---

## Open decisions for the session (the redline agenda)

1. **#65 — how to trade 9M (analyzed 2026-05-31, advisor-reviewed):** methodology direction is **SETTLED** (9M = watch-universe; entry = tightness→expansion / flag class) and **already wired in shadow** (P7.3b). The mechanical **Day-2 ORB is a legacy/bridge** running in parallel (paper): N=4 clean-closed = **−$1,541, 75% loss**, and it mechanically enters clinical biotechs (ROIV/PURR) the EP revenue-stage gate would block. *Which mechanism trades the cohort* is a **layer-2 evidence-gated call — NOT a tenet call** — so it does **not** justify demoting on N=4. Operational 3-way (operator's call, not pre-committed):
   - **(a)** leave Day-2 ORB running to the #65 gate (N≥10, earliest 7/15);
   - **(b)** add the **revenue-stage gate now** (mirror MAGNA53 `is_revenue_stage`; kills the ROIV/PURR class, lets the rest accrue) — *recommended if we ship anything today*;
   - **(c)** demote `9m_day2`→shadow now — **but this FREEZES the cohort at N=4 forever** (shadow = no fills → #65 never gets its evidence). Highest-cost; do only if we're certain we'll never trade the mechanical path.
   Caveat: at ~4 closed / 2 months, **N≥10 likely isn't reached by 7/15** → the decision may be made on methodology + qualitative cohort review at whatever N exists. Another reason (b) > (c): the gate keeps the slow accrual alive while de-risking it.
2. **The 9M→entry wiring already EXISTS** (P7.3b `ninem_universe_watch`, shadow) — *corrects this strawman's earlier "no wired entry" premise.* The real gap is (i) entry-techniques are shadow (graduate 7/15) and (ii) the legacy Day-2 ORB trades in parallel. It's a **graduation + legacy-retirement sequence**, not a missing wire.
3. **Priority of the flag/consolidation class (your stated #2 after MAGNA53)** — should it get a paper strategy once an entry technique graduates (N≥10, 7/15)?
4. **Graduate-or-not calls:** which Layer-2 detectors are *meant* to reach live (flag class?) vs stay data-only forever (5m-ORB as just a selectivity study?).
5. **Naming:** rename "MAGNA53 EP" to reflect it's a gap-momentum scorer, not the EP setup? (separate, non-urgent)
6. **RMV (6/9)** is the qualifier that makes "trade the cohort via consolidation" concrete — it's the tightness trigger. Sequencing: does the 9M re-architecture wait on RMV Phase-2?
7. **Entry-alert NOISE → actionability filter (WS-C; operator 2026-06-01, task #168):** flag-break (#94, ~5/day) + MA-pullback (#96, ~10/day) fire on *any* tightening/coiling flag candidate — ~15+/day, too noisy. Need a **selection-quality overlay** (high RS / theme-backed / 9M-EP cohort / catalyst present / liquid) so only *buyable* names surface, not raw pattern fires. Telemetry-first: measure which quality dims separate forward-winners before filtering. Same "quality overlay" idea as #65's flag-confirmation discriminator. WS-C × Layer-3.

---

## Resolved confirms (2026-05-31, read-only)
- **RMV Phase-2** (`rmv_phase2_evaluation`, earliest 6/9): a **qualifier on flag candidates** — `rmv_5d/15d` persisted per `mi_flag_candidates` row since Phase-1 (5/9). Phase-2 tests whether RMV-low catches tight setups `_compute_fresh_tightening` MISSES, or is redundant. So it's a tightness *score*, not a standalone trigger. (WS-E)
- **`mi_stocks_in_play` ingest**: TODAY only `sugar_baby_cohort` (193, all `automation_class=informational`). NOT multi-source — ADR 0004's other source slots are unbuilt. → the core **WS-A** gap.
- **Parabolic short**: real tables exist (`mi_parabolic_candidates` / `mi_parabolic_exclusions`); `parabolic_short` strategy = shadow. (WS-B, P-low.)
- **Convergence** (sugar-baby × flag): an **alert TAG** (Stage-2 prepend), not a standalone setup — a qualifier-style co-occurrence flag, not its own WS.
