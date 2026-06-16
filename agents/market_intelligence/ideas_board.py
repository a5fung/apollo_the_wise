"""`/ideas` — the unified trade-ideas front door (ADR 0004 consolidation).

ONE entry surface: a substrate-backed "Stocks in Play" block + the top NAMED ideas
per strategy. The per-strategy drill-down buttons + the edit-in-place ← back nav live
in channels/telegram.py (orchestrator), mirroring /hud; this module owns only the
summary TEXT.

Two deliberate boundaries (advisor 2026-06-16):
  • The "Stocks in Play" block reads the mi_stocks_in_play SUBSTRATE ONLY — never
    re-derived from per-detector getters, or /ideas just becomes the 8th aggregator
    of the fragmentation this whole thread consolidates.
  • The per-strategy "top ideas" lines DO pull individual detector getters today —
    legitimate scaffolding, because MAGNA53/9M/flags/fishhook aren't migrated into
    the substrate until ADR-0004 Phase 2-5. As each detector migrates, its line
    should read from the substrate and the getter call drops out.

Kept light (no heavy imports at module top) so render_ideas_summary is unit-testable
without standing up the agent / a DB. The pure renderer takes already-fetched lists
(or None on a failed getter) and only ever emits CAPS-safe tickers — never the
source_detector/reason strings, which carry underscores that desync Telegram Markdown.
"""
from __future__ import annotations

_SEP = "━━━━━━━━━━━━━━━━━━━━━"
_FLAG_STAGE_EMOJI = {"TRIGGERED": "🎯", "COILED": "🌀", "TIGHTENING": "🔧"}
_FLAG_STAGE_RANK = {"TRIGGERED": 0, "COILED": 1, "TIGHTENING": 2}


def render_ideas_summary(*, today, sip_rows, magna53, ninem_intraday,
                         ninem_day2, flags, fishhook) -> str:
    """Pure /ideas summary. All list args may be None (failed/again getter)."""
    lines = [f"💡 *Apollo Ideas* — {today.strftime('%a %b %d')}", _SEP]

    # ── Stocks in Play (SUBSTRATE ONLY) — lead with ACTIONABLE, collapse watchlist ──
    # The substrate mixes actionability tiers; an operator scanning "what do I trade now"
    # wants the operator_only/apollo_eligible rows (WITH their stage) up top and the
    # informational watchlist (e.g. the sugar-baby cohort — context, not a fire signal)
    # collapsed to a count + pointer. The stage comes from each row's reason head.
    sip_rows = sip_rows or []
    _cls_rank = {"apollo_eligible": 0, "operator_only": 1, "informational": 2}
    actionable, info_tickers, seen = [], [], set()
    for r in sorted(sip_rows, key=lambda r: _cls_rank.get(r.get("automation_class"), 3)):
        t = r["ticker"]
        if t in seen:                       # dedup multi-detector → most-actionable class wins
            continue
        seen.add(t)
        cls = r.get("automation_class")
        if cls in ("apollo_eligible", "operator_only"):
            # reason head carries the stage ("delayed-EP reclaim ready" …); underscores
            # stripped so the (non-caps-safe) reason can't desync Telegram Markdown
            stage = (r.get("reason") or "").split("—")[0].strip().replace("_", " ")
            actionable.append(("🚨" if cls == "apollo_eligible" else "👤", t, stage))
        else:
            info_tickers.append(t)
    n_act, n_info = len(actionable), len(info_tickers)
    lines.append(f"🎯 *Stocks in Play* — {n_act} actionable"
                 + (f" · {n_info} watchlist" if n_info else ""))
    if actionable:
        for emoji, t, stage in actionable[:10]:
            lines.append(f"  {emoji} `{t}` {stage}".rstrip())
        if n_act > 10:
            lines.append(f"  …+{n_act - 10} more")
    elif n_info == 0:
        lines.append("  _substrate empty — detectors quiet_")
    if info_tickers:
        chips = " ".join(f"`{t}`" for t in info_tickers[:12])
        more = f" …+{n_info - 12}" if n_info > 12 else ""
        lines.append(f"  ℹ️ watchlist: {chips}{more}  → /sugarbabies")
    if actionable or info_tickers:
        lines.append("_🚨 auto-eligible · 👤 your call · ℹ️ watchlist context_")
    lines.append(_SEP)

    # ── Top NAMED ideas per strategy (scaffolding; ADR-0004 unifies into substrate) ──
    lines.append("*Top ideas per strategy*")

    # MAGNA53: HIGH tier first, then by ep_score desc; top 3 named.
    m = magna53 or []
    m_sorted = sorted(
        m, key=lambda a: (0 if a.get("score_tier") == "HIGH" else 1,
                          -(a.get("ep_score") or 0)))
    if m_sorted:
        picks = " · ".join(
            f"`{a['ticker']}`{'(H)' if a.get('score_tier') == 'HIGH' else '(M)'}"
            for a in m_sorted[:3])
        lines.append(f"🎯 MAGNA53: {picks}")
    else:
        lines.append("🎯 MAGNA53: _none today_")

    # 9M EP: top intraday (already volume-ranked) + Day-2 pending names.
    ni = [a for a in (ninem_intraday or []) if a.get("ticker")]
    nd = [a for a in (ninem_day2 or []) if a.get("ticker")]
    if ni or nd:
        intra = " · ".join(f"`{a['ticker']}`" for a in ni[:3]) if ni else "—"
        day2 = (" · Day2: " + ", ".join(f"`{a['ticker']}`" for a in nd[:3])) if nd else ""
        lines.append(f"🏦 9M EP: {intra}{day2}")
    else:
        lines.append("🏦 9M EP: _none today_")

    # Flags: TRIGGERED > COILED > TIGHTENING, then by base_age desc; top 3 named.
    fl = sorted(
        flags or [],
        key=lambda r: (_FLAG_STAGE_RANK.get(r.get("stage"), 9),
                       -(r.get("base_age") or 0)))
    if fl:
        picks = " · ".join(
            f"`{r['ticker']}`{_FLAG_STAGE_EMOJI.get(r.get('stage'), '')}"
            for r in fl[:3])
        lines.append(f"🚩 Flags: {picks}")
    else:
        lines.append("🚩 Flags: _none today_")

    # Fishhook: active open anchors only; top 3 named.
    fh = [r for r in (fishhook or [])
          if r.get("state") in ("pending", "promoted", "reclaimed") and r.get("ticker")]
    if fh:
        picks = " · ".join(f"`{r['ticker']}`" for r in fh[:3])
        lines.append(f"🪝 Fishhook: {picks}")
    else:
        lines.append("🪝 Fishhook: _none active_")

    lines.append(_SEP)
    lines.append("_Tap a strategy to drill in · SHADOW where noted · /watch for the full board_")
    return "\n".join(lines)


async def build_ideas_text() -> str:
    """Fetch each surface fail-open (a single bad getter never blanks the board) and
    render. Stocks-in-Play = substrate; per-strategy = detector getters (scaffolding)."""
    import asyncio as _aio
    from agents.market_intelligence.collector import (
        et_today, prev_trading_days, last_trading_day,
    )
    from agents.market_intelligence.db import (
        get_stocks_in_play, get_today_ep_alerts, get_today_9m_ep_alerts,
        get_all_9m_sugar_babies, get_fishhook_outcomes_window,
    )
    from agents.market_intelligence.flag_detector import get_flag_watchlist

    today = et_today()
    query_str = last_trading_day(today).isoformat()
    yesterday = prev_trading_days(1, from_date=last_trading_day(today))[0]

    sip, magna53, ninem, day2, flags, fishhook = await _aio.gather(
        get_stocks_in_play(active_only=True),
        get_today_ep_alerts(query_str),
        get_today_9m_ep_alerts(query_str),
        get_all_9m_sugar_babies(yesterday),
        get_flag_watchlist(),
        get_fishhook_outcomes_window(60),
        return_exceptions=True,
    )

    def _ok(x):
        return x if isinstance(x, list) else None

    return render_ideas_summary(
        today=today, sip_rows=_ok(sip), magna53=_ok(magna53),
        ninem_intraday=_ok(ninem), ninem_day2=_ok(day2),
        flags=_ok(flags), fishhook=_ok(fishhook))
