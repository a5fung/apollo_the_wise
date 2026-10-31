"""#716 (2026-10-31, operator ask 2026-10-30 on /why REGN: "Can we make it more readable, now
it's a wall of text") — `/why TICKER` is SHORT by default; `/why TICKER full` keeps every line.

The short layout: a one-line verdict header (tier, score, bought / not bought and why); WHY (the
catalyst in one line + source, the score as parts OUT OF their maximum, what could still add);
GRADE NOTE; ENTRY (plan, and what happened — an outcome with no order says no order was placed);
KEY TIMES (the 3-5 decisive events). DISPLAY ONLY: no score, bar, weight or rule moves.

The "full" tests are golden-file tests: `tests/fixtures/why_716_*_full_before.txt` were captured
from the UNMODIFIED handler (origin/main bf589821) on the same fixtures, so "full equals today's
output" is a measured equality, not an assertion that restates the new code.

One DELIBERATE difference: for a trade with no order (REGN 2026-10-30, chase cap), the Fill
diagnosis section used to describe a resting order that never existed and told a false "price
moved past limit too fast" story. It now says no order was placed. Nothing else in full moves.
"""
import copy
import pathlib
from types import SimpleNamespace

import pytest

from agents.market_intelligence import ep_score_math
from agents.market_intelligence.agent import (
    _chase_cap_plain, _why_key_times, _why_verdict_line, build_why_short_lines,
)
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY
from agents.market_intelligence.ep_score_math import part_maxima, score_short_lines
from tests import why716_fixtures as fx
from tests.test_713_why_score_math import _scored_row

_FIX = pathlib.Path(__file__).parent / "fixtures"
_REGN_SHORT_TASK = "/why REGN 2026-10-30"


def _short(monkeypatch, world=None, task=_REGN_SHORT_TASK):
    fx.wire(monkeypatch, world or fx.regn_world())
    return fx.render(task)


# ── the short layout on a fixture shaped like REGN 2026-10-30 ────────────────────────────────


def test_short_layout_sections_and_their_order(monkeypatch):
    body = _short(monkeypatch)
    lines = body.split("\n")
    assert lines[0] == "📋 REGN 2026-10-30 — HIGH 65 · NOT BOUGHT — ran too far past ORB high to chase"
    marks = ["🎯 WHY HIGH", "🧠 GRADE NOTE", "💰 ENTRY", "⏱ KEY TIMES",
             "Every section and event: /why REGN 2026-10-30 full"]
    at = [lines.index(m) for m in marks]
    assert at == sorted(at) and len(set(at)) == len(at)
    # the long layout's sections are NOT in the short one
    for gone in ("🧮 SCORE", "📅 LIFECYCLE", "🔍 Fill diagnosis", "⚖️ JUDGE", "🎯 DETECTED",
                 "💰 OUTCOME", "🧠 CATALYST GRADE", "Theme:"):
        assert gone not in body
    # Telegram cannot render pipe tables (CLAUDE.md) and /why posts with no parse_mode
    assert "|" not in body and "*" not in body


def test_the_score_is_parts_out_of_their_maximum_with_the_bar_in_raw_points(monkeypatch):
    body = _short(monkeypatch)
    assert ("   gap 10/10 · liquidity 15/15 · catalyst 15/25 · theme 0/10 · float 0/5 · "
            "pre-market volume 0/5") in body
    assert "   raw 40 of 70 · HIGH bar 40 · exactly on the bar" in body
    assert "   could still add: catalyst +10 · theme +10 · float +5 · pre-market volume +5" in body


def test_entry_says_no_order_was_placed_and_never_describes_a_resting_order(monkeypatch):
    body = _short(monkeypatch)
    assert "   plan: buy $869.88 · stop $817.50 · risk $52.38 a share" in body
    assert "   result: no order was placed — price had run past the buy point; chasing it at " \
           "$928.33 would have risked $110.83 a share against $52.38 planned (cap 1.5x)" in body
    # the old section's phantom: a limit, a trigger "hit", "moved past limit too fast"
    assert "limit $" not in body and "Trigger" not in body and "too fast" not in body


def test_key_times_keep_only_the_decisive_events(monkeypatch):
    body = _short(monkeypatch)
    section = body.split("⏱ KEY TIMES\n")[1].split("\n\n")[0].split("\n")
    assert section == ["   09:35  Real-time prices lifted the gap over the floor",
                       "   09:36  Alert sent",
                       "   09:36  Entry skipped by the chase cap"]
    # shadow / trace / bookkeeping rows and the false-alarm row never appear
    for noise in ("shadow", "trace", "judge", "rubric", "provenance", "failed", "exposure"):
        assert noise not in " ".join(section).lower()


def test_short_is_much_shorter_than_full(monkeypatch):
    fx.wire(monkeypatch, fx.regn_world())
    short, full = fx.render(_REGN_SHORT_TASK), fx.render(_REGN_SHORT_TASK + " full")
    assert len(short.split("\n")) <= 25 and len(short) < len(full) / 2


def test_the_grade_note_is_one_line_with_the_reason(monkeypatch):
    body = _short(monkeypatch)
    note = body.split("🧠 GRADE NOTE\n")[1].split("\n")[0]
    assert note.startswith("   strong · set by the news grader · held all day — \"Regeneron announced")


def test_an_order_that_existed_shows_the_tape_verdict_in_entry(monkeypatch):
    body = _short(monkeypatch, fx.unfilled_world(), "/why ABCD 2026-10-30")
    assert "NOT BOUGHT — entry order expired unfilled" in body.split("\n")[0]
    assert "   result: order placed, never filled — Entry order expired unfilled" in body
    assert "   🟢 Price topped at $864.00, never reached trigger $869.88" in body
    assert "   10:00  Unfilled at the 10:00 cleanup, order cancelled" in body


# ── `full` keeps every current line ──────────────────────────────────────────────────────────


def test_full_equals_todays_output_when_an_order_existed(monkeypatch):
    fx.wire(monkeypatch, fx.unfilled_world())
    golden = (_FIX / "why_716_unfilled_full_before.txt").read_text()
    assert fx.render("/why ABCD 2026-10-30 full") == golden


def test_full_for_regn_differs_from_todays_output_only_in_the_fill_diagnosis_body(monkeypatch):
    fx.wire(monkeypatch, fx.regn_world())
    before = (_FIX / "why_716_regn_full_before.txt").read_text().split("\n")
    at = before.index("🔍 Fill diagnosis")
    end = next(i for i in range(at, len(before)) if before[i] == "")
    expected = before[:at + 1] + ["   No order was placed — there was nothing to fill."] + before[end:]
    assert fx.render("/why REGN 2026-10-30 full").split("\n") == expected


@pytest.mark.parametrize("task", [
    "/why REGN 2026-10-30 full", "/why REGN 2026-10-30 FULL", "/why full REGN 2026-10-30",
    "/why REGN full 2026-10-30",
])
def test_full_is_a_flag_not_a_ticker_in_any_position_or_case(monkeypatch, task):
    fx.wire(monkeypatch, fx.regn_world())
    body = fx.render(task)
    assert body.startswith("📋 REGN — lifecycle 2026-10-30")      # the long header, for REGN
    assert "📅 LIFECYCLE" in body


def test_a_failed_short_render_falls_back_to_the_full_view(monkeypatch):
    fx.wire(monkeypatch, fx.regn_world())

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr("agents.market_intelligence.agent.build_why_short_lines", _boom)
    body = fx.render(_REGN_SHORT_TASK)
    assert body.startswith("📋 REGN — lifecycle 2026-10-30") and "📅 LIFECYCLE" in body


def test_the_trade_read_asks_for_entry_order_id(monkeypatch):
    """The mock hands back the whole trade dict whatever the SELECT lists, so a green handler
    test cannot prove the real SQL reads the column the 'no order' decision depends on."""
    world = fx.regn_world()
    fx.wire(monkeypatch, world)
    fx.render("/why REGN 2026-10-30 full")
    trade_sql = next(s for s in world["sql"] if "FROM mi_live_trades" in s and "stop_price" in s)
    assert "entry_order_id" in trade_sql


# ── the "out of" maxima are READ from the score table ────────────────────────────────────────


def test_part_maxima_come_from_the_live_table():
    m = part_maxima(SCORE_WEIGHTS)
    assert m == {"gap": 10, "liquidity": 15, "catalyst": 25, "float": 5,
                 "vol_conviction": 5, "theme_bonus": 10}
    assert part_maxima(SCORE_WEIGHTS_LEGACY)["gap"] == 25        # the legacy ladder tops out at 25


def test_a_retuned_table_moves_the_out_of_figures(monkeypatch):
    bumped = copy.deepcopy(SCORE_WEIGHTS)
    bumped["catalyst"]["points"]["game_changer"] = 30
    bumped["theme_bonus"]["points"] = 12
    monkeypatch.setattr(ep_score_math, "SCORE_WEIGHTS", bumped)
    out = "\n".join(score_short_lines(_scored_row()))
    assert "catalyst 15/30" in out and "theme 0/12" in out and "raw 37 of 77" in out


def test_legacy_rows_use_the_legacy_table():
    row = _scored_row(weights=SCORE_WEIGHTS_LEGACY, side="legacy", gap=12.0, bar=70.0)
    out = "\n".join(score_short_lines(row))
    assert "gap 15/25" in out and "of 85" in out     # 12% pays 15 on the old ladder


def test_under_the_bar_says_how_far_short():
    out = score_short_lines(_scored_row())                 # FTAI 10-29: 37 raw, bar 40 raw
    assert "   raw 37 of 70 · HIGH bar 40 · 3 short" in out


def test_a_regime_boost_moves_the_bar_in_raw_points():
    out = score_short_lines(_scored_row(mult=1.2, quality="strong", adv_dollar=600_000_000))
    bar_line = next(ln for ln in out if "HIGH bar" in ln)
    assert "Bull-day boost, x1.20" in bar_line and "HIGH bar 34" in bar_line


def test_a_floor_lift_is_shown_as_a_lift_not_a_part_with_a_maximum():
    row = _scored_row(gap=10.5, quality="game_changer", adv_dollar=10_000_000)
    assert row["score_breakdown"].get("conviction_floor")
    out = "\n".join(score_short_lines(row))
    assert "floor lift +" in out and "floor lift +" not in out.split("raw")[1]
    lift = row["score_breakdown"]["conviction_floor"]
    assert f"raw {sum(row['score_breakdown'].values()):g} of 70" in out and lift > 0


def test_no_stored_parts_gives_no_short_score_lines():
    assert score_short_lines(None) == []
    assert score_short_lines({"ep_score": 55.0, "score_breakdown": None}) == []


# ── helpers ──────────────────────────────────────────────────────────────────────────────────

_REASON = ("setup:chase_cap_exceeded: limit $928.33 risk $110.83/sh vs planned $52.38/sh "
           "(cap 1.50x, ORB high $869.88)")


def test_chase_cap_plain_words():
    assert _chase_cap_plain(_REASON) == (
        "price had run past the buy point; chasing it at $928.33 would have risked $110.83 a "
        "share against $52.38 planned (cap 1.5x)")
    assert _chase_cap_plain("setup:stop_too_wide: ORB $1.24") is None
    assert _chase_cap_plain("setup:chase_cap_exceeded: unparseable") is None
    assert _chase_cap_plain(None) is None


def _ev(h, m, etype, summary="REGN x", s=0):
    return {"created_at": fx.ts(h, m, s), "event_type": etype, "summary": summary, "detail": None}


def test_key_times_past_the_cap_keep_first_two_and_last_three():
    evs = [_ev(9, 30 + i, "stop_updated", f"REGN stop now ${800 + i}.00") for i in range(8)]
    out = _why_key_times(evs, "REGN")
    assert len(out) == 6 and "… 3 more in the full view" in out[2]
    assert out[0].strip().startswith("09:30") and out[-1].strip().startswith("09:37")


def test_key_times_collapse_consecutive_duplicates_and_drop_unlisted_types():
    evs = [_ev(9, 36, "ep_alert"), _ev(9, 36, "ep_alert", s=1), _ev(9, 36, "vol_conviction_shadow"),
           _ev(9, 37, "judge_signal_trace"), _ev(9, 38, "trade_closed", "REGN closed +$120.00")]
    assert _why_key_times(evs, "REGN") == ["   09:36  Alert sent ×2",
                                          "   09:38  Trade closed — closed +$120.00"]


def test_verdict_header_variants():
    a = {"score_tier": "HIGH", "ep_score": 61.2}
    t = lambda **k: {"status": "closed", "total_pnl": 120.5, **k}     # noqa: E731
    d = fx.DAY
    assert _why_verdict_line("X", d, a, None, None, t()).endswith("HIGH 61.2 · BOUGHT — closed +$120.50")
    assert _why_verdict_line("X", d, a, None, None, t(total_pnl=-80)).endswith("closed -$80.00")
    assert _why_verdict_line("X", d, a, None, None, t(status="filled")).endswith("BOUGHT — position open")
    assert _why_verdict_line("X", d, a, None, None, None).endswith("NOT BOUGHT — no trade record")
    # never alerted, never traded: nothing to be "not bought"
    assert _why_verdict_line("X", d, None, {"filter_reason": "r", "ep_score": 61.2}, None, None) \
        == "📋 X 2026-10-30 — not alerted (score 61.2)"


def test_short_builder_survives_every_input_missing():
    out = build_why_short_lines("X", fx.DAY, alert=None, trade=None, scan=None, grade=None,
                                events=[], score_row=None, diag_lines=[])
    assert out[0] == "📋 X 2026-10-30 — no alert" and out[-1].endswith("/why X 2026-10-30 full")
