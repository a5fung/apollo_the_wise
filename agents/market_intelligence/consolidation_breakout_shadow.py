"""#702 P6 — the Consolidation Breakout forward SHADOW recorder (no money, SILENT).

Qullamaggie's breakout as a SETUP in the consolidation family (CLAUDE.md "SETUP vs FAMILY"; owner doc
`docs/setups/consolidation_breakout.md`). The PURE core is `agents/market_intelligence/consolidation_breakout.py`
(`cb`) - every decision here (the C0 gates, the cells, the entries, the day-0 walk, the exits) is a call into
its public functions, never a re-implementation, so a forward row and a backtest row for the same night
(`scripts/probes/_cb_backtest/runner.py`) cannot drift apart. The plumbing the runner also has around the module -
universe membership, the cross-section, the one-trade-per-base stamping, the maturity label, the forward-window cut,
the per-arm walk - is `cb`'s (section 7 of the module), imported by both: there is no second copy to keep equal.

THE LINE. This module is a passive OBSERVER:
  - It writes ONLY `mi_consolidation_breakout_watch` / `_entry` / `_exit` / `_sic` (+ `mi_audit_log` through the
    shared `log_audit_event`). NEVER a trade table, never `mi_strategies`; it imports NOTHING from `broker/`
    itself (deploy gate 5j) and has no order path. (The pure core it calls, `cb`, imports exactly one broker module,
    `broker.exit_logic` - PURE exit-ladder math with no client and no trade-state I/O - under the sanctioned marker.)
  - It is read by NO grading / entry / sizing / ordering / safeguard path.
  - SILENT. No Telegram on any normal night. A crash propagates to `audit_wrap`, whose `notify_job_failure` is
    the one page (Telegram only on a job failure). A quiet night is not an alert.

THE NIGHT (17:48 ET mon-fri, after the 17:00 nightly pull; one job, one audit row). The steps run in this order,
WATCH FIRST (see `_run_steps`: tonight's watch list is the one output nothing re-creates, so a slow minute fetch
must not be able to starve it):
  a. TONIGHT'S WATCH LIST. Universe from `mi_daily_closes` + `mi_security_types` (`cb.universe_ok`, today's raw
     factor is 1), RS percentiles across the WHOLE universe, group RS from SIC-2 (`mi_consolidation_breakout_sic`,
     filled lazily, capped per night), the phases from SPY / QQQ, `cb.explain_watch` per name, `cb.cell_flags`
     per K. One row per passing name, all features as JSON.
  b. ENTRIES. For each of the last `ENTRY_LOOKBACK_SESSIONS` (3) sessions E, the previous session's watch rows
     whose pivot (per K in k5 / k10 / full / tl) E's daily high cleared become candidates; one trade per base
     (the runner's spec key + chain key) is stamped; E's regular-hours minutes come from
     `collector.get_alpaca_minute_bars_window`; `cb.entry_variants` + `cb.close_entry` write one row per variant,
     abstains and no-triggers included with a NAMED reason. The 3-session look-back recovers the ENTRIES of a
     break day the job missed or whose minute fetch RAISED (deferred, no row, written the next night - on the OLDEST
     look-back day that is counted and named instead, never written as a false `no_minutes`). It does NOT rebuild
     a missed night's WATCH LIST: a night the watch step did not write (a crash, a timeout, a skip with no SPY bar)
     leaves no D row, so the breakouts of the NEXT session are never seen - that gap is named in the audit row's
     `watch_n` and in docs/setups/consolidation_breakout.md (deviation 4), not silently recovered.
     A split between D and today is read BEFORE the breakout test (`split_scales`): the pivot is carried into the
     stored bars' units, so a forward and a reverse split are both judged on a like-for-like breakout and a real
     one abstains every variant by name (`split_after_watch`). "A split" is what the splits ingest RECORDED as having
     moved a stored bar (#704, `db.scale_from_split_rows`); a phantom it recorded is no split here at all.
  c. EXITS. Every filled entry with a non-mature arm is walked over EVERY arm in `cb.ARMS` from stored daily bars
     (full recompute each night: restart-safe), day-0 stop-outs booked once by `cb.day0_result_to_outcome`.
     A split after the break day that moved a stored bar makes the walk `unbookable` (the #667 HTF precedent: stored
     fills are raw, stored bars are retro-adjusted); a recorded phantom does not, and one not yet applied defers it.
  c2. EXITS, `pp` and `A` (#705 (c); `walk_pp_exits`). A separate step BESIDE the fifteen: the same exit table, its own work
     list and `pp_*` counters, so the registered arms' rows are untouched. `pp` is his carried exit (the day-3 third only in
     profit, the stop to cost after any third), `A` the control it replaced; the walk is `consolidation_breakout_pp` (a port
     of the runner's registered `pp`). The breakout day's facts (the +2R touch before the stop, the day's highest minute high)
     come from the ENTRY step, which stores them on the fill (`day0_pp`) from the minutes it already holds - this step
     fetches none. A fill recorded before the column existed carries none and is not walked.
  d. ONE audit row, `consolidation_breakout_shadow_run`.

The whole job runs under `BUDGET_S` and FAILS OPEN on timeout (an `..._error` audit row, no raise): every step is
idempotent, so the next night picks up where this one stopped. That `*_error` row is not silent: the audit
self-check reads it (`audit_invariants.check_audit_error_window`, any `*_error` event in 24 h, and
`system_audit`'s `audit_errors_per_day`) - a timeout is reported through the audit, not through a job-failure page.
"""
from __future__ import annotations

import asyncio
import bisect
import json
import logging
import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from itertools import groupby
from typing import Optional

import numpy as np

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence import consolidation_breakout_pp as ppx
from agents.market_intelligence.consolidation_breakout import (
    CELL_NAMES, KS, breaks_out, chain_bases, contiguous_tail, cross_section_one_date, forward_window, gap_fields,
    is_mature, is_test_symbol, resolve_sectype, stamp_base_chain, stamp_retrigger,
)
from agents.market_intelligence.db import (
    cb_get_calendar,
    cb_count_stale_open_entries,
    cb_get_candidate_history,
    cb_get_entry_state,
    cb_count_stale_pp_open_entries,
    cb_get_open_entries,
    cb_get_pp_open_entries,
    cb_get_security_types,
    cb_get_sic,
    cb_get_splits_after,
    cb_get_ticker_bars,
    cb_get_universe_bars,
    cb_get_watch_poles,
    cb_get_watch_rows,
    cb_upsert_entry_rows,
    cb_upsert_exit_rows,
    cb_upsert_sic_rows,
    cb_upsert_watch_rows,
    get_unapplied_splits,
    log_audit_event,
    scale_from_split_rows,
    scale_unmoved,
    split_row_factor,
)
from agents.market_intelligence.execution_client import get_data_feed_name
from shared.dates import _ET

logger = logging.getLogger(__name__)

JOB_ID = "consolidation_breakout_shadow"
AUDIT_RUN_EVENT = "consolidation_breakout_shadow_run"
AUDIT_ERROR_EVENT = "consolidation_breakout_shadow_error"
AUDIT_MINUTES_EVENT = "consolidation_breakout_shadow_minutes_unavailable"

BUDGET_S = 900                     # like scheduler._CONS_SCAN_BUDGET_S: fail open on timeout
ENTRY_LOOKBACK_SESSIONS = 3        # E = each of the last 3 sessions (catch-up + the no_minutes retry)
HISTORY_SESSIONS = 150             # bars loaded per universe name: >= cb.MIN_HISTORY (130) + margin
PHASE_SESSIONS = 120               # SPY / QQQ bars loaded for the phases (SMA50 + slope needs ~56)
CALENDAR_SESSIONS = 400            # the SPY calendar every bar is indexed against
# The SQL prefilter is a strict SUPERSET of `cb.universe_ok` (its floor sits BELOW the module's $10M median
# dollar volume, its price floor equals the module's): the module stays the authority, SQL only trims the wire.
PREFILTER_DOLLAR_VOL = 0.7 * cb.MIN_DOLLAR_VOL
SIC_CALLS_PER_NIGHT = 300          # the cap: a first night fills 300 of ~2,000 names, the rest over the next week
SIC_NONE_RETRY_DAYS = 30           # a `none` row (a 404, or no sic_code) is re-tried after this long
SIC_ERROR_STREAK_STOP = 5          # consecutive non-404 failures end the fill (a provider outage burns no more calls)
SIC_FLUSH_EVERY = 50
SCAN_CHUNK = 250                   # tickers per to_thread slice: cancellation lands between slices
WALK_TICKER_CHUNK = 200            # tickers per exit-walk slice: their bars are loaded, walked and freed together
MINUTE_BATCH = 25                  # tickers per Alpaca call: 25 x 390 minute bars = 9,750 fits alpaca-py's 10,000-bar page, so one call
MINUTE_TIMEOUT_S = 45.0
MINUTE_ERROR_STREAK_STOP = 3       # batches in a row that RAISED (each already retried once) = the feed is down: stop asking.
#                                    3 x MINUTE_BATCH = 75 tickers; the cost of giving up is unchanged (3 batches x 2 tries).
#                                    An EMPTY answer is not an error and never counts (#702: raise_on_error)
EXIT_CLOSES_BACK_DAYS = 100        # calendar days of pre-entry closes loaded for the SMA10/20 trails
EXIT_STALE_MARGIN_SESSIONS = 10    # past horizon + this many sessions a still-open entry is no longer re-walked

VARIANTS = cb.ENTRY_VARIANTS + ("close",)
RETRYABLE_REASON = "no_minutes"    # the only abstain a later night may overwrite (db.CB_ENTRY_UPSERT_SQL's WHERE)
SPLIT_REASON = "split_after_watch"
SPLIT_SCALE_TOL = 0.02             # an observed D-close ratio within 2% of 1.0 or of the split table's factor is that factor
ENTRY_UNRESOLVED_LIST_MAX = 50     # tickers named in the audit row for the split-unresolved sit-out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Pure plumbing - `cb`'s (section 7 of the module), shared with the runner; only the night-by-night form is here
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def stamp_forward(history: list, new: list, poles) -> None:
    """Stamp the NEW candidates of one breakout day against every earlier candidate of the same tickers - the
    night-by-night form of the runner's batch stamping. `history` + `new` are flat candidate dicts (ticker,
    pole_date iso, pole_ci, K, E iso, one bool per `CELL_NAMES`); `poles` = (ticker, pole_ci, pole_date) over
    every stored watch row of those tickers. The runner's functions are run over history + new together and
    the history's stamps are discarded (they were written the night they were new): E is the sort key, so a
    candidate is never stamped against a LATER one - which is why running this night by night equals running
    the batch over the whole set (tests/test_cb_shadow.py pins it on a multi-night sequence)."""
    combined = list(history) + list(new)
    stamp_retrigger(combined)
    stamp_base_chain(combined, chain_bases(poles))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Bars
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def build_series(rows: list, ci_of: dict) -> tuple:
    """`rows` = (ticker, trade_date, o, h, l, c, v) sorted by (ticker, date) -> ({ticker: (DailyBars, cidx)},
    stats). A row off the SPY calendar is dropped (it becomes a hole, which contiguity then refuses); a ticker
    whose bars are unusable (NULL, non-finite, not ascending) is dropped and counted."""
    out, stats = {}, Counter()
    for ticker, grp in groupby(rows, key=lambda r: r[0]):
        grp = list(grp)
        recs = [r for r in grp if r[1] in ci_of]
        stats["off_calendar_rows"] += len(grp) - len(recs)
        if not recs:
            stats["no_bars"] += 1
            continue
        try:
            bars = cb.daily_bars_from_arrays([r[1] for r in recs], [r[2] for r in recs], [r[3] for r in recs],
                                             [r[4] for r in recs], [r[5] for r in recs], [r[6] for r in recs])
        except (ValueError, TypeError):
            stats["bad_bars"] += 1
            continue
        out[ticker] = (bars, np.asarray([ci_of[d] for d in bars.dates], dtype=np.int64))
    return out, stats


def minute_bars_from_alpaca(series: list, e: date) -> tuple:
    """Alpaca `[{ts, open, high, low, close, volume}, ...]` -> (MinuteBars | None, state). `ts` is UTC-aware ->
    converted to ET (`.astimezone(_ET)`, the house idiom); only regular hours 09:30..15:59 of day `e` are kept
    (minute index 0..389); a duplicate minute keeps the LAST bar. state: 'ok' | 'no_minutes' | 'invalid'."""
    by_min: dict = {}
    for b in series or []:
        ts = b.get("ts")
        if ts is None:
            continue
        et = ts.astimezone(_ET)
        if et.date() != e:
            continue
        m = et.hour * 60 + et.minute - (9 * 60 + 30)
        if 0 <= m <= 389:
            by_min[m] = b
    if not by_min:
        return None, "no_minutes"
    ms = sorted(by_min)
    try:
        mb = cb.minute_bars_from_lists(ms, [by_min[m]["open"] for m in ms], [by_min[m]["high"] for m in ms],
                                       [by_min[m]["low"] for m in ms], [by_min[m]["close"] for m in ms],
                                       [by_min[m].get("volume", 0) for m in ms])
    except (ValueError, KeyError, TypeError):
        return None, "invalid"
    return mb, "ok"


def _json_safe(obj):
    """Plain JSON: numpy scalars -> python, non-finite floats -> None (jsonb has no NaN), dates -> ISO."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _py(v):
    """A numpy scalar as a python one (asyncpg rejects np.int64 for an INT column)."""
    return v.item() if isinstance(v, np.generic) else v


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Tonight's watch list
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def scan_universe(series: dict, *, today_ci: int, mi_types: dict, sic_types: dict, unapplied: set) -> dict:
    """The universe members and watch features for ONE night (the last bar of each series). The order of the
    checks is the runner's `scan_ticker`: test symbol -> `cb.universe_ok` -> 130 CONSECUTIVE sessions (a failure
    only here is counted 'history') -> RS inputs -> `cb.explain_watch`. Returns {'members': [...], 'counts'}.
    A ticker whose stored history crosses an UNAPPLIED split sits out (two price scales in one series)."""
    members, counts = [], Counter()
    for ticker, (bars, cidx) in series.items():
        i = len(bars) - 1
        if int(cidx[-1]) != today_ci:
            counts["no_bar_today"] += 1
            continue
        if is_test_symbol(ticker):
            counts["universe_fail"] += 1
            continue
        if ticker in unapplied:
            counts["split_unapplied"] += 1
            continue
        if not cb.universe_ok(bars, i, raw_factor=1.0, ticker=ticker,
                              security_type=resolve_sectype(ticker, mi_types, sic_types)):
            counts["universe_fail"] += 1
            continue
        if not contiguous_tail(cidx, cb.MIN_HISTORY):
            counts["history"] += 1
            continue
        try:
            r21, r63, r126 = cb.rs_returns(bars, i)
            feat, gate = cb.explain_watch(bars, i)
            if feat is not None:
                top = max(float(bars.o[feat["pole_idx"]]), float(bars.c[feat["pole_idx"]]))
                feat["pole_hi_over_oc"] = float(feat["pole_high"]) / top if top > 0 else None  # data flag, not a gate
        except Exception as e:  # one ticker's odd bars must not blank the whole night; counted + logged
            counts["scan_error"] += 1
            logger.warning(f"consolidation_breakout_shadow: scan {ticker} failed: {type(e).__name__}: {e}")
            continue
        counts[gate if feat is None else "pass"] += 1
        members.append({"ticker": ticker, "r21": r21, "r63": r63, "r126": r126, "feat": feat,
                        "dollar_vol": cb._dollar_vol_median(bars, i)})
    return {"members": members, "counts": counts}


def compute_phases(spy: Optional["cb.DailyBars"], qqq: Optional["cb.DailyBars"], cal_tail: list) -> dict:
    """The three phase flags at the LAST session. SPY and QQQ must carry exactly the calendar's last sessions
    (the join is by DATE, never by position); anything else -> all False and `gap` True (named in the audit)."""
    out = {"phase_qqq_10_20": False, "phase_qqq_10_20_s5": False, "phase_spy_qqq_50": False, "gap": True}
    if spy is None or qqq is None:
        return out
    need = len(cal_tail)
    if spy.dates[-need:] != cal_tail or qqq.dates[-need:] != cal_tail:
        return out
    j = len(qqq) - 1
    out.update(phase_qqq_10_20=cb.phase_qqq_10_20(qqq, j, cb.PHASE_SLOPE_PRIMARY),
               phase_qqq_10_20_s5=cb.phase_qqq_10_20(qqq, j, 5),
               phase_spy_qqq_50=cb.phase_spy_qqq_50(spy, qqq, len(spy) - 1, j), gap=False)
    return out


def finish_watch(members: list, sic2_of: dict, phases: dict, today: date) -> tuple:
    """Cross-section + cells -> (watch rows for the DB, summary). RS percentiles run over EVERY universe member
    (not only the watch names); `cell_flags` is `cb`'s, per K, plus the slope-5 C1 variant."""
    r21 = [m["r21"] for m in members]
    r63 = [m["r63"] for m in members]
    r126 = [m["r126"] for m in members]
    groups = [sic2_of.get(m["ticker"]) for m in members]
    rs_best, rs_all, grp, n_groups = cross_section_one_date(r21, r63, r126, groups)
    rows, cells_per_k = [], {k: Counter() for k in KS}
    for m, rb, ra, gp in zip(members, rs_best, rs_all, grp):
        feat = m["feat"]
        if feat is None:
            continue
        ctx = {"rs_best": rb, "rs_all": ra, "grp_pct": gp, "phase_qqq_10_20": phases["phase_qqq_10_20"],
               "phase_spy_qqq_50": phases["phase_spy_qqq_50"]}
        ctx5 = dict(ctx, phase_qqq_10_20=phases["phase_qqq_10_20_s5"])
        cells = {}
        for k in KS:
            fl = cb.cell_flags(feat, ctx, k=k)
            fl["C1_s5"] = cb.cell_flags(feat, ctx5, k=k)["C1"]
            cells[k] = {name: bool(v) for name, v in fl.items()}
            for name, v in cells[k].items():
                if v:
                    cells_per_k[k][name] += 1
        rows.append({
            "ticker": m["ticker"], "scan_date": today, "pole_date": date.fromisoformat(feat["pole_date"]),
            "pole_high": feat["pole_high"],
            "pivot_k5": feat["pivot_k5"], "pivot_k5_date": date.fromisoformat(feat["pivot_k5_date"]),
            "pivot_k10": feat["pivot_k10"], "pivot_k10_date": date.fromisoformat(feat["pivot_k10_date"]),
            "pivot_full": feat["pivot_full"], "pivot_full_date": date.fromisoformat(feat["pivot_full_date"]),
            "pivot_tl": feat["pivot_tl"],
            "pivot_tl_date": date.fromisoformat(feat["pivot_tl_date"]) if feat["pivot_tl_date"] else None,
            "adr20": feat["adr20"], "close": feat["close"], "rs_best": rb, "rs_all": ra, "grp_pct": gp,
            "phase_qqq_10_20": phases["phase_qqq_10_20"], "phase_qqq_10_20_s5": phases["phase_qqq_10_20_s5"],
            "phase_spy_qqq_50": phases["phase_spy_qqq_50"], "universe_n": len(members),
            # `i` and every `*_idx` are positions inside THIS night's 150-bar slice - meaningless a night
            # later, so they are not stored (the matching dates are).
            "features": _json_safe({k: v for k, v in feat.items() if k != "i" and not k.endswith("_idx")}),
            "cells": cells,
        })
    return rows, {"universe_n": len(members), "groups_ge10": n_groups,
                  "members_with_group": sum(1 for g in groups if g is not None),
                  "cells_per_k": {k: dict(v) for k, v in cells_per_k.items()}}


async def fill_sic(order: list, cap: int, out: dict) -> dict:
    """Fetch SIC for up to `cap` tickers of `order` (watch names first, then by dollar volume) from Polygon
    `/v3/reference/tickers/{t}`, persisting every `SIC_FLUSH_EVERY` rows. A 404 or an empty sic_code is a
    cached `none`; any other failure is NOT cached (tried again tomorrow); `SIC_ERROR_STREAK_STOP` in a row ends
    the fill. Returns {ticker: sic2} for what was fetched."""
    from agents.market_intelligence.collector import _polygon_get
    fetched, batch, calls, streak = {}, [], 0, 0
    for t in order:
        if calls >= cap:
            break
        calls += 1
        try:
            data = await _polygon_get(f"/v3/reference/tickers/{t}")
            streak = 0
            res = (data or {}).get("results") or {}
            sic = str(res.get("sic_code") or "").strip() or None
            row = {"ticker": t, "sic_code": sic, "sic2": cb.sic2(sic) if sic else None,
                   "sic_description": res.get("sic_description"), "ticker_type": res.get("type"),
                   "status": "ok" if sic else "none"}
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 404:
                streak = 0
                row = {"ticker": t, "sic_code": None, "sic2": None, "sic_description": None,
                       "ticker_type": None, "status": "none"}
            else:
                out["sic_errors"] += 1
                streak += 1
                logger.warning(f"consolidation_breakout_shadow: SIC fetch {t} failed: {type(e).__name__}: {e}")
                if streak >= SIC_ERROR_STREAK_STOP:
                    logger.error("consolidation_breakout_shadow: SIC fill stopped - "
                                 f"{streak} consecutive failures (provider down?)")
                    break
                continue
        batch.append(row)
        if row["sic2"]:
            fetched[t] = row["sic2"]
        if len(batch) >= SIC_FLUSH_EVERY:
            await cb_upsert_sic_rows(batch)
            batch = []
    if batch:
        await cb_upsert_sic_rows(batch)
    out["sic_fetched"] = calls - out["sic_errors"]
    return fetched


async def build_watch(today: date, cal: list, cal_index: dict, out: dict) -> None:
    """Step b: tonight's universe, cross-section, cells; one upserted watch row per passing name."""
    n = len(cal)
    start = cal[max(0, n - HISTORY_SESSIONS)]
    liq_start = cal[max(0, n - cb.DOLLAR_VOL_WINDOW)]
    rows = await cb_get_universe_bars(today, start, liq_start, min_price=cb.MIN_PRICE,
                                      prefilter_dollar_vol=PREFILTER_DOLLAR_VOL)
    tickers = sorted({r[0] for r in rows})
    out["prefilter_tickers"] = len(tickers)
    mi_types = await cb_get_security_types(tickers)
    sic_cache = await cb_get_sic(tickers)
    unapplied = {s["ticker"] for s in await get_unapplied_splits(start, upto=today)}
    series, sstats = await asyncio.to_thread(build_series, rows, cal_index)
    del rows
    out["bad_bars"] = sstats.get("bad_bars", 0)
    sic_types = {t: v["ticker_type"] for t, v in sic_cache.items() if v.get("ticker_type")}
    today_ci = cal_index[today]
    members, counts = [], Counter()
    items = list(series.items())
    for lo in range(0, len(items), SCAN_CHUNK):
        part = await asyncio.to_thread(scan_universe, dict(items[lo:lo + SCAN_CHUNK]), today_ci=today_ci,
                                       mi_types=mi_types, sic_types=sic_types, unapplied=unapplied)
        members.extend(part["members"])
        counts.update(part["counts"])
    out["gate_funnel"] = dict(counts)

    # group RS: SIC-2 from the cache, topped up (capped) from Polygon - watch names first, then by dollar volume
    now_et = datetime.now(_ET)       # only the AGE of a cached `none` row is compared - never a market date

    def _fresh(t: str) -> bool:
        v = sic_cache.get(t)
        if not v:
            return False
        if v["status"] == "ok":
            return True
        fa = v.get("fetched_at")
        return fa is not None and (now_et - fa.astimezone(_ET)).days < SIC_NONE_RETRY_DAYS
    need = [m for m in members if not _fresh(m["ticker"])]
    need.sort(key=lambda m: (m["feat"] is None, -m["dollar_vol"]))
    sic2_of = {t: v["sic2"] for t, v in sic_cache.items() if v["status"] == "ok" and v.get("sic2")}
    out["sic_fetched"] = 0
    if need:
        sic2_of.update(await fill_sic([m["ticker"] for m in need], SIC_CALLS_PER_NIGHT, out))
    out["sic_known"] = sum(1 for m in members if sic2_of.get(m["ticker"]))

    # phases from SPY / QQQ (joined by DATE)
    prow = await cb_get_ticker_bars(["SPY", "QQQ"], cal[max(0, n - PHASE_SESSIONS)], today)
    pseries, _ = await asyncio.to_thread(build_series, prow, cal_index)
    phases = compute_phases(pseries.get("SPY", (None,))[0], pseries.get("QQQ", (None,))[0],
                            cal[-(cb.SMA_LONG + 6):])
    out["phase_data_gap"] = bool(phases["gap"])
    out["phases"] = {k: phases[k] for k in ("phase_qqq_10_20", "phase_qqq_10_20_s5", "phase_spy_qqq_50")}

    watch_rows, summary = await asyncio.to_thread(finish_watch, members, sic2_of, phases, today)
    out.update(watch_n=len(watch_rows), **{k: v for k, v in summary.items() if k != "universe_n"})
    out["universe_n"] = summary["universe_n"]
    if watch_rows:
        await cb_upsert_watch_rows(watch_rows)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Entries
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def fetch_minutes(e: date, tickers: list, out: Optional[dict] = None) -> tuple:
    """({ticker: (MinuteBars | None, state)}, errored). The collector is asked with `raise_on_error=True`, so a
    RETURNED dict - `{}` included - means Alpaca ANSWERED and a ticker missing from it really had no bars
    (`no_minutes`, a retryable abstain); a RAISED call (timeout, API error, no credentials) is a failure and is never
    written as one.

    `errored` = the tickers to DEFER, whole batches: a batch that raised twice (each batch is asked once more), plus -
    once `MINUTE_ERROR_STREAK_STOP` batches in a row raised, which sets `out["minutes_feed_down"]` so the later
    look-back days of the same run do not ask again - the tickers never asked. A hanging feed costs a bounded few
    minutes instead of the whole budget (20 batches x 2 tries x 45 s). The caller writes NO row for an errored ticker
    on ANY look-back day, the oldest included. Batches that answered before a failure are kept."""
    from agents.market_intelligence import collector
    start = datetime(e.year, e.month, e.day, 9, 30, tzinfo=_ET)
    end = datetime(e.year, e.month, e.day, 16, 0, tzinfo=_ET)
    raw: dict = {}
    answered: set = set()
    errored: set = set()
    streak = 0
    for lo in range(0, len(tickers), MINUTE_BATCH):
        batch = tickers[lo:lo + MINUTE_BATCH]
        got, ok = {}, False
        for attempt in (1, 2):                         # a RAISED batch is asked once more; an empty answer never is
            try:
                got = await collector.get_alpaca_minute_bars_window(
                    batch, start, end, timeout_s=MINUTE_TIMEOUT_S, raise_on_error=True)
                ok = True
                break
            except Exception as ex:  # loud-ok: counted in `errored`, warned here, audited by the caller - never a row
                logger.warning(f"consolidation_breakout_shadow: minute fetch E={e} batch of {len(batch)} failed "
                               f"(attempt {attempt}): {type(ex).__name__}: {ex}")
        if not ok:
            errored.update(batch)
            streak += 1
            if streak >= MINUTE_ERROR_STREAK_STOP:
                errored.update(tickers[lo + MINUTE_BATCH:])
                if out is not None:
                    out["minutes_feed_down"] = True
                break
            continue
        streak = 0
        raw.update(got or {})
        answered.update(batch)
    return {t: minute_bars_from_alpaca(raw.get(t) or [], e) for t in tickers if t in answered}, errored


def moved_splits(rows: list) -> list:
    """The rows of `rows` that moved - or, still unapplied, may yet move - a stored bar: everything the ingest did
    not record as a PHANTOM split (`db.split_row_factor` 1.0; a 'skipped_no_data' row is NOT one - it may be a failed
    fetch of a real split, so it counts as moved). A phantom is ignored by the entry step, the exit guard, the HTF
    settler and the parabolic shadow ALIKE (#704)."""
    return [s for s in rows if split_row_factor(s) != 1.0]


def split_scale(window_splits: list, d_close_now, d_close_watch, watch_date: date) -> Optional[float]:
    """The factor that carries the WATCH NIGHT's pivot into the units of the bars stored NOW, for a ticker with a
    split executing in (D, today]; None when it cannot be told. `watch_date` = D.

    The pivot was stored raw on night D; the 17:00 pull has since retro-adjusted the stored bars for every APPLIED
    split, so E's stored bar and the pivot sit on two price scales. The factor is the ingest's OWN recorded verdict
    (#704: `db.scale_from_split_rows` - the product of the applied factors, 1.0 for a PHANTOM row, the table
    ratio for a 'skipped_no_data' one, None while any row is unapplied), no longer re-derived here. The data stays as this consumer's cross-check: D's
    stored close now over the close the watch row recorded that night must agree with it (within `SPLIT_SCALE_TOL`),
    else the reading is unexplained and returns None, never a guess. For a LEGACY row (written before the outcome
    column, so a phantom cannot be told from a real split) that cross-check is what degrades a pre-column phantom
    to "sits out" instead of a wrong rescale."""
    try:
        h = scale_from_split_rows([s for s in window_splits if s["execution_date"] > watch_date])
        obs = float(d_close_now) / float(d_close_watch)
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        return None
    if h is None or not (math.isfinite(obs) and math.isfinite(h) and obs > 0.0 and h > 0.0):
        return None
    return h if abs(obs / h - 1.0) <= SPLIT_SCALE_TOL else None


async def split_scales(sp: dict, watch: list, d: date, e: date, out: dict) -> dict:
    """{ticker: factor | None} for each watch ticker with a MOVED split in (D, today] (`sp`); a ticker without one is
    absent (factor 1). None = the ticker SITS OUT tonight's entry step, counted and named in the audit row: a split
    executed and NOT yet applied leaves the stored series on two scales (the same reason the watch step drops it),
    and an unexplained scale is never guessed. Both heal: the 3-session look-back retries the day once the split
    is applied."""
    if not sp:
        return {}
    d_close = {r[0]: r[5] for r in await cb_get_ticker_bars(sorted(sp), d, d) if r[1] == d and r[5] is not None}
    w_close = {w["ticker"]: w.get("close") for w in watch}
    scale = {t: split_scale(ss, d_close.get(t), w_close.get(t), d) for t, ss in sp.items()}
    bad = sorted(t for t, v in scale.items() if v is None)
    out["entry_split_rescaled"] += len(scale) - len(bad)
    if bad:
        out["entry_split_unresolved"] += len(bad)
        room = ENTRY_UNRESOLVED_LIST_MAX - len(out["entry_split_unresolved_tickers"])
        out["entry_split_unresolved_tickers"].extend(f"{t}:{e}" for t in bad[:max(room, 0)])
        logger.warning(f"consolidation_breakout_shadow: E={e}: {len(bad)} ticker(s) with a split in the window sit "
                       f"out the entry step (unapplied or unexplained scale): {bad[:10]}")
    return scale


def _candidate(w: dict, k: str, e: date, day: tuple, cal_index: dict, scale: float = 1.0) -> Optional[dict]:
    """One flat candidate (the shape the runner's stamping reads) or None when K did not break out. `scale` carries
    the stored pivot into the units of E's stored bar (`split_scale`; 1.0 for every ticker without a split in
    the window), so the breakout test and the gap compare like with like."""
    pivot = w.get(f"pivot_{k}")
    if pivot is not None and scale != 1.0:
        pivot = pivot * scale
    open_e, high_e, low_e, close_e = day
    if not breaks_out(high_e, pivot):
        return None
    cells = (w.get("cells") or {}).get(k) or {}
    gap_open, over1 = gap_fields(open_e, pivot, w["adr20"])
    c = {"ticker": w["ticker"], "D": w["scan_date"].isoformat(), "E": e.isoformat(), "K": k,
         "pole_date": w["pole_date"].isoformat(), "pole_ci": cal_index.get(w["pole_date"]),
         "pivot": pivot, "adr20": w["adr20"], "gap_open_pct": gap_open, "gap_over_1adr": over1,
         "open_E": open_e, "high_E": high_e, "low_E": low_e, "close_E": close_e, "cells": cells}
    for name in CELL_NAMES:
        c[name] = bool(cells.get(name))
    return c


def _entry_row(c: dict, variant: str, ent: dict, minutes_state: str, feed: Optional[str]) -> dict:
    d0 = ent.get("day0") or {}
    filled = ent["status"] == "filled"
    return {
        "ticker": c["ticker"], "watch_date": date.fromisoformat(c["D"]), "break_date": date.fromisoformat(c["E"]),
        "k": c["K"], "pole_date": date.fromisoformat(c["pole_date"]), "entry_variant": variant,
        "status": ent["status"], "reason": ent.get("reason"), "pivot": _py(c["pivot"]), "level": _py(ent.get("level")),
        "fill": _py(ent.get("fill")), "stop": _py(ent.get("stop")), "width_pct": _py(ent.get("width_pct")),
        "adr20": _py(c["adr20"]), "gap_pct": _py(c["gap_open_pct"]), "gap_over_1adr": bool(c["gap_over_1adr"]),
        "fill_minute": _py(ent.get("fill_minute")),
        "day0_stopped": bool(d0.get("stopped")) if filled else None,
        "day0_exit_price": _py(d0.get("exit_price")) if filled else None,
        "day0_exit_minute": _py(d0.get("exit_minute")) if filled else None,
        "retrigger": int(c["retrigger"]), "retrigger_chain": int(c["retrigger_chain"]), "base_id": c["base_id"],
        "cells": dict(c["cells"]),
        "first_cells": {n: int(c["first_" + n]) for n in CELL_NAMES},
        "first_chain_cells": {n: int(c["first_chain_" + n]) for n in CELL_NAMES},
        "minutes_state": minutes_state, "feed": feed,
        "day0_pp": None,                  # #705 (c): set by `_with_pp_facts` for a filled row, never by this builder
    }


def _abstain(reason: str) -> dict:
    return {"status": "abstain", "reason": reason, "fill": None, "stop": None, "fill_minute": None,
            "width_pct": None, "level": None, "day0": None}


def entry_rows_for(c: dict, minutes: Optional["cb.MinuteBars"], minutes_state: str, *, split: bool,
                   feed: Optional[str]) -> list:
    """The five variant rows of ONE candidate. A split between the watch night and now abstains EVERY variant
    (minutes are raw as of E, stored bars retro-adjusted - the two cannot be compared); otherwise the four
    minute variants are `cb.entry_variants` and the fifth is `cb.close_entry` off E's daily bar."""
    if split:
        return [_entry_row(c, v, _abstain(SPLIT_REASON), "n/a", None) for v in VARIANTS]
    ev = cb.entry_variants(minutes, pivot=c["pivot"], adr20=c["adr20"], day_high=c["high_E"], day_low=c["low_E"])
    rows = [_entry_row(c, v, ev[v], minutes_state, feed) for v in cb.ENTRY_VARIANTS]
    ce = cb.close_entry(c["close_E"], c["low_E"], c["pivot"], c["adr20"])
    rows.append(_entry_row(c, "close", ce, "n/a", None))
    for r in rows:
        _with_pp_facts(r, minutes)
    return rows


def _with_pp_facts(row: dict, minutes: Optional["cb.MinuteBars"]) -> None:
    """#705 (c): a FILLED row carries the breakout day's facts for the `pp` / `A` arms (`ppx.day0_facts`), computed once from the
    minutes the entry step already holds - the exit step has none. The `close` variant has no minute after its fill:
    `ppx.no_day0_facts`. Fail-soft: a failure leaves the column NULL (the pp step does not walk that fill; counted as
    `pp_day0_missing`), never a lost entry row. Every other column of the row is untouched."""
    if row["status"] != "filled":
        return
    try:
        if row["fill_minute"] is None:
            row["day0_pp"] = ppx.no_day0_facts()
        else:
            row["day0_pp"] = ppx.day0_facts(minutes, fill=row["fill"], stop=row["stop"], fill_minute=row["fill_minute"])
    except Exception as ex:  # loud-ok: logged here, counted by record_entries_for (pp_day0_missing) - the entry row still lands
        logger.error(f"consolidation_breakout_shadow: day0_pp facts failed for {row['ticker']} {row['break_date']} "
                     f"{row['k']}/{row['entry_variant']}: {type(ex).__name__}: {ex}")
        row["day0_pp"] = None


def _group_complete(rows: list) -> bool:
    """A candidate is DONE when all five variant rows exist and none is a retryable `no_minutes` abstain."""
    variants = {r["entry_variant"] for r in rows}
    return variants == set(VARIANTS) and not any(
        r["status"] == "abstain" and r["reason"] == RETRYABLE_REASON for r in rows)


async def record_entries_for(e: date, d: date, cal: list, cal_index: dict, out: dict, *, oldest: bool) -> None:
    watch = await cb_get_watch_rows(d)
    if not watch:
        out["entry_days_without_watch"].append(d.isoformat())      # a missed night, or a genuinely empty one: named, not rebuilt
        return
    tickers = sorted({w["ticker"] for w in watch})
    day = {}
    for r in await cb_get_ticker_bars(tickers, e, e):
        if r[1] == e and None not in r[2:6]:             # a bar with a NULL field is not a bar
            day[r[0]] = (float(r[2]), float(r[3]), float(r[4]), float(r[5]))
        else:
            out["entry_day_bar_unusable"] += 1
    state: dict = defaultdict(list)
    for r in await cb_get_entry_state(e):
        state[(r["ticker"], r["pole_date"].isoformat(), r["k"])].append(r)

    # SPLIT GUARD, read BEFORE the breakout test: the pivot was stored raw on night D, E's stored bar is split-
    # adjusted (the 17:00 pull), so the test must compare like with like - a forward split would otherwise hide
    # a real breakout (no candidate, no row), a reverse one invent it (every K, every variant). The pivot is carried
    # into the stored units (`split_scale`); a candidate that then breaks out abstains EVERY variant below
    # (`split_after_watch`: minutes are raw as traded on E, the stored bars are not).
    # #704: only a split that MOVED a stored bar counts. The ingest records a PHANTOM (Polygon reported a split that
    # never happened) as such; it left every bar where it was, so the pivot, the breakout test and the minutes all
    # compare like with like and the name is treated as the unsplit name it is - the same reading the exit guard,
    # the HTF settler and the parabolic shadow now take (`moved_splits`).
    sp = {t: rs for t, rs in (await cb_get_splits_after(tickers, d, cal[-1])).items() if moved_splits(rs)}
    scale = await split_scales(sp, watch, d, e, out)
    split_t = set(sp)

    cands = []
    for w in watch:
        if w["ticker"] not in day:
            continue                                  # no bar for E: the runner's 'no_next_bar' - no candidate
        sc = scale.get(w["ticker"], 1.0)
        if sc is None:
            continue                                  # a split nobody can scale tonight: sits out, counted (split_scales)
        for k in KS:
            c = _candidate(w, k, e, day[w["ticker"]], cal_index, scale=sc)
            if c is not None and not _group_complete(state.get((c["ticker"], c["pole_date"], c["K"]), [])):
                cands.append(c)
    out["entry_candidates"] += len(cands)
    if not cands:
        return
    ctick = sorted({c["ticker"] for c in cands})

    # one trade per base: stamp against every earlier candidate of these tickers
    hist_rows = await cb_get_candidate_history(ctick, e)
    history = []
    for h in hist_rows:
        cells = h.get("cells") or {}
        hc = {"ticker": h["ticker"], "pole_date": h["pole_date"].isoformat(), "K": h["k"],
              "E": h["break_date"].isoformat(), "pole_ci": cal_index.get(h["pole_date"])}
        for name in CELL_NAMES:
            hc[name] = bool(cells.get(name))
        history.append(hc)
    poles = [(t, cal_index[pd], pd.isoformat()) for t, pd in await cb_get_watch_poles(ctick, d)
             if pd in cal_index]
    usable = [c for c in cands if c["pole_ci"] is not None]
    out["entry_pole_off_calendar"] += len(cands) - len(usable)
    cands = usable
    stamp_forward([h for h in history if h["pole_ci"] is not None], cands, poles)

    # minutes for every candidate not split-abstained (`split_t`, above)
    need_min = sorted({c["ticker"] for c in cands if c["ticker"] not in split_t})
    mins, errored = ({}, set())
    if need_min:
        if out["minutes_feed_down"]:                      # an earlier day of THIS run found the feed down: do not ask again
            errored = set(need_min)
        else:
            mins, errored = await fetch_minutes(e, need_min, out)
    if errored:
        # A RAISED fetch writes NO row - on every look-back day, the oldest included: a row would be a false
        # `no_minutes` abstain for a day that has minutes. (A successful call with no bars for a ticker is NOT here:
        # that ticker is in `mins` as `no_minutes`, and a later night may overwrite it.) The look-back retries the
        # deferred candidates tomorrow - except on the OLDEST day, which no later night reads: counted and named.
        deferred = [c for c in cands if c["ticker"] in errored]
        cands = [c for c in cands if c["ticker"] not in errored]
        out["minutes_deferred"] += len(deferred)
        if oldest:
            out["minutes_deferred_oldest"] += len(deferred)
        if deferred:
            out["minutes_outage_days"].append(e.isoformat())
            await log_audit_event(
                AUDIT_MINUTES_EVENT,
                f"{e}: the Alpaca minute fetch raised for {len(errored)} of {len(need_min)} ticker(s); "
                f"{len(deferred)} candidate(s) deferred, no row written"
                + (" - E is the OLDEST look-back day, so no later night retries it" if oldest
                   else " to the next night's catch-up"))
        if not cands:
            return
    rows = []
    for c in cands:
        mb, mstate = mins.get(c["ticker"], (None, "no_minutes"))
        rows.extend(entry_rows_for(c, mb, mstate, split=c["ticker"] in split_t, feed=get_data_feed_name()))
    for r in rows:
        out["entry_rows"] += 1
        out["entry_status"][r["status"]] += 1
        if r["status"] == "filled":
            out["pp_day0_recorded" if r["day0_pp"] is not None else "pp_day0_missing"] += 1
        if r["status"] != "filled" and r["reason"]:
            out["entry_reasons"][r["reason"]] += 1
    await cb_upsert_entry_rows(rows)


async def record_entries(today: date, cal: list, cal_index: dict, out: dict) -> None:
    """Step a, over the last `ENTRY_LOOKBACK_SESSIONS` break days, oldest first (so a catch-up night's stamps
    are in the history of the night after it)."""
    sessions = cal[-ENTRY_LOOKBACK_SESSIONS:]
    for e in sessions:
        i = cal_index[e]
        if i == 0:
            continue
        await record_entries_for(e, cal[i - 1], cal, cal_index, out, oldest=(e == sessions[0]))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Exits
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _exit_row(entry_id: int, arm: str, res: dict, n_fwd: int, last_bar: date, note: str = "") -> dict:
    return {"entry_id": entry_id, "arm": arm, "status": res["status"],
            "realized_r": _py(res["realized_r"]), "pnl_adr": _py(res["pnl_adr"]),
            "sessions_held": _py(res["sessions_held"]), "events": _json_safe(res["events"]), "n_fwd": n_fwd,
            "mature": is_mature(res["status"], n_fwd), "reason": note or None, "last_bar_date": last_bar}


def walk_entry_rows(entry: dict, bars: "cb.DailyBars", cidx, ticker_splits: list, cache: Optional[dict] = None) -> list:
    """Exit rows for ONE filled entry over every arm in `cb.ARMS` that is NOT already final (`entry["mature_arms"]`,
    from the store - a mature row is never overwritten, so recomputing it would only burn time). The walk is the
    runner's: `cb.walk_arms` (a day-0 stop-out is booked ONCE by the module and is every arm's outcome; otherwise
    `walk_exit` per arm with closes_before = the closes through E and the forward window cut at a hole); this
    function only formats the rows. A split after E that MOVED a stored bar makes every open arm `unbookable`
    (mature: final, never re-walked); one the ingest recorded as a PHANTOM (#704) is ignored; one still UNAPPLIED
    returns NO rows (the walk is redone tomorrow). An arm that settled BEFORE the split keeps its (valid,
    pre-split) outcome.

    `cache` (one per chunk, shared by its entries) is a pure DEDUPE: the walk is a function of (ticker's bars, break
    day, fill, stop, day-0 result, adr20, arm), and the K x variant entries of one candidate often share all of them
    (k5 / k10 / full pivots coincide; every opening-range variant that breaks above the pivot fills at the same
    level), so an identical walk is computed once. Each entry still takes only ITS OWN non-final arms."""
    eid, e_date, adr20 = entry["id"], entry["break_date"], entry["adr20"]
    final = set(entry.get("mature_arms") or ())
    arms = {name: arm for name, arm in cb.ARMS.items() if name not in final}
    later = [s for s in ticker_splits if s["execution_date"] > e_date]
    if later:
        # #704: the same reading as the entry step, read once. A later split the ingest recorded as PHANTOM
        # moved no stored bar - the walk is as bookable as with no split at all. A REAL one still voids
        # (this consumer's policy: the fill and stop are raw, the stored bars are not). While a later split is still
        # UNAPPLIED nothing can be said either way: no row tonight, the full recompute tomorrow settles it.
        scale = scale_from_split_rows(later)
        if scale is None:
            return []
        if not scale_unmoved(scale):
            s = moved_splits(later)[0]
            reason = f"split_{s['split_from']}:{s['split_to']}_on_{s['execution_date']}_after_entry"
            return [{"entry_id": eid, "arm": name, "status": "unbookable", "realized_r": None, "pnl_adr": None,
                     "sessions_held": None, "events": [], "n_fwd": 0, "mature": True, "reason": reason,
                     "last_bar_date": None} for name in arms]
    e = bisect.bisect_left(bars.dates, e_date)
    if e >= len(bars) or bars.dates[e] != e_date:
        raise LookupError(f"break-day bar {e_date} missing for {entry['ticker']}")
    fwd, cut = forward_window(bars, cidx, e, cb.EXIT_HORIZON)
    n_fwd = len(fwd)
    last_bar = fwd.dates[-1] if n_fwd else e_date
    ent = {"status": "filled", "fill": entry["fill"], "stop": entry["stop"],
           "day0": {"stopped": bool(entry["day0_stopped"]), "exit_price": entry["day0_exit_price"],
                    "exit_minute": entry["day0_exit_minute"]}}
    note = "day0_stop" if ent["day0"]["stopped"] else ("fwd_hole" if cut else "")
    key = (entry["ticker"], e_date, entry["fill"], entry["stop"], ent["day0"]["stopped"], ent["day0"]["exit_price"],
           ent["day0"]["exit_minute"], adr20)
    cache = {} if cache is None else cache
    todo = {name: arm for name, arm in arms.items() if (key, name) not in cache}
    if todo:
        for name, res in cb.walk_arms(ent, closes_before=bars.c[:e + 1], fwd=fwd, adr20=adr20,
                                      horizon=cb.EXIT_HORIZON, arms=todo).items():
            cache[(key, name)] = res
    return [_exit_row(eid, name, cache[(key, name)], n_fwd, last_bar, note) for name in arms]


def _walk_chunk(entries: list, series: dict, splits: dict) -> tuple:
    rows, errors = [], []
    cache: dict = {}                          # identical walks of one chunk's entries are computed once (walk_entry_rows)
    for ent in entries:
        s = series.get(ent["ticker"])
        try:
            if s is None:
                raise LookupError(f"no bars for {ent['ticker']}")
            rows.extend(walk_entry_rows(ent, s[0], s[1], splits.get(ent["ticker"], []), cache))
        except Exception as ex:  # loud-ok: in-band reporting - the error is RETURNED and logger.error'd + counted by walk_exits
            errors.append((ent["id"], ent["ticker"], f"{type(ex).__name__}: {ex}"))
    return rows, errors


async def walk_exits(today: date, cal: list, cal_index: dict, out: dict) -> None:
    """Step c: every filled entry with a non-mature arm; each of its non-final arms is recomputed in full from
    stored bars (a final arm is not touched)."""
    # An entry older than the horizon + a margin that is STILL not mature can never become so (its forward
    # window was cut at a data hole): it stays a recorded 'degraded' mark and is no longer re-walked. The
    # bound is in the query, so the work list never reads the whole entry history; the stale ones are counted.
    stale_before = cal[max(0, len(cal) - (cb.EXIT_HORIZON + EXIT_STALE_MARGIN_SESSIONS))]
    entries = await cb_get_open_entries(len(cb.ARMS), stale_before)
    out["exit_entries_stale"] = await cb_count_stale_open_entries(len(cb.ARMS), stale_before)
    out["exit_entries_open"] = len(entries)
    if not entries:
        return
    by_ticker: dict = defaultdict(list)
    for e in entries:
        by_ticker[e["ticker"]].append(e)
    tickers = sorted(by_ticker)
    for lo in range(0, len(tickers), WALK_TICKER_CHUNK):          # bars are loaded per ticker chunk: bounded memory
        chunk_t = tickers[lo:lo + WALK_TICKER_CHUNK]
        chunk_e = [e for t in chunk_t for e in by_ticker[t]]
        first_break = min(e["break_date"] for e in chunk_e)
        rows = await cb_get_ticker_bars(chunk_t, first_break - timedelta(days=EXIT_CLOSES_BACK_DAYS), today)
        series, _ = await asyncio.to_thread(build_series, rows, cal_index)
        del rows
        splits = await cb_get_splits_after(chunk_t, first_break, today)
        rws, errs = await asyncio.to_thread(_walk_chunk, chunk_e, series, splits)
        for eid, tk, msg in errs:
            out["exit_errors"] += 1
            logger.error(f"consolidation_breakout_shadow: exit walk {tk} entry {eid} failed: {msg}")
        # An entry in the work list always has an open arm, so one that produced neither a row nor an error was
        # deferred by `walk_entry_rows` (a later split not yet applied): counted, redone tomorrow.
        out["exit_split_deferred"] += len({e["id"] for e in chunk_e} - {r["entry_id"] for r in rws}
                                          - {eid for eid, _tk, _m in errs})
        for r in rws:
            out["exit_status"][r["status"]] += 1
            out["exit_mature"] += int(r["mature"])
        if rws:
            await cb_upsert_exit_rows(rws)
            out["exit_rows"] += len(rws)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5b. Exits, the `pp` and `A` arms (#705 (c)) - a SEPARATE step beside the 15 `cb.ARMS`, so those rows, their work list and
#     their counters are not touched by it: its own work list, its own counters (`pp_*`), written to the same exit table
#     (`arm` is free text). The walk is `consolidation_breakout_pp` (a port of the runner's registered `pp`), fed the breakout
#     day's facts the ENTRY step stored on the fill (`day0_pp`) - this step never fetches a minute.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _day0_pp_of(entry: dict) -> dict:
    facts = entry.get("day0_pp")
    return json.loads(facts) if isinstance(facts, str) else facts


def walk_pp_entry_rows(entry: dict, bars: "cb.DailyBars", cidx, ticker_splits: list, cache: Optional[dict] = None) -> list:
    """Exit rows for ONE filled entry over the `pp` / `A` arms that are NOT already final (`entry["mature_arms"]`). Everything
    around the walk is `walk_entry_rows`' (the break-day bar, the forward window cut at a hole, the row format, the #704 split
    reading: a later split that MOVED a stored bar makes the open arms `unbookable`, a recorded phantom is ignored, one not yet
    applied returns NO rows); only the walk differs (`ppx.walk_pp_arms` from the stored day-0 facts)."""
    eid, e_date, adr20 = entry["id"], entry["break_date"], entry["adr20"]
    facts = _day0_pp_of(entry)
    final = set(entry.get("mature_arms") or ())
    names = [n for n in ppx.PP_ARMS if n not in final]
    later = [s for s in ticker_splits if s["execution_date"] > e_date]
    if later:
        scale = scale_from_split_rows(later)
        if scale is None:
            return []
        if not scale_unmoved(scale):
            s = moved_splits(later)[0]
            reason = f"split_{s['split_from']}:{s['split_to']}_on_{s['execution_date']}_after_entry"
            return [{"entry_id": eid, "arm": name, "status": "unbookable", "realized_r": None, "pnl_adr": None,
                     "sessions_held": None, "events": [], "n_fwd": 0, "mature": True, "reason": reason,
                     "last_bar_date": None} for name in names]
    e = bisect.bisect_left(bars.dates, e_date)
    if e >= len(bars) or bars.dates[e] != e_date:
        raise LookupError(f"break-day bar {e_date} missing for {entry['ticker']}")
    fwd, cut = forward_window(bars, cidx, e, cb.EXIT_HORIZON)
    n_fwd = len(fwd)
    last_bar = fwd.dates[-1] if n_fwd else e_date
    note = "day0_stop" if facts.get("stopped") else ("fwd_hole" if cut else "")
    key = (entry["ticker"], e_date, entry["fill"], entry["stop"], adr20, json.dumps(facts, sort_keys=True))
    cache = {} if cache is None else cache
    todo = [n for n in names if (key, n) not in cache]
    if todo:
        for name, res in ppx.walk_pp_arms({"fill": entry["fill"], "stop": entry["stop"]}, facts,
                                          closes_before=bars.c[:e + 1], fwd=fwd, adr20=adr20, arms=todo).items():
            cache[(key, name)] = res
    return [_exit_row(eid, name, cache[(key, name)], n_fwd, last_bar, note) for name in names]


def _walk_pp_chunk(entries: list, series: dict, splits: dict) -> tuple:
    rows, errors = [], []
    cache: dict = {}
    for ent in entries:
        s = series.get(ent["ticker"])
        try:
            if s is None:
                raise LookupError(f"no bars for {ent['ticker']}")
            rows.extend(walk_pp_entry_rows(ent, s[0], s[1], splits.get(ent["ticker"], []), cache))
        except Exception as ex:  # loud-ok: in-band reporting - the error is RETURNED and logger.error'd + counted by walk_pp_exits
            errors.append((ent["id"], ent["ticker"], f"{type(ex).__name__}: {ex}"))
    return rows, errors


async def walk_pp_exits(today: date, cal: list, cal_index: dict, out: dict) -> None:
    """Step c2: every filled entry that carries `day0_pp` and has a non-final `pp` / `A` arm; each non-final arm is recomputed
    in full from stored bars (restart-safe; a final arm is not touched). Same staleness bound as `walk_exits`."""
    stale_before = cal[max(0, len(cal) - (cb.EXIT_HORIZON + EXIT_STALE_MARGIN_SESSIONS))]
    arms = list(ppx.PP_ARMS)
    entries = await cb_get_pp_open_entries(arms, stale_before)
    out["pp_entries_stale"] = await cb_count_stale_pp_open_entries(arms, stale_before)
    out["pp_entries_open"] = len(entries)
    if not entries:
        return
    by_ticker: dict = defaultdict(list)
    for e in entries:
        by_ticker[e["ticker"]].append(e)
    tickers = sorted(by_ticker)
    for lo in range(0, len(tickers), WALK_TICKER_CHUNK):
        chunk_t = tickers[lo:lo + WALK_TICKER_CHUNK]
        chunk_e = [e for t in chunk_t for e in by_ticker[t]]
        first_break = min(e["break_date"] for e in chunk_e)
        rows = await cb_get_ticker_bars(chunk_t, first_break - timedelta(days=EXIT_CLOSES_BACK_DAYS), today)
        series, _ = await asyncio.to_thread(build_series, rows, cal_index)
        del rows
        splits = await cb_get_splits_after(chunk_t, first_break, today)
        rws, errs = await asyncio.to_thread(_walk_pp_chunk, chunk_e, series, splits)
        for eid, tk, msg in errs:
            out["pp_exit_errors"] += 1
            logger.error(f"consolidation_breakout_shadow: pp exit walk {tk} entry {eid} failed: {msg}")
        out["pp_split_deferred"] += len({e["id"] for e in chunk_e} - {r["entry_id"] for r in rws}
                                        - {eid for eid, _tk, _m in errs})
        for r in rws:
            out["pp_exit_status"][r["status"]] += 1
            out["pp_exit_mature"] += int(r["mature"])
        if rws:
            await cb_upsert_exit_rows(rws)
            out["pp_exit_rows"] += len(rws)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The job
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _new_out(today: date) -> dict:
    return {"date": today.isoformat(), "skipped": None, "timed_out": False, "step_errors": [],
            "entry_candidates": 0, "entry_pole_off_calendar": 0, "entry_day_bar_unusable": 0,
            "entry_rows": 0, "entry_status": Counter(),
            "entry_reasons": Counter(), "minutes_deferred": 0, "minutes_deferred_oldest": 0, "minutes_outage_days": [], "minutes_feed_down": False,
            "entry_days_without_watch": [], "entry_split_rescaled": 0, "entry_split_unresolved": 0, "entry_split_unresolved_tickers": [],
            "watch_n": 0, "universe_n": 0, "prefilter_tickers": 0, "sic_errors": 0, "sic_fetched": 0,
            "sic_known": 0, "gate_funnel": {}, "cells_per_k": {}, "groups_ge10": 0, "members_with_group": 0,
            "phase_data_gap": None, "phases": {}, "bad_bars": 0, "exit_entries_open": 0,
            "exit_entries_stale": 0, "exit_split_deferred": 0, "exit_rows": 0,
            "exit_mature": 0, "exit_status": Counter(), "exit_errors": 0,
            "pp_day0_recorded": 0, "pp_day0_missing": 0, "pp_entries_open": 0, "pp_entries_stale": 0,
            "pp_split_deferred": 0, "pp_exit_rows": 0, "pp_exit_mature": 0, "pp_exit_status": Counter(),
            "pp_exit_errors": 0, "wall_s": 0.0}


async def _run_steps(today: date, out: dict) -> Optional[BaseException]:
    """The four steps (watch, entries, exits, exits_pp), each isolated: a step that crashes is recorded and the others still run. The FIRST
    failure is returned so the caller re-raises it AFTER the audit row - a crash still propagates to `audit_wrap`.

    ORDER: watch -> entries -> exits. Tonight's watch list is the ONE output with no catch-up (`build_watch`
    builds only tonight, so a night it did not write is never rebuilt, and the next session's breakouts then
    have no D row), while the entries are re-derived from the 3-session look-back and the exits are recomputed in
    full every night. So the step that cannot be redone runs first, and a slow or hanging minute fetch - which
    the time budget cuts off - can only delay work the next night does again. Nothing in the watch step reads
    the entries step: entries read the PREVIOUS sessions' watch rows (`scan_date <= D < today`)."""
    cal = await cb_get_calendar(today, CALENDAR_SESSIONS)
    if not cal or cal[-1] != today:
        out["skipped"] = "no_spy_bar_for_today"
        return None
    cal_index = {d: i for i, d in enumerate(cal)}
    first_exc: Optional[BaseException] = None
    for name, step in (("watch", build_watch), ("entries", record_entries), ("exits", walk_exits),
                       ("exits_pp", walk_pp_exits)):
        try:
            await step(today, cal, cal_index, out)
        except Exception as e:
            out["step_errors"].append(f"{name}: {type(e).__name__}: {e}")
            logger.error(f"consolidation_breakout_shadow: step '{name}' failed: {e}", exc_info=True)
            first_exc = first_exc or e
    return first_exc


def _public(out: dict) -> dict:
    return _json_safe({k: (dict(v) if isinstance(v, Counter) else v) for k, v in out.items()})


async def run_consolidation_breakout_shadow(today: Optional[date] = None) -> dict:
    """The nightly job body. Returns the run summary. Fails OPEN on the time budget; a step's crash is re-raised
    after the audit row so `audit_wrap` records the failure (and `notify_job_failure` is the one Telegram)."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    out = _new_out(today)
    t0 = time.monotonic()
    first_exc: Optional[BaseException] = None
    try:
        first_exc = await asyncio.wait_for(_run_steps(today, out), timeout=BUDGET_S)
    except asyncio.TimeoutError:
        out["timed_out"] = True
        logger.error(f"consolidation_breakout_shadow: exceeded its {BUDGET_S}s budget - fail-open; every step is "
                     f"idempotent, the next night continues")
        await log_audit_event(AUDIT_ERROR_EVENT,
                              f"{today}: exceeded its {BUDGET_S}s budget (fail-open; partial results kept)",
                              json.dumps({"budget_s": BUDGET_S, **{k: out[k] for k in ("watch_n", "entry_rows", "exit_rows")}}))
    out["wall_s"] = round(time.monotonic() - t0, 1)
    pub = _public(out)
    if out["skipped"]:
        summary = f"{today}: skipped - {out['skipped']}"
    else:
        summary = (f"{today}: {out['watch_n']} watch row(s) of {out['universe_n']} universe name(s); "
                   f"{out['entry_candidates']} breakout candidate(s) -> {out['entry_rows']} entry row(s) "
                   f"{dict(out['entry_status'])}; {out['exit_rows']} exit row(s) over {out['exit_entries_open']} "
                   f"open entr(ies), {out['exit_mature']} mature; pp/A {out['pp_exit_rows']} exit row(s) over "
                   f"{out['pp_entries_open']} open entr(ies); SIC +{out['sic_fetched']} "
                   f"({out['sic_known']} of {out['universe_n']} known); {out['wall_s']}s"
                   + (f"; STEP ERRORS: {out['step_errors']}" if out["step_errors"] else ""))
    try:
        await log_audit_event(AUDIT_RUN_EVENT, summary, json.dumps(pub))
    except Exception as ex:  # loud-ok: log_audit_event self-catches; logger fires here, the rows are already durable
        logger.warning(f"consolidation_breakout_shadow audit emit failed (non-fatal): {ex}")
    if first_exc is not None:
        raise first_exc
    return pub
