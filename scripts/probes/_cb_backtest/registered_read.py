"""#705 (a) - the shared 'registered read' scaffold for scripts/probes/_cb_backtest/runner.py (built 2026-10-24, synthetic tests only).

Four one-run reads were built by copying the same plumbing four times (`holdout`, `pre-read`, `h60-read`, `exit-read`): a freeze map
+ `--print-pins`, a once-only guard with the `.partial` protocol, option refusals, `--dry-run`, a verdict file. The copies drifted:
`h60-read --out` was checked against cb702/out but the pre period READ cb702_pre/out; `exit-read` ignored `--out`; the pre-read had no
freeze at all. This module is ONE driver for every read registered after it. The four finished reads are NOT migrated (their freeze
records pin the runner that ran them); they stay as they are, byte for byte (tests/test_cb_backtest_golden.py).

    spec = RegisteredRead(name="quality-read", tag="quality", doc="cb_quality_prereg_2026-10-24.md", frozen=..., prepare=..., outputs=...,
                          dry_run=..., body=..., periods=("discovery", "pre", "holdout"), hard_pins=(("module", module_path, SHA),))
    runner.REGISTERED_READS[spec.name] = spec          # main() dispatches it; `run_registered_read(spec, args)` runs it

The driver (`run_registered_read`) resolves data / out / small / minutes / period ONCE into a `Ctx` and runs the checks in `spec.order`:
  print_pins       `--print-pins`: the footer lines of `spec.frozen(ctx)` (+ the doc-body line) and exit 0 - before anything else
  period           `--period` required and one of `spec.periods` (when the read has periods)
  prereg           `--prereg` only with `--print-pins` / `--dry-run` (a real run pins the doc under docs/analysis itself)
  options          every `spec.refused` option; `--out` against THE DIR THE PERIOD READS (`ctx.data / "out"`); `--small-out` against HERE/out
  no_freeze_check  `--no-freeze-check` only together with `--dry-run`
  hard_pins        the registration's hard pins (e.g. the module sha): footer or no footer, even on a dry run
  freeze           `freeze_check` on the registration doc's footer against `spec.frozen(ctx)` - BEFORE any input file is opened; a read
                   that declares `doc=None` has NO freeze and its run log says so (an omission is not a declaration)
  prepare          `spec.prepare(ctx)` - the population and its minute inputs (opens no daily bar and no minute row); the once-only scan
  dry_run          `--dry-run`: `spec.dry_run(ctx, prep, existing)` printed, exit 0, nothing written
  once_only        a final output or a crashed run's `.partial` on disk refuses (the operator removes a `.partial` by hand)
  empty            no row in the population refuses
  missing_pairs    a (date, ticker) pair not logged in `_done.psv` (or logged ok with no file) refuses - a partial read is never run
then `spec.body(ctx, prep, say)`: a `Verdict` is written by the driver as `<tag>_verdict_<period>.json` + `.txt` (out) and `.txt` (small);
an int is the exit code (3 = a check inside the read failed; the driver writes nothing more). The run log goes to `<tag>_summary_<period>.txt`.
Every refusal prints to stderr and returns 2. The refusal texts are `spec.messages` templates, printed verbatim (`str.format` fields only).

Speed / memory helpers for the next reads (not retrofitted into the finished stages - a cache hit would change their printed lines):
`sha256_file` (streaming, the identical digest), `load_daily_cached` (one slot keyed by path / size / mtime: the pre-read loaded the
export twice, the exit read too), `read_watch_index` (the watch table by `usecols` + explicit dtypes in chunks - the h60 read's
`h60_watch_index` reads it whole through type inference; the values are proved identical in the tests).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

# ═════════════════════════════════════════════════════════════════════════════════════════════
# speed / memory helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def sha256_file(p) -> str:
    """sha256 of a file, streamed (`hashlib.file_digest`): the identical digest without reading the file whole."""
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


_DAILY_SLOT: dict = {}                      # the single slot: {"key": (resolved path, size, mtime_ns), "value": the loaded export}


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
    period: str = "REFUSED: --period is required: one of {periods}"
    prereg: str = "REFUSED: --prereg is honoured only with --print-pins or --dry-run - the read pins the registration doc at docs/analysis/{doc} itself"
    no_freeze_check: str = "REFUSED: --no-freeze-check is honoured only together with --dry-run"
    hard_pin_missing: str = "REFUSED: {label} missing: {path}"
    hard_pin_mismatch: str = "REFUSED: {label} sha256 {got}... is not the registered {want}... - {file} was edited; the read does not open"
    freeze: str = "REFUSED: the freeze check failed - the read is not opened:"
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
    def partial_write(self, name: str):
        """Open `<out>/<name>.partial` for bytes; renamed to `<name>` only on a clean exit (a crash leaves the `.partial` the once-only
        guard refuses until the operator removes it)."""
        final = self.out / name
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


@dataclass(frozen=True)
class RegisteredRead:
    name: str                                   # the CLI stage name
    tag: str                                    # the file tag: trades_<period>_<tag>.tsv.gz, <tag>_verdict_<period>.*, <tag>_summary_<period>.txt
    doc: "str | None"                           # the registration doc under docs/analysis; None = the read DECLARES it has no freeze
    frozen: Callable                            # ctx -> {footer label: path}: every artefact the read rests on
    prepare: Callable                           # ctx -> {"rows": [...], "inp": the minute_inputs shape (or None), ...}; opens no bar / minute
    outputs: Callable                           # ctx -> the once-only file names under ctx.out (the driver adds `.partial`)
    dry_run: Callable                           # (ctx, prep, existing) -> the DRY RUN line
    body: Callable                              # (ctx, prep, say) -> Verdict | int
    periods: tuple = ()                         # () = no --period
    refused: tuple = REFUSED_DEFAULT            # argparse dests a run may not carry
    hard_pins: tuple = ()                       # ((label, ctx -> path, sha256 hex), ...)
    pins_doc_body: bool = True
    messages: Messages = Messages()
    order: tuple = DEFAULT_ORDER
    period_dir: Callable = default_period_dir   # (dirs, period) -> the data dir the period reads

    def __post_init__(self):
        if not self.name or not self.tag:
            raise ValueError("a registered read needs a name and a file tag")
        unknown = [c for c in self.order if c not in CHECKS]
        if unknown or len(set(self.order)) != len(self.order):
            raise ValueError(f"{self.name}: order carries unknown or repeated checks {unknown or self.order}; known: {tuple(CHECKS)}")
        needs_prep = [c for c in ("dry_run", "once_only", "empty", "missing_pairs") if c in self.order]
        if needs_prep and ("prepare" not in self.order or any(self.order.index(c) < self.order.index("prepare") for c in needs_prep)):
            raise ValueError(f"{self.name}: dry_run / once_only / empty / missing_pairs need `prepare` before them")
        if "freeze" in self.order and "prepare" in self.order and self.order.index("freeze") > self.order.index("prepare"):
            raise ValueError(f"{self.name}: the freeze check must run BEFORE prepare opens a file")


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


def _check_print_pins(spec, ctx, state):
    if not getattr(ctx.args, "print_pins", False):
        return None
    lines = ctx.rt.pin_lines(ctx.data, ctx.repo, files=spec.frozen(ctx))
    if spec.doc and spec.pins_doc_body:
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
    not HERE/out, and `--prereg` on a read that declares no freeze."""
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
    if spec.doc is None:
        ctx.freeze = "NONE DECLARED"
        return None
    if getattr(ctx.args, "no_freeze_check", False):
        ctx.freeze = "SKIPPED"
        return None
    problems = ctx.rt.freeze_check(doc=ctx.doc, data=ctx.data, repo=ctx.repo, files=spec.frozen(ctx))
    if problems:
        _err(spec.messages.freeze.format(name=spec.name), *(spec.messages.problem_line.format(problem=p) for p in problems))
        return 2
    ctx.freeze = "passed"
    return None


def _check_prepare(spec, ctx, state):
    state["prep"] = spec.prepare(ctx)
    state["existing"] = ctx.rt.existing_outputs(ctx.out, tuple(spec.outputs(ctx)))
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
    if not state["prep"].get("rows"):
        _err(spec.messages.empty.format(period=ctx.period, out=ctx.out, name=spec.name))
        return 2
    return None


def _check_missing_pairs(spec, ctx, state):
    inp = state["prep"].get("inp")
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
    """`<tag>_verdict<_period>.json` + `.txt` under out, the `.txt` under small. Returns the two paths under out."""
    sfx = _suffix(spec, ctx)
    vj, vt = ctx.out / f"{spec.tag}_verdict{sfx}.json", ctx.out / f"{spec.tag}_verdict{sfx}.txt"
    vj.write_text(json.dumps(v.data, indent=1) + "\n")
    text = "\n".join(v.lines) + "\n"
    vt.write_text(text)
    (ctx.small / f"{spec.tag}_verdict{sfx}.txt").write_text(text)
    return vj, vt


def run_registered_read(spec: RegisteredRead, args, rt) -> int:
    """Run `spec` under `args` with the runner namespace `rt`. Returns the exit code (0 ok; 2 refused; 3 = the body's own check failed;
    whatever int the body returns)."""
    ctx = resolve(spec, args, rt)
    state: dict = {}
    for name in spec.order:
        rc = CHECKS[name](spec, ctx, state)
        if rc is not None:
            return rc
    prep = state.get("prep") or {}
    ctx.out.mkdir(parents=True, exist_ok=True)
    ctx.small.mkdir(parents=True, exist_ok=True)
    inp = prep.get("inp")
    pairs = f"{len(inp['pairs']):,} pairs all logged; " if inp else ""
    ctx.say(f"{spec.name.upper()} (registered read #705): {('period ' + str(ctx.period) + '; ') if spec.periods else ''}"
            f"{len(prep.get('rows') or []):,} rows; {pairs}freeze check {ctx.freeze}; code: module sha256 "
            f"{sha256_file(Path(rt.REPO) / rt.MODULE_REL) if (Path(rt.REPO) / rt.MODULE_REL).is_file() else 'MISSING'}, runner sha256 "
            f"{sha256_file(Path(rt.__file__))}")
    sfx = _suffix(spec, ctx)
    summary = ctx.small / f"{spec.tag}_summary{sfx}.txt"
    try:
        res = spec.body(ctx, prep, ctx.say)
        if isinstance(res, Verdict):
            vj, vt = write_verdict(spec, ctx, res)
            ctx.say(f"WROTE {vj}, {vt}, {ctx.small / vt.name}")
            rc = 0
        else:
            rc = int(res or 0)
        ctx.say(f"WALL TIME: {time.time() - ctx.t0:.0f}s total")
    finally:
        summary.write_text("\n".join(ctx.log) + "\n")
    return rc
