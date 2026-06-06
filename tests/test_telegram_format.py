"""Tests for the shared Telegram HTML formatting layer (#121).

The escaping is the whole point — the #129/#130/#148 bug class is a dynamic value
containing markup that breaks the parse. Every helper must HTML-escape its content.
"""
from __future__ import annotations

from shared.telegram_format import esc, b, i, code, pre, link, render, md_to_html


def test_esc_escapes_html_metachars():
    assert esc("a < b & c > d") == "a &lt; b &amp; c &gt; d"
    # Quotes left readable
    assert esc("it's a \"quote\"") == "it's a \"quote\""


def test_helpers_escape_content():
    assert b("A&B") == "<b>A&amp;B</b>"
    assert i("x<y") == "<i>x&lt;y</i>"
    assert code("a & b") == "<code>a &amp; b</code>"
    assert pre("<tag>") == "<pre>&lt;tag&gt;</pre>"


def test_link_escapes_both_sides():
    out = link("R&D <here>", "https://x.com/?a=1&b=2")
    assert out == '<a href="https://x.com/?a=1&amp;b=2">R&amp;D &lt;here&gt;</a>'


def test_render_joins_lines():
    assert render([b("Hi"), code("AAPL")]) == "<b>Hi</b>\n<code>AAPL</code>"


def test_ticker_with_markup_is_safe():
    # The exact class that broke Markdown: a value with control chars.
    assert code("A*B_C`D") == "<code>A*B_C`D</code>"  # no escaping needed for these in HTML
    assert b("buy <AAPL> & hold") == "<b>buy &lt;AAPL&gt; &amp; hold</b>"


# ── md_to_html migration translator ──────────────────────────────────────────

def test_md_bold_italic():
    assert md_to_html("*bold* and _italic_") == "<b>bold</b> and <i>italic</i>"


def test_md_code_span_content_not_escaped_as_markdown():
    # `*` inside code must stay literal, not become bold.
    assert md_to_html("see `a*b*c`") == "see <code>a*b*c</code>"


def test_md_escapes_free_text_metachars():
    assert md_to_html("a < b & c") == "a &lt; b &amp; c"
    # bold around an escaped metachar
    assert md_to_html("*x<y*") == "<b>x&lt;y</b>"


def test_md_pre_block():
    assert md_to_html("```\nline1\nline2\n```") == "<pre>\nline1\nline2\n</pre>"


def test_md_link():
    assert md_to_html("[text](https://x.com)") == '<a href="https://x.com">text</a>'


def test_md_none_and_plain():
    assert md_to_html(None) == ""
    assert md_to_html("just plain text") == "just plain text"


def test_md_does_not_bold_midword_underscores():
    # snake_case must NOT become italic — the (?<!\w)_ guards prevent it.
    assert md_to_html("news_corpus_sparse") == "news_corpus_sparse"
