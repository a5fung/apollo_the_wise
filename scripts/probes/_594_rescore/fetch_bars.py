#!/usr/bin/env python3
"""#594 re-score — STEP 1: pull the daily bars for every ruled (ticker, date), ONCE, to a file.

READ-ONLY · $0 · no paid model call. One SELECT on prod `mi_daily_closes` over SSH, saved to
`bars.tsv` next to this script. `run_score.py` reads that file and never touches the network, so
the score can be re-run any number of times without a second pull (COST EFFICIENCY: capture once,
read many).

WHY THIS FILE IS COMMITTED. The 09-21 re-score's driver lived in a session scratchpad and was
never committed; the 09-23 session had to rebuild it from a description. This is the committed
version, so the next sample's re-score is two commands:

    python scripts/probes/_594_rescore/fetch_bars.py          # one prod SELECT -> bars.tsv
    python scripts/probes/_594_rescore/run_score.py           # local, $0, repeatable

THE POPULATION IS DERIVED, NEVER HAND-LISTED. Tickers come from the fixtures:
  * `must_not_miss_eps.MUST_NOT_MISS`            every member, incl. the `excluded=True` ones
                                                 (they are scored separately and shown, not hidden)
  * `must_not_trade_charts.CHART_RULINGS`        every ruled (ticker, DATE)
  * `must_not_trade_charts.POINTED_AT_DATES`     the dates he pointed at without ruling on
so a new ruling in the fixture is picked up with no edit here.

WHY mi_daily_closes AND NOT A DATA API. Prod holds 2021-09 -> today for the whole universe (the
2026-09-06 five-year backfill), so every ruled date and its prior history is already stored. The
Alpaca/Polygon fallback is therefore NOT implemented here: it would be dead code, and `run_score.py`
reports any (ticker, date) the table does not cover as UNREADABLE in its own column rather than
quietly dropping it. If that column is ever non-zero, add the fallback then, against a real gap.

CAPTURE-ONCE GUARD: refuses to overwrite an existing `bars.tsv` unless `--force`.
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

OUT = HERE / "bars.tsv"
STAMP = HERE / "bars.pulled_at"
SSH_HOST = "apollo@87.99.134.162"
# $'\t' is expanded by the REMOTE bash — psql needs a real tab as its field separator.
REMOTE_CMD = "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F $'\\t'"
HISTORY_FROM = "2021-09-01"   # everything the table holds; the read itself decides how far back it looks
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def population_tickers() -> list[str]:
    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    from tests.fixtures.must_not_trade_charts import CHART_RULINGS, POINTED_AT_DATES

    tickers = {m.ticker for m in MUST_NOT_MISS}
    tickers |= {r.ticker for r in CHART_RULINGS}
    tickers |= {t for t, _d, _v in POINTED_AT_DATES}
    bad = sorted(t for t in tickers if not _TICKER_RE.match(t))
    if bad:  # the list is spliced into SQL — refuse anything that is not a plain symbol
        raise SystemExit(f"refusing to build SQL: unexpected ticker strings {bad}")
    return sorted(tickers)


def build_sql(tickers: list[str]) -> str:
    in_list = ", ".join(f"'{t}'" for t in tickers)
    return (
        "SELECT ticker, trade_date, open_price, high_price, low_price, close, volume\n"
        "FROM mi_daily_closes\n"
        f"WHERE ticker IN ({in_list}) AND trade_date >= '{HISTORY_FROM}'\n"
        "ORDER BY ticker, trade_date;\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite an existing bars.tsv")
    ap.add_argument("--dry-run", action="store_true", help="print the SQL and exit; no SSH")
    args = ap.parse_args()

    tickers = population_tickers()
    sql = build_sql(tickers)
    if args.dry_run:
        print(f"{len(tickers)} tickers\n{sql}")
        return 0
    if OUT.exists() and not args.force:
        print(f"{OUT} exists — capture-once guard. Read it; pass --force only to re-pull on purpose.")
        return 2

    proc = subprocess.run(["ssh", SSH_HOST, REMOTE_CMD], input=sql, text=True,
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return proc.returncode
    OUT.write_text(proc.stdout)
    STAMP.write_text(datetime.now(timezone.utc).isoformat() + "\n")
    n = max(0, proc.stdout.count("\n") - 2)  # header + "(N rows)" footer
    print(f"{len(tickers)} tickers -> {n} bar rows -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
