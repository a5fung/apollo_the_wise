"""#714 stage 1b X2 — dated analyst rating-change events via yfinance Ticker.upgrades_downgrades (the source behind
collector.get_recent_upgrade_events), for Tier A (his 8 EPs + their scored rivals). $0, no prod. None/err = fetch failed (NOT 'no events')."""
import json, os, sys, time, datetime
import yfinance as yf
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s1b_fetch_float import sections
OUT = os.path.join(HERE, "out", "x2_upgrades.jsonl")
s = sections(os.path.join(HERE, "out", "50_fetch_lists.out"))
tick = sorted({r[0] for r in s["FETCH_A"][1:]})
done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["ticker"] for l in open(OUT)}
with open(OUT, "a") as f:
    for i, t in enumerate(tick):
        if t in done: continue
        rec = {"ticker": t, "events": None, "err": None}
        for k in range(3):
            try:
                ud = yf.Ticker(t).upgrades_downgrades
                rec["events"] = [] if (ud is None or ud.empty) else [
                    {"date": str(idx.date()), "action": str(row.get("Action", "")), "to": str(row.get("ToGrade", ""))} for idx, row in ud.iterrows()]
                rec["err"] = None
                break
            except Exception as e:
                rec["err"] = f"{type(e).__name__}: {str(e)[:100]}"; time.sleep(4 * (k + 1))
        rec["fetched_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        f.write(json.dumps(rec) + "\n"); f.flush()
        if i % 20 == 0: print(i, t, None if rec["events"] is None else len(rec["events"]), rec["err"], flush=True)
        time.sleep(1.0)
print("DONE")
