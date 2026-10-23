"""#697 phase 2 probe: HTFL + MRNA re-scored by the REAL compute_flag_metrics, with the SMA20 kill loosened by a tolerance
(a runtime copy of the function with one comparison changed; nothing in the repo is edited). Inputs threaded from prod's
STORED rows (yesterday stage, recent 5-calendar-day stages), as scripts/probes/_146_unpark/replay_stored_146.py does."""
import inspect, sys, textwrap, datetime as dt
from datetime import date, timedelta
sys.path.insert(0, ".")
from agents.market_intelligence import flag_detector as fd
S = sys.argv[1]
src = textwrap.dedent(inspect.getsource(fd.compute_flag_metrics))
assert src.count("close_today < sma_20:") == 1
ns = {}
def variant(tol):
    code = src.replace("def compute_flag_metrics(", f"def cfm_{int(tol*1000)}(").replace(
        "close_today < sma_20:", f"close_today < sma_20 * (1 - {tol}):")
    exec(compile(code, "variant", "exec"), fd.__dict__, ns)
    return ns[f"cfm_{int(tol*1000)}"]
V = {0.0: fd.compute_flag_metrics, 0.005: variant(0.005), 0.01: variant(0.01), 0.02: variant(0.02)}
def load(t):
    bars = []
    for ln in open(f"{S}/bars_{t}.psv"):
        d, o, h, l, c, v = ln.strip().split("|")
        bars.append({"trade_date": date.fromisoformat(d), "open_price": float(o), "high_price": float(h),
                     "low_price": float(l), "close": float(c), "volume": float(v or 0)})
    st = {}
    for ln in open(f"{S}/stored_{t}.psv"):
        d, s, held, pd_, ph = ln.strip().split("|")
        st[date.fromisoformat(d)] = (s, held or None, date.fromisoformat(pd_) if pd_ else None, float(ph) if ph else None)
    return bars, st
for t, days in (("HTFL", ("2026-09-29","2026-10-01","2026-10-07","2026-10-13","2026-10-14","2026-10-15","2026-10-16","2026-10-19","2026-10-20")),
                ("MRNA", ("2026-09-11","2026-09-15","2026-09-16","2026-09-17","2026-09-18"))):
    bars, st = load(t)
    idx = {b["trade_date"]: i for i, b in enumerate(bars)}
    print(f"== {t}  (stored stage | re-scored at tolerance 0 / 0.5% / 1% / 2%)")
    for ds in days:
        d = date.fromisoformat(ds); i = idx[d]; rows = bars[max(0, i - fd._HISTORY_DAYS + 1): i + 1]
        prev = [k for k in st if d - timedelta(days=5) <= k < d]
        y = max(prev) if prev else None
        recent = [st[k][0] for k in sorted(prev)]
        pv = [k for k in st if k < d and st[k][2] is not None and (d - k).days <= fd._PIVOT_CARRY_DAYS]
        pk = max(pv) if pv else None
        out = []
        for tol, f in V.items():
            r = f(rows, ticker=t, yesterday_stage=st[y][0] if y else None, recent_stages=recent,
                  yesterday_was_held=bool(st[y][1]) if y else False,
                  prior_pivot_date=st[pk][2] if pk else None, prior_pivot_high=st[pk][3] if pk else None)
            out.append(f"{r['stage']} ({(r.get('reason') or '')[:34]})")
        print(f"  {ds}  stored {st.get(d, ('-',))[0]:<11} | " + " / ".join(out))
