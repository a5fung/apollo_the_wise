"""#505 CLOSENESS parent pick (operator 2026-10-09: "Yes") — which candidate parent the
nightly parent pass asks, and who is never asked.

Rank key: (-shared member stocks, -industry overlap, -word similarity, -parent size, name).
THE MINIMUM: industry overlap < 0.5 AND no shared member stock -> the pair is never asked
(no cooldown written). Industries unreadable -> the pre-closeness ranking, no minimum.

Every test here is RED on the pre-closeness engine (`propose_parent_candidates` had no
`industry_by_ticker`, `_read_parent_pass_industries` / `parent_industry_overlap` /
`parent_word_similarity` did not exist). The real-board cases use the committed 10-08
captures the replay ran on (docs/analysis/505_picker_replay_2026-10-09.md).

Run: pytest tests/test_505_closeness_pick.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.market_intelligence import theme_engine as te
from agents.market_intelligence.theme_merge_arm import pair_key

ROOT = Path(__file__).resolve().parent.parent
PULL = ROOT / "scripts" / "probes" / "_505" / "pull_2026-10-09"
IND_FILE = ROOT / "scripts" / "probes" / "_505_picker" / "q8_industry.out"


# ── real-board fixture (the replay's own captures) ──────────────────────────
@pytest.fixture(scope="module")
def real():
    board = json.loads((PULL / "q3_board.out").read_text())["rows"]
    for t in board:
        t["tickers"] = t["tickers"] or []
    eco = {r["name"]: r["e"] for r in json.loads((PULL / "q4_eco.out").read_text())}
    industry = {r["t"]: r["i"] for r in json.loads(IND_FILE.read_text()) if r.get("i")}
    cool = {pair_key(r["a"], r["b"]) for r in json.loads((PULL / "q2_cooldowns.out").read_text()) if r["live"]}
    return board, eco, industry, cool


def _asks_for(real, child_name, *, industries=True):
    """Tonight's ask for `child_name` on the 10-08 board, the child treated as childless
    (the replay's own method for the 9 live links)."""
    board, eco, industry, cool = real
    themes = [dict(t) for t in board]
    assert any(t["name"] == child_name for t in themes), f"{child_name!r} not on the captured board"
    for t in themes:
        if t["name"] == child_name:
            t["parent_theme"] = None
    out = te.propose_parent_candidates(
        themes, eco, cooldown_pairs=cool, cap=None,
        **({"industry_by_ticker": industry} if industries else {}),
    )
    return {r["child"]: r for r in out}.get(child_name)


@pytest.mark.parametrize("child,parent", [
    ("Liquid Biopsy & Molecular Cancer Diagnostics Testing", "Genomics & DNA Sequencing Tools"),
    ("Data Backup & Cyber Resiliency Software", "Network Security & Zero-Trust Edge"),
    ("Customer Engagement & Marketing/CX SaaS Platforms", "AI-Powered Enterprise Analytics & Intelligent Workflow SaaS"),
])
def test_real_parent_of_a_live_link_is_asked_first(real, child, parent):
    """Liquid Biopsy has 2 candidates; the other two are ticker-DISJOINT links the size-only
    fallback only found by being the sole candidate. All three must still be asked."""
    ask = _asks_for(real, child)
    assert ask is not None and ask["parent"] == parent, ask
    assert ask["industry_overlap"] is not None and ask["word_similarity"] is not None


def test_real_board_railroads_are_not_asked_about_tankers(real):
    """The replay's example of the weak fallback: 0 shared stocks, 0.0 industry overlap."""
    child = "Class I Railroad Freight Carriers"
    assert _asks_for(real, child, industries=False)["parent"] == "Crude & Product Tanker Shipping"  # today's ask
    ask = _asks_for(real, child)
    assert ask is None, f"railroads still asked about {ask and ask['parent']}"


def test_real_board_minimum_drops_weak_asks_and_never_adds_children(real):
    board, eco, industry, cool = real
    old = te.propose_parent_candidates(board, eco, cooldown_pairs=cool, cap=None)
    new = te.propose_parent_candidates(board, eco, cooldown_pairs=cool, cap=None, industry_by_ticker=industry)
    old_children, new_children = {r["child"] for r in old}, {r["child"] for r in new}
    assert new_children < old_children  # strictly fewer asked, none invented
    for r in new:
        assert r["shared_tickers"] > 0 or r["industry_overlap"] >= te.PARENT_PASS_MIN_INDUSTRY_OVERLAP


# ── synthetic: ranking ───────────────────────────────────────────────────────
def _t(name, tickers, stage="Mainstream", parent=None, description=""):
    return {"name": name, "tickers": list(tickers), "stage": stage, "score": 60.0,
            "parent_theme": parent, "source": "live", "description": description}


def _eco(*themes, code="E-X"):
    return {t["name"]: code for t in themes}


def _ind(**by_industry):
    """_ind(Banks=["A","B"], Oil=["C"]) -> {"A": "Banks", "B": "Banks", "C": "Oil"}"""
    return {tk: ind for ind, tks in by_industry.items() for tk in tks}


def test_industry_matched_smaller_theme_beats_bigger_unrelated_one():
    child = _t("Child", ["C1", "C2"])
    matched = _t("Matched smaller", ["M1", "M2", "M3"])                      # covers both child industries
    bigger = _t("Bigger half-match", ["B1", "B2", "B3", "B4", "B5", "B6"])   # covers one of two (0.5, passes)
    industry = _ind(Banks=["C1", "M1", "B1"], Insurance=["C2", "M2"], Other=["M3", "B2", "B3", "B4", "B5", "B6"])
    themes = [child, matched, bigger]
    eco = _eco(*themes)
    # today: biggest wins
    assert te.propose_parent_candidates(themes, eco, cap=None)[0]["parent"] == bigger["name"]
    new = te.propose_parent_candidates(themes, eco, cap=None, industry_by_ticker=industry)
    child_row = next(r for r in new if r["child"] == "Child")
    assert child_row["parent"] == matched["name"]
    assert child_row["industry_overlap"] == 1.0


def test_shared_stocks_still_rank_before_industry_overlap():
    child = _t("Child", ["C1", "C2", "C3"])
    shares = _t("Shares one stock", ["C1", "S1", "S2", "S3"])            # 1 shared, industry 1/3
    matches = _t("Matches industries", ["M1", "M2", "M3", "M4", "M5"])   # 0 shared, industry 1.0
    industry = _ind(A=["C1", "M1"], B=["C2", "M2"], C=["C3", "M3"], Z=["S1", "S2", "S3", "M4", "M5"])
    themes = [child, shares, matches]
    new = te.propose_parent_candidates(themes, _eco(*themes), cap=None, industry_by_ticker=industry)
    assert next(r for r in new if r["child"] == "Child")["parent"] == shares["name"]


def test_word_similarity_then_size_then_name_break_ties():
    child = _t("Child solar inverter makers", ["C1", "C2"], description="solar inverters and microinverters")
    near = _t("Solar inverter equipment", ["P1", "P2", "P3"], description="solar inverters")
    far = _t("Home appliance makers", ["Q1", "Q2", "Q3"], description="appliances")
    industry = _ind(Elec=["C1", "C2", "P1", "P2", "P3", "Q1", "Q2", "Q3"])  # identical overlap 1.0
    themes = [child, far, near]
    row = next(r for r in te.propose_parent_candidates(themes, _eco(*themes), cap=None, industry_by_ticker=industry)
               if r["child"] == child["name"])
    assert row["parent"] == near["name"] and row["word_similarity"] > 0
    # equal words too -> the BIGGER parent, then name
    a = _t("Aa", ["P1", "P2", "P3"]); b = _t("Bb", ["Q1", "Q2", "Q3", "Q4"]); c = _t("Cc", ["R1", "R2", "R3", "R4"])
    ch = _t("Child", ["C1", "C2"])
    ind2 = _ind(Elec=["C1", "C2", "P1", "P2", "P3", "Q1", "Q2", "Q3", "Q4", "R1", "R2", "R3", "R4"])
    ths = [ch, a, b, c]
    row = next(r for r in te.propose_parent_candidates(ths, _eco(*ths), cap=None, industry_by_ticker=ind2)
               if r["child"] == "Child")
    assert row["parent"] == "Bb"


# ── synthetic: THE MINIMUM ───────────────────────────────────────────────────
def test_candidate_below_half_overlap_with_no_shared_stock_is_skipped():
    child = _t("Railroads", ["R1", "R2"])
    tanker = _t("Tankers", ["T1", "T2", "T3"])
    industry = _ind(Rail=["R1", "R2"], Ship=["T1", "T2", "T3"])
    themes = [child, tanker]
    eco = _eco(*themes)
    assert te.propose_parent_candidates(themes, eco, cap=None)  # today: asked
    assert [r for r in te.propose_parent_candidates(themes, eco, cap=None, industry_by_ticker=industry)
            if r["child"] == "Railroads"] == []


def test_overlap_exactly_at_half_is_kept_and_a_shared_stock_overrides_the_minimum():
    child = _t("Child", ["C1", "C2"])
    half = _t("Half", ["H1", "H2", "H3"])
    industry = _ind(A=["C1", "H1"], B=["C2"], Z=["H2", "H3"])
    row = te.propose_parent_candidates([child, half], _eco(child, half), cap=None, industry_by_ticker=industry)
    assert [r["parent"] for r in row if r["child"] == "Child"] == ["Half"]  # 0.5 is not < 0.5
    # a shared stock keeps a pair whose industries do not line up at all
    child2 = _t("Child2", ["C1", "X1"])
    shares = _t("Shares", ["X1", "Y1", "Y2"])
    ind2 = _ind(A=["C1"], B=["X1"], Z=["Y1", "Y2"])
    rows = te.propose_parent_candidates([child2, shares], _eco(child2, shares), cap=None, industry_by_ticker=ind2)
    assert [r["parent"] for r in rows if r["child"] == "Child2"] == ["Shares"]


def test_skipped_candidate_falls_to_the_next_eligible_one():
    child = _t("Child", ["C1", "C2"])
    unrelated = _t("Unrelated big", ["U1", "U2", "U3", "U4", "U5"])
    related = _t("Related", ["R1", "R2", "R3"])
    industry = _ind(A=["C1", "C2", "R1", "R2", "R3"], Z=["U1", "U2", "U3", "U4", "U5"])
    themes = [child, unrelated, related]
    row = next(r for r in te.propose_parent_candidates(themes, _eco(*themes), cap=None, industry_by_ticker=industry)
               if r["child"] == "Child")
    assert row["parent"] == "Related"


def test_child_with_no_industry_data_is_asked_only_where_a_stock_is_shared():
    """Overlap is 0.0 when no child member has an industry (replay rule) - the minimum then
    leaves only pairs sharing a stock."""
    child = _t("Child", ["N1", "N2"])
    cand = _t("Cand", ["P1", "P2", "P3"])
    rows = te.propose_parent_candidates([child, cand], _eco(child, cand), cap=None,
                                        industry_by_ticker=_ind(Z=["P1", "P2", "P3"]))
    assert [r for r in rows if r["child"] == "Child"] == []


# ── unchanged: eligibility + cap + fail-safe ─────────────────────────────────
def test_eligibility_rules_unchanged_with_closeness_on():
    child = _t("Child", ["C1", "C2"])
    peers = {
        "other eco": _t("OtherEco", ["P1", "P2", "P3"]),
        "not broader": _t("NotBroader", ["P4", "P5"]),
        "fading": _t("Fading", ["P6", "P7", "P8"], stage="Fading"),
        "cooldown": _t("Cooled", ["P9", "P10", "P11"]),
    }
    industry = _ind(A=["C1", "C2", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11"])
    themes = [child, *peers.values()]
    eco = _eco(*themes)
    eco["OtherEco"] = "E-OTHER"
    rows = te.propose_parent_candidates(
        themes, eco, cooldown_pairs={pair_key("Child", "Cooled")}, cap=None, industry_by_ticker=industry)
    assert [r for r in rows if r["child"] == "Child"] == []


def test_nightly_cap_unchanged_with_closeness_on():
    themes = [_t(f"Child{i}", [f"C{i}a", f"C{i}b"]) for i in range(4)] + [
        _t("Big", [f"B{i}" for i in range(12)])]
    industry = _ind(A=[tk for t in themes for tk in t["tickers"]])
    eco = _eco(*themes)
    assert len(te.propose_parent_candidates(themes, eco, cap=None, industry_by_ticker=industry)) == 4
    assert len(te.propose_parent_candidates(themes, eco, cap=2, industry_by_ticker=industry)) == 2


@pytest.mark.parametrize("unreadable", [None, {}])
def test_industries_unreadable_gives_todays_ranking_and_no_minimum(unreadable):
    child = _t("Railroads", ["R1", "R2"])
    big = _t("Tankers", ["T1", "T2", "T3", "T4"])
    small = _t("Rail leasing", ["L1", "L2", "L3"], description="railroads")
    themes = [child, big, small]
    eco = _eco(*themes)
    legacy = te.propose_parent_candidates(themes, eco, cap=None)
    got = te.propose_parent_candidates(themes, eco, cap=None, industry_by_ticker=unreadable)
    assert [(r["child"], r["parent"]) for r in got] == [(r["child"], r["parent"]) for r in legacy]
    assert next(r for r in got if r["child"] == "Railroads")["parent"] == "Tankers"  # the old size pick
    assert next(r for r in got if r["child"] == "Railroads")["industry_overlap"] is None


# ── the armed night: I/O wiring ──────────────────────────────────────────────
def _wire(monkeypatch, *, industries):
    asked: list[tuple[str, str]] = []
    cooldowns: list = []

    async def fake_audit(*a, **kw):
        return None

    async def fake_pairs():
        return set()

    async def fake_cooldown(a, b, reason="", days=30, verdict="DISTINCT"):
        cooldowns.append((a, b, verdict))

    async def fake_adjudicate(child, parent, **kw):
        asked.append((child["name"], parent["name"]))
        return {"verdict": "PEERS", "reason": "x"}

    async def fake_industries(themes):
        return industries

    monkeypatch.setattr(te, "log_audit_event", fake_audit)
    monkeypatch.setattr(te, "get_merge_distinct_pairs", fake_pairs)
    monkeypatch.setattr(te, "add_merge_distinct_cooldown", fake_cooldown)
    monkeypatch.setattr(te, "adjudicate_containment_pair", fake_adjudicate)
    monkeypatch.setattr(te, "_read_parent_pass_industries", fake_industries)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: object())
    return asked, cooldowns


@pytest.mark.asyncio
async def test_all_skipped_child_is_not_asked_and_gets_no_cooldown(monkeypatch):
    child = _t("Railroads", ["R1", "R2"])
    tanker = _t("Tankers", ["T1", "T2", "T3"])
    asked, cooldowns = _wire(monkeypatch, industries=_ind(Rail=["R1", "R2"], Ship=["T1", "T2", "T3"]))
    out = await te._run_parent_pass([child, tanker], {}, enabled=True, eco_map=_eco(child, tanker))
    assert asked == [] and cooldowns == [] and out == []


@pytest.mark.asyncio
async def test_pass_hands_the_batched_industries_to_the_picker(monkeypatch):
    child = _t("Child", ["C1", "C2"])
    matched = _t("Matched smaller", ["M1", "M2", "M3"])
    bigger = _t("Bigger half-match", ["B1", "B2", "B3", "B4", "B5", "B6"])
    industry = _ind(Banks=["C1", "M1", "B1"], Insurance=["C2", "M2"], Other=["M3", "B2", "B3", "B4", "B5", "B6"])
    asked, _ = _wire(monkeypatch, industries=industry)
    await te._run_parent_pass([child, matched, bigger], {}, enabled=True,
                              eco_map=_eco(child, matched, bigger))
    assert ("Child", "Matched smaller") in asked and ("Child", "Bigger half-match") not in asked


@pytest.mark.asyncio
async def test_pass_with_unreadable_industries_asks_todays_pick_and_does_not_crash(monkeypatch):
    child = _t("Railroads", ["R1", "R2"])
    tanker = _t("Tankers", ["T1", "T2", "T3"])
    asked, _ = _wire(monkeypatch, industries=None)
    await te._run_parent_pass([child, tanker], {}, enabled=True, eco_map=_eco(child, tanker))
    assert asked == [("Railroads", "Tankers")]


@pytest.mark.asyncio
async def test_industry_reader_is_one_batch_and_fails_safe(monkeypatch):
    calls: list[list[str]] = []

    class _Conn:
        pass

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def fake_pool():
        return _Pool()

    async def fake_batch(conn, tickers):
        calls.append(list(tickers))
        return {"R1": "Rail"}

    monkeypatch.setattr(te, "get_pool", fake_pool)
    monkeypatch.setattr(te, "get_industries_for_tickers", fake_batch)
    themes = [_t("A", ["R1", "R2"]), _t("B", ["R2", "T1"]), _t("Gone", ["Z9"], stage="Retired")]
    assert await te._read_parent_pass_industries(themes) == {"R1": "Rail"}
    assert calls == [["R1", "R2", "T1"]]  # ONE query, de-duplicated, Retired members left out

    async def boom(conn, tickers):
        raise RuntimeError("db down")

    monkeypatch.setattr(te, "get_industries_for_tickers", boom)
    assert await te._read_parent_pass_industries(themes) is None

    async def empty(conn, tickers):
        return {}

    monkeypatch.setattr(te, "get_industries_for_tickers", empty)
    assert await te._read_parent_pass_industries(themes) is None


def test_scorers_match_the_replay_probe_copies():
    """The engine's scorers are the ones of record; the probe's pre-build copy must agree."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "closeness_probe", ROOT / "scripts" / "probes" / "_505_picker" / "closeness.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    a = _t("Liquid Biopsy & Molecular Cancer Diagnostics", ["A", "B"], description="cancer DNA diagnostics reporting")
    b = _t("Genomics & DNA Sequencing Tools", ["B", "C"], description="DNA sequencing tools and cancer diagnostics")
    ind = _ind(X=["A", "C"], Y=["B"])
    assert te.parent_word_similarity(a, b) == probe.parent_word_similarity(a, b) > 0
    assert te.parent_industry_overlap(a, b, ind) == probe.parent_industry_overlap(a, b, ind) == 1.0
    assert te.parent_word_similarity({"name": "", "description": ""}, b) == 0.0
    assert te.parent_industry_overlap({"tickers": ["Q"]}, b, {}) == 0.0
