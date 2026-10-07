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

THE STEPS (spec times, ET):
  R1  09:35:30  INFORMATIONAL — never a FAIL, never in Day A's tally, never decides Day A's cleanup,
      never a Day B dependency (operator "Ok", 2026-10-06). The 10-06 B1→B2 TIMING on a DEDICATED
      ticker (default CL, `--r1-ticker`; checked like the others at the start AND again right before
      R1 places — not held, no open orders, no trade rows — a ticker that fails is SKIPPED as INFO,
      the rest of Day A runs):
      4 sh at market, then at once — NO wait for routing — the 3-sh GTC stop, the extra 1-sh resting
      sell and the row (exactly as B1), and execute_full_exit. On 10-06 that shape had the broker
      confirm the stop's cancel 7 s after the request, so the sale AND the restore's first attempt
      were refused held_for_orders — the condition the stop-restore retry exists for, which B2's
      routed spacing will most likely never produce. Records which path ran (`stop_restore_retried`
      → "retry PROVEN live"; a first attempt that worked → "retry NOT exercised";
      `stop_restore_retry_ended` + its outcome), any STOP NOT RESTORED page, any
      `stop_ack_timeout_remediated` row, and the times of the cancel request, the broker's cancel
      confirmation and the restore. R1f then leaves the ticker FLAT before A1 (under the trade lock,
      so the stop-ACK watchdog cannot re-protect the row mid-flatten): cancel the restored stop and
      the extra sell, sell every share at market, wait until the broker shows no position and no
      open order, delete the row as cleanup does. A flatten that fails is INFO too; `cleanup` covers
      R1's ticker and order ids (kept in the state) and reports them as INFO `R1c`. The R1 row is
      one more open paper row for ~1-2 minutes inside the ORB window.
  A1  10:00  P1 = 3 sh of TICKER_P1, GTC stop 5% below the fill → assert every share reserved.
  A2  10:05  execute_partial_exit(limit far above) → OCO third resting, 2/3 stop live, all reserved.
  A3  10:10  price-only replace of the 2/3 stop +1% → new id, still covering.
  B1  10:15  P2 = 4 sh of TICKER_P2: a 3-sh GTC stop for the row + one EXTRA 1-sh resting sell that
      the books do not know about (so it is not a pending exit) → execute_full_exit → assert
      rejected, stop restored at the same price, page sent. Two paths (#687 2026-10-06): the
      restore's FIRST attempt works → <= 5 s after the rejection (the retry is then NOT exercised
      live — unit-tested only); it is refused while the broker still holds the cancelled stop's
      shares and the RETRY places it → <= RETRY_BAR_S after that first refusal + a
      `stop_restore_retried` row (the retry PROVEN live). B2's detail names the path. B2b: the
      stream did not page "unprotected" — its silent row, or its replacement branch's
      `cancel_or_reject_restored` / `stop_pointer_repair_deferred` naming the restored stop. The
      extra sell is then cancelled and the extra share sold, so P2 = 3 sh under its restored stop.
  A4  15:51 a market-on-close BUY of 1 sh on the flat PROBE ticker — INFORMATIONAL, never a FAIL:
      paper ACCEPTED it on 2026-10-06, and production never sends a market-on-close order, so the
      step only records what paper's cutoff did (accepted → cancelled at once, or rejected).
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

SPACING (#687 2026-10-06 — A2 fired 2 s after A1 while A1's stop was still `pending_new`, and the
production partial exit, reading that stop as not live, aborted). A1/A2/A3/B1 run no earlier than
their SPEC times 10:00/10:05/10:10/10:15 ET (B1 has no spec time; 10:15 follows A3) — clear of the
09:31-09:45 ORB window and the 09:35 stop refresh — AND every order a step places is waited on
until the broker shows it live (`new` for a stop or a resting sell, `filled` for a market buy;
never `pending_new`) and the position's held count has settled, before the next step runs. Started
after 10:15, the steps run back to back, still gated on those reads. R1 alone is NOT spaced — its
whole point is the unrouted stop — and it runs (and flattens) before A1 whatever the start time.

END OF DAY A (#687 2026-10-06 — a FAIL in a step Day B does not need wiped Day B's positions):
Day B tests what Day A QUEUED. It depends on DAY_B_DEPENDS_ON — P1: A1, A2, A6 (its 16:45 sale);
P2: B1, A8, A9 (its opening-auction sale; A8 re-reads P2's readiness at 18:50 itself, so B2's
restore timing or B3's 09:36 snapshot no longer decide it). Day A cleans up automatically ONLY when
every position has a failed dependency — Day B would have nothing to test. Otherwise the state is
left for Day B, whose own cleanup flattens everything in market hours; Day B skips the checks of a
position whose sale was never queued.

STATUSES: PASS · FAIL · SKIP (by design) · INFO (recorded, never counted as a failure — A4, R1/R1f/R1c).
EXIT CODES: 0 every step PASS/SKIP/INFO · 1 a FAIL · 2 refused / could not run.
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
DEFAULT_R1_TICKER = "CL"                   # R1's own liquid large-cap — no other step uses it
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
# A resting stop / limit sell the broker has actually ROUTED. `LIVE_STATUSES` above also holds
# `pending_new` — waiting on it returned at once on 10-06 and A2 fired against a pending stop.
STOP_LIVE = {"new"}
# A8 at 18:50 (after the close): a stop re-placed after 16:00 reads `accepted` (queued for the next
# session) or `held`, not `new` — both still protect P2 at the open. Only `pending_new` (not yet
# routed) caused the 10-06 problem, so it alone stays out (review 2026-10-06, NICE 6).
STOP_READY_1850 = {"new", "accepted", "held"}
SETTLE_BUDGET_S = 30.0                     # per wait for an order / the held count to settle
# B2's bar when the restore's first attempt is REFUSED and its held-shares retry places the stop:
# order_manager._RESTORE_RETRY_WINDOW_S (15 s, pinned by a test) from the first refused attempt,
# plus 2 s for the broker round trips at its ends (that refusal, the last poll's read).
RESTORE_RETRY_WINDOW_S = 15.0
RETRY_BAR_S = RESTORE_RETRY_WINDOW_S + 2.0
TERMINAL = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced", "done_for_day"}
# Rejection texts that mean "rejected for a reason OTHER than the time cutoff" — a cutoff probe that
# hits one of these proves nothing (a broken system would read the same).
WRONG_REASON = re.compile(
    r"insufficient|held_for_orders|wash|buying power|not tradable|not shortable|fractional|"
    r"qty|quantity|asset .* not found|account .* blocked", re.I)

# Fixed ET times (spec §8, plus the 19:01 opening-auction job the CHECKED section makes the vehicle).
T_A1 = dtime(10, 0)
T_A2 = dtime(10, 5)
T_A3 = dtime(10, 10)
T_B1 = dtime(10, 15)                       # no spec time — after A3 and its 20 s observation
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
# R1 (informational): 10-06's B2 ran at 09:35:43; 09:35:30 is after the 09:35:00 stop refresh.
T_R1 = dtime(9, 35, 30)
R1_STREAM_WAIT_S = 10.0       # for the stream's row on the cancel (its confirmation, as seen here)
R1_WATCHDOG_WAIT_S = 60.0     # a restore that did not land: the stop-ACK watchdog (fill + 30 s, 30 s tick)
R1_FLAT_BUDGET_S = 30.0       # for the shares to free / the broker to show the ticker flat
# The stream's own rows on a stop cancel (`stop_order_id_changed` only with a cancel_or_reject_* reason).
R1_STREAM_EVENTS = ("stop_cancel_by_planned_sale_silent", "stop_pointer_repair_deferred",
                    "stop_order_id_changed", "dead_stop_price_preserved")

# Day B tests what Day A QUEUED for it — these are the Day-A steps it DEPENDS on, per position.
# A FAIL anywhere else (B2's restore timing, B2b, B3's 09:36 snapshot, A3, the A4/A7 cutoff probes,
# A5, A6a/b/d/e/f, A9b) never wipes the positions Day B needs (#687 2026-10-06).
DAY_B_DEPENDS_ON = {
    "p1": ("A1", "A2", "A6"),    # P1 under its stop · its OCO third resting · its 16:45 sale sent
    "p2": ("B1", "A8", "A9"),    # P2 under its stop · marked at 18:50 (ready) · its opg sale queued
}


class RehearsalRefused(RuntimeError):
    """A safety guard said no. Nothing was placed."""


class LiveTouched(RuntimeError):
    """Something in this process tried to reach a non-paper account."""


def canon(status) -> str:
    return str(status or "").split(".")[-1].lower()


def _num(v):
    return float(v) if v is not None else None


def _ts(x) -> datetime | None:
    """A timestamp (datetime or ISO string) as an aware datetime, or None."""
    if x is None or x == "":
        return None
    if isinstance(x, str):
        try:
            x = datetime.fromisoformat(x)
        except ValueError:
            return None
    if not isinstance(x, datetime):
        return None
    return x if x.tzinfo is not None else x.replace(tzinfo=_ET)


def _hms(x) -> str:
    """HH:MM:SS.d ET for a log line ('?' when unknown)."""
    t = _ts(x)
    if t is None:
        return "?"
    t = t.astimezone(_ET)
    return t.strftime("%H:%M:%S") + f".{t.microsecond // 100000}"


def _gap(a, b) -> str:
    """' (+N.N s)' from a to b, or '' when either is unknown."""
    ta, tb = _ts(a), _ts(b)
    return f" ({(tb - ta).total_seconds():+.1f} s)" if ta and tb else ""


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
        self.results.append({"step": sid, "title": title, "status": st, "detail": detail,
                             "at": self.now()})
        self._write(f"[{sid}] {st} — {title}" + (f" | {detail}" if detail else ""))
        return st == "PASS"

    def failed(self) -> list[dict]:
        return [r for r in self.results if r["status"] == "FAIL"]

    def status_of(self, sid: str) -> str | None:
        """The LAST recorded status of a step id (None = it never recorded one)."""
        hits = [r["status"] for r in self.results if r["step"] == sid]
        return hits[-1] if hits else None


# ── The rehearsal (env-agnostic) ───────────────────────────────────────────────────────────────────

class Rehearsal:
    def __init__(self, env, log: StepLog, tickers=DEFAULT_TICKERS, r1_ticker=DEFAULT_R1_TICKER):
        self.env = env
        self.log = log
        self.t1, self.t2, self.probe = tickers
        self.r1_ticker = (r1_ticker or "").strip().upper() or None
        self.r1_skip: str | None = None        # set by Day A's preflight: why R1 will not run
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

    async def _settle(self, ticker: str, qty: float, free: float,
                      budget_s: float = SETTLE_BUDGET_S):
        """SPACING: wait until the broker shows `qty` shares held with `free` of them unreserved —
        the held count has settled — before the next step. Returns the last position read."""
        pos = None
        for _ in range(int(budget_s / 0.5) + 1):
            pos = await self.env.position(ticker)
            if (pos and abs(float(pos.get("qty") or 0) - qty) < 1e-9
                    and abs(float(pos.get("qty_available") or 0) - free) < 1e-9):
                return pos
            await self.env.sleep(0.5)
        return pos

    async def _not_before(self, day: date, t: dtime, label: str) -> None:
        """SPACING: a Day A step runs no earlier than its spec time."""
        when = self._at(day, t)
        if self.env.now() < when:
            self.log.note(f"{label}: waiting for {t.strftime('%H:%M')} ET (spec time)")
            await self.env.sleep_until(when)

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
        self.r1_skip = await self._r1_ticker_check()
        self.log.note(f"R1 TICKER OK: {self.r1_ticker} — not held, no open orders, no trade rows "
                      f"in the paper account" if not self.r1_skip else
                      f"R1 will be SKIPPED (informational step): {self.r1_skip}")

    async def _r1_ticker_check(self) -> str | None:
        """R1's start-of-day checks on its OWN ticker — the same three as the others, but a ticker
        that fails them only skips R1 (INFO); it never refuses Day A. None = R1 may run."""
        t = self.r1_ticker
        if not t:
            return "no R1 ticker (--r1-ticker '')"
        if t in (self.t1, self.t2, self.probe):
            return f"{t} is also P1/P2/the probe — R1 needs a ticker no other step uses"
        try:
            pos = await self.env.position(t)
            orders = await self.env.open_orders(t)
            foreign = await self.env.foreign_open_rows(t)
            ours = await self.env.sentinel_rows(t)
        except LiveTouched:
            raise
        except Exception as e:
            return f"{t} could not be checked ({type(e).__name__}: {str(e)[:160]})"
        if pos and abs(float(pos.get("qty") or 0)) > 0:
            return f"the paper account already holds {t} ({pos.get('qty')} sh)"
        if orders:
            return f"the paper account has {len(orders)} open order(s) in {t}"
        if foreign:
            return f"{foreign} open paper trade row(s) exist for {t}"
        if ours:
            return f"rehearsal rows for {t} are left from an earlier run (ids {ours}) — run `cleanup`"
        return None

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
                      "started_at": env.now().isoformat(), "order_ids": [], "p1": {}, "p2": {},
                      "r1": {}}
        await env.write_audit(START_EVENT, f"#687 paper rehearsal Day A started ({self.t1}, "
                              f"{self.t2}, probe {self.probe})", {"state": self.state})
        env.install_page_router()
        log.note("A1/A2/A3/B1 run no earlier than 10:00/10:05/10:10/10:15 ET (spec times; B1 has none) "
                 "and each waits for the previous step's orders to show live at the broker (never "
                 "pending_new) and its held shares to settle")

        await self._r1_race(today)              # INFORMATIONAL — before A1, its ticker left flat
        await self._a1_a3(today)
        await self._b1_b2(today)
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
        broken = self._day_b_broken_chains()
        intact = [n for n in DAY_B_DEPENDS_ON if n not in broken]
        why = "; ".join(f"{n.upper()}: {w}" for n, w in broken.items()) or "none"
        if intact:
            log.note(f"Day B has {[n.upper() for n in intact]} to test — state LEFT for Day B (its "
                     f"cleanup flattens everything); positions Day B cannot test: {why}")
        else:
            log.note(f"Day B has nothing to test — a step it depends on failed ({why}) — "
                     f"cleaning up now")
            await self.cleanup()
        return self._summary("Day A")

    def _day_b_broken_chains(self) -> dict[str, str]:
        """{position: why} for each position whose Day-B dependencies (DAY_B_DEPENDS_ON) did not
        all PASS, or whose sale was never queued. Empty = Day B can test both positions."""
        out = {}
        for name, deps in DAY_B_DEPENDS_ON.items():
            bad = [f"{s} {self.log.status_of(s) or 'never ran'}" for s in deps
                   if self.log.status_of(s) != "PASS"]
            if not bad and not (self.state.get(name) or {}).get("sale_id"):
                bad = ["no sale queued"]
            if bad:
                out[name] = ", ".join(bad)
        return out

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

    # ── R1 (INFORMATIONAL): the 10-06 timing, so the restore retry gets a real chance live ──
    async def _r1_race(self, today: date) -> None:
        """R1 + R1f — status INFO only, whatever happens: never a FAIL, never in Day A's tally, never
        a Day B dependency (not in DAY_B_DEPENDS_ON), never triggers or blocks Day A's cleanup.
        Only `LiveTouched` (the paper guard) escapes."""
        env, log, t = self.env, self.log, self.r1_ticker
        title = (f"R1 the stop-restore retry against the real broker — B1→B2 on {t} with NO "
                 f"routing waits (informational)")
        if self.r1_skip:
            log.step("R1", title, None, f"skipped — {self.r1_skip}; the rest of Day A proceeds",
                     status="INFO")
            return
        r1 = self.state.setdefault("r1", {})
        try:
            await self._not_before(today, T_R1, "R1")
            # Checked at launch (~09:24); a paper entry in the 09:31 ORB window could have taken
            # the ticker since — check again right before placing.
            again = await self._r1_ticker_check()
            if again:
                log.step("R1", title, None, f"skipped — at {_hms(env.now())} ET {again}; the "
                         f"rest of Day A proceeds", status="INFO")
                return
            r1.update(ticker=t, started_at=env.now().isoformat())
            await self._save()                  # from here `cleanup` covers R1's ticker
            detail = await self._r1_shape(t, r1)
        except LiveTouched:
            raise
        except Exception as e:
            detail = f"R1 raised {type(e).__name__}: {str(e)[:300]} — recorded, never judged"
        log.step("R1", title, None, detail, status="INFO")
        if not r1.get("ticker"):
            return                              # nothing was placed
        try:
            flat = await self._r1_flatten(t, r1)
        except LiveTouched:
            raise
        except Exception as e:
            flat = (f"flatten raised {type(e).__name__}: {str(e)[:200]} — `cleanup` covers {t} "
                    f"(its ticker and order ids are in the rehearsal state)")
        try:
            await self._save()
        except LiveTouched:
            raise
        except Exception as e:
            flat += f"; state save failed ({type(e).__name__})"
        log.step("R1f", f"R1: leave {t} flat before A1 (informational)", None, flat, status="INFO")

    async def _r1_shape(self, t: str, r1: dict) -> str:
        """B1 → B2 exactly, minus every wait for routing. Returns R1's INFO detail."""
        env = self.env

        def keep(key: str, oid: str) -> None:
            r1[key] = oid
            self.state["order_ids"].append(oid)

        buy = await env.submit(t, 4, "buy", kind="market", tif="day")
        keep("buy_id", buy["id"])
        if await self._wait_status(buy["id"], {"filled"}) != "filled":
            return (f"the 4-sh market buy {buy['id'][:8]} did not fill in 15 s — nothing to race "
                    f"(R1f flattens whatever filled)")
        bo = await env.get_order(buy["id"])
        fill = float(bo["filled_avg_price"])
        stop_px = round(fill * 0.95, 2)
        # 10-06's shape: from the fill to the exit NOTHING waits for the broker to route anything.
        t_stop = env.now()
        stop = await env.submit(t, 3, "sell", kind="stop", tif="gtc", stop=stop_px)
        keep("stop_id", stop["id"])
        extra = await env.submit(t, 1, "sell", kind="limit", tif="gtc", limit=round(fill * 1.5, 2))
        keep("extra_id", extra["id"])
        tid = await env.insert_trade(ticker=t, shares=3, entry=round(fill * 0.97, 2), stop=stop_px,
                                     stop_id=stop["id"], alert_date=env.et_today())
        r1.update(trade_id=tid, fill=fill, stop_price=stop_px)
        since, n_pages = env.now(), len(env.pages)
        async with env.exit_spy(tid) as spy:
            ok = await env.full_exit(tid, REASON)
        await self._save()

        cancels = [e for e in spy if e["name"] == "cancel_order"]
        close = [e for e in spy if e["name"] == "close_position"]
        place = [e for e in spy if e["name"] == "place_stop_order"]
        placed_ok = [e for e in place if e.get("ok")]
        for e in placed_ok:
            if e.get("order_id"):
                keep("restored_stop_id", e["order_id"])
        sale_refused = bool(close) and close[0].get("ok") is False
        retried = await self._audit_for_trade(["stop_restore_retried"], since, tid)
        ended = await self._audit_for_trade(["stop_restore_retry_ended"], since, tid)
        # A restore that did not land leaves the row with no stop: give the stop-ACK watchdog's
        # fallback (filled_at + 30 s, a 30 s tick) its chance to show before R1f flattens.
        wd = await self._audit_for_trade(
            ["stop_ack_timeout_remediated"], since, tid,
            budget_s=R1_WATCHDOG_WAIT_S if (sale_refused and not placed_ok) else 0.0)
        # The cancel's confirmation: the broker's own stamp, and when the stream saw it here.
        confirmed = None
        if cancels:
            await self._wait_status(stop["id"], TERMINAL, budget_s=R1_STREAM_WAIT_S)
            confirmed = await env.cancelled_at(stop["id"])
        stream: list = []
        for _ in range(int(R1_STREAM_WAIT_S) + 1):
            stream = [r for r in await self._audit_for_trade(list(R1_STREAM_EVENTS), since, tid)
                      if r["event_type"] != "stop_order_id_changed"
                      or str(r["detail"].get("reason") or "").startswith("cancel_or_reject")]
            if stream or not cancels:
                break
            await env.sleep(1.0)
        pages = [p["text"] for p in env.pages[n_pages:] if "FAILED" in p["text"]]
        not_restored = any("NOT RESTORED" in p for p in pages)
        page_line = (f" (its last line: {pages[-1].strip().splitlines()[-1][-120:]})" if pages
                     else " (no failure page)")
        trail = [f"{_hms(r.get('at'))} {r['event_type']}"
                 + (f"({r['detail'].get('reason')})" if r["detail"].get("reason") else "")
                 for r in await env.audit_rows(None, since) if r["detail"].get("trade_id") == tid]

        if not sale_refused:
            path = ("shape NOT reproduced — " + ("the sale went through" if close else
                                                 "no sale was sent") + f" (returned {ok})")
        elif retried:
            d = retried[-1]["detail"]
            path = (f"retry PROVEN live — the first restore attempt was refused while the broker "
                    f"still held the cancelled stop's shares and the retry placed the stop "
                    f"(stop_restore_retried: attempt {d.get('attempts')}, waited "
                    f"{d.get('slept_s')} s, {d.get('elapsed_s')} s wall clock)")
        elif ended:
            d = ended[-1]["detail"]
            path = (f"retry RAN but did not place the stop — stop_restore_retry_ended "
                    f"'{d.get('outcome')}' after {d.get('attempts')} attempt(s), "
                    f"{d.get('slept_s')} s waited")
        elif place and place[0].get("ok"):
            path = ("retry NOT exercised — the restore's FIRST attempt placed the stop (the cancel "
                    "had already released the shares)")
        elif placed_ok:
            path = "a later placement worked but there is NO stop_restore_retried row"
        elif place:
            path = "NOT restored — every placement refused and no retry row"
        else:
            path = "no restore placement was made (see the rows)"
        t_cancel = cancels[0].get("at") if cancels else None
        t_rest = placed_ok[-1].get("at") if placed_ok else None
        err = (close[0].get("error") or "")[:120] if close else ""
        return (f"{path}. Times (ET): stop sent {_hms(t_stop)} ({canon(stop.get('status'))}, "
                f"extra {canon(extra.get('status'))}); exit called {_hms(since)}; cancel requested "
                f"{_hms(t_cancel)}; broker confirmed the cancel {_hms(confirmed)}"
                f"{_gap(t_cancel, confirmed)}; stream saw it "
                f"{_hms(stream[0].get('at')) if stream else 'NO row'}; sale "
                f"{'refused' if sale_refused else 'sent'} {_hms(close[0].get('at') if close else None)}"
                f"{' (' + err + ')' if err else ''}; restore attempts {len(place)} "
                f"({len(place) - len(placed_ok)} refused), first {_hms(place[0].get('at') if place else None)}, "
                f"placed {_hms(t_rest)}{_gap(t_cancel, t_rest)} "
                f"{placed_ok[-1].get('order_id', '')[:8] if placed_ok else ''}. "
                f"STOP NOT RESTORED page: {'YES' if not_restored else 'no'}"
                f"{page_line}; "
                f"stop_ack_timeout_remediated: "
                f"{'YES at ' + _hms(wd[-1].get('at')) if wd else 'no'}; row #{tid} audit trail: "
                f"{trail[:14] or 'none'}")

    async def _r1_flatten(self, t: str, r1: dict) -> str:
        """R1f — leave R1's ticker FLAT: under the trade lock (the stop-ACK watchdog and the coverage
        repair try-lock and defer, so neither can re-protect the row between the stop's cancel and
        the sale), cancel every order of ours on it, sell every share at market once the broker
        frees them, wait until it shows no position and no open order, then delete the row."""
        tid = r1.get("trade_id")
        if tid:
            async with self.env.trade_lock(tid):
                return await self._r1_flatten_locked(t, r1, tid)
        return await self._r1_flatten_locked(t, r1, None)

    async def _r1_flatten_locked(self, t: str, r1: dict, tid) -> str:
        env = self.env
        known = {v for k, v in r1.items() if k.endswith("_id") and isinstance(v, str)}
        cancelled: list[str] = []
        foreign: list = []
        for _round in range(4):
            # The restore's FIRST attempt carries no rehearsal client id — it is found by the id the
            # spy saw (restored_stop_id) or the row's pointer (a watchdog fallback too).
            row = await env.trade(tid) if tid else None
            if row and row.get("stop_order_id"):
                known.add(row["stop_order_id"])
            if tid:
                known |= {r["alpaca_order_id"] for r in await env.order_rows(tid)
                          if r["alpaca_order_id"]}
            orders = await env.open_orders(t)
            mine = [o for o in orders if o["id"] in known or is_ours_coid(o.get("client_order_id"), t)]
            foreign = [o for o in orders if o not in mine]
            if not mine:
                break
            for o in mine:
                if tid and "stop" in str(o.get("type")):
                    await env.mark_planned_cancel(tid, t, o["id"])   # recorded, never paged
                await env.cancel(o["id"])
                cancelled.append(o["id"][:8])
            for o in mine:
                await self._wait_status(o["id"], TERMINAL)
        pos = await env.position(t)
        qty = float(pos["qty"]) if pos else 0.0
        foreign_rows = await env.foreign_open_rows(t)
        covers = f"`cleanup` covers {t} (its ticker and order ids are in the rehearsal state)"
        if qty < 0:
            return f"{t}: SHORT {qty:g} sh — not touched, cover by hand; {covers}"
        if qty and (foreign or foreign_rows):
            return (f"{t}: {qty:g} sh NOT flattened — {foreign_rows} non-rehearsal paper row(s) / "
                    f"{len(foreign)} foreign order(s) on it; {covers}")
        sold = "nothing to sell"
        if qty:
            # Load-bearing: a sale sent before the cancels settle is refused held_for_orders —
            # the very race R1 exists to provoke.
            await self._wait_avail(t, qty, budget_s=R1_FLAT_BUDGET_S)
            try:
                sell = await env.submit(t, qty, "sell", kind="market", tif="day")
            except LiveTouched:
                raise
            except Exception as e:
                return (f"{t}: the market sale of {qty:g} sh was REFUSED ({str(e)[:160]}); row "
                        f"#{tid} LEFT; {covers}")
            r1["flatten_id"] = sell["id"]
            self.state["order_ids"].append(sell["id"])
            st = await self._wait_status(sell["id"], {"filled"}, budget_s=20)
            sold = f"sold {qty:g} sh ({sell['id'][:8]} {st})"
        pos, orders, flat = None, [], False
        for _ in range(int(R1_FLAT_BUDGET_S / 0.5) + 1):
            pos = await env.position(t)
            orders = await env.open_orders(t)
            if not (pos and float(pos.get("qty") or 0)) and not orders:
                flat = True
                break
            await env.sleep(0.5)
        if not flat:
            return (f"{t} NOT flat after {R1_FLAT_BUDGET_S:.0f} s (position "
                    f"{pos and pos.get('qty')}, open orders "
                    f"{[(o['id'][:8], o.get('type'), o.get('qty')) for o in orders]}; cancelled "
                    f"{cancelled or 'nothing'}; {sold}) — row #{tid} LEFT; {covers}")
        deleted = await env.delete_trades([tid]) if tid else 0
        r1["flat"] = True
        return (f"{t} flat at {_hms(env.now())} ET: cancelled {cancelled or 'nothing'}; {sold}; the "
                f"broker shows no position and no open order; row #{tid} deleted ({deleted})")

    async def _a1_a3(self, today: date) -> None:
        env, log, p1 = self.env, self.log, self.state["p1"]
        t = self.t1
        try:
            await self._not_before(today, T_A1, "A1")
            buy = await env.submit(t, 3, "buy", kind="market", tif="day")
            self.state["order_ids"].append(buy["id"])
            if await self._wait_status(buy["id"], {"filled"}) != "filled":
                log.step("A1", f"buy 3 {t}", False, "the buy did not fill")
                return
            fill = float((await env.get_order(buy["id"]))["filled_avg_price"])
            stop_px, entry = round(fill * 0.95, 2), round(fill * 0.97, 2)
            stop = await env.submit(t, 3, "sell", kind="stop", tif="gtc", stop=stop_px)
            self.state["order_ids"].append(stop["id"])
            # SPACING: the stop must be ROUTED (`new`), not `pending_new` — on 10-06 A2 fired 2 s
            # after this while the stop was pending_new and the production partial exit aborted.
            st = await self._wait_status(stop["id"], STOP_LIVE, budget_s=SETTLE_BUDGET_S)
            if st not in STOP_LIVE:
                log.step("A1", f"GTC stop 5% below on {t}", False,
                         f"the stop never went live (status {st or 'unreadable'} after "
                         f"{SETTLE_BUDGET_S:.0f} s)")
                return
            tid = await env.insert_trade(ticker=t, shares=3, entry=entry, stop=stop_px,
                                         stop_id=stop["id"], alert_date=env.et_today())
            p1.update(trade_id=tid, fill=fill, stop_price=stop_px, entry=entry)
            await self._save()
            row = await env.trade(tid)
            pos = await self._settle(t, 3, 0.0)
            ok = (row["account_mode"] == ACCOUNT_MODE and row["signal_type"] == TAG_SIGNAL_TYPE
                  and row.get("partial_taken") is True
                  and pos and float(pos["qty"]) == 3 and float(pos["qty_available"]) == 0)
            log.step("A1", f"buy 3 {t} + GTC stop 5% below; every share reserved", ok,
                     f"fill ${fill:.2f}, stop ${stop_px} ({stop['id'][:8]}, {st}), row #{tid} entry "
                     f"${entry} (set 3% under the fill so the breakeven step stays below market), "
                     f"partial_taken {row.get('partial_taken')} (TRUE keeps production's +2R "
                     f"profit trigger off it), position {pos and pos['qty']} / free {pos and pos['qty_available']}")
            if not ok:
                return

            await self._not_before(today, T_A2, "A2")
            limit = round(fill * 1.5, 2)
            ok = await env.partial_exit(tid, 1, limit)
            rows = await env.order_rows(tid)
            oco = [r for r in rows if r["purpose"] == "partial_exit"]
            oco_id = oco[-1]["alpaca_order_id"] if oco else None
            row = await env.trade(tid)
            # SPACING: the OCO third and the 2/3 stop are each read once the broker shows it live.
            if oco_id:
                await self._wait_status(oco_id, STOP_LIVE, budget_s=SETTLE_BUDGET_S)
            if row["stop_order_id"]:
                await self._wait_status(row["stop_order_id"], STOP_LIVE, budget_s=SETTLE_BUDGET_S)
            stop2 = await env.get_order(row["stop_order_id"]) if row["stop_order_id"] else None
            oco_o = await env.get_order(oco_id) if oco_id else None
            pos = await self._settle(t, 3, 0.0)
            good = bool(ok and oco_o and stop2
                        and canon(oco_o["status"]) in STOP_LIVE and float(oco_o["qty"]) == 1
                        and abs(float(oco_o.get("limit_price") or 0) - limit) < 0.011
                        and canon(stop2["status"]) in STOP_LIVE and float(stop2["qty"]) == 2
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

            await self._not_before(today, T_A3, "A3")
            old_id = row["stop_order_id"]
            new_px = round(float(stop2["stop_price"]) * 1.01, 2)   # the LIVE broker stop, +1%
            new = await env.replace_stop_price(tid, old_id, new_px)
            st = await self._wait_status(new["id"], STOP_LIVE, budget_s=SETTLE_BUDGET_S)
            row = await env.trade(tid)
            n = await env.get_order(new["id"])
            pos = await self._settle(t, 3, 0.0)
            good = (new["id"] != old_id and st in STOP_LIVE and float(n["qty"]) == 2
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

    async def _b1_b2(self, today: date) -> None:
        env, log, p2 = self.env, self.log, self.state["p2"]
        t = self.t2
        try:
            await self._not_before(today, T_B1, "B1")
            buy = await env.submit(t, 4, "buy", kind="market", tif="day")
            self.state["order_ids"].append(buy["id"])
            if await self._wait_status(buy["id"], {"filled"}) != "filled":
                log.step("B1", f"buy 4 {t}", False, "the buy did not fill")
                return
            fill = float((await env.get_order(buy["id"]))["filled_avg_price"])
            stop_px = round(fill * 0.95, 2)
            stop = await env.submit(t, 3, "sell", kind="stop", tif="gtc", stop=stop_px)
            self.state["order_ids"].append(stop["id"])
            st_stop = await self._wait_status(stop["id"], STOP_LIVE, budget_s=SETTLE_BUDGET_S)
            extra = await env.submit(t, 1, "sell", kind="limit", tif="gtc", limit=round(fill * 1.5, 2))
            self.state["order_ids"].append(extra["id"])
            st_extra = await self._wait_status(extra["id"], STOP_LIVE, budget_s=SETTLE_BUDGET_S)
            tid = await env.insert_trade(ticker=t, shares=3, entry=round(fill * 0.97, 2),
                                         stop=stop_px, stop_id=stop["id"],
                                         alert_date=env.et_today())
            p2.update(trade_id=tid, fill=fill, stop_price=stop_px, extra_id=extra["id"])
            await self._save()
            pos = await self._settle(t, 4, 0.0)
            row = await env.trade(tid)
            ok = bool(pos and float(pos["qty"]) == 4 and float(pos["qty_available"]) == 0
                      and st_stop in STOP_LIVE and st_extra in STOP_LIVE
                      and row and row.get("partial_taken") is True)
            log.step("B1", f"P2: 4 {t}, row of 3 under a 3-sh stop + one extra 1-sh resting sell "
                     f"the books do not know (holds a share, not a pending exit)", ok,
                     f"fill ${fill:.2f}, stop ${stop_px} ({stop['id'][:8]}, {st_stop}), extra "
                     f"{extra['id'][:8]} ({st_extra}), row #{tid} partial_taken "
                     f"{row and row.get('partial_taken')}, position {pos and pos['qty']} / free {pos and pos['qty_available']}")
            if not ok:
                return

            since = env.now()
            async with env.exit_spy(tid) as spy:
                ok = await env.full_exit(tid, REASON)
            close = [e for e in spy if e["name"] == "close_position"]
            place = [e for e in spy if e["name"] == "place_stop_order"]
            # The restore may RETRY while the broker releases the cancelled stop's shares (#687
            # 2026-10-06). Two paths, two bars (review 2026-10-06, MUST-FIX 2): the FIRST attempt
            # worked → the spec's <= 5 s from the rejected sale; it was refused and a retry worked →
            # <= RETRY_BAR_S from that first refused placement, AND the retry's own row. Thursday's
            # spacing likely settles the cancel before the sale, so the first attempt works and the
            # retry is NOT exercised live — the detail says which path ran.
            placed_ok = [e for e in place if e.get("ok")]
            rej = await self._audit_for_trade(["full_exit_rejected"], since, tid)
            retried = await self._audit_for_trade(["stop_restore_retried"], since, tid)
            row = await env.trade(tid)
            pointer = row["stop_order_id"]
            # The restored stop is read by the id the placement RETURNED, not through the row's
            # pointer: the stream's cancel handler nulls the pointer unconditionally, and a restore
            # that lands as the cancel settles can be nulled AFTER its own write (the race named in
            # exit_discipline.md 2026-10-06; the same handler's #646 (e) fill writes it back once
            # its broker check confirms the stop). That is reported beside B2, never mistaken for a
            # restore that failed.
            restored_id = (placed_ok[-1].get("order_id") if placed_ok else None) or pointer
            restored = await env.get_order(restored_id) if restored_id else None
            st = (await self._wait_status(restored_id, STOP_LIVE, budget_s=SETTLE_BUDGET_S)
                  if restored else "")
            if restored:
                restored = await env.get_order(restored_id)
            pointer_note = (
                "row points at it" if restored_id and pointer == restored_id else
                "row pointer NULL — the stream's cancel handler nulled it after the restore wrote "
                "it (the named race); the same handler's #646 (e) fill writes it back once its "
                "broker check confirms the stop (the stop-ACK watchdog, 09-15 ET, is the backstop)"
                if pointer is None else f"row points at {pointer[:8]}")
            dt = (placed_ok[-1]["t"] - close[0]["t"]) if (close and placed_ok) else None
            first_try = bool(place and place[0].get("ok"))
            dt_retry = (placed_ok[-1]["t"] - place[0]["t"]) if (placed_ok and not first_try) \
                else None
            if first_try:
                path = ("FIRST ATTEMPT — the shares were free; the held-shares retry was NOT "
                        "exercised live (unit-tested only)")
                in_time = dt is not None and dt <= 5.0
            elif placed_ok:
                path = (f"RETRY — {len(place) - len(placed_ok)} refused, then placed "
                        f"{'%.2f s' % dt_retry} after the first refused attempt"
                        + (f" (stop_restore_retried: attempts {retried[-1]['detail'].get('attempts')}, "
                           f"waited {retried[-1]['detail'].get('slept_s')} s) — retry PROVEN live"
                           if retried else " — but NO stop_restore_retried row"))
                in_time = bool(retried) and dt_retry is not None and dt_retry <= RETRY_BAR_S
            else:
                path = "NOT RESTORED — no placement worked"
                in_time = False
            page = [p for p in env.pages if "FAILED" in p["text"] and t in p["text"]]
            says_restored = bool(page and "Stop RESTORED" in page[-1]["text"]
                                 and "NOT RESTORED" not in page[-1]["text"])
            good = bool(ok is False and close and close[0]["ok"] is False and rej and restored
                        and restored_id != stop["id"] and st in STOP_LIVE
                        and abs(float(restored["stop_price"]) - stop_px) < 0.011
                        and float(restored["qty"]) == 3 and in_time and says_restored)
            p2.update(restored_stop_id=restored_id)
            await self._save()
            log.step("B2", "extra sell holds a share → execute_full_exit rejected → stop restored at "
                     f"the same price (first attempt <= 5 s after the rejection, or the held-shares "
                     f"retry <= {RETRY_BAR_S:g} s after its first refusal) → page", good,
                     f"path: {path}; returned {ok}; sell error: "
                     f"{close and (close[0].get('error') or '')[:160]}; "
                     f"full_exit_rejected rows {len(rej)}; restore placements {len(place)} "
                     f"({len(place) - len(placed_ok)} refused), stop_restore_retried rows "
                     f"{len(retried)}; restored "
                     f"{restored and (restored['id'][:8], st, restored['qty'], restored.get('stop_price'))} "
                     f"{'%.2f s' % dt if dt is not None else '(no successful restore)'} after the "
                     f"rejection ({pointer_note if restored else 'row pointer ' + str(pointer and pointer[:8])}); "
                     f"page: {page[-1]['text'][:140] if page else 'NONE'}")
            await self._b2b_stream_verdict(tid, stop["id"], restored_id if restored else None, since)

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
            pos = await self._settle(t, 3, 0.0)
            ok = bool(filled == "filled" and pos and float(pos["qty"]) == 3
                      and float(pos["qty_available"]) == 0)
            p2["ready"] = ok          # B3's own verdict; A8 re-reads readiness itself at 18:50
            await self._save()
            log.step("B3", f"extra sell cancelled + extra share sold → P2 = 3 {t} under the restored "
                     f"stop", ok, f"position {pos and pos['qty']} / free {pos and pos['qty_available']}")
        except LiveTouched:
            raise
        except Exception as e:
            log.step("B1-B3", "P2 raised", False, f"{type(e).__name__}: {e}")

    async def _b2b_stream_verdict(self, tid, cancelled_id: str, restored_id, since) -> None:
        """B2b — what the paper stream did with the stop B2's sale cancelled. It must NOT page
        'unprotected'; three rows each prove it did not (review 2026-10-06, MUST-FIX 1):
          * `stop_cancel_by_planned_sale_silent` — no replacement seen, our planned sale's cancel
            recorded (the 10-06 shape, where the restore failed);
          * `stop_order_id_changed` reason `cancel_or_reject_restored` naming the RESTORED stop —
            its broker check found the restored stop and its #646 (e) fill re-pointed the row;
          * `stop_pointer_repair_deferred` naming the restored stop — it found it, and the
            restore's own pointer write stood (the likeliest shape for a restore that works).
        FAIL only when none appears in 30 s (it paged, or the paper stream is not running).
        SKIP when the restore re-pointed the row before the stream saw the cancel: its lookup by
        the cancelled id matched nothing, so it could neither record nor page."""
        env, log = self.env, self.log
        label = "the stream handled the planned-sale cancel without paging 'unprotected'"
        silent = repaired = deferred = []
        rows: list = []
        for _ in range(31):
            rows = await self._audit_for_trade(
                ["stop_cancel_by_planned_sale_silent", "stop_order_id_changed",
                 "stop_pointer_repair_deferred"], since, tid)
            silent = [r for r in rows if r["event_type"] == "stop_cancel_by_planned_sale_silent"
                      and r["detail"].get("cancelled_order_id") == cancelled_id]
            repaired = [r for r in rows if r["event_type"] == "stop_order_id_changed"
                        and r["detail"].get("reason") == "cancel_or_reject_restored"
                        and restored_id and r["detail"].get("new_id") == restored_id]
            deferred = [r for r in rows if r["event_type"] == "stop_pointer_repair_deferred"
                        and r["detail"].get("cancelled_order_id") == cancelled_id
                        and restored_id
                        and r["detail"].get("confirmed_replacement_id") == restored_id]
            if silent or repaired or deferred:
                break
            await env.sleep(1.0)
        ptr = [r for r in rows if r["event_type"] == "stop_order_id_changed"]
        nulled = [r for r in ptr if r["detail"].get("reason") == "cancel_or_reject_null"]
        repointed = [r for r in ptr
                     if r["detail"].get("reason") == "restored_after_failed_full_exit"]
        if repaired or deferred:
            how = ("its broker check found the restored stop and re-pointed the row "
                   "(cancel_or_reject_restored)" if repaired else
                   "its broker check found the restored stop; the restore's own pointer stood "
                   "(stop_pointer_repair_deferred)")
            log.step("B2b", label, True, f"REPLACEMENT path — {how}; the 'Stop replaced' notice, "
                     f"not 'unprotected'")
        elif silent:
            log.step("B2b", label, True, "SILENT path — no replacement seen; "
                     "stop_cancel_by_planned_sale_silent recorded the planned sale's cancel")
        elif repointed and not nulled:
            log.step("B2b", label, None,
                     "skipped — the restore re-pointed the row before the stream saw the cancel "
                     "(no cancel_or_reject_null row): the stream could not match the trade, so "
                     "it neither recorded nor paged", status="SKIP")
        else:
            log.step("B2b", label, False,
                     f"NONE of the three rows in 30 s (cancel_or_reject_null rows {len(nulled)}) — "
                     f"the paper stream paged 'unprotected', or it is not running for paper")

    async def _cutoff_probe(self, sid: str, tif: str, valid_from: dtime, valid_to: dtime,
                            label: str, *, informational: bool = False) -> None:
        """Send a 1-sh BUY on the flat probe ticker inside the window where only the time cutoff
        can reject it. `informational` (A4): record what happened as INFO — never a PASS or FAIL."""
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
            detail = ("rejected for another reason (proves nothing): " if wrong else
                      "rejected: ") + text[:300]
            if informational:
                self.log.step(sid, label, None, f"at {now_t:%H:%M:%S} {detail}", status="INFO")
            else:
                self.log.step(sid, label, not wrong, detail)
            return
        self.state["order_ids"].append(o["id"])
        cancelled = await self.env.cancel(o["id"])
        if informational:
            self.log.step(sid, label, None,
                          f"ACCEPTED at {now_t:%H:%M:%S} ({o['id'][:8]}; cancel "
                          f"{'sent' if cancelled else 'REFUSED — cleanup takes it'}) — paper "
                          f"takes this order after the documented 15:50 cutoff; production never "
                          f"sends a market-on-close order, so this is recorded, not judged",
                          status="INFO")
            return
        self.log.step(sid, label, False, f"ACCEPTED ({o['id'][:8]}, cancelled at once) — the "
                      f"cutoff is not where the design assumes")

    async def _a4_cls_probe(self) -> None:
        # INFORMATIONAL since 2026-10-06: paper ACCEPTED this 15:51 market-on-close BUY that day;
        # production never sends a market-on-close order (the ruled vehicles are the 16:45 market
        # sell and the 19:01 opening-auction sell), so paper's cutoff is recorded, never a FAIL.
        await self._cutoff_probe("A4", "cls", dtime(15, 50), dtime(16, 0),
                                 f"15:51 market-on-close BUY 1 {self.probe} — paper's cutoff "
                                 f"(informational)", informational=True)

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

    async def _p2_ready(self) -> tuple[bool, str]:
        """Is P2 what the opening-auction sale needs, read NOW from the row and the broker: the row
        open at 3 sh, the broker holding 3 sh, the row's stop live for 3 sh, nothing else resting.
        (#687 2026-10-06: B3's 09:36 snapshot no longer decides this — a restore that was late but
        landed, or the watchdog's fallback, leaves P2 ready by evening.)"""
        p2 = self.state["p2"]
        row = await self.env.trade(p2["trade_id"])
        pos = await self.env.position(self.t2)
        sid = row and row.get("stop_order_id")
        so = await self.env.get_order(sid) if sid else None
        others = [o for o in await self.env.open_orders(self.t2) if o["id"] != sid]
        ok = bool(row and row["status"] == "filled" and float(row["remaining_shares"]) == 3
                  and pos and float(pos["qty"]) == 3
                  and so and canon(so["status"]) in STOP_READY_1850 and float(so["qty"]) == 3
                  and "stop" in str(so.get("type")) and not others)
        return ok, (f"row {row and (row['status'], row['remaining_shares'])}, position "
                    f"{pos and pos['qty']}, row stop {sid and sid[:8]} "
                    f"{so and (canon(so['status']), so['qty'])}, other open orders "
                    f"{[(o['id'][:8], o['type'], o['qty']) for o in others]}; B3 said "
                    f"{'ready' if p2.get('ready') else 'not ready'}")

    async def _a8_mark_depth(self) -> None:
        p2 = self.state["p2"]
        if not p2.get("trade_id"):
            self.log.step("A8", "stamp P2 for the opening-auction sale", None,
                          "skipped — P2 was never set up (B1)", status="SKIP")
            return
        ready, detail = await self._p2_ready()
        if not ready:
            self.log.step("A8", "P2 ready for the opening-auction sale (3 sh under a live 3-sh "
                          "stop, nothing else resting)", False, detail)
            return
        # The stop the 19:01 sale must cancel is the row's stop AT MARKING TIME — not B2's restored
        # id, which anything replacing the stop between B3 and 19:01 would make stale.
        p2["stop_at_mark"] = (await self.env.trade(p2["trade_id"]))["stop_order_id"]
        await self.env.set_trade_cols(p2["trade_id"], {"exit_rule": "depth",
                                                       "depth_sell_pending_on": self.env.et_today()})
        p2["marked_at"] = self.env.now().isoformat()
        await self._save()
        self.log.step("A8", f"P2 #{p2['trade_id']} ready and stamped exit_rule='depth', marked to sell "
                      f"at the next open (the 16:45 decision skips a same-day row; unit-tested)",
                      True, detail)

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
        # Rows: P2 closes; P1 stays open at the OCO third. Only a position whose sale Day A QUEUED
        # is checked — Day A now leaves a position without one for Day B's cleanup (#687 2026-10-06).
        p1, p2 = self.state["p1"], self.state["p2"]
        for label, p in (("D3", p2), ("D3b", p1)):
            if p.get("trade_id") and not p.get("sale_id"):
                log.step(label, f"{'P2' if p is p2 else 'P1'} row after the fill", None,
                         "skipped — Day A queued no sale for it", status="SKIP")
        r1 = r2 = None
        for _ in range(30):
            r1 = await env.trade(p1["trade_id"]) if p1.get("sale_id") else None
            r2 = await env.trade(p2["trade_id"]) if p2.get("sale_id") else None
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
        if not p1.get("sale_id"):
            log.step("D4", "the 09:35 refresh did nothing for P1 (covered by the resting OCO)", None,
                     "skipped — Day A queued no sale for P1, so there is no OCO-only third to check",
                     status="SKIP")
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
        for t in self._cleanup_tickers():
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
        tickers = self._cleanup_tickers()
        trade_ids = set()
        for t in tickers:
            trade_ids |= set(await env.sentinel_rows(t))
        base = set(self.state.get("order_ids") or [])
        for p in (self.state.get("p1") or {}, self.state.get("p2") or {},
                  self.state.get("r1") or {}):
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
        r1t = self._r1_cleanup_ticker()
        if left_rows:
            main_left = [t for t in left_rows if t != r1t]
            if main_left:
                residue.append(f"rehearsal rows remain for {main_left}")
            if r1t in left_rows:
                residue.append(f"{r1t}: rehearsal row(s) remain")
        audit = await env.audit_rows(None, datetime.fromisoformat(self.state["started_at"])) \
            if self.state.get("started_at") else []
        touched = [r for r in audit if r["detail"].get("trade_id") in trade_ids]
        await env.write_audit(END_EVENT, f"#687 paper rehearsal cleanup: deleted {deleted} row(s); "
                              f"residue {len(residue)}",
                              {"trade_ids": sorted(trade_ids), "residue": residue,
                               "audit_ids_naming_rehearsal_trades": [r["id"] for r in touched]})
        log.note(f"production audit rows that name the rehearsal trades (they stay; account_mode "
                 f"'paper' in their detail): {[(r['id'], r['event_type']) for r in touched]}")
        # R1 is informational: what is left on ITS ticker is reported as INFO (R1c), never in the
        # CLEANUP verdict — but it still makes the `cleanup` command exit 1, so it is re-run.
        r1_res = [r for r in residue if r1t and r.startswith(f"{r1t}:")]
        main_res = [r for r in residue if r not in r1_res]
        self.log.step("CLEANUP", f"orders cancelled, positions flat, {deleted} rehearsal row(s) "
                      f"deleted", not main_res, "; ".join(main_res) or "clean")
        if r1t:
            self.log.step("R1c", f"cleanup of R1's ticker {r1t} (informational)", None,
                          "; ".join(r1_res) or "clean", status="INFO")
        env.clear_state()
        return 0 if not residue else 1

    def _r1_cleanup_ticker(self) -> str | None:
        """R1's ticker — only once R1 started placing orders on it. A ticker R1 SKIPPED (held,
        orders, rows) is never added: cleanup must not flatten what the rehearsal never touched."""
        return (self.state.get("r1") or {}).get("ticker") or None

    def _cleanup_tickers(self) -> list[str]:
        ts = list(self.state.get("tickers") or [self.t1, self.t2, self.probe])
        r1t = self._r1_cleanup_ticker()
        if r1t and r1t not in ts:
            ts.append(r1t)
        return ts

    def _summary(self, label: str) -> int:
        fails = self.log.failed()
        self.log.note(f"{label} RESULT: {sum(r['status'] == 'PASS' for r in self.log.results)} PASS, "
                      f"{len(fails)} FAIL, {sum(r['status'] == 'SKIP' for r in self.log.results)} SKIP, "
                      f"{sum(r['status'] == 'INFO' for r in self.log.results)} INFO"
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

    async def cancelled_at(self, oid):
        """The broker's own stamp for an order's cancel (R1) — `canceled_at` on the raw order,
        which `_order_to_dict` does not carry. Read through the PAPER client (tripwire-guarded)."""
        client = self.alpaca.get_trading_client(ACCOUNT_MODE)
        o = await asyncio.to_thread(client.get_order_by_id, oid)
        return getattr(o, "canceled_at", None)

    def trade_lock(self, tid):
        """The per-trade #151 advisory lock (BLOCKING) — R1f holds it while it flattens, so the
        try-locking re-protect paths (stop-ACK watchdog, coverage repair) defer. Never taken
        around `full_exit`, which takes the same lock itself."""
        return self.om._trade_advisory_lock(tid)

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
                        "detail": d if isinstance(d, dict) else {}, "at": r["created_at"]})
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
                    if isinstance(out, dict):
                        ev["order_id"] = out.get("id")    # B2 reads the restored stop by its id
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
                 foreign_rows=None, partial_taken_false=False, pending_new_s=0.0,
                 restore_retries=0, stream_missed_cancel=False, cls_accepted=False,
                 restore_lost_watchdog_s=None, partial_exit_fails=False,
                 stream_null_late=False, stream_sees_replacement=True):
        # #687 2026-10-06 knobs:
        #   pending_new_s — a stop / limit sell the script places sits `pending_new` this long
        #     before the broker shows it `new` (10-06: A2 fired against a pending stop);
        #   restore_retries — B2's restore is refused this many times (held shares) before it lands;
        #   stream_missed_cancel — the restore re-points the row before the stream handles the
        #     cancel, so the stream cannot match the trade (no null, no silent row, no page);
        #   cls_accepted — paper takes the 15:51 market-on-close order (it did on 10-06);
        #   restore_lost_watchdog_s — B2's restore never lands (10-06) and the stop-ACK watchdog
        #     places a fallback this many seconds later;
        #   partial_exit_fails — the production partial exit returns False (A2 FAILs).
        # B2's stream ordering (review 2026-10-06, MUST-FIX 1). By DEFAULT the stream nulls the
        # pointer as the cancel lands, BEFORE the restore writes its own; its broker check (the 3 s
        # re-check) then finds the restored stop and its #646 (e) fill DEFERS to the restore's write
        # (`stop_pointer_repair_deferred`) — the likeliest shape for a restore that works.
        #   stream_null_late — the stream read the row before the restore re-pointed it and nulled
        #     it AFTER the restore's write; its #646 (e) fill then writes the restored stop back
        #     (`stop_order_id_changed` reason `cancel_or_reject_restored`);
        #   stream_sees_replacement=False — the stream's broker reads miss the restored stop: no
        #     repair, the planned-sale silent row; with stream_null_late the pointer stays NULL and
        #     the stop-ACK watchdog re-adopts the live stop 30 s later.
        self.stream_null_late = stream_null_late
        self.stream_sees_replacement = stream_sees_replacement
        self.pending_new_s = float(pending_new_s)
        self.restore_retries = int(restore_retries)
        self.stream_missed_cancel = stream_missed_cancel
        self.cls_accepted = cls_accepted
        self.restore_lost_watchdog_s = restore_lost_watchdog_s
        self.partial_exit_fails = partial_exit_fails
        self.partial_exit_saw = None            # the P1 stop's status when the partial exit ran
        self.partial_exit_at = None
        self._timers: list[tuple] = []
        self._stream_hold: list | None = None
        self.clock = start
        self.pages: list[dict] = []
        self.tripwire_armed = False
        self.calls: list[tuple] = []           # (fn, account_mode) for every broker call
        self.prices = {"KO": 70.0, "PEP": 150.0, "PG": 160.0, "CL": 85.0}
        self._tid = 0                          # trade ids never reused (R1's row is deleted early)
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
        for at, fn in sorted((x for x in self._timers if x[0] <= when), key=lambda x: x[0]):
            self._timers.remove((at, fn))
            if at > self.clock:
                self.clock = at
            fn()
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

    def _promote(self):
        """A `pending_new` order the broker has since routed reads `new` (pending_new_s)."""
        for o in self.orders.values():
            if o["status"] == "pending_new" and o.get("live_at") and self.clock >= o["live_at"]:
                o["status"] = "new"

    async def position(self, t):
        self._call("get_position")
        self._promote()
        q = self.positions.get(t, 0.0)
        return {"symbol": t, "qty": q, "qty_available": self._avail(t)} if q else None

    async def open_orders(self, t):
        self._call("get_open_orders")
        self._promote()
        return [dict(o) for o in self.orders.values() if o["symbol"] == t
                and o["status"] in LIVE_STATUSES]

    async def get_order(self, oid):
        self._call("get_order")
        self._promote()
        return dict(self.orders[oid]) if oid in self.orders else None

    async def cancel(self, oid):
        self._call("cancel_order")
        self._promote()
        o = self.orders.get(oid)
        if not o or o["status"] not in LIVE_STATUSES:
            return False
        o["status"] = "canceled"
        o["canceled_at"] = self.clock
        for leg in o["legs"]:
            self.orders[leg["id"]]["status"] = "canceled"
        if self._spy is not None:
            self._spy.append({"name": "cancel_order", "args": (oid,), "t": self._mono(), "ok": True,
                              "at": self.clock.isoformat()})
        if self._stream_hold is not None:
            self._stream_hold.append(o)          # the stream sees it after the sale's outcome
        else:
            self._stream_on_cancel(o)
        return True

    def _mono(self):
        return self.clock.timestamp()

    async def cancelled_at(self, oid):
        self._call("get_order")
        return (self.orders.get(oid) or {}).get("canceled_at")

    @contextlib.asynccontextmanager
    async def trade_lock(self, tid):
        self.locked.add(tid)
        try:
            yield
        finally:
            self.locked.discard(tid)

    async def submit(self, t, qty, side, *, kind, tif, limit=None, stop=None):
        self._call("submit_order")
        now_t = self.clock.timetz().replace(tzinfo=None)
        if tif == "cls" and now_t >= dtime(15, 50) and not self.cls_accepted:
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
        elif kind in ("stop", "limit") and self.pending_new_s > 0:
            o["status"] = "pending_new"
            o["live_at"] = self.clock + timedelta(seconds=self.pending_new_s)
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
        self._tid += 1
        tid = 9000 + self._tid
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
        self._promote()
        r = self.trades[tid]
        old = self.orders[r["stop_order_id"]]
        self.partial_exit_saw, self.partial_exit_at = old["status"], self.clock
        # Production aborts when the stop it must replace is not CONFIRMED live
        # (`_STOP_CONFIRMED_LIVE_STATUSES` has no pending_new) — the 10-06 A2 failure.
        if self.partial_exit_fails or old["status"] not in {
                "new", "accepted", "held", "partially_filled", "accepted_for_bidding"}:
            return False
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
            ev.setdefault("at", self.clock.isoformat())
            self._spy.append(ev)

    async def _sale(self, tid, reason, vehicle):
        r = self.trades[tid]
        t, stop_id = r["ticker"], r["stop_order_id"]
        self.locked.add(tid)
        self._stream_hold, refused = [], False
        nulled: set = set()                      # cancels whose stream null already ran
        restored_id = None
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
                    refused = True
                    err = (f"insufficient qty available for order (requested: {qty:g}, "
                           f"available: {self._avail(t):g}) held_for_orders")
                    self._spy_ev(**ev, ok=False, error=err)
                    self._audit("full_exit_rejected", {"trade_id": tid})
                    self.clock += timedelta(seconds=1)
                    free = self.positions[t] - self._held(t, exclude=(stop_id,))
                    want = min(free, r["remaining_shares"])
                    if self.restore_lost_watchdog_s is not None:
                        # 10-06: the ONE restore attempt was refused; the stop-ACK watchdog placed
                        # a fallback ~40 s later.
                        self._spy_ev(name="place_stop_order", args=(t,), qty=want, ok=False,
                                     error=err)
                        r["stop_order_id"] = None
                        # Since the retry (#687 2026-10-06) a held refusal that never clears ends
                        # in this row once the window is spent; the page is unchanged.
                        self._audit("stop_restore_retry_ended",
                                    {"trade_id": tid, "outcome": "failed", "attempts": 1,
                                     "slept_s": 15.0, "elapsed_s": 15.0})

                        def _watchdog(tid=tid, t=t, want=want, px=r["stop_price"]):
                            if tid not in self.trades:     # the row was deleted (R1f, cleanup)
                                return
                            fb = self._new(t, want, "sell", "stop", "gtc", status="new", stop=px)
                            self.trades[tid]["stop_order_id"] = fb["id"]
                            self._audit("stop_ack_timeout_remediated", {"trade_id": tid})

                        self._timers.append(
                            (self.clock + timedelta(seconds=self.restore_lost_watchdog_s), _watchdog))
                        self._page(f"📄 PAPER ⚠️ Full exit FAILED for {t}: {err}\n🚨 STOP NOT "
                                   f"RESTORED — position is UNPROTECTED. Manual action required.")
                        return False
                    for _ in range(self.restore_retries):   # held: the cancel has not settled
                        self._spy_ev(name="place_stop_order", args=(t,), qty=want, ok=False,
                                     error=err)
                        self.clock += timedelta(seconds=0.5)
                    if not (self.stream_null_late or self.stream_missed_cancel):
                        for o in self._stream_hold:      # the cancel lands: the stream nulls first
                            self._stream_on_cancel(o, check=False)
                            nulled.add(o["id"])
                    restored = self._new(t, want, "sell", "stop", "gtc", status="new",
                                         stop=r["stop_price"])
                    self._spy_ev(name="place_stop_order", args=(t,), qty=restored["qty"], ok=True,
                                 order_id=restored["id"])
                    restored_id = restored["id"]
                    r["stop_order_id"] = restored["id"]
                    self._audit("stop_order_id_changed", {"trade_id": tid, "new_id": restored["id"],
                                                          "reason": "restored_after_failed_full_exit"})
                    if self.restore_retries:
                        self._audit("stop_restore_retried",
                                    {"trade_id": tid, "attempts": self.restore_retries + 1,
                                     "slept_s": 0.5 * self.restore_retries,
                                     "elapsed_s": 0.5 * self.restore_retries})
                    self._page(f"📄 PAPER ⚠️ Full exit FAILED for {t}: {err}\nStop RESTORED at "
                               f"${r['stop_price']:.2f} — position is protected.")
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
            held, self._stream_hold = self._stream_hold or [], None
            for o in held:
                # stream_missed_cancel: the restore re-pointed the row first, so the stream's
                # lookup by the cancelled stop's id finds nothing — no null, no row, no page.
                if not (refused and self.stream_missed_cancel):
                    self._stream_on_cancel(o, null=o["id"] not in nulled)
            if (restored_id and tid in self.trades
                    and self.trades[tid].get("stop_order_id") is None):
                # The stream nulled the pointer after the restore's write and did not see the
                # restored stop: the stop-ACK watchdog (09-15 ET) re-adopts the live broker stop.
                def _readopt(tid=tid, rid=restored_id):
                    if tid not in self.trades:             # the row was deleted (R1f, cleanup)
                        return
                    self.trades[tid]["stop_order_id"] = rid
                    self._audit("stop_order_id_changed", {"trade_id": tid, "new_id": rid,
                                                          "reason": "watchdog_synced_from_broker"})

                self._timers.append((self.clock + timedelta(seconds=30), _readopt))

    async def full_exit(self, tid, reason):
        return await self._sale(tid, reason, "close")

    async def depth_open_sale(self, tid):
        return await self._sale(tid, REASON, "opg")

    def _stream_on_cancel(self, o, *, null=True, check=True):
        """The production cancel handler (`trade_stream._handle_cancel_or_reject`) as far as the
        rehearsal's checks read it. A stop OUR planned sale cancelled: (null) the row's pointer is
        cleared unconditionally (`cancel_or_reject_null`); (check) the broker is asked for a
        DIFFERENT live sell stop covering the row — the REAL `_find_replacement_stop` over what
        `get_open_orders` shows (held OCO legs hidden, #566). Found → the #646 (e) fill: written
        only while the pointer is still NULL (`cancel_or_reject_restored`), else
        `stop_pointer_repair_deferred`. Not found → the planned-sale silent row (with
        stream_silent=False, the "unprotected" page instead). `null` / `check` split the handler so
        B2 can put the restore's own pointer write between them."""
        planned = {(a["detail"]["trade_id"], a["detail"]["stop_order_id"]) for a in self.audit
                   if a["event_type"] == "planned_sale_stop_cancel"}
        for tid, r in self.trades.items():
            if (tid, o["id"]) in planned and null:
                r["stop_order_id"] = None
                self._audit("stop_order_id_changed", {"trade_id": tid, "new_id": None,
                                                      "reason": "cancel_or_reject_null"})
            if (tid, o["id"]) in planned and check:
                rep = self._stream_replacement(o, r) if self.stream_sees_replacement else None
                if rep and r["stop_order_id"] is None:
                    r["stop_order_id"] = rep["id"]
                    self._audit("stop_order_id_changed", {"trade_id": tid, "new_id": rep["id"],
                                                          "reason": "cancel_or_reject_restored"})
                elif rep:
                    self._audit("stop_pointer_repair_deferred",
                                {"trade_id": tid, "cancelled_order_id": o["id"],
                                 "confirmed_replacement_id": rep["id"]})
                elif self.stream_silent:
                    self._audit("stop_cancel_by_planned_sale_silent",
                                {"trade_id": tid, "cancelled_order_id": o["id"]})
            if check and o.get("order_class") == "oco" and any(
                    x["trade_id"] == tid and x["alpaca_order_id"] == o["id"]
                    for x in self.live_orders):
                n = self._new(o["symbol"], o["qty"], "sell", "stop", "gtc", status="new",
                              stop=r["stop_price"])
                r["stop_order_id"] = n["id"]

    def _stream_replacement(self, o, r):
        # The CLI dry run (`python scripts/probes/_687/paper_rehearsal.py day-a --dry-run`) puts
        # only this script's directory on sys.path; the repo root is needed for the real function.
        root = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        if root not in sys.path:
            sys.path.insert(0, root)
        from agents.market_intelligence.broker.trade_stream import _find_replacement_stop
        shown = [dict(x) for x in self.orders.values()
                 if x["status"] in LIVE_STATUSES and not x.get("is_leg")]
        return _find_replacement_stop(shown, o["symbol"], o["id"], r["remaining_shares"])

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


async def run_dry(cmd: str, tickers, log_dir: str | None = None,
                  r1_ticker: str | None = DEFAULT_R1_TICKER,
                  **fake_kw) -> tuple[int, "FakeEnv", StepLog]:
    """Day A from 13:00 ET on a Monday, then Day B the next morning — all against FakeEnv."""
    day_a = date(2026, 10, 5)
    env = FakeEnv(start=datetime.combine(day_a, dtime(13, 0), tzinfo=_ET), **fake_kw)
    path = os.path.join(log_dir or HERE, f"rehearsal_{day_a.isoformat()}_dryrun.log")
    log = StepLog(path, env.now)
    reh = Rehearsal(env, log, tickers, r1_ticker=r1_ticker)
    rc = 0
    if cmd in ("day-a", "all"):
        rc = await reh.day_a()
    if cmd in ("day-b", "all"):
        env.clock = datetime.combine(day_a + timedelta(days=1), dtime(9, 0), tzinfo=_ET)
        rc = max(rc, await Rehearsal(env, log, tickers).day_b())
    return rc, env, log


async def run_real(cmd: str, tickers, send_pages: bool,
                   r1_ticker: str | None = DEFAULT_R1_TICKER) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
    _bootstrap_alpaca_credentials()
    env = RealEnv(send_pages=send_pages)
    if cmd in ("day-b", "status", "cleanup") and env.load_state() is None:
        st = await env.load_state_from_audit()
        if st:
            await env.save_state(st)
    log = StepLog(_log_path(env.et_today(), False), env.now)
    reh = Rehearsal(env, log, tickers, r1_ticker=r1_ticker)
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
    ap.add_argument("--r1-ticker", default=DEFAULT_R1_TICKER,
                    help="R1's own ticker (informational step; default %(default)s; '' skips R1)")
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
            rc, _, _ = asyncio.run(run_dry(cmd, tickers, r1_ticker=a.r1_ticker))
            return rc
        return asyncio.run(run_real(a.cmd, tickers, send_pages=not a.capture_pages,
                                    r1_ticker=a.r1_ticker))
    except RehearsalRefused as e:
        print(f"REFUSED: {e}")
        return 2
    except LiveTouched as e:
        print(f"ABORTED — LIVE TOUCHED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
