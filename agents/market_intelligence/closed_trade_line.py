"""#696 — the /trades closed-trade line (pure; display only, changes no trade state).

Extracted from the `_handle_trades_detail` closure so it is testable. Each line shows the
trade's REALIZED R, taken from `sell_discipline.trade_realized_r` — the same helper the
sell-discipline record uses, so /trades and the sell-discipline report can never disagree.
A trade with no valid R frame (no risk unit / no shares) renders WITHOUT an R, never a
made-up one. The old '· N attempt(s)' suffix is gone (operator 2026-10-07: it added bulk).
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from agents.market_intelligence.sell_discipline import trade_realized_r

logger = logging.getLogger(__name__)


def parse_exits(raw) -> list:
    """An mi_live_trades row's `exits` (a list, or its JSON text) as a list; malformed JSON shows
    empty (logged at debug). The ONE parser /trade and /trades share (was two closures in agent.py)."""
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except Exception as e:  # loud-ok: display only — a malformed row shows no exits, logged
        logger.debug(f"/trades: malformed exits JSON on a row, showing empty: {e}")
        return []


def fmt_closed_line(r: dict, *, parse_exits: Callable = parse_exits) -> list[str]:
    """`r` is an mi_live_trades row dict; it must carry entry_price, hard_stop, orb_low and
    entry_shares for the R (sell_discipline's R frame) plus the display columns."""
    pnl = float(r.get("total_pnl") or 0)
    emoji = "✅" if pnl > 0 else "❌"
    exits = parse_exits(r.get("exits"))
    last = exits[-1] if exits else {}
    exit_price = last.get("price")
    # Underscores in reason (stop_hit, partial_profit, sma_trail_stop) break
    # Telegram Markdown V1 italic parsing — swap to spaces for display.
    reason = (last.get("reason") or "?").replace("_", " ")
    entry = r.get("entry_price")
    hold = r.get("hold_days") or 0
    score = r.get("ep_score") or 0
    entry_str = f"${entry:.2f}" if entry else "?"
    exit_str = f"${exit_price:.2f}" if exit_price else "?"
    closed_at = r.get("closed_at")
    date_suffix = f" · {closed_at.strftime('%b %d')}" if closed_at else ""
    realized_r = trade_realized_r(r)
    r_str = f" · {realized_r:+.1f}R" if realized_r is not None else ""
    out = [
        f"  {emoji} *{r['ticker']}* ${pnl:+,.0f}{r_str} ({hold}d){date_suffix}",
        f"      {entry_str} → {exit_str} · {reason} · score {score:.0f}",
    ]
    # ⚠ EVERY LEG, not just the last one (operator 2026-08-08). The two lines above
    # render `exits[-1]`, so a trade that TOOK PROFIT and was then stopped out showed
    # only the stop — the profit-take was invisible. His words: *"I completely missed
    # this and never saw the telegram, and in /trades it just shows the total realized
    # loss… at the very least /trades should show the partial profit taken for closed
    # trades."*
    # The live case: FIGS 08-07 banked +$6.90 on a +2R partial, then lost $13.74 on the
    # remainder. /trades rendered "❌ FIGS -$7 · stop hit" and nothing else — the system
    # had done the right thing first and the surface hid it.
    if len(exits) > 1:
        legs = []
        for e in exits:
            px, sh = e.get("price"), e.get("shares")
            epnl = e.get("pnl")
            why = (e.get("reason") or "?").replace("_", " ")
            if px is None or sh is None:
                continue
            pnl_part = f" ${float(epnl):+,.2f}" if epnl is not None else ""
            legs.append(f"{float(sh):g}sh @${float(px):.2f}{pnl_part} ({why})")
        if legs:
            out.append("      ↳ " + " → ".join(legs))
    return out
