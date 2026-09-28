#!/usr/bin/env python3
"""#684 ADDENDUM follow-up (descriptive only, NO new draw, NO new feature, NO permutation) — for each
of the same 63 registered features, the runner rate (frame B, runnerB5) favourable-tercile vs rest
AMONG FILLED ROWS ONLY, using the SAME discovery-cut points the frame-B run already used. Answers:
does a feature predict the FILL (mechanical — a name already running when the ORB forms is more likely
to trade back above it) or does it still separate outcomes ONCE a row has filled (a real continuation
read)? Writes orb_conditional_out.txt. Reads features.tsv + orb_outcomes.tsv only; no new prod pull."""
from __future__ import annotations

import csv
from pathlib import Path

from study import DRAWS, fav_mask, load_features, rate, tercile_cuts

HERE = Path(__file__).resolve().parent


def main() -> None:
    feats = load_features()
    outc = {}
    with (HERE / "orb_outcomes.tsv").open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            outc[(row["ticker"], row["scan_date"])] = row
    for r in feats:
        o = outc.get((r["ticker"], r["scan_date"]))
        r["orb_readable"] = int(o is not None and o["orb_readable"] == "1")
        r["filled"] = int(o["filled"]) if (o and o["filled"] not in ("", "None")) else None
        r["runnerB5"] = int(o["runnerB5"]) if (o and o["runnerB5"] not in ("", "None")) else None
        r["block2"] = o["block"] if o else None

    readable = [r for r in feats if r["orb_readable"]]
    disc = [r for r in readable if r["block2"] == "DISCOVERY"]
    filled = [r for r in readable if r["filled"] == 1 and r["runnerB5"] is not None]

    out = []
    p = out.append
    p(f"#684 conditional-on-fill descriptive (NO draw, NO permutation) — {len(filled)} filled rows with a computed frame-B outcome")
    p("feature | when | fav side | discovery cut (same as frame B) | ALL-READABLE frame B fav vs rest (already reported) | FILLED-ONLY frame B fav vs rest | gap shrinks?")
    for col, kind, fav, when, name in DRAWS:
        dr = [r for r in disc if r.get(col) is not None]
        if len(dr) < 30:
            continue
        cut = tercile_cuts([r[col] for r in dr]) if kind == "cont" else None
        # ALL-READABLE (both blocks), for reference — same as orb_results.tsv's frame-B numbers
        allr = [r for r in readable if r.get(col) is not None and r["runnerB5"] is not None]
        fm_all = fav_mask(allr, col, kind, fav, cut)
        lab_all = [r["runnerB5"] for r in allr]
        all_fav = rate([l for l, f in zip(lab_all, fm_all) if f])
        all_rest = rate([l for l, f in zip(lab_all, fm_all) if not f])
        all_n_fav = sum(fm_all)
        # FILLED-ONLY
        fr = [r for r in filled if r.get(col) is not None]
        if len(fr) < 20:
            p(f"{col} | {when} | {fav} | {cut} | {100*all_fav:.1f}%({all_n_fav}) vs {100*all_rest:.1f}%({len(allr)-all_n_fav}) | too few filled rows (n={len(fr)}) | -")
            continue
        fm_f = fav_mask(fr, col, kind, fav, cut)
        lab_f = [r["runnerB5"] for r in fr]
        f_fav = rate([l for l, f in zip(lab_f, fm_f) if f])
        f_rest = rate([l for l, f in zip(lab_f, fm_f) if not f])
        n_fav_f = sum(fm_f)
        all_diff = (all_fav - all_rest) if (all_fav is not None and all_rest is not None) else None
        f_diff = (f_fav - f_rest) if (f_fav is not None and f_rest is not None) else None
        shrinks = "n/a"
        if all_diff is not None and f_diff is not None:
            if all_diff <= 0:
                shrinks = "n/a (all-readable gap not positive)"
            else:
                shrinks = f"{'SHRINKS' if f_diff < 0.5*all_diff else 'PERSISTS'} ({100*f_diff:+.1f}pp filled-only vs {100*all_diff:+.1f}pp all-readable)"
        p(f"{col} | {when} | {fav} | {cut} | {100*all_fav:.1f}%({all_n_fav}) vs {100*all_rest:.1f}%({len(allr)-all_n_fav}) | "
          f"{100*f_fav:.1f}%({n_fav_f}) vs {100*f_rest:.1f}%({len(fr)-n_fav_f}) | {shrinks}")
    text = "\n".join(out) + "\n"
    (HERE / "orb_conditional_out.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
