"""#270 Step 3 Phase 8 — pin the two critical properties of the graduation predicate so a
future edit can't silently drop them: (1) it gates on realized_r (the HARVESTED R), NOT
fwd_mfe_pct/MFE — gating on MFE would recreate the conflation this whole arc closed; (2) it
counts ONLY the FIRST5/gdl entry tactics — anticipation settles realized_r too but stays
observational (no realized edge), so without this guard the verdict ripens on the wrong cohort.
"""
from pathlib import Path

import yaml

YAML = Path(__file__).resolve().parent.parent / "data_gated_reviews.yaml"


def _predicate(rid):
    revs = yaml.safe_load(YAML.read_text(encoding="utf-8"))["reviews"]
    return next(r for r in revs if r.get("review_id") == rid)["predicate_sql"]


def test_graduation_predicate_gates_on_realized_r_and_first5_only():
    sql = _predicate("anticipation_270_shadow_graduation")
    assert "realized_r IS NOT NULL" in sql
    assert "fwd_mfe_pct" not in sql                       # must NOT gate on the MFE ceiling
    assert "state = 'triggered'" in sql
    assert "entry_tactic IN" in sql
    assert "first5_break" in sql and "gdl_reclaim" in sql
    assert "'anticipation'" not in sql                    # the anticipation (coil-close) TACTIC stays observational — not in entry_tactic IN (...)


def test_graduation_predicate_columns_exist_on_table():
    # the predicate's columns must match the shipped mi_anticipation_lifecycle CREATE.
    sql = _predicate("anticipation_270_shadow_graduation")
    ddl = (Path(__file__).resolve().parent.parent
           / "agents/market_intelligence/db.py").read_text(encoding="utf-8")
    assert "mi_anticipation_lifecycle" in ddl
    for col in ("state", "realized_r", "entry_tactic"):
        assert col in sql and col in ddl


def test_both_lifecycle_reviews_are_closed_while_the_writer_job_is_unregistered():
    """#633 (2026-09-09): the readiness + 3b jobs — the only writers of mi_anticipation_lifecycle —
    were un-registered 2026-06-16 (ADR-0013) and the table has not changed since. Both reviews that
    gated on it are CLOSED as superseded (Family A carries its own gates; #297 re-files if it
    reclaims Family B). The predicate text stays as history, which is why the two tests above
    still hold. Reopening either without the writer is the dead gate coming back."""
    revs = yaml.safe_load(YAML.read_text(encoding="utf-8"))["reviews"]
    for rid in ("anticipation_270_shadow_graduation", "anticipation_270_calibration_revalidation"):
        r = next(x for x in revs if x.get("review_id") == rid)
        assert r["status"] == "done", f"{rid} reopened — its writer job is still unregistered"
        assert str(r.get("closed_on")) == "2026-09-09"
        assert "#297" in r["outcome"] and "ADR-0013" in r["outcome"]
