"""#275 — kill/scale band evaluator (pure-function unit tests).

The load-bearing property: the SIGNED bands must NOT fire on the normal variance of the
healthy +0.95R/30% year (#268 Phase B envelope — trailing-20 p5 −0.63R / min −1.03R,
worst streak 15, maxDD −24.1R). These tests pin each band's boundary against that envelope.
"""
import datetime as dt

from agents.market_intelligence.kill_scale_bands import (
    evaluate_kill_scale_bands, current_losing_streak, is_transition, format_band_line,
    _SAMPLE_FLOOR, _SCALE_MIN_TRADES,
)


def _rs(value, n):
    return [value] * n


# ── losing-streak convention ──

def test_streak_counts_breakeven_as_loss():
    # r <= 0 is a loss (matches the calibration's worst-streak=15 convention).
    assert current_losing_streak([1.0, -1.0, 0.0, -1.0]) == 3
    assert current_losing_streak([-1.0, -1.0, 2.0]) == 0   # last trade was a win
    assert current_losing_streak([]) == 0


# ── sample-size floor: no strategy-health band before 20 trades ──

def test_below_floor_holds_even_with_ugly_rs():
    # 19 brutal trades — still HOLD (only equity guards bind pre-floor).
    v = evaluate_kill_scale_bands(_rs(-1.0, _SAMPLE_FLOOR - 1), equity_above_start=False)
    assert v.band == "HOLD"
    assert "sample floor" in v.reasons[0]


def test_below_floor_block_tier_still_kills():
    # The drawdown-breaker BLOCK equity guard binds from day 1, floor or not.
    v = evaluate_kill_scale_bands(_rs(-1.0, 5), equity_above_start=False, drawdown_tier="BLOCK")
    assert v.band == "KILL"
    assert "BLOCK" in v.reasons[0]


# ── KILL must NOT fire on the healthy envelope; fires just beyond it ──

def test_worst_healthy_t20_is_reduce_not_kill():
    # The worst healthy trailing-20 window was −1.03R → REDUCE, NOT KILL (kill band −1.05).
    v = evaluate_kill_scale_bands(_rs(-1.03, 20), equity_above_start=False)
    assert v.band == "REDUCE"


def test_t20_at_kill_threshold_kills():
    v = evaluate_kill_scale_bands(_rs(-1.05, 20), equity_above_start=False)
    assert v.band == "KILL"
    assert any("trailing-20" in r for r in v.reasons)


def test_healthy_maxdd_cum_r_does_not_kill():
    # −24R cumulative (the healthy maxDD) must not KILL; −30R does.
    # 24 trades averaging −1R = −24R cum, t20 = −1R (≤ −0.70 → REDUCE, not KILL via t20).
    v24 = evaluate_kill_scale_bands(_rs(-1.0, 24), equity_above_start=False)
    assert v24.band == "REDUCE"            # cum −24 alone is not a KILL
    assert all("cumulative" not in r for r in v24.reasons)
    # 30 trades averaging −1R = −30R cum AND t20 −1R → KILL (both cum and... t20 −1 > −1.05,
    # so KILL is driven by the cumulative −30R guard specifically).
    v30 = evaluate_kill_scale_bands(_rs(-1.0, 30), equity_above_start=False)
    assert v30.band == "KILL"
    assert any("cumulative" in r for r in v30.reasons)


# ── REDUCE boundary vs healthy p5 ──

def test_healthy_p5_t20_holds_not_reduce():
    # Healthy p5 trailing-20 = −0.63R; REDUCE band is −0.70R → −0.63 stays HOLD. End the
    # window with a win so the streak is cleared and we isolate the t20 mean (−12.6/20).
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [6.4], equity_above_start=False)
    assert round(v.trailing_20, 2) == -0.63
    assert v.band == "HOLD"


def test_t20_below_reduce_threshold_reduces():
    # trailing-20 exactly at −0.70 (−14.0/20), streak cleared by the trailing win → the
    # REDUCE is driven by the t20 threshold, not the streak.
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [5.0], equity_above_start=False)
    assert round(v.trailing_20, 2) == -0.70
    assert v.band == "REDUCE"
    assert any("trailing-20" in r for r in v.reasons)


def test_streak_15_holds_streak_16_reduces():
    # Worst observed healthy streak = 15 → HOLD; 16 exceeds it → REDUCE.
    base = _rs(1.0, 6)  # wins to keep t20 healthy so only the streak can trigger
    assert evaluate_kill_scale_bands(base + _rs(-1.0, 15), equity_above_start=False).band == "HOLD"
    v16 = evaluate_kill_scale_bands(base + _rs(-1.0, 16), equity_above_start=False)
    assert v16.band == "REDUCE"
    assert any("streak" in r for r in v16.reasons)


# ── SCALE ──

def test_scale_requires_40_trades_positive_t40_and_equity_up():
    rs = _rs(0.6, _SCALE_MIN_TRADES)       # trailing-40 = +0.6 ≥ +0.5
    assert evaluate_kill_scale_bands(rs, equity_above_start=True).band == "SCALE"
    # equity not above start → no scale
    assert evaluate_kill_scale_bands(rs, equity_above_start=False).band == "HOLD"
    # only 39 trades → no trailing-40 → HOLD
    assert evaluate_kill_scale_bands(_rs(0.6, 39), equity_above_start=True).band == "HOLD"
    # t40 just under +0.5 → HOLD
    assert evaluate_kill_scale_bands(_rs(0.49, 40), equity_above_start=True).band == "HOLD"


def test_healthy_year_expectancy_holds():
    # A +0.95R-ish steady cohort with normal variance sits in HOLD (not SCALE unless the
    # explicit scale conditions are met; here equity flat so HOLD).
    import random
    random.seed(7)
    rs = [random.choice([-1.0, -1.0, -1.0, 3.0, 5.0]) for _ in range(60)]  # ~+0.6R/30%-ish
    v = evaluate_kill_scale_bands(rs, equity_above_start=False)
    assert v.band in ("HOLD", "SCALE")     # never REDUCE/KILL on healthy variance
    assert v.band == "HOLD"                # equity flat → not scaling


# ── transitions ──

def test_is_transition():
    assert is_transition(None, "HOLD") is True       # first observation
    assert is_transition("HOLD", "HOLD") is False
    assert is_transition("HOLD", "REDUCE") is True
    assert is_transition("REDUCE", "KILL") is True
    assert is_transition("REDUCE", "HOLD") is True    # recovery is a transition too


# ── verdict line rendering (digest + alert) ──

def test_format_band_line_shows_band_numbers_and_override():
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [5.0], equity_above_start=False)  # REDUCE
    line = format_band_line(v)
    assert "REDUCE" in line
    assert "t20=" in line and "streak=" in line and "cum=" in line
    # override annotation surfaces when active
    annotated = format_band_line(v, override={"since": "2026-06-22", "direction": "trade through",
                                              "reason": "regime shift"})
    assert "OVERRIDE ACTIVE since 2026-06-22" in annotated
    assert "regime shift" in annotated


# ── open-book reporting (2026-08-09): REPORT ONLY — must never move the verdict itself.
# docs/analysis/kill_scale_band_closed_trade_bias_2026-08-09.md ──

def test_format_band_line_open_book_omitted_when_not_supplied():
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [5.0], equity_above_start=False)  # REDUCE
    line = format_band_line(v)  # open_positions not passed at all
    assert "open book" not in line


def test_format_band_line_open_book_flat_vs_populated():
    v = evaluate_kill_scale_bands(_rs(-1.0, 19) + [5.0], equity_above_start=False)  # REDUCE

    flat = format_band_line(v, open_positions=[])
    assert "open book (NOT in the verdict above): flat" in flat

    populated = format_band_line(
        v, open_positions=[{"ticker": "PLTR", "hold_days": 21},
                           {"ticker": "NVDA", "hold_days": 15}])
    assert "open book (NOT in the verdict above): 2 position(s)" in populated
    assert "PLTR 21d" in populated and "NVDA 15d" in populated
    # the band + its driving numbers are IDENTICAL whether or not an open book is reported —
    # open_positions only appends a trailing line, never edits band/reasons/numbers.
    assert flat.split("\n")[:3] == populated.split("\n")[:3]
    assert "REDUCE" in populated


# ── run_band_evaluation: the live-money alert path (transition → send once + persist) ──

import asyncio  # noqa: E402
import agents.market_intelligence.kill_scale_bands as ksb  # noqa: E402


def _wire(monkeypatch, *, rs, prev_band, override=None, last_band_fn=None, set_fn=None):
    """Mock run_band_evaluation's DB/Telegram edges; drive the band via the cohort `rs`.
    Returns (sent, persisted, audited) recorders.

    `last_band_fn`/`set_fn` (simplify GROUP 6, 2026-07-03) let a caller override the
    default single-caller `get_last_band`/`set_last_band` fakes with its own — e.g. the
    concurrency test below needs a SHARED store + lock across two callers, not the
    per-call `prev_band` constant / `persisted`-list recorder this default provides.
    Reusing `_wire` for that case collapses 6 hand-rolled setattrs down to the 2 that
    actually differ."""
    sent, persisted, audited = [], [], []

    async def fake_inputs(mode):
        return {"realized_rs": rs, "equity_above_start": False,
                "drawdown_tier": "OK", "account_mode": mode}

    async def fake_last_band(mode):
        return (prev_band, "2026-06-20" if prev_band else None)

    async def fake_override():           # get_active_override is global (no account_mode)
        return override

    async def fake_set(mode, band):
        # Single-caller path — this caller always wins the atomic claim (see the dedicated
        # concurrency test below for the two-caller race).
        persisted.append(band)
        return True

    async def fake_send(msg):
        sent.append(msg); return True

    async def fake_audit(evt, summary, detail):
        audited.append(evt)

    monkeypatch.setattr(ksb, "assemble_band_inputs", fake_inputs)
    monkeypatch.setattr(ksb, "get_last_band", last_band_fn or fake_last_band)
    monkeypatch.setattr(ksb, "get_active_override", fake_override)
    monkeypatch.setattr(ksb, "set_last_band", set_fn or fake_set)
    import agents.market_intelligence.briefing as briefing
    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(briefing, "send_telegram_message", fake_send)
    monkeypatch.setattr(dbmod, "log_audit_event", fake_audit)
    return sent, persisted, audited


def test_band_transition_sends_once_and_persists(monkeypatch):
    # HOLD → REDUCE (t20 −0.70): one Telegram, persists the new band, audits the transition.
    sent, persisted, audited = _wire(monkeypatch, rs=_rs(-1.0, 19) + [5.0], prev_band="HOLD")
    res = asyncio.run(ksb.run_band_evaluation("live", send=True))
    assert res["band"] == "REDUCE" and res["transitioned"] is True
    assert persisted == ["REDUCE"]
    assert len(sent) == 1 and "REDUCE" in sent[0]
    assert "kill_scale_band_transition" in audited


def test_band_no_transition_is_silent(monkeypatch):
    # Already REDUCE, still REDUCE → no send, no persist, no audit.
    sent, persisted, audited = _wire(monkeypatch, rs=_rs(-1.0, 19) + [5.0], prev_band="REDUCE")
    res = asyncio.run(ksb.run_band_evaluation("live", send=True))
    assert res["transitioned"] is False
    assert persisted == [] and sent == [] and audited == []


def test_band_baseline_hold_persists_but_does_not_alert(monkeypatch):
    # ∅ → HOLD pre-launch baseline: persists (so it won't re-fire) but is NOT alerted.
    sent, persisted, audited = _wire(monkeypatch, rs=_rs(0.5, 20), prev_band=None)
    res = asyncio.run(ksb.run_band_evaluation("live", send=True))
    assert res["band"] == "HOLD" and res["transitioned"] is True
    assert persisted == ["HOLD"]          # primed so the next eval has a baseline
    assert sent == []                     # ∅→HOLD baseline suppressed


# ── F21 — concurrent evaluations must dedup to exactly ONE alert (TOCTOU fix) ──

def test_concurrent_transitions_dedup_to_one_alert(monkeypatch):
    """Two concurrent evaluate calls (e.g. a scheduled EOD run + an on-demand `/audit`) that
    would BOTH observe HOLD→REDUCE under the old unlocked read-then-write must still produce
    exactly ONE Telegram + ONE audit row. `fake_last_band` captures its read synchronously
    (before yielding) so BOTH callers read the SAME stale prior state — the TOCTOU half of the
    bug — then yields so the two coroutines interleave. `fake_set` is the fake state store's
    ATOMIC claim: a lock-guarded check-and-set on a single row, mirroring the real
    `INSERT ... ON CONFLICT DO UPDATE ... WHERE state IS DISTINCT FROM ... RETURNING` — the
    mechanism actually under test. Only one of the two calls should win the claim.

    Reuses `_wire` (simplify GROUP 6, 2026-07-03) for the 4 edges that DON'T need the
    shared store — only `get_last_band`/`set_last_band` are overridden via
    `last_band_fn`/`set_fn`; `prev_band` is unused (the override ignores it)."""
    store: dict[str, str] = {}          # fake mi_safeguard_state row: {account_mode: band}
    claim_lock = asyncio.Lock()

    async def fake_last_band(mode):
        prev = store.get(mode)      # read captured BEFORE yielding — both callers see it stale
        await asyncio.sleep(0)      # force interleaving with the concurrent evaluation
        return (prev, None)

    async def fake_set(mode, band):
        # The atomic claim under test: single-winner check-and-set on the shared row.
        async with claim_lock:
            if store.get(mode) == band:
                return False
            store[mode] = band
            return True

    # Same cohort for both callers so both independently compute the SAME new band
    # (REDUCE) — exactly the scenario in the bug report.
    sent, _persisted, audited = _wire(
        monkeypatch, rs=_rs(-1.0, 19) + [5.0], prev_band=None,
        last_band_fn=fake_last_band, set_fn=fake_set,
    )

    async def _run_both():
        return await asyncio.gather(
            ksb.run_band_evaluation("live", send=True),
            ksb.run_band_evaluation("live", send=True),
        )

    results = asyncio.run(_run_both())

    # Both calls computed REDUCE; exactly one claimed the transition.
    assert [r["band"] for r in results] == ["REDUCE", "REDUCE"]
    assert sorted(r["transitioned"] for r in results) == [False, True]
    assert len(sent) == 1 and "REDUCE" in sent[0]
    assert audited.count("kill_scale_band_transition") == 1
    assert store["live"] == "REDUCE"


# ── assemble_band_inputs / assess_bands: open positions must NEVER move the verdict ──
# (2026-08-09, docs/analysis/kill_scale_band_closed_trade_bias_2026-08-09.md — "ruled out
# on this system's own evidence: 4 of 6 live Bull trades touched >=+1R and every one closed
# red; FIGS peaked past +2R and closed -$7". Real DB round-trip via the SAME mock-pool
# helper (`tests/conftest.make_mock_pool`) test_safeguard_state_348.py uses, so this exercises
# the ACTUAL query wiring, not a re-description of it.)

from unittest.mock import AsyncMock  # noqa: E402
from tests.conftest import make_mock_pool  # noqa: E402
import agents.market_intelligence.db as dbmod  # noqa: E402


def _closed_trade_rows(n_trades, n_days):
    """`n_trades` closed rows shaped exactly like test_t20_below_reduce_threshold_reduces
    (t20 = -0.70 -> REDUCE), spread over `n_days` distinct alert_dates. `n_days` no longer
    gates anything (the entry-day independence floor was proposed, measured, and REMOVED —
    docs/analysis/kill_scale_band_closed_trade_bias_2026-08-09.md); kept only so the fixture
    still reads as realistic dated rows for the mock pool."""
    base = dt.date(2026, 1, 5)
    rows = [{"total_pnl": -100.0, "risk_dollars": 100.0,
            "alert_date": base + dt.timedelta(days=i % n_days)} for i in range(n_trades - 1)]
    rows.append({"total_pnl": 500.0, "risk_dollars": 100.0,
                "alert_date": base + dt.timedelta(days=(n_trades - 1) % n_days)})
    return rows


def _assess_with_open_rows(monkeypatch, open_rows):
    """Wire a fake pool through db.get_pool and run the REAL assemble_band_inputs ->
    evaluate_kill_scale_bands pipeline (assess_bands) — not a re-implementation of it."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[_closed_trade_rows(20, 20), open_rows])
    conn.fetchval = AsyncMock(return_value="OK")               # drawdown tier
    # 1st fetchrow = assemble_band_inputs' equity endpoints; 2nd = get_active_override's
    # override-row lookup (assess_bands calls both) -> None so the override short-circuits.
    conn.fetchrow = AsyncMock(
        side_effect=[{"first_eq": 100000.0, "last_eq": 100000.0}, None])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    return asyncio.run(ksb.assess_bands("live"))


def test_open_positions_never_move_the_verdict(monkeypatch):
    inputs_flat, verdict_flat, _ = _assess_with_open_rows(monkeypatch, [])
    inputs_open, verdict_open, _ = _assess_with_open_rows(monkeypatch, [
        {"ticker": "PLTR", "hold_days": 21},   # a long-held "winner" by hold time alone
        {"ticker": "NVDA", "hold_days": 15},
    ])

    # Same closed cohort -> same band, same numbers, same reasons, whether or not an open
    # book with long-held positions exists. Only `open_positions` in the inputs differs.
    assert verdict_flat.band == verdict_open.band == "REDUCE"
    assert verdict_flat.trailing_20 == verdict_open.trailing_20
    assert verdict_flat.streak == verdict_open.streak
    assert verdict_flat.cum_r == verdict_open.cum_r
    assert verdict_flat.reasons == verdict_open.reasons
    assert inputs_flat["open_positions"] == []
    assert inputs_open["open_positions"] == [
        {"ticker": "PLTR", "hold_days": 21}, {"ticker": "NVDA", "hold_days": 15}]
