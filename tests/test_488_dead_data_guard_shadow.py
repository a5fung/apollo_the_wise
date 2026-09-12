"""#488 dead-data-guard SHADOW — authoritative halts vs the inferred RMV dead-floor.

Built under #386 (closed 2026-07-19; design audit only), re-applied onto main 2026-09-12 under
the live-path tracking task #488 from branch ba7533b (~1,500 commits behind main at merge
time) — `_compute_rmv`/`_ntr`/`_wilder_tr` confirmed byte-identical to the branch version
before merge (THE LINE: no live-guard behavior change).

Pins the shadow build's three contracts (SHADOW-ONLY — the live guard is untouched):
  1. `flag_detector.rmv_none_reason` is an EXACT branch mirror of `_compute_rmv`:
     reason-is-None ⟺ rmv-is-not-None on every battery series (the drift pin), and each
     degenerate branch classifies as designed (dead_floor = the halt/frozen-feed inference
     the shadow measures);
  2. `broker.halt_status_shadow` capture is INERT with the env flag off (the prod default),
     registers the "*" statuses handler with it on, and the event writer maps both the
     TradingStatus-object and raw-dict shapes and NEVER raises into the stream loop;
  3. `dead_data_guard_shadow.run_dead_data_guard_shadow` writes the correct 2×2 rows
     (inferred × authoritative, agree, halt_codes, in_flag_universe) and NEVER raises —
     a shadow failure must not fail the flag-scan job it piggybacks on.
"""
from __future__ import annotations

import asyncio
import sys
import types
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from agents.market_intelligence.flag_detector import _compute_rmv, rmv_none_reason


def _run(coro):
    return asyncio.run(coro)


def _stub_alpaca_data_live(monkeypatch, stream_instance):
    """tests/conftest.py stubs `alpaca`/`alpaca.data`/`alpaca.data.enums` etc as
    `_MockModule`s (a `sys.modules.setdefault`, so it wins even when alpaca-py IS
    installed — nothing in this process has imported the real `alpaca` package before
    conftest runs). `alpaca.data.live` is NOT in that stub list, and a `_MockModule`
    parent has no real `__path__` for the import system to find a submodule under —
    so a bare `from alpaca.data.live import StockDataStream` (what bar_stream.py does
    inside start_bar_stream) raises ModuleNotFoundError in the test process even
    though the real package IS installed. Register a throwaway module for the one test
    that needs it, scoped by monkeypatch (reverted automatically), rather than
    widening the shared conftest.py stub list for a single call site."""
    stub = types.ModuleType("alpaca.data.live")
    stub.StockDataStream = MagicMock(return_value=stream_instance)
    monkeypatch.setitem(sys.modules, "alpaca.data.live", stub)
    return stub.StockDataStream


# ─── Bar builders (keys per mi_daily_closes / get_recent_daily_history) ─────────────────

def _bar(close, high, low, day):
    return {"trade_date": date(2026, 1, 1), "open_price": close, "high_price": high,
            "low_price": low, "close": close, "volume": 1e6, "_d": day}


def _healthy(n=20, spread=0.02):
    """Rising closes with a real (~2%) daily range — rmv computes to a value."""
    return [_bar(50 + i * 0.3, (50 + i * 0.3) * (1 + spread), (50 + i * 0.3) * (1 - spread), i)
            for i in range(n)]


def _dead_tail(n=20, dead=3):
    """Healthy base, then `dead` flat bars pinned at the prior close — NTR 0 (the
    halt / frozen-feed shape the floor was built for)."""
    rows = _healthy(n - dead)
    px = rows[-1]["close"]
    for i in range(dead):
        rows.append(_bar(px, px, px, n - dead + i))
    return rows


def _degenerate(n=20):
    """A non-positive close inside the lookback window."""
    rows = _healthy(n)
    rows[-2]["close"] = 0.0
    return rows


def _all_flat(n=20):
    px = 50.0
    return [_bar(px, px, px, i) for i in range(n)]


# ─── 1. rmv_none_reason ⟷ _compute_rmv parity (the drift pin) ──────────────────────────

def test_none_reason_parity_battery():
    """RED-PROVED 2026-09-12: flipping the dead_floor comparison in rmv_none_reason
    (`<` -> `>` against _RMV_DEAD_NTR_FLOOR) broke this on the "healthy" series
    (rmv=54.5, reason='dead_floor' — a parity drift); reverted."""
    battery = {
        "healthy": _healthy(20),
        "short": _healthy(10),
        "dead_tail": _dead_tail(20),
        "degenerate": _degenerate(20),
        "all_flat": _all_flat(20),
        "healthy_long": _healthy(40),
        "dead_tail_long": _dead_tail(40),
    }
    for name, rows in battery.items():
        for lookback in (5, 15):
            idx = len(rows) - 1
            rmv = _compute_rmv(rows, idx, lookback=lookback)
            reason = rmv_none_reason(rows, idx, lookback=lookback)
            assert (reason is None) == (rmv is not None), (
                f"parity drift on {name} lookback={lookback}: rmv={rmv} reason={reason}"
            )


def test_none_reason_branch_classification():
    """RED-PROVED 2026-09-12: same dead_floor comparison flip as above (`<` -> `>`) made
    the `_healthy(20)` assertion (should be None) fail with 'dead_floor'; reverted."""
    assert rmv_none_reason(_healthy(20), 19) is None
    assert rmv_none_reason(_healthy(10), 9) == "insufficient_history"
    assert rmv_none_reason(_healthy(20), 19, current_window=0) == "insufficient_history"
    assert rmv_none_reason(_dead_tail(20), 19) == "dead_floor"
    assert rmv_none_reason(_degenerate(20), 19) == "degenerate_close"
    # every-NTR-zero hits the dead-floor branch FIRST (mirrors _compute_rmv's order —
    # zero_base stays defensive/unreachable, exactly like the original)
    assert rmv_none_reason(_all_flat(20), 19) == "dead_floor"


def test_none_reason_does_not_mutate_live_guard():
    """The shadow helper must not change what _compute_rmv returns (THE LINE).

    RED-PROVED 2026-09-12: disabling the LIVE `_compute_rmv`'s dead-floor branch itself
    (its `if max(...) < _RMV_DEAD_NTR_FLOOR` forced to `if False`) turned the dead-tail
    assertion (expected None) into 0.0; reverted."""
    rows = _dead_tail(20)
    assert _compute_rmv(rows, 19, lookback=15) is None
    healthy = _healthy(20)
    v = _compute_rmv(healthy, 19, lookback=15)
    assert v is not None and 0.0 <= v <= 100.0


# ─── 2. capture: env-gated registration + event writer ─────────────────────────────────

def test_capture_flag_off_is_inert(monkeypatch):
    """RED-PROVED 2026-09-12: forcing `maybe_register_status_capture`'s
    `if not capture_enabled(): return False` guard to `if False` (i.e. always fall
    through to registration) made this fail (`True is False`); reverted."""
    from agents.market_intelligence.broker import halt_status_shadow as hss
    monkeypatch.delenv("HALT_STATUS_CAPTURE_ENABLED", raising=False)
    stream = MagicMock()
    assert hss.maybe_register_status_capture(stream) is False
    stream.subscribe_trading_statuses.assert_not_called()

    monkeypatch.setenv("HALT_STATUS_CAPTURE_ENABLED", "false")
    assert hss.maybe_register_status_capture(stream) is False
    stream.subscribe_trading_statuses.assert_not_called()


def test_capture_flag_on_registers_wildcard(monkeypatch):
    """RED-PROVED 2026-09-12: changing the subscribe call's symbol arg from "*" to
    "ALL" made the assert_called_once_with mock-comparison fail; reverted."""
    from agents.market_intelligence.broker import halt_status_shadow as hss
    monkeypatch.setenv("HALT_STATUS_CAPTURE_ENABLED", "true")
    stream = MagicMock()
    assert hss.maybe_register_status_capture(stream) is True
    stream.subscribe_trading_statuses.assert_called_once_with(
        hss._handle_trading_status, "*")


def test_handler_writes_event_object_shape(monkeypatch):
    """RED-PROVED 2026-09-12: swapping the status_code/reason_code field mapping in
    `_handle_trading_status` made this fail ('T12' != 'H'); reverted."""
    from agents.market_intelligence.broker import halt_status_shadow as hss
    from agents.market_intelligence import db, execution_client
    ins = AsyncMock()
    monkeypatch.setattr(db, "insert_halt_status_event", ins)
    monkeypatch.setattr(execution_client, "get_data_feed_name", lambda: "iex")
    ts = datetime(2026, 7, 17, 14, 30, tzinfo=timezone.utc)
    status = SimpleNamespace(symbol="HALTY", timestamp=ts, status_code="H",
                             status_message="Halted", reason_code="T12",
                             reason_message="SEC suspension", tape="C")
    _run(hss._handle_trading_status(status))
    ins.assert_awaited_once()
    kw = ins.await_args.kwargs
    assert kw["ticker"] == "HALTY" and kw["event_ts"] == ts
    assert kw["status_code"] == "H" and kw["reason_code"] == "T12"
    assert kw["feed"] == "iex"


def test_handler_maps_raw_dict_shape(monkeypatch):
    """RED-PROVED 2026-09-12: dropping the `tape=get("tape") or get("z")` "z" fallback
    (raw-dict shape only carries "z") made the tape assertion fail (None != 'C');
    reverted."""
    from agents.market_intelligence.broker import halt_status_shadow as hss
    from agents.market_intelligence import db, execution_client
    ins = AsyncMock()
    monkeypatch.setattr(db, "insert_halt_status_event", ins)
    monkeypatch.setattr(execution_client, "get_data_feed_name", lambda: "iex")
    raw = {"S": "RAWX", "t": "2026-07-17T14:30:00Z", "sc": "H", "sm": "Halted",
           "rc": "LUDP", "rm": "LULD pause", "z": "C"}
    _run(hss._handle_trading_status(raw))
    kw = ins.await_args.kwargs
    assert kw["ticker"] == "RAWX" and kw["status_code"] == "H"
    assert kw["reason_code"] == "LUDP" and kw["tape"] == "C"


def test_handler_never_raises_into_stream_loop(monkeypatch):
    """RED-PROVED 2026-09-12: replacing `_handle_trading_status`'s
    `except Exception: logger.exception(...)` with `except Exception: raise` let the
    mocked db RuntimeError propagate out of the test call; reverted."""
    from agents.market_intelligence.broker import halt_status_shadow as hss
    from agents.market_intelligence import db
    monkeypatch.setattr(db, "insert_halt_status_event",
                        AsyncMock(side_effect=RuntimeError("db down")))
    status = SimpleNamespace(symbol="BOOM", timestamp=None, status_code=None,
                             status_message=None, reason_code=None,
                             reason_message=None, tape=None)
    _run(hss._handle_trading_status(status))  # must not raise
    # symbol-less events are dropped silently (no write attempted)
    ins = AsyncMock()
    monkeypatch.setattr(db, "insert_halt_status_event", ins)
    _run(hss._handle_trading_status({"t": "2026-07-17T14:30:00Z"}))
    ins.assert_not_awaited()


# ─── 3. nightly compare job ────────────────────────────────────────────────────────────

def _patch_compare_db(monkeypatch, rmv_map, halt_map, histories):
    from agents.market_intelligence import db
    monkeypatch.setattr(db, "get_flag_scan_rmv_map", AsyncMock(return_value=rmv_map))
    monkeypatch.setattr(db, "get_halt_events_between", AsyncMock(return_value=halt_map))

    async def _hist(ticker, days, end_date=None):
        return histories.get(ticker, [])
    monkeypatch.setattr(db, "get_recent_daily_history", _hist)
    upsert = AsyncMock()
    monkeypatch.setattr(db, "upsert_dead_data_guard_shadow", upsert)
    return upsert


def test_compare_job_2x2_matrix(monkeypatch):
    """RED-PROVED 2026-09-12: hardcoding the row's "agree" field to `True` (instead of
    `inferred_dead == halted`) made the DEADX disagree-assertion fail
    (`not r["agree"]` on a now-True value); reverted."""
    from agents.market_intelligence.dead_data_guard_shadow import run_dead_data_guard_shadow
    ev = {"status_code": "H", "reason_code": "T12", "status_message": "Halted",
          "event_ts": None, "ticker": None}
    upsert = _patch_compare_db(
        monkeypatch,
        # GOODY has a computed rmv and no halt → the uninformative cell, NOT written
        rmv_map={"DEADX": None, "BOTHX": None, "GOODY": 42.0},
        halt_map={"HALTY": [ev, dict(ev, reason_code="LUDP")], "BOTHX": [ev]},
        histories={"DEADX": _dead_tail(20), "BOTHX": _dead_tail(20),
                   "HALTY": _healthy(20)},
    )
    out = _run(run_dead_data_guard_shadow(date(2026, 7, 17)))

    rows = {c.args[0]["ticker"]: c.args[0] for c in upsert.await_args_list}
    assert set(rows) == {"DEADX", "BOTHX", "HALTY"}

    # inferred-dead, no authoritative halt → disagree (frozen-feed / zombie candidate)
    r = rows["DEADX"]
    assert r["inferred_dead"] and not r["halted_authoritative"] and not r["agree"]
    assert r["none_reason"] == "dead_floor" and r["in_flag_universe"]

    # authoritative halt the daily floor did NOT trip → disagree; outside flag universe
    r = rows["HALTY"]
    assert not r["inferred_dead"] and r["halted_authoritative"] and not r["agree"]
    assert r["halt_events_n"] == 2 and r["halt_codes"] == ["H", "LUDP", "T12"]
    assert r["in_flag_universe"] is False

    # both → agree
    r = rows["BOTHX"]
    assert r["inferred_dead"] and r["halted_authoritative"] and r["agree"]

    assert out == {"n_null_rmv": 2, "n_halted": 2, "n_rows": 3, "n_agree": 1}


def test_compare_job_no_history_row(monkeypatch):
    """RED-PROVED 2026-09-12: changing the empty-history reason string from "no_history"
    to "insufficient_history" made the none_reason equality assertion fail; reverted."""
    from agents.market_intelligence.dead_data_guard_shadow import run_dead_data_guard_shadow
    upsert = _patch_compare_db(
        monkeypatch, rmv_map={"GHOST": None}, halt_map={}, histories={},
    )
    _run(run_dead_data_guard_shadow(date(2026, 7, 17)))
    row = upsert.await_args.args[0]
    assert row["none_reason"] == "no_history" and not row["inferred_dead"]


# ─── 4. bar_stream wiring (the live registration point) ────────────────────────────────
#
# Everything above tests halt_status_shadow / dead_data_guard_shadow in isolation. Neither
# proves the ACTUAL wiring inside `bar_stream.start_bar_stream` — the one call site that
# matters, because it constructs the SAME StockDataStream that carries real-money ORB bars.
# These two tests exercise start_bar_stream end-to-end (stream construction mocked, network
# never touched) to prove (a) the registration hook is actually invoked there, and (b) with
# the flag at its prod default (unset), the constructed stream never sees
# subscribe_trading_statuses — the live-money outage risk the whole default-OFF discipline
# exists to prevent.

def test_start_bar_stream_registers_capture_hook(monkeypatch):
    """RED-PROVED 2026-09-12: commenting out bar_stream.start_bar_stream's
    `maybe_register_status_capture(_data_stream)` call made this fail
    (hook.assert_called_once_with never satisfied); reverted."""
    from agents.market_intelligence.broker import bar_stream, alpaca_client
    from agents.market_intelligence import constants
    from alpaca.data.enums import DataFeed

    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr(alpaca_client, "get_data_feed", lambda: DataFeed.IEX)
    monkeypatch.setattr(bar_stream, "_run_stream", AsyncMock())

    from agents.market_intelligence.broker import halt_status_shadow as hss

    stream_instance = MagicMock()
    _stub_alpaca_data_live(monkeypatch, stream_instance)
    hook = MagicMock()
    monkeypatch.setattr(hss, "maybe_register_status_capture", hook)

    _run(bar_stream.start_bar_stream())

    hook.assert_called_once_with(stream_instance)


def test_start_bar_stream_flag_off_never_subscribes(monkeypatch):
    """End-to-end (real halt_status_shadow, not mocked): with HALT_STATUS_CAPTURE_ENABLED
    unset (the prod default), start_bar_stream must construct the stream WITHOUT ever
    calling subscribe_trading_statuses on it.

    RED-PROVED 2026-09-12: forcing `capture_enabled()` in halt_status_shadow.py to always
    return True (bypassing the env check) made subscribe_trading_statuses get called,
    failing `assert_not_called()`; reverted."""
    from agents.market_intelligence.broker import bar_stream, alpaca_client
    from agents.market_intelligence import constants
    from alpaca.data.enums import DataFeed

    monkeypatch.delenv("HALT_STATUS_CAPTURE_ENABLED", raising=False)
    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr(alpaca_client, "get_data_feed", lambda: DataFeed.IEX)
    monkeypatch.setattr(bar_stream, "_run_stream", AsyncMock())

    stream_instance = MagicMock()
    _stub_alpaca_data_live(monkeypatch, stream_instance)

    _run(bar_stream.start_bar_stream())

    stream_instance.subscribe_trading_statuses.assert_not_called()


def test_compare_job_never_raises(monkeypatch):
    """RED-PROVED 2026-09-12: replacing `run_dead_data_guard_shadow`'s outer
    `except Exception: logger.exception(...)` with `except Exception: raise` let the
    mocked db RuntimeError propagate out of the test call; reverted."""
    from agents.market_intelligence import db
    from agents.market_intelligence.dead_data_guard_shadow import run_dead_data_guard_shadow
    monkeypatch.setattr(db, "get_flag_scan_rmv_map",
                        AsyncMock(side_effect=RuntimeError("db down")))
    out = _run(run_dead_data_guard_shadow(date(2026, 7, 17)))  # must not raise
    assert out["n_rows"] == 0
