"""ADR 0032 Phase 2 (DARK) — theme re-granularization behind THEME_SUBTHEME_ARM.

Pins the load-bearing safety property: **arm OFF ⇒ `_merge_overlapping_themes`
is byte-identical to pre-Phase-2 behavior** (the ADR-0025 build-dark discipline),
plus the Route-A acceptance fixtures from the design doc
(docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md §1.5):

  * 7/07 + 7/13 + 7/15 cyber vuln-mgmt kills → route PARENT_CHILD → persist as
    ONE ticker-set-canonicalized child of "Network Security & Zero-Trust Edge"
    (fork F-2: the LLM NAME churns daily; identity = the ticker set — the three
    re-discoveries collapse to ONE child, never three).
  * Fail-closed: MERGE / DISTINCT / ERROR / inverted-child / raised exception →
    today's strip, byte-identically.
  * §1.1-D symmetric coexistence carve-out (always-on, fork F-4) in BOTH
    directions — the child-outscores-parent gutting bug (G4).
  * Route B (`_nominate_dominant_split_themes`) eligibility + arm-off inertness.

All LLM calls are mocked (the real adjudicator is the paid §1.4 flip gate — A1).

Run: pytest tests/test_theme_subtheme_routing.py -v
"""
from __future__ import annotations

import copy
import types

import pytest

from agents.market_intelligence import theme_engine


# ── Verified fixture data (design doc G1, [V prod] 2026-07-14) ───────────────
PARENT_NAME = "Network Security & Zero-Trust Edge"
PARENT_TICKERS = [
    "TENB", "CRWD", "CVLT", "QLYS", "RPD", "PANW",
    "VRNS", "FTNT", "BB", "GRRR", "OKTA", "RBRK",
]
KILL_0707 = ("Cyber Vulnerability Management & Exposure Platforms",
             ["TENB", "RPD", "QLYS"])
KILL_0713 = ("Vulnerability Management & Data Security Posture",
             ["TENB", "RPD", "VRNS", "QLYS"])
KILL_0715 = ("Cyber Exposure & Vulnerability Analytics",
             ["TENB", "QLYS", "RPD"])


# ── Harness ──────────────────────────────────────────────────────────────────
def _audit_capture(monkeypatch):
    events: list[tuple[str, str, str]] = []

    async def fake_audit(event_type, summary, detail=""):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    return events


def _parent(score=60.0):
    return {"name": PARENT_NAME, "tickers": list(PARENT_TICKERS),
            "score": score, "stage": "Mainstream"}


def _newborn(name, tickers, score=99.0):
    return {"name": name, "tickers": list(tickers), "score": score,
            "stage": "Nascent"}


def _snapshot(themes: list[dict]) -> list[tuple]:
    """Order-independent, comparison-friendly view of a merge output."""
    return sorted(
        (t["name"], tuple(sorted(t.get("tickers") or [])), t.get("parent_theme"))
        for t in themes
    )


def _make_adjudicator(verdict, calls=None):
    """Mock Arm-B adjudicator. `verdict` = dict to return, or an Exception to
    raise. Signature mirrors theme_merge_arm.adjudicate_merge_pair."""

    async def adj(theme_a, theme_b, *, client=None, semaphore=None,
                  sectors_by_ticker=None, log_spend=False):
        if calls is not None:
            calls.append((theme_a["name"], theme_b["name"]))
        if isinstance(verdict, Exception):
            raise verdict
        return dict(verdict)

    return adj


def _poison_adjudicator():
    """Must never be reached — arm off / trigger unmet / cap exhausted."""

    async def adj(*args, **kwargs):  # pragma: no cover - reaching this IS the failure
        raise AssertionError("adjudicator called when it must not be")

    return adj


async def _run_merge(themes, protected, sub_parents, ctx=..., monkey_audit=None):
    """One _merge_overlapping_themes call on deep-copied inputs."""
    kwargs = {}
    if ctx is not ...:
        kwargs["subtheme_ctx"] = ctx
    return await theme_engine._merge_overlapping_themes(
        copy.deepcopy(themes), stocks_by_ticker={},
        protected_names=set(protected), sub_theme_parents=dict(sub_parents),
        **kwargs,
    )


# ═════════════════════════ Arm OFF — byte-identical pin ══════════════════════

@pytest.mark.asyncio
async def test_arm_off_byte_identical_protect_strip(monkeypatch):
    """THE safety pin: with the arm OFF (no ctx / ctx=None / disabled ctx) the
    7/07 protect-strip replay is byte-identical across all three call shapes
    AND matches the pre-change golden outcome (newborn stripped to empty —
    EMPTY_AFTER_STRIP — parent untouched, no parent_theme anywhere)."""
    events = _audit_capture(monkeypatch)
    themes = [_newborn(*KILL_0707), _parent()]
    protected = {PARENT_NAME}

    out_no_kwarg = await _run_merge(themes, protected, {})
    out_none = await _run_merge(themes, protected, {}, ctx=None)
    disabled_ctx = theme_engine.make_subtheme_route_ctx(
        False, adjudicate=_poison_adjudicator())
    out_disabled = await _run_merge(themes, protected, {}, ctx=disabled_ctx)

    assert _snapshot(out_no_kwarg) == _snapshot(out_none) == _snapshot(out_disabled)

    # Golden pre-change outcome (G1: exactly how the 7/07 birth died).
    by_name = {t["name"]: t for t in out_no_kwarg}
    assert set(by_name[KILL_0707[0]].get("tickers") or []) == set()
    assert set(by_name[PARENT_NAME]["tickers"]) == set(PARENT_TICKERS)
    assert all(not t.get("parent_theme") for t in out_no_kwarg)

    strip_events = [e for e in events if e[0] == "theme_pass1_protect_strip"]
    assert len(strip_events) == 3  # one per call shape
    assert all("EMPTY_AFTER_STRIP" in e[2] for e in strip_events)
    # No Phase-2 event may fire with the arm off.
    assert not [e for e in events if e[0].startswith("theme_subtheme")]
    assert disabled_ctx["routed"] == 0


@pytest.mark.asyncio
async def test_arm_off_byte_identical_both_protected_tiebreak(monkeypatch):
    """The BOTH_PROTECTED tiebreaker shape (the 153 historical strips) is
    identical with and without a disabled ctx."""
    _audit_capture(monkeypatch)
    themes = [
        {"name": "AI Memory & Storage",
         "tickers": ["MU", "SNDK", "WDC", "STX", "MRAM", "SIMO", "ICHR", "TSEM"],
         "score": 80.0, "stage": "Mainstream"},
        {"name": "Semiconductor Front-End Interconnect",
         "tickers": ["SNDK", "ICHR", "TSEM"], "score": 79.5, "stage": "Mainstream"},
    ]
    protected = {"AI Memory & Storage", "Semiconductor Front-End Interconnect"}

    out_plain = await _run_merge(themes, protected, {})
    ctx = theme_engine.make_subtheme_route_ctx(False, adjudicate=_poison_adjudicator())
    out_ctx = await _run_merge(themes, protected, {}, ctx=ctx)
    assert _snapshot(out_plain) == _snapshot(out_ctx)


@pytest.mark.asyncio
async def test_arm_on_leaves_both_protected_strips_untouched(monkeypatch):
    """G2 blast radius: routing is keyed on newborn-vs-incumbent (T2). With the
    arm ON, an established-vs-established (BOTH_PROTECTED) strip is untouched
    and the adjudicator is never called — the 153 historical strip shapes."""
    _audit_capture(monkeypatch)
    themes = [
        {"name": "AI Memory & Storage",
         "tickers": ["MU", "SNDK", "WDC", "STX", "MRAM", "SIMO", "ICHR", "TSEM"],
         "score": 80.0, "stage": "Mainstream"},
        {"name": "Semiconductor Front-End Interconnect",
         "tickers": ["SNDK", "ICHR", "TSEM"], "score": 79.5, "stage": "Mainstream"},
    ]
    protected = {"AI Memory & Storage", "Semiconductor Front-End Interconnect"}

    out_off = await _run_merge(themes, protected, {})
    ctx = theme_engine.make_subtheme_route_ctx(True, adjudicate=_poison_adjudicator())
    out_on = await _run_merge(themes, protected, {}, ctx=ctx)
    assert _snapshot(out_off) == _snapshot(out_on)
    assert ctx["routed"] == 0


# ═══════════════════ Route A — PARENT_CHILD accept + fixtures ════════════════

@pytest.mark.asyncio
async def test_route_a_parent_child_coexists(monkeypatch):
    """7/07 fixture, arm ON, adjudicator → PARENT_CHILD/child=B: NO strip; the
    newborn persists with parent_theme set; the live sub_theme_parents dict is
    mutated (Pass1.5 exemption + coexistence for the rest of the run); the
    parent keeps all 12 members; cap consumed; theme_subtheme_routed audited."""
    events = _audit_capture(monkeypatch)
    calls: list = []
    ctx = theme_engine.make_subtheme_route_ctx(
        True, adjudicate=_make_adjudicator(
            {"verdict": "PARENT_CHILD", "child": "B",
             "reason": "vuln-mgmt is a coherent sub-catalyst",
             "analysis_scratchpad": "parent=broad cyber; child=vuln mgmt"},
            calls,
        ),
    )
    sub_parents: dict[str, str] = {}
    result = await theme_engine._merge_overlapping_themes(
        [_newborn(*KILL_0707), _parent()], stocks_by_ticker={},
        protected_names={PARENT_NAME}, sub_theme_parents=sub_parents,
        subtheme_ctx=ctx,
    )

    by_name = {t["name"]: t for t in result}
    child = by_name[KILL_0707[0]]
    assert set(child["tickers"]) == set(KILL_0707[1])          # strip averted
    assert child["parent_theme"] == PARENT_NAME
    assert set(by_name[PARENT_NAME]["tickers"]) == set(PARENT_TICKERS)
    assert sub_parents == {KILL_0707[0]: PARENT_NAME}          # live-dict mutation
    assert ctx["routed"] == 1
    assert ctx["routed_children"] == {KILL_0707[0]: PARENT_NAME}
    assert calls == [(PARENT_NAME, KILL_0707[0])]              # parent=A, newborn=B
    assert [e for e in events if e[0] == "theme_subtheme_routed"]
    assert not [e for e in events if e[0] == "theme_pass1_protect_strip"]


@pytest.mark.asyncio
async def test_route_a_three_rediscoveries_collapse_to_one_child(monkeypatch):
    """THE acceptance fixture (F-2, §1.5): the 3 cyber vuln-mgmt kills
    (7/07 TENB/RPD/QLYS · 7/13 +VRNS · 7/15 TENB/QLYS/RPD) replayed as three
    consecutive nights collapse to ONE canonicalized child of the parent —
    name-keyed identity would have spawned a dupe every run; ticker-set
    canonicalization UPDATES the existing child instead. Exactly ONE paid
    adjudication across all three nights."""
    events = _audit_capture(monkeypatch)
    calls: list = []
    adjudicate = _make_adjudicator(
        {"verdict": "PARENT_CHILD", "child": "B", "reason": "sub-catalyst"}, calls)

    # ── Night 1 (7/07): birth of the child via Route A.
    ctx1 = theme_engine.make_subtheme_route_ctx(True, adjudicate=adjudicate)
    sub_parents: dict[str, str] = {}
    out1 = await theme_engine._merge_overlapping_themes(
        [_newborn(*KILL_0707), _parent()], stocks_by_ticker={},
        protected_names={PARENT_NAME}, sub_theme_parents=sub_parents,
        subtheme_ctx=ctx1,
    )
    child_name = KILL_0707[0]
    assert {t["name"] for t in out1} == {PARENT_NAME, child_name}

    def _next_night(prev_out, newborn):
        """Rebuild the next night's inputs the way run_theme_engine would:
        yesterday's survivors are incumbents (protected) and parent links
        reload from the DB snapshot into prior_sub_parents."""
        themes = []
        prior_sub_parents = {}
        for t in copy.deepcopy(prev_out):
            t["score"] = 98.0 if t.get("parent_theme") else 60.0
            themes.append(t)
            if t.get("parent_theme"):
                prior_sub_parents[t["name"]] = t["parent_theme"]
        protected = {t["name"] for t in themes}
        themes.append(newborn)
        return themes, protected, prior_sub_parents

    # ── Night 2 (7/13): re-discovery under a churned name, +VRNS.
    themes2, protected2, sub_parents2 = _next_night(out1, _newborn(*KILL_0713, score=99.5))
    ctx2 = theme_engine.make_subtheme_route_ctx(True, adjudicate=adjudicate)
    out2 = await theme_engine._merge_overlapping_themes(
        themes2, stocks_by_ticker={}, protected_names=protected2,
        sub_theme_parents=sub_parents2, subtheme_ctx=ctx2,
    )
    children2 = [t for t in out2 if t.get("parent_theme")]
    assert len(children2) == 1, f"expected ONE child, got {children2}"
    assert children2[0]["name"] == child_name                    # canonical name kept
    assert set(children2[0]["tickers"]) == set(KILL_0713[1])     # VRNS folded in
    assert KILL_0713[0] not in {t["name"] for t in out2}         # no 2nd child
    assert ctx2["routed"] == 0                                   # no paid call night 2

    # ── Night 3 (7/15): third re-discovery, subset ticker set.
    themes3, protected3, sub_parents3 = _next_night(out2, _newborn(*KILL_0715, score=99.2))
    ctx3 = theme_engine.make_subtheme_route_ctx(True, adjudicate=adjudicate)
    out3 = await theme_engine._merge_overlapping_themes(
        themes3, stocks_by_ticker={}, protected_names=protected3,
        sub_theme_parents=sub_parents3, subtheme_ctx=ctx3,
    )
    children3 = [t for t in out3 if t.get("parent_theme")]
    assert len(children3) == 1
    assert children3[0]["name"] == child_name
    assert set(children3[0]["tickers"]) == set(KILL_0713[1])     # unchanged union
    assert children3[0]["parent_theme"] == PARENT_NAME
    assert KILL_0715[0] not in {t["name"] for t in out3}
    assert ctx3["routed"] == 0

    # ONE adjudication total; nights 2+3 were deterministic canonicalizations.
    assert len(calls) == 1
    assert len([e for e in events if e[0] == "theme_subtheme_canonicalized"]) == 2
    # The parent was never stripped across the three nights.
    for out in (out1, out2, out3):
        parent_row = next(t for t in out if t["name"] == PARENT_NAME)
        assert set(parent_row["tickers"]) == set(PARENT_TICKERS)


# ═════════════════════ Route A — fail-closed verdicts ════════════════════════

@pytest.mark.parametrize(
    "verdict,expected_event",
    [
        ({"verdict": "MERGE", "reason": "redundant slice"},
         "theme_subtheme_route_merge"),
        ({"verdict": "DISTINCT", "reason": "different drivers"},
         "theme_subtheme_route_distinct"),
        ({"verdict": "ERROR", "reason": "api down"},
         "theme_subtheme_route_error"),
        ({"verdict": "PARENT_CHILD", "child": "A", "reason": "inverted"},
         "theme_subtheme_route_inverted"),
        (RuntimeError("adjudicator exploded"),
         "theme_subtheme_route_error"),
    ],
    ids=["merge", "distinct", "error", "inverted-child", "raises"],
)
@pytest.mark.asyncio
async def test_route_a_fail_closed_to_strip(monkeypatch, verdict, expected_event):
    """Every non-accepted outcome (MERGE / DISTINCT / ERROR / inverted child /
    raised exception) falls through to TODAY'S strip — output identical to the
    arm-off run — and the verdict-specific audit event fires. A routed call
    consumes the cap regardless of verdict."""
    events = _audit_capture(monkeypatch)
    themes = [_newborn(*KILL_0707), _parent()]

    out_off = await _run_merge(themes, {PARENT_NAME}, {})

    ctx = theme_engine.make_subtheme_route_ctx(
        True, adjudicate=_make_adjudicator(verdict))
    out_on = await _run_merge(themes, {PARENT_NAME}, {}, ctx=ctx)

    assert _snapshot(out_on) == _snapshot(out_off)          # byte-identical strip
    assert all(not t.get("parent_theme") for t in out_on)
    assert ctx["routed"] == 1                               # cap consumed
    assert [e for e in events if e[0] == expected_event]
    assert not [e for e in events if e[0] == "theme_subtheme_routed"]
    # The strip itself happened (EMPTY_AFTER_STRIP), exactly as today.
    assert any(e[0] == "theme_pass1_protect_strip" and "EMPTY_AFTER_STRIP" in e[2]
               for e in events)


@pytest.mark.asyncio
async def test_route_cap_exhausted_falls_back_to_strip(monkeypatch):
    """T7: once the per-run adjudication budget is spent, further candidates
    strip as today and the adjudicator is never called."""
    events = _audit_capture(monkeypatch)
    ctx = theme_engine.make_subtheme_route_ctx(True, adjudicate=_poison_adjudicator())
    ctx["routed"] = ctx["route_cap"]  # budget already consumed this run

    out = await _run_merge([_newborn(*KILL_0707), _parent()], {PARENT_NAME}, {}, ctx=ctx)
    by_name = {t["name"]: t for t in out}
    assert set(by_name[KILL_0707[0]].get("tickers") or []) == set()
    assert not [e for e in events if e[0] == "theme_subtheme_routed"]


# ═══════════════════ Route A — sole-parent helper gates ══════════════════════

@pytest.mark.asyncio
async def test_multi_parent_newborn_not_routed(monkeypatch):
    """T5: a newborn whose members spread across TWO protected incumbents is
    not a coherent subset of ONE — falls through to today's strip, no LLM."""
    events = _audit_capture(monkeypatch)
    parent_x = {"name": "Parent X", "score": 80.0, "stage": "Mainstream",
                "tickers": ["A", "B", "C", "D"] + [f"X{n}" for n in range(8)]}
    parent_y = {"name": "Parent Y", "score": 70.0, "stage": "Mainstream",
                "tickers": ["C", "D", "E"] + [f"Y{n}" for n in range(8)]}
    straddler = _newborn("Straddler", ["A", "B", "C", "D", "E"])  # 0.8 vs X, 0.6 vs Y

    ctx = theme_engine.make_subtheme_route_ctx(True, adjudicate=_poison_adjudicator())
    out = await _run_merge([straddler, parent_x, parent_y],
                           {"Parent X", "Parent Y"}, {}, ctx=ctx)
    by_name = {t["name"]: set(t.get("tickers") or []) for t in out}
    assert by_name["Straddler"] == {"E"}  # stripped by X exactly as today
    assert ctx["routed"] == 0
    assert not [e for e in events if e[0].startswith("theme_subtheme")]


@pytest.mark.asyncio
async def test_low_containment_newborn_not_routed(monkeypatch):
    """T4: overlap-ratio 0.6 fires the pair gate but containment < C_MIN keeps
    the newborn on today's strip path — no adjudication."""
    events = _audit_capture(monkeypatch)
    parent = {"name": "Parent Z", "score": 80.0, "stage": "Mainstream",
              "tickers": ["A", "B", "C"] + [f"Z{n}" for n in range(9)]}
    newborn = _newborn("Partial Overlap", ["A", "B", "C", "Q", "R"])  # c = 0.6

    ctx = theme_engine.make_subtheme_route_ctx(True, adjudicate=_poison_adjudicator())
    out = await _run_merge([newborn, parent], {"Parent Z"}, {}, ctx=ctx)
    by_name = {t["name"]: set(t.get("tickers") or []) for t in out}
    assert by_name["Partial Overlap"] == {"Q", "R"}
    assert ctx["routed"] == 0
    assert not [e for e in events if e[0].startswith("theme_subtheme")]


@pytest.mark.asyncio
async def test_tiny_newborn_not_routed(monkeypatch):
    """T6: below SUBTHEME_MIN_MEMBERS the pair strips as today (keeps the
    floor backtestable)."""
    events = _audit_capture(monkeypatch)
    # 3 shared members are required by MIN_SHARED_FOR_MERGE for the pair gate,
    # so exercise T6 with a 3-member floor bumped virtually: use a 3-member
    # newborn and a raised floor.
    monkeypatch.setattr(theme_engine, "SUBTHEME_MIN_MEMBERS", 4)
    ctx = theme_engine.make_subtheme_route_ctx(True, adjudicate=_poison_adjudicator())
    out = await _run_merge([_newborn(*KILL_0707), _parent()], {PARENT_NAME}, {}, ctx=ctx)
    by_name = {t["name"]: set(t.get("tickers") or []) for t in out}
    assert by_name[KILL_0707[0]] == set()
    assert ctx["routed"] == 0
    assert not [e for e in events if e[0].startswith("theme_subtheme")]


# ═══════════════ §1.1-D symmetric coexistence carve-out (F-4) ════════════════

@pytest.mark.asyncio
async def test_carveout_parent_outscores_child(monkeypatch):
    """Existing direction (pre-Phase-2): parent sorts as i, child as j —
    coexistence holds, no strip, no merge."""
    events = _audit_capture(monkeypatch)
    parent = _parent(score=90.0)
    child = {"name": "Vuln Mgmt Child", "tickers": ["TENB", "RPD", "QLYS"],
             "score": 80.0, "stage": "Accelerating", "parent_theme": PARENT_NAME}
    out = await _run_merge(
        [parent, child], {PARENT_NAME, "Vuln Mgmt Child"},
        {"Vuln Mgmt Child": PARENT_NAME},
    )
    by_name = {t["name"]: set(t.get("tickers") or []) for t in out}
    assert by_name[PARENT_NAME] == set(PARENT_TICKERS)
    assert by_name["Vuln Mgmt Child"] == {"TENB", "RPD", "QLYS"}
    assert not [e for e in events if e[0] == "theme_pass1_protect_strip"]


@pytest.mark.asyncio
async def test_carveout_child_outscores_parent_g4_fix(monkeypatch):
    """NEW direction (§1.1-D, always-on): an elite-RS child sorts ABOVE its
    parent (i=child, j=parent, BOTH protected). Pre-fix, the BOTH_PROTECTED
    tiebreaker stripped the smaller theme — gutting the child the night after
    it was created (G4). The symmetric carve-out must keep both intact, with
    the arm OFF (the fix is deliberately un-toggled)."""
    events = _audit_capture(monkeypatch)
    child = {"name": "Vuln Mgmt Child", "tickers": ["TENB", "RPD", "QLYS"],
             "score": 99.4, "stage": "Accelerating", "parent_theme": PARENT_NAME}
    parent = _parent(score=60.0)
    out = await _run_merge(
        [child, parent], {PARENT_NAME, "Vuln Mgmt Child"},
        {"Vuln Mgmt Child": PARENT_NAME},
    )
    by_name = {t["name"]: set(t.get("tickers") or []) for t in out}
    assert by_name["Vuln Mgmt Child"] == {"TENB", "RPD", "QLYS"}, \
        "child gutted — the G4 one-directional carve-out bug is back"
    assert by_name[PARENT_NAME] == set(PARENT_TICKERS)
    assert not [e for e in events if e[0] == "theme_pass1_protect_strip"]


# ═════════════════════════ Route B — eligibility ═════════════════════════════

def _mk_theme(name, n_members, n_strong, stage="Accelerating", parent=None):
    tickers = [f"{name[:2].upper()}{i}" for i in range(n_members)]
    t = {"name": name, "tickers": tickers, "score": 70.0, "stage": stage}
    if parent:
        t["parent_theme"] = parent
    return t, {tk: {"rs_composite": 95 if i < n_strong else 50}
               for i, tk in enumerate(tickers)}


@pytest.mark.asyncio
async def test_route_b_arm_off_no_db_touch(monkeypatch):
    """Arm OFF ⇒ [] and the ecosystem mapping is NEVER fetched (byte-identical
    engine: zero new DB access)."""
    import agents.market_intelligence.db as db_mod

    async def poison():  # pragma: no cover - reaching this IS the failure
        raise AssertionError("get_all_theme_ecosystems called with arm off")

    monkeypatch.setattr(db_mod, "get_all_theme_ecosystems", poison)
    theme, stocks = _mk_theme("Cyber Blob", 12, 11)
    out = await theme_engine._nominate_dominant_split_themes(
        [theme], stocks, arm_enabled=False)
    assert out == []


@pytest.mark.asyncio
async def test_route_b_dominant_eligibility_matrix(monkeypatch):
    """Arm ON: only a sole-sub-theme, real-ecosystem, ≥MIN_MEMBERS/≥MIN_STRONG,
    not-already-fat, non-child, non-Fading theme is nominated; each nominee
    emits theme_dominant_split_eligible BEFORE any LLM runs."""
    events = _audit_capture(monkeypatch)
    import agents.market_intelligence.db as db_mod

    qualifying, stocks_q = _mk_theme("Cyber Blob", 12, 11)
    not_sole_a, stocks_a = _mk_theme("Semi One", 12, 11)
    not_sole_b, stocks_b = _mk_theme("Semi Two", 12, 11)
    unassigned, stocks_u = _mk_theme("Drifting", 12, 11)
    unmapped, stocks_m = _mk_theme("Unmapped", 12, 11)
    too_few_members, stocks_f = _mk_theme("Thin", 9, 9)
    too_few_strong, stocks_s = _mk_theme("Weak", 12, 7)
    already_fat, stocks_fat = _mk_theme("Fat", theme_engine.MAX_THEME_STOCKS + 1, 21)
    is_child, stocks_c = _mk_theme("Childish", 12, 11, parent="Someone")
    fading, stocks_fd = _mk_theme("Tired", 12, 11, stage="Fading")

    eco_map = {
        "Cyber Blob": "E-CYBR", "Semi One": "E-AISEMI", "Semi Two": "E-AISEMI",
        "Drifting": "E-UNASSIGNED", "Thin": "E-INS", "Weak": "E-REIT",
        "Fat": "E-DEF", "Childish": "E-SAAS", "Tired": "E-BANKFIN",
    }

    async def fake_eco():
        return dict(eco_map)

    monkeypatch.setattr(db_mod, "get_all_theme_ecosystems", fake_eco)
    stocks = {**stocks_q, **stocks_a, **stocks_b, **stocks_u, **stocks_m,
              **stocks_f, **stocks_s, **stocks_fat, **stocks_c, **stocks_fd}
    all_themes = [qualifying, not_sole_a, not_sole_b, unassigned, unmapped,
                  too_few_members, too_few_strong, already_fat, is_child, fading]

    out = await theme_engine._nominate_dominant_split_themes(
        all_themes, stocks, arm_enabled=True)
    assert [t["name"] for t in out] == ["Cyber Blob"]
    eligible_events = [e for e in events if e[0] == "theme_dominant_split_eligible"]
    assert len(eligible_events) == 1 and "Cyber Blob" in eligible_events[0][1]


@pytest.mark.asyncio
async def test_route_b_nightly_cap(monkeypatch):
    """≤ DOM_SPLITS_PER_NIGHT nominees even when more themes qualify."""
    _audit_capture(monkeypatch)
    import agents.market_intelligence.db as db_mod

    t1, s1 = _mk_theme("Alpha Dominant", 12, 11)
    t2, s2 = _mk_theme("Beta Dominant", 12, 11)
    t3, s3 = _mk_theme("Gamma Dominant", 12, 11)
    eco_map = {"Alpha Dominant": "E-A", "Beta Dominant": "E-B", "Gamma Dominant": "E-C"}

    async def fake_eco():
        return dict(eco_map)

    monkeypatch.setattr(db_mod, "get_all_theme_ecosystems", fake_eco)
    out = await theme_engine._nominate_dominant_split_themes(
        [t1, t2, t3], {**s1, **s2, **s3}, arm_enabled=True)
    assert len(out) == theme_engine.DOM_SPLITS_PER_NIGHT


# ═════════════ _split_fat_theme prompt — reason_line template arg ════════════

class _CapturingClient:
    """Fake AsyncAnthropic capturing the prompt; returns a no-tool response
    (Sonnet 'no split')."""

    def __init__(self):
        self.captured: list[dict] = []
        self.messages = self

    async def create(self, **kwargs):
        self.captured.append(kwargs)
        return types.SimpleNamespace(content=[], usage=None)


@pytest.mark.asyncio
async def test_split_prompt_default_reason_byte_identical(monkeypatch):
    """reason_line=None (every pre-Phase-2 caller) ⇒ the prompt opens with the
    EXACT pre-change phrase — pins Route B's template arg as a no-op default."""
    _audit_capture(monkeypatch)
    client = _CapturingClient()
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: client)
    import agents.market_intelligence.spend_tracker as spend_mod

    async def no_spend(**kwargs):
        return None

    monkeypatch.setattr(spend_mod, "log_anthropic_call_safe", no_spend)

    theme = {"name": "Broad Theme", "tickers": [f"T{i}" for i in range(21)],
             "score": 70.0, "stage": "Mainstream"}
    sub, calls = await theme_engine._split_fat_theme(theme, {}, 0)
    assert sub is None and calls == 0
    prompt = client.captured[0]["messages"][0]["content"]
    assert prompt.startswith(
        "You are analyzing a theme that has grown too broad (21 stocks).")


@pytest.mark.asyncio
async def test_split_prompt_dominant_reason_line(monkeypatch):
    """Route B passes the ecosystem-dominant phrase — one prompt, one template
    arg, not a second prompt."""
    _audit_capture(monkeypatch)
    client = _CapturingClient()
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: client)
    import agents.market_intelligence.spend_tracker as spend_mod

    async def no_spend(**kwargs):
        return None

    monkeypatch.setattr(spend_mod, "log_anthropic_call_safe", no_spend)

    theme = {"name": "Cyber Blob", "tickers": [f"T{i}" for i in range(12)],
             "score": 70.0, "stage": "Mainstream"}
    await theme_engine._split_fat_theme(
        theme, {}, 0,
        reason_line="is ecosystem-dominant with no sub-theme structure (12 stocks)",
    )
    prompt = client.captured[0]["messages"][0]["content"]
    assert "is ecosystem-dominant with no sub-theme structure (12 stocks)" in prompt
    assert "has grown too broad" not in prompt


@pytest.mark.asyncio
async def test_sector_cap_zero_drop_emits_audit_event(monkeypatch):
    """#476 — the cap-0 silent-drop branch (biotech since 2026-03-20) must emit
    `theme_sector_cap_dropped`. For 4 months every biotech theme vanished here
    with no trace while the shadow-promote resurrected the cohort nightly."""
    from unittest.mock import AsyncMock

    from agents.market_intelligence import theme_engine as te

    audit = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", audit)
    themes = [
        {"name": "Targeted Protein Degradation Oncology",  # matches 'biotech' group? uses keywords
         "tickers": ["GLUE", "KYMR"], "score": 50, "stage": "Nascent"},
        {"name": "Clinical-Stage Biotech Innovators",
         "tickers": ["NRIX", "AGIO"], "score": 40, "stage": "Nascent"},
    ]
    # drive JUST Pass 2 via the public merge fn with no overlaps (disjoint tickers)
    out = await te._merge_overlapping_themes(themes, {}, protected_names=set())
    dropped = [c.args[0] for c in audit.await_args_list
               if c.args and c.args[0] == "theme_sector_cap_dropped"]
    surviving = {t["name"] for t in out}
    # 'Clinical-Stage Biotech Innovators' matches the biotech cap-0 group -> dropped + audited
    assert "Clinical-Stage Biotech Innovators" not in surviving
    assert dropped, "cap-0 drop must emit theme_sector_cap_dropped"
