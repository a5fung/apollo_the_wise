"""2026-11-19 — send_telegram_message retries transient network errors and 429/5xx per chunk.

A HIGH EP alert was lost to ConnectTimeout/ReadTimeout. 3 attempts per chunk, backoff 2 s / 5 s,
429 retry_after honoured (cap 10 s). A delivered chunk is never re-sent. 400 -> plain text intact.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agents.market_intelligence import briefing

CHAT = 42


class _Resp:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {"ok": status_code < 400}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=self)


class _Client:
    def __init__(self, steps, clock=None, costs=()):
        self.clock, self.costs, self.timeouts = clock, list(costs), []
        self.steps = list(steps)
        self.posts: list[dict] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, timeout=None):
        self.posts.append(json)
        self.timeouts.append(timeout)
        if self.clock is not None:
            cost = self.costs.pop(0) if self.costs else 0.0
            # a real httpx timeout caps how long the request can take
            self.clock.t += min(cost, timeout.read) if timeout is not None else cost
        step = self.steps.pop(0) if self.steps else 200
        if isinstance(step, Exception):
            raise step
        if isinstance(step, _Resp):
            return step
        return _Resp(step)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(CHAT))
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID", raising=False)


async def _run(client, text="hello", **kw):
    audit, sleep = AsyncMock(), AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", client), \
         patch.object(briefing, "log_audit_event", audit), \
         patch.object(briefing, "_tg_retry_sleep", sleep):
        ok = await briefing.send_telegram_message(text, **kw)
    return ok, [c.args for c in audit.await_args_list], [c.args[0] for c in sleep.await_args_list]


@pytest.mark.asyncio
async def test_connect_timeout_then_200_delivers_and_logs_retried_row():
    c = _Client([httpx.ConnectTimeout("t"), 200])
    ok, rows, sleeps = await _run(c)
    assert ok is True and len(c.posts) == 2 and sleeps == [1.0]
    retried = [r for r in rows if r[0] == "telegram_send_retried"]
    assert len(retried) == 1
    assert "attempts=2" in retried[0][2] and "ConnectTimeout" in retried[0][2] and f"chat={CHAT}" in retried[0][2]
    assert not [r for r in rows if r[0] == "telegram_send_failed"]


@pytest.mark.asyncio
async def test_read_timeout_three_times_fails_with_attempts_3():
    c = _Client([httpx.ReadTimeout("t")] * 3)
    ok, rows, sleeps = await _run(c)
    assert ok is False and len(c.posts) == 3 and sleeps == [1.0, 3.0]
    failed = [r for r in rows if r[0] == "telegram_send_failed"]
    assert len(failed) == 1 and "attempts=3" in failed[0][2] and "ReadTimeout" in failed[0][2]
    assert not [r for r in rows if r[0] == "telegram_send_retried"]


@pytest.mark.asyncio
async def test_503_then_200_delivers():
    c = _Client([503, 200])
    ok, rows, _ = await _run(c)
    assert ok is True and len(c.posts) == 2
    assert any(r[0] == "telegram_send_retried" and "HTTP503" in r[2] for r in rows)


@pytest.mark.asyncio
async def test_429_honours_retry_after_capped_at_10s():
    c = _Client([_Resp(429, {"ok": False, "parameters": {"retry_after": 3}}),
                 _Resp(429, {"ok": False, "parameters": {"retry_after": 60}}), 200])
    ok, _, sleeps = await _run(c)
    assert ok is True and sleeps == [3.0, 10.0]


@pytest.mark.asyncio
async def test_multichunk_failure_on_chunk2_never_resends_chunk1():
    text = ("a" * 3500 + "\n\n") + ("b" * 3000)
    c = _Client([200, httpx.ConnectError("x"), 200])
    ok, _, _ = await _run(c, text, parse_mode=None)
    assert ok is True and len(c.posts) == 3
    assert c.posts[0]["text"].startswith("a") and "b" not in c.posts[0]["text"]
    assert c.posts[1]["text"] == c.posts[2]["text"] and c.posts[1]["text"].startswith("b")


@pytest.mark.asyncio
async def test_400_path_unchanged_plain_text_retry_no_transient_retry():
    c = _Client([_Resp(400, {"ok": False, "description": "can't parse"}), 200])
    ok, rows, sleeps = await _run(c)
    assert ok is True and len(c.posts) == 2 and sleeps == []
    assert "parse_mode" in c.posts[0] and "parse_mode" not in c.posts[1]
    assert [r[0] for r in rows] == ["telegram_markdown_fallback"]


@pytest.mark.asyncio
async def test_non_transient_4xx_is_not_retried():
    c = _Client([403])
    ok, rows, sleeps = await _run(c)
    assert ok is False and len(c.posts) == 1 and sleeps == []
    assert any(r[0] == "telegram_send_failed" for r in rows)


class _Clock:
    def __init__(self):
        self.t = 0.0


async def _run_clocked(client, clock):
    audit = AsyncMock()

    async def _sleep(s):
        clock.t += s
        slept.append(s)

    slept: list[float] = []
    with patch.object(briefing.httpx, "AsyncClient", client), \
         patch.object(briefing, "log_audit_event", audit), \
         patch.object(briefing, "_tg_clock", lambda: clock.t), \
         patch.object(briefing, "_tg_retry_sleep", _sleep):
        ok = await briefing.send_telegram_message("hello")
    return ok, slept, [c.args for c in audit.await_args_list]


@pytest.mark.asyncio
async def test_a_15s_read_timeout_leaves_budget_for_one_short_retry_only():
    clk = _Clock()
    c = _Client([httpx.ReadTimeout("t")] * 3, clock=clk, costs=[15.0, 4.0, 4.0])
    ok, slept, rows = await _run_clocked(c, clk)
    # attempt 1 burns 15 s; after the 1 s backoff 4 s remain -> a 2nd attempt with a 4 s timeout;
    # that burns 4 s (t=20) so no budget remains for a 3rd.
    assert ok is False and len(c.posts) == 2 and slept == [1.0]
    assert c.timeouts[0] is None and c.timeouts[1].read == pytest.approx(4.0)
    assert clk.t <= briefing._TG_RETRY_BUDGET_S + 1e-9
    assert any(r[0] == "telegram_send_failed" and "attempts=2" in r[2] for r in rows)


@pytest.mark.asyncio
async def test_total_simulated_wait_never_exceeds_budget_on_a_full_outage():
    clk = _Clock()
    c = _Client([httpx.ConnectTimeout("t")] * 3, clock=clk, costs=[15.0, 15.0, 15.0])
    ok, _, _ = await _run_clocked(c, clk)
    assert ok is False and len(c.posts) == 2 and clk.t <= briefing._TG_RETRY_BUDGET_S
    clk2 = _Clock()
    c2 = _Client([httpx.ConnectError("x")] * 3, clock=clk2, costs=[0.1, 0.1, 0.1])
    ok2, slept2, _ = await _run_clocked(c2, clk2)
    assert ok2 is False and len(c2.posts) == 3 and slept2 == [1.0, 3.0]
    assert clk2.t <= briefing._TG_RETRY_BUDGET_S


@pytest.mark.asyncio
async def test_fast_blip_is_still_retried_within_budget():
    clk = _Clock()
    c = _Client([httpx.ConnectError("x"), 200], clock=clk, costs=[0.1, 0.1])
    ok, slept, rows = await _run_clocked(c, clk)
    assert ok is True and slept == [1.0] and any(r[0] == "telegram_send_retried" for r in rows)
