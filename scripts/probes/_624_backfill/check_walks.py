"""#624 — sanity check on the final walk (read-only, no new outcome): hold lengths by block, and one >=3R path."""
import json
from collections import Counter
from datetime import date, time
import lib624 as L, walk624 as W
from agents.market_intelligence import live_fill_counterfactuals as lfc
sig = json.load(open(L.HERE / "signals_P.json"))
daily = L.load_daily()
keys = {(s["t"], date.fromisoformat(s["d"])) for s in sig}
mins = L.load_minutes([L.HERE / f for f in ("min_s1.tsv", "min_s2a.tsv", "min_s2b.tsv", "min_s2c.tsv")], keys=keys)
dc = {t: {"rows": {x: r for x, r in dl["rows"].items() if x <= L.DATA_END}, "dates": [x for x in dl["dates"] if x <= L.DATA_END]}
      for t, dl in daily.items() if t in {k[0] for k in keys}}
hold = Counter(); mx = {}; oc = Counter()
for s in sig:
    d = date.fromisoformat(s["d"]); hh, mm = map(int, s["T"].split(":")[:2]); T = time(hh, mm)
    b = L.as_dict_bars(d, mins.get((s["t"], d), []))
    w = W.walk_primary(s["t"], d, T, b, dc.get(s["t"]))
    oc[w["outcome"]] += 1
    if w["outcome"] in ("settled", "open", "horizon", "delisted_forced_close"):
        blk = s["block"]; ex = w.get("exit_session") or 0
        avail = len(W.trading_days_after(d, L.DATA_END))
        mx[blk] = max(mx.get(blk, 0), ex)
        hold[(blk, "exit day 0" if ex == 0 else ("1-5" if ex <= 5 else ("6-20" if ex <= 20 else "21-40")))] += 1
        if blk == "INSAMPLE_0608-0903" and ex >= avail - 1:
            print("   in-sample trade exiting at the data end:", s["t"], d, ex, "of", avail)
    if (s["t"], s["d"]) in (("AKAN", "2026-04-29"), ("OMIC", "2024-09-13")):
        res_bars = b
        print(f"   PATH {s['t']} {d} tick {T}: entry {w.get('entry_price')} at {w.get('entry_minute')}, stop {w.get('stop'):.4f}, ORB {w.get('orb_high')}/{w.get('orb_low')}, "
              f"partial {w.get('partial_fired')}, exit session {w.get('exit_session')} ({w.get('exit_day')}), final {w.get('final_reason')}, R {w['R']:+.2f}")
print("outcomes:", dict(oc))
print("max exit session by block:", mx)
print("hold buckets:", dict(sorted(hold.items())))
