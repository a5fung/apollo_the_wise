"""#486 (2026-09-12) — the bounded read stops depending on somebody remembering.

THE GAP THIS CLOSES. `mi_theme_axis_shadow` is how the engine's view of a theme is compared
against the judge's, and that comparison needs a bounded as-of-alert-time value per row.
It was filled by a ONE-TIME backfill probe that last ran 2026-09-07 — correctly built as a
script for a one-off job — but the FORWARD path was never built. Measured 2026-09-12: 598
rows captured, **10 with no bounded value**, dated 09-03, 09-04 and 09-08, and the newest
backfill timestamp in the whole table was 09-07. The uncovered share grows every scan day,
so an agreement readout would measure a silently shrinking slice and degrade weekly for
reasons having nothing to do with themes.

WHY NIGHTLY AND NOT AT CAPTURE: the bounded read needs the day's own theme snapshot, which
the nightly theme run writes AFTER the alert fires. Computing at capture would read an
incomplete picture — which is why these rows were backfilled in the first place.

WHY 18:10: after the 17:58 co-move refresh and the 18:03 unscored writer, so the day's rows
exist before the sweep; and clear of BOTH deploy windows (12:00-13:00, 21:15-22:15 ET) so a
deploy restart cannot clip it.

MUTATION-PROVEN, reported as the runs came back:
  - make the audit row conditional on rows being filled -> test_it_records_every_run_even_a_quiet_one;
  - move the cron into a deploy window -> test_the_slot_avoids_both_deploy_windows;
  - mark the job execution-owned -> test_the_sweep_is_intelligence_owned.
"""
from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock

import pytest


def _src():
    return open("agents/market_intelligence/scheduler.py").read()


def test_the_slot_avoids_both_deploy_windows():
    """A job inside a deploy window gets clipped by a restart — and this one exists
    BECAUSE a fill stopped happening quietly."""
    src = _src()
    m = re.search(r'CronTrigger\(hour=(\d+), minute=(\d+),[^)]*\)\s*,\s*\n\s*id="theme_axis_bounded_sweep"', src)
    assert m, "the sweep is not registered with a CronTrigger"
    hh, mm = int(m.group(1)), int(m.group(2))
    minutes = hh * 60 + mm
    assert not (12 * 60 <= minutes < 13 * 60), "inside the 12:00-13:00 ET deploy window"
    assert not (21 * 60 + 15 <= minutes < 22 * 60 + 15), "inside the 21:15-22:15 ET window"
    # and after the two writers whose output it depends on
    assert minutes > 18 * 60 + 3, "must run after the 18:03 unscored writer"


def test_the_sweep_is_intelligence_owned():
    """It reads themes and writes a shadow table — no broker credentials, so it must NOT
    be pinned to the execution container."""
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS,
    )
    assert "theme_axis_bounded_sweep" in INTELLIGENCE_OWNED_JOB_IDS
    assert "theme_axis_bounded_sweep" not in EXECUTION_OWNED_JOB_IDS


@pytest.mark.asyncio
async def test_it_records_every_run_even_a_quiet_one(monkeypatch):
    """THE LIVENESS HALF. Most nights nothing needs filling. Without a row on those nights,
    a healthy quiet sweep and a dead job are the same silence — which is exactly how the
    original fill went unnoticed for five days."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import theme_axis_shadow as tas
    from tests.conftest import make_mock_pool

    pool, _conn = make_mock_pool()
    audited = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    monkeypatch.setattr(sch, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(sch, "log_audit_event", _audit)
    monkeypatch.setattr(sch, "notify_job_failure", AsyncMock())
    monkeypatch.setattr(tas, "backfill_bounded_theme_reads",
                        AsyncMock(return_value={"updated": 0, "remaining": 0}))

    await sch._theme_axis_bounded_sweep_job()

    assert len(audited) == 1
    evt, summary, detail = audited[0]
    assert evt == "theme_axis_bounded_sweep"
    assert "0 row(s) filled" in summary
    assert json.loads(detail)["updated"] == 0


@pytest.mark.asyncio
async def test_a_real_fill_is_reported_with_its_numbers(monkeypatch):
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import theme_axis_shadow as tas
    from tests.conftest import make_mock_pool

    pool, _conn = make_mock_pool()
    audited = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    monkeypatch.setattr(sch, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(sch, "log_audit_event", _audit)
    monkeypatch.setattr(sch, "notify_job_failure", AsyncMock())
    monkeypatch.setattr(tas, "backfill_bounded_theme_reads",
                        AsyncMock(return_value={"updated": 10, "remaining": 0}))

    await sch._theme_axis_bounded_sweep_job()

    assert "10 row(s) filled" in audited[0][1]
    assert json.loads(audited[0][2])["updated"] == 10


@pytest.mark.asyncio
async def test_a_failure_is_escalated_not_swallowed(monkeypatch):
    """If the sweep dies, saying nothing recreates the original defect exactly."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import theme_axis_shadow as tas
    from tests.conftest import make_mock_pool

    pool, _conn = make_mock_pool()
    notify = AsyncMock()
    monkeypatch.setattr(sch, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(sch, "log_audit_event", AsyncMock())
    monkeypatch.setattr(sch, "notify_job_failure", notify)
    monkeypatch.setattr(tas, "backfill_bounded_theme_reads",
                        AsyncMock(side_effect=RuntimeError("db down")))

    await sch._theme_axis_bounded_sweep_job()

    notify.assert_awaited_once()
    assert notify.await_args.args[0] == "theme_axis_bounded_sweep"
