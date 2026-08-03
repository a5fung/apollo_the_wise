"""An `ON CONFLICT` target must name a constraint that actually exists (2026-08-03).

WHAT HAPPENED. #465 (`5de10cb`, 2026-08-01 16:45 ET) made same-day dedup per-account-mode: it
DROPPED `mi_live_trades_ticker_alert_date_key` and added the 3-column
`mi_live_trades_ticker_alert_date_mode_key`. `live_tracker._insert_skipped_trade` kept naming the
old 2-column target, so from the next boot every skip-row insert raised

    there is no unique or exclusion constraint matching the ON CONFLICT specification

…which was swallowed into a logged ERROR. Nothing operator-facing changed, so it ran unnoticed
through the weekend.

WHY IT MATTERED, which is more than a missing row:
  * the skip row is the DURABLE TERMINAL STATE for a HIGH EP ("every HIGH EP has durable terminal
    state by 4:10 PM ET"), and
  * it is the DUPLICATE-SUPPRESSION ANCHOR — step 1 of `submit_trade_entry` dedupes on the row
    existing. With no row, the `bar_stream` and `cron_9_31` ORB monitors both ran FTK to completion
    on 2026-08-03 and the operator got the same skip alert TWICE.

The one-line clause fix is not the interesting part. **A schema migration and a hand-written
conflict target drifted apart, and only a duplicate Telegram two days later revealed it.** These
tests make the pairing checkable: every conflict target on a table must match a unique constraint
that table actually declares.
"""
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_DB = (_ROOT / "agents/market_intelligence/db.py").read_text()

_SCAN_DIRS = ("agents", "scripts")

# `key(a, b)` -> ("a","b"); whitespace/newline tolerant.
_ON_CONFLICT = re.compile(r"ON\s+CONFLICT\s*\(([^)]*)\)", re.I)
_INSERT_INTO = re.compile(r"INSERT\s+INTO\s+(\w+)", re.I)


def _cols(raw: str) -> tuple:
    return tuple(c.strip() for c in raw.split(",") if c.strip())


def declared_unique_sets(table: str) -> set:
    """Every unique/primary key column-set `db.py` declares for `table`.

    Covers both shapes the schema uses: a table-level `UNIQUE (...)` inside CREATE TABLE, and an
    `ADD CONSTRAINT ... UNIQUE (...)` migration."""
    out = set()
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\n\s*\)\s*;", _DB, re.S)
    if m:
        for u in re.finditer(r"\bUNIQUE\s*\(([^)]*)\)", m.group(1), re.I):
            out.add(_cols(u.group(1)))
        for pk in re.finditer(r"\bPRIMARY KEY\s*\(([^)]*)\)", m.group(1), re.I):
            out.add(_cols(pk.group(1)))
    for a in re.finditer(rf"ALTER TABLE {table}\s+ADD CONSTRAINT \w+\s+UNIQUE\s*\(([^)]*)\)",
                         _DB, re.I | re.S):
        out.add(_cols(a.group(1)))
    return out


def conflict_sites(table: str):
    """(relpath, lineno, columns) for every ON CONFLICT attached to an INSERT INTO `table`."""
    for d in _SCAN_DIRS:
        for path in sorted((_ROOT / d).rglob("*.py")):
            text = path.read_text(errors="replace")
            if table not in text:
                continue
            for m in _ON_CONFLICT.finditer(text):
                before = text[:m.start()]
                ins = _INSERT_INTO.findall(before)
                if not ins or ins[-1] != table:
                    continue
                line = before.count("\n") + 1
                yield path.relative_to(_ROOT).as_posix(), line, _cols(m.group(1))


# ── the schema itself ────────────────────────────────────────────────────────────────────────

def test_mi_live_trades_declares_the_three_column_unique():
    """#465's intent: dedup is PER ACCOUNT MODE, so a paper skip row can never suppress a live
    entry for the same ticker+date."""
    assert ("ticker", "alert_date", "account_mode") in declared_unique_sets("mi_live_trades")


def test_the_old_two_column_constraint_is_explicitly_dropped():
    assert "DROP CONSTRAINT IF EXISTS mi_live_trades_ticker_alert_date_key" in _DB


# ── the pairing that broke ───────────────────────────────────────────────────────────────────

def test_every_conflict_target_matches_a_declared_constraint():
    """The load-bearing one. A conflict target naming a constraint that does not exist raises at
    RUNTIME, on the write path, where it is easy to swallow."""
    declared = declared_unique_sets("mi_live_trades")
    assert declared, "could not parse any unique constraint for mi_live_trades — test is broken"
    bad = [f"{f}:{ln} ON CONFLICT {c}" for f, ln, c in conflict_sites("mi_live_trades")
           if c not in declared]
    assert not bad, (
        f"conflict target(s) match no declared constraint {sorted(declared)}:\n  "
        + "\n  ".join(bad))


def test_there_is_at_least_one_site_to_check():
    """Guard the guard: if the scan finds nothing, the test above passes vacuously."""
    assert list(conflict_sites("mi_live_trades")), "no ON CONFLICT sites found for mi_live_trades"


def test_the_skip_row_insert_specifically_is_mode_scoped():
    """Named directly, because this is the site that broke and the one that carries the
    duplicate-suppression anchor."""
    src = (_ROOT / "agents/market_intelligence/broker/live_tracker.py").read_text()
    i = src.index("INSERT INTO mi_live_trades")
    assert "ON CONFLICT (ticker, alert_date, account_mode) DO NOTHING" in src[i:i + 1500]


# ── the failure must be visible next time ────────────────────────────────────────────────────

def test_a_failed_skip_row_insert_raises_an_audit_event():
    """It failed for two days behind a logger.error. Failing OPEN is correct — a recording failure
    must never alter entry behaviour — but failing SILENTLY is what hid it."""
    src = (_ROOT / "agents/market_intelligence/broker/entry_pipeline.py").read_text()
    i = src.index("_insert_skipped_trade raised")
    assert "skip_row_insert_error" in src[i:i + 700]


def test_the_insert_failure_still_fails_open():
    """The entry path must not start raising because recording broke."""
    src = (_ROOT / "agents/market_intelligence/broker/entry_pipeline.py").read_text()
    i = src.index("await _insert_skipped_trade(")
    assert "except Exception" in src[i:i + 600]


@pytest.mark.parametrize("table", ["mi_live_trades"])
def test_declared_sets_are_parsed_not_assumed(table):
    """If db.py's schema shape ever changes so this parser silently returns nothing, every check
    above degrades to vacuous — fail loudly instead."""
    assert declared_unique_sets(table), f"no constraints parsed for {table}"
