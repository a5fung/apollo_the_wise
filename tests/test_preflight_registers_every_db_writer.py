"""Every module-level SQL statement db.py hands to `execute` / `executemany` as an INSERT, UPSERT,
UPDATE or DELETE is either registered with the deploy-time prepare gate or named below with a reason.

THE GAP THIS CLOSES. `scripts/preflight_db_updates.py` PREPARES each registered statement against
the production schema at deploy, because asyncpg's type-deduction errors (the CRMD-class and #606
bugs) fire at prepare time and a fail-open writer never raises them anywhere else: the table just
sits empty. The registry (`SHADOW_WRITER_STATEMENTS`) is a HAND-LISTED population, and each writer
pinned its own membership with a separate `assert any(sql is db.X for _, sql in ...)` in its own
test (about ten files). A new writer whose author forgets BOTH the registry entry and that
assertion is silently outside the gate - the exact failure the gate exists to prevent, and the
hand-listed-population defect the project's own "derive the population" rule describes
(#210's `GRADE_CORPUS_INSERT_SQL` was registered correctly, but no test would have noticed had it
not been).

THE FIX is the rule, not a 13th assertion: DERIVE the writers from db.py's own source and require
each to be accounted for. A new writer now fails this test until it is registered or named.

WHAT THE WALK CAN AND CANNOT SEE. It sees a module-level constant passed by NAME as the first
argument of `.execute(` / `.executemany(` anywhere in db.py. It does NOT see SQL written inline,
SQL built into a local variable or an argument tuple (`log_audit_event` passes `*args`), or writers
in other modules (`catalyst_metrics_extractor`, `ep_theme_belonging` register theirs by import and
keep their own assertions). The trade-lifecycle `UPDATE mi_live_trades` blocks are inline on
purpose (the [5c/7] column-writer gate attributes them to their enclosing function), so they are
out of this walk by design. The canary test below fails if the walk ever stops finding the
writers it is known to find, so it cannot pass vacuously.
"""
from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
DB = REPO / "agents" / "market_intelligence" / "db.py"

_WRITE_VERBS = {"INSERT", "UPDATE", "DELETE"}

# Statements that are NOT in the prepare registry as of this gate's birth (2026-10-10). Naming them
# is NOT a ruling that they may stay out: registering one changes what a deploy fails on, which is
# a separate decision (listed as a follow-up on the card that added this gate). The set can only
# SHRINK - `test_the_exempt_set_holds_only_real_unregistered_writers` fails the moment an entry is
# registered or removed from db.py, so a stale name cannot linger.
_UNREGISTERED_AT_GATE_BIRTH = {
    "EP_ALERT_TAPE_UPDATE_SQL":
        "tape_* telemetry UPDATE on mi_ep_alerts, run with a caller-supplied conn inside the EP "
        "scan annotator; shape pinned by tests/test_tape_quality.py, never prepared at deploy",
    "EP_ALERT_VOL_UPDATE_SQL":
        "vol_* telemetry UPDATE on mi_ep_alerts, same annotator loop; shape pinned by "
        "tests/test_vol_profile.py, never prepared at deploy",
    "EP_ALERT_VOL_LANDMARK_UPDATE_SQL":
        "vol_alert_vs_max telemetry UPDATE from the 16:10 EOD recap; shape pinned by "
        "tests/test_vol_profile.py, never prepared at deploy",
    "_DELAYED_WATCH_UPSERT_SQL":
        "delayed-entry watch-lane UPSERT (mi_delayed_entry_watch); never prepared at deploy",
}


def _statement_names_passed_to_execute() -> set[str]:
    """Names of module-level constants in db.py used as the first argument of `.execute(` /
    `.executemany(`."""
    # source-pin-ok: the property is "which statements does db.py execute" - a population only the
    # module's own source can enumerate (that is the point: it is derived, not hand-listed); no
    # behaviour of a single function can say it.
    tree = ast.parse(DB.read_text(encoding="utf-8"))
    module_names = {t.id for n in tree.body if isinstance(n, ast.Assign)
                    for t in n.targets if isinstance(t, ast.Name)}
    return {c.args[0].id for c in ast.walk(tree)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr in ("execute", "executemany")
            and c.args and isinstance(c.args[0], ast.Name) and c.args[0].id in module_names}


def _derived_writers() -> dict[str, str]:
    """name -> SQL for every derived name whose runtime value is a write statement."""
    import agents.market_intelligence.db as db
    out = {}
    for name in _statement_names_passed_to_execute():
        sql = getattr(db, name, None)
        if isinstance(sql, str) and sql.split(None, 1)[:1] and sql.split(None, 1)[0].upper() in _WRITE_VERBS:
            out[name] = sql
    return out


def _registered_ids() -> set[int]:
    import scripts.preflight_db_updates as pf
    return {id(sql) for _, sql in [*pf.SHADOW_WRITER_STATEMENTS, *pf.TRADE_LIFECYCLE_UPDATES]}


def test_the_walk_finds_the_writers_it_is_known_to_find():
    """The walk must not pass vacuously: a refactor that changed how db.py calls `execute` would
    make it see nothing, and 'nothing is unregistered' would read as green. These are named members
    - registered and unregistered, INSERT / UPSERT / UPDATE - not a count floor."""
    found = set(_derived_writers())
    for known in ("GRADE_CORPUS_INSERT_SQL", "LIVE_FILL_CF_INSERT_SQL", "_TV_NEWS_SHADOW_UPSERT_SQL",
                  "LOWCAP_LANE_SIGNAL_INSERT_SQL", "EP_ALERT_JUDGE_RESULT_UPDATE_SQL",
                  "EP_ALERT_TAPE_UPDATE_SQL", "_DELAYED_WATCH_UPSERT_SQL"):
        assert known in found, f"the walk no longer finds {known}"


def test_every_db_writer_statement_is_registered_with_the_prepare_gate_or_named():
    import agents.market_intelligence.db as db
    registered = _registered_ids()
    missing = sorted(name for name, sql in _derived_writers().items()
                     if id(sql) not in registered and name not in _UNREGISTERED_AT_GATE_BIRTH)
    assert not missing, (
        f"db.py executes {missing} but scripts/preflight_db_updates.py never PREPARES them. Add "
        "(label, db.<NAME>) to SHADOW_WRITER_STATEMENTS (import the constant, never copy it) - a "
        "fail-open writer with a type-deduction bug otherwise leaves its table empty with no error "
        "anywhere. A statement that genuinely cannot be prepared goes in _UNREGISTERED_AT_GATE_BIRTH "
        "with a reason, which is a decision to make on purpose.")
    # sanity: the registry holds the real db.py objects, so the identity test above means something
    assert any(sql is db.GRADE_CORPUS_INSERT_SQL for sql in _derived_writers().values())


def test_the_exempt_set_holds_only_real_unregistered_writers():
    """The ratchet: an exempt name that has since been registered, renamed or deleted is a stale
    entry hiding nothing - remove it, so the list only ever shrinks."""
    derived, registered = _derived_writers(), _registered_ids()
    for name in _UNREGISTERED_AT_GATE_BIRTH:
        assert name in derived, f"{name} is no longer a statement db.py executes - drop it from the exempt set"
        assert id(derived[name]) not in registered, (
            f"{name} is now registered with the prepare gate - drop it from the exempt set")
