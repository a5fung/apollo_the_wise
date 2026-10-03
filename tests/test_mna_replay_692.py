"""#692 — the prod replay script embeds the branch's question VERBATIM, and stays read-only.

scripts/probes/_692/replay_target_question.py is piped into the prod container BEFORE the #692
branch is deployed, so it carries COPIES of the new classifier prompt, both tool schemas, the
candidate pre-filter and the decision rule. A copy that drifts would replay a question the code
does not ask; these tests make the copy and the code one thing, and run the whole script on the
exported population with every fetcher stubbed ($0, no model client, no DB write).
"""
from __future__ import annotations

import asyncio
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
        "print('loaded', mod.MODEL, len(mod.LABELS))\n"
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                       cwd="/", timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    assert p.stdout.strip() == "loaded claude-sonnet-5-5 25"


def test_replay_schemas_and_lists_equal_the_code():
    assert R.CATALYST_TOOL == ep_detector._CATALYST_TOOL
    assert R.HEADLINE_TOOL == mf._HEADLINE_TOOL
    assert R.DEAL_FIELD_PROPERTIES == mf.DEAL_FIELD_PROPERTIES
    assert R.MNA_KEYWORDS == mf._MNA_KEYWORDS
    assert R.LITIGATION_PREFIXES == mf._SHAREHOLDER_LITIGATION_PREFIXES
    assert R.PINNING_CONSIDERATIONS == mf._PINNING_CONSIDERATIONS
    assert R.SHELL_ROLE_PINS == mf._SHELL_ROLE_PINS
    assert R.MODEL == "claude-sonnet-5-5" and R.MAX_CALLS == 200 and R.MAX_COST_USD == 5.00


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
    arms = {k: R.choose_arm(td) for k, td in days.items()}
    assert arms[("ACVA", "2026-09-11")] == "classifier"
    assert arms[("IOVA", "2026-09-29")] == "headline"
    assert arms[("CLRO", "2026-07-02")] == "headline"
    assert arms[("SUNE", "2026-06-08")] == "headline"
    # a #516 veto row means the classifier did NOT block — the headline block decides the arm
    assert arms[("RGTI", "2026-09-08")] == "headline"
    assert arms[("SOUN", "2026-08-06")] == "classifier"     # keyword_in_text blocked
    assert all(R.old_decision(days[k]) == "BLOCK" for k in R.LABELS)


def test_replay_dry_run_end_to_end_makes_no_model_call_and_no_write(capsys):
    """The whole script on the exported population with every fetcher stubbed: it must group,
    pick arms, estimate, print one JSON line per ticker-day and never build a model client."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    rows = _population_rows()
    conn.fetch = AsyncMock(side_effect=[rows, []])
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
    assert by[("FWDI", "2026-09-18")]["corpus_source"] == "stored_summary_only_200_chars"
