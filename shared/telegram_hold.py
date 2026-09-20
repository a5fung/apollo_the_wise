"""#672 — what a RECOVERY re-run does with the Telegrams it would have sent. Default: HOLD them.

WHY IT SITS AT THE HTTP LAYER AND NOT ON A LIST OF SENDERS. On 2026-09-20 a recovery probe re-ran
Friday's missed jobs behind a banner reading *"nothing will be sent"*, having patched
`send_telegram_message` and `notify_owner` by name. `friday_watchlist` owns a second sender with
its own httpx client, and the operator's Friday watchlist arrived on his phone TWICE, two days
late. SEVEN production modules POST to `api.telegram.org` directly (`charts.py`,
`friday_watchlist.py`, `agent.py`, `briefing.py`, `broker/telegram_confirm.py`,
`core/notifications.py`, and counting) — a per-name or per-job rule is wrong by construction.
Every one of them reaches Telegram through `httpx` (`tests/test_probe_muzzle_covers_every_sender.py`
fails the build if one ever does not), so this guard patches `httpx.AsyncClient.post` ONCE and
decides per request. [[derive-the-population-never-hand-list-it]]

WHY IT IS CONTEXT-AWARE, unlike the probe muzzle (`scripts/probes/_muzzle.py`). The muzzle refuses
EVERY Telegram send in the process, which is right for a one-off script and wrong inside the live
scheduler, where an intraday alert or an order-path page may be in flight beside a recovery. This
wrapper acts ONLY when the calling task carries a `shared.dates.recovery_pin()` — the ContextVar the
recovery sweep sets around each re-run — and passes everything else through byte-identically.

THE DEFAULT IS HOLD, NOT SEND. The operator excluded the three Friday senders from the 09-19 hand
recovery ("his call"), and the 09-20 double watchlist settled it: a re-run RECORDS what it would
have sent — the summary page names every withheld message — and sending late is his flip:
`APOLLO_RECOVERY_SEND_LATE=1`. With the flip on, the message goes out with a plain first line
saying which job and slot it stands in for and when it was actually sent.

A held send returns a synthetic 200 with a Telegram-shaped body, so the job that sent it carries on
and finishes writing its DATA — raising here (the muzzle's behaviour) would fail the job midway,
which is the gap we are recovering from, reproduced inside the recovery.
"""
from __future__ import annotations

import json
import os
from typing import Any

from shared.dates import late_banner, recovery_pin

TELEGRAM_HOST = "api.telegram.org"
SEND_LATE_ENV = "APOLLO_RECOVERY_SEND_LATE"        # operator flip; default OFF (hold)

# Every send held during a recovery, in order: (job_id, slot, method_name, text). The sweep drains
# what belongs to the run it just finished and names it in the summary page.
_HELD: list[tuple[str, Any, str, str]] = []


def send_late_enabled() -> bool:
    return os.environ.get(SEND_LATE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def held_messages() -> list:
    return list(_HELD)


def drain_held(job_id: str | None = None) -> list:
    """Remove and return held sends — all of them, or only one job's."""
    global _HELD
    if job_id is None:
        out, _HELD = _HELD, []
        return out
    out = [h for h in _HELD if h[0] == job_id]
    _HELD = [h for h in _HELD if h[0] != job_id]
    return out


def _text_of(kw: dict) -> tuple[str, str]:
    """(field, text) of the human-readable body in a Bot API payload — sendMessage's `text`,
    sendPhoto's `caption`, editMessageText's `text`. ("", "") when there is none."""
    body = kw.get("json")
    if not isinstance(body, dict):
        body = kw.get("data") if isinstance(kw.get("data"), dict) else None
    if not isinstance(body, dict):
        return "", ""
    for field in ("text", "caption"):
        if isinstance(body.get(field), str):
            return field, body[field]
    return "", ""


def _method_of(url: str) -> str:
    return str(url).rsplit("/", 1)[-1] if "/" in str(url) else str(url)


class _HeldResponse:
    """The little of `httpx.Response` the seven senders read: status, `.json()`, `.text`."""
    status_code = 200

    def __init__(self, method: str):
        self._body = {"ok": True, "result": {"message_id": 0, "held": True, "method": method}}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


def install_recovery_hold() -> None:
    """Patch `httpx.AsyncClient.post` once (idempotent). Composes with the probe muzzle in either
    install order — each wraps whatever `post` currently is."""
    import httpx

    if getattr(httpx.AsyncClient, "_apollo_recovery_hold", False):
        return
    real_post = httpx.AsyncClient.post

    async def _post(self, url, *a, **kw):
        pin = recovery_pin()
        if pin is None or TELEGRAM_HOST not in str(url):
            return await real_post(self, url, *a, **kw)
        method = _method_of(url)
        field, text = _text_of(kw)
        if send_late_enabled():
            if field:
                body = kw.get("json") if isinstance(kw.get("json"), dict) else kw.get("data")
                body[field] = late_banner() + text
            return await real_post(self, url, *a, **kw)
        _HELD.append((pin.job_id, pin.slot, method, text or f"<{method} without text>"))
        return _HeldResponse(method)

    _post.__wrapped__ = real_post          # so a reader can see through it; also lets tests unwrap
    httpx.AsyncClient.post = _post
    httpx.AsyncClient._apollo_recovery_hold = True
