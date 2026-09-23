"""
/scanned — the rejection-visibility surface (READ-ONLY).

Answers the operator's "how do I see what's rejected?" (2026-08-24): the
briefing only ever showed names that SCORED; everything killed by a bulk rule
(universe floors, quality filters, the top-20 cap) vanished with no
operator-facing trace — SDOT (gap +74%, never graded) and AERO (graded, then
filter-cut) both disappeared silently that morning. The selection was right;
the invisibility was the defect.

One screen, two halves (operator-agreed design):
  HALF 1 — the funnel: every bulk-cut rule as ONE line, count + rule in plain
           words, in the order the scan actually runs. No names. A stage with
           a ZERO count still prints — a silent stage is how a broken gate
           hides.
  HALF 2 — only names a human could argue about: everything that was GRADED
           (a few per day), plus bulk-cut names that RAN hard afterwards.
           Ranked by what the name DID AFTERWARDS (mi_ep_missed_outcomes) —
           that ranking is what makes this a scorecard instead of a log.

THE LINE: this module changes NO rule, threshold, filter or score. It reports
what already happened. Data contract: db.get_ep_scanned_day().

Rendering rules honored here:
  - Telegram cannot render pipe tables → monospace code blocks only.
  - Machine skip-reason prefixes (filter:/block:/...) go through humanize().
  - mi_ep_scan_log repeats per scan tick → the db query dedupes to the LAST
    state per ticker; grouping here is on the reason PREFIX (via the canonical
    _categorize_skip_reason), never the whole string (reasons embed numbers).
  - mi_ep_missed_outcomes rows can be STALE (#583 — stale rows corrupted a
    prior ranking table): a row only ranks if it was refreshed recently (still
    inside the nightly 30d rebuild window) OR refreshed after its 5-session
    outcome had fully settled. Stale rows display as "outcome stale" and are
    never ranked.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker.skip_reasons import humanize
from agents.market_intelligence.missed_outcomes import (
    DECLINED_NEVER_FILLED_STATUSES,
    _categorize_skip_reason,
)

_ET = ZoneInfo("America/New_York")

# Trade-row statuses that mean "no fill ever happened". 'expired' (a staged
# proposal that timed out with no broker order) is added on top of the
# canonical declined set — for THIS surface it is still "alerted but never
# entered", which is the blocked stage.
_NEVER_FILLED = frozenset(DECLINED_NEVER_FILLED_STATUSES) | {"expired"}

# ── HALF 1: the funnel ──────────────────────────────────────────────────────
# Stages in the order the scan actually runs: universe floors → mechanical
# gates → shortlist cap → grading → scoring → alert → entry. always_print
# stages render even at zero.
_FUNNEL_STAGES: list[tuple[str, str, bool]] = [
    ("u_close",      "prior close under the $5 universe floor",             True),
    ("u_vol",        "prior-day volume under the 50k-share universe floor", True),
    # #605: record-only capture band (gap under the admission floor) — not always_print:
    # rows only exist since 2026-08-29, and a zero on an old day is history, not a broken gate.
    ("below_floor",  "gap under the admission floor (recorded only)",       False),
    ("adv_low",      "average daily dollar volume too thin",                True),
    ("mcap_low",     "market cap too small",                                True),
    ("atr_high",     "day-to-day swings too wild (ATR cap)",                True),
    ("extension",    "already ran too far before this gap",                 True),
    ("pm_rvol",      "pre-market volume below its usual pace",              True),
    ("session_rvol", "session volume below its usual pace",                 True),
    ("cooldown",     "alerted within the last 60 days (cooldown)",          False),
    ("ma_filter",    "merger/buyout news, not a momentum gap",              False),
    ("duplicate",    "already handled by an earlier scan today",            False),
    ("filter_other", "other filters",                                       False),
    ("top20",        "didn't make the top-20 grading shortlist",            True),
    ("routine",      "catalyst graded routine, not scoreable",              False),
    ("graded_cut",   "graded, then a mechanical filter cut it",             True),
    ("below_bar",    "graded and scored, but under the alert bar",          True),
    ("alerted",      "alerted, no entry attempted",                         True),
    ("blocked",      "alerted, then blocked or unfilled at entry",          True),
    ("traded",       "traded",                                              True),
]

# Canonical category (missed_outcomes._categorize_skip_reason) → funnel stage.
_CATEGORY_TO_STAGE = {
    "below_gap_floor": "below_floor",  # #605 record-only band
    "adv_low": "adv_low",
    "mcap_low": "mcap_low",
    "atr_high": "atr_high",
    "extension_gate": "extension",
    "pm_rvol_low": "pm_rvol",
    "session_rvol_low": "session_rvol",
    "cooldown": "cooldown",
    "ma_filter": "ma_filter",
    "duplicate_scan": "duplicate",
    "outside_top20": "top20",
    "score_below_50": "below_bar",
    "catalyst_downgrade": "routine",
}

# Stages whose names earn an individual HALF-2 line (a human could disagree).
_GRADED_OR_BETTER = frozenset(
    {"routine", "graded_cut", "below_bar", "alerted", "blocked", "traded"})

# A bulk-cut name whose 5-session high ran at least this far above the gap-day
# open earns a HALF-2 line anyway — the bar is STATED in the section header so
# it is never a hidden rule. Display-only; feeds no trading decision.
_BULK_RUNNER_BAR = 0.20
_BULK_RUNNER_MAX_LINES = 5
_GRADED_MAX_LINES = 15

_SCORE_REASON_RE = re.compile(
    r"score\s+(-?\d+(?:\.\d+)?)\s*<\s*(?:bar\s+)?(-?\d+(?:\.\d+)?)"
    r"(?:\s*\(catalyst=([a-z_]+)\))?",
    re.IGNORECASE,
)


def _plain_reason(raw: Optional[str]) -> str:
    """Stored reason → plain words. Strips the 'quality filter: ' wrapper,
    rewrites the score-vs-bar form, and runs machine prefixes through
    humanize() (which passes unknown free-form strings through untouched —
    nothing is ever hidden)."""
    if not raw:
        return "no reason recorded"
    s = raw.strip()
    if s.lower().startswith("quality filter:"):
        s = s.split(":", 1)[1].strip()
    m = _SCORE_REASON_RE.match(s)
    if m:
        cat = m.group(3)
        cat_part = f" ({cat.replace('_', ' ')} catalyst)" if cat else ""
        return f"scored {_num(m.group(1))}, bar was {_num(m.group(2))}{cat_part}"
    return humanize(s)


def _num(s: str) -> str:
    """'52.5' → '52.5', '52.0' → '52'."""
    try:
        f = float(s)
        return f"{f:g}"
    except (TypeError, ValueError):
        return s


def _truncate(s: str, limit: int = 88) -> str:
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


# ── per-ticker stage resolution ─────────────────────────────────────────────

def _resolve_tickers(data: dict[str, list[dict[str, Any]]]) -> dict[str, dict]:
    """Merge the five sources into one record per ticker and resolve each
    ticker's FINAL stage (furthest point it reached). Precedence: traded >
    blocked > alerted > scored > graded-then-cut > bulk scan category — so a
    graded name never drowns in a bulk count and an alerted name whose last
    scan tick said 'already scored earlier today' is never mislabeled a dupe."""
    per: dict[str, dict] = {}

    def slot(t: str) -> dict:
        return per.setdefault(t, {"ticker": t})

    for r in data.get("scan") or []:
        slot(r["ticker"])["scan_row"] = r
    for r in data.get("graded") or []:
        slot(r["ticker"])["graded_row"] = r
    for r in data.get("alerts") or []:
        slot(r["ticker"])["alert_row"] = r
    for r in data.get("trades") or []:
        slot(r["ticker"]).setdefault("trade_rows", []).append(r)
    for r in data.get("outcomes") or []:
        slot(r["ticker"])["outcome_row"] = r

    for s in per.values():
        s["stage"] = _stage_for(s)
    return per


def _stage_for(s: dict) -> str:
    trade_rows = s.get("trade_rows") or []
    if any((tr.get("status") or "") not in _NEVER_FILLED for tr in trade_rows):
        return "traded"
    if trade_rows:
        return "blocked"
    sc = s.get("scan_row")
    if s.get("alert_row") or (sc and sc.get("score_tier")):
        return "alerted"
    reason = (sc or {}).get("filter_reason")
    cat = _categorize_skip_reason("scan_filter", reason) if reason else None
    if cat == "score_below_50":
        return "below_bar"
    g = s.get("graded_row")
    if g is not None:
        # A tier-shadow row exists = the name reached grading. NULL score =
        # a mechanical filter cut it before it could be scored (the AERO
        # class, capture shipped 08-23); a score with no alert = under the bar.
        if g.get("live_ep_score") is not None:
            return "below_bar"
        return "graded_cut"
    if not reason:
        return "filter_other"
    if cat == "d1_universe_floor":
        return ("u_close" if reason.startswith("filter:universe_prev_close")
                else "u_vol")
    return _CATEGORY_TO_STAGE.get(cat, "filter_other")


# ── outcome freshness (#583 guard) ──────────────────────────────────────────

def _outcome_is_fresh(o: Optional[dict], alert_d: date, now: datetime) -> bool:
    """A missed-outcome row ranks only if it is still being refreshed (the
    nightly 30d rebuild touched it within ~2 days) OR its last refresh came
    after the 5-session outcome had fully settled (~7 calendar days). Rows
    failing both stopped refreshing before their numbers settled — the exact
    stale class that corrupted a prior ranking table (#583)."""
    if not o:
        return False
    lr = o.get("last_refreshed_at")
    if lr is None:
        return False
    if lr.tzinfo is None:  # defensive — asyncpg returns aware; fixtures may not
        lr = lr.replace(tzinfo=timezone.utc)
    settled_by = datetime(alert_d.year, alert_d.month, alert_d.day,
                          tzinfo=timezone.utc) + timedelta(days=7)
    return lr >= now - timedelta(days=2) or lr >= settled_by


def _outcome_text(s: dict, alert_d: date, now: datetime) -> tuple[str, Optional[float]]:
    """→ (display text, rank key or None). Rank key = 5-session max high vs
    the gap-day open — 'what the name DID afterwards'.

    #595 (2026-08-29): a row also has to have been a SETUP AT THE BELL to rank. `gap_pct` is
    what the SCAN saw, often a pre-market print that never survived to the open — VEEE
    2026-07-08 scanned at 16-20%, OPENED at +4.1% and closed -21%, and the forward window then
    credited it +354% that actually belongs to an unrelated move three sessions later. The
    operator caught it by eye: *"i don't see gap on 7/8"*. Measured across the table: 2,654 of
    4,022 rows never gapped at the open, and 203 of the 331 ranked "big winners" (61%) were on
    days with no setup at all.

    It is a RANK gate, not a display gate — the line still prints what the name did, because
    the pre-market print is real telemetry about our own scan and hiding it would be the same
    mistake in the other direction. It simply stops being called a missed winner.
    """
    o = s.get("outcome_row")
    if o is None:
        return "outcome pending", None
    if not _outcome_is_fresh(o, alert_d, now):
        return "outcome stale, not ranked", None
    mh, r5 = o.get("max_high_5d"), o.get("ret_5d")
    if mh is None and r5 is None:
        return "outcome pending", None
    parts = []
    if mh is not None:
        parts.append(f"ran {mh * 100:+.0f}% high")
    if r5 is not None:
        parts.append(f"settled {r5 * 100:+.0f}%")
    text = ", ".join(parts) + " in 5 sessions"
    # NULL = not computed (every row written before #595, or no prior bar) — those keep
    # ranking exactly as before rather than being silently demoted by a missing value.
    if o.get("setup_at_open") is False:
        og = o.get("open_gap_pct")
        og_txt = f" (opened {og * 100:+.0f}%)" if og is not None else ""
        return text + f" — but no setup at the open{og_txt}, not ranked", None
    return text, mh


# ── HALF 2 per-name lines ───────────────────────────────────────────────────

def _gap_of(s: dict) -> Optional[float]:
    for key, field in (("scan_row", "gap_pct"), ("alert_row", "gap_pct"),
                       ("graded_row", "gap_pct_last")):
        r = s.get(key)
        if r and r.get(field) is not None:
            return float(r[field])
    return None


def _decided_line(s: dict) -> str:
    """The rule that decided this name, in plain words, with the number the
    rule actually compared (it lives inside the stored reason detail)."""
    stage = s["stage"]
    sc = s.get("scan_row") or {}
    al = s.get("alert_row") or {}
    g = s.get("graded_row") or {}
    tier = al.get("score_tier") or sc.get("score_tier") or ""
    score = al.get("ep_score") or sc.get("ep_score") or g.get("live_ep_score")
    score_s = f" {float(score):g}" if score is not None else ""

    if stage == "traded":
        pnl = sum(float(tr.get("total_pnl") or 0) for tr in s.get("trade_rows") or [])
        mode = next((tr.get("account_mode") for tr in s.get("trade_rows") or []
                     if (tr.get("status") or "") not in _NEVER_FILLED), None)
        mode_tag = f" ({mode})" if mode and mode != "live" else ""
        return f"alerted {tier}{score_s} → traded{mode_tag}, P&L ${pnl:+,.0f}"
    if stage == "blocked":
        last_tr = (s.get("trade_rows") or [{}])[-1]
        return (f"alerted {tier}{score_s} → "
                f"{_plain_reason(last_tr.get('skip_reason'))}")
    if stage == "alerted":
        return f"alerted {tier}{score_s}, no entry attempted"
    if stage == "below_bar":
        reason = sc.get("filter_reason")
        if reason:
            return _plain_reason(reason)
        return f"scored{score_s}, under the alert bar"
    if stage == "graded_cut":
        quality = g.get("live_quality_last") or "?"
        return f"graded {quality}, then cut: {_plain_reason(sc.get('filter_reason'))}"
    # routine (and any other graded-zone stage that lands here)
    return _plain_reason(sc.get("filter_reason"))


# ── the renderer ────────────────────────────────────────────────────────────

def render_scanned_day(d: date, data: dict[str, list[dict[str, Any]]],
                       now: Optional[datetime] = None) -> str:
    now = now or datetime.now(_ET)
    per = _resolve_tickers(data)
    day_label = d.strftime("%a %Y-%m-%d")

    if not per:
        return (
            f"🔬 *Scanned — {day_label}*\n"
            "No scan rows for this day. Either no scan ran (weekend/holiday) "
            "or scan logging broke — a market day with zero rows is worth a "
            "look. Try `/scanned YYYY-MM-DD` for another day."
        )

    counts = Counter(s["stage"] for s in per.values())
    n_alerted_total = sum(
        1 for s in per.values() if s["stage"] in ("alerted", "blocked", "traded"))

    lines: list[str] = [f"🔬 *Scanned — {day_label}*", "```"]
    lines.append(
        f"{len(per)} tickers looked at · {n_alerted_total} alerted"
        f" · {counts.get('traded', 0)} traded"
    )
    lines.append("")
    for key, label, always in _FUNNEL_STAGES:
        n = counts.get(key, 0)
        if n or always:
            lines.append(f"{n:>4}  {label}")
    lines.append("```")

    # HALF 2 — graded or better, ranked by what the name did afterwards.
    graded = [s for s in per.values() if s["stage"] in _GRADED_OR_BETTER]

    def _rank(s: dict):
        _, mh = _outcome_text(s, d, now)
        gap = _gap_of(s)
        return (mh if mh is not None else float("-inf"),
                gap if gap is not None else float("-inf"))

    graded.sort(key=_rank, reverse=True)

    any_pending = False
    if graded:
        lines.append("*Graded — the names a human could argue about*"
                     " (ranked by what they did after):")
        lines.append("```")
        for s in graded[:_GRADED_MAX_LINES]:
            gap = _gap_of(s)
            gap_s = f"gap {gap:+.0f}%" if gap is not None else "gap ?"
            otext, _ = _outcome_text(s, d, now)
            any_pending = any_pending or otext == "outcome pending"
            lines.append(f"{s['ticker']:<5} {gap_s:<9} {otext}")
            lines.append(f"      {_truncate(_decided_line(s))}")
        if len(graded) > _GRADED_MAX_LINES:
            lines.append(f"… and {len(graded) - _GRADED_MAX_LINES} more graded names not shown")
        lines.append("```")
    else:
        lines.append("_Nothing reached grading — every name died in the bulk cuts above._")

    # Bulk cuts that ran anyway — the scorecard's tail. Bar stated, not hidden.
    runners = []
    for s in per.values():
        if s["stage"] in _GRADED_OR_BETTER:
            continue
        otext, mh = _outcome_text(s, d, now)
        if mh is not None and mh >= _BULK_RUNNER_BAR:
            runners.append((mh, otext, s))
    runners.sort(key=lambda t: t[0], reverse=True)
    if runners:
        lines.append(f"*Bulk cuts that ran anyway* (≥ {_BULK_RUNNER_BAR * 100:+.0f}% high within 5 sessions):")
        lines.append("```")
        for mh, otext, s in runners[:_BULK_RUNNER_MAX_LINES]:
            gap = _gap_of(s)
            gap_s = f"gap {gap:+.0f}%" if gap is not None else "gap ?"
            lines.append(f"{s['ticker']:<5} {gap_s:<9} {otext}")
            lines.append(f"      cut: {_truncate(_plain_reason((s.get('scan_row') or {}).get('filter_reason')))}")
        if len(runners) > _BULK_RUNNER_MAX_LINES:
            lines.append(f"… and {len(runners) - _BULK_RUNNER_MAX_LINES} more runners not shown")
        lines.append("```")

    if any_pending:
        lines.append(f"_Outcomes settle over the next 5 sessions — re-run `/scanned {d.isoformat()}` later for the scorecard._")

    return "\n".join(lines)
