"""The catalyst-lattice monitor may not prescribe a revert it has not checked.

WHY (#638, 2026-09-10). Trigger (c) fired on two zero-alert trading days and printed the revert SQL
for `catalyst_tier_lattice`. Measured on prod that morning: the lattice's verdict was IDENTICAL to
the raw LLM grade on all 12 candidates of 2026-09-09 — `live_quality_last` == `shadow_tier_last` on
every row. **Turning it off would have been byte-identical.** It had suppressed nothing. The zero
came from the day's best score being 58.8 against a bar of 65, with the bar at 65 for "strong" and
"routine" alike, so the catalyst label was not moving it either. Supply was 1 and 10 qualifying
stocks against a base rate of 19.8 alerts per 100 — roughly two expected alerts, so zero is an
ordinary draw.

**A monitor that prescribes a revert without checking whether the reverted thing did anything is a
recommendation that cannot be wrong.** Trigger (b) learned the same lesson on 2026-08-24 in a
different shape — it named the flip as cause for a collapse that began five trading days BEFORE the
flip — and was era-scoped in response. Same file, second trigger, same class.

⚠ This does NOT silence the trigger. Two silent days on a live money path are worth a look, which
is what the 2026-08-26 note in the source argues. What changes is what the message RECOMMENDS.
"""
import pytest

from agents.market_intelligence.health_checks import lattice_altered_nothing


def _row(llm, lattice):
    return {"live_quality_last": llm, "shadow_tier_last": lattice}


def test_the_real_2026_09_09_window_reads_as_inert():
    """The actual rows: 12 candidates, every lattice verdict equal to the LLM grade."""
    rows = [_row(q, q) for q in
            ("routine", "routine", "routine", "mna", "mna", "strong",
             "routine", "routine", "routine", "routine", "strong", "strong")]
    assert lattice_altered_nothing(rows) is True


def test_one_changed_grade_is_enough_to_justify_the_prescription():
    """The bar is deliberately low — a single re-tier means the mechanism WAS acting."""
    rows = [_row("routine", "routine"), _row("routine", "strong")]
    assert lattice_altered_nothing(rows) is False


def test_no_rows_is_UNKNOWN_not_inert():
    """THREE states, not two — the pre-existing monitor tests caught me collapsing them.

    My first cut returned True (inert) when no re-tier rows existed, which withheld the revert SQL.
    That is wrong in the one case that matters most: if the shadow RECORDER were broken, the
    lattice could be acting hard while this table sat empty, and "inert" would silently mute the
    prescription exactly when it was needed. Unknown keeps the SQL and says it could not be
    verified; only OBSERVED sameness withholds it.
    """
    assert lattice_altered_nothing([]) is None
    assert lattice_altered_nothing(None) is None


def test_unknown_keeps_the_sql_and_says_so():
    """The message must distinguish "it did nothing" from "we could not tell"."""
    import inspect

    from agents.market_intelligence import health_checks
    src = inspect.getsource(health_checks)
    assert 'out.get("lattice_inert") is True' in src, "inert and unknown are collapsed again"
    assert "Could not verify the lattice actually acted" in src


def test_the_trigger_still_fires_it_only_stops_prescribing():
    """The monitor must keep reporting a silent money path — that is its job."""
    import inspect

    from agents.market_intelligence import health_checks
    src = inspect.getsource(health_checks)
    assert "ZERO-ALERT DAYS" in src, "the trigger stopped speaking entirely"
    assert "lattice_inert" in src


def test_the_revert_sql_is_gated_on_the_evidence():
    """Pin the wiring, not just the predicate — the helper passing proves nothing on its own."""
    import inspect

    from agents.market_intelligence import health_checks
    src = inspect.getsource(health_checks)
    i = src.index("_LATTICE_REVERT_SQL)")
    window = src[max(0, i - 900):i]
    assert 'if out.get("lattice_inert")' in window, (
        "the revert SQL is printed without checking whether the lattice did anything")


# ── The verdict belongs to ALL THREE triggers, not to one of them (2026-09-10, second pass) ───
#
# The first version computed `lattice_inert` inside trigger (c)'s branch. Triggers (a) and (b)
# therefore left the key unset, `out.get("lattice_inert")` read None, and the "could not verify"
# line was itself gated on `"zero_alert_days" in kinds` — so an (a)- or (b)-only firing printed the
# revert SQL with no inertness check and no caveat. (a) is the worse half: `_lattice_acting_tier`
# returns the raw LLM grade whenever `live_side != "lattice"`, so (a) can name the lattice for a
# miss it was never in the acting path of. A check that only covers one of three entrances is
# indistinguishable from no check on the other two — this week's defect, one level up.

def _monitor_src():
    import inspect

    from agents.market_intelligence import health_checks
    return inspect.getsource(health_checks.run_catalyst_lattice_monitor)


def test_the_verdict_is_computed_once_and_outside_every_trigger_branch():
    src = _monitor_src()
    assert src.count('out["lattice_inert"] = lattice_altered_nothing(') == 1, (
        "the verdict is computed in more than one place, or not at all")
    verdict = src.index('out["lattice_inert"] = lattice_altered_nothing(')
    last_append = src.rindex('out["triggers"].append(')
    assert verdict > last_append, (
        "the inertness verdict sits inside a trigger's branch — the other triggers skip it")


def test_every_trigger_contributes_the_dates_it_points_at():
    """All three must feed the window, or the verdict judges the wrong days."""
    src = _monitor_src()
    assert src.count("_implicated.append(") + src.count("_implicated.extend(") == 3, (
        "a trigger stopped contributing its dates — its firing would be judged on someone "
        "else's window, or on none")


def test_the_could_not_tell_caveat_is_not_scoped_to_one_trigger():
    src = _monitor_src()
    i = src.index("Could not verify the lattice actually acted")
    guard = src[max(0, i - 400):i]
    assert "zero_alert_days" not in guard, (
        "the unknown-verdict caveat only speaks for one trigger again")


# ── The verdict must be IN the audit row (2026-09-11) ────────────────────────────────────────
#
# The 09-11 alert printed the revert SQL and no row recorded WHY. Checked by hand afterwards:
# 7 re-tier rows, inert=False — so printing it was correct. But "correct, verified by hand the
# next day" is not the same as recorded, and the second pass caused it: moving `lattice_inert`
# off trigger (c) and onto `out` took it out of the serialised detail, which only carried
# `today` and `triggers`. An alarm that acts on a verdict nothing can audit is this task's own
# defect, reintroduced by its fix.

def test_the_audit_row_records_the_verdict_it_acted_on():
    src = _monitor_src()
    i = src.index('"catalyst_lattice_monitor_alert"')
    payload = src[i:i + 700]
    for field in ("lattice_inert", "lattice_rows_seen", "lattice_days_checked"):
        assert field in payload, f"the alert row does not record {field} — the verdict is unauditable"
