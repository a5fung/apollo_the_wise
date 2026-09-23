"""What I thought was a #631 leak is the documented brand-new-fill path — and one real index bug.

WHY THIS FILE EXISTS AS A RECORD (2026-09-10). Verifying #631 I found HOOD 2026-09-03 carrying
target_r 8 / breakeven 3 — the post-2026-09-06 levels — on a fill that traded three days before the
flip, and reported it as the pin failing. **It is not.** The pin's own comment says so: *"A
brand-new fill (no follows-live row yet) is framed by today's rule, exactly as before."* HOOD was
first recorded after the flip, had no prior follows-live row, and got today's levels — the
documented, tested behaviour.

I tried to "fix" it twice and the existing suite stopped me both times, correctly:

  1. Substituting `rule_eras` constants for the live levels — but #545 made these come from
     per-strategy `mi_strategies` OVERRIDES, and the era stack records the GLOBAL default. A
     strategy can legitimately sit at 8R while the global era says 2R; this suite's own fixture
     (FILL_DAY 2026-08-20, overrides 8R/3) is exactly that shape.
  2. Recording such fills `unscoreable` instead — which contradicts the same design, since an
     override IS the live rule and the counterfactual legitimately asks what today's rule would
     have done on an old fill.

Three failures from tests I did not write is what settled it. Kept as a test rather than a comment
so the next reader does not re-derive the same wrong conclusion from the same row.

⚠ The one REAL bug the chase turned up is pinned below: the missing-inputs branch read
`arm[4]` (trail_rule, a truthy string) where it meant `arm[5]` (follows_live_rule).
"""
from datetime import date

from agents.market_intelligence.rule_eras import PARTIAL_8R_DATE, exit_rules_as_of


def test_the_era_stack_is_not_the_live_rule():
    """The premise that made my "fix" wrong: era constants are the GLOBAL default, and per-strategy
    overrides can differ. Anything reconstructing a fill's framing must not confuse the two."""
    pre = exit_rules_as_of(date(2026, 9, 3), "magna53")
    post = exit_rules_as_of(date(2026, 9, 8), "magna53")
    assert pre["breakeven_at_r"] is None and post["breakeven_at_r"] is not None
    assert pre["intraday_partial_r"] != post["intraday_partial_r"]
    assert date(2026, 9, 3) < PARTIAL_8R_DATE <= date(2026, 9, 8)


def test_a_brand_new_fill_using_todays_rule_is_intended_not_a_leak():
    """Pin the DESIGN, so the next reader does not file HOOD as a bug again."""
    import inspect

    from agents.market_intelligence import live_fill_counterfactuals as lfc
    src = inspect.getsource(lfc)
    assert "A brand-new fill" in src and "is framed by today" in src, (
        "the documented intent this file exists to record has been edited away")


def test_follows_live_is_read_from_the_right_index():
    """THE REAL BUG. arm[5] is follows_live_rule; arm[4] is trail_rule, and a non-empty trail rule
    is truthy — so any trailing arm read as follows-live regardless of its flag. Harmless while
    every trailing arm happens to be follows-live, wrong the moment one is not."""
    import inspect

    from agents.market_intelligence import live_fill_counterfactuals as lfc
    src = inspect.getsource(lfc)
    assert "follows_live = arm[4]" not in src, "the truthy-trail_rule bug is back"
    for a in lfc.ARMS:
        assert isinstance(a[5], bool), f"{a[0]}: follows_live_rule is not at index 5"
        assert isinstance(a[4], (str, type(None))), f"{a[0]}: arm[4] is not the trail rule"
