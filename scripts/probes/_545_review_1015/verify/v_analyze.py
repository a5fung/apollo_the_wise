"""#545-025 verifier (2026-10-15). Independent of the reader's analyze.py / v_walk.py: own parse of v2_rows.out + v3_bars.out,
own walk written from agents/market_intelligence/delayed_entry_shadow.py::compute_settlement (day0_needs_minutes abstain rule,
trigger's own day-0 OHLC first, pess stop-first, MAX(SMA10,SMA20) incl. own close, 20-session hold), every arm, every row."""
import io, math
import pandas as pd

def load(fn, key):
    t = open(fn).read(); t = t[t.index(key):]
    return pd.read_csv(io.StringIO(t))
R = load('v2_rows.out', 'id,rung')
B = load('v3_bars.out', 'ticker,trade_date')
for c in R.columns:
    if pd.api.types.is_string_dtype(R[c]) and len(R[c].dropna()) and set(R[c].dropna().unique()) <= {'t', 'f'}:
        R[c] = R[c].map({'t': True, 'f': False})
spy_dates = None
E = R[R.fire_date >= '2026-09-02'].copy()
print(f"POPULATION: ep_low_reclaim first attempts fired >=09-02: {len(E)} rows, {E.groupby(['ticker','ep_date']).ngroups} campaigns, "
      f"months {E.fire_date.str[:7].value_counts().sort_index().to_dict()}, range {E.fire_date.min()}..{E.fire_date.max()}; before 09-02: {(R.fire_date < '2026-09-02').sum()}")
E['mature'] = E.spy_after >= 20
print(f"  mature(>=20 SPY sessions): {E.mature.sum()}  fire dates {E[E.mature].fire_date.value_counts().sort_index().to_dict()}  immature {(~E.mature).sum()}")

# ---- independent walk ----
bars = {tk: g.sort_values('trade_date') for tk, g in B.groupby('ticker')}
LAST = '2026-10-14'
ASSUMED = set()
def line(cl):
    s10 = sum(cl[-10:]) / 10 if len(cl) >= 10 else None
    s20 = sum(cl[-20:]) / 20 if len(cl) >= 20 else None
    if s20 is not None: return s10 if (s10 is not None and s10 > s20) else s20
    return s10
def walk(r, stop):
    entry = r.entry_price; risk = entry - stop
    if risk <= 0: return ('unscoreable', None, 'unscoreable', None)
    g = bars[r.ticker]; fd = r.fire_date
    pre = g[(g.trade_date < fd) & (g.trade_date >= str((pd.Timestamp(fd) - pd.Timedelta(days=60)).date()))].close.tolist()
    post = g[(g.trade_date > fd) & (g.trade_date <= LAST)]
    flo, fc = r.day_low, r.day_close
    none_o = none_r = tr_o = tr_r = None
    fm = r.fire_minute_et
    if not pd.isna(fm) and flo <= stop:          # day0_needs_minutes
        if r.day0_resolved is not True:
            ASSUMED.add((r.ticker, r.fire_date))   # minutes were (or will be) in scope at the incumbent's settle but not cached: assume no post-fire touch
        elif not pd.isna(r.day0_post_low) and r.day0_post_low <= stop:
            return ('stop', -1.0, 'stop', -1.0)
    elif pd.isna(fm) and flo <= stop:
        return ('stop', -1.0, 'stop', -1.0)
    cl = pre + [fc]
    ln = line(cl)
    if ln is not None and fc < ln: tr_o, tr_r = 'trail_exit', (fc - entry) / risk
    for i, b in enumerate(post.itertuples(), 1):
        if i > 20: break
        cl.append(b.close)
        if b.low_price <= stop:
            none_o, none_r = 'stop', -1.0
            if tr_o is None: tr_o, tr_r = 'stop', -1.0
            break
        if tr_o is None:
            ln = line(cl)
            if ln is not None and b.close < ln: tr_o, tr_r = 'trail_exit', (b.close - entry) / risk
        if i == 20:
            none_o, none_r = 'time_exit', (b.close - entry) / risk
            if tr_o is None: tr_o, tr_r = 'time_exit', none_r
    if none_o is None: return ('OPEN', None, tr_o or 'OPEN', tr_r)
    return (none_o, none_r, tr_o, tr_r)

ARMS = [('inc', 'stop_price', 'outcome', 'realized_r', 'outcome_trail', 'realized_r_trail'),
        ('025', 'stop_price_025', 'outcome_025', 'realized_r_025', 'outcome_trail_025', 'realized_r_trail_025'),
        ('075', 'stop_price_075', 'outcome_075', 'realized_r_075', 'outcome_trail_075', 'realized_r_trail_075')]
mm = 0; checked = 0; notes = []
for r in E.itertuples():
    for a, sc, on, rn, ot, rt in ARMS:
        st = getattr(r, sc)
        stored = (getattr(r, on), getattr(r, rn), getattr(r, ot), getattr(r, rt))
        if pd.isna(st):
            notes.append(f"{r.ticker} {r.fire_date} {a}: no stop stamped; stored={stored[0]}/{stored[2]}"); continue
        w = walk(r, st)
        if isinstance(stored[0], str) and stored[0] not in ('unscoreable',):
            checked += 1
            ok = (w[0] == stored[0] and w[2] == stored[2] and abs((w[1] or 0) - stored[1]) < 2e-3 and abs((w[3] or 0) - stored[3]) < 2e-3)
            if not ok: mm += 1; notes.append(f"MISMATCH {r.ticker} {r.fire_date} {a}: walk={w} stored={stored}")
        else:
            notes.append(f"{r.ticker} {r.fire_date} sess={r.spy_after} {a}: stored open/unsc={stored[0]}; walk says {w[0]}/{w[2]}")
print(f"  ASSUMPTION: rows whose day-0 minutes were needed but NOT cached are walked assuming no post-fire touch (production had the minutes in scope at the incumbent settle): {len(ASSUMED)}: {sorted(ASSUMED)}")
print(f"\nINDEPENDENT WALK: {checked} stored settlements (all arms, both exits) re-walked, mismatches={mm}")
for n in notes: print('  ', n)

# ---- judged set ----
J = E[E.mature & E.realized_r_trail.notna() & E.realized_r_trail_025.notna() & E.realized_r_trail_075.notna()].copy()
print(f"\nJUDGED SET n={len(J)}: {list(zip(J.ticker, J.fire_date))}")
excl = E[E.mature & ~E.index.isin(J.index)]
print(f"  mature excluded: {list(zip(excl.ticker, excl.fire_date, excl.outcome_trail_025))}")
for a, sc, on, rn, ot, rt in ARMS:
    x = J[rt]; h = J[rn]; w = {'inc': 'stop_width_pct', '025': 'stop_width_pct_025', '075': 'stop_width_pct_075'}[a]
    best = x.idxmax()
    print(f"  {a}: trail mean {x.mean():+.3f} median {x.median():+.3f} sum {x.sum():+.3f} winners {(x>0).sum()} "
          f"stops {(J[ot]=='stop').sum()} trail_exits {(J[ot]=='trail_exit').sum()} best {J.loc[best,'ticker']} {x.max():+.3f} "
          f"drop-best mean {x.drop(best).mean():+.3f} | hold-only mean {h.mean():+.3f} median {h.median():+.3f} stops {(J[on]=='stop').sum()} "
          f"| price %/fire {(x*J[w]).mean():+.3f}")
for ref, col in (('inc', 'realized_r_trail'), ('075', 'realized_r_trail_075')):
    d = J.realized_r_trail_025 - J[col]
    print(f"  paired 025 trail - {ref} trail: better {(d>1e-9).sum()} tied {(d.abs()<=1e-9).sum()} worse {(d<-1e-9).sum()} mean {d.mean():+.3f}")
print(f"  widths: incumbent stop width pct {J.stop_width_pct.round(3).tolist()}  025 width {J.stop_width_pct_025.round(3).tolist()}")
print(f"  025 wider than incumbent on {(J.stop_width_pct_025 > J.stop_width_pct).sum()} of {len(J)} judged; all prospective w/ stop: {(E.stop_width_pct_025 > E.stop_width_pct).sum()} of {E.stop_price_025.notna().sum()}")

# ---- immature contrast ----
im = E[~E.mature]
ims = im[im.realized_r_trail_025.notna()]
print(f"\nIMMATURE: {len(im)} rows; 025 trail settled {len(ims)} (stops {(ims.outcome_trail_025=='stop').sum()}, mean {ims.realized_r_trail_025.mean():+.3f}); "
      f"025 open {im.realized_r_trail_025.isna().sum()}: {im[im.realized_r_trail_025.isna()].ticker.tolist()}")

# ---- censor class (code rule: minute fire, day_low <= variant stop, incumbent never needed minutes -> no day-0 cache) ----
def cens(r, sc):
    st = getattr(r, sc)
    # strict code rule: the variant needs day-0 minutes (minute fire, day_low <= variant stop) but the INCUMBENT did not
    # (stop_price < day_low), so no minute fetch ever happened and no day-0 cache exists -> abstains to the orphan horizon
    return (not pd.isna(st)) and (not pd.isna(r.fire_minute_et)) and r.stop_price < r.day_low <= st and r.day0_resolved is not True
c25 = [ (r.ticker, r.fire_date) for r in E.itertuples() if cens(r, 'stop_price_025')]
c75 = [ (r.ticker, r.fire_date) for r in E.itertuples() if cens(r, 'stop_price_075')]
print(f"\nCENSORED 025 (never scoreable; day low reached the 025 stop, no day-0 minutes cached): {c25}")
print(f"CENSORED 075: {c75}")
since = E[E.fire_date >= '2026-09-03']
print(f"  fires since 09-03: {len(since)}; never-scoreable on 025 or 075: {len(set(t for t,_ in c25) | set(t for t,_ in c75))}")

# ---- direction of the censored class (025): what the 5 would score if the fire-day touch was pre-fire vs post-fire ----
print("\nCENSORED-025 BOUND (walk from daily bars; 'no post-fire touch' = upper bound, day-0 stop = -1.0R lower bound):")
cz = [r for r in E.itertuples() if (not pd.isna(r.stop_price_025)) and (not pd.isna(r.fire_minute_et)) and r.stop_price < r.day_low <= r.stop_price_025 and r.day0_resolved is not True]
for r in cz:
    w = walk(r, r.stop_price_025)
    print(f"  {r.ticker} {r.fire_date} sess={r.spy_after} fire_min={r.fire_minute_et} day_low={r.day_low} stop025={r.stop_price_025:.3f} stop_inc={r.stop_price}  no-touch walk: none={w[0]} {w[1]}, trail={w[2]} {None if w[3] is None else round(w[3],3)}")
