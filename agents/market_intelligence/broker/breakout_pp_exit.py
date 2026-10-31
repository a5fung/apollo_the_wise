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
    the close (his ruling 2026-10-29 late, "option a"): the marker (`PLANNED_THIRD_CANCEL`, read by the trade stream —
    `planned_third_cancel_marked` — and, fail-closed, by the +2R poll — `third_replacement_banned`), the cancel, the
    broker's confirmation of the parent AND its sibling stop leg (bounded reads, a wall-clock deadline); a limit fill
    in the race IS the third, a stop-leg fill is the third sold at its stop. A cancel the step cannot confirm (or a dead
    order whose row it cannot close) WITHDRAWS the marker for the stream (`PLANNED_THIRD_CANCEL_WITHDRAWN`), so a late
    settle is re-protected like any OCO-parent cancel; the poll's ban stands. `reprotect_after_unsold_third` covers the
    third's shares from broker truth whenever the step did not sell (pre-merge 2026-10-31, findings 1-4).
  * `session_third_due` — HIS RULING 2026-10-31 ("Retry the sale at the next day's close"): did session 3 DECIDE to sell
    the third (the record the 15:45 step writes at that decision, `SESSION_THIRD_DUE`)? On sessions 4, 5, ... the step
    retries the close sale on a trade with the record and still no third sold (`breakout_pp_rules.retry_decision`),
    cancelling any partial-exit order still resting first with the same confirm-or-replace discipline. The poll's ban
    on re-placing the +2R limit is untouched: the retry is a close sale, never a limit.

Telegram: failures page paper-prefixed, once per (trade, kind) per process; normal events are audit rows (the jobs' own
decision messages are sent by the jobs).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
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
# Pre-merge 2026-10-31 (findings 1+2, advisor item 1): the step WITHDRAWS the stream's "leave this cancel alone" when
# it did NOT sell the third (an unconfirmed cancel, a dead order whose row could not be closed) — a LATE settle is then
# an ordinary OCO-parent cancel for the stream (`_handle_oco_parent_cancel` re-protects from broker truth). The +2R
# poll's ban is NOT withdrawn with it (`third_replacement_banned` reads the marker alone): one third ever stays his.
PLANNED_THIRD_CANCEL_WITHDRAWN = "breakout_pp_planned_third_cancel_withdrawn"
# HIS RULING 2026-10-31 ("Go with rec": "Retry the sale at the next day's close"): the 15:45 step records that session 3
# DECIDED to sell the third (the close above the fill, no third sold) BEFORE it cancels or sells anything. On sessions
# 4, 5, ... the same step reads this record (`session_third_due`): a trade with it and still no third sold RETRIES the
# sale at that session's close (`breakout_pp_rules.retry_decision`). The record is what makes the retry restart-safe
# and keeps it off trades whose session 3 decided nothing (never a third on a trade whose session-3 close was at or
# under the fill). The planned-cancel marker and the session-third row are read beside it (either proves the decision).
SESSION_THIRD_DUE = "breakout_pp_session_third_due"
SESSION_THIRD_EVENT = "breakout_pp_session_third"          # the 15:45 step's "selling N sh" row (live_tracker writes it)
# Retry-pass review 2026-10-31 (the one-third-ever reader): the row's flag and booked exits are NOT the whole truth of
# what left the position — a session-3 market sale the broker ACCEPTED whose order row never got written (the INSERT
# raised, or the process restarted between the place and the INSERT) fills as an 'Untracked SELL' the stream books
# nowhere; the 16:05 sync then lowers `remaining_shares` alone (`sync_qty_overwrite`: a quantity, no exit, no flag).
# `shares_already_sold` reads the row's two share counts and the broker's position beside the flag, the exits and the
# order book, and writes this row when either says shares left that the books never recorded.
SHARES_LEFT_UNBOOKED = "breakout_pp_shares_left_unbooked"
CANCEL_POLL_ATTEMPTS = 24        # the confirmation poll's cap in reads (x CANCEL_POLL_S between reads)
CANCEL_POLL_S = 0.25
CANCEL_READ_TIMEOUT_S = 3.0      # finding 3: each confirmation read is bounded (the SDK default is 30 s)
CANCEL_DEADLINE_S = 8.0          # finding 3: the whole confirmation wait is bounded by the wall clock, so the
#                                  session-3 sale goes out at 15:45, never at the close. The cancel REQUEST itself
#                                  keeps the SDK's write timeout (alpaca_client.cancel_order takes none).
MARKER_LOOKBACK_DAYS = 200       # a breakout trade's marker stays readable for its life (the poll guard)
_DEAD_UNFILLED = frozenset({"canceled", "cancelled", "expired", "rejected", "done_for_day"})
HISTORY_LOOKBACK_DAYS = 60       # calendar days before the breakout day: ~41 sessions, the 20-day needs 20
_clock = time.monotonic          # the deadline's clock (patchable in tests)

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


async def _withdraw_planned_third_cancel(trade: dict, order_id: str, why: str) -> bool:
    """Pre-merge 2026-10-31: the step did NOT sell the third it marked for — hand the order back to the stream. A row
    naming the trade AND the order, newer than the marker: `planned_third_cancel_marked` then reads False for the
    stream, so a cancel that settles late is re-protected through `_handle_oco_parent_cancel` (broker truth,
    idempotent). The +2R poll's ban (`third_replacement_banned`) does NOT read this row. Never raises."""
    try:
        await log_audit_event(
            PLANNED_THIRD_CANCEL_WITHDRAWN,
            f"{trade.get('ticker')} #{trade.get('id')}: the planned cancel of the +2R third {str(order_id)[:8]} did "
            f"not end in a sale ({why}) — a late settle is the stream's to re-protect",
            json.dumps({"trade_id": trade.get("id"), "ticker": trade.get("ticker"), "order_id": str(order_id),
                        "account_mode": trade.get("account_mode"), "why": why}))
        return True
    except Exception as e:  # loud-ok: the step still re-protects from broker truth itself (its caller)
        logger.warning(f"breakout pp planned-third-cancel withdrawal write failed for trade {trade.get('id')}: {e}")
        return False


async def _audit_rows(event_types: list[str]) -> list[dict]:
    """The audit rows of `event_types` within a breakout trade's life, newest first (the markers' one query shape)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT event_type, detail, created_at FROM mi_audit_log WHERE event_type = ANY($1::text[]) "
            f"AND created_at > NOW() - INTERVAL '{int(MARKER_LOOKBACK_DAYS)} days' ORDER BY created_at DESC, id DESC",
            list(event_types))
    return list(rows or [])


async def _marker_rows() -> list[dict]:
    return await _audit_rows([PLANNED_THIRD_CANCEL, PLANNED_THIRD_CANCEL_WITHDRAWN])


def _marker_matches(row: dict, trade_id, order_id: str | None) -> bool:
    try:
        d = json.loads(row["detail"])
    except Exception:  # loud-ok: one malformed row is skipped, never the check
        return False
    return (str(d.get("trade_id")) == str(trade_id)
            and (order_id is None or str(d.get("order_id")) == str(order_id)))


async def planned_third_cancel_marked(trade_id, order_id: str | None = None) -> bool:
    """THE STREAM's question: did the 15:45 session-3 step cancel this trade's resting +2R third on purpose (this exact
    order, when `order_id` is given) AND is it still selling those shares? The NEWEST marker / withdrawal row naming
    the trade (and order) decides: a marker -> True (leave the cancel alone), a withdrawal -> False (re-protect as any
    OCO-parent cancel). Matched in Python (detail is TEXT). A failed read -> False (the stream then re-protects as
    before — the safe side for shares). The +2R POLL must not read this: it reads `third_replacement_banned`."""
    try:
        for row in await _marker_rows():
            if row["event_type"] not in (PLANNED_THIRD_CANCEL, PLANNED_THIRD_CANCEL_WITHDRAWN):
                continue
            if _marker_matches(row, trade_id, order_id):
                return row["event_type"] == PLANNED_THIRD_CANCEL
    except Exception as e:  # loud-ok: logged; the stream's safe side is "not marked" (it re-protects)
        logger.warning(f"breakout pp planned-third-cancel marker read failed ({e}) — treated as NOT marked")
    return False


async def third_replacement_banned(trade_id) -> bool:
    """THE +2R POLL's question (finding 4, pre-merge 2026-10-31): may a +2R limit be placed on this trade? Banned once
    the session-3 step has EVER marked a planned cancel on it (withdrawn or not — the intent to sell the third at the
    close is the ban; one third ever is his ruling, and whether a third should be retried when the sale did not happen
    is his open question). FAILS CLOSED: an unreadable log reads as banned — a limit that is not placed costs a poll,
    a limit placed beside a sale is a second third."""
    try:
        for row in await _marker_rows():
            if row["event_type"] == PLANNED_THIRD_CANCEL and _marker_matches(row, trade_id, None):
                return True
        return False
    except Exception as e:  # loud-ok: fail closed — no +2R limit is placed on a trade whose marker cannot be read
        logger.warning(f"breakout pp: marker read failed for trade {trade_id} ({e}) — the +2R limit is NOT placed")
        await log_audit_event(          # the durable record: a breakout trade past +2R with no limit and rows of THIS
            "breakout_pp_marker_unreadable",   # event is a failing read, not a ban (log_audit_event never raises)
            f"trade #{trade_id}: the planned-cancel marker could not be read ({type(e).__name__}) — no +2R limit "
            f"placed this poll (fail closed); the next poll reads again",
            json.dumps({"trade_id": trade_id, "error": str(e)[:300]}))
        return True


async def session_third_due(trade_id) -> bool:
    """THE RETRY's question (his ruling 2026-10-31): did the 15:45 step on session 3 DECIDE to sell this trade's third?
    True when any row of `SESSION_THIRD_DUE` (written at the decision, before the cancel or the sale), the planned-cancel
    marker, or the "selling N sh" row names the trade. FAILS CLOSED for selling: an unreadable log reads as NOT due —
    nothing is sold this session (a wrongful sale is irreversible; the next session reads again), audited."""
    due_types = (SESSION_THIRD_DUE, PLANNED_THIRD_CANCEL, SESSION_THIRD_EVENT)
    try:
        for row in await _audit_rows(list(due_types)):
            if row["event_type"] in due_types and _marker_matches(row, trade_id, None):
                return True
        return False
    except Exception as e:  # loud-ok: fail closed — no retry sale on a trade whose record cannot be read
        logger.warning(f"breakout pp: the session-third record could not be read for trade {trade_id} ({e}) — "
                       f"no retry this session")
        await log_audit_event(
            "breakout_pp_third_due_unreadable",
            f"trade #{trade_id}: the session-3 decision record could not be read ({type(e).__name__}) — the third is "
            f"not retried this session; the next close reads again",
            json.dumps({"trade_id": trade_id, "error": str(e)[:300]}))
        return False


def _exits_with_shares(raw) -> int:
    """How many booked exits on the row carry shares (`mi_live_trades.exits`: a jsonb list, or its text)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return 0
    if not isinstance(raw, list):
        return 0
    return sum(1 for e in raw if isinstance(e, dict) and float(e.get("shares") or 0) > 0)


def _num(v) -> float | None:
    """A share count as a float, None when the column is missing or not a number (never a crash, never a false read)."""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


async def _audit_shares_left(trade: dict, arm: str, why: str, **counts) -> None:
    """The `breakout_pp_shares_left_unbooked` row: which read disagreed with the books, and the numbers. Its own
    failure never hides the verdict (the caller has already decided 'sold')."""
    logger.warning(f"breakout pp: {trade.get('ticker')} #{trade.get('id')} — {why} (read: {arm}); treated as a third "
                   f"already sold")
    try:
        await log_audit_event(
            SHARES_LEFT_UNBOOKED,
            f"{trade.get('ticker')} #{trade.get('id')}: {why} — read as a third already sold (nothing sold, nothing "
            f"cancelled this session; the books are behind a sale they never recorded — look for an 'Untracked SELL' "
            f"page and a `sync_qty_overwrite` row)",
            json.dumps({"trade_id": trade.get("id"), "ticker": trade.get("ticker"), "read": arm,
                        "account_mode": trade.get("account_mode"),
                        **{k: (None if v is None else float(v)) for k, v in counts.items()}}))
    except Exception as e:  # loud-ok: the verdict stands; the warning above is the trail
        logger.warning(f"breakout pp: the shares-left audit failed for trade {trade.get('id')}: {e}")


async def partial_taken_now(trade_id) -> bool | None:
    """The row's `partial_taken` as stored NOW. A +2R limit that filled between a step's row read and its sale's lock
    flips the flag under that lock, and the sale is refused for it (the retry-pass review, 2026-10-31, low): the step
    must not then page 'No third was sold'. None when unreadable — the caller keeps its not-sold path, which pages."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            v = await conn.fetchval("SELECT partial_taken FROM mi_live_trades WHERE id = $1", trade_id)
        return None if v is None else bool(v)
    except Exception as e:  # loud-ok: None hands the caller its not-sold path, which audits and pages
        logger.warning(f"breakout pp: the partial_taken re-read failed for trade {trade_id} ({e})")
        return None


async def shares_already_sold(trade: dict) -> tuple[bool, str | None]:
    """Has ANY share of this trade already been sold? The WIDER "a third sold" the session-3 step and the retry read
    beside `partial_taken` (his one third ever). `partial_taken` flips only when a PARTIAL-EXIT order fills; the
    third's OCO sibling STOP leg filling (the third sold at its stop — (A)'s `stop_filled`) is booked by the stream's
    stop-fill finalizer (`order_manager._finalize_stop_fill_locked`), which decrements `remaining_shares` and appends
    a 'stop_hit' exit WITHOUT setting the flag — so a trade whose third was just stopped would read "no third sold"
    the next session and be sold another (the advisor's final-review finding, 2026-10-31). And a sale the books never
    recorded at all — a session-3 market sale the broker ACCEPTED whose order row was never written (the INSERT raised
    after the place; a restart between the two): its fill is an 'Untracked SELL' the stream books nowhere, and the
    16:05 sync then lowers `remaining_shares` alone (the retry-pass review, 2026-10-31) — must read as sold too, or
    the next session's retry sells a SECOND third. -> (sold, why; each read has its own `why`). Reads, in order:
    the row's `partial_taken`; its `exits` (any booked exit with shares — on an OPEN breakout row nothing but a sold
    third, its stop leg, or the reduced 2/3 stop ever books one); the row's own counts — `remaining_shares` below
    `entry_shares` (both are set to the FILLED quantity at the entry fill, by the stream and by the polling backup
    alike, so on an open row with no flag and no exit a gap is a sale the books never recorded); the order book — a
    'partial_exit' or 'stop_loss' row of the trade filled in full or in part (a fill the stream has not booked yet);
    and last the broker — the position's `qty` below the row's count (the same afternoon, before the sync has folded
    an unrecorded sale into the row; `qty`, never `qty_available`, which a resting +2R OCO lowers by reserving its
    shares). FAILS CLOSED for selling: an unreadable book, and no position read (gone, or unreadable — the client
    answers None to both), read as sold (nothing sold this session; the next session reads again), audited. A read
    that finds shares left which the books never recorded writes `breakout_pp_shares_left_unbooked`."""
    tid, ticker = trade.get("id"), trade.get("ticker")
    if trade.get("partial_taken"):
        return True, "partial_taken"
    n = _exits_with_shares(trade.get("exits"))
    if n:
        return True, f"{n} exit(s) already booked on the open row (a stop-leg fill is the third sold at its stop)"
    remaining, entry = _num(trade.get("remaining_shares")), _num(trade.get("entry_shares"))
    if remaining is not None and entry is not None and remaining < entry - 0.5:
        why = (f"shares already left the position: the row holds {remaining:g} of the {entry:g} filled with no exit "
               f"booked (remaining < entry)")
        await _audit_shares_left(trade, "row_counts", why, remaining_shares=remaining, entry_shares=entry)
        return True, why
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            oid = await conn.fetchval("""
                SELECT alpaca_order_id FROM mi_live_orders
                WHERE trade_id = $1 AND purpose IN ('partial_exit', 'stop_loss')
                  AND (status IN ('filled', 'partially_filled') OR COALESCE(filled_qty, 0) > 0)
                ORDER BY id DESC LIMIT 1
            """, tid)
        if oid is not None:
            return True, f"a filled exit order row ({str(oid)[:8]}) the stream has not booked yet"
    except Exception as e:  # loud-ok: fail closed — nothing sold on a book that cannot be read
        logger.warning(f"breakout pp: the exit-order read failed for trade {tid} ({e}) — treated as sold")
        await log_audit_event(
            "breakout_pp_shares_sold_unreadable",
            f"{ticker} #{tid}: the trade's exit orders could not be read ({type(e).__name__}) "
            f"— treated as a third already sold (nothing sold this session; the next close reads again)",
            json.dumps({"trade_id": tid, "ticker": ticker, "error": str(e)[:300]}))
        return True, "the order book could not be read"
    # the broker last (the one external read): what is HELD against what the row says is held
    qty, err = None, None
    try:
        pos = await alpaca.get_position(ticker, account_mode=trade.get("account_mode"))
        qty = _num(pos.get("qty")) if isinstance(pos, dict) else None
    except Exception as e:  # loud-ok: the client swallows its own errors; this is the belt for anything it does not
        err = f"{type(e).__name__}: {e}"
    if qty is None:
        logger.warning(f"breakout pp: no position read for {ticker} #{tid} ({err or 'gone or unreadable'}) — treated "
                       f"as sold")
        await log_audit_event(
            "breakout_pp_shares_sold_unreadable",
            f"{ticker} #{tid}: no position read at the broker (gone, or unreadable"
            + (f": {err[:160]}" if err else "") + ") — treated as a third already sold (nothing sold this session; "
            "the next close reads again)",
            json.dumps({"trade_id": tid, "ticker": ticker, "error": (err or "")[:300], "read": "broker_position"}))
        return True, "no position read at the broker (gone, or unreadable)"
    if remaining is not None and qty < remaining - 0.5:
        why = (f"shares already left the position: the broker holds {qty:g} against the row's {remaining:g} with no "
               f"exit booked (broker qty < remaining)")
        await _audit_shares_left(trade, "broker_position", why, remaining_shares=remaining, entry_shares=entry,
                                 broker_qty=qty)
        return True, why
    return False, None


def _filled(order: dict | None) -> bool:
    if not order:
        return False
    status = str(order.get("status") or "").split(".")[-1].lower()
    return float(order.get("filled_qty") or 0) > 0 or status == "filled"


def _cancel_state(order: dict | None, leg: dict | None = None, leg_id: str | None = None) -> str:
    """'filled' (any share of the limit filled — that fill IS the third) | 'stop_filled' (the OCO's sibling STOP leg
    filled while the parent was being cancelled — the third sold at its stop; the parent reads cancelled with 0 filled,
    which alone would look 'dead' — finding 2) | 'dead' (terminal, nothing filled, no leg fill) | 'open' | 'unknown'
    (no read; or a dead parent whose leg exists but could not be read — never sold on)."""
    if not order:
        return "unknown"
    if _filled(order):
        return "filled"
    if _filled(leg):
        return "stop_filled"
    status = str(order.get("status") or "").split(".")[-1].lower()
    if status in _DEAD_UNFILLED:
        return "unknown" if (leg_id and leg is None) else "dead"
    return "open"


async def _stored_leg_id(order_id: str, trade_id) -> str | None:
    """The OCO's sibling stop-leg id from the stored parent row (`raw_response` holds the placement response with its
    legs — the record `_handle_oco_parent_cancel` reads too; a plain get_order is not nested). None for a plain limit."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            raw = await conn.fetchval(
                "SELECT raw_response FROM mi_live_orders WHERE alpaca_order_id = $1 AND trade_id = $2",
                str(order_id), trade_id)
        if isinstance(raw, str):
            raw = json.loads(raw)
        return alpaca.extract_stop_leg_id(raw) if isinstance(raw, dict) else None
    except Exception as e:  # loud-ok: the live read's legs are the fallback; no leg id -> the parent alone decides
        logger.warning(f"breakout pp: stored leg read failed for {order_id} ({e})")
        return None


async def _close_order_row(order_id: str, trade_id) -> bool:
    """The dead +2R limit's order row closed (compare-and-set on it still being open, so `execute_partial_exit`'s
    dedup and `get_pending_exit_qty` stop seeing a resting third). One retry. False when both attempts raised."""
    from agents.market_intelligence.broker.order_manager import PENDING_EXIT_TERMINAL_STATUSES
    for attempt in range(2):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE mi_live_orders SET status = 'cancelled', cancelled_at = COALESCE(cancelled_at, NOW())
                    WHERE alpaca_order_id = $1 AND trade_id = $2 AND status != ALL($3::text[])
                """, str(order_id), trade_id, list(PENDING_EXIT_TERMINAL_STATUSES))
            return True
        except Exception as e:  # loud-ok: retried once; the caller re-protects instead of trusting the DB
            logger.warning(f"breakout pp: closing the order row {order_id} failed (attempt {attempt + 1}): {e}")
            if attempt == 0:
                await asyncio.sleep(CANCEL_POLL_S)
    return False


async def cancel_resting_third(trade: dict, order_id: str | None) -> dict:
    """Cancel the resting +2R third `order_id` of `trade` and wait for the broker to confirm. ->
    {"state", "order_id", "qty", "filled_qty", "cancel_sent", "cancel_accepted", "leg_id", "marker_withdrawn",
     "row_update_error"}:
      * 'dead'        — cancelled with NOTHING filled: the order row is closed here (`_close_order_row`, one retry) and
                        `qty` (the cancelled order's own size) is the third to sell at the close. `row_update_error`
                        set = the row could NOT be closed: the caller sells nothing (the dedup would refuse on the stale
                        row) and re-protects (`reprotect_after_unsold_third`, which retries the close first);
      * 'filled'      — it filled (in full or in part) before the cancel took: that fill IS the third — nothing more is
                        sold; the trade stream books it (`finalize_partial_exit`, idempotent) and re-protects any rest;
      * 'stop_filled' — the OCO's sibling STOP leg filled in the race: the third sold at its stop (finding 2) — nothing
                        more is sold; the leg's own fill event books it. The parent's row is closed (it is dead);
      * 'open'        — still live after the wait (CANCEL_DEADLINE_S / CANCEL_POLL_ATTEMPTS), or the cancel was
                        refused: nothing sold. The marker is WITHDRAWN (`marker_withdrawn`), so a cancel that settles
                        LATER is re-protected by the stream like any OCO-parent cancel; the caller also re-protects
                        from broker truth at once (a no-op while the limit really rests — its open row nets the third
                        — and the cover when the stream already closed the row and was told to leave it);
      * 'unknown'     — no order id / the marker could not be written (nothing cancelled, `cancel_sent` False), or
                        the order is unreadable, or a dead parent whose stop leg could not be read: nothing sold; the
                        marker withdrawn when a cancel was sent.
    Each confirmation read is bounded (CANCEL_READ_TIMEOUT_S) and the wait by the wall clock (finding 3). Paper only
    (the caller's wall). NEVER raises."""
    out = {"state": "unknown", "order_id": order_id, "qty": None, "filled_qty": None, "cancel_sent": False,
           "cancel_accepted": None, "leg_id": None, "marker_withdrawn": False, "row_update_error": None}
    if not order_id:
        return out
    mode, tid = trade.get("account_mode"), trade.get("id")
    try:
        if not await _record_planned_third_cancel(trade, order_id):
            return out
        out["leg_id"] = leg_id = await _stored_leg_id(order_id, tid)
        accepted = await alpaca.cancel_order(order_id, account_mode=mode)
        out["cancel_sent"], out["cancel_accepted"] = True, bool(accepted)
        order, leg = None, None
        t0 = _clock()
        for i in range(CANCEL_POLL_ATTEMPTS):
            order = await alpaca.get_order(order_id, account_mode=mode, timeout=CANCEL_READ_TIMEOUT_S)
            if order and not leg_id:
                leg_id = out["leg_id"] = alpaca.extract_stop_leg_id(order)      # a nested read, when the SDK gives one
            leg = None
            if order and leg_id and not _filled(order) and _cancel_state(order) != "open":
                # the parent reads dead with nothing filled: was it the OCO unwinding on a STOP-leg fill?
                leg = await alpaca.get_order(leg_id, account_mode=mode, timeout=CANCEL_READ_TIMEOUT_S)
            out["state"] = _cancel_state(order, leg, leg_id)
            if out["state"] in ("dead", "filled", "stop_filled"):
                break
            if i >= CANCEL_POLL_ATTEMPTS - 1 or _clock() - t0 >= CANCEL_DEADLINE_S:
                break
            await asyncio.sleep(CANCEL_POLL_S)
        if order:
            out["qty"] = float(order.get("qty") or 0) or None
            out["filled_qty"] = float(order.get("filled_qty") or 0)
        # a dead parent's row is closed whatever its leg did (the leg's fill, if any, is the stream's to book; the
        # coverage repair then sizes from the broker's position, so a closed dead row is right in every case)
        if order and _cancel_state(order) == "dead":
            if not await _close_order_row(order_id, tid):
                out["row_update_error"] = "the order row could not be closed"
            if out["state"] == "dead" and not out["qty"]:
                out["state"] = "unknown"        # a dead order with no size: never guess the third
    except Exception as e:  # loud-ok: audited by the caller from the returned state; nothing sold
        logger.warning(f"breakout pp: cancelling the resting third {order_id} of trade {tid} raised: {e}")
        if out["state"] not in ("filled", "stop_filled"):
            out["state"] = "unknown"
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    # the step is NOT selling the third it marked for: hand a late settle back to the stream (findings 1 + 2)
    if out["cancel_sent"] and (out["state"] in ("open", "unknown") or out.get("row_update_error")):
        why = out.get("row_update_error") or f"cancel {out['state']} after the wait"
        out["marker_withdrawn"] = await _withdraw_planned_third_cancel(trade, order_id, why)
    return out


async def reprotect_after_unsold_third(trade: dict, dead_order_id: str | None = None) -> str | None:
    """After a +2R third the step marked for cancel but did not sell, the third's shares may have no stop (the
    cancelled OCO took its sibling stop with it, and the marker kept the trade stream from re-protecting). Converge from
    BROKER truth with the shared `_ensure_stop_coverage` (idempotent; a no-op when covered — while the limit really
    rests, its open order row nets the third out of the target and nothing is placed on top of its live stop leg), at
    the row's stop. `dead_order_id` (the row-update failure path): the dead limit's row is closed FIRST (one more
    compare-and-set) so `get_pending_exit_qty` stops counting a dead order as cover."""
    from agents.market_intelligence.broker.order_manager import _ensure_stop_coverage
    try:
        if dead_order_id and not await _close_order_row(dead_order_id, trade.get("id")):
            logger.error(f"breakout pp: the dead +2R limit {dead_order_id} of trade {trade.get('id')} still could not "
                         f"be closed — the coverage repair reads it as pending")
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
