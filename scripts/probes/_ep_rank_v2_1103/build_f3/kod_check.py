#!/usr/bin/env python3
"""The ONLY calibration: does the re-defined feature 3 reproduce his KOD 2026-09-28 read?

His words (operator_shared_notes 11-02): "the two pull back is into the previous base high (around end of
Dec '25)". Target: shelf ~ $30 dated end of Dec 2025; held = yes. KOD only — no population is scored here.
Run at the stated thresholds and at every +-50% variant. Output: kod_check.txt.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rv2  # noqa: E402
from f3_def import STATED, f3_new  # noqa: E402

ns = rv2.load()
OUT = []


def P(s=""):
    print(s)
    OUT.append(s)


VARIANTS = [("stated", {})] + [(f"{k}={v}", {k: v}) for k, v in (
    ("adr_mult", 0.5), ("adr_mult", 1.5), ("pb_win", 20), ("pb_win", 60), ("base_end", 125), ("base_end", 375),
    ("run_win", 30), ("run_win", 90), ("shelf_win", 22), ("shelf_win", 68), ("run_min", 0.15), ("run_min", 0.45))]

enc, days, ia = ns["encode1"]("KOD", "2026-09-28")
adr = ns["nbis"].adr20_pct(days, ia)
P("KOD 2026-09-28 — the re-defined feature 3, his read: shelf ~$30 at end of Dec 2025, held = yes")
P(f"  history in the 5-year slice: {ia} sessions · ADR20 {adr:.3f}% (the encoder's adr20_pct)")
P(f"  {'variant':<15} {'P (high before current base)':<30} {'S (run start low)':<24} {'shelf':<22} "
  f"{'run':>6} {'two lowest swing lows (last pb_win)':<40} {'d1/d2 ADR':<13} struct held into")
for name, over in VARIANTS:
    prm = dict(STATED, **over)
    r = f3_new(days, ia, adr, prm)
    lows = ", ".join(f"{d} {v:.2f}" for d, v in (r["lows"] or []))
    P(f"  {name:<15} {r['p_date']} ${r['p_high']:.2f} (D-{r['p_idx']}) {'':<1}"
      f"{r['s_date']} ${r['s_low']:.2f} (D-{r['s_idx']})  {r['shelf_date']} ${r['shelf']:.2f} (D-{r['shelf_idx']}) "
      f"{r['run_pct']*100:>5.0f}% {lows:<40} {r['d1']:+.2f}/{r['d2']:+.2f}   {r['structure']:<6} "
      f"{r['held']:>4} {r['into']:>4}")
st = f3_new(days, ia, adr, STATED)
ok = st["shelf_date"].startswith("2025-12") and 28 <= st["shelf"] <= 32 and st["held"] == 1
P(f"\n  REPRODUCES HIS READ at the stated thresholds: {'YES' if ok else 'NO'} "
  f"(shelf {st['shelf_date']} ${st['shelf']:.2f}; held = {st['held']})")
(HERE / "kod_check.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
