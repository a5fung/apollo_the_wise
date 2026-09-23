#!/usr/bin/env python3
"""#502 pre-deploy gate — replay the SHIPPED _evaluate_fresh_pin over every
historical actionable (COILED/TRIGGERED) flag row.

The #416 lesson: a replay built from inline lookalike logic is not a gate. This
imports the real function from flag_detector and feeds it the same 40-bar window
the production batch query assembles.

  python scripts/probes/_502_fresh_pin_replay.py --pull       # base window (frozen, do not re-pull)
  python scripts/probes/_502_fresh_pin_replay.py --pull-ext   # extension window -> TSV
  python scripts/probes/_502_fresh_pin_replay.py              # evaluate base + extension

Two corpora, NOT one, since the original evidence file's `act` CTE reads
CURRENT `mi_flag_candidates.stage` — which is not a historical log; a row is
final once written (UNIQUE(ticker, scan_date)) so it does not drift, but any
name production's own layers already suppressed by the time of a later pull
has legitimately dropped out of "currently COILED/TRIGGERED" even though it
still belongs in the regression corpus. So:

  TSV      (_502_bars.tsv)             — FROZEN 2026-07-24 evidence, 405 rows,
                                          89 tickers, 2026-05-04 -> 07-24. Do
                                          NOT re-pull; it is the original
                                          "same window" regression baseline
                                          (the 11 rows the sticky change must
                                          not touch, + HUM the must-preserve
                                          canary). Re-pulling it silently loses
                                          rows that production's OWN shipped
                                          filter has since (correctly)
                                          suppressed, e.g. ATAI 07-23/07-24.
  TSV_EXT  (_502_bars_ext_20260806.tsv) — 2026-07-25 -> 2026-08-06 extension,
                                          pulled 2026-08-06 for #502's sticky-
                                          carry fix (the ATAI leak on 07-30/
                                          07-31 happened AFTER the frozen
                                          window closed). --pull-ext bounds
                                          scan_date explicitly so it is
                                          reproducible independent of
                                          whatever else is COILED/TRIGGERED
                                          "right now" when it's next run.
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
    _FRESH_PIN_STICKY_SESSIONS,
    _PIN_HISTORY_DAYS,
    _evaluate_deal_pin,
    _evaluate_fresh_pin,
)

HOST = "apollo@87.99.134.162"
TSV = pathlib.Path(__file__).with_name("_502_bars.tsv")
TSV_EXT = pathlib.Path(__file__).with_name("_502_bars_ext_20260806.tsv")

# Mirrors _check_deal_pin_signatures_batch's window, keyed per actionable row.
def _sql(date_bound: str) -> str:
    return f"""
WITH act AS (
  SELECT DISTINCT ticker, scan_date, stage
  FROM mi_flag_candidates WHERE stage IN ('COILED','TRIGGERED') {date_bound}
    -- date_bound refers to the bare column here -- there is no "a." alias
    -- in scope inside this CTE (that alias is only bound in the outer
    -- FROM act a below). Caught 2026-08-06: an "a.scan_date" bound
    -- silently matched zero rows instead of erroring.
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


def _run_pull(sql: str, out_path: pathlib.Path) -> None:
    # Default '|' separator — an E'\t' arg does not survive the ssh shell round-trip.
    remote = "docker exec -i apollo-postgres psql -U apollo -d apollo -tAX"
    out = subprocess.run(["ssh", HOST, remote], input=sql, capture_output=True, text=True)
    # psql piped over ssh/docker exec can return 0 even when the SQL itself
    # errored (caught 2026-08-06: a stray "a." alias reference inside the CTE
    # produced an empty result set silently, not a failure). Always surface
    # stderr — a real pull has none.
    if out.returncode != 0 or out.stderr.strip():
        raise SystemExit(f"psql failed (rc={out.returncode}): {out.stderr[:500]}")
    if not out.stdout.strip():
        raise SystemExit("psql returned zero rows -- check the query, don't trust an empty pull silently")
    out_path.write_text(out.stdout)
    print(f"wrote {out_path} ({len(out.stdout.splitlines())} bar rows)")


def pull() -> None:
    _run_pull(_sql("AND scan_date <= '2026-07-24'"), TSV)


def pull_ext() -> None:
    _run_pull(
        _sql("AND scan_date > '2026-07-24' AND scan_date <= '2026-08-06'"),
        TSV_EXT,
    )


def _load(path: pathlib.Path, windows: dict, corpus: str, tag: dict) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        tkr, sdate, stage, rn, hi, lo, cl, vol = line.split("|")
        windows[(tkr, sdate, stage)].append({
            "rn": int(rn),
            "high_price": float(hi), "low_price": float(lo), "close": float(cl),
            "volume": float(vol) if vol else None,
        })
        tag[(tkr, sdate, stage)] = corpus


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", action="store_true",
                     help="re-pull the FROZEN base window (2026-05-04 -> 07-24) -- normally not needed")
    ap.add_argument("--pull-ext", action="store_true",
                     help="pull the extension window (2026-07-25 -> 08-06)")
    args = ap.parse_args()
    if args.pull:
        pull()
        return
    if args.pull_ext:
        pull_ext()
        return

    windows: dict[tuple[str, str, str], list] = defaultdict(list)
    corpus_of: dict[tuple[str, str, str], str] = {}
    _load(TSV, windows, "base(05-04..07-24)", corpus_of)
    _load(TSV_EXT, windows, "ext(07-25..08-06)", corpus_of)

    # own_* = fires on the row's OWN data, i.e. identical to pre-#502-refinement
    # behaviour. sticky_* = fires ONLY because of the 2026-08-06 carry-forward —
    # this is the net-new surface the refinement adds; it must be small and
    # every row in it hand-checked (task requirement).
    own_fresh, sticky_fresh, mature_hits, both = [], [], [], []
    for key, rows in windows.items():
        rows.sort(key=lambda r: r["rn"])
        m = _evaluate_deal_pin(rows[:_DEAL_PIN_LOOKBACK_DAYS]) or {}
        f = _evaluate_fresh_pin(rows) or {}
        if m.get("is_pin") and f.get("is_fresh_pin"):
            both.append((key, f))
        elif m.get("is_pin"):
            mature_hits.append((key, m))
        elif f.get("is_fresh_pin"):
            if f.get("sticky_from_session"):
                sticky_fresh.append((key, f))
            else:
                own_fresh.append((key, f))

    total = len(windows)
    fresh_hits = own_fresh + sticky_fresh
    print(f"\nactionable rows evaluated: {total}  "
          f"(base {sum(1 for c in corpus_of.values() if c.startswith('base'))}, "
          f"ext {sum(1 for c in corpus_of.values() if c.startswith('ext'))})")
    print(f"  mature rule only        : {len(mature_hits)}")
    print(f"  fresh rule, own data    : {len(own_fresh)}   <-- same as pre-2026-08-06 behaviour")
    print(f"  fresh rule, STICKY carry: {len(sticky_fresh)}   <-- NEW from this fix")
    print(f"  both rules              : {len(both)}")
    print(f"  preserved               : {total - len(mature_hits) - len(fresh_hits) - len(both)}")

    print("\n--- fresh rule, OWN data (unchanged vs. pre-fix; expect the original 11's non-mature share) ---")
    for (t, d, st), f in sorted(own_fresh, key=lambda x: (x[0][0], x[0][1])):
        print(f"  [{corpus_of[(t, d, st)]:20s}] {t:6s} {d} {st:9s} "
              f"band {f['band_pct']:6.2%}  spike {f['vol_spike_x']:6.1f}x")

    print("\n--- fresh rule, STICKY CARRY (net-new suppressions from this fix -- hand-check every one) ---")
    for (t, d, st), f in sorted(sticky_fresh, key=lambda x: (x[0][0], x[0][1])):
        print(f"  [{corpus_of[(t, d, st)]:20s}] {t:6s} {d} {st:9s} "
              f"band {f['band_pct']:6.2%}  carried from {f['sticky_from_session']} session(s) ago")

    if both:
        print("\n--- caught by BOTH (mature label wins) ---")
        for (t, d, st), f in sorted(both, key=lambda x: (x[0][0], x[0][1])):
            print(f"  [{corpus_of[(t, d, st)]:20s}] {t:6s} {d} {st:9s} band {f['band_pct']:6.2%}  spike {f['vol_spike_x']:6.1f}x")

    print("\n--- MUST be preserved (the +25.7% counterexample) ---")
    for key, rows in sorted(windows.items()):
        if key[0] == "HUM":
            rows.sort(key=lambda r: r["rn"])
            f = _evaluate_fresh_pin(rows) or {}
            print(f"  HUM    {key[1]} band {f.get('band_pct', 0):6.2%}  "
                  f"spike {f.get('vol_spike_x', 0):6.1f}x  "
                  f"suppressed={f.get('is_fresh_pin')}  sticky_from={f.get('sticky_from_session')}")

    print("\n--- ATAI leak sessions (the regression this fix targets) ---")
    for key, rows in sorted(windows.items()):
        if key[0] == "ATAI":
            rows.sort(key=lambda r: r["rn"])
            f = _evaluate_fresh_pin(rows) or {}
            print(f"  ATAI   {key[1]} ({key[2]:9s}) band {f.get('band_pct', 0):6.2%}  "
                  f"spike {f.get('vol_spike_x', 0):6.1f}x  "
                  f"suppressed={f.get('is_fresh_pin')}  sticky_from={f.get('sticky_from_session')}")

    print(f"\n(sticky window = {_FRESH_PIN_STICKY_SESSIONS} sessions)")


if __name__ == "__main__":
    main()
