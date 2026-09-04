"""#624 (2026-09-04) — MAGNA53 LOW-CAP LANE, SHADOW ONLY: the nightly walker.

WHAT IT ANSWERS. For every lane signal `lowcap_lane.py` recorded (mi_lowcap_lane_signals —
the names under the $500M floor that cleared the lane's two free terms at a post-open scan
tick), reconstruct the CURRENT-era MAGNA53 entry FROM THAT ROW'S OWN TICK WALL-CLOCK and walk
the SAME live exit ladder, so the lane's expectancy — and above all its TAIL RATE (walks
>= 3R), the one number n=46 cannot pin to better than a factor of five — accrues on today's
population under today's bracket. Modelled on `gap_near_miss_replay.py` (the sibling that
replays "names rejected by one named floor"); every entry/exit primitive is REUSED from
`sustain_reject_replay.py` / `live_fill_counterfactuals.py`, never mirrored a sixth time.

THE THREE THINGS THE FOUR STUDIES COULD NOT SEE, recorded on every row:
  - `stop_pct_of_entry` — a $5-8 stock with a cent-wide first bar produces the two-cent-stop
    class (13 book rows removed for it; two of them worth more R than the whole book). Stored,
    surfaced at read time (the harness's 0.3% floor), never gated here.
  - `next_open_gap_pct` + `offering_flag` — the UNCY -9.97R overnight-collapse class (closed
    $7.70, opened $4.00): the next session's open against day-0's close on every walk that
    held past day 0, and whether an SEC 8-K Item 3.02 (unregistered equity sale) or any 424B
    (prospectus) was filed inside the hold. Small caps that spike on volume are exactly the
    offering population; n=46 cannot see a 1-in-100 event.
  - `submit_time_et` FROM THE TICK, never a fixed 09:31: #622 measured the 154-cohort at a
    09:36 detection and the sign flipped (+0.10R -> -0.18R). `window_out_of_orb` marks a tick
    at/after 09:45 (CLAUDE.md's own ORB rule) — recorded, never simulated.

DAY-0 MINUTE BARS. `mi_intraday_bars` is populated only for alerted/traded ticker-days and is
the siblings' ONLY price source — a never-alerted lane name has none. So the walker first
FETCHES the day's RTH minutes via `broker.alpaca_client.get_minute_bars_range` and persists
them with `persist_intraday_bars` (SIP, $0 under Algo Trader Plus; `_623_fetch_bars.py` did
this for 2,399 ticker-days), then walks off the table exactly like its siblings. Those two
wrappers are the walker's ONLY broker imports, each tagged `# exec-boundary-ok:`; no order
path, no trade-state table, no Alpaca trading client. A fetch that returns nothing is retried
for `live_fill_counterfactuals.GAP_RETRY_SESSIONS` nights before the row is written
`unscoreable` — never silently dropped.

SURVIVORSHIP — the #482/#593/#617 constraint, restated: a name still running when this walks
it is NOT dropped. Every row is written on the FIRST pass; a non-terminal walk writes
`outcome='open'` with a MARK, refreshed by the SAME guarded UPSERT
(`db.upsert_lowcap_lane_replay`, WHERE the EXISTING row's outcome = 'open') until it settles.

THE ERA STAMP. `admission_era_as_of(session_date)` records MAGNA53's admission stack in force
(the lane itself has NO switch row at shadow — it changes nothing about who MAGNA53 admits;
its row lands with the paper flip, which does). The WALK always uses
`rule_eras.exit_rules_as_of(today)` — the bracket AS IT EXISTS NOW — because the question is
"what does the CURRENT bracket pay on this lane"; `replay_exit_era` / `replay_exit_rules`
record which "current" a settled row used, so when #545 changes the exit every row can be
RE-WALKED from stored bars ($0) before it counts toward graduation (P8: 37% of the lane's
evidence outcomes ARE the current harvest's +0.33R scratch).

THE LINE — a passive OBSERVER:
  - ONE write target: `mi_lowcap_lane_replays` (plus `mi_audit_log` via `log_audit_event`
    and the `mi_intraday_bars` write-through of the canonical `persist_intraday_bars`,
    ON CONFLICT DO NOTHING — a price cache, read by nothing that decides).
  - NEVER writes mi_live_trades / mi_live_orders / mi_ep_alerts / mi_ep_scan_log / any column
    any live decision reads. Never submits, never sizes, never alerts. Read by NO grading /
    entry / sizing / ordering / safeguard path — the `_adapter_magna53_lowcap` promotion
    read and the `lowcap_lane_graduation_624` review are its only consumers.
  - Every walk is wrapped; a failure degrades to a counted error + an audit row.
    `run_lowcap_lane_replay` never raises. SILENT — no Telegram while evidence accrues.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence import rule_eras
from agents.market_intelligence import sustain_reject_replay as srr
from agents.market_intelligence.alert_rank_shadow import compute_atr14_prior
from agents.market_intelligence.backtester.filters import validate_orb_entry
from agents.market_intelligence.broker.alpaca_client import get_minute_bars_range  # exec-boundary-ok: market-DATA read only (StockHistoricalDataClient, paper creds, no trading client) — day-0 minutes for never-alerted lane names, the same wrapper the #306 path recorder uses; no order path, no trade state
from agents.market_intelligence.broker.alpaca_client import persist_intraday_bars  # exec-boundary-ok: the CANONICAL mi_intraday_bars writer (ON CONFLICT DO NOTHING price cache) — reused rather than a second copy of its INSERT; writes no trade-state table
from agents.market_intelligence.collector import get_sec_recent_filings
from agents.market_intelligence.db import (
    _f,
    get_daily_ohlc_range,
    get_intraday_bars_window,
    get_lowcap_lane_population,
    get_lowcap_lane_replay_existing,
    get_pool,
    log_audit_event,
    upsert_lowcap_lane_replay,
)
from agents.market_intelligence.live_fill_counterfactuals import (
    n_trading_days_back,
    pinned_target,
    walk_arm,
)

logger = logging.getLogger(__name__)

SETTLE_VERSION = "lcl_v1"
TARGET_R = 2.0                    # the +2R partial level, matching live_fill_counterfactuals.TARGET_R
TAIL_R = 3.0                      # the graduation gate counts walks >= 3R (4 of 46 on the evidence)
SPLIT_DIVERGENCE_ABS_PCT = 0.05   # daily-row open vs raw 09:30 intraday open tolerance (gap_near_miss precedent)
ATR_LOOKBACK_CAL_DAYS = 40        # calendar days read for the ATR-14-prior window (mirrors the siblings)
PRIOR_CLOSES_CAL_DAYS = 40        # live_fill_counterfactuals convention — the trail's window (#548)
WINDOW_TRADING_DAYS = 40          # how far back each nightly run looks for NEW / still-open signals
OFFERING_FORMS = ("8-K", "424B")  # collector.get_sec_recent_filings matches on startswith — 424B2/3/4/5 all count
OFFERING_8K_ITEMS = ("3.02",)     # Item 3.02: Unregistered Sales of Equity Securities


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def stop_pct_of_entry(entry: Optional[float], stop: Optional[float]) -> Optional[float]:
    """(entry - stop) / entry x 100 — the stop's width as a share of price. None without a
    valid frame (never fabricated)."""
    if not entry or entry <= 0 or stop is None:
        return None
    return round((entry - stop) / entry * 100.0, 4)


def next_open_gap_pct(day0_close: Optional[float],
                      sessions: list[tuple[date, Optional[dict]]]) -> Optional[float]:
    """The next session's OPEN vs day-0's close, in %. None when either side is unknown —
    the overnight tail is only stated when both prints exist."""
    if not day0_close or day0_close <= 0 or not sessions:
        return None
    _, bar = sessions[0]
    if not bar or bar.get("o") is None:
        return None
    return round((bar["o"] - day0_close) / day0_close * 100.0, 4)


def offering_from_filings(filings: list[dict], session_date: date,
                          through: date) -> tuple[bool, list[dict]]:
    """(flag, matched) from a `get_sec_recent_filings` result: any 424B*, or an 8-K whose
    items include 3.02, FILED inside [session_date, through]. Pure. ⚠ An empty `filings`
    list means "no matching filing" AND "the SEC fetch failed" — the collector returns [] on
    both; the flag is therefore False in either case and the column comment says so."""
    matched: list[dict] = []
    lo, hi = session_date.isoformat(), through.isoformat()
    for f in filings or []:
        form = str(f.get("form") or "")
        filed = str(f.get("filed") or "")
        if not (lo <= filed <= hi):
            continue
        items = str(f.get("items") or "")
        if form.startswith("424B") or (form.startswith("8-K")
                                       and any(it in items for it in OFFERING_8K_ITEMS)):
            matched.append({"form": form, "filed": filed, "items": items, "url": f.get("url")})
    return bool(matched), matched


def _tail_flags(r: Optional[float], prefix: str) -> dict[str, Optional[bool]]:
    if r is None:
        return {f"{prefix}meets_3r": None, f"{prefix}meets_4r": None, f"{prefix}meets_positive": None}
    return {f"{prefix}meets_3r": r >= TAIL_R, f"{prefix}meets_4r": r >= 4.0,
            f"{prefix}meets_positive": r > 0}


# ── Orchestration (DB reads; writes only mi_lowcap_lane_replays + audit) ───────────────


def _fresh_fields(sig: dict, admission_era: str, replay_exit_era: str, replay_exit_rules: dict,
                  replay_asof_date: date, settled_session: date) -> dict[str, Any]:
    return {
        "ticker": sig["ticker"], "session_date": sig["scan_date"], "signal_id": sig.get("signal_id"),
        "tick_wallclock_et": sig.get("tick_wallclock_et"),
        "submit_time_et": None, "window_out_of_orb": None,
        "orb_high": None, "orb_low": None, "atr14_prior": None, "atr14_prior_n": None,
        "orb_valid": None, "orb_skip_reason": None, "day0_bars_source": None,
        "entry_status": None, "entry_reason": None, "entry_price": None, "entry_minute": None,
        "stop_price": None, "stop_pct_of_entry": None, "target_price": None, "target_r": TARGET_R,
        "outcome": None, "final_reason": None, "realized_r": None, "realized_pct": None,
        "mark_r": None, "meets_3r": None, "meets_4r": None, "meets_positive": None,
        "mark_meets_3r": None, "mark_meets_4r": None, "mark_meets_positive": None,
        "partial_fired": None, "gap_through": None, "exit_session": None,
        "sessions_walked": None, "exits": [],
        "day0_close": None, "next_open_gap_pct": None, "offering_flag": None,
        "offering_forms": [], "offering_checked_through": None,
        "admission_era": admission_era, "replay_exit_era": replay_exit_era,
        "replay_exit_rules": replay_exit_rules, "replay_asof_date": replay_asof_date,
        "settle_version": SETTLE_VERSION, "settled_session": settled_session,
    }


async def _write(fields: dict, out: dict, label: str) -> bool:
    return await lfc.write_replay_row(
        fields, out, label,
        upsert=upsert_lowcap_lane_replay,
        error_event="lowcap_lane_replay_error",
    )


async def _day0_bars(conn, ticker: str, session_date: date) -> tuple[list[dict], Optional[str]]:
    """The session's stored RTH minutes (ET-normalised, complete bars only) — fetched from
    Alpaca and persisted first when the table has none for this never-alerted name."""
    start = datetime.combine(session_date, time(9, 30), tzinfo=_ET)
    end = datetime.combine(session_date, time(16, 0), tzinfo=_ET)

    def _norm(bars):
        return [{**b, "m": b["m"].astimezone(_ET) if isinstance(b["m"], datetime) else b["m"]}
                for b in bars if None not in (b["o"], b["h"], b["l"], b["c"])]

    bars = _norm(await get_intraday_bars_window(conn, ticker, start, end))
    if bars:
        return bars, "stored"
    fetched = await get_minute_bars_range(ticker, start, end)
    if not fetched:
        return [], None
    await persist_intraday_bars(ticker, fetched)
    bars = _norm(await get_intraday_bars_window(conn, ticker, start, end))
    if bars:
        return bars, "fetched_alpaca"
    # persisted but not readable back on this connection — walk the fetched bars directly
    # rather than lose the night (the write-through is fire-and-forget by contract).
    bars = _norm([{"m": b["t_et"], "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"]}
                  for b in fetched])
    return bars, "fetched_alpaca"


async def _offering(ticker: str, session_date: date, through: date,
                    run_date: date) -> tuple[bool, list[dict]]:
    """SEC filings inside the hold. `lookback_days` is anchored to et_today() inside the
    collector, so it is widened from the session date; the window is then post-filtered."""
    lookback = max(1, (run_date - session_date).days + 2)
    try:
        filings = await get_sec_recent_filings(
            ticker, forms=OFFERING_FORMS, lookback_days=lookback, max_filings=12, want_text=False)
    except Exception as e:  # loud-ok: the collector already returns [] on failure; belt + braces — flag stays False, forms empty
        logger.warning(f"#624 offering check failed for {ticker}: {e}")
        filings = []
    return offering_from_filings(filings, session_date, through)


async def _record_one_signal(conn, sig: dict, last_session: date, run_date: date,
                             out: dict) -> None:
    ticker, session_date = sig["ticker"], sig["scan_date"]
    label = f"{ticker} {session_date.isoformat()}"
    out["candidates"] += 1

    admission_era = rule_eras.admission_era_as_of(session_date)
    replay_exit_rules = rule_eras.exit_rules_as_of(run_date)
    replay_exit_era = rule_eras.exit_era_label(run_date)
    fields = _fresh_fields(sig, admission_era, replay_exit_era, replay_exit_rules,
                           run_date, last_session)

    try:
        tick = sig.get("tick_wallclock_et")
        if not isinstance(tick, datetime):
            fields.update(entry_status="no_tick_wallclock", outcome="unscoreable",
                          final_reason="no_tick_wallclock")
            await _write(fields, out, label)
            return
        submit, out_of_orb = srr.submit_time_and_window(tick.astimezone(_ET))
        fields.update(submit_time_et=submit, window_out_of_orb=out_of_orb)
        if out_of_orb:
            fields.update(entry_status="window_out_of_orb", outcome="no_trade",
                          final_reason="window_out_of_orb")
            await _write(fields, out, label)
            return

        sessions = await lfc._assemble_sessions(conn, ticker, session_date, last_session)

        prior_daily = await get_daily_ohlc_range(
            conn, ticker, session_date - timedelta(days=ATR_LOOKBACK_CAL_DAYS), session_date)
        day0_row = next((r for r in prior_daily if r.get("trade_date") == session_date), None)
        prior_daily = [r for r in prior_daily if r.get("trade_date") != session_date]
        prior_hlc = [(_f(r.get("high_price")), _f(r.get("low_price")), _f(r.get("close")))
                     for r in prior_daily]
        prior_hlc = [t for t in prior_hlc if all(v is not None for v in t)]
        atr14 = compute_atr14_prior(prior_hlc)
        fields.update(atr14_prior=atr14, atr14_prior_n=len(prior_hlc))
        prior_cut = session_date - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
        prior_closes = [float(r["close"]) for r in prior_daily
                        if r.get("close") is not None and r["trade_date"] >= prior_cut]

        bars0, bars_source = await _day0_bars(conn, ticker, session_date)
        fields["day0_bars_source"] = bars_source
        if not bars0:
            # a genuine DATA GAP — retried like the siblings' forward-session gap, then unscoreable
            stale = len(lfc._trading_days(session_date + timedelta(days=1), last_session)) >= lfc.GAP_RETRY_SESSIONS
            if not stale:
                out["pending"] += 1
                return
            fields.update(entry_status="no_day0_minute_bars", outcome="unscoreable",
                          final_reason="no_day0_minute_bars")
            await _write(fields, out, label)
            return

        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if orb is None:
            fields.update(entry_status="no_930_bar_for_orb", outcome="unscoreable",
                          final_reason="no_930_bar_for_orb")
            await _write(fields, out, label)
            return
        orb_high, orb_low = orb["h"], orb["l"]
        fields.update(orb_high=orb_high, orb_low=orb_low)
        day0_close = _f(day0_row.get("close")) if day0_row else bars0[-1]["c"]
        fields["day0_close"] = day0_close

        # SPLIT-ADJUSTMENT GUARD (the gap_near_miss precedent — mi_daily_closes is rewritten
        # split-adjusted after a LATER reverse split; the intraday table never is).
        daily_open = _f(day0_row.get("open_price")) if day0_row else None
        if daily_open and orb["o"] and abs(daily_open / orb["o"] - 1) > SPLIT_DIVERGENCE_ABS_PCT:
            fields.update(entry_status="daily_row_split_adjusted", outcome="unscoreable",
                          final_reason="daily_row_split_adjusted")
            await _write(fields, out, label)
            return

        ok, skip = validate_orb_entry(orb_high, orb_low, atr14)
        fields.update(orb_valid=ok, orb_skip_reason=skip)
        if not ok:
            fields.update(entry_status="orb_invalid", outcome="no_trade", final_reason=skip)
            await _write(fields, out, label)
            return

        cancel = srr.entry_cancel_asof(run_date)
        fill = srr.entry_walk(bars0, orb_high, submit, cancel)
        fields.update(entry_status=fill["status"], entry_reason=fill.get("reason"))
        if fill["status"] != "filled":
            fields.update(outcome="unscoreable" if fill["status"] == "abstain" else "no_trade",
                          final_reason=fill.get("reason"))
            await _write(fields, out, label)
            return

        entry_px = fill["px"]
        fields.update(entry_price=entry_px, entry_minute=fill["minute"])
        stop = srr.current_era_stop(replay_exit_rules["stop_mode"], orb_high, orb_low)
        risk = entry_px - stop
        if risk <= 0:
            fields.update(outcome="unscoreable", final_reason="nonpositive_risk_per_share")
            await _write(fields, out, label)
            return
        fields["stop_price"] = stop
        fields["stop_pct_of_entry"] = stop_pct_of_entry(entry_px, stop)
        target = (pinned_target(entry_px, orb_low, TARGET_R)
                  if replay_exit_rules["intraday_partial_r"] else None)
        fields["target_price"] = target

        fill_idx = next(i for i, b in enumerate(bars0) if b["m"] == fill["minute"])

        res = walk_arm(entry=entry_px, stop=stop, target=target, day0_bars=bars0,
                       fill_idx=fill_idx, sessions=sessions, prior_closes=prior_closes,
                       harvest="live_ladder", fill_day=session_date,
                       breakeven_at_partial=bool(replay_exit_rules["breakeven_at_partial"]),
                       trail_prior_closes=bool(replay_exit_rules["trail_prior_closes"]),
                       ladder_partial=bool(replay_exit_rules["ladder_partial"]))
        status = res["status"]

        held_past_day0 = res.get("exit_session") != 0
        if held_past_day0:
            fields["next_open_gap_pct"] = next_open_gap_pct(day0_close, sessions)

        if status == "pending":
            gap = res.get("pending_at")
            if gap is not None:
                stale = len(lfc._trading_days(gap + timedelta(days=1), last_session)) >= lfc.GAP_RETRY_SESSIONS
                if not stale:
                    out["pending"] += 1
                    return
                fields.update(outcome="unscoreable", final_reason=res.get("reason"))
                await _write(fields, out, label)
                return
            # genuinely still OPEN — written now (survivorship), refreshed until it settles.
            mark = srr.mark_pnl_per_share(res, bars0, sessions, entry_px)
            fields.update(
                outcome="open", final_reason=res.get("reason"),
                partial_fired=res.get("partial_fired"), gap_through=res.get("gap_through"),
                sessions_walked=res.get("sessions_walked"), exits=res.get("exits") or [])
            if mark is not None:
                fields["mark_r"] = mark / risk
                fields.update(_tail_flags(fields["mark_r"], "mark_"))
            flag, forms = await _offering(ticker, session_date, last_session, run_date)
            fields.update(offering_flag=flag, offering_forms=forms,
                          offering_checked_through=last_session)
            await _write(fields, out, label)
            return

        fields.update(
            partial_fired=res.get("partial_fired"), gap_through=res.get("gap_through"),
            exit_session=res.get("exit_session"), sessions_walked=res.get("sessions_walked"),
            exits=res.get("exits") or [], final_reason=res.get("final_reason") or res.get("reason"))
        if status == "settled":
            pnl = res.get("pnl_per_share")
            fields["outcome"] = "settled"
            if pnl is not None:
                fields["realized_r"] = pnl / risk
                fields["realized_pct"] = pnl / entry_px * 100.0
                fields.update(_tail_flags(fields["realized_r"], ""))
        elif status == "horizon":
            fields["outcome"] = "horizon"
            mark = res.get("mark_pnl_per_share")
            if mark is not None:
                fields["mark_r"] = mark / risk
                fields.update(_tail_flags(fields["mark_r"], "mark_"))
        else:  # abstain — a genuine day-0 order-ambiguity (same-bar stop+target, etc.)
            fields["outcome"] = "unscoreable"
        if held_past_day0 and fields["outcome"] in ("settled", "horizon"):
            exit_idx = res.get("exit_session") or len(sessions)
            through = sessions[exit_idx - 1][0] if 0 < exit_idx <= len(sessions) else last_session
            flag, forms = await _offering(ticker, session_date, through, run_date)
            fields.update(offering_flag=flag, offering_forms=forms, offering_checked_through=through)
        await _write(fields, out, label)
    except Exception as e:  # loud-ok: one signal's failure is counted; the others proceed
        out["errors"] += 1
        await log_audit_event("lowcap_lane_replay_error", f"{label}: {type(e).__name__}: {e}")


async def run_lowcap_lane_replay(today: Optional[date] = None, *,
                                 now_et: Optional[datetime] = None) -> dict[str, int]:
    """Nightly entry point. NEVER raises: every failure is a counted error + an mi_audit_log
    row. Returns the run's counters."""
    now = now_et or datetime.now(_ET)
    today = today or now.date()
    out: dict[str, int] = {"population": 0, "candidates": 0, "written": 0, "settled": 0,
                           "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
                           "pending": 0, "errors": 0}
    try:
        last_session = lfc.last_settled_session(today, now)
        window_start = n_trading_days_back(last_session, WINDOW_TRADING_DAYS)
        rows = await get_lowcap_lane_population(window_start, last_session)
        existing = await get_lowcap_lane_replay_existing(window_start)
    except Exception as e:  # loud-ok: the run reports and ends; nothing live depends on it
        out["errors"] += 1
        await log_audit_event("lowcap_lane_replay_error", f"population query failed: {e}")
        return out
    out["population"] = len(rows)
    todo = [r for r in rows
            if existing.get((r["ticker"], r["scan_date"])) in (None, "open")]
    if todo:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                for row in todo:
                    try:
                        await _record_one_signal(conn, row, last_session, today, out)
                    except Exception as e:  # loud-ok: per-name isolation; counted + audited
                        out["errors"] += 1
                        await log_audit_event(
                            "lowcap_lane_replay_error",
                            f"{row.get('ticker')} {row.get('scan_date')}: "
                            f"{type(e).__name__}: {e}")
        except Exception as e:  # loud-ok: pool-level failure; counted + audited
            out["errors"] += 1
            await log_audit_event("lowcap_lane_replay_error", f"run failed: {e}")
    await log_audit_event(
        "lowcap_lane_replay_recorded",
        f"{out['population']} lane signal(s) in window, {len(todo)} candidate(s) processed: "
        f"{out['written']} written ({out['settled']} settled, {out['no_trade']} no_trade, "
        f"{out['unscoreable']} unscoreable, {out['open']} open, {out['horizon']} at horizon), "
        f"{out['pending']} pending, {out['errors']} error(s)")
    return out
