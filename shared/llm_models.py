"""Central LLM model registry — the ONLY place production model ids live (#257).

Why: model ids were scattered as string literals across 17 call sites, and they
DRIFTED — the theme advisor was still on claude-opus-4-6 while the judge eval
compared against claude-opus-4-8, and the metrics extractor sat on a stale
claude-sonnet-4-5 pin nobody had revisited. A model upgrade done file-by-file
will always miss spots; this registry + its deploy gate make that impossible
(same enforcement idiom as the pytz ban).

Rules:
  - Call sites in agents/ core/ channels/ shared/ import a ROLE constant from
    here. A `claude-*` string literal anywhere else fails
    `scripts/preflight_model_registry.py` (deploy gate) and
    `tests/test_model_registry.py`.
  - Deliberate literal exception: `# model-ok: <reason>` on the line.
  - Changing a ROLE binding is a model-selection decision: its own commit, with
    rationale, per docs/model_selection_baseline.md (quality primary, cost
    tiebreaker — memory feedback_model_selection_quality_over_cost). Never bump
    a binding inside an unrelated refactor.

Pricing tables (core/spend.py, agents/.../spend_tracker.py) key off these
constants so a tier bump re-prices spend logging automatically; ids kept ONLY
for pricing historical rows live in the LEGACY section.
"""

# ── Tiers (raw model ids) ────────────────────────────────────────────────────
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
OPUS = "claude-opus-4-8"

# Legacy ids — kept for pricing historical spend rows / deliberate pins only.
SONNET_4_5 = "claude-sonnet-4-5"
OPUS_4_7 = "claude-opus-4-7"
OPUS_4_6 = "claude-opus-4-6"

# ── Role bindings (what each subsystem actually calls) ───────────────────────
# Orchestrator tool-use loop (core/orchestrator.py)
ORCHESTRATOR_MODEL = SONNET
# Market agent's own small LLM calls (agents/.../agent.py)
MARKET_AGENT_MODEL = HAIKU

# Theme engine: discovery/assignment/validation (Sonnet since #213 — Haiku
# misread narrowing name qualifiers as membership filters)
THEME_MODEL = SONNET
# Theme engine's senior-advisor escalation (capped 3 calls/run)
THEME_ADVISOR_MODEL = OPUS_4_6  # behavior-preserving migration 2026-06-09; flip to OPUS pending its own reviewed commit
# Ticker-description generation (theme engine chunked + nightly backfill)
DESCRIPTION_MODEL = HAIKU

# EP holistic grade judge (ADR 0011; W1 eval owns this choice)
JUDGE_MODEL = SONNET
# Grounded-summary catalyst grade (#190 — Haiku confabulated on raw headlines)
GROUNDED_GRADE_MODEL = SONNET
# Deterministic-adjacent materiality assessment (catalyst_materiality.py)
MATERIALITY_MODEL = SONNET
# Multi-quarter catalyst metrics extraction (catalyst_metrics_extractor.py)
METRICS_EXTRACTION_MODEL = SONNET_4_5  # stale-looking pin, flagged 2026-06-09 — revisit deliberately
# Catalyst TYPE classification (fire identity; cheap, structured)
CATALYST_TYPE_MODEL = HAIKU

# Trade postmortem narration (postmortem.py)
POSTMORTEM_MODEL = SONNET
# Sunday weekly system review narration (system_review.py)
SYSTEM_REVIEW_MODEL = SONNET

# Orchestrator conversation compression (core/context.py)
COMPRESSION_MODEL = HAIKU
# /agents health-check ping (channels/telegram.py — 5 tokens)
HEALTHCHECK_MODEL = HAIKU
