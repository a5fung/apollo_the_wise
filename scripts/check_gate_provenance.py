"""Preflight/pre-commit gate: enforce ADR 0013's provenance rule (#358).

ADR 0013 (`docs/decisions/0013-consolidation-plays-post-runup.md`) states: "every cohort-shaping
criterion must cite a source [in `docs/methodology/operator_shared_notes.md`]; a number with no
source may record telemetry but may NOT gate or shape the cohort, shadow or not." That rule was
prose only — nothing checked it. Root cause it exists to catch: `is_entry_tight`'s absolute-range
gate silently contradicted the operator's SIGNED 6/16 volatility-relative conclusion for weeks.

WHAT THIS CHECKS, per entry in `scripts/gate_provenance_registry.py` (the enumerated, extensible
scope — Family-A + core detection gates first, NOT every constant in the repo):

  1. STALE     — the registered constant/default no longer exists in its module (renamed/removed
                 without updating the registry). Always a hard failure — the registry has silently
                 gone out of sync, which is worse than no registry.
  2. DRIFT     — the LIVE value in the module no longer matches the value recorded in the registry
                 (numeric equality — `0.50 == 0.5`, `500_000 == 500000`). Always a hard failure,
                 never ratchet-exempt: a legitimate operator-signed value change must update the
                 registry's `value` (+ citation, if the source changed) in the SAME commit as the
                 code change — mirrors "update the SSoT in the same commit" (CLAUDE.md).
  3. BROKEN    — a citation is present but doesn't resolve: the cited file doesn't exist, or the
                 cited text isn't actually found in it (whitespace/dash-normalized compare — see
                 `_normalize`). Always a hard failure, never ratchet-exempt: a citation that doesn't
                 resolve is worse than an honest `None` (it *looks* sourced but isn't).
  4. UNCITED   — `citation` is `None`. This is the literal ADR-0013 violation this build enforces.
                 RATCHET-ELIGIBLE: an UNCITED id already in `gate_provenance_baseline.json` (a
                 tracked, named operator finding — see the registry's own `note` field for each) is
                 reported but does not fail the commit; a NEW uncited id (not in the baseline) fails
                 immediately. The baseline can only shrink via a real citation being added (which
                 itself needs a real source — never fabricate one to shrink the count) or grow via
                 an explicit `--update-baseline` re-run (never to bury a fresh omission — mirrors
                 `preflight_no_silent_failures.py`'s ratchet discipline exactly).

HONEST LIMIT (say this out loud, don't oversell): a citation that IS present and DOES resolve can
still be *semantically* wrong — the original bug was a topical-looking citation for the wrong
conclusion, not a missing one. This check forces the human checkpoint (you cannot add or keep a
cohort gate without writing down where it comes from) — it does not itself verify that the cited
text supports the coded value. Semantic review is still a human job at PR time.

CLI:
  python scripts/check_gate_provenance.py                 # ratchet mode (baseline-aware)
  python scripts/check_gate_provenance.py --strict         # ignore baseline — fail on ANY uncited
  python scripts/check_gate_provenance.py --update-baseline   # regenerate the accepted-uncited list
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from scripts.gate_provenance_registry import GATE_REGISTRY

BASELINE_PATH = Path(__file__).resolve().parent / "gate_provenance_baseline.json"


def _normalize(s: str) -> str:
    """Whitespace/dash-normalize for citation substring matching — a doc rewrap or an en-dash vs
    hyphen difference must not flip a valid citation to BROKEN (advisor 2026-07-17)."""
    s = s.replace("–", "-").replace("—", "-")   # en/em dash -> hyphen
    s = re.sub(r"\s+", " ", s)
    return s.strip()


class _ModuleIndex:
    """Parses one module ONCE and answers value-lookups for both entry kinds this registry uses:
    module-level `NAME = <literal>` (kind="const") and a function's keyword-only default
    (kind="default", name="func:param"). Deliberately narrow — not a general resolver (advisor:
    don't let the AST work balloon past what the registry actually needs)."""

    def __init__(self, repo_root: Path, rel_file: str):
        self.rel_file = rel_file
        self.exists = False
        self._consts: dict[str, object] = {}
        self._defaults: dict[str, object] = {}
        path = repo_root / rel_file
        if not path.exists():
            return
        self.exists = True
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_file)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)):
                try:
                    self._consts[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                for arg, default in zip(a.kwonlyargs, a.kw_defaults):
                    if default is None:
                        continue
                    try:
                        self._defaults[f"{node.name}:{arg.arg}"] = ast.literal_eval(default)
                    except (ValueError, TypeError):
                        pass

    def lookup(self, kind: str, name: str):
        """Returns (found: bool, value) — value is meaningless when found=False."""
        table = self._consts if kind == "const" else self._defaults
        if name not in table:
            return False, None
        return True, table[name]


def evaluate_entry(entry: dict, repo_root: Path) -> list[dict]:
    """Evaluate ONE registry entry against the live repo. Returns a list of violation dicts
    (empty = clean). Pure — no I/O beyond reading `repo_root`-relative files; safe to call with a
    synthetic `repo_root` (a tmp_path fixture) for unit tests, or the real repo for the live gate."""
    violations: list[dict] = []
    mod = _ModuleIndex(repo_root, entry["file"])
    if not mod.exists:
        violations.append({"id": entry["id"], "kind": "STALE",
                            "msg": f"{entry['file']} does not exist"})
        return violations

    found, live_value = mod.lookup(entry["kind"], entry["name"])
    if not found:
        violations.append({"id": entry["id"], "kind": "STALE",
                            "msg": f"`{entry['name']}` not found in {entry['file']} — renamed, "
                                   f"removed, or moved without updating the registry"})
    elif live_value != entry["value"]:
        violations.append({"id": entry["id"], "kind": "DRIFT",
                            "msg": f"registry records {entry['value']!r}, live code has "
                                   f"{live_value!r} — update the registry's `value` (+ citation "
                                   f"if the source changed) in the SAME commit as the code change"})

    citation = entry.get("citation")
    if citation is None:
        violations.append({"id": entry["id"], "kind": "UNCITED",
                            "msg": "no source citation (ADR 0013 provenance rule) — "
                                   + entry.get("note", "")})
    else:
        cited_path = repo_root / citation["file"]
        if not cited_path.exists():
            violations.append({"id": entry["id"], "kind": "BROKEN",
                                "msg": f"cited file does not exist: {citation['file']}"})
        else:
            content = _normalize(cited_path.read_text(encoding="utf-8"))
            if _normalize(citation["text"]) not in content:
                violations.append({"id": entry["id"], "kind": "BROKEN",
                                    "msg": f"cited text not found in {citation['file']}: "
                                           f"{citation['text']!r}"})
    return violations


def _scan(repo_root: Path) -> list[dict]:
    out: list[dict] = []
    for entry in GATE_REGISTRY:
        out.extend(evaluate_entry(entry, repo_root))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo_root = Path(__file__).resolve().parent.parent
    violations = _scan(repo_root)
    by_kind: dict[str, list[dict]] = {}
    for v in violations:
        by_kind.setdefault(v["kind"], []).append(v)
    uncited_ids = sorted(v["id"] for v in by_kind.get("UNCITED", []))
    # STALE/DRIFT/BROKEN are hard failures (never ratchet-exempt) — computed once for both paths so a
    # new hard-fail kind can't be added to one branch and silently missed in the other.
    hard = by_kind.get("STALE", []) + by_kind.get("DRIFT", []) + by_kind.get("BROKEN", [])

    if "--update-baseline" in argv:
        if hard:
            print("Refusing to write baseline — hard failures present (fix these first, they are "
                  "never ratchet-exempt):")
            for v in hard:
                print(f"  [{v['kind']}] {v['id']}: {v['msg']}")
            return 1
        BASELINE_PATH.write_text(
            json.dumps({"uncited_ids": uncited_ids}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"Baseline written: {len(uncited_ids)} known-uncited gate(s) -> "
              f"{BASELINE_PATH.name}.")
        return 0

    strict = "--strict" in argv
    baseline_ids: set[str] = set()
    if BASELINE_PATH.exists() and not strict:
        baseline_ids = set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
                            .get("uncited_ids", []))

    hard_fail = hard
    new_uncited = [v for v in by_kind.get("UNCITED", []) if v["id"] not in baseline_ids]
    known_uncited = [v for v in by_kind.get("UNCITED", []) if v["id"] in baseline_ids]

    if not hard_fail and not new_uncited:
        tail = ("no uncited cohort gates" if not known_uncited else
                f"{len(known_uncited)} known-uncited gate(s), tracked as baseline debt (ADR 0013 "
                f"violations — real findings, not hidden; see each entry's `note`)")
        print(f"Gate-provenance check (#358) — OK ({len(GATE_REGISTRY)} registered gates; {tail}).")
        for v in known_uncited:
            print(f"  [known-uncited] {v['id']}: {v['msg']}")
        return 0

    print("GATE-PROVENANCE CHECK FAILED (#358 / ADR 0013):")
    print()
    for v in hard_fail:
        print(f"  [{v['kind']}] {v['id']}: {v['msg']}")
    for v in new_uncited:
        print(f"  [UNCITED-NEW] {v['id']}: {v['msg']}")
    print()
    print("STALE/DRIFT/BROKEN are never ratchet-exempt (fix the registry or the citation). A NEW")
    print("uncited cohort-shaping gate needs a real source in operator_shared_notes.md / an ADR /")
    print("a setup SSoT / a docs/analysis backtest writeup before it may gate a cohort (ADR 0013).")
    print("Never invent a citation to make this pass, and never silently grow the baseline via")
    print("--update-baseline to bury a fresh omission.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
