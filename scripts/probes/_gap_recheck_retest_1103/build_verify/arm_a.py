# Sensitivity (a): anchor the 'ORB' on the first RTH bar whose high reached the floor price; submit the next minute;
# re-check absent (a) vs re-check at its own submit (a_s2, live read proxy = crossing-bar close). Outcome walk = verify.exit_walk.
import importlib.util, io, contextlib, re
spec = importlib.util.spec_from_file_location("v", "verify.py"); v = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(v)
from datetime import date
def nxt(hhmm):
    h, m = map(int, hhmm.split(":")); m += 1; h += m // 60; return f"{h:02d}:{m%60:02d}"
tot = {"a": [], "a_s2": []}
for r in v.pop:
    t, d = r["ticker"], r["d"]; dd = date.fromisoformat(d)
    bars = [dict(hhmm=b["hhmm"], o=float(b["open"]), h=float(b["high"]), l=float(b["low"]), c=float(b["close"])) for b in v.mins[(t, d)]]
    pc = float(re.search(r"prev close \$([\d.]+)", r["skip_reason"]).group(1)); floor = pc * 1.09
    if len(bars) < 2: print(t, "not evaluable"); continue
    cb = next((b for b in bars if b["h"] >= floor), None)
    if cb is None: print(f"{t:5} a: no crossing bar (max high {max(b['h'] for b in bars)} < floor {floor:.2f})"); continue
    sub = max("09:32", nxt(cb["hhmm"]))
    if sub >= "09:45" and cb["hhmm"] != "09:30": print(f"{t:5} a: crossing {cb['hhmm']} submit {sub} out of window"); continue
    H, L = cb["h"], cb["l"]
    live = cb["c"] if cb["hhmm"] != "09:30" else float(re.search(r"last \$([\d.]+)", r["skip_reason"]).group(1))
    for arm in ("a", "a_s2"):
        if arm == "a_s2" and (live - pc) / pc * 100 < 9.0:
            print(f"{t:5} {arm}: crossing {cb['hhmm']} -> re-check refuses (proxy {live} = {(live-pc)/pc*100:.2f}%)"); continue
        ent = v.entry_walk(bars, H, L, live, sub)
        if "fill" not in ent: print(f"{t:5} {arm}: crossing {cb['hhmm']} h={H} l={L} -> {ent['kind']}"); continue
        bars_anchor = bars  # stop = 2L - H on the crossing bar
        ex = v.exit_walk(t, dd, bars, ent, H, L)
        print(f"{t:5} {arm}: crossing {cb['hhmm']} h={H} l={L} submit {sub} -> {ent['kind']} {ent['fill']:.2f}@{ent['minute']} stop {2*L-H:.2f} risk {H-(2*L-H):.2f} | {ex['status']} R={ex['R']}  [{ex['detail']}]")
        if ex["status"] == "settled": tot[arm].append((t, round(ex["R"], 2)))
for k, x in tot.items(): print(k, "settled", x, "sum", round(sum(r for _, r in x), 2))
