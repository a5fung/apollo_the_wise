"""Regression tests for _check_description_quality (#125, 2026-05-26).

Validates three rules against the corpus of 26 two-member themes that
reached Accelerating/Mainstream in last 30d. Bug class: Sonnet-generated
descriptions sometimes hallucinate (concat tickers, name wrong stocks,
or produce empty descriptions) — but downstream stage advancement
doesn't validate.

Three rules per advisor 2026-05-26 review:
  A. Ticker concat ("LOVE SEAT" / "WLTH LIFE" class)
  B. At-least-one-member-mentioned (catches description-tickers
     mismatch — e.g. CLMT/CF theme described in terms of LYB/BW/DOW)
  C. Empty/whitespace description block
"""
from agents.market_intelligence.theme_engine import _check_description_quality


# ── Rule A: ticker concat (the original bug — LOVE SEAT) ─────────────

def test_concat_love_seat_blocked():
    """Original 2026-05-26 bug: 'LOVE SEAT is likely moving...'"""
    ok, reason = _check_description_quality(
        "Consumer Discretionary Home Furnishings Rebound",
        ["LOVE", "SEAT"],
        "LOVE SEAT is likely moving on the broader rerating in software/SaaS names",
    )
    assert not ok
    assert reason.startswith("ticker_concat")
    assert "LOVE" in reason and "SEAT" in reason


def test_concat_wlth_life_blocked():
    """Sister bug from corpus: 'WLTH LIFE is moving higher this week...'"""
    ok, reason = _check_description_quality(
        "Robo-Advisor & AI-Driven Wealth Management Platforms",
        ["WLTH", "LIFE"],
        "WLTH LIFE is moving higher this week mainly on momentum and speculative buying",
    )
    assert not ok
    assert reason.startswith("ticker_concat")


def test_legit_parenthetical_passes():
    """'Datadog (DDOG) and Fortinet (FTNT)' shouldn't false-positive on concat —
    'and' between symbols means the rule won't match."""
    ok, _ = _check_description_quality(
        "Cybersecurity",
        ["DDOG", "FTNT"],
        "Datadog (DDOG) is being driven higher by a strong post-earnings reaction. "
        "Fortinet (FTNT) is moving up as part of the broader cybersecurity rally.",
    )
    assert ok


# ── Rule B: at-least-one-member-mentioned ────────────────────────────

def test_no_member_mentioned_blocked():
    """Corpus: theme tickers {CLMT, CF} but description talks about LYB/BW/DOW."""
    ok, reason = _check_description_quality(
        "Nitrogen Fertilizer & Crop Nutrient Producers",
        ["CLMT", "CF"],
        "LYB is getting a lift from a Deutsche Bank price-target hike. "
        "BW is benefiting from strong LPG shipping rates. "
        "DOW is trading higher on the same 'early-cycle' chemical recovery theme.",
    )
    assert not ok
    assert reason == "no_member_ticker_mentioned"


def test_one_member_mentioned_passes():
    """Description mentioning at least one member ticker passes — even if it
    also references peer tickers. 'CRWD and PANW' is legit peer context."""
    ok, _ = _check_description_quality(
        "Cybersecurity",
        ["DDOG", "FTNT"],
        "DDOG benefits from rotation back into cybersec — vs CRWD and PANW.",
    )
    assert ok


# ── Rule C: empty / whitespace description ───────────────────────────

def test_empty_description_blocked():
    ok, reason = _check_description_quality("Some Theme", ["AAA", "BBB"], "")
    assert not ok
    assert reason == "empty_description"


def test_none_description_blocked():
    ok, reason = _check_description_quality("Some Theme", ["AAA", "BBB"], None)
    assert not ok
    assert reason == "empty_description"


def test_whitespace_only_description_blocked():
    ok, reason = _check_description_quality("Some Theme", ["AAA", "BBB"], "   \n  \t")
    assert not ok
    assert reason == "empty_description"


# ── Legitimate cases from corpus ─────────────────────────────────────

def test_riot_hut_crypto_legit():
    """Corpus row 1: clearly legit — both tickers mentioned, no concat."""
    ok, _ = _check_description_quality(
        "Crypto Asset Recovery",
        ["RIOT", "HUT"],
        "Riot Platforms (RIOT) is being driven by strong Q1 2026 results. "
        "Hut 8 (HUT) is benefiting from Bitcoin trading near record highs.",
    )
    assert ok


def test_wolf_stm_silicon_carbide_legit():
    """Corpus: 'WOLF is ripping higher... STM is riding the same...'"""
    ok, _ = _check_description_quality(
        "Silicon Carbide Power Semiconductors & EV Infrastructure",
        ["WOLF", "STM"],
        "WOLF is ripping higher on renewed excitement around its silicon carbide power chips. "
        "STM is riding the same silicon-carbide and power-semiconductor theme.",
    )
    assert ok


# ── Edge cases ───────────────────────────────────────────────────────

def test_single_member_with_ticker_in_description():
    """Sub-2 themes only check at-least-one-mentioned. Pass when ticker present."""
    ok, _ = _check_description_quality("Theme", ["AAA"], "AAA is up on news")
    assert ok


def test_single_member_no_ticker_in_description():
    ok, reason = _check_description_quality("Theme", ["AAA"], "Generic prose")
    assert not ok
    assert reason == "no_member_ticker_mentioned"


def test_concat_only_fires_for_distinct_tickers():
    """If a member ticker appears twice (e.g. 'AAA and AAA again'), don't
    flag as concat — only flag distinct ticker pairs."""
    ok, _ = _check_description_quality(
        "Theme", ["AAA", "BBB"],
        "AAA is moving and BBB is also moving. AAA continues to lead.",
    )
    assert ok
