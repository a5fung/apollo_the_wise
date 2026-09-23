"""Weekly review must SEND as HTML, not legacy Markdown (2026-08-30 digest failure).

BUG: the Sunday digest's Telegram send failed legacy-Markdown parsing —
"Can't find end of the entity starting at byte offset 2315" — and Telegram's 400
sent it down `send_telegram_message`'s plain-text fallback. The operator still got a
message, so nothing alarmed; he just read it stripped of every heading and emphasis.
Found during the #606 Sunday-review read.

WHY THE FIX SITS AT THE SEND BOUNDARY, not in the renderers: the digest is
assembled from ~13 independently-built sections carrying audit summaries, tickers,
catalyst text and raw error strings. Legacy Markdown has no safe escape for a
dynamic value, so one stray `*`, `_` or backtick in ANY section breaks the whole
message. Escaping each renderer leaves the fourteenth to reintroduce it; converting
once at the boundary (`shared.telegram_format.md_to_html`) covers sections nobody
has written yet — this is the exact migration path that module's own docstring
documents.

The send wiring itself (ONE send, `parse_mode="HTML"`, the head converted through
`md_to_html`, the fold as an expandable quote) is pinned BEHAVIOURALLY in
`tests/test_weekly_review_report_layout.py::test_run_weekly_review_sends_the_folded_html_once`
— #662 replaced the source-inspection pin that used to live here. The test below pins
that the converter the send path calls actually survives the shapes this digest emits.
"""
from __future__ import annotations

from shared.telegram_format import md_to_html


def test_md_to_html_survives_the_real_08_30_failure_shapes():
    """MUTATION TARGET: any change to `md_to_html`'s escaping order or regexes that
    lets a bare `&`/`<` through unescaped, or that leaves `<b>`/`<i>` unbalanced.

    These are not a happy-path smoke test — each string is a shape this digest
    actually emits (an audit count with a bare `*`, a snake_case identifier, an
    unclosed backtick from truncated SQL, raw `&`/`<` in prose) that legacy Markdown
    could not parse. If `md_to_html` regresses to letting one of these produce
    unbalanced tags or an unescaped `&`/`<`, Telegram's HTML parser 400s exactly the
    way legacy Markdown did on 2026-08-30, just on the new code path.
    """
    failure_shapes = [
        "stop_update_failed *4, last seen 1d ago",   # bare * before a digit
        "event mi_ep_alerts_source_gap fired",       # underscores inside an identifier
        "query `SELECT * FROM x died",               # unclosed backtick
        "M&A <threshold> breached",                  # raw & and < (invalid in HTML mode)
        "*balanced bold* still works",                # real markup must still convert
    ]

    for shape in failure_shapes:
        out = md_to_html(shape)

        assert out.count("<b>") == out.count("</b>"), (
            f"md_to_html({shape!r}) produced unbalanced <b> tags ({out!r}) — Telegram's "
            "HTML parser will 400 on this exactly like it did on the 2026-08-30 digest."
        )
        assert out.count("<i>") == out.count("</i>"), (
            f"md_to_html({shape!r}) produced unbalanced <i> tags ({out!r}) — Telegram's "
            "HTML parser will 400 on this exactly like it did on the 2026-08-30 digest."
        )

        stripped = out.replace("&amp;", "").replace("&lt;", "").replace("&gt;", "")
        assert "&" not in stripped, (
            f"md_to_html({shape!r}) left a bare & unescaped ({out!r}) — Telegram's "
            "HTML parser treats & as the start of an entity and 400s on a malformed one."
        )

    # The converter must still format real markup, not just escape everything into
    # inert text — a converter that only escapes would pass every assertion above
    # while silently degrading every digest to plain text again.
    assert md_to_html("*balanced bold* still works") == "<b>balanced bold</b> still works", (
        "md_to_html stopped converting real *bold* markup into <b> tags — a "
        "converter that only escapes would make every digest read as unformatted "
        "plain text, the same operator-visible symptom as the original bug."
    )
