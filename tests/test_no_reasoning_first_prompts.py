"""No prompt may tell the model to write its reasoning out before answering (2026-09-29).

claude-sonnet-5-5 answers such prompts with stop_reason "refusal" — the 09-29 assignment pass,
every parent check and every EP theme-fit check failed on it. Measured on the production
prompts: "Reason FIRST:" / "Fill analysis_scratchpad FIRST" refused 100%; the same prompts
worded as "Brief notes:" answered 5 of 5. Only the always-loaded surface of a prompt is its
string literals, so this walks every string constant in the code that builds prompts.

PENDING lists the prompts still carrying the wording, each with why. They run on a pinned
model (shared/llm_models._ROLE_OVERRIDES) until the pending decision lands; a new entry needs
the same.
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


def test_no_prompt_asks_for_reasoning_first():
    offenders = {f: v for f, v in _prompt_hits().items() if f not in PENDING}
    assert not offenders, (
        f"prompt text tells the model to reason first — sonnet-5-5 refuses it: {offenders}. "
        "Word the field as brief notes, or drop it (the model reasons in its own thinking).")


def test_pending_entries_are_still_real():
    hits = _prompt_hits()
    stale = [f for f in PENDING if f not in hits]
    assert not stale, f"no longer carries the wording — remove from PENDING (and its model pin): {stale}"
