#!/usr/bin/env python3
"""Reconcile step 3: per-trade agreement between the builder's class (build/his_5R_vs_v1.tsv) and the blind reader's
class (blind/blind_classes.tsv), the reconciled class, and a one-line resolution for each disagreement. The
resolutions were checked against the frozen replay rows (out/trades.tsv.gz: adm_guard, why_cap, reason, exit dates)
and the store-A daily bars (his-day high vs v1's level, his-day volume); see 01_run.log / his205_nights.tsv.
Reconciled rule = the blind rule (judged on HIS buy day; a guard-admitted v1 buy of the same stock from 10 sessions
before his buy to his replayed sell counts as bought earlier/later). Writes agreement.tsv."""
import pandas as pd
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/qm_vs_v1_1101"
b = pd.read_csv(f"{HERE}/build/his_5R_vs_v1.tsv", sep="\t", comment="#")
z = pd.read_csv(f"{HERE}/blind/blind_classes.tsv", sep="\t")
assert len(b) == len(z) == 28
b["k"] = b.his_E + "|" + b.name_on_panel
z["k"] = z.his_entry_date + "|" + z.ticker
m = b.merge(z, on="k", how="outer", indicator=True)
assert (m._merge == "both").all(), m[m._merge != "both"][["k"]]
prim = lambda s: s.split(" (")[0].strip()
m["builder"] = m.category.map(prim); m["blind"] = m["class"].map(prim)
m["agree"] = (m.builder == m.blind).astype(int)
RES = {
 "APT|2020-02-21": "Off the list the night before (strength 96.4); his day's high $5.77 never reached v1's level $5.98; the 3 listed nights were other days, each refused as stop too wide -> NOT LISTED (strength)",
 "PDD|2020-05-08": "v1's 06-02 buy came 16 sessions later, after his replayed sell (05-28), at $69.69 vs his $52.18: a new base, not his trade -> NOT LISTED (strength)",
 "SHOP|2020-06-15": "The builder's 05-22 buy was refused by the one-position-per-stock rule: v1 already held SHOP 05-05..05-27 (+0.2R), sold 13 sessions before his buy -> NOT LISTED (strength)",
 "APT|2020-06-17": "v1's 07-08 buy came after his replayed sell (07-06), at $18.59 vs his $13.46 (+38%) -> NOT LISTED (tightening)",
 "BE|2020-06-30": "Off the list the night before (4 checks failed, strength 89); listed only 07-24/07-27 at about twice his price; his buy was a news gap, not a base breakout -> NOT LISTED, set aside as a news-gap buy",
 "BE|2020-08-13": "Off the list the night before (strength 90.5); its listed nights were other days, refused as stop too wide or low volume -> NOT LISTED (strength)",
 "NIO|2020-09-29": "v1 bought 10-08 (stopped, -1.1R) and 10-14 at $24.39, 27% above him, for +16.5R; the full 5-slot book refused both -> BOUGHT LATER; a late re-entry the live book never took is not a match",
 "JMIA|2020-11-18": "Off the list the night before (riding-the-average check failed, strength 99.1); its 3 listed nights were before, refused as stop too wide or low volume -> NOT LISTED (riding the average)",
 "SKLZ|2021-01-05": "Off the list the night before (strength 87.9); listed once (12-29), refused for low volume -> NOT LISTED (strength)",
 "APHA|2021-01-06": "Off the list the night before (strength 85.3); listed once, 01-28, after his buy, refused for low volume -> NOT LISTED (strength)",
 "BE|2021-01-06": "v1's buys 12-07/12-08 came 19-20 sessions before his, both stopped out; off the list the night before (strength 95.8) -> NOT LISTED (strength)",
 "SI|2021-01-22": "The builder's 01-08 buy was refused by the one-position-per-stock rule: v1 held SI 11-17..01-21 for +13.7R and sold the day before his buy -> NOT LISTED (higher lows); v1 had already caught the previous leg",
 "TLRY|2021-02-02": "Off the list the night before (strength 98.9, tightening failed); its 2 listed nights were before, refused as stop too wide -> NOT LISTED (tightening)",
 "CODX|2020-07-16": "Same class; the reason differs: the bars show his day's high crossed v1's level and the day traded 0.63x its average volume, so volume (not price) kept the order off",
}
m["key"] = m.ticker_y + "|" + m.his_entry_date
m["reconciled"] = m["class"]
m.loc[m.key == "NIO|2020-09-29", "reconciled"] = "BOUGHT EARLIER OR LATER"
m["resolution"] = m.key.map(RES).fillna("")
out = m[["ticker_y", "his_entry_date", "his_R_replay", "builder", "blind", "agree", "reconciled", "resolution"]].rename(
    columns={"ticker_y": "ticker", "his_R_replay": "his_R"}).sort_values("his_entry_date")
out.to_csv(f"{HERE}/reconcile/agreement.tsv", sep="\t", index=False)
print(f"agree on the class label: {out.agree.sum()} of {len(out)}")
print(out.reconciled.str.split(" \\(").str[0].value_counts().to_dict())
print(out[out.agree == 0][["ticker", "his_entry_date", "builder", "blind"]].to_string())
