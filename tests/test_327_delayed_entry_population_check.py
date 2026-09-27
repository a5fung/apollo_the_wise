"""#327 (2026-09-26): the delayed-entry population guard. Every trigger row dated on or after the
2026-09-01 re-seed must be on a live EP alert; a breach pages, every night writes a counts row."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.health_checks as hc


class _Conn:
    def __init__(self, breach, legacy, campaigns=(), fail=False):
        self.breach, self.legacy, self.campaigns, self.fail = breach, legacy, list(campaigns), fail
        self.sql = []

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if self.fail:
            raise RuntimeError("db down")
        assert "mi_ep_alerts" in sql and "COALESCE(a.source, 'live') = 'live'" in sql
        return self.breach if "t.ep_date >= $1" in sql else self.legacy

    async def fetch(self, sql, *args):
        return [{"ticker": t, "ep_date": d} for t, d in self.campaigns]


@pytest.fixture
def wired(monkeypatch):
    import agents.market_intelligence.db as db
    import agents.market_intelligence.briefing as br
    import core.notifications as cn
    log, tg, fail = AsyncMock(), AsyncMock(return_value=True), AsyncMock()
    monkeypatch.setattr(db, "log_audit_event", log)
    monkeypatch.setattr(br, "send_telegram_message", tg)
    monkeypatch.setattr(cn, "notify_job_failure", fail)
    return log, tg, fail


def test_clean_night_writes_counts_and_stays_silent(wired):
    log, tg, _ = wired
    out = asyncio.run(hc.run_delayed_entry_population_check(conn=_Conn(0, 3667)))
    assert out["breach_rows"] == 0 and out["legacy_rows"] == 3667 and not out["spoke"]
    tg.assert_not_awaited()
    detail = json.loads(log.await_args.args[2])
    assert detail["status"] == "ok" and detail["legacy_rows"] == 3667


def test_a_non_ep_row_after_the_fix_pages_with_examples(wired):
    log, tg, _ = wired
    out = asyncio.run(hc.run_delayed_entry_population_check(
        conn=_Conn(4, 3667, [("ABCD", "2026-09-30"), ("WXYZ", "2026-09-29")])))
    assert out["spoke"] and out["breach_rows"] == 4
    assert "ABCD 2026-09-30" in tg.await_args.args[0]
    assert json.loads(log.await_args.args[2])["breach_campaigns"][0] == "ABCD 2026-09-30"


def test_a_failed_read_writes_an_error_row_and_pages(wired):
    log, tg, fail = wired
    out = asyncio.run(hc.run_delayed_entry_population_check(conn=_Conn(0, 0, fail=True)))
    assert out["errors"] and json.loads(log.await_args.args[2])["status"] == "error"
    fail.assert_awaited_once()
    tg.assert_not_awaited()


def test_the_check_is_in_the_liveness_registry():
    labels = [e[1] for e in hc._DETECTOR_LIVENESS_TABLES]
    assert "delayed-entry population check (#327)" in labels
