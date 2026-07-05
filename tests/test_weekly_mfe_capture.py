"""W3 winner-harvest KPI (#306) — weekly-review MFE-capture section.

Pins the deterministic formatter: omitted until the cohort exists, renders
the cumulative capture number against the v2.0 tier-one bar, lists the
window's new closes. The aggregator itself is DB-bound (exercised in prod);
these tests freeze the render contract so a metrics-shape drift can't
silently blank THE management KPI out of the Sunday digest.
"""
from agents.market_intelligence.system_review import _format_mfe_capture_section


def test_empty_dict_omits_section():
    assert _format_mfe_capture_section({}) == ""


def test_zero_cohort_omits_section():
    # No misleading "0%" line before any partial-taken trade has closed.
    assert _format_mfe_capture_section({"n": 0}) == ""


def test_renders_cumulative_kpi_line():
    data = {
        "n": 10,
        "mfe_dollars": 32775,
        "kept_dollars": 5942,
        "capture_pct": 18,
        "bar_pct": 50,
        "window_closes": [],
    }
    out = _format_mfe_capture_section(data)
    assert "18% cumulative" in out
    assert "$+5,942 kept" in out
    assert "$32,775 peak" in out
    assert "n=10 partial-taken closed" in out
    assert "bar >50%" in out
    # Single-line section when nothing closed this window.
    assert "\n" not in out


def test_renders_window_closes_as_bullets():
    data = {
        "n": 11,
        "mfe_dollars": 40000,
        "kept_dollars": 8000,
        "capture_pct": 20,
        "bar_pct": 50,
        "window_closes": [
            {"ticker": "CRSR", "capture_pct": 15, "kept": 1391, "mfe": 9545},
            {"ticker": "SMCI", "capture_pct": -27, "kept": -639, "mfe": 2327},
        ],
    }
    out = _format_mfe_capture_section(data)
    lines = out.split("\n")
    assert len(lines) == 3
    assert "`CRSR` closed this week: 15% ($+1,391 of $9,545)" in lines[1]
    # A partial-taken trade that round-trips to a LOSS renders negative capture.
    assert "`SMCI` closed this week: -27% ($-639 of $2,327)" in lines[2]
