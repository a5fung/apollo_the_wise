"""One-off (2026-11-27): give the 11-25 COT news alerts the figures they were scored on.

The job stored only {event, class, z, fact, read, first_minute} per news item then; the raw FXEmpire rows of that day
survive in scripts/probes/_cot_newswatch_design_1125/nw_fx_1123_1206.json. `cot_family.fill_news_item_from_fx` rebuilds
country / release / series from them and REFUSES an item whose stored class and z the rows do not reproduce.

Input: a JSON list of {id, market, direction, alert_date, detail} (the live rows). Output: a JSON list of
{id, news} (the patched news[]) and a count. Usage: python build.py rows_in.json patch_out.json
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from agents.market_intelligence import cot_family as cf  # noqa: E402

RAW = json.loads((ROOT / "scripts/probes/_cot_newswatch_design_1125/nw_fx_1123_1206.json").read_text())["united-states"]


def patch(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        det = r["detail"] if isinstance(r["detail"], dict) else json.loads(r["detail"])
        if isinstance(det, str):
            det = json.loads(det)
        day = date.fromisoformat(str(r["alert_date"])[:10])
        assert day == date(2026, 11, 25), r
        news = [cf.fill_news_item_from_fx(n, r["market"], r["direction"], day, RAW) for n in det.get("news") or []]
        out.append({"id": r["id"], "market": r["market"], "news": news})
    return out


if __name__ == "__main__":
    rows = json.loads(Path(sys.argv[1]).read_text())
    res = patch(rows)
    Path(sys.argv[2]).write_text(json.dumps(res, indent=1))
    print(f"{len(res)} alerts, {sum(len(x['news']) for x in res)} news items patched")
