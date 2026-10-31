"""#713 (2026-10-30, operator-directed) — `/why TICKER` shows HOW the EP score was built.

Operator, 2026-10-29: FTAI scored 61.2 under a bar of 65 and neither /setup nor /why showed
the parts. The stored `mi_ep_scan_log.score_breakdown` is the RAW parts (gap 10 + liquidity 12
+ catalyst 15 = 37); the regime multiplier and the #533 presentation rescale
(1.25 x final + 15) sit outside it, and the HIGH bar 65 is a raw 40.

These tests drive the renderer with rows produced by the REAL `_score_ep` (never a hand-typed
breakdown standing in for the producer's shape), so the numbers the operator reads are
the numbers the scorer made. Everything here is DISPLAY: no score, bar or weight moves.
"""
import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from agents.market_intelligence.agent import MarketIntelligenceAgent, _why_score_block
from agents.market_intelligence.ep_detector import _score_ep
from agents.market_intelligence.ep_rubric import (
    SCORE_WEIGHTS_LEGACY, SEPARATION_BAR, apply_output_scale,
)
from agents.market_intelligence.ep_score_math import score_math_lines, theme_read_lines
from shared.models import AgentRequest

_ET = ZoneInfo("America/New_York")
_SCAN_AT = datetime(2026, 10, 29, 9, 55, tzinfo=_ET)


def _scored_row(*, gap=10.76, quality="strong", adv_dollar=300_000_000, float_shares=120_000_000,
                vol_pct=50.0, theme=False, mult=1.0, weights=None, bar=65.0, side="separation"):
    """A scan-log row built from the real scorer's own output."""
    kw = {} if weights is None else {"weights": weights}
    score, breakdown = _score_ep(
        gap_pct=gap, rel_volume=3.0, catalyst_quality=quality,
        profile={"floatShares": float_shares}, regime_multiplier=mult,
        vol_percentile=vol_pct, adv_dollar=adv_dollar, in_active_theme=theme, **kw)
    return {
        "scan_time_et": _SCAN_AT, "ep_score": score, "score_breakdown": breakdown,
        "score_side": side, "ep_bar": bar, "catalyst_quality": quality, "gap_pct": gap,
        "adv": adv_dollar / 100.0, "prev_close": 100.0, "float_shares": float_shares,
        "vol_percentile": vol_pct, "rel_volume": 3.0,
    }


def _text(row):
    return "\n".join(score_math_lines(row))


# ── the FTAI 10-29 case ───────────────────────────────────────────────────────────────


def test_ftai_1029_reproduces_61_2_and_shows_every_step():
    row = _scored_row()
    assert row["ep_score"] == 61.2                       # the real scorer made 61.2
    assert row["score_breakdown"] == {"gap": 10, "liquidity": 12, "catalyst": 15,
                                      "float": 0, "vol_conviction": 0, "theme_bonus": 0}
    out = _text(row)
    # answer first: the header says the score and the raw-point gap to the bar
    assert out.lstrip().startswith("🧮 SCORE — 61.2, 3 raw points short of the HIGH bar 65")
    assert "(09:55 ET scan)" in out
    # each part with its points
    for part in ("gap +10", "liquidity +12", "catalyst +15", "float +0",
                 "pre-market volume +0", "theme +0"):
        assert part in out
    # what the NEXT tier pays, read from the rubric table (500M -> 15, game-changing -> 25)
    assert "next tier $500M pays 15" in out
    assert "next grade up: game-changing pays 25" in out
    assert "under 50M pays 5" in out
    assert "next tier 70th percentile pays 3" in out
    assert "a paying theme pays 10" in out
    # the arithmetic, end to end
    assert "raw total 37" in out
    assert "x1.00 regime multiplier" in out and "worked back from the stored score" in out
    assert "rescale 1.25 x 37 + 15 = 61.2" in out
    assert "HIGH bar 65 (= 40 before the rescale) needs a raw total of 40; this has 37" in out
    # and the FTAI question: the theme points alone would have cleared it
    alt = _scored_row(theme=True)["ep_score"]
    assert f"it would have scored {alt:g}, over the bar" in out


def test_the_rebuilt_number_always_matches_the_stored_score():
    """Whatever the row, the steps printed must rebuild the stored score; if they could
    not, the section says so instead of printing a wrong chain."""
    for kw in ({}, {"quality": "game_changer", "mult": 1.2},
               {"gap": 12.0, "adv_dollar": 600_000_000, "vol_pct": 95.0, "theme": True}):
        row = _scored_row(**kw)
        out = _text(row)
        assert "does NOT reconcile" not in out
        assert f"= {row['ep_score']:g}" in out


# ── game changer + theme, Bull day ────────────────────────────────────────────────────


def test_game_changer_in_a_theme_on_a_bull_day_clears_the_bar_with_room():
    row = _scored_row(gap=12.0, quality="game_changer", adv_dollar=600_000_000,
                      float_shares=30_000_000, vol_pct=95.0, theme=True, mult=1.2)
    assert row["score_breakdown"]["theme_bonus"] == 10 and row["score_breakdown"]["catalyst"] == 25
    out = _text(row)
    assert f"🧮 SCORE — {row['ep_score']:.1f}, clears the HIGH bar 65" in out
    assert "catalyst +25  graded game-changing · top grade" in out
    assert "theme +10  in a paying theme · top tier" in out
    assert "float +5" in out and "pre-market volume +5" in out and "liquidity +15" in out
    assert "x1.20 regime multiplier (Bull-day boost" in out
    # the bar line shows why 70 beats a bar that reads 40: a raw 34 x 1.20 is 40.8
    assert "needs a raw total of 34 (34 x 1.20 = 40.8); this has 70 (36 to spare)" in out
    # the floor exists in the breakdown but lifted nothing — must NOT claim it did
    assert "lifted nothing" in out
    assert "to spare" in out
    # a cleared name gets no "theme alone would have cleared it" line
    assert "it would have scored" not in out


# ── conviction floor ──────────────────────────────────────────────────────────────────


def test_a_binding_conviction_floor_is_shown_with_its_rule():
    row = _scored_row(gap=10.5, quality="game_changer", adv_dollar=60_000_000,
                      float_shares=120_000_000, mult=1.2)
    bd = row["score_breakdown"]
    assert bd["gap"] + bd["liquidity"] + bd["catalyst"] == 42        # under the floor
    assert bd["conviction_floor"] == 18                             # 60 - 42
    out = _text(row)
    assert "conviction floor +18  a game-changing catalyst on a gap of 10% or more " \
           "lifts the raw total to at least 60" in out
    assert "raw total 60" in out
    assert f"= {row['ep_score']:g}" in out


# ── NULL / missing / legacy / old rows ────────────────────────────────────────────────


def test_a_row_with_no_stored_parts_says_so_plainly():
    out = _text({"scan_time_et": _SCAN_AT, "ep_score": 55.0, "score_breakdown": None})
    assert "SCORE — 55.0 (09:55 ET scan)" in out
    assert "score parts were not stored" in out


def test_no_row_renders_nothing_and_never_raises():
    assert score_math_lines(None) == []
    assert score_math_lines({}) == []
    # a malformed JSON string reads as "not stored", not a crash
    assert "not stored" in _text({"ep_score": 50.0, "score_breakdown": "{not json"})


def test_a_string_breakdown_from_a_codecless_connection_still_renders():
    import json
    row = _scored_row()
    row["score_breakdown"] = json.dumps(row["score_breakdown"])
    assert "raw total 37" in _text(row)


def test_the_legacy_side_has_no_rescale_and_reads_the_legacy_ladder():
    row = _scored_row(gap=17.0, quality="strong", weights=SCORE_WEIGHTS_LEGACY,
                      side="legacy", bar=70.0)
    out = _text(row)
    assert "no rescale on this row" in out
    assert "rescale 1.25" not in out
    # legacy gap ladder: 17% pays 20; the next tier up is a 20% gap paying 25
    assert "gap +20" in out and "next tier 20% pays 25" in out
    assert f"= {row['ep_score']:g}" in out


def test_an_older_row_with_axes_the_table_no_longer_has_still_adds_up():
    row = {"scan_time_et": _SCAN_AT, "ep_score": 45.0, "score_side": "legacy", "ep_bar": 70.0,
           "score_breakdown": {"gap": 25, "rvol": 10, "prior_momentum": -5, "catalyst": 15}}
    out = _text(row)
    assert "rvol +10  (not in the current score table)" in out
    assert "prior momentum -5" in out        # no raw snake_case key in the operator's text
    assert "raw total 45" in out


def test_the_raw_gap_is_exact_at_the_boundary():
    """40 raw presents as exactly 65.0 (clears); 39 presents as 63.8 (1 point short)."""
    def row_for(raw):
        return {"scan_time_et": _SCAN_AT, "ep_score": apply_output_scale(float(raw), {
            "mult": 1.25, "offset": 15}), "score_breakdown": {"gap": 10, "catalyst": raw - 10},
            "score_side": "separation", "ep_bar": 65.0, "gap_pct": 9.0}
    assert "clears the HIGH bar 65" in _text(row_for(40))
    short = _text(row_for(39))
    assert "1 raw point short of the HIGH bar 65" in short           # singular
    assert "2 raw points short" in _text(row_for(38))


def test_the_bar_falls_back_to_the_separation_bar_when_the_row_has_none():
    row = _scored_row()
    row["ep_bar"] = None
    assert f"HIGH bar {SEPARATION_BAR}" in _text(row)


# ── plain-text contract ───────────────────────────────────────────────────────────────


def test_the_section_is_plain_text_no_pipe_table_no_markdown():
    """`/why` posts with no parse_mode and Telegram cannot render pipe tables."""
    old_axes = {"scan_time_et": _SCAN_AT, "ep_score": 45.0, "score_side": "legacy", "ep_bar": 70.0,
                "score_breakdown": {"gap": 25, "rvol": 10, "prior_momentum": -5, "catalyst": 15}}
    for row in (_scored_row(), _scored_row(quality="game_changer", gap=12.0, theme=True, mult=1.2),
                _scored_row(gap=10.5, quality="game_changer", adv_dollar=60_000_000, mult=1.2),
                _scored_row(gap=17.0, weights=SCORE_WEIGHTS_LEGACY, side="legacy", bar=70.0),
                old_axes):
        out = _text(row)
        assert "|" not in out
        assert "*" not in out and "`" not in out
        assert "_" not in out          # no raw snake_case enum leaks into the operator's text


# ── the theme read ────────────────────────────────────────────────────────────────────

_FTAI_SHADOW = {
    "listed": False, "best_theme": "Building Products & HVAC/Industrial Motion Rotation",
    "best_stage": "Mainstream", "best_corr": 0.3544,
    "shortlist": '[{"theme": "Building Products & HVAC/Industrial Motion Rotation", '
                 '"stage": "Mainstream", "corr": 0.3544}]',
    "fit_status": "rejected",
    "fit_rationale": "Aviation leasing; unrelated to building products/HVAC theme",
    "shortlist_bar": 0.35, "acting_in_theme": False,
}


def test_theme_read_ftai_shortlisted_and_rejected():
    out = "\n".join(theme_read_lines(_FTAI_SHADOW))
    assert "not listed in a paying theme" in out
    assert "Building Products & HVAC/Industrial Motion Rotation" in out
    assert "Mainstream, price co-movement 0.35" in out
    assert "judged it NOT a fit" in out
    assert "Aviation leasing; unrelated to building products/HVAC theme" in out
    assert "|" not in out


def test_theme_read_other_verdicts_in_plain_words():
    nm = "\n".join(theme_read_lines({"listed": False, "fit_status": "not_shortlisted",
                                     "best_theme": "Semis", "best_stage": "Mainstream",
                                     "best_corr": 0.12, "shortlist_bar": 0.35}))
    assert "no paying theme's stocks moved with it" in nm
    assert "closest was Semis (Mainstream, price co-movement 0.12) (under the shortlist bar 0.35)" in nm
    ok = "\n".join(theme_read_lines({"listed": False, "fit_status": "confirmed",
                                      "fit_theme": "AI Power", "acting_in_theme": False}))
    assert "judged it a fit for AI Power" in ok and "no points were paid" in ok
    paid = "\n".join(theme_read_lines({"listed": False, "fit_status": "confirmed",
                                        "fit_theme": "AI Power", "acting_in_theme": True}))
    assert "the points were paid" in paid
    assert "the fit check timed out" in "\n".join(
        theme_read_lines({"listed": False, "fit_status": "timeout"}))
    assert "IS listed" in "\n".join(theme_read_lines({"listed": True}))
    assert "no belonging-check record" in "\n".join(theme_read_lines(None))


# ── the /why handler wiring ───────────────────────────────────────────────────────────


def _wire(monkeypatch, *, score_row, shadow_row, score_sql_raises=False):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    seen = {"sql": []}

    async def _fetchrow(sql, *args):
        seen["sql"].append((sql, args))
        if "MAX(d)" in sql:
            return {"d": date(2026, 10, 29)}
        if "mi_ep_theme_belonging_shadow" in sql:
            return shadow_row
        if "score_breakdown" in sql:
            if score_sql_raises:
                raise RuntimeError("boom")
            return score_row
        if "filter_reason" in sql:       # the existing 'scanned, not alerted' read
            return {"filter_reason": "score 61 < bar 65 (catalyst=strong)", "ep_score": 61.2,
                    "gap_pct": 10.76, "score_tier": None}
        return None

    conn.fetchrow = _fetchrow
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record",
                        AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.db.get_latest_catalyst_grade_date",
                        AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map",
                        AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.agent._send_plain_with_keyboard",
                        AsyncMock(return_value=False))
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        AsyncMock(return_value=None))
    return seen


def _why(task="/why FTAI 2026-10-29 full"):   # #716: the long layout is `full`
    agent = MarketIntelligenceAgent()
    res = asyncio.run(agent._handle_why_query(
        AgentRequest(task=task, user_id=1, conversation_id="t")))
    return res.result if hasattr(res, "result") else res["result"]


def test_why_prints_the_score_section_and_the_theme_read_for_ftai(monkeypatch):
    seen = _wire(monkeypatch, score_row=_scored_row(), shadow_row=dict(_FTAI_SHADOW))
    body = _why()
    assert "🧮 SCORE — 61.2, 3 raw points short of the HIGH bar 65 (09:55 ET scan)" in body
    assert "rescale 1.25 x 37 + 15 = 61.2" in body
    assert "theme read: not listed in a paying theme" in body and "judged it NOT a fit" in body
    # the existing sections are still there
    assert "DETECTED — scanned, NOT alerted" in body
    # the scan-log read is for THIS ticker and day, scored rows only
    score_sql, args = next((s, a) for s, a in seen["sql"] if "score_breakdown" in s)
    assert args[0] == "FTAI" and args[1] == date(2026, 10, 29) and args[2] is None
    assert "ep_score IS NOT NULL" in score_sql


def test_why_with_a_paying_theme_asks_no_theme_question(monkeypatch):
    row = _scored_row(gap=12.0, theme=True)
    seen = _wire(monkeypatch, score_row=row, shadow_row=None)
    body = _why()
    assert "theme +10  in a paying theme" in body
    assert "theme read:" not in body
    assert not any("mi_ep_theme_belonging_shadow" in s for s, _ in seen["sql"])


def test_a_broken_score_read_degrades_to_the_old_output_never_raises(monkeypatch):
    _wire(monkeypatch, score_row=None, shadow_row=None, score_sql_raises=True)
    body = _why()
    assert "SCORE" not in body
    assert "DETECTED — scanned, NOT alerted" in body        # the diagnosis is untouched


def test_why_with_a_score_but_no_stored_parts_says_so(monkeypatch):
    row = {"scan_time_et": _SCAN_AT, "ep_score": 55.0, "score_breakdown": None}
    _wire(monkeypatch, score_row=row, shadow_row=None)
    body = _why()
    assert "score parts were not stored" in body
    assert "theme read:" not in body          # no breakdown -> no theme claim


def test_the_block_picks_the_row_closest_to_the_alerted_score():
    """An alert's section must describe the tick that alerted, not a later, higher one."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    captured = {}

    async def _fetchrow(sql, *args):
        captured["args"] = args
        return None

    conn.fetchrow = _fetchrow
    assert asyncio.run(_why_score_block(pool, "TWLO", date(2026, 10, 29), 83)) == []
    assert captured["args"] == ("TWLO", date(2026, 10, 29), 83.0)


def test_the_two_new_statements_parse_as_postgres_sql(monkeypatch):
    """No Postgres runs in the test env, so the strongest offline check on the two statements the
    handler really sends is Postgres's own parser (pglast): a typo or a stray token would
    otherwise be swallowed by the display-only try/except and silently drop the section."""
    import pytest
    pglast = pytest.importorskip("pglast")
    seen = _wire(monkeypatch, score_row=_scored_row(), shadow_row=dict(_FTAI_SHADOW))
    _why()
    stmts = [s for s, _ in seen["sql"]
             if "score_breakdown" in s or "mi_ep_theme_belonging_shadow" in s]
    assert len(stmts) == 2
    for sql in stmts:
        pglast.parse_sql(sql)
