"""v2.0-P2 / #299 SLICE B — pure tape-feature COMPUTE for the EP grade judge.

SLICE A shipped the judge-payload STRUCTURE (`ep_grade_judge.assemble_judge_inputs(tape=...)` +
the `--- TAPE / INTRADAY CHARACTER ---` prompt block; byte-identical when `tape` is absent).
This module computes the three tape values that block renders — opening-range ÷ ATR (entry/bracket
geometry character), the premarket volume-curve vs the name's OWN baseline, and a liquidity/spread
tag — as PURE functions over already-fetched inputs (no I/O here; callers supply bars/volumes).

BEHAVIOR-NEUTRAL until wired: `build_tape` returns None unless ≥1 feature is present, and the judge
renders the block only when a tape dict is passed. The scan wire-in + the with-vs-without judge eval
are the next (eval-gated) step — the judge is load-bearing, so the tape must EARN its way in.

Reuses `flag_detector._atr_14` (the tightness ATR reference) and the output shape of
`minute_volume.compute_rvol_at_time` (search-before-build).

TIMING NOTE for the wire-in (not this module): the opening range only exists after ~9:35 ET, but
EP HIGH alerts fire 7:00–10:00 — so OR÷ATR is computable only for post-open alerts. The premarket
volume-curve is the pre-open-available feature. The eval must segment by which features were present.
"""
from typing import Optional

from agents.market_intelligence.flag_detector import _atr_14


def compute_or_atr(or_high: Optional[float], or_low: Optional[float],
                   prior_daily_rows: list, end_idx: Optional[int] = None) -> Optional[float]:
    """Opening-range height ÷ the name's own ATR-14 — the "violent open" / bracket-geometry tell
    (>~0.25–0.30 = a wide, structurally-poor open). `prior_daily_rows` are mi_daily_closes-shaped
    {high_price,low_price,close} ASCENDING through the PRIOR session (ATR is a prior-day measure —
    today's bar must NOT be included). None if the OR or ATR can't be formed."""
    if or_high is None or or_low is None or or_high < or_low:
        return None
    if end_idx is None:
        end_idx = len(prior_daily_rows) - 1
    atr = _atr_14(prior_daily_rows, end_idx)
    if not atr or atr <= 0:
        return None
    return round((or_high - or_low) / atr, 3)


def compute_pm_vol_curve(rvol: Optional[dict]) -> Optional[str]:
    """Render `compute_rvol_at_time`'s output into the premarket-pace descriptor — today's
    cumulative volume as a multiple of the name's OWN minute-of-day baseline (NOT an absolute
    floor). None when there's no baseline (caller omits the line). Honest: a single-point multiple
    at the clock time, not a slope/shape claim."""
    if not rvol or rvol.get("rvol_at_time") is None:
        return None
    m = int(rvol.get("et_clock_minute") or 0)
    clock = f"{m // 60:02d}:{m % 60:02d}"
    anchor = "premarket" if rvol.get("anchor") == "pm" else "session"
    return (f"{rvol['rvol_at_time']:.1f}x the {anchor} baseline by {clock} ET "
            f"(baseline n={rvol.get('baseline_n')})")


def compute_liquidity_tag(dollar_vol: Optional[float] = None,
                          spread_bps: Optional[float] = None) -> Optional[str]:
    """Compact liquidity/spread tag. `dollar_vol` = today's traded $-volume so far. None when both
    inputs are absent."""
    parts = []
    if dollar_vol is not None:
        parts.append(f"${dollar_vol / 1e6:.0f}M traded")
    if spread_bps is not None:
        parts.append(f"~{spread_bps:.0f}bps spread")
    return ", ".join(parts) or None


def build_tape(*, or_atr: Optional[float] = None, pm_vol_curve: Optional[str] = None,
               liquidity: Optional[str] = None) -> Optional[dict]:
    """Assemble the tape dict the judge prompt renders (keys: `opening_range_atr`, `pm_vol_curve`,
    `liquidity`). Returns None when ALL features are absent — so the judge prompt stays
    byte-identical (behavior-neutral) for names with no tape data. Each present feature is included;
    a missing one is simply omitted (the prompt renders 'None' for an omitted key, which is fine)."""
    tape = {}
    if or_atr is not None:
        tape["opening_range_atr"] = or_atr
    if pm_vol_curve is not None:
        tape["pm_vol_curve"] = pm_vol_curve
    if liquidity is not None:
        tape["liquidity"] = liquidity
    return tape or None
