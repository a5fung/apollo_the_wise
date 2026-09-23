"""#167 gate 2, PART 2 — the roster channel (2026-08-09).

Gate 2 part 1 (`run_judge_robustness_eval.py --differential`, captured at
docs/analysis/167_judge_narrative_differential_2026-08-09.txt) tested ONLY the
`in_narrative_cohort` BOOLEAN — one of two channels v2 (Lane-2 registry mode) changes.
The untested channel is `active_narratives` — the roster block `ep_grade_judge.py` renders
whenever non-empty (~lines 264-277), which the prompt explicitly says lights the
theme/narrative axis "EVEN IF this ticker is not listed as a cohort member." The corpus
carries zero `active_narratives`, so this channel has never been varied, and it is the
channel v2 changes MOST: v2's roster is a 12-member narrative carried seven weeks (the
real 2026-06-17 -> 2026-07-31 "AI data center infrastructure buildout" cohort, mined from
the actual Lane-2 v2 replay output, not invented), vs v1's 2-3 member same-day groups.

This runs ONE new arm: every corpus case (all 36 — the 33 flippable + the 3 already
`in_narrative_cohort: true`), with the roster passed as `active_narratives`,
`in_narrative_cohort` LEFT AT ITS CORPUS VALUE (never forced — that channel was already
tested by gate 2 part 1). ONE call per case, not paired — the comparison baseline is the
ALREADY-CAPTURED gate-2-part-1 output (`base_tier`/`base_grade`/`base_rationale` per case,
read from the differential file), so re-running a no-roster baseline here would spend money
answering a question already answered. This script only makes the NEW call and dumps raw
per-case verdicts; the diff against the captured baseline happens in local post-processing
(no API cost) so a bug in the diff logic never requires a second paid run.

Own log_caller bucket (`judge_narrative_roster_eval`) — #377 spend attribution, separate
from `judge_narrative_diff_eval` (gate 2 part 1), `judge_robustness_eval` (the pass/fail
gate), and live `ep_grade_judge`.

Run (prod container has the key + the deployed judge code):
  docker cp scripts/evals/judge_robustness_corpus_v1.json apollo-market:/tmp/
  docker cp scripts/evals/run_judge_narrative_roster_eval.py apollo-market:/tmp/
  docker exec -w /app apollo-market python /tmp/run_judge_narrative_roster_eval.py \
      /tmp/judge_robustness_corpus_v1.json
Output captured directly to a LOCAL file via the ssh/docker-exec stdout pipe (never a
redirect INSIDE the remote command — that lands on the host's /tmp, not the container's,
and not on the local machine either; #167 gate-2-part-1 note).
"""
import asyncio
import json
import sys

sys.path.insert(0, "/app")

# ── the real v2 roster, mined verbatim from the Lane-2 v2 replay (2026-06-08 -> 2026-08-07,
# scratchpad lane2_replay_full.json) — the LAST good (non-error) snapshot of the one cohort
# that ever cleared the 3-member auto-promote bar, 2026-07-31, 12 members (FIFO-capped at
# LANE2_REGISTRY_MAX_MEMBERS=12; the four earliest joiners AEHR/JBL/FCEL/MU rolled off).
# name/thesis/tickers/run_date are UNEDITED from the replay's own proposal record.
ROSTER = [
    {
        "run_date": "2026-07-31",
        "name": "AI data center infrastructure buildout",
        "tickers": ["WULF", "DOCN", "PENG", "CLSK", "TSEM", "SMCI", "CORZ", "TER",
                    "COHU", "BLZE", "FLNC", "MPWR"],
        "thesis": (
            "Both stocks gapped on fresh AI-driven infrastructure demand—AEHR's "
            "burn-in equipment order for AI/data-center chips and JBL's AI data center "
            "hardware alliance with Adani—reflecting the broader AI capex buildout "
            "cycle."
        ),
    },
]


async def run_roster_arm(cases: list[dict], roster: list[dict], grade_fn, client,
                          concurrency: int = 3, timeout: float = 300.0,
                          log_caller: str = "judge_narrative_roster_eval") -> list[dict]:
    """ONE call per case: payload's `active_narratives` set to `roster`,
    `in_narrative_cohort` untouched (corpus value). One retry on a None verdict
    (transport/timeout) — mirrors run_eval/run_differential's contract."""
    sem = asyncio.Semaphore(concurrency)

    async def _call(payload):
        v = await grade_fn(client, payload, semaphore=sem, timeout=timeout,
                           include_axis_reads=True, log_caller=log_caller)
        if v is None:
            v = await grade_fn(client, payload, semaphore=sem, timeout=timeout,
                               include_axis_reads=True, log_caller=log_caller)
        return v

    async def one(case):
        payload = dict(case["payload"])
        payload["active_narratives"] = roster
        v = await _call(payload)
        return {
            "case_id": case["id"], "class": case["class"],
            "corpus_in_narrative_cohort": case["payload"].get("in_narrative_cohort"),
            "golden": case.get("golden"),
            "verdict": None if v is None else {
                "tier": v.get("tier"), "grade": v.get("grade"),
                "direction_vs_floor": v.get("direction_vs_floor"),
                "confidence": v.get("confidence"),
            },
            "rationale": (v or {}).get("rationale", "")[:400],
            "axis_reads": (v or {}).get("axis_reads"),
        }

    return list(await asyncio.gather(*[one(c) for c in cases]))


async def main() -> int:
    corpus_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/evals/judge_robustness_corpus_v1.json"
    corpus = json.load(open(corpus_path))
    cases = corpus["cases"]

    import os
    import anthropic
    from agents.market_intelligence.ep_grade_judge import (
        grade_holistic, RUBRIC_VERSION, RUBRIC_HASH, MODEL as _JUDGE_MODEL_DEFAULT,
    )
    from agents.market_intelligence.ep_detector import CATALYST_GRADE_PROMPT_VERSION

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    print(f"Roster eval: {len(cases)} cases | model={_JUDGE_MODEL_DEFAULT} | "
          f"rubric={RUBRIC_VERSION} ({RUBRIC_HASH}) | corpus={corpus['_meta']['corpus_version']} "
          f"| roster={ROSTER[0]['name']!r} ({len(ROSTER[0]['tickers'])} members, "
          f"run_date={ROSTER[0]['run_date']})", flush=True)

    results = await run_roster_arm(cases, ROSTER, grade_holistic, client)

    print("\n=== ROSTER_RESULTS_JSON ===")
    print(json.dumps({
        "keys": {"rubric_version": RUBRIC_VERSION, "rubric_hash": RUBRIC_HASH,
                 "catalyst_grade_prompt_version": CATALYST_GRADE_PROMPT_VERSION,
                 "judge_model": _JUDGE_MODEL_DEFAULT,
                 "corpus_version": corpus["_meta"]["corpus_version"],
                 "corpus_sha1": __import__("hashlib").sha1(open(corpus_path, "rb").read()).hexdigest()[:12]},
        "roster": ROSTER,
        "results": results,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
