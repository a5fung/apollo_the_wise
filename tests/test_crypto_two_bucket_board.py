"""`/crypto` renders BIG and SMALL cap boards separately (operator 2026-08-02).

*"perhaps we can have two buckets, big and small caps."*

A single flat board ranked on rs_overall is **structurally** dominated by the small end: the
universe is 202 micro + 66 mid against 12 large + 6 mega. The first live render returned a top 8 of
all micro-caps, and ETH — the move the operator was actually watching, holding 1-month RS of 84-91
for a week — never appeared.

Deliberate choices these tests pin:
  · rs_overall stays the ranking metric INSIDE each side. The question is "what is strong", and a
    coin ranked #1 of 202 is genuinely stronger than one ranked #1 of 6. Splitting the BOARD fixes
    visibility without redefining strength.
  · `unknown`-bucket coins are excluded from BOTH sides rather than dumped into one — an
    unclassified coin is not evidence of size.
  · The category-filtered path is UNCHANGED; only the default board splits.
"""
import asyncio
from unittest.mock import AsyncMock

import agents.market_intelligence.crypto.briefing as cb


def _row(sym, rs, bucket, b_rs=50.0):
    return {"symbol": sym, "rs_overall": rs, "rs_in_bucket": b_rs, "mcap_bucket": bucket}


def _wire(monkeypatch, big, small, category_rows=None):
    monkeypatch.setattr(cb, "CRYPTO_RS_ENABLED", True)

    class _Conn:
        async def fetchval(self, *a, **k):
            return "2026-08-01"

        async def fetchrow(self, *a, **k):
            return {"dominance_pct": 56.32}

        async def fetch(self, sql, *args):
            if category_rows is not None:
                return category_rows
            buckets = args[1]
            return big if "mega" in buckets else small

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self): return _Acq()

    monkeypatch.setattr(cb, "get_pool", AsyncMock(return_value=_Pool()))


def _run(**kw):
    return asyncio.run(cb.render_crypto_top(**kw))


def test_both_sections_render(monkeypatch):
    _wire(monkeypatch, [_row("ETH", 65.0, "mega")], [_row("AKE", 100.0, "micro")])
    out = _run()
    assert "Big caps" in out and "Small caps" in out


def test_a_big_cap_appears_even_when_small_caps_outrank_it(monkeypatch):
    """THE point. On a flat board ETH at 65.0 is buried under micro-caps at ~100."""
    _wire(monkeypatch, [_row("ETH", 65.0, "mega")],
          [_row(s, 99.0, "micro") for s in ("AKE", "KAITO", "UB", "GRX")])
    out = _run()
    assert "ETH" in out
    assert out.index("Big caps") < out.index("ETH") < out.index("Small caps")


def test_ranking_inside_a_side_is_rs_overall_not_rs_in_bucket(monkeypatch):
    """A coin #1 of 202 is genuinely stronger than one #1 of 6 — do not flatten that away."""
    _wire(monkeypatch, [], [_row("HI", 90.0, "micro", b_rs=10.0),
                            _row("LO", 20.0, "micro", b_rs=99.0)])
    out = _run()
    assert out.index("HI") < out.index("LO")


def test_the_note_warns_the_two_sides_are_not_size_comparable(monkeypatch):
    _wire(monkeypatch, [_row("ETH", 65.0, "mega")], [_row("AKE", 100.0, "micro")])
    assert "not comparable" in _run()


def test_an_empty_side_says_none_rather_than_vanishing(monkeypatch):
    """A missing section would read as 'no big caps are strong' instead of 'no data'."""
    _wire(monkeypatch, [], [_row("AKE", 100.0, "micro")])
    out = _run()
    assert "Big caps" in out and "_none_" in out


def test_category_filter_still_renders_ONE_table(monkeypatch):
    _wire(monkeypatch, [], [], category_rows=[_row("SOL", 88.0, "large")])
    out = _run(category="ai")
    assert "Big caps" not in out and "SOL" in out


def test_shadow_mode_still_short_circuits(monkeypatch):
    monkeypatch.setattr(cb, "CRYPTO_RS_ENABLED", False)
    assert _run() == cb.SHADOW_MESSAGE
