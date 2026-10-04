"""#692 — the M&A filter asks ONE question: is THIS ticker the target of a signed deal that fixes
its price? (2026-10-02, built, NOT deployed — awaiting the paid replay + operator sign-off.)

Three rounds of phrase-matching guards (#416 A/B/C 07-12, #516 D 08-08) did not lower the error
rate: on 2026-10-01 he ruled 10 of 11 September blocks wrong. These tests pin:

  1. THE RULE — `deal_pins_price`, the one function that decides (pure).
  2. EVERY OPERATOR-LABELLED CASE as a named regression (the table lives in the DoD's home,
     scripts/probes/_284_mna_acquirer_backtest.py, so the harness and the suite read ONE list).
     The ten 10-01 releases each BLOCKED on origin/main's `is_likely_ma` with the same inputs —
     verified with the harness's `--old-module` arm against `git show origin/main:...` (the
     table is in the #692 commit message); SUNE / CLRO / ACVA block on both.
  3. The headline question's plumbing — candidate selection, memo, daily cap, ORB-window skip,
     per-article retry bound, the UNANSWERED toggle, the conflict / released / grade audits.
  4. The schemas — verdict fields before the one free-text field; no reason-first wording.

⚠ The deal answers in the case table are EXPECTED answers, not recorded model output — the
replay produces the real ones. Green here proves the rule and the plumbing, not the model.
"""
from __future__ import annotations

import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import ma_filter as mf
from agents.market_intelligence.ma_filter import DealAnswer, deal_pins_price

_REPO = Path(__file__).resolve().parents[1]
_ET = ZoneInfo("America/New_York")


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "mna_harness_692", _REPO / "scripts" / "probes" / "_284_mna_acquirer_backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load_harness()


def _run(coro):
    return asyncio.run(coro)


# ── 1. THE RULE ───────────────────────────────────────────────────────────────────────────────

def test_rule_signed_cash_target_blocks_ACVA():
    assert deal_pins_price(DealAnswer("target", "signed", "cash", "Copart")) is True


def test_rule_all_stock_target_passes_CSR():
    """The discriminating case for 'fixes its price': an all-stock merger floats with the
    acquirer's shares (CSR 09-09, ruled wrongly blocked)."""
    assert deal_pins_price(DealAnswer("target", "signed", "stock")) is False


def test_rule_mixed_and_unknown_consideration_block():
    """Operator decisions 2 + 3 (recommended): a stated cash component pins; unstated terms on a
    signed target default to pinned."""
    assert deal_pins_price(DealAnswer("target", "signed", "mixed")) is True
    assert deal_pins_price(DealAnswer("target", "signed", "unknown")) is True
    assert deal_pins_price(DealAnswer("target", "signed", "none")) is False


def test_rule_signed_shell_blocks_CLRO_SUNE():
    """Operator decision 1: the shell arm is what keeps his two TP rulings — CLRO reads
    shell/signed/STOCK and must still block, unlike CSR."""
    assert deal_pins_price(DealAnswer("shell", "signed", "stock")) is True
    assert deal_pins_price(DealAnswer("shell", "proposed", "stock")) is False


def test_rule_a_buyer_never_blocks():
    for status in mf.DEAL_STATUSES:
        for cons in mf.DEAL_CONSIDERATIONS:
            assert deal_pins_price(DealAnswer("buyer", status, cons)) is False


def test_rule_nothing_but_signed_blocks():
    for status in ("proposed", "speculation", "completed", "none"):
        for role in mf.DEAL_ROLES:
            for cons in mf.DEAL_CONSIDERATIONS:
                assert deal_pins_price(DealAnswer(role, status, cons)) is False, (role, status, cons)


def test_rule_unanswered_is_not_a_block():
    assert deal_pins_price(None) is False


def test_rule_the_full_truth_table_has_exactly_the_pinning_cells():
    pins = {(r, s, c) for r in mf.DEAL_ROLES for s in mf.DEAL_STATUSES for c in mf.DEAL_CONSIDERATIONS
            if deal_pins_price(DealAnswer(r, s, c))}
    expected = ({("target", "signed", c) for c in ("cash", "mixed", "unknown")}
                | {("shell", "signed", c) for c in mf.DEAL_CONSIDERATIONS})
    assert pins == expected


def test_parse_rejects_out_of_vocabulary_answers():
    ok = mf.deal_answer_from_fields({"deal_role": "Target", "deal_status": "SIGNED",
                                     "deal_consideration": "cash", "deal_counterparty": "X",
                                     "note": "agreed to be acquired"}, note_key="note")
    assert ok == DealAnswer("target", "signed", "cash", "X", "agreed to be acquired")
    assert mf.deal_answer_from_fields({"deal_role": "acquirer", "deal_status": "signed",
                                       "deal_consideration": "cash"}) is None
    assert mf.deal_answer_from_fields({"deal_role": "target"}) is None
    assert mf.deal_answer_from_fields(None) is None


# ── 2. THE NAMED REGRESSION CASES (operator-labelled) ─────────────────────────────────────────

def _assert_case(ticker: str):
    case = H.CASES_BY_TICKER[ticker]
    assert case.ground_truth, f"{ticker} is not an operator-labelled case"
    out = _run(H.run_new(case))
    assert not out.unplanned, f"{ticker}: asked about an article with no fixture: {out.unplanned}"
    got = "BLOCK" if out.blocked else "PASS"
    assert got == case.expected, f"{ticker} {case.day}: expected {case.expected}, got {got} ({case.label})"
    return out


# the ten the operator ruled WRONGLY BLOCKED on 2026-10-01 — every one blocked on origin/main
def test_FWDI_2026_09_18_the_bidder_is_released():
    out = _assert_case("FWDI")
    released = [a for a in out.audits if a[0] == "mna_filter_released"]
    assert released and "grade_mna" in released[0][2]["old_reasons"]


def test_CHYM_2026_09_09_buyer_of_stride_bank_is_released():
    _assert_case("CHYM")


def test_JBS_2026_09_18_buyer_of_pilgrims_minority_is_released():
    _assert_case("JBS")


def test_GPRK_2026_09_03_no_deal_is_released():
    _assert_case("GPRK")


def test_IOVA_2026_09_29_potential_targets_list_is_released():
    out = _assert_case("IOVA")
    assert out.calls == [H._IOVA_VKTX_TITLE], "the headline question was not asked"


def test_RGTI_2026_09_08_a_funding_definitive_agreement_is_released():
    _assert_case("RGTI")


def test_VKTX_2026_09_22_speculation_is_released():
    _assert_case("VKTX")


def test_WAY_2026_09_15_exploring_a_sale_is_released():
    _assert_case("WAY")


def test_CSR_2026_09_09_all_stock_merger_is_released():
    _assert_case("CSR")


def test_SWKS_2026_09_15_buyer_of_qorvo_is_released():
    _assert_case("SWKS")


# the real targets that MUST stay blocked
def test_ACVA_2026_09_11_signed_cash_target_stays_blocked():
    out = _assert_case("ACVA")
    assert out.meta["source"] == "claude_deal_fields"
    assert (out.meta["role"], out.meta["status"], out.meta["consideration"]) == ("target", "signed", "cash")
    assert out.calls == [], "a pinning grader answer must not spend a headline question"


def test_SUNE_2026_06_08_reverse_merger_shell_stays_blocked():
    out = _assert_case("SUNE")
    assert out.meta["source"] == "polygon_headline_model" and out.meta["role"] == "shell"
    assert out.meta["match_path"] == "description+insights"


def test_CLRO_2026_07_02_reverse_merger_shell_stays_blocked():
    out = _assert_case("CLRO")
    assert out.meta["source"] == "polygon_headline_model" and out.meta["match_path"] == "title"


# the earlier rounds' false positives stay released
@pytest.mark.parametrize("ticker", ["MMED", "FRMI", "ONDS", "IMAX", "WEN", "UMAC", "LCID",
                                    "SOUN", "LII", "SCZM"])
def test_earlier_rounds_false_positives_stay_released(ticker):
    _assert_case(ticker)


def test_every_operator_labelled_case_is_named_here():
    """A labelled case added to the table without a test here would be checked only by the
    harness run — keep the two in step."""
    named = {"FWDI", "CHYM", "JBS", "GPRK", "IOVA", "RGTI", "VKTX", "WAY", "CSR", "SWKS",
             "ACVA", "SUNE", "CLRO", "MMED", "FRMI", "ONDS", "IMAX", "WEN", "UMAC", "LCID",
             "SOUN", "LII", "SCZM",
             # his 2026-10-03 sign-off (tests/test_mna_pin_check_692.py names each)
             "PD", "DSGN", "THR", "HZO", "RNW",
             # his 2026-10-03 ruling 4 ("Go with rec") + ruling 3's seven price-only catches
             "NUVL", "IRDM", "TMHC", "APGE", "SAFT", "FBRX", "VREX", "ARX", "WEAV"}
    assert {c.ticker for c in H.CASES if c.ground_truth} == named


@pytest.mark.parametrize("ticker", ["CECO", "ROKU", "QBTS", "KALV", "MGM", "ATAI"])
def test_agent_read_plumbing_cases_behave_as_designed(ticker):
    """NOT ground truth — the design's expected behaviour on plumbing shapes: the buyer side of
    the THR title (CECO); a target headline the old regex read as acquirer, kept blocked by the
    day window (ROKU); a roundup bleed never asked (QBTS); a litigation notice never asked
    (KALV); the approved 10-02 release the price agrees with by 0.24pp (MGM); the closest free
    >= 20% gapper to the price-only line (ATAI)."""
    case = H.CASES_BY_TICKER[ticker]
    out = _run(H.run_new(case))
    assert ("BLOCK" if out.blocked else "PASS") == case.expected and not out.unplanned


def test_QBTS_bleed_and_KALV_litigation_cost_no_model_call():
    for t in ("QBTS", "KALV"):
        assert _run(H.run_new(H.CASES_BY_TICKER[t])).calls == []


# ── 3. HEADLINE-QUESTION PLUMBING ─────────────────────────────────────────────────────────────

_T0 = datetime(2026, 10, 2, 8, 0, tzinfo=_ET)


def _fresh():
    mf.reset_headline_day()


def _fake(answer=("none", "none", "none"), *, fail=False):
    calls = []

    async def create(**kw):
        calls.append(kw)
        if fail:
            raise RuntimeError("boom")
        block = SimpleNamespace(type="tool_use", input={
            "deal_role": answer[0], "deal_status": answer[1], "deal_consideration": answer[2],
            "deal_counterparty": "", "note": "n"})
        return SimpleNamespace(content=[block], stop_reason="tool_use")
    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


_ITEM = {"title": "Acme to be acquired by BigCo in all-cash buyout", "description": "",
         "insights": [], "published_utc": "2026-10-01T12:00:00Z", "publisher": "p"}


def _ask(client, item=_ITEM, now=_T0, **kw):
    with patch.object(mf, "_get_headline_client", return_value=client), \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
               new=AsyncMock(return_value=None)):
        return _run(mf.ask_deal_question("ACME", item, company_name="Acme", now_et=now, **kw))


def test_question_is_memoized_per_article_per_day():
    _fresh()
    client, calls = _fake(("target", "signed", "cash"))
    a1, how1 = _ask(client)
    a2, how2 = _ask(client)
    assert (how1, how2) == ("answered", "memo") and a1 == a2 and len(calls) == 1


def test_memo_resets_on_a_new_ET_day():
    _fresh()
    client, calls = _fake()
    _ask(client)
    _ask(client, now=datetime(2026, 10, 3, 8, 0, tzinfo=_ET))
    assert len(calls) == 2


def _cap_audits():
    """Capture the raw `mna_headline_cap_hit` writes (DB dedup forced to 'first today')."""
    rows = []

    async def _log(event_type, summary, detail=""):
        rows.append((event_type, summary))
    return rows, patch.object(mf, "_first_today", new=AsyncMock(return_value=True)), \
        patch("agents.market_intelligence.db.log_audit_event", new=_log)


def test_the_daily_budget_is_400_with_an_EP_reserve_of_100():
    """Fix round: 40 was never measured; the EP scan (money path) keeps a reserve no shadow lane
    can spend."""
    assert mf._HEADLINE_QUESTION_CALLS_CAP == 400 and mf._HEADLINE_EP_RESERVE == 100
    assert mf._budget_cap("ep") == 400 and mf._budget_cap("shared") == 300


def test_a_shared_caller_stops_at_the_EP_reserve_and_the_EP_scan_does_not():
    _fresh()
    rows, p1, p2 = _cap_audits()
    with p1, p2:
        mf._HEADLINE_DAY.update({"day": _T0.date(), "calls": mf._budget_cap("shared")})
        client, calls = _fake()
        ans, how = _ask(client)                      # default pool = shared
        assert ans is None and how == "daily_cap" and calls == []
        ans, how = _ask(client, budget_pool="ep")    # the reserve is still there for EP
        assert how == "answered" and len(calls) == 1
    assert [r[0] for r in rows] == ["mna_headline_cap_hit"] and rows[0][1].startswith("shared: ")


def test_the_EP_pool_stops_at_the_full_budget_and_logs_once_per_day():
    _fresh()
    rows, p1, p2 = _cap_audits()
    with p1, p2:
        mf._HEADLINE_DAY.update({"day": _T0.date(), "calls": mf._HEADLINE_QUESTION_CALLS_CAP})
        client, calls = _fake()
        for _ in range(3):
            assert _ask(client, item={**_ITEM, "title": f"t{_}"}, budget_pool="ep") == (None, "daily_cap")
    assert calls == [] and [r[0] for r in rows] == ["mna_headline_cap_hit"]
    assert rows[0][1].startswith("ep: ")


def test_a_cap_hit_question_is_unanswered_and_passes_audited():
    """Ruling 4 covers the budget: the name passes and the row says why."""
    items = [{"title": "Acme buyout talk", "description": "", "insights": [],
              "published_utc": "2026-10-01T10:00:00Z"}]
    case = H.Case("ACME", "2026-10-01", "synthetic", False, "headline", "PASS", articles=tuple(items),
                  headline=((items[0]["title"], H.Ans("target", "signed", "cash")),))
    rows, p1, p2 = _cap_audits()
    real_reset = mf.reset_headline_day

    def _reset_then_spend():
        real_reset()
        mf._HEADLINE_DAY.update({"day": H._OUTSIDE_ORB.date(), "calls": mf._budget_cap("shared")})
    with p1, patch.object(mf, "reset_headline_day", new=_reset_then_spend):
        out = _run(H.run_new(case))
    assert out.blocked is False and out.calls == []
    ev = [a for a in out.audits if a[0] == "mna_headline_unanswered"]
    assert ev and ev[0][2]["unanswered"][0]["why"] == "daily_cap" and ev[0][2]["blocked"] is False


def test_orb_window_skips_the_call_only_when_the_caller_opts_in():
    """The EP scan opts in (`skip_in_orb=True`); the low-cap lane, flag and anticipation are
    asked inside 9:30-9:45 like any other minute (reviewer: the lane's only catalyst check went
    dark there)."""
    _fresh()
    client, calls = _fake()
    ans, how = _ask(client, now=datetime(2026, 10, 2, 9, 35, tzinfo=_ET), skip_in_orb=True)
    assert ans is None and how == "orb_window" and calls == []
    _fresh()
    ans, how = _ask(client, now=datetime(2026, 10, 2, 9, 35, tzinfo=_ET))
    assert how == "answered" and len(calls) == 1


def test_a_call_whose_timeout_would_cross_930_counts_as_in_window():
    _fresh()
    client, calls = _fake()
    at = datetime(2026, 10, 2, 9, 29, 50, tzinfo=_ET)
    assert _ask(client, now=at, skip_in_orb=True) == (None, "orb_window") and calls == []
    _fresh()
    early = datetime(2026, 10, 2, 9, 29, 0, tzinfo=_ET)    # 9:29:00 + 20 s < 9:30
    assert _ask(client, now=early, skip_in_orb=True)[1] == "answered"
    _fresh()
    assert _ask(client, now=at)[1] == "answered"          # not opted in → asked


def test_a_failing_article_is_retried_at_most_twice_a_day():
    _fresh()
    client, calls = _fake(fail=True)
    hows = [_ask(client)[1] for _ in range(4)]
    assert hows == ["error:RuntimeError", "error:RuntimeError", "gave_up", "gave_up"]
    assert len(calls) == mf._HEADLINE_MAX_ATTEMPTS_PER_ARTICLE


def test_truncated_and_invalid_answers_are_unanswered():
    _fresh()

    async def trunc(**kw):
        return SimpleNamespace(content=[], stop_reason="max_tokens")
    assert _ask(SimpleNamespace(messages=SimpleNamespace(create=trunc)))[1] == "truncated"
    _fresh()
    client, _ = _fake(("acquirer", "signed", "cash"))
    assert _ask(client) == (None, "invalid")


def test_the_question_is_a_forced_tool_on_the_graders_tier():
    _fresh()
    client, calls = _fake()
    _ask(client)
    kw = calls[0]
    from shared.llm_models import GROUNDED_GRADE_MODEL
    from shared.output_ceilings import max_tokens_for
    assert kw["model"] == GROUNDED_GRADE_MODEL
    assert kw["max_tokens"] == max_tokens_for("mna_headline_question")
    assert kw["tool_choice"] == {"type": "tool", "name": "classify_deal_headline"}
    assert "Ticker: ACME (Acme)" in kw["messages"][0]["content"]


def _items_case(articles, *, grader=None, company=None, unanswered_blocks=False, answers=None,
                quality=None, texts=None):
    """A synthetic case through the harness. An article with no entry in `answers` makes the
    fake model raise — i.e. the question goes UNANSWERED."""
    case = H.Case("ACME", "2026-10-01", "synthetic", False, "headline", "PASS",
                  catalyst_quality=quality, catalyst_texts=tuple(texts or ()),
                  grader=grader, articles=tuple(articles),
                  headline=tuple((answers or {}).items()), company=company)
    return _run(H.run_new(case, unanswered_blocks=unanswered_blocks))


def test_candidates_need_this_ticker_in_insights_unless_the_title_matches():
    items = [
        {"title": "Sector roundup", "description": "a merger elsewhere", "insights": [
            {"ticker": "OTHER", "sentiment_reasoning": "OTHER's merger"}],
         "published_utc": "2026-10-01T10:00:00Z"},
        {"title": "Quiet day", "description": "no keyword", "insights": [],
         "published_utc": "2026-10-01T11:00:00Z"},
    ]
    assert mf._candidate_articles("ACME", items) == []
    items[0]["insights"].append({"ticker": "ACME", "sentiment_reasoning": "rallied"})
    got = mf._candidate_articles("ACME", items)
    assert [(c[1], c[2]) for c in got] == [("description+insights", "merger")]


def test_an_ungraded_article_is_skipped_and_still_counted():
    """Polygon had not AI-graded the article (no insights): never asked, and the #88
    `polygon_news_insights_missing` row the monthly _b88 check counts is still written."""
    items = [{"title": "Sector wrap", "description": "a merger was announced", "insights": [],
              "published_utc": "2026-10-01T10:00:00Z"}]
    out = _items_case(items)
    assert out.blocked is False and out.calls == []
    assert [a[0] for a in out.audits] == ["polygon_news_insights_missing"]


def test_candidates_are_asked_newest_first_and_at_most_three():
    items = [{"title": f"Takeover chatter {i}", "description": "", "insights": [],
              "published_utc": f"2026-10-0{i}T10:00:00Z"} for i in range(1, 6)]
    answers = {f"Takeover chatter {i}": H.Ans("target", "speculation", "none") for i in range(1, 6)}
    out = _items_case(items, answers=answers)
    assert out.calls == ["Takeover chatter 5", "Takeover chatter 4", "Takeover chatter 3"]
    assert out.blocked is False
    # the two older candidates are recorded UNANSWERED (article_cap), never dropped silently
    ev = [a for a in out.audits if a[0] == "mna_headline_unanswered"]
    assert ev and ev[0][2]["blocked"] is False and ev[0][2]["unanswered_n"] == 2
    assert [u["why"] for u in ev[0][2]["unanswered"]] == ["article_cap", "article_cap"]
    assert [u["title"] for u in ev[0][2]["unanswered"]] == ["Takeover chatter 2", "Takeover chatter 1"]


def test_a_pin_in_an_older_asked_article_still_blocks_with_the_newest_pin_as_the_hit():
    """The ≤3 articles are asked at once; the verdict is the same as asking in order."""
    items = [{"title": f"Takeover news {i}", "description": "", "insights": [],
              "published_utc": f"2026-10-0{i}T10:00:00Z"} for i in range(1, 4)]
    answers = {"Takeover news 3": H.Ans("target", "speculation", "none"),
               "Takeover news 2": H.Ans("target", "signed", "cash", "BigCo"),
               "Takeover news 1": H.Ans("target", "signed", "cash", "BigCo")}
    out = _items_case(items, answers=answers)
    assert out.blocked is True and out.meta["title"] == "Takeover news 2"
    assert sorted(out.calls) == sorted(answers)


def test_the_articles_are_asked_concurrently_under_one_deadline():
    """A hung ask is cut at the scan's deadline and recorded UNANSWERED ('deadline'); the
    answers that landed are kept."""
    items = [{"title": f"Takeover item {i}", "description": "", "insights": [],
              "published_utc": f"2026-10-0{i}T10:00:00Z"} for i in range(1, 3)]

    class _Slow(H.FakeModel):
        async def _create(self, **kw):
            title = next(ln[7:] for ln in kw["messages"][0]["content"].splitlines()
                         if ln.startswith("Title: "))
            if title == "Takeover item 2":
                await asyncio.sleep(5)
            return await super()._create(**kw)
    model = _Slow("ACME", {f"Takeover item {i}": H.Ans("none", "none", "none") for i in (1, 2)})
    model.messages = SimpleNamespace(create=model._create)
    audits = []

    async def _cap(event_type, ticker, summary, detail):
        audits.append((event_type, detail))
    with patch.object(mf, "_HEADLINE_TIMEOUT_S", 0.2), \
         patch("agents.market_intelligence.collector.get_polygon_news", new=AsyncMock(return_value=items)), \
         patch("agents.market_intelligence.collector.get_ticker_details", new=AsyncMock(return_value={})), \
         patch.object(mf, "_get_headline_client", return_value=model), \
         patch.object(mf, "_audit_once", new=_cap), \
         patch.object(mf, "_unanswered_blocks", new=AsyncMock(return_value=False)), \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
               new=AsyncMock(return_value=None)):
        mf.reset_headline_day()
        import time
        start = time.monotonic()
        scan = _run(mf.headline_deal_scan("ACME", now_et=_T0))
        took = time.monotonic() - start
    assert took < 2.0, f"the scan waited {took:.1f}s — the deadline did not hold"
    assert [r["title"] for r in scan.released] == ["Takeover item 1"]
    assert [(u["title"], u["why"]) for u in scan.unanswered] == [("Takeover item 2", "deadline")]


def test_unanswered_passes_with_the_toggle_off_and_is_audited():
    items = [{"title": "Acme buyout talk", "description": "", "insights": [],
              "published_utc": "2026-10-01T10:00:00Z"}]
    out = _items_case(items, answers={})   # no fixture → the fake raises → unanswered
    assert out.blocked is False
    ev = [a for a in out.audits if a[0] == "mna_headline_unanswered"]
    assert ev and ev[0][2]["blocked"] is False


def test_unanswered_blocks_with_the_toggle_on():
    items = [{"title": "Acme buyout talk", "description": "", "insights": [],
              "published_utc": "2026-10-01T10:00:00Z"}]
    out = _items_case(items, answers={}, unanswered_blocks=True)
    assert out.blocked is True and out.meta["source"] == "polygon_headline_unanswered"


def test_the_unanswered_toggle_ships_off():
    """Ruling 4 (operator 2026-10-02, RULED): an unanswered headline question PASSES — the
    toggle's default OFF is his ruling. Before #692 a keyword headline blocked on its own."""
    with patch("agents.market_intelligence.db.get_runtime_toggle",
               new=AsyncMock(side_effect=lambda name, env, default=True: default)):
        assert _run(mf._unanswered_blocks()) is False


def test_a_pinning_headline_overrides_a_non_pinning_grader_and_logs_the_conflict():
    items = [{"title": "Acme to be acquired by BigCo for $20 cash", "description": "",
              "insights": [], "published_utc": "2026-10-01T10:00:00Z"}]
    out = _items_case(items, grader=H.Ans("none", "none", "none"),
                      answers={items[0]["title"]: H.Ans("target", "signed", "cash", "BigCo")})
    assert out.blocked is True and out.meta["source"] == "polygon_headline_model"
    assert any(a[0] == "mna_deal_answers_conflict" for a in out.audits)


def test_grade_mna_without_a_pin_is_audited():
    """'mna' graded while the grader's own ANSWERED fields are not a signed shell (his ruling 2,
    2026-10-03: the grade is shell-only) → the fields decide (pass) + one mna_grade_without_pin
    row; a signed shell graded 'mna' writes none (that is the rule holding)."""
    out = _items_case([], grader=H.Ans("buyer", "signed", "cash"), quality="mna")
    assert out.blocked is False
    assert [a[0] for a in out.audits].count("mna_grade_without_pin") == 1
    out = _items_case([], grader=H.Ans("shell", "signed", "stock"), quality="mna")
    assert out.blocked is True and not [a for a in out.audits if a[0] == "mna_grade_without_pin"]


# ── RULING 5 (2026-10-02): grade 'mna' with blank deal fields → BLOCK, as before #692 ─────────

def test_ruling5_grade_mna_with_blank_deal_fields_blocks():
    """The grader graded 'mna' and its deal fields were missing / out of vocabulary / cut off
    (deal_answer None). Before #692 grade 'mna' blocked; he ruled to keep that."""
    out = _items_case([], grader=None, quality="mna")
    assert out.blocked is True
    assert out.meta["source"] == "claude_classifier_unanswered"
    assert out.meta["catalyst_quality"] == "mna"
    assert out.calls == [], "the block needs no headline question"
    assert not [a for a in out.audits if a[0] == "mna_grade_without_pin"], \
        "a blank-field block must not also count as 'the prompt rule is not holding'"


def test_ruling5_does_not_fire_when_the_grade_is_not_mna():
    """A failed grade reads 'routine' with no fields — the headline decides, ruling 5 is silent."""
    out = _items_case([], grader=None, quality="routine")
    assert out.blocked is False


# ── RULING 7 (2026-10-02): a headline overrides the grader ONLY when the grader found no deal ─

_PIN_TITLE = "Acme to be acquired by BigCo for $20 a share in cash"
_PIN_ITEMS = [{"title": _PIN_TITLE, "description": "", "insights": [],
               "published_utc": "2026-10-01T10:00:00Z"}]
_PIN_ANS = {_PIN_TITLE: H.Ans("target", "signed", "cash", "BigCo")}


@pytest.mark.parametrize("grader", [
    H.Ans("buyer", "signed", "cash", "Stride Bank"),      # CHYM shape
    H.Ans("target", "speculation", "none"),               # VKTX shape
    H.Ans("target", "signed", "stock", "IRT"),            # CSR shape — all-stock
    H.Ans("buyer", "proposed", "unknown", "SkyAI"),       # FWDI shape
])
def test_ruling7_a_headline_cannot_reblock_a_grader_answered_deal(grader):
    """(The WAY shape — target/proposed — left this list on 2026-10-03: since his timing ruling a
    proposed target is NOMINATED, so the grader's own answer blocks it on the news pre-market and
    the 09:35 read decides; it is no longer a ruling-7 case.)"""
    out = _items_case(_PIN_ITEMS, grader=grader, answers=_PIN_ANS)
    assert out.blocked is False
    conflict = [a for a in out.audits if a[0] == "mna_deal_answers_conflict"]
    assert conflict and conflict[0][2]["blocked"] is False and "ruling 7" in conflict[0][1]
    released = [a for a in out.audits if a[0] == "mna_filter_released"]
    assert released and "grader_deal_no_pin" in released[0][2]["old_reasons"]
    assert released[0][2]["overruled_headline"]["title"] == _PIN_TITLE


def test_ruling7_a_headline_still_overrides_a_grader_that_found_no_deal():
    out = _items_case(_PIN_ITEMS, grader=H.Ans("none", "none", "none"), answers=_PIN_ANS)
    assert out.blocked is True and out.meta["source"] == "polygon_headline_model"
    conflict = [a for a in out.audits if a[0] == "mna_deal_answers_conflict"]
    assert conflict and conflict[0][2]["blocked"] is True


def test_ruling7_a_headline_still_decides_when_the_grader_did_not_answer():
    out = _items_case(_PIN_ITEMS, grader=None, quality="routine", answers=_PIN_ANS)
    assert out.blocked is True and out.meta["source"] == "polygon_headline_model"
    assert not [a for a in out.audits if a[0] == "mna_deal_answers_conflict"]


def test_ruling7_also_gates_the_unanswered_toggle():
    """With the toggle ON (not his ruling — proving the gate covers the whole headline path),
    an unanswered headline still cannot re-block a grader-answered deal."""
    items = [{"title": "Acme buyout talk", "description": "", "insights": [],
              "published_utc": "2026-10-01T10:00:00Z"}]
    out = _items_case(items, grader=H.Ans("buyer", "signed", "cash"), answers={},
                      unanswered_blocks=True)
    assert out.blocked is False
    out = _items_case(items, grader=H.Ans("none", "none", "none"), answers={},
                      unanswered_blocks=True)
    assert out.blocked is True and out.meta["source"] == "polygon_headline_unanswered"


def test_a_grader_answered_deal_with_no_old_rule_signal_is_released_for_review():
    """Reviewer: FWDI's 'proposal to acquire' carries no keyword — without this reason a grader
    release writes no row and the monthly review cannot see it."""
    out = _items_case([], grader=H.Ans("buyer", "proposed", "unknown", "SkyAI"), quality="strong",
                      texts=["FWDI renewed its proposal to acquire SkyAI"])
    rel = [a for a in out.audits if a[0] == "mna_filter_released"]
    assert rel and rel[0][2]["old_reasons"] == ["grader_deal_no_pin"]
    assert rel[0][2]["old_rule_would_block"] is False
    assert "released for review" in rel[0][1] and "old rule would have blocked" not in rel[0][1]


def test_no_old_rule_signal_means_no_released_row():
    out = _items_case([], grader=H.Ans("none", "none", "none"), quality="strong",
                      texts=["strong quarterly beat"])
    assert out.audits == []


def test_keyword_in_text_alone_never_blocks_any_more():
    """The keyword-in-text path is retired as a blocking path — it only feeds the comparator."""
    out = _items_case([], grader=None, quality=None,
                      texts=["XYZ entered a definitive agreement to be acquired by ABC"])
    assert out.blocked is False
    rel = [a for a in out.audits if a[0] == "mna_filter_released"]
    assert rel and rel[0][2]["old_reasons"] == ["keyword_in_text_0:definitive agreement"]


def test_telemetry_failure_cannot_change_the_verdict():
    """_audit_once swallows every error — a dead DB must never alter the filter's answer."""
    with patch("agents.market_intelligence.db.get_pool",
               new=AsyncMock(side_effect=RuntimeError("db down"))), \
         patch("agents.market_intelligence.db.log_audit_event",
               new=AsyncMock(side_effect=RuntimeError("db down"))):
        _run(mf._audit_once("mna_filter_released", "X", "s", {}))


def test_return_shape_is_unchanged_for_callers_that_patch_it():
    """flag / 9m / low-cap / anticipation call is_likely_ma(ticker, check_polygon=..., on_or_before=
    ..., polygon_lookback_days=...) and read (bool, dict|None) — no caller change needed."""
    import inspect
    sig = inspect.signature(mf.is_likely_ma)
    for kw in ("check_polygon", "on_or_before", "polygon_lookback_days", "deal_answer",
               "catalyst_quality", "catalyst_texts"):
        assert kw in sig.parameters


# ── 4. SCHEMAS ────────────────────────────────────────────────────────────────────────────────

def test_headline_tool_puts_the_note_last():
    props = list(mf._HEADLINE_TOOL["input_schema"]["properties"])
    assert props == ["deal_role", "deal_status", "deal_consideration", "deal_counterparty", "note"]
    assert mf._HEADLINE_TOOL["input_schema"]["required"] == props


_NONE_KINDS = ("minority stake", "PIPE", "private placement",
               "government or strategic equity investment", "warrants", "buyback")


def test_definitions_signed_needs_no_terms_and_target_means_control():
    """Fix round (reviewers): 'signed' carried 'terms stated' while 'unknown' consideration means
    'terms not in the text' — a model following the text could call a signed, terms-less deal
    'proposed' and release SUNE / CLRO. Terms belong to consideration only. 'target' read
    'another company is buying this company's shares', which a PIPE or a government equity
    investment fits (RGTI's 8-K carries item 3.02) — target now means control, and those are
    named 'none'. One wording in the shared field, the grader's RULE 3 and the headline prompt."""
    role = mf.DEAL_FIELD_PROPERTIES["deal_role"]["description"]
    status = mf.DEAL_FIELD_PROPERTIES["deal_status"]["description"]
    assert "terms stated" not in status and "signed: definitive/merger agreement signed or " \
        "tender offer commenced. " in status
    target = "acquiring all of, or control of, this company, so its holders are paid out"
    assert f"target: another company is {target}" in role
    headline = mf.build_headline_prompt("X", None, {}, None)
    assert f"'target' if another company is {target}" in headline
    _, _, calls = _grade({"quality": "routine", "analysis": "x"})
    rule3 = calls[0]["messages"][0]["content"].split("3. DEAL FIELDS", 1)[1].split("\n4. ", 1)[0]
    assert "terms stated" not in rule3
    assert " ".join(f"'target' if another company is {target}".split()) in " ".join(rule3.split())
    for text in (role, headline, " ".join(rule3.split())):
        for kind in _NONE_KINDS:
            assert kind in text, (kind, text[:80])


def test_the_shared_enums_match_the_rule_vocabulary():
    p = mf.DEAL_FIELD_PROPERTIES
    assert tuple(p["deal_role"]["enum"]) == mf.DEAL_ROLES
    assert tuple(p["deal_status"]["enum"]) == mf.DEAL_STATUSES
    assert tuple(p["deal_consideration"]["enum"]) == mf.DEAL_CONSIDERATIONS
    assert mf._PINNING_CONSIDERATIONS <= set(mf.DEAL_CONSIDERATIONS)


# ── 5. THE EP GRADER'S DEAL FIELDS (ep_detector plumbing) ─────────────────────────────────────

from agents.market_intelligence import ep_detector  # noqa: E402


def test_catalyst_tool_order_is_grade_then_deal_fields_then_analysis_last():
    props = list(ep_detector._CATALYST_TOOL["input_schema"]["properties"])
    # #692b: `quality_if_no_deal` is a VERDICT field — placed with the others, before the free text
    assert props == ["quality", "deal_role", "deal_status", "deal_consideration",
                     "deal_counterparty", "quality_if_no_deal", "analysis"]
    assert ep_detector._CATALYST_TOOL["input_schema"]["required"] == props
    assert ep_detector._CATALYST_TOOL["input_schema"]["properties"]["quality_if_no_deal"]["enum"] == [
        "game_changer", "strong", "routine", "mna"]
    assert ep_detector._CATALYST_TOOL["input_schema"]["properties"]["quality"]["enum"] == [
        "game_changer", "strong", "routine", "mna"]


def _grade(tool_input=None, *, raise_exc=None, sink=True):
    calls = []

    async def create(**kw):
        calls.append(kw)
        if raise_exc:
            raise raise_exc
        block = SimpleNamespace(type="tool_use", input=tool_input)
        return SimpleNamespace(content=[block], stop_reason="tool_use")
    deal_sink = {} if sink else None
    with patch.object(ep_detector._get_claude(), "messages") as m, \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
               new=AsyncMock(return_value=None)):
        m.create = create
        out = _run(ep_detector._classify_catalyst_claude(
            "FWDI", [], {"companyName": "Forward Industries"}, grounded_text="8-K text",
            deal_sink=deal_sink))
    return out, deal_sink, calls


def test_grader_writes_its_deal_answer_into_the_sink():
    out, sink, _ = _grade({"quality": "strong", "deal_role": "buyer", "deal_status": "proposed",
                           "deal_consideration": "unknown", "deal_counterparty": "SkyAI",
                           "analysis": "FWDI sweetened its bid for SkyAI."})
    assert out == ("strong", "FWDI sweetened its bid for SkyAI.")
    assert sink["deal_answer"] == DealAnswer("buyer", "proposed", "unknown", "SkyAI")


def test_grader_without_valid_deal_fields_leaves_the_question_unanswered():
    out, sink, _ = _grade({"quality": "routine", "analysis": "no catalyst"})
    assert out == ("routine", "no catalyst") and "deal_answer" not in sink


def test_failed_grade_leaves_the_question_unanswered_not_none():
    out, sink, _ = _grade(raise_exc=RuntimeError("api down"))
    assert out[0] == "routine" and ep_detector._CLASSIFY_FAIL_SENTINEL in out[1]
    assert "deal_answer" not in sink


def test_the_two_tuple_return_is_kept_without_a_sink():
    out, _, _ = _grade({"quality": "mna", "deal_role": "target", "deal_status": "signed",
                        "deal_consideration": "cash", "deal_counterparty": "Copart",
                        "analysis": "x"}, sink=False)
    assert out == ("mna", "x")


def test_rule_3_grades_a_price_fixing_buyout_mna_and_asks_the_merit_grade_too():
    """#692b (operator 2026-10-03: "the label doesn't kill it only if the M&A is false"): ruling 2
    of the same day (shell-only 'mna') is REVERTED — the ADR 0030 corpus case S19 requires a
    definitive all-cash buyout target to grade 'mna'. The rule names the pinning considerations
    again, and now also asks `quality_if_no_deal` (the merit grade used when the opening price
    releases the name). The drift test for the grader's prompt + tool."""
    _, _, calls = _grade({"quality": "routine", "analysis": "x"})
    prompt = calls[0]["messages"][0]["content"]
    assert "DEAL FIELDS" in prompt and "deal_role" in prompt and "'shell'" in prompt
    # the old keyword list is gone — RGTI's FUNDING 'definitive agreement' is why
    assert 'Keywords: "definitive agreement"' not in prompt
    rule = " ".join(prompt.split('Grade "mna" ONLY when', 1)[1].split("\n4. ", 1)[0].split())
    assert rule.startswith("deal_status is 'signed' AND either deal_role is 'shell', or deal_role is 'target' and deal_consideration is")
    for cons in mf._PINNING_CONSIDERATIONS:
        assert f"'{cons}'" in rule
    assert "'stock'" not in rule.split("quality_if_no_deal", 1)[0]
    assert "quality_if_no_deal: the grade this catalyst earns on its own merit under rules 1, 2, 4 and 5 AS IF the deal were not real" in rule
    q = ep_detector._CATALYST_TOOL["input_schema"]["properties"]["quality"]["description"]
    assert "mna: ONLY when deal_status is signed AND either deal_role is shell, or deal_role is target" in q
    assert ep_detector.CATALYST_GRADE_PROMPT_VERSION == "v4-2026-10-03-deal-fields-merit-if-no-deal"


def test_post_grade_filters_decides_on_the_graders_answer():
    seen = {}

    async def fake_is_likely_ma(ticker, **kw):
        seen.update(kw)
        return False, None
    ans = DealAnswer("buyer", "signed", "cash", "Stride Bank")
    with patch.object(ep_detector, "is_likely_ma", new=fake_is_likely_ma), \
         patch.object(ep_detector, "log_audit_event", new=AsyncMock(return_value=None)):
        _run(ep_detector._post_grade_filters(
            "CHYM", "strong", "analysis", "summary", 15.0, 1_000_000, 3.0,
            datetime(2026, 9, 9).date(), lattice_acting=False, deal_answer=ans))
    assert seen["deal_answer"] is ans and seen["check_polygon"] is True
    assert seen["catalyst_quality"] == "strong"   # ruling 5 + comparator input
    # the EP scan alone skips the ORB window and spends the reserved EP budget
    assert seen["skip_in_orb"] is True and seen["budget_pool"] == "ep"


def test_only_the_EP_scan_opts_into_the_ORB_skip_and_the_EP_budget():
    """Population gate (derived, not hand-listed): every `is_likely_ma(...)` call in agents/ is
    found by AST, the population is NAMED (a new caller fails here until it is classified), and
    only ep_detector._post_grade_filters passes skip_in_orb / budget_pool."""
    # source-pin-ok: a call-site POPULATION check — which of the six detectors pass the EP-only
    # options cannot be exercised without running each detector's full scan (DB + Polygon + the
    # scheduler); the behaviour of the options themselves is tested above. AST, not regex.
    import ast

    class _Calls(ast.NodeVisitor):
        def __init__(self, fname):
            self.fname, self.stack, self.found = fname, [], []

        def _fn(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()
        visit_FunctionDef = visit_AsyncFunctionDef = _fn

        def visit_Call(self, node):
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            if name == "is_likely_ma":
                opts = {k.arg for k in node.keywords} & {"skip_in_orb", "budget_pool", "pin_reader", "gap_pct"}
                self.found.append((self.fname, self.stack[-1] if self.stack else "<module>",
                                   tuple(sorted(opts))))
            self.generic_visit(node)
    found = []
    for path in sorted((_REPO / "agents").rglob("*.py")):
        v = _Calls(path.name)
        v.visit(ast.parse(path.read_text(encoding="utf-8")))
        found += v.found
    # 2026-10-03: `pin_reader` (the price decides) is passed by the EP scan (the open window),
    # the flag scan + the anticipation scan (the day window) and the low-cap lane (the open
    # window); the two 9M sites pass none and keep the 10-02 verdict (9M is retired). `gap_pct`
    # (his ruling 3, the price-only arm) is passed by the EP scan ONLY.
    assert sorted(found) == [
        ("ep_detector.py", "_post_grade_filters", ("budget_pool", "gap_pct", "pin_reader", "skip_in_orb")),
        ("flag_detector.py", "_mna_check", ("pin_reader",)),
        ("lowcap_lane.py", "enrich_and_record", ("pin_reader",)),
        ("ninem_detector.py", "run_9m_eod_sweep", ()),
        ("ninem_detector.py", "run_9m_scan", ()),
        ("scheduler.py", "_consolidation_readiness_scan", ("pin_reader",)),
    ]


def test_cached_grade_carries_the_answer_and_old_positional_shape_still_builds():
    g = ep_detector.CachedGrade("routine", 1.0, "n", "a", None, True)
    assert g.deal_answer is None
    g2 = g._replace(deal_answer=DealAnswer("target", "signed", "cash"))
    assert g2.deal_answer.role == "target"


def test_tier_shadow_rows_record_the_answer():
    ans = DealAnswer("target", "signed", "stock", "IRT")
    row = ep_detector._tier_kill_row("CSR", "routine", None, "llm", "a", "g", "n",
                                     {"gap_pct": 9.5}, 2.0, deal_answer=ans)
    assert (row["deal_role"], row["deal_status"], row["deal_consideration"],
            row["deal_counterparty"]) == ("target", "signed", "stock", "IRT")
    blank = ep_detector._tier_kill_row("X", "routine", None, "llm", "a", "g", "n", {}, 1.0)
    assert blank["deal_role"] is None


def test_tier_shadow_recorder_appends_the_answer_after_30():
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import catalyst_tier_shadow as cts
    pool, conn = make_mock_pool()
    captured = []

    async def _execute(sql, *args):
        captured.append((sql, args))
        return "INSERT 0 1"
    conn.execute = _execute
    with patch.object(cts, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(cts, "get_sectors_batch", new=AsyncMock(return_value={})):
        n = _run(cts.record_catalyst_tier_shadow(
            [{"ticker": "ACVA", "live_quality": "mna", "deal_role": "target",
              "deal_status": "signed", "deal_consideration": "cash",
              "deal_counterparty": "Copart"}],
            ["ACVA"], datetime(2026, 9, 11).date(), datetime(2026, 9, 11, 7, 5)))
    assert n == 1
    sql, args = captured[0]
    assert "$34" in sql and "deal_counterparty" in sql
    assert args[30:34] == ("target", "signed", "cash", "Copart")
    assert args[26] == "llm"   # $27 live_side unchanged


def test_why_shows_the_deal_answer_in_plain_words_with_the_filters_own_verdict():
    """/why (operator surface) renders the recorded answer through the SAME deal_pins_price the
    filter runs, so the line cannot disagree with what the filter did."""
    from agents.market_intelligence.agent import _deal_answer_line, _format_catalyst_grade_block
    acva = _deal_answer_line({"deal_role": "target", "deal_status": "signed",
                              "deal_consideration": "cash", "deal_counterparty": "Copart"})
    # 2026-10-03: a nominated target is decided by the open price; the line says so.
    assert acva == ("   deal: this company is being bought — signed deal with Copart, paid in cash"
                    " → deal-nominated: the M&A filter blocks it unless the open price shows it free")
    hzo = _deal_answer_line({"deal_role": "target", "deal_status": "proposed",
                             "deal_consideration": "unknown", "deal_counterparty": "Blackstone"})
    assert hzo.endswith("unless the open price shows it free") and "proposal / talks" in hzo
    sune = _deal_answer_line({"deal_role": "shell", "deal_status": "signed",
                              "deal_consideration": "stock", "deal_counterparty": "Suniva"})
    assert sune.endswith("price pinned, the M&A filter blocks it")
    fwdi = _deal_answer_line({"deal_role": "buyer", "deal_status": "proposed",
                              "deal_consideration": "unknown", "deal_counterparty": "SkyAI"})
    assert fwdi.endswith("lets it through") and "the buyer" in fwdi and "paid in" not in fwdi
    csr = _deal_answer_line({"deal_role": "target", "deal_status": "signed",
                             "deal_consideration": "stock", "deal_counterparty": "IRT"})
    assert csr.endswith("lets it through") and "paid in stock" in csr
    assert _deal_answer_line({"deal_role": "none", "deal_status": "none"}) is None
    assert _deal_answer_line({}) is None   # unanswered / pre-#692 row
    block = "\n".join(_format_catalyst_grade_block({
        "live_quality_last": "mna", "deal_role": "target", "deal_status": "signed",
        "deal_consideration": "cash", "deal_counterparty": "Copart"}))
    assert "deal-nominated: the M&A filter blocks it unless the open price shows it free" in block


def test_enriched_corpus_forwards_the_sink():
    seen = {}

    async def fake_classify(*a, **kw):
        seen.update(kw)
        return "routine", "x"
    with patch.object(ep_detector, "_classify_catalyst_claude", new=fake_classify):
        sink = {}
        _run(ep_detector._build_enriched_corpus(
            "T", datetime(2026, 9, 9).date(), {"companyName": "T"},
            ext_filings=[], dilution=None, dilution_computed=True, benzinga_items=[],
            perplexity_answer="", deal_sink=sink))
    assert seen["deal_sink"] is sink


# ── 6. THE MONTHLY REVIEW (scripts/mna_filter_accuracy_review.py) ────────────────────────────

def test_monthly_review_shows_unanswered_passes_in_the_under_fire_section(capsys):
    """Reviewer: a name that passed because the headline question got NO answer wrote no
    released row, so the monthly review could not see it. It now has its own section, read
    from `mna_headline_unanswered` rows whose summary ends 'passed'."""
    import json as _json
    import importlib
    from datetime import date as _date
    from tests.conftest import make_mock_pool
    review = importlib.import_module("scripts.mna_filter_accuracy_review")
    pool, conn = make_mock_pool()
    seen = []

    def _row(ticker, detail):
        return {"ticker": ticker, "fire_day": _date(2026, 10, 5), "detail": "", "detail_full":
                _json.dumps(detail), "open_price": 10.0, "low_price": 9.5, "peak_high": 12.0,
                "pk_vs_open": 20.0, "pk_vs_low": 26.3}

    async def _fetch(sql, event_type, days, like):
        seen.append((event_type, like))
        return {
            "mna_filter_fired": [_row("ACVA", {"role": "target", "status": "signed",
                                               "consideration": "cash"})],
            "mna_filter_released": [_row("FWDI", {"grader": {"role": "buyer", "status": "proposed",
                                                             "consideration": "unknown"}})],
            "mna_headline_unanswered": [_row("XYZ", {"blocked": False, "unanswered_n": 2,
                                                     "unanswered": [{"why": "orb_window"}]})],
            "mna_release_without_merit_grade": [],
        }[event_type]
    conn.fetch = _fetch
    with patch("agents.market_intelligence.db.get_pool", new=AsyncMock(return_value=pool)):
        assert _run(review.main(35)) == 0
    out = capsys.readouterr().out
    assert ("mna_headline_unanswered", "%passed") in seen
    assert ("mna_filter_released", "%") in seen and ("mna_filter_fired", "%") in seen
    assert "PASSED UNANSWERED" in out and "XYZ" in out and "unanswered (orb_window), 2 article(s)" in out
    assert "grader buyer/proposed/unknown" in out


def test_monthly_review_marks_a_pre_market_block_the_price_released_the_same_day(capsys):
    """His 2026-10-03 timing ruling: a nominated name is blocked pre-market on the news (fired
    row, `why = news_blocked_price_unread`) and the 09:35 read may release it (released row,
    `pin_free`) — the review shows the fired row as RELEASED, not as a suppression."""
    import json as _json
    import importlib
    from datetime import date as _date
    from tests.conftest import make_mock_pool
    review = importlib.import_module("scripts.mna_filter_accuracy_review")
    pool, conn = make_mock_pool()

    def _row(ticker, detail, pk=30.0):
        return {"ticker": ticker, "fire_day": _date(2026, 10, 6), "detail": "", "detail_full":
                _json.dumps(detail), "open_price": 10.0, "low_price": 9.5, "peak_high": 13.0,
                "pk_vs_open": pk, "pk_vs_low": 36.8}

    async def _fetch(sql, event_type, days, like):
        return {
            "mna_filter_fired": [_row("PD", {"role": "target", "status": "signed", "consideration": "unknown",
                                             "why": "news_blocked_price_unread",
                                             "pin": {"readable": False, "why": "pre_market"}}),
                                 _row("HZO", {"role": "target", "status": "proposed", "consideration": "unknown",
                                              "why": "pinned", "pin": {"window": "open5m", "range_pct": 0.15,
                                                                      "threshold_pct": 1.0, "readable": True,
                                                                      "pinned": True}}, pk=0.4)],
            "mna_filter_released": [_row("PD", {"old_reasons": ["grade_mna", "pin_free"], "grader": {},
                                                "pin_release": {"answer": {"role": "target", "status": "signed",
                                                                           "consideration": "unknown"},
                                                                "source": "claude_deal_fields",
                                                                "pin": {"window": "open5m", "range_pct": 5.36,
                                                                        "threshold_pct": 1.0, "readable": True,
                                                                        "pinned": False}}})],
            "mna_headline_unanswered": [],
            "mna_release_without_merit_grade": [],
        }[event_type]
    conn.fetch = _fetch
    with patch("agents.market_intelligence.db.get_pool", new=AsyncMock(return_value=pool)):
        assert _run(review.main(35)) == 0
    out = capsys.readouterr().out
    pd_line = next(ln for ln in out.splitlines() if ln.strip().startswith("PD ") and "blocked pre-market" in ln)
    assert "RELEASED later that day (price free at 09:35)" in pd_line and "MATERIAL-MISS" not in pd_line
    hzo_line = next(ln for ln in out.splitlines() if ln.strip().startswith("HZO "))
    assert "open5m range 0.15% vs 1.0% -> PINNED" in hzo_line and "RELEASED" not in hzo_line


def test_monthly_review_renders_the_price_reading_on_fired_and_released_rows():
    """2026-10-03: a fired row carries `pin` (the reading that blocked), a price-released row
    carries `pin_release` — the review prints both so his monthly read sees the number."""
    import importlib
    import json as _json
    review = importlib.import_module("scripts.mna_filter_accuracy_review")
    fired = review._answer(_json.dumps({"role": "target", "status": "proposed", "consideration": "unknown",
                                        "pin": {"window": "open5m", "range_pct": 0.1542,
                                                "threshold_pct": 1.0, "readable": True, "pinned": True}}))
    assert fired == "target/proposed/unknown; open5m range 0.1542% vs 1.0% -> PINNED"
    released = review._answer(_json.dumps({"old_reasons": ["grade_mna", "pin_free"], "grader": {},
                                           "pin_release": {"answer": {"role": "target", "status": "signed",
                                                                      "consideration": "unknown"},
                                                           "source": "claude_deal_fields",
                                                           "pin": {"window": "open5m", "range_pct": 5.3591,
                                                                   "threshold_pct": 1.0, "readable": True,
                                                                   "pinned": False}}}))
    assert released == "nominated target/signed/unknown via claude_deal_fields; open5m range 5.3591% vs 1.0% -> FREE"



def test_review_only_a_price_release_not_kept_blocked_marks_a_fired_row_released():
    """2026-10-03 review: any same-day `mna_filter_released` row used to mark the fired row
    "released later that day" — a comparator row (old rule would have blocked) and the #692b
    fail safe (released on price, KEPT blocked for want of a merit grade) included."""
    import importlib
    from datetime import date as _date
    review = importlib.import_module("scripts.mna_filter_accuracy_review")
    d = _date(2026, 10, 5)
    released = [{"ticker": "PD", "fire_day": d, "detail_full": '{"old_reasons": ["pin_free"], "pin_release": {}}'},
                {"ticker": "CMP", "fire_day": d, "detail_full": '{"old_reasons": ["headline_keyword"]}'},
                {"ticker": "FS", "fire_day": d, "detail_full": '{"pin_release": {}}'}]
    kept = [{"ticker": "FS", "fire_day": d}]
    assert review._price_released_days(released, kept) == {("PD", str(d))}
