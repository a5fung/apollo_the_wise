"""#601 (2026-09-02) — a theme rename must not discard the operator's rulings.

Both operator-ruling tables are keyed on a theme's NAME: a bypassed
`mi_validation_cooldowns` row is "this ticker BELONGS" (the #213 shield), an
`mi_theme_exclusions` row is "never". A #214 rename keeps a NEW name, so:
  (a) the shield's exact (ticker, theme_name) match could never fire again — deterministic;
  (b) the exclusion's 0.35-Jaccard word-overlap net fails on exactly the BROADENING renames
      #214 performs ('Oil Refining & Marketing' -> 'Energy Infrastructure' share no word).

The in-memory `renamed_from` flag was the only rename record the validator could see, and it
dies with the run. The fix persists the rename edge (`mi_theme_renames`, written by
`_save_themes`) and expands both ruling loaders across the lineage.

THE ACCEPTANCE CASE IS CROSS-RUN. A within-run test passes on the in-memory flag and proves
nothing. Here run 1 persists the rename through the REAL `_save_themes`; run 2 is a fresh
process — a theme dict with NO `renamed_from`, validated under the NEW name through the REAL
loaders — and the no-lineage negative control shows the same run 2 would have lost the ruling.
"""
from __future__ import annotations

import contextlib
import json
from datetime import date

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import theme_engine as te

OLD = "Oil Refining & Marketing"      # the task line's real pair (prod, 2026-08-26)
NEW = "Energy Infrastructure"
RENAME_DAY = date(2026, 8, 28)


# ── an in-memory DB that persists ACROSS "runs" ──────────────────────────────────────────

class _Store:
    """What survives between processes: the three tables the fix touches."""
    def __init__(self):
        self.renames: list[tuple] = []                 # (old, new, mechanism, detail, date)
        self.protected: set[tuple[str, str]] = set()   # bypassed cooldown pairs
        self.active_cooldowns: set[tuple[str, str]] = set()
        self.exclusions: set[tuple[str, str]] = set()
        self.executed: list[tuple[str, tuple]] = []
        self.lineage_read_raises = False


class _Conn:
    def __init__(self, store: _Store):
        self.store = store

    async def execute(self, sql, *args):
        self.store.executed.append((" ".join(sql.split()), args))
        if "INSERT INTO mi_theme_renames" in sql:
            key = (args[0], args[1], args[4])
            # the fake mirrors the SQL's own UNIQUE + ON CONFLICT DO NOTHING; the SQL text
            # itself is pinned separately below so the fake cannot be the only guarantee.
            if not any((r[0], r[1], r[4]) == key for r in self.store.renames):
                self.store.renames.append(tuple(args))
            return "INSERT 0 1"
        return "OK"

    async def fetch(self, sql, *args):
        s = " ".join(sql.split())
        if "FROM mi_theme_renames" in s:
            if self.store.lineage_read_raises:
                raise RuntimeError("relation mi_theme_renames does not exist")
            return [{"old_name": r[0], "new_name": r[1]} for r in self.store.renames]
        if "FROM mi_validation_cooldowns" in s:
            src = self.store.protected if "WHERE bypassed" in s else self.store.active_cooldowns
            return [{"ticker": t, "theme_name": n} for t, n in sorted(src)]
        if "FROM mi_theme_exclusions" in s:
            return [{"ticker": t, "theme_name": n} for t, n in sorted(self.store.exclusions)]
        return []   # mi_themes prior-counter lookups etc.

    async def fetchrow(self, sql, *args):
        return None


class _Pool:
    def __init__(self, store: _Store):
        self.store = store

    @contextlib.asynccontextmanager
    async def acquire(self):
        yield _Conn(self.store)


@pytest.fixture
def store(monkeypatch):
    st = _Store()
    pool = _Pool(st)

    async def _gp():
        return pool
    # TWO namespaces: `_save_themes` resolves get_pool in theme_engine; the loaders in db.
    monkeypatch.setattr(te, "get_pool", _gp)
    monkeypatch.setattr(db, "get_pool", _gp)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(te, "_emit_cross_run_dup_probe", _noop)
    monkeypatch.setattr(te, "_canonicalize_theme_names", _noop)
    return st


@pytest.fixture
def audits(monkeypatch):
    seen: list[tuple[str, str, str]] = []

    async def _audit(event_type, summary="", detail=""):
        seen.append((event_type, summary, detail))
    monkeypatch.setattr(te, "log_audit_event", _audit)
    monkeypatch.setattr(db, "log_audit_event", _audit)
    return seen


def _llm_flags(monkeypatch, remove: list[str]):
    class _B:
        type = "text"
        text = json.dumps({"remove": remove})

    class _R:
        content = [_B()]
        stop_reason = "end_turn"

    class _M:
        async def create(self, *a, **k):
            return _R()

    class _C:
        messages = _M()
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: _C())


@pytest.fixture
def cooldown_writes(monkeypatch):
    written: list[tuple[str, str]] = []

    async def _add(tk, theme, reason=""):
        written.append((tk, theme))
        return 1
    monkeypatch.setattr(te, "add_validation_cooldown", _add)
    return written


def _renamed_theme_row() -> dict:
    """What `_rescore_existing_theme` returns on the rename night: NEW name, `renamed_from`."""
    return {"theme_date": RENAME_DAY, "name": NEW, "stage": "Nascent", "score": 12.0,
            "rs_avg": None, "description": "Energy infrastructure incl SNDK.",
            "tickers": ["SNDK", "AAA", "BBB", "CCC", "DDD"], "parent_theme": None,
            "pct_above_20sma": None, "renamed_from": OLD}


async def _run1_persist_the_rename(store: _Store) -> None:
    await te._save_themes([_renamed_theme_row()])
    assert [(r[0], r[1]) for r in store.renames] == [(OLD, NEW)], \
        "run 1 must persist the old -> new edge through the real _save_themes"


# ── 0. the brief's claims, verified against the real functions ───────────────────────────

def test_the_fuzzy_exclusion_net_really_does_not_cover_the_broadening_rename():
    """The task line's claim, with the real function: no shared word, so no match."""
    assert te._themes_are_related(OLD, NEW) is False
    assert te._get_excluded_tickers_for_theme(NEW, {OLD: {"CAR"}}) == set()


# ── 1. THE ACCEPTANCE CASE — cross-run, protection shield ────────────────────────────────

@pytest.mark.asyncio
async def test_FAILS_WITHOUT_FIX_protection_recorded_under_old_name_shields_under_new_name(
        store, audits, cooldown_writes, monkeypatch):
    """Ruling under the OLD name -> run 1 renames + saves -> run 2 (fresh process, no
    in-memory flag) validates under the NEW name and the LLM flags the protected ticker.
    The real `get_operator_protected_set` runs (protected=None -> the validator's own
    fallback fetch), against the persisted lineage only."""
    store.protected.add(("SNDK", OLD))               # the operator's /bypass, pre-rename
    await _run1_persist_the_rename(store)

    # ── run 2: nothing in memory. The theme loads as NEW, no `renamed_from` anywhere.
    _llm_flags(monkeypatch, ["SNDK"])
    survivors = await te._validate_theme_membership(
        NEW, ["SNDK", "AAA", "BBB", "CCC", "DDD"], changelog=[], protected=None)

    assert "SNDK" in survivors, "the operator's ruling must follow the rename"
    assert ("SNDK", NEW) not in cooldown_writes and ("SNDK", OLD) not in cooldown_writes
    assert any(e[0] == "validation_removal_shielded" for e in audits)


@pytest.mark.asyncio
async def test_negative_control_without_the_lineage_row_the_same_run_2_loses_the_ruling(
        store, audits, cooldown_writes, monkeypatch):
    """Same run 2, but the rename was never persisted (pre-#601 world: the in-memory flag
    was the only record and it died with run 1). This is the defect, reproduced."""
    store.protected.add(("SNDK", OLD))
    assert store.renames == []                       # no lineage
    _llm_flags(monkeypatch, ["SNDK"])
    survivors = await te._validate_theme_membership(
        NEW, ["SNDK", "AAA", "BBB", "CCC", "DDD"], changelog=[], protected=None)
    assert "SNDK" not in survivors
    assert ("SNDK", NEW) in cooldown_writes


@pytest.mark.asyncio
async def test_run_level_prefetch_path_carries_the_ruling_too(store, monkeypatch):
    """`run_theme_engine` fetches the set ONCE (#217) and threads it through `protected=`.
    Same loader, so the expanded pair must be in that set."""
    store.protected.add(("SNDK", OLD))
    await _run1_persist_the_rename(store)
    protected = await db.get_operator_protected_set()
    assert ("SNDK", NEW) in protected and ("SNDK", OLD) in protected


# ── 2. THE ACCEPTANCE CASE — cross-run, exclusions ───────────────────────────────────────

@pytest.mark.asyncio
async def test_FAILS_WITHOUT_FIX_exclusion_recorded_under_old_name_strips_under_new_name(
        store):
    """Ban filed under the OLD name; run 1 persists the rename; run 2's real loader + the
    real matcher find it by exact match on the NEW name."""
    store.exclusions.add(("CAR", OLD))
    await _run1_persist_the_rename(store)

    excl = await db.get_all_theme_exclusions()       # run 2: fresh process
    assert te._get_excluded_tickers_for_theme(NEW, excl) == {"CAR"}
    assert te._get_excluded_tickers_for_theme(OLD, excl) == {"CAR"}   # still under the old one


@pytest.mark.asyncio
async def test_negative_control_exclusion_is_lost_without_the_lineage_row(store):
    store.exclusions.add(("CAR", OLD))
    excl = await db.get_all_theme_exclusions()
    assert te._get_excluded_tickers_for_theme(NEW, excl) == set()


@pytest.mark.asyncio
async def test_read_side_expansion_never_writes_to_the_exclusions_table(store):
    """Standing rule: `mi_theme_exclusions` is user-directed bans ONLY. Following a lineage
    must be a read, never a row."""
    store.exclusions.add(("CAR", OLD))
    await _run1_persist_the_rename(store)
    await db.get_all_theme_exclusions()
    await db.get_operator_protected_set()
    writes = [sql for sql, _ in store.executed
              if "mi_theme_exclusions" in sql or "mi_validation_cooldowns" in sql]
    assert writes == []


# ── 3. the lineage record itself ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_same_night_rerun_neither_duplicates_nor_erases_the_edge(store):
    """The #539 nights ran three times. Run 2 loads the theme under the NEW name with no
    `renamed_from` — a `renamed_from` COLUMN on mi_themes would be NULLed by that upsert.
    The append-only row is untouched, and a repeated write is a no-op."""
    await _run1_persist_the_rename(store)
    rerun = {**_renamed_theme_row(), "renamed_from": None}
    await te._save_themes([rerun])
    await te._save_themes([_renamed_theme_row()])          # even a repeat of run 1
    assert [(r[0], r[1]) for r in store.renames] == [(OLD, NEW)]


def test_the_writer_is_idempotent_in_the_sql_not_just_in_the_fake():
    assert "ON CONFLICT (old_name, new_name, theme_date) DO NOTHING" in db.THEME_RENAME_INSERT_SQL
    import pathlib
    src = pathlib.Path("agents/market_intelligence/db.py").read_text()
    create = src[src.index("CREATE TABLE IF NOT EXISTS mi_theme_renames"):]
    create = create[:create.index(");")]
    assert "UNIQUE (old_name, new_name, theme_date)" in create


def test_the_writer_is_registered_in_the_deploy_gate():
    """preflight_db_updates.py's own rule: register a writer when you add one — a silent
    recorder is where a type-deduction bug hides longest, and THIS recorder going silent
    is the exact defect (#601) coming back."""
    from scripts.preflight_db_updates import SHADOW_WRITER_STATEMENTS
    assert any(sql is db.THEME_RENAME_INSERT_SQL for _, sql in SHADOW_WRITER_STATEMENTS)


@pytest.mark.asyncio
async def test_a_failed_lineage_write_is_loud_but_does_not_abort_the_save(store, audits,
                                                                          monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(te, "record_theme_rename", _boom)
    second = {**_renamed_theme_row(), "name": "Other Theme", "renamed_from": None,
              "tickers": ["XXX", "YYY"]}
    await te._save_themes([_renamed_theme_row(), second])
    inserted = [args[1] for sql, args in store.executed if "INSERT INTO mi_themes" in sql]
    assert inserted == [NEW, "Other Theme"], "the save must finish for the other themes"
    assert any(e[0] == "theme_rename_lineage_write_failed" for e in audits)


# ── 4. the resolver ──────────────────────────────────────────────────────────────────────

def test_lineage_is_transitive_and_symmetric():
    """A -> B -> C: a ruling under A applies to C; a revived A is the same identity."""
    aliases = db.resolve_theme_aliases([("A", "B"), ("B", "C"), ("X", "Y")])
    assert aliases["A"] == aliases["B"] == aliases["C"] == frozenset({"A", "B", "C"})
    assert aliases["X"] == frozenset({"X", "Y"})
    assert "Unrelated" not in aliases
    assert db.resolve_theme_aliases([]) == {}
    assert db.resolve_theme_aliases([("A", "A"), ("", "B")]) == {}


def test_unrelated_rulings_are_not_dragged_across_a_lineage():
    aliases = db.resolve_theme_aliases([(OLD, NEW)])
    assert "AI Memory & Storage" not in aliases


# ── 5. fail-open is ISOLATED to the lineage step ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_lineage_read_failure_returns_the_raw_rulings_not_an_empty_set(store):
    """The shield's own fail-open reads a RAISE as "remove". If the lineage fetch could
    take the loader down, a fresh DB or a bad migration would drop ALL protection for the
    run — strictly worse than the bug. The raw set must come back, exactly as pre-#601."""
    store.protected.add(("SNDK", "AI Memory & Storage"))
    store.exclusions.add(("CAR", "Some Theme"))
    store.lineage_read_raises = True
    assert await db.get_operator_protected_set() == {("SNDK", "AI Memory & Storage")}
    assert await db.get_all_theme_exclusions() == {"Some Theme": {"CAR"}}


# ── 6. deliberately NOT carried ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_bypassed_cooldowns_do_not_follow_the_lineage(store):
    """A machine strip under the old name is not an operator ruling; the rename's premise
    is that the members were RIGHT, so the SSoT's 'old cooldowns simply expire' stands."""
    store.active_cooldowns.add(("ZZZ", OLD))
    await _run1_persist_the_rename(store)
    assert await db.get_cooldown_set() == {("ZZZ", OLD)}
