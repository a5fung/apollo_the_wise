"""Ladder watchdog — ADR 0022 §1 auto-DEMOTION, built DARK (#312, 2026-10-15).

WHAT IT IS. The nightly `ladder_watchdog` step the ADR specifies ("evaluates `demotion_triggers`
per live/paper strategy against DB ground truth"), built as the operator asked on 2026-10-12:
*"ships dark; any live flip is his sign-off."* Every night it computes the four signed M1f
triggers (ADR 0022 §7, operator-signed 2026-07-05: 6 consecutive losses · trailing-20
expectancy < −0.3R · drawdown −10R from the cumulative-R peak · 1 harmful auto-action) for every
ENABLED strategy on a rung that HAS a rung below it (phase 'paper' or 'live'), against the ONE
book that strategy's phase resolves to (`resolve_account_mode_for_strategy` — dual-account
invariant 3: `account_mode` on every trade query), and writes ONE `mi_audit_log` row
(`ladder_demotion_shadow`) listing, per strategy, each trigger's value, its threshold and
`would_demote`.

WHAT IT IS NOT — and this is structural, not a flag. This module has NO act step:
  * it never writes `mi_strategies` (no `update_strategy`, no UPDATE statement — the only
    phase writer in the repo stays `strategies/registry.update_strategy`, reached today only
    by the operator's `/strategy <id> promote|demote`);
  * it touches no sizing (`position_size_multiplier`), no toggle, no order path;
  * it sends NO Telegram — a would-demote is an audit row the weekly review can read; the only
    page this job can ever produce is the scheduler's standard `notify_job_failure` when the
    job itself crashes, which carries no verdict;
  * there is no "live mode" switch a typo could enable — the act step does not exist yet.
Pinned by `tests/test_ladder_watchdog.py` (the DB layer is spied: a synthetic breach of every
trigger produces the row and ZERO writes to `mi_strategies` or any order/sizing path).
Building the act step is a later, operator-signed build (THE LINE) — it also needs the L1
pieces this dark build does not: a `demotion_triggers` column (the thresholds below are code
constants with their provenance), `phase_history`, and the mandatory review-before-re-promotion.

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

import json
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.market_intelligence.kill_scale_bands import (
    _mean_tail,
    current_losing_streak,
    risk_placed,
)
from agents.market_intelligence.rule_eras import era_split_sentence, split_current_vs_older

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

AUDIT_EVENT = "ladder_demotion_shadow"
ERROR_EVENT = "ladder_watchdog_error"
JOB_ID = "ladder_watchdog"

# ADR 0022 §7 M1f — operator-signed 2026-07-05 ("Signed.", the recommendations as written).
# Code constants with provenance; the registry column (`demotion_triggers JSONB`, L1) lands with
# the act step, when a row value would govern something. Change ONLY via CHANGE_PROCESS.
M1F_DEMOTION_TRIGGERS: dict[str, float | int] = {
    "consec_losses": 6,              # current losing streak ≥ 6
    "trailing20_expectancy_r": -0.3,  # mean R of the last 20 closed trades < −0.3R
    "dd_from_peak_r": -10.0,          # cumulative R is ≥ 10R below its running peak
    "harmful_auto_action": 1,         # ≥ 1 operator-labelled harmful executed auto-action
}
TRAILING_WINDOW = 20
MIN_CLOSED_TRADES = 6
R_TRIGGERS = ("consec_losses", "trailing20_expectancy_r", "dd_from_peak_r")

# The rung a breach WOULD step down to. Must equal `strategies/telegram._DEMOTE_BACK` (the
# operator's manual `/strategy <id> demote`) — pinned by the test so the dark row can never
# name a rung the real command would not step to. 'shadow' / 'deprecated' have no rung below
# and are not evaluated (shadow is the bottom; deprecated is terminal, ADR 0022 §1).
DEMOTE_TO = {"live": "paper", "paper": "shadow"}

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
    ORDER BY alert_date ASC, id ASC
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


# ── Data (DB-sourced; read-only) ────────────────────────────────────────────────────────────


async def fetch_closed_r_series(conn, signal_type: str, account_mode: str, *, today: date) -> dict:
    """The strategy's closed methodology trades on ONE book as a chronological realised-R
    series (denominator = `kill_scale_bands.risk_placed`, rows without an R frame excluded and
    counted), plus the #662 era split as REPORT ONLY."""
    rows = await conn.fetch(_CLOSED_TRADES_SQL, signal_type, account_mode)
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


# ── The nightly step ────────────────────────────────────────────────────────────────────────


def _summary(as_of: date, evaluated: list[dict]) -> str:
    who = ", ".join(f"{e['strategy_id']}/{e['account_mode']}" for e in evaluated) or "none"
    n_would = sum(1 for e in evaluated if e["would_demote"])
    return (f"ladder watchdog (DARK) {as_of.isoformat()}: {len(evaluated)} evaluated ({who}) · "
            f"{n_would} would demote · acted: none")


async def run_ladder_watchdog(*, today: date | None = None) -> dict:
    """One nightly pass → ONE `ladder_demotion_shadow` audit row. Returns the row's detail.

    Reads the registry and `mi_live_trades`; writes `mi_audit_log` only. A failure writes a
    `ladder_watchdog_error` row and RE-RAISES so `audit_wrap` records the run as failed and the
    scheduler's standard job-failure page fires — a dead watchdog must not look like a quiet
    one (the only Telegram this job can produce, and it carries no verdict)."""
    from agents.market_intelligence.constants import resolve_account_mode_for_strategy
    from agents.market_intelligence.db import get_pool, log_audit_event
    from agents.market_intelligence.strategies.registry import _load_all
    from shared.dates import et_today

    as_of = today or et_today()
    try:
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

        series: dict[str, tuple[str, dict]] = {}
        pool = await get_pool()
        async with pool.acquire() as conn:
            for s in targets:
                mode = resolve_account_mode_for_strategy(s)
                series[s.strategy_id] = (
                    mode, await fetch_closed_r_series(conn, s.signal_type, mode, today=as_of))
        # The connection is RELEASED before the audit write below — holding one while asking the
        # pool for a second is the 2026-09-17 deadlock class (tests/test_no_nested_pool_acquire).

        evaluated = []
        for s in targets:
            mode, data = series[s.strategy_id]
            v = evaluate_demotion_triggers(data["realized_rs"])
            evaluated.append({
                "strategy_id": s.strategy_id, "phase": s.phase, "account_mode": mode,
                "would_demote_to": DEMOTE_TO[s.phase],
                "n_closed": v["n_closed"], "rows_without_r_frame": data["rows_without_r_frame"],
                "era": data["era"], "by_era": data["by_era"],
                "cum_r": v["cum_r"], "max_dd_r": v["max_dd_r"],
                "triggers": v["triggers"], "would_demote": v["would_demote"],
                "reasons": v["reasons"],
            })

        detail = {
            "as_of": as_of.isoformat(),
            "ran_at_et": datetime.now(_ET).isoformat(timespec="seconds"),
            "mode": "dark",
            "thresholds": dict(M1F_DEMOTION_TRIGGERS),
            "min_closed_trades": MIN_CLOSED_TRADES,
            "evaluated": evaluated,
            "skipped": skipped,
            "would_demote_count": sum(1 for e in evaluated if e["would_demote"]),
            "acted": False,
            "note": ("DARK — this module has no phase/sizing/order path; a would-demote is this "
                     "row, nothing else. Any live flip is operator sign-off (THE LINE)."),
        }
        await log_audit_event(AUDIT_EVENT, _summary(as_of, evaluated),
                              json.dumps(detail, default=str))
        return detail
    except Exception as e:
        logger.error(f"ladder watchdog failed: {e}", exc_info=True)
        try:
            await log_audit_event(ERROR_EVENT, f"ladder watchdog failed: {e}",
                                  json.dumps({"as_of": as_of.isoformat(), "error": str(e)}))
        except Exception as e2:
            logger.warning(f"ladder watchdog: error-row write also failed: {e2}")
        raise
