"""The #491 RE-HOMING PASS — custody by the tape (theme_engine, 2026-10-03, operator-signed "Rec on all").

A stock whose business pivoted could never LEAVE its legacy theme: a covered member is never offered
to another theme. This pass reads every member against every live theme on the engine's own
market-adjusted tape, offers the misfiled ones (#655 G2's signed shape, plus the unjudgeable-home arm
for a 2-member home) to the SAME assignment judgement, and on a confirmed fit MOVES the member:
appended to the target, stripped from every home, a 14-day (name, home) cooldown the global ban
ignores, an audit row and a message line. Feeder (iii) carries a join-suppressed newborn's novel
uncovered members to the join target. The orphan reach (D2) was ruled NO — a name in no theme is
never reached, and that is asserted here.

Shapes (synthetic tape, four factors): the AI-compute theme (4 members on factor A), the 2-member
Fading pivot theme whose members move on factor A (CIFR/HUT), a SaaS theme on factor C holding one
misfiled factor-A name, a bitcoin theme on factor B, a Fading power theme on factor A (a target the
pass must never choose), three homeless factor-A names (IREN/WULF/CORZ) and a noise name.

Every call goes through the REAL `_assign_uncovered_to_themes` with a scripted model client; no DB,
no network, no model. Mutation checks recorded in the commit: deleting the strip line, the cap
check, the cooldown write or the Fading refusal each turns a NAMED test here red.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import ep_theme_belonging as etb
from agents.market_intelligence import theme_correctness as tc
from agents.market_intelligence import theme_engine as te
from tests.test_theme_batching import _assign_tool_resp, _fake_client, _quiet_infra

BEFORE = date(2026, 9, 8)

AI = "Emerging AI Compute & Cloud Infrastructure Platforms"
PIVOT = "Bitcoin Miners Pivoting to AI/HPC Data Center Hosting"
SAAS = "Enterprise Software Platforms"
BTC = "Bitcoin Holding & Trading Proxy Equities"
POWER = "AI Power Buildout (fading)"

AI_MEMBERS = ["CRWV", "NBIS", "ALAB", "AIX1"]
PIVOT_MEMBERS = ["CIFR", "HUT"]
SAAS_MEMBERS = ["SNOW", "MDB", "DDOG", "MISF"]      # MISF moves on factor A — misfiled
BTC_MEMBERS = ["MARA", "RIOT", "ABTC"]
POWER_MEMBERS = ["PWR1", "PWR2", "PWR3"]
ORPHANS = ["IREN", "WULF", "CORZ"]


def _tape(seed: int = 491, n: int = 110, start: date = date(2026, 5, 10)):
    rng = np.random.default_rng(seed)
    days = [start + timedelta(days=i) for i in range(n)]
    mkt = rng.normal(0, 0.01, n)
    fa, fb, fc = (rng.normal(0, 0.02, n) for _ in range(3))

    def closes(sig):
        return dict(zip(days, (100.0 * np.exp(np.cumsum(sig))).tolist()))

    def on(fac):
        return closes(mkt + fac + rng.normal(0, 0.008, n))

    tape = {"SPY": closes(mkt), "NOIS": closes(mkt + rng.normal(0, 0.02, n))}
    for tk in AI_MEMBERS + PIVOT_MEMBERS + ORPHANS + POWER_MEMBERS + ["MISF"]:
        tape[tk] = on(fa)
    for tk in BTC_MEMBERS:
        tape[tk] = on(fb)
    for tk in ["SNOW", "MDB", "DDOG"]:
        tape[tk] = on(fc)
    return tape


def _ctx(tape, before=BEFORE) -> te.ComoveContext:
    cs = etb.session_index(tape["SPY"], before, etb.BELONGING_LOOKBACK_SESSIONS)
    mk = etb.log_returns(tape["SPY"], cs)
    ex = etb.excess_returns(tape, cs, mk)
    return te.ComoveContext(before_date=before, excess=ex, n_sessions=len(cs) - 1, n_rows=0)


def _board():
    return [
        {"name": AI, "stage": "Mainstream", "score": 70.0, "tickers": list(AI_MEMBERS),
         "description": "neoclouds selling AI compute and GPU capacity"},
        {"name": PIVOT, "stage": "Fading", "score": 20.0, "tickers": list(PIVOT_MEMBERS),
         "description": "bitcoin miners converting power to AI/HPC hosting"},
        {"name": SAAS, "stage": "Nascent", "score": 55.0, "tickers": list(SAAS_MEMBERS),
         "description": "enterprise application software"},
        {"name": BTC, "stage": "Accelerating", "score": 60.0, "tickers": list(BTC_MEMBERS),
         "description": "bitcoin treasury and mining proxies"},
        {"name": POWER, "stage": "Fading", "score": 30.0, "tickers": list(POWER_MEMBERS),
         "description": "power generation for AI data centers"},
    ]


def _sbt(monkeypatch):
    from agents.market_intelligence import universe
    out = {}
    for tk in AI_MEMBERS + PIVOT_MEMBERS + SAAS_MEMBERS + BTC_MEMBERS + POWER_MEMBERS + ORPHANS + ["NOIS"]:
        monkeypatch.setitem(universe.TICKER_DESC, tk, f"{tk} business description")
        out[tk] = {"ticker": tk, "rs_composite": 40.0, "sector": "Technology"}
    return out


def _by_name(themes):
    return {t["name"]: t for t in themes}


# ═══════════════════════════════ pure parts ═══════════════════════════════════════════════════

def test_g2_margin_is_the_signed_correctness_margin():
    assert te.REHOME_G2_MARGIN == tc.G2_MARGIN == 0.20
    assert te.REHOME_PER_TARGET_CAP == 3 and te.REHOME_COOLDOWN_DAYS == 14 and te.REHOME_REJUDGE_DAYS == 14
    assert te.REHOME_DEFAULT_ON is True


@pytest.mark.parametrize("own,reason,other,want", [
    (None, "thin_basket", 0.60, (True, "own_unjudgeable:thin_basket")),   # the CIFR/HUT shape (D3 arm)
    (0.20, "below_bar", 0.60, (True, "g2_misfiled")),                      # G2's signed shape
    (0.15, "below_bar", 0.35, (True, "g2_misfiled")),                      # both bounds inclusive
    (0.20, "below_bar", 0.39, (False, "margin_not_met")),
    (0.80, "comoves", 0.65, (False, "own_at_or_above_bar")),               # the CRWV shape
    (None, "thin_basket", 0.30, (False, "other_below_bar")),
    (0.10, "below_bar", None, (False, "other_unjudgeable")),
])
def test_leave_trigger_arms(own, reason, other, want):
    assert te._rehome_trigger(own, reason, other) == want


def test_pair_tie_matches_the_engine_verdict_for_every_member_against_every_theme():
    """The pass reads pairs through pre-built baskets; `_comove_verdict` builds one per call. Same
    maths, same bar, same thin/no-history reasons — asserted for every (name, theme) pair on the
    board, members (leave-one-out) and non-members alike."""
    ctx = _ctx(_tape())
    themes = _board()
    baskets = te._rehome_baskets(themes, ctx)
    names = {tk for t in themes for tk in t["tickers"]} | set(ORPHANS) | {"NOIS", "GHOST"}
    checked = 0
    for t in themes:
        for tk in sorted(names):
            corr, reason, used = te._rehome_pair_tie(tk, baskets.get(t["name"]), ctx)
            cv = te._comove_verdict(tk, t["tickers"], ctx)
            assert cv is not None
            assert corr == cv.corr, (tk, t["name"])
            assert reason == cv.reason, (tk, t["name"], reason, cv.reason)
            if cv.corr is not None:
                assert used == cv.basket_n
            checked += 1
    assert checked == len(themes) * len(names)
    # the 2-member pivot theme reads thin for its own members (leave-one-out basket of 1)
    assert te._rehome_pair_tie("CIFR", baskets.get(PIVOT), ctx)[1] == "thin_basket"
    assert baskets.get(PIVOT) is None


def test_cifr_hut_fire_on_the_unjudgeable_arm_toward_the_ai_theme_and_crwv_never_moves():
    ctx = _ctx(_tape())
    cands, pre_cap = te._rehome_candidates(_board(), ctx)
    by = {c.ticker: c for c in cands}
    for tk in PIVOT_MEMBERS:
        c = by[tk]
        assert c.homes == (PIVOT,) and c.arm == "own_unjudgeable:thin_basket" and c.own_corr is None
        assert c.target == AI and c.target_corr >= te.ASSIGN_COMOVE_BAR
        assert c.shortlist and c.shortlist[0][0] == AI
    # the misfiled SaaS member fires G2 proper
    assert by["MISF"].arm == "g2_misfiled" and by["MISF"].homes == (SAAS,) and by["MISF"].target == AI
    assert by["MISF"].own_corr is not None and by["MISF"].own_corr < te.ASSIGN_COMOVE_BAR
    # well-homed members never become candidates
    for tk in AI_MEMBERS + ["SNOW", "MDB", "DDOG"] + BTC_MEMBERS:
        assert tk not in by, tk
    # the three POWER members (a Fading HOME on factor A) fire too — six candidates, none capped
    assert set(by) == set(PIVOT_MEMBERS) | {"MISF"} | set(POWER_MEMBERS)
    assert pre_cap == len(cands) == 6


def test_a_fading_theme_is_read_as_a_home_but_never_chosen_as_a_target():
    ctx = _ctx(_tape())
    cands, _ = te._rehome_candidates(_board(), ctx)
    assert all(c.target != POWER for c in cands)
    assert all(name != POWER for c in cands for name, _corr in c.shortlist)
    # and the Fading POWER members themselves are read as a home: they move on factor A with the
    # AI theme, so they fire too — the pass offers them to the AI theme, not the other way round
    cands_all, _ = te._rehome_candidates(_board(), ctx, max_candidates=50)
    power = [c for c in cands_all if c.ticker in POWER_MEMBERS]
    assert power and all(c.target == AI and c.homes == (POWER,) for c in power)


def test_orphans_in_no_theme_are_never_reached_by_the_leave_feeder():
    """D2 ruled NO: a name in no live theme waits for its RS or a Lane-2 seed. IREN/WULF/CORZ move
    on factor A exactly like the AI theme and are still never candidates."""
    ctx = _ctx(_tape())
    cands, _ = te._rehome_candidates(_board(), ctx, max_candidates=100)
    assert not {c.ticker for c in cands} & set(ORPHANS)
    for tk in ORPHANS:   # the tape WOULD admit them — the feeder simply has no home to read
        assert te._comove_verdict(tk, AI_MEMBERS, ctx).admit is True


def test_protected_pairs_recently_judged_and_banned_names_are_skipped():
    ctx = _ctx(_tape())
    cands, pre = te._rehome_candidates(_board(), ctx, protected={("CIFR", PIVOT)})
    assert "CIFR" not in {c.ticker for c in cands} and "HUT" in {c.ticker for c in cands}
    cands, pre = te._rehome_candidates(_board(), ctx, skip_tickers={"HUT", "MISF"})
    assert {c.ticker for c in cands} == {"CIFR"} | set(POWER_MEMBERS) and pre == 4


def test_candidates_are_ranked_by_target_tape_and_capped_with_the_precap_count_kept():
    ctx = _ctx(_tape())
    full, pre_full = te._rehome_candidates(_board(), ctx, max_candidates=100)
    capped, pre_capped = te._rehome_candidates(_board(), ctx, max_candidates=2)
    assert pre_full == pre_capped == len(full) >= 3
    assert len(capped) == 2
    assert [c.ticker for c in capped] == [c.ticker for c in full[:2]]
    assert all(full[i].target_corr >= full[i + 1].target_corr for i in range(len(full) - 1))


def test_stock_line_carries_the_evidence_note_only_when_present():
    from agents.market_intelligence import universe
    universe.TICKER_DESC["CIFR"] = "bitcoin miner turned AI host"
    plain = te._assignment_stock_line({"ticker": "CIFR", "rs_composite": 8.2, "sector": "Technology"})
    assert plain == "- CIFR (RS 8, sector: Technology — bitcoin miner turned AI host)"
    c = te.RehomeCandidate("CIFR", (PIVOT,), None, "thin_basket", AI, 0.604,
                           "own_unjudgeable:thin_basket", ((AI, 0.604),))
    noted = te._assignment_stock_line({"ticker": "CIFR", "rs_composite": 8.2, "sector": "Technology",
                                       "_rehome_note": te._rehome_stock_note(c)})
    assert noted.startswith(plain[:-1]) and "re-homing candidate" in noted and PIVOT in noted
    assert "too small for the tape to read" in noted and f"'{AI}' at 0.60" in noted
    # the prompt BODY (a scoring input on the EP money path) is untouched
    assert te._assignment_body([{"ticker": "CIFR", "sector": "Technology"}]).startswith(
        "UNCOVERED STOCKS (not in any active theme; each line shows its RS):")


# ═══════════════════════════════ the verb, through the real funnel ════════════════════════════

VALIDATOR_CALLS: list[dict] = []


def _wire(monkeypatch, proposals, *, validate=None, client=None):
    """The REAL `_assign_uncovered_to_themes` with a scripted model, a permissive (or supplied)
    validator that records its kwargs, captured cooldown writes and audit rows."""
    events = _quiet_infra(monkeypatch)
    cooldowns: list[tuple] = []
    VALIDATOR_CALLS.clear()

    async def _cool(ticker, theme_name, reason="", days=14):
        cooldowns.append((ticker, theme_name, reason, days))
        return 1

    monkeypatch.setattr(te, "add_validation_cooldown", _cool)
    monkeypatch.setattr(te, "get_recent_rehome_judged_tickers", AsyncMock(return_value=set()))

    async def _validate_ok(name, tickers, changelog, protected=None, thesis=None, **kw):
        VALIDATOR_CALLS.append({"name": name, "tickers": list(tickers), "thesis": thesis})
        return tickers

    monkeypatch.setattr(te, "_validate_theme_membership", validate or _validate_ok)
    if client is None:
        client, calls = _fake_client(lambda i: _assign_tool_resp(proposals))
    else:
        calls = []
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)
    return events, cooldowns, calls


def _run_pass(monkeypatch, themes, proposals, *, cooldown_set=None, protected=None, validate=None):
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    events, cooldowns, calls = _wire(monkeypatch, proposals, validate=validate)
    changelog: list[dict] = []
    state: dict = {}
    cooldown_set = set() if cooldown_set is None else cooldown_set
    counts = asyncio.run(te._run_rehome_pass(
        themes, sbt, ctx, theme_exclusions=None, globally_banned=set(), cooldown_set=cooldown_set,
        protected=protected, changelog=changelog, rehome_state=state))
    return counts, changelog, events, cooldowns, calls, state, cooldown_set


def test_a_confirmed_fit_moves_cifr_and_a_rejection_leaves_hut_where_it_is(monkeypatch):
    themes = _board()
    counts, changelog, events, cooldowns, calls, state, cdset = _run_pass(
        monkeypatch, themes,
        [{"ticker": "CIFR", "theme": AI, "rationale": "sells AI compute now"}])   # HUT, MISF: no_fit
    by = _by_name(themes)
    # THE MOVE (mutation: delete the strip line in _rehome_through_funnel -> CIFR stays in PIVOT -> red)
    assert "CIFR" in by[AI]["tickers"] and "CIFR" not in by[PIVOT]["tickers"]
    # THE STAY — the judgement rejected HUT and MISF; nothing moved
    assert by[PIVOT]["tickers"] == ["HUT"] and "HUT" not in by[AI]["tickers"]
    assert "MISF" in by[SAAS]["tickers"] and "MISF" not in by[AI]["tickers"]
    # six candidates on this board (CIFR, HUT, MISF + the three Fading-home POWER members): one moved
    assert counts["moved"] == 1 and counts["stayed"] == 5 and counts["candidates_pre_cap"] == 6
    # THE COOLDOWN (mutation: delete the add_validation_cooldown call -> red)
    assert cooldowns == [("CIFR", PIVOT, cooldowns[0][2], te.REHOME_COOLDOWN_DAYS)]
    assert cooldowns[0][2].startswith(te.REHOME_REASON_PREFIX) and AI in cooldowns[0][2]
    assert ("CIFR", PIVOT) in cdset                       # the in-run carry Step 2b reads
    # ONE message line, not an "assigned" line plus a "moved" line
    kinds = [c["type"] for c in changelog]
    assert kinds.count("ticker_rehomed") == 1 and "ticker_assigned" not in kinds
    moved = next(c for c in changelog if c["type"] == "ticker_rehomed")
    assert moved["ticker"] == "CIFR" and moved["from"] == [PIVOT] and moved["theme"] == AI
    assert moved["paying"] is True and moved["stage"] == "Mainstream"          # U1: +10 on its next EP
    assert moved["arm"] == "own_unjudgeable:thin_basket" and moved["corr"] >= te.ASSIGN_COMOVE_BAR
    # AUDIT: one moved row per (name, home), one judged row per candidate, one heartbeat
    ev = [e[0] for e in events]
    assert ev.count(te.REHOME_MOVED_EVENT) == 1 and ev.count(te.REHOME_JUDGED_EVENT) == 6
    moved_row = next(e for e in events if e[0] == te.REHOME_MOVED_EVENT)
    assert moved_row[1].startswith(f"Rehome: '{PIVOT}' -> '{AI}' CIFR") and "+10 on its next EP" in moved_row[1]
    assert json.loads(moved_row[2])["paying"] is True
    judged = [e[1].split()[0] for e in events if e[0] == te.REHOME_JUDGED_EVENT]
    assert sorted(judged) == sorted(["CIFR", "HUT", "MISF"] + POWER_MEMBERS)
    assert next(e[1] for e in events if e[0] == te.REHOME_JUDGED_EVENT and e[1].startswith("CIFR")).startswith("CIFR moved")
    assert next(e[1] for e in events if e[0] == te.REHOME_JUDGED_EVENT and e[1].startswith("HUT")).startswith("HUT stays")
    ran = next(e for e in events if e[0] == "theme_rehome_pass_ran")
    assert json.loads(ran[2])["candidates_pre_cap"] == 6 and json.loads(ran[2])["moved"] == 1
    # ONE model call, offering the non-Fading board only (never a Fading destination)
    assert len(calls) == 1
    prompt = json.dumps(calls[0]["messages"], default=str)
    assert AI in prompt and SAAS in prompt and BTC in prompt
    assert PIVOT not in prompt.split("UNCOVERED STOCKS")[0] and POWER not in prompt.split("UNCOVERED STOCKS")[0]
    assert "re-homing candidate" in prompt
    # post-assignment validation judged the landing against the TARGET'S THESIS (#368's rule, enforced
    # at this fourth caller 2026-10-03) — not the name alone, which would evict a converted miner on
    # "bitcoin miner" the same run
    assert VALIDATOR_CALLS and VALIDATOR_CALLS[0]["name"] == AI
    assert VALIDATOR_CALLS[0]["thesis"] == _by_name(themes)[AI]["description"]
    assert "CIFR" in VALIDATOR_CALLS[0]["tickers"]


def test_a_move_rejected_by_post_assignment_validation_is_a_stay_and_says_so(monkeypatch):
    """F4 runs on the target as for every assignment; a member it removes never moved — and the
    memory row names F4, not the judgement, as the reason (P1/P2 must not read an F4 eviction as a
    judgement result)."""
    async def _validate_strip_cifr(name, tickers, changelog, protected=None, thesis=None, **kw):
        if "CIFR" in tickers:
            changelog.append({"type": "ticker_revalidated_out", "theme": name, "ticker": "CIFR", "reason": "r"})
        return [t for t in tickers if t != "CIFR"]

    themes = _board()
    counts, changelog, events, cooldowns, _calls, _state, _cd = _run_pass(
        monkeypatch, themes, [{"ticker": "CIFR", "theme": AI, "rationale": "x"}], validate=_validate_strip_cifr)
    by = _by_name(themes)
    assert "CIFR" in by[PIVOT]["tickers"] and "CIFR" not in by[AI]["tickers"]
    assert counts["moved"] == 0 and cooldowns == [] and not [c for c in changelog if c["type"] == "ticker_rehomed"]
    row = next(e for e in events if e[0] == te.REHOME_JUDGED_EVENT and e[1].startswith("CIFR"))
    assert "removed by post-assignment validation" in row[1]
    assert json.loads(row[2])["removed_by_validation"] is True and json.loads(row[2])["verdict"] == "stay"
    hut = next(e for e in events if e[0] == te.REHOME_JUDGED_EVENT and e[1].startswith("HUT"))
    assert "the judgement did not place it" in hut[1]


def test_a_failed_model_call_freezes_nobody(monkeypatch):
    """The funnel swallows a transient model failure (proposals already collected are kept; the rest
    stay uncovered). Every re-homing candidate on such a night reads UNJUDGED — no `theme_rehome_judged`
    row, so nobody is frozen as "stays" for 14 days by an outage (mutation: delete the
    `_rh_judged.update` bookkeeping → the move test's six judged rows vanish → red)."""
    from types import SimpleNamespace

    async def _boom(**kwargs):
        raise RuntimeError("model down")

    broken = SimpleNamespace(messages=SimpleNamespace(create=_boom))
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    events, cooldowns, _calls = _wire(monkeypatch, [], client=broken)
    themes = _board()
    changelog: list[dict] = []
    state: dict = {}
    counts = asyncio.run(te._run_rehome_pass(
        themes, sbt, ctx, theme_exclusions=None, globally_banned=set(), cooldown_set=set(),
        protected=None, changelog=changelog, rehome_state=state))
    assert counts["moved"] == 0 and counts["stayed"] == 0 and counts["unjudged"] == 6
    assert te.REHOME_JUDGED_EVENT not in [e[0] for e in events]
    assert "CIFR" in _by_name(themes)[PIVOT]["tickers"] and cooldowns == [] and changelog == []
    assert "theme_rehome_pass_ran" in [e[0] for e in events]


def test_never_into_a_fading_theme_even_when_the_model_names_one(monkeypatch):
    """Direct funnel call with a Fading theme OFFERED (the pass never offers one, but the apply
    loop refuses independently — mutation: delete the Fading refusal -> CIFR lands in POWER -> red)."""
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    events, _cool, _calls = _wire(monkeypatch, [{"ticker": "CIFR", "theme": POWER, "rationale": "x"}])
    themes = _board()
    cand = te.RehomeCandidate("CIFR", (PIVOT,), None, "thin_basket", AI, 0.6, "own_unjudgeable:thin_basket")
    state: dict = {}
    asyncio.run(te._assign_uncovered_to_themes(
        [{**sbt["CIFR"], "_rehome_note": "n"}], themes, sbt, theme_exclusions=None, globally_banned=None,
        cooldown_set=set(), protected=None, comove_ctx=ctx,
        rehome={"CIFR": cand}, per_theme_cap=te.REHOME_PER_TARGET_CAP, rehome_state=state))
    assert "CIFR" not in _by_name(themes)[POWER]["tickers"]
    assert "rehome_skipped_fading_target" in [e[0] for e in events]
    assert state["skipped"]["fading_target"] == 1


def test_an_unreadable_pair_is_refused_not_handed_to_the_sector_label(monkeypatch):
    """A re-homing move has no sector fallback: the model proposes CIFR into the 3-member BTC theme
    whose basket reads fine — but into a 2-member theme the tape cannot read -> refused."""
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    thin = {"name": "Thin Pair", "stage": "Nascent", "score": 50.0, "tickers": ["ALAB", "AIX1"], "description": "d"}
    events, _cool, _calls = _wire(monkeypatch, [{"ticker": "CIFR", "theme": "Thin Pair", "rationale": "x"}])
    themes = _board() + [thin]
    cand = te.RehomeCandidate("CIFR", (PIVOT,), None, "thin_basket", AI, 0.6, "own_unjudgeable:thin_basket")
    state: dict = {}
    asyncio.run(te._assign_uncovered_to_themes(
        [{**sbt["CIFR"], "_rehome_note": "n"}], themes, sbt, theme_exclusions=None, globally_banned=None,
        cooldown_set=set(), protected=None, comove_ctx=ctx,
        rehome={"CIFR": cand}, per_theme_cap=te.REHOME_PER_TARGET_CAP, rehome_state=state))
    assert "CIFR" not in thin["tickers"]
    kinds = [e[0] for e in events]
    assert "rehome_skipped_unjudgeable" in kinds and "assignment_skipped_sector_outlier" not in kinds
    assert "assignment_sector_kw_overridden_by_desc" not in kinds


def test_the_cooldown_blocks_a_move_back_within_14_days(monkeypatch):
    """Night 1 moves CIFR out of a non-Fading factor-A home ('Neocloud Builders', 4 members, so the tape
    WOULD admit a return) into the AI theme and writes the (CIFR, home) cooldown. Night 2 the model
    proposes CIFR back into that home: the tape says yes, the hard cooldown filter refuses it.
    (Mutation: delete the `cooldown_set.add` in _rehome_through_funnel -> the return lands -> red.)"""
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    home = {"name": "Neocloud Builders", "stage": "Nascent", "score": 50.0,
            "tickers": ["IREN", "WULF", "CORZ", "CIFR"], "description": "d"}
    themes = [t for t in _board() if t["name"] != PIVOT] + [home]
    events, cooldowns, _calls = _wire(monkeypatch, [{"ticker": "CIFR", "theme": AI, "rationale": "x"}])
    cand = te.RehomeCandidate("CIFR", (home["name"],), 0.1, "below_bar", AI, 0.6, "g2_misfiled")
    cdset: set = set()
    changelog: list[dict] = []
    asyncio.run(te._rehome_through_funnel(
        [cand], [t for t in themes if t["stage"] != "Fading"], themes, sbt,
        theme_exclusions=None, globally_banned=None, cooldown_set=cdset, protected=None,
        comove_ctx=ctx, changelog=changelog, rehome_state={}))
    by = _by_name(themes)
    assert "CIFR" in by[AI]["tickers"] and "CIFR" not in home["tickers"]
    assert ("CIFR", home["name"]) in cdset and cooldowns[0][:2] == ("CIFR", home["name"])
    # night 2: the model wants CIFR back home; the tape admits (factor A, 3 others) — the cooldown blocks
    assert te._comove_verdict("CIFR", home["tickers"], ctx).admit is True
    events2, _cool2, _calls2 = _wire(monkeypatch, [{"ticker": "CIFR", "theme": home["name"], "rationale": "x"}])
    back = te.RehomeCandidate("CIFR", (AI,), 0.1, "below_bar", home["name"], 0.6, "g2_misfiled")
    asyncio.run(te._assign_uncovered_to_themes(
        [{**sbt["CIFR"], "_rehome_note": "n"}], themes, sbt, theme_exclusions=None, globally_banned=None,
        cooldown_set=cdset, protected=None, comove_ctx=ctx,
        rehome={"CIFR": back}, per_theme_cap=te.REHOME_PER_TARGET_CAP, rehome_state={}))
    assert "CIFR" not in home["tickers"] and "CIFR" in by[AI]["tickers"]
    assert "cooldown_blocked_assignment" in [e[0] for e in events2]


def test_at_most_three_admissions_into_one_theme_per_night(monkeypatch):
    """Four candidates all proposed into the AI theme: three land, the fourth is deferred with its own
    audit row (mutation: delete the cap check -> four land -> red)."""
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    props = [{"ticker": tk, "theme": AI, "rationale": "x"} for tk in ["CIFR", "HUT", "MISF", "PWR1"]]
    events, cooldowns, _calls = _wire(monkeypatch, props)
    themes = _board()
    cands = [te.RehomeCandidate(tk, (home,), None, "thin_basket", AI, 0.6, "own_unjudgeable:thin_basket")
             for tk, home in [("CIFR", PIVOT), ("HUT", PIVOT), ("MISF", SAAS), ("PWR1", POWER)]]
    state: dict = {}
    changelog: list[dict] = []
    counts = asyncio.run(te._rehome_through_funnel(
        cands, [t for t in themes if t["stage"] != "Fading"], themes, sbt,
        theme_exclusions=None, globally_banned=None, cooldown_set=set(), protected=None,
        comove_ctx=ctx, changelog=changelog, rehome_state=state))
    landed = [tk for tk in ["CIFR", "HUT", "MISF", "PWR1"] if tk in _by_name(themes)[AI]["tickers"]]
    assert len(landed) == te.REHOME_PER_TARGET_CAP == 3
    assert state["per_theme"][AI] == 3 and state["skipped"]["cap"] == 1
    assert [e[0] for e in events].count("rehome_skipped_cap") == 1
    assert counts["moved"] == 3 and counts["stayed"] == 0 and counts["unjudged"] == 1 and len(cooldowns) == 3
    # the deferred one is still where it was and gets NO memory row — it waits a night, not 14 days
    deferred = [tk for tk in ["CIFR", "HUT", "MISF", "PWR1"] if tk not in landed]
    assert len(deferred) == 1 and deferred[0] in state["blocked"]
    judged = [e[1].split()[0] for e in events if e[0] == te.REHOME_JUDGED_EVENT]
    assert sorted(judged) == sorted(landed) and deferred[0] not in judged


def test_an_operator_protected_home_is_never_stripped_even_if_the_model_moves_it(monkeypatch):
    """Selection skips protected pairs; the verb re-checks because add_validation_cooldown resets
    `bypassed` on conflict — a /bypass ruling must never be revoked by a move."""
    themes = _board()
    counts, changelog, events, cooldowns, _calls, _state, _cd = _run_pass(
        monkeypatch, themes, [{"ticker": "CIFR", "theme": AI, "rationale": "x"},
                              {"ticker": "HUT", "theme": AI, "rationale": "x"}],
        protected={("CIFR", PIVOT)})
    by = _by_name(themes)
    assert "CIFR" in by[PIVOT]["tickers"] and "CIFR" not in by[AI]["tickers"]   # never offered
    assert "HUT" in by[AI]["tickers"] and "HUT" not in by[PIVOT]["tickers"]     # the unprotected one moves
    assert [c[0] for c in cooldowns] == ["HUT"]


# ═══════════════════════════════ feeder (iii): join carry ═════════════════════════════════════

def test_join_carry_candidates_are_the_tape_filtered_novel_members_of_a_non_fading_target():
    ctx = _ctx(_tape())
    cands = te._join_carry_candidates(
        {AI: ["IREN", "WULF", "NOIS"], POWER: ["CORZ"], "Gone": ["ALAB"]}, _board(), ctx)
    assert sorted(c.ticker for c in cands) == ["IREN", "WULF"]         # NOIS below the bar; POWER is Fading; Gone is not live
    assert all(c.homes == () and c.arm == "join_carry" and c.target == AI for c in cands)
    assert te._join_carry_candidates({AI: ["IREN"]}, _board(), ctx, skip_tickers={"IREN"}) == []


def test_join_carry_joins_through_the_funnel_without_a_home_to_leave(monkeypatch):
    ctx = _ctx(_tape())
    sbt = _sbt(monkeypatch)
    events, cooldowns, calls = _wire(monkeypatch, [{"ticker": "IREN", "theme": AI, "rationale": "AI host"}])
    themes = _board()
    changelog: list[dict] = []
    totals = asyncio.run(te._run_join_carry(
        {AI: ["IREN", "WULF"]}, themes, sbt, ctx, theme_exclusions=None, globally_banned=set(),
        cooldown_set=set(), protected=None, changelog=changelog, rehome_state={}))
    by = _by_name(themes)
    assert "IREN" in by[AI]["tickers"] and "WULF" not in by[AI]["tickers"]
    assert totals["joined"] == 1 and totals["stayed"] == 1 and cooldowns == []    # a join writes no cooldown
    row = next(e for e in events if e[0] == te.REHOME_MOVED_EVENT)
    assert row[1].startswith(f"Rehome: IREN joined '{AI}'") and "->" not in row[1]
    joined = next(c for c in changelog if c["type"] == "ticker_rehomed")
    assert joined["from"] == [] and joined["theme"] == AI and joined["arm"] == "join_carry"
    assert "theme_rehome_join_carry_ran" in [e[0] for e in events]
    # the funnel saw ONLY the join target
    prompt = json.dumps(calls[0]["messages"], default=str)
    assert AI in prompt and SAAS not in prompt.split("UNCOVERED STOCKS")[0]


# ═══════════════════════════════ wiring: toggle + engine order ════════════════════════════════

@pytest.mark.asyncio
async def test_toggle_off_skips_the_pass_and_on_runs_it_after_the_strip(monkeypatch):
    from tests.test_theme_birth_gate import _drive_engine, _MON
    ctx = _ctx(_tape())
    order: list[str] = []

    for toggle in (False, True):
        _drive_engine(monkeypatch, mode="off", discovered=[])
        monkeypatch.setattr(te, "_read_assign_comove_toggle", AsyncMock(return_value=True))
        monkeypatch.setattr(te, "_load_comove_context", AsyncMock(return_value=ctx))
        monkeypatch.setattr(te, "_read_rehome_toggle", AsyncMock(return_value=toggle))

        async def _strip(*a, **k):
            order.append("strip")
            return 0

        async def _pass(*a, **k):
            order.append("rehome")
            return {}

        monkeypatch.setattr(te, "_apply_carryforward_deterministic_filter", _strip)
        monkeypatch.setattr(te, "_run_rehome_pass", _pass)
        order.clear()
        await te.run_theme_engine(trade_date=_MON)
        assert order == (["strip", "rehome"] if toggle else ["strip"]), toggle


@pytest.mark.asyncio
async def test_no_tape_context_means_no_pass_and_no_toggle_read(monkeypatch):
    from tests.test_theme_birth_gate import _drive_engine, _MON
    _drive_engine(monkeypatch, mode="off", discovered=[])
    monkeypatch.setattr(te, "_read_assign_comove_toggle", AsyncMock(return_value=False))
    read = AsyncMock(return_value=True)
    monkeypatch.setattr(te, "_read_rehome_toggle", read)
    ran = AsyncMock(return_value={})
    monkeypatch.setattr(te, "_run_rehome_pass", ran)
    await te.run_theme_engine(trade_date=_MON)
    assert read.await_count == 0 and ran.await_count == 0


def test_the_toggle_is_discoverable_by_the_drift_check_and_defaults_on():
    from scripts.live_rules import discover_runtime_toggles
    fact = discover_runtime_toggles()[te.REHOME_TOGGLE[0]]
    assert fact.env_var == te.REHOME_TOGGLE[1] and fact.default is True
    assert fact.where.startswith("agents/market_intelligence/theme_engine.py:")


# ═══════════════════════════════ db + lineage ═════════════════════════════════════════════════

class _FakeConn:
    def __init__(self, sink, rows=()):
        self._sink, self._rows = sink, list(rows)

    async def fetch(self, sql, *params):
        self._sink.append((sql, params))
        return self._rows


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, sink, rows=()):
        self._conn = _FakeConn(sink, rows)

    def acquire(self):
        return _FakeAcquire(self._conn)


def test_global_ban_query_ignores_rehome_cooldowns(monkeypatch):
    sink: list = []

    async def _pool():
        return _FakePool(sink)

    monkeypatch.setattr(dbmod, "get_pool", _pool)
    asyncio.run(dbmod.get_globally_banned_tickers(min_distinct_themes=3, lookback_days=30))
    (sql, params), = sink
    assert "removal_reason NOT LIKE 'rehome:%'" in sql and "removal_reason IS NULL" in sql
    assert "NOT bypassed" in sql and params == ("30", 3)
    assert te.REHOME_REASON_PREFIX == "rehome:"


def test_recent_rehome_judged_tickers_reads_the_pass_own_rows(monkeypatch):
    sink: list = []
    rows = [{"summary": "CIFR moved -> 'AI' (tape 0.60, own_unjudgeable:thin_basket)"},
            {"summary": "hut stays — the judgement did not place it"}, {"summary": ""}]

    async def _pool():
        return _FakePool(sink, rows)

    monkeypatch.setattr(dbmod, "get_pool", _pool)
    out = asyncio.run(dbmod.get_recent_rehome_judged_tickers(14))
    assert out == {"CIFR", "HUT"}
    (sql, params), = sink
    assert params == (dbmod.REHOME_JUDGED_EVENT, "14") and "mi_audit_log" in sql


@pytest.mark.asyncio
async def test_step_3a5_hands_the_join_suppressed_newborns_novel_uncovered_members_to_the_carry(monkeypatch):
    """Through the real `run_theme_engine` in `dedup_only`: a newborn whose members overlap the live
    theme 100% (intersection-over-smaller) with exactly half of them already covered — so the gate's
    refinement carve-out does NOT skip the join check — is suppressed as `join`; its NOVEL uncovered
    members (L00, L01) reach `_run_join_carry` keyed on the join target; the covered ones (EX1, EX2 —
    already the target's) do not."""
    from tests.test_theme_birth_gate import _drive_engine, _MON, _EX_THEME
    ctx = _ctx(_tape())
    _drive_engine(monkeypatch, mode="dedup_only",
                  discovered=[{"name": "Newborn Hosts", "tickers": ["EX1", "EX2", "L00", "L01"], "thesis": "t"}])
    monkeypatch.setattr(te, "_read_assign_comove_toggle", AsyncMock(return_value=True))
    monkeypatch.setattr(te, "_load_comove_context", AsyncMock(return_value=ctx))
    monkeypatch.setattr(te, "_read_rehome_toggle", AsyncMock(return_value=True))
    monkeypatch.setattr(te, "_run_rehome_pass", AsyncMock(return_value={}))
    carry = AsyncMock(return_value={})
    monkeypatch.setattr(te, "_run_join_carry", carry)
    themes, changelog = await te.run_theme_engine(trade_date=_MON)
    assert [c for c in changelog if c["type"] == "theme_birth_gated"][0]["outcome"] == "join"
    assert carry.await_count == 1
    assert carry.await_args.args[0] == {_EX_THEME["name"]: ["L00", "L01"]}
    assert "Newborn Hosts" not in {t["name"] for t in themes}


def test_successor_pointer_reads_a_rehome_move_but_not_a_join():
    rows = [
        {"event_type": te.REHOME_MOVED_EVENT, "summary": f"Rehome: '{PIVOT}' -> '{AI}' CIFR moved on the tape (0.60 vs own unreadable)", "detail": ""},
        {"event_type": te.REHOME_MOVED_EVENT, "summary": f"Rehome: IREN joined '{AI}' from a suppressed newborn (tape 0.68)", "detail": ""},
    ]
    succ, cap = te._successor_pointers_from_audit_rows(rows)
    assert succ == {PIVOT: AI} and cap == {}
