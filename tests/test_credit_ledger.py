"""Proactive Anthropic low-credit ledger (credit_ledger.py, 2026-11-10).

Pins: estimate math + burn choice, threshold, command parsing, dedup (DB-sourced, per ET day),
the no-balance silent path, fail-open, and the WOULD-FAIL case (a balance that SHOULD warn does).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import credit_ledger as cl

_ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 10, 8, 0, tzinfo=_ET)


# ── pure math ───────────────────────────────────────────────────────────────
def test_estimate_subtracts_spend_and_averages_days_with_spend():
    e = cl.compute_estimate(50.0, 8.0, [2.0, 0.0, 4.0, 0.15])  # zero day excluded
    assert e["est_usd"] == pytest.approx(42.0)
    assert e["burn_days_used"] == 3
    assert e["burn_per_day"] == pytest.approx((2.0 + 4.0 + 0.15) / 3)
    assert e["days_left"] == pytest.approx(42.0 / e["burn_per_day"])


def test_no_burn_means_no_days_left():
    e = cl.compute_estimate(20.0, 0.0, [])
    assert e["burn_per_day"] == 0 and e["days_left"] is None


@pytest.mark.parametrize("est,burn,expect", [
    (9.99, 0.0, "low"),          # under the $10 floor
    (10.0, 0.0, None),           # at the floor, no burn
    (24.0, 5.0, "low"),          # under 5 x burn ($25)
    (26.0, 5.0, None),
    (0.0, 1.0, "used_up"),
    (-3.0, 1.0, "used_up"),
])
def test_warning_threshold(est, burn, expect):
    assert cl.warning_reason({"est_usd": est, "burn_per_day": burn}) == expect


def test_text_is_plain_and_actionable():
    est = cl.compute_estimate(20.0, 12.0, [2.0])
    t = cl.warning_text("low", est)
    assert "Anthropic credits low: about $8.00 left, roughly 4.0 days" in t
    assert "/credits <new balance>" in t and "|" not in t
    assert "used up" in cl.warning_text("used_up", cl.compute_estimate(5, 6, [1]))


# ── command parsing ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("task,expect", [
    ("/credits", ("show", None)),
    ("/credits   ", ("show", None)),
    ("/credits 42.50", ("set", 42.5)),
    ("/credits $1,042.5", ("set", 1042.5)),
    ("/credits 0", ("set", 0.0)),
])
def test_parse_ok(task, expect):
    assert cl.parse_credits_arg(task) == expect


@pytest.mark.parametrize("task", ["/credits abc", "/credits -5", "/credits nan", "/credits inf", "/credits 4 2"])
def test_parse_rejects(task):
    mode, msg = cl.parse_credits_arg(task)
    assert mode == "error" and "/credits 42.50" in msg


# ── scheduled check ─────────────────────────────────────────────────────────
class _Ledger:
    def __init__(self, balance=40.0, spent=0.0, daily=(2.0, 2.0), warned_rows=()):
        self.balance, self.spent, self.daily = balance, spent, list(daily)
        self.warned_rows = list(warned_rows)
        self.audit: list[tuple[str, str, dict]] = []
        self.sent: list[str] = []

    async def audit_log(self, event_type=None, since_hours=48, limit=30, **_):
        if event_type == cl.EVENT_BALANCE_RECORDED:
            if self.balance is None:
                return []
            return [{"created_at": NOW, "detail": json.dumps(
                {"usd": self.balance, "as_of": (NOW - timedelta(days=1)).isoformat()})}]
        if event_type == cl.EVENT_LOW_WARNED:
            return self.warned_rows
        return []

    async def log_audit_event(self, event_type, summary, detail=""):
        self.audit.append((event_type, summary, json.loads(detail) if detail else {}))
        return True

    async def send(self, text, **_):
        self.sent.append(text)
        return True


@pytest.fixture
def ledger(monkeypatch):
    def make(**kw):
        L = _Ledger(**kw)
        import agents.market_intelligence.db as db

        async def spent(as_of):
            return L.spent

        async def daily(today):
            return L.daily
        monkeypatch.setattr(db, "get_audit_log", L.audit_log)
        monkeypatch.setattr(db, "log_audit_event", L.log_audit_event)
        monkeypatch.setattr(cl, "fetch_spend_since", spent)
        monkeypatch.setattr(cl, "fetch_daily_spend", daily)
        return L
    return make


@pytest.mark.asyncio
async def test_no_balance_recorded_is_silent_and_writes_nothing(ledger):
    L = ledger(balance=None)
    assert await cl.run_credit_check(NOW, send=L.send) is None
    assert L.sent == [] and L.audit == []


@pytest.mark.asyncio
async def test_would_fail_case_low_balance_warns_once(ledger):
    # $40 recorded, $33 spent since, burn $2/day -> est $7 < max($10, $10): MUST warn.
    L = ledger(balance=40.0, spent=33.0, daily=(2.0, 2.0))
    r = await cl.run_credit_check(NOW, send=L.send)
    assert r["warned"] and r["reason"] == "low"
    assert len(L.sent) == 1 and "about $7.00 left" in L.sent[0]
    kinds = [a[0] for a in L.audit]
    assert kinds == [cl.EVENT_LOW_WARNED, cl.EVENT_CREDIT_CHECK]  # dedup token first, telemetry after


@pytest.mark.asyncio
async def test_healthy_balance_audits_but_does_not_telegram(ledger):
    L = ledger(balance=100.0, spent=5.0, daily=(2.0,))
    r = await cl.run_credit_check(NOW, send=L.send)
    assert r["reason"] is None and not r["warned"] and L.sent == []
    assert [a[0] for a in L.audit] == [cl.EVENT_CREDIT_CHECK]


@pytest.mark.asyncio
async def test_used_up_warns(ledger):
    L = ledger(balance=10.0, spent=12.0, daily=(2.0,))
    r = await cl.run_credit_check(NOW, send=L.send)
    assert r["reason"] == "used_up" and "used up" in L.sent[0]


@pytest.mark.asyncio
async def test_dedup_same_et_day_suppresses_but_next_day_warns(ledger):
    same_day = [{"created_at": NOW.replace(hour=4)}]      # an earlier warning today (ET)
    L = ledger(balance=40.0, spent=35.0, daily=(2.0,), warned_rows=same_day)
    r = await cl.run_credit_check(NOW, send=L.send)
    assert r["reason"] == "low" and not r["warned"] and L.sent == []
    assert [a[0] for a in L.audit] == [cl.EVENT_CREDIT_CHECK]  # telemetry still written

    yesterday = [{"created_at": NOW - timedelta(days=1)}]
    L2 = ledger(balance=40.0, spent=35.0, daily=(2.0,), warned_rows=yesterday)
    assert (await cl.run_credit_check(NOW, send=L2.send))["warned"]


@pytest.mark.asyncio
async def test_db_error_fails_open_and_audits(ledger, monkeypatch):
    L = ledger()

    async def boom(as_of):
        raise RuntimeError("db down")
    monkeypatch.setattr(cl, "fetch_spend_since", boom)
    assert await cl.run_credit_check(NOW, send=L.send) is None   # never raises
    assert L.sent == []
    assert L.audit and L.audit[-1][0] == cl.EVENT_CREDIT_CHECK and "RuntimeError" in L.audit[-1][2]["error"]


# ── wiring ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_slash_dispatch_reaches_handler_and_parity_gate_passes():
    import subprocess
    import sys
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    fake = MagicMock()
    fake._handle_credits_command = AsyncMock(return_value="ok")
    req = MagicMock()
    req.task = "/credits 42.5"
    assert await MarketIntelligenceAgent._handle_slash_command(fake, req) == "ok"
    root = Path(__file__).resolve().parent.parent
    from scripts.preflight_command_parity import TELEGRAM_FILE, parse_bot_commands, parse_command_handlers
    text = TELEGRAM_FILE.read_text(encoding="utf-8")
    assert "credits" in parse_bot_commands(text) and "credits" in parse_command_handlers(text)[1]
    r = subprocess.run([sys.executable, str(root / "scripts/preflight_command_parity.py")],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.asyncio
async def test_handler_records_then_shows_estimate(ledger, monkeypatch):
    from unittest.mock import MagicMock
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    L = ledger(balance=None)
    got = {}
    monkeypatch.setattr(cl, "current_estimate", lambda now=None: _est(None))
    fake = MagicMock()
    fake._ok = lambda request, result: result
    req = MagicMock()
    req.task = "/credits -3"
    assert "negative" in await MarketIntelligenceAgent._handle_credits_command(fake, req)
    req.task = "/credits"
    assert "No Anthropic balance recorded" in await MarketIntelligenceAgent._handle_credits_command(fake, req)
    req.task = "/credits 42.5"
    out = await MarketIntelligenceAgent._handle_credits_command(fake, req)
    assert "Recorded $42.50" in out
    assert L.audit[-1][0] == cl.EVENT_BALANCE_RECORDED and L.audit[-1][2]["usd"] == 42.5


async def _est(v):
    return v


def test_job_registered_intelligence_owned_mon_fri_8_and_18(monkeypatch):
    import asyncio
    from agents.market_intelligence import scheduler as sched
    from tests.test_job_partition import _CapturingScheduler
    assert "credit_check" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "credit_check" not in sched.EXECUTION_OWNED_JOB_IDS
    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    holder = {}
    real = sched._apply_role_partition

    def spy(scheduler, role):
        holder["jobs"] = list(scheduler.get_jobs())
        return real(scheduler, role)
    monkeypatch.setattr(sched, "_apply_role_partition", spy)

    async def go():
        sched.start_scheduler()
    asyncio.run(go())
    job = next(j for j in holder["jobs"] if j.id == "credit_check")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert (fields["hour"], fields["minute"], fields["day_of_week"]) == ("8,18", "0", "mon-fri")
    assert str(job.trigger.timezone) == "America/New_York"
