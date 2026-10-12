# READ-ONLY: reproduces agent._handle_theme_query's body (the /themes render) against the live DB.
import asyncio
from agents.market_intelligence.briefing import _compute_scored_themes
from agents.market_intelligence.theme_ecosystems import format_ecosystem_board, load_ecosystem_assignments
from agents.market_intelligence.db import get_rs_for_tickers, get_prior_theme_scores
from agents.market_intelligence.theme_engine import get_today_themes
from agents.market_intelligence.collector import et_today

async def main():
    today_str = et_today().strftime("%Y-%m-%d")
    themes = await get_today_themes(today_str)
    print("themes", len(themes), "theme_date", themes[0].get("theme_date") if themes else None)
    data_date = themes[0].get("theme_date", today_str)
    if hasattr(data_date, "isoformat"): data_date = data_date.isoformat()
    all_tickers = list({tk for t in themes for tk in (t.get("tickers") or [])})
    theme_rs_data, prior_scores, eco_map = await asyncio.gather(
        get_rs_for_tickers(data_date, all_tickers), get_prior_theme_scores(today_str), load_ecosystem_assignments())
    scored, fading = _compute_scored_themes(themes, theme_rs_data or {}, prior_scores or {})
    lines = [f"*{len(scored)} Active Themes — {data_date}*"]
    lines += format_ecosystem_board(scored, fading, theme_rs_data or {}, eco_map)
    print("\n".join(lines))
asyncio.run(main())
