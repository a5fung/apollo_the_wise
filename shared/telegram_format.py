"""Shared Telegram formatting layer (#121) — ONE parse_mode = HTML.

WHY (feedback_telegram_formatting_systematic, operator 2026-05-29): stop patching
Telegram formatting per-message. Legacy `parse_mode=Markdown` has no clean escape
for dynamic strings, so a ticker/catalyst/name containing `*`, `_`, `[`, or a
backtick silently breaks the message ("Can't find end of entity" → 400 → the
alert vanishes or shows literal markup). #129/#130/#148 were all symptoms. HTML
mode has a SINGLE, total escape (`html.escape`) — every dynamic value goes through
`esc()` and the markup is unambiguous.

HOW TO USE (new/migrated builders):
    from shared.telegram_format import b, i, code, esc, render
    msg = render([
        b("EP ALERT") + " " + code(ticker),          # ticker auto-escaped
        f"Catalyst: {esc(catalyst_text)}",            # ALWAYS esc() free text
    ])
    await send_telegram_message(msg, parse_mode="HTML")

RULE: never f-string a raw dynamic value into HTML — wrap it in esc() (or a helper,
which esc()s for you). Static markup you write by hand is fine.

MIGRATION: `md_to_html()` converts an existing legacy-Markdown string to safe HTML,
so a builder can be migrated at the send boundary without a full rewrite. The
default send path stays Markdown until a surface is explicitly moved over — this
module is additive and breaks nothing on its own.
"""
from __future__ import annotations

import html as _html
import re

__all__ = ["esc", "b", "i", "code", "pre", "link", "bullet", "render", "md_to_html"]


def esc(s) -> str:
    """HTML-escape a dynamic value for Telegram HTML mode (& < >). Quotes are
    left as-is — Telegram only requires &<> escaped in text content, and readable
    apostrophes matter for prose."""
    return _html.escape(str(s), quote=False)


def b(s) -> str:
    return f"<b>{esc(s)}</b>"


def i(s) -> str:
    return f"<i>{esc(s)}</i>"


def code(s) -> str:
    return f"<code>{esc(s)}</code>"


def pre(s) -> str:
    return f"<pre>{esc(s)}</pre>"


def link(text, url) -> str:
    # Telegram requires the href quoted; escape both sides.
    return f'<a href="{_html.escape(str(url), quote=True)}">{esc(text)}</a>'


def bullet(s, marker: str = "•") -> str:
    """A bullet line. `s` may already contain helper-built HTML, so it is NOT
    re-escaped — callers pass pre-formatted content (use esc() on raw values)."""
    return f"{marker} {s}"


def render(lines) -> str:
    """Join a list of already-HTML-safe lines with newlines."""
    return "\n".join(lines)


# ── Legacy Markdown → HTML migration helper ──────────────────────────────────
# Telegram "Markdown" (v1) markup we must translate: *bold*, _italic_, `code`,
# ```pre```, [text](url). The strategy: pull code/pre spans OUT first (their
# content must NOT be markdown-parsed), HTML-escape everything else, translate the
# inline markers, then restore the (escaped) code/pre spans. This keeps a literal
# `<` in prose safe and a `*` inside code intact.
_PRE_RE = re.compile(r"```(.*?)```", re.DOTALL)
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)")
_ITALIC_RE = re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def md_to_html(text: str) -> str:
    """Best-effort convert a legacy-Markdown Telegram string to safe HTML.

    Use at the send boundary to migrate a builder without rewriting it. Handles
    *bold* _italic_ `code` ```pre``` [text](url). Anything not matched is
    HTML-escaped, so a stray `<` or `&` in prose is safe. Not perfect for
    pathological nesting — new builders should use the helpers directly."""
    if text is None:
        return ""
    placeholders: list[str] = []

    def _stash(rendered: str) -> str:
        placeholders.append(rendered)
        return f"\x00{len(placeholders) - 1}\x00"

    # 1) Pull pre/code spans out (escape their inner content), leave a placeholder.
    text = _PRE_RE.sub(lambda m: _stash(f"<pre>{esc(m.group(1))}</pre>"), text)
    text = _CODE_RE.sub(lambda m: _stash(f"<code>{esc(m.group(1))}</code>"), text)
    # 2) Links: capture before escaping (the () [] would survive escape, but do it now).
    text = _LINK_RE.sub(lambda m: _stash(link(m.group(1), m.group(2))), text)
    # 3) Escape everything else.
    text = esc(text)
    # 4) Inline emphasis on the escaped text.
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    # 5) Restore the stashed spans.
    def _unstash(m):
        return placeholders[int(m.group(1))]
    return re.sub(r"\x00(\d+)\x00", _unstash, text)
