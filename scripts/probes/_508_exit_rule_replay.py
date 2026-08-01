#!/usr/bin/env python3
"""#508 workstream 2 — EXIT-RULE REPLAY against mi_sell_discipline_records (EVIDENCE ONLY).

THE LINE: this script is a read-only, offline replay. It produces evidence for the operator's
days-vs-R-gate question. It ships NO rule, changes NO live exit, and its output is NOT a
decision — any exit change is the operator's call via CHANGE_PROCESS + sign-off.

Inputs (prod snapshots pulled 2026-07-30, all read-only COPY TO STDOUT):
  _508_records.tsv — mi_sell_discipline_records (43 rows) + regime via
                     mi_market_regime ON regime_date = alert_date (never denormalised).
  _508_trades.tsv  — mi_live_trades exit legs + stop fields for those 43 trade ids.
  _508_minute.tsv  — in-hold RTH minute bars (mi_intraday_bars; same clamp as the recorder).
  _508_daily.tsv   — mi_daily_closes OHLC per trade span.

SIM CONTRACT (conservative; mirrors the #306 sim contract where they overlap):
  * Candidate rules REPLACE the deployed day-3 partial, so every candidate's per-trade
    baseline is the DO-NOTHING path (all shares ride to the trade's terminal exit-leg
    price); the deployed status quo is represented by (a) recorded realized_r ("actual")
    and (b) an engine re-play of the day-3 rule ("sq_replay", also a validation).
  * Trigger fills: limit-at-level — fill AT the trigger price (at the day/bar OPEN only
    when the open gaps ABOVE the trigger, standard limit mechanics). An in-hold peak >=
    trigger guarantees a limit fill at >= trigger by price continuity; granularity affects
    WHEN, not the fill price.
  * Breakeven stop after trigger: fills AT entry; a day/bar that OPENS below entry fills
    at that OPEN (gap-through — BE stops do not protect against overnight gaps).
  * Bar-covered days (bars >= 90% of expected in-hold RTH minutes) replay bar-by-bar
    (fill bar excluded from trigger scan — an entry-minute spike can't self-trigger).
    Non-covered days replay at day granularity with PESSIMISTIC intra-day ordering:
      - trigger-day close <= entry        -> BE-touch certain, remainder fills at entry;
      - trigger-day close > entry but day low <= entry -> AMBIGUOUS: pessimistic scratches
        the remainder at entry, optimistic lets it ride; both are computed, the headline
        is pessimistic, ambiguity is counted and reported;
      - later days: open <= entry fills at the open, else low <= entry fills at entry;
      - the close day's daily high/low are post-exit-contaminated: high evidence only via
        the record's attributed peak or the day's open/terminal price; low evidence via
        the terminal exit price (terminal <= entry proves an in-hold entry-touch).
  * Fill-day daily-high evidence is used only when the fill was within 15 min of 09:30
    (pre-fill prints are bounded by the ORB high <= entry, so a fill-day daily high >=
    trigger implies an in-hold print) — late fills (KURA 11:35, TEAM 11:31) are excluded
    unless bars cover the day.
  * FILL-REALISM tag per (trade, rule): "bars" when the trigger was found on a
    bar-covered day; "attr" when found via an attributed peak/middle-day daily high;
    "loose" when only an unattributed extremes max places it (day unknown — placed on the
    argmax middle-day-high day and flagged). Aggregates are reported for the full cohort
    AND restricted to bars-tier trades.
  * Exit-leg era artifacts: trades whose legs' share sum != entry_shares (April/early-May
    double-fire bugs, e.g. OMCL/AMD/TEAM) are flagged; their recorded realized_r inherits
    the artifact. Counterfactual paths use LEG PRICES (clean) applied to entry_shares;
    aggregates are also reported excluding the flagged trades.
  * Do-nothing caveat: for trades whose terminal exit sat AT breakeven because the
    deployed rule moved the stop there, the do-nothing path is optimistic (without the
    BE floor the exit could have been lower); such trades are flagged.

Run:  python3 scripts/probes/_508_exit_rule_replay.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
HERE = Path(__file__).resolve().parent

BAR_COVER_FRAC = 0.90       # a day is bar-covered when bars >= 90% of expected in-hold minutes
FILL_LAG_OK_MIN = 15        # fill-day daily-high evidence allowed only for fills <= 15 min after open
LEG_SHARE_TOL = 0.01        # legs-consistency: |sum(leg shares) - entry_shares| / entry_shares
BE_AT_ENTRY_TOL = 0.005     # terminal-at-breakeven detection tolerance ($)


def _parse_ts(s: str | None):
    if not s or s == r"\N":
        return None
    s = s.strip().replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    dt = datetime.fromisoformat(s.replace("T", " ").replace(" ", "T", 1))
    if dt.tzinfo is None:  # legacy legs carry naive UTC
        dt = dt.replace(tzinfo=UTC)
    return dt


def _parse_d(s: str | None):
    return None if (not s or s == r"\N") else date.fromisoformat(s)


def _parse_f(s: str | None):
    return None if (not s or s == r"\N") else float(s)


@dataclass
class Day:
    d: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    bars: list = field(default_factory=list)   # (bar_time, o, h, l, c) sorted
    covered: bool = False                       # bar coverage >= BAR_COVER_FRAC
    inhold_high: float | None = None            # defensible in-hold high evidence
    high_src: str = "none"                      # bars | attr | daily_mid | none
    inhold_close: bool = False                  # trade open at this day's 16:00 ET


@dataclass
class Trade:
    rec: dict
    legs: list
    days: list[Day] = field(default_factory=list)
    flags: set = field(default_factory=set)

    # -- convenience -------------------------------------------------------
    @property
    def entry(self): return self.rec["entry_price"]
    @property
    def risk(self): return self.rec["risk_per_share"]
    def to_r(self, price): return (price - self.entry) / self.risk

    @property
    def terminal_price(self):
        """Price of the last (terminal) exit leg — the counterfactual remainder's exit
        when no breakeven-touch preempts it."""
        return self.legs[-1]["price"] if self.legs else None

    @property
    def nothing_r(self):
        return self.to_r(self.terminal_price) if self.terminal_price is not None else self.rec["realized_r"]

    @property
    def global_peak(self):
        """Best in-hold high evidence across all sources — marginality basis."""
        cands = [self.rec["peak_price"]]
        for d in self.days:
            cands.append(max((b[2] for b in d.bars), default=None))
            if self.rec["fill_day"] < d.d < self.rec["close_day"]:
                cands.append(d.high)
        vals = [c for c in cands if c is not None]
        return max(vals) if vals else None

    @property
    def cohort(self):
        return f"{self.rec['account_mode']}/{self.rec['signal_type']}"


# ── load ─────────────────────────────────────────────────────────────────────

REC_COLS = ("trade_id ticker signal_type account_mode alert_date fill_day close_day filled_at "
            "closed_at entry_price risk_per_share entry_shares realized_pnl realized_r peak_price "
            "peak_r peak_time peak_day peak_hold_day peak_source peak_bars_n peak_close peak_close_r "
            "peak_close_day giveback_r capture_pct hold_trading_days stop_above_entry_ever "
            "partial_taken pnl_attribution regime "
            "stop_pct stop_per_adr peak_adr realized_adr").split()

_DATES = {"alert_date", "fill_day", "close_day", "peak_day", "peak_close_day"}
_TS = {"filled_at", "closed_at", "peak_time"}
_INTS = {"trade_id", "peak_hold_day", "peak_bars_n", "hold_trading_days"}
_BOOLS = {"stop_above_entry_ever", "partial_taken"}
_STRS = {"ticker", "signal_type", "account_mode", "peak_source", "pnl_attribution", "regime"}


def load() -> list[Trade]:
    records = {}
    for line in (HERE / "_508_records.tsv").read_text().splitlines():
        f = line.split("\t")
        rec = {}
        for k, v in zip(REC_COLS, f):
            if k in _DATES:
                rec[k] = _parse_d(v)
            elif k in _TS:
                rec[k] = _parse_ts(v)
            elif k in _INTS:
                rec[k] = None if v == r"\N" else int(v)
            elif k in _BOOLS:
                rec[k] = v == "t"
            elif k in _STRS:
                rec[k] = None if v == r"\N" else v
            else:
                rec[k] = _parse_f(v)
        records[rec["trade_id"]] = rec

    legs_by_id, stops_by_id = {}, {}
    for line in (HERE / "_508_trades.tsv").read_text().splitlines():
        f = line.split("\t")
        tid = int(f[0])
        stops_by_id[tid] = {"hard_stop": _parse_f(f[2]), "orb_low": _parse_f(f[3]),
                            "stop_price": _parse_f(f[4])}
        legs = json.loads(f[9]) if f[9] and f[9] != r"\N" else []
        norm = []
        for leg in legs:
            norm.append({
                "time": _parse_ts(leg.get("time") or leg.get("at")),
                "price": float(leg["price"]),
                "shares": float(leg.get("shares", leg.get("qty", 0)) or 0),
                "reason": leg.get("reason", ""),
            })
        norm.sort(key=lambda x: (x["time"] is None, x["time"]))
        legs_by_id[tid] = norm

    daily_by_id = defaultdict(dict)
    for line in (HERE / "_508_daily.tsv").read_text().splitlines():
        f = line.split("\t")
        tid, d = int(f[0]), _parse_d(f[1])
        daily_by_id[tid][d] = (_parse_f(f[2]), _parse_f(f[3]), _parse_f(f[4]), _parse_f(f[5]))

    bars_by_id = defaultdict(list)
    for line in (HERE / "_508_minute.tsv").read_text().splitlines():
        f = line.split("\t")
        bars_by_id[int(f[0])].append((_parse_ts(f[1]), float(f[2]), float(f[3]),
                                      float(f[4]), float(f[5])))

    trades = []
    for tid, rec in sorted(records.items()):
        t = Trade(rec=rec, legs=legs_by_id.get(tid, []))
        _build_days(t, daily_by_id.get(tid, {}), bars_by_id.get(tid, []))
        _flag(t)
        trades.append(t)
    return trades


def _build_days(t: Trade, daily: dict, bars: list):
    rec = t.rec
    fill_day, close_day = rec["fill_day"], rec["close_day"]
    filled_at, closed_at = rec["filled_at"], rec["closed_at"]
    day_dates = sorted(set(daily) | {fill_day, close_day})
    days = {d: Day(d=d) for d in day_dates}
    for d, (o, h, l, c) in daily.items():
        days[d].open, days[d].high, days[d].low, days[d].close = o, h, l, c
    for b in sorted(bars):
        bd = b[0].astimezone(ET).date()
        if bd in days:
            days[bd].bars.append(b)

    fill_lag_ok = (filled_at.astimezone(ET).time() <= dt_time(9, 30 + FILL_LAG_OK_MIN))
    for d, day in days.items():
        start = max(filled_at, datetime.combine(d, dt_time(9, 30), tzinfo=ET))
        end = min(closed_at, datetime.combine(d, dt_time(16, 0), tzinfo=ET))
        expected = max(0.0, (end - start).total_seconds() / 60.0)
        day.covered = expected > 0 and len(day.bars) >= BAR_COVER_FRAC * expected
        close_ts = datetime.combine(d, dt_time(16, 0), tzinfo=ET)
        day.inhold_close = filled_at <= close_ts and closed_at > close_ts

        # defensible in-hold HIGH evidence per day
        if day.covered:
            day.inhold_high = max(b[2] for b in day.bars)
            day.high_src = "bars"
        elif fill_day < d < close_day and day.high is not None:
            day.inhold_high = day.high
            day.high_src = "daily_mid"
        elif d == fill_day == close_day and rec["peak_price"] is not None:
            day.inhold_high = rec["peak_price"]          # extremes max is in-hold by construction
            day.high_src = "attr"
        elif rec["peak_day"] == d and rec["peak_price"] is not None:
            day.inhold_high = rec["peak_price"]
            day.high_src = "attr"
        elif d == fill_day and fill_lag_ok and day.high is not None:
            # pre-fill prints bounded by ORB high <= entry -> daily high >= trigger implies in-hold
            day.inhold_high = day.high
            day.high_src = "daily_mid"
        elif d == close_day:
            cands = [p for p in (day.open, t.terminal_price) if p is not None]
            if cands:
                day.inhold_high = max(cands)
                day.high_src = "attr"
    t.days = [days[d] for d in day_dates]


def _flag(t: Trade):
    if t.legs:
        share_sum = sum(l["shares"] for l in t.legs)
        es = t.rec["entry_shares"] or 0
        if es and abs(share_sum - es) / es > LEG_SHARE_TOL:
            t.flags.add("legs_inconsistent")
        if abs(t.terminal_price - t.entry) <= max(BE_AT_ENTRY_TOL, 0.0005 * t.entry) \
                and t.rec["partial_taken"]:
            t.flags.add("terminal_at_breakeven")
    else:
        t.flags.add("no_legs")
    peak_r = t.rec["peak_r"]
    if peak_r is not None and t.rec["peak_day"] is None and t.rec["fill_day"] != t.rec["close_day"]:
        t.flags.add("peak_unplaced")


# ── the replay engine ────────────────────────────────────────────────────────

MARGINAL_TICK = 0.01            # trigger evidence must clear the level by >= 1 cent

@dataclass
class Result:
    kept_r: float               # headline (pessimistic where ambiguous)
    kept_r_opt: float           # optimistic resolution of intra-day ambiguity
    triggered: bool = False
    ambiguous: bool = False
    realism: str = "n/a"        # bars | attr | loose | close | n/a
    marginal: bool = False      # peak evidence clears the trigger by < 1 cent


def _be_scan_bars(t: Trade, bars_after: list) -> float | None:
    """Bar-level breakeven scan; returns remainder exit R or None (no touch)."""
    for bt, o, h, l, c in bars_after:
        if o <= t.entry:
            return t.to_r(o)
        if l <= t.entry:
            return t.to_r(t.entry)
    return None


def _remainder_after(t: Trade, trig_day_i: int, trig_time, same_day_close_known: bool = True):
    """Remainder path after a trigger on day index trig_day_i (bar time trig_time when
    bar-covered). Returns (pess_r, opt_r, ambiguous)."""
    days = t.days
    day = days[trig_day_i]
    # 1. trigger day itself
    if day.covered and trig_time is not None:
        after = [b for b in day.bars if b[0] > trig_time]
        r = _be_scan_bars(t, after)
        if r is not None:
            return r, r, False
    else:
        eff_close = day.close
        if day.d == t.rec["close_day"] and not day.inhold_close:
            eff_close = t.terminal_price      # exited intraday: terminal is the day's "end"
        if eff_close is not None and eff_close <= t.entry:
            return 0.0, 0.0, False            # certain touch, fill at entry
        low_known = day.low is not None and (t.rec["fill_day"] != day.d or True)
        if low_known and day.low is not None and day.low <= t.entry:
            # ambiguous: dip to entry may pre- or post-date the trigger
            pess = 0.0
            opt_r, _, _ = _later_days(t, trig_day_i)
            return pess, opt_r, True
    # 2. later days
    r, o, amb = _later_days(t, trig_day_i)
    return r, o, amb


def _later_days(t: Trade, trig_day_i: int):
    days = t.days
    for j in range(trig_day_i + 1, len(days)):
        day = days[j]
        if day.covered and day.bars:
            r = _be_scan_bars(t, day.bars)
            if r is not None:
                return r, r, False
            continue
        is_close_day = day.d == t.rec["close_day"]
        if day.open is not None and day.open <= t.entry:
            r = t.to_r(day.open)
            return r, r, False
        if is_close_day:
            if t.terminal_price is not None and t.terminal_price <= t.entry:
                return 0.0, 0.0, False        # actual exit at/below entry proves the touch
            if day.low is not None and day.low <= t.entry:
                term = t.nothing_r            # dip may be post-exit prints -> ambiguous
                return 0.0, term, True
            continue
        if day.low is not None and day.low <= t.entry:
            return 0.0, 0.0, False            # full-session in-hold middle day: touch certain
    return t.nothing_r, t.nothing_r, False


def _find_trigger(t: Trade, trig_price: float):
    """First in-hold moment price >= trig_price. Returns (day_i, bar_time|None, realism,
    marginal) or None. Realism: bars | attr | loose. Marginal = the trade's GLOBAL in-hold
    peak clears the trigger by < 1 cent (a single-touch print — a limit fill there is a
    queue-position gamble, not a defensible fill)."""
    rec = t.rec
    gp = t.global_peak
    marginal = gp is not None and (gp - trig_price) < MARGINAL_TICK
    for i, day in enumerate(t.days):
        if day.covered:
            bars = day.bars
            if day.d == rec["fill_day"] and bars:
                bars = bars[1:]               # fill bar excluded — no self-trigger
            for b in bars:
                if b[2] >= trig_price:
                    return i, b[0], "bars", marginal
            continue
        if day.inhold_high is not None and day.inhold_high >= trig_price:
            return i, None, "attr", marginal
    # unattributed extremes max exceeds every placed high: place on argmax middle-day high
    peak = rec["peak_price"]
    if peak is not None and peak >= trig_price and "peak_unplaced" in t.flags:
        mids = [(i, d) for i, d in enumerate(t.days)
                if rec["fill_day"] < d.d < rec["close_day"] and d.high is not None]
        if mids:
            i, _ = max(mids, key=lambda x: x[1].high)
            return i, None, "loose", marginal
        return 0, None, "loose", marginal
    return None


# ── 5-MINUTE-POLL FILL MODEL (build step 1, 2026-08-01) ──────────────────────
# The signed +0.47R was measured under LIMIT-at-level fills: fill AT the trigger
# price, guaranteed by price continuity. The design we are actually building does
# NOT rest an order — `track_position_extremes` polls every 5 minutes, reads the
# minute bars since the last poll, and only THEN sells. So:
#   * DETECTION is not lossy — a spike between polls is still in the bars.
#   * The FILL is at the price when the job acts, which can be better OR worse
#     than the trigger. That is the whole difference, and it is what this models.
# Fill proxy: the OPEN of the first bar at a 5-minute boundary strictly after the
# trigger minute (the job runs at :00/:05/:10…; its sell hits at that moment).
# Returns None when the trigger day has no bar coverage — poll fills are simply
# not measurable there, and scoring them as anything would be invention.
POLL_MINUTES = 5


def _poll_fill_price(t: Trade, day_i: int, trig_time) -> float | None:
    """Price the 5-minute poll would actually transact at, or None if unmeasurable."""
    day = t.days[day_i]
    if not day.covered or trig_time is None:
        return None
    for b in day.bars:
        bt = b[0]
        if bt <= trig_time:
            continue
        if bt.minute % POLL_MINUTES == 0:     # the first poll boundary after the touch
            return b[1]                        # its OPEN — when the sell lands
    return None


def sim_r_rule_poll(t: Trade, level: float, frac: float, full_exit=False) -> Result | None:
    """Same rule, filled at the next 5-minute poll instead of at the trigger."""
    trig_price = t.entry + level * t.risk
    hit = _find_trigger(t, trig_price)
    if hit is None:
        nr = t.nothing_r
        return Result(nr, nr, triggered=False)
    day_i, bar_time, realism, marginal = hit
    px = _poll_fill_price(t, day_i, bar_time)
    if px is None:
        return None                            # unmeasurable — excluded, never guessed
    fill_r = t.to_r(px)
    if full_exit:
        return Result(fill_r, fill_r, triggered=True, realism=realism, marginal=marginal)
    pess, opt, amb = _remainder_after(t, day_i, bar_time)
    return Result(frac * fill_r + (1 - frac) * pess,
                  frac * fill_r + (1 - frac) * opt,
                  triggered=True, ambiguous=amb, realism=realism, marginal=marginal)


def sim_adr_rule_poll(t: Trade, level: float, frac: float) -> Result | None:
    a = adr_per_r(t)
    return None if a is None else sim_r_rule_poll(t, level / a, frac)


def sim_r_rule(t: Trade, level: float, frac: float, be_only=False, full_exit=False) -> Result:
    """Intraday R-trigger: at entry + level*risk, sell `frac` (or arm BE only, or exit all)."""
    trig_price = t.entry + level * t.risk
    hit = _find_trigger(t, trig_price)
    if hit is None:
        nr = t.nothing_r
        return Result(nr, nr, triggered=False)
    day_i, bar_time, realism, marginal = hit
    day = t.days[day_i]
    fill_r = level
    if day.open is not None and day.d != t.rec["fill_day"] and day.open > trig_price \
            and not day.covered:
        fill_r = t.to_r(day.open)             # gap-open above the resting limit
    if full_exit:
        return Result(fill_r, fill_r, triggered=True, realism=realism, marginal=marginal)
    pess, opt, amb = _remainder_after(t, day_i, bar_time)
    if be_only:
        return Result(pess, opt, triggered=True, ambiguous=amb, realism=realism,
                      marginal=marginal)
    kept = frac * fill_r + (1 - frac) * pess
    kept_o = frac * fill_r + (1 - frac) * opt
    return Result(kept, kept_o, triggered=True, ambiguous=amb, realism=realism,
                  marginal=marginal)


def adr_per_r(t: Trade) -> float | None:
    """How many ADR one R is worth for this trade, or None when unusable.

    `stop_per_adr` = stop_pct / adr_pct is recorded per trade, so a trigger of L
    ADR is simply an R-trigger of L / stop_per_adr — the whole fill/breakeven
    engine is reused unchanged, no new price data.

    None (never a guess) when the ratio is missing or <= 0. ⚠ HISTORICAL: before the
    2026-08-01 recorder fix + backfill this returned None on 11 of 43 rows — which
    were precisely the 11 biggest movers, because the recorder had captured the
    TRAILED stop. Post-backfill it is 0 of 43. The branch stays as the guard for
    genuinely missing ADR data.
    Verified 2026-08-01: for all 12 LIVE rows stop_pct == risk_per_share/entry*100
    exactly, so the ratio is the ORIGINAL entry risk, not a trailed stop.
    """
    v = t.rec.get("stop_per_adr")
    return v if (v is not None and v > 0) else None


def sim_adr_rule(t: Trade, level: float, frac: float, full_exit=False) -> Result | None:
    """Trigger at `level` x the ticker's own 20d ADR. None when unmeasurable."""
    a = adr_per_r(t)
    if a is None:
        return None
    return sim_r_rule(t, level / a, frac, full_exit=full_exit)


def _inhold_closes(t: Trade):
    return [(i, d) for i, d in enumerate(t.days) if d.inhold_close and d.close is not None]


def sim_close_rule(t: Trade, level: float | None, day_gate: int | None, frac: float,
                   fill_next_open: bool, sq_form: bool = False) -> Result:
    """Daily-close-axis rules. Trigger at the first in-hold close satisfying the gate:
      level    — close_r >= level (R-reached gate on the close axis)
      day_gate — Nth in-hold close, requiring close > entry (the deployed day-3 form);
                 sq_form additionally allows day >= 5 unconditionally (status quo).
    Fill at that close (MOC model) or at the NEXT session's open (deployed mechanics)."""
    closes = _inhold_closes(t)
    trig = None
    for seq, (i, d) in enumerate(closes, start=1):
        cr = t.to_r(d.close)
        if level is not None and cr >= level:
            trig = (seq, i, d)
            break
        if day_gate is not None:
            if sq_form and (seq >= day_gate and (d.close > t.entry or seq >= 5)):
                trig = (seq, i, d)
                break
            if not sq_form and seq == day_gate and d.close > t.entry:
                trig = (seq, i, d)
                break
    if trig is None:
        nr = t.nothing_r
        return Result(nr, nr, triggered=False)
    _, i, d = trig
    if not fill_next_open:
        fill_r = t.to_r(d.close)
        pess, opt, amb = _later_days(t, i)
        kept = frac * fill_r + (1 - frac) * pess
        return Result(kept, frac * fill_r + (1 - frac) * opt,
                      triggered=True, ambiguous=amb, realism="close")
    # deployed mechanics: decision EOD day i, order fills at next session's ~09:31 open
    if i + 1 >= len(t.days):
        nr = t.nothing_r
        return Result(nr, nr, triggered=False)
    nxt = t.days[i + 1]
    open_ts = datetime.combine(nxt.d, dt_time(9, 31), tzinfo=ET)
    if t.rec["closed_at"] <= open_ts or nxt.open is None:
        nr = t.nothing_r                       # trade died before the fill could happen
        return Result(nr, nr, triggered=False)
    fill_r = t.to_r(nxt.open)
    # BE armed at the same fill; scan the fill day then later days
    if nxt.open <= t.entry:
        pess = opt = t.to_r(nxt.open)          # partial itself fills below entry; remainder same
        amb = False
    else:
        pess, opt, amb = _remainder_after(t, i + 1, None)
    kept = frac * fill_r + (1 - frac) * pess
    return Result(kept, frac * fill_r + (1 - frac) * opt,
                  triggered=True, ambiguous=amb, realism="close")


# ── candidates ───────────────────────────────────────────────────────────────

# ── REGIME-CONDITIONAL RULES (operator 2026-08-01) ───────────────────────────
# "runners probably happen more often in bull markets, so one possibility is that
# we have more aggressive profit take on bear markets and let runners go in bull
# markets. The ask is to have all permutations ready once we have the samples."
#
# A conditional rule picks its trigger from the regime recorded at ALERT time, so
# one rule can take profit early in Correcting and late (or never) in Bull. A
# level of None means DO NOTHING in that regime — that is the "let it run" arm.
_REGIME_KEY = {"Bull": "bull", "Choppy": "chop", "Correcting": "corr", "Crisis": "corr"}


def sim_regime_rule(t: Trade, levels: dict, frac: float, unit: str = "R",
                    full_exit: bool = False) -> Result | None:
    """`levels` maps bull/chop/corr -> trigger level (or None = hold, no rule).

    Unknown/missing regime returns None (UNMEASURABLE, excluded from the mean) —
    never silently treated as one of the arms, which would invent evidence for a
    regime the trade was not in.
    """
    key = _REGIME_KEY.get(t.rec.get("regime") or "")
    if key is None:
        return None
    lvl = levels.get(key)
    if lvl is None:                       # "let runners go" arm: do nothing
        return Result(t.nothing_r, t.nothing_r, triggered=False)
    if unit == "ADR":
        return sim_adr_rule(t, lvl, frac, full_exit=full_exit)
    return sim_r_rule(t, lvl, frac, full_exit=full_exit)


def candidates():
    c = {}
    c["actual"] = None                       # recorded realized_r (deployed system as-run)
    c["nothing"] = lambda t: Result(t.nothing_r, t.nothing_r)
    c["sq_replay(d3+,1/3,next-open)"] = \
        lambda t: sim_close_rule(t, None, 3, 1 / 3, fill_next_open=True, sq_form=True)
    for lvl in (1.0, 1.5, 2.0, 3.0):
        c[f"R{lvl:g}_part1/3+BE"] = (lambda L: lambda t: sim_r_rule(t, L, 1 / 3))(lvl)
    c["R2_part1/2+BE"] = lambda t: sim_r_rule(t, 2.0, 0.5)
    # the SAME rules under the 5-minute-poll fill — what we are actually building
    for lvl in (1.0, 2.0, 3.0):
        c[f"R{lvl:g}_part1/3+BE_POLL5"] = (lambda L: lambda t: sim_r_rule_poll(t, L, 1 / 3))(lvl)
    c["ADR1_part1/3+BE_POLL5"] = lambda t: sim_adr_rule_poll(t, 1.0, 1 / 3)
    # ── same rules, measured in the ticker's OWN daily range instead of in R.
    # The point of the comparison (operator 2026-08-01): stop width spans 0.15-1.17
    # ADR across the live cohort, so one "+2R" rule fires at 7.7x different real
    # distances. These ask what happens when the trigger is a CONSTANT distance.
    for lvl in (0.5, 1.0, 1.5, 2.0):
        c[f"ADR{lvl:g}_part1/3+BE"] = (lambda L: lambda t: sim_adr_rule(t, L, 1 / 3))(lvl)
    for lvl in (1.0, 1.5):
        c[f"ADR{lvl:g}_exit_all"] = (lambda L: lambda t: sim_adr_rule(t, L, 1.0, full_exit=True))(lvl)

    # ── the regime permutation grid: tight in weak tape, loose/none in Bull ──
    # Named <bull>/<chop>/<corr>. "none" = hold, no profit-take in that regime.
    for name, lv in (
        ("rgm_none/2R/2R",   {"bull": None, "chop": 2.0, "corr": 2.0}),
        ("rgm_none/1R/1R",   {"bull": None, "chop": 1.0, "corr": 1.0}),
        ("rgm_4R/2R/1R",     {"bull": 4.0,  "chop": 2.0, "corr": 1.0}),
        ("rgm_4R/3R/2R",     {"bull": 4.0,  "chop": 3.0, "corr": 2.0}),
        ("rgm_3R/2R/2R",     {"bull": 3.0,  "chop": 2.0, "corr": 2.0}),
        ("rgm_6R/3R/2R",     {"bull": 6.0,  "chop": 3.0, "corr": 2.0}),
    ):
        c[f"{name}_part1/3+BE"] = (lambda L: lambda t: sim_regime_rule(t, L, 1 / 3))(lv)
    # full-exit arm of the same idea: bank it entirely when the tape is weak
    for name, lv in (
        ("rgm_none/2R/2R", {"bull": None, "chop": 2.0, "corr": 2.0}),
        ("rgm_none/3R/2R", {"bull": None, "chop": 3.0, "corr": 2.0}),
    ):
        c[f"{name}_exit_all"] = (lambda L: lambda t: sim_regime_rule(t, L, 1.0, full_exit=True))(lv)
    for lvl in (1.5, 2.0, 3.0):
        c[f"R{lvl:g}_exit_all"] = (lambda L: lambda t: sim_r_rule(t, L, 1.0, full_exit=True))(lvl)
    for lvl in (1.0, 2.0):
        c[f"R{lvl:g}_BE_only"] = (lambda L: lambda t: sim_r_rule(t, L, 0.0, be_only=True))(lvl)
    for lvl in (1.0, 2.0):
        c[f"closeR{lvl:g}_part1/3_MOC"] = \
            (lambda L: lambda t: sim_close_rule(t, L, None, 1 / 3, fill_next_open=False))(lvl)
        c[f"closeR{lvl:g}_part1/3_next-open"] = \
            (lambda L: lambda t: sim_close_rule(t, L, None, 1 / 3, fill_next_open=True))(lvl)
    for n in (1, 2):
        c[f"day{n}close_part1/3_next-open"] = \
            (lambda N: lambda t: sim_close_rule(t, None, N, 1 / 3, fill_next_open=True))(n)
    c["day1close_part1/3_MOC"] = lambda t: sim_close_rule(t, None, 1, 1 / 3, fill_next_open=False)
    return c


# ── reporting ────────────────────────────────────────────────────────────────

def fmt(v, w=7, d=2):
    return f"{v:+{w}.{d}f}" if v is not None else " " * (w - 1) + "—"


def _mean_over(res: dict, trades) -> float | None:
    """Mean kept_r over the trades this candidate could actually be measured on."""
    vs = [res[t.rec["trade_id"]].kept_r for t in trades if t.rec["trade_id"] in res]
    return sum(vs) / len(vs) if vs else None


def run():
    trades = load()
    cands = candidates()
    results: dict[str, dict[int, Result]] = {}
    for name, fn in cands.items():
        if name == "actual":
            results[name] = {t.rec["trade_id"]:
                             Result(t.rec["realized_r"], t.rec["realized_r"]) for t in trades}
        else:
            # None = the rule is UNMEASURABLE on this trade (no usable ADR ratio),
            # which is not the same as "did not trigger". Dropping the key excludes
            # it from that candidate's mean instead of scoring it as a miss.
            results[name] = {t.rec["trade_id"]: r for t in trades
                             if (r := fn(t)) is not None}

    by_cohort = defaultdict(list)
    for t in trades:
        by_cohort[t.cohort].append(t)
    cohorts = ["live/magna53", "paper/magna53", "paper/9m_day2"]

    print("=" * 100)
    print("#508 W2 — EXIT-RULE REPLAY over mi_sell_discipline_records (n=43; prod snapshot 2026-07-30)")
    print("=" * 100)
    print("\n--- DATA HONESTY -------------------------------------------------------------")
    for co in cohorts:
        n = len(by_cohort[co])
        print(f"  {co:<16} n={n}")
    bars_tier = [t for t in trades if all(d.covered for d in t.days
                                          if d.d <= t.rec["close_day"])]
    full_cov = [t.rec["trade_id"] for t in trades
                if t.days and all(d.covered for d in t.days)]
    print(f"  fully bar-covered trades (exact intraday replay): {len(full_cov)} of 43 -> ids {full_cov}")
    for fl in ("legs_inconsistent", "terminal_at_breakeven", "peak_unplaced"):
        ids = [t.rec["trade_id"] for t in trades if fl in t.flags]
        print(f"  {fl:<24}: n={len(ids)} {ids}")
    amb_any = sorted({t.rec['trade_id'] for t in trades
                      for nm in results if nm not in ('actual',)
                      and t.rec['trade_id'] in results[nm]
                      and results[nm][t.rec['trade_id']].ambiguous})
    print(f"  trades hitting ambiguous intra-day ordering under >=1 candidate: {amb_any}")

    # engine validation: sq_replay vs actual on the 11 partial trades
    print("\n--- ENGINE VALIDATION: sq_replay vs recorded actual (the 11 partial-fired trades) ---")
    print(f"  {'id':>4} {'tkr':<5} {'actual':>8} {'sq_replay':>9}  flags")
    for t in trades:
        if t.rec["partial_taken"]:
            r = results["sq_replay(d3+,1/3,next-open)"][t.rec["trade_id"]]
            print(f"  {t.rec['trade_id']:>4} {t.rec['ticker']:<5} {fmt(t.rec['realized_r'],8)} "
                  f"{fmt(r.kept_r, 9)}  {','.join(sorted(t.flags)) or '-'}")

    # per-trade live table
    key_cands = ["actual", "nothing", "sq_replay(d3+,1/3,next-open)", "R1_part1/3+BE",
                 "R2_part1/3+BE", "R3_part1/3+BE", "R2_exit_all", "R1_BE_only",
                 "closeR2_part1/3_MOC", "day1close_part1/3_next-open"]
    print("\n--- PER-TRADE, LIVE COHORT (n=12 — every trade shown; this is ALL the live evidence) ---")
    hdr = f"  {'id':>4} {'tkr':<5} {'peak_r':>7} {'pkday':>5} " + \
          " ".join(f"{c[:11]:>11}" for c in key_cands)
    print(hdr)
    for t in by_cohort["live/magna53"]:
        tid = t.rec["trade_id"]
        row = f"  {tid:>4} {t.rec['ticker']:<5} {fmt(t.rec['peak_r'])} " \
              f"{t.rec['peak_hold_day'] if t.rec['peak_hold_day'] else '—':>5} "
        row += " ".join(fmt(results[c][tid].kept_r, 11) for c in key_cands)
        amb = [c for c in key_cands if results[c][tid].ambiguous]
        if amb:
            row += "  ~amb"
        marg = [c for c in key_cands if results[c][tid].marginal]
        if marg:
            row += "  !mrg:" + "|".join(m.split("_")[0] for m in marg)
        print(row)

    # main table per cohort
    def agg(names, ts, res_key="kept_r"):
        rows = []
        for name in names:
            # PAIR trade->result, dropping unmeasurable trades TOGETHER (found by the
            # 2026-08-01 adversarial review). Two bugs lived here: `n = len(ts)` divided
            # by the FULL cohort while `kept` summed only measurable trades — scoring an
            # unmeasurable trade as kept_r = 0 rather than excluding it — and `zip(ts, rs)`
            # silently MISALIGNED trades with results the moment any were dropped, so
            # cost/win, gain/los, nW and nL were garbage on any such row. The live table
            # was unaffected (all 12 measurable) but the paper rows printed nonsense.
            pairs = [(t, results[name][t.rec["trade_id"]]) for t in ts
                     if t.rec["trade_id"] in results[name]]
            if not pairs:
                continue
            rs = [r for _t, r in pairs]
            kept = [getattr(r, res_key) for r in rs]
            n = len(pairs)          # the MEASURABLE denominator, not the cohort size
            mean = sum(kept) / n
            act = sum(t.rec["realized_r"] for t, _r in pairs) / n
            noth = sum(t.nothing_r for t, _r in pairs) / n
            winners = [(t, r) for t, r in pairs if t.nothing_r > 0]
            losers = [(t, r) for t, r in pairs if t.nothing_r <= 0]
            cw = (sum(getattr(r, res_key) - t.nothing_r for t, r in winners) / len(winners)
                  if winners else None)
            bl = (sum(getattr(r, res_key) - t.nothing_r for t, r in losers) / len(losers)
                  if losers else None)
            trig = sum(1 for r in rs if r.triggered)
            amb = sum(1 for r in rs if r.ambiguous)
            mrg = sum(1 for r in rs if r.marginal)
            rows.append((name, n, trig, mean, mean - act, mean - noth, cw, len(winners),
                         bl, len(losers), amb, mrg))
        return rows

    names = list(cands)
    for co in cohorts:
        ts = by_cohort[co]
        print(f"\n--- CANDIDATES × {co} (n={len(ts)}) — mean kept R/trade; pessimistic ambiguity ---")
        print(f"  {'candidate':<28} {'trig':>4} {'kept':>7} {'Δactual':>8} {'Δnothing':>9} "
              f"{'cost/win':>9} {'nW':>3} {'gain/los':>9} {'nL':>3} {'amb':>3} {'mrg':>3}")
        for (name, n, trig, mean, da, dn, cw, nw, bl, nl, amb, mrg) in agg(names, ts):
            print(f"  {name:<28} {trig:>4} {fmt(mean)} {fmt(da, 8)} {fmt(dn, 9)} "
                  f"{fmt(cw, 9)} {nw:>3} {fmt(bl, 9)} {nl:>3} {amb:>3} {mrg:>3}")

    # ── PER-REGIME SEGMENTATION (operator 2026-08-01, asked repeatedly) ──────
    # Runners plausibly cluster in Bull, so a single blended mean can hide that the
    # right rule DIFFERS by tape. Every cell prints its own n so an under-powered
    # cell cannot be read as a result — which is the whole point of having the
    # permutations ready BEFORE the samples arrive.
    print("\n--- PER-REGIME (live+paper magna53). Each cell: mean kept R (n). "
          "n<4 is NOT a result — it is a placeholder waiting for samples. ---")
    mag = [t for t in trades if t.rec["signal_type"] == "magna53"]
    regimes = ["Bull", "Choppy", "Correcting"]
    counts = {rg: len([t for t in mag if t.rec["regime"] == rg]) for rg in regimes}
    print("    cohort n by regime: " + " · ".join(f"{rg} {counts[rg]}" for rg in regimes)
          + f" · unknown {len([t for t in mag if t.rec['regime'] not in regimes])}")
    hdr = f"  {'rule':<30}" + "".join(f"{rg:>16}" for rg in regimes)
    print(hdr)
    for name in names:
        if name == "nothing":
            continue
        cells = []
        for rg in regimes:
            sub = [t for t in mag if t.rec["regime"] == rg
                   and t.rec["trade_id"] in results[name]]
            if not sub:
                cells.append(f"{'—':>16}")
                continue
            mean = sum(results[name][t.rec["trade_id"]].kept_r for t in sub) / len(sub)
            cells.append(f"{mean:>+11.2f} (n{len(sub)})")
        print(f"  {name:<30}" + "".join(cells))

    # optimistic sensitivity (aggregate only)
    print("\n--- AMBIGUITY SENSITIVITY (all 43): mean kept, pessimistic vs optimistic ----")
    allt = trades
    for name in names:
        if name == "actual":
            continue
        rs = [results[name][t.rec["trade_id"]] for t in allt
              if t.rec["trade_id"] in results[name]]
        p = sum(r.kept_r for r in rs) / len(rs)
        o = sum(r.kept_r_opt for r in rs) / len(rs)
        if abs(p - o) > 1e-9:
            print(f"  {name:<28} pess {fmt(p)}  opt {fmt(o)}   spread {fmt(o - p)}")

    # fill-realism split
    print("\n--- FILL-REALISM SPLIT — R-trigger rules, live cohort -----------------------")
    live = by_cohort["live/magna53"]
    bars_live = [t for t in live if all(d.covered for d in t.days)]
    print(f"  bar-covered live trades: {len(bars_live)} of {len(live)} "
          f"({[t.rec['ticker'] for t in bars_live]})")
    for name in [n for n in names if n.startswith("R")]:
        rs_all = [(t, results[name][t.rec["trade_id"]]) for t in live
                  if t.rec["trade_id"] in results[name]]
        trig_realism = defaultdict(int)
        for t, r in rs_all:
            if r.triggered:
                trig_realism[r.realism] += 1
        sub = [(t, r) for t, r in rs_all if all(d.covered for d in t.days)]
        m_all = sum(r.kept_r for _, r in rs_all) / len(rs_all)
        m_sub = sum(r.kept_r for _, r in sub) / len(sub) if sub else None
        print(f"  {name:<28} full n={len(rs_all)} kept {fmt(m_all)}   "
              f"bars-only n={len(sub)} kept {fmt(m_sub)}   trigger-evidence {dict(trig_realism)}")

    # excluding legacy leg artifacts
    clean = [t for t in trades if "legs_inconsistent" not in t.flags]
    print(f"\n--- EXCLUDING legs_inconsistent trades (n={len(clean)} of 43) — all cohorts pooled ---")
    print(f"  {'candidate':<28} {'kept':>7} {'Δactual':>8} {'Δnothing':>9}")
    for (name, n, trig, mean, da, dn, *_rest) in agg(names, clean):
        print(f"  {name:<28} {fmt(mean)} {fmt(da, 8)} {fmt(dn, 9)}")

    # per-trade appendix, paper cohorts
    print("\n--- PER-TRADE APPENDIX, PAPER COHORTS (kept under key candidates) -----------")
    print(f"  {'id':>4} {'tkr':<5} {'sig':<8} {'peak_r':>7} " +
          " ".join(f"{c[:11]:>11}" for c in key_cands) + "  flags")
    for co in ("paper/magna53", "paper/9m_day2"):
        for t in by_cohort[co]:
            tid = t.rec["trade_id"]
            row = f"  {tid:>4} {t.rec['ticker']:<5} {t.rec['signal_type']:<8} {fmt(t.rec['peak_r'])} "
            row += " ".join(fmt(results[c][tid].kept_r, 11) for c in key_cands)
            fl = ",".join(sorted(t.flags))
            marg = [c for c in key_cands if results[c][tid].marginal]
            if marg:
                fl += (";" if fl else "") + "marginal:" + "|".join(m.split("_")[0] for m in marg)
            print(row + "  " + (fl or "-"))

    # regime cut
    print("\n--- REGIME CUT (regime@alert_date via date join) — mean kept, n per cell ----")
    regimes = sorted({t.rec["regime"] for t in trades})
    show = ["actual", "nothing", "R1_part1/3+BE", "R2_part1/3+BE", "R2_exit_all"]
    for co in cohorts:
        ts = by_cohort[co]
        print(f"  {co}:")
        for rg in regimes:
            sub = [t for t in ts if t.rec["regime"] == rg]
            if not sub:
                continue
            cells = "  ".join(
                f"{name.split('_')[0]}={fmt(_mean_over(results[name], sub))}"
                for name in show)
            note = "  (n<5 — DO NOT read a preference from this cell)" if len(sub) < 5 else ""
            print(f"    {rg:<11} n={len(sub):<3} {cells}{note}")

    # days-vs-R opportunity table
    print("\n--- THE OPERATOR'S QUESTION — what does each GATE ever get to see? -----------")
    print("  (per cohort: trades where the gate's precondition occurred at all, in-hold)")
    for co in cohorts:
        ts = by_cohort[co]
        n = len(ts)
        d3 = sum(1 for t in ts if len(_inhold_closes(t)) >= 3)
        d1 = sum(1 for t in ts if len(_inhold_closes(t)) >= 1)
        r1 = sum(1 for t in ts if (t.rec["peak_r"] or -9) >= 1.0)
        r2 = sum(1 for t in ts if (t.rec["peak_r"] or -9) >= 2.0)
        r3 = sum(1 for t in ts if (t.rec["peak_r"] or -9) >= 3.0)
        c1 = sum(1 for t in ts if any(t.to_r(d.close) >= 1.0 for _, d in _inhold_closes(t)))
        print(f"  {co:<16} n={n:<3} survives-to-d3-close {d3:>2}   has-any-close {d1:>2}   "
              f"touched+1R {r1:>2}  +2R {r2:>2}  +3R {r3:>2}   closed>=+1R {c1:>2}")
    print()


if __name__ == "__main__":
    run()
