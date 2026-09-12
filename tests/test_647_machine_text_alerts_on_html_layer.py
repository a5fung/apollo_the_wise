"""#647 — alerts that carry machine text go out on the HTML layer, first send, no retry.

WHAT WAS WRONG (2026-09-12, measured in prod, `telegram_markdown_fallback` rows over 14 days):
28 alerts failed their legacy-Markdown send with a Telegram 400 and reached the operator only
because `send_telegram_message` re-sent them plain. Every body carried machine text — a
snake_case identifier (`ep_delayed_residual_scan`, `regime_date`, `TRAIL_TIGHTEN`, `trade_id`),
Alpaca's JSON (`existing_qty`), or SQL — and Telegram's v1 parser reads every bare `_` as an
italic delimiter. The senders, traced from the row's own `chunk=`:

    11× Delayed-feed residual      ep_delayed_residual.run_delayed_residual_scan
     4× Catalyst-lattice revert    health_checks.run_catalyst_lattice_monitor   (SQL)
     4× Mgmt-judge digest          mgmt_judge.run_position_mgmt_judge
     2× THE EP ALERT               briefing.send_ep_alert                      (judge prose)
     2× JOB PRODUCED NOTHING       health_checks.run_job_liveness_sweep
     2× Regime sizing FALLBACK     order_manager._alert_regime_sizing_fallback_once
     1× Full exit FAILED (OKTA)    order_manager.execute_full_exit             (JSON)
     1× ORB auto-enter failed      entry_pipeline.submit_trade_entry
     1× L2 anomaly                 system_audit._emit_l2                       (SQL)
     1× Monthly sweep digest       quarterly_review.quarterly_backward_check_sweep_job
     1× LLM TRUNCATED              cost_board.run_truncation_check
     (+ system_audit._emit_l1 and order_ingest._emit: same class, not yet seen in prod)

AND THE BACKSTOP CORRUPTED THE PAYLOAD: `_strip_markdown_markers` dropped the ``` fences first
and then stripped paired `_` across the whole message, so the plain retry delivered the
safeguard-revert SQL as `INSERT INTO misafeguardstate (... accountmode ...)` — unrunnable.

THE FIX (delivery only — no alert says anything different):
  1. each sender converts ONCE at the send boundary: `send_telegram_message(md_to_html(text),
     parse_mode="HTML")` — the migration path `shared/telegram_format.py` documents and
     `system_review.py` already uses (#121 continues it surface by surface);
  2. `md_to_html` consumes the v1 backslash escapes `_md_escape` emits, so the EP alert's ⚖️
     Acted block no longer arrives as `game\\_changer`;
  3. `_strip_markdown_markers` stashes code/fence bodies verbatim and only strips WORD-BOUNDED
     emphasis pairs, so even the Markdown backstop can no longer eat an identifier.

Every test names the mutation that reddens it. All were run RED against that mutation before
the fix was restored (see the commit).
"""
from __future__ import annotations

import html as _html
import inspect
import json
import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import briefing, health_checks as hc, system_audit
from agents.market_intelligence.briefing import _strip_markdown_markers
from shared.telegram_format import md_to_html

# ── helpers ───────────────────────────────────────────────────────────────────────────────

_ALLOWED_TAGS = {"b", "i", "code", "pre", "a", "u", "s"}
_TAG_RE = re.compile(r"<(/?)([a-z]+)(?:\s[^<>]*)?>")


def _assert_well_formed_telegram_html(s: str) -> None:
    """The property Telegram's HTML parser needs: every `<` opens a known tag, tags nest,
    every `&` is an entity. A body that passes cannot 400 for markup reasons."""
    stack: list[str] = []
    pos = 0
    for m in _TAG_RE.finditer(s):
        between = s[pos:m.start()]
        assert "<" not in between and ">" not in between, f"raw angle bracket in text: {between!r}"
        closing, name = m.group(1) == "/", m.group(2)
        assert name in _ALLOWED_TAGS, f"unsupported tag <{name}>"
        if closing:
            assert stack and stack[-1] == name, f"</{name}> closes <{stack[-1] if stack else None}>"
            stack.pop()
        else:
            stack.append(name)
        pos = m.end()
    tail = s[pos:]
    assert "<" not in tail and ">" not in tail, f"raw angle bracket in tail: {tail!r}"
    assert not stack, f"unclosed tags: {stack}"
    assert not re.search(r"&(?!(amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)", s), "a bare & survived"


def _html_backstop(s: str) -> str:
    """What `send_telegram_message._to_plain` does on the HTML path (strip tags, unescape)."""
    return _html.unescape(re.sub(r"<[^>]+>", "", s))


_OKTA_JSON = ('{"available":"0","code":40310000,"existing_qty":"2","held_for_orders":"2",'
              '"message":"insufficient qty available for order (requested: 2, available: 0)"}')


# ── 1. the backstop must not corrupt the payload ──────────────────────────────────────────

def test_fallback_stripper_keeps_fenced_sql_verbatim():
    """MUTATION TARGET: the pre-#647 `_strip_markdown_markers` body — fences dropped first,
    then `_(?=\\S)([^_\\n]*?)(?<=\\S)_` across the whole message. That delivered
    `mi_safeguard_state` as `misafeguardstate`: the revert command the operator was sent on
    09-02/09-10/09-11 was unrunnable."""
    body = ("Revert the flip (ONE flag):\n```\n" + hc._LATTICE_REVERT_SQL + "\n```\n"
            "_Permanent form: set `CATALYST_TIER_LATTICE_ENABLED=false` in prod .env._")
    out = _strip_markdown_markers(body)
    assert hc._LATTICE_REVERT_SQL in out, out
    assert "```" not in out and "CATALYST_TIER_LATTICE_ENABLED=false" in out


def test_fallback_stripper_keeps_inline_code_verbatim():
    """MUTATION TARGET: dropping the inline-code stash (back to `re.sub(r"`([^`]+)`", r"\\1")`
    before the emphasis strip). `mi_ep_alerts` then loses its underscores to the italic pass."""
    out = _strip_markdown_markers("• `EP detector alerts` (ep_scan) ran but `mi_ep_alerts` got < 1 rows")
    assert "mi_ep_alerts" in out and "(ep_scan)" in out and "`" not in out


def test_fallback_stripper_leaves_snake_case_outside_any_span_alone():
    """MUTATION TARGET: removing the `(?<!\\w)` / `(?!\\w)` guards on the `_` pair strip.
    The OKTA exit-failure JSON has no code span at all; the old pass turned
    `"existing_qty":"2","held_for_orders"` into `"existingqty":"2","heldfor_orders"`."""
    out = _strip_markdown_markers("💰 LIVE-$ ⚠️ Full exit FAILED for OKTA: " + _OKTA_JSON)
    assert _OKTA_JSON in out, out
    # …while real emphasis is still stripped (the reason the stripper exists).
    assert _strip_markdown_markers("*Stopped out:* OKTA _see above_") == "Stopped out: OKTA see above"


# ── 2. md_to_html carries machine text and the legacy escapes ─────────────────────────────

def test_md_to_html_consumes_the_v1_backslash_escapes_md_escape_emits():
    """MUTATION TARGET: removing step 1b (`_ESCAPED_RE`) from `md_to_html`. The EP alert's
    ⚖️ Acted block runs its fields through `_md_escape`, so without this the operator's
    most-read alert would print `game\\_changer` with the backslashes."""
    src = briefing._md_escape("the earnings carve-out kept game_changer via earnings_revenue_weak_downgrade")
    assert "\\_" in src                                   # the escaper really emits backslashes
    out = md_to_html(f"⚖️ Acted: {src} *kept*")
    assert "\\" not in out
    assert "game_changer" in out and "earnings_revenue_weak_downgrade" in out and "<b>kept</b>" in out
    # v1 treats a backslash inside a code span as literal — so do we.
    assert md_to_html("`a\\_b`") == "<code>a\\_b</code>"
    _assert_well_formed_telegram_html(out)


def test_md_to_html_keeps_the_revert_sql_byte_for_byte_inside_pre():
    """MUTATION TARGET: escaping the whole text BEFORE stashing the fence, or running the
    italic regex over the fence body — either way `catalyst_tier_lattice` stops being the
    literal the operator has to paste."""
    body = "```\n" + hc._LATTICE_REVERT_SQL + "\n```"
    out = md_to_html(body)
    assert out == f"<pre>\n{hc._LATTICE_REVERT_SQL}\n</pre>"
    assert _html_backstop(out).strip() == hc._LATTICE_REVERT_SQL


def _prod_bodies() -> list[tuple[str, str, str]]:
    """(label, legacy-Markdown body as the builder emits it, the machine text it must carry)
    — the real prod failures of 2026-08-31..09-11, rebuilt from the real builders where they
    are pure and from the real templates otherwise."""
    from agents.market_intelligence.mgmt_judge import format_mgmt_line
    from agents.market_intelligence.quarterly_review import _render_digest
    l2 = system_audit._format_l2_alert(
        system_audit.MetricSpec(name="9m_alerts_per_day", fetch_today=None,
                                drill_sql="SELECT * FROM mi_9m_ep_alerts WHERE alert_date = CURRENT_DATE",
                                code_pointers=["agents/market_intelligence/system_audit.py"]),
        17.0, {"p50": 10.0, "mad": 2.0}, [], {"z_score": 3.5, "ratio": 1.7})
    judge = format_mgmt_line(
        {"ticker": "OKTA", "pct_from_entry": -0.004, "r_multiple": -0.1, "hold_days": 14},
        {"verdict": "TRAIL_TIGHTEN", "rationale": "Two weeks of zero progress on a game_changer catalyst."})
    digest = _render_digest([{"exit_code": 0, "label": "M&A filter accuracy review (#284/#285)",
                              "module": "scripts.audits.ma_filter_accuracy",
                              "stdout_summary": "some table nobody taught me to read"}],
                            date(2026, 9, 1), 25.0)
    return [
        ("residual", "🔴 Delayed-feed residual 2026-09-11: 3 delay-missed EP crosser(s) today, 1 BEYOND "
                     "the 5% hybrid (the class the fix can't catch). Outcomes settle ~5d. "
                     "(/audit ep_delayed_residual_scan)", "ep_delayed_residual_scan"),
        ("regime", "📄 PAPER 🚨 Regime sizing FALLBACK (missing_or_stale): last regime_date seen "
                   "2026-09-04, label=Choppy — sizing floored to 25%.", "missing_or_stale"),
        ("full-exit", "💰 LIVE-$ ⚠️ Full exit FAILED for OKTA: " + _OKTA_JSON +
                      "\nStop RESTORED at $165.57 — position is protected.", _OKTA_JSON),
        ("lattice", "🔴 *CATALYST TIER MONITOR — revert trigger hit* (#533 flip, 2026-08-22)\n"
                    "• ZERO-ALERT DAYS: no EP alerts at all on 2026-09-11 and 2026-09-10\n\n"
                    "Revert the flip (ONE flag):\n```\n" + hc._LATTICE_REVERT_SQL + "\n```\n"
                    "_Permanent form: set `CATALYST_TIER_LATTICE_ENABLED=false` in prod .env and "
                    "redeploy market-agent. Evidence: docs/setups/magna53_ep.md 2026-08-22._",
         hc._LATTICE_REVERT_SQL),
        ("job-liveness", "🩺 JOB PRODUCED NOTHING (2)\n\n" + hc._format_job_flag(
            {"ep_scan": "EP detector alerts"},
            {"job_id": "ep_scan", "table": "mi_ep_alerts", "min_expected_rows": 1, "empty_runs": 3}),
         "mi_ep_alerts"),
        ("mgmt-judge", "🧭 Mgmt-judge — SHADOW, zero authority · 1 open\n\n" + judge, "TRAIL_TIGHTEN"),
        ("auto-enter", "💰 LIVE-$ ⚠️ *IONQ* ORB auto-enter failed — check logs (trade_id=397)", "trade_id=397"),
        ("l2", l2, "SELECT * FROM mi_9m_ep_alerts WHERE alert_date = CURRENT_DATE"),
        ("digest", digest, "M&A filter accuracy review"),
        ("truncated", "🔴 *TRUNCATED* — responses cut off by max_tokens (silent corruption):\n```\n"
                      "theme_discovery              2/17 calls (11.8%) at 8000 tokens\n```", "max_tokens"),
        ("ingest", "📄 PAPER ⚠️ *Ingest R1 rejected* — AAPL: mode_mismatch coid=apollo_live_magna53_AAPL_1715450123456 cycle=paper",
         "coid=apollo_live_magna53_AAPL_1715450123456"),
    ]


@pytest.mark.parametrize("label,body,machine_text", _prod_bodies(), ids=lambda v: v if isinstance(v, str) and len(v) < 16 else "")
def test_each_prod_failure_body_converts_to_well_formed_html_that_still_carries_its_payload(label, body, machine_text):
    """MUTATION TARGET: any change to `md_to_html`'s stash/escape order — e.g. `esc()` before
    the pre/code stash (the SQL's `<` would double-escape and the tags would be text), or
    dropping `esc()` (the digest's `M&A` becomes a bare `&`, the JSON's quotes survive but a
    `<` in an Alpaca message would open a tag). Well-formed HTML is the property that cannot
    400; the payload surviving the HTML backstop is the property the plain retry lacked."""
    out = md_to_html(body)
    _assert_well_formed_telegram_html(out)
    assert machine_text in _html_backstop(out), (label, out)


@pytest.mark.asyncio
async def test_even_the_html_backstop_delivers_the_sql_intact(monkeypatch):
    """END TO END through the real `send_telegram_message`: Telegram rejects the HTML send (a
    forced 400), the plain retry fires — and the retry text still carries the revert SQL
    byte-for-byte, `<` included. MUTATION TARGET: routing the HTML branch of `_to_plain`
    through `_strip_markdown_markers`, or dropping `html.unescape` from it (`&lt;` leaks)."""
    from tests.test_telegram_send_fallback import _FakeClient, _Resp, _entity_error_body
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    sql = "UPDATE mi_safeguard_state SET state = 'off' WHERE updated_at < NOW() AND safeguard = 'x_y';"
    body = md_to_html("*Revert:*\n```\n" + sql + "\n```")
    fake = _FakeClient([_Resp(400, _entity_error_body(3)), _Resp(200, {"ok": True})])
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", AsyncMock()):
        ok = await briefing.send_telegram_message(body, parse_mode="HTML")
    assert ok is True and len(fake.posts) == 2
    assert fake.posts[0]["parse_mode"] == "HTML"
    assert "parse_mode" not in fake.posts[1]
    assert sql in fake.posts[1]["text"], fake.posts[1]["text"]


# ── 3. the senders — behavioural where a harness is cheap ─────────────────────────────────

def _sent_html(mock: AsyncMock) -> str:
    """The text of the ONE send, asserting it went out on the HTML layer."""
    mock.assert_awaited_once()
    assert mock.await_args.kwargs.get("parse_mode") == "HTML", mock.await_args
    text = mock.await_args.args[0]
    _assert_well_formed_telegram_html(text)
    return text


@pytest.mark.asyncio
async def test_full_exit_failed_page_goes_out_as_html_with_alpacas_json_intact(monkeypatch):
    """THE OKTA PAGE (2026-09-11, live money). MUTATION TARGET: `send_telegram_message(f"…{e}…")`
    without `md_to_html(...)` / `parse_mode="HTML"` in `execute_full_exit` — the JSON's
    `existing_qty` is one bare `_` and the first send 400s again."""
    from agents.market_intelligence.broker import order_manager as om
    from tests.test_646_full_exit_never_returns_naked import _wire
    h = _wire(monkeypatch, close_raises=True)
    h["close"].side_effect = Exception(_OKTA_JSON)
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "send_telegram_message", tg)
    ok = await om.execute_full_exit(382, "sma_trail_stop")
    assert ok is False
    text = _sent_html(tg)
    assert _OKTA_JSON in _html_backstop(text) and "Stop RESTORED" in text


@pytest.mark.asyncio
async def test_regime_sizing_fallback_page_goes_out_as_html(monkeypatch):
    """Fired twice on 2026-09-08 (paper + live) and 400'd both times — `regime_date` and
    `missing_or_stale` are three bare `_` in the TEMPLATE, so every firing failed. MUTATION
    TARGET: dropping `md_to_html(...)` / `parse_mode="HTML"` from
    `_alert_regime_sizing_fallback_once`'s send."""
    from agents.market_intelligence.broker import order_manager as om

    class _Conn:
        async def fetch(self, *a, **k):
            return []                      # not yet alerted today → the page fires

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self, *a, **k): return _Acq()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "send_telegram_message", tg)
    await om._alert_regime_sizing_fallback_once(
        account_mode="live", regime_date=date(2026, 9, 4), label="Choppy",
        today=date(2026, 9, 8), reason="missing_or_stale")
    text = _sent_html(tg)
    assert "missing_or_stale" in text and "regime_date" in text and "FALLBACK" in text


@pytest.mark.asyncio
async def test_the_ep_alert_goes_out_as_html_with_judge_prose_and_the_acted_block_readable(monkeypatch):
    """The alert that drives entries (IONQ 09-08, HOOD 09-03 fell back). The judge's prose
    carries `game_changer` (an odd `_` count 400s v1; an even count toggles italics mid-word)
    and the ⚖️ Acted block is `_md_escape`d. MUTATION TARGET: `send_telegram_message(text,
    chat_id)` in `send_ep_alert` — or `md_to_html` without its backslash step, which lands
    the page but prints `game\\_changer`."""
    from tests.test_ep_alert_two_axes import OKTA
    ep = dict(OKTA, gap_pct=8.0, rel_volume=2.0,
              judge_rationale="Demoted from game_changer: the earnings_revenue_weak_downgrade held.",
              # the Acted block's `why` goes through _md_escape — give it an identifier so the
              # backslash really is emitted (OKTA's own fields carry none) and must be consumed
              floor_grade_kept=dict(OKTA["floor_grade_kept"],
                                    why="beat by 1.2%; gate earnings_revenue_weak_downgrade did not apply"))
    assert "\\_" in briefing._md_escape(ep["floor_grade_kept"]["why"])
    tg = AsyncMock(return_value=True)
    with patch.object(briefing, "send_telegram_message", tg):
        await briefing.send_ep_alert(ep)
    text = _sent_html(tg)
    assert "\\_" not in text and "\\*" not in text
    assert "<b>EP ALERT" in text and "<b>OKTA</b>" in text
    assert "<i>Judge's reasoning: Demoted from game_changer: the earnings_revenue_weak_downgrade held.</i>" in text
    assert "gate earnings_revenue_weak_downgrade did not apply" in text   # the Acted block, backslashes consumed


@pytest.mark.asyncio
async def test_lattice_revert_page_goes_out_as_html_with_the_sql_in_pre(monkeypatch):
    """4 of the last 14 days. MUTATION TARGET: `send_telegram_message("\\n".join(lines))` bare
    in `run_catalyst_lattice_monitor`'s announce — the `magna53_ep.md` underscore in the
    italic line 400s v1 and the plain retry strips the SQL's `_`."""
    from tests.test_catalyst_lattice_monitor import _patch_common, _FakeConn, _alert_rows, _FRI
    _audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=1, prior_high=4),
                     flip_date=date(2026, 1, 1))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["spoke"] is True
    text = _sent_html(tg)
    assert f"<pre>\n{hc._LATTICE_REVERT_SQL}\n</pre>" in text


@pytest.mark.asyncio
async def test_l1_and_l2_pages_go_out_as_html_with_the_drill_sql_in_pre(monkeypatch):
    """MUTATION TARGET: the bare `send_telegram_message(text)` in `_emit_l1` or `_emit_l2`.
    Both fence the drill SQL, which is the one thing the plain retry used to mangle."""
    from tests.test_l1_alert_underscore_escaping import _BODY
    monkeypatch.setattr(system_audit, "count_today_anomalies", AsyncMock(return_value=0))
    monkeypatch.setattr(system_audit, "log_audit_event", AsyncMock())
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(briefing, "send_telegram_message", tg)

    await system_audit._emit_l1("silent_audit_error_window", _BODY)
    l1 = _sent_html(tg)
    assert "<code>silent_audit_error_window</code>" in l1
    assert _BODY["drill_sql"] in _html_backstop(l1)

    tg.reset_mock()
    spec = system_audit.MetricSpec(
        name="9m_alerts_per_day", fetch_today=None,
        drill_sql="SELECT * FROM mi_9m_ep_alerts WHERE alert_date = CURRENT_DATE")
    body = {"current": 17.0, "baseline_p50": 10.0, "mad": 2.0, "z_score": 3.5, "ratio": 1.7, "to_band": 3}
    await system_audit._emit_l2(spec, system_audit.Anomaly(2, spec.name, body), event_deltas=[])
    l2 = _sent_html(tg)
    assert "<code>9m_alerts_per_day</code>" in l2 and spec.drill_sql in _html_backstop(l2)


@pytest.mark.asyncio
async def test_job_produced_nothing_page_goes_out_as_html(monkeypatch):
    """2 of the last 14 days. MUTATION TARGET: the bare `send_telegram_message(body)` in
    `run_job_liveness_sweep` — the bare `(ep_scan)` job id between two code spans 400s v1."""
    from tests.test_health_checks_job_liveness import _FakeConn
    monkeypatch.setattr(hc, "_JOB_OUTPUT_CHECKS",
                        [("ep_scan", "EP detector alerts", "mi_ep_alerts", "alert_date", 1, 1)])
    monkeypatch.setattr(hc, "log_audit_event", AsyncMock())
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(briefing, "send_telegram_message", tg)
    conn = _FakeConn(jobs={"ep_scan": (["2026-09-11", "2026-09-10", "2026-09-09"],
                                       {"2026-09-11": 0, "2026-09-10": 4, "2026-09-09": 3})},
                     table_for_job={"ep_scan": "mi_ep_alerts"})
    summary = await hc.run_job_liveness_sweep(conn)
    assert [f["job_id"] for f in summary["flags"]] == ["ep_scan"]
    text = _sent_html(tg)
    assert "JOB PRODUCED NOTHING" in text and "<code>mi_ep_alerts</code>" in text and "(ep_scan)" in text


@pytest.mark.asyncio
async def test_order_ingest_findings_go_out_as_html(monkeypatch):
    """Not yet seen in prod, provably the same class: a rejection reason reads
    `mode_mismatch coid=apollo_live_magna53_…`. MUTATION TARGET: the bare
    `send_telegram_message(telegram)` in `order_ingest._emit`."""
    from agents.market_intelligence.broker import order_ingest as oi
    monkeypatch.setattr(oi, "log_audit_event", AsyncMock())
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(oi, "send_telegram_message", tg)
    await oi._emit(oi.INGEST_REJECTED, "sig", {"class": "r1"},
                   "📄 PAPER ⚠️ *Ingest R1 rejected* — AAPL: mode_mismatch coid=apollo_live_magna53_AAPL_1 cycle=paper")
    text = _sent_html(tg)
    assert "<b>Ingest R1 rejected</b>" in text and "coid=apollo_live_magna53_AAPL_1" in text


# ── 4. the DB-bound senders — pinned at the source, the weekly-review precedent ───────────

def _src(obj) -> str:
    return inspect.getsource(obj)


@pytest.mark.parametrize("target,required", [
    ("ep_delayed_residual.run_delayed_residual_scan",
     ['f"(/audit ep_delayed_residual_scan)"), parse_mode="HTML")']),
    ("mgmt_judge.run_position_mgmt_judge",
     ['send_telegram_message(md_to_html(text), parse_mode="HTML")']),
    ("quarterly_review.quarterly_backward_check_sweep_job",
     ['send_telegram_message(md_to_html(result["digest_message"]), parse_mode="HTML")']),
    ("cost_board.run_truncation_check",
     ['send_telegram_message(md_to_html("\\n".join(lines)), parse_mode="HTML")']),
    ("broker.entry_pipeline.submit_trade_entry",
     ['auto-enter failed — "\n                f"check logs (trade_id={trade_id})"\n            ), parse_mode="HTML")',
      'proposal send failed — "\n        f"check logs (trade_id={trade_id})"\n    ), parse_mode="HTML")']),
])
def test_db_bound_senders_convert_at_the_send_boundary(target, required):
    """MUTATION TARGET: reverting that sender's send to the bare legacy-Markdown call. These
    functions are DB-bound end to end, so the wiring is pinned at the source — the same
    shape `tests/test_weekly_review_html_send.py` uses for the 08-30 digest fix. Each
    required substring is the exact converted call, so a half-revert (md_to_html kept,
    parse_mode dropped, or the reverse) fails too."""
    import importlib
    mod_name, fn_name = target.rsplit(".", 1)
    fn = getattr(importlib.import_module(f"agents.market_intelligence.{mod_name}"), fn_name)
    src = _src(fn)
    for needle in required:
        assert needle in src, f"{target}: missing {needle!r}"


def test_the_single_send_senders_have_no_bare_legacy_send_left():
    """MUTATION TARGET: adding a second, bare `send_telegram_message(` to any of these — the
    class this task closes must not be re-opened by a sibling send in the same function.
    (`run_catalyst_lattice_monitor` is not listed: its fixture-dark warning is a second,
    legitimately legacy send whose only identifier sits inside a code span.)"""
    from agents.market_intelligence import ep_delayed_residual, mgmt_judge, quarterly_review
    from agents.market_intelligence.broker import order_ingest
    for fn in (ep_delayed_residual.run_delayed_residual_scan, mgmt_judge.run_position_mgmt_judge,
               quarterly_review.quarterly_backward_check_sweep_job, order_ingest._emit,
               system_audit._emit_l1, system_audit._emit_l2, hc.run_job_liveness_sweep):
        src = _src(fn)
        n_send = src.count("send_telegram_message(")
        n_html = src.count('parse_mode="HTML"')
        # the lazy `from … import send_telegram_message` lines are not calls
        assert n_send >= 1 and n_send == n_html, (fn.__qualname__, n_send, n_html)
