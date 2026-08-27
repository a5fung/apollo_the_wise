"""Silent-days verification (2026-08-25) — arithmetic only, reads the two captures.

Re-derives, from mi_daily_closes, the SAME quantities the live gates compute
(filters.py::_check_adv_dollar_volume / compute_atr_14, ep_detector extension) for
  (a) the 25 evidence/operator-labelled real EPs in tests/fixtures/must_not_miss_eps.py, and
  (b) every name that cleared the D-1 universe floors on 2026-08-24 / 2026-08-25.
So "does a rejected name look like a real EP?" is answered on OUR OWN data, on one basis,
rather than on the numbers baked into a skip-reason string.
NO writes, no network, no paid calls.
"""
from __future__ import annotations
import re, sys, json, statistics
from datetime import date, timedelta
from collections import defaultdict

ROOT = "/Users/alvinfung/apollo_the_wise/scripts/probes/"

def blocks(path):
    out, cur = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^===([A-Z0-9_]+)===$", line)
        if m:
            cur = m.group(1); out[cur] = []; continue
        if cur is not None: out[cur].append(line)
    return out

def rows(lines):
    lines = [l for l in lines if l.strip() and not re.match(r"^\(\d+ rows?\)$", l.strip())]
    if not lines: return []
    hdr = lines[0].split("|~|")
    out = []
    for l in lines[1:]:
        p = l.split("|~|")
        if len(p) != len(hdr): continue
        out.append(dict(zip(hdr, p)))
    return out

def f(v):
    try: return float(v)
    except (TypeError, ValueError): return None

B1 = blocks(ROOT + "_silentdays_capture_out.txt")
B2 = blocks(ROOT + "_silentdays_capture2_out.txt")

# ── bars: ticker -> sorted list of (date, o,h,l,c,v) ─────────────────────────────────────────
bars = defaultdict(list)
for blk in (B1.get("Q9_DAILY_CLOSES", []), B2.get("U1_UPSTREAM_CLOSES", []), B2.get("F1_FIXTURE_CLOSES", [])):
    for r in rows(blk):
        bars[r["ticker"]].append((
            date.fromisoformat(r["trade_date"]), f(r["open_price"]), f(r["high_price"]),
            f(r["low_price"]), f(r["close"]), f(r["volume"])))
for t in bars: bars[t].sort()

def prior(t, d):
    """bars strictly before d"""
    return [b for b in bars.get(t, []) if b[0] < d]

def adv_dollar(t, d):
    """filters.py: median(close*volume) over trade_date <= d and >= d-30d, >=10 rows.
    The live call passes today's date, but mi_daily_closes has no row for today at scan time,
    so this is prior sessions only — same set the live query saw."""
    w = [b for b in bars.get(t, []) if d - timedelta(days=30) <= b[0] <= d and (b[5] or 0) > 0]
    if len(w) < 10: return None
    return statistics.median([b[4] * b[5] for b in w])

def atr_pct(t, d):
    """compute_atr_14 as the LIVE 9:31 path sees it: bars strictly before d (today's bar is
    not in mi_daily_closes yet)."""
    w = [b for b in bars.get(t, []) if d - timedelta(days=35) <= b[0] < d and b[2] and b[3]]
    if len(w) < 10: return None, None
    trs = [max(w[i][2]-w[i][3], abs(w[i][2]-w[i-1][4]), abs(w[i][3]-w[i-1][4])) for i in range(1, len(w))]
    if not trs: return None, None
    a = sum(trs[-14:]) / len(trs[-14:])
    lc = w[-1][4]
    return a, (a/lc*100 if lc else None)

def extension_pct(t, d):
    """ep_detector: (prev_close - MIN(close) over the last ~5 trading days) / MIN(close)."""
    w = prior(t, d)
    if len(w) < 6: return None
    pc = w[-1][4]; lo = min(b[4] for b in w[-5:])
    return (pc - lo) / lo * 100 if lo else None

def prof(t, d):
    w = prior(t, d)
    pc = w[-1][4] if w else None
    pv = w[-1][5] if w else None
    _, ap = atr_pct(t, d)
    today = [b for b in bars.get(t, []) if b[0] == d]
    gap = ((today[0][1]-pc)/pc*100) if today and today[0][1] and pc else None
    return dict(prev_close=pc, prev_vol=pv, advd=adv_dollar(t, d), atr_pct=ap,
                ext=extension_pct(t, d), open_gap=gap, n_bars=len(w))

FIXTURE = [("MRNA","2026-08-19"),("MU","2026-04-08"),("UMC","2026-04-17"),("STRL","2026-04-08"),
 ("MRVL","2026-03-31"),("ASX","2026-04-08"),("SNDK","2026-04-08"),("SNOW","2026-05-07"),
 ("ALGM","2026-04-08"),("NBIS","2026-04-08"),("AMKR","2026-04-08"),("AEHR","2026-03-31"),
 ("UMC","2026-05-06"),("FLY","2026-03-12"),("BE","2026-04-08"),("USAR","2026-04-08"),
 ("QCOM","2026-04-24"),("QBTS","2026-04-08"),("AMD","2026-04-24"),("HUT","2026-04-08"),
 ("QURE","2026-05-29"),("ARM","2026-05-06"),("SMTC","2026-03-30"),("IREN","2026-04-08"),
 ("APLD","2026-04-08"),("INTC","2026-04-24")]

def fmt(v, k=""):
    if v is None: return "     n/a"
    if k == "$": return f"${v/1e6:8.2f}M"
    return f"{v:8.2f}"

print("="*118)
print("A. THE 26 LABELLED REAL EPs — liquidity/volatility profile re-derived from mi_daily_closes")
print("="*118)
print(f"{'ticker':7s}{'date':12s}{'prev_close':>11s}{'prev_vol':>12s}{'ADV$(20d med)':>16s}{'ATR%14':>9s}{'ext%5d':>9s}{'openGap%':>10s}{'bars':>6s}")
fx = []
for t, ds in FIXTURE:
    d = date.fromisoformat(ds); p = prof(t, d); p["ticker"] = t; p["date"] = ds; fx.append(p)
    print(f"{t:7s}{ds:12s}{fmt(p['prev_close'])}{(f'{p[chr(39)] if False else p['prev_vol']:12,.0f}' if p['prev_vol'] else '         n/a')}"
          f"{fmt(p['advd'],'$')}{fmt(p['atr_pct'])}{fmt(p['ext'])}{fmt(p['open_gap'])}{p['n_bars']:6d}")

def stats(key, lo=None):
    v = sorted(x[key] for x in fx if x[key] is not None)
    if not v: return "no data"
    return (f"n={len(v)}  min={v[0]:,.2f}  p10={v[max(0,int(.1*len(v)))]:,.2f}  "
            f"median={statistics.median(v):,.2f}  max={v[-1]:,.2f}")
print()
print("  ADV$      :", stats("advd"))
print("  ATR%14    :", stats("atr_pct"))
print("  prev_close:", stats("prev_close"))
print("  ext%5d    :", stats("ext"))
adv_ok = [x for x in fx if x["advd"] is not None]
print(f"  ADV$ >= $1M floor : {sum(1 for x in adv_ok if x['advd']>=1e6)}/{len(adv_ok)}")
atr_ok = [x for x in fx if x["atr_pct"] is not None]
print(f"  ATR% <= 15% cap   : {sum(1 for x in atr_ok if x['atr_pct']<=15)}/{len(atr_ok)}")

print()
print("="*118)
print("B. THE TWO SILENT DAYS — every name past the D-1 universe floors, same measures")
print("="*118)
last = rows(B1["Q2_LAST_STATE_2DAY"])
surv = [r for r in last if not r["filter_reason"].startswith("filter:universe_")]
adv_med = statistics.median([x["advd"] for x in fx if x["advd"] is not None])
for d in ("2026-08-24", "2026-08-25"):
    print(f"\n--- {d} ---")
    print(f"{'ticker':7s}{'gap%':>8s}{'prev_close':>11s}{'ADV$(20dmed)':>15s}{'ATR%14':>9s}{'ext%5d':>9s}{'x fixture-median ADV$':>23s}  kill")
    dd = date.fromisoformat(d)
    for r in sorted([x for x in surv if x["scan_date"] == d], key=lambda x: -(f(x["gap_pct"]) or 0)):
        t = r["ticker"]; p = prof(t, dd)
        ratio = (p["advd"]/adv_med) if p["advd"] else None
        print(f"{t:7s}{fmt(f(r['gap_pct']))}{fmt(p['prev_close'])}{fmt(p['advd'],'$')}{fmt(p['atr_pct'])}{fmt(p['ext'])}"
              f"{(f'{ratio:22.3f}' if ratio is not None else '                   n/a')}  {r['filter_reason'][:60]}")

print()
print("="*118)
print("C. UPSTREAM — names declined in real time that never reached the scan log")
print("="*118)
UP = {"2026-08-24": ["RUM","USDE","NXTT","CLF","SUJA","WBTN","NCTY","PHOS"],
      "2026-08-25": ["SPAI","HMN","ABCL","PSQH","CRML","DBGI","PTHS","FISI","CLRO"]}
for d, ts in UP.items():
    print(f"\n--- {d} ---")
    print(f"{'ticker':7s}{'prev_close':>11s}{'ADV$(20dmed)':>15s}{'ATR%14':>9s}{'ext%5d':>9s}  gates it would face")
    dd = date.fromisoformat(d)
    for t in ts:
        p = prof(t, dd)
        why = []
        if p["advd"] is None: why.append("ADV: no data (<10 bars) -> filter:adv_no_data")
        elif p["advd"] < 1e6: why.append(f"ADV$ ${p['advd']:,.0f} < $1,000,000 FAIL")
        if p["atr_pct"] is not None and p["atr_pct"] > 15: why.append(f"ATR {p['atr_pct']:.1f}% > 15% FAIL")
        if p["ext"] is not None and p["ext"] >= 75: why.append(f"extension {p['ext']:.0f}% >= 75% FAIL")
        if not why: why.append("clears every mechanical gate we can re-derive (mcap not derivable here)")
        print(f"{t:7s}{fmt(p['prev_close'])}{fmt(p['advd'],'$')}{fmt(p['atr_pct'])}{fmt(p['ext'])}  " + " ; ".join(why))

# ── D. MARGINS + the one day of realised D0 behaviour we already have ────────────────────────
print()
print("="*118)
print("D. MARGIN OF EACH REJECTION (how close was it?) + 2026-08-24 D0 outcome (bar is in)")
print("="*118)
GATE = {  # gate -> (threshold, direction, extractor of the measured value from the reason string)
    "adv":  (1_000_000.0, "below"),
    "atr":  (15.0, "above"),
    "mcap": (500_000_000.0, "below"),
    "score":(None, "below"),
}
import re as _re
def margin(reason):
    m = _re.search(r"adv_too_low: \$([\d,]+)", reason)
    if m:
        v = float(m.group(1).replace(",", "")); return f"ADV$ {v:,.0f} vs $1,000,000 floor", (1e6-v)/1e6*100
    m = _re.search(r"atr_too_high: ([\d.]+)% > ([\d.]+)%", reason)
    if m:
        v, thr = float(m.group(1)), float(m.group(2)); return f"ATR {v:.1f}% vs {thr:.0f}% cap", (v-thr)/thr*100
    m = _re.search(r"mcap_too_small: \$(\d+)M < \$(\d+)M", reason)
    if m:
        v, thr = float(m.group(1)), float(m.group(2)); return f"mcap ${v:.0f}M vs ${thr:.0f}M floor", (thr-v)/thr*100
    m = _re.search(r"score (-?[\d.]+) < bar (\d+)", reason)
    if m:
        v, thr = float(m.group(1)), float(m.group(2)); return f"score {v:.0f} vs bar {thr:.0f}", (thr-v)/thr*100
    m = _re.search(r"pre-mkt volume ([\d,]+) < ([\d,]+)", reason)
    if m:
        v, thr = float(m.group(1).replace(",","")), float(m.group(2).replace(",",""))
        return f"pre-mkt {v:,.0f} sh vs {thr:,.0f} floor", (thr-v)/thr*100
    m = _re.search(r"rvol=([\d.]+)x .* < ([\d.]+)x", reason)
    if m:
        v, thr = float(m.group(1)), float(m.group(2)); return f"rvol {v:.2f}x vs {thr:.1f}x floor", (thr-v)/thr*100
    m = _re.search(r"already up (\d+)%", reason)
    if m:
        v = float(m.group(1)); return f"extension {v:.0f}% vs 75% cap", (v-75)/75*100
    if "cooldown" in reason: return "60-day EP cooldown (binary)", None
    if "M&A" in reason: return "M&A filter (binary)", None
    if "routine catalyst" in reason: return "routine grade + gap < 12% (binary)", None
    return reason[:40], None

barmap = {}
for blk in (B1["Q9_DAILY_CLOSES"], B2["U1_UPSTREAM_CLOSES"]):
    for r in rows(blk):
        barmap.setdefault(r["ticker"], {})[r["trade_date"]] = r

for d in ("2026-08-24", "2026-08-25"):
    print(f"\n--- {d} ---")
    print(f"{'ticker':7s}{'margin description':38s}{'miss by':>10s}   D0 (open/high/close vs prior close)")
    for r in sorted([x for x in surv if x["scan_date"] == d], key=lambda x: -(f(x["gap_pct"]) or 0)):
        t = r["ticker"]; desc, pct = margin(r["filter_reason"])
        b = barmap.get(t, {}).get(d)
        if b:
            dd = date.fromisoformat(d); w = prior(t, dd); pc = w[-1][4] if w else None
            o,h,c = f(b["open_price"]), f(b["high_price"]), f(b["close"])
            d0 = (f"O {(o-pc)/pc*100:+6.1f}%  H {(h-pc)/pc*100:+6.1f}%  C {(c-pc)/pc*100:+6.1f}%") if pc else "n/a"
        else:
            d0 = "bar not in yet"
        print(f"{t:7s}{desc:38s}{(f'{pct:9.1f}%' if pct is not None else '        —'):>10s}   {d0}")
