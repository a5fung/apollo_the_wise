"""#624 small-cap PAPER lane — the 2026-10-10 quality pass (reuse / simplification), pinned.

Every change in the pass is behaviour-preserving, so each test here states the OLD value or
behaviour and proves the new code still produces it:
  - the lane's identity constants (stop switch, account, strategy id) have ONE definition (db.py)
    and the same values the two lane modules used to spell out separately;
  - the order step's refusal page follows the funnel's own constant, not a copy of its string;
  - the judge-result / replay / existing-row SQL built from one definition is byte-identical to
    the statements that were written out by hand;
  - the tiered-name read hands back the same ticker -> latest-date map.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import lowcap_paper_lane as plane
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import lowcap_paper_entry as lpe
from agents.market_intelligence.broker import skip_reasons
from agents.market_intelligence.strategies import adapters
from tests.conftest import make_mock_pool
from tests.test_624_paper_lane import _wire_order_step


# ── identity constants: one definition, the values both modules used to hard-code ─────────


def test_the_lane_identity_constants_keep_their_values_and_have_one_definition():
    assert db.LOWCAP_PAPER_LANE_TOGGLE == "lowcap_paper_lane"
    assert db.LOWCAP_PAPER_LANE_TOGGLE_ENV == "LOWCAP_PAPER_LANE_ENABLED"
    assert db.LOWCAP_PAPER_LANE_ACCOUNT_MODE == "paper"
    assert db.LOWCAP_PAPER_LANE_STRATEGY_ID == "magna53_smallcap"
    # the grading side and the order side read the SAME objects — a stop switch that can only
    # stop half the lane is the failure this prevents
    assert (lpe.TOGGLE, lpe.TOGGLE_ENV) == (plane.TOGGLE, plane.TOGGLE_ENV) \
        == (db.LOWCAP_PAPER_LANE_TOGGLE, db.LOWCAP_PAPER_LANE_TOGGLE_ENV)
    assert lpe.LANE_ACCOUNT_MODE == plane._LANE_BOOK == db.LOWCAP_PAPER_LANE_ACCOUNT_MODE
    assert lpe.STRATEGY_ID == plane.STRATEGY_ID == db.LOWCAP_PAPER_LANE_STRATEGY_ID


def test_the_registry_adapter_is_keyed_and_bound_by_the_strategy_id_constant():
    fn = adapters._ADAPTERS[db.LOWCAP_PAPER_LANE_STRATEGY_ID]
    assert fn.keywords == {"signal_type": db.LOWCAP_PAPER_LANE_STRATEGY_ID}


def test_the_lane_uses_the_one_none_safe_float_coercion():
    assert plane._f is db._f
    assert plane._f("3.5") == 3.5 and plane._f(None) is None and plane._f("x") is None


# ── the refusal page follows the funnel's constant ────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_funnel_account_mode_refusal_pages_the_lane_and_other_blocks_do_not(monkeypatch):
    w = _wire_order_step(monkeypatch)
    w.submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_BLOCKED,
                             "reason": f"{skip_reasons.BLOCK_ACCOUNT_MODE_MISMATCH}: magna53_smallcap "
                                       f"resolves to 'live'"}
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert out[0]["action"] == ep.ACTION_BLOCKED
    assert len(w.pages) == 1 and w.pages[0].startswith("📄 PAPER") and "REFUSED" in w.pages[0]

    w = _wire_order_step(monkeypatch)       # a different block is an audit row, never a page
    w.submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_BLOCKED,
                             "reason": skip_reasons.BLOCK_TICKER_OPEN_POSITION}
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert w.pages == []


@pytest.mark.asyncio
async def test_the_refusal_page_matches_the_funnels_constant_not_a_copy_of_its_text(monkeypatch):
    """If the funnel's reason were ever reworded, the page must follow it (it reads the imported
    constant). MUTATION: put the literal "block:account_mode_mismatch" back — this goes RED."""
    w = _wire_order_step(monkeypatch)
    monkeypatch.setattr(lpe, "BLOCK_ACCOUNT_MODE_MISMATCH", "block:reworded_mismatch")
    w.submit.return_value = {"ticker": "SMLL", "action": ep.ACTION_BLOCKED,
                             "reason": "block:reworded_mismatch: x"}
    await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert len(w.pages) == 1 and "REFUSED" in w.pages[0]
    assert skip_reasons.BLOCK_ACCOUNT_MODE_MISMATCH == "block:account_mode_mismatch"   # the wire value did not move
