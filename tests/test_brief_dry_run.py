"""Rendering the evening brief for review must NOT send it (2026-08-04).

WHY THIS EXISTS. Asked to show the operator the new brief, I rendered it in production by
monkey-patching `send_telegram_message` on the briefing module. The patch did not take, and he
received a SECOND evening brief at 19:45 — `evening_brief_sent` rows at 18:00 (1669 chars) and
19:45 (1813 chars) — a duplicate message on the day spent removing duplicate messages.

The root cause is not the patch. It is that there was no supported way to LOOK at this brief
without sending it, which made a workaround inevitable and the accident with it. `dry_run=True`
is that path.

Scope: dry_run must skip EVERY outward effect, not just the Telegram — the audit row, the chart
mosaic and the Twitter post all sit after the send in the same function, and a "render" that
tweets is not a render.
"""
import ast
import inspect
import pathlib

SRC = pathlib.Path("agents/market_intelligence/briefing.py").read_text()
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def test_the_entry_point_accepts_dry_run():
    from agents.market_intelligence.briefing import send_evening_briefing
    sig = inspect.signature(send_evening_briefing)
    assert "dry_run" in sig.parameters
    assert sig.parameters["dry_run"].default is False, "sending stays the default"
    assert sig.parameters["dry_run"].kind is inspect.Parameter.KEYWORD_ONLY, (
        "keyword-only so a stray positional argument can never silence a real brief")


def test_dry_run_returns_BEFORE_the_send():
    src = ast.get_source_segment(SRC, _fn("send_evening_briefing"))
    guard = src.index("if dry_run:")
    send = src.index("await send_telegram_message(text, chat_id)")
    assert guard < send, "the guard must precede the send, not follow it"


def test_dry_run_skips_EVERY_outward_effect_not_just_telegram():
    """The audit row, chart mosaic and Twitter post all live after the send in this function.
    A render that tweets is not a render."""
    src = ast.get_source_segment(SRC, _fn("send_evening_briefing"))
    after = src[src.index("if dry_run:"):]
    body = after[:after.index("\n\n")] if "\n\n" in after else after
    assert "return text" in body, "the guard returns immediately"
    tail = src[src.index("await send_telegram_message(text, chat_id)"):]
    for effect in ("_emit_evening_brief_outcome", "mosaic"):
        assert effect in tail, (
            f"{effect} must sit AFTER the guard's return — if it moves above it, this test is "
            f"the thing that catches a dry run leaking a side effect")


def test_the_default_path_is_untouched():
    """A guard that changes normal behaviour is a regression, not a guard."""
    src = ast.get_source_segment(SRC, _fn("send_evening_briefing"))
    assert "await send_telegram_message(text, chat_id)" in src
    assert src.count("if dry_run:") == 1, "exactly one guard, no scattered conditionals"
