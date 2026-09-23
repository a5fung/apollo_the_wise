"""#663 — the diagnostic must work the FIRST time it fires, so it is tested now.

A failure reporter that has never been exercised is broken on the day you need it, and this one
exists precisely because there may be no second chance: the 2026-09-14 flake has not reproduced
in 60 runs. Every test here drives the real helper with the real shapes the EP scan produces.
"""
from __future__ import annotations

import pytest

from tests._byte_identity import assert_byte_identical, canon, differences


def test_identical_results_pass_silently():
    rows = [{"ticker": "AAA", "score_tier": "HIGH", "catalyst_type": None}]
    assert_byte_identical(rows, [dict(rows[0])], "results")


def test_a_MISSING_KEY_is_reported_first_and_names_the_key():
    """The confirmed bug class: a classifier raises, the code assigns nothing instead of None,
    and the key vanishes from one run. This is what 09-14 needed to tell us and could not."""
    a = [{"ticker": "AAA", "score_tier": "HIGH", "catalyst_type": None}]
    b = [{"ticker": "AAA", "score_tier": "HIGH"}]                      # key dropped
    with pytest.raises(AssertionError) as e:
        assert_byte_identical(a, b, "results")
    msg = str(e.value)
    assert "KEY PRESENT ONLY IN A" in msg
    assert "catalyst_type" in msg
    assert msg.index("KEY PRESENT ONLY IN A") < len(msg)


def test_key_presence_is_reported_BEFORE_a_value_difference():
    """Ordering is the design, not cosmetics — the shape difference is the one that has ever
    actually bitten, so it must not be buried under value noise."""
    a = [{"ticker": "AAA", "score": 1, "catalyst_type": None}]
    b = [{"ticker": "AAA", "score": 2}]
    lines = differences(a, b)
    assert any("KEY PRESENT ONLY IN A" in l for l in lines)
    first_key = next(i for i, l in enumerate(lines) if l.startswith("KEY PRESENT"))
    first_val = next(i for i, l in enumerate(lines) if l.startswith("VALUE"))
    assert first_key < first_val, f"value difference reported before the missing key: {lines}"


def test_a_value_difference_names_the_path_and_both_sides():
    a = [{"ticker": "AAA", "score_tier": "HIGH"}]
    b = [{"ticker": "AAA", "score_tier": "MODERATE"}]
    with pytest.raises(AssertionError) as e:
        assert_byte_identical(a, b, "results")
    msg = str(e.value)
    assert "[0].score_tier" in msg and "HIGH" in msg and "MODERATE" in msg


def test_a_row_count_difference_is_reported():
    with pytest.raises(AssertionError) as e:
        assert_byte_identical([{"t": "A"}], [{"t": "A"}, {"t": "B"}], "scan_log")
    assert "LENGTH" in str(e.value) and "1 in A" in str(e.value)


def test_nested_paths_are_readable():
    a = [{"ticker": "AAA", "judge": {"grade": "A", "axes": [1, 2, 3]}}]
    b = [{"ticker": "AAA", "judge": {"grade": "A", "axes": [1, 9, 3]}}]
    with pytest.raises(AssertionError) as e:
        assert_byte_identical(a, b, "results")
    assert "[0].judge.axes[1]" in str(e.value)


def test_the_report_is_bounded_so_a_wide_diff_stays_readable():
    """A 50-row scan that differs everywhere must not print 50 KB — that is the failure mode
    being fixed, and reproducing it with nicer words would be no better."""
    a = [{"t": f"T{i}", "v": i} for i in range(50)]
    b = [{"t": f"T{i}", "v": i + 1} for i in range(50)]
    with pytest.raises(AssertionError) as e:
        assert_byte_identical(a, b, "results")
    msg = str(e.value)
    assert "and 38 more" in msg, msg[-200:]
    assert len(msg) < 3000, f"report is {len(msg)} chars — unreadable again"


def test_equality_is_unchanged_so_this_cannot_make_a_failing_guard_pass():
    """The safety property. The helper decides equality with the SAME `canon` the old assertion
    used; only the message is new. If this ever diverges, a real regression could slip through
    a guard that now reports nicely and passes wrongly."""
    a = [{"ticker": "AAA", "n": 1}]
    for b, same in (([{"ticker": "AAA", "n": 1}], True),
                    ([{"n": 1, "ticker": "AAA"}], True),      # key order is not a difference
                    ([{"ticker": "AAA", "n": 2}], False),
                    ([{"ticker": "AAA"}], False)):
        assert (canon(a) == canon(b)) is same
        if same:
            assert_byte_identical(a, b, "results")
        else:
            with pytest.raises(AssertionError):
                assert_byte_identical(a, b, "results")


def test_a_serialisation_only_difference_is_called_out_rather_than_printing_nothing():
    """If the canonical strings differ but the structural walk finds nothing, that is itself a
    finding — an empty report would read as 'no reason', which is where this started."""
    class Odd:
        def __init__(self, s): self.s = s
        def __repr__(self): return self.s
        def __eq__(self, other): return isinstance(other, Odd)   # equal, but str() differs
        def __hash__(self): return 0
    a, b = [Odd("x")], [Odd("y")]
    assert canon(a) != canon(b)
    assert differences(a, b) == []
    with pytest.raises(AssertionError) as e:
        assert_byte_identical(a, b, "results")
    assert "serialisation, not content" in str(e.value)
