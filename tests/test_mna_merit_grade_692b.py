"""#692b (operator 2026-10-03: "the label doesn't kill it only if the M&A is false").

Ruling 2 (shell-only 'mna') is REVERTED: a SIGNED target paid cash / mixed / unknown, or a signed
shell, is graded 'mna' again — ADR 0030 corpus case S19 (a definitive all-cash buyout TARGET)
passes AS AUTHORED. The grader adds `quality_if_no_deal` (its merit grade as if the deal were not
real). When the 09:35 open-window read RELEASES a news-blocked name (`pin_free`), the EP scan
re-scores it with that merit grade instead of 'mna' — grader and judge — so a PD-class name can
reach HIGH through the existing post-open path. A pinned (confirmed) name keeps 'mna'. A missing
merit grade FAILS SAFE: the name keeps 'mna' (0 catalyst points, cannot reach HIGH) and a row says so.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import ep_detector, ep_grade_judge, ep_rubric
from agents.market_intelligence import ma_filter as mf
from agents.market_intelligence.ma_filter import DealAnswer

_REPO = Path(__file__).resolve().parents[1]
_CORPUS = json.loads((_REPO / "scripts" / "evals" / "judge_robustness_corpus_v1.json").read_text())
S19 = next(c for c in _CORPUS["cases"] if c["id"] == "S19")
_RECORD = json.loads((_REPO / "scripts" / "evals" / "judge_eval_pass_record.json").read_text())


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("mna_harness_692b", "scripts/probes/_284_mna_acquirer_backtest.py")
EVAL = _load("judge_eval_692b", "scripts/evals/run_judge_robustness_eval.py")
CHECK = _load("merit_check_692b", "scripts/probes/_692/merit_grade_check.py")


def _run(coro):
    return asyncio.run(coro)


# ── 1. the grade surface: the judge rubric is byte-identical to the passing record ───────────

def test_judge_rule_6_is_the_0827_text_and_the_rubric_hash_is_the_passing_records():
    assert ep_grade_judge.RUBRIC_HASH == "d65ac7f3" == _RECORD["rubric_hash"]
    assert ('6. M&A: if the company is being acquired (buyout/merger/tender/going-private), grade "mna" —\n'
            '   but this is advisory; a separate M&A filter is authoritative.') in ep_grade_judge._RUBRIC
    assert ep_grade_judge.RUBRIC_VERSION == _RECORD["rubric_version"]
    # the grader prompt DID change (deal fields + the merit field) → its version key moved; the
    # gate therefore asks for one eval re-run, by design
    assert ep_detector.CATALYST_GRADE_PROMPT_VERSION != _RECORD["catalyst_grade_prompt_version"]


# ── 2. S19's shape through the GRADER ────────────────────────────────────────────────────────

_S19_GRADE = {"quality": "mna", "deal_role": "target", "deal_status": "signed",
              "deal_consideration": "cash", "deal_counterparty": "a private-equity firm",
              "quality_if_no_deal": "routine",
              "analysis": "Definitive all-cash buyout at $14.50; the stock is pinned to the deal price."}


def _grade(tool_input, text):
    calls, sink = [], {}

    async def create(**kw):
        calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=tool_input)], stop_reason="tool_use")
    with patch.object(ep_detector._get_claude(), "messages") as m, \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", new=AsyncMock(return_value=None)):
        m.create = create
        out = _run(ep_detector._classify_catalyst_claude(
            S19["payload"]["ticker"], [], {"companyName": "Target Co", "sector": "Healthcare", "marketCap": 1.2e9},
            grounded_text=text, deal_sink=sink))
    return out, sink, calls[0]


def test_S19_grader_grades_a_definitive_all_cash_target_mna_and_carries_the_merit_grade():
    out, sink, kw = _grade(_S19_GRADE, S19["payload"]["grounded_text"])
    assert out[0] == "mna"
    assert sink["deal_answer"] == DealAnswer("target", "signed", "cash", "a private-equity firm")
    assert sink["quality_if_no_deal"] == "routine"
    prompt = kw["messages"][0]["content"]
    assert ("Grade \"mna\" ONLY when deal_status is 'signed' AND either deal_role is 'shell', or deal_role is\n"
            "   'target' and deal_consideration is 'cash', 'mixed' or 'unknown'") in prompt
    assert "quality_if_no_deal: the grade this catalyst earns on its own merit" in prompt
    tool = kw["tools"][0]
    assert tool["input_schema"]["required"][-2:] == ["quality_if_no_deal", "analysis"]
    assert mf.deal_pins_price(sink["deal_answer"]) is True      # the filter blocks it on the news


def test_grader_merit_field_out_of_vocabulary_or_missing_is_absent_from_the_sink():
    _, sink, _ = _grade({**_S19_GRADE, "quality_if_no_deal": "excellent"}, "t")
    assert "quality_if_no_deal" not in sink and sink["deal_answer"].role == "target"
    _, sink, _ = _grade({k: v for k, v in _S19_GRADE.items() if k != "quality_if_no_deal"}, "t")
    assert "quality_if_no_deal" not in sink


# ── 3. S19's shape through the JUDGE ─────────────────────────────────────────────────────────

def _verdict(grade="mna", tier="none"):
    return ep_grade_judge._normalize_verdict({
        "grade": grade, "tier": tier, "direction_vs_floor": "demote", "fire_axes": [],
        "rationale": "Classic target-side M&A: arbitrage spread only.", "grade_reason": "pinned to the deal price",
        "tier_reason": "no momentum trade", "materiality_tier": "transformative"})


def test_S19_judge_prompt_is_unchanged_and_its_mna_verdict_passes_the_golden_predicate():
    prompt = ep_grade_judge._build_judge_prompt(S19["payload"])
    assert "M&A FILTER READ" not in prompt and "catalyst=mna" in prompt
    verdict = _verdict()
    ok, fails = EVAL.check_predicates(S19["golden"]["must"], verdict)
    assert ok, fails
    # not released → the judge's 'mna' stands as its own read
    assert ep_detector._judge_grade_after_release(verdict, {"mna_released_on_price": False,
                                                            "quality_if_no_deal": "routine"}) == verdict


def test_a_released_name_tells_the_judge_and_relabels_its_mna_with_the_merit_grade():
    released = {**S19["payload"], "mna_price_released": True}
    prompt = ep_grade_judge._build_judge_prompt(released)
    assert "--- M&A FILTER READ (the opening price) ---" in prompt and "RELEASED it at 09:35" in prompt
    # the block is rendered OUTSIDE the hashed rubric: same rubric, same hash
    assert ep_grade_judge.RUBRIC_HASH == "d65ac7f3"
    payload = ep_grade_judge.assemble_judge_inputs({"ticker": "PD", "mna_released_on_price": True})
    assert payload["mna_price_released"] is True
    assert ep_grade_judge.assemble_judge_inputs({"ticker": "PD"})["mna_price_released"] is False
    v = _verdict()
    out = ep_detector._judge_grade_after_release(v, {"mna_released_on_price": True, "quality_if_no_deal": "strong"})
    assert out["grade"] == "strong" and out["tier"] == "none"          # the TIER is the judge's own
    assert out["grade_reason"].startswith("[mna -> strong: the open window released this name]")
    assert v["grade"] == "mna", "the original verdict is not mutated"
    # fail safe: no usable merit grade → the judge's 'mna' stands
    for bad in (None, "mna", "excellent"):
        assert ep_detector._judge_grade_after_release(v, {"mna_released_on_price": True, "quality_if_no_deal": bad}) == v
    # a non-mna judge read is never touched
    strong = _verdict("strong", "HIGH")
    assert ep_detector._judge_grade_after_release(strong, {"mna_released_on_price": True, "quality_if_no_deal": "routine"}) == strong
    assert ep_detector._judge_grade_after_release(None, {"mna_released_on_price": True}) is None


# ── 4. the release re-scores (grader side) ───────────────────────────────────────────────────

def test_merit_grade_after_release_truth_table():
    f = ep_detector.merit_grade_after_release
    assert f("mna", "strong") == ("strong", "merit_grade")
    assert f("mna", "routine") == ("routine", "merit_grade")
    assert f("mna", "game_changer") == ("game_changer", "merit_grade")
    assert f("mna", None) == ("mna", "no_merit_grade_fail_safe")
    assert f("mna", "mna") == ("mna", "no_merit_grade_fail_safe")
    assert f("mna", "excellent") == ("mna", "no_merit_grade_fail_safe")
    assert f("strong", "routine") == ("strong", "grade_not_mna")
    assert f("routine", None) == ("routine", "grade_not_mna")


_RELEASE = {"released_on_price": True, "source": "claude_deal_fields",
            "pin": {"window": "open5m", "range_pct": 5.3591, "threshold_pct": 1.0, "readable": True, "pinned": False},
            "answer": {"role": "target", "status": "signed", "consideration": "unknown"}}


def _apply(llm, merit, release):
    audits, c = [], {"ticker": "PD"}

    async def audit(event_type, summary, detail=""):
        audits.append((event_type, summary, json.loads(detail) if detail else {}))
    with patch.object(ep_detector, "log_audit_event", new=audit):
        out = _run(ep_detector._apply_release_merit_grade(
            "PD", c, llm, merit, release, "a", "g", "n", {}, False, date(2026, 5, 29)))
    return out, c, audits


def test_a_released_mna_name_is_rescored_with_its_merit_grade_and_audited():
    out, c, audits = _apply("mna", "strong", _RELEASE)
    assert out is not None and out[0] == "strong" and out[1] == "strong" and out[3] == "llm"
    assert c["mna_released_on_price"] is True and c["quality_if_no_deal"] == "strong"
    assert c["llm_catalyst_quality"] == "strong" and c["acting_catalyst_quality"] == "strong"
    assert [a[0] for a in audits] == ["mna_release_merit_grade"]
    assert audits[0][2]["from"] == "mna" and audits[0][2]["to"] == "strong" and audits[0][2]["pin"]["range_pct"] == 5.3591


def test_fail_safe_helper_keeps_mna_and_says_so_when_no_merit_grade_exists():
    """The helper's belt: a release with no usable merit grade changes nothing and writes its
    row. The FILTER is the braces — it keeps such a name BLOCKED (next test)."""
    for merit in (None, "mna", "excellent"):
        out, c, audits = _apply("mna", merit, _RELEASE)
        assert out is None, merit                                   # the caller keeps 'mna'
        assert c["mna_released_on_price"] is True and "llm_catalyst_quality" not in c
        assert [a[0] for a in audits] == ["mna_release_without_merit_grade"], merit
        assert "keeps 'mna'" in audits[0][1]


def test_fail_safe_a_released_mna_name_without_a_merit_grade_stays_BLOCKED_in_the_filter():
    """His wording: "stays 'mna' / blocked". Keeping 'mna' alone would not keep the name out — a
    0-catalyst name scores 45 raw with a theme match against the 40 bar — so the filter returns
    its skip reason and writes mna_release_without_merit_grade; with a merit grade it releases."""
    audits = []

    async def audit(event_type, summary, detail=""):
        audits.append((event_type, summary))

    async def released(ticker, **kw):
        return False, _RELEASE
    for merit in (None, "mna", "excellent"):
        sink, audits[:] = {}, []
        with patch.object(ep_detector, "is_likely_ma", new=released), \
             patch.object(ep_detector, "log_audit_event", new=audit):
            reason = _run(ep_detector._post_grade_filters(
                "PD", "mna", "a", "s", 25.4, 1_000_000, 3.0, date(2026, 5, 29), lattice_acting=False,
                deal_answer=DealAnswer("target", "signed", "unknown"), release_sink=sink,
                quality_if_no_deal=merit))
        assert reason == "M&A/buyout catalyst — no momentum trade", merit
        assert sink == {} and [a[0] for a in audits] == ["mna_release_without_merit_grade"], merit
        assert "stays blocked" in audits[0][1]
    sink, audits[:] = {}, []
    with patch.object(ep_detector, "is_likely_ma", new=released), \
         patch.object(ep_detector, "log_audit_event", new=audit):
        reason = _run(ep_detector._post_grade_filters(
            "PD", "mna", "a", "s", 25.4, 1_000_000, 3.0, date(2026, 5, 29), lattice_acting=False,
            deal_answer=DealAnswer("target", "signed", "unknown"), release_sink=sink,
            quality_if_no_deal="strong"))
    assert reason is None and sink["released_on_price"] is True and audits == []
    # a released name whose acting grade is NOT 'mna' needs no merit grade to pass
    sink, audits[:] = {}, []
    with patch.object(ep_detector, "is_likely_ma", new=released), \
         patch.object(ep_detector, "log_audit_event", new=audit):
        reason = _run(ep_detector._post_grade_filters(
            "WAY", "routine", "a", "s", 12.0, 1_000_000, 3.0, date(2026, 9, 15), lattice_acting=False,
            deal_answer=DealAnswer("target", "proposed", "unknown"), release_sink=sink,
            quality_if_no_deal=None))
    assert reason is None and sink["released_on_price"] is True and audits == []


def test_no_release_or_a_non_mna_grade_changes_nothing():
    out, c, audits = _apply("mna", "strong", {})
    assert out is None and c == {"ticker": "PD"} and audits == []
    out, c, audits = _apply("strong", "routine", _RELEASE)
    assert out is None and audits == [] and c["mna_released_on_price"] is True


def test_a_released_name_scored_on_merit_clears_the_HIGH_bar_where_mna_could_not():
    """PD's shape: +25% gap, heavy volume, a $1.2B name. Under 'mna' the catalyst scores 0 and
    the name sits below the HIGH bar; under its merit grade it clears it."""
    profile = {"companyName": "PagerDuty", "sector": "Tech", "marketCap": 1.2e9, "floatShares": 20e6}
    mna, b_mna = ep_detector._score_ep(25.4, 5.0, "mna", profile, 1.0, vol_percentile=95, adv_dollar=600e6)
    strong, b_strong = ep_detector._score_ep(25.4, 5.0, "strong", profile, 1.0, vol_percentile=95, adv_dollar=600e6)
    assert b_mna["catalyst"] == 0 and b_strong["catalyst"] == 15
    assert mna < ep_rubric.SEPARATION_BAR <= strong, (mna, strong)
    merit, why = ep_detector.merit_grade_after_release("mna", "strong")
    assert why == "merit_grade" and ep_detector._score_ep(25.4, 5.0, merit, profile, 1.0, vol_percentile=95,
                                                           adv_dollar=600e6)[0] >= ep_rubric.SEPARATION_BAR


def test_cached_grade_carries_the_merit_grade_and_the_release_flag():
    g = ep_detector.CachedGrade("mna", 1.0, "n", "a", None, False)
    assert g.quality_if_no_deal is None and g.mna_released_on_price is False
    g2 = g._replace(catalyst_quality="strong", quality_if_no_deal="strong", mna_released_on_price=True)
    assert (g2.catalyst_quality, g2.quality_if_no_deal, g2.mna_released_on_price) == ("strong", "strong", True)


# ── 5. the plumbing: the filter reports the release; the EP filter hands it to the caller ────

def test_is_likely_ma_reports_a_price_release_and_nothing_else():
    pd = _run(H.run_new(H.CASES_BY_TICKER["PD"]))                 # signed target, open free → released
    assert pd.blocked is False and pd.meta["released_on_price"] is True and pd.meta["pin"]["pinned"] is False
    hzo = _run(H.run_new(H.CASES_BY_TICKER["HZO"]))               # proposed, open pinned → confirmed, blocked
    assert hzo.blocked is True and hzo.meta["why"] == "pinned" and "released_on_price" not in hzo.meta
    chym = _run(H.run_new(H.CASES_BY_TICKER["CHYM"]))             # buyer: a plain pass
    assert chym.blocked is False and chym.meta is None


def test_post_grade_filters_hands_the_release_to_the_caller_and_a_confirmed_pin_stays_a_block():
    seen = {}

    def fake(result):
        async def _f(ticker, **kw):
            seen.update(kw)
            return result
        return _f
    sink = {}
    with patch.object(ep_detector, "is_likely_ma", new=fake((False, _RELEASE))), \
         patch.object(ep_detector, "log_audit_event", new=AsyncMock(return_value=None)):
        reason = _run(ep_detector._post_grade_filters(
            "PD", "mna", "a", "s", 25.4, 1_000_000, 3.0, date(2026, 5, 29), lattice_acting=False,
            deal_answer=DealAnswer("target", "signed", "unknown"), release_sink=sink))
    assert reason is None and sink["released_on_price"] is True and sink["pin"]["range_pct"] == 5.3591
    sink = {}
    with patch.object(ep_detector, "is_likely_ma", new=fake((False, None))), \
         patch.object(ep_detector, "log_audit_event", new=AsyncMock(return_value=None)):
        assert _run(ep_detector._post_grade_filters(
            "CHYM", "strong", "a", "s", 9.3, 1_000_000, 3.0, date(2026, 9, 9), lattice_acting=False,
            deal_answer=DealAnswer("buyer", "signed", "cash"), release_sink=sink)) is None
    assert sink == {}
    sink = {}
    with patch.object(ep_detector, "is_likely_ma", new=fake((True, {"source": "claude_deal_fields", "why": "pinned",
                                                                   "pin": {"pinned": True, "range_pct": 0.15}}))), \
         patch.object(ep_detector, "log_audit_event", new=AsyncMock(return_value=None)), \
         patch("agents.market_intelligence.ma_filter.should_log_mna_filter_fired", new=AsyncMock(return_value=True)):
        reason = _run(ep_detector._post_grade_filters(
            "HZO", "mna", "a", "s", 45.4, 1_000_000, 3.0, date(2026, 8, 10), lattice_acting=False,
            deal_answer=DealAnswer("target", "proposed", "unknown"), release_sink=sink))
    assert reason == "M&A/buyout catalyst — no momentum trade" and sink == {}


# ── 6. the paid check script is a faithful copy of the live grader ───────────────────────────

def test_merit_check_script_copies_the_live_grader_and_loads_standalone():
    assert CHECK.CATALYST_TOOL == ep_detector._CATALYST_TOOL
    assert CHECK.MAX_COST_USD == 1.50 and len(CHECK.ROWS_NOMINATED) == 18
    r3 = [json.loads(ln) for ln in (_REPO / "scripts/probes/_692/replay_pin_2026-10-03_r3.jsonl").read_text().splitlines()]
    assert list(CHECK.ROWS_NOMINATED) == [(r["ticker"], r["date"]) for r in r3 if r.get("nominated") and r.get("ep_day")]
    profile = {"companyName": "PagerDuty", "sector": "Tech", "marketCap": 1.2e9, "description": "d" * 400}
    corpus = "[SEC 8-K] " + "x" * 7000
    captured = []

    async def create(**k):
        captured.append(k["messages"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"quality": "routine", "analysis": "a"})],
                               stop_reason="tool_use")
    with patch.object(ep_detector._get_claude(), "messages") as m, \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", new=AsyncMock(return_value=None)):
        m.create = create
        _run(ep_detector._classify_catalyst_claude("PD", [], profile, grounded_text=corpus))
    assert captured[0] == CHECK.grader_prompt("PD", profile, corpus)
    probe = (
        "import importlib.abc, importlib.util, sys\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('agents', 'shared', 'core', 'scripts'):\n"
        "            raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, Block())\n"
        f"spec = importlib.util.spec_from_file_location('probe', {str(_REPO / 'scripts/probes/_692/merit_grade_check.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
        "print('loaded', mod.MAX_COST_USD, len(mod.ROWS_NOMINATED))\n")
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd="/", timeout=60)
    assert p.returncode == 0 and p.stdout.strip() == "loaded 1.5 18", p.stderr[-500:]
