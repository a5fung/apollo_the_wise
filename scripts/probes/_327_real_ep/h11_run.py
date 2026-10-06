"""#327 H11 — confluence (an MA sitting on the reclaimed level) and per-stock pullback character, on the 277 real
EPs. $0, read-only, local files only (this folder). No prod read, no DB write, no deploy, no commit.

H11 (verbatim, 327_hypotheses_2026-09-27.md): "Confluence and per-stock character have never been an arm (ledger
open questions 3 and 4; his 06-11 ruling that one global pivot rule erases the character that IS the principle).
The MNTS two-fold (MA reclaim AND gap-low reclaim in one move) is the original blueprint."
Test (verbatim): "Split existing fires by whether SMA20/21-EMA sits within 0.25x ADR of the reclaimed level; label
each stock's habitual pullback support from pre-EP history and compare matched vs mismatched fires."
Pop + pass (verbatim): "Pop: 632 first fires + a 20/21-DMA reclaim fire per campaign. Pass: matched fires >= +8 pts
over non-matched on >= 60, ex-May, ERA B same sign."

═════════════════════ PRE-REGISTRATION (written BEFORE any outcome was read) ═════════════════════
POPULATION
  Part A = fires.tsv, the 632 first fires (ERA A 595, ERA B 37), the 09-27 harness population, unchanged.
    Reclaimed level L per rung (declared): ep_low_reclaim -> EP-day low; ep_close_reclaim -> EP-day close;
    ep_close_620_prox -> EP-day close (its band centre); ep_high_break -> NO reclaimed level (a breakout) -> n/a,
    excluded from matched/non-matched, counted.
  Part B = one "20/21-DMA reclaim" fire per campaign (all 277), DAILY grade: the first post-EP session s in 1..20
    whose bar has low <= MA <= close for SMA20 or 21-EMA (MA = closes strictly before session s: known at the
    open, no look-ahead). Entry = that session's CLOSE; stop = that session's LOW (the lane's reclaim convention:
    the low of the undercut); 1xADR$ stop beside. Excluded and counted: EP-day close not above the MA zone (no
    pullback TO the MA is possible — a session-1 cross would be a breakout), SMA20 lacking history, a hole in the
    daily bars before a fire (never leapt), entry == stop.
  MA history rule: SMA20 needs >= 20 prior closes; 21-EMA (the lane's _ema_series, seeded at the first close in
    daily.tsv, which starts 2025-12-01) needs >= 42 prior closes (2x span; seed weight < 2%). A fire lacking the
    history for one MA is judged on the other; lacking both -> "no history", counted, excluded.
MATCHED (the global-rule arm — the rule his 06-11 ruling names as the anti-pattern, measured because H11 asks):
    Part A: |SMA20 - L| <= 0.25 x ADR$ OR |EMA21 - L| <= 0.25 x ADR$, ADR$ = the fire's pre-EP adr_dollar
      (the lane's own yardstick). Draws: "either" (primary), SMA20-only, EMA21-only.
    Part B (the MNTS two-fold): the touched MA sits within 0.25 x ADR$ of the EP-day low OR the EP-day close
      (EP-low-only shown beside, not counted). SMA20-only / EMA21-only draws use fires touching that MA.
    Shown beside, never counted: the "at-fire" MA (prior closes + the entry price as today's value).
HABITUAL SUPPORT (the per-stock arm), from STRICTLY pre-EP daily history, one label per campaign:
    pullback low = session i with low_i < low_{i-1}, low_{i-2} and low_i <= low_{i+1}, low_{i+2} (all pre-EP),
    close_i > SMA50_i (uptrend context; MAs include day i — a chart reading, all pre-EP); ADR_i = mean(high-low)
    of the 20 sessions through i. MA k in {SMA10, SMA20, SMA50} is TESTED when low_i <= MA_k + 0.25 x ADR_i and
    close_i >= MA_k (came within a quarter-range of it, or undercut it, and closed back above). The pullback's
    support = the DEEPEST (lowest-valued) MA tested; none tested -> "no-MA pullback" (counted).
    label = the MA with the most tests, >= 3 tests AND strictly more than the runner-up; else "none" (unlabelled).
    matched_hab = |MA_hab at the fire (prior closes) - L| <= 0.25 x ADR$ (Part B: L = the touched MA's value).
    Compared: matched_hab vs every other fire on LABELLED stocks (registered); matched_hab vs "mismatched"
    (L near a different MA in {SMA10, SMA20, EMA21, SMA50} but not near the habitual one) shown beside.
OUTCOME (the SAME measure as 09-27's H2 fire edge): +2-first rate in percentage points — walk from the entry with
    a stop barrier at entry - 1 x ADR$ and a target at entry + 2 x ADR$ (pre-EP ADR$, the "original" barriers),
    pess (stop first on a straddle), resolved by session 10; rate = share of non-abstaining fires resolved
    TARGET (open counts as not-target). Part A reads hyp_rows_h2.tsv (is_fire=1, entry_kind=rec, barrier=orig,
    bound=pess) — no recompute; fillable entry (entry_kind=fill) and the scaled barrier (trailing 3-session
    range, barrier=scaled) beside. Part B computes the same walk at the close entry (no day-0 bars, like H2's
    controls and at-the-close entries); anchored first by recomputing H2's entry_kind=close rows for all 632.
    Beside, never instead: mean R on the lane's trail arm at the lane's own stop and at 1xADR$ (Part A from
    reentry_rows.tsv attempt 1; Part B through reentry.settle_attempt -> compute_settlement, entry at the close
    via an empty post-fire 5-min list at fm = 15:59, gaps charged at the open as 09-27), and THE TAIL: share of
    fires >= 3R on each stop, plus the rerun's 7 big-winner EPs (summary.json) and his 4 labelled EPs.
DRAWS (counted): "either" union (A+B, primary) · SMA20-only union · EMA21-only union · habitual = 4.
    Noise: 0.05 x 4 = 0.2 expected false clears; per-rung, per-part, per-bucket, at-fire, fill, scaled: shown.
BAR (verbatim, operationalised before running):
    (1) ERA A (alert < 08-22): matched minus non-matched >= +8.0 pts AND matched n >= 60 fires.
    (2) ex-May (ERA A, alert month != 2026-05): matched minus non-matched >= +8.0 pts.
    (3) ERA B (alert >= 08-22): same sign (> 0); readable only with >= 8 fires in EACH arm, else "can't tell".
    PASS = (1)(2)(3) all met. A leg unreadable on n -> the hypothesis cannot pass; reported as CAN'T TELL (n), with
    direction, never as a pass. Program standard reported beside (not in the verbatim bar): drop the matched
    arm's best two names; week-block permutation (labels shuffled within ISO week of the fire, 2000 draws, seed
    327) on ERA A and DISCOVERY (alert <= 08-14); the 08-15..08-21 week (HELD-OUT A) shown separately.
CONFOUND DECLARED BEFORE RUNNING (advisor): after a ~15% gap the SMA20 sits far below the EP-day levels at
    session 1 and climbs into the band only later, so "matched" may be a proxy for "late fire" — and 09-27 found
    late fires worse and every >= 3R winner fire at session 1-2. The matched share is tabulated by session
    bucket (1-2 / 3-5 / 6-10 / 11+) BEFORE any outcome, and the comparison is reported pooled AND within bucket
    plus a bucket-weighted difference (weights = matched n per bucket). If matched is > 80% session 6+, the
    pooled number is read as lateness, not confluence.
EXPECTED (stated so a surprise is visible): matched is rare at session 1-2 and concentrated late; the pooled
    difference is negative or flat; the habitual leg labels a minority of stocks (pre-EP small caps are mostly not
    in uptrends) and cannot reach n >= 60 matched.

Usage: python3 h11_run.py pop   -> h11_pop_out.txt (population + session buckets; NO outcomes)
       python3 h11_run.py run   -> h11_rows.tsv (Part A), h11_marows.tsv (Part B), h11_anchor_out.txt
       python3 h11_report.py    -> h11_out.txt
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import hyptests as H                                  # noqa: E402
from hyptests import HORIZON, ERA_SPLIT, DISC_END, week_of, split_of, gap_charge, load_reentry_attempt1  # noqa: E402
import rerun                                          # noqa: E402
import reentry                                        # noqa: E402
import p2_probe                                       # noqa: E402
from agents.market_intelligence.delayed_entry_shadow import _ema_series, _trading_days  # noqa: E402

BAND = 0.25
SMA_MIN, EMA_MIN = 20, 42
HAB_MIN_TESTS = 3
LEVEL_OF = {"ep_low_reclaim": "ep_low", "ep_close_reclaim": "ep_close", "ep_close_620_prox": "ep_close",
            "ep_high_break": None}
_TD = {}


def sessions_after(d, n=20):
    if d not in _TD:
        _TD[d] = _trading_days(d + timedelta(days=1), HORIZON)
    return _TD[d][:n]


def bucket(s):
    if s is None:
        return None
    return "s01-02" if s <= 2 else ("s03-05" if s <= 5 else ("s06-10" if s <= 10 else "s11+"))


def closes_before(bars, ordered, day):
    return [bars[d]["close"] for d in ordered if d < day and bars[d]["close"] is not None]


def mas_from(closes):
    n = len(closes)
    return {"n_closes": n,
            "sma10": sum(closes[-10:]) / 10 if n >= 10 else None,
            "sma20": sum(closes[-20:]) / 20 if n >= SMA_MIN else None,
            "ema21": _ema_series(closes, 21)[-1] if n >= EMA_MIN else None,
            "sma50": sum(closes[-50:]) / 50 if n >= 50 else None}


def near(v, L, adr):
    return v is not None and L is not None and adr and abs(v - L) <= BAND * adr


# ── habitual pullback support (strictly pre-EP) ────────────────────────────────────────────────────────

def habitual(bars, ordered, ep):
    H_ = [d for d in ordered if d < ep and None not in (bars[d]["close"], bars[d]["high_price"], bars[d]["low_price"])]
    c = [bars[d]["close"] for d in H_]
    lo = [bars[d]["low_price"] for d in H_]
    hi = [bars[d]["high_price"] for d in H_]
    tests, pullbacks, no_ma = Counter(), 0, 0
    for i in range(49, len(H_) - 2):
        if not (lo[i] < lo[i - 1] and lo[i] < lo[i - 2] and lo[i] <= lo[i + 1] and lo[i] <= lo[i + 2]):
            continue
        sma50 = sum(c[i - 49:i + 1]) / 50
        if c[i] <= sma50:
            continue
        adr_i = sum(hi[j] - lo[j] for j in range(i - 19, i + 1)) / 20
        pullbacks += 1
        mas = {"sma10": sum(c[i - 9:i + 1]) / 10, "sma20": sum(c[i - 19:i + 1]) / 20, "sma50": sma50}
        tested = [k for k, v in mas.items() if lo[i] <= v + BAND * adr_i and c[i] >= v]
        if not tested:
            no_ma += 1
            continue
        tests[min(tested, key=lambda k: mas[k])] += 1
    rk = tests.most_common()
    label = "none"
    if rk and rk[0][1] >= HAB_MIN_TESTS and (len(rk) == 1 or rk[0][1] > rk[1][1]):
        label = rk[0][0]
    why = None
    if len(H_) < 54:
        why = "history<54"
    elif label == "none":
        why = "tests<3_or_tie"
    return {"hab": label, "hab_why": why, "hab_pre_sessions": len(H_), "hab_pullbacks": pullbacks,
            "hab_no_ma": no_ma, "hab_tests": ";".join(f"{k}:{v}" for k, v in sorted(tests.items()))}


def hab_flags(ma, L, adr, hab):
    """matched_hab / mismatched (L near a different MA, not the habitual one) for one fire."""
    if hab == "none":
        return None, None
    m = near(ma.get(hab), L, adr)
    others = [k for k in ("sma10", "sma20", "ema21", "sma50") if k != hab and not (hab == "sma20" and k == "ema21")]
    mis = (not m) and any(near(ma.get(k), L, adr) for k in others)
    return int(m), int(mis)


# ── load ───────────────────────────────────────────────────────────────────────────────────────────────

def load():
    alerts = rerun.load_alerts()
    camps = reentry.load_campaigns()
    fires = rerun.load_fires()
    daily = rerun.load_daily()
    runners = reentry.load_runners()
    from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS
    keys = {(a["ticker"], a["ep_date"].isoformat()) for a in alerts}
    labelled = {(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS if (e.ticker, e.alert_date) in keys}
    for f in fires:
        f["split"] = split_of(f["ep_date"], f["era"])
        f["week"] = week_of(f["fire_date"])
    return alerts, camps, fires, daily, runners, labelled


def ctx_for(a, camps, daily):
    bars = daily[a["ticker"]]
    epb = bars.get(a["ep_date"]) or {}
    return {"tkr": a["ticker"], "ep": a["ep_date"], "bars": bars, "ordered": sorted(bars),
            "gl": epb.get("low_price"), "gc": epb.get("close"), "gh": epb.get("high_price"),
            "adr": camps[(a["ticker"], a["ep_date"])]["adr_dollar"]}


# ── Part A flags ───────────────────────────────────────────────────────────────────────────────────────

def part_a_rows(fires, daily, habs):
    rows = []
    for f in fires:
        bars = daily[f["ticker"]]
        ordered = sorted(bars)
        cl = closes_before(bars, ordered, f["fire_date"])
        ma = mas_from(cl)
        ma_af = mas_from(cl + [f["entry"]])
        lvl_name = LEVEL_OF[f["rung"]]
        L = f[lvl_name] if lvl_name else None
        adr = f["adr_dollar"]
        hb = habs[(f["ticker"], f["ep_date"])]
        r = {"part": "A", "ticker": f["ticker"], "ep_date": f["ep_date"].isoformat(), "era": f["era"], "split": f["split"],
             "month": f["ep_date"].isoformat()[:7], "week": f["week"], "rung": f["rung"], "fire_date": f["fire_date"].isoformat(),
             "session_idx": f["session_idx"], "bucket": bucket(f["session_idx"]), "source": f["source"], "entry": f["entry"],
             "stop": f["stop"], "adr": adr, "level_kind": lvl_name or "n/a", "level": L,
             "n_closes": ma["n_closes"], "sma10": ma["sma10"], "sma20": ma["sma20"], "ema21": ma["ema21"], "sma50": ma["sma50"],
             "hab": hb["hab"]}
        if L is None:
            r["status"] = "no_level"
        elif ma["sma20"] is None and ma["ema21"] is None:
            r["status"] = "no_history"
        else:
            r["status"] = "ok"
            r["d_sma20_adr"] = (ma["sma20"] - L) / adr if ma["sma20"] is not None else None
            r["d_ema21_adr"] = (ma["ema21"] - L) / adr if ma["ema21"] is not None else None
            r["m_sma20"] = int(near(ma["sma20"], L, adr)) if ma["sma20"] is not None else None
            r["m_ema21"] = int(near(ma["ema21"], L, adr)) if ma["ema21"] is not None else None
            r["m_either"] = int(bool(r["m_sma20"]) or bool(r["m_ema21"]))
            r["m_either_atfire"] = int(near(ma_af["sma20"], L, adr) or near(ma_af["ema21"], L, adr))
            r["m_hab"], r["mis_hab"] = hab_flags(ma, L, adr, hb["hab"])
        rows.append(r)
    return rows


# ── Part B: the 20/21-DMA reclaim fire (daily grade, entry at the close) ───────────────────────────────

def ma_fire(ctx):
    bars, ordered, ep, adr = ctx["bars"], ctx["ordered"], ctx["ep"], ctx["adr"]
    if adr is None or adr <= 0 or ctx["gc"] is None:
        return {"status": "no_adr_or_ep_bar"}
    sess = sessions_after(ep, 20)
    ma0 = mas_from(closes_before(bars, ordered, sess[0])) if sess else None
    if not sess:
        return {"status": "no_sessions"}
    if ma0["sma20"] is None:
        return {"status": "no_history"}
    zone_hi0 = max(v for v in (ma0["sma20"], ma0["ema21"]) if v is not None)
    if not (ctx["gc"] > zone_hi0):
        return {"status": "ep_close_not_above_ma"}
    for s_idx, d in enumerate(sess, start=1):
        b = bars.get(d)
        if not b or None in (b["low_price"], b["close"], b["high_price"]):
            return {"status": "hole_before_fire", "hole": d.isoformat()}
        ma = mas_from(closes_before(bars, ordered, d))
        touched = {k: ma[k] for k in ("sma20", "ema21") if ma[k] is not None and b["low_price"] <= ma[k] <= b["close"]}
        if touched:
            lvl_k = max(touched, key=lambda k: touched[k])
            return {"status": "fire", "s_idx": s_idx, "fire_date": d, "entry": b["close"], "stop": b["low_price"],
                    "lvl_k": lvl_k, "level": touched[lvl_k], "touched": ",".join(sorted(touched)), "ma": ma,
                    "touched_vals": touched}
    return {"status": "no_fire_in_20"}


def h2_walk(ctx, entry, y, after, bound="pess"):
    """H2's at-the-close walk VERBATIM (hyptests_run.h2_rows.walk with no day-0 bars)."""
    bars = [((ctx["bars"][d]["high_price"], ctx["bars"][d]["low_price"]) if d in ctx["bars"] and ctx["bars"][d]["high_price"] is not None else None) for d in after]
    ev, idx = p2_probe.first_passage(bars, entry, entry - y, entry + 2 * y, bound)
    return p2_probe.at_checkpoint(ev, idx, 10, 0)


def yard(ctx, sess, s_idx):
    """H2's scaled yardstick VERBATIM: mean(high-low) over post-EP sessions max(1, s-2)..s."""
    rng = []
    for j in range(max(1, s_idx - 2), s_idx + 1):
        b = ctx["bars"].get(sess[j - 1])
        if not b or b["high_price"] is None:
            return None
        rng.append(b["high_price"] - b["low_price"])
    return sum(rng) / len(rng) if rng else None


def settle_close(ctx, entry, stop, fire_date):
    """compute_settlement (via reentry.settle_attempt) with the entry at the fire session's CLOSE: fm = 15:59 and
    a post-fire 5-min list that is EMPTY (fetched fine, nothing after the fire) — day 0 can only trail-exit at the
    close, never stop. Gaps charged at the open (hyptests.gap_charge)."""
    if stop is None or stop >= entry or stop <= 0:
        return {"status": "killed"}
    dummy = {(ctx["tkr"], fire_date): [{"m": 955, "o": entry, "h": entry, "l": entry, "c": entry}]}
    res = reentry.settle_attempt(ctx, dummy, entry, stop, fire_date, 959, HORIZON)
    if res["status"] not in ("settled", "marked"):
        return {"status": "abstain", "why": res.get("reason")}
    out = {"status": res["status"]}
    for arm in ("none", "trail"):
        out[arm] = gap_charge(ctx, res, entry, stop, arm)
    return out


def part_b_rows(alerts, camps, daily, habs, with_outcomes):
    rows = []
    for a in alerts:
        ctx = ctx_for(a, camps, daily)
        fx = ma_fire(ctx)
        hb = habs[(a["ticker"], a["ep_date"])]
        r = {"part": "B", "ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"],
             "split": split_of(a["ep_date"], a["era"]), "month": a["ep_date"].isoformat()[:7], "rung": "ma20_21_reclaim",
             "status": fx["status"], "adr": ctx["adr"], "ep_low": ctx["gl"], "ep_close": ctx["gc"], "hab": hb["hab"]}
        if fx["status"] == "fire":
            adr = ctx["adr"]
            lv = fx["level"]
            ma = fx["ma"]
            r.update({"fire_date": fx["fire_date"].isoformat(), "week": week_of(fx["fire_date"]), "session_idx": fx["s_idx"],
                      "bucket": bucket(fx["s_idx"]), "entry": fx["entry"], "stop": fx["stop"], "level": lv, "lvl_k": fx["lvl_k"],
                      "touched": fx["touched"], "n_closes": ma["n_closes"], "sma10": ma["sma10"], "sma20": ma["sma20"],
                      "ema21": ma["ema21"], "sma50": ma["sma50"],
                      "d_eplow_adr": (lv - ctx["gl"]) / adr, "d_epclose_adr": (lv - ctx["gc"]) / adr})
            tv = fx["touched_vals"]
            r["m_either"] = int(any(near(v, ctx["gl"], adr) or near(v, ctx["gc"], adr) for v in tv.values()))
            r["m_eplow_only"] = int(any(near(v, ctx["gl"], adr) for v in tv.values()))
            r["m_sma20"] = int(near(tv["sma20"], ctx["gl"], adr) or near(tv["sma20"], ctx["gc"], adr)) if "sma20" in tv else None
            r["m_ema21"] = int(near(tv["ema21"], ctx["gl"], adr) or near(tv["ema21"], ctx["gc"], adr)) if "ema21" in tv else None
            r["m_hab"], r["mis_hab"] = hab_flags(ma, lv, adr, hb["hab"])
            if r["stop"] >= r["entry"]:
                r["status"] = "killed_entry_eq_stop"
            if with_outcomes and r["status"] == "fire":
                after = sessions_after(fx["fire_date"], 20)
                r["n_after"] = len(after)
                if len(after) >= 10:
                    r["o_orig"] = h2_walk(ctx, fx["entry"], adr, after)
                    sess = sessions_after(ctx["ep"], 20)
                    ys = yard(ctx, sess, fx["s_idx"])
                    r["o_scaled"] = h2_walk(ctx, fx["entry"], ys, after) if ys and ys > 0 else None
                for lab, stp in (("lane", fx["stop"]), ("adr100", fx["entry"] - adr)):
                    st = settle_close(ctx, fx["entry"], stp, fx["fire_date"])
                    r[f"{lab}_status"] = st["status"]
                    if st["status"] in ("settled", "marked"):
                        r[f"{lab}_trail_r"] = st["trail"][1]
                        r[f"{lab}_none_r"] = st["none"][1]
                        r[f"{lab}_trail_outcome"] = st["trail"][0]
                r["stop_w_pct"] = (fx["entry"] - fx["stop"]) / fx["entry"] * 100
                r["stop_w_adr"] = (fx["entry"] - fx["stop"]) / adr
        rows.append(r)
    return rows


def write(path, rows):
    cols = []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    with open(HERE / path, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows:
            fh.write("|".join("" if r.get(c) is None else (f"{r[c]:.6g}" if isinstance(r[c], float) else str(r[c])) for c in cols) + "\n")
    print(f"wrote {path}: {len(rows)} rows")


def phase_pop():
    alerts, camps, fires, daily, runners, labelled = load()
    habs = {(a["ticker"], a["ep_date"]): habitual(daily[a["ticker"]], sorted(daily[a["ticker"]]), a["ep_date"]) for a in alerts}
    A = part_a_rows(fires, daily, habs)
    B = part_b_rows(alerts, camps, daily, habs, with_outcomes=False)
    L = ["#327 H11 — POPULATION (no outcomes read). Splits: ERA A = alert < 2026-08-22 (DISC <= 08-14, HOA 08-15..08-21); ERA B >= 08-22.", ""]
    # gate
    ea = Counter(a["era"] for a in alerts)
    L.append(f"GATE: alerts {len(alerts)} (ERA A {ea['A']}, ERA B {ea['B']}); fires {len(fires)} (ERA A {sum(1 for f in fires if f['era']=='A')}, ERA B {sum(1 for f in fires if f['era']=='B')}); "
             f"runners {len(runners)}; labelled in the 277: {len(labelled)}")
    adr_mis = sum(1 for f in fires if abs((f['adr_dollar'] or 0) - (camps[(f['ticker'], f['ep_date'])]['adr_dollar'] or 0)) > 1e-9)
    L.append(f"      fires' adr_dollar == campaigns.tsv adr_dollar on {len(fires) - adr_mis} of {len(fires)}")
    L.append("")
    L.append("PART A — the 632 first fires")
    for sp in ("A", "DISC", "HOA", "B"):
        rr = [r for r in A if (r["era"] == "A" if sp == "A" else r["split"] == sp)]
        st = Counter(r["status"] for r in rr)
        ok = [r for r in rr if r["status"] == "ok"]
        L.append(f"  {sp:4s} fires {len(rr):3d}: ok {st['ok']} · no_level(high break) {st['no_level']} · no_history {st['no_history']} | "
                 f"SMA20 lacking {sum(1 for r in ok if r['sma20'] is None)} · EMA21 lacking {sum(1 for r in ok if r['ema21'] is None)} | "
                 f"matched either {sum(r['m_either'] for r in ok)} ({len({r['ticker'] for r in ok if r['m_either']})} names) · "
                 f"sma20 {sum(1 for r in ok if r['m_sma20'])} · ema21 {sum(1 for r in ok if r['m_ema21'])} · at-fire either {sum(r['m_either_atfire'] for r in ok)}")
    L.append("  no_history fires: " + ", ".join(f"{r['ticker']} {r['ep_date']} {r['rung']} ({r['n_closes']} closes)" for r in A if r["status"] == "no_history"))
    L.append("  EMA21-lacking ok fires: " + ", ".join(sorted({f"{r['ticker']} {r['ep_date']} ({r['n_closes']})" for r in A if r['status'] == 'ok' and r['ema21'] is None})))
    L.append("")
    L.append("  matched share by SESSION BUCKET (ERA A, ok fires; matched = either):")
    for b in ("s01-02", "s03-05", "s06-10", "s11+"):
        rr = [r for r in A if r["era"] == "A" and r["status"] == "ok" and r["bucket"] == b]
        m = sum(r["m_either"] for r in rr)
        L.append(f"    {b:7s} fires {len(rr):3d} | matched {m:3d} ({100*m/len(rr) if rr else 0:5.1f}%)")
    okA = [r for r in A if r["era"] == "A" and r["status"] == "ok"]
    mA = [r for r in okA if r["m_either"]]
    late = sum(1 for r in mA if r["session_idx"] >= 6)
    L.append(f"    matched fires at session 6+: {late} of {len(mA)} ({100*late/len(mA) if mA else 0:.1f}%)")
    L.append("  by rung (ERA A ok): " + " · ".join(f"{k} {sum(r['m_either'] for r in okA if r['rung']==k)}/{sum(1 for r in okA if r['rung']==k)}" for k in ("ep_low_reclaim", "ep_close_reclaim", "ep_close_620_prox")))
    for k in ("ep_low_reclaim", "ep_close_reclaim", "ep_close_620_prox"):
        ds = sorted(r["d_sma20_adr"] for r in okA if r["rung"] == k and r["d_sma20_adr"] is not None)
        if ds:
            L.append(f"    {k}: SMA20 minus level in ADR, median {statistics.median(ds):+.2f} (p10 {ds[len(ds)//10]:+.2f}, p90 {ds[9*len(ds)//10]:+.2f}) n {len(ds)}")
    L.append("")
    L.append("PART B — the 20/21-DMA reclaim fire, one per campaign (daily grade, entry at the close)")
    for sp in ("A", "DISC", "HOA", "B"):
        rr = [r for r in B if (r["era"] == "A" if sp == "A" else r["split"] == sp)]
        st = Counter(r["status"] for r in rr)
        fr = [r for r in rr if r["status"] == "fire"]
        L.append(f"  {sp:4s} campaigns {len(rr):3d}: " + " · ".join(f"{k} {v}" for k, v in sorted(st.items())) +
                 f" | matched (two-fold, EP low or close) {sum(r['m_either'] for r in fr)} · EP-low-only {sum(r['m_eplow_only'] for r in fr)}")
    L.append("  Part B fires by SESSION BUCKET (ERA A):")
    for b in ("s01-02", "s03-05", "s06-10", "s11+"):
        rr = [r for r in B if r["era"] == "A" and r["status"] == "fire" and r["bucket"] == b]
        m = sum(r["m_either"] for r in rr)
        L.append(f"    {b:7s} fires {len(rr):3d} | matched {m:3d}")
    L.append("  no_history / hole campaigns: " + ", ".join(f"{r['ticker']} {r['ep_date']} {r['status']}" for r in B if r["status"] in ("no_history", "hole_before_fire", "no_adr_or_ep_bar", "no_sessions")))
    L.append("")
    L.append("HABITUAL SUPPORT LABELS (one per campaign, strictly pre-EP)")
    for sp in ("A", "B"):
        rr = [habs[(a["ticker"], a["ep_date"])] for a in alerts if a["era"] == sp]
        L.append(f"  ERA {sp}: " + " · ".join(f"{k} {v}" for k, v in Counter(h["hab"] for h in rr).most_common()) +
                 f" | unlabelled why: {dict(Counter(h['hab_why'] for h in rr if h['hab'] == 'none'))}"
                 f" | pullback lows in uptrend per campaign: median {statistics.median([h['hab_pullbacks'] for h in rr])}")
    okAh = [r for r in A if r["era"] == "A" and r["status"] == "ok" and r["m_hab"] is not None]
    fb = [r for r in B if r["era"] == "A" and r["status"] == "fire" and r["m_hab"] is not None]
    L.append(f"  fires on LABELLED stocks, ERA A: Part A {len(okAh)} (matched_hab {sum(r['m_hab'] for r in okAh)}, mismatched {sum(r['mis_hab'] for r in okAh)}) · "
             f"Part B {len(fb)} (matched_hab {sum(r['m_hab'] for r in fb)}, mismatched {sum(r['mis_hab'] for r in fb)})")
    L.append("  matched_hab by bucket (ERA A, A+B): " + " · ".join(
        f"{b} {sum(r['m_hab'] for r in okAh + fb if r['bucket']==b)}/{sum(1 for r in okAh + fb if r['bucket']==b)}" for b in ("s01-02", "s03-05", "s06-10", "s11+")))
    txt = "\n".join(L) + "\n"
    (HERE / "h11_pop_out.txt").write_text(txt)
    print(txt)


def phase_run():
    alerts, camps, fires, daily, runners, labelled = load()
    habs = {(a["ticker"], a["ep_date"]): habitual(daily[a["ticker"]], sorted(daily[a["ticker"]]), a["ep_date"]) for a in alerts}
    A = part_a_rows(fires, daily, habs)
    # outcomes for Part A: hyp_rows_h2 (no recompute) + reentry attempt 1
    h2 = {}
    for r in rerun.read_tsv(HERE / "hyp_rows_h2.tsv"):
        if r["is_fire"] != "1" or r["bound"] != "pess":
            continue
        h2[(r["ticker"], r["ep_date"], r["pattern"], r["entry_kind"], r["barrier"])] = r["outcome"]
    a1 = load_reentry_attempt1()
    for r in A:
        for ek, bk, lab in (("rec", "orig", "o_orig"), ("rec", "scaled", "o_scaled"), ("fill", "orig", "o_fill")):
            r[lab] = h2.get((r["ticker"], r["ep_date"], r["rung"], ek, bk))
        for s, lab in (("incumbent", "lane"), ("adr_100", "adr100")):
            ref = a1.get((r["ticker"], r["ep_date"], r["rung"], s, "trail"))
            r[f"{lab}_status"] = ref["status"] if ref else None
            r[f"{lab}_trail_r"] = ref["r_gap"] if ref and ref["status"] in ("settled", "marked") else None
            # the none arm (stop or session-20 close) beside: Part B's trail arm exits AT an MA-reclaim close entry
            # by construction (close < max(SMA10, SMA20) on the entry bar), so the none arm is the like-for-like R
            refn = a1.get((r["ticker"], r["ep_date"], r["rung"], s, "none"))
            r[f"{lab}_none_r"] = refn["r_gap"] if refn and refn["status"] in ("settled", "marked") else None
        r["runner"] = int((r["ticker"], r["ep_date"]) in runners)
        r["labelled"] = int((r["ticker"], r["ep_date"]) in labelled)
    # ANCHOR: recompute H2's entry_kind=close rows (orig + scaled, pess) for every first fire with this file's walk
    lines, drift, n = [], 0, 0
    sess_cache = {}
    for f in fires:
        a = {"ticker": f["ticker"], "ep_date": f["ep_date"]}
        ctx = ctx_for(a, camps, daily)
        after = sessions_after(f["fire_date"], 20)
        if len(after) < 10:
            continue
        fb = ctx["bars"].get(f["fire_date"]) or {}
        if fb.get("close") is None:
            continue
        s_idx = f["session_idx"]
        sess = sess_cache.setdefault(f["ep_date"], sessions_after(f["ep_date"], 20))
        if s_idx is None:
            s_idx = next((i for i, d in enumerate(sess, start=1) if d == f["fire_date"]), None)
        for bk, y in (("orig", f["adr_dollar"]), ("scaled", yard(ctx, sess, s_idx) if s_idx else None)):
            if y is None or y <= 0:
                continue
            mine = h2_walk(ctx, fb["close"], y, after)
            ref = h2.get((f["ticker"], f["ep_date"].isoformat(), f["rung"], "close", bk))
            n += 1
            if ref != mine:
                drift += 1
                if len(lines) < 10:
                    lines.append(f"  DRIFT {f['ticker']} {f['ep_date']} {f['rung']} {bk}: mine {mine} ref {ref}")
    lines.insert(0, f"ANCHOR (Part B walk == H2's at-the-close walk on the 632 first fires): {n - drift} of {n} rows identical, drift {drift}")
    # settle_close spot check: a fire whose next session gaps below a 1xADR stop is charged at the open
    B = part_b_rows(alerts, camps, daily, habs, with_outcomes=True)
    for r in B:
        r["runner"] = int((r["ticker"], r["ep_date"]) in runners)
        r["labelled"] = int((r["ticker"], r["ep_date"]) in labelled)
    txt = "\n".join(lines) + "\n"
    (HERE / "h11_anchor_out.txt").write_text(txt)
    print(txt)
    write("h11_rows.tsv", A)
    write("h11_marows.tsv", B)
    hb_rows = [{"ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"], **habs[(a["ticker"], a["ep_date"])]} for a in alerts]
    write("h11_habitual.tsv", hb_rows)


if __name__ == "__main__":
    ph = sys.argv[1] if len(sys.argv) > 1 else "pop"
    {"pop": phase_pop, "run": phase_run}[ph]()
