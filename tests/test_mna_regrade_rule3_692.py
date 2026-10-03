"""#692 ruling 2 — the paid RULE 3 regrade script (scripts/probes/_692/regrade_rule3.py) stays a
faithful, self-contained copy of the code: its NEW prompt + tool ARE the branch grader's, its OLD
copy is the 10-02 branch's (hash-pinned), its row lists are the replay's, a dry run prices the
whole path from pricing_for and makes no model call, the paid path asks exactly two calls per row,
and above the ceiling nothing is called."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import ep_detector
from agents.market_intelligence import ma_filter as mf

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "probes" / "_692" / "regrade_rule3.py"
_PIN_REPLAY = _REPO / "scripts" / "probes" / "_692" / "replay_pin_2026-10-03.jsonl"
_REPLAY_1002 = _REPO / "scripts" / "probes" / "_692" / "replay_2026-10-02.jsonl"


def _load():
    spec = importlib.util.spec_from_file_location("regrade_rule3_692", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load()


def _run(coro):
    return asyncio.run(coro)


def test_loads_with_every_repo_package_unimportable():
    probe = (
        "import importlib.abc, importlib.util, sys\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('agents', 'shared', 'core', 'scripts'):\n"
        "            raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, Block())\n"
        f"spec = importlib.util.spec_from_file_location('probe', {str(_SCRIPT)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "print('loaded', mod.MAX_COST_USD, mod.MAX_CALLS, len(mod.ROWS_NOMINATED), len(mod.ROWS_STABILITY))\n"
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd="/", timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    assert p.stdout.strip() == "loaded 3.0 120 18 30"


def test_new_arm_is_the_re_tied_prompt_that_ran_on_2026_10_03():
    """This script RAN on main on 2026-10-03 ($0.89) with the re-tied RULE 3 (ruling 2). Ruling 2
    was reverted the same night (#692b: S19 of the ADR 0030 corpus requires a definitive all-cash
    buyout target to grade 'mna'), so the NEW arm is pinned here by hash to what ran — it is a
    record, no longer the live grader (tests/test_mna_merit_grade_692b.py pins the live one)."""
    digest = hashlib.sha256((json.dumps(G.NEW_CATALYST_TOOL, sort_keys=True) + G.NEW_RULE_3).encode()).hexdigest()
    assert digest == "f7d4301b20b77b4614aed49f3a81defd657b094dbb01b7659bd5e88e543d293d"
    assert G.DEAL_FIELD_PROPERTIES == mf.DEAL_FIELD_PROPERTIES
    assert "quality_if_no_deal" not in G.NEW_CATALYST_TOOL["input_schema"]["properties"]


def test_old_copy_is_the_10_02_branch_verbatim():
    """Pinned by hash to commit f666f9e9's replay copy (CATALYST_TOOL + NEW_RULE_3 there), which
    tests/test_mna_replay_692.py had proven equal to that branch's grader."""
    digest = hashlib.sha256((json.dumps(G.OLD_CATALYST_TOOL, sort_keys=True) + G.OLD_RULE_3).encode()).hexdigest()
    assert digest == "a21ffeb6dd43971d327180c4667b594cc4b81fb480d639d6ee3feefed25c6260"
    assert G.old_prompt("X", {}, "c") == G.new_prompt("X", {}, "c").replace(G.NEW_RULE_3, G.OLD_RULE_3)
    flat_old, flat_new = " ".join(G.OLD_RULE_3.split()), " ".join(G.NEW_RULE_3.split())
    assert "deal_role is 'target' and deal_consideration" in flat_old      # the 10-02 rule graded targets
    assert "deal_role is 'target' and deal_consideration" not in flat_new
    assert "deal_role is 'shell' AND deal_status is 'signed'" in flat_new    # shell-only now


def test_row_lists_are_the_replays():
    nominated = [(r["ticker"], r["date"]) for r in map(json.loads, _PIN_REPLAY.read_text().splitlines())
                 if r.get("nominated") and r.get("ep_day")]
    assert list(G.ROWS_NOMINATED) == nominated
    stability = [(r["ticker"], r["date"]) for r in map(json.loads, _REPLAY_1002.read_text().splitlines())
                 if r.get("kind") == "grade_stability"]
    assert list(G.ROWS_STABILITY) == stability
    assert G.parse_deal({"deal_role": "Target", "deal_status": "SIGNED", "deal_consideration": "cash"}) == \
        ("target", "signed", "cash")


def _fake_pool(shadow_rows, audit_rows):
    conn = SimpleNamespace()

    async def fetch(sql, *args):
        return shadow_rows if "mi_catalyst_tier_shadow" in sql else audit_rows
    conn.fetch = fetch

    class _Tx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False
    conn.transaction = lambda readonly=False: _Tx()

    class _Acq:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *a):
            return False
    pool = SimpleNamespace(acquire=lambda: _Acq())
    return pool


def _shadow(ticker, day, text, q="routine"):
    return {"scan_date": day, "ticker": ticker, "grounded_head": text, "grounded_len": len(text),
            "claude_analysis": "a", "news_summary": "s", "live_quality_first": q, "live_quality_last": q}


def _patches(shadow_rows, audit_rows, client=None):
    from contextlib import ExitStack
    st = ExitStack()
    st.enter_context(patch("agents.market_intelligence.db.get_pool",
                           new=AsyncMock(return_value=_fake_pool(shadow_rows, audit_rows))))
    st.enter_context(patch("agents.market_intelligence.collector.get_fmp_profile",
                           new=AsyncMock(return_value={"companyName": "X", "sector": "S", "marketCap": 1e9})))
    st.enter_context(patch("agents.market_intelligence.collector.get_sec_recent_filings",
                           new=AsyncMock(return_value=[])))
    st.enter_context(patch.object(G, "_benzinga", new=AsyncMock(return_value=[])))
    if client is not None:
        from shared import llm_client
        st.enter_context(patch.object(llm_client, "make_async_anthropic", return_value=client))
    return st


def test_dry_run_prices_the_whole_path_and_makes_no_call(capsys):
    shadow_rows = [_shadow(t, d, "corpus " * 200) for t, d in list(G.ROWS_NOMINATED) + list(G.ROWS_STABILITY)]
    with _patches(shadow_rows, []):
        rc = _run(G.main(dry_run=True))
    assert rc == 0
    out, err = capsys.readouterr()
    recs = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    assert len(recs) == 48 and all(r["old_quality"] is None for r in recs)
    assert "planned model calls: 96 = 2 (OLD + NEW prompt) x 48 rows" in err
    assert "cost per call = ((prompt_chars / 3.5 + 700 tool tokens)" in err
    assert "ESTIMATED whole path $" in err and "dry run: no model call made." in err
    est = float(err.split("ESTIMATED whole path $", 1)[1].split()[0])
    assert 0 < est < 3.0


def test_above_the_ceiling_nothing_is_called(capsys):
    shadow_rows = [_shadow(t, d, "corpus " * 200) for t, d in list(G.ROWS_NOMINATED) + list(G.ROWS_STABILITY)]
    calls = []

    async def create(**kw):
        calls.append(kw)
        raise AssertionError("must not be called")
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with _patches(shadow_rows, [], client), patch.object(G, "MAX_COST_USD", 0.0001):
        rc = _run(G.main(dry_run=False))
    assert rc == 2 and calls == []
    out, err = capsys.readouterr()
    assert "ABORT" in err and all("aborted before any call" in ln for ln in out.splitlines() if ln.strip())


def test_paid_path_asks_old_and_new_on_the_same_text_and_reports_flips(capsys):
    rows = [("PD", "2026-05-29"), ("VECO", "2026-10-02")]
    shadow_rows = [_shadow("PD", "2026-05-29", "PagerDuty agreed to be taken private at a premium", "mna"),
                   _shadow("VECO", "2026-10-02", "a routine quarter", "routine")]
    seen = []

    async def create(**kw):
        prompt = kw["messages"][0]["content"]
        seen.append((kw["tools"][0]["input_schema"]["properties"]["quality"]["description"][-40:], prompt))
        old = G.OLD_RULE_3 in prompt
        pd = "PagerDuty" in prompt
        q = "mna" if (old and pd) else ("strong" if pd else "routine")
        block = SimpleNamespace(type="tool_use", input={
            "quality": q, "deal_role": "target" if pd else "none", "deal_status": "signed" if pd else "none",
            "deal_consideration": "unknown" if pd else "none", "deal_counterparty": "", "analysis": "x"})
        return SimpleNamespace(content=[block], stop_reason="tool_use",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with _patches(shadow_rows, [], client), patch.object(G, "ROWS_NOMINATED", (rows[0],)), \
         patch.object(G, "ROWS_STABILITY", (rows[1],)):
        rc = _run(G.main(dry_run=False))
    assert rc == 0 and len(seen) == 4
    out, err = capsys.readouterr()
    recs = {r["ticker"]: r for r in map(json.loads, (ln for ln in out.splitlines() if ln.strip()))}
    assert recs["PD"]["old_quality"] == "mna" and recs["PD"]["new_quality"] == "strong" and recs["PD"]["flip"]
    assert recs["VECO"]["flip"] is False
    assert "NOMINATED: 1 rows" in err and "1 flip(s)" in err and "STABILITY: 1 rows" in err and "0 flip(s)" in err
    assert "the rule holds on this sample" in err
    # the same text went to both prompts for each row
    texts = [p.split("Recent news", 1)[1][:80] for _, p in seen]
    assert texts[0] == texts[1] and texts[2] == texts[3]
