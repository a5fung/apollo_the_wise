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


def test_our_corpus_unavailable_records_same_day_items_without_a_diff():
    """The common case: mi_ep_catalyst_metrics has no row for this routine/no-direct-
    source alert (populated only on the earnings-path branch — see module docstring).
    tv_items_on_alert_date still answers "did TV have coverage"; tv_items_we_missed
    is None (nothing stored to diff against), never an empty list (which would
    falsely imply we checked and found zero misses)."""
    items = [{"title": "Butterfly Network Provides Commentary on Midjourney Medical",
              "provider": "business_wire",
              "published": int(datetime(2026, 6, 18, 8, 5, tzinfo=_ET).timestamp())}]
    row = tv.build_shadow_row(_alert(alert_date=date(2026, 6, 18)), corpus=None,
                              mic="XNYS", symbol="NYSE:BFLY", skip_reason=None,
                              fetch_result=({"items": items}, None))
    assert row["our_corpus_available"] is False
    assert row["tv_items_on_alert_date"] == 1
    assert row["tv_items_we_missed"] is None


def test_our_corpus_available_flags_the_item_we_never_held():
    corpus = {
        "raw_polygon_news_json": [{"title": "Some unrelated AI/MedTech premarket mover piece"}],
        "raw_alpaca_news_json": [],
        "raw_fmp_news_json": None,
        "raw_perplexity_text": "narrative/momentum gap, no concrete catalyst",
    }
    midjourney_ts = int(datetime(2026, 6, 18, 8, 5, tzinfo=_ET).timestamp())
    items = [
        {"title": "Some Unrelated AI/MedTech Premarket Mover Piece",  # same story, re-cased -> matched
         "provider": "polygon_wire", "published": midjourney_ts},
        {"title": "Butterfly Network Provides Commentary on Midjourney Medical",
         "provider": "business_wire", "published": midjourney_ts},   # the actual miss
    ]
    row = tv.build_shadow_row(_alert(alert_date=date(2026, 6, 18)), corpus=corpus,
                              mic="XNYS", symbol="NYSE:BFLY", skip_reason=None,
                              fetch_result=({"items": items}, None))
    assert row["our_corpus_available"] is True
    assert row["our_polygon_count"] == 1
    assert row["our_perplexity_present"] is True
    missed_titles = [m["title"] for m in row["tv_items_we_missed"]]
    assert missed_titles == ["Butterfly Network Provides Commentary on Midjourney Medical"]


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

    monkeypatch.setattr(tv, "get_catalyst_metrics_raw_corpus", fake_corpus)
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

    monkeypatch.setattr(tv, "get_no_catalyst_alert_population", fake_population)
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

    monkeypatch.setattr(tv, "get_catalyst_metrics_raw_corpus", fake_corpus)
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

    monkeypatch.setattr(tv, "get_catalyst_metrics_raw_corpus", fake_corpus)
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

    monkeypatch.setattr(tv, "get_no_catalyst_alert_population", fake_population)
    monkeypatch.setattr(tv, "get_security_exchange_map", fake_exchange_map)
    monkeypatch.setattr(tv, "upsert_tv_news_shadow_rows", fake_upsert)
    monkeypatch.setattr(tv, "get_tv_news_shadow_trailing_item_counts", fake_trailing)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)
    monkeypatch.setattr(tv, "get_catalyst_metrics_raw_corpus", fake_corpus)
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

    monkeypatch.setattr(tv, "get_no_catalyst_alert_population", fake_population)
    monkeypatch.setattr(tv, "get_security_exchange_map", fake_exchange_map)
    monkeypatch.setattr(tv, "upsert_tv_news_shadow_rows", fake_upsert)
    monkeypatch.setattr(tv, "get_tv_news_shadow_trailing_item_counts", fake_trailing)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)
    monkeypatch.setattr(tv, "_fetch_tv_headlines", fake_fetch)
    monkeypatch.setattr(tv, "get_catalyst_metrics_raw_corpus", fake_corpus)
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

    monkeypatch.setattr(tv, "get_no_catalyst_alert_population", fake_population)
    monkeypatch.setattr(tv, "log_audit_event", fake_audit)

    out = await tv.run_tv_news_shadow(date(2026, 9, 6))
    assert out["errors"] == 1
    assert out["rows_written"] == 0
