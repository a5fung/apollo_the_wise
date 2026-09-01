"""#562/#327 — OFFLINE REPLAY of the delayed-entry watch lane over stored EP history.

Question: what do the lane's four rungs (ep_low_reclaim / ep_close_reclaim /
ep_high_break / ep_close_620_prox) do over the 267 live-source EP alerts May-Aug 2026 —
fire rate, HARVESTED R under the lane's own settlement (M-none / M-trail), the >=4R
tail, what each rung misses, and whether any of it holds across eras.

FIDELITY CONTRACT (the reason this replay measures anything):
  - Every rung decision and the settlement walk go through the lane's OWN pure
    functions, imported from agents/market_intelligence/delayed_entry_shadow.py:
    session_needs_minutes / evaluate_session_minute / evaluate_session_daily /
    session_needs_minutes_620 / evaluate_session_620 / compute_settlement /
    to_rth_5min / compute_adr20 / compute_ep_adr_dollar / new_state / _trading_days
    + the rung constants. NOTHING re-implemented.
  - THE ABSTAIN RULE holds with full force: a minute-resolution decision whose
    minute bars are absent from mi_intraday_bars ABSTAINS (daily facts still fold,
    exactly the lane's missing-bars branch) — never a daily fallback, never a
    fabricated fill. Offline there is no "retry next run", so an abstain is
    permanent and is COUNTED as a result.
  - Population: live-source mi_ep_alerts (COALESCE(source,'live')='live'), all
    tiers, one row per ticker x alert_date (operator ruling 2026-09-01: any real EP
    our system caught, not just the ones we traded).
  - Re-entry recording (same_pattern / new_high_break) is NOT replayed — first
    attempts only. Stated as a limitation in the analysis doc.

Data (captured ONCE from prod, read-only, then worked from files — no live reads):
    _562bf_alerts.tsv   the 267 campaigns + context
    _562bf_daily.tsv    mi_daily_closes for cohort tickers 2026-02-15..2026-08-31
    _562bf_mincov.tsv   which (ticker, ET day) pairs mi_intraday_bars holds
    _562bf_minute.tsv.gz  1-min bars for the needed pairs only (phase `pairs` output
                          drives the SQL pull)

Usage:
    python scripts/probes/_562_backfill_replay.py pairs    # -> _562bf_needed_pairs.tsv
    python scripts/probes/_562_backfill_replay.py replay   # -> _562bf_triggers.tsv, _562bf_campaigns.tsv
    python scripts/probes/_562_backfill_replay.py report   # aggregate tables to stdout

Throwaway diagnostic (scripts/probes/ convention). Read-only everywhere; writes only
its own TSVs next to itself. No prod writes, no thresholds touched, THE LINE intact.
"""
from __future__ import annotations

import csv
import gzip
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.delayed_entry_shadow import (  # noqa: E402
    LANE_SESSIONS,
    RUNG_620_PROX,
    RUNG_EP_CLOSE,
    RUNG_EP_HIGH,
    RUNG_EP_LOW,
    WARMUP_SESSIONS_620,
    _trading_days,
    compute_adr20,
    compute_ep_adr_dollar,
    compute_settlement,
    evaluate_session_620,
    evaluate_session_daily,
    evaluate_session_minute,
    new_state,
    session_needs_minutes,
    session_needs_minutes_620,
    to_rth_5min,
)

HERE = Path(__file__).resolve().parent
LAST_DATA_DAY = date(2026, 8, 31)   # last daily bar in the capture — the replay horizon
RUNGS = (RUNG_EP_LOW, RUNG_EP_CLOSE, RUNG_EP_HIGH, RUNG_620_PROX)


def _f(v):
    if v in (None, "", "\\N"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def read_tsv(name, gz=False):
    """psql -A output: header row, | delimiter, trailing '(N rows)' line."""
    p = HERE / name
    opener = (lambda: gzip.open(p, "rt")) if gz else (lambda: open(p))
    with opener() as fh:
        rows = list(csv.reader(fh, delimiter="|"))
    hdr = rows[0]
    out = []
    for r in rows[1:]:
        if len(r) != len(hdr):
            continue  # the '(N rows)' trailer
        out.append(dict(zip(hdr, r)))
    return out


def load_alerts():
    out = []
    for r in read_tsv("_562bf_alerts.tsv"):
        out.append({
            "ticker": r["ticker"],
            "ep_date": date.fromisoformat(r["alert_date"]),
            "tier": r["score_tier"],
            "ep_score": _f(r["ep_score"]),
            "gap_pct": _f(r["gap_pct"]),
            "catalyst_grade": r["catalyst_quality"] or None,
        })
    return out


def load_daily():
    """ticker -> {trade_date: bar-dict in the lane's mi_daily_closes column names}."""
    by = defaultdict(dict)
    for r in read_tsv("_562bf_daily.tsv"):
        d = date.fromisoformat(r["trade_date"])
        by[r["ticker"]][d] = {
            "trade_date": d,
            "open_price": _f(r["open_price"]),
            "high_price": _f(r["high_price"]),
            "low_price": _f(r["low_price"]),
            "close": _f(r["close"]),
            "volume": _f(r["volume"]),
        }
    return by


def load_mincov():
    cov = set()
    for r in read_tsv("_562bf_mincov.tsv"):
        cov.add((r["ticker"], date.fromisoformat(r["d"])))
    return cov


def load_minutes():
    """(ticker, day) -> completed RTH 5-min bars via the lane's OWN to_rth_5min."""
    raw = defaultdict(list)
    for r in read_tsv("_562bf_minute.tsv.gz", gz=True):
        raw[(r["ticker"], date.fromisoformat(r["d"]))].append({
            "t": int(float(r["t_ms"])), "o": float(r["o"]), "h": float(r["h"]),
            "l": float(r["l"]), "c": float(r["c"]), "v": _f(r["v"]) or 0,
        })
    out = {}
    for (tkr, d), bars in raw.items():
        out[(tkr, d)] = to_rth_5min(bars, d)
    return out


def campaign_sessions(ep_date):
    """Forward trading sessions after the EP day, capped at the lane's 20."""
    if ep_date >= LAST_DATA_DAY:
        return []
    return _trading_days(ep_date + timedelta(days=1), LAST_DATA_DAY)[:LANE_SESSIONS]


# ── phase 1: which (ticker, day) minute pairs could the walk need? ────────────────────
# Conservative superset: undercut/dip/clean state facts ARE daily facts (a minute low
# below a level <=> the daily low is below it), so they replay exactly from daily bars;
# only the fired_* flags depend on minutes, and assuming never-fired only ADDS pairs.


def phase_pairs():
    alerts, daily = load_alerts(), load_daily()
    pairs = set()
    for a in alerts:
        tkr, ep = a["ticker"], a["ep_date"]
        bars = daily.get(tkr, {})
        epb = bars.get(ep)
        if not epb or epb["close"] is None:
            continue
        gl, gc, gh = epb["low_price"], epb["close"], epb["high_price"]
        ordered = sorted(bars)
        adr_dollar, _ = compute_ep_adr_dollar([bars[d] for d in ordered], ep, gc)
        st = new_state()  # never-fired assumption held throughout (superset)
        sess = campaign_sessions(ep)
        for d in sess:
            b = bars.get(d)
            if not b or b["close"] is None:
                continue
            hi, lo = b["high_price"], b["low_price"]
            need = session_needs_minutes(hi, lo, gap_low=gl, gap_close=gc,
                                         gap_high=gh, state=st)
            need620 = session_needs_minutes_620(hi, lo, gap_close=gc,
                                                adr_dollar=adr_dollar, state=st)
            if need or need620:
                pairs.add((tkr, d))
            if need620:  # warm-up: up to 2 prior sessions with daily bars
                prior = [x for x in ordered if x < d][-WARMUP_SESSIONS_620:]
                for w in prior:
                    pairs.add((tkr, w))
            # fold the daily facts so the state's undercut/dip flags stay faithful
            res = evaluate_session_daily(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh,
                                         prior_session_low=None, state=st)
            st = res["state"]
            for k in ("fired_ep_low_reclaim", "fired_ep_close_reclaim",
                      "fired_ep_high_break", "fired_ep_close_620_prox"):
                st[k] = False  # keep the never-fired superset assumption
    with open(HERE / "_562bf_needed_pairs.tsv", "w") as fh:
        fh.write("ticker|d\n")
        for tkr, d in sorted(pairs):
            fh.write(f"{tkr}|{d.isoformat()}\n")
    print(f"needed pairs: {len(pairs)}")
    cov = load_mincov()
    have = sum(1 for p in pairs if p in cov)
    print(f"of which present in mi_intraday_bars: {have} "
          f"({have / len(pairs) * 100:.1f}%) — the rest will ABSTAIN")


# ── phase 2: the replay itself ────────────────────────────────────────────────────────


def walk_campaign(a, daily, minutes, mincov):
    """One campaign: mirror _walk_one_member's decision branches exactly, driving the
    lane's pure functions; then settle each first fire with compute_settlement."""
    tkr, ep = a["ticker"], a["ep_date"]
    bars = daily.get(tkr, {})
    epb = bars.get(ep)
    camp = {
        "ticker": tkr, "ep_date": ep, "tier": a["tier"], "gap_pct": a["gap_pct"],
        "sessions_expected": len(campaign_sessions(ep)),
        "sessions_walked": 0, "sessions_abstained": 0,
        "complete20": False, "enroll_status": "ok",
        "max_high_pct": None, "max_adr_mult": None, "adr_dollar": None,
        "fires": [],
    }
    if not epb or epb["close"] is None or epb["high_price"] is None or epb["low_price"] is None:
        camp["enroll_status"] = "no_ep_day_bar"
        return camp
    gl, gc, gh = epb["low_price"], epb["close"], epb["high_price"]
    ordered = sorted(bars)
    all_bars = [bars[d] for d in ordered]
    adr_dollar, adr_n = compute_ep_adr_dollar(all_bars, ep, gc)
    camp["adr_dollar"] = adr_dollar

    st = new_state()
    sess = campaign_sessions(ep)
    max_high = None
    warm_cache = {}

    for idx, d in enumerate(sess, start=1):
        b = bars.get(d)
        if not b or b["close"] is None or b["high_price"] is None or b["low_price"] is None:
            camp["sessions_abstained"] += 1  # missing daily bar: know nothing, state carries
            continue
        camp["sessions_walked"] += 1
        hi, lo = b["high_price"], b["low_price"]
        max_high = hi if max_high is None else max(max_high, hi)
        prior = [x for x in ordered if x < d]
        prior_low = bars[prior[-1]]["low_price"] if prior else None

        needs_min = session_needs_minutes(hi, lo, gap_low=gl, gap_close=gc,
                                          gap_high=gh, state=st)
        needs_620 = session_needs_minutes_620(hi, lo, gap_close=gc,
                                              adr_dollar=adr_dollar, state=st)
        bars5 = minutes.get((tkr, d), []) if (needs_min or needs_620) else []

        if (needs_min or needs_620) and not bars5:
            # THE ABSTAIN RULE — the lane's missing-minute-bars branch verbatim:
            # fold daily facts, no minute-grade fire; the unambiguous daily
            # ep_high_break may still fire when only the 620 needed minutes.
            res = evaluate_session_daily(
                hi, lo, gap_low=gl, gap_close=gc, gap_high=gh,
                prior_session_low=(None if needs_min else prior_low), state=st)
            st = res["state"]
            camp["sessions_abstained"] += 1
            for fire in res["fires"]:
                camp["fires"].append(_mk_fire(fire, d, idx, "daily"))
            continue

        if needs_min:
            res = evaluate_session_minute(bars5, gap_low=gl, gap_close=gc, gap_high=gh,
                                          prior_session_low=prior_low, state=st)
        else:
            res = evaluate_session_daily(hi, lo, gap_low=gl, gap_close=gc, gap_high=gh,
                                         prior_session_low=prior_low, state=st)
        if needs_620:
            warm = []
            for w in prior[-WARMUP_SESSIONS_620:]:
                if w not in warm_cache:
                    warm_cache[w] = minutes.get((tkr, w), [])
                warm.extend(warm_cache[w])   # best-effort seed, the lane's own rule
            r620 = evaluate_session_620(warm, bars5, gap_close=gc,
                                        adr_dollar=adr_dollar, state=res["state"])
            res = {"fires": res["fires"] + r620["fires"], "state": r620["state"],
                   "p3_needs_prior_low": res.get("p3_needs_prior_low", False)}
        st = res["state"]
        if res.get("p3_needs_prior_low"):
            camp["sessions_abstained"] += 1  # would-fire ep_high_break, unknown prior low
        for fire in res["fires"]:
            camp["fires"].append(_mk_fire(
                fire, d, idx,
                "minute_5" if fire.get("fire_minute") is not None else "daily"))

    camp["complete20"] = (len(sess) == LANE_SESSIONS
                          and camp["sessions_walked"] == LANE_SESSIONS)
    if max_high is not None:
        camp["max_high_pct"] = (max_high - gc) / gc * 100.0
        if adr_dollar:
            camp["max_adr_mult"] = (max_high - gc) / adr_dollar

    # ── settle every fire via the lane's own settlement core ──
    for f in camp["fires"]:
        _settle_fire(f, tkr, bars, ordered, minutes, mincov)
    return camp


def _mk_fire(fire, d, idx, resolution):
    return {"rung": fire["rung"], "fire_date": d, "session_idx": idx,
            "fire_minute": fire.get("fire_minute"), "resolution": resolution,
            "entry": float(fire["entry"]), "stop": float(fire["stop"])}


def _settle_fire(f, tkr, bars, ordered, minutes, mincov):
    entry, stop = f["entry"], f["stop"]
    fire_date = f["fire_date"]
    fb = bars.get(fire_date) or {}
    fire_day_bar = {"h": fb.get("high_price"), "l": fb.get("low_price"),
                    "c": fb.get("close")}
    post5 = None
    if (f["fire_minute"] is not None and fire_day_bar["l"] is not None
            and fire_day_bar["l"] <= stop):
        bars5 = minutes.get((tkr, fire_date))
        if bars5:
            post5 = [b for b in bars5 if b["m"] > f["fire_minute"]]
        # missing day-0 minutes -> post5 None -> compute_settlement ABSTAINS
    sessions = _trading_days(fire_date + timedelta(days=1), LAST_DATA_DAY)
    closes_before = [bars[d]["close"] for d in ordered
                     if d < fire_date and bars[d]["close"] is not None]
    res = compute_settlement(
        entry=entry, stop=stop, fire_minute=f["fire_minute"],
        fire_day_bar=fire_day_bar, post_fire_bars5=post5, sessions=sessions,
        bars_by_day=bars, closes_before_fire=closes_before)
    f["settle_status"] = res["status"]
    f["settle_reason"] = res.get("reason")
    if res["status"] == "settled":
        for k in ("outcome", "realized_r", "outcome_trail", "realized_r_trail",
                  "mfe_r", "mae_r", "reached_4r"):
            f[k] = res.get(k)


def phase_replay():
    alerts, daily = load_alerts(), load_daily()
    minutes, mincov = load_minutes(), load_mincov()
    camps = [walk_campaign(a, daily, minutes, mincov) for a in alerts]

    with open(HERE / "_562bf_campaigns.tsv", "w") as fh:
        cols = ["ticker", "ep_date", "tier", "gap_pct", "enroll_status",
                "sessions_expected", "sessions_walked", "sessions_abstained",
                "complete20", "max_high_pct", "max_adr_mult", "adr_dollar"]
        fh.write("|".join(cols) + "\n")
        for c in camps:
            fh.write("|".join("" if c[k] is None else str(c[k]) for k in cols) + "\n")
    with open(HERE / "_562bf_triggers.tsv", "w") as fh:
        cols = ["ticker", "ep_date", "rung", "fire_date", "session_idx", "resolution",
                "entry", "stop", "settle_status", "settle_reason", "outcome",
                "realized_r", "outcome_trail", "realized_r_trail", "mfe_r", "mae_r",
                "reached_4r"]
        fh.write("|".join(cols) + "\n")
        for c in camps:
            for f in c["fires"]:
                f = {**f, "ticker": c["ticker"], "ep_date": c["ep_date"]}
                fh.write("|".join("" if f.get(k) is None else str(f.get(k))
                                  for k in cols) + "\n")
    n_f = sum(len(c["fires"]) for c in camps)
    print(f"{len(camps)} campaigns walked, {n_f} first-attempt fires recorded")


# ── phase 3: the report tables ────────────────────────────────────────────────────────


def _stats(rs):
    rs = [r for r in rs if r is not None]
    if not rs:
        return "n=0"
    return (f"n={len(rs)} mean={statistics.mean(rs):+.2f} "
            f"med={statistics.median(rs):+.2f} sum={sum(rs):+.1f} "
            f"win={sum(1 for r in rs if r > 0) / len(rs) * 100:.0f}% "
            f">=4R={sum(1 for r in rs if r >= 4)}")


def phase_report():
    camps = read_tsv("_562bf_campaigns.tsv")
    trigs = read_tsv("_562bf_triggers.tsv")
    for c in camps:
        c["mon"] = c["ep_date"][:7]
        c["max_adr_mult"] = _f(c["max_adr_mult"])
        c["max_high_pct"] = _f(c["max_high_pct"])
    # a fire is MATURE when 20 post-fire sessions existed by the data horizon: its
    # settlement could have gone EITHER way. An immature fire can only have settled
    # as a stop (a time exit needs 20 sessions), so immature settled rows are losers
    # BY CONSTRUCTION and must never pool into expectancy.
    from bisect import bisect_right
    all_days = _trading_days(date(2026, 2, 15), LAST_DATA_DAY)
    for t in trigs:
        t["mon"] = t["ep_date"][:7]
        t["realized_r"] = _f(t["realized_r"])
        t["realized_r_trail"] = _f(t["realized_r_trail"])
        t["mfe_r"] = _f(t["mfe_r"])
        t["session_idx"] = int(t["session_idx"])
        fd = date.fromisoformat(t["fire_date"])
        t["mature"] = (len(all_days) - bisect_right(all_days, fd)) >= 20
        e, s = _f(t["entry"]), _f(t["stop"])
        t["stop_w"] = (e - s) / e * 100.0 if e else None

    walked = [c for c in camps if c["enroll_status"] == "ok" and int(c["sessions_walked"]) > 0]
    key = lambda c: (c["ticker"], c["ep_date"])
    walked_keys = {key(c) for c in walked}
    print(f"campaigns: {len(camps)} total, {len(walked)} walked>=1, "
          f"{sum(1 for c in camps if c['complete20'] == 'True')} complete-20, "
          f"{sum(1 for c in camps if c['enroll_status'] != 'ok')} unenrollable")
    print(f"session abstain rate: "
          f"{sum(int(c['sessions_abstained']) for c in camps)} of "
          f"{sum(int(c['sessions_walked']) + int(c['sessions_abstained']) for c in camps)} sessions")
    fired_any = {key(t) for t in trigs}
    print(f"family union: {len(fired_any & walked_keys)}/{len(walked_keys)} campaigns "
          f"fired >=1 rung")
    mt = [t for t in trigs if t["mature"]]
    im = [t for t in trigs if not t["mature"]]
    print(f"fires: {len(trigs)} total -> {len(mt)} MATURE (20 post-fire sessions "
          f"existed; expectancy is readable) + {len(im)} immature (settled rows are "
          f"stops BY CONSTRUCTION — winners still open; never pooled)")

    hard = [c for c in walked if c["max_adr_mult"] is not None and c["max_adr_mult"] >= 8]

    print("\n== per rung, first attempts, MATURE fires only ==")
    for rung in RUNGS:
        rt_all = [t for t in trigs if t["rung"] == rung]
        rt = [t for t in rt_all if t["mature"]]
        fired_keys = {key(t) for t in rt_all}
        settled = [t for t in rt if t["settle_status"] == "settled"]
        openr = [t for t in rt if t["settle_status"] == "abstain"]
        sess_med = statistics.median([t["session_idx"] for t in rt_all]) if rt_all else None
        w_med = statistics.median([t["stop_w"] for t in rt_all if t["stop_w"] is not None])
        print(f"\n{rung}: fired {len(fired_keys)}/{len(walked_keys)} campaigns "
              f"({len(fired_keys) / len(walked_keys) * 100:.0f}%), median fire session "
              f"{sess_med}, median stop width {w_med:.1f}% of entry")
        print(f"  mature fires {len(rt)} (settled {len(settled)}, "
              f"still-blocked {len(openr)}); immature {len(rt_all) - len(rt)}")
        print(f"  M-none : {_stats([t['realized_r'] for t in settled])}")
        print(f"  M-trail: {_stats([t['realized_r_trail'] for t in settled])}")
        missed = [c for c in hard if key(c) not in fired_keys]
        print(f"  ran-hard (>=8xADR over EP close) campaigns: {len(hard)}; "
              f"missed by this rung: {len(missed)} "
              f"[{', '.join(c['ticker'] + ' ' + c['ep_date'] for c in missed)}]")
        for mon in ("2026-05", "2026-06", "2026-07", "2026-08"):
            ms = [t for t in settled if t["mon"] == mon]
            mw = [c for c in walked if c["mon"] == mon]
            mf = {key(t) for t in rt_all if t["mon"] == mon}
            n_im = sum(1 for t in rt_all if t["mon"] == mon and not t["mature"])
            print(f"    {mon}: fired {len(mf)}/{len(mw)}  "
                  f"M-none {_stats([t['realized_r'] for t in ms])}  immature={n_im}")

    print("\n== family (take every first fire, all four rungs) — MATURE only ==")
    settled_all = [t for t in mt if t["settle_status"] == "settled"]
    print(f"  M-none : {_stats([t['realized_r'] for t in settled_all])}")
    print(f"  M-trail: {_stats([t['realized_r_trail'] for t in settled_all])}")
    open_all = [t for t in trigs if t["settle_status"] == "abstain"
                and t["settle_reason"] == "window_open"]
    print(f"  immature fires excluded above: {len(im)} "
          f"({sum(1 for t in im if t['settle_status'] == 'settled')} already stopped, "
          f"{len(open_all)} open — the open rows are the candidate winners)")

    # adversarial: drop the best campaign / best month (settled MATURE M-none sum)
    by_c = defaultdict(float)
    for t in settled_all:
        if t["realized_r"] is not None:
            by_c[key(t)] += t["realized_r"]
    if by_c:
        best = max(by_c, key=by_c.get)
        rest = [t["realized_r"] for t in settled_all if key(t) != best]
        print(f"\n  drop best campaign {best} ({by_c[best]:+.1f}R): M-none {_stats(rest)}")
    by_m = defaultdict(float)
    for t in settled_all:
        if t["realized_r"] is not None:
            by_m[t["mon"]] += t["realized_r"]
    if by_m:
        bestm = max(by_m, key=by_m.get)
        rest = [t["realized_r"] for t in settled_all if t["mon"] != bestm]
        print(f"  drop best month {bestm} ({by_m[bestm]:+.1f}R): M-none {_stats(rest)}")

    print("\n== the tail: mature settled fires with harvested R >= 4 (either arm) ==")
    for t in sorted(settled_all, key=lambda x: -(x["realized_r"] or -9)):
        rn, rt_ = t["realized_r"], t["realized_r_trail"]
        if (rn is not None and rn >= 4) or (rt_ is not None and rt_ >= 4):
            print(f"  {t['ticker']:6s} {t['ep_date']} {t['rung']:20s} s{t['session_idx']:<3d} "
                  f"stop {t['stop_w']:.1f}%  M-none {rn:+.2f}R  M-trail {rt_:+.2f}R  "
                  f"mfe {t['mfe_r']:+.1f}R")

    print("\n== capture on the ran-hard campaigns (>=8xADR over EP close) ==")
    for c in sorted(hard, key=lambda x: -x["max_adr_mult"]):
        k = key(c)
        rows = [t for t in trigs if key(t) == k]
        settled_rs = [t["realized_r"] for t in rows
                      if t["settle_status"] == "settled" and t["realized_r"] is not None]
        n_open = sum(1 for t in rows if t["settle_status"] == "abstain")
        best = f"{max(settled_rs):+.2f}R" if settled_rs else "—"
        print(f"  {c['ticker']:6s} {c['ep_date']} ran {c['max_high_pct']:+.0f}% "
              f"({c['max_adr_mult']:.0f}xADR): {len(rows)} fires, best settled {best}, "
              f"open {n_open}")

    reasons = defaultdict(int)
    for t in trigs:
        if t["settle_status"] == "abstain" and t["settle_reason"] != "window_open":
            reasons[t["settle_reason"].split(":")[0]] += 1
        elif t["settle_status"] == "unscoreable":
            reasons["unscoreable:" + (t["settle_reason"] or "?")] += 1
    print(f"\n  settlement blocked offline (non-window reasons): {dict(reasons)}")


if __name__ == "__main__":
    {"pairs": phase_pairs, "replay": phase_replay,
     "report": phase_report}[sys.argv[1]]()
