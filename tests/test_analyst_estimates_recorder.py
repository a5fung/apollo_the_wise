"""#333 analyst-estimates recorder tests (2026-08-31; v2 2026-09-01). Pure core
(normalize / honest_valid_from / latest_filing_from_submissions / estimate_for_scoring)
+ the orchestration half with module-level db/fetch functions monkeypatched. THE LINE:
this recorder writes only mi_analyst_estimates (+ mi_audit_log via log_audit_event) and
is SILENT — both pinned below.

THE BUG the v2 arm exists for (2026-09-01, first live run): the filing-date anchor was
FMP /income-statement, which is 402 Payment Required on our plan — and v1 treated an
anchor fetch failure as a ticker-killing exception, so the run wrote 0 rows with 99
errors. The design already said a ticker with no resolvable filing date records with a
ZERO honest window (honest_valid_from(None) == as_of); only the orchestration aborted.
v2 anchors on SEC EDGAR (keyless, no payment tier) and makes no-anchor a FIRST-CLASS
outcome; a 402 on any FMP endpoint degrades that period, never the ticker. The honesty
contract (never claim history without a filing-date anchor; the read date is stamped,
never inferred) is the load-bearing guard here and is what the mutation tests target.
"""
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import analyst_estimates_recorder as aer

AS_OF = date(2026, 8, 31)


# ── honest_valid_from (the lookahead guard — mutation target) ────────────────────────


def test_honest_window_anchors_on_the_filing_date():
    assert aer.honest_valid_from(date(2026, 7, 31), AS_OF) == date(2026, 7, 31)


def test_honest_window_without_anchor_claims_zero_history():
    """MUTATION TARGET: a row with no resolvable filing date may NEVER claim history —
    valid_from collapses to the read date (an ETF/non-filer buys zero days, by
    design). Dropping this guard is exactly the lookahead defect that invalidated
    the 08-25 structure study."""
    assert aer.honest_valid_from(None, AS_OF) == AS_OF


def test_honest_window_clamps_a_future_anchor():
    """A filingDate AFTER the read date is bad API data — clamp to the read date,
    never claim a window that starts in the future."""
    assert aer.honest_valid_from(date(2026, 9, 15), AS_OF) == AS_OF


# ── latest_filing_from_submissions (the EDGAR anchor parse — pure) ───────────────────


def _submissions(forms_dates):
    return {"filings": {"recent": {
        "form": [f for f, _ in forms_dates],
        "filingDate": [d for _, d in forms_dates],
    }}}


def test_edgar_anchor_takes_the_most_recent_anchor_form():
    """MUTATION TARGET (max, not first): the anchor is the LATEST 10-Q/10-K-class
    filing, robust to EDGAR's ordering — an older filing as anchor would misdate
    the window; a NEWER one is impossible to invent from this payload."""
    payload = _submissions([
        ("8-K", "2026-08-20"),          # not an anchor form — ignored
        ("10-Q", "2026-05-06"),         # deliberately BEFORE the newest: first-match
        ("10-K", "2026-02-25"),         #   instead of max would return 05-06
        ("10-Q", "2026-08-05"),
    ])
    assert aer.latest_filing_from_submissions(payload) == date(2026, 8, 5)


def test_edgar_anchor_ignores_non_anchor_forms_entirely():
    """Only filing-class forms anchor the window — an 8-K press release is not a
    financial filing and must never widen the claimed history."""
    assert aer.latest_filing_from_submissions(
        _submissions([("8-K", "2026-08-20"), ("SC 13G", "2026-08-01")])) is None


def test_edgar_anchor_malformed_payload_is_none_never_a_guess():
    assert aer.latest_filing_from_submissions(None) is None
    assert aer.latest_filing_from_submissions({}) is None
    assert aer.latest_filing_from_submissions({"filings": {}}) is None
    assert aer.latest_filing_from_submissions(
        _submissions([("10-Q", "not-a-date")])) is None


# ── normalize_fmp_estimate (raw capture, never derived) ──────────────────────────────


def _rec(**over):
    base = {
        "date": "2026-12-31", "revenueAvg": 2.5e9, "revenueHigh": 3.0e9,
        "revenueLow": 2.0e9, "epsAvg": 1.25, "epsHigh": 1.5, "epsLow": 1.0,
        "numAnalystsRevenue": 7, "numAnalystsEps": 6,
    }
    base.update(over)
    return base


def test_normalize_maps_raw_fields_and_stamps_the_window():
    row = aer.normalize_fmp_estimate(
        _rec(), ticker="MRNA", period_type="annual", as_of=AS_OF,
        anchor_filing_date=date(2026, 7, 31))
    assert row["ticker"] == "MRNA"
    assert row["period_end_date"] == date(2026, 12, 31)
    assert row["as_of_date"] == AS_OF
    assert row["anchor_filing_date"] == date(2026, 7, 31)
    assert row["valid_from_date"] == date(2026, 7, 31)
    assert row["revenue_avg"] == 2.5e9 and row["revenue_low"] == 2.0e9
    assert row["eps_high"] == 1.5
    assert row["num_analysts_revenue"] == 7 and row["num_analysts_eps"] == 6
    assert row["source"] == "fmp_stable"
    assert row["recorder_version"] == aer.RECORDER_VERSION


def test_normalize_missing_values_store_null_never_zero():
    row = aer.normalize_fmp_estimate(
        _rec(revenueAvg=None, numAnalystsRevenue=None),
        ticker="X", period_type="quarter", as_of=AS_OF, anchor_filing_date=None)
    assert row["revenue_avg"] is None          # NULL is an absence; 0 is a claim
    assert row["num_analysts_revenue"] is None
    assert row["valid_from_date"] == AS_OF     # no anchor -> zero claimed history


def test_normalize_without_a_period_date_returns_none():
    assert aer.normalize_fmp_estimate(
        _rec(date=None), ticker="X", period_type="annual", as_of=AS_OF,
        anchor_filing_date=None) is None
    assert aer.normalize_fmp_estimate(
        _rec(date="not-a-date"), ticker="X", period_type="annual", as_of=AS_OF,
        anchor_filing_date=None) is None


# ── estimate_for_scoring (the sketch's n<3 -> None rule — mutation target) ───────────


def test_thin_coverage_scores_none_and_threshold_is_tunable():
    """MUTATION TARGET (the sketch's contract): n_analysts < 3 -> None; the count is
    stored so the threshold re-tunes without re-fetching — proven by the override."""
    assert aer.estimate_for_scoring({"num_analysts_revenue": 2}) is None
    assert aer.estimate_for_scoring({"num_analysts_revenue": None}) is None
    row = {"num_analysts_revenue": 3, "revenue_avg": 1.0}
    assert aer.estimate_for_scoring(row) is row
    assert aer.estimate_for_scoring(row, min_analysts=5) is None
    assert aer.estimate_for_scoring({"num_analysts_revenue": 2}, min_analysts=2) is not None


# ── orchestration (db + fetch monkeypatched; never raises; per-ticker isolation) ─────


def _wire(monkeypatch, *, estimates=None, anchors=None, fail_tickers=(),
          anchor_fail_tickers=(), p402=()):
    written = []
    audits = []

    async def fake_filing(ticker, as_of):
        if ticker in anchor_fail_tickers:
            raise RuntimeError("EDGAR down")
        return (anchors or {}).get(ticker)

    async def fake_estimates(ticker, period):
        if ticker in fail_tickers:
            raise RuntimeError("fetch boom")
        if period in p402:
            raise RuntimeError_402()
        return (estimates or {}).get((ticker, period), [])

    async def fake_upsert(rows):
        written.extend(rows)
        return len(rows)

    async def fake_audit(event_type, summary, detail=""):
        audits.append((event_type, summary))

    monkeypatch.setattr(aer, "_fetch_last_filing_date", fake_filing)
    monkeypatch.setattr(aer, "_fetch_estimates", fake_estimates)
    monkeypatch.setattr(aer, "upsert_analyst_estimates", fake_upsert)
    monkeypatch.setattr(aer, "log_audit_event", fake_audit)
    monkeypatch.setattr(aer, "FMP_PACE_SECONDS", 0)
    return written, audits


class RuntimeError_402(Exception):
    def __init__(self):
        super().__init__("402")
        self.response = SimpleNamespace(status_code=402)


@pytest.mark.asyncio
async def test_snapshot_writes_rows_with_the_read_date_stamped(monkeypatch):
    written, audits = _wire(
        monkeypatch,
        anchors={"MRNA": date(2026, 7, 31)},
        estimates={("MRNA", "annual"): [_rec()],
                   # present but NEVER fetched: quarter is not on this tier (2026-09-02)
                   ("MRNA", "quarter"): [_rec(date="2026-09-30")]},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["rows_written"] == 1 and out["errors"] == 0   # annual only
    assert {r["period_type"] for r in written} == {"annual"}, (
        "quarter is not on this tier — fetching it anyway doubled the call volume against the "
        "very quota the annual call needs, which is how a working endpoint returned 99-for-99 "
        "empty on 2026-09-02")
    assert all(r["as_of_date"] == AS_OF for r in written)
    assert all(r["valid_from_date"] == date(2026, 7, 31) for r in written)
    assert any(e == "analyst_estimates_snapshot" for e, _ in audits)


@pytest.mark.asyncio
async def test_one_bad_ticker_never_kills_the_run(monkeypatch):
    written, audits = _wire(
        monkeypatch,
        anchors={"GOOD": date(2026, 8, 7)},
        estimates={("GOOD", "annual"): [_rec()]},
        fail_tickers={"BAD"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["BAD", "GOOD"])
    assert out["errors"] == 1
    assert out["tickers_written"] == 1
    assert [r["ticker"] for r in written] == ["GOOD"]
    assert any(e == "analyst_estimates_error" for e, _ in audits)


@pytest.mark.asyncio
async def test_anchor_failure_records_with_zero_window_not_abort(monkeypatch):
    """MUTATION TARGET — THE 2026-09-01 FIRST-RUN BUG. The anchor fetch failing (v1:
    FMP 402; v2: an EDGAR outage) must NOT abort the ticker: its estimates still
    record with a ZERO honest window (valid_from == as_of — honest_valid_from's
    no-anchor arm), the ticker is COUNTED (anchor_errors, not errors), and the clock
    this backbone exists to start keeps accruing. Removing the try/except around the
    anchor call recreates the 0-rows/99-errors run exactly."""
    written, _ = _wire(
        monkeypatch,
        estimates={("MRNA", "annual"): [_rec()],
                   ("MRNA", "quarter"): [_rec(date="2026-09-30")]},
        anchor_fail_tickers={"MRNA"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["errors"] == 0
    assert out["rows_written"] == 1 and out["tickers_written"] == 1   # annual only
    assert out["anchor_errors"] == 1
    assert out["no_anchor"] == 0               # outage is NOT the by-design case
    assert all(r["valid_from_date"] == AS_OF for r in written)   # zero claimed history
    assert all(r["anchor_filing_date"] is None for r in written)


@pytest.mark.asyncio
async def test_true_non_filer_counts_no_anchor_and_claims_zero_history(monkeypatch):
    """An ETF/non-filer (anchor resolves to None without error) is the BY-DESIGN
    zero-window case: counted as no_anchor, never as an error."""
    written, _ = _wire(monkeypatch, estimates={("SPYX", "annual"): [_rec()]})
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["SPYX"])
    assert out["no_anchor"] == 1 and out["anchor_errors"] == 0 and out["errors"] == 0
    assert written[0]["valid_from_date"] == AS_OF


@pytest.mark.asyncio
async def test_the_quarter_endpoint_is_never_called_at_all(monkeypatch):
    """MUTATION TARGET: putting "quarter" back in the period loop.

    FMP refuses it explicitly — "This value set for 'period' is not available under your current
    subscription" — and we VERIFIED that. Calling it anyway spent half of every run buying a
    refusal we already had, on the same quota the annual call needs. On 2026-09-02 that produced
    99 annual-402s from an endpoint that works, and an alarm announcing a plan change that had
    not happened. A 402 we can predict is not a degrade to handle, it is a call not to make."""
    called = []
    written, _ = _wire(
        monkeypatch,
        anchors={"MRNA": date(2026, 7, 31)},
        estimates={("MRNA", "annual"): [_rec()], ("MRNA", "quarter"): [_rec()]},
    )
    real = aer._fetch_estimates

    async def spy(ticker, period):
        called.append(period)
        return await real(ticker, period)

    monkeypatch.setattr(aer, "_fetch_estimates", spy)
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert called == ["annual"], f"the run fetched {called}; quarter must never be requested"
    assert out["rows_written"] == 1 and out["errors"] == 0
    assert written[0]["period_type"] == "annual"


@pytest.mark.asyncio
async def test_annual_402_degrades_and_audits_a_plan_change(monkeypatch):
    """MUTATION TARGET: letting a 402 kill the ticker, or letting a zero-row run go silent.

    Annual IS in-plan (verified 08-31, re-verified 09-02), so a 402 here is almost always a RATE
    BREACH — FMP answers both with 402, which is exactly why the 09-02 run read as a plan change
    when the real cause was our own 240-calls/min pacing against a free tier. Either way the run
    must degrade rather than raise, and must NOT be silent: a run that stored nothing is the one
    a reader most needs told about."""
    written, audits = _wire(
        monkeypatch,
        anchors={"MRNA": date(2026, 7, 31)},
        p402={"annual"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["errors"] == 0
    assert out["rows_written"] == 0 and written == []
    assert out["annual_unavailable"] == 1
    assert sum(1 for e, _ in audits if e == "analyst_estimates_plan_change") == 1
    msg = next(m for e, m in audits if e == "analyst_estimates_plan_change")
    assert "rate" in msg.lower(), (
        "the alarm must not assert a plan change it cannot know happened — it said exactly that "
        "on 09-02 and was wrong")


@pytest.mark.asyncio
async def test_both_periods_402_is_counted_not_an_error(monkeypatch):
    """Losing the estimate endpoint is a degrade, not a per-ticker error — the counters and the
    audit row carry the news; nothing raises. (Only annual is requested since 2026-09-02, so
    `quarter_unavailable` stays 0: we cannot lose an endpoint we never call.)"""
    written, audits = _wire(
        monkeypatch, anchors={"MRNA": date(2026, 7, 31)},
        p402={"annual", "quarter"},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["errors"] == 0 and out["rows_written"] == 0
    assert out["annual_unavailable"] == 1 and out["quarter_unavailable"] == 0
    assert written == []
    assert any(e == "analyst_estimates_plan_change" for e, _ in audits)


@pytest.mark.asyncio
async def test_run_never_raises_into_the_scheduler(monkeypatch):
    async def boom(since):
        raise RuntimeError("db down")
    monkeypatch.setattr(aer, "get_analyst_estimate_population", boom)
    out = await aer.run_analyst_estimates_snapshot(AS_OF)   # population lookup fails
    assert out["errors"] == 1 and out["rows_written"] == 0


# ── registration + THE LINE pins ─────────────────────────────────────────────────────


def test_liveness_registry_watches_the_recorder_on_its_business_date():
    """The recorder is SILENT, so the detector-liveness registry is its ONLY watchdog —
    a dead writer silently stops the 60-day clock gating #333. Keyed on the plain-DATE
    column (a timestamptz key would silently never be checked)."""
    from agents.market_intelligence.health_checks import _DETECTOR_LIVENESS_TABLES
    entries = [t for t in _DETECTOR_LIVENESS_TABLES if t[0] == "mi_analyst_estimates"]
    assert len(entries) == 1
    assert entries[0][2] == "as_of_date"


def test_job_is_classified_intelligence_owned():
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS,
    )
    assert "analyst_estimates_snapshot" in INTELLIGENCE_OWNED_JOB_IDS
    assert "analyst_estimates_snapshot" not in EXECUTION_OWNED_JOB_IDS


def test_the_line_no_telegram_no_broker_no_score():
    """DATA CAPTURE ONLY, pinned to the source: no Telegram send, no broker import,
    and no computed durability score anywhere in the recorder (raw values only —
    a stored score goes stale the moment a threshold is swept)."""
    src = Path(aer.__file__).read_text()
    assert "send_telegram" not in src
    assert "notify_job_failure" not in src
    assert "from agents.market_intelligence.broker" not in src
    assert "durability_score" not in src and "a7_durability" not in src


def test_the_402_endpoint_is_never_called_and_log_lines_are_redacted():
    """Two pins from the 2026-09-01 incident. (1) FMP /income-statement and /earnings
    are 402 on our plan — verified live, 99/99 tickers — so no fetch may target them
    again (the docstring may MENTION them as history; _fmp_get may not be pointed at
    them). (2) FMP puts the API key in the QUERY STRING and 99 audit rows landed
    carrying a live key: db.log_audit_event now redacts at the chokepoint, and every
    recorder log line that formats an exception must go through redact_secrets so the
    key never lands in container logs either."""
    src = Path(aer.__file__).read_text()
    assert '_fmp_get("/income-statement"' not in src
    assert '_fmp_get("/earnings"' not in src
    assert "from shared.secret_redaction import redact_secrets" in src
    assert "logger.warning(redact_secrets(" in src   # the per-ticker failure line
