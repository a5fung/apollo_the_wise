"""Reader for the psql -A tab captures in this dir (header row, tab delimiter, '(N rows)' trailer,
sections split by '=== NAME ===' lines). Pure parsing, no I/O beyond the named file."""
from __future__ import annotations

import os

P = os.path.dirname(os.path.abspath(__file__))


def read_sections(name: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    cur, hdr = None, None
    with open(os.path.join(P, name), newline="") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("=== ") and line.endswith(" ==="):
                cur, hdr = line[4:-4], None
                out[cur] = []
                continue
            if cur is None or not line:
                continue
            if line.startswith("(") and line.endswith(" rows)") or line.endswith(" row)"):
                continue
            parts = line.split("\t")
            if hdr is None:
                hdr = parts
                continue
            if len(parts) != len(hdr):
                # a stray line (psql notice) — keep going, never silently truncate a row
                continue
            out[cur].append(dict(zip(hdr, parts)))
    return out


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
