"""#598 (2026-10-04) — the HTF digest pushes a stage TRANSITION into TIGHTENING / COILED.

WHY. CDNA reached TIGHTENING on 2026-08-18, the day before an experienced trader bought it. The
only thing that ever carried that to the operator was a one-line roll-call of bare tickers
("NEW TIGHTENING") inside a digest that also repeated every COILED name daily. This pins the
replacement: the digest's first section, NEW TODAY, one line per ticker that moved UP into
TIGHTENING or COILED today — ticker · stage · run-up · pivot · base tightness.

WHAT IS PINNED (each is a failure the operator would otherwise find out about by not hearing it):
  * the RULE   — pushes on entry, silent while it stays, silent on a relapse, pushes again on
                 re-entry after INVALIDATED / unqualified / absence;
  * the DEDUPE — one push per (ticker, stage, scan date) however many times that scan is re-run,
                 keyed on the SCAN date; a push whose Telegram failed is retried;
  * M&A        — a deal-pinned / M&A-suppressed name never messages;
  * the WIRING — `run_flag_scan` hands the digest the real previous-stage map and the post-M&A
                 result, end to end;
  * the HTML   — only <b>/<i>/<code>, balanced, no stray Markdown, every dynamic value escaped.

Read-only surface: nothing here touches a stage, threshold, entry or trade path.
"""
from __future__ import annotations

import json
from datetime import date
from html.parser import HTMLParser
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import briefing, db, ma_filter
from agents.market_intelligence import flag_detector as fd
from shared import telegram_format as tf
from tests.conftest import make_mock_pool

D1 = date(2026, 8, 18)


# ── helpers ────────────────────────────────────────────────────────────────

def _row(ticker, stage, *, runup=1.30, pivot=49.76, rr=0.95, vr=0.65, age=10, fresh=False,
         reason=None, **extra):
    return {
        "ticker": ticker, "stage": stage, "runup_pct": runup, "pivot_high_price": pivot,
        "range_contraction_ratio": rr, "vol_contraction_ratio": vr, "base_age": age,
        "fresh_tight_fires": fresh, "reason": reason, **extra,
    }


def _board(*rows):
    out = {s: [] for s in
           ("TRIGGERED", "COILED", "TIGHTENING", "WATCH", "INVALIDATED", "unqualified")}
    for r in rows:
        out[r["stage"]].append(r)
    return out


class _World:
    """The two side effects of a digest run — Telegram and the audit log — as one in-memory
    world, so a re-run sees what the previous run wrote (the thing the dedupe depends on)."""

    def __init__(self):
        self.sent: list[tuple[str, object]] = []
        self.audit: list[tuple[str, str, str]] = []
        self.telegram_ok = True
        self.lookup_sql: list[str] = []
        self.lookup_fails = False


@pytest.fixture
def world(monkeypatch):
    w = _World()

    async def _send(text, chat_id=None, parse_mode=None, reply_markup=None):
        w.sent.append((text, parse_mode))
        return w.telegram_ok

    async def _audit(event_type, summary, detail="", *, conn=None):
        w.audit.append((event_type, summary, detail))

    pool, conn = make_mock_pool()

    async def _fetch(sql, event_type, keys):
        w.lookup_sql.append(sql)
        return [{"summary": s} for (ev, s, _d) in w.audit if ev == event_type and s in keys]

    conn.fetch = AsyncMock(side_effect=_fetch)

    async def _get_pool():
        if w.lookup_fails:
            raise RuntimeError("pool down")
        return pool

    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    monkeypatch.setattr(db, "log_audit_event", _audit)
    monkeypatch.setattr(db, "get_pool", _get_pool)
    return w


def _transition_rows(w):
    return [a for a in w.audit if a[0] == "flag_stage_transition"]


# ── the RULE (pure) ────────────────────────────────────────────────────────

@pytest.mark.parametrize("prev,today,fires", [
    # entering TIGHTENING: from anywhere below it
    ("WATCH", "TIGHTENING", True),
    (None, "TIGHTENING", True),
    ("unqualified", "TIGHTENING", True),
    ("INVALIDATED", "TIGHTENING", True),
    # staying, or a relapse down into it, is not an entry
    ("TIGHTENING", "TIGHTENING", False),
    ("COILED", "TIGHTENING", False),
    ("TRIGGERED", "TIGHTENING", False),
    # entering COILED
    ("TIGHTENING", "COILED", True),
    ("WATCH", "COILED", True),
    (None, "COILED", True),
    ("INVALIDATED", "COILED", True),
    ("unqualified", "COILED", True),
    ("COILED", "COILED", False),
    ("TRIGGERED", "COILED", False),
])
def test_transition_rule(prev, today, fires):
    ymap = {} if prev is None else {"AAA": prev}
    got = fd.stage_transitions(_board(_row("AAA", today)), ymap)
    assert [(t["ticker"], t["stage"], t["prev"]) for t in got] == (
        [("AAA", today, prev)] if fires else []
    )


@pytest.mark.parametrize("stage", ["WATCH", "TRIGGERED", "INVALIDATED", "unqualified"])
def test_only_tightening_and_coiled_entries_are_pushed(stage):
    assert fd.stage_transitions(_board(_row("AAA", stage)), {}) == []


def test_one_ticker_across_days_fires_only_on_each_entry():
    """WATCH -> TIGHTENING (push) -> stays (silent) -> COILED (push) -> stays (silent) ->
    INVALIDATED (silent) -> TIGHTENING again (push) -> stays (silent)."""
    days = ["WATCH", "TIGHTENING", "TIGHTENING", "COILED", "COILED",
            "INVALIDATED", "TIGHTENING", "TIGHTENING"]
    fired, prev = [], None
    for i, stage in enumerate(days):
        got = fd.stage_transitions(_board(_row("CDNA", stage)), {} if prev is None else {"CDNA": prev})
        fired.extend((i, t["stage"]) for t in got)
        prev = stage
    assert fired == [(1, "TIGHTENING"), (3, "COILED"), (6, "TIGHTENING")]


def test_order_is_coiled_first_then_by_run_up():
    board = _board(
        _row("LOW", "TIGHTENING", runup=1.0), _row("HIGH", "TIGHTENING", runup=2.5),
        _row("COIL", "COILED", runup=0.9),
    )
    got = fd.stage_transitions(board, {})
    assert [t["ticker"] for t in got] == ["COIL", "HIGH", "LOW"]


# ── M&A: a deal-pinned name never messages ─────────────────────────────────

def test_mna_suppressed_row_is_not_a_transition_in_the_real_flow():
    """`run_flag_scan` rewrites a hit to stage=unqualified + original_stage + reason=mna_filter:*,
    so it lands in the `unqualified` bucket — which no transition ever reads."""
    hit = _row("KALV", "unqualified", original_stage="COILED", reason="mna_filter:deal_pin_signature")
    assert fd.stage_transitions(_board(hit), {"KALV": "TIGHTENING"}) == []


@pytest.mark.parametrize("extra", [
    {"original_stage": "COILED"},
    {"reason": "mna_filter:polygon_news"},
    {"reason": "mna_filter:deal_pin_fresh"},
])
def test_mna_row_never_a_transition_even_if_misfiled(extra):
    """Belt and braces: even handed over still filed under COILED, it cannot message."""
    r = _row("KALV", "COILED", **extra)
    assert fd.stage_transitions(_board(r), {"KALV": "TIGHTENING"}) == []


# ── the MESSAGE (pipeline) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watch_to_tightening_messages_once_with_every_field(world):
    await fd.send_flag_digest(_board(_row("CDNA", "TIGHTENING")), D1, yesterday_map={"CDNA": "WATCH"})
    assert len(world.sent) == 1
    text, mode = world.sent[0]
    assert mode == "HTML"
    assert "NEW TODAY" in text
    line = next(ln for ln in text.splitlines() if "CDNA" in ln and "TIGHTENING" in ln)
    for needle in ("<code>CDNA</code>", "<b>TIGHTENING</b>", "run-up +130%", "pivot $49.76",
                   "range 0.95×", "volume 0.65×", "base 10d"):
        assert needle in line, f"{needle!r} missing from {line!r}"
    assert "not a trade signal" in text and "no buy point or stop" in text
    # the durable record, in the dedupe key's shape
    rows = _transition_rows(world)
    assert [r[1] for r in rows] == ["CDNA entered TIGHTENING 2026-08-18"]
    detail = json.loads(rows[0][2])
    assert (detail["prev_stage"], detail["telegram"], detail["pivot_high_price"]) == ("WATCH", "sent", 49.76)


@pytest.mark.asyncio
async def test_staying_tightening_next_day_is_silent(world):
    await fd.send_flag_digest(_board(_row("CDNA", "TIGHTENING")), D1, yesterday_map={"CDNA": "TIGHTENING"})
    assert world.sent == [] and world.audit == []


@pytest.mark.asyncio
async def test_coiled_after_tightening_messages_and_is_not_listed_twice(world):
    await fd.send_flag_digest(_board(_row("CDNA", "COILED", rr=0.6, vr=0.5)), D1,
                              yesterday_map={"CDNA": "TIGHTENING"})
    text = world.sent[0][0]
    assert "<b>COILED</b>" in text and "range 0.60×" in text
    assert text.count("<code>CDNA</code>") == 1          # NEW TODAY only, not again in the roster
    assert "still coiled" not in text
    assert [r[1] for r in _transition_rows(world)] == ["CDNA entered COILED 2026-08-18"]


@pytest.mark.asyncio
async def test_invalidated_then_back_to_tightening_messages_again(world):
    d = [date(2026, 8, 18 + i) for i in range(4)]
    plan = [("TIGHTENING", "WATCH"),        # entry            -> push
            ("TIGHTENING", "TIGHTENING"),  # stays            -> silent
            ("INVALIDATED", "TIGHTENING"), # leaves           -> silent (nothing to push)
            ("TIGHTENING", "INVALIDATED")] # re-enters        -> push again
    for day, (today, prev) in zip(d, plan):
        await fd.send_flag_digest(_board(_row("CDNA", today)), day, yesterday_map={"CDNA": prev})
    assert len(world.sent) == 2
    assert [r[1] for r in _transition_rows(world)] == [
        "CDNA entered TIGHTENING 2026-08-18", "CDNA entered TIGHTENING 2026-08-21",
    ]


@pytest.mark.asyncio
async def test_rerun_of_the_same_scan_date_does_not_push_again(world):
    """The DEDUPE. A re-run of the same scan (missed-job recovery, a manual re-run) must not
    re-announce a transition it already delivered — even when the digest itself still goes out."""
    board = _board(_row("CDNA", "TIGHTENING"), _row("ZZZ", "COILED", rr=0.7, vr=0.6, runup=1.0))
    ymap = {"CDNA": "WATCH", "ZZZ": "COILED"}                  # ZZZ was already coiled: roster only
    await fd.send_flag_digest(board, D1, yesterday_map=ymap)
    await fd.send_flag_digest(board, D1, yesterday_map=ymap)
    first, second = world.sent[0][0], world.sent[1][0]
    assert "NEW TODAY" in first and "<code>CDNA</code>" in first
    assert "NEW TODAY" not in second and "CDNA" not in second  # roster still goes out, CDNA does not
    assert "<code>ZZZ</code>" in second
    assert len(_transition_rows(world)) == 1                   # one row per real transition
    # the lookup asked for exactly that key, by exact match on the audit event
    assert "summary = ANY($2::text[])" in world.lookup_sql[-1]


@pytest.mark.asyncio
async def test_rerun_with_nothing_else_to_say_sends_nothing(world):
    board = _board(_row("CDNA", "TIGHTENING"))
    await fd.send_flag_digest(board, D1, yesterday_map={"CDNA": "WATCH"})
    await fd.send_flag_digest(board, D1, yesterday_map={"CDNA": "WATCH"})
    assert len(world.sent) == 1


@pytest.mark.asyncio
async def test_the_dedupe_key_is_the_scan_date_not_the_clock(world):
    """A recovery re-run happens on a LATER calendar day than the scan it re-runs; the row
    written then must still match. The key is built from scan_date alone."""
    board = _board(_row("CDNA", "TIGHTENING"))
    await fd.send_flag_digest(board, D1, yesterday_map={"CDNA": "WATCH"})
    assert fd._transition_key("CDNA", "TIGHTENING", D1) == _transition_rows(world)[0][1]
    # a DIFFERENT scan date for the same ticker/stage is a different transition
    await fd.send_flag_digest(board, date(2026, 8, 19), yesterday_map={"CDNA": "WATCH"})
    assert len(world.sent) == 2


@pytest.mark.asyncio
async def test_a_failed_send_is_recorded_as_not_delivered_and_retried(world):
    board = _board(_row("CDNA", "TIGHTENING"))
    world.telegram_ok = False
    await fd.send_flag_digest(board, D1, yesterday_map={"CDNA": "WATCH"})
    assert [r[1] for r in _transition_rows(world)] == ["CDNA entered TIGHTENING 2026-08-18 (not delivered)"]
    assert json.loads(_transition_rows(world)[0][2])["telegram"] == "not delivered"
    world.telegram_ok = True
    await fd.send_flag_digest(board, D1, yesterday_map={"CDNA": "WATCH"})
    assert len(world.sent) == 2                                # the retry went out
    assert _transition_rows(world)[-1][1] == "CDNA entered TIGHTENING 2026-08-18"
    await fd.send_flag_digest(board, D1, yesterday_map={"CDNA": "WATCH"})
    assert len(world.sent) == 2                                # and now it is deduped


@pytest.mark.asyncio
async def test_a_broken_dedupe_lookup_fails_open(world):
    """A repeat on a quiet surface beats a silently dropped push."""
    world.lookup_fails = True
    await fd.send_flag_digest(_board(_row("CDNA", "TIGHTENING")), D1, yesterday_map={"CDNA": "WATCH"})
    assert len(world.sent) == 1 and "CDNA" in world.sent[0][0]


@pytest.mark.asyncio
async def test_a_broken_transition_step_still_sends_the_roster_and_is_named(world, monkeypatch):
    def _boom(*a, **k):
        raise ValueError("bad row")
    monkeypatch.setattr(fd, "stage_transitions", _boom)
    board = _board(_row("ZZZ", "COILED", rr=0.7, vr=0.6))
    await fd.send_flag_digest(board, D1, yesterday_map={"ZZZ": "COILED"})
    assert len(world.sent) == 1 and "<code>ZZZ</code>" in world.sent[0][0]
    errs = [a for a in world.audit if a[0] == "flag_stage_transition_error"]
    assert len(errs) == 1 and "ValueError" in errs[0][1]
    assert "error" in errs[0][0]       # the name the nightly %error% sweep lists


@pytest.mark.asyncio
async def test_a_quiet_day_sends_nothing(world):
    await fd.send_flag_digest(_board(_row("AAA", "WATCH"), _row("BBB", "INVALIDATED")), D1,
                              yesterday_map={"AAA": "WATCH", "BBB": "INVALIDATED"})
    assert world.sent == [] and world.audit == []


@pytest.mark.asyncio
async def test_triggered_and_dropped_out_still_render(world):
    board = _board(
        _row("TRG", "TRIGGERED", breakout_close=60.0, base_high=55.5, breakout_volume_ratio=2.1),
        _row("OLD", "INVALIDATED"),
    )
    await fd.send_flag_digest(board, D1, yesterday_map={"TRG": "COILED", "OLD": "TIGHTENING"})
    text = world.sent[0][0]
    assert "TRIGGERED (1)" in text and "close $60.00 above $55.50" in text
    assert "1 dropped out" in text
    assert "NEW TODAY" not in text                              # TRIGGERED is not a push stage


# ── the HTML ───────────────────────────────────────────────────────────────

class _TagCheck(HTMLParser):
    ALLOWED = {"b", "i", "code"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED or attrs:
            self.bad.append(f"<{tag}>")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.bad.append(f"</{tag}>")


def _full_digest():
    board = _board(
        _row("CDNA", "TIGHTENING"),
        _row("NEWC", "COILED", rr=0.6, vr=0.5, fresh=True),
        _row("OLDC", "COILED", rr=0.7, vr=0.6),
        _row("TRG", "TRIGGERED", breakout_close=60.0, base_high=55.5, breakout_volume_ratio=2.1),
        _row("GONE", "INVALIDATED"),
        _row("W1", "WATCH"),
    )
    ymap = {"CDNA": "WATCH", "NEWC": "TIGHTENING", "OLDC": "COILED", "TRG": "COILED"}
    transitions = fd.stage_transitions(board, ymap)
    return fd.build_flag_digest(board, D1, transitions)


def test_the_digest_is_clean_html():
    text = _full_digest()
    p = _TagCheck()
    p.feed(text)
    p.close()
    assert p.bad == [] and p.stack == []
    for stray in ("*", "`", "\\", "_"):
        assert stray not in text, f"stray {stray!r} in {text!r}"
    assert "<" not in tf.to_plain(text) and "&lt;" not in tf.to_plain(text)
    assert "actionable setup" not in text           # a stage is a state, not a setup
    # nothing in it needs the Markdown converter, and converting it again would damage it
    assert tf.chunk_html(text) == [text]


def test_fresh_tight_and_missing_numbers_render_in_plain_words():
    t = {"ticker": "AAA", "stage": "TIGHTENING", "prev": None,
         "row": _row("AAA", "TIGHTENING", rr=None, vr=None, fresh=True, pivot=None, age=None, runup=None)}
    line = fd._fmt_transition(t)
    assert "last 2 bars tight" in line and "pivot —" in line and "run-up —" in line
    assert "base" not in line


def test_every_dynamic_value_is_escaped():
    t = {"ticker": "A&B<", "stage": "COILED", "prev": None, "row": _row("A&B<", "COILED")}
    line = fd._fmt_transition(t)
    assert "A&amp;B&lt;" in line and "A&B<" not in line


def test_the_legend_quotes_the_live_stage_bars():
    text = _full_digest()
    assert f"range under {fd._RANGE_CONTRACTION_MAX:.2f}" in text
    assert f"volume under {fd._VOL_CONTRACTION_MAX:.2f}" in text


# ── the WIRING: run_flag_scan end to end ───────────────────────────────────

@pytest.mark.asyncio
async def test_run_flag_scan_pushes_only_the_real_new_entries(world, monkeypatch):
    """AAA WATCH -> TIGHTENING (push) · BBB TIGHTENING -> COILED but the M&A layer rewrites it to
    unqualified (silent) · CCC TIGHTENING -> TIGHTENING (silent)."""
    yesterday = {"AAA": "WATCH", "BBB": "TIGHTENING", "CCC": "TIGHTENING"}
    today = {"AAA": "TIGHTENING", "BBB": "COILED", "CCC": "TIGHTENING"}

    monkeypatch.setattr(db, "get_flag_universe", AsyncMock(return_value={t: ["rs_top200"] for t in today}))
    monkeypatch.setattr(db, "get_yesterday_flag_stages", AsyncMock(return_value=yesterday))
    monkeypatch.setattr(db, "get_recent_flag_stages", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_rs_for_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_sectors_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_yesterday_flag_pivots", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_failure_carry", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_recent_daily_history", AsyncMock(return_value=[{}] * 80))
    monkeypatch.setattr(db, "insert_flag_candidate", AsyncMock())
    monkeypatch.setattr(fd, "_check_deal_pin_signatures_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(fd, "reconcile_flag_state_post_eod", AsyncMock())

    def _metrics(history, ticker=None, **kw):
        return _row(ticker, today[ticker])
    monkeypatch.setattr(fd, "compute_flag_metrics", _metrics)

    async def _is_ma(ticker, **kw):
        return (ticker == "BBB"), ({"source": "polygon_news"} if ticker == "BBB" else {})
    monkeypatch.setattr(ma_filter, "is_likely_ma", _is_ma)
    monkeypatch.setattr(ma_filter, "should_log_mna_filter_fired", AsyncMock(return_value=False))

    by_stage = await fd.run_flag_scan(D1)

    assert [r["ticker"] for r in by_stage["unqualified"]] == ["BBB"]      # the M&A layer fired
    assert len(world.sent) == 1
    text = world.sent[0][0]
    new_today = text.split("NEW TODAY")[1]
    assert "<code>AAA</code>" in new_today
    assert "BBB" not in text and "CCC" not in text
    assert [r[1] for r in _transition_rows(world)] == ["AAA entered TIGHTENING 2026-08-18"]


# ── a base of 5 days or fewer: the 1.00 ratios are meaningless, show the fresh-tight measure ──────
# wk1010 (2026-10-10). Live 2026-10-09: KOD, base 5d, stored range 1 / volume 1 while the last two
# bars read 6.64% against a 10.53% ATR (0.63x). The detector compares the base's last 5 days with
# its first 5 over min(5, base_age) rows, so at base_age <= 5 both are the same bars. DISPLAY ONLY.

def _short(age, *, ticker="KOD", fires=True, tr=5.74, atr=10.76, **kw):
    return _row(ticker, "COILED", rr=1.0, vr=1.0, age=age, fresh=fires,
                fresh_2bar_tr_pct=tr, atr14_pct=atr, **kw)


def test_short_base_boundary_matches_the_detectors_window():
    assert [fd.is_short_base(a) for a in (3, 4, 5)] == [True, True, True]
    assert [fd.is_short_base(a) for a in (6, 12, None)] == [False, False, False]


def test_fresh_tight_ratio_is_two_bar_range_over_atr_or_none():
    assert fd.fresh_tight_ratio({"fresh_2bar_tr_pct": 5.74, "atr14_pct": 10.76}) == pytest.approx(0.5335, abs=1e-3)
    assert fd.fresh_tight_ratio({"fresh_2bar_tr_pct": "3.0", "atr14_pct": 6}) == pytest.approx(0.5)
    for bad in ({}, {"fresh_2bar_tr_pct": 5.7}, {"atr14_pct": 10.0},
                {"fresh_2bar_tr_pct": 5.7, "atr14_pct": 0}, {"fresh_2bar_tr_pct": "x", "atr14_pct": 9}):
        assert fd.fresh_tight_ratio(bad) is None


@pytest.mark.parametrize("age", [3, 4, 5])
def test_short_base_new_today_line_shows_the_measure_not_1_00(age):
    t = {"ticker": "KOD", "stage": "COILED", "prev": "WATCH", "row": _short(age)}
    line = fd._fmt_transition(t)
    assert "last 2 bars tight (0.53× usual range)" in line
    assert "1.00" not in line and "range 1" not in line and "volume 1" not in line
    assert f"base {age}d" in line


def test_short_base_without_a_computable_measure_says_n_a():
    # base 3: the fresh-tight path needs >= 4, so nothing is persisted -> 'n/a', never 1.00
    t = {"ticker": "KOD", "stage": "TIGHTENING", "prev": None,
         "row": _short(3, fires=False, tr=None, atr=None)}
    line = fd._fmt_transition(t)
    assert "tightness n/a" in line and "1.00" not in line


def test_short_base_not_firing_shows_the_plain_ratio_without_the_tight_label():
    # KOD 2026-10-09 as stored: held COILED from WATCH, fresh path NOT firing, 6.64 / 10.53
    t = {"ticker": "KOD", "stage": "COILED", "prev": None,
         "row": _short(5, fires=False, tr=6.638630, atr=10.532943)}
    line = fd._fmt_transition(t)
    assert "last 2 bars 0.63× usual range" in line and "tight (" not in line


@pytest.mark.parametrize("age", [6, 12])
def test_longer_bases_render_exactly_as_before(age):
    r = _row("AAA", "TIGHTENING", rr=0.68, vr=0.90, age=age, fresh=False,
             fresh_2bar_tr_pct=5.0, atr14_pct=10.0)
    assert fd._fmt_tightness(r) == "range 0.68×, volume 0.90×"
    r["fresh_tight_fires"] = True
    assert fd._fmt_tightness(r) == "range 0.68×, volume 0.90×, last 2 bars tight"


def test_standing_coiled_roster_line_follows_the_same_rule():
    short = fd._fmt_coiled(_short(5, fires=False, tr=6.638630, atr=10.532943))
    assert "last 2 bars 0.63× usual range" in short and "1.00" not in short
    long_ = fd._fmt_coiled(_row("OLDC", "COILED", rr=0.7, vr=0.6, age=14))
    assert long_.endswith("range 0.70 · volume 0.60") and "base 14d" in long_


def _digest_for(*rows):
    board = _board(*rows)
    return fd.build_flag_digest(board, D1, fd.stage_transitions(board, {}))


def test_legend_explains_the_short_base_measure_only_when_one_is_shown():
    both = _digest_for(_short(4), _row("LONG", "TIGHTENING"))
    assert f"{fd._SHORT_BASE_MAX} days or fewer" in both
    assert f"tight = under {fd._FRESH_TIGHT_RATIO_MAX:.2f}" in both
    only_long = _digest_for(_row("LONG", "TIGHTENING"))
    assert "days or fewer" not in only_long
    # the original sentence is untouched either way
    for text in (both, only_long):
        assert f"range under {fd._RANGE_CONTRACTION_MAX:.2f}" in text


def test_short_base_digest_is_still_clean_html():
    text = _digest_for(_short(4), _short(3, ticker="ZZZ", fires=False, tr=None, atr=None))
    p = _TagCheck()
    p.feed(text)
    p.close()
    assert p.bad == [] and p.stack == []
    for stray in ("*", "`", "\\", "_"):
        assert stray not in text, f"stray {stray!r} in {text!r}"


# ── review fixes (wk1010 review, 2026-10-10) ──────────────────────────────────────────────────────

def test_short_base_under_the_bar_but_not_firing_says_why_it_is_not_tight():
    """`fresh_tight_fires` needs the range test AND dry volume. A reading under the bar that did not
    fire (heavy volume) must not print as an unlabelled number the legend calls 'tight'."""
    s = fd.short_base_tightness(_short(5, fires=False, tr=5.9, atr=10.7))   # 0.55 <= 0.60, vol not dry
    assert s == "last 2 bars 0.55× usual range (tight on range, volume not dry)"
    # exactly at the bar: the detector's range test is `ratio > MAX -> not tight`, so 0.60 passes it
    at_bar = fd.short_base_tightness(_short(5, fires=False, tr=6.0, atr=10.0))
    assert "tight on range, volume not dry" in at_bar
    # firing keeps its own label; a reading over the bar stays plain
    assert fd.short_base_tightness(_short(5, fires=True, tr=5.9, atr=10.7)).startswith("last 2 bars tight (")
    assert fd.short_base_tightness(
        _short(5, fires=False, tr=6.64, atr=10.53)) == "last 2 bars 0.63× usual range"


def _standing_digest(*rows):
    """Rows already in their stage yesterday: they sit in the standing roster, never in NEW TODAY."""
    board = _board(*rows)
    ymap = {r["ticker"]: r["stage"] for r in rows}
    assert fd.stage_transitions(board, ymap) == []
    return fd.build_flag_digest(board, D1, [])


def test_standing_short_base_name_gets_the_legend_too():
    """KOD 2026-10-09 is the live case: a short-base name already coiled renders in 'COILED — still
    coiled' with no NEW TODAY block, so the measure used to print with no explanation at all."""
    text = _standing_digest(_short(5, fires=False, tr=6.638630, atr=10.532943))
    assert "NEW TODAY" not in text and "still coiled" in text
    assert "last 2 bars 0.63× usual range" in text
    assert f"{fd._SHORT_BASE_MAX} days or fewer" in text and "volume dry" in text
    # the sentence sits AFTER the roster line it explains
    assert text.index("days or fewer") > text.index("0.63× usual range")


def test_standing_long_base_gets_no_short_base_legend():
    text = _standing_digest(_row("OLDC", "COILED", rr=0.7, vr=0.6, age=14))
    assert "still coiled" in text and "days or fewer" not in text


def test_legend_is_printed_once_when_new_today_and_standing_both_have_a_short_base():
    board = _board(_short(4, ticker="NEWW"), _short(5, ticker="OLDD", fires=False, tr=6.6, atr=10.5))
    text = fd.build_flag_digest(board, D1, fd.stage_transitions(board, {"OLDD": "COILED"}))
    before, after = text.split("still coiled")
    assert "NEWW" in before and "OLDD" in after
    assert text.count("days or fewer") == 1


def test_standing_short_base_cut_by_the_eight_row_cap_does_not_trigger_the_legend():
    """Only a RENDERED short-base row needs the explanation; the '…N more' tail is not rendered."""
    rows = [_row(f"L{i:02d}", "COILED", rr=0.5 + i * 0.01, vr=0.5, age=14) for i in range(8)]
    rows.append(_short(5, ticker="HIDD"))            # stored ratio 1.0 sorts last -> 9th, cut by [:8]
    text = _standing_digest(*rows)
    assert "HIDD" not in text and "1 more" in text and "days or fewer" not in text


@pytest.mark.asyncio
async def test_history_select_carries_the_columns_the_short_base_render_needs(monkeypatch):
    """`/flags TICKER` prints `tightness n/a` on EVERY short-base row if the widened SELECT loses
    fresh_tight_fires / fresh_2bar_tr_pct / atr14_pct. The history render tests monkeypatch the
    fetch, so this is the one test that reads the SQL itself."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    await db.get_ticker_flag_history("kod", 14)
    sql = conn.fetch.await_args.args[0]
    for col in ("fresh_tight_fires", "fresh_2bar_tr_pct", "atr14_pct", "base_age",
                "range_contraction_ratio", "vol_contraction_ratio"):
        assert col in sql, f"history SELECT dropped {col}"
    assert conn.fetch.await_args.args[1] == "KOD"
