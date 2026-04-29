"""Telegram surface for the strategy maturity framework.

Commands:
    /strategies                       — list table (phase / on / 30d KPI / eligible)
    /strategy <id>                    — detail view (KPIs by model, blocking reasons)
    /strategy <id> enable             — set enabled = TRUE
    /strategy <id> disable            — set enabled = FALSE
    /strategy <id> promote            — advance phase (requires verdict.eligible)
    /strategy <id> demote             — step phase back (no eligibility check)

Every state change writes an `mi_audit_log` row so phase transitions are
auditable. `promote` is gated on `check_promotion_eligibility` — the
dispatcher refuses if blocking reasons remain.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from agents.market_intelligence.db import log_audit_event
from agents.market_intelligence.strategies.adapters import get_outcomes
from agents.market_intelligence.strategies.promotion import (
    WINDOW_DAYS,
    check_all_strategies,
    check_promotion_eligibility,
)
from agents.market_intelligence.strategies.registry import (
    get_strategy,
    load_strategies,
    update_strategy,
)

logger = logging.getLogger(__name__)

_DEMOTE_BACK = {"live": "paper", "paper": "shadow"}
_VALID_ACTIONS = {"enable", "disable", "promote", "demote"}


# ── Formatters ──────────────────────────────────────────────────────────────


def _fmt_kpi(verdict) -> str:
    """One-line KPI summary tailored to the promotion model."""
    m = verdict.metrics or {}
    if verdict.model == "unpaired_r":
        n = m.get("n_closed", 0)
        med = m.get("median_r")
        return f"med R {med if med is not None else '—'} (n={n})"
    if verdict.model == "paired_r":
        n = m.get("n_paired_closed", 0)
        delta = m.get("median_r_delta")
        return f"ΔR {delta if delta is not None else '—'} (n={n})"
    if verdict.model == "telemetry_review":
        n = m.get("n_climax_alerts", 0)
        return f"climax n={n}"
    return "—"


def _fmt_eligible(verdict) -> str:
    if verdict.next_phase is None:
        return "top"
    if verdict.eligible:
        return "✓"
    if verdict.blocking_reasons:
        return verdict.blocking_reasons[0]
    return "—"


async def render_strategies_table() -> str:
    """`/strategies` listing — monospace table per CLAUDE.md Telegram rules."""
    by_id = await load_strategies()
    if not by_id:
        return "No strategies registered."
    verdicts = await check_all_strategies()
    verdict_by_id = {v.strategy_id: v for v in verdicts}

    lines = [f"📋 *Strategies ({len(by_id)})*", "```"]
    lines.append(f"{'strategy':<18}{'phase':<8}{'on':<4}{'kpi':<22}eligible")
    for sid, s in sorted(by_id.items()):
        v = verdict_by_id.get(sid)
        on_flag = "✓" if s.enabled else "✗"
        kpi = _fmt_kpi(v) if v else "—"
        elig = _fmt_eligible(v) if v else "—"
        lines.append(f"{sid:<18}{s.phase:<8}{on_flag:<4}{kpi[:21]:<22}{elig[:24]}")
    lines.append("```")
    lines.append("_Detail:_ `/strategy <id>` · _Toggle:_ `/strategy <id> enable|disable`")
    return "\n".join(lines)


async def render_strategy_detail(strategy_id: str) -> str:
    s = await get_strategy(strategy_id)
    if s is None:
        return f"Unknown strategy `{strategy_id}`. See `/strategies`."

    # Fetch the wider promotion window once and reuse — promotion needs 90d
    # for eligibility, the "Recent closed" list slices to 30d below.
    all_rows = await get_outcomes(strategy_id, window_days=WINDOW_DAYS)
    v = await check_promotion_eligibility(strategy_id, rows=all_rows)
    cutoff = date.today() - timedelta(days=30)
    rows = [r for r in all_rows if r.alert_date >= cutoff]

    lines = [
        f"📌 *{s.strategy_id}* — {s.name}",
        f"Phase: `{s.phase}` · Enabled: {'✓' if s.enabled else '✗'} · Family: `{s.family}`",
        f"Model: `{s.promotion_model}` · Outcomes table: `{s.outcomes_table}`",
    ]
    if s.notes:
        lines.append(f"_{s.notes}_")
    lines.append("")

    if v is not None:
        if v.next_phase is None:
            lines.append("*Promotion:* already at top of ladder")
        else:
            lines.append(f"*Promotion to `{v.next_phase}`* — eligible: {'✓' if v.eligible else '✗'}")
            if v.metrics:
                metrics_lines = [f"  · {k}: {val}" for k, val in v.metrics.items()]
                lines.extend(metrics_lines)
            if v.blocking_reasons:
                lines.append("  Blocking:")
                for reason in v.blocking_reasons:
                    lines.append(f"    – {reason}")
    lines.append("")

    closed_rows = [r for r in rows if r.status == "closed"][-5:]
    if closed_rows:
        lines.append("*Recent closed (last 5):*")
        for r in closed_rows:
            r_str = f"{r.r_multiple:+.2f}R" if r.r_multiple is not None else "—"
            pnl_str = f"${r.pnl:+,.0f}" if r.pnl is not None else ""
            lines.append(f"  • `{r.ticker}` {r.alert_date.isoformat()}  {r_str}  {pnl_str}")
    else:
        lines.append("_No closed outcomes in the last 30d._")
    return "\n".join(lines)


# ── Action handlers ─────────────────────────────────────────────────────────


async def _do_enable_disable(strategy_id: str, *, enable: bool) -> str:
    s = await get_strategy(strategy_id)
    if s is None:
        return f"Unknown strategy `{strategy_id}`."
    if s.enabled == enable:
        state = "enabled" if enable else "disabled"
        return f"`{strategy_id}` already {state}."
    updated = await update_strategy(strategy_id, enabled=enable)
    if updated is None:
        return f"Update failed for `{strategy_id}`."
    verb = "enabled" if enable else "disabled"
    await log_audit_event(
        "strategy_phase_change",
        f"{strategy_id} {verb}",
        detail=json.dumps({"enabled_from": s.enabled, "enabled_to": enable}),
    )
    return f"`{strategy_id}` {verb}."


async def _do_promote(strategy_id: str) -> str:
    s = await get_strategy(strategy_id)
    if s is None:
        return f"Unknown strategy `{strategy_id}`."
    v = await check_promotion_eligibility(strategy_id)
    if v is None or v.next_phase is None:
        return f"`{strategy_id}` already at top of ladder — cannot promote."
    if not v.eligible:
        bullets = "\n".join(f"  – {r}" for r in v.blocking_reasons)
        return f"`{strategy_id}` not eligible for promotion to `{v.next_phase}`:\n{bullets}"
    updated = await update_strategy(strategy_id, phase=v.next_phase)
    if updated is None:
        return f"Promotion failed for `{strategy_id}`."
    await log_audit_event(
        "strategy_phase_change",
        f"{strategy_id} promoted {s.phase} → {v.next_phase}",
        detail=json.dumps({
            "phase_from": s.phase,
            "phase_to": v.next_phase,
            "model": v.model,
            "metrics": v.metrics,
        }, default=str),
    )
    return f"`{strategy_id}` promoted: `{s.phase}` → `{v.next_phase}` ✓"


async def _do_demote(strategy_id: str) -> str:
    s = await get_strategy(strategy_id)
    if s is None:
        return f"Unknown strategy `{strategy_id}`."
    target = _DEMOTE_BACK.get(s.phase)
    if target is None:
        return f"`{strategy_id}` already at bottom (`shadow`) — cannot demote."
    updated = await update_strategy(strategy_id, phase=target)
    if updated is None:
        return f"Demotion failed for `{strategy_id}`."
    await log_audit_event(
        "strategy_phase_change",
        f"{strategy_id} demoted {s.phase} → {target}",
        detail=json.dumps({"phase_from": s.phase, "phase_to": target}),
    )
    return f"`{strategy_id}` demoted: `{s.phase}` → `{target}`"


# ── Public dispatchers (called from agent.py) ───────────────────────────────


async def handle_strategies_command() -> str:
    """`/strategies` — list table."""
    return await render_strategies_table()


async def handle_strategy_action(body: str) -> str:
    """Parse `<id> [action]` and dispatch.

    Empty body → list. `<id>` alone → detail. `<id> <action>` → mutation.
    """
    body = (body or "").strip()
    if not body:
        return await render_strategies_table()
    parts = body.split()
    strategy_id = parts[0].lower()
    if len(parts) == 1:
        return await render_strategy_detail(strategy_id)
    action = parts[1].lower()
    if action not in _VALID_ACTIONS:
        return (
            f"Unknown action `{action}`. Valid: {', '.join(sorted(_VALID_ACTIONS))}.\n"
            f"Usage: `/strategy <id> <action>`"
        )
    if action == "enable":
        return await _do_enable_disable(strategy_id, enable=True)
    if action == "disable":
        return await _do_enable_disable(strategy_id, enable=False)
    if action == "promote":
        return await _do_promote(strategy_id)
    if action == "demote":
        return await _do_demote(strategy_id)
    return f"Unhandled action `{action}`."
