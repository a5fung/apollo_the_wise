"""#121 — DERIVE every operator-facing Telegram send in agents/ core/ channels/ shared/.

WHY A DERIVATION AND NOT A LIST (derive-the-population-never-hand-list-it): the #121 migration
to the HTML layer was tracked for four months as "the remaining legacy-Markdown surfaces" and was
declared finished twice ("Remaining legacy surfaces after #652/#675: none") while ~15 sends in
`channels/telegram.py` and four raw Bot-API senders still carried `parse_mode=Markdown`. A hand
list is whatever the author remembered. This module walks the AST instead, so the question the
gate asks — "is there a send we did not look at" — has a decidable answer.

THE POPULATION (four classes, each found by structure, never by function name):

  1. `send_telegram_message(...)`  — the canonical sender. Converts legacy Markdown to HTML
     itself, so BOTH its default and an explicit "Markdown" are on the HTML layer.
  2. python-telegram-bot calls     — `.reply_text / .send_message / .edit_message_text / ...`.
     These send EXACTLY what they are given, so `parse_mode=ParseMode.MARKDOWN` is a real
     legacy-Markdown send.
  3. raw Bot-API HTTP              — any function that names `api.telegram.org/bot…/sendMessage`
     (or editMessageText / sendPhoto / …). Its parse mode is the `"parse_mode"` key of the
     payload it builds.
  4. SHELL senders                 — any non-comment line in a `*.sh` under infra/ or scripts/ that
     names `api.telegram.org/bot…/<method>` (`infra/ops_lib.sh::telegram_alert`, the curl behind
     every host-cron page: backup failed, service DOWN, disk HIGH, restore-check FAILED). It was
     INVISIBLE to the first three classes - the census read only Python - and kept
     `parse_mode=Markdown` after the Python senders were declared migrated. Its parse mode is the
     `parse_mode=<mode>` / `"parse_mode":"<mode>"` text in the same shell function.

WHAT COUNTS AS LEGACY MARKDOWN (the gate's failure condition, `markers_in`):
  * the string constant "Markdown" / "MarkdownV2" ANYWHERE, IN ANY CASE (a keyword value, a dict
    literal, a signature default, a positional `_post("Markdown")` — name-based scans miss the last
    two; Telegram matches parse_mode case-insensitively, and a case-sensitive scan waved
    `parse_mode="markdown"` through);
  * `parse_mode=Markdown` / `"parse_mode": "markdown"` in a shell script (`shell_markers_in`);
  * the attribute `ParseMode.MARKDOWN` / `MARKDOWN_V2`;
  * a `.reply_markdown(...)`-style call;
  * a PLAIN send (no parse_mode) whose literal text is built with Markdown syntax — it would
    show the reader literal `*` / backticks (`Site.detail == "markdown-syntax-in-plain-text"`).

Run it:  python scripts/telegram_send_census.py          (the table)
         python scripts/telegram_send_census.py --legacy (just the failures)
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOTS = ("agents", "core", "channels", "shared")

# python-telegram-bot send/edit methods (class 2). `send_telegram_message` is class 1.
PTB_SEND_ATTRS = frozenset({
    "reply_text", "send_message", "edit_message_text", "edit_text", "edit_message_caption",
    "reply_photo", "reply_document", "send_photo", "send_document",
})
PTB_MARKDOWN_METHODS = frozenset({"reply_markdown", "reply_markdown_v2"})
# Telegram matches parse_mode case-insensitively, so the scan does too: ALWAYS compare `.lower()`.
_MARKDOWN_CONSTANTS = frozenset({"markdown", "markdownv2"})
_MARKDOWN_ATTRS = frozenset({"MARKDOWN", "MARKDOWN_V2"})
_RAW_URL = re.compile(r"api\.telegram\.org/bot\{\}/(\w+)")
SHELL_ROOTS = ("infra", "scripts")
_SH_FUNC = re.compile(r"^\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\)\s*\{")
_SH_URL = re.compile(r"api\.telegram\.org/bot[^/\s\"']*/(\w+)")
# `parse_mode=Markdown` (curl --data-urlencode "parse_mode=Markdown", -d parse_mode=...) and the
# JSON spelling `"parse_mode":"Markdown"`; a `$VAR` / `${VAR}` value is captured whole (-> dynamic).
_SH_MODE = re.compile(r"parse_mode[\"']?\s*[=:]\s*[\"']?(\$?\{?\w+)", re.IGNORECASE)
# Markdown syntax in a STATIC string (placeholders from f-strings are replaced by "X" first so a
# `{name}` can neither create nor hide a marker).
_MD_SYNTAX = re.compile(
    r"(?<![\w*\\])\*[^\s*][^*\n]*\*(?![\w*])"        # *bold*
    r"|`[^`\n]+`"                                     # `code`
    r"|(?<![\w\\])_[^\s_][^_\n]*_(?![\w])"           # _italic_
)


# path::qualified-function -> WHY this spelling of "Markdown" is not a legacy-Markdown send.
# ONE copy, read by both the CLI (`--legacy`) and the gate test, so they cannot disagree.
ALLOWED_MARKDOWN_SPELLINGS: dict[str, str] = {
    "agents/market_intelligence/briefing.py::send_telegram_message": (
        "`parse_mode == \"Markdown\"` is the COMPARISON that FOLDS an explicit Markdown request "
        "into the converting path (#675) — the body is run through md_to_html and sent as HTML. "
        "Nothing is sent with the legacy parse mode."),
}

# Plain sends deliberately built with Markdown syntax. Empty on purpose: there are none today.
ALLOWED_PLAIN_WITH_MARKDOWN: dict[str, str] = {}


@dataclass(frozen=True)
class Site:
    path: str            # repo-relative
    func: str            # qualified: Class.method / function / <module>
    line: int
    kind: str            # "send_telegram_message" | "ptb:<attr>" | "raw:<method>"
    mode: str            # html | converted-default | converted-explicit | plain | legacy-markdown | dynamic
    detail: str = ""

    @property
    def key(self) -> str:
        return f"{self.path}::{self.func}"


def _py_files():
    for root in ROOTS:
        yield from sorted((REPO / root).rglob("*.py"))


def _qualname_map(tree: ast.AST) -> dict[ast.AST, str]:
    """node -> qualified name of the INNERMOST enclosing function/class chain
    (`Class.method`, `outer.inner`)."""
    out: dict[ast.AST, str] = {}

    def walk(node: ast.AST, stack: list[str]):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, stack + [child.name])
            else:
                if stack:
                    out[child] = ".".join(stack)
                walk(child, stack)

    walk(tree, [])
    return out


def _func_of(node: ast.AST, qn: dict[ast.AST, str]) -> str:
    return qn.get(node, "<module>")


def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _static_text(node: ast.AST) -> str | None:
    """The literal text of an expression, with every dynamic part replaced by "X"; None when it
    has no static text at all (a bare name / call)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            parts.append(v.value if isinstance(v, ast.Constant) else "X")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        l, r = _static_text(node.left), _static_text(node.right)
        if l is None and r is None:
            return None
        return (l if l is not None else "X") + (r if r is not None else "X")
    return None


def _classify_mode_expr(node: ast.AST | None) -> str:
    """parse_mode value expression -> mode label."""
    if node is None:
        return "default"
    s = _const_str(node)
    if s is not None:
        if s.lower() in _MARKDOWN_CONSTANTS:
            return "legacy-markdown"
        return "html" if s.upper() == "HTML" else f"other:{s}"
    if isinstance(node, ast.Constant) and node.value is None:
        return "plain-explicit"
    if isinstance(node, ast.Attribute):
        if node.attr in _MARKDOWN_ATTRS:
            return "legacy-markdown"
        if node.attr == "HTML":
            return "html"
    return "dynamic"


def sites_in(rel: str, text: str) -> list[Site]:
    """Every send site in ONE source file (text in, so a test can feed synthetic code)."""
    sites: list[Site] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return sites
    qn = _qualname_map(tree)

    # raw senders: per FUNCTION, find the URL and the payload's parse_mode evidence
    raw_url_by_func: dict[str, list[tuple[int, str]]] = {}
    mode_evidence: dict[str, list[str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            shape = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
            m = _RAW_URL.search(shape)
            if m:
                raw_url_by_func.setdefault(_func_of(n, qn), []).append((n.lineno, m.group(1)))
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if _const_str(k) == "parse_mode":
                    mode_evidence.setdefault(_func_of(n, qn), []).append(_classify_mode_expr(v))
        if (isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store)
                and _const_str(n.slice) == "parse_mode"):
            mode_evidence.setdefault(_func_of(n, qn), []).append("dynamic")
    for func, urls in raw_url_by_func.items():
        for line, method in urls:
            ev = mode_evidence.get(func, [])
            if method not in ("sendMessage", "editMessageText"):
                mode = "n/a (media)"        # sendPhoto & co: caption only, plain by design
            elif not ev:
                mode = "plain"
            elif "legacy-markdown" in ev:
                mode = "legacy-markdown"
            elif all(e == "html" for e in ev):
                mode = "html"
            else:
                mode = "dynamic"
            sites.append(Site(rel, func, line, f"raw:{method}", mode))

    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        if name is None:
            continue
        kws = {k.arg: k.value for k in n.keywords if k.arg}
        func = _func_of(n, qn)
        if name == "send_telegram_message":
            if "parse_mode" not in kws:
                mode = "converted-default"
            else:
                m = _classify_mode_expr(kws["parse_mode"])
                mode = {"legacy-markdown": "converted-explicit", "html": "html"}.get(m, m)
            sites.append(Site(rel, func, n.lineno, "send_telegram_message", mode))
        elif isinstance(f, ast.Attribute) and name in PTB_MARKDOWN_METHODS:
            sites.append(Site(rel, func, n.lineno, f"ptb:{name}", "legacy-markdown"))
        elif isinstance(f, ast.Attribute) and name in PTB_SEND_ATTRS:
            mode = _classify_mode_expr(kws.get("parse_mode")) if "parse_mode" in kws else "plain"
            detail = ""
            if mode == "plain":
                text_node = kws.get("text") or (n.args[0] if n.args else None)
                # send_message(chat_id, text) -> the text is the 2nd positional
                if name == "send_message" and "text" not in kws and len(n.args) >= 2:
                    text_node = n.args[1]
                st = _static_text(text_node) if text_node is not None else None
                if st is not None and _MD_SYNTAX.search(st):
                    detail = "markdown-syntax-in-plain-text"
            sites.append(Site(rel, func, n.lineno, f"ptb:{name}", mode, detail))
    return sites


def markers_in(rel: str, text: str) -> list[tuple[str, str, int, str]]:
    """Every place the legacy Markdown PARSE MODE is spelled in ONE source file —
    (path, func, line, what). Independent of `sites_in()`: it looks at the constants and
    attributes themselves, so a send the census failed to classify (a positional arg, a
    signature default, a dict literal) is still caught."""
    out: list[tuple[str, str, int, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    qn = _qualname_map(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.lower() in _MARKDOWN_CONSTANTS:
            out.append((rel, _func_of(n, qn), n.lineno, f'"{n.value}"'))
        elif isinstance(n, ast.Attribute) and n.attr in _MARKDOWN_ATTRS:
            out.append((rel, _func_of(n, qn), n.lineno, f".{n.attr}"))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in PTB_MARKDOWN_METHODS:
            out.append((rel, _func_of(n, qn), n.lineno, f".{n.func.attr}()"))
    return out


def _sh_files():
    for root in SHELL_ROOTS:
        yield from sorted((REPO / root).rglob("*.sh"))


def _sh_lines(text: str):
    """(lineno, enclosing shell function, line) for every NON-COMMENT line. A function ends at a
    column-0 `}`; outside one the name is `<script>`."""
    func = "<script>"
    for no, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = _SH_FUNC.match(line)
        if m:
            func = m.group(1)
        yield no, func, line
        if line.startswith("}"):
            func = "<script>"


def shell_sites_in(rel: str, text: str) -> list[Site]:
    """Every shell send site in ONE `.sh` file: a non-comment line naming
    `api.telegram.org/bot<token>/<method>`. Its mode is read off the `parse_mode=` text of the SAME
    shell function (an absent parse_mode = plain, a `$VAR` = dynamic) - the curl behind
    `infra/ops_lib.sh::telegram_alert` is what this exists to see."""
    lines = list(_sh_lines(text))
    evidence: dict[str, list[str]] = {}
    for _no, func, line in lines:
        for m in _SH_MODE.finditer(line):
            v = m.group(1)
            label = ("dynamic" if v.startswith("$") else
                     "legacy-markdown" if v.lower() in _MARKDOWN_CONSTANTS else
                     "html" if v.upper() == "HTML" else f"other:{v}")
            evidence.setdefault(func, []).append(label)
    sites: list[Site] = []
    for no, func, line in lines:
        for m in _SH_URL.finditer(line):
            method, ev = m.group(1), evidence.get(func, [])
            if method not in ("sendMessage", "editMessageText"):
                mode = "n/a (media)"
            elif not ev:
                mode = "plain"
            elif "legacy-markdown" in ev:
                mode = "legacy-markdown"
            elif all(e == "html" for e in ev):
                mode = "html"
            else:
                mode = "dynamic"
            sites.append(Site(rel, func, no, f"shell:{method}", mode))
    return sites


def shell_markers_in(rel: str, text: str) -> list[tuple[str, str, int, str]]:
    """Every place a shell script spells the legacy Markdown parse mode - (path, func, line, what),
    case-insensitive, comment lines skipped. Independent of `shell_sites_in`: a sender whose URL is
    assembled from a variable still shows up here."""
    out: list[tuple[str, str, int, str]] = []
    for no, func, line in _sh_lines(text):
        for m in _SH_MODE.finditer(line):
            if m.group(1).lower() in _MARKDOWN_CONSTANTS:
                out.append((rel, func, no, f"parse_mode={m.group(1)}"))
    return out


def census() -> list[Site]:
    out: list[Site] = []
    for p in _py_files():
        out.extend(sites_in(str(p.relative_to(REPO)), p.read_text(encoding="utf-8", errors="replace")))
    for p in _sh_files():
        out.extend(shell_sites_in(str(p.relative_to(REPO)), p.read_text(encoding="utf-8", errors="replace")))
    return out


def legacy_markdown_markers() -> list[tuple[str, str, int, str]]:
    out: list[tuple[str, str, int, str]] = []
    for p in _py_files():
        out.extend(markers_in(str(p.relative_to(REPO)), p.read_text(encoding="utf-8", errors="replace")))
    for p in _sh_files():
        out.extend(shell_markers_in(str(p.relative_to(REPO)), p.read_text(encoding="utf-8", errors="replace")))
    return out


def unallowed(markers: list[tuple[str, str, int, str]]) -> list[tuple[str, str, int, str]]:
    """The gate's failure set: markers NOT excused by ALLOWED_MARKDOWN_SPELLINGS. ONE function, read
    by the CLI (`--legacy`) and by the gate test (which also feeds it synthetic markers to show it
    can fail)."""
    return [m for m in markers if f"{m[0]}::{m[1]}" not in ALLOWED_MARKDOWN_SPELLINGS]


def plain_sends_with_markdown_syntax() -> list[Site]:
    return [s for s in census() if s.detail == "markdown-syntax-in-plain-text"]


def _main(argv: list[str]) -> int:
    if "--legacy" in argv:
        # the gate's failure set: everything NOT on an allowlist (exit 1 iff non-empty)
        bad = unallowed(legacy_markdown_markers())
        plain = [s for s in plain_sends_with_markdown_syntax() if s.key not in ALLOWED_PLAIN_WITH_MARKDOWN]
        for path, func, line, what in bad:
            print(f"{path}:{line}  {func}  {what}")
        for s in plain:
            print(f"{s.path}:{s.line}  {s.func}  {s.kind}  {s.detail}")
        return 1 if (bad or plain) else 0
    rows = census()
    by_mode: dict[tuple[str, str], int] = {}
    for s in rows:
        k = (s.kind.split(":")[0], s.mode)
        by_mode[k] = by_mode.get(k, 0) + 1
    print(f"{len(rows)} sends in {', '.join(ROOTS)} + shell {', '.join(SHELL_ROOTS)}/**/*.sh")
    for (kind, mode), n in sorted(by_mode.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:4d}  {kind:22s} {mode}")
    if "--all" in argv:
        for s in sorted(rows, key=lambda s: (s.path, s.line)):
            print(f"{s.path}:{s.line}\t{s.func}\t{s.kind}\t{s.mode}\t{s.detail}")
    else:
        print("\nnot on the converted/HTML default (path:line  func  kind  mode):")
        for s in sorted(rows, key=lambda s: (s.path, s.line)):
            if s.mode not in ("converted-default", "html"):
                print(f"  {s.path}:{s.line}  {s.func}  {s.kind}  {s.mode} {s.detail}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
