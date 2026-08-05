"""A realized partial profit is an outcome, so it breaks the loss streak (2026-08-05).

⚖ Operator-signed. His reasoning, verbatim: *"winners tend to be held longer, so in case of
PLTR we're holding, if it continues to do well, we'll continue to hold... this circuit breaker
will remain basically for a long time"* and *"what we need to prevent is perpetual blockers
otherwise we'll never trade."*

THE BIAS. The streak read CLOSED trades only. Losers close fast — all 14 live losses closed
within about a day — while winners are HELD by design. So the only event that could break the
streak was a winner CLOSING, which is precisely what the methodology delays. Measured: 14
closed live trades, ZERO winners, so that escape has never once been able to fire.

WHAT SHIPPED. Realized partial exits enter the outcome sequence at their own exit time. Not a
special-case reset — the rule is still "are the last N outcomes ALL losses", and a win anywhere
in the window answers no. Nothing is erased: a trade that later closes red enters that loss too.

⚠ REJECTED WITH EVIDENCE — expiring losses by age. Replay showed EVERY window that would have
unblocked 2026-08-05 also leaves the breaker unable to fire on the real 14-loss streak: at 14
days its peak count is 8 against a threshold of 10, because those losses arrived ~1 per 2 days
and expire faster than they accumulate. That disarms the safeguard rather than modernising it.

⚠ REJECTED — counting UNREALIZED gains. 5 of 12 live trades reached +1R or better and ALL FIVE
finished losers (#503), so "currently up" is near-uninformative here, and counting it would
disarm the breaker during exactly the round-tripping it should catch.
"""
import ast
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text()
TREE = ast.parse(SRC)


def _safeguards_src():
    fn = next(n for n in ast.walk(TREE)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "_check_safeguards")
    return ast.get_source_segment(SRC, fn)


def _breaker_sql():
    """Just the SQL text — the comment above it discusses `unrealized` deliberately, and a
    substring check over the whole block would trip on the explanation rather than the code."""
    src = _safeguards_src()
    i = src.index("recent_closed = await conn.fetch")
    body = src[i:]
    a = body.index('"""') + 3
    sql = body[a:body.index('"""', a)]
    # strip `--` comment lines: they EXPLAIN the choice (including the word "unrealized",
    # which is exactly what was rejected) and must not be mistaken for what the query reads.
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def test_realized_partials_enter_the_outcome_sequence():
    q = _breaker_sql()
    assert "UNION ALL" in q
    assert "jsonb_array_elements" in q, "partials live in the exits array"
    assert "status <> 'closed'" in q, "only STILL-OPEN trades contribute partials"


def test_it_reads_BANKED_cash_not_mark_to_market():
    """The whole reason unrealized was rejected. `exits[].pnl` is the same array `total_pnl` is
    summed from on close — verified on PLTR 307: 33.27 = the one 2-share exit, while the
    position's unrealized was ~89."""
    q = _breaker_sql()
    assert "e->>'pnl'" in q
    for mtm in ("unrealized", "market_value", "current_price"):
        assert mtm not in q, "the QUERY must never read a mark-to-market column"


def test_the_partial_is_timestamped_at_its_OWN_exit_not_the_trade():
    """Ordering is what makes this work — a partial banked after the newest loss must sort
    above it. Using the trade's own timestamp would put it in the wrong place."""
    q = _breaker_sql()
    assert "e->>'time'" in q
    assert "ORDER BY closed_at DESC" in q


def test_the_threshold_and_cooldown_are_UNCHANGED():
    """This is a change to WHAT COUNTS as an outcome, not to how many losses trip it or how
    long the pause lasts. Both stay where the operator set them."""
    from agents.market_intelligence.constants import (
        CIRCUIT_BREAKER_CONSEC_LOSSES, CIRCUIT_BREAKER_COOLDOWN_DAYS)
    assert CIRCUIT_BREAKER_CONSEC_LOSSES == 10
    assert CIRCUIT_BREAKER_COOLDOWN_DAYS == 1


def test_the_all_losses_RULE_itself_is_unchanged():
    src = _safeguards_src()
    assert 'all(r["total_pnl"] <= 0 for r in recent_closed)' in src, (
        "still 'are the last N ALL losses' — a win anywhere in the window answers no")


def test_losses_are_NOT_expired_by_age():
    """The rejected alternative. If someone later adds an age filter to this query, the replay
    that ruled it out must be re-run first — pinned so it cannot slip in quietly."""
    q = _breaker_sql()
    for aged in ("INTERVAL", "NOW() -", "age(", "days'"):
        assert aged not in q, "loss-expiry was rejected with evidence — see the source comment"


def test_it_stays_per_account_mode():
    """A paper streak must never gate live entries, and a paper partial must never clear a
    live breaker — the widened query must keep that isolation."""
    q = _breaker_sql()
    assert q.count("account_mode = $2") == 2, "BOTH arms of the union must be mode-filtered"
