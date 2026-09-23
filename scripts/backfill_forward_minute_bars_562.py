"""#562 — one-time historical backfill of forward-window minute bars for EP names
that were surfaced, entered, and stopped out.

DATA CAPTURE ONLY — $0 on the existing Alpaca market-data subscription (SIP feed,
Algo Trader Plus, already paid for). No detection, no signal, no 620 computation:
this script writes raw 1-minute bars to `mi_intraday_bars` and nothing else. Bars
only; nothing here is read by any grading/entry/sizing/ordering path (mirrors
`persist_alert_day_paths` / `persist_forward_alert_paths`'s own THE LINE contract
in agents/market_intelligence/broker/order_manager.py).

WHY. The conversion rehearsal (docs/analysis/conversion_rehearsal_2026-08-18.md,
PLAN #562) found our surfaced tail winners are real but their run does not start on
the EP day — peaks land 7-21 sessions out, and in 3 of 5 cases the base the run
started from formed DAYS LATER and BELOW the EP-day low. The operator's own
delayed-entry trigger is the 620 chart (5-min 6/20 EMA + MACD(6,20),
docs/methodology/620_chart.md) — a 5-minute tool daily bars structurally cannot
price. `order_manager.persist_forward_alert_paths` (shipped 2026-08-18) now
captures this forward window GOING FORWARD for stopped-out names, but only from
the day it started running — every stop-out before 2026-08-18 has zero forward
minute bars. This script is the one-time backfill that closes that historical gap,
so a 620 backtest has something to read at all, now instead of waiting weeks for
fresh stop-outs to accrue.

POPULATION — WIDER than `persist_forward_alert_paths`' own population, and
deliberately so; read this before changing the query. `persist_forward_alert_paths`
reads its population FROM `mi_exit_path_shadow`, which `exit_path_shadow.py` scopes
to `account_mode = 'live'` fills only (its own module docstring, SCOPE section) —
a decision made for a DIFFERENT question (grading a stop-width change against real
money P&L, where mixing paper and live P&L into one number would be invalid). The
question THIS backfill serves is about PRICE ACTION after a stop-out — whether a
620 turn would have re-entered the name — and that does not depend on which account
the fill was booked to; the stock prints the same bars either way. Restricting to
the live-only population would have HALVED the resulting cohort for zero benefit to
this question (verified 2026-08-19: 19-21 live-only stop-outs vs 44 paper+live), so
the population here is built directly from `mi_live_trades`:

    signal_type = 'magna53' AND status IN ('closed', 'stopped') AND entry_price
    IS NOT NULL AND the LAST element of `exits` has reason = 'stop_hit'
    (the same "last exit reason" convention `exit_path_shadow.py` itself uses —
    see its `last_exit = exits[-1]; exit_reason = last_exit.get("reason")`).

This is a data-capture SCOPE decision only — it changes what history this one-shot
script backfills, not what `persist_forward_alert_paths` captures going forward,
and it touches no strategy/entry/exit/sizing/safeguard. Reported plainly in the run
summary so the operator can override (re-run with `--live-only`) if they'd rather
match the narrower population exactly.

NOTE on the "574-ticker-day" figure named when this task was costed (PLAN #562,
2026-08-18 note): that number came from the PIVOT-LADDER probe's "620 prerequisite
costing" section (docs/analysis/pivot_ladder_delayed_entry_562_2026-08-18.md) —
zone-arm approach days swept across the DECLINED-name cohort, a population PLAN.md
itself later flagged as "the WRONG population for this question" (2026-08-19
re-scope note, pointing at the STOPPED-OUT population instead). This script targets
the corrected population and reports its own real count rather than trying to
reproduce 574 — the two numbers are not the same measurement.

WINDOW: trading sessions 1..FORWARD_CAPTURE_WINDOW_SESSIONS (25 — mirrors
`order_manager.FORWARD_CAPTURE_WINDOW_SESSIONS`; duplicated here as a plain int
with a pointer comment rather than imported, so this standalone script does not
pull the whole broker/order_manager module — trading-client construction, live
order helpers, the works — into a process that runs beside the live execution
service for a read-mostly backfill) strictly AFTER alert_date, using the ticker's
own REAL trading-day calendar from `mi_daily_closes`. This is a one-shot backfill
computing the whole window at once, not an incremental daily "is today still in
the window" check, so the precise per-ticker calendar is available and cheap —
unlike the live job's calendar-day/weekday approximation, which only ever needs to
answer that one narrower question. Day 0 (the alert day itself) is deliberately
EXCLUDED — that is `persist_alert_day_paths`' job, not this one's. A session beyond
today simply is not in `mi_daily_closes` yet and is skipped — nothing to fetch; the
live forward job (for its own, narrower population) or a future re-run of this
script will pick it up once it has happened.

FETCH/PERSIST: reuses `alpaca_client.get_minute_bars_range` + `persist_intraday_
bars` UNCHANGED — no second fetcher built. `persist_intraday_bars` inserts with
`ON CONFLICT (ticker, bar_time) DO NOTHING`, so a re-run after a crash never
corrupts or duplicates anything. This script ALSO checks `mi_intraday_bars`
coverage BEFORE each fetch (>= `_PATH_MIN_DAY_BARS` = 300 rows, mirrors both
order_manager jobs) so a re-run skips every ticker-day that already succeeded and
only re-attempts what's missing/thin — resumable at the script layer, not just
idempotent at the DB layer.

RATE LIMIT: a fixed delay between requests (`_REQUEST_DELAY_S`) keeps this well
under Alpaca's per-minute market-data rate limit. `get_minute_bars_range` already
swallows its own exceptions and returns `[]` on any failure (its own docstring) —
this script cannot distinguish "rate-limited" from "legitimately no bars" for a
halted/illiquid name without changing that function, which is out of scope here
(no second fetcher, no edits to the shared fetch path); an empty/thin return is
counted as `thin` either way, exactly like the two existing order_manager jobs do.

Usage (run in the EXECUTION service — Alpaca data creds live there, see
agents/market_intelligence/broker/alpaca_client.py):
  docker exec apollo-execution python -m scripts.backfill_forward_minute_bars_562
  docker exec apollo-execution python -m scripts.backfill_forward_minute_bars_562 --dry-run
  docker exec apollo-execution python -m scripts.backfill_forward_minute_bars_562 --limit 20
  docker exec apollo-execution python -m scripts.backfill_forward_minute_bars_562 --live-only
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker import alpaca_client as alpaca
from agents.market_intelligence.db import get_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_forward_minute_bars_562")

_ET = ZoneInfo("America/New_York")

FORWARD_CAPTURE_WINDOW_SESSIONS = 25  # mirrors order_manager.FORWARD_CAPTURE_WINDOW_SESSIONS
_PATH_MIN_DAY_BARS = 300  # mirrors order_manager._PATH_MIN_DAY_BARS
_REQUEST_DELAY_S = 0.4  # ~150 req/min ceiling — politeness margin under any plan's limit

_POPULATION_SQL_PAPER_AND_LIVE = """
    SELECT DISTINCT ticker, alert_date, account_mode
    FROM mi_live_trades
    WHERE signal_type = 'magna53'
      AND status IN ('closed', 'stopped')
      AND entry_price IS NOT NULL
      AND jsonb_array_length(exits) > 0
      AND (exits -> -1 ->> 'reason') = 'stop_hit'
    ORDER BY alert_date
"""

_POPULATION_SQL_LIVE_ONLY = """
    SELECT DISTINCT ticker, alert_date, 'live' AS account_mode
    FROM mi_exit_path_shadow
    WHERE is_exit_day = true AND exit_reason = 'stop_hit'
    ORDER BY alert_date
"""

_FORWARD_DAYS_SQL = """
    SELECT trade_date FROM mi_daily_closes
    WHERE ticker = $1 AND trade_date > $2
    ORDER BY trade_date
    LIMIT $3
"""

# ⚠ day_start/day_end MUST be passed in as tz-AWARE (ZoneInfo("America/New_York"))
# datetimes computed in Python — never built as `$day::date + interval` inside
# the SQL itself. `bar_time` is TIMESTAMPTZ; a naive date+interval expression is
# resolved using the DB SESSION's timezone (this DB's is UTC — confirmed via
# `SHOW timezone`), which silently asks for 09:30-16:00 UTC (05:30-12:00 ET on
# EDT) instead of the real 09:30-16:00 ET session — the exact naive-datetime
# class CLAUDE.md's ET section warns about, just on the SQL side instead of the
# Python side. `order_manager.persist_alert_day_paths` /
# `persist_forward_alert_paths` already get this right, building
# `datetime.combine(day, ..., tzinfo=_ET)` in Python and binding it directly;
# this mirrors that (caught live during this script's own first prod smoke
# test, before the full run — see PLAN #562).
_COVERAGE_SQL = """
    SELECT count(*) FROM mi_intraday_bars
    WHERE ticker = $1 AND bar_time >= $2 AND bar_time <= $3
"""


async def build_population(conn, *, live_only: bool = False) -> list[dict]:
    """The (ticker, alert_date) pairs this backfill targets. See module docstring
    for why the default is paper+live (magna53 stop-outs from `mi_live_trades`
    directly) rather than `persist_forward_alert_paths`' narrower live-only
    population. `--live-only` reproduces that narrower population exactly, for an
    operator who wants the two capture paths to match precisely instead."""
    sql = _POPULATION_SQL_LIVE_ONLY if live_only else _POPULATION_SQL_PAPER_AND_LIVE
    rows = await conn.fetch(sql)
    return [
        {"ticker": r["ticker"], "alert_date": r["alert_date"],
         "account_mode": r["account_mode"]}
        for r in rows if r["ticker"] and r["alert_date"]
    ]


async def forward_session_days(
    conn, ticker: str, alert_date: date, window: int = FORWARD_CAPTURE_WINDOW_SESSIONS,
) -> list[date]:
    """The ticker's own real trading days strictly after `alert_date`, capped at
    `window` sessions and at however far `mi_daily_closes` currently reaches (never
    fabricates a future date that hasn't happened yet)."""
    rows = await conn.fetch(_FORWARD_DAYS_SQL, ticker, alert_date, window)
    return [r["trade_date"] for r in rows]


def session_bounds(day: date) -> tuple[datetime, datetime]:
    """The 09:30-16:00 ET session boundaries for `day`, as tz-AWARE datetimes —
    the only safe way to bind against a TIMESTAMPTZ column (see `_COVERAGE_SQL`'s
    comment). Shared by the coverage check and the fetch call so both ask about
    the exact same window."""
    day_start = datetime.combine(day, datetime.min.time().replace(hour=9, minute=30),
                                  tzinfo=_ET)
    day_end = datetime.combine(day, datetime.min.time().replace(hour=16, minute=0),
                                tzinfo=_ET)
    return day_start, day_end


async def existing_bar_count(conn, ticker: str, day_start: datetime, day_end: datetime) -> int:
    n = await conn.fetchval(_COVERAGE_SQL, ticker, day_start, day_end)
    return int(n or 0)


async def run_backfill(
    *, dry_run: bool = False, limit: int | None = None, live_only: bool = False,
    request_delay_s: float = _REQUEST_DELAY_S,
) -> dict:
    """Orchestrates the backfill. Returns the tally dict the CLI prints and the
    final report quotes verbatim:
      {"population": n names, "ticker_days_targeted": n, "already_covered": n,
       "fetched": n, "thin": n, "api_calls": n}
    `limit` caps the number of ACTUAL FETCHES performed (coverage checks still run
    over the whole population) — for a bounded smoke test before a full run.
    """
    out = {"population": 0, "ticker_days_targeted": 0, "already_covered": 0,
           "fetched": 0, "thin": 0, "api_calls": 0}
    pool = await get_pool()
    async with pool.acquire() as conn:
        population = await build_population(conn, live_only=live_only)
    out["population"] = len(population)
    logger.info(f"Population: {len(population)} magna53 stop-outs "
                f"({'live-only' if live_only else 'paper+live'})")

    for row in population:
        ticker, alert_date = row["ticker"], row["alert_date"]
        async with pool.acquire() as conn:
            days = await forward_session_days(conn, ticker, alert_date)
        out["ticker_days_targeted"] += len(days)

        for day in days:
            day_start, day_end = session_bounds(day)
            async with pool.acquire() as conn:
                n_have = await existing_bar_count(conn, ticker, day_start, day_end)
            if n_have >= _PATH_MIN_DAY_BARS:
                out["already_covered"] += 1
                continue

            if dry_run:
                out["thin"] += 1  # would-fetch, counted here so dry-run totals match a real run
                continue
            if limit is not None and out["api_calls"] >= limit:
                out["thin"] += 1  # limited out this run; still missing, next run picks it up
                continue

            try:
                out["api_calls"] += 1
                bars = await alpaca.get_minute_bars_range(ticker, day_start, day_end)
                if bars:
                    await alpaca.persist_intraday_bars(ticker, bars)
                if len(bars) >= _PATH_MIN_DAY_BARS:
                    out["fetched"] += 1
                else:
                    out["thin"] += 1
                    logger.warning(f"{ticker} {day}: thin ({len(bars)}/390 bars)")
            except Exception as e:  # one bad ticker-day must not kill the whole backfill
                out["thin"] += 1
                logger.warning(f"{ticker} {day}: fetch failed: {e}")
            await asyncio.sleep(request_delay_s)

    return out


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                     help="Report the cohort and coverage; fetch nothing.")
    ap.add_argument("--limit", type=int, default=None,
                     help="Cap the number of actual API fetch calls this run "
                          "(coverage over the whole population is still checked).")
    ap.add_argument("--live-only", action="store_true",
                     help="Match persist_forward_alert_paths' own population "
                          "exactly (account_mode='live' only) instead of the "
                          "wider paper+live default.")
    return ap.parse_args(argv)


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    started = datetime.now(_ET)
    logger.info(f"Run started {started.isoformat()} "
                f"(dry_run={args.dry_run} limit={args.limit} live_only={args.live_only})")
    out = await run_backfill(dry_run=args.dry_run, limit=args.limit, live_only=args.live_only)
    finished = datetime.now(_ET)
    logger.info(f"DONE in {(finished - started).total_seconds():.1f}s — {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
