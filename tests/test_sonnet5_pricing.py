"""claude-sonnet-5 costs $2/$10 per million tokens. That is its STANDARD rate.

TWO MIS-PRICINGS, IN OPPOSITE DIRECTIONS, ON THE SAME MODEL:

1. 2026-08-07 — sonnet-5 was missing from `PRICING_PER_MTOK` and fell through to the sonnet-TIER
   $3/$15, so every call was recorded at 150% of its cost. It was 24.7% of the 7-day bill and
   $1.84 of $22.30 was pure accounting error, while the operator was asking *"spend increase is
   concerning, it keeps going up but you keep saying it's one off or normal."* Part of the rise
   was not spend at all.

2. 2026-09-01 — the fix for (1) encoded $2/$10 as INTRODUCTORY pricing "through 2026-08-31" with
   a date check that would flip itself to $3/$15 on 09-01. It flipped. **Anthropic then cancelled
   the increase and made $2/$10 permanent**, so the check fired on a price change that never
   happened and overstated a day of spend by 50% — and the cost watchdog alarmed on our own
   arithmetic. I chased it as a real cost ramp before the operator produced the announcement.

The date check is GONE rather than re-dated: there is no second rate to switch to, and a
self-flipping mechanism whose destination no longer exists is worse than a plain number. What
survives from (1) is the reason sonnet-5 has an explicit table entry at all.
"""
from shared import llm_models as m


def test_sonnet_5_costs_two_and_ten():
    """MUTATION TARGET: restoring the $3/$15 tier rate, in the table or via a fallback."""
    assert m.pricing_for(m.SONNET_5) == {"input": 2.00, "output": 10.00}


def test_no_date_check_can_change_the_price_again():
    """The 09-01 error in one assertion: pricing must not depend on what day it is. A dated
    branch here fired on a cancelled increase and cost us a day of wrong numbers plus a false
    alarm; nothing about a rate table should be time-varying without an announcement behind it."""
    import inspect

    src = inspect.getsource(m.pricing_for)
    assert "intro" not in src.lower(), "a dated intro branch is back in pricing_for"
    assert "et_today" not in src, "pricing_for must not depend on the date"


def test_sonnet_5_is_priced_explicitly_not_by_the_tier_fallback():
    """The 2026-08-07 error. The fallback logs a WARNING on every call precisely so a missing
    rate cannot stay silent — it logged for days and nobody read it. An explicit entry is the
    fix; the warning was only ever the smoke alarm."""
    assert m.SONNET_5 in m.PRICING_PER_MTOK, (
        "claude-sonnet-5 is back to being priced by the tier fallback")
    assert m.PRICING_PER_MTOK[m.SONNET_5] == {"input": 2.00, "output": 10.00}


def test_llm_models_still_uses_the_canonical_ET_helper():
    """Kept from the intro-window suite even though pricing no longer reads the date: CLAUDE.md
    names ONE canonical ET helper after this repo lost weeks to two timezone constructions
    disagreeing (the pytz LMT bug that shifted the ORB window 56 minutes, #180/#183). Any future
    date use in this module must go through it rather than hand-building a zone."""
    import pathlib

    src = pathlib.Path("shared/llm_models.py").read_text(encoding="utf-8")
    assert 'ZoneInfo("America/New_York")' not in src, (
        "llm_models hand-builds its own ET zone — use shared.dates")
