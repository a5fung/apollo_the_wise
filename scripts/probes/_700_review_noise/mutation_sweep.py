"""#700 - mutation sweep: does each rule in the noise-cut renderer have a test that notices when it is gone?

Applies ONE one-line mutation at a time to `agents/market_intelligence/system_review.py`, runs
`tests/test_weekly_review_noise_700.py` + `tests/test_weekly_review_report_layout.py`, prints which tests
went red, and restores the file (in a `finally`). A mutation with `0 red` is a rule nothing guards.

    python scripts/probes/_700_review_noise/mutation_sweep.py            # all of them
    python scripts/probes/_700_review_noise/mutation_sweep.py M3 M7      # a subset

Result when the build was committed (2026-10-11): every mutation is killed by at least one test.
The test docstrings name these as M1..M15.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
F = ROOT / "agents/market_intelligence/system_review.py"

MUTATIONS = {
    "M1 settled forced True": (
        'return {"text": text, "settled": False, "why": why}',
        'return {"text": text, "settled": True, "why": why}'),
    "M2 _changed always prints": (
        '    if cur != prev:\n        return True, f"changed:',
        '    if True:\n        return True, f"changed:'),
    "M3 closed_this_week forced": (
        "closed_this_week = bool((metrics.get", "closed_this_week = True or bool((metrics.get"),
    "M4 promotion digits kept": (
        're.sub(r"\\d+", "", str(reasons[0]))', 'str(reasons[0])'),
    "M5 gaps all new": (
        "new = [g for g in gaps if _gap_key(g) not in prior_keys]\n        head = (f\"🚨",
        "new = list(gaps)\n        head = (f\"🚨"),
    "M6 synthesize keeps report": (
        'prior_metrics = {k: v for k, v in prior_metrics.items() if k != "report"}',
        'prior_metrics = dict(prior_metrics)'),
    "M7 replay lines unfiltered": (
        'return [l for l in lines if not l.strip().startswith(("calibration (", "ⓘ"))]', 'return list(lines)'),
    "M8 compact does not catch": (
        'except Exception:\n            logger.exception(f"{name} compaction failed - the message carries the full text")\n            return full_text',
        'except ZeroDivisionError:\n            return full_text'),
    "M9 zone after time counts as ticker": (
        "if tok in _NOT_TICKERS or _AFTER_CLOCK_TIME_RE.search(text[:m.start()]):",
        "if tok in _NOT_TICKERS:"),
    "M10 live rows grouped": (
        '    for r in groups.pop("live", []):\n        lines.append(f"{t} — live: {strip(r.get(\'why\') or \'?\')}")',
        '    for r in groups.pop("live", [])[:1]:\n        lines.append(f"{t} — live: {strip(r.get(\'why\') or \'?\')}")'),
    "M11 early window always prints": (
        "            if at_floor:\n                log(\"early_window_drift\", False",
        "            if False:\n                log(\"early_window_drift\", False"),
    "M12 drift keeps LLM block": (
        'elif kind == "drift" and have_anomalies:', 'elif kind == "drift" and False:'),
    "M13 theme queue shows all": (
        "new = [q for q in basis[\"queue\"] if seen is None or _theme_queue_key(q) not in seen]",
        "new = list(basis[\"queue\"])"),
    "M14 mfe always prints": (
        "show, why = _changed(True, key(mfe), key(pm))", "show, why = True, 'x'"),
    "M15 band non-HOLD suppressed": (
        "        elif band != \"HOLD\":\n            show_band, why = True, f\"band {band} is an action\"",
        "        elif False:\n            show_band, why = True, f\"band {band} is an action\""),
}


def main(only: list[str]) -> int:
    original = F.read_text()
    survived = 0
    for name, (old, new) in MUTATIONS.items():
        if only and not any(name.startswith(o + " ") or name == o for o in only):
            continue
        if old not in original:
            print(f"{name}: PATTERN NOT FOUND (the code moved - update the sweep)")
            survived += 1
            continue
        F.write_text(original.replace(old, new, 1))
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_weekly_review_noise_700.py",
                 "tests/test_weekly_review_report_layout.py", "-q", "-p", "no:cacheprovider",
                 "--no-header", "--tb=no"], cwd=ROOT, capture_output=True, text=True)
        finally:
            F.write_text(original)
        failed = re.findall(r"FAILED (\S+)", r.stdout)
        if not failed:
            survived += 1
        print(f"{name}: {len(failed)} red -> {[f.split('::')[-1] for f in failed]}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
