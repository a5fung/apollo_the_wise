# Apollo Setup Portfolio — Taxonomy, Treatment, Priority & Relationship Map

> **STATUS: FRAMING AGREED (operator "aligned", 2026-05-31).** The SELECTION ≠ ENTRY ≠
> QUALIFIER structure, the layer assignments, and the relationship map are endorsed as the
> portfolio's mental model. **Per-item DECISIONS (the redline agenda) are still OPEN** — and
> this doc is **NOT** a change-authorizing SSoT: any actual setup change still follows
> `docs/setups/CHANGE_PROCESS.md` (evidence, advisor, per-setup SSoT). Built per task #167 /
> memory `project_setup_portfolio_taxonomy`. Phases verified vs `mi_strategies` 2026-05-31;
> items marked **? = confirm** are still unverified.

---

## The organizing principle: SELECTION ≠ ENTRY ≠ QUALIFIER

The single most useful reframe (your own framing, made explicit): a setup is one of **three different kinds of thing**, and we've been conflating them.

- **SELECTION** — *what stock to watch.* Generates a cohort/watchlist. (EP, 9M, themes, parabolic-short universe.)
- **ENTRY** — *how/when to get in*, on an already-selected stock. (ORB, flag-breakout, support-test, MA-pullback, U&R, fishhook, wick-fill, low-vol-rest.)
- **QUALIFIER** — *a score/filter that gates or ranks* selection or entry, never traded alone. (catalyst_type, theme membership, RMV, regime.)

**The core defect this exposes:** today MAGNA53 and 9M each hardcode ONE entry (1-min ORB; Day-2 ORB w/ prior-low stop). The methodology says selection should produce a watch-cohort, and entry should be *chosen* from the entry layer based on how the stock sets up. That mismatch **is** the 9M problem (#65) and is why the entry-technique detectors exist but aren't wired to the cohorts yet.

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

## Unifying surface
- **Stocks-in-Play** (`mi_stocks_in_play`, ADR 0004) — the methodology-wide watchlist that surfaces a *stock* (from any Layer-1 signal); the *entry technique* (Layer 2) is the orthogonal axis. This IS the architecture that resolves the selection≠entry conflation — it's Phase 1, needs the entry layer wired in.

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

---

## Confirm / gaps (my read may be stale — flag for correction)
- ? Exact RMV Phase-2 scope + whether it's a flag-candidate filter or a standalone trigger.
- ? Whether `mi_stocks_in_play` currently ingests all Layer-1 signals or only sugar-baby + flag-break slots (ADR 0004 said phased).
- ? Parabolic-short current telemetry state (TI1, deployed 4/25 — settled cohort?).
- ? Convergence (sugar-baby × flag) — currently an alert *tag*; is it a setup or just decoration?
