"""skip_count_* must not count breakout v1's as-designed stop_too_wide abstains (2026-11-17 L2 page)."""
import asyncio

from agents.market_intelligence import system_audit as sa


class _Conn:
    def __init__(self):
        self.sql = None

    async def fetchrow(self, sql, *args):
        self.sql = sql
        return {"n": 3}


def test_skip_count_excludes_breakout_stop_too_wide_only():
    conn = _Conn()
    assert asyncio.run(sa._today_skip_count(conn, category="setup")) == 3.0
    assert "signal_type = 'breakout_v1'" in conn.sql
    assert "setup:stop_too_wide%" in conn.sql
    # the exclusion is narrow: only that one reason, not all breakout skips
    assert sa._AS_DESIGNED_SKIP_SQL.startswith("NOT (") and "AND skip_reason" in sa._AS_DESIGNED_SKIP_SQL


def test_setup_drilldown_matches_metric():
    spec = next(m for m in sa._TRADE_METRICS if m.name == "skip_count_setup")
    assert "setup:stop_too_wide%" in spec.drill_sql
