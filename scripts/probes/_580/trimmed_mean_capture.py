"""#580 slice: one-sided trim measurement -- STEP 1, CAPTURE (read-only, $0).

Pulls the raw rows ONCE from prod (SELECT only; the session is forced read-only)
into JSONL files next to this script. Every later step reads these files and never
re-queries (CLAUDE.md: capture once, read many).

    python scripts/probes/_580/trimmed_mean_capture.py

Population: the last 20 distinct mi_themes.theme_date values.
"""
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
SSH = ["ssh", "-o", "ConnectTimeout=20", "apollo@87.99.134.162",
       "docker exec -i apollo-postgres psql -q -At -v ON_ERROR_STOP=1 -U apollo -d apollo"]

DATES = "(SELECT DISTINCT theme_date FROM mi_themes ORDER BY theme_date DESC LIMIT 20)"
# 21st-newest date is captured for the THEMES table only, as the "previous night" of the oldest
# population date (the engine scores last night's roster; needed to rebuild the scoring-time member set).
DATES21 = "(SELECT DISTINCT theme_date FROM mi_themes ORDER BY theme_date DESC LIMIT 21)"

QUERIES = {
    # every mi_themes row on the 20 dates (Retired included so the exclusion is COUNTED, not assumed)
    "themes": f"""
        SELECT row_to_json(t) FROM (
          SELECT theme_date, name, stage, score, rs_avg, pct_above_20sma, tickers,
                 parent_theme, source, days_active
          FROM mi_themes WHERE theme_date IN {DATES21}
          ORDER BY theme_date, name) t;""",
    # stock scores: the top-1300 by rs_composite (enough to replay get_rs_leaders' LIMIT 1200 over-fetch)
    # PLUS every theme member, on each of the 20 dates.
    "scores": f"""
        WITH d AS {DATES},
        mem AS (SELECT DISTINCT m.theme_date AS score_date, unnest(m.tickers) AS ticker
                FROM mi_themes m WHERE m.theme_date IN (SELECT theme_date FROM d)),
        top AS (SELECT s.score_date, s.ticker FROM (
                  SELECT score_date, ticker,
                         row_number() OVER (PARTITION BY score_date
                                            ORDER BY rs_composite DESC NULLS LAST, ticker) rn
                  FROM mi_stock_scores WHERE score_date IN (SELECT theme_date FROM d)) s
                WHERE s.rn <= 1300)
        SELECT row_to_json(r) FROM (
          SELECT s.score_date, s.ticker, s.rs_composite, s.rs_1m, s.rs_3m, s.rs_6m,
                 s.adv_20, s.close, s.sector
          FROM mi_stock_scores s
          WHERE (s.score_date, s.ticker) IN (SELECT score_date, ticker FROM mem UNION SELECT score_date, ticker FROM top)
          ORDER BY s.score_date, s.ticker) r;""",
    # per-date row counts for the 40 newest score dates (the "complete run" test in _resolve_score_date)
    "score_counts": """
        SELECT row_to_json(r) FROM (
          SELECT score_date, count(*) n FROM mi_stock_scores
          GROUP BY score_date ORDER BY score_date DESC LIMIT 45) r;""",
    # non-EQUITY tracked tickers (excluded by get_rs_leaders)
    "non_equity": """
        SELECT row_to_json(r) FROM (
          SELECT ticker, quote_type FROM mi_tracked_stocks
          WHERE quote_type IS NOT NULL AND quote_type != 'EQUITY') r;""",
}


def run(name: str, sql: str) -> int:
    full = "SET default_transaction_read_only = on;\n" + sql
    p = subprocess.run(SSH, input=full, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        sys.exit(f"{name}: psql failed rc={p.returncode}\n{p.stderr[:2000]}")
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    for ln in lines:
        json.loads(ln)  # fail loudly on a malformed row
    (HERE / f"trimmed_mean_raw_{name}.jsonl").write_text("\n".join(lines) + "\n")
    return len(lines)


if __name__ == "__main__":
    for k, q in QUERIES.items():
        print(f"{k}: {run(k, q)} rows")
