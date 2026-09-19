"""#299 — the $0 free-feature separation check behind the tape-axis funding page.

READ-ONLY, OFFLINE. Runs on three CSVs captured ONCE from prod with the sibling
`_299_tape_free_features.sql` (CAPTURE ONCE, READ MANY):

    /tmp/299_high.csv   every score_tier='HIGH' row of mi_ep_alerts, joined to its 09:30-09:34
                        opening range (mi_intraday_bars), the scan tick's liquidity fields
                        (mi_ep_scan_log) and its settled outcomes (mi_signal_outcomes ep_alert)
    /tmp/299_daily.csv  mi_daily_closes OHLC for those tickers (ATR-14 reference)
    /tmp/299_bar1.csv   the 09:30 one-minute bar per alert day (the ORB bar the entry uses)

What it answers, without an LLM call: what would each tape feature the paid re-grade would add
(`tape_features.compute_or_atr` / the premarket-pace line / liquidity) have READ on the
operator-labelled EPs and on the whole HIGH population, and do any of them separate the labelled
EPs — or the 1-month tail — from the rest. Output is pasted into
docs/analysis/299_tape_axis_funding_page_2026-09-19.md.

Run from the repo root:  PYTHONPATH=. python3 scripts/probes/_299_tape_free_features.py
"""
import csv
import statistics as st
from collections import defaultdict
from datetime import date

from agents.market_intelligence.tape_features import build_tape, compute_or_atr
from shared.llm_models import effective_model, pricing_for

HIGH_CSV, DAILY_CSV, BAR1_CSV = "/tmp/299_high.csv", "/tmp/299_daily.csv", "/tmp/299_bar1.csv"
VIOLENT = 0.30          # the prompt's own threshold: ">~0.25-0.30 = a violent open"
STOP_WIDE_MULT = 1.5    # live entry rule: ORB (1-min) range > 1.5 x ATR -> setup:stop_too_wide
FIRST_ERA_CUT = date(2026, 8, 1)
SEP_SCORE_DATE = date(2026, 8, 22)   # rule_eras.SEP_SCORE_DATE — current admission era starts

# The operator's ground truth (docs/methodology/operator_labelled_eps.md). OR high/low for the
# three that never became alerts come from mi_intraday_bars directly (see the .sql).
LABELLED = [
    ("BFLY", date(2026, 6, 18), 8.015, 7.2006, "never alerted: catalyst graded routine"),
    ("PLTR", date(2026, 8, 4), None, None, "HIGH alert"),
    ("ABNB", date(2026, 8, 7), 171.56, 163.45, "never scored: top-20 gap cut"),
    ("TEAM", date(2026, 8, 7), None, None, "HIGH alert"),
    ("HTFL", date(2026, 8, 14), None, None, "HIGH alert"),
    ("MRNA", date(2026, 8, 19), None, None, "HIGH alert"),
    ("CHPT", date(2026, 9, 3), 7.65, 6.71, "never scored: market cap $134M"),
]


def f(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None


def q(vals, p):
    vals = sorted(v for v in vals if v is not None)
    return round(vals[min(len(vals) - 1, int(p * len(vals)))], 3) if vals else None


def pct_rank(vals, x):
    vals = sorted(v for v in vals if v is not None)
    return round(100 * sum(1 for v in vals if v <= x) / len(vals)) if vals and x is not None else None


def load():
    daily = defaultdict(list)
    for r in csv.DictReader(open(DAILY_CSV)):
        daily[r["ticker"]].append({"trade_date": date.fromisoformat(r["trade_date"]),
                                   "high_price": f(r["high_price"]), "low_price": f(r["low_price"]),
                                   "close": f(r["close"])})
    for t in daily:
        daily[t].sort(key=lambda d: d["trade_date"])
    bar1 = {(r["ticker"], date.fromisoformat(r["d"])): (f(r["b1_high"]), f(r["b1_low"]))
            for r in csv.DictReader(open(BAR1_CSV))}
    rows = list(csv.DictReader(open(HIGH_CSV)))
    return daily, bar1, rows


def prior_rows(daily, ticker, d, lookback=80):
    rows = [x for x in daily.get(ticker, []) if x["trade_date"] < d
            and x["high_price"] is not None and x["low_price"] is not None]
    return rows[-lookback:]


def atr14(daily, ticker, d):
    """Same ATR the tape feature uses: compute_or_atr(1.0-range) == 1/ATR."""
    inv = compute_or_atr(1.0, 0.0, prior_rows(daily, ticker, d))
    return (1.0 / inv) if inv else None


def build_population(daily, bar1, rows):
    first = {}
    for r in rows:  # FIRST HIGH row per ticker-day = the one that fired the alert + ORB order
        k = (r["ticker"], r["alert_date"])
        if k not in first or r["det_et"] < first[k]["det_et"]:
            first[k] = r
    pop = []
    for (t, d), r in sorted(first.items()):
        ad = date.fromisoformat(d)
        pr = prior_rows(daily, t, ad)
        oh, ol = f(r["or_high"]), f(r["or_low"])
        b1 = bar1.get((t, ad), (None, None))
        atr = atr14(daily, t, ad)
        pc = pr[-1]["close"] if pr else None
        adv = f(r["tick_adv"])
        pop.append(dict(
            ticker=t, d=ad, det=r["det_et"], gap=f(r["gap_pct"]), pm_rvol=f(r["pm_rvol"]),
            or_atr=compute_or_atr(oh, ol, pr) if oh is not None else None,
            b1_atr=compute_or_atr(b1[0], b1[1], pr) if b1[0] is not None else None,
            b1_range=(b1[0] - b1[1]) if b1[0] is not None else None, atr=atr,
            or_at_grade=(r["det_et"] >= "09:35"), tape_tier=r["tape_tier"] or None,
            judge=r["judge_tier"] or None, adv_usd=(adv * pc if adv and pc else None),
            f1m=f(r["fwd_1m_pct"]),
            era=("Aug22+" if ad >= SEP_SCORE_DATE else ("Aug1-21" if ad >= FIRST_ERA_CUT else "May-Jul"))))
    return pop


def tail(rows, label):
    v = [r["f1m"] for r in rows if r["f1m"] is not None]
    if not v:
        print(f"  {label:36} n=0")
        return
    big = sum(1 for x in v if x >= 20)
    print(f"  {label:36} n={len(v):3}  >=20%: {big:2} ({100 * big / len(v):.0f}%)  >=40%: "
          f"{sum(1 for x in v if x >= 40):2}  p90={q(v, .9):6}  median={round(st.median(v), 1):6}  "
          f"mean={round(st.mean(v), 1)}")


def main():
    daily, bar1, rows = load()
    pop = build_population(daily, bar1, rows)
    print(f"HIGH rows {len(rows)} -> {len(pop)} unique ticker-days (first HIGH row per day)")

    print("\n== OPENING RANGE AVAILABLE AT GRADE TIME (detected >= 09:35 ET), by era ==")
    for era in ("May-Jul", "Aug1-21", "Aug22+"):
        e = [p for p in pop if p["era"] == era]
        a = sum(1 for p in e if p["or_at_grade"])
        print(f"  {era:8} n={len(e):3}  OR-at-grade={a:3} ({100 * a / len(e):.0f}%)")
    a = sum(1 for p in pop if p["or_at_grade"])
    print(f"  ALL      n={len(pop)}  OR-at-grade={a} ({100 * a / len(pop):.0f}%)")

    print("\n== POPULATION PERCENTILES (unique HIGH ticker-days) ==")
    for k in ("or_atr", "b1_atr", "pm_rvol", "adv_usd", "gap"):
        vals = [p[k] for p in pop if p[k] is not None]
        print(f"  {k:8} n={len(vals):3}  p10={q(vals, .1)} p25={q(vals, .25)} p50={q(vals, .5)} "
              f"p75={q(vals, .75)} p90={q(vals, .9)}")
    v5 = [p["or_atr"] for p in pop if p["or_atr"] is not None]
    v1 = [p["b1_atr"] for p in pop if p["b1_atr"] is not None]
    print(f"  5-min OR/ATR > {VIOLENT} ('violent open' per the prompt): {sum(1 for v in v5 if v > VIOLENT)}/{len(v5)}")
    print(f"  1-min ORB bar/ATR > {VIOLENT}: {sum(1 for v in v1 if v > VIOLENT)}/{len(v1)}   "
          f"> {STOP_WIDE_MULT} (the live stop_too_wide entry rule): {sum(1 for v in v1 if v > STOP_WIDE_MULT)}/{len(v1)}")

    print("\n== LABELLED EPs — what each free feature would have read ==")
    popd = {(p["ticker"], p["d"]): p for p in pop}
    for t, d, oh, ol, note in LABELLED:
        p = popd.get((t, d))
        pr = prior_rows(daily, t, d)
        b1 = bar1.get((t, d), (None, None))
        b1a = compute_or_atr(b1[0], b1[1], pr) if b1[0] is not None else None
        if p:
            oa, pmr, det, tt, adv, f1m = p["or_atr"], p["pm_rvol"], p["det"], p["tape_tier"], p["adv_usd"], p["f1m"]
        else:
            oa, pmr, det, tt, adv, f1m = compute_or_atr(oh, ol, pr), None, None, None, None, None
        tape = build_tape(or_atr=None if (det and det < "09:35") else oa,
                          pm_vol_curve=(f"{pmr:.1f}x the premarket baseline by {det} ET" if pmr else None))
        print(f"  {t:5} {d} det={det} [{note}]")
        print(f"        5-min OR/ATR={oa} (pop pct {pct_rank(v5, oa)})  1-min bar/ATR={b1a} (pop pct {pct_rank(v1, b1a)})"
              f"  ATR=${atr14(daily, t, d):.2f}  pm_rvol={pmr} (pop pct {pct_rank([p['pm_rvol'] for p in pop], pmr)})"
              f"  tape_tier={tt}  advUSD={None if adv is None else str(round(adv / 1e6)) + 'M'}  fwd_1m={f1m}")
        print(f"        judge would see AT GRADE TIME: {tape}")

    print("\n== TAIL-FIRST OUTCOME CUTS (1-month close-to-close return, no stop) ==")
    for era in ("ALL", "May-Jul", "Aug1-21", "Aug22+"):
        e = [p for p in pop if era == "ALL" or p["era"] == era]
        print(f" -- era {era}  (n={len(e)}, with 1-month outcome={sum(1 for p in e if p['f1m'] is not None)})")
        w = [p for p in e if p["or_atr"] is not None]
        tail([p for p in w if p["or_atr"] <= VIOLENT], "5-min OR/ATR <= 0.30 (orderly)")
        tail([p for p in w if p["or_atr"] > VIOLENT], "5-min OR/ATR > 0.30 (violent)")
        w = [p for p in e if p["b1_atr"] is not None]
        tail([p for p in w if p["b1_atr"] <= STOP_WIDE_MULT], "1-min bar/ATR <= 1.5 (entry allowed)")
        tail([p for p in w if p["b1_atr"] > STOP_WIDE_MULT], "1-min bar/ATR > 1.5 (stop_too_wide)")
        m = q([p["pm_rvol"] for p in e], .5)
        w = [p for p in e if p["pm_rvol"] is not None]
        tail([p for p in w if p["pm_rvol"] <= m], f"pm_rvol <= era median {m}")
        tail([p for p in w if p["pm_rvol"] > m], f"pm_rvol > era median {m}")
        w = [p for p in e if p["tape_tier"]]
        tail([p for p in w if p["tape_tier"] == "tape_clean"], "tape_tier clean (existing fn)")
        tail([p for p in w if p["tape_tier"] != "tape_clean"], "tape_tier watch/junk (existing fn)")

    print("\n== OR/ATR TERTILES, all eras (robustness) ==")
    for key, label in (("or_atr", "5-min OR/ATR"), ("b1_atr", "1-min bar/ATR")):
        w = sorted([p for p in pop if p[key] is not None and p["f1m"] is not None], key=lambda p: p[key])
        n = len(w) // 3
        for i, third in enumerate(("low", "mid", "high")):
            seg = w[i * n:(i + 1) * n if i < 2 else None]
            tail(seg, f"{label} {third} third {seg[0][key]}-{seg[-1][key]}")

    print("\n== PRICING (pricing_for on today's judge model; tokens = measured p50 of live ep_grade_judge calls, last 45d) ==")
    m = effective_model("JUDGE_MODEL")
    pr = pricing_for(m)
    IN, OUT, TAPE_TOK = 5149, 477, 90
    per_call = (IN * pr["input"] + OUT * pr["output"]) / 1e6
    per_call_tape = ((IN + TAPE_TOK) * pr["input"] + OUT * pr["output"]) / 1e6
    print(f"  model={m} $/Mtok={pr}  per call: no-tape ${per_call:.4f}, with-tape ${per_call_tape:.4f} (measured p50 $0.0374)")
    n_all = len(pop)
    n_or = sum(1 for p in pop if p["or_at_grade"])
    aug = sum(1 for p in pop if FIRST_ERA_CUT <= p["d"] < date(2026, 9, 1))
    ongoing_wired = 12 * aug * TAPE_TOK * pr["input"] / 1e6          # +90 input tokens per live grade, 12 months
    ongoing_regrade = 12 * aug * per_call_tape                        # a second judge call per HIGH at 09:35, 12 months
    for label, n, reps in (("FULL  — every HIGH ticker-day, both arms x3", n_all, 3),
                           ("SCOPED — only rows graded after 09:35 (opening range existed), both arms x2", n_or, 2)):
        eval_cost = n * reps * (per_call + per_call_tape)
        rerun = n * 1 * per_call_tape                                  # post-wire re-run: with-tape arm once
        print(f"  {label}\n      rows={n} calls={n * 2 * reps}  eval=${eval_cost:.0f}  + post-wire re-run ${rerun:.0f}"
              f"  + 12mo ongoing ${ongoing_wired:.2f}  = WHOLE PATH ${eval_cost + rerun + ongoing_wired:.0f}")
    print(f"  (a 09:35 RE-GRADE design instead — a second judge call per HIGH — would run ${ongoing_regrade:.0f}/yr on Aug's {aug} HIGH/month)")


if __name__ == "__main__":
    main()
