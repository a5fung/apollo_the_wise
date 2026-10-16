#!/usr/bin/env python3
"""#333 annual leg — cross-check of the stored numbers, 2026-10-16. READ-ONLY, $0, no DB.

Runs the LIVE code path (snapshot_ticker, which never writes; upsert is a separate call) over
the saved 176 live-alert tickers (scripts/probes/_333cov_tickers.json, trailing-90-day
mi_ep_alerts population from 09-03 — a proxy for the nightly population; the prod read of last
night's list was refused). For each ticker it ALSO fetches Yahoo's raw earningsTrend module,
which carries Yahoo's own endDate per period, and compares:

  1. coverage: tickers with quarterly yfinance rows that also get an annual row WITH an
     estimate (the pre-registered >= 85% bar, previewed);
  2. label: our resolved period_end_date for 0y/+1y == Yahoo's own endDate;
  3. mapping: stored eps_avg / revenue_avg / analyst counts == Yahoo raw values for the same
     period (catches a 0y/+1y swap or an eps/revenue swap).

Output: xcheck_rows.jsonl (one record per ticker) + xcheck_summary.out.
"""
import asyncio, json, math, sys, time
from datetime import date
from pathlib import Path

import os
sys.path.insert(0, os.environ.get("XCHECK_ROOT") or str(Path(__file__).resolve().parents[3]))
SUFFIX = os.environ.get("XCHECK_SUFFIX", "")
import yfinance as yf  # noqa: E402
from agents.market_intelligence import analyst_estimates_recorder as r  # noqa: E402

HERE = Path(__file__).resolve().parent
AS_OF = date(2026, 10, 16)
PACE = 1.5


def raw_trend(ticker):
    t = yf.Ticker(ticker)
    _ = t.earnings_estimate
    out = {}
    for item in (t._analysis._earnings_trend or []):
        p = item.get("period")
        if p not in ("0y", "+1y"):
            continue
        ee, re_ = item.get("earningsEstimate") or {}, item.get("revenueEstimate") or {}
        g = lambda d, k: (d.get(k) or {}).get("raw") if isinstance(d.get(k), dict) else None
        out[p] = {"endDate": item.get("endDate"),
                  "eps_avg": g(ee, "avg"), "eps_n": g(ee, "numberOfAnalysts"),
                  "rev_avg": g(re_, "avg"), "rev_n": g(re_, "numberOfAnalysts")}
    return out


def close(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)


async def main():
    tickers = json.loads((HERE.parent / "_333cov_tickers.json").read_text())
    recs = []
    with open(HERE / f"xcheck_rows{SUFFIX}.jsonl", "w") as fh:
        for i, tk in enumerate(tickers):
            if i:
                await asyncio.sleep(PACE)
            rec = {"ticker": tk}
            try:
                snap = await r.snapshot_ticker(tk, AS_OF)
                rec["quarter_rows"] = snap["quarter_yf_rows"]
                rec["annual_rows"] = snap["annual_yf_rows"]
                rec["annual_informative"] = snap["annual_yf_informative"]
                rec["annual_no_label"] = snap["annual_yf_no_label"]
                ann = [x for x in snap["rows"] if x["period_type"] == "annual"]
                rec["ours"] = [{"period_end": str(x["period_end_date"]), "eps_avg": x["eps_avg"],
                                "rev_avg": x["revenue_avg"], "eps_n": x["num_analysts_eps"],
                                "rev_n": x["num_analysts_revenue"]} for x in ann]
            except Exception as e:
                rec["snap_error"] = f"{type(e).__name__}: {e}"[:200]
            try:
                rec["yahoo"] = await asyncio.get_event_loop().run_in_executor(None, raw_trend, tk)
            except Exception as e:
                rec["yahoo_error"] = f"{type(e).__name__}: {e}"[:200]
            fh.write(json.dumps(rec, default=str) + "\n"); fh.flush()
            recs.append(rec)
            if i % 25 == 0:
                print(f"{i}/{len(tickers)} {tk}", flush=True)

    # ── compare ──
    q = [x for x in recs if x.get("quarter_rows")]
    cov = [x for x in q if x.get("annual_informative")]
    label_ok = label_bad = map_ok = map_bad = 0
    bad_labels, bad_maps = [], []
    for x in recs:
        y = x.get("yahoo") or {}
        ours = x.get("ours") or []
        # pair each of our rows to the Yahoo period carrying the SAME endDate; a row whose date
        # matches no Yahoo period is a label miss. A swapped label then fails the VALUE check.
        by_end = {v["endDate"]: (p, v) for p, v in y.items()}
        for o in ours:
            if o["period_end"] not in by_end:
                label_bad += 1
                bad_labels.append((x["ticker"], o["period_end"], {p: v["endDate"] for p, v in y.items()}))
                continue
            label_ok += 1
            p, yp = by_end[o["period_end"]]
            ok = (close(o["eps_avg"], yp["eps_avg"]) and close(o["rev_avg"], yp["rev_avg"])
                  and close(o["eps_n"], yp["eps_n"]) and close(o["rev_n"], yp["rev_n"]))
            if ok:
                map_ok += 1
            else:
                map_bad += 1; bad_maps.append((x["ticker"], p, o, yp))
    lines = [
        f"code: {r.__file__}\npopulation: {len(recs)} tickers (saved 09-03 live-alert list), as_of {AS_OF}",
        f"snapshot errors: {sum(1 for x in recs if 'snap_error' in x)}; yahoo raw errors: {sum(1 for x in recs if 'yahoo_error' in x)}",
        f"COVERAGE: {len(cov)} of {len(q)} tickers with quarterly rows also have an annual estimate "
        f"({100*len(cov)/max(len(q),1):.1f}%; bar >= 85%)",
        f"  annual frames present but no label (skipped, counted): {sum(1 for x in recs if x.get('annual_no_label'))}",
        f"LABELS vs Yahoo endDate: {label_ok} match, {label_bad} differ",
        f"VALUES vs Yahoo raw (eps avg, revenue avg, both analyst counts): {map_ok} match, {map_bad} differ",
    ]
    for b in bad_labels[:40]:
        lines.append(f"  label differs: {b}")
    for b in bad_maps[:20]:
        lines.append(f"  value differs: {b}")
    (HERE / f"xcheck_summary{SUFFIX}.out").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
    print(f"elapsed {time.time()-t0:.0f}s")
