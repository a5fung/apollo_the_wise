"""ADR 0023 F1 — giveback (peak-lock) shadow on the live book. Pins the counterfactual
compute: a round-tripper locks in MORE (positive marginal, earlier exit); a name that never
runs up doesn't arm (zero marginal); no multi-day path → None.
"""
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import giveback_shadow as gs
from agents.market_intelligence.giveback_shadow import compute_giveback_shadow


def _trade(closes, entry=100.0, shares=100.0, stop=95.0, pnl=0.0):
    return {"entry_price": entry, "entry_shares": shares, "hard_stop": stop,
            "running_closes": closes, "alert_date": date(2026, 4, 1), "total_pnl": pnl}


def test_giveback_shadow_roundtripper_locks_in_more():
    # Runs 100→120 then fades to 98. The +6%/60% lock (floor 112 at the 120 peak) exits at 108,
    # while the baseline SMA-trail rides it down to 98 → the lock keeps MORE, earlier.
    r = compute_giveback_shadow(_trade([110, 120, 118, 108, 100, 98], pnl=-134))
    assert r is not None
    assert r["giveback_early"] is True
    assert r["marginal"] > 0
    assert r["giveback_pnl"] > r["baseline_pnl"]


def test_giveback_shadow_no_runup_never_arms_zero_marginal():
    # Drops from the open, never reaches the +6% arm → the lock never engages → identical to baseline.
    r = compute_giveback_shadow(_trade([98, 96], pnl=-400))
    assert r is not None
    assert r["marginal"] == 0.0
    assert r["giveback_early"] is False


def test_giveback_shadow_no_multiday_path_returns_none():
    assert compute_giveback_shadow(_trade([100])) is None     # 1 close
    assert compute_giveback_shadow(_trade([])) is None         # no path (same-day close)
    assert compute_giveback_shadow(_trade([110, 120], entry=0)) is None  # no entry price


def test_giveback_shadow_params_recorded():
    r = compute_giveback_shadow(_trade([110, 120, 108]))
    assert r["arm"] == 0.06 and r["floor_frac"] == 0.60   # the operator-picked 7/9 parameterization


# ── run_giveback_shadow: the WRITE half (mocked pool) — the INSERT + jsonb-string parse
# never run in the compute tests above, and only fire on a live round-tripper. Pin them so
# the first real signal can't be lost to a column/type/parse bug (the #173 0-rows lesson). ──

def _live_row(running_closes):
    return {"id": 777, "ticker": "TEST", "alert_date": date(2026, 4, 1), "account_mode": "live",
            "entry_price": 100.0, "entry_shares": 100.0, "hard_stop": 95.0, "total_pnl": -134.0,
            "running_closes": running_closes}


def _insert_call(conn):
    for c in conn.execute.await_args_list:
        if "INSERT INTO mi_giveback_shadow" in c.args[0]:
            return c
    return None


@pytest.mark.asyncio
async def test_run_giveback_shadow_writes_row_and_audits(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")   # covers _ensure_table CREATE + the INSERT
    conn.fetch = AsyncMock(return_value=[_live_row([110, 120, 118, 108, 100, 98])])
    monkeypatch.setattr(gs, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(gs, "log_audit_event", audit)

    n = await gs.run_giveback_shadow(date(2026, 4, 7))
    assert n == 1
    ins = _insert_call(conn)
    assert ins is not None, "a live round-tripper must produce an INSERT into mi_giveback_shadow"
    # positional args after SQL: id(1), ticker(2), alert_date(3), account_mode(4), actual_pnl(5),
    # baseline_pnl(6), giveback_pnl(7), MARGINAL(8), GIVEBACK_EARLY(9), reason(10), arm(11), floor(12)
    assert ins.args[1] == 777 and ins.args[2] == "TEST" and ins.args[4] == "live"
    assert ins.args[8] > 0            # marginal — the peak-lock kept more than the baseline
    assert ins.args[9] is True        # giveback_early
    assert ins.args[11] == 0.06 and ins.args[12] == 0.60
    audit.assert_awaited_once()       # the giveback_shadow_logged telemetry fired


@pytest.mark.asyncio
async def test_run_giveback_shadow_parses_jsonb_string_closes(monkeypatch):
    # #287 minefield: running_closes can come back as a jsonb STRING, not an array.
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    conn.fetch = AsyncMock(return_value=[_live_row(json.dumps([110, 120, 118, 108, 100, 98]))])
    monkeypatch.setattr(gs, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(gs, "log_audit_event", AsyncMock())

    n = await gs.run_giveback_shadow(date(2026, 4, 7))
    assert n == 1                                  # json.loads(str) path handled the stringified closes
    ins = _insert_call(conn)
    assert ins is not None and ins.args[8] > 0     # same marginal as the array case


@pytest.mark.asyncio
async def test_run_giveback_shadow_skips_no_path_trade(monkeypatch):
    # A same-day stopout (0 closes) — the real WULF case — must write NOTHING and emit no audit.
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="")
    conn.fetch = AsyncMock(return_value=[_live_row([])])
    monkeypatch.setattr(gs, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(gs, "log_audit_event", audit)

    n = await gs.run_giveback_shadow(date(2026, 4, 7))
    assert n == 0 and _insert_call(conn) is None
    audit.assert_not_awaited()
