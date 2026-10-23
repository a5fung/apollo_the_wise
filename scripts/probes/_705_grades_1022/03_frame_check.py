#!/usr/bin/env python3
"""#705 Track A step 3 (2026-10-23, outcome-free, $0, local): is the ticker on the screen the ticker we think it is, and does the
screen match OUR bars for it?  Then the graded-moment LABEL SET.

Per frame (TC2000 screenshot of Qullamaggie's stream, Swedish locale: decimal COMMAS, space thousands):
  OCR  : daily-tab ticker (existing vision_ocr_screen.screen + a full-frame '-1D' / '-D' / 'XXXX Daily' fallback), taskbar date,
         header 'ADR x,y%', every price-like number, and the right-axis price ladder(s) with the off-grid LAST-PRICE TAG.
  REBUILD from our bars for the on-screen ticker on the screen date (sessions M0 = last session <= date, M1 = the one before; a
         stream can run after the close, before the open, or past Swedish midnight):
    (a) ADR  : OCR ADR within TOL of ours over the 20 sessions ending M0 or M1 (formula chosen on the caption==screen frames, below)
    (b) PRICE: a right-axis label inside RAW [low*0.99, high*1.01] of M0 or M1 (RAW = split-adjusted bar x its split ratio that day)
               reported 3 ways: any axis label / the off-grid price TAG only / round ticks only.
  CONFIRMED = screen ticker has a daily tab AND ((a) OR (b)).  Reported separately: a, b.
  NEGATIVE CONTROL: the same checks with 10 random WRONG tickers per frame (same date, close >= 5, close*vol >= 10M on M0, same era
         file) -> the false-match rate.  POSITIVE CONTROL: the caption==screen frames.

Phases (resumable; OCR cached in vision/grades_frame_ocr_s*.jsonl, one json line per frame):
  python 03_frame_check.py --stage all [--workers 4]     # OCR missing frames (ocr venv, sharded) then analyse (this python)
  python 03_frame_check.py --stage ocr --shard i/n        # (run under venvs/ocr/bin/python)
  python 03_frame_check.py --stage analyze
Writes vision/grades_labels.tsv + vision/grades_frame_check.tsv and 03_frame_check.txt next to this file.
HARD: outcome-free (no forward returns, no trades), read-only on apollo_data except those outputs, no network."""
import argparse, csv, glob, json, os, re, sys, subprocess, time, random, collections, math

VIS = "/Users/alvinfung/apollo_data/cb702/qm_streams/vision"
HERE = os.path.dirname(os.path.abspath(__file__))
QS = os.path.join(os.path.dirname(HERE), "_qm_streams")
OCR_PY = "/Users/alvinfung/apollo_data/venvs/ocr/bin/python"
CB_A = "/Users/alvinfung/apollo_data/cb702_pre"
CB_B = "/Users/alvinfung/apollo_data/cb702"
ERA_A_LAST = "2022-06-30"
TOL_PRICE = (0.99, 1.01)
TOL_ADR = 0.6                      # points; justified in the summary from the caption==screen distribution
WINDOW_S = 30.0                    # attribution window (seconds either side of the frame's moment); justified in the summary
N_CONTROL = 10
MIN_PX, MIN_DV = 5.0, 10_000_000.0

# ---------------------------------------------------------------------------------------------------------- frame table
def hms(s):
    p = [int(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def read_tsv(path):
    return list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))


def graded_pairs():
    return {(r["video"], r["ticker"]) for r in read_tsv(f"{VIS}/graded_moments.tsv")}


def ok_ids():
    """frames the cutter reports ok (the log also carries tracebacks and 'noclip' rows; the cutter is still running)."""
    ok = set()
    for ln in open(f"{VIS}/frames_grades/frames_log.tsv", encoding="utf-8", errors="replace"):
        p = ln.rstrip("\n").split("\t")
        if len(p) == 4 and re.match(r"^g_\d{4}$", p[0]) and p[3] == "ok":
            ok.add(p[0])
    return ok


def frame_table():
    """grades frames (manifest) + the earlier batch-1 / p4b frames of pairs that are graded (they were skipped by the cutter)."""
    out = []
    for r in read_tsv(f"{VIS}/grades_manifest.tsv"):
        out.append(dict(frame_id=r["frame_id"], src="grades", vid=r["vid"], ts=r["ts"], caption=r["ticker"], ref_date=r["ref_date"],
                        path=f"{VIS}/frames_grades/{r['frame_id']}.png"))
    gp = graded_pairs()
    for man, sub, src in (("batch1_manifest.tsv", "frames", "b1"), ("p4b_manifest.tsv", "frames_p4b", "p4b")):
        for r in read_tsv(f"{VIS}/{man}"):
            if (r["vid"], r["ticker"]) in gp and r.get("ref_date") and not str(r.get("kind", "")).startswith("planted"):
                out.append(dict(frame_id=r["frame_id"], src=src, vid=r["vid"], ts=r["ts"], caption=r["ticker"], ref_date=r["ref_date"],
                                path=f"{VIS}/{sub}/{r['frame_id']}.png"))
    return out


def cached():
    d = {}
    for f in sorted(glob.glob(f"{VIS}/grades_frame_ocr_s*.jsonl")):
        for ln in open(f, encoding="utf-8"):
            try:
                r = json.loads(ln)
                d[r["frame_id"]] = r
            except Exception:
                pass
    return d

# ------------------------------------------------------------------------------------------------- number / axis logic (pure python)
NUM = re.compile(r"^\d{1,3}(?: \d{3})*[.,]\d{1,4}$|^\d{1,6}[.,]\d{1,4}$")
ADR_RX = re.compile(r"ADR\s*:?\s*(\d{1,2}[.,]\d{1,2})\s*%?")
TAB_RX = re.compile(r"(?<![A-Za-z])([A-Z]{1,5}(?:\.[A-Z])?)-(?:1D|D)(?![A-Za-z0-9])")
DAILY_RX = re.compile(r"(?<![A-Za-z])([A-Z]{1,5})Daily")


def parse_num(t):
    t = t.strip()
    if not NUM.match(t):
        return None
    return float(t.replace(" ", "").replace(",", "."))


NICE = [m * 10.0 ** k for k in range(-3, 5) for m in (1, 2, 2.5, 5)]


def tick_step(vs, b):
    """the axis tick step: the LARGEST 1/2/2.5/5 x 10^k for which >= 4 of the line's labels are multiples, <= 2 are not (the last-price
    tag / the crosshair label), and neighbouring ticks sit 25-450 px apart. None when no step fits (a chance line through a data panel)."""
    for st in sorted(NICE, reverse=True):
        if not (25 <= st / abs(b) <= 450):
            continue
        m = sum(1 for v in vs if is_multiple(v, st))
        if m >= 4 and len(vs) - m <= 2:
            return st
    return None


def is_multiple(v, step, tol=0.03):
    k = v / step
    return abs(k - round(k)) <= tol


def detect_axes(nums, ytol=5.0):
    """nums = [(v, x0, y0, x1, y1)] -> axes: columns (same right edge) of >= 4 labels that sit on ONE straight value-vs-y line with
    the value FALLING as y grows. Watch-list columns are not linear in y and drop out. Returns dicts with v = a + b*y and the band."""
    toks = sorted(nums, key=lambda n: n[3])
    clusters = []
    for n in toks:
        if clusters and n[3] - clusters[-1][-1][3] <= 8:
            clusters[-1].append(n)
        else:
            clusters.append([n])
    axes = []
    for cl in clusters:
        seen, c = set(), []
        for n in sorted(cl, key=lambda n: n[2]):                       # drop duplicate reads of the same label from two passes
            k = (round(n[0], 2), round((n[2] + n[4]) / 2 / 5))
            if k not in seen:
                seen.add(k)
                c.append(n)
        if len(c) < 4:
            continue
        yc = [(n[2] + n[4]) / 2 for n in c]
        best = None
        for i in range(len(c)):
            for j in range(i + 1, len(c)):
                dy = yc[j] - yc[i]
                dv = c[j][0] - c[i][0]
                if abs(dy) < 25 or dv == 0 or (dv / dy) >= 0:
                    continue
                b = dv / dy
                inl = [k for k in range(len(c)) if abs(yc[k] - (yc[i] + (c[k][0] - c[i][0]) / b)) <= ytol]
                ys = {round(yc[k] / 6) for k in inl}
                if len(ys) >= 4 and (best is None or len(ys) > best[0]):
                    best = (len(ys), inl)
        if best is None or best[0] < 4:
            continue
        inl = best[1]
        xs = [yc[k] for k in inl]
        vs = [c[k][0] for k in inl]
        n_ = len(inl)
        my, mv = sum(xs) / n_, sum(vs) / n_
        sxx = sum((y - my) ** 2 for y in xs)
        b = sum((y - my) * (v - mv) for y, v in zip(xs, vs)) / sxx
        a = mv - b * my
        step = tick_step(vs, b)
        if step is None:                          # real ticks are 'nice' numbers; a chance straight line through a data panel is not
            continue
        axes.append(dict(a=a, b=b, step=step, n=best[0],
                         bx0=min(c[k][1] for k in inl) - 20, bx1=max(c[k][3] for k in inl) + 30,
                         by0=min(xs) - 70, by1=max(xs) + 70))
    axes.sort(key=lambda a: -a["n"])
    return axes[:3]


def off_grid(v, ax):
    """the last-price TAG: a label that is not a multiple of the axis tick step (0.03 step tolerance for OCR slips like 100,06)."""
    return not is_multiple(v, ax["step"] / 2)        # step/2: a half-step tick (the step can be over-estimated by one) is still a tick


def labels_for(rec):
    """[(value, is_tag)] right-axis labels: numeric tokens inside an axis band AND at the y the axis line puts that value."""
    toks = rec["toks"]
    axes = detect_axes([(t[0], t[1], t[2], t[3], t[4]) for t in toks if t[5] in ("n", "x")])
    out = {}
    for ax in axes:
        for t in toks:
            xc, yc = (t[1] + t[3]) / 2, (t[2] + t[4]) / 2
            if not (ax["bx0"] <= xc <= ax["bx1"] and ax["by0"] <= yc <= ax["by1"]):
                continue
            if abs(yc - (t[0] - ax["a"]) / ax["b"]) > 8:
                continue
            out[(round(t[0], 2))] = out.get(round(t[0], 2), False) or off_grid(t[0], ax)
    return sorted(out.items()), axes

# ---------------------------------------------------------------------------------------------------------- OCR stage
def ocr_stage(shard, nshards, only=None, outfile=None):
    sys.path.insert(0, QS)
    import tempfile
    import Quartz, Vision
    from Foundation import NSURL
    from PIL import Image, ImageOps
    import vision_ocr_screen as vs

    def ocr_raw(path):
        src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(path), None)
        img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        w, h = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(False)
        Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None).performRequests_error_([req], None)
        out = []
        for obs in req.results() or []:
            c = obs.topCandidates_(1)
            if c:
                bb = obs.boundingBox()
                out.append((str(c[0].string()), bb.origin.x * w, (1 - bb.origin.y - bb.size.height) * h,
                            (bb.origin.x + bb.size.width) * w, (1 - bb.origin.y) * h))
        return out

    def ocr_box(path, box, scale, invert=True):
        im = Image.open(path).convert("L").crop(box)
        im = ImageOps.autocontrast(ImageOps.invert(im) if invert else im)
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        im.save(tmp)
        items = ocr_raw(tmp)
        os.remove(tmp)
        return [(t, box[0] + x0 / scale, box[1] + y0 / scale, box[0] + x1 / scale, box[1] + y1 / scale) for t, x0, y0, x1, y1 in items]

    def numeric(items, src):
        out = []
        for t, x0, y0, x1, y1 in items:
            v = parse_num(t)
            if v is not None:
                out.append([v, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1), src])
        return out

    def one(fr):
        p = fr["path"]
        im = Image.open(p)
        w, h = im.size
        im.close()
        nat = ocr_raw(p)
        x2 = ocr_box(p, (0, 0, w, h), 2)
        hdr = ocr_box(p, (0, 50, w, 230), 3)
        scr = vs.screen(p)
        toks = numeric(nat, "n") + numeric(x2, "x")
        allt = [t[0].replace(" ", "") for t in nat + x2 + hdr]
        tabs_ext = []
        for t in allt:
            for m in TAB_RX.finditer(t):
                tabs_ext.append(m.group(1))
        for t in [t[0].replace(" ", "") for t in hdr + [i for i in nat + x2 if i[2] < 230]]:
            for m in DAILY_RX.finditer(t):
                tabs_ext.append(m.group(1))
        adr = []
        for t, x0, y0, x1, y1 in [i for i in nat + x2 if i[2] < 230] + hdr:
            for m in ADR_RX.finditer(t):
                adr.append(float(m.group(1).replace(",", ".")))
        axes = detect_axes([(t[0], t[1], t[2], t[3], t[4]) for t in toks])
        for ax in axes:                                                  # second look at the axis strip: the price tag is light-on-colour
            box = (int(max(0, ax["bx0"] - 10)), int(max(0, ax["by0"])), int(min(w, ax["bx1"] + 10)), int(min(h, ax["by1"])))
            if box[2] - box[0] < 20 or box[3] - box[1] < 40:
                continue
            for inv in (True, False):
                toks += numeric(ocr_box(p, box, 4, inv), "b")
        return dict(frame_id=fr["frame_id"], src=fr["src"], scr=scr, tabs_ext=[t for t, _ in collections.Counter(tabs_ext).most_common()], adr=sorted(set(adr)), toks=toks,
                    size=[w, h])

    frames = frame_table()
    done = set(cached())
    okg = ok_ids()
    out = open(outfile or f"{VIS}/grades_frame_ocr_s{shard}.jsonl", "a", encoding="utf-8")
    n = 0
    for i, fr in enumerate(frames):
        if only and fr["frame_id"] not in only:
            continue
        if i % nshards != shard or (fr["frame_id"] in done and not only) or not os.path.exists(fr["path"]):
            continue
        if fr["src"] == "grades" and fr["frame_id"] not in okg:
            continue
        if time.time() - os.path.getmtime(fr["path"]) < 20:
            continue
        try:
            rec = one(fr)
        except Exception as e:                                           # not cached: retried next run
            print("skip", fr["frame_id"], repr(e)[:80], flush=True)
            continue
        out.write(json.dumps(rec) + "\n")
        out.flush()
        n += 1
        if n % 50 == 0:
            print(f"shard {shard}: {n} frames", flush=True)
    print(f"shard {shard}: done, {n} new", flush=True)

# ---------------------------------------------------------------------------------------------------------- bars
class Era:
    def __init__(self, name):
        import numpy as np, pandas as pd
        self.np = np
        t0 = time.time()
        cols = ["ticker", "date", "o", "h", "l", "c", "v"]
        if name == "A":
            df = pd.read_csv(f"{CB_A}/daily_closes_all.csv.gz", header=None, names=cols, usecols=[0, 1, 3, 4, 5, 6])
            rw = pd.read_csv(f"{CB_A}/daily_raw_close.csv.gz", header=None, names=["ticker", "date", "raw"])
            assert len(rw) == len(df) and (rw.ticker.to_numpy(object) == df.ticker.to_numpy(object)).all() and (rw.date.to_numpy(object) == df.date.to_numpy(object)).all(), \
                "era A raw file is not row-aligned with the adjusted file"
            ratio = (rw.raw.values / df.c.values)
        else:
            df = pd.read_csv(f"{CB_B}/daily_closes_all.csv.gz", header=None, names=cols, usecols=[0, 1, 3, 4, 5, 6])
            ratio = np.ones(len(df))
        d = pd.to_datetime(df.date, format="%Y-%m-%d").to_numpy().astype("datetime64[D]").astype("int32")
        tk_arr = df.ticker.to_numpy(object)
        codes, uniq = pd.factorize(tk_arr)
        order = np.lexsort((d, codes))
        self.d, self.h, self.l, self.c, self.v = d[order], df.h.values[order], df.l.values[order], df.c.values[order], df.v.values[order]
        self.ratio = np.asarray(ratio, dtype=float)[order]
        self.code = codes[order]
        self.tick = list(uniq)
        self.tcode = {t: i for i, t in enumerate(uniq)}
        self.start = np.searchsorted(self.code, np.arange(len(uniq)), "left")
        self.end = np.searchsorted(self.code, np.arange(len(uniq)), "right")
        if name == "B":                                  # raw = adjusted x product of (y/x) over splits dated AFTER the bar (checked: TSLA 2022-08-25 1|3)
            nsp = 0
            for ln in open(f"{CB_B}/cb702_splits.psv"):
                t, dd, x, y = ln.strip().split("|")[:4]
                k = self.tcode.get(t)
                if k is None:
                    continue
                sd = int(np.datetime64(dd, "D").astype("int32"))
                sl = slice(self.start[k], self.end[k])
                seg = self.ratio[sl]
                seg[self.d[sl] < sd] *= float(y) / float(x)
                nsp += 1
            print(f"era B: {nsp} split rows applied", flush=True)
        od = np.argsort(self.d, kind="stable")
        self.by_date = od
        self.ds = self.d[od]
        cnt = collections.Counter(self.d.tolist()) if False else None
        ud, uc = np.unique(self.d, return_counts=True)
        self.cal = ud[uc >= 500]                          # market calendar: dates with a full cross-section
        print(f"era {name}: {len(df):,} rows, {len(uniq):,} tickers, {time.time() - t0:.0f}s", flush=True)

    def sessions(self, day):
        """(M0, M1) = last market date <= day and the one before (ordinals)."""
        i = int(self.np.searchsorted(self.cal, day, "right")) - 1
        return (int(self.cal[i]), int(self.cal[i - 1])) if i >= 1 else (None, None)

    def eligible(self, m0):
        np = self.np
        lo, hi = np.searchsorted(self.ds, m0, "left"), np.searchsorted(self.ds, m0, "right")
        rows = self.by_date[lo:hi]
        ok = (self.c[rows] * self.ratio[rows] >= MIN_PX) & (self.c[rows] * self.v[rows] >= MIN_DV)
        return [self.tick[self.code[r]] for r in rows[ok]]

    def metrics(self, tick, m0, m1):
        """dict(adr_a=[end M0, end M1], adr_b=[...], lohi=[(lo,hi) raw M0, M1]) or None when the ticker has no bar on M0 / < 21 bars."""
        np = self.np
        k = self.tcode.get(tick)
        if k is None:
            return None
        s, e = self.start[k], self.end[k]
        dd = self.d[s:e]
        i0 = int(np.searchsorted(dd, m0, "left"))
        if i0 >= len(dd) or dd[i0] != m0 or i0 < 20:
            return None
        res = dict(adr_a=[], adr_b=[], lohi=[])
        for off, m in ((0, m0), (1, m1)):
            i = i0 - off
            if i >= 19 and dd[i] == m:
                H, L, C = self.h[s + i - 19:s + i + 1], self.l[s + i - 19:s + i + 1], self.c[s + i - 19:s + i + 1]
                res["adr_a"].append(float(np.mean((H - L) / C) * 100))
                res["adr_b"].append(float((np.mean(H / L) - 1) * 100))
                r = self.ratio[s + i]
                res["lohi"].append((float(self.l[s + i] * r), float(self.h[s + i] * r)))
            else:
                res["adr_a"].append(None); res["adr_b"].append(None); res["lohi"].append(None)
        return res

# ---------------------------------------------------------------------------------------------------------- checks
def adr_diff(ocr, ours):
    """smallest |OCR - ours| over every OCR ADR read and both end sessions; also the signed diff at M0 / M1 of the nearest read."""
    best = None
    for o in ocr:
        for e, a in enumerate(ours):
            if a is not None and (best is None or abs(o - a) < best[0]):
                best = (abs(o - a), o - a, e)
    return best                                            # (abs, signed, end_idx) or None


def price_hits(labels, lohi):
    """(any label, tag label, tick label) inside raw [low*0.99, high*1.01] of M0 or M1."""
    anyh = tagh = tickh = False
    for v, is_tag in labels:
        for r in lohi:
            if r is not None and r[0] * TOL_PRICE[0] <= v <= r[1] * TOL_PRICE[1]:
                anyh = True
                if is_tag:
                    tagh = True
                else:
                    tickh = True
    return anyh, tagh, tickh


def wilson(k, n):
    if n == 0:
        return (float("nan"),) * 2
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def pct(k, n):
    if n == 0:
        return "n/a (0)"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({k}/{n}; 95% CI {100 * lo:.1f}-{100 * hi:.1f}%)"


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

# ---------------------------------------------------------------------------------------------------------- analysis
def analyze():
    import numpy as np, pandas as pd
    frames = frame_table()
    fmap = {f["frame_id"]: f for f in frames}
    rec = cached()
    okg = ok_ids()
    log_lines = []

    def P(s=""):
        print(s, flush=True)
        log_lines.append(s)

    n_manifest = sum(1 for f in frames if f["src"] == "grades")
    n_prior = sum(1 for f in frames if f["src"] != "grades")
    on_disk = sum(1 for f in frames if f["src"] == "grades" and os.path.exists(f["path"]))
    P(f"## 0. Frames: manifest {n_manifest} grades frames | cutter log ok {len(okg)} | on disk {on_disk} | OCR'd {sum(1 for r in rec.values() if r['src']=='grades')}"
      f" | + prior-batch frames of graded pairs {n_prior} (OCR'd {sum(1 for r in rec.values() if r['src']!='grades')})")
    partial = {r["frame_id"]: r for r in read_tsv(f"{VIS}/grades_screen_partial.tsv")}

    eras = {}
    def era_for(day):
        n = "A" if day <= ERA_A_LAST else "B"
        if n not in eras:
            eras[n] = Era(n)
        return eras[n]

    ordinal = lambda s: int(np.datetime64(s, "D").astype("int32"))
    rows = []
    rng_master = 705
    for fid, r in sorted(rec.items()):
        if fid not in fmap:                      # cached earlier but no longer in the frame table (e.g. planted wrong-ticker test frames)
            continue
        fr = fmap[fid]
        s = r["scr"]
        labels, axes = labels_for(r)
        tab_screen = s["tabs"].split("|")[0] if s["tabs"] else ""
        daily_orig = bool(s["daily_tab"])
        tabs_ext = r["tabs_ext"]
        tab_tick = tab_screen or (tabs_ext[0] if tabs_ext else "")
        daily_ext = bool(tab_tick)
        ticker = tab_tick or s["ticker"]
        sd = s["screen_date"]
        try:                                     # a taskbar read is trusted only if the video was uploaded 0-30 days after it
            gap = (np.datetime64(fr["ref_date"], "D") - np.datetime64(sd, "D")).astype(int) if sd else None
        except Exception:
            gap = None
        date_src = "taskbar" if (sd and gap is not None and 0 <= gap <= 30) else "ref_date"
        sdate = sd if date_src == "taskbar" else fr["ref_date"]
        rows.append(dict(frame_id=fid, src=fr["src"], vid=fr["vid"], ts=fr["ts"], caption=fr["caption"], ref_date=fr["ref_date"], ticker=ticker,
                         ocr_orig_ticker=s["ticker"], daily_orig=int(daily_orig), daily=int(daily_ext), screen_date=sdate, date_src=date_src,
                         adr=r["adr"], labels=labels, n_axes=len(axes), n_tag=sum(1 for _, t in labels if t), n_labels=len(labels)))
    df = pd.DataFrame(rows)
    if df.empty:
        P("no OCR'd frames yet")
        return
    # ---- sanity vs the earlier partial screen
    pp = df[df.frame_id.isin(partial)]
    same_t = sum(1 for _, x in pp.iterrows() if x.ocr_orig_ticker == partial[x.frame_id]["ticker"])
    same_d = sum(1 for _, x in pp.iterrows() if (x.screen_date if x.date_src == "taskbar" else "") == partial[x.frame_id]["screen_date"])
    P(f"## 1. OCR extraction ({len(df)} frames)")
    P(f"- re-read agrees with the earlier partial screen on {same_t}/{len(pp)} tickers and {same_d}/{len(pp)} dates")
    P(f"- daily tab found: original crop {int(df.daily_orig.sum())}/{len(df)} ({100*df.daily_orig.mean():.1f}%) | with the full-frame '-1D/-D/XXXX Daily' fallback {int(df.daily.sum())}/{len(df)} ({100*df.daily.mean():.1f}%)")
    P(f"- screen date: taskbar {int((df.date_src=='taskbar').sum())} | fallback to the video upload date {int((df.date_src=='ref_date').sum())} "
      f"(of which taskbar read implausible/out of 0-30 d before upload: {sum(1 for r_ in rec.values() if r_['frame_id'] in fmap and r_['scr']['screen_date'] and df.set_index('frame_id').loc[r_['frame_id'], 'date_src']=='ref_date')})")
    P(f"- 'ADR x,y%' read: {int((df.adr.map(len)>0).sum())}/{len(df)} | price axis found: {int((df.n_axes>0).sum())}/{len(df)} | frames with an off-grid price tag: {int((df.n_tag>0).sum())}/{len(df)}")

    # ---- upload date vs taskbar date (justifies the ref_date fallback)
    tb = df[df.date_src == "taskbar"]
    dd = collections.Counter((ordinal(x.ref_date) - ordinal(x.screen_date)) for _, x in tb.iterrows())
    P(f"- upload date minus taskbar date (days), {len(tb)} frames: " + ", ".join(f"{k}d:{v}" for k, v in sorted(dd.items())[:8])
      + f"  -> same day {100*dd[0]/max(1,len(tb)):.1f}%")

    # ---- metrics for true + control tickers
    P("\n## 2. Rebuild from our bars (true on-screen ticker + 10 random wrong tickers per frame)")
    res = []
    n_nodata = 0
    for _, x in df.iterrows():
        er = era_for(x.screen_date)
        m0, m1 = er.sessions(ordinal(x.screen_date))
        if m0 is None:
            continue
        pool = None
        def evaluate(tk):
            m = er.metrics(tk, m0, m1)
            if m is None:
                return None
            out = {}
            for f in ("a", "b"):
                bd = adr_diff(x.adr, m["adr_" + f])
                out["adr_" + f] = None if bd is None else bd[0]
                out["sgn_" + f] = None if bd is None else bd[1]
                out["end_" + f] = None if bd is None else bd[2]
            out["p_any"], out["p_tag"], out["p_tick"] = price_hits(x.labels, m["lohi"])
            return out
        t_true = x.ticker
        e0 = evaluate(t_true) if t_true else None
        cap = evaluate(x.caption) if x.caption and x.caption != t_true else None
        pool = [t for t in er.eligible(m0) if t != t_true]
        rr = random.Random(f"{rng_master}-{x.frame_id}")
        ctl = [evaluate(t) for t in rr.sample(pool, min(N_CONTROL, len(pool)))]
        ctl = [c for c in ctl if c is not None]
        res.append(dict(frame_id=x.frame_id, true=e0, cap=cap, ctl=ctl, era=("A" if m0 <= ordinal(ERA_A_LAST) else "B")))
    R = {r["frame_id"]: r for r in res}
    df["has_bars"] = df.frame_id.map(lambda f: int(f in R and R[f]["true"] is not None))
    P(f"- frames with a readable screen ticker + our bars on the screen date: {int(df.has_bars.sum())}/{len(df)}  "
      f"(no ticker read {int((df.ticker=='').sum())}, ticker not in our bars on that date {int(((df.ticker!='') & (df.has_bars==0)).sum())})")

    # ---- calibration set: caption == screen ticker, daily tab, taskbar date
    cal_ids = [x.frame_id for _, x in df.iterrows() if x.has_bars and x.ticker == x.caption and x.daily and x.date_src == "taskbar" and len(x.adr) > 0]
    P(f"\n## 3. ADR definition + tolerance, from the {len(cal_ids)} caption==screen frames (daily tab, taskbar date, ADR read)")
    for f, name in (("a", "mean((H-L)/C) x100"), ("b", "(mean(H/L)-1) x100  [TC2000 / Qullamaggie ADR%]")):
        d = np.array([R[i]["true"]["adr_" + f] for i in cal_ids if R[i]["true"]["adr_" + f] is not None])
        sg = np.array([R[i]["true"]["sgn_" + f] for i in cal_ids if R[i]["true"]["sgn_" + f] is not None])
        P(f"- formula {f}: {name}: |OCR-ours| median {np.median(d):.2f}, p75 {np.percentile(d,75):.2f}, p90 {np.percentile(d,90):.2f}; "
          f"signed (OCR minus ours, nearest end) median {np.median(sg):+.2f}; within 0.3 {100*(d<=0.3).mean():.0f}% | 0.6 {100*(d<=0.6).mean():.0f}% | 1.0 {100*(d<=1.0).mean():.0f}% (n={len(d)})")
        ends = collections.Counter(R[i]["true"]["end_" + f] for i in cal_ids if R[i]["true"]["end_" + f] is not None)
        P(f"    nearest end session: screen-date session {ends.get(0,0)}, prior session {ends.get(1,0)}")
    med = {f: np.median([R[i]["true"]["adr_" + f] for i in cal_ids if R[i]["true"]["adr_" + f] is not None]) for f in ("a", "b")}
    F = "a" if med["a"] <= med["b"] else "b"
    P(f"- FORMULA USED (lower median error on the matched frames): {F}  ({'task wording' if F=='a' else 'H/L form'}); signed offset shown above decides if 0.6 is fair")
    for tol in (0.3, 0.6, 1.0):
        k = sum(1 for i in cal_ids if R[i]["true"]["adr_" + F] is not None and R[i]["true"]["adr_" + F] <= tol)
        allc = [c["adr_" + F] for r in R.values() for c in r["ctl"] if c["adr_" + F] is not None]
        P(f"- tolerance {tol}: true-ticker match {pct(k, len(cal_ids))} | WRONG-ticker false match {pct(sum(1 for v in allc if v <= tol), len(allc))}")
    P(f"- TOLERANCE USED: {TOL_ADR} (fixed in advance by the task; the table above is the justification, not a re-tune)")

    # ---- the checks
    def flags(c, x):
        if c is None:
            return None
        a = c["adr_" + F] is not None and c["adr_" + F] <= TOL_ADR
        return dict(adr=a, p_any=c["p_any"], p_tag=c["p_tag"], p_tick=c["p_tick"])
    def rule(fl, daily=True):
        return dict(spec=(fl["adr"] or fl["p_any"]), a=fl["adr"], b=fl["p_any"], b_tag=fl["p_tag"], b_tick=fl["p_tick"],
                    adr_and_tag=(fl["adr"] and fl["p_tag"]), adr_or_tag=(fl["adr"] or fl["p_tag"]), adr_and_any=(fl["adr"] and fl["p_any"]))
    names = [("a: ADR", "a"), ("b: any axis label in raw range", "b"), ("   b-tag: off-grid price tag only", "b_tag"), ("   b-tick: round ticks only", "b_tick"),
             ("a OR b  [spec CONFIRMED rule, before the daily-tab gate]", "spec"), ("a OR b-tag", "adr_or_tag"), ("a AND b-tag", "adr_and_tag"), ("a AND b", "adr_and_any")]
    true_fl = {i: rule(flags(R[i]["true"], None)) for i in R if R[i]["true"] is not None}
    ctl_fl = [rule(flags(c, None)) for i in R for c in R[i]["ctl"]]
    cal_set = [i for i in cal_ids if i in true_fl]
    all_true = [i for i in true_fl if df.set_index("frame_id").loc[i, "daily"] == 1]
    P(f"\n## 4. Match rates: POSITIVE control (caption==screen, n={len(cal_set)}) | all frames with a daily tab + bars (n={len(all_true)}) | NEGATIVE control: random wrong ticker (n={len(ctl_fl)} draws, {len(R)} frames)")
    for nm, k in names:
        P(f"- {nm}: positive {pct(sum(1 for i in cal_set if true_fl[i][k]), len(cal_set))} | all-daily {pct(sum(1 for i in all_true if true_fl[i][k]), len(all_true))} | FALSE-MATCH {pct(sum(1 for c in ctl_fl if c[k]), len(ctl_fl))}")
    # frames lacking an axis can only be confirmed by ADR
    noaxis = [i for i in all_true if df.set_index("frame_id").loc[i, "n_axes"] == 0]
    P(f"- frames with a daily tab but NO price axis found (price check cannot fire): {len(noaxis)}/{len(all_true)}")

    # pre-declared small = false match <= 5% per wrong ticker for the confirm rule
    fm = {k: sum(1 for c in ctl_fl if c[k]) / max(1, len(ctl_fl)) for _, k in names}
    SPEC_OK = fm["spec"] <= 0.05
    if SPEC_OK:
        CONF_KEY, CONF_NOTE = "spec", "spec rule (daily tab AND (a OR b)): false match <= 5% (pre-declared 'small')"
    else:
        cands = [k for k in ("adr_or_tag", "adr_and_any", "adr_and_tag") if fm[k] <= 0.05]
        pos = {k: sum(1 for i in cal_set if true_fl[i][k]) / max(1, len(cal_set)) for k in cands}
        CONF_KEY = max(pos, key=pos.get) if pos else "adr_and_tag"
        CONF_NOTE = (f"spec rule's false match {100*fm['spec']:.1f}% is NOT small (> 5% pre-declared): CONFIRMED tightened to '{CONF_KEY}' "
                     f"(false match {100*fm[CONF_KEY]:.1f}%, positive {100*pos.get(CONF_KEY, 0):.1f}%); the spec rule is kept as a column 'confirmed_spec'")
    P(f"- CONFIRMED RULE USED FOR LABELS: {CONF_NOTE}")

    # ---- per-frame verdict table
    di = df.set_index("frame_id")
    out_rows = []
    for fid, x in di.iterrows():
        r = R.get(fid)
        fl = true_fl.get(fid)
        daily = int(x.daily)
        d = dict(frame_id=fid, src=x.src, vid=x.vid, ts=x.ts, caption_ticker=x.caption, ocr_ticker=x.ticker, daily_tab=daily,
                 screen_date=x.screen_date, date_src=x.date_src, adr_read="|".join(f"{a:g}" for a in x.adr), n_axes=int(x.n_axes), n_tag=int(x.n_tag),
                 has_bars=int(x.has_bars))
        if fl:
            tr = R[fid]["true"]
            d.update(adr_ok=int(fl["a"]), price_ok=int(fl["b"]), price_tag_ok=int(fl["b_tag"]), price_tick_ok=int(fl["b_tick"]),
                     adr_absdiff=("" if tr["adr_" + F] is None else round(tr["adr_" + F], 2)), adr_signed=("" if tr["sgn_" + F] is None else round(tr["sgn_" + F], 2)),
                     confirmed_spec=int(daily and fl["spec"]), confirmed=int(daily and fl[CONF_KEY]))
        else:
            d.update(adr_ok="", price_ok="", price_tag_ok="", price_tick_ok="", adr_absdiff="", adr_signed="", confirmed_spec=0, confirmed=0)
        out_rows.append(d)
    cf = pd.DataFrame(out_rows)
    cf.to_csv(f"{VIS}/grades_frame_check.tsv", sep="\t", index=False)

    # ---- confirmed counts + caption-vs-screen
    P(f"\n## 5. CONFIRMED frames")
    for nm, sub in (("all", cf), ("grades frames", cf[cf.src == "grades"])):
        P(f"- {nm}: confirmed (used rule) {pct(int(sub.confirmed.sum()), len(sub))} | spec rule {int(sub.confirmed_spec.sum())} | daily tab {int(sub.daily_tab.sum())} | a alone {int((sub.adr_ok==1).sum())} | b alone {int((sub.price_ok==1).sum())}")
    for ds in ("taskbar", "ref_date"):
        sub = cf[cf.date_src == ds]
        P(f"- date source {ds}: n={len(sub)}, confirmed {int(sub.confirmed.sum())} ({100*sub.confirmed.mean() if len(sub) else 0:.1f}%)")
    both = cf[(cf.ocr_ticker != "") & (cf.caption_ticker != "")]
    agree = both[both.ocr_ticker == both.caption_ticker]
    P(f"- caption ticker == screen ticker: {pct(len(agree), len(both))} of frames where both are read")
    P(f"- among agreeing frames: confirmed {int(agree.confirmed.sum())}/{len(agree)} ({100*agree.confirmed.mean():.1f}%)")
    dis = both[both.ocr_ticker != both.caption_ticker]
    P(f"- disagreeing frames {len(dis)}: confirmed on the SCREEN ticker {int(dis.confirmed.sum())} ({100*dis.confirmed.mean():.1f}%); "
      f"the CAPTION ticker also passes the same checks on {sum(1 for f in dis.frame_id if R.get(f) and R[f]['cap'] and rule(flags(R[f]['cap'], None))[CONF_KEY])}"
      f"/{sum(1 for f in dis.frame_id if R.get(f) and R[f]['cap'])} (evaluable) -> low = the screen read is the right one")
    pat = collections.Counter()
    ex = collections.defaultdict(list)
    for _, x in dis.iterrows():
        c, s = x.caption_ticker, x.ocr_ticker
        d = lev(c, s)
        if c in s or s in c:
            k = "caption is a substring of screen (or vice versa)  e.g. DOG->DDOG"
        elif d == 1:
            k = "one character off"
        elif d == 2:
            k = "two characters off"
        else:
            k = "different ticker"
        pat[(k, bool(x.confirmed))] += 1
        ex[k].append(f"{c}->{s}{'*' if x.confirmed else ''}")
    for (k, cfm), n in sorted(pat.items(), key=lambda t: (-t[1], t[0])):
        P(f"    {k} | screen confirmed={cfm}: {n}")
    pairs = collections.Counter((x.caption_ticker, x.ocr_ticker) for _, x in dis[dis.confirmed == 1].iterrows())
    P("- most common CONFIRMED caption->screen swaps: " + ", ".join(f"{a}->{b} x{n}" for (a, b), n in pairs.most_common(25)))
    for k, v in ex.items():
        P(f"    e.g. {k}: " + ", ".join(v[:14]) + "   (* = screen ticker confirmed)")

    # ---- by year (a systematic layout / era failure would show here)
    cf["year"] = cf.screen_date.str[:4]
    P("\n- by screen-date year: frames | daily tab | our bars exist | a | b | confirmed(used) | confirmed(spec) | upload-date fallback")
    for y, g in cf.groupby("year"):
        hb = g[g.has_bars == 1]
        P(f"    {y}: {len(g)} | {int(g.daily_tab.sum())} | {len(hb)} | {int((hb.adr_ok==1).sum())} | {int((hb.price_ok==1).sum())} | {int(g.confirmed.sum())} | {int(g.confirmed_spec.sum())} | {int((g.date_src=='ref_date').sum())}")
    nd = cf[(cf.daily_tab == 0) & (cf.has_bars == 1)]
    nd_ok = nd[(nd.adr_ok.astype(str) == "1") & (nd.price_ok.astype(str) == "1")]
    P(f"- no daily tab read (tab hidden by a broadcast overlay / unreadable): {int((cf.daily_tab==0).sum())} frames, {len(nd)} with our bars; of those ADR AND price both match for {len(nd_ok)} "
      f"(NOT confirmed: the spec requires the tab; would add {len(nd_ok)} frames if the tab gate were dropped, false-match unchanged at the a-AND-b level)")
    miss = cf[(cf.has_bars == 0) & (cf.ocr_ticker != "")]
    P(f"- on-screen ticker NOT in our bars on that date (delisted, renamed, or too new (<20 sessions): the era files carry today's survivors): {len(miss)} frames, {miss.ocr_ticker.nunique()} tickers; "
      "most frequent: " + ", ".join(f"{t} {n}" for t, n in miss.ocr_ticker.value_counts().head(12).items()) + "  -> UNVERIFIABLE, not failed")
    bad = cf[(cf.caption_ticker == cf.ocr_ticker) & (cf.daily_tab == 1) & (cf.has_bars == 1) & (cf.confirmed == 0)]
    P(f"- caption==screen frames the used rule does NOT confirm ({len(bad)}): " + "; ".join(
        f"{x.frame_id} {x.ocr_ticker} {x.screen_date} adr_read={x.adr_read or '-'} diff={x.adr_absdiff} price_ok={x.price_ok} tag_ok={x.price_tag_ok} axes={x.n_axes}" for _, x in bad.head(14).iterrows()))
    ctrl_ids = [i for i in ("g_0000", "g_0204", "g_0203") if i in set(cf.frame_id)]
    for i in ctrl_ids:
        x = cf[cf.frame_id == i].iloc[0]
        P(f"- positive control {i}: ticker {x.ocr_ticker} {x.screen_date} ({x.date_src}) daily={x.daily_tab} bars={x.has_bars} ADR read {x.adr_read} diff {x.adr_absdiff} | a={x.adr_ok} b={x.price_ok} tag={x.price_tag_ok} -> confirmed={x.confirmed}")

    # ---- where does the caption name the ticker that is NOT on screen?  Is the on-screen ticker mentioned nearby?
    sm0 = []
    for f in ("/Users/alvinfung/apollo_data/cb702/qm_streams/stream_moments.tsv", "/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022/stream_moments_ext.tsv"):
        if os.path.exists(f):
            sm0 += [(r["video"], float(r["t"]), r["ticker"]) for r in read_tsv(f)]
    near = collections.defaultdict(list)
    for v, t, tk in set(sm0):
        near[(v, tk)].append(t)
    cnt_tot = cnt_hit = 0
    offs = []
    for _, x in dis[dis.confirmed == 1].iterrows():
        tf = hms(x.ts) + 3
        ts_ = near.get((x.vid, x.ocr_ticker), [])
        cnt_tot += 1
        if ts_:
            o_ = min((t - tf for t in ts_), key=abs)
            if abs(o_) <= 180:
                cnt_hit += 1
                offs.append(o_)
    if cnt_tot:
        offs = np.array(offs) if offs else np.array([0.0])
        P(f"- caption != screen, screen CONFIRMED ({cnt_tot}): the on-screen ticker is itself named in the captions within 3 min of the frame in {cnt_hit} ({100*cnt_hit/cnt_tot:.0f}%); "
          f"nearest mention is BEFORE the frame in {int((offs<0).sum())}, AFTER in {int((offs>0).sum())} (median offset {np.median(offs):+.0f} s) -> the caption names a neighbouring chart")
    top = dis[dis.confirmed == 1].ocr_ticker.value_counts().head(10)
    P("- screen tickers that sit behind the most different captions (stuck / reference chart): " + ", ".join(f"{t} x{n}" for t, n in top.items()))

    # ---- labels
    P("\n## 6. LABEL SET")
    gm = read_tsv(f"{VIS}/graded_moments.tsv")
    # dwell time: how long does a ticker stay the subject? gap to the nearest moment of a DIFFERENT ticker in the same video
    allm = collections.defaultdict(list)
    for fpath in (f"{QS}/../../../../apollo_data/cb702/qm_streams/stream_moments.tsv",):
        pass
    sm = []
    for f in ("/Users/alvinfung/apollo_data/cb702/qm_streams/stream_moments.tsv", "/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022/stream_moments_ext.tsv"):
        if os.path.exists(f):
            sm += [(r["video"], float(r["t"]), r["ticker"]) for r in read_tsv(f)]
    byv = collections.defaultdict(list)
    for v, t, tk in set(sm):
        byv[v].append((t, tk))
    gaps = []
    for v, lst in byv.items():
        lst.sort()
        for i, (t, tk) in enumerate(lst):
            nxt = next((t2 - t for t2, k2 in lst[i + 1:] if k2 != tk), None)
            if nxt is not None:
                gaps.append(nxt)
    gaps = np.array(gaps)
    P(f"- window: grade words were matched on the extraction window (mention -30 s .. +30 s) and the frame is cut at mention+3 s, so the first moment's words lie in [-33, +27] s of the frame; "
      f"a LATER moment of the same pair borrows the frame only if its mention is within +-{WINDOW_S:.0f} s of the frame time.")
    P(f"  justification: gap from a ticker mention to the next DIFFERENT-ticker mention in the same video (n={len(gaps):,}): median {np.median(gaps):.0f} s, p25 {np.percentile(gaps,25):.0f} s, p10 {np.percentile(gaps,10):.0f} s; "
      f"{100*(gaps<=WINDOW_S).mean():.0f}% of mentions are followed by another ticker inside {WINDOW_S:.0f} s (the chart may already have changed) -> the window is kept at the caption half-width, no wider")
    frame_by_pair = {}
    frames_by_vid = collections.defaultdict(list)
    for f in frames:
        if f["frame_id"] in R or f["frame_id"] in di.index:
            tf = hms(f["ts"]) + 3
            frame_by_pair[(f["vid"], f["caption"])] = (f["frame_id"], tf)
            frames_by_vid[f["vid"]].append((tf, f["frame_id"]))
    lab = []
    status = collections.Counter()
    for m in gm:
        t = float(m["t"])
        own = frame_by_pair.get((m["video"], m["ticker"]))
        fid, fp, dtv = None, "", None
        st = "no_frame"
        if own:
            fid, tf = own
            dtv = t - tf
            if abs(dtv) <= WINDOW_S:
                fp, st = "own", "in_window"
            else:
                fid = None
        if fid is None:                                   # try a same-video frame (any pair) within the window, nearest in time
                cand = sorted((abs(t - tf2), tf2, f2) for tf2, f2 in frames_by_vid.get(m["video"], []) if abs(t - tf2) <= WINDOW_S)
                if cand:
                    fid, fp, dtv, st = cand[0][2], "borrowed", t - cand[0][1], "in_window"
                else:
                    st = "out_of_window" if own else "no_frame"
        row = dict(vid=m["video"], ts=m["ts"], screen_ticker="", screen_date="", grade=m["grades"], caption_ticker=m["ticker"], confirm_adr="",
                   confirm_price="", status=st, frame_id=fid or "", frame_pair=fp, dt_s=("" if dtv is None else f"{dtv:.1f}"), ocr_ticker="", date_src="")
        if fid and fid in di.index:
            c = cf[cf.frame_id == fid].iloc[0]
            row.update(ocr_ticker=c.ocr_ticker, date_src=c.date_src, confirm_adr=c.adr_ok, confirm_price=c.price_ok)
            if c.confirmed == 1:
                row.update(screen_ticker=c.ocr_ticker, screen_date=c.screen_date, status="attributed")
            elif c.has_bars == 0 and c.ocr_ticker != "":
                row.update(status="in_window_unverifiable_no_bars", screen_date=c.screen_date)
            elif c.daily_tab == 0:                         # ADR / price columns may both read 1: the daily-tab gate is what failed
                row.update(status="in_window_no_daily_tab", screen_date=c.screen_date)
            else:
                row.update(status="in_window_checks_failed", screen_date=c.screen_date)
            row["daily_tab"] = int(c.daily_tab)
        elif fid:
            row.update(status="frame_not_ocrd_yet")
        status[(row["status"], fp)] += 1
        lab.append(row)
    for row in lab:
        row.setdefault("daily_tab", "")
        row["triple_agree"] = int(row["status"] == "attributed" and row["screen_ticker"] == row["caption_ticker"])
        # 2026-10-23 verifier fix (blocking): a grade whose confirmed screen ticker differs from the ticker the caption named is NOT a
        # label — of 20 such quotes read by hand, 7 plainly belonged to the spoken ticker. They get their own status and stay out.
        if row["status"] == "attributed" and not row["triple_agree"]:
            row["status"] = "moved_unverified"
    fields = ["vid", "ts", "screen_ticker", "screen_date", "grade", "caption_ticker", "confirm_adr", "confirm_price", "status", "frame_id", "frame_pair", "dt_s", "ocr_ticker", "date_src", "daily_tab", "triple_agree"]
    with open(f"{VIS}/grades_labels.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(lab)
    L = pd.DataFrame(lab)
    P(f"- graded moments {len(L)} | status: " + ", ".join(f"{k[0]}{'/'+k[1] if k[1] else ''} {v}" for k, v in sorted(status.items(), key=lambda t: -t[1])))
    att = L[L.status == "attributed"]   # = the triple-agreement label set since the 10-23 fix; moved_unverified counted apart
    P(f"- ATTRIBUTED labels {len(att)}/{len(L)} ({100*len(att)/len(L):.1f}%) -> grades_labels.tsv (screen_ticker filled); the rest are unattributed")
    P("- attributed by grade: " + ", ".join(f"{g} {n}" for g, n in att.grade.value_counts().items()))
    ex_ = collections.Counter(g for gs in att.grade for g in gs.split(","))
    P("- attributed, grade words exploded: " + ", ".join(f"{g} {n}" for g, n in ex_.most_common()))
    P("- all moments by grade: " + ", ".join(f"{g} {n}" for g, n in L.grade.value_counts().items()))
    P(f"- attributed with caption == screen ticker: {int((att.caption_ticker == att.screen_ticker).sum())}/{len(att)}; caption != screen: {int((att.caption_ticker != att.screen_ticker).sum())} (the grade moves to the screen ticker)")
    P(f"- CLEAN SUBSET (triple agreement: caption == screen == confirmed): {int((att.caption_ticker == att.screen_ticker).sum())} labels ('triple_agree' = 1); the other attributed labels move the grade to a different ticker than the caption named")
    P(f"- attributed via own-pair frame {int((att.frame_pair=='own').sum())} | borrowed same-video frame {int((att.frame_pair=='borrowed').sum())}")
    P(f"- attributed by date source: " + ", ".join(f"{k} {v}" for k, v in att.date_src.value_counts().items()))
    P(f"- distinct (video, screen ticker) attributed {att.drop_duplicates(['vid','screen_ticker']).shape[0]}")
    un = L[L.status.isin(["in_window_checks_failed", "in_window_no_daily_tab", "in_window_unverifiable_no_bars", "out_of_window", "no_frame", "frame_not_ocrd_yet"])]
    P("- unattributed by reason: " + ", ".join(f"{k} {v}" for k, v in un.status.value_counts().items()))
    for stn in ("in_window_unverifiable_no_bars", "in_window_no_daily_tab", "in_window_checks_failed"):
        u = L[L.status == stn]
        P(f"    {stn}: {len(u)} moments; the OCR'd on-screen ticker equals the caption ticker on {int((u.ocr_ticker == u.caption_ticker).sum())} of them "
          f"(two independent reads agree, but our bars cannot / did not confirm) - NOT attributed")
    P("\nFiles: " + f"{VIS}/grades_labels.tsv, {VIS}/grades_frame_check.tsv, {VIS}/grades_frame_ocr_s*.jsonl (OCR cache)")
    open(os.path.join(HERE, "03_frame_check.txt"), "w").write("\n".join(log_lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", "ocr", "analyze"])
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if a.stage == "ocr":
        i, n = [int(x) for x in a.shard.split("/")]
        return ocr_stage(i, n, set(a.only.split(",")) if a.only else None, a.out or None)
    if a.stage == "all":
        ps = [subprocess.Popen([OCR_PY, os.path.abspath(__file__), "--stage", "ocr", "--shard", f"{i}/{a.workers}"]) for i in range(a.workers)]
        for p in ps:
            p.wait()
    analyze()


if __name__ == "__main__":
    sys.exit(main())
