"""#545 Phase 1 — THE RETRY TEST (pre-registered in
docs/design/545_entry_exit_program_v2_2026-09-02.md §7 Phase 1; the pre-registration is binding).

Question: on the same 267 caught EPs, does a TIGHT stop with up to 3 tries beat ONE try at
the 0.75-1.0xADR stop — measured per NAME at equal dollar risk per attempt?

The operator's idea, verbatim: "with tight stop losses, to get positioned often requires
multiple tries, this is the trade off — you take smaller cuts but more tries vs bigger cuts
but less tries... we keep a very tight stop... but we take more tries... if we get shaken
out by intraday volatility, we just retry let's say up to 3 times."

FIDELITY CONTRACT (extends `_562_backfill_replay.py` + `_562_stop_grid_probe.py`):
  - Gate 1: the backfill walk is re-run and must reproduce the recorded 602 first-attempt
    fires exactly (entry, stop, fire_date) before anything is varied.
  - Gate 2: the attempts=1 column of this loop must reproduce `_562grid_rows.tsv`'s
    adr_025/050/075/100 rows (status, realized_r, realized_r_trail) with 0 drift — the
    campaign loop's first leg IS the grid.
  - Every rung decision, re-entry pattern and settlement goes through the lane's OWN pure
    functions (delayed_entry_shadow.py). The re-entry shapes are the lane's two recorded
    shapes, mirrored from `_record_reentries_for` / `_replay_same_pattern_reclaim` /
    `_replay_same_pattern_620` / `replay_level_break`:
      same_pattern    = fresh-state walk of the rung's OWN pattern from the session AFTER the
                        stop-out (the "same-trigger re-arm"); for ep_high_break it is a
                        re-touch of the EP-day high (level, daily-provable)
      new_high_break  = a break above MAX(EP-day high, every session high from the EP through
                        the latest stop-out) — buy = the level (daily-provable)
    The lane records both x1 after the FIRST attempt; this loop chains them: after every
    stop-out the same two shapes are searched again from a fresh state, the new-high level
    re-referenced through the latest stop-out.
  - PRIMARY re-entry policy (declared before the run): "either" = whichever shape fires
    first after the stop-out (the faithful re-drive of the lane, which records both; the
    policy most generous to catching). Ties on the same day take same_pattern (the
    minute-resolved one). Single-shape policies are SENSITIVITY only.
  - A re-entry opens ONLY after a STOP-OUT. A trail exit / time exit ends the campaign — a
    management exit is not "shaken out". The re-entry window is the lane's
    REENTRY_WATCH_SESSIONS (20 trading sessions) starting the session AFTER the stop-out.
  - Stop for EVERY attempt = that attempt's entry - k x ADR$ with the EP-anchored ADR$
    (compute_ep_adr_dollar) fixed for the campaign — the #616 variant basis, identical to
    how the lane stamps a re-entry row. Level-break attempts derive the touch bar from
    contiguous 5-min bars when present (the grid probe's `derived_touch` convention); else
    they settle daily-grade with the pess day-0 stop-first rule. Both are counted.
  - THE ABSTAIN RULE: a session the fresh walk needs minutes for with none stored is a
    blind session (facts fold, no fire, counted); a settlement that cannot complete abstains
    and the campaign is CENSORED under that cell — never a fabricated fill.
  - READABILITY (chained maturity): a campaign is readable under a cell only if every
    attempt in its chain is MATURE (20 post-fire sessions existed by 2026-08-31) and every
    re-entry window searched with no fire was FULLY OBSERVABLE (20 sessions existed). The
    pass-bar comparison runs on the COMMON readable set per rung (readable under every
    stop x attempts x arm of the primary policy) — apples to apples; each cell's own
    readable n is shown beside it.
  - Equal dollar risk per attempt: each attempt's R is in its OWN units (risk = entry -
    stop), so summing attempts sums equal-dollar bets. Per-name total R is the unit of
    account; a per-trade average is NOT an output (it hides the retries).

Usage:
    python scripts/probes/_545_retry_test.py run      # -> _545rt_rows.tsv, _545rt_chains.tsv
    python scripts/probes/_545_retry_test.py report   # aggregate tables -> stdout
    python scripts/probes/_545_retry_test.py handwalk # raw-bar traces of two chained campaigns

Throwaway diagnostic (scripts/probes/ convention). Read-only; consumes only the already
captured `_562bf_*` / `_562sp_extra_minutes.tsv` / `_562grid_rows.tsv` files — NO prod access.
Writes only its own TSVs next to itself. No thresholds touched, no live code, THE LINE intact.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _562_backfill_replay as bf  # noqa: E402
import _562_stop_population_probe as sp  # noqa: E402
from agents.market_intelligence.delayed_entry_shadow import (  # noqa: E402
    REENTRY_WATCH_SESSIONS,
    RUNG_620_PROX,
    RUNG_EP_CLOSE,
    RUNG_EP_HIGH,
    RUNG_EP_LOW,
    WARMUP_SESSIONS_620,
    _trading_days,
    compute_settlement,
    evaluate_session_620,
    evaluate_session_daily,
    evaluate_session_minute,
    new_state,
    replay_level_break,
    session_needs_minutes,
    session_needs_minutes_620,
)

HORIZON = bf.LAST_DATA_DAY
ADR_LADDER = (0.25, 0.50, 0.75, 1.00)
CAPS = (1, 2, 3, 0)                 # 0 = unlimited (bounded only by the data)
SHAPES = ("either", "same_pattern", "new_high_break")
PRIMARY_SHAPE = "either"
ARMS = ("none", "trail")
RUNGS = (RUNG_EP_LOW, RUNG_EP_CLOSE, RUNG_EP_HIGH, RUNG_620_PROX)
MONTHS = ("2026-05", "2026-06", "2026-07", "2026-08")


def kname(frac):
    return f"adr_{int(frac * 100):03d}"


def capname(cap):
    return "unl" if cap == 0 else str(cap)


# ── the campaign context ───────────────────────────────────────────────────────────────


def _ctx(c, daily):
    bars = daily.get(c["ticker"], {})
    epb = bars[c["ep_date"]]
    return {
        "tkr": c["ticker"], "ep": c["ep_date"], "bars": bars, "ordered": sorted(bars),
        "gl": epb["low_price"], "gc": epb["close"], "gh": epb["high_price"],
        "adr": c["adr_dollar"],
    }


def _prior_low(ctx, d):
    prior = [x for x in ctx["ordered"] if x < d]
    return ctx["bars"][prior[-1]]["low_price"] if prior else None


def _locate_first_fire(f, ctx, minutes):
    """The grid probe's fire-bar convention, verbatim: minute fires carry their bar;
    daily-grade ep_high_break fires derive the first touch when the 5-min series is
    gap-free through it."""
    bars5 = minutes.get((ctx["tkr"], f["fire_date"]), [])
    fm, derived = f["fire_minute"], False
    if fm is None and f["rung"] == RUNG_EP_HIGH and bars5:
        k = next((i for i, b in enumerate(bars5) if b["h"] >= ctx["gh"]), None)
        if k is not None and sp._contiguous_to(bars5, k):
            fm, derived = bars5[k]["m"], True
    return fm, derived


def _locate_level_touch(level, fire_date, ctx, minutes):
    bars5 = minutes.get((ctx["tkr"], fire_date), [])
    if not bars5:
        return None, False
    k = next((i for i, b in enumerate(bars5) if b["h"] >= level), None)
    if k is not None and sp._contiguous_to(bars5, k):
        return bars5[k]["m"], True
    return None, False


def _settle(ctx, minutes, entry, stop, fire_date, fm):
    fb = ctx["bars"].get(fire_date) or {}
    fire_day_bar = {"h": fb.get("high_price"), "l": fb.get("low_price"), "c": fb.get("close")}
    bars5 = minutes.get((ctx["tkr"], fire_date), [])
    post5 = [b for b in bars5 if b["m"] > fm] if fm is not None else None
    sessions = _trading_days(fire_date + timedelta(days=1), HORIZON)
    closes_before = [ctx["bars"][d]["close"] for d in ctx["ordered"]
                     if d < fire_date and ctx["bars"][d]["close"] is not None]
    res = compute_settlement(entry=entry, stop=stop, fire_minute=fm,
                             fire_day_bar=fire_day_bar, post_fire_bars5=post5,
                             sessions=sessions, bars_by_day=ctx["bars"],
                             closes_before_fire=closes_before)
    res["_sessions"] = sessions
    return res


# ── the re-entry shapes (offline mirrors of the lane's recording pass) ─────────────────


def _reentry_same_pattern_reclaim(rung, ctx, sessions, minutes):
    """Mirror of `_replay_same_pattern_reclaim`: fresh state, same evaluators, only THIS
    rung's fire is taken. Returns (hit | None, missing, needed_missing)."""
    st, missing, blind = new_state(), 0, []
    gl, gc, gh = ctx["gl"], ctx["gc"], ctx["gh"]
    for d in sessions:
        b = ctx["bars"].get(d)
        if not b or b["high_price"] is None or b["low_price"] is None or b["close"] is None:
            missing += 1
            continue
        hi, lo = b["high_price"], b["low_price"]
        pl = _prior_low(ctx, d)
        if session_needs_minutes(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh, state=st):
            bars5 = minutes.get((ctx["tkr"], d), [])
            if not bars5:
                missing += 1
                blind.append(d)
                res = evaluate_session_daily(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh,
                                             prior_session_low=None, state=st)
                st = res["state"]
                continue
            res = evaluate_session_minute(bars5, gap_low=gl, gap_close=gc, gap_high=gh,
                                          prior_session_low=pl, state=st)
        else:
            res = evaluate_session_daily(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh,
                                         prior_session_low=pl, state=st)
        st = res["state"]
        for fire in res["fires"]:
            if fire["rung"] == rung:
                return ({"fire": fire, "fire_date": d, "shape": "same_pattern"},
                        missing, blind)
    return None, missing, blind


def _reentry_same_pattern_620(ctx, sessions, minutes):
    """Mirror of `_replay_same_pattern_620`: the next qualified proximate turn after the
    stop-out, fresh state, best-effort warm-up seed (the lane's own rule)."""
    st, missing, blind = new_state(), 0, []
    gc, adr = ctx["gc"], ctx["adr"]
    if adr is None or adr <= 0:
        return None, 0, []
    for d in sessions:
        b = ctx["bars"].get(d)
        if not b or b["high_price"] is None or b["low_price"] is None or b["close"] is None:
            missing += 1
            continue
        hi, lo = b["high_price"], b["low_price"]
        if not session_needs_minutes_620(hi, lo, gap_close=gc, adr_dollar=adr, state=st):
            continue
        bars5 = minutes.get((ctx["tkr"], d), [])
        if not bars5:
            missing += 1
            blind.append(d)
            continue
        warm = []
        for w in [x for x in ctx["ordered"] if x < d][-WARMUP_SESSIONS_620:]:
            warm.extend(minutes.get((ctx["tkr"], w), []))
        res = evaluate_session_620(warm, bars5, gap_close=gc, adr_dollar=adr, state=st)
        st = res["state"]
        if res["fires"]:
            return ({"fire": res["fires"][0], "fire_date": d, "shape": "same_pattern"},
                    missing, blind)
    return None, missing, blind


def _reentry_level(rung, shape, ctx, sessions, stop_day):
    """Mirror of the level-touch branch of `_record_reentries_for`: same_pattern for
    ep_high_break = a re-touch of the EP-day high; new_high_break (any rung) = a break
    above MAX(EP-day high, every session high through the latest stop-out)."""
    level = ctx["gh"]
    if shape == "new_high_break":
        ref_days = _trading_days(ctx["ep"] + timedelta(days=1), stop_day)
        highs = [(ctx["bars"].get(d) or {}).get("high_price") for d in ref_days]
        level = max([ctx["gh"]] + [h for h in highs if h is not None])
    seed = ctx["bars"].get(stop_day) or {}
    lb = replay_level_break(sessions, ctx["bars"], level, seed_prior_low=seed.get("low_price"))
    if lb["abstained"] or lb["fire_date"] is None:
        return None, lb["missing"], []
    fire = {"rung": rung, "entry": level, "stop": lb["prior_low"], "fire_minute": None}
    return ({"fire": fire, "fire_date": lb["fire_date"], "shape": shape}, lb["missing"], [])


def _search_reentry(rung, shape_policy, ctx, sessions, stop_day, minutes):
    shapes = ("same_pattern", "new_high_break") if shape_policy == "either" else (shape_policy,)
    hits, missing_tot, blind_tot = [], 0, []
    for sh in shapes:
        if sh == "same_pattern" and rung in (RUNG_EP_LOW, RUNG_EP_CLOSE):
            hit, m, bl = _reentry_same_pattern_reclaim(rung, ctx, sessions, minutes)
        elif sh == "same_pattern" and rung == RUNG_620_PROX:
            hit, m, bl = _reentry_same_pattern_620(ctx, sessions, minutes)
        else:
            hit, m, bl = _reentry_level(rung, sh, ctx, sessions, stop_day)
        missing_tot += m
        blind_tot = sorted(set(blind_tot) | set(bl))
        if hit:
            hits.append(hit)
    if not hits:
        return None, missing_tot, blind_tot, False
    order = {"same_pattern": 0, "new_high_break": 1}
    hits.sort(key=lambda h: (h["fire_date"], order[h["shape"]]))
    tie = len(hits) == 2 and hits[0]["fire_date"] == hits[1]["fire_date"]
    return hits[0], missing_tot, blind_tot, tie


# ── the chain ──────────────────────────────────────────────────────────────────────────


def run_chain(rung, ctx, first, frac, shape_policy, arm, minutes):
    """Unlimited-attempt chain; capped columns are prefixes. Returns
    (attempt rows, chain end, window/blind counts)."""
    adr = ctx["adr"]
    attempts = []
    entry, fire_date = first["entry"], first["fire_date"]
    fm, derived = _locate_first_fire(first, ctx, minutes)
    shape_fired = "first"
    end, ties, blind, missing = None, 0, 0, 0
    blind_days = set()
    while True:
        idx = len(attempts) + 1
        row = {"attempt": idx, "shape": shape_fired, "fire_date": fire_date, "fire_minute": fm,
               "resolution": "minute_5" if fm is not None else "daily",
               "derived_touch": derived, "entry": entry, "stop_px": None, "stop_w": None,
               "status": None, "outcome": None, "r": None, "mfe_r": None, "mae_r": None,
               "reached_4r": None, "mature": sp._mature(fire_date), "day0_pess_stop": False,
               "win_len": None, "win_full": None, "win_blind": None, "win_missing": None}
        if adr is None or adr <= 0:
            row["status"] = "abstain_no_stop_basis"
            attempts.append(row)
            end = "abstain"
            break
        stop = entry - frac * adr
        row["stop_px"] = stop
        row["stop_w"] = (entry - stop) / entry * 100.0
        if stop >= entry:
            row["status"] = "killed_entry_le_stop"
            attempts.append(row)
            end = "abstain"
            break
        res = _settle(ctx, minutes, entry, stop, fire_date, fm)
        row["status"] = res["status"]
        if res["status"] != "settled":
            row["outcome"] = res.get("reason")
            attempts.append(row)
            end = "abstain"
            break
        if arm == "none":
            row["outcome"], row["r"] = res["outcome"], res["realized_r"]
        else:
            row["outcome"], row["r"] = res["outcome_trail"], res["realized_r_trail"]
        row["mfe_r"], row["mae_r"], row["reached_4r"] = res["mfe_r"], res["mae_r"], res["reached_4r"]
        fb = ctx["bars"].get(fire_date) or {}
        row["day0_pess_stop"] = (fm is None and fb.get("low_price") is not None
                                 and fb["low_price"] <= stop)
        attempts.append(row)
        if row["outcome"] != "stop":
            end = "exit"
            break
        # stop-out → the re-entry window opens the session AFTER the stop day
        sidx = res["stop_session_idx"]
        stop_day = fire_date if sidx == 0 else res["_sessions"][sidx - 1]
        row["stop_day"] = stop_day
        window = _trading_days(stop_day + timedelta(days=1), HORIZON)[:REENTRY_WATCH_SESSIONS]
        window_full = len(window) == REENTRY_WATCH_SESSIONS
        hit, m, bl, tie = _search_reentry(rung, shape_policy, ctx, window, stop_day, minutes)
        missing += m
        blind += len(bl)
        blind_days.update(bl)
        ties += int(tie)
        row["win_len"], row["win_full"] = len(window), window_full
        row["win_blind"], row["win_missing"] = len(bl), m
        if hit is None:
            end = "no_reentry" if window_full else "censored_window"
            break
        fire = hit["fire"]
        entry, fire_date, shape_fired = float(fire["entry"]), hit["fire_date"], hit["shape"]
        fm = fire.get("fire_minute")
        derived = False
        if fm is None:
            fm, derived = _locate_level_touch(entry, fire_date, ctx, minutes)
    return attempts, end, {"ties": ties, "blind": blind, "missing": missing,
                           "blind_days": blind_days}


def _cap_view(attempts, end, cap):
    """The chain as seen under an attempts cap: prefix + end + readability."""
    rows = attempts if cap == 0 else attempts[:cap]
    if cap and len(attempts) > cap:
        cend = "capped"
    else:
        cend = end
    readable = (all(r["status"] == "settled" and r["mature"] for r in rows)
                and cend in ("exit", "no_reentry", "capped"))
    return rows, cend, readable


# ── phase: run ─────────────────────────────────────────────────────────────────────────


def phase_run():
    alerts, daily = bf.load_alerts(), bf.load_daily()
    minutes, mincov = bf.load_minutes(), bf.load_mincov()
    minutes.update(sp.load_extra_minutes())
    camps = [bf.walk_campaign(a, daily, minutes, mincov) for a in alerts]

    # ── gate 1: 602/602 first-attempt reproduction ──
    rec = bf.read_tsv("_562bf_triggers.tsv")
    rec_by_key = {(r["ticker"], r["ep_date"], r["rung"], r["fire_date"]):
                  (float(r["entry"]), float(r["stop"])) for r in rec}
    got = [(c, f) for c in camps for f in c["fires"]]
    mism = 0
    for c, f in got:
        k = (c["ticker"], c["ep_date"].isoformat(), f["rung"], f["fire_date"].isoformat())
        r = rec_by_key.get(k)
        if r is None or abs(r[0] - f["entry"]) > 1e-6 or abs(r[1] - f["stop"]) > 1e-6:
            mism += 1
    print(f"gate 1 — walk reproduction: {len(got)} fires (recorded {len(rec)}), mismatches {mism}")
    assert len(got) == len(rec) and mism == 0, "walk does not reproduce the record — STOP"

    rows_out, chains_out = [], []
    blind_pairs = set()
    for c in camps:
        if c["enroll_status"] != "ok" or not c["fires"]:
            continue
        ctx = _ctx(c, daily)
        for f in c["fires"]:
            rung = f["rung"]
            for frac in ADR_LADDER:
                for shape in SHAPES:
                    for arm in ARMS:
                        attempts, end, meta = run_chain(rung, ctx, f, frac, shape, arm, minutes)
                        for d in meta["blind_days"]:
                            blind_pairs.add((ctx["tkr"], d))
                        base = {"ticker": ctx["tkr"], "ep_date": ctx["ep"].isoformat(),
                                "mon": ctx["ep"].isoformat()[:7], "rung": rung,
                                "stop": kname(frac), "shape_policy": shape, "arm": arm}
                        chains_out.append({**base, "n_attempts": len(attempts), "end": end,
                                           "ties": meta["ties"], "blind": meta["blind"],
                                           "missing": meta["missing"],
                                           "last_exit": attempts[-1].get("stop_day") or attempts[-1]["fire_date"]})
                        for a in attempts:
                            rows_out.append({**base, **a})

    cols = ["ticker", "ep_date", "mon", "rung", "stop", "shape_policy", "arm", "attempt",
            "shape", "fire_date", "fire_minute", "resolution", "derived_touch", "entry",
            "stop_px", "stop_w", "status", "outcome", "r", "mfe_r", "mae_r", "reached_4r",
            "mature", "day0_pess_stop", "stop_day", "win_len", "win_full", "win_blind",
            "win_missing"]
    with open(HERE / "_545rt_rows.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows_out:
            fh.write("|".join("" if r.get(k) is None else str(r.get(k)) for k in cols) + "\n")
    ccols = ["ticker", "ep_date", "mon", "rung", "stop", "shape_policy", "arm", "n_attempts",
             "end", "ties", "blind", "missing", "last_exit"]
    with open(HERE / "_545rt_chains.tsv", "w") as fh:
        fh.write("|".join(ccols) + "\n")
        for r in chains_out:
            fh.write("|".join("" if r.get(k) is None else str(r.get(k)) for k in ccols) + "\n")
    print(f"{len(chains_out)} chains, {len(rows_out)} attempt rows written")
    cov = bf.load_mincov()
    with open(HERE / "_545rt_blind_pairs.tsv", "w") as fh:
        fh.write("ticker|d|in_prod\n")
        for t, d in sorted(blind_pairs):
            fh.write(f"{t}|{d.isoformat()}|{(t, d) in cov}\n")
    print(f"blind (ticker, day) pairs across every chain: {len(blind_pairs)}; "
          f"of which mi_intraday_bars HOLDS (uncaptured, pullable): "
          f"{sum(1 for p in blind_pairs if p in cov)}")

    # ── gate 2: the attempts=1 leg must equal the stop grid's ADR rows, 0 drift ──
    grid = bf.read_tsv("_562grid_rows.tsv")
    gkey = {}
    for g in grid:
        if g["variant"] in {kname(f) for f in ADR_LADDER}:
            gkey[(g["ticker"], g["ep_date"], g["rung"], g["fire_date"], g["variant"])] = g
    drift = checked = 0
    for r in rows_out:
        if r["attempt"] != 1 or r["shape_policy"] != PRIMARY_SHAPE:
            continue
        g = gkey.get((r["ticker"], r["ep_date"], r["rung"], r["fire_date"].isoformat(), r["stop"]))
        checked += 1
        if g is None:
            drift += 1
            continue
        want = bf._f(g["realized_r"]) if r["arm"] == "none" else bf._f(g["realized_r_trail"])
        if g["status"] != r["status"] or (want is not None and abs(want - r["r"]) > 1e-6) \
                or (want is None) != (r["r"] is None):
            drift += 1
            print(f"  ⚠ drift {r['ticker']} {r['fire_date']} {r['rung']} {r['stop']} {r['arm']}: "
                  f"grid {g['status']}/{want} loop {r['status']}/{r['r']}")
    print(f"gate 2 — attempts=1 vs stop grid: {checked} rows checked, drift {drift}")
    assert drift == 0, "the loop's first leg does not reproduce the grid — STOP"


# ── phase: report ──────────────────────────────────────────────────────────────────────


def _load():
    rows = bf.read_tsv("_545rt_rows.tsv")
    for r in rows:
        r["attempt"] = int(r["attempt"])
        r["r"] = bf._f(r["r"])
        r["mae_r"] = bf._f(r["mae_r"])
        r["mfe_r"] = bf._f(r["mfe_r"])
        r["stop_w"] = bf._f(r["stop_w"])
        r["mature"] = r["mature"] == "True"
        r["day0_pess_stop"] = r["day0_pess_stop"] == "True"
        r["win_blind"] = int(r["win_blind"]) if r.get("win_blind") else 0
        r["win_full"] = r.get("win_full") == "True"
    chains = bf.read_tsv("_545rt_chains.tsv")
    by = defaultdict(list)
    for r in rows:
        by[(r["ticker"], r["ep_date"], r["rung"], r["stop"], r["shape_policy"], r["arm"])].append(r)
    for k in by:
        by[k].sort(key=lambda x: x["attempt"])
    cend = {(c["ticker"], c["ep_date"], c["rung"], c["stop"], c["shape_policy"], c["arm"]): c
            for c in chains}
    return by, cend


def _campaign_cell(attempts, end, cap):
    rows, cend, readable = _cap_view(attempts, end, cap)
    if not readable:
        return None
    rs = [r["r"] for r in rows]
    cum, worst = 0.0, 0.0
    for x in rs:
        cum += x
        worst = min(worst, cum)
    all_stops = all(r["outcome"] == "stop" for r in rows)
    spent = all_stops and (cend == "capped" or (cap == 0 and cend == "no_reentry")
                           or (cap and len(rows) == cap) or cend == "no_reentry")
    # windows SEARCHED under this cap: after every stopped attempt i with i < cap (or all, unlimited)
    searched = [r for i, r in enumerate(rows, start=1) if r["outcome"] == "stop"
                and (cap == 0 or i < cap)]
    capscaled = sum(x["r"] * min(1.0, (x["stop_w"] or 0) / 5.0) for x in rows)
    return {"total": sum(rs), "n_att": len(rows), "worst_cum": worst, "spent": spent,
            "blind_win": sum(r["win_blind"] for r in searched),
            "has_blind": any(r["win_blind"] > 0 for r in searched),
            "capscaled": capscaled,
            "all_stops": all_stops, "positioned": not all_stops,
            "mae_min": min((r["mae_r"] for r in rows if r["mae_r"] is not None), default=None),
            "pess0": sum(1 for r in rows if r["day0_pess_stop"]),
            "shapes": [r["shape"] for r in rows[1:]], "mon": rows[0]["mon"],
            "ge4": sum(rs) >= 4.0, "last": rows[-1]}


def _agg(cells):
    if not cells:
        return None
    tot = [c["total"] for c in cells]
    return {"n": len(cells), "sum": sum(tot), "mean": statistics.mean(tot),
            "med": statistics.median(tot),
            "att": sum(c["n_att"] for c in cells),
            "att_mean": statistics.mean(c["n_att"] for c in cells),
            "retry_names": sum(1 for c in cells if c["n_att"] > 1),
            "spent": sum(1 for c in cells if c["spent"]),
            "ge4": sum(1 for c in cells if c["ge4"]),
            "worst": min(c["worst_cum"] for c in cells),
            "worst_total": min(tot),
            "n_le2": sum(1 for c in cells if c["worst_cum"] <= -2.0 + 1e-9),
            "n_le3": sum(1 for c in cells if c["worst_cum"] <= -3.0 + 1e-9),
            "win": sum(1 for t in tot if t > 0) / len(tot) * 100,
            "pess0": sum(c["pess0"] for c in cells),
            "capscaled": sum(c["capscaled"] for c in cells),
            "blind_names": sum(1 for c in cells if c["has_blind"]),
            "blind_win": sum(c["blind_win"] for c in cells),
            "top2": sorted((c["total"] for c in cells), reverse=True)[:2],
            "mae": min((c["mae_min"] for c in cells if c["mae_min"] is not None), default=None)}


def _drop_best(cells):
    if len(cells) < 2:
        return None
    best = max(cells, key=lambda c: c["total"])
    return _agg([c for c in cells if c is not best]), best


def _fmt(a):
    if a is None:
        return "n=0"
    return (f"n={a['n']:<3d} sum={a['sum']:+7.1f}R mean/name={a['mean']:+.2f} "
            f"att={a['att']:<4d} retried={a['retry_names']:<3d} spent-all={a['spent']:<3d} "
            f">=4R={a['ge4']:<2d} win={a['win']:3.0f}% worst-name={a['worst']:+.2f}R "
            f"(<=-2R:{a['n_le2']} <=-3R:{a['n_le3']}) day0-pess={a['pess0']} "
            f"cap-scaled=${a['capscaled']:+.1f}R-eq top2={'/'.join(format(t, '+.1f') for t in a['top2'])} "
            f"blind-names={a['blind_names']}({a['blind_win']}s)")


def phase_report():
    by, cend = _load()
    for rung in RUNGS:
        keys = [k for k in by if k[2] == rung]
        camp_keys = sorted({(k[0], k[1]) for k in keys})
        print(f"\n{'=' * 110}\n== {rung} — {len(camp_keys)} campaigns with a first fire ==\n{'=' * 110}")

        # per-campaign cell results
        cell = {}   # (shape, arm, stop, cap) -> {camp: result}
        for shape in SHAPES:
            for arm in ARMS:
                for frac in ADR_LADDER:
                    for cap in CAPS:
                        d = {}
                        for ck in camp_keys:
                            k = (ck[0], ck[1], rung, kname(frac), shape, arm)
                            if k not in by:
                                continue
                            res = _campaign_cell(by[k], cend[k]["end"], cap)
                            if res is not None:
                                d[ck] = res
                        cell[(shape, arm, kname(frac), cap)] = d

        # readability census under the primary policy
        print("\n-- readability (primary policy 'either'): readable campaigns per cell, pooled / ex-May --")
        for arm in ARMS:
            line = []
            for frac in ADR_LADDER:
                for cap in CAPS:
                    d = cell[(PRIMARY_SHAPE, arm, kname(frac), cap)]
                    xm = sum(1 for v in d.values() if v["mon"] != "2026-05")
                    line.append(f"{kname(frac)[-3:]}x{capname(cap):3s} {len(d):3d}/{xm:3d}")
            print(f"  {arm:5s}: " + "  ".join(line))
        common = None
        for arm in ARMS:
            for frac in ADR_LADDER:
                for cap in CAPS:
                    s = set(cell[(PRIMARY_SHAPE, arm, kname(frac), cap)])
                    common = s if common is None else (common & s)
        common = common or set()
        common_xm = {c for c in common if c[1][:7] != "2026-05"}
        print(f"  COMMON readable set (every stop x attempts x arm, primary policy): "
              f"{len(common)} campaigns pooled, {len(common_xm)} ex-May; by month "
              + ", ".join(f"{m[-2:]}:{sum(1 for c in common if c[1][:7] == m)}" for m in MONTHS))
        # what censors the rest, ex-May, at the most demanding cell
        ends = Counter()
        for ck in camp_keys:
            if ck in common or ck[1][:7] == "2026-05":
                continue
            k = (ck[0], ck[1], rung, kname(0.25), PRIMARY_SHAPE, "none")
            if k in by:
                rows, e, ok = _cap_view(by[k], cend[k]["end"], 0)
                why = e if e in ("censored_window", "abstain") else (
                    "immature_attempt" if not all(r["mature"] for r in rows) else
                    "unsettled" if not all(r["status"] == "settled" for r in rows) else e)
                ends[why] += 1
        print(f"  ex-May campaigns NOT in the common set, why (at 0.25xADR unlimited M-none): {dict(ends)}")

        for shape in SHAPES:
            tag = "PRIMARY" if shape == PRIMARY_SHAPE else "sensitivity"
            for arm in ARMS:
                print(f"\n-- {rung} · re-entry policy {shape} ({tag}) · exit M-{arm} · "
                      f"COMMON set n={len(common)} pooled / {len(common_xm)} ex-May --")
                base = cell[(shape, arm, kname(0.75), 1)]
                for frac in ADR_LADDER:
                    for cap in CAPS:
                        d = cell[(shape, arm, kname(frac), cap)]
                        pooled = [d[c] for c in common if c in d]
                        xm = [d[c] for c in common_xm if c in d]
                        a_p, a_x = _agg(pooled), _agg(xm)
                        print(f"  {kname(frac)} x {capname(cap):3s}  own-readable n={len(d)}")
                        print(f"     pooled : {_fmt(a_p)}")
                        print(f"     ex-May : {_fmt(a_x)}")
                        db = _drop_best(xm)
                        if db and db[0]:
                            print(f"     ex-May drop-best {db[1]['last']['ticker']} "
                                  f"{db[1]['mon']} ({db[1]['total']:+.1f}R): sum={db[0]['sum']:+.1f}R "
                                  f"mean/name={db[0]['mean']:+.2f} n={db[0]['n']}")
                        both = [c for c in d if c in base]
                        both_x = [c for c in both if c[1][:7] != "2026-05"]
                        if cap != 1 or frac != 0.75:
                            print(f"     PAIRWISE vs 0.75x1 (readable under both): pooled n={len(both)} "
                                  f"cell {sum(d[c]['total'] for c in both):+.1f}R vs base "
                                  f"{sum(base[c]['total'] for c in both):+.1f}R · ex-May n={len(both_x)} "
                                  f"cell {sum(d[c]['total'] for c in both_x):+.1f}R vs base "
                                  f"{sum(base[c]['total'] for c in both_x):+.1f}R · worst-name "
                                  f"{min((d[c]['worst_cum'] for c in both_x), default=0):+.1f}R")
                        dbp = _drop_best(pooled)
                        if dbp and dbp[0]:
                            print(f"     pooled drop-best {dbp[1]['last']['ticker']} "
                                  f"{dbp[1]['mon']} ({dbp[1]['total']:+.1f}R): sum={dbp[0]['sum']:+.1f}R "
                                  f"mean/name={dbp[0]['mean']:+.2f}")
                        mline = []
                        for mon in MONTHS:
                            ms = _agg([d[c] for c in common if c in d and c[1][:7] == mon])
                            mline.append(f"{mon[-2:]}: " + ("—" if ms is None else
                                                           f"{ms['sum']:+.1f}R/n{ms['n']}"))
                        print(f"     monthly sums: " + "  ".join(mline))

        # the retries themselves (primary, 0.75 and 0.25, both arms): what fired, what it did
        print(f"\n-- {rung} · the re-entry attempts themselves (primary policy, common set, unlimited) --")
        for arm in ARMS:
            for frac in ADR_LADDER:
                d = cell[(PRIMARY_SHAPE, arm, kname(frac), 0)]
                rows2 = []
                for c in common:
                    if c not in d:
                        continue
                    k = (c[0], c[1], rung, kname(frac), PRIMARY_SHAPE, arm)
                    rows2.extend(r for r in by[k] if r["attempt"] >= 2)
                if not rows2:
                    print(f"  M-{arm} {kname(frac)}: no re-entries fired on the common set")
                    continue
                sh = Counter(r["shape"] for r in rows2)
                res = Counter(r["resolution"] for r in rows2)
                rs = [r["r"] for r in rows2]
                stops = sum(1 for r in rows2 if r["outcome"] == "stop")
                ge4 = sum(1 for r in rs if r >= 4)
                print(f"  M-{arm} {kname(frac)}: {len(rows2)} re-entry attempts on "
                      f"{len({(r['ticker'], r['ep_date']) for r in rows2})} names; shapes {dict(sh)}; "
                      f"resolution {dict(res)}; stopped {stops}; sum {sum(rs):+.1f}R; "
                      f"mean {statistics.mean(rs):+.2f}; >=4R {ge4}; "
                      f"day0-pess stops {sum(1 for r in rows2 if r['day0_pess_stop'])}; "
                      f"max attempt idx {max(r['attempt'] for r in rows2)}")
                win = sorted((r for r in rows2 if r["r"] >= 2), key=lambda r: -r["r"])
                for r in win[:8]:
                    print(f"       {r['ticker']:6s} {r['ep_date']} att{r['attempt']} {r['shape']:15s} "
                          f"{r['fire_date']} {r['resolution']:8s} stop {r['stop_w']:.1f}% "
                          f"-> {r['r']:+.2f}R (mfe {r['mfe_r']:+.1f})")

        # ≥4R campaigns and the worst names, primary, common set, 0.75 x 1 vs the tight cells
        print(f"\n-- {rung} · per-name ledger, primary policy, common set: campaigns netting >=4R "
              f"and names at the worst drawdown --")
        for arm in ARMS:
            for frac, cap in ((0.75, 1), (0.25, 3), (0.50, 3), (0.25, 0)):
                d = cell[(PRIMARY_SHAPE, arm, kname(frac), cap)]
                ok = [(c, d[c]) for c in common if c in d]
                ge4 = sorted(((c, v) for c, v in ok if v["ge4"]), key=lambda x: -x[1]["total"])
                worst = sorted(ok, key=lambda x: x[1]["worst_cum"])[:5]
                print(f"  M-{arm} {kname(frac)} x {capname(cap)}: >=4R names: "
                      + (", ".join(f"{c[0]} {c[1][:7]} {v['total']:+.1f}R/{v['n_att']}att"
                                   for c, v in ge4) or "none"))
                print(f"       worst names: "
                      + ", ".join(f"{c[0]} {c[1][:7]} cum {v['worst_cum']:+.1f}R total "
                                  f"{v['total']:+.1f}R/{v['n_att']}att" for c, v in worst))

    # compact family summary — every rung, primary policy, both arms, common set
    print(f"\n{'=' * 110}\n== FAMILY SUMMARY — primary policy, common readable set per rung, EX-MAY "
          f"(pooled in brackets) · total R per name-sum / worst-name / drop-best sum / cap-scaled ==")
    for rung in RUNGS:
        keys = [k for k in by if k[2] == rung]
        camp_keys = sorted({(k[0], k[1]) for k in keys})
        cellr = {}
        for arm in ARMS:
            for frac in ADR_LADDER:
                for cap in CAPS:
                    d = {}
                    for ck in camp_keys:
                        k = (ck[0], ck[1], rung, kname(frac), PRIMARY_SHAPE, arm)
                        if k in by:
                            res = _campaign_cell(by[k], cend[k]["end"], cap)
                            if res is not None:
                                d[ck] = res
                    cellr[(arm, kname(frac), cap)] = d
        common = None
        for dd in cellr.values():
            common = set(dd) if common is None else (common & set(dd))
        common = common or set()
        cx = {c for c in common if c[1][:7] != "2026-05"}
        print(f"\n  {rung}: common set n={len(common)} pooled / {len(cx)} ex-May")
        for arm in ARMS:
            print(f"   M-{arm:5s} {'stop':8s}" + "".join(f"{'x' + capname(c):>34s}" for c in CAPS))
            for frac in ADR_LADDER:
                line = f"   {'':7s} {kname(frac):8s}"
                for cap in CAPS:
                    d = cellr[(arm, kname(frac), cap)]
                    ax = _agg([d[c] for c in cx if c in d])
                    ap = _agg([d[c] for c in common if c in d])
                    db = _drop_best([d[c] for c in cx if c in d])
                    if ax is None:
                        line += f"{'n=0':>34s}"
                        continue
                    dbs = f"{db[0]['sum']:+.0f}" if db and db[0] else "—"
                    line += (f"{ax['sum']:+6.1f}R[{ap['sum']:+5.0f}] w{ax['worst']:+.0f} "
                             f"db{dbs:>4s} ${ax['capscaled']:+5.1f}").rjust(34)
                print(line)

    # blind-session / tie census
    print(f"\n{'=' * 110}\n== census: blind sessions (fresh walk needed minutes, none stored), "
          f"same-day shape ties, chain lengths ==")
    for rung in RUNGS:
        cs = [c for c in cend.values() if c["rung"] == rung and c["shape_policy"] == PRIMARY_SHAPE]
        blind = sum(int(c["blind"]) for c in cs)
        ties = sum(int(c["ties"]) for c in cs)
        na = Counter(int(c["n_attempts"]) for c in cs)
        print(f"  {rung:20s}: chains {len(cs)}, blind sessions {blind}, same-day ties {ties}, "
              f"attempts-fired distribution {dict(sorted(na.items()))}")


# ── phase: hand-walk ───────────────────────────────────────────────────────────────────


def phase_handwalk():
    """Raw-bar traces for chained campaigns: one same_pattern re-entry, one
    new_high_break — the pre-registration's validation substitute for the unpulled lane
    re-entry rows."""
    by, cend = _load()
    alerts, daily = bf.load_alerts(), bf.load_daily()
    minutes, mincov = bf.load_minutes(), bf.load_mincov()
    minutes.update(sp.load_extra_minutes())
    want = []
    if len(sys.argv) >= 5:            # handwalk TICKER EP_DATE adr_025  -> that exact chain
        k = (sys.argv[2], sys.argv[3], RUNG_EP_LOW, sys.argv[4], "either", "trail")
        want.append((k, by[k]))
    else:
        for shape in ("same_pattern", "new_high_break"):
            cands = [(k, v) for k, v in by.items()
                     if k[2] == RUNG_EP_LOW and k[3] == "adr_075" and k[4] == "either" and k[5] == "trail"
                     and len(v) >= 2 and v[1]["shape"] == shape and v[1]["status"] == "settled"
                     and v[1]["mature"]]
            # prefer a same-shape chain whose re-entry actually held, else the first
            cands.sort(key=lambda kv: -(kv[1][1]["r"] or -9))
            if cands:
                want.append(cands[0])
    for k, rows in want:
        tkr, ep = k[0], date.fromisoformat(k[1])
        bars = daily[tkr]
        epb = bars[ep]
        ordered = sorted(bars)
        adr, _ = bf.compute_ep_adr_dollar([bars[d] for d in ordered], ep, epb["close"])
        frac = int(k[3][-3:]) / 100.0
        print(f"\n{'#' * 100}\n# HAND-WALK {tkr} EP {ep} · rung ep_low_reclaim · stop entry-{frac:.2f}xADR · policy either · M-trail")
        print(f"# EP day: low {epb['low_price']} close {epb['close']} high {epb['high_price']} · "
              f"EP-anchored ADR$ {adr:.4f} → {frac:.2f}xADR = {frac * adr:.4f}")
        for r in rows:
            print(f"\n  attempt {r['attempt']} [{r['shape']}] fire {r['fire_date']} "
                  f"minute {r['fire_minute'] or 'daily'} ({r['resolution']}) entry {float(r['entry']):.4f} "
                  f"stop {float(r['stop_px']):.4f} ({r['stop_w']:.2f}%) → {r['outcome']} {r['r']:+.2f}R"
                  + (f" · stop day {r['stop_day']}" if r.get("stop_day") else ""))
            fd = date.fromisoformat(r["fire_date"])
            fb = bars.get(fd)
            if fb:
                print(f"    fire-day daily bar {fd}: o {fb['open_price']} h {fb['high_price']} "
                      f"l {fb['low_price']} c {fb['close']}")
            if r["attempt"] >= 2:
                # the re-entry window from the prior stop day: show the daily bars up to the fire
                prev = rows[r["attempt"] - 2]
                sd = date.fromisoformat(prev["stop_day"])
                win = _trading_days(sd + timedelta(days=1), fd)
                print(f"    re-entry window opened {win[0] if win else '—'} (session after the stop day {sd}); "
                      f"daily bars through the fire day:")
                for d in win:
                    b = bars.get(d)
                    if not b:
                        print(f"      {d}: MISSING")
                        continue
                    flag = ""
                    if b["low_price"] < epb["low_price"]:
                        flag += " <undercut EP low>"
                    if b["high_price"] >= epb["high_price"]:
                        flag += " <at/above EP high>"
                    print(f"      {d}: o {b['open_price']} h {b['high_price']} l {b['low_price']} "
                          f"c {b['close']}{flag}")
            b5 = minutes.get((tkr, fd), [])
            if b5 and r["fire_minute"]:
                fm = int(float(r["fire_minute"]))
                i = next((j for j, b in enumerate(b5) if b["m"] == fm), None)
                if i is not None:
                    print(f"    5-min bars around the fire (ET minute-of-day; the lane's own 5-min buckets):")
                    what = ("close reclaims the EP low" if r["shape"] in ("first", "same_pattern")
                            else f"high touches the level {float(r['entry']):.4f}")
                    for b in b5[max(0, i - 4): i + 4]:
                        mark = f" <FIRE: {what}>" if b["m"] == fm else ""
                        print(f"      m={b['m']} ({b['m'] // 60:02d}:{b['m'] % 60:02d}) o {b['o']} h {b['h']} "
                              f"l {b['l']} c {b['c']}{mark}")
                    if r.get("stop_day") == r["fire_date"]:
                        sp_ = float(r["stop_px"])
                        print(f"    same-day stop: post-fire 5-min bars to the first low <= {sp_:.4f}:")
                        for b in b5[i + 1:]:
                            hit = b["l"] <= sp_
                            print(f"      m={b['m']} ({b['m'] // 60:02d}:{b['m'] % 60:02d}) h {b['h']} l {b['l']} "
                                  f"c {b['c']}{' <STOP>' if hit else ''}")
                            if hit:
                                break
            # the path after the fire to the exit
            sessions = _trading_days(fd + timedelta(days=1), HORIZON)
            stop_px = float(r["stop_px"])
            print(f"    post-fire daily path (stop {stop_px:.4f}):")
            shown = 0
            for d in sessions[:22]:
                if r["outcome"] == "trail_exit" and shown >= 6 and r["attempt"] >= 2:
                    print(f"      … (trail exit {r['r']:+.2f}R; full path in the daily capture)")
                    break
                b = bars.get(d)
                if not b:
                    print(f"      {d}: MISSING")
                    continue
                flag = " <low <= stop>" if b["low_price"] <= stop_px else ""
                print(f"      {d}: h {b['high_price']} l {b['low_price']} c {b['close']}{flag}")
                shown += 1
                if flag:
                    break


if __name__ == "__main__":
    {"run": phase_run, "report": phase_report, "handwalk": phase_handwalk}[sys.argv[1]]()
