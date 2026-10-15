"""#545-025 review 2026-10-15 - independent re-walk of the judged fires from raw daily bars (v3_walk.out), written from the
SSoT's stated rules (same rules as scripts/probes/_616_review_1014/verify/v_walk.py, which reproduced QCOM and CRWD):
pess stop-first on the low; day-0 stop test uses the CACHED post-fire low (day0_post_low) when day0_resolved, else assumed
not touched (ALAB: minutes were in scope at settle time, not cached); trail = close < MAX(SMA10, SMA20) incl. the day's own
close (<20 closes -> SMA10; <10 -> none); time exit at session 20's close; R in each stop's own units; stop = -1.0R."""
import io, csv, sys
import pandas as pd

txt = open('v3_walk.out').read()
bars_txt = txt.split('==BARS==')[1].split('==STORED==')[0]
stored_txt = txt.split('==STORED==')[1]
bars = pd.read_csv(io.StringIO(bars_txt.strip()))
stored = pd.read_csv(io.StringIO(stored_txt.strip()))

def line_(cl):
    if len(cl) < 10: return None
    s10 = sum(cl[-10:]) / 10
    if len(cl) < 20: return s10
    return max(s10, sum(cl[-20:]) / 20)

def walk(b, fire, entry, stop, d0_post_low):
    """b = list of (date, high, low, close) sorted. returns {'none': (outcome, R), 'trail': (outcome, R)}"""
    risk = entry - stop
    pre = [c for d, h, l, c in b if d < fire]
    d0 = [x for x in b if x[0] == fire][0]
    post = [x for x in b if x[0] > fire][:20]
    closes = pre + [d0[3]]
    if d0_post_low is not None and d0_post_low <= stop:
        return {'none': ('stop', -1.0), 'trail': ('stop', -1.0), 'sessions': 0}
    trail = None
    ln = line_(closes)
    if ln is not None and d0[3] < ln:
        trail = ('trail_exit', round((d0[3] - entry) / risk, 4))
    none = None
    for i, (d, h, l, c) in enumerate(post, 1):
        closes.append(c)
        if l <= stop:
            none = ('stop', -1.0)
            if trail is None: trail = ('stop', -1.0)
            break
        if trail is None:
            ln = line_(closes)
            if ln is not None and c < ln:
                trail = ('trail_exit', round((c - entry) / risk, 4))
        if i == 20:
            none = ('time_exit', round((c - entry) / risk, 4))
            if trail is None: trail = ('time_exit', round((c - entry) / risk, 4))
    return {'none': none, 'trail': trail, 'sessions': len(post)}

rows = []
bad = 0
for _, s in stored.iterrows():
    tk = s['ticker']
    bb = bars[bars.ticker == tk]
    b = [(r.trade_date, r.high_price, r.low_price, r.close) for r in bb.itertuples()]
    fire = s['fire_date']
    d0low = s['day0_post_low'] if str(s['day0_resolved']) == 't' else None
    for arm, stopcol, oc_none, r_none, oc_tr, r_tr in [
        ('inc', 'stop_price', 'outcome', 'realized_r', 'outcome_trail', 'realized_r_trail'),
        ('025', 'stop_price_025', 'outcome_025', 'realized_r_025', 'outcome_trail_025', 'realized_r_trail_025'),
        ('075', 'stop_price_075', 'outcome_075', 'realized_r_075', 'outcome_trail_075', 'realized_r_trail_075')]:
        if pd.isna(s[stopcol]):
            rows.append((tk, arm, 'NOT RECORDED (no stop stamped)', '', '', '')); continue
        w = walk(b, fire, float(s['entry_price']), float(s[stopcol]), d0low)
        got_t, got_n = w['trail'], w['none']
        st_t = (s[oc_tr], s[r_tr]); st_n = (s[oc_none], s[r_none])
        ok_t = got_t is not None and got_t[0] == st_t[0] and abs(got_t[1] - float(st_t[1])) < 0.002
        ok_n = got_n is not None and got_n[0] == st_n[0] and abs(got_n[1] - float(st_n[1])) < 0.002
        if not (ok_t and ok_n): bad += 1
        rows.append((tk, arm, f'trail walk={got_t} stored={tuple(st_t)} {"OK" if ok_t else "MISMATCH"}',
                     f'none walk={got_n} stored={tuple(st_n)} {"OK" if ok_n else "MISMATCH"}', f'sessions_after_fire_in_bars={w["sessions"]}', ''))
for r in rows:
    print(' | '.join(str(x) for x in r if x != ''))
print(f'\nmismatches: {bad}')
