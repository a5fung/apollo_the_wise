"""real-count re-run vs the frozen spread_sim_v2.txt (keep 1.0 = 100% of the indicative count, keep 0.6 = 60%): PICKS THE TAIL (family of 9) and the 80% size."""
import re
def parse(path):
    out, cur, chk, k = {}, None, None, None
    for ln in open(path):
        m = re.match(r"==== .*?rate OUTSIDE 2020 (\d+)%", ln)
        if m: cur = int(m.group(1)); chk = -1; continue
        if ln.strip().startswith("-- check"): chk += 1; continue
        m = re.match(r"\s+true (\d\.\d)x: PICKS THE TAIL fam9 [\d.]+ \| whole chain ([\d.]+)", ln)
        if m and chk is not None and chk >= 0: out[(cur, chk, m.group(1))] = float(m.group(2)); continue
        m = re.match(r"\s+smallest true ratio .*?: (over 3\.0x|[\d.]+x)", ln)
        if m: out[(cur, chk, "need")] = m.group(1)
    return out
def parse_frozen(path):
    out, cur, keep, chk = {}, None, None, None
    for ln in open(path):
        m = re.match(r"==== keep ([\d.]+) .*?rate OUTSIDE 2020 (\d+)%", ln)
        if m: keep, cur, chk = m.group(1), int(m.group(2)), -1; continue
        if ln.strip().startswith("-- check"): chk += 1; continue
        m = re.match(r"\s+true (\d\.\d)x: PICKS THE TAIL fam9 [\d.]+ \| whole chain ([\d.]+)", ln)
        if m and chk is not None and chk >= 0: out[(keep, cur, chk, m.group(1))] = float(m.group(2)); continue
        m = re.match(r"\s+smallest true ratio .*?: (over 3\.0x|[\d.]+x)", ln)
        if m: out[(keep, cur, chk, "need")] = m.group(1)
    return out
R = parse("2_sim.txt"); F = parse_frozen("../design/spread_sim_v2.txt")
names = ["3a era A only", "3b +era B x1.0", "3b +era B x0.75", "3b +era B x0.5", "3b 25-mo feats x1.0", "3b 25-mo feats x0.75"]
print("WHOLE CHAIN (the quantity the prereg 5.4 table prints; carried on discovery x PICKS THE TAIL on check, family of 9) - REAL counts | frozen at 100% of the indicative count | frozen at 60%.  'need' = smallest true ratio found 4 times in 5")
for p in (5, 3, 8):
    print(f"\n== rate outside 2020 {p}%")
    for ci, nm in enumerate(names):
        cells = []
        for k in ("1.3", "1.5", "2.0"):
            cells.append(f"{k}x: {R[(p, ci, k)]:.2f} | {F[('1.0', p, ci, k)]:.2f} | {F[('0.6', p, ci, k)]:.2f}")
        print(f"  {nm:22s} " + "   ".join(cells) + f"   need: {R[(p, ci, 'need')]} | {F[('1.0', p, ci, 'need')]} | {F[('0.6', p, ci, 'need')]}")
