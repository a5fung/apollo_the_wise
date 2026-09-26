"""Block 5 / P6 — leaders + EP-style management on the delayed-entry lane. $0, read-only.

THE QUESTION (operator, 2026-09-26, after Block 5 found no full-exit cell pays): "Pick better plus
like our EP, we take partials and adjust stops, so there's various things in play" — and earlier the
same day: "any EP related trades are low winrate by default, what we want is always to catch big
winners while limiting losses". Block 5's grid used FULL exits only and admitted every EP name. This
probe adds (1) a leader-only SELECTION and (2) EP-style MANAGEMENT (partial, stop to breakeven,
remainder trailed) and asks, tail first, whether any cell keeps the winners while limiting losses.
Nothing is deployed; nothing here picks a stop, a target or a selection rule (THE LINE).

═══════════════════════════════ PRE-REGISTRATION ═══════════════════════════════
Everything in this block was written BEFORE the first cell was computed and is never changed after.
Population COUNTS (fires, names, sessions elapsed) were read to size the draws; no outcome was.

1. SELECTION — "leader" at the fire, from bars STRICTLY BEFORE the fire date, on `mi_daily_closes`'
   (adjusted) scale: prior close >= $5 · prior close > its 50-day SMA · that 50-day SMA > the 50-day
   SMA ending 10 sessions earlier (rising) · prior close > its 20-day SMA. Fewer than 60 prior closes
   → unclassifiable (counted, NOT a leader). Every result is reported for (a) ALL fires and (b)
   LEADERS, side by side, with the filter's size (fires, names) per checkpoint and per stop.
   Sized before any result: at s10 the filter keeps 143 of 3,398 fires (52 of 693 names); at s20,
   37 of 1,214 fires (21 of 463 names).

2. MANAGEMENT ARMS (the declared family):
   M0        the lane's incumbent settlement AS RECORDED — its own trail arm (`r_trail_sK`,
             stop → max(SMA10, SMA20) close-below, s20 time exit) on the incumbent stop; the
             no-exit arm (`r_none_sK`) is reported beside it. M0 is house-convention (a stop is
             exactly −1.00R) and is read on settled rows only.
   M1        the LIVE MAGNA53 EP exit stack as of each fire date, walked with the repo's own tools:
             `rule_eras.exit_rules_as_of(fire_date, "magna53")` → `stack_walk_inputs` →
             `walk_arm(harvest="live_ladder", trail_mode="sma")` — never re-implemented. The lane
             has no ORB, so the ORB-R frame is DECLARED, two ways, each its own draw:
               M1_orb2  ORB-R = half the arm's stop distance (the live stop IS entry − 2×ORB-R, so
                        the lane's stop plays the live stop): era D (fire >= 09-06) partial 1/3 at
                        +4R(stop units), breakeven armed at +1.5R; era C (fire < 09-06) partial at
                        +1R, breakeven only at the partial.
               M1_orb1  ORB-R = the whole stop distance: era D partial at +8R, breakeven at +3R;
                        era C partial at +2R, breakeven at the partial.
             ⚠ Most fires with 20 sessions elapsed are ERA C (08-25..08-27) — the RETIRED +2R rule;
             M1's n per era is reported beside every M1 cell so an era-C read is never taken for
             today's rule. Day 0 for `walk_arm` (it has no daily path): real 1-min bars from
             `intraday_day0_raw.csv` when they exist (fill bar = the last 1-min bar of the fire's
             5-min bucket for a minute fire; the first bar whose high reaches the level for a
             level-priced fire); otherwise a SYNTHETIC two-bar day — a fill point at the entry,
             then ONE excursion bar (the production `day0_pseudo_bars` shape) carrying the cached
             post-fire low/high for a minute fire, the whole fire-day range for a daily-grade fire,
             or {high = entry, low = day low} for a minute fire with no source (the day-0 high is
             never credited; a day low at/below the stop with no source ABSTAINS, as in P3). The
             excursion bar's open is None so the gap-through charge cannot fire on a level entry.
             `walk_arm`'s own abstains (same-bar stop+target, stop+breakeven) are counted per stop
             and named — M1's scored population is expected to be smaller than M2..Mk's.
             prior_closes = the 40 calendar days before the fire (the live tracker's window);
             walk_arm's trail starts at session 1 (the fire-day close is not in it — a known
             difference from compute_settlement, which counts day 0 as the first close).
   M2..M19   a small grid, walked by this probe's own daily-grain walker (validated below):
               partial   1/3 of the position at +2R or +3R (R = the cell's OWN stop distance),
                         sold AT the level on the first bar whose high reaches it;
               breakeven the stop moves to the entry when the high reaches +1R, or +2R, or right
                         after the partial ("part") — the raise takes effect from the NEXT bar
                         (an end-of-session order change; a raise can never be hit on the bar
                         that armed it);
               remainder whatever is open is trailed on the 10-day SMA close, the 20-day SMA close
                         (the line includes the session's own close, needs N closes, checked from
                         day 0 as compute_settlement does), or HELD to session 20 (no trail).
             2 × 3 × 3 = 18 arms.
   Stops (3) the incumbent stop · entry − 0.5×ADR$ · entry − 1.0×ADR$ (ADR$ = the real
             `compute_ep_adr_dollar`, Block 5's unit). A stop at/above the entry kills the fire.
   Within a bar: stop (low) first, then partial/breakeven (high), then trail (close) — the
   pessimistic order Block 5 used. A stop is filled at the stop level, EXCEPT a session that OPENS
   below the resting stop fills at the open (walk_arm's gap-through rule) — every walked arm is read
   GAP-CHARGED, which is what makes "losses limited" testable; M0 as recorded is not (P3 measured
   the difference at 0.03R on the incumbent cell). A breakeven stop is a resting order at the entry,
   filled on the low (or the open when it gaps below).
   DRAWS: per checkpoint = 2 selections × (M0 + 3 stops × 20 arms) = 122; two checkpoints = 244
   (recorded entry). Noise band scaled from the block's 1–3 of 294: ≤1 of 122 per checkpoint is
   noise; ≥10 is a family. The FILLABLE entry convention (entry = max(level, fire-day open) for
   level-priced fires) is run on every cell and reported BESIDE the recorded one — a robustness
   read, not extra draws.

3. CHECKPOINTS — session 20 is the bar (open positions marked at the s20 close); population =
   fires with >= 20 sessions elapsed by 2026-09-25 (fire_date <= 08-27: 1,214 fires). Because the
   leader filter at s20 (37 fires / 21 names) is below the n floor BY CONSTRUCTION, the same six-leg
   bar is applied at session 10 beside it (3,398 fires; leaders 143 / 52) — declared now, not after a
   result. Width floor: rows whose stop is >= 0.5% wide in the cell's own units (Block 5's rule);
   unfloored n reported.

4. PASS BAR (tail first) — a cell is a CANDIDATE only if ALL hold: mean R > 0 · kept >= 3R rate
   >= 3.0% · average loss (mean R over losers, gap-charged) no worse than −1.0R · mean R > 0 after
   dropping the single best NAME by summed R · n >= 100 fires over >= 40 names · positive mean in
   both time halves (s20: split at fire_date 08-27 — H2 is ONE fire date, said plainly; s10: split at
   09-08, Block 5's line — H2 is four fire dates). The COUNT of clearing cells is judged against the
   draws before any cell is named.

5. CONTROL — the same selection and management on the matched NON-FIRE sessions from P2: every
   non-fire session inside the 20-session window of each campaign where the lane fired, entered at
   that session's close (no day 0), leader flag evaluated at that session, stops 0.5×/1.0×ADR$ only
   (the incumbent stop has no non-fire analogue — stated, not substituted). Fire minus control on
   mean R and kept-3R rate per cell, so a positive cell cannot be regime drift.

6. BIG RUNNERS — re-derived (the addendum's script was not committed): every watched (ticker, EP
   date) with EP date <= 09-04 and >= 10 later sessions of bars; base = the EP-day close on the daily
   table's scale; "ran" = the highest high within 15 sessions >= +50% over base (the addendum
   counted 142, 24 at >= $5 — reproduced or the difference stated). For each arm and stop: of the
   fires in runner campaigns, how many KEEP >= 3R (fires and campaigns) versus M0, and the same
   arm's mean R on every NON-runner fire versus M0's on the same fires — the "did we keep the
   winners, and what did it cost" read. Runner fires with fewer than 20 sessions elapsed are marked
   at their last available close (said in the table).

7. VALIDATION before any cell is read: (a) this probe's walker with no partial, no breakeven and
   remainder ∈ {hold, max(SMA10,SMA20)} must reproduce the recorded `realized_r` / `realized_r_trail`
   (house-convention R) on settled rows a $0 day-0 source can walk — P3's cross-check (a); (b) the
   same walker (trail = max10_20, day-0 close excluded from the trail) against
   `walk_arm(harvest="trail_only")` on identical synthetic bars, R within 0.001 — the wiring check
   for M1's path. Both counts go in the doc.
═════════════════════════════════════════════════════════════════════════════════

Outputs: p6_summary.json + p6_cells.tsv (committed); p6_events.csv (per row × stop × arm, gitignored
with the other bulk files). Regenerate: python3 p6_leaders_mgmt.py (needs the extract_p0.sh /
extract_p3.sh pulls in this folder).
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from agents.market_intelligence.delayed_entry_shadow import (  # real code, never re-implemented
    compute_ep_adr_dollar, sma_trail_line, _trading_days,
)
from agents.market_intelligence.live_fill_counterfactuals import (  # the repo's own tools for M1
    PRIOR_CLOSES_CAL_DAYS, stack_walk_inputs, walk_arm,
)
from agents.market_intelligence.rule_eras import exit_era_label, exit_rules_as_of
from p1_probe import load_intraday_raw, load_triggers          # P1's loaders, reused
from p3_grid import day0_source, load_daily_full, sessions_after  # P3's loaders, reused

_ET = ZoneInfo("America/New_York")
LAST_SESSION = date(2026, 9, 25)
WINDOW = 20
CHECKPOINTS = (20, 10)                  # 20 = the bar; 10 beside it (pre-registered)
HALF_SPLIT = {20: date(2026, 8, 27), 10: date(2026, 9, 8)}
WIDTH_FLOOR_PCT = 0.5
TAIL_R = 3.0
_EPS = 1e-9
PASS = {"tail_pct": 3.0, "avg_loss": -1.0, "n": 100, "names": 40}
LEADER_MIN_PRICE, LEADER_MIN_HIST = 5.0, 60
RUNNER_EP_MAX, RUNNER_SESSIONS, RUNNER_MIN_SESSIONS, RUNNER_GAIN = date(2026, 9, 4), 15, 10, 1.5

PATTERNS = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")
STOPS = ("incumbent", "adr_050", "adr_100")
ADR_MULT = {"adr_050": 0.5, "adr_100": 1.0}
CONVENTIONS = ("recorded", "fillable")
SELECTIONS = ("all", "leader")
M1_ARMS = ("M1_orb2", "M1_orb1")
GRID_ARMS = tuple(f"P{p}_B{b}_{x}" for p in (2, 3) for b in ("1R", "2R", "part") for x in ("sma10", "sma20", "hold"))
MGMT_ARMS = M1_ARMS + GRID_ARMS
N_DRAWS_PER_K = len(SELECTIONS) * (1 + len(STOPS) * len(MGMT_ARMS))


def grid_params(arm):
    """P{2,3}_B{1R,2R,part}_{sma10,sma20,hold} -> (partial_r, be_r, remainder)."""
    p, b, x = arm.split("_")
    b = b[1:]                                   # "B1R" -> "1R", "Bpart" -> "part"
    be = "part" if b == "part" else float(b[:-1])
    return float(p[1:]), be, x


def _f(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── the daily-grain management walker (M2..M19 + validation arms) ────────────────────────

def sma_at(allc, i, n):
    return (sum(allc[i - n + 1:i + 1]) / n) if i + 1 >= n else None


def line_at(remainder, allc, i):
    if remainder == "sma10":
        return sma_at(allc, i, 10)
    if remainder == "sma20":
        return sma_at(allc, i, 20)
    if remainder == "max10_20":
        return sma_trail_line(allc[:i + 1])
    return None


def walk_mgmt(entry, stop, d0_bars, sess, allc, P, partial_r, be_r, remainder, trail_day0=True):
    """One position from the fire to the end of the available bars, pre-registered order within a
    bar: stop (low) -> partial / breakeven (high) -> trail (close). d0_bars = post-fire (h, l) bars
    (5-min real, cached pseudo, or the whole-day fold; [] = no day-0 event). sess = (o, h, l, c) for
    sessions 1..n. allc = the stock's full close history, P = the index of the fire-day close.
    be_r: None | float (arm on the high at entry + be_r x risk) | "part" (arm right after the partial);
    the raise takes effect from the NEXT bar. Returns (exits, remaining, closed_session, partial_taken,
    be_armed) with exits = [(session, qty, px_gap_charged, px_house, reason)]."""
    risk = entry - stop
    p_level = (entry + partial_r * risk) if partial_r else None
    be_level = (entry + be_r * risk) if isinstance(be_r, float) else None
    remaining, cur_stop, pending = 1.0, stop, None
    partial_taken = be_armed = False
    exits, closed_s = [], None
    for (h, l) in d0_bars:
        if pending is not None:
            cur_stop, pending = max(cur_stop, pending), None
        if l <= cur_stop:
            exits.append((0, remaining, cur_stop, cur_stop, "stop"))
            remaining, closed_s = 0.0, 0
            break
        if p_level is not None and not partial_taken and h >= p_level:
            q = remaining / 3
            exits.append((0, q, p_level, p_level, "partial"))
            remaining -= q
            partial_taken = True
            if be_r == "part":
                pending = entry
        if be_level is not None and not be_armed and h >= be_level:
            be_armed, pending = True, entry
    if closed_s is None and trail_day0 and remainder != "hold":
        ln = line_at(remainder, allc, P)
        if ln is not None and allc[P] < ln:
            exits.append((0, remaining, allc[P], allc[P], "trail"))
            remaining, closed_s = 0.0, 0
    if closed_s is None:
        for s, (o, h, l, c) in enumerate(sess, start=1):
            if pending is not None:
                cur_stop, pending = max(cur_stop, pending), None
            if l <= cur_stop:
                px_gap = o if (o is not None and o < cur_stop) else cur_stop
                exits.append((s, remaining, px_gap, cur_stop, "stop"))
                remaining, closed_s = 0.0, s
                break
            if p_level is not None and not partial_taken and h >= p_level:
                q = remaining / 3
                exits.append((s, q, p_level, p_level, "partial"))
                remaining -= q
                partial_taken = True
                if be_r == "part":
                    pending = entry
            if be_level is not None and not be_armed and h >= be_level:
                be_armed, pending = True, entry
            if remainder != "hold":
                ln = line_at(remainder, allc, P + s)
                if ln is not None and c < ln:
                    exits.append((s, remaining, c, c, "trail"))
                    remaining, closed_s = 0.0, s
                    break
    return exits, remaining, closed_s, partial_taken, be_armed


def r_at(exits, closed_s, entry, risk, allc, P, n_avail, K, gap=True):
    """(R, final_kind) at checkpoint K: realized exits through K plus the remainder marked at K's
    close; None when the first hole sits at/before K and the position was still open there."""
    px_i = 2 if gap else 3
    if closed_s is not None and closed_s <= K:
        pnl = sum(e[1] * (e[px_i] - entry) for e in exits)
        return pnl / risk, exits[-1][4]
    if n_avail < K:
        return None, "abstain_hole"
    done = [e for e in exits if e[0] <= K]
    rem = 1.0 - sum(e[1] for e in done)
    pnl = sum(e[1] * (e[px_i] - entry) for e in done) + rem * (allc[P + K] - entry)
    return pnl / risk, "open"


# ── rows ───────────────────────────────────────────────────────────────────────────────

def leader_flag(closes_before):
    """The pre-registered leader test on closes strictly before the date. None = unclassifiable."""
    c = closes_before
    if len(c) < LEADER_MIN_HIST:
        return None
    if c[-1] < LEADER_MIN_PRICE:
        return False
    s50, s50_prev, s20 = sum(c[-50:]) / 50, sum(c[-60:-10]) / 50, sum(c[-20:]) / 20
    return bool(c[-1] > s50 and s50 > s50_prev and c[-1] > s20)


def minute_bars_et(raw, f):
    """Polygon-shaped 1-min bars -> ascending RTH {m, o, h, l, c} on the walk scale (m = ET minute)."""
    out = []
    for b in raw or []:
        et = datetime.fromtimestamp(int(b["t"]) / 1000, tz=timezone.utc).astimezone(_ET)
        m = et.hour * 60 + et.minute
        if not (570 <= m < 960):
            continue
        out.append({"m": m, "o": b["o"] * f, "h": b["h"] * f, "l": b["l"] * f, "c": b["c"] * f})
    out.sort(key=lambda x: x["m"])
    return out


def build_row(t, conv, daily, intraday_raw, adr_by_campaign):
    dft = daily.get(t["ticker"], {})
    adr, _adr_n = adr_by_campaign[(t["ticker"], t["ep_date"])]
    if adr is None or not t["entry_price"] or t["entry_price"] <= 0:
        return None, "no_adr_or_entry"
    fb = dft.get(t["fire_date"])
    if not fb or not fb["close"] or not t["day_close"]:
        return None, "missing_fire_day_bar"
    f = fb["close"] / t["day_close"]
    level = t["entry_price"] * f
    entry = level
    level_priced = t["fire_minute_et"] is None
    if conv == "fillable" and level_priced and fb["open"] and fb["open"] > entry:
        entry = fb["open"]
    sessions = sessions_after(t["fire_date"])
    sess, hole = [], None
    for j, d in enumerate(sessions, start=1):
        b = dft.get(d)
        if not b or b["high_price"] is None or b["low_price"] is None or b["close"] is None:
            hole = j
            break
        sess.append((b["open"], b["high_price"], b["low_price"], b["close"]))
    n_avail = len(sess)
    pre_dates = [d for d in sorted(dft) if d < t["fire_date"] and dft[d]["close"] is not None]
    closes_pre = [dft[d]["close"] for d in pre_dates]
    prior_cut = t["fire_date"] - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
    prior_40 = [dft[d]["close"] for d in pre_dates if d >= prior_cut]
    allc = closes_pre + [fb["close"]] + [s[3] for s in sess]
    P = len(closes_pre)
    d0_kind, d0_bars = day0_source(t, f, dft, intraday_raw)
    if d0_kind == "missing_fire_day_bar":
        return None, "missing_fire_day_bar"
    day_low = (t["day_low"] * f) if t["day_low"] is not None else None
    raw = intraday_raw.get((t["ticker"], t["fire_date"]))
    mins = minute_bars_et(raw, f) if raw else []
    row = {
        "id": t["id"], "ticker": t["ticker"], "ep_date": t["ep_date"], "rung": t["rung"],
        "fire_date": t["fire_date"], "resolution": t["resolution"], "elapsed": len(sessions),
        "hole": hole, "n_avail": n_avail, "f": f, "entry": entry, "level": level, "adr": adr,
        "level_priced": level_priced, "d0_kind": d0_kind, "sessions": sessions, "sess": sess,
        "allc": allc, "P": P, "prior_40": prior_40, "mins": mins,
        "fire_minute": t["fire_minute_et"], "day_low": day_low,
        "day_high": (t["day_high"] * f) if t["day_high"] is not None else None,
        "day_close": fb["close"], "day_open": fb["open"],
        "leader": leader_flag(closes_pre), "era": exit_era_label(t["fire_date"], "magna53"),
        "rules": exit_rules_as_of(t["fire_date"], "magna53"),
        "half": {K: ("H1" if t["fire_date"] < HALF_SPLIT[K] else "H2") for K in CHECKPOINTS},
        "stops": {},
    }
    for s in STOPS:
        lvl = (t["stop_price"] * f if t["stop_price"] else None) if s == "incumbent" else entry - ADR_MULT[s] * adr
        if lvl is None or lvl >= entry or lvl <= 0:
            # lvl <= 0: an ADR$ wider than the price (a split-rescaled name) — a stop below zero is
            # a broken input, not a cell; counted with the at/above-entry kills, never scored
            row["stops"][s] = {"level": lvl, "killed": True, "why": "stop_le_0" if (lvl is not None and lvl <= 0) else "stop_ge_entry"}
            continue
        if d0_kind == "no_source":
            d0_abstain = day_low is not None and day_low <= lvl
            d0 = [] if not d0_abstain else None
        else:
            d0_abstain, d0 = False, d0_bars
        row["stops"][s] = {"level": lvl, "killed": False, "risk": entry - lvl,
                           "width_pct": (entry - lvl) / entry * 100.0, "d0_abstain": d0_abstain,
                           "d0_bars": d0}
    return row, None


# ── M1: the live stack through the repo's own walker ─────────────────────────────────────

def day0_for_walk_arm(row, st, conv):
    """(day0_bars, fill_idx, entry, source) for walk_arm — real 1-min bars when they exist, else the
    pre-registered synthetic two-bar day. (None, None, None, reason) = abstained before the walk."""
    entry, stop = row["entry"], st["level"]
    mins = row["mins"]
    if mins:
        if row["fire_minute"] is not None:
            cands = [i for i, b in enumerate(mins) if b["m"] <= row["fire_minute"] + 4]
            idx = cands[-1] if cands else 0
            src = "real_1min" if cands else "real_1min_fill_after_bucket"
            return mins, idx, entry, src
        cands = [i for i, b in enumerate(mins) if b["h"] >= row["level"]]
        if cands:
            idx = cands[0]
            e = max(row["level"], mins[idx]["o"]) if conv == "fillable" else row["level"]
            return mins, idx, e, "real_1min_level_touch"
        # the daily bar says the level was touched but no stored minute reaches it -> synthetic
    fill = {"m": None, "o": entry, "h": entry, "l": entry, "c": entry}
    if row["d0_kind"] == "daily_fold":
        exc = {"m": None, "o": None, "h": row["day_high"], "l": row["day_low"], "c": row["day_close"]}
        return [fill, exc], 0, entry, "synthetic_fold"
    if row["d0_kind"] == "cached_pseudo_bars":
        if st["d0_bars"]:
            h, l = st["d0_bars"][0]
            exc = {"m": None, "o": None, "h": h, "l": l, "c": row["day_close"]}
            return [fill, exc], 0, entry, "synthetic_cached"
        return [fill], 0, entry, "synthetic_cached_fire_last_bar"
    if row["d0_kind"] == "real_intraday_bars":
        # 5-min bars exist but no 1-min bar sits at/after the fire minute: fold the post-fire 5-min range
        if st["d0_bars"]:
            h = max(b[0] for b in st["d0_bars"]); l = min(b[1] for b in st["d0_bars"])
            exc = {"m": None, "o": None, "h": h, "l": l, "c": row["day_close"]}
            return [fill, exc], 0, entry, "synthetic_5min_fold"
        return [fill], 0, entry, "synthetic_5min_fire_last_bar"
    # no_source minute fire
    if row["day_low"] is not None and row["day_low"] <= stop:
        return None, None, None, "abstain_no_day0_source_low_reached_stop"
    exc = {"m": None, "o": None, "h": entry, "l": row["day_low"] if row["day_low"] is not None else entry,
           "c": row["day_close"]}
    return [fill, exc], 0, entry, "synthetic_no_source"


def walk_arm_sessions(row):
    out = []
    for j, d in enumerate(row["sessions"]):
        if j < row["n_avail"]:
            o, h, l, c = row["sess"][j]
            out.append((d, {"o": o, "h": h, "l": l, "c": c}))
        else:
            out.append((d, None))
    return out


def run_m1(row, st, conv, arm, K, sessions_wa):
    """walk_arm on the live stack as of the fire date. Returns (status, R, meta)."""
    entry_row, stop = row["entry"], st["level"]
    d0, idx, entry, src = day0_for_walk_arm(row, st, conv)
    if d0 is None:
        return "abstain", None, {"reason": src, "src": src}
    risk = entry - stop
    if risk <= 0:
        return "killed", None, {"reason": "fillable_entry_at_or_below_stop", "src": src}
    orb_low = entry - risk / 2.0 if arm == "M1_orb2" else stop
    target, kw = stack_walk_inputs(row["rules"], entry, orb_low)
    res = walk_arm(entry=entry, stop=stop, target=target, day0_bars=d0, fill_idx=idx,
                   sessions=sessions_wa[:K] if K < WINDOW else sessions_wa,
                   prior_closes=row["prior_40"], harvest="live_ladder", fill_day=row["fire_date"],
                   horizon=K, trail_mode="sma", **kw)
    meta = {"src": src, "partial": bool(res.get("partial_fired")), "reason": res.get("reason"),
            "final": res.get("final_reason"), "gap": bool(res.get("gap_through")), "entry": entry,
            "target_r": (target - entry) / risk if target else None,
            "be_r": (kw["breakeven_at_r"] * kw["r_frame_ps"] / risk) if kw["breakeven_at_r"] else None}
    if res["status"] == "settled":
        return "scored", res["pnl_per_share"] / risk, meta
    if res["status"] == "horizon":
        meta["final"] = "open"
        return "scored", res["mark_pnl_per_share"] / risk, meta
    if res["status"] == "pending" and res.get("reason") == "open_walk_not_definitive":
        # only reached when fewer than K sessions exist (the runner read): mark at the last close
        pnl = sum(e["pnl"] for e in res["exits"])
        last_close = row["sess"][row["n_avail"] - 1][3] if row["n_avail"] else entry
        meta["final"] = "open_marked_last"
        return "marked_last", (pnl + (last_close - entry) * res["remaining"]) / risk, meta
    return res["status"], None, meta


# ── aggregation + the bar ────────────────────────────────────────────────────────────────

def _mean(v):
    return round(float(np.mean(v)), 4) if len(v) else None


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def aggregate(scored, K, is_fire=True):
    """scored: list of dicts {row, R, kind, partial, be, width_ok, era}."""
    fl = [x for x in scored if x["width_ok"]]
    R = [x["R"] for x in fl]
    n = len(R)
    losses = [r for r in R if r < 0]
    tail = sum(1 for r in R if r >= TAIL_R - _EPS)
    out = {"n": n, "n_unfloored": len(scored), "n_names": len({x["row"]["ticker"] for x in fl}),
           "mean_r": _mean(R), "sum_r": round(float(np.sum(R)), 2) if n else None,
           "median_r": round(float(np.median(R)), 4) if n else None,
           "tail3": tail, "tail3_pct": _pct(tail, n),
           "win_pct": _pct(sum(1 for r in R if r > 0), n),
           "avg_loss": _mean(losses), "loss_pct": _pct(len(losses), n),
           "worst_r": round(min(R), 3) if n else None, "best_r": round(max(R), 3) if n else None,
           "stop_pct": _pct(sum(1 for x in fl if x["kind"] == "stop"), n),
           "trail_pct": _pct(sum(1 for x in fl if x["kind"] in ("trail", "sma_trail_stop")), n),
           "open_pct": _pct(sum(1 for x in fl if x["kind"] == "open"), n),
           "partial_pct": _pct(sum(1 for x in fl if x["partial"]), n),
           "be_pct": _pct(sum(1 for x in fl if x["be"]), n)}
    by_name = defaultdict(float)
    for x in fl:
        by_name[x["row"]["ticker"]] += x["R"]
    if by_name:
        best = max(by_name, key=by_name.get)
        v = [x["R"] for x in fl if x["row"]["ticker"] != best]
        out["drop_best"] = {"name": best, "name_sum_r": round(by_name[best], 2), "n": len(v),
                            "mean_r": _mean(v), "tail3_pct": _pct(sum(1 for r in v if r >= TAIL_R - _EPS), len(v))}
    else:
        out["drop_best"] = {"name": None, "n": 0, "mean_r": None, "tail3_pct": None}
    hv = {}
    for h in ("H1", "H2"):
        v = [x["R"] for x in fl if x["row"]["half"][K] == h] if is_fire else []
        hv[h] = {"n": len(v), "mean_r": _mean(v), "tail3": sum(1 for r in v if r >= TAIL_R - _EPS)}
    out["halves"] = hv
    if is_fire:
        pat = {}
        for p in PATTERNS:
            v = [x["R"] for x in fl if x["row"]["rung"] == p]
            pat[p] = {"n": len(v), "mean_r": _mean(v), "tail3_pct": _pct(sum(1 for r in v if r >= TAIL_R - _EPS), len(v))}
        out["per_pattern"] = pat
    era = {}
    for e in ("era_c", "era_d"):
        v = [x["R"] for x in fl if x.get("era") == e]
        era[e] = {"n": len(v), "mean_r": _mean(v), "tail3_pct": _pct(sum(1 for r in v if r >= TAIL_R - _EPS), len(v))}
    out["per_era"] = era
    return out


def legs(agg):
    d, h = agg["drop_best"], agg["halves"]
    L = {"mean_r_gt_0": agg["mean_r"] is not None and agg["mean_r"] > 0,
         "tail3_ge_3pct": agg["tail3_pct"] is not None and agg["tail3_pct"] >= PASS["tail_pct"],
         "avg_loss_ge_m1": agg["avg_loss"] is None or agg["avg_loss"] >= PASS["avg_loss"] - _EPS,
         "drop_best_name": d["mean_r"] is not None and d["mean_r"] > 0,
         "n_ge_100_names_ge_40": agg["n"] >= PASS["n"] and agg["n_names"] >= PASS["names"],
         "both_halves_positive": all(h[k]["mean_r"] is not None and h[k]["mean_r"] > 0 for k in ("H1", "H2"))}
    L["clears"] = all(L.values())
    return L


def m0_agg(rows, triggers_by_id, K, sel, arm_col):
    """M0 as recorded: r_trail_sK / r_none_sK on settled rows of the population (house convention)."""
    scored = []
    for row in rows:
        if row["elapsed"] < K or (sel == "leader" and not row["leader"]):
            continue
        t = triggers_by_id[row["id"]]
        r = _f(t.get(arm_col))
        if r is None or t["outcome"] not in ("stop", "time_exit"):
            continue
        st = row["stops"]["incumbent"]
        if st["killed"]:
            continue
        scored.append({"row": row, "R": r, "kind": t["outcome"], "partial": False, "be": False,
                       "width_ok": st["width_pct"] >= WIDTH_FLOOR_PCT, "era": row["era"]})
    return aggregate(scored, K)


# ── main ───────────────────────────────────────────────────────────────────────────────

def main():
    triggers = load_triggers()
    triggers_by_id = {t["id"]: t for t in triggers}
    daily = load_daily_full()
    intraday_raw = load_intraday_raw()
    print(f"triggers {len(triggers)} · draws per checkpoint {N_DRAWS_PER_K} = {len(SELECTIONS)} selections x "
          f"(M0 + {len(STOPS)} stops x {len(MGMT_ARMS)} arms); checkpoints {CHECKPOINTS}")

    adr_by_campaign = {}
    for t in triggers:
        key = (t["ticker"], t["ep_date"])
        if key in adr_by_campaign:
            continue
        dft = daily.get(t["ticker"], {})
        bars_asc = [dft[d] for d in sorted(dft)]
        ep_bar = dft.get(t["ep_date"])
        adr_by_campaign[key] = compute_ep_adr_dollar(bars_asc, t["ep_date"], ep_bar["close"] if ep_bar else None)

    rows = {c: [] for c in CONVENTIONS}
    excluded = Counter()
    for conv in CONVENTIONS:
        for t in triggers:
            row, why = build_row(t, conv, daily, intraday_raw, adr_by_campaign)
            if row is None:
                excluded[(conv, why)] += 1
                continue
            rows[conv].append(row)
        print(f"[{conv}] rows {len(rows[conv])}; excluded {dict((k[1], v) for k, v in excluded.items() if k[0] == conv)}")

    # selection size (population description)
    sel_size = {}
    for K in CHECKPOINTS:
        pop = [r for r in rows["recorded"] if r["elapsed"] >= K]
        lead = [r for r in pop if r["leader"]]
        sel_size[K] = {"all_fires": len(pop), "all_names": len({r["ticker"] for r in pop}),
                       "leader_fires": len(lead), "leader_names": len({r["ticker"] for r in lead}),
                       "unclassifiable": sum(1 for r in pop if r["leader"] is None),
                       "leader_by_pattern": dict(Counter(r["rung"] for r in lead)),
                       "leader_era": dict(Counter(r["era"] for r in lead)),
                       "all_era": dict(Counter(r["era"] for r in pop)),
                       "leader_names_list": sorted({r["ticker"] for r in lead})}
    print("selection size:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'leader_names_list'} for k, v in sel_size.items()}))

    # ── VALIDATION (a): walker vs the recorded settlement (house R, incumbent stop) ──
    va = Counter()
    for row in rows["recorded"]:
        t = triggers_by_id[row["id"]]
        if t["outcome"] not in ("stop", "time_exit") or t["realized_r"] is None:
            continue
        st = row["stops"]["incumbent"]
        if st["killed"] or st["d0_abstain"]:
            va["day0_abstain_or_killed"] += 1
            continue
        ok = True
        for rem, col in (("hold", "realized_r"), ("max10_20", "realized_r_trail")):
            ex, remn, cs, _, _ = walk_mgmt(row["entry"], st["level"], st["d0_bars"], row["sess"], row["allc"], row["P"], None, None, rem)
            r, _k = r_at(ex, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], WINDOW, gap=False)
            rec = _f(t[col])
            if r is None or rec is None:
                va[f"{rem}_not_walkable"] += 1
                continue
            m = abs(r - rec) <= 0.002
            va[f"{rem}_match" if m else f"{rem}_mismatch"] += 1
            if not m and va["printed"] < 6:
                va["printed"] += 1
                print(f"  (a) mismatch {row['ticker']} {row['fire_date']} {rem}: probe={r:.4f} rec={rec}")
    va.pop("printed", None)
    print("VALIDATION (a) walker vs recorded:", dict(va))

    # ── VALIDATION (b): walker (trail max10_20, no partial/BE, day-0 close excluded) vs walk_arm(trail_only) ──
    vb = Counter()
    for row in rows["recorded"]:
        if row["elapsed"] < WINDOW or row["mins"]:
            continue
        st = row["stops"]["adr_100"]
        if st["killed"] or st["d0_abstain"]:
            continue
        d0, idx, entry, src = day0_for_walk_arm(row, st, "recorded")
        if d0 is None:
            continue
        sw = walk_arm_sessions(row)
        res = walk_arm(entry=entry, stop=st["level"], target=None, day0_bars=d0, fill_idx=idx, sessions=sw,
                       prior_closes=row["prior_40"], harvest="trail_only", fill_day=row["fire_date"],
                       horizon=WINDOW, trail_mode="sma", breakeven_at_partial=True, trail_prior_closes=True,
                       ladder_partial=False,
                       breakeven_at_r=None)   # the trail_only validation arm has no breakeven by its own rule
                                              # (walk_arm rejects one); stated, never left to the default
        ex, remn, cs, _, _ = walk_mgmt(row["entry"], st["level"], st["d0_bars"], row["sess"], row["allc"], row["P"], None, None, "max10_20", trail_day0=False)
        r_mine, _k = r_at(ex, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], WINDOW, gap=True)
        if res["status"] == "settled":
            r_wa = res["pnl_per_share"] / st["risk"]
        elif res["status"] == "horizon":
            r_wa = res["mark_pnl_per_share"] / st["risk"]
        else:
            vb[f"walk_arm_{res['status']}:{(res.get('reason') or '')[:28]}"] += 1
            continue
        if r_mine is None:
            vb["mine_abstain"] += 1
            continue
        m = abs(r_mine - r_wa) <= 0.001
        if m:
            vb["match"] += 1
        else:
            # the live ladder carries the broker's RAISE-ONLY RESTING STOP: after each session the
            # resting stop ratchets to max(hard stop, trail line) and the NEXT session's LOW can hit
            # it at that level (a stop_hit priced ABOVE the hard stop); compute_settlement / this
            # walker exit only on a CLOSE below the line. Classify every mismatch by that signature.
            last = res["exits"][-1] if res["exits"] else None
            raised = (last is not None and last["reason"] == "stop_hit" and last["price"] > st["level"] + 1e-9)
            vb["mismatch_raised_resting_stop_hit_on_low" if raised else "mismatch_other"] += 1
        if not m and vb["printed"] < 6:
            vb["printed"] += 1
            print(f"  (b) mismatch {row['ticker']} {row['fire_date']} {src}: mine={r_mine:.4f} walk_arm={r_wa:.4f} final={res.get('final_reason')} exits={[(e['reason'], round(e['price'],3), e['time']) for e in res['exits']]} mine_exits={[(e[4], e[0], round(e[2],3)) for e in ex]}")
    vb.pop("printed", None)
    print("VALIDATION (b) walker vs walk_arm(trail_only):", dict(vb))

    # ── walks: every row x stop x arm, both checkpoints + the runner mark ──
    events = []       # per (conv, row, stop, arm): R20, R10, R_final(last mark), kinds
    per_row = {c: {} for c in CONVENTIONS}
    status_ct = Counter()
    for conv in CONVENTIONS:
        for row in rows[conv]:
            sw = walk_arm_sessions(row)
            for s in STOPS:
                st = row["stops"][s]
                if st["killed"]:
                    status_ct[(conv, s, "killed", st.get("why", ""))] += 1
                    continue
                if st["d0_abstain"]:
                    status_ct[(conv, s, "d0_abstain")] += 1
                    continue
                for arm in MGMT_ARMS:
                    rec = {"R": {}, "kind": {}, "partial": False, "be": False, "era": row["era"]}
                    if arm in M1_ARMS:
                        for K in CHECKPOINTS:
                            if row["elapsed"] < K:
                                continue
                            stt, r, meta = run_m1(row, st, conv, arm, K, sw)
                            status_ct[(conv, s, arm, K, stt, meta.get("reason") if stt != "scored" else "")] += 1
                            if stt == "scored":
                                rec["R"][K], rec["kind"][K] = r, meta["final"] or "open"
                                rec["partial"] = rec["partial"] or meta["partial"]
                                rec["src"] = meta["src"]
                        # the runner mark: horizon 20 even when fewer sessions exist
                        stt, r, meta = run_m1(row, st, conv, arm, WINDOW, sw)
                        if stt in ("scored", "marked_last"):
                            rec["R_final"], rec["final_kind"] = r, meta["final"]
                            rec["partial"] = rec["partial"] or meta["partial"]
                    else:
                        p_r, be_r, remn_mode = grid_params(arm)
                        ex, remn, cs, pt, be = walk_mgmt(row["entry"], st["level"], st["d0_bars"], row["sess"], row["allc"], row["P"], p_r, be_r, remn_mode)
                        rec["partial"], rec["be"] = pt, be
                        for K in CHECKPOINTS:
                            if row["elapsed"] < K:
                                continue
                            r, k = r_at(ex, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], K, gap=True)
                            if r is None:
                                status_ct[(conv, s, arm, K, "abstain_hole", "")] += 1
                                continue
                            rec["R"][K], rec["kind"][K] = r, k
                        # runner mark: through s20 or the last available close
                        Kf = min(WINDOW, row["n_avail"])
                        if Kf > 0 or cs is not None:
                            r, k = r_at(ex, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], Kf if Kf > 0 else 0, gap=True)
                            if r is not None:
                                rec["R_final"], rec["final_kind"] = r, k
                    per_row[conv][(row["id"], s, arm)] = rec
                    events.append({"convention": conv, "id": row["id"], "ticker": row["ticker"], "rung": row["rung"],
                                   "fire_date": row["fire_date"].isoformat(), "leader": row["leader"], "era": row["era"],
                                   "stop": s, "arm": arm, "width_pct": round(st["width_pct"], 4),
                                   "R_s20": rec["R"].get(20), "kind_s20": rec["kind"].get(20),
                                   "R_s10": rec["R"].get(10), "kind_s10": rec["kind"].get(10),
                                   "R_final": rec.get("R_final"), "final_kind": rec.get("final_kind"),
                                   "partial": rec["partial"], "be": rec["be"], "d0_src": rec.get("src", row["d0_kind"])})
        print(f"[{conv}] walks done: {len(per_row[conv])} (row, stop, arm) records")

    # ── cells ──
    cells = {}
    for conv in CONVENTIONS:
        for K in CHECKPOINTS:
            for sel in SELECTIONS:
                if conv == "recorded":
                    for arm_col, name in (("r_trail_s%d" % K, "M0_trail"), ("r_none_s%d" % K, "M0_none")):
                        a = m0_agg(rows[conv], triggers_by_id, K, sel, arm_col)
                        a["legs"] = legs(a)
                        cells[(conv, K, sel, "incumbent", name)] = a
                for s in STOPS:
                    for arm in MGMT_ARMS:
                        scored = []
                        for row in rows[conv]:
                            if row["elapsed"] < K or (sel == "leader" and not row["leader"]):
                                continue
                            rec = per_row[conv].get((row["id"], s, arm))
                            if rec is None or K not in rec["R"]:
                                continue
                            scored.append({"row": row, "R": rec["R"][K], "kind": rec["kind"][K], "partial": rec["partial"],
                                           "be": rec["be"], "width_ok": row["stops"][s]["width_pct"] >= WIDTH_FLOOR_PCT,
                                           "era": row["era"]})
                        a = aggregate(scored, K)
                        a["legs"] = legs(a)
                        cells[(conv, K, sel, s, arm)] = a

    # ── CONTROL: matched non-fire sessions, entered at the close ──
    fires_by_campaign = defaultdict(set)
    for t in triggers:
        fires_by_campaign[(t["ticker"], t["ep_date"])].add(t["fire_date"])
    ctl_rows, ctl_skip = [], Counter()
    for (ticker, ep_date), fire_dates in fires_by_campaign.items():
        adr, _ = adr_by_campaign[(ticker, ep_date)]
        if adr is None:
            ctl_skip["no_adr"] += 1
            continue
        dft = daily.get(ticker, {})
        window = _trading_days(ep_date + timedelta(days=1), LAST_SESSION)[:WINDOW]
        for j, sdate in enumerate(window, start=1):
            if sdate in fire_dates:
                continue
            b = dft.get(sdate)
            if not b or b["close"] is None:
                ctl_skip["no_close_bar"] += 1
                continue
            entry = b["close"]
            after = _trading_days(sdate + timedelta(days=1), LAST_SESSION)[:WINDOW]
            sess, hole = [], None
            for jj, d in enumerate(after, start=1):
                bb = dft.get(d)
                if not bb or bb["high_price"] is None or bb["low_price"] is None or bb["close"] is None:
                    hole = jj
                    break
                sess.append((bb["open"], bb["high_price"], bb["low_price"], bb["close"]))
            pre_dates = [d for d in sorted(dft) if d < sdate and dft[d]["close"] is not None]
            closes_pre = [dft[d]["close"] for d in pre_dates]
            prior_cut = sdate - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
            row = {"id": f"{ticker}|{ep_date}|{sdate}", "ticker": ticker, "ep_date": ep_date, "rung": "control",
                   "fire_date": sdate, "elapsed": len(after), "hole": hole, "n_avail": len(sess), "entry": entry,
                   "level": entry, "adr": adr, "sessions": after, "sess": sess,
                   "allc": closes_pre + [entry] + [x[3] for x in sess], "P": len(closes_pre),
                   "prior_40": [dft[d]["close"] for d in pre_dates if d >= prior_cut], "mins": [],
                   "fire_minute": None, "day_low": None, "day_high": None, "day_close": entry, "day_open": b["open"],
                   "leader": leader_flag(closes_pre), "era": exit_era_label(sdate, "magna53"),
                   "rules": exit_rules_as_of(sdate, "magna53"), "d0_kind": "control_close",
                   "half": {K: ("H1" if sdate < HALF_SPLIT[K] else "H2") for K in CHECKPOINTS}, "stops": {}}
            for s in ("adr_050", "adr_100"):
                lvl = entry - ADR_MULT[s] * adr
                row["stops"][s] = {"level": lvl, "killed": lvl >= entry, "risk": entry - lvl,
                                   "width_pct": (entry - lvl) / entry * 100.0, "d0_abstain": False, "d0_bars": []}
            ctl_rows.append(row)
    print(f"control sessions {len(ctl_rows)}; skipped {dict(ctl_skip)}; leaders "
          f"{sum(1 for r in ctl_rows if r['leader'])}")
    ctl_cells = {}
    ctl_recs = {}
    for row in ctl_rows:
        sw = walk_arm_sessions(row)
        for s in ("adr_050", "adr_100"):
            st = row["stops"][s]
            if st["killed"]:
                continue
            for arm in MGMT_ARMS:
                rec = {"R": {}, "kind": {}, "partial": False, "be": False}
                if arm in M1_ARMS:
                    for K in CHECKPOINTS:
                        if row["elapsed"] < K:
                            continue
                        d0 = [{"m": None, "o": row["entry"], "h": row["entry"], "l": row["entry"], "c": row["entry"]}]
                        orb_low = row["entry"] - st["risk"] / 2.0 if arm == "M1_orb2" else st["level"]
                        target, kw = stack_walk_inputs(row["rules"], row["entry"], orb_low)
                        res = walk_arm(entry=row["entry"], stop=st["level"], target=target, day0_bars=d0, fill_idx=0,
                                       sessions=sw[:K], prior_closes=row["prior_40"], harvest="live_ladder",
                                       fill_day=row["fire_date"], horizon=K, trail_mode="sma", **kw)
                        if res["status"] == "settled":
                            rec["R"][K], rec["kind"][K] = res["pnl_per_share"] / st["risk"], res["final_reason"]
                        elif res["status"] == "horizon":
                            rec["R"][K], rec["kind"][K] = res["mark_pnl_per_share"] / st["risk"], "open"
                        rec["partial"] = rec["partial"] or bool(res.get("partial_fired"))
                else:
                    p_r, be_r, remn_mode = grid_params(arm)
                    ex, remn, cs, pt, be = walk_mgmt(row["entry"], st["level"], [], row["sess"], row["allc"], row["P"], p_r, be_r, remn_mode)
                    rec["partial"], rec["be"] = pt, be
                    for K in CHECKPOINTS:
                        if row["elapsed"] < K:
                            continue
                        r, k = r_at(ex, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], K, gap=True)
                        if r is not None:
                            rec["R"][K], rec["kind"][K] = r, k
                ctl_recs[(row["id"], s, arm)] = rec
    for K in CHECKPOINTS:
        for sel in SELECTIONS:
            for s in ("adr_050", "adr_100"):
                for arm in MGMT_ARMS:
                    scored = []
                    for row in ctl_rows:
                        if row["elapsed"] < K or (sel == "leader" and not row["leader"]):
                            continue
                        rec = ctl_recs.get((row["id"], s, arm))
                        if rec is None or K not in rec["R"]:
                            continue
                        scored.append({"row": row, "R": rec["R"][K], "kind": rec["kind"][K], "partial": rec["partial"],
                                       "be": rec["be"], "width_ok": row["stops"][s]["width_pct"] >= WIDTH_FLOOR_PCT,
                                       "era": row["era"]})
                    ctl_cells[(K, sel, s, arm)] = aggregate(scored, K, is_fire=False)

    # ── BIG RUNNERS (re-derived on the addendum's definition) ──
    campaigns = set()
    with open(HERE / "watch.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            campaigns.add((r["ticker"], date.fromisoformat(r["ep_date"])))
    runners, runner_stats = set(), Counter()
    runner_detail = {}
    for (ticker, ep) in campaigns:
        if ep > RUNNER_EP_MAX:
            continue
        dft = daily.get(ticker, {})
        eb = dft.get(ep)
        if not eb or not eb["close"]:
            runner_stats["no_ep_bar"] += 1
            continue
        after = _trading_days(ep + timedelta(days=1), LAST_SESSION)[:RUNNER_SESSIONS]
        highs = [dft[d]["high_price"] for d in after if d in dft and dft[d]["high_price"] is not None]
        if len(highs) < RUNNER_MIN_SESSIONS:
            runner_stats["lt_10_sessions"] += 1
            continue
        runner_stats["watched"] += 1
        base = eb["close"]
        if base >= LEADER_MIN_PRICE:
            runner_stats["watched_ge5"] += 1
        mx = max(highs) / base
        if mx >= RUNNER_GAIN:
            runners.add((ticker, ep))
            runner_stats["ran"] += 1
            if base >= LEADER_MIN_PRICE:
                runner_stats["ran_ge5"] += 1
            runner_detail[f"{ticker}|{ep}"] = {"base": base, "max_up_pct": round(100 * (mx - 1), 1),
                                              "fired": (ticker, ep) in fires_by_campaign}
    runner_stats["ran_and_lane_fired"] = sum(1 for c in runners if c in fires_by_campaign)
    print("runners:", dict(runner_stats), "(addendum: 142 ran, 24 at >= $5, lane fired on 102)")
    runner_read = {}
    fire_rows_rec = rows["recorded"]
    m0_trail_by_id = {}
    for row in fire_rows_rec:
        t = triggers_by_id[row["id"]]
        r = _f(t["realized_r_trail"])
        st = row["stops"]["incumbent"]
        if r is not None and t["outcome"] in ("stop", "time_exit") and not st["killed"] and st["width_pct"] >= WIDTH_FLOOR_PCT:
            m0_trail_by_id[row["id"]] = r
    for s in STOPS:
        for arm in ("M0_trail", "M0_none") + MGMT_ARMS:
            if arm.startswith("M0") and s != "incumbent":
                continue
            run_r, other_r, camp_hit, camp_all = [], [], set(), set()
            run_names = set()
            paired_arm, paired_m0 = [], []   # non-runner fires scored by BOTH this arm and M0_trail
            for row in fire_rows_rec:
                is_run = (row["ticker"], row["ep_date"]) in runners
                st = row["stops"][s]
                if st["killed"] or st["width_pct"] < WIDTH_FLOOR_PCT:
                    continue
                if arm.startswith("M0"):
                    t = triggers_by_id[row["id"]]
                    r = _f(t["realized_r_trail" if arm == "M0_trail" else "realized_r"])
                    if r is None or t["outcome"] not in ("stop", "time_exit"):
                        continue
                else:
                    rec = per_row["recorded"].get((row["id"], s, arm))
                    if rec is None or rec.get("R_final") is None:
                        continue
                    r = rec["R_final"]
                if is_run:
                    run_r.append(r)
                    camp_all.add((row["ticker"], row["ep_date"]))
                    run_names.add(row["ticker"])
                    if r >= TAIL_R - _EPS:
                        camp_hit.add((row["ticker"], row["ep_date"]))
                else:
                    other_r.append(r)
                    if row["id"] in m0_trail_by_id:
                        paired_arm.append(r)
                        paired_m0.append(m0_trail_by_id[row["id"]])
            runner_read[(s, arm)] = {
                "other_paired_n": len(paired_arm), "other_paired_mean_r": _mean(paired_arm),
                "other_paired_m0_trail_mean_r": _mean(paired_m0),
                "net_sum_r_all_fires": round(float(sum(run_r) + sum(other_r)), 1),
                "net_mean_r_all_fires": _mean(run_r + other_r),
                "runner_fires": len(run_r), "runner_names": len(run_names),
                "runner_kept3": sum(1 for r in run_r if r >= TAIL_R - _EPS),
                "runner_kept3_pct": _pct(sum(1 for r in run_r if r >= TAIL_R - _EPS), len(run_r)),
                "runner_campaigns": len(camp_all), "runner_campaigns_kept3": len(camp_hit),
                "runner_mean_r": _mean(run_r), "runner_median_r": round(float(np.median(run_r)), 3) if run_r else None,
                "other_fires": len(other_r), "other_mean_r": _mean(other_r),
                "other_tail3_pct": _pct(sum(1 for r in other_r if r >= TAIL_R - _EPS), len(other_r)),
                "other_avg_loss": _mean([r for r in other_r if r < 0]),
            }

    # ── verdict ──
    verdict = {}
    for K in CHECKPOINTS:
        draws = [(k, a) for k, a in cells.items() if k[0] == "recorded" and k[1] == K and k[4] != "M0_none"]
        clearing = [k for k, a in draws if a["legs"]["clears"]]
        leg_fail = Counter()
        for _k, a in draws:
            for leg, ok in a["legs"].items():
                if leg != "clears" and not ok:
                    leg_fail[leg] += 1
        per_sel = {}
        for sel in SELECTIONS:
            ds = [(k, a) for k, a in draws if k[2] == sel]
            pos = [(k, a) for k, a in ds if a["mean_r"] is not None and a["mean_r"] > 0]
            tail_ok = [(k, a) for k, a in ds if a["tail3_pct"] is not None and a["tail3_pct"] >= PASS["tail_pct"]]
            both = [(k, a) for k, a in pos if a["tail3_pct"] is not None and a["tail3_pct"] >= PASS["tail_pct"]]
            best_tail = sorted(ds, key=lambda x: -(x[1]["tail3_pct"] or 0))[:5]
            best_mean = sorted(ds, key=lambda x: -(x[1]["mean_r"] if x[1]["mean_r"] is not None else -9))[:5]
            per_sel[sel] = {
                "draws": len(ds), "clearing": ["/".join(map(str, k[3:])) for k, a in ds if a["legs"]["clears"]],
                "cells_mean_pos": len(pos), "cells_tail_ge_3pct": len(tail_ok), "cells_mean_pos_and_tail": len(both),
                "n_range": [min((a["n"] for _, a in ds), default=0), max((a["n"] for _, a in ds), default=0)],
                "best_tail_cells": [("/".join(map(str, k[3:])), a["tail3_pct"], a["mean_r"], a["n"], a["n_names"]) for k, a in best_tail],
                "best_mean_cells": [("/".join(map(str, k[3:])), a["mean_r"], a["tail3_pct"], a["n"], a["n_names"]) for k, a in best_mean],
                "fillable_clearing": ["/".join(map(str, k[3:])) for k, a in cells.items()
                                      if k[0] == "fillable" and k[1] == K and k[2] == sel and a["legs"]["clears"]],
            }
        verdict[K] = {"draws": len(draws), "clearing": len(clearing), "clearing_cells": ["/".join(map(str, k[2:])) for k in clearing],
                      "leg_fail_counts": dict(leg_fail), "per_selection": per_sel,
                      "fillable_clearing_total": sum(1 for k, a in cells.items() if k[0] == "fillable" and k[1] == K and k[4] != "M0_none" and a["legs"]["clears"])}
        print(f"K={K}: {len(clearing)} of {len(draws)} cells clear; legs failed: {dict(leg_fail)}")
        for sel in SELECTIONS:
            print(f"   {sel}: mean>0 {per_sel[sel]['cells_mean_pos']}, tail>=3% {per_sel[sel]['cells_tail_ge_3pct']}, both {per_sel[sel]['cells_mean_pos_and_tail']}, n range {per_sel[sel]['n_range']}")

    # ── outputs ──
    def cell_row(key, a, ctl=None):
        conv, K, sel, s, arm = key
        d = {"convention": conv, "K": K, "selection": sel, "stop": s, "arm": arm}
        for f_ in ("n", "n_unfloored", "n_names", "mean_r", "median_r", "sum_r", "tail3", "tail3_pct", "win_pct", "avg_loss",
                   "loss_pct", "worst_r", "best_r", "stop_pct", "trail_pct", "open_pct", "partial_pct", "be_pct"):
            d[f_] = a[f_]
        d["drop_name"], d["drop_mean_r"] = a["drop_best"]["name"], a["drop_best"]["mean_r"]
        for h in ("H1", "H2"):
            d[f"{h}_n"], d[f"{h}_mean_r"], d[f"{h}_tail3"] = a["halves"][h]["n"], a["halves"][h]["mean_r"], a["halves"][h]["tail3"]
        for e in ("era_c", "era_d"):
            d[f"{e}_n"], d[f"{e}_mean_r"], d[f"{e}_tail3_pct"] = a["per_era"][e]["n"], a["per_era"][e]["mean_r"], a["per_era"][e]["tail3_pct"]
        for p in PATTERNS:
            pp = a.get("per_pattern", {}).get(p, {})
            d[f"{p}_n"], d[f"{p}_mean_r"], d[f"{p}_tail3_pct"] = pp.get("n"), pp.get("mean_r"), pp.get("tail3_pct")
        for leg, ok in a["legs"].items():
            d[f"leg_{leg}"] = ok
        if ctl is not None:
            d["ctl_n"], d["ctl_names"], d["ctl_mean_r"], d["ctl_tail3_pct"], d["ctl_avg_loss"] = ctl["n"], ctl["n_names"], ctl["mean_r"], ctl["tail3_pct"], ctl["avg_loss"]
            d["gap_mean_r"] = round(a["mean_r"] - ctl["mean_r"], 4) if (a["mean_r"] is not None and ctl["mean_r"] is not None) else None
            d["gap_tail3_pp"] = round(a["tail3_pct"] - ctl["tail3_pct"], 2) if (a["tail3_pct"] is not None and ctl["tail3_pct"] is not None) else None
        else:
            for k_ in ("ctl_n", "ctl_names", "ctl_mean_r", "ctl_tail3_pct", "ctl_avg_loss", "gap_mean_r", "gap_tail3_pp"):
                d[k_] = None
        return d
    out_rows = []
    for key, a in cells.items():
        ctl = ctl_cells.get((key[1], key[2], key[3], key[4]))
        out_rows.append(cell_row(key, a, ctl))
    with open(HERE / "p6_cells.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)
    with open(HERE / "p6_events.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)
    summary = {
        "pre_registered": {"draws_per_checkpoint": N_DRAWS_PER_K, "checkpoints": CHECKPOINTS, "stops": STOPS,
                           "arms": MGMT_ARMS, "pass": PASS, "width_floor_pct": WIDTH_FLOOR_PCT, "half_split": {k: v.isoformat() for k, v in HALF_SPLIT.items()}},
        "selection_size": sel_size, "excluded": {f"{k[0]}:{k[1]}": v for k, v in excluded.items()},
        "validation_a": dict(va), "validation_b": dict(vb),
        "status_counts": {"|".join(map(str, k)): v for k, v in status_ct.items()},
        "control": {"sessions": len(ctl_rows), "leaders": sum(1 for r in ctl_rows if r["leader"]), "skipped": dict(ctl_skip),
                    "cells": {"|".join(map(str, k)): {kk: vv for kk, vv in a.items() if kk in ("n", "n_names", "mean_r", "tail3_pct", "avg_loss", "partial_pct", "be_pct", "stop_pct")}
                              for k, a in ctl_cells.items()}},
        "runners": {"stats": dict(runner_stats), "read": {"|".join(k): v for k, v in runner_read.items()},
                    "detail": runner_detail},
        "verdict": verdict,
    }
    with open(HERE / "p6_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print(f"wrote p6_summary.json, p6_cells.tsv ({len(out_rows)} rows), p6_events.csv ({len(events)} rows)")


if __name__ == "__main__":
    main()
