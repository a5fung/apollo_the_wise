#!/usr/bin/env python3
"""#545 Phase 3 — the doc's tables, read from the ONE capture (_545p3_cells.tsv). $0, pure local.

Every table is PAIRED on a fixed cohort (the #2 discipline): a cell's row that is open at the
horizon carries its MARK (labelled), a row that abstains is dropped and counted. Nothing here
re-walks a campaign; it only aggregates what _545p3_sweep.py wrote.
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
TSV = HERE / "_545p3_cells.tsv"
MAY = "2026-05"
CTRL = "entry_minus_2r/orb/live"
STOPS = ["orb_low", "entry_minus_2r", "adr_0.5", "adr_0.75", "adr_1.0", "adr_1.25"]
RUNNERS = ["live", "breakeven", "live_trail_be", "hard", "sma10", "sma20", "atr1", "atr2",
           "gb25", "gb50", "t3", "t5", "t10", "t20"]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


rows = [l.rstrip("\n").split("|") for l in open(TSV)]
hdr = rows[0]
cells: dict[str, dict[str, dict]] = defaultdict(dict)
for r in rows[1:]:
    d = dict(zip(hdr, r))
    for k in ("realized_r", "pnl_adr", "mark_r", "leg2_r", "campaign_r", "stop_width_adr", "entry_px", "stop", "target"):
        d[k] = _f(d[k])
    d["partial_fired"] = d["partial_fired"] == "True"
    cells[d["cell"]][d["id"] or (d["ticker"] + d["alert_date"])] = d


def val(d):
    """settled R, or the MARK for an open row (labelled by the caller), else None."""
    if d["status"] == "settled":
        return d["campaign_r"] if d["campaign_r"] is not None else d["realized_r"]
    if d["status"] == "open_at_horizon":
        return d["mark_r"]
    return None


def p90(xs):
    xs = sorted(xs)
    return xs[max(0, int(round(0.9 * (len(xs) - 1))))] if xs else None


def agg(ds, label=""):
    settled = [d for d in ds if d["status"] == "settled"]
    opens = [d for d in ds if d["status"] == "open_at_horizon"]
    abst = [d for d in ds if d["status"] == "abstain"]
    xs = [val(d) for d in settled]
    ms = [d["mark_r"] for d in opens if d["mark_r"] is not None]
    adr = [d["pnl_adr"] for d in settled if d["pnl_adr"] is not None]
    if not xs:
        return f"| {label} | 0 | — | — | — | — | — | — | — | — | {len(opens)} / {sum(ms):+.1f} | {len(abst)} |"
    best = max(xs)
    return (f"| {label} | {len(xs)} | **{sum(xs):+.1f}** | {sum(1 for x in xs if x >= 4)} | "
            f"{sum(1 for x in xs if x >= 2)} | {p90(xs):+.2f} | {sum(xs) - best:+.1f} | "
            f"{st.mean(xs):+.2f} | {st.median(xs):+.2f} | {sum(1 for x in xs if x > 0) / len(xs):.0%} | "
            f"{(sum(adr) if adr else 0):+.1f} | {len(opens)} / {sum(ms):+.1f} | {len(abst)} |")


HDR = ("| cell | settled n | sum R | ≥4R | ≥2R | P90 | ex-best | mean | median | win | "
       "sum in ADR units | open n / marks | abstain |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def sub(ds, which):
    if which == "all":
        return ds
    if which == "ex_may":
        return [d for d in ds if d["alert_date"][:7] != MAY]
    if which == "aug":
        return [d for d in ds if d["alert_date"] >= "2026-08-01"]
    raise ValueError(which)


ctrl = cells[CTRL]
ctrl_settled = {k for k, d in ctrl.items() if d["status"] == "settled"}

print("## T1 — stop grid, target PINNED, live ladder (267 campaigns)\n")
for which in ("all", "ex_may", "aug"):
    print(f"\n**{which}**\n\n{HDR}")
    for s in STOPS:
        print(agg(sub(list(cells[f'{s}/orb/live'].values()), which), s))

print("\n## T1b — paired vs control (control's settled cohort), with the abstain bound\n")
print("| cell | pairs | dropped (abstain/open in cell) | ΔR sum | better | worse | Δ≥4R | "
      "if every dropped row were −1R: ΔR |\n|---|---|---|---|---|---|---|---|")
for s in STOPS:
    for frame in ("orb", "own"):
        key = f"{s}/{frame}/live"
        if key not in cells:
            continue
        c = cells[key]
        pairs = [(val(c[k]), val(ctrl[k])) for k in ctrl_settled if c[k]["status"] == "settled"]
        dropped = [k for k in ctrl_settled if c[k]["status"] != "settled"]
        d = [a - b for a, b in pairs]
        bound = sum(d) + sum(-1.0 - val(ctrl[k]) for k in dropped)
        print(f"| {key} | {len(pairs)} | {len(dropped)} | {sum(d):+.1f} | {sum(1 for x in d if x > 1e-9)} | "
              f"{sum(1 for x in d if x < -1e-9)} | {sum(1 for a,_ in pairs if a>=4) - sum(1 for _,b in pairs if b>=4):+d} | {bound:+.1f} |")

print("\n## T2 — the joint check: pinned target vs the stop's own-unit target (08-06 frame)\n")
print("| stop | frame | settled n | sum R | partials fired | ≥4R | ≥2R | sum in ADR units | open n / marks |\n|---|---|---|---|---|---|---|---|---|")
for s in STOPS:
    for frame in ("orb", "own"):
        key = f"{s}/{frame}/live"
        if key not in cells:
            continue
        ds = list(cells[key].values())
        se = [d for d in ds if d["status"] == "settled"]
        xs = [val(d) for d in se]
        op = [d for d in ds if d["status"] == "open_at_horizon"]
        adr = [d["pnl_adr"] for d in se if d["pnl_adr"] is not None]
        print(f"| {s} | {frame} | {len(xs)} | {sum(xs):+.1f} | {sum(1 for d in se if d['partial_fired'])} | "
              f"{sum(1 for x in xs if x>=4)} | {sum(1 for x in xs if x>=2)} | {sum(adr):+.1f} | "
              f"{len(op)} / {sum(d['mark_r'] or 0 for d in op):+.1f} |")

print("\n## T3 — runner rules on the PARTIAL-TAKER cohort (identical trades until the partial), marks included\n")
for s in ("entry_minus_2r", "orb_low", "adr_0.5"):
    live = cells[f"{s}/orb/live"]
    takers = {k for k, d in live.items() if d["status"] in ("settled", "open_at_horizon") and d["partial_fired"]}
    for which in ("all", "ex_may"):
        tk = {k for k in takers if k in sub(list(live.values()), which) and True}
        tk = {k for k in takers if (live[k]["alert_date"][:7] != MAY or which == "all")}
        print(f"\n**stop {s} · {which} · partial-takers n={len(tk)}** (R in the stop's own unit at equal dollar risk; "
              f"an open row carries its mark)\n")
        print("| runner | settled | open (marked) | sum R incl. marks | Δ vs live ladder | mean | median | win | ≥4R | "
              "scratches at +0.33 | worst |\n|---|---|---|---|---|---|---|---|---|---|---|")
        base = {k: val(live[k]) for k in tk}
        for rr in RUNNERS:
            c = cells.get(f"{s}/orb/{rr}")
            if not c:
                continue
            xs = {k: val(c[k]) for k in tk if c[k]["status"] in ("settled", "open_at_horizon") and val(c[k]) is not None}
            if not xs:
                continue
            v = list(xs.values())
            dlt = sum(xs[k] - base[k] for k in xs if base.get(k) is not None)
            print(f"| {rr} | {sum(1 for k in xs if c[k]['status']=='settled')} | "
                  f"{sum(1 for k in xs if c[k]['status']=='open_at_horizon')} | **{sum(v):+.1f}** | {dlt:+.1f} | "
                  f"{st.mean(v):+.2f} | {st.median(v):+.2f} | {sum(1 for x in v if x>0)/len(v):.0%} | "
                  f"{sum(1 for x in v if x>=4)} | {sum(1 for k in xs if abs(xs[k]-1/3)<0.02)} | {min(v):+.2f} |")

print("\n## T3b — stop × runner heat: sum R incl. marks on ALL entered campaigns (settled + open marks), pooled / ex-May\n")
print("| stop \\ runner | " + " | ".join(RUNNERS) + " |\n|---|" + "---|" * len(RUNNERS))
for which in ("all", "ex_may"):
    for s in STOPS:
        line = f"| {s} ({which}) |"
        for rr in RUNNERS:
            c = cells.get(f"{s}/orb/{rr}")
            if not c:
                line += " — |"
                continue
            ds = sub(list(c.values()), which)
            v = [val(d) for d in ds if val(d) is not None]
            g4 = sum(1 for x in v if x >= 4)
            line += f" {sum(v):+.0f} ({g4}) |"
        print(line)

print("\n## T4 — attempt 2 (one re-entry after a full stop-out), per-name accounting\n")
print("| stop | signal | stop-outs eligible | fired | second stops (≤−0.5R) | held ≥+0.5R | leg-2 sum | leg-2 ex-THC | "
      "campaign sum (settled) | same rows, 1 attempt | ex-May campaign vs 1-attempt | campaigns ≥4R (1-att) | worst per name |\n"
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for key in sorted(k for k in cells if "/x2:" in k):
    s, _, _, x = key.split("/")
    sig = x.split(":")[1]
    c = cells[key]
    base = cells[f"{s}/orb/live"]
    elig = [d for d in c.values() if d["status"] in ("settled", "open_at_horizon") and d["final_reason"] == "stop_hit" and not d["partial_fired"]]
    fired = [d for d in c.values() if d["attempts_fired"] == "2"]
    l2 = [d["leg2_r"] for d in fired if d["leg2_r"] is not None]
    l2x = [d["leg2_r"] for d in fired if d["leg2_r"] is not None and d["ticker"] != "THC"]
    camp = [d for d in c.values() if d["status"] == "settled"]
    cr = [d["campaign_r"] for d in camp]
    br = [base[d["id"]]["realized_r"] for d in camp if base[d["id"]]["status"] == "settled"]
    exm = [d for d in camp if d["alert_date"][:7] != MAY]
    exm_b = [base[d["id"]]["realized_r"] for d in exm if base[d["id"]]["status"] == "settled"]
    print(f"| {s} | {sig} | {len(elig)} | {len(fired)} | {sum(1 for x in l2 if x <= -0.5)} | {sum(1 for x in l2 if x >= 0.5)} | "
          f"**{sum(l2):+.1f}** | {sum(l2x):+.1f} | {sum(cr):+.1f} (n={len(cr)}) | {sum(br):+.1f} | "
          f"{sum(d['campaign_r'] for d in exm):+.1f} vs {sum(exm_b):+.1f} (n={len(exm)}) | "
          f"{sum(1 for x in cr if x>=4)} ({sum(1 for x in br if x>=4)}) | {min(cr):+.2f} |")

print("\n## T5 — where the ≥4R campaigns are (pinned frame, live ladder), by stop\n")
print("| stop | ≥4R campaigns (R) |\n|---|---|")
for s in STOPS:
    c = cells[f"{s}/orb/live"]
    big = sorted(((val(d), d["ticker"], d["alert_date"]) for d in c.values() if val(d) is not None and val(d) >= 4), reverse=True)
    print(f"| {s} | " + ", ".join(f"{t} {dt[5:]} {r:+.1f}" for r, t, dt in big) + " |")

print("\n## T6 — the adr_0.5 dropped rows: what the control did on the campaigns adr_0.5 could not settle\n")
c = cells["adr_0.5/orb/live"]
drop = [(ctrl[k]["ticker"], ctrl[k]["alert_date"], c[k]["reason"], val(ctrl[k])) for k in ctrl_settled if c[k]["status"] != "settled"]
print("| ticker | date | adr_0.5 status | control R |\n|---|---|---|---|")
for t, d, r, v in sorted(drop, key=lambda x: x[1]):
    print(f"| {t} | {d} | {r} | {v:+.2f} |")
print(f"\ncontrol R on those {len(drop)} rows: sum {sum(v for *_, v in drop):+.2f}; "
      f"if adr_0.5 had lost 1R on each: {-len(drop):+d}R")

print("\n## T1c — the RE-ADMITTED cut (P8: conditional on selection) — alerts the era-C scorer admits (142 of 267)\n")
for label, pop in (("admitted (142)", {k for k, d in ctrl.items() if d["admit"] == "admit"}),
                   ("admitted + float-band-undecided (186)", {k for k, d in ctrl.items() if d["admit"] != "reject"}),
                   ("rejected (81)", {k for k, d in ctrl.items() if d["admit"] == "reject"})):
    cs = {k for k in pop if ctrl[k]["status"] == "settled"}
    print(f"\n**{label}** — control settled {len(cs)}\n")
    print("| stop | settled | sum R | ≥4R | paired | ΔR vs live | if every dropped row were −1R | ΔADR-units (paired) | "
          "ex-May n / sum / ≥4R | Aug n / sum |\n|---|---|---|---|---|---|---|---|---|---|")
    for s in STOPS:
        c = cells[f"{s}/orb/live"]
        se = [d for k, d in c.items() if k in pop and d["status"] == "settled"]
        xs = [val(d) for d in se]
        xm = [val(d) for d in se if d["alert_date"][:7] != MAY]
        xa = [val(d) for d in se if d["alert_date"] >= "2026-08-01"]
        pairs = [k for k in cs if c[k]["status"] == "settled"]
        dl = [val(c[k]) - val(ctrl[k]) for k in pairs]
        dropped = [k for k in cs if c[k]["status"] != "settled"]
        bound = sum(dl) + sum(-1 - val(ctrl[k]) for k in dropped)
        dadr = [(c[k]["pnl_adr"] or 0) - (ctrl[k]["pnl_adr"] or 0) for k in pairs]
        print(f"| {s} | {len(xs)} | {sum(xs):+.1f} | {sum(1 for x in xs if x >= 4)} | {len(pairs)} | **{sum(dl):+.1f}** | "
              f"{bound:+.1f} | {sum(dadr):+.1f} | {len(xm)} / {sum(xm):+.1f} / {sum(1 for x in xm if x >= 4)} | "
              f"{len(xa)} / {sum(xa):+.1f} |")
adm = {k for k, d in ctrl.items() if d["admit"] == "admit"}
print("\n**ADR stops sitting INSIDE the opening range (stop above the ORB low), entered campaigns — all alerts and admitted**\n")
for s in STOPS[2:]:
    c = cells[f"{s}/orb/live"]
    for lab, pool in (("all alerts", set(c)), ("admitted", adm)):
        ent = [d for k, d in c.items() if k in pool and d["entered"] == "True" and d["stop"] and d["target"] and d["entry_px"]]
        n_in = sum(1 for d in ent if d["stop"] > d["entry_px"] - (d["target"] - d["entry_px"]) / 2 + 1e-9)
        print(f"- {s} ({lab}): {n_in} of {len(ent)} entered campaigns ({n_in / len(ent):.0%})")
print("\n**admitted: runner Δ vs the live ladder on partial-takers at the live stop**\n")
live = ctrl
tk = {k for k in adm if live[k]["status"] in ("settled", "open_at_horizon") and live[k]["partial_fired"]}
print(f"takers {len(tk)}, ex-May {sum(1 for k in tk if live[k]['alert_date'][:7] != MAY)}\n")
print("| runner | Δ pooled | worse | Δ ex-May (n) |\n|---|---|---|---|")
for rr in RUNNERS[1:]:
    c = cells[f"entry_minus_2r/orb/{rr}"]
    dl = {k: (val(c[k]) or 0) - (val(live[k]) or 0) for k in tk if val(c[k]) is not None}
    exm = {k: v for k, v in dl.items() if live[k]["alert_date"][:7] != MAY}
    print(f"| {rr} | {sum(dl.values()):+.1f} | {sum(1 for v in dl.values() if v < -1e-9)} of {len(dl)} | {sum(exm.values()):+.1f} ({len(exm)}) |")
