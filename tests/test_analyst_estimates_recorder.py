"""#333 analyst-estimates recorder tests (2026-08-31). Pure core (normalize /
honest_valid_from / estimate_for_scoring) + the orchestration half with module-level
db/fetch functions monkeypatched. THE LINE: this recorder writes only
mi_analyst_estimates (+ mi_audit_log via log_audit_event) and is SILENT — both pinned
below. The honesty contract (never claim history without a filing-date anchor; the
read date is stamped, never inferred) is the load-bearing guard here and is what the
mutation test targets.
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
          quarter_402=False):
    written = []
    audits = []

    async def fake_filing(ticker):
        if ticker in fail_tickers:
            raise RuntimeError("fetch boom")
        return (anchors or {}).get(ticker)

    async def fake_estimates(ticker, period):
        if quarter_402 and period == "quarter":
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
                   ("MRNA", "quarter"): [_rec(date="2026-09-30")]},
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["rows_written"] == 2 and out["errors"] == 0
    assert {r["period_type"] for r in written} == {"annual", "quarter"}
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
async def test_quarter_402_degrades_to_annual_only(monkeypatch):
    """The quarter endpoint is unverified on our plan — a 402 records the annual
    estimates and counts the degrade; it never kills the ticker's snapshot."""
    written, _ = _wire(
        monkeypatch,
        anchors={"MRNA": date(2026, 7, 31)},
        estimates={("MRNA", "annual"): [_rec()]},
        quarter_402=True,
    )
    out = await aer.run_analyst_estimates_snapshot(AS_OF, tickers=["MRNA"])
    assert out["rows_written"] == 1 and out["errors"] == 0
    assert out["quarter_unavailable"] == 1
    assert written[0]["period_type"] == "annual"


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
