"""#331 follow-up — is "fades beats punch" a STRUCTURE effect or a PRICE-LEVEL confound?

Forward PERCENT return is size-biased: a $1.50 name prints +300% on a move a $90 name cannot make.
The 2026-09-09 evidence run has fades_into_congestion beating punch_through on every cut, and its
top winners (VEEE +951%, SDOT +394%, JLHL +383%) are all low-priced names while punch_through's
best is DELL +59%. Before that inversion means anything about structure, it has to survive
stratification by prior close. READ-ONLY; reuses the probe's own classify() so the classes are
identical to the run being explained.
"""
import asyncio, statistics as st, sys
sys.path.insert(0, "/app")
from scripts.probes import _331_gap_alignment_evidence as E
from agents.market_intelligence.db import get_pool

BANDS = [(0, 2, "<$2"), (2, 5, "$2-5"), (5, 15, "$5-15"), (15, 50, "$15-50"), (50, 1e9, ">=$50")]

def band(p):
    for lo, hi, name in BANDS:
        if lo <= p < hi:
            return name
    return "?"

async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(E._COHORT_SQL)
        bars = await c.fetch(E._BARS_SQL, list({r["ticker"] for r in rows}))
    by = {}
    for b in bars:
        by.setdefault(b["ticker"], []).append(b)

    recs = []
    for r in rows:
        if r["fwd_5d_pct"] is None:
            continue
        bb = by.get(r["ticker"], [])
        det = E.classify(bb, r["alert_date"])
        if not det:
            continue
        # classify() returns a DICT carrying both the marker and the prior close — read them,
        # do not index it positionally (that silently compared a dict to a string and made every
        # class 0% on the first run).
        cls, pc = det.get("marker"), det.get("prior_close")
        if not cls or cls == "unknown" or not pc or pc <= 0:
            continue
        recs.append((band(float(pc)), cls, float(r["fwd_5d_pct"])))

    print(f"#331 PRICE-BAND CONTROL — {len(recs)} settled rows with a prior close\n")
    classes = ["punch_through", "clears_base_near_miss", "fades_into_congestion"]
    print("  === class MIX per price band (is fades where the cheap names live?) ===")
    for _, _, nm in BANDS:
        sub = [x for x in recs if x[0] == nm]
        if not sub:
            continue
        tot = len(sub)
        parts = "  ".join(f"{c.split('_')[0]}={sum(1 for x in sub if x[1]==c)*100//tot:>2}%" for c in classes)
        print(f"    {nm:<7} n={tot:<5} {parts}")

    print("\n  === fwd-5d avg / median / win% WITHIN each price band ===")
    for _, _, nm in BANDS:
        sub = [x for x in recs if x[0] == nm]
        if len(sub) < 30:
            continue
        print(f"    --- {nm} (n={len(sub)}) ---")
        for c in classes:
            v = [x[2] for x in sub if x[1] == c]
            if not v:
                continue
            flag = "  (N<30)" if len(v) < 30 else ""
            print(f"      {c:<24} n={len(v):<5} avg {st.mean(v):6.1f}%  med {st.median(v):6.1f}%"
                  f"  win {sum(1 for y in v if y>=5.0)*100//len(v):>3}%{flag}")

asyncio.run(main())
