"""#505 — parent-child holds on EVERY discovery path (operator 2026-07-27:
"parent child relationship must work regardless on how themes are discovered,
if not then it's broken").

What is pinned here, all RED on the pre-#505 engine:
  * `propose_parent_candidates` — the pure trigger the probe and the armed
    night share: same-ecosystem, broader parent, no cooldown, no Arm-B
    territory, no cycle, catch-all / Fading / Retired never on either side,
    priority = shared tickers > shared name tokens > parent breadth, cap.
  * `_run_parent_pass` — toggle OFF returns [] before ANY I/O (byte-identical
    engine); ON: PARENT_CHILD links (source-blind — a `shadow_promoted` theme
    is parented exactly like a `live` one), DISTINCT → 30d cooldown, MERGE →
    signal only (never executed), inverted → no link, ERROR → fail-open, a
    raising adjudicator never breaks the pass, one RAN heartbeat per run.
  * `run_theme_engine` wiring order: after Arm B, before `_restore_sub_theme_links`.
  * `theme_ecosystems.containment_parent` / `resolve_theme_parent` — the
    overloaded-column split (a Retired successor pointer is NOT a parent) and
    ruling (5): child / root-under-ecosystem / catch-all.
  * `format_ecosystem_board` renders a child NESTED under its parent (↳) — the
    relationship's first operator surface; `_compute_scored_themes` carries
    `parent_theme` through so the board has something to nest.
  * The DB toggle fails CLOSED.

Run: pytest tests/test_505_parent_pass.py -v
"""
from __future__ import annotations

import inspect

import pytest

from agents.market_intelligence import theme_engine as te
from agents.market_intelligence import theme_ecosystems as tx
from agents.market_intelligence.theme_merge_arm import pair_key


# ── Fixtures ────────────────────────────────────────────────────────────────
def _t(name, tickers, stage="Mainstream", parent=None, source="live", score=60.0):
    return {"name": name, "tickers": list(tickers), "stage": stage, "score": score,
            "parent_theme": parent, "source": source, "description": f"{name} thesis"}


BROAD = "Life Insurance & Annuity Providers"
NARROW = "Annuity-Focused Insurers"
OTHER_ECO = "Regional Bank Recovery"


def _board():
    return [
        _t(BROAD, ["MET", "PRU", "LNC", "PFG", "EQH", "CRBG"]),
        _t(NARROW, ["CRBG", "EQH", "JXN"]),          # 2 shared with BROAD
        _t(OTHER_ECO, ["KEY", "CFG", "FITB", "HBAN", "RF"]),
    ]


ECO = {BROAD: "E-INS", NARROW: "E-INS", OTHER_ECO: "E-BANKFIN"}


def _wire(monkeypatch, verdict_by_child: dict, *, raise_for: set[str] = frozenset()):
    """Fake adjudicator keyed by the CHILD's name; captured audits + cooldowns;
    no DB (cooldown read + Arm-B territory are injected as empty)."""
    events: list[tuple[str, str, str]] = []
    cooldowns: list[tuple[tuple[str, str], str, int]] = []

    async def fake_audit(event_type, summary, detail=None):
        events.append((event_type, summary, detail or ""))

    async def fake_get_pairs():
        return set()

    async def fake_add_cooldown(a, b, reason="", days=30, verdict="DISTINCT"):
        cooldowns.append((pair_key(a, b), verdict, days))

    async def fake_adjudicate(theme_a, theme_b, **kw):
        # parent = A, child = B (Route A's convention)
        if theme_b["name"] in raise_for:
            raise RuntimeError("adjudicator exploded")
        return verdict_by_child[theme_b["name"]]

    monkeypatch.setattr(te, "log_audit_event", fake_audit)
    monkeypatch.setattr(te, "get_merge_distinct_pairs", fake_get_pairs)
    monkeypatch.setattr(te, "add_merge_distinct_cooldown", fake_add_cooldown)
    monkeypatch.setattr(te, "adjudicate_merge_pair", fake_adjudicate)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: object())
    return events, cooldowns


# ── propose_parent_candidates (pure trigger) ────────────────────────────────
def test_candidate_is_same_ecosystem_broader_parent_with_why():
    cands = te.propose_parent_candidates(_board(), ECO)
    assert [(c["child"], c["parent"]) for c in cands] == [(NARROW, BROAD)]
    c = cands[0]
    assert c["shared_tickers"] == 2 and c["e_code"] == "E-INS"
    assert c["child_members"] == 3 and c["parent_members"] == 6
    assert "E-INS" in c["why"] and "shared tickers 2" in c["why"]


def test_broad_theme_is_never_a_child_of_a_narrower_one():
    """OTHER_ECO is alone in its ecosystem; BROAD is the only E-INS theme wider
    than NARROW — so BROAD itself must get no candidate (nothing broader)."""
    children = {c["child"] for c in te.propose_parent_candidates(_board(), ECO)}
    assert BROAD not in children and OTHER_ECO not in children


def test_catch_all_and_unmapped_themes_are_roots_not_candidates():
    board = _board() + [_t("Mystery Cohort", ["AAA", "BBB", "CCC"]),
                        _t("Mystery Blob", ["AAA", "BBB", "CCC", "DDD", "EEE"])]
    eco = dict(ECO, **{"Mystery Cohort": tx.E_UNASSIGNED, "Mystery Blob": tx.E_UNASSIGNED})
    children = {c["child"] for c in te.propose_parent_candidates(board, eco)}
    assert children == {NARROW}          # the two E-UNASSIGNED themes never pair


def test_fading_and_retired_never_on_either_side():
    board = _board()
    board[0]["stage"] = "Fading"          # BROAD fading → NARROW has no parent tonight
    assert te.propose_parent_candidates(board, ECO) == []
    board = _board()
    board[0]["stage"] = "Retired"
    board[0]["tickers"] = []
    assert te.propose_parent_candidates(board, ECO) == []
    board = _board()
    board[1]["stage"] = "Fading"          # a fading child is left alone
    assert te.propose_parent_candidates(board, ECO) == []


def test_live_cooldown_pair_is_skipped():
    cands = te.propose_parent_candidates(_board(), ECO, cooldown_pairs={pair_key(NARROW, BROAD)})
    assert cands == []


def test_arm_b_territory_pair_is_skipped():
    cands = te.propose_parent_candidates(_board(), ECO, arm_b_pairs={pair_key(BROAD, NARROW)})
    assert cands == []


def test_child_whose_best_pair_is_arm_b_territory_waits_not_second_best():
    """The 2026-09-26 dry-run case: the ONE ticker-contained child on the board
    ('Small Satellite…' inside 'Space Economy…', containment 1.00) is Arm-B
    territory. The child must be DEFERRED — never offered the zero-signal
    fallback ('Defense Intelligence…') instead."""
    space = _t("Space Economy: Satellite Communications & Launch Services",
               ["ASTS", "RKLB", "PL", "SATS", "IRDM", "VSAT", "GSAT", "SPIR", "BKSY"])
    small = _t("Small Satellite & Space Services Rotation", ["PL", "SPIR", "BKSY", "SATS", "IRDM"],
               source="shadow_promoted")
    defense_it = _t("Defense Intelligence & Cybersecurity IT Contractors",
                    ["BAH", "CACI", "SAIC", "LDOS", "PSN", "KTOS", "MRCY"])
    eco = {t["name"]: "E-DEF" for t in (space, small, defense_it)}
    board = [space, small, defense_it]

    def ask_for(cands):
        return {c["child"]: c["parent"] for c in cands}.get(small["name"])

    # nothing excluded → the ticker-contained parent wins outright
    assert ask_for(te.propose_parent_candidates(board, eco)) == space["name"]
    # Arm B owns (space, small) → the child waits; defense_it is NOT offered
    assert ask_for(te.propose_parent_candidates(
        board, eco, arm_b_pairs={pair_key(space["name"], small["name"])})) is None
    # …but a COOLDOWN on that pair (Arm B already ruled DISTINCT) moves on to the next candidate
    assert ask_for(te.propose_parent_candidates(
        board, eco, cooldown_pairs={pair_key(space["name"], small["name"])})) == defense_it["name"]


def test_already_parented_child_is_not_re_asked():
    board = _board()
    board[1]["parent_theme"] = BROAD
    assert te.propose_parent_candidates(board, ECO) == []


def test_no_cycles_but_chains_allowed():
    """materials → components → primes was seen live (2026-07-27). A chain is
    fine; a candidate whose ancestor chain already contains the child is not."""
    primes = _t("Defense Prime Contractors", ["LMT", "NOC", "GD", "RTX", "LHX", "HII"])
    comps = _t("Defense Precision Components", ["HEI", "TDG", "DCO", "LMT"], parent=primes["name"])
    mats = _t("Aerospace Structural Materials", ["ATI", "HWM", "CRS"])
    eco = {t["name"]: "E-DEF" for t in (primes, comps, mats)}
    cands = te.propose_parent_candidates([primes, comps, mats], eco)
    # mats is childless; both broader E-DEF themes are legal parents; breadth
    # (6 > 4, no shared tickers/tokens) picks primes.
    assert [(c["child"], c["parent"]) for c in cands] == [(mats["name"], primes["name"])]
    # Now make primes a child of mats' would-be parent chain: comps → mats
    # (comps' parent is mats) — mats must NOT be offered comps (cycle).
    comps["parent_theme"] = mats["name"]
    comps["tickers"] = ["HEI", "TDG", "DCO", "LMT", "KTOS"]   # broader than mats
    cands = te.propose_parent_candidates([primes, comps, mats], eco)
    assert (mats["name"], comps["name"]) not in [(c["child"], c["parent"]) for c in cands]


def test_priority_shared_tickers_then_tokens_then_breadth_and_cap():
    child = _t("Cyber Exposure Analytics", ["TENB", "QLYS", "RPD"])
    by_tickers = _t("Vulnerability Platforms", ["TENB", "QLYS", "RPD", "VRNS"])
    by_tokens = _t("Cyber Exposure Management Suites", ["A", "B", "C", "D", "E", "F", "G"])
    by_breadth = _t("Network Security & Zero-Trust Edge",
                    ["CRWD", "PANW", "FTNT", "OKTA", "VRNS", "RBRK", "S", "NET", "ZS"])
    eco = {t["name"]: "E-CYBR" for t in (child, by_tickers, by_tokens, by_breadth)}
    cands = te.propose_parent_candidates([child, by_tickers, by_tokens, by_breadth], eco)
    assert cands[0]["parent"] == by_tickers["name"]
    # drop the ticker-sharing parent → name tokens win over sheer breadth
    cands = te.propose_parent_candidates([child, by_tokens, by_breadth], eco)
    assert cands[0]["parent"] == by_tokens["name"]
    # cap: two childless themes, cap=1 keeps the stronger-signal child
    second = _t("Endpoint Detection", ["S", "NET", "ZS"])
    eco[second["name"]] = "E-CYBR"
    cands = te.propose_parent_candidates([child, second, by_tickers, by_breadth], eco, cap=1)
    assert len(cands) == 1 and cands[0]["child"] == child["name"]
    # uncapped: child, second AND by_tickers (itself childless, with the broader
    # by_breadth above it) — three childless themes, three candidates
    uncapped = te.propose_parent_candidates([child, second, by_tickers, by_breadth], eco, cap=None)
    assert {c["child"] for c in uncapped} == {child["name"], second["name"], by_tickers["name"]}


# ── _run_parent_pass (the armed night) ──────────────────────────────────────
@pytest.mark.asyncio
async def test_toggle_off_returns_before_any_io(monkeypatch):
    async def boom(*a, **kw):
        raise AssertionError("parent pass touched I/O with the toggle off")

    monkeypatch.setattr(te, "get_merge_distinct_pairs", boom)
    monkeypatch.setattr(te, "adjudicate_merge_pair", boom)
    monkeypatch.setattr(te, "log_audit_event", boom)
    board = _board()
    parents: dict[str, str] = {}
    out = await te._run_parent_pass(board, parents, enabled=False, eco_map=ECO)
    assert out == [] and parents == {}
    assert all(t["parent_theme"] is None for t in board)


@pytest.mark.asyncio
async def test_parent_child_verdict_sets_link_and_map(monkeypatch):
    events, cooldowns = _wire(monkeypatch, {NARROW: {"verdict": "PARENT_CHILD", "child": "B",
                                                     "reason": "annuity slice"}})
    board = _board()
    parents: dict[str, str] = {}
    out = await te._run_parent_pass(board, parents, enabled=True, eco_map=ECO)
    child = next(t for t in board if t["name"] == NARROW)
    assert child["parent_theme"] == BROAD
    assert parents == {NARROW: BROAD}          # _restore_sub_theme_links re-sets from this
    assert out[0]["verdict"] == "PARENT_CHILD"
    assert cooldowns == []
    types = [e[0] for e in events]
    assert types.count("theme_parent_pass_linked") == 1
    assert types[-1] == "theme_parent_pass_ran" and "1 linked" in events[-1][1]


@pytest.mark.asyncio
async def test_shadow_promoted_theme_parented_exactly_like_live(monkeypatch):
    """The path that NEVER reached the adjudicator (theme_engine.py:1926-27 in
    July). The pass reads the board, not the birth path — source is ignored."""
    _wire(monkeypatch, {NARROW: {"verdict": "PARENT_CHILD", "child": "B"}})
    board = _board()
    next(t for t in board if t["name"] == NARROW)["source"] = "shadow_promoted"
    parents: dict[str, str] = {}
    out = await te._run_parent_pass(board, parents, enabled=True, eco_map=ECO)
    assert out[0]["child_source"] == "shadow_promoted"
    assert next(t for t in board if t["name"] == NARROW)["parent_theme"] == BROAD


@pytest.mark.asyncio
async def test_distinct_writes_30d_cooldown_no_link(monkeypatch):
    events, cooldowns = _wire(monkeypatch, {NARROW: {"verdict": "DISTINCT", "reason": "different driver"}})
    board = _board()
    await te._run_parent_pass(board, {}, enabled=True, eco_map=ECO)
    assert next(t for t in board if t["name"] == NARROW)["parent_theme"] is None
    assert cooldowns == [(pair_key(NARROW, BROAD), "DISTINCT", te.MERGE_DISTINCT_COOLDOWN_DAYS)]
    assert any(e[0] == "theme_parent_pass_distinct" for e in events)


@pytest.mark.asyncio
async def test_merge_verdict_is_a_signal_never_executed(monkeypatch):
    events, cooldowns = _wire(monkeypatch, {NARROW: {"verdict": "MERGE", "reason": "same driver"}})
    board = _board()
    n_before = len(board)
    await te._run_parent_pass(board, {}, enabled=True, eco_map=ECO)
    assert len(board) == n_before                       # nothing merged / retired
    assert all(t["stage"] != "Retired" for t in board)
    assert next(t for t in board if t["name"] == NARROW)["parent_theme"] is None
    assert cooldowns == [(pair_key(NARROW, BROAD), "MERGE", te.PARENT_PASS_MERGE_SIGNAL_COOLDOWN_DAYS)]
    sig = [e for e in events if e[0] == "theme_parent_pass_merge_signal"]
    assert len(sig) == 1 and "NOT executed" in sig[0][1]


@pytest.mark.asyncio
async def test_inverted_parent_child_writes_no_link(monkeypatch):
    """The adjudicator naming the BROADER theme the child: fail-closed, no link."""
    events, cooldowns = _wire(monkeypatch, {NARROW: {"verdict": "PARENT_CHILD", "child": "A"}})
    board = _board()
    parents: dict[str, str] = {}
    await te._run_parent_pass(board, parents, enabled=True, eco_map=ECO)
    assert all(t["parent_theme"] is None for t in board) and parents == {}
    assert cooldowns[0][1] == "PARENT_CHILD_INVERTED"
    assert any(e[0] == "theme_parent_pass_inverted" for e in events)


@pytest.mark.asyncio
async def test_error_verdict_and_raising_adjudicator_fail_open(monkeypatch):
    events, cooldowns = _wire(monkeypatch, {NARROW: {"verdict": "ERROR", "reason": "429"}})
    board = _board()
    out = await te._run_parent_pass(board, {}, enabled=True, eco_map=ECO)
    assert out[0]["verdict"] == "ERROR" and cooldowns == []
    assert any(e[0] == "theme_parent_pass_error" for e in events)
    assert events[-1][0] == "theme_parent_pass_ran"      # the heartbeat still lands

    events, cooldowns = _wire(monkeypatch, {}, raise_for={NARROW})
    board = _board()
    out = await te._run_parent_pass(board, {}, enabled=True, eco_map=ECO)   # must not raise
    assert out[0]["verdict"] == "ERROR"
    assert next(t for t in board if t["name"] == NARROW)["parent_theme"] is None


@pytest.mark.asyncio
async def test_pass_level_failure_never_breaks_the_run(monkeypatch):
    events, _ = _wire(monkeypatch, {})

    async def boom():
        raise RuntimeError("cooldown table gone")

    monkeypatch.setattr(te, "get_merge_distinct_pairs", boom)
    board = _board()
    out = await te._run_parent_pass(board, {}, enabled=True, eco_map=ECO)
    assert out == []
    assert any(e[0] == "theme_parent_pass_error" and "failed mid-run" in e[1] for e in events)


@pytest.mark.asyncio
async def test_arm_b_territory_is_left_to_arm_b(monkeypatch):
    """A pair Arm B's Stage-A pairing would propose is never adjudicated here."""
    asked: list[tuple[str, str]] = []
    _wire(monkeypatch, {})

    async def spy(theme_a, theme_b, **kw):
        asked.append((theme_a["name"], theme_b["name"]))
        return {"verdict": "DISTINCT"}

    monkeypatch.setattr(te, "adjudicate_merge_pair", spy)
    monkeypatch.setattr(te, "propose_merge_pairs",
                        lambda themes, **kw: [(next(t for t in themes if t["name"] == BROAD),
                                               next(t for t in themes if t["name"] == NARROW))])
    await te._run_parent_pass(_board(), {}, enabled=True, eco_map=ECO)
    assert asked == []


def test_engine_wiring_after_arm_b_before_restore():
    # source-pin-ok: wiring check — run_theme_engine needs a live DB + LLM stack to exercise; the
    # ordering (after Arm B retires absorbed themes, before _restore_sub_theme_links re-sets the
    # links) is what makes a correct pass actually take effect, and a correct helper nobody called
    # is exactly the failure this repo has been burned by.
    src = inspect.getsource(te.run_theme_engine)
    i_armb = src.index("_run_thesis_merge_pass(")
    i_pass = src.index("_run_parent_pass(")
    i_restore = src.index("_restore_sub_theme_links(")
    assert i_armb < i_pass < i_restore
    assert "get_theme_parent_pass_enabled()" in src


# ── DB toggle (fail-closed) ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_toggle_fails_closed_and_reads_on(monkeypatch):
    from agents.market_intelligence import db as dbmod

    async def boom(*a):
        raise RuntimeError("db down")

    monkeypatch.setattr(dbmod, "get_safeguard_state", boom)
    assert await dbmod.get_theme_parent_pass_enabled() is False

    async def absent(*a):
        return None

    monkeypatch.setattr(dbmod, "get_safeguard_state", absent)
    assert await dbmod.get_theme_parent_pass_enabled() is False

    async def on(safeguard, mode):
        assert (safeguard, mode) == ("theme_parent_pass", "paper")
        return {"state": "on"}

    monkeypatch.setattr(dbmod, "get_safeguard_state", on)
    assert await dbmod.get_theme_parent_pass_enabled() is True


# ── Resolver: the overloaded column split + ruling (5) ──────────────────────
def test_containment_parent_ignores_retired_successor_pointer():
    assert tx.containment_parent(_t("X", ["A"], parent="Y")) == "Y"
    tomb = {"name": "Old Name", "stage": "Retired", "tickers": [], "parent_theme": "New Name"}
    assert tx.containment_parent(tomb) is None
    assert tx.containment_parent(_t("Z", ["A"], parent="")) is None


def test_resolve_theme_parent_child_root_catch_all():
    eco = {"C": "E-INS", "R": "E-INS", "U": tx.E_UNASSIGNED}
    assert tx.resolve_theme_parent(_t("C", ["A"], parent="R"), eco) == ("child", "R")
    assert tx.resolve_theme_parent(_t("R", ["A"]), eco) == ("root", "E-INS")
    assert tx.resolve_theme_parent(_t("U", ["A"]), eco) == ("catch_all", tx.E_UNASSIGNED)
    assert tx.resolve_theme_parent(_t("never mapped", ["A"]), eco) == ("catch_all", tx.E_UNASSIGNED)
    tomb = {"name": "Old", "stage": "Retired", "tickers": [], "parent_theme": "New"}
    assert tx.resolve_theme_parent(tomb, {"Old": "E-INS"}) == ("root", "E-INS")


# ── The operator surface: /themes nests children under parents ──────────────
def _scored(name, comp, stage, tickers, parent=None):
    return {"name": name, "stage": stage, "comp": comp, "rs_1m": comp, "rs_3m": comp,
            "rs_6m": comp, "delta": None, "tickers": tickers, "n_stocks": len(tickers),
            "n_scored": len(tickers), "parent_theme": parent}


def test_board_nests_child_under_parent_with_marker():
    rs = {tk: {"rs_composite": 90.0} for tk in ["MET", "PRU", "CRBG", "JXN", "KEY"]}
    scored = [
        _scored(NARROW, 95.0, "Nascent", ["CRBG", "JXN"], parent=BROAD),   # ranks ABOVE its parent
        _scored(BROAD, 80.0, "Mainstream", ["MET", "PRU", "CRBG"]),
        _scored(OTHER_ECO, 70.0, "Nascent", ["KEY"]),
    ]
    lines = tx.format_ecosystem_board(scored, [], rs, ECO)
    text = "\n".join(lines)
    child_line = next(l for l in lines if NARROW in l)
    parent_line = next(l for l in lines if BROAD in l and NARROW not in l)
    assert child_line.lstrip().startswith(tx.CHILD_MARKER)          # ↳ child
    assert not parent_line.lstrip().startswith(tx.CHILD_MARKER)
    assert lines.index(parent_line) < lines.index(child_line)      # child FOLLOWS its parent
    assert len(child_line) - len(child_line.lstrip()) > len(parent_line) - len(parent_line.lstrip())
    assert "#1 " in child_line                                      # global rank kept
    assert text.count(NARROW) == 1                                   # rendered once


def test_board_child_whose_parent_is_fading_keeps_inline_tag():
    rs = {tk: {"rs_composite": 90.0} for tk in ["CRBG", "JXN"]}
    scored = [_scored(NARROW, 95.0, "Nascent", ["CRBG", "JXN"], parent=BROAD)]
    fading = [{"name": BROAD, "stage": "Fading", "tickers": ["MET"], "parent_theme": None}]
    lines = tx.format_ecosystem_board(scored, fading, rs, ECO)
    child_line = next(l for l in lines if NARROW in l)
    assert f"under {BROAD}" in child_line and tx.CHILD_MARKER in child_line
    assert not child_line.lstrip().startswith(tx.CHILD_MARKER)      # not nested: parent not active


def test_board_chain_renders_two_levels():
    rs = {tk: {"rs_composite": 90.0} for tk in ["A", "B", "C"]}
    scored = [
        _scored("Primes", 90.0, "Mainstream", ["A"]),
        _scored("Components", 85.0, "Mainstream", ["B"], parent="Primes"),
        _scored("Materials", 80.0, "Nascent", ["C"], parent="Components"),
    ]
    eco = {n: "E-DEF" for n in ("Primes", "Components", "Materials")}
    lines = tx.format_ecosystem_board(scored, [], rs, eco)
    l1 = next(l for l in lines if "Primes" in l)
    l2 = next(l for l in lines if "Components" in l)
    l3 = next(l for l in lines if "Materials" in l)
    ind = lambda l: len(l) - len(l.lstrip())  # noqa: E731
    assert ind(l1) < ind(l2) < ind(l3)
    assert lines.index(l1) < lines.index(l2) < lines.index(l3)


def test_board_cycle_never_drops_a_theme():
    rs = {tk: {"rs_composite": 90.0} for tk in ["A", "B"]}
    scored = [_scored("X", 90.0, "Mainstream", ["A"], parent="Y"),
              _scored("Y", 85.0, "Mainstream", ["B"], parent="X")]
    text = "\n".join(tx.format_ecosystem_board(scored, [], rs, {"X": "E-INS", "Y": "E-INS"}))
    assert "X" in text and "Y" in text


def test_compute_scored_themes_carries_parent_theme():
    from agents.market_intelligence.briefing import _compute_scored_themes
    themes = [{"name": NARROW, "stage": "Nascent", "tickers": ["CRBG"], "parent_theme": BROAD}]
    scored, _ = _compute_scored_themes(themes, {"CRBG": {"rs_composite": 90.0}}, {})
    assert scored[0]["parent_theme"] == BROAD
