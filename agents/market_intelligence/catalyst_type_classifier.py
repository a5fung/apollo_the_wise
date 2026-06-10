"""Isolated catalyst-TYPE classifier — Pradeep Bonde catalyst hierarchy.

North Star (2026-05-30): the EP score grades catalyst MAGNITUDE
(game_changer / strong / routine) + gap, but never catalyst TYPE. Pradeep
ranks catalyst *types*: theme > govt policy > shortage > company-operational
(sales acceleration / new product / management change). A theme- or
policy-driven gap is a far higher-conviction EP than an isolated operational
beat at the same magnitude — and a no-narrative gap is not an EP at all
(gap = smoke; catalyst = fire). This adds the missing fire-identity signal.

DELIBERATELY DECOUPLED from `ep_detector._classify_catalyst_claude` (the
`quality` grader whose output GATES real entries via the conviction floor +
catalyst rubric + earnings-downgrade). We do NOT extend that call: an additive
schema/prompt change measurably shifts LLM output and would churn the gating
path. This is a SEPARATE isolated call → `quality` stays byte-identical.

ADVISORY ONLY: the emitted catalyst_type is recorded + surfaced; it does NOT
modify ep_score or gate entries. Purpose = accrue the queryable paired dataset
(catalyst_type → forward outcome) that will later calibrate a composite
meta-rubric (Phase 5) + gating (Phase 6). No composite / no weights here —
that is exactly what the forward data must teach (layer-2/3, not now).

Fail-open: any hard error → catalyst_type=None (NULL in DB), never raises to
the caller. Telemetry must never jeopardize the alert. NOTE the distinction:
None (NULL) = the classifier FAILED/was unavailable (infra). "unknown" = the
classifier RAN but couldn't identify a catalyst — a KNOWLEDGE/coverage GAP
(the catalyst almost certainly exists for a hard +vol gap; our info just didn't
surface it), NOT a claim that no catalyst exists. We deliberately do NOT have a
"none" class — absence-of-evidence is not evidence-of-absence (operator 2026-05-30).

Uses tool_choice structured output (not raw-JSON parsing) per the codebase's
silent-failure discipline — schema-valid output guaranteed, no string parsing.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from shared.llm_models import CATALYST_TYPE_MODEL

logger = logging.getLogger(__name__)

# Pradeep Bonde catalyst hierarchy (most → least powerful), verbatim 2026-05-17:
# "Theme is most powerful catalyst. Followed by govt policy change. Third is
#  shortages. Fourth is sales acceleration, new products launch, management
#  change and so on."  (see memory user_pradeep_catalyst_hierarchy)
CATALYST_TYPES: tuple[str, ...] = (
    "theme", "policy", "shortage",
    "sales_acceleration", "new_product", "management_change",
    "pre_catalyst_anticipation",  # gap AHEAD of an imminent-but-unannounced catalyst
    "other",
    # "unknown" — NOT "none": a +vol gap almost always HAS a catalyst; we just
    # couldn't identify it (news-coverage / extraction gap). Honest agnosticism,
    # and a queryable signal of WHERE our information pipeline is blind (→ #149).
    "unknown",
)

# Rank for downstream ordering/analysis (lower = more powerful per Pradeep).
CATALYST_TYPE_RANK: dict[str, int] = {t: i for i, t in enumerate(CATALYST_TYPES)}

# The high-conviction subset (Pradeep's top 3) — SSoT for "is this a TOP-tier
# fire." Consumed by the EP alert/briefing markers + analysis cuts so the
# displayed 🎯 set and the analyzed set can't drift (re-tiered here once).
HIGH_CONVICTION_TYPES: frozenset[str] = frozenset({"theme", "policy", "shortage"})

# NON_FIRE_TYPES (#201 fire panel) RETIRED 2026-06-10 (#249) — the judge's
# verdict fire_axes is the fire signal now (ADR 0010 superseded). The
# 'unknown'/'pre_catalyst_anticipation' values live on only in the frozen
# historical fire_status rows (see db.EP_UNKNOWN_NONFIRE_SQL).

_CATALYST_TYPE_TOOL = {
    "name": "classify_catalyst_type",
    "description": (
        "Classify the STRUCTURAL TYPE of a stock's gap-up catalyst per the "
        "Pradeep Bonde hierarchy. TYPE is independent of MAGNITUDE — a modest "
        "theme- or policy-driven move outranks a large isolated earnings beat."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "catalyst_type": {
                "type": "string",
                "enum": list(CATALYST_TYPES),
                "description": (
                    "theme: part of an industry-wide / sector secular tailwind shared "
                    "by peers (AI infrastructure, drones/defense, GLP-1, nuclear, "
                    "crypto-treasury) — NOT idiosyncratic to this one company. "
                    "policy: government / regulatory driver — funding or subsidy, "
                    "tariff, FDA approval, federal or defense contract award, legislation. "
                    "shortage: structural supply/demand imbalance in a commodity, "
                    "component, or capacity (memory, copper, shipping, grid power). "
                    "sales_acceleration: company-specific multi-quarter revenue/earnings "
                    "inflection or beat-and-raise, idiosyncratic (no theme/policy). "
                    "new_product: launch of a TAM-expanding product or platform. "
                    "management_change: high-profile leadership change. "
                    "pre_catalyst_anticipation: the gap is AHEAD of an imminent but "
                    "NOT-yet-public catalyst (gapping INTO unreleased earnings, an awaited "
                    "ruling/data readout) — positioning/anticipation, NOT a reaction to "
                    "already-announced news. Distinct from 'unknown' (catalyst not "
                    "identified) and from a post-announcement reaction. "
                    "other: real but pedestrian company news — in-line/small beat, minor "
                    "contract, buyback, routine partnership/PR with no concrete metrics. "
                    "unknown: you could NOT identify the catalyst from the available info. "
                    "Use this honestly — a stock gapping hard on volume almost always HAS a "
                    "catalyst; 'unknown' means OUR information didn't surface it (a coverage/"
                    "knowledge gap), NOT that no catalyst exists. Prefer 'unknown' over forcing "
                    "a weak guess. "
                    "If MULTIPLE apply, pick the HIGHEST in the hierarchy "
                    "(theme > policy > shortage > sales_acceleration > new_product > "
                    "management_change > pre_catalyst_anticipation > other > unknown)."
                ),
            },
            "rationale": {
                "type": "string",
                "description": "One sentence naming the specific driver and why this type.",
            },
        },
        "required": ["catalyst_type", "rationale"],
    },
}

_SYSTEM = (
    "You are a precise market-microstructure classifier identifying the "
    "STRUCTURAL TYPE of an episodic-pivot catalyst, not its size. Be skeptical: "
    "vague or generic news with no identifiable driver is 'unknown'; a routine in-line "
    "beat or a metric-free partnership/PR is 'other'. Reserve theme / policy / "
    "shortage for genuine sector-wide, regulatory, or supply-imbalance drivers."
)

_client = None
_SEM = asyncio.Semaphore(5)


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _client


async def classify_catalyst_type(
    ticker: str,
    catalyst_text: str | None,
    claude_analysis: str | None = None,
    *,
    sector: str | None = None,
) -> dict[str, Optional[str]]:
    """Classify catalyst TYPE (Pradeep hierarchy). ADVISORY — never gates.

    Returns {"catalyst_type": <enum | None>, "rationale": <str | None>}.
    Fail-open: any hard error → {"catalyst_type": None, "rationale": None}
    (NULL in DB; distinct from the model genuinely returning "none"). Never raises.
    """
    blob = "\n".join(p for p in (
        f"Ticker: {ticker}" + (f" (sector: {sector})" if sector else ""),
        f"Catalyst: {catalyst_text}" if catalyst_text else "",
        f"Prior analysis: {claude_analysis}" if claude_analysis else "",
    ) if p)

    if not (catalyst_text or claude_analysis):
        # No text to work from → we don't know (a coverage gap), not "no catalyst".
        return {"catalyst_type": "unknown", "rationale": "no catalyst text available"}

    prompt = (
        "Classify the structural TYPE of this stock gap-up catalyst per the "
        "Pradeep hierarchy. Type is independent of magnitude.\n\n" + blob
    )
    try:
        import anthropic
        async with _SEM:
            resp = None
            for attempt in range(2):
                try:
                    resp = await _get_client().messages.create(
                        model=CATALYST_TYPE_MODEL,
                        max_tokens=220,
                        system=_SYSTEM,
                        tools=[_CATALYST_TYPE_TOOL],
                        tool_choice={"type": "tool", "name": "classify_catalyst_type"},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt == 1:
                        raise
                    await asyncio.sleep(2 + attempt)
        block = next(b for b in resp.content if b.type == "tool_use")
        ct = block.input.get("catalyst_type")
        if ct not in CATALYST_TYPES:
            logger.warning(f"catalyst_type out-of-enum for {ticker}: {ct!r}")
            return {"catalyst_type": None, "rationale": None}
        return {
            "catalyst_type": ct,
            "rationale": (block.input.get("rationale") or "")[:300] or None,
        }
    except Exception as e:
        # Fail-open: telemetry never jeopardizes the alert.
        logger.warning(
            f"catalyst_type classification failed for {ticker}: "
            f"{type(e).__name__}: {e}"
        )
        return {"catalyst_type": None, "rationale": None}
