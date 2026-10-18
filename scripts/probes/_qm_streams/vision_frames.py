#!/usr/bin/env python3
"""#702 P4b vision step, part 1 ($0): cut ONE frame per manifest row from the stream at the labelled caption time + 3 s.

Operator 2026-10-18: "Let's do then in batches, review and verify correctness and accuracy before moving on, report back to
me each batch before moving forward." The paid read is vision_read.py; this script only downloads a 12 s clip per row
(yt-dlp, HLS formats 270/614/609 first: the DASH mp4 path returned empty files on long streams in the 10-18 free test),
writes <frame_id>.png and deletes the clip. Resumable (an existing PNG is skipped), >= 8 s between videos.

    python vision_frames.py --manifest QM/vision/batch1_manifest.tsv --out QM/vision/frames --ytdlp <venv>/bin/yt-dlp
"""
import argparse
import csv
import os
import subprocess
import sys
import time

OFFSET_S = 3      # frame = caption time + 3 s (the 10-18 test: the labelled ticker was on screen at +1 / +5 / +9 s)
CLIP_BEFORE_S = 2
CLIP_AFTER_S = 10
FORMATS = "270/614/609/bv*[height<=1080][protocol*=m3u8]"
GAP_S = 8


def hms(ts: str) -> int:
    p = [int(x) for x in ts.strip().split(":")]
    while len(p) < 3:
        p.insert(0, 0)
    return p[0] * 3600 + p[1] * 60 + p[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ytdlp", required=True)
    a = ap.parse_args()
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(a.out, exist_ok=True)
    rows = list(csv.DictReader(open(a.manifest, encoding="utf-8"), delimiter="\t"))
    log = open(os.path.join(a.out, "frames_log.tsv"), "a", encoding="utf-8")
    for r in rows:
        fid, vid, t = r["frame_id"], r["vid"], hms(r["ts"])
        png = os.path.join(a.out, f"{fid}.png")
        if os.path.exists(png):
            continue
        lo, hi = max(0, t - CLIP_BEFORE_S), t + CLIP_AFTER_S
        clip = os.path.join(a.out, f"{fid}.clip")
        p = subprocess.run([a.ytdlp, "-q", "--no-warnings", "--ffmpeg-location", ff, "-f", FORMATS,
                            "--download-sections", f"*{lo}-{hi}", "-o", clip + ".%(ext)s",
                            f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True)
        got = [f for f in os.listdir(a.out) if f.startswith(f"{fid}.clip.")]
        status = "fail"
        if got:
            src = os.path.join(a.out, got[0])
            q = subprocess.run([ff, "-loglevel", "error", "-y", "-ss", str(t + OFFSET_S - lo), "-i", src, "-frames:v", "1", png],
                               capture_output=True, text=True)
            status = "ok" if os.path.exists(png) and os.path.getsize(png) > 10_000 else f"noframe {q.stderr.strip()[:120]}"
            for f in got:
                os.remove(os.path.join(a.out, f))
        else:
            status = f"noclip {p.stderr.strip()[:160]}"
        log.write(f"{fid}\t{vid}\t{r['ts']}\t{status}\n")
        log.flush()
        print(fid, r["ticker"], status, flush=True)
        time.sleep(GAP_S)


if __name__ == "__main__":
    sys.exit(main())
