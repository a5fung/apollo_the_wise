"""#312 — an in-memory stand-in for everything the ladder (watchdog + press) says to the DB.

There is no Postgres in the test environment, so this fake INTERPRETS the ladder modules' OWN SQL
by identity — the `tests/test_ladder_watchdog.py::_Spy` convention — and only those statements:
the watchdog's trade read (its ORDER BY and both as-of bounds), its open-positions read, the
episode / page rows the paging cadence keeps, the "tonight's row exists" lookup, the press
handler's page lock + decision writes, and the registry's compare-and-set phase UPDATE
(`update_strategy(..., expect_phase=)` — the dynamic SQL is parsed for its SET / WHERE clauses
so the CAS semantics are exercised, not mocked away). Anything else is an AssertionError: a new
statement in either module must be taught here, so the mock can never silently answer a query
it does not understand. Edit the SQL and the fake follows what it says.

Shared by the watchdog's own test file and `tests/test_312_ladder_act_step.py` so the two cannot
disagree about what the DB does.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from shared.dates import _ET

STRATEGY_COLS = ("strategy_id", "name", "family", "phase", "enabled", "signal_type", "outcomes_table",
                 "promotion_model", "promotion_thresholds", "notes", "live_real_enabled",
                 "position_size_multiplier")


def strategy_row(sid: str, phase: str, *, enabled: bool = True, live_real: bool = False,
                 signal_type: str | None = None) -> dict:
    return {"strategy_id": sid, "name": sid, "family": "orb_long", "phase": phase, "enabled": enabled,
            "signal_type": signal_type or sid, "outcomes_table": "mi_live_trades",
            "promotion_model": "unpaired_r", "promotion_thresholds": {}, "notes": None,
            "live_real_enabled": live_real, "position_size_multiplier": 1.0}


def _lp():
    """`ladder_press` is lazily resolved so the watchdog-side tests fail on a MISSING page (a real
    assertion) rather than on an ImportError when the press module does not exist yet."""
    try:
        from agents.market_intelligence import ladder_press
        return ladder_press
    except ImportError:
        return None


def _order_key(cols):
    return lambda row: tuple(row[c] for c in cols)


class LadderFakeDb:
    def __init__(self, *, strategies=(), closed_rows=None, open_positions=None, prior_audit=()):
        self.strategies: dict[str, dict] = {s["strategy_id"]: dict(s) for s in strategies}
        self.closed_rows: dict = dict(closed_rows or {})          # (signal_type, mode) -> trade rows
        self.open_positions: dict = dict(open_positions or {})    # (signal_type, mode) -> [tickers]
        self.audit: list[tuple[str, str, str]] = [(e, s, "") for e, s in prior_audit]
        self.episodes: dict[tuple[str, dt.date], dict] = {}
        self.pages: dict[int, dict] = {}
        self._next_page_id = 1
        self.calls: list[tuple[str, str, tuple]] = []
        self.txn: list[str] = []
        self.sends: list[dict] = []
        self.send_ok = True
        self.now = dt.datetime(2026, 10, 15, 16, 17, tzinfo=_ET)
        # A test can make the press handler's phase READ disagree with the row the CAS sees —
        # the concurrent-move race the single transaction must refuse.
        self.current_phase_override: dict[str, str] = {}

    # ── wiring ──────────────────────────────────────────────────────────────────────────────

    def wire(self, monkeypatch):
        """Route `db.get_pool` (the watchdog's reads, `log_audit_event`, the press handler and the
        registry's CAS) to this fake, read the registry FRESH from `self.strategies`, and record
        every Telegram page instead of sending it."""
        import agents.market_intelligence.db as dbmod
        from agents.market_intelligence import briefing
        from agents.market_intelligence.strategies import registry
        from agents.market_intelligence.strategies.registry import Strategy
        from tests.conftest import make_mock_pool

        pool, conn = make_mock_pool()
        conn.fetch = self.fetch
        conn.fetchrow = self.fetchrow
        conn.fetchval = self.fetchval
        conn.execute = self.execute
        conn.executemany = AsyncMock(side_effect=AssertionError("unexpected executemany"))
        conn.transaction = self.transaction
        self.pool, self.conn = pool, conn
        monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(registry, "get_pool", AsyncMock(return_value=pool))   # bound at import

        async def _load_all():
            return {sid: Strategy(**{k: v for k, v in s.items()}) for sid, s in self.strategies.items()}

        monkeypatch.setattr(registry, "_load_all", _load_all)
        monkeypatch.setattr(registry, "load_strategies", AsyncMock(side_effect=AssertionError(
            "the ladder must read the registry fresh, never the process cache")))

        async def _send(text, chat_id=None, parse_mode=None, reply_markup=None, **kw):
            self.sends.append({"text": text, "chat_id": chat_id, "parse_mode": parse_mode,
                               "reply_markup": reply_markup})
            return self.send_ok

        monkeypatch.setattr(briefing, "send_telegram_message", _send)
        return self

    # ── statements ──────────────────────────────────────────────────────────────────────────

    async def fetch(self, sql, *args, **kw):
        from agents.market_intelligence import ladder_watchdog as lw
        self.calls.append(("fetch", sql, args))
        if sql == lw._CLOSED_TRADES_SQL:
            rows = list(reversed(self.closed_rows.get(tuple(args[:2]), [])))   # served REVERSED
            as_of = args[2]
            if "alert_date <= $3" in sql:
                rows = [r for r in rows if r["alert_date"] <= as_of]
            if "COALESCE((closed_at AT TIME ZONE 'America/New_York')::date, alert_date) <= $3" in sql:
                rows = [r for r in rows if (r.get("closed_on_et") or r["alert_date"]) <= as_of]
            if "ORDER BY" in sql:
                cols = [c.split()[0] for c in sql.split("ORDER BY", 1)[1].split(",")]
                rows = sorted(rows, key=_order_key(cols))
            return rows
        if sql == getattr(lw, "_OPEN_POSITIONS_SQL", object()):
            return [{"ticker": t} for t in self.open_positions.get(tuple(args[:2]), [])]
        if sql.lstrip().upper().startswith("SELECT") and "FROM mi_strategies" in sql:
            return [dict(s) for s in self.strategies.values()]
        raise AssertionError(f"unexpected fetch: {sql}")

    async def fetchrow(self, sql, *args, **kw):
        from agents.market_intelligence import ladder_watchdog as lw
        lp = _lp()
        self.calls.append(("fetchrow", sql, args))
        if sql == getattr(lw, "_OPEN_EPISODE_SQL", object()):
            for (sid, _), ep in self.episodes.items():
                if sid == args[0] and ep["closed_on"] is None:
                    return dict(ep)
            return None
        if sql == getattr(lw, "_LAST_SENT_PAGE_SQL", object()):
            pages = [p for p in self.pages.values()
                     if p["strategy_id"] == args[0] and p["episode_on"] == args[1] and p["sent_at"]]
            return dict(max(pages, key=lambda p: (p["as_of"], p["id"]))) if pages else None
        if lp is not None and sql == lp._PAGE_FOR_UPDATE_SQL:
            p = self.pages.get(args[0])
            return dict(p) if p else None
        if sql.lstrip().upper().startswith("UPDATE MI_STRATEGIES"):
            return self._cas_update(sql, args)
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args, **kw):
        from agents.market_intelligence import ladder_watchdog as lw
        lp = _lp()
        self.calls.append(("fetchval", sql, args))
        if sql == lw._NIGHT_ROW_EXISTS_SQL:
            patterns = args[1:]
            for pattern in patterns:
                assert pattern.endswith("%") and "%" not in pattern[:-1] and "_" not in pattern
            return 1 if any(e == args[0] and any(s.startswith(p[:-1]) for p in patterns)
                            for e, s, _ in self.audit) else None
        if sql == getattr(lw, "_INSERT_PAGE_SQL", object()):
            sid, episode_on, as_of, phase, demote_to, breached, stats = args
            if (sid, as_of) in {(p["strategy_id"], p["as_of"]) for p in self.pages.values()}:
                assert "ON CONFLICT (strategy_id, as_of) DO NOTHING" in sql
                return None                       # UNIQUE: one page per strategy per night
            pid = self._next_page_id
            self._next_page_id += 1
            self.pages[pid] = {"id": pid, "strategy_id": sid, "episode_on": episode_on, "as_of": as_of,
                               "phase_at_page": phase, "demote_to": demote_to,
                               "breached": json.loads(breached) if isinstance(breached, str) else breached,
                               "stats": json.loads(stats) if isinstance(stats, str) else stats,
                               "sent_at": None, "decision": None, "decided_at": None, "decided_by": None}
            return pid
        if lp is not None and sql == lp._CURRENT_PHASE_SQL:
            sid = args[0]
            if sid in self.current_phase_override:
                return self.current_phase_override[sid]
            s = self.strategies.get(sid)
            return s["phase"] if s else None
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def execute(self, sql, *args, **kw):
        import agents.market_intelligence.db as dbmod
        from agents.market_intelligence import ladder_watchdog as lw
        lp = _lp()
        self.calls.append(("execute", sql, args))
        if sql == dbmod._AUDIT_INSERT_SQL:
            self.audit.append((args[0], args[1], args[2]))
            return "INSERT 0 1"
        if sql == getattr(lw, "_MARK_PAGE_SENT_SQL", object()):
            self.pages[args[0]]["sent_at"] = self.now
            return "UPDATE 1"
        if sql == getattr(lw, "_OPEN_EPISODE_INSERT_SQL", object()):
            sid, opened_on, phase = args
            self.episodes.setdefault((sid, opened_on), {"strategy_id": sid, "opened_on": opened_on,
                                                        "phase": phase, "closed_on": None, "closed_by": None})
            return "INSERT 0 1"
        if sql == getattr(lw, "_CLOSE_EPISODE_SQL", object()):
            closed_on, closed_by, sid, opened_on = args
            ep = self.episodes[(sid, opened_on)]
            if ep["closed_on"] is None:
                ep["closed_on"], ep["closed_by"] = closed_on, closed_by
            return "UPDATE 1"
        if lp is not None and sql == lp._DECIDE_PAGE_SQL:
            decision, user_id, page_id = args
            p = self.pages[page_id]
            p["decision"], p["decided_by"], p["decided_at"] = decision, user_id, self.now
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute: {sql}")

    @asynccontextmanager
    async def transaction(self):
        self.txn.append("begin")
        try:
            yield
        except BaseException:
            self.txn.append("rollback")
            raise
        else:
            self.txn.append("commit")

    # ── the registry's phase writer, interpreted ────────────────────────────────────────────

    def _cas_update(self, sql, args):
        """`UPDATE mi_strategies SET a = $1, ... WHERE strategy_id = $n [AND phase = $m] RETURNING …`."""
        m = re.search(r"SET (.*?) WHERE strategy_id = \$(\d+)(?: AND phase = \$(\d+))?\s*RETURNING", sql, re.S)
        assert m, f"CAS shape changed: {sql}"
        sets = [s.strip() for s in m.group(1).split(",")]
        sid = args[int(m.group(2)) - 1]
        row = self.strategies.get(sid)
        if row is None:
            return None
        if m.group(3) is not None and row["phase"] != args[int(m.group(3)) - 1]:
            return None
        for s in sets:
            col, _, val = s.partition(" = ")
            col = col.strip()
            if val.strip().startswith("$"):
                row[col] = args[int(val.strip().lstrip("$").split("::")[0]) - 1]
        self.calls.append(("phase_write", sid, (row["phase"],)))
        return {c: row[c] for c in STRATEGY_COLS}

    # ── convenience ─────────────────────────────────────────────────────────────────────────

    def audit_rows(self, event):
        return [(s, d) for e, s, d in self.audit if e == event]

    @property
    def phase_writes(self):
        return [c for c in self.calls if c[0] == "phase_write"]

    @property
    def statements(self):
        return [c for c in self.calls if c[0] != "phase_write"]
