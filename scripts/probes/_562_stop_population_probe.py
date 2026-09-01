"""#562/#327 follow-on — TWO operator-directed questions on the delayed-entry backfill.

Q1 (stops):  "stop for high break needs to be tighter" — replay the ep_high_break rung's
    48 recorded first-attempt fires (identical fires, identical entries) under several
    STOP BASES side by side, settled through the lane's own compute_settlement:
      a_prior_low   prior session's low — the INCUMBENT (delayed_entry_shadow.py:375/402)
      b_break_bar   the 5-min breakout bar's own low
      c_lod_at_fire low of day so far at the fire (the operator's TEAM stop basis)
      d_adr_{f}     entry − f×ADR$ for f in 0.25/0.50/0.75/1.00 (EP-anchored ADR$,
                    compute_ep_adr_dollar — the lane's own band input)
      e_ep_close    the EP-day close
    R is each variant's OWN R (risk = entry − variant stop) — analysis_standard §4.
    A stop at/above entry KILLS the fire (entry ≤ stop) — counted as a real cost, and
    the killed fire's incumbent outcome is shown. A variant whose stop cannot be
    established from stored bars ABSTAINS and is counted — never guessed.

Q2 (classify/table): the operator's population cut — "scope to EPs that we entered on
    first day but stopped out, those are the ones that broke ORB high vs those that
    didn't." Classify the 267 caught EPs from mi_live_trades (magna53 rows only, the
    acting lane: live row if one exists, else paper) + the ORB read
    (mi_intraday_bars 9:30–9:45 ET vs the post-9:45 session; daily-bar fallback is
    VALIDATED: over 215 full-coverage pairs the daily high never exceeds the RTH minute
    max by >0.2%, so daily high ≤ ORB high proves "never broke" and > proves "broke"):
      A  entered day 1, knocked out at the stop (final exit reason stop_hit)
      C  entered day 1, NOT stopped (open, trail exit, or other close)
      B  never entered, ORB high never broke
      D  never entered, but the ORB high DID break (cancelled/skipped/blocked — real,
         and NOT one of the operator's three buckets; reported separately, never guessed
         into A or B)
      U  unclassifiable — named, with the reason
    Then the whole per-rung table from _562bf_triggers.tsv re-run separately per group,
    MATURE fires only, both settlement arms, by month.

Reuses the 2026-09-01 backfill harness (`_562_backfill_replay.py`) and the lane's pure
functions — nothing re-implemented. Captured inputs (read-only SELECTs, captured once):
  _562bf_*.tsv                the backfill capture (alerts/daily/minute/mincov/triggers)
  _562sp_trades.tsv           magna53+9m rows, alert_date 2026-05-01..08-31
  _562sp_orb.tsv              per-campaign ORB(9:30–9:45) high/low + post-9:45 max high
  _562sp_extra_minutes.tsv    1-min bars for the 7 daily-grade fire days not in the
                              backfill's needed-pairs capture

Usage:
    python scripts/probes/_562_stop_population_probe.py stops     # Q1 → _562sp_stopvariants.tsv + report
    python scripts/probes/_562_stop_population_probe.py classify  # Q2 → _562sp_classification.tsv + report
    python scripts/probes/_562_stop_population_probe.py table     # Q2 per-rung tables by group

Throwaway diagnostic (scripts/probes/ convention). Read-only; writes only its own TSVs.
No thresholds touched, no live code, THE LINE intact.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _562_backfill_replay as bf  # noqa: E402  (the harness this card extends)
from agents.market_intelligence.delayed_entry_shadow import (  # noqa: E402
    RUNG_EP_HIGH,
    _trading_days,
    compute_settlement,
    to_rth_5min,
)

LAST = bf.LAST_DATA_DAY
_ALL_DAYS = None


def _mature(fire_date: date) -> bool:
    """20 post-fire sessions existed by the data horizon — settlement could have gone
    either way (the backfill's de-biasing cut, reused verbatim)."""
    global _ALL_DAYS
    if _ALL_DAYS is None:
        _ALL_DAYS = _trading_days(date(2026, 2, 15), LAST)
    return (len(_ALL_DAYS) - bisect_right(_ALL_DAYS, fire_date)) >= 20


def _stats(rs):
    rs = [r for r in rs if r is not None]
    if not rs:
        return "n=0"
    return (f"n={len(rs)} mean={statistics.mean(rs):+.2f} "
            f"med={statistics.median(rs):+.2f} sum={sum(rs):+.1f} "
            f"win={sum(1 for r in rs if r > 0) / len(rs) * 100:.0f}% "
            f">=4R={sum(1 for r in rs if r >= 4)}")


def load_extra_minutes():
    """The 7 extra fire-day pulls, same shape as the backfill's minute loader."""
    raw = defaultdict(list)
    p = HERE / "_562sp_extra_minutes.tsv"
    with open(p) as fh:
        rows = list(csv.reader(fh, delimiter="|"))
    hdr = rows[0]
    for r in rows[1:]:
        if len(r) != len(hdr):
            continue
        d = dict(zip(hdr, r))
        raw[(d["ticker"], date.fromisoformat(d["d"]))].append({
            "t": int(float(d["t_ms"])), "o": float(d["o"]), "h": float(d["h"]),
            "l": float(d["l"]), "c": float(d["c"]), "v": bf._f(d["v"]) or 0,
        })
    return {(t, dd): to_rth_5min(bars, dd) for (t, dd), bars in raw.items()}


# ── Q1: the stop-variant replay ────────────────────────────────────────────────────────

ADR_LADDER = (0.25, 0.50, 0.75, 1.00)
VARIANTS = (["a_prior_low", "b_break_bar", "c_lod_at_fire"]
            + [f"d_adr_{int(f * 100):03d}" for f in ADR_LADDER]
            + ["e_ep_close", "f_ep_low"])


def _contiguous_to(bars5, k):
    """True when the 5-min series starts at 9:30 and has no hole through index k —
    required before trusting a DERIVED first-touch bar or a day-so-far low."""
    if not bars5 or bars5[0]["m"] != 570:
        return False
    return all(bars5[i]["m"] - bars5[i - 1]["m"] == 5 for i in range(1, k + 1))


def phase_stops():
    alerts, daily = bf.load_alerts(), bf.load_daily()
    minutes, mincov = bf.load_minutes(), bf.load_mincov()
    minutes.update(load_extra_minutes())

    camps = [bf.walk_campaign(a, daily, minutes, mincov) for a in alerts]

    # fidelity check: the walk must reproduce the recorded trigger population exactly
    rec = bf.read_tsv("_562bf_triggers.tsv")
    got = sum(len(c["fires"]) for c in camps)
    rec_hb = {(r["ticker"], r["ep_date"], r["fire_date"]): (float(r["entry"]), float(r["stop"]))
              for r in rec if r["rung"] == RUNG_EP_HIGH}
    print(f"walk reproduction: {got} fires (recorded {len(rec)}); "
          f"high-break {sum(1 for c in camps for f in c['fires'] if f['rung'] == RUNG_EP_HIGH)} "
          f"(recorded {len(rec_hb)})")

    out_rows = []
    fires = []
    for c in camps:
        tkr, ep = c["ticker"], c["ep_date"]
        bars = daily.get(tkr, {})
        epb = bars[ep]
        gl, gc, gh = epb["low_price"], epb["close"], epb["high_price"]
        ordered = sorted(bars)
        for f in c["fires"]:
            if f["rung"] != RUNG_EP_HIGH:
                continue
            k_rec = rec_hb.get((tkr, ep.isoformat(), f["fire_date"].isoformat()))
            if k_rec is None or abs(k_rec[0] - f["entry"]) > 1e-6 or abs(k_rec[1] - f["stop"]) > 1e-6:
                print(f"  ⚠ reproduction mismatch {tkr} {ep} {f['fire_date']} — recorded {k_rec}, "
                      f"walked ({f['entry']}, {f['stop']})")
            fires.append((c, f, gl, gc, gh, ordered))

    for c, f, gl, gc, gh, ordered in fires:
        tkr, ep = c["ticker"], c["ep_date"]
        fire_date, entry = f["fire_date"], f["entry"]
        bars = daily[tkr]
        fb = bars.get(fire_date) or {}
        fire_day_bar = {"h": fb.get("high_price"), "l": fb.get("low_price"),
                        "c": fb.get("close")}
        adr = c["adr_dollar"]
        bars5 = minutes.get((tkr, fire_date), [])

        # locate the breakout bar (recorded minute fires carry it; daily-grade fires
        # derive the FIRST touch of the level from minutes, only when the series is
        # gap-free up to it — else the true first touch could hide in a hole: ABSTAIN)
        fm, k = f["fire_minute"], None
        derived = False
        if fm is not None:
            k = next((i for i, b in enumerate(bars5) if b["m"] == fm), None)
        elif bars5:
            k = next((i for i, b in enumerate(bars5) if b["h"] >= gh), None)
            if k is not None and _contiguous_to(bars5, k):
                fm, derived = bars5[k]["m"], True
            else:
                k = None
        b_stop = bars5[k]["l"] if k is not None else None
        c_stop = (min(b["l"] for b in bars5[:k + 1]) if k is not None else None)
        pre_fire_hole = (k is not None and not _contiguous_to(bars5, k))

        post5 = ([b for b in bars5 if b["m"] > fm] if fm is not None else None)
        sessions = _trading_days(fire_date + timedelta(days=1), LAST)
        closes_before = [bars[d]["close"] for d in ordered
                         if d < fire_date and bars[d]["close"] is not None]

        stops = {
            "a_prior_low": f["stop"],
            "b_break_bar": b_stop,
            "c_lod_at_fire": c_stop,
            "e_ep_close": gc,
            # f_ep_low — the EP DAY's own low, added 2026-09-01 when the operator asked
            # "did you also look at stop at the entry day low as stop?". Two readings of
            # that question: the low of the SESSION THE ENTRY FIRES is c_lod_at_fire, which
            # was already tested; this is the other one — the gap day's low, the level the
            # whole EP thesis is invalidated at, and the reference ep_low_reclaim uses.
            # Expect it WIDE, not tight, on a big gap day: measured, not assumed.
            "f_ep_low": gl,
        }
        for frac in ADR_LADDER:
            stops[f"d_adr_{int(frac * 100):03d}"] = (entry - frac * adr) if adr else None

        for name in VARIANTS:
            stop = stops[name]
            row = {"ticker": tkr, "ep_date": ep.isoformat(), "fire_date": fire_date.isoformat(),
                   "mon": ep.isoformat()[:7], "variant": name, "entry": entry, "stop": stop,
                   "mature": _mature(fire_date), "derived_touch": derived,
                   "pre_fire_hole": pre_fire_hole, "status": None}
            if stop is None:
                row["status"] = "abstain_no_stop_basis"
                out_rows.append(row)
                continue
            row["stop_w"] = (entry - stop) / entry * 100.0
            if stop >= entry:
                row["status"] = "killed_entry_le_stop"
                out_rows.append(row)
                continue
            res = compute_settlement(
                entry=entry, stop=stop, fire_minute=fm, fire_day_bar=fire_day_bar,
                post_fire_bars5=post5, sessions=sessions, bars_by_day=bars,
                closes_before_fire=closes_before)
            row["status"] = res["status"]
            if res["status"] == "settled":
                for kk in ("outcome", "realized_r", "outcome_trail", "realized_r_trail",
                           "mfe_r", "mae_r", "reached_4r"):
                    row[kk] = res.get(kk)
            else:
                row["reason"] = res.get("reason")
            out_rows.append(row)

    cols = ["ticker", "ep_date", "fire_date", "mon", "variant", "entry", "stop", "stop_w",
            "mature", "derived_touch", "pre_fire_hole", "status", "reason", "outcome",
            "realized_r", "outcome_trail", "realized_r_trail", "mfe_r", "mae_r", "reached_4r"]
    with open(HERE / "_562sp_stopvariants.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in out_rows:
            fh.write("|".join("" if r.get(kk) is None else str(r.get(kk)) for kk in cols) + "\n")
    print(f"{len(fires)} high-break fires x {len(VARIANTS)} variants -> "
          f"{len(out_rows)} rows written")
    _stops_report(out_rows)


def _stops_report(rows):
    by_v = defaultdict(list)
    for r in rows:
        by_v[r["variant"]].append(r)
    a_r = {(r["ticker"], r["ep_date"], r["fire_date"]): r.get("realized_r")
           for r in by_v["a_prior_low"] if r["status"] == "settled"}

    print("\n== Q1: ep_high_break under each stop basis — identical fires, own-R, "
          "MATURE settled only ==")
    for name in VARIANTS:
        vr = by_v[name]
        killed = [r for r in vr if r["status"] == "killed_entry_le_stop"]
        nostop = [r for r in vr if r["status"] == "abstain_no_stop_basis"]
        ab = [r for r in vr if r["status"] == "abstain"]
        settled = [r for r in vr if r["status"] == "settled"]
        mt = [r for r in settled if r["mature"]]
        ws = [r["stop_w"] for r in vr if r.get("stop_w") is not None and r["stop_w"] > 0]
        w_med = statistics.median(ws) if ws else float("nan")
        print(f"\n{name}: of 48 fires — killed {len(killed)}, no-stop-basis {len(nostop)}, "
              f"settle-abstain {len(ab)}, settled {len(settled)} "
              f"({len(mt)} mature); median stop width {w_med:.1f}%")
        print(f"  M-none : {_stats([r['realized_r'] for r in mt])}")
        print(f"  M-trail: {_stats([r['realized_r_trail'] for r in mt])}")
        t4 = sum(1 for r in mt if str(r.get("reached_4r")) == "True")
        print(f"  touched >=4R during the M-none hold (own-R MFE, pess): {t4}/{len(mt)}")
        for mon in ("2026-05", "2026-06", "2026-07", "2026-08"):
            ms = [r["realized_r"] for r in mt if r["mon"] == mon]
            n_im = sum(1 for r in vr if r["mon"] == mon and not r["mature"]
                       and r["status"] in ("settled", "abstain"))
            print(f"    {mon}: M-none {_stats(ms)}  immature={n_im}")
        if killed:
            ks = [(r["ticker"], r["ep_date"],
                   a_r.get((r["ticker"], r["ep_date"], r["fire_date"])))
                  for r in killed]
            print(f"  killed fires (incumbent M-none R in brackets): "
                  + ", ".join(f"{t} {e[:7]} [{x if x is None else format(x, '+.2f')}]"
                              for t, e, x in ks))

    print("\n== P14 both-directions: every fire the INCUMBENT harvested >= +2R (mature, "
          "M-none) — what each variant does on the same fire ==")
    movers = [r for r in by_v["a_prior_low"]
              if r["status"] == "settled" and r["mature"]
              and r.get("realized_r") is not None and r["realized_r"] >= 2]
    keymap = defaultdict(dict)
    for r in rows:
        keymap[(r["ticker"], r["ep_date"], r["fire_date"])][r["variant"]] = r
    hdr = "  {:6s} {:10s} ".format("ticker", "ep_date") + " ".join(f"{v:>12s}" for v in VARIANTS)
    print(hdr)
    for m in sorted(movers, key=lambda x: -x["realized_r"]):
        kk = (m["ticker"], m["ep_date"], m["fire_date"])
        cells = []
        for v in VARIANTS:
            r = keymap[kk].get(v, {})
            if r.get("status") == "settled":
                cells.append(f"{r['realized_r']:+11.2f}R")
            elif r.get("status") == "killed_entry_le_stop":
                cells.append(f"{'KILLED':>12s}")
            else:
                cells.append(f"{'abstain':>12s}")
        print("  {:6s} {:10s} ".format(m["ticker"], m["ep_date"]) + " ".join(cells))

    print("\n== and the reverse: fires a TIGHT variant banks >= +2R that the incumbent "
          "lost (mature) ==")
    for v in VARIANTS[1:]:
        wins = []
        for r in by_v[v]:
            if (r["status"] == "settled" and r["mature"]
                    and (r.get("realized_r") or 0) >= 2):
                ar = a_r.get((r["ticker"], r["ep_date"], r["fire_date"]))
                if ar is not None and ar < 2:
                    wins.append(f"{r['ticker']} {r['ep_date'][:7]} "
                                f"({r['realized_r']:+.1f}R vs incumbent {ar:+.1f}R)")
        print(f"  {v}: " + ("; ".join(wins) if wins else "none"))


# ── Q2: the population cut ─────────────────────────────────────────────────────────────


def _read_sp(name):
    with open(HERE / name) as fh:
        rows = list(csv.reader(fh, delimiter="|"))
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:] if len(r) == len(hdr)]


def phase_classify():
    alerts = bf.read_tsv("_562bf_alerts.tsv")
    daily = {(r["ticker"], r["trade_date"]): r for r in bf.read_tsv("_562bf_daily.tsv")}
    orb = {(r["ticker"], r["ep_date"]): r for r in _read_sp("_562sp_orb.tsv")}
    trades = [t for t in _read_sp("_562sp_trades.tsv") if t["signal_type"] == "magna53"]
    bypair = defaultdict(list)
    for t in trades:
        bypair[(t["ticker"], t["alert_date"])].append(t)

    out = []
    for a in alerts:
        k = (a["ticker"], a["alert_date"])
        rows = bypair.get(k, [])
        live = [r for r in rows if r["account_mode"] == "live"]
        acting = live if live else [r for r in rows if r["account_mode"] == "paper"]
        mode = "live" if live else ("paper" if acting else "none")
        ent = [r for r in acting if r["status"] in ("closed", "filled")]
        rec = {"ticker": k[0], "ep_date": k[1], "mon": k[1][:7], "mode": mode,
               "group": None, "sub": "", "detail": ""}

        if ent:
            t = ent[0]
            if t["status"] == "filled" or bf._f(t["remaining_shares"]):
                rec["group"], rec["sub"] = "C", "open"
            else:
                try:
                    exits = json.loads(t["exits"]) if t["exits"] not in ("", "\\N") else []
                except ValueError:
                    exits = []
                reasons = [x.get("reason", "") for x in exits]
                last = reasons[-1] if reasons else ""
                if last == "stop_hit":
                    rec["group"] = "A"
                    rec["sub"] = ("partial_then_stop" if "partial_profit" in reasons[:-1]
                                  else "pure_stop")
                    times = [x.get("time", "") for x in exits if x.get("reason") == "stop_hit"]
                    rec["detail"] = f"stop_date={times[-1][:10] if times else '?'}"
                elif last in ("sma_trail_stop", "partial_profit"):
                    rec["group"], rec["sub"] = "C", f"closed_{last}"
                else:
                    rec["group"], rec["sub"] = "U", "entered_unclassifiable_exit"
                    rec["detail"] = last or "no_exit_rows"
            out.append(rec)
            continue

        # never entered on the acting lane → the ORB-break read
        level_src, level = None, None
        row_oh = next((bf._f(r["orb_high"]) for r in rows if bf._f(r["orb_high"])), None)
        o = orb.get(k, {})
        min_oh = bf._f(o.get("orb_high")) if o.get("n_orb") not in (None, "0") else None
        if min_oh is not None:
            level_src, level = "minute_orb", min_oh    # the card's uniform instrument
        elif row_oh is not None:
            level_src, level = "trade_row", row_oh
        if level is None:
            rec["group"], rec["sub"] = "U", "no_orb_basis"
            rec["detail"] = "no trade-row orb_high and no 9:30-9:45 bars in mi_intraday_bars"
            out.append(rec)
            continue
        post = bf._f(o.get("post_orb_high")) if o.get("n_post") not in (None, "0") else None
        if post is not None:
            broke = post >= level
            rec["detail"] = f"{level_src}={level:.4g} post945_high={post:.4g}"
        else:
            # daily fallback — validated: daily high == RTH minute max (215 pairs, 0
            # exceedances >0.2%), so daily high above the ORB-window max proves a
            # post-window break and at-or-below proves none.
            d = daily.get(k)
            dh = bf._f(d["high_price"]) if d else None
            if dh is None:
                rec["group"], rec["sub"] = "U", "no_post_orb_evidence"
                rec["detail"] = "no post-9:45 bars and no daily bar"
                out.append(rec)
                continue
            broke = dh > level * 1.0001
            rec["detail"] = f"{level_src}={level:.4g} daily_high={dh:.4g} (daily fallback)"
        if broke:
            rec["group"] = "D"
            rec["sub"] = ("order_cancelled_unfilled"
                          if any(r["status"] == "cancelled" for r in acting) else "no_order")
        else:
            rec["group"] = "B"
            rec["sub"] = ("order_cancelled_unfilled"
                          if any(r["status"] == "cancelled" for r in acting) else "no_order")
        out.append(rec)

    cols = ["ticker", "ep_date", "mon", "mode", "group", "sub", "detail"]
    with open(HERE / "_562sp_classification.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in out:
            fh.write("|".join(str(r[c]) for c in cols) + "\n")

    print("== Q2 classification of the 267 caught EPs ==")
    print(Counter(r["group"] for r in out))
    for g in ("A", "B", "C", "D", "U"):
        gr = [r for r in out if r["group"] == g]
        print(f"\n{g} (n={len(gr)}): " + str(Counter(r["sub"] for r in gr))
              + "  modes " + str(Counter(r["mode"] for r in gr))
              + "  months " + str(Counter(r["mon"] for r in gr)))
        if g == "U":
            for r in gr:
                print(f"   {r['ticker']} {r['ep_date']}: {r['sub']} — {r['detail']}")


def phase_table():
    cls = {(r["ticker"], r["ep_date"]): r for r in _read_sp("_562sp_classification.tsv")}
    trigs = bf.read_tsv("_562bf_triggers.tsv")
    for t in trigs:
        t["realized_r"] = bf._f(t["realized_r"])
        t["realized_r_trail"] = bf._f(t["realized_r_trail"])
        t["mature"] = _mature(date.fromisoformat(t["fire_date"]))
        c = cls.get((t["ticker"], t["ep_date"]))
        t["group"] = c["group"] if c else "?"
        t["stop_date"] = (c["detail"].split("stop_date=")[1][:10]
                          if c and "stop_date=" in c["detail"] else None)
    rungs = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")

    for g, label in (("A", "entered day 1 AND knocked out at the stop"),
                     ("B", "never entered — the ORB high never broke"),
                     ("D", "never entered though the ORB high broke (blocked/unfilled)"),
                     ("C", "entered day 1, NOT stopped (open or non-stop close)")):
        camp = {k for k, r in cls.items() if r["group"] == g}
        gt = [t for t in trigs if t["group"] == g]
        print(f"\n== group {g} — {label} (campaigns n={len(camp)}) ==")
        mt_all = [t for t in gt if t["mature"] and t["settle_status"] == "settled"]
        print(f"  family: {len({(t['ticker'], t['ep_date']) for t in gt})} campaigns fired; "
              f"{len(gt)} fires, {len(mt_all)} mature settled")
        print(f"    M-none : {_stats([t['realized_r'] for t in mt_all])}")
        print(f"    M-trail: {_stats([t['realized_r_trail'] for t in mt_all])}")
        for mon in ("2026-05", "2026-06", "2026-07", "2026-08"):
            ms = [t["realized_r"] for t in mt_all if t["ep_date"][:7] == mon]
            n_im = sum(1 for t in gt if t["ep_date"][:7] == mon and not t["mature"])
            print(f"      {mon}: M-none {_stats(ms)}  immature={n_im}")
        for rung in rungs:
            rt = [t for t in mt_all if t["rung"] == rung]
            fired = len({(t["ticker"], t["ep_date"]) for t in gt if t["rung"] == rung})
            print(f"    {rung:20s} fired {fired}/{len(camp)}  "
                  f"M-none {_stats([t['realized_r'] for t in rt])}  "
                  f"M-trail {_stats([t['realized_r_trail'] for t in rt])}")
        tail = [t for t in mt_all if (t["realized_r"] or -9) >= 4
                or (t["realized_r_trail"] or -9) >= 4]
        if tail:
            print("    >=4R fires: " + "; ".join(
                f"{t['ticker']} {t['ep_date'][:7]} {t['rung']} "
                f"(none {t['realized_r']:+.1f} / trail {t['realized_r_trail']:+.1f})"
                for t in sorted(tail, key=lambda x: -(x["realized_r"] or -9))))

    # group A, the strict re-entry cut: only fires strictly AFTER the day-1 trade's stop
    print("\n== group A, STRICT re-entry cut — fires strictly after the day-1 stop date ==")
    a_after = [t for t in trigs if t["group"] == "A" and t["stop_date"]
               and t["fire_date"] > t["stop_date"] and t["mature"]
               and t["settle_status"] == "settled"]
    a_before = [t for t in trigs if t["group"] == "A" and t["stop_date"]
                and t["fire_date"] <= t["stop_date"]]
    print(f"  fires on/before the stop date (we were still IN the trade): {len(a_before)} "
          f"— excluded here")
    print(f"  M-none : {_stats([t['realized_r'] for t in a_after])}")
    print(f"  M-trail: {_stats([t['realized_r_trail'] for t in a_after])}")


if __name__ == "__main__":
    {"stops": phase_stops, "classify": phase_classify,
     "table": phase_table}[sys.argv[1]]()
