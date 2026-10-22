"""#705 (a) - the shared 'registered read' scaffold for scripts/probes/_cb_backtest/runner.py (built 2026-10-24, synthetic tests only).

Four one-run reads were built by copying the same plumbing four times (`holdout`, `pre-read`, `h60-read`, `exit-read`): a freeze map
+ `--print-pins`, a once-only guard with the `.partial` protocol, option refusals, `--dry-run`, a verdict file. The copies drifted:
`h60-read --out` was checked against cb702/out but the pre period READ cb702_pre/out; `exit-read` ignored `--out`; the pre-read had no
freeze at all. This module is ONE driver for every read registered after it. The four finished reads are NOT migrated (their freeze
records pin the runner that ran them); they stay as they are, byte for byte (tests/test_cb_backtest_golden.py).

    spec = RegisteredRead(name="quality-read", tag="quality", doc="cb_quality_prereg_2026-10-24.md", frozen=..., prepare=..., outputs=...,
                          dry_run=..., body=..., periods=("discovery", "pre", "holdout"), hard_pins=(("module", module_path, SHA),))
    runner.REGISTERED_READS[spec.name] = spec          # main() dispatches it; `run_registered_read(spec, args)` runs it

The guards are NOT opt-out: `order` must carry EVERY check (a permutation of DEFAULT_ORDER that keeps the driver's chain - print-pins first;
period / prereg / options / no-freeze-check / hard pins before the freeze; freeze before prepare; prepare before dry-run; dry-run before
once-only; once-only before empty and missing pairs). Dropping a guard is a ValueError at construction, not a quieter read.

The driver (`run_registered_read`) resolves data / out / small / minutes / period ONCE into a `Ctx` and runs the checks in `spec.order`:
  print_pins       `--print-pins`: the footer lines of `frozen_map(spec, ctx)` (+ the doc-body line) and exit 0 - before anything else
  period           `--period` required and one of `spec.periods` (when the read has periods)
  prereg           `--prereg` only with `--print-pins` / `--dry-run` (a real run pins the doc under docs/analysis itself)
  options          every `spec.refused` option; `--out` against THE DIR THE PERIOD READS (`ctx.data / "out"`); `--small-out` against HERE/out;
                   `--minutes` against the period's own tree (hard-coded, whether or not the spec lists it)
  no_freeze_check  `--no-freeze-check` only together with `--dry-run`
  hard_pins        the registration's hard pins (e.g. the module sha): footer or no footer, even on a dry run
  freeze           `freeze_check` on the registration doc's footer against `frozen_map(spec, ctx)` - BEFORE any input file is opened. The
                   map is the spec's `frozen(ctx)` plus what the DRIVER pins by itself: the runner, THIS scaffold, and the module the body
                   lives in when that is neither (`spec module`) - the guard code is part of what a read rests on. A read that declares
                   `doc=None` has NO freeze and its run log says so (an omission is not a declaration: a doc with an empty map refuses)
  prepare          `spec.prepare(ctx)` -> {"rows": the population, "inp": `minute_inputs` or None, "path": the candidates file (optional),
                   "opens": other inputs the body will open (optional)} - opens no daily bar and no minute row. The driver then REFUSES
                   when the freeze map does not cover the minute directory `inp` reads, `path`, or any of `opens` (the pre-read's hole:
                   a freeze that passes because it pins nothing the read opens); then the once-only scan
  dry_run          `--dry-run`: `spec.dry_run(ctx, prep, existing)` printed, exit 0, nothing written
  once_only        a final output, a verdict file (out or small), or a crashed run's `.partial` on disk refuses (the operator removes a
                   `.partial` by hand)
  empty            no row in the population refuses
  missing_pairs    a (date, ticker) pair not logged in `_done.psv` (or logged ok with no file) refuses - a partial read is never run
then, after one last check that the freeze actually passed (or was declared absent), `spec.body(ctx, prep, say)`: a `Verdict` is written by
the driver through the `.partial` protocol as `<tag>_verdict_<period>.json` + `.txt` (out) and `.txt` (small); an int is the exit code
(3 = a check inside the read failed; the driver writes nothing more); `None` is a defect of the read, logged, exit 3. The run log goes to
`<tag>_summary_<period>.txt`. Every refusal prints to stderr and returns 2. The refusal texts are `spec.messages` templates, printed
verbatim (`str.format` fields only).

Speed / memory helpers for the next reads (not retrofitted into the finished stages - a cache hit would change their printed lines):
`sha256_file` (streaming, the identical digest), `load_daily_cached` (one slot keyed by path / size / mtime: the pre-read loaded the
export twice, the exit read too), `read_candidates_cached` (one slot keyed by path / size / mtime / the reader's keywords: the finished
reads parse the candidates file two or three times), `read_watch_index` (the watch table by `usecols` + explicit dtypes in chunks - the
h60 read's `h60_watch_index` reads it whole through type inference; the values are proved identical in the tests).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import inspect
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

SCAFFOLD_PATH = Path(__file__).resolve()                     # pinned by every registered read's freeze (monkeypatched to a copy in the tests)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# speed / memory helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def sha256_file(p) -> str:
    """sha256 of a file, streamed (`hashlib.file_digest`): the identical digest without reading the file whole."""
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


_DAILY_SLOT: dict = {}                      # the single slot: {"key": (resolved path, size, mtime_ns), "value": the loaded export}
_CANDS_SLOT: dict = {}                      # the single slot: {"key": (resolved path, size, mtime_ns, the reader's keywords), "value": the rows}


def load_daily_cached(path, loader: Callable):
    """`loader(path)` once per (path, size, mtime): a second call on the same unchanged export returns the loaded object instead of
    re-reading 270 MB. ONE slot - a different file replaces it. `clear_daily_cache()` empties it (tests; a long process that must
    not keep the arrays)."""
    p = Path(path).resolve()
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if _DAILY_SLOT.get("key") == key:
        print(f"bars: {p.name} unchanged since the last load - the cached export is reused", flush=True)
        return _DAILY_SLOT["value"]
    value = loader(p)
    _DAILY_SLOT.clear()
    _DAILY_SLOT.update(key=key, value=value)
    return value


def clear_daily_cache() -> None:
    _DAILY_SLOT.clear()
    _CANDS_SLOT.clear()


def read_candidates_cached(path, reader: Callable, **kw) -> list:
    """`reader(path, **kw)` (the runner's `read_candidates`) once per (path, size, mtime, keywords): the finished reads parse the same
    candidates file two or three times per run. ONE slot. The keywords are part of the key by VALUE for strings / tuples and by IDENTITY
    for a callable (`where`): a `where` defined at module level hits, a lambda built per call does not (and is merely re-read). Returns a
    new list over the SAME row dicts - a caller may filter or extend the list, not edit a row."""
    p = Path(path).resolve()
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns, tuple(sorted(kw.items(), key=lambda kv: kv[0])))
    if _CANDS_SLOT.get("key") == key:
        print(f"candidates: {p.name} unchanged since the last parse - the cached rows are reused", flush=True)
        return list(_CANDS_SLOT["value"])
    value = reader(p, **kw)
    _CANDS_SLOT.clear()
    _CANDS_SLOT.update(key=key, value=value)
    return list(value)


WATCH_INDEX_CHUNK = 200_000


def read_watch_index(path, k: str, chunksize: int = WATCH_INDEX_CHUNK) -> dict:
    """The h60 read's `h60_watch_index` - {"row": {(ticker, D): {ci, i, pole_high, base_low, pivot, slope, anchor}}, "nights": {ticker:
    set of ci}, "noline": {(ticker, pole_date): set of ci}} - read by `usecols` with EXPLICIT dtypes in chunks, so the watch table is never
    held whole (the h60 read's version reads every column through type inference: 2-3 GB peak on the real table). Same pandas parser,
    same values (tests prove it on a synthetic file). `slope` / `anchor` are None except on tl."""
    import pandas as pd
    from collections import defaultdict
    num = ["pole_high", "base_low", f"pivot_{k}"] + (["tl_slope_pct", "tl_anchor_idx"] if k == "tl" else [])
    cols = ["ticker", "watch_date", "ci", "i", "pole_date"] + num
    dtypes = {"ticker": str, "watch_date": str, "pole_date": str, "ci": np.int64, "i": np.int64, **{c: np.float64 for c in num}}
    row, nights, noline = {}, defaultdict(set), defaultdict(set)
    for df in pd.read_csv(path, sep="\t", usecols=cols, dtype=dtypes, keep_default_na=False, na_values=[""], chunksize=chunksize):
        piv = df[f"pivot_{k}"].to_numpy(dtype=float)
        slope = df["tl_slope_pct"].to_numpy(dtype=float) if k == "tl" else np.full(len(df), np.nan)
        anchor = df["tl_anchor_idx"].to_numpy(dtype=float) if k == "tl" else np.full(len(df), np.nan)
        for n, (t, d, ci, i, pole, ph, bl) in enumerate(zip(df["ticker"], df["watch_date"], df["ci"].to_numpy(), df["i"].to_numpy(),
                                                             df["pole_date"], df["pole_high"].to_numpy(), df["base_low"].to_numpy())):
            ci = int(ci)
            row[(t, d)] = {"ci": ci, "i": int(i), "pole_high": float(ph), "base_low": float(bl),
                           "pivot": None if np.isnan(piv[n]) else float(piv[n]), "slope": None if np.isnan(slope[n]) else float(slope[n]),
                           "anchor": None if np.isnan(anchor[n]) else int(anchor[n])}
            nights[t].add(ci)
            if np.isnan(piv[n]):
                noline[(t, pole)].add(ci)
    return {"row": row, "nights": nights, "noline": noline}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the spec
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Messages:
    """The refusal texts, printed verbatim (only `str.format` fields are filled). The defaults are the four finished reads' wording."""
    options: str = "REFUSED: the {name} runs only in its registered form:"
    refused_option: str = "{option}: the {name} runs in its registered form only (every row, the pinned minute trees, the registered tables)"
    out_elsewhere: str = "--out {out} is not {expected} (the dir the period {period!r} reads): the pinned inputs and the once-only check live there"
    small_out_elsewhere: str = "--small-out {small_out} is not {expected}"
    minutes_elsewhere: str = "--minutes {minutes} is not {expected} (the minute tree the period {period!r} reads and the freeze pins)"
    period: str = "REFUSED: --period is required: one of {periods}"
    prereg: str = "REFUSED: --prereg is honoured only with --print-pins or --dry-run - the read pins the registration doc at docs/analysis/{doc} itself"
    no_freeze_check: str = "REFUSED: --no-freeze-check is honoured only together with --dry-run"
    hard_pin_missing: str = "REFUSED: {label} missing: {path}"
    hard_pin_mismatch: str = "REFUSED: {label} sha256 {got}... is not the registered {want}... - {file} was edited; the read does not open"
    freeze: str = "REFUSED: the freeze check failed - the read is not opened:"
    freeze_not_run: str = "REFUSED: the freeze check did not pass before the body ({state}) - the read is not opened"
    uncovered: str = "REFUSED: the freeze map of the {name} does not cover {what} {path} - a freeze that pins nothing the read opens is no freeze"
    problem_line: str = "  - {problem}"
    crashed: str = ("REFUSED: {path} is what a CRASHED {name} left behind - it holds some outcomes. The read is run ONCE{per_period}: the "
                    "operator inspects it and removes it by hand before any re-run")
    once: str = "REFUSED: the {name}'s outcomes are read ONCE{per_period} and {path} already exists"
    per_period: str = " per period"
    empty: str = "REFUSED: no row of {period} in {out}"
    missing_pairs: str = "REFUSED: {missing:,} of {pairs:,} (date, ticker) pairs are not logged in {done}{lost}. A partial read is never run"
    lost_clause: str = "; {lost:,} more are logged ok on a date that has no minute file"


@dataclass
class Ctx:
    """Everything a run resolves ONCE: the dirs, the period and the dir it reads, out / small / minutes, the doc, the repo. `out` is checked
    against `data / "out"` (the dir this period reads) and is the ONLY out dir the body sees - the hole the h60 and exit reads had."""
    args: argparse.Namespace
    rt: object                                  # the runner module (HERE, REPO, MODULE_REL, freeze_check, pin_lines, hashes_of, doc_body_sha, ...)
    dirs: dict                                  # {"cb702": --data, "cb702_pre": --data-pre or the sibling}
    period: "str | None"
    data: Path                                  # the dir the period reads
    out: Path
    small: Path
    minutes: Path
    repo: Path
    here: Path
    workers: int
    doc: "Path | None"
    freeze: str = "not run"                     # "passed" | "SKIPPED" | "NONE DECLARED"
    t0: float = field(default_factory=time.time)
    log: list = field(default_factory=list)

    def say(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.log.append(msg)

    def table_path(self, name: str) -> Path:
        return self.out / name

    @contextlib.contextmanager
    def partial_write(self, name: str, under: "Path | None" = None):
        """Open `<under or out>/<name>.partial` for bytes; renamed to `<name>` only on a clean exit (a crash leaves the `.partial` the
        once-only guard refuses until the operator removes it)."""
        final = (under or self.out) / name
        partial = Path(str(final) + ".partial")
        final.parent.mkdir(parents=True, exist_ok=True)
        with open(partial, "wb") as fh:
            yield fh
        os.replace(partial, final)


@dataclass(frozen=True)
class Verdict:
    """What a read decides: `data` -> `<tag>_verdict_<period>.json`, `lines` -> `<tag>_verdict_<period>.txt` (out + small)."""
    data: dict
    lines: tuple


def default_period_dir(dirs: dict, period: "str | None") -> Path:
    return dirs["cb702_pre"] if period == "pre" else dirs["cb702"]


REFUSED_DEFAULT = ("keys", "levels", "limit_dates", "no_close", "no_apollo", "trades", "minutes")
DEFAULT_ORDER = ("print_pins", "period", "prereg", "options", "no_freeze_check", "hard_pins", "freeze", "prepare", "dry_run", "once_only",
                 "empty", "missing_pairs")
# the driver's chain: (before, after) pairs every `order` keeps (print_pins first is checked apart)
ORDER_RULES = (("options", "no_freeze_check"), ("no_freeze_check", "freeze"), ("period", "freeze"), ("prereg", "freeze"), ("hard_pins", "freeze"),
               ("freeze", "prepare"), ("prepare", "dry_run"), ("dry_run", "once_only"), ("once_only", "empty"), ("once_only", "missing_pairs"),
               ("empty", "missing_pairs"))


@dataclass(frozen=True)
class RegisteredRead:
    name: str                                   # the CLI stage name
    tag: str                                    # the file tag: trades_<period>_<tag>.tsv.gz, <tag>_verdict_<period>.*, <tag>_summary_<period>.txt
    doc: "str | None"                           # the registration doc under docs/analysis; None = the read DECLARES it has no freeze
    frozen: Callable                            # ctx -> {footer label: path}: every artefact the read rests on (the driver adds the code it runs on)
    prepare: Callable                           # ctx -> {"rows": [...], "inp": the minute_inputs shape (or None), "path": ..., "opens": ...}; opens no bar / minute
    outputs: Callable                           # ctx -> the once-only file names under ctx.out (the driver adds `.partial` and the verdict files)
    dry_run: Callable                           # (ctx, prep, existing) -> the DRY RUN line
    body: Callable                              # (ctx, prep, say) -> Verdict | int
    periods: tuple = ()                         # () = no --period
    refused: tuple = REFUSED_DEFAULT            # argparse dests a run may not carry
    hard_pins: tuple = ()                       # ((label, ctx -> path, sha256 hex), ...)
    messages: Messages = Messages()
    order: tuple = DEFAULT_ORDER
    period_dir: Callable = default_period_dir   # (dirs, period) -> the data dir the period reads

    def __post_init__(self):
        if not self.name or not self.tag:
            raise ValueError("a registered read needs a name and a file tag")
        unknown = [c for c in self.order if c not in CHECKS]
        if unknown or len(set(self.order)) != len(self.order):
            raise ValueError(f"{self.name}: order carries unknown or repeated checks {unknown or self.order}; known: {tuple(CHECKS)}")
        missing = [c for c in DEFAULT_ORDER if c not in self.order]
        if missing:
            raise ValueError(f"{self.name}: order drops the guard(s) {missing} - every check runs on every read; a read opts out of nothing")
        if self.order[0] != "print_pins":
            raise ValueError(f"{self.name}: print_pins runs first (it is the read-only helper that exits before any check)")
        pos = {c: n for n, c in enumerate(self.order)}
        broken = [f"{a} before {b}" for a, b in ORDER_RULES if pos[a] > pos[b]]
        if broken:
            raise ValueError(f"{self.name}: order breaks the driver's chain ({'; '.join(broken)}): {DEFAULT_ORDER}")
        if not callable(self.body) or not callable(self.prepare) or not callable(self.frozen) or not callable(self.outputs):
            raise ValueError(f"{self.name}: frozen / prepare / outputs / body are callables")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the driver
# ═════════════════════════════════════════════════════════════════════════════════════════════
def resolve(spec: RegisteredRead, args, rt) -> Ctx:
    data = Path(args.data)
    pre = getattr(args, "data_pre", None)
    dirs = {"cb702": data, "cb702_pre": Path(pre) if pre else data.parent / "cb702_pre"}
    period = getattr(args, "period", None) if spec.periods else None
    pdir = Path(spec.period_dir(dirs, period))
    out = Path(args.out) if getattr(args, "out", None) else pdir / "out"
    small = Path(args.small_out) if getattr(args, "small_out", None) else Path(rt.HERE) / "out"
    minutes = Path(args.minutes) if getattr(args, "minutes", None) else pdir / "minutes"
    prereg = getattr(args, "prereg", None)
    doc = (Path(prereg) if prereg else Path(rt.REPO) / "docs" / "analysis" / spec.doc) if spec.doc else None
    return Ctx(args=args, rt=rt, dirs=dirs, period=period, data=pdir, out=out, small=small, minutes=minutes, repo=Path(rt.REPO),
               here=Path(rt.HERE), workers=int(getattr(args, "workers", 1) or 1), doc=doc)


def _err(*lines) -> None:
    for ln in lines:
        print(ln, file=sys.stderr)


def _flag(dest: str) -> str:
    return "--" + dest.replace("_", "-")


def spec_source(spec: RegisteredRead) -> Path:
    """The file the read's body lives in - part of what the read rests on."""
    try:
        src = inspect.getsourcefile(inspect.unwrap(spec.body))
    except TypeError:
        src = None
    if not src:
        raise ValueError(f"{spec.name}: the body's source file cannot be determined (a partial / builtin / callable instance) - give the read a "
                         f"plain function so the module it lives in is pinned")
    return Path(src).resolve()


def frozen_map(spec: RegisteredRead, ctx: Ctx) -> dict:
    """The map the freeze and `--print-pins` use: `spec.frozen(ctx)` plus the code the driver pins by itself - the runner (`runner`), this
    scaffold (`scaffold`) and the body's own module when it is neither (`spec module`). A spec may carry those labels only at the same
    paths. A read with a registration doc and an empty map is refused at construction of the map (doc=None is the declared way)."""
    files = {k: Path(v) for k, v in spec.frozen(ctx).items()}
    if spec.doc is not None and not files:
        raise ValueError(f"{spec.name}: frozen(ctx) is empty - a read with a registration doc pins every artefact it rests on (doc=None "
                         f"declares that it has no freeze)")
    auto = {"runner": Path(ctx.rt.__file__).resolve(), "scaffold": Path(SCAFFOLD_PATH).resolve()}
    src = spec_source(spec)
    if src not in auto.values():
        auto["spec module"] = src
    for label, p in auto.items():
        have = files.get(label)
        if have is not None and have.resolve() != p:
            raise ValueError(f"{spec.name}: frozen label {label!r} points at {have}, not {p} - the driver pins that label itself")
        files[label] = p
    return files


def covers(files: dict, path) -> bool:
    """True when `path` is a pinned file or lies inside a pinned directory (a minute tree pin is `sha256_tree` over the directory)."""
    p = Path(path).resolve()
    for q in files.values():
        q = Path(q).resolve()
        if p == q or (p.is_relative_to(q) and q.is_dir()):
            return True
    return False


def _check_print_pins(spec, ctx, state):
    if not getattr(ctx.args, "print_pins", False):
        return None
    lines = ctx.rt.pin_lines(ctx.data, ctx.repo, files=frozen_map(spec, ctx))
    if spec.doc:
        lines.append(f"- doc body sha256: `{ctx.rt.doc_body_sha(ctx.doc.read_text(encoding='utf-8')) if ctx.doc.is_file() else 'MISSING'}`")
    print("\n".join(lines))
    return 0


def _check_period(spec, ctx, state):
    if spec.periods and ctx.period not in spec.periods:
        _err(spec.messages.period.format(periods=spec.periods, name=spec.name))
        return 2
    return None


def _check_prereg(spec, ctx, state):
    if spec.doc and getattr(ctx.args, "prereg", None) and not getattr(ctx.args, "dry_run", False):
        _err(spec.messages.prereg.format(doc=spec.doc, name=spec.name))
        return 2
    return None


def option_problems(spec: RegisteredRead, ctx: Ctx) -> list:
    """The option lines a refusal prints: every `spec.refused` option that is set, `--out` not the dir THIS PERIOD reads, `--small-out`
    not HERE/out, `--minutes` not the period's own tree (hard-coded: a spec that leaves `minutes` out of `refused` still cannot read
    another tree), and `--prereg` on a read that declares no freeze."""
    m = spec.messages
    bad = []
    for dest in spec.refused:
        val = getattr(ctx.args, dest, None)
        if val:
            bad.append(m.refused_option.format(option=_flag(dest) if isinstance(val, bool) else f"{_flag(dest)} {val}", name=spec.name))
    out = getattr(ctx.args, "out", None)
    if out and Path(out).resolve() != (ctx.data / "out").resolve():
        bad.append(m.out_elsewhere.format(out=out, expected=ctx.data / "out", period=ctx.period, name=spec.name))
    so = getattr(ctx.args, "small_out", None)
    if so and Path(so).resolve() != (ctx.here / "out").resolve():
        bad.append(m.small_out_elsewhere.format(small_out=so, expected=ctx.here / "out", name=spec.name))
    mi = getattr(ctx.args, "minutes", None)
    if mi and "minutes" not in spec.refused and Path(mi).resolve() != (ctx.data / "minutes").resolve():
        bad.append(m.minutes_elsewhere.format(minutes=mi, expected=ctx.data / "minutes", period=ctx.period, name=spec.name))
    if spec.doc is None and getattr(ctx.args, "prereg", None):
        bad.append(m.refused_option.format(option=f"--prereg {ctx.args.prereg}", name=spec.name) + " - this read declares no freeze")
    return bad


def _check_options(spec, ctx, state):
    bad = option_problems(spec, ctx)
    if bad:
        _err(spec.messages.options.format(name=spec.name), *(spec.messages.problem_line.format(problem=b) for b in bad))
        return 2
    return None


def _check_no_freeze_check(spec, ctx, state):
    if getattr(ctx.args, "no_freeze_check", False) and not getattr(ctx.args, "dry_run", False):
        _err(spec.messages.no_freeze_check.format(name=spec.name))
        return 2
    return None


def hard_pin_problem(spec: RegisteredRead, ctx: Ctx) -> "str | None":
    for label, path_of, want in spec.hard_pins:
        p = Path(path_of(ctx))
        if not p.is_file():
            return spec.messages.hard_pin_missing.format(label=label, path=p, name=spec.name)
        got = sha256_file(p)
        if got != want:
            return spec.messages.hard_pin_mismatch.format(label=label, got=got[:12], want=want[:12], file=p.name, name=spec.name)
    return None


def _check_hard_pins(spec, ctx, state):
    problem = hard_pin_problem(spec, ctx)
    if problem:
        _err(problem)
        return 2
    return None


def _check_freeze(spec, ctx, state):
    if getattr(ctx.args, "no_freeze_check", False) and not getattr(ctx.args, "dry_run", False):      # belt and braces: never skipped on a real run
        _err(spec.messages.no_freeze_check.format(name=spec.name))
        return 2
    if spec.doc is None:
        ctx.freeze = "NONE DECLARED"
        return None
    files = frozen_map(spec, ctx)
    if getattr(ctx.args, "no_freeze_check", False):
        ctx.freeze = "SKIPPED"
        return None
    problems = ctx.rt.freeze_check(doc=ctx.doc, data=ctx.data, repo=ctx.repo, files=files)
    if problems:
        _err(spec.messages.freeze.format(name=spec.name), *(spec.messages.problem_line.format(problem=p) for p in problems))
        return 2
    ctx.freeze = "passed"
    return None


def verdict_names(spec: RegisteredRead, ctx: Ctx) -> tuple:
    sfx = _suffix(spec, ctx)
    return f"{spec.tag}_verdict{sfx}.json", f"{spec.tag}_verdict{sfx}.txt"


def uncovered_inputs(spec: RegisteredRead, ctx: Ctx, prep: dict) -> list:
    """(what, path) of every input `prepare` named that the freeze map does not cover: the minute directory `inp` reads, the candidates
    file `path`, and each of `opens`."""
    files = frozen_map(spec, ctx)
    named = []
    if prep["inp"]:
        named.append(("the minute directory", Path(prep["inp"]["minutes_dir"])))
    if prep.get("path"):
        named.append(("the candidates file", Path(prep["path"])))
    named += [("an input the body opens,", Path(p)) for p in prep.get("opens", ())]
    return [(what, p) for what, p in named if not covers(files, p)]


def _check_prepare(spec, ctx, state):
    prep = spec.prepare(ctx)
    for key in ("rows", "inp"):
        if key not in prep:
            raise ValueError(f"{spec.name}: prepare must return {key!r} ({'the population' if key == 'rows' else 'minute_inputs, or None = no minute inputs'}) - "
                             f"a missing key is not a declaration")
    outputs = tuple(spec.outputs(ctx))
    if not outputs:
        raise ValueError(f"{spec.name}: outputs(ctx) is empty - a read declares the once-only table(s) it writes")
    state["prep"], state["outputs"] = prep, outputs
    if spec.doc is not None:
        bad = uncovered_inputs(spec, ctx, prep)
        if bad:
            _err(*(spec.messages.uncovered.format(name=spec.name, what=what, path=p) for what, p in bad))
            return 2
    vj, vt = verdict_names(spec, ctx)
    state["existing"] = ctx.rt.existing_outputs(ctx.out, outputs + (vj, vt)) + ctx.rt.existing_outputs(ctx.small, (vt,))
    return None


def _check_dry_run(spec, ctx, state):
    if getattr(ctx.args, "dry_run", False):
        print(spec.dry_run(ctx, state["prep"], state["existing"]))
        return 0
    return None


def _check_once_only(spec, ctx, state):
    existing = state["existing"]
    if not existing:
        return None
    per = spec.messages.per_period if spec.periods else ""
    crashed = [q for q in existing if q.name.endswith(".partial")]
    if crashed:
        _err(spec.messages.crashed.format(path=crashed[0], name=spec.name, per_period=per))
    else:
        _err(spec.messages.once.format(path=existing[0], name=spec.name, per_period=per))
    return 2


def _check_empty(spec, ctx, state):
    if not state["prep"]["rows"]:
        _err(spec.messages.empty.format(period=ctx.period, out=ctx.out, name=spec.name))
        return 2
    return None


def _check_missing_pairs(spec, ctx, state):
    inp = state["prep"]["inp"]
    if inp and (inp["missing"] or inp["lost"]):
        lost = spec.messages.lost_clause.format(lost=len(inp["lost"])) if inp["lost"] else ""
        _err(spec.messages.missing_pairs.format(missing=len(inp["missing"]), pairs=len(inp["pairs"]), done=Path(inp["minutes_dir"]) / "_done.psv",
                                                lost=lost, name=spec.name))
        return 2
    return None


CHECKS = {"print_pins": _check_print_pins, "period": _check_period, "prereg": _check_prereg, "options": _check_options,
          "no_freeze_check": _check_no_freeze_check, "hard_pins": _check_hard_pins, "freeze": _check_freeze, "prepare": _check_prepare,
          "dry_run": _check_dry_run, "once_only": _check_once_only, "empty": _check_empty, "missing_pairs": _check_missing_pairs}


def _suffix(spec: RegisteredRead, ctx: Ctx) -> str:
    return f"_{ctx.period}" if spec.periods else ""


def write_verdict(spec: RegisteredRead, ctx: Ctx, v: Verdict) -> tuple:
    """`<tag>_verdict<_period>.json` + `.txt` under out, the `.txt` under small - each through the `.partial` protocol, so a crash between
    them leaves a `.partial` the once-only guard refuses. Returns the two paths under out."""
    vj, vt = verdict_names(spec, ctx)
    with ctx.partial_write(vj) as fh:
        fh.write((json.dumps(v.data, indent=1) + "\n").encode("utf-8"))
    with ctx.partial_write(vt) as fh:
        fh.write(("\n".join(v.lines) + "\n").encode("utf-8"))
    with ctx.partial_write(vt, under=ctx.small) as fh:
        fh.write(("\n".join(v.lines) + "\n").encode("utf-8"))
    return ctx.out / vj, ctx.out / vt


def run_registered_read(spec: RegisteredRead, args, rt) -> int:
    """Run `spec` under `args` with the runner namespace `rt`. Returns the exit code (0 ok; 2 refused; 3 = the body's own check failed or
    the body returned nothing; whatever int the body returns)."""
    ctx = resolve(spec, args, rt)
    state: dict = {}
    for name in spec.order:
        rc = CHECKS[name](spec, ctx, state)
        if rc is not None:
            return rc
    want = "NONE DECLARED" if spec.doc is None else "passed"           # the last guard: whatever the order said, the body opens only after the freeze
    if ctx.freeze != want:
        _err(spec.messages.freeze_not_run.format(state=ctx.freeze, name=spec.name))
        return 2
    prep = state["prep"]
    ctx.out.mkdir(parents=True, exist_ok=True)
    ctx.small.mkdir(parents=True, exist_ok=True)
    inp = prep["inp"]
    pairs = f"{len(inp['pairs']):,} pairs all logged; " if inp else ""
    module = Path(rt.REPO) / rt.MODULE_REL
    ctx.say(f"{spec.name.upper()} (registered read #705): {('period ' + str(ctx.period) + '; ') if spec.periods else ''}"
            f"{len(prep['rows']):,} rows; {pairs}freeze check {ctx.freeze}; code: module sha256 "
            f"{sha256_file(module) if module.is_file() else 'MISSING'}, runner sha256 {sha256_file(Path(rt.__file__))}, scaffold sha256 "
            f"{sha256_file(SCAFFOLD_PATH)}")
    sfx = _suffix(spec, ctx)
    summary = ctx.small / f"{spec.tag}_summary{sfx}.txt"
    try:
        res = spec.body(ctx, prep, ctx.say)
        if isinstance(res, Verdict):
            vj, vt = write_verdict(spec, ctx, res)
            ctx.say(f"WROTE {vj}, {vt}, {ctx.small / vt.name}")
            rc = 0
        elif res is None:
            ctx.say(f"BODY RETURNED NOTHING: the {spec.name} returns a Verdict or an exit code - no verdict is written (the read's one run is spent)")
            rc = 3
        else:
            rc = int(res)
        ctx.say(f"WALL TIME: {time.time() - ctx.t0:.0f}s total")
    finally:
        summary.write_text("\n".join(ctx.log) + "\n")
    return rc
