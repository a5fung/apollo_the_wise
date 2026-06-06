"""Catalyst materiality judgment (#189) — pure helpers + LLM contract.

NORTH STAR (ep_fire_panel_load_bearing_design): "news existence != EP-grade."
A catalyst is only a real fire if it is MATERIAL relative to the company — a $50M
deal is a game_changer for a $200M micro-cap and a rounding error for a $600B mega.
The grade prompt already carries a materiality RULE (rule 5), but it is folded into
the grade enum and can't be read separately; the fire panel (#201) currently lights
the catalyst axis on grade + named-type alone, which the design memory projects runs
~95% fire_seen (too permissive). #189 makes materiality an EXPLICIT, separable signal.

STATUS — SHADOW/EVAL ONLY. This module is intentionally NOT imported by run_ep_scan
or _compute_fire_status. Wiring materiality into the fire panel is a POST-Monday
CHANGE_PROCESS flip, made against the real fire_status baseline that first lands
2026-06-08 (#200/#201 verify). Until then this backs the read-only eval
(scripts/eval_catalyst_materiality.py) that measures whether low-materiality
graded-strong alerts actually underperform — the evidence the activation needs.

The pure helpers here (deal-value parsing, ratio bucketing) are deterministic and
unit-tested; the LLM judgment layer lives in the caller (eval now, wiring later).
"""
from __future__ import annotations

import re

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


def extract_deal_value(text: str | None) -> float | None:
    """Largest dollar amount mentioned in `text`, in absolute dollars, or None.

    Returns the MAX match — a press release often cites several figures (revenue,
    deal size, buyback); the largest is the best proxy for the headline magnitude.
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
