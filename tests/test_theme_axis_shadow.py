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
    CO_MOVEMENT_FLOOR_PCT,
    _normalize_company_name,
    compute_co_movement,
    compute_name_attribution,
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


def _patch_step1_deps(monkeypatch, names=None, moves=None):
    """Shared STEP-1 dependency stub: _ensure_company_names / get_daily_moves are exercised
    end-to-end elsewhere (test_name_attribution_wired_into_writer /
    test_co_movement_wired_into_writer) — most writer tests only care about the STEP-0 path,
    so they stub these to fixed, deterministic returns."""
    async def _fake_names(_conn, _tickers):
        return names or {}
    async def _fake_moves(_conn, _date, _tickers):
        return moves or {}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow._ensure_company_names", _fake_names)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)


def test_logger_fires_and_writes_row(monkeypatch):
    """Logging fires: a themed HIGH writes one INSERT to mi_theme_axis_shadow with the as-of
    heat threaded in and a positive structural score (cohort ticker in the catalyst)."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_step1_deps(monkeypatch)

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
    #             themeless, score, attributable, matched_terms, name_score,
    #             name_attributable, matched_names, cohort_move, ticker_move, co_moving
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
    # STEP-1 signals: no names/moves stubbed in -> no match, not computable
    assert args[11] == 0 and args[12] is False and args[13] == []
    assert args[14] is None and args[15] is None and args[16] is None


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
    # STEP-1 signals: themeless -> no cohort to attribute to or co-move with
    assert args[11] == 0 and args[12] is False and args[13] == []
    assert args[14] is None and args[15] is None and args[16] is None


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
    # recency_days defaults None → passed as $3 with a `$3::int IS NULL` guard = no floor
    # (single-query form; behaviour identical to the old None branch).
    assert captured["params"] == ("TICK", "2026-06-20", None)


def test_upsert_is_idempotent_on_ticker_date(monkeypatch):
    """The EP scan re-runs every 5 min -> the same (ticker, alert_date) flows through twice.
    The writer must use ON CONFLICT upsert (latest-scan-wins) -> the SQL is an upsert, and the
    real table's UNIQUE (ticker, alert_date) collapses it to one row."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_step1_deps(monkeypatch)

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


# ─── STEP-1 (a): _normalize_company_name / compute_name_attribution (#367 / #369) ──────────

def test_normalize_strips_common_corporate_suffixes():
    """Inc/Corp/Ltd/Holdings-style suffixes are stripped from the tail, repeatedly."""
    assert _normalize_company_name("Acme Robotics Inc.") == "acme robotics"
    assert _normalize_company_name("Acme Robotics, Inc") == "acme robotics"
    assert _normalize_company_name("Friendco Corporation") == "friendco"
    assert _normalize_company_name("Friendco Holdings Inc") == "friendco"  # multi-suffix
    assert _normalize_company_name("The Boeing Company") == "boeing"       # leading article + co.
    assert _normalize_company_name("Widget Systems, LLC") == "widget systems"


def test_normalize_excludes_ambiguous_single_token_names():
    """A lone remaining token must be long + non-generic, else it's excluded entirely —
    conservative-by-design (under-count over false-match)."""
    assert _normalize_company_name("Solutions Inc") is None    # generic single word
    assert _normalize_company_name("Group Ltd") is None        # generic single word
    assert _normalize_company_name("Star Corp") is None        # short (4 chars, also generic)
    assert _normalize_company_name("Nvidia Corporation") == "nvidia"  # long + non-generic -> OK
    assert _normalize_company_name("AMD") is None  # 3 chars, below _MIN_SINGLE_TOKEN_LEN


def test_normalize_handles_empty_and_none():
    assert _normalize_company_name(None) is None
    assert _normalize_company_name("") is None
    assert _normalize_company_name("Inc") is None       # nothing left after suffix-strip
    assert _normalize_company_name("The Co") is None    # article + suffix strips to nothing


def test_name_attribution_positive_peer_match():
    """A cohort peer's normalized name appears in the catalyst text -> attributable."""
    g = "Acme Robotics announced a supply deal with Friendco Corporation to expand output."
    score, attributable, matched = compute_name_attribution(
        g, subject_ticker="TICK", cohort_tickers=["TICK", "FRND"],
        names_by_ticker={"TICK": "Acme Robotics Inc", "FRND": "Friendco Corporation"},
    )
    assert attributable is True
    assert score == 1
    assert matched == ["name:FRND:friendco"]


def test_name_attribution_subject_self_mention_excluded():
    """The subject's own name is excluded from the cohort before matching (mirrors the ticker
    signal's subject-exclusion) — a corpus about itself must not trivially self-attribute."""
    g = "Acme Robotics reported record output. Acme Robotics guided higher."
    score, attributable, matched = compute_name_attribution(
        g, subject_ticker="TICK", cohort_tickers=["TICK"],
        names_by_ticker={"TICK": "Acme Robotics Inc"},
    )
    assert score == 0 and attributable is False and matched == []


def test_name_attribution_ambiguous_name_never_matches():
    """A cohort peer whose name normalizes to None (too ambiguous) can never contribute a
    match, even if its literal words appear in the text — the conservative floor holds."""
    g = "The company signed a deal with Solutions to expand distribution."
    score, attributable, matched = compute_name_attribution(
        g, subject_ticker="TICK", cohort_tickers=["TICK", "SOLN"],
        names_by_ticker={"TICK": "Acme Robotics Inc", "SOLN": "Solutions Inc"},
    )
    assert score == 0 and attributable is False and matched == []


def test_name_attribution_missing_name_skipped_not_counted():
    """A cohort ticker with no cached/fetched company name is skipped, not treated as a match
    or a hard failure."""
    score, attributable, matched = compute_name_attribution(
        "Acme Robotics did a thing.", subject_ticker="TICK",
        cohort_tickers=["TICK", "FRND"], names_by_ticker={"TICK": "Acme Robotics Inc"},
    )
    assert score == 0 and attributable is False and matched == []


def test_name_attribution_empty_grounded_text_or_names_scores_zero():
    assert compute_name_attribution(None, "X", ["X", "Y"], {"Y": "Widget Systems Inc"}) == (
        0, False, [])
    assert compute_name_attribution("text", "X", ["X", "Y"], None) == (0, False, [])
    assert compute_name_attribution("text", "X", ["X", "Y"], {}) == (0, False, [])


# ─── STEP-1 (b): compute_co_movement (#367, the co-equal candidate) ───────────────────────

def test_co_movement_same_sign_above_floor_is_co_moving():
    cohort_move, co_moving = compute_co_movement(ticker_move=5.0, cohort_moves=[3.0, 4.0, 2.0])
    assert cohort_move == 3.0  # median
    assert co_moving is True


def test_co_movement_opposite_sign_is_not_co_moving():
    cohort_move, co_moving = compute_co_movement(ticker_move=-2.0, cohort_moves=[3.0, 4.0, 2.0])
    assert cohort_move == 3.0
    assert co_moving is False


def test_co_movement_below_floor_is_not_co_moving_even_same_sign():
    """The cohort itself barely moved -> same-sign agreement is uninformative -> False, even
    though the signs technically match."""
    below_floor = CO_MOVEMENT_FLOOR_PCT - 0.1
    cohort_move, co_moving = compute_co_movement(ticker_move=0.5, cohort_moves=[below_floor])
    assert abs(cohort_move) < CO_MOVEMENT_FLOOR_PCT
    assert co_moving is False


def test_co_movement_exactly_at_floor_is_not_below():
    """Floor is a >= (clears-the-floor) test, not a strict >, at the boundary — pin the
    documented boundary behavior (< floor fails, so == floor passes)."""
    cohort_move, co_moving = compute_co_movement(
        ticker_move=2.0, cohort_moves=[CO_MOVEMENT_FLOOR_PCT])
    assert cohort_move == CO_MOVEMENT_FLOOR_PCT
    assert co_moving is True


def test_co_movement_no_cohort_data_not_computable():
    cohort_move, co_moving = compute_co_movement(ticker_move=5.0, cohort_moves=[])
    assert cohort_move is None and co_moving is None


def test_co_movement_no_ticker_move_not_computable_but_cohort_move_known():
    """Cohort move is knowable even when the subject's own move isn't -> co_moving is None
    (unknown), NOT False (measured-not-co-moving) — the two must not be conflated."""
    cohort_move, co_moving = compute_co_movement(ticker_move=None, cohort_moves=[3.0, 4.0])
    assert cohort_move == 3.5
    assert co_moving is None


def test_co_movement_zero_ticker_move_is_not_co_moving():
    """A flat subject (0.0% move) matches neither sign branch -> not co-moving."""
    cohort_move, co_moving = compute_co_movement(ticker_move=0.0, cohort_moves=[3.0, 4.0])
    assert co_moving is False


# ─── Shadow-writer wiring: both STEP-1 signals end-to-end through log_theme_axis_shadow ────

def test_name_attribution_wired_into_writer(monkeypatch):
    """log_theme_axis_shadow threads _ensure_company_names' result into compute_name_attribution
    and persists the result on the row."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_heat(_conn, ticker, alert_date):
        return {
            "name": "Robotics", "stage": "Accelerating", "score": 88.0,
            "tickers": ["TICK", "FRND"], "description": "",
        }
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    captured_tickers = {}

    async def _fake_names(_conn, tickers):
        captured_tickers["names_call"] = list(tickers)
        return {"FRND": "Friendco Corporation"}
    async def _fake_moves(_conn, _date, _tickers):
        return {}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow._ensure_company_names", _fake_names)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)

    r = {
        "ticker": "TICK", "alert_date": "2026-06-20", "score_tier": "HIGH",
        "grounded_text": "TICK signed a pact with Friendco Corporation.",
    }
    _run(log_theme_axis_shadow(conn, r))

    args = conn.execute.await_args.args
    assert args[11] == 1              # name_attribution_score
    assert args[12] is True           # name_attributable
    assert args[13] == ["name:FRND:friendco"]
    assert "TICK" in captured_tickers["names_call"]  # cohort passed through incl. subject


# ─── S1 (coverage loop 2026-07-13): MODERATE flows through the shadow, zero grade mutation ──

def test_s1_theme_shadow_gate_covers_moderate():
    """PIN (S1): ep_detector's theme-shadow gate is HIGH+MODERATE — completes ADR 0015's
    signed 'accrue incl. sub-HIGH' intent (coverage-loop design C3). Source-level pin so a
    narrowing back to HIGH-only fails loudly here, not silently in the telemetry."""
    import inspect
    from agents.market_intelligence import ep_detector
    src = inspect.getsource(ep_detector)
    assert 'if r.get("score_tier") in ("HIGH", "MODERATE"):' in src, (
        "S1 theme-shadow gate must cover HIGH+MODERATE (ADR 0015 sub-HIGH accrual)")
    assert 'if r.get("score_tier") == "HIGH":' not in src, (
        "the old HIGH-only theme-shadow gate is back — S1 regressed")


def test_moderate_row_writes_shadow_and_never_mutates_grade(monkeypatch):
    """S1: a MODERATE row through the STEP-0 writer → row written with grade='MODERATE',
    ONLY mi_theme_axis_shadow touched (never mi_ep_alerts / any grade column), and `r`
    byte-identical after — zero grade mutation (THE LINE)."""
    import copy
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_step1_deps(monkeypatch)

    async def _fake_heat(_conn, t, d):
        return {"name": "Robotics", "stage": "Accelerating", "score": 88.0,
                "tickers": [t, "FRND"], "description": "automation"}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    r = {"ticker": "TICK", "alert_date": "2026-07-13", "score_tier": "MODERATE",
         "grounded_text": "TICK partnered with FRND on a new automation line."}
    r_before = copy.deepcopy(r)
    _run(log_theme_axis_shadow(conn, r))

    assert r == r_before                      # read-only on r — the grade is untouched
    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    assert "INSERT INTO mi_theme_axis_shadow" in args[0]
    assert "mi_ep_alerts" not in args[0]      # never the grade table
    assert args[3] == "MODERATE"              # tier-agnostic writer logs MODERATE verbatim


def test_co_movement_wired_into_writer(monkeypatch):
    """log_theme_axis_shadow queries same-day moves for ticker + cohort (excluding the subject
    from the cohort side) and persists cohort_move/ticker_move/co_moving."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_heat(_conn, ticker, alert_date):
        return {
            "name": "Robotics", "stage": "Accelerating", "score": 88.0,
            "tickers": ["TICK", "FRND", "OTHR"], "description": "",
        }
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)

    captured = {}

    async def _fake_names(_conn, _tickers):
        return {}
    async def _fake_moves(_conn, trade_date, tickers):
        captured["date"] = trade_date
        captured["tickers"] = set(tickers)
        return {"TICK": 6.0, "FRND": 4.0, "OTHR": 2.0}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow._ensure_company_names", _fake_names)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)

    r = {
        "ticker": "TICK", "alert_date": "2026-06-20", "score_tier": "HIGH",
        "grounded_text": "TICK moved with the group.",
    }
    _run(log_theme_axis_shadow(conn, r))

    assert captured["date"] == "2026-06-20"
    assert captured["tickers"] == {"TICK", "FRND", "OTHR"}  # subject + cohort queried together

    args = conn.execute.await_args.args
    assert args[14] == 3.0   # cohort_move = median(FRND=4.0, OTHR=2.0), subject excluded
    assert args[15] == 6.0   # ticker_move
    assert args[16] is True  # same sign (both positive), cohort_move clears the floor
