#!/usr/bin/env python3
"""Runner re-cut under the 2026-11-03 MAGNA53 admission rule (#718: a name whose 09:30 OPEN is below
prev close x 1.09 is not entered). Research only, $0, offline.

ONE change against the 2026-10-16 run (docs/analysis/runner_recut_results_2026-10-16.md): every Run-U
row whose day-0 09:30 open < round(prev_close x 1.09, 6) is dropped BEFORE the fill model. Everything
else — the population file, the fill model, the control, the 22 arms, the 3 reference rows, the measures,
the seeds, the decision bar — is the 10-16 code, unchanged and called as-is.

  Step 1  reproduce the 10-16 run from the captures with the 10-16/17 code, and stop if it does not match:
          - the code is materialised from commit 8fca6649 (the 10-16 results commit) with `git archive`
            into a temp dir (reads git objects only), because HEAD's live_fill_counterfactuals.py /
            exit_logic.py have changed since (the 10-28 trail-arming fix and #482 follow-ups);
          - the blob hashes of the materialised walker files must equal the pre-registration's pins,
            and recut.py / walker_cand.py / make_walker.py must equal the sha256 prefixes the 10-16 doc prints;
          - the reproduced stdout must equal _runner_recut_1017/run.out line for line (only the dump path differs),
            run_rows.tsv and run_results.json must equal the 10-16 dumps byte for byte, and every table row
            the 10-16 doc prints must be regenerated verbatim from the reproduced results.
  Step 2  drop the rows under the open floor, list them.
  Step 3  the identical sweep on the kept rows (recut.run_gates + recut.do_run, unchanged), plus a compact
          per-arm table: n, mean, median, win %, concentration, separation (week-block p, week bootstrap CI).
  Step 4  the 10-16 bar (pre-registration §5) applied mechanically to the primary, compared word for word.

Writes: recut_open_floor.txt (this script's whole stdout), repro_full/ and kept/ (recut.do_run's dumps),
dropped_rows.tsv. Never writes into _runner_recut_1017 (recut.OUTDIR is redirected before any call).

  python3 recut_open_floor.py            # the read of record (pinned code)
  python3 recut_open_floor.py --head     # the same against HEAD's code (a drift check only, not the record)
"""
import argparse
import hashlib
import importlib
import importlib.util
import io
import json
import os
import statistics
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict

REPO = "/Users/alvinfung/apollo_the_wise"
SRC = f"{REPO}/scripts/probes/_runner_recut_1017"
HERE = f"{REPO}/scripts/probes/_runner_recut_1103"
PIN_COMMIT = "8fca6649"   # '#687 runner re-cut 10-16' — the commit that carries the 10-16 results
PIN_BLOBS = {             # pre-registration §2 / results doc 'Code blobs pinned and verified at run time'
    "agents/market_intelligence/live_fill_counterfactuals.py": "e9098c36",
    "agents/market_intelligence/broker/exit_logic.py": "d5597612",
    "scripts/probes/_bt_replay.py": "727d5f84",
}
CODE_SHA = {"recut.py": "24b2e70aa29e6427", "walker_cand.py": "3a9e693c0db1ceb4",
            "make_walker.py": "840cbf1de9e58cc0", "run.out": "a781524088bd3dd4"}
FLOOR_MULT = 1.09          # MIN_GAP_PCT 9% -> x1.09; floor = round(prev_close x 1.09, 6), STRICTLY below drops
NEAR_TIE_PCT = 0.10        # descriptive only: dropped rows within 0.10% of the line are listed (not a threshold)

LOG = []


def out(s=""):
    print(s)
    LOG.append(s)


def git_blob_hash(path):
    data = open(path, "rb").read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ═════════════════════════ code loading ═════════════════════════
def materialise_pinned(dst):
    tar = subprocess.run(["git", "-C", REPO, "archive", PIN_COMMIT, "agents", "shared", "scripts/probes/_bt_replay.py"],
                         check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        tf.extractall(dst, filter="data")
    for rel, pin in PIN_BLOBS.items():
        h = git_blob_hash(f"{dst}/{rel}")
        assert h.startswith(pin), f"pinned tree blob mismatch {rel}: {h} vs {pin}"
    return dst


def load_recut(code_root):
    """Pre-import the walker modules from `code_root` so recut.py's own imports hit the cache, then load
    recut.py from the 10-16 folder (its sys.path.insert(REPO) can no longer redirect them)."""
    for f, pin in CODE_SHA.items():
        h = sha256(f"{SRC}/{f}")
        assert h.startswith(pin), f"10-16 code changed: {f} {h[:16]} vs {pin}"
    sys.path.insert(0, code_root)
    import agents.market_intelligence.broker.exit_logic as el  # noqa: F401
    import agents.market_intelligence.live_fill_counterfactuals as lfc  # noqa: F401
    import scripts.probes._bt_replay as btr  # noqa: F401
    for m in (el, lfc, btr):
        assert m.__file__.startswith(code_root), f"{m.__name__} loaded from {m.__file__}, not {code_root}"
    spec = importlib.util.spec_from_file_location("recut", f"{SRC}/recut.py")
    rc = importlib.util.module_from_spec(spec)
    sys.modules["recut"] = rc
    spec.loader.exec_module(rc)
    return rc


def assert_code_origin(code_root):
    bad = [(n, m.__file__) for n, m in list(sys.modules.items())
           if (n == "agents" or n.startswith("agents.") or n == "shared" or n.startswith("shared."))
           and getattr(m, "__file__", None) and not m.__file__.startswith(code_root)]
    assert not bad, f"modules loaded outside {code_root}: {bad[:5]}"
    for rel in PIN_BLOBS:
        modname = rel[:-3].replace("/", ".")
        m = sys.modules.get(modname)
        if m is not None:
            assert m.__file__.startswith(code_root), (modname, m.__file__)


# ═════════════════════════ the 10-16 doc's table formatter (copied verbatim from build_results_doc.py) ═════════════════════════
# Copied, not imported: importing build_results_doc.py would rewrite the 10-16 doc.
def doc_row(frame, name, m, ref=False):
    n = m["paired_n"]
    eng = "-" if ref and m.get("engaged_n") is None else m.get("engaged_n")
    xt = f"{m['n_tail']} ({100 * m['n_tail'] / n:.1f}%)"
    if ref:
        return (f"| {frame} | {name} | {n} | {eng} | {m['differ_n']} | {xt} | {m['n_be']} | {m['p90']:+.2f} | {m['total']:+.2f} | "
                f"{m['mean']:+.3f} | {m['delta_total']:+.2f} | - | - | - | - | {m['median']:+.3f} | {100 * m['win']:.1f}% | "
                f"{m['open_data_end']} |")
    return (f"| {frame} | {name} | {n} | {eng} | {m['differ_n']} | {xt} | {m['n_be']} | {m['p90']:+.2f} | {m['total']:+.2f} | "
            f"{m['mean']:+.3f} | {m['delta_total']:+.2f} | {m['delta_ex_top2']:+.2f} | {m['drop_best2']:+.2f} | "
            f"{m['h1']:+.2f} / {m['h2']:+.2f} | {m['p_weekblock']:.3f} | {m['median']:+.3f} | {100 * m['win']:.1f}% | "
            f"{m['open_data_end']} |")


DOC_HEAD = ("| frame | rule | paired n | engaged n | differ n | +4R trades (share of n) | +1.5R trades | p90 R | total R | mean R | "
            "delta vs control | delta without top 2 | drop-best-2 | H1 / H2 delta | p (week-block) | median R | win % | open at end |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def doc_ctrl_row(C):
    return (f"| - | control (depth), n = {C['n']} | {C['n']} | - | - | {C['n_tail']} ({100 * C['n_tail'] / C['n']:.1f}%) | {C['n_be']} | "
            f"{C['p90']:+.2f} | {C['total']:+.2f} | {C['mean']:+.3f} | - | - | {C['drop_best2']:+.2f} | - | - | {C['median']:+.3f} | "
            f"{100 * C['win']:.1f}% | {C['open_e']} |")


def doc_table_lines(R, rules):
    lines = [doc_ctrl_row(R["control"]), doc_row("A", "**t20_be (PRIMARY)**", R["arms"]["A|t20_be"])]
    lines += [doc_row(fr, ru, R["arms"][f"{fr}|{ru}"]) for fr in "AB" for ru in rules if f"{fr}|{ru}" != "A|t20_be"]
    lines += [doc_row("ref", n, R["refs"][n], ref=True) for n in ("t20_entry_ref", "era_d", "control_at_close")]
    return lines


# ═════════════════════════ one sweep (the 10-16 main(--run) path, verbatim order) ═════════════════════════
def sweep(rc, inp, trades, acct, outdir):
    os.makedirs(outdir, exist_ok=True)
    rc.OUTDIR = outdir
    rows = rc.run_population(trades)
    gbuf = []
    okg = rc.run_gates(inp, trades, rows, out=gbuf.append)
    rbuf = []
    results = None
    if okg:
        results = rc.do_run(inp, trades, acct, rows, out=rbuf.append)
    # recut.main(--run): print("gates (re-run ...):"); print("\n".join(buf)); print(); do_run(...)
    text = "gates (re-run immediately before the run):\n" + "\n".join(gbuf) + "\n\n" + ("\n".join(rbuf) + "\n" if rbuf else "")
    open(f"{outdir}/run.out", "w").write(text)
    return okg, rows, results, text


# ═════════════════════════ extra per-arm table (descriptive; same pairs, same seeds as recut.measure) ═════════════════════════
def own_concentration(R_list, keys):
    tot = sum(R_list)
    order = sorted(range(len(R_list)), key=lambda i: R_list[i], reverse=True)
    top2 = sum(R_list[i] for i in order[:2])
    top5 = sum(R_list[i] for i in order[:5])
    names = [(keys[i][0], keys[i][1][5:], round(R_list[i], 2)) for i in order[:5]]
    share = (lambda x: (x / tot) if tot > 1e-12 else None)
    return share(top2), share(top5), names


def arm_pairs(rows, getarm):
    return [(r, getarm(r)) for r in rows if getarm(r).R is not None and r.ctrl.R is not None]


def compact_table(rc, rows, results, title):
    out(title)
    out(f"  {'frame|rule':<22}{'n':>5}{'mean R':>9}{'median R':>10}{'win %':>7}{'total R':>9}{'+4R':>5}"
        f"{'own top2':>9}{'own top5':>9}{'d tot':>8}{'d/trade':>9}{'95% week-boot CI':>20}{'p wk':>7}{'d ex top2':>10}"
        f"{'d top5 share':>13}  sep95")
    cR = [r.ctrl.R for r in rows if r.ctrl.R is not None]
    ckeys = [r.tr.key for r in rows if r.ctrl.R is not None]
    c2, c5, cn = own_concentration(cR, ckeys)
    C = results["control"]
    out(f"  {'control (depth)':<22}{len(cR):>5}{C['mean']:>+9.3f}{C['median']:>+10.3f}{100 * C['win']:>7.1f}{C['total']:>+9.2f}"
        f"{C['n_tail']:>5}{(f'{100 * c2:.0f}%' if c2 is not None else 'n/a'):>9}{(f'{100 * c5:.0f}%' if c5 is not None else 'n/a'):>9}")
    seps = []
    entries = [("A|t20_be", lambda r: r.arms[rc.PRIMARY], results["arms"]["A|t20_be"])]
    entries += [(f"{fr}|{ru}", (lambda r, k=(fr, ru): r.arms[k]), results["arms"][f"{fr}|{ru}"])
                for fr in rc.FRAMES for ru in rc.RULES if (fr, ru) != rc.PRIMARY]
    entries += [(f"ref|{nm}", (lambda r, k=nm: r.refs[k]), results["refs"][nm]) for nm in rc.REFS]
    for name, get, m in entries:
        pairs = arm_pairs(rows, get)
        R_list = [a.R for _, a in pairs]
        keys = [r.tr.key for r, _ in pairs]
        a2, a5, _ = own_concentration(R_list, keys)
        lo, hi = m["boot_lo"], m["boot_hi"]
        sep = (m["p_weekblock"] < 0.05) and (lo > 0 or hi < 0)
        sep_p = m["p_weekblock"] < 0.05
        if sep_p or sep:
            seps.append((name, round(m["delta_total"], 2), round(m["p_weekblock"], 4), round(lo, 3), round(hi, 3)))
        t5 = m.get("top5_share")
        out(f"  {name:<22}{m['paired_n']:>5}{m['mean']:>+9.3f}{m['median']:>+10.3f}{100 * m['win']:>7.1f}{m['total']:>+9.2f}"
            f"{m['n_tail']:>5}{(f'{100 * a2:.0f}%' if a2 is not None else 'n/a'):>9}{(f'{100 * a5:.0f}%' if a5 is not None else 'n/a'):>9}"
            f"{m['delta_total']:>+8.2f}{m['delta_mean']:>+9.3f}{f'[{lo:+.3f}, {hi:+.3f}]':>20}{m['p_weekblock']:>7.3f}"
            f"{m['delta_ex_top2']:>+10.2f}{(f'{100 * t5:.0f}%' if t5 is not None else 'n/a'):>13}  "
            f"{'YES' if sep else ('p<.05 only' if sep_p else 'no')}")
    out(f"  control: its top 5 trades = {cn}")
    # where the separating arms' paired gains sit: pairs with a position still open at 2026-08-28 on either side
    # (a realized exit vs a last-close mark) against pairs both sides settled (descriptive; no new test)
    for name, get, m in entries:
        if m["p_weekblock"] >= 0.05:
            continue
        pairs = arm_pairs(rows, get)
        mk = [(r, x) for r, x in pairs if r.ctrl.status in ("data_end", "horizon") or x.status in ("data_end", "horizon")]
        st = [(r, x) for r, x in pairs if not (r.ctrl.status in ("data_end", "horizon") or x.status in ("data_end", "horizon"))]
        dmk = sum(x.R - r.ctrl.R for r, x in mk)
        dst = sum(x.R - r.ctrl.R for r, x in st)
        mk_diff = [(r.tr.t, r.tr.d.isoformat()[5:], round(x.R - r.ctrl.R, 2), r.ctrl.status, x.status) for r, x in mk if abs(x.R - r.ctrl.R) > 0.005]
        st_pos = sorted(((x.R - r.ctrl.R, r.tr.t) for r, x in st if x.R - r.ctrl.R > 0.005), reverse=True)
        out(f"  {name}: paired d {m['delta_total']:+.2f}R = {dst:+.2f}R on {len(st)} both-settled pairs + {dmk:+.2f}R on {len(mk)} pairs with a "
            f"mark on either side (the marked pairs that differ: {mk_diff}); both-settled d without its two largest gains "
            f"{dst - sum(x for x, _ in st_pos[:2]):+.2f}R (those: {[(t, round(x, 2)) for x, t in st_pos[:2]]})")
    out("  own top2 / top5 = share of the arm's OWN total R carried by its 2 / 5 best trades; d top5 share = the 5 largest positive "
        "paired gains / the paired total (the 10-16 'top-five share'); sep95 = week-block p < 0.05 AND the week-bootstrap 95% CI of "
        "the per-trade paired difference excludes 0.")
    return seps


# ═════════════════════════ main ═════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", action="store_true", help="use HEAD's code instead of the pinned 8fca6649 tree (drift check only)")
    a = ap.parse_args()
    tag = "HEAD" if a.head else f"pinned {PIN_COMMIT}"
    sfx = "_head" if a.head else ""
    txt_path = f"{HERE}/recut_open_floor{sfx}.txt"

    with tempfile.TemporaryDirectory(prefix="recut1103_") as tmp:
        code_root = REPO if a.head else materialise_pinned(tmp)
        rc = load_recut(code_root)
        if not a.head:
            assert_code_origin(code_root)
        out("=" * 110)
        out(f"RUNNER RE-CUT UNDER THE OPEN-FLOOR ADMISSION RULE (#718) — code: {tag}; python {sys.version.split()[0]}")
        out("=" * 110)
        if not a.head:
            out(f"code: git archive {PIN_COMMIT} -> temp dir; blobs verified {PIN_BLOBS}; walker modules loaded from the temp tree "
                f"(asserted for every agents.* / shared.* module)")
        out(f"10-16 code sha256 prefixes verified: {CODE_SHA}")
        out("")

        # ── STEP 1: reproduce ──
        out("STEP 1 — REPRODUCE THE 10-16 RUN")
        inp = rc.load_inputs()
        trades, acct = rc.build_trades(inp)
        okg, rows_full, res_full, text = sweep(rc, inp, trades, acct, f"{HERE}/repro_full{sfx}")
        ref = open(f"{SRC}/run.out").read()
        mine = text.replace(f"{HERE}/repro_full{sfx}", SRC)
        diff_lines = [(i, x, y) for i, (x, y) in enumerate(zip(ref.splitlines(), mine.splitlines())) if x != y]
        same_len = len(ref.splitlines()) == len(mine.splitlines())
        rows_same = open(f"{SRC}/run_rows.tsv", "rb").read() == open(f"{HERE}/repro_full{sfx}/run_rows.tsv", "rb").read()
        json_same = open(f"{SRC}/run_results.json", "rb").read() == open(f"{HERE}/repro_full{sfx}/run_results.json", "rb").read()
        doc = open(f"{REPO}/docs/analysis/runner_recut_results_2026-10-16.md").read()
        tlines = doc_table_lines(json.load(open(f"{HERE}/repro_full{sfx}/run_results.json")), rc.RULES)
        missing = [l for l in tlines if l not in doc]
        out(f"  gates on the full population: {'ALL PASS' if okg else 'RED'}")
        out(f"  stdout vs _runner_recut_1017/run.out: {len(ref.splitlines())} vs {len(mine.splitlines())} lines; "
            f"lines that differ after mapping the dump path: {len(diff_lines)}")
        out(f"  run_rows.tsv byte-identical to the 10-16 dump: {rows_same}")
        out(f"  run_results.json byte-identical to the 10-16 dump: {json_same}")
        out(f"  10-16 doc table rows regenerated from the reproduced results and found verbatim in the doc: "
            f"{len(tlines) - len(missing)} of {len(tlines)}")
        repro_ok = okg and same_len and not diff_lines and rows_same and json_same and not missing
        if not repro_ok:
            for d in diff_lines[:10]:
                out(f"    line {d[0]}: 10-16 {d[1]!r}\n             now {d[2]!r}")
            for l in missing[:10]:
                out(f"    not in doc: {l}")
            out("  REPRODUCTION FAILED — STOP (no re-cut numbers are printed).")
            open(txt_path, "w").write("\n".join(LOG) + "\n")
            sys.exit(2)
        out("  REPRODUCTION: PASS (the 10-16 table, stdout and per-trade dumps reproduce exactly)")
        out("")

        # ── STEP 2: the open floor ──
        out("STEP 2 — DROP EVERY RUN-U ROW WHOSE 09:30 OPEN < round(prev_close x 1.09, 6)")
        o930 = {}
        for (d, t), bars in inp.mbars.items():
            b = next((x for x in bars if x[0] == "09:30"), None)
            if b is not None:
                o930[(t, d.isoformat())] = b[1]
        status_full = {}
        for r in rows_full:
            status_full[r.tr.key] = r
        acct_reason = {}
        # re-derive each row's fill-model fate (same code path as build_trades) for the drop table
        for a_ in inp.rows_u:
            one = rc.Inputs([a_], inp.mbars, inp.daily, inp.all_dates, inp.hashes)
            tr1, ac1 = rc.build_trades(one)
            acct_reason[(a_["t"], a_["d"])] = "filled" if tr1 else next(k for k, v in ac1.items() if v and k != "filled")
        kept_rows_u, dropped = [], []
        side_disagree, no_bar, open_diff = [], [], []
        pc_mismatch = []
        for a_ in inp.rows_u:
            k = (a_["t"], a_["d"])
            floor = round(a_["prev_close"] * FLOOR_MULT, 6)
            ob = o930.get(k)
            if ob is None:
                no_bar.append(k)
            # the capture's own prev close vs the daily capture's prior close (should be identical)
            prior = [x for x in inp.daily.get(a_["t"], []) if x[0].isoformat() < a_["d"]]
            if prior and abs(prior[-1][4] - a_["prev_close"]) > 1e-9:
                pc_mismatch.append(k)
            the_open = ob if ob is not None else a_["open"]
            if (a_["open"] < floor) != (the_open < floor):
                side_disagree.append(k)
            if ob is not None and abs(ob - a_["open"]) > 1e-9:
                open_diff.append((k, ob, a_["open"]))
            if the_open < floor:
                dropped.append((a_, the_open, floor))
            else:
                kept_rows_u.append(a_)
        out(f"  source of the open: the 09:30 minute bar's open in bt_out_bars (what live stage 4a reads, orb_bar['open']); "
            f"rows with no 09:30 bar: {len(no_bar)} (they fall back to the admission row's 'open')")
        out(f"  cross-checks: the admission row's own 'open' lands on the same side of the floor on {len(inp.rows_u) - len(side_disagree)} of "
            f"{len(inp.rows_u)} rows (09:30-bar open differs in value on {len(open_diff)} rows: {[(k, ob, ro) for k, ob, ro in open_diff][:5]}); "
            f"the row's prev_close equals the daily capture's prior close on {len(inp.rows_u) - len(pc_mismatch)} of {len(inp.rows_u)}")
        n_drop = len(dropped)
        gap_cls = Counter((a_["gap_open"] >= 9, (a_["gap_scan"] or -1) >= 9) for a_, _, _ in dropped)
        gap_cls_all = Counter((a_["gap_open"] >= 9, (a_["gap_scan"] or -1) >= 9) for a_ in inp.rows_u)
        out(f"  DROPPED: {n_drop} of {len(inp.rows_u)} Run-U rows; kept {len(kept_rows_u)}")
        out(f"  seeding arm of the dropped rows (opened>=9%, premarket tick>=9%): {dict(gap_cls)}; whole population: {dict(gap_cls_all)}")
        fate = Counter(acct_reason[(a_['t'], a_['d'])] for a_, _, _ in dropped)
        out(f"  fate of the dropped rows under the fill model: {dict(fate)}")
        sc_drop = [status_full[(a_['t'], a_['d'])] for a_, _, _ in dropped if (a_['t'], a_['d']) in status_full]
        sc_drop_scored = [r for r in sc_drop if r.ctrl.R is not None]
        out(f"  of the 194 filled: {len(sc_drop)} dropped; of the 185 scored: {len(sc_drop_scored)} dropped "
            f"(control status of the dropped filled: {dict(Counter(r.ctrl.status for r in sc_drop))})")
        dR = sum(r.ctrl.R for r in sc_drop_scored)
        pR = sum(r.arms[rc.PRIMARY].R for r in sc_drop_scored if r.arms[rc.PRIMARY].R is not None)
        out(f"  what the dropped scored trades carried in the 10-16 run: control {dR:+.2f}R of +44.27R; primary {pR:+.2f}R of +50.96R; "
            f"paired difference {pR - dR:+.2f}R of +6.69R")
        dRs = sorted((r.ctrl.R for r in sc_drop_scored), reverse=True)
        top2d = sorted(((r.ctrl.R, r.tr.key) for r in sc_drop_scored), reverse=True)[:2]
        out(f"  the dropped scored trades under the control (descriptive): n {len(dRs)}, total {sum(dRs):+.2f}R, mean {sum(dRs) / len(dRs):+.3f}R, "
            f"median {statistics.median(dRs):+.3f}R, win {100 * sum(1 for x in dRs if x > 0) / len(dRs):.1f}%, "
            f"without its two best {[(k[0], k[1], round(x, 2)) for x, k in top2d]} {sum(dRs[2:]):+.2f}R")
        tail_drop = sorted(r.tr.key for r in sc_drop_scored if r.ctrl.R >= rc.TAIL_R - 1e-9)
        out(f"  control +4R winners dropped: {len(tail_drop)} of 10 -> {tail_drop}")
        engA = sorted(r.tr.key for r in sc_drop_scored if "A" in r.copy0["trig"])
        out(f"  Frame A engaged (reached the +8 ORB-R partial) trades dropped: {len(engA)} of 29 -> {engA}")
        near = sorted(((o / f - 1) * 100, a_["t"], a_["d"]) for a_, o, f in dropped if (1 - o / f) * 100 <= NEAR_TIE_PCT)
        out(f"  dropped rows within {NEAR_TIE_PCT:.2f}% under the line (descriptive; the rule is strictly below): "
            f"{[(t, d, round(p, 3), acct_reason[(t, d)]) for p, t, d in near]}")
        with open(f"{HERE}/dropped_rows{sfx}.tsv", "w") as fh:
            fh.write("ticker\tdate\topen_0930\trow_open\tprev_close\tfloor\topen_vs_floor_pct\tgap_open_pct\tgap_scan_pct\tfate\t"
                     "ctrl_status\tctrl_R\tprimary_R\treached_8R\n")
            for a_, o, f in sorted(dropped, key=lambda x: (x[0]["d"], x[0]["t"])):
                k = (a_["t"], a_["d"])
                r = status_full.get(k)
                cr = "" if r is None or r.ctrl.R is None else f"{r.ctrl.R:.4f}"
                pr = "" if r is None or r.arms[rc.PRIMARY].R is None else f"{r.arms[rc.PRIMARY].R:.4f}"
                fh.write(f"{a_['t']}\t{a_['d']}\t{o}\t{a_['open']}\t{a_['prev_close']}\t{f}\t{(o / f - 1) * 100:.3f}\t{a_['gap_open']}\t"
                         f"{a_['gap_scan']}\t{acct_reason[k]}\t{r.ctrl.status if r else ''}\t{cr}\t{pr}\t"
                         f"{'yes' if r is not None and 'A' in r.copy0['trig'] else ''}\n")
        out(f"  the full dropped list (ticker, date):")
        dl = [f"{a_['t']} {a_['d'][5:]}" for a_, _, _ in sorted(dropped, key=lambda x: (x[0]["d"], x[0]["t"]))]
        for i in range(0, len(dl), 12):
            out("    " + ", ".join(dl[i:i + 12]))
        out(f"  per-row detail (open, floor, fate, R): {HERE}/dropped_rows{sfx}.tsv")
        out("")

        # ── STEP 3: the identical sweep on the kept rows ──
        out("STEP 3 — THE IDENTICAL SWEEP ON THE KEPT ROWS (recut.run_gates + recut.do_run, unchanged)")
        inp_k = rc.Inputs(kept_rows_u, inp.mbars, inp.daily, inp.all_dates, inp.hashes)
        trades_k, acct_k = rc.build_trades(inp_k)
        out(f"  kept population: {len(kept_rows_u)} Run-U rows on {len({a_['t'] for a_ in kept_rows_u})} tickers -> {dict(acct_k)}")
        out("  (recut.do_run's own header line below still prints 'population: <n> Run-U replayable rows' for the KEPT set)")
        okg_k, rows_k, res_k, text_k = sweep(rc, inp_k, trades_k, acct_k, f"{HERE}/kept{sfx}")
        # the filter only removes rows: every kept trade walks identically to the full run
        full_by = {r.tr.key: r for r in rows_full}
        neq = []
        for r in rows_k:
            f = full_by[r.tr.key]
            pairs = [(r.ctrl.R, f.ctrl.R)] + [(r.arms[k].R, f.arms[k].R) for k in r.arms] + [(r.refs[k].R, f.refs[k].R) for k in r.refs]
            if any((x is None) != (y is None) or (x is not None and abs(x - y) > 1e-12) for x, y in pairs):
                neq.append(r.tr.key)
        out(f"  check: every kept trade's R under every arm equals its R in the full run: {not neq} ({len(rows_k)} trades x 26 walks; "
            f"differ {neq[:5]})")
        out("")
        for line in text_k.rstrip("\n").splitlines():
            out("  | " + line)
        out("")
        if not okg_k:
            out("  A GATE IS RED ON THE KEPT ROWS — STOP.")
            open(txt_path, "w").write("\n".join(LOG) + "\n")
            sys.exit(3)

        out("  THE 10-16 TABLE LAYOUT, KEPT ROWS (same formatter as the 10-16 doc):")
        out("  " + DOC_HEAD.replace("\n", "\n  "))
        for l in doc_table_lines(res_k, rc.RULES):
            out("  " + l)
        out("")
        seps_k = compact_table(rc, rows_k, res_k, "  PER ARM, KEPT ROWS — n, mean, median, win, concentration, separation:")
        out("")
        seps_f = compact_table(rc, rows_full, res_full, "  PER ARM, FULL 10-16 POPULATION (for side-by-side; same code):")
        out("")
        out(f"  arms at week-block p < 0.05 — full: {seps_f or 'none'}; kept: {seps_k or 'none'}")
        out("")

        # ── STEP 4: the bar ──
        out("STEP 4 — THE 10-16 BAR (pre-registration §5), APPLIED MECHANICALLY TO THE PRIMARY")
        vf, vk = res_full["verdict"], res_k["verdict"]
        pf, pk = res_full["arms"]["A|t20_be"], res_k["arms"]["A|t20_be"]
        out(f"  {'':<4}{'full (10-16)':<44}{'kept (open floor)':<44}")
        out(f"  P1  {str(vf['P1']) + ' (differ ' + str(pf['differ_n']) + ', weeks ' + str(pf['differ_weeks']) + ')':<44}"
            f"{str(vk['P1']) + ' (differ ' + str(pk['differ_n']) + ', weeks ' + str(pk['differ_weeks']) + ')':<44}")
        out(f"  P2  {str(vf['P2']) + ' (d {:+.2f}R, p {:.3f})'.format(pf['delta_total'], pf['p_weekblock']):<44}"
            f"{str(vk['P2']) + ' (d {:+.2f}R, p {:.3f})'.format(pk['delta_total'], pk['p_weekblock']):<44}")
        out(f"  P3  {str(vf['P3']) + ' (ex top 2 {:+.2f}R)'.format(pf['delta_ex_top2']):<44}"
            f"{str(vk['P3']) + ' (ex top 2 {:+.2f}R)'.format(pk['delta_ex_top2']):<44}")
        out(f"  P4  {str(vf['P4']) + ' (H1 {:+.2f} / H2 {:+.2f})'.format(pf['h1'], pf['h2']):<44}"
            f"{str(vk['P4']) + ' (H1 {:+.2f} / H2 {:+.2f})'.format(pk['h1'], pk['h2']):<44}")
        out(f"  P5  {str(vf['P5']) + ' (+4R {} vs {})'.format(pf['n_tail'], pf['n_tail_ctrl']):<44}"
            f"{str(vk['P5']) + ' (+4R {} vs {})'.format(pk['n_tail'], pk['n_tail_ctrl']):<44}")
        out(f"  P6  {str(vf['P6']):<44}{str(vk['P6']):<44}")
        out(f"  WORD  {vf['word']:<42}{vk['word']:<44}")
        out(f"  next exploratory primary registered — full: {res_full['next_primary'] or 'none'}; kept: {res_k['next_primary'] or 'none'}")
        out(f"  Frame B expectation wrong? — full: {res_full['frame_b_expectation_wrong'] or 'no'}; kept: {res_k['frame_b_expectation_wrong'] or 'no'}")
        Ck = res_k["control"]
        for lab, rws in (("full", rows_full), ("kept", rows_k)):
            sc = [r for r in rws if r.ctrl.R is not None]
            mk = [r for r in sc if r.ctrl.status == "data_end"]
            pa = [r for r in rws if r.arms[rc.PRIMARY].R is not None and r.ctrl.R is not None]
            pmk = [r for r in pa if r.arms[rc.PRIMARY].status == "data_end"]
            out(f"  marks ({lab}): control {len(mk)} positions open at 2026-08-28 carry {sum(r.ctrl.R for r in mk):+.2f}R of "
                f"{sum(r.ctrl.R for r in sc):+.2f}R (settled trades alone {sum(r.ctrl.R for r in sc if r.ctrl.status != 'data_end'):+.2f}R); "
                f"primary {len(pmk)} marks carry {sum(r.arms[rc.PRIMARY].R for r in pmk):+.2f}R of {sum(r.arms[rc.PRIMARY].R for r in pa):+.2f}R")
        out(f"  control, kept: n {Ck['n']}, total {Ck['total']:+.2f}R, mean {Ck['mean']:+.3f}R, median {Ck['median']:+.3f}R, "
            f"win {100 * Ck['win']:.1f}%, +4R {Ck['n_tail']}, open at data end {Ck['open_e']}")
        out(f"  primary, kept: total {pk['total']:+.2f}R, mean {pk['mean']:+.3f}R, median {pk['median']:+.3f}R, d {pk['delta_total']:+.2f}R "
            f"({pk['delta_mean']:+.3f}R/trade, CI [{pk['boot_lo']:+.3f}, {pk['boot_hi']:+.3f}]), p {pk['p_weekblock']:.3f}, "
            f"top-5 gains {pk['top5']}")
        out("")
        out("LIMITATIONS (stated, not modelled):")
        out("  - Live, #718 refuses only names ADMITTED BY THE REAL-TIME FLIP-UP whose open is below the floor; a name admitted by the "
            "delayed read is entered even if it opened below. The capture cannot tell the two apart, so this cut drops EVERY "
            "opened-below row: an upper bound on what the rule removes. A row that opened at/above 9% is unaffected either way.")
        out("  - Every dropped row is a premarket-tick seed (opened < 9%, a premarket tick >= 9%); every kept row opened >= 9%.")
        out("  - Exit stack: the control is the 10-16 era-E depth exit. The live exit has since changed (2026-10-28 'the trailing line governs "
            "only after the trade was above it', live from the 10-29 session; exit_discipline.md). This re-cut does NOT model it (one change only).")
        out("  - Run U's fill model does not apply the #490 09:31 live-price gap re-check (stage 4b, on since 2026-08-02), which already "
            "refuses a name trading under the 9% floor at submission; many dropped rows (e.g. AOSL opened +1.2%, SGML +3.6%) were likely "
            "refused by it before #718 existed. The dropped rows' money is money in rows Run U admitted that today's pipeline would not "
            "enter, NOT the cost of the 11-03 flip.")
        out("  - HEAD's replay code (which carries the 10-28 trail-arming fix) gives byte-identical output (recut_open_floor_head.txt): the "
            "fix is session-gated from 2026-10-29, so it is neutral on this Apr-Aug population by construction, not by measurement.")
        out("  - 'registered as the next primary' is the 10-16 exploratory rule applied mechanically; nothing is registered here (the 10-16 "
            "doc says this window is not re-cut again; registration and any proposal are the operator's). The 22 arms walk the same "
            "engaged trades (19 in Frame A, 50 in Frame B): correlated arms on one population, not 21 independent tests.")
        out("  - Every row's median is the same (-0.773R kept, -0.530R full): the median trade never reaches a trigger, so no exit rule can move it.")
        out("  - Inherited from 10-16: Run U's 2026-08-29 admission manifest (over-admits), daily bars after day 0, positions open at "
            "2026-08-28 marked at their last close (the refused extension), no portfolio effects.")

    open(txt_path, "w").write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
