"""#465 — same-day dedup must be per-ACCOUNT-MODE, not global.

mi_live_trades carried UNIQUE(ticker, alert_date) with no account_mode, and the two
pre-checks queried without one. A PAPER row therefore suppressed a LIVE entry on the
same ticker/day via ON CONFLICT DO NOTHING. Fail-safe in direction (skip, never
double-order) but a REAL entry silently dropped and mislabeled `window:duplicate`.

Violated dual-account invariant 3 — "account_mode filter on every trade query".
"""
import pathlib
import re

SRC = pathlib.Path("agents/market_intelligence/broker/entry_pipeline.py").read_text()
DB = pathlib.Path("agents/market_intelligence/db.py").read_text()


def test_dedup_precheck_is_mode_scoped():
    m = re.search(r"SELECT EXISTS\(SELECT 1 FROM mi_live_trades[^)]*\)", SRC, re.S)
    assert m, "dedup pre-check not found"
    assert "account_mode" in m.group(0), (
        "a PAPER row would suppress a LIVE entry on the same ticker/day")


def test_open_position_guard_is_mode_scoped():
    i = SRC.index("SELECT alert_date FROM mi_live_trades")
    block = SRC[i:i + 400]
    assert "account_mode = $3" in block, (
        "a PAPER position would block a LIVE entry — paper holds no real shares")


def test_conflict_target_matches_the_new_key():
    assert "ON CONFLICT (ticker, alert_date, account_mode) DO NOTHING" in SRC, (
        "the conflict target must match the unique key or the insert silently no-ops")


def test_schema_and_conflict_target_agree():
    """The failure mode this pair creates is invisible: a mismatched target does not
    error, it just quietly does nothing."""
    assert "UNIQUE (ticker, alert_date, account_mode)" in DB, "CREATE TABLE not updated"
    assert "mi_live_trades_ticker_alert_date_mode_key" in DB, "migration missing"
    assert "DROP CONSTRAINT IF EXISTS mi_live_trades_ticker_alert_date_key" in DB, (
        "old cross-mode constraint must be dropped or the new one cannot help")


def test_mode_resolution_cannot_break_the_entry_path():
    """#444's 'resolver boom' test caught this line unguarded — a registry hiccup
    would have turned into a dropped entry. It must degrade, not propagate."""
    i = SRC.index("_dedup_mode")
    block = SRC[max(0, i - 800):i + 800]
    assert "except Exception" in block and "current_account_mode()" in block, (
        "resolver failure must fall back to the process mode, not raise")
