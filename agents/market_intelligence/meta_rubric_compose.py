"""ADR 0024 M1-a — the meta-rubric tier composition (built DARK, default OFF).

`compose_final_tier(base_tier, credits) -> (final_tier, composition)` composes the judge's
CATALYST verdict (or the floor tier on fallback) with the scored context axes' CONTEXT credit
into one final tier. Per ADR 0024 §2/§3 + fork F2:
  - tier lattice: none < MODERATE < HIGH (constants.TIER_LATTICE) — nothing composes above HIGH
    or below none;
  - boost-axes (theme/structure/gap-align) add positive credit_steps per their signed tables;
    the neg axis (dilution, 0021) is demote-only (≤0). This function is AGNOSTIC — it sums the
    signed steps the axes emit and caps the NET;
  - STACKING CAP (F2): net movement ∈ {−1, 0, +1} tier-steps total across ALL axes;
  - returns a fully-named `Composition` trace for the `/why` legibility contract
    ("judge strong (catalyst) + theme Accelerating (+1) − dilution overhang (0) → HIGH").

DARK: `composite_authority_enabled()` defaults OFF and NOTHING consumes `final_tier` live yet.
The M1-d operator sitting flips it (with the rubric amendment, atomically). Pure function — no
DB/LLM/IO; the axes that PRODUCE credits are wired in M1-b/M1-d, not here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from agents.market_intelligence.constants import TIER_LATTICE, TIER_RANK

# Net axis movement cap (fork F2): the composed tier may move at most ±1 step from the base,
# no matter how many axes fire. 0016's proposed default, operator-signed 2026-07-07.
NET_CAP = 1

# DARK authority toggle. Default OFF — the composed tier is computed for measurement but is
# NOT authoritative until the M1-d sitting flips this (ADR 0024 §6). Env-read per call so a
# flip needs no redeploy; a DB-backed toggle can replace the env read at M1-d without touching
# callers of `composite_authority_enabled()`.
COMPOSITE_AUTHORITY_ENV = "COMPOSITE_AUTHORITY"


def composite_authority_enabled() -> bool:
    """Is the composed tier LOAD-BEARING? Default False (dark). Flipped only at the M1-d sitting."""
    return os.environ.get(COMPOSITE_AUTHORITY_ENV, "false").strip().lower() == "true"


@dataclass
class Contribution:
    """One axis's named contribution to the composition (for the /why trace)."""
    axis: str
    steps: int
    marker: str = ""
    reason: str = ""


@dataclass
class Composition:
    """The full, legible trace of a `compose_final_tier` call."""
    base_tier: str
    final_tier: str
    net_raw: int          # sum of all axis credit_steps, uncapped
    net_capped: int       # net_raw clamped to [−NET_CAP, +NET_CAP]
    contributions: list[Contribution] = field(default_factory=list)


def _field(c, key, default):
    """Read `key` from a credit that may be a dict or an object (axes emit either)."""
    if isinstance(c, dict):
        return c.get(key, default)
    return getattr(c, key, default)


def compose_final_tier(base_tier: str, credits) -> tuple[str, Composition]:
    """Compose the final tier from a base tier + per-axis context credits.

    base_tier: a tier string in TIER_LATTICE — the judge_tier when authority=judge, else the
      floor tier (the SAME function composes on fallback — no separate path).
    credits: iterable of per-axis credits, each a dict/obj carrying `credit_steps` (signed int)
      + optional `axis`/`marker`/`reason`. Boost-axes emit ≥0; the neg axis emits ≤0.
    Returns (final_tier, Composition). Never raises on the credits; raises ValueError only on an
    unknown base_tier (fail loud — a bad tier string is a caller bug, not runtime data)."""
    if base_tier not in TIER_RANK:
        raise ValueError(f"compose_final_tier: base_tier {base_tier!r} not in {TIER_LATTICE}")

    contributions: list[Contribution] = []
    net_raw = 0
    for c in credits or []:
        steps = int(_field(c, "credit_steps", 0) or 0)
        net_raw += steps
        contributions.append(Contribution(
            axis=str(_field(c, "axis", "?")),
            steps=steps,
            marker=str(_field(c, "marker", "") or ""),
            reason=str(_field(c, "reason", "") or ""),
        ))

    net_capped = max(-NET_CAP, min(NET_CAP, net_raw))
    final_idx = TIER_RANK[base_tier] + net_capped
    final_idx = max(0, min(len(TIER_LATTICE) - 1, final_idx))  # clamp to the lattice
    final_tier = TIER_LATTICE[final_idx]

    return final_tier, Composition(
        base_tier=base_tier, final_tier=final_tier,
        net_raw=net_raw, net_capped=net_capped, contributions=contributions,
    )
