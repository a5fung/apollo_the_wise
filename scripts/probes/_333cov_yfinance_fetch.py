#!/usr/bin/env python3
"""#333 measurement task (this session) — yfinance forward-estimate + actual-revenue
probe across the live alert population (trailing 90 days, ~176 tickers).

READ-ONLY, $0 (yfinance is free/unofficial, no key). Fetches, per ticker:
  - revenue_estimate / earnings_estimate for the NEAR forward quarter ('0q') —
    avg/low/high/numberOfAnalysts, the exact fields the recorder already stores.
  - quarterly_financials -> "Total Revenue", the last 4 REPORTED quarters — the
    reality anchor an estimate gets sanity-checked against.

Traps avoided (per the task brief): no ret_*/MFE fields touched here at all; no
mi_daily_closes read (this uses yfinance's own financials, not our price tables).
Capture once to OUT_PATH, read many — this script is meant to run exactly once.
"""
import json
import time

import yfinance as yf

OUT_PATH = "/tmp/_333cov_yfinance_out.json"
PACE_SECONDS = 0.35

with open("/tmp/_333cov_tickers.json") as f:
    TICKERS = json.load(f)


def _row(df, period):
    try:
        if df is None or period not in df.index:
            return None
        r = df.loc[period].to_dict()
        return {k: (None if v != v else v) for k, v in r.items()}  # NaN -> None
    except Exception:
        return None


def _recent_actual_revenues(t, n=4):
    try:
        qf = t.quarterly_financials
        if qf is None or "Total Revenue" not in qf.index:
            return []
        s = qf.loc["Total Revenue"].dropna()
        out = []
        for idx, val in list(s.items())[:n]:
            out.append({"period_end": str(idx.date()) if hasattr(idx, "date") else str(idx),
                        "revenue": float(val)})
        return out
    except Exception:
        return []


def main():
    out = {}
    errors = {}
    for i, ticker in enumerate(TICKERS):
        try:
            t = yf.Ticker(ticker)
            rev_df = t.revenue_estimate
            eps_df = t.earnings_estimate
            rev_0q = _row(rev_df, "0q")
            eps_0q = _row(eps_df, "0q")
            actuals = _recent_actual_revenues(t)
            out[ticker] = {"revenue_0q": rev_0q, "eps_0q": eps_0q, "recent_actual_revenue": actuals}
        except Exception as e:
            errors[ticker] = f"{type(e).__name__}: {e}"
        if (i + 1) % 20 == 0:
            print(f"...{i + 1}/{len(TICKERS)}")
        time.sleep(PACE_SECONDS)

    with open(OUT_PATH, "w") as f:
        json.dump({"data": out, "errors": errors}, f)
    print(f"DONE {len(out)} tickers, {len(errors)} errors -> {OUT_PATH}")


if __name__ == "__main__":
    main()
