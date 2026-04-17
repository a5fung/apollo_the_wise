"""
O'Neil-style fundamental analysis — earnings + sales growth quality filters.

Fetches via yfinance (free, no API key). On-demand only — not in default briefing.

Quality flags (CAN SLIM fundamentals layer):
- EPS acceleration: latest quarter YoY growth rate > prior quarter
- Consecutive quarters ≥25% YoY EPS growth
- Revenue confirming earnings (rev growth ≥15%)
- Gross margin trend: expanding / stable / contracting
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _quarter_label(dt: Any) -> str:
    """Convert a datetime-like to a readable label like 'Q2'25'."""
    try:
        q = (dt.month - 1) // 3 + 1
        return f"Q{q}'{str(dt.year)[2:]}"
    except Exception:
        return str(dt)[:7]


def _safe_float(val: Any) -> float | None:
    try:
        f = float(val)
        return None if (f != f) else f  # NaN check
    except (TypeError, ValueError):
        return None


def _yoy_pct(new: float, old: float) -> float | None:
    if old and old != 0:
        return round((new - old) / abs(old) * 100, 1)
    return None


def _avg_gross_margin(gross_row: Any, rev_row: Any, cols: list) -> float | None:
    margins = []
    for c in cols:
        g = _safe_float(gross_row.get(c))
        r = _safe_float(rev_row.get(c))
        if g is not None and r is not None and r != 0:
            margins.append(g / r * 100)
    return sum(margins) / len(margins) if margins else None


def _gross_margin_trend(q_income: Any) -> str:
    try:
        if q_income is None or q_income.empty:
            return "unknown"
        gross_row = next((q_income.loc[k] for k in ["Gross Profit"] if k in q_income.index), None)
        rev_row = next((q_income.loc[k] for k in ["Total Revenue", "Revenue"] if k in q_income.index), None)
        if gross_row is None or rev_row is None:
            return "unknown"
        cols = sorted(list(q_income.columns))
        if len(cols) < 4:
            return "unknown"
        recent = _avg_gross_margin(gross_row, rev_row, cols[-2:])
        prior = _avg_gross_margin(gross_row, rev_row, cols[-4:-2])
        if recent is None or prior is None:
            return "unknown"
        delta = recent - prior
        if delta > 1.0:
            return "expanding"
        if delta < -1.0:
            return "contracting"
        return "stable"
    except Exception:
        return "unknown"


async def get_fundamentals(ticker: str) -> dict[str, Any]:
    """
    Fetch O'Neil-style fundamentals for a ticker via yfinance.

    Returns:
        ticker, quarterly_eps, quarterly_revenue, annual_eps, annual_revenue,
        gross_margin_pct, next_earnings_date, quality_flags.
    Fails gracefully on any missing data — missing fields are None or empty lists.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"ticker": ticker, "error": "yfinance not installed"}

    try:
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker.upper())
    except Exception as e:
        logger.warning(f"get_fundamentals: failed to init Ticker for {ticker}: {e}")
        return {"ticker": ticker.upper(), "error": str(e)}

    def _fetch_q_income():
        result = getattr(t, "quarterly_income_stmt", None)
        if result is None:
            result = getattr(t, "quarterly_financials", None)
        return result

    def _fetch_a_income():
        result = getattr(t, "income_stmt", None)
        if result is None:
            result = getattr(t, "financials", None)
        return result

    def _fetch_info():
        try:
            return t.info or {}
        except Exception:
            return {}

    def _fetch_calendar():
        try:
            return t.calendar
        except Exception:
            return None

    def _fetch_earnings_estimate():
        try:
            return t.earnings_estimate
        except Exception:
            return None

    def _fetch_revenue_estimate():
        try:
            return t.revenue_estimate
        except Exception:
            return None

    _YF_TIMEOUT = 30.0
    q_income, a_income, info, calendar, earnings_est, revenue_est = await asyncio.gather(
        asyncio.wait_for(loop.run_in_executor(None, _fetch_q_income), timeout=_YF_TIMEOUT),
        asyncio.wait_for(loop.run_in_executor(None, _fetch_a_income), timeout=_YF_TIMEOUT),
        asyncio.wait_for(loop.run_in_executor(None, _fetch_info), timeout=_YF_TIMEOUT),
        asyncio.wait_for(loop.run_in_executor(None, _fetch_calendar), timeout=_YF_TIMEOUT),
        asyncio.wait_for(loop.run_in_executor(None, _fetch_earnings_estimate), timeout=_YF_TIMEOUT),
        asyncio.wait_for(loop.run_in_executor(None, _fetch_revenue_estimate), timeout=_YF_TIMEOUT),
        return_exceptions=True,
    )

    # Normalize exceptions to safe defaults
    if isinstance(q_income, Exception): q_income = None
    if isinstance(a_income, Exception): a_income = None
    if isinstance(info, Exception):     info = {}
    if isinstance(calendar, Exception): calendar = None
    if isinstance(earnings_est, Exception): earnings_est = None
    if isinstance(revenue_est, Exception): revenue_est = None

    result: dict[str, Any] = {"ticker": ticker.upper()}

    # ── Quarterly EPS & Revenue ───────────────────────────────────────────────

    quarterly_eps: list[dict] = []
    quarterly_revenue: list[dict] = []
    quarterly_gross_margin: list[dict] = []
    gross_margin_pct: float | None = None

    if q_income is not None:
        try:
            all_cols = sorted(list(q_income.columns))   # oldest first
            show_cols = all_cols[-8:]                   # up to 8 quarters

            # EPS rows to try (yfinance varies by version / ticker)
            eps_row = next(
                (q_income.loc[k] for k in
                 ["Basic EPS", "Diluted EPS",
                  "Basic Earnings Per Share", "Diluted Earnings Per Share"]
                 if k in q_income.index),
                None,
            )
            # Fallback: derive from Net Income / shares
            if eps_row is None and "Net Income" in q_income.index:
                ni_row = q_income.loc["Net Income"]
                shares_row = next(
                    (q_income.loc[k] for k in
                     ["Diluted Average Shares", "Basic Average Shares",
                      "Shares Outstanding"]
                     if k in q_income.index),
                    None,
                )
                if shares_row is not None:
                    eps_row = ni_row / shares_row

            rev_row = next(
                (q_income.loc[k] for k in ["Total Revenue", "Revenue"]
                 if k in q_income.index),
                None,
            )
            gross_row = q_income.loc["Gross Profit"] if "Gross Profit" in q_income.index else None

            for col in show_cols:
                label = _quarter_label(col)
                # Find same quarter 1 year prior for YoY
                idx = all_cols.index(col)
                prior_col = all_cols[idx - 4] if idx >= 4 else None

                if eps_row is not None:
                    eps = _safe_float(eps_row.get(col))
                    if eps is not None:
                        prior_eps = _safe_float(eps_row.get(prior_col)) if prior_col is not None else None
                        quarterly_eps.append({
                            "period": label,
                            "eps": round(eps, 2),
                            "yoy_pct": _yoy_pct(eps, prior_eps) if prior_eps is not None else None,
                        })

                if rev_row is not None:
                    rev = _safe_float(rev_row.get(col))
                    if rev is not None:
                        prior_rev = _safe_float(rev_row.get(prior_col)) if prior_col is not None else None
                        quarterly_revenue.append({
                            "period": label,
                            "revenue_m": round(rev / 1_000_000, 1),
                            "yoy_pct": _yoy_pct(rev, prior_rev) if prior_rev is not None else None,
                        })

                # Gross margin per quarter — sanity-clamped to 0–100%
                if gross_row is not None and rev_row is not None:
                    g = _safe_float(gross_row.get(col))
                    r = _safe_float(rev_row.get(col))
                    if g is not None and r is not None and r != 0:
                        gm = g / r * 100
                        if 0 <= gm <= 100:
                            quarterly_gross_margin.append({
                                "period": label,
                                "gm_pct": round(gm, 1),
                            })

            # Latest quarter gross margin for header
            if quarterly_gross_margin:
                gross_margin_pct = quarterly_gross_margin[-1]["gm_pct"]

        except Exception:
            logger.warning(f"Quarterly income parsing failed for {ticker}", exc_info=True)

    # Fallback: info dict gross margin if income stmt parsing yielded nothing valid
    if gross_margin_pct is None and isinstance(info, dict):
        gm = info.get("grossMargins")
        if gm and 0 < float(gm) <= 1.0:  # yfinance returns 0.0–1.0 fraction
            gross_margin_pct = round(float(gm) * 100, 1)

    result["quarterly_eps"] = quarterly_eps
    result["quarterly_revenue"] = quarterly_revenue
    result["quarterly_gross_margin"] = quarterly_gross_margin
    result["gross_margin_pct"] = gross_margin_pct

    # ── Annual EPS & Revenue ─────────────────────────────────────────────────

    annual_eps: list[dict] = []
    annual_revenue: list[dict] = []

    if a_income is not None:
        try:
            a_cols = sorted(list(a_income.columns))[-5:]  # last 5 fiscal years

            a_eps_row = next(
                (a_income.loc[k] for k in
                 ["Basic EPS", "Diluted EPS",
                  "Basic Earnings Per Share", "Diluted Earnings Per Share"]
                 if k in a_income.index),
                None,
            )
            if a_eps_row is None and "Net Income" in a_income.index:
                ni_row = a_income.loc["Net Income"]
                shares_row = next(
                    (a_income.loc[k] for k in
                     ["Diluted Average Shares", "Basic Average Shares"]
                     if k in a_income.index),
                    None,
                )
                if shares_row is not None:
                    a_eps_row = ni_row / shares_row

            a_rev_row = next(
                (a_income.loc[k] for k in ["Total Revenue", "Revenue"]
                 if k in a_income.index),
                None,
            )

            for col in a_cols:
                year = col.year if hasattr(col, "year") else int(str(col)[:4])
                if a_eps_row is not None:
                    eps = _safe_float(a_eps_row.get(col))
                    if eps is not None:
                        annual_eps.append({"year": year, "eps": round(eps, 2)})
                if a_rev_row is not None:
                    rev = _safe_float(a_rev_row.get(col))
                    if rev is not None:
                        annual_revenue.append({"year": year, "revenue_m": round(rev / 1_000_000, 1)})

        except Exception:
            logger.warning(f"Annual income parsing failed for {ticker}", exc_info=True)

    result["annual_eps"] = annual_eps
    result["annual_revenue"] = annual_revenue

    # ── Forward estimates (consensus) ─────────────────────────────────────────

    forward_eps: list[dict] = []
    if earnings_est is not None and hasattr(earnings_est, "empty") and not earnings_est.empty:
        try:
            # Index = period (0q, +1q, 0y, +1y), Columns = fields (avg, low, high, growth, ...)
            for period in earnings_est.index:
                entry: dict[str, Any] = {"period": str(period)}
                for field in ["avg", "low", "high", "numberOfAnalysts", "growth"]:
                    if field in earnings_est.columns:
                        val = _safe_float(earnings_est.at[period, field])
                        if field == "growth" and val is not None:
                            entry["growth_pct"] = round(val * 100, 1)
                        elif field == "numberOfAnalysts" and val is not None:
                            entry["num_analysts"] = int(val)
                        elif val is not None:
                            entry[field] = round(val, 2)
                forward_eps.append(entry)
        except Exception:
            logger.warning(f"Forward EPS parsing failed for {ticker}", exc_info=True)
    result["forward_eps"] = forward_eps

    forward_revenue: list[dict] = []
    if revenue_est is not None and hasattr(revenue_est, "empty") and not revenue_est.empty:
        try:
            for period in revenue_est.index:
                entry = {"period": str(period)}
                for field in ["avg", "low", "high", "numberOfAnalysts", "growth"]:
                    if field in revenue_est.columns:
                        val = _safe_float(revenue_est.at[period, field])
                        if field == "growth" and val is not None:
                            entry["growth_pct"] = round(val * 100, 1)
                        elif field == "numberOfAnalysts" and val is not None:
                            entry["num_analysts"] = int(val)
                        elif field in ("avg", "low", "high") and val is not None:
                            entry[field] = round(val / 1_000_000, 1)  # to $M
                        elif val is not None:
                            entry[field] = val
                forward_revenue.append(entry)
        except Exception:
            logger.warning(f"Forward revenue parsing failed for {ticker}", exc_info=True)
    result["forward_revenue"] = forward_revenue

    # ── Next earnings date ───────────────────────────────────────────────────

    next_earnings: str | None = None
    try:
        if isinstance(calendar, dict):
            ed = calendar.get("Earnings Date")
            if ed:
                val = ed[0] if hasattr(ed, "__getitem__") else ed
                next_earnings = str(val.date() if hasattr(val, "date") else val)
        elif calendar is not None and hasattr(calendar, "empty") and not calendar.empty:
            if "Earnings Date" in calendar.index:
                val = calendar.loc["Earnings Date"].iloc[0]
                next_earnings = str(val.date() if hasattr(val, "date") else val)
    except Exception:
        pass

    if next_earnings is None and isinstance(info, dict):
        ts = info.get("nextEarningsDate") or info.get("earningsTimestamp")
        if ts:
            try:
                next_earnings = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except Exception:
                pass

    result["next_earnings_date"] = next_earnings

    # ── Quality flags ────────────────────────────────────────────────────────

    eps_yoy = [q["yoy_pct"] for q in quarterly_eps if q.get("yoy_pct") is not None]
    rev_yoy = [q["yoy_pct"] for q in quarterly_revenue if q.get("yoy_pct") is not None]

    flags: dict[str, Any] = {}

    # EPS acceleration: latest qtr growth rate > prior qtr growth rate
    flags["eps_accelerating"] = bool(eps_yoy[-1] > eps_yoy[-2]) if len(eps_yoy) >= 2 else None

    # Consecutive quarters ≥25% EPS growth (counting from most recent)
    streak = 0
    for pct in reversed(eps_yoy):
        if pct >= 25:
            streak += 1
        else:
            break
    flags["eps_streak_25pct"] = streak

    # Revenue confirms earnings (latest rev YoY ≥15%)
    flags["sales_confirms"] = bool(rev_yoy[-1] >= 15) if rev_yoy else None

    # Gross margin trend
    flags["gross_margin_trend"] = _gross_margin_trend(q_income)

    result["quality_flags"] = flags
    return result


async def get_fundamentals_batch(
    tickers: list[str],
    concurrency: int = 5,
) -> dict[str, dict]:
    """
    Fetch fundamentals for multiple tickers concurrently.

    Args:
        tickers: List of ticker symbols.
        concurrency: Max simultaneous yfinance calls (default 5).

    Returns:
        Dict mapping ticker → fundamentals dict (same shape as get_fundamentals).
        Tickers that fail return {"ticker": T, "error": "..."}.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _fetch(ticker: str) -> dict:
        async with semaphore:
            return await get_fundamentals(ticker)

    results = await asyncio.gather(*[_fetch(t) for t in tickers], return_exceptions=True)

    out: dict[str, dict] = {}
    for ticker, res in zip(tickers, results):
        if isinstance(res, Exception):
            out[ticker.upper()] = {"ticker": ticker.upper(), "error": str(res)}
        else:
            out[ticker.upper()] = res
    return out


# ── Formatter ─────────────────────────────────────────────────────────────────

def format_fundamentals(data: dict) -> str:
    """Format fundamentals as a Telegram-ready text block (Caruso-style)."""
    if "error" in data:
        return f"Fundamentals unavailable for `{data.get('ticker', '?')}`: {data['error']}"

    ticker = data["ticker"]
    next_eps = data.get("next_earnings_date")
    flags = data.get("quality_flags", {})
    q_eps = data.get("quarterly_eps", [])
    q_rev = data.get("quarterly_revenue", [])
    q_gm = data.get("quarterly_gross_margin", [])
    a_eps = data.get("annual_eps", [])
    a_rev = data.get("annual_revenue", [])

    lines = [f"*{ticker} — Fundamentals*"]

    # Header: next earnings only (gross margin shown per-quarter in table)
    if next_eps:
        try:
            d = date.fromisoformat(next_eps)
            lines.append(f"Next EPS {d.strftime('%b %d, %Y')}")
        except Exception:
            lines.append(f"Next EPS {next_eps}")

    # Quarterly table — last 6 quarters
    # Align all rows to the same period set (use EPS periods as anchor)
    show_eps = q_eps[-6:]
    show_rev = q_rev[-6:]
    periods = [q["period"] for q in show_eps] or [q["period"] for q in show_rev]

    # Build a GM% lookup by period for the same set of quarters
    gm_by_period = {q["period"]: q["gm_pct"] for q in q_gm}

    if periods:
        lines.append("")
        lines.append("*Quarterly (last 6 qtrs, YoY %)*")
        lines.append("```")
        col_w = 8
        lines.append("      " + "".join(p.rjust(col_w) for p in periods))

        if show_eps:
            eps_vals = [f"{q['eps']:.2f}" for q in show_eps]
            lines.append("EPS   " + "".join(v.rjust(col_w) for v in eps_vals))
            pct_vals = [
                f"{q['yoy_pct']:+.0f}%" if q.get("yoy_pct") is not None else "n/a"
                for q in show_eps
            ]
            lines.append("  %   " + "".join(v.rjust(col_w) for v in pct_vals))

        if show_rev:
            rev_vals = [f"{q['revenue_m']:.0f}M" for q in show_rev]
            lines.append("Rev   " + "".join(v.rjust(col_w) for v in rev_vals))
            pct_vals = [
                f"{q['yoy_pct']:+.0f}%" if q.get("yoy_pct") is not None else "n/a"
                for q in show_rev
            ]
            lines.append("  %   " + "".join(v.rjust(col_w) for v in pct_vals))

        # Gross margin row — show actual % per quarter so trend is visible
        gm_vals = [
            f"{gm_by_period[p]:.0f}%" if p in gm_by_period else "n/a"
            for p in periods
        ]
        if any(v != "n/a" for v in gm_vals):
            lines.append("GM%   " + "".join(v.rjust(col_w) for v in gm_vals))

        lines.append("```")

    # Annual table — last 5 filed fiscal years (current FY shown in quarterly)
    if a_eps or a_rev:
        lines.append("*Annual (filed FY)*")
        lines.append("```")
        years = sorted({e["year"] for e in a_eps} | {r["year"] for r in a_rev})
        col_w = 8
        lines.append("      " + "".join(str(y).rjust(col_w) for y in years))

        if a_eps:
            by_year = {e["year"]: e["eps"] for e in a_eps}
            lines.append(
                "EPS   " + "".join(
                    f"{by_year[y]:.2f}".rjust(col_w) if y in by_year else "---".rjust(col_w)
                    for y in years
                )
            )
        if a_rev:
            by_year = {r["year"]: r["revenue_m"] for r in a_rev}
            lines.append(
                "Rev   " + "".join(
                    f"{by_year[y]:.0f}M".rjust(col_w) if y in by_year else "---".rjust(col_w)
                    for y in years
                )
            )
        lines.append("```")

    # Quality flags — EPS and revenue only; margin is now visible in the table
    flag_lines = []

    acc = flags.get("eps_accelerating")
    if acc is True:
        flag_lines.append("🟢 EPS accelerating")
    elif acc is False:
        flag_lines.append("🔴 EPS decelerating")

    streak = flags.get("eps_streak_25pct", 0)
    if streak >= 3:
        flag_lines.append(f"🟢 {streak} consecutive qtrs ≥25% EPS growth")
    elif streak >= 1:
        flag_lines.append(f"🟡 {streak} qtr(s) ≥25% EPS growth")
    else:
        flag_lines.append("🔴 No recent qtrs with ≥25% EPS growth")

    confirms = flags.get("sales_confirms")
    if confirms is True:
        flag_lines.append("🟢 Revenue confirms (≥15% growth)")
    elif confirms is False:
        flag_lines.append("🔴 Revenue weak (<15% growth)")

    if flag_lines:
        lines.append("")
        lines += flag_lines

    # Forward estimates
    fwd_eps = data.get("forward_eps", [])
    fwd_rev = data.get("forward_revenue", [])
    _FWD_LABELS = {"0q": "CurQ", "+1q": "NxtQ", "0y": "CurY", "+1y": "NxtY"}
    if fwd_eps or fwd_rev:
        lines.append("")
        lines.append("*Forward Estimates (Consensus)*")
        lines.append("```")
        periods = [e["period"] for e in fwd_eps] or [r["period"] for r in fwd_rev]
        labels = [_FWD_LABELS.get(p, p) for p in periods]
        col_w = 10
        lines.append("      " + "".join(l.rjust(col_w) for l in labels))
        if fwd_eps:
            vals = [f"{e['avg']:.2f}" if e.get("avg") else "n/a" for e in fwd_eps]
            lines.append("EPS   " + "".join(v.rjust(col_w) for v in vals))
            growth = [f"{e['growth_pct']:+.0f}%" if e.get("growth_pct") is not None else "n/a" for e in fwd_eps]
            lines.append(" YoY  " + "".join(v.rjust(col_w) for v in growth))
        if fwd_rev:
            vals = [f"{r['avg']:.0f}M" if r.get("avg") else "n/a" for r in fwd_rev]
            lines.append("Rev   " + "".join(v.rjust(col_w) for v in vals))
            growth = [f"{r['growth_pct']:+.0f}%" if r.get("growth_pct") is not None else "n/a" for r in fwd_rev]
            lines.append(" YoY  " + "".join(v.rjust(col_w) for v in growth))
        lines.append("```")

    return "\n".join(lines)


# ── Nightly flag cache ────────────────────────────────────────────────────────


async def compute_fundamental_flags(
    tickers: list[str],
    flag_date: date,
    concurrency: int = 5,
) -> list[dict]:
    """
    Compute lightweight fundamental flags for a list of tickers.
    Called during nightly data pull. Returns list of dicts ready for DB upsert.

    Flags per ticker:
    - eps_yoy_latest: latest quarter YoY EPS growth %
    - eps_yoy_prior: prior quarter YoY EPS growth % (for acceleration calc)
    - eps_accelerating: True if latest > prior (O'Neil acceleration)
    - eps_streak_25pct: consecutive quarters with ≥25% YoY EPS growth
    - sales_yoy_latest: latest quarter YoY revenue growth %
    - next_earnings_date: next earnings report date (if known)
    """
    fundamentals = await get_fundamentals_batch(tickers, concurrency=concurrency)

    records = []
    for ticker, data in fundamentals.items():
        if "error" in data:
            continue

        flags = data.get("quality_flags", {})
        q_eps = data.get("quarterly_eps", [])
        q_rev = data.get("quarterly_revenue", [])

        # Extract YoY growth rates for the last two quarters
        eps_yoy = [q["yoy_pct"] for q in q_eps if q.get("yoy_pct") is not None]
        rev_yoy = [q["yoy_pct"] for q in q_rev if q.get("yoy_pct") is not None]

        # Parse next earnings date
        next_ed = None
        raw_ed = data.get("next_earnings_date")
        if raw_ed:
            try:
                next_ed = date.fromisoformat(str(raw_ed))
            except (ValueError, TypeError):
                pass

        records.append({
            "ticker": ticker,
            "flag_date": flag_date,
            "eps_yoy_latest": eps_yoy[-1] if eps_yoy else None,
            "eps_yoy_prior": eps_yoy[-2] if len(eps_yoy) >= 2 else None,
            "eps_accelerating": flags.get("eps_accelerating"),
            "eps_streak_25pct": flags.get("eps_streak_25pct", 0),
            "sales_yoy_latest": rev_yoy[-1] if rev_yoy else None,
            "next_earnings_date": next_ed,
        })

    return records
