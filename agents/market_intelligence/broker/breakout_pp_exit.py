"""Breakout v1 PAPER — the `pp` exit's inputs for the live jobs (phase 2 part B, build 2026-10-30). The I/O half of
`breakout_pp_rules.py` (the pure decisions); the jobs that ACT are `live_tracker.run_partial_exits` (15:45 ET: the stall
cut, the session-3 third) and `live_tracker.update_open_positions_live` (16:45 ET: the day-0 facts, the 20-day trail mark,
the stop at cost after a third), plus `order_manager.scan_profit_triggers` (the +2R third) and
`order_manager.run_breakout_pp_open_sales` (19:02 ET: the PAPER DAY market sale at the next open).

What lives here:
  * `ensure_day0_facts` — the breakout day's facts the way the shadow recorder captures them
    (`consolidation_breakout_pp.day0_facts`, ported as `breakout_pp_rules.day0_facts`): the day's minute bars after the
    fill minute walked against the stop and the +2R target, and the day's highest minute high after the fill. Captured
    once, by the 16:45 job on the breakout day (or the first later run that finds them missing), and stored on the trade
    row (`mi_live_trades.breakout_day0_pp`, JSONB). The live third and stop on day 0 are the poll's and the broker's; the
    facts feed the stall cut's "+1R reached" and are the record the equality with the walk is read against.
  * `load_sessions` — the stock's daily closes through the breakout day and the sessions since, from one daily-bar fetch.
  * `paper_wall` — a `breakout_pp` row whose account is not 'paper' is never acted on: audited + paged, nothing sent.
  * `resting_third` — is the +2R third still RESTING at the broker (a non-terminal `partial_exit` order on the trade)? The
    15:45 session-3 step never sells a second third beside one (his ruling 2026-10-29: follow what actually filled).
  * `cancel_resting_third` — the 15:45 session-3 step's cancel of that resting +2R limit before it sells the third at
    the close (his ruling 2026-10-29 late, "option a"): the marker (`PLANNED_THIRD_CANCEL`, read by the trade stream and
    the +2R poll — `planned_third_cancel_marked`), the cancel, the broker's confirmation; a fill in the race IS the third.
    `reprotect_after_unsold_third` covers the third's shares from broker truth when the sale after a cancel fails.

Telegram: failures page paper-prefixed, once per (trade, kind) per process; normal events are audit rows (the jobs' own
decision messages are sent by the jobs).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker import breakout_pp_rules as rules
from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.collector import get_index_history
from agents.market_intelligence.constants import mode_prefix
from agents.market_intelligence.db import BREAKOUT_V1_ACCOUNT_MODE, get_pool, log_audit_event
from shared.dates import _ET

logger = logging.getLogger(__name__)

N_SESSION_MINUTES = 390
PLANNED_THIRD_CANCEL = "breakout_pp_planned_third_cancel"   # the marker the trade stream and the +2R poll read
CANCEL_POLL_ATTEMPTS = 12        # ~3 s at 0.25 s: the broker's confirmation of the cancel
CANCEL_POLL_S = 0.25
MARKER_LOOKBACK_DAYS = 200       # a breakout trade's marker stays readable for its life (the poll guard)
_DEAD_UNFILLED = frozenset({"canceled", "cancelled", "expired", "rejected", "done_for_day"})
HISTORY_LOOKBACK_DAYS = 60       # calendar days before the breakout day: ~41 sessions, the 20-day needs 20

_paged: set[tuple] = set()


def _session_open(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=_ET)


def fill_minute_of(filled_at, alert_date: date) -> int | None:
    """Minutes since 09:30 ET of the fill (the minute bar the fill printed in), or None when the fill is not inside the
    breakout day's regular session."""
    if filled_at is None:
        return None
    t = filled_at.astimezone(_ET)
    if t.date() != alert_date:
        return None
    m = int((t - _session_open(alert_date)).total_seconds() // 60)
    return m if 0 <= m < N_SESSION_MINUTES else None


def minutes_from_bars(bars: list[dict], d: date) -> list[tuple]:
    """[(minute, open, high, low)] for `d`'s regular-hours minute bars (`alpaca.get_minute_bars_range` shape), oldest first."""
    out: dict[int, tuple] = {}
    open_dt = _session_open(d)
    for b in bars or []:
        t = b.get("t_et") or b.get("timestamp")
        if t is None or any(b.get(k) is None for k in ("open", "high", "low")):
            continue
        m = int((t.astimezone(_ET) - open_dt).total_seconds() // 60)
        if 0 <= m < N_SESSION_MINUTES:
            out[m] = (m, float(b["open"]), float(b["high"]), float(b["low"]))
    return [out[m] for m in sorted(out)]


def coerce_facts(raw) -> dict | None:
    """The stored facts (the jsonb codec returns a dict; a str is tolerated), or None when absent / not a v1 record."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    return raw if rules.valid_day0_facts(raw) else None


async def _page_once(key: tuple, text: str) -> None:
    if key in _paged:
        return
    _paged.add(key)
    try:
        await send_telegram_message(f"{mode_prefix(BREAKOUT_V1_ACCOUNT_MODE)}{text}")
    except Exception as e:  # loud-ok: a page must never stop an exit pass
        logger.warning(f"breakout pp page failed: {e}")


async def paper_wall(trade: dict, job: str) -> bool:
    """True when the row may be acted on: its account is 'paper' (breakout v1's ONE permitted account). Otherwise audited +
    paged and False — nothing is sold, marked or moved by the pp branch (the broker's resting stop stays)."""
    if trade.get("account_mode") == BREAKOUT_V1_ACCOUNT_MODE:
        return True
    await log_audit_event(
        "breakout_pp_refused_not_paper",
        f"{trade.get('ticker')} #{trade.get('id')}: a breakout_pp row on account "
        f"{trade.get('account_mode')!r} — the {job} pp branch refused it (paper only)",
        json.dumps({"trade_id": trade.get("id"), "ticker": trade.get("ticker"),
                    "account_mode": trade.get("account_mode"), "job": job}),
    )
    await _page_once(("not_paper", trade.get("id")),
                     f"🚨 {trade.get('ticker')}: a breakout v1 trade row is on the "
                     f"{trade.get('account_mode')!r} account. Its exit was NOT run (paper only) — check it by hand.")
    return False


async def resting_third(trade_id: int) -> tuple[bool, str | None]:
    """(resting, order id) — True when the trade carries a NON-TERMINAL `partial_exit` order in `mi_live_orders` (the
    +2R third resting at its target, placed by `scan_profit_triggers` -> `execute_partial_exit`; the terminal set is
    `order_manager.PENDING_EXIT_TERMINAL_STATUSES`, the one copy `get_pending_exit_qty` and the partial-exit dedup read).
    FAILS SAFE: an unreadable book reads as resting (no session-3 third is sold beside an order we cannot see), audited."""
    from agents.market_intelligence.broker.order_manager import PENDING_EXIT_TERMINAL_STATUSES
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            oid = await conn.fetchval("""
                SELECT alpaca_order_id FROM mi_live_orders
                WHERE trade_id = $1 AND purpose = 'partial_exit' AND status != ALL($2::text[])
                ORDER BY id DESC LIMIT 1
            """, trade_id, list(PENDING_EXIT_TERMINAL_STATUSES))
        return (oid is not None), (str(oid) if oid is not None else None)
    except Exception as e:  # loud-ok: fail safe — read as resting (no second third), audited
        logger.warning(f"breakout pp: resting-third read failed for trade {trade_id} ({e}) — treated as resting")
        await log_audit_event(
            "breakout_pp_resting_third_unreadable",
            f"trade #{trade_id}: the open partial-exit orders could not be read ({type(e).__name__}) — treated as a "
            f"third still resting (no session-3 third sold)",
            json.dumps({"trade_id": trade_id, "error": str(e)[:300]}),
        )
        return True, None


async def _store_day0_facts(trade_id: int, facts: dict, account_mode: str) -> bool:
    """The ONE writer of `mi_live_trades.breakout_day0_pp`: write-once (only while NULL), only on a breakout_pp PAPER row."""
    from agents.market_intelligence.broker.order_manager import BREAKOUT_PP_EXIT_RULE
    from agents.market_intelligence.db import _jsonb_param
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchval("""
            UPDATE mi_live_trades SET breakout_day0_pp = $2::jsonb
            WHERE id = $1 AND breakout_day0_pp IS NULL AND exit_rule = $3 AND account_mode = $4
            RETURNING id
        """, trade_id, _jsonb_param(facts), BREAKOUT_PP_EXIT_RULE, account_mode)
    return r is not None


async def ensure_day0_facts(trade: dict) -> dict | None:
    """The trade's day-0 facts: the stored ones, else computed from the breakout day's minute bars and stored. None (audited,
    paged once) when they cannot be computed — no fill time inside the breakout day's session, no minute bars, or a stop
    not under the fill. NEVER raises: an exit pass must go on."""
    stored = coerce_facts(trade.get("breakout_day0_pp"))
    if stored is not None:
        return stored
    ticker, alert_date = trade.get("ticker"), trade.get("alert_date")
    why = None
    try:
        fill = float(trade.get("entry_price") or 0)
        stop = float(trade.get("hard_stop") or trade.get("stop_price") or 0)
        fm = fill_minute_of(trade.get("filled_at"), alert_date)
        if fm is None:
            why = "no fill time inside the breakout day's regular session"
        elif not (0 < stop < fill):
            why = f"stop {stop} is not under the fill {fill}"
        else:
            bars = await alpaca.get_minute_bars_range(
                ticker, _session_open(alert_date), _session_open(alert_date) + timedelta(minutes=N_SESSION_MINUTES))
            mins = minutes_from_bars(bars, alert_date)
            if not mins:
                why = "no minute bars for the breakout day"
            else:
                facts = rules.day0_facts(mins, fill=fill, stop=stop, fill_minute=fm)
                await _store_day0_facts(trade["id"], facts, trade.get("account_mode"))
                await log_audit_event(
                    "breakout_pp_day0_facts",
                    f"{ticker} #{trade['id']}: breakout-day facts recorded (fill minute {fm}, "
                    f"{'stopped' if facts['stopped'] else 'open'}, peak {facts['peak']})",
                    json.dumps({"trade_id": trade["id"], "ticker": ticker, "fill_minute": fm, "fill": fill,
                                "stop": stop, "facts": facts}),
                )
                return facts
    except Exception as e:  # loud-ok: audited + paged below; the exit pass goes on
        why = f"{type(e).__name__}: {e}"
    await log_audit_event(
        "breakout_pp_day0_facts_missing",
        f"{ticker} #{trade.get('id')}: breakout-day facts NOT recorded — {why}",
        json.dumps({"trade_id": trade.get("id"), "ticker": ticker, "why": why}),
    )
    await _page_once(("day0", trade.get("id")),
                     f"⚠️ {ticker}: breakout v1 could not record the breakout day's minutes ({why}). "
                     f"Its stall cut (no +1R by day 3) will NOT be applied until they are — check it by hand.")
    return None


async def load_sessions(trade: dict, today: date, today_bar: dict | None) -> tuple[list[float], list[dict]] | None:
    """(closes_before, fwd) for `breakout_pp_rules` — the daily closes through the breakout day and the sessions since,
    today's bar last (`today_bar`: the 15:45 forming bar or the settled 16:45 bar). None (audited) when the history read
    returns nothing."""
    alert_date = trade["alert_date"]
    hist = await get_index_history(trade["ticker"],
                                   (alert_date - timedelta(days=HISTORY_LOOKBACK_DAYS)).strftime("%Y-%m-%d"),
                                   today.strftime("%Y-%m-%d"))
    if not hist:
        await log_audit_event(
            "breakout_pp_history_missing",
            f"{trade['ticker']} #{trade['id']}: no daily history — no pp decision this pass (the stop stays)",
            json.dumps({"trade_id": trade["id"], "ticker": trade["ticker"], "today": str(today)}),
        )
        return None
    return rules.split_sessions(hist, alert_date=alert_date, today=today, today_bar=today_bar)


# ── the session-3 cancel of a resting +2R third (his ruling 2026-10-29 late, "option a") ─────────────────────────────────
async def _record_planned_third_cancel(trade: dict, order_id: str) -> bool:
    """The marker, written BEFORE the cancel: the trade stream then leaves this cancel's unfilled order alone (no
    re-protect of the third's shares this step is about to sell), and the +2R poll never re-places the limit on this
    trade. False when it could not be written — the step then cancels nothing."""
    try:
        await log_audit_event(
            PLANNED_THIRD_CANCEL,
            f"{trade.get('ticker')} #{trade.get('id')}: session 3 — cancelling the resting +2R third "
            f"{str(order_id)[:8]} to sell the third at the close",
            json.dumps({"trade_id": trade.get("id"), "ticker": trade.get("ticker"), "order_id": str(order_id),
                        "account_mode": trade.get("account_mode")}))
        return True
    except Exception as e:  # loud-ok: no marker -> no cancel (the limit keeps resting; nothing doubled)
        logger.warning(f"breakout pp planned-third-cancel marker write failed for trade {trade.get('id')}: {e}")
        return False


async def planned_third_cancel_marked(trade_id, order_id: str | None = None) -> bool:
    """Did the 15:45 session-3 step cancel this trade's resting +2R third on purpose (this exact order, when
    `order_id` is given)? Matched in Python (detail is TEXT). A failed read -> False for the stream (it then re-protects
    as before — the safe side for shares), and the poll's caller treats False as 'not cancelled' (it may re-place)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT event_type, detail FROM mi_audit_log WHERE event_type = $1 "
                f"AND created_at > NOW() - INTERVAL '{int(MARKER_LOOKBACK_DAYS)} days' ORDER BY created_at DESC",
                PLANNED_THIRD_CANCEL)
        for row in rows or []:
            if row["event_type"] != PLANNED_THIRD_CANCEL:
                continue
            try:
                d = json.loads(row["detail"])
            except Exception:  # loud-ok: one malformed row is skipped, never the check
                continue
            if str(d.get("trade_id")) == str(trade_id) and (order_id is None or str(d.get("order_id")) == str(order_id)):
                return True
    except Exception as e:  # loud-ok: logged; see the docstring for each caller's safe side
        logger.warning(f"breakout pp planned-third-cancel marker read failed ({e}) — treated as NOT marked")
    return False


def _cancel_state(order: dict | None) -> str:
    """'filled' (any share filled — that fill IS the third) | 'dead' (terminal, nothing filled) | 'open' | 'unknown'."""
    if not order:
        return "unknown"
    status = str(order.get("status") or "").split(".")[-1].lower()
    if float(order.get("filled_qty") or 0) > 0 or status == "filled":
        return "filled"
    if status in _DEAD_UNFILLED:
        return "dead"
    return "open"


async def cancel_resting_third(trade: dict, order_id: str | None) -> dict:
    """Cancel the resting +2R third `order_id` of `trade` and wait for the broker to confirm. ->
    {"state", "order_id", "qty", "filled_qty"}:
      * 'dead'    — cancelled with NOTHING filled: the order row is closed here (compare-and-set on it still being open,
                    so `execute_partial_exit`'s dedup sees no open third) and `qty` (the cancelled order's own size) is
                    the third to sell at the close;
      * 'filled'  — it filled (in full or in part) before the cancel took: that fill IS the third — nothing more is sold;
                    the trade stream books it (`finalize_partial_exit`, idempotent) and re-protects any unfilled rest;
      * 'open'    — still live after the wait, or the cancel was refused: nothing sold (the limit keeps resting);
      * 'unknown' — no order id, the marker could not be written, or the order is unreadable: nothing sold.
    Paper only (the caller's wall). NEVER raises."""
    out = {"state": "unknown", "order_id": order_id, "qty": None, "filled_qty": None}
    if not order_id:
        return out
    mode = trade.get("account_mode")
    try:
        if not await _record_planned_third_cancel(trade, order_id):
            return out
        accepted = await alpaca.cancel_order(order_id, account_mode=mode)
        order = None
        for i in range(CANCEL_POLL_ATTEMPTS):
            order = await alpaca.get_order(order_id, account_mode=mode)
            out["state"] = _cancel_state(order)
            if out["state"] in ("dead", "filled"):
                break
            if i < CANCEL_POLL_ATTEMPTS - 1:
                await asyncio.sleep(CANCEL_POLL_S)
        if order:
            out["qty"] = float(order.get("qty") or 0) or None
            out["filled_qty"] = float(order.get("filled_qty") or 0)
        out["cancel_accepted"] = bool(accepted)
        if out["state"] == "dead":
            from agents.market_intelligence.broker.order_manager import PENDING_EXIT_TERMINAL_STATUSES
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_orders SET status = 'cancelled', cancelled_at = COALESCE(cancelled_at, NOW())
                    WHERE alpaca_order_id = $1 AND trade_id = $2 AND status != ALL($3::text[])
                """, str(order_id), trade.get("id"), list(PENDING_EXIT_TERMINAL_STATUSES))
            if not out["qty"]:
                out["state"] = "unknown"        # a dead order with no size: never guess the third
    except Exception as e:  # loud-ok: audited by the caller from the returned state; nothing sold
        logger.warning(f"breakout pp: cancelling the resting third {order_id} of trade {trade.get('id')} raised: {e}")
        out["state"] = "unknown" if out["state"] != "filled" else "filled"
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    return out


async def reprotect_after_unsold_third(trade: dict) -> str | None:
    """After a cancelled +2R third whose sale at the close did not go through, the third's shares may have no stop (the
    cancelled OCO took its sibling stop with it, and the marker kept the trade stream from re-protecting). Converge from
    BROKER truth with the shared `_ensure_stop_coverage` (idempotent; a no-op when covered), at the row's stop."""
    from agents.market_intelligence.broker.order_manager import _ensure_stop_coverage
    try:
        mode = trade.get("account_mode")
        pos = await alpaca.get_position(trade["ticker"], account_mode=mode)
        qty = float(pos.get("qty")) if pos and pos.get("qty") is not None else 0.0
        if qty <= 0:
            return None
        stop = trade.get("stop_price") or trade.get("hard_stop")
        return await _ensure_stop_coverage(trade["id"], trade["ticker"], qty, float(stop) if stop else None,
                                           trade.get("signal_type") or "unknown", mode)
    except Exception as e:  # loud-ok: the caller pages; the 5-minute coverage repair is the backstop
        logger.error(f"breakout pp: re-protect after an unsold third raised for trade {trade.get('id')}: {e}")
        return f"re-protect raised: {e}"
