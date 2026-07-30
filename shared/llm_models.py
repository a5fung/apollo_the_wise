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

── AUTO-RESOLUTION (operator-ruled 2026-07-30) ───────────────────────────────
Tiers TRACK the newest concrete release automatically ("go with the leaders,
but have guardrails … and we can always trace back to when they were updated").
The tier constants below are RESOLVED at import via shared/model_resolver.py:

    override (this file) > resolution cache (logs/model_resolution.json,
    written nightly by the market-agent's model_resolution_refresh job)
    > committed pin (this file)

No network at import and none per LLM call — resolution is a local cache-file
read; missing/corrupt cache, an unparseable id, or ANY resolver failure falls
back to the committed pin. A resolved model takes effect at PROCESS BOOT (the
running process keeps its boot-time binding) and is never silent: the release
is Telegram'd when detected, and the boot recorder Telegrams + audit-logs +
persists every effective change to `mi_model_resolution` (queryable "what was
the judge running on date X").

🔙 ROLLBACK — the 9:31am path when grades look wrong after a model change:
    ONE EDIT: set the tier's entry in `_TIER_OVERRIDES` below to the last-good
    concrete id (e.g. "opus": "claude-opus-4-8") → deploy. The override beats
    the resolver unconditionally. Clear it back to None to resume tracking.
Housekeeping after a green judge eval on a newly-resolved id: bump that tier's
*_PIN to the evaluated id in the same commit (keeps the fail-safe floor current;
preflight_model_resolution.py nags when the pin trails the resolved id).
"""

from shared.model_resolver import TierResolution as _TierResolution
from shared.model_resolver import resolve_tier as _resolve_tier

# ── Tier pins (committed fail-safe floor — never auto-edited) ────────────────
SONNET_PIN = "claude-sonnet-4-6"
HAIKU_PIN = "claude-haiku-4-5-20251001"
OPUS_PIN = "claude-opus-4-8"

# ── Explicit tier overrides — THE one-edit rollback lever (see docstring) ────
# A non-None value bypasses the resolver for that tier. Changing an entry is a
# model-selection decision: its own commit, with rationale (and the judge-eval
# gate hard-fails a judge-affecting override that was never evaluated).
_TIER_OVERRIDES: dict[str, str | None] = {
    "opus": None,
    "sonnet": None,
    "haiku": None,
}

# ── Tiers (resolved at import — concrete model ids) ──────────────────────────
_res_opus = _resolve_tier("opus", OPUS_PIN, _TIER_OVERRIDES["opus"])
_res_sonnet = _resolve_tier("sonnet", SONNET_PIN, _TIER_OVERRIDES["sonnet"])
_res_haiku = _resolve_tier("haiku", HAIKU_PIN, _TIER_OVERRIDES["haiku"])

OPUS = _res_opus.model
SONNET = _res_sonnet.model
HAIKU = _res_haiku.model

# Forensics for the boot recorder + deploy gates: how each tier was resolved.
TIER_RESOLUTIONS: dict[str, _TierResolution] = {
    "opus": _res_opus,
    "sonnet": _res_sonnet,
    "haiku": _res_haiku,
}

_TIER_BY_ID: dict[str, str] = {OPUS: "opus", SONNET: "sonnet", HAIKU: "haiku"}


def tier_of(model_id: str) -> "str | None":
    """Which resolved tier a bound model id belongs to; None for static legacy
    pins (e.g. METRICS_EXTRACTION_MODEL's deliberate SONNET_4_5 pin)."""
    return _TIER_BY_ID.get(model_id)

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
# Theme → ecosystem bucket pick (ADR 0032 Phase 1, theme_ecosystems.py).
# Cheap structured single-code classification against a FIXED 20-bucket
# taxonomy with a scratchpad-first forced tool — Haiku tier; a deterministic
# keyword/exemplar fallback backstops abstains/errors, so a misfire degrades
# to E-UNASSIGNED (read-model only, no money path).
ECOSYSTEM_ASSIGN_MODEL = HAIKU
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
# Ensemble-divergence SHADOW 2nd opinion (#301, ADR 0011 sibling — zero-authority
# MONITOR, never a grade input). Deliberately SONNET, not OPUS: the point is an
# INDEPENDENT second read on the JUDGE_MODEL verdict, so it must differ in
# model/tier from JUDGE_MODEL, not just be a cheaper rerun of the same model.
# Also cheap — ~2-5 calls/day expected (HIGH-tier verdicts only).
JUDGE_DIVERGENCE_MODEL = SONNET
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
# Verified against the live model catalog 2026-06-09; tier rows re-verified
# against the 2026-07 catalog (opus-5 $5/$25, sonnet-5 sticker $3/$15 — the
# sonnet-5 intro discount through 2026-08-31 is deliberately NOT modeled, so
# spend is over- not under-stated during the intro window).
#
# AUTO-RESOLUTION NOTE: the tier keys (SONNET/HAIKU/OPUS) are the RESOLVED ids,
# so a resolver-tracked release re-prices automatically at its tier's rate. The
# *_PIN keys stay priced explicitly so HISTORICAL spend rows written under the
# pinned id keep pricing after the tier resolves forward (when resolution ==
# pin the duplicate dict key is harmless — same value). LIMIT, stated plainly:
# a new release that changes its TIER's price would be mispriced here until
# this table is hand-updated — models.list carries no pricing, so the resolver
# cannot verify rates. Unknown ids fall back to DEFAULT_PRICING_PER_MTOK.
PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    SONNET:     {"input": 3.00, "output": 15.00},
    SONNET_PIN: {"input": 3.00, "output": 15.00},
    SONNET_4_5: {"input": 3.00, "output": 15.00},
    HAIKU:      {"input": 1.00, "output": 5.00},
    HAIKU_PIN:  {"input": 1.00, "output": 5.00},
    OPUS:       {"input": 5.00, "output": 25.00},
    OPUS_PIN:   {"input": 5.00, "output": 25.00},
    OPUS_4_7:   {"input": 5.00, "output": 25.00},
    OPUS_4_6:   {"input": 5.00, "output": 25.00},
    # ── Perplexity (#377 cost meter) ─────────────────────────────────────────
    # Token rates verified against https://docs.perplexity.ai/guides/pricing
    # (fetched 2026-06-25). Perplexity bills BOTH per-token AND a per-request
    # search fee that varies by search-context size; the flat per-request fee
    # below is the MEDIUM-context tier (the default our callers hit). The fee is
    # added by log_perplexity_call as a flat cost_usd component, separate from
    # the token cost. If Perplexity changes its published rates, update HERE only.
    "sonar-pro": {"input": 3.00, "output": 15.00},
    "sonar":     {"input": 1.00, "output": 1.00},
}
DEFAULT_PRICING_PER_MTOK: dict[str, float] = {"input": 3.00, "output": 15.00}

# Perplexity per-request search fee in USD. Published 2026-06-25: sonar-pro
# medium = $10/1k req ($0.010/req); sonar medium = $8/1k req ($0.008/req).
# ASSUMED-MEDIUM: our callers do NOT set `search_context_size`, so the ACTUAL
# billed tier is Perplexity's API default — not confirmed to be medium. Token
# rates ARE confirmed; this per-request fee is the SOFT number. VERIFY the real
# tier + rate at the quarterly pricing sweep (Perplexity tiers this by context
# size and has changed it before). OPERATOR: confirm/adjust if exact $ matters.
PERPLEXITY_REQUEST_FEE_USD: dict[str, float] = {
    "sonar-pro": 0.010,
    "sonar":     0.008,
}
DEFAULT_PERPLEXITY_REQUEST_FEE_USD: float = 0.010
