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
for pricing historical rows live in the LEGACY section. Use `pricing_for(id)`
rather than a raw dict `.get` anywhere the id MIGHT be an auto-resolved release
not yet in the table (see AUTO-RESOLUTION below) — a raw `.get` silently
mis-prices an unrecognised id at DEFAULT_PRICING_PER_MTOK.

── AUTO-RESOLUTION (operator-ruled 2026-07-30) ───────────────────────────────
Policy (verbatim intent): "go with the leaders, but have guardrails to make
sure there's no major degradation … and we can always trace back to when they
were updated." The mechanism below is shaped by ONE hard constraint discovered
while building it, so read this before touching any of it:

`scripts/preflight_judge_eval_gate.py` runs on the HOST at deploy time — no API
key, no DB, no import of this module — it re-parses THIS FILE'S SOURCE TEXT
with `ast` to pull `JUDGE_MODEL`'s value (one-hop alias resolution) and
compares it to the last passing judge-robustness eval record
(scripts/evals/judge_eval_pass_record.json). A value produced by calling code
(e.g. `_resolve_tier(...)`) is INVISIBLE to that parser — the assignment node
is a Call, not a Constant/Name — so it can only ever validate what is
COMMITTED. Consequently:

    THE MODULE-LEVEL TIER CONSTANTS (OPUS/SONNET/HAIKU) AND EVERY ROLE
    BINDING DERIVED FROM THEM (JUDGE_MODEL, THEME_ADVISOR_MODEL, …) STAY
    PLAIN AST-PARSEABLE LITERALS — exactly as before this feature, never
    reassigned via the resolver. Do not "fix" this by making them dynamic;
    it defeats the one guardrail the deploy gate provides and is invisible
    drift by construction.

The deploy gate is UNCHANGED — it keeps validating the COMMITTED pin. That is
deliberate, not a gap: it is the guardrail for the SOURCE. Auto-resolution
gets a SEPARATE guardrail for the RUNTIME, via a parallel system that never
touches the literals above:

  1. shared/model_resolver.py — pure-stdlib id parser/orderer + a cache-file
     ("logs/model_resolution.json") reader/writer. No network, ever, here.
  2. agents/.../model_resolution.py::refresh_model_resolution — NIGHTLY,
     IN-CONTAINER (only there is ANTHROPIC_API_KEY reachable): calls
     `models.list`, computes the newest id per tier, writes the cache. A new
     release is NEVER silent — Telegram + audit event, before it can take
     effect anywhere.
  3. RESOLVED_ROLES below — the opt-in list of ROLE bindings whose ACTUAL live
     calls track the resolver (today: JUDGE_MODEL only — the one role the
     ADR-0030 robustness eval polices; every other role stays hand-pinned,
     unaffected). `effective_model(role)` returns a role's live value:
     override > cache (never below the pin) > pin — CANNOT raise (see
     shared/model_resolver.resolve_tier). Resolved ONCE, from the cache FILE
     only (zero network, zero re-read per LLM invocation) — at whichever
     point this module or a role's call site first reads it, which in
     practice means process/container boot ("the running process keeps its
     boot-time binding"). `ep_grade_judge.py` binds its `model=` default to
     `effective_model("JUDGE_MODEL")` at import — that is the ONE real call
     site this actually drives.
  4. agents/.../model_resolution.py::record_boot_resolution — boot hook,
     persists + Telegrams every EFFECTIVE role/model pairing (via
     `effective_model`, so it reflects #3 truthfully, not the static
     constant) to `mi_model_resolution`, insert-on-change — the durable "what
     was role X running on date Y" record.
  5. agents/.../model_resolution.py::check_judge_eval_divergence — NEW
     nightly WARN (never a block): compares what THIS process is actually
     running the judge on (`effective_model("JUDGE_MODEL")`) against the
     model recorded in the last PASSING eval. This is exactly the comparison
     the host-side deploy gate structurally cannot make (it only ever sees
     the committed pin). Warn, not block — adopting a new judge id needs a
     paid eval + operator sign-off; a hard deploy block would hold every
     unrelated change hostage over a model release.

🔙 ROLLBACK — the 9:31am path when grades look wrong after a model change:
    ONE EDIT: set the tier's entry in `_TIER_OVERRIDES` below to the last-good
    concrete id (e.g. "opus": "claude-opus-4-8") and redeploy —
    `effective_model` honors an override ahead of the cache unconditionally.
    Clear it back to None to resume auto-tracking.
    (To change the COMMITTED pin itself — the value the deploy gate checks —
    edit `OPUS_PIN`/`SONNET_PIN`/`HAIKU_PIN` directly; that is its own
    model-selection commit per the Rules above, evaluated by ADR-0030 first
    for JUDGE_MODEL specifically.)
"""

from shared.model_resolver import TierResolution as _TierResolution
from shared.model_resolver import parse_model_id as _parse_model_id
from shared.model_resolver import resolve_tier as _resolve_tier

# ── Tier pins (committed fail-safe floor — what the deploy gate validates;
# never auto-edited) ──────────────────────────────────────────────────────────
SONNET_PIN = "claude-sonnet-4-6"
HAIKU_PIN = "claude-haiku-4-5-20251001"
OPUS_PIN = "claude-opus-4-8"

# ── Tiers (raw model ids) — PLAIN LITERAL ALIASES, never auto-edited or
# resolver-bound. See AUTO-RESOLUTION above for why these specifically must
# stay statically parseable. ──────────────────────────────────────────────────
SONNET = SONNET_PIN
HAIKU = HAIKU_PIN
OPUS = OPUS_PIN

# Legacy ids — kept for pricing historical spend rows / deliberate pins only.
SONNET_4_5 = "claude-sonnet-4-5"
OPUS_4_7 = "claude-opus-4-7"
OPUS_4_6 = "claude-opus-4-6"

_TIER_PINS: dict[str, str] = {"opus": OPUS_PIN, "sonnet": SONNET_PIN, "haiku": HAIKU_PIN}


def tier_of(model_id: str) -> "str | None":
    """Which tier FAMILY a model id parses into (opus/sonnet/haiku), via the
    resolver's own id grammar (shared/model_resolver.parse_model_id) — this
    recognises ANY concrete release in a tracked family (including legacy pins
    like SONNET_4_5/OPUS_4_7/OPUS_4_6 — they parse fine, they're just not
    RESOLVED_ROLES-tracked), not just the three currently-pinned literals, so a
    genuinely auto-resolved id (e.g. a newer opus release picked up by
    effective_model) is correctly attributed. None only for a shape the
    resolver structurally cannot order at all — a family word it doesn't know
    (claude-fable-5), no numeric version, or an unrecognised prefix. NOTE:
    "parses into a family" is NOT the same question as "is this role
    RESOLVED_ROLES-tracked" — use `role_resolution(role)` for the latter."""
    parsed = _parse_model_id(model_id)
    return parsed.family if parsed else None


# ── Explicit tier overrides — THE one-edit rollback lever (see docstring) ────
# A non-None value bypasses the resolver for that tier's RESOLVED_ROLES roles.
# Changing an entry is a model-selection decision: its own commit, with
# rationale. (This overrides the RUNTIME binding only — it never touches the
# committed *_PIN the deploy gate validates.)
_TIER_OVERRIDES: dict[str, str | None] = {
    "opus": None,
    "sonnet": None,
    "haiku": None,
}

# ── Auto-tracked role bindings: role constant name -> tier. Adding a role
# here is a deliberate decision that its ACTUAL live calls (not just this
# file's constant) will move when the nightly refresh adopts a new release.
# Today: only the primary EP judge opts in — ep_grade_judge.py binds its
# `model=` default to effective_model("JUDGE_MODEL") at import. Every role
# NOT listed here is completely unaffected: effective_model on it just
# returns the plain module constant, unchanged behavior. ─────────────────────
# ── Operator-facing role labels ──────────────────────────────────────────────
# The change notification is read by the OPERATOR, not by us: SCREAMING_SNAKE
# constants are our notation leaking into his Telegram. Labels say what the role
# DOES. Deliberately fallback-safe rather than exhaustive — a role added later
# without a label degrades to a readable form of its own name, so this map can
# never rot into a KeyError or a blank line.
ROLE_LABELS: dict[str, str] = {
    "JUDGE_MODEL": "grading judge",
    "JUDGE_DIVERGENCE_MODEL": "second-opinion check",
    "THEME_ADVISOR_MODEL": "theme advisor",
    "THEME_MODEL": "theme discovery",
    "ORCHESTRATOR_MODEL": "orchestrator",
    "MARKET_AGENT_MODEL": "market agent",
    "SYNTHESIS_MODEL": "synthesis",
    "GROUNDED_GRADE_MODEL": "catalyst grading",
    "MATERIALITY_MODEL": "materiality",
    "METRICS_EXTRACTION_MODEL": "metrics extraction",
    "CATALYST_TYPE_MODEL": "catalyst type",
    "DESCRIPTION_MODEL": "descriptions",
    "ECOSYSTEM_ASSIGN_MODEL": "ecosystem assignment",
    "POSTMORTEM_MODEL": "trade postmortems",
    "SYSTEM_REVIEW_MODEL": "weekly review",
    "COMPRESSION_MODEL": "conversation compression",
    "HEALTHCHECK_MODEL": "health check ping",
}


def label_for(role: str) -> str:
    """Plain-words name for a role, for operator-facing text."""
    if role in ROLE_LABELS:
        return ROLE_LABELS[role]
    return role.removesuffix("_MODEL").replace("_", " ").lower() or role


def pretty_model(model_id: str) -> str:
    """`claude-opus-4-8` -> `Opus 4.8`; `claude-haiku-4-5-20251001` -> `Haiku 4.5`.
    Unparseable ids come back unchanged — never invent a name."""
    parsed = _parse_model_id(model_id)
    if not parsed:
        return model_id
    ver = ".".join(str(n) for n in parsed.version)
    return f"{parsed.family.capitalize()} {ver}"


RESOLVED_ROLES: dict[str, str] = {
    # ── ALL roles opted in (operator 2026-07-31: "opt all in") ──────────────
    # The first build covered ONLY the judge, which was backwards: the judge is
    # the one role with money consequences, while the Sonnet/Haiku roles are
    # analytical and are exactly where staleness actually bit — the theme
    # advisor sat stranded on opus-4-6 while the judge eval compared 4-8, and
    # METRICS_EXTRACTION_MODEL is STILL on a pin flagged 2026-06-09.
    "JUDGE_MODEL": "opus",
    "THEME_ADVISOR_MODEL": "opus",
    "ORCHESTRATOR_MODEL": "sonnet",
    "THEME_MODEL": "sonnet",
    "SYNTHESIS_MODEL": "sonnet",
    "GROUNDED_GRADE_MODEL": "sonnet",
    "MATERIALITY_MODEL": "sonnet",
    "METRICS_EXTRACTION_MODEL": "sonnet",
    "POSTMORTEM_MODEL": "sonnet",
    "SYSTEM_REVIEW_MODEL": "sonnet",
    "MARKET_AGENT_MODEL": "haiku",
    "DESCRIPTION_MODEL": "haiku",
    "ECOSYSTEM_ASSIGN_MODEL": "haiku",
    "CATALYST_TYPE_MODEL": "haiku",
    "COMPRESSION_MODEL": "haiku",
    "HEALTHCHECK_MODEL": "haiku",
    # JUDGE_DIVERGENCE_MODEL tracks the SONNET tier — deliberately a DIFFERENT
    # tier from JUDGE_MODEL (opus), never a different VINTAGE.
    #
    # I first excluded this to protect the #301 independence ("not just a cheaper
    # rerun of the same model" — its own registry comment). The operator caught
    # that excluding it meant NOTHING would ever update it: "all models need a
    # path to upgrade, nothing shall remain stale." He is right, and my exclusion
    # recreated the exact staleness this whole change exists to kill — the second
    # opinion would have sat on sonnet-4-6 while the judge advanced every
    # release, so the gap would widen until the "independent read" was simply a
    # much WEAKER model rather than a different one.
    #
    # INDEPENDENCE COMES FROM THE TIER, NOT FROM THE VINTAGE. Keep this bound to
    # a tier that differs from JUDGE_MODEL's; do NOT point both at the same tier.
    "JUDGE_DIVERGENCE_MODEL": "sonnet",
}

# Resolved ONCE at import (cache-FILE read only — never a network call, never
# re-read per invocation): the forensics view AND the value effective_model
# returns for a RESOLVED_ROLES role. CANNOT raise (resolve_tier's contract).
_ROLE_RESOLUTIONS: dict[str, _TierResolution] = {
    role: _resolve_tier(tier, _TIER_PINS[tier], _TIER_OVERRIDES.get(tier))
    for role, tier in RESOLVED_ROLES.items()
}


def effective_model(role: str) -> str:
    """The model `role` is ACTUALLY bound to in this process. For a
    RESOLVED_ROLES role this is the cache-resolved id (see AUTO-RESOLUTION
    above); for any other role name this is simply that name's plain module
    constant — `effective_model("THEME_MODEL") == THEME_MODEL`, always,
    since THEME_MODEL never appears in RESOLVED_ROLES."""
    res = _ROLE_RESOLUTIONS.get(role)
    if res is not None:
        return res.model
    return globals().get(role, "")


def role_resolution(role: str) -> "_TierResolution | None":
    """Full resolution forensics (source/changed_at/note) for a RESOLVED_ROLES
    role; None for a role that isn't auto-tracked (i.e. a "static" role)."""
    return _ROLE_RESOLUTIONS.get(role)

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
METRICS_EXTRACTION_MODEL = SONNET  # was SONNET_4_5, a pin flagged stale 2026-06-09 and never
# revisited — the exact rot the resolver exists to kill. Runtime already resolved this role to
# the newest sonnet (it is in RESOLVED_ROLES); this re-points the OFFLINE FALLBACK too, so a
# resolver outage degrades to current-sonnet instead of two generations back. Same tier, same
# $3/$15 rate — no cost change. (operator 2026-07-31: "nothing shall remain stale")
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
# AUTO-RESOLUTION NOTE: SONNET/HAIKU/OPUS are the same literal as their *_PIN
# (see AUTO-RESOLUTION above — the duplicate key is harmless, same value) so
# a direct `.get` on THOSE names always hits. The gap is a RESOLVED_ROLES
# role's live id (e.g. effective_model("JUDGE_MODEL") returning a genuinely
# newer opus release not yet in this table) — a raw `.get(model, DEFAULT)`
# would silently price a $5/$25 Opus call at the $3/$15 default. Call sites
# that log spend for a RESOLVED_ROLES role's id MUST use `pricing_for(id)`
# below, not a raw dict `.get`. LIMIT, stated plainly: a new release that
# changes its TIER's PRICE (not just its id) is mispriced by pricing_for's
# tier-rate fallback until this table is hand-updated — models.list carries
# no pricing, so the resolver cannot verify rates; pricing_for logs a WARNING
# every time it uses the fallback so this doesn't stay silent.
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


def pricing_for(model_id: str) -> dict[str, float]:
    """$/MTok {input, output} for `model_id`. Exact match first (covers every
    literal id already in PRICING_PER_MTOK, current + historical). Falls back
    to the id's PARSED TIER's pin rate for a genuine tracked-family release
    that isn't in the table yet (e.g. a fresh effective_model("JUDGE_MODEL")
    resolution) — same $/tier as the pin, the best available estimate
    (models.list carries no pricing) and LOGGED every time so a stale rate
    table doesn't stay a silent mis-price. Final fallback:
    DEFAULT_PRICING_PER_MTOK, for ids in no recognised family at all."""
    exact = PRICING_PER_MTOK.get(model_id)
    if exact is not None:
        return exact
    parsed = _parse_model_id(model_id)
    tier_pin = _TIER_PINS.get(parsed.family) if parsed else None
    tier_price = PRICING_PER_MTOK.get(tier_pin) if tier_pin else None
    if tier_price is not None:
        import logging
        logging.getLogger(__name__).warning(
            "llm_models.pricing_for: %r not in PRICING_PER_MTOK — pricing at "
            "its %s-tier rate (%s) as the best available estimate; add an "
            "explicit entry once the real rate for this id is confirmed.",
            model_id, parsed.family, tier_pin,
        )
        return tier_price
    return DEFAULT_PRICING_PER_MTOK

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
