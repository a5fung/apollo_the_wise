# Post-hoc MANE bracket (outcome read, labelled): force the 10-20 ordering both ways, then walk today's rule.
import importlib.util, sys, io, contextlib
spec = importlib.util.spec_from_file_location("v", "verify.py"); v = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(v)
from datetime import date
t, d = "MANE", date(2026,10,19)
bars = [dict(hhmm=b["hhmm"], o=float(b["open"]), h=float(b["high"]), l=float(b["low"]), c=float(b["close"])) for b in v.mins[(t, "2026-10-19")]]
H, L = bars[0]["h"], bars[0]["l"]; stop = 2*L-H; planned = H-stop; entry = 115.94; orb_r = entry-L
be_lvl = entry+3*orb_r; t8 = entry+8*orb_r
pb = v.prior_bars(t, d); prior = [b["c"] for b in pb]; adr = v.adr20(pb)
print(f"prior closes n={len(prior)} first {pb[0]['d']} last {pb[-1]['d']} ADR20={adr:.4f} entry line(prior)={v.sma_line(prior):.3f}")
edc = bars[-1]["c"]; print(f"entry-day close {edc} line incl it {v.sma_line(prior+[edc]):.3f} -> armed at entry day: {edc >= v.sma_line(prior+[edc])}")
d0 = [b for b in bars if b['hhmm'] > '09:34']
print(f"d0 after fill: max high {max(b['h'] for b in d0)} min low {min(b['l'] for b in d0)} (stop {stop:.2f}, BE {be_lvl:.2f})")
fwd = [b for b in v.daily[t] if b["d"] > d]
# best: s1 dip first (no stop), then BE armed; 8R not on s1 (high 130.11 < t8)
be = True; rest = entry; rem = 1.0; realized = 0.0; partial = False; held = []; sell_next=False
for j, b in enumerate(fwd, start=1):
    if sell_next:
        print(f"  s{j} {b['d']} SELL at open {b['o']}"); break
    if j > 1:
        if b['o'] <= rest: print(f"  s{j} {b['d']} GAP stop at open {b['o']} rest {rest}"); realized += rem*(b['o']-entry); rem=0; break
        hi8 = (not partial and b['h'] >= t8); lo = b['l'] <= rest
        if hi8 and lo: print(f"  s{j} {b['d']} AMBIG 8R+stop"); break
        if lo: print(f"  s{j} {b['d']} STOP at rest {rest} (low {b['l']})"); realized += rem*(rest-entry); rem=0; break
        if hi8: realized += rem/3*(t8-entry); rem *= 2/3; partial=True; print(f"  s{j} {b['d']} 8R third at {t8:.2f} (high {b['h']})")
    held.append(b['c']); line = v.sma_line(prior+held); arm = v.armed(prior, held, entry, edc)
    eff = max(stop, line if (line and arm) else 0, entry if be else 0)
    if b['c'] < eff: sell_next=True; print(f"  s{j} {b['d']} close {b['c']} < eff {eff:.2f} -> sell next open"); continue
    ds = v.depth_stop(eff, stop, entry, be, adr); rest = max(rest, ds)
    print(f"  s{j} {b['d']} o/h/l/c {b['o']}/{b['h']}/{b['l']}/{b['c']} line {line:.2f} armed {arm} eff {eff:.2f} -> rest {rest:.2f}")
print(f"best-order: realized {realized/planned:+.3f}R, remaining {rem:.3f}; mark at last close {fwd[-1]['c']}: {(realized + rem*(fwd[-1]['c']-entry))/planned:+.3f}R")
print(f"worst-order (s1 high first -> BE armed -> low 113.52 <= entry): exit at entry = {0:+.2f}R (stop at entry, booked at entry 115.94)")
