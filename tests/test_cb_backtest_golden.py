"""Golden-bytes harness for the #702 Consolidation Breakout backtest runner (#705 (a), 2026-10-24).

Every finished stage of `scripts/probes/_cb_backtest/runner.py` is run on SYNTHETIC data and the EXACT bytes it leaves behind are
pinned: the stdout, the stderr and the exit code of every invocation, and the content of every file it writes (a gzip table by its
DECOMPRESSED content - the gzip header carries a timestamp) or DELETES (`<DELETED>`). A refactor of the runner is byte-neutral when
this file is green, and the harness fails on a ONE-BYTE change (`test_the_harness_catches_a_one_byte_change` proves it on the real
pipeline).

Covered: `daily` (the registered four levels, `--step0`, `--keys com,comb --no-close-variant`, the pre-2022 era options), `minute`
(with and without the CLOSE variant / the Apollo control, `--keys com,comb`), `step0-entries`, `report`, `exits` / `exits-report`, `p5`,
and EVERY path of the four finished registered reads - `holdout`, `pre-read`, `h60-step0` / `h60-read` / `h60-hindsight`, `exit-read`:
`--print-pins`, `--dry-run`, each option refusal, no `--period`, the freeze mismatch, `--parity-only` on a mismatched footer (it skips
the freeze by design), the once-only and `.partial` refusals, the missing-pair refusals, the empty population, the module pin, the
STEP 0 refusal, every exit-3 path (the h60 twin, the exit read's parity and implementation checks, the pre-read's P5 cross-check), and
the full synthetic run of each (the real runs happened once, on real data, and are not reproduced here).

The pins: tests/fixtures/cb_backtest_golden/<scenario>.golden - one record per artefact: a header line carrying the BINDING sha256
and byte count, then the artefact's normalised text when it is text and at most TEXT_CAP bytes, so a legitimate change shows as a
readable git diff and a failure prints a unified diff; PINNED_ON.json records the platform.

Normalised before hashing - the only tokens that differ between two runs of the SAME code on the same platform, nothing else:
  <TMP>              every spelling of the test's temporary directory and of the repo root (the stages print the paths they read and write)
  <N>s               a wall-time token: `[load: 3s]`, `WALL TIME: 12s total`, `(45s)`, `load=3s`, `[... 7s]`
  <SHA:relpath>      the sha256 of a file under the test's root AS IT IS after the step, by its relative path - so `--print-pins` and
                     the freeze refusals pin WHICH file each label hashes (a gzip's raw sha differs per run; the label does not;
                     files of the same content - a gzip by what it holds - share one `a|b` label, so a gzip header's clock cannot move it);
                     `<SHA:runner>` / `<SHA:scaffold>` / `<SHA:cb_module>` are the runner's, the scaffold's and the module's own files
  <SHA12:relpath>... the 12-hex prefix + `...` of such a sha, as the freeze refusals and the twin check print it
  <SHA64> / <SHA12>  any other 64-hex sha256 / 12-hex prefix + `...` (a doc-body sha, a sha of a file the step no longer has)
  <DATE>             `written YYYY-MM-DD` in the verdict files
`test_the_normaliser_touches_only_the_volatile_tokens` pins the normaliser itself.

RE-PIN ONLY FOR AN INTENDED OUTPUT CHANGE, in its own reviewed commit (the diff of the bundles is the review):
    CB_GOLDEN_UPDATE=1 python3 -m pytest tests/test_cb_backtest_golden.py -q
PINNED_ON.json records the platform the bundles were written on. On a platform that differs in system / machine / numpy / pandas
(major.minor) the scenario tests still run, but a difference is reported as XFAIL naming the platform gap instead of a failure (a float
out of a numpy reduction is expected to be bit-identical across platforms, but a last-digit difference on another BLAS must not red
the platform the reads actually run on); the self-tests below compare a run against ITSELF and hold everywhere.
"""
from __future__ import annotations

import difflib
import gzip
import hashlib
import json
import os
import platform
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from scripts.probes._cb_backtest import registered_read as rr
from scripts.probes._cb_backtest import runner as rn

try:                                                         # the synthetic builders of the runner's own test file (pytest's module name)
    import test_cb_backtest_runner as T
except ImportError:                                          # pragma: no cover - the repo-root spelling
    from tests import test_cb_backtest_runner as T

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cb_backtest_golden"
TEXT_CAP = 64_000                                            # a text artefact up to this size keeps its diffable text in the bundle
UPDATE = os.environ.get("CB_GOLDEN_UPDATE") == "1"
TEXT_SUFFIXES = (".txt", ".tsv", ".json", ".psv", ".md", ".csv", ".log")
REAL_REPO = str(Path(rn.__file__).resolve().parents[3])
DELETED = b"<DELETED>"                                       # the artefact of a file the step removed


# ═══ the normaliser ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def normalise(text: str, roots: tuple = (), shas: "dict | None" = None) -> str:
    """`shas` = {sha256 hex: label}: a sha the step's files account for is replaced by its LABEL (`<SHA:label>`, `<SHA12:label>...`), so
    which file a printed sha belongs to is pinned; every other sha falls back to `<SHA64>` / `<SHA12>...`."""
    for r in roots:
        if r:
            text = text.replace(r, "<TMP>")
    for h, label in (shas or {}).items():
        text = text.replace(h, f"<SHA:{label}>").replace(h[:12] + "...", f"<SHA12:{label}>...")
    text = re.sub(r"[0-9a-f]{64}", "<SHA64>", text)
    text = re.sub(r"[0-9a-f]{12}\.\.\.", "<SHA12>...", text)
    text = re.sub(r"(?<=[\[(:= ])\d+s(?=[\])]|\s|$)", "<N>s", text)
    text = re.sub(r"written \d{4}-\d{2}-\d{2}", "written <DATE>", text)
    return text


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def is_text_name(name: str) -> bool:
    base = name[:-3] if name.endswith(".gz") else name
    return base.endswith(TEXT_SUFFIXES) or name in ("stdout", "stderr", "exit")


def gz_content(name: str, raw: bytes) -> bytes:
    """A `.gz` file by its decompressed content; a stub that merely wears the name (`write_text(name)`) as is."""
    if name.endswith(".gz"):
        try:
            return gzip.decompress(raw)
        except (OSError, EOFError):
            return raw
    return raw


def artefact_bytes(name: str, raw: bytes, roots: tuple, shas: "dict | None" = None) -> bytes:
    """The bytes that are pinned: a gzip file by its content; a text artefact normalised; anything else as is."""
    raw = gz_content(name, raw)
    if is_text_name(name):
        try:
            return normalise(raw.decode("utf-8"), roots, shas).encode("utf-8")
        except UnicodeDecodeError:
            return raw
    return raw


# ═══ capture: run a stage, keep what it printed and what it wrote ═════════════════════════════════════════════════════════════════
def _snapshot(root: Path) -> dict:
    """{relative path: (raw sha256, CONTENT sha256)} of every file under `root`. Change detection uses the content sha: `write_tsv(gz=True)`
    stamps the gzip header with the wall clock, so a table rewritten with identical rows is byte-identical only inside the same second -
    hashing the raw bytes made 'this step rewrote the table' depend on timing. The raw sha is what `--print-pins` and the freeze print."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            raw = p.read_bytes()
            out[p.relative_to(root).as_posix()] = (sha256(raw), sha256(gz_content(p.name, raw)))
    return out


def sha_labels(after: dict) -> dict:
    """{raw sha256: label} for the normaliser: every file under the root by its relative path, plus the runner's, the scaffold's and the
    module's own files. Files with the SAME CONTENT share one `a|b` label (in path order) whatever their raw bytes: a gzip carries the wall
    clock in its header, so two tables written with identical rows hold the same raw bytes only when they were written in the same second -
    grouping by the raw sha made the label depend on the clock (`cb702/x` in one run, `b/cb702/x|cb702/x` in the next). A gzip is grouped
    by its decompressed content, any other file by its bytes, and the two never mix."""
    groups: dict = {}
    for rel, (raw, content) in after.items():
        groups.setdefault((raw != content, content), []).append(rel)               # raw != content: a real gzip, grouped by what it holds
    shas: dict = {}
    for rel, (raw, content) in after.items():
        shas[raw] = "|".join(sorted(groups[(raw != content, content)]))
    for label, mod in (("runner", rn), ("scaffold", rr), ("cb_module", cb)):
        shas[rn.sha256_file(Path(mod.__file__))] = label
    return shas


class Capture:
    """`run(step, argv)` calls `rn.main(argv)` and records `<step>/stdout`, `<step>/stderr`, `<step>/exit` and `<step>/<relative path>`
    for every file under `root` that the call created, changed (by content) or deleted (`<DELETED>`); the test's own stubs, written between
    runs, are never artefacts."""

    def __init__(self, root: Path, capsys):
        self.root, self.capsys = root, capsys
        self.roots = tuple(dict.fromkeys([str(root), str(root.resolve()), REAL_REPO, str(Path(REAL_REPO).resolve())]))
        self.arts: dict = {}

    def run(self, step: str, argv: list) -> int:
        before = _snapshot(self.root)
        self.capsys.readouterr()
        rc = 0
        try:
            r = rn.main(argv)
            rc = int(r or 0)
        except SystemExit as ex:
            rc = int(ex.code or 0)
        cap = self.capsys.readouterr()
        after = _snapshot(self.root)
        shas = sha_labels(after)
        assert step not in {k.split("/", 1)[0] for k in self.arts}, f"step {step!r} used twice"
        self.arts[f"{step}/stdout"] = artefact_bytes("stdout", cap.out.encode(), self.roots, shas)
        self.arts[f"{step}/stderr"] = artefact_bytes("stderr", cap.err.encode(), self.roots, shas)
        self.arts[f"{step}/exit"] = str(rc).encode()
        for rel, (_raw, content) in after.items():
            if before.get(rel, (None, None))[1] != content:
                self.arts[f"{step}/{rel}"] = artefact_bytes(Path(rel).name, (self.root / rel).read_bytes(), self.roots, shas)
        for rel in before.keys() - after.keys():
            self.arts[f"{step}/{rel}"] = DELETED
        return rc


# ═══ the pins: one bundle per scenario ═══════════════════════════════════════════════════════════════════════════════════════════
# `<scenario>.golden` holds one record per artefact: a header line (BINDING: the key, the byte count and the sha256 of the pinned bytes)
# followed by the artefact's normalised text when it is text and at most TEXT_CAP bytes (the diff aid), else nothing. PINNED_ON.json
# records the platform the bundles were written on.
HEAD = "==== GOLDEN ARTEFACT "
PINNED_ON = GOLDEN / "PINNED_ON.json"


def pinned_on() -> dict:
    return {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
            "numpy": np.__version__, "pandas": pd.__version__}


def _major_minor(v) -> str:
    return ".".join(str(v).split(".")[:2])


def platform_gap() -> "str | None":
    """How this platform differs from the one the bundles were pinned on (system, machine, numpy / pandas major.minor), or None."""
    if not PINNED_ON.exists():
        return None
    on, now = json.loads(PINNED_ON.read_text()), pinned_on()
    gaps = [f"{k} {on.get(k)} -> {now[k]}" for k in ("system", "machine") if on.get(k) != now[k]]
    gaps += [f"{k} {on.get(k)} -> {now[k]}" for k in ("numpy", "pandas") if _major_minor(on.get(k)) != _major_minor(now[k])]
    return "; ".join(gaps) or None


def bundle_path(scenario: str) -> Path:
    return GOLDEN / f"{scenario}.golden"


def _stored(k: str, data: bytes) -> bool:
    return is_text_name(Path(k).name) and len(data) <= TEXT_CAP


def write_bundle(scenario: str, arts: dict) -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    parts = []
    for k in sorted(arts):
        data = arts[k]
        stored = _stored(k, data)
        parts.append(f"{HEAD}{k} | bytes={len(data)} | sha256={sha256(data)} | {'text' if stored else 'content not stored'}\n")
        if stored:
            parts.append(data.decode("utf-8") + "\n")
    bundle_path(scenario).write_text("".join(parts), encoding="utf-8")
    PINNED_ON.write_text(json.dumps(pinned_on(), indent=1) + "\n")


def read_bundle(scenario: str) -> dict:
    """{key: {"bytes": n, "sha256": hex, "text": str | None}} from the scenario's bundle (empty when there is none)."""
    p = bundle_path(scenario)
    if not p.exists():
        return {}
    pins = {}
    raw = p.read_text(encoding="utf-8")
    for rec in raw.split(HEAD)[1:]:
        header, _, body = rec.partition("\n")
        key, nbytes, sha, kind = (x.strip() for x in header.split(" | "))
        text = body[:-1] if kind == "text" else None               # the newline write_bundle appended after the content
        pins[key] = {"bytes": int(nbytes[len("bytes="):]), "sha256": sha[len("sha256="):], "text": text}
    return pins


def pins_of(arts: dict) -> dict:
    """The pins a capture WOULD write - what `read_bundle` returns for it - so the self-tests can compare a run against itself on any
    platform, never against the bundle."""
    return {k: {"bytes": len(d), "sha256": sha256(d), "text": d.decode("utf-8") if _stored(k, d) else None} for k, d in arts.items()}


def compare_pins(pins: dict, arts: dict, actual_dir: "Path | None" = None) -> list:
    """Problems (empty = every artefact equals its pin and nothing pinned is missing)."""
    problems = []
    for k, data in arts.items():
        exp = pins.get(k)
        h = sha256(data)
        if exp is None:
            problems.append(f"{k}: NOT PINNED (a new artefact; re-pin on purpose)")
            continue
        if exp["sha256"] == h:
            continue
        msg = f"{k}: sha256 {h[:12]} != pinned {exp['sha256'][:12]} ({len(data):,} vs {exp['bytes']:,} bytes)"
        if exp["text"] is not None:
            diff = list(difflib.unified_diff(exp["text"].splitlines(), data.decode("utf-8", "replace").splitlines(), "pinned", "now", lineterm="", n=1))
            msg += "\n    " + "\n    ".join(diff[:40]) + ("\n    ..." if len(diff) > 40 else "")
        if actual_dir is not None:
            p = actual_dir / k.replace("/", "__")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            msg += f"\n    (actual written to {p})"
        problems.append(msg)
    for k in pins:
        if k not in arts:
            problems.append(f"{k}: pinned but NOT PRODUCED this run")
    return problems


def compare(scenario: str, arts: dict, actual_dir: "Path | None" = None, *, update: bool = UPDATE) -> list:
    """The scenario's artefacts against its bundle. With CB_GOLDEN_UPDATE=1 the bundle is rewritten instead and the list is empty - only
    from the scenario tests: the self-tests compare a deliberately mutated run against a clean one through `compare_pins`, so a re-pin
    run can never write a mutated bundle."""
    if update:
        write_bundle(scenario, arts)
        return []
    return compare_pins(read_bundle(scenario), arts, actual_dir)


def check(scenario: str, cap: Capture, tmp_path: Path) -> None:
    problems = compare(scenario, cap.arts, tmp_path / "golden_actual")
    if not problems:
        return
    on = json.loads(PINNED_ON.read_text()) if PINNED_ON.exists() else None
    msg = (f"{len(problems)} golden artefact(s) of scenario {scenario!r} differ (pinned on {on}; this run: {pinned_on()}):\n" + "\n".join(problems))
    gap = platform_gap()
    if gap:
        pytest.xfail(f"a platform the bundles were not pinned on ({gap}) - re-pin on the pinned platform before trusting this: {msg}")
    assert not problems, msg


# ═══ the scenarios ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def scenario_daily(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The daily stage on the MRNA fixture bars (+ a WICK twin, flat SPY / QQQ): the registered four levels, the STEP 0 print, the
    com / comb run with no outcome."""
    data = T.TestTrendlineK()._daily_dir(tmp_path, with_done=True)
    small = tmp_path / "small"
    base = ["daily", "--data", str(data), "--workers", "1", "--small-out", str(small)]
    cap.run("daily", base)
    cap.run("daily_step0", base + ["--step0"])
    cap.run("daily_com_comb", base + ["--keys", "com,comb", "--no-close-variant"])
    cap.run("daily_com_comb_step0", base + ["--keys", "com,comb", "--step0"])


def scenario_daily_era(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The daily stage's pre-2022 Alpaca-era path (`--era-label` / `--watch-start` / `--watch-end` / `--raw-close` / `--breaks`) on the
    tiny era export: random walks pass no watch gate, so what is pinned is the funnel, the identity guard and the era stamp."""
    data = tmp_path / "era"
    data.mkdir(parents=True)
    days = T._era_export(data)
    brk = data / "symbol_guard.tsv"
    brk.write_text(f"symbol\tbreaks\nBBB\t{days[250].isoformat()}:jump\n")
    cap.run("daily_era", ["daily", "--data", str(data), "--workers", "1", "--out", str(data / "out"), "--small-out", str(tmp_path / "small"),
                          "--keys", "tl", "--no-close-variant", "--raw-close", str(data / "daily_raw_close.csv.gz"), "--breaks", str(brk),
                          "--watch-start", days[140].isoformat(), "--watch-end", days[280].isoformat(), "--era-label", "pre"])


def scenario_minute_report(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The discovery minute engine on four candidates (k5 / k10 / full / tl) with the daily CLOSE rows joined, the discovery report,
    then the engine without the CLOSE variant and the Apollo control."""
    data, bars, e, cands = T._syn_dir(tmp_path, n_cands=4)
    T._close_file(data, bars, e, cands)
    small = tmp_path / "small"
    cap.run("minute", ["minute", "--data", str(data), "--workers", "1", "--small-out", str(small)])
    cap.run("report", ["report", "--data", str(data), "--small-out", str(small)])
    cap.run("minute_no_close_no_apollo", ["minute", "--data", str(data), "--workers", "1", "--small-out", str(small), "--no-close", "--no-apollo"])


def scenario_step0_entries(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    data, bars, e, cands = T._syn_dir(tmp_path, split="holdout", n_cands=4)
    cap.run("step0_entries", ["step0-entries", "--data", str(data), "--workers", "1", "--small-out", str(tmp_path / "small")])


def scenario_p5(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The P5 stage on a staller (tl from candidates.tsv, com / comb from candidates_com_comb.tsv) after the two minute runs it
    cross-checks against, then the report on the tl table."""
    data, bars, e = T._p5_dir(tmp_path, staller=True)
    small = tmp_path / "small"
    cap.run("minute_tl", ["minute", "--data", str(data), "--workers", "1", "--small-out", str(small), "--no-close", "--no-apollo"])
    cap.run("minute_com_comb", ["minute", "--data", str(data), "--workers", "1", "--small-out", str(small), "--no-close", "--no-apollo", "--keys", "com,comb"])
    cap.run("p5", ["p5", "--data", str(data), "--workers", "1", "--small-out", str(small)])
    cap.run("report_tl", ["report", "--data", str(data), "--small-out", str(small)])
    cap.run("report_com_comb", ["report", "--data", str(data), "--small-out", str(small), "--keys", "com,comb"])


def scenario_exits(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    data, bars, e, cs = T.TestHisExitStage()._data(tmp_path, ("k5", "tl"))
    small = tmp_path / "small"
    cap.run("exits", ["exits", "--data", str(data), "--levels", "tl", "--workers", "1", "--small-out", str(small)])
    cap.run("exits_report", ["exits-report", "--data", str(data), "--levels", "tl", "--small-out", str(small)])


def scenario_holdout(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The holdout read on a synthetic holdout tree with a matching registration doc: the pins, both dry runs, every refusal, then the
    one synthetic run (the minute engine and the P5 pass)."""
    data, bars, e = T._p5_dir(tmp_path, split="holdout")
    (data / "cb702_sic.psv").write_text("sic\n")
    for name in ("watch.tsv.gz", "minute_fetch_list.tsv", "gap_in_bars.tsv", "close_variant_discovery.tsv.gz", "trades_discovery.tsv.gz",
                 "entries_discovery.tsv.gz", "entries_holdout_composition.tsv", "discovery_report.tsv", "watch_com_comb.tsv.gz",
                 "entries_holdout_composition_com_comb.tsv", "trades_discovery_p5.tsv.gz", "p5_report_discovery.tsv"):
        (data / "out" / name).write_text(name)
    repo = tmp_path / "repo"
    (repo / "docs" / "analysis").mkdir(parents=True)
    (repo / rn.MODULE_REL).parent.mkdir(parents=True, exist_ok=True)
    (repo / rn.MODULE_REL).write_text("# module\n")
    for rel in rn.FROZEN_CODE.values():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"# {rel}\n")
    monkeypatch.setattr(rn, "REPO", repo)
    monkeypatch.setattr(rn, "HERE", tmp_path / "hereroot")
    (rn.HERE / "out").mkdir(parents=True)
    (rn.HERE / "out" / "discovery_report.txt").write_text("report")
    (rn.HERE / "out" / "p5_report_discovery.txt").write_text("p5 report")
    T.TestHoldoutGuard()._doc(repo, data)
    base = ["holdout", "--data", str(data), "--workers", "1"]
    cap.run("print_pins", base + ["--print-pins"])
    cap.run("dry_run", base + ["--dry-run"])
    cap.run("dry_run_no_freeze_check", base + ["--dry-run", "--no-freeze-check"])
    cap.run("refuse_out", base + ["--out", str(tmp_path / "elsewhere")])
    cap.run("refuse_small_out", base + ["--small-out", str(tmp_path / "elsewhere")])
    cap.run("refuse_no_freeze_check", base + ["--no-freeze-check"])
    cap.run("refuse_limit_dates", base + ["--limit-dates", "3"])
    cap.run("refuse_no_close", base + ["--no-close"])
    cap.run("refuse_no_apollo", base + ["--no-apollo"])
    cap.run("refuse_keys", base + ["--keys", "com"])
    cap.run("refuse_levels", base + ["--levels", "tl"])
    sic = data / "cb702_sic.psv"
    sic.write_text("edited")
    cap.run("refuse_freeze_mismatch", base)
    sic.write_text("sic\n")
    (data / "out" / "trades_holdout.tsv.gz").write_bytes(b"")
    cap.run("refuse_once_only", base)
    (data / "out" / "trades_holdout.tsv.gz").unlink()
    (data / "out" / "trades_holdout_p5.tsv.gz.partial").write_bytes(b"half")
    cap.run("refuse_partial", base)
    (data / "out" / "trades_holdout_p5.tsv.gz.partial").unlink()
    cap.run("holdout_full", base)
    cap.run("refuse_after_the_run", base)


def scenario_pre_read(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The pre-read on a synthetic 2019 staller: the dry run, the refusals, the missing-pair refusal on a second tree, the one synthetic
    run, the once-only and `.partial` refusals; an empty population on a third tree; the P5 cross-check failing (exit 3) on a fourth."""
    data, bars, e = T._pre_dir(tmp_path / "ok", staller=True)
    small = tmp_path / "ok" / "small"
    base = ["pre-read", "--data", str(data), "--workers", "1", "--small-out", str(small)]
    cap.run("dry_run", base + ["--dry-run"])
    cap.run("refuse_keys", base + ["--keys", "tl"])
    cap.run("refuse_out", base + ["--out", str(tmp_path / "elsewhere")])
    cap.run("refuse_no_apollo", base + ["--no-apollo"])
    short, _b, _e = T._pre_dir(tmp_path / "short", minutes="short")
    sbase = ["pre-read", "--data", str(short), "--workers", "1", "--small-out", str(tmp_path / "short" / "small")]
    cap.run("refuse_missing_pairs", sbase)
    cap.run("dry_run_missing_pairs", sbase + ["--dry-run"])
    cap.run("pre_read", base)
    cap.run("refuse_once_only", base)
    for q in rn.pre_existing_outputs(data / "out"):
        q.unlink()
    (data / "out" / "trades_pre_tl_com.tsv.gz.partial").write_bytes(b"half")
    cap.run("refuse_partial", base)
    (data / "out" / "trades_pre_tl_com.tsv.gz.partial").unlink()
    # an empty population: the era file holds a retrigger row only (no first break of tl / com)
    empty, ebars, ee = T._pre_dir(tmp_path / "empty")
    retrig = T._p5_cand(ebars, ee, K="tl", split="pre", retrigger=1)
    rn.write_tsv(empty / "out" / "candidates_tl_com.tsv", [retrig], list(retrig.keys()))
    ebase = ["pre-read", "--data", str(empty), "--workers", "1", "--small-out", str(tmp_path / "empty" / "small")]
    cap.run("dry_run_empty", ebase + ["--dry-run"])
    cap.run("refuse_empty", ebase)
    # the P5 cross-check failing: exit 3, the report says DO NOT READ
    xc, _b, _e = T._pre_dir(tmp_path / "xc")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rn, "p5_crosscheck", lambda *a, **k: (2, ["1 of 2 paired rows differ in realized_r"]))
        cap.run("crosscheck_failed", ["pre-read", "--data", str(xc), "--workers", "1", "--small-out", str(tmp_path / "xc" / "small")])


def _tamper_pinned(path: Path, arm: str) -> bytes:
    """Add 0.5R to the pinned table's rows of `arm` (as the runner tests do); returns the original bytes to restore."""
    before = path.read_bytes()
    t = T.pd_read(path)
    t.loc[t.arm == arm, "realized_r"] += 0.5
    t.to_csv(path, sep="\t", index=False, na_rep="", compression="gzip")
    return before


def scenario_h60(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The hourly-close read on the synthetic cb702 + cb702_pre tree with a matching registration doc: the pins, the dry runs, every
    refusal, the freeze mismatch, the missing-pair refusals of STEP 0 and the read, STEP 0, the STEP 0 refusal (a registered count off the
    table), the twin failing (exit 3), the one synthetic run, the once-only / `.partial` refusals, the hindsight tables."""
    tree = T._h60_tree(tmp_path, monkeypatch)
    doc = T._h60_doc(tree)
    base = ["--data", str(tree["cb702"]), "--data-pre", str(tree["cb702_pre"]), "--workers", "1"]
    P = base + ["--period", "discovery"]
    cap.run("print_pins", ["h60-read", *base, "--print-pins"])
    cap.run("refuse_no_period", ["h60-read", *base])
    cap.run("dry_run", ["h60-read", *P, "--dry-run"])
    cap.run("dry_run_prereg", ["h60-read", *P, "--dry-run", "--prereg", str(doc)])
    cap.run("refuse_prereg", ["h60-read", *P, "--prereg", str(doc)])
    cap.run("refuse_keys", ["h60-read", *P, "--keys", "com"])
    cap.run("refuse_out", ["h60-read", *P, "--out", str(tmp_path / "elsewhere")])
    cap.run("refuse_small_out", ["h60-read", *P, "--small-out", str(tmp_path / "elsewhere")])
    cap.run("refuse_minutes", ["h60-read", *P, "--minutes", str(tree["cb702"] / "minutes")])
    cap.run("refuse_no_freeze_check", ["h60-read", *P, "--no-freeze-check"])
    p = tree["cb702"] / "out" / "candidates.tsv"
    before = p.read_bytes()
    p.write_bytes(before + b"\n")
    cap.run("refuse_freeze_mismatch", ["h60-read", *P])
    p.write_bytes(before)
    # a missing pair: the E2 pair dropped from the log; the doc re-pinned to that tree (the freeze would refuse the read first otherwise)
    done = tree["cb702"] / "minutes" / "_done.psv"
    logged = done.read_text()
    done.write_text(f"{tree['c1']['E']}|X|390|ok\n")
    T._h60_doc(tree)
    cap.run("refuse_missing_pairs_step0", ["h60-step0", *P])
    cap.run("refuse_missing_pairs", ["h60-read", *P])
    done.write_text(logged)
    T._h60_doc(tree)
    cap.run("refuse_hindsight_before_verdict", ["h60-hindsight", *P])
    cap.run("step0", ["h60-step0", *P])
    with pytest.MonkeyPatch.context() as mp:                   # a registered count off the table: refused before any exit
        mp.setitem(rn.H60_EXPECTED["discovery"], "C1", 5)
        cap.run("refuse_step0_differs", ["h60-read", *P])
    out = tree["cb702"] / "out"
    pinned = out / "trades_discovery_p5.tsv.gz"                # the twin re-walk differs from a tampered pinned table: exit 3, no report
    original = _tamper_pinned(pinned, rn.H60_ARM)
    T._h60_doc(tree)
    cap.run("twin_failed", ["h60-read", *P])
    for q in rn.h60_existing_outputs(out, "discovery"):
        q.unlink()
    pinned.write_bytes(original)
    T._h60_doc(tree)
    cap.run("h60_read", ["h60-read", *P])
    cap.run("refuse_once_only", ["h60-read", *P])
    cap.run("hindsight", ["h60-hindsight", *P])
    for q in rn.h60_existing_outputs(out, "discovery"):
        q.unlink()
    (out / "trades_discovery_h60.tsv.gz.partial").write_bytes(b"half")
    cap.run("refuse_partial", ["h60-read", *P])
    (out / "trades_discovery_h60.tsv.gz.partial").unlink()


def _xp_doc(tree: dict) -> None:
    """Re-pin the exit registration doc's footer to the tree as it is now (the body above the mark is kept)."""
    doc = tree["doc"]
    body = doc.read_text().split(rn.FREEZE_MARK)[0]
    doc.write_text(body + rn.FREEZE_MARK + "\n## Freeze record\n"
                   + "\n".join(rn.pin_lines(tree["cb702"], tree["repo"], files=rn.exitpb_frozen_files(tree, tree["repo"]))
                               + [f"- doc body sha256: `{rn.doc_body_sha(body)}`"]) + "\n")


def scenario_exit_read(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The exit read on the h60 tree after its hourly-close run: the pins, the dry run, every refusal, no `--period`, parity only on a
    MISMATCHED footer (it skips the freeze by design), the freeze mismatch, parity only, the one synthetic run, the once-only / `.partial`
    refusals, the implementation check failing (exit 3), the parity check failing (exit 3, parity-only and the read), the missing-pair
    refusal on a second tree, and the module pin refusing even a dry run."""
    tree2 = T._xp_tree(tmp_path / "b", monkeypatch)            # the second tree first: the next call re-points REPO / HERE / the module sha
    tree = T._xp_tree(tmp_path, monkeypatch)
    P = ["--data", str(tree["cb702"]), "--data-pre", str(tree["cb702_pre"]), "--period", "discovery", "--workers", "1"]
    out = tree["cb702"] / "out"
    cap.run("print_pins", ["exit-read", *P, "--print-pins"])
    cap.run("dry_run", ["exit-read", *P, "--dry-run"])
    cap.run("refuse_out", ["exit-read", *P, "--out", str(tmp_path / "elsewhere")])
    cap.run("refuse_small_out", ["exit-read", *P, "--small-out", str(tmp_path / "elsewhere")])
    cap.run("refuse_prereg", ["exit-read", *P, "--prereg", str(tree["doc"])])
    cap.run("refuse_parity_only_no_freeze_check", ["exit-read", *P, "--parity-only", "--no-freeze-check"])
    cap.run("refuse_no_period", ["exit-read", "--data", str(tree["cb702"]), "--data-pre", str(tree["cb702_pre"]), "--workers", "1"])
    cap.run("parity_only", ["exit-read", *P, "--parity-only"])
    cands = out / "candidates.tsv"                             # a pinned file edited: parity only still runs (no freeze); the read refuses
    before = cands.read_bytes()
    cands.write_bytes(before + b"\n")
    cap.run("parity_only_mismatched_footer", ["exit-read", *P, "--parity-only"])
    cap.run("refuse_freeze_mismatch", ["exit-read", *P])
    cands.write_bytes(before)
    cap.run("exit_read", ["exit-read", *P])
    cap.run("refuse_once_only", ["exit-read", *P])
    for q in rn.exitpb_existing_outputs(out, "discovery"):
        q.unlink()
    (out / "trades_discovery_exitpb.tsv.gz.partial").write_bytes(b"half")
    cap.run("refuse_partial", ["exit-read", *P])
    (out / "trades_discovery_exitpb.tsv.gz.partial").unlink()
    with pytest.MonkeyPatch.context() as mp:                   # an implementation check failing: the table stays, no report, exit 3
        mp.setattr(rn, "exitpb_self_checks", lambda df, period: (["(a) 1 pp-family session thirds sold on a close at or below the fill"], ["(a) ..."]))
        cap.run("implementation_check_failed", ["exit-read", *P])
    for q in rn.exitpb_existing_outputs(out, "discovery"):
        q.unlink()
    pinned = out / "trades_discovery_h60.tsv.gz"               # a tampered pinned row: parity fails, exit 3, nothing written
    _tamper_pinned(pinned, rn.EXITPB_BASE.name)
    _xp_doc(tree)
    cap.run("parity_failed_parity_only", ["exit-read", *P, "--parity-only"])
    cap.run("parity_failed_read", ["exit-read", *P])
    with pytest.MonkeyPatch.context() as mp:                   # the second tree: the h60 fill's pair is no longer logged
        mp.setattr(rn, "EXITPB_MODULE_SHA", rn.sha256_file(tree2["repo"] / rn.MODULE_REL))
        mp.setattr(rn, "REPO", tree2["repo"])
        mp.setattr(rn, "HERE", tmp_path / "b" / "hereroot")
        (tree2["cb702"] / "minutes" / "_done.psv").write_text(f"{tree2['c1']['E']}|X|390|ok\n")
        cap.run("refuse_missing_pairs", ["exit-read", "--data", str(tree2["cb702"]), "--data-pre", str(tree2["cb702_pre"]), "--period", "discovery",
                                         "--workers", "1", "--parity-only"])
    monkeypatch.setattr(rn, "EXITPB_MODULE_SHA", "0" * 64)
    cap.run("refuse_module_pin_dry_run", ["exit-read", *P, "--dry-run", "--no-freeze-check"])


SCENARIOS = {"daily": scenario_daily, "daily_era": scenario_daily_era, "minute_report": scenario_minute_report, "step0_entries": scenario_step0_entries,
             "p5": scenario_p5, "exits": scenario_exits, "holdout": scenario_holdout, "pre_read": scenario_pre_read, "h60": scenario_h60,
             "exit_read": scenario_exit_read}


def run_scenario(name: str, tmp_path: Path, capsys, monkeypatch) -> Capture:
    cap = Capture(tmp_path, capsys)
    SCENARIOS[name](cap, tmp_path, monkeypatch)
    return cap


# ═══ the tests ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_stage_reproduces_its_golden_bytes(name, tmp_path, capsys, monkeypatch):
    cap = run_scenario(name, tmp_path, capsys, monkeypatch)
    assert any(k.endswith("/stdout") for k in cap.arts) and len(cap.arts) > 3
    check(name, cap, tmp_path)


def test_every_scenario_has_a_bundle_and_every_stored_text_matches_its_header():
    assert PINNED_ON.exists(), "no pins yet: run with CB_GOLDEN_UPDATE=1 once"
    on_disk = {p.stem for p in GOLDEN.glob("*.golden")}
    assert on_disk == set(SCENARIOS), (on_disk ^ set(SCENARIOS))
    n = 0
    for name in SCENARIOS:
        pins = read_bundle(name)
        assert pins
        for k, pin in pins.items():
            n += 1
            if pin["text"] is not None:
                assert sha256(pin["text"].encode("utf-8")) == pin["sha256"] and len(pin["text"].encode("utf-8")) == pin["bytes"], \
                    f"{name}: the stored text of {k} does not match its header - the bundle was hand-edited"
    assert n > 250


def test_the_pinned_refusal_paths_cover_every_guard_of_the_finished_reads():
    """The brief: each finished read's refusal paths are pinned. The steps named here are the guards; a scenario that drops one fails."""
    steps = {name: {k.split("/", 1)[0] for k in read_bundle(name)} for name in SCENARIOS}
    assert {"refuse_no_period", "refuse_small_out", "refuse_missing_pairs_step0", "refuse_missing_pairs", "refuse_freeze_mismatch",
            "refuse_step0_differs", "twin_failed", "refuse_once_only", "refuse_partial"} <= steps["h60"]
    assert {"refuse_no_period", "parity_only_mismatched_footer", "refuse_freeze_mismatch", "refuse_missing_pairs", "implementation_check_failed",
            "parity_failed_parity_only", "parity_failed_read", "refuse_module_pin_dry_run", "refuse_once_only", "refuse_partial"} <= steps["exit_read"]
    assert {"refuse_no_close", "refuse_freeze_mismatch", "refuse_once_only", "refuse_partial", "refuse_after_the_run"} <= steps["holdout"]
    assert {"refuse_missing_pairs", "refuse_empty", "crosscheck_failed", "refuse_once_only", "refuse_partial"} <= steps["pre_read"]
    assert {"daily_era"} <= steps["daily_era"]
    pins = read_bundle("exit_read")
    assert pins["parity_only_mismatched_footer/exit"]["text"] == "0" and pins["refuse_freeze_mismatch/exit"]["text"] == "2"
    for k in ("h60/twin_failed", "exit_read/parity_failed_parity_only", "exit_read/parity_failed_read", "exit_read/implementation_check_failed",
              "pre_read/crosscheck_failed"):
        scenario, step = k.split("/")
        assert read_bundle(scenario)[f"{step}/exit"]["text"] == "3", k


def test_the_normaliser_touches_only_the_volatile_tokens(tmp_path):
    root = str(tmp_path)
    assert normalise(f"WROTE {root}/data/out/x.tsv (3 rows); WALL TIME: 12s total  load=3s  pass 1 (a + b)=0s", (root,)) == \
        "WROTE <TMP>/data/out/x.tsv (3 rows); WALL TIME: <N>s total  load=<N>s  pass 1 (a + b)=<N>s"
    assert normalise("bars: 440 rows / 2 tickers / 220 sessions 2023-01-02..2023-11-03 (0s); [load: 1s] [read 12 rows: 0s]") == \
        "bars: 440 rows / 2 tickers / 220 sessions 2023-01-02..2023-11-03 (<N>s); [load: <N>s] [read 12 rows: <N>s]"
    assert normalise("module sha256 " + "a" * 64 + " (registered); footer 0123456789ab... vs now fedcba987654...; (sha256 0123456789ab)") == \
        "module sha256 <SHA64> (registered); footer <SHA12>... vs now <SHA12>...; (sha256 0123456789ab)"
    h, g = "a" * 64, "b" * 64
    assert normalise(f"- x sha256: `{h}`; runner sha256 {g}; footer {h[:12]}... vs now {'c' * 12}...", shas={h: "cb702/out/x.tsv", g: "runner"}) == \
        "- x sha256: `<SHA:cb702/out/x.tsv>`; runner sha256 <SHA:runner>; footer <SHA12:cb702/out/x.tsv>... vs now <SHA12>..."
    assert normalise("VERDICT FILE - period pre - written 2026-10-24") == "VERDICT FILE - period pre - written <DATE>"
    keep = "390 rows, 2 (date, ticker) pairs, p33_s3_t10, C1_s5, stopped_day0, orh5: k5=1, tl=1, 7 dates, 10.3103\t0.5\t3\n2025-03-03|X|390|ok"
    assert normalise(keep, (root,)) == keep


def test_print_pins_binds_each_label_to_its_file(tmp_path, capsys, monkeypatch):
    """The sha a label prints is replaced by the file's relative path, so a label repointed at another file changes the pinned text."""
    cap = run_scenario("h60", tmp_path, capsys, monkeypatch)
    pins = cap.arts["print_pins/stdout"].decode()
    assert "- cb702/out/candidates.tsv sha256: `<SHA:cb702/out/candidates.tsv>`" in pins
    assert "- cb702_pre/daily_closes_all.csv.gz sha256: `<SHA:cb702_pre/daily_closes_all.csv.gz>`" in pins
    assert "- runner sha256: `<SHA:runner>`" in pins and "- module sha256: `<SHA:repo/agents/market_intelligence/consolidation_breakout.py>`" in pins
    assert "- cb702/minutes (tree) sha256: `<SHA64>`" in pins and "- doc body sha256: `<SHA64>`" in pins      # composites: not a file's sha
    with pytest.MonkeyPatch.context() as mp:                   # the pre watch table's label silently hashing the candidates file: a different text
        real = rn.h60_frozen_files

        def repointed(dirs, repo=rn.REPO):
            files = real(dirs, repo)
            files["cb702_pre/out/watch_tl_com.tsv.gz"] = files["cb702/out/candidates.tsv"]
            return files
        mp.setattr(rn, "h60_frozen_files", repointed)
        other = run_scenario("h60", tmp_path / "again", capsys, monkeypatch).arts["print_pins/stdout"].decode()
    assert "- cb702_pre/out/watch_tl_com.tsv.gz sha256: `<SHA:cb702/out/candidates.tsv>`" in other and other != pins


def test_the_harness_catches_a_one_byte_change(tmp_path, capsys, monkeypatch):
    """One extra byte in ONE cell of ONE written table - the smallest change a refactor could make - is named, and nothing else is. A clean
    run of the same scenario is the reference, so the test holds on every platform."""
    clean = pins_of(run_scenario("step0_entries", tmp_path / "clean", capsys, monkeypatch).arts)
    real = rn._fmt
    hit = []

    def one_byte(x):                                                     # the first `orh5` cell the STAGE writes (the setup writes none)
        s = real(x)
        if x == "orh5" and not hit:
            hit.append(1)
            return s + " "
        return s
    monkeypatch.setattr(rn, "_fmt", one_byte)
    cap = run_scenario("step0_entries", tmp_path / "mutated", capsys, monkeypatch)
    assert hit
    problems = compare_pins(clean, cap.arts)
    assert len(problems) == 1 and problems[0].startswith("step0_entries/data/out/entries_holdout_composition.tsv: sha256 "), problems
    assert "orh5 \t" in problems[0]                                      # the diff shows the byte


def test_the_harness_sees_a_deleted_file(tmp_path, capsys, monkeypatch):
    """A step that removes a file that existed before it leaves a `<DELETED>` artefact (an input, a prior output, a crashed run's .partial)."""
    clean = pins_of(run_scenario("step0_entries", tmp_path / "clean", capsys, monkeypatch).arts)
    real = rn.main

    def main_then_delete(argv):
        r = real(argv)
        (tmp_path / "mutated" / "data" / "minutes" / "_done.psv").unlink()
        return r
    monkeypatch.setattr(rn, "main", main_then_delete)
    cap = run_scenario("step0_entries", tmp_path / "mutated", capsys, monkeypatch)
    assert cap.arts["step0_entries/data/minutes/_done.psv"] == DELETED
    problems = compare_pins(clean, cap.arts)
    assert [p.split(":")[0] for p in problems] == ["step0_entries/data/minutes/_done.psv"] and "NOT PINNED" in problems[0], problems


def test_a_rewrite_with_identical_content_is_never_an_artefact_whatever_the_clock_says(tmp_path):
    """`write_tsv(gz=True)` stamps the gzip header with the second it ran: the change detection must read the content, not the bytes."""
    root = tmp_path / "root"
    (root / "out").mkdir(parents=True)
    rows, cols = [{"a": 1, "b": "x"}], ["a", "b"]
    p = root / "out" / "t.tsv.gz"
    rn.write_tsv(p, rows, cols, gz=True)
    a = _snapshot(root)["out/t.tsv.gz"]
    raw = bytearray(p.read_bytes())
    raw[4:8] = (int.from_bytes(raw[4:8], "little") + 1).to_bytes(4, "little")      # the header's mtime one second later, same content
    p.write_bytes(bytes(raw))
    b = _snapshot(root)["out/t.tsv.gz"]
    assert a[0] != b[0] and a[1] == b[1]                                            # raw sha differs, content sha does not
    rn.write_tsv(p, [{"a": 2, "b": "x"}], cols, gz=True)
    assert _snapshot(root)["out/t.tsv.gz"][1] != a[1]


def test_a_label_does_not_depend_on_the_second_a_gzip_was_written_in(tmp_path):
    """Two tables with the SAME rows share one label whatever their gzip header clocks say; different rows, a plain file with the same
    text and a stub that only wears the `.gz` name never mix into it (the flake: a tree built across a second boundary relabelled
    `--print-pins`)."""
    root = tmp_path / "root"
    (root / "b" / "d").mkdir(parents=True)
    (root / "d").mkdir()
    rows, cols = [{"a": 1, "b": "x"}], ["a", "b"]
    for rel in ("d/x.tsv.gz", "b/d/x.tsv.gz"):
        rn.write_tsv(root / rel, rows, cols, gz=True)
    raw = bytearray((root / "b/d/x.tsv.gz").read_bytes())
    raw[4:8] = (int.from_bytes(raw[4:8], "little") + 7).to_bytes(4, "little")                 # written seven seconds later
    (root / "b/d/x.tsv.gz").write_bytes(bytes(raw))
    rn.write_tsv(root / "d/other.tsv.gz", [{"a": 2, "b": "x"}], cols, gz=True)
    (root / "d/plain.tsv").write_bytes(gzip.decompress((root / "d/x.tsv.gz").read_bytes()))   # the same text, not a gzip
    (root / "d/stub.csv.gz").write_bytes(b"export")                                           # a stub wearing the name
    after = _snapshot(root)
    assert after["d/x.tsv.gz"][0] != after["b/d/x.tsv.gz"][0] and after["d/x.tsv.gz"][1] == after["b/d/x.tsv.gz"][1]
    labels = sha_labels(after)
    assert labels[after["d/x.tsv.gz"][0]] == labels[after["b/d/x.tsv.gz"][0]] == "b/d/x.tsv.gz|d/x.tsv.gz"
    assert labels[after["d/other.tsv.gz"][0]] == "d/other.tsv.gz"
    assert labels[after["d/plain.tsv"][0]] == "d/plain.tsv" and labels[after["d/stub.csv.gz"][0]] == "d/stub.csv.gz"


class _Clock:
    """`gzip`'s view of `time`: `step` seconds later on every call (0 = every gzip written in the same second, 1 = in a different one)."""

    def __init__(self, step: float):
        self.now, self.step = 1_800_000_000.0, step

    def time(self):
        self.now += self.step
        return self.now


def test_two_runs_of_the_same_code_give_the_same_normalised_bytes(tmp_path, capsys, monkeypatch):
    """The normaliser covers every volatile token: the cheapest scenarios, the era path and the two tampering scenarios, run twice in two
    directories, agree byte for byte - the first run with every gzip written in the SAME second, the second with each in a DIFFERENT one
    (the two extremes of the wall clock in a gzip header; a tree built across a second boundary relabelled `--print-pins` between runs)."""
    for name in ("step0_entries", "pre_read", "daily_era", "h60", "exit_read"):
        with monkeypatch.context() as mp:
            mp.setattr(gzip, "time", _Clock(0.0))
            a = run_scenario(name, tmp_path / "a" / name, capsys, monkeypatch).arts
        with monkeypatch.context() as mp:
            mp.setattr(gzip, "time", _Clock(1.0))
            b = run_scenario(name, tmp_path / "b" / name, capsys, monkeypatch).arts
        assert set(a) == set(b)
        assert [k for k in a if a[k] != b[k]] == []


def test_the_pins_are_binding_and_a_missing_artefact_fails(tmp_path, capsys, monkeypatch):
    """The header's sha is what binds: a one-newline change in a stored-text artefact fails, and so does a pinned artefact that is missing."""
    cap = run_scenario("step0_entries", tmp_path, capsys, monkeypatch)
    clean = pins_of(cap.arts)
    arts = dict(cap.arts)
    key = "step0_entries/data/out/entries_holdout_composition.tsv"
    arts[key] = arts[key] + b"\n"
    problems = compare_pins(clean, arts)
    assert len(problems) == 1 and key in problems[0]
    arts = dict(cap.arts)
    del arts["step0_entries/exit"]
    assert any("pinned but NOT PRODUCED" in p for p in compare_pins(clean, arts))
    assert compare_pins(read_bundle("step0_entries"), cap.arts) == [] or platform_gap()      # and the bundle itself binds on the pinned platform


def test_the_platform_guard_names_the_gap(monkeypatch):
    on = json.loads(PINNED_ON.read_text())
    monkeypatch.setattr(platform, "system", lambda: on["system"])        # this run made to look like the pinned platform, wherever it runs
    monkeypatch.setattr(platform, "machine", lambda: on["machine"])
    monkeypatch.setattr(np, "__version__", on["numpy"])
    monkeypatch.setattr(pd, "__version__", on["pandas"])
    assert platform_gap() is None
    monkeypatch.setattr(np, "__version__", "9.1.0")
    assert platform_gap() == f"numpy {on['numpy']} -> 9.1.0"
    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    assert platform_gap().startswith("system ") and "numpy" in platform_gap()
    monkeypatch.setattr(np, "__version__", on["numpy"].rsplit(".", 1)[0] + ".99")  # a patch release is not a gap
    assert platform_gap() == f"system {on['system']} -> Plan9"
