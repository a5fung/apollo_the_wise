"""EP Holistic Grade Judge (#240 / ADR 0011) — the North Star grade decision.

ONE LLM call that judges the EP grade holistically over the full rubric (grounded
catalyst + materiality + theme + narrative + technical structure + gap) and moves the
grade BIDIRECTIONALLY — promote an under-rated outlier, demote an immaterial big-grade —
superseding the conviction floor's gap+enum authority.

STATUS — Wave 1 SHADOW: this module is wired into run_ep_scan but writes only the
advisory `judge_tier`/direction/rationale columns and **drives nothing**; the live grade
stays the conviction floor (fed by `_classify_catalyst_claude`, retained as the fallback
grader per ADR 0011). The Wave-2 flip makes the judge load-bearing on the PAPER path.

Pure-ish + testable: `grade_holistic(client, payload)` takes the Anthropic client (a fake
in tests) and FAILS OPEN — returns None on any error/timeout, so the caller falls back to
the floor and a real EP is never killed by a judge hiccup.
"""
from __future__ import annotations

import asyncio
import logging

from agents.market_intelligence.catalyst_materiality import format_market_cap

logger = logging.getLogger(__name__)

from shared.llm_models import JUDGE_MODEL as MODEL  # Wave-1 default; the live model is chosen by the W1 eval.

GRADES = ("game_changer", "strong", "routine", "mna")
TIERS = ("HIGH", "MODERATE", "none")
DIRECTIONS = ("promote", "hold", "demote")
MATERIALITY_TIERS = ("transformative", "material", "minor", "immaterial")

# Locked output schema (ADR 0011). tool_choice forces a schema-valid object — no string
# parsing, no silent fallback to a default tier.
_JUDGE_TOOL = {
    "name": "grade_ep",
    "description": "Holistically grade an EP (Episodic Pivot) gap-up setup over the full rubric.",
    "input_schema": {
        "type": "object",
        "properties": {
            "grade": {"type": "string", "enum": list(GRADES)},
            "tier": {"type": "string", "enum": list(TIERS)},
            "direction_vs_floor": {"type": "string", "enum": list(DIRECTIONS)},
            "materiality_tier": {"type": "string", "enum": list(MATERIALITY_TIERS)},
            "fire_axes": {
                "type": "array",
                "items": {"type": "string", "enum": ["catalyst", "theme", "narrative"]},
            },
            "rationale": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["grade", "tier", "direction_vs_floor", "rationale"],
    },
}

_RUBRIC = """You are the EP (Episodic Pivot) grade judge for a momentum trading system
(Qullamaggie / Pradeep Bonde methodology). You decide the grade HOLISTICALLY — you may move
it UP or DOWN versus the raw gap magnitude on any axis. Output via the grade_ep tool.

RUBRIC (in priority order):
1. A REAL, MATERIAL catalyst is REQUIRED for HIGH. A gap alone NEVER earns HIGH — gap+volume
   is only the market's vote that a reason might exist, never sufficient on its own.
2. MATERIALITY is bidirectional and judged RELATIVE TO COMPANY SIZE (market cap below):
   - a catalyst that is transformative relative to a small company PROMOTES the grade (a
     $30M deal for a $100M micro-cap is huge), even if the magnitude grader under-rated it;
   - a catalyst that is immaterial for a large company DEMOTES it (a $270M contract for a
     $600B mega-cap is a rounding error) however positively worded.
3. Pradeep catalyst hierarchy (strongest first): theme > government policy > supply shortage
   > sales acceleration / new product / management change.
4. Theme heat + technical structure + gap alignment modulate the grade up or down (a strong
   name can be lifted to game_changer by a hot theme + clean structure).
5. M&A: if the company is being acquired (buyout/merger/tender/going-private), grade "mna" —
   but this is advisory; a separate M&A filter is authoritative.

Be skeptical: vague/numberless "earnings", boilerplate PR, broad sector drift, or a
short-squeeze with no concrete company event = routine. State the load-bearing reason in the
rationale (<= 3 sentences). direction_vs_floor compares your tier to the floor tier given."""


def assemble_judge_inputs(
    r: dict,
    *,
    grounded_text: str | None = None,
    materiality_tier: str | None = None,
    market_cap=None,
    sector: str | None = None,
    revenue_stage: bool | None = None,
    has_direct_source: bool | None = None,
) -> dict:
    """Pack the per-candidate signals (already computed in run_ep_scan) into the judge
    payload. Builds nothing new — pulls from the result dict `r` plus the few extras the
    scan has in scope (grounded_text, materiality, profile).

    `materiality_tier` (W4 #245) is the DETERMINISTIC deal-size÷market-cap rule tier ONLY
    (catalyst_materiality.rule_materiality) — the exact ratio the LLM can't compute. The
    judge's own call owns the soft/abstain materiality (it outputs materiality_tier over the
    same grounded_text+cap); None here means "no deal-context dollar value — judge it
    yourself" (earnings revenue/guidance figures deliberately don't count, #251)."""
    return {
        "ticker": r.get("ticker"),
        "grounded_text": (grounded_text or r.get("catalyst") or "")[:6000],
        "catalyst": (r.get("catalyst") or "")[:1500],
        "analysis": (r.get("claude_analysis") or "")[:1500],
        "has_direct_source": has_direct_source,
        "materiality_tier": materiality_tier,
        "in_active_theme": bool(r.get("in_active_theme")),
        "in_narrative_cohort": bool(r.get("in_narrative_cohort")),
        "gap_pct": r.get("gap_pct"),
        "pm_rvol": r.get("pm_rvol"),
        "vol_percentile": r.get("vol_percentile"),
        "ep_score": r.get("ep_score"),
        "floor_tier": r.get("score_tier"),
        "floor_catalyst_quality": r.get("catalyst_quality"),
        "market_cap": market_cap,
        "sector": sector,
        "revenue_stage": revenue_stage,
    }


def _build_judge_prompt(p: dict) -> str:
    def _b(v):
        return "yes" if v else "no"
    return f"""{_RUBRIC}

--- SETUP ---
Ticker: {p.get('ticker')}  |  Sector: {p.get('sector') or 'unknown'}
Market cap: {format_market_cap(p.get('market_cap'))}  |  Revenue-stage: {_b(p.get('revenue_stage'))}
Gap: {p.get('gap_pct')}%  |  Pre-mkt RVOL: {p.get('pm_rvol')}  |  Vol %ile: {p.get('vol_percentile')}
Floor grade (the system's current gap+enum verdict): tier={p.get('floor_tier')} catalyst={p.get('floor_catalyst_quality')}
In active theme (Lane 1): {_b(p.get('in_active_theme'))}  |  In narrative cohort (Lane 2): {_b(p.get('in_narrative_cohort'))}
Deal-size ÷ market-cap (deterministic ratio, when a deal value is parseable): {p.get('materiality_tier') or 'n/a — judge materiality yourself'}  |  Direct source present: {_b(p.get('has_direct_source'))}

--- GROUNDED CATALYST CORPUS (SEC + wires + web) ---
{p.get('grounded_text') or 'No grounded corpus.'}

--- ANALYST NOTE ---
{p.get('analysis') or '(none)'}"""


def _normalize_verdict(raw: dict) -> dict | None:
    """Validate the tool output against the schema; return a clean dict or None if the
    required enums are malformed (caller fails open)."""
    try:
        grade = (raw.get("grade") or "").lower()
        tier = raw.get("tier") or ""
        direction = (raw.get("direction_vs_floor") or "").lower()
        if grade not in GRADES or tier not in TIERS or direction not in DIRECTIONS:
            return None
        mt = (raw.get("materiality_tier") or "").lower()
        axes = [a for a in (raw.get("fire_axes") or []) if a in ("catalyst", "theme", "narrative")]
        return {
            "grade": grade,
            "tier": tier,
            "direction_vs_floor": direction,
            "materiality_tier": mt if mt in MATERIALITY_TIERS else None,
            "fire_axes": axes,
            "rationale": (raw.get("rationale") or "")[:1000],
            "confidence": raw.get("confidence"),
        }
    except (AttributeError, TypeError):
        return None


async def grade_holistic(
    client,
    payload: dict,
    *,
    semaphore: asyncio.Semaphore | None = None,
    timeout: float = 15.0,
    model: str = MODEL,
) -> dict | None:
    """One holistic judge call. Returns the verdict dict (schema), or None on any
    error/timeout — the caller then falls back to the conviction floor (FAIL-OPEN). The
    `semaphore` (shared with the catalyst grader in prod) bounds total Anthropic
    concurrency; the `wait_for` bounds total time incl. queueing for the 9:45 cutoff."""
    if client is None:
        return None
    prompt = _build_judge_prompt(payload)

    async def _call():
        kwargs = dict(
            model=model, max_tokens=500, tools=[_JUDGE_TOOL],
            tool_choice={"type": "tool", "name": "grade_ep"},
            messages=[{"role": "user", "content": prompt}],
        )
        if semaphore is not None:
            async with semaphore:
                return await client.messages.create(**kwargs)
        return await client.messages.create(**kwargs)

    try:
        resp = await asyncio.wait_for(_call(), timeout=timeout)
        tool_block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
        return _normalize_verdict(tool_block.input)
    except Exception as e:  # noqa: BLE001 — fail-open is the contract
        logger.warning(f"holistic judge failed/timeout for {payload.get('ticker')}: {e}")
        return None
