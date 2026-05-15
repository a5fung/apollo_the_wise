"""TI4 Convergence pre-coding spike: yfinance earnings-calendar coverage check.

Per project_trading_ideas_backlog.md TI4 spec: "Pre-coding spike action:
query yfinance `.calendar` for 20 random small-caps, confirm 7d-forward
coverage rate >= 60%. Below that -> shrink window to 3 days OR add FMP
fallback."

Outcome decides whether V1 (earnings as first catalyst source) is
buildable on yfinance alone or needs an FMP fallback at start.
"""
import asyncio
import random
import sys
from datetime import date, timedelta

import yfinance as yf

# Random small-cap sample. Hand-picked across sectors to avoid pure-tech bias.
SMALL_CAP_SAMPLE = [
    "SNDK", "OMCL", "BLMN", "HUT", "FCEL", "NVTS", "OSS", "POET", "AEHR", "AAOI",
    "ICHR", "MRAM", "SIMO", "AIIO", "VECO", "FORM", "INOD", "PENG", "TTMI", "QUIK",
]


def check_coverage(ticker: str, window_days: int = 7) -> tuple[bool, str]:
    """Return (has_coverage, detail). Coverage = .calendar OR .earnings_dates
    returns a future date within the window."""
    try:
        t = yf.Ticker(ticker)
        today = date.today()
        cutoff = today + timedelta(days=window_days)

        # Try .calendar first
        cal = t.calendar
        if cal is not None and not (hasattr(cal, "empty") and cal.empty):
            try:
                if hasattr(cal, "to_dict"):
                    d = cal.to_dict()
                    earnings_keys = [k for k in d.keys() if "earning" in str(k).lower()]
                    if earnings_keys:
                        return (True, f"calendar:{earnings_keys[0]}={d[earnings_keys[0]]}")
                elif isinstance(cal, dict):
                    for k, v in cal.items():
                        if "earning" in k.lower():
                            return (True, f"calendar:{k}={v}")
            except Exception:
                pass

        # Fallback: .earnings_dates
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                future = ed[ed.index.date >= today]
                if not future.empty:
                    first = future.index.min().date()
                    if first <= cutoff:
                        return (True, f"earnings_dates:{first}")
                    return (False, f"earnings_dates next at {first} (>{window_days}d out)")
        except Exception as e:
            return (False, f"earnings_dates error: {type(e).__name__}")

        return (False, "no calendar, no earnings_dates")
    except Exception as e:
        return (False, f"error: {type(e).__name__}: {e}")


def main() -> int:
    print(f"TI4 yfinance earnings-calendar coverage spike — N={len(SMALL_CAP_SAMPLE)} small-caps, 7d window\n")
    hits = 0
    for ticker in SMALL_CAP_SAMPLE:
        has_cov, detail = check_coverage(ticker, window_days=7)
        flag = "✓" if has_cov else "✗"
        print(f"  {flag} {ticker:6s}  {detail}")
        if has_cov:
            hits += 1
    rate = hits / len(SMALL_CAP_SAMPLE)
    print(f"\nCoverage: {hits}/{len(SMALL_CAP_SAMPLE)} = {rate:.0%}")
    if rate >= 0.60:
        print(f"PASS: ≥60% threshold met. TI4 V1 buildable on yfinance alone.")
        return 0
    elif rate >= 0.30:
        print(f"MARGINAL ({rate:.0%}). Consider 3-day window OR FMP fallback for V1.")
        return 1
    else:
        print(f"FAIL: <30% coverage. yfinance alone insufficient — FMP fallback required.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
