"""⚠ THE ERA CHECK the Phase 1 card could not run: does era_D — THE RULE ACTUALLY LIVE — also
settle ZERO names at >=3R on this population?

Phase 1's whole headline is "+8 to +12 over the live ladder's 0". Its baseline is `era_c` (2R
partial, breakeven at partial), which is what the design doc calls "live" — but **prod flipped to
`era_d` on 2026-09-06 (`b52fdcbc`: partial moved to +8R, price-armed breakeven at +3R)**, sixteen
days before this card ran. A cell that beats a RETIRED ladder has not been shown to beat the one
we are running. That is this repo's most expensive recurring error — 27 of 28 trades once
predated the exit rule I proposed changing.

era_d is structurally close to the thing Phase 1 found (bank higher up), so this is not a
formality: if era_d also reads 0, the finding survives intact and is now stated against the live
rule. If era_d reads 8-13, the headline is an artifact of comparing against the wrong era.

Reuses the card's own probe module so the population, admission and walk are IDENTICAL — no
re-implementation, no second definition of the cohort.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location(
    "_p1", REPO / "scripts" / "probes" / "_545_phase1_harvest_sweep.py")
p1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p1)

from ep_replay import RULESETS
from dataclasses import replace

MAY_END = "2026-05-31"


def summarise(res, label, paired_keys=None):
    settled = {k: r for k, r in res.items() if r["status"] == "settled" and r["admit"] == "admit"}
    if paired_keys is not None:
        settled = {k: r for k, r in settled.items() if k in paired_keys}
    rs = [r["realized_r"] for r in settled.values() if r["realized_r"] is not None]
    t3 = sum(1 for x in rs if x >= 3)
    t5 = sum(1 for x in rs if x >= 5)
    ex_may = [r for k, r in settled.items() if str(r["alert_date"]) > MAY_END
              and r["realized_r"] is not None]
    t3_ex = sum(1 for r in ex_may if r["realized_r"] >= 3)
    names3 = sorted(r["ticker"] for r in settled.values()
                    if r["realized_r"] is not None and r["realized_r"] >= 3)
    print(f"  {label:<34s} n={len(rs):<4d} >=3R={t3:<3d} >=5R={t5:<3d} "
          f"sum={sum(rs):+7.1f}  ex-May n={len(ex_may):<4d} >=3R={t3_ex}")
    if names3:
        print(f"      >=3R names: {', '.join(names3)}")
    return settled, t3, t3_ex


def main():
    s2, alerts, minutes, daily, extra, regime_rows = p1.load_all()
    print(f"population: {len(alerts)} campaigns — IDENTICAL to the Phase 1 card (same loader)\n")

    cells = {
        "era_c  (card's baseline, RETIRED 09-06)": RULESETS["era_c"],
        "era_d  (LIVE since 2026-09-06)": RULESETS["era_d"],
    }
    base = RULESETS["era_c"]
    for sname, srs in (("adr_0.5", replace(base, name="adr_0.5", stop_mode="adr_k", adr_k=0.5)),
                       ("orb_low", replace(base, name="orb_low", stop_mode="orb_low"))):
        for r2 in (5.0, 8.0, 10.0):
            nm = f"{sname}_2ndR{int(r2)}_t3"
            cells[nm] = replace(srs, name=nm, runner_rule="t3", second_partial_r=r2)

    res = {k: p1.walk_alerts(alerts, rs, minutes, daily, extra) for k, rs in cells.items()}

    print("=== UNPAIRED (each cell on its own admitted+settled set) ===")
    out = {}
    for k in cells:
        out[k] = summarise(res[k], k)

    live_c = {k for k, r in res["era_c  (card's baseline, RETIRED 09-06)"].items()
              if r["status"] == "settled" and r["admit"] == "admit"}
    live_d = {k for k, r in res["era_d  (LIVE since 2026-09-06)"].items()
              if r["status"] == "settled" and r["admit"] == "admit"}
    paired = live_c & live_d
    print(f"\n=== PAIRED on rows settled under BOTH era_c AND era_d (n={len(paired)}) ===")
    for k in cells:
        summarise(res[k], k, paired_keys=paired)

    print("\n=== THE PASS BAR RE-APPLIED AGAINST era_d (paired, the LIVE rule) ===")
    d_settled = {k: r for k, r in res["era_d  (LIVE since 2026-09-06)"].items()
                 if k in paired and r["realized_r"] is not None}
    d_t3 = sum(1 for r in d_settled.values() if r["realized_r"] >= 3)
    d_t3_ex = sum(1 for r in d_settled.values()
                  if str(r["alert_date"]) > MAY_END and r["realized_r"] >= 3)
    d_sum = sum(r["realized_r"] for r in d_settled.values())
    print(f"  live(era_d) paired: >=3R={d_t3}  ex-May >=3R={d_t3_ex}  sum={d_sum:+.1f}"
          f"   -> bar is >=3R {d_t3+3}, ex-May {d_t3_ex+3}, sum >= {d_sum-5:+.1f}")
    for k in cells:
        if "2ndR" not in k:
            continue
        s = {kk: r for kk, r in res[k].items()
             if kk in paired and r["status"] == "settled" and r["admit"] == "admit"
             and r["realized_r"] is not None}
        t3v = sum(1 for r in s.values() if r["realized_r"] >= 3)
        exv = sum(1 for r in s.values() if str(r["alert_date"]) > MAY_END and r["realized_r"] >= 3)
        sm = sum(r["realized_r"] for r in s.values())
        best = max((r["realized_r"] for r in s.values()), default=0)
        t3_drop = sum(1 for r in s.values()
                      if r["realized_r"] >= 3 and r["realized_r"] != best)
        legs = [t3v >= d_t3 + 3, exv >= d_t3_ex + 3, t3_drop >= d_t3 + 3, sm >= d_sum - 5]
        print(f"  {k:<22s} >=3R={t3v:<3d} ex-May={exv:<3d} drop-best={t3_drop:<3d} "
              f"sum={sm:+7.1f}  legs={['PASS' if x else 'FAIL' for x in legs]}  "
              f"-> {'CLEARS' if all(legs) else 'FAILS'}")

    print("\n=== THE QUESTION ===")
    _, t3c, _ = out["era_c  (card's baseline, RETIRED 09-06)"]
    _, t3d, _ = out["era_d  (LIVE since 2026-09-06)"]
    print(f"  era_c >=3R = {t3c}   era_d >=3R = {t3d}")
    print("  -> the Phase 1 headline stands only if era_d is also ~0." if t3d <= 2
          else "  -> the Phase 1 headline was measured against the WRONG era.")


if __name__ == "__main__":
    main()
