#!/usr/bin/env python3
"""#705 (2026-10-24, $0, local): read Qullamaggie's 'A - Positions' watchlist panel (his holdings) off TC2000 stream frames.

The panel sits in the right-hand column of his screen (usually bottom-right): a header line 'A - Positions' (or 'A -' with the
title hidden behind the linked-symbol box 'Syms XXXX'), a column header 'Flag | Sym | % Change | ...', one row per holding, and
a footer 'N Items in Personal WatchList' / 'N of M Items in Personal WatchList'.  Other panels ('1 - WL', 'US Comm Stks',
'S - Lower Liq Higher ADR', the top-left 'zz' / 'My' lists) are never read: the header must start 'A -' (or carry 'Positions').

Per frame (Apple Vision OCR, local):
  1. taskbar date              - vision_ocr_screen.screen() (the same crop + regex the other #702/#705 probes use)
  2. LOCATE (pass A)           - OCR the right half of the frame (2x, 3x for 1280x720); header = a token starting 'A -' in
                                 x >= 0.5 W; footer = the first 'Items in' line below it at the same left edge (no other panel
                                 header in between); column header = the 'Flag Sym' line under the header.
  3. COLUMN                    - the Sym column = the cell between the panel's vertical grid lines that holds the 'Sym' word
                                 (pixel profile of the grey grid), fallback fixed offsets from the panel's left edge.
  4. ROWS                      - one row per band of bright text pixels in the Sym column between the column header and the
                                 footer (so a row the OCR misses is still counted, and a half-visible last row counts).
  5. READ (pass B)             - OCR the Sym column crop, several scales x (inverted / not); unread rows retried one by one.
  6. VOTE + LEXICON (analyse)  - per row, the majority read; when it is not a ticker that traded within +-10 days of the
                                 screen date in our bar files (cb702_pre_v2 2016-22 + cb702 2021-26), a minority read or a
                                 one-confusion-away ticker (O/Q/D/0, B/E/F/P, I/L/1, M/N, V/Y, ...) that IS one replaces it,
                                 and the row is flagged 'corrected'.  1920x1080 rows whose reads all agree are never corrected
                                 (a real ticker can be missing from our bars: SI in 2021).

    python 01_read_panel.py --stage all [--workers 4] [--frames-dir DIR] [--out FILE.jsonl]
    python 01_read_panel.py --stage ocr --shard i/n        # (run under venvs/ocr/bin/python; resumable cache)
    python 01_read_panel.py --stage analyze                # pure python: vote + lexicon + summary -> 01_read_panel.txt
    python 01_read_panel.py --stage crops --only g_0814,g_1985   # write enlarged panel crops for checking by eye

v15 (2026-10-24, the same card's extension): both frame folders in one run, 'B - Positions' lists (2017), the % Change check.
    V=/Users/alvinfung/apollo_data/cb702/qm_streams/vision
    python 01_read_panel.py --stage run-all --workers 8 --frames-dir $V/frames_grades,$V/frames_positions --out $V/positions_panel_all.jsonl
    (= --stage ocr per shard under venvs/ocr/bin/python, then --stage analyze-all) -> positions_panel_all.jsonl (one line per frame:
    folder, vid, stream_ts, upload_date, screen_date, clock, et_time, list A/B, symbols, symbols_ocr, no_bars, rows with pct / pct_check /
    pct_was / pct_suggest, pct_ctx) and 02_read_all.txt.  The % check: see the v15 section below (pct_check()).

Outputs: --out (one json line per frame), OCR cache <out stem>_ocr_s<i>.jsonl, 01_read_panel.txt next to this file.
HARD: read-only on apollo_data except those outputs; no network; no paid calls."""
import argparse, bisect, collections, csv, datetime as dt, glob, gzip, json, os, pickle, re, subprocess, sys, tempfile, time
from zoneinfo import ZoneInfo

VIS = "/Users/alvinfung/apollo_data/cb702/qm_streams/vision"
HERE = os.path.dirname(os.path.abspath(__file__))
QS = os.path.join(os.path.dirname(HERE), "_qm_streams")
OCR_PY = "/Users/alvinfung/apollo_data/venvs/ocr/bin/python"
BARS = ["/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz", "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz"]
LEXICON = os.path.join(VIS, "positions_ticker_lexicon_v2.tsv")      # ticker, first/last in the 2016-22 file, first/last in the 2021-26 file
ALIAS_FILES = [("/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022/rename_map.tsv", ["polygon_ticker", "alpaca_symbol"]),
               ("/Users/alvinfung/apollo_data/cb702_pre_v2/dedupe_applied.tsv", ["dropped_symbol", "kept_symbol"]),
               ("/Users/alvinfung/apollo_data/cb702_pre/survivorship_1023/merged_trial2/refetch_dropped.tsv", ["symbol"])]
OCR_VER = 15                       # bump when the OCR stage changes: cached rows of an older version are re-read
# v15 (2026-10-24): 'B - Positions' lists (2017) are read too (tagged list=B, only when no 'A -' panel is found); the taskbar
# clock is OCR'd (rec['clock']); the % Change cell's text colour is counted per row (rec['pct_color'] = [green, red] pixels)

# the 4 frames checked by eye by the caller (2026-10-24) + the hand-checked frames (by eye on the enlarged crop, this card).
# 'exp' lists the symbols top to bottom; 'foot' = (first number, of-number or None).
REFERENCE = {
    "g_0814": dict(exp="YINN PBR ENDP RLGY BABA DXCM TEVA TDOC MNK BLDP JD MU QLED IPHI APPS FCEL SE", foot=(15, 17), by="caller",
                   screen="YINN PBR ENDP RLGY BABA DXCM TEVA TDOC MNK BLDP JD MU OLED IPHI APPS FCEL SE",
                   note="the caller's list says QLED; the screen (enlarged) and all 8 OCR variants show OLED = Universal Display, which traded "
                        "2019-11-12 at 199.09-208.01 (+2.3%, the panel shows about +2.9% at 09:44 ET); QLED has no bars at all - a transcription slip"),
    "g_1657": dict(exp="NKLA TQQQ TSLA WKHS ZS MELI SE BYND PDD BILI DKNG TWLO DDOG NET NVAX FSLY SHOP FMCI ZM", foot=(17, 19), by="caller"),
    "g_1985": dict(exp="AMAT AAL LRCX TSM SOXL ALB JETS RBLX TWTR TQQQ CLF FCX HOFV NTLA TIGR SI", foot=(20, None), by="caller"),
    "g_0957": dict(exp="CVNA FCX TNA CWEB YINN PDD MDGL GNS", foot=(7, 8), by="caller"),
}
# 10 frames picked by a fixed rule (seed 705, one per video, stratified 2018 x1, 2019-720p x2, 2020-720p x1, 2020 x2, 2021 x2, 2022 x1,
# 2023 x1, never a frame or video looked at while building) and written down from the enlarged right-column crop BEFORE the
# script's output for them was printed.
HAND = {
    "g_1645": dict(exp="AFMD BILI SPLK RH SEND OKTA COOL GRUB HFC VKTX SAIL ANET ETSY ROKU TSLA CGC", foot=(16, None),
                   note="2018 has one video: same list as dev frame g_1641, whose output was seen - not blind"),
    "g_1835": dict(exp="IGV ACAD TEVA RETA APPS ENDP RLGY PBR JCP BRZU MIK MNK", foot=(11, 12), note="1st symbol IGV by eye (IGV/KGV unsure)"),
    "g_1998": dict(exp="ENDP MNK BRZU PBR ACAD JCP MIK RLGY IGV PLUG TEVA APPS USLV", foot=(12, 17), note="scrolled; IGV as above"),
    "g_1951": dict(exp="BYND TEUM TSLA TDOC APPS LK STNE BABA HTHT DXCM ONTX AXSM FB SE AVLR RADA BE PLUG FCEL CTST VSTM OCGN MNK", foot=(19, 23),
                   note="1280x720 2020; header 'A - |' + Select Conditions row; first footer number unsure"),
    "g_0007": dict(exp="NVAX BE INO TDOC OSTK W ZS LAC VIR TSLA Z GBTC SPG GSX PINS", foot=(4, 15)),
    "g_2179": dict(exp="GBTC BYND NIO TSLA SE ZS LAC Z ESTC LVGO TWTR DDOG NVDA PTON CRWD ENPH FSLY BILI PLL", foot=(19, None),
                   note="the broadcast caption ('youtube') covers the start of the footer"),
    "g_1829": dict(exp="NVAX NET AGQ LRCX TNA SQM X ALB AMAT TQQQ ARKK RBLX", foot=(12, None)),
    "g_0309": dict(exp="NFLX FNGU SKLZ JMIA TDOC JWN M GUSH TAN FUSE XP XOP ABNB BNTX GBTC ACTC MARA WWR LAC", foot=(19, None)),
    "g_2153": dict(exp="FUTU FCX KWEB LAC F MU ERX LCID", foot=(4, 8), note="mouse cursor over the F row"),
    "g_0533": dict(exp="AI MNDY IMGN APLD PLTR IONQ DNA CVNA QBTS", foot=(9, 9)),
}

FAILURE_MODES = [
    "1280x720 frames (2019 - Jan 2020, 180 frames): ~6 px text; a look-alike read can be another real ticker (SDRL->SORL, DDS->COS->CCS, "
    "BW->EW, LK->LX, IGV->KV) - the lexicon cannot catch a wrong read that is itself a ticker; 3 of 4 hand-check misses are here. "
    "Every row keeps its votes / 'was' / 'how' so these can be re-judged; the '% Change' cell is already OCR'd (passPct) for a later "
    "check against that day's bar",
    "1280x720 footer counts: digits misread (30 of 31 -> 20 of 31, 19 of 23 -> 10 of 22): the 'of M' total is more reliable than the first number",
    "a real ticker missing from our bars is left as read and flagged not_in_bars (GBTC/ETHE OTC trusts, renamed: GSX, SPACs) - never corrected",
    "the header must be on screen: a pop-up (Messages) over the 'A -' header, a full-screen chart, or a layout without the right-hand "
    "column -> panel_found false (counted as not found, not misread)",
    "broadcast caption over the footer ('Type !start', 'youtube', 'qullamaggie.com'): total_n unknown; caption glyphs inside the list are dropped by height",
    "2017: the list is 'B - Positions' (33 frames) or absent; not read under the A-only rule",
    "a row half-hidden at the top / bottom of a scrolled list is read when possible and flagged 'partial'",
]

# ---------------------------------------------------------------------------------------------------------- regexes
HDR_RX = re.compile(r"^[^A-Za-z0-9]{0,3}A\s{0,2}[-\u2013\u2014~]")          # 'A - Positions', 'A -*Syms SHOP', ':A -'
POS_RX = re.compile(r"P[o0]s[il]?t[il]?o|Positi|Posit")      # 'Positions', 'Postions' (720p), 'Positio' (cut)
OTHER_HDR_RX = re.compile(r"^[^A-Za-z0-9]{0,3}(?:[B-Z0-9]|[A-Z0-9]{2})\s{0,2}[-\u2013\u2014]\s?[A-Za-z]")   # '1 - WL', 'S - Lower..'
FOOT_RX = re.compile(r"(?:Items?|ltems?|1tems?|Itens|tems)\s*[il1]n|\b[il1]n\s+P\w{3,9}\s*W|\b[il1]n\s+W[a-z]{2,6}\s?L|WatchL|Watchl|WaschL"
                     r"|P[ae][rm]{0,2}s{1,2}on[au]l|Persona|P\w{1,3}s{0,2}on[au][l1]|W\w{1,4}[hc][Ll][a-z]", re.I)
COL_RX = re.compile(r"(?:^|[^A-Za-z])S[yveo](?:m|n|rn)(?![a-z])|^\W{0,2}(?:Flag|Fiag|Fag|Peg|Pleg|Rag|Fao|Fisg|Flsg|Teg)\b")
B_HDR_RX = re.compile(r"^[^A-Za-z0-9]{0,3}B\s{0,2}[-\u2013\u2014~]\s{0,2}(?:P[o0]s[il]?t[il]?o|Positi|Posit)")   # 'B - Positions' (2017)
NOT_A_RX = re.compile(r"^[^A-Za-z0-9]{0,3}A\s{0,2}[-\u2013\u2014~]\s*(?:WL|W|L)(?![A-Za-z])")   # 'A-L#' = the '1 - L' list misread
# (only L / W / WL: the '|' next to the symbol box of the real header reads 'I' - 'A -I* Syms LRCX')
FOOT_LOOSE = re.compile(r"^\D{0,2}\d{1,3}\s")
FOOT_NUM = re.compile(r"^\D{0,3}(\d{1,3})\s*(?:[oaec0OóQ][fFtTre/]?\.?\s*(\d{1,3}))?(?!\d)")
SYM_RX = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")
STOP = {"FLAG", "SYM", "SYMS", "FLAGSYM", "FAG", "PEG", "FIAG", "FLSG"}
CYR = str.maketrans({"А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
                     "Б": "B", "Д": "A", "И": "N", "П": "N", "Л": "N", "У": "Y", "Ф": "O", "Ц": "U", "Ш": "W", "Э": "E", "Я": "R",
                     "Ѕ": "S", "І": "I", "Ј": "J", "Ԛ": "Q", "Ү": "Y", "Ζ": "Z", "Ι": "I", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X",
                     "Υ": "Y", "Β": "B", "Ε": "E", "Ν": "N", "Μ": "M", "Κ": "K", "Η": "H", "Α": "A", "Ю": "O", "ю": "O",
                     "Ø": "O", "Ö": "O", "Ü": "U", "Ä": "A", "Å": "A", "É": "E"})
DIG = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G", "4": "A", "7": "T", "3": "B", "9": "G"})

# ---------------------------------------------------------------------------------------------------------- OCR primitives
def _vision():
    import Quartz, Vision
    from Foundation import NSURL
    return Quartz, Vision, NSURL


def ocr_raw(path):
    """[(text, conf, x0, y0, x1, y1)] in the image's pixel coords (y from the top)."""
    Quartz, Vision, NSURL = _vision()
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
            out.append((str(c[0].string()), round(float(c[0].confidence()), 2), bb.origin.x * w, (1 - bb.origin.y - bb.size.height) * h,
                        (bb.origin.x + bb.size.width) * w, (1 - bb.origin.y) * h))
    return out


def ocr_box(im_rgb, box, scale, invert=True):
    """OCR a crop of an already-open RGB image, upscaled; tokens back in frame pixel coords."""
    import tempfile
    from PIL import Image, ImageOps
    g = im_rgb.crop(box).convert("L")
    g = ImageOps.autocontrast(ImageOps.invert(g) if invert else g)
    g = g.resize((max(1, g.width * scale), max(1, g.height * scale)), Image.LANCZOS)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    g.save(tmp)
    try:
        items = ocr_raw(tmp)
    finally:
        os.remove(tmp)
    return [[t, c, round(box[0] + x0 / scale, 1), round(box[1] + y0 / scale, 1), round(box[0] + x1 / scale, 1), round(box[1] + y1 / scale, 1)]
            for t, c, x0, y0, x1, y1 in items]

# ---------------------------------------------------------------------------------------------------------- pixel profiles
def is_grid(p):
    r, g, b = p[:3]
    L = (r + g + b) / 3
    return 28 <= L <= 135 and max(r, g, b) - min(r, g, b) < 30


def is_ink(p):
    r, g, b = p[:3]
    return min(r, g, b) > 100 or max(r, g, b) > 175


def vertical_dividers(px, x0, x1, y0, y1, s, frac=0.5):
    """x runs (x_start, x_end) where >= frac of the pixels down the rows are grid-grey (the column lines).  Grey anti-aliased edges
    of the text can pass the test on a short list (1 row): runs closer than 12 px keep only the most grid-like one."""
    if y1 - y0 < 4:
        return []
    fx = []
    for x in range(x0, x1):
        g = sum(1 for y in range(y0, y1) if is_grid(px[x, y])) / (y1 - y0)
        if g >= frac:
            fx.append((x, g))
    runs = []
    for x, g in fx:
        if runs and x - runs[-1][1] <= 1:
            runs[-1][1] = x
            runs[-1][2] = max(runs[-1][2], g)
        else:
            runs.append([x, x, g])
    kept = []
    for r in runs:
        if kept and r[0] - kept[-1][1] < 12 * s:
            if r[2] > kept[-1][2] + 0.05:
                kept[-1] = r
            continue
        kept.append(r)
    return [[a, b] for a, b, _ in kept]


def ink_bands(px, x0, x1, y0, y1, s):
    """row bands [y0, y1, ink, ink_x0, ink_x1]: runs of y with bright text pixels in the Sym column; gaps of one empty line are
    bridged.  The ink's x-extent lets a lone 'I' (a bare stroke Vision will not read) be recognised by shape."""
    rows = []
    for y in range(y0, y1):
        xs = [x for x in range(x0, x1) if is_ink(px[x, y])]
        rows.append((y, len(xs), min(xs) if xs else None, max(xs) if xs else None))
    bands, cur = [], None
    for y, v, a, b in rows:
        if v >= 1:
            if cur and y - cur[1] <= 2:
                cur[1] = y
                cur[2] += v
                cur[3], cur[4] = min(cur[3], a), max(cur[4], b)
            else:
                if cur:
                    bands.append(cur)
                cur = [y, y, v, a, b]
    if cur:
        bands.append(cur)
    bands = [b for b in bands if b[1] - b[0] + 1 >= max(2, round(3 * s)) and b[2] >= 3]     # >= 3: a lone 'I' at 1280x720 is ~4 px
    if bands:                                   # a glyph of the broadcast caption ('qullamaggie.com') is 3-6x a row's height
        hs = sorted(b[1] - b[0] + 1 for b in bands)
        med = hs[len(hs) // 2]
        bands = [b for b in bands if b[1] - b[0] + 1 <= max(13 * s, 2.2 * med)]
    return bands


# ---------------------------------------------------------------------------------------------------------- locate (pure, on tokens)
def yc(t):
    return (t[3] + t[5]) / 2


def panel_lines(toks, x0, s):
    """tokens -> text lines (same baseline, left to right) that START at the panel's left edge (within 30 px); each line is a
    token-like list [text, conf, x0, y0, x1, y1] so a footer split by Vision into '23 ise' + 'Pemsonal WachLat' is read whole."""
    toks = sorted(toks, key=lambda t: (yc(t), t[2]))
    lines = []
    for t in toks:
        for L in lines:
            if abs(yc(t) - L["yc"]) <= 4 * s:
                L["t"].append(t)
                break
        else:
            lines.append(dict(yc=yc(t), t=[t]))
    out = []
    for L in lines:
        ts = sorted(L["t"], key=lambda t: t[2])
        if abs(ts[0][2] - x0) > 30 * s:
            continue
        out.append([" ".join(t[0] for t in ts), min(t[1] for t in ts), ts[0][2], min(t[3] for t in ts), ts[-1][4], max(t[5] for t in ts)])
    return sorted(out, key=lambda t: t[3])


def is_a_header(text):
    """'A - Positions' / 'A -' (+ the symbol box).  Not 'B - Positions' (a 2017 list), not TC2000's 'Position Summary' / 'Positions
    Spreads' panels, not the '1 - L' list misread 'A-L'."""
    if HDR_RX.match(text) and not NOT_A_RX.match(text):
        return True
    m = POS_RX.search(text)
    return bool(m and re.match(r"^\W{0,3}(?:A\s{0,2})?[-\u2013\u2014~]?\s{0,2}$", text[:m.start()]) and HDR_RX.match(text[:m.start()] + " ")
                and not re.search(r"Summ|Spread", text[m.start():]))


def hdr_kind(text):
    """'A' for an 'A - Positions' / 'A -' header, 'B' for a 'B - Positions' header (the 2017 list; unlike A its title is never
    hidden behind the symbol box, so a bare 'B -' - another list - is never taken), else None."""
    if is_a_header(text):
        return "A"
    if B_HDR_RX.match(text):
        return "B"
    return None


def locate(toks, W, H, cands=None):
    """the positions panel: an 'A -' panel when there is one (exactly the v14 rule), else a 'B - Positions' panel (2017)."""
    if cands is None:
        cands = [dict(tok=t, src="passA", reread=[]) for t in toks if t[2] >= 0.5 * W and hdr_kind(t[0])]
    for kind in ("A", "B"):
        loc = locate_kind(toks, W, H, [c for c in cands if hdr_kind(c["tok"][0]) == kind], kind)
        if loc is not None:
            return loc
    return None


def locate_kind(toks, W, H, cands, kind):
    """the positions panel of one list kind: header, footer, column header.  `cands` = [dict(tok, src, reread=[texts])] from
    header_candidates()."""
    s = W / 1920
    best = None
    for c in cands:
        h = c["tok"]
        x0 = h[2]
        reads = [h[0]] + c.get("reread", [])
        if kind == "B":
            n_ok = sum(1 for r in reads if hdr_kind(r) == "B")
            pos = True                                    # the B header is taken only with 'Positions' in it
        else:
            n_ok = sum(1 for r in reads if is_a_header(r))
            pos = any(POS_RX.search(r) and is_a_header(r) for r in reads)
        c["n_ok"], c["pos"] = n_ok, pos
        below = panel_lines([t for t in toks if t[3] > h[5] - 2 and x0 - 12 * s <= t[2] <= x0 + 200 * s and t is not h], x0, s)
        # the footer: 'N [of M] Items in Personal WatchList' - at 1280x720 it reads like '15 af 17 isenia in Pesonul WwchLa', so a
        # line at the panel's left edge that starts with a count and runs >= 10 characters also counts (re-read enlarged below)
        # the FIRST such line below the header (its count may be unreadable - '24' read 'S' - the enlarged re-read gets it)
        foot = next((t for t in below if FOOT_RX.search(t[0]) or
                     (abs(t[2] - x0) <= 8 * s and FOOT_LOOSE.match(t[0]) and len(t[0]) >= 10 and "%" not in t[0]
                      and re.search(r"[a-z]{4,}", t[0]))), None)
        # another panel's header between this header and the footer -> that footer is not ours
        if foot is not None:
            mid = [t for t in below if t[3] < foot[3] and t[3] > h[5] + 30 * s and abs(t[2] - x0) <= 8 * s and "%" not in t[0]
                   and not FOOT_RX.search(t[0]) and (OTHER_HDR_RX.match(t[0]) or HDR_RX.match(t[0]))]   # a row reads '1- ICP +2,17%' 
            if mid:
                foot = None
        col = next((t for t in below if t[3] - h[5] <= 50 * s and COL_RX.search(t[0])), None)
        if col is not None:                              # the original token that holds 'Sym' (for the Sym column's x)
            col = next((t for t in toks if abs(yc(t) - yc(col)) <= 4 * s and x0 - 12 * s <= t[2] <= x0 + 60 * s and COL_RX.search(t[0])), col)
        # one lone 'A -' read that the enlarged re-reads do not repeat (Vision drops a bare 'A -' at 1280x720) is kept only when a
        # column header AND a footer sit under it - a whole panel; c['single'] marks it for the notes
        c["single"] = not pos and n_ok < 2
        if c["single"] and (foot is None or col is None):
            continue
        score = (3 if pos else 0) + min(n_ok, 3) + (2 if foot is not None else 0) + (1 if col is not None else 0)
        if best is None or score > best[0] or (score == best[0] and h[3] > best[1][3]):
            best = (score, h, foot, col, c)
    if best is None or (best[2] is None and best[3] is None):   # a header with neither a footer nor a column header under it is not a panel
        return None
    _, h, foot, col, c = best
    line = sorted([t for t in toks if abs(yc(t) - yc(h)) <= 6 * s and t[2] >= h[2] - 5 * s and t is not h], key=lambda t: t[2])
    line = [h] + [t for t in line if t[2] > h[2]]
    return dict(header=h, header_src=c["src"] + ("_single_read" if c.get("single") else ""), header_reread=c.get("reread", []), header_line=" ".join(t[0] for t in line), footer=foot, colhdr=col,
                list=kind)


def header_candidates(im, toks, W, H):
    """'A -' header tokens of pass A, plus a second, enlarged look at the line(s) above every right-half column header that has
    no candidate above it (Vision drops the short 'A -' at 1280x720); every candidate is re-read enlarged twice to confirm it."""
    s = W / 1920
    cands = [dict(tok=t, src="passA") for t in toks if t[2] >= 0.5 * W and hdr_kind(t[0])]
    sc = 3 if W >= 1500 else 5
    cols = [t for t in toks if t[2] >= 0.5 * W and COL_RX.search(t[0]) and len(t[0]) <= 14]
    for c in cols:
        if any(abs(d["tok"][2] - c[2]) <= 30 * s and -2 <= c[3] - d["tok"][5] <= 50 * s for d in cands):
            continue
        box = (int(max(0, c[2] - 6 * s)), int(max(0, c[3] - 50 * s)), int(min(W, c[2] + 175 * s)), int(max(1, c[3] - 1)))
        for inv in (1, 0):
            for t in ocr_box(im, box, sc, bool(inv)):
                if hdr_kind(t[0]) and abs(t[2] - c[2]) <= 30 * s and not any(abs(d["tok"][3] - t[3]) <= 6 * s and abs(d["tok"][2] - t[2]) <= 30 * s for d in cands):
                    cands.append(dict(tok=t, src="second_look"))
    rs = 4 if W >= 1500 else 6
    cands.sort(key=lambda d: hdr_kind(d["tok"][0]) != "A")     # stable: the A candidates first, in their v14 order
    for d in cands[:6]:
        h = d["tok"]
        box = (int(max(0, h[2] - 4 * s)), int(max(0, h[3] - 3 * s)), int(min(W, h[2] + 110 * s)), int(min(H, h[5] + 3 * s)))
        d["reread"] = [" ".join(t[0] for t in sorted(ocr_box(im, box, rs, bool(inv)), key=lambda t: t[2])) for inv in (1, 0)]
    return cands


def sym_x_est(col):
    """x of the word 'Sym' inside the column-header token (Vision often returns 'Flag Sym' as one token)."""
    if col is None:
        return None
    t = col[0]
    m = re.search(r"S[yveo][mn]", t)
    if not m:
        return None
    return col[2] + (col[4] - col[2]) * (m.start() + 1.5) / max(1, len(t))

# ---------------------------------------------------------------------------------------------------------- OCR stage
def frame_files(frames_dir):
    """the frames of one folder, or of several (comma-separated; ids g_ / p_ are disjoint)."""
    return sorted((p for d in frames_dir.split(",") for p in glob.glob(os.path.join(d, "*.png"))), key=os.path.basename)


def cache_files(out):
    stem = out[:-6] if out.endswith(".jsonl") else out
    return stem + "_ocr_s{}.jsonl", sorted(glob.glob(stem + "_ocr_s*.jsonl"))


def load_cache(out):
    d = {}
    for f in cache_files(out)[1]:
        for ln in open(f, encoding="utf-8"):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("ver") == OCR_VER:
                d[r["frame_id"]] = r
    return d


def read_frame(path):
    sys.path.insert(0, QS)
    import vision_ocr_screen as vs
    from PIL import Image
    im = Image.open(path).convert("RGB")
    W, H = im.size
    s = W / 1920
    px = im.load()
    rec = dict(frame_id=os.path.basename(path)[:-4], ver=OCR_VER, size=[W, H])
    try:
        rec["scr"] = vs.screen(path)
    except Exception as e:
        rec["scr"] = dict(screen_date="", err=repr(e)[:80])
    # the Windows taskbar clock ('17:12' over '2020-06-12'; his Swedish Windows, local time) for the session of the % Change cells
    rec["clock"] = [[t[0], t[3]] for t in ocr_box(im, (int(1700 * s), int(1036 * s), W, H), 4 if W >= 1500 else 6, True)]
    a_scale = 2 if W >= 1500 else 3
    toks = ocr_box(im, (int(0.5 * W), 0, W, H), a_scale, True)
    rec["passA"] = toks
    cands = header_candidates(im, toks, W, H)
    loc = locate(toks, W, H, cands)
    rec["candidates"] = [dict(text=d["tok"][0], x0=d["tok"][2], y0=d["tok"][3], src=d["src"], reread=d.get("reread", []), n_ok=d.get("n_ok"))
                         for d in cands]
    if loc is None:
        rec["found"] = False
        return rec
    h, foot, col = loc["header"], loc["footer"], loc["colhdr"]
    rec.update(found=True, header=h, header_src=loc["header_src"], header_reread=loc["header_reread"], header_line=loc["header_line"],
               footer=foot, colhdr=col, list=loc.get("list", "A"))
    # footer: second read of its line, enlarged (the 1280x720 footers are ~5 px tall)
    if foot is not None:
        fb = (int(max(0, h[2] - 4 * s)), int(max(0, foot[3] - 3 * s)), int(min(W, h[2] + 175 * s)), int(min(H, foot[5] + 3 * s)))
        fvars = [(4, 1), (3, 0)] if W >= 1500 else [(3, 0), (4, 0), (5, 1), (5, 0), (6, 1), (6, 0)]
        rec["footer2"] = {f"{sc}{'i' if inv else 'n'}": ocr_box(im, fb, sc, bool(inv)) for sc, inv in fvars}
    body_top = int(col[5] + 1) if col is not None else int(h[5] + 20 * s)
    body_bot = int(foot[3] - 1) if foot is not None else int(min(H - 42 * s, body_top + 360 * s))
    rec["body"] = [body_top, body_bot]
    # Sym column from the vertical grid lines, measured over the rows only (an empty area under a short list has no lines):
    # provisional rows from the fixed-offset column first
    fx0, fx1 = int(h[2] + 19 * s), int(h[2] + 50 * s)
    prov = ink_bands(px, fx0, fx1, body_top + 1, body_bot, s)
    gy0, gy1 = (prov[0][0] - 2, prov[-1][1] + 2) if prov else (body_top + 2, body_bot - 1)
    vx0, vx1 = int(max(0, h[2] - 12 * s)), int(min(W, h[2] + 170 * s))
    dy0 = int(col[3]) if col is not None else max(body_top, gy0)        # the column lines run through the column header too
    divs = vertical_dividers(px, vx0, vx1, dy0, max(gy0 + 3, min(body_bot, gy1)), s)
    divs = [d for d in divs if d[1] - d[0] <= max(3, 4 * s)]
    rec["dividers"] = divs
    sx = sym_x_est(col)
    cells = [(divs[i][1] + 1, divs[i + 1][0]) for i in range(len(divs) - 1)]
    sym_cell = None
    if sx is not None:
        sym_cell = next((c for c in cells if c[0] - 2 <= sx <= c[1] + 2 and 18 * s <= c[1] - c[0] <= 75 * s), None)
    if sym_cell is None:
        ok = [c for c in cells if 18 * s <= c[1] - c[0] <= 75 * s and c[0] > h[2] + 8 * s]
        sym_cell = ok[0] if ok else None
    rec["sym_col_src"] = "grid" if sym_cell else "fixed"
    if sym_cell is None:
        sym_cell = (int(h[2] + 17 * s), int(h[2] + 52 * s))
    cx0, cx1 = int(sym_cell[0]), int(sym_cell[1])
    rec["sym_col"] = [cx0, cx1]
    bands = ink_bands(px, cx0 + 1, cx1 - 1, body_top + 1, body_bot, s)
    rec["bands"] = bands
    if not bands:
        rec["passB"] = {}
        return rec
    by0, by1 = int(max(0, bands[0][0] - 4 * s)), int(min(H, bands[-1][1] + 4 * s))
    box = (cx0, by0, cx1, by1)
    variants = [(4, 1), (3, 0)] if W >= 1500 else [(4, 1), (4, 0), (6, 1), (6, 0), (8, 1), (8, 0), (3, 1), (3, 0)]
    rec["passB"] = {f"{sc}{'i' if inv else 'n'}": ocr_box(im, box, sc, bool(inv)) for sc, inv in variants}
    # the '% Change' cell next to the Sym column (kept for a later check of each read against that day's bar: not used yet)
    nxt = next((d for d in divs if d[0] > cx1 + 2 * s), None)
    px1 = int(min(W, nxt[0] if nxt and nxt[0] - cx1 <= 80 * s else cx1 + 46 * s))
    pbox = (cx1 + 1, by0, px1, by1)
    pvars = [(4, 1), (3, 0)] if W >= 1500 else [(4, 1), (4, 0), (6, 1), (6, 0)]
    rec["pct_col"] = [cx1 + 1, px1]
    rec["passPct"] = {f"{sc}{'i' if inv else 'n'}": ocr_box(im, pbox, sc, bool(inv)) for sc, inv in pvars}
    # the % text colour per row (green = up, red = down): the sign when Vision drops the '+' / '-'
    pc = []
    for b in bands:
        g = r_ = 0
        for y in range(int(b[0]), int(b[1]) + 1):
            for x in range(cx1 + 1, px1):
                R, G, B = px[x, y][:3]
                if G > 110 and G > R + 50 and G > B + 20:
                    g += 1
                elif R > 110 and R > G + 50 and R > B + 20:
                    r_ += 1
        pc.append([g, r_])
    rec["pct_color"] = pc
    # rows nobody read: one more look, row by row, larger
    assigned = assign(rec["passB"], bands, s)
    retry = {}
    for k, b in enumerate(bands):
        if not any(clean(r[0]) for r in assigned[k]):
            rb = (cx0, int(max(0, b[0] - 4 * s)), cx1, int(min(H, b[1] + 4 * s)))
            got = []
            for sc, inv in ((8 if W >= 1500 else 10, 1), (8 if W >= 1500 else 10, 0), (5 if W >= 1500 else 7, 1)):
                got += [g + [f"r{sc}{'i' if inv else 'n'}"] for g in ocr_box(im, rb, sc, bool(inv))]
            wb = (cx0, rb[1], int(min(W, cx1 + 48 * s)), rb[3])          # wider: the row's % value gives Vision a line to read
            for sc, inv in ((4 if W >= 1500 else 6, 1), (4 if W >= 1500 else 6, 0)):
                got += [g + [f"w{sc}{'i' if inv else 'n'}"] for g in ocr_box(im, wb, sc, bool(inv)) if g[2] < cx1 - 2 * s]
            retry[str(k)] = got
    rec["retry"] = retry
    return rec


def ocr_stage(frames_dir, out, shard, nshards, only=None):
    pat, _ = cache_files(out)
    done = set(load_cache(out))
    files = frame_files(frames_dir)
    fo = open(pat.format(shard), "a", encoding="utf-8")
    n = 0
    for i, p in enumerate(files):
        fid = os.path.basename(p)[:-4]
        if only and fid not in only:
            continue
        if i % nshards != shard or (fid in done and not only):
            continue
        if time.time() - os.path.getmtime(p) < 20:           # a frame still being written
            continue
        try:
            rec = read_frame(p)
        except Exception as e:                                # not cached: retried next run
            print("skip", fid, repr(e)[:100], flush=True)
            continue
        fo.write(json.dumps(rec) + "\n")
        fo.flush()
        n += 1
        if n % 50 == 0:
            print(f"shard {shard}: {n} frames", flush=True)
    print(f"shard {shard}: done, {n} new", flush=True)

# ---------------------------------------------------------------------------------------------------------- vote + lexicon (pure)
def clean(t):
    """an OCR token -> a ticker candidate or ''."""
    t = t.translate(CYR).strip()
    t = re.sub(r"^[^A-Za-z0-9]+", "", t)
    m = re.match(r"[^\s+\-%,*•]+", t)                         # the leading word ('X +6,07%' -> 'X')
    t = m.group(0) if m else ""
    t = re.sub(r"[^A-Za-z0-9]+$", "", t)
    if re.search(r"[^A-Za-z0-9.]", t):                           # a letter Vision could not place (e.g. Cyrillic): not a read
        return ""
    if not t or not re.search(r"[A-Z]", t) or re.search(r"[a-z]", t):
        return ""
    t = t.translate(DIG)
    t = t.strip(".")
    if t in STOP or not SYM_RX.match(t):
        return ""
    return t


def assign(passB, bands, s):
    """tokens of every variant -> the band their centre falls in (or the nearest band within half a row)."""
    out = [[] for _ in bands]
    if not bands:
        return out
    pitch = (sum(b[1] - b[0] for b in bands) / len(bands)) + 8 * s
    for var, toks in passB.items():
        for t in toks:
            c = yc(t)
            best = min(range(len(bands)), key=lambda k: abs(c - (bands[k][0] + bands[k][1]) / 2))
            b = bands[best]
            if b[0] - 4 * s <= c <= b[1] + 4 * s or abs(c - (b[0] + b[1]) / 2) <= pitch / 2:
                out[best].append(list(t[:6]) + [var])
    return out


CONF = [set("OQD0CU"), set("BEFP8R"), set("IL1TJ"), set("MN"), set("VYUW"), set("HKX"), set("S5"), set("GC6"), set("A4"), set("Z2")]


def sub_cost(a, b):
    if a == b:
        return 0.0
    return 0.5 if any(a in c and b in c for c in CONF) else 1.0


def wlev(a, b):
    """edit distance where look-alike swaps cost 0.5 and a dropped/added thin letter (I, L, 1, J) costs 0.75."""
    prev = [0.0]
    for ch in b:
        prev.append(prev[-1] + (0.75 if ch in "IL1J" else 1.0))
    for ca in a:
        cur = [prev[0] + (0.75 if ca in "IL1J" else 1.0)]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + (0.75 if ca in "IL1J" else 1.0), cur[j - 1] + (0.75 if cb in "IL1J" else 1.0), prev[j - 1] + sub_cost(ca, cb)))
        prev = cur
    return prev[-1]


class Lexicon:
    """which symbols traded near a date, from our two bar files.  The 2016-22 file carries TODAY's names (FB is META there, SQ is
    XYZ) and lacks some delisted names (SI, RADA): a symbol the 2021-26 file carries from its first day but the 2016-22 file lacks
    entirely is taken as trading on any earlier date too ('b_only')."""
    def __init__(self):
        if not os.path.exists(LEXICON):
            build_lexicon()
        self.r = {}
        for ln in open(LEXICON):
            t, a0, a1, b0, b1 = ln.rstrip("\n").split("\t")
            self.r[t] = (a0, a1, b0, b1)
        self.b_start = min(v[2] for v in self.r.values() if v[2])
        self.b_only = {t for t, v in self.r.items() if not v[0] and v[2] == self.b_start}
        # the historical symbols the bar files renamed or folded into a kept twin (CHK -> EXE ...): with the bars' own symbols
        # within 2 years (is_known), a read of one of these is a real ticker and is never look-alike 'corrected'
        self.alias = set()
        for f, cols in ALIAS_FILES:
            if os.path.exists(f):
                for row in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
                    for c in cols:
                        if row.get(c):
                            self.alias.add(row[c].strip())
        self.by_len = collections.defaultdict(list)
        for t in self.r:
            self.by_len[len(t)].append(t)

    def span(self, t):
        v = self.r.get(t)
        if v is None:
            return None
        xs = [x for x in v if x]
        return min(xs), max(xs)

    def is_known(self, t, day):
        """a symbol of our bar files within 2 years of the day, or a historical symbol from the rename / dedupe maps."""
        if t in self.alias or t in self.b_only:
            return True
        r = self.span(t)
        return r is not None and (not day or shift(r[0], -730) <= day <= shift(r[1], 730))

    def ok(self, t, day):
        v = self.r.get(t)
        if v is None:
            return False
        if not day:
            return True
        if t in self.b_only and day < self.b_start:
            return True
        return any(v[k] and shift(v[k], -10) <= day <= shift(v[k + 1], 10) for k in (0, 2))

    def near(self, t, day, cap=1.0):
        best = []
        for L in (len(t) - 1, len(t), len(t) + 1):
            for c in self.by_len.get(L, []):
                if c == t or not self.ok(c, day) or (c in self.b_only and day and day < self.b_start):
                    continue                                   # a b_only symbol is accepted as read, never proposed as a fix
                d = wlev(t, c)
                if d <= cap:
                    best.append((d, c))
        best.sort()
        return best


def shift(day, n):
    import datetime as dt
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def build_lexicon():
    """ticker -> first / last date with a daily bar in each bar file (awk, one pass each)."""
    rng = collections.defaultdict(lambda: ["", "", "", ""])
    for k, f in enumerate(BARS):
        cmd = f"gzip -dc '{f}' | awk -F, '{{if(!($1 in a) || $2<a[$1]) a[$1]=$2; if(!($1 in b) || $2>b[$1]) b[$1]=$2}} END{{for(t in a) print t\"\\t\"a[t]\"\\t\"b[t]}}'"
        for ln in subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True).stdout.splitlines():
            t, a, b = ln.split("\t")
            rng[t][2 * k], rng[t][2 * k + 1] = a, b
    with open(LEXICON, "w") as fo:
        for t, v in sorted(rng.items()):
            fo.write("\t".join([t] + v) + "\n")


def decide(reads, day, lex, lowres):
    """reads = [(cand, conf, variant)] -> (symbol or None, how, detail)."""
    cnt = collections.Counter(c for c, _, _ in reads if c)
    if not cnt:
        return None, "unread", {}
    conf = collections.defaultdict(list)
    for c, cf, _ in reads:
        if c:
            conf[c].append(cf)
    order = sorted(cnt, key=lambda c: (-cnt[c], -int(lex.ok(c, day)), -sum(conf[c]) / len(conf[c])))
    m = order[0]
    det = dict(votes=dict(cnt.most_common(6)))
    if lex.ok(m, day):
        return m, ("unanimous" if len(cnt) == 1 else "majority"), det
    # candidates (scored together, lowest wins, a tie is left as read):
    #  - a minority read of the same pixels that IS a ticker that week (ENOP 5 / ENDP 3 -> ENDP): look-alike distance minus 0.25
    #    per supporting read (max 2)
    #  - a ticker one look-alike away (O/Q/D, B/E/F/P, I/L, M/N ...): only when the reads disagree or the frame is 1280x720, and never
    #    for a read that is itself a real symbol near that date (renamed: FB is META in the era file; delisted: CHK in 2019)
    known = lex.is_known(m, day)
    #  - a minority read of another LENGTH (RAD under RADA) is usually a clipped read: it must have at least the majority's votes
    pool = {c: wlev(m, c) - 0.25 * min(cnt[c], 2) for c in order[1:] if lex.ok(c, day) and wlev(m, c) <= 2.0
            and (len(c) == len(m) or cnt[c] >= cnt[m] or (abs(len(c) - len(m)) == 1 and wlev(m, c) <= 0.75))}   # MINK 6 / MNK 2 -> MNK
    nread = sum(cnt.values())
    weak = cnt[m] < 3 and cnt[m] < 0.4 * max(1, nread)            # a read Vision barely produced (KV 2 of 8): never look-alike fixed
    if weak:
        det["weak"] = True
    if not known and not weak and len(m) >= 3 and (len(cnt) > 1 or lowres):   # 2-letter reads have too many neighbours (KV -> KW)
        for d, c in lex.near(m, day, cap=1.0 if lowres else 0.5):   # at 1920x1080 only one look-alike swap (TQOQ -> TQQQ)
            pool.setdefault(c, d)
    sc = sorted((v, -cnt.get(c, 0), c) for c, v in pool.items() if v <= 1.0)     # a tie goes to the candidate the image itself read
    sc = [(v, c) for v, _, c in sc]
    tie_ok = len(sc) >= 2 and sc[0][0] == sc[1][0] and cnt.get(sc[0][1], 0) > cnt.get(sc[1][1], 0)
    if sc and (len(sc) == 1 or sc[0][0] < sc[1][0] or tie_ok):
        det.update(was=m, score=round(sc[0][0], 2))
        return sc[0][1], ("corrected_vote" if cnt.get(sc[0][1]) else "corrected_lookalike"), det
    if sc:
        det["ambiguous"] = [c for _, c in sc[:4]]
    return m, "not_in_bars", det


def parse_footer(rec):
    """(text, first number, of-number) voted over the enlarged footer reads + the pass-A footer token."""
    texts = []
    W = rec["size"][0]
    for var, f2 in sorted((rec.get("footer2") or {}).items()):
        f2 = sorted(f2, key=lambda t: t[2])
        if f2:
            texts.append(" ".join(t[0] for t in f2 if t[2] < f2[0][2] + 140 * W / 1920))
    if rec.get("footer"):
        texts.append(rec["footer"][0])
    votes, first = collections.Counter(), {}
    for raw in texts:
        t = raw
        # digits Vision turned into letters inside the count ('20 of 3t' = 20 of 31, '1O' = 10)
        t = re.sub(r"(?<=\d)[tlI|!]|[tlI|!+](?=\d)", "1", t[:14]) + t[14:]          # '12 of +7' = 12 of 17
        t = re.sub(r"(?<=\d)[oO]|[oO](?=\d)", "0", t[:14]) + t[14:]
        t = re.sub(r"^\W{0,2}([&SBIl|OZG])(?=\s+[A-Za-z])", lambda m_: {"&": "8", "S": "5", "B": "8", "I": "1", "l": "1", "|": "1", "O": "0",
                                                                         "Z": "2", "G": "6"}[m_.group(1)], t)   # '& isung in..' = 8 Items
        m = FOOT_NUM.match(t)
        if not m:
            continue
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else None
        if b is not None and b < a:                           # 'N of M' always has N <= M: a misread
            continue
        votes[(a, b)] += 1 + (0.5 if FOOT_RX.search(t) else 0)
        first.setdefault((a, b), raw)
    if not votes:
        return (texts[-1] if texts else ""), None, None, 0
    (a, b), v = max(votes.items(), key=lambda kv: (kv[1], kv[0][1] is not None))
    return first[(a, b)], a, b, round(v / max(1, sum(votes.values())), 2)


def analyse_one(rec, lex, ref_date=""):
    W, H = rec["size"]
    s = W / 1920
    raw = rec.get("scr", {}).get("screen_date", "") or ""
    # the taskbar read is trusted when it falls 0-30 days before the video's upload date (as in 03_frame_check); a 1280x720
    # taskbar can misread a digit ('2015-10-01' for 2019-10-01), and then the upload date stands in
    if raw and (not ref_date or shift(ref_date, -30) <= raw <= shift(ref_date, 1)):
        day, src = raw, "taskbar"
    elif ref_date:
        day, src = ref_date, "ref_date"
    else:
        day, src = raw, ("taskbar" if raw else "")
    out = dict(frame_id=rec["frame_id"], screen_date=day, date_src=src, taskbar_raw=raw, clock=parse_clock(rec) if src == "taskbar" else "",
               resolution=f"{W}x{H}", panel_found=bool(rec.get("found")), list=rec.get("list", "A") if rec.get("found") else None,
               header_text="", symbols=[], visible_n=0, footer_text="", footer_n=None, total_n=None, layout={}, ocr_confidence={})
    lday = day
    if not rec.get("found"):
        rej = [f"{c['text']!r} (re-read {c.get('reread')})" for c in rec.get("candidates", [])]
        out["ocr_confidence"] = dict(notes=["no confirmed 'A -' panel header in the right half"] + ([f"rejected A-like headers: {'; '.join(rej)}"] if rej else []))
        return out
    h = rec["header"]
    out["header_text"] = rec.get("header_line", h[0])
    out["header_src"] = rec.get("header_src", "passA")
    ft, fa, fb, fagree = parse_footer(rec)
    out["footer_text"] = ft
    out["footer_n"] = fa
    out["total_n"] = fb if fb is not None else fa
    bands = rec.get("bands", [])
    rows_reads = assign(rec.get("passB", {}), bands, s)
    rows_pct = assign(rec.get("passPct", {}), bands, s)            # the % Change cell of each row (v15: checked against the bars)
    pcol = rec.get("pct_color") or [[0, 0]] * len(bands)
    for k, got in rec.get("retry", {}).items():
        rows_reads[int(k)] += [g[:6] + [g[6]] for g in got]
    # a list's rows sit at one fixed pitch: rows after a gap of more than 2.6 rows belong to something else (the next panel when
    # the footer line was missed, a caption overlay) and are dropped
    cut_note = None
    if len(bands) >= 3:
        cen = [(b[0] + b[1]) / 2 for b in bands]
        dif = sorted(cen[i + 1] - cen[i] for i in range(len(cen) - 1))
        pitch = dif[len(dif) // 2]
        cut = next((i + 1 for i in range(len(cen) - 1) if cen[i + 1] - cen[i] > 2.6 * pitch), None)
        if cut is not None:
            cut_note = f"{len(bands) - cut} ink band(s) below a {round((cen[cut] - cen[cut - 1]) / pitch, 1)}-row gap dropped (another panel / an overlay)"
            bands, rows_reads, rows_pct, pcol = bands[:cut], rows_reads[:cut], rows_pct[:cut], pcol[:cut]
    rows, syms, notes = [], [], ([cut_note] if cut_note else [])
    body = rec.get("body") or [0, H]
    for k, b in enumerate(bands):
        reads = [(clean(r[0]), r[1], r[6]) for r in rows_reads[k]]
        sym, how, det = decide(reads, lday, lex, W < 1500)
        if sym is None and len(b) >= 5 and b[4] - b[3] + 1 <= max(2, 2.5 * s) and b[1] - b[0] + 1 >= 3 * s:
            sym, how = "I", "ink_shape_I"                       # a single bare stroke: the one-letter ticker I (Vision drops it)
        row = dict(y=[b[0], b[1]], sym=sym, how=how, **det)
        row.update(pct_vote(rows_pct[k], pcol[k] if k < len(pcol) else [0, 0], W < 1500))
        # a row clipped by the column header (list scrolled) or by the footer / screen edge: read if possible, flagged
        if b[0] - body[0] <= 1.5 * s or body[1] - b[1] <= 1.5 * s:
            row["partial"] = True
        rows.append(row)
        if sym:
            syms.append(sym)
    # a band at the very top that reads as nothing and sits on the column header line is the header's own ink, not a row
    out["symbols"] = syms
    out["visible_n"] = len(bands)
    out["rows"] = rows
    out["layout"] = dict(header=[round(v) for v in h[2:6]], footer=([round(v) for v in rec["footer"][2:6]] if rec.get("footer") else None),
                         colhdr=([round(v) for v in rec["colhdr"][2:6]] if rec.get("colhdr") else None), body=rec.get("body"),
                         sym_col=rec.get("sym_col"), sym_col_src=rec.get("sym_col_src"), panel_x0=round(h[2]),
                         panel_box=[round(h[2]), round(h[3]), W, round(rec["footer"][5]) if rec.get("footer") else (rec.get("body") or [0, 0])[1]])
    unread = [k for k, r in enumerate(rows) if r["sym"] is None]
    corr = [f"{r.get('was')}->{r['sym']}" for r in rows if r["how"].startswith("corrected")]
    nib = [r["sym"] for r in rows if r["how"] == "not_in_bars"]
    split = [r["sym"] for r in rows if r["how"] == "majority"]
    if rec.get("footer") is None:
        notes.append("footer not found: rows read down to the panel's last ink above the taskbar")
    if unread:
        notes.append(f"{len(unread)} row(s) with ink but no read: {unread}")
    part = [f"{k}:{r['sym']}" for k, r in enumerate(rows) if r.get("partial")]
    if part:
        notes.append("row(s) half hidden at the top / bottom edge of the list (scrolled or cut): " + ", ".join(part))
    if corr:
        notes.append("corrected against our bars: " + ", ".join(corr))
    if nib:
        notes.append("read, not in our bars that week: " + ", ".join(nib))
    if out["total_n"] is not None and len(bands) > out["total_n"]:
        notes.append(f"more rows ({len(bands)}) than the footer total ({out['total_n']}): an extra ink band (cursor / overlay) or a misread footer")
    if not POS_RX.search(out["header_text"]):
        notes.append("title 'Positions' not visible (hidden behind the symbol box or cut): identified by the 'A -' prefix")
    out["ocr_confidence"] = dict(rows_unanimous=sum(1 for r in rows if r["how"] == "unanimous"), rows_majority=len(split), rows_corrected=len(corr),
                                 rows_not_in_bars=len(nib), rows_unread=len(unread), footer_parsed=fa is not None, footer_vote_share=fagree, notes=notes)
    return out

# ---------------------------------------------------------------------------------------------------------- analyse + summary
def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def grade(got, exp):
    """exact / near (one symbol off: one wrong, missing or extra) / wrong, on the ordered lists."""
    d = lev(got, exp)
    return ("exact" if d == 0 else "near" if d == 1 else "wrong"), d


def manifest_dates():
    p = os.path.join(VIS, "grades_manifest.tsv")
    if not os.path.exists(p):
        return {}
    return {r["frame_id"]: r["ref_date"] for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t")}


def analyze(frames_dir, out):
    rec = load_cache(out)
    lex = Lexicon()
    refd = manifest_dates()
    files = {os.path.basename(p)[:-4] for p in frame_files(frames_dir)}
    lines = []

    def P(x=""):
        print(x, flush=True)
        lines.append(x)

    res = []
    for fid in sorted(rec):
        if fid not in files:
            continue
        res.append(analyse_one(rec[fid], lex, refd.get(fid, "")))
    with open(out, "w", encoding="utf-8") as fo:
        for r in res:
            fo.write(json.dumps(r) + "\n")
    R = {r["frame_id"]: r for r in res}
    P(f"#705 positions panel read ({time.strftime('%Y-%m-%d %H:%M')}) - frames dir {frames_dir}: {len(files)} frames, OCR'd {len(res)}")
    P(f"out: {out}")

    # ---- the reference frames + the hand-checked frames
    for name, ref in (("REFERENCE (checked by eye by the caller)", REFERENCE), ("HAND CHECK (by eye on the enlarged panel crop, this card)", HAND)):
        if not ref:
            continue
        P(f"\n## {name}")
        tally = collections.Counter()
        tallies = collections.Counter()
        for fid, e in ref.items():
            r = R.get(fid)
            if r is None:
                P(f"- {fid}: not OCR'd")
                continue
            exp = (e.get("screen") or e["exp"]).split()
            g, d = grade(r["symbols"], exp)
            tally[g] += 1
            if e.get("screen"):
                g0, d0 = grade(r["symbols"], e["exp"].split())
                e = dict(e, note=f"{e['note']} | against the caller's list as written: {g0} (edit distance {d0})")
            ft = None
            if e.get("foot"):
                et = e["foot"][1] if e["foot"][1] is not None else e["foot"][0]
                ft = ("total OK" if r["total_n"] == et else f"TOTAL MISMATCH (eye {et})") + \
                     ("" if e["foot"][1] is None or r["footer_n"] == e["foot"][0] else f", first number misread (eye {e['foot'][0]})")
                tallies["total_ok"] += int(r["total_n"] == et)
            diff = "" if g == "exact" else f" | got {' '.join(r['symbols'])} | expected {' '.join(exp)}"
            P(f"- {fid} {r['screen_date']} {r['resolution']}: {g} (edit distance {d}) | {len(r['symbols'])} symbols, {r['visible_n']} rows | footer '{r['footer_text'][:40]}' -> {r['footer_n']}/{r['total_n']}"
              f"{'' if ft is None else ' ' + ft}{diff}{(' | note: ' + e['note']) if e.get('note') else ''}")
            tallies["sym_ok"] += max(0, len(exp) - d)
            tallies["sym_n"] += len(exp)
        P(f"- tally: " + ", ".join(f"{k} {v}" for k, v in tally.most_common()) +
          f" | symbols right {tallies['sym_ok']}/{tallies['sym_n']} (list length minus edit distance) | footer total right {tallies['total_ok']}/{len(ref)}")

    # ---- the whole run
    P(f"\n## RUN over {len(res)} frames")
    by = collections.defaultdict(lambda: [0, 0])
    for r in res:
        y = (r["screen_date"] or refd.get(r["frame_id"], "") or "????")[:4]
        k = (y, r["resolution"])
        by[k][0] += 1
        by[k][1] += int(r["panel_found"])
    P("- panel found, by year (taskbar date, else the video's upload date) and resolution:")
    yy = collections.defaultdict(lambda: [0, 0])
    for (y, res_), (n, f) in sorted(by.items()):
        P(f"    {y} {res_}: {f}/{n} ({100 * f / n:.0f}%)")
        yy[y][0] += n
        yy[y][1] += f
    P("- by year: " + " | ".join(f"{y} {f}/{n} ({100 * f / n:.0f}%)" for y, (n, f) in sorted(yy.items())))
    fd = [r for r in res if r["panel_found"]]
    if fd:
        vn = sorted(r["visible_n"] for r in fd)
        P(f"- found {len(fd)}/{len(res)} ({100 * len(fd) / len(res):.1f}%); visible rows: median {vn[len(vn) // 2]}, min {vn[0]}, max {vn[-1]}")
        tot = [r for r in fd if r["total_n"] is not None]
        sc = [r for r in tot if r["visible_n"] < r["total_n"]]
        eq = [r for r in tot if r["visible_n"] == r["total_n"]]
        gt = [r for r in tot if r["visible_n"] > r["total_n"]]
        P(f"- footer total read on {len(tot)}/{len(fd)}; visible rows < footer total (list scrolled / cut) {len(sc)} ({100 * len(sc) / max(1, len(tot)):.0f}%) | "
          f"equal {len(eq)} ({100 * len(eq) / max(1, len(tot)):.0f}%) | more rows than the total {len(gt)} ({100 * len(gt) / max(1, len(tot)):.0f}%)")
        hw = collections.Counter(rr["how"] for r in fd for rr in r["rows"])
        P(f"- rows {sum(hw.values())}: " + ", ".join(f"{k} {v}" for k, v in hw.most_common()))
        P(f"- frames with every row read and none corrected / outside our bars: {sum(1 for r in fd if all(rr['how'] in ('unanimous', 'majority') for rr in r['rows']) and r['rows'])}/{len(fd)}")
        nf = sum(1 for r in fd if r["layout"]["footer"] is None)
        P(f"- footer line not found {nf}; Sym column from the grid lines {sum(1 for r in fd if r['layout']['sym_col_src'] == 'grid')}/{len(fd)}; 'Positions' visible in the header {sum(1 for r in fd if POS_RX.search(r['header_text']))}/{len(fd)}")
        nib = collections.Counter(rr["sym"] for r in fd for rr in r["rows"] if rr["how"] == "not_in_bars")
        P("- most frequent reads not in our bars: " + ", ".join(f"{k} {v}" for k, v in nib.most_common(20)))
        cc = collections.Counter(f"{rr.get('was')}->{rr['sym']}" for r in fd for rr in r["rows"] if rr["how"].startswith("corrected"))
        P("- most frequent corrections: " + ", ".join(f"{k} {v}" for k, v in cc.most_common(20)))
    bpos = collections.Counter((r["screen_date"] or "????")[:4] for r in res
                               if any(re.search(r"B\s*-\s*Posit", t[0]) and t[2] > 0.5 * rec[r["frame_id"]]["size"][0] for t in rec[r["frame_id"]]["passA"]))
    P("- frames showing a 'B - Positions' list (NOT read: A-only rule): " + (", ".join(f"{y} {n}" for y, n in sorted(bpos.items())) or "none"))
    nf_ = [r for r in res if not r["panel_found"]]
    other = collections.Counter(c["text"] for r in nf_ for c in rec[r["frame_id"]].get("candidates", []))
    P(f"- not found {len(nf_)}; A-like tokens seen there but rejected: " + ", ".join(f"{k!r} {v}" for k, v in other.most_common(10)))
    P("\n## KNOWN FAILURE MODES (from the reference + hand checks and the run)")
    for f in FAILURE_MODES:
        P("- " + f)
    open(os.path.join(HERE, "01_read_panel.txt"), "w").write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------------------------------------- v15: the % Change check
# Every row's '% Change' cell is compared with that symbol's move in our daily bars.  What the cell shows depends on WHEN the frame
# was taken (his taskbar clock is Swedish local time): before the open it is the prior session's close-to-close change (or, with
# TC2000's pre-market data on, the pre-market move); in the session it is the live price vs the prior close, so it can only be
# bounded by that day's low-high range; after the close it is that day's close-to-close.  The frame's context is voted by its own
# rows (an exact close-to-close session explains most rows, else a session's range does), the clock only breaks ties.  A row whose
# % fails its context is replaced by a close OCR alternative that passes (exactly one), both recorded; a symbol with no bars stays
# as the holding it is, flagged no_bars.
TZ_LOCAL = ZoneInfo("Europe/Stockholm")      # his Windows taskbar ('Skriv här för att söka'): 11:34 on 2017-10-05 = 05:34 ET
TZ_ET = ZoneInfo("America/New_York")
ERA_A_END, ERA_B_START = "2022-06-30", "2021-09-27"
TOL_X = 0.15        # percentage points around an exact close-to-close change (the panel prints 2 decimals)
TOL_R = 0.30        # percentage points outside a session's low-high range vs the prior close (a live in-session price)
TOL_FIX = 0.02      # percentage points: a REPLACEMENT must match an exact close-to-close session this closely (92% of right reads do)
MAX_CHANCE = 0.10   # a replacement is made only when (alternatives searched) x (chance a wrong symbol matches within TOL_FIX) <= this
NULL_SHIFT = 40     # sessions: the chance-match null re-runs every test and every correction on the bars 40 sessions earlier
SIG_DATES = ("2021-10-01", "2021-11-01", "2021-12-01")     # overlap sessions: a renamed symbol's era-A name (FB -> META) by its closes
CAL_CACHE = os.path.join(VIS, "positions_pct_calendar.pkl.gz")
BARS_CACHE = os.path.join(VIS, "positions_pct_bars.pkl.gz")
CLOCK_RX = re.compile(r"^\W{0,2}([01]?\d|2[0-3])\s?[:.]\s?([0-5]\d)\W{0,2}$")
PCT_RX = re.compile(r"([+\-]?)\s*(\d{1,4})\s*[,.]\s*(\d{2})\s*%?")
ALPH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def parse_clock(rec):
    """'HH:MM' of the taskbar clock (the line above the date), or ''."""
    for t, y in sorted(rec.get("clock") or [], key=lambda t: t[1]):
        m = CLOCK_RX.match(t.strip())
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def parse_pct(t):
    t = t.translate(CYR).replace("−", "-").replace("–", "-").replace("—", "-")
    m = PCT_RX.search(t)
    if not m:
        return None
    return float(m.group(2) + "." + m.group(3)), m.group(1)


def pct_vote(toks, color, lowres):
    """the % cell of one row over the OCR variants: the value most variants read (1280x720: at least two agreeing); the sign from
    the text colour (green / red), else from the '+' / '-' the variants read."""
    vals, signs = collections.Counter(), collections.Counter()
    for t in toks:
        p = parse_pct(t[0])
        if p is None:
            continue
        vals[p[0]] += 1
        if p[1]:
            signs[p[1]] += 1
    out = dict(pct=None, pct_reads={f"{k:.2f}": v for k, v in vals.most_common(4)})
    if not vals:
        out["pct_how"] = "pct_unread"
        return out
    top = vals.most_common(2)
    v, n = top[0]
    if (len(top) > 1 and top[1][1] == n) or (lowres and n < 2):
        out["pct_how"] = "pct_disagree"
        return out
    g, r = color
    col = "+" if g >= 3 and g > 2 * r else "-" if r >= 3 and r > 2 * g else ""
    st = signs.most_common(2)
    sg = st[0][0] if st and (len(st) == 1 or st[0][1] > st[1][1]) else ""
    sign = "+" if v == 0 else (col or sg)
    if not sign:
        out["pct_how"] = "pct_no_sign"
        return out
    out["pct"] = v if sign == "+" else -v
    out["pct_how"] = "pct_read"
    # strong enough to REPLACE a symbol on: every variant that read a value read this one (1280x720: at least two of them)
    out["pct_strong"] = len(top) == 1 and n >= (2 if lowres else 1)
    return out


def ball1(t):
    out = set()
    for i in range(len(t) + 1):
        for ch in ALPH:
            out.add(t[:i] + ch + t[i:])
    for i in range(len(t)):
        out.add(t[:i] + t[i + 1:])
        for ch in ALPH:
            out.add(t[:i] + ch + t[i + 1:])
    out.discard("")
    return out


_NB = {}


def neighbours(t, cap, lexset):
    """lexicon symbols within look-alike distance `cap` of t (two edits at most), nearest first."""
    key = (t, cap)
    if key not in _NB:
        c1 = ball1(t)
        cand = set(c1)
        for u in c1:
            cand |= ball1(u)
        got = []
        for c in cand:
            if c != t and c in lexset:
                d = wlev(t, c)
                if d <= cap:
                    got.append((d, c))
        _NB[key] = sorted(got)
    return _NB[key]


def _awk(path, keys_file, extra):
    """rows of one bar file whose 'SYM,DATE' is in keys_file, or that match the awk condition `extra`."""
    cmd = (f"gzip -dc '{path}' | awk -F, 'NR==FNR{{N[$0]=1; next}} (($1\",\"$2) in N) || {extra} {{print}}' '{keys_file}' -")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True).stdout.splitlines()


def _rows(lines):
    d = {}
    for ln in lines:
        p = ln.split(",")
        try:
            d[(p[0], p[1])] = (float(p[2]), float(p[3]), float(p[4]), float(p[5]))
        except (ValueError, IndexError):
            continue
    return d


class Bars:
    """daily bars for the (symbol, session) pairs the check needs: era A (2016-22, today's names) and era B (2021-26); one awk pass
    per file, cached next to the outputs."""
    def __init__(self, lex):
        self.lex = lex
        if os.path.exists(CAL_CACHE):
            cal, sig = pickle.load(gzip.open(CAL_CACHE))
        else:
            kf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
            kf.write("NONE,NONE\n")
            kf.close()
            cond = "$1==\"SPY\" || " + " || ".join(f"$2==\"{d}\"" for d in SIG_DATES)
            ra, rb = _rows(_awk(BARS[0], kf.name, cond)), _rows(_awk(BARS[1], kf.name, cond))
            os.remove(kf.name)
            cal = sorted({d for (t, d) in ra if t == "SPY"} | {d for (t, d) in rb if t == "SPY"})
            sig = ({k: v for k, v in ra.items() if k[1] in SIG_DATES}, {k: v for k, v in rb.items() if k[1] in SIG_DATES})
            pickle.dump((cal, sig), gzip.open(CAL_CACHE, "wb"))
        self.cal = cal
        self.ix = {d: i for i, d in enumerate(cal)}
        # era-B symbols with no era-A rows whose closes on the three overlap sessions equal exactly one era-A symbol's (FB = META)
        ia = collections.defaultdict(list)
        sa = collections.defaultdict(dict)
        for (t, d), v in sig[0].items():
            sa[t][d] = round(v[3], 2)
        for t, m in sa.items():
            if len(m) == len(SIG_DATES):
                ia[tuple(m[d] for d in SIG_DATES)].append(t)
        sb = collections.defaultdict(dict)
        for (t, d), v in sig[1].items():
            sb[t][d] = round(v[3], 2)
        self.alias = {}
        for t in lex.b_only:
            m = sb.get(t, {})
            if len(m) == len(SIG_DATES):
                hit = ia.get(tuple(m[d] for d in SIG_DATES), [])
                if len(hit) == 1 and hit[0] != t:
                    self.alias[t] = hit[0]
        self.A, self.B = {}, {}

    def session(self, day):
        """index of the last session on or before `day`."""
        return bisect.bisect_right(self.cal, day) - 1

    def load(self, pairs):
        keys = set()
        for t, d in pairs:
            keys.add((t, d))
            if t in self.alias and d <= ERA_A_END:
                keys.add((self.alias[t], d))
        if os.path.exists(BARS_CACHE):
            have, A, B = pickle.load(gzip.open(BARS_CACHE))
            if keys <= have:
                self.A, self.B = A, B
                return "cache"
        kf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        kf.write("NONE,NONE\n" + "".join(f"{t},{d}\n" for t, d in sorted(keys)))
        kf.close()
        self.A, self.B = _rows(_awk(BARS[0], kf.name, "0")), _rows(_awk(BARS[1], kf.name, "0"))
        os.remove(kf.name)
        pickle.dump((keys, self.A, self.B), gzip.open(BARS_CACHE, "wb"))
        return f"read {len(keys)} pairs"

    def pair(self, sym, d0, d1):
        """(prior bar, bar) of one symbol from ONE era (B first in the overlap: its names are the contemporary ones)."""
        if d0 >= ERA_B_START:
            a, b = self.B.get((sym, d0)), self.B.get((sym, d1))
            if a and b:
                return a, b
        if d1 <= ERA_A_END:
            for t in (sym, self.alias.get(sym)):
                if t:
                    a, b = self.A.get((t, d0)), self.A.get((t, d1))
                    if a and b:
                        return a, b
        return None

    def ref(self, sym, ctx):
        """the % the cell may show under ctx = ('X', j) the close-to-close of session j, or ('R', j) session j's low-high vs the
        prior close: (lo, hi) in percent, or None (no bars)."""
        kind, j = ctx
        if j < 1 or j >= len(self.cal):
            return None
        p = self.pair(sym, self.cal[j - 1], self.cal[j])
        if p is None or not p[0][3]:
            return None
        c0 = p[0][3]
        o, h, l, c = p[1]
        if kind == "X":
            v = 100 * (c / c0 - 1)
            return (round(v, 3), round(v, 3))
        return (round(100 * (l / c0 - 1), 3), round(100 * (h / c0 - 1), 3))


def passes(pct, ref, kind):
    tol = TOL_X if kind == "X" else TOL_R
    return ref[0] - tol <= pct <= ref[1] + tol


def frame_session(out, bars):
    """(index of the session the frame's date falls on / after, the clock's context, the ET datetime or '')."""
    day = out.get("screen_date") or ""
    if not day:
        return None, "", ""
    clk = out.get("clock") or ""
    if clk:
        loc = dt.datetime.fromisoformat(f"{day}T{clk}").replace(tzinfo=TZ_LOCAL)
        et = loc.astimezone(TZ_ET)
        de, hm = et.date().isoformat(), et.hour * 60 + et.minute
        k = bars.session(de)
        if k < 0:
            return None, "", et.isoformat()
        if bars.cal[k] != de:
            cc = "closed"
        else:
            cc = "pre" if hm < 9 * 60 + 30 else "in" if hm < 16 * 60 else "post"
        return k, cc, et.isoformat(timespec="minutes")
    k = bars.session(day)
    return (k if k >= 0 else None), ("closed" if k >= 0 and bars.cal[k] != day else ""), ""


def clock_fits(cc, ctx, k):
    kind, j = ctx
    return {"pre": (("X", k - 1), ("R", k)), "in": (("R", k),), "post": (("X", k), ("R", k)), "closed": (("X", k),)}.get(cc, ()).__contains__(ctx)


def choose_ctx(rows, bars, k, cc, shift_=0):
    """the frame's context, voted by its rows (sym as read): an exact close-to-close session that explains most rows, else a
    session's range that explains most; the clock breaks ties.  Returns (ctx or None, {ctx: matches}, n rows tested)."""
    cands = [("X", k - 1), ("X", k), ("R", k), ("R", k - 1)]
    m, n = collections.Counter(), 0
    for r in rows:
        if r.get("pct") is None or not r.get("sym"):
            continue
        refs = {c: bars.ref(r["sym"], (c[0], c[1] - shift_)) for c in cands}
        if refs[("R", k)] is None and refs[("X", k - 1)] is None:
            continue
        n += 1
        for c, ref in refs.items():
            if ref is not None and passes(r["pct"], ref, c[0]):
                m[c] += 1
    if not n:
        return None, m, n

    def key(c):
        return (m[c], clock_fits(cc, c, k), c[1])
    xs = [c for c in cands if c[0] == "X" and m[c] >= 0.5 * n and (m[c] >= 2 or (n <= 2 and m[c] == n and clock_fits(cc, c, k)))]
    if xs:
        return max(xs, key=key), m, n
    # a range context only where the clock allows one (a wide range explains much by chance: the prior day's range on a
    # pre-market frame is never taken); with no clock read, any
    rs = [c for c in cands if c[0] == "R" and m[c] >= max(1, 0.6 * n) and (not cc or clock_fits(cc, c, k))]
    if rs:
        return max(rs, key=key), m, n
    return None, m, n


def row_tiers(r, day, lex, lowres):
    """the close OCR alternatives of one row, in the order they are tried: 1 the other reads of the same pixels (and the read the
    lexicon step replaced), 2 look-alikes within the lexicon step's cap (1.0 at 1280x720, 0.5 at 1920x1080), 3 at 1280x720 only,
    look-alikes up to 1.75 (KV -> IGV) - tier 3 is used only against an exact close-to-close context."""
    S = r["sym"]
    votes = r.get("votes") or {}
    was = r.get("was")
    t1 = [c for c in list(votes) + ([was] if was else []) if c and c != S]
    t1 = [c for i, c in enumerate(t1) if c not in t1[:i] and lex.ok(c, day)]
    bases = [b for b in [S, was] + list(votes)[:1] if b]
    lexset = lex.r
    cap2 = 1.0 if lowres else 0.5
    t2, t3 = [], []
    for b in bases:
        for d, c in neighbours(b, 1.75 if lowres else cap2, lexset):
            if c == S or c in t1 or not lex.ok(c, day):
                continue
            if d <= cap2 and c not in t2:
                t2.append(c)
            elif lowres and c not in t2 and c not in t3:
                t3.append(c)
    return t1, t2, t3


def try_fix(r, ctx, tiers, bars, p_fix, shift_=0):
    """the close OCR alternative that explains the row's % cell.  Exact close-to-close context: tiers are searched in order
    (cumulatively); the first tier with any alternative within TOL_FIX of the session's change decides - exactly one, and the
    alternatives searched so far times the chance a wrong symbol matches that closely (p_fix, measured on the null) at most
    MAX_CHANCE -> (symbol, tier, ref, n searched); exactly one but too many searched -> ('weak', ...); several -> ('ambiguous', ...).
    In-session range context: tier 1 only, exactly one inside the range -> ('suggest', ...) - a range explains about half of all
    symbols by chance, so it never replaces."""
    kind, j = ctx
    n = 0
    for ti, tier in enumerate(tiers, 1):
        if kind != "X" and ti >= 2:
            break
        n += len(tier)
        ok = []
        for c in tier:
            ref = bars.ref(c, (kind, j - shift_))
            if ref is None:
                continue
            if (kind == "X" and abs(r["pct"] - ref[0]) <= TOL_FIX) or (kind == "R" and passes(r["pct"], ref, "R")):
                ok.append((c, ref))
        if len(ok) > 1:
            return "ambiguous", ti, [c for c, _ in ok[:4]], n
        if len(ok) == 1:
            if kind != "X":
                return "suggest", ti, ok[0], n
            # only an alternative the OCR itself read off these pixels (tier 1) replaces: on the 2026-10-24 run tier-2/3 look-alike
            # matches were as frequent on the null (bars 40 sessions earlier) as on the real date - a misread % digit (YINN +1.81%
            # read +1.61% = WING) finds a look-alike by chance; a 0.00% cell (no trade yet) matches anything unchanged
            if ti > 1 or r["pct"] == 0 or n * p_fix > MAX_CHANCE:
                return "weak", ti, ok[0], n
            return ok[0][0], ti, ok[0][1], n
    return None


def pct_check(res, recs, lex):
    """the % Change check over every found frame (mutates the rows and symbols of `res`); returns (bars, stats)."""
    bars = Bars(lex)
    work = []
    pairs = set()
    for out in res:
        if not out["panel_found"] or not out.get("rows"):
            continue
        k, cc, et = frame_session(out, bars)
        out["et_time"] = et
        out["clock_ctx"] = cc
        if k is None or k < 2 + NULL_SHIFT:
            continue
        lowres = out["resolution"] == "1280x720"
        day = out["screen_date"]
        for r in out["rows"]:
            if not r.get("sym"):
                continue
            r["_tiers"] = row_tiers(r, day, lex, lowres) if r.get("pct") is not None else ([], [], [])
            for c in [r["sym"]] + [c for t in r["_tiers"] for c in t]:
                for j in (k - 2, k - 1, k):
                    for sh in (0, NULL_SHIFT):
                        if j - sh >= 0:
                            pairs.add((c, bars.cal[j - sh]))
        work.append((out, k, cc, lowres))
    how = bars.load(pairs)
    st = collections.Counter()
    st["pairs"] = len(pairs)
    st["load"] = how
    ctxs = collections.Counter()
    calib = dict(X=[], R=[])
    null = collections.Counter()
    # pass 1: each frame's context, and the chance that a WRONG symbol matches an exact close-to-close within TOL_FIX (the null:
    # every read against its own symbol's change NULL_SHIFT sessions earlier) - the p_fix every replacement is priced with
    for out, k, cc, lowres in work:
        rows = out["rows"]
        ctx, m, n = choose_ctx(rows, bars, k, cc)
        out["_ctx"] = ctx
        out["pct_ctx"] = dict(ctx=(f"{ctx[0]}:{bars.cal[ctx[1]]}" if ctx else None), session=(bars.cal[ctx[1]] if ctx else None),
                              kind=({"X": "close_to_close", "R": "in_session_range"}[ctx[0]] if ctx else None), rows_tested=n,
                              votes={f"{c[0]}:{bars.cal[c[1]]}": v for c, v in m.items()}, clock_ctx=cc,
                              clock_agrees=(clock_fits(cc, ctx, k) if (ctx and cc) else None))
        ctxs[(ctx[0] + ("" if ctx[1] == k else "-1")) if ctx else "none"] += 1
        if ctx and cc:
            ctxs["clock_agrees" if clock_fits(cc, ctx, k) else "clock_disagrees"] += 1
        nctx, _, _ = choose_ctx(rows, bars, k, cc, NULL_SHIFT)
        null["frames_ctx"] += int(nctx is not None)
        null["frames"] += 1
        if ctx and ctx[0] == "X":
            for r in rows:
                if r.get("sym") and r.get("pct") is not None:
                    nref = bars.ref(r["sym"], ("X", ctx[1] - NULL_SHIFT))
                    if nref is not None:
                        null["tested_fix"] += 1
                        null["pass_fix"] += int(abs(r["pct"] - nref[0]) <= TOL_FIX)
    p_fix = max(1, null["pass_fix"]) / max(1, null["tested_fix"])
    st["p_fix"] = round(p_fix, 5)
    for out, k, cc, lowres in work:
        rows = out["rows"]
        ctx = out.pop("_ctx")
        for r in rows:
            tiers = r.pop("_tiers", ([], [], []))
            if not r.get("sym"):
                continue
            if r.get("pct") is None:
                r["pct_check"] = "no_pct"
                continue
            if ctx is None:
                r["pct_check"] = "no_context"
                continue
            kind = ctx[0]
            ref = bars.ref(r["sym"], ctx)
            unanimous = r["how"] in ("unanimous", "ink_shape_I")
            # replaceable: a % cell every variant read alike, and a symbol read that is open to doubt - 1280x720, or the reads
            # disagree (a 1920x1080 read all variants agree on is never replaced: GBTC / a SPAC outside our bars is a real holding)
            gate = bool(r.get("pct_strong")) and (lowres or len(r.get("votes") or {}) > 1)
            # null: the same row and the same rules on the bars NULL_SHIFT sessions earlier
            nref = bars.ref(r["sym"], (kind, ctx[1] - NULL_SHIFT))
            if nref is not None:
                null[f"tested_{kind}"] += 1
                null[f"pass_{kind}"] += int(passes(r["pct"], nref, kind))
            if gate and ((nref is None and ref is None) or (nref is not None and not passes(r["pct"], nref, kind))):
                nb = "nb_" if ref is None else ""
                null[f"attempt_{nb}{kind}"] += 1
                null[f"attempt_t1_{nb}{kind}"] += int(bool(tiers[0]))
                f = try_fix(r, ctx, tiers, bars, p_fix, NULL_SHIFT)
                if f:
                    null[f"{f[0] if f[0] in ('ambiguous', 'weak', 'suggest') else 'fix'}_{nb}{kind}"] += 1
                    if f[0] != "ambiguous":
                        null[f"match_{nb}{kind}_t{f[1]}"] += 1
                    if f[0] not in ("ambiguous", "weak", "suggest"):
                        null[f"fix_{kind}_t{f[1]}"] += 1
            if ref is None:
                r["no_bars"] = True
                r["pct_check"] = "no_bars"
                if gate and any(tiers):
                    st[f"attempt_nb_{kind}"] += 1
                    st[f"attempt_t1_nb_{kind}"] += int(bool(tiers[0]))
                    f = try_fix(r, ctx, tiers, bars, p_fix)
                    if f and f[0] != "ambiguous":
                        st[f"match_nb_{kind}_t{f[1]}"] += 1
                    if f and f[0] not in ("ambiguous", "weak", "suggest"):
                        r.update(pct_was=r["sym"], pct_ref_was=None, sym=f[0], pct_ref=list(f[2]), pct_tier=f[1], pct_searched=f[3],
                                 how="corrected_pct", pct_check="fixed_from_no_bars")
                        r.pop("no_bars", None)
                        st[f"fix_nb_{kind}"] += 1
                    elif f and f[0] in ("weak", "suggest"):
                        r.update(pct_suggest=f[2][0], pct_suggest_ref=list(f[2][1]), pct_suggest_why=f"{f[0]} (tier {f[1]}, {f[3]} searched)")
                        st[f"{f[0]}_nb_{kind}"] += 1
                continue
            r["pct_ref"] = list(ref)
            if passes(r["pct"], ref, kind):
                r["pct_check"] = "ok"
                if unanimous and not lowres:
                    calib[kind].append(r["pct"] - ref[0] if kind == "X" else
                                       (0.0 if ref[0] <= r["pct"] <= ref[1] else min(abs(r["pct"] - ref[0]), abs(r["pct"] - ref[1]))))
                continue
            if unanimous and not lowres:
                calib[kind].append(r["pct"] - ref[0] if kind == "X" else min(abs(r["pct"] - ref[0]), abs(r["pct"] - ref[1])))
            r["pct_check"] = "mismatch_kept"
            if not gate:
                continue
            st[f"attempt_{kind}"] += 1
            st[f"attempt_t1_{kind}"] += int(bool(tiers[0]))
            f = try_fix(r, ctx, tiers, bars, p_fix)
            if f is None:
                continue
            if f[0] != "ambiguous":
                st[f"match_{kind}_t{f[1]}"] += 1
            if f[0] == "ambiguous":
                r["pct_check"] = "mismatch_ambiguous"
                r["pct_ambiguous"] = f[2]
                st[f"ambiguous_{kind}"] += 1
            elif f[0] in ("weak", "suggest"):
                r.update(pct_suggest=f[2][0], pct_suggest_ref=list(f[2][1]), pct_suggest_why=f"{f[0]} (tier {f[1]}, {f[3]} searched)")
                st[f"{f[0]}_{kind}"] += 1
            else:
                r.update(pct_was=r["sym"], pct_ref_was=list(ref), sym=f[0], pct_ref=list(f[2]), pct_tier=f[1], pct_searched=f[3],
                         how="corrected_pct", pct_check="fixed")
                st[f"fix_{kind}"] += 1
                st[f"fix_{kind}_t{f[1]}"] += 1
        out["symbols_ocr"] = out["symbols"]
        out["symbols"] = [r["sym"] for r in rows if r.get("sym")]
        out["no_bars"] = [r["sym"] for r in rows if r.get("no_bars")]
    for out in res:                                            # frames with no work: drop the transient keys
        for r in out.get("rows", []):
            r.pop("_tiers", None)
    return bars, dict(stats=st, ctxs=ctxs, calib=calib, null=null)


def all_manifests():
    """frame_id -> folder, video id, stream time (the frame's offset into the video), upload date (positions frames), ref date."""
    m, up = {}, {}
    for f in sorted(glob.glob(os.path.join(VIS, "positions_manifest_s*.tsv"))):
        for r in csv.DictReader(open(f, encoding="utf-8", newline=""), delimiter="\t"):
            u = (r.get("upload_date") or "").strip()
            u = f"{u[:4]}-{u[4:6]}-{u[6:8]}" if len(u) == 8 and u.isdigit() else ""
            m[r["frame_id"].strip()] = dict(folder="positions", vid=r["vid"].strip(), stream_ts=r["ts"].strip(), upload_date=u, ref_date=u)
            if u:
                up[r["vid"].strip()] = u
    p = os.path.join(VIS, "grades_manifest.tsv")
    for r in csv.DictReader(open(p, encoding="utf-8", newline=""), delimiter="\t"):
        m[r["frame_id"]] = dict(folder="grades", vid=r["vid"], stream_ts=r["ts"], upload_date=up.get(r["vid"], ""), ref_date=r["ref_date"],
                                grade_ticker=r["ticker"], grade_kind=r["kind"])
    return m


# 10 frames_positions frames picked by a fixed rule (seed 705, one per video, stratified 2017 x2, 2019-720p x1, 2020 x3, 2021 x2,
# 2022-23 x2, video DIvPxYjxRlg excluded - seen while building) and written down from FIXED right-column crops (not the located
# panel) BEFORE any v15 output for them existed.  exp=None: no positions list on screen (the frame must read panel_found false).
HAND_POS = {
    "p_ixK4VHeFjDI_a": dict(exp=None, note="2017-02-11: the top-right list is '3 S' (PLX MDCO TSLA); no positions list on screen"),
    "p_NG3YO4WEAR0_z": dict(exp=None, note="2017-03-02: list '2' is the active tab (OSUR TDW ANET ...); 'B - P..' is an inactive tab"),
    "p_Wb_R-YqKoR0_z": dict(exp="ENDP MNK BRZU RLGY MU OLED TDOC TEVA PBR JD APPS YINN IPHI BABA XNET AGRX", foot=(16, None),
                            note="1280x720; % cells of the red rows unreadable by eye"),
    "p_Nb1NvTY5Ulk_a": dict(exp="PDD OKTA BILI ZS TSLA BYND SE NKLA SHOP DDOG LAKE OPES LVGO APT LABU NET FSLY NVAX IDEX WKHS", foot=(24, None),
                            note="scrolled: 20 of 24 visible; 09:22 ET pre-market"),
    "p_N9n9_WUB5V0_a": dict(exp="APVO ENPH FUTU SPWR TQQQ JD GBTC SQ SE JMIA", foot=(10, None), note="09:28 ET pre-market (vaccine day)"),
    "p_Na2y_RrKZZI_a": dict(exp="MARK LVGO EXEL VAPO FCEL TLRY NUGT ETSY SAVE COF GPOR UAL CCL RCL NCLH UAVS", foot=(16, None)),
    "p_siYpCaiuPKg_a": dict(exp="RIOT ETHE MARA MSTR GBTC PLTR XP DKNG SEDG BNTX BLNK LAC LAZR PLUG NIO TDOC TSLA BILI NXTD", foot=(19, None),
                            note="broadcast caption over the bottom of the screen"),
    "p_u3k9-2pjcvs_a": dict(exp="MQ XOP ENPH GBTC QS BE MARA MSTR LAC FAS COIN AMD SOXL DWAC TSLA URNM URA FNGU CCJ GME", foot=(2, 20)),
    "p_K4PzGs13b-4_a": dict(exp="WEAT GUSH UCO TSLA", foot=(4, None)),
    "p_HpTbfp7GE-o_z": dict(exp="MARA DWAC MOS KRBN HOOD XOP SNAP NRGU GUSH", foot=(9, None)),
}
# 2 more frames_positions frames that show a 'B - Positions' list (2017), picked after the OCR stage by a fixed rule among the
# frames whose OCR found a B header (seed 7052) and written down from the fixed top-right crop before the analysis ran
HAND_B = {
    "p_yU-cNgKw508_z": dict(exp="FGEN UCTT JNUG PIRS MYOK EXTR ESIO LL SHOP PI XXII CUTR CRMD HMNY ALQA", foot=(15, None), note="2017-08-30"),
    "p_dIbyUDoRx_s_z": dict(exp="CRMD DRYS ZGNX SRPT PIRS AGEN EIGR GTHX FCEL SGH CUTR HMNY OSTK EXTR PAM ESIO SINA SEDG LL SUPV FIT", foot=(1, 24),
                            note="2017-10-03; scrolled, the last row is half hidden (FIT by eye)"),
}
# the known 1280x720 misreads of the v14 hand check that the % check should fix (row index, wrong read, right symbol)
POSITIVE = [("g_1951", "LX", "LK"), ("g_1835", "KV", "IGV"), ("g_1998", "KV", "IGV")]


def hand_tally(R, ref, P, title):
    P(f"\n## {title}")
    tally, ts = collections.Counter(), collections.Counter()
    for fid, e in ref.items():
        r = R.get(fid)
        if r is None:
            P(f"- {fid}: not OCR'd")
            continue
        if e["exp"] is None:
            g = "exact" if not r["panel_found"] else "wrong"
            tally[g] += 1
            P(f"- {fid} {r['screen_date']} {r['resolution']}: {g} (no positions list on screen; panel_found {r['panel_found']}"
              f"{'' if not r['panel_found'] else ', read ' + ' '.join(r['symbols'])}) | note: {e.get('note', '')}")
            continue
        exp = e["exp"].split()
        g, d = grade(r["symbols"], exp)
        g0, d0 = grade(r.get("symbols_ocr", r["symbols"]), exp)
        tally[g] += 1
        et = e["foot"][1] if e["foot"][1] is not None else e["foot"][0]
        ft = "total OK" if r["total_n"] == et else f"TOTAL MISMATCH (eye {et})"
        ts["total_ok"] += int(r["total_n"] == et)
        ts["sym_ok"] += max(0, len(exp) - d)
        ts["sym_n"] += len(exp)
        fixes = [f"{x.get('pct_was')}->{x['sym']}" for x in r.get("rows", []) if x.get("how") == "corrected_pct"]
        chk = collections.Counter(x.get("pct_check") for x in r.get("rows", []))
        diff = "" if g == "exact" else f" | got {' '.join(r['symbols'])} | expected {' '.join(exp)}"
        P(f"- {fid} {r['screen_date']} {r['resolution']} list {r.get('list')}: {g} (edit distance {d}; before the % check {g0}, {d0}) | "
          f"{len(r['symbols'])} symbols, {r['visible_n']} rows | footer '{r['footer_text'][:40]}' -> {r['footer_n']}/{r['total_n']} {ft} | "
          f"% context {r.get('pct_ctx', {}).get('ctx')} (clock {r.get('clock') or '-'}, {r.get('clock_ctx') or '-'}) | % checks "
          f"{dict(chk)}{(' | % fixes ' + ', '.join(fixes)) if fixes else ''}{diff}{(' | note: ' + e['note']) if e.get('note') else ''}")
    P(f"- tally: " + ", ".join(f"{k} {v}" for k, v in tally.most_common()) +
      (f" | symbols right {ts['sym_ok']}/{ts['sym_n']} (list length minus edit distance) | footer total right {ts['total_ok']}/"
       f"{sum(1 for e in ref.values() if e['exp'] is not None)}" if ts["sym_n"] else ""))
    return tally, ts


def analyze_all(frames_dir, out, cache_out):
    rec = load_cache(cache_out)
    lex = Lexicon()
    man = all_manifests()
    files = {os.path.basename(p)[:-4] for p in frame_files(frames_dir)}
    lines = []

    def P(x=""):
        print(x, flush=True)
        lines.append(x)
    res = []
    for fid in sorted(rec):
        if fid not in files:
            continue
        mm = man.get(fid, {})
        o = analyse_one(rec[fid], lex, mm.get("ref_date", ""))
        res.append(o)
    bars, ck = pct_check(res, rec, lex)
    with open(out, "w", encoding="utf-8") as fo:
        for o in res:
            mm = man.get(o["frame_id"], {})
            row = dict(frame_id=o["frame_id"], folder=mm.get("folder", "grades" if o["frame_id"].startswith("g_") else "positions"),
                       vid=mm.get("vid", ""), stream_ts=mm.get("stream_ts", ""), upload_date=mm.get("upload_date", ""),
                       ref_date=mm.get("ref_date", ""), **{k: mm[k] for k in ("grade_ticker", "grade_kind") if k in mm})
            row.update(o)
            fo.write(json.dumps(row) + "\n")
    R = {o["frame_id"]: o for o in res}
    folder = {o["frame_id"]: man.get(o["frame_id"], {}).get("folder", "grades" if o["frame_id"].startswith("g_") else "positions") for o in res}
    P(f"#705 positions panel read, both folders ({time.strftime('%Y-%m-%d %H:%M')}) - {frames_dir}")
    P(f"frames {len(files)}, OCR'd {len(res)} (grades {sum(1 for f in folder.values() if f == 'grades')}, positions "
      f"{sum(1 for f in folder.values() if f == 'positions')}); out: {out}")

    # ---- frames by year
    P("\n## FRAMES READ, by year (taskbar date, else the upload / grade date) - panel found / frames, list A / B")
    by = collections.defaultdict(collections.Counter)
    for o in res:
        y = (o["screen_date"] or "????")[:4]
        for key in ((folder[o["frame_id"]], y), ("all", y)):
            by[key]["n"] += 1
            by[key]["found"] += int(o["panel_found"])
            by[key]["A"] += int(o.get("list") == "A")
            by[key]["B"] += int(o.get("list") == "B")
            by[key]["720"] += int(o["resolution"] == "1280x720")
    for fo_ in ("positions", "grades", "all"):
        ks = sorted(k for k in by if k[0] == fo_)
        tot = collections.Counter()
        for k in ks:
            tot.update(by[k])
        P(f"- {fo_}: found {tot['found']}/{tot['n']} ({100 * tot['found'] / max(1, tot['n']):.1f}%) | " +
          " | ".join(f"{k[1]} {by[k]['found']}/{by[k]['n']} ({100 * by[k]['found'] / by[k]['n']:.0f}%)"
                     f"{' B ' + str(by[k]['B']) if by[k]['B'] else ''}{' 720p ' + str(by[k]['720']) if by[k]['720'] else ''}" for k in ks))
    fd = [o for o in res if o["panel_found"]]
    vids = collections.defaultdict(list)
    for o in res:
        if folder[o["frame_id"]] == "positions":
            vids[man.get(o["frame_id"], {}).get("vid", "")].append(o["panel_found"])
    P(f"- positions videos {len(vids)}: panel on both frames {sum(1 for v in vids.values() if len(v) == 2 and all(v))}, on one "
      f"{sum(1 for v in vids.values() if sum(v) == 1)}, on neither {sum(1 for v in vids.values() if not any(v))}")
    P(f"- list B (2017 'B - Positions') frames: {sum(1 for o in fd if o.get('list') == 'B')} "
      f"(positions {sum(1 for o in fd if o.get('list') == 'B' and folder[o['frame_id']] == 'positions')})")

    # ---- the % check
    st, ctxs, calib, null = ck["stats"], ck["ctxs"], ck["calib"], ck["null"]
    rows = [r for o in fd for r in o.get("rows", []) if r.get("sym") or r.get("pct_was")]
    pc = collections.Counter(r.get("pct_check", "not_checked") for r in rows)
    ph = collections.Counter(r.get("pct_how") for r in rows)
    P("\n## % CHANGE CHECK (each row's % cell vs its symbol's move in our bars)")
    P(f"- rule: the frame's context is voted by its rows - an exact close-to-close session (cell within {TOL_X} pp) explaining >= half "
      f"the rows, else (where the clock allows) a session's low-high range vs the prior close (within {TOL_R} pp) explaining >= 60%")
    P(f"- replacement rule: only against an exact close-to-close session; the symbol read must be open to doubt (1280x720, or the reads "
      f"disagree) and every % variant must agree; the ONE alternative within {TOL_FIX} pp in the first tier with any (tier 1 other reads "
      f"of the same pixels, tier 2 look-alikes within the lexicon cap, tier 3 1280x720 look-alikes to 1.75); it REPLACES only from tier 1, "
      f"on a non-zero cell, and when (alternatives searched) x (chance a wrong symbol matches within {TOL_FIX} pp = {st['p_fix']}, from "
      f"the null) <= {MAX_CHANCE}; a lone tier-2/3 match is recorded as a suggestion (weak), not applied (on the null it was as common "
      f"as on the real date). In-session range frames: never replaced, a lone passing tier-1 read is a suggestion. "
      f"A symbol with no bars stays as read (no_bars), replaced only under the same rule.")
    P(f"- bars: {st['pairs']} (symbol, session) pairs ({st['load']}); renamed-symbol aliases found by matching closes {len(bars.alias)} "
      f"(e.g. {', '.join(f'{a}->{b}' for a, b in sorted(bars.alias.items()) if a in ('FB', 'SQ', 'TWTR', 'CCIV', 'SPCE', 'DWAC'))})")
    P(f"- rows {len(rows)}: % cell read {ph['pct_read']} | unread {ph['pct_unread']} | variants disagree {ph['pct_disagree']} | no sign {ph['pct_no_sign']}")
    P(f"- frames by context: " + ", ".join(f"{k} {v}" for k, v in ctxs.most_common()) +
      "  (X = close-to-close of the frame's session, X-1 = of the session before, R = in-session range, R-1 = range of the session before)")
    P(f"- row results: " + ", ".join(f"{k} {v}" for k, v in pc.most_common()))
    P(f"- replacement attempts and outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items()) if k.split('_')[0] in
                                                               ("attempt", "fix", "weak", "suggest", "ambiguous")))
    fx = collections.Counter(f"{r.get('pct_was')}->{r['sym']}" for r in rows if r.get("how") == "corrected_pct")
    P(f"- replacements made ({sum(fx.values())}): " + ", ".join(f"{k} {v}" for k, v in fx.most_common(30)))
    sg = collections.Counter(f"{r['sym']}->{r['pct_suggest']} ({r['pct_suggest_why'].split(' ')[0]})" for r in rows if r.get("pct_suggest"))
    P(f"- suggestions NOT applied ({sum(sg.values())}): " + ", ".join(f"{k} {v}" for k, v in sg.most_common(20)))
    nb = collections.Counter(r["sym"] for r in rows if r.get("no_bars"))
    P(f"- no_bars holdings kept {sum(nb.values())} rows: " + ", ".join(f"{k} {v}" for k, v in nb.most_common(20)))
    mk = collections.Counter(r["sym"] for r in rows if r.get("pct_check") == "mismatch_kept")
    P(f"- mismatch kept, most frequent: " + ", ".join(f"{k} {v}" for k, v in mk.most_common(15)))
    for kind in ("X", "R"):
        c = sorted(abs(x) for x in calib[kind])
        if c:
            P(f"- calibration {kind} (1920x1080 rows whose reads all agree, {len(c)}): |cell - bars| <= 0.02 pp {sum(1 for x in c if x <= 0.02)} "
              f"({100 * sum(1 for x in c if x <= 0.02) / len(c):.1f}%), <= {TOL_X if kind == 'X' else TOL_R} pp "
              f"{sum(1 for x in c if x <= (TOL_X if kind == 'X' else TOL_R))} "
              f"({100 * sum(1 for x in c if x <= (TOL_X if kind == 'X' else TOL_R)) / len(c):.1f}%), <= 1 pp {sum(1 for x in c if x <= 1)}, median {c[len(c) // 2]:.3f}")
    P(f"- null ({NULL_SHIFT} sessions earlier): a read matches its own symbol's change within {TOL_FIX} pp by chance "
      f"{null['pass_fix']}/{null['tested_fix']} (p_fix {st['p_fix']}); within {TOL_X} pp {null['pass_X']}/{null['tested_X']}; "
      f"inside a range {null['pass_R']}/{null['tested_R']}")
    for kind in ("X", "R"):
        for nb in ("", "nb_"):
            a_r, a_n = st[f"attempt_{nb}{kind}"], null[f"attempt_{nb}{kind}"]
            if a_r or a_n:
                f_r, f_n = st[f"fix_{nb}{kind}"], null[f"fix_{nb}{kind}"]
                P(f"- null vs real, {kind}{' no-bars reads' if nb else ''}: replacements per attempt null {f_n}/{a_n} "
                  f"({100 * f_n / max(1, a_n):.1f}%) vs real {f_r}/{a_r} ({100 * f_r / max(1, a_r):.1f}%) -> chance replacements expected "
                  f"among the real ones ~{f_n / max(1, a_n) * a_r:.1f} of {f_r}")
    P("- a lone matching alternative (applied or not) per attempt, by tier, null vs real: " + "; ".join(
        f"{k[6:]} null {null[k]}/{null['attempt_' + k[6:].rsplit('_t', 1)[0]]} real {st[k]}/{st['attempt_' + k[6:].rsplit('_t', 1)[0]]}"
        for k in sorted(set(x for x in list(null) + list(st) if x.startswith("match_")))))
    P("- attempts with a tier-1 alternative at all (other reads of the same pixels that are tickers trading that week): " + "; ".join(
        f"{k[11:]} null {null[k]} real {st[k]}" for k in sorted(set(x for x in list(null) + list(st) if x.startswith("attempt_t1_")))))
    P(f"- null replacements by tier: " + ", ".join(f"{k} {v}" for k, v in sorted(null.items()) if k.startswith("fix_") and "_t" in k) +
      " | real: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items()) if k.startswith("fix_") and "_t" in k))
    P(f"- null frames with a context at all: {null['frames_ctx']}/{null['frames']}")

    # ---- positive tests
    P("\n## POSITIVE TEST (the v14 hand-check misreads at 1280x720 the % check should fix)")
    for fid, bad, good in POSITIVE:
        r = R.get(fid)
        if r is None:
            P(f"- {fid}: not read")
            continue
        hit = [x for x in r.get("rows", []) if x.get("pct_was") == bad or x.get("sym") in (bad, good) or x.get("pct_suggest") == good]
        P(f"- {fid} {bad}->{good}: " + ("FIXED" if any(x.get("pct_was") == bad and x["sym"] == good for x in hit) else "NOT fixed") + " | " +
          "; ".join(f"sym {x.get('sym')} was {x.get('pct_was')} how {x.get('how')} pct {x.get('pct')} ({x.get('pct_how')}) check "
                    f"{x.get('pct_check')} ref {x.get('pct_ref')} amb {x.get('pct_ambiguous')} suggest {x.get('pct_suggest')} "
                    f"{x.get('pct_suggest_why') or ''}" for x in hit) +
          f" | ctx {r.get('pct_ctx', {}).get('ctx')} votes {r.get('pct_ctx', {}).get('votes')} clock {r.get('clock')} {r.get('clock_ctx')}")

    # ---- regression vs the v14 grades read
    P("\n## REGRESSION vs the v14 grades read (positions_panel_grades.jsonl)")
    old = {}
    pth = os.path.join(VIS, "positions_panel_grades.jsonl")
    if os.path.exists(pth):
        for ln in open(pth, encoding="utf-8"):
            x = json.loads(ln)
            old[x["frame_id"]] = x
    cls = collections.Counter()
    oth = []
    for fid, x in old.items():
        r = R.get(fid)
        if r is None:
            cls["not re-read"] += 1
            continue
        if x["panel_found"] != r["panel_found"]:
            cls["found changed (" + ("list B" if r.get("list") == "B" else "other") + ")"] += 1
            if r.get("list") != "B":
                oth.append(fid)
            continue
        if x["symbols"] == r["symbols"]:
            cls["same"] += 1
        elif x["symbols"] == r.get("symbols_ocr"):
            cls["changed by the % check only"] += 1
        else:
            cls["other"] += 1
            oth.append(fid)
    P("- " + ", ".join(f"{k} {v}" for k, v in cls.most_common()) + (f" | other: {', '.join(oth[:12])}" if oth else ""))

    # ---- reference + hand checks
    hand_tally(R, {k: dict(v, exp=(v.get("screen") or v["exp"])) for k, v in REFERENCE.items()}, P, "REFERENCE (grades, checked by eye by the caller)")
    hand_tally(R, {k: dict(v) for k, v in HAND.items()}, P, "HAND CHECK v14 (grades frames, re-graded on the v15 read)")
    if HAND_B:
        hand_tally(R, HAND_B, P, "B-LIST CHECK (frames_positions, 2017 'B - Positions', written down before the analysis)")
    hand_tally(R, HAND_POS, P, "BLIND HAND CHECK (frames_positions, 10 frames, written down from fixed crops before any v15 output)")

    P("\n## KNOWN FAILURE MODES")
    for f in FAILURE_MODES_V15:
        P("- " + f)
    open(os.path.join(HERE, "02_read_all.txt"), "w").write("\n".join(lines) + "\n")


FAILURE_MODES_V15 = [
    "in-session frames can only be bounded by the day's low-high range (our bars are daily): a misread whose look-alike moved inside "
    "a similar range is not caught, and a replacement there is weaker evidence than one against an exact close-to-close session",
    "pre-market frames with TC2000's pre-market data on show the pre-market move, which our bars do not carry: they read as the "
    "session's range (approximately right near the open) or as no context",
    "a symbol with no bars (GBTC / ETHE before 2024, SPACs, renamed / delisted names our files lack) cannot be checked: it stays as "
    "read, flagged no_bars",
    "1280x720 % cells misread digits (ACAD's -1.63% read -1.03%, which matched ACA within 0.15 pp): a replacement needs every % variant "
    "to agree AND a match within 0.02 pp AND a small enough search; a 1920x1080 read all variants agree on is never replaced - a "
    "mismatch there is kept (mismatch_kept: a misread % cell, or a name whose bars belong to another company under today's symbol)",
    "the frame's context is voted by its own rows: a frame with one or two readable rows, or a pre-market frame with the pre-market "
    "data on, may get no context (no_context: nothing checked)",
    "replacements are made only from tier 1 against an exact close-to-close session (on this run: 3/9 such attempts matched vs 1/33 on "
    "the null -> ~91% right); an in-session tier-1 match is only a suggestion (21/25 vs 15/47 on the null -> ~60% right) and a tier-2/3 "
    "look-alike match too (X tier 2: 23/163 vs 40/661) - suggestions carry pct_suggest / pct_suggest_why on the row",
    "1280x720 column header AND footer garbled beyond the regexes ('TegiSym', 'Pieg Sm' / 'Pessorul Wiihat'): panel not found - the "
    "blind-check miss p_Wb_R-YqKoR0_z (a 16-row list); 2017: a 'B - Positions' panel whose own header line Vision drops (only the tab "
    "label read) is not found (p_yU-cNgKw508_a)",
]


def crops(frames_dir, out, only, dest):
    from PIL import Image
    rec = load_cache(out)
    os.makedirs(dest, exist_ok=True)
    for fid in only:
        r = rec.get(fid)
        if not r or not r.get("found"):
            print(fid, "no panel")
            continue
        W, H = r["size"]
        s = W / 1920
        h = r["header"]
        bot = (r["footer"][5] if r.get("footer") else r["body"][1]) + 4 * s
        path = next(p for p in frame_files(frames_dir) if os.path.basename(p) == fid + ".png")
        im = Image.open(path).convert("RGB").crop((int(h[2] - 8 * s), int(h[3] - 4 * s), int(min(W, h[2] + 120 * s)), int(min(H, bot))))
        k = 4 if W >= 1500 else 6
        im.resize((im.width * k, im.height * k), Image.LANCZOS).save(os.path.join(dest, fid + "_panel.png"))
        print(fid, "->", os.path.join(dest, fid + "_panel.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", "ocr", "analyze", "crops", "run-all", "analyze-all"])
    ap.add_argument("--frames-dir", default=os.path.join(VIS, "frames_grades"))
    ap.add_argument("--out", default=os.path.join(VIS, "positions_panel_grades.jsonl"))
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--crops-dir", default=os.path.join(VIS, "positions_panel_crops"))
    a = ap.parse_args()
    only = set(x for x in a.only.split(",") if x) or None
    if a.stage == "ocr":
        i, n = [int(x) for x in a.shard.split("/")]
        return ocr_stage(a.frames_dir, a.out, i, n, only)
    if a.stage == "crops":
        return crops(a.frames_dir, a.out, sorted(only or []), a.crops_dir)
    if a.stage in ("all", "run-all"):
        ps = [subprocess.Popen([OCR_PY, os.path.abspath(__file__), "--stage", "ocr", "--shard", f"{i}/{a.workers}", "--frames-dir", a.frames_dir,
                                "--out", a.out] + (["--only", a.only] if a.only else [])) for i in range(a.workers)]
        for p in ps:
            p.wait()
    if a.stage in ("run-all", "analyze-all"):
        return analyze_all(a.frames_dir, a.out, a.out)
    analyze(a.frames_dir, a.out)


if __name__ == "__main__":
    sys.exit(main())
