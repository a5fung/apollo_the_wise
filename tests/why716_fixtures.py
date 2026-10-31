"""#716 — shared fixtures for the `/why` short-layout tests.

Two worlds, both built from the REAL producers wherever one exists (the score parts come from
`_score_ep`, never a hand-typed breakdown):

  REGN  2026-10-30  HIGH 65, bought nothing: the chase cap skipped the entry before any order
                    existed (trade 434). Shape taken from scripts/probes/_regn_1030/q1.out. The
                    catalyst prose, the judge rationale and the news sources are ILLUSTRATIVE (the
                    probe did not capture them); every number and every timestamp is the probe's.
  UNFILLED          an order WAS placed (entry_order_id set) and the 10:00 cleanup cancelled it
                    unfilled — the case the Fill diagnosis section was written for. Its full output
                    must not move.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from agents.market_intelligence.ep_detector import _score_ep

_ET = ZoneInfo("America/New_York")
DAY = date(2026, 10, 30)


def ts(h: int, m: int, s: int = 0, ms: int = 0) -> datetime:
    return datetime(2026, 10, 30, h, m, s, ms * 1000, tzinfo=_ET)


def _scan_row(*, gap, quality, adv_dollar, float_shares, vol_pct, rel_volume, at):
    score, breakdown = _score_ep(
        gap_pct=gap, rel_volume=rel_volume, catalyst_quality=quality,
        profile={"floatShares": float_shares}, regime_multiplier=1.0,
        vol_percentile=vol_pct, adv_dollar=adv_dollar, in_active_theme=False)
    return {
        "scan_time_et": at, "ep_score": score, "score_breakdown": breakdown,
        "score_side": "separation", "ep_bar": 65.0, "catalyst_quality": quality,
        "gap_pct": gap, "adv": adv_dollar / 870.0, "prev_close": 870.0,
        "float_shares": float_shares, "vol_percentile": vol_pct,
        "rel_volume": rel_volume, "projected_vol_multiple": None,
    }


def regn_world() -> dict:
    scan = _scan_row(gap=11.7, quality="strong", adv_dollar=583_634_406,
                     float_shares=105_000_000, vol_pct=0.0, rel_volume=0.41,
                     at=ts(9, 35, 24))
    assert scan["ep_score"] == 65.0 and sum(scan["score_breakdown"].values()) == 40
    alert = {
        "ticker": "REGN", "alert_date": DAY, "score_tier": "HIGH", "ep_score": 65.0,
        "gap_pct": 11.7, "catalyst": "Regeneron reports a clinical readout (discovery blurb)",
        "catalyst_quality": "strong", "rel_volume": 0.41,
        "grade_engine_authority": True, "baseline_floor_tier": "HIGH",
        "judge_tier": "HIGH", "judge_direction": "hold", "judge_materiality_tier": "material",
        "judge_rationale": ("Primary source confirms a pivotal trial result and a revenue-stage "
                            "catalyst; the grade holds."),
        "fire_axes": ["direct_source", "revenue_stage"], "rubric_version": None,
    }
    trade = {
        "id": 434, "status": "cancelled",
        "skip_reason": ("setup:chase_cap_exceeded: limit $928.33 risk $110.83/sh vs planned "
                        "$52.38/sh (cap 1.50x, ORB high $869.88)"),
        "orb_high": 869.88, "orb_low": 843.69, "entry_price": 869.88,
        "stop_price": 817.5000000000001, "entry_shares": 1, "total_pnl": None,
        "proposed_at": ts(9, 36, 30), "confirmed_at": ts(9, 36, 30), "closed_at": None,
        "entry_order_id": None,
    }
    grade = {
        "scan_date": DAY, "ticker": "REGN",
        "first_seen_et": ts(9, 35, 15), "last_seen_et": ts(9, 36, 21),
        "live_quality_first": "game_changer", "live_quality_last": "strong",
        "shadow_tier_first": "strong", "shadow_tier_last": "strong",
        "rule_last": "strong_unchanged", "regrade_count": 0, "live_side": "llm",
        "live_ep_score": 65.0, "live_tier": "HIGH",
        "expct_sched": "unscheduled", "expct_beat": False, "expct_combined": "forward",
        "sector": "Healthcare", "sector_n": 2, "sector_confirm": True,
        "claude_analysis": ("Regeneron announced a pivotal Phase 3 result that met its primary "
                            "endpoint, with a regulatory filing planned this year; the move is "
                            "driven by a new revenue stage, not routine news."),
        "news_summary": "Regeneron's Phase 3 trial met its primary endpoint.",
        "grounded_head": ("[SEC 8-K filed 2026-10-30, items 8.01] Regeneron announced...\n\n"
                          "[Benzinga 2026-10-30] Regeneron Phase 3 Succeeds...\n\n"
                          "[Benzinga 2026-10-30] Regeneron Shares Jump..."),
        "grounded_len": 5210,
    }
    events = [
        (ts(9, 35, 3, 176), "ep_rt_floor_flip_up", "REGN rt 11.6% ≥9 > delayed 6.7% @ 09:35 ET"),
        (ts(9, 35, 15, 706), "ep_catalyst_provenance", "REGN game_changer direct=True"),
        (ts(9, 35, 24, 160), "catalyst_rubric_passed",
         "REGN: rubric PASSED composite=25.6 (>= 22) label=strong"),
        (ts(9, 35, 24, 164), "vol_conviction_shadow",
         "REGN HIGH live_vol_pct=0 shadow_vol_pct=0 live_score=65.0 shadow_score=65.0"),
        (ts(9, 35, 24, 182), "conviction_floor_eligible", "REGN gap=11.7% score=65 tier=HIGH"),
        (ts(9, 36, 21, 736), "judge_signal_trace",
         "[ep_grade_judge] REGN: direct_source held=True sent=yes | revenue_stage held=True"),
        (ts(9, 36, 28, 293), "ep_grade_decision",
         "REGN our score HIGH · judge HIGH · judge note hold · outcome verdict"),
        (ts(9, 36, 28, 309), "filter:large_cap_relvol_floor_shadow",
         "REGN HIGH rel_vol=0.41x adv$=583,634,406 @ 09:35 ET (SHADOW — alert NOT skipped)"),
        (ts(9, 36, 28, 374), "theme_axis_shadow_adjusted", "REGN 2026-10-30: strong -> strong"),
        (ts(9, 36, 28, 870), "ep_alert", "HIGH EP: REGN gap=11.7% score=65"),
        (ts(9, 36, 28, 963), "orb_triggered", "[post_open_new_high] 1 alerts: ['REGN']"),
        (ts(9, 36, 30, 179), "exposure_family_checked",
         "REGN (live/ORB): no theme membership — nothing to compare"),
        (ts(9, 36, 30, 198), "orb_bar_fetched", "ORB REGN O=869.88 H=869.88 L=843.69 range=26.19"),
        (ts(9, 36, 30, 276), "entry_chase_cap_skipped",
         "REGN [live]: setup:chase_cap_exceeded: limit $928.33 risk $110.83/sh vs planned "
         "$52.38/sh (cap 1.50x, ORB high $869.88)"),
        (ts(9, 36, 30, 705), "orb_order_failed", "ORB REGN — submit_entry returned None (trade_id=434)"),
        (ts(9, 50, 2, 973), "ep_rt_admit",
         "REGN rt 13.4% and delayed 11.6% BOTH >=9 @ 09:50 ET — real-time AGREES with the admit"),
    ]
    # Minute bars AFTER the skip: price kept running through the trigger. With no order in
    # existence this is exactly what made the old Fill diagnosis tell a false story.
    bars = [{"t": int(ts(9, 37 + i).timestamp() * 1000), "h": 880.0 + 10 * i, "l": 860.0}
            for i in range(6)]
    return {"ticker": "REGN", "alert": alert, "trade": trade, "scan": None,
            "score_row": scan, "grade": grade, "events": events, "has_buy_order": False,
            "bars": bars}


def unfilled_world() -> dict:
    """An order WAS placed and the 10:00 cleanup cancelled it unfilled; price never reached the
    trigger. The pre-#716 /why shows a Fill diagnosis for it, and that stays."""
    w = regn_world()
    w["ticker"] = "ABCD"
    w["alert"] = dict(w["alert"], ticker="ABCD")
    w["grade"] = dict(w["grade"], ticker="ABCD")
    w["trade"] = dict(
        w["trade"], status="cancelled", skip_reason="broker:entry_expired: ORB window unfilled",
        entry_order_id="ord-abcd-1", closed_at=ts(10, 0, 2))
    w["events"] = [
        (ts(9, 36, 28, 870), "ep_alert", "HIGH EP: ABCD gap=11.7% score=65"),
        (ts(9, 36, 30, 705), "orb_order_placed",
         "ORB ABCD entry=$869.88 stop=$817.50 shares=1 risk=$52 trade_id=434"),
        (ts(10, 0, 2, 100), "orb_unfilled_cancelled", "ABCD unfilled at 10:00 ET cleanup"),
    ]
    w["has_buy_order"] = True
    # one-minute bars inside the order's lifetime that never reach the trigger ($869.88)
    w["bars"] = [{"t": int(ts(9, 37 + i).timestamp() * 1000), "h": 860.0 + i, "l": 850.0}
                 for i in range(5)]
    return w


def wire(monkeypatch, world: dict) -> None:
    """Stub the /why handler's I/O edges (DB, Telegram, bars, rubric) with `world`'s rows."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    async def _fetchrow(sql, *args):
        s = " ".join(sql.split())
        world.setdefault("sql", []).append(s)
        if "MAX(d)" in s:
            return {"d": DAY}
        if "FROM mi_ep_alerts" in s:
            return world["alert"]
        if "FROM mi_live_trades" in s:
            return world["trade"]
        if "score_breakdown" in s:
            return world["score_row"]
        if "mi_ep_theme_belonging_shadow" in s:
            return None
        if "filter_reason" in s:
            return world["scan"]
        return None

    async def _fetch(sql, *args):
        return [{"created_at": t, "event_type": et, "summary": su, "detail": None}
                for t, et, su in world["events"]]

    conn.fetchrow = _fetchrow
    conn.fetch = _fetch
    conn.fetchval = AsyncMock(return_value=world["has_buy_order"])
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record",
                        AsyncMock(return_value=world["grade"]))
    monkeypatch.setattr("agents.market_intelligence.db.get_latest_catalyst_grade_date",
                        AsyncMock(return_value=DAY))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map",
                        AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.collector.get_minute_bars",
                        AsyncMock(return_value=world["bars"]))
    monkeypatch.setattr("agents.market_intelligence.agent._send_plain_with_keyboard",
                        AsyncMock(return_value=False))   # falsy -> body comes back to us
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        AsyncMock(return_value=None))
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_rubric_runtime.get_theme_membership",
        AsyncMock(return_value=None))


def render(task: str) -> str:
    import asyncio
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest
    res = asyncio.run(MarketIntelligenceAgent()._handle_why_query(
        AgentRequest(task=task, user_id=1, conversation_id="t")))
    return res.result if hasattr(res, "result") else res["result"]
