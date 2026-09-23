"""Preflight gate: ban the swallow-a-failure anti-pattern (#381).

THE recurring bug class (operator 6/25, ABSOLUTE - "never ever eat a failure"):
a BROAD/bare `except` that swallows a REAL failure and falls back SILENTLY. The
same shape produced FMP-403 (#380), theme-shadow-0-rows (#173), and others - each
a `except Exception: pass` / `... return None` that hid a genuine outage behind a
plausible-looking default. THE RULE: **fallback != silent.**

  BANNED (deploy-blocking) in agents/ core/ channels/ shared/ :
    A broad except handler whose body is SILENT - i.e. the except is
      • bare `except:`  OR  `except Exception` / `except BaseException`
        (also a tuple containing one of those, e.g. `except (KeyError, Exception)`)
    AND the handler body contains NEITHER
      • a `raise` (re-raise or raise-new), NOR
      • a call to a LOUD sink (logging, audit, Telegram, humanize - see LOUD_NAMES).

  NOT banned (left alone - genuine control-flow): NARROW excepts
  (`except KeyError: continue`, `except (ValueError, TypeError): return None`) -
  catching a specific, expected exception is normal handling, not a swallow.

  Escape hatch: append `# loud-ok: <reason>` on the `except` line to whitelist a
  reviewed exception - legitimate ONLY for:
    • genuine control-flow (e.g. optional-parse fallbacks), or
    • a fallback-of-the-fallback where even the alert can fail and nothing above
      can handle it (e.g. failure_policy.py's audit/Telegram inner guards).
  It is NOT legitimate to silence a real swallow just to make the gate green.

IMPORTANT - what this gate does NOT enforce (don't read green as "done"):
  • The ping-vs-log POLICY (operator 6/25: Telegram-PING for terminal money/grade
    failures, log-only for self-healing transients). A handler with
    `logger.debug(e); return None` PASSES this gate but may violate the policy -
    that split is enforced by hand in the remediation pass (decorator choice:
    @trade_state_fail_loud vs @advisory_fail_open in failure_policy.py), not by AST.
  • The EXCEPT-LESS silent-failure class (a function that returns null/empty on a
    real miss with no exception at all, e.g. the 200MA-null #371). That is the
    #370 health/completeness-layer flank - a different mechanism.

Static AST walk; comments mentioning "except" are NOT flagged. No runtime needed.
Run: python -m scripts.preflight_no_silent_failures  (or via deploy.sh / pre-commit)
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

# The live/orchestrator code - same scope as preflight_datetime_hygiene (operator
# 6/25: live app dirs only, NOT throwaway scripts/ or tests/, which would never go
# green and the gate would get disabled - a disabled gate is worse than none).
SCOPED_DIRS = ["agents", "core", "channels", "shared"]
EXCLUDE_SUBPATHS = ("backtester/", "backtester\\")

ESCAPE = "# loud-ok"

# RATCHET baseline: the codebase carries ~174 legacy broad+silent swallows (#381).
# Remediating all of them is a phased multi-session effort, and bulk-escaping them
# would be faking green (advisor 6/27). So the gate runs as a RATCHET - it blocks
# any NEW swallow (a file exceeding its baselined count) while the tracked debt is
# remediated DOWN over time. `--update-baseline` regenerates it (only legitimate
# after a real reduction, never to bury a fresh swallow); `--strict` ignores the
# baseline (fails on ANY - the eventual "completely gone" check + the self-test).
BASELINE_PATH = Path(__file__).resolve().parent / "no_silent_failures_baseline.json"

# Calls that make a handler "not silent". The gate only asks "is the failure
# surfaced at all" - NOT "to the right sink" (that is the manual ping-vs-log pass).
LOUD_NAMES = frozenset({
    "warning", "error", "exception", "critical", "info", "debug", "log",
    "log_audit", "log_audit_event", "audit", "audit_event",
    "send_telegram", "send_telegram_message", "humanize",
    "capture_exception", "alert", "_alert", "print",
})

# Path-criticality buckets - for triage ordering only (operator: money/trade/grade
# paths remediated first). Substring match on the relative path.
PATH_CLASS = (
    ("money", ("broker/", "broker\\", "entry_pipeline", "order_manager",
               "trade_stream", "live_tracker", "execution_client", "alpaca_client")),
    ("grade", ("ep_detector", "ep_grade", "catalyst", "mgmt_judge", "judge",
               "ninem_detector", "parabolic_detector", "flag_detector")),
    ("data", ("collector", "db.py", "ingest", "rs_engine", "fundamentals",
              "theme_engine", "minute_volume")),
)


def _classify(rel: str) -> str:
    for label, subs in PATH_CLASS:
        if any(s in rel for s in subs):
            return label
    return "advisory"


def _is_broad(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:                                   # bare `except:`
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    for n in names:
        if isinstance(n, ast.Name) and n.id in ("Exception", "BaseException"):
            return True
    return False


def _is_silent(handler: ast.ExceptHandler) -> bool:
    """True if the handler body neither raises nor calls a LOUD sink."""
    for stmt in handler.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Raise):
                return False
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else (
                    f.id if isinstance(f, ast.Name) else None)
                if name in LOUD_NAMES:
                    return False
    return True


def _has_escape(source_lines: list[str], lineno: int) -> bool:
    if 1 <= lineno <= len(source_lines):
        return ESCAPE in source_lines[lineno - 1]
    return False


class SilentFailureVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str, source_lines: list[str]):
        self.filepath = filepath
        self.lines = source_lines
        self.violations: list[dict] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if _is_broad(node) and _is_silent(node) and not _has_escape(self.lines, node.lineno):
            self.violations.append({"file": self.filepath, "line": node.lineno})
        self.generic_visit(node)


def check_file(filepath: Path) -> list[dict]:
    try:
        source = filepath.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        print(f"WARN: syntax error parsing {filepath}: {e}", file=sys.stderr)
        return []
    v = SilentFailureVisitor(str(filepath), source.splitlines())
    v.visit(tree)
    return v.violations


def _scan(repo_root: Path):
    """Return (violations [each with rel + class], n_files_scanned)."""
    violations: list[dict] = []
    n_files = 0
    for d in SCOPED_DIRS:
        root = repo_root / d
        if not root.exists():
            continue
        for filepath in sorted(root.rglob("*.py")):
            if any(sub in str(filepath) for sub in EXCLUDE_SUBPATHS):
                continue
            n_files += 1
            for v in check_file(filepath):
                rel = (v["file"].replace(str(repo_root) + "/", "")
                       .replace(str(repo_root) + "\\", "").replace("\\", "/"))
                v["rel"] = rel
                v["class"] = _classify(rel)
                violations.append(v)
    return violations, n_files


def _counts(violations: list[dict]) -> dict:
    out: dict[str, int] = {}
    for v in violations:
        out[v["rel"]] = out.get(v["rel"], 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo_root = Path(__file__).resolve().parent.parent
    violations, n_files = _scan(repo_root)
    counts = _counts(violations)

    if "--update-baseline" in argv:
        BASELINE_PATH.write_text(
            json.dumps({"total": len(violations), "per_file": counts},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Baseline written: {len(violations)} known broad+silent swallow(s) "
              f"across {len(counts)} file(s) -> {BASELINE_PATH.name}.")
        return 0

    strict = "--strict" in argv
    baseline: dict = {}
    if BASELINE_PATH.exists() and not strict:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("per_file", {})

    regressions = [(rel, n, baseline.get(rel, 0))
                   for rel, n in sorted(counts.items()) if n > baseline.get(rel, 0)]

    if not regressions:
        baselined = sum(baseline.values())
        tail = ("no broad+silent swallows" if not baselined else
                f"{baselined} known baseline swallow(s) (#381 backlog - trend must go DOWN)")
        print(f"Preflight no-silent-failures - OK "
              f"({n_files} files in {'/'.join(SCOPED_DIRS)} scanned; {tail}).")
        return 0

    print("DEPLOY FAILED - NEW swallow-a-failure anti-pattern(s) beyond baseline (#381):")
    print()
    order = {"money": 0, "grade": 1, "data": 2, "advisory": 3}
    for rel, n, allowed in sorted(regressions, key=lambda r: (order[_classify(r[0])], r[0])):
        lines = sorted(v["line"] for v in violations if v["rel"] == rel)
        print(f"  [{_classify(rel):8}] {rel}: {n} broad+silent except(s), "
              f"baseline allows {allowed} (lines: {lines})")
    print()
    print("A NEW broad except swallows a failure silently. Fix: surface it (raise, or")
    print("log+audit+Telegram via failure_policy.py's @advisory_fail_open /")
    print("@trade_state_fail_loud), OR - only for genuine control-flow - annotate")
    print("`# loud-ok: <reason>` on the except line. Do NOT run --update-baseline to")
    print("bury a real swallow. THE RULE: fallback != silent. (operator 6/25, #381)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
