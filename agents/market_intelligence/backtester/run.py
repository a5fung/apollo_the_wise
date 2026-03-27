"""CLI entry point for EP gap trading backtest."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path


async def main(args: argparse.Namespace) -> None:
    # Late imports to avoid circular deps
    from agents.market_intelligence.backtester.engine import run_backtest
    from agents.market_intelligence.backtester.report import export_csv, generate_report
    from agents.market_intelligence.collector import et_today

    today = et_today()
    to_date = today
    from_date = today - timedelta(days=args.days)

    result = await run_backtest(
        from_date=from_date,
        to_date=to_date,
        position_size=args.size,
        min_score=args.score,
        initial_capital=args.capital,
    )

    report = generate_report(result)
    print(report)

    if args.csv:
        csv_data = export_csv(result)
        Path(args.csv).write_text(csv_data)
        print(f"\nTrade log exported to {args.csv}")


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="EP Gap Trading Backtest",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--days", type=int, default=90, help="Lookback days")
    parser.add_argument("--score", type=float, default=70, help="Minimum EP score")
    parser.add_argument("--size", type=float, default=10_000, help="Position size ($)")
    parser.add_argument("--capital", type=float, default=100_000, help="Initial capital ($)")
    parser.add_argument("--csv", type=str, default=None, help="Export trade log to CSV file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
