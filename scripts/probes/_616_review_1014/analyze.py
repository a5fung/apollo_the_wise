"""#616 pre-registered read (2026-10-14). Input: q2_rows.out (CSV, first attempts, prod read-only capture).
Pre-registration: data_gated_reviews.yaml delayed_entry_adr_stop_variant_616 action_when_ready.
Judged set: ep_low_reclaim, reentry_shape='first', fire_date>=2026-09-02, live-EP row, 20 sessions elapsed
(sess_after_fire>=20 on the SPY clock), incumbent + 075 + 100 trail arms all settled (not unscoreable)."""
import io, sys
import pandas as pd, numpy as np

raw = open('q2_rows.out').read()
df = pd.read_csv(io.StringIO(raw))
for c in df.columns:
    if pd.api.types.is_string_dtype(df[c]) and len(df[c].dropna()) and set(df[c].dropna().unique()) <= {'t', 'f'}:
        df[c] = df[c].map({'t': True, 'f': False})
df['fire_date'] = pd.to_datetime(df['fire_date'])
df['month'] = df['fire_date'].dt.strftime('%Y-%m')
df['campaign'] = df['ticker'] + ' ' + df['ep_date']
print(f"last_bar={df['last_bar'].iloc[0]}  rows={len(df)}  all live_ep={bool(df['live_ep'].all())}")

ARMS = [('incumbent', 'realized_r_trail', 'realized_r', 'stop_width_pct', 'outcome_trail', 'reached_4r'),
        ('0.75xADR', 'realized_r_trail_075', 'realized_r_075', 'stop_width_pct_075', 'outcome_trail_075', 'reached_4r_075'),
        ('1.00xADR', 'realized_r_trail_100', 'realized_r_100', 'stop_width_pct_100', 'outcome_trail_100', 'reached_4r_100')]

def judged(d):
    d = d[(d.fire_date >= '2026-09-02') & d.live_ep & (d.sess_after_fire >= 20)]
    ok = d['realized_r_trail'].notna() & d['realized_r_trail_075'].notna() & d['realized_r_trail_100'].notna()
    ok &= ~d[['outcome_trail', 'outcome_trail_075', 'outcome_trail_100']].isin(['unscoreable']).any(axis=1)
    return d[ok], d

def arm_stats(m, name, rc, nc, wc, oc, fc):
    r = m[rc]; pct = r * m[wc]            # % of entry per fire (width% x R) - unit-free across stop bands
    best = m.loc[r.idxmax(), 'campaign'] if len(m) else None
    rest = m[m.campaign != best]
    return dict(arm=name, n=len(m), mean_R=r.mean(), median_R=r.median(), sum_R=r.sum(),
                win_rate=(r > 0).mean(), stops=int((m[oc] == 'stop').sum()), trail_exits=int((m[oc] == 'trail_exit').sum()),
                time_exits=int((m[oc] == 'time_exit').sum()), reached_4R=int(m[fc].sum()), max_R=r.max(), min_R=r.min(),
                mean_pct_of_entry=pct.mean(), median_pct_of_entry=pct.median(),
                best_campaign=best, best_R=r.max(), mean_R_drop_best=rest[rc].mean() if len(rest) else np.nan,
                sum_R_drop_best=rest[rc].sum() if len(rest) else np.nan, mean_none_arm_R=m[nc].mean(),
                top1_share_of_positive_sum=(r.max() / r[r > 0].sum()) if (r > 0).any() else np.nan)

def block(title, m):
    print(f"\n=== {title}  (n={len(m)}, campaigns={m.campaign.nunique()}, months={sorted(m.month.unique())})")
    if len(m) == 0:
        print('  (empty)'); return None
    t = pd.DataFrame([arm_stats(m, *a) for a in ARMS]).set_index('arm')
    with pd.option_context('display.width', 250, 'display.max_columns', 40, 'display.float_format', lambda x: f'{x:,.3f}'):
        print(t.T.to_string())
    print('  monthly trail-arm sum R (n):')
    for mo, g in m.groupby('month'):
        print(f"    {mo}: " + ' | '.join(f"{a[0]} {g[a[1]].sum():+.2f}R" for a in ARMS) + f"  (n={len(g)})")
    for v, rc in (('0.75xADR', 'realized_r_trail_075'), ('1.00xADR', 'realized_r_trail_100')):
        dlt = m[rc] - m['realized_r_trail']
        print(f"  paired {v} - incumbent (trail, R own units): mean {dlt.mean():+.3f}  median {dlt.median():+.3f}  "
              f"variant>inc {int((dlt > 1e-9).sum())}  variant<inc {int((dlt < -1e-9).sum())}  tie {int((dlt.abs() <= 1e-9).sum())}")
    return t

# ---------- 1. POPULATION FIRST ----------
print('\n##### 1. POPULATION (before any outcome number)')
ep = df[(df.fire_date >= '2026-09-02') & (df.rung == 'ep_low_reclaim')]
print(f"ep_low_reclaim first attempts, fire_date>=09-02, live-EP: {len(ep)} rows, {ep.campaign.nunique()} campaigns, months={ep.month.value_counts().sort_index().to_dict()}")
print(f"  excluded as not prospective (fire_date<09-02): {len(df[(df.fire_date < '2026-09-02') & (df.rung == 'ep_low_reclaim')])}")
print(f"  20 sessions elapsed (mature): {(ep.sess_after_fire >= 20).sum()}   immature: {(ep.sess_after_fire < 20).sum()}")
m_all, _ = judged(df[df.rung == 'ep_low_reclaim'])
mature = ep[ep.sess_after_fire >= 20]
print(f"  mature but not all three arms settled/scoreable (excluded, would be listed): "
      f"{len(mature) - len(m_all)}")
print(f"  pattern_version={ep.pattern_version.unique().tolist()}  settle_version(inc)={ep.settle_version.unique().tolist()} "
      f"v075={ep.settle_version_075.dropna().unique().tolist()} v100={ep.settle_version_100.dropna().unique().tolist()}  ep_adr20_n null={int(ep.ep_adr20_n.isna().sum())}")
print('  judged fires:')
print(m_all[['ticker', 'ep_date', 'fire_date', 'sess_after_fire', 'stop_width_pct', 'stop_width_pct_075', 'stop_width_pct_100',
             'outcome_trail', 'realized_r_trail', 'outcome_trail_075', 'realized_r_trail_075', 'outcome_trail_100', 'realized_r_trail_100']]
      .to_string(index=False, float_format=lambda x: f'{x:.3f}'))

# ---------- 2. THE PRE-REGISTERED READ ----------
print('\n##### 2. PRE-REGISTERED READ: ep_low_reclaim first attempts, mature only, trail arm')
t = block('ep_low_reclaim / first / prospective / MATURE', m_all)

# ---------- 3. SECONDARY RUNGS ----------
print('\n##### 3. SECONDARY RUNGS (same rule, mature only)')
for rung in ['ep_close_reclaim', 'ep_close_620_prox', 'ep_high_break']:
    mm, _ = judged(df[df.rung == rung]); block(rung, mm)

# ---------- 4. Contrast: why immature is not judged ----------
print('\n##### 4. NOT JUDGED - immature-settled contrast (ep_low_reclaim, 0.75xADR trail arm)')
im = ep[(ep.sess_after_fire < 20) & ep.realized_r_trail_075.notna()]
print(f"  immature rows already settled on 0.75: n={len(im)}  stop share={(im.outcome_trail_075=='stop').mean():.0%}  "
      f"mean R={im.realized_r_trail_075.mean():+.3f}   (mature: stop share={(m_all.outcome_trail_075=='stop').mean():.0%}, mean R={m_all.realized_r_trail_075.mean():+.3f})")
print(f"  immature rows still OPEN on 0.75 (ep_low_reclaim): {int(((ep.sess_after_fire<20)&ep.realized_r_trail_075.isna()).sum())} of {int((ep.sess_after_fire<20).sum())}")

# ---------- 5. Accrual / next read ----------
print('\n##### 5. ACCRUAL')
fires = ep.groupby(ep.fire_date.dt.to_period('W')).size()
n = len(ep); first, last = ep.fire_date.min(), pd.Timestamp(df['last_bar'].iloc[0])
# sessions on SPY clock between 09-02 and last bar
sess = 28  # 09-02 .. 10-13 inclusive = 29 sessions (see q0 calendar)
rate = n / 29
print(f"  ep_low_reclaim first fires since 09-02: {n} over 29 sessions = {rate:.2f}/session = {rate*21:.1f}/month")
need = 30
# session index (from 09-02 = 1) when the need-th fire is expected, then +20 sessions to mature
k = need / rate
print(f"  30th fire expected ~session {k:.0f} after 09-02; matures 20 sessions later -> ~session {k+20:.0f}")
holidays = {pd.Timestamp('2026-11-26'), pd.Timestamp('2026-12-25')}
days = [d for d in pd.bdate_range('2026-09-02', '2027-01-15') if d not in holidays and d != pd.Timestamp('2026-09-07')]
print(f"  -> calendar date of that session: {days[int(round(k+20))-1].date()}")
oct_end = pd.Timestamp('2026-10-30'); idx = [i for i,d in enumerate(days) if d==oct_end][0]
print(f"  all October fires (through 10-30) mature after session idx +20 -> {days[idx+20].date()} (20th session after 10-30)")
