"""Breakout v1 PAPER — the order step (phase 2 part A, build 2026-10-30; spec
`docs/design/breakout_v1_build_spec_2026-10-29.md` B4 + B5; owner of the rules
`docs/setups/consolidation_breakout.md`, his PAPER GO 2026-10-28 and rulings F1 / F2 2026-10-29).

WHAT IT DOES. One execution-owned job, every minute 09:35-15:55 ET mon-fri (`run_breakout_v1_entry_tick`), for each
name on LAST NIGHT's list (`mi_breakout_v1_list`, scan_date = the previous session):
  * the 5-minute opening range from today's 09:30-09:34 minute bars: ORH5 / ORL5, `level = max(ORH5, list level)`
    (`consolidation_breakout._entry_one`'s `orh5`); no bar at all in those five minutes = the named abstain
    `no_opening_range_minutes`;
  * F1 (RULED): the buy is only PLACED, and only KEPT live, while the volume so far (through the last completed
    minute) >= the list's volume bar (1.2 x the 50-day average) x the share of a day's volume normally done by that
    minute (`breakout_v1_volume_curve.CUM_SHARE`, ONE pooled curve for every stock). Before it permits there is no
    order; once an order is live and it stops permitting, the order is cancelled
    (`setup:breakout_volume_below_curve`) — terminal for the day (one trade per list name per day);
  * the order: a stop-limit buy at `level` (limit `stop_limit_buy_price(level)`), DAY, OTO with the protective stop at
    the day's low so far — through the single entry funnel `submit_trade_entry` with a spec builder that sizes like
    EP (the regime-keyed risk_pct x equity / (fill - stop), the 20% notional cap, the funnel's composite multiplier);
    the #500 price-aware submit applies (`order_manager.submit_entry`: a price already past `level` buys at
    latest x 1.002 within the 1.5x chase cap);
  * HIS STOP IS THE DAY'S LOW AT THE FILL: while the buy is unfilled, every new day's low re-prices the protective
    stop (cancel the whole order, then place it again with the new stop and a fresh `apollo_paper_breakout_v1_*` order
    id; the share count re-sized so the dollar risk placed never grows), and the buy is CANCELLED with
    `setup:stop_too_wide` once (level - day low) > ADR20 x level (`cb._finish_entry`'s width rule);
  * THE STOP AT THE FILL (his ruling 2026-10-29, "Go with rec"): the resting order's stop lags a flush inside the fill
    minute, so ONE MINUTE AFTER A FILL (the first tick whose last completed minute is the fill minute) the true low of
    the day through the fill minute is read: the 1 ADR20 width rule fails on it -> the whole position is sold at once
    (`setup:stop_too_wide_after_fill`, paged); else a true low below the placed stop LOWERS the stop leg to it (a
    price-only replace; never raised; the dollar risk may sit slightly above what was sized — recorded). Once per
    trade (the `FILL_STOP_CHECKED` marker, written after the step; a restart re-decides from broker truth);
  * unfilled at 15:55 ET -> cancelled (`window:breakout_unfilled_eod`). The 10:00 ET EP cleanup skips this
    strategy (`cancel_unfilled_entries(exclude_signal_types=...)`); the 16:05 ET EOD cleanup is the backstop.
  * every row is stamped `exit_rule = 'breakout_pp'` at insert (`order_manager.resolve_exit_rule_stamp`); the exit
    (the `pp` arm) is `broker/breakout_pp_rules.py` + `breakout_pp_exit.py`, run by the 15:45 / 16:45 / 19:02 jobs.

RESTART-SAFE. Every tick reconciles from the BROKER (the paper account's open orders, filtered to the
`apollo_paper_breakout_v1_` order-id family, and `get_order` on each row's entry order) and from today's trade rows —
never from memory. A filled (or partly filled) order is never cancelled or re-placed by this job. A planned cancel
writes a marker (`PLANNED_ENTRY_CANCEL`) naming the trade AND the order before it cancels, so the trade stream does
not record it as a broker kill (`trade_stream._handle_cancel_or_reject`), and so a tick after a crash mid-cancel can
finish what the crashed tick started. The only in-memory state is the per-day pre-flight pass and page / audit
de-duplication.

WHY IT CANNOT REACH REAL MONEY — four walls, mirrored from `lowcap_paper_entry.py` (#624), each test-pinned
(tests/test_breakout_v1_entry.py):
  1. It reads ONLY its own list table (`db.bv1_get_list` on `mi_breakout_v1_list`), never `mi_ep_alerts`.
  2. Every tick, before anything else, it requires the `breakout_v1` strategy row to be phase 'paper' AND to resolve
     (`resolve_account_mode_for_strategy`) to 'paper'; any other answer refuses the run and pages. It touches only
     trade rows whose account_mode is 'paper'.
  3. New entries call `submit_trade_entry(require_account_mode='paper')` — the funnel refuses a strategy that
     resolves anywhere else before any row or order.
  4. Every order carries `make_client_order_id('paper', 'breakout_v1', ticker)` (`order_manager.submit_entry` builds
     it from the PAPER row's account_mode + signal_type), so a fill can only match the paper book.

PRE-FLIGHT. Before the first order of an ET day the paper account must answer (not trading- or account-blocked).
TELEGRAM. Normal events (an order placed, re-priced, cancelled for a named reason, an abstain, a volume hold) send NO
Telegram — audit rows only. A FAILURE pages, paper-prefixed, once: the pre-flight, a refused phase, a crashed name, a
cancel the broker refused while the order should die, an unknown order in the family, a re-price that lost its row.
STOP SWITCH. The runtime toggle `breakout_v1_paper` (mi_safeguard_state, account_mode='global', default ON) and
`mi_strategies.enabled`: either OFF -> no new order, no re-price, and every resting unfilled breakout buy is
cancelled (`block:strategy_disabled`). LIVE_TRADING_ENABLED=false stops the job outright. `/pause` does NOT (the
manual halt is checked on the live path only — the same as the #624 lane).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timedelta

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.broker.breakout_v1_volume_curve import CUM_SHARE
from agents.market_intelligence.broker.entry_pipeline import (
    ACTION_AUTO_ENTER_FAILED,
    ACTION_AUTO_ENTERED,
    ACTION_BLOCKED,
    submit_trade_entry,
)
from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_ACCOUNT_MODE_MISMATCH,
    BLOCK_STRATEGY_DISABLED,
    SETUP_ACCOUNT_FETCH_FAILED,
    SETUP_BREAKOUT_VOLUME_BELOW_CURVE,
    SETUP_NO_OPENING_RANGE_MINUTES,
    SETUP_PRICE_EXCEEDS_CAP,
    SETUP_SIZE_TOO_SMALL,
    SETUP_STOP_TOO_WIDE,
    SETUP_STOP_TOO_WIDE_AFTER_FILL,
    SETUP_ZERO_RANGE,
    WINDOW_BREAKOUT_UNFILLED_EOD,
    WINDOW_DUPLICATE,
)
from agents.market_intelligence.constants import (
    LIVE_TRADING_ENABLED,
    MAX_POSITION_PCT,
    RISK_PCT,
    mode_prefix,
    resolve_account_mode_for_strategy,
)
from agents.market_intelligence.db import (
    BREAKOUT_V1_ACCOUNT_MODE,
    BREAKOUT_V1_PAPER_TOGGLE,
    BREAKOUT_V1_PAPER_TOGGLE_ENV,
    BREAKOUT_V1_STRATEGY_ID,
    bv1_get_list,
    get_pool,
    get_runtime_toggle,
    log_audit_event,
)
from shared.dates import _ET

logger = logging.getLogger(__name__)

ACCOUNT_MODE = BREAKOUT_V1_ACCOUNT_MODE   # the ONE permitted account — compared / passed, never used to widen
STRATEGY_ID = BREAKOUT_V1_STRATEGY_ID
TOGGLE = BREAKOUT_V1_PAPER_TOGGLE
TOGGLE_ENV = BREAKOUT_V1_PAPER_TOGGLE_ENV
STRATEGY_LABEL = "Breakout v1 (paper)"
# `alpaca_client.make_client_order_id(ACCOUNT_MODE, STRATEGY_ID, ticker)` = apollo_paper_breakout_v1_<TICKER>_<ms>.
COID_FAMILY_PREFIX = f"apollo_{ACCOUNT_MODE}_{STRATEGY_ID}_"

N_SESSION_MINUTES = 390
OR_MINUTES = 5                 # `orh5`: the opening range is minutes 0..4 (09:30..09:34 ET)
FIRST_MINUTE = OR_MINUTES      # the job's first tick: 09:35 ET (minute 5)
EOD_MINUTE = 385               # 15:55 ET: unfilled buys are cancelled; no new order from here
CANCEL_POLL_ATTEMPTS = 10      # x CANCEL_POLL_S: wait for the broker to confirm a cancel before re-placing
CANCEL_POLL_S = 0.5
STOP_EPS = 0.005               # a new low "prints" when it is below the placed stop by more than half a cent
SNAPSHOT_FAILS_BEFORE_PAGE = 3

PLANNED_ENTRY_CANCEL = "breakout_v1_planned_entry_cancel"   # the marker the trade stream reads

_FILLED_STATUSES = frozenset({"filled", "partially_filled"})
_ROWS_THAT_OWN_NO_ORDER = frozenset({"cancelled", "skipped"})   # an open order under such a row is an orphan
_DEAD_UNFILLED_STATUSES = frozenset({"canceled", "cancelled", "expired", "rejected", "done_for_day", "replaced"})

# ── in-memory, NEVER order state: the day's pre-flight pass and de-duplication of pages / audit rows ──
_preflight_ok_date: date | None = None
_paged: set[tuple] = set()
_noted: dict[tuple, str] = {}
_snapshot_fails = 0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Pure arithmetic (no I/O)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def session_open(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=_ET)


def market_minute(now_et: datetime) -> int:
    """Minutes since 09:30 ET on now's ET date (09:35:10 -> 5). Negative before the open."""
    now_et = now_et.astimezone(_ET)
    return int((now_et - session_open(now_et.date())).total_seconds() // 60)


def bars_by_minute(bars: list[dict], d: date, last_completed: int) -> dict[int, dict]:
    """{minute index 0..389: bar} for the regular-hours bars of `d` up to and including `last_completed`."""
    out: dict[int, dict] = {}
    open_dt = session_open(d)
    for b in bars or []:
        t = b.get("t_et") or b.get("timestamp")
        if t is None:
            continue
        m = int((t.astimezone(_ET) - open_dt).total_seconds() // 60)
        if 0 <= m <= min(last_completed, N_SESSION_MINUTES - 1):
            out[m] = b
    return out


def stop_from_low(low: float) -> float:
    """The protective stop at the day's low, on the cent at or BELOW it (a cent above would sit inside the range)."""
    return math.floor(round(float(low) * 100, 6)) / 100.0


def f1_permits(cum_volume: float, vol_bar: float, last_completed: int) -> tuple[bool, float]:
    """F1 (his ruling 2026-10-29): volume so far >= 1.2x the stock's normal volume BY THAT MINUTE.
    `vol_bar` is the list's 1.2 x the 50-day average volume, so the bar is vol_bar x the curve's share at the last
    completed minute. -> (permits, the volume the minute needs)."""
    m = max(0, min(int(last_completed), N_SESSION_MINUTES - 1))
    need = float(vol_bar) * CUM_SHARE[m]
    return bool(float(cum_volume) >= need), need


def evaluate(mins: dict[int, dict], *, list_level: float, adr20: float | None, vol_bar: float,
             last_completed: int) -> dict:
    """The name's state at this tick from today's completed minute bars. PURE.

    status: 'wait' (nothing to judge yet) | 'abstain' (terminal for the day: no opening range, zero range, the stop
    too wide) | 'ok' (a buy may rest — subject to `f1_ok`). Carries level / ORH5 / ORL5 / open / day low / stop /
    width / the F1 numbers."""
    st: dict = {"status": "wait", "reason": None, "level": None, "orh5": None, "orl5": None, "open": None,
                "day_low": None, "stop": None, "width": None, "cum_volume": None, "need_volume": None,
                "f1_ok": False, "last_completed": last_completed}
    if not mins:
        st["reason"] = "no_minute_bars_yet"
        return st
    in_range = {m: b for m, b in mins.items() if m < OR_MINUTES}
    if not in_range:
        if any(m >= OR_MINUTES for m in mins):
            st.update(status="abstain", reason=f"{SETUP_NO_OPENING_RANGE_MINUTES}: no trade 09:30-09:34 ET")
        else:
            st["reason"] = "no_minute_bars_yet"
        return st
    if last_completed < OR_MINUTES and (OR_MINUTES - 1) not in in_range:
        # 09:35: the 09:34 bar may not be published yet — wait one minute for the range to settle
        st["reason"] = "opening_range_not_settled"
        return st
    orh5 = max(float(b["high"]) for b in in_range.values())
    orl5 = min(float(b["low"]) for b in in_range.values())
    level = max(orh5, float(list_level))
    day_low = min(float(b["low"]) for b in mins.values())
    stop = stop_from_low(day_low)
    cum = float(sum(float(b.get("volume") or 0) for b in mins.values()))
    ok, need = f1_permits(cum, vol_bar, last_completed)
    st.update(level=level, orh5=orh5, orl5=orl5, open=float(in_range[min(in_range)]["open"]), day_low=day_low,
              stop=stop, cum_volume=cum, need_volume=need, f1_ok=ok)
    if stop >= level:
        st.update(status="abstain", reason=f"{SETUP_ZERO_RANGE}: stop ${stop:.2f} >= level ${level:.2f}")
        return st
    width = (level - stop) / level
    st["width"] = width
    if adr20 is None or not math.isfinite(float(adr20)) or float(adr20) <= 0:
        st.update(status="abstain", reason=f"{SETUP_STOP_TOO_WIDE}: ADR20 unknown on the list row")
        return st
    if width > float(adr20):
        st.update(status="abstain", reason=(f"{SETUP_STOP_TOO_WIDE}: level ${level:.2f} - day low ${stop:.2f} = "
                                            f"{width:.2%} > ADR20 {float(adr20):.2%}"))
        return st
    st["status"] = "ok"
    return st


def resize_for_new_stop(old_shares: float, risk_dollars: float | None, level: float, new_stop: float) -> int:
    """Shares after the stop moves DOWN to a new low: the dollar risk placed never grows and the share count never
    rises (so the 20% notional cap the first sizing applied still holds). PURE."""
    rps = round(float(level) - float(new_stop), 6)      # prices on the cent: no 0.39999.. floor-off-by-one
    old = int(float(old_shares or 0))
    if rps <= 0 or old <= 0:
        return 0
    budget = float(risk_dollars) if risk_dollars else old * rps
    return max(0, min(old, math.floor(budget / rps)))


def size_breakout(equity: float, risk_pct: float, entry: float, stop: float) -> dict:
    """EP's sizing arithmetic with breakout's stop (`order_manager.prepare_orb_order`'s risk math, PURE):
    shares = floor(equity x risk_pct / (entry - stop)), then the 20%-of-equity notional cap."""
    risk_dollars = equity * risk_pct
    rps = entry - stop
    shares = math.floor(risk_dollars / rps) if rps > 0 else 0
    shares_before_cap = shares
    max_position = equity * MAX_POSITION_PCT
    if shares * entry > max_position:
        shares = math.floor(max_position / entry)
    return {"risk_dollars": risk_dollars, "risk_per_share": rps, "shares": shares,
            "shares_before_cap": shares_before_cap, "max_position": max_position,
            "risk_dollars_actual": round(shares * rps, 2)}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The spec builder (sizes like EP)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def width_at_expected_fill(ticker: str, level: float, stop: float, adr20: float | None) -> str | None:
    """`cb._finish_entry`'s width rule at the fill this order would get: the level (a resting stop-limit), or — when
    the price is already past the level — the #500 fallback's limit, latest x 1.002. -> the skip reason, or None."""
    fill = float(level)
    try:
        latest = await alpaca.get_latest_trade(ticker)
        px = float((latest or {}).get("price") or 0)
        if px > fill:
            fill = round(px * 1.002, 2)
    except Exception as e:  # loud-ok: no latest trade -> judge the width at the level (the resting order's fill)
        logger.warning(f"breakout v1 {ticker}: latest trade unreadable for the width check ({e}) — using the level")
    if adr20 is None or not float(adr20) > 0:
        return f"{SETUP_STOP_TOO_WIDE}: ADR20 unknown on the list row"
    width = (fill - float(stop)) / fill
    if width > float(adr20):
        return (f"{SETUP_STOP_TOO_WIDE}: fill ${fill:.2f} - stop ${float(stop):.2f} = {width:.2%} "
                f"> ADR20 {float(adr20):.2%}")
    return None


async def prepare_breakout_order(alert: dict, orb_bar: dict, regime_record: dict | None, account_mode: str,
                                 *, today: date, adr20: float | None) -> tuple[dict | None, str | None]:
    """The order spec for `submit_trade_entry`. `orb_bar` is this job's own range: high = ORH5, low = ORL5, plus
    `level` (the trigger) and `stop` (the day's low so far). Abstains (named): the stop at/above the level; the stop
    wider than ADR20 at the expected fill (the level, or the #500 fallback's latest x 1.002 when the price is already
    past it); zero shares. Sizing is EP's: the regime-keyed risk_pct (`order_manager._resolve_regime_risk_pct`, the
    one resolver every sizing site uses) x the paper equity / (level - stop), then the 20% notional cap."""
    from agents.market_intelligence.broker.order_manager import (
        _log_notional_cap_truncation,
        _resolve_regime_risk_pct,
        stop_limit_buy_price,
    )
    ticker = alert["ticker"]
    level, stop = float(orb_bar["level"]), float(orb_bar["stop"])
    if stop >= level:
        return None, f"{SETUP_ZERO_RANGE}: stop ${stop:.2f} >= level ${level:.2f}"
    wide = await width_at_expected_fill(ticker, level, stop, adr20)
    if wide:
        return None, wide
    try:
        account = await alpaca.get_account(account_mode=account_mode)
        equity = float(account["equity"])
    except Exception as e:
        logger.error(f"breakout v1 {ticker}: cannot read the paper equity, no order: {e}")
        return None, f"{SETUP_ACCOUNT_FETCH_FAILED}: {e}"
    risk_pct = await _resolve_regime_risk_pct(regime_record, today, account_mode, base_pct=RISK_PCT)
    z = size_breakout(equity, risk_pct, level, stop)
    if z["shares_before_cap"] <= 0:
        return None, (f"{SETUP_SIZE_TOO_SMALL}: ${z['risk_dollars']:.0f} risk / ${z['risk_per_share']:.2f} "
                      f"per-share < 1 share")
    if z["shares"] <= 0:
        return None, f"{SETUP_PRICE_EXCEEDS_CAP}: ${level:.2f}/share > ${z['max_position']:.0f} (20% of ${equity:.0f})"
    if z["shares"] != z["shares_before_cap"]:
        await _log_notional_cap_truncation(
            ticker=ticker, alert_date=today, account_mode=account_mode, equity=equity,
            max_position=z["max_position"], entry_price=level, shares_before_cap=z["shares_before_cap"],
            shares_after_cap=z["shares"], risk_dollars_actual=z["risk_dollars_actual"],
            risk_dollars_intended=z["risk_dollars"])
    return {
        "ticker": ticker,
        "entry_price": level,
        "limit_price": stop_limit_buy_price(level),
        "stop_loss_price": stop,
        "shares": z["shares"],
        "risk_dollars": round(z["risk_dollars"], 2),
        "risk_dollars_actual": z["risk_dollars_actual"],
        "risk_per_share": round(z["risk_per_share"], 2),
        "position_size": round(z["shares"] * level, 2),
        "equity": equity,
        # submit_entry reads the TRIGGER from orb_high (the stop-limit's stop price) — the level, not raw ORH5
        "orb_high": level,
        "orb_low": float(orb_bar["low"]),
        "atr_14": None,
        "ep_score": None,
        "catalyst_quality": None,
        "gap_pct": alert.get("gap_pct"),
        "regime": regime_record.get("regime") if regime_record else None,
    }, None


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Walls, pre-flight, pages
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _page_once(key: tuple, text: str) -> None:
    """A FAILURE page, paper-prefixed, once per key (in-memory: a restart may page again). Never raises."""
    if key in _paged:
        return
    _paged.add(key)
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(f"{mode_prefix(ACCOUNT_MODE)}{text}")
    except Exception as e:  # loud-ok: the audit row written by the caller is the durable record
        logger.error(f"breakout v1 page failed: {e}")


async def _note(today: date, ticker: str, state: str, summary: str, detail: dict | None = None) -> None:
    """One audit row per (name, state) change in a day — a volume hold is not re-recorded every minute."""
    key = (today, ticker)
    if _noted.get(key) == state:
        return
    _noted[key] = state
    await log_audit_event("breakout_v1_entry_hold", f"{ticker}: {summary}",
                          json.dumps(dict(detail or {}, ticker=ticker, state=state), default=str))


async def paper_account_preflight(today: date) -> bool:
    """True when the paper account answered today (cached per ET day after the first success)."""
    global _preflight_ok_date
    if _preflight_ok_date == today:
        return True
    try:
        acct = await alpaca.get_account(account_mode=ACCOUNT_MODE)
        if acct.get("trading_blocked") or acct.get("account_blocked"):
            raise RuntimeError(f"paper account blocked (trading_blocked={acct.get('trading_blocked')}, "
                               f"account_blocked={acct.get('account_blocked')})")
        if not acct.get("equity"):
            raise RuntimeError(f"paper account returned no equity ({acct.get('equity')!r})")
    except Exception as e:  # loud-ok: logged + audited + paged below; the tick places nothing
        logger.error(f"breakout v1 pre-flight FAILED — no breakout orders: {e}")
        await log_audit_event("breakout_v1_preflight_failed",
                              f"{today.isoformat()}: {type(e).__name__}: {str(e)[:300]}")
        await _page_once(("preflight", today), f"🚨 Breakout v1: the PAPER account did not answer the pre-flight "
                                               f"check — no breakout orders placed ({type(e).__name__}: {str(e)[:160]})")
        return False
    _preflight_ok_date = today
    await log_audit_event("breakout_v1_preflight_ok",
                          f"{today.isoformat()}: paper account answered (equity ${float(acct['equity']):,.0f})")
    return True


_SWITCHED_OFF_WHY = "strategy row missing or disabled"


async def _strategy_state(today: date) -> tuple[bool, str]:
    """(may order, why not). Wall 2: the strategy row must be enabled, phase 'paper', and resolve to 'paper'. A
    missing / disabled row is the switch OFF (quiet); any other phase is REFUSED (audit + page)."""
    from agents.market_intelligence.strategies.registry import get_strategy
    strategy = await get_strategy(STRATEGY_ID)
    if strategy is None or not strategy.enabled:
        return False, _SWITCHED_OFF_WHY
    try:
        mode = resolve_account_mode_for_strategy(strategy) if strategy.phase == "paper" else None  # mode-ok: breakout v1's own phase guard — refuses anything but paper
    except Exception:  # loud-ok: an unresolvable phase is refused below
        mode = None
    if mode != ACCOUNT_MODE:
        msg = (f"{STRATEGY_ID} phase={strategy.phase!r} resolves to {mode!r} — breakout v1 orders on PAPER only; "
               f"refused")
        await log_audit_event("breakout_v1_refused", f"{today.isoformat()}: {msg}")
        await _page_once(("refused", today), f"🚨 Breakout v1 refused to order: {msg}")
        return False, msg
    return True, ""


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The planned cancel + its marker
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _record_planned_cancel(trade_id: int | None, ticker: str, order_id: str, intent: str, reason: str) -> None:
    """The marker the trade stream reads (`planned_entry_cancel_marked`). Never raises: a missing marker only means
    the cancel is recorded and paged by the stream as a broker kill (the row turns 'cancelled'; nothing re-places)."""
    try:
        await log_audit_event(
            PLANNED_ENTRY_CANCEL,
            f"{ticker}: cancelling breakout v1 buy {str(order_id)[:8]} on purpose ({intent}: {reason})",
            json.dumps({"trade_id": trade_id, "ticker": ticker, "order_id": str(order_id), "intent": intent,
                        "reason": reason, "account_mode": ACCOUNT_MODE}))
    except Exception as e:  # loud-ok: logged; the stream then records the cancel as before
        logger.warning(f"breakout v1 planned-cancel marker write failed for {ticker}: {e}")


async def planned_entry_cancel_marked(trade_id, order_id: str) -> bool:
    """Did THIS job cancel this exact order of this trade on purpose? True only on a `PLANNED_ENTRY_CANCEL` row naming
    both (the last day). Matched in Python (detail is TEXT). Any failure -> False (the stream then records + pages)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT event_type, detail FROM mi_audit_log WHERE event_type = $1 "
                "AND created_at > NOW() - INTERVAL '1 day' ORDER BY created_at DESC",
                PLANNED_ENTRY_CANCEL)
        for row in rows or []:
            if row["event_type"] != PLANNED_ENTRY_CANCEL:
                continue
            try:
                d = json.loads(row["detail"])
            except Exception:  # loud-ok: one malformed row is skipped, never the check
                continue
            if str(d.get("trade_id")) == str(trade_id) and str(d.get("order_id")) == str(order_id):
                return True
    except Exception as e:  # loud-ok: fail-safe — NOT planned, so the stream still records + pages
        logger.warning(f"breakout v1 planned-cancel marker read failed ({e}) — treated as NOT planned")
    return False


def _classify(order: dict | None) -> str:
    """'filled' (any fill at all) | 'dead' (terminal, nothing filled) | 'open' | 'unknown' (unreadable)."""
    if not order:
        return "unknown"
    if float(order.get("filled_qty") or 0) > 0 or order.get("status") in _FILLED_STATUSES:
        return "filled"
    if order.get("status") in _DEAD_UNFILLED_STATUSES:
        return "dead"
    return "open"


async def _cancel_and_confirm(trade_id: int | None, ticker: str, order_id: str, intent: str, reason: str) -> str:
    """Marker, cancel, then wait for the broker to confirm. -> 'dead' (cancelled, nothing filled: safe to settle or
    re-place) | 'filled' (it filled first — the stream owns it; never re-placed) | 'open' (still live after the
    wait or the cancel was refused — paged) | 'unknown'."""
    await _record_planned_cancel(trade_id, ticker, order_id, intent, reason)
    accepted = await alpaca.cancel_order(order_id, account_mode=ACCOUNT_MODE)
    state = "unknown"
    for i in range(CANCEL_POLL_ATTEMPTS):
        state = _classify(await alpaca.get_order(order_id, account_mode=ACCOUNT_MODE))
        if state in ("dead", "filled"):
            break
        if i < CANCEL_POLL_ATTEMPTS - 1:
            await asyncio.sleep(CANCEL_POLL_S)
    if state == "filled":
        await log_audit_event("breakout_v1_cancel_raced_fill",
                              f"{ticker}: order {order_id[:8]} filled before the {intent} cancel — the fill stands")
        await _page_once(("filled_on_cancel", order_id),
                         f"⚠️ Breakout v1 *{ticker}*: the buy filled while it was being cancelled ({intent}: "
                         f"{reason[:120]}) — the position stands with its stop; check the book")
    elif state != "dead":
        await log_audit_event("breakout_v1_cancel_failed",
                              f"{ticker}: order {order_id[:8]} {intent} cancel not confirmed "
                              f"(accepted={accepted}, state={state}) — retried next minute",
                              json.dumps({"trade_id": trade_id, "order_id": order_id, "reason": reason}))
        await _page_once(("cancel_failed", order_id),
                         f"🚨 Breakout v1 *{ticker}*: the broker did not confirm the cancel of the buy "
                         f"({intent}: {reason[:120]}) — it may still be live; retrying every minute")
    return state


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Row writes (CAS on the row's own status + entry order — a racing fill or stream write wins)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _mark_cancelled(trade_id: int, from_status: str, from_order_id: str | None, reason: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        got = await conn.fetchval(
            """
            UPDATE mi_live_trades SET status = 'cancelled', skip_reason = $4
            WHERE id = $1 AND status = $2 AND entry_order_id IS NOT DISTINCT FROM $3
              AND signal_type = $5 AND account_mode = $6
            RETURNING id
            """,
            trade_id, from_status, from_order_id, reason, STRATEGY_ID, ACCOUNT_MODE)
    return got is not None


async def _set_unsubmitted_order(trade_id: int, from_status: str, from_order_id: str | None, *, stop: float,
                                 shares: int, level: float) -> bool:
    """Put the row back to 'confirmed' with no order on it and the NEW stop / size, ready for `submit_entry`. Used to
    re-price (from 'order_placed' + the just-cancelled order) and to finish a tick that crashed before submitting
    (from 'confirmed' + no order). 'confirmed' still counts against the paper cap (OPEN_POSITION_STATUSES)."""
    rps = level - stop
    pool = await get_pool()
    async with pool.acquire() as conn:
        got = await conn.fetchval(
            """
            UPDATE mi_live_trades SET status = 'confirmed', entry_order_id = NULL, stop_order_id = NULL,
                   stop_price = $4, hard_stop = $4, entry_shares = $5, position_size = $6,
                   risk_dollars_actual = $7, skip_reason = NULL
            WHERE id = $1 AND status = $2 AND entry_order_id IS NOT DISTINCT FROM $3
              AND signal_type = $8 AND account_mode = $9
            RETURNING id
            """,
            trade_id, from_status, from_order_id, float(stop), float(shares), round(shares * level, 2),
            round(shares * rps, 2), STRATEGY_ID, ACCOUNT_MODE)
    return got is not None


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Per-name steps
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _enter(today: date, lrow: dict, st: dict, regime_record: dict | None) -> dict:
    """A name with no row today whose state permits a buy: through the single funnel, bound to paper."""
    ticker = lrow["ticker"]
    orb = {"open": st["open"], "high": st["orh5"], "low": st["orl5"], "level": st["level"], "stop": st["stop"]}

    async def _bar(_t, _d, _label, _orb=orb):     # the funnel's step 3: this job's own 5-minute range
        return dict(_orb)

    async def _spec(alert_ctx, orb_bar, regime, account_mode, _today=today, _adr=lrow.get("adr20")):
        return await prepare_breakout_order(alert_ctx, orb_bar, regime, account_mode, today=_today, adr20=_adr)

    close = lrow.get("close")
    gap = ((st["open"] / float(close) - 1.0) * 100.0) if close else None
    alert = {"ticker": ticker, "alert_date": today, "ep_score": None, "catalyst_quality": None, "gap_pct": gap}
    r = await submit_trade_entry(
        alert_context=alert,
        spec_builder=_spec,
        regime_record=regime_record,
        strategy_label=STRATEGY_LABEL,
        signal_type=STRATEGY_ID,
        today=today,
        atr_14=None,
        success_title="Breakout paper order placed",
        fade_midpoint_ratio=None,                 # no fade guard: the level and the day-low stop are the rule
        rt_gap_floor_pct=None,                    # EP's gap floor is not a breakout rule
        aggregate_skips=True,                     # skips are audit rows; infra:* still pages
        require_account_mode=ACCOUNT_MODE,        # wall 3
        page_cap_plus_one=False,                  # no live CAP+1 manual-trade prompt
        bar_fetcher=_bar,
    )
    if r.get("action") == ACTION_BLOCKED and str(r.get("reason", "")).startswith(BLOCK_ACCOUNT_MODE_MISMATCH):
        await _page_once(("mismatch", today, ticker),
                         f"🚨 *{ticker}* breakout v1 order REFUSED by the entry funnel — {r.get('reason')}")
    if r.get("reason") != WINDOW_DUPLICATE:
        await log_audit_event(
            "breakout_v1_entry_order",
            f"{ticker} → {r.get('action')}" + (f" ({r.get('reason')})" if r.get("reason") else "")
            + (f" trade_id={r.get('trade_id')}" if r.get("trade_id") else "")
            + f" level=${st['level']:.2f} stop=${st['stop']:.2f} vol {st['cum_volume']:,.0f} >= "
              f"{st['need_volume']:,.0f}",
            json.dumps({k: st[k] for k in ("level", "orh5", "orl5", "stop", "width", "cum_volume", "need_volume",
                                           "last_completed")}, default=str))
    return r


async def _settle_dead_order(row: dict, lrow: dict | None, st: dict | None, m: int) -> str:
    """The row's order is cancelled at the broker with nothing filled and THIS job cancelled it (marker): finish the
    planned step — re-place with the current stop, or settle the row cancelled with the reason that applies now."""
    reason = _terminal_reason(st, m)
    if reason is None:
        if st is None or st["status"] != "ok":
            return "wait"                  # cannot judge this minute (no bars) — the next tick finishes it
        if not await paper_account_preflight(row["alert_date"]):
            return "wait"
        return await _replace(row, st, (lrow or {}).get("adr20"), from_status="order_placed", from_order_id=row["entry_order_id"])
    ok = await _mark_cancelled(row["id"], "order_placed", row["entry_order_id"], reason)
    await log_audit_event("breakout_v1_entry_cancelled", f"{row['ticker']}: {reason}" + ("" if ok else " (row moved)"))
    return "cancelled"


def _terminal_reason(st: dict | None, m: int) -> str | None:
    """The named reason a resting / about-to-rest buy must die now, or None."""
    if m >= EOD_MINUTE:
        return f"{WINDOW_BREAKOUT_UNFILLED_EOD}: unfilled at 15:55 ET"
    if st is None or st["status"] == "wait":
        return None
    if st["status"] == "abstain":
        return st["reason"]
    if not st["f1_ok"]:
        return (f"{SETUP_BREAKOUT_VOLUME_BELOW_CURVE}: {st['cum_volume']:,.0f} shares by minute "
                f"{st['last_completed']} < {st['need_volume']:,.0f} needed")
    return None


async def _replace(row: dict, st: dict, adr20: float | None, *, from_status: str, from_order_id: str | None) -> str:
    """Put a new order on the row at the CURRENT stop (re-sized so the dollar risk placed never grows), through
    `order_manager.submit_entry` — the same #500 price-aware submit, COID builder and order-row writes as every
    entry."""
    from agents.market_intelligence.broker.order_manager import submit_entry
    ticker = row["ticker"]
    level = float(row["orb_high"])
    shares = resize_for_new_stop(row["entry_shares"], row["risk_dollars"], level, st["stop"])
    wide = await width_at_expected_fill(ticker, level, st["stop"], adr20)
    if wide or shares < 1:
        reason = wide or f"{SETUP_SIZE_TOO_SMALL}: re-sized to the new stop ${st['stop']:.2f} — < 1 share"
        await _mark_cancelled(row["id"], from_status, from_order_id, reason)
        await log_audit_event("breakout_v1_entry_cancelled", f"{ticker}: {reason}")
        return "cancelled"
    if not await _set_unsubmitted_order(row["id"], from_status, from_order_id, stop=st["stop"], shares=shares,
                                        level=level):
        await log_audit_event("breakout_v1_reprice_lost",
                              f"{ticker}: the row moved before the re-price (from {from_status}) — nothing placed")
        await _page_once(("reprice_lost", row["id"]),
                         f"⚠️ Breakout v1 *{ticker}*: the buy was cancelled to move its stop but the trade row "
                         f"changed underneath — no new buy placed today")
        return "lost"
    order = await submit_entry(row["id"])
    await log_audit_event(
        "breakout_v1_stop_repriced" if from_order_id else "breakout_v1_entry_resubmitted",
        f"{ticker}: stop ${float(row['stop_price'] or 0):.2f} → ${st['stop']:.2f}, shares "
        f"{int(float(row['entry_shares'] or 0))} → {shares}, level ${level:.2f} — "
        + (f"order {order['id'][:8]}" if order else "submit failed (row settled by submit_entry)"),
        json.dumps({"trade_id": row["id"], "old_order_id": from_order_id, "new_order_id": (order or {}).get("id"),
                    "old_stop": row["stop_price"], "new_stop": st["stop"], "shares": shares}, default=str))
    return "repriced" if order else "submit_failed"


async def _manage(row: dict, lrow: dict | None, st: dict | None, m: int, open_by_id: dict) -> str:
    """A breakout row already exists today. Never touches a filled order; settles / cancels / re-prices an unfilled
    one from broker truth."""
    ticker = row["ticker"]
    status, oid = row["status"], row.get("entry_order_id")
    if status == "confirmed" and not oid:
        # a tick that crashed between the row write and the submit (or between a re-price's cancel and its submit)
        reason = _terminal_reason(st, m)
        if reason is not None:
            await _mark_cancelled(row["id"], "confirmed", None, reason)
            await log_audit_event("breakout_v1_entry_cancelled", f"{ticker}: {reason} (never submitted)")
            return "cancelled"
        if st is None or st["status"] != "ok" or not await paper_account_preflight(row["alert_date"]):
            return "wait"
        return await _replace(row, st, (lrow or {}).get("adr20"), from_status="confirmed", from_order_id=None)
    if status != "order_placed" or not oid:
        return "untouched"                 # filled / filling / closed / cancelled / skipped / submitting: not ours now
    order = open_by_id.get(oid) or await alpaca.get_order(oid, account_mode=ACCOUNT_MODE)
    state = _classify(order)
    if state in ("filled", "unknown"):
        return state                       # the stream owns a fill; an unreadable order is left for the next tick
    if state == "dead":
        if await planned_entry_cancel_marked(row["id"], oid):
            return await _settle_dead_order(row, lrow, st, m)
        return "dead_unplanned"            # a broker kill: the trade stream / check_fills record it
    # open: decide
    reason = _terminal_reason(st, m)
    if reason is not None:
        res = await _cancel_and_confirm(row["id"], ticker, oid, "cancel", reason)
        if res == "dead":
            ok = await _mark_cancelled(row["id"], "order_placed", oid, reason)
            await log_audit_event("breakout_v1_entry_cancelled", f"{ticker}: {reason}" + ("" if ok else " (row moved)"))
            return "cancelled"
        return res
    if st is None or st["status"] != "ok":
        return "held"
    placed_stop = float(row["stop_price"]) if row.get("stop_price") is not None else None
    if placed_stop is not None and st["stop"] < placed_stop - STOP_EPS:
        if not await paper_account_preflight(row["alert_date"]):
            return "held"
        res = await _cancel_and_confirm(row["id"], ticker, oid, "reprice",
                                        f"new day low ${st['day_low']:.2f} (stop ${placed_stop:.2f} → ${st['stop']:.2f})")
        if res == "dead":
            return await _replace(row, st, (lrow or {}).get("adr20"), from_status="order_placed", from_order_id=oid)
        return res
    return "resting"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6b. THE STOP AT THE FILL (his ruling 2026-10-29, "Go with rec")
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The resting buy carries the stop of the last tick (read through the last COMPLETED minute), so a flush inside the fill
# minute — or in the minute or two before it — is not in the stop. ONE MINUTE AFTER A FILL (the first tick whose last
# completed minute is the fill minute) the TRUE low of the day through the fill minute is read from the minute bars:
#   * `cb._finish_entry`'s 1 ADR20 width rule fails on it ((fill - true low) > ADR20 x fill) -> the whole position is
#     sold at once (paper, market: `order_manager.execute_full_exit`, reason `setup:stop_too_wide_after_fill`), paged;
#   * otherwise, the true low BELOW the placed stop -> the protective stop is LOWERED to it (an atomic price-only replace
#     of the stop leg; never raised; the dollar risk may then sit slightly above what was sized — recorded on the row's
#     `risk_dollars_actual` and in the audit row beside the sized `risk_dollars`);
#   * otherwise nothing changes.
# Exactly once per trade: decided from the broker and the row, then the marker `FILL_STOP_CHECKED` (an audit row naming
# the trade) is written AFTER the step completed, so a tick after a crash re-decides from broker truth (a stop already at
# the new price is only recorded; a sale already pending or a row already closed is only marked). Never touches a row
# that is not a 'breakout_v1' PAPER row (the tick only reads its own paper rows; every write below is guarded again).
FILL_STOP_CHECKED = "breakout_v1_fill_stop_checked"
FILL_BAR_WAIT_MINUTES = 3        # the fill minute's bar not published yet: wait up to 3 minutes, then judge without it
STOP_LOWER_VERIFY_POLLS = 12     # x STOP_LOWER_VERIFY_S: the successor stop must be CONFIRMED live before the row says so
STOP_LOWER_VERIFY_S = 0.25
_fill_checked: set[int] = set()  # in-memory cache of a marker already read (never order state; a restart re-reads it)


def _parse_ts(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def fill_minute_of(filled_at: datetime | None, d: date) -> int | None:
    """Minutes since 09:30 ET of the fill on `d` (the minute bar it printed in); None outside that session."""
    if filled_at is None or filled_at.tzinfo is None:
        return None
    t = filled_at.astimezone(_ET)
    if t.date() != d:
        return None
    m = int((t - session_open(d)).total_seconds() // 60)
    return m if 0 <= m < N_SESSION_MINUTES else None


def stop_at_fill_decision(*, fill: float, true_low: float, adr20: float | None, placed_stop: float) -> dict:
    """His ruling 2026-10-29, PURE. -> {"action": 'sell_all' | 'lower' | 'keep', "fill", "true_low", "width",
    "new_stop", "reason"}. `width` = (fill - true low) / fill, the `cb._finish_entry` rule on the RAW low (the walk's
    stop); 'sell_all' when it exceeds ADR20. Else 'lower' when the stop on the cent at or below the true low
    (`stop_from_low`) is below the placed stop by more than half a cent; else 'keep'. Never raises a stop."""
    fill, true_low, placed_stop = float(fill), float(true_low), float(placed_stop)
    width = (fill - true_low) / fill
    out = {"action": "keep", "fill": fill, "true_low": true_low, "width": width, "new_stop": None, "reason": None}
    if adr20 is None or not math.isfinite(float(adr20)) or float(adr20) <= 0:
        out["reason"] = "ADR20 unknown on the list row — the width rule cannot be judged; the stop is kept"
        return out
    if width > float(adr20):
        out.update(action="sell_all", reason=(
            f"{SETUP_STOP_TOO_WIDE_AFTER_FILL}: fill ${fill:.2f} - true low ${true_low:.2f} = {width:.2%} "
            f"> ADR20 {float(adr20):.2%}"))
        return out
    new_stop = stop_from_low(true_low)
    if new_stop < placed_stop - STOP_EPS:
        out.update(action="lower", new_stop=new_stop,
                   reason=f"true low ${true_low:.2f} under the placed stop ${placed_stop:.2f}")
    return out


async def _mark_fill_checked(row: dict, decision: str, summary: str, detail: dict | None = None) -> None:
    """The once-per-trade marker, written AFTER the step completed. Never raises (a lost marker only means the next
    tick re-decides from broker truth, which is idempotent)."""
    try:
        await log_audit_event(
            FILL_STOP_CHECKED, f"{row['ticker']} #{row['id']}: {summary}",
            json.dumps(dict(detail or {}, trade_id=row["id"], ticker=row["ticker"], decision=decision,
                            account_mode=ACCOUNT_MODE), default=str))
        _fill_checked.add(int(row["id"]))
    except Exception as e:  # loud-ok: logged; the next tick re-decides from broker truth
        logger.warning(f"breakout v1 {row['ticker']}: fill-stop marker write failed: {e}")


async def fill_stop_checked(trade_id) -> bool:
    """Has the stop at the fill already been decided for this trade? A `FILL_STOP_CHECKED` row naming it (the last 3
    days; matched in Python, detail is TEXT). A read failure -> False: the step re-decides from broker truth."""
    if int(trade_id) in _fill_checked:
        return True
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT event_type, detail FROM mi_audit_log WHERE event_type = $1 "
                "AND created_at > NOW() - INTERVAL '3 days' ORDER BY created_at DESC",
                FILL_STOP_CHECKED)
        for r in rows or []:
            try:
                d = json.loads(r["detail"])
            except Exception:  # loud-ok: one malformed row is skipped, never the check
                continue
            if r["event_type"] == FILL_STOP_CHECKED and str(d.get("trade_id")) == str(trade_id):
                _fill_checked.add(int(trade_id))
                return True
    except Exception as e:  # loud-ok: re-deciding is idempotent (broker truth), so False is the safe answer
        logger.warning(f"breakout v1: fill-stop marker read failed ({e}) — re-deciding from broker truth")
    return False


async def _record_stop_lowered(trade_id: int, *, stop_order_id: str, new_stop: float, risk_dollars_actual: float) -> bool:
    """The row follows the broker AFTER the lowered stop is confirmed live: the leg pointer, `stop_price` and
    `hard_stop` (his "day's low at the fill" — the pp exit's R, the +2R target and the stall cut read it) and the dollar
    risk now carried. Compare-and-set: only a FILLED 'breakout_v1' PAPER row with no third sold, and never a raise."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        got = await conn.fetchval(
            """
            UPDATE mi_live_trades SET stop_order_id = $2, stop_price = $3, hard_stop = $3, risk_dollars_actual = $4
            WHERE id = $1 AND status = 'filled' AND signal_type = $5 AND account_mode = $6
              AND COALESCE(partial_taken, FALSE) = FALSE AND (stop_price IS NULL OR stop_price >= $3)
            RETURNING id
            """,
            trade_id, str(stop_order_id), float(new_stop), float(risk_dollars_actual), STRATEGY_ID, ACCOUNT_MODE)
    return got is not None


async def _insert_stop_leg_row(trade_id: int, order: dict, ticker: str, qty: float, stop: float) -> None:
    """The successor stop in `mi_live_orders` (purpose 'stop_loss') so its fill routes to the stop-fill handler —
    the same row `scan_breakeven_arms` writes for its price-only replace."""
    from agents.market_intelligence.db import _jsonb_param
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_live_orders
                (trade_id, alpaca_order_id, ticker, side, order_type,
                 qty, stop_price, status, raw_response, purpose, exit_reason)
            VALUES ($1, $2, $3, 'sell', 'stop', $4, $5, $6, $7::jsonb,
                    'stop_loss', 'stop_hit')
            ON CONFLICT (alpaca_order_id) DO NOTHING
        """, trade_id, order["id"], ticker, float(qty), float(stop), order.get("status", "new"), _jsonb_param(order))


async def _row_state(trade_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchrow(
            "SELECT id, status, remaining_shares, partial_taken, stop_order_id, stop_price FROM mi_live_trades "
            "WHERE id = $1 AND signal_type = $2 AND account_mode = $3", trade_id, STRATEGY_ID, ACCOUNT_MODE)
    return dict(r) if r else None


async def _adopt_replaced_successor(row: dict, shares: float, replaced_id: str, detail: dict) -> str:
    """The row's stop leg reads 'replaced' (Alpaca accepted our lower, then the tick died before the row followed, or
    the replace call raised after the broker took it): the successor is the ONE live sell-stop for the ticker in THIS
    strategy's order-id family (the replace carries `make_client_order_id(..., STRATEGY_ID, ...)`) covering the shares.
    Exactly one -> the row's pointer is moved to it (a pure DB write; nothing placed or cancelled) and the next tick
    records it at its price; 0 or >1, or the book unreadable -> nothing guessed, audited, retried next minute."""
    from agents.market_intelligence.broker import order_manager as om
    ticker, tid = row["ticker"], row["id"]
    err = ""
    try:
        open_orders = await alpaca.get_open_orders(ticker=ticker, account_mode=ACCOUNT_MODE, raise_on_error=True)
    except Exception as e:  # loud-ok: get_open_orders alerts before re-raising; audited below, retried next minute
        open_orders, err = None, f"{type(e).__name__}: {str(e)[:200]}"
    cands = []
    for o in om._live_sell_stops(open_orders or []):
        try:
            covers = o.get("qty") is not None and float(o["qty"]) >= float(shares) - 0.5
        except (TypeError, ValueError):
            covers = False
        if covers and str(o.get("client_order_id") or "").startswith(COID_FAMILY_PREFIX) and o.get("id"):
            cands.append(o)
    if open_orders is None or len(cands) != 1:
        why = err if open_orders is None else f"{len(cands)} live family sell-stops"
        await log_audit_event("breakout_v1_fill_stop_unreadable",
                              f"{ticker} #{tid}: stop {str(replaced_id)[:8]} reads 'replaced' and its successor could "
                              f"not be named ({why}) — nothing touched, retried next minute",
                              json.dumps(dict(detail, successor_candidates=len(cands)), default=str))
        return "fill_check_wait"
    succ = cands[0]
    await om.set_stop_order_id(tid, succ["id"], reason="breakout_v1_fill_stop_successor_adopted",
                               account_mode=ACCOUNT_MODE)
    await log_audit_event("breakout_v1_fill_stop_successor_adopted",
                          f"{ticker} #{tid}: stop {str(replaced_id)[:8]} was replaced at the broker — the row now "
                          f"points at its successor {str(succ['id'])[:8]} (${float(succ.get('stop_price') or 0):.2f}); "
                          f"recorded next minute", json.dumps(dict(detail, successor_id=succ["id"]), default=str))
    return "fill_check_wait"


async def _sell_after_fill(row: dict, dec: dict) -> str:
    """The width rule fails at the true low: sell the WHOLE position now (paper, market), paged. Restart-safe: a row
    already closed / emptied, or a sale already pending at the broker, is only marked."""
    from agents.market_intelligence.broker.order_manager import execute_full_exit, get_pending_exit_qty
    ticker, tid = row["ticker"], row["id"]
    detail = {k: dec[k] for k in ("fill", "true_low", "width")}
    ok = await execute_full_exit(tid, dec["reason"])
    if not ok:
        now = await _row_state(tid)
        if now is None or now["status"] != "filled" or float(now.get("remaining_shares") or 0) <= 0:
            await _mark_fill_checked(row, "closed_before_sale", "the position was already closed — nothing to sell",
                                     detail)
            return "fill_closed"
        if await get_pending_exit_qty(tid) > 0:
            await _mark_fill_checked(row, "sale_pending", "a sale is already pending at the broker", detail)
            return "fill_sale_pending"
        await log_audit_event("breakout_v1_fill_sale_failed",
                              f"{ticker} #{tid}: the stop at the fill is too wide but the sale failed — retried "
                              f"next minute ({dec['reason']})", json.dumps(dict(detail, trade_id=tid), default=str))
        await _page_once(("fill_sale_failed", tid),
                         f"🚨 Breakout v1 *{ticker}*: the stop at the true low is too wide (his rule) but the sale "
                         f"FAILED — the position is still open with its stop; retrying every minute")
        return "fill_sale_failed"
    await _mark_fill_checked(row, "sold", dec["reason"], detail)
    await log_audit_event("breakout_v1_sold_too_wide_after_fill", f"{ticker} #{tid}: {dec['reason']} — sold all",
                          json.dumps(dict(detail, trade_id=tid), default=str))
    await _page_once(("fill_sold", tid),
                     f"✂️ Breakout v1 *{ticker}*: sold the whole position a minute after the fill — the true low "
                     f"${dec['true_low']:.2f} makes the stop too wide (fill ${dec['fill']:.2f}, {dec['width']:.1%} > "
                     f"1 ADR20). His rule: never hold a fill his entry would have abstained on.")
    return "fill_sold_too_wide"


async def _lower_stop_after_fill(row: dict, dec: dict) -> str:
    """Lower the protective stop leg to the true low — an atomic PRICE-ONLY replace (quantity unchanged; a rejected
    replace leaves the old stop live), the shape of `order_manager.scan_breakeven_arms`: the live leg is read first, the
    successor is confirmed live before the row says so, a dead stop is re-protected to broker truth. Never raises a
    stop; never runs beside a third (sold or pending — its stop is at cost / being reduced)."""
    from agents.market_intelligence.broker import order_manager as om
    ticker, tid = row["ticker"], row["id"]
    new_stop, fill = float(dec["new_stop"]), float(dec["fill"])
    shares = float(row.get("remaining_shares") or row.get("entry_shares") or 0)
    risk_now = round(shares * (fill - new_stop), 2)
    detail = {"fill": fill, "true_low": dec["true_low"], "width": dec["width"], "new_stop": new_stop,
              "shares": shares, "risk_dollars_sized": row.get("risk_dollars"), "risk_dollars_now": risk_now}
    if row.get("partial_taken") or await om.get_pending_exit_qty(tid) > 0:
        await _mark_fill_checked(row, "superseded_by_exit", "a third / an exit is already in flight — stop not "
                                                            "lowered (never under a stop at cost)", detail)
        return "fill_superseded"
    stop_id = row.get("stop_order_id")
    if not stop_id:
        await log_audit_event("breakout_v1_fill_stop_no_leg", f"{ticker} #{tid}: no stop leg on the row yet — the "
                                                               f"lower is retried next minute", json.dumps(detail))
        await _page_once(("fill_no_leg", tid), f"⚠️ Breakout v1 *{ticker}*: the filled position has no stop leg on "
                                               f"its row — the stop at the true low could not be set yet; retrying")
        return "fill_check_wait"
    reprotect = False
    outcome = "fill_check_wait"
    async with om._trade_advisory_try_lock(tid) as have_lock:
        if not have_lock:
            return "fill_check_wait"           # an exit holds the trade lock — the next tick decides again
        live = await alpaca.get_order(stop_id, account_mode=ACCOUNT_MODE)
        status = om._canonical_order_status(live.get("status") if live else None)
        broker_stop = live.get("stop_price") if live else None
        detail.update(stop_order_id=stop_id, broker_status=status, broker_stop=broker_stop)
        if status == "filled":
            await _mark_fill_checked(row, "stopped_before_check", "the stop filled before the check", detail)
            return "fill_stopped"
        if status == "replaced":
            # our lower was accepted and the row never followed (a crash during the verify polls): adopt the successor
            return await _adopt_replaced_successor(row, shares, stop_id, detail)
        if status not in om._STOP_CONFIRMED_LIVE_STATUSES or broker_stop is None:
            await log_audit_event("breakout_v1_fill_stop_unreadable",
                                  f"{ticker} #{tid}: stop {str(stop_id)[:8]} not confirmed live (status={status}) — "
                                  f"nothing touched, retried next minute", json.dumps(detail, default=str))
            return "fill_check_wait"
        broker_stop = float(broker_stop)
        if broker_stop >= fill - 1e-9:
            await _mark_fill_checked(row, "superseded_stop_at_cost", f"the broker stop ${broker_stop:.2f} is already "
                                                                     f"at/above the fill — never lowered", detail)
            return "fill_superseded"
        if broker_stop <= new_stop + 1e-9:
            # already at the true low (a tick after a crash, or an unverified successor that is now live): record it
            if await _record_stop_lowered(tid, stop_order_id=stop_id, new_stop=broker_stop,
                                          risk_dollars_actual=round(shares * (fill - broker_stop), 2)):
                await _insert_stop_leg_row(tid, live, ticker, shares, broker_stop)   # ON CONFLICT DO NOTHING
            await _mark_fill_checked(row, "lowered", f"stop already at ${broker_stop:.2f} at the broker — recorded",
                                     detail)
            return "fill_stop_lowered"
        new_order = None
        try:
            new_order = await alpaca.replace_order(
                stop_id, stop_price=new_stop, account_mode=ACCOUNT_MODE,
                client_order_id=alpaca.make_client_order_id(ACCOUNT_MODE, STRATEGY_ID, ticker))
        except Exception as e:
            chk = await alpaca.get_order(stop_id, account_mode=ACCOUNT_MODE)
            chk_status = om._canonical_order_status(chk.get("status") if chk else None)
            detail.update(error=str(e)[:300], recheck_status=chk_status)
            if chk_status in om._STOP_CONFIRMED_LIVE_STATUSES:
                await log_audit_event("breakout_v1_stop_lower_rejected",
                                      f"{ticker} #{tid}: lowering the stop to ${new_stop:.2f} was rejected "
                                      f"({type(e).__name__}); stop ${broker_stop:.2f} still live — retried next minute",
                                      json.dumps(detail, default=str))
                await _page_once(("fill_lower_rejected", tid),
                                 f"⚠️ Breakout v1 *{ticker}*: lowering the stop to the true low ${new_stop:.2f} was "
                                 f"rejected — the stop stays at ${broker_stop:.2f} (protected); retrying every minute")
                return "fill_lower_rejected"
            if chk_status == "filled":
                await _mark_fill_checked(row, "stopped_before_check", "the stop filled during the lower", detail)
                return "fill_stopped"
            if chk_status == "replaced":
                # the call raised but the broker took the replace: a live successor exists — adopt it, never re-protect
                return await _adopt_replaced_successor(row, shares, stop_id, detail)
            if chk_status in om._STOP_DEAD_STATUSES:
                await om.set_stop_order_id(tid, None, reason="breakout_v1_fill_stop_lower_failed",
                                           account_mode=ACCOUNT_MODE)
                reprotect = True
                outcome = "fill_lower_failed_stop_dead"
            else:
                await log_audit_event("breakout_v1_stop_lower_failed",
                                      f"{ticker} #{tid}: the lower raised and the stop could not be read back "
                                      f"(status={chk_status}) — nothing changed here", json.dumps(detail, default=str))
                await _page_once(("fill_lower_unknown", tid),
                                 f"⚠️ Breakout v1 *{ticker}*: lowering the stop to ${new_stop:.2f} failed and the "
                                 f"stop could not be read back — verify the stop on Alpaca")
                return "fill_lower_unverified"
        if new_order is not None:
            new_id = new_order["id"]
            # the pointer follows the broker AT ONCE: Alpaca marks the old leg 'replaced' the moment it accepts, so a
            # crash during the verify polls below must never leave the row on a dead id (review 2026-10-29)
            await om.set_stop_order_id(tid, new_id, reason="breakout_v1_fill_stop_lower_issued",
                                       account_mode=ACCOUNT_MODE)
            succ = "unknown"
            for i in range(STOP_LOWER_VERIFY_POLLS):
                chk = await alpaca.get_order(new_id, account_mode=ACCOUNT_MODE)
                st = om._canonical_order_status(chk.get("status") if chk else None)
                if st in om._STOP_CONFIRMED_LIVE_STATUSES:
                    succ = "live"
                    break
                if st in om._STOP_DEAD_STATUSES or st == "filled":
                    succ = "dead" if st != "filled" else "filled"
                    break
                if i < STOP_LOWER_VERIFY_POLLS - 1:
                    await asyncio.sleep(STOP_LOWER_VERIFY_S)
            detail.update(new_stop_order_id=new_id, successor=succ)
            if succ == "live":
                if not await _record_stop_lowered(tid, stop_order_id=new_id, new_stop=new_stop,
                                                  risk_dollars_actual=risk_now):
                    # the row moved under us: never leave its pointer on the REPLACED leg while the successor rests
                    await om.set_stop_order_id(tid, new_id, reason="breakout_v1_fill_stop_lower_row_moved",
                                               account_mode=ACCOUNT_MODE)
                    await log_audit_event("breakout_v1_stop_lower_row_moved",
                                          f"{ticker} #{tid}: stop lowered to ${new_stop:.2f} at the broker but the row "
                                          f"moved — pointer set to {new_id[:8]}, price not written",
                                          json.dumps(detail, default=str))
                await _insert_stop_leg_row(tid, new_order, ticker, shares, new_stop)
                await log_audit_event(
                    "breakout_v1_stop_lowered_after_fill",
                    f"{ticker} #{tid}: stop ${broker_stop:.2f} → ${new_stop:.2f} (the true low through the fill minute "
                    f"${dec['true_low']:.2f}); risk now ${risk_now:,.0f} vs ${float(row.get('risk_dollars') or 0):,.0f} "
                    f"sized ({str(stop_id)[:8]}→{new_id[:8]})", json.dumps(detail, default=str))
                await _mark_fill_checked(row, "lowered", f"stop lowered to ${new_stop:.2f}", detail)
                outcome = "fill_stop_lowered"
            elif succ == "filled":
                await om.set_stop_order_id(tid, new_id, reason="breakout_v1_fill_stop_lowered",
                                           account_mode=ACCOUNT_MODE)
                await _mark_fill_checked(row, "stopped_before_check", "the lowered stop filled at once", detail)
                outcome = "fill_stopped"
            elif succ == "dead":
                await om.set_stop_order_id(tid, None, reason="breakout_v1_fill_stop_lower_failed",
                                           account_mode=ACCOUNT_MODE)
                reprotect = True
                outcome = "fill_lower_failed_stop_dead"
            else:
                # still settling: the pointer is already on the successor (written as the replace returned); the price
                # is withheld — the next tick finds the new leg at the true low and records it
                await log_audit_event("breakout_v1_stop_lower_unverified",
                                      f"{ticker} #{tid}: the lower to ${new_stop:.2f} was accepted but not yet confirmed "
                                      f"live — re-read next minute", json.dumps(detail, default=str))
                outcome = "fill_check_wait"
    if reprotect:
        msg = None
        try:
            pos = await alpaca.get_position(ticker, account_mode=ACCOUNT_MODE)
            qty = float(pos.get("qty")) if pos and pos.get("qty") is not None else None
            if qty and qty > 0:
                msg = await om._ensure_stop_coverage(tid, ticker, qty, row.get("stop_price"), STRATEGY_ID,
                                                     ACCOUNT_MODE)
        except Exception as e:  # loud-ok: audited + paged below; the coverage retry reconciles
            msg = f"re-protect raised: {type(e).__name__}: {e}"
        await log_audit_event("breakout_v1_stop_lower_failed",
                              f"{ticker} #{tid}: the stop read back dead after the lower — pointer nulled, "
                              f"re-protecting ({msg or 'coverage met / deferred'})", json.dumps(detail, default=str))
        await _page_once(("fill_lower_dead", tid),
                         f"🚨 Breakout v1 *{ticker}*: lowering the stop failed and the stop read back DEAD — "
                         f"re-protecting ({msg or 'verify the stop on Alpaca'}); the lower is retried next minute")
    return outcome


async def _check_stop_at_fill(row: dict, lrow: dict | None, now_et: datetime, m: int) -> str:
    """ONE filled breakout row: the stop at the fill, once (see the section comment). -> the tick's action label."""
    ticker, tid = row["ticker"], row["id"]
    if row.get("signal_type") != STRATEGY_ID or row.get("account_mode") != ACCOUNT_MODE:
        return "untouched"                   # never another strategy's or another account's row
    if await fill_stop_checked(tid):
        return "fill_checked"
    result = await _check_stop_at_fill_once(row, lrow, now_et, m)
    if result == "fill_check_wait" and m >= EOD_MINUTE:
        await log_audit_event("breakout_v1_fill_stop_unchecked",
                              f"{ticker} #{tid}: the stop at the fill could not be decided by 15:55 ET — the last "
                              f"tick of the day; the stop was not confirmed at the true low")
        await _page_once(("fill_unchecked", tid), f"⚠️ Breakout v1 *{ticker}*: the stop at the true low could not be "
                                                  f"checked before 15:55 ET — check the stop on Alpaca by hand")
    return result


async def check_stop_at_fill_after_close(row: dict, now_et: datetime | None = None) -> str:
    """Advisor item 3 (pre-merge 2026-10-31): the stop at the fill for a FILLED breakout paper row the minute job never
    decided — a fill in the 15:55 minute has no tick after it (the disclosed race with the EOD cancel). Run by the
    16:45 pass (`live_tracker.update_open_positions_live`, the breakout branch, before the day-0 facts), the next
    pass that exists: the minute job's population is TODAY's rows for last night's list, so a row filled yesterday
    is never in it, while the 16:45 pass already visits every open breakout row on its breakout day. Decides from
    the breakout day's minute bars (`row['alert_date']`'s session, every minute complete) and the broker: the stop
    leg it lowers is the 16:20 post-close refresh's GTC stop (the entry's DAY leg expired at the close); a pointer
    still on a dead leg leaves the stop untouched (audited `breakout_v1_fill_stop_unreadable`) and the check runs
    again the next evening — never a stop placed on top of one the row cannot see. A row already checked costs one
    marker read. -> the check's action label ('fill_checked' | 'fill_stop_lowered' | 'fill_sold_too_wide' |
    'fill_stop_kept' | 'fill_check_wait' | ...). NEVER raises (audited + paged)."""
    ticker, tid = row["ticker"], row["id"]
    if (row.get("signal_type") != STRATEGY_ID or row.get("account_mode") != ACCOUNT_MODE
            or row.get("status") != "filled" or row.get("alert_date") is None):
        return "untouched"
    if await fill_stop_checked(tid):
        return "fill_checked"
    alert_date = row["alert_date"]
    now_et = (now_et or datetime.now(_ET)).astimezone(_ET)
    session_end = session_open(alert_date) + timedelta(minutes=N_SESSION_MINUTES)
    m = N_SESSION_MINUTES if now_et >= session_end else market_minute(now_et)
    try:
        prev = await _previous_session(alert_date)
        lrows = await bv1_get_list(prev) if prev else []
        lrow = next((x for x in lrows if x["ticker"] == ticker), None)
        result = await _check_stop_at_fill_once(row, lrow, now_et, m, session_date=alert_date)
    except Exception as e:  # loud-ok: audited + paged; the evening pass must go on to the row's exit
        logger.exception(f"breakout v1 {ticker}: the stop at the fill (after the close) crashed")
        await log_audit_event("breakout_v1_entry_crash", f"{ticker} (stop at the fill, after the close) — "
                                                         f"{type(e).__name__}: {str(e)[:300]}")
        await _page_once(("crash_fill_close", tid),
                         f"🚨 *{ticker}* breakout v1 stop-at-the-fill check (after the close) crashed — "
                         f"{type(e).__name__}: {str(e)[:160]}")
        return "crashed"
    if result in ("fill_check_wait", "fill_lower_rejected", "fill_lower_unverified", "fill_sale_failed"):
        # the evening pass has no "next minute": whatever `_lower_stop_after_fill` / `_sell_after_fill` audited as
        # retried next minute is retried the NEXT EVENING. A `breakout_v1_stop_lower_rejected` from HERE is the
        # signal the broker does not take a price-only replace of the GTC stop after hours — then this check must
        # move to the next session's first minutes (not built; disclosed in the SSoT).
        await log_audit_event("breakout_v1_fill_stop_unchecked_after_close",
                              f"{ticker} #{tid}: the stop at the fill was not settled by the evening pass either "
                              f"({result}) — the stop stands as it is; the check runs again the next evening",
                              json.dumps({"trade_id": tid, "ticker": ticker, "alert_date": str(alert_date),
                                          "result": result}))
        await _page_once(("fill_unchecked_close", tid),
                         f"⚠️ Breakout v1 *{ticker}*: the stop at the true low could not be settled after the close "
                         f"either ({result}) — it is retried the next evening, not every minute; check the stop on "
                         f"Alpaca by hand")
    return result


async def _check_stop_at_fill_once(row: dict, lrow: dict | None, now_et: datetime, m: int,
                                   session_date: date | None = None) -> str:
    # `session_date` (the after-close check): the breakout day's session, when `now_et` is no longer on it
    ticker, tid, today = row["ticker"], row["id"], (session_date or now_et.date())
    order = (await alpaca.get_order(row["entry_order_id"], account_mode=ACCOUNT_MODE)
             if row.get("entry_order_id") else None)
    if order is not None and order.get("status") not in ("filled",):
        return "fill_check_wait"             # still partly filled (more shares may come) — decided once complete
    filled_at = _parse_ts((order or {}).get("filled_at")) or _parse_ts(row.get("filled_at"))
    fm = fill_minute_of(filled_at, today)
    fill = float((order or {}).get("filled_avg_price") or row.get("entry_price") or 0)
    detail = {"fill": fill, "fill_minute": fm, "filled_at": filled_at}
    if fm is None or fill <= 0:
        await _mark_fill_checked(row, "not_checkable", "no fill time inside today's session / no fill price — the "
                                                       "stop it filled with stands", detail)
        await _page_once(("fill_not_checkable", tid), f"⚠️ Breakout v1 *{ticker}*: the fill time or price is "
                                                      f"unknown — the stop at the true low was not checked")
        return "fill_not_checkable"
    last_completed = min(m - 1, N_SESSION_MINUTES - 1)
    if last_completed < fm:
        return "fill_check_wait"             # the fill minute is still printing — one minute after the fill
    bars = await alpaca.get_minute_bars_range(
        ticker, session_open(today), min(now_et, session_open(today) + timedelta(minutes=N_SESSION_MINUTES)))
    mins = bars_by_minute(bars, today, fm)
    if fm not in mins and m < fm + 1 + FILL_BAR_WAIT_MINUTES:
        return "fill_check_wait"             # the fill minute's bar is not published yet
    if not mins:
        await _mark_fill_checked(row, "not_checkable", "no minute bars through the fill minute — the stop it filled "
                                                       "with stands", detail)
        await _page_once(("fill_not_checkable", tid), f"⚠️ Breakout v1 *{ticker}*: no minute bars through the fill — "
                                                      f"the stop at the true low was not checked")
        return "fill_not_checkable"
    true_low = min(min(float(b["low"]) for b in mins.values()), fill)
    placed = row.get("stop_price") if row.get("stop_price") is not None else row.get("hard_stop")
    dec = stop_at_fill_decision(fill=fill, true_low=true_low, adr20=(lrow or {}).get("adr20"),
                                placed_stop=float(placed) if placed is not None else fill)
    detail.update(true_low=true_low, width=dec["width"], placed_stop=placed, fill_bar_seen=fm in mins)
    if dec["action"] == "sell_all":
        return await _sell_after_fill(row, dec)
    if dec["action"] == "lower":
        return await _lower_stop_after_fill(row, dec)
    await _mark_fill_checked(row, "kept", dec["reason"] or f"true low ${true_low:.2f} is not under the placed stop "
                                                           f"— the stop is kept", detail)
    return "fill_stop_kept"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The tick
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _previous_session(today: date) -> date | None:
    """The NYSE session before today (the exchange calendar — never the last stored SPY bar: a failed nightly pull
    would otherwise hand the tick a list two sessions stale). The list read then keys on exactly that night, so a
    night whose list job did not run is no names. None (calendar unreadable) -> no names, audited."""
    try:
        from agents.market_intelligence.trading_calendar import _get_nyse_calendar
        return _get_nyse_calendar().previous_session(today.isoformat()).date()
    except Exception as e:  # loud-ok: no calendar -> no list -> nothing placed; audited + logged
        logger.warning(f"breakout v1: previous session unreadable for {today}: {e}")
        await log_audit_event("breakout_v1_calendar_unreadable",
                              f"{today.isoformat()}: previous session unreadable ({type(e).__name__}: {str(e)[:200]})"
                              f" — no breakout names this minute")
        return None


async def _today_rows(today: date, tickers: list[str]) -> dict[str, dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mi_live_trades WHERE alert_date = $1 AND account_mode = $2 AND ticker = ANY($3::text[])",
            today, ACCOUNT_MODE, list(tickers))
    return {r["ticker"]: dict(r) for r in rows}


async def _regime(today: date) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rec = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1", today)
    return dict(rec) if rec else None


async def _family_open_orders() -> list[dict] | None:
    """The paper account's open orders in THIS strategy's order-id family; None = the broker could not be read."""
    global _snapshot_fails
    try:
        orders = await alpaca.get_open_orders(account_mode=ACCOUNT_MODE, raise_on_error=True)
    except Exception as e:  # loud-ok: the tick takes no action without broker truth; paged after repeated misses
        _snapshot_fails += 1
        await log_audit_event("breakout_v1_broker_unreadable", f"open orders unreadable ({type(e).__name__}: "
                                                               f"{str(e)[:200]}) — no breakout action this minute")
        if _snapshot_fails >= SNAPSHOT_FAILS_BEFORE_PAGE:
            await _page_once(("snapshot", datetime.now(_ET).date()),
                             f"🚨 Breakout v1: the paper account's open orders could not be read for "
                             f"{_snapshot_fails} minutes — breakout buys are not being managed")
        return None
    _snapshot_fails = 0
    # BUY side only: an orphan is only ever an entry. A protective stop leg (sell) is never in the family, whatever
    # order id the broker gives it — so the orphan sweep below can never cancel a filled position's stop.
    return [o for o in orders if str(o.get("client_order_id") or "").startswith(COID_FAMILY_PREFIX)
            and str(o.get("side") or "").lower() == "buy"]


async def _cancel_orphans(today: date, family: list[dict], rows: dict[str, dict]) -> int:
    """An open order in the family that no LIVE row of today carries (a crash between the broker accepting an order
    and the row recording it, or a row settled 'cancelled' / 'skipped' while an order still rests under it):
    cancelled — an order no row tracks is never left resting. Paged. A 'filled' / 'filling' row still owns its order
    (a partly filled entry stays open at the broker)."""
    known = {r.get("entry_order_id") for r in rows.values()
             if r.get("signal_type") == STRATEGY_ID and r.get("status") not in _ROWS_THAT_OWN_NO_ORDER}
    n = 0
    for o in family:
        if o.get("id") in known:
            continue
        tkr = o.get("symbol") or "?"
        if _classify(o) == "filled":
            await _page_once(("orphan_filled", o.get("id")),
                             f"🚨 Breakout v1 *{tkr}*: an order no trade row tracks has filled shares — check the book")
            continue
        res = await _cancel_and_confirm(None, tkr, o["id"], "orphan", "no trade row carries this order")
        await log_audit_event("breakout_v1_orphan_order", f"{tkr}: untracked family order {str(o['id'])[:8]} → {res}")
        await _page_once(("orphan", o.get("id")),
                         f"⚠️ Breakout v1 *{tkr}*: an order no trade row tracks was found and cancelled ({res})")
        n += 1
    return n


async def run_breakout_v1_entry_tick(now_et: datetime | None = None) -> dict:
    """ONE minute of the breakout v1 paper order step. Called by the execution-owned job `breakout_v1_entry`
    (scheduler.py, every minute 09:35-15:55 ET mon-fri; the window is enforced HERE). Never raises for one name."""
    now_et = (now_et or datetime.now(_ET)).astimezone(_ET)
    today = now_et.date()
    out: dict = {"date": today.isoformat(), "minute": None, "names": 0, "actions": {}, "skipped": None}
    if not LIVE_TRADING_ENABLED:
        out["skipped"] = "live_trading_disabled"
        return out
    m = market_minute(now_et)
    out["minute"] = m
    if not FIRST_MINUTE <= m <= EOD_MINUTE:
        out["skipped"] = "outside_window"
        return out
    from agents.market_intelligence.trading_calendar import get_market_status
    if not get_market_status(today).is_trading_day:
        out["skipped"] = "not_a_trading_day"
        return out
    prev = await _previous_session(today)
    lrows = await bv1_get_list(prev) if prev else []          # wall 1: its own list table only
    if not lrows:
        out["skipped"] = "no_list_names"
        return out
    out["names"] = len(lrows)
    tickers = [r["ticker"] for r in lrows]
    rows = await _today_rows(today, tickers)
    family = await _family_open_orders()
    if family is None:
        out["skipped"] = "broker_unreadable"
        return out
    open_by_id = {o["id"]: o for o in family}
    await _cancel_orphans(today, family, rows)

    switch_on = await get_runtime_toggle(TOGGLE, TOGGLE_ENV, default=True)
    may_order, why = await _strategy_state(today) if switch_on else (False, f"toggle {TOGGLE} off")
    if not may_order and (not switch_on or why == _SWITCHED_OFF_WHY):
        # THE STOP AT THE FILL is part of a filled position's stop, not a new order: it still runs when the switch is
        # off (like the pp exit's jobs) — never on a refused phase (wall 2: nothing is touched then).
        for r in rows.values():
            if r.get("signal_type") == STRATEGY_ID and r["status"] == "filled":
                try:
                    out["actions"][r["ticker"]] = await _check_stop_at_fill(
                        r, next((x for x in lrows if x["ticker"] == r["ticker"]), None), now_et, m)
                except Exception as e:  # loud-ok: audited + paged; the switch-off cancels below still run
                    logger.exception(f"breakout v1 {r['ticker']}: the stop at the fill crashed")
                    await log_audit_event("breakout_v1_entry_crash", f"{r['ticker']} (stop at the fill) — "
                                                                     f"{type(e).__name__}: {str(e)[:300]}")
                    await _page_once(("crash_fill", today, r["ticker"]),
                                     f"🚨 *{r['ticker']}* breakout v1 stop-at-the-fill step crashed — "
                                     f"{type(e).__name__}: {str(e)[:160]}")
                    out["actions"][r["ticker"]] = "crashed"
    if not may_order:
        # the switch is off / the row refused: no new order, no re-price — and no resting breakout buy is left live
        reason = f"{BLOCK_STRATEGY_DISABLED}: breakout v1 switched off ({why})"
        for r in rows.values():
            if r.get("signal_type") == STRATEGY_ID and r["status"] == "order_placed" and r.get("entry_order_id"):
                if _classify(open_by_id.get(r["entry_order_id"])) == "open":
                    res = await _cancel_and_confirm(r["id"], r["ticker"], r["entry_order_id"], "switch_off", reason)
                    if res == "dead":
                        await _mark_cancelled(r["id"], "order_placed", r["entry_order_id"], reason)
                    out["actions"][r["ticker"]] = f"switch_off_{res}"
            elif r.get("signal_type") == STRATEGY_ID and r["status"] == "confirmed" and not r.get("entry_order_id"):
                await _mark_cancelled(r["id"], "confirmed", None, reason)       # an unsubmitted row frees its slot
                out["actions"][r["ticker"]] = "switch_off_unsubmitted"
        out["skipped"] = "switched_off"
        return out

    regime_record: dict | None = None
    last_completed = min(m - 1, N_SESSION_MINUTES - 1)
    for lrow in lrows:
        ticker = lrow["ticker"]
        try:
            row = rows.get(ticker)
            if row is not None and row.get("signal_type") != STRATEGY_ID:
                out["actions"][ticker] = f"owned_by_{row.get('signal_type')}"    # another paper strategy has it today
                continue
            if row is not None and row["status"] == "filled":
                # his ruling 2026-10-29: one minute after the fill, the stop at the TRUE low (once per trade)
                out["actions"][ticker] = await _check_stop_at_fill(row, lrow, now_et, m)
                continue
            if row is not None and row["status"] not in ("order_placed", "confirmed"):
                out["actions"][ticker] = f"row_{row['status']}"
                continue
            st = None
            if not (row is None and m >= EOD_MINUTE):
                bars = await alpaca.get_minute_bars_range(ticker, session_open(today), now_et)
                mins = bars_by_minute(bars, today, last_completed)
                st = evaluate(mins, list_level=float(lrow["level"]), adr20=lrow.get("adr20"),
                              vol_bar=float(lrow["vol_bar"]), last_completed=last_completed)
            if row is not None:
                out["actions"][ticker] = await _manage(row, lrow, st, m, open_by_id)
                continue
            # no row today
            if m >= EOD_MINUTE:
                out["actions"][ticker] = "never_placed"
                continue
            if st["status"] == "wait":
                await _note(today, ticker, "wait", f"waiting — {st['reason']}")
                out["actions"][ticker] = "wait"
                continue
            if st["status"] == "abstain":
                from agents.market_intelligence.broker.live_tracker import _insert_skipped_trade
                await _insert_skipped_trade(ticker, today, {"ticker": ticker}, None, st["reason"],
                                            signal_type=STRATEGY_ID, account_mode=ACCOUNT_MODE)
                await log_audit_event("breakout_v1_entry_abstain", f"{ticker}: {st['reason']}",
                                      json.dumps({k: st[k] for k in ("level", "orh5", "orl5", "day_low", "width")},
                                                 default=str))
                out["actions"][ticker] = "abstain"
                continue
            if not st["f1_ok"]:
                await _note(today, ticker, "volume_below_curve",
                            f"no buy yet — volume {st['cum_volume']:,.0f} by minute {last_completed} < "
                            f"{st['need_volume']:,.0f} (1.2x normal by this minute)",
                            {"cum_volume": st["cum_volume"], "need_volume": st["need_volume"],
                             "minute": last_completed})
                out["actions"][ticker] = "volume_hold"
                continue
            if not await paper_account_preflight(today):
                out["actions"][ticker] = "preflight_failed"
                continue
            if regime_record is None:
                regime_record = await _regime(today)
            r = await _enter(today, lrow, st, regime_record)
            out["actions"][ticker] = r.get("action")
        except Exception as e:  # loud-ok: one name's crash is audited + paged; the other names still run
            logger.exception(f"breakout v1 {ticker}: tick crashed")
            await log_audit_event("breakout_v1_entry_crash", f"{ticker} — {type(e).__name__}: {str(e)[:300]}")
            await _page_once(("crash", today, ticker),
                             f"🚨 *{ticker}* breakout v1 paper order step crashed — {type(e).__name__}: {str(e)[:160]}")
            out["actions"][ticker] = "crashed"

    if m >= EOD_MINUTE:
        await log_audit_event("breakout_v1_entry_day", f"{today.isoformat()}: {len(lrows)} list name(s) — "
                              + ", ".join(f"{t} {a}" for t, a in out["actions"].items()),
                              json.dumps(out, default=str))
    entered = sum(1 for a in out["actions"].values() if a == ACTION_AUTO_ENTERED)
    failed = sum(1 for a in out["actions"].values() if a in (ACTION_AUTO_ENTER_FAILED, "crashed"))
    if entered or failed:
        logger.info(f"breakout v1 minute {m}: {entered} paper order(s) placed, {failed} failed, {len(lrows)} name(s)")
    return out
