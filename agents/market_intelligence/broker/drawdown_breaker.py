"""Drawdown-based circuit breaker (#39, shadow shipped 2026-05-08).

Replaces the count-based `CIRCUIT_BREAKER_CONSEC_LOSSES` check on flip day
(env: `DRAWDOWN_BREAKER_PHASE=active`). Methodology-aware: trips on equity
drawdown from recent peak — Alpaca `account.equity` already includes
unrealized P&L, so open winners' MTM lifts equity and prevents the
self-perpetuating-streak / methodology-blind problems of the count-based
check.

Architecture (per plan `~/.claude/plans/let-s-go-into-plan-glittery-graham.md`):
- Daily snapshot at 16:10 ET (after eod_cleanup) writes one row to
  `mi_account_equity_snapshots` per (snapshot_date, account_mode).
- Same job calls `recompute_drawdown_state(mode)` which evaluates the
  state machine and persists to `mi_safeguard_state`.
- State transitions emit a single audit event each (`drawdown_breaker_tripped`
  / `drawdown_breaker_released` / `drawdown_check_unavailable`).
- `_check_safeguards()` (active phase only, env-gated) does a cheap PK
  lookup via `read_breaker_state` — zero per-call compute, zero audit
  emission.

Hysteresis is state-aware (advisor-flagged): when state='OK', only the
trip threshold is checked; when state='TRIPPED', only the release
threshold. Eliminates the `-5.1% → -4.9% → -5.1%` flap-and-spam scenario
that a stateless threshold-comparator would produce.

Stale-data guard (advisor-flagged): if the most recent snapshot is older
than 48 hours, `sufficient_history=False` and the breaker fails OPEN
(allows trading) regardless of count. Protects against silent cron
failures locking the system on a week-old peak.

SSoT: `docs/setups/safeguards.md`. Promotion plan: ≥14d post-live-cutover
shadow telemetry, then env flip + replace count-based block in
`live_tracker._check_safeguards`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.constants import (
    DRAWDOWN_PEAK_WINDOW_DAYS,
    DRAWDOWN_RELEASE_PCT,
    DRAWDOWN_TRIP_PCT,
    MIN_SNAPSHOT_HISTORY_DAYS,
    current_account_mode,
)
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

_SAFEGUARD_NAME = "drawdown_breaker"
_STATE_OK = "OK"
_STATE_TRIPPED = "TRIPPED"
_STALE_DATA_HOURS = 48


@dataclass
class DrawdownState:
    current: float
    peak: float
    peak_date: Optional[date]
    drawdown_pct: float
    snapshots_count: int
    most_recent_snapshot_date: Optional[date]
    sufficient_history: bool


# ── Snapshot ────────────────────────────────────────────────────────────────


async def snapshot_account_equity(
    source: str = "eod",
    account_mode: str | None = None,
) -> Optional[dict]:
    """Fetch Alpaca equity and persist a row for today's ET date.

    Idempotent via UNIQUE (snapshot_date, account_mode). On Alpaca API
    failure: emits `drawdown_check_unavailable` audit event and returns None
    (caller skips the recompute step). Never raises into caller.

    account_mode: 'paper' | 'live'. None falls back to current_account_mode()
    for legacy callers; dual-account scheduler iterates and passes explicit
    mode per call.
    """
    mode = account_mode or current_account_mode()
    today_et = _today_et()

    try:
        account = await alpaca.get_account(account_mode=mode)
    except Exception as e:
        logger.warning(f"snapshot_account_equity: Alpaca get_account failed: {e}")
        await log_audit_event(
            "drawdown_check_unavailable",
            f"snapshot failed for {mode}: {type(e).__name__}",
            json.dumps({
                "stage": "snapshot",
                "account_mode": mode,
                "snapshot_date": today_et.isoformat(),
                "error": str(e)[:200],
            }),
        )
        return None

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mi_account_equity_snapshots
                (snapshot_date, account_mode, equity, cash, portfolio_value, source)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (snapshot_date, account_mode) DO NOTHING
            RETURNING id, snapshot_date, account_mode, equity, cash, portfolio_value, source
            """,
            today_et,
            mode,
            float(account["equity"]),
            float(account.get("cash") or 0.0),
            float(account.get("portfolio_value") or 0.0),
            source,
        )

    if row is None:
        # Already snapshotted today — return the existing row for callers.
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT id, snapshot_date, account_mode, equity, cash, portfolio_value, source
                FROM mi_account_equity_snapshots
                WHERE snapshot_date = $1 AND account_mode = $2
                """,
                today_et, mode,
            )
        return dict(existing) if existing else None

    logger.info(
        f"Equity snapshot: {mode} {today_et} equity=${float(row['equity']):,.2f} source={source}"
    )
    return dict(row)


# ── Compute drawdown state (read-only) ──────────────────────────────────────


async def compute_drawdown_state(mode: str) -> Optional[DrawdownState]:
    """Read current Alpaca equity + last 30d snapshots, return drawdown state.

    Returns None if the Alpaca account fetch fails (caller emits an audit
    event; recompute should not transition state without current equity).
    """
    today_et = _today_et()
    cutoff = today_et - timedelta(days=DRAWDOWN_PEAK_WINDOW_DAYS)

    try:
        account = await alpaca.get_account(account_mode=mode)
        current = float(account["equity"])
    except Exception as e:
        logger.warning(f"compute_drawdown_state: Alpaca get_account failed: {e}")
        return None

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT snapshot_date, equity
            FROM mi_account_equity_snapshots
            WHERE account_mode = $1 AND snapshot_date >= $2
            ORDER BY snapshot_date DESC
            """,
            mode, cutoff,
        )

    if not rows:
        # No history at all — fail open.
        return DrawdownState(
            current=current,
            peak=current,
            peak_date=None,
            drawdown_pct=0.0,
            snapshots_count=0,
            most_recent_snapshot_date=None,
            sufficient_history=False,
        )

    peak_row = max(rows, key=lambda r: float(r["equity"]))
    peak = float(peak_row["equity"])
    peak_date = peak_row["snapshot_date"]
    most_recent = rows[0]["snapshot_date"]  # ORDER BY DESC

    drawdown_pct = (current - peak) / peak if peak > 0 else 0.0

    # Stale-data fail-open: even with 30 rows, if the most-recent is >48h old,
    # the snapshot cron likely failed silently — treat as insufficient.
    snapshots_count = len(rows)
    days_since_recent = (today_et - most_recent).days
    sufficient_history = (
        snapshots_count >= MIN_SNAPSHOT_HISTORY_DAYS
        and days_since_recent <= 2  # 48h in calendar-day terms
    )

    return DrawdownState(
        current=current,
        peak=peak,
        peak_date=peak_date,
        drawdown_pct=drawdown_pct,
        snapshots_count=snapshots_count,
        most_recent_snapshot_date=most_recent,
        sufficient_history=sufficient_history,
    )


# ── State machine driver ────────────────────────────────────────────────────


async def recompute_drawdown_state(mode: str) -> tuple[str, str, dict]:
    """Evaluate state machine and persist. Emit audit event on transitions.

    Returns (prev_state, new_state, details). Hysteresis is state-aware:
    OK→TRIPPED only when drawdown ≤ TRIP threshold; TRIPPED→OK only when
    drawdown ≥ RELEASE threshold. Eliminates flap-and-spam.

    Active-phase only blocks on `state='TRIPPED'` AND `sufficient_history`
    (the latter check happens in `read_breaker_state`'s caller pattern; this
    function transitions state regardless because we want shadow calibration
    data even when history is sparse).
    """
    state_obj = await compute_drawdown_state(mode)
    if state_obj is None:
        await log_audit_event(
            "drawdown_check_unavailable",
            f"recompute failed for {mode}: get_account error during compute",
            json.dumps({"stage": "compute", "account_mode": mode}),
        )
        return _read_state_or_default(mode), _read_state_or_default(mode), {}

    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT state FROM mi_safeguard_state
            WHERE safeguard = $1 AND account_mode = $2
            """,
            _SAFEGUARD_NAME, mode,
        )
    prev_state = existing["state"] if existing else _STATE_OK

    # State-aware threshold check (hysteresis):
    #   OK → TRIPPED only when drawdown ≤ TRIP threshold
    #   TRIPPED → OK only when drawdown ≥ RELEASE threshold
    new_state = prev_state
    if prev_state == _STATE_OK:
        if state_obj.drawdown_pct <= DRAWDOWN_TRIP_PCT:
            new_state = _STATE_TRIPPED
    else:  # TRIPPED
        if state_obj.drawdown_pct >= DRAWDOWN_RELEASE_PCT:
            new_state = _STATE_OK

    transitioned = new_state != prev_state
    now = datetime.now(timezone.utc)

    # `now` for last_transition_at is fine on both INSERT (first observation
    # = new "transition" into starting state) and UPDATE (preserved by SQL
    # CASE when state didn't change).
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO mi_safeguard_state
                (safeguard, account_mode, state, last_transition_at,
                 last_evaluation_at, last_drawdown_pct, last_peak, last_peak_date,
                 updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (safeguard, account_mode) DO UPDATE SET
                state              = EXCLUDED.state,
                last_transition_at = CASE
                    WHEN mi_safeguard_state.state IS DISTINCT FROM EXCLUDED.state
                        THEN EXCLUDED.last_transition_at
                    ELSE mi_safeguard_state.last_transition_at
                END,
                last_evaluation_at = EXCLUDED.last_evaluation_at,
                last_drawdown_pct  = EXCLUDED.last_drawdown_pct,
                last_peak          = EXCLUDED.last_peak,
                last_peak_date     = EXCLUDED.last_peak_date,
                updated_at         = EXCLUDED.updated_at
            """,
            _SAFEGUARD_NAME,
            mode,
            new_state,
            now,  # last_transition_at — preserved by SQL CASE if no transition
            now,  # last_evaluation_at
            state_obj.drawdown_pct,
            state_obj.peak,
            state_obj.peak_date,
            now,  # updated_at
        )

    details = {
        "account_mode": mode,
        "current": state_obj.current,
        "peak": state_obj.peak,
        "peak_date": state_obj.peak_date.isoformat() if state_obj.peak_date else None,
        "drawdown_pct": state_obj.drawdown_pct,
        "snapshots_count": state_obj.snapshots_count,
        "most_recent_snapshot_date": (
            state_obj.most_recent_snapshot_date.isoformat()
            if state_obj.most_recent_snapshot_date else None
        ),
        "sufficient_history": state_obj.sufficient_history,
        "prev_state": prev_state,
        "new_state": new_state,
    }

    if transitioned:
        if new_state == _STATE_TRIPPED:
            await log_audit_event(
                "drawdown_breaker_tripped",
                f"{mode}: drawdown {state_obj.drawdown_pct*100:.2f}% "
                f"(peak ${state_obj.peak:,.2f} → current ${state_obj.current:,.2f})",
                json.dumps(details),
            )
        else:
            await log_audit_event(
                "drawdown_breaker_released",
                f"{mode}: drawdown recovered to {state_obj.drawdown_pct*100:.2f}% "
                f"(peak ${state_obj.peak:,.2f} → current ${state_obj.current:,.2f})",
                json.dumps(details),
            )
        logger.info(
            f"Drawdown breaker transition {mode}: {prev_state} → {new_state} "
            f"(dd={state_obj.drawdown_pct*100:.2f}%)"
        )

    return prev_state, new_state, details


# ── State read (called from _check_safeguards in active phase) ──────────────


async def read_breaker_state(mode: str) -> str:
    """Cheap PK lookup. Returns 'OK' if no row exists (fail-open default).

    Used by _check_safeguards() in active phase. Zero compute, single index hit.
    Fail-safe: any DB error returns 'OK' (don't block on infra failure).
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT state FROM mi_safeguard_state
                WHERE safeguard = $1 AND account_mode = $2
                """,
                _SAFEGUARD_NAME, mode,
            )
        return row["state"] if row else _STATE_OK
    except Exception as e:
        logger.warning(f"read_breaker_state failed for {mode}: {e}")
        return _STATE_OK


# ── Internals ───────────────────────────────────────────────────────────────


def _today_et() -> date:
    """Today's date in ET. Uses zoneinfo (matches CLAUDE.md ET-everywhere rule)."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).date()


def _read_state_or_default(mode: str) -> str:
    # Sync helper for the unavailable-data path. Synchronous wrapper would
    # require pool acquisition; for this rare error path we just return OK
    # (the audit event already records the failure). Active-phase reads use
    # `read_breaker_state` which IS async and does the PK lookup.
    return _STATE_OK
