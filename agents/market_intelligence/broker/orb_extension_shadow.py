"""ORB-window-extension shadow telemetry.

Records counterfactual lifecycle for trades cancelled at 10:00 ET (the
ORB unfilled-entry cleanup). For each cancellation we simulate "what if
the cutoff had been C ET instead?" across multiple cutoffs, and persist
the per-cutoff outcome so that — once enough cancellations accumulate
(~N=20 distinct trade_ids) — we can decide whether to extend the live
ORB cutoff with data instead of single-anecdote evidence.

Two entry points:
- record_shadow_for_cancellation(...) — fires from cancel_unfilled_entries
  when reason indicates the 10:00 ET ORB-window path (NOT the 4:05 PM
  EOD path). Day-1 minute bars fetched once and reused across cutoffs.
- settle_open_shadows(...) — appended to nightly_data_pull. Re-evaluates
  every still_open row via apply_daily_exit_step (production exit logic).

The simulation uses stop_limit_buy_price(stop) as the fill threshold so
fill realism matches the live broker's stop-limit BUY semantics — high
must reach the LIMIT price, not just the stop trigger.
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime as _dt, timedelta as _td
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker.exit_logic import iter_exit_ladder
from agents.market_intelligence.broker.order_manager import stop_limit_buy_price
from agents.market_intelligence.collector import (
    et_today, get_index_history, get_minute_bars,
)
from agents.market_intelligence.db import (
    get_open_orb_extension_shadows,
    insert_orb_extension_shadow_row,
    update_orb_extension_shadow_state,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
MAX_ENTRY_ATTEMPTS = 2  # mirrors broker.order_manager.MAX_ENTRY_ATTEMPTS
CUTOFF_MINUTES = [600, 660, 720, 780, 840, 960]  # 10:00, 11:00, 12:00, 13:00, 14:00, 16:00


def _hhmm(t: _dt) -> int:
    return t.hour * 100 + t.minute


def _cutoff_dt(d: _date, cutoff_min: int) -> _dt:
    h, m = divmod(cutoff_min, 60)
    return _dt.combine(d, _dt.min.time(), tzinfo=_ET).replace(hour=h, minute=m)


async def _fetch_rth_minute(ticker: str, d: _date) -> list[tuple]:
    bars = await get_minute_bars(ticker, d.isoformat(), d.isoformat())
    out = []
    for b in bars:
        t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
        if 931 <= _hhmm(t) <= 1600:
            out.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    return sorted(out)


def _simulate_day1(
    rth: list[tuple],
    proposed_at: _dt,
    cutoff_t: _dt,
    limit: float,
    stop: float,
    shares: int,
) -> dict:
    """Run Day-1 entry simulation against pre-fetched 1-min bars.

    Fill threshold uses stop_limit_buy_price(stop) so the sim matches the
    live broker's stop-limit BUY semantics (high must reach the LIMIT
    price, not the stop trigger).

    Returns dict with: would_fill, fill_at, fill_price, entry_attempts,
    final_status (one of 'no_cross_by_cutoff', 'max_attempts_stopped',
    'open_eod'), exits (list of intraday stop-out legs), day1_close.
    """
    fill_limit = stop_limit_buy_price(stop)
    cur_t = proposed_at
    attempts = 0
    exits: list[dict] = []
    fill_t = None
    fill_price = None

    while attempts < MAX_ENTRY_ATTEMPTS:
        cross = next(
            ((t, h) for t, _o, h, _l, _c in rth
             if cur_t <= t <= cutoff_t and h >= fill_limit),
            None,
        )
        if not cross:
            break
        attempts += 1
        fill_t, fill_price = cross[0], fill_limit
        cur_fill_t = cross[0]
        # Intraday stop-out scan from fill to EOD (no cutoff for exits)
        stop_hit = next(
            ((t, l) for t, _o, _h, l, _c in rth
             if t > cur_fill_t and l <= stop),
            None,
        )
        if not stop_hit:
            return {
                "would_fill": True,
                "fill_at": fill_t,
                "fill_price": fill_price,
                "entry_attempts": attempts,
                "final_status": "open_eod",
                "exits": exits,
                "day1_close": rth[-1][4] if rth else None,
            }
        leg_pnl = (stop - fill_limit) * shares
        exits.append({
            "day": 1,
            "time": stop_hit[0].isoformat(),
            "price": stop,
            "shares": shares,
            "reason": "intraday_stop",
            "pnl": leg_pnl,
        })
        cur_t = stop_hit[0]

    if fill_t is None:
        return {
            "would_fill": False,
            "entry_attempts": 0,
            "final_status": "no_cross_by_cutoff",
            "exits": [],
            "day1_close": rth[-1][4] if rth else None,
        }
    # fill_t set but loop exited → max_attempts_stopped
    return {
        "would_fill": True,
        "fill_at": fill_t,
        "fill_price": fill_price,
        "entry_attempts": attempts,
        "final_status": "max_attempts_stopped",
        "exits": exits,
        "day1_close": rth[-1][4] if rth else None,
    }


async def record_shadow_for_cancellation(
    trade_id: int,
    ticker: str,
    alert_date: _date,
    proposed_at: _dt,
    limit_price: float,
    stop_price: float,
    shares: int,
    cancelled_at: _dt,
) -> None:
    """Fire-and-forget. Called from cancel_unfilled_entries on the 10:00 ET path.

    Fetches Day-1 RTH bars ONCE, then evaluates each cutoff against the
    cached bars (6 cutoffs × 1 fetch, not 6). For cutoffs that produce an
    open EOD position, persists state so the nightly settlement job can
    resume via apply_daily_exit_step.
    """
    try:
        rth = await _fetch_rth_minute(ticker, alert_date)
    except Exception as e:
        logger.warning(f"orb_ext_shadow {ticker} {alert_date}: bar fetch failed: {e}")
        return

    if not rth:
        logger.info(f"orb_ext_shadow {ticker} {alert_date}: no Day-1 RTH bars; skipping")
        return

    proposed_et = proposed_at.astimezone(_ET)
    for cutoff_min in CUTOFF_MINUTES:
        cutoff_t = _cutoff_dt(alert_date, cutoff_min)
        if cutoff_t < proposed_et:
            continue  # cutoff before order would even exist

        sim = _simulate_day1(
            rth, proposed_et, cutoff_t,
            limit=float(limit_price), stop=float(stop_price), shares=int(shares),
        )

        realised = sum(e.get("pnl", 0) for e in sim["exits"])

        if not sim["would_fill"]:
            row = {
                "trade_id": trade_id, "ticker": ticker,
                "alert_date": alert_date, "cutoff_minute": cutoff_min,
                "limit_price": limit_price, "stop_price": stop_price,
                "shares": shares, "cancelled_at": cancelled_at,
                "would_fill": False, "fill_at": None, "fill_price": None,
                "entry_attempts": 0,
                "state": {"exits": [], "running_closes": []},
                "final_status": "no_cross_by_cutoff",
                "closed_at": None, "total_pnl": 0.0,
                "hold_days": 0, "last_close": None,
                "last_evaluated_date": alert_date,
            }
        elif sim["final_status"] == "max_attempts_stopped":
            row = {
                "trade_id": trade_id, "ticker": ticker,
                "alert_date": alert_date, "cutoff_minute": cutoff_min,
                "limit_price": limit_price, "stop_price": stop_price,
                "shares": shares, "cancelled_at": cancelled_at,
                "would_fill": True, "fill_at": sim["fill_at"],
                "fill_price": sim["fill_price"],
                "entry_attempts": sim["entry_attempts"],
                "state": {"exits": sim["exits"], "running_closes": []},
                "final_status": "max_attempts_stopped",
                "closed_at": alert_date,
                "total_pnl": realised, "hold_days": 0,
                "last_close": sim["day1_close"],
                "last_evaluated_date": alert_date,
            }
        else:
            # open_eod — persist state for nightly resume
            state = {
                "alert_date": alert_date.isoformat(),
                "remaining_shares": shares,
                "entry_price": float(sim["fill_price"]),
                "hard_stop": float(stop_price),
                "partial_taken": False,
                "breakeven_active": False,
                "exits": sim["exits"],
                "running_closes": [sim["day1_close"]] if sim["day1_close"] is not None else [],
            }
            unrealised = (sim["day1_close"] - sim["fill_price"]) * shares if sim["day1_close"] else 0.0
            row = {
                "trade_id": trade_id, "ticker": ticker,
                "alert_date": alert_date, "cutoff_minute": cutoff_min,
                "limit_price": limit_price, "stop_price": stop_price,
                "shares": shares, "cancelled_at": cancelled_at,
                "would_fill": True, "fill_at": sim["fill_at"],
                "fill_price": sim["fill_price"],
                "entry_attempts": sim["entry_attempts"],
                "state": state,
                "final_status": "still_open",
                "closed_at": None,
                "total_pnl": realised + unrealised,
                "hold_days": 0,
                "last_close": sim["day1_close"],
                "last_evaluated_date": alert_date,
            }

        try:
            await insert_orb_extension_shadow_row(row)
        except Exception as e:
            logger.warning(
                f"orb_ext_shadow {ticker} {alert_date} cutoff={cutoff_min}: insert failed: {e}"
            )

    logger.info(
        f"orb_ext_shadow recorded {ticker} {alert_date} "
        f"(trade_id={trade_id}, {len(CUTOFF_MINUTES)} cutoffs)"
    )


async def settle_open_shadows(today: _date | None = None) -> dict:
    """Resume each still_open shadow forward via production exit logic.

    Pulls daily bars from last_evaluated_date+1 through today and walks
    apply_daily_exit_step bar-by-bar, persisting state after each row.
    Called at the end of _nightly_data_pull (after mi_daily_closes is
    refreshed).

    Returns summary dict for audit logging.
    """
    today = today or et_today()
    open_rows = await get_open_orb_extension_shadows()
    if not open_rows:
        return {"reviewed": 0, "settled": 0, "still_open": 0, "errors": 0}

    settled = 0
    still_open = 0
    errors = 0
    for r in open_rows:
        try:
            state = dict(r["state"]) if r["state"] else {}
            if isinstance(state.get("alert_date"), str):
                state["alert_date"] = _date.fromisoformat(state["alert_date"])
            elif state.get("alert_date") is None:
                state["alert_date"] = r["alert_date"]
            # asyncpg JSONB → list/dict already; defensive copy
            state["exits"] = list(state.get("exits") or [])
            state["running_closes"] = list(state.get("running_closes") or [])

            start = (r["last_evaluated_date"] or r["alert_date"]) + _td(days=1)
            if start > today:
                still_open += 1
                continue
            try:
                bars_raw = await get_index_history(
                    r["ticker"], start.isoformat(), today.isoformat(),
                )
            except Exception as e:
                logger.warning(
                    f"orb_ext_shadow settle {r['ticker']}: bar fetch failed: {e}"
                )
                errors += 1
                continue

            bars = sorted(
                (
                    {
                        "date": _dt.fromtimestamp(b["t"] / 1000, tz=_ET).date(),
                        "l": float(b["l"]),
                        "c": float(b["c"]),
                    }
                    for b in bars_raw
                ),
                key=lambda x: x["date"],
            )

            closed_status = None
            closed_date = None
            last_eval = r["last_evaluated_date"] or r["alert_date"]
            # #445: seed + carry live in the ONE driver (in-place carry = the
            # persisted-state contract; `state` writes straight back below).
            fwd = ((b["date"], b) for b in bars if b["date"] > last_eval)
            for _i, d, step in iter_exit_ladder(state, fwd):
                last_eval = d
                if step.closed:
                    closed_status = step.close_reason
                    closed_date = d

            realised = sum(e.get("pnl", 0) for e in state["exits"])
            if closed_status:
                hold_days = (closed_date - r["alert_date"]).days
                last_close = state["running_closes"][-1] if state["running_closes"] else None
                await update_orb_extension_shadow_state(
                    r["id"],
                    state=state,
                    final_status=closed_status,
                    closed_at=closed_date,
                    total_pnl=realised,
                    hold_days=hold_days,
                    last_close=last_close,
                    last_evaluated_date=last_eval,
                )
                settled += 1
            else:
                last_close = state["running_closes"][-1] if state["running_closes"] else None
                unrealised = (
                    (last_close - state["entry_price"]) * state["remaining_shares"]
                    if last_close and state.get("entry_price") else 0.0
                )
                await update_orb_extension_shadow_state(
                    r["id"],
                    state=state,
                    final_status="still_open",
                    closed_at=None,
                    total_pnl=realised + unrealised,
                    hold_days=(today - r["alert_date"]).days,
                    last_close=last_close,
                    last_evaluated_date=last_eval,
                )
                still_open += 1
        except Exception as e:
            logger.warning(
                f"orb_ext_shadow settle id={r.get('id')} {r.get('ticker')}: {e}",
                exc_info=True,
            )
            errors += 1

    return {
        "reviewed": len(open_rows),
        "settled": settled,
        "still_open": still_open,
        "errors": errors,
    }
