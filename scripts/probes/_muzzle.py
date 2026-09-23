"""One chokepoint that stops a probe sending the operator anything. Import it; never hand-list senders.

WHY THIS EXISTS, and it is not hypothetical. On 2026-09-20 a recovery probe re-ran Friday's missed
jobs behind a banner reading *"outbound messages MUZZLED — nothing will be sent"*. It patched
`send_telegram_message` and `notify_owner` BY NAME. `friday_watchlist` owns a SECOND sender,
`_send_with_keyboard`, which POSTs to the Bot API with its own httpx client and touches neither
name — so the operator's Friday watchlist arrived on his phone TWICE, two days late, while the
script said it could not happen. He confirmed receiving both.

That is the same defect as the outage the probe was recovering from: a property asserted over a
population that was hand-listed instead of derived. [[derive-the-population-never-hand-list-it]]

DERIVED, 2026-09-20: SEVEN production modules POST to api.telegram.org directly — `charts.py`
(sendMessage + sendPhoto), `friday_watchlist.py` (×2), `agent.py` (×2), `briefing.py` (sendMessage
+ sendPhoto + editMessageText), `broker/telegram_confirm.py` and `core/notifications.py`. A
name-based muzzle was never going to hold, and adding the eighth name would not have fixed it —
the ninth would be written next week.

So this does not patch senders at all. **Every one of them reaches Telegram through `httpx`**
(verified across all seven), so the guard sits at the HTTP layer: any request whose URL contains
`api.telegram.org` is captured and REFUSED, no matter which function built it or whether anyone
knew it existed. `tests/test_probe_muzzle_covers_every_sender.py` fails the build if a sender ever
reaches Telegram by some other library, which is the only way past this.
"""
from __future__ import annotations

TELEGRAM_HOST = "api.telegram.org"


class TelegramSendRefused(RuntimeError):
    """Raised INSTEAD of delivering. Loud on purpose — a silent skip would leave a probe reporting
    success for a message the operator never got, which is the other half of the same bug."""


def muzzle_telegram(captured: list | None = None) -> list:
    """Patch httpx so nothing can reach the Bot API. Returns the list captures land in.

    Idempotent, and it patches the CLASS rather than an instance, so a client constructed later —
    inside a job, in a library, anywhere — is covered too.
    """
    out = [] if captured is None else captured
    import httpx

    if getattr(httpx.AsyncClient, "_apollo_muzzled", False):
        return getattr(httpx.AsyncClient, "_apollo_captured", out)

    real_post = httpx.AsyncClient.post
    real_get = httpx.AsyncClient.get

    async def _post(self, url, *a, **kw):
        if TELEGRAM_HOST in str(url):
            out.append(("POST", str(url).split("/bot")[0], str(kw.get("json") or kw.get("data") or "")[:4000]))
            raise TelegramSendRefused(f"refused a send to {TELEGRAM_HOST} (captured #{len(out)})")
        return await real_post(self, url, *a, **kw)

    async def _get(self, url, *a, **kw):
        if TELEGRAM_HOST in str(url):
            out.append(("GET", str(url).split("/bot")[0], ""))
            raise TelegramSendRefused(f"refused a GET to {TELEGRAM_HOST}")
        return await real_get(self, url, *a, **kw)

    httpx.AsyncClient.post = _post
    httpx.AsyncClient.get = _get
    httpx.AsyncClient._apollo_muzzled = True
    httpx.AsyncClient._apollo_captured = out
    return out
