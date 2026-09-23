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

── The ENVELOPE fingerprint (#547, PLAN.md, operator-ruled 2026-08-13) ──────────────────────
The keys `extract_live_keys()` returns above are the grade SURFACE (rubric/model/corpus) and
are the ONLY inputs that may ever trigger the paid eval re-run — that stays exactly as it is
above, unchanged. The judge's call ENVELOPE (`max_tokens`, the live `timeout`, `tool_choice`,
and the transport's fail-open rules) can *also* move live grades — #543 (2026-08-07) proved it:
raising `max_tokens` 500->1500 and adding the truncated-verdict fail-open changed 7 of 49 live
verdicts, and this gate printed "grade surface unchanged" through the whole thing because none
of it touches the rubric.

The operator's ruling (verbatim): *"these type of fixes shouldn't cause a rerun"* — folding the
envelope into the trigger keys above would force a paid $3.49 eval on every ceiling tweak
(measured: up to three reruns on 08-07 alone), which is exactly the cost class the 08-03 rule
forbids and the predictable result is people avoiding ceiling fixes to dodge the eval. So the
envelope is a SEPARATE, ADDITIVE signal: `extract_envelope_keys()` / `check_envelope()` below
are wholly independent of `extract_live_keys()` / `check()` above — a mismatch here FLAGS
LOUDLY (stdout + an `mi_audit_log` row relayed by `deploy.sh` via
`scripts/log_judge_envelope_change.py`, since this script itself has no DB access by design)
but NEVER changes `main()`'s exit code and NEVER touches the eval-rerun record. An envelope
extraction failure (a genuine refactor of the call sites this reads) is loud on its own terms
too — caught, printed as its own `UNREADABLE` line — and likewise never turns into exit-17
"re-run the eval" (a code-motion refactor is not a grade-surface change).

Its baseline lives in the SAME record file, nested under the `"envelope"` key — matching the
existing gate's one-store mechanism rather than inventing a second. Envelope keys ARE
hand-seedable (unlike the eval-derived keys above): they are cost-free static reads, not eval
outputs, so seeding/updating `record["envelope"]` after a reviewed envelope change is the
normal, expected flow — "do NOT hand-edit the record" above refers only to the eval-derived
keys. ⚠ Whoever regenerates the top-level record from a fresh eval run (today a hand/agent
step — no code in this repo writes this file) MUST carry the existing `"envelope"` section
forward rather than dropping it; an accidentally-omitted section degrades safely (this gate
reads it as UNVERIFIED, never as a false "unchanged"), but loses detection until re-seeded.
"""
import ast
import hashlib
import io
import json
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECORD = REPO / "scripts" / "evals" / "judge_eval_pass_record.json"
CORPUS = REPO / "scripts" / "evals" / "judge_robustness_corpus_v1.json"
JUDGE_SRC = REPO / "agents" / "market_intelligence" / "ep_grade_judge.py"
DETECTOR_SRC = REPO / "agents" / "market_intelligence" / "ep_detector.py"
MODELS_SRC = REPO / "shared" / "llm_models.py"
CEILINGS_SRC = REPO / "shared" / "output_ceilings.py"
TRANSPORT_SRC = REPO / "agents" / "market_intelligence" / "judge_transport.py"


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
            elif (isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Name)
                  and node.value.func.id == "effective_model"
                  and node.value.args
                  and isinstance(node.value.args[0], ast.Constant)):
                # 2026-08-06: role constants now bind to the RESOLVER
                # (`JUDGE_MODEL = effective_model("JUDGE_MODEL")`), because binding them to the
                # raw tier pin meant every caller imported a stale model while the resolver
                # reported the new one — 28 of that day's 34 Sonnet calls ran on sonnet-4-6 a
                # week after "everything is updated". This gate reads SOURCE, never imports, so
                # it cannot ask the resolver; it records the ROLE and the tier's fallback pin.
                # That is the honest thing to hash on: the gate's job is detecting a change to
                # the grade surface, and a resolver-driven model change IS such a change — it
                # must still trip the eval gate, exactly as a hand-edited pin did.
                out[name] = ("__role__", node.value.args[0].value)
    # one-hop alias resolution (JUDGE_MODEL = OPUS; OPUS = "claude-...")
    for k, v in list(out.items()):
        if isinstance(v, tuple) and v[0] == "__alias__":
            out[k] = out.get(v[1])
    # resolver-bound roles: report the tier's fallback pin, which is what a source-only reader
    # can honestly know. RESOLVED_ROLES maps role -> tier; the tier's *_PIN holds the literal.
    roles_to_tier = _resolved_roles_map(tree)
    for k, v in list(out.items()):
        if isinstance(v, tuple) and v[0] == "__role__":
            tier = roles_to_tier.get(v[1])
            out[k] = out.get(f"{tier.upper()}_PIN") if tier else None
    return out


def _resolved_roles_map(tree) -> dict:
    """RESOLVED_ROLES as {role: tier}, read from source without importing."""
    for node in tree.body:
        # ⚠ RESOLVED_ROLES is an ANNOTATED assignment (`RESOLVED_ROLES: dict[str, str] = {...}`),
        # which ast models as AnnAssign, NOT Assign. Handling only Assign silently returned {},
        # which made every resolver-bound role read as None — a SILENT blinding of this gate,
        # the same shape as the bug the gate change is fixing. Both node types, deliberately.
        tgt = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            tgt = node.target
        if (tgt is not None and isinstance(tgt, ast.Name) and tgt.id == "RESOLVED_ROLES"
                and isinstance(node.value, ast.Dict)):
            return {k.value: v.value for k, v in zip(node.value.keys, node.value.values)
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
    return {}


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


def _assign_target_name(node) -> "str | None":
    """Name bound by `node`, whether a plain `ast.Assign` or an annotated `ast.AnnAssign`.
    A reader that only handles `Assign` goes silently blind on an annotated binding — that
    exact shape (`RESOLVED_ROLES: dict[str, str] = {...}`) already blinded this gate once
    (see `_resolved_roles_map` above); `CEILINGS: dict[str, OutputCeiling] = {...}` below is
    the same shape, so both node types are handled here from the start."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _extract_ceiling_max_tokens(ceilings_src: Path = CEILINGS_SRC, key: str = "ep_grade_judge") -> int:
    """The registered `max_tokens` for `key` in shared/output_ceilings.py's CEILINGS registry —
    ast-only, no import (mirrors what `max_tokens_for(key)` returns at runtime, without running
    it). Two passes: (1) collect every top-level `NAME = OutputCeiling(<int>, ...)` binding;
    (2) resolve `CEILINGS[key]`'s value node against that map, following either a bare `Name`
    reference (`"ep_grade_judge": _JUDGE`) or a `<base>._replace(...)` call (an explicit
    `max_tokens=` kwarg there wins; otherwise it inherits the base's value, matching
    `NamedTuple._replace`'s real semantics). Raises — never silently returns a wrong number —
    if the shape doesn't resolve, exactly like the rubric extractor above."""
    tree = ast.parse(ceilings_src.read_text())
    bindings: dict[str, int] = {}
    ceilings_dict: "ast.Dict | None" = None
    for node in tree.body:
        name = _assign_target_name(node)
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if name == "CEILINGS" and isinstance(value, ast.Dict):
            ceilings_dict = value
            continue
        if (name and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name) and value.func.id == "OutputCeiling"
                and value.args and isinstance(value.args[0], ast.Constant)):
            bindings[name] = value.args[0].value
    if ceilings_dict is None:
        raise RuntimeError(f"could not ast-extract CEILINGS dict from {ceilings_src}")
    for k_node, v_node in zip(ceilings_dict.keys, ceilings_dict.values):
        if not (isinstance(k_node, ast.Constant) and k_node.value == key):
            continue
        if isinstance(v_node, ast.Name) and v_node.id in bindings:
            return bindings[v_node.id]
        if isinstance(v_node, ast.Call):
            if (isinstance(v_node.func, ast.Name) and v_node.func.id == "OutputCeiling"
                    and v_node.args and isinstance(v_node.args[0], ast.Constant)):
                return v_node.args[0].value
            if (isinstance(v_node.func, ast.Attribute) and v_node.func.attr == "_replace"
                    and isinstance(v_node.func.value, ast.Name)):
                for kw in v_node.keywords:
                    if kw.arg == "max_tokens" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
                base = v_node.func.value.id
                if base in bindings:
                    return bindings[base]
        raise RuntimeError(f"could not resolve max_tokens for CEILINGS[{key!r}] in {ceilings_src}")
    raise RuntimeError(f"CEILINGS[{key!r}] not found in {ceilings_src}")


def _extract_live_timeout(detector_src: Path = DETECTOR_SRC,
                          log_caller: str = "ep_grade_judge") -> "int | float":
    """The `timeout=` kwarg at the ONE `grade_holistic(...)` call site carrying
    `log_caller="ep_grade_judge"` — the live 9:45 grade path in ep_detector.py. Other call
    sites (chart_axis.py's shadow, judge_divergence.py) run different timeouts on purpose;
    they are not the live grade surface this gate watches, exactly like `extract_live_keys()`
    above only ever reads the live rubric/model, never an eval-only variant.

    Matches on the `log_caller` literal (not a line number) so a benign reformat can't blind
    it — but an ACTUAL refactor (kwarg renamed, call moved behind a helper, log_caller no
    longer a literal) must raise, never go quiet: a `.get()`-shaped reader here would recreate
    the exact defect class #547 exists to close, just one file over."""
    tree = ast.parse(detector_src.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None)
        if fname != "grade_holistic":
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        lc = kwargs.get("log_caller")
        if isinstance(lc, ast.Constant) and lc.value == log_caller:
            timeout_node = kwargs.get("timeout")
            if isinstance(timeout_node, ast.Constant) and isinstance(timeout_node.value, (int, float)):
                return timeout_node.value
            raise RuntimeError(
                f"grade_holistic(log_caller={log_caller!r}) call site found in {detector_src} "
                "but its `timeout=` is not a literal constant")
    raise RuntimeError(
        f"no grade_holistic(log_caller={log_caller!r}) call site found in {detector_src} — "
        "the live grade path may have moved or been refactored")


def _invoke_forced_tool_def(transport_src: Path) -> ast.AsyncFunctionDef:
    tree = ast.parse(transport_src.read_text())
    outer = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "invoke_forced_tool"), None)
    if outer is None:
        raise RuntimeError(f"could not find invoke_forced_tool in {transport_src}")
    return outer


def _extract_tool_choice_type(transport_src: Path = TRANSPORT_SRC) -> str:
    """The literal `"type"` forced onto every judge call's `tool_choice` dict, inside
    `invoke_forced_tool._call()` (judge_transport.py). `"tool"` forces a schema-valid object
    (ADR 0011's locked-output-schema guarantee); `"auto"`/`"any"` would let the model skip the
    tool and return free text the normalizer can't parse. Shared by every `grade_holistic()`
    caller (live + shadow + eval) through this one transport, so one read covers the class."""
    outer = _invoke_forced_tool_def(transport_src)
    for node in ast.walk(outer):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "kwargs"
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "dict"):
            continue
        for kw in node.value.keywords:
            if kw.arg == "tool_choice" and isinstance(kw.value, ast.Dict):
                for k_node, v_node in zip(kw.value.keys, kw.value.values):
                    if (isinstance(k_node, ast.Constant) and k_node.value == "type"
                            and isinstance(v_node, ast.Constant)):
                        return v_node.value
    raise RuntimeError(f"could not ast-extract tool_choice['type'] from {transport_src}")


# Token types whose exact text is dropped from the hash input — only their PRESENCE (and, for
# INDENT/DEDENT, their position in the stream) matters. NEWLINE's string varies ('\n' vs '' at
# EOF) for reasons that have nothing to do with the code; INDENT/DEDENT's string is the literal
# whitespace of that line, and hashing it would make the hash sensitive to spaces-vs-tabs style
# even though the block's *nesting* (what actually changes behavior) is unchanged. Recording
# only the token TYPE for these keeps block structure — moving a statement in or out of the
# `if`/`except` — hash-sensitive, while indentation *style* stays hash-insensitive.
_FAIL_OPEN_STRUCTURAL_ONLY = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
# Token types dropped entirely: comments, blank-line markers, the tokenizer's own bookkeeping.
_FAIL_OPEN_SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER}


def _normalize_source_tokens(source_segment: str) -> str:
    """Canonical, reformat-insensitive text of a source snippet, built via the stdlib `tokenize`
    module (never a regex) so a `#` or blank line *inside a string literal* is never mistaken
    for an actual comment or blank line. Comments, blank lines, and trailing whitespace never
    reach the token stream in the first place (tokenize consumes them without emitting a
    meaningful token), so they fall out for free; INDENT/DEDENT/NEWLINE tokens are kept for
    their type only (see `_FAIL_OPEN_STRUCTURAL_ONLY` above)."""
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(source_segment).readline):
        if tok.type in _FAIL_OPEN_SKIP:
            continue
        if tok.type in _FAIL_OPEN_STRUCTURAL_ONLY:
            out.append(tokenize.tok_name[tok.type])
        else:
            out.append(f"{tokenize.tok_name[tok.type]}:{tok.string}")
    return "\n".join(out)


def _extract_fail_open_hash(transport_src: Path = TRANSPORT_SRC) -> str:
    """Structural hash of `invoke_forced_tool`'s top-level try/except — the truncation check
    (`is_truncated(resp)` -> discard -> None, #543) and the exception handler (#273
    credit-exhaustion alert -> None).

    Hashes the block's NORMALISED SOURCE TEXT (`_normalize_source_tokens`, via `tokenize`), not
    `ast.dump()`. AST is still used to LOCATE the block (`_invoke_forced_tool_def` above) —
    that part was always fine. But `ast.dump()`'s *string representation* of a parsed tree is
    not a stable, version-independent format: on the first real deploy of this gate (#547), the
    exact same commit (byte-identical `judge_transport.py`, md5-verified) hashed to two
    different values purely because the seeding machine ran Python 3.14 and the deploy server
    ran Python 3.12 — no code changed. `tokenize`'s token stream for unchanged code is stable
    across those versions (unlike `ast.dump`'s repr), which is why this hash is computed from
    it instead. A comment or whitespace edit does not move this hash (hashing raw source text
    verbatim would cry wolf on every one of the many comments in this block); any real change to
    the control flow, a literal, or a name inside it does move it — see
    `tests/test_preflight_judge_eval_gate.py`'s reformat/logic-change/cross-version-stability
    tests for the pinned proof."""
    outer = _invoke_forced_tool_def(transport_src)
    try_node = next((n for n in outer.body if isinstance(n, ast.Try)), None)
    if try_node is None:
        raise RuntimeError(f"invoke_forced_tool in {transport_src} has no top-level try/except")
    source = transport_src.read_text()
    # padded=True keeps the block's original column offsets so tokenize's INDENT/DEDENT
    # bookkeeping (which tracks absolute indentation) doesn't desync partway through — without
    # it, the first line ("try:") loses its leading whitespace while the rest of the block keeps
    # its original indentation, and the `except` line's dedent no longer matches any indent
    # level tokenize saw, raising IndentationError.
    segment = ast.get_source_segment(source, try_node, padded=True)
    if segment is None:
        raise RuntimeError(f"could not extract source segment for the try/except in {transport_src}")
    normalized = _normalize_source_tokens(segment)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def extract_envelope_keys(
    ceilings_src: Path = CEILINGS_SRC,
    detector_src: Path = DETECTOR_SRC,
    transport_src: Path = TRANSPORT_SRC,
) -> dict:
    """The call-ENVELOPE fingerprint (#547): max_tokens / the live timeout / tool_choice / the
    transport's fail-open rules. Deliberately a wholly separate dict from `extract_live_keys()`
    — see the module docstring's ENVELOPE section for why that separation is structural, not a
    convention someone can accidentally erode by merging the two."""
    return {
        "max_tokens": _extract_ceiling_max_tokens(ceilings_src),
        "timeout": _extract_live_timeout(detector_src),
        "tool_choice_type": _extract_tool_choice_type(transport_src),
        "fail_open_hash": _extract_fail_open_hash(transport_src),
    }


_ENVELOPE_LABELS = {
    "max_tokens": "max_tokens",
    "timeout": "timeout (live grade path, ep_detector.py)",
    "tool_choice_type": "tool_choice type (judge_transport.py)",
    "fail_open_hash": "transport fail-open logic hash (judge_transport.py)",
}


def check_envelope(baseline: "dict | None", live: dict) -> tuple[bool, list[str]]:
    """(changed, messages) for the envelope signal ONLY. Structurally independent of `check()`:
    nothing returned here may ever flip `main()`'s exit code or the eval-rerun trigger — that
    independence is what the operator's 2026-08-13 ruling requires, and it holds because this
    function never touches `record`'s top-level keys, only `record.get("envelope")`.

    `baseline is None` (record missing, or present with no `"envelope"` key yet) is its OWN
    third state — UNVERIFIED, not "unchanged" — so an unseeded gate reads as exactly that
    instead of silently passing forever (the #173 "looks armed, isn't" class)."""
    if baseline is None:
        return False, [
            "envelope baseline missing (judge_eval_pass_record.json has no 'envelope' section) "
            "— cannot compare; this reads as UNVERIFIED, not unchanged. Seed it once with "
            "extract_envelope_keys()'s current output.",
        ]
    diffs = [(k, baseline.get(k), live[k]) for k in live if baseline.get(k) != live[k]]
    if not diffs:
        return False, [
            "judge call envelope unchanged (max_tokens / timeout / tool_choice / fail-open "
            "logic all match the recorded baseline).",
        ]
    msgs = [
        "⚠️  JUDGE CALL ENVELOPE CHANGED since the recorded baseline. This does NOT trigger the "
        "paid eval (separate signal by design — operator-ruled 2026-08-13, PLAN.md #547 / "
        "ADR 0030) — review the change on its own merits:",
    ]
    for k, old, new in diffs:
        msgs.append(f"  {_ENVELOPE_LABELS.get(k, k)}: {old!r} -> {new!r}")
    return True, msgs


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


def _envelope_audit_payload(baseline: "dict | None", live: dict) -> dict:
    """`{event_type, summary, detail}` for `log_judge_envelope_change.py` to relay into
    `mi_audit_log` — named-diff detail (`key: old -> new`), never a bare hash dump."""
    baseline = baseline or {}
    diffs = [(k, baseline.get(k), live[k]) for k in live if baseline.get(k) != live[k]]
    detail = "; ".join(f"{_ENVELOPE_LABELS.get(k, k)}: {old!r} -> {new!r}" for k, old, new in diffs)
    return {
        "event_type": "judge_envelope_changed",
        "summary": "judge call envelope changed at deploy (#547 / ADR 0030) — see detail",
        "detail": detail[:8000],
    }


def main() -> int:
    record = json.loads(RECORD.read_text()) if RECORD.exists() else None
    baseline_env = record.get("envelope") if record else None

    # `--envelope-audit-json`: a second, cheap (<1s, no network) invocation deploy.sh makes to
    # get a payload it can relay into mi_audit_log via the in-container companion script — this
    # script itself stays host-side/no-DB by design (see [5l/7]'s pattern), so it cannot write
    # the audit row directly. Prints ONE line of JSON iff the envelope moved; nothing otherwise
    # — including on an extraction failure, which is loud on the human path below instead.
    if "--envelope-audit-json" in sys.argv:
        try:
            live_env = extract_envelope_keys()
        except Exception:
            return 0
        env_changed, _ = check_envelope(baseline_env, live_env)
        if env_changed:
            print(json.dumps(_envelope_audit_payload(baseline_env, live_env)))
        return 0

    # The rerun-trigger check runs and its verdict is fixed FIRST, unconditionally — an
    # envelope-extraction failure below must NEVER pre-empt this or change `ok`. Letting an
    # uncaught exception here abort the script would exit non-zero, and deploy.sh reads any
    # non-zero exit as "grade surface changed, re-run the eval" — exactly the coupling the
    # operator's 2026-08-13 ruling forbids, arriving through the error path instead of the
    # trigger keys. A code-motion refactor of a call site is not a grade-surface change.
    live = extract_live_keys()
    ok, msgs = check(record, live)

    try:
        live_env = extract_envelope_keys()
        env_changed, env_msgs = check_envelope(baseline_env, live_env)
    except Exception as e:
        env_changed, env_msgs = False, [
            f"envelope fingerprint UNREADABLE ({e}) — cannot compare this run. Likely a "
            "refactor of the call sites this reads, not a grade-surface change; does not "
            "affect the verdict above and does not trigger the eval.",
        ]

    # Ordering: when the envelope moved, that is the finding a skim should land on FIRST —
    # printing it after the (unrelated, still-passing) rubric line would recreate the 08-07
    # shape in miniature, where the real finding sat three lines below "unchanged".
    ordered_msgs = (env_msgs + msgs) if env_changed else (msgs + env_msgs)
    for m in ordered_msgs:
        print(m)

    state = "OK (no eval rerun required)" if ok else "FAIL"
    if env_changed:
        state += " · ENVELOPE CHANGED (see above)"
    print(f"Judge-eval regression gate — {state}.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
