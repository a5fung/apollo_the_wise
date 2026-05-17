"""EP Selectivity Phase 1 — Block C — Fundamentals fetcher.

Pulls 8 quarters of structured financial data per ticker for the
6-axis catalyst rubric (see `analysis/2026-05-16/catalyst_rubric_design.md`).

Sources:
  - Polygon `/vX/reference/financials` (primary)
  - yfinance quarterly_financials (fallback)

Output:
  analysis/2026-05-16/fundamentals/{TICKER}.json — per-ticker
  structured 8-quarter financials including:
    - quarterly revenue, EPS, gross/operating/net margins
    - YoY + QoQ deltas and accelerations
    - data source per row (polygon vs yfinance)
    - coverage flags (which axes are populated)

Sample composition (locked):
  - 6 fixtures: NBIS, CSCO, KLAR, TRT, ONDS, CPA
  - 44 stratified across HIGH-win, HIGH-loss, MODERATE-win,
    MODERATE-loss, SKIPPED-winner, SKIPPED-loser

Run on prod:
  docker exec apollo-market python -m scripts.fetch_ep_fundamentals
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import random
from pathlib import Path
from typing import Optional

from agents.market_intelligence.collector import _polygon_get

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("analysis/2026-05-16")
OUT_DIR = DATA_DIR / "fundamentals"
ALERTS_CSV = DATA_DIR / "ep_cohort_alerts_60d.csv"

FIXTURES = ["NBIS", "CSCO", "KLAR", "TRT", "ONDS", "CPA"]
SAMPLE_SIZE = 50  # 6 fixtures + 44 stratified

# Polygon /vX/reference/financials field paths.
# financials.income_statement.<field>.value lives under each report.
INCOME_PATHS = {
    "revenue": "revenues",
    "gross_profit": "gross_profit",
    "operating_income": "operating_income_loss",
    "net_income": "net_income_loss",
    "eps_basic": "basic_earnings_per_share",
    "eps_diluted": "diluted_earnings_per_share",
}


async def fetch_polygon_quarterlies(ticker: str, limit: int = 8) -> list[dict]:
    """Pull last `limit` quarterly reports from Polygon.

    Fix 2026-05-17 (VSNT/ARX/HUT class bug):
    - Polygon's `sort=filing_date` interleaves late-filed quarters with
      current ones (HUT had Q4 2025 at index 7 instead of in
      chronological position). We re-sort by `end_date` DESC after fetch.
    - Polygon sometimes returns the same `(fiscal_year, fiscal_period)`
      twice via multiple filings (amended reports). Dedup keeping the
      most recently-filed copy per fiscal-quarter tuple.
    - Use `(fiscal_year, fiscal_period)` as the dedup key — NOT
      `end_date`. 52/53-week fiscal-year companies shift end_date by
      a few days across years (per Gemini 2026-05-17), causing same-
      quarter rows to appear distinct under end_date keying.
    """
    try:
        # Fetch MORE than requested so we have headroom after dedup
        data = await _polygon_get(
            "/vX/reference/financials",
            {
                "ticker": ticker,
                "timeframe": "quarterly",
                "limit": limit + 4,  # dedup margin
                "sort": "filing_date",
                "order": "desc",
            },
        )
        results = data.get("results", []) or []

        # Dedup by (fiscal_year, fiscal_period), keeping most-recently-filed
        # (input is sorted by filing_date DESC, so first occurrence wins)
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for r in results:
            key = (r.get("fiscal_year"), r.get("fiscal_period"))
            if key in seen or key == (None, None):
                continue
            seen.add(key)
            deduped.append(r)

        # Re-sort by end_date DESC (chronological newest-first), so
        # downstream index-based reads (margins q0/q1/q2) are aligned.
        # Fall back to filing_date when end_date is missing.
        def _sort_key(r):
            ed = r.get("end_date") or ""
            fd = r.get("filing_date") or ""
            return (ed, fd)
        deduped.sort(key=_sort_key, reverse=True)

        # Trim to requested limit
        return deduped[:limit]
    except Exception as e:
        logger.warning("polygon financials failed for %s: %s", ticker, e)
        return []


def extract_polygon_quarter(report: dict) -> dict:
    """Pull the fields we care about from one quarterly report dict."""
    out = {
        "source": "polygon",
        "fiscal_period": report.get("fiscal_period"),
        "fiscal_year": report.get("fiscal_year"),
        "end_date": report.get("end_date"),
        "filing_date": report.get("filing_date"),
    }
    fin = report.get("financials", {}) or {}
    income = fin.get("income_statement", {}) or {}
    for our_field, poly_field in INCOME_PATHS.items():
        node = income.get(poly_field)
        if isinstance(node, dict):
            out[our_field] = node.get("value")
        else:
            out[our_field] = None
    # Margins computed from absolute values
    rev = out.get("revenue")
    if rev and rev > 0:
        if out.get("gross_profit") is not None:
            out["gross_margin"] = out["gross_profit"] / rev
        if out.get("operating_income") is not None:
            out["op_margin"] = out["operating_income"] / rev
        if out.get("net_income") is not None:
            out["net_margin"] = out["net_income"] / rev
    return out


async def fetch_yfinance_quarterlies(ticker: str) -> list[dict]:
    """yfinance fallback. Returns up to 4 quarters (yfinance limit on
    free tier). Sorted newest first."""
    try:
        # yfinance is sync — wrap in run_in_executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _yf_pull_quarterlies, ticker)
    except Exception as e:
        logger.warning("yfinance failed for %s: %s", ticker, e)
        return []


def _yf_pull_quarterlies(ticker: str) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return []
    t = yf.Ticker(ticker)
    inc = t.quarterly_financials
    if inc is None or inc.empty:
        return []
    # Columns are quarter end dates (Timestamp); rows are line items
    results = []
    for col in inc.columns:
        row = {
            "source": "yfinance",
            "end_date": str(col.date()) if hasattr(col, "date") else str(col),
        }
        # yfinance field names: 'Total Revenue', 'Gross Profit',
        # 'Operating Income', 'Net Income', etc.
        m = {
            "revenue": "Total Revenue",
            "gross_profit": "Gross Profit",
            "operating_income": "Operating Income",
            "net_income": "Net Income",
            "eps_basic": "Basic EPS",
            "eps_diluted": "Diluted EPS",
        }
        for our, yf_name in m.items():
            v = inc.loc[yf_name, col] if yf_name in inc.index else None
            row[our] = float(v) if v is not None and not _is_nan(v) else None
        # Compute margins
        rev = row.get("revenue")
        if rev and rev > 0:
            for tier in ["gross_profit", "operating_income", "net_income"]:
                if row.get(tier) is not None:
                    mname = {"gross_profit": "gross_margin",
                             "operating_income": "op_margin",
                             "net_income": "net_margin"}[tier]
                    row[mname] = row[tier] / rev
        results.append(row)
    return results


def _is_nan(v) -> bool:
    try:
        return v != v  # NaN trick
    except Exception:
        return False


def compute_growth_deltas(quarters: list[dict]) -> dict:
    """Given quarters list (newest first, len ≥ 5 ideally), compute
    Y/Y growth + acceleration deltas + Q/Q sequentials + 8-quarter
    history for milestone detection.

    Fix 2026-05-17 (VSNT-class bug): Y/Y lookup uses
    `(fiscal_year, fiscal_period)` matching, NOT index `[i+4]`. The
    old approach broke when fetched quarters had gaps (missing
    filings, restatements, or interleaved late-filings). Now we
    explicitly find the prior-year same-fiscal-period quarter.
    Falls back to index-based ONLY when fiscal attributes missing.
    """
    out = {
        "rev_yoy_q0": None, "rev_yoy_q1": None, "rev_yoy_q2": None,
        "rev_yoy_q3": None,
        "eps_yoy_q0": None, "eps_yoy_q1": None, "eps_yoy_q2": None,
        "rev_qoq_q0": None,
        "rev_accel": None, "rev_accel_streak": 0,
        "eps_accel": None,
        "rev_yoy_max_prior_7q": None,
        "eps_qm4": None,  # for small-base guardrail
        "margins_q0": {}, "margins_q1": {}, "margins_q2": {},
        "data_quality_flag": None,  # populated when fiscal lookup misses
    }
    if len(quarters) < 2:
        return out

    def _fy(q):
        v = q.get("fiscal_year")
        try:
            return int(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    def _fp(q):
        return q.get("fiscal_period")

    def _eps(q):
        return q.get("eps_diluted") or q.get("eps_basic")

    def _find_prior_year(idx: int) -> dict | None:
        """Find the quarter at fiscal_year=cur-1, fiscal_period=cur.
        Returns None if not present (caller treats as missing data)."""
        if idx >= len(quarters):
            return None
        cur = quarters[idx]
        cur_fy = _fy(cur)
        cur_fp = _fp(cur)
        if cur_fy is None or cur_fp is None:
            # No fiscal attributes — graceful fallback to index-based
            # ONLY for yfinance rows. Polygon rows always have fiscal
            # attributes; yfinance lacks them and is structurally
            # ordered by end_date already.
            fallback_idx = idx + 4
            if fallback_idx < len(quarters):
                out["data_quality_flag"] = "fiscal_attrs_missing_fallback_index"
                return quarters[fallback_idx]
            return None
        for q in quarters:
            if _fy(q) == cur_fy - 1 and _fp(q) == cur_fp:
                return q
        return None  # genuinely missing prior-year quarter

    def _yoy_rev(idx: int) -> float | None:
        if idx >= len(quarters):
            return None
        cur = quarters[idx].get("revenue")
        prior_q = _find_prior_year(idx)
        prior = prior_q.get("revenue") if prior_q else None
        if cur is not None and prior and prior > 0:
            return cur / prior - 1
        return None

    def _yoy_eps(idx: int) -> float | None:
        if idx >= len(quarters):
            return None
        cur = _eps(quarters[idx])
        prior_q = _find_prior_year(idx)
        prior = _eps(prior_q) if prior_q else None
        if cur is not None and prior is not None and abs(prior) > 0.001:
            return cur / prior - 1
        return None

    out["rev_yoy_q0"] = _yoy_rev(0)
    out["rev_yoy_q1"] = _yoy_rev(1)
    out["rev_yoy_q2"] = _yoy_rev(2)
    out["rev_yoy_q3"] = _yoy_rev(3)
    out["eps_yoy_q0"] = _yoy_eps(0)
    out["eps_yoy_q1"] = _yoy_eps(1)
    out["eps_yoy_q2"] = _yoy_eps(2)

    # eps_qm4 (small-base guard) — find prior-year q0
    prior_q0 = _find_prior_year(0)
    if prior_q0:
        out["eps_qm4"] = _eps(prior_q0)

    # Q/Q sequential: q0 vs q1 (assumes sequential after sort+dedup)
    if len(quarters) >= 2:
        cur_rev = quarters[0].get("revenue")
        prev_rev = quarters[1].get("revenue")
        if cur_rev is not None and prev_rev and prev_rev > 0:
            out["rev_qoq_q0"] = cur_rev / prev_rev - 1

    if out["rev_yoy_q0"] is not None and out["rev_yoy_q1"] is not None:
        out["rev_accel"] = out["rev_yoy_q0"] - out["rev_yoy_q1"]
    if out["eps_yoy_q0"] is not None and out["eps_yoy_q1"] is not None:
        out["eps_accel"] = out["eps_yoy_q0"] - out["eps_yoy_q1"]

    # acceleration streak (consecutive quarters of positive Y/Y delta)
    streak = 0
    for i in range(0, min(4, len(quarters) - 1)):
        cur_y = _yoy_rev(i)
        prior_y = _yoy_rev(i + 1)
        if cur_y is None or prior_y is None:
            break
        if cur_y - prior_y > 0:
            streak += 1
        else:
            break
    out["rev_accel_streak"] = streak

    # max Y/Y over prior 7 quarters (for milestone "beat prior max by ≥5pp")
    prior_7 = [_yoy_rev(i) for i in range(1, min(8, len(quarters)))]
    prior_7 = [v for v in prior_7 if v is not None]
    out["rev_yoy_max_prior_7q"] = max(prior_7) if prior_7 else None

    # Margins for q0, q1, q2
    for q, key in [(0, "margins_q0"), (1, "margins_q1"), (2, "margins_q2")]:
        if q < len(quarters):
            out[key] = {
                "gross_margin": quarters[q].get("gross_margin"),
                "op_margin": quarters[q].get("op_margin"),
                "net_margin": quarters[q].get("net_margin"),
            }
    return out


async def fetch_one(ticker: str) -> dict:
    """Pull Polygon → fallback yfinance if Polygon < 5 quarters."""
    poly_quarters = await fetch_polygon_quarterlies(ticker, limit=8)
    quarters_normalized = [extract_polygon_quarter(r) for r in poly_quarters]
    source_chain = ["polygon"]
    if len([q for q in quarters_normalized if q.get("revenue")]) < 5:
        # Polygon coverage too thin; supplement with yfinance
        yf_quarters = await fetch_yfinance_quarterlies(ticker)
        # Use yfinance ONLY if it's better than what polygon gave
        if len([q for q in yf_quarters if q.get("revenue")]) > \
                len([q for q in quarters_normalized if q.get("revenue")]):
            quarters_normalized = yf_quarters
            source_chain = ["yfinance"]
        else:
            source_chain.append("yfinance_attempted_no_improvement")
    deltas = compute_growth_deltas(quarters_normalized)
    return {
        "ticker": ticker,
        "source_chain": source_chain,
        "n_quarters": len(quarters_normalized),
        "n_quarters_with_revenue": len(
            [q for q in quarters_normalized if q.get("revenue")]
        ),
        "quarters": quarters_normalized,
        "deltas": deltas,
    }


def build_sample(alerts_rows: list[dict]) -> list[str]:
    """Sample composition: 6 fixtures + stratified 44 across cohort
    score-tier × outcome quadrants."""
    tickers_in_cohort = list({r["ticker"] for r in alerts_rows})
    selected = list(FIXTURES)
    pool = [t for t in tickers_in_cohort if t not in selected]
    # naive stratification — just shuffle and take 44 unique
    random.seed(42)
    random.shuffle(pool)
    selected.extend(pool[: SAMPLE_SIZE - len(FIXTURES)])
    return selected


def build_full_labeled_set() -> list[str]:
    """Full coverage: every ticker in catalyst_labels.csv that has a
    user_label populated. Used for the post-label cross-tab pass."""
    labels_csv = DATA_DIR / "catalyst_labels.csv"
    if not labels_csv.exists():
        return []
    with labels_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return sorted({
        r["ticker"] for r in rows
        if r.get("user_label", "").strip()
    })


async def main(mode: str = "sample") -> None:
    """mode = 'sample' (50-ticker stratified) or 'labeled' (all
    user-labeled tickers from catalyst_labels.csv)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with ALERTS_CSV.open("r", encoding="utf-8") as f:
        alerts = list(csv.DictReader(f))

    if mode == "labeled":
        sample = build_full_labeled_set()
    else:
        sample = build_sample(alerts)
    logger.info("mode=%s fetching fundamentals for %d tickers: %s",
                mode, len(sample), sample[:10])

    completed = 0
    for ticker in sample:
        out_path = OUT_DIR / f"{ticker}.json"
        if out_path.exists():
            completed += 1
            continue
        try:
            result = await fetch_one(ticker)
            out_path.write_text(json.dumps(result, indent=2, default=str))
            completed += 1
            logger.info("[%d/%d] %s: %d quarters (source=%s)",
                        completed, len(sample), ticker,
                        result["n_quarters_with_revenue"],
                        ",".join(result["source_chain"]))
        except Exception as e:
            logger.warning("fetch failed for %s: %s", ticker, e)

    logger.info("complete. %d/%d tickers in %s", completed, len(sample), OUT_DIR)


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
    asyncio.run(main(mode))
