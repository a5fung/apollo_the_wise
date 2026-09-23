"""#493 — the CRYPTO vs MARKET evening-brief pulse (slice 1 of the Market Strength Map #494):
'is BTC/ETH holding up while the equity market corrects?' rendered as a compact cross-asset block."""
from agents.market_intelligence.briefing import _format_crypto_pulse_section


def test_pulse_empty_is_omitted():
    assert _format_crypto_pulse_section({}) == ""
    assert _format_crypto_pulse_section({"crypto": []}) == ""


def test_pulse_leading_verdict_and_numbers():
    pulse = {
        "crypto": [{"sym": "BTC", "r2": 1.9, "r4": 2.0},
                   {"sym": "ETH", "r2": 5.7, "r4": 10.1},
                   {"sym": "SOL", "r2": -5.2, "r4": 8.0}],
        "market": [{"sym": "QQQ", "r2": -3.7, "r4": -5.7},
                   {"sym": "SPY", "r2": -1.2, "r4": -0.3},
                   {"sym": "IWM", "r2": -2.2, "r4": -2.0}],
        "verdict": "LEADING", "lead_4w": 11.8,
    }
    out = _format_crypto_pulse_section(pulse)
    assert "CRYPTO vs MARKET" in out
    assert "LEADING" in out and "🟢" in out
    assert "ETH +10.1" in out and "QQQ -5.7" in out   # crypto up, market down, both shown


def test_pulse_tolerates_none_values():
    pulse = {"crypto": [{"sym": "BTC", "r2": None, "r4": None}],
             "market": [{"sym": "QQQ", "r2": None, "r4": None}],
             "verdict": "MIXED", "lead_4w": None}
    out = _format_crypto_pulse_section(pulse)
    assert "CRYPTO vs MARKET" in out and "n/a" in out   # never crashes on missing data
