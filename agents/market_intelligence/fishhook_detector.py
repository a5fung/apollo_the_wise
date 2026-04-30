"""Fishhook V3 — daily EOD state-machine pass.

Reframed (post-Stage-0 explorer): gap-up undercut & reclaim base-rate
harvester, NOT the original "deeper drift = explosive reclaim" thesis
(disproven across 240 threshold permutations — drift floor inverted the
edge). Median R_5d ~1.1, hit rate ~13-19%. High-frequency, low-R.

State machine (single row per anchor in mi_fishhook_anchors):

    pending → promoted → reclaimed → settled
                ↓           ↓
                ↓     invalidated  (close<washout_low post-reclaim, in 5d)
                ↓
            expired_no_promotion (T+10 elapsed, no drift)
            expired_no_reclaim   (T+25 elapsed, no cross)

Daily-bar resolution. Read-only on mi_daily_closes / mi_ep_alerts /
mi_security_types; writes only to mi_fishhook_anchors. Idempotent —
re-running for the same `today` is a no-op (UNIQUE on insert; updates
re-derive from the same forward bars).

This module is shadow-phase telemetry: NO Alpaca orders, NO live trades.
Promotion to paper requires n_settled ≥ 60, median R_5d ≥ 1.0,
hit_rate ≥ 0.13 (gates in mi_strategies.promotion_thresholds).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from agents.market_intelligence.db import (
    get_open_fishhook_anchors,
    get_pool,
    insert_fishhook_anchor,
    log_audit_event,
    update_fishhook_anchor,
)
from agents.market_intelligence.strategies.registry import should_run

logger = logging.getLogger(__name__)

# State-machine windows (locked from Stage-0 explorer findings)
WATCH_START = 3        # T+3 — earliest promotion (rejects same-week wick reversals)
WATCH_END = 10         # T+10 — promotion deadline
RECLAIM_WINDOW = 25    # T+25 — reclaim deadline (absolute, from anchor)
SETTLEMENT_HORIZON = 5 # 5 sessions post-reclaim → settled
GAP_FLOOR = 0.08       # 8% minimum gap (locked)
GAP_CAP = 0.50         # drops 100%+ outliers (BATL 109% / SWMR 29%-class)
TOP_N = 2000           # universe gate (top 2000 by trailing 20d $-volume)

# State machine — single source of truth for state strings.
S_PENDING = "pending"
S_PROMOTED = "promoted"
S_RECLAIMED = "reclaimed"
S_SETTLED = "settled"
S_INVALIDATED = "invalidated"
S_EXPIRED_NO_PROMOTION = "expired_no_promotion"
S_EXPIRED_NO_RECLAIM = "expired_no_reclaim"
OPEN_STATES = frozenset({S_PENDING, S_PROMOTED, S_RECLAIMED})


async def _fetch_today_anchors(today: date) -> list[dict]:
    """Find new gap-up anchors for `today` only.

    Adapted from scripts/fishhook_v3_explorer.py::fetch_anchors but bounded
    to a single anchor_date so the EOD insert touches exactly the rows
    detected today. ADV window walks back 45 calendar days so the
    20-PRECEDING window has data.
    """
    pool = await get_pool()
    dv_start = today - timedelta(days=45)
    sql = """
        WITH dv AS (
            SELECT ticker, trade_date,
                   AVG(close * volume) OVER (
                       PARTITION BY ticker ORDER BY trade_date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) AS adv_dollar_20
            FROM mi_daily_closes
            WHERE close >= 10.00
              AND trade_date BETWEEN $3 AND $1
        ),
        ranked AS (
            SELECT ticker, trade_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY trade_date
                       ORDER BY adv_dollar_20 DESC NULLS LAST
                   ) AS rk
            FROM dv WHERE adv_dollar_20 IS NOT NULL
        ),
        candidates AS (
            SELECT
                d.ticker, d.trade_date AS anchor_date,
                d.open_price AS anchor_open, d.close AS anchor_close,
                LAG(d.close) OVER (
                    PARTITION BY d.ticker ORDER BY d.trade_date
                ) AS prev_close
            FROM mi_daily_closes d
            WHERE d.trade_date BETWEEN ($1::date - INTERVAL '7 days') AND $1
        )
        SELECT
            c.ticker, c.anchor_date, c.anchor_open, c.anchor_close, c.prev_close,
            (c.anchor_open - c.prev_close) / c.prev_close AS gap_pct,
            COALESCE(r.rk <= $4, FALSE) AS in_top2000,
            EXISTS (
                SELECT 1 FROM mi_ep_alerts ea
                WHERE ea.ticker = c.ticker AND ea.alert_date = c.anchor_date
            ) AS in_ep_alerts
        FROM candidates c
        LEFT JOIN ranked r
          ON r.ticker = c.ticker AND r.trade_date = c.anchor_date
        LEFT JOIN mi_security_types st ON st.ticker = c.ticker
        WHERE c.anchor_date = $1
          AND c.prev_close > 0
          AND c.anchor_open IS NOT NULL
          AND c.anchor_close > c.anchor_open
          AND (c.anchor_open - c.prev_close) / c.prev_close BETWEEN $2 AND $5
          AND (st.security_type IN ('CS','ADRC') OR st.ticker IS NULL)
          AND (
              COALESCE(r.rk <= $4, FALSE)
              OR EXISTS (
                  SELECT 1 FROM mi_ep_alerts ea
                  WHERE ea.ticker = c.ticker AND ea.alert_date = c.anchor_date
              )
          )
        ORDER BY c.ticker
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, today, GAP_FLOOR, dv_start, TOP_N, GAP_CAP)
    return [dict(r) for r in rows]


async def _fetch_forward_bars(
    tickers: list[str], from_date: date, to_date: date
) -> dict[str, list[dict]]:
    """Batched OHLC fetch for all open-anchor tickers, keyed ticker → asc bars."""
    if not tickers:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, trade_date, open_price, high_price, low_price, close
            FROM mi_daily_closes
            WHERE ticker = ANY($1) AND trade_date BETWEEN $2 AND $3
            ORDER BY ticker, trade_date
            """,
            tickers, from_date, to_date,
        )
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(dict(r))
    return by_ticker


def _advance_state(anchor: dict, forward: list[dict]) -> dict[str, Any] | None:
    """Compute the state transition (if any) for one open anchor.

    Returns dict of fields to UPDATE, or None if no change. `forward` is
    the list of bars strictly AFTER anchor_date, ascending.

    Idempotent — re-running with the same forward bars produces the same
    `updates`. Only writes a `state` field if it differs from incoming.
    """
    if not forward:
        return None

    anchor_open = float(anchor["anchor_open"])
    incoming_state = anchor["state"]
    today_offset = len(forward)

    # Carry persisted offsets through detection (so re-runs don't reset them)
    promotion_offset = anchor.get("promoted_session_offset")
    reclaim_existing = anchor.get("reclaim_session_offset")
    reclaim_idx = (reclaim_existing - 1) if reclaim_existing else None

    drift_pct_max = None
    for i, bar in enumerate(forward, start=1):
        # Stop scanning past the reclaim window once reclaim is set —
        # nothing after it affects any field below.
        if reclaim_idx is not None and i > RECLAIM_WINDOW and i > WATCH_END:
            break
        close = float(bar["close"]) if bar["close"] is not None else None
        high = float(bar["high_price"]) if bar["high_price"] is not None else None

        if close is not None and WATCH_START <= i <= WATCH_END:
            d = (close - anchor_open) / anchor_open
            if drift_pct_max is None or d < drift_pct_max:
                drift_pct_max = d
            if promotion_offset is None and close < anchor_open:
                promotion_offset = i

        if (
            reclaim_idx is None
            and promotion_offset is not None
            and i >= promotion_offset
            and i <= RECLAIM_WINDOW
            and high is not None
            and high >= anchor_open
        ):
            reclaim_idx = i - 1

    # Washout cap: at reclaim if reached, else min(today_offset, RECLAIM_WINDOW).
    # Caps the stop denominator so it doesn't drift after the trap closes.
    if reclaim_idx is not None:
        cap = reclaim_idx + 1
    else:
        cap = min(today_offset, RECLAIM_WINDOW)
    washout_low = None
    washout_offset = None
    for i, bar in enumerate(forward, start=1):
        if i > cap:
            break
        low = float(bar["low_price"]) if bar["low_price"] is not None else None
        if low is None:
            continue
        if washout_low is None or low < washout_low:
            washout_low = low
            washout_offset = i

    updates: dict[str, Any] = {}
    new_state = incoming_state

    if incoming_state == S_PENDING:
        if promotion_offset is not None:
            new_state = S_PROMOTED
            updates["promoted_session_offset"] = promotion_offset
        elif today_offset > WATCH_END:
            new_state = S_EXPIRED_NO_PROMOTION

    if new_state == S_PROMOTED:
        if reclaim_idx is not None:
            r_bar = forward[reclaim_idx]
            r_open = float(r_bar["open_price"]) if r_bar["open_price"] is not None else None
            r_close = float(r_bar["close"]) if r_bar["close"] is not None else None
            if r_open is not None:
                actual_entry = max(anchor_open, r_open)
                updates.update(
                    reclaim_session_offset=reclaim_idx + 1,
                    reclaim_open=r_open,
                    reclaim_close=r_close,
                    reclaim_open_vs_anchor_pct=(r_open - anchor_open) / anchor_open,
                    actual_entry_price=actual_entry,
                )
                new_state = S_RECLAIMED
            # Malformed reclaim bar — stay promoted, retry next pass
        elif today_offset > RECLAIM_WINDOW:
            new_state = S_EXPIRED_NO_RECLAIM

    if new_state == S_RECLAIMED:
        actual_entry = updates.get("actual_entry_price") or anchor.get("actual_entry_price")
        ws_low = washout_low if washout_low is not None else anchor.get("washout_low")
        reclaim_off_resolved = updates.get("reclaim_session_offset", anchor.get("reclaim_session_offset"))
        if actual_entry is not None and ws_low is not None and reclaim_off_resolved is not None:
            r0 = reclaim_off_resolved - 1
            fwd_window = forward[r0 : r0 + 10]
            n_fwd = len(fwd_window)

            for n in (1, 3, 5, 10):
                if n_fwd < n or actual_entry <= 0:
                    continue
                sub = fwd_window[:n]
                highs = [float(b["high_price"]) for b in sub if b["high_price"] is not None]
                if not highs:
                    continue
                updates[f"fwd_{n}d_high_pct"] = (max(highs) - actual_entry) / actual_entry

            if n_fwd >= 5:
                nth_close = fwd_window[4]["close"]
                if nth_close is not None and actual_entry > 0:
                    updates["fwd_5d_close_pct"] = (float(nth_close) - actual_entry) / actual_entry

                # Invalidation: any close in next 5 post-reclaim < washout_low
                invalidated = False
                for b in fwd_window[:5]:
                    c = b["close"]
                    if c is not None and float(c) < ws_low:
                        invalidated = True
                        break
                updates["invalidated_within_5d"] = invalidated
                updates["n_fwd_sessions_available"] = n_fwd

                fwd_5d_pct = updates.get("fwd_5d_high_pct")
                if fwd_5d_pct is not None:
                    fwd_5d_max_high = fwd_5d_pct * actual_entry + actual_entry
                    risk = actual_entry - float(ws_low)
                    if risk > 0:
                        updates["r_5d"] = (fwd_5d_max_high - actual_entry) / risk

                new_state = S_INVALIDATED if invalidated else S_SETTLED

    if washout_low is not None:
        updates["washout_low"] = washout_low
        updates["washout_session_offset"] = washout_offset
    if drift_pct_max is not None:
        updates["drift_pct_max"] = drift_pct_max

    if new_state != incoming_state:
        updates["state"] = new_state

    return updates if updates else None


async def run_eod_pass(today: date) -> int:
    """Daily EOD pass.

    Returns total rows touched (new pending + state transitions) — used by
    audit_wrap for telemetry. Counter detail is logged + written to
    mi_audit_log.

    Workflow:
      1. Detect today's gap-up anchors → insert as state='pending'.
      2. Walk every open anchor (pending/promoted/reclaimed) forward;
         advance state per the state machine.

    Disabled-strategy short-circuit returns 0 without DB reads.
    """
    if not await should_run("fishhook_v3"):
        logger.info("fishhook_v3 disabled — skipping EOD pass")
        return 0

    counts: dict[str, int] = defaultdict(int)

    # 1. Insert new anchors detected today
    new_anchors = await _fetch_today_anchors(today)
    for a in new_anchors:
        await insert_fishhook_anchor({
            "ticker": a["ticker"],
            "anchor_date": a["anchor_date"],
            "prev_close": float(a["prev_close"]),
            "anchor_open": float(a["anchor_open"]),
            "anchor_close": float(a["anchor_close"]),
            "gap_pct": float(a["gap_pct"]),
            "in_top2000": bool(a["in_top2000"]),
            "in_ep_alerts": bool(a["in_ep_alerts"]),
        })
        counts["new_pending"] += 1

    # 2. Walk forward all open anchors
    open_anchors = await get_open_fishhook_anchors(today)
    if open_anchors:
        tickers = sorted({a["ticker"] for a in open_anchors})
        earliest = min(a["anchor_date"] for a in open_anchors)
        bars_by_ticker = await _fetch_forward_bars(
            tickers, earliest + timedelta(days=1), today
        )
        for a in open_anchors:
            all_bars = bars_by_ticker.get(a["ticker"], [])
            forward = [b for b in all_bars if b["trade_date"] > a["anchor_date"]]
            updates = _advance_state(a, forward)
            if not updates:
                continue
            new_state = updates.get("state")
            if new_state and new_state != a["state"]:
                counts[f"transition_to_{new_state}"] += 1
            await update_fishhook_anchor(a["id"], **updates)

    summary = dict(counts)
    logger.info(f"Fishhook EOD pass {today}: {summary}")
    if summary:
        parts = ", ".join(f"{k}={v}" for k, v in summary.items())
        await log_audit_event(
            "fishhook_eod_pass",
            f"{today.isoformat()}: {parts}",
        )
    return sum(counts.values())
