"""#489 delayed-feed residual tracker — the EP trades the ~15-min Polygon detection delay misses.

EOD job. For a run_date, replays that day's minute bars for QUALITY (common-stock/ADR + liquid)
gappers and records every name that crossed +10% vs prev close INSIDE the 9:31-9:44 ORB window in
REAL time, but which the ~16-min-delayed detection feed showed below 10% through the window (so the
live scan missed it). Each row carries whether the 5% hybrid (Pass-1 delayed superset + Pass-2 rt
confirm) WOULD have caught it. `hybrid_caught=false` is the structural residual — flat pre-market
then explode — that the hybrid can never catch. #490 §9.4 (operator-signed 2026-07-24): this table
is no longer an ESCALATION dashboard (the full-RT question is decided) — it is the RT-2 shadow
proof-join + the RT-4 post-cutover regression monitor, on the honest CROSS basis
(design doc `490_full_realtime_design_2026-07-25.md` §9.4).

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
            # #490 §9.4 — cross-basis columns stamped at insert (cross_px = the price at the
            # moment of the real-time cross; the honest baseline the day CLOSE is not).
            cross_px = r.prev_close * (1 + r.rt_gap / 100)
            cross_to_close = round((r.day_close / cross_px - 1) * 100, 2) if r.day_close else None
            cross_to_high = round(((r.prev_close * (1 + r.day_high_gap / 100)) / cross_px - 1) * 100, 2)
            await conn.execute("""
                INSERT INTO mi_ep_delayed_residual
                    (run_date, ticker, cross_tick_et, rt_gap, delayed_gap, day_high_gap,
                     hybrid_caught, prev_close, baseline_close, cross_to_close_pct, cross_to_high_pct)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (run_date, ticker) DO UPDATE SET
                    cross_tick_et=EXCLUDED.cross_tick_et, rt_gap=EXCLUDED.rt_gap,
                    delayed_gap=EXCLUDED.delayed_gap, day_high_gap=EXCLUDED.day_high_gap,
                    hybrid_caught=EXCLUDED.hybrid_caught, prev_close=EXCLUDED.prev_close,
                    baseline_close=EXCLUDED.baseline_close,
                    cross_to_close_pct=EXCLUDED.cross_to_close_pct,
                    cross_to_high_pct=EXCLUDED.cross_to_high_pct, computed_at=NOW()
            """, rd, r.ticker, r.cross_tick, r.rt_gap, r.delayed_gap, r.day_high_gap,
                 r.hybrid_caught, r.prev_close, r.day_close, cross_to_close, cross_to_high)

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


# ── O-9 DISPOSITION (#490 §9.4, operator-signed 2026-07-24) ──────────────────────────────────
# The O-9 escalation trigger (operator-pinned 7/20: ≥5 residual misses / median fwd-5d ≥ +8%)
# is RETIRED — its question ("escalate to full-RT?") was consumed by the operator's #490 ruling,
# and its metric ran on the known-wrong close basis (C3). What remains here:
#   - `backfill_residual_outcomes` keeps its column NAMES but the basis becomes honest: fwd_1d/
#     fwd_5d are computed vs cross_px (the price AT the real-time cross), not the day close.
#   - `residual_regression_stats` is the re-pointed RT-4 REGRESSION MONITOR: post-cutover the
#     residual count should read ~0; any sustained nonzero = the overlay is leaking.
#   - `rt_shadow_capture_join` is the RT-2 daily proof-join (every hybrid_caught=false row on a
#     shadow day must have a same-day `ep_rt_universe_catch`).
O9_WINDOW_DAYS = 21          # ≈ 15 trading days — the regression monitor's rolling window


async def backfill_residual_outcomes() -> int:
    """G3 (#490 RT-1): stamp fwd_1d_pct + fwd_5d_pct on SETTLED residual rows. #490 §9.4: the
    basis is CROSS_PX = prev_close × (1 + rt_gap/100) — the price at the moment of the real-time
    cross (the columns keep their names, the basis becomes honest; the old close-basis
    understated the winners the dashboard exists to find, C3). Also stamps the cross_to_*
    columns on any row the boot backfill missed. Read-only vs trade state (only UPDATEs the
    residual dashboard). Returns rows stamped."""
    pool = await db.get_pool()
    updated = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT run_date, ticker, prev_close, rt_gap, day_high_gap, baseline_close
            FROM mi_ep_delayed_residual
            WHERE fwd_5d_pct IS NULL AND baseline_close IS NOT NULL
              AND prev_close IS NOT NULL AND prev_close > 0 AND rt_gap IS NOT NULL
              AND run_date <= (CURRENT_DATE - INTERVAL '8 days')
        """)
        for r in rows:
            cross_px = float(r["prev_close"]) * (1 + float(r["rt_gap"]) / 100)
            if cross_px <= 0:
                continue
            fwd = await conn.fetch("""
                SELECT close FROM mi_daily_closes
                WHERE ticker=$1 AND trade_date > $2 AND close IS NOT NULL
                ORDER BY trade_date ASC LIMIT 5
            """, r["ticker"], r["run_date"])
            closes = [float(x["close"]) for x in fwd if x["close"]]
            if len(closes) < 5:
                continue   # not enough forward data settled yet
            base_close = float(r["baseline_close"])
            cross_to_close = round((base_close / cross_px - 1) * 100, 2)
            cross_to_high = (round(((float(r["prev_close"]) * (1 + float(r["day_high_gap"]) / 100))
                                    / cross_px - 1) * 100, 2)
                             if r["day_high_gap"] is not None else None)
            await conn.execute("""
                UPDATE mi_ep_delayed_residual SET fwd_1d_pct=$1, fwd_5d_pct=$2,
                    cross_to_close_pct=COALESCE(cross_to_close_pct, $3),
                    cross_to_high_pct=COALESCE(cross_to_high_pct, $4)
                WHERE run_date=$5 AND ticker=$6
            """, round((closes[0] / cross_px - 1) * 100, 2),
               round((closes[4] / cross_px - 1) * 100, 2),
               cross_to_close, cross_to_high, r["run_date"], r["ticker"])
            updated += 1
    if updated:
        await db.log_audit_event(
            "ep_residual_outcomes_backfilled",
            f"G3: stamped fwd outcomes (cross-basis, #490 §9.4) on {updated} settled residual row(s)",
            json.dumps({"updated": updated, "basis": "cross_px"}))
    logger.info(f"backfill_residual_outcomes: {updated} rows stamped (cross-basis)")
    return updated


async def residual_regression_stats() -> dict:
    """#490 §9.4 — the re-pointed RT-4 regression monitor (formerly `evaluate_o9_escalation`,
    RETIRED as a trigger: the operator's #490 ruling consumed its question; it must not keep
    reporting "not triggered" on a dead basis against a decided question). Over the rolling
    O9_WINDOW_DAYS window: count residual (hybrid_caught=false) misses with settled outcomes +
    their median fwd_5d_pct (now cross-basis). Post-cutover (RT-3) the count should trend ~0;
    any sustained nonzero = the overlay is leaking. Read-only. Returns {count, median_fwd5d}."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT fwd_5d_pct FROM mi_ep_delayed_residual
            WHERE hybrid_caught = false AND fwd_5d_pct IS NOT NULL
              AND run_date >= (CURRENT_DATE - INTERVAL '{O9_WINDOW_DAYS} days')
        """)
    vals = [float(r["fwd_5d_pct"]) for r in rows]
    median = statistics.median(vals) if vals else None
    return {"count": len(vals),
            "median_fwd5d": round(median, 2) if median is not None else None}


async def rt_shadow_capture_join(run_date: str) -> dict:
    """#490 RT-2 daily proof-join (piggybacks the 16:35 residual job): every
    `hybrid_caught=false` residual row on a shadow day must have a same-day in-window
    `ep_rt_universe_catch` audit event. Post-cutover (RT-3) the same join inverts into the
    standing verifier — a residual row with no catch = regression alarm. Read-only vs trade
    state. Returns {residual_total, caught_by_rt, missing: [tickers]}."""
    rd = datetime.strptime(run_date, "%Y-%m-%d").date()
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        residual_rows = await conn.fetch("""
            SELECT ticker FROM mi_ep_delayed_residual
            WHERE run_date = $1 AND hybrid_caught = false
        """, rd)
        catch_rows = await conn.fetch("""
            SELECT detail FROM mi_audit_log WHERE event_type = 'ep_rt_universe_catch'
              AND (created_at AT TIME ZONE 'America/New_York')::date = $1
        """, rd)
    caught: set = set()
    for r in catch_rows:
        try:
            j = json.loads(r["detail"]) if isinstance(r["detail"], str) else (r["detail"] or {})
            if j.get("ticker"):
                caught.add(j["ticker"])
        except (ValueError, TypeError):
            continue
    residual = [r["ticker"] for r in residual_rows]
    missing = [t for t in residual if t not in caught]
    return {"residual_total": len(residual),
            "caught_by_rt": len(residual) - len(missing),
            "missing": missing}
