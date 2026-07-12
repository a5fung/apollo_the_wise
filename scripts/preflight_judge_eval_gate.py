"""Preflight [5m/7] — the grade-quality regression gate (ADR 0030 §4).

Runs on the HOST (stdlib-only, ast — the [5l/7] pattern; no container, no imports of app code).
FAILS the deploy iff the LIVE grade-surface keys differ from the last PASSING eval record:

  rubric_version + RUBRIC_HASH   (ast-extracted from ep_grade_judge.py; the hash is recomputed
                                  from the _RUBRIC text, so ANY edit — signed or accidental —
                                  changes it, exactly like the module's own sha1)
  catalyst_grade_prompt_version  (ep_detector.py)
  judge_model                    (shared/llm_models.py, one-hop alias resolved)
  corpus_sha1                    (content hash of the corpus file — label-only edits can't dodge)

Record: scripts/evals/judge_eval_pass_record.json (written from a passing
scripts/evals/run_judge_robustness_eval.py run). `pass` must be true. An operator-signed
`waiver: "<reason> <date>"` lets an emergency deploy through — printed LOUDLY.

Fix a failure by re-running the eval (and getting it green), not by editing the record.
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECORD = REPO / "scripts" / "evals" / "judge_eval_pass_record.json"
CORPUS = REPO / "scripts" / "evals" / "judge_robustness_corpus_v1.json"
JUDGE_SRC = REPO / "agents" / "market_intelligence" / "ep_grade_judge.py"
DETECTOR_SRC = REPO / "agents" / "market_intelligence" / "ep_detector.py"
MODELS_SRC = REPO / "shared" / "llm_models.py"


def _module_consts(path: Path) -> dict:
    """Top-level `NAME = <literal or Name>` assignments in a module, via ast (no import)."""
    out: dict = {}
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if isinstance(node.value, ast.Constant):
                out[name] = node.value.value
            elif isinstance(node.value, ast.Name):
                out[name] = ("__alias__", node.value.id)
    # one-hop alias resolution (JUDGE_MODEL = OPUS; OPUS = "claude-...")
    for k, v in list(out.items()):
        if isinstance(v, tuple) and v[0] == "__alias__":
            out[k] = out.get(v[1])
    return out


def extract_live_keys(judge_src: Path = JUDGE_SRC, detector_src: Path = DETECTOR_SRC,
                      models_src: Path = MODELS_SRC, corpus: Path = CORPUS) -> dict:
    judge = _module_consts(judge_src)
    rubric_text = judge.get("_RUBRIC")
    if not isinstance(rubric_text, str):
        raise RuntimeError("could not ast-extract _RUBRIC from ep_grade_judge.py")
    return {
        "rubric_version": judge.get("RUBRIC_VERSION"),
        # recompute exactly as the module does: sha1(_RUBRIC)[:8]
        "rubric_hash": hashlib.sha1(rubric_text.encode("utf-8")).hexdigest()[:8],
        "catalyst_grade_prompt_version": _module_consts(detector_src).get("CATALYST_GRADE_PROMPT_VERSION"),
        "judge_model": _module_consts(models_src).get("JUDGE_MODEL"),
        "corpus_sha1": hashlib.sha1(corpus.read_bytes()).hexdigest()[:12],
    }


def check(record: "dict | None", live: dict) -> tuple[bool, list[str]]:
    """(ok, messages). Missing record / pass!=true / any key mismatch → FAIL (unless waiver)."""
    msgs: list[str] = []
    if record is None:
        return False, ["no pass record (scripts/evals/judge_eval_pass_record.json missing) — "
                       "run the judge robustness eval first"]
    waiver = record.get("waiver")
    mismatches = [f"  {k}: record={record.get(k)!r} live={live[k]!r}"
                  for k in live if record.get(k) != live[k]]
    if not record.get("pass"):
        mismatches.insert(0, "  record.pass is not true — the last eval run FAILED")
    if mismatches:
        if waiver:
            msgs.append("⚠️  JUDGE-EVAL GATE WAIVED (operator-signed) — deploying UNGRADED grade-surface changes:")
            msgs.append(f"⚠️  waiver: {waiver}")
            msgs.extend(mismatches)
            return True, msgs
        msgs.append("grade surface changed since the last passing eval:")
        msgs.extend(mismatches)
        msgs.append("run: the judge robustness eval (scripts/evals/run_judge_robustness_eval.py "
                    "on prod) → green → regenerate the pass record. Do NOT hand-edit the record.")
        return False, msgs
    msgs.append(f"grade surface unchanged since the passing eval of {record.get('run_at')} "
                f"(rubric {live['rubric_version']}/{live['rubric_hash']} · model {live['judge_model']} "
                f"· corpus {live['corpus_sha1']}).")
    return True, msgs


def main() -> int:
    record = json.loads(RECORD.read_text()) if RECORD.exists() else None
    live = extract_live_keys()
    ok, msgs = check(record, live)
    for m in msgs:
        print(m)
    print(f"Judge-eval regression gate — {'OK' if ok else 'FAIL'}.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
