"""#687 STEP 0 — the REBUILT EP-like population (NOT our live alerts; there were none for most of this history).

Every rule below was fixed BEFORE any outcome was computed. Inputs: pull_pop_out.txt (prod pull 2, the SQL rules),
pull_daily_out.txt (prod pull 3, daily bars per ticker), pull_sectypes_out.txt (prod pull 4, mi_security_types),
splits.json (Polygon splits since 2024-01-02), types_unclassified.json (Polygon type lookup for tickers absent from
mi_security_types today — delisted names, kept when common stock so the list does not survive-bias).

RULES (the live admission rules that CAN be computed from daily bars, in the order the live scan applies them):
  1. universe: ticker <= 5 upper-case letters (MAX_TICKER_LEN / no '.'), not in constants.SKIP_TICKERS, security type
     CS or ADRC (mi_security_types today, else Polygon's reference type for delisted names; the live scan skips
     non-stock AND unclassified — here an unclassified name whose Polygon type is CS/ADRC is KEPT, stated).
  2. prior close >= $5 and prior-day volume >= 50,000 shares (MIN_PREV_CLOSE / MIN_PREV_DAY_VOLUME) applied to the RAW
     (unadjusted) values: mi_daily_closes is split-adjusted, so a later reverse split lifts an old $0.75 close to $11 —
     the raw value is recovered from Polygon's split table (price x prod(split_to/split_from) of later splits).
  3. gap >= 9% = the day's official open vs the prior close (MIN_GAP_PCT 9.0; the live 09:30 real-time re-check uses
     the same open).
  4. extension: (prev_close - min close over [D-10 calendar days, D-1]) / min < 50% (MAX_EXTENSION_PCT, the live
     extension_map window).
  5. quality (check_filters): 30-calendar-day median dollar volume through D-1 >= $1M with >= 10 rows
     (_check_adv_dollar_volume as it stands at 09:31); ATR14% (Wilder TR, rows in [D-35, D-1], last 14 TRs, / prev
     close) <= 15% (_check_atr_pct; < 10 rows -> passes, as live). Market cap >= $500M is NOT applied (FMP, current-only).
  6. volume confirmation PROXY for the live RVOL rule: the gap day's FULL-DAY volume >= 3x the mean volume of the prior
     20 sessions. This is a PROXY and it LOOKS AHEAD: live gates on RVOL at scan time (pre-market / first minutes); the
     full-day volume is known only at the close and selects for days that kept trading. It biases WHICH days enter, not
     the arm-vs-arm pairing on the trades that did.
  7. cooldown: one entry per ticker per 60 days (EP_COOLDOWN_DAYS; live keys on alerts, here on qualifying rows).
NOT applied (not computable from bars): catalyst grade / EP score / regime threshold / pre-market share floor /
market cap / theme membership / the operator's judgement. Stated in the doc.

Outputs: population.tsv (the list), population_out.txt (composition + every exclusion count). HALT rule: a surprising
trait (one ticker dominating, most rows under $10) is printed and stops the run for a human read.
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
from agents.market_intelligence.constants import SKIP_TICKERS  # noqa: E402

MAX_ATR_PCT = 15.0
MIN_PREV_CLOSE = 5.0
MIN_PREV_DAY_VOLUME = 50_000
VOL_MULT = 3.0
COOLDOWN_DAYS = 60


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_daily() -> dict[str, dict[date, dict]]:
    out: dict[str, dict[date, dict]] = {}
    with open(HERE / "pull_daily_out.txt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7 or p[0] in ("ticker",) or p[0].startswith("==="):
                continue
            try:
                d = date.fromisoformat(p[1])
            except ValueError:
                continue
            out.setdefault(p[0], {})[d] = {"o": _f(p[2]), "h": _f(p[3]), "l": _f(p[4]), "c": _f(p[5]), "v": _f(p[6])}
    return out


def atr14_pct_live(dbars: dict[date, dict], d: date) -> float | None:
    """filters.compute_atr_14 as it stands at 09:31 on day d: rows in [d-35, d-1], Wilder TR, last 14 TRs, / last close."""
    rows = [dbars[x] for x in sorted(dbars) if d - timedelta(days=35) <= x < d
            and dbars[x]["h"] is not None and dbars[x]["l"] is not None and dbars[x]["c"] is not None]
    if len(rows) < 10:
        return None
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"])) for p, r in zip(rows, rows[1:])]
    if not trs:
        return None
    w = trs[-14:]
    atr = sum(w) / len(w)
    lc = rows[-1]["c"]
    return atr / lc * 100 if lc else None


def main():
    log = open(HERE / "population_out.txt", "w")

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s); log.write(s + "\n")

    rows = []
    lines = [l.rstrip("\n") for l in open(HERE / "pull_pop_out.txt") if not l.startswith("===") and not l.startswith("(")]
    hdr = lines[0].split("|")
    for l in lines[1:]:
        p = l.split("|")
        if len(p) == len(hdr):
            rows.append(dict(zip(hdr, p)))
    for r in rows:
        r["d"] = date.fromisoformat(r["trade_date"])
        for k in ("o", "h", "l", "c", "v", "pc", "pv", "avgv20", "gap_pct", "low_close", "ext_pct", "adv_dollar", "vol_mult"):
            r[k] = _f(r[k])
    P(f"# #687 population build — SQL candidates (gap>=9%, adj prior close>=$5, adj prior vol>=50k, ADV$>=1M, ext<50%): {len(rows)}")

    st = {}
    for l in open(HERE / "pull_sectypes_out.txt"):
        p = l.rstrip("\n").split("|")
        if len(p) == 4 and p[0] != "ticker":
            st[p[0]] = p[1]
    poly = json.load(open(HERE / "types_unclassified.json"))
    splits = collections.defaultdict(list)
    for s in json.load(open(HERE / "splits.json")):
        splits[s["ticker"]].append(s)
    daily = load_daily()

    def sec_type(t):
        if t in st:
            return st[t], "mi_security_types"
        rec = poly.get(t) or {}
        return rec.get("type") or "UNKNOWN", "polygon"

    def raw_factor(t, d):
        f = 1.0
        for s in splits.get(t, []):
            if date.fromisoformat(s["execution_date"]) > d:
                f *= s["split_to"] / s["split_from"]
        return f

    excl = collections.Counter()
    kept = []
    for r in rows:
        t = r["ticker"]
        if t in SKIP_TICKERS:
            excl["1.skip_tickers_list"] += 1; continue
        typ, src = sec_type(t)
        if typ not in ("CS", "ADRC"):
            excl[f"1.non_stock:{typ}"] += 1; continue
        r["sec_src"] = src
        f = raw_factor(t, r["d"])
        r["raw_pc"] = r["pc"] * f
        r["raw_pv"] = r["pv"] / f
        r["split_factor"] = f
        if r["raw_pc"] < MIN_PREV_CLOSE:
            excl["2.raw_prior_close_below_5"] += 1; continue
        if r["raw_pv"] < MIN_PREV_DAY_VOLUME:
            excl["2.raw_prior_vol_below_50k"] += 1; continue
        ap = atr14_pct_live(daily.get(t, {}), r["d"])
        r["atr_pct"] = ap
        if ap is not None and ap > MAX_ATR_PCT:
            excl["5.atr_pct_above_15"] += 1; continue
        if r["vol_mult"] is None or r["vol_mult"] < VOL_MULT:
            excl["6.volume_proxy_below_3x"] += 1; continue
        kept.append(r)
    kept.sort(key=lambda r: (r["d"], r["ticker"]))
    last = {}
    final = []
    for r in kept:
        t = r["ticker"]
        if t in last and (r["d"] - last[t]).days < COOLDOWN_DAYS:
            excl["7.cooldown_60d"] += 1; continue
        last[t] = r["d"]
        final.append(r)
    P("## exclusions (in order applied):", dict(sorted(excl.items())))
    P(f"## FINAL population: {len(final)} gap-days on {len({r['ticker'] for r in final})} tickers; "
      f"delisted-since (Polygon-typed) tickers kept: {len({r['ticker'] for r in final if r.get('sec_src') == 'polygon'})}; "
      f"rows with a later split (raw floors re-applied): {sum(1 for r in final if r['split_factor'] != 1.0)}")

    def comp(pop, label):
        P(f"## COMPOSITION {label} n={len(pop)}")
        P("   by year:", dict(sorted(collections.Counter(r["d"].year for r in pop).items())))
        P("   by month:", dict(sorted(collections.Counter(r["d"].strftime("%Y-%m") for r in pop).items())))
        pb = collections.Counter("<10" if r["raw_pc"] < 10 else "10-20" if r["raw_pc"] < 20 else "20-50" if r["raw_pc"] < 50
                                 else "50-100" if r["raw_pc"] < 100 else "100+" for r in pop)
        P("   raw prior-close band:", dict(pb))
        gb = collections.Counter("9-12" if r["gap_pct"] < 12 else "12-15" if r["gap_pct"] < 15 else "15-20" if r["gap_pct"] < 20
                                 else "20-30" if r["gap_pct"] < 30 else "30-50" if r["gap_pct"] < 50 else "50+" for r in pop)
        P("   gap band:", dict(gb))
        tc = collections.Counter(r["ticker"] for r in pop)
        P("   top tickers:", tc.most_common(8), "distinct", len(tc))
        P(f"   medians: gap {statistics.median(r['gap_pct'] for r in pop):.1f}% raw prior close ${statistics.median(r['raw_pc'] for r in pop):.2f} "
          f"vol proxy {statistics.median(r['vol_mult'] for r in pop):.1f}x ADV$ {statistics.median(r['adv_dollar'] for r in pop) / 1e6:.1f}M")
        P(f"   DISCOVERY (2024): {sum(1 for r in pop if r['d'].year == 2024)}  HELD-OUT (2025-01..2026-04): {sum(1 for r in pop if r['d'].year >= 2025)}")
    comp(final, "FINAL")
    # HALT checks
    alarms = []
    top = collections.Counter(r["ticker"] for r in final).most_common(1)[0]
    if top[1] > 0.02 * len(final):
        alarms.append(f"one ticker dominates: {top}")
    if sum(1 for r in final if r["raw_pc"] < 10) > 0.5 * len(final):
        alarms.append("most rows under $10")
    mo = collections.Counter(r["d"].strftime("%Y-%m") for r in final)
    if max(mo.values()) > 0.15 * len(final):
        alarms.append(f"one month dominates: {mo.most_common(1)}")
    P("## HALT CHECK:", "ALARMS " + "; ".join(alarms) if alarms else "no surprising trait (no ticker > 2%, under-$10 share < 50%, no month > 15%)")
    cols = ["ticker", "trade_date", "o", "h", "l", "c", "v", "pc", "pv", "raw_pc", "raw_pv", "split_factor", "gap_pct", "ext_pct",
            "adv_dollar", "atr_pct", "vol_mult", "sec_src"]
    with open(HERE / "population.tsv", "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in final:
            fh.write("|".join("" if r.get(c) is None else str(r[c]) for c in cols) + "\n")
    log.close()
    if alarms:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
