"""ADR 0025 C3 — the Stage-B merge-adjudicator golden-corpus gate (T2b).

Runs every corpus pair (scripts/evals/theme_merge_corpus_v1.json — 8 real 7/11-replay
verdicts + 6 adversarial synthetics) through the REAL adjudicator
(`theme_merge_arm.adjudicate_merge_pair` — the exact prompt / tool-schema / temp=0
path the nightly arm runs) and scores each verdict against the golden
(`accept_also` honored).

GATE (corpus _meta + ADR 0025 §4, operator-signed 7/12): hard pairs 100%, others ≥85%.
**The THEME_MERGE_ARM flip is FORBIDDEN on a failing (or absent) run.**

Read-only by construction: no DB tables touched (the #377 spend meter is not invoked —
the eval passes log_spend=False by default since it may run outside the container).
A WRONG verdict is a datum, never retried (the adjudicator's own retry covers only
transport/parse failures).

On a GREEN run, regenerate the pass record from the RESULTS_JSON block:
  scripts/evals/theme_merge_eval_pass_record.json
FLAT shape (the judge_eval_pass_record.json pattern):
  {**RESULTS_JSON["keys"], **RESULTS_JSON["summary"], "run_at": "<ISO ts>",
   "results": RESULTS_JSON["results"]}
tests/test_theme_merge_corpus_gate.py pins the record against the live prompt/corpus
hashes — editing either without re-running the eval reds CI. Do NOT hand-edit the record.

Run (prod container has the key + deployed code):
  docker cp scripts/evals/run_theme_merge_corpus_eval.py apollo-market:/tmp/ && \
  docker cp scripts/evals/theme_merge_corpus_v1.json apollo-market:/tmp/ && \
  docker exec -w /app apollo-market python /tmp/run_theme_merge_corpus_eval.py /tmp/theme_merge_corpus_v1.json
Locally: ANTHROPIC_API_KEY=... python scripts/evals/run_theme_merge_corpus_eval.py
"""
import asyncio
import hashlib
import json
import sys

# Container runs from /app (probes pattern); harmless locally where the repo is the cwd.
sys.path.insert(0, "/app")

# ── pass bars (corpus _meta + ADR 0025 §4) ───────────────────────────────────
HARD_BAR = 1.0    # hard=true pairs are zero-tolerance
OTHERS_BAR = 0.85


def score_pair(case: dict, verdict: "str | None") -> bool:
    """Pure scorer: golden_verdict plus any accept_also verdicts pass."""
    accepted = {case["golden_verdict"], *case.get("accept_also", [])}
    return verdict in accepted


def summarize(results: list[dict]) -> dict:
    """Aggregate per-pair results → the gate verdict (hard 100% AND others ≥85%)."""
    hard = [r for r in results if r["hard"]]
    others = [r for r in results if not r["hard"]]
    hard_failures = [r["pair_id"] for r in hard if not r["passed"]]
    others_rate = (sum(1 for r in others if r["passed"]) / len(others)) if others else 1.0
    overall = (sum(1 for r in results if r["passed"]) / len(results)) if results else 0.0
    gate_pass = not hard_failures and others_rate >= OTHERS_BAR
    return {
        "n_pairs": len(results),
        "n_hard": len(hard),
        "hard_failures": hard_failures,
        "others_rate": round(others_rate, 3),
        "others_failed": [r["pair_id"] for r in others if not r["passed"]],
        "overall": round(overall, 3),
        "pass": gate_pass,
    }


async def run_eval(pairs: list[dict], adjudicate_fn, client, concurrency: int = 2) -> list[dict]:
    """Run every corpus pair through adjudicate_fn(theme_a, theme_b, client=...)."""
    sem = asyncio.Semaphore(concurrency)

    async def one(case):
        v = await adjudicate_fn(case["theme_a"], case["theme_b"], client=client, semaphore=sem)
        verdict = v.get("verdict")
        return {
            "pair_id": case["id"],
            "hard": bool(case.get("hard")),
            "golden": case["golden_verdict"],
            "accept_also": case.get("accept_also", []),
            "verdict": verdict,
            "passed": score_pair(case, verdict),
            "driver_a": v.get("driver_a", ""),
            "driver_b": v.get("driver_b", ""),
            "reason": v.get("reason", ""),
            "scratchpad": (v.get("analysis_scratchpad") or "")[:300],
        }

    return list(await asyncio.gather(*[one(c) for c in pairs]))


def adjudication_surface_sha1() -> str:
    """Content hash of the live adjudication surface (prompt + tool schema) — the
    pass record pins this so a prompt/schema edit can't dodge a re-run."""
    from agents.market_intelligence.theme_merge_arm import (
        ADJUDICATION_PROMPT, MERGE_ADJUDICATION_TOOL,
    )
    blob = ADJUDICATION_PROMPT + json.dumps(MERGE_ADJUDICATION_TOOL, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


async def main() -> int:
    corpus_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/evals/theme_merge_corpus_v1.json"
    corpus = json.load(open(corpus_path))
    pairs = corpus["pairs"]

    import os
    import anthropic
    from agents.market_intelligence.theme_merge_arm import (
        adjudicate_merge_pair, ADJUDICATION_PROMPT_VERSION,
    )
    from shared.llm_models import HAIKU

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    print(f"Eval: {len(pairs)} pairs | model={HAIKU} | prompt={ADJUDICATION_PROMPT_VERSION} "
          f"({adjudication_surface_sha1()}) | corpus={corpus['_meta']['corpus_version']}", flush=True)

    results = await run_eval(pairs, adjudicate_merge_pair, client)
    summary = summarize(results)

    print("\n=== PER-PAIR ===")
    for r in results:
        kind = "HARD" if r["hard"] else "soft"
        flag = "✓" if r["passed"] else "✗"
        print(f"  [{kind}] {r['pair_id']}  golden={r['golden']:<12} got={str(r['verdict']):<12} {flag}"
              + ("" if r["passed"] else f"   — {r['reason'][:80]}"))
    print(f"\nhard failures: {summary['hard_failures'] or 'NONE'} (bar: zero)")
    print(f"others rate: {summary['others_rate']} (bar {OTHERS_BAR})"
          + (f" — failed: {summary['others_failed']}" if summary["others_failed"] else ""))
    print(f"overall: {summary['overall']}")
    print(f"GATE: {'✓ PASS' if summary['pass'] else '✗ FAIL'} — "
          f"{'the THEME_MERGE_ARM flip is corpus-cleared' if summary['pass'] else 'the THEME_MERGE_ARM flip is FORBIDDEN'}")

    print("\n=== RESULTS_JSON ===")
    print(json.dumps({
        "keys": {
            "prompt_version": ADJUDICATION_PROMPT_VERSION,
            "prompt_sha1": adjudication_surface_sha1(),
            "model": HAIKU,
            "corpus_version": corpus["_meta"]["corpus_version"],
            "corpus_sha1": hashlib.sha1(open(corpus_path, "rb").read()).hexdigest()[:12],
        },
        "summary": summary,
        "results": results,
    }, separators=(",", ":")))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
