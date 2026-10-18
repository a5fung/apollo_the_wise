#!/usr/bin/env python3
"""#702 P4b step 1 - pull YouTube AUTO-CAPTIONS (free, public) for a channel video list.

$0 only: yt-dlp reads the public caption track, nothing is downloaded or paid for.
Throttled (>= MIN_GAP s between videos, jittered), exponential back-off on HTTP 429,
resumable (fetch_log.tsv: ids with status ok / nocaps are skipped on re-run; failures are retried
up to MAX_ATTEMPTS across runs).

usage: fetch_transcripts.py --videos qm_videos.txt --out OUT --yt-dlp PATH [--limit N]
videos file lines: id|seconds|title
"""
import argparse
import os
import random
import subprocess
import sys
import time

MIN_GAP = 8.0
MAX_ATTEMPTS = 3          # per run, per video (network errors); 429s back off separately
BACKOFF_START = 60
BACKOFF_MAX = 1800


def load_log(path):
    done, fails = {}, {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            p = ln.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            vid, status = p[1], p[2]
            if status in ("ok", "nocaps"):
                done[vid] = status
            else:
                fails[vid] = fails.get(vid, 0) + 1
    return done, fails


def log(path, vid, status, upload_date="", track="", note=""):
    with open(path, "a", encoding="utf-8") as f:
        f.write("\t".join([time.strftime("%Y-%m-%dT%H:%M:%S"), vid, status, upload_date, track, note.replace("\t", " ").replace("\n", " ")[:300]]) + "\n")


def run_one(ytdlp, vid, subs_dir, lang, env):
    cmd = [ytdlp, "--no-simulate", "--print", "DATE:%(upload_date)s", "--write-auto-subs", "--sub-langs", lang,
           "--skip-download", "--sub-format", "vtt", "--no-playlist", "--no-warnings",
           "-o", os.path.join(subs_dir, "%(id)s.%(ext)s"), "https://www.youtube.com/watch?v=" + vid]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=240)
    date = ""
    for ln in r.stdout.splitlines():
        if ln.startswith("DATE:"):
            date = ln[5:].strip()
    return r.returncode, date, (r.stderr or "")[-600:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--yt-dlp", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    subs_dir = os.path.join(a.out, "subs")
    os.makedirs(subs_dir, exist_ok=True)
    logp = os.path.join(a.out, "fetch_log.tsv")
    env = dict(os.environ)
    if "SSL_CERT_FILE" not in env:
        import certifi
        env["SSL_CERT_FILE"] = certifi.where()
    vids = [ln.split("|")[0] for ln in open(a.videos, encoding="utf-8") if ln.strip()]
    done, fails = load_log(logp)
    todo = [v for v in vids if v not in done]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(vids)} videos, {len(done)} already done, {len(todo)} to do", flush=True)
    t0 = time.time()
    last = 0.0
    backoff = BACKOFF_START
    for i, vid in enumerate(todo, 1):
        wait = MIN_GAP + random.uniform(0, 3) - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        attempt = 0
        n429 = 0
        while attempt < MAX_ATTEMPTS:
            attempt += 1
            last = time.time()
            try:
                rc, date, err = run_one(a.yt_dlp, vid, subs_dir, "en-orig", env)
            except subprocess.TimeoutExpired:
                rc, date, err = 99, "", "timeout"
            if "429" in err or "Too Many Requests" in err or "rate-limit" in err.lower():
                n429 += 1
                log(logp, vid, "retry_429", note=f"sleep {backoff}s (#{n429})")
                print(f"[{i}/{len(todo)}] {vid} 429 -> sleep {backoff}s", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
                if n429 >= 6:
                    log(logp, vid, "fail", date, "", "6x HTTP 429")
                    break
                attempt -= 1          # a 429 does not consume a network-error attempt
                continue
            track = "en-orig"
            f = os.path.join(subs_dir, f"{vid}.en-orig.vtt")
            if rc == 0 and not os.path.exists(f):
                # no en-orig track on this (older) video: fall back to the plain auto 'en' track
                time.sleep(3)
                try:
                    rc, date2, err = run_one(a.yt_dlp, vid, subs_dir, "en", env)
                except subprocess.TimeoutExpired:
                    rc, date2, err = 99, "", "timeout"
                date = date or date2
                f = os.path.join(subs_dir, f"{vid}.en.vtt")
                track = "en"
            if rc == 0 and os.path.exists(f):
                log(logp, vid, "ok", date, track)
                backoff = BACKOFF_START
                print(f"[{i}/{len(todo)}] {vid} ok {date} {track}  {time.time()-t0:.0f}s", flush=True)
                break
            if rc == 0:
                log(logp, vid, "nocaps", date, "", "no auto-caption track")
                print(f"[{i}/{len(todo)}] {vid} nocaps {date}", flush=True)
                break
            log(logp, vid, "fail", date, "", f"rc={rc} {err}")
            print(f"[{i}/{len(todo)}] {vid} FAIL rc={rc} attempt {attempt}: {err[-120:]}", flush=True)
            time.sleep(10 * attempt)
    print(f"finished in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
