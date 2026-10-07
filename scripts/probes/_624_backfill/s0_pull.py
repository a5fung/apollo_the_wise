"""#624 backfill — STAGE 0: prod reads, READ-ONLY, each captured once to /tmp/_624bf/s0_*.

Run inside apollo-market. Uses the fresh Polygon split pull (/tmp/_624bf/splits.json, executed splits only —
execution_date <= 2026-10-06; mi_splits shows every executed split since 2026-03-02 applied) to un-adjust the
two raw floors (prior close >= $5, prior-day volume >= 50k) BEFORE choosing which tickers' daily series to pull.

Files:
  s0_cand.tsv          every (ticker, D) in the backfill window 2024-01-02..2026-09-03 and the live window
                       2026-09-09..2026-10-05 with daily high >= 1.15 x prior close, symbol ^[A-Z]{1,5}$, raw prior
                       close >= 5, raw prior-day volume >= 50k (o,h,l,c,v,pc,pv adjusted; F = raw factor for D-1)
  s0_daily.tsv         mi_daily_closes for every s0_cand ticker [first D - 130 days, 2026-10-06] and every F300-pool
                       ticker [2026-04-15, 2026-10-06]
  s0_sectypes.tsv      mi_security_types (today)
  s0_lane_signals.json mi_lowcap_lane_signals, all columns
  s0_lane_replays.json mi_lowcap_lane_replays, all columns — consumed ONLY by the A2 comparator and the "beside" column
  s0_f300_pool.tsv     mi_universe_floor_shadow 2026-09-09..2026-10-05 with today_volume_at_open > 0
  s0_s300_pool.tsv     mi_ep_scan_log ticker-days with market_cap, 2026-08-31..2026-10-05 (first row per ticker-day)
  s0_audit.tsv         mi_audit_log lowcap_lane_* rows, ET dates 2026-09-09..2026-10-05
"""
import asyncio
import json
import re
from collections import defaultdict
from datetime import date, timedelta

from agents.market_intelligence.db import get_pool

D = "/tmp/_624bf"
TODAY = date(2026, 10, 6)
SYM = re.compile(r"^[A-Z]{1,5}$")


def _j(v):
    if isinstance(v, (date,)):
        return v.isoformat()
    return str(v) if v is not None and not isinstance(v, (int, float, bool, str, list, dict)) else v


async def main():
    splits = json.load(open(f"{D}/splits.json"))
    by_t = defaultdict(list)
    for s in splits:
        ed = date.fromisoformat(s["execution_date"])
        if ed <= TODAY and s.get("split_from") and s.get("split_to"):
            by_t[s["ticker"]].append((ed, float(s["split_to"]) / float(s["split_from"])))

    def fac(t, d0):  # raw = adjusted x fac for values dated BEFORE d0 (splits executing on/after d0)
        f = 1.0
        for ed, r in by_t.get(t, ()):
            if ed >= d0:
                f *= r
        return f

    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute("SET statement_timeout = '1500s'")
        rows = await c.fetch("""
            WITH x AS (
              SELECT ticker, trade_date, open_price o, high_price h, low_price l, close c, volume v,
                     lag(close) OVER w pc, lag(volume) OVER w pv, lag(trade_date) OVER w pd
              FROM mi_daily_closes WHERE trade_date >= '2023-12-01'
              WINDOW w AS (PARTITION BY ticker ORDER BY trade_date))
            SELECT * FROM x
            WHERE ((trade_date BETWEEN '2024-01-02' AND '2026-09-03') OR (trade_date BETWEEN '2026-09-09' AND '2026-10-05'))
              AND pc > 0 AND h >= pc * 1.15 AND ticker ~ '^[A-Z]{1,5}$'""")
        n_raw = len(rows)
        cand = []
        for r in rows:
            f = fac(r["ticker"], r["trade_date"])
            if r["pc"] * f >= 5.0 and (r["pv"] or 0) / f >= 50000:
                cand.append((r, f))
        with open(f"{D}/s0_cand.tsv", "w") as fh:
            fh.write("ticker|d|o|h|l|c|v|pc|pv|pd|fac\n")
            for r, f in cand:
                fh.write("|".join(str(x) for x in (r["ticker"], r["trade_date"], r["o"], r["h"], r["l"], r["c"], r["v"],
                                                   r["pc"], r["pv"], r["pd"], f)) + "\n")
        first_d = {}
        for r, _ in cand:
            t = r["ticker"]
            first_d[t] = min(first_d.get(t, r["trade_date"]), r["trade_date"])
        print(f"cand rows high>=+15% symbol-ok: {n_raw}; after raw floors: {len(cand)}; tickers {len(first_d)}")

        # F300 pool (inputs only)
        f300 = await c.fetch("""
            SELECT scan_date, ticker, minutes_since_open_at_open msoo, today_volume_at_open vol, today_price_at_open px,
                   gap_pct_at_open gap, prev_close, prev_day_volume
            FROM mi_universe_floor_shadow
            WHERE scan_date BETWEEN '2026-09-09' AND '2026-10-05' AND today_volume_at_open > 0
            ORDER BY scan_date, ticker""")
        with open(f"{D}/s0_f300_pool.tsv", "w") as fh:
            fh.write("scan_date|ticker|msoo|vol|px|gap|prev_close|prev_day_volume\n")
            for r in f300:
                fh.write("|".join(str(r[k]) for k in ("scan_date", "ticker", "msoo", "vol", "px", "gap", "prev_close", "prev_day_volume")) + "\n")
        start = {t: d - timedelta(days=130) for t, d in first_d.items()}
        for r in f300:
            t = r["ticker"]
            s = date(2026, 4, 15)
            start[t] = min(start.get(t, s), s)
        print(f"f300 pool rows {len(f300)}; daily tickers {len(start)}")

        # daily series, streamed
        n_daily = 0
        tick = sorted(start)
        with open(f"{D}/s0_daily.tsv", "w") as fh:
            fh.write("ticker|d|o|h|l|c|v\n")
            for i in range(0, len(tick), 400):
                batch = tick[i:i + 400]
                lo = min(start[t] for t in batch)
                async with c.transaction(readonly=True):
                    async for r in c.cursor("""SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
                                               FROM mi_daily_closes WHERE ticker = ANY($1) AND trade_date >= $2
                                                 AND trade_date <= '2026-10-06' ORDER BY ticker, trade_date""",
                                            batch, lo, prefetch=20000):
                        if r["trade_date"] < start[r["ticker"]]:
                            continue
                        fh.write(f"{r['ticker']}|{r['trade_date']}|{r['open_price']}|{r['high_price']}|{r['low_price']}|{r['close']}|{r['volume']}\n")
                        n_daily += 1
        print(f"daily rows {n_daily}")

        st = await c.fetch("SELECT ticker, security_type, exchange FROM mi_security_types ORDER BY ticker")
        with open(f"{D}/s0_sectypes.tsv", "w") as fh:
            for r in st:
                fh.write(f"{r['ticker']}|{r['security_type']}|{r['exchange']}\n")
        print(f"sectypes {len(st)}")

        sig = await c.fetch("SELECT * FROM mi_lowcap_lane_signals ORDER BY scan_date, ticker")
        json.dump([{k: _j(v) for k, v in dict(r).items()} for r in sig], open(f"{D}/s0_lane_signals.json", "w"), default=str)
        rep = await c.fetch("SELECT * FROM mi_lowcap_lane_replays ORDER BY session_date, ticker")
        json.dump([{k: _j(v) for k, v in dict(r).items()} for r in rep], open(f"{D}/s0_lane_replays.json", "w"), default=str)
        print(f"lane signals {len(sig)}; lane replays rows {len(rep)} (written to file, not printed)")

        s300 = await c.fetch("""
            SELECT DISTINCT ON (ticker, scan_date) ticker, scan_date, market_cap, prev_close, current_price, gap_pct,
                   scan_time_et AT TIME ZONE 'America/New_York' AS t_et, minutes_since_open
            FROM mi_ep_scan_log
            WHERE scan_date BETWEEN '2026-08-31' AND '2026-10-05' AND market_cap IS NOT NULL AND market_cap > 0
            ORDER BY ticker, scan_date, scan_time_et""")
        with open(f"{D}/s0_s300_pool.tsv", "w") as fh:
            fh.write("ticker|scan_date|market_cap|prev_close|current_price|gap_pct|t_et|msoo\n")
            for r in s300:
                fh.write("|".join(str(r[k]) for k in ("ticker", "scan_date", "market_cap", "prev_close", "current_price", "gap_pct", "t_et", "minutes_since_open")) + "\n")
        print(f"s300 pool ticker-days {len(s300)}")

        au = await c.fetch("""
            SELECT id, created_at AT TIME ZONE 'America/New_York' AS t_et, event_type, summary, detail
            FROM mi_audit_log
            WHERE event_type LIKE 'lowcap_lane%'
              AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-09' AND '2026-10-05'
            ORDER BY created_at""")
        with open(f"{D}/s0_audit.tsv", "w") as fh:
            for r in au:
                fh.write("\t".join(str(r[k]).replace("\t", " ").replace("\n", " ") for k in ("id", "t_et", "event_type", "summary", "detail")) + "\n")
        print(f"audit rows {len(au)}")


asyncio.run(main())
