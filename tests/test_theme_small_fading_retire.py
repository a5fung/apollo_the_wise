"""#655 rule B + bug E (theme_engine, 2026-10-04, operator "aligned": rule 1 YES, rule 2 WAIT, E fix).

RULE B — a theme whose emitted row tonight is WEAK-Fading (stage 'Fading' AND rs_avg None — the row
only `_rescore_existing_theme`'s weak branch writes; the scored path always carries a number) with
FEWER THAN 3 members is retired tonight instead of after FADING_RETIRE_AFTER (5) weak nights. It is a
separate pass sited right AFTER Step 2a.5 (#491 re-homing) because the stage decision runs in Step 1,
before the pools are built; the dropped theme takes the SAME engine-drop path a 5-night retirement
takes (tombstone + `theme_auto_retired`, the `theme_retired` changelog line). Toggle
`theme_small_fading_retire`, DEFAULT ON; OFF = nothing retired here.

BUG E — the promote lane read "has a prior mi_themes row" as "maintenance of a live theme", but the
immediately-prior row by name is frequently an auto-retire TOMBSTONE (stage 'Retired'); a cohort
retired one night and re-promoted the next skipped the birth gate, so the dedup_only join arm could
never fire on it. A tombstone prior is now a first crossing for the gate; a live prior stays
maintenance; days_active continuity is untouched.

Red-without / mutation record (run on this commit, stated in the commit message). On origin/main's
theme_engine.py: the pass-level tests fail on the missing symbol (`_retire_small_fading_themes`), the
two engine tests fail on `AttributeError` at `te._retire_small_fading_themes` (NOT on behaviour — the
behaviour coverage for them is the mutation record below), and the tombstone-prior join test fails on
behaviour. The preservation tests stay green on revert by construction and were each turned red by one
mutation: drop `rs_avg is None` → the scored/elite test; `<` → `<=` → the 3-member grace test; ignore
the toggle → the OFF tests; `_first_crossing = True` → the live-prior test; no-op the pass → the
runs-after-re-homing test.

REVIEW FIX (2026-10-04, both reviewers): with the REAL `theme_member_rehomed` audit row present, the
B tombstone claimed the theme was "absorbed/superseded" by the re-homing TARGET (parent_theme set),
because the engine-drop block reads "'<home>' -> '<target>'" as a successor pointer and a B candidate
is, by design, still on the board when re-homing runs. The first build's e2e test hid it by returning
[] from the audit read. `test_runs_after_rehoming…` now feeds the real row and is RED on 0d487cb0 on
behaviour (parent_theme == the AI theme) and green after; `test_a_home_rehoming_emptied…` is HALF
preservation: on 0d487cb0 its `parent_theme == target` assertion already holds (the pointer is #491's
designed case) and its rule-B NOTE assertion is new (fails there on the old "absorbed/superseded"
text); the mutation "blanket-skip the successor for every B name" reddens it on parent_theme (None).

ONE-NIGHT WAIT (operator ruling 2026-10-05, after the first live night retired 20 themes, 10 of them
emptied from >= 3 members that same night): rule B retires a theme only if it was ALREADY under 3
members on its PREVIOUS persisted night (`prior_member_counts`, off the `existing` snapshot); no
previous row -> kept. Mutation record (run on this commit; M1 = the predicate without the prior test,
i.e. the pre-wait rule): M1 reddens the five that expect a theme KEPT or still dropped by the cap
(`..._three_or_more_members_last_night_is_kept`, `..._with_no_previous_row_is_kept`,
`test_a_same_day_rerun_row_is_not_a_previous_night`, `test_the_wait_spares_a_three_member_theme_that_
dropped_to_two`, `test_emptied_from_three_to_zero…`); `prior < MIN` -> `prior <= MIN` reddens the 3-member
boundary three (last-night, wait-spares, emptied); ignoring the toggle reddens the OFF pair; counting a
same-day rerun row as a previous night reddens the helper and rerun tests; treating a missing prior as 0
reddens the no-previous-row and rerun tests. The retire cases are green before and after by
construction. `test_emptied_from_three_to_zero…` pins the NOT-changed edge: Step 4's cap
(PRUNE_MIN_TICKERS = 2, older than rule B) still drops a 0/1-member theme the same night, so the wait
only reaches the 3+ -> 2 shape. The two rule-B e2e tombstone tests moved to a 2-member prior: with a
3-member prior the same fixtures are now the wait.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool
from tests.test_theme_birth_gate import _BOARD_THEME, _FRI, _MON, _drive_engine, _wire_promote

from agents.market_intelligence import audit_events as ae
from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_correctness as tc
from agents.market_intelligence import theme_engine as te

CRUISE = "Cruise & Expedition Travel Operators"      # the #368 guard's case: a healthy pair shown Fading, RS 81
COAL = "Coal Mining Producers"                        # a 2-member weak-Fading shell on the 10-02 board
PIVOT = "Bitcoin Miners Pivoting to AI/HPC Data Center Hosting"
AI = "Emerging AI Compute & Cloud Infrastructure Platforms"


def _row(name, tickers, stage="Fading", rs_avg=None, **kw):
    """One emitted row in the shape `_rescore_existing_theme` returns."""
    return {"theme_date": _MON, "name": name, "stage": stage, "score": 20.0, "rs_avg": rs_avg,
            "description": "d", "tickers": list(tickers), "pct_above_20sma": None,
            "parent_theme": None, "renamed_from": None, **kw}


def _wire_pass(monkeypatch, toggle=True, audit=None):
    events: list[tuple] = []

    async def _audit(event_type, summary="", detail="", **kw):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(te, "log_audit_event", audit or _audit)
    read = AsyncMock(return_value=toggle)
    monkeypatch.setattr(te, "_read_small_fading_retire_toggle", read, raising=False)
    return events, read


def _run(themes, changelog, prior=None):
    """`prior` = last night's member counts by name; DEFAULT = every theme was already at 2 (small
    last night too), so the pass-level cases that predate the one-night wait keep their meaning."""
    if prior is None:
        prior = {t["name"]: 2 for t in themes}
    return asyncio.run(te._retire_small_fading_themes(themes, changelog, prior))


# ═══════════════════════════════ rule B — the pass ═══════════════════════════════════════════


def test_a_two_member_weak_fading_theme_retires_tonight(monkeypatch):
    """RED without the change (the pass does not exist on origin/main)."""
    events, _read = _wire_pass(monkeypatch)
    healthy = _row("Healthy Four", ["A", "B", "C", "D"], stage="Mainstream", rs_avg=85.0)
    themes = [_row(COAL, ["BTU", "CEIX"]), healthy, _row("Remnant", ["X"])]   # 2 members, and the 1-member remnant a #491 move leaves
    changelog: list[dict] = []
    out = _run(themes, changelog)
    assert [t["name"] for t in out] == ["Healthy Four"]
    # ONE named audit row per retirement, summary in the live check's wording
    assert [e[0] for e in events] == [ae.THEME_RETIRED_SMALL_FADING] * 2
    assert events[0][1] == f"{COAL}: retired — weak Fading at 2 members (< 3), #655"
    assert events[1][1] == "Remnant: retired — weak Fading at 1 members (< 3), #655"
    detail = json.loads(events[0][2])
    assert detail["members"] == 2 and detail["tickers"] == ["BTU", "CEIX"]
    assert detail["prior_members"] == 2          # the wait's evidence, on the row the live check reads
    # the 5-night path's own changelog line — the nightly message, the funnel count and the
    # `theme_retired` audit row all come off it
    assert changelog == [
        {"type": "theme_retired", "theme": COAL, "tickers": ["BTU", "CEIX"], "via": "small_fading"},
        {"type": "theme_retired", "theme": "Remnant", "tickers": ["X"], "via": "small_fading"},
    ]


def test_a_scored_or_elite_two_member_theme_is_never_touched(monkeypatch):
    """The #368 guard: a Fading row WITH rs_avg is the scored path (a healthy pair the score-delta or
    hysteresis shows Fading) — not retired, and no toggle read without a weak candidate.
    Mutation: drop `rs_avg is None` from the predicate → red."""
    events, read = _wire_pass(monkeypatch)
    themes = [_row(CRUISE, ["LIND", "VIK"], stage="Fading", rs_avg=81.0),
              _row("Elite Pair", ["P1", "P2"], stage="Mainstream", rs_avg=83.0),
              _row("Weak but Nascent", ["N1", "N2"], stage="Nascent", rs_avg=55.0)]
    changelog: list[dict] = []
    out = _run(themes, changelog)
    assert out == themes and events == [] and changelog == []
    assert read.await_count == 0


def test_three_members_keep_the_five_night_grace(monkeypatch):
    """Mutation: `<` → `<=` → red."""
    events, read = _wire_pass(monkeypatch)
    themes = [_row("Weak Trio", ["A", "B", "C"]), _row("Weak Five", ["A", "B", "C", "D", "E"])]
    out = _run(themes, [])
    assert out == themes and events == [] and read.await_count == 0
    # the boundary is G4's and the coverage floor's: under 3 members
    assert te.SMALL_FADING_RETIRE_MIN_MEMBERS == te.THEME_COVERAGE_MIN == 3
    assert tc.compute_g4([{"name": "x", "tickers": ["A", "B"]}])["small"] == 1
    assert tc.compute_g4([{"name": "x", "tickers": ["A", "B", "C"]}])["small"] == 0
    assert te._is_weak_fading_small(_row("x", ["A", "B"]), 2) is True
    assert te._is_weak_fading_small(_row("x", ["A", "B", "C"]), 2) is False


def test_toggle_off_is_the_old_behaviour(monkeypatch):
    """Mutation: ignore the toggle → red."""
    events, read = _wire_pass(monkeypatch, toggle=False)
    themes = [_row(COAL, ["BTU", "CEIX"]), _row("Healthy", ["A", "B", "C"], stage="Mainstream", rs_avg=80.0)]
    changelog: list[dict] = []
    out = _run(themes, changelog)
    assert out == themes and events == [] and changelog == []
    assert read.await_count == 1          # a candidate existed, so the toggle WAS consulted


def test_a_theme_that_had_three_or_more_members_last_night_is_kept(monkeypatch):
    """THE RULING (operator 2026-10-05): tonight Fading/2 members with 9 last night ('US Regional Bank
    Laggards Rate-Curve Basket' 9 -> 2) gets a night to recover. RED before the wait (retired the
    same night). Mutation: `prior < MIN` -> `prior <= MIN` turns the 3-member case red."""
    events, read = _wire_pass(monkeypatch)
    themes = [_row("Banks 9 to 2", ["JPM", "BAC"]), _row("Telecom 3 to 2", ["T", "VZ"]),
              _row("Nuclear 4 to 2", ["SMR", "OKLO"])]
    changelog: list[dict] = []
    out = _run(themes, changelog, prior={"Banks 9 to 2": 9, "Telecom 3 to 2": 3, "Nuclear 4 to 2": 4})
    assert out == themes and events == [] and changelog == []
    assert read.await_count == 0                  # no retirement candidate -> the toggle is not even read


def test_a_theme_already_small_last_night_is_retired(monkeypatch):
    """The wait is ONE night: under 3 on the previous persisted night too (2, 1 or an emptied 0) ->
    retired tonight, and the audit row carries that previous count."""
    events, _read = _wire_pass(monkeypatch)
    themes = [_row("Two Then Two", ["A", "B"]), _row("One Then One", ["C"]), _row("Zero Then Two", ["D", "E"])]
    changelog: list[dict] = []
    out = _run(themes, changelog, prior={"Two Then Two": 2, "One Then One": 1, "Zero Then Two": 0})
    assert out == []
    assert [json.loads(e[2])["prior_members"] for e in events] == [2, 1, 0]
    assert [c["theme"] for c in changelog] == ["Two Then Two", "One Then One", "Zero Then Two"]


def test_a_theme_with_no_previous_row_is_kept(monkeypatch):
    """No previous persisted row (not in `prior_member_counts`) -> not retired tonight. RED before the
    wait. A mixed night: only the already-small theme goes."""
    events, _read = _wire_pass(monkeypatch)
    themes = [_row("Brand New Shell", ["A", "B"]), _row("Old Shell", ["C", "D"])]
    changelog: list[dict] = []
    out = _run(themes, changelog, prior={"Old Shell": 2})
    assert [t["name"] for t in out] == ["Brand New Shell"]
    assert [json.loads(e[2])["theme"] for e in events] == ["Old Shell"]
    assert te._is_weak_fading_small(_row("x", ["A", "B"]), None) is False


def test_the_wait_does_not_touch_a_scored_pair_or_a_trio(monkeypatch):
    """The wait only NARROWS rule B: a scored Fading pair and a 3-member theme are as untouched as
    ever even when last night's count says small."""
    events, read = _wire_pass(monkeypatch)
    themes = [_row(CRUISE, ["LIND", "VIK"], rs_avg=81.0), _row("Weak Trio", ["A", "B", "C"])]
    out = _run(themes, [], prior={CRUISE: 2, "Weak Trio": 2})
    assert out == themes and events == [] and read.await_count == 0


def test_prior_member_counts_reads_only_nights_before_tonight():
    """PURE. The snapshot is `get_active_themes`' latest row per name; a row dated TONIGHT (a same-day
    'rerun theme engine' reading its own first pass) or with no date is no previous night. RED before
    the wait (the helper does not exist)."""
    import datetime as dt
    today = dt.date(2026, 10, 6)
    existing = [
        {"name": "Last Night", "theme_date": dt.date(2026, 10, 5), "tickers": ["A", "B", "C", "D"]},
        {"name": "Last Friday", "theme_date": dt.date(2026, 10, 2), "tickers": ["E"]},
        {"name": "Emptied", "theme_date": dt.date(2026, 10, 5), "tickers": []},
        {"name": "Rerun Same Day", "theme_date": today, "tickers": ["F", "G"]},
        {"name": "No Date", "tickers": ["H", "I"]},
    ]
    assert te._prior_member_counts(existing, today) == {"Last Night": 4, "Last Friday": 1, "Emptied": 0}


def test_a_same_day_rerun_row_is_not_a_previous_night(monkeypatch):
    """Through the helper into the pass: on a rerun the theme's `existing` row is tonight's own first
    pass (2 members), so it must NOT read as 'already small' — it has no previous row -> kept. RED
    before the wait."""
    events, _read = _wire_pass(monkeypatch)
    existing = [{"name": COAL, "theme_date": _MON, "tickers": ["BTU", "CEIX"]}]
    prior = te._prior_member_counts(existing, _MON)
    themes = [_row(COAL, ["BTU", "CEIX"])]
    assert _run(themes, [], prior=prior) == themes and events == []


def test_a_theme_renamed_this_run_gets_one_night(monkeypatch):
    """Its old name is already tombstoned with the new name as successor; retiring the new name the
    same night would point that lineage at a theme that never got a row."""
    events, _read = _wire_pass(monkeypatch)
    themes = [_row("New Name", ["A", "B"], renamed_from="Old Name")]
    assert _run(themes, []) == themes and events == []


def test_an_audit_row_that_cannot_be_written_keeps_the_theme(monkeypatch):
    """The row IS the live check's evidence — no row, no retirement for that theme tonight."""
    async def _boom(event_type, summary="", detail="", **kw):
        raise RuntimeError("audit down")

    _events, _read = _wire_pass(monkeypatch, audit=_boom)
    themes = [_row(COAL, ["BTU", "CEIX"])]
    changelog: list[dict] = []
    assert _run(themes, changelog) == themes and changelog == []


def test_the_toggle_is_discoverable_by_the_drift_check_and_defaults_on():
    from scripts.live_rules import discover_runtime_toggles
    fact = discover_runtime_toggles()[te.SMALL_FADING_RETIRE_TOGGLE[0]]
    assert fact.env_var == te.SMALL_FADING_RETIRE_TOGGLE[1] and fact.default is True
    assert fact.where.startswith("agents/market_intelligence/theme_engine.py:")


def test_the_audit_events_are_registered():
    assert ae.THEME_RETIRED_SMALL_FADING == "theme_retired_small_fading"
    assert ae.THEME_SMALL_FADING_RETIRE_ERROR == "theme_small_fading_retire_error"


# ═══════════════════════════════ rule B — siting in run_theme_engine ═════════════════════════


def _rehome_audit_row(home: str, target: str, ticker: str) -> dict:
    """The REAL `theme_member_rehomed` summary `_run_rehome_pass` writes for a move (theme_engine
    ~:6298) — the row the engine-drop block reads back as a successor pointer."""
    return {"event_type": te.REHOME_MOVED_EVENT,
            "summary": f"Rehome: '{home}' -> '{target}' {ticker} moved on the tape (0.61 vs own 0.12; leave)",
            "detail": json.dumps({"ticker": ticker, "from": home, "to": target})}


def _drive_with_rehome(monkeypatch, *, small_fading_on: bool, audit_rows=None, move=("CIFR",),
                       weak_tickers=("CIFR", "HUT"), real_cap=False):
    """Drive the REAL run_theme_engine with a weak-Fading pivot theme on the board (its persisted row
    from FRIDAY holds `weak_tickers`, so that count is its previous night's — the one-night wait reads
    it) and a re-homing pass that moves `move` (default CIFR) out of it into the AI theme.
    `audit_rows` = what the engine-drop block's mi_audit_log read returns tonight; DEFAULT = the
    real re-homing row for each move (the mocked pass writes none itself). Returns (saved rows,
    audits mock, order). `real_cap` = run Step 4's REAL `_enforce_max_themes_per_stock` (the shared
    driver passes it through) so a 0/1-member theme is dropped below PRUNE_MIN_TICKERS as in prod."""
    move = list(move)
    if audit_rows is None:
        audit_rows = [_rehome_audit_row(PIVOT, AI, tk) for tk in move]
    cap_fn = te._enforce_max_themes_per_stock
    saved, _discover, _accel, audits = _drive_engine(monkeypatch, mode="off", discovered=[])
    if real_cap:
        monkeypatch.setattr(te, "_enforce_max_themes_per_stock", cap_fn)
    weak = {"name": PIVOT, "stage": "Fading", "score": 20.0, "rs_avg": None, "theme_date": _FRI,
            "tickers": list(weak_tickers), "description": "d"}
    target = {"name": AI, "stage": "Mainstream", "score": 70.0, "rs_avg": 90.0, "theme_date": _FRI,
              "tickers": ["CRWV", "NBIS", "ALAB"], "description": "d"}
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(weak), dict(target)]))
    # members off the leaders list are RS-fetched by name — stub the two DB reads
    monkeypatch.setattr(dbmod, "get_rs_for_tickers", AsyncMock(return_value={
        tk: {"rs_composite": 60.0} for tk in weak["tickers"] + target["tickers"]}))
    monkeypatch.setattr(dbmod, "get_sectors_batch", AsyncMock(return_value={}))
    # the tape context exists and re-homing is ON, so Step 2a.5 runs
    monkeypatch.setattr(te, "_read_assign_comove_toggle", AsyncMock(return_value=True))
    monkeypatch.setattr(te, "_load_comove_context", AsyncMock(return_value=te.ComoveContext(
        before_date=_MON, excess={}, n_sessions=0, n_rows=0)))
    monkeypatch.setattr(te, "_read_rehome_toggle", AsyncMock(return_value=True))
    order: list[str] = []

    async def _rehome(themes, sbt, ctx, **kw):
        order.append("rehome")
        by = {t["name"]: t for t in themes}
        by[PIVOT]["tickers"] = [tk for tk in by[PIVOT]["tickers"] if tk not in move]
        by[AI]["tickers"] = by[AI]["tickers"] + move
        for tk in move:
            kw["changelog"].append({"type": "ticker_rehomed", "ticker": tk, "from": [PIVOT], "theme": AI})
        return {"moved": len(move)}

    monkeypatch.setattr(te, "_run_rehome_pass", _rehome)
    real = te._retire_small_fading_themes

    async def _recorded(themes, changelog, prior_member_counts):
        order.append("small_fading")
        return await real(themes, changelog, prior_member_counts)

    monkeypatch.setattr(te, "_retire_small_fading_themes", _recorded, raising=False)
    monkeypatch.setattr(te, "_read_small_fading_retire_toggle",
                        AsyncMock(return_value=small_fading_on), raising=False)
    # the engine-drop block reads today's successor pointers from mi_audit_log
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=audit_rows)
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    asyncio.run(te.run_theme_engine(trade_date=_MON))
    return saved, audits, order


def test_runs_after_rehoming_so_a_rehomed_member_is_not_double_handled(monkeypatch):
    """RED without rule B: the pivot theme stays on the board as a 1-member Fading row. Its previous
    persisted night was ALREADY 2 members (CIFR, HUT), so the one-night wait does not spare it."""
    saved, audits, order = _drive_with_rehome(monkeypatch, small_fading_on=True)
    assert order == ["rehome", "small_fading"]
    rows = {(r["name"], r["stage"]): r for r in saved}
    # CIFR landed in its new home BEFORE the retire read the pivot theme
    assert "CIFR" in rows[(AI, "Mainstream")]["tickers"]
    # the pivot theme is on tonight's board ONLY as the engine-drop tombstone
    assert (PIVOT, "Fading") not in rows
    tomb = rows[(PIVOT, "Retired")]
    # the REAL re-homing row ("'PIVOT' -> 'AI' CIFR moved") is in tonight's audit read, and it
    # must NOT become the tombstone's successor: HUT was released, not absorbed
    assert tomb["tickers"] == [] and tomb["parent_theme"] is None
    assert "absorbed" not in tomb["description"]
    assert "weak Fading at 1 members (< 3), #655 rule B" in tomb["description"]
    assert "members released: HUT" in tomb["description"]
    names = [c.args[0] for c in audits.await_args_list]
    # the named row counts 1 member (HUT) — the moved name is not double-handled — and carries last
    # night's count, the evidence the one-night wait fired on
    small = next(c for c in audits.await_args_list if c.args[0] == ae.THEME_RETIRED_SMALL_FADING)
    assert small.kwargs["summary"] == f"{PIVOT}: retired — weak Fading at 1 members (< 3), #655"
    detail = json.loads(small.kwargs["detail"])
    assert detail["tickers"] == ["HUT"] and detail["prior_members"] == 2
    # the 5-night path's rows fire for it too: the tombstone's and the retirement's
    assert "theme_auto_retired" in names and "theme_retired" in names
    retired_row = next(c for c in audits.await_args_list if c.args[0] == "theme_retired")
    assert retired_row.kwargs["summary"] == f"Retired: {PIVOT}"
    auto = next(c for c in audits.await_args_list if c.args[0] == "theme_auto_retired")
    assert "(0 with successor pointer)" in auto.kwargs["summary"]
    assert f"'{PIVOT}' -> parent='(unknown)'" in auto.kwargs["detail"]


def test_a_home_rehoming_emptied_to_zero_keeps_the_rehoming_target_as_successor(monkeypatch):
    """The ONE case the re-homing pointer is true for a B-retired theme: re-homing moved EVERY
    member out (#491's "a home emptied by its members leaving points at where they went"). B then
    retires the 0-member shell tonight (it was already a 2-member pair last night) and the tombstone
    keeps parent_theme = the target — the same pointer the Step 4 cap drop writes for it with the
    toggle OFF. On 0d487cb0 the pointer assertion holds and the note assertion is new (red there on
    the generic "absorbed" text); blanket-skipping the successor for every B name reddens it on
    parent_theme (None)."""
    moves = ["CIFR", "HUT"]
    audit_rows = [_rehome_audit_row(PIVOT, AI, tk) for tk in moves]
    saved, audits, order = _drive_with_rehome(monkeypatch, small_fading_on=True,
                                              audit_rows=audit_rows, move=moves)
    assert order == ["rehome", "small_fading"]
    rows = {(r["name"], r["stage"]): r for r in saved}
    assert set(moves) <= set(rows[(AI, "Mainstream")]["tickers"])
    assert (PIVOT, "Fading") not in rows
    tomb = rows[(PIVOT, "Retired")]
    assert tomb["tickers"] == [] and tomb["parent_theme"] == AI
    assert f"weak Fading at 0 members (< 3), #655 rule B — emptied by re-homing into '{AI}'" in tomb["description"]
    small = next(c for c in audits.await_args_list if c.args[0] == ae.THEME_RETIRED_SMALL_FADING)
    assert small.kwargs["summary"] == f"{PIVOT}: retired — weak Fading at 0 members (< 3), #655"
    auto = next(c for c in audits.await_args_list if c.args[0] == "theme_auto_retired")
    assert "(1 with successor pointer)" in auto.kwargs["summary"]


def test_the_wait_spares_a_three_member_theme_that_dropped_to_two(monkeypatch):
    """THE RULING through the real run_theme_engine ('Legacy Telecom…' 3 -> 2 after a wrong validator
    removal): 3 members last night, 2 tonight -> NOT retired — it stays on the board as a 2-member
    Fading row, with no tombstone and no rule-B audit row. RED before the wait (retired the same
    night). Mutation: ignore `prior_member_counts` -> red."""
    saved, audits, order = _drive_with_rehome(
        monkeypatch, small_fading_on=True, weak_tickers=("CIFR", "HUT", "WULF"), move=("CIFR",))
    assert order == ["rehome", "small_fading"]
    rows = {(r["name"], r["stage"]): r for r in saved}
    assert rows[(PIVOT, "Fading")]["tickers"] == ["HUT", "WULF"]
    assert (PIVOT, "Retired") not in rows
    names = [c.args[0] for c in audits.await_args_list]
    assert ae.THEME_RETIRED_SMALL_FADING not in names and "theme_auto_retired" not in names


def test_emptied_from_three_to_zero_is_still_dropped_the_same_night_by_the_cap(monkeypatch):
    """NOT CHANGED by the wait ('Small Modular Reactor…' 4 -> 0): rule B spares it (3+ members last
    night) but Step 4's cap — PRUNE_MIN_TICKERS = 2, older than rule B — drops any theme below 2
    members, so a 0/1-member theme still leaves the same night. Its tombstone is the cap drop's
    (the re-homing successor, an 'absorbed' note), not rule B's. The wait only reaches 3+ -> 2."""
    moves = ["CIFR", "HUT", "WULF"]
    saved, audits, _order = _drive_with_rehome(
        monkeypatch, small_fading_on=True, weak_tickers=tuple(moves), move=moves, real_cap=True)
    rows = {(r["name"], r["stage"]): r for r in saved}
    assert (PIVOT, "Fading") not in rows
    tomb = rows[(PIVOT, "Retired")]
    assert tomb["tickers"] == [] and tomb["parent_theme"] == AI
    assert "rule B" not in tomb["description"] and "absorbed/superseded" in tomb["description"]
    names = [c.args[0] for c in audits.await_args_list]
    assert "theme_cap_drop" in names and ae.THEME_RETIRED_SMALL_FADING not in names


def test_toggle_on_retires_an_unmoved_pair_that_was_already_a_pair(monkeypatch):
    """The OFF test's mirror (same fixture, toggle ON): a 2-member weak-Fading theme that was a
    2-member theme last night is retired. Mutation: ignore the toggle -> the OFF test goes red."""
    saved, _audits, _order = _drive_with_rehome(monkeypatch, small_fading_on=True, move=())
    rows = {(r["name"], r["stage"]): r for r in saved}
    assert (PIVOT, "Fading") not in rows and (PIVOT, "Retired") in rows


def test_toggle_off_in_the_engine_keeps_the_two_member_theme_on_the_board(monkeypatch):
    saved, audits, order = _drive_with_rehome(monkeypatch, small_fading_on=False, move=())
    assert order == ["rehome", "small_fading"]
    rows = {(r["name"], r["stage"]): r for r in saved}
    assert rows[(PIVOT, "Fading")]["tickers"] == ["CIFR", "HUT"]
    assert (PIVOT, "Retired") not in rows
    names = [c.args[0] for c in audits.await_args_list]
    assert ae.THEME_RETIRED_SMALL_FADING not in names and "theme_auto_retired" not in names


# ═══════════════════════════════ bug E — the promote lane ════════════════════════════════════


@pytest.mark.asyncio
async def test_a_tombstone_prior_is_a_first_crossing_so_the_join_arm_fires(monkeypatch):
    """RED without the change: the tombstone read as a live prior, the gate was never consulted and
    the duplicate cohort was re-minted over its live twin (the 10-02 'Defense & Space…' shape)."""
    conn, tele, _ = _wire_promote(
        monkeypatch,
        [{"name": "Dup Cohort", "tickers": ["J1", "J2", "J3"], "thesis": "t", "source": "narrative_cogap"}],
        mode="dedup_only",
        prior_rows=[{"name": "Dup Cohort", "days_active": 4, "stage": "Retired"}])
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(_BOARD_THEME)]))
    n = await te.promote_shadow_themes(_MON)
    assert n == 0
    assert not [c for c in conn.execute.await_args_list if "INSERT INTO mi_themes" in c.args[0]]
    rec = dbmod.record_birth_candidate_sighting
    assert rec.await_args.kwargs["outcome"] == "join" and rec.await_args.kwargs["join_target"] == "Board Name"
    tele.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_tombstone_prior_that_passes_the_gate_keeps_days_active_continuity(monkeypatch):
    """Continuity is NOT part of the defect: a returning cohort the gate births resumes its counter."""
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Returning Theme", "tickers": ["R1", "R2", "R3"], "thesis": "t", "source": "narrative_cogap"}],
        mode="dedup_only",
        prior_rows=[{"name": "Returning Theme", "days_active": 4, "stage": "Retired"}])
    monkeypatch.setattr(dbmod, "get_recent_birth_candidates", AsyncMock(return_value=[
        {"id": 11, "name": "Returning Theme", "first_seen": _FRI, "last_seen": _FRI,
         "sightings": 1, "tickers": ["R1", "R2", "R3"], "status": "watching"}]))
    monkeypatch.setattr(dbmod, "get_cohort_rs_snapshot", AsyncMock(return_value=(84.0, 80.0)))
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    dbmod.record_birth_candidate_sighting.assert_awaited()          # the gate WAS consulted
    ins = next(c for c in conn.execute.await_args_list if "INSERT INTO mi_themes" in c.args[0])
    assert ins.args[2] == "Returning Theme" and ins.args[6] == 5    # days_active = prior 4 + 1


@pytest.mark.asyncio
async def test_a_live_prior_is_maintenance_and_the_gate_is_not_consulted(monkeypatch):
    """Mutation: `_first_crossing = True` → red."""
    conn, _, _ = _wire_promote(
        monkeypatch,
        [{"name": "Established Theme", "tickers": ["J1", "J2", "J3"], "thesis": "t", "source": "narrative_cogap"}],
        mode="dedup_only",
        prior_rows=[{"name": "Established Theme", "days_active": 9, "stage": "Fading"}])
    monkeypatch.setattr(te, "get_active_themes", AsyncMock(return_value=[dict(_BOARD_THEME)]))
    n = await te.promote_shadow_themes(_MON)
    assert n == 1
    assert [c.args[2] for c in conn.execute.await_args_list
            if "INSERT INTO mi_themes" in c.args[0]] == ["Established Theme"]
    dbmod.record_birth_candidate_sighting.assert_not_awaited()
