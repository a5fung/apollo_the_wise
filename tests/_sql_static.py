"""Static checks shared by the nightly-export SQL tests (#706 trades, #719 breadth): the comment and literal strips and
the one-read-only-statement check. Nothing here executes SQL — the unit suite has no database.

ONE banned-keyword list for every export: the two copies had already drifted (#706's did not ban LOCK)."""
from __future__ import annotations

import re

READ_ONLY_BANNED = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|MERGE|CALL|SET|VACUUM|LOCK)\b")


def strip_comments(sql: str) -> str:
    """The SQL with every `--` comment removed (a keyword inside a comment must not trip the read-only check)."""
    return re.sub(r"--[^\n]*", "", sql)


def strip_literals(sql: str) -> str:
    """Every '...' string literal emptied to '' — prose inside a literal (a word like 'set') is not SQL."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def assert_one_read_only(code: str) -> None:
    """`code` (already stripped as the caller needs) is ONE statement, opens with SELECT / WITH, and carries no
    writing or locking keyword — the host cron runs these exports against the live database every night."""
    code = code.strip()
    assert re.match(r"(?is)(WITH|SELECT)\b", code), "the export must open with SELECT (or a WITH feeding it)"
    assert code.endswith(";") and code.count(";") == 1, "exactly one statement"
    banned = READ_ONLY_BANNED.findall(code)
    assert not banned, f"a read-only export may not contain {sorted(set(banned))}"
