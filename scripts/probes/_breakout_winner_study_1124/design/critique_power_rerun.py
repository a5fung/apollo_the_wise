#!/usr/bin/env python3
"""Critique finding 9 (2026-11-24): `spread_sim.py`'s whole-chain figure for a true 1.5x under fork 3b, re-run with era B at
30 months / 3,623 events (the draft's own E+60 <= 2024-12-31 rule) and era B's base rate scaled (1.0, 0.75 = the #705 hint
7.9 vs 10.5, 0.5 = a stress). SYNTHETIC labels only; reads spread_sim.py's source, no data file.
    python3 critique_power_rerun.py > critique_power_rerun.txt"""
import os
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "spread_sim.py")).read()
head = src.split("DISC_Y = (2017")[0]
BODY = '''
DISC_Y = (2017, 2018, 2019, 2020); CONF_Y = (2021, 2022)
for keep in (1.0, 0.6):
    for p in (0.03, 0.05):
        D = blocks(DISC_Y, keep, p); C = blocks(CONF_Y, keep, p, with_b=True)
        r0, r0x, nd = draw(D, 1.0); c0, _, nc = draw(C, 1.0)
        thr2 = np.quantile(np.abs(r0), 0.95)
        r, rx, _ = draw(D, 1.5); rc, _, _ = draw(C, 1.5)
        c123 = (r >= np.log(1.25)) & (np.abs(r) >= thr2) & (rx >= np.log(1.10))
        ok = (rc >= np.quantile(c0, 1 - 0.05 / 9)) & (rc >= np.log(1.2))
        print(f"   keep {keep} rate outside 2020 {p:.0%}: true 1.5x whole chain fam9 {c123.mean() * ok.mean():.3f} (check n {nc})")
'''
for name, erab, bmult in (("draft: 33 months, 3,985 events, era-B rate = the 2017-19 rate", (3985, 33), 1.0),
                          ("30 months, 3,623 events, same rate", (3623, 30), 1.0),
                          ("30 months, 3,623 events, era-B rate 0.75x (the #705 hint)", (3623, 30), 0.75),
                          ("30 months, 3,623 events, era-B rate 0.5x (stress)", (3623, 30), 0.5)):
    h = head.replace("ERA_B = (3985, 33)", f"ERA_B = {erab}")
    old = "out += [(int(ERA_B[0] * keep / ERA_B[1]), p, 2023)]"
    assert old in h
    h = h.replace(old, f"out += [(int(ERA_B[0] * keep / ERA_B[1]), p * {bmult}, 2023)]")
    print(name); exec(h + BODY, {})
