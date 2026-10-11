"""#699 verify-live probe. THIS ONE SENDS - exactly ONE clearly-labelled paper test message, once.

Why it exists (2026-10-11, review of #699): the dry run proves the CODE routes by the signed rule, and
the first natural paper alert (Monday 08:25 ET, the #687 paper-test page) is the first free proof in
production - but neither shows, the day of the deploy and with the market shut, that the CONTAINER'S
real sender and real env put a paper-tagged message in Apollo Paper. This does, through the real
`briefing.send_telegram_message` and the real environment:

  docker exec -i apollo-execution python - < scripts/probes/_699_paper_chat/live_routing_check.py

Run it in apollo-execution (the service that sends the paper/live trade alerts); repeat in
apollo-market only if you also want that container's env proven (it sends one more message).

ONE message, deliberately: the env var can only change where a PAPER message goes (live-tagged and
untagged messages never read it - the dry run and the unit tests prove that), so a LIVE-$ test line in
the main chat would add noise and prove nothing new.

It REFUSES to send anything unless the container's real `TELEGRAM_PAPER_CHAT_ID` resolves a paper
message to the signed id (-5382801675) - a missing, quoted or mistyped value stops here with exit 1
and nothing sent. After it sends, LOOK (a human reads two chats; the script cannot):

  * the "PAPER" probe -> the Apollo Paper group, and NOT the main chat

WOULD-FAIL-IF: the probe shows up in the main chat (switch off / wrong id / migrated group) or in
neither chat (the bot is not in the group; the script prints `sent=False` and exits 1 for that).

The text says "test message, no trade". Nothing here touches the broker, the database or any trade
state.
"""
from __future__ import annotations

import asyncio
import os
import sys

from agents.market_intelligence import briefing, constants

EXPECTED_PAPER_CHAT = -5382801675          # the signed "Apollo Paper" chat id (#699, confirmed by the bot's getChat)


def probe_texts() -> list[tuple[str, str]]:
    """(kind, text) for the probe. The tag comes from `mode_prefix` - never re-typed - so the probe
    tests the same tag the production alerts wear."""
    note = "#699 routing check (test message, no trade)"
    return [
        ("paper", f"{constants.mode_prefix('paper')}{note} - this belongs in Apollo Paper, NOT the main chat"),
    ]


async def main() -> int:
    raw = os.environ.get("TELEGRAM_PAPER_CHAT_ID")
    paper_text = dict(probe_texts())["paper"]
    routed = constants.paper_chat_id_for(paper_text)
    print(f"real env: TELEGRAM_PAPER_CHAT_ID={raw!r} -> a paper message routes to {routed}")
    if routed != EXPECTED_PAPER_CHAT:
        print(f"REFUSING TO SEND: expected the signed Apollo Paper id {EXPECTED_PAPER_CHAT}. "
              "Nothing was sent. Fix TELEGRAM_PAPER_CHAT_ID in the server .env and recreate the containers.")
        return 1

    ok = await briefing.send_telegram_message(paper_text)
    print(f"  paper  sent={ok}  expected in: Apollo Paper ({EXPECTED_PAPER_CHAT}) only")
    if not ok:
        print("LIVECHECK FAIL - the send returned False (see telegram_send_failed audit rows).")
        return 1
    print("LIVECHECK SENT - now LOOK: the PAPER probe must be in Apollo Paper and NOT in the main chat.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
