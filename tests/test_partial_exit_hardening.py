

# ── the breaker must alert ONCE, not every cycle (operator 2026-08-04) ───────────────────────

def test_breaker_open_alerts_once_per_trade_not_once_per_cycle():
    """PLTR, 2026-08-04: the +2R profit trigger failed structurally (Alpaca rejects a qty change on
    a bracket leg — "qty cannot be changed for advanced orders"), the breaker opened, and the
    5-minute job then re-sent the SAME pair of messages every cycle for hours.

    Operator: *"I've been bombarded with these msg non stop, this is a really really bad bug."*

    A breaker that is OPEN is a KNOWN state. Re-announcing it is not information — it buries the one
    message that mattered. The audit row still fires every cycle so the durable record stays
    complete; only the Telegram is deduped."""
    src = open("agents/market_intelligence/broker/order_manager.py").read()
    assert "_breaker_already_alerted" in src
    i = src.index("Partial-exit circuit breaker OPEN")
    window = src[max(0, i - 900):i]
    assert "already_alerted" in window, "the Telegram must be gated on the dedupe check"


def test_the_audit_row_is_NOT_deduped():
    """Only the notification is suppressed. Losing the per-cycle audit row would destroy the
    forensic trail for exactly the failure being investigated."""
    import ast
    tree = ast.parse(open("agents/market_intelligence/broker/order_manager.py").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "execute_partial_exit")
    src = ast.unparse(fn)
    audit = src.index("partial_exit_circuit_open")
    tg = src.index("Partial-exit circuit breaker OPEN")
    assert audit < tg, "the audit row must be written before, and independently of, the alert"


def test_the_dedupe_fails_OPEN():
    """A duplicate message is a nuisance; a missed one on a live money path is not."""
    import ast
    tree = ast.parse(open("agents/market_intelligence/broker/order_manager.py").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_breaker_already_alerted")
    handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
    assert handlers and any(
        isinstance(x, ast.Return) and getattr(x.value, "value", None) is False
        for h in handlers for x in ast.walk(h)), "must return False (alert) on error"
