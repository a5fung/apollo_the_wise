#!/usr/bin/env python3
"""Stop-hook gate on the REPORT FORMAT rule in CLAUDE.md (operator, asked 6x across many days).

WHY THIS IS A SCRIPT AND NOT A REMINDER
The rule already lives in the two places that were supposed to hold it — a memory
(`report-like-an-exec-summary`) and CLAUDE.md's always-loaded surface — and it drifted again
inside a single session on 2026-08-02. That is the same lesson this repo already learned about
PLAN.md, the burndown count, and verify-live: *every prose-discipline reconcile here has failed;
only gates hold.* So the rule gets a gate, in the same shape as `check_plan.py` — a script plus a
hook, not another sentence asking for better behaviour.

WHAT IT CHECKS — exactly ONE thing
A PROSE PARAGRAPH outside a bullet. CLAUDE.md names this precisely: *"a bolded lead-in followed by
3 sentences is still a paragraph, and is the exact drift that keeps recurring."*

Deliberately narrow. A guard that always fires is not a guard (the 2026-08-01 transitive-import
lesson), and a broad style checker would fire on ordinary answers and get switched off within a
week. Bullets are free-form; only unbulleted multi-sentence blocks trip it.

NOT CHECKED, on purpose: the "action always stated" rule and the "header carries substance" rule.
Both are semantic, both would misfire on a plain answer to a plain question, and a gate that cries
wolf is worse than no gate. This one is objectively decidable from the text alone.

Exit codes (Claude Code Stop-hook contract): 0 = allow, 2 = block and feed stderr back.
"""
from __future__ import annotations

import json
import os
import re
import sys

# A block must clear BOTH bars to count as prose. Tuned against the 2026-08-02 drift: the offending
# lines ran 200-260 chars with 3 sentences each; a legitimate one-line header or a short standalone
# sentence sits well under.
_MIN_CHARS = 150
_MIN_SENTENCES = 2

# Message shorter than this is a reply, not a report — the format rule is about progress reports
# and summaries, and gating a two-line answer would be exactly the over-firing this avoids.
_MIN_MESSAGE_CHARS = 400

_SENTENCE_END = re.compile(r"[.!?](?:\*\*|\*|`|\)|\"|')?(?:\s|$)")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)]|>)\s")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_TABLE = re.compile(r"^\s*\|")


def prose_blocks(text: str) -> list[str]:
    """Unbulleted blocks carrying >= _MIN_SENTENCES sentences and >= _MIN_CHARS characters."""
    out, in_fence = [], False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        if _BULLET.match(line) or _HEADING.match(line) or _TABLE.match(line):
            continue
        if len(line) >= _MIN_CHARS and len(_SENTENCE_END.findall(line)) >= _MIN_SENTENCES:
            out.append(line)
    return out


def last_assistant_text(transcript_path: str) -> str:
    """The final assistant message in the transcript — the thing the operator is about to read.

    Tolerant by construction: an unreadable or unfamiliar transcript returns "", which lets the
    turn through. A formatting gate must never be able to wedge a session."""
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    for raw in reversed(lines):
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [c.get("text", "") for c in content
                     if isinstance(c, dict) and c.get("type") == "text"]
            if any(p.strip() for p in parts):
                return "\n".join(parts)
    return ""


def complaint(blocks: list[str]) -> str:
    shown = "\n".join(f"    {b[:110]}{'...' if len(b) > 110 else ''}" for b in blocks[:3])
    return (
        "REPORT FORMAT GATE — the message has "
        f"{len(blocks)} prose paragraph(s) outside a bullet:\n{shown}\n\n"
        "CLAUDE.md, asked by the operator 6x: bullets, titled blocks, ONE LINE PER BULLET. "
        "A bolded lead-in followed by 2-3 sentences IS a paragraph — that is the exact drift.\n"
        "Rewrite: every idea becomes its own bullet; reasoning and caveats go to the commit, "
        "PLAN.md or the SSoT, not the message; state the action explicitly, including \"none\"."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0                       # no payload -> nothing to judge; never wedge the session
    if payload.get("stop_hook_active"):
        return 0                       # already re-entered from this gate; one block per turn
    if os.environ.get("REPORT_FORMAT_GATE") == "off":
        return 0
    text = last_assistant_text(payload.get("transcript_path", ""))
    if len(text) < _MIN_MESSAGE_CHARS:
        return 0
    blocks = prose_blocks(text)
    if not blocks:
        return 0
    print(complaint(blocks), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
