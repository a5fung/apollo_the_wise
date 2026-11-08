"""Breakout v1 PAPER — the order step (phase 2 part A, build 2026-10-30; spec
`docs/design/breakout_v1_build_spec_2026-10-29.md` B4 + B5; owner of the rules
`docs/setups/consolidation_breakout.md`, his PAPER GO 2026-10-28 and rulings F1 / F2 2026-10-29).

WHAT IT DOES. One execution-owned job, every minute 09:35-15:55 ET mon-fri (`run_breakout_v1_entry_tick`), for each
name on LAST NIGHT's list (`mi_breakout_v1_list`, scan_date = the previous session):
  * the 5-minute opening range from today's 09:30-09:34 minute bars: ORH5 / ORL5, `level = max(ORH5, list level)`
    (`consolidation_breakout._entry_one`'s `orh5`); no bar at all in those five minutes = the named abstain
    `no_opening_range_minutes`;
  * F1 (RULED): the buy is only PLACED, and only KEPT live, while the volume so far (through the last completed
    minute) >= the list's volume bar (1.2 x the average FULL daily volume of the last 10 sessions to the list night —
    his ruling 2026-11-02, read from the list row's `vol_bar`; it was the 50-day average before) x the share of a
    day's volume normally done by that minute (`breakout_v1_volume_curve.CUM_SHARE`, ONE pooled curve for every
    stock; its unit, the full daily volume, is the same for both averages). Before it permits there is no
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

THE LIST AT 150-350 NAMES (#717 stage 2, 2026-11-07; design `docs/design/717_stage2_design_2026-11-06.md`):
  * ONE batched minute-bar read per tick (`alpaca.get_minute_bars_range_batch`: the whole day so far for every name the
    minute must judge, chunked so each request is one 10,000-bar page — ~2 requests at 09:35, ~14 at 15:55 for 350
    names; it was one request per name per minute), on the batch's OWN single thread — never the ~7-thread pool every
    broker call in apollo-execution shares. A name whose request failed is judged next minute
    (`breakout_v1_bars_unreadable`, one row per tick); its resting buy, if any, is left as it is. A page that HANGS
    ends that tick's read, and every tick until it returns SKIPS its batch (`breakout_v1_bars_batch_in_flight`, one
    row per tick, nothing submitted behind the stuck page) — a hung endpoint never holds more than that one thread.
    3 straight ticks with unread names, for either reason, page once a day.
  * THE SLOTS (his rulings 2026-11-06, "Go with rec, track what we miss"): the 5 paper slots are shared with every paper
    strategy (F2). Each minute, after the existing rows are managed, the names whose state permits a buy are taken in
    LIST RANK order (the night's order score, rank 1 first): the first `free` = 5 - the funnel's own open count
    (`live_tracker.count_open_positions`, every paper strategy's filled / order_placed / confirmed rows; the smaller of
    that and the breakout row's own `max_concurrent_positions` when one is set — NULL today) go to the funnel (whose
    advisory-locked recount still rules); the rest are HELD — one `breakout_v1_entry_hold` row (state `slots_full`)
    and NO trade row, so they are retried every minute until a slot frees, judged at THAT minute's price by the
    existing width rule. HOLD-ONLY: a resting lower-ranked buy keeps its slot (no displacement — a one-function add on
    his word). A funnel `block:max_positions` / `block:strategy_position_cap` on one name (a same-moment entry
    elsewhere, the disclosed race) holds the rest of the minute's names instead of sending each to a terminal skip,
    and holds that name too (its skipped row is terminal, so only a hold row lets 15:55 record it). An open count that
    cannot be READ holds every eligible name under its own state (`slots_count_unreadable`) — never a missed record.
  * TRACK WHAT WE MISS (his ruling: "every name that met the break (level + volume pace) but never got a slot", with
    the first break minute): at 15:55 ET one `breakout_v1_missed_by_slots` audit row per list name that was held
    (`slots_full`) at least once today, never got a slot (no trade row today, or only a 'skipped' one — no order was
    ever placed) AND BROKE OUT after the hold — the held names are added to the 15:55 bars read and `first_break`
    finds the first minute at/after the first hold whose high reached the level WITH the volume pace held at that
    minute (`f1_permits` through the minute before, the live tick's own check); a held name that never traded at its
    level, or touched it only on lapsed volume, writes nothing. The record: ticker, day, the BREAK minute, the break
    price (the level), the stop it would have carried (the day low through the break minute), the pace at the break,
    the first hold's minute and stop, list rank, order score, the pace at the hold, the list row's `vol_bar` and
    `adr20`, reason `slots_full`. The holds are read back from the audit log (restart-safe; a hold note is marked
    written only when the audit log confirms it, else retried next tick); #720's monthly review joins daily bars on it.

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
manual halt is checked on the live path only — the same as the #624 lane). The strategy row is read FRESH every
minute (#312: his Demote press commits in the market agent and must stop the next tick here without a restart); a
row that cannot be READ (a database blip, the 5 s bound) is neither the switch nor a refusal: that minute returns
`strategy_unreadable` — no new order, no re-price, no cancel — and the next minute re-reads (paged once a day).
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
    BLOCK_MAX_POSITIONS,
    BLOCK_STRATEGY_DISABLED,
    BLOCK_STRATEGY_POSITION_CAP,
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
    MAX_CONCURRENT_LIVE_POSITIONS,
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

# #717 stage 2 (2026-11-07): the batched bars read and the slots
BARS_CHUNK_MAX = 200                                        # symbols per bars request at most (`alpaca.bars_batch_chunk_size`)
BARS_FAILS_BEFORE_PAGE = 3                                  # straight ticks with unread names before ONE page a day
HOLD_EVENT = "breakout_v1_entry_hold"                       # one row per (name, state) change a day (`_note`)
SLOTS_FULL_STATE = "slots_full"                             # the hold state: eligible, the paper book full, retried next minute
SLOTS_UNREADABLE_STATE = "slots_count_unreadable"           # held because the open count could not be READ: never a missed record
MISSED_BY_SLOTS = "breakout_v1_missed_by_slots"             # 15:55 ET: one row per name that BROKE OUT (level + pace) while held and never got a slot

_FILLED_STATUSES = frozenset({"filled", "partially_filled"})
_ROWS_THAT_OWN_NO_ORDER = frozenset({"cancelled", "skipped"})   # an open order under such a row is an orphan
_DEAD_UNFILLED_STATUSES = frozenset({"canceled", "cancelled", "expired", "rejected", "done_for_day", "replaced"})

# ── in-memory, NEVER order state: the day's pre-flight pass and de-duplication of pages / audit rows ──
_preflight_ok_date: date | None = None
_paged: set[tuple] = set()
_noted: dict[tuple, str] = {}
_snapshot_fails = 0
_bars_unread_ticks = 0           # straight ticks with at least one name's bars unread (a failed / hung chunk); pages at 3


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Pure arithmetic (no I/O)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def session_open(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=_ET)


def _clock(d: date, m: int) -> str:
    """Minute index `m` of `d`'s session as an ET clock string (5 -> '09:35')."""
    return (session_open(d) + timedelta(minutes=m)).strftime("%H:%M")


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
    `vol_bar` is the list's 1.2 x the average full daily volume of the last 10 sessions (his ruling 2026-11-02; the
    50-day before — this function only reads the row's value), so the bar is vol_bar x the curve's share at the last
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


def _preview(names: list[str], n: int) -> str:
    """The first `n` names, comma-joined, with '…' when there are more (a page's names list)."""
    return f"{', '.join(names[:n])}{'…' if len(names) > n else ''}"


async def _crashed(key: tuple, ticker: str, where: str, e: Exception, *, step: str = "paper order step",
                   log: str = "tick crashed") -> str:
    """ONE name's crash record: logged with its traceback, audited `breakout_v1_entry_crash` (`where` names the step in
    the summary; '' for the order step), paged once per `key` (the caller's dedup key, unchanged). -> 'crashed'."""
    logger.exception(f"breakout v1 {ticker}: {log}", exc_info=e)
    await log_audit_event("breakout_v1_entry_crash", f"{ticker}{f' ({where})' if where else ''} — "
                                                     f"{type(e).__name__}: {str(e)[:300]}")
    await _page_once(key, f"🚨 *{ticker}* breakout v1 {step} crashed — {type(e).__name__}: {str(e)[:160]}")
    return "crashed"


async def _note(today: date, ticker: str, state: str, summary: str, detail: dict | None = None) -> None:
    """One audit row per (name, state) change in a day — a volume hold is not re-recorded every minute. The detail
    carries `ticker`, `state` and `day` (the 15:55 missed-by-slots step reads the `slots_full` rows back by them).
    A `slots_full` note is marked noted ONLY once the write reports success (`log_audit_event` -> True): a write the
    audit log swallowed (a timeout, a pool error) is retried on the next tick, so a hold is never lost to the 15:55 record
    silently — its recorded first hold is then the first hold WRITTEN (re-review 2026-11-07 finding 4)."""
    key = (today, ticker)
    if _noted.get(key) == state:
        return
    ok = await log_audit_event(HOLD_EVENT, f"{ticker}: {summary}",
                               json.dumps(dict(detail or {}, ticker=ticker, state=state, day=today.isoformat()),
                                          default=str))
    # Only `slots_full` is read back (by 15:55), so only it is retried; any other state is marked noted whether or
    # not the write landed, as before — a slow audit log must not make every tick re-write ~350 `wait` notes
    # (final review 2026-11-07 finding 2).
    if ok or state != SLOTS_FULL_STATE:
        _noted[key] = state
    if not ok:
        logger.warning(f"breakout v1 {ticker}: the '{state}' note was not written (the audit log swallowed it)"
                       + (" — retried next tick" if state == SLOTS_FULL_STATE else ""))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3b. THE SLOTS (#717 stage 2; his rulings 2026-11-06 — hold-only, the overflow waits, track what we miss)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _free_slots() -> int | None:
    """The paper book's free slots this minute = the shared cap (`MAX_CONCURRENT_LIVE_POSITIONS`, 5) minus the funnel's
    OWN open count (`live_tracker.count_open_positions(conn, 'paper')`: every paper strategy's filled / order_placed /
    confirmed rows — the small-cap lane's included, his F2; no `signal_type`) — and, when the breakout row carries its
    own `mi_strategies.max_concurrent_positions` (NULL today, F2; the funnel enforces it when set, #65), the SMALLER of
    that and the strategy's own free count. ADVISORY: the funnel's advisory-locked recount at the insert still rules.
    -> None when the count could not be READ (audited): the caller holds every eligible name under its own state
    (`slots_count_unreadable` — a hold is retryable, a wrong entry is not — and never a missed-by-slots record)."""
    from agents.market_intelligence.broker.live_tracker import count_open_positions
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            free = int(MAX_CONCURRENT_LIVE_POSITIONS) - int(await count_open_positions(conn, ACCOUNT_MODE))
            cap = await conn.fetchval(
                "SELECT max_concurrent_positions FROM mi_strategies WHERE strategy_id = $1", STRATEGY_ID)
            if cap is not None:
                own = int(await count_open_positions(conn, ACCOUNT_MODE, STRATEGY_ID))
                free = min(free, int(cap) - own)
    except Exception as e:  # loud-ok: logged + audited; the caller holds every name this minute, the next tick re-reads
        logger.warning(f"breakout v1: the paper book's open count is unreadable ({type(e).__name__}: {e}) — holding")
        await log_audit_event("breakout_v1_slots_unreadable",
                              f"open-position count unreadable ({type(e).__name__}: {str(e)[:200]}) — every eligible "
                              f"name held this minute (not a missed-by-slots record)")
        return None
    return max(0, free)


async def _hold_for_slot(today: date, lrow: dict, st: dict, m: int, free: int, seated: int,
                         count_unreadable: bool = False) -> None:
    """A name whose state permits a buy while the paper book is full: HELD — one hold row (state `slots_full`; the
    first such row's facts are the missed-by-slots record's hold facts), no trade row, no funnel call; retried next
    minute. `free` is the free count AT THIS HOLD (0 — the book is full; never the tick-start count, which overstated it
    on the funnel-block path) and `seated` how many names took a slot this minute before it. `count_unreadable`: the
    open count could not be read — the row's state is `slots_count_unreadable` instead, which 15:55 never records."""
    clock = _clock(today, m)
    rank, score = lrow.get("list_rank"), lrow.get("order_score")
    state = SLOTS_UNREADABLE_STATE if count_unreadable else SLOTS_FULL_STATE
    why = ("the paper book's open count could not be read" if count_unreadable
           else f"the paper book is full ({seated} name(s) seated this minute ahead of it)")
    await _note(today, lrow["ticker"], state,
                f"held at {clock} ET — {why}, ranked #{rank}; retried every minute, judged at that minute's price",
                {"minute": m, "last_completed": st["last_completed"], "clock_et": clock, "list_rank": rank,
                 "order_score": score, "level": st["level"], "stop": st["stop"], "width": st["width"],
                 "cum_volume": st["cum_volume"], "need_volume": st["need_volume"], "free_slots": int(free),
                 "seated_this_minute": int(seated), "count_unreadable": bool(count_unreadable), "reason": state})


def first_break(mins: dict[int, dict], *, level: float, vol_bar: float, from_minute: int) -> dict | None:
    """THE BREAK a held name made (his ruling 2026-11-06: record the names that "met the break (LEVEL + VOLUME PACE)",
    with the first break minute): the first minute k >= `from_minute` (the first hold's tick minute — a buy seated
    then would have rested from that minute) whose bar HIGH reaches the level the buy would have rested at AND whose
    volume pace held — `f1_permits(the volume of minutes <= k-1, vol_bar, k-1)`, exactly the check the live tick
    makes at minute k (last_completed = k-1) before it places or keeps the buy that would have filled in minute k
    (re-review 2026-11-07 finding 1: a touch of the level on lapsed volume is NOT a break — a seated buy would have
    been cancelled `setup:breakout_volume_below_curve` before it filled; a later touch back on pace is). PURE.
    -> {minute, high, stop (the day's low through the break minute on the cent — the resting buy was re-priced to
    each new low until the fill, so this is the stop it would have carried), width ((level - stop) / level),
    cum_volume / need_volume (the pace at the break: through k-1, against the curve at k-1)}; None = never broke out
    from the hold on. ⚠ An UPPER BOUND on the trades we missed: it replays the pace at each minute, not the volume
    CANCEL — a seated buy whose pace lapsed was cancelled for the day, while a held name that lapsed, recovered and
    then touched its level is recorded (final review 2026-11-07 finding 3)."""
    if not mins or level is None:
        return None
    lvl = float(level)
    for k in sorted(mins):
        if k < int(from_minute):
            continue
        if float(mins[k]["high"]) < lvl:
            continue
        cum = float(sum(float(mins[j].get("volume") or 0) for j in mins if j <= k - 1))
        ok, need = f1_permits(cum, vol_bar, k - 1)
        if not ok:
            continue                                   # at the level, but the live tick would not have had a buy resting
        low = min(float(mins[j]["low"]) for j in mins if j <= k)
        stop = stop_from_low(low)
        return {"minute": k, "high": float(mins[k]["high"]), "stop": stop, "width": (lvl - stop) / lvl,
                "cum_volume": cum, "need_volume": need}
    return None


async def _audit_details(event_type: str, *, last_day: bool) -> list:
    """The parsed `detail` of every `event_type` row in `mi_audit_log`, newest first — the last day's rows, or every
    row (`last_day=False`). Matched in Python by each caller (detail is TEXT); a row whose detail is not JSON is skipped,
    never the read. RAISES when the log cannot be read: each caller keeps its own fail-safe answer. Not
    `db.get_audit_log`: its LIMIT 30 would cut the ~350-name hold read."""
    sql = ("SELECT event_type, detail FROM mi_audit_log WHERE event_type = $1 "
           + ("AND created_at > NOW() - INTERVAL '1 day' " if last_day else "") + "ORDER BY created_at DESC")
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, event_type)
    out = []
    for r in rows or []:
        if r["event_type"] != event_type:
            continue
        try:
            out.append(json.loads(r["detail"]))
        except Exception:  # loud-ok: one malformed row is skipped, never the read
            continue
    return out


async def _todays_details(event_type: str, today: date) -> list[dict] | None:
    """The parsed `detail` of every `event_type` audit row written for `today` (the detail's own `day` field — the rows
    of the last day are read, matched in Python; detail is TEXT). None = the log could not be read."""
    try:
        details = await _audit_details(event_type, last_day=True)
    except Exception as e:  # loud-ok: the caller audits + pages; nothing is written on a read it cannot trust
        logger.warning(f"breakout v1: today's {event_type} rows are unreadable ({type(e).__name__}: {e})")
        return None
    return [d for d in details if isinstance(d, dict) and d.get("day") == today.isoformat() and d.get("ticker")]


async def _first_holds_today(today: date) -> dict[str, dict] | None:
    """{ticker: the EARLIEST `slots_full` hold row's detail today} from the audit log (durable: a restart mid-session
    loses no name, and a second hold row written after a restart is folded by minute). None = unreadable."""
    details = await _todays_details(HOLD_EVENT, today)
    if details is None:
        return None
    first: dict[str, dict] = {}
    for d in details:
        if d.get("state") != SLOTS_FULL_STATE:
            continue
        cur = first.get(d["ticker"])
        if cur is None or int(d.get("minute") or 0) < int(cur.get("minute") or 0):
            first[d["ticker"]] = d
    return first


def _never_seated(first: dict[str, dict] | None, rows: dict[str, dict]) -> list[str]:
    """The names held for `slots_full` today that never got a slot: no trade row today, or only a 'skipped' one (no
    order was ever placed; a cancelled / order_placed / filled row means it had a slot at some point). In list-rank
    order. These are the 15:55 missed-by-slots CANDIDATES — the tick adds them to its bars read so the break can be judged."""
    if not first:
        return []
    return [t for t, d in sorted(first.items(), key=lambda kv: (kv[1].get("list_rank") or 10 ** 9, kv[0]))
            if rows.get(t) is None or rows[t].get("status") == "skipped"]


async def _record_missed_by_slots(today: date, rows: dict[str, dict], first: dict[str, dict] | None,
                                  bars_by_ticker: dict[str, list[dict]], last_completed: int,
                                  lrows: dict[str, dict]) -> int | None:
    """TRACK WHAT WE MISS (his ruling 2026-11-06: "every name that met the break (level + volume pace) but never got a
    slot", with the first break minute). At 15:55 ET: one `breakout_v1_missed_by_slots` row per list name HELD for
    `slots_full` at least once today (`first` = the earliest such hold per name, read back from the audit log by the
    tick BEFORE its bars read), that never got a slot (`_never_seated`), AND that BROKE OUT after the hold —
    `first_break` on today's bars (`bars_by_ticker`, the tick's one batched read, the held names added to it) with the
    list row's `vol_bar` (`lrows`, keyed by ticker): the first minute at/after the first hold whose high reached the
    level WITH the volume pace held at that minute, the live tick's own check. A name held that never traded at its
    level, or that touched it only on lapsed volume (a seated buy would have been cancelled before it filled), is NOT
    a miss and writes nothing. The record: ticker, day, `minute` + `clock_et` = THE BREAK, `break_high`, `break_price`
    (the level the buy would have rested at), `stop` (the day low through the break minute — the stop it would have
    carried) + `width`, `break_cum_volume` / `break_need_volume` (the pace at the break), `hold_minute` /
    `hold_clock_et` / `stop_at_hold` (the first hold), list rank, order score, the pace at the hold, `vol_bar` and
    `adr20` from the list row (#720 applies the width filter without a join), reason `slots_full`, the row status.
    Once per name per day: the step runs on the one 15:55 tick, and a name already recorded today (a re-run of that
    minute after a restart inside the misfire grace) is not written again — a record whose write the audit log
    swallowed is NOT counted and is written by such a re-run. A candidate whose bars were NOT read at 15:55 (its chunk
    failed), or that has no list row to take the volume bar from, is never judged "never broke" on an absence: audited
    `breakout_v1_missed_unreadable` naming it + paged once, nothing written for it. -> the count WRITTEN; None = the
    hold log was unreadable (audited + paged, nothing written)."""
    done = await _todays_details(MISSED_BY_SLOTS, today) if first else []
    if first is None or done is None:
        await log_audit_event("breakout_v1_missed_unreadable",
                              f"{today.isoformat()}: today's hold rows could not be read — no missed-by-slots records")
        await _page_once(("missed_unreadable", today),
                         f"⚠️ Breakout v1: the names held for a paper slot today could not be read back at 15:55 ET — "
                         f"today's missed-by-slots records were NOT written")
        return None
    already = {d["ticker"] for d in done}
    n, unread = 0, []
    for ticker in _never_seated(first, rows):
        if ticker in already:
            continue                                   # recorded already (the 15:55 minute re-run)
        d, row, lrow = first[ticker], rows.get(ticker), lrows.get(ticker)
        if ticker not in bars_by_ticker or lrow is None or lrow.get("vol_bar") is None:
            unread.append(ticker)                      # cannot be judged: never "never broke" on an absence
            continue
        mins = bars_by_minute(bars_by_ticker[ticker], today, last_completed)
        brk = first_break(mins, level=d.get("level"), vol_bar=float(lrow["vol_bar"]),
                          from_minute=int(d.get("minute") or 0))
        if brk is None:
            continue                                   # held, but it never broke out (level + pace): nothing was missed
        clock = _clock(today, brk["minute"])
        rec = {"ticker": ticker, "day": today.isoformat(), "minute": brk["minute"], "clock_et": clock,
               "break_price": d.get("level"), "break_high": brk["high"], "stop": brk["stop"], "width": brk["width"],
               "break_cum_volume": brk["cum_volume"], "break_need_volume": brk["need_volume"],
               "hold_minute": d.get("minute"), "hold_clock_et": d.get("clock_et"), "stop_at_hold": d.get("stop"),
               "list_rank": d.get("list_rank"), "order_score": d.get("order_score"),
               "cum_volume": d.get("cum_volume"), "need_volume": d.get("need_volume"),
               "vol_bar": lrow.get("vol_bar"), "adr20": lrow.get("adr20"),
               "reason": SLOTS_FULL_STATE, "row_status": (row or {}).get("status"), "account_mode": ACCOUNT_MODE}
        try:
            ok = await log_audit_event(
                MISSED_BY_SLOTS,
                f"{ticker}: broke out at {clock} ET on pace (#{d.get('list_rank')}, score {d.get('order_score')}; held "
                f"for a slot since {d.get('clock_et')} ET) but never got a paper slot today — would have bought "
                f"${float(d.get('level')):.2f} with the stop at ${float(brk['stop']):.2f} ({SLOTS_FULL_STATE})",
                json.dumps(rec, default=str))
        except Exception as e:  # loud-ok: one failed write is logged; the other names' records still go out
            logger.error(f"breakout v1 {ticker}: the missed-by-slots record failed ({type(e).__name__}: {e})")
            ok = False
        if ok:
            n += 1                                     # counted only when the row exists (re-review 2026-11-07)
        else:
            logger.error(f"breakout v1 {ticker}: the missed-by-slots record was NOT written (the audit log swallowed "
                         f"it) — lost unless a restart inside the misfire grace re-runs the 15:55 minute (there is no later tick)")
    if unread:
        await log_audit_event("breakout_v1_missed_unreadable",
                              f"{today.isoformat()}: {len(unread)} held name(s) could not be judged at 15:55 (no "
                              f"minute bars — a bars request failed — or no list row for the volume bar) — their "
                              f"missed-by-slots records were NOT written: {', '.join(unread)}",
                              json.dumps({"unread": unread, "written": n}))
        await _page_once(("missed_bars_unreadable", today),
                         f"⚠️ Breakout v1: {len(unread)} name(s) held for a paper slot today could not be judged "
                         f"at 15:55 ET (no minute bars or no list row) ({_preview(unread, 5)}) — their "
                         f"missed-by-slots records were NOT written")
    return n


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

# The four answers of `_strategy_state` (wall 2). The tick acts on the STATE, never on the text of `why`:
#   OK           — enabled, phase 'paper', resolves to paper: the minute runs.
#   SWITCHED_OFF — the toggle is off, or the row is missing / disabled: quiet; the stop at the fill still runs; every
#                  resting unfilled buy is cancelled (`block:strategy_disabled`).
#   REFUSED      — any other phase (a demote to shadow, a promote to live): audit + page; the resting buys cancelled.
#   UNREADABLE   — the row could not be READ this minute (a database blip, the 5 s bound): the tick returns with no
#                  new order, no re-price and NO cancel — a resting buy is left exactly as it is and the next minute
#                  re-reads (#312 re-review 2026-11-07 finding 2: one failed read used to take the switch-off branch
#                  and cancel the day's resting buys for good — breakout v1's own rule for an unreadable broker is
#                  "take no action", and this is the same rule). Audited every such minute, paged once a day.
STATE_OK = "ok"
STATE_SWITCHED_OFF = "switched_off"
STATE_REFUSED = "refused"
STATE_UNREADABLE = "unreadable"


async def _strategy_state(today: date) -> tuple[str, str]:
    """(state, why) — one of the `STATE_*` answers above. Wall 2: the strategy row must be enabled, phase 'paper',
    and resolve to 'paper'. A missing / disabled row is the switch OFF (quiet); any other phase is REFUSED (audit +
    page). Read FRESH (#312 review, 2026-11-07): a demote or disable committed in the market agent must stop the
    NEXT tick here without an apollo-execution restart — never a cached phase. A row that cannot be read is
    UNREADABLE: its own state, its own audit row and its own once-a-day page key (never the refusal's, so a morning
    blip cannot silence a real refusal page later that day)."""
    from agents.market_intelligence.strategies.registry import get_strategy_fresh
    try:
        strategy = await get_strategy_fresh(STRATEGY_ID)
    except Exception as e:  # loud-ok: fail CLOSED for NEW orders — the tick takes no action this minute (audit + page)
        msg = (f"{STRATEGY_ID}: the strategy row could not be read fresh ({type(e).__name__}: {str(e)[:160]}) — "
               f"breakout v1 takes no action this minute (no new order, no re-price, no cancel); it re-reads next minute")
        await log_audit_event("breakout_v1_strategy_unreadable", f"{today.isoformat()}: {msg}")
        await _page_once(("strategy_unreadable", today), f"⚠️ Breakout v1: {msg}")
        return STATE_UNREADABLE, msg
    if strategy is None or not strategy.enabled:
        return STATE_SWITCHED_OFF, _SWITCHED_OFF_WHY
    try:
        mode = resolve_account_mode_for_strategy(strategy) if strategy.phase == "paper" else None  # mode-ok: breakout v1's own phase guard — refuses anything but paper
    except Exception:  # loud-ok: an unresolvable phase is refused below
        mode = None
    if mode != ACCOUNT_MODE:
        msg = (f"{STRATEGY_ID} phase={strategy.phase!r} resolves to {mode!r} — breakout v1 orders on PAPER only; "
               f"refused")
        await log_audit_event("breakout_v1_refused", f"{today.isoformat()}: {msg}")
        await _page_once(("refused", today), f"🚨 Breakout v1 refused to order: {msg}")
        return STATE_REFUSED, msg
    return STATE_OK, ""


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
        for d in await _audit_details(PLANNED_ENTRY_CANCEL, last_day=True):
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
    """Has the stop at the fill already been decided for this trade? A `FILL_STOP_CHECKED` row naming it — of ANY
    age (pre-merge 2026-10-31: the lookup was 3 days, so after a restart, with the in-memory cache gone, an older
    trade read 'not checked' and could be re-decided from its day-0 bars; matched in Python, detail is TEXT). A read
    failure -> False: the step re-decides from broker truth."""
    if int(trade_id) in _fill_checked:
        return True
    try:
        for d in await _audit_details(FILL_STOP_CHECKED, last_day=False):     # ANY age: no window
            if str(d.get("trade_id")) == str(trade_id):
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
                # broker-confirmed: the pointer is cleared only after get_order read the stop back from the broker
                # in a DEAD status (om._STOP_DEAD_STATUSES) — the leg no longer exists there, and reprotect=True below
                # places a fresh stop at once (ADR 0008).
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
    is never in it, while the 16:45 pass already visits every open breakout row on its breakout day. ONLY a row
    FILLED THIS SESSION is checked (`alert_date` = the pass's ET date — review low, pre-merge 2026-10-31: the pass
    visits every open breakout row every evening, and a row filled days ago with its marker out of a bounded
    lookup's reach was re-decidable from day-0 bars — and could have been SOLD — days after the fill; the marker
    is now also read regardless of age). Decides from the breakout day's minute bars (`row['alert_date']`'s
    session, every minute complete) and the broker: the stop leg it lowers is the 16:20 post-close refresh's GTC
    stop (the entry's DAY leg expired at the close); a pointer still on a dead leg leaves the stop untouched
    (audited `breakout_v1_fill_stop_unreadable`, paged) and is NOT retried — the stop stands as it filled, never
    wider — never a stop placed on top of one the row cannot see. A row already checked costs one marker read.
    -> the check's action label ('fill_other_session' | 'fill_checked' | 'fill_stop_lowered' |
    'fill_sold_too_wide' | 'fill_stop_kept' | 'fill_check_wait' | ...). NEVER raises (audited + paged)."""
    ticker, tid = row["ticker"], row["id"]
    if (row.get("signal_type") != STRATEGY_ID or row.get("account_mode") != ACCOUNT_MODE
            or row.get("status") != "filled" or row.get("alert_date") is None):
        return "untouched"
    alert_date = row["alert_date"]
    now_et = (now_et or datetime.now(_ET)).astimezone(_ET)
    if alert_date != now_et.date():
        return "fill_other_session"          # the 15:55 fill race is today's; an older fill is never re-decided here
    if await fill_stop_checked(tid):
        return "fill_checked"
    session_end = session_open(alert_date) + timedelta(minutes=N_SESSION_MINUTES)
    m = N_SESSION_MINUTES if now_et >= session_end else market_minute(now_et)
    try:
        prev = await _previous_session(alert_date)
        lrows = await bv1_get_list(prev) if prev else []
        lrow = next((x for x in lrows if x["ticker"] == ticker), None)
        result = await _check_stop_at_fill_once(row, lrow, now_et, m, session_date=alert_date)
    except Exception as e:  # loud-ok: audited + paged; the evening pass must go on to the row's exit
        return await _crashed(("crash_fill_close", tid), ticker, "stop at the fill, after the close", e,
                              step="stop-at-the-fill check (after the close)",
                              log="the stop at the fill (after the close) crashed")
    if result in ("fill_check_wait", "fill_lower_rejected", "fill_lower_unverified", "fill_sale_failed"):
        # the evening pass has no "next minute", and no next evening either (only a row filled THIS session is
        # visited): whatever `_lower_stop_after_fill` / `_sell_after_fill` audited as retried next minute is NOT
        # retried — the stop stands as it filled (never wider), paged. A `breakout_v1_stop_lower_rejected` from HERE
        # is the signal the broker does not take a price-only replace of the GTC stop after hours — then this check
        # must move to the next session's first minutes (not built; disclosed in the SSoT).
        await log_audit_event("breakout_v1_fill_stop_unchecked_after_close",
                              f"{ticker} #{tid}: the stop at the fill was not settled by the evening pass either "
                              f"({result}) — the stop stands as it filled; not retried",
                              json.dumps({"trade_id": tid, "ticker": ticker, "alert_date": str(alert_date),
                                          "result": result}))
        await _page_once(("fill_unchecked_close", tid),
                         f"⚠️ Breakout v1 *{ticker}*: the stop at the true low could not be settled after the close "
                         f"either ({result}) — it is NOT retried; the stop stands as it filled (never wider). Check "
                         f"the stop on Alpaca by hand")
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


async def _read_list_bars(today: date, m: int, need: list[str], now_et: datetime,
                          last_completed: int) -> dict[str, list[dict]]:
    """The tick's ONE batched bars read (#717 stage 2) for the names in `need` -> {ticker: bars}; a name absent was not
    read this minute (its chunk failed, or the whole batch was skipped). Owns `_bars_unread_ticks`: every tick with a
    name unread adds one (audited), the third straight pages ONCE a day, a tick with every name read resets it. No
    names -> no request, the count untouched."""
    global _bars_unread_ticks
    if not need:
        return {}
    bars_by_ticker: dict[str, list[dict]] = {}
    answer = await alpaca.get_minute_bars_range_batch(
        need, session_open(today), now_et, last_completed=last_completed, chunk_max=BARS_CHUNK_MAX)
    if answer is None:
        # the previous minute's page is still on the batch thread (a hung request; alpaca-py sets no HTTP
        # timeout): this minute's batch was SKIPPED — nothing submitted behind it, every name unread, a resting
        # buy left as it is; counts toward the same 3-straight page as a failed request (re-review 2026-11-07)
        unread, why = list(need), "the bars batch is still in flight"
        _bars_unread_ticks += 1
        await log_audit_event("breakout_v1_bars_batch_in_flight",
                              f"minute {m}: bars batch still in flight — the previous minute's bars page has not "
                              f"returned from alpaca-py, so this minute's read was skipped (nothing submitted "
                              f"behind it); {len(need)} name(s) unread this minute, judged once it returns",
                              json.dumps({"minute": m, "need": len(need), "straight_ticks": _bars_unread_ticks}))
    else:
        bars_by_ticker = answer
        unread, why = [t for t in need if t not in bars_by_ticker], "a bars request failed"
        if unread:
            _bars_unread_ticks += 1
            await log_audit_event("breakout_v1_bars_unreadable",
                                  f"minute {m}: {len(unread)} of {len(need)} name(s) have no minute bars this "
                                  f"minute (a bars request failed) — judged next minute: {', '.join(unread[:20])}"
                                  + (" …" if len(unread) > 20 else ""),
                                  json.dumps({"minute": m, "need": len(need), "unread": unread,
                                              "straight_ticks": _bars_unread_ticks}))
    if unread and _bars_unread_ticks >= BARS_FAILS_BEFORE_PAGE:
        # a chunk that keeps failing (one bad symbol can blind up to 200 names), or a page that stays hung, pages
        # ONCE a day — an audit row a minute is not a signal anyone reads (review 2026-11-07)
        await _page_once(("bars_unreadable", today),
                         f"⚠️ Breakout v1: the minute bars of {len(unread)} of {len(need)} list name(s) could "
                         f"not be read for {_bars_unread_ticks} minutes running ({why}; "
                         f"{_preview(unread, 5)}) — those names are not "
                         f"being judged, and a resting buy under one is left exactly as it is")
    elif not unread:
        _bars_unread_ticks = 0
    return bars_by_ticker


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
    state, why = await _strategy_state(today) if switch_on else (STATE_SWITCHED_OFF, f"toggle {TOGGLE} off")
    if state == STATE_UNREADABLE and m < EOD_MINUTE:
        # the strategy row could not be READ this minute (re-review 2026-11-07 finding 2): no new order, no re-price
        # and NO cancel — a resting buy is left as it is, exactly as an unreadable broker leaves it (`broker_unreadable`
        # above); the next minute re-reads. The cancel below is for a real disable or a phase other than paper only.
        # A filled row's stop-at-the-fill check waits one minute too: `_fill_checked` is marked only after a decision,
        # so the next readable minute runs it — delayed, never dropped.
        out["skipped"] = "strategy_unreadable"
        return out
    if state == STATE_UNREADABLE:
        # 15:55 and unreadable (re-review 2026-11-07, the LOW): there is no next minute, and the last tick places
        # nothing NEW whatever the row says (a name without a row is `never_placed` in PASS 1, before the slots) —
        # but four things must run without the row: the cancel of the resting DAY buys (`_manage`, else one can
        # fill between 15:55 and 16:00), a filled row's stop-at-the-fill check (`_check_stop_at_fill` — it may
        # LOWER a stop or SELL the position; a filled position's stop is not a new order, final review finding 5),
        # the missed-by-slots record and the day row. So this minute runs as a normal one, and ONLY the switch-off
        # cancel below (a real disable / wrong rung) is skipped — a read failure must never mark a row
        # `block:strategy_disabled`.
        out["strategy_unreadable"] = True
    # UNREADABLE reaches here at 15:55 only: no NEW buy is placed (PASS 1 marks a row-less name `never_placed`); the
    # EOD cancel of resting buys, a filled row's stop-at-the-fill check, the missed record and the day row still run
    may_order = state in (STATE_OK, STATE_UNREADABLE)
    if state == STATE_SWITCHED_OFF:
        # THE STOP AT THE FILL is part of a filled position's stop, not a new order: it still runs when the switch is
        # off (like the pp exit's jobs) — never on a refused phase (wall 2: nothing is touched then).
        for r in rows.values():
            if r.get("signal_type") == STRATEGY_ID and r["status"] == "filled":
                try:
                    out["actions"][r["ticker"]] = await _check_stop_at_fill(
                        r, next((x for x in lrows if x["ticker"] == r["ticker"]), None), now_et, m)
                except Exception as e:  # loud-ok: audited + paged; the switch-off cancels below still run
                    out["actions"][r["ticker"]] = await _crashed(
                        ("crash_fill", today, r["ticker"]), r["ticker"], "stop at the fill", e,
                        step="stop-at-the-fill step", log="the stop at the fill crashed")
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

    # 15:55: the names held for a slot today are read back from the audit log BEFORE the bars read, so the ones that
    # never got a slot can be judged on today's bars (did they break out after the hold?) — TRACK WHAT WE MISS below
    first_holds: dict[str, dict] | None = None
    missed_candidates: list[str] = []
    if m >= EOD_MINUTE:
        first_holds = await _first_holds_today(today)
        listed = set(tickers)
        missed_candidates = [t for t in _never_seated(first_holds, rows) if t in listed]

    # ONE batched bars read (#717 stage 2) for every name this minute must judge: a name with no row today (before
    # 15:55) or with a resting / unsubmitted breakout row — and at 15:55 the held-never-seated names for the missed
    # record. A filled row reads its own bars in the fill check; a settled row and a name another strategy holds read none.
    need = [t for t in tickers
            if (rows.get(t) is None and m < EOD_MINUTE)
            or (rows.get(t) is not None and rows[t].get("signal_type") == STRATEGY_ID
                and rows[t]["status"] in ("order_placed", "confirmed"))]
    need += [t for t in missed_candidates if t not in need]
    bars_by_ticker = await _read_list_bars(today, m, need, now_et, last_completed)

    # PASS 1 — every name's state; the rows that exist are managed NOW (a cancel this minute frees its slot this
    # minute); the names whose state permits a buy are collected for the slots below.
    eligible: list[tuple[dict, dict]] = []
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
            if ticker in bars_by_ticker:
                mins = bars_by_minute(bars_by_ticker[ticker], today, last_completed)
                st = evaluate(mins, list_level=float(lrow["level"]), adr20=lrow.get("adr20"),
                              vol_bar=float(lrow["vol_bar"]), last_completed=last_completed)
            if row is not None:
                # no bars this minute (st None): a resting buy is held as it is, never cancelled or re-priced on nothing
                out["actions"][ticker] = await _manage(row, lrow, st, m, open_by_id)
                continue
            # no row today
            if m >= EOD_MINUTE:
                out["actions"][ticker] = "never_placed"
                continue
            if st is None:
                out["actions"][ticker] = "bars_unreadable"                     # its bars request failed: next minute
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
            eligible.append((lrow, st))
        except Exception as e:  # loud-ok: one name's crash is audited + paged; the other names still run
            out["actions"][ticker] = await _crashed(("crash", today, ticker), ticker, "", e)

    # PASS 2 — THE SLOTS (his rulings 2026-11-06): the eligible names in LIST RANK order; the first `free` go to the
    # funnel, the rest are HELD (no trade row, retried next minute at that minute's price). HOLD-ONLY: a resting
    # lower-ranked buy is never cancelled to seat a higher-ranked name.
    if eligible:
        eligible.sort(key=lambda e: (e[0].get("list_rank") is None, e[0].get("list_rank") or 0, e[0]["ticker"]))
        if not await paper_account_preflight(today):
            for lrow, _st in eligible:
                out["actions"][lrow["ticker"]] = "preflight_failed"
        else:
            free = await _free_slots()
            count_unreadable = free is None                     # the count could not be read: hold all, own state
            free = 0 if count_unreadable else free
            seated = 0
            for lrow, st in eligible:
                ticker = lrow["ticker"]
                try:
                    if free <= 0:
                        await _hold_for_slot(today, lrow, st, m, free, seated, count_unreadable)
                        out["actions"][ticker] = "held_count_unreadable" if count_unreadable else "held_slots_full"
                        continue
                    if regime_record is None:
                        regime_record = await _regime(today)
                    r = await _enter(today, lrow, st, regime_record)
                    out["actions"][ticker] = r.get("action")
                    reason = str(r.get("reason", ""))
                    if r.get("action") == ACTION_AUTO_ENTERED:
                        free -= 1
                        seated += 1
                    elif r.get("action") == ACTION_BLOCKED and (reason.startswith(BLOCK_MAX_POSITIONS)
                                                                or reason.startswith(BLOCK_STRATEGY_POSITION_CAP)):
                        # the funnel's locked recount says the book is full (a same-moment entry elsewhere — the
                        # disclosed race; or the strategy's own cap, when set): hold the rest of this minute's names
                        # rather than send each to a terminal skip — and hold THIS name too (its skipped row is
                        # terminal for the day), so 15:55 can record it if it breaks out and never seats
                        free = 0
                        await _hold_for_slot(today, lrow, st, m, 0, seated)
                except Exception as e:  # loud-ok: one name's crash is audited + paged; the other names still run
                    out["actions"][ticker] = await _crashed(("crash", today, ticker), ticker, "", e,
                                                            log="tick crashed (slots)")

    if m >= EOD_MINUTE:
        # TRACK WHAT WE MISS (his ruling 2026-11-06): the names that broke out while held and never got a slot, once each
        out["missed_by_slots"] = await _record_missed_by_slots(today, rows, first_holds, bars_by_ticker, last_completed,
                                                               {r["ticker"]: r for r in lrows})
        await log_audit_event("breakout_v1_entry_day", f"{today.isoformat()}: {len(lrows)} list name(s) — "
                              + ", ".join(f"{t} {a}" for t, a in out["actions"].items()),
                              json.dumps(out, default=str))
    entered = sum(1 for a in out["actions"].values() if a == ACTION_AUTO_ENTERED)
    failed = sum(1 for a in out["actions"].values() if a in (ACTION_AUTO_ENTER_FAILED, "crashed"))
    held = sum(1 for a in out["actions"].values() if a in ("held_slots_full", "held_count_unreadable"))
    if entered or failed or held:
        logger.info(f"breakout v1 minute {m}: {entered} paper order(s) placed, {held} held for a slot, {failed} failed, "
                    f"{len(lrows)} name(s)")
    return out
