"""2026-09-03 — #617 STEP 2: STANDING GAP-FLOOR NEAR-MISS REPLAY.

WHY (operator, #617 card): Step 1 (docs/analysis/617_universe_admission_recall_jun_aug_2026-09-03.md)
was a HAND-RUN scan that found ZERO names in the 7-9% open-gap band — the fixture's own
"7 excluded ≥10R winners" debt — that our own bracket would have paid ≥4R on across Jun-Aug
2026. That is a clean negative TODAY, but it was also a debt nobody looked at from April to
September because nothing made it look. This module ends that: it makes the SAME measurement
STANDING, so it reports itself every trading session instead of waiting for someone to
remember. The question it answers, continuously: *"is universe admission excluding names our
OWN bracket would have paid >=4R on?"*

SCOPE — DELIBERATELY NARROW (the #617 card, 2026-09-03). Only the near-miss band immediately
below the live gap floor: `[MIN_GAP_PCT - NEAR_MISS_BAND_WIDTH_PCT, MIN_GAP_PCT)` — 7-9% while
the floor sits at 9.0. Step 1 measured ~4-5 excluded names/session in this band across three
months, tractable nightly. **The 5-6% band is a DIFFERENT question and is NOT reviewed here** —
Step 1 found admitting 5-9% nearly TRIPLES the funnel (25 extra names/session) to recover 11
names across 3 months, at a cost of -229R. Do not widen this table's population to that band
without a new card; if MIN_GAP_PCT itself ever moves (THE LINE — operator-only, Step 3 of
#617), this band is defined RELATIVE to the live floor (imported, never restated — see the
import comment below), so the NEXT DEPLOY picks it up with no second manual update — never a
hardcoded copy silently going stale the way a second literal would. It does NOT move inside a
running process (Python binds a default argument once, at import — the identical cadence
`ep_detector.MIN_GAP_PCT` itself uses for its own env-var read), which matches the live floor's
own restart-only refresh exactly.

THE BUILD. For every (ticker, session) whose OPEN gap sat in the near-miss band and who
cleared every OTHER universe floor (ticker shape, security type, MIN_PREV_CLOSE,
MIN_PREV_DAY_VOLUME) but got NO scored `mi_ep_scan_log` row and NO live-source `mi_ep_alerts`
row that day — i.e. the gap floor alone kept it out, not a downstream filter (#545 Phase 2
already measured those) and not a real-time re-check admission (a name whose open missed but
whose intraday price crossed the floor and WAS scored/alerted is, correctly, not in this
population at all):
  1. Reconstruct the CURRENT-era MAGNA53 entry at 09:31 ET — the most optimistic detection
     time for a name the universe never admitted (Step 1's own assumption, so today's rate is
     comparable to Step 1's headline number). `entry_walk` / `entry_cancel_asof` /
     `current_era_stop` are REUSED from `sustain_reject_replay.py` (the closest sibling, built
     the same day) rather than mirrored a third time — production code importing production
     code is fine; only `scripts/` (offline-capture-only) may not be imported from here.
  2. If it would have filled, walk the SAME live exit ladder
     (`live_fill_counterfactuals.walk_arm` — REUSED, not reimplemented) under CURRENT-era
     rules (`rule_eras.exit_rules_as_of`), and store `realized_r` / `meets_4r` (>=4R, the P1
     real-EP measure) / `meets_positive` (>0R, the lesser measure) — exactly #593's contract.
  3. Also record `touch_floor_intraday` / `sustain_floor_intraday`: whether the 09:30-09:44
     window would have crossed today's real-time gap re-check anyway (Step 1's own finding:
     65% of the 8-9% band touched it, 24% held it 3 minutes) — context for reading the rate,
     never a second population; the near-miss population is defined on the OPEN gap only.

SURVIVORSHIP — the #482/#593 design constraint, restated because it bites here too: a name
still running when this walks it is NOT dropped just because it has not settled. Every row is
written on the FIRST pass, terminal or not; a non-terminal walk writes `outcome='open'` with a
MARK (`mark_r`/`mark_meets_4r`), refreshed by the SAME guarded UPSERT
(`db.upsert_gap_near_miss_replay`, WHERE the EXISTING row's outcome = 'open') on every later
run until it actually settles. A genuine DATA GAP is retried for
`live_fill_counterfactuals.GAP_RETRY_SESSIONS` nights before being written `unscoreable` —
never silently dropped either.

THE ERA STAMP — same reasoning as #482/#593/#616: the universe admission stack WILL move
(P1: a real EP must never be missed, so the operator keeps tuning filters as he spots misses).
`admission_era_as_of(session_date)` records which stack excluded this name so a later reader
segments instead of pooling. The WALK always uses `rule_eras.exit_rules_as_of(today)` — the
bracket AS IT EXISTS NOW — because the question is "does the CURRENT bracket miss this",
never archaeology; `replay_exit_era` / `replay_exit_rules` / `replay_asof_date` record which
"current" a settled row used.

⚠ DO NOT PICK THE TRIGGER THRESHOLD HERE. The data_gated_reviews.yaml entry
(`gap_near_miss_tradeable_miss_rate_617`) gates on SAMPLE SIZE only (>=30 decided rows) — a
mechanical evidence-sufficiency floor, not a policy call. The rate itself, and what rate
should re-open review of the 9% floor, is the operator's call (THE LINE) — see that entry's
`action_when_ready` for the one-line question this review exists to eventually put to him.

THE LINE — read this before touching anything here. This module is a passive OBSERVER:
  - ONE write target: `mi_gap_near_miss_replays` (plus `mi_audit_log` via `log_audit_event` —
    never a trade-state table).
  - It NEVER writes to `mi_live_trades`, `mi_live_orders`, `mi_ep_alerts`, `mi_ep_scan_log`,
    or any column any live decision reads. It never touches `MIN_GAP_PCT`, `MIN_PREV_CLOSE`,
    or `MIN_PREV_DAY_VOLUME` — it only READS them (imported, never restated, so the NEXT
    DEPLOY after the floor moves needs no second manual update here — the #595
    `missed_outcomes.py` precedent for exactly this; see `near_miss_lo_pct`'s own docstring
    for the precise import-time-binding cadence). It calls no broker module and no Alpaca
    client — its only
    imports beyond `agents.market_intelligence` are `backtester.filters.validate_orb_entry`
    (the shared, non-broker admission rule) and `alert_rank_shadow.compute_atr14_prior` (pure).
  - It is read by NO grading / entry / sizing / ordering / safeguard path — comparison
    telemetry only, feeding the #617 data_gated_reviews.yaml predicate alone. The recorder can
    be completely broken and the live trade path is unaffected: every walk is wrapped; a
    failure degrades to a counted error + an `mi_audit_log` row, `run_gap_near_miss_replay`
    never raises.
  - SILENT. No Telegram, ever, while evidence accrues (same posture as #482/#593's sibling
    lanes). `mi_gap_near_miss_replays` is registered in `health_checks._DETECTOR_LIVENESS_TABLES`
    so a dead writer (not "zero misses" — zero WRITES) still gets caught and Telegrammed by the
    nightly liveness sweep, the same watchdog covering #482/#593.
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
from agents.market_intelligence.db import (
    COMMON_STOCK_TYPES,
    _f,
    get_daily_ohlc_range,
    get_gap_near_miss_existing,
    get_gap_near_miss_population,
    get_intraday_bars_window,
    get_pool,
    log_audit_event,
    upsert_gap_near_miss_replay,
)
# #595 precedent (missed_outcomes.py): the SAME floors the live scan admits on, imported
# rather than restated. A second copy would drift the moment the operator moves one (MIN_GAP_PCT
# went 10.0 -> 9.0 on 2026-08-19), and this module's whole job is "would the CURRENT universe
# stack have admitted this" — the near-miss band is defined RELATIVE to the live floor, so it
# slides automatically if the floor ever moves (Step 3 of #617, operator-only; THE LINE).
from agents.market_intelligence.ep_detector import (
    MIN_GAP_PCT as _GAP_FLOOR_PCT,
    MIN_PREV_CLOSE as _MIN_PREV_CLOSE,
    MIN_PREV_DAY_VOLUME as _MIN_PREV_DAY_VOLUME,
)
from agents.market_intelligence.live_fill_counterfactuals import (
    n_trading_days_back,
    pinned_target,
    walk_arm,
)

logger = logging.getLogger(__name__)

SETTLE_VERSION = "gnm_v1"
TARGET_R = 2.0                    # the +2R partial level, matching live_fill_counterfactuals.TARGET_R
NEAR_MISS_BAND_WIDTH_PCT = 2.0     # the near-miss band is [floor-2, floor) — 7-9% today. NOT 5-6%
                                   # (module docstring SCOPE) — do not widen without a new card.
SUBMIT_TIME = time(9, 31)         # the most optimistic detection time for an excluded name — matches
                                   # Step 1's own assumption so today's rate is comparable to it.
SPLIT_DIVERGENCE_ABS_PCT = 0.05   # daily-row open vs raw 09:30 intraday open tolerance — see the
                                   # split-adjustment guard in _record_one_near_miss below. A reverse
                                   # split multiplies one side by 2x-100x+; ordinary feed/print noise
                                   # never approaches 5%.
ATR_LOOKBACK_CAL_DAYS = 40        # calendar days read for the ATR-14-prior window (mirrors #593)
PRIOR_CLOSES_CAL_DAYS = 40        # live_fill_counterfactuals convention — the trail's window (#548)
WINDOW_TRADING_DAYS = 40          # how far back each nightly run looks for NEW/still-open candidates
                                   # (a generous buffer against a missed run — mirrors sustain_reject_replay)


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def near_miss_lo_pct(floor_pct: float = _GAP_FLOOR_PCT) -> float:
    """The near-miss band's lower edge — floor minus the fixed 2pp width. `floor_pct`
    defaults to `_GAP_FLOOR_PCT`, which is bound ONCE when this module is first imported
    (a Python default-argument value, not re-evaluated per call) — the SAME cadence
    `ep_detector.MIN_GAP_PCT` itself uses (also resolved once, from EP_MIN_GAP_PCT, at ITS
    own import). A deploy (process restart) picks up an operator-changed floor; nothing
    changes it mid-process. Pass `floor_pct` explicitly for a caller that must not depend on
    import-time binding (e.g. a test)."""
    return floor_pct - NEAR_MISS_BAND_WIDTH_PCT


def gap_band(open_gap_pct: float, floor_pct: float = _GAP_FLOOR_PCT) -> str:
    """Which half of the near-miss band a name sits in, relative to the CURRENT floor —
    '7_8' / '8_9' today (floor=9.0). Bisects the band so #617's own "111 in 8-9%, 246 in 7-8%"
    per-band read (Step 1 §3) has a standing counterpart."""
    lo = floor_pct - NEAR_MISS_BAND_WIDTH_PCT
    mid = floor_pct - NEAR_MISS_BAND_WIDTH_PCT / 2.0
    return f"{lo:g}_{mid:g}" if open_gap_pct < mid else f"{mid:g}_{floor_pct:g}"


def touch_and_sustain(bars0: list[dict], prev_close: Optional[float],
                      floor_pct: float = _GAP_FLOOR_PCT) -> tuple[Optional[bool], Optional[bool]]:
    """(touch, sustain) against the CURRENT MIN_GAP_PCT floor, on the day's 09:30-09:44 ET
    window (bars0 already normalised to ET) — the SAME in-window measure #617 Step 1 read.
    touch = window HIGH vs the raw prior close (an upper bound on what a real-time re-check
    would admit); sustain = 3 consecutive minute CLOSES >= the floor (the `_sustain_ok` bar
    `ep_rt_sustain_enabled` applies — a lower bound). None when the window has no bars, or
    prev_close is unknown — never guessed."""
    window = [b for b in bars0 if time(9, 30) <= b["m"].time() < time(9, 45)]
    if not window or not prev_close:
        return None, None
    touch = any(b["h"] is not None and (b["h"] - prev_close) / prev_close * 100 >= floor_pct
               for b in window)
    run = 0
    sustain = False
    for b in window:
        if b["c"] is not None and (b["c"] - prev_close) / prev_close * 100 >= floor_pct:
            run += 1
            if run >= 3:
                sustain = True
                break
        else:
            run = 0
    return touch, sustain


# ── Orchestration (DB reads; writes only mi_gap_near_miss_replays + audit) ─────────────


def _fresh_fields(ticker: str, session_date: date, open_gap_pct: Optional[float],
                  band: str, prev_close: Optional[float], prev_volume: Optional[float],
                  admission_era: str, replay_exit_era: str, replay_exit_rules: dict,
                  replay_asof_date: date, settled_session: date) -> dict[str, Any]:
    return {
        "ticker": ticker, "session_date": session_date, "open_gap_pct": open_gap_pct,
        "gap_band": band, "prev_close": prev_close, "prev_volume": prev_volume,
        "touch_floor_intraday": None, "sustain_floor_intraday": None,
        "orb_high": None, "orb_low": None, "atr14_prior": None, "atr14_prior_n": None,
        "orb_valid": None, "orb_skip_reason": None,
        "submit_time_et": SUBMIT_TIME, "entry_status": None, "entry_reason": None,
        "entry_price": None, "entry_minute": None,
        "stop_price": None, "target_price": None, "target_r": TARGET_R,
        "outcome": None, "final_reason": None, "realized_r": None, "realized_pct": None,
        "mark_r": None, "meets_4r": None, "meets_positive": None, "mark_meets_4r": None,
        "mark_meets_positive": None,
        "partial_fired": None, "gap_through": None, "exit_session": None,
        "sessions_walked": None, "exits": [],
        "admission_era": admission_era, "replay_exit_era": replay_exit_era,
        "replay_exit_rules": replay_exit_rules, "replay_asof_date": replay_asof_date,
        "settle_version": SETTLE_VERSION, "settled_session": settled_session,
    }


async def _write(fields: dict, out: dict, label: str) -> bool:
    return await lfc.write_replay_row(
        fields, out, label,
        upsert=upsert_gap_near_miss_replay,
        error_event="gap_near_miss_replay_error",
    )


async def _record_one_near_miss(conn, row: dict, last_session: date, run_date: date,
                                out: dict) -> None:
    ticker, session_date = row["ticker"], row["trade_date"]
    prev_close = _f(row.get("prev_close"))
    prev_volume = _f(row.get("prev_volume"))
    open_gap_pct = _f(row.get("open_gap_pct"))
    label = f"{ticker} {session_date.isoformat()}"
    out["candidates"] += 1

    admission_era = rule_eras.admission_era_as_of(session_date)
    replay_exit_rules = rule_eras.exit_rules_as_of(run_date)
    replay_exit_era = rule_eras.exit_era_label(run_date)
    band = gap_band(open_gap_pct) if open_gap_pct is not None else "?"
    fields = _fresh_fields(ticker, session_date, open_gap_pct, band, prev_close, prev_volume,
                           admission_era, replay_exit_era, replay_exit_rules, run_date, last_session)

    try:
        # sessions AFTER session_date — needed regardless of whether an entry ever fills (a
        # no_trade/orb_invalid row still deserves the touch/sustain context above); fetched
        # once and reused for the post-fill walk below.
        sessions = await lfc._assemble_sessions(conn, ticker, session_date, last_session)

        prior_daily = await get_daily_ohlc_range(
            conn, ticker, session_date - timedelta(days=ATR_LOOKBACK_CAL_DAYS),
            session_date - timedelta(days=1))
        prior_hlc = [(_f(r.get("high_price")), _f(r.get("low_price")), _f(r.get("close")))
                    for r in prior_daily]
        prior_hlc = [t for t in prior_hlc if all(v is not None for v in t)]
        atr14 = compute_atr14_prior(prior_hlc)
        fields.update(atr14_prior=atr14, atr14_prior_n=len(prior_hlc))
        prior_cut = session_date - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
        prior_closes = [float(r["close"]) for r in prior_daily
                        if r.get("close") is not None and r["trade_date"] >= prior_cut]

        start = datetime.combine(session_date, time(9, 30), tzinfo=_ET)
        end = datetime.combine(session_date, time(16, 0), tzinfo=_ET)
        bars0 = await get_intraday_bars_window(conn, ticker, start, end)
        # bar_time is TIMESTAMPTZ; asyncpg hands it back UTC-aware — normalize to ET BEFORE any
        # .time() comparison (the ORB lookup, the 09:30-09:44 touch/sustain window) or every one
        # of them silently compares the wrong clock (the live_fill_counterfactuals precedent).
        bars0 = [{**b, "m": b["m"].astimezone(_ET) if isinstance(b["m"], datetime) else b["m"]}
                for b in bars0 if None not in (b["o"], b["h"], b["l"], b["c"])]
        if not bars0:
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

        # SPLIT-ADJUSTMENT GUARD (Step 1 §7 item 3: mi_daily_closes is REWRITTEN split-
        # adjusted after a LATER reverse split — LGCL read $118.94 in a Jun-Aug capture,
        # traded $0.95 on the day). This module's population query reads mi_daily_closes
        # FRESH every run, so a name that splits after session_date but before tonight's run
        # can show an inflated prev_close/open_price that clears MIN_PREV_CLOSE on adjusted
        # dollars while mi_intraday_bars (this module's ONLY price source for the walk,
        # never rewritten) is still in cents — the exact R-inflation class Step 1 had to
        # hand-re-file 199 rows to avoid (2-8c stops -> phantom >=4R). The daily row's own
        # open_price should equal the RAW 09:30 print within ordinary feed noise; a split
        # multiplies one side by 2x-100x+ and not the other, so a >5% divergence is treated
        # as a data-quality abstain, never walked.
        daily_open = _f(row.get("open_price"))
        if daily_open and orb["o"] and abs(daily_open / orb["o"] - 1) > SPLIT_DIVERGENCE_ABS_PCT:
            fields.update(entry_status="daily_row_split_adjusted", outcome="unscoreable",
                         final_reason="daily_row_split_adjusted")
            await _write(fields, out, label)
            return

        touch, sustain = touch_and_sustain(bars0, prev_close)
        fields.update(touch_floor_intraday=touch, sustain_floor_intraday=sustain)

        ok, skip = validate_orb_entry(orb_high, orb_low, atr14)
        fields.update(orb_valid=ok, orb_skip_reason=skip)
        if not ok:
            fields.update(entry_status="orb_invalid", outcome="no_trade", final_reason=skip)
            await _write(fields, out, label)
            return

        cancel = srr.entry_cancel_asof(run_date)
        fill = srr.entry_walk(bars0, orb_high, SUBMIT_TIME, cancel)
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

        if status == "pending":
            gap = res.get("pending_at")
            if gap is not None:
                # a genuine DATA GAP — retried like #482/#593's own forward-session gap,
                # never silently dropped.
                stale = len(lfc._trading_days(gap + timedelta(days=1), last_session)) >= lfc.GAP_RETRY_SESSIONS
                if not stale:
                    out["pending"] += 1
                    return
                fields.update(outcome="unscoreable", final_reason=res.get("reason"))
                await _write(fields, out, label)
                return
            # genuinely still OPEN — not a data gap. Written now (the survivorship fix), and
            # refreshed by later runs via the guarded UPSERT until it actually settles.
            mark = srr.mark_pnl_per_share(res, bars0, sessions, entry_px)
            fields.update(
                outcome="open", final_reason=res.get("reason"),
                partial_fired=res.get("partial_fired"), gap_through=res.get("gap_through"),
                sessions_walked=res.get("sessions_walked"), exits=res.get("exits") or [])
            if mark is not None:
                fields["mark_r"] = mark / risk
                fields["mark_meets_4r"] = fields["mark_r"] >= 4.0
                fields["mark_meets_positive"] = fields["mark_r"] > 0
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
                fields["meets_4r"] = fields["realized_r"] >= 4.0
                fields["meets_positive"] = fields["realized_r"] > 0
        elif status == "horizon":
            fields["outcome"] = "horizon"
            mark = res.get("mark_pnl_per_share")
            if mark is not None:
                fields["mark_r"] = mark / risk
                fields["mark_meets_4r"] = fields["mark_r"] >= 4.0
                fields["mark_meets_positive"] = fields["mark_r"] > 0
        else:  # abstain — a genuine day-0 order-ambiguity (same-bar stop+target, etc.)
            fields["outcome"] = "unscoreable"
        await _write(fields, out, label)
    except Exception as e:  # loud-ok: one candidate's failure is counted; the others proceed
        out["errors"] += 1
        await log_audit_event("gap_near_miss_replay_error", f"{label}: {type(e).__name__}: {e}")


async def run_gap_near_miss_replay(today: Optional[date] = None, *,
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
        rows = await get_gap_near_miss_population(
            window_start, last_session, near_miss_lo_pct(), _GAP_FLOOR_PCT,
            _MIN_PREV_CLOSE, _MIN_PREV_DAY_VOLUME, list(COMMON_STOCK_TYPES))
        existing = await get_gap_near_miss_existing(window_start)
    except Exception as e:  # loud-ok: the run reports and ends; nothing live depends on it
        out["errors"] += 1
        await log_audit_event("gap_near_miss_replay_error", f"population query failed: {e}")
        return out
    out["population"] = len(rows)
    todo = [r for r in rows
           if existing.get((r["ticker"], r["trade_date"])) in (None, "open")]
    if todo:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                for row in todo:
                    try:
                        await _record_one_near_miss(conn, row, last_session, today, out)
                    except Exception as e:  # loud-ok: per-name isolation; counted + audited
                        out["errors"] += 1
                        await log_audit_event(
                            "gap_near_miss_replay_error",
                            f"{row.get('ticker')} {row.get('trade_date')}: "
                            f"{type(e).__name__}: {e}")
        except Exception as e:  # loud-ok: pool-level failure; counted + audited
            out["errors"] += 1
            await log_audit_event("gap_near_miss_replay_error", f"run failed: {e}")
    await log_audit_event(
        "gap_near_miss_replay_recorded",
        f"{out['population']} near-miss ticker-day(s) in window, {len(todo)} candidate(s) "
        f"processed: {out['written']} written ({out['settled']} settled, "
        f"{out['no_trade']} no_trade, {out['unscoreable']} unscoreable, {out['open']} open, "
        f"{out['horizon']} at horizon), {out['pending']} pending, {out['errors']} error(s)")
    return out
