"""Breakout v1 — the NIGHTLY LIST (component B2) and its one Telegram message (B3), PAPER setup phase 1. No orders.

The rules are `breakout_v1.py` (PURE); this module is the plumbing around them for ONE night D = today:
  1. universe bars from `mi_daily_closes` (`db.cb_get_universe_bars`, the shadow's SQL prefilter at the v1 floors:
     close >= $2 today, median dollar volume over the last 20 sessions >= 0.7 x $5M — a deliberate SUPERSET, the module
     stays the authority), indexed on SPY's calendar (`consolidation_breakout_shadow.build_series`);
  2. the TYPE half of the universe from `mi_security_types` (type + Polygon's stored name): common stock, ADRs and
     SINGLE-ASSET funds (`breakout_v1.security_admitted` / `fund_rule`); a fund with no stored name is EXCLUDED (fail
     closed) and counted; a ticker whose stored history crosses an UNAPPLIED split sits out (two price scales);
  3. the RS cross-section over EVERY security at the v1 floors (raw close >= $2, 20-session median dollar volume >= $5M,
     a 63-session return known over consecutive sessions), funds and ETFs included — `cb.cross_section_one_date`'s
     rs_best. His ruling 2026-10-29 ("Ok a"): the pool the approved 12-of-24 check ranked against; the TYPE rule decides
     only who may be LISTED (a pool-only member is ranked, never given the gates);
  4. `breakout_v1.v1_gates` per member with the 86-session consecutive history; every name passing every gate is a row
     of `mi_breakout_v1_list` (the night's rows replaced whole — idempotent), ranked by rs_best;
  5. ONE audit row `breakout_v1_list_run` (universe size, funds kept / excluded and why, names passing, per-gate fail
     counts, the message's fate);
  6. ONE paper-prefixed Telegram message naming tonight's list (ticker, level, rs_best) — ONLY when the list is
     non-empty (an alert that says no action is noise). A failed send is logged and counted in the audit row.

THE LINE. A LIST and a GRADE only: this module writes `mi_breakout_v1_list` and `mi_audit_log` (through
`log_audit_event`), imports nothing from `broker/`, writes no trade table and no `mi_strategies` row, prepares no
order. No entry / sizing / order / safeguard path reads the list in phase 1.

Fails OPEN under `BUDGET_S` (a `breakout_v1_list_error` audit row, no raise; the next night rebuilds its own list);
a crash is re-raised AFTER the audit row so `audit_wrap`'s `notify_job_failure` is the one page.
Owner doc: docs/setups/consolidation_breakout.md (2026-10-29 "breakout v1 PHASE 1 BUILT").
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from datetime import date
from typing import Optional

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence.consolidation_breakout_shadow import _json_safe, build_series
from agents.market_intelligence.db import (
    bv1_get_security_types_named,
    bv1_replace_list,
    cb_get_calendar,
    cb_get_universe_bars,
    get_unapplied_splits,
    log_audit_event,
)

logger = logging.getLogger(__name__)

JOB_ID = "breakout_v1_list"
AUDIT_RUN_EVENT = "breakout_v1_list_run"
AUDIT_ERROR_EVENT = "breakout_v1_list_error"
BUDGET_S = 600                        # fail open past this (the shadow's pattern; a night is ~1 minute of work)
HISTORY_SESSIONS = 150                # bars loaded per name: >= 127 (the 126-session return) + margin
CALENDAR_SESSIONS = 400
PREFILTER_DOLLAR_VOL = 0.7 * bv.MIN_DOLLAR_VOL
SCAN_CHUNK = 250                      # tickers per to_thread slice: cancellation lands between slices
FUND_EXCLUDED_LIST_MAX = 60           # fund tickers named in the audit row, per reason
MESSAGE_MAX_NAMES = 40


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Pure plumbing (unit-tested without a database)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def scan_members(series: dict, *, today_ci: int, types: dict, unapplied: set) -> dict:
    """Tonight's RS-pool members and their facts. `series` = {ticker: (DailyBars, cidx)}, `types` = {ticker:
    (security_type, name)}. Returns {"members": [...], "counts": Counter, "fund_kept": [...], "fund_excluded":
    {reason: [...]}}. A member passes the $2 / $5M floors at D and has a 63-session return over consecutive sessions —
    whatever its type (the RS pool, his 2026-10-29 ruling (a)); `listable` says whether its TYPE admits it to the list
    (stock, ADR, unknown type, kept single-asset fund); `history` says whether the 86-session data guard holds. Only a
    listable member with history gets the gates. Bad tickers / test symbols are out of both."""
    members, counts = [], Counter()
    fund_kept, fund_excl = [], {}
    for ticker, (bars, cidx) in series.items():
        D = len(bars) - 1
        if int(cidx[-1]) != today_ci:
            counts["no_bar_today"] += 1
            continue
        st, name = types.get(ticker, (None, None))
        ok, why = bv.security_admitted(ticker, st, name)
        if st == bv.FUND_SECURITY_TYPE:
            if ok:
                fund_kept.append(ticker)
            else:
                fund_excl.setdefault(why, []).append(ticker)
        if why == "ticker":
            counts["excluded_ticker"] += 1
            continue
        if ok:
            counts["admitted_" + why] += 1
        else:
            counts["rank_only_" + why] += 1          # ranked in the RS pool, never listed (ruling (a), 2026-10-29)
        if ticker in unapplied:
            counts["split_unapplied"] += 1
            continue
        rc = float(bars.c[D])
        if D + 1 < cb.DOLLAR_VOL_WINDOW:
            counts["short_history"] += 1
            continue
        dv20 = cb._dollar_vol_median(bars, D)
        if not (rc >= bv.MIN_PRICE and dv20 >= bv.MIN_DOLLAR_VOL):
            counts["below_floors"] += 1
            continue
        r21, r63, r126 = bv.rs_returns_contiguous(bars, D, cidx)
        if r63 is None:
            counts["no_r63"] += 1
            continue
        members.append({"ticker": ticker, "security_type": st or "", "r21": r21, "r63": r63, "r126": r126,
                        "listable": bool(ok), "history": bv.history_ok(D, cidx), "bars": bars, "cidx": cidx})
    return {"members": members, "counts": counts, "fund_kept": fund_kept, "fund_excluded": fund_excl}


def evaluate_members(members: list, rs_best: list, today: date) -> tuple:
    """`v1_gates` per member (with its rs_best) -> (passing list rows unranked, per-gate fail Counter, n evaluated)."""
    rows, fails, n_eval = [], Counter(), 0
    for m, rb in zip(members, rs_best):
        if not m.get("listable", True):
            continue                                 # in the RS pool only (an ETF, a leveraged fund ...): never listed
        if not m["history"]:
            fails["history"] += 1
            continue
        bars, cidx = m["bars"], m["cidx"]
        D = len(bars) - 1
        try:
            g = bv.v1_gates(bars, D, rs_best=rb, cidx=cidx)
        except Exception as e:  # one name's odd bars must not blank the night; counted + logged
            fails["gate_error"] += 1
            logger.warning(f"breakout_v1_list: gates {m['ticker']} failed: {type(e).__name__}: {e}")
            continue
        n_eval += 1
        for k in g["failed"]:
            fails[k] += 1
        if not g["ok"]:
            continue
        gates = {k: v for k, v in g.items() if k != "pole_idx"}
        rows.append({"scan_date": today, "ticker": m["ticker"], "level": float(g["level"]),
                     "vol_bar": float(g["vol_bar"]), "adr20": g["adr20"], "rs_best": float(rb), "close": g["close"],
                     "security_type": m["security_type"], "gates": _json_safe(gates)})
    return rows, fails, n_eval


def rank_rows(rows: list) -> list:
    """list_rank 1 = the highest rs_best (ties: ticker order), in place; returns the ranked list."""
    rows.sort(key=lambda r: (-r["rs_best"], r["ticker"]))
    for k, r in enumerate(rows, 1):
        r["list_rank"] = k
    return rows


def format_list_message(today: date, rows: list) -> Optional[str]:
    """The ONE Telegram message for a night's list, paper-prefixed (the paper chat); None for an empty list."""
    if not rows:
        return None
    from agents.market_intelligence.constants import mode_prefix
    shown = rows[:MESSAGE_MAX_NAMES]
    lines = [f"{'TICKER':6s} {'LEVEL':>10s} {'RS':>5s}"]
    for r in shown:
        lines.append(f"{r['ticker']:6s} {r['level']:>10.2f} {r['rs_best']:>5.1f}")
    more = f"\n…and {len(rows) - len(shown)} more (mi_breakout_v1_list)" if len(rows) > len(shown) else ""
    n = len(rows)
    return (f"{mode_prefix('paper')}*Breakout v1 — watch list for the next session* ({today.isoformat()}, "
            f"{n} name{'s' if n != 1 else ''})\n"
            f"A name breaks out when it trades above its level on at least 1.2× its 50-day volume. "
            f"No orders are placed (list and grades only).\n"
            "```\n" + "\n".join(lines) + "\n```" + more +
            "\nGrade one: `/bgrade TICKER A+|A|B|C|skip [note]` · `/bgrade` lists the ungraded")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The job
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _new_out(today: date) -> dict:
    return {"date": today.isoformat(), "skipped": None, "timed_out": False, "error": None,
            "prefilter_tickers": 0, "bad_bars": 0, "universe_n": 0, "listable_n": 0, "evaluated": 0, "passing": 0, "written": 0,
            "counts": {}, "gate_fails": {}, "funds_kept": 0, "funds_excluded": 0, "funds_excluded_no_name": 0,
            "fund_kept_tickers": [], "fund_excluded_tickers": {}, "message": "not_needed", "wall_s": 0.0}


async def _run(today: date, out: dict) -> list:
    cal = await cb_get_calendar(today, CALENDAR_SESSIONS)
    if not cal or cal[-1] != today:
        out["skipped"] = "no_spy_bar_for_today"
        return []
    cal_index = {d: i for i, d in enumerate(cal)}
    n = len(cal)
    start = cal[max(0, n - HISTORY_SESSIONS)]
    liq_start = cal[max(0, n - cb.DOLLAR_VOL_WINDOW)]
    rows = await cb_get_universe_bars(today, start, liq_start, min_price=bv.MIN_PRICE,
                                      prefilter_dollar_vol=PREFILTER_DOLLAR_VOL)
    tickers = sorted({r[0] for r in rows})
    out["prefilter_tickers"] = len(tickers)
    types = await bv1_get_security_types_named(tickers)
    unapplied = {s["ticker"] for s in await get_unapplied_splits(start, upto=today)}
    series, sstats = await asyncio.to_thread(build_series, rows, cal_index)
    del rows
    out["bad_bars"] = sstats.get("bad_bars", 0)
    today_ci = cal_index[today]

    members, counts, fund_kept, fund_excl = [], Counter(), [], {}
    items = list(series.items())
    for lo in range(0, len(items), SCAN_CHUNK):
        part = await asyncio.to_thread(scan_members, dict(items[lo:lo + SCAN_CHUNK]), today_ci=today_ci,
                                       types=types, unapplied=unapplied)
        members.extend(part["members"])
        counts.update(part["counts"])
        fund_kept.extend(part["fund_kept"])
        for k, v in part["fund_excluded"].items():
            fund_excl.setdefault(k, []).extend(v)
    out["counts"] = dict(counts)
    out["universe_n"] = len(members)                 # the RS pool (every type at the floors)
    out["listable_n"] = sum(1 for m in members if m["listable"])
    out["funds_kept"] = len(fund_kept)
    out["funds_excluded"] = sum(len(v) for v in fund_excl.values())
    out["funds_excluded_no_name"] = len(fund_excl.get("fund_no_name", []))
    out["fund_kept_tickers"] = sorted(fund_kept)[:FUND_EXCLUDED_LIST_MAX]
    out["fund_excluded_tickers"] = {k: sorted(v)[:FUND_EXCLUDED_LIST_MAX] for k, v in fund_excl.items()}

    rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                 [m["r126"] for m in members], [None] * len(members))
    list_rows, fails, n_eval = [], Counter(), 0
    for lo in range(0, len(members), SCAN_CHUNK):
        r_, f_, e_ = await asyncio.to_thread(evaluate_members, members[lo:lo + SCAN_CHUNK],
                                             rs_best[lo:lo + SCAN_CHUNK], today)
        list_rows.extend(r_)
        fails.update(f_)
        n_eval += e_
    rank_rows(list_rows)
    out["evaluated"], out["passing"], out["gate_fails"] = n_eval, len(list_rows), dict(fails)
    out["written"] = await bv1_replace_list(today, list_rows)
    out["tickers"] = [r["ticker"] for r in list_rows]
    return list_rows


async def run_breakout_v1_list(today: Optional[date] = None) -> dict:
    """The nightly job body (17:55 ET mon-fri). Returns the run summary (also the audit row's detail)."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    out = _new_out(today)
    t0 = time.monotonic()
    first_exc: Optional[BaseException] = None
    rows: list = []
    try:
        rows = await asyncio.wait_for(_run(today, out), timeout=BUDGET_S)
    except asyncio.TimeoutError:
        out["timed_out"] = True
        logger.error(f"breakout_v1_list: exceeded its {BUDGET_S}s budget - fail-open; the next night rebuilds its list")
        await log_audit_event(AUDIT_ERROR_EVENT, f"{today}: exceeded its {BUDGET_S}s budget (fail-open; no list written)",
                              json.dumps({"budget_s": BUDGET_S, "universe_n": out["universe_n"]}))
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        logger.error(f"breakout_v1_list: failed: {e}", exc_info=True)
        first_exc = e

    msg = format_list_message(today, rows) if (rows and not out["timed_out"] and first_exc is None) else None
    if msg:
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            sent = await send_telegram_message(msg)
            out["message"] = "sent" if sent else "send_failed"
            if not sent:
                logger.warning(f"breakout_v1_list: the list message for {today} was not delivered "
                               f"(send_telegram_message returned False; {len(rows)} name(s) are in the table)")
        except Exception as e:
            out["message"] = "send_failed"
            logger.warning(f"breakout_v1_list: the list message for {today} raised: {type(e).__name__}: {e}")
    out["wall_s"] = round(time.monotonic() - t0, 1)
    pub = _json_safe(out)
    if out["skipped"]:
        summary = f"{today}: skipped - {out['skipped']}"
    else:
        summary = (f"{today}: {out['passing']} name(s) on the list of {out['universe_n']} universe name(s) "
                   f"({out['evaluated']} evaluated); funds kept {out['funds_kept']}, excluded {out['funds_excluded']} "
                   f"({out['funds_excluded_no_name']} with no stored name); message {out['message']}; {out['wall_s']}s"
                   + (f"; TIMED OUT" if out["timed_out"] else "")
                   + (f"; ERROR: {out['error']}" if out["error"] else ""))
    try:
        await log_audit_event(AUDIT_RUN_EVENT, summary, json.dumps(pub))
    except Exception as ex:  # loud-ok: log_audit_event self-catches; logger fires here, the rows are already durable
        logger.warning(f"breakout_v1_list audit emit failed (non-fatal): {ex}")
    if first_exc is not None:
        raise first_exc
    return pub


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# /bgrade — his grade on a list name (a LABEL, never a gate). The handler is agent.py::_handle_bgrade_command.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
GRADES = {"a+": "A+", "a": "A", "b": "B", "c": "C", "skip": "skip"}
UNGRADED_NIGHTS = 5
BGRADE_USAGE = ("Usage: `/bgrade TICKER A+|A|B|C|skip [note]`\n"
                "Grades a name on the breakout v1 list (the latest night that listed it). "
                "A grade is a label — it never blocks or places anything.\n"
                "Bare `/bgrade` lists the ungraded names of the last 5 list nights.")


def parse_bgrade(text: str) -> Optional[dict]:
    """`/bgrade` -> {"list": True}; `/bgrade TICKER GRADE [note...]` -> {"list": False, ticker, grade, note};
    anything else (no grade, an unknown grade, a malformed ticker) -> None (the caller replies with the usage)."""
    toks = (text or "").strip().split()
    if toks and toks[0].startswith("/"):
        toks = toks[1:]
    if not toks:
        return {"list": True}
    ticker = toks[0].upper().lstrip("$")
    if not cb.UNIVERSE_TICKER_RE.fullmatch(ticker) or len(toks) < 2:
        return None
    grade = GRADES.get(toks[1].lower())
    if grade is None:
        return None
    note = " ".join(toks[2:]).strip() or None
    return {"list": False, "ticker": ticker, "grade": grade, "note": note}


def format_ungraded(rows: list) -> str:
    """The bare `/bgrade` reply: ungraded list names of the last 5 list nights, newest night first."""
    if not rows:
        return f"_No ungraded breakout v1 names in the last {UNGRADED_NIGHTS} list nights._"
    lines = [f"{'NIGHT':10s} {'TICKER':6s} {'LEVEL':>10s} {'RS':>5s}"]
    for r in rows:
        d = r["scan_date"].isoformat() if hasattr(r["scan_date"], "isoformat") else str(r["scan_date"])
        lines.append(f"{d:10s} {r['ticker']:6s} {float(r['level']):>10.2f} {float(r['rs_best']):>5.1f}")
    return (f"*Breakout v1 — {len(rows)} ungraded name{'s' if len(rows) != 1 else ''}* "
            f"(last {UNGRADED_NIGHTS} list nights)\n```\n" + "\n".join(lines) + "\n```\n"
            "`/bgrade TICKER A+|A|B|C|skip [note]`")
