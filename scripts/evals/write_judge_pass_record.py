"""ADR 0030 — regenerate `scripts/evals/judge_eval_pass_record.json` FROM a captured eval run.

Until now this was a hand step (the preflight's docstring: "no code in this repo writes this
file"), and the hand step could drop the hand-seeded `envelope` section. This tool makes the
regeneration mechanical and faithful:

  python scripts/evals/write_judge_pass_record.py /tmp/judge_eval_v4_20261003.txt

  * finds the `=== RESULTS_JSON ===` block in the captured stdout of
    scripts/evals/run_judge_robustness_eval.py (the paid run — capture once, read many),
  * REFUSES unless `summary.pass` is true (a failing run never becomes a pass record — fix the
    rubric or report, never the record; ADR 0030 §4),
  * writes the FLAT record shape the gate reads — `{**keys, **summary, run_at, pass, n_cases,
    results}` — and CARRIES the existing record's `envelope` section forward verbatim (#547: it
    is a static-read baseline, not an eval output; dropping it silently loses envelope-drift
    detection),
  * never edits any value: every key is copied from the block. Use `--dry-run` to print the
    record it would write.
Then: commit the record and redeploy (market-agent + execution).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECORD = REPO / "scripts" / "evals" / "judge_eval_pass_record.json"
MARKER = "=== RESULTS_JSON ==="


def extract_results_json(captured: str) -> dict:
    """The JSON object that follows the RESULTS_JSON marker (the eval prints it as one json.dumps
    line; a trailing differential block or log noise after it is ignored)."""
    if MARKER not in captured:
        raise ValueError(f"no '{MARKER}' block in the captured output")
    tail = captured.split(MARKER, 1)[1].lstrip()
    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(tail)
    if not isinstance(obj, dict) or "keys" not in obj or "summary" not in obj:
        raise ValueError("RESULTS_JSON block does not carry 'keys' and 'summary'")
    return obj


def build_record(results_json: dict, existing: dict | None, run_at: str | None = None) -> dict:
    """The flat record. Refuses a non-passing run. Carries `envelope` forward from `existing`."""
    summary = results_json["summary"]
    if summary.get("pass") is not True:
        raise ValueError("the captured run did NOT pass — a pass record is never written from a "
                         "failing run (ADR 0030 §4: fix the rubric, never the record)")
    results = results_json.get("results") or []
    record = {
        "run_at": run_at or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **results_json["keys"],
        **{k: v for k, v in summary.items() if k != "by_class"},
        "n_cases": len(results),
        "per_class": summary.get("by_class", {}),
        "pass": True,
    }
    # What the deploy gate reads from SOURCE for the judge model (the tier's fallback pin) — kept
    # beside the eval's real model so the gate compares like with like (2026-10-03).
    try:
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
        from preflight_judge_eval_gate import extract_live_keys
        record["judge_model_source_pin"] = extract_live_keys()["judge_model"]
    except Exception as e:  # loud-ok: the gate then falls back to judge_model and says FAIL on a mismatch
        print(f"warning: could not read the gate's source pin ({e}); judge_model_source_pin not written")
    if existing and "envelope" in existing:
        record["envelope"] = existing["envelope"]      # carried forward VERBATIM (#547)
    return record


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("captured", help="file holding the eval run's captured stdout (+stderr)")
    ap.add_argument("--record", default=str(RECORD), help="the pass record to (re)write")
    ap.add_argument("--dry-run", action="store_true", help="print the record; write nothing")
    args = ap.parse_args(argv)
    captured = Path(args.captured).read_text(encoding="utf-8", errors="replace")
    results_json = extract_results_json(captured)
    record_path = Path(args.record)
    existing = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else None
    record = build_record(results_json, existing)
    text = json.dumps(record, indent=2, default=str) + "\n"
    if args.dry_run:
        print(text)
        return 0
    record_path.write_text(text, encoding="utf-8")
    print(f"wrote {record_path} — rubric {record.get('rubric_version')}/{record.get('rubric_hash')}, "
          f"grader prompt {record.get('catalyst_grade_prompt_version')}, model {record.get('judge_model')}, "
          f"corpus {record.get('corpus_sha1')}, {record.get('n_cases')} cases, overall {record.get('overall')}"
          + (", envelope carried forward" if "envelope" in record else ", ⚠ no envelope section to carry"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
