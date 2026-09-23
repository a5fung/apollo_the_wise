"""A live trade must not reach a terminal status without saying why.

#184, 2026-09-06. `check_reason_coverage` already existed but its arm required
`status IS NULL` as well as a null reason — so it only caught rows the pipeline dropped
before deciding anything. A row that DECIDED and did not explain itself was invisible.

Four did exactly that: FCEL 06-24, ABSI 06-24, SNX 06-25, ACAD 06-26 — all live account,
all magna53, all with an entry price computed, all `status='cancelled'` with no
skip_reason and no `mi_live_orders` row at all. Nothing flagged them, and by the time
they surfaced in a Sunday review the container logs had rotated and the cause was gone.

The two arms answer different questions and the test pins both:
  status NULL          -> the pipeline dropped it before deciding
  terminal + no reason -> the pipeline decided and did not say why  (the money-path one)
"""
import inspect

from agents.market_intelligence import audit_invariants as ai


def _source() -> str:
    return inspect.getsource(ai.check_reason_coverage)


def test_terminal_statuses_are_named_and_cover_the_real_spellings():
    """Alpaca and our own writers disagree on the spelling of cancelled."""
    terminal = set(ai._TERMINAL_TRADE_STATUSES)
    for s in ("cancelled", "canceled", "expired", "rejected"):
        assert s in terminal, f"{s!r} missing — a real terminal status would slip the check"


def test_the_query_no_longer_requires_a_null_status():
    """The original arm's `AND status IS NULL` is what hid the four rows."""
    src = _source()
    assert "status IS NULL OR status = ANY" in src, \
        "the check must catch terminal-with-no-reason, not only status-NULL rows"
    assert "AND status IS NULL\n" not in src, \
        "the old conjunctive arm is back — terminal rows would be invisible again"


def test_a_null_reason_is_still_required():
    """Widening must not make it fire on every terminal row — only unexplained ones."""
    assert "skip_reason IS NULL" in _source()


def test_the_summary_separates_the_two_arms():
    """One number for two different defects would hide which one fired."""
    src = _source()
    assert "_silent" in src and "_unexplained" in src, \
        "the summary must split silent-drop from terminal-without-why"
    assert "terminal-without-why" in src


def test_the_drill_sql_matches_the_predicate():
    """A drill query that does not reproduce the finding sends the reader in circles."""
    src = _source()
    assert "status IN ('cancelled','canceled','expired','rejected')" in src, \
        "drill_sql must reproduce the widened predicate, not the old one"
