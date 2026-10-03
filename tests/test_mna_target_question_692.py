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
             "SOUN", "LII", "SCZM"}
    assert {c.ticker for c in H.CASES if c.ground_truth} == named


@pytest.mark.parametrize("ticker", ["THR", "CECO", "ROKU", "QBTS", "DSGN", "KALV"])
def test_agent_read_plumbing_cases_behave_as_designed(ticker):
    """NOT ground truth — the design's expected behaviour on plumbing shapes: one title, two
    opposite roles (THR/CECO); a target headline the old regex read as acquirer (ROKU); a
    roundup bleed never asked (QBTS); recall moved from the retired keyword path to the grader
    fields (DSGN); a litigation notice never asked (KALV)."""
    case = H.CASES_BY_TICKER[ticker]
    out = _run(H.run_new(case))
    assert ("BLOCK" if out.blocked else "PASS") == case.expected and not out.unplanned


def test_QBTS_bleed_and_KALV_litigation_cost_no_model_call():
    for t in ("QBTS", "KALV"):
        assert _run(H.run_new(H.CASES_BY_TICKER[t])).calls == []


# ── 3. HEADLINE-QUESTION PLUMBING ─────────────────────────────────────────────────────────────

_T0 = datetime(2026, 10, 2, 8, 0, tzinfo=_ET)


def _fresh():
    mf._HEADLINE_MEMO.clear()
    mf._HEADLINE_ATTEMPTS.clear()
    mf._HEADLINE_DAY.update({"day": None, "calls": 0})


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


def _ask(client, item=_ITEM, now=_T0):
    with patch.object(mf, "_get_headline_client", return_value=client), \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
               new=AsyncMock(return_value=None)):
        return _run(mf.ask_deal_question("ACME", item, company_name="Acme", now_et=now))


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


def test_daily_cap_leaves_the_question_unanswered():
    _fresh()
    mf._HEADLINE_DAY.update({"day": _T0.date(), "calls": mf._HEADLINE_QUESTION_CALLS_CAP})
    client, calls = _fake()
    ans, how = _ask(client)
    assert ans is None and how == "daily_cap" and calls == []


def test_orb_window_skips_the_call():
    _fresh()
    client, calls = _fake()
    ans, how = _ask(client, now=datetime(2026, 10, 2, 9, 35, tzinfo=_ET))
    assert ans is None and how == "orb_window" and calls == []


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
    """No toggle flip in the build (THE LINE): the default is OFF = pass. OFF is NOT today's
    behaviour (today a keyword headline blocks) — operator decision 4."""
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
    out = _items_case([], grader=H.Ans("buyer", "signed", "cash"), quality="mna")
    assert out.blocked is False
    assert [a[0] for a in out.audits].count("mna_grade_without_pin") == 1


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
    assert props == ["quality", "deal_role", "deal_status", "deal_consideration",
                     "deal_counterparty", "analysis"]
    assert ep_detector._CATALYST_TOOL["input_schema"]["required"] == props
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


def test_rule_3_asks_the_question_and_ties_the_grade_to_the_pin():
    _, _, calls = _grade({"quality": "routine", "analysis": "x"})
    prompt = calls[0]["messages"][0]["content"]
    assert "DEAL FIELDS" in prompt and "deal_role" in prompt and "'shell'" in prompt
    # the old keyword list is gone — RGTI's FUNDING 'definitive agreement' is why
    assert 'Keywords: "definitive agreement"' not in prompt
    # the grade rule names exactly the pinning considerations the code uses
    rule = prompt.split('Grade "mna" ONLY when', 1)[1].split("— that is", 1)[0]
    for cons in mf._PINNING_CONSIDERATIONS:
        assert f"'{cons}'" in rule
    assert "'shell'" in rule and "'signed'" in rule and "'stock'" not in rule


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
    assert seen["catalyst_quality"] == "strong"   # comparator input only


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
    assert acva == ("   deal: this company is being bought — signed deal with Copart, paid in cash"
                    " → price pinned, the M&A filter blocks it")
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
    assert "price pinned, the M&A filter blocks it" in block


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
