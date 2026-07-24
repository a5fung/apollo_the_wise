"""FL-2 daily-loss COVERAGE fix pin (operator-signed 2026-07-24).

The daily-loss backstop (`_check_safeguards` in broker/live_tracker.py) must
attribute realized losses by CLOSE day (`closed_at`, ET), NOT `alert_date` — else
a multi-day position (Day 2-5: SMA-trail / partial / time-stop) that stops out
TODAY is invisible to today's -2% limit, because its loss is mis-attributed to the
(prior) alert day. Backtest (mi_live_trades, 40 closed trades / 28 loss-days):
old `alert_date` vs new `closed_at` disagreed on 12/28 loss-days; days that read $0
under alert_date had real realized losses (6/24 -$1483, 5/26 -$862, 5/12 -$639).

Source-pin so a refactor can't silently revert to the buggy alert_date filter.
See docs/setups/safeguards.md change log 2026-07-24.
"""
import re
from pathlib import Path

_LT = (Path(__file__).resolve().parent.parent
       / "agents" / "market_intelligence" / "broker" / "live_tracker.py").read_text()


def _daily_loss_query() -> str:
    """The SUM(total_pnl) daily-loss query block in _check_safeguards."""
    m = re.search(r'today_losses\s*=\s*await conn\.fetchval\(\s*"""(.+?)"""', _LT, re.S)
    assert m, "daily-loss query (today_losses fetchval) not found — refactor?"
    return m.group(1)


def test_daily_loss_counts_by_close_day_not_alert_date():
    q = _daily_loss_query()
    assert "closed_at AT TIME ZONE 'America/New_York'" in q, \
        "daily-loss gate must filter by closed_at (ET), not alert_date (FL-2 coverage fix)"
    assert re.search(
        r"WHERE\s*\(closed_at AT TIME ZONE 'America/New_York'\)::date\s*=\s*\$1", q), \
        "the close-day filter must be the WHERE clause"
    # the buggy alert_date filter must NOT come back
    assert not re.search(r"WHERE\s+alert_date\s*=", q), \
        "daily-loss gate reverted to `alert_date = today` — the multi-day-blind filter"


def test_daily_loss_still_sums_realized_losses_per_mode():
    q = _daily_loss_query()
    assert "SUM(total_pnl)" in q and "total_pnl < 0" in q and "status = 'closed'" in q, \
        "daily-loss gate must still sum realized (closed, losing) trade P&L"
    assert "account_mode = $2" in q, "daily-loss gate must stay per-account_mode"
