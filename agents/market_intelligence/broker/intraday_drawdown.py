"""#455 R4 stage-1 — ALERT-ONLY intraday drawdown-crossing check (2026-07-16).

The tiered drawdown breaker evaluates ONCE daily at the 16:12 ET equity
snapshot; nothing portfolio-level watched the live book intraday between the
ORB window and that EOD evaluation. This module closes the VISIBILITY gap
only: it piggybacks on the EXISTING 15-min order-status-reconcile cycle
(scheduler._order_status_reconcile_job — no new polling loop) and computes
the live account's drawdown from the SAME 30d snapshot peak the breaker uses
(`drawdown_breaker.compute_drawdown_state`, read-only: one Alpaca get_account
+ one snapshot-table read).

When the intraday drawdown crosses a WATCH or REDUCE trip threshold DEEPER
than the breaker's persisted state (`mi_safeguard_state` via
`read_breaker_state` — you can't "cross into" a tier the breaker already
holds, and without this comparison a multi-day WATCH drawdown would re-alert
every morning), it sends ONE Telegram alert + writes ONE
`intraday_drawdown_crossing` audit row. The audit row IS the dedup state,
per (tier, ET day) — the `cost_board.run_daily_spend_alarm` pattern. A
deeper alert subsumes shallower tiers for the day (a REDUCE crossing implies
WATCH was crossed; recovering back into the WATCH band later the same day is
not a new crossing).

HARD SCOPE (operator-signed 7/12 as filed — stage 1 ONLY):
- ALERT-ONLY. Zero writes to `mi_safeguard_state`, sizing, entries, exits,
  or the EOD breaker. The ONLY DB write is the audit row.
- LIVE mode only (the paper book is not real-money risk).
- Thresholds/tier vocabulary reused VERBATIM from the breaker
  (`DRAWDOWN_WATCH_TRIP_PCT` / `DRAWDOWN_REDUCE_TRIP_PCT`, `_STATE_DEPTH`).
  No new thresholds, no new authority. BLOCK-depth intraday drawdowns
  surface as a REDUCE-tier crossing (the alert prints the actual dd%); the
  EOD breaker + the 2% daily-loss limit own everything mechanical.
- Mirrors the breaker's fail-open gates: insufficient/stale snapshot
  history → silent (no alert off a sparse or week-old peak).
- `run_intraday_drawdown_check` NEVER raises into the reconcile job:
  everything is wrapped; repeated consecutive failures emit one
  `intraday_drawdown_check_failed` audit row, then the counter resets.

STAGE 2 (applying REDUCE sizing intraday) is an OPERATOR FORK — not built.
SSoT for the breaker itself: docs/setups/safeguards.md.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from agents.market_intelligence.audit_events import (
    INTRADAY_DRAWDOWN_CHECK_FAILED,
    INTRADAY_DRAWDOWN_CROSSING,
)
from agents.market_intelligence.broker.drawdown_breaker import (
    _LEGACY_STATE_TRIPPED,
    _STATE_DEPTH,
    _STATE_REDUCE,
    _STATE_WATCH,
    _today_et,
    compute_drawdown_state,
    read_breaker_state,
)
from agents.market_intelligence.constants import (
    DRAWDOWN_REDUCE_TRIP_PCT,
    DRAWDOWN_WATCH_TRIP_PCT,
    active_account_modes,
)
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

_MODE = "live"  # stage-1 scope: the live book only

# Emit ONE intraday_drawdown_check_failed audit row after this many
# CONSECUTIVE failures (~45 min of the 15-min cadence), then reset. A single
# transient Alpaca hiccup stays log-only; a persistent breakage surfaces.
_FAILURE_AUDIT_THRESHOLD = 3
_consecutive_failures = 0

# Dedup subsumption: which alerted tiers cover a given crossing for the rest
# of the ET day. A REDUCE row covers a later WATCH-band reading (recovery
# direction ≠ a new crossing); a WATCH row does NOT cover a later deepening
# to REDUCE (that's new information and alerts).
_TIER_COVERED_BY = {
    _STATE_WATCH: (_STATE_WATCH, _STATE_REDUCE),
    _STATE_REDUCE: (_STATE_REDUCE,),
}


def _deepest_crossed_tier(drawdown_pct: float) -> str | None:
    """Deepest WATCH/REDUCE trip threshold the drawdown has crossed.

    Same constants + same `<=` trip-side comparison as
    `drawdown_breaker._next_state` — no new thresholds. Stage-1 vocabulary is
    WATCH/REDUCE only (per the task spec); a BLOCK-depth dd still returns
    REDUCE here and the alert body carries the raw dd%.
    """
    if drawdown_pct <= DRAWDOWN_REDUCE_TRIP_PCT:
        return _STATE_REDUCE
    if drawdown_pct <= DRAWDOWN_WATCH_TRIP_PCT:
        return _STATE_WATCH
    return None


def _persisted_depth(state: str) -> int:
    """Depth of the breaker's persisted state (legacy TRIPPED ≙ REDUCE,
    matching `drawdown_breaker._next_state`'s migration mapping)."""
    if state == _LEGACY_STATE_TRIPPED:
        state = _STATE_REDUCE
    return _STATE_DEPTH.get(state, 0)


async def _already_alerted_today(tier: str, today: date) -> bool:
    """Audit-log-as-state dedup: has a crossing row at this tier (or deeper)
    already been written this ET day? Summary carries a machine-matchable
    `tier=<TIER>` token; ≤2 rows/day possible, so filter in Python."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT summary FROM mi_audit_log
            WHERE event_type = $1
              AND (created_at AT TIME ZONE 'America/New_York')::date = $2
            """,
            INTRADAY_DRAWDOWN_CROSSING, today,
        )
    markers = tuple(f"tier={t}" for t in _TIER_COVERED_BY[tier])
    return any(
        marker in (row["summary"] or "")
        for row in rows
        for marker in markers
    )


async def _check_live_drawdown() -> str | None:
    """One evaluation. Returns the tier alerted, or None (silent)."""
    state_obj = await compute_drawdown_state(_MODE)
    if state_obj is None:
        # Alpaca get_account failed inside the compute — surface into the
        # caller's unified failure counter (log-only unless repeated).
        raise RuntimeError("compute_drawdown_state returned None (live account fetch failed)")

    if not state_obj.sufficient_history:
        # Mirror the breaker's min-history / stale-snapshot fail-open: never
        # alert off a sparse or week-old peak.
        return None

    tier = _deepest_crossed_tier(state_obj.drawdown_pct)
    if tier is None:
        return None

    persisted = await read_breaker_state(_MODE)
    if _persisted_depth(persisted) >= _STATE_DEPTH[tier]:
        # The EOD breaker already holds this tier (or deeper) — the operator
        # was alerted at that transition; an intraday reading inside a known
        # tier is not a crossing.
        return None

    today = _today_et()
    if await _already_alerted_today(tier, today):
        return None

    dd_pct = state_obj.drawdown_pct * 100
    summary = (
        f"{_MODE} intraday drawdown crossed tier={tier} "
        f"(dd {dd_pct:.2f}%, peak ${state_obj.peak:,.2f} → "
        f"${state_obj.current:,.2f}, breaker state {persisted})"
    )
    details = {
        "account_mode": _MODE,
        "tier": tier,
        "drawdown_pct": state_obj.drawdown_pct,
        "current": state_obj.current,
        "peak": state_obj.peak,
        "peak_date": state_obj.peak_date.isoformat() if state_obj.peak_date else None,
        "snapshots_count": state_obj.snapshots_count,
        "persisted_breaker_state": persisted,
        "et_date": today.isoformat(),
        "source": "order_status_reconcile_piggyback",
    }
    # Audit row FIRST — it is the dedup state (breaker-transition precedent:
    # audit is the record; a Telegram failure is tolerated + logged).
    await log_audit_event(INTRADAY_DRAWDOWN_CROSSING, summary, json.dumps(details))

    try:
        from agents.market_intelligence.briefing import send_telegram_message
        from shared.telegram_format import b, esc
        tier_icons = {_STATE_WATCH: "🟡", _STATE_REDUCE: "🟠"}
        await send_telegram_message(
            f"{tier_icons.get(tier, 'ℹ️')} {b('INTRADAY DRAWDOWN')} ({esc(_MODE)}): "
            f"crossed {esc(tier)} threshold\n"
            f"Drawdown {dd_pct:.2f}% "
            f"(peak ${state_obj.peak:,.2f} → ${state_obj.current:,.2f})\n"
            f"Alert-only — sizing unchanged; the 16:12 ET breaker evaluation decides state.",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("intraday drawdown crossing telegram failed")

    logger.info(f"intraday drawdown crossing alerted: {summary}")
    return tier


async def run_intraday_drawdown_check() -> str | None:
    """Entry point for the 15-min reconcile piggyback. NEVER raises.

    Returns the tier alerted ('WATCH'/'REDUCE') or None. No-op when the
    deployment has no live mode (`ENABLE_LIVE_MODE=false`).
    """
    global _consecutive_failures
    try:
        if _MODE not in active_account_modes():
            return None
        result = await _check_live_drawdown()
        _consecutive_failures = 0
        return result
    except Exception as e:
        _consecutive_failures += 1
        logger.warning(
            f"intraday drawdown check failed "
            f"({_consecutive_failures} consecutive): {e}",
            exc_info=True,
        )
        if _consecutive_failures >= _FAILURE_AUDIT_THRESHOLD:
            try:
                await log_audit_event(
                    INTRADAY_DRAWDOWN_CHECK_FAILED,
                    f"intraday drawdown check failed {_consecutive_failures}x "
                    f"consecutively (latest: {type(e).__name__})",
                    json.dumps({
                        "account_mode": _MODE,
                        "consecutive_failures": _consecutive_failures,
                        "error": str(e)[:200],
                    }),
                )
            except Exception:
                logger.exception("intraday_drawdown_check_failed audit emit failed")
            _consecutive_failures = 0
        return None
