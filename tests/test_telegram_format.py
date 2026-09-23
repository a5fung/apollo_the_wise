"""Tests for the shared Telegram HTML formatting layer (#121).

The escaping is the whole point — the #129/#130/#148 bug class is a dynamic value
containing markup that breaks the parse. Every helper must HTML-escape its content.
"""
from __future__ import annotations

from shared.telegram_format import esc, b, i, code, pre, link, render, md_to_html, chunk_html


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
    """#652 (2026-09-19): the newline after the opening fence is DROPPED, mirroring Telegram's
    legacy-Markdown parser; the newline before the closing fence is kept, as v1 keeps it. Before
    the patch this pinned `<pre>\\nline1…` — a code block that opened with a blank line on every
    L1/L2 audit page already on the HTML layer. MUTATION TARGET: restoring `_PRE_RE` to
    ```` ```(.*?)``` ```` (verified: this test fails on that mutation)."""
    assert md_to_html("```\nline1\nline2\n```") == "<pre>line1\nline2\n</pre>"


def test_md_pre_block_mirrors_the_legacy_fence_rule_shape_by_shape():
    """#652: every fence shape the v1 parser handles, rendered the way v1 renders it (tdlib
    `parse_markdown`: skip an optional language token, then ONE newline; keep the rest). The
    task's own repro is the first case — the exact body `system_audit._format_l2_alert` writes.
    MUTATION TARGET: restoring the old `_PRE_RE` — the first three cases fail on it."""
    sql = "SELECT * FROM mi_live_trades WHERE stop_order_id IS NULL"
    assert md_to_html(f"*L2 anomaly* — stop drift\n\n```\n{sql}\n```") == (
        f"<b>L2 anomaly</b> — stop drift\n\n<pre>{sql}\n</pre>")
    # a language token is dropped (v1 records it as the entity's language; no production fence
    # carries one — 0 in the 2026-09-18 census — so dropping it is the safe mirror)
    assert md_to_html("```sql\nx\n```") == "<pre>x\n</pre>"
    # \r\n after the opener counts as ONE newline, exactly as tdlib skips it
    assert md_to_html("```\r\nx\r\n```") == "<pre>x\r\n</pre>"
    # only ONE newline is skipped — a deliberate blank first line survives
    assert md_to_html("```\n\nx\n```") == "<pre>\nx\n</pre>"
    # a bare word between fences is CONTENT, not a language (nothing follows it)
    assert md_to_html("```abc```") == "<pre>abc</pre>"
    # a language followed by a space, not a newline: the token goes, the space stays (v1)
    assert md_to_html("```sql SELECT```") == "<pre> SELECT</pre>"
    # content is still HTML-escaped inside the block
    assert md_to_html("```\na < b & c\n```") == "<pre>a &lt; b &amp; c\n</pre>"


def test_md_link():
    assert md_to_html("[text](https://x.com)") == '<a href="https://x.com">text</a>'


def test_md_none_and_plain():
    assert md_to_html(None) == ""
    assert md_to_html("just plain text") == "just plain text"


def test_md_does_not_bold_midword_underscores():
    # snake_case must NOT become italic — the (?<!\w)_ guards prevent it.
    assert md_to_html("news_corpus_sparse") == "news_corpus_sparse"


# ── chunk_html — the tag-aware splitter the HTML send path uses (#652) ──────────────


def _well_formed(chunk: str) -> None:
    from tests.test_647_machine_text_alerts_on_html_layer import _assert_well_formed_telegram_html
    _assert_well_formed_telegram_html(chunk)


def _visible(chunk: str) -> str:
    import html as _h, re as _r
    return _h.unescape(_r.sub(r"<[^>]+>", "", chunk))


def test_chunk_html_returns_short_text_untouched():
    assert chunk_html("short") == ["short"]
    assert chunk_html("x" * 4000) == ["x" * 4000]


def test_chunk_html_closes_and_reopens_a_pre_block_that_spans_the_cut():
    """A drill-SQL / table block longer than one message. The legacy chunker cut it at the
    last newline and left `<pre>` open in one half and `</pre>` orphaned in the other — both
    400. MUTATION TARGET: dropping the closers/openers (`closers = openers = ""`) — every
    assertion but the length one fails; verified."""
    body = "<b>Head</b>\n\n<pre>" + "\n".join(f"row_{n} value_{n}" for n in range(600)) + "\n</pre>\n\nTail"
    chunks = chunk_html(body)
    assert len(chunks) >= 3 and all(len(c) <= 4000 for c in chunks)
    for c in chunks:
        _well_formed(c)
    middle = [c for c in chunks if "row_300 " in c][0]
    assert middle.startswith("<pre>") and middle.endswith("</pre>")
    # nothing the operator reads is lost at the seams (only the whitespace stripped there)
    assert _visible("".join(chunks)).replace("\n", "") == _visible(body).replace("\n", "")


def test_chunk_html_reopens_nested_tags_in_order_and_a_link_with_its_href():
    """Nested <b><i> at the seam must close inner-first and reopen outer-first; an <a> must
    come back WITH its href or the second half is a dead link. MUTATION TARGET: reopening
    with `f"<{name}>"` instead of the captured tag (the href assertion fails)."""
    chunks = chunk_html("<b>B <i>I " + "x" * 5000 + "</i></b>")
    assert [c[:9] for c in chunks] == ["<b>B <i>I", "<b><i>xxx"]
    assert all(c.endswith("</i></b>") for c in chunks)
    for c in chunks:
        _well_formed(c)
    link_body = '<a href="https://x.com/a?b=1&amp;c=2">' + "l" * 4500 + "</a>"
    chunks = chunk_html(link_body)
    assert len(chunks) == 2
    assert chunks[1].startswith('<a href="https://x.com/a?b=1&amp;c=2">')
    for c in chunks:
        _well_formed(c)


def test_chunk_html_hard_cut_never_lands_inside_an_entity_or_a_tag_token():
    """No newline anywhere, so the splitter must cut hard — and a cut inside `&amp;` or
    inside `<a href=…>` is a guaranteed 400. MUTATION TARGET: `_hard_split_point` returning
    `at` unchanged (the entity assertion fails; verified)."""
    import re as _r
    chunks = chunk_html("<b>" + "&amp;" * 1700 + "</b>")
    assert len(chunks) == 3
    for c in chunks:
        _well_formed(c)
        assert _r.fullmatch(r"<b>(&amp;)+</b>", c), c[:20] + "…" + c[-20:]
    # the 4000th char falls INSIDE the `<a href=…>` token: the cut must back off to before `<`
    straddle = "p" * 3990 + '<a href="https://example.com/very/long/path">t</a>' + "q" * 50
    chunks = chunk_html(straddle)
    assert len(chunks) == 2 and chunks[0] == "p" * 3990
    assert chunks[1].startswith('<a href="https://example.com/very/long/path">t</a>')
    for c in chunks:
        _well_formed(c)


def test_chunk_html_terminates_and_keeps_the_legacy_section_preference():
    """A 20k-char text with no newlines finishes (progress is guaranteed at every seam), and
    the same input the legacy chunker split at the blank line still splits there."""
    chunks = chunk_html("z" * 20000)
    assert sum(len(c) for c in chunks) == 20000 and all(len(c) <= 4000 for c in chunks)
    assert chunk_html("A" * 3000 + "\n\n" + "B" * 3000) == ["A" * 3000, "B" * 3000]

