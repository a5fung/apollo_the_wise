"""#490 §9.4 — cross-basis residual outcomes (operator-signed 2026-07-24).

The C3 flaw: fwd_1d/5d_pct were stamped vs `baseline_close` = the day CLOSE (AFTER the
intraday move) — understating the very winners the residual dashboard exists to find. The
writers are re-based to CROSS_PX = prev_close × (1 + rt_gap/100) (columns keep their names,
the basis becomes honest) and the two derived cross_to_* columns ride along. The old columns
are NOT deleted; the boot migration backfills historical rows in pure SQL.
"""
import asyncio
from datetime import date

from agents.market_intelligence import ep_delayed_residual as er


class _Conn:
    """backfill_residual_outcomes: one fetch of candidate rows, then per-row fwd closes +
    an UPDATE per row (args captured)."""

    def __init__(self, rows, closes):
        self._rows = rows
        self._closes = closes
        self.executed = []

    async def fetch(self, q, *a):
        if "mi_ep_delayed_residual" in q:
            return self._rows
        return self._closes

    async def execute(self, q, *a):
        self.executed.append(a)


class _Acq:
    def __init__(self, conn):
        self._c = conn

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acq(self._conn)


def _wire(monkeypatch, conn):
    async def _pool():
        return _Pool(conn)
    monkeypatch.setattr(er.db, "get_pool", _pool)
    logged = []

    async def _log(event_type, summary, detail=""):
        logged.append(event_type)
    monkeypatch.setattr(er.db, "log_audit_event", _log)
    return logged


def test_backfill_stamps_cross_basis_forward_outcomes(monkeypatch):
    # prev_close 10, rt_gap +10% → cross_px = 11. Day closed at 13 (the OLD basis).
    # 5 forward closes: fwd_1d = (11.55/11 − 1) = +5.0% vs cross; fwd_5d = (16.5/11 − 1) = +50%.
    # Old basis would have said fwd_1d = (11.55/13 − 1) = −11.2% — a winner misread as a fader.
    row = {"run_date": date(2026, 7, 10), "ticker": "NVVE", "prev_close": 10.0,
           "rt_gap": 10.0, "day_high_gap": 50.0, "baseline_close": 13.0}
    closes = [{"close": 11.55}, {"close": 12.0}, {"close": 12.0}, {"close": 12.0},
              {"close": 16.5}]
    conn = _Conn([row], closes)
    _wire(monkeypatch, conn)
    n = asyncio.run(er.backfill_residual_outcomes())
    assert n == 1
    (fwd1, fwd5, c2c, c2h, run_date, ticker) = conn.executed[0]
    assert fwd1 == 5.0 and fwd5 == 50.0
    assert c2c == round((13.0 / 11.0 - 1) * 100, 2)        # cross → close +18.18%
    assert c2h == round((15.0 / 11.0 - 1) * 100, 2)        # cross → high  +36.36%
    assert (run_date, ticker) == (date(2026, 7, 10), "NVVE")


def test_backfill_skips_unsettled_rows(monkeypatch):
    row = {"run_date": date(2026, 7, 22), "ticker": "TRAX", "prev_close": 10.0,
           "rt_gap": 12.0, "day_high_gap": 40.0, "baseline_close": 11.0}
    conn = _Conn([row], [{"close": 11.0}, {"close": 11.2}])   # only 2 settled closes
    _wire(monkeypatch, conn)
    n = asyncio.run(er.backfill_residual_outcomes())
    assert n == 0 and conn.executed == []


# ── G1: the scan-log writer threads the #490 shadow columns (design M5/C4) ─────────────────

class _ManyConn:
    def __init__(self):
        self.sql = None
        self.rows = None

    async def executemany(self, sql, rows):
        self.sql, self.rows = sql, rows


def test_log_ep_scan_candidates_threads_g1_columns(monkeypatch):
    from agents.market_intelligence import db as mdb
    conn = _ManyConn()

    async def _pool():
        return _Pool(conn)
    monkeypatch.setattr(mdb, "get_pool", _pool)
    rec = {"scan_date": date(2026, 7, 24), "ticker": "NVVE", "gap_pct": 20.0,
           "gap_pct_rt": 20.0, "gap_pct_delayed": 1.0,
           "price_source": "alpaca_sip_universe", "rt_price_age_s": 1.2,
           "prev_close_alpaca": 10.0}
    asyncio.run(mdb.log_ep_scan_candidates([rec]))
    for col in ("gap_pct_rt", "gap_pct_delayed", "price_source",
                "rt_price_age_s", "prev_close_alpaca"):
        assert col in conn.sql
    assert len(conn.rows[0]) == 21                     # 16 legacy + 5 G1 params
    assert conn.rows[0][-5:] == (20.0, 1.0, "alpaca_sip_universe", 1.2, 10.0)


def test_log_ep_scan_candidates_legacy_records_still_write(monkeypatch):
    # FREEZE: a record with none of the G1 keys (flags-off shape minus Pass-1 stamps)
    # writes NULLs — the writer never requires the new keys.
    from agents.market_intelligence import db as mdb
    conn = _ManyConn()

    async def _pool():
        return _Pool(conn)
    monkeypatch.setattr(mdb, "get_pool", _pool)
    asyncio.run(mdb.log_ep_scan_candidates([{"scan_date": date(2026, 7, 24), "ticker": "AAA"}]))
    assert conn.rows[0][-5:] == (None, None, None, None, None)
