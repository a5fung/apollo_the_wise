"""Inspect RDW's actual trade prints during bar 1 (9:30-9:31 ET).

The audit log shows bar-OHLC H=$19.68 which our entry stop_limit
triggered on. Alpaca shows the order as still 'new' (stop hasn't
triggered) ~30 min later. Hypothesis: $19.68 was a fringe-exchange
print that didn't appear on the consolidated trade tape used by
Alpaca's stop monitor.

Dumps every trade print between 9:30:00 and 9:31:00 ET (13:30:00
to 13:31:00 UTC). For each print: price, size, exchange code,
conditions, timestamp.

Run via: docker exec apollo-market python -m scripts._diag_rdw_prints
"""
import asyncio
from datetime import datetime


async def main() -> None:
    from agents.market_intelligence.collector import _polygon_get

    # 9:30:00 ET = 13:30:00 UTC (in May 2026 EDT = UTC-4)
    # Extend window to 9:34 ET so we see what bars 2/3 looked like
    start_ns = 1779802200_000_000_000   # 2026-05-26 13:30:00 UTC
    end_ns = 1779802500_000_000_000     # 2026-05-26 13:35:00 UTC (5 min)

    # v3 trades endpoint is premium tier. Fall back to 1-second aggregate
    # bars — if no 1s bar high reaches $19.68, the bar-1 H=$19.68 was a
    # sub-second outlier print (likely fringe exchange).
    data = await _polygon_get(
        "/v2/aggs/ticker/RDW/range/1/second/2026-05-26/2026-05-26",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    bars = data.get("results", [])
    # Filter to bar-1 window (13:30:00 - 13:31:00 UTC = 9:30-9:31 ET)
    window_bars = [b for b in bars if start_ns / 1e6 <= b["t"] < end_ns / 1e6]
    print(f"Pulled {len(bars)} 1-second bars, {len(window_bars)} in 9:30-9:31 ET window\n")
    if not window_bars:
        print("No 1s bars in window — check timestamp math")
        return

    max_high = max(b["h"] for b in window_bars)
    bars_at_or_above_1968 = [b for b in window_bars if b["h"] >= 19.68]
    print(f"Highest 1s bar in window: ${max_high}")
    print(f"1s bars with H >= $19.68: {len(bars_at_or_above_1968)}")
    print()
    # Just print 1-MINUTE-level summary across 9:30-9:35 + flag prints at/above $19.68
    from collections import defaultdict
    minute_bins: dict[int, dict] = defaultdict(lambda: {"h": 0, "l": 9999, "v": 0})
    for b in window_bars:
        minute_key = b["t"] // 60000
        agg = minute_bins[minute_key]
        agg["h"] = max(agg["h"], b["h"])
        agg["l"] = min(agg["l"], b["l"])
        agg["v"] += b["v"]
        if "o" not in agg:
            agg["o"] = b["o"]
        agg["c"] = b["c"]
    print(f"{'minute':10} {'O':>7} {'H':>7} {'L':>7} {'C':>7} {'V':>10}  ticks_at_19.68")
    print("-" * 70)
    for k in sorted(minute_bins):
        ts = datetime.fromtimestamp(k * 60).strftime("%H:%M")
        a = minute_bins[k]
        ticks_above = sum(1 for b in window_bars if b["t"] // 60000 == k and b["h"] >= 19.68)
        flag = f"  ({ticks_above} ticks at >=$19.68)" if ticks_above else ""
        print(f"{ts:10} {a['o']:>7.2f} {a['h']:>7.2f} {a['l']:>7.2f} {a['c']:>7.2f} {a['v']:>10.0f}{flag}")
    return  # exit; rest of original main is unused
    trades: list = []
    print(f"Pulled {len(trades)} trade prints from 9:30:00-9:31:10 ET")
    print(f"{'time':12} {'price':>8} {'size':>6} {'exch':>4} {'conditions':12}")
    print("-" * 50)

    # Bucket by exchange + flag prints AT $19.68
    exch_counts: dict[int, int] = {}
    high_water = 0.0
    high_water_exch: int | None = None
    high_water_size: int | None = None
    high_water_ts: int | None = None
    for t in trades:
        price = t.get("price", 0)
        size = t.get("size", 0)
        exch = t.get("exchange", 0)
        conditions = t.get("conditions", [])
        ts_ns = t.get("participant_timestamp") or t.get("sip_timestamp") or 0
        ts = datetime.fromtimestamp(ts_ns / 1e9).strftime("%H:%M:%S.%f")[:12]

        exch_counts[exch] = exch_counts.get(exch, 0) + 1

        if price > high_water:
            high_water = price
            high_water_exch = exch
            high_water_size = size
            high_water_ts = ts_ns

        # Spotlight: prints AT or ABOVE 19.68 (where stop should trigger)
        if price >= 19.68:
            cond_str = ",".join(str(c) for c in conditions)
            print(f"{ts:12} {price:>8.4f} {size:>6} {exch:>4} {cond_str:12}")

    print("\n=== Summary ===")
    print(f"  Highest print: ${high_water} on exchange {high_water_exch} size {high_water_size}")
    if high_water_ts:
        print(f"    at {datetime.fromtimestamp(high_water_ts / 1e9).strftime('%H:%M:%S.%f')[:12]} UTC")
    print(f"  Prints by exchange: {exch_counts}")
    print()
    print("Polygon exchange codes (common): "
          "8=ISE/MIAX, 11=NYSE/EDGX, 12=Nasdaq, 19=Nasdaq, 21=NYSE Arca, "
          "62=BX, 7=BATS, 4=IEX")


if __name__ == "__main__":
    asyncio.run(main())
