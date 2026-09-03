#!/usr/bin/env python3
"""Pre-commit Gate 6 — every analysis document carries its caveats.

WHY THIS IS A SCRIPT AND NOT A GUIDELINE
Operator, 2026-08-29, after a geometry analysis was corrected three times in one session and
then retracted: *"you run a lot of analysis, i can't keep pointing out your errors, you need to
do these reviews and analysis with structure, with known caveats, with understanding of the
goals, what we're trying to find, what we're missing etc."*

The standard is `docs/methodology/analysis_standard.md`. This gate enforces the part of it that
is objectively decidable from the text — the same bargain every other gate in this repo makes,
for the same reason: prose discipline has never held here, and PLAN.md, the burndown count,
verify-live and the report format all had to become gates before they stuck.

WHAT IT CHECKS, on ADDED or MODIFIED docs/analysis/*.md only:
  1. a "what this does not answer" section exists and is NOT empty
  2. a method/population statement exists — WHICH ROWS, over WHAT WINDOW
  3. every table row carrying a count states an n (a table of bare percentages hides its base)

WHAT IT DOES NOT CHECK, deliberately: whether the population is CORRECT. That is the failure
that caused this gate to exist and it is not decidable from the text — no regex can tell that a
cohort was admitted by a since-changed filter. §2 of the standard is the human half; this gate
only guarantees the caveats are stated, never that they are right.

Narrow by design. A gate that fires on ordinary work gets switched off within a week.
"""
from __future__ import annotations

import re
import subprocess
import sys

DOC_DIR = "docs/analysis/"

# "What this does not answer" — the section that keeps an analysis honest about its reach.
# `_NUM` — an optional "4. " / "4) " / "IV. " heading prefix. A numbered heading is ordinary
# markdown, and without this the gate rejected `## 4. What this does not answer` on a doc that
# HAD the section (2026-09-01). A false rejection teaches people to --no-verify, which is worse
# than the drift the gate exists to stop.
_NUM = r"(?:[0-9]+|[ivxlIVXL]+)?[.)]?\s*"
_LIMITS = re.compile(
    r"#+\s*" + _NUM + r"(what\s+this\s+does\s*n[o']?t\s+answer"
    r"|what\s+(it|this)\s+does\s*n[o']?t\s+(answer|cover|show)"
    r"|limits?\b|limitations?\b|caveats?\b)", re.I)

# A method statement: says which rows over what window. Either an explicit heading or a
# population line naming a table and a date range.
_METHOD = re.compile(r"#+\s*" + _NUM + r"(method|population|cohort|how\s+this\s+was\s+(built|run|measured))", re.I)
_POP_LINE = re.compile(r"\*\*population:?\*\*|population[:\s]+.*\b(mi_|n\s*=)", re.I)

_EXEMPT = re.compile(r"^\s*(⛔|>|#+\s*(retracted|superseded))", re.I | re.M)


def changed_docs() -> list[tuple[str, bool]]:
    """Analysis docs in the index, each with whether it is NEW.

    ADDED docs are always checked. MODIFIED docs are checked only if they were ALREADY
    compliant, so the gate protects compliance without forcing a retrofit — a document written
    before this standard existed must not become unpublishable because someone corrected a stale
    constant in it. That is not hypothetical: on 2026-08-29 a one-word drift annotation on three
    2026-07 design docs tripped this gate, which is the gate being wrong, not the docs.

    Deletions are not our business.
    """
    try:
        out = subprocess.run(["git", "diff", "--cached", "--name-status"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    files: list[tuple[str, bool]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or parts[0].startswith("D"):
            continue
        path = parts[-1]
        if path.startswith(DOC_DIR) and path.endswith(".md"):
            files.append((path, parts[0].startswith("A")))
    return files


def _was_compliant(path: str) -> bool:
    """Did the committed version already pass? Only then does a modification have to keep it."""
    try:
        prev = subprocess.run(["git", "show", f"HEAD:{path}"],
                              capture_output=True, text=True, timeout=20)
    except Exception:
        return False
    if prev.returncode != 0:
        return False
    return not _problems(prev.stdout)


def _section_body(text: str, header_re: re.Pattern) -> str | None:
    """The text under the first matching header, up to the next header of any level."""
    m = header_re.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"\n#+\s", rest)
    return (rest[:nxt.start()] if nxt else rest).strip()


def check(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    return _problems(text)


def _problems(text: str) -> list[str]:
    # A retracted document is a record of a failure, not a live claim — it is exempt, and the
    # banner is what makes it so.
    if _EXEMPT.search(text[:600]):
        return []

    problems: list[str] = []

    body = _section_body(text, _LIMITS)
    if body is None:
        problems.append(
            'no "What this does not answer" section. Every analysis has a reach; state it. '
            "An unstated limit gets quoted later as though it were not there.")
    elif len(body) < 40:
        problems.append(
            '"What this does not answer" is present but empty. Name at least one real limit — '
            "sample size, the population it excludes, or a question it was never asked.")

    if not (_METHOD.search(text) or _POP_LINE.search(text)):
        problems.append(
            "no method/population statement. Say WHICH ROWS over WHAT WINDOW, and how the "
            "population was derived — §2 of docs/methodology/analysis_standard.md. Population "
            "errors, not arithmetic errors, are what retracted the 2026-08-29 geometry doc.")

    # A results table whose rows carry counts must show them. Cheap proxy: a table exists, it
    # quotes percentages, and the document never writes an n anywhere.
    if re.search(r"^\|.*\|$", text, re.M) and "%" in text:
        if not re.search(r"\bn\s*=|\bn\b\s*\|", text, re.I):
            problems.append(
                "tables quote percentages but no n appears anywhere. A ratio without its "
                "denominator is not a finding (2 of 65 is 3%; 2 events is nothing).")
    return problems


def _report(failed: dict, header: str, footer: str = "") -> int:
    """Print the failures. ONE printer for both entry points (2026-09-02) — the CLI-path branch
    and the pre-commit git-diff branch had their own copies of the same loop, differing only in
    header and footer, which is how two paths quietly start formatting the same failure
    differently."""
    print(header, file=sys.stderr)
    for doc, problems in failed.items():
        print(f"\n  {doc}", file=sys.stderr)
        for pr in problems:
            print(f"    - {pr}", file=sys.stderr)
    if footer:
        print(footer, file=sys.stderr)
    return 1


def main() -> int:
    # ⚠ AN EXPLICIT PATH IS HONOURED (2026-09-02). Until today this ignored argv entirely and
    # always derived its targets from the git diff, so `check_analysis_doc.py <path>` — the form
    # every card brief and docstring reaches for — silently checked something else, or nothing,
    # and printed a pass. A gate that returns 0 for a question it never asked is worse than no
    # gate. Found when a card followed the documented invocation and had to work around it.
    if len(sys.argv) > 1:
        argv = sys.argv[1:]
        if any(a.startswith("-") for a in argv):
            print(f"usage: {sys.argv[0]} [PATH ...]   (no flags; no args = the staged diff)",
                  file=sys.stderr)
            return 2
        failed = {path: problems for path in argv if (problems := check(path))}
        return _report(failed, "✘ analysis document(s) missing required sections") if failed else 0

    docs = changed_docs()
    if not docs:
        return 0
    failed = {}
    for path, is_new in docs:
        if not is_new and not _was_compliant(path):
            continue  # pre-existing document, unrelated edit — see changed_docs()
        if problems := check(path):
            failed[path] = problems
    if not failed:
        return 0
    return _report(
        failed,
        "✘ pre-commit: analysis document(s) missing required sections\n"
        "  Standard: docs/methodology/analysis_standard.md",
        "\n  A RETRACTED doc is exempt — start it with a ⛔ banner if that is what it is.")


if __name__ == "__main__":
    sys.exit(main())
