"""#121 — GATE: no operator-facing Telegram send may use the legacy-Markdown parse mode.

THE REGRESSION THIS CLOSES. #121 ("all operator-facing Telegram on the HTML layer") was filed
2026-05-29 and declared finished twice. Telegram's legacy parser reads every bare `_` as an italic
delimiter, so a ticker, a job id or a verdict like `TRAIL_TIGHTEN` in a Markdown-mode body 400s the
send. #647/#652/#675 moved `send_telegram_message` and its callers onto HTML — and the doc said
"Remaining legacy surfaces: none" — while ~15 sends in `channels/telegram.py` (the slash commands,
every drill-down button, the LLM reply path), `core/notifications.notify_owner` (every job-failure
page), `broker/telegram_confirm` (the trade proposal), `friday_watchlist`, `charts` and
`briefing.edit_telegram_message` (the hourly /hud refresh) still sent `parse_mode=Markdown`
through their OWN clients. Nothing derived the population, so nothing noticed.

HOW THIS GATE WORKS. `scripts/telegram_send_census.py` walks the AST of agents/ core/ channels/
shared/ and finds the sends by STRUCTURE (the canonical sender, python-telegram-bot calls, raw
Bot-API POSTs) — never by function name, and independent of any list. This file then asserts:

  1. the derivation is not vacuous — a set of NAMED senders must be found, and the AST census must
     agree with an independent text scan for `api.telegram.org` (a count floor proves nothing,
     [[derive-the-population-never-hand-list-it]]);
  2. the legacy Markdown parse mode is spelled NOWHERE except the allowlist in scripts/telegram_send_census.py, and every
     allowlist entry still exists (a stale allowlist is a hole);
  3. no plain send is built with Markdown syntax (the reader would see literal `*` and backticks);
  4. the scanner itself CATCHES each spelling — fed synthetic source, so the gate is shown able to
     fail, not merely observed passing.

A NEW module that sends `parse_mode="Markdown"` / `ParseMode.MARKDOWN` fails the build. To send
legacy-Markdown text: call `send_telegram_message(text)` (converts for you), or build the HTML
with `shared.telegram_format` and send `parse_mode="HTML"`.
"""
from __future__ import annotations

import functools
import textwrap

import pytest

from scripts import telegram_send_census as tsc

# The allowlists live in the census module so the CLI (`--legacy`) and this gate cannot disagree.
ALLOWED_MARKDOWN_SPELLINGS = tsc.ALLOWED_MARKDOWN_SPELLINGS
ALLOWED_PLAIN_WITH_MARKDOWN = tsc.ALLOWED_PLAIN_WITH_MARKDOWN


@functools.lru_cache(maxsize=None)
def _census_by_key():
    out: dict[str, list[tsc.Site]] = {}
    for s in tsc.census():
        out.setdefault(s.key, []).append(s)
    return out


# ── 1. the derivation finds the population (named members, not a count) ──────────────────────

# (path::function, kind, EXACT set of modes its sends of that kind are classified as). Each was
# migrated or surveyed by #121. A function that sends HTML and keeps a plain-words retry reads
# {html, plain}; that retry is `to_plain(html)` — words only, not Markdown.
NAMED_SENDERS = [
    ("channels/telegram.py::TelegramChannel._send_chunk", "ptb:reply_text", {"html", "plain"}),
    ("channels/telegram.py::TelegramChannel._reply_with_fallback", "ptb:reply_text", {"html", "plain"}),
    ("channels/telegram.py::TelegramChannel.send_message", "ptb:send_message", {"html", "plain"}),
    ("channels/telegram.py::TelegramChannel._handle_help", "ptb:reply_text", {"html"}),
    ("channels/telegram.py::TelegramChannel._handle_rules", "ptb:reply_text", {"html"}),
    ("channels/telegram.py::TelegramChannel._edit_or_resend", "ptb:edit_message_text", {"html"}),
    ("channels/telegram.py::TelegramChannel._handle_hud_drill_down", "ptb:reply_text", {"html", "plain"}),
    ("channels/telegram.py::TelegramChannel._handle_theme_promote_callback", "ptb:reply_text", {"html", "plain"}),
    ("channels/telegram.py::TelegramChannel._handle_spend", "ptb:reply_text", {"html", "plain"}),
    ("channels/webhooks.py::_handle_tradingview_alert", "ptb:send_message", {"html", "plain"}),
    ("core/notifications.py::notify_owner", "raw:sendMessage", {"html"}),
    ("agents/market_intelligence/charts.py::send_chart_mosaic", "raw:sendMessage", {"html"}),
    ("agents/market_intelligence/briefing.py::edit_telegram_message", "raw:editMessageText", {"dynamic"}),
    ("agents/market_intelligence/briefing.py::send_telegram_message._post", "raw:sendMessage", {"dynamic"}),
    ("agents/market_intelligence/broker/telegram_confirm.py::send_trade_proposal._post", "raw:sendMessage", {"dynamic"}),
    ("agents/market_intelligence/friday_watchlist.py::_send_with_keyboard", "send_telegram_message", {"converted-default"}),
    # plain by design — deliberately NOT markup (their docstrings say why)
    ("agents/market_intelligence/agent.py::_send_plain_with_keyboard", "raw:sendMessage", {"plain"}),
    ("channels/telegram.py::TelegramChannel.send_plain_message", "ptb:send_message", {"plain"}),
]


@pytest.mark.parametrize("key,kind,modes", NAMED_SENDERS, ids=[n[0].split("::")[1] for n in NAMED_SENDERS])
def test_the_derivation_finds_every_named_sender_in_the_mode_it_was_left_in(key, kind, modes):
    """MUTATION: reverting `_send_chunk` to `parse_mode=ParseMode.MARKDOWN` adds
    `legacy-markdown` to its modes and this fails; renaming/moving a sender without the census
    following it fails the lookup — the derivation going blind is itself a red."""
    sites = [s for s in _census_by_key().get(key, []) if s.kind == kind]
    assert sites, (
        f"the census did not find {kind} in {key} — either the sender moved or the derivation "
        f"stopped seeing it. Fix the derivation; do not delete the anchor.")
    assert {s.mode for s in sites} == modes, (key, [(s.line, s.mode) for s in sites])


def test_the_ast_census_and_an_independent_text_scan_agree_on_the_raw_senders():
    """The raw-HTTP class is found from f-string shapes in the AST. Cross-check it against the
    blunt text scan the probe-muzzle test uses: every module that names `api.telegram.org` must
    show up in the census with a raw site (the one exception is the hold, which only holds the
    host as a constant). A raw sender the AST pass cannot see — a `.format()` URL, a concatenation
    — would be named by the text scan and missing here."""
    from tests.test_probe_muzzle_covers_every_sender import _senders
    text_scan = {str(p.relative_to(tsc.REPO)) for p in _senders()} - {"shared/telegram_hold.py"}
    ast_scan = {s.path for s in tsc.census() if s.kind.startswith("raw:")}
    assert text_scan, "the text scan found no raw senders — it has gone vacuous"
    assert text_scan <= ast_scan, (
        f"modules that name api.telegram.org but have no raw site in the census: "
        f"{sorted(text_scan - ast_scan)}")


# ── 2. the legacy parse mode is spelled nowhere ──────────────────────────────────────────────

def test_no_send_uses_the_legacy_markdown_parse_mode():
    """THE GATE. Any `"Markdown"` / `"MarkdownV2"` constant, `ParseMode.MARKDOWN[_V2]` attribute
    or `.reply_markdown()` call under agents/ core/ channels/ shared/ fails the build unless it is
    in ALLOWED_MARKDOWN_SPELLINGS with a reason. MUTATION (run RED by hand, 2026-10-01): putting
    `parse_mode=ParseMode.MARKDOWN` back on `_send_chunk`, or `"parse_mode": "Markdown"` back in
    `notify_owner`'s payload, fails this and names the file:line."""
    offenders = [
        f"{path}:{line}  {func}  {what}"
        for path, func, line, what in tsc.legacy_markdown_markers()
        if f"{path}::{func}" not in ALLOWED_MARKDOWN_SPELLINGS
    ]
    assert not offenders, (
        "legacy-Markdown parse mode on the operator's Telegram — a bare `_` in any dynamic value "
        "400s the send, and the plain retry used to strip identifiers. Send via "
        "`send_telegram_message(text)` (converts for you) or build HTML with "
        "shared.telegram_format and send parse_mode=\"HTML\":\n  " + "\n  ".join(offenders))


def test_every_allowlisted_markdown_spelling_still_exists():
    """A stale allowlist entry is a hole: it would silently excuse a future send in the same
    function. MUTATION: deleting the `parse_mode == "Markdown"` fold from send_telegram_message
    fails this until the allowlist entry is deleted too."""
    present = {f"{path}::{func}" for path, func, _l, _w in tsc.legacy_markdown_markers()}
    stale = sorted(set(ALLOWED_MARKDOWN_SPELLINGS) - present)
    assert not stale, f"allowlist entries that no longer match anything: {stale}"
    assert all(r.strip() for r in ALLOWED_MARKDOWN_SPELLINGS.values())


def test_no_plain_send_is_built_with_markdown_syntax():
    """A send with NO parse_mode whose literal text carries `*bold*` / backticks / `_italic_`
    shows the reader the raw markers. (Dynamic text — a variable or a call — has no static form
    to inspect; those are the market agent's already-converted bodies and the plain-by-design
    `/why` / `/setup` senders.)"""
    offenders = [f"{s.path}:{s.line}  {s.func}  {s.kind}" for s in tsc.plain_sends_with_markdown_syntax()
                 if s.key not in ALLOWED_PLAIN_WITH_MARKDOWN]
    assert not offenders, "plain sends carrying Markdown syntax:\n  " + "\n  ".join(offenders)


# ── 3. the scanner can FAIL (fed synthetic source) ───────────────────────────────────────────

def _markers(src: str):
    return tsc.markers_in("synthetic.py", textwrap.dedent(src))


@pytest.mark.parametrize("label,src", [
    ("ptb kwarg ParseMode.MARKDOWN", """
        async def h(update):
            await update.message.reply_text("hi", parse_mode=ParseMode.MARKDOWN)
        """),
    ("string kwarg", """
        async def h(update):
            await update.message.reply_text("hi", parse_mode="Markdown")
        """),
    ("raw payload dict literal", """
        async def h(client):
            await client.post("https://x", json={"chat_id": 1, "text": "t", "parse_mode": "Markdown"})
        """),
    ("positional argument (what a keyword-only scan misses)", """
        async def h():
            await _post("Markdown")
        """),
    ("signature default (what a call-site scan misses)", """
        async def edit(chat_id, text, parse_mode: str = "Markdown"):
            ...
        """),
    ("MarkdownV2", """
        async def h(update):
            await update.message.reply_text("hi", parse_mode="MarkdownV2")
        """),
    ("reply_markdown helper", """
        async def h(update):
            await update.message.reply_markdown("hi")
        """),
])
def test_the_scanner_catches_each_spelling_of_the_legacy_parse_mode(label, src):
    """MUTATION: dropping the matching branch from `markers_in` makes the corresponding case
    return [] — each spelling has its own case because three drafts of the sibling probe-muzzle
    guard were each wrong in a different way."""
    assert _markers(src), f"the scanner missed: {label}"


@pytest.mark.parametrize("label,src", [
    ("HTML kwarg", """
        async def h(update):
            await update.message.reply_text("<b>x</b>", parse_mode=ParseMode.HTML)
        """),
    ("canonical sender default", """
        async def h():
            await send_telegram_message("*bold* ok_here")
        """),
    ("a docstring that merely mentions it", '''
        def f():
            """Used to send parse_mode="Markdown"; no longer does."""
        '''),
])
def test_the_scanner_does_not_cry_wolf(label, src):
    """The converse: a gate that fires on prose is a gate people allowlist into uselessness."""
    assert _markers(src) == [], label


def test_a_plain_send_built_with_markdown_syntax_is_flagged():
    src = textwrap.dedent('''
        async def h(update, name):
            await update.message.reply_text(f"Got it - I'm *{name}*.\\n`/setup TICKER`")
        async def ok(update):
            await update.message.reply_text("Market agent not available.")
        ''')
    hits = [s for s in tsc.sites_in("synthetic.py", src) if s.detail]
    assert [(s.func, s.mode) for s in hits] == [("h", "plain")]


def test_a_raw_sender_with_a_markdown_payload_is_classified_legacy():
    src = textwrap.dedent('''
        async def notify(client, bot_token, text):
            await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                              json={"text": text, "parse_mode": "Markdown"})
        async def fine(client, bot_token, text):
            await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                              json={"text": text, "parse_mode": "HTML"})
        ''')
    by_func = {s.func: s.mode for s in tsc.sites_in("synthetic.py", src)}
    assert by_func == {"notify": "legacy-markdown", "fine": "html"}
