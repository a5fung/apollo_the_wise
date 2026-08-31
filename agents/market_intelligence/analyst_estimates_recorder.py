"""2026-08-31 — #333 ANALYST-ESTIMATES RECORDER (the sourcing backbone's 60-day clock).

Pradeep's durability test is FORWARD: ~2 quarters realized PLUS ~4 quarters projected of
high revenue growth. The rubric can only score the trailing leg because we have never
stored a single analyst estimate — #333's build gate is this backbone plus >=60 days of
stored estimates, and the clock starts when this module's first snapshot lands.

THE LINE — read before touching anything here. DATA CAPTURE ONLY:
  - Writes EXACTLY ONE table: `mi_analyst_estimates` (+ `mi_audit_log` via the shared
    `log_audit_event` telemetry helper — never a trade-state table).
  - No rubric axis, no scoring change, no admission change lives here. The #333 axis
    itself needs operator sign-off + CHANGE_PROCESS long after this capture.
  - Read by NO grading / entry / sizing / ordering / safeguard path.
  - Never touches the 09:45 ET scan path — this is an EOD scheduled job (18:05 ET).
  - SILENT: no Telegram on any path. Errors degrade to mi_audit_log + logs; the
    detector-liveness registry (health_checks._DETECTOR_LIVENESS_TABLES,
    mi_analyst_estimates) is the watchdog for a silently-dead writer.

THE HONESTY CONSTRAINT (this decided the whole design). Estimates are point-in-time:
what FMP returns today for a future period is TODAY'S consensus — stamping it onto a
past alert date is lookahead, the defect class that invalidated the 08-25 structure
study. But there is a genuine, bounded backfill (operator-identified): an estimate for a
future period persists until that period's results land, so today's read IS the estimate
that stood on any date since THAT TICKER'S most recent filing. Hence every row stores:
  as_of_date         the date the value was READ (never inferred by a future reader)
  anchor_filing_date the ticker's most recent income-statement filingDate at read time
  valid_from_date    = anchor_filing_date (or as_of_date when no anchor resolves —
                       NEVER claim history without an anchor; CHECK-enforced)
The backfill window is PER TICKER, back to its own last filing — never a flat lookback.
Measured on the real alert population (2026-08-31, SEC EDGAR filing dates, 306/335
alert tickers resolved): mean reach 28 days, median 25 — BELOW the ~45-day estimate,
because the measurement ran just past earnings season; the reach is cyclical and grows
toward ~45+ mid-cycle. `docs/analysis/analyst_estimates_backfill_reach_2026-08-31.md`.

RAW VALUES, NEVER A COMPUTED SCORE: thresholds belong to today's rule set; a stored
score goes stale the moment one is swept. The sketch's n_analysts<3 -> None rule is
applied READ-SIDE (`estimate_for_scoring`, threshold parameterized) and the count is
stored, so the rule can be re-tuned without re-fetching.

ENDPOINTS (FMP /stable/, the subscription we already pay for — collector._fmp_get is
the canonical transport):
  /analyst-estimates?symbol=X&period=annual   verified in-plan (2026-08-31)
  /analyst-estimates?symbol=X&period=quarter  NOT yet verified — degrade gracefully:
                                              a 402 records annual only + audit note
  /income-statement?symbol=X&period=quarter   verified in-plan; filingDate = the anchor
  /earnings                                   402 on our plan — the filing date IS the
                                              anchor, never this endpoint
COST: fixed subscription — call budget only. ~3 calls per ticker per run; the daily
population (live-source EP alerts, trailing 30 days) is ~100 tickers => ~300 calls/day,
paced under FMP's 300/min limit. The one-shot backfill over the full alert population
(~335 tickers) is ~1,000 calls, once.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Optional

from agents.market_intelligence.db import (
    get_analyst_estimate_population,
    log_audit_event,
    upsert_analyst_estimates,
)

logger = logging.getLogger(__name__)

RECORDER_VERSION = "v1"
ESTIMATES_SOURCE = "fmp_stable"
POPULATION_LOOKBACK_DAYS = 30     # daily run: tickers with a live-source alert this recent
MIN_ANALYSTS_DEFAULT = 3          # the sketch's n<3 -> None rule (read-side, re-tunable)
MAX_PERIODS_PER_CALL = 20         # bound the per-ticker estimate payload
FMP_PACE_SECONDS = 0.25           # courtesy pacing, ~240 calls/min worst case


# ── pure core (mock-free, the house idiom) ────────────────────────────────────────────

def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[date]:
    """ISO date string (or date) -> date; anything unparseable -> None, never a guess."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def honest_valid_from(anchor_filing_date: Optional[date], as_of: date) -> date:
    """The earliest date a value read on `as_of` can honestly be said to have stood.

    GUARD (mutation-tested): no anchor -> as_of (a row may NEVER claim history without
    a resolved filing date — ETFs/non-filers buy zero days, by design). An anchor in
    the future of the read (a bad API date) is clamped to as_of the same way.
    """
    if anchor_filing_date is None or anchor_filing_date > as_of:
        return as_of
    return anchor_filing_date


def normalize_fmp_estimate(
    rec: dict, *, ticker: str, period_type: str, as_of: date,
    anchor_filing_date: Optional[date],
) -> Optional[dict]:
    """One FMP /stable/analyst-estimates record -> one mi_analyst_estimates row.

    Raw field capture only — no derived numbers. Returns None when the record has no
    parseable period date (a row that is FOR no period is meaningless). Missing value
    fields store as NULL, never 0 — zero is a claim, NULL is an absence.
    """
    period_end = _d(rec.get("date"))
    if period_end is None:
        return None
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "anchor_filing_date": anchor_filing_date,
        "valid_from_date": honest_valid_from(anchor_filing_date, as_of),
        "period_type": period_type,
        "period_end_date": period_end,
        "revenue_avg": _f(rec.get("revenueAvg")),
        "revenue_high": _f(rec.get("revenueHigh")),
        "revenue_low": _f(rec.get("revenueLow")),
        "eps_avg": _f(rec.get("epsAvg")),
        "eps_high": _f(rec.get("epsHigh")),
        "eps_low": _f(rec.get("epsLow")),
        "num_analysts_revenue": _i(rec.get("numAnalystsRevenue")),
        "num_analysts_eps": _i(rec.get("numAnalystsEps")),
        "source": ESTIMATES_SOURCE,
        "recorder_version": RECORDER_VERSION,
    }


def estimate_for_scoring(
    row: dict, min_analysts: int = MIN_ANALYSTS_DEFAULT
) -> Optional[dict]:
    """READ-SIDE neglect rule (the sketch's contract, mutation-tested): a thin-coverage
    estimate scores None — the missing-data scaling absorbs it; never penalize the
    un-covered. The count is STORED on every row so this threshold can be re-tuned
    without re-fetching. An unknown count is thin by definition (None, not 0 analysts,
    but either way not >= min_analysts).

    THE LINE: no live path calls this today — it exists so the future #333 axis has ONE
    sanctioned accessor instead of re-deriving the rule per caller.
    """
    n = row.get("num_analysts_revenue")
    if n is None or n < min_analysts:
        return None
    return row


# ── FMP fetch (collector._fmp_get is the canonical transport) ─────────────────────────

async def _fetch_last_filing_date(ticker: str) -> Optional[date]:
    """The ticker's most recent income-statement filingDate — the honest-window anchor.
    /earnings is 402 on our plan; the filing date is the anchor BY DESIGN (it is the
    conservative bound: the 10-Q lands at or after the results release, so anchoring on
    it claims FEWER days, never more)."""
    from agents.market_intelligence.collector import _fmp_get
    reports = await _fmp_get("/income-statement",
                             {"symbol": ticker, "period": "quarter", "limit": 1})
    if not isinstance(reports, list) or not reports:
        return None
    return _d(reports[0].get("filingDate"))


async def _fetch_estimates(ticker: str, period: str) -> list[dict]:
    from agents.market_intelligence.collector import _fmp_get
    out = await _fmp_get("/analyst-estimates",
                         {"symbol": ticker, "period": period,
                          "page": 0, "limit": MAX_PERIODS_PER_CALL})
    return out if isinstance(out, list) else []


def _is_payment_required(exc: Exception) -> bool:
    """True for FMP's 402 (endpoint not in plan) — the degrade-not-die case."""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 402


async def snapshot_ticker(ticker: str, as_of: date) -> dict[str, Any]:
    """Fetch + normalize one ticker's estimates. Returns
    {rows, quarter_unavailable, anchor} — raises only on a hard fetch failure the
    caller counts (per-ticker isolation lives in the run loop, not here)."""
    anchor = await _fetch_last_filing_date(ticker)
    await asyncio.sleep(FMP_PACE_SECONDS)
    rows: list[dict] = []
    quarter_unavailable = False
    for period in ("annual", "quarter"):
        try:
            recs = await _fetch_estimates(ticker, period)
        except Exception as e:
            if period == "quarter" and _is_payment_required(e):
                # /analyst-estimates?period=quarter is unverified on our plan — a 402
                # here degrades to annual-only capture, it never kills the snapshot.
                quarter_unavailable = True
                break
            raise
        for rec in recs:
            row = normalize_fmp_estimate(
                rec, ticker=ticker, period_type=period, as_of=as_of,
                anchor_filing_date=anchor,
            )
            if row is not None:
                rows.append(row)
        await asyncio.sleep(FMP_PACE_SECONDS)
    return {"rows": rows, "quarter_unavailable": quarter_unavailable, "anchor": anchor}


# ── run functions (never raise into the scheduler — the house shadow contract) ────────

async def _run_over_tickers(tickers: list[str], as_of: date, label: str) -> dict[str, Any]:
    out = {"population": len(tickers), "tickers_written": 0, "rows_written": 0,
           "no_anchor": 0, "quarter_unavailable": 0, "errors": 0}
    for ticker in tickers:
        try:
            snap = await snapshot_ticker(ticker, as_of)
            written = await upsert_analyst_estimates(snap["rows"])
            out["rows_written"] += written
            if written:
                out["tickers_written"] += 1
            if snap["anchor"] is None:
                out["no_anchor"] += 1
            if snap["quarter_unavailable"]:
                out["quarter_unavailable"] += 1
        except Exception as e:  # per-ticker isolation: one bad name never kills the run
            out["errors"] += 1
            logger.warning(f"{label}: {ticker} failed: {type(e).__name__}: {e}")
            try:
                await log_audit_event(
                    "analyst_estimates_error",
                    f"{label}: {ticker}: {type(e).__name__}: {e}"[:400],
                )
            except Exception:  # loud-ok: logger.warning above already fired
                pass
    return out


async def run_analyst_estimates_snapshot(
    today: date, tickers: "list[str] | None" = None
) -> dict[str, Any]:
    """The daily 18:05 ET snapshot. Population: live-source EP-alert tickers from the
    trailing POPULATION_LOOKBACK_DAYS — today's alerts get their estimates recorded
    the same evening (honest as-of the alert day: as_of_date is the read date, never
    back-stamped), and recent-alert names keep accruing a revision series. Never
    raises; SILENT (no Telegram on any path)."""
    try:
        if tickers is None:
            from datetime import timedelta
            since = today - timedelta(days=POPULATION_LOOKBACK_DAYS)
            tickers = await get_analyst_estimate_population(since)
        out = await _run_over_tickers(tickers, today, "analyst_estimates_snapshot")
        try:
            await log_audit_event(
                "analyst_estimates_snapshot",
                f"{out['rows_written']} row(s) across {out['tickers_written']}/"
                f"{out['population']} ticker(s); {out['no_anchor']} no-anchor, "
                f"{out['quarter_unavailable']} quarter-unavailable, "
                f"{out['errors']} error(s)",
            )
        except Exception:  # loud-ok: counters already logged by the scheduler wrapper
            pass
        return out
    except Exception as e:  # never raises into the scheduler
        logger.error(f"analyst_estimates_snapshot failed: {e}", exc_info=True)
        return {"population": 0, "tickers_written": 0, "rows_written": 0,
                "no_anchor": 0, "quarter_unavailable": 0, "errors": 1}


async def run_analyst_estimates_backfill(today: date) -> dict[str, Any]:
    """The ONE-SHOT bounded backfill (run by hand at deploy, not scheduled): a snapshot
    over the FULL live-source alert population, all history. The per-ticker honest
    window [anchor_filing_date, as_of_date] is baked into every row — the backfill IS
    a snapshot with a wider population; the valid-from semantics do the rest. A ticker
    that reported last week buys days; one with no resolvable filing buys ZERO, by
    design. ~1,000 calls once (~335 tickers x 3). Never raises."""
    try:
        tickers = await get_analyst_estimate_population(date(2000, 1, 1))
        out = await _run_over_tickers(tickers, today, "analyst_estimates_backfill")
        try:
            await log_audit_event(
                "analyst_estimates_backfill",
                f"one-shot backfill: {out['rows_written']} row(s) across "
                f"{out['tickers_written']}/{out['population']} ticker(s); "
                f"{out['no_anchor']} no-anchor (zero honest days, by design), "
                f"{out['quarter_unavailable']} quarter-unavailable, "
                f"{out['errors']} error(s)",
            )
        except Exception:  # loud-ok
            pass
        return out
    except Exception as e:
        logger.error(f"analyst_estimates_backfill failed: {e}", exc_info=True)
        return {"population": 0, "tickers_written": 0, "rows_written": 0,
                "no_anchor": 0, "quarter_unavailable": 0, "errors": 1}
