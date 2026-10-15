"""ADR 0022 L2 — the ladder demotion watchdog, built DARK (#312, 2026-10-15).

ADR §6's L2 plan reads "synthetic breach → demotion + alert + history row; no-breach → zero
writes". Adapted to the dark build the operator asked for (2026-10-12: "ships dark; any live
flip is his sign-off"), the bar is:

  * a synthetic breach of EACH trigger → `would_demote: true` IN THE AUDIT ROW, and the spied DB
    layer saw exactly one write — the audit INSERT — never `mi_strategies`, never an order or
    sizing path, never a Telegram;
  * no breach → `would_demote: false`, still one row (the row existing is the liveness proof);
  * too few trades → "not enough data" on every trigger, never a breach.

The orchestrator tests run the REAL `run_ladder_watchdog` over `tests.conftest.make_mock_pool`
(the same harness the kill/scale band tests use), so the query wiring, the account-mode threading
and the audit write are exercised, not re-described. The one source scan at the bottom checks
the NON-existence of an act step, which no call can exercise — it carries the reviewed escape.
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


def _closed_rows(rs, *, exit_rule=None):
    """Uncapped rows: entry_shares=1, entry 101, hard_stop 1 → risk_placed = 100, so total_pnl
    = 100·R reproduces the R series exactly (the #586 fixture shape)."""
    base = dt.date(2026, 7, 1)
    return [{"total_pnl": 100.0 * r, "risk_dollars_actual": None, "entry_shares": 1.0,
             "entry_price": 101.0, "hard_stop": 1.0,
             "alert_date": base + dt.timedelta(days=i), "signal_type": "magna53",
             "exit_rule": exit_rule} for i, r in enumerate(rs)]


class _Spy:
    """Every statement the watchdog sent to the DB, by verb, plus the senders it must never
    reach. Wires `db.get_pool` (used by both the watchdog's read and `log_audit_event`) so the
    REAL audit write is observed, not mocked away."""

    def __init__(self, monkeypatch, strategies, rows_by_key):
        from tests.conftest import make_mock_pool
        self.calls: list[tuple[str, str, tuple]] = []
        pool, conn = make_mock_pool()

        async def fetch(sql, *args, **kw):
            self.calls.append(("fetch", sql, args))
            return rows_by_key.get(tuple(args), [])

        async def execute(sql, *args, **kw):
            self.calls.append(("execute", sql, args))
            return "INSERT 0 1"

        conn.fetch = fetch
        conn.execute = execute
        conn.fetchrow = AsyncMock(side_effect=AssertionError("unexpected fetchrow"))
        conn.fetchval = AsyncMock(side_effect=AssertionError("unexpected fetchval"))
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


def _run(spy):
    return asyncio.run(lw.run_ladder_watchdog(today=_TODAY))


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
    detail = _run(spy)

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
    _run(spy)
    reads = [c[2] for c in spy.calls if c[0] == "fetch"]
    assert sorted(reads) == [("magna53", "live"), ("magna53_smallcap", "paper")]
    for _, sql, _ in [c for c in spy.calls if c[0] == "fetch"]:
        assert "account_mode = $2" in sql and "pnl_attribution IS NULL" in sql
        assert "status = 'closed'" in sql


def test_no_breach_still_writes_one_row_with_would_demote_false(monkeypatch):
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)], {
        ("magna53", "live"): _closed_rows([1.5, -1.0, 2.0, -1.0, -1.0, 3.0] * 5)})
    _run(spy)
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["would_demote"] is False and e["reasons"] == [] and e["n_closed"] == 30
    assert row["would_demote_count"] == 0
    assert len(spy.writes) == 1


def test_too_few_trades_reads_not_enough_data_in_the_row(monkeypatch):
    spy = _Spy(monkeypatch, [_strategy("magna53_smallcap", "paper")], {
        ("magna53_smallcap", "paper"): _closed_rows(_rs(-1.0, 3))})
    _run(spy)
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
    _run(spy)
    _, row = _row_detail(spy)
    assert [e["strategy_id"] for e in row["evaluated"]] == ["magna53"]
    assert set(row["skipped"]) == {"shadow_orb_5m", "9m_day2", "paused_lane"}
    assert "no rung below" in row["skipped"]["shadow_orb_5m"]
    assert "no rung below" in row["skipped"]["9m_day2"]
    assert row["skipped"]["paused_lane"].startswith("disabled")
    # only the evaluated strategy was read
    assert [c[2] for c in spy.calls if c[0] == "fetch"] == [("magna53", "live")]


def test_rows_without_an_r_frame_are_excluded_and_counted(monkeypatch):
    rows = _closed_rows(_rs(-1.0, 6))
    rows[0] = {**rows[0], "hard_stop": None, "risk_dollars_actual": None}   # no R frame
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): rows})
    _run(spy)
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["n_closed"] == 5 and e["rows_without_r_frame"] == 1
    assert e["would_demote"] is False   # 5 < floor — the excluded row is not a 6th loss


def test_era_split_rides_in_the_row_as_report_only(monkeypatch):
    """#662: the row says which rules its trades ran under; a depth-stamped row (era E) is
    labelled from its own `exit_rule`, not the date. Verdict unchanged by the split."""
    old = _closed_rows(_rs(-1.0, 6))                       # 2026-07 alert dates → era A
    new = _closed_rows([2.0, 2.0], exit_rule="depth")      # row-stamped era E
    for r in new:
        r["alert_date"] = dt.date(2026, 10, 14)
    spy = _Spy(monkeypatch, [_strategy("magna53", "live", live_real=True)],
               {("magna53", "live"): old + new})
    _run(spy)
    _, row = _row_detail(spy)
    e = row["evaluated"][0]
    assert e["by_era"].get("era_e") == 2 and e["by_era"].get("era_a") == 6
    assert "older rules: 6 trades" in e["era"]
    assert e["would_demote"] is False   # streak broken by the two winners; pooled verdict


def test_a_crash_writes_an_error_row_and_re_raises(monkeypatch):
    """A dead watchdog must not look like a quiet one: the error row feeds the nightly
    `%error%` sweep and the re-raise lets audit_wrap record 'failed'."""
    spy = _Spy(monkeypatch, [], {})
    monkeypatch.setattr(registry, "_load_all",
                        AsyncMock(side_effect=RuntimeError("registry unreachable")))
    with pytest.raises(RuntimeError, match="registry unreachable"):
        _run(spy)
    assert [c[2][0] for c in spy.audit_rows] == [lw.ERROR_EVENT]
    assert len(spy.writes) == 1


# ─── 3. Registration: the job exists, is INTELLIGENCE-owned, and fires after the close ─────


def _registered_jobs(monkeypatch):
    """The jobs `start_scheduler` ACTUALLY registers (the test_job_partition capture), with their
    real trigger objects."""
    from agents.market_intelligence import scheduler as sched
    from tests.test_job_partition import _CapturingScheduler
    seen = {}
    real = sched._apply_role_partition

    def _spy(scheduler, role):
        seen["jobs"] = {j.id: j for j in scheduler.get_jobs()}
        return real(scheduler, role)

    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    monkeypatch.setattr(sched, "_apply_role_partition", _spy)

    async def _start():
        sched.start_scheduler()

    asyncio.run(_start())
    return seen["jobs"]


def test_ladder_watchdog_is_registered_intelligence_owned_after_the_close(monkeypatch):
    from agents.market_intelligence import scheduler as sched
    jobs = _registered_jobs(monkeypatch)
    assert lw.JOB_ID in jobs, "ladder_watchdog is not registered by start_scheduler"
    trig = str(jobs[lw.JOB_ID].trigger)
    assert "hour='16'" in trig and "minute='17'" in trig and "mon-fri" in trig, trig
    assert lw.JOB_ID in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert lw.JOB_ID not in sched.EXECUTION_OWNED_JOB_IDS
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
    forbidden = {"update_strategy", "send_telegram_message", "notify_owner", "notify_job_failure",
                 "submit_trade_entry", "place_stop_order", "replace_order",
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
