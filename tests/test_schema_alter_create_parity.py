"""#258 — schema-parity regression: every column a live ALTER TABLE ... ADD COLUMN
IF NOT EXISTS statement can add to a table must ALSO be declared in that table's
CREATE TABLE IF NOT EXISTS block, in agents/market_intelligence/db.py.

Why this matters (not just tidiness): CREATE TABLE IF NOT EXISTS is a NO-OP on an
existing table. Historically, columns were added via trailing ALTERs without ever
being folded back into the CREATE — so a freshly-provisioned database silently
diverges from every long-lived one (a live instance of this cost: crypto_btc_dominance
carried 5 columns in CREATE that nothing ever wrote, found 2026-08-08). This test
pins the inverse direction: an ALTER-only column that a fresh install would be
missing entirely.

Static analysis only — no DB required, no network. Runs in every CI pass.

Known limitation: DDL built dynamically (f-strings / tuple-driven loops) can't be
parsed by a fully generic regex. This test special-cases the three patterns that
exist in db.py today (see _extract_alter_columns). If a NEW dynamic-DDL shape is
added later that this test doesn't recognize, it will silently miss it — the
literal-ALTER path (the common case) is unaffected.
"""
from __future__ import annotations

import re
from pathlib import Path

DB_PY = Path(__file__).resolve().parent.parent / "agents" / "market_intelligence" / "db.py"


def _strip_sql_comments(sql_block: str) -> str:
    """Drop `-- ...` line comments so they can't leak stray commas/parens into
    the column-list splitter below."""
    out_lines = []
    for line in sql_block.split("\n"):
        idx = line.find("--")
        if idx != -1:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def _split_top_level_commas(coldefs: str) -> list[str]:
    """Split a CREATE TABLE column-def block on commas that are NOT inside
    parens (e.g. TEXT[] DEFAULT '{}') or single-quoted string literals."""
    depth = 0
    in_str = False
    parts: list[str] = []
    cur = ""
    for ch in coldefs:
        if ch == "'":
            in_str = not in_str
        if not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if ch == "," and depth == 0 and not in_str:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


_TABLE_LEVEL_KEYWORDS = {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"}


def _extract_create_table_columns(source: str) -> dict[str, list[str]]:
    """table_name -> [column_name, ...] for every `CREATE TABLE IF NOT EXISTS`
    block in the given source text."""
    create_re = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\s{0,16}\);",
        re.IGNORECASE | re.DOTALL,
    )
    tables: dict[str, list[str]] = {}
    for m in create_re.finditer(_strip_sql_comments(source)):
        tbl, coldefs = m.group(1), m.group(2)
        colnames = []
        for part in _split_top_level_commas(coldefs):
            part = part.strip()
            if not part:
                continue
            first_word = part.split()[0].upper()
            if first_word in _TABLE_LEVEL_KEYWORDS:
                continue
            colnames.append(part.split()[0])
        # A table name can legitimately appear only once as CREATE TABLE IF NOT
        # EXISTS in this file; last-write-wins if that ever changes.
        tables[tbl] = colnames
    return tables


def _extract_alter_columns(source: str) -> dict[str, set[str]]:
    """table_name -> {column_name, ...} for every ADD COLUMN IF NOT EXISTS this
    file can issue, across all three shapes currently in db.py:

    1. Literal: ALTER TABLE <tbl> ADD COLUMN IF NOT EXISTS <col> <type...>;
    2. The `_ensure_ep_alert_columns` shape: one ALTER built via
       ", ".join(f"ADD COLUMN IF NOT EXISTS {col}" for col in (<ddl strings>))
    3. Loop-tuple shapes (mi_sell_discipline_records, mi_market_regime):
       for _col, _typ in (("col", "TYPE"), ...): ALTER TABLE <tbl> ADD COLUMN
       IF NOT EXISTS {_col} {_typ}
    """
    tables: dict[str, set[str]] = {}

    # 1. Literal single-column ALTERs.
    literal_re = re.compile(
        r"ALTER TABLE\s+(?:IF EXISTS\s+)?(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)\s+[^;]+;",
        re.IGNORECASE | re.DOTALL,
    )
    for tbl, col in literal_re.findall(source):
        tables.setdefault(tbl, set()).add(col)

    # 2. _ensure_ep_alert_columns: a tuple of quoted "<col> <type...>" DDL clauses,
    # joined into one ALTER TABLE mi_ep_alerts statement.
    m = re.search(
        r'await conn\.execute\("ALTER TABLE (\w+) " \+ ", "\.join\(\s*'
        r'f"ADD COLUMN IF NOT EXISTS \{col\}" for col in \((.*?)\)\)\)',
        source,
        re.DOTALL,
    )
    if m:
        tbl = m.group(1)
        # Strip Python `#` line-comments first — several carry double-quoted
        # prose (e.g. "unseasoned", "1y") that would otherwise be mistaken for
        # DDL clause strings by the quote-scan below.
        clause_block = "\n".join(
            line.split("#", 1)[0] for line in m.group(2).split("\n")
        )
        for clause in re.findall(r'"([^"]+)"', clause_block):
            col = clause.split()[0]
            tables.setdefault(tbl, set()).add(col)

    # 3. Loop-tuple shapes: `for _col, _typ in ((...), ...):` immediately followed
    # (within a few lines) by an f-string ALTER TABLE <tbl> ... {_col} {_typ}.
    # Bounded, non-backtracking scan: find each loop-header position with a cheap
    # single-line regex, then inspect only a small fixed-size slice after it
    # (avoids catastrophic backtracking from a DOTALL .*? across the whole file).
    loop_header_re = re.compile(r"for\s+\w+,\s*\w+\s+in\s+[\(\[]")
    tuple_item_re = re.compile(r'\(\s*"([a-zA-Z_]\w*)"\s*,\s*"([^"]*)"\s*\)')
    alter_after_loop_re = re.compile(r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS")
    close_paren_re = re.compile(r"[\)\]]:\s*\n")
    WINDOW = 2000
    for hm in loop_header_re.finditer(source):
        start = hm.end()
        # Find the end of the tuple literal (the `):` or `]:` closing the for-loop)
        # within a bounded window — the tuple lists here are short (a handful of
        # (col, type) pairs), so this is always well inside WINDOW.
        cm = close_paren_re.search(source, start, start + WINDOW)
        if not cm:
            continue
        tuple_block = source[start:cm.start()]
        after_block = source[cm.end():cm.end() + WINDOW]
        am = alter_after_loop_re.search(after_block)
        if not am:
            continue
        tbl = am.group(1)
        for col, _typ in tuple_item_re.findall(tuple_block):
            tables.setdefault(tbl, set()).add(col)

    return tables


def test_every_alter_added_column_is_also_in_create_table():
    source = DB_PY.read_text()
    create_cols = _extract_create_table_columns(source)
    alter_cols = _extract_alter_columns(source)

    # Sanity: the extractors must actually be finding things, or this test is
    # vacuously passing and worthless.
    assert len(create_cols) > 30, "CREATE TABLE extractor found suspiciously few tables — parser broke"
    assert len(alter_cols) > 10, "ALTER extractor found suspiciously few tables — parser broke"

    missing: dict[str, list[str]] = {}
    for tbl, cols in alter_cols.items():
        create_set = set(create_cols.get(tbl, []))
        gap = sorted(cols - create_set)
        if gap:
            missing[tbl] = gap

    assert not missing, (
        "Column(s) added only via ALTER TABLE, missing from the matching CREATE "
        "TABLE IF NOT EXISTS — a fresh database would never get them (#258). "
        f"Fold into CREATE, keep the ALTER: {missing}"
    )


def test_extractors_see_known_load_bearing_columns():
    """Pin the specific #258 finding (mi_live_trades.account_mode) so a future
    refactor of the extractor regexes can't accidentally stop checking it. This
    column is referenced by the table's own inline UNIQUE constraint — on a
    fresh install, a CREATE TABLE missing it fails outright at CREATE time, not
    just silently diverges."""
    source = DB_PY.read_text()
    create_cols = _extract_create_table_columns(source)
    assert "account_mode" in create_cols.get("mi_live_trades", []), (
        "mi_live_trades.account_mode must be declared in CREATE — it is referenced "
        "by the table's own UNIQUE (ticker, alert_date, account_mode) constraint, "
        "so a fresh CREATE TABLE would fail without it."
    )
