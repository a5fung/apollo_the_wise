"""Preflight: command-parity check.

Verifies that slash commands are consistently registered across the four
places they need to exist. Telegram silently drops commands when the
chain is broken (the bug class caught 2026-05-25 evening: /breadth +
7 other commands had BotCommand + agent dispatch but no CommandHandler).

Windows note: intentionally ASCII-only output so PowerShell cp1252
console doesn't UnicodeEncodeError on the failure path.

Two slash-command shapes exist:

  A. Orchestrator-direct: CommandHandler routes to a method on the
     bot class itself (e.g., _handle_status, _handle_themes_command).
     These need BotCommand + CommandHandler. No agent.py dispatch
     required.

  B. Market-agent-routed: CommandHandler routes to
     `self._dispatch_market_slash`, which forwards the task string
     to the market agent's execute_task → _handle_slash_command →
     dispatch dict. These need BotCommand + CommandHandler +
     dispatch entry in agent.py.

The preflight separates the two and applies the right rule to each.

Allowlist `HIDDEN_OK` covers commands that are intentionally NOT in the
autocomplete menu (e.g., short aliases for legacy compat). They still
need a CommandHandler and (for market-agent-routed) a dispatch entry.

Exits non-zero on any unallowlisted mismatch.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TELEGRAM_FILE = REPO_ROOT / "channels" / "telegram.py"
AGENT_FILE = REPO_ROOT / "agents" / "market_intelligence" / "agent.py"

# Commands intentionally hidden from Telegram menu (autocomplete) but still
# callable. Add new entries with a comment. If unsure, register a BotCommand
# instead.
HIDDEN_OK = {
    # Legacy / short aliases (commands that the operator types but we don't
    # want cluttering the autocomplete menu)
    "9m",
    "altseason",
    "clusters",
    "crypto",
    "dryrun",
    "missed",
    "parabolic",
    "regime",
    "trade",
    "audit",
    "pregame",
    "strategy",
    "why",
    "wick",
    "watchlist",
    "fishhook",
    # Singular aliases paired with plural BotCommand
    "flagbreak",
    "supporttest",
    "mapullback",
    "sugarbaby",
    "flag",
    "setup",
    "rubric",
    # Orchestrator built-ins (Telegram convention — these have menus elsewhere)
    "start",
    "help",
    # Orchestrator-direct handlers intentionally not in autocomplete menu
    # (kept hidden to reduce menu clutter; still operator-callable).
    "agents",   # /agents — agent registry status, operator-only
    "eps",      # alias of /ep
    "rules",    # /rules — strategy rules dump
    "spend",    # /spend — Anthropic spend tracker
    "themes",   # /themes — themes detail (longer than briefing summary)
}

# Commands that ARE in the market-routed loop but are handled by the keyword-
# routing branch at the top of execute_task (line ~741) BEFORE reaching the
# slash dispatch dict. Preflight skips the "missing dispatch" check for these.
# Add new entries with a comment.
KEYWORD_ROUTED_OK = {
    "crypto",      # execute_task: matches "crypto" / "/crypto" → _handle_crypto_query
    "altseason",   # execute_task: matches "altseason" / "/altseason" → _handle_crypto_query
}


def parse_bot_commands(text: str) -> set[str]:
    """BotCommand("name", ...) names."""
    return set(re.findall(r'BotCommand\(\s*"([a-z_0-9]+)"', text))


def parse_command_handlers(text: str) -> tuple[set[str], set[str]]:
    """Returns (direct_handlers, market_handlers).

    direct_handlers: CommandHandler(name, self._handle_X) — orchestrator-direct
    market_handlers: CommandHandler(name, self._dispatch_market_slash) —
                     routed to market agent (needs agent.py dispatch entry)
    """
    direct: set[str] = set()
    market: set[str] = set()

    # Form 1: individual CommandHandler("name", target)
    for m in re.finditer(
        r'CommandHandler\(\s*"([a-z_0-9]+)"\s*,\s*self\.([_A-Za-z][_A-Za-z0-9]*)',
        text,
    ):
        name, target = m.group(1), m.group(2)
        if target == "_dispatch_market_slash":
            market.add(name)
        else:
            direct.add(name)

    # Form 2: for _cmd in (...): app.add_handler(CommandHandler(_cmd, ...))
    # By convention this loop ALWAYS routes to _dispatch_market_slash.
    # The DOTALL match captures the multi-line tuple body.
    for tuple_match in re.finditer(
        r'for\s+_cmd\s+in\s*\((.*?)\)\s*:\s*(?:#[^\n]*)?\n\s*app\.add_handler\(CommandHandler\(\s*_cmd\s*,\s*self\.([_A-Za-z][_A-Za-z0-9]*)',
        text, re.DOTALL,
    ):
        tuple_body = tuple_match.group(1)
        target = tuple_match.group(2)
        names = set(re.findall(r'"([a-z_0-9]+)"', tuple_body))
        if target == "_dispatch_market_slash":
            market.update(names)
        else:
            direct.update(names)

    return direct, market


def parse_dispatch_keys(text: str) -> set[str]:
    """Slash-command keys from the dispatch dict in
    agent.py::_handle_slash_command. Looks for `"/name": self._handle_*`."""
    m = re.search(
        r'async def _handle_slash_command\b[^\n]*\n.*?dispatch\s*=\s*\{([^}]+)\}',
        text, re.DOTALL,
    )
    if not m:
        return set()
    return set(re.findall(r'"/([a-z_0-9]+)"', m.group(1)))


def main() -> int:
    telegram_text = TELEGRAM_FILE.read_text(encoding="utf-8")
    agent_text = AGENT_FILE.read_text(encoding="utf-8")

    bot_commands = parse_bot_commands(telegram_text)
    direct_handlers, market_handlers = parse_command_handlers(telegram_text)
    dispatch_keys = parse_dispatch_keys(agent_text)

    all_handlers = direct_handlers | market_handlers
    print(
        f"Parsed: {len(bot_commands)} BotCommand, "
        f"{len(direct_handlers)} direct + {len(market_handlers)} market-routed CommandHandlers, "
        f"{len(dispatch_keys)} agent dispatch keys"
    )

    errors: list[str] = []

    # 1. BotCommand without ANY CommandHandler → SILENT DROP in Telegram.
    missing_handlers = bot_commands - all_handlers
    if missing_handlers:
        errors.append(
            "  BotCommand without CommandHandler (Telegram silently drops these):\n"
            + "\n".join(f"    - /{c}" for c in sorted(missing_handlers))
        )

    # 2. Market-routed CommandHandler without agent.py dispatch entry → market
    #    agent returns 'unknown command' (unless keyword-routed via execute_task).
    missing_dispatch = (market_handlers - dispatch_keys) - KEYWORD_ROUTED_OK
    if missing_dispatch:
        errors.append(
            "  Market-routed CommandHandler without agent.py dispatch entry\n"
            "  (market agent returns 'unknown command'):\n"
            + "\n".join(f"    - /{c}" for c in sorted(missing_dispatch))
        )

    # 3. CommandHandler without BotCommand AND not in HIDDEN_OK → forgotten
    #    BotCommand registration. (Direct + market handlers treated the same
    #    here — both need either a menu entry or an explicit allowlist.)
    hidden_unallowlisted = (all_handlers - bot_commands) - HIDDEN_OK
    if hidden_unallowlisted:
        errors.append(
            "  CommandHandler without BotCommand AND not in HIDDEN_OK allowlist\n"
            "  (either add BotCommand in channels/telegram.py OR add to HIDDEN_OK\n"
            "  in scripts/preflight_command_parity.py with a comment):\n"
            + "\n".join(f"    - /{c}" for c in sorted(hidden_unallowlisted))
        )

    if errors:
        print("\nFAIL Command parity check FAILED:\n")
        for e in errors:
            print(e + "\n")
        print(
            "  Fix the imbalance and re-run. The discipline:\n"
            "    1. BotCommand in channels/telegram.py (autocomplete menu)\n"
            "    2. CommandHandler in channels/telegram.py (orchestrator route)\n"
            "    3. dispatch dict in agent.py (market-routed commands only)\n"
            "    4. async def _handle_X handler in agent.py (actual code)\n"
        )
        return 1

    print("Command parity check - OK (BotCommand / CommandHandler / dispatch aligned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
