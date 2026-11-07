"""Ladder press — HIS button on a breach page: Demote (one rung down) or No action (#312, ADR 0022 §1).

THE ONLY PLACE A PAGE MOVES A PHASE. The nightly `ladder_watchdog` pages him on a breach; the press
arrives through `channels/telegram.py` (the `ladder:` callback, which answers "Unauthorized" to any
user outside `telegram_allowed_user_ids` before anything else runs) as the market agent's internal
`/ladder_press <demote|noaction> <page id>`, and lands here with the pressing user's id. A second
check against the same allowlist (`TELEGRAM_ALLOWED_USER_IDS`) sits in front of every decision —
defence in depth behind the channel gate, not a replacement for it.

ONE TRANSACTION, IDEMPOTENT, STALE-SAFE. The page row is locked (`FOR UPDATE`), its decision checked
(a decided page refuses — a double press moves one rung TOTAL), the strategy's CURRENT phase read
and compared with the phase the page SHOWED (a strategy moved since the page — the typed
`/strategy <id> demote|promote`, or another page's press — refuses and marks the page stale), and
then, for Demote, the move itself: `strategies/registry.update_strategy(..., phase=<the rung below>,
expect_phase=<phase at page>, conn=<this connection>)` — the one phase writer, with a compare-and-set
on the WHERE so even a move that lands between the read and the write matches no row and is refused.
The decision, the phase write, the episode close and the audit rows commit together or not at all.
No action records the decision and the audit row and moves nothing.

WHAT MOVES AND WHAT DOES NOT. A demote changes `mi_strategies.phase` — the registry row NEW entries
route by (`resolve_account_mode_for_strategy`). Open positions are untouched: every exit and stop
path reads the TRADE ROW's own `account_mode` (`execute_full_exit`, `morning_stop_refresh`,
`update_open_positions_live`, `scan_profit_triggers`, `sync_positions` per mode — pinned in
`tests/test_312_ladder_act_step.py` §C), so a live position keeps its live-account management
after a live→paper demote. ⚠ The registry cache is per PROCESS: `update_strategy` invalidates the
market agent's; apollo-execution (the ORB entry pipeline) refreshes its copy at its next restart —
the same property the typed `/strategy <id> demote` has today, reported on the #312 card.

ADR 0022 §2 — "a demotion zeroes the pending allocation proposal for that strategy": the L3
`allocation_proposals` store is UNBUILT (no production module names it), so there is no pending
proposal to zero; the demote audit row records that fact (`allocator_proposal`), and
`tests/test_312_ladder_act_step.py` fails the day such a store appears without this hook being
wired. The bound sizing knob (`position_size_multiplier`) is NOT touched here — sizing is his.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from agents.market_intelligence.ladder_watchdog import DEMOTE_TO, _CLOSE_EPISODE_SQL
from shared.dates import _ET

logger = logging.getLogger(__name__)

NO_ACTION_EVENT = "ladder_press_no_action"
REFUSED_EVENT = "ladder_press_refused"
PHASE_CHANGE_EVENT = "strategy_phase_change"     # the same event the typed /strategy <id> demote writes
ACTIONS = ("demote", "noaction")

ALLOCATOR_NOTE = ("no pending proposal to zero — the L3 allocation_proposals store is unbuilt "
                  "(ADR 0022 §2); wire the zeroing here when it lands")

_PAGE_FOR_UPDATE_SQL = """
    SELECT id, strategy_id, episode_on, as_of, phase_at_page, demote_to, breached, sent_at,
           decision, decided_at, decided_by
    FROM mi_ladder_pages WHERE id = $1 FOR UPDATE
"""
_CURRENT_PHASE_SQL = "SELECT phase FROM mi_strategies WHERE strategy_id = $1"
_DECIDE_PAGE_SQL = """
    UPDATE mi_ladder_pages SET decision = $1, decided_by = $2, decided_at = NOW()
    WHERE id = $3 AND decision IS NULL
"""


def allowed_user_ids() -> set[int]:
    """The operator allowlist the pages are sent to (`TELEGRAM_ALLOWED_USER_IDS`)."""
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


def _when(ts) -> str:
    """A decided_at for the button answer (an aware timestamp from Postgres; anything else as-is)."""
    if ts is None:
        return "earlier"
    if isinstance(ts, datetime) and ts.tzinfo is not None:
        return ts.astimezone(_ET).strftime("%a %m-%d %H:%M ET")
    return str(ts)


async def _refuse(conn, *, page_id: int, user_id, why: str, reason_code: str, page: dict | None) -> str:
    from agents.market_intelligence.db import log_audit_event
    await log_audit_event(
        REFUSED_EVENT,
        f"ladder page #{page_id}: press refused — {why}",
        json.dumps({"page_id": page_id, "pressed_by": user_id, "reason": reason_code,
                    "pressed_at": datetime.now(_ET).isoformat(timespec="seconds"),
                    "strategy_id": page["strategy_id"] if page else None,
                    "phase_at_page": page["phase_at_page"] if page else None}, default=str),
        conn=conn)
    return f"Not done — {why}"


async def _demote_on_page(conn, page: dict, *, user_id: int, pressed_at: str) -> str:
    """The move: one rung down from the rung the page showed, compare-and-set, on THIS connection
    inside the caller's transaction. Returns the answer for the button."""
    from agents.market_intelligence.db import log_audit_event
    from agents.market_intelligence.strategies.registry import update_strategy

    sid, frm, to = page["strategy_id"], page["phase_at_page"], page["demote_to"]
    updated = await update_strategy(sid, phase=to, expect_phase=frm, conn=conn)
    if updated is None:
        # The row moved between the phase read above and this write (a concurrent typed command).
        await conn.execute(_DECIDE_PAGE_SQL, "stale", user_id, page["id"])
        return await _refuse(conn, page_id=page["id"], user_id=user_id, page=page, reason_code="moved_during_press",
                             why=(f"{sid} moved off {frm} while the press was being applied; the page "
                                  f"is stale and nothing was changed. /strategy {sid} shows where it is."))
    await conn.execute(_DECIDE_PAGE_SQL, "demote", user_id, page["id"])
    # The episode closes on the day of the PRESS (it may land nights after the page), by his demote.
    await conn.execute(_CLOSE_EPISODE_SQL, datetime.now(_ET).date(), "demote", sid, page["episode_on"])
    await log_audit_event(
        PHASE_CHANGE_EVENT,
        f"{sid} demoted {frm} → {to} (ladder page #{page['id']}, pressed by {user_id})",
        json.dumps({"phase_from": frm, "phase_to": to, "source": "ladder_press",
                    "page_id": page["id"], "page_night": page["as_of"], "pressed_by": user_id,
                    "pressed_at": pressed_at, "breached": page["breached"],
                    "allocator_proposal": ALLOCATOR_NOTE}, default=str),
        conn=conn)
    return (f"Demoted: {sid} moved from {frm} to {to} (page #{page['id']}, night {page['as_of']}). "
            f"Open positions keep their {('live' if frm == 'live' else 'paper')}-book stops and exits; "
            f"new entries follow the registry. Back up is /strategy {sid} promote.")


async def _decide_locked(conn, action: str, page_id: int, *, user_id: int, pressed_at: str) -> str:
    """The body of the ONE transaction: lock the page, check it, decide it. Returns the answer."""
    from agents.market_intelligence.db import log_audit_event

    page = await conn.fetchrow(_PAGE_FOR_UPDATE_SQL, page_id)
    if page is None or page["sent_at"] is None:
        return await _refuse(conn, page_id=page_id, user_id=user_id, page=None, reason_code="no_such_page",
                             why=f"no such page (#{page_id})")
    page = dict(page)
    if isinstance(page.get("breached"), str):
        page["breached"] = json.loads(page["breached"])
    sid, frm = page["strategy_id"], page["phase_at_page"]
    if page["decision"] is not None:
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="already_decided",
            why=(f"page #{page_id} was already decided: {page['decision']} at "
                 f"{_when(page['decided_at'])} (by {page['decided_by']}). Nothing was changed."))
    current = await conn.fetchval(_CURRENT_PHASE_SQL, sid)
    if current != frm:
        await conn.execute(_DECIDE_PAGE_SQL, "stale", user_id, page_id)
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="stale_phase",
            why=(f"{sid} has moved since this page: it showed {frm}, the registry says "
                 f"{current}. Nothing was changed; a new breach on {current} will page again."))
    if action == "noaction":
        await conn.execute(_DECIDE_PAGE_SQL, "no_action", user_id, page_id)
        await log_audit_event(
            NO_ACTION_EVENT,
            f"ladder page #{page_id}: No action — {sid} stays {frm} (pressed by {user_id})",
            json.dumps({"page_id": page_id, "strategy_id": sid, "phase": frm,
                        "pressed_by": user_id, "pressed_at": pressed_at,
                        "breached": page["breached"]}, default=str),
            conn=conn)
        return (f"No action recorded: {sid} stays {frm} (page #{page_id}). The same limits "
                f"will not page again this episode; a newly breached one will.")
    if DEMOTE_TO.get(frm) != page["demote_to"]:
        return await _refuse(conn, page_id=page_id, user_id=user_id, page=page, reason_code="no_rung_below",
                             why=f"{frm} has no rung below it")
    return await _demote_on_page(conn, page, user_id=user_id, pressed_at=pressed_at)


async def handle_ladder_press(action: str, page_id: int, *, user_id: int | None) -> str:
    """Apply his press on page `page_id`. Returns the plain-words answer the button shows."""
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.strategies.registry import invalidate_cache

    pressed_at = datetime.now(_ET).isoformat(timespec="seconds")
    pool = await get_pool()
    async with pool.acquire() as conn:
        if action not in ACTIONS:
            return await _refuse(conn, page_id=page_id, user_id=user_id, page=None, reason_code="unknown_action",
                                 why=f"unknown action {action!r}")
        if user_id not in allowed_user_ids():
            return await _refuse(conn, page_id=page_id, user_id=user_id, page=None, reason_code="unauthorized",
                                 why="this user is not authorized to decide a ladder page")
        try:
            async with conn.transaction():
                return await _decide_locked(conn, action, page_id, user_id=user_id, pressed_at=pressed_at)
        finally:
            # AFTER the transaction has committed (or rolled back): `update_strategy` invalidates
            # the process cache before the commit, and a concurrent `get_strategy()` in between
            # could re-cache the pre-commit row — so invalidate once more here, post-commit.
            invalidate_cache()
