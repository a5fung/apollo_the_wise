"""The deploy's import-shadowing gate (scripts/preflight_import_shadowing.py, the 2026-05-20
UnboundLocalError outage class) also runs in the test suite, so a function-local re-import of a
module-level name is caught before a push — not only after a deploy has already restarted the
containers (2026-10-10: the #655 fold's `get_operator_protected_set` re-import passed the suite and
two reviews, and was caught only by deploy step 5d, after the restart)."""
import importlib.util
from pathlib import Path


def test_no_function_local_import_shadows_a_module_level_name():
    path = Path(__file__).resolve().parents[1] / "scripts" / "preflight_import_shadowing.py"
    spec = importlib.util.spec_from_file_location("preflight_import_shadowing", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main() == 0, "a function-local import shadows a module-level one — see the output above"
