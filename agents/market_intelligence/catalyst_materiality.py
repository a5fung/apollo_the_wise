"""Catalyst materiality judgment (#189) — pure helpers + LLM contract.

NORTH STAR (ep_fire_panel_load_bearing_design): "news existence != EP-grade."
A catalyst is only a real fire if it is MATERIAL relative to the company — a $50M
deal is a game_changer for a $200M micro-cap and a rounding error for a $600B mega.
The grade prompt already carries a materiality RULE (rule 5), but it is folded into
the grade enum and can't be read separately; the fire panel (#201) currently lights
the catalyst axis on grade + named-type alone, which the design memory projects runs
~95% fire_seen (too permissive). #189 makes materiality an EXPLICIT, separable signal.

STATUS — JUDGE INPUT (since #245/#249). The deterministic helpers
(extract_deal_value + rule_materiality) feed the holistic grade judge's payload on
the live scan path (ep_detector._judge_shadow); the judge's own Sonnet call owns the
soft/abstain materiality tier, so judge_materiality_llm / assess_materiality back
the read-only eval (scripts/eval_catalyst_materiality.py) only. The earlier ADR 0010
staged flip + OFFLINE shadow writer (materiality_shadow.py, 16:25 job) were retired
2026-06-10 (#249) — superseded by the judge going load-bearing (ADR 0011).

This module still owns BOTH the pure helpers (deal-value parsing, ratio bucketing —
deterministic + unit-tested) AND the one shared Sonnet judgment layer, so the eval
and any future consumer never diverge on the prompt (feedback_single_source_of_truth).
"""
from __future__ import annotations

import json
import re
from shared.llm_response import first_text

# Materiality tiers (ordinal). Higher = more material to the company.
MATERIALITY_TIERS = ("immaterial", "minor", "material", "transformative")
_TIER_ORD = {t: i for i, t in enumerate(MATERIALITY_TIERS)}

# Deal value as a fraction of market cap -> tier. Calibrated to the #189 anchors
# (RUM $270M @ $2.5B ~= 10.8% -> material; the same $270M @ $600B ~= 0.045% ->
# immaterial). Boundaries are deliberately coarse — this is a directional rule,
# not a precise score; the LLM layer handles the soft cases.
_RATIO_TIERS = (
    (0.25, "transformative"),  # >= 25% of cap — bet-the-company scale
    (0.05, "material"),        # >= 5%
    (0.01, "minor"),           # >= 1%
    (0.0, "immaterial"),       # < 1%
)

_MULT = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "trillion": 1e12,
}

# "$270 million", "$1.2B", "$270M", "$500,000", "USD 1.5 billion"
_DEAL_RE = re.compile(
    r"(?:\$|USD\s*)\s*([\d,]+(?:\.\d+)?)\s*(k|m|mm|b|bn|t|thousand|million|billion|trillion)?\b",
    re.IGNORECASE,
)

# #251 context gates: a $ figure only counts as a DEAL value when deal-ish language
# sits nearby AND no financial-metric label claims it first. On an earnings release
# the largest $ figure is usually REVENUE or guidance — which fed the judge a false
# 'transformative' deal÷cap anchor (KSS/PGY, judge_backfill_replay 2026-06-09).
_DEAL_CONTEXT_RE = re.compile(
    r"\b(deal|contract|agreement|acquisitions?|acquir\w*|mergers?|buyout|takeover|"
    r"award\w*|orders?|purchase|sale|buyback|repurchase|tender|invest\w*|"
    r"(?:re)?financing|funding|grants?|settlement|divest\w*|stake|offering|"
    r"valued at|worth|licens\w*|collaboration|partnership|milestones?|"
    r"rais(?:e[sd]?|ing))\b",
    re.IGNORECASE,
)
# NB: deal keyword is singular "sale" (asset sale) — the metric veto owns plural
# "sales" (revenue); \b keeps them disjoint, so number alone disambiguates.
_METRIC_CONTEXT_RE = re.compile(
    r"\b(revenues?|sales|eps|earnings|guidance|ebitda|income|profits?|loss(?:es)?|"
    r"market\s+cap(?:italization)?|backlog|arr)\b",
    re.IGNORECASE,
)
# Clause boundary for the metric veto — keeps "revenue of $500M, a $2.1B order"
# from letting the first clause's "revenue" veto the second clause's real deal.
_CLAUSE_SPLIT_RE = re.compile(r"[,;:.()\n]")


def _is_deal_context(text: str, start: int, end: int) -> bool:
    """Both #251 gates for the $ amount at text[start:end]: metric VETO (a
    financial-metric label in the same clause just before or right after the
    amount → reported figure), then deal-keyword REQUIRE within ±60 chars.
    A clause longer than the 40-char look-back can hide its metric label, but
    such figures still need a deal keyword nearby to pass — the gates are
    redundant in the failure direction (abstain)."""
    pre = _CLAUSE_SPLIT_RE.split(text[max(0, start - 40):start])[-1]
    post = _CLAUSE_SPLIT_RE.split(text[end:end + 20])[0]
    if _METRIC_CONTEXT_RE.search(pre) or _METRIC_CONTEXT_RE.search(post):
        return False
    return bool(_DEAL_CONTEXT_RE.search(text[max(0, start - 60):end + 60]))


def extract_deal_value(text: str | None) -> float | None:
    """Largest DEAL-CONTEXT dollar amount in `text`, in absolute dollars, or None.

    #251: returning the bare MAX figure made earnings revenue look like a deal —
    a false 'transformative' anchor on the judge's materiality axis. Two
    deterministic gates per match now:
      1. metric VETO — a financial-metric label (revenue/EPS/guidance/...) in the
         same clause just before or right after the amount → reported figure, skip.
      2. deal-context REQUIRE — a deal/contract/financing keyword within ±60 chars
         → otherwise skip.
    No qualifying figure → None → rule_materiality ABSTAINS and the judge owns
    materiality (fail-open downstream: is_material(None) is True). Precision over
    recall by design: a missed real deal degrades to "judge decides", never to a
    wrong deterministic anchor.
    Pure + deterministic. Does NOT decide materiality — that needs market cap.
    """
    if not text:
        return None
    best: float | None = None
    for m in _DEAL_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        val *= _MULT.get(unit, 1.0)
        # The regex already requires a $/USD prefix, so years/counts don't match.
        # Drop only unit-less sub-$1000 figures ("$45.20/share", "$5") as price
        # noise; keep comma-grouped amounts like "$500,000".
        if not unit and val < 1000:
            continue
        if not _is_deal_context(text, m.start(), m.end()):
            continue
        if best is None or val > best:
            best = val
    return best


def rule_materiality(deal_value: float | None, market_cap: float | None) -> str | None:
    """Deterministic materiality tier from deal value vs market cap, or None when
    the ratio can't be computed (no deal value parsed, or unknown/zero cap).
    None = 'rules abstain, defer to the LLM judgment' — NOT 'immaterial'."""
    if not deal_value or not market_cap or market_cap <= 0:
        return None
    ratio = deal_value / market_cap
    for threshold, tier in _RATIO_TIERS:
        if ratio >= threshold:
            return tier
    return "immaterial"


def is_material(tier: str | None) -> bool:
    """Collapse a tier to the fire-panel boolean: material/transformative => fire.
    Unknown tier (None) => True (fail-open — never demote on missing signal)."""
    if tier is None:
        return True
    return _TIER_ORD.get(tier, 99) >= _TIER_ORD["material"]


def format_market_cap(mc) -> str:
    """Human market-cap string for the LLM prompt + display ('$2.5B' / '$480M' /
    'unknown'). Tolerant of None / non-numeric."""
    try:
        mc = float(mc)
    except (TypeError, ValueError):
        return "unknown"
    return f"${mc/1e9:.1f}B" if mc >= 1e9 else f"${mc/1e6:.0f}M"


# ── LLM judgment layer (#189) — ONE copy, shared by the eval and the shadow ──
# writer (feedback_single_source_of_truth: a second prompt is the two-impl
# divergence trap). Judges materiality of the STORED grounded catalyst text
# (point-in-time, no lookahead on the input). The LLM is a JUDGE on grounded
# text here, not a discoverer (feedback_catalyst_sourcing_direct_over_llm).
from shared.llm_models import MATERIALITY_MODEL as _MODEL
from shared.output_ceilings import max_tokens_for

_JUDGE_PROMPT = """You judge whether a stock's gap-up catalyst is MATERIAL relative to the company.
Materiality = impact RELATIVE TO COMPANY SIZE, not absolute. A $50M deal is
transformative for a $200M micro-cap and a rounding error for a $600B mega-cap.

Company: {company} — {sector}
Market cap: {mktcap}
Catalyst (as captured at alert time):
{catalyst}

Analyst note:
{analysis}

Return ONLY JSON: {{"tier": one of ["immaterial","minor","material","transformative"], "rationale": "<one sentence>"}}.
- transformative: bet-the-company scale (large fraction of cap/revenue; FDA approval for lead asset; etc.)
- material: a meaningful, needle-moving event for this company's size.
- minor: real but small relative to the company — unlikely to re-rate it.
- immaterial: routine/boilerplate, broad sector drift, or no concrete company-specific event of size.
Be skeptical: a positively-worded press release about a small deal is "minor" or "immaterial"."""


def _extract_json_object(raw: str) -> str:
    """Slice the first balanced {...} object out of an LLM response (handles a
    fenced ```json block + trailing prose). Depth-aware."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rstrip("` \n")
    start, depth = raw.find("{"), 0
    if start < 0:
        return raw
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return raw[start:]


async def judge_materiality_llm(client, *, company, sector, market_cap,
                                catalyst, analysis) -> str | None:
    """Sonnet materiality tier for a (mostly non-deal) catalyst. Returns a tier in
    MATERIALITY_TIERS, or None on any error/parse failure (caller fails OPEN — a
    None tier is treated as material, never demotes). `market_cap` is a raw float
    (or None); formatting happens here so callers pass one shape."""
    prompt = _JUDGE_PROMPT.format(
        company=company or "", sector=sector or "",
        mktcap=format_market_cap(market_cap),
        catalyst=(catalyst or "")[:1500], analysis=(analysis or "")[:1500],
    )
    resp = await client.messages.create(
        model=_MODEL, max_tokens=max_tokens_for("catalyst_materiality"),
        system="You are a JSON API. Respond with valid JSON only.",
        messages=[{"role": "user", "content": prompt}],
    )
    # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    await log_anthropic_call_safe(model=_MODEL, caller="catalyst_materiality",
                                   response=resp)
    raw = first_text(resp)  # #544: never content[0]
    try:
        tier = (json.loads(_extract_json_object(raw)).get("tier") or "").lower()
    except (ValueError, AttributeError):
        return None  # unparseable / non-JSON response — caller fails OPEN
    return tier if tier in MATERIALITY_TIERS else None


async def assess_materiality(client, *, company, sector, market_cap,
                             catalyst, analysis) -> tuple[str | None, str]:
    """Production materiality policy (#189), shared by the shadow writer and the
    eventual #201 fire-panel flip: RULE-FIRST (deterministic deal/cap ratio — free),
    Sonnet ONLY when the rules abstain (no parseable deal value or unknown cap, e.g.
    earnings/sales catalysts). Returns (tier, source) with source ∈
    {'rule','llm','abstain'}. Tier may be None (LLM error / no client) → the caller
    fails OPEN via is_material(None)=True. Never raises."""
    # Coerce market_cap once: FMP's `marketCap` can come back as a STRING, and
    # rule_materiality does arithmetic on it (`<= 0`, division). Without this a
    # deal-value catalyst would TypeError on the rule path (which is outside the
    # try below) → the caller's per-row except would silently skip the write — the
    # #173-class silent-0-rows bug. float-or-None mirrors the eval's coercion.
    try:
        market_cap = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        market_cap = None
    deal = extract_deal_value(f"{catalyst or ''} {analysis or ''}")
    rt = rule_materiality(deal, market_cap)
    if rt is not None:
        return rt, "rule"
    if client is None:
        return None, "abstain"
    try:
        tier = await judge_materiality_llm(
            client, company=company, sector=sector, market_cap=market_cap,
            catalyst=catalyst, analysis=analysis,
        )
        return tier, ("llm" if tier is not None else "abstain")
    except Exception as e:
        # #376: credit exhaustion silently abstains (→ fails OPEN as material) —
        # alert it (deduped) before returning.
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("catalyst materiality", e)
        return None, "abstain"
