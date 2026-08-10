"""#167 Lane-2 grouping v2 — REGISTRY mode (operator-ruled 2026-07-27) — flag-gated pins.

The load-bearing contracts:
1. Flag OFF ⇒ discover_narrative_themes is BYTE-IDENTICAL to the pre-flag v1
   behavior — the prompt is compared against a FROZEN copy of the original v1
   template (any drift of the shared _LANE2_NARRATIVE_RULES / contract strings
   breaks this test), and no registry surface is ever touched.
2. Registry memory horizon is 10 TRADING days (weekend-skipping) — the
   operator's measured chain (WULF 07-06 → HUT/IREN 07-20; seed link
   WULF→CLSK = 8 calendar days) must fit.
3. Dedup is STRUCTURAL: a continuing story JOINS the active narrative —
   registry name + thesis are FROZEN (never the model's re-wording), and two
   same-run proposals of the same story collapse to ONE row.
4. Precision floor: a genuinely DIFFERENT narrative is NOT merged; member
   overlap with an active narrative only fires a surface-only tripwire audit.
5. Walls: 'narrative_seed' can never auto-promote nor reach the judge's
   active_narratives; the roster readers are hard-scoped to the lane's own
   sources (anti-circularity — judge_inferred/coverage_probe never enter).
6. Missing grounded_text degrades gracefully (grounded → claude_analysis →
   catalyst) and the fallback mix is VISIBLE in the audit summary.

GRADE-AFFECTING context: Lane-2 proposals feed the judge's active_narratives
(ep_detector → assemble_judge_inputs) and can auto-promote into live mi_themes,
so the OFF-is-identical pin is a money-path safety, not a style preference.
"""
from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.db as db
import agents.market_intelligence.spend_tracker as spend_tracker
from agents.market_intelligence import theme_engine
from agents.market_intelligence.theme_engine import (
    LANE2_REGISTRY_MAX_MEMBERS,
    LANE2_SEED_STORY_BUDGET,
    LANE2_WINDOW_TRADING_DAYS,
    _lane2_registry_clean,
    _lane2_window_start,
    _norm_narrative_name,
    discover_narrative_themes,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

_LONG_CATALYST = ("WULF gapped up because the company announced a transformative agreement. " * 10)[:500]
_GROUNDED = (
    "8-K: TeraWulf entered a 20-year lease with a global technology company for "
    "AI data center campus capacity at its Lake Mariner facility, with expected "
    "revenue of approximately $3.7 billion over the initial term. " * 20
)


def _alert(ticker, d, ep=80.0, gap=12.0, catalyst=_LONG_CATALYST,
           analysis="Grounded analysis: AI data-center capacity lease.",
           grounded=_GROUNDED):
    return {
        "ticker": ticker, "alert_date": d, "ep_score": ep, "gap_pct": gap,
        "catalyst": catalyst, "claude_analysis": analysis, "grounded_text": grounded,
    }


def _narrative(name, tickers, d=date(2026, 7, 20), thesis="Frozen registry thesis."):
    return {"run_date": d, "name": name, "tickers": list(tickers), "thesis": thesis}


def _seed(ticker, d=date(2026, 7, 6), story="20-year AI data-center lease worth $3.7B."):
    return {"run_date": d, "ticker": ticker, "story": story}


class _FakeMsg:
    def __init__(self, text, stop_reason="tool_use"):
        # 2026-08-10: the lane uses a FORCED tool call (output bounded by
        # construction — see _LANE2_NARRATIVE_TOOL). The scripted JSON is
        # delivered as the tool_use input, exactly as the API would return it.
        import json as _json
        self.content = [SimpleNamespace(type="tool_use",
                                        name="report_narrative_themes",
                                        input=_json.loads(text), id="t1")]
        self.usage = None
        self.stop_reason = stop_reason


def _wire(monkeypatch, *, flag_on, today_alerts=(), active=(), pending=(),
          llm_response='{"themes": [], "seeds": []}'):
    """Patch every side-effecting dependency; return (captured_kwargs, mocks)."""
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeMsg(llm_response)

    client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: client)

    async def _noop_spend(**kwargs):
        return None

    monkeypatch.setattr(spend_tracker, "log_anthropic_call_safe", _noop_spend)

    mocks = SimpleNamespace(
        flag=AsyncMock(return_value=flag_on),
        today=AsyncMock(return_value=list(today_alerts)),
        active=AsyncMock(return_value=[dict(n) for n in active]),
        pending=AsyncMock(return_value=[dict(s) for s in pending]),
        persist=AsyncMock(side_effect=lambda d, themes, backfilled=False: len(themes)),
        persist_seeds=AsyncMock(side_effect=lambda d, seeds: len(seeds)),
        audit=AsyncMock(),
    )
    monkeypatch.setattr(db, "get_lane2_grouping_v2_enabled", mocks.flag)
    monkeypatch.setattr(db, "get_today_ep_alerts", mocks.today)
    monkeypatch.setattr(db, "get_lane2_active_narratives", mocks.active)
    monkeypatch.setattr(db, "get_lane2_pending_seeds", mocks.pending)
    monkeypatch.setattr(db, "persist_narrative_theme_candidates", mocks.persist)
    monkeypatch.setattr(db, "persist_lane2_seeds", mocks.persist_seeds)
    monkeypatch.setattr(db, "log_audit_event", mocks.audit)
    return captured, mocks


# ── 1. flag OFF ⇒ byte-identical v1 ──────────────────────────────────────────

def _v1_frozen_prompt(cand):
    """VERBATIM copy of the pre-flag v1 prompt construction (git d8f0ef3 era).
    Do NOT 'refactor' this to reuse theme_engine constants — its entire point
    is to be an independent frozen reference the shared constants are checked
    against."""
    lines = []
    for a in cand:
        cat = (a.get("catalyst") or a.get("claude_analysis") or "")[:280]
        lines.append(f"- {a['ticker']} (gap {a.get('gap_pct','?')}%, ep {a.get('ep_score')}): {cat}")
    return (
        "Below are today's gap-up momentum stocks and their catalysts. Identify EMERGING "
        "NARRATIVE THEMES that 2 OR MORE of them genuinely SHARE. Themes MAY span sectors and "
        "RS levels (e.g. a government-policy theme spanning Industrials + Tech + Defense). A theme "
        "must be a real shared story/catalyst, NOT a generic sector label.\n"
        "CRITICAL: a theme is a SPECIFIC shared NARRATIVE / DRIVER (a technology cycle, a "
        "government policy, a supply shortage, a product category, a specific industry catalyst) "
        "— NOT a generic CATALYST-TYPE that names coincidentally share because of the calendar. "
        "'They all beat Q1 earnings', 'broad earnings-beat momentum', 'raised guidance', or "
        "'relief rally' are NOT themes (those are catalyst categories, not narratives). A bare "
        "one-word catchall ('AI', 'software', 'tech') is also too generic — BUT a SPECIFIC "
        "AI/tech-DRIVEN narrative IS a valid theme (e.g. 'AI-native/vertical SaaS adoption', "
        "'AI data-center buildout', 'edge-AI silicon'). Group ONLY when the names share a SPECIFIC "
        "emerging story a trader would name as a theme (e.g. 'nuclear/AI power demand', 'defense "
        "drone expansion', 'quantum computing', 'GLP-1 obesity', 'edge-AI silicon', 'AI-native SaaS'). "
        "If there is NO genuine shared narrative across 2+ of these names, return an EMPTY "
        "list — do NOT force groupings.\n\n"
        "Stocks:\n" + "\n".join(lines) + "\n\n"
        'Return ONLY JSON: {"themes":[{"name":"<=6 words","catalyst_type":"theme|govt_policy|shortage|'
        'sales_acceleration|new_product|management_change|other","tickers":["TICK","TICK"],"thesis":"one sentence"}]}. '
        "Include a theme ONLY if 2+ of the listed tickers truly share it; otherwise themes=[]. "
        "The name's breadth must match the group: every grouped ticker must individually fit the name."
    )


@pytest.mark.asyncio
async def test_flag_off_is_byte_identical_v1(monkeypatch):
    d = date(2026, 7, 14)
    cand = [_alert("CLSK", d, ep=61.0), _alert("TSEM", d, ep=55.0)]
    captured, mocks = _wire(
        monkeypatch, flag_on=False, today_alerts=cand,
        llm_response='{"themes": [{"name": "AI data-center buildout", '
                     '"catalyst_type": "theme", "tickers": ["CLSK", "TSEM"], '
                     '"thesis": "Both add AI DC capacity."}]}')

    out = await discover_narrative_themes(d)

    # Exact prompt bytes of the pre-flag implementation — grounded_text unread,
    # 280-char truncation intact, no roster blocks, no seeds contract.
    assert captured["messages"][0]["content"] == _v1_frozen_prompt(cand)
    assert captured["model"] == theme_engine.THEME_MODEL
    assert captured["max_tokens"] == 1500
    # v1 path never touches any registry surface.
    mocks.active.assert_not_awaited()
    mocks.pending.assert_not_awaited()
    mocks.persist_seeds.assert_not_awaited()
    mocks.today.assert_awaited_once()
    assert out["themes"] == 1 and out["names"] == ["AI data-center buildout"]
    assert "registry" not in out and "input_sources" not in out and "proposals" not in out
    # v1 audit summary format unchanged.
    assert mocks.audit.await_args.args[1] == \
        "2026-07-14: 2 alerts -> 1 narrative theme(s): ['AI data-center buildout']"


@pytest.mark.asyncio
async def test_flag_off_below_two_gate_unchanged(monkeypatch):
    d = date(2026, 7, 6)
    captured, mocks = _wire(monkeypatch, flag_on=False,
                            today_alerts=[_alert("WULF", d, ep=96.0)])
    out = await discover_narrative_themes(d)
    assert out["alerts"] == 1 and out["themes"] == 0
    assert not captured  # no LLM call
    assert mocks.audit.await_args.args[1] == \
        "2026-07-06: 1 qualifying alert(s) (<2) — no grouping"


@pytest.mark.asyncio
async def test_flag_fail_closed_on_db_error(monkeypatch):
    # The toggle read failing must select the v1 lane, never raise.
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert await db.get_lane2_grouping_v2_enabled() is False


# ── 2. ten TRADING days of registry memory, not calendar ─────────────────────

def test_memory_horizon_ten_trading_days_across_weekends():
    # Operator-measured chain: from Mon 2026-07-20, ten trading days back is
    # Mon 2026-07-06 — a narrative/seed last touched 07-06 must still be
    # visible on 07-20 (WULF chain), and the WULF→CLSK seed link (07-06 →
    # 07-14 = 8 CALENDAR days) must survive — a 7-calendar-day expiry would
    # kill it one day short.
    assert LANE2_WINDOW_TRADING_DAYS == 10
    assert _lane2_window_start(date(2026, 7, 20)) == date(2026, 7, 6)
    assert _lane2_window_start(date(2026, 7, 14)) <= date(2026, 7, 6)  # seed link survives
    # Mid-week anchor crossing two weekends.
    assert _lane2_window_start(date(2026, 6, 17)) == date(2026, 6, 3)
    assert (date(2026, 7, 20) - _lane2_window_start(date(2026, 7, 20))).days == 14


# ── 3. input fallback chain + degraded-day visibility ────────────────────────

def test_input_text_fallback_chain_budgets_and_flattening():
    d = date(2026, 7, 14)
    # Mid-doc evidence beyond any head-slice must survive: the replay pull
    # falsified a 2.5k head budget (SEC boilerplate head; CLSK 'AI'@6394,
    # JBL 'AI'@4430) — the budget is a >=10k safety ceiling, full-doc in
    # practice (era max grounded_text = 9,615 chars).
    assert theme_engine.LANE2_GROUNDED_BUDGET >= 9615
    rich = _alert("WULF", d, grounded="  line one\nline two  " + "x" * 6300 + " AI data-center lease " + "y" * 2000)
    text, tag = theme_engine._lane2_input_text(rich)
    assert tag == "grounded"
    assert len(text) <= theme_engine.LANE2_GROUNDED_BUDGET
    assert "AI data-center lease" in text  # deep-in-doc evidence retained
    assert "\n" not in text and text.startswith("line one line two")

    no_grounded = _alert("CLSK", d, grounded=None)
    text, tag = theme_engine._lane2_input_text(no_grounded)
    assert tag == "analysis" and text.startswith("Grounded analysis:")

    catalyst_only = _alert("TSEM", d, grounded="   ", analysis=None)
    text, tag = theme_engine._lane2_input_text(catalyst_only)
    assert tag == "catalyst" and len(text) <= theme_engine.LANE2_CATALYST_BUDGET

    barren = _alert("HQ", d, grounded=None, analysis=None, catalyst=None)
    assert theme_engine._lane2_input_text(barren) == ("", "none")  # never crashes


@pytest.mark.asyncio
async def test_v2reg_degraded_day_visible_in_audit_summary(monkeypatch):
    today = date(2026, 7, 14)
    alerts = [
        _alert("WULF", today, ep=96.0),                                # grounded
        _alert("CLSK", today, ep=61.0, grounded=None),                 # → analysis
        _alert("TSEM", today, ep=55.0, grounded=None, analysis=None),  # → catalyst
    ]
    captured, mocks = _wire(monkeypatch, flag_on=True, today_alerts=alerts)
    out = await discover_narrative_themes(today)
    assert out["input_sources"] == {"grounded": 1, "analysis": 1, "catalyst": 1, "none": 0}
    summary = mocks.audit.await_args.args[1]
    assert "grounded=1 analysis=1 catalyst=1" in summary
    assert "v2reg" in summary


# ── v2 REGISTRY: gate, cold start, roster plumbing ───────────────────────────

@pytest.mark.asyncio
async def test_v2reg_gate_zero_qualifying_today_no_llm(monkeypatch):
    today = date(2026, 7, 20)
    # Rich registry but nothing qualifying today → no LLM call, state untouched.
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("JUNK", today, ep=42.0)],  # below ep 50
        active=[_narrative("Miners pivot to AI", ["WULF", "CLSK"])])
    out = await discover_narrative_themes(today)
    assert not captured and out["themes"] == 0
    assert out["alerts"] == 0 and out["registry"] == {"active": 1, "seeds": 0}
    assert "no evaluation" in mocks.audit.await_args.args[1]
    mocks.persist.assert_not_awaited()
    mocks.persist_seeds.assert_not_awaited()
    # Roster readers are called with the trading-day window, PRIOR days only.
    mocks.active.assert_awaited_once_with(_lane2_window_start(today), today)
    mocks.pending.assert_awaited_once_with(_lane2_window_start(today), today)


@pytest.mark.asyncio
async def test_v2reg_cold_start_omits_roster_blocks_and_births_from_today(monkeypatch):
    # Empty registry (cold start / post-outage drain): prompt degrades to
    # v1-plus-seeds; 2+ same-day names can still birth a narrative.
    today = date(2026, 6, 11)
    alerts = [_alert("HUT", today, ep=75.0), _alert("IREN", today, ep=72.0)]
    captured, mocks = _wire(
        monkeypatch, flag_on=True, today_alerts=alerts,
        llm_response='{"themes": [{"name": "Miners to AI data centers", '
                     '"catalyst_type": "theme", "tickers": ["HUT", "IREN"], '
                     '"thesis": "Both lease HPC capacity."}], "seeds": []}')
    out = await discover_narrative_themes(today)
    prompt = captured["messages"][0]["content"]
    assert "ACTIVE tracked narratives (from prior sessions):" not in prompt  # roster block absent
    assert "WATCH LIST (recent single-name stories" not in prompt
    assert "Stocks TODAY:" in prompt and '"seeds"' in prompt
    assert out["themes"] == 1 and out["born"] == ["Miners to AI data centers"]
    assert out["joined"] == [] and out["registry"] == {"active": 0, "seeds": 0}


# ── v2 REGISTRY: structural dedup (JOIN) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_v2reg_join_keeps_registry_identity_and_unions_members(monkeypatch):
    today = date(2026, 7, 22)
    reg = _narrative("AI data-center infrastructure buildout", ["WULF", "CLSK"],
                     d=date(2026, 7, 20), thesis="Frozen registry thesis.")
    # Model reuses the name modulo case/punctuation (normalize must catch it)
    # and re-words the thesis — the registry identity must win on BOTH.
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("APLD", today, ep=70.0)],
        active=[reg],
        llm_response='{"themes": [{"name": "AI Data Center Infrastructure Buildout", '
                     '"catalyst_type": "theme", "tickers": ["APLD", "WULF"], '
                     '"thesis": "A re-worded thesis that must NOT stick."}], "seeds": []}')
    out = await discover_narrative_themes(today)
    persisted = mocks.persist.await_args.args[1]
    assert len(persisted) == 1
    assert persisted[0]["name"] == "AI data-center infrastructure buildout"  # verbatim registry name
    assert persisted[0]["tickers"] == ["WULF", "CLSK", "APLD"]  # union, join order kept
    assert persisted[0]["thesis"] == "Frozen registry thesis."  # thesis frozen at birth
    assert out["joined"] == ["AI data-center infrastructure buildout"] and out["born"] == []
    assert "1 join + 0 new" in mocks.audit.await_args.args[1]
    # A joined proposal refreshes the SAME name → downstream DISTINCT ON (name)
    # (judge context + auto-promote) sees ONE cohort, not a near-duplicate.


@pytest.mark.asyncio
async def test_v2reg_same_run_reproposals_collapse_to_one_row(monkeypatch):
    # The 18-of-23 failure class: the same story proposed twice under different
    # wordings in ONE response must collapse into ONE persisted row.
    today = date(2026, 7, 22)
    reg = _narrative("AI data center power infrastructure deals", ["VRT", "ETN"])
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("PWR", today, ep=66.0), _alert("NRG", today, ep=64.0)],
        active=[reg],
        llm_response='{"themes": ['
                     '{"name": "AI data center power infrastructure deals", '
                     '"catalyst_type": "theme", "tickers": ["PWR", "VRT"], "thesis": "x"}, '
                     '{"name": "AI Data-Center Power Infrastructure Deals", '
                     '"catalyst_type": "theme", "tickers": ["NRG", "ETN"], "thesis": "y"}], '
                     '"seeds": []}')
    out = await discover_narrative_themes(today)
    persisted = mocks.persist.await_args.args[1]
    assert len(persisted) == 1 and out["themes"] == 1
    assert persisted[0]["name"] == "AI data center power infrastructure deals"
    assert persisted[0]["tickers"] == ["VRT", "ETN", "PWR", "NRG"]


@pytest.mark.asyncio
async def test_v2reg_join_requires_fresh_today_evidence(monkeypatch):
    # A "join" that adds no same-day qualifying ticker is a re-listing touch —
    # dropped, so a narrative can never keep itself alive (staleness must bite)
    # and the model cannot resurrect a story with zero fresh market evidence.
    today = date(2026, 7, 22)
    reg = _narrative("Miners pivot to AI", ["WULF", "CLSK"])
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("GOLD", today, ep=60.0)],
        active=[reg], pending=[_seed("HUT", d=date(2026, 7, 15))],
        llm_response='{"themes": ['
                     '{"name": "Miners pivot to AI", "catalyst_type": "theme", '
                     '"tickers": ["WULF", "CLSK"], "thesis": "re-listing"}, '
                     '{"name": "Miners pivot to AI", "catalyst_type": "theme", '
                     '"tickers": ["HUT"], "thesis": "seed-only touch"}], "seeds": []}')
    out = await discover_narrative_themes(today)
    assert out["themes"] == 0 and out["names"] == []
    assert mocks.persist.await_args.args[1] == []


# ── v2 REGISTRY: precision floor + tripwire ──────────────────────────────────

@pytest.mark.asyncio
async def test_v2reg_precision_floor_distinct_story_not_merged(monkeypatch):
    # A genuinely different narrative (no name match, no member overlap) must
    # persist as its OWN row — over-merging is as bad as under-merging.
    today = date(2026, 6, 15)
    reg = _narrative("AI data-center infrastructure buildout", ["NVDA", "VRT"])
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("GOLD", today, ep=68.0), _alert("AEM", today, ep=63.0)],
        active=[reg],
        llm_response='{"themes": [{"name": "Precious metals breakout", '
                     '"catalyst_type": "theme", "tickers": ["GOLD", "AEM"], '
                     '"thesis": "Gold miners surge on metal highs."}], "seeds": []}')
    out = await discover_narrative_themes(today)
    persisted = mocks.persist.await_args.args[1]
    assert [t["name"] for t in persisted] == ["Precious metals breakout"]
    assert persisted[0]["thesis"] == "Gold miners surge on metal highs."  # model thesis kept for births
    assert out["born"] == ["Precious metals breakout"] and out["joined"] == []
    # No overlap → no duplicate tripwire.
    assert not [c for c in mocks.audit.await_args_list
                if c.args[0] == "lane2_possible_duplicate_narrative"]


@pytest.mark.asyncio
async def test_v2reg_overlap_tripwire_surfaces_but_never_merges(monkeypatch):
    # Same cohort, plausibly different story: surfaced to the operator via an
    # audit event, persisted UNMERGED — the filter list is the operator's call.
    today = date(2026, 7, 23)
    reg = _narrative("Miners pivot to AI", ["CLSK", "HUT", "WULF"])
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("CLSK", today, ep=71.0), _alert("HUT", today, ep=65.0)],
        active=[reg],
        llm_response='{"themes": [{"name": "Bitcoin halving supply squeeze", '
                     '"catalyst_type": "theme", "tickers": ["CLSK", "HUT"], '
                     '"thesis": "Halving economics squeeze."}], "seeds": []}')
    out = await discover_narrative_themes(today)
    assert out["born"] == ["Bitcoin halving supply squeeze"]  # persisted, not merged
    trip = [c for c in mocks.audit.await_args_list
            if c.args[0] == "lane2_possible_duplicate_narrative"]
    assert len(trip) == 1
    assert "'Bitcoin halving supply squeeze'" in trip[0].args[1]
    assert "'Miners pivot to AI'" in trip[0].args[1]
    assert "NOT auto-merged" in trip[0].args[1]


# ── v2 REGISTRY: seeds (cross-day birth without a pool) ──────────────────────

@pytest.mark.asyncio
async def test_v2reg_lone_alert_becomes_seed(monkeypatch):
    # The WULF 07-06 class: a lone qualifying alert with a real story becomes a
    # watch-list seed (story whitespace-collapsed + budgeted) — NOT a theme.
    today = date(2026, 7, 6)
    captured, mocks = _wire(
        monkeypatch, flag_on=True, today_alerts=[_alert("WULF", today, ep=96.0)],
        llm_response='{"themes": [], "seeds": [{"ticker": "WULF", '
                     '"story": "20-year  AI data-center\\nlease with hyperscaler, ~$3.7B."}]}')
    out = await discover_narrative_themes(today)
    assert out["themes"] == 0 and out["seeds"] == 1
    seeds = mocks.persist_seeds.await_args.args[1]
    assert seeds == [{"ticker": "WULF",
                      "story": "20-year AI data-center lease with hyperscaler, ~$3.7B."}]
    assert len(seeds[0]["story"]) <= LANE2_SEED_STORY_BUDGET


@pytest.mark.asyncio
async def test_v2reg_seed_pairs_with_today_alert_to_birth_narrative(monkeypatch):
    # The CLSK 07-14 class: today's lone alert + a prior-day seed = a 2-member
    # birth — the cross-day accretion the pool used to provide, without
    # re-reading prior days' documents.
    today = date(2026, 7, 14)
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("CLSK", today, ep=61.0)],
        pending=[_seed("WULF", d=date(2026, 7, 6))],
        llm_response='{"themes": [{"name": "Bitcoin miners pivot to AI leases", '
                     '"catalyst_type": "theme", "tickers": ["WULF", "CLSK"], '
                     '"thesis": "Miners lease HPC capacity to AI tenants."}], "seeds": []}')
    out = await discover_narrative_themes(today)
    prompt = captured["messages"][0]["content"]
    assert "WATCH LIST" in prompt and "- WULF (2026-07-06):" in prompt
    persisted = mocks.persist.await_args.args[1]
    assert persisted[0]["tickers"] == ["WULF", "CLSK"]
    assert out["born"] == ["Bitcoin miners pivot to AI leases"]


@pytest.mark.asyncio
async def test_v2reg_seed_hygiene_placed_member_and_hallucinated_dropped(monkeypatch):
    today = date(2026, 7, 20)
    reg = _narrative("Miners pivot to AI", ["WULF", "CLSK"])
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("HUT", today, ep=75.0), _alert("IREN", today, ep=72.0)],
        active=[reg],
        llm_response='{"themes": [{"name": "Miners pivot to AI", '
                     '"catalyst_type": "theme", "tickers": ["HUT", "WULF"], "thesis": "j"}], '
                     '"seeds": ['
                     '{"ticker": "HUT", "story": "placed tonight — must not seed"}, '
                     '{"ticker": "CLSK", "story": "already a member — must not seed"}, '
                     '{"ticker": "ZZZZ", "story": "not qualifying today — hallucinated"}, '
                     '{"ticker": "IREN", "story": "real leftover story"}, '
                     '{"ticker": "IREN", "story": "duplicate entry"}]}')
    out = await discover_narrative_themes(today)
    seeds = mocks.persist_seeds.await_args.args[1]
    assert seeds == [{"ticker": "IREN", "story": "real leftover story"}]
    assert out["seeds"] == 1


@pytest.mark.asyncio
async def test_v2reg_roster_hygiene_seed_superseded_by_membership_and_today(monkeypatch):
    # A seed whose ticker is already a narrative member (consumed) or alerts
    # again today (superseded by fresh evidence) never re-enters the prompt.
    today = date(2026, 7, 21)
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("IREN", today, ep=70.0), _alert("APLD", today, ep=66.0)],
        active=[_narrative("Miners pivot to AI", ["WULF", "CLSK"])],
        pending=[_seed("CLSK"), _seed("IREN"), _seed("SMCI", story="AI server demand")])
    out = await discover_narrative_themes(today)
    prompt = captured["messages"][0]["content"]
    # Seed lines carry a dated prefix "- TICK (YYYY-MM-DD):" — distinct from
    # today-stock lines "- TICK (gap …" — so match on the dated form.
    assert "- SMCI (2026-07-06):" in prompt   # genuine pending seed survives
    assert "- CLSK (2026-" not in prompt      # consumed by membership
    assert "- IREN (2026-" not in prompt      # superseded by today's own alert line
    assert out["registry"] == {"active": 1, "seeds": 1}


# ── v2 REGISTRY: ticker hygiene + member cap ─────────────────────────────────

@pytest.mark.asyncio
async def test_v2reg_birth_needs_two_real_members_and_today_anchor(monkeypatch):
    today = date(2026, 7, 20)
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("HUT", today, ep=75.0)],
        pending=[_seed("WULF"), _seed("CLSK")],
        llm_response='{"themes": ['
                     # hallucinated member filtered → 1 real member → dropped
                     '{"name": "Broken cohort", "catalyst_type": "theme", '
                     '"tickers": ["HUT", "FAKE"], "thesis": "x"}, '
                     # seed-only birth (no today anchor) → dropped
                     '{"name": "Stale seed pair", "catalyst_type": "theme", '
                     '"tickers": ["WULF", "CLSK"], "thesis": "y"}], "seeds": []}')
    out = await discover_narrative_themes(today)
    assert out["themes"] == 0 and mocks.persist.await_args.args[1] == []


def test_v2reg_member_cap_fifo_drops_oldest():
    active = [_narrative("Mega story", [f"T{i:02d}" for i in range(11)])]  # 11 members
    themes = [{"name": "Mega story", "catalyst_type": "theme",
               "tickers": ["NEW1", "NEW2"], "thesis": "join"}]
    clean, seeds, dups = _lane2_registry_clean(
        themes, [], active, [], today_set={"NEW1", "NEW2"})
    assert len(clean) == 1
    got = clean[0]["tickers"]
    assert len(got) == LANE2_REGISTRY_MAX_MEMBERS == 12
    assert got[-2:] == ["NEW1", "NEW2"]      # newest joiners kept
    assert "T00" not in got and got[0] == "T01"  # oldest member aged off the front


def test_v2reg_norm_name_matches_wording_drift_not_different_stories():
    assert _norm_narrative_name("AI Data-Center  Buildout!") == \
        _norm_narrative_name("ai data center buildout")
    assert _norm_narrative_name("AI data center power deals") != \
        _norm_narrative_name("AI data center leasing boom")


# ── v2 REGISTRY: birth bias correction + decision-record telemetry ───────────

@pytest.mark.asyncio
async def test_v2reg_prompt_orders_join_new_seed_with_seed_as_last_resort(monkeypatch):
    # First registry replay regression: seeding was costless and the model
    # filed shared stories as separate seeds (06-17 AEHR+JBL; 07-20 IREN).
    # Pin the corrected decision block: JOIN → NEW(expected) → SEED(last
    # resort) + the pre-answer self-check. Deterministic guards unchanged.
    today = date(2026, 6, 17)
    captured, _ = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("AEHR", today, ep=70.0), _alert("JBL", today, ep=68.0)])
    await discover_narrative_themes(today)
    prompt = captured["messages"][0]["content"]
    assert "Decide in this order." in prompt
    assert "you MUST return them as ONE new themes entry" in prompt
    assert "never file the same story as two separate seeds" in prompt
    assert "must be JOINED, never seeded" in prompt
    assert "SEED — last resort" in prompt
    assert "re-check your seeds" in prompt
    assert prompt.index("1) JOIN:") < prompt.index("2) NEW:") < prompt.index("3) SEED")


@pytest.mark.asyncio
async def test_v2reg_decision_record_outcomes_and_seed_conversion(monkeypatch):
    # Operator: "if this info is captured, it allows us to tune over time" —
    # per-name outcome + seed→narrative conversions, one audit row per
    # evaluated night, queryable JSON detail (lane2_seed_birth_calibration
    # review keys off it).
    import json as _json
    today = date(2026, 7, 14)
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("CLSK", today, ep=61.0),
                      _alert("IREN", today, ep=64.0),
                      _alert("WDFC", today, ep=55.0)],
        active=[_narrative("Clean-power infrastructure for AI compute", ["APLD"])],
        pending=[_seed("WULF", d=date(2026, 7, 6))],
        llm_response='{"themes": ['
                     '{"name": "Clean-power infrastructure for AI compute", '
                     '"catalyst_type": "theme", "tickers": ["CLSK", "WULF"], '
                     '"thesis": "join with seed conversion"}], '
                     '"seeds": [{"ticker": "IREN", "story": "GPU cloud contract"}]}')
    out = await discover_narrative_themes(today)
    recs = [c for c in mocks.audit.await_args_list
            if c.args[0] == "lane2_decision_record"]
    assert len(recs) == 1
    assert "offered=3 join=1 birth=0 seed=1 none=1 conversions=1" in recs[0].args[1]
    detail = _json.loads(recs[0].kwargs.get("detail") or recs[0].args[2])
    assert detail == out["decision_record"]
    assert detail["offered"] == ["CLSK", "IREN", "WDFC"]
    assert detail["outcomes"]["CLSK"] == {
        "outcome": "join", "narrative": "Clean-power infrastructure for AI compute"}
    assert detail["outcomes"]["IREN"] == {"outcome": "seed"}
    assert detail["outcomes"]["WDFC"] == {"outcome": "none"}
    # WULF: seeded 07-06, pulled into the narrative 07-14 → conversion, lag 8d.
    assert detail["seed_conversions"] == [{
        "ticker": "WULF", "seeded": "2026-07-06", "lag_days": 8,
        "narrative": "Clean-power infrastructure for AI compute"}]
    # The record precedes the run summary — the LAST audit call is still the
    # narrative_theme_discovery_ran line (pinned elsewhere).
    assert mocks.audit.await_args.args[0] == "narrative_theme_discovery_ran"


@pytest.mark.asyncio
async def test_v2reg_decision_record_counts_conversion_even_when_seed_realerts_today(monkeypatch):
    # Hygiene hides a re-alerting seed from the prompt, but conversion
    # telemetry must still see it: WULF seeded 07-06, re-alerts 07-14 and
    # joins → conversion with lag, keyed off the PRE-hygiene seed map.
    import json as _json
    today = date(2026, 7, 14)
    captured, mocks = _wire(
        monkeypatch, flag_on=True,
        today_alerts=[_alert("WULF", today, ep=88.0), _alert("CLSK", today, ep=61.0)],
        pending=[_seed("WULF", d=date(2026, 7, 6))],
        llm_response='{"themes": [{"name": "Miners pivot to AI leases", '
                     '"catalyst_type": "theme", "tickers": ["WULF", "CLSK"], '
                     '"thesis": "birth"}], "seeds": []}')
    out = await discover_narrative_themes(today)
    conv = out["decision_record"]["seed_conversions"]
    assert conv == [{"ticker": "WULF", "seeded": "2026-07-06", "lag_days": 8,
                     "narrative": "Miners pivot to AI leases"}]
    assert out["decision_record"]["outcomes"]["WULF"]["outcome"] == "birth"
    # And the seed line itself was hidden from the prompt (superseded by today).
    assert "- WULF (2026-07-06):" not in captured["messages"][0]["content"]
    _json.loads([c for c in mocks.audit.await_args_list
                 if c.args[0] == "lane2_decision_record"][0].kwargs.get("detail"))


@pytest.mark.asyncio
async def test_v2reg_decision_record_not_persisted_on_backfill(monkeypatch):
    # Hindsight runs must not pollute the forward calibration stream — the
    # record still rides on `out` (the replay chains off it) but no
    # lane2_decision_record audit row is written.
    today = date(2026, 7, 6)
    captured, mocks = _wire(
        monkeypatch, flag_on=True, today_alerts=[_alert("WULF", today, ep=96.0)],
        llm_response='{"themes": [], "seeds": [{"ticker": "WULF", "story": "s"}]}')
    out = await discover_narrative_themes(today, persist=True, backfilled=True)
    assert out["decision_record"]["outcomes"]["WULF"] == {"outcome": "seed"}
    assert not [c for c in mocks.audit.await_args_list
                if c.args[0] == "lane2_decision_record"]


# ── v2 REGISTRY: walls (anti-circularity + auto-promote) ─────────────────────

def test_v2reg_walls_by_construction():
    # 1. Watch-list seeds can NEVER auto-promote into live mi_themes …
    assert "narrative_seed" not in db.AUTO_PROMOTE_THEME_SOURCES
    # … and NEVER reach the judge's active_narratives input.
    assert "narrative_seed" not in inspect.getsource(db.get_narrative_theme_candidates)
    # 2. The roster the model sees comes from the lane's OWN output only —
    # a judge inference (judge_inferred) or probe row can never steer the lane
    # that feeds the judge (the judge_theme_gap.py anti-circularity wall).
    for fn in (db.get_lane2_active_narratives, db.get_lane2_pending_seeds):
        src = inspect.getsource(fn)
        sql = src[src.index('conn.fetch'):]
        assert "judge_inferred" not in sql and "coverage_probe" not in sql
        assert "backfill" not in sql and "rs_slope_synthesis" not in sql and "shadow_v2" not in sql
    assert "source = 'narrative_cogap'" in inspect.getsource(db.get_lane2_active_narratives)
    assert "source = 'narrative_seed'" in inspect.getsource(db.get_lane2_pending_seeds)


@pytest.mark.asyncio
async def test_v2reg_backfill_never_writes_seeds(monkeypatch):
    # Hindsight (backfill) runs must not plant seeds into the FORWARD watch
    # list — themes go to the segregated backfill source, seeds are skipped.
    today = date(2026, 7, 6)
    captured, mocks = _wire(
        monkeypatch, flag_on=True, today_alerts=[_alert("WULF", today, ep=96.0)],
        llm_response='{"themes": [], "seeds": [{"ticker": "WULF", "story": "s"}]}')
    out = await discover_narrative_themes(today, persist=True, backfilled=True)
    mocks.persist_seeds.assert_not_awaited()
    assert out["seeds"] == 1  # still REPORTED (the replay chains off it) — just not persisted
    assert mocks.persist.await_args.kwargs.get("backfilled") is True


# ── 2026-08-10: forced-tool transport + truncation honesty ───────────────────
# The plain-text JSON transport let sonnet-5 spend ~1000 output tokens/call on
# freeform deliberation around a ~300-token JSON payload (completed 1312 of the
# 1500 ceiling on a FIVE-alert night; the sibling call truncated mid-string).
# The forced tool bounds the response at the schema'd payload by construction.

@pytest.mark.asyncio
async def test_llm_call_is_forced_tool_on_both_paths(monkeypatch):
    d = date(2026, 7, 14)
    cand = [_alert("CLSK", d, ep=61.0), _alert("TSEM", d, ep=55.0)]
    for flag in (False, True):
        captured, mocks = _wire(monkeypatch, flag_on=flag, today_alerts=cand)
        await discover_narrative_themes(d)
        assert captured["tool_choice"] == \
            {"type": "tool", "name": "report_narrative_themes"}, \
            f"lane-2 (flag_on={flag}) reverted to the freeform text transport — " \
            "sonnet-5 deliberation will eat the 1500 ceiling again"
        assert captured["tools"][0]["name"] == "report_narrative_themes"


@pytest.mark.asyncio
async def test_truncated_narrative_response_is_failure_not_zero_themes(monkeypatch):
    """2026-08-10 21:20Z: a max_tokens response died as an 'Unterminated string'
    JSON error — and a luckier cut could have read as a genuine quiet night.
    Truncation must land in the shared fail-open (error recorded, failed audit
    row), never as themes=0."""
    d = date(2026, 7, 14)
    cand = [_alert("CLSK", d, ep=61.0), _alert("TSEM", d, ep=55.0)]
    captured, mocks = _wire(monkeypatch, flag_on=True, today_alerts=cand)

    async def truncated_create(**kwargs):
        captured.update(kwargs)
        return _FakeMsg('{"themes": []}', stop_reason="max_tokens")

    client = SimpleNamespace(messages=SimpleNamespace(create=truncated_create))
    monkeypatch.setattr(theme_engine, "_get_anthropic_client", lambda: client)

    out = await discover_narrative_themes(d)

    assert out["error"] and "TRUNCATED" in out["error"], \
        "a truncated narrative response was read as a genuine empty result"
    assert out["themes"] == 0
    failed = [c for c in mocks.audit.await_args_list
              if c.args and c.args[0] == "narrative_theme_discovery_failed"]
    assert failed, "truncation did not write the failed audit row"
