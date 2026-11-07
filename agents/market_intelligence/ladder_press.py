"""Ladder press — HIS button on a breach page: Demote (one rung down) or No action (#312, ADR 0022 §1).

THE ONLY PLACE A PAGE MOVES A PHASE. The nightly `ladder_watchdog` pages him on a breach; the press
arrives through `channels/telegram.py` (the `ladder:` callback, which answers "Unauthorized" to any
user outside `telegram_allowed_user_ids` before anything else runs) as the market agent's internal
`/ladder_press <demote|noaction> <page id> <token>`, and lands here with the pressing user's id. A
second check against the same allowlist (`TELEGRAM_ALLOWED_USER_IDS`) sits in front of every decision —
defence in depth behind the channel gate, not a replacement for it.

THE BUTTON IS THE ONLY SENDER — PROVEN BY A TOKEN, NOT BY CONVENTION (#312 review, 2026-11-07). The
orchestrator's LLM reaches the market agent with free text through its `call_market_agent` tool, and
any text starting with "/" goes to slash dispatch, so a `/ladder_press demote 7` could arrive carrying
his user id with no press behind it. Every page therefore carries a random token
(`mi_ladder_pages.token`, 32 url-safe chars), both buttons carry it (`ladder:<action>:<page id>:<token>`,
under Telegram's 64-byte limit), and a press whose token does not match in constant time is refused —
nothing marked, nothing moved, audited `bad_token`. The button data is the only thing that holds the
token; the LLM never sees it. (`/ladder_press` is also kept off the "Available" list the
Unknown-command reply prints.)

ONE TRANSACTION, IDEMPOTENT, STALE-SAFE — AND HONEST ABOUT WHAT COMMITTED. The page row is locked
(`FOR UPDATE`), its token checked, its decision checked (a decided page refuses — a double press moves
one rung TOTAL), its EPISODE checked (a page whose breach episode has ended — the breach cleared, or
the strategy moved by any other path — refuses with "this breach ended on X"; its numbers are stale),
the strategy's CURRENT phase read and compared with the phase the page SHOWED (a strategy moved since
the page refuses and marks the page stale), and then, for Demote, the move itself:
`strategies/registry.update_strategy(..., phase=<the rung below>, expect_phase=<phase at page>,
conn=<this connection>)` — the one phase writer, with a compare-and-set on the WHERE so even a move
that lands between the read and the write matches no row and is refused. The decision, the phase
write, the episode close and the audit rows commit together or not at all. Every audit row written
INSIDE the transaction is a RAISING write (`log_audit_event(..., strict=True)`): the plain call
swallows its own failure, which inside a transaction leaves it ABORTED, and Postgres answers the COMMIT
of an aborted transaction with a silent ROLLBACK — a demote whose audit INSERT timed out would have
rolled back while the screen said "Demoted". And the answer is built from a RE-READ of the committed
phase and page decision after the transaction, never from what the handler meant to do. No action
records the decision and the audit row and moves nothing.

WHAT MOVES AND WHAT DOES NOT. A demote changes `mi_strategies.phase` — the row NEW entries route by.
Since the #312 review that row is read FRESH (`registry.get_strategy_fresh`, one primary-key SELECT,
never the per-process cache) at the top of the entry funnel, in both paper lanes and by the label
resolver, so the commit here is visible to the very next entry in apollo-execution with no restart.
An entry already past that read when the press commits still submits on the old phase — inherent,
and the answer says so. Open positions are untouched: every exit and stop path reads the TRADE ROW's
own `account_mode` (`execute_full_exit`, `morning_stop_refresh`, `update_open_positions_live`,
`scan_profit_triggers`, `sync_positions` per mode — pinned in `tests/test_312_ladder_act_step.py`
§C), so a live position keeps its live-account management after a live→paper demote.

ADR 0022 §2 — "a demotion zeroes the pending allocation proposal for that strategy": the L3
`allocation_proposals` store is UNBUILT (no production module names it), so there is no pending
proposal to zero; the demote audit row records that fact (`allocator_proposal`), and
`tests/test_312_ladder_act_step.py` fails the day such a store appears without this hook being
wired. The bound sizing knob (`position_size_multiplier`) is NOT touched here — sizing is his.
"""
from __future__ import annotations

import hmac
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
    SELECT id, strategy_id, episode_on, as_of, phase_at_page, demote_to, breached, token, sent_at,
           decision, decided_at, decided_by
    FROM mi_ladder_pages WHERE id = $1 FOR UPDATE
"""
_CURRENT_PHASE_SQL = "SELECT phase FROM mi_strategies WHERE strategy_id = $1"
_DECIDE_PAGE_SQL = """
    UPDATE mi_ladder_pages SET decision = $1, decided_by = $2, decided_at = NOW()
    WHERE id = $3 AND decision IS NULL
"""
# The page's episode: a closed one (the breach cleared, or the strategy moved by another path) makes
# the page's numbers stale, so the press refuses it.
_EPISODE_STATE_SQL = """
    SELECT closed_on, closed_by FROM mi_ladder_episodes WHERE strategy_id = $1 AND opened_on = $2
"""
# The post-commit re-read the answer is built from.
_PAGE_DECISION_SQL = "SELECT decision FROM mi_ladder_pages WHERE id = $1"


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


async def _refuse(conn, *, page_id: int, user_id, why: str, reason_code: str, page: dict | None,
                  strict: bool = True) -> str:
    """Record the refusal and answer it. `strict` (the default) makes the audit write RAISE on
    failure — inside the press transaction a swallowed failure would abort it silently; outside
    it (the post-commit check) the caller passes strict=False so a sick DB still gets an answer."""
    from agents.market_intelligence.db import log_audit_event
    await log_audit_event(
        REFUSED_EVENT,
        f"ladder page #{page_id}: press refused — {why}",
        json.dumps({"page_id": page_id, "pressed_by": user_id, "reason": reason_code,
                    "pressed_at": datetime.now(_ET).isoformat(timespec="seconds"),
                    "strategy_id": page["strategy_id"] if page else None,
                    "phase_at_page": page["phase_at_page"] if page else None}, default=str),
        conn=conn, strict=strict)
    return f"Not done — {why}"


def _demoted_answer(sid: str, frm: str, to: str, page: dict) -> str:
    return (f"Demoted: {sid} moved from {frm} to {to} (page #{page['id']}, night {page['as_of']}). "
            f"Open positions keep their {('live' if frm == 'live' else 'paper')}-book stops and exits; "
            f"new entries read the registry fresh, so the next entry routes on {to} (an entry already "
            f"past its registry read when you pressed still goes on {frm}). Back up is /strategy {sid} promote.")


async def _demote_on_page(conn, page: dict, *, user_id: int, pressed_at: str) -> tuple[str, dict | None]:
    """The move: one rung down from the rung the page showed, compare-and-set, on THIS connection
    inside the caller's transaction. Returns (the provisional answer, what the committed state must
    show for that answer to be true)."""
    from agents.market_intelligence.db import log_audit_event
    from agents.market_intelligence.strategies.registry import update_strategy

    sid, frm, to = page["strategy_id"], page["phase_at_page"], page["demote_to"]
    updated = await update_strategy(sid, phase=to, expect_phase=frm, conn=conn)
    if updated is None:
        # The row moved between the phase read above and this write (a concurrent typed command).
        await conn.execute(_DECIDE_PAGE_SQL, "stale", user_id, page["id"])
        return await _refuse(conn, page_id=page["id"], user_id=user_id, page=page, reason_code="moved_during_press",
                             why=(f"{sid} moved off {frm} while the press was being applied; the page "
                                  f"is stale and nothing was changed. /strategy {sid} shows where it is.")), None
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
        conn=conn, strict=True)
    expect = {"strategy_id": sid, "page_id": page["id"], "decision": "demote", "phase": to,
              "phase_from": frm}
    return _demoted_answer(sid, frm, to, page), expect


async def _decide_locked(conn, action: str, page_id: int, token: str | None, *, user_id: int,
                         pressed_at: str, ctx: dict) -> tuple[str, dict | None]:
    """The body of the ONE transaction: lock the page, check it, decide it. Returns (the answer,
    what the committed state must show for a 'done' answer — None for a refusal). `ctx` receives
    the strategy id as soon as the page is read, so a failed transaction can still name it."""
    from agents.market_intelligence.db import log_audit_event

    page = await conn.fetchrow(_PAGE_FOR_UPDATE_SQL, page_id)
    if page is None:
        return await _refuse(conn, page_id=page_id, user_id=user_id, page=None, reason_code="no_such_page",
                             why=f"no such page (#{page_id})"), None
    page = dict(page)
    if isinstance(page.get("breached"), str):
        page["breached"] = json.loads(page["breached"])
    sid, frm = page["strategy_id"], page["phase_at_page"]
    ctx["strategy_id"] = sid
    if page["sent_at"] is None:
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="page_unsent",
            why=(f"page #{page_id} was never confirmed as sent, so it cannot be pressed; the next "
                 f"breach night re-pages {sid}. Nothing was changed.")), None
    expected = page.get("token") or ""
    if not token or not expected or not hmac.compare_digest(expected, token):
        # The real buttons stay pressable: nothing is marked on the page.
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="bad_token",
            why=(f"this press did not come from page #{page_id}'s own buttons (its token did not "
                 f"match); only the Demote / No action buttons on the page can decide it. Nothing "
                 f"was changed.")), None
    if page["decision"] is not None:
        who = page["decided_by"] if page["decided_by"] is not None else "the nightly ladder read"
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="already_decided",
            why=(f"page #{page_id} was already decided: {page['decision']} at "
                 f"{_when(page['decided_at'])} (by {who}). Nothing was changed.")), None
    episode = await conn.fetchrow(_EPISODE_STATE_SQL, sid, page["episode_on"])
    if episode is not None and episode["closed_on"] is not None:
        await conn.execute(_DECIDE_PAGE_SQL, "stale", user_id, page_id)
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="episode_ended",
            why=(f"this breach episode ended on {episode['closed_on']} ({episode['closed_by']}); the "
                 f"page's numbers are stale and nothing was changed. If you still want it: "
                 f"/strategy {sid} demote.")), None
    current = await conn.fetchval(_CURRENT_PHASE_SQL, sid)
    if current != frm:
        await conn.execute(_DECIDE_PAGE_SQL, "stale", user_id, page_id)
        return await _refuse(
            conn, page_id=page_id, user_id=user_id, page=page, reason_code="stale_phase",
            why=(f"{sid} has moved since this page: it showed {frm}, the registry says "
                 f"{current}. Nothing was changed; a new breach on {current} will page again.")), None
    if action == "noaction":
        await conn.execute(_DECIDE_PAGE_SQL, "no_action", user_id, page_id)
        await log_audit_event(
            NO_ACTION_EVENT,
            f"ladder page #{page_id}: No action — {sid} stays {frm} (pressed by {user_id})",
            json.dumps({"page_id": page_id, "strategy_id": sid, "phase": frm,
                        "pressed_by": user_id, "pressed_at": pressed_at,
                        "breached": page["breached"]}, default=str),
            conn=conn, strict=True)
        return ((f"No action recorded: {sid} stays {frm} (page #{page_id}). The same limits "
                 f"will not page again this episode; a newly breached one will."),
                {"strategy_id": sid, "page_id": page_id, "decision": "no_action", "phase": frm})
    if DEMOTE_TO.get(frm) != page["demote_to"]:
        return await _refuse(conn, page_id=page_id, user_id=user_id, page=page, reason_code="no_rung_below",
                             why=f"{frm} has no rung below it"), None
    return await _demote_on_page(conn, page, user_id=user_id, pressed_at=pressed_at)


async def _not_committed(conn, *, page_id: int, user_id, strategy_id: str | None, why: str) -> str:
    """The honest answer when the committed state does not show the decision: nothing moved."""
    sid = strategy_id or "the strategy"
    answer = (f"Not done — {why}; nothing was changed. Press the button again, or use "
              f"/strategy {sid} demote.")
    try:
        await _refuse(conn, page_id=page_id, user_id=user_id, page=None, reason_code="not_committed",
                      why=why, strict=False)
    except Exception as e:  # loud-ok: the DB is already sick here; the answer above is what matters
        logger.warning(f"ladder press: could not record the not-committed refusal: {e}")
    return answer


async def _confirmed(conn, answer: str, expect: dict, *, user_id) -> str:
    """Build the answer from the COMMITTED state: the page's decision and the strategy's phase,
    re-read after the transaction. A mismatch — the COMMIT that was really a ROLLBACK — answers
    'Not done', never the provisional success."""
    decision = await conn.fetchval(_PAGE_DECISION_SQL, expect["page_id"])
    phase = await conn.fetchval(_CURRENT_PHASE_SQL, expect["strategy_id"])
    if decision == expect["decision"] and phase == expect["phase"]:
        return answer
    return await _not_committed(
        conn, page_id=expect["page_id"], user_id=user_id, strategy_id=expect["strategy_id"],
        why=(f"the transaction did not commit — the registry says {expect['strategy_id']} is "
             f"{phase} and page #{expect['page_id']} is {decision or 'undecided'}"))


async def handle_ladder_press(action: str, page_id: int, *, user_id: int | None, token: str | None) -> str:
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
        ctx: dict = {}
        error: Exception | None = None
        answer, expect = "", None
        try:
            async with conn.transaction():
                answer, expect = await _decide_locked(conn, action, page_id, token, user_id=user_id,
                                                      pressed_at=pressed_at, ctx=ctx)
        except Exception as e:  # loud-ok: the transaction rolled back; the answer is built from the committed state below
            logger.exception(f"ladder press on page #{page_id} did not commit: {e}")
            error = e
        finally:
            # AFTER the transaction has committed (or rolled back): `update_strategy` invalidates
            # the process cache before the commit, and a concurrent `get_strategy()` in between
            # could re-cache the pre-commit row — so invalidate once more here, post-commit.
            invalidate_cache()
        if error is not None:
            return await _not_committed(
                conn, page_id=page_id, user_id=user_id, strategy_id=ctx.get("strategy_id"),
                why=f"the database refused the write ({type(error).__name__}: {str(error)[:120]})")
        if expect is not None:
            return await _confirmed(conn, answer, expect, user_id=user_id)
        return answer
