"""delayed_entry_mid_november_reread — 2026-11-16. Read-only, $0, measurement only (THE LINE: nothing changed/proposed).

PRE-REGISTRATION OF RECORD = docs/analysis/327_hypotheses_2026-09-27.md §7 (written 09-27). Rules restated here BEFORE any
result was computed in this folder:
  * Unit = campaign = one live-source mi_ep_alerts row per (ticker, alert_date), alert_date >= 2026-08-22, with >= 15
    sessions after the EP day by 11-15 (last bar 2026-11-13). Campaigns with no lane fire stay in the population.
  * GROUPS (never pooled, §7 rule 1): split at the EP-rule changes 08-29 (extension cap revert), 09-14 (theme-bonus fix),
    10-04 (#692 M&A filter deployed), 10-10 (#624 small-cap paper lane / #694 ranking / Benzinga source).
    Each bar applies INSIDE a group. An all-groups figure is a labelled count only and can never rescue a bar.
  * PRIMARY readable only with >= 3 winner campaigns in a group; below that: report the count and stop.
    Winner = FAST label (highest high of sessions 1-15 >= +50% over EP close AND s15 close >= +30%) or, where 40
    sessions exist, SLOW label (s40 close >= +25% and above the 50-day average) — h6_run.labels_for, copied verbatim.
    His labelled EPs (operator_labelled_eps.md) are co-primary: flagged, never graded.
    "Kept" = a FIRST-attempt fire ending >= 3R on the lane's arm (stop + trail), per recorded stop (incumbent/_025/_075/_100).
  * DIRECTION checks (a)-(d): a sign only at >= 30 first-attempt fires per cell (pattern x group); otherwise counts.
  * H6: campaigns with >= 40 sessions; launch = +50% from a post-EP low (sessions 1-40, high in a later session);
    bar needs >= 10 launches (>= half outside every attempt window); hand-off exit bar is on WINNER fires.
  * Fires whose 20-session window has not closed are losers-first: open rows are counted separately, never in a mean.
"""
import csv, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent
D = dt.date.fromisoformat
CUTS = [D('2026-08-29'), D('2026-09-14'), D('2026-10-04'), D('2026-10-10')]
GN = ['G1 08-22..08-28', 'G2 08-29..09-13', 'G3 09-14..10-03', 'G4 10-04..10-09', 'G5 10-10+']
def group(ep): return GN[sum(ep >= c for c in CUTS)]
def rd(name):
    txt = (HERE / name).read_text().split('\n')
    i = next(k for k, l in enumerate(txt) if '|' in l)
    return [r for r in csv.DictReader(txt[i:], delimiter='|') if None not in r.values() and len(r) > 1]
def f(v): return float(v) if v not in ('', None) else None
def load():
    al = rd('q1_alerts.out'); camps = {}
    for r in al:
        if r['source'] != 'live': continue
        camps.setdefault((r['ticker'], D(r['alert_date'])), r)
    daily = {}
    for r in rd('q3_daily.out'):
        daily.setdefault(r['ticker'], {})[D(r['trade_date'])] = {k: float(r[k]) for k in ('open_price', 'high_price', 'low_price', 'close')}
    cal = sorted({d for b in daily.values() for d in b})
    trig = rd('q2_trigger.out')
    for r in trig:
        r['ep'] = D(r['ep_date']); r['fd'] = D(r['fire_date'])
    return camps, daily, cal, trig
