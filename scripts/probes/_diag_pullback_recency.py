"""One-shot: measure 'minutes-since-touch' staleness for today's MA-pullback
events. Picks K empirically before #124 rework writes code.

For each row in mi_flag_ma_pullbacks (today):
  1. Fetch 1-minute bars from 9:30 ET to pullback_time
  2. Find FIRST minute where bar.low ≤ day_low + 0.005 (small tolerance)
  3. minutes_since_touch = pullback_time - first_touch_minute
  4. Categorize as fresh (<K) or stale (>=K) for candidate K values

Run via: docker exec apollo-market python -m scripts._diag_pullback_recency
"""
import asyncio
from datetime import datetime, timezone


async def main() -> None:
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.collector import _polygon_get

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, pullback_time, day_low, ma_label, pct_below_ma,
                   bounce_pct_from_low, minutes_since_open
            FROM mi_flag_ma_pullbacks
            WHERE pullback_date = '2026-05-26'
            ORDER BY pullback_time
        """)

    print(f"Analyzing {len(rows)} pullback events from 2026-05-26")
    print(f"{'ticker':6} {'alert_t':8} {'day_low':>8} {'touch_t':8} {'mins_since':>10} {'pct_under':>9} {'bounce':>7}")
    print("-" * 75)

    results = []
    for r in rows:
        ticker = r["ticker"]
        pb_time = r["pullback_time"]  # tz-aware UTC
        day_low = r["day_low"]

        # Fetch 1-min bars from market open to pullback_time
        # 9:30 ET on 2026-05-26 = 13:30 UTC = epoch_ms
        market_open_ms = int(
            datetime(2026, 5, 26, 13, 30, tzinfo=timezone.utc).timestamp() * 1000
        )
        pb_ms = int(pb_time.timestamp() * 1000)

        try:
            data = await _polygon_get(
                f"/v2/aggs/ticker/{ticker}/range/1/minute/"
                f"{market_open_ms}/{pb_ms}",
                {"adjusted": "true", "sort": "asc", "limit": 500},
            )
        except Exception as e:
            print(f"{ticker:6} FETCH_FAIL: {e}")
            continue

        bars = data.get("results", []) or []
        if not bars:
            print(f"{ticker:6} NO_BARS")
            continue

        # First minute where bar.low <= day_low + tolerance
        # (day_low is the day's low from snapshot; minute bars should hit it)
        tolerance = 0.01
        first_touch_ms = None
        for b in bars:
            if b["l"] <= day_low + tolerance:
                first_touch_ms = b["t"]
                break

        if first_touch_ms is None:
            print(f"{ticker:6} NO_TOUCH_FOUND day_low={day_low}")
            continue

        first_touch_time = datetime.fromtimestamp(
            first_touch_ms / 1000, tz=timezone.utc
        )
        minutes_since = int((pb_time - first_touch_time).total_seconds() / 60)

        alert_t = pb_time.strftime("%H:%M")
        touch_t = first_touch_time.strftime("%H:%M")
        print(
            f"{ticker:6} {alert_t:8} {day_low:>8.2f} {touch_t:8} "
            f"{minutes_since:>10} {float(r['pct_below_ma']):>9.2f} "
            f"{float(r['bounce_pct_from_low']):>7.2f}"
        )
        results.append(minutes_since)

    if not results:
        print("\nNo results collected")
        return

    # Distribution
    results.sort()
    n = len(results)
    print(f"\n=== Distribution ({n} events with data) ===")
    print(f"  min:    {results[0]}")
    print(f"  p25:    {results[n // 4]}")
    print(f"  median: {results[n // 2]}")
    print(f"  p75:    {results[3 * n // 4]}")
    print(f"  max:    {results[-1]}")
    print()
    for k in (5, 10, 15, 20, 30, 45, 60, 120):
        fresh = sum(1 for x in results if x < k)
        stale = n - fresh
        print(f"  K={k:3} min -> {fresh:>3} fresh ({100*fresh/n:>5.1f}%), {stale:>3} stale")


if __name__ == "__main__":
    asyncio.run(main())
