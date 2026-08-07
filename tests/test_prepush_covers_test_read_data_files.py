"""The pre-push gate skipped a push that broke CI, because the change was not Python.

2026-08-06: commit `a9d93eb` changed ONLY `data_gated_reviews.yaml`. `.githooks/pre-push` ran the
suite only when the pushed range touched `*.py`, so it skipped — and the push broke
`test_review_registry_dates_are_dates`, which READS that yaml. CI went red; the local gate whose
entire purpose is to mirror CI stayed silent.

CLAUDE.md already documented this exact failure for CLAUDE.md ("a docs-only push skips the
pre-push pytest gate, so this only surfaces in CI"). It was a known papercut that bit a different
file, which is the signal it needed generalising rather than another footnote.

The hook now also fires on data files the suite reads. THIS test is what stops that list rotting:
it discovers, from the test sources themselves, every repo-root data file the suite opens, and
fails if the hook's pattern would not catch a change to it. Without this the list is a comment
that drifts the first time someone adds a data-driven test.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
HOOK = REPO / ".githooks" / "pre-push"
TESTS = REPO / "tests"

# Literal repo-relative paths passed to Path(...)/open(...) inside tests/.
_READ = re.compile(r'(?:Path|open)\(\s*"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|ya?ml|json|txt|tsv))"')


def _hook_pattern() -> str:
    """Extract `_DATA_RE` from the hook so the test checks the REAL pattern, not a copy.

    A copy would pass forever while the hook drifted — the whole failure mode this file exists
    to prevent, re-created one level up.
    """
    src = HOOK.read_text(encoding="utf-8")
    m = re.search(r"^_DATA_RE='([^']+)'", src, re.M)
    assert m, "could not find _DATA_RE in .githooks/pre-push — did the hook change shape?"
    return m.group(1)


def _discovered_data_paths() -> set[str]:
    found = set()
    for f in sorted(TESTS.glob("test_*.py")):
        for m in _READ.finditer(f.read_text(encoding="utf-8")):
            p = m.group(1)
            # Only repo-root-relative reads matter; tests/fixtures live under tests/, which the
            # hook matches wholesale via `^tests/`.
            if not p.startswith("tests/"):
                found.add(p)
    return found


def test_the_hook_exists_and_exposes_its_pattern():
    assert HOOK.exists(), ".githooks/pre-push is missing — the local CI mirror is gone"
    assert _hook_pattern()


def test_every_data_file_the_suite_reads_would_trigger_the_hook():
    """The regression itself: a change to any of these must NOT skip the suite."""
    pattern = re.compile(_hook_pattern())
    missed = sorted(p for p in _discovered_data_paths() if not pattern.search(p))
    assert not missed, (
        "these repo-root files are READ by the suite but a change to them would SKIP the "
        "pre-push suite, so they can break CI silently (the 2026-08-06 a9d93eb failure):\n  "
        + "\n  ".join(missed)
        + "\n\nAdd them to _DATA_RE in .githooks/pre-push."
    )


def test_discovery_actually_found_something():
    """Guard the guard — if the read-regex stops matching, the test above passes vacuously."""
    found = _discovered_data_paths()
    assert found, "discovered no data reads at all; _READ has probably drifted"
    assert "data_gated_reviews.yaml" in found, (
        "expected the yaml at the centre of the 2026-08-06 failure to be discovered")


@pytest.mark.parametrize("path", ["data_gated_reviews.yaml", "PLAN.md", "CLAUDE.md",
                                  "docs/setups/exit_discipline.md", "agents/x.py"])
def test_known_paths_match(path):
    assert re.compile(_hook_pattern()).search(path), f"{path} should trigger the suite"


@pytest.mark.parametrize("path", ["README.md", "docs/analysis/some_writeup.md",
                                  "CHANGELOG.md", "docs/ops/runbook.md"])
def test_genuinely_docs_only_paths_still_skip(path):
    """The gate must stay narrow. If a plain prose push runs a 45s suite, operators learn
    --no-verify — which is how a safety gate dies."""
    assert not re.compile(_hook_pattern()).search(path), (
        f"{path} is prose the suite does not read; making it trigger the suite trains "
        f"operators toward --no-verify")
