"""#121 — every operator-facing legacy-Markdown send is on the HTML layer, DELIVERY ONLY.

WHAT WAS WRONG. #647/#652/#675 put `send_telegram_message` (and everything that calls it) on HTML.
What they could not reach were the senders that talk to Telegram through THEIR OWN client:

    channels/telegram.py   ~15 `ParseMode.MARKDOWN` sends — /help /rules /status /setup, the
                           onboarding replies, every market slash command (`_reply_with_fallback`),
                           every drill-down button (eps/trades/ideas/hud/tpromo) and the LLM reply
                           path (`_send_chunk`), plus a second, weaker copy of `md_to_html`
    core/notifications     `notify_owner` — EVERY scheduled-job-failure page
    broker/telegram_confirm `send_trade_proposal` — the staged-trade FYI
    briefing               `edit_telegram_message` — the hourly refresh of the pinned /hud
    friday_watchlist       `_send_with_keyboard` — its own POST, no chunking
    charts                 the RS-leaders link fallback

A bare `_` in any dynamic value (a theme, a ticker, a job id, an exception text, a model id) is an
italic delimiter to Telegram's v1 parser: the send 400s, and the old plain retries then deleted
every underscore from the identifiers they carried (`re.sub(r"[*_`\\[\\]]", "", text)`).

THE FIX (same shape as #647): convert legacy Markdown ONCE at the send boundary (`md_to_html`),
send `parse_mode=HTML`, and retry on a rejection with `to_plain` (tags removed, entities
unescaped — it cannot touch an identifier). The words a reader sees do not change: bold stays
bold, code stays code.

Every test renders the REAL message through the REAL send path with a body containing the
underscores / asterisks / `&` / `<` that used to 400, and asserts (a) the HTML layer was used,
(b) the body is well-formed Telegram HTML, (c) the identifiers survived, (d) no pipe table
(CLAUDE.md: Telegram cannot render them). The mutation that reddens each is named in its docstring.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from telegram.constants import ParseMode

from channels.telegram import TelegramChannel
from shared.telegram_format import md_to_html, to_plain
from tests.conftest import fake_httpx_client
from tests.test_647_machine_text_alerts_on_html_layer import (
    _assert_well_formed_telegram_html as _well_formed,
    _html_backstop,
)

_PIPE_TABLE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)

# the shapes that 400'd: identifiers with underscores, an asterisk run, & and <.
_IDS = ("ep_delayed_residual_scan", "existing_qty", "claude-opus-5-5", "BRK_B", "stop_order_id")


def _no_pipe_table(text: str) -> None:
    assert not _PIPE_TABLE.search(text), f"a pipe table — Telegram cannot render it:\n{text}"


# ── harness ──────────────────────────────────────────────────────────────────────────────────

def _channel() -> TelegramChannel:
    ch = TelegramChannel.__new__(TelegramChannel)      # no live bot token needed
    ch._secrets = SimpleNamespace(telegram_allowed_user_ids=[42], internal_api_secret="s")
    return ch


def _update(args=None):
    sent = SimpleNamespace(message_id=7)
    msg = MagicMock()
    msg.reply_text = AsyncMock(return_value=sent)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42),
                             effective_chat=SimpleNamespace(id=42), message=msg)
    return update, SimpleNamespace(args=args or []), msg


def _query(*, edit_raises: BaseException | None = None):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    q = SimpleNamespace(from_user=SimpleNamespace(id=42), message=msg,
                        edit_message_text=AsyncMock(side_effect=edit_raises))
    return q, msg


def _only_html_send(mock: AsyncMock) -> str:
    """The text of the ONE reply, asserting it went out on the HTML layer and is well-formed."""
    mock.assert_awaited_once()
    assert mock.await_args.kwargs.get("parse_mode") == ParseMode.HTML, mock.await_args
    text = mock.await_args.args[0]
    _well_formed(text)
    _no_pipe_table(text)
    return text


# ── 0. the shared pieces ─────────────────────────────────────────────────────────────────────

def test_to_plain_is_tags_out_entities_unescaped_and_leaves_identifiers_alone():
    """MUTATION: `to_plain` that strips `_` pairs (the old `re.sub(r"[*_`\\[\\]]", "", …)`) eats
    `existing_qty`; one that skips `html.unescape` leaks `&lt;`."""
    html = md_to_html("*Full exit FAILED*: `existing_qty` < 2 & held_for_orders")
    assert to_plain(html) == "Full exit FAILED: existing_qty < 2 & held_for_orders"


def test_the_channels_converter_is_the_shared_one():
    """#121 consolidation: `TelegramChannel._md_to_html` used to be a near-copy with no code-span
    stash, no link handling and no backslash escapes. MUTATION: restoring a private body."""
    assert TelegramChannel._md_to_html is md_to_html
    out = TelegramChannel._md_to_html("run `ep_scan` for [the board](https://x.test/a_b) *now*")
    assert "<code>ep_scan</code>" in out and "<b>now</b>" in out and 'href="https://x.test/a_b"' in out
    _well_formed(out)


# ── 1. channels/telegram.py — python-telegram-bot sends ──────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_confirmations_go_out_as_html_split_tag_aware():
    """The orchestrator's confirmation path. MUTATION: `parse_mode=ParseMode.MARKDOWN` back on
    `TelegramChannel.send_message` — `existing_qty` + `held_for_orders` are four bare `_`."""
    ch = _channel()
    bot = SimpleNamespace(send_message=AsyncMock())
    ch._app = SimpleNamespace(bot=bot)
    await ch.send_message(42, "*Confirm exit?*\nexisting_qty=2 held_for_orders=2\n```\nSELECT stop_order_id FROM t;\n```")
    bot.send_message.assert_awaited_once()
    kw = bot.send_message.await_args.kwargs
    assert kw["parse_mode"] == ParseMode.HTML
    _well_formed(kw["text"])
    assert "<b>Confirm exit?</b>" in kw["text"] and "existing_qty=2 held_for_orders=2" in kw["text"]
    assert "<pre>SELECT stop_order_id FROM t;\n</pre>" in kw["text"]


@pytest.mark.asyncio
async def test_send_message_retries_as_plain_words_and_keeps_every_underscore():
    """MUTATION: the old fallback `re.sub(r"[*_`\\[\\]]", "", text)` — delivers `existingqty`."""
    ch = _channel()
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[Exception("400 can't parse"), None]))
    ch._app = SimpleNamespace(bot=bot)
    await ch.send_message(42, "*Exit FAILED*: `existing_qty` held_for_orders")
    first, second = bot.send_message.await_args_list
    assert first.kwargs["parse_mode"] == ParseMode.HTML
    assert "parse_mode" not in second.kwargs
    assert second.kwargs["text"] == "Exit FAILED: existing_qty held_for_orders"


@pytest.mark.asyncio
async def test_setup_usage_reply_is_html_code():
    ch = _channel()
    update, ctx, msg = _update(args=[])
    await ch._handle_setup(update, ctx)
    assert _only_html_send(msg.reply_text) == "Usage: <code>/setup TICKER [days]</code>"


@pytest.mark.asyncio
async def test_onboarding_replies_escape_what_the_operator_typed(monkeypatch):
    """The operator NAMES the assistant and DESCRIBES its personality — both free text. A name
    like `my_bot*` was interpolated raw into `*{name}*`. MUTATION: `f"*{name}*"` back in."""
    import core.memory
    monkeypatch.setattr(core.memory, "save_memory", AsyncMock())
    monkeypatch.setattr(core.memory, "search_memories",
                        AsyncMock(return_value=[SimpleNamespace(content="Apollo_Prime <v2>")]))
    ch = _channel()
    ch._set_onboarding_state = AsyncMock()
    ch._clear_onboarding_state = AsyncMock()

    update, _ctx, msg = _update()
    await ch._start_onboarding(update, 42)
    assert "<i>(Default: Apollo — just send a period to keep it)</i>" in _only_html_send(msg.reply_text)

    update, _ctx, msg = _update()
    await ch._handle_onboarding_reply(update, 42, "my_bot*x & <co>", "awaiting_name")
    text = _only_html_send(msg.reply_text)
    assert "I'm <b>my_bot*x &amp; &lt;co&gt;</b>" in text
    assert "<i>Examples:</i>" in text and "<code>Concise and direct. No filler words.</code>" in text

    update, _ctx, msg = _update()
    await ch._handle_onboarding_reply(update, 42, "terse & fast_ <ok>", "awaiting_persona")
    text = _only_html_send(msg.reply_text)
    assert "<b>Name:</b> Apollo_Prime &lt;v2&gt;" in text
    assert "<b>Personality:</b> terse &amp; fast_ &lt;ok&gt;" in text


@pytest.mark.asyncio
async def test_help_and_rules_render_as_html_with_the_doc_name_intact(monkeypatch):
    """/help and /rules are static Markdown. Two real defects the HTML layer fixes by moving
    the markup, not the words: `EP_TRADING_RULES.md` (two `_`) was rendered `EP` + italic
    `TRADING` + `RULES.md` under v1, and `<=` was an unescaped angle bracket one step from a
    400. MUTATION: `parse_mode=ParseMode.MARKDOWN` back on either."""
    ch = _channel()
    ch._load_persona = AsyncMock(return_value=("Apollo_Prime", None))
    update, ctx, msg = _update()
    await ch._handle_help(update, ctx)
    help_text = _only_html_send(msg.reply_text)
    assert help_text.startswith("<b>Apollo_Prime — Quick Reference</b>\n\n<b>Daily commands</b>")
    assert "<code>/why TICKER [YYYY-MM-DD]</code>" in help_text
    assert "EP_TRADING_RULES.md" in help_text and "ATR% &lt;= 15%" in help_text
    assert "<i>Full doc: EP_TRADING_RULES.md</i>" in help_text

    update, ctx, msg = _update()
    await ch._handle_rules(update, ctx)
    rules = _only_html_send(msg.reply_text)
    assert "<b>EP Trading Rules (Qullamaggie v2)</b>" in rules
    assert "Full doc: EP_TRADING_RULES.md" in rules and "ATR% &lt;= 15%" in rules


@pytest.mark.asyncio
async def test_status_goes_out_as_html_with_spend_ids_and_strategy_ids_intact(monkeypatch):
    """/status merged the old /spend summary — its caller and model ids (`ep_grade_judge`,
    `claude-opus-5-5`) are bare underscores in a Markdown body, and the send had NO retry behind
    it. MUTATION: `parse_mode=ParseMode.MARKDOWN` back on the /status reply."""
    import core.router
    import core.spend

    async def _spend():
        return "*API spend*\nep_grade_judge  claude-opus-5-5  $1.23\nmgmt_judge  $0.40"
    monkeypatch.setattr(core.spend, "get_spend_summary", _spend)
    monkeypatch.setattr(core.router, "health_check_all_agents",
                        AsyncMock(return_value={"market_intelligence": (True, "ok")}))
    monkeypatch.setattr(core.router, "get_market_pipeline_status",
                        AsyncMock(return_value={"jobs": {}, "data": {},
                                                "scheduler": {"scheduler_running": True, "next_jobs": []}}))
    ch = _channel()
    ch._check_db = AsyncMock(return_value=(True, ""))
    ch._check_redis = AsyncMock(return_value=(True, ""))
    ch._check_claude = AsyncMock(return_value=(True, ""))
    ch._check_account_mode = AsyncMock(
        return_value=["📄 *PAPER* · routed: `9m_day2`", "  Equity: $5,000.00"])
    update, ctx, msg = _update()
    await ch._handle_status(update, ctx)
    text = _only_html_send(msg.reply_text)
    assert "<b>System Status</b>" in text and "<b>Market Pipeline</b>" in text
    assert "<code>9m_day2</code>" in text
    assert "ep_grade_judge" in text and "claude-opus-5-5" in text and "mgmt_judge" in text
    assert "Market Intelligence Agent — running" in text      # `.title()` of the agent id, unchanged


@pytest.mark.asyncio
async def test_market_slash_results_use_html_and_a_rejection_retries_plain_with_identifiers():
    """`_reply_with_fallback` carries /ep /themes /trades /hud /ideas. MUTATION: the Markdown
    mode back in — or the retry sending `text` (markers showing) instead of `to_plain(html)`."""
    ch = _channel()
    update, _ctx, msg = _update()
    body = "*Theme board*\nai_infra_chips  NVDA_x\n```\nstop_order_id  existing_qty\n```"
    markup = object()
    sent = await ch._reply_with_fallback(update, body, reply_markup=markup)
    assert sent.message_id == 7                                    # /hud pins this
    kw = msg.reply_text.await_args.kwargs
    assert kw["parse_mode"] == ParseMode.HTML and kw["reply_markup"] is markup
    _well_formed(msg.reply_text.await_args.args[0])

    update, _ctx, msg = _update()
    msg.reply_text = AsyncMock(side_effect=[Exception("400"), SimpleNamespace(message_id=9)])
    await ch._reply_with_fallback(update, body)
    retry = msg.reply_text.await_args_list[1]
    assert "parse_mode" not in retry.kwargs
    assert retry.args[0].startswith("Theme board\nai_infra_chips  NVDA_x\n")
    assert "*" not in retry.args[0] and "`" not in retry.args[0] and "stop_order_id  existing_qty" in retry.args[0]


@pytest.mark.asyncio
async def test_a_slash_result_that_fits_as_markdown_but_not_as_html_is_chunked_not_flattened():
    """The size-dependent regression the HTML layer could introduce: the market agent holds a
    body under ~3900 chars AS MARKDOWN, but 190 bold rows are over Telegram's 4096 AS HTML — the
    send would be rejected and retried as unformatted words (bold lost). `_reply_with_fallback`
    now splits after conversion, puts the keyboard on the LAST chunk only and returns the LAST
    Message (/hud pins what it returns). MUTATION: the single un-chunked send back."""
    ch = _channel()
    update, _ctx, msg = _update()
    msg.reply_text = AsyncMock(side_effect=[SimpleNamespace(message_id=i) for i in range(1, 6)])
    body = "\n".join(f"• *T{i:03d}* — chip_{i}" for i in range(190))
    assert len(body) <= 3900 and len(md_to_html(body)) > 4096
    markup = object()
    sent = await ch._reply_with_fallback(update, body, reply_markup=markup)
    calls = msg.reply_text.await_args_list
    assert len(calls) >= 2
    for c in calls:
        assert c.kwargs["parse_mode"] == ParseMode.HTML and len(c.args[0]) <= 4096
        _well_formed(c.args[0])
    assert [c.kwargs["reply_markup"] is markup for c in calls] == [False] * (len(calls) - 1) + [True]
    assert sent.message_id == len(calls)                              # the LAST message comes back
    assert "<b>T189</b> — chip_189" in calls[-1].args[0]              # bold survived to the end


@pytest.mark.asyncio
async def test_replies_convert_first_then_split_so_no_chunk_is_malformed_or_over_the_ceiling():
    """THE #652 LESSON, applied to the channel. The HTML is longer than the Markdown it came from
    (a `*x*` gains 5 chars, `&` gains 4), and a seam inside a fenced block leaves BOTH halves
    malformed. MUTATION: splitting the Markdown at 4000 and converting each half — the first
    chunk crosses 4096 and the fence is cut in two."""
    ch = _channel()
    rows = "\n".join(f"{i:03d}  row_{i}  stop_order_id  <{i}>  a&b" for i in range(260))
    text = "# Heading goes away\n" + "\n".join(f"*line* {i} ep_scan" for i in range(120)) + \
           "\n```\n" + rows + "\n```\n_tail_"
    assert len(text) > 8000
    update, _ctx, msg = _update()
    await ch._reply(update, text)
    sent = [c.args[0] for c in msg.reply_text.await_args_list]
    assert len(sent) >= 3
    for chunk, call in zip(sent, msg.reply_text.await_args_list):
        assert call.kwargs["parse_mode"] == ParseMode.HTML
        assert len(chunk) <= 4096, len(chunk)
        _well_formed(chunk)
    joined = _html_backstop("\n".join(sent))
    assert "Heading goes away" in joined and "# Heading" not in joined          # headings stripped
    for i in (0, 130, 259):
        assert f"row_{i}  stop_order_id  <{i}>  a&b" in joined                   # nothing lost at a seam


@pytest.mark.asyncio
async def test_an_llm_reply_written_in_commonmark_bold_renders_bold_with_no_stray_asterisks():
    """THE ONE PLACE this migration could have made the operator's chat WORSE. The orchestrator's
    own prompt (core/context.py) tells Claude to write "**Action required:** …" — double stars.
    Legacy Markdown reads a `**` pair as two empty entities (clean, unbolded words); the shared
    converter's single-star rule alone printed `*` + bold `*Action required:` + `*`.
    MUTATION: dropping `_BOLD2_RE` from `md_to_html`."""
    ch = _channel()
    update, _ctx, msg = _update()
    await ch._reply(update, "**Action required:** close `ep_scan` for BRK_B. Reply YES to confirm or NO to cancel.")
    assert _only_html_send(msg.reply_text) == (
        "<b>Action required:</b> close <code>ep_scan</code> for BRK_B. Reply YES to confirm or NO to cancel.")


@pytest.mark.asyncio
async def test_a_rejected_reply_chunk_is_retried_as_plain_words():
    ch = _channel()
    update, _ctx, msg = _update()
    msg.reply_text = AsyncMock(side_effect=[Exception("400"), None])
    await ch._reply(update, "The `stuck_fill_watchdog` job hit existing_qty")
    assert msg.reply_text.await_args_list[1].args == ("The stuck_fill_watchdog job hit existing_qty",)


def _drill_wiring(monkeypatch, result: str):
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr(httpx, "AsyncClient", fake_httpx_client(json_body={"result": result}))


@pytest.mark.asyncio
async def test_drill_down_buttons_edit_the_message_in_place_as_html(monkeypatch):
    """eps:/trades: and ideas: buttons. MUTATION: `parse_mode=ParseMode.MARKDOWN` on the
    `edit_message_text` — a theme or skip-reason with a `_` made the edit fail and the operator got
    a second, plain message instead of the board updating in place."""
    _drill_wiring(monkeypatch, "*EPs HIGH*\nBRK_B  rs_rank=91  ep_rt_halt_suspect")
    ch = _channel()
    q, qmsg = _query()
    await ch._handle_drill_down_callback(q, "eps:HIGH:2026-07-15")
    text = _only_html_send(q.edit_message_text)
    assert "<b>EPs HIGH</b>" in text and "BRK_B  rs_rank=91  ep_rt_halt_suspect" in text
    assert q.edit_message_text.await_args.kwargs["reply_markup"] is not None      # ← Summary kept
    qmsg.reply_text.assert_not_awaited()

    q, qmsg = _query()
    await ch._handle_ideas_drill_down(q, "ideas:summary")
    assert "<b>EPs HIGH</b>" in _only_html_send(q.edit_message_text)


@pytest.mark.asyncio
async def test_a_failed_edit_resends_as_html_then_as_plain_words(monkeypatch):
    _drill_wiring(monkeypatch, "*Board*\nai_infra_chips")
    ch = _channel()
    q, qmsg = _query(edit_raises=Exception("message to edit not found"))
    await ch._handle_drill_down_callback(q, "trades:summary")
    assert qmsg.reply_text.await_args.kwargs["parse_mode"] == ParseMode.HTML      # edit failed → new HTML message

    q, qmsg = _query(edit_raises=Exception("gone"))
    qmsg.reply_text = AsyncMock(side_effect=[Exception("400"), None])
    await ch._handle_drill_down_callback(q, "trades:summary")
    assert qmsg.reply_text.await_args_list[1].args == ("Board\nai_infra_chips",)


@pytest.mark.asyncio
async def test_hud_drill_down_sections_are_html_and_split_tag_aware(monkeypatch):
    """The Themes board exceeds 4096 (#473). MUTATION: splitting the Markdown at 4000 and
    converting each piece (the removed `_split_message` order) instead of converting first."""
    big = "*Themes*\n" + "\n".join(f"• *theme_{i}* — ai_infra_{i} & co" for i in range(400))
    _drill_wiring(monkeypatch, big)
    ch = _channel()
    q, qmsg = _query()
    await ch._handle_hud_drill_down(q, "hud:themes")
    calls = qmsg.reply_text.await_args_list
    assert len(calls) >= 2
    for c in calls:
        assert c.kwargs["parse_mode"] == ParseMode.HTML and len(c.args[0]) <= 4096
        _well_formed(c.args[0])
    assert "theme_399" in _html_backstop("\n".join(c.args[0] for c in calls))


@pytest.mark.asyncio
async def test_theme_promote_reply_is_html():
    ch = _channel()
    ch._post_market_task = AsyncMock(return_value="✅ Promoted *Optical_Networking* (cohort_7) & watchers")
    q, qmsg = _query()
    await ch._handle_theme_promote_callback(q, "tpromo:abc123")
    text = _only_html_send(qmsg.reply_text)
    assert "<b>Optical_Networking</b>" in text and "cohort_7" in text and "&amp; watchers" in text


# ── 2. the raw Bot-API senders ───────────────────────────────────────────────────────────────

def _wire(responses):
    from tests.test_telegram_send_fallback import _FakeClient, _Resp
    return _FakeClient([_Resp(s, b) for s, b in responses])


@pytest.mark.asyncio
async def test_job_failure_pages_go_out_as_html_with_identifiers_and_one_backslash(monkeypatch):
    """EVERY scheduled-job-failure page. The error text is `esc()`d inside `<i>…</i>` (built as
    HTML since the #121 review, 2026-10-01 - it no longer takes a Markdown round trip).
    MUTATION: `"parse_mode": "Markdown"` back in `notify_owner`. A second defect fixed with it:
    `md_escape` doubled backslashes, so `C:\\dir` printed two once converted."""
    from core import notifications
    fake = _wire([(200, {"ok": True})])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    await notifications.notify_job_failure(
        "nightly_data_pull",       # not in LOUD_FAILURE_JOBS → silent (#635), asserted below
        'column "stop_order_id" does_not exist at C:\\dir <x> & existing_qty *2*')
    (post,) = fake.posts
    assert post["parse_mode"] == "HTML" and post["disable_notification"] is True
    text = post["text"]
    _well_formed(text)
    assert text.startswith("🚨 <b>Scheduled job failed</b>: <code>nightly_data_pull</code>\n<i>")
    plain = _html_backstop(text)
    for needle in ("stop_order_id", "does_not exist", "existing_qty", "<x> & ", "*2*"):
        assert needle in plain, (needle, plain)
    assert "C:\\dir" in plain and "C:\\\\dir" not in plain          # ONE backslash


async def _one_job_failure_post(monkeypatch, job, error):
    """Run the REAL notify_job_failure -> notify_owner against the fake wire; return the one POST."""
    from core import notifications
    fake = _wire([(200, {"ok": True})])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    await notifications.notify_job_failure(job, error)
    (post,) = fake.posts
    return post


@pytest.mark.asyncio
async def test_a_job_failure_quoting_identifiers_in_backticks_renders_code_not_backslashes(monkeypatch):
    """Review defect 2 (2026-10-01), the EXACT input from the review. The old path backslash-
    escaped the exception text (`rs\\_rank`, ``\\` ``) and `md_to_html` stashes code spans BEFORE it
    honours escapes, so the reader got `\\<code>rs\\_rank\\</code>`. Decision recorded: the fix is
    in `notify_job_failure` (dynamic text must not take a Markdown round trip), NOT in
    `md_to_html`'s ordering - reordering would honour `\\`` and print LITERAL backticks, losing
    the code formatting the exception text was asking for, and would change a converter ~200
    callers share. MUTATION: `error_html(...)` back to a backslash-escaped string through
    `md_to_html` (the pre-fix code) puts backslashes in `text` and fails every assertion here."""
    post = await _one_job_failure_post(
        monkeypatch, "nightly_data_pull",
        "UndefinedColumnError: column `rs_rank` does not exist in `mi_stock_scores`")
    text = post["text"]
    _well_formed(text)
    assert post["parse_mode"] == "HTML"
    assert "\\" not in text                                         # no stray backslashes
    assert "<code>rs_rank</code>" in text and "<code>mi_stock_scores</code>" in text
    assert "column <code>rs_rank</code> does not exist in <code>mi_stock_scores</code>" in text
    # what the reader sees (and what the plain-text retry would send)
    assert "column rs_rank does not exist in mi_stock_scores" in _html_backstop(text)


@pytest.mark.asyncio
async def test_a_job_failure_text_ending_in_a_backslash_keeps_its_italics_closed(monkeypatch):
    """Review defect 4 (2026-10-01): `md_escape` no longer doubled a backslash, so a text ENDING in
    one escaped the closing `_` of the `_…_` wrapper and the reader saw literal underscores
    around the message (`_path C:\\data\\_`). MUTATION: the Markdown wrapper back
    (`f"_{md_escape(flat)}_"` through `md_to_html`) leaves `<i>` absent and literal `_` in the
    plain words."""
    post = await _one_job_failure_post(monkeypatch, "nightly_data_pull", "path C:\\data\\")
    text = post["text"]
    _well_formed(text)
    assert text.endswith("<i>path C:\\data\\</i>")                   # ONE backslash each, italics closed
    assert _html_backstop(text).endswith("\npath C:\\data\\")
    assert "_" not in _html_backstop(text).replace("nightly_data_pull", "")   # no literal underscores


def test_error_html_escapes_free_text_and_only_pairs_backticks():
    from core.notifications import error_html
    assert error_html("a_b *c* <d> & [e]") == "a_b *c* &lt;d&gt; &amp; [e]"
    assert error_html("`x_y` and `z`") == "<code>x_y</code> and <code>z</code>"
    assert error_html("one ` lone backtick") == "one ` lone backtick"      # unpaired stays literal
    assert error_html("`a<b>&c`") == "<code>a&lt;b&gt;&amp;c</code>"      # code content escaped too
    assert error_html("") == ""


@pytest.mark.asyncio
async def test_notify_owner_html_flag_sends_the_text_as_is_and_default_still_converts(monkeypatch):
    """`html=True` = the caller built HTML, so it must NOT be converted a second time (a `<b>`
    would be escaped to `&lt;b&gt;`); the default path still converts legacy Markdown."""
    from core import notifications
    fake = _wire([(200, {"ok": True}), (200, {"ok": True})])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    await notifications.notify_owner("<b>already</b> html_ok", html=True)
    await notifications.notify_owner("*converted* html_ok")
    assert fake.posts[0]["text"] == "<b>already</b> html_ok"
    assert fake.posts[1]["text"] == "<b>converted</b> html_ok"


@pytest.mark.asyncio
async def test_a_rejected_job_failure_page_retries_plain_and_still_buzzes_if_loud(monkeypatch):
    from core import notifications
    fake = _wire([(400, {"description": "can't parse entities"}), (200, {"ok": True})])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    await notifications.notify_job_failure("stop_ack_timeout_watchdog", "existing_qty is 0")
    first, second = fake.posts
    assert first["parse_mode"] == "HTML" and "parse_mode" not in second
    assert second["text"] == "🚨 Scheduled job failed: stop_ack_timeout_watchdog\nexisting_qty is 0"
    assert first["disable_notification"] is False and second["disable_notification"] is False   # #635


@pytest.mark.asyncio
async def test_the_hourly_hud_refresh_edits_as_html_and_never_cuts_inside_a_tag(monkeypatch):
    """The pinned /hud's first send is HTML (`_reply_with_fallback`); its refresh must not flip the
    layer. The 4096 cut is applied AFTER conversion and tag-aware — a cut inside `<b>` would 400
    and `_hud_refresh_job` reads a failed edit as "the message was deleted" and unpins.
    MUTATION: `"parse_mode": "Markdown"` / `text[:4096]` on the converted string."""
    from agents.market_intelligence import briefing
    fake = _wire([(200, {"ok": True}), (200, {"ok": True}), (200, {"ok": True})])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(briefing.httpx, "AsyncClient", fake)

    hud = "*HUD*\nregime_date 2026-09-30 · ep_scan ok · BRK_B +4.1%"
    assert await briefing.edit_telegram_message(42, 7, hud) is True
    p = fake.posts[0]
    assert p["parse_mode"] == "HTML" and p["message_id"] == 7
    _well_formed(p["text"])
    assert p["text"] == "<b>HUD</b>\nregime_date 2026-09-30 · ep_scan ok · BRK_B +4.1%"

    # 4090 chars, then a bold span: as MARKDOWN this is 4101 chars of which the span starts at
    # 4091 — as HTML the 4096th character lands INSIDE the `<b>` tag, so a naive `[:4096]` leaves
    # an unclosed tag (the exact edit Telegram 400s, which _hud_refresh_job reads as "deleted").
    long_hud = "a" * 4090 + " *bold text*"
    assert len(md_to_html(long_hud)) > 4096
    with pytest.raises(AssertionError):
        _well_formed(md_to_html(long_hud)[:4096])                       # the naive cut IS malformed
    assert await briefing.edit_telegram_message(42, 7, long_hud) is True
    cut = fake.posts[1]["text"]
    assert len(cut) <= 4096
    _well_formed(cut)                                                   # no half-open tag

    assert await briefing.edit_telegram_message(42, 7, "plain *words* x_y", parse_mode=None) is True
    assert "parse_mode" not in fake.posts[2] and fake.posts[2]["text"] == "plain *words* x_y"


@pytest.mark.asyncio
async def test_friday_watchlist_digest_with_buttons_converts_once_and_chunks_after_conversion(monkeypatch):
    """It had its own POST: one request, no chunking, a Markdown 400 → plain retry. The digest is
    held under 3900 chars as MARKDOWN (`_TG_SAFE_LIMIT`) but the HTML is longer, so one POST could
    cross 4096. Delegating to the canonical sender gives the keyboard to the LAST chunk only.
    MUTATION: the old raw POST (parse_mode Markdown / one request / keyboard on every request)."""
    from agents.market_intelligence import briefing, friday_watchlist as fw
    fake = _wire([(200, {"ok": True})] * 4)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(briefing.httpx, "AsyncClient", fake)
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())
    keyboard = [[{"text": "📈 BRK_B", "url": "https://www.tradingview.com/chart/?symbol=NYSE:BRK_B"}]]

    body = "🔥 *EP HIGH* (1)\n• *BRK_B* — gap 12% · ep_theme_belonging"
    tv = "📋 *TradingView Import* (copy → Watchlist → Import):\n`NASDAQ:AAPL,NYSE:BRK_B`"
    assert await fw._send_with_keyboard(body + "\n\n" + tv, keyboard) is True
    (post,) = fake.posts
    assert post["parse_mode"] == "HTML"
    _well_formed(post["text"])
    assert "<b>BRK_B</b> — gap 12% · ep_theme_belonging" in post["text"]
    assert "<code>NASDAQ:AAPL,NYSE:BRK_B</code>" in post["text"]
    assert json.loads(post["reply_markup"]) == {"inline_keyboard": keyboard}

    fake.posts.clear()
    body = "\n".join(f"• *T{i:03d}* — chip_{i}" for i in range(190))
    # fits the digest's own guard AS MARKDOWN, but is over Telegram's ceiling AS HTML
    assert len(body) <= fw._TG_SAFE_LIMIT and len(md_to_html(body)) > 4096
    assert await fw._send_with_keyboard(body, keyboard) is True
    assert len(fake.posts) >= 2
    for p in fake.posts:
        assert len(p["text"]) <= 4096
        _well_formed(p["text"])
    assert ["reply_markup" in p for p in fake.posts] == [False] * (len(fake.posts) - 1) + [True]


@pytest.mark.asyncio
async def test_chart_link_fallback_is_an_html_anchor(monkeypatch):
    """The RS-leaders link when the mosaic cannot be built. `[text](url)` Markdown broke on a `)`
    or `_` in the URL; `link()` quotes and escapes the href. MUTATION: Markdown mode back in."""
    from agents.market_intelligence import charts
    fake = _wire([(200, {"ok": True})])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setattr(charts.httpx, "AsyncClient", fake)
    monkeypatch.setattr(charts, "build_chart_mosaic",
                        AsyncMock(return_value=(None, "https://finviz.com/screener.ashx?v=210&t=AAPL,BRK_B")))
    assert await charts.send_chart_mosaic(["AAPL", "BRK_B"]) is True
    (post,) = fake.posts
    assert post["parse_mode"] == "HTML" and post["disable_web_page_preview"] is False
    _well_formed(post["text"])
    assert post["text"] == ('📊 <a href="https://finviz.com/screener.ashx?v=210&amp;t=AAPL,BRK_B">'
                            'RS Leaders Charts</a>')


@pytest.mark.asyncio
async def test_trade_proposal_goes_out_as_html_delivery_only(monkeypatch):
    """The staged-trade FYI. DELIVERY ONLY — the words, numbers and the STAGED-PAPER / mode banner
    are the same strings as before (THE LINE: nothing about sizing, stops or the decision moved).
    A theme name with `_` and `&` is the case Markdown could not carry. MUTATION: `_post("Markdown")`
    back in `send_trade_proposal`."""
    from agents.market_intelligence.broker import telegram_confirm
    import agents.market_intelligence.catalyst_rubric_runtime as crr
    from tests.test_trade_proposal_send_fallback import _ALERT, _SPEC, _Resp

    posted = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            posted.append(json)
            return _Resp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(telegram_confirm.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(crr, "get_theme_membership", AsyncMock(
        return_value={"stage": "Accelerating", "name": "AI Infra_Chips & Memory", "score": 92.0}))
    ok = await telegram_confirm.send_trade_proposal(
        _ALERT, dict(_SPEC, ticker="BRK_B"), trade_id=234, live_real_enabled=False, account_mode="live")
    assert ok is True
    (p,) = posted
    assert p["parse_mode"] == "HTML" and "reply_markup" not in p                 # #364: still FYI-only
    _well_formed(p["text"])
    assert p["text"].startswith("🟡 <b>STAGED-PAPER (not armed — no auto-submit):</b> BRK_B\n")
    plain = _html_backstop(p["text"])
    for line in ("Entry: $295.19 (ORB high)", "Stop: $282.16 (ORB low)", "Risk: $40 (0.8% of account)",
                 "Shares: 3", "Score: 72 | Catalyst grade: game-changing",
                 "Gap: 11.2% | Regime: Choppy", "AI Infra_Chips & Memory"):
        assert line in plain, (line, plain)
    assert "game_changer" not in plain
