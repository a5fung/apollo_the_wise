"""FAMILY A — "consolidation plays post a runup" (ADR 0013, signed §2) pure-core tests.

Pins the Phase-1 SHADOW RECORDER (`evaluate_consolidation` + `consolidation_shapes` /
`consolidation_telemetry`):
  1. the runup CANARY gate — ≥1.15 MAX/MIN over the anchor-ending window is IN, exactly 1.15
     is on-border IN (the COO case), a flat no-runup series is None;
  2. the ABSOLUTE anchor — runup_ratio/runup_high are anchored to the PEAK, invariant to how
     many trailing coil bars are appended (the property that makes the (ticker, anchor_date)
     key scan-stable: appending tomorrow's coil bar must NOT move the anchor metrics);
  3. state classification (coiled / post_runup / aged);
  4. Family-A shapes never emit the gap-anchored `gap_low_undercut` (that's Family B / the
     deferred U&R entry mode), and telemetry stays JSON/SQL-native.
"""
import json
from pathlib import Path

import agents.market_intelligence.anticipation as de

# Two REAL §2 universe snapshots (6/15 → 6/16, live DB) — the 7 anchor-drift names the probe
# exposed. The carry-forward test runs the REAL select_consolidation_keys on real data (no deploy).
_SNAP = Path(__file__).resolve().parent.parent / "scripts" / "_familyA_drift_snapshots.json"
_DRIFT = ["ATKR", "BSX", "IMVT", "KNSA", "ROL", "SBRA", "UHS"]


def _load_snap():
    return json.loads(_SNAP.read_text(encoding="utf-8"))


def _seed_existing(snap_rows):
    """Existing non-aged rows as if recorded on scan_a (one anchor per ticker on first seed)."""
    return {r["ticker"]: [{"anchor_date": r["anchor_date"], "runup_high": r["runup_high"],
                           "dvol_med": r["dvol_med"]}] for r in snap_rows}


def _runup_then_coil(peak_idx=14, n_coil=8, *, lo=10.0, peak=11.6, coil_c=11.4,
                     tight=True, lead=5):
    """A clean runup leg into `peak_idx` (the 10-bar window ending at the peak rises lo→peak)
    followed by `n_coil` consolidation bars below the peak. `tight` → dead-flat coil closes
    (a tight-close series); else a >0.4% wiggle (breaks the streak). Distinct h/l so ATR≠0."""
    bars = []
    # lead-in bars below the runup window (don't affect the [peak-9, peak] window)
    for i in range(lead):
        bars.append({"date": f"d{i:04d}", "o": 9.5, "h": 9.6, "l": 9.4, "c": 9.5, "v": 1e6})
    # the runup window: rise lo → peak across the 10 bars ending at peak_idx
    win = peak_idx - lead + 1
    for k in range(win):
        c = lo + (peak - lo) * k / (win - 1)
        bars.append({"date": f"d{lead + k:04d}", "o": c, "h": c + 0.15, "l": c - 0.12,
                     "c": round(c, 4), "v": 2e6})
    # the coil: below the peak, tight or wiggly
    for j in range(n_coil):
        c = coil_c if tight else (coil_c + (0.06 if j % 2 else -0.06))
        idx = peak_idx + 1 + j
        bars.append({"date": f"d{idx:04d}", "o": c, "h": c + 0.10, "l": c - 0.10,
                     "c": round(c, 4), "v": 8e5})
    return bars, f"d{peak_idx:04d}"


# ── 1. runup canary gate ──────────────────────────────────────────────────────
def test_runup_in_when_leg_exceeds_115():
    bars, anchor = _runup_then_coil(peak=11.6)            # 11.6/10.0 = 1.16 ≥ 1.15
    row = de.evaluate_consolidation(bars, anchor)
    assert row is not None and row["runup_ratio"] >= 1.15
    assert row["runup_high"] == 11.6 and row["anchor_date"] == anchor


def test_runup_on_border_exactly_115_is_in():
    bars, anchor = _runup_then_coil(peak=11.5)            # 11.5/10.0 = 1.15 exactly → IN (COO canary)
    row = de.evaluate_consolidation(bars, anchor)
    assert row is not None and abs(row["runup_ratio"] - 1.15) < 1e-9


def test_no_runup_returns_none():
    # flat series, no ≥15% leg → below the runup floor → dropped
    bars = [{"date": f"d{i:04d}", "o": 10.0, "h": 10.05, "l": 9.95, "c": 10.0, "v": 1e6}
            for i in range(30)]
    assert de.evaluate_consolidation(bars, "d0020") is None


def test_anchor_not_in_bars_returns_none():
    bars, _ = _runup_then_coil()
    assert de.evaluate_consolidation(bars, "1999-01-01") is None


# ── 2. absolute-anchor invariance (the scan-stable-key property) ──────────────
def test_anchor_metrics_invariant_to_trailing_coil_bars():
    # The (ticker, anchor_date) key is scan-stable only if the anchor's runup metrics do NOT
    # shift as new coil bars land. Append one more flat coil bar (tomorrow's scan) → runup_ratio,
    # runup_high, and the anchor must be IDENTICAL; only coil_days advances by 1.
    bars, anchor = _runup_then_coil(n_coil=6)
    r1 = de.evaluate_consolidation(bars, anchor)
    last = bars[-1]
    bars2 = bars + [{**last, "date": "d9999"}]            # one more day of the same coil
    r2 = de.evaluate_consolidation(bars2, anchor)
    assert r2["anchor_date"] == r1["anchor_date"]
    assert r2["runup_ratio"] == r1["runup_ratio"]
    assert r2["runup_high"] == r1["runup_high"]
    assert r2["coil_days"] == r1["coil_days"] + 1


# ── 3. state classification ───────────────────────────────────────────────────
def test_state_coiled_on_tight_close_series():
    bars, anchor = _runup_then_coil(n_coil=8, tight=True)
    row = de.evaluate_consolidation(bars, anchor)
    assert row["tight_close_streak"] >= de.TIGHT_SERIES_MIN
    assert row["state"] == "coiled"


def test_state_post_runup_when_not_tight():
    bars, anchor = _runup_then_coil(n_coil=8, tight=False)
    row = de.evaluate_consolidation(bars, anchor)
    assert row["state"] in ("post_runup", "coiled")       # wiggly tail → no tight series
    if not row["fresh_tightening"] and row["tight_close_streak"] < de.TIGHT_SERIES_MIN:
        assert row["state"] == "post_runup"


def test_state_aged_when_coil_exceeds_age_out():
    # anchor far back so coil_days > CONSOL_AGE_OUT
    n_coil = de.CONSOL_AGE_OUT + 4
    bars, anchor = _runup_then_coil(peak_idx=12, n_coil=n_coil, tight=True)
    row = de.evaluate_consolidation(bars, anchor)
    assert row["coil_days"] > de.CONSOL_AGE_OUT and row["state"] == "aged"


# ── 4. Family-A shapes + native telemetry types ───────────────────────────────
def test_consolidation_shapes_never_gap_low_undercut():
    bars, _ = _runup_then_coil(n_coil=10, tight=True)
    _, shapes = de.consolidation_shapes(bars, len(bars) - 1)
    assert "gap_low_undercut" not in shapes               # the gap-anchored shape is Family B only
    assert "low_vol_rest" in shapes                       # tight + quiet coil → resting


def test_consolidation_telemetry_native_types():
    bars, _ = _runup_then_coil(n_coil=8)
    tel = de.consolidation_telemetry(bars, len(bars) - 1, anchor_idx=14)
    assert set(tel) == {"pullback_shape", "pullback_shapes", "fresh_tightening",
                        "fresh_2bar_tr_pct", "atr14_pct", "tight_close_streak"}
    assert isinstance(tel["fresh_tightening"], bool)
    assert isinstance(tel["tight_close_streak"], int)
    for k in ("fresh_2bar_tr_pct", "atr14_pct"):
        assert tel[k] is None or isinstance(tel[k], float)


# ── 5. carry-forward on the REAL 6/15→6/16 drift (the un-pause gate, advisor 6/17) ───────────
def test_carry_forward_absorbs_real_615_to_616_drift():
    # The 7 names whose rolling-window anchor drifted off the aging-out 2026-05-26 peak. Seeded
    # from scan_a, select_consolidation_keys MUST resolve each to its scan_a anchor (carried) —
    # NOT the drifted scan_b anchor — and to exactly ONE key (no duplicate row for the same leg).
    d = _load_snap()
    a = {r["ticker"]: r for r in d["a"]}
    b = {r["ticker"]: r for r in d["b"]}
    keys = de.select_consolidation_keys(d["b"], _seed_existing(d["a"]))
    by_ticker = {}
    for k in keys:
        by_ticker.setdefault(k["ticker"], []).append(k["anchor_date"])
    for t in _DRIFT:
        assert t in a and t in b and a[t]["anchor_date"] != b[t]["anchor_date"]   # really drifted
        assert b[t]["runup_high"] <= a[t]["runup_high"]            # lesser peak = same leg, not new
        ancs = by_ticker.get(t, [])
        assert ancs == [a[t]["anchor_date"]]                       # carried original, exactly once


def test_new_higher_high_seeds_a_new_leg():
    # A scan_b name whose runup_high EXCEEDS its scan_a anchor = a genuinely new leg → its scan_b
    # anchor is seeded (the only case where the universe anchor wins over the carried one).
    d = _load_snap()
    a = {r["ticker"]: r for r in d["a"]}
    keyset = {(k["ticker"], k["anchor_date"])
              for k in de.select_consolidation_keys(d["b"], _seed_existing(d["a"]))}
    checked = 0
    for r in d["b"]:
        t = r["ticker"]
        if (t in a and r["anchor_date"] != a[t]["anchor_date"]
                and (r["runup_high"] or 0) > (a[t]["runup_high"] or 0)):
            assert (t, r["anchor_date"]) in keyset
            checked += 1
    assert checked >= 1                                            # fixture has real new-high legs


def test_brand_new_ticker_seeded_with_universe_anchor():
    d = _load_snap()
    a_tickers = {r["ticker"] for r in d["a"]}
    keyset = {(k["ticker"], k["anchor_date"])
              for k in de.select_consolidation_keys(d["b"], _seed_existing(d["a"]))}
    new_only = [r for r in d["b"] if r["ticker"] not in a_tickers]
    assert new_only                                                # 262 > 232 → genuinely-new names
    for r in new_only:
        assert (r["ticker"], r["anchor_date"]) in keyset


# ── shared plain-words row formats: the SINGLE source for /anticipation + the daily Family-A
#    digest (operator 6/18 — glanceable, no acronym soup; the two must not drift again). ──
def test_consolidation_row_plain_words():
    # 1.70 runup, deeply contracted (rmv≤15) + a fresh tightening
    row = de.format_consolidation_row("LUNL", 1.70, 14, rmv_5d=0, fresh_tightening=True)
    assert row == "  `LUNL ` +70% · coiling 14d · very tight · tightening↓"
    # loose (rmv>40) → "loose", no tightening flag
    assert de.format_consolidation_row("TENB", 1.26, 12, rmv_5d=65) == \
        "  `TENB ` +26% · coiling 12d · loose"


def test_consolidation_row_post_runup_omits_tightness():
    # post-runup (not coiled): the tightness word reads as a contradiction there → omit it, show
    # only runup + age (operator readability, 6/18). rmv is ignored in this mode.
    assert de.format_consolidation_row("FUTU", 1.17, 15, rmv_5d=0, coiled=False) == \
        "  `FUTU ` +17% · 15d since peak"


def test_consolidation_row_is_none_safe():
    # asyncpg Decimals / missing fields must not crash the digest or the command.
    assert de.format_consolidation_row("XYZ", None, None) == "  `XYZ  ` ?% · coiling 0d"
    assert de.format_consolidation_row("XYZ", None, None, coiled=False) == "  `XYZ  ` ?% · 0d since peak"


def test_entry_fired_row():
    assert de.format_entry_fired_row("PRIM", 101.30, 100.09, "9m") == \
        "  `PRIM ` buy 101.30 · stop 100.09 (-1.2%) · 9M"
    # family_a origin → no tag
    assert de.format_entry_fired_row("X", 10.0, 9.5, "family_a") == \
        "  `X    ` buy 10.00 · stop 9.50 (-5.0%)"


def test_entry_settled_row():
    assert de.format_entry_settled_row("PRIM", "capture", 3.0) == "  `PRIM ` ✓ captured +3.0R"
    assert de.format_entry_settled_row("X", "stop", -1.0) == "  `X    ` ✗ stopped -1.0R"
    assert de.format_entry_settled_row("X", "open", 0.4) == "  `X    ` ○ timed out +0.4R"
    # None realized_r (early-definitive settle) → no R suffix, still labeled
    assert de.format_entry_settled_row("X", "capture", None) == "  `X    ` ✓ captured"
