#!/usr/bin/env python3
"""#717 diagnostic cited by the v2 revision note in 01_vol.py: last 30 daily true ranges / closes of the anchors vs ok charts."""
import numpy as np, pandas as pd, os
WL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../_717_wideloose_1114")
gr = pd.read_csv(f"{WL}/graded_rows.tsv", sep="\t"); W = np.load(f"{WL}/graded_windows200.npy")
for t in ['MELI', 'RRC', 'TDOC', 'CRWD', 'ZS', 'TTD', 'ADMS', 'CAR']:
    r = gr[gr.ticker == t].iloc[0]; w = np.log(W[r.wid].astype(float)); h, l, c = w[1], w[2], w[3]
    tr = np.fmax(h[1:], c[:-1]) - np.fmin(l[1:], c[:-1]); d = np.diff(c)
    print(t, r.D, r.grade, 'TR%', ' '.join(f'{x*100:.0f}' for x in tr[-30:])); print('   dc%', ' '.join(f'{x*100:+.0f}' for x in d[-30:]))
    print('   box10 %.3f box10-20 %.3f box20-30 %.3f' % (h[-10:].max() - l[-10:].min(), h[-20:-10].max() - l[-20:-10].min(), h[-30:-20].max() - l[-30:-20].min()))
