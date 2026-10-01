"""#584 verify: 15th-name 20-session date per bar after dropping rows with <20 prior sessions (ADR undefined). Writes v9_out.txt."""
import runpy
g = runpy.run_path('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v5_verify.py')
inw, bars, date15 = g['inw'], g['bars'], g['date15']
ok = [r for r in inw if len([d for d in bars.get(r['ticker'], {}) if d < r['scan_date']]) >= 20]
with open('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v9_out.txt', 'w') as o:
    for bv in (10e6, 25e6, 50e6, 100e6):
        s = [r for r in ok if r['today_dollar_volume_at_open'] >= bv and r['gap_pct_at_open'] >= 10]
        print(f">=${bv/1e6:.0f}M gap>=10 ADR-defined: 15th name D0+20 = {date15(s)}", file=o)
