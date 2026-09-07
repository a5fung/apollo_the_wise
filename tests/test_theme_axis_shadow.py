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
    LABEL_SETTLED_MIN_SESSIONS_5D,
    LABEL_WINNER_FWD_5D_PCT,
    _normalize_company_name,
    classify_label_stratum,
    compute_co_movement,
    compute_name_attribution,
    compute_structural_attribution,
    log_theme_axis_shadow,
    refresh_co_movement_for_date,
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


# ─── EOD co-movement refresh (#329 STEP-0 completion) ─────────────────────────────────────
# The intraday writer runs before today's mi_daily_closes exist -> co_moving is NULL on every
# live row; refresh_co_movement_for_date is the 17:58 EOD recompute that makes the INDEPENDENT
# check actually accrue. These pin its as-of discipline + shadow contract.

from datetime import date  # noqa: E402  (test-local import, mirrors file style)


def _make_refresh_conn(rows):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rows)
    conn.execute = AsyncMock()
    return conn


def test_refresh_recomputes_co_movement_strictly_prior(monkeypatch):
    """A themed row on trade_date gets its co-movement recomputed EOD, with the theme cohort
    re-derived at alert_date MINUS 1 DAY — strictly-prior state, reproducing what the 9:35 AM
    scan saw (today's theme snapshot didn't exist yet) and blocking the born-today-theme
    circularity (a cohort born from today's move would trivially co-move)."""
    conn = _make_refresh_conn([{"ticker": "TICK", "alert_date": date(2026, 7, 24)}])
    captured = {}

    async def _fake_heat(_conn, ticker, asof):
        captured["asof"] = asof
        return {"name": "Robotics", "stage": "Accelerating", "score": 88.0,
                "tickers": ["TICK", "FRND", "OTHR"], "description": ""}

    async def _fake_moves(_conn, trade_date, tickers):
        captured["moves_date"] = trade_date
        return {"TICK": 6.0, "FRND": 4.0, "OTHR": 2.0}

    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake_heat)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_daily_moves", _fake_moves)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.log_audit_event", AsyncMock())

    out = _run(refresh_co_movement_for_date(conn, date(2026, 7, 24)))

    assert captured["asof"] == date(2026, 7, 23)      # STRICTLY prior — the load-bearing pin
    assert captured["moves_date"] == date(2026, 7, 24)  # moves are the alert day's own
    assert out == {"refreshed": 1, "skipped": 0}
    sql = conn.execute.await_args.args[0]
    assert "UPDATE mi_theme_axis_shadow" in sql
    # Writes ONLY the three co-movement columns — never attribution/heat/grade columns.
    for col in ("cohort_move", "ticker_move", "co_moving"):
        assert col in sql
    for col in ("name_attribution", "structural_attribution", "theme_stage", "grade"):
        assert col not in sql
    args = conn.execute.await_args.args
    assert args[3] == 3.0    # cohort_move = median(FRND, OTHR), subject excluded
    assert args[4] == 6.0    # ticker_move
    assert args[5] is True   # co_moving


def test_refresh_selects_only_themed_rows_for_the_date():
    """The refresh query is scoped to trade_date AND themeless_flag = FALSE — themeless rows
    have no cohort to co-move with and must stay NULL, not be recomputed."""
    conn = _make_refresh_conn([])
    _run(refresh_co_movement_for_date(conn, date(2026, 7, 24)))
    sql = conn.fetch.await_args.args[0]
    assert "themeless_flag = FALSE" in sql
    assert "alert_date = $1" in sql


def test_refresh_skips_rows_whose_cohort_is_not_rederivable(monkeypatch):
    """heat=None at the strictly-prior as-of (e.g. the theme's first snapshot IS today) ->
    the row is skipped (columns stay NULL), never guessed from today's snapshot."""
    conn = _make_refresh_conn([{"ticker": "NEWB", "alert_date": date(2026, 7, 24)}])

    async def _no_heat(_conn, _t, _d):
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _no_heat)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.log_audit_event", AsyncMock())

    out = _run(refresh_co_movement_for_date(conn, date(2026, 7, 24)))
    assert out == {"refreshed": 0, "skipped": 1}
    conn.execute.assert_not_awaited()


def test_refresh_never_raises_on_db_error(monkeypatch):
    """SHADOW contract: a refresh failure must swallow to an audit event, never propagate
    (the job wrapper would otherwise mark the whole EOD chain red for pure telemetry)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=RuntimeError("db down"))
    audit = AsyncMock()
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.log_audit_event", audit)

    out = _run(refresh_co_movement_for_date(conn, date(2026, 7, 24)))  # must not raise
    assert out == {"refreshed": 0, "skipped": 0}
    assert audit.await_count == 1
    assert audit.await_args.args[0] == "theme_axis_co_move_refresh_failed"


def test_refresh_job_registered_after_nightly_pull():
    """Source pin: scheduler registers theme_axis_co_move_refresh at 17:58 ET (after the
    17:00 nightly pull ingests today's mi_daily_closes — the same dependency the 17:55
    coverage probe rides). Without the job the independent check never accrues live."""
    import inspect
    from agents.market_intelligence import scheduler as sched
    src = inspect.getsource(sched)
    assert 'id="theme_axis_co_move_refresh"' in src
    idx = src.index('id="theme_axis_co_move_refresh"')
    block = src[idx - 400:idx]
    assert "hour=17, minute=58" in block


# ─── classify_label_stratum (#329 STEP-0 part 3 — the label-cohort enrolment rule) ─────────

def test_stratum_themed_enrols_regardless_of_outcome():
    """Every themed row enrols — the asymmetric boost's only acting population; its
    false-positive side needs labels even (especially) when the trade went nowhere."""
    assert classify_label_stratum(False, None, None) == "themed"
    assert classify_label_stratum(False, -12.0, 5) == "themed"
    assert classify_label_stratum(False, 40.0, 5) == "themed"


def test_stratum_themeless_settled_winner_enrols():
    assert classify_label_stratum(True, 12.0, 5) == "themeless_winner"
    # Boundary: the established win bar is >= +5% (not strict >).
    assert classify_label_stratum(True, LABEL_WINNER_FWD_5D_PCT, 5) == "themeless_winner"


def test_stratum_themeless_unsettled_or_loser_not_enrolled():
    assert classify_label_stratum(True, 12.0, LABEL_SETTLED_MIN_SESSIONS_5D - 1) is None
    assert classify_label_stratum(True, 4.9, 5) is None      # below the win bar
    assert classify_label_stratum(True, None, None) is None  # no outcome row at all
    assert classify_label_stratum(True, 12.0, None) is None  # outcome without session count


def test_seeder_upsert_never_overwrites_operator_labels():
    """Source pin on the seeding script: the ON CONFLICT update must be guarded by
    `operator_label IS NULL` — re-seeding can top up the cohort but NEVER clobber a row the
    operator already labeled (the labels are #368's ground truth)."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "scripts" / "seed_theme_relevance_cohort.py"
    text = src.read_text()
    assert "operator_label IS NULL" in text
    # The enrolment rule is the ONE shared classifier, not a re-implementation.
    assert "from agents.market_intelligence.theme_axis_shadow import classify_label_stratum" \
        in text


# ─── #486: the shadow records BOTH theme reads (bounded + unbounded) ────────────────────
# WHY. get_theme_heat_asof's default has NO recency floor, so the shadow walks back to the
# newest non-Retired snapshot containing the ticker however old it is; the LIVE credit path
# (in_active_theme) is 7d-bounded. Measured 2026-08-29 over 107 shadow rows carrying a theme:
# 35 (33%) were staler than the live path accepts, 15 of them over 30 days old, averaging 64.
# A judge-vs-engine cross-validation built on that table was comparing two different
# definitions of "themed" — and it led to five rows being mis-read as a live-flag defect when
# the live flag had been right every time.
#
# ⚠ These tests exist because the writer's bounded read is wrapped in its own try/except (a
# diagnostic must never cost the caller its row). That means a BROKEN call degrades silently to
# NULL and the suite still passes — so "the tests are green" is not evidence the read ran.
# Every test below asserts on the VALUE written, never on the absence of an exception.

def _heat_stub(monkeypatch, unbounded, bounded):
    """Stub get_theme_heat_asof with a recency-aware fake: recency_days=None -> the unbounded
    answer, recency_days=7 -> the bounded one. Accepting the kwarg is itself the contract."""
    calls = []

    async def _fake(_conn, ticker, alert_date, recency_days=None):
        calls.append(recency_days)
        return bounded if recency_days else unbounded
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake)
    return calls


_T = {"name": "Robotics", "stage": "Accelerating", "score": 88.0,
      "tickers": ["TICK"], "description": "automation"}
_ROW = {"ticker": "TICK", "alert_date": "2026-06-20", "score_tier": "HIGH",
        "grounded_text": "TICK shipped an automation line."}


def _write(monkeypatch, unbounded, bounded):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_step1_deps(monkeypatch)
    calls = _heat_stub(monkeypatch, unbounded, bounded)
    _run(log_theme_axis_shadow(conn, _ROW))
    args = conn.execute.await_args.args
    return args, calls


def test_both_reads_are_requested_and_the_bounded_one_is_written(monkeypatch):
    stale = dict(_T, name="StaleTheme", stage="Mainstream")
    args, calls = _write(monkeypatch, unbounded=stale, bounded=None)
    assert None in calls and 7 in calls, f"both reads must be requested, saw {calls}"
    assert args[4] == "StaleTheme"          # unbounded columns keep their old meaning
    assert args[17] is None                 # theme_name_7d — bounded found nothing
    assert args[18] is None                 # theme_stage_7d
    assert args[19] is False                # bounded_matches_unbounded: they DISAGREE


def test_agreement_is_recorded_when_both_reads_find_the_same_theme(monkeypatch):
    args, _ = _write(monkeypatch, unbounded=_T, bounded=_T)
    assert args[17] == "Robotics" and args[18] == "Accelerating"
    assert args[19] is True


def test_both_finding_nothing_counts_as_agreement_not_as_a_mismatch(monkeypatch):
    """A themeless name is not a disagreement — the cross-validation filters on this column,
    so conflating 'neither found a theme' with 'they differ' would inflate the mismatch set."""
    args, _ = _write(monkeypatch, unbounded=None, bounded=None)
    assert args[17] is None and args[18] is None
    assert args[19] is True


def test_a_failing_bounded_read_writes_NULL_not_FALSE(monkeypatch):
    """NULL means 'not captured'; FALSE means 'captured, and they disagreed'. A diagnostic
    failure must not masquerade as a measured mismatch — the co_moving discipline."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _patch_step1_deps(monkeypatch)

    async def _fake(_conn, ticker, alert_date, recency_days=None):
        if recency_days:
            raise RuntimeError("bounded read exploded")
        return _T
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _fake)

    _run(log_theme_axis_shadow(conn, _ROW))
    args = conn.execute.await_args.args
    assert conn.execute.await_count == 1, "the caller must still get its row"
    assert args[4] == "Robotics", "the unbounded read is unaffected by the diagnostic failing"
    assert args[17] is None and args[18] is None
    assert args[19] is None, "a failed read is NOT a recorded mismatch"


def test_the_insert_is_column_placeholder_and_arg_aligned():
    """Three lists must move together (columns, $N, bind args). A silent off-by-one here writes
    the wrong value into the wrong column, which no runtime error would reveal."""
    import io
    import re as _re
    src = io.open("agents/market_intelligence/theme_axis_shadow.py", encoding="utf-8").read()
    blk = src[src.index("INSERT INTO mi_theme_axis_shadow"):
              src.index("except Exception as _e:  # SHADOW")]
    cols = blk[blk.index("(") + 1:blk.index(") VALUES")]
    n_cols = len([c for c in cols.replace("\n", " ").split(",") if c.strip()])
    n_ph = len(_re.findall(r"\$\d+", blk[blk.index(") VALUES"):blk.index("ON CONFLICT")]))
    n_args = len([a for a in blk[blk.rindex('"""') + 3:].replace("\n", " ").split(",")
                  if a.strip()])
    assert n_cols == n_ph == n_args, f"cols={n_cols} placeholders={n_ph} args={n_args}"


# ─── #486 bounded-read backfill (2026-09-07 unblock) ───────────────────────────────────────
# 588 of 592 mi_theme_axis_shadow rows sat NULL on theme_name_7d/theme_stage_7d/
# bounded_matches_unbounded (instrumented 2026-09-03, forward-only). This backfills them
# from data already stored on every row. The load-bearing property under test: the as-of
# ANCHOR the backfill queries get_theme_heat_asof with must match the anchor the row's OWN
# theme_name was actually captured with — a same-day-write (live-scan) row could only ever
# see theme_date <= alert_date-1 (mi_themes' theme_date=alert_date row isn't written until
# the evening theme-engine run), while a later-day-write row (the #369 mass backfill) could
# see alert_date's own snapshot. Getting this wrong silently writes a DIFFERENT theme than
# what the live path actually saw — proven against prod on 2026-09-07 (ALAB, alert_date
# 2026-09-04: naive same-day form returns "AI data-center power buildout", the live-
# captured theme_name_7d is "Optical Networking & Photonics Components for AI Data
# Centers" — the prior-day form the tests below pin).

from agents.market_intelligence.theme_axis_shadow import (  # noqa: E402
    bounded_backfill_anchor,
    compute_bounded_backfill_read,
    compute_bounded_theme_match,
)


def test_bounded_backfill_anchor_same_day_write_steps_back_one_day():
    """MUTATION TARGET: bounded_backfill_anchor NOT subtracting a day (or using the wrong
    recency_days) for a same_day_write row flips this — that row's stored theme_name_7d
    was captured when alert_date's own mi_themes row did not exist yet (see module comment
    in theme_axis_shadow.py), so the backfill anchor must exclude it too."""
    anchor, recency = bounded_backfill_anchor(date(2026, 9, 4), True)
    assert anchor == date(2026, 9, 3)
    assert recency == 6


def test_bounded_backfill_anchor_non_same_day_write_keeps_alert_date():
    """MUTATION TARGET: subtracting a day here too flips this — the #369 mass-backfill
    population's stored theme_name WAS computed with alert_date's own snapshot visible
    (the backfill ran months after those alert_dates, once every historical theme_date row
    already existed), so re-anchoring at alert_date-1 would mismatch it."""
    anchor, recency = bounded_backfill_anchor(date(2026, 9, 4), False)
    assert anchor == date(2026, 9, 4)
    assert recency == 7


def _dual_snapshot_heat_fake(same_day_name="SameDayTheme", prior_day_name="PriorDayTheme"):
    """A theme whose 7d-bounded answer DIFFERS depending on whether the alert_date's own
    (same-calendar-day) mi_themes snapshot is visible to the query — models the real ALAB
    2026-09-04 case where a theme's cohort/attribution changed between D-1 and D."""
    async def _fake(_conn, ticker, query_date, recency_days=None):
        assert recency_days in (6, 7)
        if query_date == date(2026, 9, 4):
            return {"name": same_day_name, "stage": "Nascent", "score": 1.0,
                    "tickers": [ticker], "description": ""}
        return {"name": prior_day_name, "stage": "Accelerating", "score": 2.0,
                "tickers": [ticker], "description": ""}
    return _fake


def test_backfill_reproduces_the_live_writers_value_for_a_same_day_write_row(monkeypatch):
    """THE FIDELITY PROOF for a live-captured (same_day_write=True) row: the live writer's
    scan-time call could only ever see theme_date <= alert_date-1, so the backfill must
    reproduce "PriorDayTheme", never "SameDayTheme" — the value a naive alert_date-inclusive
    re-query would wrongly return now that alert_date's own snapshot exists.

    MUTATION TARGET: bounded_backfill_anchor returning `alert_date` unchanged for
    same_day_write=True flips theme_name_7d to "SameDayTheme" and `matches` to False."""
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof",
        _dual_snapshot_heat_fake())
    name_7d, stage_7d, matches = _run(compute_bounded_backfill_read(
        None, "ALAB", date(2026, 9, 4), True, "PriorDayTheme"))
    assert name_7d == "PriorDayTheme"
    assert stage_7d == "Accelerating"
    assert matches is True


def test_backfill_reproduces_the_mass_backfill_populations_value_for_a_later_write_row(
    monkeypatch,
):
    """Companion to the test above for the OTHER population (same_day_write=False, the
    #369 mass backfill): its stored theme_name WAS captured with alert_date's own snapshot
    visible, so the bounded backfill must reproduce "SameDayTheme" for these rows, not
    "PriorDayTheme".

    MUTATION TARGET: bounded_backfill_anchor subtracting a day for same_day_write=False
    flips theme_name_7d to "PriorDayTheme" and `matches` to False."""
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof",
        _dual_snapshot_heat_fake())
    name_7d, _, matches = _run(compute_bounded_backfill_read(
        None, "ALAB", date(2026, 9, 4), False, "SameDayTheme"))
    assert name_7d == "SameDayTheme"
    assert matches is True


def test_themeless_row_backfill_resolves_true_for_the_right_reason(monkeypatch):
    """A themeless row (stored theme_name=None) whose bounded read ALSO finds nothing must
    resolve `matches=True` — but for the right reason (both sides agree there's no theme),
    not vacuously. Proven by also checking the read finding SOMETHING resolves False.

    MUTATION TARGET: compute_bounded_theme_match hardcoded to `return True` would leave the
    first assertion green but flip the second (both-None vs found-something) assertion —
    proving the True above isn't vacuous."""
    async def _no_heat(_conn, ticker, query_date, recency_days=None):
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _no_heat)
    _, _, matches = _run(compute_bounded_backfill_read(
        None, "LONE", date(2026, 6, 1), True, None))
    assert matches is True

    async def _found_heat(_conn, ticker, query_date, recency_days=None):
        return {"name": "SomeTheme", "stage": "Nascent", "score": 1.0,
                "tickers": [ticker], "description": ""}
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _found_heat)
    _, _, matches2 = _run(compute_bounded_backfill_read(
        None, "LONE", date(2026, 6, 1), True, None))
    assert matches2 is False


def test_write_helper_sql_sets_the_backfilled_marker_and_idempotency_guard():
    """The marker + guard live in the SQL constant itself (registered in
    scripts/preflight_db_updates.py so a type-deduction bug can't hide silently — #606
    class). A reader must never mistake a backfilled value for a live-captured one.

    MUTATION TARGET: dropping `bounded_backfilled_at = NOW()` from the UPDATE removes the
    marker this column exists for; dropping the `AND bounded_matches_unbounded IS NULL`
    guard would let a re-run (or a race with a live write) clobber an already-captured
    row."""
    from agents.market_intelligence.db import THEME_AXIS_SHADOW_BOUNDED_BACKFILL_UPDATE_SQL as sql
    assert "bounded_backfilled_at = NOW()" in sql
    assert "WHERE id = $1 AND bounded_matches_unbounded IS NULL" in sql


def test_write_helper_returns_the_actual_update_count(monkeypatch):
    """MUTATION TARGET: hardcoding a return of 1 regardless of the UPDATE status string
    flips this — the guard clause can legitimately produce "UPDATE 0" (a row a live write
    raced ahead of the backfill), and the caller must be able to tell."""
    from agents.market_intelligence.db import write_theme_axis_shadow_bounded_backfill
    pool, conn = make_mock_pool()

    conn.execute = AsyncMock(return_value="UPDATE 1")
    n = _run(write_theme_axis_shadow_bounded_backfill(conn, 1, "X", "Nascent", True))
    assert n == 1

    conn.execute = AsyncMock(return_value="UPDATE 0")
    n2 = _run(write_theme_axis_shadow_bounded_backfill(conn, 1, "X", "Nascent", True))
    assert n2 == 0


def test_backfill_orchestrator_sums_writer_returned_count_not_a_blind_increment(monkeypatch):
    """MUTATION TARGET: `backfilled += 1` in backfill_bounded_theme_reads instead of
    `backfilled += n` flips this — a guard-blocked write (UPDATE 0) must not inflate the
    reported backfilled count."""
    from agents.market_intelligence.theme_axis_shadow import backfill_bounded_theme_reads
    pool, conn = make_mock_pool()

    targets = [
        {"id": 1, "ticker": "AAA", "alert_date": date(2026, 6, 1), "theme_name": None,
         "same_day_write": True},
        {"id": 2, "ticker": "BBB", "alert_date": date(2026, 6, 1), "theme_name": "Th",
         "same_day_write": True},
    ]

    async def _fake_targets(_conn):
        return targets
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow."
        "get_theme_axis_shadow_bounded_backfill_targets",
        _fake_targets,
    )

    async def _no_heat(_conn, ticker, query_date, recency_days=None):
        return None
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.get_theme_heat_asof", _no_heat)

    write_returns = [1, 0]  # first row writes; second simulates a guard-blocked race

    async def _fake_write(_conn, row_id, name_7d, stage_7d, matches):
        return write_returns.pop(0)
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.write_theme_axis_shadow_bounded_backfill",
        _fake_write,
    )

    result = _run(backfill_bounded_theme_reads(conn))
    assert result["candidates"] == 2
    assert result["backfilled"] == 1, "must reflect the guard block, not double-count"
    assert result["themed"] == 1 and result["themeless"] == 1


def test_backfill_targets_query_carries_the_real_idempotency_guard():
    """The actual idempotency mechanism lives in the SELECT's WHERE clause (a second run
    must find zero candidates), not in the orchestrator loop — this pins the real SQL text.

    MUTATION TARGET: dropping `WHERE bounded_matches_unbounded IS NULL` from
    db.get_theme_axis_shadow_bounded_backfill_targets's SELECT flips this red — a second
    run's SELECT would then return every row, live-captured or already-backfilled, and
    write_theme_axis_shadow_bounded_backfill's own guard is the only thing left stopping a
    clobber (belt, not suspenders)."""
    import inspect
    from agents.market_intelligence import db as db_module
    src = inspect.getsource(db_module.get_theme_axis_shadow_bounded_backfill_targets)
    assert "WHERE bounded_matches_unbounded IS NULL" in src


def test_backfill_orchestrator_reports_zero_everywhere_on_zero_candidates(monkeypatch):
    """Companion sanity check on the orchestrator itself: given zero targets (the real
    post-first-run state once the SELECT guard above excludes everything), the loop must
    run zero iterations — no writes, and every counter starts and stays at 0.

    MUTATION TARGET: seeding `backfilled`/`themed`/`themeless` from anything but a literal
    0 (e.g. `len(targets)` before the loop) would flip this even though nothing was
    actually read or written."""
    from agents.market_intelligence.theme_axis_shadow import backfill_bounded_theme_reads
    pool, conn = make_mock_pool()

    async def _empty_targets(_conn):
        return []
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow."
        "get_theme_axis_shadow_bounded_backfill_targets",
        _empty_targets,
    )
    write_mock = AsyncMock()
    monkeypatch.setattr(
        "agents.market_intelligence.theme_axis_shadow.write_theme_axis_shadow_bounded_backfill",
        write_mock,
    )

    result = _run(backfill_bounded_theme_reads(conn))
    assert result == {"candidates": 0, "backfilled": 0, "themed": 0, "themeless": 0}
    write_mock.assert_not_called()


def test_compute_bounded_theme_match_shared_by_writer_and_backfill():
    """The live writer (log_theme_axis_shadow) and the backfill (compute_bounded_backfill_
    read) both call compute_bounded_theme_match — never a locally re-derived `==`.

    MUTATION TARGET: either call site inlining its own comparison expression again (the
    pre-2026-09-07 shape) instead of calling the shared helper flips this string check."""
    import io
    src = io.open("agents/market_intelligence/theme_axis_shadow.py", encoding="utf-8").read()
    assert src.count("compute_bounded_theme_match(") >= 3, (
        "expected the def plus at least 2 call sites (writer + backfill)")
