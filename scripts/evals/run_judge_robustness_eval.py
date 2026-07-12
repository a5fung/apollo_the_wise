"""ADR 0030 C1/C3 — the judge-robustness eval (Arm 1: judge-payload).

Feeds every corpus case's payload (exact `assemble_judge_inputs` shape) to the REAL judge
(`grade_holistic`, live JUDGE_MODEL, `include_axis_reads=True` — the eval arm it was built for),
scores the normalized verdict against the case's `golden.must` predicates, and prints:
  1. the ROBUSTNESS MAP (per-class pass rates + the gate verdict per ADR 0030 §3 bars), and
  2. a delimited RESULTS_JSON block (per-case verdict + rationale — the failure-analysis input +
     the pass-record source; the caller writes the repo files from it).

Read-only by construction: no DB tables are touched (the #377 spend meter's audit rows are the
only side effect). One retry on a None verdict (transport/timeout) — a WRONG verdict is a datum,
never retried. Timeout is generous (300s): grade_holistic's wait_for bounds time INCLUDING
semaphore queueing (built for the 9:45 market cutoff, which does not exist offline).

Run (prod container has the key + the deployed judge code):
  docker cp corpus+this → apollo-market:/tmp/ → docker exec -w /app apollo-market \
      python /tmp/run_judge_robustness_eval.py /tmp/judge_robustness_corpus_v1.json
Tests: tests/test_judge_robustness_eval.py (pure scorer truth-table + fake-client end-to-end).
"""
import asyncio
import json
import sys

# Container runs from /app (probes pattern); harmless locally where the repo is the cwd.
sys.path.insert(0, "/app")

# ── pass bars (ADR 0030 §3, operator-signed F2 at the 7/12 sitting) ─────────────────────────
HARD_CLASSES = {
    "mna_as_catalyst", "stale_news_repackaged", "dilutive_offering_as_growth",
    "promotional_microcap_pr", "one_time_eps_anomaly",
    # T2a degradation classes fail-conservative — hard — EXCEPT the positive control D08:
    "degradation_empty_corpus", "degradation_retrieval_artifact",
    "degradation_contradictory_layers", "degradation_thin_social_only",
    "degradation_stale_only_corpus", "degradation_truncated_midclaim",
    "degradation_conflicting_figures",
}
POSITIVE_CLASSES = {
    "structural_upgrade", "transformative_for_size", "clean_print_control",
    "degradation_thin_but_complete",
}
SOFT_BAR = 0.80          # per soft class
POSITIVE_BAR = 0.80      # aggregate across positive-control cases
OVERALL_BAR = 0.85


def check_predicates(must: dict, verdict: dict) -> tuple[bool, list[str]]:
    """Pure predicate scorer. Returns (passed, [failed-predicate descriptions])."""
    fails = []
    tier = verdict.get("tier")
    grade = verdict.get("grade")
    direction = verdict.get("direction_vs_floor")
    for key, want in must.items():
        if key == "tier_is":
            if tier != want:
                fails.append(f"tier_is {want} (got {tier})")
        elif key == "tier_not":
            if tier == want:
                fails.append(f"tier_not {want} (got {tier})")
        elif key == "tier_in":
            if tier not in want:
                fails.append(f"tier_in {want} (got {tier})")
        elif key == "grade_is":
            if grade != want:
                fails.append(f"grade_is {want} (got {grade})")
        elif key == "grade_in":
            if grade not in want:
                fails.append(f"grade_in {want} (got {grade})")
        elif key == "direction_in":
            if direction not in want:
                fails.append(f"direction_in {want} (got {direction})")
        else:  # unknown predicate = authoring error → loud fail, never silent pass
            fails.append(f"UNKNOWN predicate {key!r}")
    return (not fails, fails)


def summarize(results: list[dict]) -> dict:
    """Aggregate case results → the robustness map + the gate verdict."""
    by_class: dict[str, dict] = {}
    for r in results:
        c = by_class.setdefault(r["class"], {"n": 0, "passed": 0, "failed_ids": []})
        c["n"] += 1
        if r["passed"]:
            c["passed"] += 1
        else:
            c["failed_ids"].append(r["case_id"])

    hard_failures = [r["case_id"] for r in results
                     if r["class"] in HARD_CLASSES and not r["passed"]]
    pos = [r for r in results if r["class"] in POSITIVE_CLASSES]
    pos_rate = (sum(1 for r in pos if r["passed"]) / len(pos)) if pos else 1.0
    soft_below = sorted(
        cls for cls, c in by_class.items()
        if cls not in HARD_CLASSES and cls not in POSITIVE_CLASSES
        and c["passed"] / c["n"] < SOFT_BAR
    )
    overall = sum(1 for r in results if r["passed"]) / len(results) if results else 0.0
    gate_pass = (not hard_failures and pos_rate >= POSITIVE_BAR
                 and not soft_below and overall >= OVERALL_BAR)
    return {
        "by_class": {k: {"n": v["n"], "passed": v["passed"],
                         "rate": round(v["passed"] / v["n"], 2),
                         "failed_ids": v["failed_ids"]}
                     for k, v in sorted(by_class.items())},
        "hard_failures": hard_failures,
        "positive_control_rate": round(pos_rate, 2),
        "soft_classes_below_bar": soft_below,
        "overall": round(overall, 3),
        "pass": gate_pass,
    }


async def run_eval(cases: list[dict], grade_fn, client, concurrency: int = 3,
                   timeout: float = 300.0) -> list[dict]:
    """Run every case through grade_fn(client, payload) with one retry on None."""
    sem = asyncio.Semaphore(concurrency)

    async def one(case):
        verdict = await grade_fn(client, case["payload"], semaphore=sem,
                                 timeout=timeout, include_axis_reads=True)
        if verdict is None:  # transport/timeout/malformed — retry ONCE; a verdict is never retried
            verdict = await grade_fn(client, case["payload"], semaphore=sem,
                                     timeout=timeout, include_axis_reads=True)
        if verdict is None:
            return {"case_id": case["id"], "class": case["class"], "passed": False,
                    "verdict": None, "failed_predicates": ["NO_VERDICT (2x None)"],
                    "rationale": None}
        passed, fails = check_predicates(case["golden"]["must"], verdict)
        return {"case_id": case["id"], "class": case["class"], "passed": passed,
                "verdict": {k: verdict.get(k) for k in
                            ("grade", "tier", "direction_vs_floor", "materiality_tier",
                             "fire_axes", "confidence")},
                "failed_predicates": fails,
                "rationale": (verdict.get("rationale") or "")[:400],
                "axis_reads": verdict.get("axis_reads")}

    return list(await asyncio.gather(*[one(c) for c in cases]))


async def main() -> int:
    corpus_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/evals/judge_robustness_corpus_v1.json"
    model_override = sys.argv[2] if len(sys.argv) > 2 else None  # T7 ensemble arm (e.g. claude-sonnet-5)
    corpus = json.load(open(corpus_path))
    cases = corpus["cases"]

    import os
    import anthropic
    from agents.market_intelligence.ep_grade_judge import (
        grade_holistic, RUBRIC_VERSION, RUBRIC_HASH,
    )
    from agents.market_intelligence.ep_detector import CATALYST_GRADE_PROMPT_VERSION
    from shared.llm_models import JUDGE_MODEL

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    print(f"Eval: {len(cases)} cases | model={JUDGE_MODEL} | rubric={RUBRIC_VERSION} ({RUBRIC_HASH}) "
          f"| corpus={corpus['_meta']['corpus_version']}", flush=True)

    if model_override:
        import functools
        grade_fn = functools.partial(grade_holistic, model=model_override)
        print(f"MODEL OVERRIDE: {model_override} (T7 ensemble arm)", flush=True)
    else:
        grade_fn = grade_holistic
    results = await run_eval(cases, grade_fn, client)
    summary = summarize(results)

    print("\n=== ROBUSTNESS MAP (per class) ===")
    for cls, c in summary["by_class"].items():
        kind = ("HARD" if cls in HARD_CLASSES else
                "POS " if cls in POSITIVE_CLASSES else "soft")
        flag = "" if not c["failed_ids"] else f"  ✗ {','.join(c['failed_ids'])}"
        print(f"  [{kind}] {cls:<34} {c['passed']}/{c['n']}{flag}")
    print(f"\nhard failures: {summary['hard_failures'] or 'NONE'}")
    print(f"positive-control rate: {summary['positive_control_rate']} (bar {POSITIVE_BAR})")
    print(f"soft classes below bar: {summary['soft_classes_below_bar'] or 'NONE'}")
    print(f"overall: {summary['overall']} (bar {OVERALL_BAR})")
    print(f"GATE: {'✓ PASS' if summary['pass'] else '✗ FAIL'}")

    print("\n=== RESULTS_JSON ===")
    print(json.dumps({
        "keys": {"rubric_version": RUBRIC_VERSION, "rubric_hash": RUBRIC_HASH,
                 "catalyst_grade_prompt_version": CATALYST_GRADE_PROMPT_VERSION,
                 "judge_model": JUDGE_MODEL,
                 "corpus_version": corpus["_meta"]["corpus_version"],
                 "corpus_sha1": __import__("hashlib").sha1(open(corpus_path,"rb").read()).hexdigest()[:12]},
        "summary": summary,
        "results": results,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
