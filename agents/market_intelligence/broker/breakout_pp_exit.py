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

Telegram: failures page paper-prefixed, once per (trade, kind) per process; normal events are audit rows (the jobs' own
decision messages are sent by the jobs).
"""
from __future__ import annotations

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
