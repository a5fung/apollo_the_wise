"""
One-off verification for the Alpaca SIP data feed upgrade.

Runs the four pre-flip checks documented in
~/.claude/plans/shiny-mapping-locket.md before flipping
`ALPACA_DATA_FEED=sip` on production:

  1. Subscription gate    — SIP REST call for AAPL. 403 / auth error
                            means Algo Trader Plus is not active yet.
  2. AAPL IEX vs SIP parity — OHLC should agree within 0.5% on a liquid
                              name on a recent trading day.
  3. URI 2026-04-22 check   — the incident day. SIP must show a non-zero
                              first-minute range where IEX showed zero.
                              If SIP also shows zero, the diagnosis was
                              wrong and we should NOT flip the feed.
  4. 90-day zero-range replay — for every historical `mi_live_trades`
                                row skipped as `setup:zero_range*`,
                                re-fetch via SIP and count how many
                                would now have a usable range. This is
                                the empirical miss-recovery figure.

Hard-wires DataFeed.SIP independent of ALPACA_DATA_FEED so it tests the
subscription without touching live trading. Safe to run any time.

Usage:
    python scripts/verify_sip_parity.py                 # all four checks
    python scripts/verify_sip_parity.py --skip-replay   # skip check 4 (slow)
    python scripts/verify_sip_parity.py --days 30       # replay window
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

_ET = ZoneInfo("America/New_York")

# URI ORB miss day — the canonical test case. If SIP returns zero range
# here, the whole upgrade premise is wrong.
URI_INCIDENT_DATE = date(2026, 4, 22)
URI_TICKER = "URI"


@dataclass
class BarSnapshot:
    open: float
    high: float
    low: float
    close: float
    volume: int

    @property
    def range(self) -> float:
        return self.high - self.low


def _client() -> StockHistoricalDataClient:
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        print("ERROR: ALPACA_API_KEY / ALPACA_SECRET_KEY not set", file=sys.stderr)
        sys.exit(2)
    return StockHistoricalDataClient(api_key, secret_key)


def _fetch_first_bar(
    client: StockHistoricalDataClient, ticker: str, trade_date: date, feed: DataFeed
) -> BarSnapshot | None:
    start = datetime.combine(trade_date, datetime.min.time().replace(hour=9, minute=30), tzinfo=_ET)
    end = start + timedelta(minutes=5)
    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=feed,
    )
    bars = client.get_stock_bars(req)
    bar_data = bars.data if hasattr(bars, "data") else bars
    bar_set = bar_data.get(ticker, [])
    if not bar_set:
        return None
    b = bar_set[0]
    return BarSnapshot(
        open=float(b.open), high=float(b.high), low=float(b.low),
        close=float(b.close), volume=int(b.volume),
    )


def _recent_trading_day() -> date:
    d = datetime.now(_ET).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# ── Check 1: subscription gate ──────────────────────────────────────────────

def check_subscription(client: StockHistoricalDataClient) -> bool:
    print("[1/4] Subscription gate — calling SIP for AAPL on a recent trading day...")
    d = _recent_trading_day()
    try:
        bar = _fetch_first_bar(client, "AAPL", d, DataFeed.SIP)
    except Exception as e:
        msg = str(e)
        if "403" in msg or "forbidden" in msg.lower() or "subscription" in msg.lower():
            print(f"  ❌ SIP subscription NOT active: {e}")
            print("     Subscribe to Algo Trader Plus in the Alpaca dashboard before flipping ALPACA_DATA_FEED=sip.")
        else:
            print(f"  ❌ SIP call failed: {e}")
        return False
    if bar is None:
        print(f"  ⚠️  SIP call succeeded but returned no bars for AAPL {d}. Unusual — investigate before flipping.")
        return False
    print(f"  ✅ SIP active. AAPL {d} O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume:,}")
    return True


# ── Check 2: AAPL IEX vs SIP parity ──────────────────────────────────────────

def check_aapl_parity(client: StockHistoricalDataClient) -> bool:
    d = _recent_trading_day()
    print(f"[2/4] AAPL parity — IEX vs SIP on {d}...")
    try:
        iex = _fetch_first_bar(client, "AAPL", d, DataFeed.IEX)
        sip = _fetch_first_bar(client, "AAPL", d, DataFeed.SIP)
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return False
    if iex is None or sip is None:
        print(f"  ⚠️  No bars (iex={iex is not None}, sip={sip is not None})")
        return False

    def pct_diff(a: float, b: float) -> float:
        return abs(a - b) / a * 100 if a else 0.0

    diffs = {
        "O": pct_diff(iex.open, sip.open),
        "H": pct_diff(iex.high, sip.high),
        "L": pct_diff(iex.low, sip.low),
        "C": pct_diff(iex.close, sip.close),
    }
    max_diff = max(diffs.values())
    print(f"  IEX: O={iex.open:.4f} H={iex.high:.4f} L={iex.low:.4f} C={iex.close:.4f}")
    print(f"  SIP: O={sip.open:.4f} H={sip.high:.4f} L={sip.low:.4f} C={sip.close:.4f}")
    print(f"  Max OHLC diff: {max_diff:.3f}% ({diffs})")
    if max_diff > 0.5:
        print(f"  ⚠️  Divergence > 0.5% — unexpected on a liquid name. Investigate.")
        return False
    print(f"  ✅ Within 0.5% tolerance.")
    return True


# ── Check 3: URI 2026-04-22 ─────────────────────────────────────────────────

def check_uri_incident(client: StockHistoricalDataClient) -> bool:
    print(f"[3/4] URI {URI_INCIDENT_DATE} — the incident day. SIP must show non-zero range.")
    try:
        iex = _fetch_first_bar(client, URI_TICKER, URI_INCIDENT_DATE, DataFeed.IEX)
        sip = _fetch_first_bar(client, URI_TICKER, URI_INCIDENT_DATE, DataFeed.SIP)
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return False
    iex_range = iex.range if iex else None
    sip_range = sip.range if sip else None
    print(f"  IEX range: {iex_range}  SIP range: {sip_range}")
    if sip is None:
        print("  ❌ SIP returned no bar — cannot validate. Stop.")
        return False
    if sip.range <= 0:
        print("  ❌ SIP also shows ZERO range. Diagnosis was wrong; DO NOT flip the feed.")
        return False
    print(f"  ✅ SIP range {sip.range:.4f} > 0 on URI incident day — diagnosis confirmed.")
    return True


# ── Check 4: 90-day zero-range replay ───────────────────────────────────────

async def check_zero_range_replay(client: StockHistoricalDataClient, days: int) -> bool:
    print(f"[4/4] {days}-day zero-range replay — re-fetching historical misses via SIP...")
    try:
        from agents.market_intelligence.db import get_pool
    except Exception as e:
        print(f"  ⚠️  Could not import db module ({e}); skipping replay. "
              "Run from project root on the prod container.")
        return True  # non-fatal

    pool = await get_pool()
    cutoff = _recent_trading_day() - timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, alert_date
            FROM mi_live_trades
            WHERE status = 'skipped'
              AND skip_reason LIKE 'setup:zero_range%'
              AND alert_date >= $1
            ORDER BY alert_date DESC
            """,
            cutoff,
        )

    if not rows:
        print(f"  (no setup:zero_range rows in last {days} days)")
        return True

    recovered = 0
    still_zero = 0
    no_data = 0
    error = 0
    for r in rows:
        ticker = r["ticker"]
        trade_date = r["alert_date"]
        try:
            sip = _fetch_first_bar(client, ticker, trade_date, DataFeed.SIP)
        except Exception as e:
            print(f"  {ticker} {trade_date}: fetch failed — {e}")
            error += 1
            continue
        if sip is None:
            no_data += 1
            continue
        if sip.range > 0:
            recovered += 1
            print(f"  ✅ {ticker} {trade_date}: SIP range ${sip.range:.4f} (O={sip.open:.2f} H={sip.high:.2f} L={sip.low:.2f})")
        else:
            still_zero += 1
            print(f"  ⚠️  {ticker} {trade_date}: SIP still zero range")

    total = len(rows)
    pct = recovered / total * 100 if total else 0
    print()
    print(f"  Total misses: {total}")
    print(f"  Recovered (non-zero SIP range): {recovered} ({pct:.1f}%)")
    print(f"  Still zero on SIP:              {still_zero}")
    print(f"  No SIP bar returned:            {no_data}")
    print(f"  Fetch errors:                   {error}")
    return True


# ── Main ────────────────────────────────────────────────────────────────────

async def main(skip_replay: bool, days: int) -> int:
    client = _client()
    results: dict[str, bool] = {}

    results["subscription"] = check_subscription(client)
    if not results["subscription"]:
        print("\nAborting: subscription check failed. Remaining checks would all 403.")
        return 1

    print()
    results["parity"] = check_aapl_parity(client)
    print()
    results["uri"] = check_uri_incident(client)
    print()
    if not skip_replay:
        results["replay"] = await check_zero_range_replay(client, days)

    print("\n── Summary ──────────────────────────")
    for name, ok in results.items():
        print(f"  {name:<14} {'✅' if ok else '❌'}")
    print()
    critical_ok = results["subscription"] and results["uri"]
    if critical_ok:
        print("Critical checks passed. Safe to set ALPACA_DATA_FEED=sip and restart market-agent.")
        return 0
    print("Critical checks FAILED. DO NOT flip ALPACA_DATA_FEED=sip yet.")
    return 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--skip-replay", action="store_true", help="skip 90-day zero-range replay (faster)")
    p.add_argument("--days", type=int, default=90, help="replay window in calendar days (default 90)")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.skip_replay, args.days)))
