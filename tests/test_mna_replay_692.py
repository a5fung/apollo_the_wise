"""#692 — the prod replay script embeds the branch's question VERBATIM, and stays read-only.

scripts/probes/_692/replay_target_question.py is piped into the prod container BEFORE the #692
branch is deployed, so it carries COPIES of the new classifier prompt, both tool schemas, the
candidate pre-filter, the LIVE decision rule (rulings 4 / 5 / 7) and origin/main's OLD grader for
the grade-stability pass. A copy that drifts would replay a question the code does not ask, or
decide with a rule the code does not run; these tests make the copy and the code one thing
(`live_verdict` is checked against the real `is_likely_ma` over a grid through the harness), and
run the whole script on the exported population with every fetcher stubbed — dry, and once with
a FAKE model client ($0, no network, no DB write).
"""
from __future__ import annotations

import asyncio
import re
import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from agents.market_intelligence import ep_detector
from agents.market_intelligence import ma_filter as mf
from agents.market_intelligence.ma_filter import DealAnswer, deal_pins_price

_REPO = Path(__file__).resolve().parents[1]
_ET = ZoneInfo("America/New_York")


def _run(coro):
    return asyncio.run(coro)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("mna_harness_692r", _REPO / "scripts" / "probes" / "_284_mna_acquirer_backtest.py")


_REPLAY_PATH = _REPO / "scripts" / "probes" / "_692" / "replay_target_question.py"
_POPULATION = _REPO / "scripts" / "probes" / "_692" / "population_mna_events_2026-05-15_2026-10-02.jsonl"


def _load_replay():
    spec = importlib.util.spec_from_file_location("replay_692", _REPLAY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load_replay()


def test_replay_loads_with_every_repo_package_unimportable():
    """Self-contained: the script must LOAD in a process where agents / shared / core / scripts
    cannot be imported at all (deployed helpers are imported inside functions, at run time)."""
    import subprocess
    import sys
    probe = (
        "import importlib.abc, importlib.util, sys\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('agents', 'shared', 'core', 'scripts'):\n"
        "            raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, Block())\n"
        f"spec = importlib.util.spec_from_file_location('replay_probe', {str(_REPLAY_PATH)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "print('loaded', mod.MAX_COST_USD, mod.MAX_CALLS, len(mod.LABELS))\n"
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                       cwd="/", timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    assert p.stdout.strip() == "loaded 6.0 700 25"


def test_replay_schemas_and_lists_equal_the_code():
    assert R.CATALYST_TOOL == ep_detector._CATALYST_TOOL
    assert R.HEADLINE_TOOL == mf._HEADLINE_TOOL
    assert R.DEAL_FIELD_PROPERTIES == mf.DEAL_FIELD_PROPERTIES
    assert R.MNA_KEYWORDS == mf._MNA_KEYWORDS
    assert R.LITIGATION_PREFIXES == mf._SHAREHOLDER_LITIGATION_PREFIXES
    assert R.PINNING_CONSIDERATIONS == mf._PINNING_CONSIDERATIONS
    assert R.SHELL_ROLE_PINS == mf._SHELL_ROLE_PINS
    assert R.HEADLINE_MAX_ARTICLES == mf._HEADLINE_MAX_ARTICLES
    assert R.MAX_CALLS == 700 and R.MAX_COST_USD == 6.00
    assert not hasattr(R, "MODEL"), "the model is resolved at run time (GROUNDED_GRADE_MODEL)"


def test_replay_old_grader_is_origin_mains_verbatim():
    """The stability pass's OLD arm = origin/main fbf181b7's tool + RULE 3. Verified byte-for-byte
    once against that commit's ep_detector (2026-10-02, the fix-round commit message); pinned
    here by hash so an edit to the copy fails, and structurally against the NEW prompt."""
    import hashlib
    import json as _json
    digest = hashlib.sha256((_json.dumps(R.OLD_CATALYST_TOOL, sort_keys=True)
                             + R.OLD_RULE_3).encode()).hexdigest()
    assert digest == "1a1de46d0bd14bbda656098afb4aafa4ff0aad9cbfc8ab7c16fc23484cf17de6"
    assert list(R.OLD_CATALYST_TOOL["input_schema"]["properties"]) == ["quality", "analysis"]
    new_props = dict(ep_detector._CATALYST_TOOL["input_schema"]["properties"])
    for k in mf.DEAL_FIELD_NAMES:
        new_props.pop(k)
    assert new_props["analysis"] == R.OLD_CATALYST_TOOL["input_schema"]["properties"]["analysis"]
    profile = {"companyName": "X", "sector": "Tech", "marketCap": 5e8}
    new = R.classifier_prompt("X", profile, "corpus")
    assert R.NEW_RULE_3 in new and R.OLD_RULE_3 not in new
    assert R.old_classifier_prompt("X", profile, "corpus") == new.replace(R.NEW_RULE_3, R.OLD_RULE_3)


def test_replay_parse_equals_the_code():
    for fields in ({"deal_role": "Target", "deal_status": "SIGNED", "deal_consideration": "cash"},
                   {"deal_role": "acquirer", "deal_status": "signed", "deal_consideration": "cash"},
                   {"deal_role": "target"}, None, {"deal_role": "none", "deal_status": "none",
                                                   "deal_consideration": "none"}):
        code = mf.deal_answer_from_fields(fields)
        assert R.parse_deal(fields) == (None if code is None else (code.role, code.status,
                                                                   code.consideration))


_GRID_GRADERS = [None, ("none", "none", "none"), ("buyer", "signed", "cash"),
                 ("target", "signed", "cash"), ("target", "signed", "stock"),
                 ("target", "proposed", "unknown"), ("shell", "signed", "stock")]
_PIN, _NOPIN = ("target", "signed", "cash"), ("target", "speculation", "none")
_GRID_HEADLINES = [[], [_PIN], [_NOPIN], [None], [_NOPIN, _PIN], [None, _NOPIN], [None, _PIN]]


def test_replay_live_verdict_equals_is_likely_ma_on_every_grid_cell():
    """The replay's rule IS the live rule: every (grade, grader answer, headline answers) cell
    through the real is_likely_ma (harness: Polygon + the model faked; None = the question
    raises = unanswered) gives the same verdict as R.live_verdict."""
    cells = 0
    for grade in (None, "mna", "strong"):
        for grader in _GRID_GRADERS:
            for heads in _GRID_HEADLINES:
                items, answers = [], {}
                for i, a in enumerate(heads):
                    title = f"Acme takeover report {i}"
                    items.append(H._item(title, published=f"2026-09-2{8 - i}T12:00:00Z"))
                    if a is not None:
                        answers[title] = H.Ans(*a)
                case = H.Case("ACME", "2026-09-30", "grid", False, "headline", "PASS",
                              catalyst_quality=grade, grader=H.Ans(*grader) if grader else None,
                              articles=tuple(items), headline=tuple(answers.items()))
                live = _run(H.run_new(case)).blocked
                replay, _why = R.live_verdict(grade, grader, list(heads))
                assert ("BLOCK" if live else "PASS") == replay, (grade, grader, heads)
                cells += 1
    assert cells == 3 * len(_GRID_GRADERS) * len(_GRID_HEADLINES)


def test_replay_live_verdict_names_the_rulings():
    assert R.live_verdict("mna", None, []) == ("BLOCK", "claude_classifier_unanswered")      # 5
    assert R.live_verdict("strong", ("buyer", "signed", "cash"), [_PIN]) == \
        ("PASS", "headline_pin_overruled_by_grader_deal")                                     # 7
    assert R.live_verdict("routine", ("none", "none", "none"), [_PIN]) == \
        ("BLOCK", "polygon_headline_model")                                                   # 7
    assert R.live_verdict(None, None, [None]) == ("PASS", "headline_unanswered")              # 4


def test_replay_rule_equals_the_code_on_every_cell():
    for r in mf.DEAL_ROLES:
        for s in mf.DEAL_STATUSES:
            for c in mf.DEAL_CONSIDERATIONS:
                assert R.deal_pins_price(r, s, c) == deal_pins_price(DealAnswer(r, s, c)), (r, s, c)


def test_replay_headline_prompt_equals_the_code():
    item = {"title": "T", "description": "D", "published_utc": "2026-09-01T00:00:00Z"}
    assert R.headline_prompt("X", "X Corp", item, "why") == mf.build_headline_prompt("X", "X Corp", item, "why")
    assert R.headline_prompt("X", None, {}, None) == mf.build_headline_prompt("X", None, {}, None)


def test_replay_classifier_prompt_equals_the_code():
    profile = {"companyName": "Forward Industries", "sector": "Tech", "marketCap": 2.5e9,
               "description": "d" * 400}
    corpus = "[SEC 8-K] " + "x" * 7000
    captured = []

    async def create(**kw):
        captured.append(kw["messages"][0]["content"])
        block = SimpleNamespace(type="tool_use", input={"quality": "routine", "analysis": "a"})
        return SimpleNamespace(content=[block], stop_reason="tool_use")
    with patch.object(ep_detector._get_claude(), "messages") as m, \
         patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
               new=AsyncMock(return_value=None)):
        m.create = create
        _run(ep_detector._classify_catalyst_claude("FWDI", [], profile, grounded_text=corpus))
    assert captured[0] == R.classifier_prompt("FWDI", profile, corpus)


def test_replay_candidate_selection_equals_the_code():
    items = [H._item(c.articles[0]["title"], description=c.articles[0]["description"],
                     ticker=c.ticker,
                     reasoning=(c.articles[0]["insights"] or [{}])[0].get("sentiment_reasoning"),
                     published=c.articles[0]["published_utc"])
             for c in H.CASES if c.articles]
    for t in ("SUNE", "QBTS", "KALV", "CLRO", "FRMI"):
        assert [(i["title"], mp) for i, mp, _k, _r in R.candidate_articles(t, items)] == \
               [(i["title"], mp) for i, mp, _k, _r in mf._candidate_articles(t, items)]


def _population_rows():
    import json as _json
    rows = []
    for line in _POPULATION.read_text(encoding="utf-8").splitlines():
        r = _json.loads(line)
        r["et_day"] = datetime.fromisoformat(r["created_at"]).astimezone(_ET).date()
        rows.append(r)
    return rows


def test_replay_groups_the_exported_population_into_its_ticker_days():
    days = R.build_ticker_days(_population_rows())
    fired = [td for td in days.values() if "mna_filter_fired" in td["events"]]
    assert len(fired) == 137          # the export's distinct fired ticker-days
    for key in R.LABELS:
        assert key in days, f"labelled {key} missing from the grouped population"
    ep = {k for k, td in days.items() if "ep" in td["detectors"]}
    # the live rule ORs two answers on EP: every EP day asks the grader AND the headline scan —
    # the three 10-01 headline blocks (IOVA, VKTX, RGTI) are EP days, so their grader is asked
    for k in [("ACVA", "2026-09-11"), ("FWDI", "2026-09-18"), ("IOVA", "2026-09-29"),
              ("VKTX", "2026-09-22"), ("RGTI", "2026-09-08"), ("SOUN", "2026-08-06")]:
        assert k in ep, k
    assert ("SUNE", "2026-06-08") not in ep and ("CLRO", "2026-07-02") not in ep
    sig = {k for k, td in days.items() if R.price_signature_only(td)}
    assert len(sig) == 11 and ("FBRX", "2026-08-04") in sig and not (sig & ep)
    assert len(ep) == 108
    assert all(R.old_decision(days[k]) == "BLOCK" for k in R.LABELS)


def test_replay_dry_run_end_to_end_makes_no_model_call_and_no_write(capsys):
    """The whole script on the exported population with every fetcher stubbed: it must group,
    pick arms, estimate, print one JSON line per ticker-day and never build a model client."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    rows = _population_rows()
    conn.fetch = AsyncMock(side_effect=[rows, [], []])
    tx_kwargs = []

    class _Tx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None

    def _transaction(**kw):
        tx_kwargs.append(kw)
        return _Tx()
    conn.transaction = _transaction
    conn.execute = AsyncMock(side_effect=AssertionError("the replay must never write"))
    with patch("agents.market_intelligence.db.get_pool", new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.collector.get_polygon_news", new=AsyncMock(return_value=[])), \
         patch("agents.market_intelligence.collector.get_alpaca_news", new=AsyncMock(return_value=[])), \
         patch("agents.market_intelligence.collector.get_ticker_details", new=AsyncMock(return_value={})), \
         patch("agents.market_intelligence.collector.get_fmp_profile", new=AsyncMock(return_value={})), \
         patch("agents.market_intelligence.collector.get_sec_recent_filings", new=AsyncMock(return_value=[])), \
         patch.object(R, "_benzinga", new=AsyncMock(return_value=[])), \
         patch("shared.llm_client.make_async_anthropic",
               side_effect=AssertionError("a dry run must not build a model client")):
        rc = _run(R.main(dry_run=True))
    assert rc == 0
    assert tx_kwargs == [{"readonly": True}], "the population read must run in a READ ONLY transaction"
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")]
    import json as _json
    recs = [_json.loads(ln) for ln in out]
    assert len(recs) == len(R.build_ticker_days(rows))
    assert all(r["new_decision"] is None or r["arm"] == "price_signature" for r in recs)
    by = {(r["ticker"], r["date"]): r for r in recs}
    # no shadow row → the 200-char audit excerpt is the only text, and says so
    assert by[("FWDI", "2026-09-18")]["corpus_source"] == "audit_excerpt_200_chars_only"
    assert by[("IOVA", "2026-09-29")]["arm"] == "ep: grader + headline"
    assert by[("SUNE", "2026-06-08")]["arm"] == "headline"


def test_replay_paid_path_with_a_fake_model_asks_both_questions_and_decides_live(capsys):
    """The paid pass end to end at $0: a FAKE model client answers by tool and ticker. Every EP
    day asks the grader AND the headline scan, the verdict is the live rule, the stability pass
    re-grades the non-deal sample with the OLD and NEW tool, and the summary carries the labelled
    acceptance, the MUST-SHOW block and the flips. No DB write, the adapter audit off."""
    import json as _json
    from datetime import date as _date
    from shared import llm_client
    from tests.conftest import make_mock_pool
    keep = {("ACVA", "2026-09-11"), ("FWDI", "2026-09-18"), ("IOVA", "2026-09-29"),
            ("SUNE", "2026-06-08"), ("FBRX", "2026-08-04")}
    rows = [r for r in _population_rows()
            if (r["summary"].split(" ")[0].split(":")[0], str(r["et_day"])) in keep]
    acva_head = "[SEC 8-K] Copart to acquire ACV Auctions for $19.00 per share in cash."
    shadow = [{"scan_date": _date(2026, 9, 11), "ticker": "ACVA", "grounded_len": len(acva_head),
               "grounded_head": acva_head,
               "claude_analysis": "a", "news_summary": "n", "live_quality_last": "mna"}]
    stab = [
        {"scan_date": _date(2026, 9, 30), "ticker": "XYZ", "grounded_len": 300,
         "grounded_head": "XYZ raised full-year revenue guidance 20% on record bookings. " * 4,
         "claude_analysis": "Revenue guidance raise.", "live_quality_first": "strong",
         "live_quality_last": "strong"},
        {"scan_date": _date(2026, 9, 29), "ticker": "DEALCO", "grounded_len": 300,
         "grounded_head": "DEALCO announced the acquisition of a smaller peer for $40M. " * 4,
         "claude_analysis": "Bolt-on acquisition.", "live_quality_first": "routine",
         "live_quality_last": "routine"},
        {"scan_date": _date(2026, 9, 11), "ticker": "ACVA", "grounded_len": 300,
         "grounded_head": "ACVA quarterly revenue beat. " * 10, "claude_analysis": "beat",
         "live_quality_first": "strong", "live_quality_last": "strong"},
    ]
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[rows, shadow, stab])

    class _Tx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None
    conn.transaction = lambda **kw: _Tx()
    conn.execute = AsyncMock(side_effect=AssertionError("the replay must never write"))

    iova_item = H._item(H._IOVA_VKTX_TITLE, published="2026-09-28T14:00:00Z")
    sune_item = H._item("Clean Energy Stocks Are Trending — Here's Why", ticker="SUNE",
                        description="one small cap exploded on a reverse merger",
                        reasoning="definitive reverse merger with Suniva",
                        published="2026-06-08T16:13:28Z")

    async def _news(ticker, lookback_days=14, on_or_before=None, limit=20):
        return {"IOVA": [iova_item], "SUNE": [sune_item]}.get(ticker, [])

    calls = []

    def _answer(tool, prompt):
        ticker = re.search(r"(?:Stock|Ticker): (\w+)", prompt).group(1)
        if tool["name"] == "classify_deal_headline":
            return {"IOVA": ("target", "speculation", "none"),
                    "SUNE": ("shell", "signed", "stock")}[ticker], None
        new_tool = "deal_role" in tool["input_schema"]["properties"]
        if not new_tool:
            return None, "routine"          # the OLD arm on XYZ → a flip vs the NEW 'strong'
        return {"ACVA": (("target", "signed", "cash"), "mna"),
                "FWDI": (("buyer", "proposed", "unknown"), "strong"),
                "IOVA": (("none", "none", "none"), "strong"),
                "XYZ": (("none", "none", "none"), "strong")}[ticker]

    async def create(**kw):
        tool, prompt = kw["tools"][0], kw["messages"][0]["content"]
        calls.append((tool["name"], "deal_role" in tool["input_schema"]["properties"],
                      re.search(r"(?:Stock|Ticker): (\w+)", prompt).group(1)))
        deal, quality = _answer(tool, prompt)
        inp = {}
        if quality:
            inp["quality"] = quality
        if deal:
            inp.update(deal_role=deal[0], deal_status=deal[1], deal_consideration=deal[2],
                       deal_counterparty="")
        inp["analysis" if tool["name"] == "classify_catalyst" else "note"] = "x"
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=inp)],
                               stop_reason="tool_use",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=300))
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with patch("agents.market_intelligence.db.get_pool", new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.collector.get_polygon_news", new=_news), \
         patch("agents.market_intelligence.collector.get_alpaca_news", new=AsyncMock(return_value=[])), \
         patch("agents.market_intelligence.collector.get_ticker_details", new=AsyncMock(return_value={})), \
         patch("agents.market_intelligence.collector.get_fmp_profile", new=AsyncMock(return_value={})), \
         patch("agents.market_intelligence.collector.get_sec_recent_filings", new=AsyncMock(return_value=[])), \
         patch.object(R, "_benzinga", new=AsyncMock(return_value=[])), \
         patch("shared.llm_models.GROUNDED_GRADE_MODEL", "claude-sonnet-5-5"), \
         patch.object(llm_client, "_audit_best_effort", new=llm_client._audit_best_effort), \
         patch("shared.llm_client.make_async_anthropic", return_value=fake_client):
        rc = _run(R.main(dry_run=False))
    assert rc == 0
    cap = capsys.readouterr()
    recs = [_json.loads(ln) for ln in cap.out.splitlines() if ln.startswith("{")]
    days = {(r["ticker"], r["date"]): r for r in recs if r["kind"] == "ticker_day"}
    assert days[("ACVA", "2026-09-11")]["new_decision"] == "BLOCK"
    assert days[("ACVA", "2026-09-11")]["new_why"] == "claude_deal_fields"
    assert days[("ACVA", "2026-09-11")]["corpus_source"] == "stored_grade_corpus"
    assert days[("FWDI", "2026-09-18")]["new_decision"] == "PASS"
    iova = days[("IOVA", "2026-09-29")]
    assert iova["new_decision"] == "PASS" and iova["grader_parsed"] == ["none", "none", "none"]
    assert [h["parsed"] for h in iova["headline_asked"]] == [["target", "speculation", "none"]]
    assert days[("SUNE", "2026-06-08")]["new_decision"] == "BLOCK"
    assert days[("SUNE", "2026-06-08")]["new_why"] == "polygon_headline_model"
    assert days[("FBRX", "2026-08-04")]["arm"] == "price_signature"
    stab_recs = [r for r in recs if r["kind"] == "grade_stability"]
    assert [r["ticker"] for r in stab_recs] == ["XYZ"], "deal rows and M&A days stay out"
    assert stab_recs[0]["old_quality"] == "routine" and stab_recs[0]["new_quality"] == "strong"
    assert stab_recs[0]["flip"] is True
    # both questions on every EP day; the stability pass asks the OLD and the NEW tool
    assert sorted(calls) == sorted([
        ("classify_catalyst", True, "ACVA"), ("classify_catalyst", True, "FWDI"),
        ("classify_catalyst", True, "IOVA"), ("classify_deal_headline", True, "IOVA"),
        ("classify_deal_headline", True, "SUNE"),
        ("classify_catalyst", False, "XYZ"), ("classify_catalyst", True, "XYZ")])
    err = cap.err
    assert "planned model calls (UPPER BOUND" in err and "7 = 3 grader + 2 headline + 2 stability" in err
    assert "claude-sonnet-5-5" in err and "$2.00 in / $10.00 out per MTok" in err
    assert "labelled acceptance: 4 of 4 as labelled" in err
    assert "MUST-SHOW" in err and "GRADE STABILITY (ruling 6): 1 non-deal rows" in err
    assert "1 quality flip(s)" in err and "XYZ" in err
    conn.execute.assert_not_called()


def test_replay_aborts_before_any_call_above_the_ceiling(capsys):
    """The priced whole path above $6 → nothing is called (the client is never built)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[_population_rows(), [], []])

    class _Tx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None
    conn.transaction = lambda **kw: _Tx()
    with patch("agents.market_intelligence.db.get_pool", new=AsyncMock(return_value=pool)), \
         patch("agents.market_intelligence.collector.get_polygon_news", new=AsyncMock(return_value=[])), \
         patch("agents.market_intelligence.collector.get_alpaca_news", new=AsyncMock(return_value=[])), \
         patch("agents.market_intelligence.collector.get_ticker_details", new=AsyncMock(return_value={})), \
         patch("agents.market_intelligence.collector.get_fmp_profile", new=AsyncMock(return_value={})), \
         patch("agents.market_intelligence.collector.get_sec_recent_filings", new=AsyncMock(return_value=[])), \
         patch.object(R, "_benzinga", new=AsyncMock(return_value=[])), \
         patch.object(R, "MAX_COST_USD", 0.01), \
         patch("shared.llm_client.make_async_anthropic",
               side_effect=AssertionError("no client above the ceiling")):
        rc = _run(R.main(dry_run=False))
    assert rc == 2 and "ABORT" in capsys.readouterr().err


def test_replay_grader_text_prefers_the_shadow_row_over_the_audit_excerpt():
    """Reviewer: `td.news_summary or shadow.news_summary` always took the 200-char audit excerpt.
    Order now: stored corpus → (rebuild +) the shadow row's news_summary with its claude_analysis
    appended → the audit excerpt ONLY when no shadow row exists."""
    td = {"ticker": "FWDI", "date": "2026-09-18", "news_summary": "AUDIT EXCERPT"}
    shadow = {"grounded_head": None, "news_summary": "SHADOW NARRATIVE", "claude_analysis": "GRADER WHY"}
    with patch("agents.market_intelligence.collector.get_sec_recent_filings",
               new=AsyncMock(return_value=[])), \
         patch.object(R, "_benzinga", new=AsyncMock(return_value=[])):
        text, src = _run(R.classifier_corpus(td, shadow, {}))
        assert (text, src) == ("SHADOW NARRATIVE\nGRADER WHY", "shadow_summary+analysis_only")
        assert "AUDIT EXCERPT" not in text
        text, src = _run(R.classifier_corpus(td, None, {}))
        assert (text, src) == ("AUDIT EXCERPT", "audit_excerpt_200_chars_only")
        full = {**shadow, "grounded_head": "STORED CORPUS", "grounded_len": 13}
        assert _run(R.classifier_corpus(td, full, {})) == ("STORED CORPUS", "stored_grade_corpus")
