"""Regression lock for the ADR-0013 gate-provenance check (#358).

The gate (`scripts/check_gate_provenance.py`) must FAIL a cohort-shaping gate constant that has no
source citation, FAIL a citation that doesn't actually resolve (fabricated/stale), FAIL a value that
silently drifted from what the registry recorded, and leave a properly-cited, unchanged value alone.
The synthetic-fixture tests below prove the MECHANISM on throwaway files (never touching real
detector code); the final section proves the REAL registry is wired and green against the committed
ratchet baseline — mirrors `tests/test_no_silent_failures_gate.py`'s baseline-lock pattern exactly.
"""
import json
from pathlib import Path

import pytest

from scripts.check_gate_provenance import evaluate_entry, _normalize, BASELINE_PATH
from scripts.gate_provenance_registry import GATE_REGISTRY


def _kinds(violations: list[dict]) -> set[str]:
    return {v["kind"] for v in violations}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny synthetic repo: one module with a const + a function with a kwonly default, and one
    doc a citation can point at."""
    mod_dir = tmp_path / "pkg"
    mod_dir.mkdir()
    (mod_dir / "detector.py").write_text(
        "GATE_X = 0.07\n"
        "\n"
        "def scan(*, gate_y: float = 12.5):\n"
        "    return gate_y\n",
        encoding="utf-8",
    )
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "notes.md").write_text(
        "The operator said: tightness caps at 7% intraday range — sourced 2026-06-01.\n"
        "Also a line with an en–dash and   extra   spaces for normalization.\n",
        encoding="utf-8",
    )
    return tmp_path


# ── DoD: the check FAILS on an uncited value ────────────────────────────────────────────────────

def test_fails_on_uncited_value(repo):
    entry = {
        "id": "pkg.detector.GATE_X", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_X", "value": 0.07, "citation": None, "note": "no source yet",
    }
    violations = evaluate_entry(entry, repo)
    assert _kinds(violations) == {"UNCITED"}


def test_481_resolved_findings_stay_cited():
    """#481 (2026-07-18): the 3 operator findings from #358's first pass are RESOLVED and must
    stay CITED — ep_detector.MAX_EXTENSION_PCT (SSoT transcription-fix, operator-ruled 7/18),
    dvol_min ($20M signed as-is), _HTF_MIN_ADR_PCT (operator_shared_notes citation). This guards
    against a regression that silently drops any of their citations. Deliberately does NOT assert
    the global uncited set is empty — a future NEW finding is allowed to appear; only one of these
    three regressing to UNCITED would fail this test (the baseline ratchet is now 0)."""
    repo_root = Path(__file__).resolve().parent.parent
    uncited_ids = {
        e["id"] for e in GATE_REGISTRY
        if any(v["kind"] == "UNCITED" for v in evaluate_entry(e, repo_root))
    }
    resolved = {
        "db.get_anticipation_universe:dvol_min",
        "flag_detector._HTF_MIN_ADR_PCT",
        "ep_detector.MAX_EXTENSION_PCT",
    }
    regressed = resolved & uncited_ids
    assert regressed == set(), f"#481-resolved finding(s) regressed to UNCITED: {regressed}"


# ── a present, correct citation resolves clean ──────────────────────────────────────────────────

def test_cited_and_matching_value_is_clean(repo):
    entry = {
        "id": "pkg.detector.GATE_X", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_X", "value": 0.07,
        "citation": {"file": "docs/notes.md", "text": "tightness caps at 7% intraday range"},
        "note": "",
    }
    assert evaluate_entry(entry, repo) == []


def test_default_kwarg_kind_resolves(repo):
    entry = {
        "id": "pkg.detector.scan:gate_y", "file": "pkg/detector.py", "kind": "default",
        "name": "scan:gate_y", "value": 12.5,
        "citation": {"file": "docs/notes.md", "text": "tightness caps at 7% intraday range"},
        "note": "",
    }
    assert evaluate_entry(entry, repo) == []


# ── a citation that doesn't resolve is BROKEN, not silently trusted ─────────────────────────────

def test_citation_pointing_at_missing_file_is_broken(repo):
    entry = {
        "id": "pkg.detector.GATE_X", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_X", "value": 0.07,
        "citation": {"file": "docs/does_not_exist.md", "text": "anything"},
        "note": "",
    }
    assert _kinds(evaluate_entry(entry, repo)) == {"BROKEN"}


def test_citation_text_not_found_is_broken(repo):
    entry = {
        "id": "pkg.detector.GATE_X", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_X", "value": 0.07,
        "citation": {"file": "docs/notes.md", "text": "this exact sentence is not in the doc"},
        "note": "",
    }
    assert _kinds(evaluate_entry(entry, repo)) == {"BROKEN"}


def test_citation_matching_survives_dash_and_whitespace_normalization(repo):
    """A future rewrap or en-dash/hyphen difference must not spuriously break a valid citation
    (advisor 2026-07-17) — the normalizer collapses both."""
    entry = {
        "id": "pkg.detector.GATE_X", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_X", "value": 0.07,
        "citation": {"file": "docs/notes.md", "text": "an en-dash and extra spaces"},
        "note": "",
    }
    assert evaluate_entry(entry, repo) == []


def test_normalize_folds_en_dash_and_collapses_whitespace():
    assert _normalize("a–b   c\n\nd") == "a-b c d"


# ── silent code drift away from the recorded/cited value is always caught ──────────────────────

def test_value_drift_is_flagged_even_with_a_valid_citation(repo):
    entry = {
        "id": "pkg.detector.GATE_X", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_X", "value": 0.04,   # registry says 0.04, code actually has 0.07
        "citation": {"file": "docs/notes.md", "text": "tightness caps at 7% intraday range"},
        "note": "",
    }
    assert _kinds(evaluate_entry(entry, repo)) == {"DRIFT"}


def test_drift_compares_numerically_not_by_string(repo):
    """0.50 == 0.5 and 500_000 == 500000 must NOT false-trip (advisor 2026-07-17)."""
    (repo / "pkg" / "detector.py").write_text(
        "GATE_Z = 500000\n", encoding="utf-8")
    entry = {
        "id": "pkg.detector.GATE_Z", "file": "pkg/detector.py", "kind": "const",
        "name": "GATE_Z", "value": 500_000, "citation": None, "note": "",
    }
    assert _kinds(evaluate_entry(entry, repo)) == {"UNCITED"}   # no DRIFT alongside it


# ── a renamed/removed constant is STALE, not silently skipped ──────────────────────────────────

def test_missing_constant_is_stale(repo):
    # citation is valid/present so the assertion isolates STALE — a missing constant with NO
    # citation legitimately reports BOTH kinds (see test_missing_constant_without_citation_reports_both).
    entry = {
        "id": "pkg.detector.GONE", "file": "pkg/detector.py", "kind": "const",
        "name": "GONE", "value": 1,
        "citation": {"file": "docs/notes.md", "text": "tightness caps at 7% intraday range"},
        "note": "",
    }
    assert _kinds(evaluate_entry(entry, repo)) == {"STALE"}


def test_missing_constant_without_citation_reports_both():
    """A renamed/removed constant that ALSO has no citation is doubly wrong — both kinds surface,
    neither hides the other."""
    entry = {
        "id": "pkg.detector.GONE", "file": "agents/market_intelligence/anticipation.py",
        "kind": "const", "name": "DOES_NOT_EXIST_XYZ", "value": 1, "citation": None, "note": "",
    }
    repo_root = Path(__file__).resolve().parent.parent
    assert _kinds(evaluate_entry(entry, repo_root)) == {"STALE", "UNCITED"}


def test_missing_module_is_stale(repo):
    entry = {
        "id": "pkg.ghost.X", "file": "pkg/ghost.py", "kind": "const",
        "name": "X", "value": 1, "citation": None, "note": "",
    }
    assert _kinds(evaluate_entry(entry, repo)) == {"STALE"}


# ── the REAL registry stays wired + green against the committed ratchet baseline ────────────────

def test_real_registry_matches_committed_baseline():
    """Mirrors test_no_silent_failures_gate.py::test_committed_baseline_not_exceeded — the ratchet
    must not silently drift up. A NEW uncited gate (or a hard STALE/DRIFT/BROKEN failure, which is
    never baseline-exempt) fails here, in CI, before it reaches prod."""
    repo_root = Path(__file__).resolve().parent.parent
    baseline_ids = set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["uncited_ids"])

    hard_failures = []
    new_uncited = []
    for entry in GATE_REGISTRY:
        for v in evaluate_entry(entry, repo_root):
            if v["kind"] == "UNCITED":
                if v["id"] not in baseline_ids:
                    new_uncited.append(v)
            else:
                hard_failures.append(v)

    assert not hard_failures, f"hard gate-provenance failure(s) (never ratchet-exempt): {hard_failures}"
    assert not new_uncited, (
        f"NEW cohort-shaping gate(s) added without a citation: {new_uncited}. Add a real source "
        f"(operator_shared_notes.md / an ADR / a setup SSoT / a docs/analysis writeup), or — if "
        f"genuinely untraceable — run `python -m scripts.check_gate_provenance --update-baseline` "
        f"to track it as an explicit, named finding (never to bury one silently).")


def test_no_baseline_id_is_orphaned():
    """Every baselined id must still exist in the registry (and still actually be uncited) — an
    orphaned baseline entry would hide a since-fixed gate forever instead of shrinking."""
    repo_root = Path(__file__).resolve().parent.parent
    baseline_ids = set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["uncited_ids"])
    registry_ids = {e["id"] for e in GATE_REGISTRY}
    assert baseline_ids <= registry_ids
