"""shared/llm_call_sites.py — the call-site key -> role map the #690 replay depends on.

A POPULATION gate, not a count: the map is REGENERATED from the source by the same AST scan
that wrote it (scripts/gen_llm_call_sites.py) and must equal the committed dict member for
member. A new or moved messages.create that nobody re-mapped fails here — otherwise its samples
would be recorded under no role (never replayed) or the wrong one (replayed on the wrong tier).

The named members below are the 2026-09-30 census (26 production request sites) — the cross-check
that the scan resolves the hard cases: judge_transport's four callers split across TWO roles, a
positional `model` through theme_merge_arm's wrapper, and a raw HAIKU default staying UNTRACKED.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))

import gen_llm_call_sites as gen  # noqa: E402
from shared.llm_call_sites import CALL_SITES  # noqa: E402
from shared.llm_models import RESOLVED_ROLES  # noqa: E402


def test_the_committed_map_is_what_the_source_says():
    fresh = gen.build_map()
    missing = sorted(set(fresh) - set(CALL_SITES))
    extra = sorted(set(CALL_SITES) - set(fresh))
    moved = sorted(k for k in set(fresh) & set(CALL_SITES) if fresh[k] != CALL_SITES[k])
    assert not (missing or extra or moved), (
        f"shared/llm_call_sites.py is stale — run python3 scripts/gen_llm_call_sites.py\n"
        f"  new call sites: {missing}\n  gone: {extra}\n  role changed: {moved}")


CENSUS = {
    # judge_transport's four callers — the live grade, the chart shadow and the management judge on
    # the opus judge role; the second opinion on its own (sonnet) role.
    "agents.market_intelligence.ep_detector:_judge_shadow": "JUDGE_MODEL",
    "agents.market_intelligence.chart_axis:grade_one": "JUDGE_MODEL",
    "agents.market_intelligence.mgmt_judge:manage_holistic": "JUDGE_MODEL",
    "agents.market_intelligence.judge_divergence:_run": "JUDGE_DIVERGENCE_MODEL",
    # theme_merge_arm._create_with_backoff: model passed POSITIONALLY by both callers
    "agents.market_intelligence.theme_merge_arm:adjudicate_containment_pair": "THEME_PARENT_ADJUDICATION_MODEL",
    "agents.market_intelligence.theme_merge_arm:adjudicate_merge_pair": "UNTRACKED",   # raw HAIKU pin
    # theme_engine._assignment_turn's two callers
    "agents.market_intelligence.theme_engine:_propose_assignment_batch": "THEME_MODEL",
    "agents.market_intelligence.theme_engine:judge_theme_fit": "THEME_MODEL",
    # aliases: `from shared.llm_models import X as _MODEL`, a function-local import
    "agents.market_intelligence.catalyst_materiality:judge_materiality_llm": "MATERIALITY_MODEL",
    "agents.market_intelligence.system_review:_synthesize": "SYSTEM_REVIEW_MODEL",
    "agents.market_intelligence.postmortem:generate_postmortem_narrative": "POSTMORTEM_MODEL",
    "agents.market_intelligence.ecosystem_discovery:propose_ecosystem_via_llm": "SYNTHESIS_MODEL",
    "agents.market_intelligence.ep_detector:_classify_catalyst_claude": "GROUNDED_GRADE_MODEL",
    # the never-captured privacy roles still map (capture excludes them by role)
    "core.orchestrator:_tool_use_loop": "ORCHESTRATOR_MODEL",
    "core.context:_summarize_messages": "COMPRESSION_MODEL",
    "channels.telegram:_check_claude": "HEALTHCHECK_MODEL",
}


@pytest.mark.parametrize("key,role", sorted(CENSUS.items()))
def test_census_member(key, role):
    assert CALL_SITES.get(key) == role


def test_every_role_in_the_map_is_a_tracked_role_or_untracked():
    assert set(CALL_SITES.values()) <= set(RESOLVED_ROLES) | {"UNTRACKED"}


def test_the_transport_and_its_canary_are_not_call_sites():
    assert not any(k.startswith("shared.llm_client:") for k in CALL_SITES)
    assert not any(k.startswith("agents.market_intelligence.judge_transport:") for k in CALL_SITES)


# ── the generator fails LOUDLY rather than guessing ──────────────────────────

def _fake_repo(tmp_path, source: str) -> Path:
    pkg = tmp_path / "agents" / "fake"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return tmp_path


def test_one_key_with_two_roles_is_an_error(tmp_path):
    repo = _fake_repo(tmp_path, """
        from shared.llm_models import THEME_MODEL, JUDGE_MODEL
        async def both(client):
            await client.messages.create(model=THEME_MODEL, max_tokens=1, messages=[])
            await client.messages.create(model=JUDGE_MODEL, max_tokens=1, messages=[])
    """)
    with pytest.raises(gen.GenError, match="several roles"):
        gen.build_map(repo)


def test_an_unresolvable_model_is_an_error(tmp_path):
    repo = _fake_repo(tmp_path, """
        async def mystery(client, pick):
            await client.messages.create(model=pick, max_tokens=1, messages=[])
    """)
    with pytest.raises(gen.GenError, match="no default"):
        gen.build_map(repo)


def test_aliases_and_defaults_resolve(tmp_path):
    repo = _fake_repo(tmp_path, """
        from shared.llm_models import SYNTHESIS_MODEL as _M, effective_model, HAIKU
        _LOCAL = _M
        async def a(client):
            await client.messages.create(model=_LOCAL, max_tokens=1, messages=[])
        async def b(client, model=effective_model("JUDGE_DIVERGENCE_MODEL")):
            kw = dict(model=model, max_tokens=1, messages=[])
            await client.messages.create(**kw)
        async def c(client, model: str = HAIKU):
            await client.messages.create(model=model, max_tokens=1, messages=[])
    """)
    assert gen.build_map(repo) == {
        "agents.fake.mod:a": "SYNTHESIS_MODEL",
        "agents.fake.mod:b": "JUDGE_DIVERGENCE_MODEL",
        "agents.fake.mod:c": "UNTRACKED",
    }
