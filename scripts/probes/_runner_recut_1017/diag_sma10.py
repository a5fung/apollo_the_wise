"""Diagnostic: do the sma10_depth arm's per-session lines differ from the control's on trades where SMA20 > SMA10 post-trigger?"""
import sys
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1017")
import recut as rc
inp = rc.load_inputs(); trades, acct = rc.build_trades(inp); rows = rc.run_population(trades)
for fr in rc.FRAMES:
    n_cases = n_diff_lines = 0
    for r in rows:
        if fr not in r.copy0['trig']: continue
        k = r.copy0['trig'][fr]['idx']
        o, trc = r.cand_outs[(fr, 'sma10_depth')]
        ctrc = r.copy0_trace
        cs = {s['idx']: s for s in ctrc.get('sessions', [])}
        ks = {s['idx']: s for s in trc.get('sessions', [])}
        closes = list(r.tr.prior); inv = []
        for idx, (d, b) in enumerate(r.tr.sessions, start=1):
            if b is None: break
            closes.append(b['c'])
            s10, s20 = rc.sma(closes, 10), rc.sma(closes, 20)
            if idx >= max(k, 1) and s10 and s20 and s20 > s10 and idx in cs and idx in ks:
                inv.append(idx)
        if inv:
            n_cases += 1
            diffs = [(i, round(cs[i]['eff_stop'], 3), round(ks[i]['eff_stop'], 3), round(cs[i]['resting_in'], 3), round(ks[i]['resting_in'], 3)) for i in inv if abs(cs[i]['eff_stop'] - ks[i]['eff_stop']) > 1e-9 or abs(cs[i]['resting_in'] - ks[i]['resting_in']) > 1e-9]
            n_diff_lines += bool(diffs)
            print(f"Frame {fr} {r.tr.key}: SMA20>SMA10 on sessions {inv[:6]}...; sessions where eff_stop/resting differ between control and sma10_depth: {diffs[:3] if diffs else 'none'}")
    print(f"Frame {fr}: {n_cases} trades with SMA20>SMA10 post-trigger while both walks are live; {n_diff_lines} of them show any differing stop line\n")
