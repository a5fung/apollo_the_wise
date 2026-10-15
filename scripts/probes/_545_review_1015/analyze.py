"""#545-025 pre-registered read (2026-10-15). Input: q2_rows.out (CSV, first attempts, prod read-only capture, last SPY bar 2026-10-14).
Pre-registration: data_gated_reviews.yaml delayed_entry_adr_stop_variant_025_545 (question + action_when_ready + can_fire.instrument_trusted).
Judged set: ep_low_reclaim, reentry_shape='first', fire_date>=2026-09-02, live-EP row, 20 SPY sessions elapsed (sess_after_fire>=20),
incumbent + 025 + 075 trail arms all settled (not unscoreable) - the arms the action says to read on the SAME fires.
Bar (threshold) = 30 judged fires. Nothing here changes admission/stop (THE LINE)."""
import io
import pandas as pd, numpy as np

raw = open('q2_rows.out').read()
raw = raw[raw.index('id,rung'):]
df = pd.read_csv(io.StringIO(raw))
for c in df.columns:
    if pd.api.types.is_string_dtype(df[c]) and len(df[c].dropna()) and set(df[c].dropna().unique()) <= {'t', 'f'}:
        df[c] = df[c].map({'t': True, 'f': False})
df['fire_date'] = pd.to_datetime(df['fire_date'])
df['month'] = df['fire_date'].dt.strftime('%Y-%m')
df['campaign'] = df['ticker'] + ' ' + df['ep_date']
print(f"last_bar={df['last_bar'].iloc[0]}  first-attempt rows pulled (all rungs, fire>=08-28)={len(df)}")

# arm: name, trail R, none R, width%, trail outcome, none outcome, reached4R
ARMS = [('incumbent', 'realized_r_trail', 'realized_r', 'stop_width_pct', 'outcome_trail', 'outcome', 'reached_4r'),
        ('0.25xADR', 'realized_r_trail_025', 'realized_r_025', 'stop_width_pct_025', 'outcome_trail_025', 'outcome_025', 'reached_4r_025'),
        ('0.75xADR', 'realized_r_trail_075', 'realized_r_075', 'stop_width_pct_075', 'outcome_trail_075', 'outcome_075', 'reached_4r_075')]

E = df[(df.rung == 'ep_low_reclaim') & (df.fire_date >= '2026-09-02')].copy()

# ---------- 1. POPULATION FIRST ----------
print('\n##### 1. POPULATION (before any outcome number)')
print(f"ep_low_reclaim first attempts, fire_date>=09-02: {len(E)} rows, {E.campaign.nunique()} campaigns, all live-EP={bool(E.live_ep.all())}, months={E.month.value_counts().sort_index().to_dict()}")
print(f"  excluded as not prospective (fire_date<09-02): {len(df[(df.fire_date < '2026-09-02') & (df.rung == 'ep_low_reclaim')])}")
print(f"  pattern_version={E.pattern_version.unique().tolist()}  settle_version_025={E.settle_version_025.dropna().unique().tolist()}  ep_adr20_n null={int(E.ep_adr20_n.isna().sum())}")
E['mature'] = E.sess_after_fire >= 20
print(f"  20 SPY sessions elapsed (mature): {int(E.mature.sum())}   immature: {int((~E.mature).sum())}")
print('  fire days of the mature rows:', E[E.mature].fire_date.dt.strftime('%m-%d').value_counts().sort_index().to_dict())
def state(r, oc, rr):
    if r[oc] == 'unscoreable': return 'unscoreable'
    if pd.notna(r[rr]): return 'settled'
    return 'open'
for a in ARMS:
    s = E.apply(lambda r: state(r, a[4], a[1]), axis=1)
    sm = s[E.mature]
    print(f"  {a[0]:9s} trail arm: all fires {s.value_counts().to_dict()}   | mature fires {sm.value_counts().to_dict()}")
mature_bad = E[E.mature & ~(E.realized_r_trail.notna() & E.realized_r_trail_025.notna() & E.realized_r_trail_075.notna())]
print(f"  mature but not all three arms settled (excluded from the judged set): {len(mature_bad)}  {mature_bad[['ticker','fire_date','outcome_trail_025','settle_version_025']].astype(str).values.tolist()}")

# precise censor rule (code: minutes fetched only when the INCUMBENT needs them): minute fire AND stop_inc < day_low <= stop_variant AND no cached day-0
def censored(r, stopcol):
    if pd.isna(r[stopcol]) or pd.isna(r.fire_minute_et): return False
    return bool(r.stop_price < r.day_low <= r[stopcol]) and not (r.day0_resolved is True)
E['cens025'] = E.apply(lambda r: censored(r, 'stop_price_025'), axis=1)
E['cens075'] = E.apply(lambda r: censored(r, 'stop_price_075'), axis=1)
E['norec025'] = E.stop_price_025.isna()
print('  rows that can NEVER score the 0.25xADR arm (no stop on file, or fire-day low reached the 025 stop but not the incumbent\'s and no day-0 minutes cached):')
for r in E[E.cens025 | E.norec025].itertuples():
    why = 'no 025 stop recorded (025 columns first stamped on the 09-03 run)' if r.norec025 else 'censored by rule'
    print(f"     {r.ticker} fired {r.fire_date:%m-%d} sess={r.sess_after_fire} mature={r.mature} 025state={r.outcome_trail_025 if isinstance(r.outcome_trail_025,str) else 'open'}  -> {why}")
print('  rows that can NEVER score the 0.75xADR arm:', E[E.cens075].ticker.tolist())

# ---------- 2. THE PRE-REGISTERED READ ----------
J = E[E.mature & E.realized_r_trail.notna() & E.realized_r_trail_025.notna() & E.realized_r_trail_075.notna()
      & ~E[['outcome_trail', 'outcome_trail_025', 'outcome_trail_075']].isin(['unscoreable']).any(axis=1)].copy()
print(f'\n##### 2. PRE-REGISTERED READ: ep_low_reclaim first attempts, MATURE, three arms settled - n={len(J)} vs bar 30')
print(J[['ticker', 'ep_date', 'fire_date', 'sess_after_fire', 'stop_width_pct', 'stop_width_pct_025', 'stop_width_pct_075',
         'outcome_trail', 'realized_r_trail', 'outcome_trail_025', 'realized_r_trail_025', 'realized_r_025',
         'outcome_trail_075', 'realized_r_trail_075', 'realized_r_075']].to_string(index=False, float_format=lambda x: f'{x:.3f}'))

def stats(m, name, rt, rn, wc, ot, on, f4):
    r = m[rt]; pct = r * m[wc]
    best = m.loc[r.idxmax(), 'campaign']
    rest = m[m.campaign != best]
    return dict(arm=name, n=len(m), mean_trail_R=r.mean(), median_trail_R=r.median(), sum_trail_R=r.sum(), winners=int((r > 0).sum()),
                stops=int((m[ot] == 'stop').sum()), trail_exits=int((m[ot] == 'trail_exit').sum()), time_exits=int((m[ot] == 'time_exit').sum()),
                max_R=r.max(), min_R=r.min(), mean_pct_of_entry=pct.mean(), best=best,
                mean_trail_R_drop_best=rest[rt].mean(), sum_trail_R_drop_best=rest[rt].sum(),
                mean_none_R=m[rn].mean(), median_none_R=m[rn].median(), none_stops=int((m[on] == 'stop').sum()), none_winners=int((m[rn] > 0).sum()),
                reached_4R=int(m[f4].sum()))
t = pd.DataFrame([stats(J, *a) for a in ARMS]).set_index('arm')
with pd.option_context('display.width', 250, 'display.max_columns', 40, 'display.float_format', lambda x: f'{x:,.3f}'):
    print(t.T.to_string())
print('  monthly (trail sum R): ' + '; '.join(f"{mo}: " + ' | '.join(f"{a[0]} {g[a[1]].sum():+.2f}R" for a in ARMS) + f" (n={len(g)})" for mo, g in J.groupby('month')))
for lab, col in (('trail', 'realized_r_trail_025'), ('none', 'realized_r_025')):
    for ref_lab, ref in (('incumbent', 'realized_r_trail'), ('0.75xADR trail', 'realized_r_trail_075')):
        d = J[col] - J[ref]
        print(f"  paired 0.25xADR {lab} - {ref_lab}: mean {d.mean():+.3f} median {d.median():+.3f}  0.25 better on {int((d > 1e-9).sum())}, tied {int((d.abs() <= 1e-9).sum())}, worse on {int((d < -1e-9).sum())}")
print(f"  independent fire days in the judged set: {J.fire_date.nunique()}  ({J.fire_date.dt.strftime('%m-%d').value_counts().sort_index().to_dict()})")
bf_trail, bf_none, bf_n = -32.7, -26.5, 46
print(f"  BACKFILL reference (545_retry_test_2026-09-02.md, 0.25xADR x 1 try, ep_low_reclaim, ex-May, common set n=46) - quoted, never pooled: trail {bf_trail}R = {bf_trail/bf_n:+.2f}R/fire; none {bf_none}R = {bf_none/bf_n:+.2f}R/fire")
print(f"  prospective 0.25xADR single attempt: trail {J.realized_r_trail_025.mean():+.2f}R/fire; none {J.realized_r_025.mean():+.2f}R/fire (n={len(J)})")

# sensitivity: judged without the single winner / with CRWD's missing 025 treated as a day-0 stop (reconstructed, NOT recorded)
x = J[J.campaign != J.loc[J.realized_r_trail_025.idxmax(), 'campaign']]
print(f"  drop-best 0.25xADR trail mean: {x.realized_r_trail_025.mean():+.3f} (n={len(x)}); incumbent drop-best {J[J.campaign != J.loc[J.realized_r_trail.idxmax(),'campaign']].realized_r_trail.mean():+.3f}; 0.75xADR drop-best {J[J.campaign != J.loc[J.realized_r_trail_075.idxmax(),'campaign']].realized_r_trail_075.mean():+.3f}")
c = E[E.ticker == 'CRWD'].iloc[0]
adr_dollar = (c.entry_price - c.stop_price_075) / 0.75
s025_recon = c.entry_price - 0.25 * adr_dollar
print(f"  CRWD (025 not recorded) RECONSTRUCTED stop {s025_recon:.3f} vs cached day-0 post-fire low {c.day0_post_low} -> would have been a day-0 stop: {bool(c.day0_post_low <= s025_recon)}; "
      f"if added as -1.0R: 7-fire mean {(J.realized_r_trail_025.sum() - 1.0) / (len(J) + 1):+.3f}  (reconstructed, not recorded, NOT in the judged set)")

# ---------- 3. Contrast: why immature is not judged ----------
print('\n##### 3. NOT JUDGED - immature-settled contrast (ep_low_reclaim first attempts, 0.25xADR trail arm)')
im = E[(~E.mature) & E.realized_r_trail_025.notna()]
op = E[(~E.mature) & E.realized_r_trail_025.isna() & (E.outcome_trail_025 != 'unscoreable')]
print(f"  immature rows already settled on 0.25: n={len(im)}  stop share={(im.outcome_trail_025=='stop').mean():.0%}  mean R={im.realized_r_trail_025.mean():+.3f}   "
      f"(mature judged: stop share={(J.outcome_trail_025=='stop').mean():.0%}, mean R={J.realized_r_trail_025.mean():+.3f})")
print(f"  immature rows still open on 0.25: {len(op)} of {int((~E.mature).sum())}  -> a tight stop settles FASTEST, so an immature read is the stop-heavy tail")

# ---------- 4. All-shapes view the predicate-as-written counts (first attempts only here; the rest from q0) ----------
print('\n##### 4. Accrual / next read')
n_fires = len(E)
# sessions between 09-02 and last bar on the SPY clock = max(sess_after_fire of the 09-02 fire) + 1
sess_span = int(E.sess_after_fire.max()) + 1
rate = n_fires / sess_span
elig = ~(E.cens025 | E.norec025 | E.cens075)
share = elig[E.fire_date >= '2026-09-03'].mean()           # exclude CRWD (structural, one-off shipping artefact) from the share
rate_recent = E[E.fire_date >= '2026-09-14'].shape[0] / (sess_span - 8)
print(f"  ep_low_reclaim first fires since 09-02: {n_fires} over {sess_span} sessions = {rate:.2f}/session (since 09-14: {rate_recent:.2f}/session)")
print(f"  share that can ever score all three arms (excluding CRWD): {share:.0%}  ({int(elig[E.fire_date>='2026-09-03'].sum())} of {int((E.fire_date>='2026-09-03').sum())})")
hol = {pd.Timestamp(d) for d in ['2026-09-07', '2026-11-26', '2026-12-25', '2027-01-01', '2027-01-18']}
days = [d for d in pd.bdate_range('2026-09-02', '2027-03-31') if d not in hol]
for lab, rt in (('overall rate', rate), ('recent rate', rate_recent)):
    k = 30 / (rt * share)
    print(f"  [{lab} {rt:.2f}/session x scoring share {share:.0%}] 30th scoring fire ~session {k:.0f} after 09-02; matures 20 sessions later -> session {k+20:.0f} = {days[int(round(k+20))-1].date()}")
fires_to_1030 = n_fires + rate * len([d for d in days if pd.Timestamp('2026-10-15') <= d <= pd.Timestamp('2026-10-30')])
print(f"  expected judged count on 2026-12-01 (every fire through 10-30 mature): ~{fires_to_1030 * share:.0f}  (bar 30)")
