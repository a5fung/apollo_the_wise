"""#706 — the dashboard export (scripts/export_trades_snapshot.sql) feeds the Apollo Trades page's Size % and
Stop % on OPEN positions, so it must (a) carry the open-position inputs under the names portfolio-app2's
apollo_data._load_from_snapshot reads, (b) stay a single read-only SELECT (the host cron runs it against the live
database every night), and (c) keep the date-bounded price and the equity's own date that make a stale input visible.

Nothing here executes the SQL: no database in the unit suite. The one-off run on a real Postgres against synthetic
tables is scripts/probes/_706_export_sql_1103/ (its captured output sits beside the script).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SQL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "export_trades_snapshot.sql"


def _code() -> str:
    """The SQL with every `--` comment removed (a keyword inside a comment must not trip the read-only check)."""
    return re.sub(r"--[^\n]*", "", SQL_PATH.read_text())


def _aliases() -> set[str]:
    return set(re.findall(r"\bAS\s+(\w+)", _code()))


# The #706 inputs, by the names the dashboard documents (apollo_data.py "Optional columns (#706)").
OPEN_POSITION_COLUMNS = (
    "side", "current_price", "current_price_date", "market_value", "account_equity", "account_equity_date",
)
# Columns that existed before #706 and that the dashboard's base schema reads: kept, same names.
LEGACY_ALIASES = (
    "entry_strategy", "status", "entry_price", "stop_price", "hard_stop", "orb_low", "entry_shares", "total_pnl",
    "gap_pct", "ep_score", "lowest_price_seen", "highest_price_seen", "exit_price",
)
LEGACY_BARE = ("ticker", "alert_date", "filled_at", "closed_at", "regime", "catalyst_quality", "account_mode")


@pytest.mark.parametrize("col", OPEN_POSITION_COLUMNS)
def test_selects_each_open_position_input_under_the_dashboards_name(col):
    assert col in _aliases(), f"export no longer selects `{col}` (the dashboard prints a dash for it)"


@pytest.mark.parametrize("col", LEGACY_ALIASES)
def test_keeps_every_pre_706_aliased_column(col):
    assert col in _aliases()


@pytest.mark.parametrize("col", LEGACY_BARE)
def test_keeps_every_pre_706_bare_column(col):
    assert re.search(rf"\b{col}\s*,", _code()), f"`{col}` is no longer selected"


def test_is_one_read_only_statement():
    code = _code().strip()
    assert re.match(r"(?is)(WITH|SELECT)\b", code), "the export must open with SELECT (or a WITH feeding it)"
    assert code.endswith(";") and code.count(";") == 1, "exactly one statement"
    banned = re.findall(
        r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|MERGE|CALL|SET|VACUUM)\b", code)
    assert not banned, f"a read-only export may not contain {sorted(set(banned))}"


def test_stays_the_live_book_only():
    """#480: paper / staged rows must never reach the operator-facing live Trades page."""
    assert re.search(r"AND\s+account_mode\s*=\s*'live'", _code())


def test_every_close_is_bounded_by_the_export_days_et_date():
    """current_price, current_price_date and market_value each read mi_daily_closes: all three on the SAME rule
    ("the latest close on or before the export's ET date"), so they can never describe different days."""
    code = _code()
    assert "AT TIME ZONE 'America/New_York'" in code
    assert len(re.findall(r"FROM\s+mi_daily_closes", code)) == 3
    assert len(re.findall(r"d\.trade_date\s*<=\s*\(SELECT et_date FROM export_day\)", code)) == 3


def test_equity_and_its_date_come_from_the_same_ordering():
    """account_equity and account_equity_date are two reads of ONE row: same filter, same ORDER BY ... LIMIT 1."""
    code = _code()
    assert len(re.findall(r"FROM\s+mi_account_equity_snapshots", code)) == 2
    assert len(re.findall(
        r"ORDER BY e\.snapshot_date DESC, e\.created_at DESC LIMIT 1", code)) == 2
    assert len(re.findall(r"e\.account_mode\s*=\s*mi_live_trades\.account_mode", code)) == 2
