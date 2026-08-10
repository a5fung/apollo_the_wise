"""The Telegram said "stop moves to breakeven" and nothing did (#548, 2026-08-08).

FIGS, 2026-08-07: the +2R trigger fired at 09:35, banked +$6.90 on 20 shares, and the operator's
Telegram told him *"stop moves to breakeven."* `finalize_partial_exit` duly set
`breakeven_active = TRUE` — **in the database**. The only consumer of that flag is `exit_logic`'s
DAILY pass, which runs after the close. FIGS stopped out at 09:51 the SAME MORNING, roughly six
hours earlier, with the remaining 41 shares still behind the ORIGINAL $15.19 stop. They lost
$13.74 on a trade that had already banked a profit.

It is structural, not bad luck: live MAGNA53 averages ~1.5-day holds and most trades die on day
0-1, so a breakeven that only exists after the close can rarely protect the trades it is for.

**Why this was shippable while the 2R-limit half is still being designed:** the stop is ALREADY
re-created at partial time — a bracket leg's quantity cannot be replaced (Alpaca 42210000), so it
is cancel-then-new regardless. Breakeven is therefore a PRICE ARGUMENT to an operation that
already happens. Zero extra orders, zero extra legs, zero new failure modes — which is exactly
what the operator's constraint asks for: *"we've been bitten by stop orders failing at broker when
it gets complex."*
"""
import pathlib
import re

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text(encoding="utf-8")


_BLOCK_END = "if old_stop_id and stop_price and new_remaining > 0:"


def _block() -> str:
    """The fold-in block: the marker comment through to the stop re-creation it rides on.

    ⚠ Bounded by the NEXT STATEMENT, never by a character count. It used to be
    `SRC[i:i + 2200]`, and on 2026-08-10 the #548 resting-limit build added ~700 chars of
    block comment ahead of the code — which pushed the `stop_price` assignment past 2200 and
    reddened `test_the_breakeven_stop_actually_reaches_the_broker` while the behaviour was
    completely intact. A guard that fires on comment growth is a guard nobody trusts. The
    re-creation line is the real end of this block, so slice to it.
    """
    i = SRC.find("REAL-TIME BREAKEVEN (#548")
    assert i > 0, "the breakeven block is gone — the Telegram is lying again"
    j = SRC.find(_BLOCK_END, i)
    assert j > i, (
        "the breakeven block no longer runs into the existing stop re-creation — it has been "
        "moved away from the operation it is supposed to be a price argument to")
    return SRC[i:j]


def test_the_breakeven_stop_actually_reaches_the_broker():
    b = _block()
    assert "stop_price = _be" in b, (
        "breakeven no longer changes the stop price that is sent to the broker — it is back to "
        "being a database flag the daily pass reads, which cannot help a trade that dies on day 0")


def test_it_can_only_RAISE_the_stop():
    """max(), never min() and never an unconditional assignment. If the original stop already
    sits above entry — a trailed or gapped-up position — breakeven must leave it alone. A
    'breakeven' that LOWERS protection would be strictly worse than doing nothing."""
    b = _block()
    assert "max(float(stop_price), float(_entry))" in b, "breakeven can now lower the stop"
    assert "if _be > float(stop_price):" in b, (
        "the raise-only guard is gone — an entry BELOW the current stop would move it down")


def test_it_rides_the_stop_re_creation_that_ALREADY_happens():
    """The whole reason this half shipped ahead of the 2R limit. If someone later moves it to a
    separate replace/new order, that reintroduces exactly the broker complexity the operator
    ruled against — and the tests should say so out loud."""
    b = _block()
    i = SRC.find("REAL-TIME BREAKEVEN (#548")
    after = SRC[i:i + 3000]
    assert "if old_stop_id and stop_price and new_remaining > 0:" in after, (
        "the breakeven price is no longer computed immediately before the EXISTING stop "
        "re-creation — check it has not grown its own order-submission path")
    for banned in ("submit_order(", "place_stop", "_reduce_stop_via_cancel_new("):
        assert banned not in b, (
            f"the breakeven block now issues its own {banned} — it must remain a price argument "
            "to the re-creation that already happens, not a new broker operation")


def test_it_ships_DARK_behind_a_runtime_toggle():
    """#508's own history is the argument: that change was deployed INERT, confirmed in prod,
    and only then flipped — 'so the path was proven before it was allowed to act on money.'
    Same idiom as #541's entry_ask_aware: one mi_safeguard_state row, no redeploy."""
    assert "async def _breakeven_at_broker_enabled" in SRC
    assert 'get_safeguard_state("breakeven_at_broker", account_mode)' in SRC
    assert "await _breakeven_at_broker_enabled(account_mode)" in _block(), (
        "the breakeven change is no longer gated — it would act on live money on deploy")


def test_the_toggle_fails_CLOSED():
    """An unreadable flag must leave exit behaviour exactly as it is. The one thing it must never
    do is enable a money-path change because a query hiccupped."""
    i = SRC.find("async def _breakeven_at_broker_enabled")
    body = SRC[i:i + 1200]
    assert "except Exception" in body and "return False" in body.split("except Exception")[1][:200], (
        "breakeven_at_broker no longer fails closed")


def test_it_leaves_an_audit_trail():
    """The original defect was invisible precisely because nothing recorded that the breakeven
    had not happened. The row is what makes the verify-live check possible on Monday."""
    assert "partial_exit_breakeven_armed" in _block(), (
        "no audit row when breakeven arms — the fix would be as unverifiable as the bug was")
    b = _block()
    assert re.search(r"was \$\{float\(stop_price\)", b) or "was $" in b, (
        "the audit row no longer records the OLD stop, so a reader cannot tell what changed")
