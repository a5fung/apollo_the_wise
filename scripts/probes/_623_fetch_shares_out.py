"""#623 — fetch current shares-outstanding (Polygon reference /v3/reference/tickers/{ticker})
for every unique ticker in the #623 population, to build a point-in-time market-cap PROXY for
rows where mi_ep_scan_log has no persisted market_cap and filter_reason carries no parseable
mcap figure (scan_date < 2026-08-31, not an mcap-rejected row).

PROXY METHOD: proxy_market_cap_at_scan = shares_outstanding_NOW * prev_close_AT_SCAN (from the
population's own scan_log tick). Shares outstanding is near-static over the ~3-month window for
most names (assumption named, not hidden) EXCEPT across a reverse/forward split or a share
issuance/buyback — flagged separately by cross-checking against the 155 rows that already carry
a REAL point-in-time market cap (persisted column or filter_reason parse): if
|proxy/real - 1| > 20% for a ticker whose scan_date is close to now, that's a split/issuance
red flag, reported, not silently used.

Uses the SAME Polygon helper the live app uses (agents.market_intelligence.collector.
get_ticker_details -> _polygon_get), same courtesy delay -- run standalone (not through the app's
shared semaphore) but with an equivalent per-call delay so as not to hammer Polygon.

Run inside the market-agent container (has POLYGON_API_KEY):
  docker cp scripts/probes/_623_fetch_shares_out.py apollo-market:/tmp/_623_fetch_shares_out.py
  docker cp /tmp/_623_all_tickers.txt apollo-market:/tmp/_623_all_tickers.txt
  docker exec -w /app apollo-market python /tmp/_623_fetch_shares_out.py
Output: /tmp/_623_shares_out.jsonl (one JSON object per line, flushed as it goes -- safe to resume)
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/app")

# 2026-09-04 alert-sweep fix: this probe calls the SAME collector helper the live scan
# path uses (see the module docstring above), inside the SAME container, with the SAME
# real API key — nothing at the HTTP layer can tell this script's failures from a live
# scan's. Setting this before importing collector marks every _polygon_get/_fmp_get
# failure this process raises as probe-origin (llm_health._is_probe_origin): the
# api_failure_polygon audit row still gets written, but it never pages and never counts
# toward a live sustained-failure escalation. See llm_health.py's PROBE-ORIGIN section.
os.environ.setdefault("APOLLO_CALL_ORIGIN", "probe")

from agents.market_intelligence.collector import get_ticker_details  # noqa: E402

TICKERS_PATH = "/tmp/_623_all_tickers.txt"
OUT_PATH = "/tmp/_623_shares_out.jsonl"
DELAY_S = 0.15


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


async def main():
    with open(TICKERS_PATH) as f:
        # #623 alert-sweep fix (2026-09-04): TICKERS_PATH was built from a psql capture and
        # this loop had no footer guard -- the literal "(3458 rows)" summary line rode along
        # as if it were a ticker (sorts first, "(" < "A"), got GET-ed against Polygon's
        # /v3/reference/tickers/{ticker} and tripped the live api_failure_polygon alarm on a
        # 3458-row population that was never a real ticker. Same house pattern as
        # _623_join.py/_623_replay.py's `not r["ticker"].startswith("(")` psql-footer guard.
        tickers = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("(")]

    done = set()
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            for ln in f:
                try:
                    done.add(json.loads(ln)["ticker"])
                except Exception:
                    pass
    _log(f"{len(tickers)} tickers total, {len(done)} already done, {len(tickers)-len(done)} remaining")

    with open(OUT_PATH, "a") as out:
        for i, t in enumerate(tickers):
            if t in done:
                continue
            try:
                details = await get_ticker_details(t)
            except Exception as e:
                details = {}
                _log(f"{t}: EXC {e}")
            rec = {
                "ticker": t,
                "shares_outstanding": details.get("share_class_shares_outstanding")
                    or details.get("weighted_shares_outstanding"),
                "market_cap_polygon_field": details.get("market_cap"),
                "sic_description": details.get("sic_description"),
                "type": details.get("type"),
            }
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if i % 100 == 0:
                _log(f"{i}/{len(tickers)} ({t})")
            await asyncio.sleep(DELAY_S)
    _log("DONE")


if __name__ == "__main__":
    asyncio.run(main())
