"""/trades by STRATEGY (operator 2026-11-24, display only — changes no trading, sizing, entry, exit or
safeguard).

The paper book's realized total mixed the current breakout setup with two retired strategies, so it
could not answer "how is the breakout setup doing". Two levels: LEVEL 1 = one line per ACTIVE strategy
of the book + one folded "retired" line; LEVEL 2 = one strategy (or the retired group) with the
existing Closed / Skipped / Scanned views scoped to it. A strategy with a setup-version registry
(`setup_versions.py`; breakout_v1 today) also shows one line per buy-rule version on its page.

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

# One strategy's traded rows, for the split by setup (buy-rule) version (operator 2026-11-25; setup_versions.py).
# Same population and the same R as _STATS_SQL, so the version lines add up to the strategy's own line. `$1` is the
# book (bound — dual-account invariant), `$2` the strategy. Grouped in Python: a row's own stamp wins, an unstamped
# row maps by its alert_date.
_VERSION_ROWS_SQL = """
    SELECT alert_date, setup_version, status, total_pnl, remaining_shares,
           total_pnl / NULLIF(COALESCE(NULLIF(risk_dollars_actual, 0), NULLIF(risk_dollars, 0)), 0) AS r
    FROM mi_live_trades
    WHERE account_mode = $1  -- the book (dual-account invariant)
      AND signal_type = ANY($2::text[])
      AND status IN ('filled', 'closed')
    ORDER BY alert_date
"""


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
    """{'active': [stat...], 'retired': [stat...], 'all_ids': set}.
    Active = registry-active for the book AND has a filled/closed trade in it (a new strategy appears
    from its first trade); retired = has trades in the book but is not registry-active for it."""
    reg = await conn.fetch(_REGISTRY_SQL)
    stat_rows = await conn.fetch(_STATS_SQL, book)
    active_ids = _active_for_book(reg, book)
    for sig in sorted(active_ids):
        if await _runtime_off(sig):
            active_ids.discard(sig)
    stats = [_stat(r) for r in stat_rows]
    stats = [s for s in stats if _traded(s)]
    stats.sort(key=lambda s: (s["first_trade"] or date.max, s["sig"]))
    active = [s for s in stats if s["sig"] in active_ids]
    # newest strategy first on the board: it is the one being judged
    active.sort(key=lambda s: s["first_trade"] or date.min, reverse=True)
    retired = [s for s in stats if s["sig"] not in active_ids]
    return {"active": active, "retired": retired,
            "all_ids": {s["sig"] for s in stats} | {r["signal_type"] for r in reg if r["signal_type"]}}


def has_versions(sig: str) -> bool:
    """True when the strategy has a setup-version registry (so its page carries the split)."""
    from agents.market_intelligence import setup_versions as sv
    return bool(sv.versions_for(sig))


async def load_version_stats(conn, book: str, sig: str) -> list[dict]:
    """One stat dict per setup version of `sig` that has a trade in the book, NEWEST version first. [] for a
    strategy with no version registry (no query is made). A stamp the registry does not know is kept on its own
    line, last; a row no version covers is counted under 'before v1'."""
    from agents.market_intelligence import setup_versions as sv
    versions = sv.versions_for(sig)
    if not versions:
        return []
    rows = await conn.fetch(_VERSION_ROWS_SQL, book, [sig])
    by: dict[str, dict] = {}
    for r in rows:
        v = sv.setup_version_for_row(sig, r["setup_version"], r["alert_date"]) or "before v1"
        g = by.setdefault(v, {"version": v, "first_trade": None, "last_trade": None, "closed_n": 0, "wins": 0,
                              "realized": 0.0, "rs": [], "open_n": 0})
        d = r["alert_date"]
        if d is not None:
            g["first_trade"] = d if g["first_trade"] is None else min(g["first_trade"], d)
            g["last_trade"] = d if g["last_trade"] is None else max(g["last_trade"], d)
        pnl = float(r["total_pnl"] or 0)
        if r["status"] == "closed":
            g["closed_n"] += 1
            g["wins"] += 1 if pnl > 0 else 0
            g["realized"] += pnl
            if r["r"] is not None:
                g["rs"].append(float(r["r"]))
        elif (r["remaining_shares"] or 0) > 0:
            g["open_n"] += 1
    order = {v.version: i for i, v in enumerate(versions)}
    short = {v.version: v.short for v in versions}
    out = []
    for v, g in by.items():
        rs = g.pop("rs")
        g["avg_r"] = (sum(rs) / len(rs)) if rs else None
        g["short"] = short.get(v, "")
        g["name"] = sv.display_name(v, sig)
        out.append(g)
    out.sort(key=lambda g: order.get(g["version"], -1 if g["version"] == "before v1" else len(order)), reverse=True)
    current = versions[-1].version
    if current not in by:       # the rules in force now, even before their first trade
        out.insert(0, {"version": current, "name": sv.display_name(current, sig), "short": short[current],
                       "first_trade": None, "last_trade": None, "closed_n": 0, "wins": 0, "realized": 0.0,
                       "avg_r": None, "open_n": 0})
    for g in out:
        g["current"] = g["version"] == current
    return out


def _span(first, last) -> str:
    if first is None:
        return ""
    a = f"{first.strftime('%b')} {first.day}"
    if last is None or last == first:
        return a
    return f"{a}–{last.day}" if (last.year, last.month) == (first.year, first.month) else f"{a}–{last.strftime('%b')} {last.day}"


def fmt_version_line(g: dict) -> str:
    """`v1.4` context checks (Nov 17–23) · 18 closed -$7,236 · win 6% · avg -0.9R · 5 open"""
    span = _span(g["first_trade"], g["last_trade"])
    head = f"`{g['name']}`" + (f" {g['short']}" if g["short"] else "") + (" · now" if g.get("current") else "")
    head += f" ({span})" if span else ""
    n = g["closed_n"]
    if n:
        r = f" · avg {g['avg_r']:+.1f}R" if g["avg_r"] is not None else ""
        body = f"{n} closed {_d(g['realized'])} · win {round(g['wins'] / n * 100)}%{r}"
    else:
        body = "0 closed"
    if g["open_n"]:
        body += f" · {g['open_n']} open"
    return f"{head} · {body}"


def render_versions(stats: list[dict]) -> str:
    """The 'by rule version' block under a strategy's stat line; '' when the strategy has no versions."""
    if not stats:
        return ""
    return "\n".join(["*By rule version* (the buy rules each trade was bought under)",
                      *[f"  {fmt_version_line(g)}" for g in stats]])


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


def fmt_line(s: dict) -> str:
    """One strategy's stat line (plain words, no table)."""
    n = s["closed_n"]
    parts = [f"`{s['sig']}` ({_since(s['first_trade'])})"]
    if n:
        win = round(s["wins"] / n * 100)
        r = f" · avg {s['avg_r']:+.1f}R" if s["avg_r"] is not None else ""
        parts.append(f"{n} closed {_d(s['realized'])} · win {win}%{r}")
    else:
        parts.append("0 closed")
    if s["open_n"]:
        # open_realized is what partial sales on the open trades already banked — NOT how the open
        # trades stand (unrealized needs live prices; the strategy page shows it). Label it so.
        banked = f" ({_d(s['open_realized'])} already taken)" if s["open_realized"] else ""
        parts.append(f"{s['open_n']} open{banked}")
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
    from agents.market_intelligence.agent import PAPER_BOOK_BADGE   # one wording for the paper badge
    badge = PAPER_BOOK_BADGE if book == "paper" else "💰 LIVE (real money)"
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
