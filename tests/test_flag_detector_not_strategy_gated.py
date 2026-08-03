"""Retiring a STRATEGY must never switch off the DETECTOR other setups are sourced from.

WHAT HAPPENED. On 2026-08-02 the deprecated `flag_continuation` strategy row was correctly disabled
— it is terminal and can never place an order. `run_flag_scan` gated on
`should_run("flag_continuation")`, so that same switch also turned off the DAILY DETECTOR.

Measured cost, on the first market day after:
  * `mi_flag_candidates` — 573 / 587 / 577 rows on 7/29 / 7/30 / 7/31, then **ZERO on 8/03**.
  * `mi_htf_breakout_shadow` — nothing at all, because **this scan is HTF's engine**.
  * #356's go-live evidence (needs 5 takeable breakouts, had 3) silently stopped accruing.

Nothing raised. The job reported `success` with `rows_written=0`; only the #340 row-count drift
check caught it, one day later.

THE DISTINCTION, which the operator has stated more than once and which CLAUDE.md now carries as a
definition:

    *"flag detector is on, that can just be detecting flags in general of which the real setups can
    be sourced from."*  — operator, 2026-08-02

A **setup** needs a defined buy point and stop. **Continuation is a FAMILY** — a chart condition
that hosts setups but is not tradeable itself. `docs/setups/flag_continuation.md` already carried a
section titled "Why the DETECTOR exists but the STRATEGY does not"; the DOC said they were separate
while the CODE made them one switch. A comment is not a constraint.

Entry gating belongs at the entry path, where a strategy phase is meaningful. Detection feeds
watch surfaces and other setups, and must outlive the strategy that first needed it.
"""
import ast
import re

_DETECTOR = "agents/market_intelligence/flag_detector.py"
_SRC = open(_DETECTOR).read()
_TREE = ast.parse(_SRC)


def _run_flag_scan_body() -> str:
    m = re.search(r"async def run_flag_scan\(.*?(?=\nasync def |\ndef )", _SRC, re.S)
    assert m, "run_flag_scan not found — did it get renamed?"
    return m.group(0)


def _calls_in_run_flag_scan() -> set:
    """Function names actually CALLED inside run_flag_scan — AST, not text.

    The first version of this test grepped the source and tripped on its own explanatory comment,
    which quotes the removed gate. A comment describing a bug is not the bug; only parsing can tell
    them apart — the same lesson as the chart-pause tests earlier today."""
    fn = next(n for n in ast.walk(_TREE)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_flag_scan")
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            out.add(f.id if isinstance(f, ast.Name)
                    else f.attr if isinstance(f, ast.Attribute) else "")
    return out


def test_the_scan_does_not_bail_on_the_strategy_registry():
    """THE regression. A disabled strategy row must not stop detection."""
    assert "should_run" not in _calls_in_run_flag_scan(), (
        "run_flag_scan CALLS the strategy registry again — disabling the deprecated "
        "flag_continuation row would starve the detector AND HTF, exactly as it did on 2026-08-03")


def test_no_strategy_gate_of_any_kind_short_circuits_the_scan():
    """Guard against the same coupling reappearing under a different key or helper."""
    called = _calls_in_run_flag_scan()
    for banned in ("should_run", "is_enabled", "strategy_enabled"):
        assert banned not in called, f"{banned}() re-introduces the strategy gate ahead of detection"


def test_the_detector_places_no_orders():
    """Why removing the gate is safe, stated as a property rather than an assumption: this module
    computes and records. Entry gating belongs where entries happen."""
    for forbidden in ("submit_trade_entry", "place_order", "submit_order", "trading_client"):
        assert forbidden not in _SRC, f"flag_detector must never {forbidden}"


def test_the_reason_is_recorded_where_the_next_reader_will_look():
    """This coupling has now cost real data once. The next person to tidy up a deprecated strategy
    must find the reason in the code, not reconstruct it."""
    body = _run_flag_scan_body()
    assert "NO STRATEGY GATE HERE" in body
    assert "HTF" in body, "must say that this scan is HTF's engine"


def test_the_setup_versus_family_distinction_is_documented():
    """The operator has corrected this repeatedly; it is a definition, not a preference."""
    doc = open("docs/setups/flag_continuation.md").read()
    assert "DETECTOR exists but the STRATEGY does not" in doc
    claude_md = open("CLAUDE.md").read()
    assert "SETUP vs FAMILY" in claude_md
