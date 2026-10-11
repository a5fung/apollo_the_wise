"""#692 Alpaca/Benzinga source — the $0 offline replay over the captured raw pull (news_pull.jsonl).

No model call, no network. Candidate selection is the REAL `ma_filter._candidate_articles` /
`_merge_headline_sources` / `_alpaca_to_scan_items`; the model's answer step is NOT replayed (that
costs money) except where the SAME headline already has a stored answer in the paid 10-02 replay
(input_replay_2026-10-02.jsonl `headline_asked`) — those are reused.

Questions answered (population stated in every block):
  A. COVERAGE  — on the ticker-days up to 06-17 (Polygon still carried Benzinga), every candidate
     article Polygon gave from Benzinga: does the Alpaca feed give the same headline as a candidate?
  B. ADDITIONS — on ticker-days 06-18 .. 10-02 (Polygon carries no Benzinga), which candidates does
     Alpaca ADD to what Polygon alone gives, and which of those carry a stored answer?
  C. DISPLACEMENT — the scan asks the 3 newest candidates. Does an added Alpaca candidate push a
     Polygon candidate that was asked (and acted) out of the top 3?
  D. WEEKLY — the five buyout names the 10-05 board rejected: keyword candidates by feed, by week.
Run:  python scripts/probes/_692_alpaca/analyze.py > scripts/probes/_692_alpaca/analysis_out.txt
"""
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence import ma_filter as mf  # noqa: E402

CUT_BENZINGA = "2026-06-17"          # Polygon last carried Benzinga on/before this day (10-06 check)

pull = [json.loads(l) for l in open(HERE / "news_pull.jsonl")]
replay = [json.loads(l) for l in open(HERE / "input_replay_2026-10-02.jsonl")]
stored = {}          # (ticker, date) -> replay row
for r in replay:
    if r.get("kind") == "ticker_day":
        stored[(r["ticker"], r["date"])] = r


def upto(items, day):
    return [i for i in items if (i.get("published_utc") or "") <= f"{day}T23:59:59Z"]


def cands(ticker, items, company=None):
    return mf._candidate_articles(ticker, items, company_name=company)


def acts(ans):
    a = mf.DealAnswer(ans["deal_role"], ans["deal_status"], ans["deal_consideration"])
    return mf._headline_acts(a)


cells = [p for p in pull if p["kind"] == "cell"]
print(f"RAW PULL: {len(cells)} ticker-day cells, {sum(1 for p in pull if p['kind']=='weekly')} weekly cells")
print(f"  Polygon items {sum(len(c['polygon']) for c in cells)}, Alpaca items {sum(len(c['alpaca']) for c in cells)}\n")

# ── A. coverage ─────────────────────────────────────────────────────────────────────────────────
print("=" * 100)
print(f"A. COVERAGE — ticker-days on/before {CUT_BENZINGA}: Benzinga candidates Polygon gave vs Alpaca's")
bz_total = bz_found = 0
miss = []
poly_b_cells = 0
for c in cells:
    if c["day"] > CUT_BENZINGA:
        continue
    t, day = c["ticker"], c["day"]
    poly = upto(c["polygon"], day)
    alp_raw = upto(mf._alpaca_to_scan_items(c["alpaca"]), day)
    pb = [x for x in cands(t, [i for i in poly if (i.get("publisher") or "").lower() == "benzinga"])]
    if pb:
        poly_b_cells += 1
    a_titles = {mf._norm_title(x[0]["title"]) for x in cands(t, alp_raw, company=None)}
    a_raw_titles = {mf._norm_title(i["title"]) for i in alp_raw}
    for item, mp, kw, _r in pb:
        bz_total += 1
        k = mf._norm_title(item["title"])
        if k in a_titles:
            bz_found += 1
        else:
            miss.append((t, day, item["title"][:110], mp, kw,
                         "in Alpaca raw but not a candidate" if k in a_raw_titles else "not in Alpaca at all"))
print(f"  ticker-days in this slice: {sum(1 for c in cells if c['day'] <= CUT_BENZINGA)}; "
      f"with >=1 Benzinga candidate in Polygon: {poly_b_cells}")
print(f"  Benzinga candidate articles (Polygon, publisher=Benzinga): {bz_total}; "
      f"also a candidate from Alpaca (same headline): {bz_found}")
for m in miss:
    print("   MISS", m)

# ── B. additions ────────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 100)
print(f"B. ADDITIONS — ticker-days {CUT_BENZINGA}+1 .. 10-02 (Polygon carries no Benzinga)")
add_rows = []
n_days = n_days_with_add = 0
poly_only_n = alp_only_n = 0
for c in cells:
    if c["day"] <= CUT_BENZINGA:
        continue
    t, day = c["ticker"], c["day"]
    n_days += 1
    poly = upto(c["polygon"], day)
    alp = upto(mf._alpaca_to_scan_items(c["alpaca"]), day)
    merged = mf._merge_headline_sources(poly, alp)
    cm = cands(t, merged, company=None)
    cp = cands(t, poly)
    poly_only_n += len(cp)
    added = [x for x in cm if x[0].get("news_source") == "alpaca"]
    alp_only_n += len(added)
    if added:
        n_days_with_add += 1
    st = stored.get((t, day)) or {}
    stored_ans = {mf._norm_title(a["title"]): a.get("answer") for a in (st.get("headline_asked") or [])}
    for item, mp, kw, _r in added:
        sa = stored_ans.get(mf._norm_title(item["title"]))
        add_rows.append({"ticker": t, "day": day, "title": item["title"][:120], "match_path": mp,
                         "kw": kw, "published": item["published_utc"], "label": st.get("label"),
                         "old_decision": st.get("old_decision"), "new_decision": st.get("new_decision"),
                         "stored_answer": sa})
print(f"  ticker-days: {n_days}; Polygon-only candidates: {poly_only_n}; "
      f"Alpaca-ADDED candidates (headline not already in Polygon): {alp_only_n}; "
      f"ticker-days that gain >=1: {n_days_with_add}")
print("  (the model question on each ADDED candidate was NOT replayed — no stored answer unless noted)")
for r in add_rows:
    lab = (r["label"] or "")[:34]
    print(f"   {r['ticker']:6} {r['day']} [{r['match_path'][:12]:12}] kw={r['kw']!r:20} "
          f"{r['title'][:90]!r} label={lab!r}")
json.dump(add_rows, open(HERE / "alpaca_added_candidates.json", "w"), indent=1, default=str)

# ── C. displacement (top-3 cap) ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 100)
print("C. DISPLACEMENT — does an added Alpaca candidate push an asked-and-acting Polygon candidate out of the 3 newest?")
disp = []
shared_displaced = []
not_reproduced = 0
for c in cells:
    t, day = c["ticker"], c["day"]
    st = stored.get((t, day)) or {}
    asked = st.get("headline_asked") or []
    acting = {mf._norm_title(a["title"]) for a in asked if a.get("answer") and acts(a["answer"])}
    if not acting:
        continue
    poly = upto(c["polygon"], day)
    alp = upto(mf._alpaca_to_scan_items(c["alpaca"]), day)
    merged = mf._merge_headline_sources(poly, alp)
    cm = cands(t, merged)
    n = mf._HEADLINE_MAX_ARTICLES
    # only stored acting headlines this pull's Polygon-only candidates still contain (the 10-02 replay
    # used the scheduler's 21-day lookback for some callers; a title outside this pull's 14-day window is
    # not a displacement, it is not in the population)
    poly_titles = {mf._norm_title(x[0]["title"]) for x in cands(t, poly)}
    not_reproduced += len(acting - poly_titles)
    acting = acting & poly_titles
    if not acting:
        continue
    shared_cap = {mf._norm_title(x[0]["title"]) for x in cm[:n]}          # the first design (one shared cap)
    per_feed = {mf._norm_title(x[0]["title"]) for feed in (False, True)   # the shipped design (cap per feed)
                for x in [y for y in cm if (y[0].get("news_source") == "alpaca") is feed][:n]}
    lost_shared = acting - shared_cap
    if lost_shared:
        shared_displaced.append((t, day))
    lost = acting - per_feed
    disp.append((t, day, len(acting), len(lost)))
    if lost:
        print("   DISPLACED", t, day, sorted(lost))
print(f"  stored acting headlines not in this pull's Polygon candidates (excluded): {not_reproduced}")
print(f"  ticker-days where the stored Polygon-era answers include an ACTING headline still in the Polygon pull: {len(disp)}; "
      f"pushed out under ONE shared 3-cap: {len(shared_displaced)} {shared_displaced}; "
      f"pushed out under the SHIPPED per-feed cap: {sum(1 for d in disp if d[3])}")

# ── D. weekly: the five names ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 100)
print("D. WEEKLY 06-19 .. 10-09 — keyword candidates by feed for ARX, BWIN, CBZ, DV, ITGR")
seen = collections.defaultdict(dict)
for p in pull:
    if p["kind"] != "weekly":
        continue
    t = p["ticker"]
    for it in p["polygon"]:
        if mf.matches_mna_keywords(it.get("title")):
            seen[t].setdefault(mf._norm_title(it["title"]), {"title": it["title"], "pub": it["published_utc"],
                                                              "feeds": set(), "publisher": it.get("publisher")})["feeds"].add("polygon")
    for it in mf._alpaca_to_scan_items(p["alpaca"]):
        if mf.matches_mna_keywords(it.get("title")):
            seen[t].setdefault(mf._norm_title(it["title"]), {"title": it["title"], "pub": it["published_utc"],
                                                              "feeds": set(), "publisher": it.get("publisher")})["feeds"].add("alpaca")
for t in ("ARX", "BWIN", "CBZ", "DV", "ITGR"):
    rows = sorted(seen[t].values(), key=lambda r: r["pub"])
    print(f"  {t}: {len(rows)} title-keyword headlines in 06-19..10-09")
    for r in rows:
        print(f"     {r['pub'][:10]} feeds={'+'.join(sorted(r['feeds'])):14} {r['title'][:100]!r}")
