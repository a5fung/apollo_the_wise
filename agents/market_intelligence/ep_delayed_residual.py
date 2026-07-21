"""#489 delayed-feed residual tracker — the EP trades the ~15-min Polygon detection delay misses.

EOD job. For a run_date, replays that day's minute bars for QUALITY (common-stock/ADR + liquid)
gappers and records every name that crossed +10% vs prev close INSIDE the 9:31-9:44 ORB window in
REAL time, but which the ~16-min-delayed detection feed showed below 10% through the window (so the
live scan missed it). Each row carries whether the 5% hybrid (Pass-1 delayed superset + Pass-2 rt
confirm) WOULD have caught it. `hybrid_caught=false` is the structural residual — flat pre-market
then explode — that the hybrid can never catch; its count + forward outcome is the escalation
dashboard for going full-real-time (design doc `realtime_detection_feed_design_2026-07-20.md` §14).

Read-only vs prod trade state (Polygon minute bars + grouped daily); writes mi_ep_delayed_residual.
"""
import json
import logging
import statistics
from datetime import datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

from agents.market_intelligence import collector, db


class _ResidualRow(NamedTuple):
    """One delay-missed in-window 10%-crosser (a mi_ep_delayed_residual row before insert).
    Field order matches the INSERT column order — keep them in sync."""
    ticker: str
    cross_tick: str          # "HH:MM" of the first real-time 10% cross
    rt_gap: float
    delayed_gap: "float | None"
    day_high_gap: float
    hybrid_caught: bool
    prev_close: float
    day_close: float

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

LAG_MIN = 16          # measured Polygon Starter feed delay (design §14)
MIN_GAP = 10.0        # the real EP gap floor
SUPERSET = 5.0        # the chosen hybrid Pass-1 superset (operator 2026-07-20)
DOLLAR_VOL_MIN = 5_000_000
SCREEN_HIGH_PCT = 9.0
WIN_TICKS = [9 * 60 + 31, 9 * 60 + 35, 9 * 60 + 40]   # in-window scan ticks (9:31-9:44)
WIN_LAST = 9 * 60 + 44


# In-window scan ticks as minutes-of-day: 7:00-9:55 every 5 min, plus the 9:31 ORB tick.
TICKS = sorted(set(range(7 * 60, 9 * 60 + 56, 5)) | {9 * 60 + 31})


async def _prev_trading_grouped(run_date: str):
    d = datetime.strptime(run_date, "%Y-%m-%d").date() - timedelta(days=1)
    for _ in range(6):
        gd = await collector.get_grouped_daily(d.isoformat())
        if gd:
            return gd
        d -= timedelta(days=1)
    return {}


async def run_delayed_residual_scan(run_date: str) -> tuple[int, int]:
    """run_date = 'YYYY-MM-DD' ET trading day. Returns (n_missed_total, n_residual_beyond_hybrid)."""
    gd = await collector.get_grouped_daily(run_date)
    if not gd:
        logger.info(f"delayed_residual: {run_date} not a trading day")
        return (0, 0)
    cs = await db.get_common_stock_tickers()
    gp = await _prev_trading_grouped(run_date)
    if not gp:
        logger.warning(f"delayed_residual: no prior trading day for {run_date}")
        return (0, 0)

    cands = []
    for t, row in gd.items():
        if t not in cs or "." in t or len(t) > 5:
            continue
        prev = gp.get(t)
        if not prev:
            continue
        pc, pv, hi = prev.get("c"), prev.get("v"), row.get("h")
        if not (pc and pc >= 5 and pv and pv >= 50000 and hi):
            continue
        if pc * pv < DOLLAR_VOL_MIN or (hi / pc - 1) * 100 < SCREEN_HIGH_PCT:
            continue
        cands.append((t, pc, row.get("c")))

    out = []
    for t, pc, day_close in cands:
        try:
            bars = await collector.get_minute_bars(t, run_date, run_date)
        except Exception as e:
            logger.warning(f"delayed_residual minute bars failed for {t}: {e}")
            continue
        series = []
        for b in bars or []:
            ts = b.get("t")
            if ts is None:
                continue
            bt = datetime.fromtimestamp(ts / 1000, _ET)
            if bt.date().isoformat() == run_date and b.get("c"):
                series.append((bt.hour * 60 + bt.minute, b["c"]))
        series.sort()
        if not series:
            continue

        def price_at(mod, _s=series):
            p = None
            for mm, cc in _s:
                if mm <= mod:
                    p = cc
                else:
                    break
            return p

        rt, dl = {}, {}
        first_rt = first_dl = None
        for tk in TICKS:
            rp, dp = price_at(tk), price_at(tk - LAG_MIN)
            rt[tk] = (rp / pc - 1) * 100 if rp else None
            dl[tk] = (dp / pc - 1) * 100 if dp else None
            if rt[tk] is not None and rt[tk] >= MIN_GAP and first_rt is None:
                first_rt = tk
            if dl[tk] is not None and dl[tk] >= MIN_GAP and first_dl is None:
                first_dl = tk
        caught_by_scan = first_dl is not None and first_dl <= WIN_LAST
        if first_rt is None or first_rt > WIN_LAST or caught_by_scan:
            continue   # not a delay-missed in-window crosser

        hyb = any(dl.get(w) is not None and dl[w] >= SUPERSET
                  and rt.get(w) is not None and rt[w] >= MIN_GAP for w in WIN_TICKS)
        tk = first_rt
        out.append(_ResidualRow(t, f"{tk // 60:02d}:{tk % 60:02d}", round(rt[tk], 2),
                                round(dl[tk], 2) if dl[tk] is not None else None,
                                round((max(c for _, c in series) / pc - 1) * 100, 2), hyb, pc, day_close))

    rd = datetime.strptime(run_date, "%Y-%m-%d").date()   # DATE column wants a date, not a str
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        for r in out:
            await conn.execute("""
                INSERT INTO mi_ep_delayed_residual
                    (run_date, ticker, cross_tick_et, rt_gap, delayed_gap, day_high_gap,
                     hybrid_caught, prev_close, baseline_close)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (run_date, ticker) DO UPDATE SET
                    cross_tick_et=EXCLUDED.cross_tick_et, rt_gap=EXCLUDED.rt_gap,
                    delayed_gap=EXCLUDED.delayed_gap, day_high_gap=EXCLUDED.day_high_gap,
                    hybrid_caught=EXCLUDED.hybrid_caught, prev_close=EXCLUDED.prev_close,
                    baseline_close=EXCLUDED.baseline_close, computed_at=NOW()
            """, rd, r.ticker, r.cross_tick, r.rt_gap, r.delayed_gap, r.day_high_gap,
                 r.hybrid_caught, r.prev_close, r.day_close)

    n_missed = len(out)
    n_residual = sum(1 for r in out if not r.hybrid_caught)
    await db.log_audit_event(
        "ep_delayed_residual_scan",
        f"{run_date}: {n_missed} quality in-window crossers missed by the delay; "
        f"{n_residual} beyond the 5% hybrid (residual — flat-premkt-then-explode)",
        json.dumps({"run_date": run_date, "missed_total": n_missed, "residual_beyond_hybrid": n_residual}),
    )
    # #489: LOUD nightly summary of the delay's cost (only on days with a miss — quiet days stay silent).
    if n_missed > 0:
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(
                f"🔴 Delayed-feed residual {run_date}: {n_missed} delay-missed EP crosser(s) today, "
                f"{n_residual} BEYOND the 5% hybrid (the class the fix can't catch). Outcomes settle ~5d. "
                f"(/audit ep_delayed_residual_scan)")
        except Exception:  # loud-ok: Telegram is best-effort; the mi_ep_delayed_residual rows are durable
            pass
    logger.info(f"delayed_residual {run_date}: {n_missed} missed, {n_residual} residual beyond hybrid")
    return (n_missed, n_residual)


# ── G3 + O-9 escalation trigger (#490 §1.3; operator-pinned 2026-07-20: 5 misses / median fwd-5d ≥ +8%) ──
O9_MIN_MISSES = 5             # ≥ this many settled residual misses over the window …
O9_MEDIAN_FWD5D_MIN = 8.0     # … AND their median fwd_5d_pct ≥ this (real winners we're missing, not faders)
O9_WINDOW_DAYS = 21          # ≈ 15 trading days


async def backfill_residual_outcomes() -> int:
    """G3 (#490 RT-1): stamp fwd_1d_pct + fwd_5d_pct on SETTLED residual rows so the O-9 trigger can
    read forward outcomes. For each mi_ep_delayed_residual row with fwd_5d_pct NULL whose run_date
    has ≥5 forward trading-day closes in mi_daily_closes, compute the return vs baseline_close.
    Read-only vs trade state (only UPDATEs the residual dashboard). Returns rows stamped."""
    pool = await db.get_pool()
    updated = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT run_date, ticker, baseline_close FROM mi_ep_delayed_residual
            WHERE fwd_5d_pct IS NULL AND baseline_close IS NOT NULL
              AND run_date <= (CURRENT_DATE - INTERVAL '8 days')
        """)
        for r in rows:
            base = float(r["baseline_close"]) if r["baseline_close"] else None
            if not base:
                continue
            fwd = await conn.fetch("""
                SELECT close FROM mi_daily_closes
                WHERE ticker=$1 AND trade_date > $2 AND close IS NOT NULL
                ORDER BY trade_date ASC LIMIT 5
            """, r["ticker"], r["run_date"])
            closes = [float(x["close"]) for x in fwd if x["close"]]
            if len(closes) < 5:
                continue   # not enough forward data settled yet
            await conn.execute("""
                UPDATE mi_ep_delayed_residual SET fwd_1d_pct=$1, fwd_5d_pct=$2
                WHERE run_date=$3 AND ticker=$4
            """, round((closes[0] / base - 1) * 100, 2), round((closes[4] / base - 1) * 100, 2),
               r["run_date"], r["ticker"])
            updated += 1
    if updated:
        await db.log_audit_event(
            "ep_residual_outcomes_backfilled",
            f"G3: stamped fwd outcomes on {updated} settled residual row(s)",
            json.dumps({"updated": updated}))
    logger.info(f"backfill_residual_outcomes: {updated} rows stamped")
    return updated


async def evaluate_o9_escalation() -> dict:
    """O-9 (#490 §1.3, operator-pinned 2026-07-20): should we trigger the full-real-time cutover?
    Over the last ≈15 trading days, count residual (hybrid_caught=false) misses WITH settled
    outcomes; TRIGGER when count ≥ O9_MIN_MISSES AND their median fwd_5d_pct ≥ O9_MEDIAN_FWD5D_MIN
    (the delay is costing WINNING EPs, not faders). Read-only. Returns {count, median_fwd5d, triggered}."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT fwd_5d_pct FROM mi_ep_delayed_residual
            WHERE hybrid_caught = false AND fwd_5d_pct IS NOT NULL
              AND run_date >= (CURRENT_DATE - INTERVAL '{O9_WINDOW_DAYS} days')
        """)
    vals = [float(r["fwd_5d_pct"]) for r in rows]
    median = statistics.median(vals) if vals else None
    triggered = len(vals) >= O9_MIN_MISSES and median is not None and median >= O9_MEDIAN_FWD5D_MIN
    return {"count": len(vals),
            "median_fwd5d": round(median, 2) if median is not None else None,
            "triggered": triggered}
