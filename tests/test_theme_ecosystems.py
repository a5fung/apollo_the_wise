"""ADR 0032 Phase 1 — theme ecosystems read-model.

Covers the four Phase-1 components in theme_ecosystems.py:
  1. Taxonomy loader (repo YAML, ordering, fail-safe on missing/broken file,
     module cache).
  2. D3 ecosystem score — the pure formula, the ANTI-FRAGMENTATION property
     (same members as 1 blob vs 8 near-dup sub-themes must not out-score),
     the strong<5 thin floor, the depth term + cap, elite pairs, the
     rs_composite-not-score landmine.
  3. Assignment — keyword/exemplar fallback (deterministic), Haiku primary
     with abstain/error/invalid-code fallback, ensure_theme_ecosystems
     orchestration (dry-run vs execute, skip-mapped, audit events).
  4. /themes v2 render — ecosystems ranked by boosted score, sub-themes
     nested with global rank, Fading struck-through INSIDE its ecosystem,
     E-UNASSIGNED last, flat comp-ranked fallback when the mapping is empty
     (which also pins the Mainstream-buried-below-Nascent stage-order fix).

Plus the backfill script's dry-run-first contract on synthetic themes.
No DB, no network — db + anthropic surfaces are monkeypatched.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import theme_ecosystems as te
from agents.market_intelligence.theme_ecosystems import (
    E_UNASSIGNED,
    compute_ecosystem_scores,
    format_ecosystem_board,
    keyword_fallback_ecosystem,
)


@pytest.fixture(autouse=True)
def _fresh_taxonomy_cache():
    te.reset_taxonomy_cache()
    yield
    te.reset_taxonomy_cache()


# ═════════════════════════════════════════════════════════════════════════
# 1. Taxonomy loader
# ═════════════════════════════════════════════════════════════════════════

class TestTaxonomyLoader:
    def test_loads_repo_taxonomy_ordered(self):
        ecos = te.get_ecosystems()
        codes = te.get_ecosystem_codes()
        assert len(ecos) == 21, "operator-signed taxonomy: 20 buckets + E-UNASSIGNED"
        assert codes[0] == "E-CYBR"
        assert codes[-1] == E_UNASSIGNED
        m = te.get_ecosystem_map()
        assert "CRWD" in m["E-CYBR"]["exemplars"]
        assert m["E-AISEMI"]["name"] == "AI silicon & semiconductors"

    def test_missing_file_fail_safe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(te, "_PATH", tmp_path / "nope.yaml")
        assert te.get_ecosystems() == []
        assert te.get_ecosystem_codes() == []
        assert te.get_ecosystem_map() == {}

    def test_parse_failure_fail_safe(self, tmp_path, monkeypatch):
        bad = tmp_path / "theme_ecosystems.yaml"
        bad.write_text("ecosystems: [unclosed\n  - what: {", encoding="utf-8")
        monkeypatch.setattr(te, "_PATH", bad)
        assert te.get_ecosystems() == []   # logged, never raises

    def test_wrong_shape_fail_safe(self, tmp_path, monkeypatch):
        bad = tmp_path / "theme_ecosystems.yaml"
        bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
        monkeypatch.setattr(te, "_PATH", bad)
        assert te.get_ecosystems() == []

    def test_module_cache(self, tmp_path, monkeypatch):
        first = te.get_ecosystems()
        assert len(first) == 21
        # Point at a broken path — the cache must still serve the loaded copy.
        monkeypatch.setattr(te, "_PATH", tmp_path / "gone.yaml")
        assert len(te.get_ecosystems()) == 21
        te.reset_taxonomy_cache()
        assert te.get_ecosystems() == []


# ═════════════════════════════════════════════════════════════════════════
# 2. D3 ecosystem score (pure)
# ═════════════════════════════════════════════════════════════════════════

def _rs_data(members: dict[str, float]) -> dict[str, dict]:
    return {tk: {"rs_composite": v} for tk, v in members.items()}


def _theme(name: str, tickers: list[str], stage: str = "Mainstream", **kw) -> dict:
    return {"name": name, "tickers": tickers, "stage": stage, **kw}


class TestEcosystemScore:
    def test_basic_formula(self):
        members = {f"M{i}": 90.0 for i in range(12)}
        eco = {"E-X": [_theme("Blob", list(members))]}
        s = compute_ecosystem_scores(eco, _rs_data(members))["E-X"]
        assert s["raw"] == pytest.approx(90.0)
        assert s["strong"] == 12
        assert s["depth"] == 1
        assert s["boost"] == pytest.approx(0.04 * 1 + 0.015 * 12)  # 0.22
        assert s["boosted"] == pytest.approx(90.0 * 1.22)
        assert s["member_union"] == sorted(members)

    def test_anti_fragmentation_near_dups_cannot_outscore_blob(self):
        """THE acceptance property (ADR 0032 D3): the SAME members split into
        8 near-dup sub-themes must NOT out-score them as 1 sub-theme. The
        union base pins raw/strong; the depth near-dup dedup pins depth."""
        tks = [f"C{i}" for i in range(12)]
        rs = _rs_data({tk: 96.0 for tk in tks})

        blob = compute_ecosystem_scores({"E-CYBR": [_theme("Blob", tks)]}, rs)["E-CYBR"]
        # 8 near-duplicates: fragment i = the same cohort minus one member.
        frags = [_theme(f"Near-dup {i}", [t for t in tks if t != f"C{i}"])
                 for i in range(8)]
        frag = compute_ecosystem_scores({"E-CYBR": frags}, rs)["E-CYBR"]

        assert frag["member_union"] == blob["member_union"]      # union base
        assert frag["raw"] == pytest.approx(blob["raw"])
        assert frag["strong"] == blob["strong"]
        assert frag["depth"] == blob["depth"] == 1               # near-dups count once
        assert frag["boosted"] <= blob["boosted"] + 1e-9         # must NOT out-score
        assert frag["boosted"] == pytest.approx(blob["boosted"])

    def test_thin_floor_strong_below_5_no_boost(self):
        members = {f"T{i}": 99.0 for i in range(4)}   # 4 strong < floor of 5
        eco = {"E-X": [_theme("Tiny Elite", list(members))]}
        s = compute_ecosystem_scores(eco, _rs_data(members))["E-X"]
        assert s["strong"] == 4
        assert s["boost"] == 0.0
        assert s["boosted"] == pytest.approx(s["raw"])   # raw-only ranking

    def test_depth_term_real_substructure_boosts(self):
        """Genuinely DISTINCT sub-clusters (disjoint) raise depth → boosted —
        the intended Marios 'inherited from Themes' pop; capped at 0.30."""
        tks = [f"C{i}" for i in range(12)]
        rs = _rs_data({tk: 96.0 for tk in tks})
        one = compute_ecosystem_scores({"E": [_theme("Blob", tks)]}, rs)["E"]
        four = compute_ecosystem_scores(
            {"E": [_theme(f"Cluster {j}", tks[3 * j:3 * j + 3]) for j in range(4)]},
            rs)["E"]
        assert four["depth"] == 4 and one["depth"] == 1
        assert four["boosted"] > one["boosted"]
        assert four["boost"] == pytest.approx(0.30)      # 0.04*4 + 0.015*12 capped
        assert four["boosted"] <= four["raw"] * 1.30 + 1e-9

    def test_parent_child_subset_counts_toward_depth(self):
        """A small child INSIDE a big parent (the Phase-2 PARENT_CHILD shape,
        low Jaccard) must count — the dedup only collapses near-dups."""
        tks = [f"C{i}" for i in range(12)]
        rs = _rs_data({tk: 96.0 for tk in tks})
        s = compute_ecosystem_scores(
            {"E": [_theme("Parent", tks), _theme("Vuln-mgmt child", tks[:3])]},
            rs)["E"]
        assert s["depth"] == 2      # Jaccard 3/12 = 0.25 < 0.6 → both count

    def test_elite_pair_qualifies_for_depth(self):
        rs = _rs_data({"A": 95.0, "B": 95.0, "C": 95.0, "D": 85.0})
        elite = compute_ecosystem_scores(
            {"E": [_theme("Pair", ["A", "B"])]}, rs)["E"]
        assert elite["depth"] == 1
        not_elite = compute_ecosystem_scores(
            {"E": [_theme("Weak pair", ["C", "D"])]}, rs)["E"]   # min 85 < 90
        assert not_elite["depth"] == 0

    def test_fading_excluded_from_members(self):
        rs = _rs_data({"A": 90.0, "B": 90.0, "F1": 99.0, "F2": 99.0})
        s = compute_ecosystem_scores(
            {"E": [_theme("Live", ["A", "B"]),
                   _theme("Gone", ["F1", "F2"], stage="Fading")]}, rs)["E"]
        assert s["member_union"] == ["A", "B"]
        assert s["n_active_themes"] == 1

    def test_uses_rs_composite_never_stored_score(self):
        """The scale landmine: a bogus stored `score` on the theme dict must
        have zero effect — only member rs_composite drives raw."""
        members = {f"M{i}": 90.0 for i in range(6)}
        eco = {"E": [_theme("Promoted", list(members), score=5.0, rs_avg=1.0)]}
        s = compute_ecosystem_scores(eco, _rs_data(members))["E"]
        assert s["raw"] == pytest.approx(90.0)

    def test_unscored_members_dont_crash(self):
        s = compute_ecosystem_scores(
            {"E": [_theme("No data", ["X", "Y", "Z"])]}, {})["E"]
        assert s["raw"] == 0.0 and s["strong"] == 0 and s["depth"] == 0
        assert s["boosted"] == 0.0


# ═════════════════════════════════════════════════════════════════════════
# 3a. Keyword fallback (deterministic)
# ═════════════════════════════════════════════════════════════════════════

class TestKeywordFallback:
    def test_cyber_theme_maps_to_ecybr(self):
        code, score = keyword_fallback_ecosystem(
            "Cyber Vulnerability Management & Exposure Platforms",
            "Vulnerability management and exposure assessment platforms.",
            ["TENB", "QLYS", "RPD"],
        )
        assert code == "E-CYBR"
        assert score > 0

    def test_exemplar_overlap_alone_suffices(self):
        code, _ = keyword_fallback_ecosystem(
            "Momentum Leaders Group A", "", ["NVDA", "AVGO"])
        assert code == "E-AISEMI"

    def test_no_match_returns_unassigned(self):
        code, score = keyword_fallback_ecosystem(
            "Completely Mysterious Cohort", "Things going up.", ["ZZZT"])
        assert code == E_UNASSIGNED
        assert score == 0.0

    def test_description_noise_only_goes_to_triage(self):
        """A lone incidental description-stem hit (0.5) is below the assign
        threshold — mappings are sticky, so it must land in E-UNASSIGNED
        triage rather than stick a wrong bucket (live dry-run case: 'Life
        Science Tools…' scored 0.5 on E-CYBR via one description word)."""
        code, score = keyword_fallback_ecosystem(
            "Life Science Tools & Analytical Instruments",
            "Vendors expanding threat detection assays for research labs.",
            ["XXAA"])
        assert code == E_UNASSIGNED
        assert 0 < score < 2.0

    def test_single_name_stem_hit_clears_threshold(self):
        code, score = keyword_fallback_ecosystem(
            "Multifamily Apartment REITs", "", ["XXAA"])
        assert code == "E-REIT"
        assert score >= 2.0


# ═════════════════════════════════════════════════════════════════════════
# 3b. assign_theme_to_ecosystem — Haiku primary + fallbacks
# ═════════════════════════════════════════════════════════════════════════

_CYBER_THEME = {
    "name": "Cyber Vulnerability Management & Exposure Platforms",
    "description": "Vulnerability management and exposure platforms.",
    "tickers": ["TENB", "QLYS", "RPD"],
    "stage": "Nascent",
}


class _FakeBlock:
    type = "tool_use"

    def __init__(self, e_code):
        self.input = {"analysis_scratchpad": "reasoned first", "e_code": e_code}


class _FakeResp:
    def __init__(self, blocks):
        self.content = blocks
        self.usage = None


def _fake_client(monkeypatch, *, e_code=None, exc=None, no_tool=False):
    """Wire a fake anthropic client into theme_engine._get_anthropic_client
    (the plumbing assign reuses) + silence the spend meter."""
    from agents.market_intelligence import theme_engine, spend_tracker

    calls: list[dict] = []

    class _Messages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if exc is not None:
                raise exc
            blocks = [] if no_tool else [_FakeBlock(e_code)]
            return _FakeResp(blocks)

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: _Client())
    monkeypatch.setattr(spend_tracker, "log_anthropic_call_safe", AsyncMock())
    return calls


class TestAssignThemeToEcosystem:
    @pytest.mark.asyncio
    async def test_haiku_success(self, monkeypatch):
        calls = _fake_client(monkeypatch, e_code="e-cybr")   # pins normalization
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME)
        assert res["e_code"] == "E-CYBR"
        assert res["method"] == "haiku"
        assert res["llm_attempted"] is True
        # analysis_scratchpad-first house discipline is IN the tool schema
        tool = calls[0]["tools"][0]
        assert list(tool["input_schema"]["properties"])[0] == "analysis_scratchpad"
        assert tool["input_schema"]["required"][0] == "analysis_scratchpad"
        assert calls[0]["tool_choice"] == {"type": "tool",
                                           "name": "assign_theme_ecosystem"}

    @pytest.mark.asyncio
    async def test_haiku_abstain_falls_back_to_keyword(self, monkeypatch):
        _fake_client(monkeypatch, e_code=E_UNASSIGNED)
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME)
        assert res["e_code"] == "E-CYBR"      # keyword rescues the abstain
        assert res["method"] == "keyword"
        assert res["llm_attempted"] is True

    @pytest.mark.asyncio
    async def test_haiku_error_falls_back_to_keyword(self, monkeypatch):
        _fake_client(monkeypatch, exc=RuntimeError("api down"))
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME)
        assert res["e_code"] == "E-CYBR"
        assert res["method"] == "keyword"

    @pytest.mark.asyncio
    async def test_haiku_invalid_code_falls_back(self, monkeypatch):
        _fake_client(monkeypatch, e_code="E-NOPE")
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME)
        assert res["method"] == "keyword"

    @pytest.mark.asyncio
    async def test_no_tool_call_falls_back(self, monkeypatch):
        _fake_client(monkeypatch, no_tool=True)
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME)
        assert res["method"] == "keyword"

    @pytest.mark.asyncio
    async def test_use_llm_false_goes_straight_to_keyword(self):
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME, use_llm=False)
        assert res["e_code"] == "E-CYBR"
        assert res["method"] == "keyword"
        assert res["llm_attempted"] is False

    @pytest.mark.asyncio
    async def test_nothing_matches_returns_unassigned(self):
        res = await te.assign_theme_to_ecosystem(
            {"name": "Mysterious Cohort", "description": "?", "tickers": ["ZZZT"]},
            use_llm=False)
        assert res["e_code"] == E_UNASSIGNED
        assert res["method"] == "unassigned"

    @pytest.mark.asyncio
    async def test_empty_taxonomy_degrades_without_llm_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(te, "_PATH", tmp_path / "gone.yaml")
        res = await te.assign_theme_to_ecosystem(_CYBER_THEME)   # use_llm=True
        assert res["e_code"] == E_UNASSIGNED
        assert res["llm_attempted"] is False


# ═════════════════════════════════════════════════════════════════════════
# 3c. ensure_theme_ecosystems orchestration (+ backfill semantics)
# ═════════════════════════════════════════════════════════════════════════

def _mock_db(monkeypatch, existing=None):
    from agents.market_intelligence import db as db_mod
    mocks = {
        "get_all_theme_ecosystems": AsyncMock(return_value=dict(existing or {})),
        "get_sectors_batch": AsyncMock(return_value={}),
        "upsert_theme_ecosystem": AsyncMock(),
        "log_audit_event": AsyncMock(),
    }
    for name, m in mocks.items():
        monkeypatch.setattr(db_mod, name, m)
    return mocks


_SYNTH_THEMES = [
    dict(_CYBER_THEME),
    {"name": "Gold & Silver Royalty Streamers",
     "description": "Precious metals royalty and streaming companies.",
     "tickers": ["NEM", "AG"], "stage": "Mainstream"},
    {"name": "Mysterious Cohort", "description": "?",
     "tickers": ["ZZZT"], "stage": "Nascent"},
]


class TestEnsureThemeEcosystems:
    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self, monkeypatch):
        mocks = _mock_db(monkeypatch)
        results = await te.ensure_theme_ecosystems(
            _SYNTH_THEMES, dry_run=True, use_llm=False)
        assert len(results) == 3
        assert mocks["upsert_theme_ecosystem"].await_count == 0
        assert mocks["log_audit_event"].await_count == 0
        by_name = {r["theme_name"]: r for r in results}
        assert by_name[_CYBER_THEME["name"]]["e_code"] == "E-CYBR"
        assert by_name["Gold & Silver Royalty Streamers"]["e_code"] == "E-METAL"
        assert by_name["Mysterious Cohort"]["e_code"] == E_UNASSIGNED

    @pytest.mark.asyncio
    async def test_execute_upserts_and_audits(self, monkeypatch):
        mocks = _mock_db(monkeypatch)
        results = await te.ensure_theme_ecosystems(
            _SYNTH_THEMES, dry_run=False, use_llm=False)
        assert len(results) == 3
        assert mocks["upsert_theme_ecosystem"].await_count == 3
        args = mocks["upsert_theme_ecosystem"].await_args_list[0].args
        assert args == (_CYBER_THEME["name"], "E-CYBR", "keyword")
        # theme_ecosystem_assigned audit rows, one per assignment
        assert mocks["log_audit_event"].await_count == 3
        assert mocks["log_audit_event"].await_args_list[0].args[0] == \
            "theme_ecosystem_assigned"

    @pytest.mark.asyncio
    async def test_already_mapped_and_retired_skipped(self, monkeypatch):
        mocks = _mock_db(monkeypatch,
                         existing={_CYBER_THEME["name"]: "E-CYBR"})
        themes = _SYNTH_THEMES + [
            {"name": "Dead Theme", "tickers": [], "stage": "Retired"}]
        results = await te.ensure_theme_ecosystems(themes, use_llm=False)
        names = {r["theme_name"] for r in results}
        assert _CYBER_THEME["name"] not in names   # stable mapping — no re-assign
        assert "Dead Theme" not in names
        assert len(results) == 2
        assert mocks["upsert_theme_ecosystem"].await_count == 2

    @pytest.mark.asyncio
    async def test_sector_fetch_failure_degrades_loudly_not_fatally(self, monkeypatch):
        mocks = _mock_db(monkeypatch)
        from agents.market_intelligence import db as db_mod
        monkeypatch.setattr(db_mod, "get_sectors_batch",
                            AsyncMock(side_effect=RuntimeError("db hiccup")))
        results = await te.ensure_theme_ecosystems(
            _SYNTH_THEMES, use_llm=False)
        assert len(results) == 3                     # assignment still ran
        assert mocks["upsert_theme_ecosystem"].await_count == 3


class TestBackfillScript:
    @pytest.mark.asyncio
    async def test_dry_run_default_writes_nothing(self, monkeypatch):
        from scripts.backfill_theme_ecosystems import _run
        from agents.market_intelligence import db as db_mod
        mocks = _mock_db(monkeypatch)
        monkeypatch.setattr(db_mod, "get_active_themes",
                            AsyncMock(return_value=list(_SYNTH_THEMES)))
        rc = await _run(execute=False, keyword_only=True, stale_after_days=7)
        assert rc == 0
        assert mocks["upsert_theme_ecosystem"].await_count == 0

    @pytest.mark.asyncio
    async def test_execute_writes(self, monkeypatch):
        from scripts.backfill_theme_ecosystems import _run
        from agents.market_intelligence import db as db_mod
        mocks = _mock_db(monkeypatch)
        monkeypatch.setattr(db_mod, "get_active_themes",
                            AsyncMock(return_value=list(_SYNTH_THEMES)))
        rc = await _run(execute=True, keyword_only=True, stale_after_days=7)
        assert rc == 0
        assert mocks["upsert_theme_ecosystem"].await_count == 3


# ═════════════════════════════════════════════════════════════════════════
# 4. /themes v2 render
# ═════════════════════════════════════════════════════════════════════════

def _scored(name, comp, stage, tickers, delta=None):
    """Shape of one _compute_scored_themes entry."""
    return {"name": name, "stage": stage, "comp": comp, "rs_1m": comp,
            "rs_3m": comp, "rs_6m": comp, "delta": delta, "tickers": tickers,
            "n_stocks": len(tickers), "n_scored": len(tickers)}


def _board_fixture():
    """2 mapped ecosystems + 1 unmapped theme + 1 Fading cyber sub-theme.
    scored_themes is comp-desc, as _compute_scored_themes returns it."""
    cyber_a = ["TENB", "QLYS", "RPD"]
    cyber_b = ["CRWD", "PANW", "FTNT", "OKTA", "VRNS", "RBRK"]
    reit = ["PLD", "DHI", "LEN", "AMT"]
    mystery = ["AAA", "BBB", "CCC"]
    rs = {}
    rs.update({tk: {"rs_composite": 99.0} for tk in cyber_a})
    rs.update({tk: {"rs_composite": 96.0} for tk in cyber_b})
    rs.update({tk: {"rs_composite": 60.0} for tk in reit})
    rs.update({tk: {"rs_composite": 70.0} for tk in mystery})
    scored = [
        _scored("Cyber Vulnerability & Exposure Mgmt", 99.0, "Nascent", cyber_a),
        _scored("Network Security & Zero-Trust Edge", 96.0, "Mainstream", cyber_b,
                delta=0.5),
        _scored("Mysterious Cohort", 70.0, "Nascent", mystery),
        _scored("Data Center REITs", 60.0, "Nascent", reit),
    ]
    fading = [{"name": "Endpoint Security", "stage": "Fading",
               "tickers": ["S", "NET"]}]
    eco_map = {
        "Cyber Vulnerability & Exposure Mgmt": "E-CYBR",
        "Network Security & Zero-Trust Edge": "E-CYBR",
        "Endpoint Security": "E-CYBR",
        "Data Center REITs": "E-REIT",
        # "Mysterious Cohort" deliberately unmapped → E-UNASSIGNED
    }
    return scored, fading, rs, eco_map


class TestFormatEcosystemBoard:
    def test_ecosystems_ranked_and_nested(self):
        scored, fading, rs, eco_map = _board_fixture()
        text = "\n".join(format_ecosystem_board(scored, fading, rs, eco_map))

        # Ecosystem headers carry a rank prefix (1., 2., …); E-UNASSIGNED unnumbered.
        assert "*1. E-CYBR Cybersecurity*" in text
        assert "*2. E-REIT Real estate / REITs*" in text
        i_cybr = text.index("E-CYBR Cybersecurity")
        i_reit = text.index("E-REIT Real estate / REITs")
        i_un = text.index("*E-UNASSIGNED")
        assert i_cybr < i_reit < i_un        # boosted rank; unmapped pinned last

        # Header carries the raw → boosted (Δ) · names · RS80+ readout
        header = [l for l in text.splitlines() if "E-CYBR Cybersecurity" in l][0]
        assert "raw" in header and "→ boosted" in header
        assert "9 names" in header and "9 RS80+" in header

        # Sub-themes nested beneath with GLOBAL theme rank (comp order)
        assert "#1 " in text and "#2 " in text
        i_vuln = text.index("Cyber Vulnerability & Exposure Mgmt")
        i_net = text.index("Network Security & Zero-Trust Edge")
        assert i_cybr < i_vuln < i_net < i_reit

        # Stage is a per-line TAG — the old stage-group headers are gone
        assert "_[Mainstream]_" in text and "_[Nascent]_" in text
        assert "*MAINSTREAM*" not in text and "*NASCENT*" not in text

        # Member preview rides under the sub-theme line
        assert "TENB 99" in text

    def test_fading_struck_through_inside_ecosystem(self):
        scored, fading, rs, eco_map = _board_fixture()
        text = "\n".join(format_ecosystem_board(scored, fading, rs, eco_map))
        struck = te._strike("Endpoint Security")
        assert struck in text
        # INSIDE the E-CYBR block (between the CYBR and REIT headers)…
        assert text.index("E-CYBR") < text.index(struck) < text.index("E-REIT")
        # …NOT in a global footnote
        assert "_Fading:" not in text

    def test_unmapped_theme_lands_in_unassigned_section_last(self):
        scored, fading, rs, eco_map = _board_fixture()
        lines = format_ecosystem_board(scored, fading, rs, eco_map)
        text = "\n".join(lines)
        assert "Mysterious Cohort" in text
        assert text.index("Mysterious Cohort") > text.index("*E-UNASSIGNED")
        assert "awaiting mapping" in text

    def test_mainstream_strongest_ranks_above_nascent_noise(self):
        """The verified /themes bug: Mainstream rendered LAST, below Nascent
        2-member noise. v2 ranks by score — a dominant Mainstream theme must
        render above weaker Nascent themes in BOTH modes."""
        rs = {tk: {"rs_composite": v} for tk, v in
              [("A", 97.0), ("B", 96.0), ("C", 95.0), ("N1", 55.0), ("N2", 52.0)]}
        scored = [
            _scored("Dominant Mature Theme", 96.0, "Mainstream", ["A", "B", "C"]),
            _scored("Noise Pair", 53.0, "Nascent", ["N1", "N2"]),
        ]
        # Flat fallback (no mapping)
        flat = "\n".join(format_ecosystem_board(scored, [], rs, {}))
        assert flat.index("Dominant Mature Theme") < flat.index("Noise Pair")
        # Ecosystem mode
        eco = "\n".join(format_ecosystem_board(
            scored, [], rs,
            {"Dominant Mature Theme": "E-CYBR", "Noise Pair": "E-REIT"}))
        assert eco.index("Dominant Mature Theme") < eco.index("Noise Pair")

    def test_flat_fallback_when_mapping_empty(self):
        scored, fading, rs, _ = _board_fixture()
        lines = format_ecosystem_board(scored, fading, rs, eco_map={})
        text = "\n".join(lines)
        assert "E-CYBR" not in text          # no ecosystem headers pre-backfill
        assert "#1 " in text                  # still ranked
        assert "🔻 _Fading: Endpoint Security_" in text   # v1-style footnote
        # Ranked by comp: vuln (99) before REIT (60)
        assert text.index("Cyber Vulnerability") < text.index("Data Center REITs")

    def test_fading_only_ecosystem_renders_without_score_noise(self):
        rs = {"S": {"rs_composite": 96.0}}
        fading = [{"name": "Endpoint Security", "stage": "Fading", "tickers": ["S"]}]
        text = "\n".join(format_ecosystem_board(
            [], fading, rs, {"Endpoint Security": "E-CYBR"}))
        assert "all sub-themes Fading" in text
        assert te._strike("Endpoint Security") in text

    def test_empty_board_is_safe(self):
        assert format_ecosystem_board([], [], {}, {}) == []
        assert format_ecosystem_board([], [], {}, {"X": "E-CYBR"}) == []


# ═════════════════════════════════════════════════════════════════════════
# 5. /themes handler wiring (integration through _handle_theme_query)
# ═════════════════════════════════════════════════════════════════════════

class TestHandleThemeQueryV2:
    def _make_agent(self):
        from unittest.mock import patch
        from agents.market_intelligence.agent import MarketIntelligenceAgent
        from shared.models import AgentName
        with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
            agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
            agent.agent_name = AgentName.MARKET_INTELLIGENCE
        return agent

    @pytest.mark.asyncio
    async def test_themes_renders_ecosystem_board(self, monkeypatch):
        from unittest.mock import patch
        from shared.models import AgentRequest

        themes = [
            {"name": "Network Security & Zero-Trust Edge", "stage": "Mainstream",
             "tickers": ["CRWD", "PANW", "FTNT", "TENB", "QLYS", "RPD"],
             "theme_date": "2026-07-14"},
            {"name": "Data Center REITs", "stage": "Nascent",
             "tickers": ["PLD", "DHI"], "theme_date": "2026-07-14"},
        ]
        rs = {tk: {"rs_composite": 96.0, "rs_1m": 96.0, "rs_3m": 96.0,
                   "rs_6m": 96.0}
              for tk in ["CRWD", "PANW", "FTNT", "TENB", "QLYS", "RPD"]}
        rs.update({tk: {"rs_composite": 60.0, "rs_1m": 60.0, "rs_3m": 60.0,
                        "rs_6m": 60.0} for tk in ["PLD", "DHI"]})
        eco_map = {"Network Security & Zero-Trust Edge": "E-CYBR",
                   "Data Center REITs": "E-REIT"}

        agent = self._make_agent()
        with patch("agents.market_intelligence.agent.get_today_themes",
                   new=AsyncMock(return_value=themes)), \
                patch("agents.market_intelligence.agent.get_rs_for_tickers",
                      new=AsyncMock(return_value=rs)), \
                patch("agents.market_intelligence.agent.get_prior_theme_scores",
                      new=AsyncMock(return_value={})), \
                patch("agents.market_intelligence.agent.get_current_regime",
                      new=AsyncMock(return_value=None)), \
                patch("agents.market_intelligence.theme_ecosystems."
                      "load_ecosystem_assignments",
                      new=AsyncMock(return_value=eco_map)), \
                patch("agents.market_intelligence.theme_engine."
                      "evaluate_narrative_themes",
                      new=AsyncMock(return_value=[])):
            resp = await agent._handle_theme_query(
                AgentRequest(task="/themes", user_id=1, conversation_id="t"))

        assert resp.success, resp.error
        assert "2 Active Themes" in resp.result
        assert "*1. E-CYBR Cybersecurity*" in resp.result
        assert "*2. E-REIT" in resp.result
        assert resp.result.index("E-CYBR") < resp.result.index("E-REIT")
        # The Mainstream theme is NOT buried under a stage group anymore
        assert "*MAINSTREAM*" not in resp.result

    @pytest.mark.asyncio
    async def test_themes_survives_mapping_outage_flat(self):
        """load_ecosystem_assignments degrading to {} (DB down / pre-backfill)
        must yield the flat board, never an exception."""
        from unittest.mock import patch
        from shared.models import AgentRequest
        themes = [{"name": "Solo Theme", "stage": "Nascent",
                   "tickers": ["AAA"], "theme_date": "2026-07-14"}]
        rs = {"AAA": {"rs_composite": 70.0, "rs_1m": 70.0, "rs_3m": 70.0,
                      "rs_6m": 70.0}}
        agent = self._make_agent()
        with patch("agents.market_intelligence.agent.get_today_themes",
                   new=AsyncMock(return_value=themes)), \
                patch("agents.market_intelligence.agent.get_rs_for_tickers",
                      new=AsyncMock(return_value=rs)), \
                patch("agents.market_intelligence.agent.get_prior_theme_scores",
                      new=AsyncMock(return_value={})), \
                patch("agents.market_intelligence.agent.get_current_regime",
                      new=AsyncMock(return_value=None)), \
                patch("agents.market_intelligence.theme_ecosystems."
                      "load_ecosystem_assignments",
                      new=AsyncMock(return_value={})), \
                patch("agents.market_intelligence.theme_engine."
                      "evaluate_narrative_themes",
                      new=AsyncMock(return_value=[])):
            resp = await agent._handle_theme_query(
                AgentRequest(task="/themes", user_id=1, conversation_id="t"))
        assert resp.success, resp.error
        assert "Solo Theme" in resp.result
        assert "E-CYBR" not in resp.result
