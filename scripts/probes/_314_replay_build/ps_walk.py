#!/usr/bin/env python3
"""#314 replay — the walk and the bars (plan §Substitutions (c), §The primary walk, §Reads 1, §Bars, §Consequence). `replay_episode`
is called UNCHANGED (its module is pinned); the one-open-episode-per-company rule, the `ended_mid_walk` booking with its haircut,
the costs, the ADR P&L, the tail clause, the month-block bootstrap (`runner.block_bootstrap_ci`, 2,000 draws, seed 702), the
difference intervals, the verdicts and the independent re-derivation live here. Nothing here is tuned; every cut is ps_common's.

READINGS (continued; the main loop decides):
  R23 Rule (c) is applied in D0 order per population with the walk's outcomes known: a climax on company key K is rejected
      `episode_already_open` when K's earlier admitted episode has an outcome date > D0 or no outcome date; a `degraded` or
      `ended_mid_walk` episode releases the name at its LAST WALKED BAR (the date the position is booked), the plan naming no other
      release. The count the company key adds beyond a ticker key is printed.
  R24 The forward bars of a walk are D0+1..D0+7 of the SAME series, cut at the first missing session (-> `degraded` if still open),
      at the series' last bar before the era's last session (-> `ended_mid_walk`), or at the era-B owner's `delisted_utc` (R13).
      A `distribution_suspect` is a cut bar (open / prior close - 1 <= -0.25) among the walked forward bars.
  R25 `ended_mid_walk` classes on the last walked bar: collapse = RAW last close < $1 or the adjusted close <= -50% against the close 60
      sessions earlier (the data standard's C1); pinned = the last 10 closes within 1% (max / min - 1 <= 0.01); other. The haircut
      (1.25 x the last close) applies to collapse and to an `other` ending whose last bar is a one-day fall of 20% or more.
  R26 Costs: every covering leg's exit price x (1 + x) for x in {0.1%, 0.2%}; the flush leg (1/3 at entry - 1R) is a covering leg too.
      ADR20% = mean((high - low) / close) over the 20 sessions ending at D0 - 1 (rows[ci-20 : ci]); a window with fewer than 20 bars
      cannot occur (120 rows of history).
  R27 The difference interval draws entry-month blocks once from the union of both groups' months (as many blocks as months), takes
      both group means from the drawn episodes and their difference; a draw leaving a group empty is redrawn (counted); seed = 702
      mixed with the row's key through `rng_for(key, 702)`.
  R28 "Unknown-dominated" = the unknown group holds more than half of the population's SETTLED episodes (the plan's words).
  R29 The P2 small-tier beside pass is its own climax list and its own walk (population label `P2small`); its numbers are printed beside
      P2's and never pooled.
"""
from __future__ import annotations

import bisect
import math
import os
import sys
import zlib
from collections import Counter, defaultdict
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402

GuardStop = X.GuardStop


def shadow_module():
    from agents.market_intelligence import parabolic_short_shadow as psh
    return psh


# ═════════════════════════════════════════════════════════════════════════════════════════════
# one walk
# ═════════════════════════════════════════════════════════════════════════════════════════════
def forward_bars(dicts: list, ci_arr, j: int, cut_date: "str | None", era_last: str, cal: list) -> tuple:
    """(bars after the climax row j, stop reason) — R24. `ci_arr` = the ticker's session indices (aligned with `dicts`)."""
    out, reason = [], "complete"
    for k in range(j + 1, min(len(dicts), j + 1 + X.WALK_AFTER)):
        if ci_arr[k] != ci_arr[k - 1] + 1:
            reason = "hole"
            break
        d = dicts[k]["trade_date"].isoformat()
        if cut_date and d > cut_date:
            reason = "owner_delisted"
            break
        out.append(dicts[k])
    if reason == "complete" and len(out) < X.WALK_AFTER:
        last = dicts[-1]["trade_date"].isoformat()
        reason = "end_of_series" if last < era_last else "end_of_file"
    return out, reason


def adr20(rows: list, ci: int) -> "float | None":
    w = rows[max(0, ci - 20):ci]
    if len(w) < 20:
        return None
    return float(np.mean([(float(r["high_price"]) - float(r["low_price"])) / float(r["close"]) for r in w]))    # str->float


def legs_of(trigger: dict, outcome: dict) -> list:
    """[(weight, exit price)] of a settled episode: the flush leg (1/3 at entry - 1R) when taken, then the exit leg."""
    legs = []
    if outcome.get("flush_taken"):
        legs.append((1.0 / shadow_module().FLUSH_COVER_DENOM, float(outcome["flush_price"])))      # str->float
        legs.append((1.0 - 1.0 / shadow_module().FLUSH_COVER_DENOM, float(outcome["exit_price"])))
    else:
        legs.append((1.0, float(outcome["exit_price"])))
    return legs


def r_of_legs(entry: float, risk: float, legs: list, slip: float = 0.0) -> float:
    return sum(w * (entry - px * (1.0 + slip)) for w, px in legs) / risk


def pnl_adr_of(entry: float, legs: list, adr: "float | None", slip: float = 0.0) -> "float | None":
    if adr is None or adr <= 0:
        return None
    return sum(w * (entry - px * (1.0 + slip)) for w, px in legs) / entry / adr


def ending_class(dicts: list, raw_last: float, j_last: int) -> tuple:
    """R25 -> (class, one_day_fall)."""
    closes = [float(d["close"]) for d in dicts[: j_last + 1]]            # str->float
    last = closes[-1]
    one_day = (last / closes[-2] - 1.0) if len(closes) >= 2 else 0.0
    ret60 = (last / closes[-1 - X.COLLAPSE_WINDOW] - 1.0) if len(closes) > X.COLLAPSE_WINDOW else None
    if raw_last < X.COLLAPSE_PRICE or (ret60 is not None and ret60 <= X.COLLAPSE_RET):
        return ("collapse", one_day)
    tail = closes[-X.PINNED_WINDOW:]
    if len(tail) >= X.PINNED_WINDOW and (max(tail) / min(tail) - 1.0) <= X.PINNED_SPREAD:
        return ("pinned", one_day)
    return ("other", one_day)


def walk_one(dicts: list, ci_arr, j: int, d0: str, cal: list, era_last: str, cut_date: "str | None", raw_close, earnings_after=frozenset()) -> dict:
    """One climax night walked under the 5-stop, the 3-stop and the 8-K beside (both stops). Returns the episode's record."""
    psh = shadow_module()
    hist = dicts[j - X.HISTORY + 1: j + 1]
    if hist[-1]["trade_date"].isoformat() != d0 or len(hist) != X.HISTORY:
        raise GuardStop(f"walk: rows[-1].trade_date != D0 ({hist[-1]['trade_date']} vs {d0}) or {len(hist)} rows")
    fwd, stop_reason = forward_bars(dicts, ci_arr, j, cut_date, era_last, cal)
    rows = hist + fwd
    ci = X.HISTORY - 1
    geom = psh.arm_geometry(rows, ci)
    stop_price = geom["stop_price"]
    armed_on = date.fromisoformat(d0)
    res = {}
    for label, ts, earn in (("r5", X.TIME_STOP_PRIMARY, frozenset()), ("r3", X.TIME_STOP_READ1, frozenset()),
                            ("e5", X.TIME_STOP_PRIMARY, earnings_after), ("e3", X.TIME_STOP_READ1, earnings_after)):
        res[label] = psh.replay_episode(rows, ci, stop_price=stop_price, armed_on=armed_on, earnings_after=earn, time_stop=ts)
    out = {"stop_price": stop_price, "atr_14": geom["atr_14"], "climax_high": geom["climax_high"], "climax_low": geom["climax_low"],
           "adr20": adr20(rows, ci), "forward_bars": len(fwd), "stop_reason": stop_reason,
           "suspect_gap_date": "", "suspect_gap": None, "jump_in_walk": 0,
           "last_walked_date": (fwd[-1]["trade_date"] if fwd else hist[-1]["trade_date"]).isoformat()}
    for k, b in enumerate(fwd):
        prev = rows[ci + k]
        gap = float(b["open_price"]) / float(prev["close"]) - 1.0        # str->float
        if gap <= X.GAP_CUT and not out["suspect_gap_date"]:
            out["suspect_gap_date"], out["suspect_gap"] = b["trade_date"].isoformat(), gap
    out["raw_last"] = X.num(raw_close[j + len(fwd)]) if raw_close is not None else None
    last_idx = j + len(fwd)
    for label in ("r5", "r3", "e5", "e3"):
        out.update(book(label, res[label], rows, ci, stop_reason, dicts, last_idx, out["raw_last"], out["adr20"]))
    return out


def book(label: str, r: dict, rows: list, ci: int, stop_reason: str, dicts: list, last_idx: int, raw_last, adr) -> dict:
    """The state of one replay -> columns prefixed `label_`: status, reason, entry / exit, R, legs at the costs, the mid-walk marks."""
    psh = shadow_module()
    o = {f"{label}_status": "", f"{label}_reason": "", f"{label}_entry_date": "", f"{label}_entry_price": None, f"{label}_entry_kind": "",
         f"{label}_risk": None, f"{label}_exit_date": "", f"{label}_exit_price": None, f"{label}_sessions_held": None, f"{label}_flush_taken": 0,
         f"{label}_flush_price": None, f"{label}_r": None, f"{label}_exit_leg_r": None, f"{label}_mfe": None, f"{label}_mae": None,
         f"{label}_pnl_adr": None, f"{label}_r_slip1": None, f"{label}_r_slip2": None, f"{label}_pnl_adr_slip1": None, f"{label}_pnl_adr_slip2": None,
         f"{label}_last_close": None, f"{label}_r_last_close": None, f"{label}_r_haircut": None, f"{label}_ended_class": "", f"{label}_one_day_fall": None,
         f"{label}_pnl_adr_last_close": None, f"{label}_pnl_adr_haircut": None,
         f"{label}_entry_month": ""}
    trig = r.get("trigger")
    if trig:
        o.update({f"{label}_entry_date": trig["date"].isoformat(), f"{label}_entry_price": trig["entry_price"], f"{label}_entry_kind": trig["kind"],
                  f"{label}_risk": trig["risk_per_share"], f"{label}_entry_month": trig["date"].isoformat()[:7]})
    state, outc = r["state"], r.get("outcome")
    if state == "closed" and outc:
        st = outc["status"]
        if st == "settled":
            o[f"{label}_status"], o[f"{label}_reason"] = "settled", outc["reason"]
            legs = legs_of(trig, outc)
            entry, risk = float(trig["entry_price"]), float(trig["risk_per_share"])      # str->float
            o.update({f"{label}_exit_date": X.iso(outc["date"]), f"{label}_exit_price": outc["exit_price"], f"{label}_sessions_held": outc["sessions_held"],
                      f"{label}_flush_taken": int(bool(outc["flush_taken"])), f"{label}_flush_price": outc["flush_price"], f"{label}_r": outc["realized_r"],
                      f"{label}_exit_leg_r": outc["exit_leg_r"], f"{label}_mfe": outc["mfe_r"], f"{label}_mae": outc["mae_r"],
                      f"{label}_pnl_adr": pnl_adr_of(entry, legs, adr), f"{label}_r_slip1": r_of_legs(entry, risk, legs, X.SLIPPAGES[1]),
                      f"{label}_r_slip2": r_of_legs(entry, risk, legs, X.SLIPPAGES[2]), f"{label}_pnl_adr_slip1": pnl_adr_of(entry, legs, adr, X.SLIPPAGES[1]),
                      f"{label}_pnl_adr_slip2": pnl_adr_of(entry, legs, adr, X.SLIPPAGES[2])})
            check = r_of_legs(entry, risk, legs, 0.0)
            if abs(check - outc["realized_r"]) > 1e-9:
                raise GuardStop(f"booking: realized R {outc['realized_r']} != 1/3 + 2/3 x exit-leg R recomputed {check}")
        elif st == "closed_untriggered":
            o[f"{label}_status"], o[f"{label}_reason"], o[f"{label}_exit_date"] = outc["reason"], outc["reason"], X.iso(outc["date"])
        elif st == "voided":
            o[f"{label}_status"], o[f"{label}_reason"] = outc["reason"], outc["reason"]
        return o
    if state == "data_gap":
        raise GuardStop("walk: replay_episode met a bar lacking a price (the loader asserts finite bars)")
    # waiting / open with the forward bars exhausted
    if stop_reason == "hole":
        o[f"{label}_status"], o[f"{label}_reason"] = "degraded", "hole"
    elif stop_reason in ("end_of_series", "owner_delisted"):
        o[f"{label}_status"], o[f"{label}_reason"] = "ended_mid_walk", stop_reason
    elif stop_reason == "end_of_file":
        o[f"{label}_status"], o[f"{label}_reason"] = "open_at_end", "end_of_file"
    else:
        raise GuardStop(f"walk: an episode is still {state} after a complete D0+7 span (time stop {label})")
    if state == "open" and trig and o[f"{label}_status"] == "ended_mid_walk":
        last_close = float(rows[-1]["close"])                                     # str->float
        entry, risk = float(trig["entry_price"]), float(trig["risk_per_share"])
        op = r["open"]
        frac = 1.0 / psh.FLUSH_COVER_DENOM
        flush_px = entry - psh.FLUSH_R_MULT * risk
        legs = ([(frac, flush_px), (1.0 - frac, last_close)] if op["flush_taken"] else [(1.0, last_close)])
        cls, fall = ending_class(dicts, raw_last if raw_last is not None else last_close, last_idx)
        hair = X.HAIRCUT if (cls == "collapse" or (cls == "other" and fall <= X.ONE_DAY_FALL)) else 1.0
        legs_h = ([(frac, flush_px), (1.0 - frac, last_close * hair)] if op["flush_taken"] else [(1.0, last_close * hair)])
        o.update({f"{label}_last_close": last_close, f"{label}_r_last_close": r_of_legs(entry, risk, legs), f"{label}_r_haircut": r_of_legs(entry, risk, legs_h),
                  f"{label}_pnl_adr_last_close": pnl_adr_of(entry, legs, adr), f"{label}_pnl_adr_haircut": pnl_adr_of(entry, legs_h, adr),
                  f"{label}_ended_class": cls, f"{label}_one_day_fall": fall, f"{label}_flush_taken": int(bool(op["flush_taken"])),
                  f"{label}_sessions_held": op["sessions_held"], f"{label}_mfe": op["mfe_r"], f"{label}_mae": op["mae_r"]})
    elif o[f"{label}_status"] == "ended_mid_walk":
        o[f"{label}_ended_class"] = "armed_untriggered"
    return o


# ═════════════════════════════════════════════════════════════════════════════════════════════
# rule (c): one open episode per company, advance-before-decide, oldest climax first (R23)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def closes_on(ep: dict, label: str = "r5") -> "str | None":
    st = ep.get(f"{label}_status")
    if st == "settled" or st in ("invalidated", "expired_untriggered"):
        return ep.get(f"{label}_exit_date") or None
    if st == "void_bad_geometry":
        return ep.get(f"{label}_entry_date") or ep["d0"]
    if st in ("degraded", "ended_mid_walk", "open_at_end"):
        return ep.get("last_walked_date") or None
    return None


def apply_open_rule(episodes: list, key_field: str = "company_key", label: str = "r5", field: str = "decision") -> Counter:
    """Sets `field` = admitted | episode_already_open on each episode (sorted by (d0, ticker)); the open rule keyed by `key_field`,
    the close dates read from the `label` walk. -> the tally. Advance-before-decide: an earlier episode whose close date == D0 has
    closed by that night's bar. Asserts no key ever holds two open episodes on one night."""
    episodes.sort(key=lambda e: (e["d0"], e["ticker"]))
    open_until = {}
    tally = Counter()
    for ep in episodes:
        k = ep[key_field]
        d0 = ep["d0"]
        until = open_until.get(k)
        if until is not None and (until == "" or until > d0):
            ep[field] = "episode_already_open"
            tally["episode_already_open"] += 1
            continue
        ep[field] = "admitted"
        tally["admitted"] += 1
        c = closes_on(ep, label)
        open_until[k] = c if c is not None else ""
    return tally


def ticker_key_rejections(episodes: list) -> int:
    """The count a company key adds beyond a ticker key (printed)."""
    import copy
    eps = [dict(e) for e in episodes]
    t = apply_open_rule(eps, key_field="ticker")
    c = apply_open_rule([dict(e) for e in episodes], key_field="company_key")
    return int(c["episode_already_open"] - t["episode_already_open"])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# statistics (the bars)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def mean_ci(values, months, key: str) -> tuple:
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return (float("nan"), float("nan"), float("nan"))
    lo, hi = X.block_bootstrap_ci(v, list(months), draws=X.BOOT_DRAWS, seed=X.BOOT_SEED, key=key)
    return (float(v.mean()), lo, hi)


def diff_ci(v_a, m_a, v_b, m_b, key: str, draws: int = X.BOOT_DRAWS) -> tuple:
    """R27 -> (difference, lo, hi, redraws)."""
    v_a, v_b = np.asarray(v_a, float), np.asarray(v_b, float)
    m_a, m_b = np.asarray(m_a), np.asarray(m_b)
    if not len(v_a) or not len(v_b):
        return (float("nan"), float("nan"), float("nan"), 0)
    months = np.unique(np.concatenate([m_a, m_b]))
    m = len(months)
    ia = np.searchsorted(months, m_a)
    ib = np.searchsorted(months, m_b)
    sa, ca = np.bincount(ia, weights=v_a, minlength=m), np.bincount(ia, minlength=m).astype(float)
    sb, cb = np.bincount(ib, weights=v_b, minlength=m), np.bincount(ib, minlength=m).astype(float)
    rng = X.rng_for(key, X.BOOT_SEED)
    diffs, redraws, got = [], 0, 0
    while got < draws:
        idx = rng.integers(0, m, size=m)
        na, nb = ca[idx].sum(), cb[idx].sum()
        if na == 0 or nb == 0:
            redraws += 1
            continue
        diffs.append(sa[idx].sum() / na - sb[idx].sum() / nb)
        got += 1
    d = np.asarray(diffs)
    return (float(v_a.mean() - v_b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), redraws)


def tail_clause(settled: list, r_field: str = "r5_r", bar: float = X.TAIL_R) -> dict:
    """>= 3 settled trades at >= bar R, from >= 3 companies and >= 3 distinct entry months; fewer = FAIL (never vacuously true)."""
    hits = [e for e in settled if e.get(r_field) is not None and float(e[r_field]) >= bar]         # str->float
    comps = {e["company_key"] for e in hits}
    months = {e["r5_entry_month"] for e in hits}
    ok = len(hits) >= X.TAIL_TRADES and len(comps) >= X.TAIL_COMPANIES and len(months) >= X.TAIL_MONTHS
    return {"pass": ok, "trades": len(hits), "companies": len(comps), "months": len(months)}


def base_verdict(settled: list, key: str, r_field: str = "r5_r", pnl_field: str = "r5_pnl_adr") -> dict:
    n = len(settled)
    r = [float(e[r_field]) for e in settled]                                           # str->float
    months = [e["r5_entry_month"] for e in settled]
    mean, lo, hi = mean_ci(r, months, key)
    pnl = [float(e[pnl_field]) for e in settled if e.get(pnl_field) not in (None, "")]
    mean_pnl = float(np.mean(pnl)) if pnl else float("nan")
    tail = tail_clause(settled, r_field)
    if n >= X.N_FLOOR and lo > 0 and mean_pnl > 0 and tail["pass"]:
        v = "PASS"
    elif n >= X.N_FLOOR and hi < 0:
        v = "FAIL"
    elif n >= X.N_FLOOR and lo > 0:
        v = "CAN'T TELL (positive, no tail)" if not tail["pass"] else "CAN'T TELL (positive, ADR P&L not > 0)"
    else:
        v = "CAN'T TELL"
    return {"n": n, "mean_r": mean, "lo": lo, "hi": hi, "mean_pnl_adr": mean_pnl, "tail": tail, "verdict": v,
            "tail2": tail_clause(settled, r_field, X.TAIL_BESIDE_R)}


def read_verdict(diff: float, lo: float, hi: float, n_a: int, n_b: int, n_unknown: int, n_settled: int) -> str:
    if n_settled and n_unknown > 0.5 * n_settled:
        return "coverage-bound"
    if n_a < X.N_FLOOR or n_b < X.N_FLOOR:
        return "CAN'T TELL"
    if lo > 0:
        return "separates in HIS direction"
    if hi < 0:
        return "separates AGAINST him"
    return "CAN'T TELL"


def verdict_three_ways(settled: list, ended: list, key: str, a: "dict | None" = None) -> dict:
    """(a) settled only (pass the deciding verdict itself, so (a) IS the base verdict, same interval); (b) + ended_mid_walk at the last
    close; (c) + the haircut. The label when (b) or (c) differs from (a)."""
    a = a if a is not None else base_verdict(settled, key + ":a")
    b_rows = settled + [{**e, "r5_r": e["r5_r_last_close"], "r5_pnl_adr": e.get("r5_pnl_adr_last_close")} for e in ended
                        if e.get("r5_r_last_close") not in (None, "")]
    c_rows = settled + [{**e, "r5_r": e["r5_r_haircut"], "r5_pnl_adr": e.get("r5_pnl_adr_haircut")} for e in ended
                        if e.get("r5_r_haircut") not in (None, "")]
    b = base_verdict(b_rows, key + ":b") if len(b_rows) > len(settled) else a      # no delisted episode with an R: (b) IS (a)
    c = base_verdict(c_rows, key + ":c") if len(c_rows) > len(settled) else a
    n_delisted = len(b_rows) - len(settled)
    label = a["verdict"]
    if b["verdict"] != a["verdict"] or c["verdict"] != a["verdict"]:
        label = f"{a['verdict']}, depends on {n_delisted} delisted episodes"
    return {"a": a, "b": b, "c": c, "label": label, "n_delisted": n_delisted}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the result: the base verdict per population, the costs, the three ways, the beside rows, the reads, the grid (plan §Bars,
# §Consequence). Every number also goes into `numbers` for the independent re-derivation (ps_rederive.py) to match.
# ═════════════════════════════════════════════════════════════════════════════════════════════
POPS = ("P1", "P2", "P2small")
READ_POPS = ("P1", "P2")


def in_n(e: dict, label: str = "r5", decision: str = "decision") -> bool:
    return (e.get(decision) == "admitted" and e.get(f"{label}_status") == "settled" and str(e.get("void_adjustment_event")) != "1"
            and e.get("distribution_class") != "distribution")


def _bv_numbers(prefix: str, bv: dict, nums: dict) -> None:
    nums[f"{prefix}:n"] = bv["n"]
    for k in ("mean_r", "lo", "hi", "mean_pnl_adr"):
        nums[f"{prefix}:{k}"] = bv[k]
    for k in ("trades", "companies", "months"):
        nums[f"{prefix}:tail_{k}"] = bv["tail"][k]
    nums[f"{prefix}:verdict"] = bv["verdict"]


def _fmt(x) -> str:
    return "nan" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.4f}"


def _bv_line(say, label: str, bv: dict) -> None:
    t = bv["tail"]
    say(f"  {label}: n {bv['n']}, mean R {_fmt(bv['mean_r'])} [{_fmt(bv['lo'])}, {_fmt(bv['hi'])}], ADR P&L {_fmt(bv['mean_pnl_adr'])}, "
        f"tail >= 3R {t['trades']} trades / {t['companies']} companies / {t['months']} months ({'pass' if t['pass'] else 'fail'}), "
        f">= 2R beside {bv['tail2']['trades']} / {bv['tail2']['companies']} / {bv['tail2']['months']} -> {bv['verdict']}")


def two_group(eps: list, grp, key: str, r_field: str = "r5_r") -> dict:
    """A read's difference A - B (grp(e) -> 'A' | 'B' | None = unknown) with the shared-block interval (R27)."""
    A = [e for e in eps if grp(e) == "A"]
    B = [e for e in eps if grp(e) == "B"]
    U = [e for e in eps if grp(e) is None]
    if len(A) + len(B) + len(U) != len(eps):
        raise GuardStop(f"{key}: an episode in two groups of one read, or in none")
    d, lo, hi, red = diff_ci([float(e[r_field]) for e in A], [e["r5_entry_month"] for e in A],
                             [float(e[r_field]) for e in B], [e["r5_entry_month"] for e in B], key)
    v = read_verdict(d, lo, hi, len(A), len(B), len(U), len(eps))
    return {"n_a": len(A), "n_b": len(B), "n_unknown": len(U), "diff": d, "lo": lo, "hi": hi, "redraws": red, "verdict": v}


def paired(eps: list, other: str, key: str, base: str = "r5") -> dict:
    """Read 1: per episode settled under BOTH stops, other - base (R5); the month-block interval of the paired differences."""
    pr = [e for e in eps if e.get(f"{other}_status", "settled") == "settled" and e.get(f"{other}_r") is not None]
    dv = [float(e[f"{other}_r"]) - float(e[f"{base}_r"]) for e in pr]
    mean, lo, hi = mean_ci(dv, [e["r5_entry_month"] for e in pr], key)
    n = len(pr)
    v = "CAN'T TELL" if n < X.N_FLOOR else ("separates in HIS direction" if lo > 0 else "separates AGAINST him" if hi < 0 else "CAN'T TELL")
    return {"n_a": n, "n_b": n, "n_unknown": len(eps) - n, "diff": mean, "lo": lo, "hi": hi, "redraws": 0, "verdict": v}


def _read_numbers(prefix: str, r: dict, nums: dict) -> None:
    for k in ("n_a", "n_b", "n_unknown", "diff", "lo", "hi", "redraws", "verdict"):
        nums[f"{prefix}:{k}"] = r[k]


def _read_line(say, label: str, r: dict) -> None:
    say(f"  {label}: groups {r['n_a']} vs {r['n_b']} (unknown {r['n_unknown']}); difference {_fmt(r['diff'])} [{_fmt(r['lo'])}, {_fmt(r['hi'])}]"
        f"{' (redrawn ' + str(r['redraws']) + ')' if r['redraws'] else ''} -> {r['verdict']}")


def _num_or_none(x):
    return None if x in (None, "", "None") else float(x)


def read_groups() -> dict:
    """The five reads' registered groupings (A = the first named group of the difference)."""
    def pause(e):
        p = _num_or_none(e.get("pause_count"))
        return None if p is None else ("A" if p <= X.PAUSE_CUT else "B")

    def ratio(e):
        p = _num_or_none(e.get("pause_ratio"))
        return None if p is None else ("A" if p <= X.PAUSE_RATIO_CUT else "B")

    def news(e):
        return {"present": "A", "absent": "B"}.get(e.get("news3_group"))

    def swing(e):
        return {"no_swing": "A", "swing": "B"}.get(e.get("swing_group"))

    def swing_any(e):
        return {"no_swing": "A", "swing": "B"}.get(e.get("swing_group_any"))

    def dil(e):
        return {"ge20": "A", "lt20": "B"}.get(e.get("dilution_bucket"))

    def dil_itm(e):
        p = _num_or_none(e.get("dilution_ratio_itm"))
        if e.get("dilution_bucket") not in ("ge20", "lt20") or p is None:
            return None
        return "A" if p >= X.DILUTION_CUT else "B"
    return {"read2": pause, "read2_ratio": ratio, "read3": news, "read4": swing, "read4_any": swing_any, "read5": dil, "read5_itm": dil_itm}


GRID = {
    ("PASS", "PASS"): "proposal: a P2 shadow lane with its own borrow check (the $250M floor is his signed rule: CHANGE_PROCESS); P1 = the candidate for the next rung (paper is his call)",
    ("PASS", "CAN'T TELL"): "P1 the candidate for the next rung; P2: no lane, the shortfall named",
    ("PASS", "FAIL"): "P1 the candidate for the next rung; P2: no lane, 'small caps as floored here FAIL' reported with n",
    ("CAN'T TELL", "PASS"): "P1: the live shadow continues unchanged, no rung; P2: the lane proposal",
    ("CAN'T TELL", "CAN'T TELL"): "nothing changes anywhere; both shortfalls named; no re-read without a dated event",
    ("CAN'T TELL", "FAIL"): "P1: nothing; P2: the FAIL reported with n, no lane",
    ("FAIL", "PASS"): "P1: the shadow keeps running, the FAIL goes to him with n (retiring the lane is his call); P2: the lane proposal, flagged that the floored version failed",
    ("FAIL", "CAN'T TELL"): "P1 FAIL to him; P2: nothing",
    ("FAIL", "FAIL"): "both FAILs to him with n; the setup review carries them; nothing live changes",
}


def _cell(v: str) -> str:
    return "PASS" if v.startswith("PASS") else "FAIL" if v.startswith("FAIL") else "CAN'T TELL"


def results(eps: list, say) -> dict:
    nums = {}
    say("\n## The base verdict (primary walk; n = settled, admitted by rule (c), not voided)")
    verdicts = {}
    for pop in POPS:
        sub = [e for e in eps if e["population"] == pop]
        S = [e for e in sub if in_n(e)]
        tally = Counter(e.get("decision") for e in sub)
        say(f"\n### {pop}: climax {len(sub)} -> admitted {tally.get('admitted', 0)} / episode_already_open {tally.get('episode_already_open', 0)} "
            f"(the company key adds {ticker_key_rejections([dict(e) for e in sub if e.get('r5_status') != 'open_at_seal'])} rejections beyond a ticker key)")
        st = Counter(e.get("r5_status") for e in sub if e.get("decision") == "admitted")
        say(f"  admitted by status: {dict(st)}")
        for era in ("pooled", "A", "B"):
            SS = S if era == "pooled" else [e for e in S if e["era"] == era]
            bv = base_verdict(SS, f"base:{pop}:{era}")
            _bv_numbers(f"base:{pop}:{era}", bv, nums)
            _bv_line(say, f"{pop} {era}", bv)
            if era == "pooled":
                verdicts[pop] = bv
        for k in (1, 2):
            bv = base_verdict(S, f"slip{k}:{pop}", r_field=f"r5_r_slip{k}", pnl_field=f"r5_pnl_adr_slip{k}")
            _bv_numbers(f"slip{k}:{pop}", bv, nums)
            _bv_line(say, f"{pop} at {k * 0.1:.1f}% exit slippage per leg", bv)
            if k == 1:
                verdicts[pop + ":slip1"] = bv
        ended = [e for e in sub if e.get("decision") == "admitted" and e.get("r5_status") == "ended_mid_walk"
                 and str(e.get("void_adjustment_event")) != "1" and e.get("distribution_class") != "distribution"]
        tw = verdict_three_ways(S, ended, f"three:{pop}", a=verdicts[pop])
        for lab in ("b", "c"):
            _bv_numbers(f"three:{pop}:{lab}", tw[lab], nums)
        nums[f"three:{pop}:n_delisted"] = tw["n_delisted"]
        nums[f"three:{pop}:label"] = tw["label"]
        say(f"  ended_mid_walk: {len(ended)} ({dict(Counter(e.get('r5_ended_class') for e in ended))}); (b) at the last close -> {tw['b']['verdict']}; "
            f"(c) with the 1.25x haircut -> {tw['c']['verdict']}; label: {tw['label']}")
        verdicts[pop + ":label"] = tw["label"]
        if pop not in READ_POPS:
            continue                                   # R29: the all-small-tier P2 beside prints its base numbers only
        beside = {
            "voids_in": [e for e in sub if e.get("decision") == "admitted" and e.get("r5_status") == "settled"],
            "jump_removed": [e for e in sub if in_n(e, decision="decision_jump_removed")],
            "mna": [e for e in sub if in_n(e, decision="decision_mna")],
        }
        if pop == "P1":
            beside["cap_floor"] = [e for e in sub if in_n(e, decision="decision_cap_floor")]
            small = sum(1 for e in sub if e.get("cap") is not None and e["cap"] < 250_000_000)
            unk = sum(1 for e in sub if e.get("cap") is None)
            nums["cap_floor:P1:rejected_small"], nums["cap_floor:P1:rejected_unknown"] = small, unk
            say(f"  the $250M floor (his signed rule) rejects {small} climaxes under $250M and {unk} with the cap unknown (as live does)")
        for nm, rows in beside.items():
            bv = base_verdict(rows, f"{nm}:{pop}")
            _bv_numbers(f"{nm}:{pop}", bv, nums)
            _bv_line(say, f"beside {nm}", bv)
        e8 = [e for e in sub if in_n(e, label="e5", decision="decision_8k")]
        bv = base_verdict(e8, f"8k:{pop}", r_field="e5_r", pnl_field="e5_pnl_adr")
        _bv_numbers(f"8k:{pop}", bv, nums)
        _bv_line(say, "beside 8-K (earnings on the climax day dropped; the earnings exit walked)", bv)
        say(f"  8-K groups: {dict(Counter(e.get('earnings_flag') for e in sub))}")
        uk = [e for e in sub if in_n(e) and e.get("earnings_flag") == "unknown"]
        bv = base_verdict(uk, f"8k_unknown:{pop}")
        _bv_numbers(f"8k_unknown:{pop}", bv, nums)
        _bv_line(say, "the 8-K unknown group (no CIK / no filing history / 6-K filer; its own group, never 'no earnings')", bv)
        r8 = paired(e8, "e3", f"read1_8k:{pop}", base="e5")
        _read_numbers(f"read1_8k:{pop}", r8, nums)
        _read_line(say, "read 1 in the 8-K row (E3 - E5, the earnings window passed the same time stop)", r8)
        if pop == "P2":
            for g in ("yes", "no"):
                rows = [e for e in S if e.get("gone") == g]
                bv = base_verdict(rows, f"gone_{g}:{pop}")
                _bv_numbers(f"gone_{g}:{pop}", bv, nums)
                _bv_line(say, f"gone = {g} (expectation: the gone companies carry the higher mean R)", bv)
        if pop in READ_POPS:
            say(f"\n### {pop}: the reads (unknown groups excluded; their N printed)")
            r1 = paired(S, "r3", f"read1:{pop}")
            _read_numbers(f"read1:{pop}", r1, nums)
            _read_line(say, "read 1 time stop 3 vs 5 (R3 - R5, paired)", r1)
            r1b = paired(S, "d3", f"read1_d3:{pop}")
            _read_numbers(f"read1_d3:{pop}", r1b, nums)
            _read_line(say, "read 1 beside: exit at the close of D0 + 3 (minus R5, paired)", r1b)
            for key, grp in read_groups().items():
                rr = two_group(S, grp, f"{key}:{pop}")
                _read_numbers(f"{key}:{pop}", rr, nums)
                _read_line(say, key.replace("_", " beside "), rr)
                if key == "read2":
                    rl = {g: [float(e["run_length"]) for e in S if grp(e) == g and e.get("run_length") not in (None, "")] for g in ("A", "B")}
                    say(f"    run length (base to D0) per group: <= 2 pauses mean {np.mean(rl['A']) if rl['A'] else float('nan'):.1f}, "
                        f">= 3 pauses mean {np.mean(rl['B']) if rl['B'] else float('nan'):.1f}; anchor bases {sum(1 for e in S if str(e.get('anchor')) == '1')}")
    p1, p2 = verdicts["P1"]["verdict"], verdicts["P2"]["verdict"]
    say("\n## The consequence grid")
    cell = GRID[(_cell(p1), _cell(p2))]
    flags = []
    for pop, v in (("P1", p1), ("P2", p2)):
        if v.startswith("PASS") and verdicts[pop + ":slip1"]["lo"] <= 0:
            flags.append(f"{pop} PASS at zero cost only")
        if "depends on" in verdicts[pop + ":label"]:
            flags.append(f"{pop}: {verdicts[pop + ':label']}")
    say(f"- P1 {p1} x P2 {p2}: {cell}" + (f" [{'; '.join(flags)}]" if flags else ""))
    nums["grid:cell"] = cell
    return {"numbers": nums, "verdicts": {k: v for k, v in verdicts.items() if isinstance(v, str)}}
