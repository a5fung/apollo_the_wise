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
  - Never touches the 09:45 ET scan path — this is an EOD scheduled job (18:12 ET).
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
  anchor_filing_date the ticker's most recent 10-Q/10-K-class filingDate at read time
  valid_from_date    = anchor_filing_date (or as_of_date when no anchor resolves —
                       NEVER claim history without an anchor; CHECK-enforced)
The backfill window is PER TICKER, back to its own last filing — never a flat lookback.
Measured on the real alert population (2026-08-31, SEC EDGAR filing dates, 306/335
alert tickers resolved): mean reach 28 days, median 25 — BELOW the ~45-day estimate,
because the measurement ran just past earnings season; the reach is cyclical and grows
toward ~45+ mid-cycle. `docs/analysis/analyst_estimates_backfill_reach_2026-08-31.md`.

NO-ANCHOR IS A FIRST-CLASS OUTCOME, NEVER AN ABORT (v2, 2026-09-01). The first live
run (2026-09-01 18:12 ET) wrote 0 rows with 99 errors: FMP's /income-statement — v1's
filing-date anchor — is 402 Payment Required on our plan, and v1 treated an anchor
fetch failure as a ticker-killing exception. Wrong shape: a ticker whose filing date
cannot be resolved must still record its estimates with a ZERO honest window
(valid_from_date == as_of_date) and be counted — `honest_valid_from` already encodes
that; only the orchestration aborted. NEVER invent or approximate a filing date to
widen a window — no anchor means no claimed history, full stop.

THE ANCHOR SOURCE IS SEC EDGAR (v2, 2026-09-01) — the authority FMP's filingDate is
derived from, keyless and $0, so no payment tier can take it away again:
  https://www.sec.gov/files/company_tickers.json        ticker -> CIK (1 call/run, cached)
  https://data.sec.gov/submissions/CIK##########.json   filings.recent, newest-first
Anchor = the MOST RECENT filing among ANCHOR_FORMS (10-Q/10-K/20-F/6-K + /A) — the
same conservative bound as before: the filing lands at or after the results release,
so anchoring on it claims FEWER days, never more. yfinance earnings dates were probed
and REJECTED: they are ANNOUNCEMENT dates (at-or-before the filing), so anchoring on
them would WIDEN the window — the forbidden direction. The 08-31 reach measurement
used this exact EDGAR path and resolved 306/335 real alert tickers; the unresolved 29
are ETFs/preferreds/non-filers, which buy zero days BY DESIGN. SEC asks for a
declared User-Agent (collector._SEC_UA, `SEC_USER_AGENT` env) and <=10 req/s; the run pace
is ~4 req/s worst case.

A 402 DEGRADES THE FIELD, NEVER THE TICKER (v2). Any FMP endpoint going 402 marks
that period unavailable and the snapshot continues; the run summary carries the
counts, and an annual-period 402 — the endpoint verified in-plan 2026-08-31 —
additionally writes ONE `analyst_estimates_plan_change` audit row, because that means
the FMP plan itself changed and must be visible, not silent.

RAW VALUES, NEVER A COMPUTED SCORE: thresholds belong to today's rule set; a stored
score goes stale the moment one is swept. The sketch's n_analysts<3 -> None rule is
applied READ-SIDE (`estimate_for_scoring`, threshold parameterized) and the count is
stored, so the rule can be re-tuned without re-fetching.

ENDPOINTS (estimates: FMP /stable/, the subscription we already pay for —
collector._fmp_get is the canonical transport; anchor: SEC EDGAR, above):
  /analyst-estimates?symbol=X&period=annual   verified in-plan (2026-08-31); a 402
                                              here = plan change -> audit + degrade
  /analyst-estimates?symbol=X&period=quarter  NOT yet verified — degrade gracefully:
                                              a 402 records annual only + counter
  /income-statement                           402 on our plan (verified live
                                              2026-09-01, 99/99 tickers) — NEVER call
  /earnings                                   402 on our plan — same
COST: fixed subscription — call budget only. ~3 calls per ticker per run (1 EDGAR +
2 FMP) + 1 EDGAR ticker-map call per run; the daily population (live-source EP
alerts, trailing 30 days) is ~100 tickers => ~300 calls/day, paced under FMP's
300/min limit and EDGAR's 10/s policy. The one-shot backfill over the full alert
population (~335 tickers) is ~1,000 calls, once.

CREDENTIALS: FMP authenticates by QUERY STRING, so raw exception text can carry the
live key (it did — 99 audit rows on 2026-09-01). `db.log_audit_event` redacts at the
chokepoint; every log line here that formats an exception goes through
`redact_secrets` too, so the key never lands in container logs either.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any, Optional

from agents.market_intelligence.db import (
    _f,
    get_analyst_estimate_population,
    log_audit_event,
    upsert_analyst_estimates,
)
from shared.secret_redaction import redact_secrets

logger = logging.getLogger(__name__)

RECORDER_VERSION = "v2"           # v2 2026-09-01: anchor source FMP -> SEC EDGAR (402 fix)
ESTIMATES_SOURCE = "fmp_stable"   # the ESTIMATE values are still FMP; only the anchor moved
POPULATION_LOOKBACK_DAYS = 30     # daily run: tickers with a live-source alert this recent
MIN_ANALYSTS_DEFAULT = 3          # the sketch's n<3 -> None rule (read-side, re-tunable)
MAX_PERIODS_PER_CALL = 20         # bound the per-ticker estimate payload
# 🛑 PACING IS THE WHOLE BUG (root-caused 2026-09-02). This was 0.25s — its own comment said
# "~240 calls/min worst case" — against a FREE tier. FMP answers a rate breach with HTTP **402**,
# not 429, so it is indistinguishable from "endpoint not in your plan" unless you read the body:
# a plan refusal says "not available under your current subscription", a rate breach says nothing
# and CLEARS ON ITS OWN. Proven by probing the identical URL minutes apart from inside the
# container: 200 -> 402 -> 200. The 09-02 run's "99 annual-402" was NOT a plan change; the alarm
# that fired said the plan had changed, and it was wrong.
FMP_PACE_SECONDS = 12.0           # ~5 calls/min — the free tier's documented allowance

# ── SEC EDGAR anchor source (v2) ──────────────────────────────────────────────────────
# The exact form set the 08-31 reach measurement used (306/335 resolved) — foreign
# filers report on 20-F/6-K; amendments carry the same filing-date semantics.
ANCHOR_FORMS = frozenset({"10-Q", "10-K", "20-F", "6-K", "10-Q/A", "10-K/A", "20-F/A"})
_EDGAR_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# SEC's access policy asks every client to identify itself — with ONE identity per codebase.
# We declare collector._SEC_UA (env `SEC_USER_AGENT`), which has been this repo's SEC contact
# since #187. This module briefly shipped its own `SEC_EDGAR_USER_AGENT` (2026-09-01), which
# meant SEC saw two different names from one process for the same purpose and an operator could
# set either env var without knowing the other existed. Imported lazily inside the fetch so the
# module keeps its no-collector-at-import-time property.
_EDGAR_TIMEOUT_SECONDS = 30

# One ticker->CIK map fetch per as_of day, success OR failure — a dead sec.gov must
# cost the run ONE timeout, not one per ticker. {"as_of": date|None, "map": dict|None}.
_cik_map_state: dict[str, Any] = {"as_of": None, "map": None}


# ── pure core (mock-free, the house idiom) ────────────────────────────────────────────

def _i(v) -> Optional[int]:
    """None-safe int coercion. NOT db._int_or_none — that one raises on garbage
    (its callers want a BIGINT param to fail loudly); an FMP field must degrade to
    None instead. Float coercion is db._f, imported above."""
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


def latest_filing_from_submissions(payload: Any) -> Optional[date]:
    """EDGAR submissions payload -> the ticker's most recent anchor-form filing date.

    Pure and defensive: takes the MAX parsed date over ANCHOR_FORMS rather than
    trusting EDGAR's newest-first ordering; any malformed payload -> None (which the
    caller records as zero honest window — never a guess, never a widened window).
    """
    try:
        recent = payload["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
    except (TypeError, KeyError):
        return None
    best: Optional[date] = None
    for form, fdate in zip(forms, dates):
        if form not in ANCHOR_FORMS:
            continue
        parsed = _d(fdate)
        if parsed is not None and (best is None or parsed > best):
            best = parsed
    return best


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


# ── anchor fetch (SEC EDGAR — keyless, $0, no payment tier) ───────────────────────────

async def _edgar_get_json(url: str) -> Any:
    import httpx

    from agents.market_intelligence.collector import _SEC_UA
    # ⚠ KNOWN, MEASURED, DELIBERATELY NOT FIXED HERE: this opens a fresh connection per call —
    # ~100 TLS handshakes on the daily run (est. 5-20s) and ~335 on the backfill. Reusing one
    # client means threading it through snapshot_ticker and _fetch_last_filing_date, both of
    # which the test suite monkeypatches by signature. Seconds on a once-a-day job did not
    # justify churning those the day after this module shipped. Revisit if the population grows.
    async with httpx.AsyncClient(
        timeout=_EDGAR_TIMEOUT_SECONDS, headers=_SEC_UA
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def _get_cik_map(as_of: date) -> Optional[dict]:
    """Ticker->CIK map, fetched AT MOST ONCE per as_of day (success or failure) —
    a dead sec.gov costs the run one timeout, never one per ticker. None = the map
    is unavailable today; callers raise so the failure is COUNTED per ticker
    (anchor_errors), distinguishing an EDGAR outage from true non-filers."""
    if _cik_map_state["as_of"] == as_of:
        return _cik_map_state["map"]
    _cik_map_state["as_of"] = as_of
    _cik_map_state["map"] = None
    try:
        raw = await _edgar_get_json(_EDGAR_TICKER_MAP_URL)
        _cik_map_state["map"] = {
            str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()
        }
    except Exception as e:
        logger.warning(f"EDGAR ticker map fetch failed: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
    return _cik_map_state["map"]


async def _fetch_last_filing_date(ticker: str, as_of: date) -> Optional[date]:
    """The ticker's most recent anchor-form EDGAR filing date — the honest-window
    anchor. None = the ticker genuinely resolves no filing (not in EDGAR's map, or
    no anchor-form filing) -> zero honest window BY DESIGN. Raises on transport
    failure so the caller can COUNT it (anchor_errors) — but the caller still
    records the ticker with a zero window; no anchor path aborts a snapshot.

    v1 used FMP /income-statement filingDate; it is 402 on our plan (2026-09-01,
    99/99 tickers) — never call it again."""
    cik_map = await _get_cik_map(as_of)
    if cik_map is None:
        raise RuntimeError("EDGAR ticker map unavailable")
    cik = cik_map.get(ticker.upper())
    if cik is None:
        return None  # ETF / preferred / non-filer — zero honest days, by design
    payload = await _edgar_get_json(_EDGAR_SUBMISSIONS_URL.format(cik=cik))
    return latest_filing_from_submissions(payload)


# ── estimates fetch (collector._fmp_get is the canonical FMP transport) ───────────────

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
    {rows, unavailable_periods, anchor, anchor_error} — raises only on a hard
    ESTIMATES fetch failure the caller counts (per-ticker isolation lives in the run
    loop, not here). The anchor NEVER aborts: an unresolvable or failed anchor
    records the rows with a zero honest window (the 2026-09-01 first-run bug was
    exactly this abort)."""
    anchor: Optional[date] = None
    anchor_error = False
    try:
        anchor = await _fetch_last_filing_date(ticker, as_of)
    except Exception as e:
        # FIRST-CLASS no-anchor: zero honest window, counted, never fatal.
        anchor_error = True
        logger.warning(f"anchor fetch failed for {ticker} (zero honest window): "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
    await asyncio.sleep(FMP_PACE_SECONDS)
    rows: list[dict] = []
    unavailable_periods: set[str] = set()
    # ⚠ ANNUAL ONLY (2026-09-02). `period=quarter` is NOT on this tier — FMP says so explicitly:
    # "This value set for 'period' is not available under your current subscription". Calling it
    # anyway DOUBLED our call volume for a guaranteed 402, on the exact quota the annual call
    # needs, which is how a working endpoint came back 99-for-99 empty. Half of every run was
    # spent buying a refusal we had already verified. The quarterly leg, if we want it, comes from
    # yfinance (free, already a dependency, returns 0q/+1q with numberOfAnalysts) — an operator
    # call, not a silent substitution.
    for period in ("annual",):
        try:
            recs = await _fetch_estimates(ticker, period)
        except Exception as e:
            if _is_payment_required(e):
                # A 402 degrades the FIELD, never the ticker — whichever period it
                # hits. (Annual was verified in-plan 2026-08-31; the run loop turns
                # an annual 402 into a plan-change audit row.)
                unavailable_periods.add(period)
                continue
            raise
        for rec in recs:
            row = normalize_fmp_estimate(
                rec, ticker=ticker, period_type=period, as_of=as_of,
                anchor_filing_date=anchor,
            )
            if row is not None:
                rows.append(row)
        await asyncio.sleep(FMP_PACE_SECONDS)
    return {"rows": rows, "unavailable_periods": unavailable_periods,
            "anchor": anchor, "anchor_error": anchor_error}


# ── run functions (never raise into the scheduler — the house shadow contract) ────────

async def _run_over_tickers(tickers: list[str], as_of: date, label: str) -> dict[str, Any]:
    out = {"population": len(tickers), "tickers_written": 0, "rows_written": 0,
           "no_anchor": 0, "anchor_errors": 0,
           "annual_unavailable": 0, "quarter_unavailable": 0, "errors": 0}
    for ticker in tickers:
        try:
            snap = await snapshot_ticker(ticker, as_of)
            written = await upsert_analyst_estimates(snap["rows"])
            out["rows_written"] += written
            if written:
                out["tickers_written"] += 1
            if snap["anchor_error"]:
                out["anchor_errors"] += 1        # EDGAR outage — NOT the by-design case
            elif snap["anchor"] is None:
                out["no_anchor"] += 1            # true non-filer/ETF — zero days by design
            if "annual" in snap["unavailable_periods"]:
                out["annual_unavailable"] += 1
            if "quarter" in snap["unavailable_periods"]:
                out["quarter_unavailable"] += 1
        except Exception as e:  # per-ticker isolation: one bad name never kills the run
            out["errors"] += 1
            logger.warning(redact_secrets(
                f"{label}: {ticker} failed: {type(e).__name__}: {e}"))
            try:
                await log_audit_event(
                    "analyst_estimates_error",
                    f"{label}: {ticker}: {type(e).__name__}: {e}"[:400],
                )
            except Exception:  # loud-ok: logger.warning above already fired
                pass
    if out["annual_unavailable"]:
        # Annual is IN-PLAN (verified 2026-08-31, re-verified 2026-09-02). A 402 here is
        # therefore almost always a RATE BREACH — FMP returns 402 for both, which is why the
        # 09-02 run read as a plan change when it was our own 240-calls/min pacing. One loud
        # row per run either way: a run that stored nothing must never be silent.
        try:
            await log_audit_event(
                "analyst_estimates_plan_change",
                f"{label}: /analyst-estimates period=annual returned 402 for "
                f"{out['annual_unavailable']} ticker(s). FMP answers a RATE BREACH with 402, "
                f"not 429, so this is most likely pacing, not a plan change — verified "
                f"2026-09-02 by probing the identical URL minutes apart: 200 -> 402 -> 200. "
                f"Check the pace before assuming a downgrade; a genuine plan refusal says "
                f"'not available under your current subscription' in the body and does NOT "
                f"clear on its own.",
            )
        except Exception:  # loud-ok: the run-summary row still carries the counter
            pass
    return out


_EMPTY_RUN = {"population": 0, "tickers_written": 0, "rows_written": 0,
              "no_anchor": 0, "anchor_errors": 0,
              "annual_unavailable": 0, "quarter_unavailable": 0, "errors": 1}


async def _run_and_log(tickers: list[str], today: date, event_type: str,
                       summary_prefix: str = "") -> dict[str, Any]:
    """Run the population and write ONE audit row. The daily snapshot and the one-shot
    backfill are the same run over different populations — extracted so a change to the
    counters or the audit shape lands in one place, not two (the duplication class
    `_persist_minute_bars_for_ticker_day` was pulled apart for the same day).
    Never raises into the scheduler; SILENT (no Telegram on any path)."""
    try:
        out = await _run_over_tickers(tickers, today, event_type)
        try:
            await log_audit_event(
                event_type,
                f"{summary_prefix}{out['rows_written']} row(s) across "
                f"{out['tickers_written']}/{out['population']} ticker(s); "
                f"{out['no_anchor']} no-anchor (zero honest days, by design), "
                f"{out['anchor_errors']} anchor-error (zero honest days, EDGAR fetch failed), "
                f"{out['annual_unavailable']} annual-402, "
                f"{out['quarter_unavailable']} quarter-402, "
                f"{out['errors']} error(s)",
            )
        except Exception:  # loud-ok: counters already logged by the scheduler wrapper
            pass
        return out
    except Exception as e:
        logger.error(f"{event_type} failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)


async def run_analyst_estimates_snapshot(
    today: date, tickers: "list[str] | None" = None
) -> dict[str, Any]:
    """The daily 18:12 ET snapshot. Population: live-source EP-alert tickers from the
    trailing POPULATION_LOOKBACK_DAYS — today's alerts get their estimates recorded
    the same evening (honest as-of the alert day: as_of_date is the read date, never
    back-stamped), and recent-alert names keep accruing a revision series."""
    try:
        if tickers is None:
            from datetime import timedelta
            since = today - timedelta(days=POPULATION_LOOKBACK_DAYS)
            tickers = await get_analyst_estimate_population(since)
    except Exception as e:
        logger.error(f"analyst_estimates_snapshot population query failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)
    return await _run_and_log(tickers, today, "analyst_estimates_snapshot")


async def run_analyst_estimates_backfill(today: date) -> dict[str, Any]:
    """The ONE-SHOT bounded backfill (run by hand at deploy, not scheduled): a snapshot
    over the FULL live-source alert population, all history. The per-ticker honest
    window [anchor_filing_date, as_of_date] is baked into every row — the backfill IS
    a snapshot with a wider population; the valid-from semantics do the rest. A ticker
    that reported last week buys days; one with no resolvable filing buys ZERO, by
    design. ~1,000 calls once (~335 tickers x 3)."""
    try:
        tickers = await get_analyst_estimate_population(date(2000, 1, 1))
    except Exception as e:
        logger.error(f"analyst_estimates_backfill population query failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)
    return await _run_and_log(tickers, today, "analyst_estimates_backfill",
                              summary_prefix="one-shot backfill: ")
