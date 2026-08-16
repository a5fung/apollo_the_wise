"""2026-08-16 — EXIT-PATH SHADOW RECORDER.

The operator is weighing a stop change (hold through -2R instead of exiting at the ORB
low). Every number behind that fork so far is reconstructed on ONE regime
(docs/roadmap/ep_profitability_program.md §0c). His own framing of the shadow, verbatim:

    "shouldn't we just expand the shadow to all our combination of variables since it
    doesn't cost real money?"

The answer is not N pre-chosen arms — that is exactly the overfitting that killed the
545-parameter grid (32 cells against 5 outlier events, nothing survived a time holdout,
same doc). **RECORD THE PATH, NOT THE RULES.** This module logs what each LIVE position
actually did, at daily resolution (minute resolution on day 0), so ANY exit rule —
including ones not yet proposed — can be scored OFFLINE against real recorded prices,
with no new capture needed for a new candidate.

THE LINE — read this before touching anything here. This module is a passive OBSERVER:
  - It has EXACTLY ONE write target: `mi_exit_path_shadow` (plus `mi_audit_log` via the
    shared `log_audit_event` telemetry helper — never a trade-state table).
  - It NEVER writes to `mi_live_trades`, `mi_live_orders`, or any column any live decision
    reads. It never calls the Alpaca client, `order_manager`, or `live_tracker`.
  - It reads `mi_live_trades` (closed AND open rows — read-only), `mi_intraday_bars`,
    `mi_daily_closes`, and (fallback only) Polygon `get_index_history` — all read paths
    already used elsewhere in this codebase for telemetry.
  - It imports NOTHING from `broker/` — not even `exit_logic.py`. The trail formula
    (`_sma_trail` below) is a deliberate DUPLICATE of `exit_logic.py`'s SMA10/20-max,
    pinned against the live formula by a byte-parity test rather than sharing a call
    path with it (see `_sma_trail`'s docstring for why). Nothing in the live entry/exit
    path imports THIS module either (grep `exit_path_shadow` — the only hits outside
    this file + its tests are the `mi_exit_path_shadow` CREATE TABLE in db.py and the
    one scheduler registration).
  - It runs as an INTELLIGENCE-owned job (see scheduler.py) precisely because it makes
    zero broker calls — same class as giveback_shadow.py / pivot_stop_shadow.py /
    sell_discipline.py, which it follows in file shape.

WHY DAILY-BAR CLOSES, NOT MINUTE-BAR CLOSES, FOR `day_close`. The trail (SMA10/20) and
every close-based field here must match what the LIVE trail actually saw
(`live_tracker._load_exit_state` -> `get_index_history`'s official daily close), not a
5-minute-poll's last print — those differ, sometimes materially on a thin name (the
ETON liquidity lesson, exit_discipline.md 2026-08-15). So `day_open`/`day_high`/
`day_low`/`day_close` are sourced from `mi_daily_closes` (falling back to Polygon
`get_index_history` when a row is missing) for EVERY day. The one exception: day 0's
`day_high`/`day_low` are further RESTRICTED to the in-hold minute window from
`mi_intraday_bars` (clamp B in `order_manager.track_open_position_extremes` —
`filled_at <= t <= min(closed_at, 16:00 ET)`) because a fresh position's excursion must
be measured from the fill, not from the whole day's pre-fill action. This is why the job
runs in the 17:xx EOD-shadow family (giveback 17:38 / pivot_stop 17:42 / sell_discipline
17:46, all after the 17:00 `nightly_data_pull` refresh of `mi_daily_closes`) rather than
the 16:10/16:22 execution-side path-recorder slot: at 16:10/16:22 today's `mi_daily_closes`
row does not exist yet, and a minute-bar proxy for `day_close` would silently make this
table's trail diverge from the live trail on the one number the operator is deciding
against.

SCOPE. Every LIVE fill (`account_mode = 'live'`, `filled_at IS NOT NULL`) — both setups
this system trades, not just MAGNA53. From the fill through close, or 60 calendar days,
whichever comes first (per-trade cap; older still-open positions simply stop growing new
rows past day 60, the already-recorded days are untouched). Idempotent, self-healing
UPSERT keyed on (trade_id, trading_day) — safe to re-run, and a trade already recorded
through its window's end is skipped without any query (cheap as history accumulates).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence.db import get_pool, log_audit_event

# NOTE (THE LINE): this module does NOT import broker/exit_logic.py or anything else
# from broker/. `_sma_trail` below duplicates exit_logic's SMA10/20-max formula rather
# than replaying its stateful ladder (`apply_daily_exit_step`) — a stateful replay would
# need a per-call dummy-state reset (remaining_shares etc.) to avoid its own early-close
# branch, which is exactly the kind of subtle coupling a passive observer should not
# carry. The duplicate is pinned against the live formula by a byte-parity test
# (tests/test_exit_path_shadow.py::test_sma_trail_matches_exit_logic_active_sma_byte_for_byte,
# which imports exit_logic directly — nothing in THIS module ever does) so the two can
# never silently drift.

logger = logging.getLogger(__name__)

# Per-trade cap: stop growing new rows once a position (still open) has been tracked
# this many calendar days from fill. Already-recorded days are untouched.
_MAX_CALENDAR_DAYS = 60

# The profit-trigger level this shadow evaluates. Deliberately a fixed 2.0, NOT
# `constants.PROFIT_TRIGGER_R` — this column answers "did the position ever trade at
# +2R", the level named throughout docs/roadmap/ep_profitability_program.md, independent
# of whatever the live constant is currently set to.
_PROFIT_TRIGGER_R = 2.0

_R_TOUCH_THRESHOLDS = (1.0, 2.0, 3.0, 5.0)


def _f(v) -> Optional[float]:
    """None-safe float (asyncpg NUMERIC arrives as Decimal)."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _et_1600(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 16, 0, tzinfo=_ET)


def _et_0930(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=_ET)


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def _sma_trail(closes: list[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """MAX(SMA10, SMA20), replicating broker/exit_logic.py's DEFAULT 'sma' trail_mode
    (`apply_daily_exit_step` lines ~313-329) EXACTLY.

    Duplicated rather than called — see the module docstring for why this module never
    shares a call path with the live decision function. A byte-parity test
    (test_exit_path_shadow.py::test_trail_matches_exit_logic_formula) pins this against
    `apply_daily_exit_step`'s own `active_sma` output on the same closes list so the two
    can never silently drift.

    `closes`: prior_closes (the stock's own closes from BEFORE fill) + running closes
    from fill day through today, oldest-first — mirrors exit_logic's `trail_closes`
    construction exactly (prior_closes + running_closes, in that order).
    """
    sma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if sma20 is not None:
        trail = sma10 if (sma10 is not None and sma10 > sma20) else sma20
    elif sma10 is not None:
        trail = sma10
    else:
        trail = None
    return sma10, sma20, trail


def compute_realized_r(
    total_pnl: Optional[float], risk_per_share: float, entry_shares: Optional[float],
) -> Optional[float]:
    """Whole-trade R multiple. None when any input is missing/non-positive — never a
    fabricated number (the ADR 0014 no-valid-R-frame lesson)."""
    if total_pnl is None or not risk_per_share or not entry_shares:
        return None
    return total_pnl / (risk_per_share * entry_shares)


def compute_day_row(
    *,
    is_day_zero: bool,
    entry_price: float,
    stop_ref: float,
    risk_per_share: float,
    day_open: Optional[float],
    day_high: float,
    day_low: float,
    day_close: float,
    prior_close: Optional[float],
    prior_worst_adverse_r: float,
    prior_best_favourable_r: float,
    breakeven_armed: bool,
    trail_sma10: Optional[float],
    trail_sma20: Optional[float],
    trail_price: Optional[float],
    is_exit_day: bool = False,
    exit_price: Optional[float] = None,
    exit_reason: Optional[str] = None,
    realized_r: Optional[float] = None,
) -> dict[str, Any]:
    """Pure. Every derived field for one `mi_exit_path_shadow` row from already-resolved
    daily OHLC + trail inputs. No IO, no DB, no broker — see module docstring (THE LINE).

    `prior_worst_adverse_r` / `prior_best_favourable_r`: the RUNNING value through
    yesterday (seed 0.0 on day 0) — this function folds today's excursion in and returns
    the new running value; it does not read or write any table itself.
    """
    adverse_r = (entry_price - day_low) / risk_per_share
    favourable_r = (day_high - entry_price) / risk_per_share
    worst_adverse_r = max(prior_worst_adverse_r, adverse_r)
    best_favourable_r = max(prior_best_favourable_r, favourable_r)
    close_r = (day_close - entry_price) / risk_per_share

    gap_r = None
    gap_through_stop_ref = None
    if not is_day_zero and prior_close is not None and day_open is not None:
        gap_r = (day_open - prior_close) / risk_per_share
        gap_through_stop_ref = day_open < stop_ref

    close_below_trail = (day_close < trail_price) if trail_price is not None else None

    return {
        "day_open": day_open, "day_high": day_high, "day_low": day_low, "day_close": day_close,
        "prior_close": prior_close,
        "gap_r": gap_r, "gap_through_stop_ref": gap_through_stop_ref,
        "adverse_excursion_r": adverse_r,
        "worst_adverse_excursion_r": worst_adverse_r,
        "favourable_excursion_r": favourable_r,
        "best_favourable_excursion_r": best_favourable_r,
        "close_r": close_r,
        "touched_minus_1r": adverse_r >= _R_TOUCH_THRESHOLDS[0],
        "touched_minus_2r": adverse_r >= _R_TOUCH_THRESHOLDS[1],
        "touched_minus_3r": adverse_r >= _R_TOUCH_THRESHOLDS[2],
        "touched_minus_5r": adverse_r >= _R_TOUCH_THRESHOLDS[3],
        "closed_above_stop_ref": day_close > stop_ref,
        "touched_plus_2r": favourable_r >= _PROFIT_TRIGGER_R,
        "breakeven_armed": bool(breakeven_armed),
        "trail_sma10": trail_sma10, "trail_sma20": trail_sma20, "trail_price": trail_price,
        "close_below_trail": close_below_trail,
        "is_exit_day": bool(is_exit_day),
        "exit_price": exit_price, "exit_reason": exit_reason, "realized_r": realized_r,
    }


# ── DB orchestration ────────────────────────────────────────────────────────────────────

_ELIGIBLE_TRADES_SQL = """
    SELECT t.id, t.ticker, t.account_mode, t.signal_type, t.alert_date,
           t.entry_price, t.orb_low, t.hard_stop, t.entry_shares,
           t.filled_at, t.closed_at, t.breakeven_active, t.exits,
           t.total_pnl, t.pnl_attribution,
           MAX(s.trading_day) AS max_recorded_day
    FROM mi_live_trades t
    LEFT JOIN mi_exit_path_shadow s ON s.trade_id = t.id
    WHERE t.account_mode = 'live'  -- mode-ok: 2026-08-16 shadow scope is real-money trades only (see module docstring)
      AND t.filled_at IS NOT NULL
    GROUP BY t.id
"""

_DAILY_BAR_SQL = """
    SELECT open_price, high_price, low_price, close FROM mi_daily_closes
    WHERE ticker = $1 AND trade_date = $2
"""

_PRIOR_CLOSES_SQL = """
    SELECT close FROM mi_daily_closes
    WHERE ticker = $1 AND trade_date >= $2::date AND trade_date <= $3::date
    ORDER BY trade_date
"""

_MINUTE_HL_SQL = """
    SELECT MIN(low) AS lo, MAX(high) AS hi, count(*) AS n FROM mi_intraday_bars
    WHERE ticker = $1 AND bar_time >= $2 AND bar_time <= $3
"""

_UPSERT_SQL = """
    INSERT INTO mi_exit_path_shadow (
        trade_id, ticker, account_mode, signal_type, alert_date, fill_day,
        trading_day, trading_day_index, hold_days, entry_price, stop_ref, risk_per_share,
        entry_shares, day_open, day_high, day_low, day_close, bar_source,
        prior_close, gap_r, gap_through_stop_ref,
        adverse_excursion_r, worst_adverse_excursion_r,
        favourable_excursion_r, best_favourable_excursion_r, close_r,
        touched_minus_1r, touched_minus_2r, touched_minus_3r, touched_minus_5r,
        closed_above_stop_ref, touched_plus_2r, breakeven_armed,
        trail_sma10, trail_sma20, trail_price, close_below_trail,
        is_exit_day, exit_price, exit_reason, realized_r, pnl_attribution
    ) VALUES (
        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,
        $22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,$37,$38,$39,$40,$41
    )
    ON CONFLICT (trade_id, trading_day) DO UPDATE SET
        day_open = EXCLUDED.day_open, day_high = EXCLUDED.day_high,
        day_low = EXCLUDED.day_low, day_close = EXCLUDED.day_close,
        bar_source = EXCLUDED.bar_source, prior_close = EXCLUDED.prior_close,
        gap_r = EXCLUDED.gap_r, gap_through_stop_ref = EXCLUDED.gap_through_stop_ref,
        adverse_excursion_r = EXCLUDED.adverse_excursion_r,
        worst_adverse_excursion_r = EXCLUDED.worst_adverse_excursion_r,
        favourable_excursion_r = EXCLUDED.favourable_excursion_r,
        best_favourable_excursion_r = EXCLUDED.best_favourable_excursion_r,
        close_r = EXCLUDED.close_r,
        touched_minus_1r = EXCLUDED.touched_minus_1r, touched_minus_2r = EXCLUDED.touched_minus_2r,
        touched_minus_3r = EXCLUDED.touched_minus_3r, touched_minus_5r = EXCLUDED.touched_minus_5r,
        closed_above_stop_ref = EXCLUDED.closed_above_stop_ref,
        touched_plus_2r = EXCLUDED.touched_plus_2r, breakeven_armed = EXCLUDED.breakeven_armed,
        trail_sma10 = EXCLUDED.trail_sma10, trail_sma20 = EXCLUDED.trail_sma20,
        trail_price = EXCLUDED.trail_price, close_below_trail = EXCLUDED.close_below_trail,
        is_exit_day = EXCLUDED.is_exit_day, exit_price = EXCLUDED.exit_price,
        exit_reason = EXCLUDED.exit_reason, realized_r = EXCLUDED.realized_r,
        pnl_attribution = EXCLUDED.pnl_attribution, computed_at = NOW()
"""

_UPSERT_COLS = (
    "trade_id", "ticker", "account_mode", "signal_type", "alert_date", "fill_day",
    "trading_day", "trading_day_index", "hold_days", "entry_price", "stop_ref",
    "risk_per_share", "entry_shares", "day_open", "day_high", "day_low", "day_close",
    "bar_source", "prior_close", "gap_r", "gap_through_stop_ref",
    "adverse_excursion_r", "worst_adverse_excursion_r",
    "favourable_excursion_r", "best_favourable_excursion_r", "close_r",
    "touched_minus_1r", "touched_minus_2r", "touched_minus_3r", "touched_minus_5r",
    "closed_above_stop_ref", "touched_plus_2r", "breakeven_armed",
    "trail_sma10", "trail_sma20", "trail_price", "close_below_trail",
    "is_exit_day", "exit_price", "exit_reason", "realized_r", "pnl_attribution",
)


async def _fetch_daily_bar(
    conn, ticker: str, trading_day: date,
) -> Optional[tuple[Optional[float], Optional[float], Optional[float], float, str]]:
    """(open, high, low, close, bar_source) for one trading day. `mi_daily_closes`
    primary; Polygon `get_index_history` fallback (today's row may not be ingested yet
    on a rerun, or a genuine gap). None only when NEITHER source has the day."""
    row = await conn.fetchrow(_DAILY_BAR_SQL, ticker, trading_day)
    if row is not None and row["close"] is not None:
        return _f(row["open_price"]), _f(row["high_price"]), _f(row["low_price"]), float(row["close"]), "daily"

    from agents.market_intelligence.collector import get_index_history
    d_str = trading_day.strftime("%Y-%m-%d")
    try:
        bars = await get_index_history(ticker, d_str, d_str)
    except Exception as e:  # loud-ok: caller logs the None outcome
        logger.warning(f"exit_path_shadow: Polygon fallback failed for {ticker} {trading_day}: {e}")
        bars = []
    if not bars or bars[0].get("c") is None:
        return None
    b = bars[0]
    return b.get("o"), b.get("h"), b.get("l"), float(b["c"]), "polygon_fallback"


async def _restrict_day_zero_hl(
    conn, ticker: str, filled_at: datetime, trading_day: date, closed_at: Optional[datetime],
) -> Optional[tuple[float, float]]:
    """In-hold minute-bar low/high for the fill day only — clamp B semantics (matches
    `order_manager.track_open_position_extremes` exactly): `filled_at <= t <=
    min(closed_at, 16:00 ET)`. None when no minute bars exist for the window (falls back
    to the full daily bar's high/low, less precise but never silently wrong — flagged via
    `bar_source`)."""
    window_end = _et_1600(trading_day)
    if closed_at is not None and closed_at.astimezone(_ET).date() == trading_day:
        window_end = min(window_end, closed_at)
    row = await conn.fetchrow(_MINUTE_HL_SQL, ticker, filled_at, window_end)
    if row is None or not row["n"] or row["lo"] is None:
        return None
    return float(row["lo"]), float(row["hi"])


async def _fetch_prior_closes(conn, ticker: str, alert_date: date) -> list[float]:
    """The stock's own closes from BEFORE `alert_date`, oldest-first — the SAME 40-
    calendar-day window ending the day before `alert_date` that
    `live_tracker._load_exit_state` uses, so the trail this table records matches what
    the live trail actually saw. `mi_daily_closes` primary; Polygon fallback."""
    start = alert_date - timedelta(days=40)
    end = alert_date - timedelta(days=1)
    rows = await conn.fetch(_PRIOR_CLOSES_SQL, ticker, start, end)
    closes = [float(r["close"]) for r in rows if r["close"] is not None]
    if closes:
        return closes
    from agents.market_intelligence.collector import get_index_history
    try:
        hist = await get_index_history(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        return [float(b["c"]) for b in (hist or []) if b.get("c") is not None]
    except Exception as e:  # loud-ok: fail-soft, byte-identical to empty prior_closes (matches live_tracker)
        logger.warning(f"exit_path_shadow: prior-close fetch failed for {ticker}: {e}")
        return []


def _trading_days(fill_day: date, last_day: date) -> list[date]:
    from agents.market_intelligence.trading_calendar import get_market_status
    out = []
    d = fill_day
    while d <= last_day:
        if get_market_status(d).is_trading_day:
            out.append(d)
        d += timedelta(days=1)
    return out


async def _record_one_trade(conn, trade: dict, today: date) -> int:
    ticker = trade["ticker"]
    filled_at: datetime = trade["filled_at"]
    fill_day = filled_at.astimezone(_ET).date()
    alert_date = trade["alert_date"]
    closed_at: Optional[datetime] = trade["closed_at"]
    closed_day = closed_at.astimezone(_ET).date() if closed_at else None

    cutoff_day = min(today, fill_day + timedelta(days=_MAX_CALENDAR_DAYS))
    last_day = min(cutoff_day, closed_day) if closed_day else cutoff_day
    if last_day < fill_day:
        return 0

    max_recorded = trade.get("max_recorded_day")
    if max_recorded is not None and max_recorded >= last_day:
        return 0  # already fully recorded through this trade's window

    entry_price = _f(trade["entry_price"])
    orb_low = _f(trade["orb_low"])
    hard_stop = _f(trade["hard_stop"])
    stop_ref = orb_low if orb_low is not None else hard_stop
    if entry_price is None or stop_ref is None or stop_ref >= entry_price:
        await log_audit_event(
            "exit_path_shadow_skipped",
            f"{ticker} trade {trade['id']}: no valid R frame "
            f"(entry={entry_price} orb_low={orb_low} hard_stop={hard_stop})",
        )
        return 0
    risk_per_share = entry_price - stop_ref
    entry_shares = _f(trade["entry_shares"])

    exits = trade["exits"] if isinstance(trade["exits"], list) else json.loads(trade["exits"] or "[]")
    partial_days: set[date] = set()
    for e in exits:
        if e.get("reason") != "partial_profit":
            continue
        try:
            t = datetime.fromisoformat(e["time"])
            if t.tzinfo is None:
                t = t.replace(tzinfo=_ET)
            partial_days.add(t.astimezone(_ET).date())
        except Exception:  # loud-ok: a malformed timestamp just can't arm breakeven early; not fatal
            continue

    trading_days = _trading_days(fill_day, last_day)
    prior_closes = await _fetch_prior_closes(conn, ticker, alert_date)

    running_closes: list[float] = []
    prior_close_val: Optional[float] = prior_closes[-1] if prior_closes else None
    worst = 0.0
    best = 0.0
    written = 0

    for idx, trading_day in enumerate(trading_days):
        is_day_zero = idx == 0
        bar = await _fetch_daily_bar(conn, ticker, trading_day)
        if bar is None:
            logger.warning(f"exit_path_shadow: no bar for {ticker} {trading_day} — skipping day")
            # A skipped day breaks the "prior_close is YESTERDAY's close" invariant for
            # whichever day gets recorded next — without this reset, that next row's
            # gap_r would silently describe a multi-day gap as if it were overnight
            # (found in review). NULL is honest; a mislabelled gap on the exact column
            # the stop-fork decision reads is not.
            prior_close_val = None
            continue
        day_open, day_high, day_low, day_close, bar_source = bar

        if is_day_zero:
            hl = await _restrict_day_zero_hl(conn, ticker, filled_at, trading_day, closed_at)
            if hl is not None:
                day_low, day_high = hl
                bar_source = f"{bar_source}+minute_hl"

        running_closes.append(day_close)
        trail_closes = prior_closes + running_closes
        sma10, sma20, trail_price = _sma_trail(trail_closes)

        is_exit_day = closed_day == trading_day
        exit_price = exit_reason = realized_r = None
        if is_exit_day and exits:
            last_exit = exits[-1]
            exit_price = _f(last_exit.get("price"))
            exit_reason = last_exit.get("reason")
            realized_r = compute_realized_r(_f(trade["total_pnl"]), risk_per_share, entry_shares)

        breakeven_armed = any(pd <= trading_day for pd in partial_days)

        row = compute_day_row(
            is_day_zero=is_day_zero, entry_price=entry_price, stop_ref=stop_ref,
            risk_per_share=risk_per_share,
            day_open=day_open, day_high=day_high, day_low=day_low, day_close=day_close,
            prior_close=prior_close_val,
            prior_worst_adverse_r=worst, prior_best_favourable_r=best,
            breakeven_armed=breakeven_armed,
            trail_sma10=sma10, trail_sma20=sma20, trail_price=trail_price,
            is_exit_day=is_exit_day, exit_price=exit_price, exit_reason=exit_reason,
            realized_r=realized_r,
        )
        worst = row["worst_adverse_excursion_r"]
        best = row["best_favourable_excursion_r"]
        prior_close_val = day_close

        values = {
            "trade_id": trade["id"], "ticker": ticker, "account_mode": trade["account_mode"],
            "signal_type": trade.get("signal_type"), "alert_date": alert_date, "fill_day": fill_day,
            "trading_day": trading_day, "trading_day_index": idx,
            "hold_days": (trading_day - alert_date).days,
            "entry_price": entry_price, "stop_ref": stop_ref, "risk_per_share": risk_per_share,
            "entry_shares": entry_shares, "bar_source": bar_source,
            "pnl_attribution": trade.get("pnl_attribution"),
            **row,
        }
        await conn.execute(_UPSERT_SQL, *(values[c] for c in _UPSERT_COLS))
        written += 1

    return written


async def record_exit_path_shadow(today: Optional[date] = None) -> int:
    """Write/refresh one `mi_exit_path_shadow` row per (LIVE trade, trading day) — full
    per-trade backfill on first sight, idempotent UPSERT thereafter. Pure DB read/compute/
    write; no broker calls, no live-trade mutation (THE LINE — see module docstring).
    Returns rows written/updated."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()

    pool = await get_pool()
    written = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(_ELIGIBLE_TRADES_SQL)
        for r in rows:
            trade = dict(r)
            try:
                written += await _record_one_trade(conn, trade, today)
            except Exception as e:
                logger.error(f"exit_path_shadow: trade {trade.get('id')} ({trade.get('ticker')}) failed: {e}")
                try:
                    await log_audit_event(
                        "exit_path_shadow_error",
                        f"{trade.get('ticker')} trade {trade.get('id')}: {type(e).__name__}: {e}",
                    )
                except Exception:  # loud-ok: log_audit_event self-catches; logger.error above already fired
                    pass
    if written:
        try:
            await log_audit_event(
                "exit_path_shadow_recorded", f"recorded/updated {written} exit-path row(s) for {today}",
            )
        except Exception as _e:  # loud-ok: telemetry-of-telemetry; the rows are already durable
            logger.warning(f"exit_path_shadow audit emit failed (non-fatal): {_e}")
    return written
