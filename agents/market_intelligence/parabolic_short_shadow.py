"""Parabolic-short forward SHADOW (#314, ADR 0020 section 4, card B3) - NO orders, NO money.

Records what the backside-confirmation short would have done, so the ladder's first rung (ADR 0020:
SHADOW -> N>=30 triggered cohort with positive expectancy -> PAPER) has a forward record to read.
The detector (`parabolic_detector.py`) is untouched: this module consumes the climax-stage candidates
it already persists to `mi_parabolic_candidates`, after the M&A / news exclusions, and runs inside the
17:15 ET `parabolic_scan` job.

THE STATE MACHINE (one episode per climax-flagged (ticker, scan date) D0), every number from stored daily
bars (`mi_daily_closes`), every day counted in TRADING rows, never calendar days:

  D0 evening  decide ONCE: one-open-episode-per-name -> market-cap floor ($250M HARD reject, unknown cap
              rejects too) -> borrow check (Alpaca `shortable AND easy_to_borrow`, ETB-only) -> ARM, or a
              rejected 'arm' row with a NAMED reason. A borrow READ that fails (`infra:`) writes no row while
              a later night can still arm it - the candidate is retried; the infra row is written only on the
              last window night. The geometry is recorded either way: climax high, prior-day low (the level in
              force), ATR14, the stop buffer min(3% of the climax high, 0.5 x ATR14), the stop above the climax
              high, and 1R's risk basis (half the long book's per-trade risk - a RECORDED NUMBER ONLY).
  sessions 1-3 after D0 (the arm window): a stop-limit SHORT rests at the PRIOR session's low (it trails
              daily). A session whose low reaches it TRIGGERS (borrow check repeated -> 'trigger' row). A
              session that CLOSES above the climax high first, or the 3rd session passing untriggered,
              closes the episode ('outcome' row, closed_untriggered).
  after trigger  cover 1/3 at the first 1R flush (price one R below entry) - the stop trails to the
              prior session's high daily (it only ever moves down) - hard time stop at the close of the
              5th session held (the entry session counts as 1) - an overnight into an earnings date is
              not held - no adds, ever. Settlement writes the 'outcome' row with the blended R.

DAILY-BAR HONESTY (a daily bar cannot order its own events): the fill convention is the one a real
DAY stop-limit SHORT has - open above the level and low <= level fills AT the level (`intraday`); an open
at/below the level but inside the limit fills at the open (`gap_open`); an open BELOW the limit triggers the
stop and leaves a resting limit SELL, which fills at the limit the moment the session trades back up to it
(`limit_recovery`: high >= limit - the open is the first print, so the rise happened while the order was
live); only when the high never reaches the limit is it a NO FILL (the arm carries to the next session, its
level re-set to that session's low). Whenever one bar could both stop the position out and take the flush,
the STOP is assumed first; a stop-out on the entry session itself is flagged `entry_day_ambiguous` (the high
may have come before the fill). A gap above the stop exits at the open. On the ENTRY session only: an
`intraday` fill does not count that session's high toward `mae_r` (price was above the level before the
fill, so the high may predate it); a `limit_recovery` fill credits no flush and no `mfe_r` from that
session's low (the low sat under the limit BEFORE the order could fill) and flags `entry_day_ambiguous` if
the low reached the flush level.

THE BOUNDARY (deploy gate 5j, #256 W1): this module imports `execution_client` only - never `broker.*`.
The ONE broker call it can reach is the read-only `execution_client.get_asset`; `tests` pin that no order
function is reachable. A broker/transport failure on the borrow read is an `infra:` row, never "assume ETB".

Owner doc: docs/setups/parabolic_short.md. ADR: docs/decisions/0020-multi-setup-book.md.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Optional

from agents.market_intelligence import execution_client
from agents.market_intelligence.broker.skip_reasons import FILTER_MCAP_TOO_SMALL  # vocabulary only (gate 5j exempt)
from agents.market_intelligence.flag_detector import _atr_14

logger = logging.getLogger(__name__)

# ── ADR 0020 section 4 (operator-signed 2026-07-05) ──────────────────────────────────────────────────
SHORT_MCAP_FLOOR_USD = 250_000_000     # "HARD REJECT any short entry below $250M market cap" (Gemini am. 7/5, J4)
STOP_BUFFER_PCT_CAP = 0.03             # stop buffer = min(3% of the climax high, 0.5 x ATR14)
STOP_BUFFER_ATR_MULT = 0.5
ARM_WINDOW_SESSIONS = 3                # "cancel ... after 3 unarmed days" - see the doc's reading
TIME_STOP_SESSIONS = 5                 # "hard time-stop 5 trading days"
FLUSH_COVER_DENOM = 3                  # "cover 1/3 on the first -1R-equivalent flush"
FLUSH_R_MULT = 1.0                     # the flush: price one R BELOW the entry
SHORT_RISK_FRACTION = 0.5              # 1R sizes at HALF the long book's per-trade risk (J4) - recorded only

# ── Implementation choices (not in the ADR; each is in the change log) ──────────────────────────────
BORROW_ACCOUNT_MODE = "paper"          # shadow phase resolves to no account; the first real rung is PAPER
LIMIT_BUFFER_PCT = 0.005               # mirrors order_manager.stop_limit_buy_price, on the other side
LIMIT_BUFFER_MIN = 0.02
HISTORY_ROWS = 60                      # >= ATR14 warm-up + the arm window + the time stop, with headroom
NEW_CANDIDATE_LOOKBACK_DAYS = 7        # calendar bound for the candidate query only
STALE_EPISODE_DAYS = 30                # backstop: an episode still open after this is voided (data gap)
RESTATE_TOLERANCE = 0.005              # climax high re-read from bars vs the arm row: a split restates history

# ── Bounded vocabulary (aggregation key = split_part(reason, ':', 1)) ───────────────────────────────
FILTER_MCAP_UNKNOWN = "filter:mcap_unknown"
BORROW_NOT_TRADABLE = "borrow:not_tradable"
BORROW_NOT_SHORTABLE = "borrow:not_shortable"
BORROW_HARD_TO_BORROW = "borrow:hard_to_borrow"
BORROW_ASSET_NOT_FOUND = "borrow:asset_not_found"
INFRA_BORROW_CHECK_FAILED = "infra:borrow_check_failed"
REASON_INVALIDATED_BEFORE_ARM = "invalidated_before_arm"
REASON_EPISODE_OPEN = "episode_already_open"      # ADR "no adds, ever": one open episode per name
OUT_INVALIDATED = "invalidated"
OUT_EXPIRED = "expired_untriggered"
OUT_STOP = "stop"
OUT_TRAIL_STOP = "trail_stop"
OUT_TIME_STOP = "time_stop"
OUT_EARNINGS_EXIT = "earnings_exit"
OUT_TRIGGER_SKIPPED = "trigger_skipped"
OUT_VOID_RESTATED = "void_restated"
OUT_VOID_MISMATCH = "void_replay_mismatch"
OUT_VOID_GEOMETRY = "void_bad_geometry"
OUT_VOID_DATA_GAP = "void_data_gap"

# Trigger kinds (`trigger_fill` returns one; the trigger row records it as detail.kind)
KIND_NONE = "none"                          # the session's low never reached the level
KIND_INTRADAY = "intraday"                  # opened above the level, traded down through it: filled AT the level
KIND_GAP_OPEN = "gap_open"                  # opened at/below the level but inside the limit: filled at the open
KIND_LIMIT_RECOVERY = "limit_recovery"      # opened below the limit; the resting limit sell filled on the way back up
KIND_NO_FILL = "gap_through_limit"          # triggered, but the high never got back to the limit: no fill
FILL_KINDS = frozenset({KIND_INTRADAY, KIND_GAP_OPEN, KIND_LIMIT_RECOVERY})


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Pure functions (no DB, no IO) - rows are OHLCV ascending by trade_date, the shape
# `db.get_recent_daily_history` returns: trade_date, open_price, high_price, low_price, close, volume.
# ═════════════════════════════════════════════════════════════════════════════════════════════════

def _bar_ok(bar: dict) -> bool:
    return all(bar.get(k) is not None for k in ("open_price", "high_price", "low_price", "close"))


def _as_date(v: Any) -> Optional[date]:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v)
    return None


def short_limit_price(stop_price: float) -> float:
    """The LIMIT under a stop-limit SHORT's stop - `order_manager.stop_limit_buy_price` mirrored: once the
    stop trades, the order is a limit SELL that fills only at/above this price. Two floors, as on the buy
    side: 0.5% below the stop, and an absolute $0.02 for penny-priced names."""
    return round(min(stop_price * (1.0 - LIMIT_BUFFER_PCT), stop_price - LIMIT_BUFFER_MIN), 2)


def stop_buffer(climax_high: float, atr14: Optional[float]) -> float:
    """Dollars above the climax high for the stop: min(3% of the climax high, 0.5 x ATR14). With no
    usable ATR the 3% cap stands alone (recorded as atr_14 = NULL)."""
    cap = STOP_BUFFER_PCT_CAP * climax_high
    if atr14 is None or atr14 <= 0:
        return cap
    return min(cap, STOP_BUFFER_ATR_MULT * atr14)


def _atr14(rows: list[dict], idx: int) -> Optional[float]:
    """ATR14 at `idx` from flag_detector (the repo's one ATR). None when there is not enough history or a
    bar lacks a high/low - the buffer then falls back to the 3% cap."""
    try:
        return _atr_14(rows, idx)
    except (TypeError, ValueError, KeyError):
        return None


def arm_geometry(rows: list[dict], ci: int) -> dict:
    """Data prep for one climax day (card B3: prior_day_low / climax_high from the stored bars, ATR14
    computed and persisted): everything an arm row records, whether or not the episode then arms."""
    bar = rows[ci]
    climax_high = float(bar["high_price"])
    climax_low = float(bar["low_price"])
    atr = _atr14(rows, ci)
    buf = stop_buffer(climax_high, atr)
    return {
        "climax_high": climax_high,
        "climax_low": climax_low,
        "prior_day_low": climax_low,                     # the level for session 1 = the climax day's low
        "limit_price": short_limit_price(climax_low),
        "atr_14": atr,
        "stop_buffer": buf,
        "stop_price": round(climax_high + buf, 2),
    }


def trigger_fill(level: float, bar: dict) -> tuple[str, Optional[float]]:
    """A resting DAY stop-limit SHORT at `level` against one session's bar -> (kind, fill price).

    (KIND_NONE, None)           the low never reached the level
    (KIND_INTRADAY, level)      opened above it, traded down through it: filled AT the level
    (KIND_GAP_OPEN, open)       gapped to/below it but opened inside the limit: filled at the open
    (KIND_LIMIT_RECOVERY, limit) opened below the limit: the opening print triggers the stop and the order
                                rests as a limit SELL at `limit`; a high >= limit means price came back up
                                to it while the order was live - a certain fill, at the limit
    (KIND_NO_FILL, None)        opened below the limit and the high never got back to it: triggered, never
                                filled (the arm carries)
    """
    low = float(bar["low_price"])
    if low > level:
        return (KIND_NONE, None)
    open_ = float(bar["open_price"])
    if open_ > level:
        return (KIND_INTRADAY, level)
    limit = short_limit_price(level)
    if open_ >= limit:
        return (KIND_GAP_OPEN, open_)
    if float(bar["high_price"]) >= limit:
        return (KIND_LIMIT_RECOVERY, limit)
    return (KIND_NO_FILL, None)


def replay_episode(
    rows: list[dict],
    ci: int,
    *,
    stop_price: float,
    armed_on: date,
    earnings_after: frozenset = frozenset(),
    arm_window: int = ARM_WINDOW_SESSIONS,
    time_stop: int = TIME_STOP_SESSIONS,
) -> dict:
    """Replay one episode from its climax bar `rows[ci]` through the last row, deterministically.

    `armed_on` - the night the arm decision was made: a session dated on/before it cannot trigger (a late
    arm does not get credit for a break that happened before it existed) but still counts toward the
    window and the invalidation test. `earnings_after` - session dates after whose CLOSE the position must
    not be held (earnings before the next open); the caller computes them, this stays pure.

    Returns {state, sessions_since, next_level, gap_skips, trigger, outcome}:
      state 'waiting' (armed, untriggered, window open) | 'open' (position held) | 'closed' (episode over)
            | 'data_gap' (a needed bar lacks a price - nothing advances until it is filled)
    """
    climax_high = float(rows[ci]["high_price"])
    level = float(rows[ci]["low_price"])
    n_after = len(rows) - 1 - ci
    out: dict = {"state": "waiting", "sessions_since": n_after, "next_level": level, "gap_skips": 0,
                 "trigger": None, "outcome": None}

    entry_idx = None
    entry_price = None
    entry_level = None
    entry_kind = None
    for k in range(1, n_after + 1):
        idx = ci + k
        bar = rows[idx]
        if not _bar_ok(bar):
            out["state"] = "data_gap"
            return out
        bar_date = _as_date(bar["trade_date"])
        if bar_date is not None and bar_date > armed_on:
            kind, px = trigger_fill(level, bar)
            if kind in FILL_KINDS:
                entry_idx, entry_price, entry_level, entry_kind = idx, px, level, kind
                break
            if kind == KIND_NO_FILL:
                out["gap_skips"] += 1
        if float(bar["close"]) > climax_high:
            out["state"] = "closed"
            out["outcome"] = {"status": "closed_untriggered", "reason": OUT_INVALIDATED, "date": bar_date}
            return out
        if k >= arm_window:
            out["state"] = "closed"
            out["outcome"] = {"status": "closed_untriggered", "reason": OUT_EXPIRED, "date": bar_date}
            return out
        level = float(bar["low_price"])
        out["next_level"] = level
    if entry_idx is None:
        return out

    risk = stop_price - entry_price
    entry_bar_date = _as_date(rows[entry_idx]["trade_date"])
    out["trigger"] = {
        "idx": entry_idx, "date": entry_bar_date, "level": entry_level,
        "limit": short_limit_price(entry_level), "entry_price": entry_price,
        "kind": entry_kind,
        "risk_per_share": risk,
    }
    if risk <= 0:
        out["state"] = "closed"
        out["outcome"] = {"status": "voided", "reason": OUT_VOID_GEOMETRY, "date": entry_bar_date}
        return out

    flush_level = entry_price - FLUSH_R_MULT * risk
    stop = stop_price
    flush_taken = False
    flush_price = None
    mfe = 0.0
    mae = 0.0
    ambiguous = False
    for j in range(entry_idx, len(rows)):
        bar = rows[j]
        if not _bar_ok(bar):
            out["state"] = "data_gap"
            return out
        held = j - entry_idx + 1
        if j > entry_idx:
            stop = min(stop, float(rows[j - 1]["high_price"]))   # trails to the prior session's high; never up
        high, low = float(bar["high_price"]), float(bar["low_price"])
        close, open_ = float(bar["close"]), float(bar["open_price"])
        # What an ENTRY-session bar can honestly say about the held position (a daily bar cannot order its
        # events): an `intraday` fill came on the way DOWN from above the level, so that session's high may
        # predate it (no MAE from it); a `limit_recovery` fill came on the way UP from under the limit, so
        # that session's low predates it (no MFE and no flush credit from it).
        entry_bar = j == entry_idx
        high_after_fill = not (entry_bar and entry_kind == KIND_INTRADAY)
        low_after_fill = not (entry_bar and entry_kind == KIND_LIMIT_RECOVERY)
        if low_after_fill:
            mfe = max(mfe, (entry_price - low) / risk)
        if high_after_fill:
            mae = max(mae, (high - entry_price) / risk)
        exit_px = None
        reason = None
        if high >= stop:                                          # stop BEFORE the flush: the conservative order
            if entry_bar:
                exit_px, ambiguous = stop, True                   # the high may predate the fill
            else:
                exit_px = max(stop, open_)                        # a gap above the stop exits at the open
            mae = max(mae, (exit_px - entry_price) / risk)        # a stop-out is at least the stop distance
            reason = OUT_TRAIL_STOP if stop < stop_price else OUT_STOP
        else:
            if not flush_taken and low <= flush_level:
                if low_after_fill:
                    flush_taken, flush_price = True, flush_level
                else:
                    ambiguous = True                              # the flush may have come after the fill - not credited
            bar_date = _as_date(bar["trade_date"])
            if held >= time_stop:
                exit_px, reason = close, OUT_TIME_STOP
            elif bar_date in earnings_after:
                exit_px, reason = close, OUT_EARNINGS_EXIT
        if exit_px is not None:
            exit_leg_r = (entry_price - exit_px) / risk
            frac = 1.0 / FLUSH_COVER_DENOM
            realized = (frac * FLUSH_R_MULT + (1.0 - frac) * exit_leg_r) if flush_taken else exit_leg_r
            out["state"] = "closed"
            out["outcome"] = {
                "status": "settled", "reason": reason, "date": _as_date(bar["trade_date"]),
                "exit_price": exit_px, "sessions_held": held, "flush_taken": flush_taken,
                "flush_price": flush_price, "realized_r": realized, "exit_leg_r": exit_leg_r,
                "mfe_r": mfe, "mae_r": mae, "entry_day_ambiguous": ambiguous,
            }
            return out
    out["state"] = "open"
    out["open"] = {"sessions_held": len(rows) - entry_idx, "stop": stop, "flush_taken": flush_taken,
                   "mfe_r": mfe, "mae_r": mae}
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Borrow check - through the facade, read-only
# ═════════════════════════════════════════════════════════════════════════════════════════════════

async def check_borrow(ticker: str) -> dict:
    """ETB-only borrow gate -> {ok, reason, snapshot}. `snapshot` always carries which account was read.

    ok only when Alpaca says the asset is active AND tradable AND shortable AND easy_to_borrow. A 404 is the
    broker's ANSWER (`borrow:asset_not_found`); ANY failure to read - the wire (ExecutionUnreachable), a
    broker error that ran in execution (ExecutionCallFailed), a timeout, missing credentials in-process -
    is `infra:borrow_check_failed` and never an ok: the shadow does not assume easy-to-borrow."""
    snapshot: dict = {"borrow_acct": BORROW_ACCOUNT_MODE}
    try:
        asset = await execution_client.get_asset(ticker, account_mode=BORROW_ACCOUNT_MODE)
    except Exception as e:     # the failure is logged here and recorded on the row - fallback is not silent
        logger.warning("parabolic_short_shadow: borrow read for %s failed: %s: %s", ticker, type(e).__name__, e)
        snapshot["error"] = f"{type(e).__name__}: {e}"[:300]
        return {"ok": False, "reason": INFRA_BORROW_CHECK_FAILED, "snapshot": snapshot}
    if asset is None:
        return {"ok": False, "reason": BORROW_ASSET_NOT_FOUND, "snapshot": snapshot}
    snapshot.update({
        "shortable": asset.get("shortable"), "easy_to_borrow": asset.get("easy_to_borrow"),
        "asset_status": asset.get("status"), "tradable": asset.get("tradable"),
    })
    if asset.get("status") != "active" or asset.get("tradable") is not True:
        return {"ok": False, "reason": BORROW_NOT_TRADABLE, "snapshot": snapshot}
    if asset.get("shortable") is not True:
        return {"ok": False, "reason": BORROW_NOT_SHORTABLE, "snapshot": snapshot}
    if asset.get("easy_to_borrow") is not True:
        return {"ok": False, "reason": BORROW_HARD_TO_BORROW, "snapshot": snapshot}
    return {"ok": True, "reason": None, "snapshot": snapshot}


def _borrow_cols(snapshot: dict) -> dict:
    return {
        "borrow_acct": snapshot.get("borrow_acct"),
        "shortable": snapshot.get("shortable"),
        "easy_to_borrow": snapshot.get("easy_to_borrow"),
        "asset_status": snapshot.get("asset_status"),
    }


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Earnings: "no overnight holds through earnings dates"
# ═════════════════════════════════════════════════════════════════════════════════════════════════

def _next_session(d: date) -> date:
    """The next NYSE trading day after `d`: weekends AND exchange holidays skipped, the same calendar
    `job_recovery._session_opens_on` counts a session on. Weekends are skipped HERE, before the calendar call
    (as `_session_opens_on` does): `get_market_status` fails open on a library error and reads a Saturday as a
    trading day, which would make a Friday's next session Saturday and drop the Monday-morning print. So a
    calendar failure falls back to the plain next weekday; the loop bound is only a backstop."""
    from agents.market_intelligence.trading_calendar import get_market_status
    n = d + timedelta(days=1)
    for _ in range(10):
        if n.weekday() < 5 and get_market_status(n).is_trading_day:
            break
        n += timedelta(days=1)
    return n


async def default_earnings_before_next_open(ticker: str, session: date) -> Optional[bool]:
    """True if an earnings date sits between `session`'s close and the next open; None if unknowable.

    `is_earnings_day(ticker, d)` matches earnings on d-1 or d, so asking for d+1 covers "after-close on the
    session" and, on a Friday, for the next trading day too (Monday pre-market; Tuesday after a Monday holiday).
    It also matches an earnings print ON the session (before the open), which exits one night early - the safe
    direction."""
    from agents.market_intelligence.earnings_calendar import is_earnings_day
    unknown = False
    for probe in sorted({session + timedelta(days=1), _next_session(session)}):
        try:
            matched, source = await is_earnings_day(ticker, probe)
        except Exception as e:
            logger.warning("parabolic_short_shadow: earnings lookup for %s %s failed: %s", ticker, probe, e)
            unknown = True
            continue
        if matched:
            return True
        if source == "unavailable":
            unknown = True
    return None if unknown else False


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# The nightly step
# ═════════════════════════════════════════════════════════════════════════════════════════════════

def _new_summary(trade_date: date) -> dict:
    return {"trade_date": str(trade_date), "armed": [], "rejected": [], "triggered": [], "settled": [],
            "closed": [], "deferred": [], "stale": 0, "errors": [], "disabled": False}


def _row(ticker: str, climax_date: date, kind: str, event_date: date, status: str, reason: Optional[str],
         **cols: Any) -> dict:
    return {"ticker": ticker, "climax_date": climax_date, "row_kind": kind, "event_date": event_date,
            "status": status, "reason": reason, **cols}


def _geometry_cols(geo: dict) -> dict:
    return {k: geo.get(k) for k in ("climax_high", "climax_low", "prior_day_low", "limit_price", "atr_14",
                                    "stop_buffer", "stop_price")}


def _risk_fraction() -> float:
    from agents.market_intelligence.constants import RISK_PCT
    return RISK_PCT * SHORT_RISK_FRACTION


async def _decide_candidate(cand: dict, trade_date: date, summary: dict, open_tickers: set) -> None:
    """The arm decision for a climax candidate with no 'arm' row yet - ONE row, written once.

    `open_tickers` - names with an armed episode that has no outcome row yet (read AFTER tonight's advance
    step, so an episode that closed on tonight's own bar no longer blocks). ADR 0020 "NO adds, ever": a name
    holds at most one open episode, so a second climax on it is rejected by name (it is never a second row of
    the same cohort). A newly armed ticker is added to the set, so two candidates for one name cannot both
    arm in one run.

    The one thing that is NOT decided is a failed borrow READ (`infra:`): while a later night can still arm
    this candidate no row is written and it is retried (summary['deferred']); the infra row is written only
    on the last window night, when there is no later night to retry on.
    """
    from agents.market_intelligence import db

    ticker = cand["ticker"]
    d0 = _as_date(cand["scan_date"])
    rows = await db.get_recent_daily_history(ticker, HISTORY_ROWS, end_date=trade_date)
    ci = next((i for i, r in enumerate(rows) if _as_date(r["trade_date"]) == d0), None)
    if ci is None or not _bar_ok(rows[ci]):
        summary["errors"].append(f"{ticker} {d0}: no usable climax bar in mi_daily_closes")
        logger.warning("parabolic_short_shadow: %s %s has no usable climax bar - not decided", ticker, d0)
        return
    sessions_since = len(rows) - 1 - ci
    if sessions_since >= ARM_WINDOW_SESSIONS:
        summary["stale"] += 1          # the window is over before the shadow met it (e.g. pre-deploy history)
        return

    geo = arm_geometry(rows, ci)
    if sessions_since > 0 and _bar_ok(rows[-1]):
        # A late arm (a carried-over or retried candidate): the level in force tonight is the LAST session's
        # low, not the climax day's - record the one the resting order would actually sit at.
        live_level = float(rows[-1]["low_price"])
        geo["prior_day_low"] = live_level
        geo["limit_price"] = short_limit_price(live_level)
    mcap = cand.get("market_cap")
    base = _geometry_cols(geo)
    base.update(market_cap=mcap, risk_fraction=_risk_fraction())
    detail: dict = {"cap_tier": cand.get("cap_tier"), "late_sessions": sessions_since}

    reject: Optional[str] = None
    snapshot: dict = {}
    if ticker in open_tickers:
        reject = REASON_EPISODE_OPEN
        detail["open_episode"] = True
    elif mcap is None:
        reject = FILTER_MCAP_UNKNOWN
    elif mcap < SHORT_MCAP_FLOOR_USD:
        reject = FILTER_MCAP_TOO_SMALL
        detail["floor_usd"] = SHORT_MCAP_FLOOR_USD
    else:
        pre = replay_episode(rows, ci, stop_price=geo["stop_price"], armed_on=trade_date)
        if pre["outcome"] and pre["outcome"]["reason"] == OUT_INVALIDATED:
            reject = REASON_INVALIDATED_BEFORE_ARM      # it closed above the climax high before we could arm
        else:
            b = await check_borrow(ticker)
            snapshot = b["snapshot"]
            if not b["ok"]:
                reject = b["reason"]
                if snapshot.get("error"):
                    detail["borrow_error"] = snapshot["error"]
                if reject.startswith("infra:") and sessions_since < ARM_WINDOW_SESSIONS - 1:
                    # Could not READ the broker, and tomorrow night can still arm this one: no row (rows are
                    # insert-once, so writing now would forfeit it for good). Logged by check_borrow; counted
                    # here and in the audit row, deliberately NOT in `errors` (that pages).
                    summary["deferred"].append({"ticker": ticker, "reason": reject,
                                                "sessions_since": sessions_since, "error": snapshot.get("error")})
                    return
    if reject is not None:
        new = await db.insert_parabolic_short_shadow_row(
            _row(ticker, d0, "arm", trade_date, "rejected", reject, **base, **_borrow_cols(snapshot), detail=detail))
        if new:
            summary["rejected"].append({"ticker": ticker, "reason": reject, "stage": "arm"})
        return

    new = await db.insert_parabolic_short_shadow_row(
        _row(ticker, d0, "arm", trade_date, "armed", None, **base, **_borrow_cols(snapshot), detail=detail))
    if new:
        open_tickers.add(ticker)
        summary["armed"].append({"ticker": ticker, "level": geo["prior_day_low"], "stop": geo["stop_price"]})


async def _earnings_dates_for(ticker: str, rows: list[dict], trigger_idx: int, time_stop: int,
                              checker: Callable[[str, date], Awaitable[Optional[bool]]]) -> tuple[frozenset, list]:
    """Sessions in the held window after whose close an earnings date falls. The last session of the window
    needs no check - the time stop already exits at its close."""
    hit: set = set()
    unknown: list = []
    last = min(len(rows), trigger_idx + time_stop - 1)
    for j in range(trigger_idx, last):
        d = _as_date(rows[j]["trade_date"])
        verdict = await checker(ticker, d)
        if verdict is True:
            hit.add(d)
            break                          # the position leaves at this close; later sessions are moot
        if verdict is None:
            unknown.append(str(d))
    return frozenset(hit), unknown


async def _advance_episode(ep: dict, trade_date: date, summary: dict,
                           earnings_checker: Callable[[str, date], Awaitable[Optional[bool]]]) -> None:
    """Replay one armed episode through `trade_date` and write only the rows that are NEW."""
    from agents.market_intelligence import db

    ticker = ep["ticker"]
    d0 = _as_date(ep["climax_date"])
    armed_on = _as_date(ep["armed_on"])
    base = {
        "climax_high": ep.get("climax_high"), "climax_low": ep.get("climax_low"),
        "atr_14": ep.get("atr_14"), "stop_buffer": ep.get("stop_buffer"), "stop_price": ep.get("stop_price"),
        "risk_fraction": ep.get("risk_fraction"), "market_cap": ep.get("market_cap"),
    }

    async def _outcome(status: str, reason: str, on: date, **extra: Any) -> None:
        detail = extra.pop("detail", None)
        new = await db.insert_parabolic_short_shadow_row(
            _row(ticker, d0, "outcome", on, status, reason, **base, entry_price=ep.get("trigger_entry"),
                 detail=detail, **extra))
        if new:
            entry = {"ticker": ticker, "reason": reason, "realized_r": extra.get("realized_r")}
            (summary["settled"] if status == "settled" else summary["closed"]).append(entry)

    rows = await db.get_recent_daily_history(ticker, HISTORY_ROWS, end_date=trade_date)
    ci = next((i for i, r in enumerate(rows) if _as_date(r["trade_date"]) == d0), None)
    if ci is None or not _bar_ok(rows[ci]):
        if (trade_date - d0).days > STALE_EPISODE_DAYS:
            await _outcome("voided", OUT_VOID_DATA_GAP, trade_date, detail={"why": "climax bar missing"})
        else:
            summary["errors"].append(f"{ticker} {d0}: climax bar missing, episode not advanced")
            logger.warning("parabolic_short_shadow: %s %s climax bar missing - not advanced", ticker, d0)
        return

    # #704: the splits ingest's OWN verdict on every split since the levels were frozen (`stored_price_scale`, the
    # window (armed_on, trade_date]) - the same reading the CB shadow and the HTF settler take. A split the ingest
    # recorded as PHANTOM moved no bar (1.0) and changes nothing here; one it APPLIED restated the history under
    # the frozen levels: void, below. One executed and not yet applied leaves the series on two scales tonight -
    # wait (a deferral, never an `error`, which pages); the 17:00 pull applies it and the next night decides.
    scale = await db.stored_price_scale(ticker, armed_on, trade_date)
    if scale is None:
        if (trade_date - d0).days > STALE_EPISODE_DAYS:
            await _outcome("voided", OUT_VOID_DATA_GAP, trade_date,
                           detail={"why": f"a split stayed unapplied {STALE_EPISODE_DAYS}+ days after the climax"})
        else:
            summary["deferred"].append({"ticker": ticker, "reason": "split_unapplied", "climax_date": str(d0)})
            logger.warning("parabolic_short_shadow: %s %s has a split not yet applied - episode not advanced", ticker, d0)
        return
    stored_high, current_high = ep.get("climax_high"), float(rows[ci]["high_price"])
    legacy_scale = None
    if not db.scale_unmoved(scale):
        # A LEGACY split row (applied before the ingest recorded a verdict, outcome NULL) is read at the table's
        # ratio, so a legacy PHANTOM looks like a real split here. Before #704 this shadow decided those on the DATA
        # alone (the climax-high re-read below), and a phantom left the high where it was - so for a window whose only
        # movers are legacy rows the data still decides, and the void is the re-read's. Any recorded verdict
        # (`applied`, or `skipped_no_data` - which may be a FAILED fetch of a real split, a cliff the re-read cannot
        # see) is the ingest's own word and voids without the re-read, as above.
        if db.split_verdict_recorded(await db.get_split_dates_after(ticker, armed_on, trade_date)) or not stored_high:
            # The ingest restated the history under the frozen arm levels: unbookable - never a made-up R across
            # two price scales (the consolidation shadow's split guard).
            await _outcome("voided", OUT_VOID_RESTATED, trade_date,
                           detail={"stored_climax_high": float(stored_high) if stored_high else None,
                                   "current_climax_high": current_high, "split_scale": scale})
            return
        legacy_scale = scale
    if stored_high and abs(current_high / float(stored_high) - 1.0) > RESTATE_TOLERANCE:
        # Any OTHER restatement (a corrected bar, a split the table never held, a LEGACY split row the data bears out)
        # moved the bars under the frozen levels: the same void. The data check stays as the catch-all behind the
        # split table.
        await _outcome("voided", OUT_VOID_RESTATED, trade_date,
                       detail={"stored_climax_high": float(stored_high), "current_climax_high": current_high,
                               **({"legacy_split_scale": legacy_scale} if legacy_scale is not None else {})})
        return

    if ep.get("trigger_status") == "skipped":
        # A trigger row says the borrow check failed at the trigger, but its outcome row is missing (the
        # run died between the two inserts): finish the pair, never re-decide.
        await _outcome("closed_untriggered", OUT_TRIGGER_SKIPPED, _as_date(ep.get("trigger_date")) or trade_date,
                       detail={"recovered": True})
        return

    stop_price = float(ep["stop_price"])
    res = replay_episode(rows, ci, stop_price=stop_price, armed_on=armed_on)
    unknown_earnings: list = []
    if res["trigger"] is not None:
        earn, unknown_earnings = await _earnings_dates_for(
            ticker, rows, res["trigger"]["idx"], TIME_STOP_SESSIONS, earnings_checker)
        if earn:
            res = replay_episode(rows, ci, stop_price=stop_price, armed_on=armed_on, earnings_after=earn)

    trig = res["trigger"]
    if ep.get("trigger_status") == "triggered" and trig is None and res["state"] != "data_gap":
        await _outcome("voided", OUT_VOID_MISMATCH, trade_date,
                       detail={"why": "a trigger row exists but the replay finds no trigger"})
        return

    if trig is not None and ep.get("trigger_status") is None:
        b = await check_borrow(ticker)              # the SECOND borrow check: at trigger
        trig_row = _row(
            ticker, d0, "trigger", trig["date"], "triggered" if b["ok"] else "skipped", b["reason"],
            **base, prior_day_low=trig["level"], limit_price=trig["limit"], entry_price=trig["entry_price"],
            risk_per_share=trig["risk_per_share"], **_borrow_cols(b["snapshot"]),
            detail={"kind": trig["kind"], "gap_skips": res["gap_skips"],
                    **({"borrow_error": b["snapshot"]["error"]} if b["snapshot"].get("error") else {})})
        if await db.insert_parabolic_short_shadow_row(trig_row) and b["ok"]:
            summary["triggered"].append({"ticker": ticker, "entry": trig["entry_price"], "stop": stop_price})
        if not b["ok"]:
            summary["rejected"].append({"ticker": ticker, "reason": b["reason"], "stage": "trigger"})
            await _outcome("closed_untriggered", OUT_TRIGGER_SKIPPED, trig["date"], detail={"borrow": b["reason"]})
            return
        ep = {**ep, "trigger_status": "triggered", "trigger_entry": trig["entry_price"]}

    out = res["outcome"]
    if out is None:
        if (trade_date - d0).days > STALE_EPISODE_DAYS:
            # Backstop: bars stopped arriving (delisting, a permanent hole) - the episode must still close.
            await _outcome("voided", OUT_VOID_DATA_GAP, trade_date,
                           detail={"why": f"state {res['state']} {STALE_EPISODE_DAYS}+ days after the climax"})
        return
    extra: dict = {}
    if out["status"] == "settled":
        extra = {k: out[k] for k in ("exit_price", "sessions_held", "flush_taken", "flush_price", "realized_r",
                                     "exit_leg_r", "mfe_r", "mae_r")}
        extra["exit_date"] = out["date"]
        extra["risk_per_share"] = trig["risk_per_share"] if trig else None
    detail = {"entry_day_ambiguous": out.get("entry_day_ambiguous", False), "gap_skips": res["gap_skips"]}
    if unknown_earnings:
        detail["earnings_unknown_sessions"] = unknown_earnings
    await _outcome(out["status"], out["reason"], out["date"] or trade_date, detail=detail, **extra)


async def run_parabolic_short_shadow(
    trade_date: date,
    *,
    earnings_checker: Callable[[str, date], Awaitable[Optional[bool]]] = default_earnings_before_next_open,
) -> dict:
    """The nightly step: advance every open episode, then decide new climax candidates (oldest first) against
    the episodes still open. Reads only data <= trade_date. One failing episode is logged and counted in
    `errors` and never stops the others; the caller (the scan job) pages on `errors` and still sends the
    digest. One audit row per run, so a night with nothing to do is distinguishable from a night the step
    did not run."""
    from agents.market_intelligence import db
    from agents.market_intelligence.strategies.registry import should_run

    summary = _new_summary(trade_date)
    if not await should_run("parabolic_short"):
        summary["disabled"] = True
        return summary

    # ADVANCE first, DECIDE second: an episode that closes on tonight's own bar (a close above its climax
    # high is exactly the next day's own climax flag) must be closed before the "one open episode per name"
    # check reads the open set. A newly armed episode has nothing to advance on its arm night - a session on
    # or before `armed_on` cannot trigger and the invalidation was tested at the arm - so nothing is lost.
    open_eps = await db.get_parabolic_short_open_episodes()
    for ep in open_eps:
        try:
            await _advance_episode(ep, trade_date, summary, earnings_checker)
        except Exception as e:
            logger.error("parabolic_short_shadow: advancing %s failed: %s", ep.get("ticker"), e, exc_info=True)
            summary["errors"].append(f"{ep.get('ticker')} advance: {type(e).__name__}: {e}")

    open_tickers = {e["ticker"] for e in await db.get_parabolic_short_open_episodes()}
    # Oldest climax first (the reader returns newest first): with two climaxes on one name in a catch-up run,
    # the earlier one is the episode that would have armed on its own night.
    candidates = sorted(await db.get_parabolic_short_new_candidates(trade_date, NEW_CANDIDATE_LOOKBACK_DAYS),
                        key=lambda c: (_as_date(c["scan_date"]) or date.min, c["ticker"]))
    for cand in candidates:
        try:
            await _decide_candidate(cand, trade_date, summary, open_tickers)
        except Exception as e:
            logger.error("parabolic_short_shadow: deciding %s failed: %s", cand.get("ticker"), e, exc_info=True)
            summary["errors"].append(f"{cand.get('ticker')} decide: {type(e).__name__}: {e}")

    text = (f"armed {len(summary['armed'])}, rejected {len(summary['rejected'])}, "
            f"triggered {len(summary['triggered'])}, settled {len(summary['settled'])}, "
            f"closed {len(summary['closed'])}, deferred {len(summary['deferred'])}, "
            f"errors {len(summary['errors'])} "
            f"({len(open_eps)} episode(s) open going in)")
    await db.log_audit_event("parabolic_short_shadow_run", f"{trade_date}: {text}",
                             json.dumps(summary, default=str))
    return summary
