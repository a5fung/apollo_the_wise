"""#327 hypothesis tests — the `run` and `report` phases of hyptests.py (same folder; the docstring of
hyptests.py is the pre-registration of record). Run ONCE; the report reads the row files."""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

import hyptests as H
from hyptests import (HERE, HORIZON, BPS, K_POST, H1C_N, H13_RULES, PIVOT_K, TAIL_R, PATTERNS, _f, fmt, mean,
                      week_of, split_of, settle_first, settle_both, fill_entry, walk_h13, load_reentry_attempt1,
                      load_era_c, load_rank_shadow, sma_n)
import reentry
import p2_probe
from agents.market_intelligence.delayed_entry_shadow import (_trading_days, macd_620, qualified_620_crosses,
                                                              WARMUP_SESSIONS_620, MIN_CROSS_IDX, BASING_BARS,
                                                              BASING_BAND_ADR, HOOK_SHORT, HOOK_LONG)

TEAM = ("TEAM", date(2026, 8, 7))


def w(path, cols, rows):
    with open(HERE / path, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    print(f"wrote {path}: {len(rows)} rows")


def sessions_after(d, n=20):
    return _trading_days(d + timedelta(days=1), HORIZON)[:n]


def campaign_sessions(ctx):
    return sessions_after(ctx["ep"], 20)


# ── H2: entry edge vs control, original and volatility-scaled barriers ─────────────────────────────────

def h2_rows(D):
    """One row per walk: fires (recorded / fillable / at-the-close entry) and every non-fire control session of
    the same campaign windows, under the ORIGINAL pre-EP-ADR barriers and the SCALED trailing-3-session
    barriers (window max(1, s-2)..s; sensitivity: the fire session through the fire bar). Outcome at session 10."""
    rows = []
    fires_by_c = defaultdict(lambda: defaultdict(set))
    for f in D["fires"]:
        fires_by_c[(f["ticker"], f["ep_date"])][f["rung"]].add(f["fire_date"])

    def yard(ctx, sess, s_idx, partial_hl=None):
        """mean(high-low) over post-EP sessions max(1, s-2)..s; the fire session's own range replaced by the
        through-fire-bar range when partial_hl is given (the sensitivity)."""
        rng = []
        for j in range(max(1, s_idx - 2), s_idx + 1):
            d = sess[j - 1]
            b = ctx["bars"].get(d)
            if not b or b["high_price"] is None:
                return None
            if j == s_idx and partial_hl is not None:
                rng.append(partial_hl[0] - partial_hl[1])
            else:
                rng.append(b["high_price"] - b["low_price"])
        return sum(rng) / len(rng) if rng else None

    def walk(entry, y, d0_bars, after_sessions, ctx, bound):
        bars = list(d0_bars) + [((ctx["bars"][d]["high_price"], ctx["bars"][d]["low_price"]) if d in ctx["bars"] and ctx["bars"][d]["high_price"] is not None else None) for d in after_sessions]
        ev, idx = p2_probe.first_passage(bars, entry, entry - y, entry + 2 * y, bound)
        return p2_probe.at_checkpoint(ev, idx, 10, len(d0_bars))

    for (tkr, ep), rungs in fires_by_c.items():
        f0 = next(f for f in D["fires"] if f["ticker"] == tkr and f["ep_date"] == ep)
        ctx = reentry.make_ctx(f0, D["daily"])
        adr = f0["adr_dollar"]
        if adr is None:
            continue
        sess = campaign_sessions(ctx)
        all_fire_dates = set().union(*rungs.values())
        era, split = f0["era"], f0["split"]
        # controls: every non-fire session with >= 10 sessions after it, entered at the close
        for s_idx, sd in enumerate(sess, start=1):
            b = ctx["bars"].get(sd)
            if not b or b["close"] is None or sd in all_fire_dates:
                continue
            after = sessions_after(sd)
            if len(after) < 10:
                continue
            y_s = yard(ctx, sess, s_idx)
            for pat in rungs:            # a control row per pattern it serves (the rerun's per-pattern control sets)
                for bnd in ("pess", "opt"):
                    for bar_kind, y in (("orig", adr), ("scaled", y_s)):
                        if y is None or y <= 0:
                            continue
                        o = walk(b["close"], y, [], after, ctx, bnd)
                        rows.append({"ticker": tkr, "ep_date": ep, "era": era, "split": split, "week": week_of(sd), "pattern": pat,
                                     "is_fire": 0, "entry_kind": "close", "session_idx": s_idx, "barrier": bar_kind, "bound": bnd,
                                     "y": round(y, 4), "y_over_adr": round(y / adr, 3), "outcome": o})
        # fires
        for f in [x for x in D["fires"] if x["ticker"] == tkr and x["ep_date"] == ep]:
            after = sessions_after(f["fire_date"])
            if len(after) < 10:
                continue
            s_idx = f["session_idx"]
            if s_idx is None:
                s_idx = next((i for i, d in enumerate(sess, start=1) if d == f["fire_date"]), None)
                if s_idx is None:
                    continue
            b5 = D["min5"].get((tkr, f["fire_date"])) or []
            fm = f["fire_minute"]
            fb = ctx["bars"].get(f["fire_date"]) or {}
            partial = None
            if fm is not None and b5:
                pre = [x for x in b5 if x["m"] <= fm]
                if pre:
                    partial = (max(x["h"] for x in pre), min(x["l"] for x in pre))
            y_s = yard(ctx, sess, s_idx)
            y_p = yard(ctx, sess, s_idx, partial) if partial else None
            d0_cache = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
            # day-0 bars (recorded): post-fire 5-min bars; lane-recorded -> cached pseudo bars; else abstain if needed
            if fm is None:
                d0_rec = [(fb["high_price"], fb["low_price"])] if fb.get("high_price") is not None else None
            elif b5:
                d0_rec = [(x["h"], x["l"]) for x in b5 if x["m"] > fm]
            elif d0_cache is not None and reentry.day0_pseudo_bars(*d0_cache) is not None:
                d0_rec = [(x["h"], x["l"]) for x in reentry.day0_pseudo_bars(*d0_cache)]
            else:
                d0_rec = None
            fe = fill_entry(f, D["min5"], ctx)
            for bnd in ("pess", "opt"):
                for bar_kind, y in (("orig", adr), ("scaled", y_s), ("scaled_partial", y_p)):
                    if y is None or y <= 0:
                        continue
                    base = {"ticker": tkr, "ep_date": ep, "era": era, "split": split, "week": f["week"], "pattern": f["rung"], "is_fire": 1,
                            "session_idx": s_idx, "barrier": bar_kind, "bound": bnd, "y": round(y, 4), "y_over_adr": round(y / adr, 3)}
                    # recorded entry
                    if d0_rec is None:
                        o = H.ABSTAIN if (fb.get("low_price") is not None and fb["low_price"] <= f["entry"] - y) else walk(f["entry"], y, [], after, ctx, bnd)
                    else:
                        o = walk(f["entry"], y, d0_rec, after, ctx, bnd)
                    rows.append({**base, "entry_kind": "rec", "outcome": o})
                    # at-the-close entry
                    if fb.get("close") is not None:
                        rows.append({**base, "entry_kind": "close", "outcome": walk(fb["close"], y, [], after, ctx, bnd)})
                    # fillable entry
                    if fe is not None:
                        if fe["kind"] == "next_bucket":
                            d0f = [(x["h"], x["l"]) for x in fe["post5"]]
                            rows.append({**base, "entry_kind": "fill", "outcome": walk(fe["entry"], y, d0f, after, ctx, bnd)})
                        elif fe["kind"] == "level_open":
                            rows.append({**base, "entry_kind": "fill", "outcome": walk(fe["entry"], y, d0_rec or [], after, ctx, bnd)})
                        else:   # next session open: that session is bar 1 of the walk
                            aft2 = sessions_after(fe["fire_date"])
                            nb = ctx["bars"][fe["fire_date"]]
                            rows.append({**base, "entry_kind": "fill", "outcome": walk(fe["entry"], y, [(nb["high_price"], nb["low_price"])], aft2, ctx, bnd)})
    return rows


# ── H1b / H1c / H3: stop substitutions and fire features on the same first fires ─────────────────────

def post_gap_range(ctx, f):
    """mean(high-low) of the last <= 3 COMPLETED post-gap sessions known at the fire: the EP day (session 0) and
    post-EP sessions before the fire session. Returns (value, n_sessions_used)."""
    sess = [ctx["ep"]] + [d for d in campaign_sessions(ctx) if d < f["fire_date"]]
    rng = []
    for d in sess[-3:]:
        b = ctx["bars"].get(d)
        if b and b["high_price"] is not None and b["low_price"] is not None:
            rng.append(b["high_price"] - b["low_price"])
    return (sum(rng) / len(rng), len(rng)) if rng else (None, 0)


def locate_low(b5, fm, stop):
    """Bar index (0-based within the session) of the stop-defining low before the fire bar, or None."""
    for i, b in enumerate(b5):
        if b["m"] >= fm:
            break
        if abs(b["l"] - stop) < 1e-6:
            return i
    return None


def stop_rows(D):
    """Per first fire: H1b stops (k x post-gap range), H1c first-N-minute-low stops and the age of the defining
    low, H3 fire-time bucket and volume ratios; the lane's own and the 1xADR settlements from reentry_rows."""
    a1 = load_reentry_attempt1()
    rows = []
    for f in D["fires"]:
        ctx = reentry.make_ctx(f, D["daily"])
        adr = f["adr_dollar"]
        k = (f["ticker"], f["ep_date"].isoformat(), f["rung"])
        d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        row = {"ticker": f["ticker"], "ep_date": f["ep_date"].isoformat(), "era": f["era"], "split": f["split"], "week": f["week"],
               "rung": f["rung"], "fire_date": f["fire_date"].isoformat(), "session_idx": f["session_idx"], "fire_minute": f["fire_minute"],
               "source": f["source"], "entry": f["entry"], "stop": f["stop"], "adr": adr,
               "stop_w": (f["entry"] - f["stop"]) / f["entry"] * 100 if f["stop"] else None}
        for s, lab in (("incumbent", "lane"), ("adr_100", "adr100")):
            for arm in ("trail", "none"):
                ref = a1.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], s, arm))
                row[f"{lab}_{arm}_status"] = ref["status"] if ref else None
                row[f"{lab}_{arm}_r"] = ref["r_gap"] if ref and ref["status"] in ("settled", "marked") else None
                row[f"{lab}_{arm}_outcome"] = ref["outcome"] if ref else None
                if arm == "none" and ref and ref.get("stop_day"):
                    sd = date.fromisoformat(ref["stop_day"])
                    row[f"{lab}_stop_sessions"] = len(_trading_days(f["fire_date"] + timedelta(days=1), sd)) if sd > f["fire_date"] else 0
        # fillable version of the lane's own stop (the baseline for the fillable comparisons)
        sb = settle_both(ctx, D["min5"], f, lambda e, s=f["stop"]: s, d0)
        fl = sb["fill"]
        row["lane_fill_kind"] = fl.get("kind")
        for arm in ("trail", "none"):
            row[f"lane_fill_{arm}_r"] = fl[arm][1] if fl.get("status") in ("settled", "marked") else None
            row[f"lane_fill_{arm}_status"] = fl.get("status")
        # H1b
        rp, n_rp = post_gap_range(ctx, f)
        row["rpost"], row["rpost_n"], row["rpost_over_adr"] = rp, n_rp, (rp / adr if (rp and adr) else None)
        for kk in K_POST:
            lab = f"h1b_{int(kk*100):03d}"
            if rp is None:
                row[f"{lab}_status"] = "no_rpost"
                continue
            sb = settle_both(ctx, D["min5"], f, lambda e, kk=kk, rp=rp: e - kk * rp, d0)
            for ek in ("rec", "fill"):
                r_ = sb[ek]
                row[f"{lab}_{ek}_status"] = r_.get("status")
                e_used = r_.get("entry", f["entry"]) if ek == "fill" else f["entry"]
                row[f"{lab}_{ek}_w"] = ((e_used - r_["stop"]) / e_used * 100) if (r_.get("stop") and e_used) else None
                for arm in ("trail", "none"):
                    row[f"{lab}_{ek}_{arm}_r"] = r_[arm][1] if r_.get("status") in ("settled", "marked") else None
                    row[f"{lab}_{ek}_{arm}_outcome"] = r_[arm][0] if r_.get("status") in ("settled", "marked") else None
                    if arm == "none":
                        row[f"{lab}_{ek}_stop_idx"] = r_.get("stop_idx") if r_.get("status") in ("settled", "marked") else None
        # H1c (c1): first-N-minute low; (c2) age of the defining low; H3 volume
        b5 = D["min5"].get((f["ticker"], f["fire_date"])) or []
        fm = f["fire_minute"]
        if fm is not None and b5:
            for N in H1C_N:
                lab = f"h1c_first{N}"
                if fm < 570 + N:
                    row[f"{lab}_status"] = "fire_before_N"
                    continue
                first = [b for b in b5 if b["m"] < 570 + N]
                if not first or first[0]["m"] != 570:
                    row[f"{lab}_status"] = "no_open_bars"
                    continue
                lowN = min(b["l"] for b in first)
                row[f"{lab}_low"] = lowN
                sb = settle_both(ctx, D["min5"], f, lambda e, lowN=lowN: lowN, d0)
                for ek in ("rec", "fill"):
                    r_ = sb[ek]
                    row[f"{lab}_{ek}_status"] = r_.get("status")
                    for arm in ("trail", "none"):
                        row[f"{lab}_{ek}_{arm}_r"] = r_[arm][1] if r_.get("status") in ("settled", "marked") else None
            i_low = locate_low(b5, fm, f["stop"])
            i_fire = next((i for i, b in enumerate(b5) if b["m"] == fm), None)
            if i_low is not None and i_fire is not None:
                row["low_age_bars"] = i_fire - i_low
                row["low_age_kind"] = "same_session"
                row["vol_low_bar"] = b5[i_low].get("v")
            else:
                row["low_age_bars"] = None
                row["low_age_kind"] = "earlier_session" if f["rung"] in ("ep_low_reclaim", "ep_close_reclaim") else "n/a"
            if i_fire is not None:
                row["vol_fire_bar"] = b5[i_fire].get("v")
                prior = [b.get("v", 0.0) for b in b5[:i_fire]]
                row["vol_prior_mean"] = (sum(prior) / len(prior)) if prior else None
                row["n_prior_bars"] = len(prior)
        row["time_bucket"] = None if fm is None else ("0930" if fm == 570 else ("0935_0959" if fm < 600 else "1000plus"))
        rows.append(row)
    return rows


# ── H4 rows come straight from reentry_rows + the era-C verdict (no recompute) ─────────────────────────

def h4_rows(D):
    a1 = load_reentry_attempt1()
    ec = load_era_c()
    rows = []
    for f in D["fires"]:
        v = ec.get((f["ticker"], f["ep_date"].isoformat()))
        for s, lab in (("incumbent", "lane"), ("adr_100", "adr100")):
            ref = a1.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], s, "trail"))
            if not ref or ref["status"] not in ("settled", "marked"):
                continue
            rows.append({"ticker": f["ticker"], "ep_date": f["ep_date"].isoformat(), "era": f["era"], "split": f["split"], "week": f["week"],
                         "month": f["ep_date"].isoformat()[:7], "rung": f["rung"], "cell": lab, "admit": v or "unscored",
                         "r": ref["r_gap"], "outcome": ref["outcome"]})
    return rows


# ── H5: per-campaign stop-independent outcome + EP-day features ───────────────────────────────────────

def h5_rows(D):
    rs = load_rank_shadow()
    rows = []
    for a in D["alerts"]:
        k = (a["ticker"], a["ep_date"])
        c = D["camps"][k]
        bars = D["daily"].get(a["ticker"], {})
        epb = bars.get(a["ep_date"]) or {}
        adr = c["adr_dollar"]
        sess = sessions_after(a["ep_date"], 15)
        highs = [bars[d]["high_price"] for d in sess if d in bars and bars[d]["high_price"] is not None]
        out = None
        if highs and adr and epb.get("close"):
            out = (max(highs) - epb["close"]) / adr
        r = rs.get((a["ticker"], a["ep_date"].isoformat()), {})
        rows.append({"ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"], "split": split_of(a["ep_date"], a["era"]),
                     "week": week_of(a["ep_date"]), "tier": a["tier"], "outcome_adr15": out, "n_sess": len(highs), "censored": int(len(highs) < 15),
                     "runner7": int((a["ticker"], a["ep_date"].isoformat()) in D["runners"]), "labelled": int((a["ticker"], a["ep_date"].isoformat()) in D["labelled"]),
                     "ext_xadr_eod": _f(r.get("ext_xadr_eod")), "ext_xadr_pregap": _f(r.get("ext_xadr_pregap")),
                     "tightness_pct_eod": _f(r.get("tightness_pct_eod")), "composite_rank_eod": _f(r.get("composite_rank_eod")),
                     "open_range_position": _f(r.get("open_range_position")), "expct_scheduled": r.get("expct_scheduled") or None,
                     "expct_looking": r.get("expct_looking") or None, "expct_beat": r.get("expct_beat") or None,
                     "catalyst_type": r.get("catalyst_type") or None})
    return rows


def main(ph):
    import hyptests_run2
    if ph == "run":
        D = H.load_everything()
        rows = h2_rows(D)
        w("hyp_rows_h2.tsv", ["ticker", "ep_date", "era", "split", "week", "pattern", "is_fire", "entry_kind", "session_idx", "barrier", "bound", "y", "y_over_adr", "outcome"], rows)
        rows = stop_rows(D)
        cols = sorted({c for r in rows for c in r}, key=lambda c: (c not in ("ticker", "ep_date", "era", "split", "week", "rung", "fire_date"), c))
        w("hyp_rows_stops.tsv", cols, rows)
        w("hyp_rows_h4.tsv", ["ticker", "ep_date", "era", "split", "week", "month", "rung", "cell", "admit", "r", "outcome"], h4_rows(D))
        rows = h5_rows(D)
        w("hyp_rows_h5.tsv", list(rows[0].keys()), rows)
        hyptests_run2.run_h12_h13(D)
    elif ph == "report":
        import hyptests_report
        hyptests_report.report()
    else:
        raise SystemExit(f"unknown phase {ph}")
