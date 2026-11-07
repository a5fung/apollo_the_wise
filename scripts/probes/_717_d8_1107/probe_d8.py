"""#717 stage 2 D8 (design §A): READ-ONLY timing of get_minute_bars_range_batch over Fri 11-06's full session, run
inside apollo-execution. No order path, no DB write. Tickers arrive on stdin as two lines: 11-06 list, then 11-05 list."""
import asyncio, sys, time
from datetime import datetime
from zoneinfo import ZoneInfo
from agents.market_intelligence.broker import alpaca_client as ac

ET = ZoneInfo("America/New_York")
lines = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
l1106 = lines[0].split(","); l1105 = lines[1].split(",")
union = list(dict.fromkeys(l1106 + l1105))
start = datetime(2026, 11, 6, 9, 30, tzinfo=ET); end = datetime(2026, 11, 6, 15, 59, tzinfo=ET)


async def run(label, names):
    calls = []
    orig = ac._run_bars_page

    async def counted(fn, *a, timeout):
        calls.append(1)
        return await orig(fn, *a, timeout=timeout)

    ac._run_bars_page = counted
    t0 = time.monotonic()
    out = await ac.get_minute_bars_range_batch(names, start, end, last_completed=385)
    dt = time.monotonic() - t0
    ac._run_bars_page = orig
    got = {k: v for k, v in (out or {}).items()}
    nbars = sum(len(v) for v in got.values())
    missing = [t for t in names if t not in got]
    empty = [t for t in names if t in got and not got[t]]
    print(f"{label}: names={len(names)} requests={len(calls)} seconds={dt:.1f} bars={nbars} "
          f"absent={len(missing)} empty={len(empty)} absent_list={missing[:10]} empty_list={empty[:10]}")
    return got, empty


async def main():
    print("feed:", ac.get_data_feed())
    got, empty = await run("11-06 list (184 expected)", l1106)
    await run("11-05 U 11-06 lists", union)
    # parity: for up to 5 names the batch returned empty or short, compare the per-name call
    sample = empty[:5] or sorted(got, key=lambda t: len(got[t]))[:3]
    for t in sample:
        one = await ac.get_minute_bars_range(t, start, end)
        print(f"parity {t}: batch={len(got.get(t, []))} per_name={len(one or [])}")

asyncio.run(main())
