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
  esc `error_html(...)` -> the raw `str(error)` in core/notifications.py::notify_job_failure
      → test_notify_job_failure_survives_underscores FAIL (an unescaped `<` / `&` reaches the
      HTML parser; #121 review 2026-10-01 replaced the Markdown `md_escape` with `esc()`).
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
async def test_notify_job_failure_survives_underscores(monkeypatch):
    """Three underscores (odd) inside `_..._` italics 400'd the send and dropped the alert
    (health_checks.py's recorder guard documents the same trap). The page is built as HTML now
    (#121 review 2026-10-01), so the underscores need no escaping at all: they go out as written,
    with no backslash anywhere, and the `<` / `&` that WOULD break HTML are entity-escaped."""
    sent = []

    async def _owner(text, **kw):
        sent.append((text, kw))

    monkeypatch.setattr(notifications, "notify_owner", _owner)
    await notifications.notify_job_failure(
        "stuck_fill_watchdog", 'column "stop_order_id" does_not exist <x> & y\nsecond line')
    text, kw = sent[0]
    assert kw["html"] is True                              # already HTML: never converted twice
    body = text.split("\n", 1)[1]
    assert body.startswith("<i>") and body.endswith("</i>")
    inner = body[3:-4]
    assert "stop_order_id" in inner and "does_not exist" in inner
    assert "\\" not in inner                               # no escape backslashes
    assert "&lt;x&gt; &amp; y" in inner                    # the bytes that 400 HTML are escaped
    assert "\n" not in inner                               # italics cannot span lines


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
    # #121 (2026-10-01): the page rides the HTML layer; the plain retry is the tag-stripped
    # backstop and still reads as words with the identifier's underscores intact.
    assert posts[0]["parse_mode"] == "HTML"
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


# ── #635 — the naked-position / stop-ack watchdog DEATH pages buzz; the rest stay silent ──
# Operator-approved 2026-09-13 (the split, not the flip-everything option). The
# alerts those watchdogs EMIT already buzz — `briefing.send_telegram_message`
# sends no `disable_notification` key — so the only silent page was the one that
# says the watchdog itself DIED, and that page comes out of `notify_owner`.
#
# The fixture below leaves `record_job_failure`, `notify_job_failure` and
# `notify_owner` REAL and replaces only the DB sinks and the httpx wire, so the
# assertion is on the JSON Telegram would receive from the REAL producer. The
# `sinks` fixture above stubs `notify_job_failure`; that seam would let a fixture
# decide the payload (the #649 lesson, CLAUDE.md 2026-09-12), so it is not used here.

_LOUD_SLOTS = ("post_close", "late", "evening")


@pytest.fixture
def wire(monkeypatch):
    """Real funnel, captured wire. Returns the list of JSON payloads posted."""
    posts: list[dict] = []

    class _Resp:
        status_code = 200
        text = ""

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **kw):
            posts.append(json)
            return _Resp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    s = _Sinks()
    import agents.market_intelligence.db as db
    from agents.market_intelligence import scheduler as sch
    monkeypatch.setattr(db, "log_audit_event", s.log_audit_event)
    monkeypatch.setattr(db, "get_audit_log", s.get_audit_log)
    monkeypatch.setattr(sch, "log_audit_event", s.log_audit_event)
    monkeypatch.setattr(job_audit, "_last_job_failure_alert_ts", {})
    _wire_job_runs(monkeypatch)
    return posts


async def _boom():
    raise RuntimeError("watchdog exploded")


@pytest.mark.asyncio
@pytest.mark.parametrize("job_id", ["stop_ack_timeout_watchdog", "stuck_fill_watchdog"])
async def test_635_a_no_handler_watchdog_death_buzzes(monkeypatch, wire, job_id):
    """The two watchdogs with no handler of their own page from audit_run's generic
    branch — the ONLY place their death can be routed. Same wording as before;
    only the sound bit changes."""
    from core.job_audit import audit_wrap
    with pytest.raises(RuntimeError):
        await audit_wrap(_boom, job_id)()
    assert len(wire) == 1
    assert wire[0]["disable_notification"] is False
    assert wire[0]["text"].startswith(f"🚨 <b>Scheduled job failed</b>: <code>{job_id}</code>\n")
    assert "watchdog exploded" in wire[0]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("job_id", ["crypto_nightly_ingest", "theme_quality_check"])
async def test_635_an_ordinary_no_handler_job_death_stays_silent(monkeypatch, wire, job_id):
    from core.job_audit import audit_wrap
    with pytest.raises(RuntimeError):
        await audit_wrap(_boom, job_id)()
    assert len(wire) == 1
    assert wire[0]["disable_notification"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", _LOUD_SLOTS)
async def test_635_a_dead_coverage_slot_buzzes(monkeypatch, wire, slot):
    """#646/#649 bare-window slots: the handler's own except → the real notify chain."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import constants as const
    from agents.market_intelligence.broker import order_manager as om
    monkeypatch.setattr(const, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(om, "check_position_coverage",
                        AsyncMock(side_effect=RuntimeError("broker read blew up")))
    await sch._coverage_watch_job(slot)
    assert len(wire) == 1
    assert wire[0]["disable_notification"] is False
    assert wire[0]["text"].startswith(f"🚨 <b>Scheduled job failed</b>: <code>coverage_watch_{slot}</code>\n")


@pytest.mark.asyncio
async def test_635_the_dead_15min_coverage_detector_buzzes(monkeypatch, wire):
    """#527's market-hours detector. The clock is pinned inside its window so the
    guard admits the run and the detector's failure reaches the real notify chain."""
    from datetime import datetime as _real_dt
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import constants as const
    from agents.market_intelligence.broker import order_manager as om

    class _Clock(_real_dt):
        @classmethod
        def now(cls, tz=None):
            return _real_dt(2026, 9, 14, 10, 0, tzinfo=tz)

    monkeypatch.setattr(sch, "datetime", _Clock)
    monkeypatch.setattr(const, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(om, "check_position_coverage",
                        AsyncMock(side_effect=RuntimeError("broker read blew up")))
    await sch._position_coverage_check_job()
    assert len(wire) == 1
    assert wire[0]["disable_notification"] is False
    assert wire[0]["text"].startswith("🚨 <b>Scheduled job failed</b>: <code>position_coverage_check</code>\n")


@pytest.mark.asyncio
@pytest.mark.parametrize("handler, job_id", [
    ("_naked_position_pre_close_check_job", "naked_position_pre_close_check"),
    ("_naked_position_post_refresh_check_job", "naked_position_post_refresh_check"),
])
async def test_635_a_dead_l1_naked_position_check_buzzes(monkeypatch, wire, handler, job_id):
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import system_audit
    monkeypatch.setattr(system_audit, "run_naked_position_check",
                        AsyncMock(side_effect=RuntimeError("invariant query died")))
    await getattr(sch, handler)()
    assert len(wire) == 1
    assert wire[0]["disable_notification"] is False
    assert wire[0]["text"].startswith(f"🚨 <b>Scheduled job failed</b>: <code>{job_id}</code>\n")


@pytest.mark.asyncio
async def test_635_a_dead_repair_job_stays_silent(monkeypatch, wire):
    """The judgement call, pinned: the 21:00 REPAIR's death is silent. Its result is
    verified ten minutes later by the 21:10 slot, whose own death now buzzes and whose
    "still unprotected" page already did."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence import constants as const
    from agents.market_intelligence.broker import order_manager as om
    monkeypatch.setattr(const, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(om, "sync_positions",
                        AsyncMock(side_effect=RuntimeError("sync died")))
    await sch._evening_position_backstop_job()
    assert len(wire) == 1
    assert wire[0]["disable_notification"] is True
    assert wire[0]["text"].startswith("🚨 <b>Scheduled job failed</b>: <code>evening_position_backstop</code>\n")


@pytest.mark.asyncio
async def test_635_a_loud_page_stays_loud_on_the_plain_text_retry(monkeypatch):
    """A loud page that 400s on Markdown is re-sent plain — and must still buzz.
    Before #635 both sends hardcoded the silent bit independently."""
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
    await notifications.notify_job_failure("stop_ack_timeout_watchdog", "bad _ text")
    assert [p["disable_notification"] for p in posts] == [False, False]


@pytest.mark.asyncio
async def test_635_startup_and_direct_owner_pages_are_unchanged(monkeypatch, wire):
    """The other two producers on the funnel keep today's behaviour byte-for-byte."""
    import core.confirmations as confirmations
    monkeypatch.setattr(confirmations, "get_redis",
                        AsyncMock(side_effect=RuntimeError("no redis in tests")))
    await notifications.notify_startup({"market": (True, "ok")})
    await notifications.notify_owner("🔶 *2 job run(s) marked interrupted*")
    assert [p["disable_notification"] for p in wire] == [True, True]


def test_635_every_loud_job_is_one_the_scheduler_really_registers(monkeypatch):
    """A renamed job id would silently drop out of the loud set — the unfireable-gate
    class. Pin the set against what start_scheduler ACTUALLY registers, not a manifest."""
    from tests.test_job_partition import _really_registered_job_ids
    registered = _really_registered_job_ids(monkeypatch)
    missing = notifications.LOUD_FAILURE_JOBS - registered
    assert not missing, f"in LOUD_FAILURE_JOBS but never registered: {sorted(missing)}"


def test_635_the_loud_set_is_exactly_the_two_approved_families():
    """He approved two families — the naked-position detectors and the stop-ack
    watchdog — and nothing else. A repair job or a heartbeat added here is a
    widening of that decision, which is his to make."""
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS,
    )
    loud = notifications.LOUD_FAILURE_JOBS
    assert loud <= EXECUTION_OWNED_JOB_IDS | INTELLIGENCE_OWNED_JOB_IDS
    for repair_or_heartbeat in ("evening_position_backstop", "stop_coverage_repair_retry",
                                "post_close_stop_refresh", "morning_stop_refresh",
                                "evening_verify_heartbeat"):
        assert repair_or_heartbeat not in loud
    assert {"stop_ack_timeout_watchdog", "stuck_fill_watchdog"} <= loud


# ── #635 Tier 2/3 (2026-09-30) — F13: the nightly state-alert step ────────────────────────
# SoT: docs/analysis/silent_failure_taxonomy_2026-07-23.md §2 F13. The regime / theme
# deterioration Telegrams come out of nightly step 8; a failure there was `logger.error` only,
# so they could stop arriving with no trace that survives a restart. Surfaced through
# `record_job_failure` (audit row + deduped Telegram) — NOT by appending to the pull's
# `failures` list, which would skip `log_job_run(JOB_NIGHTLY_DATA_PULL)` and make
# `check_missed_jobs` re-run the whole pull on the next evening restart.
#
# MUTATION CHECK (run by hand 2026-09-30): delete the `await record_job_failure(...)` in
# scheduler._state_alerts_step -> the two failure tests below FAIL (no row, no page).

@pytest.mark.asyncio
async def test_f13_a_failed_state_alert_step_is_surfaced_and_still_swallowed(monkeypatch, sinks):
    from datetime import date
    from agents.market_intelligence import scheduler as sched
    monkeypatch.setattr(sched, "detect_state_changes", AsyncMock(
        side_effect=RuntimeError('relation "mi_theme_snapshots" does not exist')))
    parts: list = []

    await sched._state_alerts_step(date(2026, 9, 30), [], parts)   # swallowed — no raise

    assert parts == []                                   # summary untouched, as before
    rows = sinks.rows(JOB_FAILED_ERROR)
    assert len(rows) == 1 and "job=nightly_state_alerts " in rows[0][1]
    assert len(sinks.telegrams) == 1
    page = sinks.telegrams[0]
    assert "state-change alerts did NOT go out" in page
    assert "mi_theme_snapshots" in page


@pytest.mark.asyncio
async def test_f13_a_failing_send_is_surfaced_too(monkeypatch, sinks):
    from datetime import date
    from agents.market_intelligence import scheduler as sched
    monkeypatch.setattr(sched, "detect_state_changes", AsyncMock(return_value=([{"x": 1}], {}, {})))
    monkeypatch.setattr(sched, "send_state_alerts", AsyncMock(side_effect=RuntimeError("telegram 502")))
    parts: list = []

    await sched._state_alerts_step(date(2026, 9, 30), [], parts)

    assert parts == []                                   # nothing was sent, so nothing is claimed
    assert len(sinks.rows(JOB_FAILED_ERROR)) == 1
    assert "telegram 502" in sinks.telegrams[0]


@pytest.mark.asyncio
async def test_f13_the_success_path_is_byte_identical_and_silent(monkeypatch, sinks):
    from datetime import date
    from agents.market_intelligence import scheduler as sched
    send = AsyncMock()
    monkeypatch.setattr(sched, "detect_state_changes",
                        AsyncMock(return_value=([{"a": 1}, {"b": 2}], {"t": 1}, {"t": 0})))
    monkeypatch.setattr(sched, "send_state_alerts", send)
    parts: list = []

    await sched._state_alerts_step(date(2026, 9, 30), ["cl1"], parts)

    send.assert_awaited_once_with([{"a": 1}, {"b": 2}], ["cl1"], {"t": 1}, {"t": 0})
    assert parts == ["3 state alerts"]                   # 2 alerts + 1 changelog line
    assert sinks.audit_rows == [] and sinks.telegrams == []


def test_f13_the_nightly_pull_routes_step_8_through_the_helper():
    """Wiring check. Driving the whole ~600-line pull needs two dozen collaborators mocked; the
    step's behaviour is exercised directly above, this only proves the pull still calls it (an
    inline copy of the old block would quietly bring the silent swallow back). Structural - the
    call set of the function, read off its AST - not a text match."""
    from tests._audit_emitters import names_called_in
    called = names_called_in("agents/market_intelligence/scheduler.py", "_nightly_data_pull")
    assert "_state_alerts_step" in called
    assert "detect_state_changes" not in called       # no inlined copy of the old block


# ── #635 Tier 2/3 (2026-09-30) — commit B: the money-path surfaces (F6, F8-F11) ─────────────
# Observability only. Every test drives the REAL failing path - the real `run_ep_scan` (via the
# test_624 harness), `_process_entry_fill`, `check_fills`, `read_breaker_state`,
# `_start_one_stream` - with only the leaf sinks captured, and asserts BOTH that the new
# audit row / Telegram appears AND that the original control flow is unchanged.
#
# MUTATION CHECKS (run by hand 2026-09-30, recorded here, not re-run by CI): each of these turns
# the named tests RED.
#   F6   delete the `await log_audit_event("ep_repoll_upgrade_error", ...)` in ep_detector.py
#   F8   delete the `_n_parse_dropped += 1` counter / the post-loop audit dispatch
#   F9   delete `_schedule_breaker_read_alert(mode, e)` in drawdown_breaker.read_breaker_state
#   F10  delete either `await note_partial_fill_close_failed(...)` call
#   F11  delete `await _note_sdk_shape_guard_tripped(account_mode)` in trade_stream

import asyncio  # noqa: E402
from datetime import datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from agents.market_intelligence.audit_events import (  # noqa: E402
    DRAWDOWN_BREAKER_READ_ERROR,
    PARTIAL_FILL_CLOSE_ERROR,
    TRADE_STREAM_SDK_SHAPE_ERROR,
)
from tests._byte_identity import assert_byte_identical  # noqa: E402


async def _drain(*task_sets):
    """Await every fire-and-forget task the code under test parked in `task_sets`."""
    for _ in range(5):
        pending = [t for s in task_sets for t in list(s) if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


def _pending_only(rows):
    """`conn.fetch` double for `check_fills`: the pending-entry query gets `rows`, every other
    query the function goes on to run (Day-1 re-entry polling) gets none."""
    async def _fetch(sql, *a, **k):
        return list(rows) if "order_placed" in sql else []
    return _fetch


def _capture_sinks(monkeypatch, *modules):
    """Replace `log_audit_event` / `send_telegram_message` on each module that has them."""
    audit, tg = [], []

    async def _log(event_type, summary, detail=""):
        audit.append((event_type, summary, detail))

    async def _send(text, **kw):
        tg.append(text)
        return True

    for m in modules:
        if hasattr(m, "log_audit_event"):
            monkeypatch.setattr(m, "log_audit_event", _log)
        if hasattr(m, "send_telegram_message"):
            monkeypatch.setattr(m, "send_telegram_message", _send)
    return audit, tg


# ── F11 — TradingStream SDK-shape guard ───────────────────────────────────────────────────

class _StreamWithoutRunForever:
    """alpaca-py after a (hypothetical) SDK change: no `_run_forever` coroutine."""

    def __init__(self, *a, **k):
        pass

    def subscribe_trade_updates(self, handler):
        pass


class _HealthyStream(_StreamWithoutRunForever):
    async def _run_forever(self):
        return None


@pytest.fixture
def stream_env(monkeypatch):
    from agents.market_intelligence.broker import trade_stream as ts
    ts._sdk_shape_paged.clear()
    for m in ("paper", "live"):
        ts._trading_streams.pop(m, None)
        ts._stream_tasks.pop(m, None)
        monkeypatch.setenv(f"ALPACA_{m.upper()}_API_KEY", "k")
        monkeypatch.setenv(f"ALPACA_{m.upper()}_SECRET_KEY", "s")
    audit, tg = _capture_sinks(monkeypatch, ts)
    return ts, audit, tg


@pytest.mark.asyncio
async def test_f11_a_tripped_sdk_guard_is_audited_and_paged_once_per_mode(monkeypatch, stream_env):
    ts, audit, tg = stream_env
    monkeypatch.setattr(ts, "ReasonPreservingTradingStream", _StreamWithoutRunForever)

    await ts._start_one_stream("paper")
    await ts._start_one_stream("paper")          # the watchdog re-enters every few minutes
    await ts._start_one_stream("live")           # a different mode is its own page

    # behaviour unchanged: NO stream registered, polling stays the only fill observer
    assert ts._trading_streams == {} and ts._stream_tasks == {}
    rows = [r for r in audit if r[0] == TRADE_STREAM_SDK_SHAPE_ERROR]
    assert len(rows) == 3 and TRADE_STREAM_SDK_SHAPE_ERROR.endswith("_error")
    assert ["tg=1" in r[1] for r in rows] == [True, False, True]
    assert len(tg) == 2                                   # paper once + live once
    assert "WebSocket fill stream" in tg[0] and "polling fallback" in tg[0]
    assert "PAPER" in tg[0].upper() or "paper" in tg[0]


@pytest.mark.asyncio
async def test_f11_a_healthy_sdk_shape_raises_nothing(monkeypatch, stream_env):
    ts, audit, tg = stream_env
    monkeypatch.setattr(ts, "ReasonPreservingTradingStream", _HealthyStream)

    async def _no_loop(account_mode):        # do not start a real reconnect loop
        return None

    monkeypatch.setattr(ts, "_run_stream_with_monitoring", _no_loop)
    await ts._start_one_stream("paper")
    await _drain(ts._stream_tasks.values())
    assert "paper" in ts._trading_streams               # registered exactly as before
    assert audit == [] and tg == []
    ts._trading_streams.pop("paper", None)
    ts._stream_tasks.pop("paper", None)


# ── F10 — partial-fill-too-small close failure ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_f10_ws_path_close_failure_is_surfaced_and_the_row_is_still_closed(monkeypatch):
    from agents.market_intelligence.broker import trade_stream as ts, order_manager as om
    audit, tg = _capture_sinks(monkeypatch, ts, om)
    monkeypatch.setattr(ts.alpaca, "close_position",
                        AsyncMock(side_effect=RuntimeError("position does not exist")))
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    trade = {"id": 11, "ticker": "TINY", "entry_shares": 100}

    await ts._process_entry_fill(trade, SimpleNamespace(id="o1"), 50.0, 2.0, pool, "live")

    rows = [r for r in audit if r[0] == PARTIAL_FILL_CLOSE_ERROR]
    assert len(rows) == 1 and PARTIAL_FILL_CLOSE_ERROR.endswith("_error")
    assert "TINY" in rows[0][1] and "account_mode=live" in rows[0][1]
    d = json.loads(rows[0][2])
    assert d["trade_id"] == 11 and d["where"] == "trade_stream._process_entry_fill"
    assert len(tg) == 1 and "TINY" in tg[0] and "NOT closed" in tg[0]
    assert "position does not exist" in tg[0]
    # ORIGINAL CONTROL FLOW: the row is still marked closed, the function still returns
    sql, *args = conn.execute.await_args.args
    assert "status = 'closed'" in sql and "Partial fill too small" in sql and args == [11]


@pytest.mark.asyncio
async def test_f10_polling_path_close_failure_is_surfaced_and_the_row_is_still_closed(monkeypatch):
    from agents.market_intelligence.broker import order_manager as om
    audit, tg = _capture_sinks(monkeypatch, om)
    pool, conn = make_mock_pool()
    conn.fetch = _pending_only([{
        "id": 12, "ticker": "TINY", "entry_order_id": "e1", "entry_shares": 100,
        "orb_low": 9.0, "orb_high": 10.0, "stop_price": 9.0, "entry_attempt": 1,
        "account_mode": "paper",
    }])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "get_order", AsyncMock(return_value={
        "status": "filled", "filled_avg_price": 50.0, "filled_qty": 2.0}))
    monkeypatch.setattr(om.alpaca, "close_position",
                        AsyncMock(side_effect=RuntimeError("403 forbidden")))
    upd = AsyncMock()
    monkeypatch.setattr(om, "_update_trade_status", upd)

    results = await om.check_fills()

    assert results == [{"ticker": "TINY", "action": "partial_cancelled"}]   # unchanged
    upd.assert_awaited_once_with(12, "closed", skip_reason="partial_fill_too_small")
    rows = [r for r in audit if r[0] == PARTIAL_FILL_CLOSE_ERROR]
    assert len(rows) == 1 and json.loads(rows[0][2])["where"] == "check_fills"
    assert len(tg) == 1 and "403 forbidden" in tg[0]


@pytest.mark.asyncio
async def test_f10_a_successful_close_raises_no_alarm(monkeypatch):
    from agents.market_intelligence.broker import order_manager as om
    audit, tg = _capture_sinks(monkeypatch, om)
    pool, conn = make_mock_pool()
    conn.fetch = _pending_only([{
        "id": 13, "ticker": "TINY", "entry_order_id": "e1", "entry_shares": 100,
        "orb_low": 9.0, "orb_high": 10.0, "stop_price": 9.0, "entry_attempt": 1,
        "account_mode": "paper"}])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om.alpaca, "get_order", AsyncMock(return_value={
        "status": "filled", "filled_avg_price": 50.0, "filled_qty": 2.0}))
    monkeypatch.setattr(om.alpaca, "close_position", AsyncMock(return_value={"id": "x"}))
    monkeypatch.setattr(om, "_update_trade_status", AsyncMock())
    await om.check_fills()
    assert audit == [] and tg == []


# ── F9 — read_breaker_state: ALERT-ONLY, fail-open direction unchanged ───────────────────

@pytest.fixture
def breaker_env(monkeypatch):
    from agents.market_intelligence.broker import drawdown_breaker as dd
    from agents.market_intelligence import briefing
    dd._last_breaker_read_alert_ts.clear()
    audit, tg = _capture_sinks(monkeypatch, dd, briefing)
    monkeypatch.setattr(dd, "get_safeguard_state",
                        AsyncMock(side_effect=ConnectionError("pool closed")))
    return dd, audit, tg


@pytest.mark.asyncio
async def test_f9_a_failed_read_still_fails_open_and_is_audited_and_paged(breaker_env):
    dd, audit, tg = breaker_env

    state = await dd.read_breaker_state("live")

    assert state == "OK"                                  # THE LINE: direction unchanged
    await _drain(dd._ALERT_BG_TASKS)
    rows = [r for r in audit if r[0] == DRAWDOWN_BREAKER_READ_ERROR]
    assert len(rows) == 1 and DRAWDOWN_BREAKER_READ_ERROR.endswith("_error")
    assert "account_mode=live" in rows[0][1] and "pool closed" in rows[0][1]
    assert "tg=1" in rows[0][1]
    assert len(tg) == 1
    assert "DRAWDOWN BREAKER READ FAILED" in tg[0] and "NOT limited" in tg[0]


@pytest.mark.asyncio
async def test_f9_the_page_is_deduped_per_mode_but_every_failure_leaves_a_row(breaker_env):
    dd, audit, tg = breaker_env
    for _ in range(3):
        assert await dd.read_breaker_state("live") == "OK"
    assert await dd.read_breaker_state("paper") == "OK"
    await _drain(dd._ALERT_BG_TASKS)

    rows = [r for r in audit if r[0] == DRAWDOWN_BREAKER_READ_ERROR]
    assert len(rows) == 4
    assert len(tg) == 2                                   # live once, paper once
    assert sum("tg=1" in r[1] for r in rows) == 2


@pytest.mark.asyncio
async def test_f9_the_alert_never_delays_the_entry_path(monkeypatch, breaker_env):
    """The audit write is deliberately BLOCKED: `read_breaker_state` must still return at once.
    (The DB that just failed is probably the DB the audit row writes to.)"""
    dd, audit, tg = breaker_env
    gate = asyncio.Event()

    async def _slow_audit(event_type, summary, detail=""):
        await gate.wait()
        audit.append((event_type, summary, detail))

    monkeypatch.setattr(dd, "log_audit_event", _slow_audit)
    state = await asyncio.wait_for(dd.read_breaker_state("live"), timeout=1.0)
    assert state == "OK" and audit == []                  # returned while the audit is still pending
    gate.set()
    await _drain(dd._ALERT_BG_TASKS)
    assert len([r for r in audit if r[0] == DRAWDOWN_BREAKER_READ_ERROR]) == 1


@pytest.mark.asyncio
async def test_f9_a_dead_audit_and_dead_telegram_cannot_break_the_read(monkeypatch, breaker_env):
    dd, audit, tg = breaker_env
    from agents.market_intelligence import briefing
    monkeypatch.setattr(dd, "log_audit_event", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(briefing, "send_telegram_message",
                        AsyncMock(side_effect=RuntimeError("tg down")))
    assert await dd.read_breaker_state("live") == "OK"
    await _drain(dd._ALERT_BG_TASKS)                      # no unhandled task exception


@pytest.mark.asyncio
async def test_f9_healthy_reads_are_silent_and_a_real_state_still_wins(monkeypatch, breaker_env):
    dd, audit, tg = breaker_env
    monkeypatch.setattr(dd, "get_safeguard_state", AsyncMock(return_value={"state": "BLOCK"}))
    assert await dd.read_breaker_state("live") == "BLOCK"
    monkeypatch.setattr(dd, "get_safeguard_state", AsyncMock(return_value=None))
    assert await dd.read_breaker_state("live") == "OK"
    await _drain(dd._ALERT_BG_TASKS)
    assert audit == [] and tg == []


# ── F6 / F8 — inside the real run_ep_scan (test_624's end-to-end harness) ────────────────

_ET_NY = ZoneInfo("America/New_York")


@pytest.mark.asyncio
async def test_f8_parse_drops_are_audited_past_the_threshold_and_change_nothing(monkeypatch):
    from tests.test_624_lowcap_lane import _run_scan_once
    base_sink: list = []
    base = await _run_scan_once(monkeypatch, lane_mode="off", audit_sink=base_sink)

    # `prevDay: None` makes `snap.get("prevDay", {}).get("c")` raise AttributeError - the exact
    # "exception in the per-ticker candidate build" shape the bulkhead swallows.
    bad = {f"B{i:04d}": {"prevDay": None, "min": {"c": 5.0}} for i in range(60)}
    sink: list = []
    hit = await _run_scan_once(monkeypatch, lane_mode="off", audit_sink=sink, extra_snapshots=bad)

    rows = [r for r in sink if r[0] == "ep_candidate_parse_error"]
    assert len(rows) == 1
    d = json.loads(rows[0][2])
    assert d["n_dropped"] == 60 and d["n_snapshots"] == 83        # 20 fillers + 3 smalls + 60 bad
    assert "AttributeError" in d["first_error"] and len(d["sample_tickers"]) == 5
    assert "60 of" in rows[0][1]
    assert [r for r in base_sink if r[0] == "ep_candidate_parse_error"] == []   # clean scan: silent
    # THE BULKHEAD IS UNCHANGED: the dropped rows alter nothing the scan returns or records
    assert_byte_identical(base[0], hit[0], "results")
    assert_byte_identical(base[1], hit[1], "scan_log rows")
    assert_byte_identical(base[2], hit[2], "alert inserts")


@pytest.mark.asyncio
async def test_f8_a_few_bad_rows_stay_silent(monkeypatch):
    from tests.test_624_lowcap_lane import _run_scan_once
    bad = {f"B{i:04d}": {"prevDay": None, "min": {"c": 5.0}} for i in range(10)}
    sink: list = []
    await _run_scan_once(monkeypatch, lane_mode="off", audit_sink=sink, extra_snapshots=bad)
    assert [r for r in sink if r[0] == "ep_candidate_parse_error"] == []


@pytest.fixture
def premarket_repoll(monkeypatch):
    """The admit-path harness with the cached-grade RE-POLL window open: a clock before 9:30 ET
    and a primary-subject source that 'arrived after the routine grade'. Returns `arm()`, which
    arms the ticker's re-poll state (the harness resets the grade cache but not this)."""
    import tests.test_624_lowcap_lane as t624
    from agents.market_intelligence import ep_detector
    monkeypatch.setattr(t624, "TICK", datetime(2026, 9, 3, 9, 10, 0, tzinfo=_ET_NY))
    monkeypatch.setattr(ep_detector, "_repoll_shadow_date", t624.SESSION_DATE)
    monkeypatch.setattr(ep_detector, "get_alpaca_news",
                        AsyncMock(return_value=[{"headline": "Big Cap Co wins FDA approval"}]))
    monkeypatch.setattr(ep_detector, "is_primary_subject_news", lambda *a, **k: True)

    def arm(armed=True):
        state = ({t624.ADMIT_TICKER: {"count": 0, "quality": "routine", "logged": False}}
                 if armed else {})
        monkeypatch.setattr(ep_detector, "_repoll_shadow_state", state)
        return state

    return arm


@pytest.mark.asyncio
async def test_f6_a_failed_cached_repoll_is_audited_and_the_scan_carries_on(monkeypatch, premarket_repoll):
    from agents.market_intelligence import ep_detector as ed
    from tests.test_624_lowcap_lane import _run_scan_once, ADMIT_TICKER
    monkeypatch.setattr(ed, "_build_enriched_corpus",
                        AsyncMock(side_effect=RuntimeError("edgar 503 on the content build")))
    # control: the very same premarket scan with NO re-poll armed
    premarket_repoll(armed=False)
    control = await _run_scan_once(monkeypatch, lane_mode="off", admit=True, cached_quality="routine")

    state = premarket_repoll(armed=True)
    sink: list = []
    hit = await _run_scan_once(monkeypatch, lane_mode="off", admit=True, cached_quality="routine",
                               audit_sink=sink)

    rows = [r for r in sink if r[0] == "ep_repoll_upgrade_error"]
    assert len(rows) == 1 and "ep_repoll_upgrade_error".endswith("_error")
    assert rows[0][1].startswith(f"{ADMIT_TICKER}: RuntimeError") and "edgar 503" in rows[0][1]
    d = json.loads(rows[0][2])
    assert d["ticker"] == ADMIT_TICKER and d["path"] == "cached_repoll"
    # the latch was set BEFORE the failing call (unchanged) - which is exactly why the failure
    # must not be silent: the upgrade stays off for the rest of the day
    assert state[ADMIT_TICKER]["logged"] is True
    # distinct from the grading-health event (#543 counts `live_enriched_grade_failed`)
    assert not [r for r in sink if r[0] == "live_enriched_grade_failed"]
    # THE SWALLOW IS UNCHANGED: results, scan log and alert inserts are identical to the control
    assert_byte_identical(control[0], hit[0], "results")
    assert_byte_identical(control[1], hit[1], "scan_log rows")
    assert_byte_identical(control[2], hit[2], "alert inserts")


@pytest.mark.asyncio
async def test_f6_a_healthy_repoll_raises_no_error_row(monkeypatch, premarket_repoll):
    from agents.market_intelligence import ep_detector as ed
    from tests.test_624_lowcap_lane import _run_scan_once
    monkeypatch.setattr(ed, "_build_enriched_corpus", AsyncMock(
        return_value=("routine", "no change", None, None, None, None)))
    premarket_repoll(armed=True)
    sink: list = []
    await _run_scan_once(monkeypatch, lane_mode="off", admit=True, cached_quality="routine",
                         audit_sink=sink)
    assert not [r for r in sink if r[0] == "ep_repoll_upgrade_error"]
    # the trigger really fired (so the negative above is not vacuous): a healthy re-poll logs
    assert [r for r in sink if r[0] == "ep_repoll_shadow"]


