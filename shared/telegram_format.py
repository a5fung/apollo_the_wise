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
so a builder can be migrated at the send boundary without a full rewrite. Since #652
(2026-09-19) `send_telegram_message` does that conversion ITSELF whenever the caller
passes no `parse_mode` — a builder that writes legacy Markdown and calls the sender
bare is already on the HTML layer. Pass `parse_mode="HTML"` only for a body that is
already HTML (built with the helpers above, or converted by the caller); it is then
passed through untouched. `parse_mode="Markdown"` is ALSO converted (#675, 2026-09-20 —
folded into the same path as the default; it no longer has a raw legacy-Markdown route of
its own). `chunk_html()` is the tag-aware splitter the HTML send path uses.
"""
from __future__ import annotations

import html as _html
import re

__all__ = ["esc", "b", "i", "code", "pre", "link", "bullet", "render", "md_to_html", "chunk_html"]


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
# Fence = Telegram's legacy-Markdown pre rule, mirrored (#652, 2026-09-19): an optional
# language token — a run of non-space, non-backtick chars straight after the opener, taken
# only when whitespace follows it (so ```abc``` is content, not a language) — is DROPPED,
# then ONE newline (\r\n or \n\r count as one) is skipped; the newline BEFORE the closer is
# kept, exactly as the v1 parser keeps it. Before this the converter kept the newline after
# the opener too, so every fenced block a builder writes as ```\n…\n``` (system_audit's
# L1/L2 drill SQL, health_checks, cost_board, the close digest) rendered with a BLANK FIRST
# LINE. 19 of 732 real bodies differed from the legacy path for that reason alone; 0 after.
_PRE_RE = re.compile(r"```(?:[^\s`]+(?=\s))?(?:\r\n|\n\r|\n|\r)?(.*?)```", re.DOTALL)
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)")
_ITALIC_RE = re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Legacy-Markdown backslash escapes — the four characters Telegram's v1 parser reads as
# markup, and exactly what `briefing._md_escape` emits (`\_`, `\*`). Consumed OUTSIDE
# code/pre only, matching v1, where a backslash inside a code span is literal.
_ESCAPED_RE = re.compile(r"\\([_*`\[])")


def md_to_html(text: str) -> str:
    """Best-effort convert a legacy-Markdown Telegram string to safe HTML.

    Use at the send boundary to migrate a builder without rewriting it. Handles
    *bold* _italic_ `code` ```pre``` [text](url) and the v1 backslash escapes
    `\\_` `\\*` `` \\` `` `\\[` (#647: `_md_escape`d fields such as the EP alert's
    ⚖️ Acted block used to arrive with literal backslashes). Anything not matched is
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
    # 1b) Backslash-escaped markup chars become literal text (stashed so neither the
    #     link/emphasis regexes below nor a neighbouring `_` can pair with them).
    text = _ESCAPED_RE.sub(lambda m: _stash(esc(m.group(1))), text)
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


# ── Tag-aware chunking for HTML-mode sends (#652, 2026-09-19) ────────────────
# Telegram caps a message at 4096 chars, so `send_telegram_message` splits at the last blank
# line before 4000. On the legacy path that was harmless; on HTML a split that lands INSIDE
# an open <pre>/<b>/<a> leaves BOTH halves malformed and Telegram 400s both. The converted
# text is also longer than the Markdown it came from (escapes + tags), so a body that fit in
# one message as Markdown can cross the line as HTML — one real weekly review already does
# (3,593 chars -> 4,043). This chunker closes whatever is open at the split and reopens it at
# the head of the next chunk, and a hard split never lands inside a `<…>` token or an `&…;`
# entity. Pure function; briefing.py's plain-text chunker (`_chunk_plain`, for the
# unconverted `parse_mode=None` case) is untouched — it is NOT tag-aware, deliberately: a bare
# `<word>`-shaped substring in plain prose is not a real tag, and running it through THIS
# chunker's tag tracker would inject a bogus closer into what Telegram shows verbatim (#675).
_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^<>]*)?>")
_ENTITY_MAX = 10   # longest entity we emit is `&#x1F525;` (9 chars) — the back-off window


def _open_tags_before(text: str, pos: int) -> list[tuple[str, str]]:
    """Tags still open at `pos`, outermost first, as (name, full opening tag)."""
    stack: list[tuple[str, str]] = []
    for m in _TAG_RE.finditer(text, 0, pos):
        if m.group(1):
            if stack and stack[-1][0] == m.group(2):
                stack.pop()
        else:
            stack.append((m.group(2), m.group(0)))
    return stack


def _hard_split_point(text: str, at: int) -> int:
    """Back `at` off so it is not inside a `<…>` token or an `&…;` entity."""
    lt, gt = text.rfind("<", 0, at), text.rfind(">", 0, at)
    if lt > gt:                       # an unclosed '<' before `at` → inside a tag token
        at = lt
    amp = text.rfind("&", max(0, at - _ENTITY_MAX), at)
    if amp != -1 and ";" not in text[amp:at]:
        at = amp
    return at


def _seam(remaining: str, split_at: int) -> tuple[str, str, str]:
    """`(closers, openers, head)` for a candidate split point — the four lines the retry loop
    and its hard-cut fallback both need.

    Lifted on simplify review 2026-09-19: the loop and the `for/else` computed this identically,
    so a change to how closers are ordered or how `head` is trimmed had two sites to update and
    only one would have been noticed. `closers` closes every still-open tag in reverse order;
    `openers` reopens them at the top of the NEXT chunk; `head` is the finished chunk.
    """
    open_tags = _open_tags_before(remaining, split_at)
    closers = "".join(f"</{name}>" for name, _ in reversed(open_tags))
    openers = "".join(tag for _, tag in open_tags)
    return closers, openers, remaining[:split_at].strip() + closers


def chunk_html(text: str, limit: int = 4000) -> list[str]:
    """Split HTML-mode text into ≤`limit`-char chunks that each parse on their own.

    Same section preference as the legacy chunker (last blank line, then last newline,
    then a hard cut) and the same `.strip()` at the seam; the difference is that every
    tag open at the seam is closed at the end of the chunk and reopened at the start of
    the next, so a `<pre>` block or a bold span spanning the cut renders in both messages
    instead of failing both. A text at or under the limit is returned as-is, one chunk.
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        reserve = 0
        for _attempt in range(8):
            budget = limit - reserve
            split_at = remaining.rfind("\n\n", 0, budget)
            if split_at < 1:
                split_at = remaining.rfind("\n", 0, budget)
            if split_at < 1:
                split_at = _hard_split_point(remaining, budget)
            if split_at < 1:
                split_at = budget
            closers, openers, head = _seam(remaining, split_at)
            # the seam must shrink the text: a split at or before the reopened tags would spin
            if len(head) <= limit and split_at > len(openers):
                break
            reserve = len(closers) + max(0, len(head) - limit) + len(openers)
        else:                          # closers never fit — cut hard, well inside the limit
            split_at = _hard_split_point(remaining, limit - limit // 10)
            closers, openers, head = _seam(remaining, split_at)
        if head:
            chunks.append(head)
        remaining = openers + remaining[split_at:].strip()
    if remaining and remaining != "".join(tag for _, tag in _open_tags_before(remaining, len(remaining))):
        chunks.append(remaining)
    return chunks

