"""#687 helper — dump #685's admitted population (the 192 keys, their harness status, ORB, submit time, fill) from
study.py's OWN harness walk, so the entry-half anchor can run the live order path on the same alerts and stored IEX bars.
Local only, $0, no prod read. Output: anchor_keys.tsv."""
import sys
from datetime import time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_685"))
import study as ST  # noqa: E402

alerts, regime_rows, adv, daily, day0, held, mincov, trades, S = ST.load_all()
rs_d = ST.ep.RULESETS["era_d"]
H0 = ST.harness_walk(alerts, regime_rows, adv, daily, day0, rs_d, ST.HORIZON)
live_high_abstain = [r for r in H0 if str(r["admit"]).startswith("abstain") and r["alert"].get("score_tier") == "HIGH"]
adm = [r for r in H0 if r["admit"] == "admit"] + live_high_abstain
adm.sort(key=lambda r: (r["alert_date"], r["ticker"]))
with open(HERE / "anchor_keys.tsv", "w") as fh:
    fh.write("ticker|alert_date|status|reason|entered|entry_px|stop|target|submit|orb_high|orb_low|adr_pct|n_day0_bars|realized_r\n")
    for h in adm:
        bars0 = day0.get((h["ticker"], h["alert_date"]), [])
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        fh.write("|".join(str(x) for x in [h["ticker"], h["alert_date"], h["status"], h["reason"], h["entered"], h["entry_px"], h["stop"], h["target"],
                                             h["submit"].strftime("%H:%M"), orb["h"] if orb else "", orb["l"] if orb else "", h["adr_pct"], len(bars0), h["realized_r"]]) + "\n")
print("admitted", len(adm), "entered", sum(1 for h in adm if h["entered"]))
