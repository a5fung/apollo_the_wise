"""Guard: every module registered in the monthly backward-check sweep must be
importable + module-runnable (`python -m <module>`).

The sweep (`run_quarterly_sweep`) runs each entry as a subprocess `python -m <module>`.
A typo'd / renamed module path doesn't fail loudly until the 1st-of-month cron, where
it only shows as a 🔴 line in the digest. This test catches it at CI time instead —
loud-not-silent (feedback_no_silent_trading_failures), the same discipline the sweep
itself enforces. Importing is side-effect-free: every registered script guards work
behind `if __name__ == "__main__"` and `async def main`, and DB access is lazy.
"""
import importlib

from agents.market_intelligence.quarterly_review import QUARTERLY_BACKWARD_CHECK_SCRIPTS


def test_every_registered_sweep_module_imports():
    failures = []
    for entry in QUARTERLY_BACKWARD_CHECK_SCRIPTS:
        label, module = entry[0], entry[1]
        try:
            importlib.import_module(module)
        except Exception as e:  # noqa: BLE001 — report ALL failures, not just the first
            failures.append(f"{label}: {module} -> {type(e).__name__}: {e}")
    assert not failures, "Unimportable sweep module(s):\n  " + "\n  ".join(failures)


def test_mna_accuracy_review_registered():
    # #285 — the M&A accuracy review was graduated into the monthly sweep.
    modules = [e[1] for e in QUARTERLY_BACKWARD_CHECK_SCRIPTS]
    assert "scripts.mna_filter_accuracy_review" in modules
