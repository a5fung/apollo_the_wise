"""D-1 UNIVERSE FLOOR SHADOW (#606, 2026-08-31).

WHY. `docs/analysis/606_d1_floor_2026-08-31.md`: the live D-1 universe floor
(prior close >= $5 AND prior-day volume >= 50,000 shares — `ep_detector.py`'s
`MIN_PREV_CLOSE` / `MIN_PREV_DAY_VOLUME`) is the pipeline's single largest
exclusion class by an order of magnitude, and 5 trading days of evidence found
its SHAPE weaker than the alternative: at equal recall, a $1M D-1
dollar-volume floor admits 43% fewer noise rows than any price-only cut of
equal catch, because price x volume is what liquidity actually IS — a $3
stock trading 5M shares is more liquid than a $50 stock trading 3k shares, a
distinction the two-part price+share-count gate structurally cannot express.
5 days is not enough to change a live detection criterion (THE LINE — the
universe floor is a detection criterion; changing it is the operator's SOLE
authority), so this records the comparison beside the acting floor at full
scan speed instead of waiting on it passively.

WHAT IT RECORDS. One row per (scan_date, ticker) for every REAL candidate —
every ticker whose gap clears the day's Pass-1 gap floor — on BOTH sides of
the D-1 floor (admitted AND rejected). The comparison must run both ways:
what a dollar-volume floor would newly ADMIT (recall the two-part floor is
currently costing) and what it would newly REJECT among names the two-part
floor lets through today (the cost a swap would add) — judging a floor swap
on only one direction is not evidence, it's half of it.

⚠ RAW INPUTS ONLY, NEVER A VERDICT: prior close, prior-day share volume, and
prior-day dollar volume (price x volume — an invariant fact of that day's
data, not a threshold-dependent computation) — plus which of the two
ALREADY-ACTING floors the ticker failed, a plain fact about the LIVE rule as
it stood at write time, not a hypothetical one. What is explicitly NOT
stored is any "would a $500k / $1M / $2M / ... floor admit this" flag:
thresholds are a function of today's rule set, and the moment a level is
swept, a stored verdict against it goes stale and a replay silently scores
the old level (the #583 stale-derived-value class; `catalyst_tier_shadow` /
`ep_shortlist_shadow` set this convention — raw inputs "so any variant can be
replayed against outcomes later without new data"). Storing raw inputs means
ANY level can be swept later from these same rows, with no new data.
`acting_price_floor` / `acting_volume_floor` stamp the LIVE constants at
write time so a future reader never has to infer them from a date.

⚠ WHY THREE OBSERVATION SLOTS (first / at_open / last), NOT ONE FROZEN READ.
The scan ticks repeatedly through the morning, and the D-1 floor is checked
starting pre-market — a ticker's FIRST tick is often a pre-market print that
fades before 9:30 and never becomes a real setup (`mi_ep_missed_outcomes` was
60% corrupted by exactly this, #595; the 606 card's own population filters on
`setup_at_open`, the gap AT THE OPEN, for the same reason). Freezing the
first-ever read (e.g. via ON CONFLICT DO NOTHING) would silently re-introduce
that class into this table. Instead each row tracks:
  - `gap_pct_first` / `minutes_since_open_first` — whatever the very first
    tick saw (often pre-market; NULL minutes = pre-market by construction).
  - `gap_pct_at_open` / `minutes_since_open_at_open` — the FIRST tick where
    `minutes_since_open IS NOT NULL`, set once and never overwritten — the
    reading comparable to the 606 card's `setup_at_open` population.
  - `gap_pct_last` / `minutes_since_open_last` — the most recent tick's read,
    updated every tick (`ON CONFLICT ... DO UPDATE`), so a reader can also see
    how the gap moved through the morning.
`prev_close` / `prev_day_volume` / `prev_day_dollar_volume` /
`failed_price_floor` / `failed_volume_floor` are static for the trading day —
written once, never touched by later ticks.

$0 AT RUNTIME — pure arithmetic on numbers the scan already holds (prev_close,
prev_day_volume, gap_pct); no LLM, no API call, no new I/O beyond the one
batched insert per tick. The recorder is fail-open (never raises) and is read
by NO grading / entry / sizing / ordering / safeguard path — comparison
telemetry only, same contract as `ep_shortlist_shadow.py` /
`catalyst_tier_shadow.py`.

⚖ THE LINE: this module makes no decision and flips nothing. The universe
floor is a detection criterion; nothing about live admission changes here —
it is a passive recorder beside it.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# The actual INSERT lives in db.py (the single source of truth for every DB
# query) — this module owns the row SHAPE and is the table's single writer.
from agents.market_intelligence.db import insert_universe_floor_shadow_rows  # noqa: E402


def build_universe_floor_shadow_row(
    ticker: str,
    prev_close: "float | None",
    prev_day_volume: "float | None",
    gap_pct: "float | None",
    acting_price_floor: float,
    acting_volume_floor: float,
    scan_date: date,
    minutes_since_open: "int | None" = None,
    seen_et: "datetime | None" = None,
) -> dict[str, Any]:
    """Pure — no I/O. RAW INPUTS for one real-candidate ticker at THIS tick's
    read of the D-1 universe-floor gate, on whichever side it lands. Reconciling
    this single-tick reading into the row's first/at_open/last observation
    slots is the writer's job (db.py's ON CONFLICT clause) — this function
    hands over exactly what the current tick saw, nothing more.

    `failed_price_floor` / `failed_volume_floor` are two INDEPENDENT checks
    (a ticker can fail one, the other, both, or neither) — computed here
    directly against the raw values rather than re-derived from
    `_universe_floor_skip`'s reason string, which reports only the FIRST
    floor it hit (price checked before volume) and would silently under-count
    a name that fails both.
    """
    dollar_volume = (
        float(prev_close) * float(prev_day_volume)
        if prev_close is not None and prev_day_volume is not None
        else None
    )
    return {
        "scan_date": scan_date,
        "ticker": ticker,
        "seen_et": seen_et,
        "gap_pct": gap_pct,
        "minutes_since_open": minutes_since_open,
        "prev_close": prev_close,
        "prev_day_volume": prev_day_volume,
        "prev_day_dollar_volume": dollar_volume,
        "failed_price_floor": (
            prev_close is None or prev_close < acting_price_floor
        ),
        "failed_volume_floor": (
            prev_day_volume is None or prev_day_volume < acting_volume_floor
        ),
        "acting_price_floor": acting_price_floor,
        "acting_volume_floor": acting_volume_floor,
    }


async def record_universe_floor_shadow(rows: list[dict[str, Any]]) -> int:
    """Batch writer — called fire-and-forget after the scan loop (the
    catalyst_tier_shadow / ep_shortlist_shadow contract: never raises, never
    blocks the scan; one batched insert per tick, not one round trip per
    ticker — the floor's rejects alone run ~700/week). Thin delegation to
    db.py, which owns the SQL; this module is the table's single writer."""
    if not rows:
        return 0
    return await insert_universe_floor_shadow_rows(rows)
