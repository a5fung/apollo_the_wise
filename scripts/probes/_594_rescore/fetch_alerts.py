#!/usr/bin/env python3
"""#594 re-score — STEP 1b: what did the LIVE system already do on each ruled date? ONCE, to a file.

READ-ONLY · $0. One SELECT on prod `mi_ep_alerts` over SSH, saved to `alerts.tsv`.

WHY. "The read catches 9 of his 25 bad charts" means nothing until you know how many of the 25 the
live stack would ever have let through. The 2026-08-25 study found the live stack had already
rejected all eleven of session 1; later sessions were built partly from names we ALERTED. Counting
a rule's catches against names that were never admitted is the miss-counting mistake this repo
keeps making ([[check-what-the-system-already-did]]). The fixture records this only as free text in
`prior_runup_note`, so it is read from the table here instead of regex-parsed from prose.

Pairs are DERIVED from the fixtures (every ruled date, every pointed-at date, every real EP), never
hand-listed. CAPTURE-ONCE guard as in fetch_bars.py.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = HERE / "alerts.tsv"
STAMP = HERE / "alerts.pulled_at"
SSH_HOST = "apollo@87.99.134.162"
REMOTE_CMD = "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F $'\\t'"
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def population_pairs() -> list[tuple[str, str]]:
    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    from tests.fixtures.must_not_trade_charts import CHART_RULINGS, POINTED_AT_DATES

    pairs = {(m.ticker, m.alert_date) for m in MUST_NOT_MISS}
    pairs |= {(r.ticker, r.alert_date) for r in CHART_RULINGS}
    pairs |= {(t, d) for t, d, _v in POINTED_AT_DATES}
    for t, d in pairs:   # spliced into SQL — plain symbols and ISO dates only
        if not (_TICKER_RE.match(t) and _DATE_RE.match(d)):
            raise SystemExit(f"refusing to build SQL: unexpected value {(t, d)}")
    return sorted(pairs)


def build_sql(pairs: list[tuple[str, str]]) -> str:
    vals = ", ".join(f"('{t}', '{d}'::date)" for t, d in pairs)
    return (
        "SELECT a.ticker, a.alert_date, a.score_tier, MAX(a.ep_score) AS ep_score, COUNT(*) AS n_rows\n"
        "FROM mi_ep_alerts a\n"
        f"JOIN (VALUES {vals}) AS p(ticker, d) ON p.ticker = a.ticker AND p.d = a.alert_date\n"
        "GROUP BY a.ticker, a.alert_date, a.score_tier\n"
        "ORDER BY a.ticker, a.alert_date, a.score_tier;\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pairs = population_pairs()
    sql = build_sql(pairs)
    if args.dry_run:
        print(f"{len(pairs)} pairs\n{sql[:600]}")
        return 0
    if OUT.exists() and not args.force:
        print(f"{OUT} exists — capture-once guard.")
        return 2
    proc = subprocess.run(["ssh", SSH_HOST, REMOTE_CMD], input=sql, text=True,
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return proc.returncode
    OUT.write_text(proc.stdout)
    STAMP.write_text(datetime.now(timezone.utc).isoformat() + "\n")
    print(f"{len(pairs)} pairs queried -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
