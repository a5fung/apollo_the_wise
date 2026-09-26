"""#668 — one-shot READ-ONLY pull from prod for the alpha-capture cause split (a) vs (c).

Capture once, read many (CLAUDE.md cost rule). Every query is a SELECT; nothing is written to
prod. Outputs land in scripts/probes/_668_out/ as CSV; the bars file is gzipped and gitignored.

Run from the repo root:
    python scripts/probes/_668_pull.py            # the five small pulls
    python scripts/probes/_668_pull.py --bars     # the bar history for the post-swap alpha cohort
                                                  # (reads cohort.csv written by the first mode)
"""
from __future__ import annotations

import csv
import gzip
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "_668_out"
SSH = ["ssh", "apollo@87.99.134.162"]
PSQL = "docker exec -i apollo-postgres psql -U apollo -d apollo --csv -v ON_ERROR_STOP=1 -f -"

# The cohort query is the CORRECTED audit join (scripts/ep_delayed_capture_audit.py after
# 2026-09-16: live-preferring, paper fallback) with the cohort bounded to a MATURE 21-day
# forward window. Pulled 2026-05-18 → 2026-09-05 so the analysis can split at 2026-06-26
# itself; nothing here is reported unsplit.
HIGH_ALERTS_CTE = """
high_alerts AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
           a.ticker, a.alert_date, a.ep_score, a.gap_pct, a.catalyst_quality
    FROM mi_ep_alerts a
    WHERE a.alert_date BETWEEN DATE '2026-05-18' AND DATE '2026-09-05'
      AND a.score_tier = 'HIGH'
    ORDER BY a.ticker, a.alert_date, a.ep_score DESC NULLS LAST,
             a.detected_at DESC NULLS LAST, a.id DESC
)
"""

QUERIES = {
    "cohort": f"""
WITH {HIGH_ALERTS_CTE},
d AS (
    SELECT a.*,
           lt.status AS d1_status, lt.total_pnl AS d1_pnl, lt.skip_reason AS d1_skip_reason,
           lt.account_mode AS d1_mode, lt.closed_at AS d1_closed_at, lt.entry_price AS d1_entry,
           CASE
               WHEN lt.status = 'closed' AND COALESCE(lt.total_pnl, 0) > 0 THEN 'WON_DAY1'
               WHEN lt.status = 'closed' AND COALESCE(lt.total_pnl, 0) <= 0 THEN 'LOST_DAY1'
               WHEN lt.status = 'cancelled' THEN 'NO_ENTRY'
               WHEN lt.status = 'skipped' THEN 'SKIPPED'
               WHEN lt.id IS NULL THEN 'NO_TRADE_ROW'
               ELSE COALESCE(lt.status, 'UNKNOWN')
           END AS day1_class
    FROM high_alerts a
    LEFT JOIN LATERAL (
        SELECT t.* FROM mi_live_trades t
        WHERE t.ticker = a.ticker AND t.alert_date = a.alert_date
          AND t.pnl_attribution IS NULL
        ORDER BY (t.account_mode = 'live') DESC, t.id DESC
        LIMIT 1
    ) lt ON true
)
SELECT d.ticker, d.alert_date, d.ep_score, d.gap_pct, d.catalyst_quality, d.day1_class,
       d.d1_status, d.d1_pnl, d.d1_skip_reason, d.d1_mode, d.d1_closed_at, d.d1_entry,
       (SELECT MIN(alert_date) FROM mi_9m_ep_alerts
          WHERE ticker = d.ticker AND alert_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
           AS next_9m_ep_date,
       (SELECT MIN(alert_date) FROM mi_9m_day2_candidates
          WHERE ticker = d.ticker AND alert_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
           AS next_day2_date,
       (SELECT MIN(scan_date) FROM mi_flag_candidates
          WHERE ticker = d.ticker AND scan_date BETWEEN d.alert_date + 1 AND d.alert_date + 21
            AND stage IN ('COILED', 'TRIGGERED', 'WATCH'))
           AS next_flag_date,
       (SELECT MIN(scan_date) FROM mi_flag_candidates
          WHERE ticker = d.ticker AND scan_date BETWEEN d.alert_date + 1 AND d.alert_date + 21
            AND stage IN ('COILED', 'TRIGGERED', 'WATCH', 'TIGHTENING'))
           AS next_flag_date_incl_tightening,
       (SELECT COUNT(*) FROM mi_flag_candidates
          WHERE ticker = d.ticker AND scan_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
           AS flag_rows_in_window,
       (SELECT MIN(scan_date) FROM mi_flag_candidates
          WHERE ticker = d.ticker AND scan_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
           AS first_flag_scan_in_window,
       (SELECT MIN(alert_date) FROM mi_ep_alerts
          WHERE ticker = d.ticker AND alert_date BETWEEN d.alert_date + 1 AND d.alert_date + 21
            AND score_tier IN ('HIGH', 'MODERATE'))
           AS next_ep_date,
       (SELECT MAX(high_price) FROM mi_daily_closes
          WHERE ticker = d.ticker AND trade_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
           AS max_high_21d,
       (SELECT open_price FROM mi_daily_closes
          WHERE ticker = d.ticker AND trade_date = d.alert_date)
           AS d0_open,
       (SELECT COUNT(*) FROM mi_live_trades t
          WHERE t.ticker = d.ticker AND t.alert_date = d.alert_date
            AND t.status = 'closed' AND t.skip_reason = 'block:r3_reentry_disabled')
           AS r3_rows
FROM d
ORDER BY d.alert_date, d.ticker;
""",
    # Every R3 block-event ever written, both books — the carryforward's SOURCE population.
    "r3_rows": """
SELECT id, ticker, alert_date, status, account_mode, signal_type, skip_reason, total_pnl,
       entry_attempt, filled_at, closed_at, entry_price, stop_price
FROM mi_live_trades
WHERE skip_reason = 'block:r3_reentry_disabled'
ORDER BY alert_date, ticker;
""",
    # Every flag row the carryforward path actually admitted — its ACTUAL firings.
    "r3_flag_rows": """
SELECT ticker, scan_date, stage, reason, universe_sources
FROM mi_flag_candidates
WHERE 'magna53_failed_r3' = ANY(universe_sources)
ORDER BY scan_date, ticker;
""",
    # Scan-day census: which days the scan ran, how many promoted, how many R3-tagged.
    "scan_census": """
SELECT scan_date,
       COUNT(*) AS rows_total,
       COUNT(*) FILTER (WHERE stage IN ('WATCH', 'TIGHTENING', 'COILED', 'TRIGGERED')) AS promoted,
       COUNT(*) FILTER (WHERE 'magna53_failed_r3' = ANY(universe_sources)) AS r3_tagged,
       COUNT(*) FILTER (WHERE 'ninem_universe_watch' = ANY(universe_sources)) AS ninem_tagged
FROM mi_flag_candidates
WHERE scan_date >= DATE '2026-06-01'
GROUP BY 1 ORDER BY 1;
""",
    # What the flag board ALREADY DID with each cohort name inside its 21-day window —
    # every stored row, with the stored reject reason. Read before calling anything a miss.
    "cohort_flag_rows": f"""
WITH {HIGH_ALERTS_CTE}
SELECT h.ticker, h.alert_date, f.scan_date, f.stage, f.reason, f.universe_sources,
       f.base_age, f.runup_pct, f.flag_depth_pct, f.pivot_high_date, f.pivot_high_price,
       f.sma_10, f.sma_20, f.held_from_stage, f.score
FROM high_alerts h
JOIN mi_flag_candidates f
  ON f.ticker = h.ticker AND f.scan_date BETWEEN h.alert_date + 1 AND h.alert_date + 21
ORDER BY h.alert_date, h.ticker, f.scan_date;
""",
}

BARS_SQL = """
SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE ticker = ANY(ARRAY[{tickers}])
  AND trade_date BETWEEN DATE '2025-05-01' AND DATE '2026-09-25'
ORDER BY ticker, trade_date;
"""


def run_sql(sql: str) -> str:
    proc = subprocess.run(SSH + [PSQL], input=sql, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"psql failed rc={proc.returncode}")
    return proc.stdout


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--bars" in sys.argv:
        cohort = list(csv.DictReader((OUT / "cohort.csv").open()))
        # bars for every failed-Day-1 name from the post-swap era onward (the (a)/(c) replay
        # population is a subset; pulling the failed set once avoids a second round-trip)
        tickers = sorted({
            r["ticker"] for r in cohort
            if r["alert_date"] >= "2026-06-26" and r["day1_class"] != "WON_DAY1"
        })
        arr = ",".join(f"'{t}'" for t in tickers)
        text = run_sql(BARS_SQL.format(tickers=arr))
        with gzip.open(OUT / "bars.csv.gz", "wt") as fh:
            fh.write(text)
        print(f"bars: {len(tickers)} tickers, {text.count(chr(10)) - 1} rows -> bars.csv.gz")
        return
    for name, sql in QUERIES.items():
        text = run_sql(sql)
        (OUT / f"{name}.csv").write_text(text)
        print(f"{name}: {text.count(chr(10)) - 1} rows")


if __name__ == "__main__":
    main()
