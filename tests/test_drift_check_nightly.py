"""Nightly docs-vs-reality drift check (2026-08-29).

`python scripts/live_rules.py --drift-only` worked but only ran when someone typed it by hand,
so drift accumulated silently for weeks (docs/architecture/entry_pipeline.md called the #490
real-time gap re-check "BUILT OFF" for four weeks after it went live; lane2_grouping_v2 ran ON
and grade-affecting with no owner doc naming it at all). This ships:

  1. `agents/market_intelligence/health_checks.run_drift_check` — reuses scripts/live_rules.py's
     detection functions DIRECTLY (never a second copy of the rules), reading "prod" in-process
     (mi_safeguard_state + mi_strategies via the DB pool, env off os.environ) instead of the
     interactive tool's SSH round-trip, since this job already runs ON prod.
  2. `agents/market_intelligence/scheduler._post_drift_check_job` — scheduled nightly, EVERY
     day (docs rot on weekends too), own try/except + notify_job_failure so a drift-check
     failure can never take down anything else.
  3. `agents/market_intelligence/system_review._aggregate_drift_findings` — the Sunday weekly
     digest's only surface for UNVERIFIED findings (DRIFT already Telegrams nightly on its own).

Severities are NOT alerted the same way (CLAUDE.md audit L1/L2/L3 tiering): DRIFT (a doc
provably contradicts code/prod) Telegrams every run while it stands, always naming what's NEW
vs standing (a standing count nobody has fixed is noise; a new one is signal). UNVERIFIED (a
dated claim nothing can check) is audit-log only.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import health_checks as hc
from agents.market_intelligence import scheduler as sched
from scripts.live_rules import DriftRow

HC_SRC = pathlib.Path("agents/market_intelligence/health_checks.py").read_text(encoding="utf-8")
SCHED_SRC = pathlib.Path("agents/market_intelligence/scheduler.py").read_text(encoding="utf-8")
DB_SRC = pathlib.Path("agents/market_intelligence/db.py").read_text(encoding="utf-8")
DOCKERFILE = pathlib.Path("docker/Dockerfile.market").read_text(encoding="utf-8")
DEPLOY_SRC = pathlib.Path("scripts/deploy.sh").read_text(encoding="utf-8")
REVIEW_SRC = pathlib.Path("agents/market_intelligence/system_review.py").read_text(encoding="utf-8")


def _drift(where, claim="claim", actual="actual", words="words", rule="stale-claim"):
    return DriftRow(rule=rule, severity="DRIFT", where=where, claim=claim, actual=actual, words=words)


def _unverified(where, claim="claim", actual="actual", words="words", rule="stale-claim"):
    return DriftRow(rule=rule, severity="UNVERIFIED", where=where, claim=claim, actual=actual, words=words)


class _FakeConn:
    """Minimal asyncpg-Connection stand-in: `fetch` branches on the SQL text (toggle table vs
    strategy table — get_all_safeguard_states/get_all_strategy_summaries run for REAL against
    this fake, so this is also a live check that those two db.py functions issue matching SQL);
    `fetchrow` returns the previous drift-check snapshot, if any."""

    def __init__(self, prev_detail: dict | None = None, safeguard_rows=None, strategy_rows=None,
                fail_fetch=False):
        self._prev_detail = prev_detail
        self._safeguard_rows = safeguard_rows if safeguard_rows is not None else []
        self._strategy_rows = strategy_rows if strategy_rows is not None else []
        self._fail_fetch = fail_fetch

    async def fetch(self, sql, *args):
        if self._fail_fetch:
            raise RuntimeError("prod db unreachable (simulated)")
        if "mi_safeguard_state" in sql:
            return self._safeguard_rows
        if "mi_strategies" in sql:
            return self._strategy_rows
        raise AssertionError(f"unexpected fetch: {sql}")

    async def fetchrow(self, sql, *args):
        assert "mi_audit_log" in sql
        if self._prev_detail is None:
            return None
        return {"detail": json.dumps(self._prev_detail)}


def _patch_live_rules(monkeypatch, drift_rows):
    """Stub out the expensive real-repo scans and pin detect_drift's output — isolates the
    counting/routing/diffing logic in health_checks.run_drift_check from the ACTUAL current
    state of docs/ and agents/market_intelligence/ (which changes every session and must not
    make this test flaky)."""
    from scripts import live_rules as lr
    monkeypatch.setattr(lr, "collect_code_facts", lambda repo: {})
    monkeypatch.setattr(lr, "discover_runtime_toggles", lambda repo: {})
    # A non-empty sentinel — `detect_drift` below is also stubbed and ignores its content, but
    # run_drift_check refuses to proceed on an EMPTY doc list (see
    # test_empty_doc_list_is_a_reported_error_not_a_clean_run), so this must not be [].
    monkeypatch.setattr(lr, "load_setup_docs", lambda repo: ["sentinel-doc"])
    monkeypatch.setattr(lr, "detect_drift", lambda docs, res: drift_rows)


# ── run_drift_check: severity routing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_drift_present_telegrams_and_writes_audit_row(monkeypatch):
    _patch_live_rules(monkeypatch, [_drift("docs/setups/magna53_ep.md:12")])
    audit = AsyncMock()
    tg = AsyncMock()
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(hc, "log_audit_event", audit)
    monkeypatch.setattr(brief, "send_telegram_message", tg)

    out = await hc.run_drift_check(conn=_FakeConn())

    assert out["drift_n"] == 1
    tg.assert_awaited_once()
    assert "DRIFT" in tg.await_args.args[0]
    # every run persists a snapshot, drift or not — it is the diff baseline for next time
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "drift_check_snapshot"


@pytest.mark.asyncio
async def test_telegram_send_failure_on_drift_is_logged_and_persisted(monkeypatch, caplog):
    """send_telegram_message never raises on a delivery failure — it swallows it and returns
    False. Without an explicit check here, a failed send on the ONE severity meant to wake
    someone is invisible everywhere except a single log line nobody tails."""
    _patch_live_rules(monkeypatch, [_drift("docs/setups/magna53_ep.md:12")])
    audit = AsyncMock()
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(hc, "log_audit_event", audit)
    monkeypatch.setattr(brief, "send_telegram_message", AsyncMock(return_value=False))

    with caplog.at_level("ERROR"):
        out = await hc.run_drift_check(conn=_FakeConn())

    assert out["spoke"] is False
    assert any("TELEGRAM" in r.message.upper() for r in caplog.records)
    detail = json.loads(audit.await_args.args[2])
    assert detail["spoke"] is False
    assert "TELEGRAM SEND FAILED" in audit.await_args.args[1]


@pytest.mark.asyncio
async def test_unverified_only_writes_audit_no_telegram(monkeypatch):
    """UNVERIFIED is a human-read item, not an actionable one — nightly Telegram on it is
    exactly the muted-alert failure mode CLAUDE.md warns about."""
    _patch_live_rules(monkeypatch, [_unverified("docs/analysis/some_finding.md:40")])
    audit = AsyncMock()
    tg = AsyncMock()
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(hc, "log_audit_event", audit)
    monkeypatch.setattr(brief, "send_telegram_message", tg)

    out = await hc.run_drift_check(conn=_FakeConn())

    assert out["drift_n"] == 0
    assert out["unverified_n"] == 1
    tg.assert_not_awaited()
    audit.assert_awaited_once()
    detail = json.loads(audit.await_args.args[2])
    assert detail["unverified_n"] == 1


@pytest.mark.asyncio
async def test_clean_run_still_persists_a_snapshot(monkeypatch):
    """Zero findings still needs a row written — it is the next run's diff baseline (a gap here
    would make every finding on the FOLLOWING clean-to-dirty transition read as 'new'.)"""
    _patch_live_rules(monkeypatch, [])
    audit = AsyncMock()
    tg = AsyncMock()
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(hc, "log_audit_event", audit)
    monkeypatch.setattr(brief, "send_telegram_message", tg)

    out = await hc.run_drift_check(conn=_FakeConn())

    assert out == {"drift_n": 0, "new_drift_n": 0, "unverified_n": 0,
                   "prod_reachable": True, "error": None, "spoke": False}
    tg.assert_not_awaited()
    audit.assert_awaited_once()


# ── run_drift_check: new-vs-standing diffing ─────────────────────────────────


@pytest.mark.asyncio
async def test_new_since_last_run_is_computed_against_the_persisted_snapshot(monkeypatch):
    """Two DRIFT rows tonight; the previous snapshot already carried one of them. Only the
    other one is NEW — this is the whole point of persisting fingerprints (a standing count
    of 2 that nobody has fixed is noise; '1 NEW' is a signal)."""
    known = _drift("docs/setups/magna53_ep.md:12", claim="c1", actual="a1", rule="stale-claim")
    fresh = _drift("docs/setups/ninem.md:99", claim="c2", actual="a2", rule="value-mismatch")
    _patch_live_rules(monkeypatch, [known, fresh])
    audit = AsyncMock()
    tg = AsyncMock()
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(hc, "log_audit_event", audit)
    monkeypatch.setattr(brief, "send_telegram_message", tg)

    prev_snapshot = {"drift_fingerprints": [hc._drift_fingerprint(known)]}
    out = await hc.run_drift_check(conn=_FakeConn(prev_detail=prev_snapshot))

    assert out["drift_n"] == 2
    assert out["new_drift_n"] == 1
    msg = tg.await_args.args[0]
    assert "1 NEW" in msg
    assert "ninem.md" in msg          # the new one is named
    assert "1 standing" in msg        # the old one is acknowledged, not restated in full


@pytest.mark.asyncio
async def test_a_doc_reflow_does_not_fake_new_drift(monkeypatch):
    """The SAME finding at a DIFFERENT line number (an unrelated edit above it shifted every
    line below) must NOT read as new — fingerprinting on `file:line` would fake exactly this,
    which is the noise that trains an operator to stop reading the alert."""
    prev_row = _drift("docs/setups/magna53_ep.md:12", claim="c1", actual="a1")
    same_but_shifted = _drift("docs/setups/magna53_ep.md:57", claim="c1", actual="a1")
    _patch_live_rules(monkeypatch, [same_but_shifted])
    monkeypatch.setattr(hc, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(brief, "send_telegram_message", AsyncMock())

    prev_snapshot = {"drift_fingerprints": [hc._drift_fingerprint(prev_row)]}
    out = await hc.run_drift_check(conn=_FakeConn(prev_detail=prev_snapshot))

    assert out["drift_n"] == 1
    assert out["new_drift_n"] == 0, "a line-number shift alone must not count as new drift"


# ── run_drift_check: prod-unreachable degrades honestly ──────────────────────


@pytest.mark.asyncio
async def test_prod_db_read_failure_degrades_without_raising_or_faking_drift(monkeypatch):
    """The in-process prod read (mi_safeguard_state/mi_strategies) can fail like any DB call.
    Must report prod_reachable=False and keep going — never crash, never invent drift."""
    _patch_live_rules(monkeypatch, [])
    monkeypatch.setattr(hc, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(brief, "send_telegram_message", AsyncMock())

    out = await hc.run_drift_check(conn=_FakeConn(fail_fetch=True))

    assert out["prod_reachable"] is False
    assert out["error"] is None  # this is a degrade, not a job failure


@pytest.mark.asyncio
async def test_empty_doc_list_is_a_reported_error_not_a_clean_run(monkeypatch):
    """A dropped `COPY docs/ docs/`, a renamed docs/setups/, or a bad repo-path resolution
    would make load_setup_docs return []. Falling through to detect_drift on an empty doc list
    would report '0 DRIFT / 0 UNVERIFIED' forever — a false-clean result on the exact class of
    failure this check exists to catch. Must refuse instead."""
    from scripts import live_rules as lr
    monkeypatch.setattr(lr, "collect_code_facts", lambda repo: {})
    monkeypatch.setattr(lr, "discover_runtime_toggles", lambda repo: {})
    monkeypatch.setattr(lr, "load_setup_docs", lambda repo: [])
    audit = AsyncMock()
    tg = AsyncMock()
    from agents.market_intelligence import briefing as brief
    monkeypatch.setattr(hc, "log_audit_event", audit)
    monkeypatch.setattr(brief, "send_telegram_message", tg)

    out = await hc.run_drift_check(conn=_FakeConn())

    assert out["error"] is not None and "ZERO doc files" in out["error"]
    assert out["drift_n"] == 0 and out["unverified_n"] == 0  # never silently reported as clean
    tg.assert_not_awaited()
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "drift_check_error"


def test_live_rules_import_failure_is_handled_not_raised():
    """scripts.live_rules must be importable as-is inside run_drift_check — a broken import
    must degrade (recorded, function returns) rather than propagate and take the job down."""
    body = HC_SRC[HC_SRC.find("async def run_drift_check"):]
    assert "except Exception as e:  # loud-ok: an import failure IS the finding here" in body
    assert 'out["error"]' in body


# ── scheduler wiring ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_notifies_on_failure_and_does_not_raise(monkeypatch):
    async def _boom():
        raise RuntimeError("simulated drift-check crash")
    monkeypatch.setattr(hc, "run_drift_check", _boom)
    notify = AsyncMock()
    monkeypatch.setattr(sched, "notify_job_failure", notify)

    await sched._post_drift_check_job()  # must not raise

    notify.assert_awaited_once()
    assert notify.await_args.args[0] == "drift_check"


def test_job_is_registered_every_day_not_just_trading_days():
    """Docs rot on weekends too — this must NOT inherit the mon-fri trading-day guard the
    surrounding market jobs use."""
    i = SCHED_SRC.find('id="drift_check"')
    assert i > 0, "the drift-check job is not registered in the scheduler"
    seg = SCHED_SRC[max(0, i - 400):i]
    assert "_post_drift_check_job" in seg
    assert 'day_of_week="mon-fri"' not in seg, (
        "drift check must run every day — docs can go stale on a weekend same as a weekday")


def test_job_is_isolated_with_its_own_try_except():
    i = SCHED_SRC.find("async def _post_drift_check_job")
    assert i > 0
    body = SCHED_SRC[i:i + 1500]
    assert "except Exception as e" in body
    assert "notify_job_failure" in body


# ── db.py: bulk toggle/strategy reads ─────────────────────────────────────────


def test_bulk_safeguard_and_strategy_readers_exist():
    assert "async def get_all_safeguard_states" in DB_SRC
    assert "async def get_all_strategy_summaries" in DB_SRC
    assert "FROM mi_safeguard_state ORDER BY safeguard, account_mode" in DB_SRC
    assert "FROM mi_strategies ORDER BY strategy_id" in DB_SRC


@pytest.mark.asyncio
async def test_get_all_safeguard_states_returns_injected_rows():
    from agents.market_intelligence.db import get_all_safeguard_states
    conn = _FakeConn(safeguard_rows=[{"safeguard": "drawdown_breaker", "account_mode": "live",
                                      "state": "on", "last_transition_at": None}])
    rows = await get_all_safeguard_states(conn)
    assert rows[0]["safeguard"] == "drawdown_breaker"


# ── image + deploy-scope wiring: docs/ must ship inside the market-agent image ──


def test_dockerfile_bakes_docs_into_the_market_image():
    assert "COPY docs/ docs/" in DOCKERFILE


def test_deploy_scope_guard_rebuilds_market_agent_on_a_docs_change():
    """Without this, a doc fix lands in git but the deployed image (and the drift check inside
    it) keeps the stale text until an unrelated deploy happens to rebuild it — the #533
    fixture-staleness class, now against the check whose job is catching staleness."""
    i = DEPLOY_SRC.find("docs/*)")
    assert i > 0, "no docs/* case arm in the deploy.sh scope-drift guard"
    line = DEPLOY_SRC[i:i + 60]
    assert "NEED_MARKET=1" in line


# ── weekly digest: UNVERIFIED's only surface ──────────────────────────────────


def test_weekly_digest_aggregates_drift_findings():
    assert "_aggregate_drift_findings" in REVIEW_SRC
    assert '"drift_check": drift_check' in REVIEW_SRC
    # Data reaching `metrics` is not the same as the LLM narrator being TOLD to surface it —
    # _SYSTEM_PROMPT dictates an "exactly this structure... no filler headers" output, so a key
    # with no matching prompt rule silently never appears. Must be an explicit rule, same as
    # every other conditional appendix (audit_errors, wick, shadow_orb, ...).
    assert "drift_check.unverified_n" in REVIEW_SRC


@pytest.mark.asyncio
async def test_weekly_aggregate_reads_the_latest_snapshot(monkeypatch):
    from agents.market_intelligence import system_review as sr
    fake_row = {"detail": json.dumps({"drift_n": 0, "unverified_n": 3,
                                       "prod_reachable": True,
                                       "unverified_claims": [{"where": "x.md:1", "words": "w"}]}),
               "created_at": "2026-08-29T18:02:00+00:00"}
    monkeypatch.setattr(sr, "get_audit_log", AsyncMock(return_value=[fake_row]))

    out = await sr._aggregate_drift_findings(7)

    assert out["unverified_n"] == 3
    assert out["drift_n"] == 0
