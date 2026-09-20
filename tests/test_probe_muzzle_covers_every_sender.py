"""The probe muzzle must cover EVERY Telegram sender, including ones nobody has written yet.

FOUND THE HARD WAY, 2026-09-20. A recovery probe announced "outbound messages MUZZLED — nothing
will be sent", having patched `send_telegram_message` and `notify_owner` by name.
`friday_watchlist` owns a SECOND sender, `_send_with_keyboard`, that POSTs to the Bot API with its
own httpx client. The operator received Friday's watchlist TWICE, two days late, and confirmed
both.

The muzzle now sits at the HTTP layer instead of on a list of function names, so the question this
file must answer is no longer "did we list every sender" — which is undecidable and was wrong —
but "can any sender reach Telegram by a route the HTTP layer cannot see". That IS decidable.
[[derive-the-population-never-hand-list-it]]
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROOTS = ("agents", "core", "channels", "shared")
OTHER_HTTP = ("requests.", "urllib.request", "aiohttp", "http.client", "pycurl")


def _imports_httpx(text: str) -> bool:
    """Does this module actually import httpx? Parsed, not pattern-matched.

    ⚠ THREE DRAFTS OF THIS ONE CHECK WERE WRONG, all the same way — a string where a structure was
    meant, which is the defect this whole file polices:
      1. `"httpx" in text` — passed a module that had swapped to `requests`, because the word still
         appeared elsewhere. Its mutation read GREEN.
      2. `^\\s*import\\s+httpx` — fooled by `_nothttpx`... and then it FAILED on real code:
         `agent.py` writes `import os as _os, httpx as _httpx`, a combined import the regex cannot
         see. It called a covered module uncovered.
    So: ask the AST. An alias, a combined import and a `from httpx import ...` all answer correctly,
    and a rename cannot fake one.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:                      # not parseable → cannot vouch for it
        return False
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "httpx" for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "httpx":
            return True
    return False


def _senders() -> dict[Path, str]:
    """DERIVED, not listed: every source file naming the Bot API host."""
    out = {}
    for root in ROOTS:
        for p in (REPO / root).rglob("*.py"):
            t = p.read_text(encoding="utf-8", errors="replace")
            if "api.telegram.org" in t:
                out[p] = t
    return out


def test_there_are_senders_to_cover():
    """Stops the file going vacuously green if the host string is renamed or the senders move."""
    s = _senders()
    assert len(s) >= 5, (
        f"only {len(s)} file(s) reference api.telegram.org — either they moved or this test has "
        f"stopped finding them. A vacuous guard is worse than none; fix the finder, do not relax "
        f"the bar.")


def test_every_sender_reaches_telegram_through_httpx():
    """The muzzle patches `httpx.AsyncClient`. A sender on any OTHER http library slips straight
    past it — which is precisely how `_send_with_keyboard` slipped past the name-based version.

    MUTATION: adding a `requests.post("https://api.telegram.org/...")` line to a covered module
    reddens this. Verified by running it."""
    # ⚠ The first version of this check was `if "httpx" in text: continue`, and its own mutation
    # did NOT redden: swapping `import httpx` for `import requests` leaves the word "httpx" in the
    # file (other call sites, a comment) and the guard waved it through. Checking for the PRESENCE
    # of the safe thing is not the same as checking for the ABSENCE of an unsafe one — the same
    # shape of error as the muzzle this file exists to police. Both are asserted now.
    offenders = {}
    for p, text in _senders().items():
        rival = [l for l in OTHER_HTTP if l in text]
        if rival:
            offenders[str(p.relative_to(REPO))] = rival
        elif not _imports_httpx(text):
            offenders[str(p.relative_to(REPO))] = ["no httpx import"]
    assert not offenders, (
        f"these reach api.telegram.org WITHOUT httpx, so the probe muzzle cannot see them and a "
        f"probe could send the operator a message while reporting that it could not: {offenders}")


@pytest.mark.asyncio
async def test_the_muzzle_refuses_a_send_no_matter_who_builds_it():
    """Behaviour, not structure: an ARBITRARY caller — standing in for the sender nobody has
    written yet — is refused, and the attempt is CAPTURED rather than lost.

    MUTATION: dropping the `TELEGRAM_HOST in str(url)` check lets this through. Verified RED."""
    import httpx

    from scripts.probes._muzzle import TelegramSendRefused, muzzle_telegram

    captured = muzzle_telegram([])

    async def a_sender_nobody_listed():
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post("https://api.telegram.org/bot123:ABC/sendMessage",
                         json={"chat_id": 1, "text": "Friday watchlist"})

    with pytest.raises(TelegramSendRefused):
        await a_sender_nobody_listed()

    assert captured, "the refused send was not captured — a probe would hide the gap it caused"
    assert "Friday watchlist" in captured[-1][2], (
        f"the capture does not carry the body, so nobody can see what would have gone out: "
        f"{captured[-1]}")
