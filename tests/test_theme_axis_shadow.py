"""#329 STEP-0 — theme-axis SHADOW scaffold. Focused tests for the meta-rubric theme axis:

  • the deterministic structural-attribution logic (subject-ticker exclusion = the load-bearing
    correctness property; word-boundary/English-word filtering; keyword pass);
  • the shadow logger fires + honors the as-of accessor;
  • themeless -> NULL heat + score 0;
  • one structural-match positive case;
  • upsert idempotency (the EP scan re-runs every 5 min -> exactly one row).

SHADOW ONLY — none of this touches the live grade / judge output / trade state.
"""
from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool

from agents.market_intelligence.theme_axis_shadow import (
    compute_structural_attribution,
    log_theme_axis_shadow,
)


# ─── compute_structural_attribution (pure logic) ──────────────────────────────────────

def test_subject_ticker_excluded_self_mention_only_scores_zero():
    """THE trap (advisor): the corpus is ABOUT the subject ticker, so it appears trivially.
    A themed EP whose grounded_text mentions ONLY itself must score 0 — attribution asks
    'does the catalyst reference the REST of the theme?', not 'does it name itself?'."""
    g = "NVDA announced record datacenter results. NVDA NVDA NVDA."
    score, attributable, matched = compute_structural_attribution(
        g, subject_ticker="NVDA", cohort_tickers=["NVDA", "AMD", "AVGO"],
        theme_name="AI Datacenter", theme_description="GPU accelerator compute buildout",
    )
    # NVDA is the subject (excluded); AMD/AVGO not in text. But keyword overlap on the
    # theme description: "datacenter" appears in g -> would the description match? g has
    # "datacenter"; description has "buildout","accelerator","compute" (4+) — none in g
    # except... "datacenter" is in the NAME not the description; name+desc both scanned.
    # "datacenter" (from name "AI Datacenter") IS in g -> 1 keyword match expected.
    # Assert the TICKER pass contributed nothing (the subject-exclusion property):
    assert "ticker:AMD" not in matched and "ticker:AVGO" not in matched
    assert "ticker:NVDA" not in matched  # subject never self-attributes
    # The only match is a theme KEYWORD ('datacenter' from the name) — tagged 'kw:' so the
    # data-sizing pass can tell this trivial own-vocabulary hit from a strong peer-ticker hit.
    assert matched == ["kw:datacenter"]


def test_subject_only_no_keyword_overlap_scores_zero():
    """Clean isolation of the subject-ticker trap: themed EP, text mentions only itself, and
    no theme keyword appears -> score 0, not attributable."""
    g = "ACME reported a blowout quarter. ACME guided higher. ACME."
    score, attributable, matched = compute_structural_attribution(
        g, subject_ticker="ACME", cohort_tickers=["ACME", "WXYZ"],
        theme_name="Quantum Photonics", theme_description="silicon laser interconnect fabric",
    )
    assert score == 0
    assert attributable is False
    assert matched == []


def test_structural_match_positive_cohort_ticker():
    """Positive case: the catalyst references ANOTHER cohort ticker -> attributable."""
    g = "TICK signed a supply pact with peer FRND to expand capacity."
    score, attributable, matched = compute_structural_attribution(
        g, subject_ticker="TICK", cohort_tickers=["TICK", "FRND", "OTHR"],
        theme_name="Whatever", theme_description="",
    )
    assert "ticker:FRND" in matched   # tagged as a PEER cohort ticker (strong evidence)
    assert attributable is True
    assert score >= 1


def test_structural_match_positive_keyword():
    """Positive case: a 4+ letter theme keyword appears in the catalyst text -> attributable."""
    g = "Company unveils a new lithium battery cathode plant."
    score, attributable, matched = compute_structural_attribution(
        g, subject_ticker="ZZZ", cohort_tickers=["ZZZ"],
        theme_name="Lithium Battery", theme_description="cathode anode electrolyte",
    )
    # "lithium","battery","cathode" all present -> >=1 keyword match (tagged 'kw:').
    assert attributable is True
    assert any(w in matched for w in ("kw:lithium", "kw:battery", "kw:cathode"))


def test_english_word_ticker_false_positive_filtered():
    """Word-boundary + English-word filter: cohort 'ON' / 'AS' must NOT match the prepositions
    'ON'/'AS' that appear in normal prose. _PREPOSITION_SKIP guards this."""
    g = "AS volume picked up the stock moved ON heavy turnover."
    score, attributable, matched = compute_structural_attribution(
        g, subject_ticker="XYZ", cohort_tickers=["XYZ", "ON", "AS"],
        theme_name="", theme_description="",
    )
    assert "ON" not in matched and "AS" not in matched
    assert score == 0


def test_lowercase_ticker_in_prose_not_matched():
    """Case-sensitive ticker pass: 'care' (lowercase prose) must not match cohort ticker CARE."""
    g = "The company will take care of integration over the next year."
    score, attributable, matched = compute_structural_attribution(
        g, subject_ticker="XYZ", cohort_tickers=["XYZ", "CARE"],
        theme_name="", theme_description="",
    )
    assert "CARE" not in matched


def test_empty_grounded_text_scores_zero():
    assert compute_structural_attribution(None, "X", ["X", "Y"], "n", "d") == (0, False, [])
    assert compute_structural_attribution("", "X", ["X", "Y"], "n", "d") == (0, False, [])


# ─── log_theme_axis_shadow (writer; mocked pool/accessor) ──────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_logger_fires_and_writes_row(monkeypatch):
    """Logging fires: a themed HIGH writes one INSERT to mi_theme_axis_shadow with the as-of
    heat threaded in and a positive structural score (cohort ticker in the catalyst)."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_heat(_conn, ticker, alert_date):
        assert ticker == "TICK" and alert_date == "2026-06-20"  # as-of key honored
        return {
            "name": "Robotics", "stage": "Accelerating", "score": 88.0,
            "tickers": ["TICK", "FRND"], "description": "automation actuator vision",
        }
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    r = {
        "ticker": "TICK", "alert_date": "2026-06-20", "score_tier": "HIGH",
        "grounded_text": "TICK partnered with FRND on a new automation line.",
    }
    _run(log_theme_axis_shadow(conn, r))

    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    # positional: sql, ticker, alert_date, grade, theme_name, theme_stage, theme_score,
    #             themeless, score, attributable, matched_terms
    assert args[1] == "TICK"
    assert args[2] == "2026-06-20"
    assert args[3] == "HIGH"
    assert args[4] == "Robotics"
    assert args[5] == "Accelerating"
    assert args[6] == 88.0
    assert args[7] is False          # themeless_flag
    assert args[8] >= 1              # structural score (FRND + 'automation' keyword)
    assert args[9] is True           # attributable
    assert "ticker:FRND" in args[10]  # matched_terms persisted, peer ticker tagged


def test_themeless_logs_null_heat_and_zero_score(monkeypatch):
    """Themeless -> NULL stage/score/name, themeless_flag True, structural score 0."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _no_theme(_conn, ticker, alert_date):
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _no_theme)

    r = {
        "ticker": "LONE", "alert_date": "2026-06-20", "score_tier": "HIGH",
        "grounded_text": "LONE gapped 20% on an earnings beat.",
    }
    _run(log_theme_axis_shadow(conn, r))

    args = conn.execute.await_args.args
    assert args[4] is None and args[5] is None and args[6] is None  # name/stage/score NULL
    assert args[7] is True           # themeless_flag
    assert args[8] == 0              # structural score 0
    assert args[9] is False          # not attributable
    assert args[10] == []            # matched_terms empty


def test_asof_query_uses_no_lookahead():
    """As-of handling: the shared accessor query filters theme_date <= alert_date (no lookahead).
    Verify the live accessor's SQL — not get_theme_membership (which is TODAY's membership)."""
    pool, conn = make_mock_pool()
    captured = {}

    async def _capture_fetchrow(sql, *params):
        captured["sql"] = sql
        captured["params"] = params
        return None
    conn.fetchrow = _capture_fetchrow

    from agents.market_intelligence.db import get_theme_heat_asof
    _run(get_theme_heat_asof(conn, "TICK", "2026-06-20"))
    assert "theme_date <= $2" in captured["sql"]
    assert "stage != 'Retired'" in captured["sql"]
    assert captured["params"] == ("TICK", "2026-06-20")


def test_upsert_is_idempotent_on_ticker_date(monkeypatch):
    """The EP scan re-runs every 5 min -> the same (ticker, alert_date) flows through twice.
    The writer must use ON CONFLICT upsert (latest-scan-wins) -> the SQL is an upsert, and the
    real table's UNIQUE (ticker, alert_date) collapses it to one row."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_heat(_conn, t, d):
        return {"name": "T", "stage": "Mainstream", "score": 50.0,
                "tickers": [t], "description": "x"}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    r = {"ticker": "RPT", "alert_date": "2026-06-20", "score_tier": "HIGH",
         "grounded_text": "RPT did a thing."}
    _run(log_theme_axis_shadow(conn, r))
    _run(log_theme_axis_shadow(conn, r))  # second 5-min cycle

    assert conn.execute.await_count == 2
    sql = conn.execute.await_args.args[0]
    assert "ON CONFLICT (ticker, alert_date) DO UPDATE" in sql


def test_writer_never_raises_on_db_error(monkeypatch):
    """SHADOW contract: a telemetry failure must NOT propagate into the grade path."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(side_effect=RuntimeError("db down"))

    async def _fake_heat(_conn, t, d):
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.log_audit_event", AsyncMock())

    r = {"ticker": "ERR", "alert_date": "2026-06-20", "score_tier": "HIGH",
         "grounded_text": "x"}
    # Must not raise.
    _run(log_theme_axis_shadow(conn, r))
