#!/usr/bin/env python3
"""#705 v2 re-run, PARITY receipt: each read re-run with inputs = cb702_pre (switches CB_PRE_*) into
cb702_pre_v2/out/rerun_1023/parity/<read>/, compared with the table / numbers file that the docs cite.
  * .tsv.gz   - the DECOMPRESSED bytes (a gzip header carries an mtime, so the .gz bytes differ by design)
  * .parquet  - sha256 of the file
  * .json     - equal as JSON (numbers files: the 2017-21 part only where the cited file also holds 2022-24)
  * .tsv/.txt - byte-equal, or equal after masking wall-clock seconds and absolute data paths (logs)
  * .md       - the 2017-21 section of the cited report equals the re-run report (trailing blank line ignored)
Prints one line per file and a verdict; writes nothing but its stdout (captured in parity_results.txt)."""
import gzip, hashlib, json, re, sys

R = "/Users/alvinfung/apollo_data/cb702_pre_v2/out/rerun_1023/parity"
O = "/Users/alvinfung/apollo_data/cb702_pre/out"
P = "/Users/alvinfung/apollo_the_wise/scripts/probes"
res = []


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def gz_equal(a, b):
    with gzip.open(a, "rb") as fa, gzip.open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 24), fb.read(1 << 24)
            if x != y:
                return False
            if not x:
                return True


def mask(s):
    s = re.sub(r"/Users/alvinfung/apollo_data/\S*?(?=/(?:wrecall|bdef|esr|trail)_|\s|$)", "<DIR>", s)
    s = re.sub(r"(?<=[\s:;(])\d+s(?=[;)\s]|$)", "Ns", s)
    return re.sub(r"in \d+s", "in Ns", s)


def rec(label, ok, note=""):
    res.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}{('  ' + note) if note else ''}")


def tbl(read, name, old):
    rec(f"{read}/{name}", gz_equal(f"{R}/{read}/{name}", old), "decompressed bytes")


def pq(read, name, old):
    rec(f"{read}/{name}", sha(f"{R}/{read}/{name}") == sha(old), "sha256")


def js(read, name, old, sub=None):
    a, b = json.load(open(f"{R}/{read}/{name}")), json.load(open(old))
    if sub:
        b = sub(b)
    rec(f"{read}/{name}", a == b, "json equal" + (" (2017-21 part)" if sub else ""))


def txt(read, name, old, masked=False):
    a, b = open(f"{R}/{read}/{name}").read(), open(old).read()
    rec(f"{read}/{name}", (mask(a) == mask(b)) if masked else a == b, "text equal after masking timings and data paths" if masked else "byte-equal")


def md(read, name, old, start, end):
    a, b = open(f"{R}/{read}/{name}").read().split("\n"), open(old).read().split("\n")
    i = b.index(start)
    j = b.index(end) if end else len(b)
    rec(f"{read}/{name}", "\n".join(b[i:j]).rstrip() == "\n".join(a).rstrip(), f"section '{start}' equal")


def md_subseq(read, name, old):
    """the winner-recall report interleaves both eras under each factor heading: every line of the 2017-21-only re-run must appear in the cited report, in order"""
    a, b = open(f"{R}/{read}/{name}").read().rstrip().split("\n"), iter(open(old).read().split("\n"))
    miss = sum(1 for ln in a if not any(ln == o for o in b))
    rec(f"{read}/{name}", miss == 0, f"all {len(a)} lines found in order in the cited report ({miss} missing)")


W, B, E, T = (f"{P}/_702_winner_recall_1022", f"{P}/_702_breakout_definition_1022", f"{P}/_702_entry_stop_retry_1022", f"{P}/_702_trail_variants_1023")
# 1 winner recall (01 episodes, 02 catch, 03 report)
for t in ("x200", "x150"):
    tbl("winner_recall", f"wrecall_episodes_2017-21_{t}.tsv.gz", f"{O}/wrecall_episodes_2017-21_{t}.tsv.gz")
    tbl("winner_recall", f"wrecall_catch_2017-21_{t}.tsv.gz", f"{O}/wrecall_catch_2017-21_{t}.tsv.gz")
    tbl("winner_recall", f"wrecall_nights_2017-21_{t}.tsv.gz", f"{O}/wrecall_nights_2017-21_{t}.tsv.gz")
txt("winner_recall", "01_episodes_2017-21.txt", f"{W}/01_episodes_2017-21.txt", True)
txt("winner_recall", "02_catch_2017-21.txt", f"{W}/02_catch_2017-21.txt", True)
txt("winner_recall", "02_reverse_2017-21.txt", f"{W}/02_reverse_2017-21.txt")
js("winner_recall", "03_numbers.json", f"{W}/03_numbers.json", lambda d: {k: v for k, v in d.items() if "2017-21" in k})
md_subseq("winner_recall", "03_report.md", f"{W}/03_report.md")
# 2 breakout definition
for n in ("fills", "r1", "kvar", "control"):
    tbl("breakout_definition", f"bdef_{n}_2017-21.tsv.gz", f"{O}/bdef_{n}_2017-21.tsv.gz")
txt("breakout_definition", "02_build_checks_2017-21.txt", f"{B}/02_build_checks_2017-21.txt", True)
js("breakout_definition", "03_numbers.json", f"{B}/03_numbers.json", lambda d: {k: v for k, v in d.items() if "2017-21" in k})
md("breakout_definition", "03_report.md", f"{B}/03_report.md", "# 2017-21", "# 2022-24")
# 3 entry / stop / retry
for n in ("esr_win", "esr_r1", "esr_ctlsample"):
    tbl("entry_stop_retry", f"{n}_2017-21.tsv.gz", f"{O}/{n}_2017-21.tsv.gz")
pq("entry_stop_retry", "esr_ctl_2017-21.parquet", f"{O}/esr_ctl_2017-21.parquet")
js("entry_stop_retry", "02_numbers_2017-21.json", f"{E}/02_numbers_2017-21.json")
txt("entry_stop_retry", "02_sample_R1_2017-21.tsv", f"{E}/02_sample_R1_2017-21.tsv")
txt("entry_stop_retry", "02_sample_R2_2017-21.tsv", f"{E}/02_sample_R2_2017-21.tsv")
js("entry_stop_retry", "03_headline.json", f"{E}/03_headline.json", lambda d: {"2017-21": d["2017-21"]})
md("entry_stop_retry", "03_report.md", f"{E}/03_report.md", "## 2017-21", "## 2022-24")
# 4 trail variants
for n in ("trail_win", "trail_r1", "trail_ctlsample"):
    tbl("trail_variants", f"{n}_2017-21.tsv.gz", f"{O}/{n}_2017-21.tsv.gz")
pq("trail_variants", "trail_ctlmatch_2017-21.parquet", f"{O}/trail_ctlmatch_2017-21.parquet")
js("trail_variants", "02_numbers_2017-21.json", f"{T}/02_numbers_2017-21.json")
js("trail_variants", "03_headline.json", f"{T}/03_headline.json", lambda d: {"2017-21": d["2017-21"]})
md("trail_variants", "03_report.md", f"{T}/03_report.md", "## 2017-21", "## 2022-24")
print(f"\nPARITY: {sum(res)} of {len(res)} files identical" + ("  -> ALL PASS" if all(res) else "  -> FAILURES"))
sys.exit(0 if all(res) else 1)
