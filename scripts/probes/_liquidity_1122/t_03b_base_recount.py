"""t_03b: recount of the in-window all-events base shares from the run-2 frames (second route: plain date filter)."""
import pandas as pd
VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27")
for nm, f, c in (("EP", "build_r2/p2_ep_frame.csv", "E"), ("breakout", "build_r2/p2_breakout_frame.csv", "D")):
    d = pd.read_csv(f, parse_dates=[c]); assert d[c].max() <= pd.Timestamp("2024-12-31"); x = d[(d[c] >= VS) & (d[c] <= VE)]
    print(f"{nm}: big winners {int(x.win.sum())} of n={len(x)} = {x.win.mean()*100:.2f}%")
