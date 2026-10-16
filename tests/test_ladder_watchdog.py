"""ADR 0022 L2 — the ladder demotion watchdog, built DARK (#312, 2026-10-15).

ADR §6's L2 plan reads "synthetic breach → demotion + alert + history row; no-breach → zero
writes". Adapted to the dark build the operator asked for (2026-10-12: "ships dark; any live
flip is his sign-off"), the bar is:

  * a synthetic breach of EACH trigger → `would_demote: true` (the pure evaluator, one test per
    trigger), and a synthetic STREAK breach through the real run → `would_demote: true` IN THE
    AUDIT ROW with the spied DB layer seeing exactly one write — the audit INSERT — never
    `mi_strategies`, never an order or sizing path, never a Telegram;
  * no breach → `would_demote: false`, still one row (the row existing is the liveness proof);
  * too few trades → "not enough data" on every trigger, never a breach.

The orchestrator tests run the REAL `run_ladder_watchdog` over `tests.conftest.make_mock_pool`
(the same harness the kill/scale band tests use), so the query wiring, the account-mode threading
and the audit write are exercised, not re-described. The mock DB interprets ONLY the clauses
the watchdog's own SQL declares — its ORDER BY, the as-of bound and the "tonight's row exists"
lookup — so a change to that SQL changes what the run sees (there is no Postgres in the test
environment to execute it). The one source scan at the bottom checks the NON-existence of an act
step, which no call can exercise — it carries the reviewed escape.
"""
from __future__ import annotations

import ast
import asyncio
import datetime as dt
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.db as dbmod
from agents.market_intelligence import ladder_watchdog as lw
from agents.market_intelligence.strategies import registry
from agents.market_intelligence.strategies.registry import Strategy
from tests._audit_emitters import TELEGRAM_SENDERS

_TODAY = dt.date(2026, 10, 15)


def _rs(value, n):
    return [value] * n


# ─── 1. The pure evaluator — one breach per trigger, all clear, too few ────────────────────


def test_six_consecutive_losses_breaches_only_that_trigger():
    v = lw.evaluate_demotion_triggers(_rs(2.0, 20) + _rs(-1.0, 6))
    assert v["triggers"]["consec_losses"]["value"] == 6
    assert v["triggers"]["consec_losses"]["breached"] is True
    assert v["triggers"]["trailing20_expectancy_r"]["breached"] is False   # (14×2 − 6)/20 = +1.1R
    assert v["triggers"]["dd_from_peak_r"]["breached"] is False            # −6R from peak
    assert v["would_demote"] is True
    assert v["reasons"] == ["consec_losses 6 vs 6"]


def test_five_consecutive_losses_is_not_a_breach():
    v = lw.evaluate_demotion_triggers(_rs(2.0, 20) + _rs(-1.0, 5))
    assert v["triggers"]["consec_losses"]["value"] == 5
    assert v["would_demote"] is False


def test_breakeven_counts_as_a_loss_in_the_streak():
    """Same convention as the #268 calibration's worst-streak (kill_scale_bands)."""
    v = lw.evaluate_demotion_triggers(_rs(2.0, 20) + [0.0, -0.5, 0.0, -0.2, 0.0, -0.1])
    assert v["triggers"]["consec_losses"]["value"] == 6
    assert v["triggers"]["consec_losses"]["breached"] is True


def test_trailing20_below_minus_0_3r_breaches_only_that_trigger():
    # alternating −0.8 / +0.1 → mean −0.35R < −0.3R; streak 1; drawdown −7R (above −10R)
    series = [-0.8, 0.1] * 10
    v = lw.evaluate_demotion_triggers(_rs(3.0, 5) + series)
    t = v["triggers"]["trailing20_expectancy_r"]
    assert t["value"] == pytest.approx(-0.35)
    assert t["breached"] is True
    assert v["triggers"]["consec_losses"]["breached"] is False
    assert v["triggers"]["dd_from_peak_r"]["breached"] is False
    assert v["would_demote"] is True


def test_trailing20_above_minus_0_3r_is_not_a_breach():
    """Mean −0.25R over the window (a losing stretch, but above the signed bar) stays clear."""
    v = lw.evaluate_demotion_triggers(_rs(3.0, 5) + [-0.6, 0.1] * 10)
    assert v["triggers"]["trailing20_expectancy_r"]["value"] == pytest.approx(-0.25)
    assert v["triggers"]["trailing20_expectancy_r"]["breached"] is False
    assert v["would_demote"] is False


def test_trailing20_exactly_at_the_threshold_is_not_a_breach():
    """The trigger is STRICT (`<`): a mean sitting exactly ON the line is not below it. Pinned
    through the `thresholds` override with a value that is exact in binary — the signed -0.3 is
    not, so no real series can land on it — so a `<=` regression is caught here. [-0.5, 0.0]*10
    averages exactly -0.25. (Only this trigger is asserted: under this module's convention a
    breakeven 0.0 is a loss, so the streak breaches on this series and `would_demote` is True.)"""
    series = [-0.5, 0.0] * 10
    at_line = lw.evaluate_demotion_triggers(series, thresholds={"trailing20_expectancy_r": -0.25})
    t = at_line["triggers"]["trailing20_expectancy_r"]
    assert t["value"] == -0.25 and t["threshold"] == -0.25
    assert t["breached"] is False
    just_above = lw.evaluate_demotion_triggers(
        series, thresholds={"trailing20_expectancy_r": -0.2})
    assert just_above["triggers"]["trailing20_expectancy_r"]["breached"] is True


def test_drawdown_10r_from_peak_breaches_only_that_trigger():
    """A slow bleed: 40 trades alternating −1.0 / +0.5 after a +20R peak reaches exactly −10R
    below it while the streak never passes 1 and the last-20 mean is −0.25R (above −0.3R) —
    so the drawdown trigger is the ONLY one that fires. 0.5-multiples are exact in binary."""
    v = lw.evaluate_demotion_triggers(_rs(2.0, 10) + [-1.0, 0.5] * 20)
    dd = v["triggers"]["dd_from_peak_r"]
    assert dd["value"] == -10.0
    assert v["max_dd_r"] == -10.5     # the trough one trade earlier, before the final +0.5
    assert dd["breached"] is True
    assert v["triggers"]["consec_losses"]["value"] == 0
    assert v["triggers"]["consec_losses"]["breached"] is False
    assert v["triggers"]["trailing20_expectancy_r"]["value"] == pytest.approx(-0.25)
    assert v["triggers"]["trailing20_expectancy_r"]["breached"] is False
    assert v["would_demote"] is True
    assert v["reasons"] == ["dd_from_peak_r -10.0 vs -10.0"]


def test_drawdown_9_5r_from_peak_is_not_a_breach():
    v = lw.evaluate_demotion_triggers(_rs(2.0, 10) + [-1.0, 0.5] * 19)   # −9.5R below the peak
    assert v["triggers"]["dd_from_peak_r"]["value"] == -9.5
    assert v["would_demote"] is False


def test_drawdown_trigger_is_the_current_drawdown_not_the_worst_ever():
    """A −10R hole that has since been climbed out of is NOT a breach now (the trigger reads
    the state, like the drawdown breaker); the worst value still rides in the row."""
    hole = _rs(-1.0, 5) + [0.5] + _rs(-1.0, 5) + [0.5] + [-1.0]   # −10R from the peak, streak ≤ 5
    recovery = _rs(1.0, 12)
    v = lw.evaluate_demotion_triggers(_rs(2.0, 10) + hole + recovery)
    assert v["max_dd_r"] == -10.0
    assert v["triggers"]["dd_from_peak_r"]["value"] == 0.0
    assert v["triggers"]["dd_from_peak_r"]["breached"] is False
    assert v["would_demote"] is False


def test_no_breach_is_not_a_demotion():
    v = lw.evaluate_demotion_triggers([1.5, -1.0, 2.0, -1.0, -1.0, 3.0] * 5)
    assert all(t["breached"] is False for t in v["triggers"].values())
    assert v["would_demote"] is False
    assert v["reasons"] == []
    assert v["n_closed"] == 30


def test_too_few_trades_is_not_enough_data_never_a_breach():
    """Five straight losses on a five-trade book: below the 6-trade floor every R trigger says
    'not enough data' (a floor-less streak read would already show 5 of 6)."""
    v = lw.evaluate_demotion_triggers(_rs(-1.0, 5))
    for name in lw.R_TRIGGERS:
        t = v["triggers"][name]
        assert t["value"] is None and t["breached"] is False
        assert t["status"].startswith("not enough data")
    assert v["would_demote"] is False


def test_trailing20_needs_its_own_window_even_above_the_floor():
    v = lw.evaluate_demotion_triggers(_rs(-1.0, 10))   # 10 trades: streak evaluates, t20 cannot
    assert v["triggers"]["consec_losses"]["breached"] is True
    t20 = v["triggers"]["trailing20_expectancy_r"]
    assert t20["value"] is None and t20["breached"] is False
    assert "< 20 window" in t20["status"]


def test_harmful_auto_action_is_recorded_not_measurable_never_breached():
    v = lw.evaluate_demotion_triggers(_rs(-1.0, 30))
    h = v["triggers"]["harmful_auto_action"]
    assert h["breached"] is False and h["value"] is None
    assert h["status"].startswith("not measurable yet")
    assert h["threshold"] == 1


def test_signed_m1f_thresholds_are_the_defaults():
    """ADR 0022 §7 M1f, operator-signed 2026-07-05 — the numbers the row is judged against."""
    assert lw.M1F_DEMOTION_TRIGGERS == {
        "consec_losses": 6, "trailing20_expectancy_r": -0.3,
        "dd_from_peak_r": -10.0, "harmful_auto_action": 1}


def test_would_demote_to_matches_the_operators_manual_demote_map():
    """The dark row may never name a rung the real `/strategy <id> demote` would not step to."""
    from agents.market_intelligence.strategies import telegram as st
    assert lw.DEMOTE_TO == st._DEMOTE_BACK
    assert "shadow" not in lw.DEMOTE_TO and "deprecated" not in lw.DEMOTE_TO


# ─── 2. The nightly pass over a spied DB layer ─────────────────────────────────────────────


def _strategy(sid, phase, enabled=True, live_real=False):
    return Strategy(strategy_id=sid, name=sid, family="orb_long", phase=phase, enabled=enabled,
                    signal_type=sid, outcomes_table="mi_live_trades",
                    promotion_model="unpaired_r", promotion_thresholds={},
                    live_real_enabled=live_real)


def _one_row(r, *, id, alert_date, closed_on_et="same-day", exit_rule=None):
    """One closed row with realised R = `r` at an explicit id / entry date / close date.
    Uncapped: entry_shares=1, entry 101, hard_stop 1 → risk_placed = 100, so total_pnl = 100·R
    reproduces the R series exactly (the #586 fixture shape). `closed_on_et` (the ET date of
    `closed_at`) is NOT selected by the watchdog, only read by the mock DB's as-of bound; the
    default is a same-day close, `None` is a legacy row with no `closed_at`."""
    return {"id": id, "total_pnl": 100.0 * r, "risk_dollars_actual": None, "entry_shares": 1.0,
            "entry_price": 101.0, "hard_stop": 1.0, "alert_date": alert_date,
            "closed_on_et": alert_date if closed_on_et == "same-day" else closed_on_et,
            "signal_type": "magna53", "exit_rule": exit_rule}


def _closed_rows(rs, *, exit_rule=None, first_id=1):
    """A series of same-day-close rows (`_one_row`); `id` ascends with `alert_date`."""
    base = dt.date(2026, 7, 1)
    return [_one_row(r, id=first_id + i, alert_date=base + dt.timedelta(days=i),
                     exit_rule=exit_rule) for i, r in enumerate(rs)]


def _order_key(cols):
    return lambda row: tuple(row[c] for c in cols)


class _Spy:
    """Every statement the watchdog sent to the DB, by verb, plus the senders it must never
    reach. Wires `db.get_pool` (used by both the watchdog's read and `log_audit_event`) so the
    REAL audit write is observed, not mocked away.

    There is no Postgres in the test environment, so the mock DB INTERPRETS the clauses the
    watchdog's SQL declares — and only those: the trade read's ORDER BY, its `alert_date <= $3`
    and `COALESCE(<closed_at ET date>, alert_date) <= $3` bounds, and the "tonight's row exists"
    lookup over the audit rows it has seen (pre-seeded via `prior_audit` and appended to by every
    audit INSERT). Stored rows are served REVERSED, so a read with no ORDER BY — or the wrong one
    — hands the evaluator a different series. Edit the SQL and the mock follows what it says."""

    def __init__(self, monkeypatch, strategies, rows_by_key, prior_audit=()):
        from tests.conftest import make_mock_pool
        self.calls: list[tuple[str, str, tuple]] = []
        self.audit_seen: list[tuple[str, str]] = list(prior_audit)   # (event_type, summary)
        pool, conn = make_mock_pool()

        async def fetch(sql, *args, **kw):
            self.calls.append(("fetch", sql, args))
            rows = list(reversed(rows_by_key.get(tuple(args[:2]), [])))
            as_of = args[2] if len(args) > 2 else None
            if "alert_date <= $3" in sql:
                rows = [r for r in rows if r["alert_date"] <= as_of]
            if "COALESCE((closed_at AT TIME ZONE 'America/New_York')::date, alert_date) <= $3" in sql:
                rows = [r for r in rows if (r.get("closed_on_et") or r["alert_date"]) <= as_of]
            if "ORDER BY" in sql:
                cols = [c.split()[0] for c in sql.split("ORDER BY", 1)[1].split(",")]
                rows = sorted(rows, key=_order_key(cols))
            return rows

        async def fetchval(sql, *args, **kw):
            self.calls.append(("fetchval", sql, args))
            assert sql == lw._NIGHT_ROW_EXISTS_SQL, f"unexpected fetchval: {sql}"
            event_type, pattern = args
            assert pattern.endswith("%") and "%" not in pattern[:-1] and "_" not in pattern
            return 1 if any(e == event_type and m.startswith(pattern[:-1])
                            for e, m in self.audit_seen) else None

        async def execute(sql, *args, **kw):
            self.calls.append(("execute", sql, args))
            if sql == dbmod._AUDIT_INSERT_SQL:
                self.audit_seen.append((args[0], args[1]))
            return "INSERT 0 1"

        conn.fetch = fetch
        conn.fetchval = fetchval
        conn.execute = execute
        conn.fetchrow = AsyncMock(side_effect=AssertionError("unexpected fetchrow"))
        conn.executemany = AsyncMock(side_effect=AssertionError("unexpected executemany"))
        monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
        # The watchdog reads the rows FRESH (`registry._load_all`, a plain SELECT), never the
        # process cache — a hand-UPDATE of a phase the same day must land in tonight's row.
        monkeypatch.setattr(registry, "_load_all",
                            AsyncMock(return_value={s.strategy_id: s for s in strategies}))
        monkeypatch.setattr(registry, "load_strategies",
                            AsyncMock(side_effect=AssertionError(
                                "the watchdog must read the registry fresh, not the cache")))

        # The act step must not exist: if anything in the pass reaches a phase writer, a sizing
        # knob or a Telegram sender, the test fails loudly rather than recording a "write".
        async def _forbidden(*a, **k):
            raise AssertionError(f"DARK watchdog reached a forbidden path: {a} {k}")

        monkeypatch.setattr(registry, "update_strategy", _forbidden)
        from agents.market_intelligence import briefing
        from core import notifications
        monkeypatch.setattr(briefing, "send_telegram_message", _forbidden)
        monkeypatch.setattr(notifications, "notify_owner", _forbidden)
        monkeypatch.setattr(notifications, "notify_job_failure", _forbidden)

    @property
    def writes(self):
        return [c for c in self.calls if c[0] in ("execute", "executemany")]

    @property
    def audit_rows(self):
        return [c for c in self.writes if c[1] == dbmod._AUDIT_INSERT_SQL]


def _run(today=_TODAY):
    return asyncio.run(lw.run_ladder_watchdog(today=today))


def _row_detail(spy, event=lw.AUDIT_EVENT):
    rows = [c for c in spy.audit_rows if c[2][0] == event]
    assert len(rows) == 1, f"expected exactly one {event} row, got {len(rows)}"
    return rows[0][2][1], json.loads(rows[0][2][2])


def test_breach_writes_would_demote_true_and_touches_nothing_else(monkeypatch):
    """ADR §6 L2, dark: synthetic breach → the row says would_demote, and the DB layer saw ONE
    write — the audit INSERT. No UPDATE, no mi_strategies, no order/sizing table, no Telegram."""
    strategies = [_strategy("magna53", "live", live_real=True),
                  _strategy("magna53_smallcap", "paper")]
    spy = _Spy(monkeypatch, strategies, {
        ("magna53", "live"): _closed_rows(_rs(2.0, 20) + _rs(-1.0, 6)),   # 6-streak breach
        ("magna53_smallcap", "paper"): _closed_rows([1.0, -1.0, 2.0, -0.5, 1.5, -1.0]),
    })
    detail = _run()

    summary, row = _row_detail(spy)
    assert row == json.loads(json.dumps(detail, default=str))
    by_id = {e["strategy_id"]: e for e in row["evaluated"]}
    assert by_id["magna53"]["would_demote"] is True
    assert by_id["magna53"]["would_demote_to"] == "paper"
    assert by_id["magna53"]["triggers"]["consec_losses"] == {
        "value": 6, "threshold": 6, "breached": True, "status": "evaluated"}
    assert by_id["magna53_smallcap"]["would_demote"] is False
    assert row["would_demote_count"] == 1 and row["acted"] is False and row["mode"] == "dark"
    assert "1 would demote" in summary and "acted: none" in summary

    # ZERO writes anywhere but the audit log.
    assert len(spy.writes) == 1 and spy.writes[0][1] == dbmod._AUDIT_INSERT_SQL
    for verb, sql, _ in spy.calls:
        up = sql.upper()
        assert "UPDATE" not in up and "MI_STRATEGIES" not in up and "DELETE" not in up, (verb, sql)
        assert "ORDER" not in up.replace("ORDER BY", "") and "POSITION_SIZE" not in up


def test_each_strategy_is_read_on_its_own_book(monkeypatch):
    """Dual-account invariant 3: the read for a live strategy carries ('<signal_type>', 'live'),
    the paper lane's carries 'paper' — never the other book, never unfiltered."""
    strategies = [_strategy("magna53", "live", live_real=True),
                  _strategy("magna53_smallcap", "paper")]
    spy = _Spy(monkeypatch, strategies, {})
    _run()
    reads = [c[2] for c in spy.calls if c[0] == "fetch"]
    assert sorted(r[:2] for r in reads) == [("magna53", "live"), ("magna53_smallcap", "paper")]
    assert all(r[2] == _TODAY for r in reads)   # the night being scored rides as $3
    for _, sql, _ in [c for c in spy.calls if c[0] == "fetch"]:
        assert "account_mode = $2" in sql and "pnl_attribution IS NULL" in sql
        assert "status = 'closed'" in sql


def test_no_breach_still_writes_one_row_with_would_demote_false(monkeypatch):
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)], {
        ("magna53", "live"): _closed_rows([1.5, -1.0, 2.0, -1.0, -1.0, 3.0] * 5)})
    _run()
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["would_demote"] is False and e["reasons"] == [] and e["n_closed"] == 30
    assert row["would_demote_count"] == 0
    assert len(spy.writes) == 1


def test_too_few_trades_reads_not_enough_data_in_the_row(monkeypatch):
    spy = _Spy(monkeypatch, [_strategy("magna53_smallcap", "paper")], {
        ("magna53_smallcap", "paper"): _closed_rows(_rs(-1.0, 3))})
    _run()
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["n_closed"] == 3 and e["would_demote"] is False
    for name in lw.R_TRIGGERS:
        assert e["triggers"][name]["status"] == "not enough data (3 closed < 6)"
    assert e["triggers"]["harmful_auto_action"]["status"].startswith("not measurable yet")


def test_shadow_deprecated_and_disabled_are_skipped_with_a_reason(monkeypatch):
    strategies = [_strategy("magna53", "live", live_real=True),
                  _strategy("shadow_orb_5m", "shadow"),
                  _strategy("9m_day2", "deprecated", enabled=False),
                  _strategy("paused_lane", "paper", enabled=False)]
    spy = _Spy(monkeypatch, strategies, {})
    _run()
    _, row = _row_detail(spy)
    assert [e["strategy_id"] for e in row["evaluated"]] == ["magna53"]
    assert set(row["skipped"]) == {"shadow_orb_5m", "9m_day2", "paused_lane"}
    assert "no rung below" in row["skipped"]["shadow_orb_5m"]
    assert "no rung below" in row["skipped"]["9m_day2"]
    assert row["skipped"]["paused_lane"].startswith("disabled")
    # only the evaluated strategy was read
    assert [c[2][:2] for c in spy.calls if c[0] == "fetch"] == [("magna53", "live")]


def test_rows_without_an_r_frame_are_excluded_and_counted(monkeypatch):
    rows = _closed_rows(_rs(-1.0, 6))
    rows[0] = {**rows[0], "hard_stop": None, "risk_dollars_actual": None}   # no R frame
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): rows})
    _run()
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["n_closed"] == 5 and e["rows_without_r_frame"] == 1
    assert e["would_demote"] is False   # 5 < floor — the excluded row is not a 6th loss


def test_era_split_rides_in_the_row_as_report_only(monkeypatch):
    """#662: the row says which rules its trades ran under; a depth-stamped row (era E) is
    labelled from its own `exit_rule`, not the date. Verdict unchanged by the split."""
    old = _closed_rows(_rs(-1.0, 6))                       # 2026-07 alert dates → era A
    new = _closed_rows([2.0, 2.0], exit_rule="depth", first_id=100)   # row-stamped era E
    for r in new:
        r["alert_date"] = r["closed_on_et"] = dt.date(2026, 10, 14)
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): old + new})
    _run()
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["by_era"].get("era_e") == 2 and e["by_era"].get("era_a") == 6
    assert "older rules: 6 trades" in e["era"]
    assert e["would_demote"] is False   # streak broken by the two winners; pooled verdict


def test_a_crash_propagates_out_of_the_run_and_writes_no_row_of_its_own(monkeypatch):
    """A dead watchdog must not look like a quiet one: the crash leaves `run_ladder_watchdog`
    (so `audit_wrap` records 'failed', writes `job_failed_error` and pages once — pinned
    through the real job below) and the run itself writes nothing."""
    spy = _Spy(monkeypatch, [], {})
    monkeypatch.setattr(registry, "_load_all",
                        AsyncMock(side_effect=RuntimeError("registry unreachable")))
    with pytest.raises(RuntimeError, match="registry unreachable"):
        _run()
    assert spy.writes == []


def test_the_series_is_in_alert_date_order_not_insertion_order(monkeypatch):
    """The streak, the trailing-20 mean and the drawdown all depend on ORDER. A row backfilled
    late (high id) with an EARLY alert_date belongs at the START of the series: in alert_date
    order the book ends on six straight losses (breach); read in id order the backfilled winner
    would land last and the streak would read 0. The mock DB serves rows reversed and applies
    the SQL's own ORDER BY, so `ORDER BY id` (or none) fails this."""
    rows = _closed_rows(_rs(2.0, 20) + _rs(-1.0, 6))                     # ids 1-26, dates 07-01..07-26
    rows.append(_one_row(2.0, id=999, alert_date=dt.date(2026, 6, 30)))  # backfilled: early date, last id
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): rows})
    _run()
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["n_closed"] == 27
    assert e["triggers"]["consec_losses"]["value"] == 6
    assert e["triggers"]["consec_losses"]["breached"] is True


def test_same_day_entries_are_ordered_by_id(monkeypatch):
    """Two trades with the SAME alert_date: `id ASC` is the tie-break. The winner has the lower
    id, so the book ends on the loss (streak 1); without the tie-break the mock's reversed
    storage order would put the winner last (streak 0)."""
    last_day = dt.date(2026, 8, 1)
    rows = _closed_rows(_rs(2.0, 10) + _rs(-1.0, 5))
    rows += [_one_row(2.0, id=100, alert_date=last_day), _one_row(-1.0, id=101, alert_date=last_day)]
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): rows})
    _run()
    _, row = _row_detail(spy)
    assert row["evaluated"][0]["triggers"]["consec_losses"]["value"] == 1


def test_a_rerun_scores_only_what_that_night_could_have_seen(monkeypatch):
    """A re-run of night D (manual, or a #672 recovery that pins `et_today()` to D) must not
    score the future: a trade ENTERED after D, and a trade entered on/before D that CLOSED after
    D, are both excluded — and a legacy closed row with no `closed_at` is still counted (the
    COALESCE falls back to its entry date). Unbounded, the two later winners would end the book
    and break the six-loss streak."""
    past = _closed_rows(_rs(2.0, 20) + _rs(-1.0, 6))
    past[-1] = {**past[-1], "closed_on_et": None}                  # legacy row: no closed_at
    entered_after = _one_row(2.0, id=500, alert_date=_TODAY + dt.timedelta(days=1))
    closed_after = _one_row(2.0, id=501, alert_date=_TODAY - dt.timedelta(days=1),
                            closed_on_et=_TODAY + dt.timedelta(days=1))   # multi-day hold
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): past + [entered_after, closed_after]})
    _run()
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["n_closed"] == 26
    assert e["triggers"]["consec_losses"]["value"] == 6 and e["would_demote"] is True


def test_the_trade_read_carries_both_as_of_bounds(monkeypatch):
    """The SQL itself names both bounds on the night being scored ($3)."""
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)], {})
    _run()
    (_, sql, args), = [c for c in spy.calls if c[0] == "fetch"]
    assert "alert_date <= $3" in sql
    assert "COALESCE((closed_at AT TIME ZONE 'America/New_York')::date, alert_date) <= $3" in sql
    assert args == ("magna53", "live", _TODAY)


def test_a_rerun_of_the_same_night_writes_no_second_row(monkeypatch):
    """ONE row per night. A manual re-run, or a #672 recovery re-run after a run whose row landed
    but whose ledger entry did not, must not stack a second `ladder_demotion_shadow` row for the
    same as_of (the first row stands; the returned dict says so)."""
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)], {
        ("magna53", "live"): _closed_rows(_rs(2.0, 20) + _rs(-1.0, 6))})
    first = _run()
    second = _run()
    assert "row_already_written" not in first
    assert second["row_already_written"] is True
    assert second["would_demote_count"] == first["would_demote_count"] == 1   # still evaluated
    assert len(spy.audit_rows) == 1 and len(spy.writes) == 1


def test_an_existing_row_for_another_night_does_not_suppress_tonights(monkeypatch):
    """The existence key is the night AND the event type: yesterday's row (here pre-seeded) and
    the same night's row of another event type do not stop tonight's `ladder_demotion_shadow`."""
    yesterday = _TODAY - dt.timedelta(days=1)
    prior = [(lw.AUDIT_EVENT, lw._summary(yesterday, [])),
             ("some_other_event", lw._summary(_TODAY, []))]
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)], {}, prior_audit=prior)
    detail = _run()
    assert "row_already_written" not in detail
    summary, row = _row_detail(spy)
    assert row["as_of"] == _TODAY.isoformat() and _TODAY.isoformat() in summary
    # …and the next evening writes its own row again
    _run(today=_TODAY + dt.timedelta(days=1))
    assert len(spy.audit_rows) == 2


# ─── 2b. The scheduler job: a crash must reach the run ledger, not be swallowed ────────────


def test_a_crash_in_the_job_reaches_the_ledger_as_failed_and_pages_once(monkeypatch):
    """`_ladder_watchdog_job` used to catch the crash and call `notify_job_failure` itself, so
    `audit_wrap` saw a clean return: `mi_job_runs` said 'success', the durable deduped
    `record_job_failure` never ran, and #672 recovery had nothing to re-run. Run through the
    REAL `audit_wrap` the way `start_scheduler` registers it: the exception must propagate, the
    ledger must read 'failed', and the one page + durable row must come from `audit_run`."""
    from agents.market_intelligence import scheduler as sched
    from core import job_audit
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"id": 42})       # _record_start -> run id
    conn.execute = AsyncMock(return_value="UPDATE 1")        # _record_finish
    audit = AsyncMock()
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(dbmod, "log_audit_event", audit)
    monkeypatch.setattr(dbmod, "get_audit_log", AsyncMock(return_value=[]))   # dedup lookback
    monkeypatch.setattr(job_audit, "notify_job_failure", AsyncMock())         # the ONE page
    monkeypatch.setattr(job_audit, "_last_job_failure_alert_ts", {})
    direct = AsyncMock()                                     # the scheduler's own bound name
    monkeypatch.setattr(sched, "notify_job_failure", direct)
    monkeypatch.setattr(lw, "run_ladder_watchdog",
                        AsyncMock(side_effect=RuntimeError("registry unreachable")))

    wrapped = job_audit.audit_wrap(sched._ladder_watchdog_job, lw.JOB_ID)
    with pytest.raises(RuntimeError, match="registry unreachable"):
        asyncio.run(wrapped())

    conn.execute.assert_awaited_once()                       # the ledger UPDATE…
    assert conn.execute.await_args.args[3] == "failed"       # …status, not 'success'
    assert audit.await_args.args[0] == "job_failed_error"    # durable row from record_job_failure
    assert f"job={lw.JOB_ID} " in audit.await_args.args[1]
    job_audit.notify_job_failure.assert_awaited_once()       # exactly one page
    direct.assert_not_awaited()                              # none from a handler in the job


# ─── 3. Registration: the job exists, is INTELLIGENCE-owned, and fires after the close ─────


def test_ladder_watchdog_is_registered_intelligence_owned_after_the_close(monkeypatch):
    from agents.market_intelligence import scheduler as sched
    from tests.test_672_missed_job_recovery import _real_job_list
    _, registered = _real_job_list(monkeypatch)   # what start_scheduler ACTUALLY registers
    jobs = {j.id: j for j in registered}
    assert lw.JOB_ID in jobs, "ladder_watchdog is not registered by start_scheduler"
    trig = str(jobs[lw.JOB_ID].trigger)
    assert "hour='16'" in trig and "minute='17'" in trig and "mon-fri" in trig, trig
    assert lw.JOB_ID in sched.INTELLIGENCE_OWNED_JOB_IDS   # (disjointness: test_job_partition)
    assert jobs[lw.JOB_ID].misfire_grace_time == 600


# ─── 4. The act step does not exist — a structural check, not a flag ───────────────────────


def test_the_module_has_no_phase_sizing_order_or_telegram_path():
    # source-pin-ok: the NON-existence of an act step cannot be exercised by calling anything;
    # the runtime tests above prove no write happened on a breach, this proves there is no code
    # path that could — no "live mode" flag a typo could flip.
    src = Path(lw.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                for a in n.names}
    forbidden = TELEGRAM_SENDERS | {
        "update_strategy", "submit_trade_entry", "place_stop_order", "replace_order",
        "claim_safeguard_state_transition", "set_safeguard_state"}
    assert not forbidden & (names | attrs | imported), forbidden & (names | attrs | imported)
    # Every string the module can hand to the DB — docstrings (which DESCRIBE the forbidden
    # paths) excluded by identity, not by content.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
               and isinstance(n.value, str) and id(n) not in docstrings]
    sql_like = [s for s in strings if "mi_strategies" in s.lower()
                or ("update " in s.lower() and " set " in s.lower())]
    assert not sql_like, sql_like
    body = src.split('"""', 2)[2]   # after the module docstring
    assert "position_size_multiplier" not in body and "live_mode" not in body.lower()
