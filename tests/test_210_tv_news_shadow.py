"""#210 TradingView news cross-reference SHADOW tests (2026-09-06).

Covers: the parser against a REAL captured payload (tests/fixtures/
tv_headlines_bfly_2026-09-06.json — a live fetch, never hand-written), the fail-open
path (a raised fetch exception, a schema-changed response, a malformed population
row), the degradation detector (classify_run_degradation's three thresholds), and
exchange-resolution skip (resolve_tv_symbol never guesses a prefix).

THE LINE: this module writes exactly one table (mi_tv_news_shadow) + mi_audit_log.
Nothing here touches a grade/score/admission/trade-state path — these tests exercise
that contract, not any live behavior change.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import tv_news_shadow as tv

_ET = ZoneInfo("America/New_York")
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tv_headlines_bfly_2026-09-06.json"


def _alert(ticker="BFLY", alert_date=date(2026, 6, 18), catalyst_quality="routine",
          has_direct_source=False, source_class_count=0):
    return {"ticker": ticker, "alert_date": alert_date, "catalyst_quality": catalyst_quality,
            "has_direct_source": has_direct_source, "source_class_count": source_class_count}


# ── parser against the REAL captured payload ─────────────────────────────────────────

def test_parser_against_real_captured_bfly_payload():
    """The fixture is a live fetch of
    https://news-headlines.tradingview.com/v2/headlines?client=overview&lang=en&symbol=NYSE:BFLY
    captured 2026-09-06 — never hand-written. Pins the exact counts the operator's
    own brief stated (25 items / 7 providers) so a future schema drift in the fixture
    (or in parse_tv_item's field assertions) is caught here, not in production."""
    payload = json.loads(FIXTURE_PATH.read_text())
    items, malformed = tv.parse_tv_response(payload)
    assert malformed == 0
    assert len(items) == 25
    from collections import Counter
    assert Counter(it["provider"] for it in items) == {
        "tradingview": 7, "dow-jones": 6, "business_wire": 4,
        "quartr": 3, "zacks": 2, "reuters": 2, "benzinga": 1,
    }
    assert all(isinstance(it["title"], str) and it["title"] for it in items)
    assert all(isinstance(it["published"], int) for it in items)
    # The most-recent item is the Merge Labs/Butterfly Midjourney-adjacent release —
    # confirms `published` really decodes to a sane, recent-looking unix timestamp.
    newest = max(it["published"] for it in items)
    assert tv.tv_item_et_datetime(newest).year == 2026


def test_a_present_but_empty_items_list_is_ok_not_a_schema_change():
    """Verified live 2026-09-06: an unresolved/invalid symbol returns HTTP 200 with
    literally {"items": []} — a legitimate outcome, not an error. malformed must be 0,
    never the -1 schema-change sentinel."""
    items, malformed = tv.parse_tv_response({"items": []})
    assert items == []
    assert malformed == 0


def test_a_missing_items_key_is_the_schema_change_sentinel():
    items, malformed = tv.parse_tv_response({"headlines": []})
    assert items == []
    assert malformed == -1


def test_items_not_a_list_is_also_the_schema_change_sentinel():
    items, malformed = tv.parse_tv_response({"items": "not-a-list"})
    assert malformed == -1


def test_a_non_dict_payload_is_the_schema_change_sentinel():
    items, malformed = tv.parse_tv_response(["unexpected", "array", "body"])
    assert malformed == -1


@pytest.mark.parametrize("bad_item", [
    {"provider": "reuters", "published": 123},                    # no title
    {"title": "  ", "provider": "reuters", "published": 123},     # blank title
    {"title": "X", "published": 123},                              # no provider
    {"title": "X", "provider": "reuters"},                         # no published
    {"title": "X", "provider": "reuters", "published": "not-a-number"},
    {"title": "X", "provider": "reuters", "published": True},      # bool masquerading as int
    "not-a-dict",
])
def test_malformed_items_are_counted_not_guessed(bad_item):
    items, malformed = tv.parse_tv_response({"items": [bad_item]})
    assert items == []
    assert malformed == 1


# ── normalize_title / is_same_day_item ────────────────────────────────────────────────

def test_normalize_title_collapses_punctuation_and_case():
    a = tv.normalize_title("Butterfly Network, Inc. Reports Q2 2026 Results!")
    b = tv.normalize_title("butterfly network inc reports q2 2026 results")
    assert a == b


def test_normalize_title_does_not_dedupe_across_providers_re_titling_the_same_story():
    """Documented upper-bound limitation, pinned: a Dow Jones wire-blurb and a
    Business Wire full headline for the SAME real release do not normalize to the
    same string — tv_items_we_missed can therefore over-count real misses."""
    dj = tv.normalize_title("Butterfly Network 2Q Rev $32.6M >BFLY")
    bw = tv.normalize_title("Butterfly Network Reports Second Quarter 2026 Financial Results")
    assert dj != bw


def test_same_day_item_matches_the_alert_date():
    et_dt = datetime(2026, 6, 18, 8, 5, tzinfo=_ET)
    assert tv.is_same_day_item(et_dt, date(2026, 6, 18), date(2026, 6, 17))


def test_same_day_item_matches_prior_day_after_close():
    et_dt = datetime(2026, 6, 17, 16, 30, tzinfo=_ET)
    assert tv.is_same_day_item(et_dt, date(2026, 6, 18), date(2026, 6, 17))


def test_same_day_item_rejects_prior_day_before_close():
    et_dt = datetime(2026, 6, 17, 12, 0, tzinfo=_ET)
    assert not tv.is_same_day_item(et_dt, date(2026, 6, 18), date(2026, 6, 17))


def test_same_day_item_rejects_an_unrelated_date():
    et_dt = datetime(2026, 8, 30, 8, 5, tzinfo=_ET)
    assert not tv.is_same_day_item(et_dt, date(2026, 6, 18), date(2026, 6, 17))


# ── exchange-resolution skip (never a hardcoded ticker map, never a guess) ───────────

def test_resolve_tv_symbol_builds_the_query_symbol_from_a_known_mic():
    symbol, reason = tv.resolve_tv_symbol("BFLY", "XNYS")
    assert symbol == "NYSE:BFLY"
    assert reason is None


def test_resolve_tv_symbol_skips_when_no_exchange_on_file():
    symbol, reason = tv.resolve_tv_symbol("ZZZZ", "")
    assert symbol is None
    assert reason == "no_exchange_on_file"


def test_resolve_tv_symbol_skips_an_unmapped_mic_rather_than_guessing():
    """XASE (NYSE American) is a real Polygon MIC not present in the shared
    friday_watchlist._TV_EXCHANGE_MAP — this must be a recorded skip, never a
    silent default (unlike agent.py's OWN display use of the same map, which
    defaults an unmapped MIC to 'NASDAQ' for a clickable chart link — wrong here,
    since a wrong exchange prefix silently queries a different company)."""
    symbol, reason = tv.resolve_tv_symbol("SPCE", "XASE")
    assert symbol is None
    assert reason == "mic_unmapped:XASE"


# ── build_shadow_row: the corpus comparison + the honesty guards ────────────────────

def test_skipped_exchange_row_still_never_touches_tv_fields():
    row = tv.build_shadow_row(_alert(), corpus=None, mic="", symbol=None,
                              skip_reason="no_exchange_on_file", fetch_result=None)
    assert row["tv_status"] == "skipped_exchange"
    assert row["tv_skip_reason"] == "no_exchange_on_file"
    assert row["tv_item_count"] is None
    assert row["our_corpus_available"] is False


def test_fetch_exception_becomes_a_fetch_error_row_never_raises():
    row = tv.build_shadow_row(_alert(), corpus=None, mic="XNYS", symbol="NYSE:BFLY",
                              skip_reason=None, fetch_result=(None, TimeoutError("dead")))
    assert row["tv_status"] == "fetch_error"
    assert "TimeoutError" in row["tv_skip_reason"]


def test_zero_items_is_ok_status_with_no_coverage_claim():
    row = tv.build_shadow_row(_alert(), corpus=None, mic="XNYS", symbol="NYSE:BFLY",
                              skip_reason=None, fetch_result=({"items": []}, None))
    assert row["tv_status"] == "ok"
    assert row["tv_item_count"] == 0
    assert row["tv_coverage_reaches_alert_date"] is False   # cannot confirm reach — see docstring


# The eleven shadow columns the #210 build added (db.py ALTER block). On a row with no corpus
# every one of them is NULL ("not computed"), never a zero.
_ELEVEN_NEW_COLS = (
    "our_captured_at", "our_corpus_source", "our_acting_grade", "our_acting_rule",
    "tv_coverage_reaches_period_start", "tv_unseen_minutes_at_period_start",
    "tv_items_before_grade", "tv_items_in_repoll_window", "tv_items_after_cutoff",
    "tv_match_summary", "tv_items_unmatched_seen",
)


def test_our_corpus_unavailable_records_same_day_items_without_a_diff():
    """The case with nothing stored to diff against (no grade-corpus row and no metrics row).
    tv_items_on_alert_date still answers "did TV have coverage"; tv_items_we_missed
    is None (nothing stored to diff against), never an empty list (which would
    falsely imply we checked and found zero misses) - and so is every one of the eleven
    #210 frame columns."""
    items = [{"title": "Butterfly Network Provides Commentary on Midjourney Medical",
              "provider": "business_wire",
              "published": int(datetime(2026, 6, 18, 8, 5, tzinfo=_ET).timestamp())}]
    row = tv.build_shadow_row(_alert(alert_date=date(2026, 6, 18)), corpus=None,
                              mic="XNYS", symbol="NYSE:BFLY", skip_reason=None,
                              fetch_result=({"items": items}, None))
    assert row["our_corpus_available"] is False
    assert row["tv_items_on_alert_date"] == 1
    assert row["tv_items_we_missed"] is None
    for col in _ELEVEN_NEW_COLS:
        assert row[col] is None, f"{col} must be NULL when no corpus exists, got {row[col]!r}"


def test_acting_grade_and_rule_are_carried_whether_or_not_a_corpus_exists():
    """They are properties of the ALERT (mi_ep_alerts.catalyst_quality, the lattice's rule_last),
    not of the diff - a corpus-less row keeps them so the second cut stays one WHERE clause."""
    alert = _alert(alert_date=date(2026, 6, 18)) | {
        "acting_grade": "strong", "acting_rule": "routine_promoted_demotion_corrective"}
    row = tv.build_shadow_row(alert, corpus=None, mic="XNYS", symbol="NYSE:BFLY",
                              skip_reason=None, fetch_result=({"items": []}, None))
    assert row["our_acting_grade"] == "strong"
    assert row["our_acting_rule"] == "routine_promoted_demotion_corrective"
    assert row["catalyst_quality"] == "routine"   # the RAW grade stays in its own column


def test_our_corpus_available_flags_the_item_we_never_held():
    """A window that REACHES the period start (a filler item before 16:00 ET on the prior
    trading day) and a grade captured at 07:01: the Midjourney release that arrived after the
    grade is the miss, in BOTH lists, tagged `none`. (The previous version of this test used a
    window whose oldest item was 08:05 on the alert date - under the corrected reach rule that
    window cannot speak for 16:00-08:05, so the DoD column is NULL there.)"""
    corpus = {
        "raw_polygon_news_json": [{"title": "Some unrelated AI/MedTech premarket mover piece"}],
        "raw_alpaca_news_json": [],
        "raw_fmp_news_json": None,
        "raw_perplexity_text": "narrative/momentum gap, no concrete catalyst",
        "captured_at": datetime(2026, 6, 18, 7, 1, tzinfo=_ET),
        "company_name": None, "polygon_available": True, "source": "grade_corpus",
    }
    ts_0805 = int(datetime(2026, 6, 18, 8, 5, tzinfo=_ET).timestamp())
    items = [
        {"title": "A filler piece from the middle of the prior session", "provider": "zacks",
         "published": int(datetime(2026, 6, 17, 12, 0, tzinfo=_ET).timestamp())},   # < 16:00 ET
        {"title": "Some Unrelated AI/MedTech Premarket Mover Piece",  # same story, re-cased -> matched
         "provider": "polygon_wire", "published": ts_0805},
        {"title": "Butterfly Network Provides Commentary on Midjourney Medical",
         "provider": "business_wire", "published": ts_0805},   # the actual miss
    ]
    row = tv.build_shadow_row(_alert(alert_date=date(2026, 6, 18)), corpus=corpus,
                              mic="XNYS", symbol="NYSE:BFLY", skip_reason=None,
                              fetch_result=({"items": items}, None))
    assert row["our_corpus_available"] is True
    assert row["our_polygon_count"] == 1
    assert row["our_perplexity_present"] is True
    assert row["tv_coverage_reaches_period_start"] is True
    missed_titles = [m["title"] for m in row["tv_items_we_missed"]]
    assert missed_titles == ["Butterfly Network Provides Commentary on Midjourney Medical"]
    assert [m["title"] for m in row["tv_items_unmatched_seen"]] == missed_titles
    assert all(m["match"] == "none" for m in row["tv_items_we_missed"])
    assert all(m["match"] == "none" for m in row["tv_items_unmatched_seen"])


def test_coverage_reaches_alert_date_false_when_window_has_rolled_past_it():
    """The endpoint's own verified shape: a rolling most-recent window with no date
    parameter. An oldest item newer than the alert date means the window cannot
    speak to that date at all — must not be read as "TV had nothing"."""
    items = [{"title": "Much later, unrelated news", "provider": "zacks",
              "published": int(datetime(2026, 8, 30, 12, 0, tzinfo=_ET).timestamp())}]
    row = tv.build_shadow_row(_alert(alert_date=date(2026, 6, 18)), corpus=None,
                              mic="XNYS", symbol="NYSE:BFLY", skip_reason=None,
                              fetch_result=({"items": items}, None))
    assert row["tv_coverage_reaches_alert_date"] is False
    assert row["tv_items_on_alert_date"] == 0


# ── the degradation detector ─────────────────────────────────────────────────────────

def test_a_single_stray_failure_among_successes_is_not_degradation():
    summary = {"fetches_ok": 9, "fetches_failed": 1, "unparseable": 0, "ok_item_counts": [10] * 9}
    assert tv.classify_run_degradation(summary, trailing_item_counts=[10] * 25) == []


def test_a_majority_failure_rate_is_flagged():
    summary = {"fetches_ok": 2, "fetches_failed": 3, "unparseable": 0, "ok_item_counts": [10, 12]}
    reasons = tv.classify_run_degradation(summary, trailing_item_counts=[])
    assert any("fetch_failure_rate" in r for r in reasons)


def test_any_unparseable_response_is_flagged_as_a_candidate_reason():
    """The shared canary's own 3-in-72h sustained requirement is what actually
    prevents a single garbled byte from paging — this function only decides whether
    THIS run is a candidate."""
    summary = {"fetches_ok": 5, "fetches_failed": 0, "unparseable": 1, "ok_item_counts": [10] * 5}
    reasons = tv.classify_run_degradation(summary, trailing_item_counts=[])
    assert any("unparseable_response" in r for r in reasons)


def test_item_count_collapse_needs_enough_trailing_history_first():
    """Cold-start guard: fewer than _TV_NORM_MIN_SAMPLES trailing rows must never
    trigger a collapse call, no matter how low today's count is."""
    summary = {"fetches_ok": 3, "fetches_failed": 0, "unparseable": 0, "ok_item_counts": [0, 0, 0]}
    thin_history = [25] * (tv._TV_NORM_MIN_SAMPLES - 1)
    assert tv.classify_run_degradation(summary, trailing_item_counts=thin_history) == []


def test_item_count_collapse_fires_once_history_is_sufficient():
    summary = {"fetches_ok": 3, "fetches_failed": 0, "unparseable": 0, "ok_item_counts": [0, 0, 0]}
    enough_history = [25] * tv._TV_NORM_MIN_SAMPLES
    reasons = tv.classify_run_degradation(summary, trailing_item_counts=enough_history)
    assert any("item_count_collapse" in r for r in reasons)


def test_a_mild_dip_within_the_collapse_ratio_does_not_fire():
    """Today's median at 50% of trailing (above the 30% _TV_COLLAPSE_RATIO floor)
    is ordinary night-to-night population churn, not a collapse."""
    summary = {"fetches_ok": 3, "fetches_failed": 0, "unparseable": 0, "ok_item_counts": [12, 13, 14]}
    enough_history = [25] * tv._TV_NORM_MIN_SAMPLES
    assert tv.classify_run_degradation(summary, trailing_item_counts=enough_history) == []


def test_a_run_where_every_candidate_is_skipped_is_flagged_not_silent():
    """THE QUIET-ZERO GAP: a night where every candidate is skipped for exchange
    resolution has zero failures, zero unparseable responses, and no item counts to
    collapse — classes 1-4 all stay silent. Without this explicit fifth check the
    run would report "healthy" while producing zero evidence, exactly what the
    operator's addendum said must not happen."""
    summary = {"population": 4, "fetches_ok": 0, "fetches_failed": 0, "unparseable": 0,
               "skipped_exchange": 4, "ok_item_counts": [],
               "exchange_skip_reasons": {"no_exchange_on_file": 3, "mic_unmapped:XASE": 1}}
    reasons = tv.classify_run_degradation(summary, trailing_item_counts=[])
    assert any("all_candidates_unresolved" in r for r in reasons)


def test_a_run_with_zero_population_is_not_flagged():
    """A quiet night with genuinely nothing to check (population == 0) is healthy,
    not degraded — the all_candidates_unresolved check requires population > 0."""
    summary = {"population": 0, "fetches_ok": 0, "fetches_failed": 0, "unparseable": 0,
               "skipped_exchange": 0, "ok_item_counts": [], "exchange_skip_reasons": {}}
    assert tv.classify_run_degradation(summary, trailing_item_counts=[]) == []


def test_a_run_with_at_least_one_attempted_fetch_is_not_flagged_by_this_check():
    summary = {"population": 5, "fetches_ok": 1, "fetches_failed": 0, "unparseable": 0,
               "skipped_exchange": 4, "ok_item_counts": [10],
               "exchange_skip_reasons": {"no_exchange_on_file": 4}}
    reasons = tv.classify_run_degradation(summary, trailing_item_counts=[])
    assert not any("all_candidates_unresolved" in r for r in reasons)


@pytest.mark.asyncio
async def test_exchange_skip_reasons_are_tallied_by_reason(monkeypatch):
    async def fake_corpus(ticker, alert_date):
        return None

    async def fake_fetch(symbol):
        return {"items": []}

    monkeypatch.setattr(tv, "get_grade_corpus", fake_corpus)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)

    population = [_alert(ticker="NOEXCH"), _alert(ticker="UNMAPPED"), _alert(ticker="GOOD")]
    exchange_map = {"NOEXCH": "", "UNMAPPED": "XASE", "GOOD": "XNAS"}
    rows, summary = await tv._run_over_population(population, exchange_map)

    assert summary["skipped_exchange"] == 2
    assert summary["exchange_skip_reasons"] == {
        "no_exchange_on_file": 1, "mic_unmapped:XASE": 1,
    }


@pytest.mark.asyncio
async def test_run_where_all_candidates_skip_exchange_fires_the_canary(monkeypatch):
    """End-to-end: a population that is ENTIRELY exchange-unresolvable must still
    reach the shared degradation canary — this is the exact gap the pure
    classify_run_degradation test above targets, exercised through the real
    orchestration path."""
    calls = []

    async def fake_population(since, today):
        return [_alert(ticker="NOEXCH", alert_date=today)]

    async def fake_exchange_map(tickers):
        return {}  # nothing on file for anyone this run

    async def fake_upsert(rows):
        return len(rows)

    async def fake_trailing(days, before):
        return []

    async def fake_audit(*a, **k):
        return None

    async def fake_shape_anomaly(provider, event_type, reason, detail=""):
        calls.append((provider, event_type, reason))

    monkeypatch.setattr(tv, "get_tv_shadow_population", fake_population)
    monkeypatch.setattr(tv, "get_security_exchange_map", fake_exchange_map)
    monkeypatch.setattr(tv, "upsert_tv_news_shadow_rows", fake_upsert)
    monkeypatch.setattr(tv, "get_tv_news_shadow_trailing_item_counts", fake_trailing)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)
    monkeypatch.setattr("agents.market_intelligence.llm_health.alert_endpoint_shape_anomaly",
                        fake_shape_anomaly)

    out = await tv.run_tv_news_shadow(date(2026, 9, 6))

    assert out["fetches_ok"] == 0 and out["fetches_failed"] == 0
    assert out["skipped_exchange"] == 1
    assert len(calls) == 1
    assert "all_candidates_unresolved" in calls[0][2]


# ── orchestration-level fail-open (monkeypatched I/O, no network/DB) ────────────────

@pytest.mark.asyncio
async def test_one_bad_fetch_never_kills_the_run(monkeypatch):
    async def fake_corpus(ticker, alert_date):
        return None

    async def fake_fetch(symbol):
        if symbol == "NASDAQ:BAD":
            raise RuntimeError("simulated dead endpoint")
        return {"items": []}

    monkeypatch.setattr(tv, "get_grade_corpus", fake_corpus)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)

    population = [_alert(ticker="BAD"), _alert(ticker="GOOD")]
    exchange_map = {"BAD": "XNAS", "GOOD": "XNAS"}
    rows, summary = await tv._run_over_population(population, exchange_map)

    statuses = {r["ticker"]: r["tv_status"] for r in rows}
    assert statuses == {"BAD": "fetch_error", "GOOD": "ok"}
    assert summary["fetches_failed"] == 1
    assert summary["fetches_ok"] == 1
    assert summary["errors"] == 0


@pytest.mark.asyncio
async def test_a_malformed_population_row_is_isolated_not_fatal(monkeypatch):
    """Belt-and-braces: even a code-bug-shaped input (a population row missing
    `ticker`) must not kill the run — this exercises _run_over_population's OWN
    per-ticker try/except, one layer outside snapshot_ticker's internal guards."""
    async def fake_corpus(ticker, alert_date):
        return None

    async def fake_fetch(symbol):
        return {"items": []}

    monkeypatch.setattr(tv, "get_grade_corpus", fake_corpus)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)

    population = [{"alert_date": date(2026, 9, 1)}, _alert(ticker="GOOD")]  # first has no "ticker"
    rows, summary = await tv._run_over_population(population, {"GOOD": "XNAS"})

    assert summary["errors"] == 1
    assert [r["ticker"] for r in rows] == ["GOOD"]


@pytest.mark.asyncio
async def test_degraded_run_fires_the_shared_shape_anomaly_canary_once(monkeypatch):
    """Every fetch failing this run must reach llm_health.alert_endpoint_shape_anomaly
    EXACTLY ONCE (not once per ticker) — the run-level, not per-fetch, contract the
    operator's addendum asked for."""
    calls = []

    async def fake_population(since, today):
        return [_alert(ticker="BAD1", alert_date=today), _alert(ticker="BAD2", alert_date=today)]

    async def fake_exchange_map(tickers):
        return {t: "XNYS" for t in tickers}

    async def fake_upsert(rows):
        return len(rows)

    async def fake_trailing(days, before):
        return []

    async def fake_audit(*a, **k):
        return None

    async def fake_fetch(symbol):
        raise TimeoutError("simulated dead endpoint")

    async def fake_corpus(ticker, alert_date):
        return None

    async def fake_shape_anomaly(provider, event_type, reason, detail=""):
        calls.append((provider, event_type, reason))

    monkeypatch.setattr(tv, "get_tv_shadow_population", fake_population)
    monkeypatch.setattr(tv, "get_security_exchange_map", fake_exchange_map)
    monkeypatch.setattr(tv, "upsert_tv_news_shadow_rows", fake_upsert)
    monkeypatch.setattr(tv, "get_tv_news_shadow_trailing_item_counts", fake_trailing)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)
    monkeypatch.setattr(tv, "get_grade_corpus", fake_corpus)
    monkeypatch.setattr("agents.market_intelligence.llm_health.alert_endpoint_shape_anomaly",
                        fake_shape_anomaly)

    out = await tv.run_tv_news_shadow(date(2026, 9, 6))

    assert out["fetches_failed"] == 2
    assert len(calls) == 1, f"expected exactly one canary call for the whole run, got {calls}"
    assert calls[0][0] == "tradingview"
    assert calls[0][1] == "tv_news_endpoint_error"


@pytest.mark.asyncio
async def test_a_healthy_run_never_calls_the_canary(monkeypatch):
    async def fake_population(since, today):
        return [_alert(ticker="GOOD", alert_date=today)]

    async def fake_exchange_map(tickers):
        return {t: "XNYS" for t in tickers}

    async def fake_upsert(rows):
        return len(rows)

    async def fake_trailing(days, before):
        return []

    async def fake_audit(*a, **k):
        return None

    async def fake_fetch(symbol):
        return {"items": []}

    async def fake_corpus(ticker, alert_date):
        return None

    calls = []

    async def fake_shape_anomaly(*a, **k):
        calls.append((a, k))

    monkeypatch.setattr(tv, "get_tv_shadow_population", fake_population)
    monkeypatch.setattr(tv, "get_security_exchange_map", fake_exchange_map)
    monkeypatch.setattr(tv, "upsert_tv_news_shadow_rows", fake_upsert)
    monkeypatch.setattr(tv, "get_tv_news_shadow_trailing_item_counts", fake_trailing)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)
    monkeypatch.setattr(tv, "get_grade_corpus", fake_corpus)
    monkeypatch.setattr("agents.market_intelligence.llm_health.alert_endpoint_shape_anomaly",
                        fake_shape_anomaly)

    out = await tv.run_tv_news_shadow(date(2026, 9, 6))
    assert out["fetches_ok"] == 1
    assert calls == []


@pytest.mark.asyncio
async def test_population_query_failure_degrades_to_an_empty_result_never_raises(monkeypatch):
    async def fake_population(since, today):
        raise ConnectionError("db unavailable")

    async def fake_audit(*a, **k):
        return None

    monkeypatch.setattr(tv, "get_tv_shadow_population", fake_population)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)

    out = await tv.run_tv_news_shadow(date(2026, 9, 6))
    assert out["errors"] == 1
    assert out["rows_written"] == 0


# ═════════════════════════════════════════════════════════════════════════════════════════
# #210 BUILD (2026-10-10) - the story matcher, the comparison frame, the grade corpus, the
# every-alert population and the 10:10 ET slot. Every case below loads the REAL captured
# fixture tests/fixtures/tv_shadow_210_cases_2026-10-10.json (a byte copy of
# scripts/probes/_wk1010_210/fixture_cases.json - never edited by hand) and asserts what
# scripts/probes/_wk1010_210/run_fixture_proof.py proved on the reference implementation.
# ═════════════════════════════════════════════════════════════════════════════════════════

FIXTURE_210 = Path(__file__).parent / "fixtures" / "tv_shadow_210_cases_2026-10-10.json"
_HELD = {"title", "story", "event", "move"}   # every verdict that means "a story we held"


def _fx() -> dict:
    return json.loads(FIXTURE_210.read_text(encoding="utf-8"))


def _iso_et(s):
    """ISO string from the fixture -> ET-aware datetime (None stays None: FMP carries no dates)."""
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_ET)


def _case_inputs(name: str):
    """(case, our_items, company, alert_date, prior_trading_day, captured_at) exactly as the
    reference proof builds them."""
    c = _fx()["cases"][name]
    our_items = []
    for src in ("polygon", "alpaca", "fmp"):
        for it in c["our_corpus"][src]:
            our_items.append({"title": it["title"], "published": _iso_et(it.get("published"))})
    alert_date = date.fromisoformat(c["alert_date"])
    prior, how = tv.prior_trading_day_holiday_aware(alert_date)
    assert how == "nyse_calendar"
    company = tv.company_tokens(None, c["ticker"], [o["title"] for o in our_items])
    return c, our_items, company, alert_date, prior, datetime.fromisoformat(c["our_captured_at"])


def _corpus_dict(c: dict) -> dict:
    """A db.get_grade_corpus-shaped dict rebuilt from the fixture's per-source items, in each
    source's REAL stored key (polygon published_utc, alpaca created_at, fmp undated)."""
    return {
        "raw_polygon_news_json": [{"title": i["title"], "published_utc": i.get("published")}
                                  for i in c["our_corpus"]["polygon"]],
        "raw_alpaca_news_json": [{"title": i["title"], "created_at": i.get("published")}
                                 for i in c["our_corpus"]["alpaca"]],
        "raw_fmp_news_json": [{"title": i["title"], "text": ""} for i in c["our_corpus"]["fmp"]],
        "raw_perplexity_text": "perplexity text" if c.get("our_perplexity_present") else None,
        "captured_at": datetime.fromisoformat(c["our_captured_at"]),
        "company_name": None, "polygon_available": True, "source": "grade_corpus",
    }


def _row_for_case(name: str) -> dict:
    c = _fx()["cases"][name]
    alert = _alert(ticker=c["ticker"], alert_date=date.fromisoformat(c["alert_date"]))
    return tv.build_shadow_row(alert, _corpus_dict(c), "XNYS", f"NYSE:{c['ticker']}", None,
                               ({"items": c["tv_items"]}, None))


def _pair_verdict(name: str, tv_title: str, our_title: str) -> str:
    c, our_items, company, alert_date, prior, _cap = _case_inputs(name)
    ours = next(o for o in our_items if o["title"] == our_title)
    return tv.match_tv_item(tv_title, [ours], alert_date=alert_date, prior_trading_day=prior,
                            company=company)[0]


def test_match_tv_item_is_importable_with_its_constants():
    """The Part 2 port: every name the card lists must exist in tv_news_shadow, so the matcher
    cannot be 'ported' by re-deriving it."""
    from agents.market_intelligence.tv_news_shadow import (  # noqa: F401
        CATALYST_CLASS_PATTERNS, CATALYST_CLASSES, CLASS_WORDS, COMMENTARY_STRONG_RE,
        COMMENTARY_WEAK_RE, GENERIC_WORDS, PREVIEW_RE, STOPWORDS, _ANALYST_VERBS, _CAP,
        _FIRM_HEAD_RE, _FIRM_TAIL_RE, _FY_RE, _PCT_RE, _UNIT, _USD_RE, _num, alpha_anchors,
        analyst_firm, build_frame, catalyst_classes, company_tokens, holds_a_catalyst,
        is_commentary, is_preview, match_tv_item, numeric_anchors, period_start, prior_weekday,
        prior_trading_day_holiday_aware, primary_class,
    )
    assert callable(match_tv_item) and callable(build_frame)


def test_acn_rolled_window_is_null_with_buckets():
    """ACN 2026-10-01: every TradingView item postdates our 07:10 capture, and the window's
    oldest item (09:31) is 1052 minutes after the period start - so the DoD column is NULL,
    never a list, while the one re-poll item reads as the results event we held."""
    row = _row_for_case("ACN")
    assert (row["tv_items_before_grade"], row["tv_items_in_repoll_window"],
            row["tv_items_after_cutoff"]) == (0, 1, 24)
    assert row["tv_coverage_reaches_period_start"] is False
    assert row["tv_unseen_minutes_at_period_start"] == 1052
    assert row["tv_items_we_missed"] is None
    assert row["tv_items_unmatched_seen"] == []
    assert row["tv_match_summary"]["repoll_window"] == {"event": 1}


def test_acn_results_summary_is_the_event_we_held():
    """The control for the preview test below: against the REAL ACN corpus (results wires
    present) the Reuters results summary is the earnings event we already held."""
    exp = _fx()["expected"]["ACN"]["control_must_match_as_event"]
    assert _pair_verdict("ACN", exp[0], exp[1]) == "event"


def test_peng_every_seen_item_is_a_story_we_held():
    """PENG 2026-10-07: the 18 items the window showed from before the cutoff are retitles or
    commentary on stories we held - so nothing is unmatched - and the window falls 7 minutes
    short of the period start, so the DoD column is NULL (a lower bound, not a zero)."""
    row = _row_for_case("PENG")
    assert (row["tv_items_before_grade"], row["tv_items_in_repoll_window"],
            row["tv_items_after_cutoff"]) == (17, 1, 7)
    assert row["tv_coverage_reaches_period_start"] is False
    assert row["tv_unseen_minutes_at_period_start"] == 7
    assert row["tv_items_we_missed"] is None
    assert row["tv_items_unmatched_seen"] == []
    summ = row["tv_match_summary"]
    seen = {**summ["before_grade"]}
    for v, n in summ["repoll_window"].items():
        seen[v] = seen.get(v, 0) + n
    assert sum(seen.values()) == 18
    assert set(seen) <= _HELD, f"a seen item did not read as held: {seen}"
    for tv_title, our_title in _fx()["expected"]["PENG"]["must_match_as_held"]:
        assert _pair_verdict("PENG", tv_title, our_title) in _HELD, tv_title


def test_same_target_different_firm_is_class_not_story():
    """Anchor-first: for an analyst note the anchor must be the FIRM. Rosenblatt $100 vs
    Stifel $85, and Needham $85 vs Stifel $85 (the same target from a different firm), are the
    same CLASS but not the same story."""
    for tv_title, our_title in _fx()["expected"]["PENG"]["must_match_as_class_not_story"]:
        assert _pair_verdict("PENG", tv_title, our_title) == "class"
    comp = {"penguin", "solutions", "peng"}
    v = tv.match_tv_item(
        "Needham maintains Buy rating on Penguin Solutions, $85 price target",
        [{"title": "Stifel Maintains Buy on Penguin Solutions, Raises Price Target to $85",
          "published": datetime(2026, 10, 7, 9, 25, tzinfo=_ET)}],
        alert_date=date(2026, 10, 7), prior_trading_day=date(2026, 10, 6), company=comp)[0]
    assert v == "class"


def test_preview_on_our_side_does_not_absorb_the_results():
    """ACN_PREVIEW (constructed): our only same-day earnings item is a PREVIEW, so TradingView's
    actual results summary is NOT the event we held - it stays visible as `class` in
    tv_items_unmatched_seen (the loose readout)."""
    exp = _fx()["expected"]["ACN_PREVIEW"]
    row = _row_for_case("ACN_PREVIEW")
    assert [i["title"] for i in row["tv_items_unmatched_seen"]] == exp["tv_items_unmatched_seen_titles"]
    assert all(i["match"] == "class" for i in row["tv_items_unmatched_seen"])
    assert row["tv_items_we_missed"] is None   # the window still does not reach the period start
    tv_title, our_title = exp["must_match_as_class_not_event"]
    assert _pair_verdict("ACN_PREVIEW", tv_title, our_title) == "class"


def test_bfly_unmatched_item_survives_in_the_repoll_bucket():
    """BFLY 2026-06-18: a window that REACHES the period start keeps its unmatched item in the
    DoD column - tagged with its bucket and verdict - and the filler we held matches by title."""
    exp = _fx()["expected"]["BFLY"]
    row = _row_for_case("BFLY")
    assert (row["tv_items_before_grade"], row["tv_items_in_repoll_window"],
            row["tv_items_after_cutoff"]) == (0, 1, 1)
    assert row["tv_coverage_reaches_period_start"] is True
    assert row["tv_unseen_minutes_at_period_start"] == 0
    missed = row["tv_items_we_missed"]
    assert [m["title"] for m in missed] == exp["tv_items_we_missed_titles"]
    assert all(m["bucket"] == "repoll_window" and m["match"] == "none" and m["class"] == "other"
               for m in missed)
    assert missed == row["tv_items_unmatched_seen"]
    listed = {m["title"] for m in missed} | {m["title"] for m in row["tv_items_unmatched_seen"]}
    assert not any("Stocktwits" in t or "Four-Year High" in t for t in listed)   # after the cutoff
    c, our_items, company, alert_date, prior, _cap = _case_inputs("BFLY")
    filler = c["tv_items"][0]["title"]
    assert tv.match_tv_item(filler, our_items, alert_date=alert_date, prior_trading_day=prior,
                            company=company)[0] == "title"


def test_period_start_is_the_prior_nyse_trading_day():
    """The Tuesday after Labor Day: the prior NYSE trading day is Friday 09-04. The weekend-only
    shared.dates.last_trading_day (the shadow's old rule) returned the closed Monday 09-07."""
    assert tv.prior_trading_day_holiday_aware(date(2026, 9, 8)) == (date(2026, 9, 4), "nyse_calendar")
    assert tv.period_start(date(2026, 9, 8), date(2026, 9, 4)) == datetime(2026, 9, 4, 16, 0, tzinfo=_ET)
    # and the same rule feeds the row: a Friday-after-16:00 item is same-day on Tuesday 09-08
    items = [{"title": "Held company filing", "provider": "zacks",
              "published": int(datetime(2026, 9, 4, 17, 0, tzinfo=_ET).timestamp())}]
    row = tv.build_shadow_row(_alert(alert_date=date(2026, 9, 8)), corpus=None, mic="XNYS",
                              symbol="NYSE:ERO", skip_reason=None,
                              fetch_result=({"items": items}, None))
    assert row["tv_items_on_alert_date"] == 1


@pytest.mark.asyncio
async def test_grade_corpus_write_is_fail_open(monkeypatch):
    """The scan-path write can never raise: a dead pool is a logged warning, not an exception."""
    from agents.market_intelligence import db as dbmod
    warnings = []

    async def dead_pool():
        raise ConnectionError("pool is down")

    monkeypatch.setattr(dbmod, "get_pool", dead_pool)
    monkeypatch.setattr(dbmod.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
    ok = await dbmod.write_grade_corpus(
        "ACN", date(2026, 10, 1), datetime(2026, 10, 1, 7, 0, tzinfo=_ET), "Accenture plc",
        [{"title": "x"}], [], "pplx text", "8-K filed 2026-10-01, items 2.02", "routine")
    assert ok is False
    assert len(warnings) == 1 and "ACN" in warnings[0] and "ConnectionError" in warnings[0]


@pytest.mark.asyncio
async def test_grade_corpus_write_binds_json_once_and_never_overwrites(monkeypatch):
    """The INSERT is DO NOTHING (the FIRST grade's corpus is the one the grade saw) and the two
    JSON params go in as Python lists for the jsonb codec to encode ONCE (the #216 class) -
    None stays NULL, never []."""
    from unittest.mock import AsyncMock, MagicMock
    from agents.market_intelligence import db as dbmod
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = lambda *a, **k: ctx
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    alpaca = [{"title": "PR", "created_at": "2026-10-01T10:00:00+00:00", "symbols": ["ACN"]}]
    ok = await dbmod.write_grade_corpus(
        "ACN", date(2026, 10, 1), datetime(2026, 10, 1, 7, 0, tzinfo=_ET), None,
        alpaca, None, None, None, "routine")
    assert ok is True
    sql, *args = conn.execute.await_args.args
    assert "ON CONFLICT (ticker, alert_date) DO NOTHING" in sql
    assert "$5::jsonb" in sql and "$6::jsonb" in sql
    assert args[4] == alpaca and isinstance(args[4], list)   # a list, not a json string
    assert args[5] is None                                    # None stays NULL


@pytest.mark.asyncio
async def test_population_is_every_alert_with_both_grades(monkeypatch):
    """Every mi_ep_alerts ticker-day comes back (no raw-grade predicate): the RAW grade from
    the provenance row (None where absent - the row is kept), the ACTING grade from the alert,
    and the lattice rule only where a lattice row exists. A 'strong' with a direct source - the
    row the old predicate dropped - is present."""
    from unittest.mock import AsyncMock, MagicMock
    from agents.market_intelligence import db as dbmod
    d = date(2026, 10, 5)
    alert_rows = [
        {"ticker": "NU", "alert_date": d, "acting_grade": "strong",
         "acting_rule": "routine_promoted_demotion_corrective"},
        {"ticker": "PENG", "alert_date": d, "acting_grade": "strong", "acting_rule": None},
        {"ticker": "NOPROV", "alert_date": d, "acting_grade": "strong", "acting_rule": None},
    ]
    prov_rows = [
        {"detail": json.dumps({"ticker": "NU", "alert_date": d.isoformat(),
                               "catalyst_quality": "routine", "sources": {"news": 2},
                               "has_direct_source": False})},
        {"detail": json.dumps({"ticker": "PENG", "alert_date": d.isoformat(),
                               "catalyst_quality": "strong", "sources": {"pr": 1, "sec": 1},
                               "has_direct_source": True})},
        {"detail": "not json at all"},   # malformed: skipped, never fatal
    ]
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[alert_rows, prov_rows])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = lambda *a, **k: ctx
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))

    out = await dbmod.get_tv_shadow_population(date(2026, 10, 3), d)

    by = {r["ticker"]: r for r in out}
    assert set(by) == {"NU", "PENG", "NOPROV"}   # 3 alerts in, 3 rows out - none dropped
    assert by["NU"]["catalyst_quality"] == "routine" and by["NU"]["has_direct_source"] is False
    assert by["PENG"]["catalyst_quality"] == "strong" and by["PENG"]["has_direct_source"] is True
    assert by["PENG"]["source_class_count"] == 2
    assert by["NOPROV"]["catalyst_quality"] is None            # no provenance row: kept, raw grade NULL
    assert by["NOPROV"]["has_direct_source"] is None
    assert [by[t]["acting_grade"] for t in ("NU", "PENG", "NOPROV")] == ["strong"] * 3
    assert by["NU"]["acting_rule"] == "routine_promoted_demotion_corrective"
    assert by["PENG"]["acting_rule"] is None and by["NOPROV"]["acting_rule"] is None


def test_shadow_job_is_registered_at_1010_et(monkeypatch):
    """The slot, EXERCISED not read: run start_scheduler against a capturing scheduler and ask
    the REGISTERED tv_news_shadow trigger when it fires next. 10:10 ET on trading weekdays (it
    was 20:45) - from a Friday-after-the-slot and from a Saturday the next fire is Monday
    10:10, and from Monday 09:00 it is Monday 10:10 the same morning."""
    import asyncio
    from agents.market_intelligence import scheduler as sched
    from tests.test_job_partition import _CapturingScheduler
    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    holder = {}
    real = sched._apply_role_partition

    def _spy(scheduler, role):
        holder["jobs"] = list(scheduler.get_jobs())
        return real(scheduler, role)

    monkeypatch.setattr(sched, "_apply_role_partition", _spy)

    async def _go():
        sched.start_scheduler()
    asyncio.run(_go())

    job = next((j for j in holder.get("jobs", []) if j.id == "tv_news_shadow"), None)
    assert job is not None, "tv_news_shadow is not registered at all"
    mon_1010 = datetime(2026, 10, 12, 10, 10, tzinfo=_ET)
    for now in (datetime(2026, 10, 9, 10, 11, tzinfo=_ET),    # Fri, just after the slot
                datetime(2026, 10, 10, 12, 0, tzinfo=_ET),    # Sat
                datetime(2026, 10, 12, 9, 0, tzinfo=_ET)):    # Mon, before the slot
        assert job.trigger.get_next_fire_time(None, now) == mon_1010, now


# ── beyond the card's eleven: the pieces the review found the fixture cannot reach ──────────
# (the fixture bypasses the stored-JSON path and the db readers entirely)

def test_each_stored_source_date_key_is_read_into_an_et_aware_datetime():
    """Polygon stores `published_utc` ('...Z'), Alpaca `created_at` (an ISO offset string), the
    FMP/yfinance wrapper stores NO date. If the key were wrong every item would read as undated
    (= same-day) and the frame would be silently wrong with every fixture test still green."""
    poly = tv._items_from_raw([{"title": "P", "published_utc": "2026-10-01T10:30:00Z"}],
                              tv._RAW_PUBLISHED_KEY["polygon"])
    alp = tv._items_from_raw([{"title": "A", "created_at": "2026-10-01T14:30:00+00:00"}],
                             tv._RAW_PUBLISHED_KEY["alpaca"])
    fmp = tv._items_from_raw([{"title": "F", "text": "x"}], tv._RAW_PUBLISHED_KEY["fmp"])
    assert poly[0]["published"] == datetime(2026, 10, 1, 6, 30, tzinfo=_ET)
    assert alp[0]["published"] == datetime(2026, 10, 1, 10, 30, tzinfo=_ET)
    assert poly[0]["published"].utcoffset() is not None
    assert fmp[0]["published"] is None
    # shape surprises degrade to skipped / undated, never raise
    assert tv._items_from_raw(None, "published_utc") == []
    assert tv._items_from_raw('[{"title": "J", "published_utc": "not a date"}]',
                              "published_utc") == [{"title": "J", "published": None}]
    assert tv._items_from_raw([{"title": "  "}, "junk", {"nope": 1}], "published_utc") == []


def test_a_grade_corpus_row_has_no_polygon_count_not_zero():
    """A grade-corpus row has no Polygon side (Polygon is fetched only inside
    extract_earnings_metrics). Its Polygon count is NULL, never 0 - a 0 reads as 'Polygon was
    checked and held nothing'. The total counts only what was captured."""
    c = _fx()["cases"]["BFLY"]
    corpus = _corpus_dict(c) | {"polygon_available": False, "raw_polygon_news_json": None,
                                "source": "grade_corpus"}
    alert = _alert(ticker="BFLY", alert_date=date(2026, 6, 18))
    row = tv.build_shadow_row(alert, corpus, "XNYS", "NYSE:BFLY", None,
                              ({"items": c["tv_items"]}, None))
    assert row["our_polygon_count"] is None
    assert row["our_alpaca_count"] == len(c["our_corpus"]["alpaca"])
    assert row["our_fmp_count"] == len(c["our_corpus"]["fmp"])
    assert row["our_total_item_count"] == row["our_alpaca_count"] + row["our_fmp_count"]
    assert row["our_corpus_source"] == "grade_corpus"
    assert row["our_captured_at"] == corpus["captured_at"]


def test_a_metrics_only_corpus_keeps_its_polygon_count_and_says_so():
    c = _fx()["cases"]["BFLY"]
    corpus = _corpus_dict(c) | {"polygon_available": True, "source": "metrics"}
    row = tv.build_shadow_row(_alert(ticker="BFLY", alert_date=date(2026, 6, 18)), corpus,
                              "XNYS", "NYSE:BFLY", None, ({"items": c["tv_items"]}, None))
    assert row["our_polygon_count"] == len(c["our_corpus"]["polygon"])
    assert row["our_corpus_source"] == "metrics"


def test_a_corpus_without_a_capture_time_leaves_the_frame_null_and_warns(monkeypatch):
    """Cannot happen through get_grade_corpus (both sources carry a timestamp), but if a corpus
    ever arrives without one the frame must be NULL - never bucketed against 'now' or zero."""
    warnings = []
    monkeypatch.setattr(tv.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
    c = _fx()["cases"]["BFLY"]
    corpus = _corpus_dict(c) | {"captured_at": None}
    row = tv.build_shadow_row(_alert(ticker="BFLY", alert_date=date(2026, 6, 18)), corpus,
                              "XNYS", "NYSE:BFLY", None, ({"items": c["tv_items"]}, None))
    assert row["our_corpus_available"] is True
    for col in ("our_captured_at", "tv_coverage_reaches_period_start", "tv_items_before_grade",
                "tv_match_summary", "tv_items_unmatched_seen", "tv_items_we_missed"):
        assert row[col] is None, col
    assert any("captured_at" in w for w in warnings)


def test_bucket_counts_sum_to_the_same_day_count_on_every_fixture_case():
    """The WOULD-FAIL-IF invariant, on all four captured windows: the three buckets and the
    match summary each account for exactly tv_items_on_alert_date."""
    for name in ("ACN", "ACN_PREVIEW", "PENG", "BFLY"):
        row = _row_for_case(name)
        n = row["tv_items_on_alert_date"]
        assert (row["tv_items_before_grade"] + row["tv_items_in_repoll_window"]
                + row["tv_items_after_cutoff"]) == n, name
        assert sum(sum(d.values()) for d in row["tv_match_summary"].values()) == n, name
        # a [] in the DoD column may only ever sit on a window that reaches the period start
        if row["tv_items_we_missed"] is not None:
            assert row["tv_coverage_reaches_period_start"] is True, name


@pytest.mark.asyncio
async def test_get_grade_corpus_prefers_the_grade_row_and_falls_back_to_metrics(monkeypatch):
    """source='grade_corpus' (captured_at = the grade time) when that row exists, with Polygon
    taken from the metrics row if there is one; source='metrics' (captured_at = extracted_at)
    when only the metrics row exists; None when neither does."""
    from unittest.mock import AsyncMock, MagicMock
    from agents.market_intelligence import db as dbmod
    t_grade = datetime(2026, 10, 1, 7, 0, 20, tzinfo=_ET)
    t_extract = datetime(2026, 10, 1, 7, 10, 15, tzinfo=_ET)
    gc = {"captured_at": t_grade, "company_name": "Accenture plc",
          "alpaca_json": [{"title": "A"}], "fmp_json": [], "perplexity_text": "p"}
    mm = {"raw_polygon_news_json": [{"title": "P"}], "raw_alpaca_news_json": [{"title": "OTHER"}],
          "raw_fmp_news_json": None, "raw_perplexity_text": "q", "extracted_at": t_extract}

    async def run(gc_row, mm_row):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[gc_row, mm_row])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.acquire = lambda *a, **k: ctx
        monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
        return await dbmod.get_grade_corpus("ACN", date(2026, 10, 1))

    both = await run(gc, mm)
    assert both["source"] == "grade_corpus" and both["captured_at"] == t_grade
    assert both["company_name"] == "Accenture plc"
    assert both["raw_alpaca_news_json"] == [{"title": "A"}]       # the corpus the GRADE saw
    assert both["raw_polygon_news_json"] == [{"title": "P"}] and both["polygon_available"] is True

    grade_only = await run(gc, None)
    assert grade_only["source"] == "grade_corpus" and grade_only["polygon_available"] is False
    assert grade_only["raw_polygon_news_json"] is None

    metrics_only = await run(None, mm)
    assert metrics_only["source"] == "metrics" and metrics_only["captured_at"] == t_extract
    assert metrics_only["polygon_available"] is True and metrics_only["company_name"] is None
    assert metrics_only["raw_alpaca_news_json"] == [{"title": "OTHER"}]

    assert await run(None, None) is None


def test_the_scan_path_write_sits_in_its_own_except_exception_after_the_provenance_row():
    """THE LINE, structurally: the write_grade_corpus call in ep_detector's uncached grade branch
    must (a) sit inside its own try whose handler catches Exception and does not re-raise, and
    (b) come AFTER the ep_catalyst_provenance audit call (so a failure cannot reorder or skip
    it) and BEFORE the enrichment shadow. Telemetry that can raise into the scan is a defect."""
    # source-pin-ok: wiring check - the call sits in `_grade_admitted`, a ~2,000-line closure nested
    # inside run_ep_scan with no independently callable seam around the uncached grade branch (it
    # needs a live LLM grade, six data feeds and the DB to run); the write's own fail-open behaviour
    # is exercised for real in test_grade_corpus_write_is_fail_open. What only the source can say is
    # that the call site is wrapped, sits after the provenance audit row, and that every name the
    # call uses RESOLVES there - a NameError would be swallowed by the very except that makes the
    # write fail-open, leaving the table silently empty.
    import ast
    import symtable
    src = (Path(__file__).resolve().parent.parent / "agents" / "market_intelligence"
           / "ep_detector.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def is_call(node, fn_name):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == fn_name)

    writes = [n for n in ast.walk(tree) if is_call(n, "write_grade_corpus")]
    assert len(writes) == 1, "exactly one write_grade_corpus call site in ep_detector"
    w = writes[0]
    p = parents[w]
    while not isinstance(p, ast.Try):
        p = parents[p]   # an unwrapped call would reach the function def and KeyError here
    assert any(isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in p.handlers)
    assert not any(isinstance(n, ast.Raise) for h in p.handlers for n in ast.walk(h))
    prov_line = next(n.lineno for n in ast.walk(tree) if is_call(n, "log_audit_event")
                     and n.args and isinstance(n.args[0], ast.Constant)
                     and n.args[0].value == "ep_catalyst_provenance")
    enrich_line = next(n.lineno for n in ast.walk(tree) if is_call(n, "log_audit_event")
                       and n.args and isinstance(n.args[0], ast.Constant)
                       and n.args[0].value == "ep_grade_enrich_shadow")
    assert prov_line < w.lineno < enrich_line

    # every name in the call resolves at the write site: `_ET` is a FREE variable bound by
    # run_ep_scan's own `from ... import _ET` (a function-local import, so a module-level move of
    # `_grade_admitted` would turn it into an undefined global), `datetime`/`write_grade_corpus`
    # are module-level imports.
    fn = w
    while not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        fn = parents[fn]
    top = symtable.symtable(src, "ep_detector.py", "exec")

    def find(tab, name):
        for ch in tab.get_children():
            if ch.get_name() == name and ch.get_type() == "function" and ch.get_lineno() == fn.lineno:
                return ch
            hit = find(ch, name)
            if hit is not None:
                return hit
        return None

    tab = find(top, fn.name)
    assert tab is not None, f"could not locate {fn.name} in the symbol table"
    assert tab.lookup("_ET").is_free(), "_ET is not a closure variable at the write site"
    assert tab.lookup("datetime").is_global() and tab.lookup("write_grade_corpus").is_global()
    for name in ("profile", "alpaca_news", "fmp_news", "perplexity_answer", "sec_filing",
                 "catalyst_quality", "ticker"):
        assert tab.lookup(name).is_local(), f"{name} is not bound in the grade function"
    assert tab.lookup("today").is_free(), "today is not a closure variable at the write site"
