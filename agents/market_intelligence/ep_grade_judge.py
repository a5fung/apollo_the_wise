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
import hashlib
import logging

from agents.market_intelligence.catalyst_materiality import format_market_cap

logger = logging.getLogger(__name__)

from agents.market_intelligence.judge_transport import invoke_forced_tool
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
        # fire_axes REQUIRED (#249): it is THE fire signal — a model omission
        # must not masquerade as "judge saw no fire" (empty list). Omission →
        # None in _normalize_verdict → fire_axes column stays NULL (not adjudicated).
        "required": ["grade", "tier", "direction_vs_floor", "fire_axes", "rationale"],
    },
}

# Rubric VERSIONING (operator directive 2026-06-11): every signed rubric change
# bumps the human label; the hash is computed FROM the text so any edit — signed
# or accidental — changes the recorded version. Both are stamped on every
# ep_grade_decision payload + the alert row, so evals/replays can segment by
# prompt era instead of silently mixing them (Phase A of #268 ran v1; Phase B
# runs v2 — distinguishable forever).
# v1 = ADR 0011 as signed 2026-06-08. v2 = #269 revenue-over-EPS amendment.
# v3 = catalyst-freshness clause (operator-signed 2026-06-12; the AKTS case —
# judge promoted MODERATE→HIGH on a May-2024 Lilly partnership surfaced undated
# by a web-only corpus; materiality without freshness must never clear HIGH).
RUBRIC_VERSION = "v3-2026-06-12-catalyst-freshness"

_RUBRIC = """You are the EP (Episodic Pivot) grade judge for a momentum trading system
(Qullamaggie / Pradeep Bonde methodology). You decide the grade HOLISTICALLY — you may move
it UP or DOWN versus the raw gap magnitude on any axis. Output via the grade_ep tool.

RUBRIC (in priority order):
1. A REAL, MATERIAL catalyst is REQUIRED for HIGH. A gap alone NEVER earns HIGH — gap+volume
   is only the market's vote that a reason might exist, never sufficient on its own.
   FRESHNESS is part of REAL: the catalyst must be NEW — dated today/overnight, or confirmed
   freshly disclosed by a direct primary source (SEC filing / press wire). An UNDATED catalyst,
   or one the evidence shows predates the gap, CANNOT be the attributed driver no matter how
   material (a years-old partnership resurfacing in a web summary is not today's catalyst).
   If no fresh verifiable driver exists, say the driver is UNIDENTIFIED and grade only what is
   verifiable — MODERATE at best, usually routine. has_direct_source=false combined with a
   materiality-driven promotion is the highest-risk pattern: apply explicit skepticism and
   prefer the floor tier unless freshness is established.
2. MATERIALITY is bidirectional and judged RELATIVE TO COMPANY SIZE (market cap below):
   - a catalyst that is transformative relative to a small company PROMOTES the grade (a
     $30M deal for a $100M micro-cap is huge), even if the magnitude grader under-rated it;
   - a catalyst that is immaterial for a large company DEMOTES it (a $270M contract for a
     $600B mega-cap is a rounding error) however positively worded.
3. Pradeep catalyst hierarchy (strongest first): theme > government policy > supply shortage
   > sales acceleration / new product / management change.
4. EARNINGS catalysts on GROWTH names: REVENUE growth/acceleration (Q/Q + Y/Y, ideally with
   a guidance RAISE) is the load-bearing signal — the market does not pay for EPS changes on
   growth stocks. An EPS beat with flat or missing revenue is NOT a HIGH catalyst. EPS becomes
   the signal only in TURNAROUND situations (loss→profit inflection, first-profitability
   flip) — and the turnaround must be SUSTAINABLE/structural (margin or demand inflection
   confirmed by revenue), NOT a single-quarter anomaly from one-time or external items
   (asset sale, litigation settlement, tax benefit) — the CBRL class.
5. Theme heat + technical structure + gap alignment modulate the grade up or down (a strong
   name can be lifted to game_changer by a hot theme + clean structure).
6. M&A: if the company is being acquired (buyout/merger/tender/going-private), grade "mna" —
   but this is advisory; a separate M&A filter is authoritative.

Be skeptical: vague/numberless "earnings", boilerplate PR, broad sector drift, or a
short-squeeze with no concrete company event = routine. State the load-bearing reason in the
rationale (<= 3 sentences). direction_vs_floor compares your tier to the floor tier given."""

# Auto-derived from the text — changes whenever ANY character of the rubric does.
RUBRIC_HASH = hashlib.sha1(_RUBRIC.encode("utf-8")).hexdigest()[:8]


def assemble_judge_inputs(
    r: dict,
    *,
    grounded_text: str | None = None,
    materiality_tier: str | None = None,
    market_cap=None,
    sector: str | None = None,
    revenue_stage: bool | None = None,
    has_direct_source: bool | None = None,
    active_narratives: list[dict] | None = None,
    tape: dict | None = None,
) -> dict:
    """Pack the per-candidate signals (already computed in run_ep_scan) into the judge
    payload. Builds nothing new — pulls from the result dict `r` plus the few extras the
    scan has in scope (grounded_text, materiality, profile).

    `materiality_tier` (W4 #245) is the DETERMINISTIC deal-size÷market-cap rule tier ONLY
    (catalyst_materiality.rule_materiality) — the exact ratio the LLM can't compute. The
    judge's own call owns the soft/abstain materiality (it outputs materiality_tier over the
    same grounded_text+cap); None here means "no deal-context dollar value — judge it
    yourself" (earnings revenue/guidance figures deliberately don't count, #251).

    `active_narratives` (Lane-2 → theme axis, plan lane2-judge-theme-axis): recent
    narrative cohorts as [{run_date, name, tickers, thesis}], NOT a boolean — the judge
    semantically matches the catalyst against active narratives, so a NEW JOINER of a
    spreading story lights the axis even when ticker-set membership (in_narrative_cohort)
    is false (the RCAT 5/28 class). None/empty → prompt byte-identical to pre-change.

    `tape` (v2.0-P2 / #299) is the structured tape-feature block — opening-range character
    (OR range ÷ ATR; the violent-open KLAR/DELL/NVTS cohort), premarket-volume-curve shape
    vs the minute-volume baselines (mi_minute_volume_curves), liquidity/spread flags. This
    is the PAYLOAD STRUCTURE only (behavior-neutral, like active_narratives): the scan does
    NOT pass it yet — wiring it into the live judge is gated on the with-vs-without eval +
    sign-off (the judge is load-bearing). None → prompt byte-identical to pre-change."""
    return {
        "ticker": r.get("ticker"),
        "grounded_text": (grounded_text or r.get("catalyst") or "")[:6000],
        "catalyst": (r.get("catalyst") or "")[:1500],
        "analysis": (r.get("claude_analysis") or "")[:1500],
        "has_direct_source": has_direct_source,
        "materiality_tier": materiality_tier,
        "in_active_theme": bool(r.get("in_active_theme")),
        "in_narrative_cohort": bool(r.get("in_narrative_cohort")),
        "active_narratives": [
            {
                "run_date": str(c.get("run_date") or ""),
                "name": (c.get("name") or "")[:80],
                "tickers": list(c.get("tickers") or [])[:12],
                "thesis": (c.get("thesis") or "")[:200],
            }
            for c in (active_narratives or [])[:5]
        ],
        "gap_pct": r.get("gap_pct"),
        "pm_rvol": r.get("pm_rvol"),
        "vol_percentile": r.get("vol_percentile"),
        "ep_score": r.get("ep_score"),
        "floor_tier": r.get("score_tier"),
        "floor_catalyst_quality": r.get("catalyst_quality"),
        "market_cap": market_cap,
        "sector": sector,
        "revenue_stage": revenue_stage,
        "tape": tape,
    }


def _build_judge_prompt(p: dict) -> str:
    def _b(v):
        return "yes" if v else "no"
    # Lane-2 narratives block (plan lane2-judge-theme-axis). Rendered ONLY when cohorts
    # exist — empty/missing list keeps the prompt byte-identical to the pre-change form,
    # so shipping this is behavior-neutral until the scan passes cohorts in.
    narr_block = ""
    if p.get("active_narratives"):
        lines = "\n".join(
            f"- {c.get('run_date')} \"{c.get('name')}\" ({', '.join(c.get('tickers') or [])}): {c.get('thesis')}"
            for c in p["active_narratives"]
        )
        narr_block = f"""

--- ACTIVE NARRATIVE COHORTS (Lane 2 — groups that recently gapped together on a SHARED story; discovered EOD on prior days) ---
{lines}
Match the CATALYST against these narratives: a catalyst that JOINS an active narrative (same story, new name — e.g. a drone-defense contract while a drone-defense cohort is active) lights the theme/narrative axis EVEN IF this ticker is not listed as a cohort member. A name merely sharing a sector with a cohort, without the story, does not."""
    # Tape-feature block (v2.0-P2 / #299). Rendered ONLY when the scan passes a tape dict —
    # absent/None keeps the prompt byte-identical to the pre-change form, so the structure
    # ships behavior-neutral (the wire-in is eval-gated; the judge is load-bearing).
    tape_block = ""
    t = p.get("tape")
    if t:
        tape_block = f"""

--- TAPE / INTRADAY CHARACTER (structured; opening-range vs the name's own volatility, premarket pace vs its baseline) ---
Opening-range ÷ ATR: {t.get('opening_range_atr')} (>~0.25-0.30 = a violent open — bracket geometry is structurally poor; weigh entry quality, not just the catalyst)
Premarket volume-curve vs baseline: {t.get('pm_vol_curve')}
Liquidity / spread: {t.get('liquidity')}"""
    return f"""{_RUBRIC}

--- SETUP ---
Ticker: {p.get('ticker')}  |  Sector: {p.get('sector') or 'unknown'}
Market cap: {format_market_cap(p.get('market_cap'))}  |  Revenue-stage: {_b(p.get('revenue_stage'))}
Gap: {p.get('gap_pct')}%  |  Pre-mkt RVOL: {p.get('pm_rvol')}  |  Vol %ile: {p.get('vol_percentile')}
Floor grade (the system's current gap+enum verdict): tier={p.get('floor_tier')} catalyst={p.get('floor_catalyst_quality')}
In active theme (Lane 1): {_b(p.get('in_active_theme'))}  |  In narrative cohort (Lane 2): {_b(p.get('in_narrative_cohort'))}
Deal-size ÷ market-cap (deterministic ratio, when a deal value is parseable): {p.get('materiality_tier') or 'n/a — judge materiality yourself'}  |  Direct source present: {_b(p.get('has_direct_source'))}{narr_block}

--- GROUNDED CATALYST CORPUS (SEC + wires + web) ---
{p.get('grounded_text') or 'No grounded corpus.'}

--- ANALYST NOTE ---
{p.get('analysis') or '(none)'}{tape_block}"""


def format_tier_transition(floor_tier, judge_tier) -> str:
    """#253 presentation contract, ONE copy (digest + replay + delta review all use it):
    direction_vs_floor is the judge's qualitative call and can disagree with the tier
    outcome — a `promote` with the tier held is a quality read, NOT a tier upgrade, and
    must never render as one."""
    if judge_tier != floor_tier:
        return f"{floor_tier}→{judge_tier}"
    return f"{floor_tier} (tier held — quality read)"


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
        # Distinguish OMITTED (None → fire_axes column stays NULL = not
        # adjudicated) from explicit [] (= judge saw no fire on any axis).
        _axes_raw = raw.get("fire_axes")
        axes = (None if _axes_raw is None
                else [a for a in _axes_raw if a in ("catalyst", "theme", "narrative")])
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
    image_png: bytes | None = None,
) -> dict | None:
    """One holistic judge call. Returns the verdict dict (schema), or None on any
    error/timeout — the caller then falls back to the conviction floor (FAIL-OPEN). The
    `semaphore` (shared with the catalyst grader in prod) bounds total Anthropic
    concurrency; the `wait_for` bounds total time incl. queueing for the 9:45 cutoff.

    `image_png` (#267 chart-vision, W4) optionally attaches a point-in-time daily chart so
    the judge can read the price/MA/volume structure. None = byte-identical text-only call
    (the live grade path passes None until the rubric axis is sign-off-gated live; only the
    eval harness passes a chart today)."""
    return await invoke_forced_tool(
        client, _build_judge_prompt(payload),
        tool=_JUDGE_TOOL, tool_name="grade_ep",
        normalize=_normalize_verdict, label="holistic judge",
        subject=payload.get("ticker") or "",
        semaphore=semaphore, timeout=timeout, model=model, image_png=image_png)
