"""Peak-lock (giveback) SHADOW on the LIVE book — ADR 0023 F1 forward measurement.

Operator picked (7/9) the peak-lock direction (arm +6% / floor 60%) but chose to VALIDATE it in
SHADOW rather than flip live — and paper is dormant, so the shadow rides the LIVE MAGNA53 book:
when a live trade closes, replay its daily-close path through the exit engine WITH vs WITHOUT the
giveback and log the MARGINAL (`giveback_pnl − baseline_pnl`). NOTHING changes the live exit — the
real position exits exactly as it does today; we only OBSERVE the counterfactual. THE LINE holds.

The marginal cancels the two replay approximations (running_closes carries closes not intraday
lows → l=c; dates reconstructed as alert_date+i) because BOTH arms share them — the #306
marginal-model logic. Accrues at MAGNA53's real rate (only round-trip winners produce signal), so
it's slow by design; the offline sweep (306_step2_sweep) stays the primary evidence, this adds
forward confirmation until there's enough to inform a live-flip decision (CHANGE_PROCESS + sign-off).
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from agents.market_intelligence.broker.exit_logic import iter_exit_ladder, seed_exit_state  # exec-boundary-ok: exit_logic is PURE exit-ladder math (no Alpaca client, no trade-state I/O) — the ADR 0023 F1 giveback SHADOW reuses the tested ladder for the counterfactual rather than re-implementing it (same F11 pattern as flag_detector's #396 mgmt shadow); pure compute, no live execution
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# The operator-picked parameterization (7/9 F1): arm on +6% peak gain, lock 60% of the peak.
GIVEBACK_SHADOW_ARM = 0.06
GIVEBACK_SHADOW_FLOOR = 0.60


def compute_giveback_shadow(
    trade: dict, *, arm: float = GIVEBACK_SHADOW_ARM, floor_frac: float = GIVEBACK_SHADOW_FLOOR,
) -> dict | None:
    """Replay one closed trade's daily-close path through the exit engine WITH and WITHOUT the
    peak-lock, returning the giveback's marginal effect. None when there's no measurable multi-day
    path (same-day / no stored closes → the giveback can't engage anyway)."""
    entry = float(trade.get("entry_price") or 0)
    shares = float(trade.get("entry_shares") or 0)
    hard_stop = trade.get("hard_stop")
    closes = [float(c) for c in (trade.get("running_closes") or [])]
    alert_date = trade.get("alert_date")
    if isinstance(alert_date, str):
        alert_date = date.fromisoformat(alert_date)
    if not entry or shares <= 0 or len(closes) < 2 or alert_date is None:
        return None

    def _replay(with_giveback: bool):
        # #445: seed + carry live in the ONE driver (exit_logic.iter_exit_ladder);
        # this consumer keeps only its fold (l=c bars, marginal-cancel dates).
        state = seed_exit_state(alert_date=alert_date, entry_price=entry,
                                hard_stop=hard_stop, remaining_shares=shares)
        bars = ((alert_date + timedelta(days=i + 1), {"l": c, "c": c})
                for i, c in enumerate(closes))  # l=c and reconstructed dates cancel in the marginal
        for i, day, step in iter_exit_ladder(
                state, bars,
                giveback_arm_gain=arm if with_giveback else None,
                giveback_floor_frac=floor_frac if with_giveback else None):
            if step.closed:
                return step.new_total_pnl, i, step.close_reason
        remaining = state["remaining_shares"]
        pnl = sum(e.get("pnl", 0) for e in state["exits"]) + (closes[-1] - entry) * remaining
        return pnl, len(closes) - 1, "held_to_end"

    base_pnl, base_idx, _ = _replay(False)
    gb_pnl, gb_idx, gb_reason = _replay(True)
    return {
        "actual_pnl": float(trade.get("total_pnl")) if trade.get("total_pnl") is not None else None,
        "baseline_pnl": round(base_pnl, 2),
        "giveback_pnl": round(gb_pnl, 2),
        "marginal": round(gb_pnl - base_pnl, 2),
        "giveback_early": gb_idx < base_idx,   # the lock exited before the baseline would
        "gb_exit_reason": gb_reason,
        "arm": arm, "floor_frac": floor_frac,
    }


async def run_giveback_shadow(today: date, *, signal_type: str = "magna53",
                              account_mode: str = "live") -> int:
    """Log the giveback shadow for LIVE trades that closed `today` and aren't shadowed yet.
    Pure compute + DB/audit — no broker calls, no live-exit change. Returns the count logged.
    The mi_giveback_shadow table is seeded by db.initialize_schema at boot (schema SSoT)."""
    pool = await get_pool()
    logged = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.id, t.ticker, t.alert_date, t.account_mode, t.entry_price, t.entry_shares,
                   t.hard_stop, t.total_pnl, t.running_closes
            FROM mi_live_trades t
            WHERE t.status = 'closed' AND t.signal_type = $1 AND t.account_mode = $2
              AND (t.closed_at AT TIME ZONE 'America/New_York')::date = $3
              AND NOT EXISTS (SELECT 1 FROM mi_giveback_shadow g WHERE g.trade_id = t.id)
        """, signal_type, account_mode, today)
        for r in rows:
            trade = dict(r)
            rc = trade.get("running_closes")
            trade["running_closes"] = json.loads(rc) if isinstance(rc, str) else (rc or [])
            shadow = compute_giveback_shadow(trade)
            if shadow is None:
                continue
            await conn.execute("""
                INSERT INTO mi_giveback_shadow
                    (trade_id, ticker, alert_date, account_mode, actual_pnl, baseline_pnl,
                     giveback_pnl, marginal, giveback_early, gb_exit_reason, arm, floor_frac)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (trade_id) DO NOTHING
            """, r["id"], r["ticker"], r["alert_date"], r["account_mode"],
                shadow["actual_pnl"], shadow["baseline_pnl"], shadow["giveback_pnl"],
                shadow["marginal"], shadow["giveback_early"], shadow["gb_exit_reason"],
                shadow["arm"], shadow["floor_frac"])
            logged += 1
    if logged:
        try:
            await log_audit_event(
                "giveback_shadow_logged",
                summary=f"logged {logged} live giveback-shadow row(s) for {today}",
                detail=f"arm={GIVEBACK_SHADOW_ARM} floor={GIVEBACK_SHADOW_FLOOR}")
        except Exception as _e:  # loud-ok: telemetry-of-telemetry; the shadow rows are already durable
            logger.warning("giveback_shadow audit emit failed (non-fatal): %s", _e)
    return logged
