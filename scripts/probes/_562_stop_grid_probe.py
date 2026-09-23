"""#562/#327 — THE FULL ENTRY x STOP EXPECTANCY GRID over the 267-caught-EP backfill.

The operator's reframe (2026-09-01, verbatim): "we are not predicting anything, we're not
building a prediction engine here, we are building a trading system that can be risk
managed, we find entries and exits where we can manage risk properly and where we have
positive expected returns." The #545 selection test showed no fire-time fact picks the
winners; the stop-basis sweep (`_562_stop_population_probe.py` Q1) showed the stop moves
ep_high_break from -0.41R to +1.66R per fire — but that sweep ran for ONE of the four
buy signals. This probe runs it for ALL FOUR, on the identical 602 recorded first-attempt
fires of the 2026-09-01 backfill.

FIDELITY CONTRACT (extends `_562_backfill_replay.py` + `_562_stop_population_probe.py`):
  - The fire population is the backfill walk RE-RUN and verified to reproduce the
    recorded 602 triggers exactly (entry, stop, fire_date per fire) before anything
    is varied. Entries never change; only the stop does.
  - Every variant settles through the lane's own `compute_settlement`, both arms
    (M-none hard stop / M-trail = stop + MAX(SMA10,20) close-below exit). R is each
    variant's OWN R (risk = entry - variant stop) — analysis_standard §4.
  - A stop at/above entry KILLS the fire at birth (the lane's own fill-sanity rule:
    no stop exists below the buy) — counted as a real cost, with the incumbent's
    outcome on that fire shown (P14: what a basis kills matters as much as what it
    keeps).
  - A basis that cannot be established from stored bars ABSTAINS and is counted —
    never guessed, never a fabricated fill.
  - Maturity discipline inherited verbatim: expectancy is MATURE fires only (20
    post-fire sessions existed by 2026-08-31); immature settled rows are stops BY
    CONSTRUCTION and are never pooled.

STOP BASES (per fire; incumbent differs per rung — that IS the grid's point):
  incumbent   the lane's recorded stop: dip-low (ep_low_reclaim = low since undercut,
              ep_close_reclaim = low of dip), prior session low (ep_high_break),
              low-of-day-so-far at the cross (ep_close_620_prox)
  bar_low     the fire bar's own 5-min low (minute fires; daily-grade ep_high_break
              fires derive the first touch of the level, only when the 5-min series
              is gap-free through it — else ABSTAIN)
  lod_fire    low of day so far at the fire bar (== incumbent for 620_prox — asserted)
  prior_low   the prior session's daily low (== incumbent for ep_high_break — asserted)
  adr_{k}     entry - k x ADR$ for k in 0.25/0.50/0.75/1.00 (EP-anchored ADR$,
              compute_ep_adr_dollar — the lane's own band input)
  ep_close    the EP-day close (structurally AT/ABOVE many reclaim entries — the kill
              count is the finding, not a bug)
  ep_low      the EP-day low

Usage:
    python scripts/probes/_562_stop_grid_probe.py grid    # -> _562grid_rows.tsv
    python scripts/probes/_562_stop_grid_probe.py report  # aggregate tables to stdout

Throwaway diagnostic (scripts/probes/ convention). Read-only; consumes only the already
captured `_562bf_*` / `_562sp_extra_minutes.tsv` files — NO prod access at all. Writes
only its own TSV next to itself. No thresholds touched, no live code, THE LINE intact.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _562_backfill_replay as bf  # noqa: E402  (the harness this card extends)
import _562_stop_population_probe as sp  # noqa: E402  (reuses _mature/_contiguous_to/extra minutes)
from agents.market_intelligence.delayed_entry_shadow import (  # noqa: E402
    RUNG_620_PROX,
    RUNG_EP_CLOSE,
    RUNG_EP_HIGH,
    RUNG_EP_LOW,
    _trading_days,
    compute_settlement,
)

ADR_LADDER = (0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00)
VARIANTS = (["incumbent", "bar_low", "lod_fire", "prior_low"]
            + [f"adr_{int(f * 100):03d}" for f in ADR_LADDER]
            + ["ep_close", "ep_low"])
RUNGS = (RUNG_EP_LOW, RUNG_EP_CLOSE, RUNG_EP_HIGH, RUNG_620_PROX)
MONTHS = ("2026-05", "2026-06", "2026-07", "2026-08")


def phase_grid():
    alerts, daily = bf.load_alerts(), bf.load_daily()
    minutes, mincov = bf.load_minutes(), bf.load_mincov()
    minutes.update(sp.load_extra_minutes())

    camps = [bf.walk_campaign(a, daily, minutes, mincov) for a in alerts]

    # fidelity gate 1: the walk must reproduce the recorded trigger population exactly
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
            print(f"  ⚠ reproduction mismatch {k} — recorded {r}, "
                  f"walked ({f['entry']}, {f['stop']})")
    print(f"walk reproduction: {len(got)} fires (recorded {len(rec)}), mismatches {mism}")
    assert len(got) == len(rec) and mism == 0, "walk does not reproduce the record — STOP"

    out_rows = []
    inv_620 = inv_hb = 0
    for c in camps:
        tkr, ep = c["ticker"], c["ep_date"]
        bars = daily.get(tkr, {})
        epb = bars[ep]
        gl, gc, gh = epb["low_price"], epb["close"], epb["high_price"]
        ordered = sorted(bars)
        adr = c["adr_dollar"]
        for f in c["fires"]:
            fire_date, entry, rung = f["fire_date"], f["entry"], f["rung"]
            fb = bars.get(fire_date) or {}
            fire_day_bar = {"h": fb.get("high_price"), "l": fb.get("low_price"),
                            "c": fb.get("close")}
            bars5 = minutes.get((tkr, fire_date), [])

            # locate the fire bar. Minute fires carry it; daily-grade fires exist ONLY
            # for ep_high_break (a level touch — first h >= gh derives it, contiguity
            # required, sp's exact convention). Reclaim/620 logic is never re-derived.
            fm, k, derived = f["fire_minute"], None, False
            if fm is not None:
                k = next((i for i, b in enumerate(bars5) if b["m"] == fm), None)
            elif rung == RUNG_EP_HIGH and bars5:
                k = next((i for i, b in enumerate(bars5) if b["h"] >= gh), None)
                if k is not None and sp._contiguous_to(bars5, k):
                    fm, derived = bars5[k]["m"], True
                else:
                    k = None
            bar_low = bars5[k]["l"] if k is not None else None
            lod = min(b["l"] for b in bars5[:k + 1]) if k is not None else None
            pre_fire_hole = (k is not None and not sp._contiguous_to(bars5, k))
            prior = [x for x in ordered if x < fire_date]
            prior_low = bars[prior[-1]]["low_price"] if prior else None

            # internal-consistency gates (the lane's own definitions, checked not assumed)
            if rung == RUNG_620_PROX and lod is not None and abs(lod - f["stop"]) > 1e-6:
                inv_620 += 1
            if (rung == RUNG_EP_HIGH and prior_low is not None
                    and abs(prior_low - f["stop"]) > 1e-6):
                inv_hb += 1

            stops = {"incumbent": f["stop"], "bar_low": bar_low, "lod_fire": lod,
                     "prior_low": prior_low, "ep_close": gc, "ep_low": gl}
            for frac in ADR_LADDER:
                stops[f"adr_{int(frac * 100):03d}"] = (entry - frac * adr) if adr else None

            post5 = ([b for b in bars5 if b["m"] > fm] if fm is not None else None)
            sessions = _trading_days(fire_date + timedelta(days=1), bf.LAST_DATA_DAY)
            closes_before = [bars[d]["close"] for d in ordered
                             if d < fire_date and bars[d]["close"] is not None]

            for name in VARIANTS:
                stop = stops[name]
                row = {"ticker": tkr, "ep_date": ep.isoformat(),
                       "fire_date": fire_date.isoformat(), "mon": ep.isoformat()[:7],
                       "rung": rung, "variant": name, "entry": entry, "stop": stop,
                       "mature": sp._mature(fire_date), "derived_touch": derived,
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
                    for kk in ("outcome", "realized_r", "outcome_trail",
                               "realized_r_trail", "mfe_r", "mae_r", "reached_4r"):
                        row[kk] = res.get(kk)
                else:
                    row["reason"] = res.get("reason")
                out_rows.append(row)

    print(f"consistency: 620 lod==incumbent mismatches {inv_620}; "
          f"high-break prior_low==incumbent mismatches {inv_hb}")

    cols = ["ticker", "ep_date", "fire_date", "mon", "rung", "variant", "entry", "stop",
            "stop_w", "mature", "derived_touch", "pre_fire_hole", "status", "reason",
            "outcome", "realized_r", "outcome_trail", "realized_r_trail", "mfe_r",
            "mae_r", "reached_4r"]
    with open(HERE / "_562grid_rows.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in out_rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols)
                     + "\n")
    print(f"{len(got)} fires x {len(VARIANTS)} bases -> {len(out_rows)} rows written")

    # fidelity gate 2: the incumbent column must reproduce the recorded settlements
    rec_settled = {(r["ticker"], r["ep_date"], r["rung"], r["fire_date"]): bf._f(r["realized_r"])
                   for r in rec if r["settle_status"] == "settled"}
    bad = 0
    for r in out_rows:
        if r["variant"] != "incumbent" or r["status"] != "settled":
            continue
        want = rec_settled.get((r["ticker"], r["ep_date"], r["rung"], r["fire_date"]))
        if want is None or abs(want - r["realized_r"]) > 1e-6:
            bad += 1
            print(f"  ⚠ incumbent settlement drift {r['ticker']} {r['fire_date']} "
                  f"{r['rung']}: recorded {want}, grid {r['realized_r']}")
    print(f"incumbent-vs-recorded settlement drift: {bad} rows")


# ── report ─────────────────────────────────────────────────────────────────────────────


def _agg(rows, arm):
    rs = [r[arm] for r in rows if r.get(arm) is not None]
    if not rs:
        return None
    return {"n": len(rs), "mean": statistics.mean(rs), "med": statistics.median(rs),
            "sum": sum(rs), "win": sum(1 for x in rs if x > 0) / len(rs) * 100,
            "t4": sum(1 for x in rs if x >= 4)}


def _fmt(a):
    if a is None:
        return "n=0"
    return (f"n={a['n']:<3d} mean={a['mean']:+.2f} med={a['med']:+.2f} "
            f"sum={a['sum']:+7.1f} win={a['win']:3.0f}% >=4R={a['t4']}")


def phase_report():
    rows = bf.read_tsv("_562grid_rows.tsv")
    for r in rows:
        for c in ("realized_r", "realized_r_trail", "mfe_r", "stop_w"):
            r[c] = bf._f(r.get(c))
        r["mature"] = r["mature"] == "True"
        r["reached_4r"] = r.get("reached_4r") == "True"
    by = defaultdict(list)
    for r in rows:
        by[(r["rung"], r["variant"])].append(r)
    inc_r = {(r["ticker"], r["ep_date"], r["rung"], r["fire_date"]): r
             for r in rows if r["variant"] == "incumbent"}

    for rung in RUNGS:
        n_fires = len({(r["ticker"], r["ep_date"], r["fire_date"])
                       for r in rows if r["rung"] == rung})
        print(f"\n{'=' * 100}\n== {rung} — {n_fires} recorded fires, entry unchanged, "
              f"stop varied ==\n{'=' * 100}")
        for v in VARIANTS:
            vr = by[(rung, v)]
            killed = [r for r in vr if r["status"] == "killed_entry_le_stop"]
            killed_mt = [r for r in killed if r["mature"]]
            nob = [r for r in vr if r["status"] == "abstain_no_stop_basis"]
            ab = [r for r in vr if r["status"] == "abstain"]
            unsc = [r for r in vr if r["status"] == "unscoreable"]
            st = [r for r in vr if r["status"] == "settled"]
            mt = [r for r in st if r["mature"]]
            ws = [r["stop_w"] for r in vr if r.get("stop_w") is not None and r["stop_w"] > 0]
            wmed = statistics.median(ws) if ws else float("nan")
            print(f"\n{v}: killed {len(killed)} ({len(killed_mt)} mature) · no-basis "
                  f"{len(nob)} · settle-abstain {len(ab) + len(unsc)} · settled {len(st)} "
                  f"({len(mt)} mature) · med stop width {wmed:.1f}%")
            a_n, a_t = _agg(mt, "realized_r"), _agg(mt, "realized_r_trail")
            print(f"  M-none : {_fmt(a_n)}")
            print(f"  M-trail: {_fmt(a_t)}")
            xm = [r for r in mt if r["mon"] != "2026-05"]
            print(f"  ex-May M-none : {_fmt(_agg(xm, 'realized_r'))}")
            print(f"  ex-May M-trail: {_fmt(_agg(xm, 'realized_r_trail'))}")
            t4_touch = sum(1 for r in mt if r["reached_4r"])
            print(f"  touched >=4R in-hold (own-R MFE): {t4_touch}/{len(mt)} "
                  f"(harvested: none {a_n['t4'] if a_n else 0} / trail "
                  f"{a_t['t4'] if a_t else 0})")
            mline = []
            for mon in MONTHS:
                ms = _agg([r for r in mt if r["mon"] == mon], "realized_r")
                mline.append(f"{mon[-2:]}: {'—' if ms is None else format(ms['sum'], '+.1f') + 'R/n' + str(ms['n'])}")
            print(f"  monthly M-none sums: " + "  ".join(mline))
            if killed:
                names = []
                for r in sorted(killed, key=lambda x: -(inc_r.get((x['ticker'], x['ep_date'], x['rung'], x['fire_date']), {}).get('realized_r') or -9)):
                    i = inc_r.get((r["ticker"], r["ep_date"], r["rung"], r["fire_date"]), {})
                    ir = i.get("realized_r")
                    names.append(f"{r['ticker']} {r['ep_date'][:7]}"
                                 f"[{'' if ir is None else format(ir, '+.1f')}]")
                print(f"  killed (incumbent M-none R in brackets): " + ", ".join(names))

        # P14 both directions, per rung: what each basis does on the incumbent's winners
        movers = [r for r in by[(rung, "incumbent")]
                  if r["status"] == "settled" and r["mature"]
                  and (r.get("realized_r") or 0) >= 2]
        if movers:
            keymap = defaultdict(dict)
            for r in rows:
                if r["rung"] == rung:
                    keymap[(r["ticker"], r["ep_date"], r["fire_date"])][r["variant"]] = r
            print(f"\n  P14 — the incumbent's >=+2R fires under every basis:")
            print("  {:6s} {:8s}".format("ticker", "ep_mon")
                  + "".join(f"{v:>10s}" for v in VARIANTS))
            for m in sorted(movers, key=lambda x: -x["realized_r"]):
                kk = (m["ticker"], m["ep_date"], m["fire_date"])
                cells = []
                for v in VARIANTS:
                    r = keymap[kk].get(v, {})
                    if r.get("status") == "settled":
                        cells.append(f"{r['realized_r']:+9.1f}R")
                    elif r.get("status") == "killed_entry_le_stop":
                        cells.append(f"{'KILLED':>10s}")
                    else:
                        cells.append(f"{'abst':>10s}")
                print("  {:6s} {:8s}".format(m["ticker"], m["ep_date"][:7]) + "".join(cells))

    # family view: every fire, all four rungs, one basis at a time
    print(f"\n{'=' * 100}\n== FAMILY (all four rungs pooled, mature settled) — "
          f"kills counted per basis ==\n{'=' * 100}")
    print("{:12s} {:>6s} {:>6s} {:>28s} {:>28s}   {}".format(
        "basis", "killed", "abst", "M-none", "ex-May M-none", "M-trail / ex-May"))
    for v in VARIANTS:
        vr = [r for r in rows if r["variant"] == v]
        mt = [r for r in vr if r["status"] == "settled" and r["mature"]]
        killed = sum(1 for r in vr if r["status"] == "killed_entry_le_stop" and r["mature"])
        nob = sum(1 for r in vr if r["status"].startswith("abstain") and r["mature"])
        a = _agg(mt, "realized_r")
        x = _agg([r for r in mt if r["mon"] != "2026-05"], "realized_r")
        at = _agg(mt, "realized_r_trail")
        xt = _agg([r for r in mt if r["mon"] != "2026-05"], "realized_r_trail")
        f2 = lambda a: "n=0" if a is None else f"{a['mean']:+.2f}/{a['sum']:+.0f}R/n{a['n']}/4R:{a['t4']}"
        print(f"{v:12s} {killed:>6d} {nob:>6d} {f2(a):>28s} {f2(x):>28s}   "
              f"{f2(at)} / {f2(xt)}")


if __name__ == "__main__":
    {"grid": phase_grid, "report": phase_report}[sys.argv[1]]()
