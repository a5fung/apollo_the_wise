"""#687 toggle-OFF convergence harness (cut-back round, 2026-10-02).

Drives FIXED toggle-OFF scenarios through the code tree it is RUN IN and prints, per scenario,
every broker-client call (method + bound arguments), every Telegram page, the return value and the
end state of the fake book. Run it in two trees and diff the logs:

    python tests/_convergence_687_harness.py --out <file>            # this tree
    (copied into a `git worktree` of the pinned pre-#687 baseline and run there — see
     scripts/probes/_687/capture_toggle_off_baseline.sh)

`tests/test_687_toggle_off_convergence.py` runs it on this tree and asserts the log equals the
recorded baseline except an explicit, named allow-list (fixes (a)-(f), the 61a6c479 sync hunk,
rulings (1)-(3)).

THE FAKE WORLD is version-agnostic on purpose: one in-memory book (trades / exit orders / audit
log) answered by a tiny SQL interpreter, and one fake broker. Both code trees see the same world
and only their own logic differs. SQL the interpreter does not understand is answered permissively
and LISTED under `_unknown_sql` (never compared) so a false difference is debuggable.

Recording boundary = the `alpaca_client` module functions (every public coroutine is wrapped, so a
stray call of ANY method is recorded), the `send_telegram_message` name in each module, plus one
SDK-boundary scenario for #687 (d) (`close_position(qty)` is only visible at the `TradingClient`).
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TODAY = date(2026, 10, 6)                       # a Tuesday
NOW_UTC = datetime(2026, 10, 6, 20, 45, tzinfo=timezone.utc)   # 16:45 ET

LIVE_ORDER_STATUSES = {"new", "accepted", "held", "pending_new", "partially_filled",
                       "accepted_for_bidding", "pending_replace"}


def _norm(sql: str) -> str:
    lines = [re.sub(r"--.*$", "", ln) for ln in str(sql).splitlines()]
    return " ".join(" ".join(lines).split())


def _split_top(s: str, sep: str = ",") -> list[str]:
    out, depth, cur, i = [], 0, "", 0
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if depth == 0 and s.startswith(sep, i):
            out.append(cur.strip())
            cur = ""
            i += len(sep)
            continue
        cur += ch
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        seq = sorted(x, key=str) if isinstance(x, set) else x
        return [_jsonable(v) for v in seq]
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, (int, float, str, bool)) or x is None:
        return x
    from unittest import mock
    if isinstance(x, mock.NonCallableMock):
        # an alpaca-py request object under the suite's SDK stubs (tests/conftest.py): record
        # WHICH class was built and with what — e.g. ClosePositionRequest(qty='2')
        parent = getattr(x, "_mock_new_parent", None)
        call = getattr(parent, "call_args", None)
        return {"__type__": x._extract_mock_name().split(".")[-1].rstrip("()"),
                "built_with": _jsonable(dict(call.kwargs)) if call else None}
    if hasattr(x, "model_dump"):
        return {"__type__": type(x).__name__, **_jsonable(x.model_dump(exclude_none=True))}
    return repr(x)


# ══════════════════════════════════════════════════════════════════════════════════════════
# The fake book + a tiny SQL interpreter
# ══════════════════════════════════════════════════════════════════════════════════════════

class World:
    def __init__(self):
        self.trades: dict[int, dict] = {}
        self.orders: list[dict] = []          # mi_live_orders
        self.audits: list[dict] = []          # mi_audit_log
        self.closed_losses_today = 0.0
        self.foreign_locks: set[int] = set()  # trade ids whose lock another process holds
        self.unknown: list[str] = []
        # broker
        self.positions: dict[str, dict] = {}
        self.broker_orders: list[dict] = []
        self.close_errors: list = []          # raised by successive close_position calls (None = ok)
        self.place_errors: list = []          # raised by successive place_stop_order calls
        self.opg_errors: list = []
        self.calls: list = []
        self.pages: list = []
        self.index_today: dict | None = None
        self.index_prior: list = []
        self.n = 0

    def next_id(self, prefix):
        self.n += 1
        return f"{prefix}-{self.n}"

    # ── broker model ──
    def broker_order(self, oid):
        return next((o for o in self.broker_orders if o["id"] == oid), None)


def _trade_atom(atom: str, row: dict, args: tuple, w: World) -> bool:
    a = atom.strip()
    while a.startswith("(") and a.endswith(")") and a.count("(") == a.count(")"):
        inner = a[1:-1]
        if inner.count("(") == inner.count(")"):
            a = inner.strip()
        else:
            break

    def val(tok):
        tok = tok.strip()
        m = re.fullmatch(r"\$(\d+)(::[\w\[\]]+)?", tok)
        if m:
            return args[int(m.group(1)) - 1]
        if tok.upper() == "NULL":
            return None
        if tok.startswith("'") and tok.endswith("'"):
            return tok[1:-1]
        try:
            return float(tok)
        except ValueError:
            return ("?", tok)

    if "AT TIME ZONE" in a and "closed_at" in a:
        return row.get("closed_on") == val(a.split("=")[-1])
    if re.search(r"NOW\(\)", a) and "<" in a:
        return True
    m = re.fullmatch(r"(\w+) IS NOT DISTINCT FROM (\S+)", a)
    if m:
        return row.get(m.group(1)) == val(m.group(2))
    m = re.fullmatch(r"(\w+) IS (NOT )?NULL", a)
    if m:
        is_null = row.get(m.group(1)) is None
        return (not is_null) if m.group(2) else is_null
    m = re.fullmatch(r"(\w+) = ANY\((\$\d+)\)", a)
    if m:
        return row.get(m.group(1)) in val(m.group(2))
    m = re.fullmatch(r"(\w+) != ALL\((\$\d+)::text\[\]\)", a)
    if m:
        return row.get(m.group(1)) not in val(m.group(2))
    m = re.fullmatch(r"(\w+) (NOT )?IN \((.*)\)", a)
    if m:
        vals = [val(t) for t in _split_top(m.group(3))]
        hit = row.get(m.group(1)) in vals
        return (not hit) if m.group(2) else hit
    m = re.fullmatch(r"(\w+) (=|<>|!=|>|<|>=|<=) (.+)", a)
    if m:
        lhs, op, rv = row.get(m.group(1)), m.group(2), val(m.group(3))
        if isinstance(rv, tuple):
            w.unknown.append(f"atom:{a}")
            return True
        if op == "=":
            return lhs == rv
        if op in ("<>", "!="):
            return lhs != rv
        if lhs is None:
            return False
        return {">": lhs > rv, "<": lhs < rv, ">=": lhs >= rv, "<=": lhs <= rv}[op]
    m = re.fullmatch(r"\(?dead_stop_price IS NULL OR \$2 > dead_stop_price\)?", a)
    if m:
        return row.get("dead_stop_price") is None or args[1] > row["dead_stop_price"]
    w.unknown.append(f"atom:{a}")
    return True


def _where(sql: str) -> str:
    m = re.search(r" WHERE (.*?)(?: RETURNING .*| ORDER BY .*| LIMIT .*| FOR UPDATE.*)?$", sql)
    return m.group(1) if m else ""


def _match(sql: str, rows, args, w):
    where = _where(sql)
    if not where:
        return list(rows)
    atoms = re.split(r" AND (?![^()]*\))", where)
    return [r for r in rows if all(_trade_atom(x, r, args, w) for x in atoms)]


def _apply_set(sql: str, row: dict, args: tuple):
    m = re.search(r" SET (.*?) WHERE ", sql)
    for assign in _split_top(m.group(1)):
        col, expr = [x.strip() for x in assign.split("=", 1)]
        em = re.fullmatch(r"\$(\d+)(::\w+)?", expr)
        if em:
            v = args[int(em.group(1)) - 1]
            if em.group(2) == "::jsonb" and isinstance(v, str):
                v = json.loads(v)
            row[col] = v
        elif expr.upper() == "NULL":
            row[col] = None
        elif expr.upper() == "NOW()":
            row[col] = "NOW"
            if col == "closed_at":
                row["closed_on"] = TODAY
        elif expr.startswith("'"):
            row[col] = expr.strip("'")
        elif "COALESCE" in expr or "||" in expr:
            pass                                              # raw_response snapshot merge
        else:
            row[col] = ("expr", expr)


def _returning(sql: str, row: dict):
    m = re.search(r" RETURNING (.*)$", sql)
    if not m:
        return None
    cols = m.group(1).strip()
    if cols == "*":
        return dict(row)
    return {c.strip(): row.get(c.strip()) for c in cols.split(",")}


class FakeConn:
    def __init__(self, w: World):
        self.w = w

    # ---- dispatch ----
    async def _run(self, kind, sql, *args, **_kw):
        w, s = self.w, _norm(sql)
        if "pg_advisory_lock" in s or "pg_advisory_unlock" in s:
            return True
        if "pg_try_advisory_lock" in s:
            return int(args[1]) not in w.foreign_locks
        if "mi_audit_log" in s:
            return self._audit_query(kind, s, args)
        if "mi_safeguard_state" in s or "mi_strategies" in s:
            return None if kind != "fetch" else []
        if s.startswith("INSERT INTO mi_live_orders"):
            return self._insert_order(s, args)
        if "mi_live_orders" in s:
            return self._orders_query(kind, s, args)
        if "mi_live_trades" in s:
            return self._trades_query(kind, s, args)
        w.unknown.append(f"{kind}:{s[:160]}")
        return [] if kind == "fetch" else None

    async def fetch(self, sql, *a, **k):
        return await self._run("fetch", sql, *a, **k)

    async def fetchrow(self, sql, *a, **k):
        return await self._run("fetchrow", sql, *a, **k)

    async def fetchval(self, sql, *a, **k):
        return await self._run("fetchval", sql, *a, **k)

    async def execute(self, sql, *a, **k):
        r = await self._run("execute", sql, *a, **k)
        return r if isinstance(r, str) else "OK"

    # ---- mi_live_trades ----
    def _trades_query(self, kind, s, args):
        w = self.w
        rows = list(w.trades.values())
        if s.startswith("UPDATE mi_live_trades"):
            hit = _match(s, rows, args, w)
            for r in hit:
                _apply_set(s, r, args)
            if kind == "execute":
                return f"UPDATE {len(hit)}"
            ret = _returning(s, hit[0]) if hit else None
            if kind == "fetchval":
                return next(iter(ret.values())) if ret else None
            return ret
        hit = _match(s, rows, args, w)
        if s.startswith("SELECT COUNT(*)"):
            return len(hit)
        if "SUM(total_pnl)" in s:
            return w.closed_losses_today
        if kind == "fetch":
            return [dict(r) for r in hit]
        if kind == "fetchrow":
            return dict(hit[0]) if hit else None
        if kind == "fetchval":
            col = re.match(r"SELECT (\w+) FROM", s)
            return hit[0].get(col.group(1)) if (hit and col) else None
        return None

    # ---- mi_live_orders ----
    def _orders_query(self, kind, s, args):
        w = self.w
        if s.startswith("UPDATE mi_live_orders"):
            hit = _match(s, w.orders, args, w)
            for r in hit:
                _apply_set(s, r, args)
            if kind == "execute":
                return f"UPDATE {len(hit)}"
            return _returning(s, hit[0]) if hit else None
        hit = _match(s, w.orders, args, w)
        if "BOOL_OR" in s:
            return {"reserved": int(sum(float(r["qty"]) for r in hit)),
                    "full_pending": any(r["purpose"] == "full_exit" for r in hit)}
        if "SUM(qty)" in s:
            return int(sum(float(r["qty"]) for r in hit))
        if kind == "fetch":
            return [dict(r) for r in hit]
        if kind == "fetchrow":
            return dict(hit[0]) if hit else None
        if kind == "fetchval":
            col = re.match(r"SELECT (\w+) FROM", s)
            return hit[0].get(col.group(1)) if (hit and col) else None
        return None

    def _insert_order(self, s, args):
        w = self.w
        m = re.search(r"\((.*?)\) VALUES \((.*?)\)", s)
        cols = [c.strip() for c in m.group(1).split(",")]
        vals = []
        for v in _split_top(m.group(2)):
            vm = re.fullmatch(r"\$(\d+)(::\w+)?", v)
            vals.append(args[int(vm.group(1)) - 1] if vm else v.strip("'"))
        row = dict(zip(cols, vals))
        row.pop("raw_response", None)
        if any(o["alpaca_order_id"] == row["alpaca_order_id"] for o in w.orders):
            return "INSERT 0 0"
        w.orders.append(row)
        return "INSERT 0 1"

    # ---- mi_audit_log ----
    def _audit_query(self, kind, s, args):
        w = self.w
        types = None
        m = re.search(r"event_type IN \((.*?)\)", s)
        if m:
            types = {t.strip().strip("'") for t in m.group(1).split(",")}
        m = re.search(r"event_type = '(\w+)'", s)
        if m:
            types = {m.group(1)}
        m = re.search(r"event_type = \$(\d+)", s)
        if m:
            types = {args[int(m.group(1)) - 1]}
        rows = [a for a in w.audits if types is None or a["event_type"] in types]
        m = re.search(r"summary LIKE \$(\d+)", s)
        if m:
            prefix = str(args[int(m.group(1)) - 1]).rstrip("%")
            rows = [a for a in rows if a["summary"].startswith(prefix)]
        m = re.search(r"->> 'trade_id' = \$(\d+)", s)
        if m:
            tid = str(args[int(m.group(1)) - 1])
            rows = [a for a in rows if str(_detail(a).get("trade_id")) == tid]
        m = re.search(r"->> 'skip_code' = \$(\d+)", s)
        if m:
            code = args[int(m.group(1)) - 1]
            rows = [a for a in rows if _detail(a).get("skip_code") == code]
        if s.startswith("SELECT COUNT(*)"):
            return len(rows)
        if s.startswith("SELECT 1"):
            return 1 if rows else None
        if kind == "fetch":
            return [dict(r) for r in reversed(rows)]
        if kind == "fetchrow":
            return dict(rows[-1]) if rows else None
        return None


def _detail(a):
    try:
        return json.loads(a.get("detail") or "{}")
    except ValueError:
        return {}


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    def __await__(self):
        async def _c():
            return self.conn
        return _c().__await__()

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *e):
        return False


class FakePool:
    def __init__(self, w):
        self.conn = FakeConn(w)

    def acquire(self, *a, **k):
        return _Acquire(self.conn)

    async def release(self, *a, **k):
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════
# The fake broker (wrapped at the alpaca_client function boundary)
# ══════════════════════════════════════════════════════════════════════════════════════════

def _broker_impl(w: World):
    def _live(o):
        return o["status"] in LIVE_ORDER_STATUSES

    async def get_position(ticker, account_mode=None):
        p = w.positions.get(ticker)
        return dict(p) if p else None

    async def get_all_positions(account_mode=None, **k):
        return [{"symbol": t, "qty": p["qty"], "qty_available": p["qty_available"]}
                for t, p in w.positions.items() if p["qty"] > 0]

    async def get_open_orders(ticker=None, account_mode=None, raise_on_error=False, **k):
        return [dict(o) for o in w.broker_orders
                if _live(o) and (ticker is None or o["symbol"] == ticker)]

    async def get_order(order_id, account_mode=None, **k):
        o = w.broker_order(order_id)
        return dict(o) if o else None

    async def cancel_order(order_id, account_mode=None):
        o = w.broker_order(order_id)
        if o and _live(o):
            o["status"] = "canceled"
            p = w.positions.get(o["symbol"])
            if p:
                p["qty_available"] = p["qty_available"] + (float(o["qty"]) - float(o.get("filled_qty") or 0))
        return True

    def _new_sell(ticker, qty, otype, status, **extra):
        oid = w.next_id("sell" if otype != "stop" else "stop")
        o = {"id": oid, "symbol": ticker, "side": "sell", "type": otype, "qty": float(qty),
             "filled_qty": 0.0, "status": status, "order_class": "simple", **extra}
        w.broker_orders.append(o)
        p = w.positions.get(ticker)
        if p:
            p["qty_available"] = max(p["qty_available"] - float(qty), 0.0)
        return o

    async def close_position(ticker, qty=None, account_mode=None):
        err = w.close_errors.pop(0) if w.close_errors else None
        if err:
            raise err
        p = w.positions.get(ticker) or {"qty": 0}
        o = _new_sell(ticker, qty if qty is not None else p["qty"], "market", "accepted")
        return {"id": o["id"], "status": "accepted", "qty": o["qty"]}

    async def place_stop_order(ticker, qty, stop_price, account_mode=None, client_order_id=None,
                               **k):
        err = w.place_errors.pop(0) if w.place_errors else None
        if err:
            raise err
        o = _new_sell(ticker, qty, "stop", "new", stop_price=float(stop_price))
        return {"id": o["id"], "status": "new", "stop_price": float(stop_price)}

    async def place_market_on_open_sell(ticker, qty, account_mode=None, client_order_id=None):
        err = w.opg_errors.pop(0) if w.opg_errors else None
        if err:
            raise err
        o = _new_sell(ticker, qty, "market", "accepted")
        return {"id": o["id"], "status": "accepted"}

    async def get_account(account_mode=None):
        return {"equity": 5000.0, "cash": 5000.0, "buying_power": 10000.0}

    return {f.__name__: f for f in (get_position, get_all_positions, get_open_orders, get_order,
                                    cancel_order, close_position, place_stop_order,
                                    place_market_on_open_sell, get_account)}


def _install(w: World):
    """Patch every module the scenarios touch onto the fake world. Returns an undo list."""
    from agents.market_intelligence import briefing, collector, db
    from agents.market_intelligence.broker import alpaca_client as ac
    from agents.market_intelligence.broker import live_tracker as lt
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence.broker import trade_stream as ts
    import agents.market_intelligence.scheduler as sched

    undo = []

    def patch(obj, name, value):
        if hasattr(obj, name):
            undo.append((obj, name, getattr(obj, name)))
        else:
            undo.append((obj, name, None))
        setattr(obj, name, value)

    pool = FakePool(w)

    async def _get_pool(*a, **k):
        return pool

    async def _audit(event_type, summary="", detail="", *a, **k):
        w.audits.append({"event_type": event_type, "summary": summary or "",
                         "detail": detail or "", "created_at": NOW_UTC})

    async def _send(msg, *a, **k):
        w.pages.append(str(msg))
        return True

    from agents.market_intelligence import constants

    async def _job_failure(job, err, *a, **k):
        w.pages.append(f"[job failure] {job}: {err}")

    for mod in (om, ts, lt, db, sched):
        patch(mod, "get_pool", _get_pool)
        patch(mod, "log_audit_event", _audit)
    for mod in (om, ts, lt, briefing, sched):
        patch(mod, "send_telegram_message", _send)
    patch(sched, "notify_job_failure", _job_failure)
    patch(constants, "LIVE_TRADING_ENABLED", True)
    async def _index_history(ticker, start, end, *a, **k):
        if start == end:
            return [dict(w.index_today)] if w.index_today else []
        return [dict(b) for b in w.index_prior]

    patch(lt, "get_index_history", _index_history)
    patch(collector, "et_today", lambda: TODAY)
    patch(lt, "et_today", lambda: TODAY)
    patch(lt, "LIVE_TRADING_ENABLED", True)

    impl = _broker_impl(w)
    for name, fn in list(vars(ac).items()):
        if name.startswith("_") or not inspect.iscoroutinefunction(fn) or fn.__module__ != ac.__name__:
            continue
        sig = inspect.signature(fn)

        def _make(name=name, sig=sig):
            async def _rec(*a, **k):
                try:
                    bound = sig.bind(*a, **k)
                    bound.apply_defaults()
                    rec = dict(bound.arguments)
                except TypeError:
                    rec = {"args": list(a), **k}
                w.calls.append({"method": name, "args": _jsonable(rec)})
                if name in impl:
                    return await impl[name](*a, **k)
                return None
            return _rec
        patch(ac, name, _make())

    counter = {"n": 0}

    def _coid(account_mode, strategy_id, ticker):
        counter["n"] += 1
        return f"apollo_{account_mode}_{strategy_id}_{ticker}_{counter['n']}"
    patch(ac, "make_client_order_id", _coid)

    real_sleep = asyncio.sleep

    async def _nosleep(*a, **k):
        await real_sleep(0)
    patch(asyncio, "sleep", _nosleep)

    if hasattr(ts, "_next_repair_sentence"):
        real_nrs = ts._next_repair_sentence
        patch(ts, "_next_repair_sentence", lambda _now: real_nrs(NOW_UTC))
    return undo


def _uninstall(undo):
    for obj, name, old in reversed(undo):
        if old is None:
            try:
                delattr(obj, name)
            except AttributeError:
                pass
        else:
            setattr(obj, name, old)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Scenario fixtures
# ══════════════════════════════════════════════════════════════════════════════════════════

def _trade(w, tid=401, ticker="KOD", remaining=10, stop_id="stop-1", stop_price=58.0, **over):
    t = {"id": tid, "ticker": ticker, "account_mode": "live", "status": "filled",
         "remaining_shares": remaining, "entry_shares": remaining, "entry_price": 60.0,
         "stop_price": stop_price, "stop_order_id": stop_id, "hard_stop": 55.0, "orb_low": 57.5,
         "signal_type": "magna53", "alert_date": date(2026, 9, 28), "exits": [],
         "total_pnl": None, "partial_taken": False, "breakeven_active": False,
         "filled_at": datetime(2026, 10, 6, 13, 31, 5, tzinfo=timezone.utc),
         "entry_order_id": f"entry-{tid}", "exit_rule": None, "depth_sell_pending_on": None,
         "dead_stop_price": None, "dead_stop_status": None, "dead_stop_order_id": None,
         "closed_at": None, "closed_on": None}
    t.update(over)
    w.trades[tid] = t
    return t


def _position(w, ticker, qty, available):
    w.positions[ticker] = {"symbol": ticker, "qty": float(qty), "qty_available": float(available)}


def _bstop(w, oid, ticker, qty, price, status="new"):
    w.broker_orders.append({"id": oid, "symbol": ticker, "side": "sell", "type": "stop",
                            "qty": float(qty), "filled_qty": 0.0, "status": status,
                            "order_class": "simple", "stop_price": float(price)})


def _boco(w, oid, ticker, qty, limit=90.0):
    w.broker_orders.append({"id": oid, "symbol": ticker, "side": "sell", "type": "limit",
                            "qty": float(qty), "filled_qty": 0.0, "status": "new",
                            "order_class": "oco", "limit_price": limit})


def _bsell(w, oid, ticker, qty, status="accepted"):
    w.broker_orders.append({"id": oid, "symbol": ticker, "side": "sell", "type": "market",
                            "qty": float(qty), "filled_qty": 0.0, "status": status,
                            "order_class": "simple"})


def _mirror(w, oid, tid, ticker, purpose, qty, status="new", exit_reason=None, raw=None):
    w.orders.append({"trade_id": tid, "alpaca_order_id": oid, "ticker": ticker, "side": "sell",
                     "order_type": "market", "qty": float(qty), "status": status,
                     "purpose": purpose, "exit_reason": exit_reason,
                     "raw_response": raw if raw is not None else {"order_class": "simple"}})


BREACH = '{"code":42210000,"message":"stop price must be less than current price"}'


def _ws_order(oid, symbol, *, filled_qty=0.0, avg=None, side="sell", status="canceled"):
    order = SimpleNamespace(id=oid, symbol=symbol, status=status, filled_qty=filled_qty,
                            filled_avg_price=avg, qty=1.0, side=side, type="market",
                            limit_price=None, stop_price=None, canceled_at=None, failed_at=None,
                            expired_at=None, updated_at=None)
    return SimpleNamespace(order=order, event=status, reason=None, price=avg, qty=filled_qty)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Scenarios — each returns (world, coroutine-factory). Toggle `magna53_depth_exit` is OFF
# (no mi_safeguard_state row) and no trade is stamped exit_rule='depth'.
# ══════════════════════════════════════════════════════════════════════════════════════════

def s01_1645_exit_no_resting(om, **_):
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    return w, lambda: om.execute_full_exit(401, "sma_trail_stop")


def s02_1645_exit_sale_rejected_restored(om, **_):
    w, run = s01_1645_exit_no_resting(om)
    w.close_errors = [Exception("insufficient qty available: available 0, held_for_orders 10")]
    return w, run


def s03_1645_exit_restore_through_the_price(om, **_):
    w, run = s01_1645_exit_no_resting(om)
    w.close_errors = [Exception("insufficient qty available: available 0, held_for_orders 10")]
    w.place_errors = [Exception(BREACH)]
    return w, run


def s04_1645_exit_beside_resting_oco_third(om, **_):
    w = World()
    _trade(w, remaining=6, partial_taken=True, breakeven_active=True, stop_price=60.0)
    _position(w, "KOD", 6, 0)
    _bstop(w, "stop-1", "KOD", 4, 60.0)
    _boco(w, "oco-1", "KOD", 2)
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, raw={"order_class": "oco"})
    return w, lambda: om.execute_full_exit(401, "sma_trail_stop")


def s05_1645_exit_closing_order_already_queued(om, **_):
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 0)
    _bsell(w, "sell-q", "KOD", 10)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    return w, lambda: om.execute_full_exit(401, "sma_trail_stop")


def s06_update_stop_raise(om, **_):
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    return w, lambda: om.update_stop(401, 61.5, stop_source="trail")


def s07_update_stop_row_held_only_by_oco_third(om, **_):
    w = World()
    _trade(w, remaining=2, stop_id=None, partial_taken=True, breakeven_active=True,
           stop_price=60.0)
    _position(w, "KOD", 2, 0)
    _boco(w, "oco-1", "KOD", 2)
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, raw={"order_class": "oco"})
    return w, lambda: om.update_stop(401, 61.5, stop_source="trail")


def s08_sync_broker_lower_no_queued_sale(om, **_):
    w = World()
    _trade(w, account_mode="paper")
    _position(w, "KOD", 8, 0)
    _bstop(w, "stop-1", "KOD", 8, 58.0)
    return w, lambda: om._sync_positions_for_mode("paper")


def s09_sync_under_a_queued_sale_paper_soft_reservation(om, **_):
    w = World()
    _trade(w, account_mode="paper", stop_id=None, remaining=10, partial_taken=True,
           breakeven_active=True)
    _position(w, "KOD", 3, 0)                       # paper soft-reserves the queued 7
    _boco(w, "oco-1", "KOD", 3)
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 3, raw={"order_class": "oco"})
    _bsell(w, "sell-q", "KOD", 7)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 7, status="accepted",
            exit_reason="sma_trail_stop")
    return w, lambda: om._sync_positions_for_mode("paper")


def _fill(ts, oid, symbol, qty, price):
    return ts._handle_fill(_ws_order(oid, symbol, filled_qty=float(qty), avg=float(price),
                                     status="filled"), "live")


def s10_stream_fill_of_the_whole_sale(om, ts, **_):
    w = World()
    _trade(w, stop_id="stop-1")
    _position(w, "KOD", 10, 0)
    _bsell(w, "sell-q", "KOD", 10)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    return w, lambda: _fill(ts, "sell-q", "KOD", 10, 57.0)


def s11_stream_fill_beside_resting_oco_third(om, ts, **_):
    w = World()
    _trade(w, remaining=6, partial_taken=True, breakeven_active=True, stop_id="stop-1",
           exits=[{"time": "2026-10-01T15:00:00+00:00", "price": 80.0, "reason": "partial_profit",
                   "shares": 3, "pnl": 60.0, "order_id": "p-1"}])
    _position(w, "KOD", 6, 0)
    _boco(w, "oco-1", "KOD", 2)
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, raw={"order_class": "oco"})
    _bsell(w, "sell-q", "KOD", 4)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 4, status="accepted",
            exit_reason="sma_trail_stop")
    return w, lambda: _fill(ts, "sell-q", "KOD", 4, 66.0)


def s12_stream_stop_cancelled_by_the_planned_sale(om, ts, **_):
    w, _run = s01_1645_exit_no_resting(om)

    async def run():
        out = await om.execute_full_exit(401, "sma_trail_stop")
        await ts._handle_cancel_or_reject(_ws_order("stop-1", "KOD"), "canceled", "live")
        return out
    return w, run


def s13_stream_stop_cancelled_by_hand(om, ts, **_):
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 10)
    _bstop(w, "stop-1", "KOD", 10, 58.0, status="canceled")
    return w, lambda: ts._handle_cancel_or_reject(_ws_order("stop-1", "KOD"), "canceled", "live")


def _dead_sale_world(event):
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _bsell(w, "sell-q", "KOD", 10, status=event)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    return w


def s14_stream_queued_sale_cancelled_stop_restored(om, ts, **_):
    w = _dead_sale_world("canceled")
    return w, lambda: ts._handle_cancel_or_reject(_ws_order("sell-q", "KOD"), "canceled", "live")


def s15_stream_queued_sale_expired_restore_through_the_price(om, ts, **_):
    w = _dead_sale_world("expired")
    w.place_errors = [Exception(BREACH)]
    return w, lambda: ts._handle_cancel_or_reject(_ws_order("sell-q", "KOD", status="expired"),
                                                  "expired", "live")


def s16_watchdog_fresh_entry_without_a_stop(om, sched, **_):
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    return w, lambda: sched._stop_ack_timeout_watchdog_job()


def s17_watchdog_while_an_exit_holds_the_trade_lock(om, sched, **_):
    w, run = s16_watchdog_fresh_entry_without_a_stop(om, sched)
    w.foreign_locks.add(401)
    return w, run


def s18_coverage_1700_slot_after_a_queued_sale(om, sched, **_):
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 0)
    _bsell(w, "sell-q", "KOD", 10)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    return w, lambda: sched._coverage_watch_job("post_close")


def s19_coverage_1700_slot_genuine_gap_repair_fails(om, sched, **_):
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    w.place_errors = [Exception("insufficient qty available")]
    return w, lambda: sched._coverage_watch_job("post_close")


def s20_refresh_row_held_only_by_oco_third(om, lt, **_):
    w = World()
    _trade(w, remaining=2, stop_id=None, partial_taken=True, breakeven_active=True,
           stop_price=60.0)
    _position(w, "KOD", 2, 0)
    _boco(w, "oco-1", "KOD", 2)
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, raw={"order_class": "oco"})
    return w, lambda: lt._stop_refresh(include_same_day=True, label="Post-close")


def s21_refresh_genuinely_uncovered(om, lt, **_):
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    w.place_errors = [Exception("insufficient qty available"),
                      Exception("insufficient qty available")]
    return w, lambda: lt._stop_refresh(include_same_day=True, label="Post-close")


def s22_safeguards_partial_sale_loss_today(om, lt, **_):
    w = World()
    w.closed_losses_today = -50.0
    _trade(w, tid=402, ticker="VICR", account_mode="paper", remaining=2,
           exits=[{"time": "2026-10-06T13:30:05+00:00", "price": 55.0, "reason": "sma_trail_stop",
                   "shares": 4, "pnl": -60.0, "order_id": "s-9"}])
    return w, lambda: lt._check_safeguards(account_mode="paper")


def s23_sdk_close_position_with_qty(om, **_):
    """#687 (d): what `alpaca_client.close_position(qty=…)` hands alpaca-py's TradingClient."""
    from agents.market_intelligence.broker import alpaca_client as ac
    w = World()

    class _Client:
        def close_position(self, symbol_or_asset_id, close_options=None):
            w.calls.append({"method": "TradingClient.close_position",
                            "args": {"symbol_or_asset_id": symbol_or_asset_id,
                                     "close_options": _jsonable(close_options)}})
            if close_options is not None and not hasattr(close_options, "to_request_fields"):
                raise AttributeError("'dict' object has no attribute 'to_request_fields'")
            return SimpleNamespace(
                id="sdk-1", client_order_id="c-1", symbol=symbol_or_asset_id, side="sell",
                type="market", qty="2", filled_qty=None, filled_avg_price=None, stop_price=None,
                limit_price=None, status="accepted", order_class="simple", created_at=None,
                filled_at=None, legs=None)

    async def run():
        real_get = ac.get_trading_client
        real_close = _REAL["close_position"]
        ac.get_trading_client = lambda *a, **k: _Client()
        try:
            return await real_close("KOD", qty=2, account_mode="live")
        finally:
            ac.get_trading_client = real_get
    return w, run


# branch-only (main records "absent"): the depth machinery must be inert with the toggle OFF
def s24_depth_1901_runner_with_no_marked_rows(om, **_):
    fn = om.run_depth_open_sales                    # AttributeError here = absent in this tree
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    return w, lambda: fn()


def s25_depth_stamp_with_the_toggle_off(om, **_):
    fn = om.resolve_exit_rule_stamp
    w = World()
    return w, lambda: fn("magna53", "live")


def _bars(w, today_bar, prior_close=70.0):
    """20+ sessions before entry at a steady close (the line ≈ prior_close), and today's bar."""
    w.index_today = today_bar
    w.index_prior = [{"o": prior_close, "h": prior_close + 1.5, "l": prior_close - 1.5,
                      "c": prior_close, "v": 1_000_000} for _ in range(25)]


def s26_1645_job_unstamped_trade_closes_below_the_line(om, lt, **_):
    """The 16:45 job itself, toggle OFF (exit_rule NULL): today's close-below sale."""
    w = World()
    _trade(w, stop_price=58.0, hold_days=8, running_closes=[70.0] * 8, partial_taken=True,
           breakeven_active=True, alert_date=date(2026, 9, 24))
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    _bars(w, {"o": 69.0, "h": 69.5, "l": 64.5, "c": 65.0, "v": 2_000_000})
    return w, lambda: lt.update_open_positions_live(TODAY)


def s27_1645_job_unstamped_trade_trail_raise(om, lt, **_):
    """The 16:45 job, toggle OFF: the trail rises → `update_stop` to the line (not the depth level)."""
    w = World()
    _trade(w, stop_price=58.0, hold_days=8, running_closes=[70.0] * 8, partial_taken=True,
           breakeven_active=True, alert_date=date(2026, 9, 24))
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    _bars(w, {"o": 74.0, "h": 76.0, "l": 73.5, "c": 75.0, "v": 2_000_000})
    return w, lambda: lt.update_open_positions_live(TODAY)


SCENARIOS = [v for k, v in sorted(globals().items()) if re.fullmatch(r"s\d\d_\w+", k)]
_REAL: dict = {}


def _snapshot(w: World) -> dict:
    trades = {}
    for tid, t in sorted(w.trades.items()):
        t2 = {k: v for k, v in t.items() if k not in ("filled_at",)}
        ex = t2.get("exits")
        if isinstance(ex, str):
            ex = json.loads(ex)
        t2["exits"] = [{k: v for k, v in e.items() if k != "time"} for e in (ex or [])]
        trades[str(tid)] = _jsonable(t2)
    orders = sorted(({"id": o["alpaca_order_id"], "purpose": o.get("purpose"),
                      "qty": o.get("qty"), "status": o.get("status"),
                      "exit_reason": o.get("exit_reason")} for o in w.orders),
                    key=lambda o: str(o["id"]))
    return {"trades": trades, "orders": _jsonable(orders)}


async def _run_one(fn, mods) -> dict:
    try:
        w, factory = fn(**mods)
    except AttributeError as e:          # the scenario's function does not exist in this tree
        return {"absent": str(e)}
    undo = _install(w)
    try:
        result = await factory()
        err = None
    except Exception as e:               # noqa: BLE001 — recorded, compared like a return value
        result, err = None, f"{type(e).__name__}: {e}"
    finally:
        _uninstall(undo)
    return {"broker_calls": w.calls, "pages": w.pages, "result": _jsonable(result),
            "raised": err, "book_after": _snapshot(w), "_unknown_sql": sorted(set(w.unknown))}


async def run_all() -> dict:
    import os
    os.environ.setdefault("DRAWDOWN_BREAKER_PHASE", "shadow")
    os.environ.setdefault("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    from agents.market_intelligence.broker import alpaca_client as ac
    from agents.market_intelligence.broker import live_tracker as lt
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence.broker import trade_stream as ts
    import agents.market_intelligence.scheduler as sched
    _REAL["close_position"] = ac.close_position
    mods = {"om": om, "ts": ts, "lt": lt, "sched": sched}
    out = {}
    for fn in SCENARIOS:
        out[fn.__name__] = await _run_one(fn, mods)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    import tests.conftest  # noqa: F401 — the same SDK/module stubs the suite runs under
    import logging
    logging.disable(logging.CRITICAL)
    log = asyncio.run(run_all())
    Path(args.out).write_text(json.dumps(log, indent=1, sort_keys=True, default=str))
    print(f"{len(log)} scenarios -> {args.out}")


if __name__ == "__main__":
    main()
