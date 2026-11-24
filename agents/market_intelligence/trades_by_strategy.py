"""/trades by STRATEGY (operator 2026-11-24, display only — changes no trading, sizing, entry, exit or
safeguard).

The paper book's realized total mixed the current breakout setup with two retired strategies, so it
could not answer "how is the breakout setup doing". Two levels: LEVEL 1 = one line per ACTIVE strategy
of the book + one folded "retired" line; LEVEL 2 = one strategy (or the retired group) with the
existing Closed / Skipped / Scanned views scoped to it.

Strategy key = `mi_live_trades.signal_type`. ACTIVE vs RETIRED is DERIVED from the strategy registry
(`mi_strategies`: enabled, phase -> `resolve_account_mode_for_strategy` == this book), never a typed
list: a new paper strategy shows up on its own line from its first trade, and drops into the retired
line when it is disabled / deprecated / re-routed to the other book. Every query here keeps its
`account_mode` filter (dual-account invariant) — the book is a BOUND parameter.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

RETIRED = "retired"            # the pseudo-strategy token for the folded group
UNLABELLED = "unlabelled"      # rows whose signal_type is NULL (pre-framework) — never active

# Short typed aliases. Everything else resolves by registry id / unique prefix (>= 6 chars so a typed
# ticker such as BREAK can never be hijacked — a ticker is at most 5 letters).
_ALIASES = {"ep": "magna53"}
_MIN_PREFIX = 6

REGIME_NOTE = ("_Returns taken in the current bear-market regime — a bad stretch is not a verdict "
               "on the setup._")

# One row per signal_type for the book. AVG() ignores NULL, so a trade with no risk figure is skipped
# from the R average (never a made-up R). `$1` is the book (bound — never a literal).
_STATS_SQL = """
    SELECT COALESCE(signal_type, 'unlabelled') AS sig,
           MIN(alert_date) FILTER (WHERE status IN ('filled', 'closed')) AS first_trade,
           MAX(alert_date) FILTER (WHERE status IN ('filled', 'closed')) AS last_trade,
           COUNT(*) FILTER (WHERE status = 'closed') AS closed_n,
           COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) AS wins,
           COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) AS realized,
           AVG(total_pnl / NULLIF(COALESCE(NULLIF(risk_dollars_actual, 0), NULLIF(risk_dollars, 0)), 0))
               FILTER (WHERE status = 'closed') AS avg_r,
           COUNT(*) FILTER (WHERE status = 'filled' AND remaining_shares > 0) AS open_n,
           COALESCE(SUM(total_pnl) FILTER (WHERE status = 'filled' AND remaining_shares > 0), 0) AS open_realized
    FROM mi_live_trades
    WHERE account_mode = $1  -- the book (dual-account invariant)
    GROUP BY 1
"""

_REGISTRY_SQL = "SELECT strategy_id, signal_type, name, phase, enabled FROM mi_strategies"


def _active_for_book(rows, book: str) -> set[str]:
    """signal_types of registry strategies that are enabled AND routed to `book` today."""
    from agents.market_intelligence.constants import resolve_account_mode_for_strategy
    out: set[str] = set()
    for r in rows:
        if not r["enabled"] or not r["signal_type"]:
            continue
        try:
            if resolve_account_mode_for_strategy({"phase": r["phase"]}) == book:
                out.add(r["signal_type"])
        except ValueError:      # shadow / deprecated: routes nowhere, so never active
            continue
    return out


def _stat(r) -> dict:
    closed_n = int(r["closed_n"] or 0)
    return {
        "sig": r["sig"],
        "first_trade": r["first_trade"],
        "last_trade": r["last_trade"],
        "closed_n": closed_n,
        "wins": int(r["wins"] or 0),
        "realized": float(r["realized"] or 0),
        "avg_r": (float(r["avg_r"]) if r["avg_r"] is not None else None),
        "open_n": int(r["open_n"] or 0),
        "open_realized": float(r["open_realized"] or 0),
    }


def _traded(s: dict) -> bool:
    return s["first_trade"] is not None or s["closed_n"] > 0 or s["open_n"] > 0


async def _runtime_off(sig: str) -> bool:
    """True when the strategy's own runtime stop switch (mi_safeguard_state, read by the order step
    through `get_runtime_toggle`) is OFF — it then places no orders, so it is retired for display. The
    switch names come from the constants in db.py, never a typed copy. A failed read = not off."""
    from agents.market_intelligence import db
    toggles = {
        db.BREAKOUT_V1_STRATEGY_ID: (db.BREAKOUT_V1_PAPER_TOGGLE, db.BREAKOUT_V1_PAPER_TOGGLE_ENV),
        db.LOWCAP_PAPER_LANE_STRATEGY_ID: (db.LOWCAP_PAPER_LANE_TOGGLE, db.LOWCAP_PAPER_LANE_TOGGLE_ENV),
    }
    t = toggles.get(sig)
    if t is None:
        return False
    try:
        return not await db.get_runtime_toggle(t[0], t[1])
    except Exception as e:  # loud-ok: display only — a failed read leaves the strategy on its active line
        logger.warning(f"/trades runtime toggle read failed for {sig}: {e}")
        return False


async def load_book_strategies(conn, book: str) -> dict:
    """{'active': [stat...], 'retired': [stat...], 'all_ids': set, 'names': {sig: name}}.
    Active = registry-active for the book AND has a filled/closed trade in it (a new strategy appears
    from its first trade); retired = has trades in the book but is not registry-active for it."""
    reg = await conn.fetch(_REGISTRY_SQL)
    stat_rows = await conn.fetch(_STATS_SQL, book)
    active_ids = _active_for_book(reg, book)
    for sig in sorted(active_ids):
        if await _runtime_off(sig):
            active_ids.discard(sig)
    names = {r["signal_type"]: r["name"] for r in reg if r["signal_type"]}
    stats = [_stat(r) for r in stat_rows]
    stats = [s for s in stats if _traded(s)]
    stats.sort(key=lambda s: (s["first_trade"] or date.max, s["sig"]))
    active = [s for s in stats if s["sig"] in active_ids]
    # newest strategy first on the board: it is the one being judged
    active.sort(key=lambda s: s["first_trade"] or date.min, reverse=True)
    retired = [s for s in stats if s["sig"] not in active_ids]
    return {"active": active, "retired": retired,
            "all_ids": {s["sig"] for s in stats} | {r["signal_type"] for r in reg if r["signal_type"]},
            "names": names}


def single_strategy_sig(bs: dict) -> str | None:
    """The SKIP RULE: exactly one active strategy and no retired ones -> its signal_type."""
    if len(bs["active"]) == 1 and not bs["retired"]:
        return bs["active"][0]["sig"]
    return None


def resolve_arg(bs: dict, arg: str) -> str | None:
    """A typed `/trades <arg>` -> a scope token (a signal_type, or 'retired'), else None (the caller
    then treats it as a ticker). Exact id / alias always; a prefix only at >= 6 chars and only when it
    is unique."""
    a = (arg or "").strip().lower()
    if not a:
        return None
    if a == RETIRED:
        return RETIRED if bs["retired"] else None
    ids = {i.lower(): i for i in bs["all_ids"]}
    if a in ids:
        return ids[a]
    if a in _ALIASES and _ALIASES[a] in ids:
        return ids[_ALIASES[a]]
    if len(a) >= _MIN_PREFIX:
        hits = [orig for low, orig in ids.items() if low.startswith(a)]
        if len(hits) == 1:
            return hits[0]
    return None


def scope_sigs(bs: dict, scope: str) -> list[str]:
    """The signal_types a scope token stands for (the retired group = every retired one)."""
    if scope == RETIRED:
        return [s["sig"] for s in bs["retired"]]
    return [scope]


def nav_payload(bs: dict, match: str | None) -> dict:
    """What the Telegram layer needs to build the buttons — pure data, JSON-safe."""
    return {
        "strategies": [s["sig"] for s in bs["active"]],
        "retired": bool(bs["retired"]),
        "skip": single_strategy_sig(bs),
        "match": match,
    }


# ── rendering ────────────────────────────────────────────────────────────────

def _d(x) -> str:
    return f"{'-' if x < 0 else '+'}${abs(x):,.0f}"


def _since(first) -> str:
    return f"since {first.strftime('%b')} {first.day}" if first else "no fills yet"


def fmt_line(s: dict, label: str | None = None) -> str:
    """One strategy's stat line (plain words, no table)."""
    name = label or s["sig"]
    n = s["closed_n"]
    parts = [f"`{name}` ({_since(s['first_trade'])})"]
    if n:
        win = round(s["wins"] / n * 100)
        r = f" · avg {s['avg_r']:+.1f}R" if s["avg_r"] is not None else ""
        parts.append(f"{n} closed {_d(s['realized'])} · win {win}%{r}")
    else:
        parts.append("0 closed")
    if s["open_n"]:
        parts.append(f"{s['open_n']} open {_d(s['open_realized'])}")
    return " · ".join(parts)


def fmt_group_line(group: list[dict]) -> str:
    """The folded retired line: names, combined closed count + realized, date span."""
    names = ", ".join(f"`{s['sig']}`" for s in group)
    n = sum(s["closed_n"] for s in group)
    pnl = sum(s["realized"] for s in group)
    firsts = [s["first_trade"] for s in group if s["first_trade"]]
    lasts = [s["last_trade"] for s in group if s.get("last_trade")] or firsts
    span = ""
    if firsts:
        lo, hi = min(firsts), max(lasts)
        span = f" ({lo.strftime('%b')}–{hi.strftime('%b')})" if lo.month != hi.month else f" ({lo.strftime('%b')})"
    return f"retired: {names} · {n} closed {_d(pnl)}{span}"


def render_level1(bs: dict, book: str, date_str: str) -> str:
    badge = "📄 PAPER — not real money" if book == "paper" else "💰 LIVE (real money)"
    lines = [f"📊 *Strategies — {date_str}* · {badge}", ""]
    for s in bs["active"]:
        lines.append(fmt_line(s))
    if bs["retired"]:
        lines.append(fmt_group_line(bs["retired"]))
    lines += ["", REGIME_NOTE]
    return "\n".join(lines)


def scope_header(bs: dict, scope: str) -> str:
    """The level-2 stat line(s) that sit above a strategy's views."""
    if scope == RETIRED:
        return "\n".join(["*Retired strategies*",fmt_group_line(bs["retired"]),
                          *[f"  {fmt_line(s)}" for s in bs["retired"]]])
    s = next((x for x in bs["active"] + bs["retired"] if x["sig"] == scope), None)
    if s is None:
        return f"`{scope}` — no trades in this book yet."
    tag = "" if s in bs["active"] else " · retired"
    return fmt_line(s) + tag
