#!/usr/bin/env python3
"""POST-HOC (written AFTER read.out was seen; NOT pre-registered; cannot change the verdict).
Two attribution questions about D1's discovery lean (>= 9M: 14.5 % vs 8.9 % reaching >= 5 ADR, p 0.051):
  (a) where does it live in time — the best week (2026-W19, the early-May earnings cluster) vs the rest?
  (b) is it volatility leaking through — >= 9M names carry a higher ADR %, and #684 found ADR % HIGHER a
      discovery lead. Read >= 9M vs < 9M inside ADR % terciles (discovery cuts).
Writes posthoc.out. Run: PYTHONDONTWRITEBYTECODE=1 python3 posthoc.py
"""
from __future__ import annotations

from common import HERE, load_rows

import study  # noqa: E402


def cell(g):
    n = len(g)
    k5 = sum(r["runner5"] for r in g)
    k8 = sum(r["runner8"] for r in g)
    return f"{k5}/{n} = {100 * k5 / n:.1f}% (>=8 ADR {k8})" if n else "—"


def main() -> None:
    rows = load_rows()
    study.add_outcomes(rows, study.load_daily())
    scored = [r for r in rows if r["runner5"] is not None]
    disc = [r for r in scored if r["block"] == "DISCOVERY"]
    out = ["POST-HOC — not pre-registered; attribution only; the verdict in read.out stands.", ""]
    p = out.append
    p("(a) D1 by time, DISCOVERY: >= 9M vs < 9M share reaching >= 5 ADR")
    for name, g in (("best week 2026-W19", [r for r in disc if r["iso_week"] == "2026-W19"]), ("all other weeks", [r for r in disc if r["iso_week"] != "2026-W19"])):
        p(f"  {name}: >= 9M {cell([r for r in g if r['SC_ge9m'] == 1.0])}   < 9M {cell([r for r in g if r['SC_ge9m'] == 0.0])}")
    p("")
    cut = study.tercile_cuts([r["PRE_adr20_pct"] for r in disc if r.get("PRE_adr20_pct") is not None])
    p(f"(b) D1 inside ADR % terciles (discovery cuts {cut[0]:.2f}% / {cut[1]:.2f}%), ALL 667 rows with an ADR:")
    for name, f in (("low ADR", lambda x: x <= cut[0]), ("mid ADR", lambda x: cut[0] < x < cut[1]), ("high ADR", lambda x: x >= cut[1])):
        g = [r for r in scored if r.get("PRE_adr20_pct") is not None and f(r["PRE_adr20_pct"])]
        a = [r for r in g if r["SC_ge9m"] == 1.0]
        b = [r for r in g if r["SC_ge9m"] == 0.0]
        p(f"  {name}: >= 9M {cell(a)}   < 9M {cell(b)}")
    text = "\n".join(out) + "\n"
    (HERE / "posthoc.out").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
