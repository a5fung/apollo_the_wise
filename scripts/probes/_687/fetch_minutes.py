# #687 — minute-bar fetch inside the production container (the Polygon key lives here). ONE call per (ticker, day),
# paced >= 0.3 s, captured ONCE to /tmp/_687_minutes_<tag>.tsv (RTH 09:30-15:59 ET, split-adjusted like mi_daily_closes)
# with a per-call log /tmp/_687_fetch_log_<tag>.txt (ticker|date|bars_total|bars_rth|status). Resumable: keys already in
# the log are skipped. Usage: python /tmp/fetch_minutes.py <tag>   (reads /tmp/_687_fetch_list_<tag>.txt)
import asyncio, os, sys, time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from agents.market_intelligence.collector import get_minute_bars
ET = ZoneInfo("America/New_York")
tag = sys.argv[1]
lst = f"/tmp/_687_fetch_list_{tag}.txt"; out = f"/tmp/_687_minutes_{tag}.tsv"; logp = f"/tmp/_687_fetch_log_{tag}.txt"
done = set()
if os.path.exists(logp):
    for l in open(logp):
        p = l.rstrip("\n").split("|")
        if len(p) >= 2: done.add((p[0], p[1]))
keys = [tuple(l.strip().split("|")) for l in open(lst) if l.strip()]
async def main():
    fo = open(out, "a"); fl = open(logp, "a")
    for i, (t, d) in enumerate(keys):
        if (t, d) in done: continue
        t0 = time.monotonic()
        try:
            bars = await get_minute_bars(t, d, d)
            status = "ok"
        except Exception as e:
            bars = []; status = f"err:{str(e)[:60]}"
        n_rth = 0
        for b in bars:
            m = datetime.fromtimestamp(b["t"] / 1000, tz=ET)
            if m.date().isoformat() != d: continue
            if dtime(9, 30) <= m.time() < dtime(16, 0):
                fo.write(f"{t}|{m.strftime('%Y-%m-%d %H:%M')}|{b['o']}|{b['h']}|{b['l']}|{b['c']}|{b.get('v', '')}\n"); n_rth += 1
        fl.write(f"{t}|{d}|{len(bars)}|{n_rth}|{status}\n")
        if i % 50 == 0: fo.flush(); fl.flush()
        el = time.monotonic() - t0
        if el < 0.35: await asyncio.sleep(0.35 - el)
    fo.close(); fl.close(); open(f"/tmp/_687_done_{tag}", "w").write("done\n")
asyncio.run(main())
