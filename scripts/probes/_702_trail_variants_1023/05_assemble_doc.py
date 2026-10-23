"""#705 Track B — step 5: assemble docs/analysis/cb_trail_variants_2026-10-23.md from doc_head.md (the hand-written lead, §D, §1) + the
in-doc tables filled from 02_numbers_<era>.json and the trade tables (the under −2R per 1,000 column) + §M / §L / §V + 03_report.md verbatim."""
import json, subprocess
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_trail_variants_1023"
DOC = "/Users/alvinfung/apollo_the_wise/docs/analysis/cb_trail_variants_2026-10-23.md"
DATA = {"2017-21": "/Users/alvinfung/apollo_data/cb702_pre", "2022-24": "/Users/alvinfung/apollo_data/cb702"}
J = {e: json.load(open(f"{HERE}/02_numbers_{e}.json")) for e in DATA}
cells = J["2017-21"]["cells"]
assert cells == J["2022-24"]["cells"]
NAME = {}
for k in cells:
    n, t, p = k[1:3], k[4:6], k[7:9]
    NAME[k] = f"{n} · {t} · {p}" + (" (= `pp`)" if k == "A20_X1_P1" else "")


def ci(d, dd=3, scale=1.0, unit=""):
    return f"{d['diff']*scale:+.{dd}f} ({d['lo']*scale:+.{dd}f} .. {d['hi']*scale:+.{dd}f}){unit}"


under2 = {}
for e, data in DATA.items():
    r = pd.read_csv(f"{data}/out/trail_r1_{e}.tsv.gz", sep="\t", low_memory=False, usecols=["cell", "attempt", "status", "complete120", "realized_r"])
    r = r[(r.status >= 0) & (r.complete120 == 1) & (r.attempt == 0)]
    under2[e] = {k: 1000 * (g.realized_r < -2).mean() for k, g in r.groupby("cell")}

s = open(f"{HERE}/doc_head.md").read()
# P-win 2022-24 T2 rows
rows = []
G = J["2022-24"]["grid"]
for k in cells:
    w = G[k]["win"]["T2"]; n = w["n"]
    rows.append(f"| {NAME[k]} | T2 | n = {n} | {w['still_in_s50']} ({100*w['still_in_s50']/n:.0f}%) | {w['kept_half']} ({100*w['kept_half']/n:.0f}%) | {w['kept_quarter']} ({100*w['kept_quarter']/n:.0f}%) | "
                f"{w['kept_share_q'][1]:.3f} ({w['kept_share_q'][0]:.3f} .. {w['kept_share_q'][2]:.3f}) | {w['held_chain_q'][1]:.0f} ({w['held_chain_q'][0]:.0f} .. {w['held_chain_q'][2]:.0f}) | "
                f"{w['first_stopped_before_s50']} / {w['first_cut']} / {w['first_trailed_before_s50']} | {w['retries_mean']:.2f} ({w['used1']} / {w['used2']}) | {w['chain_r_mean']:+.2f} / {w['chain_r_q'][1]:+.2f} | "
                f"{w['any5']} / {w['any10']} | {w['trade_r']['worst']:+.2f}, {w['trade_r']['p5']:+.2f} |")
s = s.replace("GEN_PWIN_2022_T2", "\n".join(rows))
# R1 T0 per era
for e, tag in (("2017-21", "GEN_R1T0_2017"), ("2022-24", "GEN_R1T0_2022")):
    G = J[e]["grid"]; rows = []
    for k in cells:
        g = G[k]["R1_T0_complete"]; E, M, D = g["entries"], g["control"], g["diff"]; cq = G[k]["ctl_trade_r"]["T0"]["complete"]
        rows.append(f"| {NAME[k]} | {E['any5_per100']:.1f} vs {M['any5_per100']:.1f}; {ci(D['any5'], 1)} | {E['any10_per100']:.1f} vs {M['any10_per100']:.1f}; {ci(D['any10'], 1)} | "
                    f"{E['r_per_trade']:+.3f} vs {M['r_per_trade']:+.3f} | {ci(D['r_per_base'])} | {E['r_per_trade_median']:+.2f} | {E['trade_r']['worst']:+.1f} / {E['trade_r']['p5']:+.2f} ({cq['p5']:+.2f}) | "
                    f"{under2[e][k]:.1f} | {100*E['win_per_trade']:.0f}% (ctl {100*M['win']:.0f}%) | {g['account']['total_pct']:+.0f}% / {g['account']['max_dd_pct']:.0f}% | {g['account_control']['total_pct']:+.0f}% / {g['account_control']['max_dd_pct']:.0f}% |")
    s = s.replace(tag, "\n".join(rows))
# R1 T2 both eras
rows = []
for e in DATA:
    G = J[e]["grid"]
    for k in cells:
        g = G[k]["R1_T2_complete"]; E, M, D = g["entries"], g["control"], g["diff"]
        rows.append(f"| {e} | {NAME[k]} | {E['trades_per_week']:.1f} (ctl {M['trades_per_week']:.1f}) | {E['r_per_base']:+.3f} vs {M['r_per_base']:+.3f}; {ci(D['r_per_base'])} | {E['any5_per100']:.1f} vs {M['any5_per100']:.1f}; {ci(D['any5'], 1)} | "
                    f"{E['trade_r']['worst']:+.1f} / {E['trade_r']['p5']:+.2f} (n = {E['trade_r']['n']}) | {g['account']['total_pct']:+.0f}% / {g['account']['max_dd_pct']:.0f}% | {g['account_control']['total_pct']:+.0f}% / {g['account_control']['max_dd_pct']:.0f}% |")
s = s.replace("GEN_R1T2", "\n".join(rows))
# R2 both eras, T0 and T2
rows = []
for e in DATA:
    G = J[e]["grid"]
    for k in cells:
        for T in (0, 2):
            g = G[k][f"R2_T{T}_complete"]; E, M, D = g["entries"], g["control"], g["diff"]
            rows.append(f"| {e} | {NAME[k]} | T{T} | n = {E['n']} | {E['r_per_trade']:+.3f} vs {M['r_per_trade']:+.3f} | {ci(D['r_per_base'])} | {ci(D['any5'], 1)} | {E['trade_r']['worst']:+.1f} / {E['trade_r']['p5']:+.2f} |")
s = s.replace("GEN_R2", "\n".join(rows))
assert "GEN_" not in s

tail = r"""
## M. Method and population

**Population:** the three row sets of the 10-22 read, loaded by the same code with the same asserts (`trail_lib.load_pops`). **P-win** = the
covered measurable-breakout doubler episodes of `cb_big_winner_recall_2026-10-22.md` (`wrecall_episodes_<era>_x200.tsv.gz` ×
`wrecall_catch_<era>_x200.tsv.gz`, `class_p = measurable_breakout`, `excluded = 0`, `covered = 1`): **n = 481** (troughs 2017-03-01..2021-12-31)
and **n = 258** (2022-03-28..2024-12-31); entry at the close of the breakout day `b_p`. **P-all** = the R1 rows of
`cb_breakout_definition_2026-10-22.md` (`bdef_r1_<era>.tsv.gz`): **n = 9,281 / 5,530**, **complete** (t + 120 ≤ the last readable session)
**9,239 / 4,457** (entry days 2017-03-03..2022-01-06 / 2022-04-01..2024-07-11, 244 / 114 weeks); R2 = `r2_exp = 1`, complete 1,575 / 845.
**P-ctl** = the rows of `bdef_control_<era>.tsv.gz` on the R1 entry days: **2,096,517 / 1,469,399** (complete 2,047,198 / 1,195,658), re-walked
under every cell; the matching cells and the seed-702 account-view draw are the 10-22 read's (`02_sample_R{1,2}_<era>.tsv`, asserted equal).
Bars: each era's `daily_closes_all.csv.gz` (Alpaca split-adjusted daily bars; 2017–21 export 2016-01-04..2022-06-30; **2022–24 cut to ≤
2024-12-31 at load, asserted**); SPY's calendar. The export adjusts splits but not every corporate action: an unadjusted 2-for-1 (IGIB /
IGSB 2018-08) and reassigned / deal-pinned tickers (BHVN 2022-10, COHR 2022-07) sit in the control's worst trades, and one spin-off
distribution (ZWS 2021-10-05) in the entries'; they are named where they appear and the 5th-percentile and under-2R / under-5R counts are the
robust reads of "major losses".

**The walk** (`trail_lib.py`): `esr_lib.walk` of the 10-22 read copied as `walk_v` with the trail arms (§D), `walk_chain` copied as
`walk_chain_v`; `Frame`, the stops, the retry rule, the race, the bootstrap and the account view imported from `esr_lib` unchanged; the
matched-control helpers of the 10-22 `02_build.py` copied verbatim. 16 cells × 3 populations × 3 retry depths per era; each cell ~6–8 s.

**Files.** Probes: `scripts/probes/_702_trail_variants_1023/BRIEF.md` (the frozen grid), `DEFINITIONS.md` (the silent spots, written before
any walk), `trail_lib.py`, `01_parity.py` (+ `.txt`), `02_build.py` (+ `02_numbers_<era>.json`, `02_build_<era>.log`, `02_run_<era>.log`),
`03_report.py` (+ `03_report.md`, `03_headline.json`), `04_checks.py` (+ `.txt`), `05_assemble_doc.py`, `doc_head.md`. Tables:
`apollo_data/cb702_pre/out/trail_{win,r1,ctlsample}_2017-21.tsv.gz` (one row per cell × base × attempt), `trail_ctlmatch_2017-21.parquet`
(the matched control means per entry × cell × entry set × retry depth, complete bases) and the same under `apollo_data/cb702/out/` for
2022–24. The full control's per-base summaries are not persisted (16 cells × 2.1M rows); a re-walk is seconds and the per-trade quantiles
are in the JSON. Nothing pinned was written or moved; the runner and the once-only stages were neither run nor imported; `esr_lib.py` is
untouched; no 2025–26 file was opened; no network; no subagent; no commit.

## L. What this does not answer

- **Whether any cell PAYS.** No cell's per-base R clears the matched control at T0 in either era; the doublers say what a cell holds, never
  whether it pays. The T2 lifts in 2017–21 carry the control-retry caveat and do not repeat in 2022–24.
- **The intraday trigger on daily bars.** X4 is read as a low under the prior session's average with the pessimistic touch-both rule; on
  minute bars a +2R print before the low would be ordered, and the fill at the level is assumed. The published ORH5 entry is not here.
- **Other grace lengths, other decisive sizes, other averages.** X3 forgives exactly two sessions, X2 is exactly 0.5 ADR or two closes, the
  averages are 10 and 20; the grid is the brief's, no cell outside it was read.
- **Entry, stop and retry held fixed** at the 10-22 read's best-holding cell. A trail that reads differently under a wider stop or a next-open
  entry is a different grid.
- **Corporate actions in the export.** The worst-trade columns carry an unadjusted split and reassigned tickers on the control side and one
  spin-off distribution on the entries' side (named above); the counts under −2R and −5R are reported beside and are the robust read.
- **Same-day conditioning, survivorship, censoring at the cut** — as the 10-22 read states; the complete-only headline and the all-bases arm
  (generated tables) bound the censoring.
- **Selection.** Every entry set is derived from the published C0 `tl` fills' bases; stricter cells, his stream grades and RS leadership are
  not re-read here. Nothing after 2024-12-31 was read; the registered RS-leadership read stays unspent.

## V. Verification (2026-10-23)

- **Parity before any new arm was read** (`01_parity.txt`; `02_build_<era>.log`): (a) SMA20 rebuilt from the close frame equals the 10-22
  frame's SMA bit for bit, both eras; (b) `walk_chain_v(20, X1, P1)` equals `esr_lib.walk_chain` on every shared column (NaN = NaN) for P-win
  (797 / 416 rows), R1 (16,386 / 9,543) and a 300,000-row control subsample (400,122 / 389,249); (c) the `pp` cell through the new build
  reproduces every number of `02_numbers_<era>.json['grid']['S2_close']` of the 10-22 read — 2,014 numeric leaves per era, max |diff| 0 — and
  the build asserts it before the other 15 cells run; (d) the published `pp` rows re-walked through `walk_v`: 7,334 of 7,335 and 4,905 of
  4,905 (as 10-22).
- **Own code, no walker import (`04_checks.py` / `.txt`), CHECKS PASS:** (a) a plain per-trade Python walk of every trigger × partial, written
  from DEFINITIONS.md, on 300 random trades × 16 cells × 3 tables × 2 eras = 28,800 trades, inputs at the frame's float32 prices — 0
  mismatches, 0 knife-edge ties, max |ΔR| 4.6e-5 (per table R1 / control sample / P-win: 4.2e-5 / 2.0e-5 / 3.4e-5 in 2017–21, 1.1e-5 /
  4.6e-5 / 1.9e-5 in 2022–24); (b) the retry rule re-derived from raw closes on every P-win cell
  (4,305 / 2,271 retries) and two R1 cells (12,256 / 7,056) — 0 violations, 0 retries after a non-stop exit (an X4 level exit never earns one),
  0 stopped chains with an unused retry; (c) the P-win still-in / kept-½ / kept-¼ / median kept share / median sessions held recounted from the
  trade table for two new cells per era — equal; (g) the matched-control file's per-cell means equal the JSON's control per-base R and ≥ 5R
  per 100 on 128 numbers per era — to the digit.
- **Found and stated, not patched:** the control's worst trades are corporate-action artifacts of the export (an unadjusted 2-for-1, reassigned
  tickers); one of the entries' (ZWS, 2.7× its prior median volume on the gap day) is a spin-off distribution, while OPLN (8.9×) and AVIR (53×)
  printed repricing volume and are read as real. The under-2R and under-5R counts were added beside the worst trade.
- **Not independently verified by a second agent** (this read ran without subagents by instruction); the generated tables, the checks file and
  the trade tables are the material for the two verifiers that follow.

---

## Generated tables (`03_report.py`, verbatim; n on every row)

"""
s = s + tail + open(f"{HERE}/03_report.md").read()
open(DOC, "w").write(s)
print(f"wrote {DOC}: {len(s):,} chars, {s.count(chr(10))} lines")
r = subprocess.run(["python3", "/Users/alvinfung/apollo_the_wise/scripts/check_analysis_doc.py", DOC], capture_output=True, text=True)
print("check_analysis_doc:", "PASS" if r.returncode == 0 else "FAIL", r.stderr[-600:])
