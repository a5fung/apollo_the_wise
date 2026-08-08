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


_ns: dict = {"json": json}
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
