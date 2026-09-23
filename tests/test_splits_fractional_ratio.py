"""Fund share-class reorgs must not be ingested as splits.

2026-07-24: 21 of that day's 26 `split_detected` events were Neuberger Berman
mutual-fund share classes (NBGAX/NRACX/NSNRX/…) with fractional ratios like
`1:0.9623`. `int()` truncated the second leg to 0, storing degenerate rows, and
the event volume drove a 6.5x `split_detected` delta into the cooldowns_per_day
L2 anomaly.
"""
import pytest

from agents.market_intelligence.splits_ingest import _as_split_legs


@pytest.mark.parametrize("raw_from, raw_to, expected", [
    # Real share splits — pass through as integers.
    (1, 5, (1, 5)),
    (30, 1, (30, 1)),
    (50, 51, (50, 51)),
    ("2", "1", (2, 1)),
    (1.0, 2.0, (1, 2)),
])
def test_real_splits_parse(raw_from, raw_to, expected):
    assert _as_split_legs(raw_from, raw_to) == expected


@pytest.mark.parametrize("raw_from, raw_to", [
    (1, 0.9623),    # NBGAX — int() used to truncate this leg to 0
    (1, 0.9067),    # NINCX
    (1, 1.0127518490181076),  # REMYF
    (1, 1.0045),    # NRAEX — int() used to collapse this to a 1:1 no-op
    (0.5, 1),       # fractional first leg
])
def test_fund_reorg_ratios_rejected(raw_from, raw_to):
    assert _as_split_legs(raw_from, raw_to) == (None, None)


@pytest.mark.parametrize("raw_from, raw_to", [
    (None, 1), (1, None), ("", 1), ("abc", "1"),
    (0, 1), (1, 0), (-1, 2),      # degenerate/nonsensical legs
])
def test_malformed_legs_rejected(raw_from, raw_to):
    assert _as_split_legs(raw_from, raw_to) == (None, None)
