#!/usr/bin/env python3
"""Step 2 follow-up — is the one separating read (share of a subject's STRONG industry peers that
had gapped >= 9% in the prior month: his yes-labels median 24% vs never-alerted controls 11%)
a property of real themes, or of the single fortnight his 31 labels come from?

READ-ONLY, $0. Reads ONLY scripts/probes/_step2_theme_recall_rows.tsv (the step-2 probe's
per-subject output) — nothing is re-measured, no prod access, no engine call.

The measure is a property of the (industry, date) CELL, not of the name: it is computed on the
subject's industry peers as of date - 1, so two subjects in the same industry on the same day
carry the identical share (NXPI and SIMO, 2026-04-29, both 15 of 48). Every comparison below is
therefore shown twice — per labelled ROW (his 21 / 7) and per distinct CELL — and a same-date,
same-industry control is equal to the label by construction (stated, not computed).

Out: scripts/probes/_step2_reflexivity_datematch_out.txt
"""
from __future__ import annotations

import csv
import os
import statistics
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = os.path.join(HERE, "_step2_theme_recall_rows.tsv")
OUT = os.path.join(HERE, "_step2_reflexivity_datematch_out.txt")
SCAN_LOG_START = date(2026, 4, 13)
DROP = {"MANE", "NXPI", "AVTX"}     # the three named as carrying the 24%

LOG: list[str] = []


def say(s: str = "") -> None:
    LOG.append(s)
    print(s)


def q(xs) -> str:
    xs = sorted(xs)
    if not xs:
        return "n=0"
    f = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]  # noqa: E731
    return f"p25 {100 * f(0.25):.0f}% · median {100 * f(0.5):.0f}% · p75 {100 * f(0.75):.0f}% (n={len(xs)})"


def med(xs) -> float | None:
    return statistics.median(xs) if xs else None


def main() -> None:
    with open(ROWS) as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    for r in rows:
        r["d"] = date.fromisoformat(r["date"])
        r["n_strong"] = int(r["n_strong"]); r["n_strong_gap"] = int(r["n_strong_gap"]); r["n_data"] = int(r["n_data"])
        r["ok"] = r["src"] == "industry" and r["n_data"] >= 3 and r["n_strong"] > 0
        r["share"] = (r["n_strong_gap"] / r["n_strong"]) if r["ok"] else None
        r["cell"] = (r["group"], r["d"])

    Y = [r for r in rows if r["pop"] == "label:y" and r["ok"]]
    N = [r for r in rows if r["pop"] == "label:n" and r["ok"]]
    label_keys = {(r["ticker"], r["d"]) for r in rows if r["pop"].startswith("label:")}
    C = [r for r in rows if r["pop"] == "control" and r["themeless"] == "True" and r["ok"]]
    TA = [r for r in rows if r["pop"] == "alert" and r["themeless"] == "True" and r["d"] >= SCAN_LOG_START
          and r["ok"] and (r["ticker"], r["d"]) not in label_keys]

    def cells(pool):
        """One value per (industry, date) cell — the share is identical within a cell."""
        return {r["cell"]: r["share"] for r in pool}

    say("=== Step-2 follow-up: date-matched reflexivity read (from _step2_theme_recall_rows.tsv) ===")
    say("share = strong industry peers that gapped >=9% in the 20 sessions ending date-1 / strong peers; subjects "
        "with an industry, >=3 data-bearing peers and >=1 strong peer")
    ldates = sorted({r["d"] for r in Y + N})
    say(f"label dates: {ldates[0]} -> {ldates[-1]} ({len(ldates)} sessions); yes rows {len(Y)} (uncovered/unusable "
        f"{22 - len(Y)}), no rows {len(N)} (unusable {9 - len(N)})")

    say("\n## A. Pooled (as in the doc §8)")
    say(f"  his YES rows        {q([r['share'] for r in Y])}")
    say(f"  his NO rows         {q([r['share'] for r in N])}")
    say(f"  themeless alerts    {q([r['share'] for r in TA])}   (>=04-13, excluding the 31 labelled rows)")
    say(f"  themeless controls  {q([r['share'] for r in C])}   (whole span)")

    say("\n## B. Date-matched — controls and alerts drawn from the SAME sessions as his labels")
    Cd = [r for r in C if r["d"] in set(ldates)]
    TAd = [r for r in TA if r["d"] in set(ldates)]
    say(f"  his YES rows                     {q([r['share'] for r in Y])}")
    say(f"  his NO rows                      {q([r['share'] for r in N])}")
    say(f"  themeless alerts, same dates     {q([r['share'] for r in TAd])}")
    say(f"  themeless controls, same dates   {q([r['share'] for r in Cd])}")
    say("  -- the same, one value per (industry, date) CELL (the measure's true unit):")
    say(f"  YES cells                        {q(cells(Y).values())}")
    say(f"  NO cells                         {q(cells(N).values())}")
    say(f"  themeless-alert cells, same dates {q(cells(TAd).values())}")
    say(f"  control cells, same dates        {q(cells(Cd).values())}")
    lo, hi = ldates[0] - timedelta(days=7), ldates[-1] + timedelta(days=7)
    Cw = [r for r in C if lo <= r["d"] <= hi]
    say(f"  control cells, window +-1 week ({lo} -> {hi})  {q(cells(Cw).values())}")

    say("\n## C. Per-date paired read — each label row against the SAME-DAY control cells")
    cd_by_date = defaultdict(dict)
    for r in Cd:
        cd_by_date[r["d"]][r["cell"]] = r["share"]
    for lab, pool in (("YES", Y), ("NO", N)):
        above = below = tie = 0
        diffs = []
        for r in pool:
            ctl = list(cd_by_date[r["d"]].values())
            m = med(ctl)
            if m is None:
                continue
            diffs.append(r["share"] - m)
            above += r["share"] > m; below += r["share"] < m; tie += r["share"] == m
        say(f"  {lab}: rows above their same-day control median {above} · below {below} · tie {tie} (of {len(pool)}); "
            f"median (row - same-day control median) {100 * med(diffs):+.0f} pts" if diffs else f"  {lab}: no same-day controls")
    say("  per label row (share | same-day control cells: n, median | same-industry control same day?):")
    for r in sorted(Y + N, key=lambda x: (x["d"], x["pop"], x["ticker"])):
        ctl = cd_by_date[r["d"]]
        same_ind = r["cell"] in ctl
        say(f"    {r['pop'][-1].upper()} {r['ticker']:<5} {r['d']} {r['group'][:30]:<30} {r['n_strong_gap']:>2}/{r['n_strong']:>2} = "
            f"{100 * r['share']:3.0f}% | controls n={len(ctl):>2} median {100 * med(ctl.values()):3.0f}% | "
            f"{'same-industry control cell EXISTS (equal by construction)' if same_ind else 'no same-industry control that day'}")

    say("\n## D. Within his own sample — yes vs no in the SAME industry (the cell view)")
    by_ind = defaultdict(lambda: {"y": [], "n": []})
    for r in Y + N:
        by_ind[r["group"]][r["pop"][-1]].append(r)
    for ind, d in sorted(by_ind.items()):
        if d["y"] and d["n"]:
            say(f"  {ind}: YES " + ", ".join(f"{x['ticker']} {x['d'].strftime('%m-%d')} {100 * x['share']:.0f}%" for x in d["y"])
                + " | NO " + ", ".join(f"{x['ticker']} {x['d'].strftime('%m-%d')} {100 * x['share']:.0f}%" for x in d["n"]))
    say("  industries with only YES: " + ", ".join(f"{i} ({len(d['y'])})" for i, d in sorted(by_ind.items()) if d["y"] and not d["n"]))
    say("  industries with only NO:  " + ", ".join(f"{i} ({len(d['n'])})" for i, d in sorted(by_ind.items()) if d["n"] and not d["y"]))

    say("\n## E. Is the 24% carried by a few names?")
    Y2 = [r for r in Y if r["ticker"] not in DROP]
    say(f"  YES rows without {sorted(DROP)}: {q([r['share'] for r in Y2])}")
    say(f"  YES cells without them:          {q(cells(Y2).values())}")
    say("  YES rows by industry family: " + " · ".join(
        f"{fam} {q([r['share'] for r in Y if pred(r['group'])])}" for fam, pred in (
            ("biotech/med", lambda g: g in ("Biotechnology", "Medical Devices", "Diagnostics & Research")),
            ("semis/electronics/hardware", lambda g: g in ("Semiconductors", "Electronic Components", "Computer Hardware")),
            ("software", lambda g: g.startswith("Software")),
            ("other", lambda g: not (g in ("Biotechnology", "Medical Devices", "Diagnostics & Research", "Semiconductors",
                                            "Electronic Components", "Computer Hardware") or g.startswith("Software"))))))

    say("\n## F. The calendar — control-cell median share by week over the whole span (is that fortnight unusual?)")
    byw = defaultdict(dict)
    for r in C:
        wk = r["d"] - timedelta(days=r["d"].weekday())
        byw[wk][r["cell"]] = r["share"]
    for wk in sorted(byw):
        v = list(byw[wk].values())
        flag = "  <- label fortnight" if ldates[0] - timedelta(days=6) <= wk <= ldates[-1] else ""
        say(f"  week of {wk}: control cells {len(v):>3} · median {100 * med(v):3.0f}% · p75 {100 * sorted(v)[min(len(v) - 1, int(0.75 * len(v)))]:3.0f}%{flag}")

    with open(OUT, "w") as fh:
        fh.write("\n".join(LOG) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
