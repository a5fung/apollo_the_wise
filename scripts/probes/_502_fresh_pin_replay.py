#!/usr/bin/env python3
"""#502 pre-deploy gate — replay the SHIPPED _evaluate_fresh_pin over every
historical actionable (COILED/TRIGGERED) flag row.

The #416 lesson: a replay built from inline lookalike logic is not a gate. This
imports the real function from flag_detector and feeds it the same 40-bar window
the production batch query assembles.

  python scripts/probes/_502_fresh_pin_replay.py --pull   # ssh read-only -> TSV
  python scripts/probes/_502_fresh_pin_replay.py          # evaluate the TSV
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from agents.market_intelligence.flag_detector import (  # noqa: E402
    _DEAL_PIN_LOOKBACK_DAYS,
    _PIN_HISTORY_DAYS,
    _evaluate_deal_pin,
    _evaluate_fresh_pin,
)

HOST = "apollo@87.99.134.162"
TSV = pathlib.Path(__file__).with_name("_502_bars.tsv")

# Mirrors _check_deal_pin_signatures_batch's window, keyed per actionable row.
SQL = f"""
WITH act AS (
  SELECT DISTINCT ticker, scan_date, stage
  FROM mi_flag_candidates WHERE stage IN ('COILED','TRIGGERED')
)
SELECT a.ticker, a.scan_date, a.stage, x.rn,
       x.high_price, x.low_price, x.close, x.volume
FROM act a
JOIN LATERAL (
  SELECT high_price, low_price, close, volume,
         ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS rn
  FROM mi_daily_closes d
  WHERE d.ticker = a.ticker AND d.trade_date <= a.scan_date
    AND high_price IS NOT NULL AND low_price IS NOT NULL
    AND close IS NOT NULL AND close > 0
  ORDER BY trade_date DESC
  LIMIT {_PIN_HISTORY_DAYS}
) x ON TRUE
ORDER BY a.ticker, a.scan_date, x.rn;
"""


def pull() -> None:
    # Default '|' separator — an E'\t' arg does not survive the ssh shell round-trip.
    remote = "docker exec -i apollo-postgres psql -U apollo -d apollo -tAX"
    out = subprocess.run(["ssh", HOST, remote], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"psql failed: {out.stderr[:500]}")
    TSV.write_text(out.stdout)
    print(f"wrote {TSV} ({len(out.stdout.splitlines())} bar rows)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", action="store_true")
    args = ap.parse_args()
    if args.pull:
        pull()
        return

    windows: dict[tuple[str, str, str], list] = defaultdict(list)
    for line in TSV.read_text().splitlines():
        if not line.strip():
            continue
        tkr, sdate, stage, rn, hi, lo, cl, vol = line.split("|")
        windows[(tkr, sdate, stage)].append({
            "rn": int(rn),
            "high_price": float(hi), "low_price": float(lo), "close": float(cl),
            "volume": float(vol) if vol else None,
        })

    fresh_hits, mature_hits, both = [], [], []
    for key, rows in windows.items():
        rows.sort(key=lambda r: r["rn"])
        m = _evaluate_deal_pin(rows[:_DEAL_PIN_LOOKBACK_DAYS]) or {}
        f = _evaluate_fresh_pin(rows) or {}
        if m.get("is_pin") and f.get("is_fresh_pin"):
            both.append((key, f))
        elif m.get("is_pin"):
            mature_hits.append((key, m))
        elif f.get("is_fresh_pin"):
            fresh_hits.append((key, f))

    total = len(windows)
    print(f"\nactionable rows evaluated: {total}")
    print(f"  mature rule only : {len(mature_hits)}")
    print(f"  fresh  rule only : {len(fresh_hits)}   <-- NEW suppressions (#502)")
    print(f"  both rules       : {len(both)}")
    print(f"  preserved        : {total - len(mature_hits) - len(fresh_hits) - len(both)}")

    print("\n--- NEW suppressions (fresh rule, would not have fired before) ---")
    for (t, d, st), f in sorted(fresh_hits, key=lambda x: (x[0][0], x[0][1])):
        print(f"  {t:6s} {d} {st:9s} band {f['band_pct']:6.2%}  spike {f['vol_spike_x']:6.1f}x")

    if both:
        print("\n--- caught by BOTH (mature label wins) ---")
        for (t, d, st), f in sorted(both, key=lambda x: (x[0][0], x[0][1])):
            print(f"  {t:6s} {d} {st:9s} band {f['band_pct']:6.2%}  spike {f['vol_spike_x']:6.1f}x")

    print("\n--- MUST be preserved (the +25.7% counterexample) ---")
    for key, rows in sorted(windows.items()):
        if key[0] == "HUM":
            rows.sort(key=lambda r: r["rn"])
            f = _evaluate_fresh_pin(rows) or {}
            print(f"  HUM    {key[1]} band {f.get('band_pct', 0):6.2%}  "
                  f"spike {f.get('vol_spike_x', 0):6.1f}x  "
                  f"suppressed={f.get('is_fresh_pin')}")


if __name__ == "__main__":
    main()
