#!/usr/bin/env python3
"""#702 P4b vision step, part 2 (PAID, operator-approved 2026-10-18: Sonnet, one frame per stock-base, in batches with a
review + report to him after each batch). Reads each frame BLIND (image + fixed questions only - never the label ticker, the
talk date or anything from our tables) and writes every raw response + usage to a JSONL on the first run.

Raw SDK client on purpose, NOT shared/llm_client's factory: the factory keeps replay samples per call site and the nightly
release refresh replays them, which would put this probe (with images) into a recurring loop. Runs where the API key is
(the apollo-market container); the frames are copied in, the JSONL is copied out. Pre-registration:
QM/vision/PREREGISTRATION.md.

    python vision_read.py --frames DIR --manifest batch1_manifest.tsv --out batch1_reads.jsonl [--limit 1] [--thinking between_tools|none]
"""
import argparse
import base64
import csv
import json
import os
import sys
import time

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 1500

PROMPT = """This is a screenshot from a stock trader's livestream: TC2000 charting software, usually a DAILY chart on the left and an HOURLY chart on the right.
Answer ONLY from what is visible in the image; use "" / -1 / "cant_tell" rather than guess.
- The date printed at the top right of each chart header is the NEXT-EARNINGS date, not the data date: read dates from the
  Windows taskbar clock (bottom right) and the charts' x-axis labels.
- ticker_on_screen: the symbol of the main charts.
- daily_scrolled_back: "yes" if the daily chart's right edge is clearly earlier than the taskbar date.
- base = the most recent consolidation on the DAILY chart before its right edge, after a prior run-up. Give its start/end
  month (YYYY-MM), its top and bottom price, and the run-up into it (from price, to price).
- daily_lines: the hand-drawn RED lines on the daily chart around that base (not the coloured moving averages). For each:
  direction, role (top / bottom / other), and the month + price at each end.
- wick_above_top_line: does a big upper wick or spike stick out above a drawn top line (the line ignores it)?
- base_character: pick one class for the base's shape.
- why: at most two short sentences, written last."""

LINE = {"type": "object", "additionalProperties": False,
        "properties": {"direction": {"type": "string", "enum": ["horizontal", "falling", "rising"]},
                       "role": {"type": "string", "enum": ["top", "bottom", "other"]},
                       "start_month": {"type": "string"}, "start_price": {"type": "number"},
                       "end_month": {"type": "string"}, "end_price": {"type": "number"}},
        "required": ["direction", "role", "start_month", "start_price", "end_month", "end_price"]}
SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {
              "screen_type": {"type": "string", "enum": ["chart", "not_a_chart"]},
              "ticker_on_screen": {"type": "string"},
              "screen_date": {"type": "string"},
              "panels": {"type": "string"},
              "daily_scrolled_back": {"type": "string", "enum": ["no", "yes", "cant_tell"]},
              "daily_last_bar_month": {"type": "string"},
              "base_start_month": {"type": "string"},
              "base_end_month": {"type": "string"},
              "base_top": {"type": "number"},
              "base_bottom": {"type": "number"},
              "run_from": {"type": "number"},
              "run_to": {"type": "number"},
              "daily_lines": {"type": "array", "items": LINE},
              "wick_above_top_line": {"type": "string", "enum": ["yes", "no", "cant_tell", "no_top_line"]},
              "base_character": {"type": "string", "enum": ["tight_flat", "wide_then_tightening", "falling_flag",
                                                            "ascending_triangle", "symmetric_triangle", "other",
                                                            "no_base_visible"]},
              "hourly_lines": {"type": "string"},
              "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
              "why": {"type": "string"}},
          "required": ["screen_type", "ticker_on_screen", "screen_date", "panels", "daily_scrolled_back",
                       "daily_last_bar_month", "base_start_month", "base_end_month", "base_top", "base_bottom",
                       "run_from", "run_to", "daily_lines", "wick_above_top_line", "base_character", "hourly_lines",
                       "confidence", "why"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--thinking", default="between_tools", choices=["between_tools", "none"])
    a = ap.parse_args()
    import anthropic
    client = anthropic.Anthropic()
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["frame_id"] for l in open(a.out, encoding="utf-8") if l.strip()}
    rows = [r for r in csv.DictReader(open(a.manifest, encoding="utf-8"), delimiter="\t") if r["frame_id"] not in done]
    if a.limit:
        rows = rows[:a.limit]
    out = open(a.out, "a", encoding="utf-8")
    for r in rows:
        png = os.path.join(a.frames, f"{r['frame_id']}.png")
        img = base64.standard_b64encode(open(png, "rb").read()).decode()
        kw = dict(model=MODEL, max_tokens=MAX_TOKENS,
                  messages=[{"role": "user", "content": [
                      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
                      {"type": "text", "text": PROMPT}]}],
                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        if a.thinking == "between_tools":
            kw["thinking"] = {"type": "between_tools"}
        rec = {"frame_id": r["frame_id"], "model": MODEL, "thinking": a.thinking, "t": time.time()}
        try:
            resp = client.messages.create(**kw)
            text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
            rec.update(stop_reason=resp.stop_reason, usage=resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage),
                       raw_text=text, content_types=[getattr(b, "type", "") for b in resp.content])
            try:
                rec["read"] = json.loads(text)
            except Exception as e:
                rec["parse_error"] = str(e)[:200]
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        out.write(json.dumps(rec) + "\n")
        out.flush()
        u = rec.get("usage") or {}
        print(r["frame_id"], rec.get("error") or rec.get("parse_error") or
              f"ok in={u.get('input_tokens')} out={u.get('output_tokens')} {rec.get('read', {}).get('ticker_on_screen')}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
