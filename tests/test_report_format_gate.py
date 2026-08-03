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

from report_format_gate import prose_blocks  # noqa: E402

# The verbatim shape the operator objected to on 2026-08-02: a bolded lead-in, then sentences.
_THE_DRIFT = """Fixed, shipped, and checked on the live system.

**The cost tracking was never broken.** It was reporting one bucket that had two different things \
in it. Live grading and the chart experiment were both filed under the same name, so no report \
could tell them apart.
"""

_THE_FIX = """Cost attribution fixed and live — spend is now readable per lane.

- **Not a tracking failure.** One bucket held two things: live grading and the experiment.
- **Root cause:** the grading call let a lane skip naming who pays, so it billed the live lane.
- **Scope was 8 lanes, not 1** — every offline test and replay was billing live grading too.
- **Action: none.** No new task, no ceiling change.
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


def test_bullets_are_free_even_when_they_carry_two_sentences():
    """The rule is 'no prose paragraphs', not 'no second sentence anywhere'. Gating inside bullets
    would make the format unusable and the gate would be turned off."""
    text = ("- **Root cause.** The call let a lane skip naming who pays, so it billed the live "
            "lane instead. That is why the report could not separate them at all, ever.")
    assert prose_blocks(text) == []


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
    r = _run({"transcript_path": _transcript(tmp_path, _THE_FIX * 3)})
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
