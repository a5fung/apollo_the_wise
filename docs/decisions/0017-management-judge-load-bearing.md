# ADR 0017 — P3 Management Judge: the load-bearing design (D-1, #427)

**Status:** PROPOSED (2026-07-05, Fable design block D-1) — awaiting operator sign-off (§11).
**Extends** ADR 0014 (the shadow seed — LIVE since 6/18, 15 decision rows through 7/1). 0014 stays
the record of the shadow; THIS doc is the executable spec for everything 0014 deferred: the
character/pivot engine, intraday triggers, the authority ladder to load-bearing, and the
enum→mechanical execution mapping. Requirements source for pivots/character:
`docs/methodology/pivots-and-stock-character.md` (operator principles, 6/11 — treated as SSoT).
**Baseline KPI:** aggregate MFE capture 18% (N=10, #306 STEP-0); the pillar bar is **>50%**.

Contract: pure-execution depth. A builder executing §10's cards needs zero design judgment;
every open fork is in §11 for the operator, nothing buried.
**Adversarial review 7/5 (Sonnet, claims-verified vs source): 3 HIGH + 3 MED/LOW findings —
ALL corrected below** (§3.1 T2 mechanism, §3.3 breaking-not-additive migration, §4 halt
coverage, §5 PARTIAL_TAKE signature + FORCE_EXIT respec, §2.2 schedule referent).

---

## 1. Architecture — three components

```
(A) CHARACTER/PIVOT ENGINE          (B) THE JUDGE                    (C) AUTHORITY LADDER
deterministic, no LLM               LLM, bounded enum (0014)          L0 shadow → L3 bounded-full
per-ticker profile + ranked         + richer payload                  each rung: evidence gate +
pivot candidates                    + intraday triggers               CHANGE_PROCESS + sign-off
        └────────────── feeds ──────────┘                                   │
                                    verdict + params ──── maps via §6 ──────┘
                       MECHANICAL LAYER stays the floor: stops/partials/time-stops
                       run regardless; the judge can only ADD risk-reduction (§5).
```

## 2. Component A — the character/pivot engine (deterministic tier)

### 2.1 `mi_ticker_character` (new table)
```
ticker TEXT PK · computed_at TIMESTAMPTZ · trend_start DATE (current-trend anchor: last
close<200MA date or last >50%-in-5d re-rating, whichever later) · ma_resolution JSONB
({"10":{"touches":n,"resumes":n},"20":{...},"50":{...}} over the trend window) ·
undercut_depth_p50/p90 NUMERIC (% beyond the resolved MA on undercut episodes) ·
pullback_duration_p50 INT (days) · vol_contraction_ratio NUMERIC (pullback vol / preceding
leg vol, median) · sample_pullbacks INT · profile_class TEXT (derived label, §2.3) ·
stale BOOLEAN DEFAULT FALSE
```
Pullback episode detection (pure function over `mi_daily_closes`, same source rs_engine uses):
a pullback = ≥2 consecutive closes below the prior 5-day high with the name above its 200MA;
resolution = which MA (10/20/50, ±undercut_depth) the episode's LOW sat nearest when the
subsequent close reclaimed the 5-day high. Undercut = low beyond the resolving MA, in %.
`sample_pullbacks < 3` ⇒ profile is LOW-CONFIDENCE (flag, don't fabricate — the judge payload
says "insufficient character history" rather than a fake profile).

### 2.2 Jobs
- **Weekly recompute** (Sun 18:30 ET — an idle evening slot between the 18:00 crypto ingest and 19:00 category refresh; NB the weekly review itself runs Sun 08:00 ET): all tickers with an open
  position, any alert in 30d, or on the flag/coil boards (~bounded set, not the 9,700 universe).
- **On-demand**: entry pipeline requests a profile at fill time (cache-read; compute if absent);
  freshness rule — recompute if `computed_at` > 7d old OR a >50%-in-5d move occurred since
  (the re-rating reset from the SSoT's anti-pattern list; §11-F5 sets the exact threshold).

### 2.3 Ranked pivot candidates (function, not table)
`rank_pivots(ticker, profile, bars) -> [(pivot_type, level, confidence)]` — computable tier only
in this ADR: resolved-MA (from profile), gap-day low, prior swing low, entry-day low. Structural
tier (congestion/volume shelves) arrives with chart-vision maturation (P2, D-5) and slots into
the same ranked list — the interface is built for it now. Confidence = the profile's
touch-resume frequency for that reference (e.g. NBIS-class: 20MA 0.8 with 2.1% undercut
tolerance; MNTS-class: gap-day-low + 21EMA).

## 3. Component B — judge maturation (extends `mgmt_judge.py`)

### 3.1 Triggers (each writes the same table, `trigger_type` column; rate-bounded)
| ID | Trigger | Detection | Cadence bound |
|---|---|---|---|
| T0 | Daily pass | 16:00 ET job (EXISTS, 0014) | 1/day/position |
| T1 | Gap-against | 9:25 ET pre-open check: snapshot price < entry AND < nearest ranked pivot | 1/day/position |
| T2 | +2R excursion | piggybacks **`track_open_position_extremes`** (the existing 5-min `track_position_extremes` job — which IS the dedicated 5-min poll Gemini's F3 modification asked for; NOT a tick stream): fires when high-water crosses entry + 2R, **AND the sustain check passes at dispatch: the CURRENT 5-min observation must still be ≥ entry + 1.8R** (Gemini am. 7/5 — a single 5-min wick re-arms instead of firing; kills the spike-then-collapse slippage case) | once/position lifetime |
| T3 | Theme-state change | theme of position transitions to Fading/Retired in the nightly run → next-morning 9:25 batch | per transition |
No new polling loops — T1/T3 ride scheduled points, T2 rides existing position-sync events
(§11-F3 confirms). Per-position daily LLM budget: max 3 judge calls/day (T0 + 2 triggered).

### 3.2 Payload additions (to 0014's baseline)
Character profile + ranked pivots (compact text rendering) · peak excursion + capture-so-far
(`(px−entry)/(peak−entry)`) · theme health (stage + days-in-stage) · chart image + structural
verdict (REUSES the #267/#343 grade-judge render rails — same image discipline, Gemini am.2) ·
mechanical posture (trail mode, partial state, time-stop clock) · the #306 tune state once
STEP-3 lands. Prompt contract: the judge PROPOSES against the stock's OWN ranked pivots
("mechanics execute, judge proposes" — SSoT principle); rationale must cite which pivot.

### 3.3 Output schema evolution (`mi_position_mgmt_decisions` — additive migration)
`+ trigger_type TEXT CHECK IN ('daily','gap_against','excursion_2r','theme_change')`
`+ proposed_partial_fraction NUMERIC NULL CHECK (IN (0.33, 0.5))`
`+ proposed_stop_price NUMERIC NULL` — **hard rule: valid only if ≥ current stop (never-widen);
violating proposals are logged + treated as HOLD (fail-safe, counted in the eval)**
`+ character_snapshot JSONB NULL · + chart_verdict TEXT NULL · + executed BOOLEAN DEFAULT FALSE ·
+ execution_ref TEXT NULL` (order id when L2+ acts). The 4-verdict enum is UNCHANGED
(HOLD/PARTIAL_TAKE/TRAIL_TIGHTEN/FORCE_EXIT — bounded-enum contract reaffirmed, Gemini am.4).
**⚠ BREAKING, not additive (review 7/5):** the table today has `UNIQUE (position_id,
decision_date)` and the writer upserts on that key (day-grain by 0014 design) — a second
same-day trigger would silently OVERWRITE the first. The migration must: drop that constraint
→ `UNIQUE (position_id, decision_date, trigger_type)` → backfill existing rows
`trigger_type='daily'` → update `insert_position_mgmt_decision`'s ON CONFLICT target. Ships
in C3 with both-direction tests (same-day T0+T2 coexist; duplicate T0 still idempotent).

## 4. Component C — the authority ladder

| Rung | Authority | Entry gate (ALL required) |
|---|---|---|
| **L0 SHADOW** (now) | none — telemetry | live since 6/18 |
| **L1 ADVISORY** | disagreements surface: a 16:10 digest line + the position board flags "judge proposes PARTIAL (cites 20MA pivot)"; operator acts manually | ≥30 operator-labeled rows AND ≥80% label-agreement on the ACT verdicts (PARTIAL/TIGHTEN/EXIT — precision on labels, attribution-correctness not outcome) + sign-off |
| **L2 RISK-REDUCING AUTO** | judge AUTO-EXECUTES exposure-REDUCING actions only: PARTIAL_TAKE (≤0.5) and TRAIL_TIGHTEN (≥ current stop). NEVER auto-FORCE_EXIT, never anything risk-increasing. Real-time Telegram per action; halt coverage per the correction below | L1 ≥3 weeks + ≥50 labels + counterfactual ledger shows 0 harmful would-have-executions + CHANGE_PROCESS + sign-off |
| **L3 FULL BOUNDED** | + auto FORCE_EXIT | L2 ≥4 weeks clean + capture_pct trending toward the bar + its own sign-off (H2/M5 horizon) |

**Halt coverage (review 7/5 — the original claim was FALSE):** today's `/pause` halts NEW
ENTRIES ONLY (`agent.py::_handle_pause_command` — "open positions are untouched"); nothing in
the exit path reads it. C6 therefore MUST ship an exit-lane halt: the L2 executor checks the
same `mi_safeguard_state` halt row AND the `MGMT_JUDGE_AUTHORITY` toggle before EVERY action,
and `/pause`'s reply text is extended to state it also freezes judge auto-actions (operator
surface change, documented in the C6 CHANGE_PROCESS entry). Until C6, no lane exists to halt.

**Invariants at every rung:** the mechanical layer is a FLOOR the judge cannot lower (no stop
widening, no partial cancellation, no breaker override — safeguards precede judge actions in
code path order); every auto-action routes through the SAME #151-hardened functions with their
never-naked invariants; per-position auto-action budget 1/day at L2; all actions
`account_mode`-isolated and audit-rowed. Demotion is automatic: any harmful executed action
(operator-labeled) drops the lane one rung pending review (the P5 auto-demotion principle,
applied here first).

**Conviction sizing = a separate lane on the same ladder** (entry-side): grade-judge tier →
`position_size_multiplier` (plumbing exists, #65). Starts SHADOW (log the would-be multiplier
per entry) when L1 starts; promotes with the same discipline. Portfolio-aware curve hands off
to P5. (§11-F4 sets timing.)

## 5. Enum → mechanical mapping (L2+; exact functions + guards)

| Verdict | Executes via | Guards (in order) |
|---|---|---|
| HOLD | no-op | — |
| PARTIAL_TAKE | `execute_partial_exit(trade_id, shares, force=False)` — the #151-hardened path; **shares = round(remaining_shares × fraction)** computed by the executor (the function takes an absolute count, not a fraction — review 7/5). Note: it carries its own `_PARTIAL_EXIT_PAUSED` module kill-switch, an independent inherited gate | market hours · fraction ∈ {0.33,0.5} · not already partial_taken that day · never-naked coverage rules inside the function |
| TRAIL_TIGHTEN | the stop-replace path (`replace_order` w/ verify-stop-live, ADR 0009 coverage invariant) | proposed ≥ current stop · ≥1 tick below last price · market hours · replace (not cancel+place) |
| FORCE_EXIT (L3 only) | **a new `execute_full_exit(trade_id)` built as the fraction=1.0 generalization of `execute_partial_exit`'s guarded stop-replace/sell interlock** (which already solves stop-holds-shares + never-naked sequencing). The `/timestop` path is NOT reusable (review 7/5: it places a next-open OPG sell, cancels NO stop, and its query is hardcoded `signal_type='9m_day2'` — 'exit now' would become 'exit tomorrow' beside a live stale stop) | L3 only · operator real-time notify · daily budget |

## 6. Outcome metrics (the eval spine)
1. **capture_pct** (the #306 weekly KPI) — THE north metric; 18% baseline → >50% bar.
2. **Per-verdict counterfactual R**: for every decision row, forward outcome (5d/close-of-trade)
   vs the verdict — "FORCE_EXIT calls saved X R" / "HOLD calls cost Y" — computable from shadow
   rows already accruing; a nightly backfill query, no new collection.
3. **Label precision** per verdict class (operator sittings, #307's ritual carries them).
4. **Ladder-health**: harmful-action count (auto-demotion input), fail-open rate, trigger volume.

## 7. Failure/safety matrix
LLM null/timeout → fail-open to mechanical (exists) · malformed/out-of-enum → HOLD + audit ·
never-widen violation → HOLD + counted · double-trigger race → per-position daily budget +
advisory-lock around the execute step · market closed → queue T1/T3 to next open, drop T2 ·
degraded price read → skip position this pass (the #137 rule: an unreadable price is never
"exit") · postgres/table down → job fails loud (audit_wrap) · `/pause` halts L2+ lane instantly ·
account_mode isolation identical to entry pipeline's.

## 8. What this ADR does NOT change
Entry decisions (ADR 0011's domain) · the mechanical exit system's parameters (the #306 STEP-3
tune is a separate operator decision feeding the same mechanics) · safeguards/breakers ·
anything at L0/L1 that touches an order (nothing does until L2 + sign-off).

## 9. Interactions
- **#306 STEP-2/3 (exit tune)**: tunes the mechanical FLOOR the judge stands on; ships
  independently. The judge payload carries the tune state; the capture_pct KPI serves both.
- **D-2 experience stack**: precedent retrieval later feeds the judge's payload ("the last N
  times this name/class was here…") — interface reserved (a `precedents` payload field), not built here.
- **P2 chart vision**: structural-tier pivots slot into §2.3's ranked list when D-5 lands.
- **#91 time-stop**: unchanged; its clock is payload context.

## 10. Build cards (execution order; each ships alone)
| Card | Scope | Class |
|---|---|---|
| C1 | `mi_ticker_character` schema + episode-detection pure functions + weekly job + tests (golden NBIS/MNTS fixtures from their daily bars) | Sonnet card |
| C2 | `rank_pivots` + payload rendering + prompt update + schema migration (§3.3) + tests | Sonnet card |
| C3 | Triggers T1/T2/T3 (ride existing jobs/sync) + daily-budget guard + tests | Sonnet card, Fable review (touches sync surroundings, read-only) |
| C4 | L1 advisory surfaces (digest line + board flag) + label plumbing into #307's sitting | Sonnet card |
| C5 | Counterfactual ledger (nightly backfill query + weekly-review line) | Sonnet card |
| C6 | L2 execution mapping behind `MGMT_JUDGE_AUTHORITY` runtime toggle (default L0) + #151-style exercise against paper Alpaca | **careful path — Fable-led, NOT a card**; gated on the L2 evidence gate |
Sequencing: C1→C2 (→ judge payload richer, still shadow) → C3 → C5 accrues → L1 gate check →
C4 → L1 runs ≥3wks → C6 built-dark → L2 sign-off flips the toggle.

## 11. Operator sign-off forks (decide at D-review; recs first)
- **F1** L1 gate numbers: **≥30 labels / ≥80% act-verdict agreement** (rec) — or stricter.
- **F2** L2 action set: **PARTIAL_TAKE + TRAIL_TIGHTEN only** (rec); FORCE_EXIT waits for L3.
- **F3** T2 detection: **ANSWERED (Gemini 7/5 + code reality)** — the mechanism is already a
  dedicated 5-min poll (`track_open_position_extremes`); the sustain-at-dispatch dampener
  (≥1.8R on the current observation) is adopted.
- **F4** Conviction-sizing shadow start: **with L1** (rec) vs after L2.
- **F5** Character reset threshold: **>50% move in 5d** (rec, from the SSoT example) — or tune.
- **F6** Sign-off on the ladder itself (the CHANGE_PROCESS anchor for every rung promotion).

## 12. Test plan
Unit: episode detection on golden fixtures (NBIS = 20MA-undercut class, MNTS = gap-low class,
a sub-3-pullback low-confidence name) · never-widen guard · enum/params validation · trigger
budget. Integration (pre-L2): C6 exercised against real paper Alpaca per #151 (partial +
replace paths) before any live authority. Regression: the routing/freeze suites extended; the
counterfactual queries pinned against a fixture cohort. Shadow-parity: L0 rows before/after C2
payload change compared for verdict drift (a payload change that flips verdicts is itself a
finding, reviewed before L1).
