"""No prompt may tell the model to write its reasoning out before answering (2026-09-29).

claude-sonnet-5-5 answers such prompts with stop_reason "refusal" — the 09-29 assignment pass,
every parent check and every EP theme-fit check failed on it. Measured on the production
prompts: "Reason FIRST:" / "Fill analysis_scratchpad FIRST" refused 100%; the same prompts
worded as "Brief notes:" answered 5 of 5. Only the always-loaded surface of a prompt is its
string literals, so this walks every string constant in the code that builds prompts.

TWO shapes are guarded, because the second one hides from the first (#693, 2026-10-02):

  1. WORDING — a prompt string that says "reason first" / "scratchpad first" (BANNED, PENDING).
  2. SHAPE — a tool whose REQUIRED scratchpad field comes BEFORE the answer fields. Its prompt can
     say "brief notes" and still ask the model to write notes before it decides: the containment
     adjudicator and the synthesis tool did exactly that and passed only by luck of the sample
     (6 of 6 pairs on 10-01; a refusal is random, one night proves nothing). The notes go AFTER
     the verdict, in the property order AND in `required` (SCRATCHPAD_FIRST_PENDING).

PENDING / SCRATCHPAD_FIRST_PENDING list what still carries the shape, each with why. A new entry
needs the same.
"""
from __future__ import annotations

import ast
import pathlib
import re

ROOTS = ("agents", "shared", "core", "channels")
BANNED = re.compile(
    r"reason(ing)?\s+(first|step.by.step)|step.by.step\s+reasoning|think\s+step.by.step"
    r"|scratchpad`?\s+first|required\s+first",
    re.I)
# file -> the banned phrases still allowed there, and why.
PENDING = {
    "agents/market_intelligence/theme_merge_arm.py": (
        "the MERGE adjudicator only (the containment one is reworded): it runs on Haiku, which "
        "answers it, and its prompt is pinned by a corpus eval (test_theme_merge_corpus_gate) — "
        "reword it with a re-run of that eval before Haiku's tier advances"),
}
# tool name -> why its required scratchpad may still precede the answer fields.
SCRATCHPAD_FIRST_PENDING = {
    "adjudicate_theme_merge": (
        "the MERGE adjudicator (Haiku, Arm B): its prompt text and schema are pinned by "
        "test_theme_merge_corpus_gate's corpus eval — reorder with a re-run of that eval, together "
        "with the PENDING wording above"),
    "assign_theme_ecosystem": (
        "ecosystem assignment runs on Haiku (ECOSYSTEM_ASSIGN_MODEL), which answers it; its prompt "
        "is already worded as brief notes — reorder when Haiku's tier advances"),
    "propose_ecosystem": (
        "FOUND 2026-10-02 (#693), NOT fixed there: the weekly ecosystem proposer runs on the "
        "SYNTHESIS_MODEL tier (Sonnet) with a required scratchpad before `decision` — the same "
        "shape the containment and synthesis tools just lost. Operator's call whether to move it "
        "now; remove this entry when the notes go after `decision`"),
}
SCRATCHPAD_WORD = "scratchpad"


def _prompt_hits() -> dict[str, list[str]]:
    """String constants that are not docstrings (a docstring is never sent to a model)."""
    out: dict[str, list[str]] = {}
    for root in ROOTS:
        for path in pathlib.Path(root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docs = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    body = getattr(node, "body", [])
                    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                        docs.add(id(body[0].value))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    m = BANNED.search(node.value)
                    if m:
                        out.setdefault(str(path), []).append(m.group(0))
    return out


def _const_keys(node: ast.AST) -> list[str]:
    """The string-literal keys of a dict literal, in source order."""
    if not isinstance(node, ast.Dict):
        return []
    return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def _dict_value(node: ast.Dict, key: str):
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


def scratchpad_first_tools(source: str) -> list[str]:
    """Names of the tools in `source` whose REQUIRED scratchpad field precedes another required
    field — in `required`, or in the property order. Reads dict literals only: a tool built at
    run time is not seen (every production tool here is a literal)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        schema = _dict_value(node, "input_schema")
        name = _dict_value(node, "name")
        if not isinstance(schema, ast.Dict) or not isinstance(name, ast.Constant):
            continue
        props = _const_keys(_dict_value(schema, "properties"))
        req_node = _dict_value(schema, "required")
        required = [e.value for e in req_node.elts if isinstance(e, ast.Constant)] \
            if isinstance(req_node, (ast.List, ast.Tuple)) else []
        pads = [r for r in required if SCRATCHPAD_WORD in str(r)]
        others = [r for r in required if SCRATCHPAD_WORD not in str(r)]
        if not pads or not others:
            continue
        pad = pads[0]
        first_in_required = required.index(pad) < max(required.index(o) for o in others)
        in_props = [p for p in props if p == pad or p in others]
        first_in_props = bool(in_props) and in_props[0] == pad and any(o in props for o in others)
        if first_in_required or first_in_props:
            found.append(str(name.value))
    return found


def _scratchpad_first_in_repo() -> dict[str, str]:
    """tool name -> file, for every production tool whose required scratchpad precedes its answer."""
    out: dict[str, str] = {}
    for root in ROOTS:
        for path in pathlib.Path(root).rglob("*.py"):
            for name in scratchpad_first_tools(path.read_text(encoding="utf-8")):
                out[name] = str(path)
    return out


def test_no_prompt_asks_for_reasoning_first():
    offenders = {f: v for f, v in _prompt_hits().items() if f not in PENDING}
    assert not offenders, (
        f"prompt text tells the model to reason first — sonnet-5-5 refuses it: {offenders}. "
        "Word the field as brief notes, or drop it (the model reasons in its own thinking).")


def test_pending_entries_are_still_real():
    hits = _prompt_hits()
    stale = [f for f in PENDING if f not in hits]
    assert not stale, f"no longer carries the wording — remove from PENDING (and its model pin): {stale}"


def test_no_tool_requires_its_scratchpad_before_the_answer():
    """The notes go AFTER the verdict — in the property order AND in `required`. A tool that
    needs a scratchpad written before it may decide is the shape sonnet-5-5 can refuse as
    "reasoning_extraction", whatever its prompt says (#693: containment + synthesis fixed)."""
    offenders = {n: f for n, f in _scratchpad_first_in_repo().items() if n not in SCRATCHPAD_FIRST_PENDING}
    assert not offenders, (
        f"required scratchpad precedes the answer fields: {offenders}. Put the verdict fields "
        "first and the notes last, in both `properties` and `required`.")


def test_scratchpad_first_pending_entries_are_still_real():
    stale = [n for n in SCRATCHPAD_FIRST_PENDING if n not in _scratchpad_first_in_repo()]
    assert not stale, f"no longer scratchpad-first — remove from SCRATCHPAD_FIRST_PENDING: {stale}"


def test_the_two_fixed_tools_carry_their_notes_after_the_verdict():
    """The tools this guard was extended for (#693) — named, so un-fixing either one is red here
    even if somebody adds it to SCRATCHPAD_FIRST_PENDING."""
    from agents.market_intelligence.theme_merge_arm import CONTAINMENT_ADJUDICATION_TOOL
    from agents.market_intelligence.theme_synthesis import _SYNTHESIS_TOOL
    for tool, answer in ((CONTAINMENT_ADJUDICATION_TOOL, "verdict"), (_SYNTHESIS_TOOL, "cohorts")):
        schema = tool["input_schema"]
        assert list(schema["properties"])[0] == answer, tool["name"]
        assert schema["required"][0] == answer, tool["name"]
        assert schema["required"][-1] == "analysis_scratchpad", tool["name"]
        assert list(schema["properties"])[-1] == "analysis_scratchpad", tool["name"]
        assert tool["name"] not in SCRATCHPAD_FIRST_PENDING


def test_the_detector_sees_a_scratchpad_first_tool_and_only_that():
    """The guard has teeth: it flags either order, and ignores a scratchpad that is optional,
    last, or alone."""
    def tool(props, required):
        return (f'T = {{"name": "t", "input_schema": {{"type": "object", '
                f'"properties": {{{", ".join(repr(p) + ": {}" for p in props)}}}, '
                f'"required": {required!r}}}}}')
    assert scratchpad_first_tools(tool(["analysis_scratchpad", "verdict"], ["analysis_scratchpad", "verdict"])) == ["t"]
    # first only in the property order
    assert scratchpad_first_tools(tool(["analysis_scratchpad", "verdict"], ["verdict", "analysis_scratchpad"])) == ["t"]
    # first only in `required`
    assert scratchpad_first_tools(tool(["verdict", "analysis_scratchpad"], ["analysis_scratchpad", "verdict"])) == ["t"]
    assert scratchpad_first_tools(tool(["verdict", "reason", "analysis_scratchpad"],
                                       ["verdict", "reason", "analysis_scratchpad"])) == []
    assert scratchpad_first_tools(tool(["analysis_scratchpad", "verdict"], ["verdict"])) == []    # optional
    assert scratchpad_first_tools(tool(["analysis_scratchpad"], ["analysis_scratchpad"])) == []   # alone
