"""Next-day re-entry v2 — with a STOP-DISTANCE FLOOR, a wait sweep, and subset robustness.

Three things v1 could not answer:
  1. R was inflated by stops a fraction of a percent wide  -> MIN STOP = 0.5 x ADR20
     (if the natural stop is closer than that, it is WIDENED; R falls but becomes real)
  2. the 10-day wait window was my arbitrary choice        -> sweep 3 / 5 / 10 / 20
  3. the cohort is a superset we do not believe in         -> re-score on tighter subsets
     and check whether the RANKING of arms survives (operator 2026-08-16)

⚠ READ-ONLY, reconstructed, daily-bar resolution, 60-day horizon. THE LINE: measured only.
"""
from pathlib import Path
import _468_moderate_realized_r as M
from _delayed_reentry import triggers, run, HORIZON

H = Path(".").resolve()
M.COHORT, M.DAILY = H / "_468_cohort.tsv", H / "_468_daily_full.tsv"
MIN_STOP_ADR = 0.5


def adr20(db, i):
    w = db[max(0, i - 20):i]
    return (sum((b["h"] - b["l"]) / b["c"] for b in w if b["c"]) / len(w)) if w else None


rows = [r for r in M.load_cohort() if r["tier"] == "HIGH"]
daily = M.load_daily()
names = []
for r in rows:
    db = daily.get(r["ticker"], [])
    i = M.idx_of_date(db, r["alert_date"])
    if i is None or len(db) - i - 1 < HORIZON:
        continue
    ep, fwd = db[i], db[i + 1:]
    a = adr20(db, i)
    lo5 = min((b["c"] for b in db[max(0, i - 5):i]), default=None)
    ext = (lo5 and db[i - 1]["c"] and (db[i - 1]["c"] - lo5) / lo5 * 100 >= 50)
    risk0 = ep["c"] - ep["l"]
    peak = max((b["h"] for b in fwd[:HORIZON]), default=ep["c"])
    names.append(dict(nm=f"{r['ticker']} {r['alert_date']}", ep=ep, fwd=fwd, adr=a,
                      closes=[b["c"] for b in db[:i]], authority=r["authority"], ext=bool(ext),
                      opp=((peak - ep["c"]) / risk0 if risk0 > 0 else 0)))

SUBSETS = {"ALL (current definition)": lambda n: True,
           "judge held authority": lambda n: n["authority"] == "judge",
           "NOT parabolic (<50% in 5d)": lambda n: not n["ext"]}
ARMS = [("T1 reclaim EP low", "close"), ("T1 reclaim EP low", "touch"),
        ("T2 reclaim EP close", "close"), ("T2 reclaim EP close", "touch"),
        ("T4 close above prior high", "close"), ("T5 reclaim 10d MA", "close")]

print(f"{'subset':<28}{'wait':>5}{'arm':<30}{'fired':>6}{'catch':>7}{'/BIG':>6}{'catch%':>8}{'totR(floored)':>14}{'maxR':>7}")
rank_by_subset = {}
for sname, keep in SUBSETS.items():
    pool = [n for n in names if keep(n)]
    BIG = {n["nm"] for n in pool if n["opp"] >= 5}
    for wait in (3, 5, 10, 20):
        import _delayed_reentry as D
        D.MAXWAIT = wait
        scored = []
        for arm, sem in ARMS:
            rs, caught, fired = [], set(), 0
            for n in pool:
                tg = triggers(n["ep"], n["fwd"], n["closes"])
                if arm not in tg:
                    continue
                j, px, tlow = tg[arm]
                floor_stop = px - MIN_STOP_ADR * (n["adr"] or 0) * px
                stop = min(tlow, floor_stop)          # WIDEN a too-tight stop to the floor
                v = run(px, stop, n["fwd"][j + 1:], sem == "close")
                if v is None:
                    continue
                fired += 1
                rs.append(v)
                if v >= 5:
                    caught.add(n["nm"])
            if fired >= 8:
                scored.append((len(caught & BIG), sum(rs), arm, sem, fired, max(rs)))
        if not scored:
            continue
        scored.sort(reverse=True)
        rank_by_subset.setdefault(sname, {})[wait] = [f"{a}|{s}" for _, _, a, s, _, _ in scored]
        for c, tot, arm, sem, fired, mx in scored[:2]:
            print(f"{sname:<28}{wait:>5}{arm + '|' + sem:<30}{fired:>6}{c:>7}{len(BIG):>6}"
                  f"{100.0*c/max(len(BIG),1):>7.0f}%{tot:>14.1f}{mx:>7.1f}")

print("\nRANKING STABILITY (does the best arm survive a tighter cohort?):")
for s, byw in rank_by_subset.items():
    print(f"  {s:<28} best@wait10 = {byw.get(10, ['n/a'])[0]}")
