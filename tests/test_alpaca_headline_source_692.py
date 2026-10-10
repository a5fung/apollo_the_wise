"""#692 (2026-10-10) — the headline deal scan ALSO reads Benzinga via Alpaca news.

Why: Polygon's news feed stopped carrying Benzinga between 06-17 and 06-23 (88 Benzinga articles
on 05-14, 72 on 06-17, 0 on 06-23 and every sampled day since — scripts/probes/_1006/
polygon_benzinga_check.py). `ma_filter.headline_deal_scan` read ONLY Polygon, so the flag / coil /
low-cap boards and the EP path's second deal source went blind to Benzinga deal headlines. His yes
2026-10-06: read `collector.get_alpaca_news` (the source the EP grader already reads, $0 extra)
alongside Polygon.

What these pin:
  1. The Alpaca item is reshaped onto the Polygon shape and the candidate rule is the SAME $0
     keyword rule (title keyword; a summary keyword only when the article is about this ticker).
  2. The same headline from both feeds is asked ONCE and tagged Polygon.
  3. Every nomination / release / unanswered row carries its source (`news_source`), and an
     Alpaca-sourced HIT reads `source = alpaca_headline_model` beside Polygon's.
  4. The decision rule is untouched: the same fake answers give the same BLOCK/PASS from either feed.
  5. A dead / slow / empty Alpaca read changes NOTHING (today's Polygon-only behaviour); a toggle
     turns the source off with no redeploy.
"""
from __future__ import annotations

import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from agents.market_intelligence import ma_filter as mf

_REPO = Path(__file__).resolve().parents[1]
_ET = ZoneInfo("America/New_York")
_T0 = datetime(2026, 10, 1, 11, 0, tzinfo=_ET)


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "mna_harness_692_alpaca", _REPO / "scripts" / "probes" / "_284_mna_acquirer_backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load_harness()


def _run(coro):
    return asyncio.run(coro)


def _alp(title, *, summary="", symbols=("ACME",), created="2026-10-01T10:00:00+00:00",
         source="benzinga"):
    """An item in `collector.get_alpaca_news`'s raw output shape."""
    return {"title": title, "summary": summary, "content": "", "author": "", "source": source,
            "url": "", "symbols": list(symbols), "created_at": created}


def _poly(title, *, description="", published="2026-10-01T10:00:00Z", insights=None,
          publisher="GlobeNewswire Inc."):
    return {"title": title, "description": description, "published_utc": published,
            "publisher": publisher, "tickers": ["ACME"], "insights": insights or []}


def _case(*, polygon=(), alpaca=(), answers=None, grader=None, alpaca_on=True, company="Acme Corp"):
    case = H.Case("ACME", "2026-10-01", "synthetic", False, "headline", "PASS",
                  grader=grader, articles=tuple(polygon), alpaca_articles=tuple(alpaca),
                  headline=tuple((answers or {}).items()), company=company)
    return _run(H.run_new(case, alpaca_on=alpaca_on))


def _scan(polygon=(), alpaca=(), answers=None, *, alpaca_effect=None, enabled=True):
    """headline_deal_scan itself (not is_likely_ma), so the released / unanswered lists are visible."""
    model = H.FakeModel("ACME", dict(answers or {}))
    alp = (AsyncMock(side_effect=alpaca_effect) if alpaca_effect is not None
           else AsyncMock(return_value=[dict(a) for a in alpaca]))
    audits: list = []

    async def _raw_audit(event_type, summary, detail=None):
        audits.append((event_type, summary, detail))
    mf.reset_headline_day()
    mf._COMPANY_NAME_MEMO.clear()
    with patch("agents.market_intelligence.collector.get_polygon_news",
               new=AsyncMock(return_value=[dict(p) for p in polygon])), \
         patch("agents.market_intelligence.collector.get_alpaca_news", new=alp), \
         patch.object(mf, "_alpaca_source_enabled", new=AsyncMock(return_value=enabled), create=True), \
         patch("agents.market_intelligence.collector.get_ticker_details",
               new=AsyncMock(return_value={"name": "Acme Corp"})), \
         patch.object(mf, "_get_headline_client", return_value=model), \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
               new=AsyncMock(return_value=None)), \
         patch("agents.market_intelligence.db.log_audit_event", new=_raw_audit):
        scan = _run(mf.headline_deal_scan("ACME", now_et=_T0))
    return scan, model, alp, audits


_TARGET = H.Ans("target", "signed", "cash", "BigCo")
_NONE = H.Ans("none", "none", "none")


# ── 1. an Alpaca-only deal headline nominates, and says where it came from ─────────────────────

def test_alpaca_only_buyout_headline_blocks_and_is_tagged_alpaca():
    title = "Acme Corp Agrees To Be Acquired By BigCo For $20 Per Share In All-Cash Deal"
    out = _case(alpaca=[_alp(title)], answers={title: _TARGET})
    assert out.blocked is True
    assert out.meta["source"] == "alpaca_headline_model"
    assert out.meta["news_source"] == "alpaca"
    assert out.meta["publisher"] == "benzinga" and out.meta["match_path"] == "title"


def test_polygon_only_headline_is_still_tagged_polygon():
    title = "Acme Corp enters definitive agreement to be acquired by BigCo"
    out = _case(polygon=[_poly(title)], answers={title: _TARGET})
    assert out.blocked is True
    assert out.meta["source"] == "polygon_headline_model" and out.meta["news_source"] == "polygon"


def test_the_decision_rule_is_the_same_from_either_feed():
    """Every fake answer gives the SAME verdict whichever feed carried the headline."""
    title = "Acme Corp tender offer launched by BigCo"
    for ans, expect in ((_TARGET, True), (H.Ans("target", "signed", "stock"), False),
                        (H.Ans("buyer", "signed", "cash"), False),
                        (H.Ans("target", "speculation", "none"), False), (_NONE, False)):
        mf.reset_headline_day()
        via_poly = _case(polygon=[_poly(title)], answers={title: ans}).blocked
        via_alp = _case(alpaca=[_alp(title)], answers={title: ans}).blocked
        assert via_poly == via_alp == expect, ans


# ── 2. the same headline from both feeds is asked once ────────────────────────────────────────

def test_the_same_headline_in_both_feeds_is_asked_once_and_tagged_polygon():
    t_poly = "Acme Corp to be Acquired by BigCo for $20 Cash"
    t_alp = "  ACME Corp to be acquired by BigCo for $20 cash  "     # case + whitespace differ
    out = _case(polygon=[_poly(t_poly, published="2026-10-01T09:58:00Z")],
                alpaca=[_alp(t_alp, created="2026-10-01T10:01:00+00:00")],
                answers={t_poly: _TARGET, t_alp.strip(): _TARGET})
    assert len(out.calls) == 1, out.calls
    assert out.blocked is True and out.meta["source"] == "polygon_headline_model"
    assert out.meta["news_sources"] == ["polygon", "alpaca"]


def test_dedupe_is_on_the_headline_only_not_a_fuzzy_match():
    a = "Acme Corp receives takeover approach from BigCo"
    b = "Acme Corp receives takeover approach from OtherCo"
    scan, model, _alp_mock, _ = _scan(polygon=[_poly(a)], alpaca=[_alp(b)],
                                      answers={a: _NONE, b: _NONE})
    assert sorted(model.calls) == sorted([a, b]) and scan.candidates_n == 2


# ── 3. candidate rule for Alpaca items (no per-ticker insights) ───────────────────────────────

def test_alpaca_summary_keyword_on_a_single_symbol_article_is_a_candidate():
    title = "Acme Corp Announces Transaction"
    scan, model, _, _ = _scan(alpaca=[_alp(title, summary="Acme will be a going private deal at $9",
                                           symbols=("ACME",))], answers={title: _NONE})
    assert scan.candidates_n == 1 and [r["match_path"] for r in scan.released] == ["description+symbols"]
    assert scan.released[0]["news_source"] == "alpaca"


def test_alpaca_summary_keyword_on_a_multi_symbol_roundup_is_not_a_candidate_and_not_missing_insights():
    title = "Sector Wrap: Who Is Buying Whom This Week"
    scan, model, _, audits = _scan(alpaca=[_alp(title, summary="a merger was announced",
                                                symbols=("ACME", "OTHR", "THIRD"))])
    assert scan.candidates_n == 0 and model.calls == []
    assert [a for a in audits if a[0] == "polygon_news_insights_missing"] == []


def test_alpaca_summary_keyword_multi_symbol_but_title_names_the_company_is_a_candidate():
    title = "Acme Corp, BigCo Said To Weigh Combination"
    scan, model, _, _ = _scan(alpaca=[_alp(title, summary="a merger of equals is discussed",
                                           symbols=("ACME", "BIGC"))], answers={title: _NONE})
    assert scan.candidates_n == 1


def test_litigation_notice_titles_from_alpaca_are_skipped_like_polygon():
    title = "Halper Sadeh LLC Investigates ACME's Merger"
    scan, model, _, _ = _scan(alpaca=[_alp(title)])
    assert scan.candidates_n == 0 and model.calls == []


# ── 4. rows carry the source ──────────────────────────────────────────────────────────────────

def test_released_and_unanswered_rows_carry_news_source():
    rel = "Acme Corp rejects takeover bid from BigCo"
    una = "Acme Corp exploring buyout options, sources say"
    scan, model, _, _ = _scan(
        polygon=[_poly(rel, published="2026-10-01T08:00:00Z")], alpaca=[_alp(una)],
        answers={rel: _NONE})        # `una` has no fixture → the fake raises → unanswered
    assert [(r["title"], r["news_source"]) for r in scan.released] == [(rel, "polygon")]
    assert [(u["title"], u["news_source"]) for u in scan.unanswered] == [(una, "alpaca")]


def test_alpaca_timestamp_is_reshaped_to_the_polygon_format_so_the_newest_first_order_holds():
    old_p = "Acme Corp buyout rumour (polygon, older)"
    new_a = "Acme Corp buyout deal signed (alpaca, newer)"
    items = mf._alpaca_to_scan_items([_alp(new_a, created="2026-10-01T10:00:00+00:00")], "ACME")
    assert items[0]["published_utc"] == "2026-10-01T10:00:00Z" and items[0]["news_source"] == "alpaca"
    assert items[0]["description"] == "" and items[0]["insights"] == []
    merged = mf._merge_headline_sources([_poly(old_p, published="2026-10-01T09:00:00Z")], items)
    got = mf._candidate_articles("ACME", merged, company_name="Acme Corp")
    assert [c[0]["title"] for c in got] == [new_a, old_p]


# ── 5. safe to be wrong: a dead feed changes nothing; a toggle turns it off ────────────────────

def test_a_failing_alpaca_read_gives_exactly_the_polygon_only_result():
    title = "Acme Corp to be acquired by BigCo for cash"
    base, *_ = _scan(polygon=[_poly(title)], answers={title: _TARGET})
    for effect in (RuntimeError("boom"), asyncio.TimeoutError()):
        scan, *_ = _scan(polygon=[_poly(title)], answers={title: _TARGET}, alpaca_effect=effect)
        assert scan.hit == base.hit and scan.released == base.released
        assert scan.unanswered == base.unanswered


def test_a_hung_alpaca_read_is_cut_at_the_deadline_and_polygon_still_answers():
    title = "Acme Corp to be acquired by BigCo for cash"

    async def _hang(*a, **k):
        await asyncio.sleep(30)
    import time
    start = time.monotonic()
    with patch.object(mf, "_ALPACA_FETCH_TIMEOUT_S", 0.2, create=True):
        scan, *_ = _scan(polygon=[_poly(title)], answers={title: _TARGET}, alpaca_effect=_hang)
    assert time.monotonic() - start < 5 and scan.hit and scan.hit["title"] == title


def test_the_toggle_off_never_calls_alpaca():
    title = "Acme Corp to be acquired by BigCo for cash"
    scan, model, alp, _ = _scan(alpaca=[_alp(title)], answers={title: _TARGET}, enabled=False)
    assert scan.hit is None and scan.candidates_n == 0
    alp.assert_not_called()


def test_the_alpaca_toggle_ships_on_his_yes_2026_10_06():
    with patch("agents.market_intelligence.db.get_runtime_toggle",
               new=AsyncMock(side_effect=lambda name, env, default=True: default)):
        assert _run(mf._alpaca_source_enabled()) is True


def test_alpaca_is_asked_for_the_same_window_the_polygon_read_uses():
    title = "Acme Corp buyout talk"
    scan, model, alp, _ = _scan(alpaca=[_alp(title)], answers={title: _NONE})
    kw = alp.call_args.kwargs
    assert alp.call_args.args == ("ACME",)
    assert kw["lookback_days"] == 14 and kw["limit"] == 20 and kw["include_content"] is False


# ── 6. the second feed can only ADD questions, never displace a Polygon one ───────────────────
# (found by the 10-10 replay: 1 of 22 ticker-days (PYPL 07-28) whose Polygon-era answers included an
#  acting headline would have lost it out of a shared 3-newest cap to newer Alpaca candidates)

def test_added_alpaca_candidates_never_push_a_polygon_candidate_out_of_the_cap():
    poly = [_poly(f"Acme Corp buyout news P{i}", published=f"2026-09-0{i}T10:00:00Z") for i in (1, 2, 3)]
    alp = [_alp(f"Acme Corp takeover report A{i}", created=f"2026-09-2{i}T10:00:00+00:00") for i in (1, 2)]
    answers = {p["title"]: _NONE for p in poly} | {a["title"]: _NONE for a in alp}
    scan, model, _, _ = _scan(polygon=poly, alpaca=alp, answers=answers)
    assert sorted(model.calls) == sorted(answers)            # all 3 Polygon + both Alpaca asked
    assert scan.unanswered == [] and scan.candidates_n == 5


def test_each_feed_is_capped_at_three_and_the_rest_are_recorded_unanswered():
    poly = [_poly(f"Acme Corp buyout news P{i}", published=f"2026-09-0{i}T10:00:00Z") for i in range(1, 6)]
    alp = [_alp(f"Acme Corp takeover report A{i}", created=f"2026-09-2{i}T10:00:00+00:00") for i in range(1, 6)]
    answers = {p["title"]: _NONE for p in poly} | {a["title"]: _NONE for a in alp}
    scan, model, _, _ = _scan(polygon=poly, alpaca=alp, answers=answers)
    assert len(model.calls) == 6
    assert sorted(u["title"] for u in scan.unanswered) == [
        "Acme Corp buyout news P1", "Acme Corp buyout news P2",
        "Acme Corp takeover report A1", "Acme Corp takeover report A2"]
    assert {u["why"] for u in scan.unanswered} == {"article_cap"}


def test_a_polygon_nomination_survives_five_newer_alpaca_candidates():
    old = "Acme Corp to be acquired by BigCo for $20 cash"
    poly = [_poly(old, published="2026-09-01T10:00:00Z")]
    alp = [_alp(f"Acme Corp takeover chatter A{i}", created=f"2026-09-2{i}T10:00:00+00:00") for i in range(1, 6)]
    answers = {old: _TARGET} | {a["title"]: _NONE for a in alp}
    scan, *_ = _scan(polygon=poly, alpaca=alp, answers=answers)
    assert scan.hit is not None and scan.hit["title"] == old and scan.hit["source"] == "polygon_headline_model"
