"""Ladder watchdog — ADR 0022 §1 demotion: the nightly READ, and on a breach HIS page (#312).

WHAT IT IS. The nightly `ladder_watchdog` step the ADR specifies. Every night it computes the four
signed M1f triggers (ADR 0022 §7, operator-signed 2026-07-05: 6 consecutive losses · trailing-20
expectancy < −0.3R · drawdown −10R from the cumulative-R peak · 1 harmful auto-action) for every
ENABLED strategy on a rung that HAS a rung below it (phase 'paper' or 'live'), against the ONE
book that strategy's phase resolves to (`resolve_account_mode_for_strategy` — dual-account
invariant 3: `account_mode` on every trade query), and writes ONE `mi_audit_log` row
(`ladder_demotion_shadow`) listing, per strategy, each trigger's value, its threshold and
`would_demote`. One row per night: see `_summary_prefix`.

THE ACT STEP IS HIS PRESS (ruled 2026-11-04: *"i want explicit action from me to demote, so i review
stats present to me and a one-click demote or no action"*; it replaced the 07-05 "automatic"). On a
breach this module sends him ONE Telegram page — the strategy and its rung, each limit's value
against its bar, closed trades, cumulative R, open positions (count + tickers) — with two buttons:
**Demote to <the rung below>** and **No action**. The press travels `channels/telegram.py`
(`ladder:` callback, behind the shared authorization gate) → the market agent's internal
`/ladder_press` → `ladder_press.handle_ladder_press`, which is the ONLY place a page moves a phase:
one rung down, through the one writer `strategies/registry.update_strategy`, compare-and-set on the
rung the page SHOWED, in one transaction with the page's decision, writing `strategy_phase_change`
(the same event the typed `/strategy <id> demote` writes). No action writes an audit row and moves
nothing. Shadow is the bottom rung — never evaluated, never paged, and the keyboard builder draws no
Demote button for a rung with nothing below.

PAGING CADENCE — the default, written here and in the SSoT as a decision HE can override:
ONE page per strategy per breach EPISODE. An episode opens on the first would-demote night on a
rung and closes on the first night with no limit breached (or when the rung changes — his Demote
press or the typed command — because the rung below is a different book and a fresh question).
Inside an episode a second breach night sends nothing (the first page's buttons are still live).
After No action there is no re-page in the same episode UNLESS a limit that was not breached at the
last page newly breaches — then one more page, same episode, listing what is new. The state lives
in the DB (`mi_ladder_episodes`, `mi_ladder_pages`), never in process memory, so a restart cannot
re-page. A page whose send failed does not count (`sent_at` stays NULL, `ladder_page_send_error`
is written, the next night retries) — the send itself is tried `1 + len(SEND_RETRY_DELAYS)` times
inside the run, so one Telegram blip does not cost a trading day. A #672 recovery re-run NEVER
pages: every Telegram it sends is held at the httpx layer and reports success without reaching
him, so the re-run records what it would have paged and leaves the episode unpaged for the next
live night.

A STRATEGY THAT LEAVES THE LADDER ENDS ITS EPISODE (#312 review, 2026-11-07). A strategy demoted
to shadow (his press on a paper page, or the typed command) or disabled is skipped by the nightly
read and would never reach the close path, so its episode stayed open and its page stayed
pressable on stale numbers — and when he promoted it back, the pooled series still breached the
same limits, the old episode read as "already paged", and NOTHING was sent (the DoD's own
WOULD-FAIL-IF). Now every skipped strategy's open episode is closed (`phase_moved`) and its
undecided pages are marked `stale`, so the return pages afresh. The same stale-marking applies
when a rung change closes an episode in the paging pass. And the rung is RE-READ (one primary-key
read of the committed row, `registry.get_strategy_fresh`) right before a page is inserted: a press
or a typed command that lands between the registry read at the top of the run and the page would
otherwise page a rung the strategy has already left.

THE PAGE'S OWN TOKEN. Each page carries a random token (`mi_ladder_pages.token`, 32 url-safe
chars) and both buttons carry it (`ladder:<action>:<page id>:<token>`); the press refuses without
it. The button data is the only thing that holds the token, so a `/ladder_press` arriving by any
other route — the orchestrator's LLM, a typed message — moves nothing (`ladder_press.py`).

WHAT IT IS NOT — and this is structural, not a flag. This module has NO phase writer:
  * it never calls `update_strategy`, never names `mi_strategies` (it reads the registry through
    `registry._load_all`), touches no sizing (`position_size_multiplier`), no toggle, no order path;
  * the only writes it makes are the audit rows and its own page / episode rows;
  * there is no "auto mode" switch a typo could enable — the phase moves only in `ladder_press.py`,
    only on his press.
Pinned by `tests/test_ladder_watchdog.py` (a spied DB layer) and `tests/test_312_ladder_act_step.py`
(every `update_strategy(phase=…)` call in the codebase, derived by AST: the typed promote, the typed
demote and the button — nothing else).

WHAT COUNTS AS R. `kill_scale_bands.risk_placed` — the ONE realised-R denominator (#586: the
risk AT the placed stop, after the 20% notional cap), over `status='closed'` methodology trades
(`pnl_attribution IS NULL` — the 09-01 voided cohort is still in the table and must not be
scored), chronological by entry (`alert_date, id`), the same convention as the signed kill/scale
bands so "consecutive losses" means the same thing on both instruments. A breakeven (r ≤ 0)
counts as a loss, as in the #268 calibration's worst-streak.

ERA. The verdict is computed on the POOLED series — that is what the M1f numbers were signed
against; a current-era-only verdict would change what the signed thresholds mean, which is not
this module's call. The rule-era split (#662, `rule_eras.split_current_vs_older`, with each
row's own `exit_rule` stamp so era E labels correctly) rides in the row as REPORT ONLY, exactly
as the kill/scale bands carry it.

DATA FLOOR. `MIN_CLOSED_TRADES` (6 — the smallest trigger's own window: six consecutive losses
need six trades) below which every trigger reads "not enough data" and nothing can breach; the
trailing-20 trigger additionally needs 20 trades (its window), and says so. These are judgement
calls recorded in the #312 commit, not signed numbers.

The 4th trigger ("1 harmful auto-action", ADR 0017 §4: a harmful EXECUTED judge action,
operator-labelled) has no source today — `mgmt_judge.py` is at L0 SHADOW with zero execution
authority, so nothing auto-executes and nothing can be labelled harmful. The row records it as
`not measurable yet` rather than inventing a definition.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets as _secrets
from datetime import date, datetime
from typing import Any

# The rung a breach steps down to — the ONE map the operator's typed `/strategy <id> demote` steps
# by too (`strategies/telegram._DEMOTE_BACK`), so a page can never name a rung the real command
# would not step to. Re-exported here: `ladder_press` and the tests read `ladder_watchdog.DEMOTE_TO`.
# 'shadow' / 'deprecated' have no rung below and are not evaluated (ADR 0022 §1).
from agents.market_intelligence.constants import DEMOTE_TO
from agents.market_intelligence.kill_scale_bands import (
    _mean_tail,
    current_losing_streak,
    risk_placed,
)
from agents.market_intelligence.rule_eras import era_split_sentence, split_current_vs_older
from shared.dates import _ET
from shared.telegram_format import b, esc, pre

logger = logging.getLogger(__name__)

AUDIT_EVENT = "ladder_demotion_shadow"      # the nightly row (the name predates the act step; kept for continuity)
PAGED_EVENT = "ladder_breach_paged"         # one per page that reached Telegram
CLEARED_EVENT = "ladder_breach_cleared"     # an open episode closed by a night with nothing breached
SEND_ERROR_EVENT = "ladder_page_send_error" # the page did not send — the nightly error sweep shows it
JOB_ID = "ladder_watchdog"
CALLBACK_PREFIX = "ladder:"                 # channels/telegram.py routes `ladder:<demote|noaction>:<page id>:<token>`
# The page send is retried inside the run after these pauses (seconds) — one Telegram blip must not
# cost a trading day (#312 review, finding 6). Tests set it to () to skip the sleeps.
SEND_RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0)
TOKEN_BYTES = 24                            # secrets.token_urlsafe(24) → 32 chars; the button data stays under 64 bytes

# ADR 0022 §7 M1f — operator-signed 2026-07-05 ("Signed.", the recommendations as written).
# Code constants with provenance; the registry column (`demotion_triggers JSONB`, L1) lands when a
# row value would govern something. Change ONLY via CHANGE_PROCESS.
M1F_DEMOTION_TRIGGERS: dict[str, float | int] = {
    "consec_losses": 6,              # current losing streak ≥ 6
    "trailing20_expectancy_r": -0.3,  # mean R of the last 20 closed trades < −0.3R
    "dd_from_peak_r": -10.0,          # cumulative R is ≥ 10R below its running peak
    "harmful_auto_action": 1,         # ≥ 1 operator-labelled harmful executed auto-action
}
TRAILING_WINDOW = 20
MIN_CLOSED_TRADES = 6
R_TRIGGERS = ("consec_losses", "trailing20_expectancy_r", "dd_from_peak_r")
# Plain words on the page (operator: every number carries its meaning).
TRIGGER_LABELS = {
    "consec_losses": "losing streak",
    "trailing20_expectancy_r": "mean R, last 20 trades",
    "dd_from_peak_r": "drawdown from the peak",
    "harmful_auto_action": "harmful auto-action",
}

HARMFUL_NOT_MEASURABLE = (
    "not measurable yet — no auto-action lane exists (mgmt_judge.py is L0 SHADOW, zero "
    "execution authority; ADR 0017 §4), so no harmful-action label source"
)

_CLOSED_TRADES_SQL = """
    SELECT total_pnl, risk_dollars_actual, entry_shares, entry_price, hard_stop,
           alert_date, signal_type, exit_rule
    FROM mi_live_trades
    WHERE status = 'closed' AND signal_type = $1 AND account_mode = $2
      AND pnl_attribution IS NULL
      AND alert_date <= $3
      AND COALESCE((closed_at AT TIME ZONE 'America/New_York')::date, alert_date) <= $3
    ORDER BY alert_date ASC, id ASC
"""

# The strategy's open positions on ITS book (the page names them; their stops and exits read the
# trade row's own account_mode, so a demote never moves them — tests/test_312_ladder_act_step.py §C).
_OPEN_POSITIONS_SQL = """
    SELECT ticker FROM mi_live_trades
    WHERE status = 'filled' AND remaining_shares > 0
      AND signal_type = $1 AND account_mode = $2
    ORDER BY ticker
"""

# Is tonight's row already there? Keyed on the summary prefix — see `_summary_prefix`. Two
# patterns: tonight's prefix and the pre-act-step "(DARK)" spelling, so a re-run of a night
# written before 2026-11-07 still finds its row.
_NIGHT_ROW_EXISTS_SQL = """
    SELECT 1 FROM mi_audit_log
    WHERE event_type = $1 AND (summary LIKE $2 OR summary LIKE $3) LIMIT 1
"""

# ── The paging cadence's state (mi_ladder_episodes / mi_ladder_pages — DDL in db._LADDER_DDL) ──
_OPEN_EPISODE_SQL = """
    SELECT strategy_id, opened_on, phase, closed_on, closed_by
    FROM mi_ladder_episodes
    WHERE strategy_id = $1 AND closed_on IS NULL
    ORDER BY opened_on DESC LIMIT 1
"""
# The same "latest open episode" read for many strategies at once (`end_episodes_of_skipped`).
_OPEN_EPISODES_OF_SQL = """
    SELECT DISTINCT ON (strategy_id) strategy_id, opened_on, phase
    FROM mi_ladder_episodes
    WHERE strategy_id = ANY($1) AND closed_on IS NULL
    ORDER BY strategy_id, opened_on DESC
"""
_LAST_SENT_PAGE_SQL = """
    SELECT id, as_of, breached, decision
    FROM mi_ladder_pages
    WHERE strategy_id = $1 AND episode_on = $2 AND sent_at IS NOT NULL
    ORDER BY as_of DESC, id DESC LIMIT 1
"""
_CLOSE_EPISODE_SQL = """
    UPDATE mi_ladder_episodes SET closed_on = $1, closed_by = $2
    WHERE strategy_id = $3 AND opened_on = $4 AND closed_on IS NULL
"""
_OPEN_EPISODE_INSERT_SQL = """
    INSERT INTO mi_ladder_episodes (strategy_id, opened_on, phase) VALUES ($1, $2, $3)
    ON CONFLICT (strategy_id, opened_on) DO NOTHING
"""
_INSERT_PAGE_SQL = """
    INSERT INTO mi_ladder_pages (strategy_id, episode_on, as_of, phase_at_page, demote_to, breached, stats, token)
    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8)
    ON CONFLICT (strategy_id, as_of) DO NOTHING
    RETURNING id
"""
_MARK_PAGE_SENT_SQL = "UPDATE mi_ladder_pages SET sent_at = NOW() WHERE id = $1"
# A closed episode's undecided pages are stale: the press refuses them, and `decided_by` NULL says
# the nightly read — not a person — decided it.
_STALE_OPEN_PAGES_SQL = """
    UPDATE mi_ladder_pages SET decision = 'stale', decided_at = NOW()
    WHERE strategy_id = $1 AND episode_on = $2 AND decision IS NULL
"""


# ── Pure core ───────────────────────────────────────────────────────────────────────────────


def drawdown_from_peak(rs: list[float]) -> tuple[float, float]:
    """(CURRENT drawdown of cumulative R from its running peak, WORST drawdown seen) — both ≤ 0.
    The trigger reads the current value (a state that clears when the equity curve recovers,
    like the drawdown breaker); the worst value rides in the row for the reader."""
    cum = peak = 0.0
    worst = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    return cum - peak, worst


def _trigger(value: Any, threshold: Any, breached: bool, status: str = "evaluated") -> dict:
    return {"value": value, "threshold": threshold, "breached": bool(breached), "status": status}


def evaluate_demotion_triggers(realized_rs, thresholds: dict | None = None) -> dict:
    """Pure: the four M1f triggers over a chronological (oldest→newest) realised-R series.

    Returns {n_closed, triggers: {name: {value, threshold, breached, status}}, would_demote,
    reasons, cum_r, max_dd_r}. `would_demote` is True iff ANY trigger is breached; a trigger
    whose window is not filled is `status: not enough data` and can never breach."""
    th = {**M1F_DEMOTION_TRIGGERS, **(thresholds or {})}
    rs = [float(r) for r in realized_rs if r is not None]
    n = len(rs)
    triggers: dict[str, dict] = {}
    cum_r = round(sum(rs), 4) if rs else 0.0
    max_dd_r = 0.0
    if n < MIN_CLOSED_TRADES:
        status = f"not enough data ({n} closed < {MIN_CLOSED_TRADES})"
        for name in R_TRIGGERS:
            triggers[name] = _trigger(None, th[name], False, status)
    else:
        streak = current_losing_streak(rs)
        triggers["consec_losses"] = _trigger(streak, th["consec_losses"],
                                             streak >= th["consec_losses"])
        t20 = _mean_tail(rs, TRAILING_WINDOW)
        if t20 is None:
            triggers["trailing20_expectancy_r"] = _trigger(
                None, th["trailing20_expectancy_r"], False,
                f"not enough data ({n} closed < {TRAILING_WINDOW} window)")
        else:
            triggers["trailing20_expectancy_r"] = _trigger(
                round(t20, 4), th["trailing20_expectancy_r"],
                t20 < th["trailing20_expectancy_r"])
        dd, max_dd_r = drawdown_from_peak(rs)
        max_dd_r = round(max_dd_r, 4)
        triggers["dd_from_peak_r"] = _trigger(round(dd, 4), th["dd_from_peak_r"],
                                              dd <= th["dd_from_peak_r"])
    triggers["harmful_auto_action"] = _trigger(None, th["harmful_auto_action"], False,
                                               HARMFUL_NOT_MEASURABLE)
    reasons = [f"{name} {t['value']} vs {t['threshold']}"
               for name, t in triggers.items() if t["breached"]]
    return {"n_closed": n, "triggers": triggers, "would_demote": bool(reasons),
            "reasons": reasons, "cum_r": cum_r, "max_dd_r": max_dd_r}


def breached_names(triggers: dict) -> list[str]:
    """The limits breached, in the page's order."""
    return [name for name in TRIGGER_LABELS if triggers.get(name, {}).get("breached")]


def decide_page(*, would_demote: bool, breached_now: list[str], phase: str,
                open_episode: dict | None, last_page: dict | None) -> tuple[str, str]:
    """Pure: the paging cadence. → (action, reason), action in {'page', 'skip', 'close', 'none'}.

    `open_episode` is the strategy's open episode row ({opened_on, phase}) or None; `last_page`
    the newest DELIVERED page of that episode ({id, breached}) or None."""
    if not would_demote:
        if open_episode is None:
            return "none", "no limit breached, no open episode"
        return "close", "no limit breached tonight"
    if open_episode is None:
        return "page", "new episode"
    if open_episode["phase"] != phase:
        return "page", f"new episode (the rung changed: {open_episode['phase']} → {phase})"
    if last_page is None:
        return "page", "episode has no delivered page yet"
    newly = sorted(set(breached_now) - set(last_page["breached"] or []))
    if newly:
        return "page", f"newly breached since page #{last_page['id']}: {', '.join(newly)}"
    return "skip", f"already paged this episode (page #{last_page['id']}, nothing newly breached)"


def _fmt_r(v) -> str:
    return "n/a" if v is None else f"{float(v):+.2f}R"


def _limit_rows(triggers: dict) -> list[tuple[str, str, str, str]]:
    rows = []
    for name, label in TRIGGER_LABELS.items():
        t = triggers.get(name)
        if t is None:
            continue
        if name == "consec_losses":
            value, bar = ("n/a" if t["value"] is None else str(t["value"])), str(t["threshold"])
        elif name == "harmful_auto_action":
            value, bar = "n/a", str(t["threshold"])
        else:
            value, bar = _fmt_r(t["value"]), _fmt_r(t["threshold"])
        if t["breached"]:
            state = "BREACHED"
        elif t["status"] == "evaluated":
            state = "ok"
        elif t["status"].startswith("not measurable yet"):
            state = "not measurable yet"
        else:
            state = t["status"]
        rows.append((label, value, bar, state))
    return rows


def format_breach_page(e: dict, *, page_id: int, as_of: date) -> str:
    """The page body, as Telegram HTML (shared helpers; a monospace block, never a pipe table).
    The book tag (#699: the tag picks the chat) is prepended by the sender, `page_breaches`, from
    the strategy's RESOLVED mode — the function that tags is the function that sends."""
    sid, phase, below = e["strategy_id"], e["phase"], e["would_demote_to"]
    rows = _limit_rows(e["triggers"])
    w0 = max(len(r[0]) for r in rows) + 2
    w1 = max(len("value"), *(len(r[1]) for r in rows)) + 2
    w2 = max(len("bar"), *(len(r[2]) for r in rows)) + 2
    table = [f"{'limit':<{w0}}{'value':<{w1}}{'bar':<{w2}}"]
    table += [f"{lbl:<{w0}}{val:<{w1}}{bar:<{w2}}{state}" for lbl, val, bar, state in rows]
    pos = e.get("open_positions") or {"count": 0, "tickers": []}
    open_line = f"open positions {pos['count']}"
    if pos["count"]:
        open_line += (f" — {esc(', '.join(pos['tickers']))} (their stops and exits stay on the "
                      f"{esc(e['account_mode'])} book)")
    lines = [
        f"🪜 {b(f'Ladder breach — {sid} ({phase})')}",
        f"Your call: {b(f'Demote to {below}')} or {b('No action')}. Nothing moves until you press.",
        pre("\n".join(table)),
        (f"closed trades {e['n_closed']} · cumulative R {_fmt_r(e['cum_r'])} · "
         f"worst drawdown ever {_fmt_r(e['max_dd_r'])}"),
        open_line,
        f"Page #{page_id} · night {as_of.isoformat()} · the nightly ladder read (ADR 0022 §1)",
    ]
    return "\n".join(lines)


def build_ladder_keyboard(page_id: int, phase: str, token: str) -> dict:
    """The two buttons, each carrying the page id AND the page's own token (the press refuses
    without it). A rung with nothing below (shadow) gets no Demote button — the bottom rung
    cannot be demoted, so the page cannot offer it."""
    row = []
    below = DEMOTE_TO.get(phase)
    if below:
        row.append({"text": f"⬇️ Demote to {below}",
                    "callback_data": f"{CALLBACK_PREFIX}demote:{page_id}:{token}"})
    row.append({"text": "No action", "callback_data": f"{CALLBACK_PREFIX}noaction:{page_id}:{token}"})
    return {"inline_keyboard": [row]}


# ── Data (DB-sourced; read-only) ────────────────────────────────────────────────────────────


async def fetch_closed_r_series(conn, signal_type: str, account_mode: str, *, today: date) -> dict:
    """The strategy's closed methodology trades on ONE book as a chronological realised-R
    series (denominator = `kill_scale_bands.risk_placed`, rows without an R frame excluded and
    counted), plus the #662 era split as REPORT ONLY. `today` is the night being scored; the
    read is bounded to it (see `_summary_prefix`)."""
    rows = await conn.fetch(_CLOSED_TRADES_SQL, signal_type, account_mode, today)
    rs: list[float] = []
    meta: list[dict] = []
    no_frame = 0
    for t in rows:
        risk = risk_placed(t)
        if risk is None or risk <= 0:
            no_frame += 1
            continue
        rs.append(float(t["total_pnl"]) / risk)
        meta.append({"alert_date": t["alert_date"], "signal_type": t["signal_type"],
                     "exit_rule": t["exit_rule"]})
    era = split_current_vs_older(rs, meta, today) if rs else None
    return {
        "realized_rs": rs,
        "rows_without_r_frame": no_frame,
        "era": era_split_sentence(era) if era else None,
        "by_era": era["by_era"] if era else {},
    }


async def fetch_open_positions(conn, signal_type: str, account_mode: str) -> dict:
    """The strategy's open positions on ITS book: {count, tickers}."""
    rows = await conn.fetch(_OPEN_POSITIONS_SQL, signal_type, account_mode)
    tickers = [r["ticker"] for r in rows]
    return {"count": len(tickers), "tickers": tickers}


# ── The nightly step ────────────────────────────────────────────────────────────────────────


def _summary_prefix(as_of: date) -> str:
    """The head of the night's audit summary — the key `_NIGHT_ROW_EXISTS_SQL` matches on.

    ONE ROW PER NIGHT, PINNED TO THE NIGHT. The pass is stamped with `as_of` (the ET trading
    day; inside a #672 recovery re-run `et_today()` returns the missed slot's day). Two guards
    make a re-run of the same night honest: (1) the trade read is bounded to what that night
    could have seen — entered on or before `as_of` AND closed (ET date of `closed_at`, falling
    back to `alert_date` for a row with no `closed_at`) on or before `as_of` — so a late re-run
    does not score trades that closed afterwards; (2) when a row for that `as_of` already
    exists the write AND the paging are skipped (`row_already_written` on the returned dict),
    so a manual or recovery re-run cannot stack a second row or a second page (the first
    stands; to recompute, delete it). The key is the SUMMARY prefix, not `detail`: `detail` is a
    TEXT column whose JSON `_fit_audit_detail` may wrap in a truncation envelope, so a SQL cast
    of it is unsafe and a key inside it can vanish. NOT a lock — `max_instances=1` plus
    `jobs_in_flight()` already keep two runs of the job from overlapping."""
    return f"ladder watchdog {as_of.isoformat()}:"


def _legacy_summary_prefix(as_of: date) -> str:
    """The spelling every row before the act step (2026-11-07) carries."""
    return f"ladder watchdog (DARK) {as_of.isoformat()}:"


def _summary(as_of: date, evaluated: list[dict], paged: list[dict]) -> str:
    who = ", ".join(f"{e['strategy_id']}/{e['account_mode']}" for e in evaluated) or "none"
    n_would = sum(1 for e in evaluated if e["would_demote"])
    sent = ", ".join(p["strategy_id"] for p in paged if p["action"] == "paged") or "none"
    return (f"{_summary_prefix(as_of)} {len(evaluated)} evaluated ({who}) · "
            f"{n_would} would demote · paged: {sent} · acted: none (a phase moves only on his press)")


async def _end_episode(conn, sid: str, opened_on: date, closed_on: date, closed_by: str) -> None:
    """Close a breach episode on THIS connection. A `phase_moved` close also marks the episode's
    undecided pages stale (the rung they showed is gone, so a press must refuse them); a `cleared`
    close leaves them — the press refuses an ended episode on its own (`episode_ended`). The audit
    row, where there is one, stays with the caller."""
    await conn.execute(_CLOSE_EPISODE_SQL, closed_on, closed_by, sid, opened_on)
    if closed_by == "phase_moved":
        await conn.execute(_STALE_OPEN_PAGES_SQL, sid, opened_on)


async def page_breaches(as_of: date, evaluated: list[dict]) -> list[dict]:
    """The act step's SEND half: for each evaluated strategy, apply the paging cadence
    (`decide_page`) against the DB state, send the page where it says so, persist the page and
    the episode. Returns one record per strategy that produced an event — `action` in
    {paged, skipped, episode closed, held, send failed} — for the nightly row; a strategy with
    no breach and no open episode produces none.

    Telegram is never called while a pool connection is held; every audit row written inside a
    connection block hands that connection over (`log_audit_event(conn=...)` — never a second
    acquire). Writes nothing but audit rows and its own two tables."""
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.constants import strategy_mode_prefix
    from agents.market_intelligence.db import _jsonb_list_param, _jsonb_param, get_pool, log_audit_event
    from agents.market_intelligence.strategies.registry import get_strategy_fresh
    from shared.dates import recovery_pin

    pool = await get_pool()
    out: list[dict] = []
    for e in evaluated:
        sid, phase, mode = e["strategy_id"], e["phase"], e["account_mode"]
        breached_now = breached_names(e["triggers"])
        async with pool.acquire() as conn:
            ep = await conn.fetchrow(_OPEN_EPISODE_SQL, sid)
            ep = dict(ep) if ep else None
            last = await conn.fetchrow(_LAST_SENT_PAGE_SQL, sid, ep["opened_on"]) if ep else None
            last = dict(last) if last else None
        if last is not None and isinstance(last.get("breached"), str):
            last["breached"] = json.loads(last["breached"])
        action, reason = decide_page(would_demote=e["would_demote"], breached_now=breached_now,
                                     phase=phase, open_episode=ep, last_page=last)
        rec = {"strategy_id": sid, "action": None, "reason": reason, "page_id": None}
        if action == "none":
            continue
        if action == "close":
            closed_by = "cleared" if ep["phase"] == phase else "phase_moved"
            async with pool.acquire() as conn:
                await _end_episode(conn, sid, ep["opened_on"], as_of, closed_by)
                await log_audit_event(
                    CLEARED_EVENT,
                    f"{sid}/{mode}: the breach episode opened {ep['opened_on']} closed on "
                    f"{as_of.isoformat()} ({closed_by}) — no limit breached tonight",
                    json.dumps({"strategy_id": sid, "phase": phase, "episode_on": ep["opened_on"],
                                "closed_on": as_of, "closed_by": closed_by}, default=str),
                    conn=conn)
            rec["action"] = "episode closed"
            out.append(rec)
            continue
        if action == "skip":
            rec.update(action="skipped", page_id=last["id"])
            out.append(rec)
            continue
        # action == "page"
        if recovery_pin() is not None:
            rec.update(action="held", reason=(f"recovery re-run: a held Telegram reports success without "
                                              f"reaching him, so the episode stays unpaged for the next "
                                              f"live night — {reason}"))
            out.append(rec)
            continue
        # The rung NOW (#312 review, finding 7): a press or a typed command between the registry
        # read at the top of the run and this insert would page a rung the strategy has left (a
        # "live" page, and a live episode, for a strategy now at paper). One primary-key read of
        # the committed row — never the process cache; a mismatch skips tonight's page and the
        # next night reads the new rung afresh.
        fresh = await get_strategy_fresh(sid)
        live_phase = fresh.phase if fresh is not None else None
        if live_phase != phase:
            rec.update(action="skipped",
                       reason=(f"the rung moved during the run ({phase} → {live_phase}); tonight's "
                               f"read is stale — the next night reads the new rung"))
            out.append(rec)
            continue
        if ep is not None and ep["phase"] != phase:
            async with pool.acquire() as conn:
                await _end_episode(conn, sid, ep["opened_on"], as_of, "phase_moved")
            ep = None
        episode_on = ep["opened_on"] if ep else as_of
        token = _secrets.token_urlsafe(TOKEN_BYTES)
        async with pool.acquire() as conn:
            page_id = await conn.fetchval(
                _INSERT_PAGE_SQL, sid, episode_on, as_of, phase, e["would_demote_to"],
                _jsonb_list_param(breached_now), _jsonb_param(e), token)
        if page_id is None:
            # One page per strategy per night (UNIQUE): a same-night re-run whose first pass wrote
            # its page but lost its audit row (log_audit_event never raises) must not page twice.
            rec.update(action="skipped", reason="a page for tonight already exists (same-night re-run)")
            out.append(rec)
            continue
        # The book tag picks the chat (#699): a paper lane's breach goes to the paper chat, a
        # live strategy's to the main chat. From the RESOLVED mode — never the process default.
        text = strategy_mode_prefix(mode) + format_breach_page(e, page_id=page_id, as_of=as_of)
        keyboard = build_ladder_keyboard(page_id, phase, token)
        attempts = 1 + len(SEND_RETRY_DELAYS)
        ok = False
        for attempt, pause in enumerate((0.0, *SEND_RETRY_DELAYS), start=1):
            if pause:
                await asyncio.sleep(pause)
            ok = await send_telegram_message(text, parse_mode="HTML", reply_markup=keyboard)
            if ok:
                break
            logger.warning(f"ladder watchdog: breach page #{page_id} for {sid} did not send "
                           f"(attempt {attempt} of {attempts})")
        if not ok:
            logger.error(f"ladder watchdog: breach page #{page_id} for {sid} did not send after "
                         f"{attempts} attempts")
            await log_audit_event(
                SEND_ERROR_EVENT,
                f"{sid}/{mode}: breach page #{page_id} did not send after {attempts} attempts — the "
                f"episode is NOT paged; the next breach night retries",
                json.dumps({"strategy_id": sid, "phase": phase, "page_id": page_id, "as_of": as_of,
                            "breached": breached_now, "attempts": attempts}, default=str))
            rec.update(action="send failed", page_id=page_id)
            out.append(rec)
            continue
        async with pool.acquire() as conn:
            await conn.execute(_MARK_PAGE_SENT_SQL, page_id)
            if ep is None:
                await conn.execute(_OPEN_EPISODE_INSERT_SQL, sid, episode_on, phase)
            await log_audit_event(
                PAGED_EVENT,
                f"{sid}/{mode}: breach page #{page_id} sent ({reason}) — breached: "
                f"{', '.join(breached_now)}; Demote → {e['would_demote_to']} or No action is his press",
                json.dumps({"strategy_id": sid, "phase": phase, "page_id": page_id, "as_of": as_of,
                            "episode_on": episode_on, "breached": breached_now, "reason": reason},
                           default=str),
                conn=conn)
        rec.update(action="paged", page_id=page_id)
        out.append(rec)
    return out


async def end_episodes_of_skipped(conn, as_of: date, skipped: dict[str, str]) -> list[dict]:
    """A strategy that LEFT the ladder ends its breach episode (#312 review, finding 4).

    A strategy skipped by the nightly read — demoted to shadow (his press on a paper page, or the
    typed command) or disabled — never reaches `decide_page`'s close path, so its episode stayed
    open and its undecided page stayed pressable on stale numbers. Worse, promoted back later the
    pooled R series still breaches the same limits, `decide_page` reads the old episode as "already
    paged" and sends NOTHING — the DoD's own WOULD-FAIL-IF. So every skipped strategy's open episode
    is closed (`phase_moved`) and its undecided pages are marked stale, on the HELD connection (no
    second acquire). Idempotent: a re-run finds no open episode and writes nothing. Returns one
    record per episode ended, for the nightly row."""
    from agents.market_intelligence.db import log_audit_event
    out: list[dict] = []
    if not skipped:
        return out
    open_eps = {r["strategy_id"]: dict(r) for r in await conn.fetch(_OPEN_EPISODES_OF_SQL, sorted(skipped))}
    for sid in sorted(open_eps):
        ep = open_eps[sid]
        await _end_episode(conn, sid, ep["opened_on"], as_of, "phase_moved")
        await log_audit_event(
            CLEARED_EVENT,
            f"{sid}: the breach episode opened {ep['opened_on']} (rung {ep['phase']}) closed on "
            f"{as_of.isoformat()} (phase_moved) — the strategy left the ladder ({skipped[sid]}); its "
            f"undecided pages are stale, a return to the ladder pages afresh",
            json.dumps({"strategy_id": sid, "phase": ep["phase"], "episode_on": ep["opened_on"],
                        "closed_on": as_of, "closed_by": "phase_moved", "skipped": skipped[sid]},
                       default=str),
            conn=conn)
        out.append({"strategy_id": sid, "action": "episode closed",
                    "reason": f"left the ladder ({skipped[sid]}); undecided pages marked stale",
                    "page_id": None})
    return out


async def run_ladder_watchdog(*, today: date | None = None) -> dict:
    """One nightly pass → ONE `ladder_demotion_shadow` audit row, plus a breach page per the
    cadence above. Returns the row's detail.

    Reads the registry and `mi_live_trades`; writes `mi_audit_log` and its own page / episode
    rows. A crash propagates to `audit_wrap` (run 'failed', `job_failed_error` row, one deduped
    page). A re-run of a night that already has its row skips the write AND the paging and
    returns `row_already_written: True` — see `_summary_prefix`. A skipped strategy's open
    episode is always ended (`end_episodes_of_skipped`, idempotent)."""
    from agents.market_intelligence.constants import resolve_account_mode_for_strategy
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.strategies.registry import _load_all
    from shared.dates import et_today

    as_of = today or et_today()
    # The rows as they are TONIGHT, not the process cache: the operator hand-UPDATEs
    # `mi_strategies` (registry.py: a direct edit is unseen by `load_strategies()` until
    # restart), and a same-day phase change must not mislabel this row's phase / book.
    # `_load_all` is a fresh SELECT that mutates no shared state — the cache the entry
    # pipeline reads is untouched (never `load_strategies(force=True)` here).
    strategies = await _load_all()
    targets, skipped = [], {}
    for sid, s in sorted(strategies.items()):
        if s.phase not in DEMOTE_TO:
            skipped[sid] = f"phase={s.phase}: no rung below — nothing to demote"
        elif not s.enabled:
            skipped[sid] = f"disabled (phase={s.phase})"
        else:
            targets.append(s)

    evaluated = []
    pool = await get_pool()
    async with pool.acquire() as conn:
        already_written = bool(await conn.fetchval(
            _NIGHT_ROW_EXISTS_SQL, AUDIT_EVENT, _summary_prefix(as_of) + "%",
            _legacy_summary_prefix(as_of) + "%"))
        for s in targets:
            mode = resolve_account_mode_for_strategy(s)
            data = await fetch_closed_r_series(conn, s.signal_type, mode, today=as_of)
            v = evaluate_demotion_triggers(data["realized_rs"])
            evaluated.append({
                "strategy_id": s.strategy_id, "phase": s.phase, "account_mode": mode,
                "would_demote_to": DEMOTE_TO[s.phase],
                "n_closed": v["n_closed"], "rows_without_r_frame": data["rows_without_r_frame"],
                "era": data["era"], "by_era": data["by_era"],
                "cum_r": v["cum_r"], "max_dd_r": v["max_dd_r"],
                "triggers": v["triggers"], "would_demote": v["would_demote"],
                "reasons": v["reasons"],
                "open_positions": await fetch_open_positions(conn, s.signal_type, mode),
            })
        # A strategy that left the ladder (shadow / disabled) ends its open episode — on this held
        # connection, idempotent, so a re-run of the night writes nothing here.
        ended = await end_episodes_of_skipped(conn, as_of, skipped)
    # The connection is RELEASED before the paging and the audit write below — holding one
    # while asking the pool for a second is the 2026-09-17 deadlock class
    # (tests/test_no_nested_pool_acquire), and a Telegram send must never sit on a connection.

    paged = [] if already_written else ended + await page_breaches(as_of, evaluated)

    detail = {
        "as_of": as_of.isoformat(),
        "ran_at_et": datetime.now(_ET).isoformat(timespec="seconds"),
        "mode": "page",
        "thresholds": dict(M1F_DEMOTION_TRIGGERS),
        "min_closed_trades": MIN_CLOSED_TRADES,
        "evaluated": evaluated,
        "skipped": skipped,
        "would_demote_count": sum(1 for e in evaluated if e["would_demote"]),
        "paged": paged,
        "acted": False,
        "note": ("This job has no phase/sizing/order path: a breach is a PAGE to the operator "
                 "(Demote / No action); only his press moves a phase (ladder_press.py, THE LINE)."),
    }
    if already_written:
        logger.info(f"ladder watchdog: a row for {as_of.isoformat()} already exists — "
                    f"write and paging skipped")
        detail["row_already_written"] = True   # on the RETURNED dict only; the stored row stands
    else:
        await log_audit_event(AUDIT_EVENT, _summary(as_of, evaluated, paged),
                              json.dumps(detail, default=str))
    return detail
