#!/usr/bin/env python3
"""v2 questions (2026-10-18, after the free re-test + his VIR answer): each drawn line's two end points as date + price,
the 50-day-average fix; shape comes from the bars, not the frame.
#702 P4b vision step, part 2 (PAID, operator-approved 2026-10-18: Sonnet, one frame per stock-base, in batches with a
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
MAX_TOKENS = 16000   # thinking ON (batch 1c) shares this budget

PROMPT = """You are reading a screenshot from a stock trader's livestream (TC2000 charting software, 1920x1080). Answer only from what is visible; use "" / -1 / "cant_tell" rather than guess.

What matters is the HAND-DRAWN lines on the DAILY chart (the panel whose tab/header says "Daily" or "-1D").
- Hand-drawn lines are STRAIGHT segments. The curved coloured lines are moving averages: the 50-day moving average is drawn in RED and is CURVED - never report the curve itself as a drawn line. Moving averages 10 (magenta), 20 (yellow), 100/150/200 (orange/blue/green) are also curves - ignore them.
- A drawn red line can run RIGHT BESIDE the red 50-day average (often a rising line under the lows of a base). Look closely along the 50-day average for a STRAIGHT red segment that touches the lows or highs - that straight segment IS a drawn line and must be reported.
- Report every straight RED line on the daily chart (short ones too), and every straight WHITE HORIZONTAL line that carries a price label at its right end (a "level" he drew). Ignore straight WHITE DIAGONAL lines that point to a text note (annotation pointers).
- For each line give: role (top = sits on highs above price, bottom = under lows, level = a horizontal price level, other), its two end points as DATE (YYYY-MM-DD, best estimate from the x-axis month labels - interpolate between labels) and PRICE (read from the right-hand price axis), and whether each end sits on a candle high, a candle low, a candle body, or floats in empty space.
- The date printed at the top right of each chart header is the NEXT-EARNINGS date, not the data date. Read the screen date from the Windows taskbar clock (bottom right).
- daily_scrolled_back = "yes" when the daily chart's right edge is clearly earlier than the screen date.
- why: at most two short sentences, written last."""

LINE = {"type": "object", "additionalProperties": False,
        "properties": {"role": {"type": "string", "enum": ["top", "bottom", "level", "other"]},
                       "color": {"type": "string", "enum": ["red", "white", "other"]},
                       "start_date": {"type": "string"}, "start_price": {"type": "number"},
                       "end_date": {"type": "string"}, "end_price": {"type": "number"},
                       "start_on": {"type": "string", "enum": ["candle_high", "candle_low", "candle_body", "floating", "cant_tell"]},
                       "end_on": {"type": "string", "enum": ["candle_high", "candle_low", "candle_body", "floating", "cant_tell"]},
                       "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
        "required": ["role", "color", "start_date", "start_price", "end_date", "end_price", "start_on", "end_on", "confidence"]}
SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {
              "ticker_on_screen": {"type": "string"},
              "screen_date": {"type": "string"},
              "daily_panel": {"type": "string", "enum": ["left", "right", "full", "none"]},
              "other_panel_timeframe": {"type": "string"},
              "daily_axis_first_month": {"type": "string"},
              "daily_axis_last_month": {"type": "string"},
              "daily_scrolled_back": {"type": "string", "enum": ["no", "yes", "cant_tell"]},
              "daily_lines": {"type": "array", "items": LINE},
              "hourly_red_line_count": {"type": "number"},
              "why": {"type": "string"}},
          "required": ["ticker_on_screen", "screen_date", "daily_panel", "other_panel_timeframe", "daily_axis_first_month",
                       "daily_axis_last_month", "daily_scrolled_back", "daily_lines", "hourly_red_line_count", "why"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--thinking", default="between_tools", choices=["between_tools", "adaptive", "none"])
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default="", choices=["", "low", "medium", "high", "xhigh", "max"])
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
        kw = dict(model=a.model, max_tokens=MAX_TOKENS,
                  messages=[{"role": "user", "content": [
                      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
                      {"type": "text", "text": PROMPT}]}],
                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        if a.thinking == "between_tools":
            kw["thinking"] = {"type": "between_tools"}
        elif a.thinking == "adaptive":
            kw["thinking"] = {"type": "adaptive"}
        if a.effort:
            kw["output_config"]["effort"] = a.effort
        rec = {"frame_id": r["frame_id"], "model": a.model, "thinking": a.thinking, "effort": a.effort, "t": time.time()}
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
