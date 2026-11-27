"""Diagnosis of the two centring misses (outcome-free; table + RNG only)."""
import numpy as np, sys
sys.argv=['x']
import s2_calib as S, s2lib as L
P=print
DD,col=L.pop_frame(S.D,'f20'); pop=S.Pop(DD,col)
top,bot=pop.sets['all']
y2020=pop.ey==2020
P(f"f20 discovery: top third {top.sum()} events ({(top&y2020).sum()} in 2020 = {(top&y2020).sum()/top.sum():.3f}); bottom third {bot.sum()} ({(bot&y2020).sum()} in 2020 = {(bot&y2020).sum()/bot.sum():.3f})")
for mult in (1.0,3.0):
    pb=0.05*np.where(y2020,mult,1.0); P(f"  composition-expected ratio with 2020 at {mult}x: {pb[top].mean()/pb[bot].mean():.4f}")
P("  month-level: share of the month's events in the top third minus in the bottom third, by year (ties move the top block):")
for y in (2017,2018,2019,2020):
    m=pop.ey==y; P(f"    {y}: top {(top&m).sum()/m.sum():.3f} bottom {(bot&m).sum()/m.sum():.3f}")
DD,col=L.pop_frame(S.C,'f24a'); pop=S.Pop(DD,col)
for e in 'AB':
    t,b=pop.sets['era'+e]; P(f"f24a check era {e}: events {(DD.era==e).sum()}, top {t.sum()}, bottom {b.sum()}")
rng=np.random.default_rng(7)
for p in (0.03,0.05,0.08):
    t,b=pop.sets['eraB']; nt,nb=t.sum(),b.sum()
    w=rng.binomial(nt,p,200000); v=rng.binomial(nb,p,200000)
    r=L.ratio_counts(w,nt,v,nb); P(f"  pure binomial draws (no months, no noise) at {p:.0%}: median ratio {np.median(r):.3f}, mean winners per third {nt*p:.1f}/{nb*p:.1f}, share with a zero {((w==0)|(v==0)).mean():.3f}")
