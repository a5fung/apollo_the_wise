"""#722 one-off: prove the ecosystems change moved NO pre-existing byte of the breadth export.

Runs the export as it stood before #722 (git rev 576102f9, the last main commit without `ecosystems`) and the current
file on the SAME synthetic fixture and the SAME embedded Postgres, renders each result to text, cuts the two new
fragments out of the new one (the top-level `ecosystems` array and the `definitions.ecosystems` string) and requires the
rest to be identical, character for character (`generated_at` aside: it carries the run minute).

    python check_722_existing_bytes.py      # needs the same venv as run_export_sql.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

import psycopg2
import pixeltable_pgserver as pgserver

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import run_export_sql as probe  # noqa: E402

BASE_REV = "576102f9"
base = subprocess.run(["git", "show", f"{BASE_REV}:scripts/export_breadth_snapshot.sql"], cwd=probe.REPO,
                      check=True, capture_output=True, text=True).stdout.strip().rstrip(";")
new = probe.SQL.strip().rstrip(";")

days, rows, types = probe.build_fixture()
srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp()) / "pg")
conn = psycopg2.connect(srv.get_uri())
conn.autocommit = True
cur = conn.cursor()
probe.load(cur, rows, types)


def text_of(sql: str) -> str:
    cur.execute("BEGIN READ ONLY")
    cur.execute("SELECT x::text FROM (" + sql + ") AS q(x)")
    out = cur.fetchone()[0]
    cur.execute("ROLLBACK")
    return re.sub(r'"generated_at" : "[^"]*"', "G", out)


tb, tn = text_of(base), text_of(new)
m1 = re.search(r', "ecosystems" : \[.*?\], "stocks" : ', tn, re.S)
assert m1, "top-level ecosystems array not found"
tn = tn[:m1.start()] + ', "stocks" : ' + tn[m1.end():]
m2 = re.search(r', "ecosystems" : "(?:[^"\\]|\\.)*", "theme_returns" : ', tn)
assert m2, "definitions.ecosystems not found"
tn = tn[:m2.start()] + ', "theme_returns" : ' + tn[m2.end():]
same = tb == tn
print(f"base rev {BASE_REV}: {len(tb):,} chars | new, minus the two ecosystems fragments: {len(tn):,} chars")
print("RESULT:", "PASS — every pre-#722 key is character-identical" if same else "FAIL — the text differs")
sys.exit(0 if same else 1)
