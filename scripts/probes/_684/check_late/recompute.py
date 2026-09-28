#!/usr/bin/env python3
"""Adversarial recompute of #684 late-alerts Option 1 vs CONTROL. Read-only; reads captured files only.
Own fill logic (study mechanics AND live #500 mechanics); P&L via the live exit function walk_arm
(same function the study used - it IS the live ladder, so reusing it is the point)."""
import csv, sys, re, datetime as dt
from collections import Counter, defaultdict
H = '/Users/alvinfung/apollo_the_wise/scripts/probes/_684/'
sys.path.insert(0, H); sys.path.insert(0, '/Users/alvinfung/apollo_the_wise')
from study import load_daily, load_features, add_outcomes
from late_alerts import load_bars_full, sessions_for, prior_closes_for, walk_one
from study_orb_live import compute_atr14_prior, validate_orb_entry, load_psv

def psv(p):
    out = []; hdr = None
    for line in open(p):
        line = line.rstrip('\n')
        if not line or line.startswith('('): continue
        parts = line.split('|')
        if hdr is None: hdr = parts; continue
        if len(parts) != len(hdr): continue
        out.append(dict(zip(hdr, parts)))
    return out

rows = load_features(); daily = load_daily(); add_outcomes(rows, daily)
idx = {(r['ticker'], r['scan_date']): r for r in rows}
pop = {(r['ticker'], r['scan_date']): r for r in load_psv(__import__('pathlib').Path(H + 'pop.tsv'))}
bars = load_bars_full()
outc = list(csv.DictReader(open(H + 'orb_live_outcomes.tsv'), delimiter='\t'))
alerts = psv(H + 'check_late_pop.txt'); aby = defaultdict(list)
for a in alerts: aby[(a['ticker'], a['alert_date'])].append(a)
trades = psv(H + 'check_late_trades.txt'); tby = defaultdict(list)
for t in trades: tby[(t['ticker'], t['alert_date'])].append(t)

LATE = [(r['ticker'], r['scan_date']) for r in outc if r['alerted'] == '1' and r['orb_status'].startswith('window_out_of_orb')]
CTRL = [(r['ticker'], r['scan_date']) for r in outc if r['alerted'] == '1' and r['orb_readable'] == '1' and not r['orb_status'].startswith('window_out_of_orb')]

def is_high(k):
    at = set(a['score_tier'] for a in aby.get(k, []))
    if at: return 'HIGH' in at
    # pre-05-11: no alert rows survive; use live trade rows (a magna53 row = HIGH was processed) else chosen tick tier
    if any(t['signal_type'] == 'magna53' for t in tby.get(k, [])): return True
    return pop[k]['score_tier'] == 'HIGH'

def detect_minute(k):
    """Earliest minute the live system could have submitted: the WINDOW skip row's 'detected HH:MM', else alert created."""
    for t in tby.get(k, []):
        m = re.search(r'detected (\d\d:\d\d) ET', t['skip_reason'])
        if m: return m.group(1)
    hi = [a for a in aby.get(k, []) if a['score_tier'] == 'HIGH']
    if hi: return min(a['alert_created_et'] for a in hi)[:5]
    return None

def slb(p): return round(max(p * 1.005, p + 0.02), 2)

def mins(h): a, b = h.split(':'); return int(a) * 60 + int(b)

def entry_study(blist, H_, submit, cancel):
    """study mechanics (pre-#500): stop-limit at H, limit slb(H); if already above, wait for pullback to limit."""
    limit = slb(H_); armed = False
    win = [b for b in blist if b['m'] >= submit and (cancel is None or b['m'] < cancel)]
    for b in win:
        o, h, l = b['o'], b['h'], b['l']
        if armed:
            if l <= limit: return ('filled', limit, b['m'])
            continue
        if o >= H_:
            if o <= limit: return ('filled', o, b['m'])
            armed = True
            if l <= limit: return ('filled', limit, b['m'])
        elif h >= H_:
            return ('filled', H_, b['m'])
    if armed: return ('no_entry', 'above_limit_never_back', None)
    end = cancel or '16:00'
    if len(win) < mins(end) - mins(max(submit, '09:30')): return ('abstain', 'gaps', None)
    return ('no_entry', 'never_crossed', None)

def entry_live500(blist, H_, L_, submit, cancel, px_mode='open'):
    """live submit_entry (#500 + ask-aware ON since 08-07): at submit, if latest price > H -> marketable limit at
    px*1.002 subject to chase cap (limit - stop <= 1.5*(H - stop)), else skip; if price <= H -> stop-limit walk.
    latest price proxy = the submit minute bar's open (px_mode='open') or previous minute close ('prevclose')."""
    stop = 2 * L_ - H_
    b0 = next((b for b in blist if b['m'] >= submit), None)
    if b0 is None: return ('abstain', 'no_submit_bar', None)
    if px_mode == 'prevclose':
        prev = [b for b in blist if b['m'] < b0['m']]
        px = prev[-1]['c'] if prev else b0['o']
    else:
        px = b0['o']
    if px > H_:
        lim = round(px * 1.002, 2)
        if lim - stop > 1.5 * (H_ - stop):
            return ('chase_cap_skip', round((px - H_) / (H_ - L_), 2), None)
        # marketable limit: fills in the submit minute if the bar trades at/below the limit (it opened there)
        if b0['l'] <= lim: return ('filled_chase', min(lim, max(b0['o'], b0['l'])), b0['m'])
        return ('no_entry', 'limit_not_reached', None)
    r = entry_study(blist, H_, submit, cancel)
    return r

def atr_for(t, d):
    db = daily.get(t, []); dates = [b[0] for b in db]
    if d not in dates: return None, None, db
    i0 = dates.index(d)
    cut = (dt.date.fromisoformat(d) - dt.timedelta(days=40)).isoformat()
    return compute_atr14_prior([(b[2], b[3], b[4]) for b in db[:i0] if b[0] >= cut]), i0, db

def rt_gap_ok(d, submit, bk, prev_close, uniform):
    if not uniform and d < '2026-08-02': return True
    floor = 9.0 if (uniform or d >= '2026-08-19') else 10.0
    b = bk['by_hhmm'].get(submit)
    if b is None or not prev_close: return True
    return (b['o'] - prev_close) / prev_close * 100 >= floor

def replay(k, submit, cancel, mech, uniform_gates):
    t, d = k
    bk = bars.get(k)
    if bk is None or '09:30' not in bk['by_hhmm']: return {'st': 'no_930_bar'}
    H_, L_ = bk['by_hhmm']['09:30']['h'], bk['by_hhmm']['09:30']['l']
    atr, i0, db = atr_for(t, d)
    prev_close = db[i0 - 1][4] if (i0 is not None and i0 >= 1) else None
    if not rt_gap_ok(d, submit, bk, prev_close, uniform_gates): return {'st': 'gap_below_floor'}
    ok, why = validate_orb_entry(H_, L_, atr)
    if not ok: return {'st': 'orb_invalid'}
    if mech == 'study':
        f = entry_study(bk['list'], H_, submit, cancel)
    else:
        f = entry_live500(bk['list'], H_, L_, submit, cancel, mech.split(':')[1] if ':' in mech else 'open')
    if not f[0].startswith('filled'): return {'st': f[0], 'why': f[1]}
    px, fm = f[1], f[2]
    stop = 2 * L_ - H_
    w = walk_one(px, stop, L_, bk['list'], fm, sessions_for(db, i0), prior_closes_for(db, i0, d), dt.date.fromisoformat(d))
    rr = w['pnl_per_share'] / (px - stop) if w['status'] == 'settled' else None
    r = idx[k]
    run = None
    fwd = db[i0 + 1:i0 + 16]
    if len(fwd) == 15 and r.get('adr_dollar_ep'):
        mx = max([max(b['h'] for b in bk['list'] if b['m'] >= fm)] + [b[2] for b in fwd])
        run = (mx - px) / r['adr_dollar_ep']
    return {'st': 'filled', 'kind': f[0], 'px': px, 'fm': fm, 'H': H_, 'L': L_, 'stop': stop, 'walk': w['status'],
            'wreason': w.get('reason'), 'R': rr, 'run': run, 'ext_orb': None}

def summ(label, res, drop=None):
    res = [(k, x) for k, x in res if not drop or k not in drop]
    fills = [(k, x) for k, x in res if x['st'] == 'filled']
    rs = [(k, x['R']) for k, x in fills if x['R'] is not None]
    mean = sum(v for _, v in rs) / len(rs) if rs else float('nan')
    losers = [v for _, v in rs if v < 0]
    runners = sum(1 for _, x in fills if x['run'] is not None and x['run'] >= 5)
    lab = sum(1 for k, x in fills if idx[k].get('runner5'))
    return (f"{label}: n={len(res)} fills={len(fills)} settled={len(rs)} R/trade={mean:+.2f} "
            f"loss_rate={100*len(losers)/len(rs) if rs else 0:.0f}% worst={min((v for _, v in rs), default=float('nan')):+.2f} "
            f"<-1.5R={sum(1 for v in losers if v < -1.5)} runs>=5ADR_from_fill={runners} labelled_runners_filled={lab} "
            f"sumR={sum(v for _, v in rs):+.2f}"), rs

def best2(rs): return {k for k, _ in sorted(rs, key=lambda x: -x[1])[:2]}

def report(label, res, out):
    s, rs = summ(label, res); out.append(s)
    if len(rs) >= 3:
        s2, _ = summ(label + ' drop-best-two', res, best2(rs)); out.append('   ' + s2)
    st = Counter(x['st'] + (':' + x.get('kind', '') if x['st'] == 'filled' else '') for _, x in res)
    out.append('   status: ' + str(dict(st)))
    # by month
    bym = defaultdict(list)
    for k, x in res:
        if x['st'] == 'filled' and x['R'] is not None: bym[k[1][:7]].append(x['R'])
    out.append('   by month (n, R/trade, sumR): ' + '; '.join(f"{m} n={len(v)} {sum(v)/len(v):+.2f} sum={sum(v):+.1f}" for m, v in sorted(bym.items())))
    return rs

out = []
p = out.append
late_high = [k for k in LATE if is_high(k)]
ctrl_high = [k for k in CTRL if is_high(k)]
p(f"LATE {len(LATE)} -> HIGH {len(late_high)}; CTRL {len(CTRL)} -> HIGH {len(ctrl_high)}")
p(f"LATE labelled runners: {sum(1 for k in LATE if idx[k].get('runner5'))}, of which HIGH {sum(1 for k in late_high if idx[k].get('runner5'))}: "
  + ', '.join(f'{k[0]} {k[1]}' for k in late_high if idx[k].get('runner5')))
p(f"LATE non-HIGH runners: " + ', '.join(f'{k[0]} {k[1]}' for k in LATE if not is_high(k) and idx[k].get('runner5')))

def fp(k): return pop[k]['first_pass_time']
def ctrl_submit(k): return max(fp(k), '09:31')

p('\n== REPRODUCE study (all 99 / 164, study mechanics, era gates) ==')
res = [(k, replay(k, fp(k), '10:30', 'study', False)) for k in LATE]; report('OPT1 study-repro 10:30', res, out)
res = [(k, replay(k, ctrl_submit(k), '10:00' if k[1] >= '2026-08-01' else None, 'study', False)) for k in CTRL]; report('CTRL study-repro (era cancel)', res, out)

p('\n== HIGH only, study mechanics ==')
res = [(k, replay(k, fp(k), '10:30', 'study', False)) for k in late_high]; report('OPT1 HIGH study 10:30', res, out)
res = [(k, replay(k, ctrl_submit(k), '10:00' if k[1] >= '2026-08-01' else None, 'study', False)) for k in ctrl_high]; report('CTRL HIGH study (era cancel)', res, out)

p('\n== HIGH only, submit at ACTUAL detection minute, study mechanics ==')
dm = {k: detect_minute(k) for k in late_high}
p('detection minute vs first-pass minute: ' + str(Counter((mins(dm[k]) - mins(fp(k))) if dm[k] else None for k in late_high)))
res = [(k, replay(k, dm[k] or fp(k), '10:30', 'study', False)) for k in late_high]; report('OPT1 HIGH detect-min study 10:30', res, out)

p('\n== TODAY\'S RULES uniformly (9% rt gap all dates, #500 chase + cap, 10:00 CTRL cancel / 10:30 OPT1) ==')
for mech in ('live500:open', 'live500:prevclose'):
    res = [(k, replay(k, dm[k] or fp(k), '10:30', mech, True)) for k in late_high]
    report(f'OPT1 HIGH detect-min {mech} 10:30', res, out)
    cc = Counter(x.get('why') for _, x in res if x['st'] == 'chase_cap_skip')
    exts = sorted(x['why'] for _, x in res if x['st'] == 'chase_cap_skip')
    p(f'   chase-cap skips: {len(exts)}; price above ORB high at submit, in ORB ranges: {exts}')
    res_c = [(k, replay(k, ctrl_submit(k), '10:00', mech, True)) for k in ctrl_high]
    report(f'CTRL HIGH {mech} uniform 10:00', res_c, out)
    if mech == 'live500:open':
        R_opt1_live, R_ctrl_live = res, res_c
res = [(k, replay(k, dm[k] or fp(k), '10:30', 'study', True)) for k in late_high]; report('OPT1 HIGH detect-min study-mech uniform-gates 10:30', res, out)
res = [(k, replay(k, ctrl_submit(k), '10:00', 'study', True)) for k in ctrl_high]; report('CTRL HIGH study-mech uniform (10:00 cancel, 9% all dates)', res, out)

# the study's 41 fills: how many are at the first-pass minute, how many are pullback-limit fills
p('\n== anatomy of the study\'s Option-1 fills (99 pop, study mechanics) ==')
an = Counter(); det = []
for k in LATE:
    x = replay(k, fp(k), '10:30', 'study', False)
    if x['st'] != 'filled': continue
    bk = bars[k]; b0 = next(b for b in bk['list'] if b['m'] >= fp(k))
    where = 'above_H_at_submit' if b0['o'] > x['H'] else 'below_H_at_submit'
    kind = 'pullback_limit' if abs(x['px'] - slb(x['H'])) < 1e-9 and b0['o'] > slb(x['H']) else ('fill_at_trigger' if abs(x['px'] - x['H']) < 1e-9 else 'fill_at_open')
    an[(is_high(k), where, kind, x['fm'] == fp(k))] += 1
    det.append((k, is_high(k), where, kind, x['fm'], round(x['R'], 2) if x['R'] is not None else None, round((b0['o'] - x['H']) / (x['H'] - x['L']), 2)))
for kk, v in sorted(an.items(), key=lambda z: -z[1]): p(f'   HIGH={kk[0]} {kk[1]} {kk[2]} fill_minute==first_pass={kk[3]}: {v}')
p('   per fill (key, HIGH, where, kind, fill_min, R, (open-H)/ORBrange at submit):')
for d_ in det: p('     ' + str(d_))

txt = '\n'.join(out) + '\n'
open('/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/recompute_out.txt', 'w').write(txt)
print(txt)
