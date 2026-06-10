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
# Theme engine's senior-advisor escalation (capped 3 calls/run).
# 2026-06-09: opus-4-6 → opus-4-8. Same price tier ($5/$25), strictly more
# capable, and aligns the advisor with the model the judge eval compares
# against (the drift that motivated this registry).
THEME_ADVISOR_MODEL = OPUS
# Ticker-description generation (theme engine chunked + nightly backfill)
DESCRIPTION_MODEL = HAIKU
# Cross-ticker emerging-theme synthesis (theme_synthesis.py — #240 advisory
# feed; Sonnet: the same cross-sector narrative reasoning tier as THEME_MODEL)
SYNTHESIS_MODEL = SONNET

# EP holistic grade judge (ADR 0011; W1 eval owns this choice).
# OPUS since 2026-06-10: operator-labeled closed-gap eval (lit Lane-2 theme
# axis, grounded corpus, 36 alerts / 17 disagreements) scored Opus 9 - Sonnet
# 2 - Neither 4 - tie 1. Decision doc:
# docs/analysis/judge_model_eval_closed_gap_2026-06-10.md; baseline:
# docs/model_selection_baseline.md. Cost gap small ($5/$25 vs $3/$15);
# quality-over-cost on the load-bearing path. Live latency budgets raised
# with the flip (judge timeout 15->25s; ep_detector post-loop 60->110s) —
# Opus is slower and a tight timeout converts quality into fail-open noise.
JUDGE_MODEL = OPUS
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

# ── Pricing ($ per 1M tokens) — ONE copy ─────────────────────────────────────
# Both spend tables (core/spend.py orchestrator-side, agents/.../spend_tracker.py
# market-agent-side) import this. The 2026-06-09 stale-rate bug (Haiku 0.80/4.00,
# Opus 15/75) existed precisely because the rates lived in two hand-typed copies.
# Verified against the live model catalog 2026-06-09.
PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    SONNET:     {"input": 3.00, "output": 15.00},
    SONNET_4_5: {"input": 3.00, "output": 15.00},
    HAIKU:      {"input": 1.00, "output": 5.00},
    OPUS:       {"input": 5.00, "output": 25.00},
    OPUS_4_7:   {"input": 5.00, "output": 25.00},
    OPUS_4_6:   {"input": 5.00, "output": 25.00},
}
DEFAULT_PRICING_PER_MTOK: dict[str, float] = {"input": 3.00, "output": 15.00}
