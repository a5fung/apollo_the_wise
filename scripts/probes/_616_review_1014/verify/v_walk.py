"""Verifier's own re-walk of QCOM 09-10 and CRWD 09-02 from raw daily bars (v3_walk.out), written from the
SSoT's stated rules, not by importing the lane code: pess stop-first on the low; trail = close < MAX(SMA10,SMA20)
incl. the day's own close (<20 closes -> SMA10; <10 -> none); time exit at session 20's close; R in each stop's units."""
import re
txt = open('v3_walk.out').read()
def bars(tag):
    sec = txt.split(tag)[1].split('==')[0]
    out = []
    for line in sec.splitlines():
        m = re.match(r'\s*(\d{4}-\d\d-\d\d)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)', line)
        if m: out.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))))
    return out
def line_(cl):
    if len(cl) < 10: return None
    s10 = sum(cl[-10:]) / 10
    if len(cl) < 20: return s10
    return max(s10, sum(cl[-20:]) / 20)
def walk(b, fire, entry, stop, day0_low):
    risk = entry - stop
    pre = [c for d, h, l, c in b if d < fire]
    d0 = [x for x in b if x[0] == fire][0]
    post = [x for x in b if x[0] > fire][:20]
    res = {}
    closes = pre + [d0[3]]
    trail = None
    if day0_low <= stop: return {'none': ('stop', 0, -1.0), 'trail': ('stop', 0, -1.0)}
    ln = line_(closes)
    if ln is not None and d0[3] < ln: trail = ('trail_exit', 0, (d0[3] - entry) / risk)
    mfe = d0[1]; reached4 = False; none = None
    for i, (d, h, l, c) in enumerate(post, 1):
        closes.append(c)
        if l <= stop:
            none = ('stop', i, d, -1.0)
            if trail is None: trail = ('stop', i, d, -1.0)
            break
        mfe = max(mfe, h)
        if h >= entry + 4 * risk: reached4 = True
        if trail is None:
            ln = line_(closes)
            if ln is not None and c < ln: trail = ('trail_exit', i, d, round((c - entry) / risk, 4))
        if i == 20:
            none = ('time_exit', i, d, round((c - entry) / risk, 4))
            if trail is None: trail = ('time_exit', i, d, round((c - entry) / risk, 4))
    return {'none': none, 'trail': trail, 'reached4': reached4, 'sessions_walked': len(post)}
q = bars('W1. QCOM'); c = bars('W2. CRWD')
for name, b, fire, entry, stops, d0low in [
    ('QCOM', q, '2026-09-10', 172.24, {'inc': 172.002, '075': 168.42639874028302, '100': 167.15519832037737}, 171.0),
    ('CRWD', c, '2026-09-02', 206.5, {'inc': 204.4003, '075': 199.04505455693734, '100': 196.56007274258315}, 200.6)]:
    print(name, 'bars before fire', len([x for x in b if x[0] < fire]), 'after', len([x for x in b if x[0] > fire]))
    for k, s in stops.items():
        print('  ', k, f'stop {s:.2f}', walk(b, fire, entry, s, d0low))
