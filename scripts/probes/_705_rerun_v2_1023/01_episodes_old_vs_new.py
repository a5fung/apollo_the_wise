#!/usr/bin/env python3
"""#705 v2 re-run, the one read that can run end to end: the big-winner EPISODES (01_episodes.py) on cb702_pre vs cb702_pre_v2.

Runs the winner-recall read's own `composition()` (03_report.py, imported unchanged) on the episode tables of the two builds and prints
the headline counts side by side. Reads only wrecall_episodes_2017-21_x{200,150}.tsv.gz of each build; writes
HERE/episodes_old_vs_new.json and HERE/episodes_old_vs_new.md. Nothing under DATA is opened for writing."""
import importlib.util, json, os, sys
import pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_705_rerun_v2_1023"
OLD = "/Users/alvinfung/apollo_data/cb702_pre/out"
NEW = "/Users/alvinfung/apollo_data/cb702_pre_v2/out/rerun_1023/winner_recall"
REPORT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_winner_recall_1022/03_report.py"
sys.argv = ["03_report.py", "2017-21"]                      # the report module limits itself to the era named on its command line
spec = importlib.util.spec_from_file_location("wr03", REPORT)
wr = importlib.util.module_from_spec(spec); spec.loader.exec_module(wr)


def load(d, tag):
    e = pd.read_csv(f"{d}/wrecall_episodes_2017-21_{tag}.tsv.gz", sep="\t", keep_default_na=False, na_values=[""])
    return e, e[e.excluded == 0].reset_index(drop=True)


res = {}
for tag in ("x200", "x150"):
    for name, d in (("old", OLD), ("new", NEW)):
        raw, e = load(d, tag)
        wr.out.clear(); wr.NUM.clear()
        wr.composition(e, "2017-21", tag)
        comp = wr.NUM[f"2017-21/{tag}/composition"]; cls = wr.NUM[f"2017-21/{tag}/classes"]
        mb = e[e.class_p == "measurable_breakout"]
        res[f"{tag}/{name}"] = dict(
            episodes_all=len(raw), excluded=int(raw.excluded.sum()), kept=len(e), tickers=int(e.ticker.nunique()),
            by_year={k: int(v) for k, v in e.trough_date.str[:4].value_counts().sort_index().items()},
            classes={v: cls[v] for v in cls}, ep_gap_start=comp["gap_start"], measurable_breakouts=comp["mb"], mb_expansion=comp["mb_expansion"],
            mb_b_minus_t_median=comp["mb_b_minus_t_median"], mb_L_median=comp["mb_L_median"], gain_median=comp["gain_median"], close_t_median=comp["close_t_median"],
            mb_base_contains_trough=int(mb.base_contains_trough.sum()), late_base=int((e.class_p == "late_base").sum()),
            late_base_depth_median=float(e[e.class_p == "late_base"].base_depth_pct.median()),
            late_base_gain_made_at_b_close_median=float(e[e.class_p == "late_base"].gain_made_at_b_close.median()))
json.dump(res, open(f"{HERE}/episodes_old_vs_new.json", "w"), indent=1, default=float)

L = []
for tag in ("x200", "x150"):
    o, n = res[f"{tag}/old"], res[f"{tag}/new"]
    L.append(f"### {tag} ({'the +100% set' if tag == 'x200' else 'the +50% sensitivity set'})")
    L.append("| number (as computed) | old (cb702_pre) | new (v2) | change |")
    L.append("|---|---|---|---|")

    def row(name, a, b, pct=False):
        ch = f"{b - a:+,}" if isinstance(a, int) else f"{b - a:+.3f}"
        if isinstance(a, int) and a:
            ch += f" ({100 * (b - a) / a:+.1f}%)"
        L.append(f"| {name} | {a:,} | {b:,} | {ch} |" if isinstance(a, int) else f"| {name} | {a:.3f} | {b:.3f} | {ch} |")
    row("episodes found (all)", o["episodes_all"], n["episodes_all"])
    row("excluded (artifact jump or identity break)", o["excluded"], n["excluded"])
    row("big winners kept (n)", o["kept"], n["kept"])
    row("distinct tickers among kept", o["tickers"], n["tickers"])
    for cls in ("measurable_breakout", "late_base", "ep_gap", "other", "no_consolidation"):
        row(f"class_p = {cls} (n)", o["classes"]["p"].get(cls, 0), n["classes"]["p"].get(cls, 0))
    for v in ("s4", "s7", "shortL"):
        row(f"measurable_breakout under variant {v} (n)", o["classes"][v].get("measurable_breakout", 0), n["classes"][v].get("measurable_breakout", 0))
    row("measurable breakouts with the expansion-day test (n)", o["mb_expansion"], n["mb_expansion"])
    row("episodes with an EP-gap start (n)", o["ep_gap_start"], n["ep_gap_start"])
    row("measurable breakouts whose base contains the trough (n)", o["mb_base_contains_trough"], n["mb_base_contains_trough"])
    for y in sorted(set(o["by_year"]) | set(n["by_year"])):
        row(f"episodes with trough in {y} (n)", o["by_year"].get(y, 0), n["by_year"].get(y, 0))
    row("gain trough->peak, median", o["gain_median"], n["gain_median"])
    row("late-base: share of gain already made at the breakout close, median", o["late_base_gain_made_at_b_close_median"], n["late_base_gain_made_at_b_close_median"])
    row("late-base: base depth, median", o["late_base_depth_median"], n["late_base_depth_median"])
    L.append("")
open(f"{HERE}/episodes_old_vs_new.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
