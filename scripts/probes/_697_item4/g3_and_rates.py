import collections, sys
from datetime import date
sys.path.insert(0, "scripts/probes/_697_item4")
import replay_equiv as R

cap, stored = R.load_capture()
corpus = R.load_corpus()
out = {}
for src, bars, st in (("capture", cap, stored), ("corpus", corpus, {})):
    for t, b in bars.items():
        out[(src, t)] = (R.replay(t, b), st.get(t, {}))

# first stamped row of each stamp episode = the first row where (from) differs from the previous replayed row's
events = []
for (src, t), (res, st) in out.items():
    prev = None
    for d in sorted(res):
        m = res[d]
        f = m["post_breakout_from"]
        if f is not None and f != prev:
            events.append((src, t, d, f, m["days_since_breakout"], m["base_age"], m["stage"], st.get(d)))
        prev = f

# a "re-anchor event" = the row where the pivot moved (the event path): pivot_high_date of the row != previous row's pivot and stamp is set
reanchor = []
for (src, t), (res, st) in out.items():
    prev_piv = None
    for d in sorted(res):
        m = res[d]
        piv = m["pivot_high_date"]
        if m["post_breakout_from"] is not None and prev_piv is not None and piv is not None and piv > prev_piv and m["days_since_breakout"] is not None:
            # was it newly set at this row (event) rather than carried?
            pass
        if piv is not None:
            prev_piv = piv

caps = [e for e in events if e[0] == "capture"]
print("capture episodes (a row whose stamp differs from the previous replayed row's):", len(caps), "tickers:", len({e[1] for e in caps}))
dist = collections.Counter(min(e[4], 3) for e in caps)
print("days on the first stamped row: 1 ->", dist[1], "| 2 ->", dist[2], "| >=3 ->", dist[3])
g3 = {("CDNA", date(2026, 7, 31)): "corpus", ("CDNA", date(2026, 8, 25)): "corpus", ("CHPT", date(2026, 9, 18)): "capture",
      ("EFOR", date(2026, 10, 1)): "capture", ("HELP", date(2026, 8, 4)): "capture", ("PBF", date(2026, 9, 2)): "capture",
      ("REPL", date(2026, 9, 2)): "capture", ("TJGC", date(2026, 9, 11)): "capture", ("XHLD", date(2026, 9, 9)): "capture"}
for (t, d), src in g3.items():
    res, st = out[(src, t)]
    nxt = next(x for x in sorted(res) if x > d)
    m = res[nxt]
    s = st.get(nxt)
    print(f"G3 {t} {d} -> next row {nxt}: stamp from={m['post_breakout_from']} day={m['days_since_breakout']} reason={m['reason'][:24]} pivot={m['pivot_high_date']} | stored: {s[2] if s else '-'} {s[3] if s else ''}")
