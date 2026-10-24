#!/usr/bin/env python3
"""Off the output files only (no third run): the security-type mix of the primary EP events, of the label-matched events and of the
tier-1 controls — the untyped-admitted rule (`universe_ok` admits an unknown type, as prod does) has no downstream gate in an EP list."""
import pandas as pd
O = "/Users/alvinfung/apollo_data/cb702/qm_streams/ep_join_1023"
def mix(df, label):
    t = df.sectype.fillna("").astype(str)
    wu = df.ticker.str.match(r"^[A-Z]{5}$") & df.ticker.str[-1].isin(["W", "U"]) & (t == "")
    print(f"{label}: n {len(df)} | CS {int((t == 'CS').sum())} | ADRC {int((t == 'ADRC').sum())} | UNTYPED {int((t == '').sum())} ({100 * (t == '').mean():.0f}%)"
          f" | of the untyped, 5-letter tickers ending W/U (warrant/unit shape) {int(wu.sum())} | other typed {int((~t.isin(['CS', 'ADRC', ''])).sum())}")
for e in ("A", "B"):
    ev = pd.read_csv(f"{O}/ep_events_{e}.tsv.gz", sep="\t", dtype={"ticker": str, "E": str, "sectype": str}, keep_default_na=False)
    mix(ev, f"era {e} primary EP events")
    F = pd.read_csv(f"{O}/ep_minute_fetch_list.psv", sep="|", dtype=str)
    f1 = F[(F.era == e) & (F.tier == "1")].merge(ev[["ticker", "E", "sectype"]], left_on=["ticker", "date"], right_on=["ticker", "E"], how="left")
    mix(f1, f"era {e} tier-1 controls to fetch")
X = pd.read_csv(f"{O}/labels_ep_joined.tsv", sep="\t", dtype=str, keep_default_na=False)
m = X[(X.bo_matched == "0") & (X.m_primary == "1")]
for e in ("A", "B"):
    g = m[m.era == e].drop_duplicates(["sym", "E_ep"])
    print(f"era {e} label-matched EP events (distinct): {len(g)} | typed CS/ADRC {int(g.ep_sectype.isin(['CS', 'ADRC']).sum())} | UNTYPED {int((g.ep_sectype == '').sum())} -> {sorted(set(g[g.ep_sectype == ''].sym))}")
# base rate for the window: the 294's EP events within +-60 spread flat over 121 sessions -> expected in a 16-session window
for e in ("A", "B"):
    g = X[(X.bo_matched == "0") & (X.era == e)]
    n60 = int((g.delta_ep_wide60 != "").sum()); n_win = int(g.m_primary.astype(int).sum())
    print(f"era {e}: labels with an EP event within +-60: {n60}; a flat spread over the 121 sessions puts {n60 * 16 / 121:.1f} in the 16-session window [-10, +5]; observed {n_win}")
