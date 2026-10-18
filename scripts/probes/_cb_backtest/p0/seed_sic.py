#!/usr/bin/env python3
"""#702 P6 ops helper: seed `mi_consolidation_breakout_sic` from the backtest's point-in-time SIC pull.

The nightly shadow fills its SIC cache lazily, `SIC_CALLS_PER_NIGHT` (300) names a night, so group RS is thin for the
first week. The backtest already pulled SIC for the same liquid universe (`cb702_sic.psv`, written by `pull_sic.py`:
ticker|date|http_status|sic_code|sic_description|type). This turns that file into a SQL file; the MAIN LOOP runs it on
prod. THIS SCRIPT TOUCHES NO DATABASE and makes no network call - it reads the .psv and writes text.

  python scripts/probes/_cb_backtest/p0/seed_sic.py --out /path/to/cb702_sic_seed.sql [--data /Users/alvinfung/apollo_data/cb702]

Row shape = the shadow's own `fill_sic` rows, column for column (`db.CB_SIC_COLS` + `fetched_at`):
  - a 200 with a sic_code          -> status 'ok'   (sic_code, sic2 = `cb.sic2(sic_code)`, description, type)
  - a 200 without one              -> status 'none' (description / type kept, as the shadow stores them)
  - a 404                          -> status 'none', every other column NULL
  - any other HTTP status          -> NOT written (the shadow never caches a failure either: it is retried)
`fetched_at` is 2026-10-16 (the pull date) for every row, so a `none` row is re-tried by the shadow after its normal
`SIC_NONE_RETRY_DAYS` (30) - the seed does not make a `none` permanent.

`INSERT ... ON CONFLICT (ticker) DO NOTHING`: a ticker the shadow has already cached is never overwritten, and the
file is safe to run twice.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402

DEFAULT_DATA = Path("/Users/alvinfung/apollo_data/cb702")
TABLE = "mi_consolidation_breakout_sic"
COLS = ("ticker", "sic_code", "sic2", "sic_description", "ticker_type", "status", "fetched_at")   # the DDL's columns, in order
FETCHED_AT = "2026-10-16T00:00:00+00"
BATCH = 500                                                                                     # VALUES rows per INSERT


def _lit(v) -> str:
    """A SQL text literal: NULL, or '...' with every single quote doubled. Control characters are refused (a
    NUL or newline in a provider string would not belong in this table)."""
    if v is None:
        return "NULL"
    if any(ord(ch) < 32 for ch in v):
        raise ValueError(f"control character in {v!r}")
    return "'" + v.replace("'", "''") + "'"


def rows_from_psv(text: str) -> tuple:
    """([row dict], skipped) from the .psv text. `skipped` = rows whose HTTP status is neither 200 nor 404."""
    rows, skipped, seen = [], 0, set()
    for ln in text.splitlines():
        if not ln.strip():
            continue
        f = ln.split("|")
        if len(f) != 6:
            raise ValueError(f"expected 6 fields, got {len(f)}: {ln!r}")
        ticker, _date, code, sic, desc, typ = f
        if ticker in seen:
            raise ValueError(f"duplicate ticker {ticker}")
        seen.add(ticker)
        if code == "404":
            rows.append({"ticker": ticker, "sic_code": None, "sic2": None, "sic_description": None,
                         "ticker_type": None, "status": "none"})
        elif code == "200":
            sic = sic.strip() or None
            rows.append({"ticker": ticker, "sic_code": sic, "sic2": cb.sic2(sic) if sic else None,
                         "sic_description": desc or None, "ticker_type": typ or None,
                         "status": "ok" if sic else "none"})
        else:
            skipped += 1
    return rows, skipped


def render_sql(rows: list) -> str:
    out = [f"-- #702 SIC seed for {TABLE}: {len(rows)} rows from cb702_sic.psv. INSERT ... DO NOTHING, safe to re-run.",
           "BEGIN;"]
    for lo in range(0, len(rows), BATCH):
        vals = ",\n".join(
            "  (" + ", ".join([_lit(r["ticker"]), _lit(r["sic_code"]), _lit(r["sic2"]), _lit(r["sic_description"]),
                              _lit(r["ticker_type"]), _lit(r["status"]), f"'{FETCHED_AT}'::timestamptz"]) + ")"
            for r in rows[lo:lo + BATCH])
        out.append(f"INSERT INTO {TABLE} ({', '.join(COLS)}) VALUES\n{vals}\nON CONFLICT (ticker) DO NOTHING;")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default=str(DEFAULT_DATA), help="the backtest data dir holding cb702_sic.psv")
    ap.add_argument("--out", required=True, help="where to write the SQL file (not the repo's out/ dir)")
    args = ap.parse_args(argv)
    src = Path(args.data) / "cb702_sic.psv"
    rows, skipped = rows_from_psv(src.read_text())
    Path(args.out).write_text(render_sql(rows))
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"wrote {args.out}: {len(rows)} rows ({n_ok} ok, {len(rows) - n_ok} none), {skipped} skipped "
          f"(non-200/404 status), fetched_at {FETCHED_AT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
