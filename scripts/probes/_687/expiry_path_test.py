"""#687 — the MONDAY PAPER TEST of the expired full-exit-sale restore (card 1 of
docs/roadmap/weekend_build_cards_2026-10-10.md; his ruling 2026-10-09: *"ok, monday"* — one test of
this path at Monday's open, then the switch-on).

WHAT IT PROVES. Friday's Day B (scripts/probes/_1008/) found that when a queued opening-auction sale
EXPIRES unfilled, `trade_stream._handle_cancel_or_reject` §3 counted the dead sale as still holding
every share, paged "No stop re-placed" and returned: PEP sat without a stop 09:30:57 -> 09:35:00. The
fix (excluded dead sale id + a background held-shares retry) is unit-tested; this is the one live
look at the real thing. A 3-share KO position on the PAPER account is bought pre-market with NO stop,
a sale that cannot fill is queued for the open, the sale expires at ~09:30:57, and we look for the
stop.

PAPER ONLY — it reuses paper_rehearsal.py's guards unchanged: the paper account id is compared with
the live one, a TRIPWIRE makes any non-paper client lookup raise, every order carries
`make_client_order_id('paper', 'integration_test', ticker)`, every row is
`signal_type='integration_test', account_mode='paper'`, and cleanup is the rehearsal's own.

SCHEDULE (ET, a market day):
  08:30  extended-hours LIMIT buy of 3 KO at the ask (alpaca-py LimitOrderRequest, extended_hours=True,
         DAY) -> its fill pages "Untracked fill" (expected). Then the trade row: status 'filled',
         remaining_shares 3, stop_order_id NULL (as on Day B), stop_price/hard_stop 15% BELOW the
         fill (a stop above the market would take ruling 3 — a market sale — instead of restoring).
  09:05  opening-auction (opg) SELL of 3 sh, recorded with `order_manager._record_full_exit_order`
         (called, not copied). A LIMIT at 2x the last price cannot fill; only a MARKET opg that expires
         unfilled is proven on paper (Day B), so a refused opg limit falls back to a market opg (it
         may FILL -> VOID).
  09:30  watch the sale and the broker. 09:31:30 is the FAIL line; 09:32 is the INCONCLUSIVE line.
  09:46  cleanup (rehearsal's: the planned-sale cancel row for the restored stop is written BEFORE it
         is cancelled, shares free, KO sold at market, rows deleted).

VERDICTS (`classify`, pure, unit-checked):
  PASS          a stop for 3 sh at the row's price, created <= 15 s after the expiry, its id on the row,
                and the restore's pointer row (`stop_order_id_changed` reason `cancel_or_reject_restored`
                — written immediately before the 'Stop re-placed' page). It ALSO records whether a
                `stop_restore_retried` row appeared: a first-attempt stop passes but leaves the retry
                unit-tested only (as on Day A) — that is a pass, say so.
  FAIL          no stop by 09:31:30; a stop of the wrong size / price / not on the row / late; or a
                'No stop re-placed' / UNPROTECTED page was seen.
  INCONCLUSIVE  the opg order was rejected, or no expiry by 09:32.
  VOID          the sale FILLED.
  ⚠ The pages themselves are sent by the STREAM process, not this one, so they are not observable
  here: the probe uses the pointer row as the page's marker and prints "CHECK TELEGRAM" — the laptop
  wake looks for exactly one 'Stop re-placed' paper page and none of 'No stop re-placed' /
  'UNPROTECTED' / 'STOP RESTORE FAILED'.

WHERE IT RUNS — the SERVER, never the laptop (a laptop wake can miss 08:30). Armed Sunday night as a
`nohup` wall-clock loop on the host that, at 08:25 ET Monday, runs
    docker exec -d apollo-execution python scripts/probes/_687/expiry_path_test.py run
logging `LAUNCHED` to /home/apollo/expiry_test_launch_2026-10-12.log (the shape of Friday's dayb_launch).
    expiry_path_test.py status     # read-only: the log tail + the row + KO at the broker
    expiry_path_test.py cleanup    # the abort path
It REFUSES to start outside a market day 08:20-08:45 ET (`--force-time` overrides, for a dry look).

EXIT CODES: 0 PASS (or INCONCLUSIVE/VOID, which are re-runs, not failures — see the log) ·
1 FAIL · 2 refused / could not run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import paper_rehearsal as PR   # noqa: E402  (the guards, StepLog, RealEnv and cleanup — reused, not copied)

_ET = ZoneInfo("America/New_York")
TICKER = "KO"
QTY = 3
STOP_BELOW_FILL = 0.85            # the row's stop: 15% under the fill — far below any pre-open price
SALE_LIMIT_MULT = 2.0             # an opg LIMIT sell at 2x the last price cannot fill
RESULT_EVENT = "expiry_path_test_687_result"

T_LAUNCH_FROM = dtime(8, 20)
T_LAUNCH_TO = dtime(8, 45)
T_BUY = dtime(8, 30)
T_BUY_FILL_DEADLINE = dtime(8, 58)
T_SELL = dtime(9, 5)
T_OPEN = dtime(9, 30)
T_FAIL_DEADLINE = dtime(9, 31, 30)      # no stop by here = FAIL
T_NO_EXPIRY_DEADLINE = dtime(9, 32)     # no expiry by here = INCONCLUSIVE
T_CLEANUP = dtime(9, 46)
PASS_WITHIN_S = 15.0                    # stop created within this long of the expiry

PASS, FAIL, INCONCLUSIVE, VOID = "PASS", "FAIL", "INCONCLUSIVE", "VOID"
BAD_PAGES = ("No stop re-placed", "UNPROTECTED", "STOP RESTORE FAILED")
DEAD_STATUSES = {"expired", "canceled", "cancelled"}


# ── pure parts (unit-checked in tests/test_687_expiry_path_probe.py; never touch a broker) ────────

def launch_refusal(now: datetime) -> str | None:
    """Why the test must NOT start now (None = fine). A market day, inside the launch window."""
    n = now.astimezone(_ET)
    if n.weekday() >= 5:
        return "needs a market day (Mon-Fri) — the sale has to meet a real opening auction"
    t = n.timetz().replace(tzinfo=None)
    if not (T_LAUNCH_FROM <= t <= T_LAUNCH_TO):
        return (f"launch window is {T_LAUNCH_FROM:%H:%M}-{T_LAUNCH_TO:%H:%M} ET (the 08:30 buy needs "
                f"it); it is {t:%H:%M:%S} ET")
    return None


def stop_price_for(fill: float) -> float:
    """The row's stop / hard stop: well below the market, so a rejected restore can only be a
    held-shares one (never ruling 3's 'price through the stop')."""
    return round(float(fill) * STOP_BELOW_FILL, 2)


def sale_limit_for(last: float) -> float:
    return round(float(last) * SALE_LIMIT_MULT, 2)


def ext_hours_buy_fields(ticker: str, qty: int, ask: float, client_order_id: str) -> dict:
    """The extended-hours buy, as plain fields (pure): a LIMIT at the ask, DAY (alpaca-py rejects
    anything but DAY with `extended_hours=True`), extended_hours set."""
    return {"symbol": ticker, "qty": qty, "side": "buy", "time_in_force": "day",
            "limit_price": round(float(ask), 2), "extended_hours": True,
            "client_order_id": client_order_id}


def build_ext_hours_buy(ticker: str, qty: int, ask: float, client_order_id: str):
    """The alpaca-py request for `ext_hours_buy_fields`. No helper exists in alpaca_client, so it is
    built here and handed to the PAPER client."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest
    f = ext_hours_buy_fields(ticker, qty, ask, client_order_id)
    return LimitOrderRequest(
        symbol=f["symbol"], qty=f["qty"], side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
        limit_price=f["limit_price"], extended_hours=f["extended_hours"],
        client_order_id=f["client_order_id"])


def terminal_at(raw) -> datetime | None:
    """When the broker says the sale died: expired_at, else canceled_at / failed_at, else the last
    update. `raw` is the alpaca-py order object or a dict of the same names."""
    for name in ("expired_at", "canceled_at", "failed_at", "updated_at"):
        v = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)
        t = PR._ts(v)
        if t is not None:
            return t
    return None


def find_restored_stop(open_orders: list, qty: int) -> dict | None:
    """The live SELL stop that holds `qty` shares (the restored one), or None."""
    for o in open_orders:
        if (str(o.get("side") or "").split(".")[-1].lower() == "sell"
                and str(o.get("type") or "").split(".")[-1].lower() == "stop"
                and abs(float(o.get("qty") or 0) - qty) < 1e-9):
            return o
    return None


def classify(obs: dict) -> tuple[str, str]:
    """(verdict, why) from what the watch saw. `obs` keys:
       sale_status      canon status of the opg sale ('filled', 'rejected', 'expired', ...)
       expiry_at        datetime the sale died (None = it had not by the INCONCLUSIVE line)
       stop             {'id','qty','price','created_at'} of the stop at the broker, or None
       expected_qty / expected_price   the row's own
       row_stop_id      mi_live_trades.stop_order_id at the end of the watch
       pointer_row      a stop_order_id_changed row, reason cancel_or_reject_restored, naming the stop
       retry_row        a stop_restore_retried row exists for the trade
       bad_page_seen    True / False / None (None = not observable from this process)
    """
    status = PR.canon(obs.get("sale_status"))
    if status == "filled":
        return VOID, "the sale FILLED — there was nothing to restore; re-run another morning"
    if status == "rejected":
        return INCONCLUSIVE, "the opening-auction order was REJECTED — no expiry to test"
    if obs.get("expiry_at") is None:
        return INCONCLUSIVE, f"no expiry by {T_NO_EXPIRY_DEADLINE:%H:%M} ET (sale status '{status}')"
    if obs.get("bad_page_seen"):
        return FAIL, "a 'No stop re-placed' / UNPROTECTED page was seen"
    stop = obs.get("stop")
    if not stop:
        return FAIL, (f"NO stop at the broker by {T_FAIL_DEADLINE:%H:%M:%S} ET after the sale "
                      f"died at {PR._hms(obs['expiry_at'])} ET — the Day B failure, not fixed")
    problems = []
    if abs(float(stop.get("qty") or 0) - float(obs["expected_qty"])) > 1e-9:
        problems.append(f"stop is for {stop.get('qty')} sh, not {obs['expected_qty']}")
    if abs(float(stop.get("price") or 0) - float(obs["expected_price"])) > 0.005:
        problems.append(f"stop price {stop.get('price')} != the row's {obs['expected_price']}")
    if obs.get("row_stop_id") != stop.get("id"):
        problems.append(f"the row's stop_order_id is {obs.get('row_stop_id')!r}, not the stop "
                        f"{stop.get('id')!r}")
    created = PR._ts(stop.get("created_at"))
    delta = (created - PR._ts(obs["expiry_at"])).total_seconds() if created else None
    if delta is None:
        problems.append("the stop has no creation time")
    elif delta > PASS_WITHIN_S:
        problems.append(f"stop created {delta:.1f}s after the expiry (> {PASS_WITHIN_S:.0f}s)")
    elif delta < 0:
        problems.append(f"stop created {-delta:.1f}s BEFORE the expiry — not the restore")
    if not obs.get("pointer_row"):
        problems.append("no stop_order_id_changed row (reason cancel_or_reject_restored) naming the stop "
                        "— the 'Stop re-placed' page's marker")
    if problems:
        return FAIL, "; ".join(problems)
    path = ("the held-shares RETRY placed it (stop_restore_retried row) — the retry is PROVEN live"
            if obs.get("retry_row") else
            "the FIRST attempt placed it (no stop_restore_retried row) — the retry stays "
            "unit-tested only, as on Day A; a pass, not a fail")
    return PASS, (f"stop for {stop.get('qty'):g} sh @ ${float(stop['price']):.2f} created "
                  f"{delta:.1f}s after the expiry, on the row; {path}. "
                  f"CHECK TELEGRAM: one 'Stop re-placed' paper page, none of {list(BAD_PAGES)}")


# ── the real run (apollo-execution, paper) ────────────────────────────────────────────────────────

def _at(day: date, t: dtime) -> datetime:
    return datetime.combine(day, t, tzinfo=_ET)


async def _ticker_clean(env, ticker: str) -> str | None:
    """Why the ticker is NOT usable (None = clean): held, open orders, any open/own trade row."""
    pos = await env.position(ticker)
    if pos and abs(float(pos.get("qty") or 0)) > 0:
        return f"the paper account already holds {ticker} ({pos.get('qty')} sh)"
    if await env.open_orders(ticker):
        return f"the paper account has open order(s) in {ticker}"
    if await env.foreign_open_rows(ticker):
        return f"open paper trade row(s) exist for {ticker}"
    if await env.sentinel_rows(ticker):
        return f"rehearsal rows for {ticker} are left from an earlier run — run `cleanup` first"
    return None


async def _raw_order(env, oid):
    client = env.alpaca.get_trading_client(PR.ACCOUNT_MODE)        # tripwire-guarded
    return await asyncio.to_thread(client.get_order_by_id, oid)


async def _wait_until(env, day: date, t: dtime) -> None:
    if env.now() < _at(day, t):
        await env.sleep_until(_at(day, t))


async def _buy(env, log, reh, ticker: str, today: date) -> tuple[int, float]:
    """08:30 — the extended-hours buy, its fill, and the row. Returns (trade_id, fill price)."""
    await _wait_until(env, today, T_BUY)
    quote = await env.alpaca.get_latest_quote(ticker)
    if not quote or not quote.get("ask"):
        raise PR.RehearsalRefused(f"no ask for {ticker} — cannot price the extended-hours buy")
    req = build_ext_hours_buy(ticker, QTY, quote["ask"], env._coid(ticker))
    client = env.alpaca.get_trading_client(PR.ACCOUNT_MODE)
    order = env.alpaca._order_to_dict(await asyncio.to_thread(client.submit_order, req))
    reh.state["order_ids"].append(order["id"])
    await reh._save()
    log.note(f"extended-hours LIMIT buy {QTY} {ticker} @ ask ${quote['ask']:.2f} sent "
             f"(order {order['id'][:8]}); its fill pages 'Untracked fill' — expected")
    st = await reh._wait_status(order["id"], {"filled"}, budget_s=max(
        (_at(today, T_BUY_FILL_DEADLINE) - env.now()).total_seconds(), 1.0))
    if st != "filled":
        raise PR.RehearsalRefused(f"the buy was '{st}' by {T_BUY_FILL_DEADLINE:%H:%M} ET — "
                                  f"no position to test; cleaning up")
    filled = await env.get_order(order["id"])
    fill = float(filled["filled_avg_price"])
    tid = await env.insert_trade(ticker=ticker, shares=QTY, entry=fill, stop=stop_price_for(fill),
                                 stop_id=None, alert_date=today)
    reh.state["trade_id"], reh.state["fill"] = tid, fill
    await reh._save()
    log.step("T1", f"{QTY} {ticker} bought pre-market, row #{tid} (no stop, as on Day B)", True,
             f"fill ${fill:.2f}; stop_price/hard_stop ${stop_price_for(fill):.2f}")
    return tid, fill


async def _queue_sale(env, log, reh, ticker: str, tid: int, fill: float, today: date) -> str:
    """09:05 — the opg sale that cannot fill, recorded as the production path records it."""
    await _wait_until(env, today, T_SELL)
    last = (await env.alpaca.get_latest_trade(ticker) or {}).get("price") or fill
    kind = "LIMIT"
    try:
        sale = await env.submit(ticker, QTY, "sell", kind="limit", tif="opg",
                                limit=sale_limit_for(last))
    except PR.LiveTouched:
        raise
    except Exception as e:
        kind = "MARKET (the opg limit was refused: " + str(e)[:120] + ")"
        sale = await env.alpaca.place_market_on_open_sell(
            ticker, QTY, account_mode=PR.ACCOUNT_MODE, client_order_id=env._coid(ticker))
    reh.state["order_ids"].append(sale["id"])
    reh.state["sale_id"] = sale["id"]
    await env.om._record_full_exit_order(tid, ticker, sale, QTY, PR.REASON)
    await reh._save()
    log.step("T2", f"opening-auction {kind} sell of {QTY} {ticker} queued and recorded", True,
             f"order {sale['id'][:8]} status {PR.canon(sale.get('status'))}")
    return sale["id"]


async def _watch(env, log, reh, ticker: str, tid: int, sale_id: str, today: date) -> dict:
    """09:30 -> the FAIL / INCONCLUSIVE lines: when did the sale die, and what protects the shares."""
    await _wait_until(env, today, T_OPEN)
    since = _at(today, dtime(8, 0))
    obs = {"sale_status": "", "expiry_at": None, "stop": None, "expected_qty": QTY,
           "expected_price": stop_price_for(reh.state["fill"]), "row_stop_id": None,
           "pointer_row": False, "retry_row": False, "bad_page_seen": None}
    while env.now() < _at(today, T_NO_EXPIRY_DEADLINE):
        raw = await _raw_order(env, sale_id)
        obs["sale_status"] = PR.canon(getattr(raw, "status", None))
        if obs["sale_status"] in ("filled", "rejected"):
            break
        if obs["sale_status"] in DEAD_STATUSES and obs["expiry_at"] is None:
            obs["expiry_at"] = terminal_at(raw) or env.now()
            log.note(f"the sale went '{obs['sale_status']}' at {PR._hms(obs['expiry_at'])} ET")
        if obs["expiry_at"] is not None:
            stop = find_restored_stop(await env.open_orders(ticker), QTY)
            row = await env.trade(tid)
            obs["row_stop_id"] = (row or {}).get("stop_order_id")
            if stop:
                obs["stop"] = {"id": stop["id"], "qty": stop.get("qty"),
                               "price": stop.get("stop_price"), "created_at": stop.get("created_at")}
                rows = await env.audit_rows(["stop_order_id_changed", "stop_restore_retried"], since)
                mine = [r for r in rows if r["detail"].get("trade_id") == tid]
                obs["pointer_row"] = any(
                    r["event_type"] == "stop_order_id_changed"
                    and r["detail"].get("reason") == "cancel_or_reject_restored"
                    and r["detail"].get("new_id") == stop["id"] for r in mine)
                obs["retry_row"] = any(r["event_type"] == "stop_restore_retried" for r in mine)
                if obs["pointer_row"] and obs["row_stop_id"] == stop["id"]:
                    break
            elif env.now() >= _at(today, T_FAIL_DEADLINE):
                break
        await env.sleep(1.0)
    return obs


async def run_real(cmd: str, ticker: str, *, force_time: bool, send_pages: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
    _bootstrap_alpaca_credentials()
    env = PR.RealEnv(send_pages=send_pages, state_path=os.path.join(HERE, "expiry_state.json"))
    today = env.et_today()
    log = PR.StepLog(os.path.join(HERE, f"expiry_test_{today.isoformat()}.log"), env.now)
    reh = PR.Rehearsal(env, log, (ticker, ticker, ticker), r1_ticker=None)
    if cmd in ("status", "cleanup") and env.load_state() is None:
        st = await env.load_state_from_audit()
        if st:
            await env.save_state(st)
    if cmd == "cleanup":
        await reh.preflight(day="cleanup")          # paper guard + tripwire BEFORE anything is cancelled
        reh.state = env.load_state() or {"tickers": [ticker], "order_ids": [], "p1": {}, "p2": {},
                                         "r1": {}}
        return await reh.cleanup()
    if cmd == "status":
        await reh.preflight(day="status")
        pos = await env.position(ticker)
        log.note(f"{ticker} at the broker: {pos}; open orders: "
                 f"{[(o['id'][:8], o['type'], o['qty']) for o in await env.open_orders(ticker)]}; "
                 f"rows: {await env.sentinel_rows(ticker)}; state: {env.load_state()}")
        return 0

    why = launch_refusal(env.now())
    if why and not force_time:
        raise PR.RehearsalRefused(why)
    await reh.preflight(day="expiry")                       # paper guard + live tripwire
    unusable = await _ticker_clean(env, ticker)
    if unusable:
        raise PR.RehearsalRefused(unusable)
    env.install_page_router()
    reh.state = {"day_a": today.isoformat(), "tickers": [ticker], "started_at": env.now().isoformat(),
                 "order_ids": [], "p1": {}, "p2": {}, "r1": {}}
    await env.write_audit(PR.START_EVENT, f"#687 expiry-path test started ({ticker})", {"state": reh.state})
    verdict, why = INCONCLUSIVE, "did not complete"
    try:
        tid, fill = await _buy(env, log, reh, ticker, today)
        sale_id = await _queue_sale(env, log, reh, ticker, tid, fill, today)
        obs = await _watch(env, log, reh, ticker, tid, sale_id, today)
        verdict, why = classify(obs)
        log.step("T3", "the expired sale's stop is re-placed within 15 s",
                 verdict == PASS, f"{verdict}: {why}",
                 status="PASS" if verdict == PASS else ("FAIL" if verdict == FAIL else "INFO"))
        await env.write_audit(RESULT_EVENT, f"#687 expiry-path test: {verdict}",
                              {"verdict": verdict, "why": why, "trade_id": tid,
                               "obs": {k: v for k, v in obs.items()}})
        await _wait_until(env, today, T_CLEANUP)
    except PR.RehearsalRefused as e:
        verdict, why = INCONCLUSIVE, f"refused: {e}"
        log.step("T0", "could not run", None, why, status="INFO")
    finally:
        await reh.cleanup()
    log.note(f"RESULT: {verdict} — {why}")
    return 1 if verdict == FAIL else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["run", "status", "cleanup"])
    ap.add_argument("--ticker", default=TICKER)
    ap.add_argument("--force-time", action="store_true",
                    help="skip the 08:20-08:45 ET market-day launch refusal")
    ap.add_argument("--capture-pages", action="store_true",
                    help="log the pages this process would send instead of sending them")
    a = ap.parse_args(argv)
    try:
        return asyncio.run(run_real(a.cmd, a.ticker.upper(), force_time=a.force_time,
                                    send_pages=not a.capture_pages))
    except PR.RehearsalRefused as e:
        print(f"REFUSED: {e}")
        return 2
    except PR.LiveTouched as e:
        print(f"ABORTED — LIVE TOUCHED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
