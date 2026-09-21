"""Half-two: does the STILL-SKIPPED (>=75%) tail convert under our bracket?
Uses the 2026-08-16 extended-cohort bar cache (159 pairs) - no new fetch.
For every filled name: max R reached BEFORE the stop is touched (what a live
trade could actually have banked) vs MFE overall."""
import sys, pathlib
sys.path.insert(0, '.'); sys.path.insert(0, '../..')
import _468_moderate_realized_r as M
HERE = pathlib.Path('.')
M.COHORT, M.DAILY, M.MINUTE = HERE/'_ext_cohort.tsv', HERE/'_ext_daily.tsv', HERE/'_ext_minute.tsv'
rows, daily, minute = M.load_cohort(), M.load_daily(), M.load_minute()

ext = {}
so = {}
for ln in open('_577b_mo_ext.psv'):
    p = ln.rstrip('\n').split('|')
    if len(p) < 4 or not p[0] or not p[2]:
        continue
    ext[(p[0], p[1])] = float(p[2]); so[(p[0], p[1])] = (p[3] == 't')

def walk(entry, stop, day0_after, fwd, n_days):
    """(max R before stop touched, max R overall, stopped?) over day0 minutes + n daily."""
    risk = entry - stop
    best_before = -1.0; best_all = -1.0; stopped = False
    for b in day0_after:
        if not stopped:
            best_before = max(best_before, (b['h'] - entry)/risk)
            if b['l'] <= stop: stopped = True
        best_all = max(best_all, (b['h'] - entry)/risk)
    for d in fwd[:n_days]:
        if not stopped:
            best_before = max(best_before, (d['h'] - entry)/risk)
            if d['l'] <= stop: stopped = True
        best_all = max(best_all, (d['h'] - entry)/risk)
    return best_before, best_all, stopped

buckets = {'50-75': [], '>=75': [], 'unknown': []}
skip = {}
for r in rows:
    key = (r['ticker'], r['alert_date'])
    e = ext.get(key)
    b = 'unknown' if e is None else ('50-75' if 50 <= e < 75 else ('>=75' if e >= 75 else 'under50'))
    if b == 'under50':
        continue
    db = daily.get(r['ticker'], []); i = M.idx_of_date(db, r['alert_date'])
    raw = minute.get(key, [])
    if i is None or not raw:
        skip[key] = 'no_bars'; continue
    rth = M.de.polygon_to_rth_minutes(raw, r['alert_date'])
    if not rth: skip[key] = 'no_rth'; continue
    rec = M.reconstruct(rth, M.SUBMIT_MIN, M.atr14_prior_close(db, i), db[i:])
    if rec.get('outcome') != 'filled':
        skip[key] = rec.get('outcome'); continue
    after = [x for x in rth if x['m'] >= rec['fill_minute']]
    bb, ba, st = walk(rec['entry'], rec['stop'], after, db[i+1:], 20)
    buckets[b].append({'k': key, 'before': bb, 'all': ba, 'stopped': st,
                       'setup': so.get(key)})

print(f"08-16 extended-cohort bar cache: {len(rows)} (ticker,date) pairs")
print("not filled / no bars: " + ", ".join(f"{k}={sum(1 for v in skip.values() if v==k)}" for k in sorted(set(skip.values()))))
for name in ('50-75', '>=75', 'unknown'):
    v = buckets[name]
    if not v: continue
    bef = sorted(x['before'] for x in v); al = sorted(x['all'] for x in v)
    n = len(v)
    print(f"\n[{name}]  filled n={n}   (setup_at_open TRUE: {sum(1 for x in v if x['setup'])})")
    print(f"   reached BEFORE the stop:  >=2R {sum(1 for x in bef if x>=2)}/{n}   >=3R {sum(1 for x in bef if x>=3)}/{n}   >=8R {sum(1 for x in bef if x>=8)}/{n}   median {M._median(bef):+.2f}R  max {bef[-1]:+.2f}R")
    print(f"   MFE overall (incl. after the stop): >=2R {sum(1 for x in al if x>=2)}/{n}   >=5R {sum(1 for x in al if x>=5)}/{n}   median {M._median(al):+.2f}R  max {al[-1]:+.2f}R")
    print(f"   stop touched within 20 sessions: {sum(1 for x in v if x['stopped'])}/{n}")
