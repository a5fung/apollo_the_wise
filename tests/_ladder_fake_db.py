"""#312 — an in-memory stand-in for everything the ladder (watchdog + press) says to the DB.

There is no Postgres in the test environment, so this fake INTERPRETS the ladder modules' OWN SQL
by identity — the `tests/test_ladder_watchdog.py::_Spy` convention — and only those statements:
the watchdog's trade read (its ORDER BY and both as-of bounds), its open-positions read, the
episode / page rows the paging cadence keeps, the "tonight's row exists" lookup, the press
handler's page lock + decision writes + episode / decision re-reads, the registry's one-row fresh
read (`registry._SELECT_ONE_SQL`) and its compare-and-set phase UPDATE (`update_strategy(...,
expect_phase=)` — the dynamic SQL is parsed for its SET / WHERE clauses so the CAS semantics are
exercised, not mocked away). Anything else is an AssertionError: a new statement in either module
must be taught here, so the mock can never silently answer a query it does not understand. Edit
the SQL and the fake follows what it says.

TRANSACTIONS ARE MODELLED, NOT JUST LABELLED (#312 review, finding 3). `transaction()` snapshots
the tables at BEGIN; an exception restores them (ROLLBACK). A statement the test makes fail
(`fail_audit_events`) raises AND marks the transaction ABORTED, every later statement in it raises
("current transaction is aborted"), and a clean exit of an aborted transaction RESTORES the
snapshot — Postgres answers that COMMIT with a ROLLBACK and no error, which is exactly the hole
the press's strict audit writes close. `silent_rollback_on_commit` restores on a clean exit with
no failure at all, so a caller that trusts its own intent instead of re-reading is caught.

Shared by the watchdog's own test file and `tests/test_312_ladder_act_step.py` so the two cannot
disagree about what the DB does.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import agents.market_intelligence.db as dbmod
from agents.market_intelligence import ladder_press as lp
from agents.market_intelligence import ladder_watchdog as lw
from agents.market_intelligence.strategies import registry
from shared.dates import _ET

# The registry's own column list (its single source), so the fake's fresh read and CAS RETURNING
# carry exactly the columns the real statements select.
STRATEGY_COLS = tuple(c.strip() for c in registry._STRATEGY_COLUMNS.split(",") if c.strip())


def strategy_row(sid: str, phase: str, *, enabled: bool = True, live_real: bool = False,
                 signal_type: str | None = None) -> dict:
    return {"strategy_id": sid, "name": sid, "family": "orb_long", "phase": phase, "enabled": enabled,
            "signal_type": signal_type or sid, "outcomes_table": "mi_live_trades",
            "promotion_model": "unpaired_r", "promotion_thresholds": {}, "notes": None,
            "live_real_enabled": live_real, "position_size_multiplier": 1.0}


def operator_env(monkeypatch, user_id: int) -> None:
    """The env the press and the typed-command paths read: `user_id` is the one allowlisted
    operator, a bot token is set, and no paper chat is configured."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(user_id))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID", raising=False)


def rs(value, n):
    """A flat R series: `value`, `n` times."""
    return [value] * n


def one_row(r, *, id, alert_date, closed_on_et="same-day", exit_rule=None):
    """One closed row with realised R = `r` at an explicit id / entry date / close date.
    Uncapped: entry_shares=1, entry 101, hard_stop 1 → risk_placed = 100, so total_pnl = 100·R
    reproduces the R series exactly (the #586 fixture shape). `closed_on_et` (the ET date of
    `closed_at`) is NOT selected by the watchdog, only read by the mock DB's as-of bound; the
    default is a same-day close, `None` is a legacy row with no `closed_at`."""
    return {"id": id, "total_pnl": 100.0 * r, "risk_dollars_actual": None, "entry_shares": 1.0,
            "entry_price": 101.0, "hard_stop": 1.0, "alert_date": alert_date,
            "closed_on_et": alert_date if closed_on_et == "same-day" else closed_on_et,
            "signal_type": "magna53", "exit_rule": exit_rule}


def closed_rows(series, *, exit_rule=None, first_id=1):
    """A series of same-day-close rows (`one_row`); `id` ascends with `alert_date`."""
    base = dt.date(2026, 7, 1)
    return [one_row(r, id=first_id + i, alert_date=base + dt.timedelta(days=i),
                    exit_rule=exit_rule) for i, r in enumerate(series)]


def _order_key(cols):
    return lambda row: tuple(row[c] for c in cols)


class _AbortedTransaction(RuntimeError):
    """What asyncpg raises for every statement after a failure inside a transaction."""


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
        # True / False for every send, or a list consumed one send at a time (a blip, then success).
        self.send_ok = True
        self.now = dt.datetime(2026, 10, 15, 16, 17, tzinfo=_ET)
        # A test can make the press handler's phase READ disagree with the row the CAS sees —
        # the concurrent-move race the single transaction must refuse.
        self.current_phase_override: dict[str, str] = {}
        # Transaction modelling (see the module docstring).
        self.fail_audit_events: set[str] = set()
        self.silent_rollback_on_commit = False
        self._in_txn = False
        self._aborted = False
        self._snapshot = None
        # One-shot hook run before the registry's FRESH one-row read answers (the race a press or a
        # typed command wins between the nightly's registry read and its page insert).
        self.fresh_read_hook = None

    # ── wiring ──────────────────────────────────────────────────────────────────────────────

    def wire(self, monkeypatch):
        """Route `db.get_pool` (the watchdog's reads, `log_audit_event`, the press handler and the
        registry's CAS + fresh read) to this fake, read the registry FRESH from `self.strategies`,
        and record every Telegram page instead of sending it."""
        from agents.market_intelligence import briefing
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
        # The retries without the sleeps.
        monkeypatch.setattr(lw, "SEND_RETRY_DELAYS", (0.0, 0.0))

        async def _send(text, chat_id=None, parse_mode=None, reply_markup=None, **kw):
            self.sends.append({"text": text, "chat_id": chat_id, "parse_mode": parse_mode,
                               "reply_markup": reply_markup})
            if isinstance(self.send_ok, list):
                return self.send_ok.pop(0) if self.send_ok else True
            return self.send_ok

        monkeypatch.setattr(briefing, "send_telegram_message", _send)
        return self

    # ── transaction modelling ───────────────────────────────────────────────────────────────

    def _state(self):
        return copy.deepcopy((self.strategies, self.pages, self.episodes, self.audit, self._next_page_id))

    def _restore(self, snap):
        self.strategies, self.pages, self.episodes, self.audit, self._next_page_id = copy.deepcopy(snap)

    def _guard(self):
        if self._in_txn and self._aborted:
            raise _AbortedTransaction("current transaction is aborted, commands ignored until end of "
                                      "transaction block")

    @asynccontextmanager
    async def transaction(self):
        self.txn.append("begin")
        self._in_txn, self._aborted, self._snapshot = True, False, self._state()
        try:
            yield
        except BaseException:
            self._restore(self._snapshot)
            self.txn.append("rollback")
            raise
        else:
            if self._aborted or self.silent_rollback_on_commit:
                # Postgres: COMMIT on an aborted transaction is a ROLLBACK, answered without error.
                self._restore(self._snapshot)
                self.txn.append("rollback")
            else:
                self.txn.append("commit")
        finally:
            self._in_txn, self._aborted, self._snapshot = False, False, None

    # ── statements ──────────────────────────────────────────────────────────────────────────

    async def fetch(self, sql, *args, **kw):
        self.calls.append(("fetch", sql, args))
        self._guard()
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
        if sql == lw._OPEN_POSITIONS_SQL:
            return [{"ticker": t} for t in self.open_positions.get(tuple(args[:2]), [])]
        if sql == lw._OPEN_EPISODES_OF_SQL:
            # DISTINCT ON (strategy_id) … ORDER BY strategy_id, opened_on DESC: the latest open
            # episode of each strategy named in the array, served in REVERSE so a caller that
            # trusts the row order (rather than its own) is caught.
            latest: dict[str, dict] = {}
            for (sid, opened_on), ep in self.episodes.items():
                if sid in args[0] and ep["closed_on"] is None:
                    if sid not in latest or opened_on > latest[sid]["opened_on"]:
                        latest[sid] = ep
            return [{"strategy_id": sid, "opened_on": ep["opened_on"], "phase": ep["phase"]}
                    for sid, ep in sorted(latest.items(), reverse=True)]
        if sql.lstrip().upper().startswith("SELECT") and "FROM mi_strategies" in sql:
            return [dict(s) for s in self.strategies.values()]
        raise AssertionError(f"unexpected fetch: {sql}")

    async def fetchrow(self, sql, *args, **kw):
        self.calls.append(("fetchrow", sql, args))
        self._guard()
        if sql == lw._OPEN_EPISODE_SQL:
            for (sid, _), ep in self.episodes.items():
                if sid == args[0] and ep["closed_on"] is None:
                    return dict(ep)
            return None
        if sql == lw._LAST_SENT_PAGE_SQL:
            pages = [p for p in self.pages.values()
                     if p["strategy_id"] == args[0] and p["episode_on"] == args[1] and p["sent_at"]]
            return dict(max(pages, key=lambda p: (p["as_of"], p["id"]))) if pages else None
        if sql == lp._PAGE_FOR_UPDATE_SQL:
            p = self.pages.get(args[0])
            return dict(p) if p else None
        if sql == lp._EPISODE_STATE_SQL:
            ep = self.episodes.get((args[0], args[1]))
            return {"closed_on": ep["closed_on"], "closed_by": ep["closed_by"]} if ep else None
        if sql == registry._SELECT_ONE_SQL:
            if self.fresh_read_hook is not None:
                hook, self.fresh_read_hook = self.fresh_read_hook, None
                hook()
            s = self.strategies.get(args[0])
            return {c: s[c] for c in STRATEGY_COLS} if s else None
        if sql.lstrip().upper().startswith("UPDATE MI_STRATEGIES"):
            return self._cas_update(sql, args)
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args, **kw):
        self.calls.append(("fetchval", sql, args))
        self._guard()
        if sql == lw._NIGHT_ROW_EXISTS_SQL:
            patterns = args[1:]
            for pattern in patterns:
                assert pattern.endswith("%") and "%" not in pattern[:-1] and "_" not in pattern
            return 1 if any(e == args[0] and any(s.startswith(p[:-1]) for p in patterns)
                            for e, s, _ in self.audit) else None
        if sql == lw._INSERT_PAGE_SQL:
            sid, episode_on, as_of, phase, demote_to, breached, stats = args[:7]
            token = args[7] if len(args) > 7 else None
            if (sid, as_of) in {(p["strategy_id"], p["as_of"]) for p in self.pages.values()}:
                assert "ON CONFLICT (strategy_id, as_of) DO NOTHING" in sql
                return None                       # UNIQUE: one page per strategy per night
            pid = self._next_page_id
            self._next_page_id += 1
            self.pages[pid] = {"id": pid, "strategy_id": sid, "episode_on": episode_on, "as_of": as_of,
                               "phase_at_page": phase, "demote_to": demote_to,
                               "breached": json.loads(breached) if isinstance(breached, str) else breached,
                               "stats": json.loads(stats) if isinstance(stats, str) else stats,
                               "token": token, "sent_at": None, "decision": None, "decided_at": None,
                               "decided_by": None}
            return pid
        if sql == lp._CURRENT_PHASE_SQL:
            sid = args[0]
            if sid in self.current_phase_override:
                return self.current_phase_override[sid]
            s = self.strategies.get(sid)
            return s["phase"] if s else None
        if sql == lp._PAGE_DECISION_SQL:
            p = self.pages.get(args[0])
            return p["decision"] if p else None
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def execute(self, sql, *args, **kw):
        self.calls.append(("execute", sql, args))
        self._guard()
        if sql == dbmod._AUDIT_INSERT_SQL:
            if args[0] in self.fail_audit_events:
                if self._in_txn:
                    self._aborted = True
                raise RuntimeError("canceling statement due to statement timeout")
            self.audit.append((args[0], args[1], args[2]))
            return "INSERT 0 1"
        if sql == lw._MARK_PAGE_SENT_SQL:
            self.pages[args[0]]["sent_at"] = self.now
            return "UPDATE 1"
        if sql == lw._OPEN_EPISODE_INSERT_SQL:
            sid, opened_on, phase = args
            self.episodes.setdefault((sid, opened_on), {"strategy_id": sid, "opened_on": opened_on,
                                                        "phase": phase, "closed_on": None, "closed_by": None})
            return "INSERT 0 1"
        if sql == lw._CLOSE_EPISODE_SQL:
            closed_on, closed_by, sid, opened_on = args
            ep = self.episodes[(sid, opened_on)]
            if ep["closed_on"] is None:
                ep["closed_on"], ep["closed_by"] = closed_on, closed_by
            return "UPDATE 1"
        if sql == lw._STALE_OPEN_PAGES_SQL:
            sid, episode_on = args
            n = 0
            for p in self.pages.values():
                if p["strategy_id"] == sid and p["episode_on"] == episode_on and p["decision"] is None:
                    p["decision"], p["decided_at"] = "stale", self.now
                    n += 1
            return f"UPDATE {n}"
        if sql == lp._DECIDE_PAGE_SQL:
            decision, user_id, page_id = args
            p = self.pages[page_id]
            if p["decision"] is None:
                p["decision"], p["decided_by"], p["decided_at"] = decision, user_id, self.now
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute: {sql}")

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

    def token_of(self, page_id: int) -> str:
        """The page's own button token (what the real buttons carry)."""
        return self.pages[page_id]["token"]
