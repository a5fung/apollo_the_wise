"""#216 — jsonb double-encoding fix for the seven db.py writers named on the ticket
(plus two more of the same shape found by grep) + a defensive read-tolerance fix.

Same bug class as #177/#179/#287: `db.py::get_pool` registers a jsonb type codec
(`_init_conn` -> `conn.set_type_codec('jsonb', encoder=_json_encoder)`) whose encoder
is plain `json.dumps`, applied AUTOMATICALLY to every jsonb param. A caller that ALSO
`json.dumps()`s the value before binding it to a `$N::jsonb` (or implicitly-jsonb)
param double-encodes — the codec re-serialises the already-serialised string, so the
column lands as `jsonb_typeof='string'` holding literal text like '["EP_HIGH"]'
instead of a real array. Confirmed on prod (2026-08-17): mi_signal_outcomes.detail
2440/2441 rows corrupted, mi_weekly_watchlists.sources 378/378, etc.

Fix: pass the PLAIN dict/list into the ::jsonb param so the codec encodes it exactly
once. Two small helpers do this safely (round-tripping through json.dumps(default=str)
+loads so an embedded date/datetime is stringified before the codec's single encode):
  `_jsonb_param`      — dict-shaped columns (existing #179 convention)
  `_jsonb_list_param` — list-shaped columns (new; extracts the `suggestions_param`
                        idiom already shipped in insert_system_review, #412)

Each test below pins the param TYPE at the conn.execute()/executemany()/fetchval()
call site for one write-path fix — a regression that reintroduces a pre-dumps would
fail these by producing a `str` param instead of a `dict`/`list`.

Mutation proof (2026-08-17): ran this file against `git stash`-ed db.py (i.e. the
pre-#216 code) — every dict/list-typed assertion below failed with the corrupted
`str` type, confirming these tests are not vacuous. Then `git stash pop` restored
the fix and the full file passed again.
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence import db

from tests.conftest import make_mock_pool


def _tx_mock_conn(conn):
    """Wire `conn.transaction()` as an async context manager (MagicMock doesn't
    support __aenter__/__aexit__ out of the box) — needed by insert_weekly_watchlist."""
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)


# ─── _seed_strategies_registry — mi_strategies.promotion_thresholds (dict) ──────


@pytest.mark.asyncio
async def test_seed_strategies_registry_promotion_thresholds_param_is_dict():
    conn = MagicMock()
    conn.executemany = AsyncMock()
    conn.execute = AsyncMock()  # the post-seed deprecation-migration UPDATE

    await db._seed_strategies_registry(conn)

    assert conn.executemany.await_count == 1
    sql, records = conn.executemany.await_args[0]
    assert "promotion_thresholds" in sql
    assert "$8::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    for rec in records:
        pt_param = rec[7]
        assert isinstance(pt_param, dict), (
            f"promotion_thresholds param must be a plain dict (codec encodes exactly "
            f"once) — got {type(pt_param)}. A json.dumps() pre-encode here "
            "double-encodes into jsonb_typeof='string' (#216)."
        )
        assert not isinstance(pt_param, str)
    assert records[0][7]["shadow_to_paper"]["min_closed"] == 30


# ─── upsert_regime — mi_market_regime.breadth_monitor (dict) ────────────────────


@pytest.mark.asyncio
async def test_upsert_regime_breadth_monitor_param_is_dict(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    record = {
        "regime_date": date(2026, 8, 17),
        "regime": "Confirmed Uptrend",
        "breadth_monitor": {"pct_above_40ma": 55.2, "bo_bd_ratio_5d": 1.8},
    }
    await db.upsert_regime(record)

    # 3 ALTER TABLE COLUMN calls + 1 INSERT — the INSERT is last.
    sql, *args = conn.execute.await_args_list[-1].args
    assert "breadth_monitor" in sql
    assert "$18::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    bm_param = args[17]  # 18th bind param, 0-indexed into args (sql already popped)
    assert isinstance(bm_param, dict), (
        f"breadth_monitor param must be a plain dict — got {type(bm_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(bm_param, str)
    assert bm_param["pct_above_40ma"] == 55.2


# ─── settle_anticipation_3b — mi_anticipation_lifecycle.day0_fills (list) ───────


@pytest.mark.asyncio
async def test_settle_anticipation_3b_day0_fills_param_is_list(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    await db.settle_anticipation_3b(
        "TEST", date(2026, 8, 10), realized_r=1.5, fwd_mfe_pct=4.2,
        day0_fills=[{"day_idx": 0, "fraction": 0.5}, {"day_idx": 1, "fraction": 0.5}],
    )

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    assert "day0_fills=$5::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    fills_param = args[4]
    assert isinstance(fills_param, list), (
        f"day0_fills param must be a plain list — got {type(fills_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(fills_param, str)
    assert fills_param[0]["day_idx"] == 0


# ─── upsert_signal_outcome — mi_signal_outcomes.detail (dict) ───────────────────


@pytest.mark.asyncio
async def test_upsert_signal_outcome_detail_param_is_dict(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    await db.upsert_signal_outcome({
        "signal_type": "ep_alert", "signal_date": date(2026, 8, 10), "identifier": "TEST",
        "detail": {"rs_composite": 100.0},
    })

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    assert "$4::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    detail_param = args[3]
    assert isinstance(detail_param, dict), (
        f"detail param must be a plain dict — got {type(detail_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216) — confirmed on prod: "
        'mi_signal_outcomes.detail held the literal string \'{"rs_composite": 100.0}\'.'
    )
    assert not isinstance(detail_param, str)
    assert detail_param["rs_composite"] == 100.0


# ─── update_shadow_trade — mi_orb_shadow_trades.running_closes / .exits (list) ──
# The task's mandatory minimum case: a list written through update_shadow_trade
# reads back as a list, not a string. This is also the site tied to the PROVEN
# downstream breakage (shadow_orb_tracker._row_to_state raising on a corrupted
# string row, freezing 59/79 open shadow trades — separately covered below).


@pytest.mark.asyncio
async def test_update_shadow_trade_running_closes_and_exits_params_are_lists(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    await db.update_shadow_trade(7, {
        "running_closes": [101.0, 102.5, 103.0],
        "exits": [{"time": "2026-08-10T16:00:00", "price": 101.0, "reason": "stop_hit"}],
    })

    assert conn.execute.await_count == 1
    sql, trade_id, running_closes_param, exits_param = conn.execute.await_args[0]
    assert "running_closes = $2::jsonb" in sql
    assert "exits = $3::jsonb" in sql
    assert trade_id == 7

    assert isinstance(running_closes_param, list), (
        f"running_closes param must be a plain list (codec encodes exactly once) — "
        f"got {type(running_closes_param)}. Confirmed on prod: mi_orb_shadow_trades."
        "running_closes held literal string text instead of a real array (#216)."
    )
    assert not isinstance(running_closes_param, str)
    assert running_closes_param == [101.0, 102.5, 103.0]

    assert isinstance(exits_param, list), (
        f"exits param must be a plain list — got {type(exits_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(exits_param, str)
    assert exits_param[0]["reason"] == "stop_hit"


# ─── add_journal_entry — mi_journal_entries.ep_context (list) ───────────────────


@pytest.mark.asyncio
async def test_add_journal_entry_ep_context_param_is_list(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=1)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    row_id = await db.add_journal_entry(
        text="note", regime="Confirmed Uptrend",
        ep_context=[{"ticker": "TEST", "ep_score": 90.0}],
        theme_context="Accelerating: AI Memory",
    )

    assert row_id == 1
    assert conn.fetchval.await_count == 1
    sql, *args = conn.fetchval.await_args[0]
    assert "$3::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    ep_param = args[2]
    assert isinstance(ep_param, list), (
        f"ep_context param must be a plain list — got {type(ep_param)}. "
        "A json.dumps() pre-encode here double-encodes (#216)."
    )
    assert not isinstance(ep_param, str)
    assert ep_param[0]["ticker"] == "TEST"


# ─── insert_weekly_watchlist — mi_weekly_watchlists.sources (list) ──────────────


@pytest.mark.asyncio
async def test_insert_weekly_watchlist_sources_param_is_list(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    _tx_mock_conn(conn)
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    n = await db.insert_weekly_watchlist(date(2026, 8, 14), [
        {"ticker": "TEST", "sources": ["EP_HIGH"], "composite_priority": 1, "reason_chip": "x"},
    ])

    assert n == 1
    assert conn.executemany.await_count == 1
    sql, records = conn.executemany.await_args[0]
    assert "$3::jsonb" in sql, "the ::jsonb cast must stay in the SQL"
    sources_param = records[0][2]
    assert isinstance(sources_param, list), (
        f"sources param must be a plain list — got {type(sources_param)}. Confirmed "
        'on prod: mi_weekly_watchlists.sources held the literal string \'["EP_HIGH"]\' '
        "(#216)."
    )
    assert not isinstance(sources_param, str)
    assert sources_param == ["EP_HIGH"]


# ─── enqueue_pending_allocation — mi_pending_allocations.raw_dimensions (dict) ──
# Not one of the 7 named on the ticket — found via the deliverable-2 repo grep.


@pytest.mark.asyncio
async def test_enqueue_pending_allocation_raw_dimensions_param_is_dict(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=False)  # not a deprecated strategy
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    await db.enqueue_pending_allocation(
        "TEST", date(2026, 8, 17), "magna53", 88.5,
        {"setup_score": 90, "catalyst_score": 80},
    )

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    raw_dim_param = args[4]
    assert isinstance(raw_dim_param, dict), (
        f"raw_dimensions param must be a plain dict — got {type(raw_dim_param)}. "
        "Confirmed on prod: mi_pending_allocations.raw_dimensions 331/331 rows "
        "corrupted (#216)."
    )
    assert not isinstance(raw_dim_param, str)
    assert raw_dim_param["setup_score"] == 90


# ─── upsert_htf_management_shadow — mi_htf_management_shadow.events (list) ─────
# Not one of the 7 named on the ticket — found via the deliverable-2 repo grep.


@pytest.mark.asyncio
async def test_upsert_htf_management_shadow_events_param_is_list(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    await db.upsert_htf_management_shadow(
        1, "TEST", date(2026, 6, 1),
        entry_price=10.0, initial_stop=9.0, initial_shares=100.0,
        scale_fraction=0.5, trail_mode="sma", status="open",
        remaining_shares=100.0, partial_taken=False, breakeven_active=False,
        events=[{"date": "2026-06-01", "type": "scale_out"}],
        realized_r=None, last_bar_date=None,
    )

    assert conn.execute.await_count == 1
    sql, *args = conn.execute.await_args[0]
    events_param = args[12]
    assert isinstance(events_param, list), (
        f"events param must be a plain list — got {type(events_param)}. Confirmed "
        "on prod: mi_htf_management_shadow.events 4/4 rows corrupted (#216)."
    )
    assert not isinstance(events_param, str)
    assert events_param[0]["type"] == "scale_out"


# ─── shadow_orb_tracker._row_to_state — defensive READ tolerance ───────────────
# In scope per #216's HARD LIMITS: shadow_orb_tracker.py may only gain READ
# tolerance for a legacy corrupted (string) row, not be restructured. Before this
# fix, a corrupted running_closes string ("[101.0, ...]") made
# `[float(x) for x in row["running_closes"]]` iterate CHARACTERS and raise on
# float('['), which update_shadow_positions' per-row except silently swallowed —
# the proven cause of 59/79 mi_orb_shadow_trades rows stuck 'open' forever.


def test_row_to_state_survives_legacy_string_jsonb_columns():
    from agents.market_intelligence.broker.shadow_orb_tracker import _row_to_state

    legacy_row = {
        "alert_date": date(2026, 4, 30),
        "remaining_shares": 60,
        "entry_price": 100.0,
        "hard_stop": 95.0,
        "partial_taken": True,
        "breakeven_active": False,
        # double-encoded #216-shaped corruption: real JSON text, not a native array
        "exits": '[{"price": 101.0, "reason": "partial"}]',
        "running_closes": "[101.0, 102.0, 103.0]",
    }

    state = _row_to_state(legacy_row)  # must NOT raise

    assert state["exits"] == [{"price": 101.0, "reason": "partial"}]
    assert state["running_closes"] == [101.0, 102.0, 103.0]


def test_row_to_state_still_handles_native_list_rows():
    """A correctly-written (post-fix) row must keep working unchanged."""
    from agents.market_intelligence.broker.shadow_orb_tracker import _row_to_state

    clean_row = {
        "alert_date": date(2026, 8, 17),
        "remaining_shares": 60,
        "entry_price": 100.0,
        "hard_stop": 95.0,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [110.0, 111.0],
    }

    state = _row_to_state(clean_row)

    assert state["exits"] == []
    assert state["running_closes"] == [110.0, 111.0]
