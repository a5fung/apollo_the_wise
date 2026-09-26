"""Block 5 / P2 — is there an ENTRY at all? ADR-normalised, against a matched control. $0.

The question this file answers, exactly as the block fixes it: for every fire, walk the
forward daily path from `entry_price` and measure whether it reaches +2×ADR$ BEFORE
−1×ADR$ at s5/s10/s20, against a CONTROL of every non-fire session inside the same
(ticker, 20-session watch window) entered at that session's close. Sessions where both
levels sit inside one daily range are counted under BOTH bounds (pess = stop-first,
opt = target-first). The unit is ADR DOLLARS — a unit the stop cannot contaminate.

Pass bar (fixed in advance, applied literally, never re-picked): a pattern has entry
edge only if its +2ADR-before-−1ADR rate at s10 exceeds the matched control's by
>=5pp under the PESSIMISTIC bound, holds after dropping the single best-contributing
NAME (from BOTH sides), on n>=150 fires spanning >=60 distinct names.
Kill rule: all four patterns within ±2pp of control on both bounds at s10.

Conventions, every one stated here because every one moves a number:
  * POPULATION = SESSIONS ELAPSED. A fire is in the checkpoint-K population iff >=K
    trading sessions after its fire_date exist in the extract (last bar 2026-09-25).
    Settlement status is never consulted. The same clock applies to every control
    session. Re-entry shapes are pooled into their rung, as the 2026-09-22 read did.
  * PRICE SCALE. `mi_daily_closes` is a continuously ADJUSTED history (P1 found 16
    post-fire reverse splits; this run finds 158 fires on 26 tickers whose fire-day
    close differs from the trigger row's contemporaneous day_close, all clean-integer
    reverse splits bar two ~2.5-5% dividend adjustments). Every fire-time-scale input
    (entry_price, the incumbent stop for the anchor check, the day-0 cache, the raw
    1-min bars) is multiplied by f = dc_close(fire_date) / trigger.day_close, which
    puts the whole walk on ONE scale. ADR$ is recomputed on that scale with the REAL
    `compute_ep_adr_dollar` and the EP-day close from the same table.
  * DAY 0 mirrors `compute_settlement`: a daily-grade fire folds the whole fire-day
    bar (pess stop-first; opt target-first); a minute-grade fire walks the post-fire
    5-min bars when a $0 source exists (real `mi_intraday_bars` via the production
    `to_rth_5min`, else the row's own `day0_post_low/high` cache via the production
    `day0_pseudo_bars`), else ABSTAINS when its day low reached the stop, else
    carries no day-0 event — the ambiguous day-0 daily high is never credited.
  * HOLES: the first missing daily bar ABSTAINS every checkpoint at or beyond it
    (never leap a gap). Abstains are counted, never dropped silently.
  * ANCHOR (P2's own P1): the same walker, given the incumbent stop and no target,
    must reproduce production's recorded `stop_hit_date` / time-exit on every settled
    row it can walk. The match rate is printed and stored; a walker that cannot
    reproduce a known fact has no business scoring an unknown one.

Outputs: p2_summary.json (the grids + the verdict), p2_fire_walks.csv (per-fire, per-
bound checkpoint outcomes for P3/P4 — gitignored with the other CSVs).
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from agents.market_intelligence.delayed_entry_shadow import (  # real code, never re-implemented
    compute_ep_adr_dollar, day0_pseudo_bars, to_rth_5min, _trading_days,
)
from p1_probe import load_triggers, load_daily_closes, load_intraday_raw  # P1's loaders, reused

LAST_SESSION = date(2026, 9, 25)     # last daily bar in the P0 extract (09-26 is a Saturday)
CHECKPOINTS = (5, 10, 20)
PRIMARY_K = 10                       # P0 verdict: checkpoint stays s10
WINDOW = 20                          # the lane's watch window (LANE_SESSIONS)
TARGET_ADR, STOP_ADR = 2.0, 1.0
LADDER = (2.0, 3.0, 4.0, 6.0)        # tail-first: +m×ADR$ before −1×ADR$
PATTERNS = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")
BOUNDS = ("pess", "opt")
PASS_PP, PASS_N, PASS_NAMES, KILL_PP = 5.0, 150, 60, 2.0

TARGET, STOP, OPEN, ABSTAIN = "target", "stop", "open", "abstain"


def _f(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    return round(vals[len(vals) // 2], 3) if vals else None


def load_daily_opens():
    """{ticker: {date: open}} — P1's loader carries no open; the fillable-stop-buy read needs it."""
    out = defaultdict(dict)
    with open(HERE / "daily_closes.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["ticker"]][date.fromisoformat(r["trade_date"])] = _f(r["open_price"])
    return out


# ── the walker ────────────────────────────────────────────────────────────────────────

def first_passage(bars, entry, stop, target, bound):
    """bars: list of (h, l) or None (a hole), index 0 = the first bar walked. Returns
    (event, idx) — idx is the 0-based bar index at which the event happened; OPEN → the
    number of bars walked; ABSTAIN → the hole's index. pess checks the stop first on
    every bar, opt checks the target first: a bar holding both resolves differently
    under the two bounds, which is exactly the straddle the block wants counted twice."""
    for i, b in enumerate(bars):
        if b is None:
            return ABSTAIN, i
        h, l = b
        hit_stop = l <= stop
        hit_target = h >= target
        if bound == "pess":
            if hit_stop:
                return STOP, i
            if hit_target:
                return TARGET, i
        else:
            if hit_target:
                return TARGET, i
            if hit_stop:
                return STOP, i
    return OPEN, len(bars)


def at_checkpoint(event, idx, k, n_day0):
    """Fold a first-passage result to the checkpoint-K reading. Bars are laid out as
    [day-0 bars...] + [session 1..]; a session-j bar sits at index n_day0 + j - 1. A
    hole at or before session K abstains K; an event at or before session K resolves
    it; else K is OPEN (only asked when the row has >=K sessions elapsed)."""
    if event == ABSTAIN:
        return ABSTAIN if idx <= n_day0 + k - 1 else OPEN
    if event in (STOP, TARGET):
        return event if idx <= n_day0 + k - 1 else OPEN
    return OPEN


# ── input assembly ────────────────────────────────────────────────────────────────────

def session_bars(daily_for_ticker, sessions):
    """[(h, l) | None] for each expected session, in order — None marks a hole."""
    out = []
    for d in sessions:
        b = daily_for_ticker.get(d)
        if not b or b["high_price"] is None or b["low_price"] is None or b["close"] is None:
            out.append(None)
        else:
            out.append((b["high_price"], b["low_price"]))
    return out


def day0_bars_for_fire(trig, scale, stop, daily_for_ticker, intraday_raw):
    """Day-0 bars on the daily-table scale, mirroring compute_settlement's sources and
    abstain rule. Returns (bars, source). bars == None means ABSTAIN (minute-grade fire
    whose day low reached the stop, no $0 minute source)."""
    fire_date, ticker = trig["fire_date"], trig["ticker"]
    fb = daily_for_ticker.get(fire_date)
    if trig["fire_minute_et"] is None:
        # daily-grade fire: fold the whole fire-day bar (house convention)
        if not fb:
            return None, "missing_fire_day_bar"
        return [(fb["high_price"], fb["low_price"])], "daily_grade_fold"
    raw = intraday_raw.get((ticker, fire_date))
    if raw:
        bars5 = to_rth_5min(raw, fire_date)
        post5 = [b for b in bars5 if b["m"] > trig["fire_minute_et"]]
        if post5 or bars5:
            return [(b["h"] * scale, b["l"] * scale) for b in post5], "real_intraday_bars"
    if trig["day0_resolved"] is not None:
        pb = day0_pseudo_bars(trig["day0_resolved"], trig["day0_post_low"], trig["day0_post_high"])
        if pb is not None:
            return [(b["h"] * scale, b["l"] * scale) for b in pb], "cached_pseudo_bars"
    day_low = (trig["day_low"] * scale) if trig["day_low"] is not None else None
    if day_low is not None and day_low <= stop:
        return None, "missing_day0_minutes"
    return [], "minute_fire_no_day0_exposure"


def scale_factor(trig, daily_for_ticker):
    fb = daily_for_ticker.get(trig["fire_date"])
    if fb and fb["close"] and trig["day_close"]:
        return fb["close"] / trig["day_close"]
    return 1.0


# ── rate helpers ──────────────────────────────────────────────────────────────────────

def rate(rows, key):
    """rows: list of dicts with rows[key] in {target, stop, open}. (n, hits, pct)."""
    n = sum(1 for r in rows if r.get(key, ABSTAIN) != ABSTAIN)
    hits = sum(1 for r in rows if r.get(key) == TARGET)
    return n, hits, (100.0 * hits / n if n else None)


def gap(fires, controls, key, ctl_key=None):
    nf, hf, rf = rate(fires, key)
    nc, hc, rc = rate(controls, ctl_key or key)
    return {"n_fires": nf, "fire_hits": hf, "fire_pct": None if rf is None else round(rf, 2),
            "n_control": nc, "control_hits": hc, "control_pct": None if rc is None else round(rc, 2),
            "gap_pp": None if (rf is None or rc is None) else round(rf - rc, 2)}


def main():
    triggers = load_triggers()
    daily = load_daily_closes()
    opens = load_daily_opens()
    intraday_raw = load_intraday_raw()
    for t in triggers:
        for col in ("gap_day_close", "stop_width_pct"):
            t[col] = _f(t.get(col))
        t["stop_hit_date"] = date.fromisoformat(t["stop_hit_date"]) if t.get("stop_hit_date") else None
    print(f"triggers {len(triggers)} · tickers {len({t['ticker'] for t in triggers})} · "
          f"campaigns {len({(t['ticker'], t['ep_date']) for t in triggers})}")

    # ── ADR$ per campaign, on the daily-table scale, with the real function ──
    adr_by_campaign, adr_missing = {}, Counter()
    for t in triggers:
        key = (t["ticker"], t["ep_date"])
        if key in adr_by_campaign:
            continue
        dft = daily.get(t["ticker"], {})
        bars_asc = [dft[d] for d in sorted(dft)]
        ep_bar = dft.get(t["ep_date"])
        gc = ep_bar["close"] if ep_bar else None
        a, n = compute_ep_adr_dollar(bars_asc, t["ep_date"], gc)
        adr_by_campaign[key] = (a, n)
        if a is None:
            adr_missing["no_ep_day_bar" if gc is None else "no_pre_ep_bars"] += 1
    print(f"ADR$ computed for {sum(1 for v in adr_by_campaign.values() if v[0] is not None)} "
          f"of {len(adr_by_campaign)} campaigns; missing: {dict(adr_missing)}")

    # ── the fire walks ──
    fire_rows, fire_abstain = [], Counter()
    scale_flags = Counter()
    anchor = Counter()
    for t in triggers:
        dft = daily.get(t["ticker"], {})
        adr, adr_n = adr_by_campaign[(t["ticker"], t["ep_date"])]
        if adr is None or not t["entry_price"] or t["entry_price"] <= 0:
            fire_abstain["no_adr_or_entry"] += 1
            continue
        f = scale_factor(t, dft)
        scale_flags["rescaled_gt_0p5pct" if abs(f - 1) >= 0.005 else "scale_1"] += 1
        entry = t["entry_price"] * f
        stop = entry - STOP_ADR * adr
        sessions = _trading_days(t["fire_date"] + timedelta(days=1), LAST_SESSION)[:WINDOW]
        elapsed = len(sessions)
        d0, d0_src = day0_bars_for_fire(t, f, stop, dft, intraday_raw)
        row = {"id": t["id"], "ticker": t["ticker"], "ep_date": t["ep_date"].isoformat(),
               "rung": t["rung"], "reentry_shape": t["reentry_shape"],
               "fire_date": t["fire_date"].isoformat(), "resolution": t["resolution"],
               "sessions_elapsed": elapsed, "scale_factor": round(f, 6),
               "entry_scaled": round(entry, 6), "adr_dollar": round(adr, 6), "adr_n": adr_n,
               "stop_width_pct": t["stop_width_pct"], "day0_source": d0_src}
        sbars = session_bars(dft, sessions)
        # ── the anchor: incumbent stop, no target, reproduce stop_hit_date / time exit ──
        if t["outcome"] in ("stop", "time_exit") and t["stop_price"]:
            inc_stop = t["stop_price"] * f
            a_d0, a_src = day0_bars_for_fire(t, f, inc_stop, dft, intraday_raw)
            full_sessions = _trading_days(t["fire_date"] + timedelta(days=1), LAST_SESSION)[:WINDOW]
            if a_d0 is None:
                anchor["abstain_day0"] += 1
            else:
                ev, idx = first_passage(a_d0 + session_bars(dft, full_sessions), entry, inc_stop,
                                        float("inf"), "pess")
                n0 = len(a_d0)
                if ev == ABSTAIN:
                    anchor["abstain_hole"] += 1
                elif ev == STOP:
                    hit = t["fire_date"] if idx < n0 else full_sessions[idx - n0]
                    if t["outcome"] == "stop" and t["stop_hit_date"] == hit:
                        anchor["match"] += 1
                    else:
                        anchor["mismatch"] += 1
                        if anchor["mismatch"] <= 12:
                            print(f"  anchor mismatch {t['ticker']} {t['fire_date']} {t['rung']} "
                                  f"rec={t['outcome']}@{t['stop_hit_date']} probe=stop@{hit} src={a_src} f={f:.3f}")
                else:   # OPEN through the walked sessions
                    if len(full_sessions) < WINDOW:
                        anchor["open_window_incomplete"] += 1
                    elif t["outcome"] == "time_exit":
                        anchor["match"] += 1
                    else:
                        anchor["mismatch"] += 1
                        if anchor["mismatch"] <= 12:
                            print(f"  anchor mismatch {t['ticker']} {t['fire_date']} {t['rung']} "
                                  f"rec={t['outcome']}@{t['stop_hit_date']} probe=open src={a_src} f={f:.3f}")
        # fire-at-CLOSE variant: enter at the fire session's close, no day-0 exposure —
        # readable even when the level-entry walk must abstain on day 0
        fb = dft.get(t["fire_date"])
        if fb and fb["close"]:
            e2 = fb["close"]
            for b in BOUNDS:
                ev, idx = first_passage(sbars, e2, e2 - STOP_ADR * adr, e2 + TARGET_ADR * adr, b)
                for k in CHECKPOINTS:
                    if elapsed >= k:
                        row[f"close_{b}_s{k}"] = at_checkpoint(ev, idx, k, 0)
        # ── the P2 walk: +m×ADR before −1×ADR, both bounds, the ladder ──
        if d0 is None:
            fire_abstain[d0_src] += 1
            row.update({f"{b}_s{k}": ABSTAIN for b in BOUNDS for k in CHECKPOINTS})
            row.update({f"{b}_m{m:g}_s{k}": ABSTAIN for b in BOUNDS for m in LADDER for k in CHECKPOINTS})
            row.update({f"fill_{b}_s{k}": ABSTAIN for b in BOUNDS for k in CHECKPOINTS})
            row.update({f"fill_{b}_m{m:g}_s{k}": ABSTAIN for b in BOUNDS for m in LADDER for k in CHECKPOINTS})
            row["level_priced"] = t["fire_minute_et"] is None
            row["abstain"] = d0_src
            fire_rows.append(row)
            continue
        n0 = len(d0)
        bars = d0 + sbars
        row["n_day0"] = n0
        for b in BOUNDS:
            for m in LADDER:
                ev, idx = first_passage(bars, entry, stop, entry + m * adr, b)
                if m == TARGET_ADR:
                    row[f"{b}_event"] = ev
                    row[f"{b}_hit_idx"] = idx if ev in (STOP, TARGET) else None
                for k in CHECKPOINTS:
                    if elapsed < k:
                        continue
                    row[f"{b}_m{m:g}_s{k}"] = at_checkpoint(ev, idx, k, n0)
            for k in CHECKPOINTS:
                if elapsed >= k:
                    row[f"{b}_s{k}"] = row[f"{b}_m{TARGET_ADR:g}_s{k}"]
        # THE FILLABLE STOP-BUY. A daily-grade fire is a resting stop-buy AT the level
        # (ep_high_break's own daily fires and every new_high_break re-entry on every
        # rung, via replay_level_break) and the lane records the LEVEL as entry_price
        # even when the session OPENED ABOVE it — a stop-buy would have filled at the
        # open. entry = max(level, fire-day open) removes that head start; a minute-grade
        # fire enters at a traded 5-min close and is unchanged. Reported beside the bar,
        # never in place of it: the bar is fixed on the recorded entry_price.
        o = opens.get(t["ticker"], {}).get(t["fire_date"])
        row["level_priced"] = t["fire_minute_et"] is None
        e3 = entry
        if t["fire_minute_et"] is None and o is not None and o > 0:
            row["gap_over_adr"] = round(max(0.0, (o - entry) / adr), 4)
            e3 = max(entry, o)
        stop3 = e3 - STOP_ADR * adr
        d03 = d0 if e3 == entry else day0_bars_for_fire(t, f, stop3, dft, intraday_raw)[0]
        n03 = len(d03) if d03 is not None else 0
        for b in BOUNDS:
            for m in LADDER:
                if d03 is None:
                    ev, idx = ABSTAIN, 0
                else:
                    ev, idx = first_passage(d03 + sbars, e3, stop3, e3 + m * adr, b)
                for k in CHECKPOINTS:
                    if elapsed >= k:
                        row[f"fill_{b}_m{m:g}_s{k}"] = at_checkpoint(ev, idx, k, n03)
            for k in CHECKPOINTS:
                if elapsed >= k:
                    row[f"fill_{b}_s{k}"] = row[f"fill_{b}_m{TARGET_ADR:g}_s{k}"]
        fire_rows.append(row)
    print(f"fire rows walked {len(fire_rows)}; excluded/abstained {dict(fire_abstain)}; "
          f"scale {dict(scale_flags)}")
    anchor_scored = anchor["match"] + anchor["mismatch"]
    anchor_pct = round(100.0 * anchor["match"] / anchor_scored, 3) if anchor_scored else None
    print(f"ANCHOR (incumbent stop, no target → stop_hit_date / time_exit): "
          f"{anchor['match']}/{anchor_scored} = {anchor_pct}%  detail={dict(anchor)}")

    # ── the control: every non-fire session in each fired campaign's 20-session window ──
    fires_by_campaign = defaultdict(set)
    for t in triggers:
        fires_by_campaign[(t["ticker"], t["ep_date"])].add(t["fire_date"])
    control_rows, control_skip = [], Counter()
    for (ticker, ep_date), fire_dates in fires_by_campaign.items():
        adr, _ = adr_by_campaign[(ticker, ep_date)]
        if adr is None:
            control_skip["no_adr"] += 1
            continue
        dft = daily.get(ticker, {})
        window = _trading_days(ep_date + timedelta(days=1), LAST_SESSION)[:WINDOW]
        for j, s in enumerate(window, start=1):
            is_fire = s in fire_dates
            b = dft.get(s)
            if not b or b["close"] is None:
                control_skip["no_close_bar"] += 1
                continue
            entry = b["close"]
            after = _trading_days(s + timedelta(days=1), LAST_SESSION)[:WINDOW]
            elapsed = len(after)
            sbars = session_bars(dft, after)
            row = {"ticker": ticker, "ep_date": ep_date.isoformat(), "session_date": s.isoformat(),
                   "session_idx": j, "is_fire_session": is_fire, "sessions_elapsed": elapsed,
                   "entry": entry, "adr_dollar": adr}
            for bnd in BOUNDS:
                for m in LADDER:
                    ev, idx = first_passage(sbars, entry, entry - STOP_ADR * adr, entry + m * adr, bnd)
                    for k in CHECKPOINTS:
                        if elapsed >= k:
                            row[f"{bnd}_m{m:g}_s{k}"] = at_checkpoint(ev, idx, k, 0)
                for k in CHECKPOINTS:
                    if elapsed >= k:
                        row[f"{bnd}_s{k}"] = row[f"{bnd}_m{TARGET_ADR:g}_s{k}"]
            control_rows.append(row)
    n_nonfire = sum(1 for r in control_rows if not r["is_fire_session"])
    print(f"control sessions walked {len(control_rows)} (non-fire {n_nonfire}, fire-session-at-close "
          f"{len(control_rows) - n_nonfire}); skipped {dict(control_skip)}")

    # ── grids ──
    def pop(rows, k, key_prefix=""):
        return [r for r in rows if r["sessions_elapsed"] >= k and f"{key_prefix}pess_s{k}" in r]

    def fires_of(p, k, shape=None, width_floor=None):
        out = []
        for r in fire_rows:
            if r["rung"] != p or r["sessions_elapsed"] < k:
                continue
            if shape and r["reentry_shape"] != shape:
                continue
            if width_floor is not None and (r["stop_width_pct"] is None or r["stop_width_pct"] < width_floor):
                continue
            out.append(r)
        return out

    def matched_controls(fires, k, nonfire_only=True):
        camps = {(r["ticker"], r["ep_date"]) for r in fires}
        return [c for c in control_rows if (c["ticker"], c["ep_date"]) in camps
                and c["sessions_elapsed"] >= k and (not nonfire_only or not c["is_fire_session"])]

    grid = {}
    for p in PATTERNS:
        grid[p] = {}
        for k in CHECKPOINTS:
            fires = fires_of(p, k)
            ctl = matched_controls(fires, k)
            cell = {"n_fires_in_population": len(fires),
                    "n_fire_abstain": sum(1 for r in fires if r.get(f"pess_s{k}", ABSTAIN) == ABSTAIN),
                    "n_names": len({r["ticker"] for r in fires if r.get(f"pess_s{k}", ABSTAIN) != ABSTAIN}),
                    "n_campaigns": len({(r["ticker"], r["ep_date"]) for r in fires}),
                    "n_control_sessions": len(ctl)}
            for b in BOUNDS:
                cell[b] = gap(fires, ctl, f"{b}_s{k}")
            cell["straddle_decided_fires"] = sum(
                1 for r in fires if r.get(f"pess_s{k}", ABSTAIN) != ABSTAIN and r[f"pess_s{k}"] != r[f"opt_s{k}"])
            cell["straddle_decided_controls"] = sum(
                1 for c in ctl if c.get(f"pess_s{k}", ABSTAIN) != ABSTAIN and c[f"pess_s{k}"] != c[f"opt_s{k}"])
            # tail ladder, tail-first
            cell["ladder"] = {}
            for m in LADDER:
                cell["ladder"][f"+{m:g}ADR"] = {b: gap(fires, ctl, f"{b}_m{m:g}_s{k}") for b in BOUNDS}
            # the fillable stop-buy read of the same cell (informational, see docstring)
            cell["fillable"] = {b: gap(fires, ctl, f"fill_{b}_s{k}", f"{b}_s{k}") for b in BOUNDS}
            cell["fillable_ladder"] = {}
            for m in LADDER:
                cell["fillable_ladder"][f"+{m:g}ADR"] = {
                    b: gap(fires, ctl, f"fill_{b}_m{m:g}_s{k}", f"{b}_m{m:g}_s{k}") for b in BOUNDS}
            lp = [r for r in fires if r.get("level_priced")]
            cell["level_priced_fires"] = {
                "n_level_priced": len(lp),
                "n_gap_over_open_above_level": sum(1 for r in lp if r.get("gap_over_adr", 0) > 0),
                "median_gap_over_adr_when_over": _median([r["gap_over_adr"] for r in lp if r.get("gap_over_adr", 0) > 0]),
            }
            grid[p][f"s{k}"] = cell

    # ── the pass bar and kill rule at the primary checkpoint ──
    k = PRIMARY_K
    verdicts = {}
    for p in PATTERNS:
        fires = fires_of(p, k)
        ctl = matched_controls(fires, k)
        cell = grid[p][f"s{k}"]
        g_pess = cell["pess"]["gap_pp"]
        # drop-best-NAME: the name whose removal (from BOTH sides) shrinks the pess gap most
        best_name, best_gap = None, None
        for nm in {r["ticker"] for r in fires}:
            g2 = gap([r for r in fires if r["ticker"] != nm],
                     [c for c in ctl if c["ticker"] != nm], f"pess_s{k}")["gap_pp"]
            if g2 is not None and (best_gap is None or g2 < best_gap):
                best_name, best_gap = nm, g2
        checks = {
            "gap_pess_ge_5pp": g_pess is not None and g_pess >= PASS_PP,
            "drop_best_name": {"name": best_name, "gap_pp_after": best_gap,
                               "holds": best_gap is not None and best_gap >= PASS_PP},
            "n_ge_150": cell["pess"]["n_fires"] >= PASS_N,
            "names_ge_60": cell["n_names"] >= PASS_NAMES,
        }
        checks["entry_edge"] = bool(checks["gap_pess_ge_5pp"] and checks["drop_best_name"]["holds"]
                                    and checks["n_ge_150"] and checks["names_ge_60"])
        checks["within_2pp_both_bounds"] = all(
            cell[b]["gap_pp"] is not None and abs(cell[b]["gap_pp"]) <= KILL_PP for b in BOUNDS)
        # the same four checks on the FILLABLE entry — informational, NOT the bar
        fg = cell["fillable"]["pess"]["gap_pp"]
        fbest_name, fbest_gap = None, None
        for nm in {r["ticker"] for r in fires}:
            g2 = gap([r for r in fires if r["ticker"] != nm],
                     [c for c in ctl if c["ticker"] != nm], f"fill_pess_s{k}", f"pess_s{k}")["gap_pp"]
            if g2 is not None and (fbest_gap is None or g2 < fbest_gap):
                fbest_name, fbest_gap = nm, g2
        checks["fillable_read_not_the_bar"] = {
            "gap_pess_pp": fg, "gap_opt_pp": cell["fillable"]["opt"]["gap_pp"],
            "drop_best_name": {"name": fbest_name, "gap_pp_after": fbest_gap},
            "n_fires": cell["fillable"]["pess"]["n_fires"],
            "would_clear_5pp": fg is not None and fg >= PASS_PP and fbest_gap is not None and fbest_gap >= PASS_PP,
            "within_2pp_both_bounds": all(cell["fillable"][b]["gap_pp"] is not None
                                          and abs(cell["fillable"][b]["gap_pp"]) <= KILL_PP for b in BOUNDS),
        }
        verdicts[p] = checks
    any_edge = any(v["entry_edge"] for v in verdicts.values())
    kill = all(v["within_2pp_both_bounds"] for v in verdicts.values())
    between = [p for p, v in verdicts.items()
               if not v["entry_edge"] and grid[p][f"s{k}"]["pess"]["gap_pp"] is not None
               and grid[p][f"s{k}"]["pess"]["gap_pp"] > KILL_PP]
    verdict = "pass" if any_edge else ("kill" if kill else "pass")

    # ── robustness reads (informational, never the bar) ──
    robust = {}
    for p in PATTERNS:
        fires = fires_of(p, k)
        ctl = matched_controls(fires, k)
        r = {}
        # (a) fire entered at the fire session's CLOSE, same entry convention as the control
        r["fire_at_close"] = {b: gap(fires, ctl, f"close_{b}_s{k}", f"{b}_s{k}") for b in BOUNDS}
        # (a3) where the fire's hits come from: day 0 vs later, daily-grade vs minute-grade
        hits = [x for x in fires if x.get(f"pess_s{k}") == TARGET]
        r["pess_hits_on_day0"] = {"n_hits": len(hits),
                                  "n_on_day0": sum(1 for x in hits if x.get("pess_hit_idx") is not None
                                                   and x["pess_hit_idx"] < x.get("n_day0", 0))}
        r["by_resolution_pess"] = {}
        for res in ("daily", "minute_5"):
            fr = [x for x in fires if x["resolution"] == res]
            r["by_resolution_pess"][res] = gap(fr, matched_controls(fr, k), f"pess_s{k}")
        # (b) first-shape only
        ff = fires_of(p, k, shape="first")
        r["first_shape_only"] = {b: gap(ff, matched_controls(ff, k), f"{b}_s{k}") for b in BOUNDS}
        # (c) width floor re-applied (the 09-22 read's exclusion)
        fw = fires_of(p, k, width_floor=0.5)
        r["stop_width_ge_0p5"] = {b: gap(fw, matched_controls(fw, k), f"{b}_s{k}") for b in BOUNDS}
        # (d) control = ALL sessions in the window at close, fire sessions included
        r["control_all_sessions_at_close"] = {b: gap(fires, matched_controls(fires, k, nonfire_only=False),
                                                     f"{b}_s{k}") for b in BOUNDS}
        # (e) paired per-campaign difference (equal weight per campaign)
        fc, cc = defaultdict(list), defaultdict(list)
        for x in fires:
            if x.get(f"pess_s{k}", ABSTAIN) != ABSTAIN:
                fc[(x["ticker"], x["ep_date"])].append(1.0 if x[f"pess_s{k}"] == TARGET else 0.0)
        for c in ctl:
            if c.get(f"pess_s{k}", ABSTAIN) != ABSTAIN:
                cc[(c["ticker"], c["ep_date"])].append(1.0 if c[f"pess_s{k}"] == TARGET else 0.0)
        diffs = [sum(fc[c]) / len(fc[c]) - sum(cc[c]) / len(cc[c]) for c in fc if c in cc]
        diffs.sort()
        r["paired_per_campaign_pess"] = {
            "n_campaigns": len(diffs),
            "mean_diff_pp": round(100 * sum(diffs) / len(diffs), 2) if diffs else None,
            "median_diff_pp": round(100 * diffs[len(diffs) // 2], 2) if diffs else None,
            "share_campaigns_fire_better": round(100 * sum(1 for d in diffs if d > 0) / len(diffs), 1) if diffs else None,
            "share_campaigns_control_better": round(100 * sum(1 for d in diffs if d < 0) / len(diffs), 1) if diffs else None,
        }
        # (f) by re-entry shape
        r["by_shape_pess"] = {}
        r["by_shape_fillable_pess"] = {}
        for sh in ("first", "same_pattern", "new_high_break"):
            fs = fires_of(p, k, shape=sh)
            r["by_shape_pess"][sh] = gap(fs, matched_controls(fs, k), f"pess_s{k}")
            r["by_shape_fillable_pess"][sh] = gap(fs, matched_controls(fs, k), f"fill_pess_s{k}", f"pess_s{k}")
        r["by_resolution_fillable_pess"] = {}
        for res in ("daily", "minute_5"):
            fr = [x for x in fires if x["resolution"] == res]
            r["by_resolution_fillable_pess"][res] = gap(fr, matched_controls(fr, k), f"fill_pess_s{k}", f"pess_s{k}")
        robust[p] = r

    # ── pooled (all four) for context only ──
    pooled = {}
    for kk in CHECKPOINTS:
        fires = [r for r in fire_rows if r["sessions_elapsed"] >= kk]
        ctl = matched_controls(fires, kk)
        pooled[f"s{kk}"] = {b: gap(fires, ctl, f"{b}_s{kk}") for b in BOUNDS}

    # ── print the grid ──
    print("\n=== +2×ADR$ before −1×ADR$ — fire rate vs matched non-fire control (pp) ===")
    for p in PATTERNS:
        print(f"\n{p}")
        for kk in CHECKPOINTS:
            c = grid[p][f"s{kk}"]
            print(f"  s{kk:<2} n={c['pess']['n_fires']:>4} names={c['n_names']:>3} ctl={c['n_control_sessions']:>5} | "
                  f"pess fire {c['pess']['fire_pct']:>5}% ctl {c['pess']['control_pct']:>5}% gap {c['pess']['gap_pp']:>6}pp | "
                  f"opt fire {c['opt']['fire_pct']:>5}% ctl {c['opt']['control_pct']:>5}% gap {c['opt']['gap_pp']:>6}pp | "
                  f"straddle f/c {c['straddle_decided_fires']}/{c['straddle_decided_controls']} abst {c['n_fire_abstain']}")
        v = verdicts[p]
        print(f"  s10 checks: gap>=5 {v['gap_pess_ge_5pp']} · drop {v['drop_best_name']['name']} → "
              f"{v['drop_best_name']['gap_pp_after']}pp · n>=150 {v['n_ge_150']} · names>=60 {v['names_ge_60']} "
              f"→ edge={v['entry_edge']} · within±2 both bounds={v['within_2pp_both_bounds']}")
        lad = grid[p]["s10"]["ladder"]
        print("  tail ladder s10 (pess fire/ctl): " + "  ".join(
            f"{m}: {lad[m]['pess']['fire_pct']}/{lad[m]['pess']['control_pct']}" for m in lad))
        rb = robust[p]
        print(f"  robustness s10 pess: at-close gap {rb['fire_at_close']['pess']['gap_pp']}pp "
              f"(fire {rb['fire_at_close']['pess']['fire_pct']}%) · first-only "
              f"{rb['first_shape_only']['pess']['gap_pp']}pp (n={rb['first_shape_only']['pess']['n_fires']}) · "
              f"width>=0.5 {rb['stop_width_ge_0p5']['pess']['gap_pp']}pp · ctl-all-sessions "
              f"{rb['control_all_sessions_at_close']['pess']['gap_pp']}pp · paired mean "
              f"{rb['paired_per_campaign_pess']['mean_diff_pp']}pp over {rb['paired_per_campaign_pess']['n_campaigns']} campaigns")
        print(f"  hits on day 0: {rb['pess_hits_on_day0']['n_on_day0']}/{rb['pess_hits_on_day0']['n_hits']} · "
              f"by resolution pess gap: daily {rb['by_resolution_pess']['daily']['gap_pp']}pp "
              f"(n={rb['by_resolution_pess']['daily']['n_fires']}) · minute {rb['by_resolution_pess']['minute_5']['gap_pp']}pp "
              f"(n={rb['by_resolution_pess']['minute_5']['n_fires']})")
        c10 = grid[p]["s10"]
        fv = verdicts[p]["fillable_read_not_the_bar"]
        lpf = c10["level_priced_fires"]
        print(f"  FILLABLE stop-buy (entry=max(level, open); not the bar): s10 pess fire {c10['fillable']['pess']['fire_pct']}% "
              f"ctl {c10['fillable']['pess']['control_pct']}% gap {c10['fillable']['pess']['gap_pp']}pp · opt gap "
              f"{c10['fillable']['opt']['gap_pp']}pp · drop {fv['drop_best_name']['name']} → {fv['drop_best_name']['gap_pp_after']}pp · "
              f"would clear 5pp {fv['would_clear_5pp']} · within±2 {fv['within_2pp_both_bounds']} | level-priced fires "
              f"{lpf['n_level_priced']}, of which opened above the level {lpf['n_gap_over_open_above_level']} "
              f"(median over-shoot {lpf['median_gap_over_adr_when_over']} ADR)")
        print("  fillable tail ladder s10 (pess fire/ctl): " + "  ".join(
            f"{m}: {c10['fillable_ladder'][m]['pess']['fire_pct']}/{c10['fillable_ladder'][m]['pess']['control_pct']}" for m in c10["fillable_ladder"]))
        print(f"  fillable by shape pess: " + " · ".join(
            f"{sh} {rb['by_shape_fillable_pess'][sh]['gap_pp']}pp (n={rb['by_shape_fillable_pess'][sh]['n_fires']})"
            for sh in rb["by_shape_fillable_pess"]) + f" · by resolution: daily {rb['by_resolution_fillable_pess']['daily']['gap_pp']}pp "
              f"minute {rb['by_resolution_fillable_pess']['minute_5']['gap_pp']}pp")
    print(f"\nVERDICT: {verdict} · any pattern with entry edge: {any_edge} · kill rule (all four within ±2pp "
          f"both bounds at s10): {kill} · between 2pp and 5pp: {between}")

    summary = {
        "generated": datetime.now().isoformat(),
        "last_session_in_extract": LAST_SESSION.isoformat(),
        "conventions": {
            "unit": "EP-anchored ADR$ (compute_ep_adr_dollar on mi_daily_closes, EP-day close from the same table)",
            "target_stop": f"+{TARGET_ADR:g}xADR$ before -{STOP_ADR:g}xADR$",
            "population": "sessions elapsed after fire_date >= K in the extract; never settlement status; re-entry shapes pooled into their rung",
            "control": "every NON-FIRE session of the 20-session window after ep_date, for the campaigns where the pattern fired, entered at that session's close, same clock and abstain rules",
            "bounds": "pess = stop checked first on every bar; opt = target checked first",
            "day0": "daily-grade: whole fire-day bar folded; minute-grade: post-fire 5-min bars (real or cached pseudo bar) when available, else abstain if day low <= stop, else no day-0 event",
            "price_scale": "every fire-time input x dc_close(fire_date)/trigger.day_close (adjusted-history fix)",
        },
        "n_triggers": len(triggers),
        "n_fire_rows_walked": len(fire_rows),
        "fire_exclusions": dict(fire_abstain),
        "scale_factor_flags": dict(scale_flags),
        "adr_missing_campaigns": dict(adr_missing),
        "anchor_incumbent_stop_reproduction": {**dict(anchor), "scored": anchor_scored, "match_pct": anchor_pct},
        "control": {"n_sessions_walked": len(control_rows), "n_nonfire": n_nonfire, "skipped": dict(control_skip)},
        "grid": grid,
        "pooled_all_patterns_context_only": pooled,
        "pass_bar_s10": verdicts,
        "robustness_s10": robust,
        "verdict": {"verdict": verdict, "any_pattern_entry_edge": any_edge,
                    "kill_rule_fired": kill, "patterns_between_2pp_and_5pp_pess": between,
                    "fillable_read_not_the_bar": {
                        p: {"gap_pess_pp": v["fillable_read_not_the_bar"]["gap_pess_pp"],
                            "gap_opt_pp": v["fillable_read_not_the_bar"]["gap_opt_pp"],
                            "would_clear_5pp": v["fillable_read_not_the_bar"]["would_clear_5pp"],
                            "within_2pp_both_bounds": v["fillable_read_not_the_bar"]["within_2pp_both_bounds"]}
                        for p, v in verdicts.items()},
                    "fillable_kill_rule_would_fire": all(v["fillable_read_not_the_bar"]["within_2pp_both_bounds"]
                                                         for v in verdicts.values())},
    }
    with open(HERE / "p2_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    cols = ["id", "ticker", "ep_date", "rung", "reentry_shape", "fire_date", "resolution", "sessions_elapsed",
            "scale_factor", "entry_scaled", "adr_dollar", "adr_n", "stop_width_pct", "day0_source", "abstain"]
    cols += [f"{b}_s{k}" for b in BOUNDS for k in CHECKPOINTS]
    cols += [f"{b}_m{m:g}_s{k}" for b in BOUNDS for m in LADDER for k in CHECKPOINTS]
    cols += [f"close_{b}_s{k}" for b in BOUNDS for k in CHECKPOINTS]
    cols += [f"fill_{b}_s{k}" for b in BOUNDS for k in CHECKPOINTS]
    cols += [f"fill_{b}_m{m:g}_s{k}" for b in BOUNDS for m in LADDER for k in CHECKPOINTS]
    cols += ["n_day0", "pess_event", "pess_hit_idx", "opt_event", "opt_hit_idx", "level_priced", "gap_over_adr"]
    with open(HERE / "p2_fire_walks.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in fire_rows:
            w.writerow(r)
    with open(HERE / "p2_control_walks.csv", "w", newline="") as fh:
        ccols = ["ticker", "ep_date", "session_date", "session_idx", "is_fire_session", "sessions_elapsed",
                 "entry", "adr_dollar"] + [f"{b}_s{k}" for b in BOUNDS for k in CHECKPOINTS]
        w = csv.DictWriter(fh, fieldnames=ccols, extrasaction="ignore")
        w.writeheader()
        for r in control_rows:
            w.writerow(r)
    print(f"\nwrote {HERE / 'p2_summary.json'}, p2_fire_walks.csv, p2_control_walks.csv")


if __name__ == "__main__":
    main()
