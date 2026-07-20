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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence import collector, db

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

LAG_MIN = 16          # measured Polygon Starter feed delay (design §14)
MIN_GAP = 10.0        # the real EP gap floor
SUPERSET = 5.0        # the chosen hybrid Pass-1 superset (operator 2026-07-20)
DOLLAR_VOL_MIN = 5_000_000
SCREEN_HIGH_PCT = 9.0
WIN_TICKS = [9 * 60 + 31, 9 * 60 + 35, 9 * 60 + 40]   # in-window scan ticks (9:31-9:44)
WIN_LAST = 9 * 60 + 44


def _scan_ticks():
    out, h, m = [], 7, 0
    while (h, m) <= (9, 55):
        out.append(h * 60 + m)
        m += 5
        if m >= 60:
            h += 1; m = 0
    out.append(9 * 60 + 31)
    return sorted(set(out))


TICKS = _scan_ticks()


async def _cs_universe() -> set:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker FROM mi_security_types WHERE security_type IN ('CS','ADRC')")
    return {r["ticker"] for r in rows if r["ticker"]}


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
    cs = await _cs_universe()
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
        if not (first_rt is not None and first_rt <= WIN_LAST and not caught_by_scan):
            continue   # not a delay-missed in-window crosser

        hyb = any(dl.get(w) is not None and dl[w] >= SUPERSET
                  and rt.get(w) is not None and rt[w] >= MIN_GAP for w in WIN_TICKS)
        tk = first_rt
        out.append((t, f"{tk // 60:02d}:{tk % 60:02d}", round(rt[tk], 2),
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
            """, rd, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])

    n_missed = len(out)
    n_residual = sum(1 for r in out if not r[5])
    await db.log_audit_event(
        "ep_delayed_residual_scan",
        f"{run_date}: {n_missed} quality in-window crossers missed by the delay; "
        f"{n_residual} beyond the 5% hybrid (residual — flat-premkt-then-explode)",
        json.dumps({"run_date": run_date, "missed_total": n_missed, "residual_beyond_hybrid": n_residual}),
    )
    logger.info(f"delayed_residual {run_date}: {n_missed} missed, {n_residual} residual beyond hybrid")
    return (n_missed, n_residual)
