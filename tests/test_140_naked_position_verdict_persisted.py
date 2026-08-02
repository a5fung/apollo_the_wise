"""#140 follow-up — the naked-position VERDICT must survive in the audit row.

`classify_naked_positions` asks the broker whether each flagged position actually has stop
coverage, and splits the rows into 🚨 REAL-NAKED (real money unprotected) and ⚠️ DB-DRIFT (the
broker HAS the stop; only our `stop_order_id` column is empty). That classification is what makes
the alert triageable.

**The bug this file pins (found 2026-08-02):** the verdict was computed, rendered into the Telegram
text, and then DROPPED — `_emit_l1` wrote a fixed key set that did not include it. So severity
existed for exactly one message and then evaporated.

Consequence on the real 2026-07-27 QBTS alert: the weekly system review flagged it "UNVERIFIED" and
answering it required reconstructing the exit from `mi_live_trades.exits` (`reason=stop_hit` ⇒ a
stop existed ⇒ DB drift, no exposure). **An alert whose severity cannot be recovered afterwards
cannot be triaged afterwards.**
"""
import ast
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1]
        / "agents/market_intelligence/system_audit.py").read_text()


def _emit_l1_source() -> str:
    tree = ast.parse(_SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "_emit_l1")
    return "\n".join(_SRC.split("\n")[fn.lineno - 1:fn.end_lineno])


def test_verdict_keys_are_written_to_the_audit_detail():
    src = _emit_l1_source()
    for key in ('"real_naked"', '"db_drift"'):
        assert key in src, f"{key} is computed but never persisted — severity evaporates"


def test_a_classified_flag_distinguishes_unrun_from_empty():
    """`real_naked: []` is ambiguous on its own — it means BOTH 'classifier ran, found none' and
    'classifier never ran'. That ambiguity is the same instrumentation trap; the flag resolves it."""
    assert '"classified"' in _emit_l1_source()


def test_classification_still_happens_BEFORE_the_row_is_written():
    """If the audit write moved above the classifier call the keys would persist as empty and the
    test above would still pass — order is load-bearing, so pin it."""
    src = _emit_l1_source()
    assert src.index("classify_naked_positions") < src.index("log_audit_event")


def test_only_the_naked_invariant_carries_these_keys():
    """Other L1 invariants have no broker classification; adding the keys unconditionally would
    imply a verdict that was never computed."""
    src = _emit_l1_source()
    guard = src.index('if name == "naked_position":\n        _detail["real_naked"]')
    assert guard > 0, "verdict keys must sit behind the naked_position guard"
