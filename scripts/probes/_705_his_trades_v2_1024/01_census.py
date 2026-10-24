#!/usr/bin/env python3
"""#705 — HIS TRADE LIST v2, 01: census of Qullamaggie's "I bought / I'm long" stream mentions and the outcome-free v2 candidate list
(docs/analysis/cb_his_trade_list_v2_prereg_2026-10-24.md). OUTCOME-FREE: no return, R, stop, exit, fill or any bar AFTER an event day
E is read; an event's EXISTENCE on a day is the only price fact used (the candidate / EP tables are read with explicit `usecols`,
see EXCLUDED COLUMNS). No subagent, no DB, no network. Read-only on every input; writes only under OUT.

Why: his streams are the ONLY record of his trades (operator 2026-10-24). The replays so far used the 236 frame-confirmed
breakout calls of 2017-21 (caption = screen = our bars, said on or before our breakout day). That slice is thin outside 2020-21
and his bar — real alpha and strong market outperformance — is not met on it. The streams carry 2,871 "bought / long" phrase hits
in 447 videos; the frame check attributed 854 of 2,472 graded moments. This script COUNTS what a caption-only rule (no frame)
would add, builds the candidate list, and writes the hand-check sample. It decides nothing about outcomes.

EVERY CHOICE BELOW WAS FIXED BEFORE THE FIRST RUN (this header is the record; the doc repeats it verbatim):
  UNIT         a (video, caption ticker) PAIR with at least one ticker-matched moment whose +-30 s caption window carries a BOUGHT
               phrase (`vision/graded_moments.tsv`, grade contains `bought`; regex asserted equal to 02_graded_moments.py's literal).
               The stream session s0 = the last era session <= the video's UPLOAD date (the frame check: upload minus taskbar date is
               0 d on 96.2% of frames); the same rule for every pair, frame or not. A pair's year (census) = the upload year; a
               trade's year (v2 list) = the EVENT year.
  ARMS         STRICT (primary) = the bought phrase sits in the ticker's OWN caption line — `quote`, the words within [-9 s, +14 s]
               of the pair's first mention in that moment (extract_hits.py:264-268), cut at 220 chars; WIDE (beside) = the phrase
               anywhere in the +-30 s window (= the grade itself). One output, one flag column (`own_line`); no second run.
  ERA          upload date <= 2022-01-03 -> era A (cb702_pre_v2: the rebuilt 2017-21 file), else era B (cb702, every row dated after
               2024-12-31 dropped AT READ and asserted; the videos end 2023-12 so the cut costs nothing — standing rule).
  SYMBOL       era A: the caption ticker itself if the v2 export has it, else dedupe_applied.tsv -> refetch_dropped.tsv -> rename_map.tsv
               (Track A's order, 01_join_labels.py); era B: as read (Polygon-keyed). "RESOLVES TO OUR BARS" = the resolved symbol has
               >= 1 daily bar inside the window [s0-10, s0+2] in the era's daily file (not the extractor's +-60-day validation).
  EVENTS       BREAKOUT = a `tl` candidate row (the registered level), first breaks AND retriggers (every day the high cleared the
               line is a day he could have bought); era A `out/candidates_tl_com.tsv` K=tl (split `pre` asserted), era B
               `out/candidates.tsv` K=tl, split `discovery` (D <= 2024-12-31; later rows are the sealed holdout), E <= cut.
               EP = `ep_join_1023/ep_events_{A,B}.tsv.gz` rows with `primary` True (gap >= 9% on >= 3x the 20-day mean volume, $5
               raw, $10M median liquidity; 01_ep_join.py's registered event, REUSED not recomputed).
  WINDOW       E in [s0 - 10, s0 + 2] sessions, BOTH setups. Why: "I bought" / "I'm long" is said about a buy ALREADY MADE (his
               correction 2026-10-23: a label dates the talk, not the buy), so the event sits at or before the talk; +2 covers a
               stream recorded before the open ("buying it tomorrow") and the upload-date slop; -10 covers "I bought it two weeks
               ago" (the month / year-word rule of the extractor already drops older recollections). The EVENT's day is the trade
               day; the stream date only marks WHICH event. BESIDE (counts only, never deciding): [-20, +2] and [-10, +5] (the EP
               join's window), and the nearest-event histogram over [-60, +60].
  MATCH        nearest event by |delta| (delta = idx(E) - idx(s0)); a TIE (one before, one after at the same distance) goes to the
               EARLIER E — the talk is about a buy already made (the EP join's rule; the OPPOSITE of Track A's, which read anticipation
               of a line break). A pair can support one breakout row and one EP row; its SETUP class = breakout / EP / both (both
               setups found, same day or not; `same_day` flagged) / neither. `neither` is split by coverage (the window outside the
               era's event range is a coverage fact, not a miss — 2022-01..03 has no breakout candidates in either era).
  DEDUPE       the v2 TRADE list is one row per (symbol, E, setup); mentions across moments and videos are COUNTED on the row.
  POSITIVE     the 854 frame-attributed labels (caption = screen = our bars): their bought pairs run through the SAME stages (phrase ->
  CONTROL      own line -> resolves -> event in window -> event agreement). REGISTERED BAR (the stage the RULE controls, not the
               window): among the 854's bought pairs where Track A's join placed a tl event with delta <= +2 (inside v2's window) AND
               v2 finds a tl event, >= 80% must land on the SAME E. The window-ceiling recall is a FACT stated in advance from Track A
               §3 (bought labels with delta <= +2: 261 of 624 = 42%; own line 350 of 669 = 52%): strict + [-10, +2] cannot "recover
               most" of the 854 by construction, and the 236's 127 strictly-before events are outside v2's reach by design. The 236
               set is RECOMPUTED here from labels_joined.tsv (era A, coverage != none, bought or best, E_tl set, delta >= 0 -> distinct
               (sym, E)) and asserted == 236 (era B 9); its recovery in the v2 list is printed split by the label's delta (<= 2 / >= 3).
  FRAME READS  the frame check's screen reads are a 2,000-moment precision check at $0: among bought moments whose on-screen ticker
  AS A CHECK   was CONFIRMED (status attributed or moved_unverified), P(caption == screen) by own-line vs window-only, and by
               event-in-window yes / no. caption != screen is an UPPER bound on the spoken ticker being wrong (7 of 20 moved quotes
               read by hand belonged to the spoken ticker — 03_frame_check.py).
  PLANTED      for every STRICT pair with a resolved symbol: N_CONTROL = 10 random WRONG tickers (seed 1024) from the era file with a
  CONTROL      bar on s0, close >= $5 and close x volume >= $10M on s0 (the frame check's control floors; era A on the split-adjusted
               file, era B as exported) -> the false-match rate of "an event of that ticker in the window" for tl all rows, tl first
               breaks, EP, and any. BESIDE: the same rate on the ticker-matched pairs that carry NO grade at all (what a merely
               MENTIONED stock reads — he talks about stocks that are moving).
  SAMPLE       30 STRICT pairs WITHOUT a frame-attributed label (not in the 854 — where the uncertainty is), stratified by upload year x
               setup in proportion (seed 1024, at least 1 per non-empty cell), with the YouTube link at the moment's second, the caption
               line, ticker, symbol, event day, setup, delta; `verdict` / `why` left blank for the reader.
  EXCLUDED     candidates: open_E high_E low_E close_E vol_E breakout_vol_x and every C*/first_* flag; labels_joined / matched_events:
  COLUMNS      r1_status r2 r1_off_from_E delta_r1 (forward by construction); ep_events: everything but ticker, E, primary, era.

OUTPUTS (/Users/alvinfung/apollo_data/cb702/qm_streams/his_trades_v2/): census.tsv (the per-year table), pairs_v2.tsv (one row per
  bought pair with every stage flag), trades_v2.tsv (one row per (symbol, E, setup), arms + mention counts), hand_check_30.tsv,
  _cache_*.pkl (the daily-file passes, so a re-run reads the cache: capture once, read many); the printout beside this script as
  01_census.txt. Pins (sha256) of every input and of this file are printed last.

Run:  python3 scripts/probes/_705_his_trades_v2_1024/01_census.py > scripts/probes/_705_his_trades_v2_1024/01_census.txt
"""
from __future__ import annotations

import bisect
import csv
import glob
import hashlib
import os
import pickle
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_qm_streams"))
import qmlib  # noqa: E402

DATA = "/Users/alvinfung/apollo_data"
A = f"{DATA}/cb702_pre_v2"
A_OLD = f"{DATA}/cb702_pre"
B = f"{DATA}/cb702"
QM = f"{B}/qm_streams"
VIS = f"{QM}/vision"
TA = f"{QM}/track_a_1023"
EPJ = f"{QM}/ep_join_1023"
OUT = f"{QM}/his_trades_v2"
SUBS = f"{QM}/subs"
FILES = {
    "video_status": f"{QM}/video_status.tsv",
    "moments": f"{VIS}/graded_moments.tsv",
    "labels": f"{VIS}/grades_labels.tsv",
    "labels_joined": f"{TA}/labels_joined.tsv",
    "stream_moments": f"{QM}/stream_moments.tsv",
    "stream_moments_ext": f"{QM}/ext_2016_2022/stream_moments_ext.tsv",
    "cal_A": f"{A}/sessions.txt",
    "cal_B": f"{TA}/spy_sessions_eraB_le_2024-12-31.txt",
    "cand_A": f"{A}/out/candidates_tl_com.tsv",
    "cand_B": f"{B}/out/candidates.tsv",
    "ep_A": f"{EPJ}/ep_events_A.tsv.gz",
    "ep_B": f"{EPJ}/ep_events_B.tsv.gz",
    "export_A": f"{A}/daily_closes_all.csv.gz",
    "export_B": f"{B}/daily_closes_all.csv.gz",
    "universe_B": f"{QM}/universe_dates.pkl",
    "alias_dedupe": f"{A}/dedupe_applied.tsv",
    "alias_refetch": f"{A_OLD}/survivorship_1023/merged_trial2/refetch_dropped.tsv",
    "alias_rename": f"{QM}/ext_2016_2022/rename_map.tsv",
    "done_A": f"{A}/minutes/_done.psv",
    "done_B": f"{B}/minutes/_done.psv",
    "done_ep": f"{B}/minutes_ep_1023/_done.psv",
    "grade_script": os.path.join(os.path.dirname(HERE), "_705_grades_1022", "02_graded_moments.py"),
    "phrase_script": os.path.join(os.path.dirname(HERE), "_705_grades_1022", "01_grade_phrases.py"),
}
BOUGHT_RX = r"\bi (bought|added|got in|took a (starter|position)|entered)\b|\bi'?m (long|in it)\b"
W_BACK, W_FWD = 10, 2
BESIDE_WINDOWS = ((20, 2), (10, 5))
WIDE_HIST = 60
ERA_A_LAST = "2022-01-03"
CUT_B = "2024-12-31"
SEED = 1024
N_CONTROL = 10
MIN_PX, MIN_DV = 5.0, 10_000_000.0
SAMPLE_N = 30
AGREEMENT_BAR = 0.80
YEARS = [str(y) for y in range(2016, 2024)]
CAND_COLS = ["ticker", "D", "E", "K", "retrigger", "split"]
EP_COLS = ["ticker", "E", "primary", "era"]
LJ_COLS = ["vid", "ts", "frame_id", "screen_ticker", "sym", "screen_date", "s0", "era", "coverage", "grade", "is_bought", "is_best",
           "delta_tl", "E_tl", "retrigger_tl"]
STR = str


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def P(*a):
    print(*a, flush=True)


def pct(n, d):
    return f"{n}/{d} ({100.0 * n / d:.1f}%)" if d else f"{n}/0"


def read_cal(path, cut=None):
    c = [ln.strip() for ln in open(path) if ln.strip()]
    if cut:
        c = [d for d in c if d <= cut]
    assert c == sorted(c)
    return c


def s_idx(cal, d):
    """index of the last session <= d (-1 if before the calendar)."""
    return bisect.bisect_right(cal, d) - 1


def read_tsv(path, usecols):
    return pd.read_csv(path, sep="\t", usecols=usecols, dtype=STR, keep_default_na=False)


# ═════════════════════════════════════════════════════════════════════════════════════════════ daily-file passes (cached)
EPOCH_ORD = date(1970, 1, 1).toordinal()
TICK_RX = re.compile(r"^[A-Z]{1,5}$")


def _pool_rows(ch, s0_dates):
    """the control pool rows of one chunk: (ticker, date) on a stream session with close >= MIN_PX and close x volume >= MIN_DV."""
    m = ch[ch.d.isin(s0_dates) & (ch.c >= MIN_PX) & (ch.c * ch.v >= MIN_DV)]
    return [(t, d) for t, d in zip(m.t, m.d) if TICK_RX.match(t)]


def era_a_pass(s0_dates: set) -> tuple[dict, dict]:
    """ONE pass over the era-A export (12M rows): symbol -> sorted date ordinals (every row), and the control POOL per stream session
    (tickers passing the floors on that s0). Nothing but ticker, date, close and volume is read; the close is the SAME day's. Cached."""
    cache = f"{OUT}/_cache_eraA.pkl"
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    code, tcodes, ords, pool = {}, [], [], defaultdict(set)
    for ch in pd.read_csv(FILES["export_A"], header=None, usecols=[0, 1, 5, 6], names=["t", "d", "c", "v"],
                          dtype={"t": str, "d": str, "c": float, "v": float}, chunksize=2_000_000):
        cat = pd.Categorical(ch.t)
        ids = np.array([code.setdefault(c, len(code)) for c in cat.categories], dtype=np.int32)
        tcodes.append(ids[cat.codes])
        ords.append((pd.to_datetime(ch.d, format="%Y-%m-%d").values.astype("datetime64[D]").astype(np.int64) + EPOCH_ORD).astype(np.int32))
        for t, d in _pool_rows(ch, s0_dates):
            pool[d].add(t)
    tc, oc = np.concatenate(tcodes), np.concatenate(ords)
    order = np.lexsort((oc, tc))
    tc, oc = tc[order], oc[order]
    names = {v: k for k, v in code.items()}
    bounds = np.flatnonzero(np.diff(tc)) + 1
    uni = {names[int(tc[s])]: oc[s:e] for s, e in zip(np.r_[0, bounds], np.r_[bounds, len(tc)])}
    pool = {d: sorted(v) for d, v in pool.items()}
    pickle.dump((uni, pool), open(cache, "wb"))
    return uni, pool


def era_b_pass(s0_dates: set) -> tuple[dict, int]:
    """the control POOL per era-B stream session from the cb702 export; every row dated after the cut dropped at read (asserted). Cached."""
    cache = f"{OUT}/_cache_eraB_pool.pkl"
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    pool, dropped = defaultdict(set), 0
    for ch in pd.read_csv(FILES["export_B"], header=None, usecols=[0, 1, 5, 6], names=["t", "d", "c", "v"],
                          dtype={"t": str, "d": str, "c": float, "v": float}, chunksize=2_000_000):
        n0 = len(ch)
        ch = ch[ch.d <= CUT_B]
        dropped += n0 - len(ch)
        for t, d in _pool_rows(ch, s0_dates):
            pool[d].add(t)
    assert all(d <= CUT_B for d in pool)
    out = ({d: sorted(v) for d, v in pool.items()}, dropped)
    pickle.dump(out, open(cache, "wb"))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    P("# #705 HIS TRADE LIST v2 — 01_census (outcome-free). Every choice fixed in the script header before the first run.")
    P(f"# unit = (video, caption ticker) pair with a bought-graded moment; s0 = last era session <= upload date; window E in [s0-{W_BACK}, s0+{W_FWD}];"
      f" delta = idx(E) - idx(s0) (<0 event BEFORE the talk); nearest |delta|, tie -> earlier E; STRICT = phrase in the ticker's own caption line")

    # ------------------------------------------------------------------ the regex, asserted against the two source scripts
    src2 = open(FILES["grade_script"], encoding="utf-8").read()
    lit2 = re.search(r'"bought":\s*r"((?:[^"\\]|\\.)*)"', src2).group(1)
    src1 = open(FILES["phrase_script"], encoding="utf-8").read()
    lit1 = re.search(r'"bought":\s*r"((?:[^"\\]|\\.)*)"', src1).group(1)
    assert lit2 == BOUGHT_RX and lit1 == BOUGHT_RX, (lit1, lit2)
    rx = re.compile(BOUGHT_RX)
    P(f"- bought regex asserted equal to 01_grade_phrases.py and 02_graded_moments.py: {BOUGHT_RX}")

    # ------------------------------------------------------------------ videos
    vs = read_tsv(FILES["video_status"], ["id", "seconds", "title", "status", "upload_date", "track", "words", "hits"])
    vinfo = {}
    for r in vs.itertuples(index=False):
        d = r.upload_date
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else ""
        vinfo[r.id] = dict(upload=iso, status=r.status, title=r.title, year=iso[:4] if iso else "")
    vids_by_year = defaultdict(Counter)
    for v, i in vinfo.items():
        vids_by_year[i["year"] or "none"][i["status"]] += 1
    P(f"\n## 0. Videos: {len(vinfo)} listed | status {dict(Counter(i['status'] for i in vinfo.values()))} | upload span "
      f"{min(i['upload'] for i in vinfo.values() if i['upload'])}..{max(i['upload'] for i in vinfo.values())}")

    # ------------------------------------------------------------------ phrase hits per video (full caption text)
    phrase_cache = f"{OUT}/_cache_phrase_hits.pkl"
    if os.path.exists(phrase_cache):
        phrase_hits = pickle.load(open(phrase_cache, "rb"))
    else:
        phrase_hits = {}
        for f in sorted(glob.glob(f"{SUBS}/*.vtt")):
            vid = os.path.basename(f).split(".")[0]
            text = " ".join(w for _, w in qmlib.parse_vtt(f)).lower()
            phrase_hits[vid] = len(rx.findall(text))
        pickle.dump(phrase_hits, open(phrase_cache, "wb"))
    P(f"- caption files {len(phrase_hits)} | bought-phrase hits {sum(phrase_hits.values())} in {sum(1 for v in phrase_hits.values() if v)} videos"
      f" (01_grade_phrases.py: 2871 in 447)")

    # ------------------------------------------------------------------ graded moments -> bought pairs
    mo = read_tsv(FILES["moments"], ["video", "upload_date", "t", "ts", "ticker", "tier", "via", "grades", "quote"])
    assert not mo.duplicated(["video", "ts", "ticker"]).any()
    qmap = {(v, t, c): q for v, t, c, q in zip(mo.video, mo.ts, mo.ticker, mo.quote)}
    bm = mo[mo.grades.str.contains("bought")].copy()
    bm["own_line"] = [int(rx.search(q.lower()) is not None) for q in bm.quote]
    bm["year"] = bm.upload_date.str[:4]
    P(f"- graded moments {len(mo)} | bought-graded {len(bm)} (by year {dict(Counter(bm.year))}) | own-line {int(bm.own_line.sum())}")
    pairs = {}
    bm["tf"] = bm.t.astype(float)
    for r in bm.sort_values(["video", "ticker", "tf"]).itertuples(index=False):
        k = (r.video, r.ticker)
        p = pairs.get(k)
        if p is None:
            pairs[k] = p = dict(video=r.video, ticker=r.ticker, upload=r.upload_date, year=r.upload_date[:4], title=vinfo.get(r.video, {}).get("title", ""),
                                n_moments=0, n_own=0, own_line=0, first_ts=r.ts, first_t=float(r.t), own_ts="", own_t=None, own_quote="", tier=r.tier, via=r.via, quote=r.quote)
        p["n_moments"] += 1
        if r.own_line:
            p["n_own"] += 1
            if not p["own_line"]:
                p["own_line"], p["own_ts"], p["own_t"], p["own_quote"] = 1, r.ts, float(r.t), r.quote
    P(f"- distinct bought (video, ticker) pairs {len(pairs)} | strict (own line) {sum(p['own_line'] for p in pairs.values())}")

    # ------------------------------------------------------------------ the 854 and the 236
    lab = read_tsv(FILES["labels"], ["vid", "ts", "screen_ticker", "screen_date", "grade", "caption_ticker", "status", "frame_id", "ocr_ticker", "triple_agree"])
    att = lab[lab.status == "attributed"]
    assert len(att) == 854 and (att.triple_agree == "1").all()
    att_pairs_any = set(zip(att.vid, att.caption_ticker))
    att_pairs_bought = set(zip(att.loc[att.grade.str.contains("bought"), "vid"], att.loc[att.grade.str.contains("bought"), "caption_ticker"]))
    frame_by_pair = {}
    for r in lab.itertuples(index=False):
        if r.frame_id and (r.vid, r.caption_ticker) not in frame_by_pair:
            frame_by_pair[(r.vid, r.caption_ticker)] = r.frame_id
    LJ = read_tsv(FILES["labels_joined"], LJ_COLS)
    pos = LJ[(LJ.coverage != "none") & (LJ.E_tl != "") & ((LJ.is_bought == "1") | (LJ.is_best == "1"))].copy()
    pos["d"] = pos.delta_tl.astype(int)
    ev236 = {e: set(zip(pos.loc[(pos.era == e) & (pos.d >= 0), "sym"], pos.loc[(pos.era == e) & (pos.d >= 0), "E_tl"])) for e in ("A", "B")}
    assert len(ev236["A"]) == 236 and len(ev236["B"]) == 9, (len(ev236["A"]), len(ev236["B"]))
    # the smallest non-negative label delta per 236 event (how far before E the earliest qualifying call was said)
    d236 = {}
    for r in pos[pos.d >= 0].itertuples(index=False):
        k = (r.era, r.sym, r.E_tl)
        d236[k] = min(d236.get(k, 10 ** 9), r.d)
    lj_pairs_236 = set()
    for r in pos[pos.d >= 0].itertuples(index=False):
        if (r.sym, r.E_tl) in ev236[r.era]:
            lj_pairs_236.add((r.vid, r.screen_ticker))
    # the join's tl event per attributed BOUGHT label row (for the agreement check)
    lj_bought = LJ[(LJ.is_bought == "1") & (LJ.coverage != "none")]
    join_ev = defaultdict(list)            # (vid, screen_ticker) -> [(delta, E_tl)]
    for r in lj_bought.itertuples(index=False):
        if r.E_tl:
            join_ev[(r.vid, r.screen_ticker)].append((int(r.delta_tl), r.E_tl))
    P(f"- 854 attributed labels: pairs any grade {len(att_pairs_any)} | bought pairs {len(att_pairs_bought)} | the 236 recomputed: era A {len(ev236['A'])}, era B {len(ev236['B'])}"
      f" | attributed pairs carrying a 236 event {len(lj_pairs_236)}")

    # ------------------------------------------------------------------ calendars, eras, s0
    cal = {"A": read_cal(FILES["cal_A"]), "B": read_cal(FILES["cal_B"], CUT_B)}
    assert cal["A"][-1] == "2022-06-30" and cal["B"][-1] <= CUT_B
    P(f"- calendars: A {len(cal['A'])} sessions {cal['A'][0]}..{cal['A'][-1]} | B {len(cal['B'])} sessions {cal['B'][0]}..{cal['B'][-1]}")
    for p in pairs.values():
        p["era"] = "A" if p["upload"] <= ERA_A_LAST else "B"
        c = cal[p["era"]]
        p["i0"] = s_idx(c, p["upload"])
        assert p["i0"] >= 0
        p["s0"] = c[p["i0"]]
    s0_dates = {"A": {p["s0"] for p in pairs.values() if p["era"] == "A"}, "B": {p["s0"] for p in pairs.values() if p["era"] == "B"}}
    # the no-grade mention pairs (beside): every ticker-matched pair without any graded moment
    graded_pairs = set(zip(mo.video, mo.ticker))
    ng = set()
    for f in (FILES["stream_moments"], FILES["stream_moments_ext"]):
        sm = read_tsv(f, ["video", "ticker", "upload_date"])
        for v, t, d in zip(sm.video, sm.ticker, sm.upload_date):
            if (v, t) not in graded_pairs:
                ng.add((v, t, d))
    ng_pairs = []
    for v, t, d in ng:
        e = "A" if d <= ERA_A_LAST else "B"
        i0 = s_idx(cal[e], d)
        if i0 >= 0:
            ng_pairs.append(dict(video=v, ticker=t, upload=d, era=e, i0=i0, s0=cal[e][i0]))
    for p in ng_pairs:
        s0_dates[p["era"]].add(p["s0"])
    P(f"- stream sessions s0: era A {len(s0_dates['A'])} dates, era B {len(s0_dates['B'])} | pairs by era {dict(Counter(p['era'] for p in pairs.values()))}"
      f" | no-grade mention pairs (beside) {len(ng_pairs)}")

    # ------------------------------------------------------------------ symbols: era A universe + aliases, era B universe
    uni_a, pool_a = era_a_pass(s0_dates["A"])
    pool_b, dropped_b = era_b_pass(s0_dates["B"])
    uni_b_full = pickle.load(open(FILES["universe_B"], "rb"))
    cut_o = date.fromisoformat(CUT_B).toordinal()
    uni_b = {t: a[a <= cut_o] for t, a in uni_b_full.items()}
    uni_b = {t: a for t, a in uni_b.items() if len(a)}
    P(f"- era A export symbols {len(uni_a)} (one pass, cached) | era B universe symbols with a bar <= {CUT_B}: {len(uni_b)} of {len(uni_b_full)}"
      f" | era B export rows dated after the cut dropped at the price pass: {dropped_b}")
    alias_maps = []
    for name in ("alias_dedupe", "alias_refetch", "alias_rename"):
        m = {}
        for r in csv.DictReader(open(FILES[name]), delimiter="\t"):
            drop = r.get("dropped_symbol") or r.get("symbol") or r.get("polygon_ticker")
            keep = r.get("kept_symbol") or r.get("alpaca_symbol") or (r.get("reason", "").split("_of_")[-1].split("(")[0] if "_of_" in r.get("reason", "") else "")
            if drop and keep:
                m[drop] = keep
        alias_maps.append((os.path.basename(FILES[name]), m))

    def resolve(t, era):
        if era == "B":
            return (t, "own") if t in uni_b else (t, "unresolved")
        if t in uni_a:
            return t, "own"
        for name, m in alias_maps:
            k = m.get(t)
            if k and k in uni_a:
                return k, name
        return t, "unresolved"

    def has_bar(sym, era, lo_i, hi_i):
        arr = (uni_a if era == "A" else uni_b).get(sym)
        if arr is None:
            return False
        c = cal[era]
        lo = date.fromisoformat(c[max(lo_i, 0)]).toordinal()
        hi = date.fromisoformat(c[min(hi_i, len(c) - 1)]).toordinal()
        i = int(arr.searchsorted(lo))
        return i < len(arr) and arr[i] <= hi

    # ------------------------------------------------------------------ events
    ca = read_tsv(FILES["cand_A"], CAND_COLS)
    ca = ca[ca.K == "tl"]
    assert (ca.split == "pre").all()
    cb_rows = []
    drop_b = Counter()
    for ch in pd.read_csv(FILES["cand_B"], sep="\t", usecols=CAND_COLS, dtype=STR, keep_default_na=False, chunksize=500_000):
        ch = ch[ch.K == "tl"]
        n0 = len(ch)
        ch = ch[ch.split == "discovery"]
        drop_b["not_discovery"] += n0 - len(ch)
        n1 = len(ch)
        ch = ch[(ch.E <= CUT_B) & (ch.D <= CUT_B)]
        drop_b["dated_after_cut"] += n1 - len(ch)
        cb_rows.append(ch)
    cb = pd.concat(cb_rows, ignore_index=True)
    assert cb.E.max() <= CUT_B
    ep = {}
    for e in ("A", "B"):
        t = pd.read_csv(FILES[f"ep_{e}"], sep="\t", usecols=EP_COLS, dtype=STR, keep_default_na=False)
        t = t[t.primary == "True"]
        assert (t.era == e).all()
        if e == "B":
            assert t.E.max() <= CUT_B
        ep[e] = t
    cand = {"A": ca, "B": cb}
    ev = {}                                  # (era, setup, ticker) -> (iE array, retrigger array)
    e_range = {}
    for e in ("A", "B"):
        c = cand[e]
        iE = np.array([s_idx(cal[e], x) for x in c.E])
        assert (np.array(cal[e])[iE] == c.E.to_numpy()).all(), f"era {e}: a tl E off the calendar"
        c = c.assign(iE=iE, rt=c.retrigger.astype(int))
        for t, g in c.groupby("ticker"):
            g = g.sort_values("iE")
            ev[(e, "tl", t)] = (g.iE.to_numpy(), g.rt.to_numpy())
        e_range[(e, "tl")] = (int(iE.min()), int(iE.max()))
        x = ep[e]
        iEp = np.array([s_idx(cal[e], d) for d in x.E])
        assert (np.array(cal[e])[iEp] == x.E.to_numpy()).all(), f"era {e}: an EP E off the calendar"
        x = x.assign(iE=iEp)
        for t, g in x.groupby("ticker"):
            g = g.sort_values("iE")
            ev[(e, "ep", t)] = (g.iE.to_numpy(), np.zeros(len(g), dtype=int))
        e_range[(e, "ep")] = (int(iEp.min()), int(iEp.max()))
        P(f"- era {e} events: tl rows {len(c)} (first breaks {int((c.rt == 0).sum())}; E {c.E.min()}..{c.E.max()})"
          + (f"; era B rows dropped at read {dict(drop_b)}" if e == "B" else "")
          + f" | EP primary {len(x)} (E {x.E.min()}..{x.E.max()})")

    def nearest(era, setup, sym, i0, back, fwd):
        """nearest event in [i0-back, i0+fwd]: (delta, iE, n_in_window, retrigger) or None. Tie -> the earlier E."""
        a = ev.get((era, setup, sym))
        if a is None:
            return None
        arr, rt = a
        lo, hi = int(arr.searchsorted(i0 - back)), int(arr.searchsorted(i0 + fwd, side="right"))
        if hi <= lo:
            return None
        w = arr[lo:hi]
        d = w - i0
        order = np.lexsort((d, np.abs(d)))      # |delta| first, then the smaller (earlier) delta
        j = order[0]
        return int(d[j]), int(w[j]), hi - lo, int(rt[lo + j])

    def coverage(era, setup, i0):
        lo, hi = i0 - W_BACK, i0 + W_FWD
        emin, emax = e_range[(era, setup)]
        if hi < emin or lo > emax:
            return "none"
        return "full" if lo >= emin and hi <= emax else "partial"

    # ------------------------------------------------------------------ the join, per pair
    rows = []
    for (v, t), p in pairs.items():
        e, i0 = p["era"], p["i0"]
        sym, via = resolve(t, e)
        rec = dict(video=v, ticker=t, sym=sym, resolved_via=via, era=e, upload=p["upload"], year=p["year"], s0=p["s0"], title=p["title"],
                   n_moments=p["n_moments"], n_own=p["n_own"], own_line=p["own_line"], first_ts=p["first_ts"], first_t=p["first_t"],
                   own_ts=p["own_ts"], own_t=p["own_t"], quote=(p["own_quote"] or p["quote"]), tier=p["tier"], via=p["via"],
                   in_854_any=int((v, t) in att_pairs_any), in_854_bought=int((v, t) in att_pairs_bought), in_236=int((v, t) in lj_pairs_236),
                   frame_id=frame_by_pair.get((v, t), ""), resolves=int(via != "unresolved" and has_bar(sym, e, i0 - W_BACK, i0 + W_FWD)))
        for setup in ("tl", "ep"):
            rec[f"cov_{setup}"] = coverage(e, setup, i0)
            m = nearest(e, setup, sym, i0, W_BACK, W_FWD) if rec["resolves"] else None
            rec[f"has_{setup}"] = int(m is not None)
            rec[f"delta_{setup}"] = m[0] if m else ""
            rec[f"E_{setup}"] = cal[e][m[1]] if m else ""
            rec[f"n_win_{setup}"] = m[2] if m else 0
            if setup == "tl":
                rec["retrigger_tl"] = m[3] if m else ""
            for bk, fw in BESIDE_WINDOWS:
                rec[f"has_{setup}_{bk}_{fw}"] = int(rec["resolves"] and nearest(e, setup, sym, i0, bk, fw) is not None)
            mw = nearest(e, setup, sym, i0, WIDE_HIST, WIDE_HIST) if rec["resolves"] else None
            rec[f"delta_wide_{setup}"] = mw[0] if mw else ""
        rec["same_day"] = int(bool(rec["E_tl"]) and rec["E_tl"] == rec["E_ep"])
        rec["setup"] = ("both" if rec["has_tl"] and rec["has_ep"] else "breakout" if rec["has_tl"] else "ep" if rec["has_ep"] else "neither")
        if rec["setup"] == "neither":
            rec["neither_why"] = ("unresolved" if via == "unresolved" else "no_bar_in_window" if not rec["resolves"]
                                  else "no_coverage" if rec["cov_tl"] == "none" and rec["cov_ep"] == "none" else "no_event")
        else:
            rec["neither_why"] = ""
        rec["in_236_v2"] = int(bool(rec["E_tl"]) and (sym, rec["E_tl"]) in ev236[e])
        rows.append(rec)
    PR = pd.DataFrame(rows)
    PR.to_csv(f"{OUT}/pairs_v2.tsv", sep="\t", index=False)

    # ------------------------------------------------------------------ 1. CENSUS per year
    P(f"\n## 1. CENSUS per upload year (counts only). 'event in window' = a tl breakout or primary EP event of the resolved ticker in [s0-{W_BACK}, s0+{W_FWD}]")
    hdr = ["year", "videos", "with_caps", "phrase_hits", "bought_moments", "pairs", "in_854_any", "in_854_bought", "in_236", "own_line", "resolve", "event_any",
           "event_tl", "event_ep", "strict_resolve", "strict_event_any", "strict_tl", "strict_ep", "strict_both_sameday", "strict_neither_nocov"]
    cen = []
    for y in YEARS + ["all"]:
        g = PR if y == "all" else PR[PR.year == y]
        vy = [v for v, i in vinfo.items() if (y == "all" or i["year"] == y)]
        st = g[g.own_line == 1]
        cen.append(dict(year=y, videos=len(vy), with_caps=sum(1 for v in vy if vinfo[v]["status"] == "ok"),
                        phrase_hits=sum(phrase_hits.get(v, 0) for v in vy), bought_moments=int(len(bm) if y == "all" else (bm.year == y).sum()),
                        pairs=len(g), in_854_any=int(g.in_854_any.sum()), in_854_bought=int(g.in_854_bought.sum()), in_236=int(g.in_236.sum()),
                        own_line=len(st), resolve=int(g.resolves.sum()), event_any=int((g.setup != "neither").sum()),
                        event_tl=int(g.has_tl.sum()), event_ep=int(g.has_ep.sum()),
                        strict_resolve=int(st.resolves.sum()), strict_event_any=int((st.setup != "neither").sum()), strict_tl=int(st.has_tl.sum()),
                        strict_ep=int(st.has_ep.sum()), strict_both_sameday=int(st.same_day.sum()),
                        strict_neither_nocov=int((st.neither_why == "no_coverage").sum())))
    CEN = pd.DataFrame(cen)[hdr]
    CEN.to_csv(f"{OUT}/census.tsv", sep="\t", index=False)
    pd.set_option("display.width", 300)
    P(CEN.to_string(index=False))
    P("- columns: videos = listed uploads that year; with_caps = an auto-caption track; phrase_hits = bought-phrase hits in the whole caption text; bought_moments ="
      " ticker-matched moments whose +-30 s window carries the phrase; pairs = distinct (video, ticker) of those; in_854_* = the pair has a frame-attributed label"
      " (any grade / bought); in_236 = the pair's attributed label sits on one of the 236 events; own_line = STRICT arm; resolve = the ticker has a bar in the window;"
      " event_* = nearest tl / EP event in the window exists; strict_* = the same on the STRICT pairs; strict_neither_nocov = strict pairs whose window lies outside both event ranges")
    P(f"- setup class, all pairs: {dict(Counter(PR.setup))} | strict: {dict(Counter(PR.loc[PR.own_line == 1, 'setup']))}")
    P(f"- 'neither' reasons, all pairs: {dict(Counter(PR.loc[PR.setup == 'neither', 'neither_why']))} | strict: {dict(Counter(PR.loc[(PR.setup == 'neither') & (PR.own_line == 1), 'neither_why']))}")
    P(f"- era A symbol resolution of the pairs: {dict(Counter(PR.loc[PR.era == 'A', 'resolved_via']))} | era B: {dict(Counter(PR.loc[PR.era == 'B', 'resolved_via']))}")
    P(f"- unresolved tickers (most frequent): {Counter(PR.loc[PR.resolved_via == 'unresolved', 'ticker']).most_common(25)}")
    st = PR[PR.own_line == 1]
    P(f"- STRICT pairs with a tl event: nearest is a retrigger {int((st.loc[st.has_tl == 1, 'retrigger_tl'].astype(int) == 1).sum())} of {int(st.has_tl.sum())};"
      f" > 1 tl event in the window {int((st.n_win_tl > 1).sum())}; > 1 EP event {int((st.n_win_ep > 1).sum())}")
    for setup in ("tl", "ep"):
        d = Counter(int(x) for x in st.loc[st[f"delta_{setup}"] != "", f"delta_{setup}"])
        P(f"- STRICT delta histogram, {setup} (delta: n; <0 = the event came BEFORE the talk): " + " ".join(f"{k:+d}:{d[k]}" for k in sorted(d)))
        dw = Counter(int(x) for x in st.loc[st[f"delta_wide_{setup}"] != "", f"delta_wide_{setup}"])
        inside = sum(v for k, v in dw.items() if -W_BACK <= k <= W_FWD)
        P(f"    nearest {setup} event within +-{WIDE_HIST} (beside): {sum(dw.values())} of {int(st.resolves.sum())} resolved strict pairs | inside the window {inside} |"
          f" 3..10 sessions AFTER the talk {sum(v for k, v in dw.items() if 3 <= k <= 10)} | 11..60 after {sum(v for k, v in dw.items() if 11 <= k <= 60)} |"
          f" 11..20 before {sum(v for k, v in dw.items() if -20 <= k <= -11)} | 21..60 before {sum(v for k, v in dw.items() if -60 <= k <= -21)}")
    P("- BESIDE windows (strict pairs with an event; counts only, never deciding): "
      + " | ".join(f"[-{bk}, +{fw}] tl {int(st[f'has_tl_{bk}_{fw}'].sum())}, ep {int(st[f'has_ep_{bk}_{fw}'].sum())}, any {int(((st[f'has_tl_{bk}_{fw}'] == 1) | (st[f'has_ep_{bk}_{fw}'] == 1)).sum())}"
                   for bk, fw in BESIDE_WINDOWS)
      + f" || primary [-{W_BACK}, +{W_FWD}] tl {int(st.has_tl.sum())}, ep {int(st.has_ep.sum())}, any {int((st.setup != 'neither').sum())}")

    # ------------------------------------------------------------------ 2. the v2 TRADE list (dedupe per symbol, E, setup)
    tr = {}
    for r in PR.itertuples(index=False):
        for setup in ("tl", "ep"):
            E = getattr(r, f"E_{setup}")
            if not E:
                continue
            k = (r.era, r.sym, E, "breakout" if setup == "tl" else "ep")
            x = tr.get(k)
            if x is None:
                tr[k] = x = dict(era=r.era, sym=k[1], E=E, setup=k[3], event_year=E[:4], strict=0, wide=0, n_mentions=0, n_videos=0, videos=set(), tickers=set(),
                                 in_236=int(k[3] == "breakout" and (r.sym, E) in ev236[r.era]), in_854_bought=0, retrigger=(r.retrigger_tl if setup == "tl" else ""),
                                 same_day_other_setup=int(r.same_day), min_abs_delta=abs(int(getattr(r, f"delta_{setup}"))))
            x["wide"] = 1
            x["strict"] = max(x["strict"], int(r.own_line))
            x["n_mentions"] += int(r.n_moments)
            x["videos"].add(r.video)
            x["tickers"].add(r.ticker)
            x["in_854_bought"] = max(x["in_854_bought"], int(r.in_854_bought))
            x["min_abs_delta"] = min(x["min_abs_delta"], abs(int(getattr(r, f"delta_{setup}"))))
    TR = pd.DataFrame([{**{k: v for k, v in x.items() if k not in ("videos", "tickers")}, "n_videos": len(x["videos"]),
                        "videos": ",".join(sorted(x["videos"])), "caption_tickers": ",".join(sorted(x["tickers"]))} for x in tr.values()])
    TR = TR.sort_values(["setup", "E", "sym"]).reset_index(drop=True)
    TR.to_csv(f"{OUT}/trades_v2.tsv", sep="\t", index=False)
    P(f"\n## 2. The v2 TRADE list: one row per (symbol, E, setup); STRICT = at least one mention with the phrase in the ticker's own caption line")
    for arm, mask in (("STRICT", TR.strict == 1), ("WIDE (beside)", TR.wide == 1)):
        g = TR[mask]
        tab = g.groupby(["event_year", "setup"]).size().unstack(fill_value=0)
        tab["total"] = tab.sum(axis=1)
        tab.loc["all"] = tab.sum()
        P(f"- {arm}: {len(g)} trades ({int((g.setup == 'breakout').sum())} breakout, {int((g.setup == 'ep').sum())} EP; same-day EP+breakout pairs {int(g.same_day_other_setup.sum())})"
          f" | already among the 236: {int(g.in_236.sum())} | carrying a frame-attributed bought label: {int(g.in_854_bought.sum())} | NEW vs the 236 (breakout rows not in it): "
          f"{int(((g.setup == 'breakout') & (g.in_236 == 0)).sum())} | NEW vs the 854 (no attributed label): {int((g.in_854_bought == 0).sum())}")
        P(tab.to_string())
    g = TR[(TR.strict == 1) & (TR.setup == "breakout")]
    P(f"- STRICT breakout rows by era: {dict(Counter(g.era))} | retrigger share {pct(int((g.retrigger.astype(str) == '1').sum()), len(g))} | by |delta| (0 / 1-2 / 3-5 / 6-10): "
      f"{int((g.min_abs_delta == 0).sum())} / {int(g.min_abs_delta.between(1, 2).sum())} / {int(g.min_abs_delta.between(3, 5).sum())} / {int(g.min_abs_delta.between(6, 10).sum())}")
    P(f"- STRICT trades per symbol: {len(g.sym.unique())} symbols; most frequent {Counter(g.sym).most_common(15)}")

    # ------------------------------------------------------------------ 3. POSITIVE CONTROL: the 854's bought pairs through the stages
    P(f"\n## 3. POSITIVE CONTROL — the 854's frame-attributed BOUGHT pairs ({len(att_pairs_bought)}) through the same stages")
    pc = PR[PR.in_854_bought == 1]
    assert len(pc) == len(att_pairs_bought)
    P(f"- stage: phrase in the window {len(pc)} (100%, by construction) -> own line {pct(int(pc.own_line.sum()), len(pc))} -> resolves {pct(int(pc.resolves.sum()), len(pc))}"
      f" -> event in window: tl {pct(int(pc.has_tl.sum()), len(pc))}, EP {pct(int(pc.has_ep.sum()), len(pc))}, any {pct(int((pc.setup != 'neither').sum()), len(pc))}")
    pcs = pc[pc.own_line == 1]
    P(f"- STRICT arm on the 854 bought pairs: own line {len(pcs)} -> event in window any {pct(int((pcs.setup != 'neither').sum()), len(pcs))} = {pct(int((pcs.setup != 'neither').sum()), len(pc))} of all 854 bought pairs"
      f" (the window ceiling stated in advance: Track A bought labels with delta <= +2 were 261/624 = 41.8%; own line 350/669 = 52.3%)")
    # agreement with Track A's join where its event is inside v2's window
    agree = dis = nov2 = 0
    for r in pc.itertuples(index=False):
        js = [E for d, E in join_ev.get((r.video, r.ticker), []) if d <= W_FWD]
        if not js:
            continue
        if not r.E_tl:
            nov2 += 1
            continue
        if r.E_tl in js:
            agree += 1
        else:
            dis += 1
    tot = agree + dis
    verdict = "PASS" if tot and agree / tot >= AGREEMENT_BAR else "FAIL"
    P(f"- REGISTERED BAR (event agreement): 854 bought pairs whose Track A join placed a tl event with delta <= +{W_FWD}: {tot + nov2}; v2 found a tl event for {tot}"
      f" (none for {nov2}: the join's window [-10, +20] vs v2's [-10, +2] with a different tie rule) | SAME E {pct(agree, tot)} | bar >= {AGREEMENT_BAR:.0%} -> {verdict}")
    # the 236 recovery
    P(f"- the 236 events in the v2 breakout list: STRICT {sum(1 for k in ev236['A'] if k in set(zip(TR.loc[(TR.strict == 1) & (TR.era == 'A') & (TR.setup == 'breakout'), 'sym'], TR.loc[(TR.strict == 1) & (TR.era == 'A') & (TR.setup == 'breakout'), 'E'])))} of 236"
      f" | WIDE {sum(1 for k in ev236['A'] if k in set(zip(TR.loc[(TR.era == 'A') & (TR.setup == 'breakout'), 'sym'], TR.loc[(TR.era == 'A') & (TR.setup == 'breakout'), 'E'])))} of 236")
    wide_set = set(zip(TR.loc[(TR.era == "A") & (TR.setup == "breakout"), "sym"], TR.loc[(TR.era == "A") & (TR.setup == "breakout"), "E"]))
    strict_set = set(zip(TR.loc[(TR.strict == 1) & (TR.era == "A") & (TR.setup == "breakout"), "sym"], TR.loc[(TR.strict == 1) & (TR.era == "A") & (TR.setup == "breakout"), "E"]))
    split = Counter()
    for k in ev236["A"]:
        d = d236[("A",) + k]
        band = "label delta <= 2 (inside v2's window)" if d <= W_FWD else "label delta >= 3 (outside v2's window by design)"
        split[(band, "strict" if k in strict_set else "wide" if k in wide_set else "missed")] += 1
    for band in ("label delta <= 2 (inside v2's window)", "label delta >= 3 (outside v2's window by design)"):
        n = sum(v for (b, _), v in split.items() if b == band)
        P(f"    {band}: {n} events | in v2 STRICT {split[(band, 'strict')]} | WIDE only {split[(band, 'wide')]} | missed {split[(band, 'missed')]}")
    P("    (a 236 event can be reached by v2 only through a pair whose s0 is within 2 sessions after E or 10 before it; the join read labels up to 20 sessions before E)")

    # ------------------------------------------------------------------ 4. FRAME READS as a precision check
    P(f"\n## 4. FRAME READS AS A PRECISION CHECK — bought moments whose on-screen ticker was CONFIRMED (status attributed or moved_unverified): P(caption == screen)")
    conf = lab[(lab.status.isin(["attributed", "moved_unverified"])) & (lab.grade.str.contains("bought"))].copy()
    conf["own_line"] = [int(rx.search((qmap.get((v, t, c), "") or "").lower()) is not None) for v, t, c in zip(conf.vid, conf.ts, conf.caption_ticker)]
    conf["same"] = (conf.triple_agree == "1").astype(int)
    pr_ev = {(r.video, r.ticker): (r.setup != "neither", r.resolves) for r in PR.itertuples(index=False)}
    conf["event"] = [int(pr_ev.get((v, c), (False, 0))[0]) for v, c in zip(conf.vid, conf.caption_ticker)]
    conf["resolves"] = [int(pr_ev.get((v, c), (False, 0))[1]) for v, c in zip(conf.vid, conf.caption_ticker)]
    P(f"- confirmed bought moments {len(conf)} | caption == screen overall {pct(int(conf.same.sum()), len(conf))}")
    for name, m in (("own line", conf.own_line == 1), ("window only", conf.own_line == 0)):
        g = conf[m]
        P(f"- {name:12s}: n {len(g)} | caption == screen {pct(int(g.same.sum()), len(g))}")
    for name, m in (("event in window", conf.event == 1), ("no event (resolved)", (conf.event == 0) & (conf.resolves == 1)), ("unresolved / no bar", conf.resolves == 0)):
        g = conf[m]
        P(f"- {name:20s}: n {len(g)} | caption == screen {pct(int(g.same.sum()), len(g))}")
    for name, m in (("own line AND event", (conf.own_line == 1) & (conf.event == 1)), ("own line, no event", (conf.own_line == 1) & (conf.event == 0) & (conf.resolves == 1)),
                    ("window only AND event", (conf.own_line == 0) & (conf.event == 1)), ("window only, no event", (conf.own_line == 0) & (conf.event == 0) & (conf.resolves == 1))):
        g = conf[m]
        P(f"- {name:22s}: n {len(g)} | caption == screen {pct(int(g.same.sum()), len(g))}")
    P("- caveat: caption != screen is an UPPER bound on the spoken ticker being wrong (the chart on screen may be a neighbour while he speaks of the named stock;"
      " 7 of 20 moved quotes read by hand belonged to the spoken ticker, 03_frame_check.py); it is the best $0 ground truth available at this scale")
    g = conf[(conf.own_line == 1) & (conf.same == 0)]
    P(f"- own-line moments whose confirmed screen ticker differs (most frequent caption->screen): {Counter(f'{c}->{s}' for c, s in zip(g.caption_ticker, g.screen_ticker)).most_common(20)}")

    # ------------------------------------------------------------------ 5. PLANTED wrong-ticker control
    P(f"\n## 5. PLANTED WRONG-TICKER CONTROL — {N_CONTROL} random wrong tickers per STRICT resolved pair (seed {SEED}; bar on s0, close >= ${MIN_PX:.0f}, close x volume >= ${MIN_DV / 1e6:.0f}M on s0)")
    rng = random.Random(SEED)
    pool = {"A": pool_a, "B": pool_b}
    hits = Counter()
    draws = 0
    nopool = 0
    for r in PR[(PR.own_line == 1) & (PR.resolves == 1)].itertuples(index=False):
        cands = [t for t in pool[r.era].get(r.s0, []) if t != r.sym and t != r.ticker]
        if len(cands) < N_CONTROL:
            nopool += 1
            continue
        i0 = s_idx(cal[r.era], r.s0)
        for t in rng.sample(cands, N_CONTROL):
            draws += 1
            m_tl = nearest(r.era, "tl", t, i0, W_BACK, W_FWD)
            m_ep = nearest(r.era, "ep", t, i0, W_BACK, W_FWD)
            if m_tl:
                hits["tl_all"] += 1
            a = ev.get((r.era, "tl", t))
            if a is not None:
                arr, rt = a
                lo, hi = int(arr.searchsorted(i0 - W_BACK)), int(arr.searchsorted(i0 + W_FWD, side="right"))
                if (rt[lo:hi] == 0).any():
                    hits["tl_first_any"] += 1
            if m_ep:
                hits["ep"] += 1
            if m_tl or m_ep:
                hits["any"] += 1
    P(f"- draws {draws} on {draws // N_CONTROL if N_CONTROL else 0} strict resolved pairs (pairs skipped for a thin pool: {nopool}) | pool sizes: era A median {int(np.median([len(v) for v in pool['A'].values()])) if pool['A'] else 0} tickers per s0, era B {int(np.median([len(v) for v in pool['B'].values()])) if pool['B'] else 0}")
    P(f"- FALSE-MATCH rate (a wrong ticker has an event in the window): tl any row {pct(hits['tl_all'], draws)} | tl first break present {pct(hits['tl_first_any'], draws)} |"
      f" EP {pct(hits['ep'], draws)} | any {pct(hits['any'], draws)}")
    sr = PR[(PR.own_line == 1) & (PR.resolves == 1)]
    P(f"- the STRICT resolved pairs' own rate: tl {pct(int(sr.has_tl.sum()), len(sr))} | EP {pct(int(sr.has_ep.sum()), len(sr))} | any {pct(int((sr.setup != 'neither').sum()), len(sr))}"
      f" -> lift over a wrong ticker: tl x{(sr.has_tl.sum() / len(sr)) / (hits['tl_all'] / draws) if draws and hits['tl_all'] else float('nan'):.2f},"
      f" EP x{(sr.has_ep.sum() / len(sr)) / (hits['ep'] / draws) if draws and hits['ep'] else float('nan'):.2f}")
    # beside: the no-grade mention pairs
    ngh = Counter()
    ngn = 0
    for p in ng_pairs:
        sym, via = resolve(p["ticker"], p["era"])
        if via == "unresolved" or not has_bar(sym, p["era"], p["i0"] - W_BACK, p["i0"] + W_FWD):
            continue
        ngn += 1
        m_tl = nearest(p["era"], "tl", sym, p["i0"], W_BACK, W_FWD)
        m_ep = nearest(p["era"], "ep", sym, p["i0"], W_BACK, W_FWD)
        ngh["tl"] += bool(m_tl)
        ngh["ep"] += bool(m_ep)
        ngh["any"] += bool(m_tl or m_ep)
    P(f"- BESIDE, merely MENTIONED (ticker-matched pairs with no grade, resolved): n {ngn} | tl {pct(ngh['tl'], ngn)} | EP {pct(ngh['ep'], ngn)} | any {pct(ngh['any'], ngn)}"
      f"  (he talks about stocks that are moving: the gap between this and the wrong-ticker rate is topic selection, the gap between this and the strict pairs is the bought phrase)")

    # ------------------------------------------------------------------ 6. HAND-CHECK sample
    P(f"\n## 6. HAND-CHECK SAMPLE — {SAMPLE_N} STRICT pairs with an event and NO frame-attributed label, stratified by upload year x setup (seed {SEED})")
    cand_s = PR[(PR.own_line == 1) & (PR.setup != "neither") & (PR.in_854_any == 0)].copy()
    cells = cand_s.groupby(["year", "setup"]).size()
    alloc = {}
    tot_n = len(cand_s)
    for k, n in cells.items():
        alloc[k] = max(1, int(round(SAMPLE_N * n / tot_n)))
    while sum(alloc.values()) > SAMPLE_N:                  # trim the most over-allocated cell that still has more than its floor of 1
        big = [k for k in alloc if alloc[k] > 1]
        if not big:
            break
        k = max(big, key=lambda x: (alloc[x] - SAMPLE_N * cells[x] / tot_n, alloc[x]))
        alloc[k] -= 1
    while sum(alloc.values()) < SAMPLE_N:
        k = min(alloc, key=lambda x: alloc[x] - SAMPLE_N * cells[x] / tot_n)
        alloc[k] += 1
    assert sum(alloc.values()) == SAMPLE_N, alloc
    rng2 = random.Random(SEED)
    picked = []
    for k, n in sorted(alloc.items()):
        g = cand_s[(cand_s.year == k[0]) & (cand_s.setup == k[1])].sort_values(["video", "ticker"])
        idx = sorted(rng2.sample(range(len(g)), min(n, len(g))))
        picked.append(g.iloc[idx])
    S = pd.concat(picked).reset_index(drop=True)
    S["n"] = range(1, len(S) + 1)
    S["t_secs"] = S.own_t.astype(float).round().astype(int)
    S["url"] = [f"https://youtu.be/{v}?t={max(int(t) - 15, 0)}" for v, t in zip(S.video, S.t_secs)]
    S["frame_png"] = [f"{VIS}/frames_grades/{f}.png" if f.startswith("g_") else "" for f in S.frame_id]
    S["verdict"] = ""
    S["why"] = ""
    S = S[["n", "video", "own_ts", "url", "upload", "title", "ticker", "sym", "era", "setup", "E_tl", "delta_tl", "retrigger_tl", "E_ep", "delta_ep", "same_day", "quote", "frame_id", "frame_png", "verdict", "why"]]
    S.to_csv(f"{OUT}/hand_check_30.tsv", sep="\t", index=False)
    P(f"- population {tot_n} pairs | cells {dict((f'{y}/{s}', int(n)) for (y, s), n in cells.items())} | drawn {len(S)} -> {OUT}/hand_check_30.tsv (url opens 15 s before the moment; verdict / why blank)")
    for r in S.itertuples(index=False):
        P(f"    {r.n:2d}. {r.ticker:5s} {r.setup:8s} E_tl {r.E_tl or '-':10s} E_ep {r.E_ep or '-':10s} | {r.url} | {r.upload} | \"{r.quote[:140]}\"")

    # ------------------------------------------------------------------ 7. minute coverage of the v2 event days (the replay's one hard dependency)
    P(f"\n## 7. MINUTE COVERAGE — is the day-0 minute file of each v2 (symbol, E) already fetched? (`_done.psv` status, any; no minute file opened; era B rows after the cut dropped)")
    done = {}
    for e, key in (("A", "done_A"), ("B", "done_B")):
        s = done.setdefault(e, set())
        n0 = n_drop = 0
        for ln in open(FILES[key]):
            p = ln.rstrip("\n").split("|")
            if len(p) < 4 or p[0] == "date":
                continue
            n0 += 1
            if e == "B" and p[0] > CUT_B:
                n_drop += 1
                continue
            s.add((p[1], p[0]))
        P(f"- {key}: {n0} rows, {n_drop} dated after {CUT_B} dropped")
    # the EP-day folder was fetched for era A days too (ESPR 2017-03-20 ...): count it for either era
    ep_done = set()
    for ln in open(FILES["done_ep"]):
        p = ln.rstrip("\n").split("|")
        if len(p) >= 4 and p[0] != "date" and p[0] <= CUT_B:
            ep_done.add((p[1], p[0]))
    TR["minutes_fetched"] = [int((s, E) in done[e] or (s, E) in ep_done) for e, s, E in zip(TR.era, TR.sym, TR.E)]
    for arm, mask in (("STRICT", TR.strict == 1), ("WIDE-only", (TR.strict == 0) & (TR.wide == 1))):
        g = TR[mask]
        P(f"- {arm}: {len(g)} trades | minutes already fetched {pct(int(g.minutes_fetched.sum()), len(g))} | by setup: "
          + ", ".join(f"{st} {pct(int(gg.minutes_fetched.sum()), len(gg))}" for st, gg in g.groupby("setup")))
    fetch = TR[TR.minutes_fetched == 0].copy()
    fetch["tier"] = np.where(fetch.strict == 1, 0, 1)
    fetch = fetch.sort_values(["tier", "E", "sym"])
    with open(f"{OUT}/v2_minute_fetch_list.psv", "w") as fh:
        fh.write("ticker|date|tier|era\n")
        for r in fetch.itertuples(index=False):
            fh.write(f"{r.sym}|{r.E}|{r.tier}|{r.era}\n")
    P(f"- FETCH LIST (tier 0 = strict, tier 1 = wide-only): {len(fetch)} (symbol, E) pairs, {fetch.E.nunique()} dates, era {dict(Counter(fetch.era))} -> {OUT}/v2_minute_fetch_list.psv")
    TR.to_csv(f"{OUT}/trades_v2.tsv", sep="\t", index=False)

    # ------------------------------------------------------------------ pins
    P("\n## Pins (sha256)")
    for name, path in list(FILES.items()) + [("this_script", os.path.abspath(__file__))]:
        P(f"- {name}: {sha(path)}  {path}")
    P(f"\nFiles: {OUT}/census.tsv, {OUT}/pairs_v2.tsv, {OUT}/trades_v2.tsv, {OUT}/hand_check_30.tsv")


if __name__ == "__main__":
    main()
