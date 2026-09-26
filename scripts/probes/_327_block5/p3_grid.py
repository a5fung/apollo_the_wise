"""Block 5 / P3 — the stop × target × exit grid, path-ordered, daily grain. $0.

THE QUESTION (fixed by the block): is there any stop × target × exit combination under which
one of the four delayed-entry patterns pays? One walk per (row, stop) captures the path; every
target and exit is then applied over the captured path. Nothing is deployed; nothing here
picks a stop (THE LINE) — the output is grids, measured tails and the clearing COUNT.

THE DRAWS — pre-registered before the first run:
  stops   (7)  incumbent · entry−{0.25,0.5,0.75,1.0,1.5}×ADR$ · prior-session low
               (a stop at/above the entry KILLS the fire at birth — counted, never scored)
  targets (7)  none · 1R · 2R · 3R · 1×ADR$ · 2×ADR$ · 3×ADR$   (R = the cell's OWN risk)
  exits  (12)  the block's six — none · trail SMA10 · trail SMA20 · time s3 · s5 · s10 —
               PLUS the incumbent arm itself — trail MAX(SMA10, SMA20), the production
               `sma_trail_line`, so the lane's recorded exit sits inside the grid as its
               baseline — PLUS FIVE arms drawn from his marked charts (2026-09-23,
               docs/methodology/traderlion_2020_leaders_2026-09-23.md and
               boik_monster_stock_lessons_2026-09-23.md), never invented:
                 sma21_2x   — a close below the 21-day SMA two sessions running (Boik's 21-day
                              area; exit at the second close)
                 ema23_2x   — a close below the 23-EMA two sessions running (TraderLion:
                              "at least a partial sale" — scored here as a FULL exit; no
                              partials are modelled)
                 sma50_1x   — a close below the 50-DMA (TraderLion / Boik: "out")
                 ema65_1x   — a close below the 65-EMA (TraderLion's 50-DMA/65-EMA pair)
                 hv21_50_noreclaim2 — THE FVRR CAUTION: a close below BOTH the 21-day SMA and
                              the 50-DMA on heavy volume (>= 1.5× the mean volume of the prior
                              50 sessions, >= 10 required), having closed at/above at least one
                              of them the session before (it CUT THROUGH); if a close reclaims
                              the 21-day SMA within the next two sessions the break is an
                              add-on, not an exit, and scanning resumes; otherwise the exit is
                              the close of the second session after the break (the moment the
                              non-reclaim is known).
               MA lines include the session's own close (the live `exit_logic` 'sma'
               convention); an EMA is seeded with the SMA of its first N closes; a line needs
               N closes or it does not exist and cannot exit (the live None-guard). The
               fire day (day 0) counts as the first close of the hold, as in
               `compute_settlement`'s trail check.
  TOTAL   7 × 7 × 12 = 588 draws per entry convention (the block sized its noise judgement
          at 294; "1–3 clearing is noise" scales to ~≤6 of 588, and an ELIGIBLE-DRAWS count
          is reported beside it: a 1R or 2R target can never reach 3R, so those cells are
          dead on arrival for the tail leg and are not "draws" in the noise sense).
  Two entry conventions, both run in full: RECORDED (the lane's entry_price — the bar) and
  FILLABLE (entry = max(level, fire-day open) for level-priced fires — P2's finding that a
  resting stop-buy fills at the open when the session opens above the level). The bar is
  fixed on the recorded entry; the fillable grid is reported beside it, never in its place.

SCORING, exactly as compute_settlement orders things:
  * checkpoint K=10 is PRIMARY (P0); K=20 secondary. POPULATION = SESSIONS ELAPSED (>=K
    sessions after the fire exist by 2026-09-25) — never settlement status.
  * within a session: stop (low) → target (high) → close-rule / time exit (close). A bar
    holding both stop and target resolves PESS (stop) for the bar; OPT (target-first) is
    carried beside it for the straddle count P4 needs. Stop = −1.0R exit at the stop level
    (house convention; a gap-charged mean is reported as information), target = exit at the
    target level, close exit = (close − entry)/risk, open at K = mark at K's close.
  * day 0 mirrors P2/compute_settlement: daily-grade fire → the whole fire-day bar folded
    (a LEVEL entry may credit its own day-0 high); minute-grade → post-fire 5-min bars from
    a $0 source (real mi_intraday_bars via `to_rth_5min`, else the row's cached
    `day0_post_low/high` via `day0_pseudo_bars`), else ABSTAIN when the day low reached THAT
    stop, else no day-0 event (the ambiguous day-0 high is never credited).
  * the first missing daily bar ABSTAINS every checkpoint at or beyond it.
  * price scale: every fire-time input × f = dc_close(fire_date)/trigger.day_close (P2's
    adjusted-history fix); ADR$ = the real `compute_ep_adr_dollar` on that scale.

PASS BAR (block, verbatim, applied on the population AFTER the width floor >=0.5% re-applied
in the cell's OWN stop units, all at K=10): mean R > 0 · >=3R rate >= 3.0% · positive on
BOTH time halves (split at fire_date 2026-09-08 — the midpoint of the 08-25→09-21 window the
block references; the second half is four fire dates 09-08..09-11 and its n is reported) ·
positive (mean R > 0) on >=3 of the 4 patterns · survives dropping the single best NAME by
summed R (mean R > 0 AND >=3R >= 3.0% after the drop) · n >= 300. Reported first: the number
of cells clearing every leg against 588 (and against the eligible count). KILL: zero clear,
or every clearing cell clears only WITHOUT the floor.

CROSS-CHECKS before any cell is read (recorded convention):
  (a) the incumbent cell reproduces the recorded realized_r (M-none) and realized_r_trail
      (M-trail) on settled rows a $0 day-0 source can walk;
  (b) every (stop, target, exit∈{none, time s5, trail_max}) cell at K=10 equals what the REAL
      compute_settlement(target_r=…) returns (r_none_s10 / r_none_s5 / r_trail_s10) on the
      same scaled inputs — the only production change the block allows, used as the oracle.

Outputs: p3_summary.json (committed), p3_cells.tsv (every cell, both conventions — committed),
p3_events.csv (per row × stop × target decisions with the straddle session DATE, for P4 —
gitignored with the other bulk files).
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from agents.market_intelligence.delayed_entry_shadow import (  # real code, never re-implemented
    compute_ep_adr_dollar, compute_settlement, day0_needs_minutes, day0_pseudo_bars,
    sma_trail_line, to_rth_5min, _trading_days,
)
from p1_probe import load_triggers, load_intraday_raw  # P1's loaders, reused

LAST_SESSION = date(2026, 9, 25)
WINDOW = 20
PRIMARY_K = 10
CHECKPOINTS = (10, 20)
HALF_SPLIT = date(2026, 9, 8)          # first half < 09-08, second half >= 09-08 (see docstring)
WIDTH_FLOOR_PCT = 0.5
PASS_TAIL_PCT, PASS_N, PASS_PATTERNS = 3.0, 300, 3
TAIL_R = 3.0
_EPS = 1e-9          # 3 x ADR$ / (entry - (entry - ADR$)) is 2.999999… in floating point
HV_VOL_MULT, HV_VOL_LOOKBACK, HV_VOL_MIN_N, HV_RECLAIM_SESSIONS = 1.5, 50, 10, 2

PATTERNS = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")
STOPS = ("incumbent", "adr_025", "adr_050", "adr_075", "adr_100", "adr_150", "prior_low")
ADR_MULT = {"adr_025": 0.25, "adr_050": 0.5, "adr_075": 0.75, "adr_100": 1.0, "adr_150": 1.5}
TARGETS = ("none", "1R", "2R", "3R", "1ADR", "2ADR", "3ADR")
EXITS = ("none", "trail_sma10", "trail_sma20", "trail_max10_20", "time_s3", "time_s5", "time_s10",
         "sma21_2x", "ema23_2x", "sma50_1x", "ema65_1x", "hv21_50_noreclaim2")
CONVENTIONS = ("recorded", "fillable")
N_DRAWS = len(STOPS) * len(TARGETS) * len(EXITS)

STOP, TARGET, EXIT, OPEN, ABSTAIN, KILLED = "stop", "target", "exit", "open", "abstain", "killed"


def _f(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_daily_full():
    """{ticker: {date: {open, high, low, close, vol}}} — the P0 window PLUS the P3 warm-up
    pull (extract_p3.sh), so the 50-DMA / 65-EMA exist at an August fire."""
    out = defaultdict(dict)
    for fn in ("daily_closes_warmup.csv", "daily_closes.csv"):
        with open(HERE / fn, newline="") as fh:
            for r in csv.DictReader(fh):
                d = date.fromisoformat(r["trade_date"])
                out[r["ticker"]][d] = {
                    "trade_date": d, "open": _f(r["open_price"]), "high_price": _f(r["high_price"]),
                    "low_price": _f(r["low_price"]), "close": _f(r["close"]),
                    "vol": _f(r["volume"]),
                }
    return out


# ── moving averages over the full close history ───────────────────────────────────────

def sma_series(vals, n):
    a = np.asarray(vals, dtype=float)
    out = np.full(len(a), np.nan)
    if len(a) >= n:
        cs = np.cumsum(np.insert(a, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def ema_series(vals, n):
    a = np.asarray(vals, dtype=float)
    out = np.full(len(a), np.nan)
    if len(a) < n:
        return out
    k = 2.0 / (n + 1)
    e = a[:n].mean()
    out[n - 1] = e
    for i in range(n, len(a)):
        e = e + k * (a[i] - e)
        out[i] = e
    return out


def vol_avg_prior(vols, lookback, min_n):
    """mean volume of the prior `lookback` sessions (excluding i), NaN with < min_n."""
    a = np.asarray(vols, dtype=float)
    out = np.full(len(a), np.nan)
    cs = np.cumsum(np.insert(a, 0, 0.0))
    for i in range(len(a)):
        j = max(0, i - lookback)
        n = i - j
        if n >= min_n:
            out[i] = (cs[i] - cs[j]) / n
    return out


# ── per-row path assembly ─────────────────────────────────────────────────────────────

_TD_CACHE = {}


def sessions_after(d):
    if d not in _TD_CACHE:
        _TD_CACHE[d] = _trading_days(d + timedelta(days=1), LAST_SESSION)[:WINDOW]
    return _TD_CACHE[d]


def day0_source(t, f, dft, intraday_raw):
    """(kind, bars) on the walk scale. kind: daily_fold | real_intraday_bars |
    cached_pseudo_bars | no_source. bars: [(h, l)] (None for no_source)."""
    fb = dft.get(t["fire_date"])
    if t["fire_minute_et"] is None:
        if not fb or fb["high_price"] is None or fb["low_price"] is None:
            return "missing_fire_day_bar", None
        return "daily_fold", [(fb["high_price"], fb["low_price"])]
    raw = intraday_raw.get((t["ticker"], t["fire_date"]))
    if raw:
        bars5 = to_rth_5min(raw, t["fire_date"])
        post5 = [b for b in bars5 if b["m"] > t["fire_minute_et"]]
        if post5 or bars5:
            return "real_intraday_bars", [(b["h"] * f, b["l"] * f) for b in post5]
    if t["day0_resolved"] is not None:
        pb = day0_pseudo_bars(t["day0_resolved"], t["day0_post_low"], t["day0_post_high"])
        if pb is not None:
            return "cached_pseudo_bars", [(b["h"] * f, b["l"] * f) for b in pb]
    return "no_source", None


def first_idx(mask):
    nz = np.flatnonzero(mask)
    return int(nz[0]) if len(nz) else None


def build_row(t, conv, daily, opens_unused, intraday_raw, adr_by_campaign):
    dft = daily.get(t["ticker"], {})
    adr, adr_n = adr_by_campaign[(t["ticker"], t["ep_date"])]
    if adr is None or not t["entry_price"] or t["entry_price"] <= 0:
        return None, "no_adr_or_entry"
    fb = dft.get(t["fire_date"])
    if not fb or not fb["close"] or not t["day_close"]:
        return None, "missing_fire_day_bar"
    f = fb["close"] / t["day_close"]
    entry = t["entry_price"] * f
    level_priced = t["fire_minute_et"] is None
    gap_over_adr = 0.0
    if conv == "fillable" and level_priced and fb["open"] and fb["open"] > entry:
        gap_over_adr = (fb["open"] - entry) / adr
        entry = fb["open"]
    sessions = sessions_after(t["fire_date"])
    elapsed = len(sessions)
    # session bars up to the first hole
    sh, sl, sc, so, sv = [], [], [], [], []
    hole = None
    for j, d in enumerate(sessions, start=1):
        b = dft.get(d)
        if not b or b["high_price"] is None or b["low_price"] is None or b["close"] is None:
            hole = j
            break
        sh.append(b["high_price"]); sl.append(b["low_price"]); sc.append(b["close"])
        so.append(b["open"]); sv.append(b["vol"] if b["vol"] is not None else 0.0)
    n_avail = len(sc)
    # close/volume history: pre-fire (ascending) + day 0 + sessions
    pre = [dft[d] for d in sorted(dft) if d < t["fire_date"] and dft[d]["close"] is not None]
    closes_pre = [b["close"] for b in pre]
    vols_pre = [b["vol"] if b["vol"] is not None else 0.0 for b in pre]
    allc = closes_pre + [fb["close"]] + sc
    allv = vols_pre + [fb["vol"] if fb["vol"] is not None else 0.0] + sv
    P = len(closes_pre)                       # index of day 0 in allc
    # day-0 bars (shared across stops); abstain decided per stop
    d0_kind, d0_bars = day0_source(t, f, dft, intraday_raw)
    if d0_kind == "missing_fire_day_bar":
        return None, "missing_fire_day_bar"
    day_low = (t["day_low"] * f) if t["day_low"] is not None else None
    row = {
        "id": t["id"], "ticker": t["ticker"], "ep_date": t["ep_date"], "rung": t["rung"],
        "shape": t["reentry_shape"], "fire_date": t["fire_date"], "resolution": t["resolution"],
        "elapsed": elapsed, "hole": hole, "n_avail": n_avail, "f": f, "entry": entry, "adr": adr,
        "level_priced": level_priced, "gap_over_adr": gap_over_adr, "d0_kind": d0_kind,
        "sessions": sessions, "c": [fb["close"]] + sc, "o": [None] + so,
        "allc": allc, "allv": allv, "P": P,
        "stops": {}, "half": "H1" if t["fire_date"] < HALF_SPLIT else "H2",
    }
    # stop levels
    for s in STOPS:
        if s == "incumbent":
            lvl = t["stop_price"] * f if t["stop_price"] else None
        elif s == "prior_low":
            psl = _f(t["prior_session_low"])
            lvl = psl * f if psl else None
        else:
            lvl = entry - ADR_MULT[s] * adr
        if lvl is None or lvl >= entry:
            row["stops"][s] = {"level": lvl, "killed": True}
            continue
        risk = entry - lvl
        width = (entry - lvl) / entry * 100.0
        if d0_kind == "no_source":
            d0_abstain = day_low is not None and day_low <= lvl
            d0 = [] if not d0_abstain else None
        else:
            d0_abstain, d0 = False, d0_bars
        row["stops"][s] = {"level": lvl, "killed": False, "risk": risk, "width_pct": width,
                           "d0_abstain": d0_abstain, "d0_bars": d0}
    return row, None


def first_passages(row):
    """Per stop × target: the deciding (session, kind) under pess and opt + the straddle
    bar's session; the bar arrays are day-0 bars + session bars up to the hole."""
    out = {}
    for s, st in row["stops"].items():
        if st["killed"] or st["d0_abstain"]:
            continue
        d0 = st["d0_bars"]
        H = np.asarray([h for h, _ in d0] + list(_row_sh(row)), dtype=float)
        L = np.asarray([l for _, l in d0] + list(_row_sl(row)), dtype=float)
        sessnum = np.asarray([0] * len(d0) + list(range(1, row["n_avail"] + 1)), dtype=int)
        stop_i = first_idx(L <= st["level"]) if len(L) else None
        entry, risk, adr = row["entry"], st["risk"], row["adr"]
        for tg in TARGETS:
            if tg == "none":
                lvl, tR = None, None
            elif tg.endswith("ADR"):
                m = float(tg[:-3]); lvl, tR = entry + m * adr, m * adr / risk
            else:
                m = float(tg[:-1]); lvl, tR = entry + m * risk, m
            tgt_i = first_idx(H >= lvl) if (lvl is not None and len(H)) else None
            # pess: stop first on the deciding bar; opt: target first
            if stop_i is None and tgt_i is None:
                pess = opt = (None, None)
                straddle = False
            else:
                if stop_i is not None and (tgt_i is None or stop_i <= tgt_i):
                    pess = (int(sessnum[stop_i]), STOP)
                else:
                    pess = (int(sessnum[tgt_i]), TARGET)
                if tgt_i is not None and (stop_i is None or tgt_i <= stop_i):
                    opt = (int(sessnum[tgt_i]), TARGET)
                else:
                    opt = (int(sessnum[stop_i]), STOP)
                straddle = stop_i is not None and tgt_i is not None and stop_i == tgt_i
            out[(s, tg)] = {"pess": pess, "opt": opt, "straddle": straddle, "target_r": tR,
                            "tail_eligible": (tR is None) or (tR >= TAIL_R - _EPS)}
    return out


def _row_sh(row):
    return row["_sh"]


def _row_sl(row):
    return row["_sl"]


def exit_sessions(row):
    """Per exit arm: the session (0 = day 0) at whose close the arm exits, or None. Computed
    once per row over the closes actually available (never past the hole)."""
    allc, allv, P = row["allc"], row["allv"], row["P"]
    n_avail = row["n_avail"]
    walk = range(0, n_avail + 1)                       # s = 0..n_avail ↔ allc[P + s]
    sma10, sma20 = sma_series(allc, 10), sma_series(allc, 20)
    sma21, sma50 = sma_series(allc, 21), sma_series(allc, 50)
    ema23, ema65 = ema_series(allc, 23), ema_series(allc, 65)
    vavg = vol_avg_prior(allv, HV_VOL_LOOKBACK, HV_VOL_MIN_N)
    ex = {"none": None}
    for k in (3, 5, 10):
        ex[f"time_s{k}"] = k if k <= n_avail else None

    def first_close_below(line):
        for s in walk:
            i = P + s
            if not np.isnan(line[i]) and allc[i] < line[i]:
                return s
        return None

    ex["trail_sma10"] = first_close_below(sma10)
    ex["trail_sma20"] = first_close_below(sma20)
    ex["sma50_1x"] = first_close_below(sma50)
    ex["ema65_1x"] = first_close_below(ema65)
    # the production trail: MAX(SMA10, SMA20) with the <20 → SMA10, <10 → None fallbacks
    tm = None
    for s in walk:
        line = sma_trail_line(allc[:P + s + 1])
        if line is not None and allc[P + s] < line:
            tm = s
            break
    ex["trail_max10_20"] = tm

    def two_running_below(line):
        for s in walk:
            if s == 0:
                continue
            i, h = P + s, P + s - 1
            if (not np.isnan(line[i]) and not np.isnan(line[h])
                    and allc[i] < line[i] and allc[h] < line[h]):
                return s
        return None

    ex["sma21_2x"] = two_running_below(sma21)
    ex["ema23_2x"] = two_running_below(ema23)
    # the FVRR caution: heavy-volume cut through BOTH the 21 and the 50, not reclaimed
    hv = None
    s = 0
    while s <= n_avail:
        i, h = P + s, P + s - 1
        ok_lines = not (np.isnan(sma21[i]) or np.isnan(sma50[i]) or np.isnan(vavg[i]))
        if ok_lines and h >= 0 and not np.isnan(sma21[h]) and not np.isnan(sma50[h]):
            below_both = allc[i] < sma21[i] and allc[i] < sma50[i]
            was_above = allc[h] >= sma21[h] or allc[h] >= sma50[h]
            heavy = allv[i] >= HV_VOL_MULT * vavg[i]
            if below_both and was_above and heavy:
                reclaimed_at = None
                for j in range(s + 1, s + 1 + HV_RECLAIM_SESSIONS):
                    if j > n_avail:
                        break
                    if not np.isnan(sma21[P + j]) and allc[P + j] > sma21[P + j]:
                        reclaimed_at = j
                        break
                if reclaimed_at is not None:
                    s = reclaimed_at + 1
                    continue
                if s + HV_RECLAIM_SESSIONS <= n_avail:
                    hv = s + HV_RECLAIM_SESSIONS
                break                                   # unresolved (window ends) → None
        s += 1
    ex["hv21_50_noreclaim2"] = hv
    return ex


def cell_r(row, st, fp, ex_s, K, bound="pess"):
    """(status, R, kind, event_session) for one (row, stop, target, exit) at checkpoint K."""
    if st["killed"]:
        return KILLED, None, None, None
    if st["d0_abstain"]:
        return ABSTAIN, None, None, None
    if row["elapsed"] < K:
        return "not_in_population", None, None, None
    dec_s, dec_kind = fp[bound]
    ev_s, ev_kind = dec_s, dec_kind
    if ex_s is not None and (ev_s is None or ex_s < ev_s):
        ev_s, ev_kind = ex_s, EXIT
    entry, risk = row["entry"], st["risk"]
    if ev_s is not None and ev_s <= K:
        if ev_kind == STOP:
            return "scored", -1.0, STOP, ev_s
        if ev_kind == TARGET:
            return "scored", fp["target_r"], TARGET, ev_s
        return "scored", (row["c"][ev_s] - entry) / risk, EXIT, ev_s
    if row["hole"] is not None and row["hole"] <= K:
        return ABSTAIN, None, None, None
    return "scored", (row["c"][K] - entry) / risk, OPEN, None


def _mean(v):
    return round(float(np.mean(v)), 4) if len(v) else None


def _tail(v):
    return sum(1 for x in v if x >= TAIL_R - _EPS)


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def aggregate(scored):
    """scored: list of (row, R, kind, ev_s, straddle, r_opt, r_gap, tail_eligible, width_ok)."""
    fl = [x for x in scored if x[8]]
    R = [x[1] for x in fl]
    n = len(R)
    out = {"n_scored_unfloored": len(scored), "n": n,
           "mean_r": _mean(R), "sum_r": round(float(np.sum(R)), 2) if n else None,
           "tail3": _tail(R), "tail3_pct": _pct(_tail(R), n),
           "win_pct": _pct(sum(1 for r in R if r > 0), n),
           "unfloored_mean_r": _mean([x[1] for x in scored]),
           "unfloored_tail3_pct": _pct(_tail([x[1] for x in scored]), len(scored)),
           "stop_pct": _pct(sum(1 for x in fl if x[2] == STOP), n),
           "target_pct": _pct(sum(1 for x in fl if x[2] == TARGET), n),
           "exit_fired_pct": _pct(sum(1 for x in fl if x[2] == EXIT), n),
           "open_at_k_pct": _pct(sum(1 for x in fl if x[2] == OPEN), n),
           "straddle_decided": sum(1 for x in fl if x[4]),
           "opt_mean_r": _mean([x[5] for x in fl if x[5] is not None]),
           "gapcharged_mean_r": _mean([x[6] for x in fl]),
           "tail_eligible_pct": _pct(sum(1 for x in fl if x[7]), n),
           "n_names": len({x[0]["ticker"] for x in fl})}
    # per pattern
    pat = {}
    for p in PATTERNS:
        v = [x[1] for x in fl if x[0]["rung"] == p]
        pat[p] = {"n": len(v), "mean_r": _mean(v), "tail3": _tail(v), "tail3_pct": _pct(_tail(v), len(v))}
    out["per_pattern"] = pat
    out["patterns_positive"] = sum(1 for p in PATTERNS if pat[p]["mean_r"] is not None and pat[p]["mean_r"] > 0)
    # halves
    hv = {}
    for h in ("H1", "H2"):
        v = [x[1] for x in fl if x[0]["half"] == h]
        hv[h] = {"n": len(v), "mean_r": _mean(v), "tail3": _tail(v)}
        vh = [x[1] for x in fl if x[0]["half"] == h and x[0]["rung"] == "ep_high_break"]
        hv[h]["ep_high_break_n"], hv[h]["ep_high_break_mean_r"] = len(vh), _mean(vh)
    out["halves"] = hv
    # drop the best NAME by summed R
    by_name = defaultdict(float)
    for x in fl:
        by_name[x[0]["ticker"]] += x[1]
    if by_name:
        best = max(by_name, key=by_name.get)
        v = [x[1] for x in fl if x[0]["ticker"] != best]
        out["drop_best_name"] = {"name": best, "name_sum_r": round(by_name[best], 2), "n": len(v),
                                 "mean_r": _mean(v), "tail3_pct": _pct(_tail(v), len(v))}
    else:
        out["drop_best_name"] = {"name": None, "n": 0, "mean_r": None, "tail3_pct": None}
    return out


def legs(agg):
    d = agg["drop_best_name"]
    h = agg["halves"]
    L = {
        "mean_r_gt_0": agg["mean_r"] is not None and agg["mean_r"] > 0,
        "tail3_ge_3pct": agg["tail3_pct"] is not None and agg["tail3_pct"] >= PASS_TAIL_PCT,
        "both_halves_positive": all(h[k]["mean_r"] is not None and h[k]["mean_r"] > 0 for k in ("H1", "H2")),
        "patterns_ge_3_of_4": agg["patterns_positive"] >= PASS_PATTERNS,
        "drop_best_name": (d["mean_r"] is not None and d["mean_r"] > 0
                           and d["tail3_pct"] is not None and d["tail3_pct"] >= PASS_TAIL_PCT),
        "n_ge_300": agg["n"] >= PASS_N,
    }
    L["clears"] = all(L.values())
    return L


def main():
    triggers = load_triggers()
    daily = load_daily_full()
    intraday_raw = load_intraday_raw()
    for t in triggers:
        t["stop_hit_date"] = date.fromisoformat(t["stop_hit_date"]) if t.get("stop_hit_date") else None
    n_pre_hist = Counter()
    print(f"triggers {len(triggers)} · tickers {len({t['ticker'] for t in triggers})} · draws per "
          f"convention {N_DRAWS} = {len(STOPS)} stops × {len(TARGETS)} targets × {len(EXITS)} exits")
    print("exit arms:", ", ".join(EXITS))

    # ADR$ per campaign on the daily-table scale (P2's method, the real function)
    adr_by_campaign = {}
    for t in triggers:
        key = (t["ticker"], t["ep_date"])
        if key in adr_by_campaign:
            continue
        dft = daily.get(t["ticker"], {})
        bars_asc = [dft[d] for d in sorted(dft)]
        ep_bar = dft.get(t["ep_date"])
        adr_by_campaign[key] = compute_ep_adr_dollar(bars_asc, t["ep_date"],
                                                     ep_bar["close"] if ep_bar else None)

    # ── build rows, walks, exits ──
    rows = {c: [] for c in CONVENTIONS}
    excluded = Counter()
    for conv in CONVENTIONS:
        for t in triggers:
            row, why = build_row(t, conv, daily, None, intraday_raw, adr_by_campaign)
            if row is None:
                excluded[(conv, why)] += 1
                continue
            row["_sh"] = [daily[t["ticker"]][d]["high_price"] for d in row["sessions"][:row["n_avail"]]]
            row["_sl"] = [daily[t["ticker"]][d]["low_price"] for d in row["sessions"][:row["n_avail"]]]
            row["fp"] = first_passages(row)
            row["ex"] = exit_sessions(row)
            n_pre_hist[min(row["P"] // 25 * 25, 200)] += 1
            rows[conv].append(row)
        print(f"[{conv}] rows built {len(rows[conv])}; excluded {dict((k[1], v) for k, v in excluded.items() if k[0] == conv)}")
    print(f"pre-fire close history per row (bucketed by 25 sessions, recorded+fillable): {dict(sorted(n_pre_hist.items()))}")

    # ── cross-check (a): the incumbent cell vs the recorded settlement ──
    def settle_r(row, st, fp, ex_s):
        """Realized R the way production settles: the first of stop/target/exit on the
        available bars, else the session-20 time exit when 20 bars exist, else None."""
        dec_s, dec_kind = fp["pess"]
        ev_s, ev_kind = dec_s, dec_kind
        if ex_s is not None and (ev_s is None or ex_s < ev_s):
            ev_s, ev_kind = ex_s, EXIT
        if ev_s is not None:
            if ev_kind == STOP:
                return -1.0
            if ev_kind == TARGET:
                return fp["target_r"]
            return (row["c"][ev_s] - row["entry"]) / st["risk"]
        if row["n_avail"] >= WINDOW:
            return (row["c"][WINDOW] - row["entry"]) / st["risk"]
        return None

    xa = Counter()
    for row in rows["recorded"]:
        t = next(x for x in triggers if x["id"] == row["id"])
        if t["outcome"] not in ("stop", "time_exit") or t["realized_r"] is None:
            continue
        st = row["stops"]["incumbent"]
        if st["killed"] or st["d0_abstain"]:
            xa["day0_abstain_or_killed"] += 1
            continue
        fp = row["fp"][("incumbent", "none")]
        r_none = settle_r(row, st, fp, None)
        r_tr = settle_r(row, st, fp, row["ex"]["trail_max10_20"])
        if r_none is None:
            xa["not_walkable_window_open_or_hole"] += 1
            continue
        ok_none = abs(r_none - t["realized_r"]) <= 0.002
        ok_tr = (t["realized_r_trail"] is not None and r_tr is not None
                 and abs(r_tr - t["realized_r_trail"]) <= 0.002)
        xa["none_match" if ok_none else "none_mismatch"] += 1
        xa["trail_match" if ok_tr else "trail_mismatch"] += 1
        if (not ok_none or not ok_tr) and xa["printed"] < 10:
            xa["printed"] += 1
            print(f"  anchor mismatch {row['ticker']} {row['fire_date']} {row['rung']} rec none={t['realized_r']} "
                  f"probe={round(r_none, 4)} · rec trail={t['realized_r_trail']} probe={r_tr and round(r_tr, 4)} f={row['f']:.3f}")
    xa.pop("printed", None)
    print(f"CROSS-CHECK (a) incumbent cell vs recorded: {dict(xa)}")

    # ── cross-check (b): every (stop, target) × {none, time_s5, trail_max} at K=10 vs the REAL
    #    compute_settlement(target_r=…) on the same scaled inputs ──
    xb = Counter()
    xb_examples = []
    for row in rows["recorded"]:
        if row["elapsed"] < WINDOW or row["hole"] is not None:
            continue
        t = next(x for x in triggers if x["id"] == row["id"])
        dft = daily[row["ticker"]]
        fb = dft.get(row["fire_date"])
        fire_day_bar = {"h": fb["high_price"], "l": fb["low_price"], "c": fb["close"]}
        sessions = row["sessions"]
        bars_by_day = {d: dft[d] for d in sessions}
        closes_before = row["allc"][:row["P"]]
        for s, st in row["stops"].items():
            if st["killed"]:
                continue
            if st["d0_abstain"]:
                xb["day0_abstain_walker"] += 1
                continue
            post5 = None
            needs = day0_needs_minutes(t["fire_minute_et"], fire_day_bar["l"], st["level"])
            if needs:
                if row["d0_kind"] == "no_source":
                    xb["oracle_would_abstain_no_minutes"] += 1   # trigger low x f vs daily low disagree
                    continue
                post5 = [{"h": h, "l": l} for h, l in st["d0_bars"]]
            elif row["d0_kind"] in ("real_intraday_bars", "cached_pseudo_bars") and st["d0_bars"]:
                # the walker walks real post-fire bars whenever they exist (a target hit there is
                # genuine); production only consults minutes when the day low reached the stop —
                # not comparable on day 0, counted, excluded from the oracle read
                xb["walker_has_day0_bars_oracle_would_not_consult"] += 1
                continue
            for tg in TARGETS:
                fp = row["fp"][(s, tg)]
                res = compute_settlement(
                    entry=row["entry"], stop=st["level"], fire_minute=t["fire_minute_et"],
                    fire_day_bar=fire_day_bar, post_fire_bars5=post5, sessions=sessions,
                    bars_by_day=bars_by_day, closes_before_fire=closes_before,
                    target_r=fp["target_r"])
                if res["status"] != "settled":
                    xb[f"oracle_{res['status']}:{res.get('reason', '')[:15]}"] += 1
                    continue
                checks = (("none", "r_none_s10", None), ("time_s5", "r_none_s5", 5),
                          ("trail_max10_20", "r_trail_s10", row["ex"]["trail_max10_20"]))
                for ex_name, col, ex_s in checks:
                    _, r_mine, _, _ = cell_r(row, st, fp, ex_s, PRIMARY_K)
                    ok = r_mine is not None and res[col] is not None and abs(r_mine - res[col]) <= 0.002
                    xb["match" if ok else f"mismatch_{ex_name}"] += 1
                    if not ok and len(xb_examples) < 8:
                        xb_examples.append(f"{row['ticker']} {row['fire_date']} {s}/{tg}/{ex_name}: mine={r_mine} oracle={res[col]} outcome={res['outcome']}")
    print(f"CROSS-CHECK (b) grid vs compute_settlement(target_r): {dict(xb)}")
    for e in xb_examples:
        print("   ", e)

    # ── the grid ──
    grid = {c: {} for c in CONVENTIONS}
    events_out = []
    for conv in CONVENTIONS:
        for s in STOPS:
            for tg in TARGETS:
                for ex in EXITS:
                    scored, status = [], Counter()
                    for row in rows[conv]:
                        st = row["stops"][s]
                        if st["killed"]:
                            status[KILLED] += 1
                            continue
                        fp = row["fp"].get((s, tg))
                        ex_s = row["ex"][ex]
                        if fp is None:                 # day-0 abstain for this stop
                            status[ABSTAIN] += 1 if row["elapsed"] >= PRIMARY_K else 0
                            continue
                        stt, R, kind, ev_s = cell_r(row, st, fp, ex_s, PRIMARY_K)
                        status[stt] += 1
                        if stt != "scored":
                            continue
                        _, r_opt, _, _ = cell_r(row, st, fp, ex_s, PRIMARY_K, bound="opt")
                        r_gap = R
                        if kind == STOP and ev_s is not None and ev_s >= 1:
                            o = row["o"][ev_s]
                            if o is not None and o < st["level"]:
                                r_gap = (o - row["entry"]) / st["risk"]
                        straddle = (kind in (STOP, TARGET) and fp["straddle"]
                                    and fp["pess"][1] != fp["opt"][1])
                        scored.append((row, R, kind, ev_s, straddle, r_opt, r_gap, fp["tail_eligible"],
                                       st["width_pct"] >= WIDTH_FLOOR_PCT))
                    agg = aggregate(scored)
                    agg["status"] = dict(status)
                    agg["legs"] = legs(agg)
                    grid[conv][(s, tg, ex)] = agg
        # per-row events for P4 (one line per stop × target; exits are per row)
        for row in rows[conv]:
            for (s, tg), fp in row["fp"].items():
                sd = fp["pess"][0]
                events_out.append({
                    "convention": conv, "id": row["id"], "ticker": row["ticker"], "rung": row["rung"],
                    "fire_date": row["fire_date"].isoformat(), "elapsed": row["elapsed"], "stop": s,
                    "target": tg, "stop_level": round(row["stops"][s]["level"], 6),
                    "width_pct": round(row["stops"][s]["width_pct"], 4),
                    "pess_session": sd, "pess_kind": fp["pess"][1],
                    "opt_session": fp["opt"][0], "opt_kind": fp["opt"][1],
                    "straddle": fp["straddle"],
                    "straddle_date": (row["fire_date"] if sd == 0 else row["sessions"][sd - 1]).isoformat()
                    if (fp["straddle"] and sd is not None) else "",
                    **{f"exit_{e}": row["ex"][e] for e in EXITS if e != "none"},
                })

    # ── verdict per convention ──
    summary_conv = {}
    for conv in CONVENTIONS:
        g = grid[conv]
        clearing = [k for k, a in g.items() if a["legs"]["clears"]]
        eligible = [k for k, a in g.items() if (a["tail_eligible_pct"] or 0) >= PASS_TAIL_PCT]
        leg_fail = Counter()
        for a in g.values():
            for leg, ok in a["legs"].items():
                if leg != "clears" and not ok:
                    leg_fail[leg] += 1
        # cells that clear every leg WITHOUT the floor but not with it (the artifact class)
        floor_only_loss = 0
        best_mean = max((a["mean_r"] for a in g.values() if a["mean_r"] is not None), default=None)
        n_mean_pos = sum(1 for a in g.values() if a["mean_r"] is not None and a["mean_r"] > 0)
        n_tail_ok = sum(1 for a in g.values() if a["tail3_pct"] is not None and a["tail3_pct"] >= PASS_TAIL_PCT)
        n_both = sum(1 for a in g.values() if a["legs"]["mean_r_gt_0"] and a["legs"]["tail3_ge_3pct"])
        for a in g.values():
            um, ut = a["unfloored_mean_r"], a["unfloored_tail3_pct"]
            if um is not None and um > 0 and ut is not None and ut >= PASS_TAIL_PCT and not (
                    a["legs"]["mean_r_gt_0"] and a["legs"]["tail3_ge_3pct"]):
                floor_only_loss += 1
        # tail-first per pattern: how many cells give the pattern >=3R >= 3% with mean > 0
        per_pattern = {}
        for p in PATTERNS:
            cells_ok = [k for k, a in g.items() if a["per_pattern"][p]["mean_r"] is not None
                        and a["per_pattern"][p]["mean_r"] > 0
                        and a["per_pattern"][p]["tail3_pct"] is not None
                        and a["per_pattern"][p]["tail3_pct"] >= PASS_TAIL_PCT
                        and a["per_pattern"][p]["n"] >= 50]
            tails = [a["per_pattern"][p]["tail3_pct"] for a in g.values() if a["per_pattern"][p]["tail3_pct"] is not None]
            means = [a["per_pattern"][p]["mean_r"] for a in g.values() if a["per_pattern"][p]["mean_r"] is not None]
            per_pattern[p] = {
                "cells_mean_pos_and_tail_ge_3pct_n_ge_50": len(cells_ok),
                "cells_mean_pos": sum(1 for m in means if m > 0),
                "max_tail3_pct": max(tails) if tails else None,
                "max_mean_r": max(means) if means else None,
                "n_at_s10_in_none_none_none_cell": g[("incumbent", "none", "none")]["per_pattern"][p]["n"],
                "incumbent_cell_mean_r": g[("incumbent", "none", "trail_max10_20")]["per_pattern"][p]["mean_r"],
                "incumbent_cell_tail3_pct": g[("incumbent", "none", "trail_max10_20")]["per_pattern"][p]["tail3_pct"],
                "example_cells_mean_pos_and_tail": ["/".join(k) for k in cells_ok[:12]],
            }
        summary_conv[conv] = {
            "draws": N_DRAWS, "cells_tested": len(g),
            "cells_clearing_all_legs": len(clearing),
            "clearing_cells": [{"stop": k[0], "target": k[1], "exit": k[2], **{kk: g[k][kk] for kk in
                                ("n", "mean_r", "tail3_pct", "n_names", "per_pattern", "halves", "drop_best_name",
                                 "exit_fired_pct", "straddle_decided", "opt_mean_r", "gapcharged_mean_r",
                                 "unfloored_mean_r", "unfloored_tail3_pct")}} for k in clearing],
            "tail_eligible_draws": len(eligible),
            "noise_band_scaled": {"block_said": "1-3 of 294 = noise; >=25 = family",
                                  "scaled_to_draws": f"<= {round(3 * N_DRAWS / 294)} of {N_DRAWS} = noise; >= {round(25 * N_DRAWS / 294)} = family",
                                  "scaled_to_eligible": f"<= {round(3 * len(eligible) / 294)} of {len(eligible)} = noise; >= {round(25 * len(eligible) / 294)} = family"},
            "leg_failure_counts": dict(leg_fail),
            "cells_mean_r_positive": n_mean_pos, "cells_tail3_ge_3pct": n_tail_ok,
            "cells_mean_pos_and_tail_ok": n_both,
            "cells_clearing_mean_and_tail_only_without_floor": floor_only_loss,
            "best_cell_mean_r": best_mean,
            "per_pattern_tail_first": per_pattern,
            "incumbent_baseline_cell": {kk: g[("incumbent", "none", "trail_max10_20")][kk] for kk in
                                        ("n", "mean_r", "tail3_pct", "per_pattern", "halves", "status")},
        }
        print(f"\n=== [{conv}] {len(clearing)} of {N_DRAWS} cells clear every leg at s10 "
              f"(tail-eligible draws {len(eligible)}) · mean>0 in {n_mean_pos} · tail>=3% in {n_tail_ok} · "
              f"both {n_both} · clear-only-without-floor {floor_only_loss} · best mean {best_mean}")
        print(f"    leg failures: {dict(leg_fail)}")
        for k in clearing:
            a = g[k]
            print(f"    CLEARS {'/'.join(k)}: n={a['n']} mean={a['mean_r']} tail3={a['tail3_pct']}% names={a['n_names']} "
                  f"halves H1 {a['halves']['H1']['mean_r']} (n={a['halves']['H1']['n']}) H2 {a['halves']['H2']['mean_r']} "
                  f"(n={a['halves']['H2']['n']}) drop {a['drop_best_name']['name']} → {a['drop_best_name']['mean_r']} · "
                  + " · ".join(f"{p[:8]} {a['per_pattern'][p]['mean_r']}/{a['per_pattern'][p]['tail3_pct']}% n={a['per_pattern'][p]['n']}" for p in PATTERNS))
        for p in PATTERNS:
            pp = per_pattern[p]
            print(f"    tail-first {p}: cells with mean>0 & tail>=3% (n>=50): {pp['cells_mean_pos_and_tail_ge_3pct_n_ge_50']} · "
                  f"max tail {pp['max_tail3_pct']}% · max mean {pp['max_mean_r']} · incumbent cell mean {pp['incumbent_cell_mean_r']} tail {pp['incumbent_cell_tail3_pct']}%")

    both = {}
    for k in grid["recorded"]:
        both[k] = grid["recorded"][k]["legs"]["clears"] and grid["fillable"][k]["legs"]["clears"]
    # KILL = zero cells clear; "loses it at the width floor" is subsumed — every leg is
    # already evaluated on the floored population, so a clearing cell has survived the floor.
    verdict = "pass" if summary_conv["recorded"]["cells_clearing_all_legs"] >= 1 else "kill"
    summary = {
        "generated": datetime.now().isoformat(),
        "last_session_in_extract": LAST_SESSION.isoformat(),
        "warmup_pulled_at": (HERE / "daily_closes_warmup.pulled_at").read_text().strip() if (HERE / "daily_closes_warmup.pulled_at").exists() else None,
        "draws": {"stops": STOPS, "targets": TARGETS, "exits": EXITS, "total_per_convention": N_DRAWS,
                  "added_exit_arms_beyond_the_block": ["trail_max10_20 (the incumbent arm)", "sma21_2x", "ema23_2x",
                                                       "sma50_1x", "ema65_1x", "hv21_50_noreclaim2"]},
        "conventions": {
            "primary_checkpoint": PRIMARY_K, "population": "sessions elapsed >= K, never settlement status",
            "half_split": HALF_SPLIT.isoformat(), "width_floor_pct": WIDTH_FLOOR_PCT,
            "pass_bar": "mean R>0 · >=3R rate>=3% · both halves mean>0 · >=3 of 4 patterns mean>0 · "
                        "drop best NAME by summed R keeps mean>0 and >=3R>=3% · n>=300; all on the floored population at s10",
            "hv_arm": f"vol >= {HV_VOL_MULT}x mean of prior {HV_VOL_LOOKBACK} sessions (>= {HV_VOL_MIN_N}); reclaim = close > SMA21 within {HV_RECLAIM_SESSIONS} sessions; exit at close of break+{HV_RECLAIM_SESSIONS}",
            "redundancy": "exit=none and exit=time_s10 are the same reading at the s10 checkpoint (both are the s10 close); counted as the block's distinct draws",
        },
        "rows": {c: {"built": len(rows[c]), "excluded": {k[1]: v for k, v in excluded.items() if k[0] == c},
                     "s10_population": sum(1 for r in rows[c] if r["elapsed"] >= PRIMARY_K),
                     "killed_at_birth": {s: sum(1 for r in rows[c] if r["stops"][s]["killed"] and r["elapsed"] >= PRIMARY_K) for s in STOPS},
                     "day0_abstain": {s: sum(1 for r in rows[c] if not r["stops"][s]["killed"] and r["stops"][s]["d0_abstain"] and r["elapsed"] >= PRIMARY_K) for s in STOPS},
                     "day0_kind": dict(Counter(r["d0_kind"] for r in rows[c]))}
                 for c in CONVENTIONS},
        "cross_checks": {"a_incumbent_vs_recorded": dict(xa), "b_grid_vs_compute_settlement_target_r": dict(xb),
                         "b_examples": xb_examples},
        "verdict": {"verdict": verdict,
                    "recorded_clearing": summary_conv["recorded"]["cells_clearing_all_legs"],
                    "fillable_clearing": summary_conv["fillable"]["cells_clearing_all_legs"],
                    "cells_clearing_under_both_conventions": sum(1 for v in both.values() if v)},
        "by_convention": summary_conv,
    }
    with open(HERE / "p3_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    # every cell, both conventions
    with open(HERE / "p3_cells.tsv", "w", newline="") as fh:
        cols = ["convention", "stop", "target", "exit", "n", "n_scored_unfloored", "n_names", "mean_r", "sum_r",
                "tail3", "tail3_pct", "win_pct", "unfloored_mean_r", "unfloored_tail3_pct", "stop_pct", "target_pct",
                "exit_fired_pct", "open_at_k_pct", "straddle_decided", "opt_mean_r", "gapcharged_mean_r",
                "tail_eligible_pct", "patterns_positive", "H1_n", "H1_mean_r", "H2_n", "H2_mean_r",
                "H2_ep_high_break_n", "H2_ep_high_break_mean_r", "drop_name", "drop_mean_r", "drop_tail3_pct"]
        cols += [f"{p}_{m}" for p in PATTERNS for m in ("n", "mean_r", "tail3_pct")]
        cols += ["leg_mean", "leg_tail", "leg_halves", "leg_patterns", "leg_drop", "leg_n", "clears", "n_killed", "n_abstain"]
        w = csv.writer(fh, delimiter="\t")
        w.writerow(cols)
        for conv in CONVENTIONS:
            for k, a in grid[conv].items():
                L, h, d = a["legs"], a["halves"], a["drop_best_name"]
                w.writerow([conv, *k, a["n"], a["n_scored_unfloored"], a["n_names"], a["mean_r"], a["sum_r"], a["tail3"],
                            a["tail3_pct"], a["win_pct"], a["unfloored_mean_r"], a["unfloored_tail3_pct"], a["stop_pct"],
                            a["target_pct"], a["exit_fired_pct"], a["open_at_k_pct"], a["straddle_decided"], a["opt_mean_r"],
                            a["gapcharged_mean_r"], a["tail_eligible_pct"], a["patterns_positive"], h["H1"]["n"], h["H1"]["mean_r"],
                            h["H2"]["n"], h["H2"]["mean_r"], h["H2"]["ep_high_break_n"], h["H2"]["ep_high_break_mean_r"],
                            d["name"], d["mean_r"], d["tail3_pct"],
                            *[a["per_pattern"][p][m] for p in PATTERNS for m in ("n", "mean_r", "tail3_pct")],
                            L["mean_r_gt_0"], L["tail3_ge_3pct"], L["both_halves_positive"], L["patterns_ge_3_of_4"],
                            L["drop_best_name"], L["n_ge_300"], L["clears"], a["status"].get(KILLED, 0), a["status"].get(ABSTAIN, 0)])
    with open(HERE / "p3_events.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events_out[0].keys()))
        w.writeheader()
        w.writerows(events_out)
    print(f"\nVERDICT: {verdict} · recorded clearing {summary['verdict']['recorded_clearing']} / {N_DRAWS} · "
          f"fillable clearing {summary['verdict']['fillable_clearing']} / {N_DRAWS}")
    print(f"wrote p3_summary.json, p3_cells.tsv ({len(grid['recorded']) * 2} rows), p3_events.csv ({len(events_out)} rows)")


if __name__ == "__main__":
    main()
