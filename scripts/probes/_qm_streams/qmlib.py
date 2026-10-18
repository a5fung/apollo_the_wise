"""Shared helpers for the #702 P4b stream mining: VTT parsing, ticker universe, keyword flags, ticker extraction.

$0 only - pure text/regex/pandas, no network, no model call.
"""
import bisect
import datetime as dt
import os
import re
from collections import defaultdict

CUE_RE = re.compile(r"(\d+):(\d\d):(\d\d)\.(\d+)\s+-->\s+(\d+):(\d\d):(\d\d)\.(\d+)")
TS_RE = re.compile(r"<(\d+:\d\d:\d\d\.\d+)>")
TAG_RE = re.compile(r"</?c[^>]*>|<[^>]+>")
FILLER_LINES = {"foreign", "[music]", "[applause]", "[laughter]", "[ music ]", "(music)"}


def _secs(h, m, s, frac):
    return int(h) * 3600 + int(m) * 60 + int(s) + float("0." + frac)


def _ts_secs(ts):
    h, m, rest = ts.split(":")
    s, frac = rest.split(".")
    return _secs(h, m, s, frac)


def parse_vtt(path):
    """YouTube rolling auto-caption VTT -> list of (t_seconds, word). De-duplicates the rolling repeats:
    only the inline-timed ('tagged') line of each cue carries NEW words; untagged lines are repeats of an
    earlier tagged line (or standalone one-shot captions, kept once)."""
    raw = open(path, encoding="utf-8", errors="replace").read().replace("\r", "")
    blocks = re.split(r"\n\s*\n", raw)
    words = []
    recent = []                      # normalized text of recent emitted lines
    any_tagged = "<c>" in raw or TS_RE.search(raw) is not None
    for b in blocks:
        lines = b.split("\n")
        k = next((i for i, ln in enumerate(lines) if CUE_RE.search(ln)), None)
        if k is None:
            continue
        m = CUE_RE.search(lines[k])
        t0 = _secs(*m.group(1, 2, 3, 4))
        text = [ln for ln in lines[k + 1:] if ln.strip()]
        tagged = [ln for ln in text if TS_RE.search(ln) or "<c>" in ln]
        if tagged:
            for ln in tagged:
                parts = TS_RE.split(ln)
                for j in range(0, len(parts), 2):
                    t = t0 if j == 0 else _ts_secs(parts[j - 1])
                    seg = TAG_RE.sub("", parts[j])
                    for w in seg.split():
                        words.append((t, w))
                recent.append(TAG_RE.sub("", ln).strip().lower())
            recent = recent[-8:]
        else:
            for ln in text:
                norm = TAG_RE.sub("", ln).strip().lower()
                if not norm or norm in FILLER_LINES:
                    continue
                if any_tagged and any(norm == r or norm in r for r in recent):
                    continue
                if (not any_tagged) and norm in recent:
                    continue
                recent.append(norm)
                recent = recent[-8:]
                for w in TAG_RE.sub("", ln).split():
                    words.append((t0, w))
    return words


def tokenize(words):
    """words [(t, raw)] -> [(t, token)] lowercase letters only (apostrophes / possessives stripped)."""
    out = []
    for t, w in words:
        w = w.lower().replace("\u2019", "'")
        w = re.sub(r"'s$", "", w)
        w = re.sub(r"[^a-z0-9&.]", "", w)
        w = w.strip(".")
        if w:
            out.append((t, w))
    return out


def window_text(words, t0, t1):
    return " ".join(w for t, w in words if t0 <= t <= t1)


# ---------------------------------------------------------------- keyword flags
KW = {
    "base": r"\bbases?\b",
    "flag": r"\bflags?\b",
    "tight": r"\btight(?:er|ly)?\b",
    "tightening": r"\btighten(?:s|ed|ing)?\b",
    "wedge": r"\bwedges?\b",
    "triangle": r"\btriangles?\b",
    "trendline": r"\btrend ?lines?\b",
    "line": r"\blines?\b",
    "wick": r"\bwicks?\b",
    "draw": r"\b(?:draw|draws|drawing|drawn|drew)\b",
    "breakout": r"\bbreak(?:ing|s)? ?outs?\b|\bbroke out\b",
    "orh": r"\bopening range\b|\borh\b|\bopening high\b",
    "pivot": r"\bpivots?\b",
    "ep": r"\b(?:eps?|episodic|e p)\b",
    "gap": r"\bgap(?:s|ped|ping)?\b",
    "surf": r"\bsurf(?:ing|s|ed)?\b|\b(?:10|ten|20|twenty)[- ]?(?:day|d)\b|\b(?:10|20) ?(?:sma|ma|ema)\b|\bmoving averages?\b",
    "higher_lows": r"\bhigher lows?\b",
    "vol_dry": r"\b(?:volume|vol)\b.{0,25}\b(?:dry|dried|drying|dries|light|low|contract\w*|disappear\w*)\b|\bdr(?:y|ies|ied|ying) up\b",
    "vol_up": r"\b(?:volume|vol)\b.{0,25}\b(?:up|surg\w*|spik\w*|expan\w*|heavy|huge|big)\b|\b(?:heavy|huge|big|massive) volume\b",
}
KW_RE = {k: re.compile(v) for k, v in KW.items()}
# the shape words: what he says when he is LOOKING AT / DRAWING a base
CHART_KW = ("base", "flag", "tight", "tightening", "wedge", "triangle", "trendline", "line", "wick", "draw", "higher_lows", "vol_dry")
CONTEXT_KW = ("breakout", "orh", "pivot", "ep", "gap", "surf", "vol_up")
KW_WEIGHT = {"base": 3, "flag": 3, "tight": 3, "tightening": 3, "wedge": 3, "triangle": 3, "trendline": 4, "line": 1,
             "wick": 3, "draw": 2, "higher_lows": 2, "vol_dry": 2, "breakout": 1, "orh": 1, "pivot": 1, "ep": 0.5,
             "gap": 0.5, "surf": 1, "vol_up": 0.5}


def kw_flags(text):
    return {k: int(bool(r.search(text))) for k, r in KW_RE.items()}


def kw_strength(flags, text=""):
    return sum(KW_WEIGHT[k] for k, v in flags.items() if v)


# ---------------------------------------------------------------- ticker universe
def d2o(s):
    return dt.date.fromisoformat(s[:10]).toordinal()


def load_universe(closes_gz, cache):
    """ticker -> sorted list of date ordinals with a bar (cached as a pickle of numpy arrays)."""
    import pickle
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    import numpy as np
    import pandas as pd
    df = pd.read_csv(closes_gz, header=None, usecols=[0, 1], names=["t", "d"], dtype={"t": "category", "d": "string"})
    df["o"] = pd.to_datetime(df["d"]).map(dt.datetime.toordinal)
    uni = {}
    for t, g in df.groupby("t", observed=True):
        uni[str(t)] = np.sort(g["o"].to_numpy(dtype=np.int32))
    pickle.dump(uni, open(cache, "wb"))
    return uni


def tickers_in_window(uni, center_ord, days=60):
    lo, hi = center_ord - days, center_ord + days
    out = set()
    for t, arr in uni.items():
        i = bisect.bisect_left(arr, lo) if isinstance(arr, list) else int(arr.searchsorted(lo))
        if i < len(arr) and arr[i] <= hi:
            out.add(t)
    return out
