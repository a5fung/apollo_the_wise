"""#624 backfill — shared, pure helpers. Mirrors of the live pure functions; the rule itself is IMPORTED.

Nothing here reads an outcome. The walker lives in walk624.py; the screen in screen624.py.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import statistics
import subprocess
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from agents.market_intelligence import lowcap_lane as LL  # noqa: E402
from agents.market_intelligence.constants import SKIP_TICKERS  # noqa: E402
from agents.market_intelligence.ep_detector import (  # noqa: E402
    EP_COOLDOWN_DAYS, MAX_EXTENSION_PCT, MIN_PREMARKET_SHARES, MIN_PREV_CLOSE, MIN_PREV_DAY_VOLUME)
from agents.market_intelligence.backtester.filters import MAX_ATR_PCT, MIN_ADV_DOLLAR_VOLUME  # noqa: E402

ET = ZoneInfo("America/New_York")
TODAY = date(2026, 10, 6)
DATA_END = date(2026, 10, 5)
TICKS = (time(9, 30), time(9, 31), time(9, 35), time(9, 40), time(9, 45), time(9, 50), time(9, 55))
STOCK_TYPES = ("CS", "ADRC")
NONSTOCK_TODAY = ("ETF", "WARRANT", "UNIT", "PFD", "RIGHT", "FUND", "SP", "ETS", "ETV", "ETN")

# ── the freeze: the probe refuses to run on drifted code or a drifted rule ───────────────
FROZEN_BLOBS = {
    "agents/market_intelligence/lowcap_lane.py": "7bb49f266cc1",
    "agents/market_intelligence/lowcap_lane_replay.py": "24a14d012ee8",
    "agents/market_intelligence/sustain_reject_replay.py": "098f1f595322",
    "agents/market_intelligence/live_fill_counterfactuals.py": "f374fefd5338",
    "agents/market_intelligence/rule_eras.py": "6785a809959c",
    "agents/market_intelligence/ep_detector.py": "1581b8661bd7",
    "agents/market_intelligence/backtester/filters.py": "b96021ac6f80",
    "agents/market_intelligence/alert_rank_shadow.py": "0d4ef59cda77",
    "scripts/probes/_687/backfill.py": "c53987221734",
    "scripts/probes/_685/study.py": "d7794ee825e1",
}
PREREG_SHA = "e56902f4e3ced2ecce35547b2f332cb9e4887aa3aeae59fa997270b94438fc90"


def assert_frozen() -> None:
    bad = []
    for p, want in FROZEN_BLOBS.items():
        got = subprocess.run(["git", "hash-object", str(REPO / p)], capture_output=True, text=True).stdout.strip()[:12]
        if got != want:
            bad.append(f"{p}: {got} != {want}")
    s = open(REPO / "docs/analysis/624_lowcap_backfill_2026-10-06.md").read()
    sha = hashlib.sha256(s[s.index("## Pre-registration (frozen"):s.index("## Results")].encode()).hexdigest()
    if sha != PREREG_SHA:
        bad.append(f"prereg section sha {sha[:12]} != {PREREG_SHA[:12]}")
    consts = (LL.LANE_MIN_GAP_PCT, LL.LANE_MIN_VOL_PERCENTILE, LL.LANE_MIN_PREV_CLOSE, float(LL.LANE_MAX_MARKET_CAP))
    if consts != (15.0, 90.0, 5.0, 5e8):
        bad.append(f"lane constants drifted: {consts}")
    if (MIN_PREV_CLOSE, MIN_PREV_DAY_VOLUME, MIN_PREMARKET_SHARES, MAX_EXTENSION_PCT, EP_COOLDOWN_DAYS,
            MIN_ADV_DOLLAR_VOLUME, MAX_ATR_PCT) != (5.0, 50_000, 25_000, 50.0, 60, 1_000_000, 15.0):
        bad.append("MAGNA53 stamp constants drifted")
    if bad:
        raise SystemExit("FREEZE CHECK FAILED — " + "; ".join(bad))


# ── loaders ───────────────────────────────────────────────────────────────────────────────

def _open(p: Path):
    p = Path(p)
    if not p.exists() and Path(str(p) + ".gz").exists():
        p = Path(str(p) + ".gz")
    return gzip.open(p, "rt") if str(p).endswith(".gz") else open(p)


def fnum(x):
    if x in (None, "", "None"):
        return None
    return float(x)


def load_daily(path=HERE / "s0_daily.tsv") -> dict[str, dict]:
    """ticker -> {"dates": [date..], "rows": {date: {o,h,l,c,v}}} (adjusted, as stored)."""
    out: dict[str, dict] = {}
    with _open(path) as fh:
        next(fh)
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7:
                continue
            t, d = p[0], date.fromisoformat(p[1])
            e = out.setdefault(t, {"rows": {}})
            e["rows"][d] = {"o": fnum(p[2]), "h": fnum(p[3]), "l": fnum(p[4]), "c": fnum(p[5]), "v": fnum(p[6])}
    for e in out.values():
        e["dates"] = sorted(e["rows"])
    return out


def load_cand(path=HERE / "s0_cand.tsv") -> list[dict]:
    rows = []
    with _open(path) as fh:
        next(fh)
        for line in fh:
            p = line.rstrip("\n").split("|")
            rows.append({"t": p[0], "d": date.fromisoformat(p[1]), "o": fnum(p[2]), "h": fnum(p[3]), "l": fnum(p[4]),
                         "c": fnum(p[5]), "v": fnum(p[6]), "pc": fnum(p[7]), "pv": fnum(p[8]),
                         "pd": date.fromisoformat(p[9]) if p[9] not in ("", "None") else None, "fac": float(p[10])})
    return rows


def load_splits(path=HERE / "splits.json") -> dict[str, list[tuple[date, float]]]:
    by = defaultdict(list)
    for s in json.load(_open(path)):
        ed = date.fromisoformat(s["execution_date"])
        if ed <= TODAY and s.get("split_from") and s.get("split_to"):
            by[s["ticker"]].append((ed, float(s["split_to"]) / float(s["split_from"])))
    return by


def fac_prior(splits, t: str, d: date) -> float:
    """raw = adjusted x fac for values dated BEFORE d (D-1 close/volume): splits executing on/after d."""
    f = 1.0
    for ed, r in splits.get(t, ()):
        if ed >= d:
            f *= r
    return f


def fac_day(splits, t: str, d: date) -> float:
    """raw = adjusted x fac for D's OWN values (price at T, acting volume at T): splits executing after d."""
    f = 1.0
    for ed, r in splits.get(t, ()):
        if ed > d:
            f *= r
    return f


def iter_minutes(paths):
    """Stream (ticker, D, bars) from fetch captures; bars = [(mod, o, h, l, c, v)] sorted, mod = ET minute of day.
    The fetcher writes one key's bars consecutively; a key split across files/workers is merged by the caller."""
    for path in paths:
        cur, buf = None, {}
        with _open(path) as fh:
            for line in fh:
                p = line.rstrip("\n").split("|")
                if len(p) != 7:
                    continue
                try:
                    hh, mm = int(p[1][11:13]), int(p[1][14:16])
                    bar = (hh * 60 + mm, float(p[2]), float(p[3]), float(p[4]), float(p[5]),
                           float(p[6]) if p[6] not in ("", "None") else 0.0)
                except ValueError:
                    continue
                key = (p[0], date.fromisoformat(p[1][:10]))
                if key != cur:
                    if cur is not None:
                        yield cur[0], cur[1], [buf[k] for k in sorted(buf)]
                    cur, buf = key, {}
                buf[bar[0]] = bar
        if cur is not None:
            yield cur[0], cur[1], [buf[k] for k in sorted(buf)]


def load_minutes(paths, keys=None) -> dict[tuple[str, date], list[tuple]]:
    out: dict[tuple[str, date], dict] = {}
    for t, d, bars in iter_minutes(paths):
        if keys is not None and (t, d) not in keys:
            continue
        e = out.setdefault((t, d), {})
        for b in bars:
            e[b[0]] = b
    return {k: [v[m] for m in sorted(v)] for k, v in out.items()}


def as_dict_bars(d: date, bars: list[tuple], rth_only: bool = True) -> list[dict]:
    """Tuple bars -> the walker's shape {m (aware ET), o,h,l,c} (RTH 09:30-15:59 when rth_only)."""
    out = []
    for mod, o, h, l, c, v in bars:
        if rth_only and not (570 <= mod < 960):
            continue
        out.append({"m": datetime.combine(d, time(mod // 60, mod % 60), tzinfo=ET), "o": o, "h": h, "l": l, "c": c, "v": v})
    return out


def load_minlog(paths) -> dict[tuple[str, date], tuple[int, int, str]]:
    out = {}
    for path in paths:
        if not Path(path).exists():
            continue
        for line in open(path):
            q = line.rstrip("\n").split("|")
            if len(q) == 5:
                out[(q[0], date.fromisoformat(q[1]))] = (int(q[2]), int(q[3]), q[4])
    return out


def load_refs(paths) -> dict[tuple[str, date], dict]:
    out = {}
    for path in paths:
        if not Path(path).exists() and not Path(str(path) + ".gz").exists():
            continue
        with _open(path) as fh:
            for line in fh:
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                out[(j["t"], date.fromisoformat(j["d"]))] = j
    return out


def load_sectypes(path=HERE / "s0_sectypes.tsv") -> dict[str, str]:
    out = {}
    with _open(path) as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) >= 2:
                out[p[0]] = p[1]
    return out


# ── pre-open terms (every window ends at D-1: W5) ─────────────────────────────────────────

def rows_before(dl: dict, d: date, start: date) -> list[tuple[date, dict]]:
    """Stored daily rows with start <= trade_date < d (D's own row NEVER included)."""
    ds = dl["dates"]
    i0, i1 = bisect_left(ds, start), bisect_left(ds, d)
    return [(x, dl["rows"][x]) for x in ds[i0:i1]]


def vol_history(dl: dict | None, d: date, days: int = 60) -> list[float]:
    """db.get_volume_history_daily_closes for ONE ticker, line for line: rows in [d-124, d), skip if <20 rows,
    rolling 20-row mean volume at every end-date >= d-60."""
    if not dl:
        return []
    fetch_cutoff = d - timedelta(days=int(days * 1.4) + 40)
    day_rows = [(x, r["v"]) for x, r in rows_before(dl, d, fetch_cutoff)]
    if len(day_rows) < 20:
        return []
    window_cutoff = d - timedelta(days=days)
    out = []
    for i in range(19, len(day_rows)):
        if day_rows[i][0] < window_cutoff:
            continue
        out.append(sum(v for _, v in day_rows[i - 19:i + 1]) / 20.0)
    return out


def extension_pct(dl: dict | None, d: date, pc_adj: float) -> float | None:
    """ep_detector's extension_map: MIN(close) over trade_date in [d-10, d); ext = (pc - min)/min x 100, 2 dp."""
    if not dl:
        return None
    cl = [r["c"] for _, r in rows_before(dl, d, d - timedelta(days=10)) if r["c"] is not None]
    if not cl:
        return None
    lc5 = min(cl)
    if not lc5 or lc5 <= 0 or not pc_adj:
        return None
    return round((pc_adj - lc5) / lc5 * 100.0, 2)


def adv_dollar(dl: dict | None, d: date) -> float | None:
    """filters._check_adv_dollar_volume at 09:3x on D: rows in [D-30, D-1] with volume > 0, >= 10 rows,
    PERCENTILE_CONT(0.5) of close x volume (adjusted x adjusted = raw dollars). None = adv_no_data."""
    if not dl:
        return None
    vals = sorted(r["c"] * r["v"] for _, r in rows_before(dl, d, d - timedelta(days=30))
                  if r["v"] and r["v"] > 0 and r["c"] is not None)
    if len(vals) < 10:
        return None
    return statistics.median(vals)


def atr_pct_stamp(dl: dict | None, d: date) -> float | None:
    """filters.compute_atr_14 at 09:3x on D: rows [D-35, D-1] with H/L, >= 10 rows, Wilder TR, last 14; / last close."""
    if not dl:
        return None
    rows = [r for _, r in rows_before(dl, d, d - timedelta(days=35)) if r["h"] is not None and r["l"] is not None]
    if len(rows) < 10:
        return None
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"])) for p, r in zip(rows, rows[1:])]
    if not trs:
        return None
    w = trs[-14:]
    atr = sum(w) / len(w)
    lc = rows[-1]["c"]
    return atr / lc * 100 if lc and lc > 0 else None


# ── tick readings ─────────────────────────────────────────────────────────────────────────

def _mod(T: time) -> int:
    return T.hour * 60 + T.minute


def tick_price(bars: list[tuple], T: time, mode930: str = "open930") -> float | None:
    """Polygon reconstruction of the Alpaca last trade at tick T (prereg §2). bars = tuples (mod,o,h,l,c,v).
    T = 09:30: the 09:30 bar's OPEN ('open930') or the 09:29 bar's close ('close929'); T >= 09:31: the close of the
    bar that started at T-1. No such bar -> the latest earlier bar's close since 04:00; none -> None."""
    if not bars:
        return None
    if T == time(9, 30):
        if mode930 == "open930":
            for b in bars:
                if b[0] == 570:
                    return b[1]
            prev = [b for b in bars if 240 <= b[0] < 570]
            return prev[-1][4] if prev else None
        prev = [b for b in bars if 240 <= b[0] <= 569]
        return prev[-1][4] if prev else None
    tm1 = _mod(T) - 1
    prev = [b for b in bars if 240 <= b[0] <= tm1]
    return prev[-1][4] if prev else None


def tick_volume(bars: list[tuple], T: time, k: int) -> float:
    """Sum of minute volume for bars starting in [04:00, T - k min)."""
    cut = _mod(T) - k
    return sum(b[5] for b in bars if 240 <= b[0] < cut)


def gap_pct(price: float | None, pc_adj: float | None) -> float | None:
    if price is None or not pc_adj or pc_adj <= 0:
        return None
    return round((price - pc_adj) / pc_adj * 100.0, 2)   # live: round(rt_gap, 2)


def free_terms(t: str, gap: float | None, pc_raw: float | None, vol_adj: float, hist: list[float]):
    """THE RULE, imported: lowcap_lane.free_terms on the live candidate shape."""
    return LL.free_terms({"ticker": t, "gap_pct": gap, "prev_close": pc_raw, "today_volume": vol_adj}, hist)


def blocking_stamps(*, ext, cooldown, days_since, adv, atr_pct, vol_raw) -> list[dict]:
    """lowcap_lane.blocking_filters_for on the live row shape (shortlist / M&A not reconstructed: absent)."""
    if adv is None:
        q = "filter:adv_no_data"
    elif adv < MIN_ADV_DOLLAR_VOLUME:
        q = f"filter:adv_too_low: ${adv:,.0f}"
    elif atr_pct is not None and atr_pct > MAX_ATR_PCT:
        q = f"filter:atr_too_high: {atr_pct:.1f}% > {MAX_ATR_PCT}%"
    else:
        q = None
    return LL.blocking_filters_for(extension_pct=ext, on_cooldown=cooldown, days_since_prior_alert=days_since,
                                   quality_reason=q, quality_adv_dollar=adv, atr_pct=atr_pct,
                                   acting_rank=None, ma_flag=None, today_volume=vol_raw)


def common_type(ref: dict | None) -> str | None:
    if not ref or not ref.get("r"):
        return None
    return ref["r"].get("type")


def shares_of(ref: dict | None) -> float | None:
    if not ref or not ref.get("r"):
        return None
    r = ref["r"]
    s = r.get("weighted_shares_outstanding") or r.get("share_class_shares_outstanding")
    return float(s) if s else None
