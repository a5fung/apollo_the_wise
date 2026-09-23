"""A PAPER success was closing the LIVE circuit breaker (#525, operator-signed 2026-08-08).

`_consecutive_partial_exit_failures` counted partial-exit failures since the last
`partial_exit_committed` — with **no `account_mode` filter anywhere in the query**. So a
simulated success switched off a real safety stop.

**Measured on prod at the time of the fix, which is what made it urgent rather than theoretical:**

| | successes that reset the breaker | recorded genuine failures |
|---|---|---|
| paper | **12** | **5** |
| live | 2 | 0 |

Twelve of the fourteen resets had come from the paper book.

It violates invariant 3 of the dual-account safety backbone — *"account_mode filter on every
trade query"* (`docs/architecture/dual_account.md`) — so it is a BUG FIX against a rule already
signed, not a new criterion.

⚠ Attribution is the interesting part: `mi_audit_log` has no `account_mode` column and these rows
never wrote one, so mode is resolved from the `account_mode` key written into `detail` from this
commit onward, falling back to a `trade_id` join for every historical row.
"""
import pathlib
import re

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text(encoding="utf-8")


def _fn() -> str:
    """The whole function, bounded by the NEXT top-level def rather than a character count —
    a fixed window silently truncated the SQL and made four of these tests fail against
    correct code."""
    i = SRC.find("async def _consecutive_partial_exit_failures")
    assert i > 0, "the breaker function moved — re-point this test"
    j = SRC.find("\ndef ", i)
    k = SRC.find("\nasync def ", i + 1)
    end = min(x for x in (j, k, len(SRC)) if x > 0)
    return SRC[i:end]


def test_the_breaker_is_asked_about_ONE_account_mode():
    body = _fn()
    assert "account_mode: str," in body.split(")")[0] + ")", (
        "the breaker no longer takes an account_mode — it is back to counting both books "
        "together, and a paper success can close the live breaker")
    assert "_consecutive_partial_exit_failures(breaker_mode)" in SRC, (
        "the caller stopped passing a mode — the breaker is counting both books again")
    # the breaker runs BEFORE the trade is loaded, so the mode is resolved with its own
    # lookup; without that this is an UnboundLocalError at runtime, which is exactly how the
    # first version of this fix broke three existing tests.
    assert "SELECT account_mode FROM mi_live_trades WHERE id = $1" in SRC, (
        "the pre-breaker mode lookup is gone — account_mode is not bound this early")


def test_a_success_only_closes_ITS_OWN_book():
    """The actual defect. The anchor — 'last success' — must match the mode being asked about."""
    body = _fn()
    assert "event_type = 'partial_exit_committed' AND mode = $2" in body, (
        "a success in EITHER book closes the breaker again — this is exactly the reported bug")


def test_an_operator_RESET_still_clears_every_book():
    """Deliberate asymmetry: a `partial_exit_breaker_reset` is an audited operator action naming
    the fault it clears, and it should clear it everywhere. Only the automatic path is per-mode."""
    body = _fn()
    assert "OR event_type = 'partial_exit_breaker_reset'" in body, (
        "the operator reset became mode-scoped — it is a deliberate manual action and should "
        "clear the fault it names in both books")


def test_failures_are_filtered_to_the_mode_asked_about():
    assert "AND (mode = $2 OR mode IS NULL)" in _fn(), (
        "failures are no longer filtered by mode")


def test_an_UNATTRIBUTABLE_failure_COUNTS():
    """Direction matters on a safety device. A failure whose mode cannot be resolved is treated
    as belonging to the mode being asked about: over-counting delays trading, under-counting
    removes a stop. `mode IS NULL` must stay on the FAILURE side and must NOT appear on the
    success anchor — an unattributable SUCCESS must never close anything."""
    body = _fn()
    anchor = body.split("SELECT COUNT(*) AS n FROM tagged")[0]
    assert "mode IS NULL" not in anchor, (
        "an unattributable row can close the breaker — a success we cannot attribute must not "
        "switch off a safety stop in a book it may not belong to")


def test_history_is_attributed_by_joining_the_trade():
    """These rows never carried a mode, so without the join every historical row would be
    unattributable and the fix would be cosmetic."""
    body = _fn()
    assert "LEFT JOIN mi_live_trades t" in body and "trade_id" in body, (
        "historical rows are no longer attributed via trade_id — the fix only works for rows "
        "written after the deploy")


def _code_only(s: str) -> str:
    """Strip comments AND the docstring before grepping.

    ⚠ THIRD TIME THIS BIT ME IN ONE SESSION. A guard that greps a file for a banned string
    matches that string inside the very prose explaining why it is banned — so the test passes
    on broken code, or fails on correct code. Both happened today. Any assertion of the form
    "X must not appear" has to look at CODE."""
    body = s.split('"""')
    s = body[0] + ("".join(body[2:]) if len(body) > 2 else "")
    return "\n".join(line.split("--", 1)[0].split("#", 1)[0] for line in s.split("\n"))


def test_the_sql_avoids_a_json_cast():
    """Some rows carry malformed/truncated detail; `detail::json` raises on them and would take
    the breaker query down with it — a safety device that errors is a safety device that is off."""
    code = _code_only(_fn())
    assert "detail::json" not in code, ("the breaker query casts detail to json — it will raise "
                                        "on the malformed rows already present in prod")
    assert "substring(a.detail from" in code


def test_new_rows_carry_their_own_mode():
    """So the query stops depending on a join, and a row cannot be misattributed by a later
    schema change. The SUCCESS row matters most — it is the one that closes the breaker."""
    i = SRC.find('"partial_exit_committed",')
    seg = SRC[i:i + 900]
    assert '"account_mode": account_mode' in seg, (
        "the partial_exit_committed row no longer records which book it belongs to")
