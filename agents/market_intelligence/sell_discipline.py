"""#508 workstream 1 — the unified SELL-DISCIPLINE RECORDER (record + display, NO rule).

Operator framing (2026-07-27, verbatim intent): the scattered exit evidence must answer ONE
question per trade — **how much of the peak did we keep?** Tables and jobs stay separate
(mi_position_mgmt_decisions / mi_giveback_shadow / mi_pivot_stop_shadow / the #306 path
recorder are all left alone); this module unifies the OUTPUT: one durable record per closed
trade (what it REACHED, what it KEPT, and the context a candidate rule needs), rendered on
the management-judge Telegram the operator already receives.

THE LINE: this module records and displays. It contains NO exit rule, changes NO live exit,
submits/cancels/modifies NOTHING. Workstream 2 replays candidate rules against these records;
any live change is the operator's call via CHANGE_PROCESS + sign-off.

Two peak axes, both recorded (a daily-close-only store structurally cannot see an intraday
round trip — 7 of the first 11 live closes were same-day):
  • intraday axis — peak_r from in-hold minute bars (mi_intraday_bars, full coverage from
    2026-07-25) with bar-level WHEN; else highest_price_seen (the extremes tracker: 5-min
    polls pre-07-25, window starts 09:30, blind under ~10 minutes — the record carries
    peak_source so the surface never implies precision the data lacks).
  • daily-close axis — peak_close_r over closes where the trade was still open at that
    day's 16:00 ET (what a close-driven rule like the giveback lock could have seen).

Regime is RECONSTRUCTED at read time via `mi_market_regime ON regime_date = alert_date` —
never denormalised into the record (mi_consolidation_entry_shadow.regime_at_entry showed
where that road goes: 41 of 265 rows populated).

R denominator = entry − hard_stop (the actual placed initial stop; falls back to orb_low).
NB the judge digest's own R uses entry − orb_low (ADR 0014) — identical for MAGNA53, may
differ for 9M Day 2 (prior-day-low stops).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Iterable, Optional

from shared.dates import _ET

from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# Catch-up window (the #310 lesson: never an exact closed_at::date = today match — re-scan
# recently-closed, not-yet-recorded trades every run). 120d spans the whole dual-account era
# and matches mi_intraday_bars' retention horizon, so the first prod run backfills the full
# live cohort plus the paper history while its bar/extremes sources still exist.
_CATCHUP_LOOKBACK_DAYS = 120

# Price-match tolerance when attributing the peak value to a specific day/bar. Prices on the
# consolidated tape are cents-quantized; extremes/daily/minute sources all read the same tape.
_PEAK_MATCH_TOL = 0.005

# Minute-bar WHEN needs credible coverage: pre-07-25 rows have a single fill-seed bar whose
# high can coincide with the true peak (e.g. a never-above-entry trade) — 1 bar must not
# masquerade as bar-level precision.
_MIN_BARS_FOR_WHEN = 3

_VERDICT_ABBR = {"HOLD": "H", "PARTIAL_TAKE": "PT", "TRAIL_TIGHTEN": "TT", "FORCE_EXIT": "FX"}


def _f(v) -> Optional[float]:
    """None-safe float (asyncpg NUMERIC arrives as Decimal)."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def trade_risk_per_share(trade: dict) -> Optional[float]:
    """Original entry risk per share: entry − hard_stop, falling back to entry − orb_low.
    None when neither gives a positive risk (no valid R frame — never a negative/zero
    denominator, the ADR 0014 trap)."""
    entry = _f(trade.get("entry_price"))
    if entry is None:
        return None
    for stop_key in ("hard_stop", "orb_low"):
        stop = _f(trade.get(stop_key))
        if stop is not None and stop < entry:
            return entry - stop
    return None


def _judge_context(decisions: Iterable[dict]) -> dict:
    """Aggregate the position's mi_position_mgmt_decisions rows (may be empty): how many
    verdicts, the last one, and the FIRST non-HOLD (did the judge warn before the round
    trip?). Also folds stop_above_entry observed on any judged day."""
    rows = sorted((dict(d) for d in decisions), key=lambda d: d["decision_date"])
    out = {
        "judge_verdicts_n": len(rows),
        "judge_last_verdict": None, "judge_last_verdict_date": None, "judge_last_verdict_r": None,
        "judge_first_warn_verdict": None, "judge_first_warn_date": None, "judge_first_warn_r": None,
        "judge_saw_stop_above_entry": False,
    }
    if not rows:
        return out
    last = rows[-1]
    out["judge_last_verdict"] = last.get("verdict")
    out["judge_last_verdict_date"] = last.get("decision_date")
    out["judge_last_verdict_r"] = _f(last.get("r_multiple"))
    for r in rows:
        if r.get("stop_above_entry"):
            out["judge_saw_stop_above_entry"] = True
        if out["judge_first_warn_verdict"] is None and r.get("verdict") not in (None, "HOLD"):
            out["judge_first_warn_verdict"] = r.get("verdict")
            out["judge_first_warn_date"] = r.get("decision_date")
            out["judge_first_warn_r"] = _f(r.get("r_multiple"))
    return out


def compute_sell_record(
    trade: dict,
    *,
    minute_peak: Optional[tuple[float, datetime]] = None,
    minute_bars_n: int = 0,
    daily_rows: Iterable[dict] = (),
    decisions: Iterable[dict] = (),
) -> Optional[dict]:
    """Pure, fixture-testable. One sell-discipline record for one CLOSED trade.

    trade        — an mi_live_trades row (dict); needs entry/hard_stop/shares/pnl/
                   filled_at/closed_at (+ stop_price, breakeven_active, partial_taken,
                   highest_price_seen).
    minute_peak  — (high, bar_time) argmax over IN-HOLD minute bars (already clamped
                   filled_at ≤ t ≤ closed_at and 09:30–16:00 ET by the caller's SQL).
    minute_bars_n— in-hold bar count (coverage honesty; WHEN needs ≥ _MIN_BARS_FOR_WHEN).
    daily_rows   — mi_daily_closes rows {trade_date, high_price, close} spanning
                   [fill_day, close_day] ET for the ticker.
    decisions    — the position's mi_position_mgmt_decisions rows.

    Returns None when the trade has no valid R frame or isn't a completed round trip
    (no filled_at/closed_at) — the recorder audits those instead of writing junk.
    """
    risk = trade_risk_per_share(trade)
    entry = _f(trade.get("entry_price"))
    shares = _f(trade.get("entry_shares")) or 0.0
    filled_at, closed_at = trade.get("filled_at"), trade.get("closed_at")
    if risk is None or entry is None or shares <= 0 or not filled_at or not closed_at:
        return None

    fill_day = filled_at.astimezone(_ET).date()
    close_day = closed_at.astimezone(_ET).date()
    risk_dollars = risk * shares
    realized_pnl = _f(trade.get("total_pnl"))
    realized_r = round(realized_pnl / risk_dollars, 4) if realized_pnl is not None else None

    daily = [dict(r) for r in daily_rows
             if r.get("trade_date") and fill_day <= r["trade_date"] <= close_day]
    daily.sort(key=lambda r: r["trade_date"])

    # ── intraday-axis peak: ladder over the in-hold sources ──────────────────
    hps = _f(trade.get("highest_price_seen"))
    mb_price = _f(minute_peak[0]) if minute_peak else None
    mb_time = minute_peak[1] if minute_peak else None
    # Strict middle days (fill_day < d < close_day) are in-hold for the WHOLE session, so
    # their daily highs are peak candidates. Fill/close-day daily highs are NOT candidates
    # by themselves (pre-fill / post-exit prints contaminate) — they only ATTRIBUTE a value
    # that an in-hold-clamped source (extremes / minute bars) already established.
    mid_days = [r for r in daily if fill_day < r["trade_date"] < close_day]
    mid_max = max((_f(r["high_price"]) for r in mid_days if r.get("high_price") is not None),
                  default=None)

    candidates = [p for p in (hps, mb_price, mid_max) if p is not None]
    peak_price = max(candidates) if candidates else None

    peak_time: Optional[datetime] = None
    peak_day: Optional[date] = None
    peak_source = "none"
    if peak_price is not None:
        near = lambda a, b: a is not None and b is not None and abs(a - b) <= _PEAK_MATCH_TOL
        if near(mb_price, peak_price) and minute_bars_n >= _MIN_BARS_FOR_WHEN:
            peak_time = mb_time
            peak_day = mb_time.astimezone(_ET).date() if mb_time else None
            peak_source = "minute_bars"
        elif fill_day == close_day:
            # Same-day round trip: the peak day is trivially the trade day; only the
            # time-of-day is unknown without minute bars.
            peak_day = fill_day
            peak_source = "extremes" if near(hps, peak_price) else "daily_high"
        else:
            mid_matches = [r["trade_date"] for r in mid_days if near(_f(r["high_price"]), peak_price)]
            if mid_matches:
                peak_day = mid_matches[0]  # first touch on ties
                peak_source = "daily_high" + ("+extremes" if near(hps, peak_price) else "")
            elif near(hps, peak_price):
                # hps is in-hold by construction (the extremes tracker clamps); if it equals
                # exactly one edge day's session high, that day is the peak day.
                edge = [r["trade_date"] for r in daily
                        if r["trade_date"] in (fill_day, close_day) and near(_f(r["high_price"]), peak_price)]
                if len(edge) >= 1:
                    peak_day = edge[0]
                    peak_source = "extremes+daily"
                else:
                    peak_source = "extremes"
            else:
                peak_source = "extremes"

    peak_r = round((peak_price - entry) / risk, 4) if peak_price is not None else None

    # ── daily-close axis: closes where the trade was still open at that 16:00 ET ─────────
    peak_close = peak_close_day = None
    for r in daily:
        c = _f(r.get("close"))
        if c is None:
            continue
        close_ts = datetime.combine(r["trade_date"], dt_time(16, 0), tzinfo=_ET)
        if filled_at <= close_ts and closed_at > close_ts:
            if peak_close is None or c > peak_close:
                peak_close, peak_close_day = c, r["trade_date"]
    peak_close_r = round((peak_close - entry) / risk, 4) if peak_close is not None else None

    # ── hold-day indexing off the ticker's own trading dates ─────────────────
    day_list = sorted({r["trade_date"] for r in daily} | {fill_day, close_day})
    hold_trading_days = len(day_list)
    peak_hold_day = (day_list.index(peak_day) + 1) if peak_day in day_list else None

    jc = _judge_context(decisions)
    stop_price = _f(trade.get("stop_price"))
    stop_above_entry_ever = bool(
        (stop_price is not None and stop_price > entry)
        or trade.get("breakeven_active")
        or jc.pop("judge_saw_stop_above_entry")
    )

    # ── ADR-NORMALISED axis (#508, 2026-07-30) — R is NOT comparable across trades ──
    # MEASURED on the live cohort: stop width ranges 0.14x to 0.97x of the stock's OWN
    # 20d average daily range — a 7x spread. So the R denominator is mostly measuring
    # STOP TIGHTNESS, not trade quality. MANE and QBTS made near-identical moves
    # (8.76% vs 8.64%, both ~1.1 ADR) and scored 7.92R vs 3.74R. NVCR made the LARGEST
    # real move of the cohort (1.90 ADR) and scored the LOWEST R of the four movers.
    #
    # A "+3R partial" therefore fires constantly on tight-stopped names and almost never
    # on wide-stopped ones, INDEPENDENT of whether the trade is working. This field
    # records the same excursion in units that mean the same thing on every ticker, so
    # the operator's tuning axes (regime, biotech/small-cap character) are not
    # confounded by stop width when the cohort is finally large enough to read.
    #
    # DISPLAY/TELEMETRY ONLY — nothing reads this to make a decision. Recording it NOW
    # so the data accruing from today is usable later; 25 more trades measured on an
    # uncalibrated R would leave us exactly where we are, with more rows.
    adr_pct = _f(trade.get("adr_20_pct"))
    # ⚠ FIXED 2026-08-01 — this read `stop_price`, which is the CURRENT stop on the
    # trade row, i.e. the TRAILED stop by the time a trade closes. Every trade that
    # RAN had its stop moved up, so stop_pct came out ~0 (or negative), and the whole
    # ADR family derived from it was garbage on exactly the winners this field exists
    # to measure. Verified over the 43-row cohort: every paper trade above +1.02R was
    # corrupted (BW/FTRE/RCAT/TEAM/KURA/SMCI/QURE/PURR recorded stop_pct = 0.0000 with
    # true entry risk 0.78-10.56%; GOOGL -3.47 vs 0.83; FPS -10.96 vs 11.42), and CRSR
    # recorded 0.0276 against a true 4.2454 — which made it look like +12.36R on 0.06
    # of a daily range when the real move was ~9.5 daily ranges on a mid-range stop.
    # The 12 LIVE rows happened to be clean ONLY because all 12 lost, so no stop ever
    # trailed above entry — the bug was invisible in the money cohort by luck.
    # `risk` IS the original entry risk (it already drives realized_r); use it.
    stop_pct = round(risk / entry * 100, 4) if (risk is not None and entry) else None
    stop_per_adr = round(stop_pct / adr_pct, 4) if (
        stop_pct is not None and adr_pct) else None
    peak_adr = round(peak_r * stop_pct / adr_pct, 4) if (
        peak_r is not None and stop_pct is not None and adr_pct) else None
    realized_adr = round(realized_r * stop_pct / adr_pct, 4) if (
        realized_r is not None and stop_pct is not None and adr_pct) else None

    giveback_r = round(peak_r - realized_r, 4) if (peak_r is not None and realized_r is not None) else None
    capture_pct = (round(realized_r / peak_r, 4)
                   if (peak_r is not None and peak_r > 0 and realized_r is not None) else None)

    return {
        "trade_id": trade.get("id"),
        "ticker": trade.get("ticker"),
        "signal_type": trade.get("signal_type"),
        "account_mode": trade.get("account_mode"),
        "alert_date": trade.get("alert_date"),
        "fill_day": fill_day, "close_day": close_day,
        "filled_at": filled_at, "closed_at": closed_at,
        "entry_price": entry, "risk_per_share": round(risk, 6), "entry_shares": shares,
        "realized_pnl": realized_pnl, "realized_r": realized_r,
        "peak_price": peak_price, "peak_r": peak_r,
        "peak_time": peak_time, "peak_day": peak_day, "peak_hold_day": peak_hold_day,
        "peak_source": peak_source, "peak_bars_n": minute_bars_n,
        "peak_close": peak_close, "peak_close_r": peak_close_r, "peak_close_day": peak_close_day,
        "giveback_r": giveback_r, "capture_pct": capture_pct,
        # adr_20_pct stored RAW (2026-08-01): the review gate and any future rule must
        # key off the ticker's own daily range directly, NEVER off a stop-derived
        # ratio — a ratio inherits any stop-recording defect, which is what corrupted
        # every winner above.
        "adr_20_pct": round(adr_pct, 4) if adr_pct is not None else None,
        "stop_pct": stop_pct, "stop_per_adr": stop_per_adr,
        "peak_adr": peak_adr, "realized_adr": realized_adr,
        "hold_trading_days": hold_trading_days,
        "stop_above_entry_ever": stop_above_entry_ever,
        "partial_taken": bool(trade.get("partial_taken")),
        "pnl_attribution": trade.get("pnl_attribution"),
        **jc,
    }


# ── The recorder job (writes mi_sell_discipline_records; idempotent catch-up) ─────────────

_SCAN_SQL = """
    SELECT t.id, t.ticker, t.signal_type, t.account_mode, t.alert_date, t.entry_price,
           t.hard_stop, t.orb_low, t.entry_shares, t.total_pnl, t.stop_price,
           t.breakeven_active, t.partial_taken, t.highest_price_seen, t.filled_at,
           t.closed_at, t.pnl_attribution,
           -- 20d ADR as of the alert, from the ticker's OWN prior bars (#508,
           -- 2026-07-30). Needed because R is not comparable across trades — see the
           -- ADR-normalised block in compute_sell_record. Strictly PRE-alert bars, so
           -- no lookahead. NULL when a ticker has too little history; the normalised
           -- fields then render NULL rather than a fabricated number.
           (SELECT AVG((d.high_price - d.low_price) / NULLIF(d.close, 0) * 100)
              FROM mi_daily_closes d
             WHERE d.ticker = t.ticker
               AND d.trade_date <  t.alert_date
               AND d.trade_date >= t.alert_date - 30) AS adr_20_pct
    FROM mi_live_trades t
    WHERE t.status = 'closed' AND t.filled_at IS NOT NULL AND t.closed_at IS NOT NULL
      -- $2 carries an explicit ::int cast: Postgres has BOTH `date - integer -> date`
      -- and `date - date -> integer`, so an uncast param lets asyncpg infer `date`
      -- and the comparison becomes `date >= integer` — the exact class that crashed
      -- pivot_stop_shadow nightly 07-25→07-27. Never drop the casts.
      AND (t.closed_at AT TIME ZONE 'America/New_York')::date
          BETWEEN ($1::date - $2::int) AND $1::date
      AND NOT EXISTS (SELECT 1 FROM mi_sell_discipline_records s WHERE s.trade_id = t.id)
      -- #528/#512 family: a trade already known to have no valid R frame (structural —
      -- entry/hard_stop/orb_low/shares don't change once closed) is remembered in
      -- mi_sell_discipline_skips so it stops re-entering this scan every night forever
      -- (CRMD trade 137, found 2026-08-08). See record_sell_discipline's skip-write.
      AND NOT EXISTS (SELECT 1 FROM mi_sell_discipline_skips k WHERE k.trade_id = t.id)
"""

_MINUTE_PEAK_SQL = """
    SELECT high, bar_time FROM mi_intraday_bars
    WHERE ticker = $1 AND bar_time >= $2 AND bar_time <= $3
      AND (bar_time AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '16:00'
    ORDER BY high DESC, bar_time ASC LIMIT 1
"""

_MINUTE_COUNT_SQL = """
    SELECT count(*) AS n FROM mi_intraday_bars
    WHERE ticker = $1 AND bar_time >= $2 AND bar_time <= $3
      AND (bar_time AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '16:00'
"""

_DAILY_SQL = """
    SELECT trade_date, high_price, close FROM mi_daily_closes
    WHERE ticker = $1 AND trade_date >= $2::date AND trade_date <= $3::date
    ORDER BY trade_date
"""

_DECISIONS_SQL = """
    SELECT decision_date, verdict, r_multiple, stop_above_entry
    FROM mi_position_mgmt_decisions WHERE position_id = $1 ORDER BY decision_date
"""

# #528/#512 family — "skip once, remember": a trade with no valid R frame is structurally
# invalid (entry/hard_stop/orb_low/shares are static once closed) and can never resolve on
# its own, so re-scanning it every night just re-logs the same skip forever (CRMD trade 137).
# ON CONFLICT DO NOTHING keeps this idempotent against the 120d catch-up window re-selecting
# the same trade before this write lands.
_SKIP_INSERT_SQL = """
    INSERT INTO mi_sell_discipline_skips (trade_id, ticker, reason)
    VALUES ($1, $2, $3)
    ON CONFLICT (trade_id) DO NOTHING
"""

_INSERT_SQL = """
    INSERT INTO mi_sell_discipline_records
        (trade_id, ticker, signal_type, account_mode, alert_date, fill_day, close_day,
         filled_at, closed_at, entry_price, risk_per_share, entry_shares,
         realized_pnl, realized_r, peak_price, peak_r, peak_time, peak_day, peak_hold_day,
         peak_source, peak_bars_n, peak_close, peak_close_r, peak_close_day,
         giveback_r, capture_pct, adr_20_pct, stop_pct, stop_per_adr, peak_adr, realized_adr,
         hold_trading_days, stop_above_entry_ever, partial_taken,
         judge_verdicts_n, judge_last_verdict, judge_last_verdict_date, judge_last_verdict_r,
         judge_first_warn_verdict, judge_first_warn_date, judge_first_warn_r, pnl_attribution)
    -- 42 placeholders (adr_20_pct added 2026-08-01). Adding a column above without
    -- extending THIS line gave "INSERT has more target columns than expressions"
    -- (2026-07-30). Note the test that counts BOUND ARGS passed while this line was
    -- still short — arg-count and placeholder-count are different failures and only
    -- the database catches the second. tests/test_sell_discipline*.py now compares
    -- the two counts statically, which is what caught the 42nd here.
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,$37,
            $38,$39,$40,$41,$42)
    ON CONFLICT (trade_id) DO NOTHING
"""

_INSERT_COLS = (
    "trade_id", "ticker", "signal_type", "account_mode", "alert_date", "fill_day", "close_day",
    "filled_at", "closed_at", "entry_price", "risk_per_share", "entry_shares",
    "realized_pnl", "realized_r", "peak_price", "peak_r", "peak_time", "peak_day", "peak_hold_day",
    "peak_source", "peak_bars_n", "peak_close", "peak_close_r", "peak_close_day",
    "giveback_r", "capture_pct", "adr_20_pct", "stop_pct", "stop_per_adr", "peak_adr", "realized_adr",
    "hold_trading_days", "stop_above_entry_ever", "partial_taken",
    "judge_verdicts_n", "judge_last_verdict", "judge_last_verdict_date", "judge_last_verdict_r",
    "judge_first_warn_verdict", "judge_first_warn_date", "judge_first_warn_r", "pnl_attribution",
)


async def record_sell_discipline(today: date) -> int:
    """Write one sell-discipline record per newly-closed trade (ALL signal types, BOTH
    account modes — every cohort query downstream filters account_mode, dual-account
    invariant 3). Catch-up window, idempotent (NOT EXISTS + ON CONFLICT DO NOTHING).
    Pure compute + DB/audit — no broker calls, no live-trade mutation. Returns rows written."""
    pool = await get_pool()
    logged = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SCAN_SQL, today, _CATCHUP_LOOKBACK_DAYS)
        for r in rows:
            try:
                trade = dict(r)
                fill_day = trade["filled_at"].astimezone(_ET).date()
                close_day = trade["closed_at"].astimezone(_ET).date()
                mb = await conn.fetchrow(
                    _MINUTE_PEAK_SQL, trade["ticker"], trade["filled_at"], trade["closed_at"])
                mb_n = await conn.fetchval(
                    _MINUTE_COUNT_SQL, trade["ticker"], trade["filled_at"], trade["closed_at"])
                daily = await conn.fetch(_DAILY_SQL, trade["ticker"], fill_day, close_day)
                decisions = await conn.fetch(_DECISIONS_SQL, trade["id"])
                rec = compute_sell_record(
                    trade,
                    minute_peak=(float(mb["high"]), mb["bar_time"]) if mb else None,
                    minute_bars_n=int(mb_n or 0),
                    daily_rows=[dict(d) for d in daily],
                    decisions=[dict(d) for d in decisions],
                )
                if rec is None:
                    reason = (
                        f"no valid R frame (entry={trade.get('entry_price')} "
                        f"hard_stop={trade.get('hard_stop')} orb_low={trade.get('orb_low')} "
                        f"shares={trade.get('entry_shares')})"
                    )
                    await log_audit_event(
                        "sell_discipline_record_skipped",
                        f"{trade['ticker']} trade {trade['id']}: {reason}")
                    # Remember it — this condition is permanent for a closed trade, so
                    # without this the 120d catch-up window re-flags it every night (#528/#512).
                    await conn.execute(_SKIP_INSERT_SQL, trade["id"], trade["ticker"], reason)
                    continue
                await conn.execute(_INSERT_SQL, *(rec[c] for c in _INSERT_COLS))
                logged += 1
            except Exception as e:
                logger.error(f"sell_discipline: trade {r['id']} ({r['ticker']}) failed: {e}")
                try:
                    await log_audit_event(
                        "sell_discipline_record_error",
                        f"{r['ticker']} trade {r['id']}: {type(e).__name__}: {e}")
                except Exception:  # loud-ok: log_audit_event self-catches; logger.error above already fired
                    pass
    if logged:
        try:
            await log_audit_event(
                "sell_discipline_recorded",
                summary=f"recorded {logged} sell-discipline record(s) for {today}")
        except Exception as _e:  # loud-ok: telemetry-of-telemetry; the records are already durable
            logger.warning("sell_discipline audit emit failed (non-fatal): %s", _e)
    return logged


# ── The unified surface (rides the management-judge Telegram, #508) ───────────────────────


def _r(v, digits: int = 1) -> str:
    return f"{v:+.{digits}f}R" if v is not None else "R?"


def _fmt_open_line(pos: dict, current_price: Optional[float]) -> Optional[str]:
    """One reach-vs-now line per OPEN position. None when the position has no R frame."""
    risk = trade_risk_per_share(pos)
    entry = _f(pos.get("entry_price"))
    if risk is None or entry is None:
        return None
    hps = _f(pos.get("highest_price_seen"))
    peak_r = (hps - entry) / risk if hps is not None else None
    now_r = (current_price - entry) / risk if current_price is not None else None
    stop = _f(pos.get("stop_price"))
    stop_r = (stop - entry) / risk if stop is not None else None
    flags = ""
    if stop is not None and stop > entry:
        flags += " BE+"
    if pos.get("partial_taken"):
        flags += " part"
    return (f" {pos.get('ticker', ''):<5} d{pos.get('hold_days', 0)}  "
            f"peak {_r(peak_r)} → now {_r(now_r)}  stop {_r(stop_r)}{flags}")


def _fmt_recorded_line(rec: dict) -> str:
    """One recorded round trip: when it closed, what it reached (and when), what it kept,
    plus the judge's last shadow verdict if one exists. `~` marks an extremes-sourced peak
    (5-min poll floor — blind under ~10 min, window from 09:30)."""
    approx = "~" if str(rec.get("peak_source") or "").startswith("extremes") else ""
    when = ""
    if rec.get("peak_hold_day"):
        when = f" d{rec['peak_hold_day']}"
        if rec.get("peak_time"):
            when += f" {rec['peak_time'].astimezone(_ET).strftime('%H:%M')}"
    judge = ""
    if rec.get("judge_last_verdict"):
        judge = (f"  {_VERDICT_ABBR.get(rec['judge_last_verdict'], rec['judge_last_verdict'])}"
                 f"@{_r(rec.get('judge_last_verdict_r'))}")
    close_day = rec.get("close_day")
    close_s = close_day.strftime("%m-%d") if close_day else "?"
    mode = "" if (rec.get("account_mode") or "live") == "live" else f" ({rec['account_mode']})"
    return (f" {close_s} {rec.get('ticker', ''):<5} {approx}{_r(rec.get('peak_r'))}{when}"
            f" → {_r(rec.get('realized_r'))}{judge}{mode}")


def format_sell_discipline_section(data: dict) -> str:
    """Pure renderer. Monospace code block, no pipe tables, one idea per line.
    `data` keys (all optional): open_lines [str], provisional [dict], recorded [dict],
    live_cohort {n,wins,reached_avg,kept_avg,partials,stop_above,regimes:[(name,n,kept)]},
    cohorts [dict], shadow {consol:[(mode,n,reached,kept)], htf, wick, giveback_n, pivot_cf}.
    Returns "" when there is nothing at all to show."""
    body: list[str] = []

    if data.get("open_lines"):
        body.append("OPEN")
        body.extend(data["open_lines"])

    if data.get("provisional"):
        body.append("CLOSED today (provisional — recorded tonight)")
        for p in data["provisional"]:
            body.append(f" {p.get('ticker', ''):<5} reached ~{_r(p.get('peak_r'))}"
                        f" → kept {_r(p.get('realized_r'))}")

    if data.get("recorded"):
        body.append("RECORDED round trips (7d) · reached → kept")
        body.extend(_fmt_recorded_line(rec) for rec in data["recorded"])

    lc = data.get("live_cohort")
    if lc and lc.get("n"):
        body.append(f"LIVE $ cohort n={lc['n']} · {lc.get('wins', 0)} wins")
        body.append(f" reached avg {_r(lc.get('reached_avg'))}"
                    f" → kept avg {_r(lc.get('kept_avg'))}")
        body.append(f" partials {lc.get('partials', 0)}"
                    f" · stop ever above entry {lc.get('stop_above', 0)}")
        if lc.get("regimes"):
            body.append(" regime@entry: " + " · ".join(
                f"{name} {n} ({_r(kept)})" for name, n, kept in lc["regimes"]))

    if data.get("cohorts"):
        body.append("OTHER RECORDED COHORTS · avg reached → kept")
        for c in data["cohorts"]:
            label = f"{c.get('signal_type') or '?'}/{c.get('account_mode') or '?'}"
            # Mark DEPRECATED strategies (operator 2026-07-30: "sell discipline still
            # tracks 9m day2 but it's deprecated"). KEPT rather than removed, on
            # purpose: 9m_day2 is the ONLY cohort with a positive kept (+0.2R) and it
            # is what proved the day-3 partial WORKS when it fires (avg hold 8.0d, 5 of
            # 7 reached day 3, 4 partials) versus live magna53 (1.5d, 0 partials).
            # Dropping it would delete the evidence behind the exit thesis. But shown
            # unlabelled it reads as a live comparison, which it is not — nothing here
            # can trade. Phase comes from mi_strategies so the tag stays true if a
            # phase changes.
            phase = (data.get("phases") or {}).get(c.get("signal_type"))
            tag = "  (deprecated — cannot trade)" if phase == "deprecated" else ""
            body.append(f" {label:<14} n={c['n']:<3} {_r(c.get('reached_avg'))}"
                        f" → {_r(c.get('kept_avg'))}{tag}")

    sh = data.get("shadow") or {}
    shadow_lines = []
    for mode, n, reached, kept in sh.get("consol", []):
        shadow_lines.append(f" consol-{mode:<11} n={n:<3} {_r(reached)} → {_r(kept)}")
    if sh.get("htf"):
        n, reached, kept = sh["htf"]
        shadow_lines.append(f" htf-breakout      n={n:<3} {_r(reached)} → {_r(kept)}")
    if sh.get("wick"):
        n, reached, kept = sh["wick"]
        reached_s = f"{reached:+.1f}%" if reached is not None else "?"
        kept_s = f"{kept:+.1f}%" if kept is not None else "?"
        shadow_lines.append(f" wick (pct frame)  n={n:<3} {reached_s} → {kept_s}")
    if shadow_lines:
        body.append("SHADOW SETUPS (no live $) · median reached → kept")
        body.extend(shadow_lines)
    cf = sh.get("pivot_cf") or {}
    if cf.get("n"):
        body.append("CANDIDATE RULE · would it have kept more? (live $, replay)")
        body.append(f" pivot-stop  n={cf['n']} ({cf.get('abstained', 0)} abstained)"
                    f"  reached {_r(cf.get('reached'))}")
        # The DIFF count is the load-bearing number, not the average: an average can move
        # simply because a profile is NULL on some trades. "changed 0" means the candidate
        # would have done nothing at all, which is the finding.
        body.append(f"  actual {_r(cf.get('actual'))}"
                    f" · p1 {_r(cf.get('p1'))} (changed {cf.get('p1_diff', 0)})"
                    f" · p2 {_r(cf.get('p2'))} (changed {cf.get('p2_diff', 0)})")
    if sh.get("giveback_n") is not None:
        body.append(f"giveback store: n={sh.get('giveback_n', 0)}")

    if not body:
        return ""
    if any("~" in ln for ln in body):
        body.append("~ = extremes-poll peak (5-min floor, blind <10min, from 09:30)")
    return ("📼 *Sell discipline — reached vs kept* (recorder only, no rule)\n"
            "```\n" + "\n".join(body) + "\n```")


async def build_sell_discipline_section(
    open_positions: list[dict], snaps: dict, today: date,
) -> str:
    """Assemble the unified surface data (records + regime reconstruction + shadow-cohort
    aggregates) and render it. Read-only. Raises to the caller on DB failure — the caller
    (run_position_mgmt_judge) fail-opens loudly so the judge digest always sends."""
    from agents.market_intelligence.mgmt_judge import snapshot_price

    pool = await get_pool()
    async with pool.acquire() as conn:
        recorded = await conn.fetch("""
            SELECT * FROM mi_sell_discipline_records
            WHERE close_day >= ($1::date - 7) AND pnl_attribution IS NULL
            ORDER BY close_day DESC, ticker LIMIT 8
        """, today)
        provisional = await conn.fetch("""
            SELECT t.id, t.ticker, t.entry_price, t.hard_stop, t.orb_low,
                   t.entry_shares, t.total_pnl, t.highest_price_seen
            FROM mi_live_trades t
            WHERE t.status = 'closed'
              AND (t.closed_at AT TIME ZONE 'America/New_York')::date = $1::date
              AND NOT EXISTS (SELECT 1 FROM mi_sell_discipline_records s WHERE s.trade_id = t.id)
            ORDER BY t.closed_at
        """, today)
        # dual-account invariant 3: every cohort read filters/groups account_mode.
        live_stats = await conn.fetchrow("""
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE realized_r > 0) AS wins,
                   avg(peak_r) AS reached_avg, avg(realized_r) AS kept_avg,
                   count(*) FILTER (WHERE partial_taken) AS partials,
                   count(*) FILTER (WHERE stop_above_entry_ever) AS stop_above
            FROM mi_sell_discipline_records
            WHERE account_mode = 'live' AND pnl_attribution IS NULL
        """)
        # ⚠ REGIME FRAME — read this before changing the join (#508 verify, 2026-08-08).
        # This used to RECONSTRUCT regime by joining mi_market_regime on alert_date. That
        # produced a DIFFERENT answer from `exit_tune_bull_regime_read`, the trigger that gates
        # every bull-tape conclusion: the trigger counts `mi_live_trades.regime` (stamped at
        # entry) and read Bull 3, while this surface read Bull 6. They disagreed on 5 of 17
        # trades — WULF, TSEM, FTNT, BTDR, BLZE — because a day's regime can be REVISED after
        # the entry was taken (08-04 was Choppy at 09:31 and resolved Bull).
        #
        # Both numbers are true; they answer different questions. For an EXIT-RULE read the
        # question is "what tape did we believe we were entering into", because that is the
        # information the decision actually had. A later revision cannot retro-justify or
        # retro-condemn a decision made without it. So: the STAMPED value wins, and this
        # surface now agrees with the trigger that gates the review it feeds.
        #
        # The operator reads BOTH surfaces. Two numbers for one question is the failure class
        # he has been calling out all week, and it nearly caught me twice in two days.
        regimes = await conn.fetch("""
            SELECT COALESCE(t.regime, '?') AS regime, count(*) AS n, sum(r.realized_r) AS kept
            FROM mi_sell_discipline_records r
            JOIN mi_live_trades t ON t.id = r.trade_id
            WHERE r.account_mode = 'live' AND r.pnl_attribution IS NULL
            GROUP BY 1 ORDER BY n DESC, regime
        """)
        cohorts = await conn.fetch("""
            SELECT signal_type, account_mode, count(*) AS n,
                   avg(peak_r) AS reached_avg, avg(realized_r) AS kept_avg
            FROM mi_sell_discipline_records
            WHERE pnl_attribution IS NULL AND account_mode <> 'live'
            GROUP BY 1, 2 ORDER BY 2, 1
        """)
        # Strategy phases so the render can mark DEPRECATED cohorts (#508, operator
        # 2026-07-30: "sell discipline still tracks 9m day2 but it's deprecated").
        # Read from mi_strategies rather than hardcoded, so the tag stays true if a
        # phase changes. Fail-soft: an empty map tags nothing, never tags wrongly.
        try:
            phases = {r["strategy_id"]: r["phase"] for r in await conn.fetch(
                "SELECT strategy_id, phase FROM mi_strategies")}
        except Exception as e:  # loud-ok: display-only; no tag beats a wrong tag
            logger.warning(f"strategy phases unavailable (non-fatal): {e}")
            phases = {}
        consol = await conn.fetch("""
            SELECT entry_mode, count(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd_mfe_r) AS reached,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY realized_r) AS kept
            FROM mi_consolidation_entry_shadow
            WHERE outcome IN ('capture', 'stop') GROUP BY 1 ORDER BY 1
        """)
        htf = await conn.fetchrow("""
            SELECT count(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd_mfe_r) AS reached,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY realized_r) AS kept
            FROM mi_htf_breakout_shadow WHERE outcome IN ('capture', 'stop')
        """)
        wick = await conn.fetchrow("""
            SELECT count(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY
                       GREATEST(fwd_1d_from_close_pct, fwd_3d_from_close_pct,
                                fwd_10d_from_close_pct)) AS reached,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY fwd_10d_from_close_pct) AS kept
            FROM mi_wick_candidates WHERE fwd_10d_from_close_pct IS NOT NULL
        """)
        giveback_n = await conn.fetchval("SELECT count(*) FROM mi_giveback_shadow")
        # DoD leg 3 (#508): "what a CANDIDATE RULE would have kept". This line used to render
        # two bare ROW COUNTS — which answers "does the store have rows", not the question the
        # task exists for. mi_pivot_stop_shadow already carries the answer per trade
        # (baseline_exit_r = what we actually kept, p1/p2_exit_r = what each candidate profile
        # would have kept), so the surface just was not asking.
        # ⚠ DISPLAY ONLY. Rendering what a rule WOULD have kept is evidence; changing a rule is
        # THE LINE (CHANGE_PROCESS + sign-off). This makes candidate rules replayable so they
        # stop being argued — including, as of today, showing when a candidate does NOTHING.
        pivot_cf = await conn.fetchrow("""
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE abstained) AS abstained,
                   avg(mfe_r) AS reached,
                   avg(baseline_exit_r) AS actual,
                   avg(p1_exit_r) AS p1,
                   avg(p2_exit_r) AS p2,
                   count(*) FILTER (WHERE p1_exit_r IS DISTINCT FROM baseline_exit_r) AS p1_diff,
                   count(*) FILTER (WHERE p2_exit_r IS NOT NULL
                                      AND p2_exit_r IS DISTINCT FROM baseline_exit_r) AS p2_diff
            FROM mi_pivot_stop_shadow WHERE account_mode = 'live'
        """)

    open_lines = []
    for pos in open_positions:
        line = _fmt_open_line(pos, snapshot_price(snaps.get(pos.get("ticker"))))
        if line:
            open_lines.append(line)

    prov = []
    for p in provisional:
        t = dict(p)
        risk = trade_risk_per_share(t)
        entry, shares = _f(t.get("entry_price")), _f(t.get("entry_shares")) or 0.0
        if risk is None or entry is None or shares <= 0:
            continue
        hps, pnl = _f(t.get("highest_price_seen")), _f(t.get("total_pnl"))
        prov.append({
            "ticker": t["ticker"],
            "peak_r": (hps - entry) / risk if hps is not None else None,
            "realized_r": pnl / (risk * shares) if pnl is not None else None,
        })

    data = {
        "open_lines": open_lines,
        "provisional": prov,
        "recorded": [dict(r) for r in recorded],
        "live_cohort": {
            "n": live_stats["n"], "wins": live_stats["wins"],
            "reached_avg": _f(live_stats["reached_avg"]), "kept_avg": _f(live_stats["kept_avg"]),
            "partials": live_stats["partials"], "stop_above": live_stats["stop_above"],
            "regimes": [(r["regime"], r["n"], _f(r["kept"])) for r in regimes],
        } if live_stats and live_stats["n"] else None,
        "phases": phases,
        "cohorts": [
            {"signal_type": c["signal_type"], "account_mode": c["account_mode"], "n": c["n"],
             "reached_avg": _f(c["reached_avg"]), "kept_avg": _f(c["kept_avg"])}
            for c in cohorts
        ],
        "shadow": {
            "consol": [(c["entry_mode"], c["n"], _f(c["reached"]), _f(c["kept"])) for c in consol],
            "htf": (htf["n"], _f(htf["reached"]), _f(htf["kept"])) if htf and htf["n"] else None,
            "wick": (wick["n"], _f(wick["reached"]), _f(wick["kept"])) if wick and wick["n"] else None,
            "giveback_n": giveback_n, "pivot_cf": dict(pivot_cf) if pivot_cf else None,
        },
    }
    return format_sell_discipline_section(data)
