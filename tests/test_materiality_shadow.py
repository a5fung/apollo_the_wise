"""#189 / ADR 0010 — materiality shadow: the shared judgment layer + the
would-be-fire_status mechanism the offline writer relies on.

Two things are locked here:
  1. assess_materiality policy — RULE-FIRST (free), Sonnet only on rule-abstain,
     and FAIL-OPEN (None tier on no-client / LLM error → is_material(None)=True).
  2. The shadow's would-be fire_status trick — calling the UNCHANGED hot-path
     _compute_fire_status with catalyst_type forced non-fire when immaterial
     reproduces the staged ADR 0010 demotion without editing the firing path.
"""
import asyncio

from agents.market_intelligence.catalyst_materiality import (
    assess_materiality, is_material, format_market_cap, judge_materiality_llm,
)
from agents.market_intelligence.ep_detector import _compute_fire_status


# ── fake Anthropic async client ──────────────────────────────────────────────
class _FakeResp:
    def __init__(self, text):
        self.content = [type("C", (), {"text": text})()]


class _FakeMessages:
    def __init__(self, text="", raise_exc=False):
        self.text, self.raise_exc, self.calls = text, raise_exc, 0

    async def create(self, **kw):
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("boom")
        return _FakeResp(self.text)


class _FakeClient:
    def __init__(self, text="", raise_exc=False):
        self.messages = _FakeMessages(text, raise_exc)


def _run(coro):
    return asyncio.run(coro)


# ── format_market_cap ────────────────────────────────────────────────────────
def test_format_market_cap():
    assert format_market_cap(2.5e9) == "$2.5B"
    assert format_market_cap(4.8e8) == "$480M"
    assert format_market_cap(None) == "unknown"
    assert format_market_cap("nan-ish") == "unknown"


# ── assess_materiality: rule-first ───────────────────────────────────────────
def test_rule_first_skips_llm_when_deal_and_cap_known():
    client = _FakeClient(text='{"tier":"immaterial"}')
    # $500M deal vs $1B cap = 50% → transformative, deterministically, no LLM.
    tier, source = _run(assess_materiality(
        client, company="X", sector="Tech", market_cap=1e9,
        catalyst="Company announces $500 million acquisition", analysis=""))
    assert tier == "transformative"
    assert source == "rule"
    assert client.messages.calls == 0  # rules answered → never paid for Sonnet


def test_rule_first_handles_string_market_cap():
    # FMP can return marketCap as a STRING — a deal catalyst must NOT TypeError on
    # the rule path (the #173-class silent-skip). $500M deal vs "1000000000" cap.
    client = _FakeClient(text='{"tier":"immaterial"}')
    tier, source = _run(assess_materiality(
        client, company="X", sector="Tech", market_cap="1000000000",
        catalyst="Company announces $500 million acquisition", analysis=""))
    assert tier == "transformative"
    assert source == "rule"
    assert client.messages.calls == 0


def test_garbage_market_cap_string_falls_through_to_llm():
    # Unparseable cap → coerced to None → rules abstain → Sonnet judges (no raise).
    client = _FakeClient(text='{"tier":"minor"}')
    tier, source = _run(assess_materiality(
        client, company="X", sector="Tech", market_cap="N/A",
        catalyst="Company announces $500 million acquisition", analysis=""))
    assert tier == "minor"
    assert source == "llm"


def test_rule_first_immaterial_small_deal_big_cap():
    client = _FakeClient(text='{"tier":"transformative"}')
    # $270M @ $600B ≈ 0.045% → immaterial by rule; LLM not consulted.
    tier, source = _run(assess_materiality(
        client, company="Mega", sector="Tech", market_cap=6e11,
        catalyst="$270 million contract win", analysis=""))
    assert tier == "immaterial"
    assert source == "rule"
    assert client.messages.calls == 0


# ── assess_materiality: LLM fallback on rule-abstain ─────────────────────────
def test_llm_fallback_when_rules_abstain():
    client = _FakeClient(text='{"tier":"material","rationale":"meaningful beat"}')
    # Earnings/sales catalyst — no parseable deal value → rules abstain → Sonnet.
    tier, source = _run(assess_materiality(
        client, company="Y", sector="Tech", market_cap=2e9,
        catalyst="Q1 revenue beat, guidance raised", analysis="strong quarter"))
    assert tier == "material"
    assert source == "llm"
    assert client.messages.calls == 1


# ── assess_materiality: FAIL-OPEN ────────────────────────────────────────────
def test_fail_open_no_client():
    tier, source = _run(assess_materiality(
        None, company="Y", sector="Tech", market_cap=2e9,
        catalyst="Q1 revenue beat", analysis=""))
    assert tier is None
    assert source == "abstain"
    assert is_material(tier) is True  # missing signal NEVER demotes


def test_fail_open_on_llm_error():
    client = _FakeClient(raise_exc=True)
    tier, source = _run(assess_materiality(
        client, company="Y", sector="Tech", market_cap=2e9,
        catalyst="Q1 revenue beat", analysis=""))
    assert tier is None
    assert source == "abstain"
    assert is_material(tier) is True


def test_judge_parses_fenced_json():
    client = _FakeClient(text='```json\n{"tier":"minor","rationale":"small"}\n```')
    tier = _run(judge_materiality_llm(
        client, company="Y", sector="Tech", market_cap=2e9,
        catalyst="small deal", analysis=""))
    assert tier == "minor"


def test_judge_returns_none_on_garbage():
    client = _FakeClient(text="not json at all")
    tier = _run(judge_materiality_llm(
        client, company="Y", sector="Tech", market_cap=2e9,
        catalyst="x", analysis=""))
    assert tier is None


# ── would-be fire_status trick (the shadow writer's mechanism) ───────────────
def _would_status(tier, catalyst_type, catalyst_text):
    """Reproduce materiality_shadow._shadow_one's would-be computation: force the
    catalyst_type non-fire when the tier is confirmed immaterial, then call the
    UNCHANGED _compute_fire_status. Catalyst-only fire ⇒ in_theme/in_narrative False."""
    effective = catalyst_type if is_material(tier) else "unknown"
    return _compute_fire_status(
        in_theme=False, in_narrative=False, catalyst_quality="game_changer",
        catalyst_text=catalyst_text, catalyst_type=effective)[0]


def test_material_keeps_fire_seen():
    # game_changer sales_accel, material → axis stays lit → fire_seen.
    assert _would_status("material", "sales_acceleration",
                         "Q1 revenue +40%, raised guide") == "fire_seen"
    # fail-open: None tier (judgment gap) is material → never demotes.
    assert _would_status(None, "sales_acceleration",
                         "Q1 revenue +40%, raised guide") == "fire_seen"


def test_immaterial_demotes_catalyst_only_fire():
    # Confirmed immaterial → catalyst axis dark → not fire_seen. With substantive
    # catalyst text the discovery bucket is no_fire_confirmed (had inputs).
    assert _would_status(
        "immaterial", "sales_acceleration",
        "A long substantive catalyst description well over forty characters here"
    ) == "no_fire_confirmed"
    # Thin/empty text → real_unknown (no inputs to judge).
    assert _would_status("immaterial", "sales_acceleration", "") == "real_unknown"
