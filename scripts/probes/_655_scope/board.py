"""#655 scope — shared helpers: rebuild a night's board and G3 inputs from the capture. $0."""
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from agents.market_intelligence import market_adjusted_correlation as mac  # noqa: E402
from agents.market_intelligence import theme_correctness as tc  # noqa: E402
from load import load  # noqa: E402

B = load()
NIGHTS = [date.fromisoformat(r["et"][:10]) for r in B["correctness"] if r["et"][11:16] == "17:31"][-10:]
STORED = {date.fromisoformat(r["et"][:10]): r["detail"] for r in B["correctness"] if r["et"][11:16] == "17:31"}
ENGINE_NIGHTS = sorted({r["d"] for r in B["themes"]})


def board_at(d):
    """get_active_themes(7) as of night d: latest row per name dated d-7..d, then drop Retired."""
    latest = {}
    for r in B["themes"]:
        if d - timedelta(days=7) <= r["d"] <= d:
            if r["name"] not in latest or (r["d"], r["id"]) > (latest[r["name"]]["d"], latest[r["name"]]["id"]):
                latest[r["name"]] = r
    return [r for r in latest.values() if r["stage"] != "Retired"]


def ordered_board(d):
    """Board in the stored audit row's own order (= get_active_themes' DB-collation order)."""
    bd = {r["name"]: r for r in board_at(d)}
    order = [t["name"] for t in STORED[d]["g3"]["themes"]]
    missing = [n for n in order if n not in bd]
    extra = [n for n in bd if n not in set(order)]
    return [bd[n] for n in order if n in bd], missing, extra


_EX = {}


def g3_inputs(d):
    if d in _EX:
        return _EX[d]
    sd = max(x for x in B["scores"] if x <= d)
    scores = B["scores"][sd]
    sector = {t: v["sector"] for t, v in scores.items() if v["sector"]}
    closes = B["closes"]
    sessions = mac.session_index(closes["SPY"], d, mac.BELONGING_LOOKBACK_SESSIONS)
    market = mac.log_returns(closes["SPY"], sessions)
    excess = mac.excess_returns(closes, sessions, market)
    usable = tc.usable_set(excess)
    _EX[d] = (excess, usable, scores, sector)
    return _EX[d]


def g3(themes, d):
    excess, usable, scores, sector = g3_inputs(d)
    return tc.compute_g3([{"name": t["name"], "stage": t["stage"], "tickers": list(t["tickers"])} for t in themes],
                         excess, usable, scores, sector)
