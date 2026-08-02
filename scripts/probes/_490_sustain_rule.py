"""#490 — how much does requiring the >=10% move to SUSTAIN change what we admit?

Operator 2026-08-02: *"target should be stable, in fact just a single 1min bar touching >10% may be
too lose especially for premarket, maybe we should see that move sustain with a few bars"* … *"maybe
look at not just consecutive, say 3 of last 5 bars is above, or 5 of last 10 bars, etc."*

DESIGN NOTE THAT MATTERS MORE THAN THE NUMBER: every rule here looks BACKWARD from the detection
tick. Waiting N bars forward would push detection past the 09:45 ORB cutoff and recreate the very
miss the real-time work exists to fix. Backward costs zero latency and the bars are already fetched
for Q3 corroboration.

Cohort = every `ep_rt_universe_catch` (what the flip would newly admit), scored against that day's
settled outcome. Read-only; touches no trade state.

Run: docker exec apollo-market python -m scripts.probes._490_sustain_rule
"""
import asyncio
import json
import statistics
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence import collector
from agents.market_intelligence.db import get_pool

_ET = ZoneInfo("America/New_York")
FLOOR = 10.0

# (label, M, N) — M of the last N bars (inclusive of the tick bar) must close >= FLOOR.
# M == N is the strictly-consecutive case.
RULES = [
    ("1 bar (today)",  1, 1),
    ("2 consecutive",  2, 2),
    ("3 consecutive",  3, 3),
    ("2 of last 3",    2, 3),
    ("3 of last 5",    3, 5),
    ("5 of last 10",   5, 10),
    ("7 of last 10",   7, 10),
]


def _rule_passes(gaps, m, n):
    """`gaps` = list of per-minute gap%, OLDEST->NEWEST, ending at the tick bar. Missing bars are
    already excluded by the caller; a window with fewer than n real bars is judged on what exists,
    which is the honest treatment pre-market where bars genuinely do not exist."""
    window = gaps[-n:]
    if not window:
        return None                      # undecidable — no bars at all
    return sum(1 for g in window if g >= FLOOR) >= min(m, len(window))


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        events = await c.fetch("""
            SELECT detail::json->>'ticker' AS ticker,
                   (created_at AT TIME ZONE 'America/New_York')::date AS d,
                   detail::json->>'tick_et' AS tick,
                   (detail::json->>'rt_gap')::numeric AS rt_gap
            FROM mi_audit_log
            WHERE event_type = 'ep_rt_universe_catch'
            ORDER BY created_at
        """)
    print(f"cohort: {len(events)} universe catches\n")

    rows = []
    no_bars = 0
    for e in events:
        tk, d, tick = e["ticker"], e["d"], e["tick"]
        if not tick:
            continue
        async with pool.acquire() as c:
            prev = await c.fetchrow(
                "SELECT close FROM mi_daily_closes WHERE ticker=$1 AND trade_date<$2 "
                "ORDER BY trade_date DESC LIMIT 1", tk, d)
            out = await c.fetchrow(
                "SELECT open_price, high_price, low_price, close FROM mi_daily_closes "
                "WHERE ticker=$1 AND trade_date=$2", tk, d)
        if not prev or not prev["close"]:
            continue
        pc = float(prev["close"])
        bars = await collector.get_minute_bars(tk, d.isoformat(), d.isoformat())
        if not bars:
            no_bars += 1
            continue
        series = []
        for b in bars:
            ts = b.get("t")
            if ts is None:
                continue
            hhmm = datetime.fromtimestamp(ts / 1000, tz=_ET).strftime("%H:%M")
            series.append((hhmm, (b["c"] - pc) / pc * 100))
        series.sort()
        upto = [g for hhmm, g in series if hhmm <= tick]
        if not upto:
            continue
        r = {"ticker": tk, "date": str(d), "tick": tick, "rt_gap": float(e["rt_gap"] or 0)}
        if out and out["open_price"]:
            o = float(out["open_price"])
            r["oc"] = (float(out["close"]) - o) / o * 100
            r["oh"] = (float(out["high_price"]) - o) / o * 100
            r["ol"] = (float(out["low_price"]) - o) / o * 100
        for label, m, n in RULES:
            r[label] = _rule_passes(upto, m, n)
        rows.append(r)

    print(f"scored {len(rows)} (skipped {no_bars} with no minute bars)\n")
    print(f"{'rule':<16} {'admits':>7} {'%':>6} {'med o->c':>9} {'med o->h':>9} {'med o->l':>9} {'win>+5%':>8}")
    print("-" * 72)
    for label, _m, _n in RULES:
        adm = [r for r in rows if r.get(label)]
        oc = [r["oc"] for r in adm if "oc" in r]
        oh = [r["oh"] for r in adm if "oh" in r]
        ol = [r["ol"] for r in adm if "ol" in r]
        win = sum(1 for v in oc if v >= 5)
        print(f"{label:<16} {len(adm):>7} {100*len(adm)/max(len(rows),1):>5.0f}% "
              f"{statistics.median(oc) if oc else 0:>8.1f}% {statistics.median(oh) if oh else 0:>8.1f}% "
              f"{statistics.median(ol) if ol else 0:>8.1f}% "
              f"{(str(win)+'/'+str(len(oc))) if oc else '-':>8}")

    print("\n--- what each rule DROPS vs today (the cost side) ---")
    base = [r for r in rows if r.get("1 bar (today)")]
    for label, _m, _n in RULES[1:]:
        dropped = [r for r in base if not r.get(label)]
        oc = [r["oc"] for r in dropped if "oc" in r]
        good = [r for r in dropped if r.get("oc", -99) >= 5]
        print(f"{label:<16} drops {len(dropped):>3}  median o->c of dropped {statistics.median(oc) if oc else 0:>6.1f}%"
              f"   dropped-but-good (>=+5%): {len(good)}"
              + (f"  {[g['ticker'] for g in good][:8]}" if good else ""))

    with open("/tmp/_490_sustain_rows.json", "w") as f:
        json.dump(rows, f, default=str)
    print("\nrows -> /tmp/_490_sustain_rows.json")

asyncio.run(main())
