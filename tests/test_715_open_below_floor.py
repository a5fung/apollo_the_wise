"""#715 — the flip-up OPEN rule at submission (`entry_pipeline.check_flip_up_open_floor`, stage 4a).

His sign-off 2026-10-31 ("Take all recs") on the #715 study's rec (b): a MAGNA53 alert ADMITTED BY THE
REAL-TIME FLIP-UP — the opening gap read under the floor, the live price over it minutes later — is not
entered when its 09:30 bar OPENED below the gap floor price, `prev_close × (1 + MIN_GAP_PCT/100)`. Shipped
behind the three-mode toggle `magna53_open_below_floor` ('shadow' = the deploy default: enter + record;
'on' = skip `setup:open_below_gap_floor`; 'off' = not read). SSoT: docs/setups/magna53_ep.md 2026-10-31.

The invariants pinned here, in the task's own words:
  1. shadow writes the would-skip row AND enters; on skips with the new reason; off does nothing;
  2. an open at/above the floor enters in every mode;
  3. a non-flip-up alert never reads the rule (no prev-close read, no audit row);
  4. the small-cap paper lane, breakout v1 and 9M never read it (the kwarg is MAGNA53's alone — derived by
     walking every `submit_trade_entry(` call site, not hand-listed);
  5. the floor follows the day's MIN_GAP_PCT (the pct is a PARAMETER; the call site passes the detector's);
  6. the rule FAILS OPEN on every non-answer (unreadable toggle, flip-up row, denominator, bar, exception).

Fixture numbers are the study's own rows (`scripts/probes/_715_study_1031/s2_rows.tsv`, 9% floor):
CEG 2026-10-06 prev 267.62 → floor 291.7058, open 291.11 (0.20% under — the fragile one); HOOD 09-03 prev
106.99 → floor 116.6191, open 113.80; CRWD 08-27 open 208.25 vs floor 206.21 (admitted, +0.99%).
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import ep_detector
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.skip_reasons import (
    SETUP_GAP_BELOW_FLOOR, SETUP_OPEN_BELOW_GAP_FLOOR, humanize,
)
from tests.conftest import make_mock_pool
from tests.test_461_cap_toctou_race import FakeDB, _spec_builder, _wire

REPO = Path(__file__).resolve().parent.parent

# ── the study's rows ──────────────────────────────────────────────────────────────────────────
CEG = dict(ticker="CEG", alert_date=date(2026, 10, 6), prev_close=267.62, open=291.11)     # floor 291.7058
HOOD = dict(ticker="HOOD", alert_date=date(2026, 9, 3), prev_close=106.99, open=113.80)    # floor 116.6191
CRWD = dict(ticker="CRWD", alert_date=date(2026, 8, 27), prev_close=189.18, open=208.25)   # floor 206.21
FLOOR = 9.0
FLIP = {"tick_et": "09:33", "rt_gap": 9.4, "delayed_gap": 8.8, "authoritative": True, "created_at": None}


def _bar(open_px: float) -> dict:
    return {"open": open_px, "high": open_px * 1.02, "low": open_px * 0.99, "close": open_px * 1.01, "volume": 1000}


def _wire_rule(monkeypatch, *, mode="shadow", flip=FLIP, prev_close=CEG["prev_close"],
               mode_raises=False, flip_raises=False, prev_raises=False):
    """Pin the rule's three reads (toggle, flip-up row, prev close) and capture its audit rows.
    Returns (audit_mock, spies) where spies counts how often each read ran."""
    spies = SimpleNamespace(mode=0, flip=0, prev=0)

    async def _mode():
        spies.mode += 1
        if mode_raises:
            raise RuntimeError("toggle store down")
        return mode

    async def _flip(ticker, alert_date):
        spies.flip += 1
        if flip_raises:
            raise RuntimeError("audit log down")
        return flip

    async def _prev(ticker, before_date, timeout=None):
        spies.prev += 1
        if prev_raises:
            raise RuntimeError("daily closes down")
        return prev_close

    monkeypatch.setattr(ep, "get_open_floor_mode", _mode)
    monkeypatch.setattr(ep, "find_flip_up_admission", _flip)
    monkeypatch.setattr("agents.market_intelligence.db.get_prev_close", _prev)
    audit = AsyncMock()
    monkeypatch.setattr(ep, "log_audit_event", audit)
    return audit, spies


def _events(audit) -> list[str]:
    return [c.args[0] for c in audit.await_args_list]


def _detail(audit, event: str) -> dict:
    (call,) = [c for c in audit.await_args_list if c.args[0] == event]
    return json.loads(call.args[2])


_ROW_BAR = object()      # sentinel: "the row's own 09:30 bar" — so a test CAN pass bar=None


def _run(row=CEG, *, bar=_ROW_BAR, floor=FLOOR, alert=None):
    ctx = alert if alert is not None else {"ticker": row["ticker"], "alert_date": row["alert_date"], "gap_pct": 9.4}
    return asyncio.run(ep.check_flip_up_open_floor(
        row["ticker"], ctx, _bar(row["open"]) if bar is _ROW_BAR else bar, floor))


# ── 1. the three modes on a flip-up that opened BELOW the floor (CEG, the fragile 0.20%) ─────────

def test_shadow_records_the_would_skip_and_lets_the_entry_proceed(monkeypatch):
    audit, spies = _wire_rule(monkeypatch, mode="shadow")
    assert _run(CEG) == (True, None)
    assert _events(audit) == ["magna53_open_floor_checked", "magna53_open_below_floor_would_skip"]
    d = _detail(audit, "magna53_open_below_floor_would_skip")
    assert d["ticker"] == "CEG" and d["mode"] == "shadow" and d["verdict"] == "would_skip"
    assert d["open"] == 291.11 and d["prev_close"] == 267.62 and d["floor_pct"] == 9.0
    assert d["floor_price"] == pytest.approx(291.7058, abs=1e-4)
    assert d["gap_at_open_pct"] == pytest.approx(8.78, abs=0.01)      # the gap AT THE OPEN, under 9%
    assert d["flip_up_tick_et"] == "09:33" and d["flip_up_authoritative"] is True
    # the summary carries every number the operator needs to check it by hand
    summary = [c for c in audit.await_args_list if c.args[0] == "magna53_open_below_floor_would_skip"][0].args[1]
    assert "$291.11" in summary and "$291.71" in summary and "$267.62" in summary and "SHADOW" in summary


def test_on_skips_with_the_new_reason(monkeypatch):
    audit, spies = _wire_rule(monkeypatch, mode="on")
    ok, reason = _run(CEG)
    assert ok is False
    assert reason.startswith(SETUP_OPEN_BELOW_GAP_FLOOR + ":")
    assert "$291.11" in reason and "$291.71" in reason and "$267.62" in reason and "09:33 ET" in reason
    # the checked row says 'skip'; NO would-skip row (that is the shadow's word)
    assert _events(audit) == ["magna53_open_floor_checked"]
    assert _detail(audit, "magna53_open_floor_checked")["verdict"] == "skip"


def test_off_reads_nothing_and_enters(monkeypatch):
    audit, spies = _wire_rule(monkeypatch, mode="off")
    assert _run(CEG) == (True, None)
    assert spies.flip == 0 and spies.prev == 0 and _events(audit) == []


@pytest.mark.parametrize("mode", ["shadow", "on", "off"])
def test_hood_the_largest_dropped_name_follows_its_mode(monkeypatch, mode):
    audit, _ = _wire_rule(monkeypatch, mode=mode, prev_close=HOOD["prev_close"])
    ok, reason = _run(HOOD)
    assert ok is (mode != "on")
    if mode == "on":
        assert reason.startswith(SETUP_OPEN_BELOW_GAP_FLOOR) and "$113.80" in reason and "$116.62" in reason


# ── 2. an open AT or ABOVE the floor enters in every mode ────────────────────────────────────────

@pytest.mark.parametrize("mode", ["shadow", "on", "off"])
def test_crwd_open_above_the_floor_enters_in_every_mode(monkeypatch, mode):
    audit, spies = _wire_rule(monkeypatch, mode=mode, prev_close=CRWD["prev_close"])
    assert _run(CRWD) == (True, None)
    if mode == "off":
        assert _events(audit) == []
    else:
        assert _events(audit) == ["magna53_open_floor_checked"]       # the positive observable
        assert _detail(audit, "magna53_open_floor_checked")["verdict"] == "clear"


@pytest.mark.parametrize("mode", ["shadow", "on"])
def test_an_open_exactly_at_the_floor_price_is_NOT_below(monkeypatch, mode):
    """`open < floor` strictly, as the study replayed it (`open_ge_floor = orb_o >= fpx`) — and a TRUE tie
    reads "at the floor": 100 × 1.09 is 109.00000000000001 in binary, so without the 6-dp rounding an open
    of exactly $109.00 would have been called below (float noise, not the rule)."""
    audit, _ = _wire_rule(monkeypatch, mode=mode, prev_close=100.0)
    row = dict(ticker="AT", alert_date=date(2026, 10, 6), open=109.0)       # 100 × 1.09 exactly
    assert _run(row) == (True, None)
    assert _detail(audit, "magna53_open_floor_checked")["verdict"] == "clear"
    row["open"] = 108.99
    ok, _r = _run(row)
    assert ok is (mode != "on")


# ── 3. a non-flip-up alert never reads the rule ─────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["shadow", "on"])
def test_a_non_flip_up_alert_never_reads_the_rule(monkeypatch, mode):
    """Admitted by the delayed read (no `ep_rt_floor_flip_up` row today): no denominator read, no audit
    row, the entry proceeds — even with an open far below the floor and the toggle 'on'."""
    audit, spies = _wire_rule(monkeypatch, mode=mode, flip=None)
    assert _run(CEG, bar=_bar(200.0)) == (True, None)
    assert spies.flip == 1 and spies.prev == 0 and _events(audit) == []


def test_no_floor_passed_means_the_strategy_did_not_opt_in(monkeypatch):
    """Default None = opt-OUT. A strategy must ASK for this rule, or the shared funnel would silently
    apply MAGNA53's entry discipline to another strategy (THE LINE)."""
    audit, spies = _wire_rule(monkeypatch, mode="on")
    assert asyncio.run(ep.check_flip_up_open_floor(
        "CEG", {"alert_date": CEG["alert_date"]}, _bar(CEG["open"]), None)) == (True, None)
    assert spies.mode == 0 and spies.flip == 0 and spies.prev == 0 and _events(audit) == []


# ── 4. the small-cap paper lane, breakout v1 and 9M never read it — each caller DRIVEN, its kwargs read ──

@pytest.mark.asyncio
async def test_magna53s_orb_pass_hands_the_funnel_the_days_floor(monkeypatch):
    """BEHAVIOUR: drive `live_tracker.process_new_alerts_live` (the #706 harness) with the funnel stubbed
    and read what MAGNA53 actually passes — the detector's own MIN_GAP_PCT, the one floor 4a and 4b share."""
    from tests.test_706_trades_stats_and_skip_dedupe import _Monitor
    m = _Monitor(monkeypatch)
    seen: dict[str, dict] = {}

    async def _capture(*, alert_context, **kw):
        seen[alert_context["ticker"]] = kw
        return {"ticker": alert_context["ticker"], "action": lt.ACTION_SKIPPED, "reason": "setup:test"}

    monkeypatch.setattr(lt, "submit_trade_entry", _capture)
    await m.run({"REGN": {"action": lt.ACTION_SKIPPED, "reason": "setup:test"}})
    kw = seen["REGN"]
    assert kw["signal_type"] == "magna53"
    assert kw["flip_up_open_floor_pct"] == ep_detector.MIN_GAP_PCT
    assert kw["flip_up_open_floor_pct"] == kw["rt_gap_floor_pct"]           # one floor for 4a and 4b
    assert lt._MAGNA53_MIN_GAP_PCT is ep_detector.MIN_GAP_PCT               # not a copied number


@pytest.mark.asyncio
async def test_the_small_cap_paper_lane_hands_the_funnel_no_floor(monkeypatch):
    """BEHAVIOUR (the #624 order-step harness): the lane passes MAGNA53's `rt_gap_floor_pct` but NOT this
    floor — which is exactly why the rule is not keyed on `rt_gap_floor_pct`."""
    from agents.market_intelligence.broker import lowcap_paper_entry as lpe
    from tests.test_624_paper_lane import _wire_order_step
    w = _wire_order_step(monkeypatch)
    out = await lpe.process_lowcap_paper_alerts(today=date(2026, 10, 12))
    assert [r["action"] for r in out] == [ep.ACTION_AUTO_ENTERED]
    kw = w.submit.await_args.kwargs
    assert kw["signal_type"] == "magna53_smallcap"
    assert kw["rt_gap_floor_pct"] == ep_detector.MIN_GAP_PCT
    assert "flip_up_open_floor_pct" not in kw                                 # the funnel's default: never read


@pytest.mark.asyncio
async def test_breakout_v1_hands_the_funnel_no_floor(monkeypatch):
    """BEHAVIOUR (the breakout v1 World): its 09:35 tick names neither floor."""
    from tests.test_breakout_v1_entry import World
    w = World(monkeypatch)
    out = await w.tick()
    assert out["actions"] == {"BRKO": ep.ACTION_AUTO_ENTERED}
    kw = w.funnel.await_args.kwargs
    assert kw["rt_gap_floor_pct"] is None and "flip_up_open_floor_pct" not in kw


def test_no_fourth_caller_of_the_funnel_opts_in():
    """The population of CALLERS is derived by walking agents/, never hand-listed."""
    # source-pin-ok: a behaviour test can only drive the callers it already knows (the three above);
    # this catches a FOURTH caller of the funnel appearing and passing the floor — a population no
    # behaviour test can enumerate. 9M's absence (its Day-2 entry was deleted 2026-08-02) is stated
    # the same way: no caller, so nothing to drive.
    callers = []
    for p in sorted((REPO / "agents").rglob("*.py")):
        text = p.read_text()
        if "submit_trade_entry(" in text and "def submit_trade_entry(" not in text:
            callers.append((p.name, "flip_up_open_floor_pct=" in text))
    names = {n for n, _ in callers}
    assert {"live_tracker.py", "lowcap_paper_entry.py", "breakout_v1_entry.py"} <= names, names
    assert [n for n, passes in callers if passes] == ["live_tracker.py"], callers
    assert not any("9m" in n.lower() or "ninem" in n.lower() for n in names)


def test_the_toggle_name_is_the_one_the_drift_check_and_the_ssot_use():
    assert ep.OPEN_FLOOR_TOGGLE == "magna53_open_below_floor"
    assert ep.OPEN_FLOOR_DEFAULT_MODE == "shadow" and set(ep.OPEN_FLOOR_MODES) == {"shadow", "on", "off"}


def test_live_rules_discovers_the_toggle_and_renders_its_code_default():
    from scripts import live_rules as lr
    assert "magna53_open_below_floor" in lr.discover_runtime_toggles()
    res = lr.Resolver({}, {}, lr.ProdState(reachable=True))
    assert lr._mode_toggle_line(res, "magna53_open_below_floor", "shadow") == \
        "global=shadow [no mi_safeguard_state row — code default]"
    res.prod.toggles = [{"safeguard": "magna53_open_below_floor", "account_mode": "global",
                         "state": "on", "last_transition_at": "2026-11-10 17:00:00+00"}]
    assert lr._mode_toggle_line(res, "magna53_open_below_floor", "shadow") == \
        "global=on [mi_safeguard_state (set 2026-11-10)]"
    assert "magna53_open_below_floor" in "\n".join(lr.build_entry_section(res))


# ── 5. the floor follows the day's MIN_GAP_PCT ───────────────────────────────────────────────────

@pytest.mark.parametrize("floor,expect_below", [(9.0, False), (10.0, True)])
def test_the_floor_is_a_parameter_so_a_changed_min_gap_pct_moves_the_line(monkeypatch, floor, expect_below):
    """prev 100, open 109.5: at/above a 9% floor (109.0), below a 10% floor (110.0). Same bar, same
    flip-up — only the day's floor decides. The call site hands in `ep_detector.MIN_GAP_PCT` (above)."""
    audit, _ = _wire_rule(monkeypatch, mode="on", prev_close=100.0)
    ok, reason = _run(dict(ticker="PCT", alert_date=date(2026, 10, 6), open=109.5), floor=floor)
    assert ok is (not expect_below)
    d = _detail(audit, "magna53_open_floor_checked")
    assert d["floor_pct"] == floor and d["floor_price"] == pytest.approx(100 * (1 + floor / 100))


# ── 6. FAIL OPEN on every non-answer ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("kw", [{"mode_raises": True}, {"flip_raises": True}, {"prev_raises": True}])
def test_fails_open_when_any_read_raises(monkeypatch, kw):
    audit, _ = _wire_rule(monkeypatch, mode="on", **kw)
    assert _run(CEG) == (True, None)
    assert SETUP_OPEN_BELOW_GAP_FLOOR not in " ".join(_events(audit))


def test_the_prev_close_read_carries_the_stage_timeout_and_a_timeout_fails_open(monkeypatch):
    """Simplify review 2026-10-31: the 4a reads are bounded by asyncpg's OWN `timeout=` (#621), never an
    external asyncio.wait_for around a pooled call. The read is handed the stage's bound, and when that bound
    fires (asyncpg raises TimeoutError) the stage fails open: (True, None), nothing skipped, no audit row."""
    audit, spies = _wire_rule(monkeypatch, mode="on")
    seen = []

    async def _times_out(ticker, before_date, timeout=None):
        spies.prev += 1
        seen.append(timeout)
        raise asyncio.TimeoutError

    monkeypatch.setattr("agents.market_intelligence.db.get_prev_close", _times_out)
    ctx = {"ticker": CEG["ticker"], "alert_date": CEG["alert_date"], "gap_pct": 9.4}
    result = asyncio.run(ep.check_flip_up_open_floor(CEG["ticker"], ctx, _bar(CEG["open"]), FLOOR))
    assert result == (True, None)
    assert seen == [ep.OPEN_FLOOR_READ_TIMEOUT_S] and spies.prev == 1 and spies.flip == 1
    assert _events(audit) == []


@pytest.mark.parametrize("bad_prev", [None, 0.0, -5.0])
def test_fails_open_without_a_usable_denominator_and_says_so(monkeypatch, bad_prev):
    audit, _ = _wire_rule(monkeypatch, mode="on", prev_close=bad_prev)
    assert _run(CEG) == (True, None)
    assert _events(audit) == ["magna53_open_floor_unreadable"]


@pytest.mark.parametrize("bar", [None, {}, {"open": None, "high": 1, "low": 1}, {"open": 0.0}, {"open": "n/a"}])
def test_fails_open_without_a_usable_open_and_says_so(monkeypatch, bar):
    audit, _ = _wire_rule(monkeypatch, mode="on")
    assert _run(CEG, bar=bar) == (True, None)
    assert _events(audit) == ["magna53_open_floor_unreadable"]


def test_fails_open_without_an_alert_date(monkeypatch):
    audit, spies = _wire_rule(monkeypatch, mode="on")
    assert _run(CEG, alert={"gap_pct": 9.4}) == (True, None)
    assert spies.flip == 0 and _events(audit) == []


def test_an_iso_string_alert_date_from_the_wire_is_coerced(monkeypatch):
    seen = {}

    async def _flip(ticker, alert_date):
        seen["alert_date"] = alert_date
        return FLIP

    audit, _ = _wire_rule(monkeypatch, mode="shadow")
    monkeypatch.setattr(ep, "find_flip_up_admission", _flip)
    assert _run(CEG, alert={"alert_date": "2026-10-06"}) == (True, None)
    assert seen["alert_date"] == date(2026, 10, 6)


# ── the toggle reader: exactly 'on' / 'off', everything else is 'shadow' ─────────────────────────

@pytest.mark.parametrize("row,expect", [
    ({"state": "on"}, "on"), ({"state": "off"}, "off"), ({"state": "shadow"}, "shadow"),
    ({"state": " ON "}, "on"), ({"state": "active"}, "shadow"), ({"state": None}, "shadow"),
    (None, "shadow"),
])
def test_get_open_floor_mode(monkeypatch, row, expect):
    seen = []

    async def _state(name, mode, timeout=None):
        seen.append((name, mode))
        return row

    monkeypatch.setattr("agents.market_intelligence.db.get_safeguard_state", _state)
    assert asyncio.run(ep.get_open_floor_mode()) == expect
    assert seen == [("magna53_open_below_floor", "global")]


def test_get_open_floor_mode_fails_to_shadow_on_error_and_on_timeout(monkeypatch):
    async def _boom(name, mode, timeout=None):
        raise RuntimeError("db down")
    monkeypatch.setattr("agents.market_intelligence.db.get_safeguard_state", _boom)
    assert asyncio.run(ep.get_open_floor_mode()) == "shadow"

    seen = []

    async def _times_out(name, mode, timeout=None):     # asyncpg's own timeout firing (#621)
        seen.append(timeout)
        raise asyncio.TimeoutError
    monkeypatch.setattr("agents.market_intelligence.db.get_safeguard_state", _times_out)
    assert asyncio.run(ep.get_open_floor_mode()) == "shadow"
    assert seen == [ep.OPEN_FLOOR_READ_TIMEOUT_S]


# ── the population test is the study's SQL, verbatim ──────────────────────────────────────────

def test_find_flip_up_admission_uses_the_studys_join_and_parses_the_detail(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "created_at": "2026-10-06 13:33:03+00",
        "summary": "CEG rt 9.4% ≥9 > delayed 8.8% @ 09:33 ET",
        "detail": json.dumps({"ticker": "CEG", "rt_gap": 9.4, "delayed_gap": 8.8,
                              "tick_et": "09:33", "authoritative": True}),
    })
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    out = asyncio.run(ep.find_flip_up_admission("CEG", date(2026, 10, 6)))
    assert out["tick_et"] == "09:33" and out["rt_gap"] == 9.4 and out["authoritative"] is True
    (sql, ticker, alert_date), = [c.args for c in conn.fetchrow.await_args_list]
    s = " ".join(sql.split())
    assert "event_type = 'ep_rt_floor_flip_up'" in s
    assert "(created_at AT TIME ZONE 'America/New_York')::date = $2" in s      # the ET alert date
    assert "substring(summary from '^([A-Z.]{1,6}) ') = $1" in s              # q3_flipups.sql's own token
    assert "ORDER BY created_at, id LIMIT 1" in s                             # the FIRST flip-up tick
    assert (ticker, alert_date) == ("CEG", date(2026, 10, 6))
    # the study's own SQL carries the same predicates — the definition is reused, not restated
    q3 = (REPO / "scripts/probes/_regn_1030/q3_flipups.sql").read_text()
    assert "event_type = 'ep_rt_floor_flip_up'" in q3 and "substring(summary from '^([A-Z.]{1,6}) ')" in q3


def test_find_flip_up_admission_returns_none_when_not_a_flip_up_and_raises_on_timeout(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(ep, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(ep.find_flip_up_admission("XYZ", date(2026, 10, 6))) is None

    assert conn.fetchrow.await_args.kwargs == {"timeout": ep.OPEN_FLOOR_READ_TIMEOUT_S}   # asyncpg's own bound
    pool.acquire.assert_called_with(timeout=ep.OPEN_FLOOR_READ_TIMEOUT_S)
    conn.fetchrow = AsyncMock(side_effect=asyncio.TimeoutError)        # the bound firing
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(ep.find_flip_up_admission("XYZ", date(2026, 10, 6)))


# ── the whole funnel: the REAL submit_trade_entry over the #461 FakeDB ─────────────────────────

_TODAY = date(2026, 7, 17)     # the #461 harness's day; its bar is open 10.0 / high 10.5 / low 9.8


async def _submit_magna(ticker: str, *, floor: float | None = FLOOR) -> dict:
    return await ep.submit_trade_entry(
        alert_context={"ticker": ticker, "alert_date": _TODAY, "ep_score": 71,
                       "catalyst_quality": "strong", "gap_pct": 9.4},
        spec_builder=_spec_builder, regime_record=None, strategy_label="ORB", signal_type="magna53",
        today=_TODAY, atr_14=1.0, fade_midpoint_ratio=None, rt_gap_floor_pct=FLOOR,
        flip_up_open_floor_pct=floor, aggregate_skips=True,
    )


def _wire_funnel(monkeypatch, *, mode: str, prev_close: float, flip=FLIP):
    """The #461 harness (real funnel, real safeguards, FakeDB) + this rule's three reads pinned.
    prev_close 9.5 → floor 10.355 > the harness's 10.0 open (BELOW); 9.0 → floor 9.81 (clear).
    The 4b live-price re-check is pinned clear so only the new stage can refuse."""
    db = FakeDB()
    sent, audit = _wire(monkeypatch, db)
    _wire_rule(monkeypatch, mode=mode, prev_close=prev_close, flip=flip)
    monkeypatch.setattr(ep, "log_audit_event", audit)        # _wire_rule swapped it; keep ONE recorder
    monkeypatch.setattr(ep, "check_rt_gap_floor", AsyncMock(return_value=(True, None)))
    import agents.market_intelligence.broker.order_manager as om
    return db, sent, audit, om


@pytest.mark.asyncio
async def test_funnel_shadow_enters_and_records(monkeypatch):
    db, sent, audit, om = _wire_funnel(monkeypatch, mode="shadow", prev_close=9.5)
    out = await _submit_magna("CEG")
    assert out["action"] == ep.ACTION_AUTO_ENTERED
    assert om.submit_entry.await_count == 1 and len(db.rows) == 1
    ev = _events(audit)
    assert "magna53_open_below_floor_would_skip" in ev and "orb_open_below_gap_floor" not in ev
    assert lt._insert_skipped_trade.await_count == 0


@pytest.mark.asyncio
async def test_funnel_on_skips_through_the_existing_skip_path(monkeypatch):
    db, sent, audit, om = _wire_funnel(monkeypatch, mode="on", prev_close=9.5)
    out = await _submit_magna("CEG")
    assert out["action"] == ep.ACTION_SKIPPED and out["reason"].startswith(SETUP_OPEN_BELOW_GAP_FLOOR)
    assert om.submit_entry.await_count == 0 and db.rows == []           # no order, no trade row
    # the skip row is written through the funnel's one skip path, with the new reason
    (args, kwargs) = lt._insert_skipped_trade.await_args
    assert args[0] == "CEG" and args[4].startswith(SETUP_OPEN_BELOW_GAP_FLOOR)
    assert kwargs["signal_type"] == "magna53"
    assert "orb_open_below_gap_floor" in _events(audit)
    assert sent == []                                                   # aggregate_skips: the digest pages, not _skip


@pytest.mark.asyncio
async def test_funnel_off_enters_with_no_rows(monkeypatch):
    db, sent, audit, om = _wire_funnel(monkeypatch, mode="off", prev_close=9.5)
    out = await _submit_magna("CEG")
    assert out["action"] == ep.ACTION_AUTO_ENTERED and om.submit_entry.await_count == 1
    assert not any(e.startswith("magna53_open") for e in _events(audit))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["shadow", "on", "off"])
async def test_funnel_open_above_the_floor_enters_in_every_mode(monkeypatch, mode):
    db, sent, audit, om = _wire_funnel(monkeypatch, mode=mode, prev_close=9.0)   # floor 9.81 < open 10.0
    out = await _submit_magna("CRWD")
    assert out["action"] == ep.ACTION_AUTO_ENTERED and om.submit_entry.await_count == 1
    assert "magna53_open_below_floor_would_skip" not in _events(audit)
    assert "orb_open_below_gap_floor" not in _events(audit)


@pytest.mark.asyncio
async def test_funnel_non_flip_up_enters_even_when_on(monkeypatch):
    db, sent, audit, om = _wire_funnel(monkeypatch, mode="on", prev_close=9.5, flip=None)
    out = await _submit_magna("DELAYED")
    assert out["action"] == ep.ACTION_AUTO_ENTERED and om.submit_entry.await_count == 1
    assert not any(e.startswith("magna53_open") for e in _events(audit))


@pytest.mark.asyncio
async def test_funnel_a_caller_that_passes_no_floor_never_reaches_the_rule(monkeypatch):
    """What the small-cap paper lane and breakout v1 hand the funnel (no floor) — the rule is never read,
    even with the toggle 'on' and a flip-up row present."""
    db, sent, audit, om = _wire_funnel(monkeypatch, mode="on", prev_close=9.5)
    out = await _submit_magna("LANE", floor=None)
    assert out["action"] == ep.ACTION_AUTO_ENTERED and om.submit_entry.await_count == 1
    assert not any(e.startswith("magna53_open") for e in _events(audit))


@pytest.mark.asyncio
async def test_funnel_4a_runs_before_4b_so_the_open_rule_names_the_refusal(monkeypatch):
    """A flip-up that opened below the floor AND whose live price retreated: with the toggle 'on' the
    recorded reason is the open rule's (the study's order), not the live-price re-check's."""
    db, sent, audit, om = _wire_funnel(monkeypatch, mode="on", prev_close=9.5)
    monkeypatch.setattr(ep, "check_rt_gap_floor",
                        AsyncMock(return_value=(False, f"{SETUP_GAP_BELOW_FLOOR}: rt 7.0% < 9% floor")))
    out = await _submit_magna("BOTH")
    assert out["reason"].startswith(SETUP_OPEN_BELOW_GAP_FLOOR)
    assert ep.check_rt_gap_floor.await_count == 0


# ── the operator never sees the machine prefix ────────────────────────────────────────────────

def test_humanize_renders_the_new_reason():
    out = humanize(f"{SETUP_OPEN_BELOW_GAP_FLOOR}: 09:30 open $291.11 < floor $291.71")
    assert out.startswith("Opened below the gap floor (") and "setup:" not in out


@pytest.mark.parametrize("call", ["state", "prev"])
def test_the_db_readers_forward_the_bound_to_asyncpg(monkeypatch, call):
    """Advisor, simplify review 2026-10-31: stage 4a hands `timeout=` to `db.get_safeguard_state` and
    `db.get_prev_close`; this pins that both forward it to asyncpg's acquire AND query (#621). WOULD-FAIL-IF
    either `timeout=timeout` were dropped — the pipeline tests above would stay green while the read ran
    unbounded."""
    from agents.market_intelligence import db
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)

    async def _pool():
        return pool
    monkeypatch.setattr(db, "get_pool", _pool)
    if call == "state":
        asyncio.run(db.get_safeguard_state("magna53_open_below_floor", "global", timeout=5.0))
    else:
        asyncio.run(db.get_prev_close("CEG", date(2026, 10, 6), timeout=5.0))
    pool.acquire.assert_called_once_with(timeout=5.0)
    assert conn.fetchrow.await_args.kwargs == {"timeout": 5.0}
