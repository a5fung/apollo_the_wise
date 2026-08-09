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

--differential (#167 gate 2, added 2026-08-09): a DIFFERENT question from the pass/fail gate
above — does forcing `in_narrative_cohort=true` (the population the Lane-2 v2 criteria flip)
move the verdict? Runs every corpus case with `in_narrative_cohort: false` TWICE (as-authored,
then forced true), compares the two verdicts (`classify_movement`), and reports UP/UNCHANGED/DOWN
+ any HIGH-tier boundary crossing (`summarize_differential`). Cases already `true` in the corpus
are skipped — v2 cannot move them, so re-running them spends money without adding information.
Separate log_caller bucket (`judge_narrative_diff_eval`) from the robustness gate's
(`judge_robustness_eval`) and from LIVE grading (`ep_grade_judge`) — #377 spend attribution.
  python /tmp/run_judge_robustness_eval.py /tmp/judge_robustness_corpus_v1.json --differential
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


# ── #167 gate 2 — DIFFERENTIAL mode ──────────────────────────────────────────────────────────
# Question this answers: flipping v2 (Lane-2 cohort criteria) marks MORE tickers
# `in_narrative_cohort: true`, and the judge reads that flag verbatim in the prompt
# ("In narrative cohort (Lane 2): yes/no", ep_grade_judge.py:297). The risk is grade
# INFLATION — more names flagged -> more names graded up -> more entries. This does NOT
# change the robustness gate's four watched keys (rubric/hash/prompt-version/model/corpus
# sha1), so the existing pass/fail eval is silent on it by construction; a differential
# run is the only instrument that can see it.
#
# Ordinal ladders for movement comparison. `mna` is deliberately OUT of GRADE_RANK: it is
# the M&A path (a different axis — "is this company being bought", not "how strong is the
# catalyst"), not a rung on the game_changer/strong/routine excitement ladder. Comparing it
# numerically against those would misclassify an M&A read as an up/down move it isn't.
TIER_RANK = {"none": 0, "MODERATE": 1, "HIGH": 2}
GRADE_RANK = {"routine": 0, "strong": 1, "game_changer": 2}


def _verdict_rank(verdict: dict) -> tuple[int, int | None]:
    return TIER_RANK.get(verdict.get("tier"), -1), GRADE_RANK.get(verdict.get("grade"))


def classify_movement(base: dict | None, forced: dict | None) -> dict:
    """Compare the corpus-value verdict (`base`) against the in_narrative_cohort=true
    verdict (`forced`) for the SAME case. `crossed_into_high` is the behaviourally load-bearing
    signal (HIGH drives the Telegram alert + the ORB submission window) — a tier hold with a
    grade bump is inflation-but-inert; a cross into HIGH is inflation that ACTS."""
    if base is None or forced is None:
        return {"direction": "NO_VERDICT", "tier_delta": None, "grade_delta": None,
                "crossed_into_high": False, "base_tier": base and base.get("tier"),
                "forced_tier": forced and forced.get("tier"),
                "base_grade": base and base.get("grade"),
                "forced_grade": forced and forced.get("grade"),
                "note": "one or both calls returned NO_VERDICT (2x None) — excluded from up/down"}
    bt, bg = _verdict_rank(base)
    ft, fg = _verdict_rank(forced)
    tier_delta = ft - bt
    grade_delta = (fg - bg) if (fg is not None and bg is not None) else None
    if tier_delta > 0 or (tier_delta == 0 and grade_delta and grade_delta > 0):
        direction = "UP"
    elif tier_delta < 0 or (tier_delta == 0 and grade_delta and grade_delta < 0):
        direction = "DOWN"
    else:
        direction = "UNCHANGED"
    note = None
    if base.get("grade") == "mna" or forced.get("grade") == "mna":
        note = "grade includes 'mna' (M&A path) — tier compared, grade_delta not computed"
    return {"direction": direction, "tier_delta": tier_delta, "grade_delta": grade_delta,
            "crossed_into_high": base.get("tier") != "HIGH" and forced.get("tier") == "HIGH",
            "base_tier": base.get("tier"), "forced_tier": forced.get("tier"),
            "base_grade": base.get("grade"), "forced_grade": forced.get("grade"),
            "note": note}


def summarize_differential(results: list[dict]) -> dict:
    """The aggregate #167 gate 2 actually needs: of the flippable population, how many
    grade UP / are UNCHANGED / grade DOWN, plus every boundary crossing named (a crossing is
    what changes behaviour, not the raw up/down count)."""
    up = [r["case_id"] for r in results if r["direction"] == "UP"]
    down = [r["case_id"] for r in results if r["direction"] == "DOWN"]
    unchanged = [r["case_id"] for r in results if r["direction"] == "UNCHANGED"]
    no_verdict = [r["case_id"] for r in results if r["direction"] == "NO_VERDICT"]
    crossed = [r["case_id"] for r in results if r.get("crossed_into_high")]
    return {"n": len(results), "up": len(up), "unchanged": len(unchanged), "down": len(down),
            "no_verdict": len(no_verdict), "up_ids": up, "down_ids": down,
            "unchanged_ids": unchanged, "no_verdict_ids": no_verdict,
            "crossed_into_high": crossed}


async def run_differential(cases: list[dict], grade_fn, client, concurrency: int = 3,
                           timeout: float = 300.0,
                           log_caller: str = "judge_narrative_diff_eval") -> dict:
    """Run every FLIPPABLE case (corpus `in_narrative_cohort: false`) twice: once on the
    payload exactly as authored (the baseline v2 cannot touch it doesn't apply to yet) and
    once with `in_narrative_cohort` forced `true` (the state v2 would put it in). Cases
    already `true` in the corpus are SKIPPED, not re-run: v2 cannot move them (they are
    already the state v2 flips TO), so a second call would spend money answering a question
    nobody is asking — the #167 cost ceiling rules that out, and it isn't information the
    differential needs.

    Retry-on-None mirrors `run_eval`'s contract (one retry for transport/timeout `None`; a
    real verdict is never retried) — reimplemented locally rather than shared because the
    pairing (two calls per case, compared to each other) is a genuinely different shape from
    `run_eval`'s one-call-per-case scoring loop."""
    sem = asyncio.Semaphore(concurrency)
    flippable = [c for c in cases if c["payload"].get("in_narrative_cohort") is False]
    skipped = [c["id"] for c in cases if c["payload"].get("in_narrative_cohort") is not False]

    async def _call(payload):
        v = await grade_fn(client, payload, semaphore=sem, timeout=timeout,
                           include_axis_reads=True, log_caller=log_caller)
        if v is None:  # transport/timeout — retry ONCE; a verdict is never retried
            v = await grade_fn(client, payload, semaphore=sem, timeout=timeout,
                               include_axis_reads=True, log_caller=log_caller)
        return v

    async def one(case):
        base_payload = case["payload"]
        forced_payload = dict(base_payload)
        forced_payload["in_narrative_cohort"] = True
        base_v, forced_v = await asyncio.gather(_call(base_payload), _call(forced_payload))
        move = classify_movement(base_v, forced_v)
        return {"case_id": case["id"], "class": case["class"], **move,
                "base_rationale": (base_v or {}).get("rationale", "")[:300],
                "forced_rationale": (forced_v or {}).get("rationale", "")[:300],
                "base_axis_reads": (base_v or {}).get("axis_reads"),
                "forced_axis_reads": (forced_v or {}).get("axis_reads")}

    results = list(await asyncio.gather(*[one(c) for c in flippable]))
    return {"results": results, "skipped_already_true": skipped,
            "summary": summarize_differential(results)}


async def run_eval(cases: list[dict], grade_fn, client, concurrency: int = 3,
                   timeout: float = 300.0) -> list[dict]:
    """Run every case through grade_fn(client, payload) with one retry on None."""
    sem = asyncio.Semaphore(concurrency)

    async def one(case):
        # log_caller became REQUIRED on grade_holistic 2026-08-02 (an experiment had been billing
        # the LIVE judge's bucket). This eval's spend gets its own bucket for the same reason: it
        # is authorised per run and must be countable on its own, never blended into production
        # grading. ~36 calls, roughly $1.50.
        verdict = await grade_fn(client, case["payload"], semaphore=sem,
                                 timeout=timeout, include_axis_reads=True,
                                 log_caller="judge_robustness_eval")
        if verdict is None:  # transport/timeout/malformed — retry ONCE; a verdict is never retried
            verdict = await grade_fn(client, case["payload"], semaphore=sem,
                                     timeout=timeout, include_axis_reads=True,
                                     log_caller="judge_robustness_eval")
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
    # --differential (#167 gate 2): a flag, not a separate CLI, so it shares corpus loading,
    # the model-override arm, and the client setup below verbatim — only the run+report tail
    # branches. argv is filtered so the flag can appear in any position without disturbing the
    # existing positional corpus_path/model_override contract other callers already rely on.
    argv = [a for a in sys.argv[1:] if a != "--differential"]
    differential = "--differential" in sys.argv[1:]
    corpus_path = argv[0] if len(argv) > 0 else "scripts/evals/judge_robustness_corpus_v1.json"
    model_override = argv[1] if len(argv) > 1 else None  # T7 ensemble arm (e.g. claude-sonnet-5)
    corpus = json.load(open(corpus_path))
    cases = corpus["cases"]

    import os
    import anthropic
    from agents.market_intelligence.ep_grade_judge import (
        grade_holistic, RUBRIC_VERSION, RUBRIC_HASH,
        MODEL as _JUDGE_MODEL_DEFAULT,
    )
    from agents.market_intelligence.ep_detector import CATALYST_GRADE_PROMPT_VERSION

    # #509: record the id the eval ACTUALLY ran on, not the committed pin —
    # ep_grade_judge.MODEL is resolver-tracked and can differ from
    # shared.llm_models.JUDGE_MODEL. This value feeds judge_eval_pass_record.json,
    # which agents/.../model_resolution.py::check_judge_eval_divergence compares
    # against the LIVE resolution — a mislabeled record would corrupt that check.
    actual_model = model_override or _JUDGE_MODEL_DEFAULT

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    print(f"Eval: {len(cases)} cases | model={actual_model} | rubric={RUBRIC_VERSION} ({RUBRIC_HASH}) "
          f"| corpus={corpus['_meta']['corpus_version']}", flush=True)

    if model_override:
        import functools
        grade_fn = functools.partial(grade_holistic, model=model_override)
        print(f"MODEL OVERRIDE: {model_override} (T7 ensemble arm)", flush=True)
    else:
        grade_fn = grade_holistic

    if differential:
        # #167 gate 2 — differential mode. Never touches the robustness gate (summarize/
        # HARD/POSITIVE bars, judge_eval_pass_record.json) — a separate question, a separate
        # report, no shared mutable state.
        diff = await run_differential(cases, grade_fn, client)
        summary = diff["summary"]
        print(f"\n=== DIFFERENTIAL MAP (in_narrative_cohort forced true, {summary['n']} "
              f"flippable of {len(cases)} corpus cases) ===")
        print(f"skipped (already in_narrative_cohort=true in corpus): "
              f"{diff['skipped_already_true'] or 'NONE'}")
        for r in diff["results"]:
            flag = "  <== CROSSED INTO HIGH" if r.get("crossed_into_high") else ""
            print(f"  [{r['direction']:<10}] {r['case_id']:<5} {r['class']:<28} "
                  f"tier {r['base_tier']}->{r['forced_tier']}  grade {r['base_grade']}->{r['forced_grade']}"
                  f"{flag}")
        print(f"\nUP:{summary['up']}  UNCHANGED:{summary['unchanged']}  DOWN:{summary['down']}"
              f"  NO_VERDICT:{summary['no_verdict']}  (of {summary['n']} flippable)")
        print(f"crossed into HIGH: {summary['crossed_into_high'] or 'NONE'}")

        print("\n=== DIFFERENTIAL_RESULTS_JSON ===")
        print(json.dumps({
            "keys": {"rubric_version": RUBRIC_VERSION, "rubric_hash": RUBRIC_HASH,
                     "catalyst_grade_prompt_version": CATALYST_GRADE_PROMPT_VERSION,
                     "judge_model": actual_model,
                     "corpus_version": corpus["_meta"]["corpus_version"],
                     "corpus_sha1": __import__("hashlib").sha1(open(corpus_path, "rb").read()).hexdigest()[:12]},
            "skipped_already_true": diff["skipped_already_true"],
            "summary": summary,
            "results": diff["results"],
        }, separators=(",", ":")))
        return 0

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
                 "judge_model": actual_model,
                 "corpus_version": corpus["_meta"]["corpus_version"],
                 "corpus_sha1": __import__("hashlib").sha1(open(corpus_path,"rb").read()).hexdigest()[:12]},
        "summary": summary,
        "results": results,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
