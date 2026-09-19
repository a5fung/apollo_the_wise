"""send_telegram_message Markdown-400 fallback — offset-snippet diagnostics.

2026-07-16: the evening brief hit "can't find end of the entity starting at
byte offset 4205"; the audit row logged only chunk[:300], so the offending
section was undiagnosable. The 400 handler now decodes the UTF-8 byte offset
Telegram reports and logs the surrounding snippet in the warning + both audit
events. These tests pin: (1) the snippet is cut at the BYTE offset (multibyte
content before the culprit must not skew it), (2) the plain-text retry still
delivers, (3) a body without an offset degrades gracefully (empty snippet).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import briefing


class _Resp:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self.text = json.dumps(body or {})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status on failure response")


class _FakeClient:
    """httpx.AsyncClient stand-in returning queued responses per post()."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []

    def __call__(self, *a, **k):   # constructor shim: httpx.AsyncClient(timeout=15)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posts.append(json)
        return self._responses.pop(0)


def _entity_error_body(offset: int) -> dict:
    return {"ok": False, "error_code": 400,
            "description": f"Bad Request: can't parse entities: Can't find end "
                           f"of the entity starting at byte offset {offset}"}


@pytest.mark.asyncio
async def test_markdown_400_logs_snippet_at_byte_offset(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")

    # Multibyte content BEFORE the culprit: 50 emoji = 200 UTF-8 bytes but only
    # 50 chars — a char-indexed cut would land far from the marker.
    prefix = "🔥" * 50
    text = prefix + "CULPRIT_MARKER stray * here"
    offset = text.encode().index(b"CULPRIT_MARKER")

    fake = _FakeClient([_Resp(400, _entity_error_body(offset)), _Resp(200, {"ok": True})])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message(text)

    assert ok is True
    assert len(fake.posts) == 2                      # markdown try + plain retry
    assert "parse_mode" not in fake.posts[1]          # retry was plain text
    event, _summary, detail = audit.await_args.args[:3]
    assert event == "telegram_markdown_fallback"
    assert "CULPRIT_MARKER" in detail                 # the snippet names the culprit


@pytest.mark.asyncio
async def test_utf16_offset_interpretation_also_captured(monkeypatch):
    """If Telegram's reported offset is UTF-16 code units (its documented
    entity convention), the UTF-8-byte window lands deep in preceding emoji and
    misses the culprit — the u16 window must still capture it."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")

    prefix = "🔥" * 80                      # 160 UTF-16 units, 320 UTF-8 bytes
    text = prefix + "CULPRIT16 stray * here"
    utf16_offset = len(prefix.encode("utf-16-le")) // 2   # marker at unit 160

    fake = _FakeClient([_Resp(400, _entity_error_body(utf16_offset)), _Resp(200, {"ok": True})])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message(text)

    assert ok is True
    detail = audit.await_args.args[2]
    assert "CULPRIT16" in detail            # the u16 window names the culprit


@pytest.mark.asyncio
async def test_markdown_400_without_offset_degrades_gracefully(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")

    fake = _FakeClient([
        _Resp(400, {"ok": False, "error_code": 400, "description": "Bad Request: message is too long"}),
        _Resp(200, {"ok": True}),
    ])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message("*hello*")

    assert ok is True
    detail = audit.await_args.args[2]
    assert "offset_snippet=''" in detail              # no offset → empty snippet, no crash


def test_quality_warnings_banner_neutralizes_snake_case():
    """#477 class, 2nd instance: data_quality.py's {step}/{metric} fallback puts
    snake_case into the DATA QUALITY banner — one bare underscore breaks the
    whole chunk's entity parity. The banner escapes dynamic tokens via the
    canonical _md_escape (#148): every `_`/`*` must be backslash-escaped."""
    import re as _re
    out = briefing._format_quality_warnings(
        ["rs_engine/scored_count: 12 (expected 9000)", "Sector coverage: 41% (threshold 80%)"])
    body = out.split("\n", 1)[1]        # skip the deliberate *DATA QUALITY* header markup
    assert not _re.search(r"(?<!\\)[_*]", body), f"banner leaked a bare entity char: {body}"


# ── #652: the DEFAULT converts legacy Markdown to HTML — a sender that does nothing special
#    cannot 400 on an identifier; an explicit mode is never converted ─────────────────────

_ACCEPTANCE_SQL = "SELECT * FROM mi_live_trades WHERE stop_order_id IS NULL"


def _well_formed(chunk: str) -> None:
    from tests.test_647_machine_text_alerts_on_html_layer import _assert_well_formed_telegram_html
    _assert_well_formed_telegram_html(chunk)


@pytest.mark.asyncio
@pytest.mark.parametrize("shape,body", [
    ("bare", _ACCEPTANCE_SQL),
    ("under a *bold* header", "*L2 anomaly* — stop drift\n\n" + _ACCEPTANCE_SQL),
    ("fenced", "*Revert:*\n```\n" + _ACCEPTANCE_SQL + "\n```"),
])
async def test_unmodified_default_sender_delivers_the_acceptance_sql_on_the_first_send(
        monkeypatch, shape, body):
    """The task's WOULD-FAIL-IF, verbatim: `SELECT * FROM mi_live_trades WHERE stop_order_id
    IS NULL` through a sender that passes NO parse_mode. Under the old "Markdown" default the
    bare `*` and the three `_` 400'd the first send and the body only arrived on the plain
    retry, headers stripped. Now the FIRST send is HTML, well-formed, and carries the SQL
    verbatim — underscores and `*` included. MUTATION TARGET: the default back to
    `parse_mode: str = "Markdown"` (verified: all three shapes fail — parse_mode is
    "Markdown" and the fenced shape has no <pre>)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    fake = _FakeClient([_Resp(200, {"ok": True})])
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        ok = await briefing.send_telegram_message(body)          # nothing special passed
    assert ok is True and len(fake.posts) == 1, shape
    sent = fake.posts[0]
    assert sent["parse_mode"] == "HTML", shape
    assert _ACCEPTANCE_SQL in sent["text"], (shape, sent["text"])
    _well_formed(sent["text"])
    if shape == "fenced":
        assert "<pre>" + _ACCEPTANCE_SQL in sent["text"], "the block must open ON the SQL (#652 step 1)"
    if shape.startswith("under"):
        assert sent["text"].startswith("<b>L2 anomaly</b>"), "the header survives as real bold"


@pytest.mark.asyncio
async def test_default_path_400_still_lands_plain_with_identifiers_intact_and_names_its_mode(monkeypatch):
    """If Telegram ever rejects a converted body, the plain retry must carry the identifiers
    byte-for-byte (tags stripped, entities unescaped) and the audit row must say which mode
    failed — `mode=HTML(default)` is how a converter defect is told apart from a hand-built
    HTML body during verify-live. MUTATION TARGET: `_to_plain` routing the HTML branch through
    `_strip_markdown_markers` (a `<b>` leaks), or dropping `mode=` from the audit detail."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    body = "*Revert:* M&A < threshold\n```\n" + _ACCEPTANCE_SQL + "\n```"
    fake = _FakeClient([_Resp(400, _entity_error_body(3)), _Resp(200, {"ok": True})])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message(body)
    assert ok is True and len(fake.posts) == 2
    assert fake.posts[0]["parse_mode"] == "HTML"
    assert "parse_mode" not in fake.posts[1]
    plain = fake.posts[1]["text"]
    assert _ACCEPTANCE_SQL in plain and "M&A < threshold" in plain and "<" not in plain.replace("M&A < ", "")
    event, summary, detail = audit.await_args.args[:3]
    assert event == "telegram_markdown_fallback"             # the verify-live row keeps its name
    assert "mode=HTML(default)" in detail and "HTML(default)" in summary


@pytest.mark.asyncio
async def test_explicit_html_is_passed_through_never_converted_twice(monkeypatch):
    """A caller that built HTML (or converted it itself) and SAID so must reach Telegram
    byte-identical — converting again turns `<b>` into `&lt;b&gt;` and `&amp;` into
    `&amp;amp;`. MUTATION TARGET: deciding to convert on `parse_mode == "HTML"` or on
    truthiness instead of the sentinel identity (verified: this test fails)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    body = "<b>Full exit FAILED</b> — M&amp;A\n<pre>{\"existing_qty\": 3}</pre> <code>x_y</code>"
    fake = _FakeClient([_Resp(200, {"ok": True})])
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        ok = await briefing.send_telegram_message(body, parse_mode="HTML")
    assert ok is True
    assert fake.posts[0]["text"] == body and fake.posts[0]["parse_mode"] == "HTML"


def _explicit_html_bodies_from_the_0918_corpus() -> list[str]:
    """Every unique body a REAL explicit-HTML site sent while the suite ran on 2026-09-18
    (scripts/probes/_652_corpus_tests.jsonl — a data capture, read as data). These are the
    29 surfaces already on HTML: the population the 732-body render check could not vouch
    for, so they are replayed through the flipped sender here."""
    import json as _json
    from pathlib import Path as _P
    path = _P(__file__).resolve().parents[1] / "scripts/probes/_652_corpus_tests.jsonl"
    seen, out = set(), []
    for line in path.read_text(encoding="utf-8").splitlines():
        r = _json.loads(line)
        if r.get("parse_mode") == "HTML" and r["body"] not in seen:
            seen.add(r["body"]); out.append(r["body"])
    return out


@pytest.mark.asyncio
async def test_every_real_explicit_html_body_reaches_telegram_byte_identical_after_the_flip(monkeypatch):
    """The 45 unique real bodies from the sites that were ALREADY on HTML before #652. The
    flip must not touch them: each is posted exactly as given, with parse_mode HTML, in one
    chunk (none exceeds 4000). A second conversion, a chunker change, or a default that
    ignores an explicit mode all fail this. MUTATION TARGET: the same as the test above."""
    bodies = _explicit_html_bodies_from_the_0918_corpus()
    assert len(bodies) >= 40, "the captured corpus is missing — the risk-set replay has nothing to replay"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    for body in bodies:
        fake = _FakeClient([_Resp(200, {"ok": True})] * 3)
        with patch.object(briefing.httpx, "AsyncClient", fake), \
             patch.object(briefing, "log_audit_event", AsyncMock()):
            ok = await briefing.send_telegram_message(body, parse_mode="HTML")
        assert ok is True
        assert len(fake.posts) == 1 and fake.posts[0]["text"] == body, body[:80]
        assert fake.posts[0]["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_explicit_markdown_is_the_opt_in_for_raw_legacy_and_none_means_plain(monkeypatch):
    """`parse_mode="Markdown"` (scheduler._backup_health_check_job's three sites) sends the
    raw legacy body — `*` and backticks untouched — with parse_mode Markdown, chunked and
    backstopped exactly as before the flip; `parse_mode=None` sends plain text with NO
    parse_mode key. MUTATION TARGET: converting on anything but the sentinel."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    body = "🚨 *Apollo off-site backup MISSING*\nNo `gdrive_backup_success` event ever recorded."
    fake = _FakeClient([_Resp(200, {"ok": True})])
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        assert await briefing.send_telegram_message(body, parse_mode="Markdown") is True
    assert fake.posts[0] == {"chat_id": 42, "text": body, "disable_web_page_preview": True,
                             "parse_mode": "Markdown"}
    # the legacy chunker is still the one that splits an explicit-Markdown body
    long_md = "A" * 3000 + "\n\n" + "B" * 3000
    fake = _FakeClient([_Resp(200, {"ok": True})] * 2)
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        assert await briefing.send_telegram_message(long_md, parse_mode="Markdown") is True
    assert [p["text"] for p in fake.posts] == ["A" * 3000, "B" * 3000]
    fake = _FakeClient([_Resp(200, {"ok": True})])
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        assert await briefing.send_telegram_message("plain *stars*", parse_mode=None) is True
    assert fake.posts[0]["text"] == "plain *stars*" and "parse_mode" not in fake.posts[0]


@pytest.mark.asyncio
async def test_default_path_long_message_splits_tag_aware_and_keeps_markup_on_the_last_chunk(monkeypatch):
    """A default sender writing a fenced table longer than one message (the shape of the
    row-count drift and detector-liveness digests): after conversion each chunk must parse on
    its own — `<pre>` closed at the seam and reopened — and the inline keyboard rides ONLY
    the last chunk, as before. MUTATION TARGET: chunking HTML with `_chunk_legacy` (an
    orphaned `<pre>` fails the well-formed check)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    body = "*Row-count drift*\n```\n" + "\n".join(f"mi_table_{n}  {n * 7}" for n in range(500)) + "\n```"
    assert len(body) > 4000
    markup = {"inline_keyboard": [[{"text": "ok", "callback_data": "x"}]]}
    fake = _FakeClient([_Resp(200, {"ok": True})] * 5)
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        assert await briefing.send_telegram_message(body, reply_markup=markup) is True
    assert len(fake.posts) >= 2
    for post in fake.posts:
        assert post["parse_mode"] == "HTML" and len(post["text"]) <= 4000
        _well_formed(post["text"])
    assert all("reply_markup" not in p for p in fake.posts[:-1]) and "reply_markup" in fake.posts[-1]
    assert "mi_table_499" in fake.posts[-1]["text"]

