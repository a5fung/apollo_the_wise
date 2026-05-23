# ADR 0004 — Stocks in Play unified watchlist (per-stock maturity model)

**Date**: 2026-05-23
**Status**: Design — generalization gated on Sugar Baby Convergence prototype earning its keep over 2-3 weeks operationally (#84 shipped 2026-05-22)
**Authors**: Apollo Assistant (with user framing 2026-05-22 PM)
**Supersedes**: none
**Sequencing**: Step 2 of option (c) — Prototype (#83/#84) shipped 2026-05-22; this ADR captures the macro-scale architecture; full `mi_stocks_in_play` ship deferred pending prototype validation

## 1. Context

Apollo currently exposes ~7 fragmented detector surfaces:

| Surface | Detector | Telegram cmd | Phase |
|---|---|---|---|
| Persistent Sugar Babies cohort | `_sugar_babies_cohort_refresh_job` | `/sugarbabies` | observational |
| Continuation flags | `flag_detector.run_flag_scan` | `/flags` | shadow |
| Wick fill candidates | `wick_tracker` | `/wick` | shadow |
| Parabolic shorts | `parabolic_detector` | `/parabolic` | shadow |
| Fishhook V3 anchors | `fishhook_detector` | `/fishhook` | shadow |
| 9M sugar baby Day 2 candidates | `mi_9m_sugar_babies` (#82 rename pending) | (in evening briefing) | paper |
| EP HIGH alerts | `ep_detector` + `ninem_detector` | (live Telegram) | paper/live |

Each surface has its own command, its own evening-briefing section, its own promotion threshold, and its own implicit notion of "ready." The operator must mentally aggregate across these surfaces to answer "what's actionable today?"

**Trigger** (2026-05-22 PM): user shared a Pradeep Bonde tweet showing a 3-stage convergence on QBTS — `Sugar Baby in cohort → tight, vol compresses → expansion day with news/catalyst`. The 3-way intersection cuts across detector surfaces, suggesting that the current per-detector view fragments a signal that's actually unified at the *stock* level.

User reframed: *"all strategies with stocks mature to ready state should move into the stocks in play list, and each stock in there will have a reason why it was added, and the full watchlist are stocks waiting for catalyst to be traded."*

**Intended outcome**: a per-stock maturity model that mirrors the per-strategy `mi_strategies.phase` model already in place, with an explicit user-vs-Apollo trade division that can evolve as LLM capability grows.

## 2. The three maturity axes

All three coexist on a single row in the proposed `mi_stocks_in_play` table.

### Axis 1 — Per-strategy phase (already exists)

`mi_strategies.phase`: `shadow → paper → live`. Governs whether the strategy submits to a broker account. No change in this ADR.

### Axis 2 — Per-stock maturity (new framing)

```
identifying → watching → pattern-meeting → ready → trade
```

Each detector advances stocks through its own ladder.

| Stage | Meaning | Example |
|---|---|---|
| identifying | Detector noticed the ticker once | First-time COILED on flag detector |
| watching | Detector keeps it in lookback but not ready | Sugar Baby cohort member without recent flag activity |
| pattern-meeting | Detector criteria partially met | TIGHTENING but base age <5d |
| **ready** | Detector's promotion threshold satisfied; ticker enters `mi_stocks_in_play` | COILED + base ≥10d + 6mo runup |
| trade | Position open (handled by `mi_live_trades`) | — |

**`ready` is the ADR scope** — what `mi_stocks_in_play` tracks. Earlier drafts distinguished `ready` from `in-play` (multi-detector convergence), but they're operationally identical at the row level: each detector inserts a row when its threshold fires; consolidation across detectors happens at *read time* (briefing/`/inplay` aggregate per-ticker), not at storage time. Collapsing the two simplifies the schema with no loss of expressiveness.

### Axis 3 — Per-entry automation class (new framing)

```
informational → operator_only → apollo_eligible
```

Captures the user-vs-Apollo trade division explicitly. Defaults derive from detector + strategy phase.

| automation_class | Meaning | Current defaults |
|---|---|---|
| `informational` | Watchlist context, not a trade signal | Persistent Sugar Babies cohort (alone), shadow-phase detectors with no entry pipeline |
| `operator_only` | Requires human chart review + judgment | Convergence tag (Pradeep pattern recognition; not yet LLM-grade), flag COILED, wick fill, parabolic short, fishhook V3 |
| `apollo_eligible` | Auto-routes to entry_pipeline | MAGNA53 HIGH EP on paper phase, 9M Day 2 ORB on paper phase |

**Defined transitions** (each direction has an explicit trigger):

| From → To | Trigger | Mechanism |
|---|---|---|
| `informational → operator_only` | Ticker accumulates a second detector signal on the same `entry_date` (e.g., Sugar Baby cohort member also fires COILED that day). The cross-detector overlap is the operator-relevance signal — single-detector context is informational; multi-detector intersection earns operator attention. | Computed at insert time by a `_recompute_automation_class(ticker, entry_date)` helper that re-checks all rows for that (ticker, entry_date) and UPDATEs the existing `informational` row to `operator_only` if a second detector row was inserted today. |
| `operator_only → apollo_eligible` | N≥10 settled positive outcomes (forward-return validation backtest passes) AND explicit user UPDATE. Never auto-promotes — automation expansion requires user-in-the-loop. | Manual SQL `UPDATE mi_stocks_in_play SET automation_class='apollo_eligible' WHERE source_detector=...`. Phase 1 ships with no auto-promote path. |
| `apollo_eligible → operator_only` (demotion) | Accumulating loss-bias over rolling 60d window (criteria detector-specific). | Daily housekeeping job audits per-detector R-expectancy; flags candidates for demotion; user UPDATEs to enact. Never auto-demotes (avoids whiplash on noisy short windows). |
| `operator_only → informational` (demotion) | The complementary detector signal expires and the ticker reverts to single-detector context. | Same `_recompute_automation_class` helper runs daily as part of expiry housekeeping (§3); detects when the row's "second detector" entry has expired and downgrades. |

The class is a column, not a code branch — flip via SQL UPDATE or the recompute helper, no redeploy required.

## 3. Schema

```sql
CREATE TABLE mi_stocks_in_play (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    entry_date DATE NOT NULL,           -- ET date when ticker entered "ready" state
    source_detector TEXT NOT NULL,      -- enum value from stocks_in_play_sources constants (see §4)
    automation_class TEXT NOT NULL,     -- 'informational' | 'operator_only' | 'apollo_eligible'
    reason TEXT NOT NULL,               -- one-line human-readable: "Pradeep cohort 4x + COILED 3d"
    readiness_signal JSONB,             -- detector-specific structured detail (base_age, range_contraction_ratio, ep_score, etc.)
    source_phase TEXT,                  -- copy of strategy.phase at entry time ('paper'/'live'/'shadow') for shadow-source visual de-ranking
    expires_at TIMESTAMPTZ NOT NULL,    -- NOT NULL by design: every row MUST declare its TTL at insert (see "Expiry policy" below)
    promoted_at TIMESTAMPTZ,            -- when automation_class flipped operator_only → apollo_eligible (if ever)
    promoted_to_trade_at TIMESTAMPTZ,   -- when this ticker became a real trade (joins mi_live_trades)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ticker, entry_date, source_detector)
);
CREATE INDEX idx_stocks_in_play_active ON mi_stocks_in_play(entry_date DESC)
    WHERE expires_at > NOW();
CREATE INDEX idx_stocks_in_play_ticker ON mi_stocks_in_play(ticker, entry_date DESC);
CREATE INDEX idx_stocks_in_play_class ON mi_stocks_in_play(automation_class, entry_date DESC);
```

**State model**: state-table with audit-log for transitions (NOT event-table). One row per `(ticker, entry_date, source_detector)` triple. UPSERT semantics — re-firing within the same `entry_date` is a no-op on the existing row; new day = new row.

**Multi-detector storage decision (pinned)**: when a ticker qualifies via multiple detectors simultaneously (the convergence case), **each detector inserts its own row**. The UNIQUE constraint `(ticker, entry_date, source_detector)` encodes this: three detectors firing on one ticker = three rows with full provenance preserved. Aggregation to a single per-ticker display row happens at **read time** (in `/inplay` query + briefing render), not at storage time. This decision is load-bearing for every downstream read query — pinning it here prevents Phase 1 from re-litigating.

**Expiry policy** (NOT NULL by design — avoids the silent-forever landmine class from CLAUDE.md "DB tracks attempt not outcome" pattern):
- Every INSERT site MUST set `expires_at` explicitly. No defaults at the DB layer — forces detector-author intent.
- Recommended per-detector defaults (set by detector at insert time):
  - Sugar Baby cohort (alone): `entry_date + INTERVAL '1 day'` (rebuilt daily at 5:22 PM ET)
  - Flag stages (COILED/TIGHTENING/TRIGGERED): `entry_date + INTERVAL '5 trading sessions'` (matches typical breakout window)
  - Convergence (anticipatory or breakout): `entry_date + INTERVAL '5 trading sessions'`
  - Wick fill: `entry_date + INTERVAL '10 trading sessions'` (matches `wick_tracker` settlement horizon)
  - Parabolic / fishhook: detector-specific (parabolic climax decays fast; fishhook anchors hold longer)
  - MAGNA53 / 9M EP HIGH: `entry_date + INTERVAL '1 day'` (today's signal; tomorrow gets a fresh entry if still firing)
- **Housekeeping invariant**: a daily audit job (in `_post_eod_audit_job` 16:15 ET) flags any active rows where `expires_at > entry_date + INTERVAL '30 days'` as anomalies — catches detector bugs where a detector accidentally sets a TTL too far in the future. Emits `stocks_in_play_long_ttl_anomaly` audit.

## 4. Per-detector ready predicates

Each detector defines its own promotion threshold. This ADR doesn't lock the predicates — each detector owner defines via SSoT update — but documents current expected thresholds.

**Constants module** (Phase 1 creates this file to prevent magic-string drift across N insert sites — same lesson as `agents/market_intelligence/broker/skip_reasons.py`):

```python
# agents/market_intelligence/stocks_in_play_sources.py
SOURCE_SUGAR_BABY_COHORT        = "sugar_baby_cohort"
SOURCE_SUGAR_BABY_RIPE          = "sugar_baby_ripe"           # cohort × flag stage
SOURCE_CONVERGENCE_ANTICIPATORY = "convergence_anticipatory"  # cohort × COILED/TIGHTENING × EP
SOURCE_CONVERGENCE_BREAKOUT     = "convergence_breakout"      # cohort × TRIGGERED × EP
SOURCE_FLAG_COILED              = "flag_coiled"
SOURCE_FLAG_TRIGGERED           = "flag_triggered"
SOURCE_WICK_FILL                = "wick_fill"
SOURCE_PARABOLIC_SHORT          = "parabolic_short"
SOURCE_FISHHOOK_V3              = "fishhook_v3"
SOURCE_MAGNA53_EP_HIGH          = "magna53_ep_high"
SOURCE_NINEM_EP_HIGH            = "ninem_ep_high"

VALID_SOURCES = frozenset({
    SOURCE_SUGAR_BABY_COHORT, SOURCE_SUGAR_BABY_RIPE,
    SOURCE_CONVERGENCE_ANTICIPATORY, SOURCE_CONVERGENCE_BREAKOUT,
    SOURCE_FLAG_COILED, SOURCE_FLAG_TRIGGERED,
    SOURCE_WICK_FILL, SOURCE_PARABOLIC_SHORT, SOURCE_FISHHOOK_V3,
    SOURCE_MAGNA53_EP_HIGH, SOURCE_NINEM_EP_HIGH,
})

VALID_CLASSES = frozenset({"informational", "operator_only", "apollo_eligible"})
```

Every detector insert site imports from this module. Adding a new source detector requires updating `VALID_SOURCES` in the same commit — same friction-by-design pattern as Gate 5 G's `ALLOWED_WRITERS` (`docs/architecture/trade-state-ownership.md`).

| Detector | Ready predicate | source_detector value | Default automation_class |
|---|---|---|---|
| Persistent Sugar Babies cohort (alone) | In `mi_sugar_babies_cohort` for current day | `sugar_baby_cohort` | informational |
| Sugar Baby × flag-stage (Stage 1 today) | Cohort member AND flag stage ∈ {COILED, TIGHTENING, TRIGGERED} | `sugar_baby_ripe` | operator_only |
| Sugar Baby Convergence (anticipatory) | Cohort × COILED/TIGHTENING × HIGH EP fire | `convergence_anticipatory` | operator_only |
| Sugar Baby Convergence (breakout) | Cohort × TRIGGERED × HIGH EP fire | `convergence_breakout` | operator_only |
| Flag continuation COILED | `mi_flag_candidates` stage=COILED, base_age ≥ 10d | `flag_coiled` | operator_only |
| Flag continuation TRIGGERED | `mi_flag_candidates` stage=TRIGGERED | `flag_triggered` | operator_only |
| Wick fill | `mi_wick_candidates` open + green body | `wick_fill` | operator_only |
| Parabolic short anticipation/climax | `mi_parabolic_candidates` stage ∈ {anticipation, climax} | `parabolic_short` | operator_only |
| Fishhook V3 anchor | `mi_fishhook_anchors` state=promoted | `fishhook_v3` | operator_only |
| MAGNA53 EP HIGH | EP fire with score_tier=HIGH | `magna53_ep_high` | apollo_eligible (paper phase) |
| 9M EP HIGH | 9M intraday alert score_tier=HIGH | `ninem_ep_high` | apollo_eligible (paper phase) |

Each detector emits an INSERT or UPSERT into `mi_stocks_in_play` at its ready threshold. Existing detector tables stay (single source of truth for detector internals); `mi_stocks_in_play` is a thin aggregation layer.

## 5. Briefing UX consolidation

**Current state**: ~7 evening briefing sections across detectors. Operator scans each for "anything actionable."

**Target state**: ONE consolidated `🎯 Stocks in Play` section with provenance tags. Sub-sections rank by automation class:

```
🎯 Stocks in Play — 2026-05-23 (12 entries)

🚨 apollo_eligible (3) — Apollo auto-tracks these:
  • TICKR1  MAGNA53 HIGH  catalyst=game_changer  cohort 5x
  • TICKR2  9M Day 2 ORB
  • TICKR3  MAGNA53 HIGH

👤 operator_only (8) — needs your judgment:
  • QBTS    🍬🌀🎯 CONVERGENCE  cohort 5x · COILED 2d
  • POET    🌀  Sugar Baby + COILED 8d
  • TICKR4  🚩  Flag COILED 14d  runup +47%
  • TICKR5  🌀  Sugar Baby + COILED 5d
  • TICKR6  🚩  Flag COILED 11d
  • TICKR7  🔥  Wick fill candidate
  • TICKR8  🚩  Flag TRIGGERED today
  • TICKR9  📉  Parabolic climax stage

ℹ️ informational (1) — context only:
  • TICKR10  🍬  Sugar Baby cohort (no flag activity)

Drill-down: /inplay TICKER for full detector chronology
```

**Visual hierarchy**:
- `apollo_eligible` first (most-actionable; some auto-routed already)
- `operator_only` second (the watchlist proper)
- `informational` tail (collapsible / always-shown question — see open questions §10)

**Shadow-phase entries** (where `source_phase='shadow'`) render with reduced visual weight (e.g. italics or a `[shadow]` tag) so the operator doesn't FOMO-trade on un-validated signals. Per CLAUDE.md sample-size discipline.

**Existing per-detector sections** (`/sugarbabies`, `/flags`, etc.) remain for drill-down, but the evening briefing collapses to the unified section.

## 6. User-vs-Apollo trade division

Three concrete examples:

### Example 1 — Today's reality (2026-05-23)

| ticker | source_detector | automation_class | What happens |
|---|---|---|---|
| QBTS | sugar_baby_cohort | informational | Surfaced in briefing; no trade action |
| TICKR | magna53_ep_high (paper) | apollo_eligible | Auto-routed through entry_pipeline; ORB bracket submitted |
| TICKR | convergence_anticipatory | operator_only | Telegram alert tagged 🍬🌀🎯; user reviews chart, decides |

### Example 2 — Future state (when LLM "trade like user" matures)

Convergence backtest (filed as `sugar_baby_convergence_backtest_first_eval` data-gated review, earliest 2026-08-01) returns N≥10 settled fires showing measurably better R-expectancy than baseline HIGH alerts. Decision: promote `convergence_anticipatory` from `operator_only → apollo_eligible`.

Mechanism: SQL `UPDATE mi_stocks_in_play SET automation_class='apollo_eligible' WHERE source_detector='convergence_anticipatory' AND ...` — no code change. Entry pipeline now picks up convergence rows for auto-routing.

### Example 3 — Demotion (if a class fails)

A shadow-phase detector promoted to `operator_only` shows accumulating loss-bias over 60d. Demote back to `informational` via SQL UPDATE. Briefing renders it with reduced visual weight; no Telegram alert.

This bidirectional flow without redeploys is the architectural value of axis 3.

## 7. Migration plan (when triggered)

**Trigger condition** — Phase 1 implementation gated on **first 5 real-world convergence fires logged in `mi_audit_log` AND ≥3 weeks observation since #84 deploy (2026-05-22)**. The composite "earns keep" framing was fuzzy; tightening to a concrete-count + calendar gate so the decision point is unambiguous.

After the gate fires, Phase 1 starts on ANY of:
- The `sugar_baby_convergence_backtest_first_eval` data-gated review predicate firing (N≥10 settled — likely 6-10 weeks of observation)
- User explicit signal: *"let's build mi_stocks_in_play"*
- A second cross-detector convergence pattern emerges in another detector (proves the abstraction generalizes beyond Sugar Baby — would justify shipping before the full N≥10 settled)

**Phase 1 — Schema + first detector migration** (~half-day):
- Create `mi_stocks_in_play` table (idempotent migration in `db.py::initialize_schema`)
- Migrate Persistent Sugar Babies cohort + Sugar Baby ripeness decoration (today's #83 work) into INSERT-to-stocks-in-play
- Add `/inplay` command + replace `/sugarbabies` evening briefing block with consolidated section
- Existing `/sugarbabies` stays as drill-down

**Phase 2 — Convergence migration** (~half-day):
- Sugar Baby Convergence audit events become INSERTs into `mi_stocks_in_play` with `source_detector='convergence_anticipatory'` or `'convergence_breakout'`
- `automation_class='operator_only'` set on insert
- Existing Telegram tag prepending stays — convergence is BOTH a stocks_in_play entry AND an alert escalator

**Phase 3 — Flag + 9M Day 2 migration** (~half-day):
- Flag COILED/TIGHTENING/TRIGGERED → INSERT
- 9M Day 2 sugar baby (single-day; pre-#82 rename) → INSERT with `apollo_eligible` class
- `/flags` drill-down remains

**Phase 4 — Shadow detectors** (~half-day):
- Wick, Parabolic, Fishhook → INSERT with `informational` class (or `operator_only` if confidence warrants)
- Their respective `/wick`, `/parabolic`, `/fishhook` commands stay for drill-down
- Briefing sections retire (consolidated section replaces)

**Phase 5 — MAGNA53 + 9M EP HIGH migration** (~quarter-day):
- Live alert path also writes to `mi_stocks_in_play` with `apollo_eligible` class
- Telegram alert stays (it's the operator escalation channel)
- Existing `mi_ep_alerts` and `mi_9m_ep_alerts` tables stay (detector internals)
- **Triple-write fail-open invariant**: a single logical EP fire now triggers three writes (`mi_ep_alerts` row, Telegram send, `mi_stocks_in_play` row). The `mi_stocks_in_play` write MUST be fail-open — a failed INSERT here CANNOT block `entry_pipeline.submit_trade_entry`. Same shape as the convergence-check telemetry decoupling from EP alert send (#84 Gemini contract #4). Wrap in try/except + audit log; never raise.

**Critical invariant** (Gemini contract #3 from #84 review): each phase is a separate atomic commit with deploy + preflight between. No bundle-shipping the unified watchlist.

## 8. Trading-session vs calendar-day hardening (Gemini contract #1)

Today's Sugar Baby Convergence (#84) uses `INTERVAL '5 days'` calendar-day lookup for "recently in flag stage." Memorial Day weekend (next week) compresses this to ~2 active scan sessions.

**ADR-time hardening**: replace calendar-day lookbacks with trading-session subqueries throughout the unified watchlist:

```sql
-- BEFORE (calendar-day, prototype scope):
scan_date >= CURRENT_DATE - INTERVAL '5 days'

-- AFTER (trading-session, ADR-time):
scan_date IN (
    SELECT DISTINCT scan_date
    FROM mi_flag_candidates
    ORDER BY scan_date DESC
    LIMIT 5
)
```

This generalizes — every "last N scans/days" check in the unified surface uses trading-session counts, not calendar days. Handles long weekends, holidays, and timezone edge cases uniformly.

## 9. Reuse from existing code

- `mi_strategies.phase` model — Axis 1 already exists; ADR mirrors the pattern at the stock level (Axis 2) and entry-class level (Axis 3)
- `mi_audit_log` — transitions logged here (state changes carry audit rows; the state-table itself is `mi_stocks_in_play`)
- `audit_wrap` from `core.job_audit` — per-phase migration jobs use this
- `should_log_mna_filter_fired` pattern (#89) — same dedup shape applies if `mi_stocks_in_play` inserts need same-day dedup
- `make_client_order_id` from `alpaca_client` (#66) — apollo_eligible class entries feed into the existing dual-account COID generation

## 10. Open questions

- **Multi-detector dedup**: when a ticker qualifies via 3 detectors simultaneously (Sugar Baby + COILED + EP fire), do we display 1 consolidated row or 3 rows? Lean: 3 rows in DB (one per detector for provenance), 1 consolidated row in briefing/`/inplay` via per-ticker aggregation. Settle in Phase 1.
- **`informational` tier briefing UX**: always-shown (full transparency, info overload risk), collapsible (cleaner but hides context), or always-hidden (cleanest, loses context). Lean: collapsible tail with count visible.
- **`apollo_eligible` automatic graduation**: should a `operator_only` class auto-promote after N≥10 settled positive outcomes, or always require explicit user UPDATE? Lean: always explicit (user-in-the-loop on automation expansion).
- **Decay metrics**: should `mi_stocks_in_play` track daily diff (new entries vs drops vs unchanged) for operator situational awareness? Lean: yes, in `/inplay` drill-down but not in evening briefing main section.
- **Retention**: `expires_at` per detector vs global TTL? Lean: per-detector (each detector knows when its signal stops being valid).
- **`source_phase='shadow'` visual de-ranking**: italic tag vs `[shadow]` prefix vs separate sub-section. Lean: separate sub-section under `informational`.

## 11. Discipline notes

- **Sample-size discipline applies to confidence scoring**: any integrated cross-detector "ripeness score" (e.g. cohort + COILED + EP fire = score 9/10) needs N≥30 evidence per `feedback_validate_metric_before_decision.md` before citing authoritatively. Initial ship uses sort-order only, no numeric score.
- **Filter behavior decoupled from telemetry** (#89 lesson): `mi_stocks_in_play` writes are telemetry; underlying detector trade decisions stay in their own code paths. Failures to write to `mi_stocks_in_play` must NEVER break detector behavior. Fail-open everywhere.
- **Ground-truth verification** (`feedback_ground_truth_verification.md`): when computing per-stock outcomes (forward returns), verify against `mi_daily_closes` not against derived flags. Don't repeat the 2026-05-22 `is_anticipation` pivot lesson.
- **Audit-trail discipline**: every transition (state change, automation_class flip, demote) writes a `stocks_in_play_*` audit event. Backtest scripts query via the audit trail, not the live state table.

## 12. Sequencing decision (re-affirmed)

| Phase | Status | Trigger | Estimated effort |
|---|---|---|---|
| Prototype (Sugar Baby Convergence) | **SHIPPED 2026-05-22** (#83/#84) | User direction | Done |
| ADR (this document) | **SHIPPED 2026-05-23** (#87) | User direction "proceed" | Done |
| Phase 1 implementation | Deferred | Convergence backtest OR explicit user trigger OR 2nd cross-detector pattern emerges | ~half-day |
| Phase 2-5 | Deferred | Phase N-1 stable for 1+ weeks | ~half-day each |

This ADR is the architectural commitment, not the implementation. Future sessions execute against this document rather than re-deriving the framing.

## 13. Cross-references

- `~/.claude/projects/.../memory/project_stocks_in_play_architecture.md` — original framing (2026-05-22); this ADR supersedes
- `data_gated_reviews.yaml::sugar_baby_convergence_backtest_first_eval` — gates Phase 1 trigger via N≥10 convergence outcomes
- `data_gated_reviews.yaml::ninem_day2_mechanical_vs_methodology_alignment` (#65) — partly resolves under this architecture; the methodology gap between mechanical 9M Day 2 and Pradeep "ready then catalyst" intent becomes a per-stock-maturity question
- `user_pradeep_9m_universe_methodology.md` — Pradeep's "9M = universe, entry = tightness→expansion" methodology IS this maturity model applied to individual stocks; the unified watchlist makes that explicit
- `feedback_sample_size_discipline.md` — guards against shipping confidence scores without evidence
- `feedback_per_commit_advisor_deploy.md` — multi-detector migration touches many sites; each phase MUST be a separate commit with deploy + preflight between (Gemini contract #3 generalized)
- `feedback_ground_truth_verification.md` — outcome computation must use ground truth, not intermediate flags
- `docs/setups/magna53_ep.md` — MAGNA53 EP detector SSoT; will receive a change-log entry when Phase 5 migrates the EP path
- `BACKLOG.md` — backlog index; will reference this ADR once Phase 1 is triggered
