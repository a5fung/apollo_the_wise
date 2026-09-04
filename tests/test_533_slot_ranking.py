"""#533 (2026-08-30, OPERATOR-SIGNED) — within-day slot ranking: behaviour + wiring pins.

`process_new_alerts_live`'s DISTINCT ON (ticker) query left the ACROSS-ticker order
alphabetical — ticker name decided which HIGH alerts got the five position slots.
Operator ruling: "switch to RS rank, but observe going forward if it deteriorates or
other ranking starts to do better." Acting order: prior-day rs_composite DESC,
ep_score DESC tiebreak, ticker ASC. ONE revert flag (`ep_slot_rank_rs` /
EP_SLOT_RANK_RS_ENABLED, default ON): OFF must restore the legacy query's own order
EXACTLY.

Pins here:
  1. the legacy SELECT is BYTE-IDENTICAL to the pre-change inline query (it is the
     revert target — with the flag OFF its row order IS the acting order), and the
     per-ticker dedup (`DISTINCT ON` + `ORDER BY ticker, ep_score DESC`) is intact;
  2. the acting sort key: RS DESC -> ep_score DESC -> ticker ASC, total order,
     input-order independent, non-mutating, and a PERMUTATION of the board (ranking
     can never add or drop a name);
  3. the missing-RS-row policy: ranked after every RS-scored name, NEVER dropped;
  4. the flag + fail direction end-to-end: ON -> RS order acts; OFF -> legacy order
     acts; any ranking-block error -> legacy order acts + a slot_rank_fallback
     audit row (never a dead selection);
  5. the watch (mi_ep_slot_rank_shadow): raw inputs + all six ranks (rank_vol_pct
     added 2026-09-04, #624, records only) + acting_key, written on BOTH toggle
     sides (a revert must not kill the watch), writer fail-open (returns 0,
     never raises), SILENT.
"""
from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.ep_slot_rank_shadow import (
    SLOT_RANK_KEYS,
    compute_slot_rank_rows,
    fetch_theme_stage_by_ticker,
    rank_board_by_rs,
    slot_rank_key,
    snapshot_slot_rank_board,
)
from tests.conftest import make_mock_pool


# ── Part 1: the legacy query is the revert target — byte-identical, dedup intact ──


def test_legacy_select_is_byte_identical_to_the_pre_533_query():
    """The exact string that was inline in process_new_alerts_live before #533.
    With the flag OFF this query's own row order IS the acting order, so any
    edit here silently moves the revert target."""
    assert lt._HIGH_ALERT_SELECT_SQL == """
            SELECT DISTINCT ON (ticker)
                   ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date = $1 AND score_tier = 'HIGH'
            ORDER BY ticker, ep_score DESC
        """


def test_per_ticker_dedup_clause_is_untouched():
    """DISTINCT ON (ticker) + ORDER BY ticker, ep_score DESC = the max-ep_score
    row survives per ticker. #533 moved the ACROSS-ticker ordering to Python
    precisely so this SQL never changes."""
    sql = lt._HIGH_ALERT_SELECT_SQL
    assert "DISTINCT ON (ticker)" in sql
    assert "ORDER BY ticker, ep_score DESC" in sql


def test_the_function_fetches_via_the_pinned_constant():
    src = inspect.getsource(lt.process_new_alerts_live)
    assert "conn.fetch(_HIGH_ALERT_SELECT_SQL, today)" in src
    assert "SELECT DISTINCT ON" not in src, "no inline copy may shadow the pinned constant"


# ── Part 2: the acting sort key ───────────────────────────────────────────────


def _alert(t, score=70.0, gap=12.0, vol_pct=90.0):
    return {"ticker": t, "alert_date": date(2026, 8, 28), "gap_pct": gap,
            "rel_volume": 5.0, "ep_score": score, "score_tier": "HIGH",
            "catalyst": "earnings", "catalyst_quality": "strong",
            "vol_percentile": vol_pct}


def _rs(comp, rank=100, adv=2e6, close=50.0):
    return {"rs_composite": comp, "rs_rank": rank, "adv_20": adv, "close": close}


def test_rs_desc_is_the_primary_axis():
    """The 08-04 worked case: RS puts LIFE (98) and ZBRA (92) ahead of BTDR (24)
    — the live path gave BTDR a slot alphabetically and cap-blocked ZBRA."""
    board = [_alert("BTDR", 85), _alert("LIFE", 70), _alert("ZBRA", 75)]
    ranks = rank_board_by_rs(board, {
        "BTDR": _rs(24), "LIFE": _rs(98), "ZBRA": _rs(92)})
    assert ranks == {"LIFE": 1, "ZBRA": 2, "BTDR": 3}


def test_ep_score_breaks_rs_ties_then_ticker():
    board = [_alert("BBB", 70), _alert("AAA", 70), _alert("CCC", 80)]
    ranks = rank_board_by_rs(board, {t: _rs(90) for t in ("AAA", "BBB", "CCC")})
    assert ranks == {"CCC": 1, "AAA": 2, "BBB": 3}  # score first, then ticker asc


def test_input_order_never_decides():
    board = [_alert(t) for t in ("EEE", "AAA", "CCC", "BBB", "DDD")]
    rs = {"AAA": _rs(50), "BBB": _rs(60), "CCC": _rs(50), "DDD": _rs(60),
          "EEE": _rs(70)}
    assert rank_board_by_rs(board, rs) == rank_board_by_rs(list(reversed(board)), rs)


def test_ranking_is_a_permutation_never_an_admission_change():
    """Ranking reorders the board; it must never add or drop a name (P1 — the
    selection population is the entry path's, not this sort's, to change)."""
    board = [_alert(t) for t in ("AA", "BB", "CC", "DD")]
    ranks = rank_board_by_rs(board, {"AA": _rs(90)})   # three names have no RS row
    assert sorted(ranks) == ["AA", "BB", "CC", "DD"]
    assert sorted(ranks.values()) == [1, 2, 3, 4]


def test_ranking_does_not_mutate_the_board():
    board = [_alert(t) for t in ("ZZ", "AA")]
    before = [a["ticker"] for a in board]
    rank_board_by_rs(board, {"AA": _rs(90), "ZZ": _rs(10)})
    assert [a["ticker"] for a in board] == before


# ── Part 3: the missing-RS-row policy (deliberate, not accidental) ────────────


def test_no_rs_row_ranks_after_every_scored_name_and_is_never_dropped():
    """MUTATION TARGET: the `0 if has_rs else 1` group term in slot_rank_key.
    Removing it lets a missing-RS name (treated as RS 0.0) tie into the scored
    ordering; dropping the name entirely would shrink the permutation (caught
    above too). Policy: no evidence of relative strength buys no priority, but
    the name stays on the board for whatever slots remain."""
    board = [_alert("NORS", 99), _alert("LOWR", 60), _alert("HIGH", 70)]
    ranks = rank_board_by_rs(board, {"LOWR": _rs(5), "HIGH": _rs(95)})
    assert ranks == {"HIGH": 1, "LOWR": 2, "NORS": 3}
    # among several missing-RS names: ep_score desc, then ticker
    board2 = [_alert("BNO", 50), _alert("ANO", 50), _alert("CNO", 80),
              _alert("SCOR", 10)]
    ranks2 = rank_board_by_rs(board2, {"SCOR": _rs(1)})
    assert ranks2 == {"SCOR": 1, "CNO": 2, "ANO": 3, "BNO": 4}


def test_none_rs_composite_on_an_existing_row_is_missing_too():
    key_none = slot_rank_key("AAA", 70.0, None)
    key_zero = slot_rank_key("AAA", 70.0, 0.0)
    assert key_none > key_zero, "a NULL rs_composite must sort as missing, after a real 0"


# ── Part 4: flag + fail direction, end to end ─────────────────────────────────


_TODAY = date(2026, 8, 28)
_SCORE_DATE = date(2026, 8, 27)


def _dispatching_fetch(alerts_rows, rs_rows):
    """conn.fetch stand-in routing on SQL text: the alerts board, the #554
    completeness counts, the RS fetch, and the themes fetch."""
    async def _fetch(sql, *args):
        if "FROM mi_ep_alerts" in sql:
            return list(alerts_rows)
        if "COUNT(*)" in sql and "mi_stock_scores" in sql:
            return [{"score_date": _SCORE_DATE, "n": 2400}]
        if "FROM mi_stock_scores" in sql:
            return list(rs_rows)
        if "mi_themes" in sql:
            return []
        raise AssertionError(f"unexpected SQL in test: {sql[:80]}")
    return _fetch


async def _drive(monkeypatch, *, toggle, alerts_rows, rs_rows,
                 rs_fetch_raises=False):
    """Run process_new_alerts_live with everything past selection stubbed.
    Returns (board_order, audit_events, insert_calls)."""
    pool, conn = make_mock_pool()
    fetch = _dispatching_fetch(alerts_rows, rs_rows)
    if rs_fetch_raises:
        _inner = fetch

        async def fetch(sql, *args):  # noqa: F811 — deliberate wrap
            if "COUNT(*)" in sql and "mi_stock_scores" in sql:
                raise RuntimeError("rs backend down")
            return await _inner(sql, *args)

    conn.fetch = AsyncMock(side_effect=fetch)
    conn.fetchrow = AsyncMock(return_value=None)   # regime lookup
    conn.fetchval = AsyncMock(return_value=False)  # no pre-existing trade rows
    conn.executemany = AsyncMock(return_value=None)
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(lt, "get_runtime_toggle", AsyncMock(return_value=toggle))
    monkeypatch.setattr(lt, "check_filters", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(lt, "compute_atr_14", AsyncMock(return_value=(1.0, 2.0)))
    monkeypatch.setattr(lt, "send_telegram_message", AsyncMock(return_value=True))

    audit_events: list[tuple] = []

    async def _audit(event, msg, *a, **k):
        audit_events.append((event, msg))

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "log_audit_event", _audit)

    async def _fake_submit(*, alert_context, **_kw):
        return {"ticker": alert_context["ticker"], "action": lt.ACTION_SKIPPED,
                "reason": "setup:test"}

    monkeypatch.setattr(lt, "submit_trade_entry", _fake_submit)
    await lt.process_new_alerts_live(today=_TODAY)

    triggered = [m for e, m in audit_events if e == "orb_triggered"]
    assert len(triggered) == 1
    board_order = [t.strip("'\" ") for t in
                   triggered[0].split("[")[-1].rstrip("]").split(",")]
    inserts = [c for c in conn.executemany.await_args_list
               if "mi_ep_slot_rank_shadow" in c.args[0]]
    return board_order, audit_events, inserts


_BOARD_ROWS = [_alert("BTDR", 85), _alert("LIFE", 70), _alert("ZBRA", 75)]
_RS_ROWS = [
    {"ticker": "BTDR", "rs_composite": 24.0, "rs_rank": 1969, "adv_20": 1e6, "close": 10.0},
    {"ticker": "LIFE", "rs_composite": 98.0, "rs_rank": 50, "adv_20": 5e5, "close": 4.0},
    {"ticker": "ZBRA", "rs_composite": 92.0, "rs_rank": 200, "adv_20": 2e6, "close": 300.0},
]


@pytest.mark.asyncio
async def test_toggle_on_rs_order_acts(monkeypatch):
    board, _events, inserts = await _drive(
        monkeypatch, toggle=True, alerts_rows=_BOARD_ROWS, rs_rows=_RS_ROWS)
    assert board == ["LIFE", "ZBRA", "BTDR"]
    # the watch stamped the acting side
    rows = inserts[0].args[1]
    assert all(r[-1] == "rs" for r in rows)


@pytest.mark.asyncio
async def test_toggle_off_is_the_legacy_order_exactly(monkeypatch):
    """OFF = the legacy query's own row order acts, byte-identical behaviour —
    the board is processed exactly as fetched (alphabetical here, because that
    is what the legacy ORDER BY leaves behind across tickers)."""
    board, _events, inserts = await _drive(
        monkeypatch, toggle=False, alerts_rows=_BOARD_ROWS, rs_rows=_RS_ROWS)
    assert board == ["BTDR", "LIFE", "ZBRA"]
    # the watch still records on the OFF side — a revert must not kill it
    assert inserts, "shadow write must happen on BOTH toggle sides"
    rows = inserts[0].args[1]
    assert all(r[-1] == "legacy_alpha" for r in rows)


@pytest.mark.asyncio
async def test_ranking_error_falls_back_to_legacy_order_loudly(monkeypatch):
    """MUTATION TARGET: the try/except around the ranking block. Fail direction
    is the LEGACY order acting + a durable slot_rank_fallback audit row — never
    a dead selection, never a silently-empty board."""
    board, events, _inserts = await _drive(
        monkeypatch, toggle=True, alerts_rows=_BOARD_ROWS, rs_rows=_RS_ROWS,
        rs_fetch_raises=True)
    assert board == ["BTDR", "LIFE", "ZBRA"]
    assert any(e == "slot_rank_fallback" for e, _m in events)


@pytest.mark.asyncio
async def test_missing_rs_name_is_processed_last_not_dropped(monkeypatch):
    board, _events, _ins = await _drive(
        monkeypatch, toggle=True,
        alerts_rows=_BOARD_ROWS + [_alert("AAAA", 99)],   # alphabetically first, no RS row
        rs_rows=_RS_ROWS)
    assert board == ["LIFE", "ZBRA", "BTDR", "AAAA"]


def test_the_flag_guards_the_only_reorder():
    """test_347 idiom: a refactor cannot drop the flip or grow a second one."""
    src = inspect.getsource(lt.process_new_alerts_live)
    assert ('"ep_slot_rank_rs", "EP_SLOT_RANK_RS_ENABLED", default=True)' in src), \
        "one instant-revert flag, default ON"
    assert "if _slot_rank_live and _rs_score_date is not None:" in src, \
        "no complete RS date -> the legacy order acts even with the flag ON"
    assert src.count("alerts = _rs_order") == 1, "exactly one acting re-order"


# ── Part 5: the watch record ──────────────────────────────────────────────────


def test_rows_carry_raw_inputs_all_six_ranks_and_the_acting_key():
    board = [_alert("BTDR", 85, gap=30.0, vol_pct=95.0),
             _alert("LIFE", 70, gap=40.0, vol_pct=60.0)]
    rs = {"BTDR": _rs(24, 1969, 1e6, 10.0), "LIFE": _rs(98, 50, 5e5, 4.0)}
    rows = compute_slot_rank_rows(
        board, rs, _SCORE_DATE, {"LIFE": "Accelerating"},
        acting_key="rs", trigger="cron_9_31")
    assert SLOT_RANK_KEYS == (
        "rank_rs", "rank_ep_score", "rank_composite", "rank_adv", "rank_alpha",
        "rank_vol_pct")
    by_t = {r["ticker"]: r for r in rows}
    life, btdr = by_t["LIFE"], by_t["BTDR"]
    # raw inputs present; computed points/composites ABSENT (#583 class)
    for r in rows:
        for k in ("ep_score", "gap_pct", "rs_composite", "rs_rank",
                  "rs_score_date", "adv_20", "score_close", "theme_stage",
                  "vol_percentile"):
            assert k in r
        assert "composite" not in r and "points" not in r
        assert r["acting_key"] == "rs" and r["trigger"] == "cron_9_31"
        assert r["board_n"] == 2
    assert life["rank_rs"] == 1 and btdr["rank_rs"] == 2
    assert btdr["rank_ep_score"] == 1                       # 85 > 70
    assert life["rank_composite"] == 1                      # 70+15+9.8 > 85+2.4
    assert btdr["rank_adv"] == 1                            # $10M > $2M ADV$
    assert btdr["rank_alpha"] == 1                          # B < L — the control
    assert btdr["rank_vol_pct"] == 1                        # 95 > 60
    assert life["theme_stage"] == "Accelerating" and btdr["theme_stage"] is None
    assert life["rs_score_date"] == _SCORE_DATE
    assert btdr["vol_percentile"] == 95.0 and life["vol_percentile"] == 60.0


def test_missing_vol_percentile_ranks_after_every_scored_name_and_is_never_dropped():
    """Mirrors the RS missing-value policy (Part 3): no vol_percentile reading
    ranks AFTER every name that has one, never drops the name, never crashes."""
    board = [_alert("NOVOL", 99, vol_pct=None),
             _alert("LOWV", 60, vol_pct=20.0),
             _alert("HIGHV", 70, vol_pct=90.0)]
    rows = compute_slot_rank_rows(
        board, {}, None, {}, acting_key="rs", trigger="cron")
    by_t = {r["ticker"]: r for r in rows}
    assert by_t["HIGHV"]["rank_vol_pct"] == 1
    assert by_t["LOWV"]["rank_vol_pct"] == 2
    assert by_t["NOVOL"]["rank_vol_pct"] == 3
    assert by_t["NOVOL"]["vol_percentile"] is None
    assert sorted(r["rank_vol_pct"] for r in rows) == [1, 2, 3]  # a permutation


@pytest.mark.asyncio
async def test_writer_never_raises_and_returns_zero_on_failure():
    pool = MagicMock()
    pool.acquire = MagicMock(side_effect=RuntimeError("pool down"))
    n = await snapshot_slot_rank_board(
        pool, [_alert("AAA")], {}, None,
        acting_key="rs", trigger="cron", alert_date=_TODAY)
    assert n == 0


@pytest.mark.asyncio
async def test_empty_board_writes_nothing():
    pool = MagicMock()
    n = await snapshot_slot_rank_board(
        pool, [], {}, None, acting_key="rs", trigger="cron", alert_date=_TODAY)
    assert n == 0
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_theme_fetch_failure_degrades_to_no_themes_never_raises():
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=RuntimeError("themes down"))
    assert await fetch_theme_stage_by_ticker(pool, ["AAA"], _TODAY) == {}


@pytest.mark.asyncio
async def test_strongest_stage_wins_per_ticker():
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"tk": "AAA", "stage": "Nascent"},
        {"tk": "AAA", "stage": "Accelerating"},
        {"tk": "AAA", "stage": "Mainstream"},
    ])
    stages = await fetch_theme_stage_by_ticker(pool, ["AAA"], _TODAY)
    assert stages == {"AAA": "Accelerating"}
