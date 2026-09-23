"""#652 — turn the ONE read-only prod capture into corpus JSONL (capture once, read many).

Input: the psql dump written by `_652_capture.sql` (sections separated by ===NAME=== lines,
rows tab-separated, newlines/tabs escaped as \\n / \\t). Output: one JSON object per line
with {"id", "source", "site", "kind", "body"} where `kind` is:
  * fallback_chunk   — the first 300 chars of a chunk Telegram REALLY 400'd (+ its verdict)
  * weekly_review    — a full stored weekly-review body (mi_system_reviews.summary)
  * dyn:<event>      — a REAL dynamic field builders embed (judge rationale, anomaly detail,
                       grounded text, theme description); tested standalone AND wrapped in the
                       shape the builder gives it
Run:  python scripts/probes/_652_build_prod_corpus.py /tmp/652_capture_out.tsv scripts/probes/_652_corpus_prod.jsonl
"""
from __future__ import annotations

import json
import re
import sys


def _unescape(s: str) -> str:
    # psql wrote each REAL newline/tab as the 3-char sequence backslash-backslash-n (a '...'
    # literal keeps backslashes under standard_conforming_strings). A single backslash-n is a
    # repr() escape inside the offset_snippet and must be left for literal_eval.
    return s.replace("\\\\n", "\n").replace("\\\\t", "\t")


def _snippet(raw: str) -> str:
    import ast
    try:
        return ast.literal_eval(raw)
    except Exception:
        return raw


def main(src: str, dst: str) -> int:
    sec = None
    out: list[dict] = []
    for raw in open(src, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("==="):
            sec = line.strip("=")
            continue
        if not line.strip() or sec is None or sec == "EPALERT_COLS":
            continue
        parts = line.split("\t")
        if sec == "FALLBACK_ROWS":
            rid, ts, detail = parts[0], parts[1], "\t".join(parts[2:])
            m = re.search(r"md_body=(.*?) \| offset_snippet=(.*) \| chunk=(.*)$", detail, re.S)
            if not m:
                m2 = re.search(r"first_chunk=(.*)$", detail, re.S)
                if m2:
                    out.append({"id": f"fb{rid}", "source": f"mi_audit_log telegram_send_failed {ts[:10]}",
                                "site": None, "kind": "send_failed_chunk", "body": _unescape(m2.group(1)),
                                "verdict": "ConnectError (not a parse verdict)"})
                continue
            verdict = m.group(1)
            off = re.search(r"byte offset (\d+)", verdict)
            out.append({
                "id": f"fb{rid}", "source": f"mi_audit_log telegram_markdown_fallback {ts[:10]}",
                "site": None, "kind": "fallback_chunk", "body": _unescape(m.group(3)),
                "verdict": verdict, "tg_byte_offset": int(off.group(1)) if off else None,
                "offset_snippet": _snippet(m.group(2)),
            })
        elif sec == "SYSREV":
            rid, ts, body = parts[0], parts[1], "\t".join(parts[2:])
            out.append({"id": f"sr{rid}", "source": f"mi_system_reviews {ts[:10]}",
                        "site": "agents/market_intelligence/system_review.py:299", "kind": "weekly_review",
                        "body": _unescape(body)})
        elif sec in ("GRADE_DECISION", "ANOMALY", "THEME_DESC"):
            rid, ts, body = parts[0], parts[1], "\t".join(parts[2:])
            kind = {"GRADE_DECISION": "dyn:ep_grade_decision", "ANOMALY": "dyn:anomaly_detected",
                    "THEME_DESC": "dyn:theme_description"}[sec]
            out.append({"id": f"{sec.lower()}{rid}", "source": f"mi_audit_log {ts[:10]}", "site": None,
                        "kind": kind, "body": _unescape(body)})
        elif sec == "GROUNDED":
            rid, ticker, body = parts[0], parts[1], "\t".join(parts[2:])
            out.append({"id": f"gt{rid}", "source": f"mi_ep_alerts.grounded_text {ticker}", "site": None,
                        "kind": "dyn:grounded_text", "body": _unescape(body)})
    with open(dst, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"wrote {len(out)} items -> {dst}")
    for k, n in Counter(r["kind"] for r in out).most_common():
        print(f"  {n:4d} {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
