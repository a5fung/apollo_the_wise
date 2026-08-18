"""Output-bounding batching for the three theme-engine LLM callers (2026-08-10).

THE BUG CLASS: theme_assignment / theme_discovery output scales LINEARLY with the
candidate population (the scratchpad contract narrates every rendered stock), so no
output ceiling can hold — the ceilings were raised 4000→8000 on 2026-08-07 for
exactly this truncation and pegged again within days (22/22 assignment calls in the
21 days to 08-10 censored at-cap; #534 D2 widened the pool to ~373 stocks).
theme_split measured DIFFERENTLY: its input is one bounded theme (~2.1K input
tokens) — what blew its 1750 cap was freeform scratchpad verbosity on a more
verbose model, and the truncated response parsed as propose_split-with-split-
missing → logged "Sonnet found theme already coherent" (an affirmative lie,
twice on 2026-08-10).

THE FIX: chunk the INPUT so a single call's output cannot reach its ceiling —
stocks are batched, the FULL theme list rides in every call (input-side context
costs no output). Split gets the proven terse-scratchpad + tool_choice=any recipe
plus truncation honesty. Batch sizes are DERIVED from measured per-item output
cost (derivations at _ASSIGN_LLM_BATCH_SIZE / _DISCOVERY_LLM_BATCH_STOCKS in
theme_engine.py); the derivation-gate tests here fail if either constant is ever
bumped past what the measurements support.

Truncation is no longer silent: a stop_reason='max_tokens' response is treated as
a FAILED call (never "proposed 0" / "0 themes" / "declined split"); the alarm
itself is #543's existing spend-tracker live truncation alarm — no second
mechanism. (Heavy-import stubbing via tests/conftest.py.)
"""
import asyncio
import re
from types import SimpleNamespace

import pytest

from agents.market_intelligence import theme_engine as te


# ── scaffolding ───────────────────────────────────────────────────────────────

class _Block:
    def __init__(self, type, name=None, input=None, id="b1", text=""):
        self.type = type
        self.name = name
        self.input = input or {}
        self.id = id
        self.text = text


def _resp(*blocks, stop_reason="tool_use", out_tok=500):
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        usage=SimpleNamespace(output_tokens=out_tok),
    )


def _fake_client(responses):
    """Scripted client; if `responses` is callable it maps call-index → response."""
    calls = []

    async def _create(**kwargs):
        calls.append(kwargs)
        i = len(calls) - 1
        return responses(i) if callable(responses) else responses[i]

    return SimpleNamespace(messages=SimpleNamespace(create=_create)), calls


def _quiet_infra(monkeypatch):
    """Silence audit/spend/advisor infra; return the audit-event capture list."""
    events = []

    async def _audit(event_type, summary="", detail="", **kw):
        events.append((event_type, summary, detail))

    async def _spend(**kw):
        return None

    async def _advice(question, context, caller=""):
        return "advisor verdict"

    monkeypatch.setattr(te, "log_audit_event", _audit)
    import agents.market_intelligence.spend_tracker as spend_mod
    monkeypatch.setattr(spend_mod, "log_anthropic_call_safe", _spend)
    monkeypatch.setattr(te, "_call_advisor", _advice)
    return events


def _mk_stocks(n, monkeypatch, sector="Technology", prefix="T"):
    from agents.market_intelligence import universe
    stocks = []
    for i in range(n):
        tk = f"{prefix}{i:03d}"
        monkeypatch.setitem(universe.TICKER_DESC, tk, f"maker of widget {i}")
        stocks.append({"ticker": tk, "rs_composite": 90, "sector": sector})
    return stocks


def _mk_themes(monkeypatch):
    """Two live themes whose members carry sectors (so the apply-loop sector
    gate accepts same-sector assignments)."""
    themes = [
        {"name": "Widget Platforms", "stage": "Nascent",
         "tickers": ["AAA", "BBB"], "description": "widget platform makers"},
        {"name": "Gadget Makers", "stage": "Nascent",
         "tickers": ["CCC", "DDD"], "description": "gadget manufacturing"},
    ]
    sbt = {tk: {"ticker": tk, "sector": "Technology"}
           for tk in ["AAA", "BBB", "CCC", "DDD"]}

    async def _validate_ok(name, tickers, changelog, protected=None):
        return tickers

    monkeypatch.setattr(te, "_validate_theme_membership", _validate_ok)
    return themes, sbt


def _assign_call_text(call) -> str:
    content = call["messages"][0]["content"]
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content)


def _rendered_tickers(text) -> list[str]:
    return re.findall(r"- (\w+) \(RS", text)


def _assign_tool_resp(assignments, stop_reason="tool_use"):
    return _resp(
        _Block("tool_use", name="assign_stocks_to_themes",
               input={"analysis_scratchpad": "terse", "assignments": assignments}),
        stop_reason=stop_reason,
    )


def _run_assign(stocks, themes, sbt):
    # The engine's stocks_by_ticker covers the pool stocks too (sector data for
    # the apply-loop gates) — mirror that.
    full_sbt = {**sbt, **{s["ticker"]: s for s in stocks}}
    return asyncio.run(te._assign_uncovered_to_themes(
        stocks, themes, full_sbt, theme_exclusions=None, globally_banned=None,
        cooldown_set=set(), protected=None))


# ── assignment: batching splits correctly, every call bounded ────────────────

def test_assignment_pool_is_batched_and_every_call_bounded(monkeypatch):
    """40 stocks → ceil(40/18)=3 calls; no call renders more than the derived
    batch size; the FULL theme list appears in every call (a stock's best home
    can never be 'in another batch'); the shared prefix carries the prompt-cache
    breakpoint."""
    _quiet_infra(monkeypatch)
    themes, sbt = _mk_themes(monkeypatch)
    stocks = _mk_stocks(40, monkeypatch)
    client, calls = _fake_client(lambda i: _assign_tool_resp([]))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    remaining, changelog = _run_assign(stocks, themes, sbt)

    assert len(calls) == 3, "40 stocks at batch size 18 must produce exactly 3 calls"
    seen = []
    for c in calls:
        text = _assign_call_text(c)
        batch = _rendered_tickers(text)
        assert 0 < len(batch) <= te._ASSIGN_LLM_BATCH_SIZE, \
            f"a single call rendered {len(batch)} stocks — the output bound is broken"
        assert "Widget Platforms" in text and "Gadget Makers" in text, \
            "every batch must see the FULL theme list"
        # cost: the shared theme-list prefix must be cache-marked
        first_block = c["messages"][0]["content"][0]
        assert first_block.get("cache_control") == {"type": "ephemeral"}, \
            "shared prefix lost its prompt-cache breakpoint — every batch re-bills the theme list"
        seen.extend(batch)
    assert sorted(seen) == sorted(s["ticker"] for s in stocks), \
        "batches must partition the pool exactly — nothing lost, nothing duplicated"
    assert len(remaining) == 40 and changelog == []


def test_oversized_pool_never_issues_an_unbatched_call(monkeypatch):
    """The 2026-08-10 failure population: 373 stocks. Pre-fix this was ONE call
    whose output demand (~373 × ≥73 tok) could never fit any ceiling; now no
    single call may exceed the derived batch size."""
    _quiet_infra(monkeypatch)
    themes, sbt = _mk_themes(monkeypatch)
    stocks = _mk_stocks(373, monkeypatch)
    client, calls = _fake_client(lambda i: _assign_tool_resp([]))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    _run_assign(stocks, themes, sbt)

    assert len(calls) == 21  # ceil(373/18)
    assert max(len(_rendered_tickers(_assign_call_text(c))) for c in calls) \
        <= te._ASSIGN_LLM_BATCH_SIZE


def test_assign_batch_size_satisfies_measured_demand_bound():
    """Derivation gate: worst-case predicted output for one batch must stay
    under the registry's pre-failure threshold. Constants are the MEASURED ones
    (fit 274 + 73.4/stock + max residual 416 on the 16 untruncated sonnet-4-6
    calls; 3.5x = largest measured completed-sample freeform model growth).
    Fails if _ASSIGN_LLM_BATCH_SIZE is bumped without re-deriving."""
    from shared.output_ceilings import max_tokens_for, NEAR_CEILING_FRACTION
    predicted = 3.5 * (274 + 416 + 73.4 * te._ASSIGN_LLM_BATCH_SIZE)
    assert predicted <= NEAR_CEILING_FRACTION * max_tokens_for("theme_assignment"), \
        "batch size exceeds what the measured per-stock output cost supports"


def test_assignment_aggregation_applies_proposals_from_every_batch(monkeypatch):
    """Proposals from ALL batches are applied (nothing lost): batch 1 and
    batch 2 each propose one of their own stocks."""
    _quiet_infra(monkeypatch)
    themes, sbt = _mk_themes(monkeypatch)
    stocks = _mk_stocks(20, monkeypatch)  # 2 batches: 18 + 2

    def _script(i):
        if i == 0:  # batch 1 holds T000..T017
            return _assign_tool_resp([{"ticker": "T000", "theme": "Widget Platforms",
                                       "rationale": "fits"}])
        return _assign_tool_resp([{"ticker": "T019", "theme": "Gadget Makers",
                                   "rationale": "fits"}])

    client, calls = _fake_client(_script)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    remaining, changelog = _run_assign(stocks, themes, sbt)

    assigned = {(c["ticker"], c["theme"]) for c in changelog
                if c.get("type") == "ticker_assigned"}
    assert assigned == {("T000", "Widget Platforms"), ("T019", "Gadget Makers")}, \
        "an assignment proposed by a later batch was lost in aggregation"
    assert "T000" in themes[0]["tickers"] and "T019" in themes[1]["tickers"]
    rem = {s["ticker"] for s in remaining}
    assert "T000" not in rem and "T019" not in rem and len(rem) == 18


def test_cross_batch_echo_cannot_duplicate_an_assignment(monkeypatch):
    """Batch 1 echoes a ticker it was NOT shown (it lives in batch 2). The
    partition guarantee drops the echo; only batch 2's own proposal lands —
    exactly one changelog entry, ticker in exactly one theme."""
    _quiet_infra(monkeypatch)
    themes, sbt = _mk_themes(monkeypatch)
    stocks = _mk_stocks(20, monkeypatch)

    def _script(i):
        if i == 0:  # batch 1 proposes batch 2's T019 — a cross-batch echo
            return _assign_tool_resp([{"ticker": "T019", "theme": "Widget Platforms",
                                       "rationale": "echo"}])
        return _assign_tool_resp([{"ticker": "T019", "theme": "Gadget Makers",
                                   "rationale": "real"}])

    client, calls = _fake_client(_script)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    _, changelog = _run_assign(stocks, themes, sbt)

    entries = [c for c in changelog if c.get("type") == "ticker_assigned"
               and c["ticker"] == "T019"]
    assert len(entries) == 1 and entries[0]["theme"] == "Gadget Makers", \
        "a cross-batch echo duplicated (or stole) an assignment"
    assert "T019" not in themes[0]["tickers"] and "T019" in themes[1]["tickers"]


def test_truncated_assignment_batch_is_a_failure_not_proposed_zero(monkeypatch):
    """The silent-outage killer: a stop_reason='max_tokens' batch must NOT write
    an assignment_llm_proposed row (that is how ten dead nights read as quiet
    ones). Later batches still run; the truncated batch's stocks stay uncovered."""
    events = _quiet_infra(monkeypatch)
    themes, sbt = _mk_themes(monkeypatch)
    stocks = _mk_stocks(20, monkeypatch)

    def _script(i):
        if i == 0:  # truncated mid-scratchpad: assignments key parsed away
            return _resp(_Block("tool_use", name="assign_stocks_to_themes",
                                input={"analysis_scratchpad": "cut off mid-"}),
                         stop_reason="max_tokens", out_tok=8000)
        return _assign_tool_resp([{"ticker": "T019", "theme": "Gadget Makers",
                                   "rationale": "fits"}])

    client, calls = _fake_client(_script)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    remaining, changelog = _run_assign(stocks, themes, sbt)

    proposed = [e for e in events if e[0] == "assignment_llm_proposed"]
    assert len(proposed) == 1 and "batch 2/2" in proposed[0][1], \
        "a TRUNCATED batch was reported as a genuine proposal round"
    assert not any(e[0] == "assignment_silent_stop" for e in events)
    assert len(calls) == 2, "a truncated batch must not abort the remaining batches"
    assert {c["ticker"] for c in changelog if c.get("type") == "ticker_assigned"} == {"T019"}
    assert "T000" in {s["ticker"] for s in remaining}, \
        "truncated batch's stocks must stay uncovered (retry next run), not vanish"


def test_advisor_budget_is_run_level_across_batches(monkeypatch):
    """_MAX_ADVISOR_CALLS was always a per-RUN cost bound; batching must not
    multiply it by the batch count. Batch 1 burns all 3; batch 2's advisor
    request gets 'limit reached' without another Opus call."""
    _quiet_infra(monkeypatch)
    n_advisor = {"n": 0}

    async def _advice(question, context, caller=""):
        n_advisor["n"] += 1
        return "verdict"

    monkeypatch.setattr(te, "_call_advisor", _advice)
    themes, sbt = _mk_themes(monkeypatch)
    stocks = _mk_stocks(20, monkeypatch)
    ask = _resp(_Block("tool_use", name="consult_advisor",
                       input={"question": "?", "context": "ctx"}))

    def _script(i):
        # batch 1: three advisor rounds then an empty assign; batch 2: one more
        # advisor ask (must be denied), then empty assign.
        return {0: ask, 1: ask, 2: ask, 3: _assign_tool_resp([]),
                4: ask, 5: _assign_tool_resp([])}[i]

    client, calls = _fake_client(_script)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    _run_assign(stocks, themes, sbt)

    assert n_advisor["n"] == te._MAX_ADVISOR_CALLS, \
        f"advisor ran {n_advisor['n']}x — the run-level budget leaked to per-batch"


# ── discovery: batching + aggregation + truncation honesty ───────────────────

def _disc_report(themes, stop_reason="tool_use"):
    return _resp(_Block("tool_use", name="report_themes",
                        input={"analysis_scratchpad": "terse", "themes": themes}),
                 stop_reason=stop_reason)


def test_discovery_small_pool_stays_one_call(monkeypatch):
    _quiet_infra(monkeypatch)
    stocks = _mk_stocks(5, monkeypatch)
    sbt = {s["ticker"]: s for s in stocks}
    client, calls = _fake_client([_disc_report([])])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert len(calls) == 1 and out == []


def test_discovery_large_pool_batches_and_bounds_each_call(monkeypatch):
    """80 uncovered stocks → 4 calls (cap 22); each call's rendered population
    is bounded; the existing-themes context block rides in every call."""
    _quiet_infra(monkeypatch)
    stocks = _mk_stocks(80, monkeypatch)
    sbt = {s["ticker"]: s for s in stocks}
    existing = [{"name": "Widget Platforms", "stage": "Nascent", "score": 50,
                 "tickers": ["AAA"]}]
    client, calls = _fake_client(lambda i: _disc_report([]))
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    asyncio.run(te._discover_new_themes(stocks, existing, sbt))

    assert len(calls) == 4, "80 stocks at cap 22 must produce 4 calls"
    seen = []
    for c in calls:
        prompt = c["messages"][0]["content"]
        batch = _rendered_tickers(prompt)
        assert 0 < len(batch) <= te._DISCOVERY_LLM_BATCH_STOCKS
        assert "Widget Platforms" in prompt, "every batch must see the existing-themes context"
        seen.extend(batch)
    assert sorted(seen) == sorted(s["ticker"] for s in stocks), \
        "discovery batches must partition the pool exactly"


def test_discovery_batch_size_satisfies_measured_demand_bound():
    """Derivation gate: cap × the designed per-stock output cost must stay under
    the registry's pre-failure threshold. 2026-08-18 re-derivation: the 08-18
    censored floor (8000 tokens / the OLD cap of 37) × the same 1.5 measured
    tail ratio used on 08-10 ≈ 324 design tok/stock. Fails if
    _DISCOVERY_LLM_BATCH_STOCKS is bumped without re-deriving from fresh data."""
    from shared.output_ceilings import max_tokens_for, NEAR_CEILING_FRACTION
    design_tok_per_stock = (8000 / 37) * 1.5
    assert design_tok_per_stock * te._DISCOVERY_LLM_BATCH_STOCKS \
        <= NEAR_CEILING_FRACTION * max_tokens_for("theme_discovery"), \
        "discovery batch cap exceeds what the measured per-stock cost supports"


def test_discovery_aggregates_across_batches_and_merges_same_name(monkeypatch):
    """Aggregation invariant: distinct themes from different batches all
    survive; the SAME theme surfacing from two batches merges its members
    instead of losing one half."""
    _quiet_infra(monkeypatch)
    stocks = _mk_stocks(80, monkeypatch)
    sbt = {s["ticker"]: s for s in stocks}

    def _script(i):
        if i == 0:
            return _disc_report([{"name": "Widget AI", "thesis": "t",
                                  "tickers": ["T000", "T001"]}])
        if i == 1:
            return _disc_report([{"name": "Widget AI", "thesis": "t2",
                                  "tickers": ["T040", "T041"]},
                                 {"name": "Gadget Robotics", "thesis": "t3",
                                  "tickers": ["T050", "T051"]}])
        return _disc_report([])

    client, calls = _fake_client(_script)
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    by_name = {t["name"]: t for t in out}
    assert set(by_name) == {"Widget AI", "Gadget Robotics"}, \
        "a theme discovered by one batch was lost in aggregation"
    assert sorted(by_name["Widget AI"]["tickers"]) == ["T000", "T001", "T040", "T041"], \
        "same-named themes from two batches must UNION members, not drop a half"


def test_partition_is_exact_and_keeps_clusters_together():
    """Pure partition invariants: (1) every pool entry lands in exactly one
    batch; (2) a correlation cluster's members stay in ONE batch and the
    cluster block travels with them — even when the sector sort would have
    separated them."""
    unc = [{"ticker": f"U{i:02d}", "rs_composite": 90,
            "sector": "SectorA" if i < 10 else "SectorB"} for i in range(20)]
    vel = [{"ticker": f"V{i:02d}", "rs_composite": 80, "sector": "SectorC"}
           for i in range(10)]
    # cluster bridges SectorA and SectorC — the sort alone would split it
    cluster = {"tickers": ["U00", "V00"], "member_count": 2,
               "mean_corr": 0.9, "avg_rs": 88}
    batches = te._partition_discovery_pools(
        {"uncovered": unc, "velocity": vel, "turner": [], "elite": []},
        [cluster], batch_cap=12)

    all_out = [s["ticker"] for b in batches for k in
               ("uncovered", "velocity", "turner", "elite") for s in b[k]]
    assert sorted(all_out) == sorted([s["ticker"] for s in unc + vel]), \
        "partition lost or duplicated a pool entry"
    homes = [i for i, b in enumerate(batches)
             if any(s["ticker"] in {"U00", "V00"}
                    for k in ("uncovered", "velocity") for s in b[k])]
    assert len(set(homes)) == 1, "correlation-cluster members were split across batches"
    cluster_home = [i for i, b in enumerate(batches) if cluster in b["clusters"]]
    assert cluster_home == [homes[0]], \
        "the cluster block must travel with its members' batch"
    assert all(sum(len(b[k]) for k in ("uncovered", "velocity", "turner", "elite"))
               <= 12 for b in batches)


# ── partition: bound / coverage / order at the LIVE production cap ───────────
# (2026-08-18 tighten, _DISCOVERY_LLM_BATCH_STOCKS 37 -> 22. These run against
# the real constant so a future bump is exercised here too, not just at the
# derivation-gate test.)

def test_partition_never_exceeds_the_discovery_batch_cap():
    """No single batch may exceed the cap regardless of pool mix — uncovered +
    velocity + turner + elite all contribute to one call's rendered population."""
    unc = [{"ticker": f"U{i:03d}", "rs_composite": 90, "sector": "SectorA"} for i in range(60)]
    vel = [{"ticker": f"V{i:03d}", "rs_composite": 80, "sector": "SectorB"} for i in range(20)]
    turner = [{"ticker": f"N{i:03d}", "rs_composite": 70, "sector": "SectorC"} for i in range(15)]
    elite = [{"ticker": f"E{i:03d}", "rs_composite": 95, "sector": "SectorD"} for i in range(10)]

    batches = te._partition_discovery_pools(
        {"uncovered": unc, "velocity": vel, "turner": turner, "elite": elite},
        [], batch_cap=te._DISCOVERY_LLM_BATCH_STOCKS)

    assert len(batches) > 1, "test pool must actually require multiple batches"
    for b in batches:
        total = sum(len(b[k]) for k in ("uncovered", "velocity", "turner", "elite"))
        assert total <= te._DISCOVERY_LLM_BATCH_STOCKS, \
            f"a batch rendered {total} stocks — exceeds the derived cap"


def test_partition_covers_every_candidate_none_dropped():
    """A candidate list bigger than one batch must be FULLY covered — every
    stock lands in exactly one batch, nothing silently dropped or duplicated."""
    unc = [{"ticker": f"U{i:03d}", "rs_composite": 90, "sector": "SectorA"} for i in range(90)]

    batches = te._partition_discovery_pools(
        {"uncovered": unc, "velocity": [], "turner": [], "elite": []},
        [], batch_cap=te._DISCOVERY_LLM_BATCH_STOCKS)

    assert len(batches) > 1, "test pool must actually require multiple batches"
    out_tickers = [s["ticker"] for b in batches for s in b["uncovered"]]
    assert len(out_tickers) == len(unc), "candidate count changed across the partition"
    assert sorted(out_tickers) == sorted(s["ticker"] for s in unc), \
        "partition dropped or duplicated a candidate stock"


def test_partition_preserves_original_order_within_each_batch():
    """Batch BOUNDARIES are chosen by sector (so thematic cohorts stay
    together), but each batch's own list must come back out in original pool
    (RS-ranked) order, never sector-scrambled — interleave two sectors so a
    skipped restoration step would show up as a reordering."""
    unc = [{"ticker": f"U{i:03d}", "rs_composite": 90,
            "sector": "SectorA" if i % 2 == 0 else "SectorB"} for i in range(50)]

    batches = te._partition_discovery_pools(
        {"uncovered": unc, "velocity": [], "turner": [], "elite": []},
        [], batch_cap=te._DISCOVERY_LLM_BATCH_STOCKS)

    assert len(batches) > 1, "test pool must actually require multiple batches"
    for b in batches:
        batch_tickers = [s["ticker"] for s in b["uncovered"]]
        member_set = set(batch_tickers)
        expected_order = [s["ticker"] for s in unc if s["ticker"] in member_set]
        assert batch_tickers == expected_order, \
            "a batch's stock order drifted from original (RS-ranked) pool order"


def test_discovery_truncated_report_is_never_accepted(monkeypatch):
    """The 2026-08-10 21:13Z case: a truncated response can carry a PARSED
    report_themes block (partial input). It must be discarded and the report
    re-forced; a forced report that ALSO truncates returns [] — never the
    partial themes."""
    _quiet_infra(monkeypatch)
    stocks = _mk_stocks(4, monkeypatch)
    sbt = {s["ticker"]: s for s in stocks}
    partial = _disc_report([{"name": "Half A Theme", "thesis": "cut",
                             "tickers": ["T000", "T001"]}],
                           stop_reason="max_tokens")
    complete = _disc_report([{"name": "Real Theme", "thesis": "ok",
                              "tickers": ["T002", "T003"]}])
    client, calls = _fake_client([partial, complete])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    out = asyncio.run(te._discover_new_themes(stocks, [], sbt))

    assert len(calls) == 2
    assert calls[1]["tool_choice"] == {"type": "tool", "name": "report_themes"}
    assert [t["name"] for t in out] == ["Real Theme"], \
        "a TRUNCATED report's partial themes were accepted as genuine"

    # forced retry ALSO truncated → honest empty, not the partial
    client2, calls2 = _fake_client([partial, partial])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client2)
    out2 = asyncio.run(te._discover_new_themes(stocks, [], sbt))
    assert out2 == [] and len(calls2) == 2, \
        "a doubly-truncated discovery call must return [] loudly, not partial themes"


# ── split: truncation is a failure, never a decline ──────────────────────────

def _split_theme():
    return {"name": "Fat Theme", "tickers": [f"S{i:02d}" for i in range(23)],
            "score": 70.0, "stage": "Mainstream"}


def test_split_truncation_is_not_a_decline(monkeypatch):
    """Twice on 2026-08-10 a truncated split response parsed as propose_split
    with `split` missing and was logged 'Sonnet found theme already coherent'.
    A max_tokens response must return no-split WITHOUT the fat_theme_no_split
    (coherent) audit row — the #543 truncation alarm is the signal."""
    events = _quiet_infra(monkeypatch)
    truncated = _resp(_Block("tool_use", name="propose_split",
                             input={"analysis_scratchpad": "cut off mid-"}),
                      stop_reason="max_tokens", out_tok=1750)
    client, calls = _fake_client([truncated])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    sub, advisor = asyncio.run(te._split_fat_theme(_split_theme(), {}, 0))

    assert sub is None and advisor == 0
    assert not any(e[0] == "fat_theme_no_split" for e in events), \
        "a TRUNCATED split response was logged as an affirmative 'already coherent'"


def test_split_genuine_decline_still_logs_no_split(monkeypatch):
    """Contrast pin: an honest, completed decline (split=null, natural stop)
    must STILL write fat_theme_no_split — truncation honesty must not silence
    real declines."""
    events = _quiet_infra(monkeypatch)
    decline = _resp(_Block("tool_use", name="propose_split",
                           input={"analysis_scratchpad": "coherent", "split": None}),
                    stop_reason="tool_use")
    client, calls = _fake_client([decline])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    sub, _ = asyncio.run(te._split_fat_theme(_split_theme(), {}, 0))

    assert sub is None
    assert any(e[0] == "fat_theme_no_split" for e in events)


def test_split_forces_a_tool_call_and_terse_scratchpad(monkeypatch):
    """The proven anti-budget-burn recipe applied to split: tool_choice=any (free
    text cannot eat the budget; the advisor path survives because consult_advisor
    is a tool) + the terse scratchpad contract in the schema."""
    _quiet_infra(monkeypatch)
    decline = _resp(_Block("tool_use", name="propose_split",
                           input={"analysis_scratchpad": "x", "split": None}))
    client, calls = _fake_client([decline])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: client)

    asyncio.run(te._split_fat_theme(_split_theme(), {}, 0))

    assert calls[0]["tool_choice"] == {"type": "any"}, \
        "split reverted to tool_choice=auto — pre-tool prose can burn the budget again"
    desc = te._SPLIT_TOOL["input_schema"]["properties"]["analysis_scratchpad"]["description"]
    assert "KEEP IT SHORT" in desc and "not per stock" in desc.lower(), \
        "split scratchpad lost its terse contract — verbosity truncation returns"
    prompt = calls[0]["messages"][0]["content"]
    assert "Do NOT write any free-text analysis before your tool call" in prompt
