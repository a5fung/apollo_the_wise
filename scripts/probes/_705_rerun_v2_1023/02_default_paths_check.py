#!/usr/bin/env python3
"""#705 v2 re-run: with NO CB_PRE_* variable set, every edited script resolves exactly the paths it hard-coded before the edit.
Imports the edited modules that are safe to import (no work at import time) and checks, per era, the data dir, the table dir
(`out_dir`) and the log dir against the literal strings of the original code; the two report scripts that run at import time
(entry_stop_retry 03_report.py, trail_variants 03_report.py) are checked on their source text. Opens no data file."""
import importlib.util, os, re, sys

for k in [k for k in os.environ if k.startswith("CB_PRE_")]:
    del os.environ[k]
P = "/Users/alvinfung/apollo_the_wise/scripts/probes"
PRE, POST = "/Users/alvinfung/apollo_data/cb702_pre", "/Users/alvinfung/apollo_data/cb702"
bad = []


def load(name, path, argv=()):
    sys.argv = [path, *argv]
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def check(label, ok):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        bad.append(label)


sys.dont_write_bytecode = True
m = load("ep01", f"{P}/_702_winner_recall_1022/01_episodes.py")
check("winner_recall 01_episodes: ERAS data dirs", m.ERAS["2017-21"]["data"] == PRE and m.ERAS["2022-24"]["data"] == POST)
check("winner_recall 01_episodes: out_dir = DATA/out, both eras", m.out_dir("2017-21", PRE) == f"{PRE}/out" and m.out_dir("2022-24", POST) == f"{POST}/out")
check("winner_recall 01_episodes: log dir = HERE", m.LOG_DIR == m.HERE and m.PRE_OUT is None)
m = load("catch", f"{P}/_702_winner_recall_1022/02_catch.py")
check("winner_recall 02_catch: ERAS data dirs", m.ERAS["2017-21"]["data"] == PRE and m.ERAS["2022-24"]["data"] == POST)
check("winner_recall 02_catch: out_dir / log dir", m.out_dir("2017-21", PRE) == f"{PRE}/out" and m.LOG_DIR == m.HERE and m.PRE_OUT is None)
m = load("wr03", f"{P}/_702_winner_recall_1022/03_report.py")
check("winner_recall 03_report: DATA, out_dir, log dir", m.DATA == {"2017-21": PRE, "2022-24": POST} and m.out_dir("2017-21") == f"{PRE}/out"
      and m.out_dir("2022-24") == f"{POST}/out" and m.LOG_DIR == m.HERE)
m = load("bd02", f"{P}/_702_breakout_definition_1022/02_build.py")
check("breakout_definition 02_build: ERAS data dirs", m.ERAS["2017-21"]["data"] == PRE and m.ERAS["2022-24"]["data"] == POST)
check("breakout_definition 02_build: out_dir / log dir", m.out_dir("2017-21", PRE) == f"{PRE}/out" and m.out_dir("2022-24", POST) == f"{POST}/out" and m.LOG_DIR == m.HERE)
m = load("bd03", f"{P}/_702_breakout_definition_1022/03_report.py")
check("breakout_definition 03_report: DATA (already ends in /out), log dir", m.DATA == {"2017-21": f"{PRE}/out", "2022-24": f"{POST}/out"} and m.LOG_DIR == m.HERE)
m = load("esr_lib", f"{P}/_702_entry_stop_retry_1022/esr_lib.py")
check("entry_stop_retry esr_lib: ERAS data dirs", m.ERAS["2017-21"]["data"] == PRE and m.ERAS["2022-24"]["data"] == POST)
check("entry_stop_retry esr_lib: out_dir / log dir", m.out_dir("2017-21", PRE) == f"{PRE}/out" and m.out_dir("2022-24", POST) == f"{POST}/out"
      and m.LOG_DIR == m.HERE and m.PRE_OUT is None)
m = load("esr02", f"{P}/_702_entry_stop_retry_1022/02_build.py")
check("entry_stop_retry 02_build: log dir = HERE", m.LOG_DIR == m.HERE and m.PRE_OUT is None)
m = load("trail_lib", f"{P}/_702_trail_variants_1023/trail_lib.py")
check("trail_variants trail_lib: ERAS data dirs (shared with esr_lib)", m.ERAS["2017-21"]["data"] == PRE and m.ERAS["2022-24"]["data"] == POST
      and m.out_dir("2017-21", PRE) == f"{PRE}/out")
m = load("tr02", f"{P}/_702_trail_variants_1023/02_build.py")
check("trail_variants 02_build: log dir = HERE, entry-stop-retry dir = PREV, no table-dir override",
      m.LOG_DIR == m.HERE and m.PREV_DIR == m.PREV and m.PRE_OUT is None)
for path, here in ((f"{P}/_702_entry_stop_retry_1022/03_report.py", "_702_entry_stop_retry_1022"), (f"{P}/_702_trail_variants_1023/03_report.py", "_702_trail_variants_1023")):
    src = open(path).read()
    check(f"{here} 03_report.py (source): LOG_DIR defaults to HERE, ERAS default both eras",
          'LOG_DIR = os.environ.get("CB_PRE_LOG", HERE)' in src and 'ERAS = tuple(sys.argv[1:]) or ("2017-21", "2022-24")' in src and "/Users/alvinfung/apollo_data/cb702_pre" not in src)
print("ALL DEFAULTS UNCHANGED" if not bad else f"{len(bad)} FAILED")
sys.exit(1 if bad else 0)
