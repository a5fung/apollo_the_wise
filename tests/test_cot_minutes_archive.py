"""COT 1-minute archive (2026-11-15): isolation of one bad ticker, all-fail raises after the audit row, file shape,
ET timestamps, Saturday 10:00 ET registration."""
import asyncio
import csv
import gzip
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from agents.market_intelligence import cot_minutes_archive as cma
from shared.dates import _ET

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 14, 10, 0, tzinfo=_ET)


def _df():
    idx = pd.DatetimeIndex(["2026-11-13 14:30:00", "2026-11-13 14:31:00"], tz="UTC")
    return pd.DataFrame({"Open": [1.0, 2.0], "High": [1.5, 2.5], "Low": [0.5, 1.5], "Close": [1.2, 2.2],
                         "Volume": [10, 20]}, index=idx)


@pytest.fixture
def audit(monkeypatch):
    rows = []

    async def fake(evt, summary, detail="", **kw):
        rows.append((evt, summary, detail))
        return True
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", fake)
    return rows


def test_one_bad_ticker_does_not_stop_the_rest(tmp_path, audit):
    def fetch(t):
        if t == "BAD":
            raise RuntimeError("boom")
        if t == "EMPTY":
            return pd.DataFrame()
        return _df()
    n = asyncio.run(cma.run_scheduled(NOW, tickers={"a": "A", "b": "BAD", "c": "EMPTY", "d": "D"},
                                      fetch=fetch, directory=tmp_path))
    assert n == 4
    assert len(audit) == 1 and '"failed": 1' in audit[0][2] and '"empty": 1' in audit[0][2]
    assert "ok 2 empty 1 failed 1" in audit[0][1]


def test_file_has_columns_and_et_timestamps(tmp_path, audit):
    asyncio.run(cma.run_scheduled(NOW, tickers={"gold": "GC=F"}, fetch=lambda t: _df(), directory=tmp_path))
    f = tmp_path / "2026-11-14.csv.gz"
    with gzip.open(f, "rt", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["market", "ticker", "ts_et", "o", "h", "l", "c", "v"]
    assert rows[1][:2] == ["gold", "GC=F"]
    assert rows[1][2] == "2026-11-13T09:30:00-05:00"
    assert not list(tmp_path.glob(".*tmp"))


def test_all_fail_raises_after_the_audit_row(tmp_path, audit):
    def fetch(t):
        raise RuntimeError("down")
    with pytest.raises(cma.CotMinutesArchiveError):
        asyncio.run(cma.run_scheduled(NOW, tickers={"a": "A", "b": "B"}, fetch=fetch, directory=tmp_path))
    assert len(audit) == 1 and "failed 2" in audit[0][1]
    assert not list(tmp_path.glob("*.csv.gz"))


def test_registered_saturday_10_et_intelligence_owned():
    from scripts.check_job_date_sources import Module, registrations
    from agents.market_intelligence import scheduler as sched
    regs = [r for r in registrations(Module(REPO / "agents" / "market_intelligence" / "scheduler.py"))
            if r["job_id"] == cma.JOB_ID]
    assert len(regs) == 1, regs
    c = regs[0]["cron"]
    assert c["day_of_week"] == "sat" and c["hour"] == 10 and c["minute"] == 0
    assert c["timezone"] == "America/New_York"
    assert cma.JOB_ID in sched.INTELLIGENCE_OWNED_JOB_IDS and cma.JOB_ID not in sched.EXECUTION_OWNED_JOB_IDS
