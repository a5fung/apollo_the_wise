#!/usr/bin/env python3
"""#705 v2 re-run, B7 PROOFS of `v2_compare.py`, before the freeze (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md §4 B7). On the PUBLISHED old
sources only (no v2 number exists):
  P1  old against old (a flat copy of every §7 source) -> "holds" on every deciding line, every read's conclusion holds, every check passes, no source
      check fires (each old value read equals the value §7 quotes), and every restored-only method reproduces the read's own number on all rows
  P2  the restored-only path on real rows: the same, with a restored set made of the old file's B* symbols -> a value printed on every deciding line
  P4  a failed check line (4.0) -> that read is NOT COMPARED; every line prints its source
  P3  pushed values, one at a time, in a copy - each must flip exactly that line to "changes" and that read's conclusion to "changes":
        1.6 lo -> +0.001 (SPANS -> ABOVE); 2.2 watched 240 -> 210 (49.9% -> 43.7%, past +-5); 3.1 another cell 20 doublers better (the best cell moves);
        4.4b the A20_X3_P0 interval pushed below zero (SPANS -> BELOW); 1.1 the median 1.16 -> -0.10 (the direction flips)
  P5  the check line 2.0 pushed (994 -> 993 big winners) -> FAILS and read 2 NOT COMPARED, the other reads hold
  P6  S6's verdict word changed (loss -> can't tell) -> S6 changes (R2 + R1: the word alone decides)
  P7  1.6's interval made NaN (a broken resample) -> 1.6 NOT COMPARED and read 1 NOT COMPARED - never "holds"
  P8  the CLI in --proofs mode, old vs old -> exit 0, every source's sha256 printed; without --proofs a proof option refuses (exit 2)
  P9  §7's tables (the doc above the marker) = the script's lines, roles and rules
    python3 scripts/probes/_705_rerun_v2_1023/v2_compare_proofs.py SCRATCH_DIR     # receipt -> v2_compare_proofs.txt beside this file
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.probes._705_rerun_v2_1023 import v2_compare as vc  # noqa: E402

RECEIPT = Path(__file__).resolve().parent / "v2_compare_proofs.txt"
lines, res = [], []


def say(s=""):
    print(s, flush=True)
    lines.append(s)


def rec(label, ok, note=""):
    res.append(ok)
    say(f"{'PASS' if ok else 'FAIL'}  {label}{('  ' + note) if note else ''}")


def flat_copy(d: Path) -> Path:
    """Every §7 source copied (json / md / tsv) or linked (the row tables) under its logical name."""
    d.mkdir(parents=True)
    for k, (old, _new) in vc.LOGICAL.items():
        if k.endswith(".tsv.gz"):
            (d / k).symlink_to(old)
        else:
            shutil.copyfile(old, d / k)
    return d


def run(new_flat: Path, out: Path, guards=None) -> tuple:
    vc.EXPECT["episodes"] = 994
    rest = vc.restored_symbols(*guards) if guards else vc.restored_symbols()
    rows, concl = vc.compare(vc.Src("old"), vc.Src("new", new_flat), rest)
    out.write_text(vc.render(rows, concl, vc.Src("old"), vc.Src("new", new_flat)) + "\n")
    return {r["id"]: r for r in rows}, concl


def edit_json(path: Path, fn) -> None:
    d = json.loads(path.read_text())
    fn(d)
    path.write_text(json.dumps(d))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    if root.exists():
        sys.exit(f"REFUSED: {root} exists")
    say("#705 v2 B7 proofs of v2_compare.py (on the published old sources; no v2 number exists)")
    base = flat_copy(root / "old_flat")
    rows, concl = run(base, root / "P1.txt")
    dec = [r for r in rows.values() if r["role"] == "deciding"]
    rec("P1 old vs old: every deciding line holds", all(r["verdict"] == "holds" for r in dec), f"{len(dec)} deciding lines")
    rec("P1 old vs old: every read's conclusion holds", all(concl[k][0] == "holds" for k in (1, 2, 3, 4)), str({k: v[0] for k, v in concl.items()}))
    rec("P1 old vs old: every check passes (2.0 at 994, 4.0)", all(r["verdict"] == "passes" for r in rows.values() if r["role"] == "check"))
    rec("P1 old vs old: every beside and stage line holds or is reported", all(r["verdict"] in ("holds", "reported") for r in rows.values() if r["role"] in ("beside", "stage")))
    rec("P1 old vs old: no source check fires (each old value read = the value §7 quotes)", not any(r["source_check"] for r in rows.values()),
        "; ".join(f"{r['id']}: {r['source_check']}" for r in rows.values() if r["source_check"]))
    rec("P1 old vs old: every restored-only method reproduces the read's own number (none withheld)",
        all(r["restored"] == "restored-only: none (no restored row)" for r in dec), "; ".join(f"{r['id']}: {r['restored']}" for r in dec if "none" not in r["restored"]))
    # P2: a restored set made of the old file's B* symbols (through the guards)
    g_new = vc.OLD_DATA / "symbol_guard.tsv"
    g_old = root / "guard_without_B.tsv"
    g = g_new.read_text().splitlines(keepends=True)
    g_old.write_text("".join([g[0]] + [ln for ln in g[1:] if not ln.startswith("B")]))
    rows2, _c = run(base, root / "P2.txt", guards=(g_new, g_old))
    vals = {r["id"]: r["restored"] for r in rows2.values() if r["role"] == "deciding"}
    rec("P2 the restored-only path prints a value on every deciding line (B* as the restored set)",
        all(v.startswith("restored-only: ") and "none" not in v and "withheld" not in v and "not computed" not in v for v in vals.values()),
        "; ".join(f"{k}: {v[15:90]}" for k, v in vals.items()))
    # P3: pushed values
    pushes = [
        ("1.6", 1, "read1_03_numbers.json", lambda d: d[vc.R1KEY][vc.Q + "share >= 5 ADR within 60"].__setitem__("lo", 0.001)),
        ("2.2", 2, "read2_03_numbers.json", lambda d: d["2017-21/x200/funnel"][vc.FUNNEL["watched"]].__setitem__(0, 210)),
        ("3.1", 3, "read3_03_headline.json", lambda d: d["2017-21"]["win_S1_T2"].__setitem__("still_in_s50", 233)),
        ("4.4b", 4, "read4_03_headline.json", lambda d: d["2017-21"]["A20_X3_P0"]["R1_T0"]["diff"].update(diff=-0.08, lo=-0.12, hi=-0.01)),
    ]
    for lid, rd, name, fn in pushes:
        d = flat_copy(root / f"push_{lid}")
        edit_json(d / name, fn)
        r, c = run(d, root / f"P3_{lid}.txt")
        changed = sorted(k for k, v in r.items() if v["verdict"] == "changes")
        rec(f"P3 push {lid}: that line -> changes, and only it among the deciding lines", [k for k in changed if r[k]["role"] == "deciding"] == [lid],
            f"{lid} {r[lid]['verdict']}: {r[lid]['note']}")
        rec(f"P3 push {lid}: read {rd}'s conclusion -> changes, the other reads hold", c[rd][0] == "changes" and all(c[k][0] == "holds" for k in (1, 2, 3, 4) if k != rd),
            f"{c[rd]}")
    # P4: a failed check (4.0: read 4's pp cell no longer read 3's S2 cell) -> read 4 is NOT COMPARED, the other reads hold
    d = flat_copy(root / "push_4.0")
    edit_json(d / "read4_03_headline.json", lambda x: x["2017-21"]["A20_X1_P1"]["win_T2"].__setitem__("kept_half", 9))
    r, c = run(d, root / "P4_4.0.txt")
    rec("P4 push 4.0: the check FAILS -> read 4 NOT COMPARED, the other reads hold", r["4.0"]["verdict"] == "FAILS" and c[4][0] == "NOT COMPARED"
        and all(c[k][0] == "holds" for k in (1, 2, 3)), f"{c[4]}")
    p1 = (root / "P1.txt").read_text()
    rec("P1 every line prints the source it read (old and new path + the key)", p1.count("        source: old ") == len(rows), f"{p1.count('        source: old ')} of {len(rows)} lines")
    d = flat_copy(root / "push_1.1")
    md = (d / "read1_03_report.md").read_text()
    (d / "read1_03_report.md").write_text(re.sub(r"(\| 2017-21 \| n = 13,363 \| )1\.16( \|)", r"\g<1>-0.10\2", md, count=1))
    r, c = run(d, root / "P3_1.1.txt")
    rec("P3 push 1.1: the median's direction flips -> changes; read 1 changes", r["1.1"]["verdict"] == "changes" and c[1][0] == "changes", r["1.1"]["note"])
    # P5: the 2.0 check pushed
    d = flat_copy(root / "push_2.0")
    edit_json(d / "read2_03_numbers.json", lambda x: x["2017-21/x200/composition"].__setitem__("n", 993))
    r, c = run(d, root / "P5_2.0.txt")
    rec("P5 push 2.0 (993 big winners, target 994): the check FAILS -> read 2 NOT COMPARED, the other reads hold",
        r["2.0"]["verdict"] == "FAILS" and c[2][0] == "NOT COMPARED" and all(c[k][0] == "holds" for k in (1, 3, 4)), f"{r['2.0']['note']}; {c[2]}")
    # P6: S6's verdict word
    d = flat_copy(root / "push_S6")
    edit_json(d / "exitpb_verdict_pre.json", lambda x: x["delta_c1"].__setitem__("verdict", "can't tell"))
    r, c = run(d, root / "P6_S6.txt")
    rec("P6 push S6's word (loss -> can't tell): S6 changes", r["S6"]["verdict"] == "changes", r["S6"]["note"])
    # P7: a NaN interval on a deciding line
    d = flat_copy(root / "push_1.6_nan")
    edit_json(d / "read1_03_numbers.json", lambda x: x[vc.R1KEY][vc.Q + "share >= 5 ADR within 60"].update(lo=float("nan"), hi=float("nan")))
    r, c = run(d, root / "P7_1.6_nan.txt")
    rec("P7 1.6's interval NaN: 1.6 NOT COMPARED and read 1 NOT COMPARED (never holds); the other reads hold",
        r["1.6"]["verdict"] == "NOT COMPARED" and c[1][0] == "NOT COMPARED" and all(c[k][0] == "holds" for k in (2, 3, 4)), f"{c[1]}")
    # P8: the CLI
    rc = vc.main(["--proofs", "--new-flat", str(base), "--out", str(root / "P8_cli.txt"), "--expect-episodes", "994"])
    p8 = (root / "P8_cli.txt").read_text() if (root / "P8_cli.txt").exists() else ""
    rec("P8 the CLI in --proofs mode: exit 0, every read holds, every source's sha256 printed", rc == 0 and p8.count("CONCLUSION HOLDS") == 4
        and "SOURCE SHA256" in p8, f"exit {rc}")
    rec("P8 a proof option without --proofs refuses (exit 2), nothing written", vc.main(["--new-flat", str(base), "--out", str(root / "P8_bad.txt")]) == 2
        and not (root / "P8_bad.txt").exists())
    # P9: §7 = the script
    pr = vc.section7_problems(vc.DOC.read_text(encoding="utf-8"))
    rec("P9 §7's tables (lines, roles, rules, stated R3 tolerances, the 2.0 target) = the script's", pr == [], "; ".join(pr))
    say(f"\nB7 PROOFS: {sum(res)} of {len(res)} pass -> {'ALL PASS' if all(res) else 'FAILURES'}")
    RECEIPT.write_text("\n".join(lines) + "\n")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
