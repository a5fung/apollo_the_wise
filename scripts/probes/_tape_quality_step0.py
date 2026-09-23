#!/usr/bin/env python3
"""Tape Quality Score (TQS) — structure tightness / character filter for EP setups (Fable design
2026-07-21, operator-aligned). Measures whether a name's PRE-GAP tape is tight/orderly vs.
wide-and-loose "penny gap-and-crap". READ-ONLY.

Key design points (operator: "EP itself creates large bars — don't over-pivot to remove what makes
an EP an EP"):
  - Window = the 20 sessions STRICTLY BEFORE the alert (the EP/gap day is excluded — a name is never
    penalised for its own thrust).
  - Per-bar primitive = NTR (intraday range %) = (high-low)/close*100. NOT gap-aware TR: an overnight
    gap that then trades tight intraday is orderly, only intraday travel counts. Price-level-free.
  - The discriminator is NOT max-bar. It is the SPIKE/REVERSAL count: a big bar that HOLDS = a legit
    thrust (fine); big bars that REVERSE and REPEAT = junk. Uses the 2nd-largest bar (bmr2) so a lone
    legit event bar (earnings / prior EP) can't trip it.

Verdict rule R1 (validated 6/6 on the operator-labelled cases + on the 467-row #331 cohort):
    junk  = spike_rev>=2 OR spike_ct>=4 OR bmr2>=3.0
    watch = (not junk) AND (spike_rev==1 OR spike_ct in {2,3} OR bmr2>=2.5)
    clean = otherwise ; unknown = <15 live bars (NEVER junk).

Run: docker exec apollo-market python scripts/probes/_tape_quality_step0.py
"""
from __future__ import annotations

import asyncio
import statistics
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
except IndexError:  # run from a flat path (e.g. /tmp) — rely on the container's PYTHONPATH
    pass
from agents.market_intelligence.db import get_pool  # noqa: E402

_WIN = 20
_SPIKE_K = 2.0          # a "spike" bar = NTR > K * median NTR
_HELD_CLOSE = 0.70      # close in outer 30% of its own range (in the bar's direction)
_GIVEBACK = 0.60        # a HELD bar keeps >= 40% of its range over the next 2 closes

_COHORT_SQL = """
    SELECT s.ticker, s.alert_date, o.fwd_5d_pct
    FROM mi_theme_axis_shadow s
    LEFT JOIN mi_ep_scan_outcomes o ON o.ticker=s.ticker AND o.scan_date=s.alert_date
    ORDER BY s.alert_date, s.ticker
"""
_BARS_SQL = """
    SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
    FROM mi_daily_closes WHERE ticker = ANY($1::text[]) ORDER BY ticker, trade_date
"""


def _live(b):
    return (b["volume"] or 0) > 0 and b["high_price"] is not None and b["low_price"] is not None \
        and b["close"] and float(b["high_price"]) > float(b["low_price"]) and float(b["close"]) > 0


def tape_quality(bars, alert_date):
    """Return the TQS dict for the 20 live sessions strictly before alert_date, or {'tier':'unknown'}."""
    pre = [b for b in bars if b["trade_date"] < alert_date]
    win = [b for b in pre[-_WIN:] if _live(b)]
    if len(win) < 15:
        return {"tier": "unknown", "n": len(win)}
    ntr = [(float(b["high_price"]) - float(b["low_price"])) / float(b["close"]) * 100 for b in win]
    med = statistics.median(ntr)
    if med <= 0:
        return {"tier": "unknown", "n": len(win)}
    spike_idx = [i for i, v in enumerate(ntr) if v > _SPIKE_K * med]
    held = rev = 0
    for i in spike_idx:
        b = win[i]
        h, l, c, o = float(b["high_price"]), float(b["low_price"]), float(b["close"]), \
            (float(b["open_price"]) if b["open_price"] else float(b["close"]))
        rng = h - l
        up = c >= o
        close_pos = (c - l) / rng if up else (h - c) / rng      # near-extreme in the bar's direction
        # give-back over the next 2 closes (last-bar spike: close-position only)
        giveback = 0.0
        nxt = [float(win[j]["close"]) for j in (i + 1, i + 2) if j < len(win)]
        if nxt:
            adverse = min(nxt) if up else max(nxt)
            giveback = (c - adverse) / rng if up else (adverse - c) / rng
        if close_pos >= _HELD_CLOSE and giveback < _GIVEBACK:
            held += 1
        else:
            rev += 1
    srt = sorted(ntr, reverse=True)
    bmr2 = (srt[1] / med) if len(srt) > 1 else (srt[0] / med)
    junk = rev >= 2 or len(spike_idx) >= 4 or bmr2 >= 3.0
    watch = (not junk) and (rev == 1 or len(spike_idx) in (2, 3) or bmr2 >= 2.5)
    tier = "tape_junk" if junk else "tape_watch" if watch else "tape_clean"
    whip = 2 * rev + 0.5 * held + max(0.0, bmr2 - 1.5)
    return {"tier": tier, "n": len(win), "ntr_med": med, "spike_ct": len(spike_idx),
            "held": held, "rev": rev, "bmr2": bmr2, "adr": statistics.mean(ntr), "whip": whip}


def _tier_stats(rows, key="fwd_5d_pct"):
    out = {}
    for t in ("tape_clean", "tape_watch", "tape_junk"):
        sub = [r for r in rows if r["tqs"]["tier"] == t]
        s = [r[key] for r in sub if r.get(key) is not None]
        if not sub:
            continue
        loss10 = sum(1 for v in s if v <= -10)
        loss5 = sum(1 for v in s if v <= -5)
        win5 = sum(1 for v in s if v >= 5)
        out[t] = dict(n=len(sub), settled=len(s),
                      avg=(sum(s) / len(s) if s else None),
                      med=(statistics.median(s) if s else None),
                      loss5=loss5, loss10=loss10, win5=win5)
    return out


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        cohort = [dict(r) for r in await conn.fetch(_COHORT_SQL)]
        tickers = sorted({r["ticker"] for r in cohort})
        bar_rows = await conn.fetch(_BARS_SQL, tickers)
    bars_by = defaultdict(list)
    for r in bar_rows:
        bars_by[r["ticker"]].append(dict(r))
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["trade_date"])

    for r in cohort:
        r["tqs"] = tape_quality(bars_by.get(r["ticker"], []), r["alert_date"])

    comp = [r for r in cohort if r["tqs"]["tier"] != "unknown"]
    print(f"TQS — cohort N={len(cohort)}, computable {len(comp)}\n")

    print("== Labelled-6 check (operator ground truth) ==")
    LAB = {("FCEL", "2026-06-24"): "clean", ("SHAZ", "2026-06-12"): "clean",
           ("CRML", "2026-04-27"): "clean", ("GLND", "2026-04-27"): "junk",
           ("HTCO", "2026-05-11"): "junk", ("HTCO", "2026-05-12"): "junk"}
    for r in cohort:
        k = (r["ticker"], str(r["alert_date"]))
        if k in LAB:
            q = r["tqs"]
            ok = "OK" if LAB[k] in q["tier"] else "*** MISMATCH ***"
            print(f"  {r['ticker']:<6}{k[1]}  -> {q['tier']:<11} "
                  f"(spk {q.get('spike_ct')} / {q.get('held')}H {q.get('rev')}R, bmr2 {q.get('bmr2',0):.1f}, "
                  f"adr {q.get('adr',0):.1f})  expect {LAB[k]}  {ok}")

    print("\n== Tier x fwd-5d ==")
    st = _tier_stats(comp)
    print(f"  {'tier':<12}{'n':>5}{'settled':>8}{'avg':>8}{'med':>8}{'loss<=-5':>9}{'loss<=-10':>10}{'win>=5':>8}")
    for t in ("tape_clean", "tape_watch", "tape_junk"):
        if t in st:
            s = st[t]
            print(f"  {t:<12}{s['n']:>5}{s['settled']:>8}{(s['avg'] or 0):>7.1f}%{(s['med'] or 0):>7.1f}%"
                  f"{s['loss5']:>9}{s['loss10']:>10}{s['win5']:>8}")

    # #331 fades ex-junk stratification (reuses the alignment classifier)
    try:
        from importlib import import_module
        step0 = import_module("scripts.probes._331_gap_alignment_step0")
        clf = getattr(step0, "classify", None)
    except Exception:
        clf = None
    if clf:
        print("\n== #331 fades_into_congestion: ALL vs ex-junk ==")
        for label, keep in (("ALL", lambda r: True),
                            ("ex-junk (tape_clean+watch)", lambda r: r["tqs"]["tier"] != "tape_junk")):
            sub = []
            for r in comp:
                if not keep(r) or r.get("fwd_5d_pct") is None:
                    continue
                d = clf(bars_by.get(r["ticker"], []), r["alert_date"], strict=False)
                if isinstance(d, dict) and d.get("marker") == "fades_into_congestion":
                    sub.append(r["fwd_5d_pct"])
            if sub:
                crash = sum(1 for v in sub if v <= -20)
                print(f"  fades {label:<28} n={len(sub):>3}  avg {sum(sub)/len(sub):>6.1f}%  "
                      f"crash(<=-20%) {crash} ({crash/len(sub)*100:.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
