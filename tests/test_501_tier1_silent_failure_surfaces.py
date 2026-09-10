"""#501 Tier-1 (2026-09-10) — the four money-path safety nets that could die silently.

SoT: docs/analysis/silent_failure_taxonomy_2026-07-23.md §2 F1–F4 (+ §5 fixes 1–4).
All four fixes are observability-only (audit row + deduped Telegram); no strategy,
safeguard, sizing or trade-state behaviour changes, and every test below asserts
the ORIGINAL control flow is preserved (the exception still re-raises, the empty
snapshot still returns `{}`, the handler still swallows, `errors` still counts).

Every test drives the REAL code path — `core.job_audit.audit_run`,
`collector.get_snapshot_all` → `llm_health.alert_endpoint_shape_anomaly`,
`scheduler._check_fills_job` / `_stream_health_watchdog`,
`order_manager.reconcile_all_modes` — and only the leaf sinks (audit-log write,
audit-log lookback, Telegram send) are captured. No local re-implementation of any
guard is asserted against (the failure mode this week's six could-not-fail gates
shared).

MUTATION CHECKS (run by hand on 2026-09-10, recorded here, not re-run by CI):
  F1  delete `await record_job_failure(job_id, e)` in core/job_audit.py::audit_run
      → test_f1_* FAIL (no audit row, no Telegram; the exception still re-raises).
  F2  delete `await _note_empty_snapshot(...)` in collector.get_snapshot_all
      → test_f2_* FAIL (no row, no page on the 3rd empty tick).
  F3  delete the two `await record_job_failure(...)` calls in scheduler.py
      → test_f3_* FAIL.
  F4  delete `await _note_mode_reconcile_failure(...)` in order_manager.reconcile_all_modes
      → test_f4_* FAIL.
  esc delete `md_escape(...)` in core/notifications.py::notify_job_failure
      → test_notify_job_failure_escapes_underscores FAIL.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from core import job_audit, notifications
from core.job_audit import audit_run, record_job_failure
from agents.market_intelligence.audit_events import (
    JOB_FAILED_ERROR,
    ORDER_STATUS_RECONCILE_MODE_ERROR,
    POLYGON_SNAPSHOT_EMPTY_ERROR,
)
from tests.conftest import make_mock_pool


# ── shared wiring ─────────────────────────────────────────────────────────────

class _Sinks:
    """The three leaf sinks every surface here ends in, captured."""

    def __init__(self):
        self.audit_rows: list[tuple[str, str, str]] = []
        self.lookback_rows: list[dict] = []
        self.telegrams: list[str] = []

    async def log_audit_event(self, event_type, summary, detail=""):
        self.audit_rows.append((event_type, summary, detail))

    async def get_audit_log(self, event_type=None, since_hours=48, limit=30, **kw):
        return [r for r in self.lookback_rows
                if event_type is None or r.get("event_type") == event_type]

    async def notify_job_failure(self, job_name, error):
        self.telegrams.append(f"{job_name}: {error}")

    async def send_telegram_message(self, text, **kw):
        self.telegrams.append(text)
        return True

    def rows(self, event_type):
        return [r for r in self.audit_rows if r[0] == event_type]


@pytest.fixture
def sinks(monkeypatch):
    s = _Sinks()
    import agents.market_intelligence.db as db
    from agents.market_intelligence import briefing
    monkeypatch.setattr(db, "log_audit_event", s.log_audit_event)
    monkeypatch.setattr(db, "get_audit_log", s.get_audit_log)
    monkeypatch.setattr(job_audit, "notify_job_failure", s.notify_job_failure)
    monkeypatch.setattr(briefing, "send_telegram_message", s.send_telegram_message)
    monkeypatch.setattr(job_audit, "_last_job_failure_alert_ts", {})
    return s


def _wire_job_runs(monkeypatch, run_id=7):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"id": run_id})
    conn.execute = AsyncMock(return_value="UPDATE 1")
    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    return conn


# ── F1 — a no-handler job raising into audit_run ──────────────────────────────

@pytest.mark.asyncio
async def test_f1_no_handler_job_failure_writes_audit_row_and_pages(monkeypatch, sinks):
    conn = _wire_job_runs(monkeypatch)

    with pytest.raises(RuntimeError):
        async with audit_run("stuck_fill_watchdog"):
            raise RuntimeError('column "stop_order_id" does not exist')

    # original behaviour preserved: mi_job_runs row flips to 'failed' and it re-raised
    assert conn.execute.await_args.args[3] == "failed"
    # NEW: durable audit row, named to ride the nightly %error% sweep
    rows = sinks.rows(JOB_FAILED_ERROR)
    assert len(rows) == 1
    assert JOB_FAILED_ERROR.endswith("_error")
    assert "job=stuck_fill_watchdog " in rows[0][1] and "tg=1" in rows[0][1]
    assert json.loads(rows[0][2])["job_id"] == "stuck_fill_watchdog"
    # NEW: the operator is paged, with the error text
    assert len(sinks.telegrams) == 1
    assert "stuck_fill_watchdog" in sinks.telegrams[0]
    assert "stop_order_id" in sinks.telegrams[0]


@pytest.mark.asyncio
async def test_f1_page_is_deduped_per_job_but_rows_keep_landing(monkeypatch, sinks):
    """A 30-second watchdog failing all session must not send 780 pages: one per
    job per window; every failure still writes its row. A DIFFERENT job pages."""
    _wire_job_runs(monkeypatch)
    for _ in range(3):
        with pytest.raises(ValueError):
            async with audit_run("stop_ack_timeout_watchdog"):
                raise ValueError("boom")
    with pytest.raises(ValueError):
        async with audit_run("stuck_fill_watchdog"):
            raise ValueError("boom")

    rows = sinks.rows(JOB_FAILED_ERROR)
    assert len(rows) == 4
    assert [("tg=1" in r[1]) for r in rows] == [True, False, False, True]
    assert len(sinks.telegrams) == 2
    assert "stop_ack_timeout_watchdog" in sinks.telegrams[0]
    assert "stuck_fill_watchdog" in sinks.telegrams[1]


@pytest.mark.asyncio
async def test_f1_dedup_survives_a_restart_via_audit_log_lookback(sinks):
    """Fresh process (empty pre-gate) but the audit log already holds a tg=1 row
    for this job inside the window → no second page."""
    sinks.lookback_rows = [{"event_type": JOB_FAILED_ERROR,
                            "summary": "job=stuck_fill_watchdog ValueError: x tg=1"}]
    paged = await record_job_failure("stuck_fill_watchdog", ValueError("again"))
    assert paged is False
    assert sinks.telegrams == []
    assert "tg=0" in sinks.rows(JOB_FAILED_ERROR)[0][1]


@pytest.mark.asyncio
async def test_f1_lookback_outage_still_pages_and_helper_never_raises(monkeypatch, sinks):
    """The DB outage that killed the job may also kill the lookback — page anyway
    (a duplicate beats a dead watchdog nobody hears about); and NOTHING the
    helper does may mask the original exception."""
    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "get_audit_log", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(job_audit, "notify_job_failure",
                        AsyncMock(side_effect=RuntimeError("tg down")))
    paged = await record_job_failure("x_job", ValueError("orig"))
    assert paged is True   # attempted — the send itself failing is logged, not raised


@pytest.mark.asyncio
async def test_f1_cancelled_branch_untouched(monkeypatch, sinks):
    """#512's contract: CancelledError never Telegrams (no network call inside a
    cancellation handler). The F1 surface lives ONLY on the Exception branch."""
    import asyncio
    _wire_job_runs(monkeypatch)
    with pytest.raises(asyncio.CancelledError):
        async with audit_run("some_job"):
            raise asyncio.CancelledError()
    assert sinks.telegrams == []
    assert sinks.rows(JOB_FAILED_ERROR) == []


# ── the page must be able to RENDER — legacy-Markdown 400 hazard ──────────────

@pytest.mark.asyncio
async def test_notify_job_failure_escapes_underscores(monkeypatch):
    """Three underscores (odd) inside `_..._` italics 400'd the send and dropped
    the alert (health_checks.py's recorder guard documents the same trap)."""
    sent = []

    async def _owner(text):
        sent.append(text)

    monkeypatch.setattr(notifications, "notify_owner", _owner)
    await notifications.notify_job_failure(
        "stuck_fill_watchdog", 'column "stop_order_id" does_not exist\nsecond line')
    body = sent[0].split("\n", 1)[1]
    assert body.startswith("_") and body.endswith("_")
    inner = body[1:-1]
    assert "\\_" in inner and "stop\\_order\\_id" in inner
    assert inner.replace("\\_", "").count("_") == 0      # no unescaped `_` remains
    assert "\n" not in inner                              # italics cannot span lines


@pytest.mark.asyncio
async def test_notify_owner_resends_plain_text_on_400(monkeypatch):
    posts = []

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = "Bad Request: can't parse entities"

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **kw):
            posts.append(json)
            return _Resp(400 if "parse_mode" in json else 200)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    await notifications.notify_owner(
        "🚨 *Scheduled job failed*: `stuck_fill_watchdog`\n_bad \\_ text_")
    assert len(posts) == 2
    assert posts[0]["parse_mode"] == "Markdown"
    assert "parse_mode" not in posts[1]
    assert posts[1]["text"] == "🚨 Scheduled job failed: stuck_fill_watchdog\nbad _ text"


# ── F2 — 200-OK-but-empty full-market snapshot ────────────────────────────────

@pytest.fixture
def snapshot_env(monkeypatch, sinks):
    from agents.market_intelligence import collector, llm_health
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})
    monkeypatch.setattr(collector, "_polygon_get", AsyncMock(return_value={"tickers": []}))
    return collector


def _polygon_rows(n, tg1_at=None):
    return [{"event_type": POLYGON_SNAPSHOT_EMPTY_ERROR,
             "summary": f"ENDPOINT SHAPE ANOMALY provider=polygon reason=x count={i + 1} "
                        f"tg={1 if tg1_at == i else 0}"} for i in range(n)]


@pytest.mark.asyncio
async def test_f2_empty_200_snapshot_writes_a_row_and_still_returns_empty(snapshot_env, sinks):
    async def scan_like_caller():
        return await snapshot_env.get_snapshot_all()

    out = await scan_like_caller()
    assert out == {}                                   # behaviour unchanged
    rows = sinks.rows(POLYGON_SNAPSHOT_EMPTY_ERROR)
    assert len(rows) == 1
    assert POLYGON_SNAPSHOT_EMPTY_ERROR.endswith("_error")
    assert "provider=polygon" in rows[0][1]
    assert "caller=scan_like_caller" in rows[0][1]     # labelled from the frame, no call-site edit
    assert sinks.telegrams == []                       # one blip does not page


@pytest.mark.asyncio
async def test_f2_third_empty_tick_in_the_window_pages_with_blind_wording(snapshot_env, sinks):
    sinks.lookback_rows = _polygon_rows(2)             # two earlier empties this hour
    await snapshot_env.get_snapshot_all(caller="ep_scan")
    assert len(sinks.telegrams) == 1
    page = sinks.telegrams[0]
    assert "DETECTION IS BLIND" in page.split("\n")[0]  # consequence is the FIRST line
    assert "3×" in page and "ep_scan" in page
    assert "sunset" not in page                        # not the vendor-sunset wording
    assert "tg=1" in sinks.rows(POLYGON_SNAPSHOT_EMPTY_ERROR)[0][1]


@pytest.mark.asyncio
async def test_f2_page_is_deduped_inside_the_window(snapshot_env, sinks):
    sinks.lookback_rows = _polygon_rows(3, tg1_at=0)   # already paged this hour
    await snapshot_env.get_snapshot_all(caller="flag_scan")
    assert sinks.telegrams == []
    assert len(sinks.rows(POLYGON_SNAPSHOT_EMPTY_ERROR)) == 1   # row still lands


@pytest.mark.asyncio
async def test_f2_exception_path_is_not_double_surfaced(monkeypatch, snapshot_env, sinks):
    """`_polygon_get` raising is already loud via maybe_alert_api_failure — the
    empty guard must NOT add a second surface for the same outage."""
    monkeypatch.setattr(snapshot_env, "_polygon_get",
                        AsyncMock(side_effect=httpx.ConnectError("down")))
    assert await snapshot_env.get_snapshot_all() == {}
    assert sinks.rows(POLYGON_SNAPSHOT_EMPTY_ERROR) == []


@pytest.mark.asyncio
async def test_f2_non_empty_snapshot_is_silent(monkeypatch, snapshot_env, sinks):
    monkeypatch.setattr(snapshot_env, "_polygon_get",
                        AsyncMock(return_value={"tickers": [{"ticker": "AAPL"}]}))
    assert await snapshot_env.get_snapshot_all() == {"AAPL": {"ticker": "AAPL"}}
    assert sinks.audit_rows == [] and sinks.telegrams == []


@pytest.mark.asyncio
async def test_f2_canary_defaults_unchanged_for_existing_callers(sinks, monkeypatch):
    """The kwargs are additive: with none passed the 72h/3 constants and the
    vendor-sunset wording still apply (the #603 Perplexity + TV-news callers)."""
    from agents.market_intelligence import llm_health
    monkeypatch.setattr(llm_health, "_last_shape_alert_ts", {})
    sinks.lookback_rows = [{"event_type": "perplexity_endpoint_error",
                            "summary": "ENDPOINT SHAPE ANOMALY provider=perplexity x tg=0"}] * 2
    await llm_health.alert_endpoint_shape_anomaly("perplexity", "perplexity_endpoint_error", "x")
    assert len(sinks.telegrams) == 1 and "sunset" in sinks.telegrams[0]
    assert "72h" in sinks.telegrams[0]


# ── F3 — the WS-outage backstop chain's own failures ──────────────────────────

@pytest.fixture
def live_mode(monkeypatch):
    from agents.market_intelligence import constants
    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", True)


@pytest.mark.asyncio
async def test_f3_fallback_fill_checker_failure_is_surfaced(monkeypatch, sinks, live_mode):
    from agents.market_intelligence import scheduler as sched
    from agents.market_intelligence.broker import trade_stream, order_manager
    monkeypatch.setattr(trade_stream, "get_stream_status",
                        lambda: {"healthy": False, "task_alive": False})
    monkeypatch.setattr(order_manager, "check_fills",
                        AsyncMock(side_effect=RuntimeError("alpaca 500")))

    await sched._check_fills_job()                     # still swallows — no raise

    rows = sinks.rows(JOB_FAILED_ERROR)
    assert len(rows) == 1 and "job=check_fills " in rows[0][1]
    assert len(sinks.telegrams) == 1
    assert "check_fills" in sinks.telegrams[0]
    assert "UNOBSERVED" in sinks.telegrams[0]          # consequence-first framing
    assert "alpaca 500" in sinks.telegrams[0]


@pytest.mark.asyncio
async def test_f3_stream_health_watchdog_failure_is_surfaced(monkeypatch, sinks, live_mode):
    from agents.market_intelligence import scheduler as sched
    from agents.market_intelligence.broker import trade_stream

    def _boom():
        raise KeyError("task_alive")

    monkeypatch.setattr(trade_stream, "get_stream_status", _boom)

    await sched._stream_health_watchdog()

    rows = sinks.rows(JOB_FAILED_ERROR)
    assert len(rows) == 1 and "job=stream_health_watchdog " in rows[0][1]
    assert len(sinks.telegrams) == 1
    assert "RESTARTS a dead trade stream" in sinks.telegrams[0]


@pytest.mark.asyncio
async def test_f3_watchdog_pages_once_per_window(monkeypatch, sinks, live_mode):
    """Every 5 minutes all session = 78 fires; one page, 78 rows."""
    from agents.market_intelligence import scheduler as sched
    from agents.market_intelligence.broker import trade_stream

    def _boom():
        raise KeyError("task_alive")

    monkeypatch.setattr(trade_stream, "get_stream_status", _boom)
    for _ in range(5):
        await sched._stream_health_watchdog()
    assert len(sinks.rows(JOB_FAILED_ERROR)) == 5
    assert len(sinks.telegrams) == 1


# ── F4 — the 15-min reconcile losing a whole account mode ─────────────────────

@pytest.fixture
def reconcile_env(monkeypatch):
    from agents.market_intelligence.broker import order_manager as om
    om._mode_reconcile_consecutive_failures.clear()
    audit, tg = [], []

    async def _log(event_type, summary, detail=""):
        audit.append((event_type, summary, detail))

    async def _send(text, **kw):
        tg.append(text)
        return True

    monkeypatch.setattr(om, "log_audit_event", _log)
    monkeypatch.setattr(om, "send_telegram_message", _send)
    monkeypatch.setattr(om, "active_account_modes", lambda: ["paper", "live"])

    async def _reconcile(mode, lookback_days=90):
        if mode == "live":
            raise PermissionError("403 forbidden: live key revoked")
        return {"examined": 4, "updated": 1, "errors": 0}

    monkeypatch.setattr(om, "reconcile_order_states", _reconcile)
    return om, audit, tg


@pytest.mark.asyncio
async def test_f4_whole_mode_failure_writes_a_row_every_time_pages_at_third(reconcile_env):
    om, audit, tg = reconcile_env
    results = [await om.reconcile_all_modes(lookback_days=90) for _ in range(3)]

    # original aggregate contract preserved: paper counted, live counted as 1 error
    assert all(r == {"examined": 4, "updated": 1, "errors": 1} for r in results)
    rows = [r for r in audit if r[0] == ORDER_STATUS_RECONCILE_MODE_ERROR]
    assert len(rows) == 3
    assert ORDER_STATUS_RECONCILE_MODE_ERROR.endswith("_error")
    assert all("account_mode=live" in r[1] for r in rows)
    assert [json.loads(r[2])["consecutive_failures"] for r in rows] == [1, 2, 3]
    assert [("tg=1" in r[1]) for r in rows] == [False, False, True]
    assert len(tg) == 1
    assert "LIVE ORDER RECONCILE DOWN" in tg[0] and "UNWATCHED" in tg[0]
    assert "403 forbidden" in tg[0]
    # counter reset on the page → the NEXT page needs another 3 (natural dedup)
    assert om._mode_reconcile_consecutive_failures["live"] == 0


@pytest.mark.asyncio
async def test_f4_success_resets_the_mode_counter(monkeypatch, reconcile_env):
    om, audit, tg = reconcile_env
    await om.reconcile_all_modes()
    await om.reconcile_all_modes()
    assert om._mode_reconcile_consecutive_failures["live"] == 2

    async def _ok(mode, lookback_days=90):
        return {"examined": 1, "updated": 0, "errors": 0}

    monkeypatch.setattr(om, "reconcile_order_states", _ok)
    await om.reconcile_all_modes()
    assert om._mode_reconcile_consecutive_failures["live"] == 0
    assert tg == []                                      # 2 then recovery: never paged


@pytest.mark.asyncio
async def test_f4_paper_mode_is_never_blamed_for_live(reconcile_env):
    om, audit, tg = reconcile_env
    await om.reconcile_all_modes()
    assert "paper" not in om._mode_reconcile_consecutive_failures or \
        om._mode_reconcile_consecutive_failures["paper"] == 0
    assert all("account_mode=paper" not in r[1] for r in audit)
