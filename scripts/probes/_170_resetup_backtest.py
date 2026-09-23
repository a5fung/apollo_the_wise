"""#170 C1 — EP cooldown re-setup admission backtest (Lane-1 pre-build, read-only).

Design: docs/analysis/170_cooldown_resetup_design_2026-07-11.md. Admission rule = days_since ≥ 10
AND gap ≥ 15%. Pull the cooldown-suppressed scan-log cohort (dedup per ticker-day, max gap),
compute days_since = scan_date − most-recent prior EP alert, join forward returns, then print the
full 3×3 JOINT grid (days ∈ {7,10,14} × gap ∈ {12,15,20}) — admitted-cohort forward stats + the
suppressed baseline — so the operator sees the plateau. Forward metric = 5d-max-high % from the
scan-day close; winner = ≥ +10%. Read-only; the sitting rules on the table.

Run:  docker cp then  docker exec -w /app apollo-market python /tmp/_170_resetup_backtest.py
"""
import asyncio
import statistics
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool

DAYS = [7, 10, 14]
GAPS = [12.0, 15.0, 20.0]
WIN_BAR = 10.0  # % forward-max


async def main() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH cohort AS (
                SELECT DISTINCT ON (l.ticker, l.scan_date) l.ticker, l.scan_date, l.gap_pct
                FROM mi_ep_scan_log l
                WHERE l.filter_reason ILIKE 'EP cooldown%' AND l.gap_pct IS NOT NULL
                ORDER BY l.ticker, l.scan_date, l.gap_pct DESC
            )
            SELECT c.ticker, c.scan_date, c.gap_pct::float AS gap,
                   (c.scan_date - (SELECT max(a.alert_date) FROM mi_ep_alerts a
                                   WHERE a.ticker=c.ticker AND a.alert_date < c.scan_date)) AS days_since,
                   dc.close::float AS entry_close,
                   (SELECT max(f.high_price) FROM mi_daily_closes f
                    WHERE f.ticker=c.ticker AND f.trade_date BETWEEN c.scan_date+1 AND c.scan_date+8
                      AND f.high_price IS NOT NULL)::float AS fwd_max_high
            FROM cohort c
            LEFT JOIN mi_daily_closes dc ON dc.ticker=c.ticker AND dc.trade_date=c.scan_date
        """)

    cohort = []
    for r in rows:
        if r["days_since"] is None or not r["entry_close"] or r["fwd_max_high"] is None:
            continue
        cohort.append({"ticker": r["ticker"], "date": r["scan_date"], "gap": r["gap"],
                       "days": r["days_since"],
                       "fwd": 100.0 * (r["fwd_max_high"] - r["entry_close"]) / r["entry_close"]})
    print(f"Cooldown-suppressed ticker-days with a forward path: {len(cohort)}\n")

    def stats(sub):
        if not sub:
            return "n=  0"
        fwds = [x["fwd"] for x in sub]
        win = 100 * sum(1 for f in fwds if f >= WIN_BAR) / len(fwds)
        return (f"n={len(sub):>3}  mean={statistics.mean(fwds):+5.1f}%  "
                f"med={statistics.median(fwds):+5.1f}%  win≥10%={win:>3.0f}%")

    print("=== BASELINE: all cooldown-suppressed (the do-nothing cohort) ===")
    print(f"  {stats(cohort)}\n")

    print("=== ADMITTED cohort by (days_since ≥ D) × (gap ≥ G) — the JOINT grid ===")
    print(f"  {'':>10}" + "".join(f"gap≥{g:>4.0f}%{'':>10}" for g in GAPS))
    for d in DAYS:
        cells = []
        for g in GAPS:
            adm = [x for x in cohort if x["days"] >= d and x["gap"] >= g]
            cells.append(stats(adm))
        print(f"  days≥{d:<3}  " + "   ".join(cells))
    print()

    headline = [x for x in cohort if x["days"] >= 10 and x["gap"] >= 15]
    print(f"=== HEADLINE cell (days≥10 & gap≥15%) — the proposed rule: {stats(headline)} ===")
    print("  would-admit (ticker date gap days fwd-max%):")
    for x in sorted(headline, key=lambda z: -z["fwd"]):
        print(f"    {x['ticker']:<6} {x['date']}  gap={x['gap']:>4.0f}%  d={x['days']:>3}  fwd={x['fwd']:+6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
