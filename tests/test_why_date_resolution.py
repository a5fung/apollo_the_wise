"""`/why TICKER` with no date must land on the day the ticker was actually active.

2026-11-09: `/why app` showed 11-06 with nothing, while APP was scanned and dropped on 11-05.
Two causes, both in the no-date resolution of `_handle_why_query`:
  (a) the audit arm matched the ticker as a SUBSTRING (ILIKE '%APP%'), so APPN / "approved" /
      "happened" rows pulled the answer onto an unrelated day;
  (b) `mi_ep_scan_log` (scanned, not alerted) was not part of the resolution at all.
The fake connection below evaluates the resolution query by what its SQL actually says (ILIKE
substring vs. whole-word regex; scan-log arm present or absent), so the tests fail on the old SQL.
"""
import asyncio
import re
from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from agents.market_intelligence.agent import MarketIntelligenceAgent
from agents.market_intelligence.ep_detector import _score_ep
from shared.models import AgentRequest

_ET = ZoneInfo("America/New_York")
SCAN_DAY = date(2026, 11, 5)
NOISE_DAY = date(2026, 11, 6)


def _app_scan_row():
    score, breakdown = _score_ep(
        gap_pct=10.0, rel_volume=3.0, catalyst_quality="routine",
        profile={"floatShares": 250_000_000}, regime_multiplier=1.0,
        vol_percentile=50.0, adv_dollar=900_000_000, in_active_theme=False)
    return {
        "scan_time_et": datetime(2026, 11, 5, 9, 40, tzinfo=_ET), "ep_score": score,
        "score_breakdown": breakdown, "score_side": "separation", "ep_bar": 65.0,
        "catalyst_quality": "routine", "gap_pct": 10.0, "adv": 9_000_000.0, "prev_close": 100.0,
        "float_shares": 250_000_000, "vol_percentile": 50.0, "rel_volume": 3.0,
        "projected_vol_multiple": None,
    }


def _wire(monkeypatch, *, audit_rows, scan_days=(), scan_row=None):
    """audit_rows: [(date, summary)]; scan_days: dates with an mi_ep_scan_log row for the ticker."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    seen = {"dates": []}

    def _audit_max(sql, ticker):
        if "ILIKE" in sql:   # the old substring match
            hit = [d for d, s in audit_rows if ticker.lower() in s.lower()]
        else:                # whole word, case-insensitive: what `~* '\m..\M'` means
            rx = re.compile(r"\b" + re.escape(ticker) + r"\b", re.I)
            hit = [d for d, s in audit_rows if rx.search(s)]
        return max(hit) if hit else None

    async def _fetchrow(sql, *args):
        s = " ".join(sql.split())
        if "MAX(d)" in s:
            arms = [_audit_max(s, args[0])]
            if "mi_ep_scan_log" in s:
                arms.append(max(scan_days) if scan_days else None)
            arms = [a for a in arms if a]
            return {"d": max(arms) if arms else None}
        if "score_breakdown" in s:
            seen["dates"].append(args[1])
            return scan_row if args[1] in scan_days else None
        if "filter_reason" in s:
            seen["dates"].append(args[1])
            if args[1] in scan_days:
                return {"filter_reason": "score 61 < bar 65 (catalyst=routine)",
                        "ep_score": 61.2, "gap_pct": 10.0, "score_tier": None}
            return None
        return None

    conn.fetchrow = _fetchrow
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record",
                        AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.db.get_latest_catalyst_grade_date",
                        AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map",
                        AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.agent._send_plain_with_keyboard",
                        AsyncMock(return_value=False))   # falsy -> the body comes back to us
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        AsyncMock(return_value=None))
    return seen


def _why(task):
    res = asyncio.run(MarketIntelligenceAgent()._handle_why_query(
        AgentRequest(task=task, user_id=1, conversation_id="t")))
    return res.result if hasattr(res, "result") else res["result"]


_NOISE = [
    (NOISE_DAY, "APPN: scan complete"),
    (NOISE_DAY, "approved the budget"),
    (NOISE_DAY, "what happened to the run"),
]


def test_a_short_ticker_does_not_match_inside_other_words(monkeypatch):
    """APP must not resolve to a day whose only audit rows say APPN / approved / happened."""
    seen = _wire(monkeypatch, audit_rows=_NOISE, scan_days=(SCAN_DAY,), scan_row=_app_scan_row())
    body = _why("/why APP")
    assert str(SCAN_DAY) in body and str(NOISE_DAY) not in body
    assert set(seen["dates"]) == {SCAN_DAY}


def test_a_whole_word_audit_row_still_counts(monkeypatch):
    """The audit arm is narrowed, not removed: an audit row naming APP itself still resolves."""
    seen = _wire(monkeypatch, audit_rows=_NOISE + [(date(2026, 11, 7), "APP: bar_stream tick")])
    _why("/why APP")
    assert set(seen["dates"]) == {date(2026, 11, 7)}


def test_a_scan_only_day_is_resolved(monkeypatch):
    """A name scanned and dropped has no alert / trade / audit row: the scan log alone must
    carry the resolution (otherwise the bare command lands on today with nothing)."""
    seen = _wire(monkeypatch, audit_rows=[], scan_days=(SCAN_DAY,), scan_row=_app_scan_row())
    body = _why("/why APP")
    assert str(SCAN_DAY) in body
    assert "no alert / trade / audit events" not in body
    assert set(seen["dates"]) == {SCAN_DAY}


def test_the_score_breakdown_is_rendered_for_a_scanned_not_alerted_day(monkeypatch):
    """`/why app` on a dropped name says WHY the score was what it was: each part with its
    points, the bar, and the catalyst grade — plain text, no pipe table."""
    _wire(monkeypatch, audit_rows=[], scan_days=(SCAN_DAY,), scan_row=_app_scan_row())
    short = _why("/why APP")
    assert "WHY NOT ALERTED" in short
    assert "gap 10/10 · liquidity 15/15 · catalyst 0/25" in short       # each part, with its points
    assert "raw 25 of 70 · HIGH bar 40 · 15 short" in short             # the bar, in raw points
    assert "🧠 GRADE NOTE" in short and "routine" in short.lower()      # the catalyst grade
    full = _why(f"/why APP {SCAN_DAY} full")
    assert "🧮 SCORE — " in full and "HIGH bar 65" in full
    assert "|" not in short and "|" not in full
