#!/usr/bin/env python3
"""Copies the two operator-example bar series the v1 unit tests read (ODD, ZCSH — mi_daily_closes, read-only pulls
already committed under scripts/probes/_594_sample4_1029/q5_odd_1009.out and scripts/probes/_zcsh_1029/q1.out) and
the 90-name ETV reference list (etv_names_2026-10-28.tsv, beside this file) into tests/fixtures/breakout_v1_parity/,
so CI reads them without the probe folders. Text copy only; no network."""
import csv
import shutil
from pathlib import Path

REPO = Path('/Users/alvinfung/apollo_the_wise')
OUT = REPO / 'tests/fixtures/breakout_v1_parity'
SRC = {'ODD': REPO / 'scripts/probes/_594_sample4_1029/q5_odd_1009.out',
       'ZCSH': REPO / 'scripts/probes/_zcsh_1029/q1.out'}
rows = []
for t, p in SRC.items():
    take = False
    for line in p.read_text().splitlines():
        if line.startswith('trade_date|'):
            take = True
            continue
        if take:
            parts = line.split('|')
            if len(parts) != 6 or not parts[0][:2] == '20':
                take = False
                continue
            rows.append([t] + parts)
with open(OUT / 'operator_examples_bars.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ticker', 'date', 'o', 'h', 'l', 'c', 'v'])
    w.writerows(rows)
shutil.copy(REPO / 'scripts/probes/_breakout_v1_build/etv_names_2026-10-28.tsv', OUT / 'etv_names_2026-10-28.tsv')
print({t: sum(1 for r in rows if r[0] == t) for t in SRC})
