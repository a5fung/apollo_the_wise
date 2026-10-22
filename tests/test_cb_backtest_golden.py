"""Golden-bytes harness for the #702 Consolidation Breakout backtest runner (#705 (a), 2026-10-24).

Every finished stage of `scripts/probes/_cb_backtest/runner.py` is run on SYNTHETIC data and the EXACT bytes it leaves behind are
pinned: the stdout, the stderr and the exit code of every invocation, and the content of every file it writes (a gzip table by its
DECOMPRESSED content - the gzip header carries a timestamp). A refactor of the runner is byte-neutral when this file is green, and
the harness fails on a ONE-BYTE change (`test_the_harness_catches_a_one_byte_change` proves it on the real pipeline).

Covered: `daily` (the registered four levels, `--step0`, `--keys com,comb --no-close-variant`), `minute` (with and without the CLOSE
variant / the Apollo control, `--keys com,comb`), `step0-entries`, `report`, `exits` / `exits-report`, `p5`, and EVERY path of the four
finished registered reads - `holdout`, `pre-read`, `h60-step0` / `h60-read` / `h60-hindsight`, `exit-read`: `--print-pins`, `--dry-run`,
each option refusal, the freeze mismatch, the once-only and `.partial` refusals, the missing-pair refusal, the module pin, and the full
synthetic run of each (the real runs happened once, on real data, and are not reproduced here).

The pins: tests/fixtures/cb_backtest_golden/<scenario>.golden - one record per artefact: a header line carrying the BINDING sha256
and byte count, then the artefact's normalised text when it is text and at most TEXT_CAP bytes, so a legitimate change shows as a
readable git diff and a failure prints a unified diff; PINNED_ON.json records the platform.

Normalised before hashing - the only tokens that differ between two runs of the SAME code on the same platform, nothing else:
  <TMP>        every spelling of the test's temporary directory and of the repo root (the stages print the paths they read and write)
  <N>s         a wall-time token: `[load: 3s]`, `WALL TIME: 12s total`, `(45s)`, `load=3s`, `[... 7s]`
  <SHA64>      any 64-hex sha256 (the runner prints the hash of its OWN file, which changes with every edit of it)
  <SHA12>...   the 12-hex prefix + `...` the freeze refusals and the twin check print
  <DATE>       `written YYYY-MM-DD` in the verdict files
`test_the_normaliser_touches_only_the_volatile_tokens` pins the normaliser itself.

RE-PIN ONLY FOR AN INTENDED OUTPUT CHANGE, in its own reviewed commit (the diff of the bundles is the review):
    CB_GOLDEN_UPDATE=1 python3 -m pytest tests/test_cb_backtest_golden.py -q
PINNED_ON.json records the platform; a float that comes out of a numpy reduction is expected to be bit-identical
across platforms (the pairwise sum is scalar C), but if a run on another platform differs ONLY in a last digit, say so before re-pinning.
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


# ═══ the normaliser ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def normalise(text: str, roots: tuple = ()) -> str:
    for r in roots:
        if r:
            text = text.replace(r, "<TMP>")
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


def artefact_bytes(name: str, raw: bytes, roots: tuple) -> bytes:
    """The bytes that are pinned: a gzip file by its content; a text artefact normalised; anything else as is."""
    if name.endswith(".gz"):
        raw = gzip.decompress(raw)
    if is_text_name(name):
        try:
            return normalise(raw.decode("utf-8"), roots).encode("utf-8")
        except UnicodeDecodeError:
            return raw
    return raw


# ═══ capture: run a stage, keep what it printed and what it wrote ═════════════════════════════════════════════════════════════════
def _snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[p.relative_to(root).as_posix()] = sha256(p.read_bytes())
    return out


class Capture:
    """`run(step, argv)` calls `rn.main(argv)` and records `<step>/stdout`, `<step>/stderr`, `<step>/exit` and `<step>/<relative path>`
    for every file under `root` that the call created or changed (the test's own stubs, written between runs, are never artefacts)."""

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
        assert step not in {k.split("/", 1)[0] for k in self.arts}, f"step {step!r} used twice"
        self.arts[f"{step}/stdout"] = artefact_bytes("stdout", cap.out.encode(), self.roots)
        self.arts[f"{step}/stderr"] = artefact_bytes("stderr", cap.err.encode(), self.roots)
        self.arts[f"{step}/exit"] = str(rc).encode()
        for rel, h in after.items():
            if before.get(rel) != h:
                self.arts[f"{step}/{rel}"] = artefact_bytes(Path(rel).name, (self.root / rel).read_bytes(), self.roots)
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


def bundle_path(scenario: str) -> Path:
    return GOLDEN / f"{scenario}.golden"


def write_bundle(scenario: str, arts: dict) -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    parts = []
    for k in sorted(arts):
        data = arts[k]
        stored = is_text_name(Path(k).name) and len(data) <= TEXT_CAP
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


def compare(scenario: str, arts: dict, actual_dir: "Path | None" = None, *, update: bool = UPDATE) -> list:
    """Problems (empty = every artefact of the scenario equals its pin and nothing pinned is missing). With CB_GOLDEN_UPDATE=1 the
    scenario's bundle is rewritten instead and the list is empty - only from the scenario tests: the self-tests below compare deliberately
    mutated artefacts and pass `update=False`, so a re-pin run can never write a mutated bundle."""
    if update:
        write_bundle(scenario, arts)
        return []
    pins = read_bundle(scenario)
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


def check(scenario: str, cap: Capture, tmp_path: Path) -> None:
    problems = compare(scenario, cap.arts, tmp_path / "golden_actual")
    on = json.loads(PINNED_ON.read_text()) if PINNED_ON.exists() else None
    assert not problems, (f"{len(problems)} golden artefact(s) of scenario {scenario!r} differ (pinned on {on}; this run: {pinned_on()}):\n"
                          + "\n".join(problems))


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
    run, the once-only and `.partial` refusals."""
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


def scenario_h60(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The hourly-close read on the synthetic cb702 + cb702_pre tree with a matching registration doc: the pins, the dry runs, every
    refusal, the freeze mismatch, STEP 0, the one synthetic run, the once-only / `.partial` refusals, the hindsight tables."""
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
    cap.run("refuse_minutes", ["h60-read", *P, "--minutes", str(tree["cb702"] / "minutes")])
    cap.run("refuse_no_freeze_check", ["h60-read", *P, "--no-freeze-check"])
    p = tree["cb702"] / "out" / "candidates.tsv"
    before = p.read_bytes()
    p.write_bytes(before + b"\n")
    cap.run("refuse_freeze_mismatch", ["h60-read", *P])
    p.write_bytes(before)
    cap.run("refuse_hindsight_before_verdict", ["h60-hindsight", *P])
    cap.run("step0", ["h60-step0", *P])
    cap.run("h60_read", ["h60-read", *P])
    cap.run("refuse_once_only", ["h60-read", *P])
    cap.run("hindsight", ["h60-hindsight", *P])
    out = tree["cb702"] / "out"
    for q in rn.h60_existing_outputs(out, "discovery"):
        q.unlink()
    (out / "trades_discovery_h60.tsv.gz.partial").write_bytes(b"half")
    cap.run("refuse_partial", ["h60-read", *P])
    (out / "trades_discovery_h60.tsv.gz.partial").unlink()


def scenario_exit_read(cap: Capture, tmp_path: Path, monkeypatch) -> None:
    """The exit read on the h60 tree after its hourly-close run: the pins, the dry run, every refusal, parity only, the one synthetic
    run, the once-only / `.partial` refusals, and the module pin refusing even a dry run."""
    tree = T._xp_tree(tmp_path, monkeypatch)
    P = ["--data", str(tree["cb702"]), "--data-pre", str(tree["cb702_pre"]), "--period", "discovery", "--workers", "1"]
    cap.run("print_pins", ["exit-read", *P, "--print-pins"])
    cap.run("dry_run", ["exit-read", *P, "--dry-run"])
    cap.run("refuse_out", ["exit-read", *P, "--out", str(tmp_path / "elsewhere")])
    cap.run("refuse_small_out", ["exit-read", *P, "--small-out", str(tmp_path / "elsewhere")])
    cap.run("refuse_prereg", ["exit-read", *P, "--prereg", str(tree["doc"])])
    cap.run("refuse_parity_only_no_freeze_check", ["exit-read", *P, "--parity-only", "--no-freeze-check"])
    cap.run("parity_only", ["exit-read", *P, "--parity-only"])
    cap.run("exit_read", ["exit-read", *P])
    cap.run("refuse_once_only", ["exit-read", *P])
    out = tree["cb702"] / "out"
    for q in rn.exitpb_existing_outputs(out, "discovery"):
        q.unlink()
    (out / "trades_discovery_exitpb.tsv.gz.partial").write_bytes(b"half")
    cap.run("refuse_partial", ["exit-read", *P])
    (out / "trades_discovery_exitpb.tsv.gz.partial").unlink()
    monkeypatch.setattr(rn, "EXITPB_MODULE_SHA", "0" * 64)
    cap.run("refuse_module_pin_dry_run", ["exit-read", *P, "--dry-run", "--no-freeze-check"])


SCENARIOS = {"daily": scenario_daily, "minute_report": scenario_minute_report, "step0_entries": scenario_step0_entries, "p5": scenario_p5,
             "exits": scenario_exits, "holdout": scenario_holdout, "pre_read": scenario_pre_read, "h60": scenario_h60, "exit_read": scenario_exit_read}


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


def test_the_normaliser_touches_only_the_volatile_tokens(tmp_path):
    root = str(tmp_path)
    assert normalise(f"WROTE {root}/data/out/x.tsv (3 rows); WALL TIME: 12s total  load=3s  pass 1 (a + b)=0s", (root,)) == \
        "WROTE <TMP>/data/out/x.tsv (3 rows); WALL TIME: <N>s total  load=<N>s  pass 1 (a + b)=<N>s"
    assert normalise("bars: 440 rows / 2 tickers / 220 sessions 2023-01-02..2023-11-03 (0s); [load: 1s] [read 12 rows: 0s]") == \
        "bars: 440 rows / 2 tickers / 220 sessions 2023-01-02..2023-11-03 (<N>s); [load: <N>s] [read 12 rows: <N>s]"
    assert normalise("module sha256 " + "a" * 64 + " (registered); footer 0123456789ab... vs now fedcba987654...; (sha256 0123456789ab)") == \
        "module sha256 <SHA64> (registered); footer <SHA12>... vs now <SHA12>...; (sha256 0123456789ab)"
    assert normalise("VERDICT FILE - period pre - written 2026-10-24") == "VERDICT FILE - period pre - written <DATE>"
    keep = "390 rows, 2 (date, ticker) pairs, p33_s3_t10, C1_s5, stopped_day0, orh5: k5=1, tl=1, 7 dates, 10.3103\t0.5\t3\n2025-03-03|X|390|ok"
    assert normalise(keep, (root,)) == keep


def test_the_harness_catches_a_one_byte_change(tmp_path, capsys, monkeypatch):
    """One extra byte in ONE cell of ONE written table - the smallest change a refactor could make - is named, and nothing else is."""
    real = rn._fmt
    hit = []

    def one_byte(x):                                                     # the first `orh5` cell the STAGE writes (the setup writes none)
        s = real(x)
        if x == "orh5" and not hit:
            hit.append(1)
            return s + " "
        return s
    monkeypatch.setattr(rn, "_fmt", one_byte)
    cap = run_scenario("step0_entries", tmp_path, capsys, monkeypatch)
    assert hit
    problems = compare("step0_entries", cap.arts, update=False)
    assert len(problems) == 1 and problems[0].startswith("step0_entries/data/out/entries_holdout_composition.tsv: sha256 "), problems
    assert "orh5 \t" in problems[0]                                      # the diff shows the byte


def test_two_runs_of_the_same_code_give_the_same_normalised_bytes(tmp_path, capsys, monkeypatch):
    """The normaliser covers every volatile token: the cheapest two scenarios, run twice in two directories, agree byte for byte."""
    for name in ("step0_entries", "pre_read"):
        a = run_scenario(name, tmp_path / "a" / name, capsys, monkeypatch).arts
        b = run_scenario(name, tmp_path / "b" / name, capsys, monkeypatch).arts
        assert set(a) == set(b)
        assert [k for k in a if a[k] != b[k]] == []


def test_the_pins_are_binding_and_a_missing_artefact_fails(tmp_path, capsys, monkeypatch):
    """The header's sha is what binds: a one-newline change in a stored-text artefact fails, and so does a pinned artefact that is missing."""
    cap = run_scenario("step0_entries", tmp_path, capsys, monkeypatch)
    arts = dict(cap.arts)
    key = "step0_entries/data/out/entries_holdout_composition.tsv"
    arts[key] = arts[key] + b"\n"
    problems = compare("step0_entries", arts, update=False)
    assert len(problems) == 1 and key in problems[0]
    arts = dict(cap.arts)
    del arts["step0_entries/exit"]
    assert any("pinned but NOT PRODUCED" in p for p in compare("step0_entries", arts, update=False))
