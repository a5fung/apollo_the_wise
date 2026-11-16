"""s2 — descriptive counts behind the gates of s1 (see common.py docstring = the registration). Nothing here is a verdict:
s1 showed 0 winner campaigns in every group and no pattern x group cell at 30 first fires."""
from common import *
import collections as C, json, re
camps, daily, cal, trig = load()
lab = json.load(open(HERE/'labels.json'))
pop = {k for k in camps if lab[f"{k[0]}|{k[1]}"]['in_pop']}
def sess(d): return [x for x in cal if x > d]
def mean(v): return sum(v)/len(v) if v else float('nan')
T = [r for r in trig if (r['ticker'], r['ep']) in pop]
F1 = [r for r in T if r['reentry_shape'] == 'first']
def mature(r): return len(sess(r['fd'])) >= 20
print('== lane arm on FIRST fires, per group (mature = 20 sessions after the fire; open rows listed apart) ==')
print('group | first fires | mature | stopped -1R (hard-stop arm) | >=3R on trail arm inc/025/075/100 | mean trail R inc | n with all 3 variants | mean trail R inc/025/075/100 on those')
for g in GN + ['ALL (labelled count only)']:
    S = [r for r in F1 if g.startswith('ALL') or group(r['ep']) == g]; M = [r for r in S if mature(r) and r['realized_r_trail'] != '']
    V = [r for r in M if all(r[f'realized_r_trail_{v}'] != '' for v in ('025', '075', '100'))]
    k3 = lambda col, X: sum(f(r[col]) >= 3 for r in X if r[col] != '')
    print(g, '|', len(S), '|', len(M), '|', sum(r['outcome'] == 'stop' for r in M), '|', k3('realized_r_trail', M), k3('realized_r_trail_025', M), k3('realized_r_trail_075', M), k3('realized_r_trail_100', M),
          '|', f"{mean([f(r['realized_r_trail']) for r in M]):+.2f}", '|', len(V), '|', ' '.join(f"{mean([f(r[c]) for r in V]):+.2f}" for c in ('realized_r_trail', 'realized_r_trail_025', 'realized_r_trail_075', 'realized_r_trail_100')))
print('open / immature first fires:', [(r['ticker'], r['ep_date'], r['rung'], r['fire_date'], r['outcome'] or 'OPEN') for r in F1 if not mature(r)])
print('\n== his labelled EP in the population: PENG 2026-10-07 (G4) — every lane row ==')
for r in T:
    if r['ticker'] == 'PENG': print('  ', r['rung'], r['fire_date'], r['reentry_shape'], 'entry', r['entry_price'], 'stop', r['stop_price'], 'out', r['outcome'], 'R', r['realized_r'], 'trail', r['realized_r_trail'], '075', r['realized_r_trail_075'], '100', r['realized_r_trail_100'], 'mfe', r['mfe_r'])
print('\n== VICR 2026-09-17 (ran +53% in 15 sessions, held +21%: NOT a winner by the label) — lane rows ==')
for r in T:
    if r['ticker'] == 'VICR': print('  ', r['rung'], r['fire_date'], r['reentry_shape'], 'entry', r['entry_price'], 'stop', r['stop_price'], 'w%', r['stop_width_pct'][:5], 'out', r['outcome'], 'R', r['realized_r'], 'trail', r['realized_r_trail'], '075', r['realized_r_trail_075'], '100', r['realized_r_trail_100'], 'mfe', r['mfe_r'])

print('\n== DIRECTION checks — COUNTS ONLY (no cell reaches 30 first fires; no sign is read) ==')
# (b) fire-session stop share: incumbent (stop_hit_date == fire_date) vs _075 (fire-day post-fire low <= stop_price_075 where day0 resolved)
def b075(r):
    if r['stop_price_075'] == '' : return None
    lo = f(r['day0_post_low']) if r['day0_resolved'] == 't' and r['day0_post_low'] != '' else None
    if lo is None: return None
    return lo <= f(r['stop_price_075'])
print('(b) fire-session stops, first fires: group | n | incumbent stopped on the fire day | _075 determinable n | _075 stopped on the fire day')
for g in GN + ['ALL (labelled count only)']:
    S = [r for r in F1 if g.startswith('ALL') or group(r['ep']) == g]
    d = [b075(r) for r in S]; d = [x for x in d if x is not None]
    print('   ', g, '|', len(S), '|', sum(r['stop_hit_date'] == r['fire_date'] for r in S), '|', len(d), '|', sum(d))
# (c) shake-out share: first attempts stopped within 2 sessions (fire day = session 0..2 after fire) whose close 10 sessions after the fire is above the entry
print('(c) shake-outs: group | first fires stopped within 2 sessions of the fire | of those with a bar 10 sessions later | close above entry')
for g in GN + ['ALL (labelled count only)']:
    S = [r for r in F1 if g.startswith('ALL') or group(r['ep']) == g]; a = b = c = 0
    for r in S:
        if r['stop_hit_date'] == '': continue
        ss = sess(r['fd']); k = 0 if D(r['stop_hit_date']) == r['fd'] else ss.index(D(r['stop_hit_date'])) + 1
        if k > 2: continue
        a += 1
        if len(ss) >= 10 and ss[9] in daily[r['ticker']]:
            b += 1; c += daily[r['ticker']][ss[9]]['close'] > f(r['entry_price'])
    print('   ', g, '|', a, '|', b, '|', c)
# (d) regime on the fire date
reg = {}
for l in (HERE/'q4_regime.out').read_text().split('\n'):
    m = re.match(r'^(2026-\d\d-\d\d)\|([A-Za-z ]+)\|', l)
    if m: reg[D(m.group(1))] = m.group(2)
print('(d) lane arm (incumbent + trail) by regime on the fire date, mature first fires: group | regime | n | mean trail R | >=3R')
for g in GN + ['ALL (labelled count only)']:
    S = [r for r in F1 if (g.startswith('ALL') or group(r['ep']) == g) and mature(r) and r['realized_r_trail'] != '']
    by = C.defaultdict(list)
    for r in S: by[reg.get(r['fd'], 'no regime row')].append(f(r['realized_r_trail']))
    for k, v in sorted(by.items()): print('   ', g, '|', k, '|', len(v), '|', f"{mean(v):+.2f}", '|', sum(x >= 3 for x in v))
print('(a) H2-corrected entry edge: NOT COMPUTED — it is a rate against control sessions and no pattern x group cell has 30 fires (largest 10).')

# ============ H6 ============
print('\n== H6 — campaigns with >= 40 sessions (EP <= 2026-09-17) ==')
tk = C.defaultdict(list)
for r in T: tk[(r['ticker'], r['ep'])].append(r)
arm40 = sorted([k for k in pop if lab[f"{k[0]}|{k[1]}"]['n40']], key=lambda k: k[1])
print('campaigns:', len(arm40), dict(C.Counter(group(k[1]) for k in arm40)))
launches = []
for t, ep in arm40:
    b = daily[t]; ss = sess(ep)[:40]; best = (0, None, None)
    for j in range(len(ss)-1):
        hi = max(b[ss[k]]['high_price'] for k in range(j+1, len(ss))); g_ = hi / b[ss[j]]['low_price'] - 1
        if g_ > best[0]: best = (g_, j, hi)
    if best[0] >= 0.5:
        j = best[1]; start = ss[j]
        own = j + 1 <= 20
        rw = any(r['stop_hit_date'] and D(r['stop_hit_date']) < start <= (sess(D(r['stop_hit_date']))[:20] or [D(r['stop_hit_date'])])[-1] for r in tk[(t, ep)])
        other = any(k2[0] == t and k2 != (t, ep) and k2[1] < start <= (sess(k2[1])[:20] or [k2[1]])[-1] for k2 in camps)
        fired_after = [r for r in tk[(t, ep)] if r['fd'] >= start]
        launches.append((t, ep, j+1, start, best[0], own, rw, other, len(fired_after)))
        print(f"   LAUNCH {t} EP {ep} {group(ep)[:2]} · start s{j+1} {start} · +{best[0]*100:.0f}% · own 20-session window {own} · re-entry window {rw} · other EP window {other} · lane fires on/after the start {len(fired_after)}")
print('launches:', len(launches), 'of', len(arm40), 'campaigns; outside every recorded window:', sum(not (l[5] or l[6] or l[7]) for l in launches), '(Family A coverage not pulled: the >= 10-launch gate fails first)')
print('per group launches:', dict(C.Counter(group(l[1]) for l in launches)))
print('slow-move question (moves starting in sessions 21-40):', [(l[0], str(l[1]), l[2]) for l in launches if l[2] > 20])

# hand-off exit vs lane trail on first fires of the 40-session campaigns — daily walker, anchored on the lane's own trail R first
def sma(cl, n): return sum(cl[-n:])/n if len(cl) >= n else None
def walk(r, arm, K):
    t = r['ticker']; b = daily[t]; e = f(r['entry_price']); st = f(r['stop_price']); R = e - st
    if R <= 0: return None
    if r['stop_hit_date'] == r['fire_date']: return -1.0, 0, 'stop_d0'
    ss = sess(r['fd']); alld = sorted(b); phase2 = False; below21 = 0
    posthigh = max(b[d]['high_price'] for d in alld if r['ep'] <= d <= r['fd'])
    def trail_break(d):
        cl = [b[x]['close'] for x in alld if x <= d]; s10, s20 = sma(cl, 10), sma(cl, 20)
        line = max(x for x in (s10, s20) if x is not None) if (s10 or s20) else None
        return line is not None and b[d]['close'] < line
    if trail_break(r['fd']) and arm in ('trail', 'handoff'): return (b[r['fd']]['close']-e)/R, 0, 'trail_d0'
    for i, d in enumerate(ss, 1):
        if d not in b: return None
        if b[d]['low_price'] <= st: return -1.0, i, 'stop'
        cl = [b[x]['close'] for x in alld if x <= d]
        if arm == 'handoff' and not phase2 and (b[d]['high_price'] >= e + 3*R or b[d]['high_price'] > posthigh): phase2 = True; ho = i
        posthigh = max(posthigh, b[d]['high_price'])
        if arm == 'handoff' and phase2:
            s21 = sma(cl, 21); below21 = below21 + 1 if (s21 is not None and b[d]['close'] < s21) else 0
            if below21 >= 2: return (b[d]['close']-e)/R, i, 'sma21_2x'
        elif trail_break(d): return (b[d]['close']-e)/R, i, 'trail'
        if K and i >= K and not (arm == 'handoff' and phase2): return (b[d]['close']-e)/R, i, 'time'
    return (b[ss[-1]]['close']-e)/R if ss else None, len(ss), 'open_mark'
F40 = [r for r in F1 if (r['ticker'], r['ep']) in set(arm40) and r['realized_r_trail'] != '']
ok = bad = 0; diffs = []
for r in F40:
    w = walk(r, 'trail', 20)
    if w is None: continue
    if abs(w[0] - f(r['realized_r_trail'])) < 0.02: ok += 1
    else: bad += 1; diffs.append((r['ticker'], r['fire_date'], r['rung'], round(w[0], 2), w[2], r['realized_r_trail'], r['outcome_trail']))
print(f"\nANCHOR: my daily trail walker vs the lane's recorded realized_r_trail on {len(F40)} first fires: match {ok}, differ {bad}")
for d in diffs[:25]: print('   differ', d)
res = [(r, walk(r, 'handoff', 20)) for r in F40]
print('hand-off (lane trail until +3R or a new post-EP high, then two closes under the 21-day; no cap; marked 11-13 if open) vs lane trail, incumbent stop, per group:')
for g in GN[:3] + ['ALL (labelled count only)']:
    S = [(r, w) for r, w in res if w and (g.startswith('ALL') or group(r['ep']) == g)]
    print('   ', g, '| n', len(S), '| lane trail mean', f"{mean([f(r['realized_r_trail']) for r, w in S]):+.2f}", '>=3R', sum(f(r['realized_r_trail']) >= 3 for r, w in S),
          '| hand-off mean', f"{mean([w[0] for r, w in S]):+.2f}", '>=3R', sum(w[0] >= 3 for r, w in S), '| still open', sum(w[2] == 'open_mark' for r, w in S))
for r, w in res:
    if w and (w[0] >= 2 or f(r['realized_r_trail']) >= 2): print('     ', r['ticker'], r['ep_date'], r['rung'], r['fire_date'], 'lane trail', r['realized_r_trail'], 'hand-off', round(w[0], 2), w[2], 's', w[1])
