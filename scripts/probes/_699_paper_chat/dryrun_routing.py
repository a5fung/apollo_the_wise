"""Dry run of the #699 paper-chat switch. NO NETWORK, NO DATABASE, NOTHING SENT.

Why it exists (2026-10-11, "paper alerts go to their own Telegram group"): the switch can only be
seen live on the first real paper alert after the deploy (Monday 2026-10-12 08:25 ET, the #687 paper
test page). After the deploy this proves, the same day and with no market open, that the code each
container actually runs routes by the signed rule. It drives the REAL `briefing.send_telegram_message`
(and the real `constants.paper_chat_id_for`); the only things it replaces are the HTTP client (a
recorder that answers a scripted status per chat id) and `log_audit_event` (so the failure path opens
no database connection).

  docker exec -i apollo-market    python - < scripts/probes/_699_paper_chat/dryrun_routing.py
  docker exec -i apollo-execution python - < scripts/probes/_699_paper_chat/dryrun_routing.py

It sets its OWN fake bot token, main chat (42) and paper chat (-5382801675) for the run and restores
the environment afterwards, so it proves the CODE and says nothing about whether the container's real
`TELEGRAM_PAPER_CHAT_ID` is set — that is the verify-live step (the container prints it below).

PASS prints `DRYRUN PASS` and exits 0. On the PRIOR code (no routing) the paper cases land in the main
chat, so it prints `DRYRUN FAIL` and exits 1 — the broken system cannot print PASS.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock

from agents.market_intelligence import briefing, constants
from shared.telegram_format import md_to_html

MAIN, PAPER = 42, -5382801675
PAPER_TEXT = "📄 PAPER ✅ *FILLED:* ABCD (attempt 1)\nEntry $10.00"
LIVE_TEXT = "💰 LIVE-$ ✅ *FILLED:* ABCD (attempt 1)\nEntry $10.00"
SYSTEM_TEXT = "🚨 *Job FAILED:* `ep_scan` — timeout"


class _Resp:
    def __init__(self, status: int):
        self.status_code = status
        self.text = json.dumps({"ok": status < 400})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Recorder:
    """Stands in for httpx.AsyncClient: records each payload, answers a scripted status per chat."""

    def __init__(self, plan: dict | None = None):
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.posts: list[dict] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        assert "api.telegram.org" in url          # the only URL the sender ever builds
        self.posts.append(json)
        q = self.plan.get(json["chat_id"])
        step = q.pop(0) if q else 200
        if isinstance(step, Exception):
            raise step
        return _Resp(step)

    def chats(self):
        return [p["chat_id"] for p in self.posts]


async def _drive(text, plan=None, **kw):
    rec = _Recorder(plan)
    real_client, real_audit = briefing.httpx.AsyncClient, briefing.log_audit_event
    briefing.httpx.AsyncClient, briefing.log_audit_event = rec, AsyncMock()
    try:
        ok = await briefing.send_telegram_message(text, **kw)
    finally:
        briefing.httpx.AsyncClient, briefing.log_audit_event = real_client, real_audit
    return ok, rec


async def main() -> int:
    bad: list = []
    print(f"container env: TELEGRAM_PAPER_CHAT_ID set = {bool(os.environ.get('TELEGRAM_PAPER_CHAT_ID'))}")
    saved = {k: os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_IDS", "TELEGRAM_PAPER_CHAT_ID")}
    os.environ.update({"TELEGRAM_BOT_TOKEN": "dryrun-token", "TELEGRAM_ALLOWED_USER_IDS": str(MAIN),
                       "TELEGRAM_PAPER_CHAT_ID": str(PAPER)})
    try:
        if not hasattr(constants, "paper_chat_id_for"):
            bad.append(("constants.paper_chat_id_for missing", "pre-#699 code"))

        # (label, text, plan, kwargs, expected chats in send order, expected return)
        cases = [
            ("paper text -> paper chat only", PAPER_TEXT, None, {}, [PAPER], True),
            ("live text -> main chat", LIVE_TEXT, None, {}, [MAIN], True),
            ("untagged system alert -> main chat", SYSTEM_TEXT, None, {}, [MAIN], True),
            ("explicit chat_id honoured for paper text", PAPER_TEXT, None, {"chat_id": 777}, [777], True),
            ("pre-converted HTML paper body -> paper chat",
             md_to_html("📄 PAPER ⚠️ *Ingest R1 rejected* — ABCD: x"), None, {"parse_mode": "HTML"}, [PAPER], True),
            ("paper chat 'not found' (400,400) -> falls back to main", PAPER_TEXT, {PAPER: [400, 400]}, {},
             [PAPER, PAPER, MAIN], True),
            ("bot removed from group (403) -> falls back to main", PAPER_TEXT, {PAPER: [403]}, {}, [PAPER, MAIN], True),
            ("both chats failing -> False, not silent", PAPER_TEXT, {PAPER: [403], MAIN: [403]}, {}, [PAPER, MAIN], False),
        ]
        for label, text, plan, kw, want_chats, want_ok in cases:
            ok, rec = await _drive(text, plan, **kw)
            good = rec.chats() == want_chats and ok is want_ok
            print(f"  {'ok  ' if good else 'BAD '}{label:<58} chats={rec.chats()} ok={ok}")
            if not good:
                bad.append((label, rec.chats(), ok, want_chats, want_ok))

        # env unset: byte-identical to the pre-#699 payload
        os.environ.pop("TELEGRAM_PAPER_CHAT_ID")
        ok, rec = await _drive(PAPER_TEXT)
        want = [{"chat_id": MAIN, "text": md_to_html(PAPER_TEXT), "disable_web_page_preview": True, "parse_mode": "HTML"}]
        good = ok is True and rec.posts == want
        print(f"  {'ok  ' if good else 'BAD '}{'env unset -> main chat, payload byte-identical':<58} chats={rec.chats()} ok={ok}")
        if not good:
            bad.append(("env unset", rec.posts, want))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    if bad:
        print(f"DRYRUN FAIL — {len(bad)} mismatch(es): {bad}")
        return 1
    print("DRYRUN PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
