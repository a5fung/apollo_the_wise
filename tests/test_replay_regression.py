"""#302 — P6 replay-regression v0 unit tests.

Two load-bearing properties: (1) the per-trade fingerprint math is correct (it's what the
operator reads against the calibration card), and (2) the report SURFACES — it never emits an
automated divergence verdict, and it persists a snapshot ONLY once live trades exist (so the
quarterly review has history but pre-launch noise rows don't accrue).
"""
import asyncio
from datetime import date

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

def _split(rs, d=date(2026, 8, 20)):
    """#662 — every live line carries its rule-era split; these trades ran under an older rule."""
    from agents.market_intelligence.rule_eras import split_current_vs_older
    return split_current_vs_older(rs, [{"alert_date": d, "signal_type": "magna53"} for _ in rs],
                                  date(2026, 9, 20))


def test_render_prelaunch_reads_comparison_begins_at_cutover():
    lines = rr.render_section("live", {"n": 0}, None)
    text = "\n".join(lines)
    assert "comparison begins at cutover" in text
    assert "#268b calibration" in text            # the reference card still renders
    assert "diverg" not in text.lower()           # NO automated divergence judgment


def test_render_postlaunch_shows_live_numbers_and_caveat_no_verdict():
    rs = [-1.0, 3.0, -1.0, 5.0]
    fp = rr.compute_fingerprint(rs)
    text = "\n".join(rr.render_section("live", fp, _split(rs)))
    assert "live (n=4)" in text
    assert "older rules: 4 trades" in text        # #662 — the era clause is part of the line
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


def test_run_persist_false_never_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(tmp_path))
    audited = _wire(monkeypatch, [1.0, -1.0, 2.0])
    asyncio.run(rr.run_replay_regression("live", persist=False))
    assert audited == []
    assert list(tmp_path.iterdir()) == []            # #313: no CI status file either


# ── #313 / ADR 0022 L4: the persisting run writes ci_status/selection_replay.json ──

def _ci_file(tmp_path):
    import json
    p = tmp_path / "selection_replay.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_persisting_run_writes_the_ci_status_file_green_below_n50(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(tmp_path))
    audited = _wire(monkeypatch, [2.0, -1.0, 3.0, -1.0])
    asyncio.run(rr.run_replay_regression("live", persist=True))
    raw = _ci_file(tmp_path)
    assert raw["job"] == "selection_replay" and raw["status"] == "green"
    assert "n=4" in raw["detail"] and "not armed" in raw["detail"]
    assert raw["asof"].endswith(("-04:00", "-05:00"))   # ET, offset-aware
    assert [e for e, _ in audited] == ["replay_regression_snapshot"]   # file-only: no second audit row


def test_persisting_run_writes_the_file_at_n0_too_so_a_missing_file_means_the_job_died(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(tmp_path))
    audited = _wire(monkeypatch, [])
    asyncio.run(rr.run_replay_regression("live", persist=True))
    raw = _ci_file(tmp_path)
    assert raw["status"] == "green" and "n=0" in raw["detail"]
    assert audited == []                              # the audit snapshot still skips n=0


def test_persisting_run_goes_red_at_the_signed_threshold(monkeypatch, tmp_path):
    """50 live trades at +0.60R mean vs the +0.95R calibration = a 0.35R gap at n>=50 (M3f)."""
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(tmp_path))
    _wire(monkeypatch, [0.60] * 50)
    asyncio.run(rr.run_replay_regression("live", persist=True))
    raw = _ci_file(tmp_path)
    assert raw["status"] == "red" and "n=50" in raw["detail"] and "REGRESSION" in raw["detail"]
    _wire(monkeypatch, [0.60] * 49)
    asyncio.run(rr.run_replay_regression("live", persist=True))
    assert _ci_file(tmp_path)["status"] == "green"    # one trade fewer: not armed


def test_a_failed_status_write_never_breaks_the_digest(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(blocker / "ci"))
    _wire(monkeypatch, [1.0, 2.0])
    res = asyncio.run(rr.run_replay_regression("live", persist=True))
    assert "error" not in res and any("live (n=2)" in ln for ln in res["lines"])


# ── review 2026-10-14: the CI write is isolated and live-only ──

def test_a_raise_in_the_ci_status_code_never_costs_the_digest_its_replay_section(monkeypatch, tmp_path):
    """The CI block sat inside run_replay_regression's outer try, so ANY raise from the status code
    replaced the already-rendered digest lines with 'replay-regression unavailable'. Unreachable
    today (compute_fingerprint always sets expectancy_r when n>0) — but a future edit to the status
    code must cost the deploy gate a stale file, never the Sunday review its replay section."""
    import agents.market_intelligence.ci_status as cs
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(tmp_path))
    audited = _wire(monkeypatch, [2.0, -1.0, 3.0, -1.0])

    def boom(*a, **k):
        raise RuntimeError("status code regressed")

    monkeypatch.setattr(cs, "selection_replay_status", boom)
    res = asyncio.run(rr.run_replay_regression("live", persist=True))
    assert "error" not in res and any("live (n=4)" in ln for ln in res["lines"])
    assert not any("unavailable" in ln for ln in res["lines"])
    assert res["fingerprint"]["n"] == 4
    assert [e for e, _ in audited] == ["replay_regression_snapshot"]      # the audit row still landed
    assert list(tmp_path.iterdir()) == []                                  # and no half-written file


def test_a_non_live_run_never_overwrites_the_live_ci_status(monkeypatch, tmp_path):
    """M3f was signed against the LIVE cohort. Paper's n is large with low expectancy: a paper
    call (nothing makes one today) would overwrite the live status with a false RED that blocks
    the next trading-scope deploy."""
    monkeypatch.setenv("APOLLO_CI_STATUS_DIR", str(tmp_path))
    _wire(monkeypatch, [2.0, -1.0, 3.0, -1.0])
    asyncio.run(rr.run_replay_regression("live", persist=True))
    live_file = _ci_file(tmp_path)
    assert live_file["status"] == "green" and "n=4" in live_file["detail"]
    _wire(monkeypatch, [0.1] * 400)                    # a big, mediocre paper book: would read RED
    res = asyncio.run(rr.run_replay_regression("paper", persist=True))
    assert "error" not in res and res["fingerprint"]["n"] == 400    # the paper digest still renders
    assert _ci_file(tmp_path) == live_file             # byte-for-byte the live reading
