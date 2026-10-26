#!/usr/bin/env python3
"""#705 v2 re-run - the freeze record's diff rule (docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md, Freeze record; §12 F7), mechanical:
`git diff <registration commit> -- <doc>` ABOVE the freeze marker may touch only §5's (B2) cells and a G9 console reference; anything else refuses.

  - every removed / added line above the marker is either a §5 table row (same label, same old-file columns, only the two v2 columns changed from
    `(B2)` to counts), or a change inside §6's G9 bullet that only INSERTS words (every old word kept, in order) and whose inserted text names the
    console (`console` or `.console.txt`) - a G9 console reference, nothing else;
  - and the doc's §5 must now parse (v2_rerun_read.parse_section5: every v2 cell filled).

The BASE is not chosen at check time: `REG_BODY_SHA` pins the registered doc body (the sha256 of every byte above the marker, `runner.doc_body_sha`),
and the commit passed must be an ancestor of HEAD whose copy of the doc carries exactly that body - so a §7 edit committed later can never become
the base. (Not a hard-coded commit sha: the main loop makes the registration commit after this build, and the doc it commits must be
byte-identical above the marker to the body pinned here; a doc edit before that commit updates REG_BODY_SHA in the same commit.)

    python3 scripts/probes/_705_rerun_v2_1023/v2_freeze_diff_check.py REGISTRATION_COMMIT [DOC]    # exit 0 = the freeze may proceed; 2 = refuse
Reads git and the doc only.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.probes._cb_backtest import v2_rerun_read as v2  # noqa: E402

MARK = "<!-- FREEZE -->"
REG_BODY_SHA = "a53a26b874b6b8bf084dbc1b5f615bb24b7624488028e9a5622aa1ac4a91feea"   # the registered doc body (above the marker), 10-25 round 2


def body_sha(text: str) -> str:
    return hashlib.sha256(text.split(MARK, 1)[0].encode("utf-8")).hexdigest()


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def base_text(commit: str, rel: str) -> tuple:
    """(the doc's text at the registration commit, problems): the commit must exist, be an ancestor of HEAD, and carry the pinned body."""
    r = _git("rev-parse", "--verify", f"{commit}^{{commit}}")
    if r.returncode != 0:
        return None, [f"{commit!r} is not a commit"]
    full = r.stdout.strip()
    if _git("merge-base", "--is-ancestor", full, "HEAD").returncode != 0:
        return None, [f"{full[:12]} is not an ancestor of HEAD"]
    r = _git("show", f"{full}:{rel}")
    if r.returncode != 0:
        return None, [f"{full[:12]} carries no {rel}"]
    got = body_sha(r.stdout)
    if got != REG_BODY_SHA:
        return None, [f"{full[:12]} is not the registration commit: its doc body is {got[:12]}..., the registered body is {REG_BODY_SHA[:12]}... "
                      f"(the base is pinned, never chosen at check time)"]
    return r.stdout, []


def above(text: str) -> list:
    return text.split(MARK, 1)[0].splitlines()


def g9_span(lines: list) -> tuple:
    """(first, last) line index of §6's G9 bullet: from the line starting `- **G9` to the line before the next section heading."""
    s = next((k for k, ln in enumerate(lines) if ln.startswith("- **G9")), None)
    if s is None:
        return (-1, -1)
    e = next((k for k in range(s + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return (s, e - 1)


def g9_problems(old_lines: list, new_lines: list) -> list:
    """The G9 bullet may only GAIN words (a console reference): the old bullet's words survive in order, and the inserted words name the console."""
    import difflib
    import re
    tok = lambda lines: re.findall(r"\w+|[^\w\s]", " ".join(lines))          # words and punctuation apart: 'record.' -> 'record', '.'
    a, b = tok(old_lines), tok(new_lines)
    if a == b:
        return []
    ops = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    bad = [(tag, " ".join(a[i1:i2]), " ".join(b[j1:j2])) for tag, i1, i2, j1, j2 in ops if tag not in ("equal", "insert")]
    if bad:
        return [f"the G9 bullet lost or rewrote words (only an inserted console reference is allowed): {bad[:3]}"]
    ins = " ".join(" ".join(b[j1:j2]) for tag, _i1, _i2, j1, j2 in ops if tag == "insert")
    if "console" not in ins.split():
        return [f"the G9 bullet gained words that are not a console reference: {ins[:160]!r}"]
    return []


def problems(old_text: str, new_text: str) -> list:
    a, b = above(old_text), above(new_text)
    out = []
    if len(a) != len(b):
        if g9_span(a)[0] < 0 or g9_span(b)[0] < 0:
            return [f"the doc above the marker changed length ({len(a)} -> {len(b)} lines) and has no G9 bullet to absorb it"]
    labels = {lbl for lbl, _k in v2.S5_ROWS}
    ga, gb = g9_span(a), g9_span(b)
    pre_a, pre_b = a[:ga[0]] if ga[0] >= 0 else a, b[:gb[0]] if gb[0] >= 0 else b
    post_a, post_b = a[ga[1] + 1:] if ga[0] >= 0 else [], b[gb[1] + 1:] if gb[0] >= 0 else []
    if len(pre_a) != len(pre_b) or post_a != post_b:
        out.append("lines outside §5 and the G9 bullet were added, removed or edited after the G9 bullet")
    if ga[0] >= 0 and gb[0] >= 0:
        out += g9_problems(a[ga[0]:ga[1] + 1], b[gb[0]:gb[1] + 1])
    for k, (x, y) in enumerate(zip(pre_a, pre_b)):
        if x == y:
            continue
        cx = [c.strip() for c in x.strip().strip("|").split("|")] if x.startswith("|") else None
        cy = [c.strip() for c in y.strip().strip("|").split("|")] if y.startswith("|") else None
        if not (cx and cy and cx[0] in labels and cx[0] == cy[0] and len(cx) == len(cy) == 5):
            out.append(f"line {k + 1} changed and is not a §5 v2 row: {x[:100]!r} -> {y[:100]!r}")
            continue
        for col in (0, 1, 3):
            if cx[col] != cy[col]:
                out.append(f"§5 row {cx[0]!r}: column {col + 1} (not a v2 column) changed: {cx[col]!r} -> {cy[col]!r}")
        for col in (2, 4):
            if cx[col] != cy[col] and cx[col] != "(B2)":
                out.append(f"§5 row {cx[0]!r}: v2 column {col + 1} was {cx[col]!r}, not (B2) - only (B2) cells may be filled")
    try:
        v2.parse_section5(new_text)
    except v2.Refuse as exc:
        out.append(f"§5 does not parse: {exc}")
    return out


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a:
        print(__doc__, file=sys.stderr)
        return 2
    commit = a[0]
    doc = Path(a[1]) if len(a) > 1 else REPO / "docs" / "analysis" / v2.V2_DOC
    rel = doc.resolve().relative_to(REPO)
    old, pr = base_text(commit, rel.as_posix())
    if not pr:
        pr = problems(old, doc.read_text(encoding="utf-8"))
    for p in pr:
        print(f"REFUSED: {p}", file=sys.stderr)
    print("FREEZE DIFF CHECK: " + ("ok - above the marker only §5's (B2) cells and the G9 bullet changed since " + commit if not pr else f"{len(pr)} problem(s) - the freeze refuses"))
    return 2 if pr else 0


if __name__ == "__main__":
    sys.exit(main())
