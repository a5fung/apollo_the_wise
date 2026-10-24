"""#491 U2 (2026-10-23) — the nightly shadow promotion honours the rehome cooldown wall.

THE BUG (found 10-23, `scripts/probes/_verify_1023/task_491.md`): the re-homing pass MOVES a stock out of
its home and writes a 14-day `(ticker, home)` cooldown. The home, left with 1-2 members, is retired that
night. The next night `promote_shadow_themes` re-graduated the SAME shadow cohort — moved stock included —
as a 3-member `shadow_promoted` row under the home's name: 4 of 32 moves bounced straight back (MKSI 10-07,
PAYX 10-16, YUM 10-16, CXM 10-21). The promotion path read no cooldown, ban or exclusion.

THE FIX: `_strip_guarded_promotion_members` removes, from each cohort about to graduate, every member the
engine's ONE hard guard (`_hard_guard_refusal`: an operator exclusion, then a live cooldown FROM that
theme's name) bars — AFTER canonicalization (the cooldown is keyed on the live name), BEFORE every lookup.
A cohort left under `_PROMOTE_MIN_MEMBERS` is not graduated and is not a "silent failure". The operator's
`/promotetheme` is his ruling and is NOT filtered. A failed read stops the run (no empty-set fallback).

No DB, no network, no model. Mutation checks recorded in the commit: deleting the strip call, stripping
BEFORE canonicalization, deleting the floor hold, deleting `- n_guard_held` from the alarm, and dropping
the cooldown arm of `_hard_guard_refusal` each turn a NAMED test here red.
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_engine as te
from tests.conftest import make_mock_pool, stub_promotion_guards

_TODAY = _dt.date(2026, 10, 8)
_TOMORROW = _dt.date(2026, 10, 9)

SOURCE = "Semiconductor Capital Equipment & Process Control"   # the theme the stock was moved OUT of
OTHER = "Enterprise Software Platforms"
MOVED = "MKSI"


def _cand(name, tickers, source="shadow_v2"):
    return {"name": name, "tickers": list(tickers), "thesis": "t", "source": source}


def _wire(monkeypatch, cands, *, cooldowns=(), exclusions=None, execute="INSERT 0 1", canonicalize=None):
    """The real `promote_shadow_themes` over a mocked pool: three conn.fetch calls (prior rows, prior
    description rows, RS rows), the cooldown + exclusion readers pinned to `cooldowns` / `exclusions`."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], [], []])
    conn.execute = AsyncMock(return_value=execute)
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names",
                        canonicalize or AsyncMock(return_value=0))
    audit = AsyncMock()
    monkeypatch.setattr(te, "log_audit_event", audit)
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))
    monkeypatch.setattr(te, "_map_ecosystems_nonfatal", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    tele = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tele)
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=cands))
    guards = stub_promotion_guards(monkeypatch, cooldowns=cooldowns, exclusions=exclusions)
    return conn, audit, tele, guards


def _written(conn):
    """{theme name: tickers written} from the mi_themes INSERTs (sql, today, name, score, desc, tickers, …)."""
    return {c.args[2]: c.args[5] for c in conn.execute.await_args_list
            if "INSERT INTO mi_themes" in c.args[0]}


def _skips(audit):
    import json
    return [json.loads(c.kwargs["detail"]) for c in audit.await_args_list
            if c.args and c.args[0] == te._PROMOTE_GUARD_EVENT]


# ════════════════ 1. The ONE guard — pure, and shared with the membership path ════════════════


def test_hard_guard_refusal_order_keying_and_the_shared_membership_path():
    cd = {(MOVED, SOURCE)}
    # exclusion first, then cooldown, then nothing
    assert te._hard_guard_refusal(MOVED, SOURCE, {MOVED}, cd) == "exclusion"
    assert te._hard_guard_refusal(MOVED, SOURCE, set(), cd) == "cooldown"
    assert te._hard_guard_refusal("OTHR", SOURCE, set(), cd) is None
    # keyed on the PAIR: the same stock under a different theme's name is not barred
    assert te._hard_guard_refusal(MOVED, OTHER, set(), cd) is None
    assert te._hard_guard_refusal(MOVED, SOURCE, set(), None) is None
    assert te._hard_guard_refusal(MOVED, SOURCE, set(), set()) is None
    # `_membership_path` (sector-cap re-homing + the #655 fold) is built ON it — one definition
    assert te._membership_path(MOVED, SOURCE, ["A", "B"], None, {MOVED}, cd) == ("exclusion", None)
    assert te._membership_path(MOVED, SOURCE, ["A", "B"], None, set(), cd) == ("cooldown", None)
    assert te._membership_path(MOVED, OTHER, ["A", "B"], None, set(), cd) == ("unjudgeable", None)


def test_strip_removes_only_pairs_barred_from_that_theme_and_leaves_others_untouched():
    themes = [
        {"name": SOURCE, "tickers": ["A", "B", MOVED, "D"], "source": "shadow_v2"},
        {"name": OTHER, "tickers": ["E", MOVED, "G"], "source": "narrative_cogap"},   # same stock, other theme
        {"name": "Untouched", "tickers": ["X", "Y", "Z"], "source": "shadow_v2"},
    ]
    refusals = te._strip_guarded_promotion_members(themes, {(MOVED, SOURCE)}, None)
    assert [t["tickers"] for t in themes] == [["A", "B", "D"], ["E", MOVED, "G"], ["X", "Y", "Z"]]
    assert refusals == [{"theme": SOURCE, "ticker": MOVED, "reason": "cooldown",
                         "source": "shadow_v2", "kept": 3}]
    assert themes[0]["guard_refused"] == 1 and "guard_refused" not in themes[1]
    assert "guard_refused" not in themes[2]


def test_strip_with_no_bar_changes_nothing_and_returns_no_refusal():
    themes = [{"name": SOURCE, "tickers": ["A", "B", MOVED], "source": "shadow_v2"}]
    assert te._strip_guarded_promotion_members(themes, set(), {}) == []
    assert te._strip_guarded_promotion_members(themes, None, None) == []
    assert themes[0]["tickers"] == ["A", "B", MOVED] and "guard_refused" not in themes[0]


def test_strip_honours_an_operator_exclusion_incl_a_reworded_theme_name():
    # exclusions survive a Claude rename (fuzzy word-overlap net) — the same lookup every other path uses
    themes = [{"name": "Semiconductor Capital Equipment & Process Control Tools",
               "tickers": ["A", "B", "C", "EXC"], "source": "shadow_v2"}]
    refusals = te._strip_guarded_promotion_members(themes, set(), {SOURCE: {"EXC"}})
    assert themes[0]["tickers"] == ["A", "B", "C"]
    assert [(r["ticker"], r["reason"]) for r in refusals] == [("EXC", "exclusion")]


# ════════════════ 2. The nightly promotion, end to end (real function, mocked pool) ════════════════


@pytest.mark.asyncio
async def test_a_promoted_cohort_does_not_re_add_a_stock_under_a_rehome_cooldown(monkeypatch):
    """THE BUG: MKSI was moved out of SOURCE on 10-07 (cooldown on (MKSI, SOURCE)); the shadow cohort
    {A, B, C, MKSI} re-graduates under SOURCE's name. It must graduate WITHOUT MKSI, and say why."""
    conn, audit, tele, _ = _wire(
        monkeypatch, [_cand(SOURCE, ["A", "B", "C", MOVED])], cooldowns={(MOVED, SOURCE)})
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 1
    assert _written(conn) == {SOURCE: ["A", "B", "C"]}                     # the rest proceeds
    skips = _skips(audit)
    assert len(skips) == 1 and skips[0]["ticker"] == MOVED and skips[0]["path"] == "cooldown"
    assert skips[0]["theme"] == SOURCE and skips[0]["held_below_floor"] is False and skips[0]["kept"] == 3
    # the named reason is in the plain-words summary an operator reads
    skip_row = next(c for c in audit.await_args_list if c.args and c.args[0] == te._PROMOTE_GUARD_EVENT)
    assert MOVED in skip_row.kwargs["summary"] and "cooldown" in skip_row.kwargs["summary"]
    # the RS batch was asked about the kept members only (rs_avg / breadth are over what is written)
    assert MOVED not in conn.fetch.await_args_list[2].args[1]


@pytest.mark.asyncio
async def test_a_cohort_with_no_barred_member_is_unaffected_byte_for_byte(monkeypatch):
    conn, audit, _, _ = _wire(
        monkeypatch,
        [_cand(SOURCE, ["A", "B", "C", MOVED]), _cand(OTHER, ["E", "F", "G"])],
        # a cooldown on the same stock from ANOTHER theme, and on another stock from this one: neither bars
        cooldowns={(MOVED, "Some Unrelated Theme"), ("ZZZ", SOURCE)})
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 2
    assert _written(conn) == {SOURCE: ["A", "B", "C", MOVED], OTHER: ["E", "F", "G"]}
    assert _skips(audit) == []
    promo = next(c for c in audit.await_args_list if c.args and c.args[0] == "shadow_themes_promoted")
    assert "member floor" not in promo.kwargs["summary"]


@pytest.mark.asyncio
async def test_the_cooldowns_expiry_re_admits_the_stock(monkeypatch):
    """Night 1 the pair is in the active set -> left out. 14 days on, `get_cooldown_set` (whose SQL is
    `cooldown_until > NOW()`, pinned below) no longer returns it -> the SAME cohort writes MKSI again."""
    cohort = [_cand(SOURCE, ["A", "B", "C", MOVED])]
    conn1, audit1, _, _ = _wire(monkeypatch, cohort, cooldowns={(MOVED, SOURCE)})
    await te.promote_shadow_themes(_TODAY)
    assert _written(conn1) == {SOURCE: ["A", "B", "C"]} and len(_skips(audit1)) == 1

    conn2, audit2, _, _ = _wire(monkeypatch, cohort, cooldowns=set())      # the row has expired
    await te.promote_shadow_themes(_TODAY + _dt.timedelta(days=15))
    assert _written(conn2) == {SOURCE: ["A", "B", "C", MOVED]} and _skips(audit2) == []


@pytest.mark.asyncio
async def test_the_reader_filters_expired_and_bypassed_rows_in_sql_and_shares_the_writers_table():
    """Expiry is the READER's job (so the engine needs no clock): active = `NOT bypassed AND
    cooldown_until > NOW()`, over the same (ticker, theme_name) table `add_validation_cooldown` writes."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"ticker": MOVED, "theme_name": SOURCE}])
    import unittest.mock as um
    with um.patch.object(dbmod, "get_pool", AsyncMock(return_value=pool)):
        got = await dbmod.get_cooldown_set()
    assert got == {(MOVED, SOURCE)}
    sql = conn.fetch.await_args.args[0]
    assert "mi_validation_cooldowns" in sql and "NOT bypassed" in sql and "cooldown_until > NOW()" in sql
    # the WRITER (what the rehome pass calls) targets the same table and the same (ticker, theme) key
    wpool, wconn = make_mock_pool()
    wconn.fetchrow = AsyncMock(return_value={"removal_count": 1})
    with um.patch.object(dbmod, "get_pool", AsyncMock(return_value=wpool)):
        await dbmod.add_validation_cooldown(MOVED, SOURCE, reason="rehome: moved", days=14)
    wsql, w_ticker, w_theme = wconn.fetchrow.await_args.args[:3]
    assert "INSERT INTO mi_validation_cooldowns (ticker, theme_name" in wsql
    assert (w_ticker, w_theme) == (MOVED, SOURCE)


@pytest.mark.asyncio
async def test_a_cohort_left_under_the_member_floor_is_held_and_is_not_a_silent_failure(monkeypatch):
    """All four bounce rows were exactly 3 members holding the moved stock. Stripped they are 2: the
    floor (`_PROMOTE_MIN_MEMBERS`) holds, no 2-member half-state is written, and the zero-writes alarm
    (a Telegram + `shadow_promotion_silent_failure`) does NOT fire for a deliberate hold."""
    conn, audit, tele, _ = _wire(
        monkeypatch, [_cand(SOURCE, ["A", "B", MOVED])], cooldowns={(MOVED, SOURCE)})
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 0 and _written(conn) == {}
    skips = _skips(audit)
    assert len(skips) == 1 and skips[0]["held_below_floor"] is True and skips[0]["kept"] == 2
    names = [c.args[0] for c in audit.await_args_list if c.args]
    assert "shadow_promotion_silent_failure" not in names
    tele.assert_not_awaited()
    promo = next(c for c in audit.await_args_list if c.args and c.args[0] == "shadow_themes_promoted")
    assert "1 held under the member floor" in promo.kwargs["summary"]


@pytest.mark.asyncio
async def test_the_zero_writes_alarm_still_fires_for_a_real_failure(monkeypatch):
    """Control for the alarm subtraction: it removes ONLY floor-held cohorts. A cohort that qualified and
    wrote nothing for any other reason (the upsert guard skipped it) still pages."""
    conn, audit, tele, _ = _wire(
        monkeypatch, [_cand(SOURCE, ["A", "B", "C"])], execute="INSERT 0 0")
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 0
    assert "shadow_promotion_silent_failure" in [c.args[0] for c in audit.await_args_list if c.args]
    tele.assert_awaited_once()


@pytest.mark.asyncio
async def test_one_held_cohort_does_not_hide_a_failure_in_another(monkeypatch):
    conn, audit, tele, _ = _wire(
        monkeypatch,
        [_cand(SOURCE, ["A", "B", MOVED]), _cand(OTHER, ["E", "F", "G"])],
        cooldowns={(MOVED, SOURCE)}, execute="INSERT 0 0")
    await te.promote_shadow_themes(_TODAY)
    # SOURCE held at the floor (deliberate); OTHER qualified and the upsert wrote nothing -> still pages
    assert "shadow_promotion_silent_failure" in [c.args[0] for c in audit.await_args_list if c.args]


@pytest.mark.asyncio
async def test_the_strip_runs_after_canonicalization_so_the_live_name_is_the_key(monkeypatch):
    """The cooldown is keyed on the LIVE name. The shadow lane names the cohort differently; canonicalization
    converges it to SOURCE only because the FULL ticker set matches the live row. Stripping first would leave
    the cohort under its shadow name, the wall would never match and the bounce would proceed relabelled."""
    async def _canon(conn, themes, today):
        for t in themes:
            if set(t["tickers"]) == {"A", "B", "C", MOVED}:      # matches the live row only as the FULL set
                t["name"] = SOURCE
        return 1
    conn, audit, _, _ = _wire(
        monkeypatch, [_cand("Semicap Process Control (shadow name)", ["A", "B", "C", MOVED])],
        cooldowns={(MOVED, SOURCE)}, canonicalize=_canon)
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 1 and _written(conn) == {SOURCE: ["A", "B", "C"]}
    assert _skips(audit)[0]["theme"] == SOURCE


@pytest.mark.asyncio
async def test_an_operator_exclusion_also_keeps_a_member_out_of_the_promotion(monkeypatch):
    conn, audit, _, _ = _wire(
        monkeypatch, [_cand(SOURCE, ["A", "B", "C", "EXC"])], exclusions={SOURCE: {"EXC"}})
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 1 and _written(conn) == {SOURCE: ["A", "B", "C"]}
    assert [(s["ticker"], s["path"]) for s in _skips(audit)] == [("EXC", "exclusion")]


@pytest.mark.asyncio
async def test_a_failed_guard_read_stops_the_run_it_never_falls_back_to_an_empty_wall(monkeypatch):
    conn, audit, _, (cd, _ex) = _wire(monkeypatch, [_cand(SOURCE, ["A", "B", "C", MOVED])])
    cd.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError, match="db down"):
        await te.promote_shadow_themes(_TODAY)
    assert _written(conn) == {}


@pytest.mark.asyncio
async def test_no_qualifying_cohort_reads_nothing(monkeypatch):
    """The early return is untouched: no cohort -> neither guard is read (no extra DB round trip)."""
    conn, audit, _, (cd, ex) = _wire(monkeypatch, [_cand("Too Small", ["A", "B"])])
    assert await te.promote_shadow_themes(_TODAY) == 0
    cd.assert_not_awaited()
    ex.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_operators_promotetheme_is_a_ruling_and_is_not_filtered(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    upsert = AsyncMock(return_value=True)
    monkeypatch.setattr(te, "_upsert_promoted_theme", upsert)
    monkeypatch.setattr(te, "_map_ecosystems_nonfatal", AsyncMock())
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates",
                        AsyncMock(return_value=[_cand(SOURCE, ["A", "B", "C", MOVED])]))
    cd, ex = stub_promotion_guards(monkeypatch, cooldowns={(MOVED, SOURCE)})
    res = await te.promote_candidate_by_name("Semiconductor Capital", _TODAY)
    assert res["status"] == "promoted"
    assert upsert.await_args.args[2] == ["A", "B", "C", MOVED]        # (conn, name, tickers, …)
    assert res["tickers"] == ["A", "B", "C", MOVED]
    cd.assert_not_awaited()
    ex.assert_not_awaited()
