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
