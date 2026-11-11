import sys
sys.path.insert(0, "."); sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R, sheet as S
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb
items = []
for b in R.load():
    if b["set"] != "dated" or b["row"].get("big_winner") != "1":
        continue
    bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
    t = b["win"][-1]; D = t - 1
    g = bv.v1_gates(bars, D, rs_best=float(b["row"]["rs_best"]), raw_close=float(b["row"]["raw_close_D"]))
    f = bv.breakout_triggered({"h": float(b["h"][t]), "v": float(b["v"][t])}, g)
    if f["fired"]:
        continue
    failed = [k for k, v in g.get("gates", {}).items() if isinstance(v, dict) and not v.get("pass", True)] if isinstance(g.get("gates"), dict) else g.get("failed")
    why = (f"not listed: {failed}" if not g["ok"] else
           f"listed; buy day high {f['high']:.2f} vs level {f['level']:.2f} ({'cleared' if f['level_pass'] else 'NOT cleared'}), "
           f"volume {f['volume']/f['vol_bar']:.2f}x of the bar ({'ok' if f['volume_pass'] else 'SHORT'})")
    print(b["ticker"], b["row"]["E"], "|", why)
    items.append((b, dict(level=g.get("level"), p=max(0, t - 30), why=why)))
S.render(items, "scripts/probes/_717_qm_confidence_1111/big_missed.png",
         "Qullamaggie big winners the new rules do NOT buy — chart ends on his buy day (shaded); dashed = our buy level",
         "letter|ticker|buy day|why", lambda b, r: f"{b['ticker']}|{b['row']['E']}|{r['why']}")
