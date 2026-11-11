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
     of `mi_breakout_v1_list` (the night's rows replaced whole — idempotent), carrying its two order inputs
     (`breakout_v1.order_inputs`) and ranked by the ORDER SCORE over the night's whole list (`rank_rows`; the rebuilt
     rules his spec sign-off of 2026-11-02 named, `docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md` §2);
  5. ONE audit row `breakout_v1_list_run` (universe size, funds kept / excluded and why, names passing, per-gate fail
     counts, the message's fate);
  6. ONE paper-prefixed Telegram message: tonight's TOP 10 by the order score (ticker, level, score, rs_best) and
     the night's total count (the rebuilt list holds ~250 names a night — never 250 lines) — ONLY when the list is
     non-empty (an alert that says no action is noise). A failed send is logged and counted in the audit row.

THE LINE. A LIST and a GRADE only: this module writes `mi_breakout_v1_list` and `mi_audit_log` (through
`log_audit_event`), imports nothing from `broker/`, writes no trade table and no `mi_strategies` row, prepares no
order. No entry / sizing / order / safeguard path reads the list in phase 1.

Fails OPEN under `BUDGET_S` (a `breakout_v1_list_error` audit row, no raise; the next night rebuilds its own list);
a crash is re-raised AFTER the audit row so `audit_wrap`'s `notify_job_failure` is the one page.
Owner doc: docs/setups/consolidation_breakout.md (2026-10-29 "breakout v1 PHASE 1 BUILT"; 2026-11-02 the rebuilt
rules + the order score).
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
    BREAKOUT_V1_PAPER_TOGGLE,
    BREAKOUT_V1_PAPER_TOGGLE_ENV,
    bv1_get_security_types_named,
    bv1_replace_list,
    cb_get_calendar,
    cb_get_universe_bars,
    get_runtime_toggle,
    get_unapplied_splits,
    log_audit_event,
)

logger = logging.getLogger(__name__)

JOB_ID = "breakout_v1_list"
AUDIT_RUN_EVENT = "breakout_v1_list_run"
AUDIT_ERROR_EVENT = "breakout_v1_list_error"
BUDGET_S = 600                        # fail open past this (the shadow's pattern; a night is ~1 minute of work)
# Bars loaded per name: the 6-month move reads 126 highs, each against the lowest low of the 64 sessions up to it, so
# 189 sessions are needed for the research's full look-back (`breakout_v1.runup6m_at`; 150 shortened it), + margin.
# The EMA21 is seeded at the first loaded bar (its weight at D after 200 bars is ~1e-8).
HISTORY_SESSIONS = 200
CALENDAR_SESSIONS = 400
PREFILTER_DOLLAR_VOL = 0.7 * bv.MIN_DOLLAR_VOL
SCAN_CHUNK = 250                      # tickers per to_thread slice: cancellation lands between slices
FUND_EXCLUDED_LIST_MAX = 60           # fund tickers named in the audit row, per reason
MESSAGE_TOP_N = 10                    # the nightly message and bare /bgrade show the top 10 by the order score


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
        oi = bv.order_inputs(bars, D, g["adr20"])        # the two order-score inputs, bars <= D (passing names only)
        gates = {k: v for k, v in g.items() if k != "pole_idx"}
        gates["order_inputs"] = oi
        rows.append({"scan_date": today, "ticker": m["ticker"], "level": float(g["level"]),
                     "vol_bar": float(g["vol_bar"]), "adr20": g["adr20"], "rs_best": float(rb), "close": g["close"],
                     "security_type": m["security_type"], "runup6m_adr": oi["runup6m_adr"],
                     "spread10_adr": oi["spread10_adr"], "gates": _json_safe(gates)})
    return rows, fails, n_eval


def pct_rank(values: list, *, ascending: bool = True) -> list:
    """pandas `Series.rank(pct=True)` (method 'average') over the non-None values: rank 1..n (tied values share the
    mean of their positions) / n, where n = the count of non-None values; None stays None. `ascending=False` gives
    the LARGEST value rank 1, so its pct is 1/n and the smallest value's is 1.0 — the research's
    `rank(pct=True, ascending=False)` (33_rank_topn.py)."""
    idx = [i for i, x in enumerate(values) if x is not None]
    n = len(idx)
    out: list = [None] * len(values)
    if not n:
        return out
    order = sorted(idx, key=lambda i: values[i], reverse=not ascending)
    k = 0
    while k < n:
        j = k
        while j + 1 < n and values[order[j + 1]] == values[order[k]]:
            j += 1
        avg = float(sum(range(k + 1, j + 2))) / (j - k + 1)        # the 1-based positions k+1..j+1, averaged
        for t in range(k, j + 1):
            out[order[t]] = avg / n
        k = j + 1
    return out


def rank_rows(rows: list) -> list:
    """The night's ORDER (spec §2, `33_rank_topn.py`), in place over the night's WHOLE passing list; returns it ranked.
    p_run = the within-night percentile of `runup6m_adr` (bigger first), p_tight = of `spread10_adr` (tighter first),
    order_score = (p_run + p_tight) / 2; list_rank 1 = the highest score, ties by ticker (the research's
    method='first' on ticker-sorted rows). A row missing an input has no score and ranks after every scored row (by
    ticker). The score ORDERS the list; it never removes a name (his spec: as a cut it would lose most of
    Qullamaggie's buys). It is comparable only inside one night."""
    p_run = pct_rank([r.get("runup6m_adr") for r in rows], ascending=True)
    p_tight = pct_rank([r.get("spread10_adr") for r in rows], ascending=False)
    for r, a, b in zip(rows, p_run, p_tight):
        r["order_score"] = (a + b) / 2 if (a is not None and b is not None) else None
    rows.sort(key=lambda r: (r["order_score"] is None, -(r["order_score"] or 0.0), r["ticker"]))
    for k, r in enumerate(rows, 1):
        r["list_rank"] = k
    return rows


def _score_str(x) -> str:
    return "-" if x is None else f"{float(x):.2f}"


def format_list_message(today: date, rows: list) -> Optional[str]:
    """The ONE Telegram message for a night's list, paper-prefixed (the paper chat); None for an empty list. Shows the
    TOP `MESSAGE_TOP_N` by the order score (`rows` ranked by `rank_rows`) and the night's total count — the rebuilt
    list holds ~250 names a night, so the full list lives in `mi_breakout_v1_list`, never in the chat. It no longer
    names `/bgrade` (his word 2026-11-05: grades come from chart sheets shown in chat, not Telegram; #717 stage 2) —
    the command itself stays, as the catch-up path."""
    if not rows:
        return None
    from agents.market_intelligence.constants import mode_prefix
    shown = sorted(rows, key=lambda r: r.get("list_rank") or 10 ** 9)[:MESSAGE_TOP_N]
    lines = [f"{'#':>3s} {'TICKER':6s} {'LEVEL':>10s} {'SCORE':>5s} {'RS':>5s}"]
    for r in shown:
        lines.append(f"{r.get('list_rank') or 0:>3d} {r['ticker']:6s} {r['level']:>10.2f} "
                     f"{_score_str(r.get('order_score')):>5s} {r['rs_best']:>5.1f}")
    n = len(rows)
    more = f"\n…and {n - len(shown)} more (mi_breakout_v1_list)" if n > len(shown) else ""
    return (f"{mode_prefix('paper')}*Breakout v1 — watch list for the next session* ({today.isoformat()}, "
            f"{n} name{'s' if n != 1 else ''}; the top {len(shown)} by the order score)\n"
            f"A name breaks out when it trades above its level (the high of its range) on more than its average "
            f"volume of the last {bv.VOL_WINDOW} sessions. No order is placed from this message.\n"
            "```\n" + "\n".join(lines) + "\n```" + more)


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
    # His word 2026-11-10 ("I don't want to see these garbage charts again", after the first paper session bought
    # charts with no higher lows and no surfing average): the message goes out ONLY while breakout paper is on.
    # The list itself is still computed and written every night (the rebuild scores against it).
    if msg and not await get_runtime_toggle(BREAKOUT_V1_PAPER_TOGGLE, BREAKOUT_V1_PAPER_TOGGLE_ENV):
        out["message"] = "suppressed_paper_off"
        msg = None
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
                "Bare `/bgrade` shows the top 10 ungraded names by the order score (newest list night first) "
                "and how many of the last 5 list nights' names are ungraded.")


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
    """The bare `/bgrade` reply. `rows` = every ungraded list name of the last 5 list nights, newest night first and
    by list_rank inside a night (`db.bv1_ungraded`). At ~250 names a night that is ~1,250 rows, so the reply shows
    the TOP `MESSAGE_TOP_N`: the newest night's best-scored ungraded names (spilling to the night before when the
    newest has fewer than 10 left) plus the total ungraded count and the count per night. The order score compares
    names only within one night, so the newest night is read first."""
    if not rows:
        return f"_No ungraded breakout v1 names in the last {UNGRADED_NIGHTS} list nights._"

    def _d(r):
        return r["scan_date"].isoformat() if hasattr(r["scan_date"], "isoformat") else str(r["scan_date"])
    per_night: dict = {}
    for r in rows:
        per_night[_d(r)] = per_night.get(_d(r), 0) + 1
    shown = rows[:MESSAGE_TOP_N]
    lines = [f"{'NIGHT':10s} {'#':>3s} {'TICKER':6s} {'LEVEL':>10s} {'SCORE':>5s} {'RS':>5s}"]
    for r in shown:
        lines.append(f"{_d(r):10s} {int(r.get('list_rank') or 0):>3d} {r['ticker']:6s} {float(r['level']):>10.2f} "
                     f"{_score_str(r.get('order_score')):>5s} {float(r['rs_best']):>5.1f}")
    n = len(rows)
    nights = ", ".join(f"{d} {k}" for d, k in sorted(per_night.items(), reverse=True))
    return (f"*Breakout v1 — {n} ungraded name{'s' if n != 1 else ''}* (last {UNGRADED_NIGHTS} list nights: "
            f"{nights}); the top {len(shown)} by the order score:\n```\n" + "\n".join(lines) + "\n```\n"
            "`/bgrade TICKER A+|A|B|C|skip [note]`")
