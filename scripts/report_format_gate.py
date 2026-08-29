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


# ── WORD CAP (2026-08-29) ──────────────────────────────────────────────────────────────────────
# THE OPERATOR'S NUMBER, not a derived one: *"cap it at the original tweet size, 140 chars, 28
# words."*
#
# WHY THIS ARM EXISTS WHEN THREE OTHERS ALREADY DO. Every prior arm caps a SHAPE — paragraphs,
# bullet count, empty bullets — and the drift kept moving into whatever the shape allowed. On
# 2026-08-29 he said: *"why do i need to ask you to rewrite summary every single time... you always
# write junk"*, and then, of the reply that answered it: *"you literally just did it again, this
# msg you just sent can be cut by at least 50% easily and lose no info."* Five legal bullets at
# fifty words each clears every existing arm and is still a wall.
#
# ⚠ IT IS NOT CALIBRATED AGAINST HISTORY, DELIBERATELY. I measured 7,824 replies to find a
# separating threshold and there is none: recent replies run a 48-word median against a 42-word
# historical median. The history is not a baseline to hold to — it is the thing being corrected,
# so a cap fitted to it would bless the problem. That is why this number is his and not mine, and
# why it is not to be raised to chase a lower firing rate.
#
# It WILL fire often at first. That is the intent.
_WORD_CAP = 28
_BULLET_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")

# Same exemptions the other arms use, for the same reasons: a code fence is data he asked to see,
# a table is structure, a blockquote is his own words quoted back, a heading is a label. None of
# them is prose I chose to write at him.


# ── FILLER ARM (2026-08-24) ────────────────────────────────────────────────────────────────────
# Operator, angry, on a 4-bullet reply that cleared the cap: *"I don't know why you need 4 bullets
# to state what you need to say, so much useless info, like no shit deferring won't move it... yet
# you wrote 4 bullets that gave no solution whatsoever, this needs to stop once and for all."*
#
# The cap arm could not catch it: 4 bullets is legal. The drift moved BELOW the ceiling — bullets
# that are well-formed and carry nothing. CLAUDE.md rule 7 already states the test ("would he act
# differently without it? No -> cut"), and that test is not machine-decidable in general.
#
# What IS decidable: a bullet that names no NUMBER, no file/path, no #task, no command and no
# decision verb is almost never something he can act on. It is restatement. Measured against the
# 2026-08-24 message that triggered this: 2 of its 4 bullets carry no concrete token, and both are
# the ones he called out by name. Deliberately narrow — one filler bullet in a message is normal
# (a lead-in, an "action: none"); a message that is MOSTLY filler is the failure.
_CONCRETE = re.compile(
    r"\d"                                   # any number — counts, prices, R, dates, percentages
    r"|#\d+"                                # a task id
    r"|[\w./-]+\.(?:py|md|ya?ml|json|sql|txt|sh)"   # a file
    r"|`[^`]+`"                             # code/command/identifier he can run or grep
    r"|\b(?:none|yes|no|deploy|deployed|closed|fixed|shipped|blocked|waiting|verify|verified)\b",
    re.I,
)
_FILLER_MIN_BULLETS = 3     # below this, a filler line is a lead-in, not a pattern
_FILLER_RATIO = 0.5         # MOST of the message must be filler before it blocks


def filler_bullets(text: str) -> list[str]:
    """Bullets carrying no number, file, task id, code span or decision word — nothing he can act
    on. Returns them only when they are the MAJORITY of a >=3-bullet message; otherwise []."""
    bullets = []
    in_fence = False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        if _BULLET.match(line) and not line.lstrip().startswith(">"):
            bullets.append(line)
    if len(bullets) < _FILLER_MIN_BULLETS:
        return []
    empty = [b for b in bullets if not _CONCRETE.search(b)]
    return empty if len(empty) / len(bullets) > _FILLER_RATIO else []


def filler_complaint(blocks: list[str], total: int) -> str:
    shown = "\n".join(f"    {b[:110]}{'...' if len(b) > 110 else ''}" for b in blocks[:3])
    return (
        f"REPORT FORMAT GATE — {len(blocks)} of {total} bullets carry nothing he can act on:\n"
        f"{shown}\n\n"
        "No number, no file, no task id, no command, no decision. That is restatement, and it is "
        "what he means by \"useless info\" (operator 2026-08-24, angry: a 4-bullet reply that "
        "cleared the cap and still \"gave no solution whatsoever\").\n"
        "Rewrite: keep the bullets that carry a number, a name, or a decision. DELETE the rest — "
        "do not reword them. If that leaves one bullet, the answer was one bullet."
    )


def countable_words(text: str) -> int:
    """Words the operator actually has to read. Skips code fences, tables, headings and
    blockquotes — the same carve-outs prose_blocks() and bullet_count() already make."""
    n, in_fence = 0, False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        if _HEADING.match(line) or _TABLE.match(line) or line.lstrip().startswith(">"):
            continue
        # Strip the bullet/numbering marker before counting — "-" and "1." are markup, not words
        # he reads. Leaving them in inflated every bulleted reply by one word per line, which on
        # a 28-word budget is up to a fifth of it.
        n += len(_BULLET_MARKER.sub("", line.lstrip()).split())
    return n


def word_complaint(n: int) -> str:
    return (
        f"REPORT FORMAT GATE — {n} words; the cap is {_WORD_CAP} (operator 2026-08-29: "
        f"\"cap it at the original tweet size, 140 chars, 28 words\").\n"
        "Cut it, do not restructure it. The same information fits — he has said so every time: "
        "\"can be cut by at least 50% easily and lose no info\".\n"
        "Delete first: mechanism, caveats already recorded in the commit or PLAN, restating his "
        "question, and anything that proves you did the work rather than telling him the answer.\n"
        "Code, tables, headings and quoted text are NOT counted — only prose you chose to write."
    )


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
        # NOT a free pass any more — the word cap below still applies. This only skips the
        # SHAPE arms, which need a body big enough to have a shape.
        return _word_arm(text)
    blocks = prose_blocks(text)
    if blocks:
        print(complaint(blocks), file=sys.stderr)
        return 2
    n = bullet_count(text)
    if n > _BULLET_CAP:
        print(length_complaint(n), file=sys.stderr)
        return 2
    # Runs LAST, and only on messages that already cleared the cap — this arm exists precisely
    # because the drift moved BELOW the ceiling (operator 2026-08-24, on a legal 4-bullet reply).
    empty = filler_bullets(text)
    if empty:
        print(filler_complaint(empty, n), file=sys.stderr)
        return 2
    # WORD CAP runs LAST so the SHAPE arms keep their more specific diagnosis when both apply —
    # "this is a paragraph" tells me more than "this is long". But it is never skipped: 28 words
    # is ~170 chars, far under _MIN_MESSAGE_CHARS, so the short-message branch above calls it too.
    return _word_arm(text)


def _word_arm(text: str) -> int:
    words = countable_words(text)
    if words > _WORD_CAP:
        print(word_complaint(words), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
