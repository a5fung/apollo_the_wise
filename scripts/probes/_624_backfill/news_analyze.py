"""#624 news step 1 — local analysis of the captured pulls (no network, no cost).
Inputs : per_signal_P.tsv, news_raw.jsonl (Polygon), news_alpaca_raw.jsonl (Alpaca/Benzinga, if present), ref_*.jsonl (names).
Outputs: news_articles.jsonl (the Polygon deliverable, one line per signal, each article flagged primary_subject),
         printed tables (captured to news_analysis_out.txt by the caller)."""
import glob
import json
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict

import pandas as pd

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.collector import is_primary_subject_news  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)  # noqa: E731

sig = pd.read_csv(P("per_signal_P.tsv"), sep="|", keep_default_na=False, na_values=[""])  # ticker "NA" (Nano Labs) is real; default NA-parsing turned it into NaN
OOS_END = "2026-06-05"
sig["year"] = sig.d.str[:4]
sig["oos"] = sig.d <= OOS_END
sig["walked"] = sig.outcome.eq("settled")

names = {}
for f in glob.glob(P("ref_*.jsonl")):
    for l in open(f):
        try:
            r = json.loads(l)
            n = (r.get("r") or {}).get("name")
            if n:
                names[(r["t"], r["d"])] = n
                names.setdefault((r["t"], None), n)
        except Exception:  # noqa: BLE001
            pass


def nm(t, d):
    return names.get((t, d)) or names.get((t, None)) or ""


def load(path):
    out = {}
    if os.path.exists(path):
        for l in open(path):
            r = json.loads(l)
            out[(r["ticker"], r["D"])] = r
    return out


def load_merged(main, fix):
    """The first list was written by a default pandas read, which turned ticker "NA" into NaN -> "nan"; those 2 rows were
    re-pulled as `fix` and replace the bogus `nan` keys."""
    d = {k: v for k, v in load(P(main)).items() if k[0] != "nan"}
    d.update(load(P(fix)))
    return d


poly = load_merged("news_raw.jsonl", "news_raw_fix.jsonl")
alp = load_merged("news_alpaca_raw.jsonl", "news_alpaca_raw_fix.jsonl")


def prim(a, tk, name):
    return is_primary_subject_news({"title": a.get("title"), "symbols": a.get("tickers") or []}, tk, name)


def annotate(rec):
    tk, d = rec["ticker"], rec["D"]
    name = nm(tk, d)
    for a in rec["articles"]:
        a["primary_subject"] = bool(prim(a, tk, name))
        a["chars"] = len(a.get("title") or "") + len(a.get("description") or "")
    return rec


for r in poly.values():
    annotate(r)
for r in alp.values():
    annotate(r)

# ---- deliverable: news_articles.jsonl (Polygon; backfill signals first, then the 19 live rows)
with open(P("news_articles.jsonl"), "w") as f:
    for r in poly.values():
        if r["set"] == "alert":
            continue
        row = {"ticker": r["ticker"], "D": r["D"], "tick": r["tick"], "set": r["set"],
               "window_utc": r["window_utc"],
               "articles": [{k: a.get(k) for k in ("published_utc", "publisher", "title", "description",
                                                    "article_url", "primary_subject", "n_tickers")}
                            for a in r["articles"]],
               "earlier_7d_n": len(r["earlier_7d"]),
               "earlier_7d_titles": [(e["published_utc"][:10], e["publisher"], e["title"]) for e in r["earlier_7d"]]}
        f.write(json.dumps(row) + "\n")

bf = sig.copy()
bf["key"] = list(zip(bf.ticker, bf.d))
bf["n_raw"] = [len(poly[k]["articles"]) if k in poly else None for k in bf.key]
bf["n_prim"] = [sum(a["primary_subject"] for a in poly[k]["articles"]) if k in poly else None for k in bf.key]
bf["n_early"] = [len(poly[k]["earlier_7d"]) if k in poly else None for k in bf.key]
bf["n_alp"] = [len(alp[k]["articles"]) if k in alp else None for k in bf.key]
bf["n_alp_prim"] = [sum(a["primary_subject"] for a in alp[k]["articles"]) if k in alp else None for k in bf.key]
print("signals", len(bf), "missing polygon rows", bf.n_raw.isna().sum(), "alpaca rows", bf.n_alp.notna().sum())


def cov(df, col):
    n = len(df)
    k = int((df[col] >= 1).sum())
    return f"{k}/{n} = {100 * k / n:.1f}%" if n else "n/a"


def block(title, df):
    print(f"\n== {title} (n={len(df)})")
    print(f"   Polygon raw >=1 article in window      : {cov(df, 'n_raw')}")
    print(f"   Polygon primary-subject >=1            : {cov(df, 'n_prim')}")
    print(f"   Polygon any article in prior 7d too    : {int(((df.n_raw + df.n_early) >= 1).sum())}/{len(df)}")
    if df.n_alp.notna().any():
        print(f"   Alpaca/Benzinga raw >=1                : {cov(df, 'n_alp')}")
        print(f"   Alpaca/Benzinga primary-subject >=1    : {cov(df, 'n_alp_prim')}")
        both = int(((df.n_prim >= 1) | (df.n_alp_prim >= 1)).sum())
        print(f"   either source primary-subject >=1      : {both}/{len(df)}")


block("ALL 768 backfill signals", bf)
block("walked (settled) trades, whole window", bf[bf.walked])
block("walked OOS 2024-01-02..2026-06-05 (the 279)", bf[bf.walked & bf.oos])
print("\n-- by year (all signals)")
for y, g in bf.groupby("year"):
    block(f"year {y}", g)
print("\n-- by year (walked)")
for y, g in bf[bf.walked].groupby("year"):
    block(f"walked {y}", g)

# ---- publisher mix by year (Polygon, window articles; and earlier-7d too)
print("\n== Polygon publisher mix by year (articles in window; top 8 each)")
pm = defaultdict(Counter)
for (tk, d), r in poly.items():
    if r["set"] != "bf":
        continue
    for a in r["articles"]:
        pm[d[:4]][a["publisher"]] += 1
for y in sorted(pm):
    print(y, sum(pm[y].values()), pm[y].most_common(8))
print("\n== Polygon publisher mix of PRIMARY-subject articles by year")
pm2 = defaultdict(Counter)
for (tk, d), r in poly.items():
    if r["set"] != "bf":
        continue
    for a in r["articles"]:
        if a["primary_subject"]:
            pm2[d[:4]][a["publisher"]] += 1
for y in sorted(pm2):
    print(y, sum(pm2[y].values()), pm2[y].most_common(8))
if alp:
    print("\n== Alpaca publisher mix by year")
    am = defaultdict(Counter)
    for (tk, d), r in alp.items():
        if r["set"] != "bf":
            continue
        for a in r["articles"]:
            am[d[:4]][a["publisher"]] += 1
    for y in sorted(am):
        print(y, sum(am[y].values()), am[y].most_common(6))

# ---- input size per signal (title+description chars)
print("\n== input size per signal, chars of title+description (Polygon)")
for lab, flt in (("raw", lambda a: True), ("primary-subject", lambda a: a["primary_subject"])):
    per = []
    for (tk, d), r in poly.items():
        if r["set"] != "bf":
            continue
        per.append(sum(a["chars"] for a in r["articles"] if flt(a)))
    nz = [x for x in per if x > 0]
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))] if xs else 0  # noqa: E731
    print(f"{lab}: signals={len(per)} total={sum(per):,} chars mean/signal={sum(per) / len(per):.0f} "
          f"median(all)={st.median(per):.0f} p90={q(per, .9)} max={max(per)} | with>=1 article n={len(nz)} "
          f"median={st.median(nz) if nz else 0:.0f} p90={q(nz, .9)}")
if alp:
    per = []
    for (tk, d), r in alp.items():
        if r["set"] != "bf":
            continue
        per.append(sum(a["chars"] for a in r["articles"] if a["primary_subject"]))
    nz = [x for x in per if x > 0]
    print(f"Alpaca primary-subject: signals={len(per)} total={sum(per):,} chars mean/signal={sum(per) / len(per):.0f} "
          f"median(all)={st.median(per):.0f} p90={sorted(per)[int(.9 * len(per))]} | with>=1: n={len(nz)} "
          f"median={st.median(nz) if nz else 0:.0f}")

# ---- tail trades
print("\n== tail trades (R >= 3), walked")
tails = bf[(bf.R >= 3)].sort_values("d")
for r in tails.itertuples():
    tag = "OOS" if r.oos else "in-sample (after 2026-06-05)"
    pr = poly[r.key]
    print(f"\n{r.ticker} {r.d} tick {r.tick} R={r.R:.2f} [{tag}] name={nm(r.ticker, r.d)!r}  Polygon raw={r.n_raw} prim={r.n_prim} earlier7d={r.n_early}"
          f" | Alpaca raw={r.n_alp} prim={r.n_alp_prim}")
    for a in pr["articles"]:
        print(f"   POLY {a['published_utc'][:16]}Z {a['publisher'][:22]:22} prim={int(a['primary_subject'])} tk={a['n_tickers']} | {a['title'][:140]}")
    for e in pr["earlier_7d"]:
        print(f"   POLY(prior7d) {e['published_utc'][:16]}Z {e['publisher'][:22]:22} | {e['title'][:120]}")
    if r.key in alp:
        for a in alp[r.key]["articles"]:
            print(f"   ALP  {a['published_utc'][:16]}Z {a['publisher'][:10]:10} prim={int(a['primary_subject'])} tk={a['n_tickers']} | {a['title'][:140]}")


# ================= added: time structure, Alpaca-vs-Polygon match, live lane rows =================
def toks(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower())) - {"the", "a", "an", "of", "to", "and", "in", "for", "on", "with",
                                                               "as", "at", "by", "from", "inc"}


def same(t1, t2):
    a, b = toks(t1), toks(t2)
    return bool(a and b) and len(a & b) >= 3 and len(a & b) / min(len(a), len(b)) >= 0.7


bf["half"] = bf.d.str[:4] + bf.d.str[5:7].map(lambda m: "H1" if int(m) <= 6 else "H2")
print("\n== by half-year: Polygon primary>=1 (and Alpaca primary>=1 when pulled), all signals")
for h, g in bf.groupby("half"):
    line = f"{h}: n={len(g):3d} polygon raw {int((g.n_raw >= 1).sum()):3d} ({100 * (g.n_raw >= 1).mean():4.1f}%) prim {int((g.n_prim >= 1).sum()):3d} ({100 * (g.n_prim >= 1).mean():4.1f}%)"
    if g.n_alp.notna().any():
        line += f" | alpaca raw {int((g.n_alp >= 1).sum()):3d} ({100 * (g.n_alp >= 1).mean():4.1f}%) prim {int((g.n_alp_prim >= 1).sum()):3d} ({100 * (g.n_alp_prim >= 1).mean():4.1f}%)"
    print(line)
g = bf[(bf.d >= "2026-01-01") & (bf.d < "2026-06-19")]
g2 = bf[bf.d >= "2026-06-19"]
for lab, gg in (("2026 before Benzinga left Polygon (<2026-06-19)", g), ("2026-06-19 on (Benzinga absent from Polygon)", g2)):
    print(f"{lab}: n={len(gg)} polygon prim>=1 {int((gg.n_prim >= 1).sum())} ({100 * (gg.n_prim >= 1).mean():.1f}%)"
          + (f" | alpaca prim>=1 {int((gg.n_alp_prim >= 1).sum())} ({100 * (gg.n_alp_prim >= 1).mean():.1f}%)" if gg.n_alp.notna().any() else ""))

if alp:
    print("\n== Alpaca/Benzinga primary-subject articles also present in Polygon (title match), by year")
    tot = Counter(); hit = Counter()
    for (tk, d), r in alp.items():
        if r["set"] != "bf" or (tk, d) not in poly:
            continue
        pt = [a["title"] for a in poly[(tk, d)]["articles"]] + [e["title"] for e in poly[(tk, d)]["earlier_7d"]]
        for a in r["articles"]:
            if not a["primary_subject"]:
                continue
            tot[d[:4]] += 1
            if any(same(a["title"], t) for t in pt):
                hit[d[:4]] += 1
    for y in sorted(tot):
        print(f"{y}: {hit[y]}/{tot[y]} = {100 * hit[y] / tot[y]:.0f}% of Alpaca primary articles also in Polygon (window+prior7d)")
    print("\n== both-source view: signals with Alpaca primary>=1 but Polygon primary==0")
    only_a = bf[(bf.n_alp_prim >= 1) & (bf.n_prim == 0)]
    only_p = bf[(bf.n_alp_prim == 0) & (bf.n_prim >= 1)]
    both = bf[(bf.n_alp_prim >= 1) & (bf.n_prim >= 1)]
    print(f"alpaca-only {len(only_a)} | polygon-only {len(only_p)} | both {len(both)} | neither {int(((bf.n_alp_prim == 0) & (bf.n_prim == 0)).sum())}")

print("\n== the 19 live lane rows (2026-09-09..10-05): Polygon vs Alpaca/Benzinga, same window")
for (tk, d), r in poly.items():
    if r["set"] != "live":
        continue
    a = alp.get((tk, d))
    print(f"\n{tk} {d} {r['tick']} ET | Polygon raw={len(r['articles'])} prim={sum(x['primary_subject'] for x in r['articles'])} prior7d={len(r['earlier_7d'])}"
          + (f" | Alpaca raw={len(a['articles'])} prim={sum(x['primary_subject'] for x in a['articles'])}" if a else ""))
    for x in r["articles"]:
        print(f"   POLY {x['published_utc'][5:16]}Z {x['publisher'][:14]:14} prim={int(x['primary_subject'])} | {x['title'][:130]}")
    if a:
        for x in a["articles"]:
            print(f"   ALP  {x['published_utc'][5:16]}Z {x['publisher'][:8]:8} prim={int(x['primary_subject'])} tk={x['n_tickers']} | {x['title'][:130]}")

# ---- deliverable 2: Alpaca/Benzinga articles per signal (same windows), merged with the NA fix
with open(P("news_alpaca_articles.jsonl"), "w") as f:
    for r in alp.values():
        f.write(json.dumps({"ticker": r["ticker"], "D": r["D"], "tick": r["tick"], "set": r["set"], "window_utc": r["window_utc"],
                            "articles": [{k: a.get(k) for k in ("published_utc", "publisher", "title", "description", "article_url",
                                                                 "primary_subject", "n_tickers")} for a in r["articles"]]}) + "\n")
