"""COT family — weekly 1-minute futures archive (operator ruled "Go", 2026-11-15).

WHAT: once a week, save free 1-minute futures bars (extended hours included) for every COT market, so the COT
family's first-tick news-failure rule can be tested later. yfinance keeps only ~30 days of 1-minute history, so
a weekly save loses nothing. SSoT: docs/setups/cot_family.md ("Data — 1-minute archive").

OUTPUT: ONE gzip CSV per run at <logs>/cot_minutes/<run_date_ET>.csv.gz, columns market,ticker,ts_et,o,h,l,c,v.
Each run fetches the last 8 calendar days, so consecutive files OVERLAP by design; DEDUPE AT READ TIME on
(market, ts_et). Written atomically (tmp + rename). ONE audit row per run. Read-only: no DB table, no broker, no
money path. One ticker's failure never stops the rest; a run where EVERY ticker fails raises AFTER the audit row
so audit_wrap pages.
"""
from __future__ import annotations

import asyncio
import csv
import gzip
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from agents.market_intelligence import cot_family
from shared.dates import _ET

logger = logging.getLogger(__name__)

JOB_ID = "cot_minutes_archive"
EVT_ARCHIVE = "cot_minutes_archive"
LOOKBACK_DAYS = 8
COLUMNS = ["market", "ticker", "ts_et", "o", "h", "l", "c", "v"]
REPO = Path(__file__).resolve().parents[2]          # /app in the container
ENV_DIR = "COT_MINUTES_DIR"

# market -> yfinance ticker, DERIVED from the COT family's own market table (review 2026-11-15: it was a hand copy).
# So it holds exactly the markets the alerts cover: the dollar index is IN (DX-Y.NYB does serve 1-minute bars —
# 8,003 rows over 8 days, checked 2026-11-15), and oats (ZO=F) is OUT (the CFTC no longer reports it, so it has no
# index, no set up and no alert to test).
MARKET_TICKERS: dict[str, str] = {m: cot_family.ticker_of(m) for m in cot_family.MARKETS}


class CotMinutesArchiveError(RuntimeError):
    """Every ticker failed or came back empty (the page)."""


def out_dir() -> Path:
    return Path(os.environ.get(ENV_DIR) or REPO / "logs" / "cot_minutes")


def _fetch_one(ticker: str):
    """cot_family's own 1-minute pull, over the archive's longer window."""
    return cot_family.fetch_minute_frame(ticker, f"{LOOKBACK_DAYS}d")


def _rows_for(market: str, ticker: str, df) -> list[list]:
    if df is None or len(df) == 0:
        return []
    out = []
    for ts, (o, h, l, c, v) in zip(cot_family.et_index(df), df[["Open", "High", "Low", "Close", "Volume"]].itertuples(index=False)):
        if c != c:  # NaN close: no bar
            continue
        out.append([market, ticker, ts.isoformat(), o, h, l, c, v])
    return out


def fetch_all(tickers: dict[str, str] | None = None, fetch=_fetch_one) -> tuple[list[list], dict]:
    """Blocking. Returns (rows, stats); one ticker's exception is recorded, never raised."""
    rows: list[list] = []
    stats = {"ok": 0, "empty": 0, "failed": 0, "failed_tickers": []}
    for market, ticker in (tickers or MARKET_TICKERS).items():
        try:
            r = _rows_for(market, ticker, fetch(ticker))
        except Exception as e:  # loud-ok: counted + audited; all-fail raises after the audit row
            logger.warning(f"{JOB_ID}: {ticker} failed: {type(e).__name__}: {e}")
            stats["failed"] += 1
            stats["failed_tickers"].append(ticker)
            continue
        if r:
            stats["ok"] += 1
            rows.extend(r)
        else:
            stats["empty"] += 1
    return rows, stats


def write_archive(rows: list[list], run_date, directory: Path | None = None) -> Path:
    d = directory or out_dir()
    d.mkdir(parents=True, exist_ok=True)
    final = d / f"{run_date.isoformat()}.csv.gz"
    tmp = d / f".{final.name}.tmp"
    with gzip.open(tmp, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    os.replace(tmp, final)
    return final


async def run_scheduled(now_et: datetime | None = None, *, tickers: dict[str, str] | None = None,
                        fetch=_fetch_one, directory: Path | None = None) -> int:
    """The job body under audit_wrap. Returns rows written (mi_job_runs)."""
    from agents.market_intelligence.db import log_audit_event

    now = now_et or datetime.now(_ET)
    run_date = now.date()
    rows, stats = await asyncio.to_thread(fetch_all, tickers, fetch)
    n_tickers = stats["ok"] + stats["empty"] + stats["failed"]
    path = None
    nbytes = 0
    if stats["ok"]:
        path = await asyncio.to_thread(write_archive, rows, run_date, directory)
        nbytes = path.stat().st_size
    detail = {"rows": len(rows), "ok": stats["ok"], "empty": stats["empty"], "failed": stats["failed"],
              "failed_tickers": stats["failed_tickers"], "path": str(path) if path else None, "bytes": nbytes}
    await log_audit_event(
        EVT_ARCHIVE,
        (f"{run_date}: {len(rows)} rows; tickers ok {stats['ok']} empty {stats['empty']} failed {stats['failed']} "
         f"of {n_tickers}; {path} {nbytes} bytes")[:300],
        json.dumps(detail),
    )
    if not stats["ok"]:
        raise CotMinutesArchiveError(
            f"{JOB_ID}: no ticker returned bars (empty {stats['empty']}, failed {stats['failed']} of {n_tickers})")
    return len(rows)
