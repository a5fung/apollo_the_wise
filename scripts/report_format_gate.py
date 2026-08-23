#!/usr/bin/env python3
"""Stop-hook gate on the REPORT FORMAT rule in CLAUDE.md (operator, asked many times across many days).

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
week.

⚠ **Bullets were fully exempt for exactly one day.** On 2026-08-03 the operator said *"you are
reverting back to being too wordy"* — about a message that WAS all bullets, each carrying three
sentences. The exemption was too generous: the drift simply moved inside the bullet. A bullet may
now carry two sentences (claim + the number behind it); three in a long bullet is a paragraph.

NOT CHECKED, on purpose: the "action always stated" rule and the "header carries substance" rule.
Both are semantic, both would misfire on a plain answer to a plain question, and a gate that cries
wolf is worse than no gate. This one is objectively decidable from the text alone.

LENGTH ARM (added 2026-08-09, operator: *"how is this enforced? ... you always end up writing a
book no matter what i tell you not to do it"*) -- the paragraph arm held its one line; the drift
just moved into correctly-formatted bullets, which it does not check at all.

Calibrated against the operator's own transcripts (~/.claude/projects/.../ *.jsonl, six weeks,
1,419 replies actually shown to him), not picked by intuition:
- 25 messages matched a verbosity-complaint keyword search; 14 were genuine (the rest were "too
  much going on" / "way too many commands" -- about decision complexity or feature count, not
  reply length, and excluded).
- Length ALONE does not separate cleanly. The 08-09 anchor ("it's a simple ask ... instead you
  wrote 10 lines", 1,037 chars) sits BELOW the accepted-reply median (1,348 chars) -- a char
  ceiling that catches it fires on over half of history. Chars are not gated here.
- Bullet count does separate, at the number already written into CLAUDE.md rule 7 ("~6 bullets
  ... hard") -- that number is the operator's, not derived from this search. `bullets > 6` catches
  9 of 14 genuine complaints, incl. both named anchors (30606: 13 bullets; 31384: 7 bullets, the
  floor). All 5 misses (0-5 bullets each) already trip prose_blocks() above -- no residual case a
  length arm needs to cover; the paragraph arm already gates them.
- Firing rate, two ways -- both from the same six weeks, almost all of it predating rule 7:
  GROSS 29% of every >=400-char reply has bullets > 6 (369/1,274); but 155 of those already trip
  prose_blocks() and never reach this arm. MARGINAL -- of the 298 replies that actually pass the
  paragraph arm and reach this one -- 72% have bullets > 6 (214/298). That is the real number:
  most "correctly formatted" (no-prose-paragraph) replies in this history are still over the cap.
  Both exceed this repo's own "signal not wallpaper" line (the paragraph arm shipped at 16%).
  Shipped anyway because 6 is the operator's own written cap, not a number to soften for a nicer
  rate -- the size of the number IS the finding: the bullet habit is the default, unenforced,
  everywhere, which is exactly "how is this enforced ... you always end up writing a book" says.
  Expect frequent blocks/rewrites at first; that is the mechanism working, not a defect.
- Known gap, measured not fixed: an enumerated multi-part ask ("1. ... 2. ... 3. ...") legitimately
  earns a multi-bullet answer. 39 negatives opened with numbered items; 4 (10%) also had bullets>6
  in the reply and would now block. Low enough not to build a carve-out for (a carve-out here would
  be a second feature fitted on 14 positives, the same objection that killed the short-ask arm) --
  named here so a future false block on an enumerated ask isn't a surprise.
- A short-ask-only variant (gate tighter when the opening message was a short directive) got the
  gross rate to 16.9% without losing either anchor, but needs turn-boundary state the hook does not
  have at runtime and adds a judgment ("your ask was short") the gate cannot defend under fail-open.
  Not shipped. A chars-only OR arm was also tried and dropped -- zero measured residual case: every
  0-bullet complaint in the corpus already trips the paragraph arm or predates it entirely.

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

# A BULLET may carry a second sentence (claim + the number behind it). Three sentences in a long
# bullet is a paragraph wearing a bullet — the operator caught exactly that on 2026-08-03, one day
# after this gate shipped exempting bullets wholesale. Thresholds MEASURED against 548 report-sized
# messages from that session: 16% would have been blocked at (180 chars, 3 sentences), vs 6% at
# 4 sentences (too loose to catch the drift) — a rate that is signal without becoming wallpaper.
_BULLET_MIN_CHARS = 180
_BULLET_MIN_SENTENCES = 3

_SENTENCE_END = re.compile(r"[.!?](?:\*\*|\*|`|\)|\"|')?(?:\s|$)")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)]|>)\s")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_TABLE = re.compile(r"^\s*\|")

# CLAUDE.md rule 7: 5 bullets is the CEILING, not the target (operator 2026-08-23: "5 bullet
# is max, but that means max when you have a lot to say to, typically one bullet is sufficient,
# sometimes 2-3, but rarely 5 is needed"). Lowered from 6 that day — the cap was being written
# TO. A gate can only catch the ceiling; typical-is-one stays a judgement call. The operator's own
# number -- measured against his transcripts (see module docstring), not re-derived here. Do NOT
# raise this to chase a lower firing rate; that is re-legislating a cap he wrote himself.
_BULLET_CAP = 5


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
        if _HEADING.match(line) or _TABLE.match(line):
            continue
        n_sent = len(_SENTENCE_END.findall(line))
        if _BULLET.match(line):
            # blockquotes stay fully exempt — they are the operator quoted back, not my prose
            if line.lstrip().startswith(">"):
                continue
            if len(line) >= _BULLET_MIN_CHARS and n_sent >= _BULLET_MIN_SENTENCES:
                out.append(line)
            continue
        if len(line) >= _MIN_CHARS and n_sent >= _MIN_SENTENCES:
            out.append(line)
    return out


def bullet_count(text: str) -> int:
    """Every bullet-shaped line, at ANY nesting depth (indented sub-bullets count too) -- the
    same shape prose_blocks() already recognizes as a bullet. Intentional: three headers with two
    children each is still nine lines he has to read, the same wall the cap targets. Code fences
    and blockquotes are exempt for the same reasons they're exempt above: a fence is data he asked
    to see, a blockquote is his own words quoted back."""
    n, in_fence = 0, False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _BULLET.match(line) and not line.lstrip().startswith(">"):
            n += 1
    return n


# Only the tail is ever needed, and the transcript accumulates every tool call and result for the
# whole session (megabytes by evening). Reading it whole on EVERY turn made the cost grow with the
# square of session length, for a few KB of signal.
_TAIL_BYTES = 256_000


def _tail_lines(transcript_path: str) -> list[str]:
    """The last complete lines of the file, bounded. Falls back to the whole file only if the
    bounded chunk holds no complete line (a single message larger than the chunk)."""
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - _TAIL_BYTES))
            chunk = fh.read()
        if size > _TAIL_BYTES:
            chunk = chunk.split(b"\n", 1)[1] if b"\n" in chunk else b""
        lines = chunk.decode("utf-8", "replace").splitlines()
        if lines:
            return lines
        with open(transcript_path, encoding="utf-8") as fh:
            return fh.readlines()
    except OSError:
        return []


def _is_operator_turn(entry: dict) -> bool:
    """A user entry the OPERATOR actually typed — not a tool_result, which the transcript also
    records as type "user". This is the turn boundary the search below stops at."""
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        # A tool_result-only entry is the harness echoing a tool call back, not the operator.
        return any(isinstance(c, dict) and c.get("type") != "tool_result" for c in content)
    return False


def last_assistant_text(transcript_path: str) -> str:
    """The final assistant message OF THE CURRENT TURN — the thing the operator is about to read.

    ⚠ Bounded at the last operator message on purpose (2026-08-23). Without the bound this walked
    back until it found ANY assistant text, so when the current turn's reply was not yet flushed to
    the transcript it judged a message from an EARLIER turn — one already delivered and already
    rewritten. Observed the day the bullet cap dropped 6 -> 5: a one-line reply was blocked as
    "6 bullets", the count of a report two turns back. A stale judgement is unfixable by the
    author, so the gate would fire on every subsequent turn — the wedge its own design forbids.
    Finding nothing after the boundary now returns "" and PASSES, matching the fail-open contract.

    Tolerant by construction: an unreadable or unfamiliar transcript returns "", which lets the
    turn through. A formatting gate must never be able to wedge a session."""
    for raw in reversed(_tail_lines(transcript_path)):
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if _is_operator_turn(entry):
            return ""  # reached the turn boundary without finding this turn's reply — pass
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
        "CLAUDE.md report format: bullets, titled blocks, ONE LINE PER BULLET. "
        "A bolded lead-in followed by 2-3 sentences IS a paragraph — that is the exact drift.\n"
        "This is NOT an instruction to produce more bullets: typically ONE is enough, "
        "sometimes 2-3. Rewriting a paragraph into five bullets misses the point.\n"
        "Rewrite: every idea becomes its own bullet; reasoning and caveats go to the commit, "
        "PLAN.md or the SSoT, not the message; state the action explicitly, including \"none\"."
    )


def length_complaint(n: int) -> str:
    return (
        f"REPORT FORMAT GATE — {n} bullets. The CEILING is 5, and 5 is rare.\n\n"
        "TYPICALLY ONE BULLET IS THE WHOLE ANSWER; sometimes 2-3 (operator 2026-08-23). "
        "The cap is a ceiling you are writing TO — that is the drift this arm now catches.\n"
        "CLAUDE.md rule 7 (operator 2026-08-08/09): bullets are still a wall of text if there are "
        "too many of them — the paragraph check only catches prose, and the drift moved here.\n"
        "Rewrite: first line = the answer, he can stop there and be right. Mechanism, root cause, "
        "verification, caveats — delete by default, they go to the commit/PLAN.md/SSoT, not the "
        "message. Per line: would he act differently without it? No → cut. Match the reply to the "
        "ask — a one-line instruction gets ONE LINE, not a report."
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
    if blocks:
        print(complaint(blocks), file=sys.stderr)
        return 2
    n = bullet_count(text)
    if n > _BULLET_CAP:
        print(length_complaint(n), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
