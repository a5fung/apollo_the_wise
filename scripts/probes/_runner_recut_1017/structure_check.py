"""Pre-run STRUCTURE diagnostics: accounting and plumbing only (statuses, trigger counts, input census).
Prints no R, no totals, no per-rule results."""
import sys
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1017")
from collections import Counter
import recut as rc

inp = rc.load_inputs()
trades, acct = rc.build_trades(inp)
rows = rc.run_population(trades)
print("filled", len(rows), dict(acct))
print("control status:", dict(Counter(r.ctrl.status for r in rows)))
print("control pending/abstain reasons:", dict(Counter((r.ctrl.out['reason'] or '').split(':')[0] for r in rows if r.ctrl.R is None)))
for fr in rc.FRAMES:
    ts = [r for r in rows if fr in r.copy0['trig']]
    print(f"Frame {fr}: control-path trigger fired on {len(ts)}; of them control scored {sum(1 for r in ts if r.ctrl.R is not None)}; trigger session idx histogram {dict(sorted(Counter(r.copy0['trig'][fr]['idx'] for r in ts).items()))}")
print("sessions available (len) histogram for filled trades:", dict(sorted(Counter(len(r.tr.sessions) for r in rows).items())))
print("entries by month:", dict(sorted(Counter(r.tr.d.strftime('%Y-%m') for r in rows).items())))
print("entries by half H1/H2:", sum(1 for r in rows if r.tr.d <= rc.H1_END), sum(1 for r in rows if r.tr.d > rc.H1_END))
print("distinct entry weeks:", len({r.tr.week for r in rows}))
print("arm status counts (A|t20_be):", dict(Counter(r.arms[rc.PRIMARY].status for r in rows)))
print("arm unscored reasons (A|t20_be):", dict(Counter((r.arms[rc.PRIMARY].out['reason'] or '').split(':')[0] for r in rows if r.arms[rc.PRIMARY].R is None)))
print("atr14 None:", sum(1 for r in rows if r.tr.atr14 is None), " <20 prior closes:", sum(1 for r in rows if len(r.tr.prior) < 20), [r.tr.key for r in rows if len(r.tr.prior) < 20][:6])
print("distinct tickers with a gap-status control:", sorted({r.tr.key for r in rows if r.ctrl.status == 'gap'})[:10])
