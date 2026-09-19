"""
End-to-end /status render validator. Builds the actual rendered output
the orchestrator's _handle_status produces, then POSTs to Telegram's
sendMessage API with parse_mode=Markdown to verify the bytes parse
cleanly server-side.

Sends a [VALIDATION] -prefixed message to the user's chat with
disable_notification=True. Use after /status touches to confirm no
Markdown parse regressions before declaring the deploy green.

Designed to catch the 2026-05-13 regression: strategy IDs like
`9m_day2` contain underscores Telegram interprets as italic markers;
an odd count of underscores crashes the entity parser server-side.
The preflight smoke test didn't exercise the render path, so this
script closes that gap.
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

from shared.registry import get_agent_url
from shared.secrets import get_secrets


async def main() -> int:
    url = get_agent_url("market_intelligence")
    secret = get_secrets().internal_api_secret

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{url}/account/status", headers={"X-Apollo-Secret": secret}
        )
        resp.raise_for_status()
        data = resp.json()

    # Build the exact same lines _check_account_mode produces
    lines: list[str] = []
    if not data.get("live_trading_enabled", False):
        lines = ["⚪ Trading: DISABLED (LIVE_TRADING_ENABLED=false)"]
    else:
        for block in data.get("modes", []):
            mode = block.get("mode", "?")
            icon = "📄" if mode == "paper" else "💰"
            label = "PAPER" if mode == "paper" else "LIVE-$ (real money)"
            routed_strats = block.get("routed_strategies", [])
            if routed_strats:
                routed = " · routed: " + ", ".join(f"`{s}`" for s in routed_strats)
            else:
                routed = " · (no strategies routed)"
            lines.append(f"{icon} *{label}*{routed}")
            account = block.get("account")
            err = block.get("error")
            if account:
                equity = account.get("equity", 0.0)
                buying_power = account.get("buying_power", 0.0)
                lines.append(f"  Equity: ${equity:,.2f}")
                lines.append(f"  Buying power: ${buying_power:,.2f}")
            elif err:
                lines.append(f"  ⚠️ Account fetch failed: {err[:100]}")
            lines.append("")
        while lines and not lines[-1]:
            lines.pop()

    body = "\n".join(lines)
    print("=== Rendered account block ===")
    print(body)
    print("=== End ===\n")

    # POST to Telegram with parse_mode=Markdown. We send to the user's chat
    # (the only chat the bot is allowed to message) with disable_notification
    # + a clear [VALIDATION] prefix. If Markdown parses cleanly, the API
    # returns 200; if Markdown is invalid, it returns 400 BadRequest with
    # "Can't parse entities".
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = (os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "") or "").split(",")[0].strip()
    if not token or not chat_id:
        print("WARN: no TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USER_IDS set; skipping live API check")
        return 0

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"[VALIDATION /status preview — safe to ignore]\n{body}",
                "parse_mode": "Markdown",
                "disable_notification": True,
            },
        )
        print(f"Telegram API status: {r.status_code}")
        print(f"Response: {r.json()}")
        if r.status_code != 200:
            print("\nFAIL — Markdown parse error. Do NOT consider /status fixed.")
            return 1

    print("\nOK — /status account block renders cleanly through Telegram Markdown parser.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
