"""wick_fill RETIRED (operator 2026-10-17: "kill wick fill, remove that setup completely").

The setup is gone from the codebase the way 9M Day 2 was: no job, no sweep, no writer, no reader, no
Telegram command, no seed row. What stays is HISTORY — the `mi_wick_candidates` table + its DDL and
the `mi_strategies` row (phase 'deprecated', enabled false), exactly as for 9M. docs/setups/wick_fill.md.

Five things pinned, every one over the real code (no source text is trusted where behaviour can run):
  1. The registry SEED no longer creates a wick_fill row.
  2. The startup fix-up, RUN as SQL against a real engine, leaves an existing row deprecated AND
     disabled in ONE statement. The disabled half is the load-bearing one: `phase='deprecated'`
     with `enabled=true` makes `registry.assert_no_deprecated_but_enabled` RAISE at the first
     `load_strategies()` — a phase-only copy of the 9m_day2 migration would turn this retirement
     into a boot failure on apollo-market.
  3. No scheduler job id for it is registered, and none is classified in either ownership manifest.
  4. The module, adapter, DB helpers and slash command are gone (command-parity lists included).
  5. NOTHING writes the table any more — derived over every production .py file, not a hand list.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest

from agents.market_intelligence import scheduler as sched
from agents.market_intelligence.db import _seed_strategies_registry
from agents.market_intelligence.strategies.registry import Strategy, assert_no_deprecated_but_enabled

REPO = Path(__file__).resolve().parent.parent


# ── 1 + 2. registry seed and the startup fix-up ────────────────────────────────────────────

class _FakeConn:
    def __init__(self):
        self.executemany_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []

    async def executemany(self, query, args):
        self.executemany_calls.append((query, args))

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _run_seed() -> _FakeConn:
    conn = _FakeConn()
    asyncio.run(_seed_strategies_registry(conn))
    return conn


def _wick_fixup_sql() -> str:
    conn = _run_seed()
    hits = [q for q, _ in conn.execute_calls if "strategy_id = 'wick_fill'" in q and "UPDATE mi_strategies" in q]
    assert len(hits) == 1, f"expected exactly one wick_fill fix-up UPDATE, found {len(hits)}"
    return hits[0]


def test_the_seed_no_longer_creates_a_wick_fill_row():
    conn = _run_seed()
    assert conn.executemany_calls, "the seed ran no INSERT at all — the harness is not exercising it"
    _, seed_rows = conn.executemany_calls[0]
    ids = {row[0] for row in seed_rows}
    assert "wick_fill" not in ids, "the seed still creates a wick_fill row"
    # the OTHER strategies are untouched by this removal
    assert {"magna53", "9m_day2", "shadow_orb_5m", "magna53_lowcap", "parabolic_short",
            "flag_continuation"} <= ids
    # and no seed row (any column) points at the retired table or signal
    for row in seed_rows:
        assert "mi_wick_candidates" not in row and "wick_fill" not in row


def _engine_with(rows):
    """sqlite3 stand-in for the one table the fix-up touches; the migration SQL itself is executed
    verbatim (NOW() -> CURRENT_TIMESTAMP is the only rewrite)."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE mi_strategies (strategy_id TEXT PRIMARY KEY, phase TEXT NOT NULL, "
               "enabled BOOLEAN NOT NULL DEFAULT 1, updated_at TEXT DEFAULT 'never')")
    db.executemany("INSERT INTO mi_strategies (strategy_id, phase, enabled) VALUES (?, ?, ?)", rows)
    return db


def _state(db):
    return {sid: (phase, bool(en)) for sid, phase, en in
            db.execute("SELECT strategy_id, phase, enabled FROM mi_strategies")}


def _as_registry(state):
    return {sid: Strategy(strategy_id=sid, name=sid, family="x", phase=ph, enabled=en,
                          signal_type=sid, outcomes_table="t", promotion_model="unpaired_r",
                          promotion_thresholds={}) for sid, (ph, en) in state.items()}


_OTHERS = [("magna53", "live", 1), ("parabolic_short", "shadow", 1), ("shadow_orb_5m", "shadow", 1),
           ("9m_day2", "deprecated", 0), ("flag_continuation", "deprecated", 0)]


@pytest.mark.parametrize("before", [
    ("shadow", 1),        # how prod seeded it: the row that exists today
    ("deprecated", 1),    # the BOOT-CRASH state a phase-only migration would leave behind
    ("paper", 1),         # a manual /strategy promote that must not survive the retirement
    ("deprecated", 0),    # already converged
], ids=["shadow-enabled", "deprecated-enabled", "paper-enabled", "already-converged"])
def test_the_startup_fixup_leaves_wick_fill_deprecated_and_disabled(before):
    sql = _wick_fixup_sql().replace("NOW()", "CURRENT_TIMESTAMP")
    db = _engine_with([("wick_fill", *before)] + _OTHERS)
    others_before = {k: v for k, v in _state(db).items() if k != "wick_fill"}

    db.execute(sql)
    after = _state(db)
    assert after["wick_fill"] == ("deprecated", False), f"{before} -> {after['wick_fill']}"
    # no other strategy row is touched (THE LINE: this removes ONE shadow setup, nothing else)
    assert {k: v for k, v in after.items() if k != "wick_fill"} == others_before
    # the end state is bootable: the registry assertion that guards load_strategies() passes
    assert_no_deprecated_but_enabled(_as_registry(after))


def test_the_fixup_is_idempotent_and_does_not_churn_updated_at():
    sql = _wick_fixup_sql().replace("NOW()", "CURRENT_TIMESTAMP")
    db = _engine_with([("wick_fill", "shadow", 1)] + _OTHERS)
    assert db.execute(sql).rowcount == 1
    stamp = db.execute("SELECT updated_at FROM mi_strategies WHERE strategy_id='wick_fill'").fetchone()
    assert db.execute(sql).rowcount == 0, "a converged row was rewritten again (updated_at churn every boot)"
    assert db.execute("SELECT updated_at FROM mi_strategies WHERE strategy_id='wick_fill'").fetchone() == stamp


def test_a_fresh_database_gets_no_wick_fill_row_and_the_fixup_never_inserts_or_deletes():
    sql = _wick_fixup_sql().replace("NOW()", "CURRENT_TIMESTAMP")
    db = _engine_with(_OTHERS)
    assert db.execute(sql).rowcount == 0
    assert "wick_fill" not in _state(db), "the fix-up created a row on a fresh DB"
    upper = _wick_fixup_sql().upper()
    assert "DELETE" not in upper and "INSERT" not in upper, "rows are deprecated, never deleted"


def test_a_phase_only_migration_WOULD_have_been_a_boot_failure():
    """The reason the fix-up sets BOTH columns: the 9m_day2 / flag_continuation migration sets the
    phase only. Applied to a still-enabled wick_fill row it produces deprecated+enabled, which the
    registry refuses at load. MUTATION: dropping `enabled = FALSE` from the real fix-up reddens
    test_the_startup_fixup_leaves_wick_fill_deprecated_and_disabled[shadow-enabled] (verified RED
    2026-10-17: 5 of 12 tests in this file fail with the clause removed)."""
    with pytest.raises(RuntimeError, match="deprecated strategies are still enabled"):
        assert_no_deprecated_but_enabled(_as_registry({"wick_fill": ("deprecated", True)}))
    sql = _wick_fixup_sql()
    assert re.search(r"enabled\s*=\s*FALSE", sql), "the fix-up must disable the row in the same statement"
    assert re.search(r"phase\s*=\s*'deprecated'", sql)


# ── 3. no scheduler job ────────────────────────────────────────────────────────────────────

def test_no_wick_job_is_registered_or_classified(monkeypatch):
    from tests.test_job_partition import _really_registered_job_ids
    registered = _really_registered_job_ids(monkeypatch)
    assert len(registered) > 80, f"only {len(registered)} jobs captured — the capture is wrong"
    assert not [j for j in registered if "wick" in j.lower()], "a wick job is still registered"
    for manifest in (sched.EXECUTION_OWNED_JOB_IDS, sched.INTELLIGENCE_OWNED_JOB_IDS):
        assert not [j for j in manifest if "wick" in j.lower()], "a wick job id is still in an ownership manifest"
    for name in ("JOB_WICK_FORWARD_RETURNS", "_wick_forward_returns_job"):
        assert not hasattr(sched, name), f"scheduler.{name} still exists"


# ── 4. module, adapter, DB helpers, command ────────────────────────────────────────────────

def test_the_module_adapter_helpers_and_command_are_gone():
    assert importlib.util.find_spec("agents.market_intelligence.wick_tracker") is None

    from agents.market_intelligence.strategies import adapters
    assert "wick_fill" not in adapters._ADAPTERS and not hasattr(adapters, "_adapter_wick_fill")

    from agents.market_intelligence import db
    for name in ("get_eod_9m_wick_candidates", "insert_wick_candidate", "get_unsettled_wick_candidates",
                 "update_wick_forward_returns", "get_wick_candidates_window", "get_wick_pending_candidates"):
        assert not hasattr(db, name), f"db.{name} still exists"

    from agents.market_intelligence import stocks_in_play_sources as sources
    assert not hasattr(sources, "SOURCE_WICK_FILL") and "wick_fill" not in sources.VALID_SOURCES

    from agents.market_intelligence.agent import MarketIntelligenceAgent
    assert not hasattr(MarketIntelligenceAgent, "_handle_wick_query")

    from agents.market_intelligence.brief_composer import CITED_SLASH_COMMANDS, BriefData
    assert "/wick" not in CITED_SLASH_COMMANDS
    assert not [f for f in BriefData.__dataclass_fields__ if "wick" in f]

    from scripts import preflight_command_parity as pcp
    telegram_text = pcp.TELEGRAM_FILE.read_text(encoding="utf-8")
    agent_text = pcp.AGENT_FILE.read_text(encoding="utf-8")
    direct, market = pcp.parse_command_handlers(telegram_text)
    assert "wick" not in direct | market | pcp.parse_bot_commands(telegram_text) | pcp.HIDDEN_OK
    assert "wick" not in pcp.parse_dispatch_keys(agent_text)


# ── 5. nothing writes the retired table ────────────────────────────────────────────────────

_WRITE = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)\s+mi_wick_candidates\b", re.I)
_PROD_DIRS = ("agents", "channels", "core", "shared", "scripts", "backtester")


def test_nothing_in_production_code_writes_mi_wick_candidates():
    """DERIVED over every .py file under the production directories (scripts/probes — one-off
    analysis captures, never run by the services — excluded). The DDL (CREATE TABLE / INDEX) is
    deliberately kept and is not a write."""
    # source-pin-ok: "nothing writes this table" is an invariant over the whole code population; the only way to prove an absence across every file is to read them
    files = [p for d in _PROD_DIRS if (REPO / d).is_dir() for p in (REPO / d).rglob("*.py")
             if "probes" not in p.parts]
    assert len(files) > 300, f"only {len(files)} production files scanned — the walk is wrong"
    offenders = [str(p.relative_to(REPO)) for p in files if _WRITE.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not offenders, f"these files still write mi_wick_candidates: {offenders}"


def test_the_retained_ddl_still_exists_as_history(monkeypatch):
    """The table is KEPT (like the 9M tables) — dropping history is a separate decision. BEHAVIOURAL:
    `initialize_schema` is RUN against a permissive recording pool and must still issue the CREATE
    (no source text is read). Also: it must not have grown a wick writer on the way."""
    from agents.market_intelligence import db
    statements: list[str] = []

    class _Conn:
        async def execute(self, q, *a, **k): statements.append(q); return "OK"
        async def executemany(self, q, a): statements.append(q)
        async def fetch(self, q, *a, **k): statements.append(q); return []
        async def fetchval(self, q, *a, **k): statements.append(q); return None
        async def fetchrow(self, q, *a, **k): statements.append(q); return None

    class _Ctx:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self): return _Ctx()

    async def _get_pool(): return _Pool()
    monkeypatch.setattr(db, "get_pool", _get_pool)
    asyncio.run(db.initialize_schema())

    assert len(statements) > 50, f"initialize_schema issued only {len(statements)} statements - the fake is wrong"
    assert any("CREATE TABLE IF NOT EXISTS mi_wick_candidates" in q for q in statements)
    assert not [q for q in statements if _WRITE.search(q)], "initialize_schema writes mi_wick_candidates"
