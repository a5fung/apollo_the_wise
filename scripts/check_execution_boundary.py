"""#256 W1 — execution/intelligence import-boundary check.

The service split's load-bearing invariant: intelligence-side code reaches
execution ONLY through the typed facade (execution_client.py), never by
importing broker internals. This script enforces it statically, the same way
[5d/7] enforces import hygiene.

MODES
  report (default)  — enumerate every violation, exit 0. This output IS the
                      W1 migration worklist; run it before/while carving the
                      facade.
  check             — exit 8 on any violation. Flips into deploy.sh as
                      [5j/7] once the worklist is empty.

ALLOWED to import agents.market_intelligence.broker.*:
  - broker/ itself
  - execution_client.py (the facade — its lazy function-local imports are the
    one sanctioned seam; W2 swaps them for HTTP calls)
  - integration/ (paper-Alpaca harness exercises broker directly by design)
  - backtester/ (offline, simulates exits; not part of the live service)
  - scripts/, tests/ (ops tooling + tests run inside the owning container)
  - skip_reasons EXEMPTION: `broker.skip_reasons` is pure vocabulary
    (constants + humanize, no broker I/O) — importable from anywhere until it
    graduates to shared/.

INLINE ESCAPE (the `# tz-ok:` pattern): an import line ending in
`# exec-boundary-ok: <reason>` is exempt. Sanctioned reason today:
`moves-with-job (W2)` — the import lives inside a scheduler job / boot block
that transfers WHOLESALE into the execution service at W2, where a direct
broker import is correct; facading it now would be throwaway. W2's job
partition deletes these lines from intelligence entirely.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ROOT / "agents"

# [ \t]* not \s* — \s matches newlines, which would anchor the match on a
# preceding BLANK line: wrong line number reported AND the inline
# `# exec-boundary-ok` marker checked on the wrong line.
_IMPORT_RE = re.compile(
    r"^[ \t]*(?:from|import)\s+agents\.market_intelligence\.broker(?P<sub>\.[\w.]+)?"
    r"(?:[ \t]+import[ \t]+(?P<names>[\w, ()*]+))?",
    re.M,
)

_ALLOWED_DIR_PARTS = ("broker", "integration", "backtester")
_ALLOWED_FILES = ("execution_client.py",)
_VOCab_EXEMPT = ".skip_reasons"


def find_violations() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for py in sorted(SCOPE.rglob("*.py")):
        rel = py.relative_to(ROOT)
        parts = rel.parts
        if any(p in _ALLOWED_DIR_PARTS for p in parts):
            continue
        if rel.name in _ALLOWED_FILES:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for m in _IMPORT_RE.finditer(text):
            sub = m.group("sub") or ""
            names = (m.group("names") or "").strip()
            if sub == _VOCab_EXEMPT:
                continue
            line_idx = text.count("\n", 0, m.start())
            if "# exec-boundary-ok:" in lines[line_idx]:
                continue
            # `from agents.market_intelligence.broker import skip_reasons`-form
            if not sub and names and all(
                n.strip() in ("skip_reasons",) for n in names.split(",")):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            out.append((str(rel), line_no,
                        m.group(0).strip()[:100]))
    return out


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    violations = find_violations()
    if not violations:
        print("Execution-boundary check — OK (no broker imports outside the facade).")
        return
    by_file: dict[str, int] = {}
    for f, n, line in violations:
        by_file[f] = by_file.get(f, 0) + 1
        print(f"  {f}:{n}: {line}")
    print(f"\n{len(violations)} broker import(s) outside the boundary "
          f"across {len(by_file)} file(s):")
    for f, c in sorted(by_file.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3}  {f}")
    if mode == "check":
        print("\nEXECUTION-BOUNDARY CHECK FAILED — route these through "
              "execution_client.py (#256 W1).")
        sys.exit(8)
    print("\n(report mode — this list is the #256 W1 migration worklist)")


if __name__ == "__main__":
    main()
