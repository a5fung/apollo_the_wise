"""#492 — the RECOVERY evening-brief section: restores the RS-recovery signal #479
orphaned + surfaces the fast crypto-proxy V-recovery the RISING ≥40 floor hides."""
from agents.market_intelligence.briefing import _format_recovery_section


def test_recovery_section_empty_is_omitted():
    assert _format_recovery_section([]) == ""
    assert _format_recovery_section(None or []) == ""


def test_recovery_section_renders_header_names_and_int_rs():
    rows = [
        {"ticker": "MSTR", "sector": None, "rs_1m": 75.7, "rs_3m": 0.8, "rs_6m": 2.7, "rs_composite": 22.0},
        {"ticker": "COIN", "sector": "Financials", "rs_1m": 76.7, "rs_3m": 9.8, "rs_6m": 7.9, "rs_composite": 28.0},
    ]
    out = _format_recovery_section(rows, section_num=5)
    assert "5. RECOVERY" in out
    assert "MSTR" in out and "COIN" in out
    assert "1M 75" in out          # rs_1m rendered as int (75.7 -> 75)
    assert "comp 22" in out
    assert "Financials" in out     # sector tail when present


def test_recovery_section_tolerates_missing_fields():
    # None rs values must not crash (render as "?")
    out = _format_recovery_section([{"ticker": "XYZ"}], section_num=5)
    assert "XYZ" in out and "RECOVERY" in out
