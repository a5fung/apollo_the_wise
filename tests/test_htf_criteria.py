"""Spec-fidelity lock for the HTF (High Tight Flag) criteria (#356, 2026-06-27).

Proves the SOURCED criteria are encoded (not the retired n=1 50/60), that the key
gates fire, and that the empty-board path is graceful (no crash) — the things the
incidental `-k flag` tests don't cover. SSoT: docs/setups/htf.md.
"""
from datetime import date, timedelta

from agents.market_intelligence import flag_detector as fd


# ── 1. the sourced CONSTANTS are encoded (catches a regression to 50/60) ─────

def test_sourced_constants():
    assert fd._RUNUP_MIN_RATIO == 1.90          # ≥90% flagpole (was n=1 1.50)
    assert fd._RUNUP_LOOKBACK_DAYS == 40         # ~8wk (was n=1 60)
    assert fd._FLAG_DEPTH_MIN == 0.75            # ≤25% pullback, absolute low
    assert fd._SMA50_WINDOW == 50                # Stage-2 trend filter


# ── 2. empty / missing input is graceful (the empty-board robustness) ────────

def test_empty_rows_graceful():
    out = fd.compute_flag_metrics([], ticker="X")
    assert out["stage"] == "unqualified"
    assert out["reason"] == "no_rows"


# ── 3. end-to-end fixture: base → pole → pivot → flag ────────────────────────

def _row(d, o, h, l, c, v):
    return {"trade_date": d, "open_price": o, "high_price": h,
            "low_price": l, "close": c, "volume": v}


def _htf_rows(runup_ratio=2.0, flag_depth=0.10, vol_spike=True,
              n_base=42, n_pole=20, n_flag=8, base_price=10.0):
    """base (flat low) → pole (ramp to peak) → flag (consolidate). today = last."""
    rows, d0, di = [], date(2026, 1, 1), 0
    for _ in range(n_base):
        rows.append(_row(d0 + timedelta(days=di), base_price, base_price * 1.01,
                         base_price * 0.99, base_price, 1_000_000)); di += 1
    peak = base_price * runup_ratio
    for j in range(n_pole):
        p = base_price + (peak - base_price) * ((j + 1) / n_pole)
        v = 3_000_000 if (vol_spike and j == n_pole // 2) else 1_000_000
        rows.append(_row(d0 + timedelta(days=di), p * 0.99, p * 1.025,
                         p * 0.975, p, v)); di += 1   # ~5% ADR (clears the >4% tradability floor)
    flag_price = peak * (1 - flag_depth)
    for _ in range(n_flag):
        rows.append(_row(d0 + timedelta(days=di), flag_price, flag_price * 1.025,
                         flag_price * 0.975, flag_price, 800_000)); di += 1   # ~5% ADR
    return rows


def test_valid_htf_qualifies():
    out = fd.compute_flag_metrics(_htf_rows(runup_ratio=2.0, flag_depth=0.10),
                                  ticker="HTF", recent_stages=[])
    assert out["stage"] not in ("unqualified", "INVALIDATED"), out["reason"]
    assert out["runup_pct"] >= 0.90


def test_runup_below_90_rejected():
    out = fd.compute_flag_metrics(_htf_rows(runup_ratio=1.6), ticker="LOW", recent_stages=[])
    assert out["stage"] == "unqualified"
    assert "below_90%" in (out["reason"] or "")


def test_deep_flag_rejected_on_absolute_low():
    # a 35% pullback flag breaks the ≤25% absolute-low depth gate
    out = fd.compute_flag_metrics(_htf_rows(runup_ratio=2.0, flag_depth=0.35),
                                  ticker="DEEP", recent_stages=[])
    assert out["stage"] in ("unqualified", "INVALIDATED")


def test_low_adv_rejected():
    # a valid HTF shape but thin volume (<500k ADV) is rejected on the liquidity floor
    rows = _htf_rows(runup_ratio=2.0, flag_depth=0.10)
    for r in rows:
        r["volume"] = 100_000
    out = fd.compute_flag_metrics(rows, ticker="THIN", recent_stages=[])
    assert out["stage"] == "unqualified"
    assert "adv_" in (out["reason"] or "") and "below" in (out["reason"] or "")


def test_low_adr_rejected():
    # a valid HTF shape but a sleepy ~1% daily range (<4% ADR) is rejected on the tradability floor
    rows = _htf_rows(runup_ratio=2.0, flag_depth=0.10)
    for r in rows:
        c = r["close"]
        r["high_price"], r["low_price"] = c * 1.005, c * 0.995
    out = fd.compute_flag_metrics(rows, ticker="SLEEPY", recent_stages=[])
    assert out["stage"] == "unqualified"
    assert "adr_" in (out["reason"] or "") and "below" in (out["reason"] or "")


def test_grinder_no_volume_spike_rejected():
    out = fd.compute_flag_metrics(_htf_rows(runup_ratio=2.0, vol_spike=False),
                                  ticker="GRIND", recent_stages=[])
    assert out["stage"] == "unqualified"
    assert "grinder" in (out["reason"] or "")


def _crash_recovery_rows():
    """NCI-style (operator 6/27): spike to a high → crash → a recovery 'pole' far
    below the prior high. The recovery passes the runup gate (+175%) but is NOT
    Stage-2 (−90% from the 52w high) — must be rejected."""
    rows, d0, di = [], date(2026, 1, 1), 0
    def push(p, v=1_000_000):
        nonlocal di
        rows.append(_row(d0 + timedelta(days=di), p * 0.99, p * 1.025, p * 0.975, p, v)); di += 1  # ~5% ADR
    for _ in range(20): push(10.0)                       # base
    for j in range(10): push(10 + 9 * (j + 1))           # spike to ~100 (the 52w high)
    for j in range(10): push(100 - 9.5 * (j + 1))        # crash to ~5
    for _ in range(40): push(5.0)                        # long low-base — pushes the spike OUT of the 50d window
    for j in range(25):                                  # sharp recent pole 5 -> ~11 (+120%, passes sma50)
        push(5 + (11 - 5) * ((j + 1) / 25), 3_000_000 if j == 12 else 1_000_000)
    for _ in range(8): push(10.5, 800_000)               # flag ~10.5, near the pole top
    return rows


def test_crash_recovery_rejected_stage2():
    out = fd.compute_flag_metrics(_crash_recovery_rows(), ticker="NCI", recent_stages=[])
    assert out["stage"] in ("unqualified", "INVALIDATED"), out["reason"]
    assert "52w_high" in (out["reason"] or "") or "stage2" in (out["reason"] or "")
