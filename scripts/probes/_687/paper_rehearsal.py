"""#687 — PAPER REHEARSAL of the depth-exit order sequence (operator ruling 2026-09-29: switch to the
depth rule only after a paper rehearsal of the exact order sequence in market hours passes; then his
final yes). Spec: docs/analysis/687_depth_trail_mechanics_2026-09-29.md §8 "Paper rehearsal", as
corrected by its CHECKED section (the opening-auction sale from 19:00 ET is the ruled vehicle; the
09:00/09:15 coverage-detector assertion is replaced by a unit test).

PAPER ONLY. Nothing here can reach the live account:
  * every broker call and every trade row carries account_mode='paper' (the literal ACCOUNT_MODE);
  * at start the paper account id is read and compared with the live one (one read-only
    GET /v2/account on live, the only live call this process ever makes) — equal → refuse; the
    paper client must resolve to the paper endpoint;
  * then a TRIPWIRE replaces alpaca_client.get_trading_client: any call that resolves to a mode other
    than 'paper' raises LiveTouched, the cached live client is dropped and the ALPACA_LIVE_* env vars
    are removed from this process;
  * every order this script places uses make_client_order_id('paper', 'integration_test', ticker).

WHERE IT RUNS — apollo-execution (apollo-market has blank Alpaca keys and EXECUTION_MODE=http):
    docker cp scripts/probes/_687/paper_rehearsal.py apollo-execution:/app/scripts/probes/_687/
    docker exec -d apollo-execution python scripts/probes/_687/paper_rehearsal.py day-a
    docker exec apollo-execution tail -f scripts/probes/_687/rehearsal_<ET date>.log
    (next trading day, launch before 09:25 ET)
    docker exec -d apollo-execution python scripts/probes/_687/paper_rehearsal.py day-b
    docker exec apollo-execution python scripts/probes/_687/paper_rehearsal.py status
    docker exec apollo-execution python scripts/probes/_687/paper_rehearsal.py cleanup   # abort path
    python scripts/probes/_687/paper_rehearsal.py day-a --dry-run    # fakes, no broker, no DB

TAGGING. Trade rows: mi_live_trades.signal_type = 'integration_test' (the tag every paper-validation
script uses; analytics key on a strategy's signal_type, so these rows are never counted as a strategy's
trades), account_mode='paper', alert_date = the ET date. Production code then stamps its own orders
'apollo_paper_integration_test_<TICKER>_<ms>', which coverage_drift already classifies as harness
cruft (INFO, never a D2-HIGH page). Day A -> Day B state lives in rehearsal_state.json AND in an
mi_audit_log row 'paper_rehearsal_687_state' (survives a container restart in the deploy window).
Cleanup (end of Day B, or `cleanup`): cancel only OUR orders (ids recorded here, ids in our rows'
mi_live_orders / stop_order_id, legs of those, and our client-order-id prefix), flatten the ticker
only when no non-rehearsal paper row or foreign order exists on it, delete our rows by id AND
signal_type (SET LOCAL mi.allow_trade_delete), then verify.

THE STEPS (spec times; the first three run at start time — said so in the log):
  A1  P1 = 3 sh of TICKER_P1, GTC stop 5% below the fill → assert every share reserved.
  A2  execute_partial_exit(limit far above) → OCO third resting, 2/3 stop live, all reserved.
  A3  price-only replace of the 2/3 stop +1% → new id, still covering.
  B1  P2 = 4 sh of TICKER_P2: a 3-sh GTC stop for the row + one EXTRA 1-sh resting sell that the
      books do not know about (so it is not a pending exit) → execute_full_exit → assert rejected,
      stop restored at the same price <= 5 s, page sent. The extra sell is then cancelled and the
      extra share sold, so P2 = 3 sh under its restored stop.
  A4  15:51 a market-on-close BUY of 1 sh on the flat PROBE ticker → assert rejected (cutoff).
  A5  16:30 a 1-sh sell of P1 while the stop + OCO hold everything → assert insufficient qty /
      held_for_orders (the OKTA error).
  A6  16:45 execute_full_exit(P1) → lock held, stop cancelled and shares free <= 5 s,
      close_position(qty=2) accepted, OCO untouched, full_exit row, the stream's
      stop_cancel_by_planned_sale_silent row (positive evidence of NO "unprotected" page).
  A7  16:46 an opening-auction BUY of 1 sh on PROBE → assert rejected (cutoff).
  A8  18:50 stamp P2 exit_rule='depth', depth_sell_pending_on=today (the 16:45 decision itself skips
      a same-day row and is unit-tested) → 19:04 assert the PRODUCTION 19:01 job queued the opg sale
      (else drive execute_depth_open_sale here and say so).
  D1  Day B before the open: overnight jobs placed nothing beside the queued sales.
      (09:00/09:15 coverage detector → replaced by tests/test_position_coverage_check_527.py::
      test_a_queued_full_exit_beside_a_resting_profit_take_covers_the_whole_position, CHECKED §.)
  D2  09:30 both sales fill by 09:40; fill time + price vs the first-minute open (feed named).
  D3  rows: P2 closed; P1 open at the OCO third's 1 share.
  D4  09:35 refresh placed nothing for P1 (covered_by_resting_exit / already_covered).
  D5  cancel the OCO → the existing handler re-protects the third (1-sh stop) <= 60 s.
  D6  cleanup.

EXIT CODES: 0 every step PASS/SKIP-by-design · 1 a FAIL · 2 refused / could not run.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
ACCOUNT_MODE = "paper"                     # literal, threaded to every call — NEVER live
TAG_SIGNAL_TYPE = "integration_test"       # the paper-validation scripts' row tag
DEFAULT_TICKERS = ("KO", "PEP", "PG")      # P1, P2, cutoff probe — liquid large-caps
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_EVENT = "paper_rehearsal_687_state"
START_EVENT = "paper_rehearsal_687_start"
END_EVENT = "paper_rehearsal_687_end"
LOCK_NAMESPACE = 0x504152                  # order_manager._TRADE_LOCK_NAMESPACE
REHEARSAL_TAG = "🧪 #687 REHEARSAL (paper test order, not a real position) — "
REASON = "sma_trail_stop"

LIVE_STATUSES = {"new", "accepted", "held", "partially_filled", "accepted_for_bidding",
                 "pending_new", "pending_replace"}
QUEUED_OK = {"new", "accepted", "held", "pending_new", "accepted_for_bidding"}
TERMINAL = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced", "done_for_day"}
# Rejection texts that mean "rejected for a reason OTHER than the time cutoff" — a cutoff probe that
# hits one of these proves nothing (a broken system would read the same).
WRONG_REASON = re.compile(
    r"insufficient|held_for_orders|wash|buying power|not tradable|not shortable|fractional|"
    r"qty|quantity|asset .* not found|account .* blocked", re.I)

# Fixed ET times (spec §8, plus the 19:01 opening-auction job the CHECKED section makes the vehicle).
T_CLS = dtime(15, 51)
T_HELD = dtime(16, 30)
T_FULL_EXIT = dtime(16, 45)
T_OPG = dtime(16, 46)
T_MARK = dtime(18, 50)
T_DEPTH_CHECK = dtime(19, 4)
T_DAYB_OPEN = dtime(9, 30, 5)
T_DAYB_FILL_DEADLINE = dtime(9, 40)
T_DAYB_REFRESH_CHECK = dtime(9, 36, 30)
LATEST_DAY_A_START = dtime(15, 40)


class RehearsalRefused(RuntimeError):
    """A safety guard said no. Nothing was placed."""


class LiveTouched(RuntimeError):
    """Something in this process tried to reach a non-paper account."""


def canon(status) -> str:
    return str(status or "").split(".")[-1].lower()


def _num(v):
    return float(v) if v is not None else None


# ── Safety guards (pure, unit-tested) ──────────────────────────────────────────────────────────────

def arm_live_tripwire(alpaca_module) -> None:
    """Make every client lookup that resolves to a non-paper mode raise, for the rest of the process.

    Wraps `alpaca_module.get_trading_client` (every alpaca_client wrapper and every production
    function this script drives goes through it), drops a cached live client, and removes the live
    keys from the environment so no new live client can be built anywhere in this process."""
    current = alpaca_module.get_trading_client
    if getattr(current, "_rehearsal_tripwire", False):
        return
    original = current

    def guarded(account_mode=None):
        mode = alpaca_module._resolve_account_mode(account_mode)
        if mode != ACCOUNT_MODE:
            raise LiveTouched(f"#687 rehearsal: a call resolved to account_mode={mode!r} — refused "
                              f"(PAPER ONLY)")
        return original(account_mode)

    guarded._rehearsal_tripwire = True
    alpaca_module.get_trading_client = guarded
    if hasattr(alpaca_module, "_get_trading_client"):
        alpaca_module._get_trading_client = guarded
    clients = getattr(alpaca_module, "_TRADING_CLIENTS", None)
    if isinstance(clients, dict):
        for k in [k for k in clients if k != ACCOUNT_MODE]:
            clients.pop(k, None)
    for k in ("ALPACA_LIVE_API_KEY", "ALPACA_LIVE_SECRET_KEY"):
        os.environ.pop(k, None)


def client_base_url(client) -> str:
    """The endpoint a TradingClient talks to, as a plain URL. alpaca-py (0.43.2) stores it as
    `BaseURL(str, Enum)`, whose str() is 'BaseURL.TRADING_PAPER' — not a URL — so read `.value`."""
    for attr in ("_base_url", "base_url"):
        v = getattr(client, attr, None)
        if v:
            return str(getattr(v, "value", v))
    return ""


def check_account_ids(ids: dict) -> str:
    """Refuse unless the paper account is provably not the live one. Returns a log line."""
    paper_id = ids.get("paper_id")
    live_id = ids.get("live_id")
    base = (ids.get("paper_base_url") or "").lower()
    if not paper_id:
        raise RehearsalRefused("the paper account id could not be read")
    if base and "paper-api" not in base:
        raise RehearsalRefused(f"the paper client resolves to {base!r}, not the paper endpoint")
    if live_id is not None and str(live_id) == str(paper_id):
        raise RehearsalRefused(f"the paper and live account ids are the SAME ({paper_id})")
    if ids.get("same_keys"):
        raise RehearsalRefused("ALPACA_PAPER_API_KEY equals ALPACA_LIVE_API_KEY")
    return (f"paper account {paper_id} != live account "
            f"{live_id if live_id is not None else '(no live keys in this process)'}; "
            f"paper endpoint {base or 'unreadable'}")


def route_page(text: str) -> str:
    """Every page this process sends reads as a paper rehearsal: the system's paper prefix first,
    then the rehearsal tag (so it can never look like a real alarm)."""
    prefix = "📄 PAPER "
    body = text[len(prefix):] if text.startswith(prefix) else text
    return prefix + REHEARSAL_TAG + body


def is_ours_coid(coid: str | None, ticker: str) -> bool:
    return bool(coid) and coid.startswith(f"apollo_{ACCOUNT_MODE}_{TAG_SIGNAL_TYPE}_{ticker}_")


# ── Step log ───────────────────────────────────────────────────────────────────────────────────────

class StepLog:
    def __init__(self, path: str, now_fn):
        self.path = path
        self.now = now_fn
        self.results: list[dict] = []
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _write(self, line: str) -> None:
        stamp = self.now().isoformat(timespec="seconds")
        full = f"{stamp} {line}"
        print(full, flush=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(full + "\n")

    def note(self, msg: str) -> None:
        self._write(f"[note] {msg}")

    def step(self, sid: str, title: str, ok: bool | None, detail: str = "", *,
             status: str | None = None) -> bool:
        st = status or ("PASS" if ok else "FAIL")
        self.results.append({"step": sid, "title": title, "status": st, "detail": detail})
        self._write(f"[{sid}] {st} — {title}" + (f" | {detail}" if detail else ""))
        return st == "PASS"

    def failed(self) -> list[dict]:
        return [r for r in self.results if r["status"] == "FAIL"]


# ── The rehearsal (env-agnostic) ───────────────────────────────────────────────────────────────────

class Rehearsal:
    def __init__(self, env, log: StepLog, tickers=DEFAULT_TICKERS):
        self.env = env
        self.log = log
        self.t1, self.t2, self.probe = tickers
        self.state: dict = {}

    # ── helpers ──
    def _at(self, day: date, t: dtime) -> datetime:
        return datetime.combine(day, t, tzinfo=_ET)

    async def _wait_status(self, oid: str, want: set, budget_s: float = 15.0) -> str:
        deadline = time.monotonic() + budget_s if not self.env.fake else None
        last = ""
        for _ in range(int(budget_s / 0.5) + 1):
            o = await self.env.get_order(oid)
            last = canon(o.get("status") if o else None)
            if last in want:
                return last
            if deadline is not None and time.monotonic() > deadline:
                break
            await self.env.sleep(0.5)
        return last

    async def _wait_avail(self, ticker: str, want: float, budget_s: float = 5.0):
        pos = None
        for _ in range(int(budget_s / 0.5) + 1):
            pos = await self.env.position(ticker)
            if pos and abs(float(pos.get("qty_available") or 0) - want) < 1e-9:
                return pos
            await self.env.sleep(0.5)
        return pos

    async def _audit_for_trade(self, events, since, trade_id, *, budget_s=0.0, extra=None):
        """Audit rows of `events` since `since` naming this trade (and matching `extra`)."""
        for _ in range(max(int(budget_s / 1.0), 0) + 1):
            rows = await self.env.audit_rows(events, since)
            hits = [r for r in rows if r["detail"].get("trade_id") == trade_id
                    and all(r["detail"].get(k) == v for k, v in (extra or {}).items())]
            if hits:
                return hits
            if budget_s:
                await self.env.sleep(1.0)
        return []

    async def _save(self) -> None:
        await self.env.save_state(self.state)

    # ── guards ──
    async def preflight(self, *, day: str) -> None:
        line = check_account_ids(await self.env.account_ids())
        self.env.arm_tripwire()
        self.log.note(f"PAPER GUARD OK: {line}; live tripwire armed (any non-paper client "
                      f"lookup raises; live keys removed from this process)")
        if day != "day-a":
            return
        for t in (self.t1, self.t2, self.probe):
            pos = await self.env.position(t)
            orders = await self.env.open_orders(t)
            foreign = await self.env.foreign_open_rows(t)
            ours = await self.env.sentinel_rows(t)
            if pos and abs(float(pos.get("qty") or 0)) > 0:
                raise RehearsalRefused(f"the paper account already holds {t} "
                                       f"({pos.get('qty')} sh) — pick another with --tickers")
            if orders:
                raise RehearsalRefused(f"the paper account has {len(orders)} open order(s) in {t} "
                                       f"— pick another with --tickers")
            if foreign:
                raise RehearsalRefused(f"{foreign} open paper trade row(s) exist for {t}")
            if ours:
                raise RehearsalRefused(f"rehearsal rows for {t} are left from an earlier run "
                                       f"(ids {ours}) — run `cleanup` first")
        self.log.note(f"TICKERS OK: P1={self.t1} P2={self.t2} probe={self.probe} — not held, no "
                      f"open orders, no trade rows in the paper account")

    # ── Day A ──
    async def day_a(self) -> int:
        env, log = self.env, self.log
        now = env.now()
        today = env.et_today()
        if now.weekday() >= 5:
            raise RehearsalRefused("Day A needs a weekday")
        if now.timetz().replace(tzinfo=None) > LATEST_DAY_A_START:
            raise RehearsalRefused(f"Day A must start by {LATEST_DAY_A_START} ET (its first steps "
                                   f"need regular-hours fills)")
        await self.preflight(day="day-a")
        if now < self._at(today, dtime(9, 31)):
            await env.sleep_until(self._at(today, dtime(9, 31)))
        toggles = await env.paper_toggles()
        log.note(f"paper toggles in mi_safeguard_state (read-only; patched IN-PROCESS for the "
                 f"partial only, prod unaffected): {toggles}")
        log.note(f"open paper trade rows before the rehearsal: {await env.open_paper_rows()} "
                 f"(the rehearsal adds 2; they count toward the PAPER 5-position cap until cleanup)")
        self.state = {"day_a": today.isoformat(), "tickers": [self.t1, self.t2, self.probe],
                      "started_at": env.now().isoformat(), "order_ids": [], "p1": {}, "p2": {}}
        await env.write_audit(START_EVENT, f"#687 paper rehearsal Day A started ({self.t1}, "
                              f"{self.t2}, probe {self.probe})", {"state": self.state})
        env.install_page_router()
        log.note("A1-A3 and B1 run NOW (spec 10:00/10:05/10:10) — the steps, not the clock time, are "
                 "what the rehearsal checks")

        await self._a1_a3()
        await self._b1_b2()
        await self._save()

        await self._fixed(today, T_CLS, self._a4_cls_probe)
        await self._fixed(today, T_HELD, self._a5_held_sell)
        await self._fixed(today, T_FULL_EXIT, self._a6_full_exit)
        await self._fixed(today, T_OPG, self._a7_opg_probe)
        await self._fixed(today, T_MARK, self._a8_mark_depth)
        await self._fixed(today, T_DEPTH_CHECK, self._a8_check_depth_sale)
        await self._save()

        log.note(f"pages sent by THIS process (paper prefix + rehearsal tag): "
                 f"{[p['text'][:120] for p in env.pages] or 'none'}; pages from the production "
                 f"stream / 19:01 job carry the system's own paper prefix")
        if not self.state["p1"].get("sale_id") and not self.state["p2"].get("sale_id"):
            log.note("no sale is queued for Day B — cleaning up now")
            await self.cleanup()
        return self._summary("Day A")

    async def _fixed(self, day: date, t: dtime, fn) -> None:
        when = self._at(day, t)
        if self.env.now() < when:
            self.log.note(f"waiting for {t.strftime('%H:%M')} ET")
            await self.env.sleep_until(when)
        try:
            await fn()
        except LiveTouched:
            raise
        except Exception as e:   # one step's crash must not strand the rest; logged as a FAIL
            self.log.step(getattr(fn, "__name__", "?"), "step raised", False,
                          f"{type(e).__name__}: {e}")

    async def _a1_a3(self) -> None:
        env, log, p1 = self.env, self.log, self.state["p1"]
        t = self.t1
        try:
            buy = await env.submit(t, 3, "buy", kind="market", tif="day")
            self.state["order_ids"].append(buy["id"])
            if await self._wait_status(buy["id"], {"filled"}) != "filled":
                log.step("A1", f"buy 3 {t}", False, "the buy did not fill")
                return
            fill = float((await env.get_order(buy["id"]))["filled_avg_price"])
            stop_px, entry = round(fill * 0.95, 2), round(fill * 0.97, 2)
            stop = await env.submit(t, 3, "sell", kind="stop", tif="gtc", stop=stop_px)
            self.state["order_ids"].append(stop["id"])
            if await self._wait_status(stop["id"], LIVE_STATUSES) not in LIVE_STATUSES:
                log.step("A1", f"GTC stop 5% below on {t}", False, "the stop never went live")
                return
            tid = await env.insert_trade(ticker=t, shares=3, entry=entry, stop=stop_px,
                                         stop_id=stop["id"], alert_date=env.et_today())
            p1.update(trade_id=tid, fill=fill, stop_price=stop_px, entry=entry)
            await self._save()
            row = await env.trade(tid)
            pos = await self._wait_avail(t, 0.0)
            ok = (row["account_mode"] == ACCOUNT_MODE and row["signal_type"] == TAG_SIGNAL_TYPE
                  and row.get("partial_taken") is True
                  and pos and float(pos["qty"]) == 3 and float(pos["qty_available"]) == 0)
            log.step("A1", f"buy 3 {t} + GTC stop 5% below; every share reserved", ok,
                     f"fill ${fill:.2f}, stop ${stop_px} ({stop['id'][:8]}), row #{tid} entry "
                     f"${entry} (set 3% under the fill so the breakeven step stays below market), "
                     f"partial_taken {row.get('partial_taken')} (TRUE keeps production's +2R "
                     f"profit trigger off it), position {pos and pos['qty']} / free {pos and pos['qty_available']}")
            if not ok:
                return

            limit = round(fill * 1.5, 2)
            ok = await env.partial_exit(tid, 1, limit)
            rows = await env.order_rows(tid)
            oco = [r for r in rows if r["purpose"] == "partial_exit"]
            oco_id = oco[-1]["alpaca_order_id"] if oco else None
            row = await env.trade(tid)
            stop2 = await env.get_order(row["stop_order_id"]) if row["stop_order_id"] else None
            oco_o = await env.get_order(oco_id) if oco_id else None
            pos = await self._wait_avail(t, 0.0)
            good = bool(ok and oco_o and stop2
                        and canon(oco_o["status"]) in LIVE_STATUSES and float(oco_o["qty"]) == 1
                        and abs(float(oco_o.get("limit_price") or 0) - limit) < 0.011
                        and canon(stop2["status"]) in LIVE_STATUSES and float(stop2["qty"]) == 2
                        and pos and float(pos["qty_available"]) == 0)
            p1.update(oco_id=oco_id, stop2_id=row["stop_order_id"], limit=limit)
            await self._save()
            log.step("A2", "execute_partial_exit (limit far above) → OCO third resting, 2/3 stop "
                     "live, every share reserved", good,
                     f"returned {ok}; OCO {oco_id and oco_id[:8]} "
                     f"{oco_o and (canon(oco_o['status']), oco_o['qty'], oco_o.get('limit_price'))}; "
                     f"2/3 stop {stop2 and (stop2['id'][:8], canon(stop2['status']), stop2['qty'], stop2.get('stop_price'))}; "
                     f"free {pos and pos['qty_available']}")
            if not good:
                return

            old_id = row["stop_order_id"]
            new_px = round(float(stop2["stop_price"]) * 1.01, 2)   # the LIVE broker stop, +1%
            new = await env.replace_stop_price(tid, old_id, new_px)
            st = await self._wait_status(new["id"], LIVE_STATUSES)
            row = await env.trade(tid)
            n = await env.get_order(new["id"])
            pos = await self._wait_avail(t, 0.0)
            good = (new["id"] != old_id and st in LIVE_STATUSES and float(n["qty"]) == 2
                    and abs(float(n["stop_price"]) - new_px) < 0.011
                    and row["stop_order_id"] == new["id"]
                    and pos and float(pos["qty_available"]) == 0)
            p1.update(stop3_id=new["id"], stop3_price=new_px)
            await self._save()
            since_a3 = env.now()
            log.step("A3", "price-only replace of the 2/3 stop +1% → a new id, still covering", good,
                     f"{old_id[:8]} → {new['id'][:8]} @ ${new_px} ({st}, qty {n['qty']}); row "
                     f"pointer {row['stop_order_id'][:8]}; free {pos and pos['qty_available']}")
            # The stream's "Stop order CANCELED/REPLACED — Position unprotected" page writes NO audit
            # row, so a false page on this replace cannot be proven absent from here: log what the
            # stream DID record for 20 s, and check the paper channel by eye.
            await env.sleep(20.0)
            seen = [r["event_type"] for r in await env.audit_rows(None, since_a3)
                    if r["detail"].get("trade_id") == tid]
            log.note(f"A3: audit rows naming P1 in the 20 s after the replace: {seen or 'none'} — "
                     f"the stream's unprotected page leaves no row; check the paper channel for a "
                     f"'Stop order ... Position unprotected' page on {t} around "
                     f"{since_a3:%H:%M:%S} ET")
        except LiveTouched:
            raise
        except Exception as e:
            log.step("A1-A3", "P1 setup raised", False, f"{type(e).__name__}: {e}")

    async def _b1_b2(self) -> None:
        env, log, p2 = self.env, self.log, self.state["p2"]
        t = self.t2
        try:
            buy = await env.submit(t, 4, "buy", kind="market", tif="day")
            self.state["order_ids"].append(buy["id"])
            if await self._wait_status(buy["id"], {"filled"}) != "filled":
                log.step("B1", f"buy 4 {t}", False, "the buy did not fill")
                return
            fill = float((await env.get_order(buy["id"]))["filled_avg_price"])
            stop_px = round(fill * 0.95, 2)
            stop = await env.submit(t, 3, "sell", kind="stop", tif="gtc", stop=stop_px)
            self.state["order_ids"].append(stop["id"])
            await self._wait_status(stop["id"], LIVE_STATUSES)
            extra = await env.submit(t, 1, "sell", kind="limit", tif="gtc", limit=round(fill * 1.5, 2))
            self.state["order_ids"].append(extra["id"])
            await self._wait_status(extra["id"], LIVE_STATUSES)
            tid = await env.insert_trade(ticker=t, shares=3, entry=round(fill * 0.97, 2),
                                         stop=stop_px, stop_id=stop["id"],
                                         alert_date=env.et_today())
            p2.update(trade_id=tid, fill=fill, stop_price=stop_px, extra_id=extra["id"])
            await self._save()
            pos = await self._wait_avail(t, 0.0)
            row = await env.trade(tid)
            ok = bool(pos and float(pos["qty"]) == 4 and float(pos["qty_available"]) == 0
                      and row and row.get("partial_taken") is True)
            log.step("B1", f"P2: 4 {t}, row of 3 under a 3-sh stop + one extra 1-sh resting sell "
                     f"the books do not know (holds a share, not a pending exit)", ok,
                     f"fill ${fill:.2f}, stop ${stop_px} ({stop['id'][:8]}), extra {extra['id'][:8]}, "
                     f"row #{tid} partial_taken {row and row.get('partial_taken')}, position {pos and pos['qty']} / free {pos and pos['qty_available']}")
            if not ok:
                return

            since = env.now()
            async with env.exit_spy(tid) as spy:
                ok = await env.full_exit(tid, REASON)
            close = [e for e in spy if e["name"] == "close_position"]
            place = [e for e in spy if e["name"] == "place_stop_order"]
            rej = await self._audit_for_trade(["full_exit_rejected"], since, tid)
            row = await env.trade(tid)
            restored = await env.get_order(row["stop_order_id"]) if row["stop_order_id"] else None
            st = await self._wait_status(row["stop_order_id"], LIVE_STATUSES) if restored else ""
            dt = (place[0]["t"] - close[0]["t"]) if (close and place) else None
            page = [p for p in env.pages if "FAILED" in p["text"] and t in p["text"]]
            good = bool(ok is False and close and close[0]["ok"] is False and rej and restored
                        and row["stop_order_id"] != stop["id"] and st in LIVE_STATUSES
                        and abs(float(restored["stop_price"]) - stop_px) < 0.011
                        and float(restored["qty"]) == 3 and dt is not None and dt <= 5.0 and page)
            p2.update(restored_stop_id=row["stop_order_id"])
            await self._save()
            log.step("B2", "extra sell holds a share → execute_full_exit rejected → stop restored at "
                     "the same price <= 5 s → page", good,
                     f"returned {ok}; sell error: {close and (close[0].get('error') or '')[:160]}; "
                     f"full_exit_rejected rows {len(rej)}; restored "
                     f"{restored and (restored['id'][:8], st, restored['qty'], restored.get('stop_price'))} "
                     f"{'%.2f s' % dt if dt is not None else '(no restore call)'} after the rejection; "
                     f"page: {page[0]['text'][:140] if page else 'NONE'}")
            silent = await self._audit_for_trade(
                ["stop_cancel_by_planned_sale_silent"], since, tid, budget_s=30,
                extra={"cancelled_order_id": stop["id"]})
            log.step("B2b", "the stream recorded the planned-sale cancel instead of paging "
                     "'unprotected'", bool(silent),
                     "stop_cancel_by_planned_sale_silent row found" if silent else
                     "NO row in 30 s — the paper stream did not take the silent path (it paged, "
                     "or it is not running for paper)")

            # Make P2 an ordinary 3-sh position again for the opening-auction step — only if the
            # failed exit really left all 4 shares (a sale that went through must not be followed by
            # a sell that would open a short).
            pos = await env.position(t)
            if not pos or float(pos["qty"]) != 4:
                p2["ready"] = False
                await self._save()
                log.step("B3", f"P2 back to 3 {t}", None, f"skipped — the position is "
                         f"{pos and pos['qty']} sh, not 4; cleanup handles it", status="SKIP")
                return
            await env.cancel(extra["id"])
            await self._wait_status(extra["id"], TERMINAL)
            sell = await env.submit(t, 1, "sell", kind="market", tif="day")
            self.state["order_ids"].append(sell["id"])
            filled = await self._wait_status(sell["id"], {"filled"})
            pos = await self._wait_avail(t, 0.0)
            ok = bool(filled == "filled" and pos and float(pos["qty"]) == 3
                      and float(pos["qty_available"]) == 0)
            p2["ready"] = ok
            await self._save()
            log.step("B3", f"extra sell cancelled + extra share sold → P2 = 3 {t} under the restored "
                     f"stop", ok, f"position {pos and pos['qty']} / free {pos and pos['qty_available']}")
        except LiveTouched:
            raise
        except Exception as e:
            log.step("B1-B3", "P2 raised", False, f"{type(e).__name__}: {e}")

    async def _cutoff_probe(self, sid: str, tif: str, valid_from: dtime, valid_to: dtime,
                            label: str) -> None:
        now_t = self.env.now().timetz().replace(tzinfo=None)
        if not (valid_from <= now_t < valid_to):
            self.log.step(sid, label, None, f"skipped — now {now_t:%H:%M:%S} is outside "
                          f"{valid_from:%H:%M}-{valid_to:%H:%M}, where only the cutoff can reject",
                          status="SKIP")
            return
        try:
            o = await self.env.submit(self.probe, 1, "buy", kind="market", tif=tif)
        except LiveTouched:
            raise
        except Exception as e:
            text = str(e)
            wrong = WRONG_REASON.search(text)
            self.log.step(sid, label, not wrong,
                          ("rejected for another reason (proves nothing): " if wrong else
                           "rejected: ") + text[:300])
            return
        self.state["order_ids"].append(o["id"])
        await self.env.cancel(o["id"])
        self.log.step(sid, label, False, f"ACCEPTED ({o['id'][:8]}, cancelled at once) — the "
                      f"cutoff is not where the design assumes")

    async def _a4_cls_probe(self) -> None:
        await self._cutoff_probe("A4", "cls", dtime(15, 50), dtime(16, 0),
                                 f"15:51 market-on-close BUY 1 {self.probe} → rejected (cutoff)")

    async def _a7_opg_probe(self) -> None:
        await self._cutoff_probe("A7", "opg", dtime(9, 28), dtime(19, 0),
                                 f"16:46 opening-auction BUY 1 {self.probe} → rejected (cutoff)")

    async def _a5_held_sell(self) -> None:
        p1 = self.state["p1"]
        if not p1.get("stop3_id"):
            self.log.step("A5", "held-shares sell", None, "skipped — P1 not set up", status="SKIP")
            return
        try:
            o = await self.env.submit(self.t1, 1, "sell", kind="limit", tif="gtc",
                                      limit=p1["limit"])
        except LiveTouched:
            raise
        except Exception as e:
            text = str(e)
            ok = "insufficient" in text.lower() and ("held_for_orders" in text
                                                    or "available: 0" in text
                                                    or '"available":"0"' in text)
            self.log.step("A5", f"16:30 1-sh sell of {self.t1} while stop + OCO hold every share → "
                          f"insufficient qty / held_for_orders", ok, text[:300])
            return
        self.state["order_ids"].append(o["id"])
        await self.env.cancel(o["id"])
        self.log.step("A5", "held-shares sell", False,
                      f"ACCEPTED ({o['id'][:8]}, cancelled) — shares were not all reserved")

    async def _a6_full_exit(self) -> None:
        env, log, p1 = self.env, self.log, self.state["p1"]
        tid = p1.get("trade_id")
        if not p1.get("stop3_id"):
            log.step("A6", "16:45 execute_full_exit", None, "skipped — P1 not set up", status="SKIP")
            return
        row = await env.trade(tid)
        stop_id, oco_id = row["stop_order_id"], p1["oco_id"]
        since = env.now()
        async with env.exit_spy(tid) as spy:
            ok = await env.full_exit(tid, REASON)
        cancels = [e for e in spy if e["name"] == "cancel_order"]
        close = [e for e in spy if e["name"] == "close_position"]
        c = close[0] if close else {}
        stop_after = await env.get_order(stop_id)
        oco_after = await env.get_order(oco_id)
        rows = [r for r in await env.order_rows(tid) if r["purpose"] == "full_exit"]
        sale_id = rows[-1]["alpaca_order_id"] if rows else None
        sale = await env.get_order(sale_id) if sale_id else None
        p1["sale_id"] = sale_id
        await self._save()
        dt = (c["t"] - cancels[0]["t"]) if (c and cancels) else None
        log.step("A6", "16:45 execute_full_exit returned True", ok is True, f"returned {ok}")
        log.step("A6a", "the per-trade lock was held when the sale went out",
                 bool(c.get("lock_held")), f"pg_locks advisory ({LOCK_NAMESPACE}, {tid}) granted="
                 f"{c.get('lock_held')}")
        log.step("A6b", "stop cancelled and the shares free <= 5 s",
                 bool(cancels and cancels[0]["args"][0] == stop_id and cancels[0]["ok"]
                      and canon(stop_after and stop_after["status"]) in {"canceled", "cancelled"}
                      and dt is not None and dt <= 5.0
                      and float(c.get("qty_available") or 0) >= 2),
                 f"cancel {stop_id[:8]} → {canon(stop_after and stop_after['status'])}; sale sent "
                 f"{'%.2f s' % dt if dt is not None else '?'} after the cancel with "
                 f"{c.get('qty_available')} sh free")
        log.step("A6c", "close_position(qty=2) accepted",
                 bool(c and c.get("qty") == 2 and c.get("ok")
                      and canon(sale and sale["status"]) in QUEUED_OK | {"filled"}),
                 f"qty={c.get('qty')} ok={c.get('ok')} order {sale_id and sale_id[:8]} "
                 f"{canon(sale and sale['status'])} {c.get('error') or ''}")
        log.step("A6d", "the OCO third untouched",
                 bool(oco_after and canon(oco_after["status"]) in LIVE_STATUSES
                      and not [e for e in cancels if e["args"][0] == oco_id]),
                 f"OCO {oco_id[:8]} {canon(oco_after and oco_after['status'])}")
        log.step("A6e", "a full_exit row written", bool(rows and float(rows[-1]["qty"]) == 2),
                 f"mi_live_orders full_exit {[(r['alpaca_order_id'][:8], r['qty']) for r in rows]}")
        planned = await self._audit_for_trade(["planned_sale_stop_cancel"], since, tid)
        silent = await self._audit_for_trade(
            ["stop_cancel_by_planned_sale_silent"], since, tid, budget_s=30,
            extra={"cancelled_order_id": stop_id})
        log.step("A6f", "NO 'unprotected' page: the stream recorded the planned-sale cancel",
                 bool(planned and silent),
                 f"planned_sale_stop_cancel {len(planned)}, stop_cancel_by_planned_sale_silent "
                 f"{len(silent)}" + ("" if silent else " — the paper stream paged or is not "
                                                       "running (check its log)"))

    async def _a8_mark_depth(self) -> None:
        p2 = self.state["p2"]
        if not p2.get("ready"):
            self.log.step("A8", "stamp P2 for the opening-auction sale", None,
                          "skipped — P2 not ready", status="SKIP")
            return
        # The stop the 19:01 sale must cancel is the row's stop AT MARKING TIME — not B2's restored
        # id, which anything replacing the stop between B3 and 19:01 would make stale.
        p2["stop_at_mark"] = (await self.env.trade(p2["trade_id"]))["stop_order_id"]
        await self.env.set_trade_cols(p2["trade_id"], {"exit_rule": "depth",
                                                       "depth_sell_pending_on": self.env.et_today()})
        p2["marked_at"] = self.env.now().isoformat()
        await self._save()
        self.log.step("A8", f"P2 #{p2['trade_id']} stamped exit_rule='depth', marked to sell at the "
                      f"next open (the 16:45 decision skips a same-day row; unit-tested)", True)

    async def _a8_check_depth_sale(self) -> None:
        env, log, p2 = self.env, self.log, self.state["p2"]
        if not p2.get("marked_at"):
            log.step("A9", "19:01 opening-auction sale", None, "skipped — P2 not marked",
                     status="SKIP")
            return
        tid = p2["trade_id"]
        since = datetime.fromisoformat(p2["marked_at"])
        stop_id = p2.get("stop_at_mark") or p2.get("restored_stop_id") \
            or (await env.trade(tid))["stop_order_id"]
        placed = await self._audit_for_trade(["depth_open_sale_placed"], since, tid)
        driver = "the PRODUCTION 19:01 job"
        if not placed:
            row = await env.trade(tid)
            if row.get("depth_sell_pending_on") is not None:
                driver = "THIS process (the production job had not taken it by 19:04)"
                async with env.exit_spy(tid):
                    await env.depth_open_sale(tid)
                placed = await self._audit_for_trade(["depth_open_sale_placed"], since, tid)
        other = await self._audit_for_trade(
            ["full_exit_rejected", "full_exit_skipped", "depth_sale_mark_stale",
             "depth_open_sale_error"], since, tid)
        rows = [r for r in await env.order_rows(tid) if r["purpose"] == "full_exit"]
        sale_id = rows[-1]["alpaca_order_id"] if rows else None
        sale = await env.get_order(sale_id) if sale_id else None
        old = await env.get_order(stop_id) if stop_id else None
        p2["sale_id"] = sale_id
        await self._save()
        log.step("A9", "the opening-auction (opg) sale queued for P2 at 19:01",
                 bool(placed and sale and canon(sale["status"]) in QUEUED_OK
                      and float(rows[-1]["qty"]) == 3
                      and canon(old and old["status"]) in {"canceled", "cancelled"}),
                 f"driven by {driver}; order {sale_id and sale_id[:8]} "
                 f"{canon(sale and sale['status'])} qty {rows and rows[-1]['qty']}; stop "
                 f"{stop_id and stop_id[:8]} {canon(old and old['status'])}; other rows "
                 f"{[r['event_type'] for r in other] or 'none'}")
        silent = await self._audit_for_trade(
            ["stop_cancel_by_planned_sale_silent"], since, tid, budget_s=30,
            extra={"cancelled_order_id": stop_id})
        log.step("A9b", "NO 'unprotected' page for the depth stop's cancel", bool(silent),
                 "silent row found" if silent else "NO stop_cancel_by_planned_sale_silent row")

    # ── Day B ──
    async def day_b(self) -> int:
        env, log = self.env, self.log
        self.state = env.load_state() or {}
        if not self.state:
            raise RehearsalRefused("no Day A state (file or audit row) — nothing to do")
        self.t1, self.t2, self.probe = self.state["tickers"]
        today = env.et_today()
        if today.isoformat() <= self.state["day_a"]:
            raise RehearsalRefused(f"Day B must run on a later day than Day A ({self.state['day_a']})")
        await self.preflight(day="day-b")
        env.install_page_router()
        day_a_start = datetime.fromisoformat(self.state["started_at"])
        try:
            await self._d1_overnight(day_a_start)
            await self._d2_fills(today)
            await self._d4_refresh(today)
            await self._d5_oco_cancel()
        except LiveTouched:
            raise
        except Exception as e:
            log.step("D", "Day B raised", False, f"{type(e).__name__}: {e}")
        finally:
            await self.cleanup()
        return self._summary("Day B")

    async def _d1_overnight(self, since: datetime) -> None:
        env, log, p1, p2 = self.env, self.log, self.state["p1"], self.state["p2"]
        log.note("09:00/09:15 coverage-detector check: replaced by the unit test tests/"
                 "test_position_coverage_check_527.py::test_a_queued_full_exit_beside_a_resting_"
                 "profit_take_covers_the_whole_position (CHECKED section — the detector is live-only)")
        ids = [x for x in (p1.get("trade_id"), p2.get("trade_id")) if x]
        rows = await env.audit_rows(None, since)
        mine = [r for r in rows if r["detail"].get("trade_id") in ids]
        log.note(f"audit rows naming the rehearsal trades since Day A start: "
                 f"{sorted({r['event_type'] for r in mine})}")
        # The rows must still be OPEN at 3 + 3 before the open — otherwise D3's "row closed by the
        # stream" could be passing on an overnight sync that closed it (a different mechanism).
        for label, p, cancelled in ((f"P1 {self.t1}", p1, p1.get("stop3_id")),
                                    (f"P2 {self.t2}", p2,
                                     p2.get("stop_at_mark") or p2.get("restored_stop_id"))):
            if not p.get("sale_id"):
                continue
            row = await env.trade(p["trade_id"])
            sid = row and row.get("stop_order_id")
            so = await env.get_order(sid) if sid else None
            ok = bool(row and row["status"] == "filled" and float(row["remaining_shares"]) == 3
                      and (sid is None or sid == cancelled
                           or canon(so and so["status"]) not in LIVE_STATUSES))
            log.step("D1r", f"{label}: row still open at 3 sh before the open, no live stop pointer",
                     ok, f"status {row and row['status']}, remaining "
                     f"{row and row['remaining_shares']}, stop pointer {sid and sid[:8]} "
                     f"{canon(so and so['status']) if so else ''}")
        for label, t, keep in ((f"P1 {self.t1}", self.t1, {p1.get("sale_id"), p1.get("oco_id")}),
                               (f"P2 {self.t2}", self.t2, {p2.get("sale_id")})):
            keep.discard(None)
            if not keep:
                continue
            legs = set()
            for k in keep:
                o = await env.get_order(k)
                legs |= {leg["id"] for leg in (o or {}).get("legs") or []}
            orders = await env.open_orders(t)
            extra = [o for o in orders if o["id"] not in keep | legs]
            log.step("D1", f"{label}: overnight jobs placed nothing beside the queued sale",
                     not extra, f"open {[(o['id'][:8], o['type'], o['qty']) for o in orders]}"
                     + (f"; UNEXPECTED {[(o['id'][:8], o['type']) for o in extra]}" if extra else ""))

    async def _d2_fills(self, today: date) -> None:
        env, log = self.env, self.log
        sales = [(n, self.state[n].get("sale_id"), t) for n, t in (("p1", self.t1), ("p2", self.t2))]
        sales = [s for s in sales if s[1]]
        if env.now() < self._at(today, T_DAYB_OPEN):
            log.note("waiting for the 09:30 open")
            await env.sleep_until(self._at(today, T_DAYB_OPEN))
        deadline = self._at(today, T_DAYB_FILL_DEADLINE)
        pending = {s[1] for s in sales}
        while pending and env.now() < deadline:
            for _, oid, _ in sales:
                if oid in pending and canon((await env.get_order(oid) or {}).get("status")) == "filled":
                    pending.discard(oid)
            if pending:
                await env.sleep(2.0)
        feed = env.data_feed()
        for name, oid, t in sales:
            o = await env.get_order(oid) or {}
            bar = await env.first_bar(t, today)
            px, at = _num(o.get("filled_avg_price")), o.get("filled_at")
            opn = bar and bar.get("open")
            slip = (f"{(px - opn) / opn * 100:+.2f}% vs the first-minute open ${opn:.2f} "
                    f"(feed {feed}; IEX is not the official open — `status` re-reads later)"
                    if px and opn else "no open to compare")
            self.state[name]["fill"] = {"price": px, "at": at, "first_bar_open": opn, "feed": feed}
            log.step("D2", f"{name.upper()} {t} sale filled by 09:40", canon(o.get("status")) == "filled",
                     f"{canon(o.get('status'))} at {at} for ${px}; {slip}")
        await self._save()
        # Rows: P2 closes; P1 stays open at the OCO third.
        for _ in range(30):
            r1 = await env.trade(self.state["p1"]["trade_id"]) if self.state["p1"].get("trade_id") else None
            r2 = await env.trade(self.state["p2"]["trade_id"]) if self.state["p2"].get("trade_id") else None
            if (not r2 or r2["status"] == "closed") and (not r1 or float(r1["remaining_shares"]) == 1):
                break
            await env.sleep(2.0)
        if r2:
            log.step("D3", f"P2 row closed by the stream after the auction fill", r2["status"] == "closed",
                     f"status {r2['status']}, remaining {r2['remaining_shares']}")
        if r1:
            log.step("D3b", "P1 row stays open at the OCO third (1 sh)",
                     r1["status"] == "filled" and float(r1["remaining_shares"]) == 1,
                     f"status {r1['status']}, remaining {r1['remaining_shares']}")

    async def _d4_refresh(self, today: date) -> None:
        env, log, p1 = self.env, self.log, self.state["p1"]
        if not p1.get("trade_id"):
            return
        await env.sleep_until(self._at(today, T_DAYB_REFRESH_CHECK))
        rows = [r for r in await env.audit_rows(["stop_refresh_ran"], self._at(today, dtime(9, 34)))]
        d = rows[-1]["detail"] if rows else {}
        covered = self.t1 in (d.get("covered_by_resting_exit") or []) + (d.get("already_covered") or [])
        ok = bool(rows and covered and self.t1 not in (d.get("placed_tickers") or [])
                  and self.t1 not in (d.get("unprotected") or []))
        log.step("D4", "the 09:35 refresh did nothing for P1 (covered by the resting OCO)", ok,
                 f"stop_refresh_ran: {rows[-1]['summary'] if rows else 'NO ROW since 09:34'}; "
                 f"detail {json.dumps({k: d.get(k) for k in ('placed_tickers', 'covered_by_resting_exit', 'already_covered', 'unprotected')})}")

    async def _d5_oco_cancel(self) -> None:
        env, log, p1 = self.env, self.log, self.state["p1"]
        oco_id = p1.get("oco_id")
        o = await env.get_order(oco_id) if oco_id else None
        if not o or canon(o["status"]) not in LIVE_STATUSES:
            log.step("D5", "cancel the OCO → the third re-protected", None,
                     f"skipped — OCO {canon(o and o['status'])}", status="SKIP")
            return
        await env.cancel(oco_id)
        found = None
        for _ in range(30):
            row = await env.trade(p1["trade_id"])
            sid = row and row.get("stop_order_id")
            so = await env.get_order(sid) if sid else None
            if so and canon(so["status"]) in LIVE_STATUSES and "stop" in str(so.get("type")) \
                    and float(so["qty"]) == 1 and sid not in {oco_id, p1.get("stop3_id")}:
                found = so
                break
            await env.sleep(2.0)
        log.step("D5", "OCO cancelled → the existing handler re-protects the third (1-sh stop)",
                 bool(found), f"new stop {found['id'][:8]} @ ${found.get('stop_price')}" if found
                 else "no live 1-sh stop on the row within 60 s")

    # ── status / cleanup ──
    async def status(self) -> int:
        env, log = self.env, self.log
        self.state = env.load_state() or {}
        await self.preflight(day="status")
        log.note(f"state: {json.dumps(self.state, default=str)[:1500]}")
        for t in self.state.get("tickers") or [self.t1, self.t2, self.probe]:
            pos = await env.position(t)
            orders = await env.open_orders(t)
            log.note(f"{t}: position {pos and (pos['qty'], pos['qty_available'])}; open orders "
                     f"{[(o['id'][:8], o['side'], o['type'], o['qty'], canon(o['status'])) for o in orders]}; "
                     f"rehearsal rows {await env.sentinel_rows(t)}")
        for name in ("p1", "p2"):
            p = self.state.get(name) or {}
            if p.get("trade_id"):
                log.note(f"{name}: row {await env.trade(p['trade_id'])}")
            if p.get("fill") and self.state.get("day_a"):
                log.note(f"{name}: fill {p['fill']}")
        return 0

    async def cleanup(self) -> int:
        env, log = self.env, self.log
        if not self.state:
            self.state = env.load_state() or {}
            if not env.tripwire_armed:
                await self.preflight(day="cleanup")
        tickers = self.state.get("tickers") or [self.t1, self.t2, self.probe]
        trade_ids = set()
        for t in tickers:
            trade_ids |= set(await env.sentinel_rows(t))
        base = set(self.state.get("order_ids") or [])
        for p in (self.state.get("p1") or {}, self.state.get("p2") or {}):
            base |= {v for k, v in p.items() if k.endswith("_id") and isinstance(v, str)}
        residue = []
        foreign_by_ticker: dict[str, list] = {}
        # Rounds: cancelling a rehearsal OCO lets the production handler re-protect the third, which
        # places a NEW stop (pointed at by our row) — so re-derive and cancel until nothing of ours
        # is live. Every stop we cancel is first marked as a planned cancel, so the stream records
        # it instead of paging "unprotected".
        for _round in range(4):
            ours, stop_of = set(base), {}
            for tid in trade_ids:
                ours |= {r["alpaca_order_id"] for r in await env.order_rows(tid)
                         if r["alpaca_order_id"]}
                row = await env.trade(tid)
                if row and row.get("stop_order_id"):
                    ours.add(row["stop_order_id"])
                    stop_of[row["stop_order_id"]] = (tid, row["ticker"])
            for oid in list(ours):
                o = await env.get_order(oid)
                ours |= {leg["id"] for leg in (o or {}).get("legs") or []}
            live_mine = 0
            for t in tickers:
                orders = await env.open_orders(t)
                mine = [o for o in orders
                        if o["id"] in ours or is_ours_coid(o.get("client_order_id"), t)]
                foreign_by_ticker[t] = [o for o in orders if o not in mine]
                live_mine += len(mine)
                for o in sorted(mine, key=lambda o: 0 if o.get("legs") else 1):
                    if o["id"] in stop_of:
                        await env.mark_planned_cancel(*stop_of[o["id"]], o["id"])
                    await env.cancel(o["id"])
            if not live_mine:
                break
            await env.sleep(3.0)
        for t in tickers:
            foreign_orders = foreign_by_ticker.get(t) or []
            pos = await env.position(t)
            qty = float(pos["qty"]) if pos else 0
            foreign_rows = await env.foreign_open_rows(t)
            if qty < 0:
                residue.append(f"{t}: SHORT {qty} sh — not touched, cover by hand")
            elif qty and (foreign_rows or foreign_orders):
                residue.append(f"{t}: {qty} sh NOT flattened — {foreign_rows} non-rehearsal paper "
                               f"row(s) / {len(foreign_orders)} foreign order(s) on it")
            elif qty:
                # A refused flatten (e.g. a re-protect stop reserving the shares) must not abort
                # cleanup before the rows are deleted and the end row written — record it, go on.
                try:
                    sell = await env.submit(t, qty, "sell", kind="market", tif="day")
                    st = await self._wait_status(sell["id"], {"filled"}, budget_s=20)
                    if st != "filled":
                        residue.append(f"{t}: flatten order {sell['id'][:8]} is {st} (queued for "
                                       f"the next open if the market is shut)")
                except LiveTouched:
                    raise
                except Exception as e:
                    residue.append(f"{t}: flatten of {qty} sh FAILED ({type(e).__name__}: "
                                   f"{str(e)[:160]}) — re-run `cleanup`")
            if foreign_orders:
                residue.append(f"{t}: left {len(foreign_orders)} order(s) that are not ours")
        deleted = await env.delete_trades(sorted(trade_ids))
        left_rows = [t for t in tickers if await env.sentinel_rows(t)]
        for t in tickers:
            pos = await env.position(t)
            if pos and abs(float(pos["qty"])) and not any(r.startswith(t) for r in residue):
                residue.append(f"{t}: still {pos['qty']} sh")
        if left_rows:
            residue.append(f"rehearsal rows remain for {left_rows}")
        audit = await env.audit_rows(None, datetime.fromisoformat(self.state["started_at"])) \
            if self.state.get("started_at") else []
        touched = [r for r in audit if r["detail"].get("trade_id") in trade_ids]
        await env.write_audit(END_EVENT, f"#687 paper rehearsal cleanup: deleted {deleted} row(s); "
                              f"residue {len(residue)}",
                              {"trade_ids": sorted(trade_ids), "residue": residue,
                               "audit_ids_naming_rehearsal_trades": [r["id"] for r in touched]})
        log.note(f"production audit rows that name the rehearsal trades (they stay; account_mode "
                 f"'paper' in their detail): {[(r['id'], r['event_type']) for r in touched]}")
        self.log.step("CLEANUP", f"orders cancelled, positions flat, {deleted} rehearsal row(s) "
                      f"deleted", not residue, "; ".join(residue) or "clean")
        env.clear_state()
        return 0 if not residue else 1

    def _summary(self, label: str) -> int:
        fails = self.log.failed()
        self.log.note(f"{label} RESULT: {sum(r['status'] == 'PASS' for r in self.log.results)} PASS, "
                      f"{len(fails)} FAIL, {sum(r['status'] == 'SKIP' for r in self.log.results)} SKIP"
                      + (f" — FAILED: {[f['step'] for f in fails]}" if fails else ""))
        return 1 if fails else 0


# ── The real environment (apollo-execution) ────────────────────────────────────────────────────────

class RealEnv:
    fake = False

    def __init__(self, *, send_pages: bool = True, state_path: str | None = None):
        from agents.market_intelligence.broker import alpaca_client, order_manager
        from agents.market_intelligence import db
        self.alpaca, self.om, self.db = alpaca_client, order_manager, db
        self.pages: list[dict] = []
        self.send_pages = send_pages
        self.tripwire_armed = False
        self.state_path = state_path or os.path.join(HERE, "rehearsal_state.json")
        self._last_coid = None

    # clock
    def now(self) -> datetime:
        return datetime.now(_ET)

    def et_today(self) -> date:
        return self.now().date()

    async def sleep(self, s: float) -> None:
        await asyncio.sleep(s)

    async def sleep_until(self, when: datetime) -> None:
        while True:
            left = (when - self.now()).total_seconds()
            if left <= 0:
                return
            await asyncio.sleep(min(left, 30.0))

    # guards
    async def account_ids(self) -> dict:
        paper_client = self.alpaca.get_trading_client(ACCOUNT_MODE)
        paper = await asyncio.to_thread(paper_client.get_account)
        base = client_base_url(paper_client)
        live_id = None
        pk, lk = os.environ.get("ALPACA_PAPER_API_KEY"), os.environ.get("ALPACA_LIVE_API_KEY")
        if lk:
            # The ONLY live call this process makes: a read of the account id, before the tripwire.
            live = await asyncio.to_thread(self.alpaca.get_trading_client("live").get_account)
            live_id = str(live.id)
        return {"paper_id": str(paper.id), "live_id": live_id, "paper_base_url": base,
                "same_keys": bool(pk and lk and pk == lk)}

    def arm_tripwire(self) -> None:
        arm_live_tripwire(self.alpaca)
        self.tripwire_armed = True

    def install_page_router(self) -> None:
        original = self.om.send_telegram_message
        if getattr(original, "_rehearsal_router", False):
            return

        async def router(text, *args, **kwargs):
            routed = route_page(str(text))
            self.pages.append({"text": routed, "sent": self.send_pages})
            if self.send_pages:
                return await original(routed, *args, **kwargs)
            return True

        router._rehearsal_router = True
        self.om.send_telegram_message = router

    # broker
    async def position(self, ticker):
        return await self.alpaca.get_position(ticker, account_mode=ACCOUNT_MODE)

    async def open_orders(self, ticker):
        orders = await self.alpaca.get_open_orders(ticker, account_mode=ACCOUNT_MODE,
                                                   raise_on_error=True)
        return [o for o in orders if o.get("symbol") == ticker]

    async def get_order(self, oid):
        return await self.alpaca.get_order(oid, account_mode=ACCOUNT_MODE)

    async def cancel(self, oid) -> bool:
        return await self.alpaca.cancel_order(oid, account_mode=ACCOUNT_MODE)

    def _coid(self, ticker: str) -> str:
        coid = self.alpaca.make_client_order_id(ACCOUNT_MODE, TAG_SIGNAL_TYPE, ticker)
        while coid == self._last_coid:
            time.sleep(0.002)
            coid = self.alpaca.make_client_order_id(ACCOUNT_MODE, TAG_SIGNAL_TYPE, ticker)
        self._last_coid = coid
        return coid

    async def submit(self, ticker, qty, side, *, kind, tif, limit=None, stop=None) -> dict:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest, StopOrderRequest
        common = dict(symbol=ticker, qty=qty,
                      side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                      time_in_force={"day": TimeInForce.DAY, "gtc": TimeInForce.GTC,
                                     "cls": TimeInForce.CLS, "opg": TimeInForce.OPG}[tif],
                      client_order_id=self._coid(ticker))
        if kind == "market":
            req = MarketOrderRequest(**common)
        elif kind == "limit":
            req = LimitOrderRequest(limit_price=round(limit, 2), **common)
        else:
            req = StopOrderRequest(stop_price=round(stop, 2), **common)
        client = self.alpaca.get_trading_client(ACCOUNT_MODE)
        order = await asyncio.to_thread(client.submit_order, req)
        return self.alpaca._order_to_dict(order)

    def data_feed(self) -> str:
        return str(self.alpaca.get_data_feed())

    async def first_bar(self, ticker, day):
        return await self.alpaca.get_first_bar(ticker, day)

    # db
    async def _pool(self):
        return await self.db.get_pool()

    async def insert_trade(self, *, ticker, shares, entry, stop, stop_id, alert_date) -> int:
        # partial_taken = TRUE: production's 5-minute `scan_profit_triggers` selects EVERY filled row
        # with partial_taken FALSE (no signal_type filter) and, on this row's R frame (entry 3% under
        # the fill, stop 5% under → R = 2% of the fill, target +2R = 1% above the fill), would SELL a
        # third of P2 on an ordinary +1% day, and page / write failure rows every poll for P1. No
        # function the rehearsal drives reads partial_taken (it is read only by that scan and the
        # EOD ladder, which skips same-day rows), so TRUE takes both rows out of its reach only.
        pool = await self._pool()
        async with pool.acquire() as conn:
            tid = await conn.fetchval("""
                INSERT INTO mi_live_trades
                    (ticker, alert_date, status, account_mode, signal_type, entry_shares,
                     remaining_shares, entry_price, stop_price, hard_stop, orb_low, stop_order_id,
                     hold_days, partial_taken, filled_at)
                VALUES ($1, $2, 'filled', $3, $4, $5, $5, $6, $7, $7, $7, $8, 0, TRUE, NOW())
                RETURNING id
            """, ticker, alert_date, ACCOUNT_MODE, TAG_SIGNAL_TYPE, float(shares), float(entry),
                float(stop), stop_id)
            mode = await conn.fetchval("SELECT account_mode FROM mi_live_trades WHERE id = $1", tid)
        if mode != ACCOUNT_MODE:
            raise LiveTouched(f"row {tid} resolved account_mode={mode!r}")
        return tid

    async def trade(self, tid):
        pool = await self._pool()
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT * FROM mi_live_trades WHERE id = $1", tid)
        if r and r["account_mode"] != ACCOUNT_MODE:
            raise LiveTouched(f"row {tid} is account_mode={r['account_mode']!r}")
        return dict(r) if r else None

    async def set_trade_cols(self, tid, cols: dict) -> None:
        allowed = {"exit_rule", "depth_sell_pending_on"}
        if set(cols) - allowed:
            raise ValueError(f"only {allowed} may be set by the rehearsal")
        pool = await self._pool()
        sets = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(cols))
        async with pool.acquire() as conn:
            await conn.execute(f"UPDATE mi_live_trades SET {sets} WHERE id = $1 "
                               f"AND signal_type = $2 AND account_mode = 'paper'",
                               tid, TAG_SIGNAL_TYPE, *cols.values())

    async def order_rows(self, tid):
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT alpaca_order_id, purpose, qty, status FROM mi_live_orders "
                                    "WHERE trade_id = $1 ORDER BY id", tid)
        return [dict(r) for r in rows]

    async def audit_rows(self, events, since: datetime):
        pool = await self._pool()
        async with pool.acquire() as conn:
            if events:
                rows = await conn.fetch("SELECT id, event_type, summary, detail, created_at FROM "
                                        "mi_audit_log WHERE event_type = ANY($1::text[]) AND "
                                        "created_at >= $2 ORDER BY id", list(events), since)
            else:
                rows = await conn.fetch("SELECT id, event_type, summary, detail, created_at FROM "
                                        "mi_audit_log WHERE created_at >= $1 ORDER BY id", since)
        out = []
        for r in rows:
            try:
                d = json.loads(r["detail"] or "{}")
            except (TypeError, ValueError):
                d = {}
            out.append({"id": r["id"], "event_type": r["event_type"], "summary": r["summary"],
                        "detail": d if isinstance(d, dict) else {}})
        return out

    async def write_audit(self, event, summary, detail) -> None:
        await self.db.log_audit_event(event, summary, json.dumps(detail, default=str))

    async def lock_held(self, tid) -> bool:
        pool = await self._pool()
        async with pool.acquire() as conn:
            return bool(await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND "
                "classid::bigint = $1 AND objid::bigint = $2 AND granted)", LOCK_NAMESPACE, tid))

    async def foreign_open_rows(self, ticker) -> int:
        pool = await self._pool()
        async with pool.acquire() as conn:
            return int(await conn.fetchval(
                "SELECT COUNT(*) FROM mi_live_trades WHERE ticker = $1 AND account_mode = 'paper' "
                "AND status IN ('filled', 'order_placed') AND signal_type IS DISTINCT FROM $2",
                ticker, TAG_SIGNAL_TYPE))

    async def sentinel_rows(self, ticker) -> list[int]:
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM mi_live_trades WHERE ticker = $1 AND "
                                    "account_mode = 'paper' AND signal_type = $2 ORDER BY id",
                                    ticker, TAG_SIGNAL_TYPE)
        return [r["id"] for r in rows]

    async def open_paper_rows(self) -> int:
        pool = await self._pool()
        async with pool.acquire() as conn:
            return int(await conn.fetchval("SELECT COUNT(*) FROM mi_live_trades WHERE account_mode "
                                           "= 'paper' AND status = 'filled' AND remaining_shares > 0"))

    async def paper_toggles(self) -> dict:
        out = {}
        for k in ("profit_take_resting_limit", "profit_take_oco", "magna53_depth_exit"):
            try:
                row = await self.db.get_safeguard_state(k, ACCOUNT_MODE)
                out[k] = (row or {}).get("state", "no row")
            except Exception as e:   # read-only context for the log
                out[k] = f"unreadable ({e})"
        return out

    async def delete_trades(self, ids) -> int:
        pool = await self._pool()
        n = 0
        async with pool.acquire() as conn:
            for tid in ids:
                async with conn.transaction():
                    await conn.execute("SET LOCAL mi.allow_trade_delete = 'yes'")
                    await conn.execute("DELETE FROM mi_live_orders WHERE trade_id = $1", tid)
                    r = await conn.execute("DELETE FROM mi_live_trades WHERE id = $1 AND "
                                           "signal_type = $2 AND account_mode = 'paper'",
                                           tid, TAG_SIGNAL_TYPE)
                    n += int(r.split()[-1])
        return n

    async def mark_planned_cancel(self, tid, ticker, stop_id) -> None:
        """Cleanup cancels a rehearsal stop ON PURPOSE: write the marker the stream honours, so the
        cancel is recorded (stop_cancel_by_planned_sale_silent) instead of paged as unprotected."""
        await self.om._record_planned_sale_stop_cancel(
            tid, ticker, stop_id, "paper_rehearsal_687_cleanup", ACCOUNT_MODE,
            site="paper_rehearsal_687_cleanup")

    # production functions under test
    async def partial_exit(self, tid, shares, limit_price) -> bool:
        om = self.om
        real_rl, real_oco = om._profit_take_resting_limit_enabled, om._profit_take_oco_enabled

        async def _paper_on(account_mode):   # in-process only; the scheduler process is untouched
            return account_mode == ACCOUNT_MODE

        om._profit_take_resting_limit_enabled = _paper_on
        om._profit_take_oco_enabled = _paper_on
        try:
            return await om.execute_partial_exit(tid, int(shares), force=True,
                                                 limit_price=float(limit_price))
        finally:
            om._profit_take_resting_limit_enabled = real_rl
            om._profit_take_oco_enabled = real_oco

    async def full_exit(self, tid, reason) -> bool:
        return await self.om.execute_full_exit(tid, reason)

    async def depth_open_sale(self, tid) -> bool:
        return await self.om.execute_depth_open_sale(tid)

    async def replace_stop_price(self, tid, stop_id, new_price) -> dict:
        """The price-only replace the breakeven arm uses (atomic at the broker), under the trade lock,
        with the pointer written by the single authorized writer."""
        row = await self.trade(tid)
        async with self.om._trade_advisory_lock(tid):
            new = await self.alpaca.replace_order(
                stop_id, stop_price=new_price, account_mode=ACCOUNT_MODE,
                client_order_id=self._coid(row["ticker"]))
            await self.om.set_stop_order_id(tid, new["id"], reason="rehearsal_687_price_replace",
                                            account_mode=ACCOUNT_MODE)
            pool = await self._pool()
            async with pool.acquire() as conn:
                await conn.execute("UPDATE mi_live_trades SET stop_price = $2 WHERE id = $1 AND "
                                   "signal_type = $3", tid, float(new_price), TAG_SIGNAL_TYPE)
        return new

    @contextlib.asynccontextmanager
    async def exit_spy(self, tid):
        """Record cancel / close / stop / opg calls the production function makes (and, at the sale,
        whether the trade lock is held and how many shares are free)."""
        a = self.alpaca
        events: list[dict] = []
        saved = {n: getattr(a, n) for n in ("cancel_order", "close_position", "place_stop_order",
                                            "place_market_on_open_sell")}

        def wrap(name):
            real = saved[name]

            async def spy(*args, **kwargs):
                ev = {"name": name, "args": args, "qty": kwargs.get("qty"),
                      "mode": kwargs.get("account_mode")}
                if name in ("close_position", "place_market_on_open_sell"):
                    ev["lock_held"] = await self.lock_held(tid)
                    pos = await self.position(args[0])
                    ev["qty_available"] = pos and pos.get("qty_available")
                    if name == "place_market_on_open_sell" and ev["qty"] is None and len(args) > 1:
                        ev["qty"] = args[1]
                ev["t"] = time.monotonic()
                ev["at"] = self.now().isoformat()
                try:
                    out = await real(*args, **kwargs)
                    ev["ok"] = out is not False
                    return out
                except Exception as e:
                    ev["ok"], ev["error"] = False, str(e)
                    raise
                finally:
                    events.append(ev)
            return spy

        for n in saved:
            setattr(a, n, wrap(n))
        try:
            yield events
        finally:
            for n, f in saved.items():
                setattr(a, n, f)

    # state
    async def save_state(self, state) -> None:
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, default=str, indent=1)
        # Also in the DB: a deploy in the 21:15 window can restart the container between the days.
        await self.write_audit(STATE_EVENT, "#687 paper rehearsal state", state)

    def load_state(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, encoding="utf-8") as fh:
                return json.load(fh)
        return None

    async def load_state_from_audit(self):
        """The newest saved state — unless a cleanup (END_EVENT) came after it: a finished run is
        never resumed."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT event_type, detail FROM mi_audit_log WHERE event_type = "
                                    "ANY($1::text[]) ORDER BY id DESC LIMIT 1",
                                    [STATE_EVENT, END_EVENT])
        if not r or r["event_type"] != STATE_EVENT:
            return None
        return json.loads(r["detail"])

    def clear_state(self) -> None:
        if os.path.exists(self.state_path):
            os.replace(self.state_path, self.state_path + ".done")


# ── The fake environment (--dry-run and the tests): a small broker + book + the production behaviours
#    the steps observe. It exercises the STEP LOGIC — guards, sequencing, waits, assertions, logging —
#    not the production functions themselves (those are covered by their own unit tests). ─────────────

class FakeEnv:
    fake = True

    def __init__(self, *, start: datetime, held=None, open_orders=None, same_account=False,
                 stream_silent=True, prod_depth_job=True, broken_close_qty=False,
                 foreign_rows=None, partial_taken_false=False):
        self.clock = start
        self.pages: list[dict] = []
        self.tripwire_armed = False
        self.calls: list[tuple] = []           # (fn, account_mode) for every broker call
        self.prices = {"KO": 70.0, "PEP": 150.0, "PG": 160.0}
        self.positions: dict[str, float] = dict(held or {})
        self.orders: dict[str, dict] = {}
        self.trades: dict[int, dict] = {}
        self.live_orders: list[dict] = []
        self.audit: list[dict] = []
        self.locked: set[int] = set()
        self.state = None
        self.same_account = same_account
        self.stream_silent = stream_silent
        self.prod_depth_job = prod_depth_job
        self.broken_close_qty = broken_close_qty
        self.partial_taken_false = partial_taken_false   # a DB that drops the insert's TRUE
        self.foreign_rows = dict(foreign_rows or {})
        self._n = 0
        self._ran = set()
        self._spy: list | None = None
        for t, q in (open_orders or {}).items():
            self._new(t, q, "sell", "limit", "gtc", status="new", limit=999.0)

    # clock
    def now(self):
        return self.clock

    def et_today(self):
        return self.clock.date()

    async def sleep(self, s):
        await self.sleep_until(self.clock + timedelta(seconds=s))

    async def sleep_until(self, when):
        for t, fn in ((dtime(9, 30), self._open_auction), (dtime(9, 35), self._refresh_0935),
                      (dtime(19, 1), self._depth_job_1901)):
            at = datetime.combine(self.clock.date(), t, tzinfo=_ET)
            key = (self.clock.date(), t)
            if self.clock < at <= when and key not in self._ran:
                self._ran.add(key)
                self.clock = at
                await fn()
        if when > self.clock:
            self.clock = when

    def _hours(self):
        t = self.clock.timetz().replace(tzinfo=None)
        return self.clock.weekday() < 5 and dtime(9, 30) <= t < dtime(16, 0)

    # guards
    async def account_ids(self):
        return {"paper_id": "PAPER-1", "live_id": "PAPER-1" if self.same_account else "LIVE-9",
                "paper_base_url": "https://paper-api.alpaca.markets", "same_keys": False}

    def arm_tripwire(self):
        self.tripwire_armed = True

    def install_page_router(self):
        pass

    def _page(self, text):
        self.pages.append({"text": route_page(text), "sent": False})

    # broker
    def _call(self, fn, mode=ACCOUNT_MODE):
        self.calls.append((fn, mode))
        if mode != ACCOUNT_MODE:
            raise LiveTouched(fn)

    def _new(self, t, qty, side, kind, tif, *, status, limit=None, stop=None, order_class="simple",
             legs=None, coid=None):
        self._n += 1
        oid = f"ord{self._n:04d}-0000-0000"
        o = {"id": oid, "symbol": t, "side": side, "type": kind, "qty": float(qty), "tif": tif,
             "status": status, "limit_price": limit, "stop_price": stop, "order_class": order_class,
             "legs": legs or [], "client_order_id": coid, "filled_avg_price": None, "filled_at": None,
             "filled_qty": 0}
        self.orders[oid] = o
        return o

    def _held(self, t, exclude=()):
        return sum(o["qty"] for o in self.orders.values()
                   if o["symbol"] == t and o["side"] == "sell" and o["status"] in LIVE_STATUSES
                   and o["id"] not in exclude and not o.get("is_leg"))

    def _avail(self, t):
        return self.positions.get(t, 0.0) - self._held(t)

    def _fill(self, o, px=None):
        px = px or self.prices[o["symbol"]]
        o.update(status="filled", filled_avg_price=px, filled_at=self.clock.isoformat(),
                 filled_qty=o["qty"])
        self.positions[o["symbol"]] = self.positions.get(o["symbol"], 0) + (
            o["qty"] if o["side"] == "buy" else -o["qty"])

    async def position(self, t):
        self._call("get_position")
        q = self.positions.get(t, 0.0)
        return {"symbol": t, "qty": q, "qty_available": self._avail(t)} if q else None

    async def open_orders(self, t):
        self._call("get_open_orders")
        return [dict(o) for o in self.orders.values() if o["symbol"] == t
                and o["status"] in LIVE_STATUSES]

    async def get_order(self, oid):
        self._call("get_order")
        return dict(self.orders[oid]) if oid in self.orders else None

    async def cancel(self, oid):
        self._call("cancel_order")
        o = self.orders.get(oid)
        if not o or o["status"] not in LIVE_STATUSES:
            return False
        o["status"] = "canceled"
        for leg in o["legs"]:
            self.orders[leg["id"]]["status"] = "canceled"
        if self._spy is not None:
            self._spy.append({"name": "cancel_order", "args": (oid,), "t": self._mono(), "ok": True})
        self._stream_on_cancel(o)
        return True

    def _mono(self):
        return self.clock.timestamp()

    async def submit(self, t, qty, side, *, kind, tif, limit=None, stop=None):
        self._call("submit_order")
        now_t = self.clock.timetz().replace(tzinfo=None)
        if tif == "cls" and now_t >= dtime(15, 50):
            raise RuntimeError('{"code":42210000,"message":"market on close orders must be '
                               'submitted before 15:50"}')
        if tif == "opg" and dtime(9, 28) <= now_t < dtime(19, 0):
            raise RuntimeError('{"code":42210000,"message":"opg orders must be submitted after '
                               '7:00pm"}')
        if side == "sell" and qty > self._avail(t) + 1e-9:
            raise RuntimeError(f'{{"code":40310000,"message":"insufficient qty available for order '
                               f'(requested: {qty:g}, available: {self._avail(t):g})",'
                               f'"held_for_orders":"{self._held(t):g}"}}')
        o = self._new(t, qty, side, kind, tif, status="accepted", limit=limit, stop=stop,
                      coid=f"apollo_paper_{TAG_SIGNAL_TYPE}_{t}_{self._n}")
        if kind == "market" and tif == "day" and self._hours():
            self._fill(o)
        elif kind in ("stop", "limit") or tif in ("cls", "opg") or not self._hours():
            o["status"] = "new"
        return dict(o)

    def data_feed(self):
        return "iex"

    async def first_bar(self, t, day):
        self._call("get_stock_bars")
        return {"open": self.prices[t]}

    # db
    async def insert_trade(self, *, ticker, shares, entry, stop, stop_id, alert_date):
        tid = 9000 + len(self.trades) + 1
        self.trades[tid] = {"id": tid, "ticker": ticker, "alert_date": alert_date, "status": "filled",
                            "account_mode": ACCOUNT_MODE, "signal_type": TAG_SIGNAL_TYPE,
                            "entry_shares": shares, "remaining_shares": float(shares),
                            "entry_price": entry, "stop_price": stop, "hard_stop": stop,
                            "stop_order_id": stop_id, "exit_rule": None,
                            "depth_sell_pending_on": None,
                            "partial_taken": not self.partial_taken_false}
        return tid

    async def trade(self, tid):
        return dict(self.trades[tid]) if tid in self.trades else None

    async def set_trade_cols(self, tid, cols):
        self.trades[tid].update(cols)

    async def order_rows(self, tid):
        return [dict(r) for r in self.live_orders if r["trade_id"] == tid]

    def _audit(self, event, detail, summary=""):
        self.audit.append({"id": len(self.audit) + 1, "event_type": event, "summary": summary,
                           "detail": detail, "at": self.clock})

    async def audit_rows(self, events, since):
        return [dict(r) for r in self.audit
                if (events is None or r["event_type"] in events) and r["at"] >= since]

    async def write_audit(self, event, summary, detail):
        self._audit(event, detail, summary)

    async def lock_held(self, tid):
        return tid in self.locked

    async def mark_planned_cancel(self, tid, ticker, stop_id):
        self._audit("planned_sale_stop_cancel", {"trade_id": tid, "stop_order_id": stop_id})

    async def foreign_open_rows(self, t):
        return self.foreign_rows.get(t, 0)

    async def sentinel_rows(self, t):
        return [i for i, r in self.trades.items() if r["ticker"] == t]

    async def open_paper_rows(self):
        return sum(1 for r in self.trades.values() if r["status"] == "filled")

    async def paper_toggles(self):
        return {"profit_take_resting_limit": "on", "profit_take_oco": "on",
                "magna53_depth_exit": "no row"}

    async def delete_trades(self, ids):
        for i in ids:
            self.trades.pop(i, None)
        self.live_orders = [r for r in self.live_orders if r["trade_id"] not in ids]
        return len(ids)

    # production behaviours (simulated)
    def _record_order(self, tid, o, purpose):
        self.live_orders.append({"trade_id": tid, "alpaca_order_id": o["id"], "purpose": purpose,
                                 "qty": o["qty"], "status": o["status"]})

    async def partial_exit(self, tid, shares, limit_price):
        r = self.trades[tid]
        old = self.orders[r["stop_order_id"]]
        old["status"] = "replaced"
        stop2 = self._new(r["ticker"], r["remaining_shares"] - shares, "sell", "stop", "gtc",
                          status="new", stop=old["stop_price"])
        leg = self._new(r["ticker"], shares, "sell", "stop", "gtc", status="held",
                        stop=max(r["stop_price"], r["entry_price"]))
        leg["is_leg"] = True
        oco = self._new(r["ticker"], shares, "sell", "limit", "gtc", status="new",
                        limit=limit_price, order_class="oco", legs=[{"id": leg["id"]}])
        self._record_order(tid, oco, "partial_exit")
        stop2["status"] = "replaced"
        be = self._new(r["ticker"], stop2["qty"], "sell", "stop", "gtc", status="new",
                       stop=r["entry_price"])
        r.update(stop_order_id=be["id"], stop_price=r["entry_price"])
        return True

    async def replace_stop_price(self, tid, stop_id, new_price):
        o = self.orders[stop_id]
        o["status"] = "replaced"
        n = self._new(o["symbol"], o["qty"], "sell", "stop", "gtc", status="new", stop=new_price)
        self.trades[tid].update(stop_order_id=n["id"], stop_price=new_price)
        return dict(n)

    @contextlib.asynccontextmanager
    async def exit_spy(self, tid):
        self._spy = []
        try:
            yield self._spy
        finally:
            self._spy = None

    def _spy_ev(self, **ev):
        if self._spy is not None:
            ev.setdefault("t", self._mono())
            self._spy.append(ev)

    async def _sale(self, tid, reason, vehicle):
        r = self.trades[tid]
        t, stop_id = r["ticker"], r["stop_order_id"]
        self.locked.add(tid)
        try:
            pending = [x for x in self.live_orders if x["trade_id"] == tid
                       and x["purpose"] == "partial_exit"
                       and self.orders[x["alpaca_order_id"]]["status"] in LIVE_STATUSES]
            sell_qty = None
            if pending or vehicle == "opg":
                held = self._held(t, exclude=(stop_id,))
                sell_qty = int(min(self.positions[t] - held,
                                   r["remaining_shares"] - sum(x["qty"] for x in pending)))
            self._audit("planned_sale_stop_cancel", {"trade_id": tid, "stop_order_id": stop_id})
            await self.cancel(stop_id)
            self.clock += timedelta(seconds=1)
            qty = sell_qty if sell_qty is not None else self.positions[t]
            if vehicle == "opg":
                self._spy_ev(name="place_market_on_open_sell", args=(t, qty), qty=qty, ok=True,
                             lock_held=True, qty_available=self._avail(t))
                o = self._new(t, qty, "sell", "market", "opg", status="accepted")
            else:
                ev = {"name": "close_position", "args": (t,),
                      "qty": None if self.broken_close_qty else sell_qty,
                      "lock_held": True, "qty_available": self._avail(t)}
                if qty > self._avail(t) + 1e-9:
                    err = (f"insufficient qty available for order (requested: {qty:g}, "
                           f"available: {self._avail(t):g}) held_for_orders")
                    self._spy_ev(**ev, ok=False, error=err)
                    self._audit("full_exit_rejected", {"trade_id": tid})
                    self.clock += timedelta(seconds=1)
                    free = self.positions[t] - self._held(t, exclude=(stop_id,))
                    restored = self._new(t, min(free, r["remaining_shares"]), "sell", "stop", "gtc",
                                         status="new", stop=r["stop_price"])
                    self._spy_ev(name="place_stop_order", args=(t,), qty=restored["qty"], ok=True)
                    r["stop_order_id"] = restored["id"]
                    self._page(f"📄 PAPER ⚠️ Full exit FAILED for {t}: {err}\nStop re-placed")
                    return False
                self._spy_ev(**ev, ok=True)
                o = self._new(t, qty, "sell", "market", "day", status="accepted")
            self._record_order(tid, o, "full_exit")
            if vehicle == "opg":
                r["depth_sell_pending_on"] = None
                self._audit("depth_open_sale_placed", {"trade_id": tid, "order_id": o["id"]})
            self._page(f"📄 PAPER 📋 Closing order placed: {t} — {reason}")
            return True
        finally:
            self.locked.discard(tid)

    async def full_exit(self, tid, reason):
        return await self._sale(tid, reason, "close")

    async def depth_open_sale(self, tid):
        return await self._sale(tid, REASON, "opg")

    def _stream_on_cancel(self, o):
        planned = {(a["detail"]["trade_id"], a["detail"]["stop_order_id"]) for a in self.audit
                   if a["event_type"] == "planned_sale_stop_cancel"}
        for tid, r in self.trades.items():
            if (tid, o["id"]) in planned and self.stream_silent:
                self._audit("stop_cancel_by_planned_sale_silent",
                            {"trade_id": tid, "cancelled_order_id": o["id"]})
            if o.get("order_class") == "oco" and any(
                    x["trade_id"] == tid and x["alpaca_order_id"] == o["id"]
                    for x in self.live_orders):
                n = self._new(o["symbol"], o["qty"], "sell", "stop", "gtc", status="new",
                              stop=r["stop_price"])
                r["stop_order_id"] = n["id"]

    async def _depth_job_1901(self):
        if not self.prod_depth_job:
            return
        for tid, r in list(self.trades.items()):
            if r["exit_rule"] == "depth" and r["depth_sell_pending_on"] is not None:
                await self.depth_open_sale(tid)

    async def _open_auction(self):
        for o in list(self.orders.values()):
            if o["side"] == "sell" and o["type"] == "market" and o["status"] in QUEUED_OK:
                self._fill(o)
                for x in self.live_orders:
                    if x["alpaca_order_id"] == o["id"]:
                        r = self.trades[x["trade_id"]]
                        r["remaining_shares"] -= o["qty"]
                        r["status"] = "closed" if r["remaining_shares"] <= 0 else "filled"

    async def _refresh_0935(self):
        covered = [r["ticker"] for r in self.trades.values()
                   if r["status"] == "filled" and r["remaining_shares"] > 0]
        self._audit("stop_refresh_ran", {"placed_tickers": [], "covered_by_resting_exit": covered,
                                         "already_covered": [], "unprotected": []},
                    f"09:35: examined {len(covered)}, placed 0")

    # state
    async def save_state(self, state):
        self.state = json.loads(json.dumps(state, default=str))

    def load_state(self):
        return self.state

    def clear_state(self):
        self.state = None


# ── CLI ────────────────────────────────────────────────────────────────────────────────────────────

def _log_path(day: date, dry: bool) -> str:
    return os.path.join(HERE, f"rehearsal_{day.isoformat()}{'_dryrun' if dry else ''}.log")


async def run_dry(cmd: str, tickers, log_dir: str | None = None, **fake_kw) -> tuple[int, "FakeEnv", StepLog]:
    """Day A from 13:00 ET on a Monday, then Day B the next morning — all against FakeEnv."""
    day_a = date(2026, 10, 5)
    env = FakeEnv(start=datetime.combine(day_a, dtime(13, 0), tzinfo=_ET), **fake_kw)
    path = os.path.join(log_dir or HERE, f"rehearsal_{day_a.isoformat()}_dryrun.log")
    log = StepLog(path, env.now)
    reh = Rehearsal(env, log, tickers)
    rc = 0
    if cmd in ("day-a", "all"):
        rc = await reh.day_a()
    if cmd in ("day-b", "all"):
        env.clock = datetime.combine(day_a + timedelta(days=1), dtime(9, 0), tzinfo=_ET)
        rc = max(rc, await Rehearsal(env, log, tickers).day_b())
    return rc, env, log


async def run_real(cmd: str, tickers, send_pages: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
    _bootstrap_alpaca_credentials()
    env = RealEnv(send_pages=send_pages)
    if cmd in ("day-b", "status", "cleanup") and env.load_state() is None:
        st = await env.load_state_from_audit()
        if st:
            await env.save_state(st)
    log = StepLog(_log_path(env.et_today(), False), env.now)
    reh = Rehearsal(env, log, tickers)
    if cmd == "day-a":
        return await reh.day_a()
    if cmd == "day-b":
        return await reh.day_b()
    if cmd == "status":
        return await reh.status()
    return await reh.cleanup()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["day-a", "day-b", "status", "cleanup"])
    ap.add_argument("--dry-run", action="store_true", help="fakes only — no broker, no DB")
    ap.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                    help="P1,P2,PROBE (default %(default)s)")
    ap.add_argument("--capture-pages", action="store_true",
                    help="log the pages this process would send instead of sending them")
    a = ap.parse_args(argv)
    tickers = tuple(x.strip().upper() for x in a.tickers.split(","))
    if len(tickers) != 3 or len(set(tickers)) != 3:
        print("--tickers needs three different symbols: P1,P2,PROBE")
        return 2
    try:
        if a.dry_run:
            cmd = "all" if a.cmd in ("day-a", "day-b") else a.cmd
            if cmd not in ("all",):
                print("--dry-run runs day-a then day-b against fakes")
                return 2
            rc, _, _ = asyncio.run(run_dry(cmd, tickers))
            return rc
        return asyncio.run(run_real(a.cmd, tickers, send_pages=not a.capture_pages))
    except RehearsalRefused as e:
        print(f"REFUSED: {e}")
        return 2
    except LiveTouched as e:
        print(f"ABORTED — LIVE TOUCHED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
