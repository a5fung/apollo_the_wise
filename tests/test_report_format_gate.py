"""The report-format rule gets a GATE, because six askings did not hold it (operator 2026-08-02).

*"you are reverting back to your prose and not repsecting the bullet point, lead to key insight,
etc. format i asked for over and over"*

The rule was already in a memory AND on CLAUDE.md's always-loaded surface, and it still drifted
inside one session. Same lesson as PLAN.md, the burndown count, and verify-live: only gates hold.

⚠ **The two failure modes a gate like this has, and what pins them here:**
1. **Over-firing** — a style checker that trips on ordinary answers gets switched off within a week
   ("a guard that always fires is not a guard", 2026-08-01). Everything below the `_ok` line is a
   message that must pass untouched.
2. **Wedging the session** — a formatting check must never be able to block work. Unreadable
   payload, unreadable transcript, and a re-entry after its own block all fail OPEN.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_GATE = _ROOT / "scripts/report_format_gate.py"
sys.path.insert(0, str(_ROOT / "scripts"))

from report_format_gate import bullet_count, prose_blocks  # noqa: E402

# The verbatim shape the operator objected to on 2026-08-02: a bolded lead-in, then sentences.
_THE_DRIFT = """Fixed, shipped, and checked on the live system.

**The cost tracking was never broken.** It was reporting one bucket that had two different things \
in it. Live grading and the chart experiment were both filed under the same name, so no report \
could tell them apart.
"""

# ⚠ SHRUNK 2026-08-29 for the 28-word cap (operator: "cap it at the original tweet size,
# 140 chars, 28 words"). These fixtures encoded the OLD bar — they were legal in SHAPE and
# still 33-85 words, which is exactly the drift the word cap exists to catch. Each keeps
# every fact it carried; only the words came out, which was his whole point.
_THE_FIX = """Spend is readable per lane again.

- A grading call let lanes skip naming who pays; 8 lanes billed live.
- Fixed and live. Action: none.
"""


# ── it catches the thing it exists for ───────────────────────────────────────────────────────

def test_it_catches_the_exact_drift_the_operator_named():
    assert prose_blocks(_THE_DRIFT), "the 8/02 drift must be caught or the gate is decorative"


def test_a_bolded_lead_in_does_not_launder_a_paragraph():
    """CLAUDE.md says this outright: 'a bolded lead-in followed by 3 sentences is still a
    paragraph'. Bolding the first clause is the move that kept slipping through."""
    text = ("**Header here.** " + "This is a sentence of reasonable length. " * 4)
    assert prose_blocks(text)


def test_several_paragraphs_are_all_reported_not_just_the_first():
    """The operator should see the scale of it, not one example."""
    assert len(prose_blocks(_THE_DRIFT + "\n" + _THE_DRIFT)) == 2


# ── _ok: things that must pass untouched ─────────────────────────────────────────────────────

def test_the_correctly_formatted_version_passes():
    assert prose_blocks(_THE_FIX) == []


def test_a_bullet_may_carry_TWO_sentences():
    """The rule is 'no paragraphs', not 'no second sentence anywhere' — claim plus the number
    behind it is the format working, and gating it would get the whole thing switched off."""
    text = ("- **Root cause.** The call let a lane skip naming who pays, so it billed the live "
            "lane instead of its own, which is why no report could ever separate the two.")
    assert prose_blocks(text) == []


def test_a_THREE_sentence_bullet_is_still_a_paragraph():
    """Operator 2026-08-03, one day after this gate shipped: *"you are reverting back to being too
    wordy"* — about a message that WAS all bullets, each carrying three sentences. Exempting
    bullets wholesale just moved the drift inside them."""
    text = ("- **Two alerts today have no permanent record.** FTK at 8:45 and LIND at 9:55, both "
            "blocked, both before the fix landed. Their reasons are in the audit log, so /why "
            "still answers — only the trade rows are missing.")
    assert prose_blocks(text), "a 3-sentence bullet must trip the gate"


def test_a_SHORT_three_sentence_bullet_passes():
    """Length is half the test — three terse clauses are not a paragraph."""
    text = "- Fixed. Deployed. Verified."
    assert prose_blocks(text) == []


def test_the_bullet_thresholds_are_the_MEASURED_ones():
    """Chosen from 548 report-sized messages, not taste: 16% blocked at (180, 3) vs 6% at
    (180, 4), which was too loose to catch the drift the operator named."""
    import report_format_gate as g
    assert (g._BULLET_MIN_CHARS, g._BULLET_MIN_SENTENCES) == (180, 3)


def test_a_long_single_sentence_header_passes():
    """Rule 1 says the header must carry the substance — so it is allowed to be long."""
    text = ("Cost attribution is fixed and verified live, and spend is now readable per lane "
            "rather than merged into one bucket that hid an experiment inside production.")
    assert prose_blocks(text) == []


def test_code_blocks_are_never_prose():
    text = "Result:\n\n```\n" + ("a long line of output. with periods. and more. " * 4) + "\n```\n"
    assert prose_blocks(text) == []


def test_headings_and_tables_are_not_prose():
    assert prose_blocks("### " + "A heading. With sentences. And more. " * 5) == []
    assert prose_blocks("| a | b |\n|---|---|\n| " + "x. y. z. " * 20 + " | q |") == []


def test_quoted_operator_text_is_not_counted_as_my_prose():
    """Blockquotes are the operator's words being quoted back — gating those would punish
    quoting him accurately, which the format explicitly wants."""
    assert prose_blocks("> " + "His sentence here. And another one of his. And a third. " * 3) == []


# ── it can never wedge the session ───────────────────────────────────────────────────────────

def _run(payload: dict, env_extra: "dict | None" = None):
    import os
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([sys.executable, str(_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def _transcript(tmp_path, text: str) -> str:
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n"
                 + json.dumps({"type": "assistant",
                               "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    return str(p)


def test_blocks_on_a_prose_report(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _THE_DRIFT * 3)})
    assert r.returncode == 2
    assert "REPORT FORMAT GATE" in r.stderr and "bullet" in r.stderr.lower()


def test_allows_a_correctly_formatted_report(tmp_path):
    # Padded with a heading (exempt from both the prose and the bullet count) rather than
    # repeating _THE_FIX, which would have tripled its 4 bullets past the length arm's cap of 6 —
    # an artifact of the old padding trick, not a real multi-report reply.
    padded = _THE_FIX + "\n### Confirmed in production — no further action needed on this line.\n"
    r = _run({"transcript_path": _transcript(tmp_path, padded)})
    assert r.returncode == 0, r.stderr


def test_a_re_entry_after_its_own_block_never_blocks_again(tmp_path):
    """Without this the gate could loop forever on a message it keeps disliking."""
    r = _run({"transcript_path": _transcript(tmp_path, _THE_DRIFT * 3), "stop_hook_active": True})
    assert r.returncode == 0


def test_an_unreadable_transcript_fails_open():
    r = _run({"transcript_path": "/nonexistent/nope.jsonl"})
    assert r.returncode == 0


def test_a_malformed_payload_fails_open():
    r = subprocess.run([sys.executable, str(_GATE)], input="not json",
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_a_short_reply_is_never_gated(tmp_path):
    """The format rule is about progress reports and summaries. Gating a two-line answer is the
    over-firing that would get this switched off."""
    r = _run({"transcript_path": _transcript(tmp_path, "Yes — 336 of 379 calls. Action: none.")})
    assert r.returncode == 0


# ── LENGTH ARM — the drift that moved past the paragraph check (operator 2026-08-09) ───────────
#
# Calibrated against six weeks of the operator's own transcripts (1,419 replies actually shown to
# him). 14 were genuinely complained about as too long/wordy; bullets > 6 catches 9 of them,
# including both anchors below, at the number CLAUDE.md rule 7 already states as the hard cap.
# Full calibration story lives in the module docstring — this file freezes the numbers so a later
# edit can't quietly loosen the cap.

# Verbatim reply that drew "this sounds too complicated, just in one simple sentence" and then,
# two turns later, "please fix how you write ... hides the core most important points underneath
# all the rambling" (2026-08-09, session 6bd49b80, line 30606). 13 bullets, 0 prose paragraphs —
# it was fully "correctly formatted" and still the thing he was objecting to.
_ANCHOR_30606 = """**Carryover recorded and #555 filed — the matcher rewrite now has its own line.**

**What it says**
- Theme identity is decided by ticker overlap alone, one day at a time.
- Nine rules now stack on a single decision.
- The newest sits in a gap 0.014 wide, judged on two examples.
- The core case: overlap alone cannot tell a stray re-attachment from a genuine rename.

**What I locked into it**
- The three bad merges must stay split; the real defence duplicate must stay merged.
- Grid must be identical at all 21 slider settings, not one.
- The rule count must come down — ten instead of nine solves nothing.

**Why it couldn't stay on #553**
- #553 is the patch; this is the rewrite that patch is evidence for.
- Leaving it there would repeat July's mistake of folding new work onto an old line.

**Board: 84**, ceiling raised to 84 with your authorisation and the reason recorded.

**Action — one thing**
- Use **Reboot app** on share.streamlit.io next time you open the dashboard, not a reload.

**Monday, unchanged**
- Flip the breakeven stop before 09:30 ET.
- Run the order-shape test during market hours.
- Confirm five things landed in production.
"""

# Verbatim reply that drew "how come you still write so much ... it's a simple ask and you just
# need to tell me you're doing it, one line, instead you wrote 10 lines" (2026-08-09, same
# session, line 31384). 7 bullets — the exact floor of the cap; this is the anchor that rules out
# every threshold above 6.
_ANCHOR_31384 = """**Agreed, and this one is genuinely gateable — unlike yesterday's.**

**Why it can be caught mechanically**
- The trigger is my own written claim, not a judgement call. If a task says a check is pending, its date and status must back that up.
- That's decidable from the board file alone, same as the gates already running before every commit.

**I measured your board before carding it**
- 12 lines are correctly marked. **7 claim a verification while sitting in a status that will never surface it** — including #548, tomorrow's breakeven work.
- So this isn't a one-off slip, it's a standing hole.

**Being built now**
- Fails the commit when a line promises a check without a date that surfaces it, naming the task and the exact fix.
- Must separate a pending promise from a past one already confirmed — that's the hard part, and if the noise can't be kept low it won't ship.
- Existing 7 get flagged rather than blocking the first commit; new ones fail hard.

**Action: none.** I'll verify it catches today's case before it goes in.
"""

# Five bullets, comfortably over _MIN_MESSAGE_CHARS — must pass. The cap is "over 5", not "5".
# ⚠ Five is the CEILING and is RARE (operator 2026-08-23) — a legal message, not a model one.
# Five bullets is still legal in SHAPE — but note what fitting it inside 28 words costs. The
# word cap now binds tighter than the bullet cap in almost every real reply, which is the point:
# five bullets is a rare ceiling, and spending it means five very short lines.
_FIVE_BULLETS_OK = """**Spend is readable per lane.**

- 8 lanes billed live.
- Payer required at the call site.
- Replay bills itself.
- Verified a day.
- Action: none.
"""


def test_the_bullet_cap_is_the_operators_own_written_number():
    """CLAUDE.md rule 7. LOWERED 6 -> 5 on 2026-08-23, operator-directed: "5 bullet is max, but
    that means max when you have a lot to say to, typically one bullet is sufficient, sometimes
    2-3, but rarely 5 is needed... you always write way too much". This test exists to stop a
    quiet LOOSENING; a tightening the operator asked for by name is the one legitimate edit, and
    it carries his words. ⚠ The gate polices the ceiling only — "typically one bullet" is not
    machine-decidable and never will be."""
    import report_format_gate as g
    assert g._BULLET_CAP == 5


def test_anchor_30606_thirteen_bullets_is_over_cap():
    assert bullet_count(_ANCHOR_30606) == 13


def test_anchor_31384_seven_bullets_is_over_the_cap():
    """7 was the minimum bullet count across every genuine length complaint in the 2026-08-09
    corpus, and set the original cap of 6. The cap is 5 since 2026-08-23, so this anchor now
    clears it by two — the threshold can still never be RAISED past 6 without losing it."""
    assert bullet_count(_ANCHOR_31384) == 7


def test_five_bullets_passes():
    assert bullet_count(_FIVE_BULLETS_OK) <= 5


def test_code_fenced_bullet_like_lines_are_not_counted():
    """A code block or diff full of '- ' lines is data he asked to see, not my bullets."""
    text = "Diff:\n\n```\n" + "\n".join(f"- old line {i}" for i in range(20)) + "\n```\n"
    assert bullet_count(text) == 0


def test_nested_sub_bullets_count_too():
    """Intentional, not a bug: three headers with three children each is still nine lines he has
    to read line by line -- the same wall the cap targets, however it's indented."""
    text = "\n".join(f"  - child {i}" for i in range(9))
    assert bullet_count(text) == 9


def test_a_terse_reply_under_400_chars_is_never_gated_even_with_many_bullets(tmp_path):
    """The length arm only ever runs once the message clears _MIN_MESSAGE_CHARS, same gate the
    paragraph arm already uses. Eight short bullets that stay under 400 chars total ARE the terse
    list he wants -- pinned so a change to _MIN_MESSAGE_CHARS can't silently widen this arm's
    scope without a test noticing."""
    text = "\n".join(f"- item {i}" for i in range(8))
    assert len(text) < 400
    r = _run({"transcript_path": _transcript(tmp_path, text)})
    assert r.returncode == 0, r.stderr


def test_blocks_on_the_exact_anchor_31384_via_the_hook(tmp_path):
    """The floor case, run through the actual Stop hook subprocess — not just the pure function."""
    r = _run({"transcript_path": _transcript(tmp_path, _ANCHOR_31384)})
    assert r.returncode == 2
    assert "7 bullets" in r.stderr and "CEILING is 5" in r.stderr


def test_blocks_on_the_exact_anchor_30606_via_the_hook(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _ANCHOR_30606)})
    assert r.returncode == 2
    assert "13 bullets" in r.stderr


def test_allows_five_bullets_via_the_hook(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _FIVE_BULLETS_OK)})
    assert r.returncode == 0, r.stderr


def test_length_block_message_states_actual_count_and_the_cap():
    from report_format_gate import length_complaint
    msg = length_complaint(17)
    assert "17 bullets" in msg and "CEILING is 5" in msg
    assert "TYPICALLY ONE BULLET" in msg, (
        "the message must say what the target IS, not only what the ceiling is — the operator's\n"
        "2026-08-23 correction was that a cap alone gets written TO")


def test_a_re_entry_after_a_length_block_never_blocks_again(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _ANCHOR_31384), "stop_hook_active": True})
    assert r.returncode == 0


def test_the_length_arm_off_switch_covers_it_too(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _ANCHOR_30606)},
             {"REPORT_FORMAT_GATE": "off"})
    assert r.returncode == 0


def test_there_is_an_off_switch(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _THE_DRIFT * 3)},
             {"REPORT_FORMAT_GATE": "off"})
    assert r.returncode == 0


# ── wiring ───────────────────────────────────────────────────────────────────────────────────

def test_the_gate_is_actually_wired_as_a_stop_hook():
    """A gate nobody runs is a script. `/audit` and `/crypto` both shipped this week with working
    handlers and no registration — the same class of miss."""
    cfg = json.loads((_ROOT / ".claude/settings.json").read_text())
    hooks = json.dumps(cfg.get("hooks", {}))
    assert "Stop" in cfg.get("hooks", {}), "no Stop hook registered"
    assert "report_format_gate.py" in hooks


@pytest.mark.parametrize("doc", ["CLAUDE.md"])
def test_claude_md_points_at_the_gate(doc):
    """The rule and its enforcement must be findable from each other, or the next reader
    re-litigates it — which is how it got asked six times."""
    assert "report_format_gate" in (_ROOT / doc).read_text()


# --- turn boundary (2026-08-23) -------------------------------------------------------------
# The gate judged a message from an EARLIER turn when the current turn's reply had not yet been
# flushed to the transcript: a one-line reply was blocked as "6 bullets", the count of a report
# two turns back. A stale judgement cannot be fixed by rewriting, so it fires again every turn --
# the wedge this gate's own design forbids. last_assistant_text() now stops at the last operator
# message and returns "" (pass) if this turn produced no text yet.

def _multi_turn(tmp_path, *entries) -> str:
    """entries: ("user", text) | ("assistant", text) | ("tool_result", text), in order."""
    p = tmp_path / "multi.jsonl"
    lines = []
    for kind, text in entries:
        if kind == "user":
            lines.append({"type": "user", "message": {"content": text}})
        elif kind == "tool_result":
            lines.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "x", "content": text}]}})
        else:
            lines.append({"type": "assistant",
                          "message": {"content": [{"type": "text", "text": text}]}})
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(p)


def test_a_prior_turns_over_cap_reply_is_not_judged_again(tmp_path):
    """THE OBSERVED BUG. An over-cap reply, then the operator speaks, then this turn has produced
    no text yet. The gate must PASS -- judging the old message would block a turn whose author
    cannot fix it."""
    from report_format_gate import last_assistant_text
    t = _multi_turn(tmp_path, ("user", "start"), ("assistant", _ANCHOR_31384), ("user", "ok next"))
    assert last_assistant_text(t) == ""
    r = _run({"transcript_path": t})
    assert r.returncode == 0, r.stderr


def test_this_turns_reply_is_still_judged_after_the_boundary(tmp_path):
    """The bound must not blind the gate: text written AFTER the operator's message is this
    turn's reply and is judged exactly as before."""
    t = _multi_turn(tmp_path, ("assistant", "old and clean"), ("user", "go"),
                    ("assistant", _ANCHOR_31384))
    r = _run({"transcript_path": t})
    assert r.returncode == 2
    assert "7 bullets" in r.stderr


def test_a_tool_result_is_not_a_turn_boundary(tmp_path):
    """Tool results are recorded as type "user". Treating one as the boundary would blind the
    gate on every turn that ends with a tool call -- which is most of them."""
    t = _multi_turn(tmp_path, ("user", "go"), ("tool_result", "ok"),
                    ("assistant", _ANCHOR_31384))
    r = _run({"transcript_path": t})
    assert r.returncode == 2


def test_the_boundary_returns_the_latest_reply_when_several_exist(tmp_path):
    """Mid-turn text before a tool call is superseded by the final reply -- unchanged behaviour,
    pinned so the boundary edit cannot quietly change which message is judged."""
    from report_format_gate import last_assistant_text
    t = _multi_turn(tmp_path, ("user", "go"), ("assistant", "first pass"),
                    ("tool_result", "ok"), ("assistant", "final answer"))
    assert last_assistant_text(t) == "final answer"


# --- filler arm (2026-08-24) -----------------------------------------------------------------
# Operator, on a 4-bullet reply that CLEARED the 5-bullet cap: "I don't know why you need 4
# bullets to state what you need to say, so much useless info... yet you wrote 4 bullets that
# gave no solution whatsoever, this needs to stop once and for all." The cap could not catch it;
# the drift moved below the ceiling into well-formed bullets carrying nothing actionable.

_THE_FILLER_MESSAGE = """You're right, and it has been flat for a while:

- **The gate only stops growth — it was never an engine.** We close two and find two, every session.
- **Deferring will not move it either.** Pushing dates out is honest scheduling but the count stays.
- **The only thing that reduces it is deciding some will never be done.** That is the real lever.
- **That is your call, not mine.** I cannot close real work as won't-do on my own authority.
"""

_ACTIONABLE_MESSAGE = """Deployed and verified.

- Closed #585 and #517.
- `deploy.sh execution` still owed.
- Action: none — next signal is tomorrow's open.
"""


def test_the_filler_message_is_blocked():
    """THE ANCHOR. Four legal bullets, none carrying a number, file, task id or decision."""
    from report_format_gate import filler_bullets
    assert len(filler_bullets(_THE_FILLER_MESSAGE)) >= 3


def test_a_message_whose_bullets_carry_facts_passes(tmp_path):
    from report_format_gate import filler_bullets
    assert filler_bullets(_ACTIONABLE_MESSAGE) == []
    r = _run({"transcript_path": _transcript(tmp_path, _ACTIONABLE_MESSAGE)})
    assert r.returncode == 0, r.stderr


def test_one_or_two_bullets_are_never_filler_blocked():
    """A short answer is the GOAL. This arm must never punish it — that would invert the rule."""
    from report_format_gate import filler_bullets
    assert filler_bullets("- It cannot be done that way.\n- I would not recommend it.\n") == []


def test_a_single_filler_bullet_among_facts_passes():
    """Narrow by design: one lead-in among real content is normal, not the failure."""
    from report_format_gate import filler_bullets
    text = ("- **This is the part I would change.**\n"
            "- Closed #585 and #517 today.\n"
            "- `deploy.sh execution` still owed.\n")
    assert filler_bullets(text) == []


def test_the_filler_block_names_the_offending_lines(tmp_path):
    r = _run({"transcript_path": _transcript(tmp_path, _THE_FILLER_MESSAGE)})
    assert r.returncode == 2
    assert "carry nothing he can act on" in r.stderr
    assert "DELETE the rest" in r.stderr


# ─── WORD CAP (2026-08-29) ───────────────────────────────────────────────────────────────
# Operator: "cap it at the original tweet size, 140 chars, 28 words." Every prior arm caps a
# SHAPE, and the drift kept moving into whatever the shape allowed — five legal bullets at
# fifty words each clears all three and is still a wall. This arm caps the one thing they
# don't: how much he has to read.

_OVER_CAP = """Measured — and the honest answer is that a gate can't be calibrated from my own
history, because the history is the problem. My recent replies are no longer than my past ones.

- So the ceiling has to be a number you set, not one derived from me. I'd propose 40 words.
- That kills roughly half of everything I've ever sent you, which is the point.
- Say a number and I'll wire it into the same Stop hook today.
"""


def test_the_reply_he_rejected_now_fires(tmp_path):
    """The literal message he pushed back on ("this msg you just sent can be cut by at least
    50% easily and lose no info"). It cleared every existing arm."""
    r = _run({"transcript_path": _transcript(tmp_path, _OVER_CAP)})
    assert r.returncode == 2
    # It happens to trip the FILLER arm first, which is correct — a more specific diagnosis
    # wins. What matters is that it no longer passes; assert the word arm on it directly too.
    from report_format_gate import _WORD_CAP, countable_words
    assert countable_words(_OVER_CAP) > _WORD_CAP


def test_a_tweet_sized_answer_passes(tmp_path):
    tight = "- Issue: the comparison used stale data.\n- Fix: records both reads. Deployed.\n- Real numbers start Monday.\n"
    r = _run({"transcript_path": _transcript(tmp_path, tight)})
    assert r.returncode == 0, r.stderr


def test_short_messages_are_no_longer_a_free_pass(tmp_path):
    """_MIN_MESSAGE_CHARS (400) exempts a message from the SHAPE arms because a short body has
    no shape to judge. 28 words is ~170 chars — far under it — so exempting the word cap the
    same way would have exempted exactly the messages it exists to catch."""
    from report_format_gate import _MIN_MESSAGE_CHARS
    msg = "- " + " ".join(["word"] * 60) + "\n"
    assert len(msg) < _MIN_MESSAGE_CHARS
    r = _run({"transcript_path": _transcript(tmp_path, msg)})
    assert r.returncode == 2, "a short-but-wordy reply must still be caught"


def test_code_tables_headings_and_his_own_words_are_not_counted(tmp_path):
    """Only prose I chose to write at him counts. A fence is data he asked to see, a table is
    structure, a blockquote is his own words quoted back."""
    from report_format_gate import countable_words
    body = ("- Deployed.\n"
            "### A heading that is quite long and would otherwise blow the cap on its own\n"
            "> " + " ".join(["quoted"] * 50) + "\n"
            "| a | b |\n|---|---|\n"
            "```\n" + " ".join(["code"] * 80) + "\n```\n")
    assert countable_words(body) == 1
    r = _run({"transcript_path": _transcript(tmp_path, body)})
    assert r.returncode == 0, r.stderr


def test_a_shape_violation_still_wins_the_diagnosis(tmp_path):
    """Ordering: the word arm runs LAST so "this is a paragraph" — the more specific and more
    useful complaint — is what I see when a message trips both."""
    prose = ("This is an unbulleted paragraph. It carries several sentences in a row. That is "
             "the exact drift the first arm was built to catch, and it should be named as such "
             "rather than reported merely as length. " * 2)
    r = _run({"transcript_path": _transcript(tmp_path, prose)})
    assert r.returncode == 2
    assert "prose paragraph" in r.stderr and "the cap is 28" not in r.stderr


def test_the_cap_is_the_operators_number_not_a_fitted_one():
    """Pinned deliberately. I measured 7,824 replies looking for a separating threshold and
    there is none — recent replies run a 48-word median against a 42-word historical median.
    The history is the thing being corrected, not a baseline to fit to, so this number is his.
    Do not raise it to chase a lower firing rate."""
    from report_format_gate import _WORD_CAP
    assert _WORD_CAP == 28
