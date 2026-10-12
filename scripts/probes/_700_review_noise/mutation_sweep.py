"""#700 - mutation sweep: does each rule in the noise-cut renderer have a test that notices when it is gone?

Applies ONE one-line mutation at a time to `agents/market_intelligence/system_review.py`, runs
`tests/test_weekly_review_noise_700.py` + `tests/test_weekly_review_report_layout.py`, prints which tests
went red, and restores the file (in a `finally`). A mutation with `0 red` is a rule nothing guards.

    python scripts/probes/_700_review_noise/mutation_sweep.py            # all of them
    python scripts/probes/_700_review_noise/mutation_sweep.py M3 M7      # a subset

Result when the build was committed (2026-10-11): every mutation is killed by at least one test.
The test docstrings name these as M1..M24 (M16-M24 are the review-fix round: the settle rule's L1/L2
guard, the held-trade close key, the all-settled header, the no-novelty wording, the era line, the
near-ceiling flag and the preview probe's name-bound pool guard).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
F = ROOT / "agents/market_intelligence/system_review.py"
PREVIEW = ROOT / "scripts/probes/_700_review_noise/preview.py"
OTHER_FILE = {"M19": PREVIEW}          # a mutation that targets a file other than system_review.py

MUTATIONS = {
    "M1 settled forced True": (
        'return {"text": text, "settled": False, "why": why}',
        'return {"text": text, "settled": True, "why": why}'),
    "M2 _changed always prints": (
        '    if cur != prev:\n        return True, f"changed:',
        '    if True:\n        return True, f"changed:'),
    "M3 alert-window close forced": (
        "alert_window_close = bool((metrics.get", "alert_window_close = True or bool((metrics.get"),
    "M4 promotion digits kept": (
        're.sub(r"\\d+", "", str(reasons[0]))', 'str(reasons[0])'),
    "M5 gaps all new": (
        "new = [g for g in gaps if _ticker_date_key(g) not in prior_keys]", "new = list(gaps)"),
    "M6 synthesize keeps report": (
        'prior_metrics = {k: v for k, v in prior_metrics.items() if k != "report"}',
        'prior_metrics = dict(prior_metrics)'),
    "M7 replay lines unfiltered": (
        'return [l for l in lines if not l.strip().startswith(("calibration (", "ⓘ"))]', 'return list(lines)'),
    "M8 compact does not catch": (
        'except Exception:\n        logger.exception(f"{name} compaction failed - the message carries the full text")\n        return fallback',
        'except ZeroDivisionError:\n        return fallback'),
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
        "        elif kind in repl:", "        elif False:"),
    "M13 theme queue shows all": (
        "new = [q for q in basis[\"queue\"] if seen is None or _ticker_date_key(q) not in seen]",
        "new = list(basis[\"queue\"])"),
    "M14 mfe always prints": (
        "    if key(mfe) != key(pm):\n        return True,", "    if True:\n        return True,"),
    "M15 band non-HOLD suppressed": (
        "        elif band != \"HOLD\":\n            show_band, why = True, f\"band {band} is an action\"",
        "        elif False:\n            show_band, why = True, f\"band {band} is an action\""),
    "M16 every L1/L2 section settleable": (
        "        if not beyond and not unlisted:", "        if True:"),
    "M17 closed-trade count move ignored": (
        "    elif live_closed_n != prev_n:", "    elif False:"),
    "M18 all-settled block headerless": (
        "    elif settled:\n        # without a header", "    elif False:\n        # without a header"),
    "M19 name-bound pools unguarded": (
        "        if getattr(mod, \"get_pool\", None) is original:", "        if False:"),
    "M20 era-count line kept in the message": (
        " or s.startswith(\"eras:\"):", ":"),
    "M21 near-ceiling flag dropped": (
        "near = budget > 0 and not over and cost / budget * 100 >= 80", "near = False"),
    "M22 novelty claimed with no prior": (
        "        if seen is None:\n            # nothing to compare", "        if False:\n            # nothing to compare"),
    "M23 partial-taken winner close ignored": (
        "                              or (metrics.get(\"mfe_capture\") or {}).get(\"window_closes\"))",
        "                              or False)"),
    "M24 missing stored count hides": (
        "    elif prev_n is None:", "    elif False:"),
}


def main(only: list[str]) -> int:
    survived = 0
    for name, (old, new) in MUTATIONS.items():
        if only and not any(name.startswith(o + " ") or name == o for o in only):
            continue
        target = OTHER_FILE.get(name.split(" ", 1)[0], F)
        original = target.read_text()
        if old not in original:
            print(f"{name}: PATTERN NOT FOUND (the code moved - update the sweep)")
            survived += 1
            continue
        target.write_text(original.replace(old, new, 1))
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_weekly_review_noise_700.py",
                 "tests/test_weekly_review_report_layout.py", "-q", "-p", "no:cacheprovider",
                 "--no-header", "--tb=no"], cwd=ROOT, capture_output=True, text=True)
        finally:
            target.write_text(original)
        failed = re.findall(r"FAILED (\S+)", r.stdout)
        if not failed:
            survived += 1
        print(f"{name}: {len(failed)} red -> {[f.split('::')[-1] for f in failed]}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
