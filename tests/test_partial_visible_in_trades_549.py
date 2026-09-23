"""A trade that TOOK PROFIT and then stopped out showed only the stop (operator 2026-08-08).

FIGS, 2026-08-07: the +2R profit trigger fired, banked +$6.90 on 20 shares, and the remaining
41 stopped out for −$13.74. The system did the right thing first — and **both** trade surfaces
hid it:

  `/trades` (closed list)  rendered only `exits[-1]`      → "❌ FIGS -$7 · stop hit"
  `/trades TICKER`         collided both legs on one key  → "→ 13:51 (stop_hit) P&L $-14"

The second was the worse bug: `exits_by_att` was a dict keyed on `attempt`, the partial carries
no `attempt` key so it defaulted to 1, the stop carries an explicit `attempt: 1` — and the stop
silently overwrote the partial. That view also showed **−$14**, the stop leg alone, rather than
the true net of −$6.84.

His words: *"I completely missed this and never saw the telegram, and in /trades it just shows
the total realized loss… at the very least /trades should show the partial profit taken for
closed trades."*

⚠ These tests cover the DISPLAY only. The underlying finding — that the partial sold at market
instead of the 2R target, and that "stop moves to breakeven" never reached the broker — is #548
and is THE LINE.
"""
import importlib.util
import json
import pathlib
import re

# conftest STUBS agents.market_intelligence.backtester.tracker (it drags in heavy deps the suite
# deliberately mocks), so a plain import hands back a MagicMock and every assertion below would
# pass without executing one line of the real formatter — a green test proving nothing, which is
# this week's recurring lesson.
#
# The module also can't be exec'd standalone (its own imports need the package). So compile just
# the function under test, with its two tiny dependencies, into a private namespace. Sourced
# from the real file, so it cannot drift from what ships.
_TRACKER_SRC = pathlib.Path(
    "agents/market_intelligence/backtester/tracker.py").read_text(encoding="utf-8")


def _extract(name: str) -> str:
    i = _TRACKER_SRC.index(f"def {name}(")
    j = _TRACKER_SRC.find("\ndef ", i + 1)
    return _TRACKER_SRC[i:j if j > 0 else len(_TRACKER_SRC)]


from datetime import datetime, timezone  # noqa: E402 — needed by the exec'd source below

from shared.dates import et_hhmm as hhmm_et  # noqa: E402

_ns: dict = {"json": json, "datetime": datetime, "timezone": timezone,
             "et_hhmm": hhmm_et}
exec(_extract("parse_json_list"), _ns)          # noqa: S102 — real source, not a fixture
exec(_extract("format_trade_attempts"), _ns)    # noqa: S102
format_trade_attempts = _ns["format_trade_attempts"]

# FIGS 08-07, verbatim from production.
_FIGS_EXITS = [
    {"pnl": 6.900359999999992, "time": "2026-08-07T13:35:04.544908+00:00", "price": 15.8401,
     "reason": "partial_profit", "shares": 20, "order_id": "676b9bad"},
    {"pnl": -13.738361999999995, "time": "2026-08-07T13:51:02.672791+00:00", "price": 15.16,
     "reason": "stop_hit", "shares": 41.0, "source": "websocket", "attempt": 1},
]
_FIGS_ENTRIES = [{"price": 15.495082, "stop": 15.19, "shares": 61, "attempt": 1,
                  "time": "2026-08-07T13:32:31+00:00"}]


def _figs_lines() -> list[str]:
    return format_trade_attempts(json.dumps(_FIGS_ENTRIES), json.dumps(_FIGS_EXITS))


def test_the_profit_take_is_visible_at_all():
    """The whole point. Before this fix the word never appeared."""
    out = "\n".join(_figs_lines())
    assert "partial_profit" in out, (
        "the profit-take leg is invisible again — the system banked +$6.90 and the operator "
        "would see only the stop-out")


def test_both_legs_render_not_just_the_last():
    out = "\n".join(_figs_lines())
    assert "stop_hit" in out and "partial_profit" in out
    assert "$+7" in out and "$-14" in out


def test_the_legs_do_not_collide_on_the_attempt_key():
    """The actual bug: a dict keyed on `attempt` silently dropped the earlier leg. A partial
    carries no `attempt` (defaults to 1) and the stop carries `attempt: 1`."""
    src = pathlib.Path(
        "agents/market_intelligence/backtester/tracker.py").read_text(encoding="utf-8")
    assert 'exits_by_att = {ex.get("attempt", i + 1): ex for i, ex in enumerate(exits)}' not in src, (
        "exits_by_att is a one-exit-per-attempt dict again — two legs of the same attempt "
        "collide and the profit-take is lost")
    assert "setdefault(ex.get(\"attempt\", i + 1), []).append(ex)" in src


def test_the_NET_is_shown_not_just_the_final_leg():
    """The old view printed −$14 (the stop leg) for a trade that actually netted −$6.84. A
    number that disagrees with /trades' own total is worse than no number."""
    out = "\n".join(_figs_lines())
    assert "net P&L $-7" in out, (
        "the multi-leg view no longer reconciles to the trade's true net — it reports the "
        "final leg as if it were the result")


def test_an_ordinary_single_leg_trade_is_UNCHANGED():
    """A guard that rewrites the common case is a regression, not a fix. One leg = one line,
    no shares/price detail, no net line — exactly as it has read for months."""
    lines = format_trade_attempts(
        json.dumps(_FIGS_ENTRIES),
        json.dumps([{"pnl": -635, "time": "2026-08-07T14:00:00+00:00",
                     "reason": "stop_hit", "attempt": 1}]))
    body = [l for l in lines if "ORB entry" not in l]
    assert len(body) == 1, f"single-leg trade now renders {len(body)} lines: {body}"
    assert "net P&L" not in body[0]
    assert "sh @$" not in body[0]


def test_an_open_trade_still_reads_open():
    lines = format_trade_attempts(json.dumps(_FIGS_ENTRIES), json.dumps([]))
    assert any("(open)" in l for l in lines)


def test_the_closed_list_also_shows_every_leg():
    """`/trades`' closed list rendered `exits[-1]` only. Pinned at source because the handler
    is a 7000-line module and this formatter is a nested closure."""
    src = pathlib.Path(
        "agents/market_intelligence/agent.py").read_text(encoding="utf-8")
    i = src.find("def _fmt_closed_line(")
    assert i > 0, "the closed-trade formatter moved — re-point this test"
    seg = src[i:i + 3000]
    assert "if len(exits) > 1:" in seg, (
        "/trades' closed list is back to rendering only the final exit — a trade that took "
        "profit and was then stopped shows as a plain loss")
    assert re.search(r'legs\.append', seg), "the per-leg breakdown is gone"


# ── the times were UTC (operator 2026-08-08: "we need to fix the timezone") ────────────────

def test_the_timeline_renders_ET_not_UTC():
    """These lines are read by someone reconstructing what happened inside the ORB window, and
    they were FOUR HOURS off. FIGS took profit at 09:35 ET and stopped at 09:51 ET; the view
    said 13:35 and 13:51 because `ts[11:16]` is a raw slice of the stored UTC ISO string.

    This is the UTC-read-as-ET class CLAUDE.md's Time Handling section exists for — the same
    shape as the pytz/LMT bug that shifted the ORB window by 56 minutes (#180/#183)."""
    out = "\n".join(_figs_lines())
    assert "09:35" in out and "09:51" in out, f"times are not ET:\n{out}"
    assert "13:35" not in out and "13:51" not in out, (
        "the trade timeline is rendering UTC again — a market surface four hours off")


def test_it_uses_the_canonical_ET_zone_not_a_second_hand_built_one():
    """CLAUDE.md names ONE canonical ET zone (`shared.dates._ET`). A second construction here
    is how a future timezone audit finds two answers to one question, and pytz is banned
    outright."""
    # THREE surfaces across TWO containers each sliced the ISO string themselves. They all
    # route through the one helper now, which is the whole point of putting it in shared/.
    for f in ("agents/market_intelligence/backtester/tracker.py", "channels/telegram.py"):
        src = pathlib.Path(f).read_text(encoding="utf-8")
        assert "from shared.dates import et_hhmm" in src, (
            f"{f} no longer uses the canonical ET formatter")
        # Check USAGE, not the substring: "pytz" legitimately appears in comments explaining
        # why it is banned, and a check that fails on its own documentation is a broken check.
        code = "\n".join(l.split("#", 1)[0] for l in src.split("\n"))
        assert "import pytz" not in code, f"{f} reintroduced pytz"
        # Deliberately NOT asserting the whole file never constructs a ZoneInfo: telegram.py is
        # ~1500 lines with unrelated, legitimate timezone code, and a first draft of this test
        # failed on it. A guard that fires on code it was never about is worse than no guard —
        # the repo-wide ban is the deploy gate's job (preflight_datetime_hygiene), not this
        # test's. Scope here is the RENDERER, pinned by the et_hhmm assertion above.


def test_naive_timestamps_are_treated_as_UTC():
    """The container writes naive timestamps. Treating one as already-local would put a
    09:35 ET fill at 13:35 ET — wrong in the other direction and much harder to notice."""
    assert hhmm_et("2026-08-07T13:35:04") == "09:35"
    assert hhmm_et("2026-08-07T13:35:04Z") == "09:35"
    assert hhmm_et(datetime(2026, 8, 7, 13, 35, 4, tzinfo=timezone.utc)) == "09:35"


def test_DST_is_handled_on_BOTH_sides():
    """A hardcoded -4 offset is right in August and wrong in January. ET is EDT (-4) in
    summer and EST (-5) in winter; both must land on 09:35."""
    assert hhmm_et("2026-08-07T13:35:00+00:00") == "09:35"   # EDT
    assert hhmm_et("2026-01-15T14:35:00+00:00") == "09:35"   # EST


def test_an_unparseable_timestamp_degrades_instead_of_crashing():
    """This is a display path on a Telegram digest — a bad row must not take the message down."""
    assert hhmm_et("not-a-time") is None
    assert hhmm_et(None) is None
    assert hhmm_et("") is None
    lines = format_trade_attempts(
        json.dumps(_FIGS_ENTRIES),
        json.dumps([{"pnl": -1, "time": "garbage", "reason": "stop_hit", "attempt": 1}]))
    assert any("stop_hit" in l for l in lines)


def test_slash_trades_TICKER_reaches_the_per_ticker_view():
    """`/trades FIGS` answered "Unknown view: figs" — the second argument was parsed as a VIEW
    name. The only route to the per-ticker timeline was the phrase "FIGS trade", which for the
    operator routed to fundamentals instead. His ruling: *"this should belong to /trades FIGS"*."""
    src = pathlib.Path("agents/market_intelligence/agent.py").read_text(encoding="utf-8")
    i = src.find('return self._ok(request, result=f"Unknown view: {view}")')
    assert i > 0
    seg = src[max(0, i - 900):i]
    assert "_handle_trades_query(request, ticker=view.upper())" in seg, (
        "/trades TICKER no longer reaches the per-ticker view")
    # It must be the LAST branch, so a real view name can never be swallowed as a ticker.
    for v in ("summary", "live", "paper", "skipped", "closed"):
        assert src.find(f'if view == "{v}":') < i, f"the ticker fallback now shadows /trades {v}"


def test_the_orchestrator_copy_shows_every_leg_too():
    """channels/telegram.py carried its own duplicate of this renderer with BOTH bugs — the UTC
    slice and the attempt-key collision that hid the profit-take. One container being right is
    not the same as the operator seeing the truth."""
    src = pathlib.Path("channels/telegram.py").read_text(encoding="utf-8")
    assert 'exits_by_att = {ex.get("attempt", i+1): ex for i, ex in enumerate(exits)}' not in src
    assert 'setdefault(ex.get("attempt", i + 1), []).append(ex)' in src


# ── the Telegram layer dropped the ticker before the agent ever saw it ─────────────────────

def test_the_telegram_trades_command_forwards_a_TICKER_argument():
    """`/trades FIGS` returned the plain summary (operator, 2026-08-08: *"the /trades FIGS
    command just return /trades"*).

    The agent-side routing for `/trades TICKER` was added and verified the same day by calling
    `execute_task("/trades FIGS")` directly — which passes the string straight through, so it
    could not possibly catch this. `_handle_trades_command` HARDCODED
    `f"/trades_detail summary {today_str}"` and never read `context.args`; the ticker was
    discarded in the Telegram layer, one level above everything that was tested.

    ⚠ The rule this pins: the only proof a COMMAND works is the command, not the function
    behind it. A green agent-level test on a broken command is worse than no test."""
    src = pathlib.Path("channels/telegram.py").read_text(encoding="utf-8")
    i = src.find("async def _handle_trades_command")
    assert i > 0, "the /trades handler moved — re-point this test"
    body = src[i:i + 3000]
    # CODE ONLY. My first version of this check matched the phrase inside the very comment
    # explaining the bug, so a mutation that deleted the actual line still passed — the same
    # self-satisfying-guard mistake I had just flagged in someone else's test. Caught by
    # mutation-checking, which is the only reason a guard is worth anything.
    code = "\n".join(l.split("#", 1)[0] for l in body.split("\n"))
    assert "context, \"args\"" in code or "context.args" in code, (
        "/trades no longer reads its argument — `/trades FIGS` silently returns the summary "
        "again, discarding the ticker before the agent can route it")
    assert "/trades_detail {_tk}" in code, (
        "the ticker is read but not forwarded to the per-ticker view")
    # the plain `/trades` path must be untouched
    assert "/trades_detail summary {today_str}" in code, (
        "the no-argument summary path is gone — /trades itself is broken")


def test_a_non_ticker_argument_still_gets_the_summary():
    """`/trades` with junk, or a date, must not fall into the ticker branch and lose the
    board. Only a plain 2-5 letter token is treated as a ticker."""
    src = pathlib.Path("channels/telegram.py").read_text(encoding="utf-8")
    i = src.find("async def _handle_trades_command")
    body = src[i:i + 3000]
    code = "\n".join(l.split("#", 1)[0] for l in body.split("\n"))
    assert "_tk.isalpha() and 2 <= len(_tk) <= 5" in code, (
        "the ticker guard is gone or widened — a date or a view name could now be swallowed "
        "as a ticker")
