"""A task may not leave PLAN.md unless the close is judged against the task's OWN DoD.

WHY (operator 2026-09-10). He caught four bad calls in one morning and then asked the question this
gate answers: *"Do I need to ask you to double check all your work every time and re prompt you
after things are closed? You can expect me to do this every time. How do we solve this?"*

The worst of the four: #540 was CLOSED on a liveness heartbeat while its DoD demanded a non-null
`broker_reason` on a real rejection. The heartbeat fires on the branch with no tracked entry row, so
it carries no reason at all — a strictly weaker fact that happened to be true. The line held BOTH a
DoD and a later, narrower VERIFY sentence about that sub-feature, and the narrow one got matched.

**A close is the one irreversible act in this repo with nothing checking it**: the line vanishes from
PLAN.md and any unmet criterion vanishes with it. Hence a gate, not a resolution — every prose
commitment here has failed and been replaced by a gate, and this is that gate.

The cases below use the REAL #540 text.
"""
import pytest

from scripts.check_plan import close_bar_for, close_bar_matches

# The real shape: a DoD, then a later VERIFY sentence about one sub-feature.
_540 = (
    "**A live entry was rejected on a stock that ran +33%, and Alpaca had told us why.** "
    "DoD: the next broker cancel OR rejection carries a non-null `broker_reason` in its audit row "
    "and Telegram — proven on a real live event, not a replay.** This is the exact defect class the "
    "task exists to close. ▶ The heartbeat now fires inside `_handle_cancel_or_reject` on a buy-side "
    "order whose `entry_trade` lookup finds nothing, so the handler proves itself alive. "
    "▶ **VERIFY: a heartbeat row appears on the next buy-side cancel/reject.**"
)

_WHAT_I_CHECKED = "a heartbeat row appears on the next buy-side cancel/reject"
_THE_REAL_BAR = "the next broker cancel OR rejection carries a non-null broker_reason"


def test_the_dod_outranks_a_later_verify_sentence():
    """THE ORDERING IS THE POINT. A sub-feature's verify line must not become the closing bar."""
    kind, bar = close_bar_for(_540)
    assert kind == "DoD"
    assert "broker_reason" in bar
    assert "heartbeat" not in bar.lower(), (
        "close_bar_for picked the narrow VERIFY sentence over the DoD — the exact #540 mistake")


def test_the_actual_mistake_is_rejected():
    """Replay 2026-09-10: closing #540 on the heartbeat must FAIL."""
    _, bar = close_bar_for(_540)
    assert not close_bar_matches(_WHAT_I_CHECKED, bar), (
        "the gate accepted a heartbeat as evidence for a broker_reason DoD — it would not have "
        "caught the close it exists to catch")


def test_an_honest_close_is_accepted():
    """It must not block real work: quoting part of the DoD passes."""
    _, bar = close_bar_for(_540)
    assert close_bar_matches(_THE_REAL_BAR, bar)


def test_partial_quotes_and_markdown_do_not_decide_it():
    """A close quotes PART of a long DoD, and backticks/case must never be the deciding factor."""
    _, bar = close_bar_for(_540)
    assert close_bar_matches("carries a NON-NULL `broker_reason` in its audit row", bar)
    assert close_bar_matches("proven on a real live event, not a replay", bar)


def test_a_plausible_paraphrase_still_fails():
    """Restating the DoD in your own words is not quoting it — that is how substitution starts."""
    _, bar = close_bar_for(_540)
    assert not close_bar_matches("the rejection path emits a reason we can read", bar)


def test_verify_live_is_used_when_there_is_no_dod():
    """Older lines carry no DoD; VERIFY-LIVE is then the bar rather than nothing."""
    line = ("Phases 2-3 re-granularization. VERIFY-LIVE = `mi_themes.parent_theme` NON-NULL for the "
            "cyber-vuln child on Monday's row. ▶ next steps follow")
    kind, bar = close_bar_for(line)
    assert kind == "VERIFY-LIVE"
    assert close_bar_matches("mi_themes.parent_theme NON-NULL for the cyber-vuln child", bar)


def test_a_line_with_no_criterion_at_all_returns_none():
    """Then the ledger must carry NO-BAR-DECLARED — closing a task that never defined done."""
    assert close_bar_for("- some old line with no stated criterion whatsoever, just prose") is None


def test_empty_inputs_never_pass():
    assert not close_bar_matches("", "anything at all here")
    assert not close_bar_matches("something", "")


# ── The bar may not bleed into rebump commentary (2026-09-10, altitude review) ────────────────
#
# `close_bar_for`'s capture groups stop only at ▶ >> ⚠ ✅ ⛔ — not at `[`. So a DoD followed by an
# `[ok:...]` rebump tag extracted BOTH: 12 of 67 open lines on the day the gate shipped, #540
# included, whose 624-character "bar" ran into "[ok:2026-08-07→2026-08-10 — NOT a deferral: it
# shipped, the verify RAN today...]". #540 is the task whose mishandled close is the whole reason
# this gate exists, so the gate could have been SATISFIED by quoting rebump history — the exact
# substitution it refuses. Fixed by matching `_verify_claim_body(title)`, the substrate the two
# verify-claim gates already share, rather than a second definition of "this task's own claim".

_REBUMP_TAIL = (
    "**DoD: a non-null `broker_reason` on a real live buy-side rejection, proven on a real event.** "
    "[ok:2026-08-07→2026-08-10 — NOT a deferral: it shipped, the verify RAN today on a real live "
    "cancel, and it FAILED (broker_reason null while the reason sat on the event stream).]"
)


def test_the_bar_stops_at_the_dod_and_never_enters_a_rebump_tag():
    from scripts.check_plan import close_bar_for

    kind, bar = close_bar_for(_REBUMP_TAIL)
    assert kind == "DoD"
    assert "broker_reason" in bar, "the real DoD was lost"
    assert "NOT a deferral" not in bar, "the bar swallowed the [ok:] rebump commentary"
    assert "[ok:" not in bar


def test_rebump_prose_cannot_be_quoted_as_the_bar():
    """THE CONSEQUENCE, asserted directly: with the tag inside the bar, this quote passed."""
    from scripts.check_plan import close_bar_for, close_bar_matches

    _, bar = close_bar_for(_REBUMP_TAIL)
    assert not close_bar_matches("NOT a deferral it shipped the verify RAN today", bar), (
        "a close could be justified by quoting the rebump note instead of the DoD")
    assert close_bar_matches("a non-null broker_reason on a real live buy-side rejection", bar)


def test_every_open_task_on_the_real_board_has_a_clean_bar():
    """The board is the population that matters — 12 of 67 were leaking when this was written."""
    import re

    from scripts.check_plan import PLAN, close_bar_for, parse

    tasks = parse(PLAN.read_text(encoding="utf-8"))[0]
    meta = re.compile(r"\[(?:ok|blocked|swept|revalidated):", re.I)
    leaking = [t["id"] for t in tasks
               if (got := close_bar_for(t["title"])) and meta.search(got[1])]
    assert not leaking, f"bars bleeding into rebump commentary: {leaking}"


# ── A SPLIT MAY NOT NARROW THE BAR SILENTLY (2026-09-11) ──────────────────────────────────────
#
# Operator, reading the #501 close: *"so you're saying the unbuilt stuff sits with 635, so it's ok
# to close 501?"* — the honest answer is that the gate could not tell. `close_bar_matches` only asks
# whether the quote APPEARS in the bar, so "split the task, quote the surviving half, close" passed
# every time. #501's DoD was `the Tier-1 four surfaced (audit + deduped Telegram) + operator rules
# the Tier-2/3 batch`; the second clause moved to #635 and the close quoted only the first.
#
# ⚠ CALIBRATED, NOT GUESSED. A "fraction of the bar's words missing from the quote" rule fires on 10
# of the 12 real ledger entries (0.33 to 1.00 missing) because a legitimate close quotes PART of a
# long DoD — it cannot discriminate. A top-level ` + ` conjunction can.

_TWO_CLAUSE = ("**DoD: the Tier-1 four surfaced (audit plus deduped Telegram alerting) + "
               "the operator rules on the Tier-2 and Tier-3 batch of remaining findings.**")


def _clauses_of(bar_text):
    import re

    from scripts.check_plan import _norm
    return [c for c in re.split(r"\s\+\s", bar_text) if len(_norm(c).split()) >= 4]


def test_a_two_clause_dod_is_seen_as_two_clauses():
    from scripts.check_plan import close_bar_for

    _, bar = close_bar_for(_TWO_CLAUSE)
    assert len(_clauses_of(bar)) == 2, "the conjunction that makes this a partial close is invisible"


def test_quoting_one_clause_leaves_the_other_uncovered():
    """The mechanical fact the gate acts on."""
    from scripts.check_plan import close_bar_for, close_bar_matches

    _, bar = close_bar_for(_TWO_CLAUSE)
    quote = "the Tier-1 four surfaced (audit plus deduped Telegram alerting)"
    cov = [close_bar_matches(quote, c) for c in _clauses_of(bar)]
    assert cov == [True, False], cov


def test_quoting_the_whole_dod_covers_every_clause():
    """A full close must not trip the new arm — this is the false-positive guard."""
    from scripts.check_plan import close_bar_for, close_bar_matches

    _, bar = close_bar_for(_TWO_CLAUSE)
    assert all(close_bar_matches(bar, c) for c in _clauses_of(bar))


def test_the_gate_asks_for_moved_or_accepted_partial():
    """Pin the WIRING: the error text must name both escapes, or nobody can satisfy it."""
    import inspect

    from scripts.check_plan import _close_evidence_gate
    src = inspect.getsource(_close_evidence_gate)
    assert "MOVED:" in src and "ACCEPTED-PARTIAL:" in src
    assert "still_open" in src.split("MOVED:")[1][:900], (
        "a MOVED: target that is not an open task would let the clause vanish anyway")


# ── The bar stops at ⚖ and ➕ too (2026-09-11) ────────────────────────────────────────────────
#
# Found while calibrating the rule above: `⚖` marks the scope / THE-LINE sentence and was NOT in the
# stop set, so a DoD followed by "⚖ no strategy or sizing change; any flip needs sign-off" swallowed
# it. On the live board that day: 15 of 64 open tasks. A close could have quoted a THE-LINE caveat
# as the criterion it was judged against. Same over-capture class as the `[ok:]` leak, one day later.

def test_the_bar_stops_at_the_scope_marker():
    from scripts.check_plan import close_bar_for

    line = ("**DoD: the recorder writes one row per fill with every arm present.** "
            "⚖ **NO MONEY PATH — no strategy, sizing or safeguard change; any flip needs sign-off.**")
    kind, bar = close_bar_for(line)
    assert "one row per fill" in bar
    assert "NO MONEY PATH" not in bar and "sign-off" not in bar, (
        "the bar swallowed the scope / THE-LINE note")


def test_the_bar_stops_at_the_inherited_addition_marker():
    from scripts.check_plan import close_bar_for

    line = ("**DoD: every declined cluster records why it was declined.** "
            "➕ INHERITED FROM #444 on its close — a 14th gate-invisible gap, same taxonomy.")
    _, bar = close_bar_for(line)
    assert "records why" in bar and "INHERITED" not in bar


def test_no_open_task_has_a_bar_running_past_a_marker():
    """The board is the population that matters — 15 of 64 were leaking when this was written."""
    from scripts.check_plan import PLAN, close_bar_for, parse

    tasks = parse(PLAN.read_text(encoding="utf-8"))[0]
    leaking = [t["id"] for t in tasks
               if (got := close_bar_for(t["title"])) and ("⚖" in got[1] or "➕" in got[1])]
    assert not leaking, f"bars running into a scope note: {leaking}"
