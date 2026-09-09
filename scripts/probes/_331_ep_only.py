"""#331 — the SAME cut restricted to OUR EP ALERTS, which is the population the axis would act on.

The 2026-09-09 evidence run used all 3,120 mi_theme_axis_shadow rows. Only 347 of those are names
we actually alerted on; 89% are names the EP stack never surfaced. A meta-rubric axis grades EP
candidates, so the shadow cohort answers a question nobody asked. READ-ONLY.
"""
import asyncio, statistics as st, sys
sys.path.insert(0, "/app")
from scripts.probes import _331_gap_alignment_evidence as E
from agents.market_intelligence.db import get_pool

SQL = """
    SELECT s.ticker, s.alert_date, o.fwd_5d_pct, o.fwd_10d_pct,
           COALESCE(r.regime,'Unknown') AS regime,
           EXISTS (SELECT 1 FROM mi_ep_alerts a
                    WHERE a.ticker = s.ticker AND a.alert_date = s.alert_date) AS is_ep,
           (SELECT max(a.ep_score) FROM mi_ep_alerts a
             WHERE a.ticker = s.ticker AND a.alert_date = s.alert_date) AS ep_score
    FROM mi_theme_axis_shadow s
    LEFT JOIN mi_ep_scan_outcomes o ON o.ticker = s.ticker AND o.scan_date = s.alert_date
    LEFT JOIN mi_market_regime r ON r.regime_date = s.alert_date
"""
CLASSES = ["punch_through", "clears_base_near_miss", "fades_into_congestion"]

def table(rows, label, key="fwd_5d_pct"):
    print(f"  --- {label} (N={len(rows)}, {key}) ---")
    for c in CLASSES:
        v = [r[key] for r in rows if r["cls"] == c and r.get(key) is not None]
        if not v:
            print(f"    {c:<24} n=0")
            continue
        win = sum(1 for x in v if x >= 5.0)
        flag = "  (N<30)" if len(v) < 30 else ""
        print(f"    {c:<24} n={len(v):>4}  avg {st.mean(v):>6.1f}%  med {st.median(v):>6.1f}%"
              f"  win {win}/{len(v)} ({win*100//len(v)}%){flag}")
    print()

async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(SQL)
        bars = await c.fetch(E._BARS_SQL, list({r["ticker"] for r in rows}))
    by = {}
    for b in bars:
        by.setdefault(b["ticker"], []).append(b)
    recs = []
    for r in rows:
        det = E.classify(by.get(r["ticker"], []), r["alert_date"])
        cls = det.get("marker") if det else None
        if not cls or cls == "unknown":
            continue
        recs.append({"cls": cls, "is_ep": r["is_ep"], "ep_score": r["ep_score"],
                     "fwd_5d_pct": r["fwd_5d_pct"], "fwd_10d_pct": r["fwd_10d_pct"]})

    ep  = [r for r in recs if r["is_ep"] and r["fwd_5d_pct"] is not None]
    non = [r for r in recs if not r["is_ep"] and r["fwd_5d_pct"] is not None]
    print(f"#331 EP-ONLY CUT — classified {len(recs)}; EP-alerted {len(ep)}; never alerted {len(non)}\n")
    table(ep,  "OUR EP ALERTS ONLY  <<< the population the axis would act on")
    table(non, "names we never alerted on (the other 89%)")
    table(ep,  "OUR EP ALERTS ONLY, 10-day", key="fwd_10d_pct")
    hi = [r for r in ep if (r["ep_score"] or 0) >= 70]
    table(hi, "OUR EP ALERTS scoring >=70 (the ones that can actually trade)")

asyncio.run(main())
