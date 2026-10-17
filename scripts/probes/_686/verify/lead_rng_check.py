#!/usr/bin/env python3
"""Why do the FROZEN L2 discovery drop-legs read 0.089 / 0.028 in the real read but 0.079 / 0.018 in the
registration + dry run? Hypothesis: one random.Random(687) is shared across L1's four legs and then L2's;
L1's 4th leg is the NEW block (63 rows in the dry run, 75 in the read), and random.shuffle's consumption
depends on the group sizes, so L2's frozen legs are drawn from a different part of the stream.
Imports the frozen read's functions (no main(), nothing written outside verify/). Run with
PYTHONDONTWRITEBYTECODE=1 so no __pycache__ lands next to the hashed files."""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import preregistered_read as R  # noqa: E402
study = R.study

study.HERE = R.P684
rows684 = study.load_features(); daily684 = study.load_daily()
study.add_outcomes(rows684, daily684); R.derive_alert_unscheduled(rows684)
scored = [r for r in rows684 if r["runner5"] is not None]
disc = [r for r in scored if r["block"] == "DISCOVERY"]
held = [r for r in scored if r["block"] == "HELD-OUT"]
adr_cut = study.tercile_cuts([r[R.ADR_CONTROL_COL] for r in disc if r.get(R.ADR_CONTROL_COL) is not None])

study.HERE = R.DATA686
new_all = study.load_features(); daily_new = study.load_daily()
study.add_outcomes(new_all, daily_new); R.derive_alert_unscheduled(new_all)
new = [r for r in new_all if r["runner5"] is not None]
best_week, best_two = "2026-W19", ["UMC", "CRSR"]
print(f"disc {len(disc)} held684 {len(held)} new block {len(new)} runners {sum(r['runner5'] for r in new)}")


def legs(rng, block_rows):
    out = {}
    for lead in R.LEADS:
        code, col, side, _ = lead
        cut = study.tercile_cuts([r[col] for r in disc if r.get(col) is not None])
        a = R.lead_leg(lead, disc, cut, adr_cut, rng)
        w = R.lead_leg(lead, [r for r in disc if r["iso_week"] != best_week], cut, adr_cut, rng)
        n = R.lead_leg(lead, [r for r in disc if r["ticker"] not in best_two], cut, adr_cut, rng)
        h = R.lead_leg(lead, block_rows, cut, adr_cut, rng)
        out[code] = (a, w, n, h)
    return out


for label, blk in (("DRY-RUN order (L1's 4th leg = #684 held-out, 63 rows)", held),
                   ("REAL-READ order (L1's 4th leg = September block, 75 rows)", new)):
    o = legs(random.Random(R.SEED_LEADS), blk)
    for code in ("L1", "L2"):
        a, w, n, h = o[code]
        print(f"{label} {code}: disc raw p(less) {a['p_raw_less']:.3f} ctl {100*a['diff_ctl']:+.1f}pp p {a['p_ctl_less']:.3f} | "
              f"drop-week ctl p {w['p_ctl_less']:.3f} | drop-two ctl p {n['p_ctl_less']:.3f} | block ctl {100*h['diff_ctl']:+.1f}pp p {h['p_ctl_less']:.3f}")

R.N_PERM = 40000
for code_i, lead in enumerate(R.LEADS):
    code, col, side, _ = lead
    cut = study.tercile_cuts([r[col] for r in disc if r.get(col) is not None])
    rng = random.Random(99)
    a = R.lead_leg(lead, disc, cut, adr_cut, rng)
    w = R.lead_leg(lead, [r for r in disc if r["iso_week"] != best_week], cut, adr_cut, rng)
    n = R.lead_leg(lead, [r for r in disc if r["ticker"] not in best_two], cut, adr_cut, rng)
    h = R.lead_leg(lead, new, cut, adr_cut, rng)
    print(f"PRECISE (40,000 draws, seed 99) {code}: disc ctl p {a['p_ctl_less']:.4f} | drop-week {w['p_ctl_less']:.4f} | "
          f"drop-two {n['p_ctl_less']:.4f} | block raw p(less) {h['p_raw_less']:.4f} ctl p(less) {h['p_ctl_less']:.4f} p(more) {h['p_ctl_more']:.4f}")
