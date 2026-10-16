#!/usr/bin/env python3
"""#655 Saturday 10-17 churn re-measure: run the four READ-ONLY query files on prod, each ONCE, each to its own .out.

    python3 scripts/probes/_655_churn_1017/run.py                 # q1 q2 q3 q4, in order
    python3 scripts/probes/_655_churn_1017/run.py q3              # one file (matches the name prefix)
    python3 scripts/probes/_655_churn_1017/run.py --explain       # PLAN-ONLY dry run (syntax + column names); nothing executes

Capture once, read many (CLAUDE.md cost rule): an existing .out is never overwritten; read it instead. Delete it by hand to
re-capture. The SQL goes to the container's psql on STDIN, so nothing is written on the prod host. (If the stdin form is
refused, the fallback is the cwp pattern: copy the file to /tmp/cwp_655_<name>.sql on the host, run it with psql -f, read the
output, and remove the copy; do not retry the stdin form.) Every file opens its own
`BEGIN TRANSACTION READ ONLY`, so a write would fail rather than land. `--explain` prefixes EXPLAIN (no ANALYZE) to every
query statement and leaves the psql-variable definitions alone, so it checks the SQL against the real schema without reading
a row of theme data; its output goes to <name>.explain.out.
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HOST = "apollo@87.99.134.162"
PSQL = "docker exec -i apollo-postgres psql -U apollo -d apollo -X -q -v ON_ERROR_STOP=1"
FILES = ["q1_moved", "q2_undone", "q3_baseline", "q4_named_cases"]


def to_explain(text: str) -> str:
    """Prefix EXPLAIN to each query statement. A statement ends at a ';' outside a dollar-quoted block. The statements that
    define psql variables (they carry \\gset) and BEGIN/COMMIT are left alone so the later statements still expand."""
    out, buf, tag, i = [], [], None, 0
    lines = text.split("\n")
    for line in lines:
        buf.append(line)
        # track dollar quotes ($f$, $m$, $q$, $b$) so a ';' inside a CTE definition does not end the statement
        j = 0
        while True:
            k = line.find("$", j)
            if k < 0:
                break
            e = line.find("$", k + 1)
            if e < 0:
                break
            t = line[k:e + 1]
            if tag is None and len(t) <= 4 and t[1:-1].isalnum():
                tag = t
            elif tag == t:
                tag = None
            j = e + 1
        if tag is None and line.rstrip().endswith((";", "\\gset")):
            stmt = "\n".join(buf)
            sql_lines = [x for x in buf if x.strip() and not x.lstrip().startswith(("--", "\\"))]
            first = sql_lines[0].strip().upper() if sql_lines else ""
            if "\\gset" in stmt or first.startswith(("BEGIN", "COMMIT")) or not sql_lines:
                out.append(stmt)
            else:
                at = next(n for n, x in enumerate(buf) if x.strip() and not x.lstrip().startswith(("--", "\\")))
                buf[at] = "EXPLAIN " + buf[at]
                out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    explain = "--explain" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    todo = [f for f in FILES if not wanted or any(f.startswith(w) for w in wanted)]
    if not todo:
        print("no file matches", wanted)
        return 2
    rc = 0
    for name in todo:
        src = HERE / f"{name}.sql"
        dst = HERE / (f"{name}.explain.out" if explain else f"{name}.out")
        if dst.exists():
            print(f"SKIP {dst.name}: already captured (read it; delete it by hand to re-capture)")
            continue
        sql = src.read_text()
        if explain:
            sql = to_explain(sql)
        proc = subprocess.run(["ssh", HOST, PSQL], input=sql, capture_output=True, text=True)
        dst.write_text(proc.stdout + (("\n-- STDERR --\n" + proc.stderr) if proc.stderr else ""))
        print(f"{'OK  ' if proc.returncode == 0 else 'FAIL'} {name}: exit {proc.returncode}, {len(proc.stdout)} bytes -> {dst.name}")
        if proc.stderr:
            print("   stderr:", proc.stderr.strip().splitlines()[-1][:200])
        rc = rc or proc.returncode
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
