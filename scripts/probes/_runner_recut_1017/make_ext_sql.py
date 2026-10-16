#!/usr/bin/env python3
"""Runner re-cut (2026-10-17) — build the ONE optional read-only prod pull: daily bars for the
Run-U replayable tickers, 2026-02-20 -> 2026-10-16, so the trades still open at the 08-29
capture's end (2026-08-28) can settle instead of being marked.

Pre-registration: docs/analysis/runner_recut_preregistration_2026-10-16.md (section "Saturday
commands", step 2). Reads ONLY the population's ticker symbols from the 08-29 admission capture
(no outcome field is read). Writes pull_daily_ext.sql next to this file. Nothing is sent anywhere.

The window starts at the capture's own first date (2026-02-20) on purpose: the overlap
2026-02-20 -> 2026-08-28 is diffed against the capture per ticker before any forward bar is
used (a split re-adjusted since 08-28 would otherwise splice two price bases into one walk).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ADM = "/Users/alvinfung/.claude/jobs/6b173ac9/tmp/bt_admission_result.json"
START, END = "2026-02-20", "2026-10-16"

rows = json.load(open(ADM))["U"]["replayable"]
tickers = sorted({r["t"] for r in rows})
arr = ",".join("'" + t.replace("'", "''") + "'" for t in tickers)
sql = f"""-- Runner re-cut 2026-10-17: read-only daily-bar pull for the {len(tickers)} Run-U replayable tickers
-- ({len(rows)} replayable rows), {START} -> {END}. Captured ONCE; remote name /tmp/cwp_runner_recut_daily.sql.
SET default_transaction_read_only = on;
SELECT ticker||'|'||trade_date||'|'||COALESCE(open_price::text,'')||'|'||COALESCE(high_price::text,'')||'|'||COALESCE(low_price::text,'')||'|'||close||'|'||volume
FROM mi_daily_closes
WHERE ticker = ANY(ARRAY[{arr}])
  AND trade_date BETWEEN DATE '{START}' AND DATE '{END}'
ORDER BY ticker, trade_date;
"""
out = os.path.join(HERE, "pull_daily_ext.sql")
with open(out, "w") as fh:
    fh.write(sql)
print(f"wrote {out}: {len(tickers)} tickers, {len(rows)} replayable rows, {START} -> {END}")
