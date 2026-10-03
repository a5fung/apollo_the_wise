"""#580 — the breadth-fix replay probe (scripts/probes/_580/replay_breadth_fix.py) is itself tested.

The probe runs ONCE against prod (piped into the market container) to decide a money-path deploy, so
its pure parts must be right before that run: the stage-rule recompute (old vs fixed), the birth-fill
arithmetic and completeness pick, and the EP score transform (bonus removed, floor, multiplier,
output scale, the 65 bar). A fake read-only DB then drives `main()` end to end on a hand-built
history: a Mainstream theme two nights at 0% (A), a newborn whose filled breadth fades it the next
night (B), and an EP alert that loses the +10 and drops under 65. No DB, no network, no model calls.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "probes" / "_580" / "replay_breadth_fix.py"
_spec = importlib.util.spec_from_file_location("replay_breadth_fix_580", _PATH)
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


# ─── pure parts ─────────────────────────────────────────────────────────────────

def test_selftest_passes():
    assert rp.selftest() == 0


def test_prior_read_old_vs_fixed_differs_only_on_exact_zero():
    for prev in (None, 0.0, 0.1, 0.39, 0.4, 0.41, 1.0):
        old, new = rp.prior_counts(prev, fixed=False), rp.prior_counts(prev, fixed=True)
        assert (old != new) == (prev == 0.0), prev


def test_stage_rule_mirrors_the_engine_on_the_fixed_case():
    """The probe's recompute and the engine's rescore must agree on the case the fix is about."""
    h = [74.0] * 5
    assert rp.stage_rule(74.5, h, 74, "Mainstream", 0.0, 0.0, True, fixed=False) == "Mainstream"
    assert rp.stage_rule(74.5, h, 74, "Mainstream", 0.0, 0.0, True, fixed=True) == "Fading"
    assert rp.stage_rule(74.5, h, 74, "Mainstream", 0.0, None, True, fixed=True) == "Mainstream"


def test_stage_rule_reads_the_three_oldest_history_scores_like_the_engine():
    """`_get_theme_history` is newest-first and the engine averages `history[-3:]` — the three
    OLDEST rows of the window. Newest 90, oldest three 60 -> smoothed 60, delta +15 -> Accelerating
    (hysteresis: yesterday 90 - 60 = +30 > 5 confirms)."""
    assert rp.stage_rule(75.0, [90.0, 80.0, 60.0, 60.0, 60.0], 90, "Nascent", 0.9, 0.9, True,
                         fixed=True) == "Accelerating"


def test_hysteresis_holds_an_unconfirmed_flip():
    # delta +10 but yesterday's score sits at the smoothed level -> flip held at the prior stage
    assert rp.stage_rule(70.0, [60.0, 60.0, 60.0], 60, "Nascent", 0.9, 0.9, True,
                         fixed=True) == "Nascent"


def test_score_transform_exact_and_crossing():
    bd = {"gap": 20, "liquidity": 10, "catalyst": 5, "float": 0, "vol_conviction": 0, "theme_bonus": 10}
    s = rp.score_without_bonus(bd, 71.2, "separation", 12.0, "strong", 1.2)
    assert (s["before"], s["after"], s["mult"], s["reproduced"]) == (71.2, 58.8, 1.0, True)
    assert rp.crosses(s["before"], s["after"], rp.BAR_65) is True
    # a stored score no multiplier reproduces is flagged, not silently trusted
    s = rp.score_without_bonus(bd, 80.0, "separation", 12.0, "strong", 1.0)
    assert s["reproduced"] is False


def test_score_transform_keeps_the_floor():
    bd = {"gap": 10, "liquidity": 10, "catalyst": 15, "theme_bonus": 10, "conviction_floor": 15}
    s = rp.score_without_bonus(bd, 90.0, "separation", 11.0, "game_changer", 1.0)
    assert s["after"] == s["before"] == 90.0


def test_score_transform_legacy_side_raw_scale():
    bd = {"gap": 25, "catalyst": 20, "theme_bonus": 10}
    s = rp.score_without_bonus(bd, 66.0, "legacy", 21.0, "moderate", 1.0)
    assert (s["before"], s["after"], s["mult"]) == (66.0, 54.0, 1.2)


def test_completeness_pick_skips_stray_and_partial_days():
    base = [(date(2026, 9, 29) - timedelta(days=i), 2400) for i in range(10)]
    assert rp.pick_latest_complete([(date(2026, 9, 30), 3)] + base) == date(2026, 9, 29)
    assert rp.pick_latest_complete([(date(2026, 9, 30), 1100)] + base) == date(2026, 9, 29)
    assert rp.pick_latest_complete([(date(2026, 9, 30), 2300)] + base) == date(2026, 9, 30)


def test_probe_constants_match_the_running_code():
    from agents.market_intelligence import ep_rubric as R
    from agents.market_intelligence import theme_engine as te
    from agents.market_intelligence.ep_theme_belonging import THEME_BONUS_STAGES
    assert rp.BREADTH_DECAY_THRESHOLD == te._BREADTH_DECAY_THRESHOLD
    assert rp.PAYING == THEME_BONUS_STAGES
    assert rp.BAR_65 == R.SEPARATION_BAR
    assert rp.THEME_BONUS_POINTS == R.SCORE_WEIGHTS["theme_bonus"]["points"]
    assert rp.SEPARATION_SCALE == (R.SCORE_WEIGHTS["output_scale"]["mult"],
                                   R.SCORE_WEIGHTS["output_scale"]["offset"])
    for x in (40.0, 52.3, 61.7):
        assert rp.present(x, 1.0, "separation") == R.apply_output_scale(
            round(x, 1), R.SCORE_WEIGHTS["output_scale"])
    from agents.market_intelligence import db as dbmod
    rows = [{"close": 11.0, "sma_20": 10.0}, {"close": 9.0, "sma_20": 10.0}, {"close": None, "sma_20": 1.0}]
    assert rp.breadth_above_sma20(rows) == dbmod.breadth_above_sma20(rows)


# ─── main() end to end on a fake read-only DB ─────────────────────────────────

_UTC = timezone.utc


def _theme(d, name, stage, score, breadth, tickers, *, source="live", rs_avg=70.0, made=None,
           desc=None):
    return {"theme_date": d, "name": name, "stage": stage, "score": score, "rs_avg": rs_avg,
            "pct_above_20sma": breadth, "tickers": tickers, "source": source,
            "created_at": made or datetime(d.year, d.month, d.day, 21, 3, tzinfo=_UTC),
            "description": desc or f"{name}: {', '.join(tickers)} lead the group."}


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, data):
        self.data, self.sql = data, []

    def transaction(self, readonly=False):
        assert readonly, "the probe must read inside a READ ONLY transaction"
        return _Tx()

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        for key, rows in self.data.items():
            if key in sql:
                return rows
        raise AssertionError(f"unexpected query: {sql[:80]}")


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_main_end_to_end_on_a_fake_db(monkeypatch, capsys):
    gold = ["AEM", "KGC", "NEM"]
    rigs = ["RIG", "VAL"]
    D = lambda m, d: date(2026, m, d)
    themes = [_theme(D(9, d), "Gold Miners", "Mainstream", 74.0, 0.6, gold) for d in (21, 22, 23, 24, 25)]
    themes += [
        _theme(D(9, 28), "Gold Miners", "Mainstream", 74.0, 0.0, gold),   # first 0% night
        _theme(D(9, 29), "Gold Miners", "Mainstream", 74.5, 0.0, gold),   # 2nd: old keeps, fix fades
        _theme(D(9, 30), "Gold Miners", "Mainstream", 74.5, 0.5, gold),   # recovered: Mainstream again
        # newborn on 09-28 (nightly promote, NULL breadth) whose members were all below average
        _theme(D(9, 28), "Offshore Drillers", "Nascent", 40.0, None, rigs, source="shadow_promoted",
               made=datetime(2026, 9, 28, 21, 5, tzinfo=_UTC)),
        _theme(D(9, 29), "Offshore Drillers", "Nascent", 41.0, 0.0, rigs),
        # last seen 09-10: aged out of get_active_themes' 7-day window, so it cannot carry KGC's +10
        _theme(D(9, 10), "Stale Gold Theme", "Mainstream", 70.0, 0.6, ["KGC"]),
    ]
    counts = [{"score_date": D(9, 30) - timedelta(days=i), "n": 2400} for i in range(60)]
    scores = [{"ticker": tk, "score_date": D(9, 28), "close": 9.0, "sma_20": 10.0} for tk in rigs]
    alerts = [
        {"id": 1, "ticker": "KGC", "alert_date": D(9, 30), "detected_at": datetime(2026, 9, 30, 13, 35, tzinfo=_UTC),
         "created_at": datetime(2026, 9, 30, 13, 35, tzinfo=_UTC), "ep_score": 71.2, "score_tier": "HIGH",
         "in_active_theme": True, "source": "live", "gap_pct": 12.0, "catalyst_quality": "strong"},
        {"id": 2, "ticker": "AEM", "alert_date": D(9, 26), "detected_at": datetime(2026, 9, 26, 13, 35, tzinfo=_UTC),
         "created_at": datetime(2026, 9, 26, 13, 35, tzinfo=_UTC), "ep_score": 80.0, "score_tier": "HIGH",
         "in_active_theme": True, "source": "live", "gap_pct": 15.0, "catalyst_quality": "strong"},
    ]
    scanlog = [{"scan_date": D(9, 30), "ticker": "KGC", "ep_score": 71.2,
                "score_breakdown": {"gap": 20, "liquidity": 10, "catalyst": 5, "float": 0,
                                    "vol_conviction": 0, "theme_bonus": 10},
                "ep_bar": 65.0, "score_side": "separation",
                "scan_time_et": datetime(2026, 9, 30, 13, 34, tzinfo=_UTC),
                "catalyst_quality": "strong", "gap_pct": 12.0}]
    regimes = [{"regime_date": D(9, 29), "regime": "Neutral", "ep_threshold": 65}]
    conn = _FakeConn({
        "FROM mi_themes": themes,
        "COUNT(*) AS n FROM mi_stock_scores": counts,
        "close, sma_20 FROM mi_stock_scores": scores,
        "FROM mi_ep_alerts": alerts,
        "FROM mi_ep_scan_log": scanlog,
        "FROM mi_ep_theme_belonging_shadow": [],
        "FROM mi_market_regime": regimes,
    })
    from agents.market_intelligence import db as dbmod
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=_Pool(conn)))

    assert await rp.main() == 0
    out, err = capsys.readouterr()
    lines = [json.loads(x) for x in out.splitlines() if x.strip()]
    days = {(x["name"], x["theme_date"]): x for x in lines if x["kind"] == "theme_day"}
    alerts_out = [x for x in lines if x["kind"] == "alert"]

    assert all(s.lstrip().upper().startswith("SELECT") for s in conn.sql), "read-only probe"
    assert set(days) == {("Gold Miners", "2026-09-29"), ("Offshore Drillers", "2026-09-29")}
    g = days[("Gold Miners", "2026-09-29")]
    assert (g["stored_stage"], g["fixed_stage"], g["cause"]) == ("Mainstream", "Fading", "zero_prior")
    assert g["recompute_agrees_with_stored"] is True
    o = days[("Offshore Drillers", "2026-09-29")]
    assert (o["stored_stage"], o["fixed_stage"], o["cause"]) == ("Nascent", "Fading", "birth_fill")
    assert o["prev_breadth_stored"] is None and o["prev_breadth_fixed"] == 0.0

    assert len(alerts_out) == 1                     # AEM 09-26 saw a healthy board: unchanged
    a = alerts_out[0]
    assert (a["ticker"], a["change"], a["score_before"], a["score_after"]) == ("KGC", "loses_bonus", 71.2, 58.8)
    assert a["method"] == "exact" and a["crosses_65"] is True and a["crosses_acting_bar"] is True
    assert a["lost_themes"] == ["Gold Miners"] and a["paying_themes_fixed"] == []

    assert "FIDELITY — old-rule recompute == stored stage on rescore rows" in err
    assert "listed at scan time' == mi_ep_alerts.in_active_theme: 2 of 2" in err
    assert "constants cross-checked" in err
