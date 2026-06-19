"""#302 — P6 replay-regression v0 unit tests.

Two load-bearing properties: (1) the per-trade fingerprint math is correct (it's what the
operator reads against the calibration card), and (2) the report SURFACES — it never emits an
automated divergence verdict, and it persists a snapshot ONLY once live trades exist (so the
quarterly review has history but pre-launch noise rows don't accrue).
"""
import asyncio

import agents.market_intelligence.kill_scale_bands as ksb
import agents.market_intelligence.db as dbmod
import agents.market_intelligence.replay_regression as rr


# ── fingerprint math ──

def test_fingerprint_per_trade_and_path_stats():
    # cum path: -1,-2,+1,0,-1,-2,+3  → maxDD 3R; loss-runs 2 then 3 → worst_streak 3; ends win.
    fp = rr.compute_fingerprint([-1.0, -1.0, 3.0, -1.0, -1.0, -1.0, 5.0])
    assert fp["n"] == 7
    assert round(fp["expectancy_r"], 4) == round(3.0 / 7, 4)
    assert round(fp["win_rate"], 4) == round(2 / 7, 4)
    assert fp["avg_win_r"] == 4.0          # (3+5)/2
    assert fp["avg_loss_r"] == -1.0
    assert fp["max_dd_r"] == -3.0          # expressed as a negative drawdown
    assert fp["worst_streak"] == 3
    assert fp["cur_streak"] == 0           # last trade was a win


def test_fingerprint_current_streak_when_ending_in_losses():
    fp = rr.compute_fingerprint([2.0, -1.0, -1.0])
    assert fp["cur_streak"] == 2 and fp["worst_streak"] == 2


def test_fingerprint_empty_cohort():
    assert rr.compute_fingerprint([]) == {"n": 0}
    assert rr.compute_fingerprint([None, None]) == {"n": 0}


# ── render: surfaces, never verdicts ──

def test_render_prelaunch_reads_comparison_begins_at_cutover():
    lines = rr.render_section("live", {"n": 0})
    text = "\n".join(lines)
    assert "comparison begins at cutover" in text
    assert "#268b calibration" in text            # the reference card still renders
    assert "diverg" not in text.lower()           # NO automated divergence judgment


def test_render_postlaunch_shows_live_numbers_and_caveat_no_verdict():
    fp = rr.compute_fingerprint([-1.0, 3.0, -1.0, 5.0])
    text = "\n".join(rr.render_section("live", fp))
    assert "live (n=4)" in text
    assert "calibration (#268b Phase B, n=399)" in text
    assert "STRUCTURAL" in text                    # the investigate-don't-assume-decay caveat
    # The report must NOT prescribe — no divergence verdict, no band-action words.
    assert "diverg" not in text.lower()
    for banned in ("KILL", "REDUCE", "SCALE UP", "DEGRADING"):
        assert banned not in text


# ── run_replay_regression: persist only when live trades exist; no Telegram ──

def _wire(monkeypatch, rs):
    audited = []

    async def fake_inputs(mode):
        return {"realized_rs": rs, "equity_above_start": False,
                "drawdown_tier": "OK", "account_mode": mode}

    async def fake_audit(evt, summary, detail):
        audited.append((evt, detail))

    monkeypatch.setattr(ksb, "assemble_band_inputs", fake_inputs)
    monkeypatch.setattr(dbmod, "log_audit_event", fake_audit)
    return audited


def test_run_persists_one_snapshot_when_live_trades_exist(monkeypatch):
    audited = _wire(monkeypatch, [2.0, -1.0, 3.0, -1.0])
    res = asyncio.run(rr.run_replay_regression("live", persist=True))
    assert res["fingerprint"]["n"] == 4
    assert [e for e, _ in audited] == ["replay_regression_snapshot"]
    assert "calibration_source" in audited[0][1]   # the snapshot carries the envelope provenance


def test_run_does_not_persist_pre_launch(monkeypatch):
    audited = _wire(monkeypatch, [])
    res = asyncio.run(rr.run_replay_regression("live", persist=True))
    assert res["fingerprint"]["n"] == 0
    assert audited == []                           # no snapshot row when N=0 (no noise)
    assert any("comparison begins at cutover" in ln for ln in res["lines"])


def test_run_persist_false_never_writes(monkeypatch):
    audited = _wire(monkeypatch, [1.0, -1.0, 2.0])
    asyncio.run(rr.run_replay_regression("live", persist=False))
    assert audited == []
