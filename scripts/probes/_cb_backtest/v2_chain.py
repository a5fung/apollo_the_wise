"""#705 v2 re-run (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md) - the chain's shared pieces, ONE module imported by the spec module
(`v2_rerun_read.py`), by `_702_r_decomposition_1022/02_build_paths.py` (when its switch is set) and called by `_705_rerun_v2_1023/04_relaunch.sh`.

  restored set   B8: the symbols in cb702_pre_v2/symbol_guard.tsv and not in cb702_pre/symbol_guard.tsv (the `symbol` column only)
  calendar       B6: the SPY session list in sessions.txt (1,635 sessions 2016-01-04..2022-06-30) - a walked calendar and a log's calendar line
  manifest       B5 / §8: `cb702_pre_v2/out/v2_chain_manifest.tsv`, APPEND-ONLY and hash-chained: every line carries the sha256 of the file it
                 names, the stage that wrote it, the sha256 of the manifest before it (`prev_sha`) and its own (`line_sha`). A later stage refuses
                 when a table it reads differs from the table's manifest line, when any line was rewritten (the chain breaks), or when a label
                 carries more than one line (a table is registered ONCE: `manifest_append` refuses a label already present). Labels are
                 DERIVED from the path (`chain_label`), one rule shared by the runner bodies, 02_build_paths.py, 04_relaunch.sh and v2_compare.py
  test mode      `V2_CHAIN_TEST=1` (tests and the old-file parity receipts only): 04_relaunch.sh and 02_build_paths.py honour their path
                 overrides and the freeze re-check runs `V2_TEST_FREEZE_CMD` instead of the runner; test mode REFUSES the real cb702_pre_v2.
                 Off (the real run): every override refuses and the freeze re-check is `runner.py v2-exit-read --dry-run` (the full §8 freeze check)
  receipt        B5: sha256 of every protected file (§4 table, the read dirs' committed outputs, the 10-23 v2 episode tables, stage 0's pinned
                 copies) and of every file under cb702_pre/, taken before stage 1 (after the freeze) and after stage 7, plus the manifest's final sha256

CLI (04_relaunch.sh and the main loop):
  python3 v2_chain.py manifest-check MANIFEST LABEL PATH [LABEL PATH ...]   exit 2 on a mismatch, a missing line or a broken chain
  python3 v2_chain.py manifest-add MANIFEST STAGE LABEL PATH [LABEL PATH ...]
  python3 v2_chain.py manifest-check-paths MANIFEST PATH [PATH ...]         the same, each label derived from its path (`chain_label`)
  python3 v2_chain.py manifest-add-paths MANIFEST STAGE PATH [PATH ...]
  python3 v2_chain.py freeze-recheck V2_DIR                                 exit 2 unless the §8 freeze check still passes (test mode: see above)
  python3 v2_chain.py calendar-check LOG [LOG ...]                          exit 2 unless every log carries a calendar line = 1635 / 2016-01-04..2022-06-30
  python3 v2_chain.py restored-count DATA TABLE [COL]                       B8: exit 3 when no row of TABLE sits on a restored ticker
  python3 v2_chain.py gz-equal A B                                          exit 2 unless the two gzip files hold the same bytes
  python3 v2_chain.py pp-parity READ3_HEADLINE READ4_HEADLINE              §3 row 6: exit 2 unless read 4's pp cell = read 3's S2 cell to 1e-9
  python3 v2_chain.py receipt OUT.json                                      the protected-file receipt (paths: the real repo and apollo_data)
  python3 v2_chain.py receipt-compare BEFORE.json AFTER.json                exit 2 on any difference (the manifest's final sha is printed beside)
Opens no price bar. Imports no runner code.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent                               # scripts/probes/_cb_backtest
DATA_ROOT = Path("/Users/alvinfung/apollo_data")
OLD_NAME, V2_NAME = "cb702_pre", "cb702_pre_v2"
SESSIONS_N, SESSIONS_FIRST, SESSIONS_LAST = 1635, "2016-01-04", "2022-06-30"
MANIFEST_NAME = "v2_chain_manifest.tsv"
MANIFEST_COLS = ("label", "path", "sha256", "stage", "time", "prev_sha", "line_sha")
REAL_V2 = DATA_ROOT / V2_NAME                                        # the one data dir the real run may use (test mode refuses it)
TEST_ENV, TEST_FREEZE_ENV = "V2_CHAIN_TEST", "V2_TEST_FREEZE_CMD"
RERUN_SUB, SMALL_SUB = "rerun_v2_1025", "v2_1025"


class ChainRefusal(Exception):
    """A chain check failed: the caller refuses (exit 2) and writes nothing more."""


def sha256_file(p) -> str:
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def gz_content_sha(p) -> str:
    """sha256 of a gzip file's DECOMPRESSED bytes, streamed."""
    import gzip
    h = hashlib.sha256()
    with gzip.open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


# ═══ B8: the restored set ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
def guard_symbols(path) -> frozenset:
    """The `symbol` column of a symbol_guard.tsv (no other column is read)."""
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        if "symbol" not in (rd.fieldnames or ()):
            raise ChainRefusal(f"{path}: no `symbol` column - not a symbol_guard.tsv")
        return frozenset(r["symbol"] for r in rd)


def restored_set(new_guard, old_guard) -> frozenset:
    """B8: the symbols in the rebuilt file's guard and not in the old file's (2,669 on 10-25)."""
    return guard_symbols(new_guard) - guard_symbols(old_guard)


# ═══ B6: the calendar ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def read_sessions(path) -> list:
    return [ln.strip() for ln in Path(path).read_text().splitlines() if ln.strip()]


def calendar_problem(cal_iso: list, sessions: list) -> "str | None":
    """None when the walked calendar equals sessions.txt, else what differs (lengths, the first differing session)."""
    cal_iso = [str(d) for d in cal_iso]
    if cal_iso == list(sessions):
        return None
    first = next((k for k, (a, b) in enumerate(zip(cal_iso, sessions)) if a != b), min(len(cal_iso), len(sessions)))
    return (f"the walked calendar ({len(cal_iso)} sessions {cal_iso[0] if cal_iso else '-'}..{cal_iso[-1] if cal_iso else '-'}) is not sessions.txt "
            f"({len(sessions)} sessions {sessions[0] if sessions else '-'}..{sessions[-1] if sessions else '-'}); first difference at position {first}")


# the four spellings the chain's scripts print (each script's own, unedited): 01_episodes / bdef 02_build; esr_lib / trail_lib Frame;
# 02_build_paths.py; read 2's 02_catch ("export loaded: N sessions a..b"). Each yields (n, first, last).
CAL_PATTERNS = (re.compile(r"calendar (\d+) sessions \((\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})\)"),
                re.compile(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2}) = (\d+) sessions"),
                re.compile(r"calendar = SPY sessions: (\d+) \((\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})\)"),
                re.compile(r"export loaded: (\d+) sessions (\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})"))


def log_calendars(text: str) -> list:
    """Every (n, first, last) calendar line in a log, whichever script's spelling."""
    out = []
    for k, pat in enumerate(CAL_PATTERNS):
        for m in pat.finditer(text):
            g = m.groups()
            out.append((int(g[2]), g[0], g[1]) if k == 1 else (int(g[0]), g[1], g[2]))
    return out


def log_calendar_problems(path, n: int = SESSIONS_N, first: str = SESSIONS_FIRST, last: str = SESSIONS_LAST) -> list:
    """B4 / B6: a log must carry at least one calendar line, and every one it carries must read n sessions first..last."""
    p = Path(path)
    if not p.is_file():
        return [f"{p}: log missing"]
    cals = log_calendars(p.read_text(errors="replace"))
    if not cals:
        return [f"{p}: carries no calendar line"]
    return [f"{p}: calendar {c[0]} sessions ({c[1]}..{c[2]}), not {n} sessions ({first}..{last})" for c in cals if c != (n, first, last)]


# ═══ test mode, the real data dir, the freeze re-check ═══════════════════════════════════════════════════════════════════════════════
def test_mode() -> bool:
    return os.environ.get(TEST_ENV) == "1"


def data_dir_problem(data) -> "str | None":
    """The real run reads the real cb702_pre_v2 only; test mode never does (so a test can never write next to the real chain)."""
    real = Path(data).resolve() == REAL_V2.resolve()
    if test_mode() and real:
        return f"{TEST_ENV}=1 with the REAL data dir {REAL_V2} - test mode never touches the real chain"
    if not test_mode() and not real:
        return f"the data dir {data} is not {REAL_V2} - only {TEST_ENV}=1 (tests) may point the chain elsewhere"
    return None


def freeze_recheck(v2_dir, say=print) -> list:
    """The §8 freeze check, re-run before a stage that the scaffold does not guard (stage 5 = 02_build_paths.py, stage 6 = 04_relaunch.sh,
    stage 7 = v2_compare.py): `runner.py v2-exit-read --dry-run` checks every footer pin (the doc body, the code incl. this module,
    v2_compare.py, 04_relaunch.sh, 02_build_paths.py, the read scripts, the data, the old sources) and opens no bar. [] = passed.
    Test mode: `V2_TEST_FREEZE_CMD` (a shell command; its exit code decides) replaces it - unset refuses."""
    if test_mode():
        cmd = os.environ.get(TEST_FREEZE_ENV)
        if not cmd:
            return [f"{TEST_ENV}=1 but {TEST_FREEZE_ENV} is unset - the freeze re-check has nothing to run"]
        say(f"TEST MODE ({TEST_ENV}=1): the freeze re-check runs {TEST_FREEZE_ENV}={cmd!r} instead of the runner")
        rc = subprocess.run(cmd, shell=True).returncode
        return [] if rc == 0 else [f"the freeze re-check ({TEST_FREEZE_ENV}) exited {rc}"]
    runner = REPO / "scripts" / "probes" / "_cb_backtest" / "runner.py"
    cmd = [sys.executable, str(runner), "v2-exit-read", "--data", str(DATA_ROOT / "cb702"), "--data-pre", str(v2_dir), "--period", "pre", "--dry-run"]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    ok = p.returncode == 0 and "freeze check passed" in p.stdout
    say(f"FREEZE RE-CHECK ({' '.join(cmd[1:])}): {'passed' if ok else f'FAILED (exit {p.returncode})'}")
    if ok:
        return []
    return [f"the freeze re-check failed (exit {p.returncode}): " + (p.stderr.strip() or p.stdout.strip())[-1500:]]


FREEZE_MARK = "<!-- FREEZE -->"                                     # = runner.FREEZE_MARK (asserted in the tests)


def footer_pin_problems(doc, items) -> list:
    """For each (footer label, file): the registration doc's footer (below the freeze marker) carries `<label> sha256: <hex>` - the FIRST such
    line, the runner's `freeze_check` regex - and the file's sha256 now equals it. [] = every pin holds. Used by stage 7 on its own sources
    and its own code, before the full re-check."""
    doc = Path(doc)
    if not doc.is_file():
        return [f"registration doc missing: {doc}"]
    text = doc.read_text(encoding="utf-8")
    if FREEZE_MARK not in text:
        return [f"{doc}: no {FREEZE_MARK} marker"]
    footer = text.split(FREEZE_MARK, 1)[1]
    out = []
    for label, f in items:
        m = re.search(rf"(?m)^\s*[-*]?\s*{re.escape(label)}\s+sha256:\s*`?([0-9a-f]{{64}})", footer)
        if m is None:
            out.append(f"the footer carries no {label} sha256 (not frozen)")
        elif not Path(f).is_file():
            out.append(f"{label}: {f} missing")
        elif sha256_file(f) != m.group(1):
            out.append(f"{label}: {f} sha256 {sha256_file(f)[:12]}... is not the footer's {m.group(1)[:12]}... - edited after the freeze")
    return out


# ═══ the manifest's labels: ONE rule, derived from the path ═════════════════════════════════════════════════════════════════════════
def chain_label(path) -> str:
    """The manifest label of a chain-made file, from its path: `cb702_pre_v2/out/<rel>` (the data dir's out/), `_cb_backtest/out/v2_1025/<rel>`
    (the v2 stages' small dir), `<read dir>/rerun_v2_1025/<rel>` (a read's numbers / report). Anything else raises: the chain makes nothing else."""
    parts = Path(path).parts
    for k in range(len(parts) - 1):
        if parts[k] == V2_NAME and parts[k + 1] == "out" and len(parts) > k + 2:
            return "/".join(parts[k:])
        if parts[k] == "_cb_backtest" and parts[k + 1:k + 3] == ("out", SMALL_SUB) and len(parts) > k + 3:
            return "/".join(parts[k:])
        if parts[k] in READ_DIRS and parts[k + 1] == RERUN_SUB and len(parts) > k + 2:
            return "/".join(parts[k:])
    raise ValueError(f"{path}: not a chain-made path (cb702_pre_v2/out/, _cb_backtest/out/{SMALL_SUB}/ or <read dir>/{RERUN_SUB}/)")


# ═══ B5 / §8: the chain manifest ════════════════════════════════════════════════════════════════════════════════════════════════════
def _line_sha(prev_sha: str, fields: tuple) -> str:
    return hashlib.sha256((prev_sha + "\t" + "\t".join(fields)).encode("utf-8")).hexdigest()


def manifest_rows(path) -> list:
    """The manifest's rows, the hash chain verified: raises ChainRefusal on a malformed, reordered or rewritten line."""
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "\t".join(MANIFEST_COLS):
        raise ChainRefusal(f"{p}: the header is not {MANIFEST_COLS} - the manifest was rewritten")
    rows, prev = [], hashlib.sha256(b"").hexdigest()
    for n, ln in enumerate(lines[1:], 2):
        f = ln.split("\t")
        if len(f) != len(MANIFEST_COLS):
            raise ChainRefusal(f"{p} line {n}: {len(f)} fields, not {len(MANIFEST_COLS)} - the manifest was rewritten")
        r = dict(zip(MANIFEST_COLS, f))
        if r["prev_sha"] != prev or r["line_sha"] != _line_sha(prev, tuple(f[:5])):
            raise ChainRefusal(f"{p} line {n} ({r['label']}): the hash chain breaks - a manifest line was rewritten (the manifest is append-only)")
        rows.append(r)
        prev = r["line_sha"]
    return rows


def manifest_append(path, stage: str, items) -> list:
    """Append one line per (label, file) - the file's sha256 now. The chain is verified first (a broken manifest is never extended), and a label
    already in the manifest (or twice in `items`) refuses: a table is registered ONCE, so a second line can never stand in for a changed table.
    Returns the appended rows."""
    p = Path(path)
    rows = manifest_rows(p)
    items = [(label, Path(f)) for label, f in items]
    have = {r["label"] for r in rows}
    seen = set()
    for label, _f in items:
        if label in have or label in seen:
            raise ChainRefusal(f"{p}: the label {label!r} is already registered - the manifest takes one line per table, written by the stage "
                               f"that made it")
        seen.add(label)
    prev = rows[-1]["line_sha"] if rows else hashlib.sha256(b"").hexdigest()
    new = []
    for label, f in items:
        if "\t" in label or "\n" in label or "\t" in str(f):
            raise ValueError(f"a manifest label / path carries a tab or newline: {label!r} {f}")
        fields = (label, str(f), sha256_file(f), stage, time.strftime("%Y-%m-%dT%H:%M:%S"))
        ls = _line_sha(prev, fields)
        new.append(dict(zip(MANIFEST_COLS, (*fields, prev, ls))))
        prev = ls
    p.parent.mkdir(parents=True, exist_ok=True)
    head = "" if p.exists() else "\t".join(MANIFEST_COLS) + "\n"
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(head + "".join("\t".join(r[c] for c in MANIFEST_COLS) + "\n" for r in new))
    return new


def manifest_problems(path, items) -> list:
    """For each (label, file): its ONE manifest line exists, names the same path, and the file's sha256 now equals it. A broken chain is
    one problem for all; a label with more than one line is a problem (a re-registered table)."""
    try:
        rows = manifest_rows(path)
    except ChainRefusal as exc:
        return [str(exc)]
    last, n_of = {}, {}
    for r in rows:
        last[r["label"]] = r
        n_of[r["label"]] = n_of.get(r["label"], 0) + 1
    out = [f"{lbl}: {n} lines in {path} - a table is registered once; a second line is a re-registration" for lbl, n in sorted(n_of.items()) if n > 1]
    for label, f in items:
        f = Path(f)
        r = last.get(label)
        if r is None:
            out.append(f"{label}: no line in {path} - a table the chain did not make (or made elsewhere) is never read")
        elif Path(r["path"]) != f:
            out.append(f"{label}: the manifest names {r['path']}, not {f}")
        elif not f.is_file():
            out.append(f"{label}: {f} missing")
        elif sha256_file(f) != r["sha256"]:
            out.append(f"{label}: {f.name} sha256 {sha256_file(f)[:12]}... is not the manifest's {r['sha256'][:12]}... (written by {r['stage']}) - the "
                       f"table was changed after the stage that made it")
    return out


# ═══ §3 row 6 / §7 4.0: read 4's `pp` cell equals read 3's S2 cell to 1e-9 ═══════════════════════════════════════════════════════════
PP_TOL = 1e-9
PP_WIN_KEYS = ("n", "still_in_s50", "kept_half", "kept_quarter", "retries_mean", "first_cut", "first_stopped_before_s50")
PP_R1_SCALARS = (("n", "n"), ("r_per_base", "r_trade"), ("ctl_r_per_base", "r_trade_ctl"), ("any5", "any5"), ("ctl_any5", "any5_ctl"))
PP_R1_INTERVALS = (("diff_r_per_base", "diff"), ("diff_any5", "any5_diff"), ("diff_any10", "any10_diff"))


def pp_parity_problems(h3: dict, h4: dict, era: str = "2017-21") -> list:
    """Read 4's `pp` cell (A20_X1_P1 = 20-day / close below / a third at +2R) against read 3's S2 cell, from the two 03_headline.json dicts: the
    two-retry doubler cell (`win_T2` vs `win_S2_T2`) and the no-retry R1 (`R1_T0` vs `all_S2_T0`: the means, the >= 5R rates, the three intervals),
    every value to 1e-9. [] = equal; a missing key is a problem (never skipped)."""
    out = []

    def cmp(what, a, b):
        try:
            if not (abs(float(a) - float(b)) <= PP_TOL):           # written so a NaN on either side is a difference (NaN compares False)
                out.append(f"{what}: read 3 {a} vs read 4 {b}")
        except (TypeError, ValueError):
            out.append(f"{what}: not comparable ({a!r} vs {b!r})")

    try:
        w3, w4 = h3[era]["win_S2_T2"], h4[era]["A20_X1_P1"]["win_T2"]
        a3, a4 = h3[era]["all_S2_T0"], h4[era]["A20_X1_P1"]["R1_T0"]
    except KeyError as exc:
        return [f"a 4.0 source key is missing: {exc}"]
    for k in PP_WIN_KEYS:
        cmp(f"win {k}", w3.get(k), w4.get(k))
    for k3, k4 in PP_R1_SCALARS:
        cmp(f"R1 {k3} / {k4}", a3.get(k3), a4.get(k4))
    for k3, k4 in PP_R1_INTERVALS:
        i3, i4 = a3.get(k3) or {}, a4.get(k4) or {}
        for f in ("diff", "lo", "hi", "n"):
            cmp(f"R1 {k3}.{f} / {k4}.{f}", i3.get(f), i4.get(f))
    return out


# ═══ B5: the protected-file receipt ═════════════════════════════════════════════════════════════════════════════════════════════════
PROTECTED_SMALL = ("p5_report_pre.txt", "p5_report_pre.tsv", "p5_summary_pre.txt", "minute_summary_pre_tl_com.txt", "h60_step0_pre.txt",
                   "h60_report_pre.txt", "h60_hindsight_pre.txt", "h60_report_pre.tsv", "h60_summary_pre.txt", "h60_verdict_pre.txt",
                   "h60_hindsight_pre.tsv", "exitpb_report_pre.txt", "exitpb_report_pre.tsv", "exitpb_deltas_pre.tsv", "exitpb_summary_pre.txt",
                   "exitpb_verdict_pre.txt")                     # the doc's table of printouts under scripts/probes/_cb_backtest/out/
STEP0_PINNED = ("v2_step0_1025/h60_step0_pre.tsv.gz", "v2_step0_1025/h60_step0_pre.txt", "v2_step0_1025/h60_step0_pre_counts.json")
READ_DIRS = ("_702_winner_recall_1022", "_702_breakout_definition_1022", "_702_entry_stop_retry_1022", "_702_trail_variants_1023")


def protected_files(repo: Path = REPO, data_root: Path = DATA_ROOT) -> dict:
    """{label: path} of the §4 protected table: the old printouts under _cb_backtest/out, 02_build_checks_2017-21.txt, every git-tracked
    file in the four read dirs that is not code (their committed numbers / report / log files), and the 10-23 v2 episode tables."""
    files = {f"_cb_backtest/out/{n}": repo / "scripts/probes/_cb_backtest/out" / n for n in PROTECTED_SMALL}
    files["_702_r_decomposition_1022/02_build_checks_2017-21.txt"] = repo / "scripts/probes/_702_r_decomposition_1022/02_build_checks_2017-21.txt"
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files", *[f"scripts/probes/{d}" for d in READ_DIRS]], capture_output=True, text=True,
                             check=True).stdout.split()
    for rel in tracked:
        if not rel.endswith((".py", ".sh")):
            files[rel] = repo / rel
    wr = data_root / V2_NAME / "out" / "rerun_1023" / "winner_recall"
    for p in sorted(wr.glob("*")) if wr.is_dir() else ():
        files[f"{V2_NAME}/out/rerun_1023/winner_recall/{p.name}"] = p
    for name in STEP0_PINNED:                       # stage 0's pinned copies (§8): stage 2 must never touch them - take the BEFORE receipt after stage 0
        files[f"{V2_NAME}/out/{name}"] = data_root / V2_NAME / "out" / name
    files["_cb_backtest/out/v2_1025/step0/h60_step0_pre.txt"] = repo / "scripts/probes/_cb_backtest/out/v2_1025/step0/h60_step0_pre.txt"
    return files


def receipt(repo: Path = REPO, data_root: Path = DATA_ROOT) -> dict:
    """sha256 of every protected file and of every file under cb702_pre/ (None = missing), plus the manifest's sha256 if it exists."""
    rec = {"protected": {}, "cb702_pre": {}, "manifest": None, "taken": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for label, p in protected_files(repo, data_root).items():
        rec["protected"][label] = sha256_file(p) if Path(p).is_file() else None
    old = data_root / OLD_NAME
    for p in sorted(old.rglob("*")):
        if p.is_file():
            rec["cb702_pre"][p.relative_to(old).as_posix()] = sha256_file(p)
    m = data_root / V2_NAME / "out" / MANIFEST_NAME
    rec["manifest"] = sha256_file(m) if m.is_file() else None
    return rec


def receipt_problems(before: dict, after: dict) -> list:
    out = []
    for part in ("protected", "cb702_pre"):
        a, b = before.get(part, {}), after.get(part, {})
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                out.append(f"{part}: {k}: {'(absent)' if k not in a else (a[k] or 'MISSING')[:12]} -> {'(absent)' if k not in b else (b[k] or 'MISSING')[:12]}")
    return out


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a:
        print(__doc__)
        return 2
    cmd, rest = a[0], a[1:]
    try:
        if cmd == "manifest-check":
            man, pairs = rest[0], list(zip(rest[1::2], rest[2::2]))
            pr = manifest_problems(man, pairs)
            for p in pr:
                print(f"REFUSED: {p}", file=sys.stderr)
            if not pr:
                print(f"MANIFEST OK: {', '.join(lbl for lbl, _f in pairs)} equal their last lines in {man}")
            return 2 if pr else 0
        if cmd == "manifest-add":
            man, stage, pairs = rest[0], rest[1], list(zip(rest[2::2], rest[3::2]))
            for r in manifest_append(man, stage, pairs):
                print(f"MANIFEST + {r['label']} {r['sha256'][:12]}... ({stage})")
            return 0
        if cmd == "manifest-check-paths":
            man, files = rest[0], rest[1:]
            pr = manifest_problems(man, [(chain_label(f), f) for f in files])
            for p in pr:
                print(f"REFUSED: {p}", file=sys.stderr)
            if not pr:
                print(f"MANIFEST OK: {len(files)} file(s) equal their lines in {man}")
            return 2 if pr else 0
        if cmd == "manifest-add-paths":
            man, stage, files = rest[0], rest[1], rest[2:]
            for r in manifest_append(man, stage, [(chain_label(f), f) for f in files]):
                print(f"MANIFEST + {r['label']} {r['sha256'][:12]}... ({stage})")
            return 0
        if cmd == "freeze-recheck":
            pr = freeze_recheck(rest[0])
            for p in pr:
                print(f"REFUSED: {p}", file=sys.stderr)
            return 2 if pr else 0
        if cmd == "calendar-check":
            pr = [p for f in rest for p in log_calendar_problems(f)]
            for p in pr:
                print(f"REFUSED: {p}", file=sys.stderr)
            if not pr:
                print(f"CALENDAR OK: {len(rest)} log(s) read {SESSIONS_N} sessions ({SESSIONS_FIRST}..{SESSIONS_LAST})")
            return 2 if pr else 0
        if cmd == "restored-count":                 # B8: rows of a table on restored tickers (DATA/symbol_guard.tsv minus the sibling old guard)
            data, table, col = Path(rest[0]), Path(rest[1]), (rest[2] if len(rest) > 2 else "ticker")
            rs = restored_set(data / "symbol_guard.tsv", data.parent / OLD_NAME / "symbol_guard.tsv")
            n = tot = 0
            opener = __import__("gzip").open if table.name.endswith(".gz") else open
            with opener(table, "rt", newline="") as fh:
                for r in csv.DictReader(fh, delimiter="\t"):
                    tot += 1
                    n += r[col] in rs
            print(f"B8 RESTORED: {n:,} of {tot:,} rows of {table.name} sit on restored tickers ({len(rs):,} restored symbols)")
            if n == 0:
                print(f"REFUSED (B8): 0 rows of {table} on restored tickers - the restored names were dropped", file=sys.stderr)
                return 3
            return 0
        if cmd == "gz-equal":                       # decompressed bytes (a gzip header carries a clock)
            a_, b_ = (gz_content_sha(x) for x in rest[:2])
            print(f"{'EQUAL' if a_ == b_ else 'DIFFER'}: {rest[0]} vs {rest[1]} (decompressed)")
            return 0 if a_ == b_ else 2
        if cmd == "pp-parity":                      # §3 row 6: read 4's pp cell = read 3's S2 cell to 1e-9 (else the chain stops)
            pr = pp_parity_problems(json.loads(Path(rest[0]).read_text()), json.loads(Path(rest[1]).read_text()))
            for p in pr:
                print(f"REFUSED (4.0): {p}", file=sys.stderr)
            print(f"PP PARITY {'FAILED' if pr else 'OK'}: read 4's A20_X1_P1 vs read 3's S2 ({len(PP_WIN_KEYS)} win values, "
                  f"{len(PP_R1_SCALARS) + 4 * len(PP_R1_INTERVALS)} R1 values, to {PP_TOL:g})")
            return 2 if pr else 0
        if cmd == "receipt":
            rec = receipt()
            Path(rest[0]).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
            print(f"RECEIPT: {len(rec['protected'])} protected files, {len(rec['cb702_pre'])} files under cb702_pre/, manifest "
                  f"{(rec['manifest'] or 'absent')[:12]} -> {rest[0]}")
            return 0
        if cmd == "receipt-compare":
            b, c = (json.loads(Path(x).read_text()) for x in rest[:2])
            pr = receipt_problems(b, c)
            for p in pr:
                print(f"RECEIPT DIFFERS: {p}", file=sys.stderr)
            print(f"RECEIPT {'BROKEN - the run is reported as broken, not read' if pr else 'OK'}: {len(c['protected'])} protected files and "
                  f"{len(c['cb702_pre'])} cb702_pre files compared; manifest final sha256 {c.get('manifest')}")
            return 2 if pr else 0
    except (ChainRefusal, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"unknown command {cmd!r}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
