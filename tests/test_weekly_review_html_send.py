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

Test 1 pins the wiring in `run_weekly_review` itself (source-inspection, since the
function is DB-bound end to end and not cheaply exercised via a live call). Test 2
pins that the converter it calls actually survives the shapes this digest emits.
"""
from __future__ import annotations

import inspect
import re

from agents.market_intelligence import system_review
from shared.telegram_format import md_to_html


def test_weekly_review_sends_via_md_to_html_as_html():
    """MUTATION TARGET: dropping `parse_mode="HTML"` from the send call, OR reverting
    to a bare `send_telegram_message(message)` without `md_to_html`.

    Dropping `parse_mode="HTML"` makes Telegram render the `<b>`/`<i>` tags `md_to_html`
    produces as literal text in the digest. Dropping `md_to_html` returns the send to
    the unescapable legacy-Markdown path that broke on 2026-08-30 — the bug this test
    exists to keep fixed.
    """
    src = inspect.getsource(system_review.run_weekly_review)

    assert "md_to_html(message)" in src, (
        "run_weekly_review no longer converts the digest through md_to_html before "
        "sending — the send is back on the unescapable legacy-Markdown path that "
        "failed to parse on 2026-08-30 and silently fell back to stripped plain text."
    )
    assert 'parse_mode="HTML"' in src, (
        "run_weekly_review's send is missing parse_mode=\"HTML\" — Telegram will "
        "render the md_to_html output's <b>/<i> tags as literal text instead of "
        "formatting, degrading the digest exactly like the bug this guards."
    )
    assert not re.search(r"send_telegram_message\(message\)(?!\w)", src), (
        "a bare send_telegram_message(message) call is back in run_weekly_review — "
        "the fix requires md_to_html(message) to be the only argument sent, not "
        "supplemented alongside it."
    )


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
