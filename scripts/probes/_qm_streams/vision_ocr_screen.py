#!/usr/bin/env python3
"""#702 P4b step 2 ($0, local): read the ticker tab and the taskbar date off each stream frame with the Mac's built-in text
recognition (Apple Vision, VNRecognizeTextRequest) - the free screen that replaces a paid one-call read (operator
2026-10-18: "I want to run free first, confirm before spending"). Gate: 30/30 on the batch-1 frames whose ticker and date
are known before it screens new frames.

    <venv with pyobjc-framework-Vision>/bin/python vision_ocr_screen.py --frames DIR --out screen.tsv [--glob 'p4b_*.png']
"""
import argparse
import csv
import glob
import os
import re
import sys

import Quartz
import Vision
from Foundation import NSURL

TAB = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z])?)-1D\b")
HDR = re.compile(r"^\+?\s*([A-Z]{1,5}(?:\.[A-Z])?)\b")
DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")


def ocr(path, box=None, scale=1):
    """[(text, x, y_top)] in pixel coords of the 1920x1080 frame (y from the top). `box` = (x0, y0, x1, y1): OCR only that
    region, upscaled `scale`x first (the tab text is ~9 px tall; Vision misreads it at native size)."""
    if box is not None:
        from PIL import Image
        import tempfile
        from PIL import ImageOps
        im = Image.open(path).convert("L").crop(box)
        im = ImageOps.autocontrast(ImageOps.invert(im))                # light text on a dark chart -> dark on light
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        im.save(tmp)
        items, w, h = ocr(tmp)
        os.remove(tmp)
        return [(t, box[0] + x / scale, box[1] + y / scale) for t, x, y in items], 1920, 1080
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    w, h = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    handler.performRequests_error_([req], None)
    out = []
    for obs in req.results() or []:
        c = obs.topCandidates_(1)
        if not c:
            continue
        bb = obs.boundingBox()          # normalised, origin bottom-left
        out.append((str(c[0].string()), bb.origin.x * w, (1 - bb.origin.y - bb.size.height) * h))
    return out, w, h


def screen(path):
    # 2026-10-23 fix (Track A verifier): the crop boxes were hard-coded for 1920x1080, so 1280x720 frames (118 of them, mostly 2019)
    # cropped the wrong pixels and lost the tab and the taskbar date. Boxes are now scaled to the frame's own size.
    from PIL import Image
    with Image.open(path) as im:
        fw, fh = im.size
    sx, sy = fw / 1920, fh / 1080
    box = lambda x0, y0, x1, y1: (int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy))
    w, h = 1920, 1080
    top, _, _ = ocr(path, box=box(0, 58, 300, 112), scale=round(5 / sx) if sx < 1 else 5)        # the "TICKER-1D" tab + header
    bot, _, _ = ocr(path, box=box(1700, 1040, 1920, 1080), scale=round(4 / sx) if sx < 1 else 4)  # the Windows taskbar clock
    tabs = [m.group(1) for t, x, y in top for m in TAB.finditer(t.replace(" ", ""))]
    skip = {"NYSE", "NASDAQ", "ADR", "TI", "AMEX", "ARCA", "BATS", "NEW", "D", "W", "M", "H", "X"}
    hdrs = [m.group(1) for t, x, y in top for m in [HDR.match(t.strip())] if m and m.group(1) not in skip]
    dates = [f"{m.group(1)}-{m.group(2)}-{m.group(3)}" for t, x, y in bot for m in [DATE.search(t.replace(" ", ""))] if m]
    # a single letter in the top-left is usually a watchlist label ("Z - Empty" in his 2023 layout): prefer >= 2 letters
    multi = [t for t in hdrs if len(t) >= 2]
    ticker = tabs[0] if tabs else (multi[0] if multi else (hdrs[0] if hdrs else ""))
    return dict(ticker=ticker, daily_tab=int(bool(tabs)), screen_date=dates[-1] if dates else "",
                tabs="|".join(tabs[:4]), headers="|".join(hdrs[:3]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--glob", default="*.png")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.frames, a.glob)))
    with open(a.out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["frame_id", "ticker", "daily_tab", "screen_date", "tabs", "headers"], delimiter="\t")
        wr.writeheader()
        for p in files:
            r = screen(p)
            wr.writerow(dict(frame_id=os.path.basename(p)[:-4], **r))
    print(len(files), "frames ->", a.out)


if __name__ == "__main__":
    sys.exit(main())
