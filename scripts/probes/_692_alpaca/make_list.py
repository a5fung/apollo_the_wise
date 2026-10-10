"""$0, offline: turn paid_check_2026-10-10.jsonl into the list for him (paid_check_list_2026-10-10.md).

"What the filter would do" is derived with the PRODUCTION functions (`ma_filter.deal_nominates` /
`deal_pins_price` / `_headline_acts`), never by hand:
  BLOCK   = the headline acts: target of a signed/proposed deal on price-fixing terms (the 09:35 price
            may still release it), or a signed shell
  RELEASE = answered, a deal is named, but it does not act (buyer, speculation, all-stock, completed ...)
  NO DEAL = role 'none'
  UNANSWERED = no usable answer (not folded into the others)
Labels are HIS words only (docs/analysis/mna_filter_operator_labels_2026-10-01.md, the 10-03 sign-off,
and the label field of the 10-02 replay). Nothing here is the agent's classification.
Run: python scripts/probes/_692_alpaca/make_list.py
"""
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from agents.market_intelligence import ma_filter as mf  # noqa: E402

rows = [json.loads(l) for l in open(HERE / "paid_check_2026-10-10.jsonl")]
replay = [json.loads(l) for l in open(HERE / "input_replay_2026-10-02.jsonl")]

# his labels, by ticker (the date is his label's own date, shown in the list)
LAB: dict[str, list[str]] = collections.defaultdict(list)
for r in replay:
    if r.get("label"):
        txt = r["label"].replace("operator-confirmed", "operator").replace("operator ", "")
        s = f"block {r['date'][5:]}: {txt}"
        if s not in LAB[r["ticker"]]:
            LAB[r["ticker"]].append(s)
SIGNOFF = {   # 2026-10-03 sign-off on the 151-stock-day replay
    "DSGN": "2026-05-18 not a buyout, release", "THR": "2026-05-22 not a buyout, release",
    "PD": "2026-05-29 not a buyout, release", "HZO": "2026-08-10 real buyout, keep blocked",
    "RNW": "2026-08-11 real buyout, keep blocked",
}
for t, s in SIGNOFF.items():
    LAB[t].append(f"10-03 sign-off, {s}")
# 10-01 table: role in his words (FWDI bidder; CHYM, JBS, SWKS buyers; GPRK, IOVA, RGTI no deal; VKTX speculation; WAY exploring a sale; CSR all-stock)
ROLE_WORDS = {"FWDI": "bidder/buyer", "CHYM": "buyer", "JBS": "buyer", "SWKS": "buyer", "GPRK": "no deal",
              "IOVA": "no deal", "RGTI": "no deal", "VKTX": "speculation", "WAY": "exploring a sale",
              "CSR": "all-stock merger", "ACVA": "REAL target", "SUNE": "REAL target", "CLRO": "REAL target"}
BUYERS = ("FWDI", "CHYM", "JBS", "SWKS")      # his 10-01 buyers
REAL = ("ACVA", "SUNE", "CLRO", "HZO", "RNW", "UTZ", "DV", "SYNA")   # names he called real buyouts / kept blocked


def verdict(r):
    a = r.get("answer")
    if a is None:
        return "UNANSWERED"
    ans = mf.DealAnswer(a["role"], a["status"], a["consideration"], a.get("counterparty") or "", a.get("note") or "")
    if mf._headline_acts(ans):
        return "BLOCK"
    return "NO DEAL" if ans.role == "none" else "RELEASE"


for r in rows:
    r["verdict"] = verdict(r)
rows.sort(key=lambda r: (r["ticker"], r["published_utc"]))
cnt = collections.Counter(r["verdict"] for r in rows)
buyer_rows = [r for r in rows if r["ticker"] in BUYERS]
buyer_blocked = [r for r in buyer_rows if r["verdict"] == "BLOCK"]
cost = sum((r.get("raw") or {}).get("usage", {}).get("in") or 0 for r in rows), \
    sum((r.get("raw") or {}).get("usage", {}).get("out") or 0 for r in rows)

out = ["# #692 paid check — the 88 Benzinga-via-Alpaca headlines, asked once (2026-10-10)", "",
       f"Model `{rows[0].get('model', 'claude-sonnet-5-5')}`, production prompt and tool (`ma_filter.ask_deal_question`), "
       "no table written. Raw answers: `paid_check_2026-10-10.jsonl`.", "",
       "- Set = every headline the Alpaca feed adds that the scan would ask about: the 47 the ORIGINAL keywords nominate "
       "plus 41 the seven deal-wire phrases add, over the 151 replayed ticker-days (unique ticker + headline).",
       f"- Result: **{cnt['BLOCK']} BLOCK as target**, {cnt['RELEASE']} RELEASE (a deal, not the target-on-price-fixing-terms), "
       f"{cnt['NO DEAL']} NO DEAL, {cnt['UNANSWERED']} unanswered.",
       f"- Names he labelled a buyer (FWDI, CHYM, SWKS; JBS has no headline in the set): {len(buyer_rows)} headlines in the set, "
       f"**{len(buyer_blocked)} answered as a blocking target**"
       + (": " + ", ".join(f"{r['ticker']} '{r['title'][:60]}'" for r in buyer_blocked) if buyer_blocked else "") + ".",
       "- Names he called real buyouts (" + ", ".join(REAL) + "): "
       + ", ".join(f"{t} {'BLOCK' if any(r['verdict']=='BLOCK' for r in rows if r['ticker']==t) else 'NOT blocked'}"
                   for t in REAL) + " (any headline in the set).",
       "- BLOCK is the pre-market verdict; at 09:35 the open-window price can still RELEASE a name that moves (ruling 2026-10-03).",
       "- His labels shown are his own words on the dates given; a label is a label of that day's block, not of every headline.",
       "", "| Ticker | Day | Headline | Feed | Model answer | Filter | His label |", "|---|---|---|---|---|---|---|"]
for r in rows:
    a = r.get("answer")
    ans = "unanswered (" + r["how"] + ")" if a is None else \
        f"{a['role']} / {a['status']} / {a['consideration']}" + (f" ({a['counterparty']})" if a.get("counterparty") else "")
    lab = "; ".join(LAB.get(r["ticker"], [])) or ""
    title = r["title"].replace("|", "/")[:120]
    out.append(f"| {r['ticker']} | {r['published_utc'][:10]} | {title} | Alpaca (Benzinga), "
               f"{'summary' if r['match_path'] != 'title' else 'title'} match '{r['kw']}' | {ans} | **{r['verdict']}** | {lab} |")
open(HERE / "paid_check_list_2026-10-10.md", "w").write("\n".join(out) + "\n")
print(dict(cnt), "buyer headlines", len(buyer_rows), "buyer blocked", [(r['ticker'], r['title'][:50]) for r in buyer_blocked])
print("tokens in/out", cost)
