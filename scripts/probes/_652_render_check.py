"""#652 — THE RENDERING CHECK: every real message body rendered BOTH ways.

For each body: (A) TODAY's path — chunk like `send_telegram_message`, parse each chunk with the
legacy-Markdown emulator, and on a 400 deliver what the real `_strip_markdown_markers` fallback
would; (B) the PROPOSED path — `md_to_html(body)`, chunk, parse each chunk with the HTML emulator,
and on a 400 deliver the HTML-branch plain fallback. Then compare what the operator would SEE:
plain text + entities, per chunk. Differences are characterised (and judged better / neutral /
worse for HTML), not just counted.

Corpus sources (all real, none invented — the one synthetic group says so in its name):
  * scripts/probes/_652_corpus_prod.jsonl  — captured ONCE from prod (read-only SQL, 2026-09-18):
      178 chunks Telegram REALLY 400'd (300-char heads + Telegram's verdict + byte offset),
      21 full weekly-review bodies, 165 real dynamic fields (judge decisions, anomaly details,
      grounded text, theme descriptions) tested raw and in the builder shapes that embed them
  * scripts/probes/_652_corpus_tests.jsonl — every body the test suite pushed through the sender,
      produced by the REAL builders on fixture data, attributed to the production call site
      (harvested ONCE by `_652_harvest_plugin.py`; override with `--tests PATH`)
  * skeletons — the message TEMPLATE of every default-Markdown site reconstructed from its AST
      (`_652_site_templates.py`), dynamic slots filled with underscore-bearing placeholders.
      Structure-only evidence for the 120 sites the harvest never reaches.
  * the acceptance case from #652's WOULD-FAIL-IF, verbatim, in four shapes
  * a deliberate hunt for what md_to_html's docstring warns about (pathological nesting):
      constructed cases, AND every real body is tagged when it carries the pattern

Modes:
  python scripts/probes/_652_render_check.py --validate            # v1 emulator vs 178 real verdicts
  python scripts/probes/_652_render_check.py [--tests PATH] [--show-diffs N]
Read-only: imports the real converter/stripper, changes nothing.
"""
from __future__ import annotations

import argparse
import csv
import html as _html
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _652_tg_parsers import Entity, TgParseError, fix_formatted_text, parse_html, parse_markdown_v1, render_markup  # noqa: E402
from _652_site_templates import skeletons  # noqa: E402
from shared.telegram_format import md_to_html  # noqa: E402
from agents.market_intelligence.briefing import _md_escape, _strip_markdown_markers  # noqa: E402

PROD_CORPUS = ROOT / "scripts/probes/_652_corpus_prod.jsonl"
TESTS_CORPUS = ROOT / "scripts/probes/_652_corpus_tests.jsonl"
CENSUS_TSV = ROOT / "scripts/probes/_652_call_sites.tsv"
ACCEPTANCE_SQL = "SELECT * FROM mi_live_trades WHERE stop_order_id IS NULL"
_IDENT_RE = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")

# tag -> (HTML verdict, plain-words meaning)
TAG_VERDICT = {
    "v1_bogus_span_bare_marker": ("BETTER", "v1 paired a bare `_`/`*` inside an identifier with one later: underscores eaten, a bogus italic/bold span (often across lines), anything inside it shown literally. HTML shows the text as written."),
    "html_keeps_brackets": ("BETTER", "v1 consumed `[…]` as a link attempt (brackets vanish; domain-like text becomes a link). HTML keeps them literal."),
    "html_renders_markup_v1_left_literal": ("BETTER", "v1 showed the markers literally (inside a bogus span); HTML renders the intended bold/italic/code."),
    "html_nested_markup": ("NEUTRAL+", "a `code` span or _italic_ inside *bold* (or vice versa): v1 cannot nest so showed the inner markers literally; HTML nests them."),
    "html_keeps_empty_marker_pair": ("NEUTRAL", "`**` / `__` — v1 drops both characters, HTML shows them."),
    "html_underscore_rule_line": ("NEUTRAL", "a `__________` separator line (SEC filing text): v1 deletes it, HTML shows the underscores italicised — both are garbage renderings of a rule; HTML keeps the characters."),
    "chunk_count_differs": ("NEUTRAL (hazard)", "the HTML text is longer (escapes + tags) and crossed the 4000-char split where the Markdown did not: arrives as more messages. A split inside <pre>/<b> would 400 both halves — none found, but the chunker is not tag-aware."),
    "html_pre_leading_newline": ("WORSE (cosmetic)", "the builder writes ```\\n…```; v1 skips that first newline, md_to_html keeps it, so the code block starts with a blank line. Fix belongs in md_to_html (mirror v1: drop one newline after the opening fence)."),
    "html_pre_leaks_fence_language_word": ("WORSE", "```sql … — v1 treats the word as a language tag; md_to_html prints it as the first line of the block. Zero occurrences in production code today."),
    "v1_deliberate_multiline_emphasis_html_literal": ("WORSE", "a *bold*/_italic_ written across a line break: v1 renders it, md_to_html's regexes stop at a newline and leave the markers literal."),
    "html_missed_emphasis": ("WORSE", "a word-bounded emphasis pair v1 renders that md_to_html's stricter regex did not match (e.g. a marker followed by a space)."),
    "html_400": ("WORSE (blocker)", "renders today, 400s under HTML — the flip would break it."),
    "text_other": ("CHECK", "a text difference not covered by the tags above — read the diff."),
}


# ── the sender's own chunker, copied verbatim (briefing.send_telegram_message) ──────────
def chunk_like_sender(text: str) -> list[str]:
    if len(text) <= 4000:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > 4000:
        split_at = remaining.rfind("\n\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


@dataclass
class ChunkResult:
    status: str            # "ok" | "400"
    error: str = ""
    text: str = ""         # plain text Telegram would show (after parse) — or the fallback text
    entities: list[Entity] = field(default_factory=list)


def legacy_path(body: str) -> list[ChunkResult]:
    out = []
    for chunk in chunk_like_sender(body):
        try:
            t, e = fix_formatted_text(*parse_markdown_v1(chunk))
            out.append(ChunkResult("ok", "", t, e))
        except TgParseError as ex:
            out.append(ChunkResult("400", ex.message, _strip_markdown_markers(chunk), []))
    return out


def html_path(body: str) -> list[ChunkResult]:
    out = []
    for chunk in chunk_like_sender(md_to_html(body)):
        try:
            t, e = fix_formatted_text(*parse_html(chunk))
            out.append(ChunkResult("ok", "", t, e))
        except TgParseError as ex:
            out.append(ChunkResult("400", ex.message, _html.unescape(re.sub(r"<[^>]+>", "", chunk)), []))
    return out


def _u16_slice(text: str, e: Entity) -> str:
    idx: list[int] = []
    for i, ch in enumerate(text):
        idx.append(i)
        if ord(ch) > 0xFFFF:
            idx.append(i)
    idx.append(len(text))
    s = idx[min(e.offset, len(idx) - 1)]
    t = idx[min(e.offset + e.length, len(idx) - 1)]
    return text[s:t]


def _first_diff(a: str, b: str, ctx: int = 40) -> str:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    if i == n and len(a) == len(b):
        return ""
    return f"legacy…{a[max(0, i - ctx):i + ctx]!r}  ⟷  html…{b[max(0, i - ctx):i + ctx]!r}"


@dataclass
class Verdict:
    kind: str                      # both_ok_identical | both_ok_differs | legacy_400_html_ok | html_400_legacy_ok | both_400 | empty_body
    tags: list[str]
    detail: str
    idents_lost_legacy: list[str]
    idents_lost_html: list[str]
    legacy: list[ChunkResult]
    html: list[ChunkResult]


def _deliberate_pair(body: str, s: str) -> bool:
    """Was `s` written as a word-bounded *s* / _s_ pair in the source body?"""
    return re.search(r"(?<!\w)([*_])" + re.escape(s) + r"\1(?!\w)", body) is not None


def compare(body: str) -> Verdict:
    if not body.strip():
        return Verdict("empty_body", [], "", [], [], [], [])
    L = legacy_path(body)
    H = html_path(body)
    l400 = any(c.status == "400" for c in L)
    h400 = any(c.status == "400" for c in H)
    tags: list[str] = []
    details: list[str] = []
    idents = set(_IDENT_RE.findall(body))
    l_text = "\n".join(c.text for c in L)
    h_text = "\n".join(c.text for c in H)
    lost_l = sorted(i for i in idents if i not in l_text)
    lost_h = sorted(i for i in idents if i not in h_text)
    if len(L) != len(H):
        tags.append("chunk_count_differs")
        details.append(f"chunks {len(L)}→{len(H)} (md {len(body)} chars, html {len(md_to_html(body))} chars)")
    if l400 and h400:
        kind = "both_400"
    elif l400:
        kind = "legacy_400_html_ok"
    elif h400:
        kind = "html_400_legacy_ok"
        tags.append("html_400")
        details.append("; ".join(c.error for c in H if c.status == "400"))
    else:
        same = len(L) == len(H) and all(a.text == b.text and a.entities == b.entities for a, b in zip(L, H))
        kind = "both_ok_identical" if same else "both_ok_differs"
    if kind != "both_ok_identical":
        for a, b in zip(L, H):
            if not (a.status == "ok" and b.status == "ok"):
                continue
            le = {(e.type, _u16_slice(a.text, e), e.arg) for e in a.entities}
            he = {(e.type, _u16_slice(b.text, e), e.arg) for e in b.entities}
            explained_text = False

            def _strip_markers(x: str) -> str:
                return re.sub(r"[`*_]", "", x)

            for t, s, arg in sorted(le - he):
                if t in ("bold", "italic"):
                    # HTML rendered the SAME span, only with the inner `code`/_italic_ nested rather
                    # than shown as literal markers (v1 cannot nest) → the entity text differs by
                    # exactly those marker characters
                    if any(ht == t and _strip_markers(hs) == _strip_markers(s) for ht, hs, _ in he):
                        tags.append("html_nested_markup")
                    elif _deliberate_pair(body, s):
                        tags.append("v1_deliberate_multiline_emphasis_html_literal" if "\n" in s else "html_missed_emphasis")
                    else:
                        tags.append("v1_bogus_span_bare_marker")
                        explained_text = True
                elif t == "pre" and arg:
                    tags.append("html_pre_leaks_fence_language_word")
                elif t == "text_url":
                    tags.append("html_keeps_brackets")
                    explained_text = True
                elif t in ("code", "pre"):
                    # v1 code span that HTML rendered differently: usually the span sat inside a
                    # bogus v1 italic (v1 has no nesting) — HTML nests it or shows it as written
                    tags.append("html_nested_markup")
                else:
                    tags.append(f"legacy_only_entity:{t}")
                details.append(f"legacy-only {t}({s[:60]!r})")
            for t, s, arg in sorted(he - le):
                if t == "pre" and s.startswith("\n"):
                    tags.append("html_pre_leading_newline")
                elif t == "pre" and any(lt == "pre" and ls in s for lt, ls, _ in le):
                    tags.append("html_pre_leaks_fence_language_word")
                elif t in ("italic", "bold") and s.strip("_* ") == "":
                    tags.append("html_underscore_rule_line")  # a "________" separator line
                elif t in ("italic", "bold", "code") and any(lt == t and _strip_markers(ls) == _strip_markers(s) for lt, ls, _ in le):
                    tags.append("html_nested_markup")
                elif t in ("italic", "bold", "code") and any(bt != t and s in bs for bt, bs, _ in he):
                    tags.append("html_nested_markup")
                elif t in ("italic", "bold", "code") and (f"*{s}*" in a.text or f"_{s}_" in a.text or f"`{s}`" in a.text):
                    tags.append("html_renders_markup_v1_left_literal")
                    explained_text = True
                elif t in ("italic", "bold", "code") and "v1_bogus_span_bare_marker" in tags:
                    # v1's bogus span shifted every later pairing (a backtick inside the bogus italic
                    # is literal, so the NEXT backtick opens the span): HTML pairs them as written
                    tags.append("html_renders_markup_v1_left_literal")
                    explained_text = True
                else:
                    tags.append(f"html_only_entity:{t}")
                details.append(f"html-only {t}({s[:60]!r})")
            if a.text != b.text:
                d = _first_diff(a.text, b.text)
                if b.text.count("[") > a.text.count("[") or b.text.count("]") > a.text.count("]"):
                    tags.append("html_keeps_brackets")
                    explained_text = True
                if ("**" in b.text and "**" not in a.text) or ("__" in b.text and "__" not in a.text):
                    tags.append("html_keeps_empty_marker_pair")
                    explained_text = True
                if _strip_markers(a.text) == _strip_markers(b.text):
                    explained_text = True  # same words; only marker characters differ (tagged above)
                if "html_pre_leading_newline" in tags and re.sub(r"\s+", "", a.text) == re.sub(r"\s+", "", b.text):
                    explained_text = True  # the only text change is that newline inside the block
                if not explained_text and not lost_l:
                    tags.append("text_other")
                details.append(d)
    return Verdict(kind, sorted(set(tags)), " | ".join(d for d in details if d)[:700], lost_l, lost_h, L, H)


# ── corpus loading ───────────────────────────────────────────────────────────────

def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_census() -> list[dict]:
    if not CENSUS_TSV.exists():
        return []
    with CENSUS_TSV.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def nearest_census_site(site: str | None, census_map: dict[str, str]) -> tuple[str | None, str | None]:
    """The harvest records the frame of the CALL; a multi-line call's lineno in AST is its first
    line while the frame may report a later line — match same file, nearest line at or before."""
    if not site:
        return None, None
    f, _, ln = site.rpartition(":")
    try:
        ln_i = int(ln)
    except ValueError:
        return None, None
    best = None
    for key, cls in census_map.items():
        kf, _, kl = key.rpartition(":")
        if kf == f:
            kl_i = int(kl)
            if kl_i <= ln_i and (best is None or kl_i > best[0]) and ln_i - kl_i <= 12:
                best = (kl_i, key, cls)
    return (best[1], best[2]) if best else (None, None)


# ── deliberate pathological cases (the docstring's warning, made concrete) ──────────
PATHOLOGICAL = [
    ("interleave: *a _b* c_ d_", "*a _b* c_ d_"),
    ("interleave in prose: *Verdict TRAIL_TIGHTEN* qty_ 3 shares_", "*Verdict TRAIL_TIGHTEN for OKTA* qty_ 3 shares_"),
    ("multi-line bold: *line1\\nline2*", "*Header line\nsecond line*"),
    ("multi-line italic: _a\\nb_", "_first\nsecond_"),
    ("fence with language tag", "```sql\nSELECT * FROM mi_live_trades WHERE stop_order_id IS NULL;\n```"),
    ("fence, no tag, leading newline", "```\nSELECT 1;\n```"),
    ("bare brackets [text]", "see [PLAN.md] for the task"),
    ("bracket with url", "see [the task](https://example.com/a_b) now"),
    ("empty link [](url)", "[](https://example.com) trailing"),
    ("bullet asterisk at line start", "* item one\n* item two"),
    ("nested emphasis *a _b_ c*", "*bold with _inner_ italic*"),
    ("dunder __init__", "module __init__ loaded"),
    ("arithmetic 5*3*2", "size 5*3*2 = 30"),
    ("url with underscores", "https://example.com/a_b_c?x_y=1"),
    ("v1 backslash escapes", "value \\_escaped\\_ and \\*star\\*"),
    ("html specials in prose", "AT&T <b>not a tag</b> 3 > 2 & 1 < 2"),
    ("empty bold **", "double ** star"),
    ("underscore in code span", "run `mi_live_trades` now"),
    ("html tag inside code span", "`<b>x</b>` literal"),
    ("odd underscore identifier", "TRAIL_TIGHTEN"),
    ("even underscores identifier", "ep_rt_sustain_reject"),
    ("bold then identifier then italic", "*Title* snake_case _italic_"),
    ("star inside bold span", "*a * b*"),
    ("code span spanning newline", "`a\nb`"),
    ("emoji + bold", "🟢 *MRNA — HOLD* +27.1%"),
    ("_md_escape'd rationale inside _italic_ (pre-#647 EP alert shape)", "*EP ALERT*\n   _" + _md_escape("game_changer over the floor's strong_read") + "_"),
]

ACCEPTANCE = [
    ("bare", ACCEPTANCE_SQL),
    ("in a ``` fence", f"Revert:\n```\n{ACCEPTANCE_SQL};\n```"),
    ("in a `code` span", f"Run `{ACCEPTANCE_SQL}` now"),
    ("under a *bold* header (the revert-page shape)", f"*CATALYST TIER MONITOR — revert*\n{ACCEPTANCE_SQL}"),
]


def _delivered(chunks: list[ChunkResult]) -> str:
    return "\n".join(c.text for c in chunks)


def _status(chunks: list[ChunkResult]) -> str:
    return "400→plain retry" if any(c.status == "400" for c in chunks) else "ok, 1st send"


def _markup(chunks: list[ChunkResult]) -> str:
    return " / ".join(render_markup(c.text, c.entities) if c.status == "ok" else f"400→{c.text!r}" for c in chunks)


# ── report ─────────────────────────────────────────────────────────────────────────

def run_validate(prod: list[dict]) -> None:
    fb = [r for r in prod if r["kind"] == "fallback_chunk"]
    inwin = exact = beyond = beyond_fail = 0
    mism = []
    for r in fb:
        chunk, off = r["body"], r["tg_byte_offset"]
        try:
            parse_markdown_v1(chunk)
            mine = None
        except TgParseError as e:
            mine = e.byte_offset
        blen = len(chunk.encode("utf-8"))
        if off is not None and off < blen:
            inwin += 1
            if mine == off:
                exact += 1
            else:
                mism.append((r["id"], off, mine, chunk[:60]))
        else:
            beyond += 1
            if mine is not None:
                beyond_fail += 1
    print("== v1 EMULATOR CREDENTIAL — against Telegram's own verdicts ==")
    print(f"real 400 rows: {len(fb)}; Telegram's byte offset falls inside the stored 300-char head on {inwin}")
    print(f"  exact byte-offset match: {exact} / {inwin}")
    print(f"  offset beyond the stored head: {beyond} (only 'an entity is still open at char 300' is decidable there; the emulator says so on {beyond_fail})")
    for m in mism[:10]:
        print("  MISMATCH", m)
    errs = Counter(re.sub(r"\d+", "N", r["verdict"]) for r in fb)
    print("  Telegram error kinds:", dict(errs))
    print("  HTML emulator: NO prod oracle exists (zero HTML 400s in 60 days) — validated against tdlib's rules only.")
    print()


def _grade_fields(detail: str) -> str:
    """The EP alert embeds the judge's prose, not the audit JSON: pull the prose fields."""
    try:
        d = json.loads(detail)
    except Exception:
        return detail[:280]
    parts = [str(d.get(k) or "") for k in ("judge_grade_reason", "judge_tier_reason", "rationale")]
    return " ".join(p for p in parts if p)[:280] or detail[:280]


def run_report(prod: list[dict], tests: list[dict], show_diffs: int) -> None:
    census = load_census()
    census_map = {f"{r['file']}:{r['line']}": r["class"] for r in census if r["is_test"] == "False"}
    print("== 1. ACCEPTANCE CASE (#652 WOULD-FAIL-IF), verbatim SQL in four shapes ==")
    print("   ('400→plain retry' = arrives only via the second, unformatted send; post-#647 the stripper keeps identifiers intact)")
    for label, body in ACCEPTANCE:
        v = compare(body)
        print(f"- {label}:")
        print(f"    TODAY : {_status(v.legacy):16s} underscores intact={not v.idents_lost_legacy}  sees: {_markup(v.legacy)!r}")
        print(f"    HTML  : {_status(v.html):16s} underscores intact={not v.idents_lost_html}  sees: {_markup(v.html)!r}")
    print()

    print("== 2. PATHOLOGICAL HUNT — constructed from md_to_html's own docstring warning ==")
    worse = []
    for label, body in PATHOLOGICAL:
        v = compare(body)
        flag = ""
        if v.kind == "html_400_legacy_ok":
            flag = "  ⛔ HTML WORSE (400 where legacy renders)"
            worse.append(label)
        elif any(TAG_VERDICT.get(t, ("",))[0].startswith("WORSE") for t in v.tags):
            flag = "  ⚠ HTML WORSE (renders, but loses something legacy showed)"
            worse.append(label)
        print(f"- {label}: {v.kind}{flag}")
        print(f"    legacy: {_markup(v.legacy)!r}")
        print(f"    html  : {_markup(v.html)!r}")
        if v.tags:
            print(f"    tags  : {v.tags}")
    print(f"\n  constructed cases where HTML is worse than today: {len(worse)} / {len(PATHOLOGICAL)} → {worse}")
    print()

    # ── real bodies ──
    print("== 3. REAL BODIES — every one rendered both ways ==")
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in prod:
        k = r["kind"]
        if k == "fallback_chunk":
            groups["prod: chunks Telegram REALLY 400'd (300-char heads)"].append((r["id"], r["body"]))
        elif k == "weekly_review":
            groups["prod: full weekly-review bodies (mi_system_reviews)"].append((r["id"], r["body"]))
        elif k.startswith("dyn:"):
            groups[f"prod dynamic field, raw: {k[4:]}"].append((r["id"], r["body"]))
            groups[f"prod dynamic field under a *bold* header: {k[4:]}"].append((r["id"] + "/hd", f"*ANOMALY [L2]*\n\n{r['body']}"))
            if k == "dyn:ep_grade_decision":
                groups["prod judge prose in the EP-alert italic shape `_{_md_escape(x)}_` (briefing.py:2561)"].append(
                    (r["id"] + "/it", f"*EP ALERT*\n   _{_md_escape(_grade_fields(r['body']))}_"))
    seen_bodies: set[str] = set()
    site_of_body: dict[str, str] = {}
    for r in tests:
        b = r["body"]
        if b in seen_bodies:
            continue
        seen_bodies.add(b)
        site_key, cls = nearest_census_site(r.get("site"), census_map)
        site_of_body[b] = f"{site_key or r.get('site') or r.get('site_any')} [{cls or 'unattributed'}]"
        if cls in ("explicit_html_md_to_html", "explicit_html_native"):
            groups["tests: bodies from EXPLICIT-HTML sites (already converted/native — flip must not double-convert)"].append((r["test"], b))
        elif cls == "explicit_markdown":
            groups["tests: bodies from EXPLICIT-Markdown sites (opt-in stays)"].append((r["test"], b))
        elif cls == "default_markdown":
            groups["tests: bodies from DEFAULT-Markdown production senders (THE FLIP POPULATION, real builder output)"].append((r["test"], b))
        else:
            groups["tests: bodies sent directly by a test (no production sender)"].append((r["test"], b))

    grand = Counter()
    grand_n = 0
    tag_examples: dict[str, list[str]] = defaultdict(list)
    tag_counts: Counter = Counter()
    html_worse_cases: list[tuple[str, str, Verdict, str]] = []
    for gname in sorted(groups):
        items = groups[gname]
        kinds = Counter()
        tags = Counter()
        lost_l = lost_h = 0
        for ident, body in items:
            v = compare(body)
            kinds[v.kind] += 1
            for t in v.tags:
                tags[t] += 1
                if not gname.startswith("tests: bodies from EXPLICIT-HTML"):
                    tag_counts[t] += 1
                    if len(tag_examples[t]) < 3:
                        tag_examples[t].append(f"{ident}: {v.detail[:160]}")
            lost_l += bool(v.idents_lost_legacy)
            lost_h += bool(v.idents_lost_html)
            if v.kind == "html_400_legacy_ok" or any(TAG_VERDICT.get(t, ("",))[0].startswith("WORSE") for t in v.tags):
                html_worse_cases.append((gname, ident if not str(ident).startswith("tests/") else site_of_body.get(body, ident), v, body))
            if not gname.startswith("tests: bodies from EXPLICIT-HTML") and v.kind != "empty_body":
                grand[v.kind] += 1
                grand_n += 1
        n = len(items)
        print(f"\n[{gname}]  n={n}")
        for k in ("both_ok_identical", "both_ok_differs", "legacy_400_html_ok", "html_400_legacy_ok", "both_400", "empty_body"):
            if kinds[k]:
                print(f"   {kinds[k]:4d} / {n}  {k}")
        print(f"   bodies where an identifier loses its underscores in what is DELIVERED — today: {lost_l} / {n}; HTML: {lost_h} / {n}")
        if tags:
            print("   difference tags:", ", ".join(f"{t}×{c}" for t, c in tags.most_common()))
        if gname.startswith("tests: bodies from EXPLICIT-HTML"):
            dbl = sum(1 for _, b in items if md_to_html(b) != b)
            print(f"   double-conversion check: md_to_html(body) != body on {dbl} / {n} — a flip that converts inside the sender MUST skip explicit-HTML callers")

    print("\n== 4. GRAND TOTAL over the flip-relevant REAL bodies (explicit-HTML group and empty bodies excluded) ==")
    for k in ("both_ok_identical", "both_ok_differs", "legacy_400_html_ok", "html_400_legacy_ok", "both_400"):
        print(f"   {grand[k]:4d} / {grand_n}  {k}")

    print("\n== 5. EVERY DIFFERENCE TAG, JUDGED (real bodies; count = bodies carrying it) ==")
    for t, c in tag_counts.most_common():
        verdict, meaning = TAG_VERDICT.get(t.split(":")[0], ("CHECK", t))
        print(f"   {c:4d}  {t:48s} HTML {verdict:18s} {meaning}")
        for ex in tag_examples[t][:2]:
            print(f"           e.g. {ex}")

    print(f"\n== 6. REAL BODIES WHERE HTML IS WORSE THAN TODAY: {len(html_worse_cases)} ==")
    for gname, ident, v, body in html_worse_cases[:show_diffs]:
        print(f"- [{gname}] {ident}: {v.kind} tags={[t for t in v.tags if TAG_VERDICT.get(t, ('',))[0].startswith('WORSE')]}")
        print(f"    {v.detail[:300]}")

    # ── coverage ──
    default_sites = {k for k, c in census_map.items() if c == "default_markdown"}
    covered = {nearest_census_site(r.get("site"), census_map)[0] for r in tests}
    covered_default = {s for s in covered if s in default_sites}
    print(f"\n== 7. COVERAGE — default-Markdown production call sites whose REAL output the harvest exercised: {len(covered_default)} / {len(default_sites)} ==")
    uncovered = sorted(default_sites - covered_default)
    by_file = Counter(s.rpartition(':')[0] for s in uncovered)
    print("   not exercised, by file:", ", ".join(f"{f.split('/')[-1]}×{n}" for f, n in by_file.most_common()))

    # ── skeletons ──
    rows = [r for r in census if r["is_test"] == "False" and r["class"] == "default_markdown"]
    sk = skeletons(rows)
    ok = [s for s in sk if s["reconstructible"]]
    print(f"\n== 8. TEMPLATE SKELETONS (synthetic values, real structure) for ALL default-Markdown sites: reconstructed {len(ok)} / {len(sk)} ==")
    kinds = Counter()
    sk_tags = Counter()
    sk_worse = []
    for s in ok:
        v = compare(s["skeleton"])
        kinds[v.kind] += 1
        for t in v.tags:
            sk_tags[t] += 1
        if v.kind == "html_400_legacy_ok" or any(TAG_VERDICT.get(t, ("",))[0].startswith("WORSE") for t in v.tags):
            sk_worse.append((f"{s['file']}:{s['line']}", s["func"], v))
    for k in ("both_ok_identical", "both_ok_differs", "legacy_400_html_ok", "html_400_legacy_ok", "both_400"):
        if kinds[k]:
            print(f"   {kinds[k]:4d} / {len(ok)}  {k}")
    print("   difference tags:", ", ".join(f"{t}×{c}" for t, c in sk_tags.most_common()))
    print(f"   sites whose TEMPLATE is worse under HTML: {len(sk_worse)}")
    for site, func, v in sk_worse:
        print(f"     - {site} ({func}): {v.kind} {[t for t in v.tags if TAG_VERDICT.get(t, ('',))[0].startswith('WORSE') or t == 'html_400']}  {v.detail[:200]}")
    not_rec = [s for s in sk if not s["reconstructible"]]
    print(f"   not reconstructible (body built by a helper / passed in): {len(not_rec)} → "
          + ", ".join(f"{s['file'].split('/')[-1]}:{s['line']}" for s in not_rec))

    # ── the leading-newline fence sites, named ──
    print("\n== 9. SITES THAT WRITE A FENCE AS ```\\n… (the one cosmetic regression) ==")
    hits = []
    for s in sk:
        if s["skeleton"] and re.search(r"```\n", s["skeleton"]):
            hits.append(f"{s['file'].split('/')[-1]}:{s['line']}")
    print(f"   {len(hits)} of {len(ok)} reconstructed default sites → {', '.join(hits)}")

    # ── the bogus-span class checked from the other side ──
    # A legitimately written `*bold*s` (marker glued to a word on ONE side) also fails
    # _deliberate_pair and would sit in the "HTML better" bucket while HTML actually leaves it
    # literal. So: for every bogus-tagged body, find each legacy-only emphasis whose OPENER looks
    # legitimate in the source (non-word before, non-space after, non-space before the closer) and
    # report whether the HTML rendering has an emphasis of that type covering the same words.
    print("\n== 10. BOGUS-SPAN CLASS, CHECKED FROM THE OTHER SIDE (could it hide an emphasis HTML missed?) ==")

    def _one_sided(items: list[tuple[str, str]], label: str) -> None:
        n_bogus = 0
        missed: list[tuple[str, str, str]] = []
        for ident, body in items:
            if not body.strip():
                continue
            v = compare(body)
            if "v1_bogus_span_bare_marker" not in v.tags:
                continue
            n_bogus += 1
            for a, b in zip(v.legacy, v.html):
                if a.status != "ok" or b.status != "ok":
                    continue
                for e in a.entities:
                    if e.type not in ("bold", "italic"):
                        continue
                    s = _u16_slice(a.text, e)
                    m = "*" if e.type == "bold" else "_"
                    pat = r"(?<!\w)" + re.escape(m) + r"(?!\s)" + re.escape(s) + r"(?<!\s)" + re.escape(m)
                    if "\n" in s or not re.search(pat, body):
                        continue
                    # what md_to_html would emphasise from that same opener
                    mm = re.search(r"(?<!\w)" + re.escape(m) + r"(?!\s)(.+?)(?<!\s)" + re.escape(m) + r"(?!\w)", body[body.find(m + s):] or "")
                    want = re.sub(r"[`*_]", "", mm.group(1)) if mm else re.sub(r"[`*_]", "", s)
                    rendered = any(he.type == e.type and re.sub(r"[`*_]", "", _u16_slice(b.text, he)) == want for he in b.entities)
                    literal_ok = (m + s) in b.text and "LIKE" in body  # a SQL LIKE pattern shown as written
                    if not rendered and not literal_ok:
                        missed.append((str(ident), e.type, s[:50]))
        print(f"   [{label}] bodies carrying a bogus span: {n_bogus}; deliberate emphasis HTML left literal: {len(missed)}")
        for x in missed[:15]:
            print("      ", x)

    real_items: list[tuple[str, str]] = []
    for gname, items in groups.items():
        if not gname.startswith("tests: bodies from EXPLICIT-HTML"):
            real_items.extend((str(i), b) for i, b in items)
    _one_sided(real_items, "real bodies")
    _one_sided([(f"{s['file']}:{s['line']}", s["skeleton"]) for s in ok], "templates")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--tests", default=str(TESTS_CORPUS))
    ap.add_argument("--show-diffs", type=int, default=25)
    a = ap.parse_args()
    prod = load_jsonl(PROD_CORPUS)
    tests = load_jsonl(Path(a.tests))
    print(f"corpus: prod items={len(prod)} (from {PROD_CORPUS.name}); test-harvest records={len(tests)} "
          f"(unique bodies={len({r['body'] for r in tests})}) from {a.tests}\n")
    if a.validate:
        run_validate(prod)
        return 0
    run_report(prod, tests, a.show_diffs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
