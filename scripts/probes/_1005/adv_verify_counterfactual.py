"""2026-10-05 adversarial verify (read-only): would the INTENDED shortlist order (Friday's RS-universe
ADV feeding the liquidity axis) have graded a different set than the alphabetical order that acted?
Recomputes the ranking per tick with the real ep_shortlist_shadow.compute_shortlist_ranking."""
import asyncio
from collections import defaultdict
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_shortlist_shadow import compute_shortlist_ranking
from agents.market_intelligence.ep_rubric import SHORTLIST_SIZE

ET = "AT TIME ZONE 'America/New_York'"


async def one_day(c, d):
    prev = await c.fetchval("SELECT max(score_date) FROM mi_stock_scores WHERE score_date < $1", d)
    advm = {r["ticker"]: float(r["adv_20"]) for r in await c.fetch(
        "SELECT ticker, adv_20 FROM mi_stock_scores WHERE score_date=$1 AND adv_20 IS NOT NULL", prev)}
    rows = await c.fetch("""SELECT scan_time_et, (scan_time_et AT TIME ZONE 'America/New_York')::time::text t,
               ticker, gap_pct, prev_close, adv, adv_source, in_active_theme, rank_by_prescore, shortlisted_by_prescore, board_n
               FROM mi_ep_shortlist_shadow WHERE scan_date=$1 ORDER BY scan_time_et, rank_by_prescore""", d)
    ticks = defaultdict(list)
    for r in rows:
        ticks[(r["scan_time_et"], r["t"])].append(r)
    print(f"== {d}: prev score_date {prev}, {len(advm)} names with adv_20; ticks={len(ticks)}")
    flips_in, flips_out = defaultdict(list), defaultdict(list)
    for (ts, t), rs in sorted(ticks.items()):
        if len(rs) <= SHORTLIST_SIZE:
            continue
        cands, theme = [], set()
        for r in rs:
            a = advm.get(r["ticker"])
            cands.append({"ticker": r["ticker"], "gap_pct": r["gap_pct"], "prev_close": r["prev_close"],
                          "adv": a if a else r["adv"], "adv_source": "rs_universe" if a else "pending"})
            if r["in_active_theme"]:
                theme.add(r["ticker"])
        _, rk = compute_shortlist_ranking(cands, theme)
        actual_in = {r["ticker"] for r in rs if r["shortlisted_by_prescore"]}
        # sanity: recompute the ACTUAL order from the stored raw inputs -> must reproduce the stored ranks
        _, rk_act = compute_shortlist_ranking(
            [{"ticker": r["ticker"], "gap_pct": r["gap_pct"], "prev_close": r["prev_close"], "adv": r["adv"],
              "adv_source": r["adv_source"]} for r in rs], theme)
        repro = all(rk_act[r["ticker"]] == r["rank_by_prescore"] for r in rs)
        intended_in = {tk for tk, k in rk.items() if k <= SHORTLIST_SIZE}
        fin, fout = sorted(intended_in - actual_in), sorted(actual_in - intended_in)
        for x in fin:
            flips_in[x].append(t[:5])
        for x in fout:
            flips_out[x].append(t[:5])
        print(f"  {t[:8]} board={len(rs)} repro_actual={repro} would-ADD={fin} would-DROP={fout}")
    return flips_in, flips_out


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("now ET:", await c.fetchval(f"SELECT (now() {ET})::text"))
        for d in await c.fetch("""SELECT DISTINCT scan_date FROM mi_ep_shortlist_shadow WHERE board_n > 20 ORDER BY 1"""):
            fi, fo = await one_day(c, d["scan_date"])
            names = sorted(set(fi) | set(fo))
            if not names:
                continue
            print(f"  -- {d['scan_date']}: per-name max ep_score / tier that day, and alerts")
            for tk in names:
                r = await c.fetchrow("""SELECT max(ep_score) mx, count(*) FILTER (WHERE ep_score IS NOT NULL) n_graded,
                        string_agg(DISTINCT score_tier, ',') tiers,
                        string_agg(DISTINCT LEFT(filter_reason, 50), ' | ') FILTER (WHERE filter_reason NOT LIKE 'outside top-%') why
                        FROM mi_ep_scan_log WHERE scan_date=$1 AND ticker=$2""", d["scan_date"], tk)
                al = await c.fetchval("SELECT count(*) FROM mi_ep_alerts WHERE alert_date=$1 AND ticker=$2", d["scan_date"], tk)
                print(f"     {tk:6} add@{fi.get(tk, [])[:6]}{'...' if len(fi.get(tk, []))>6 else ''} "
                      f"drop@{fo.get(tk, [])[:6]}{'...' if len(fo.get(tk, []))>6 else ''} "
                      f"max_score={r['mx']} graded_rows={r['n_graded']} tiers={r['tiers']} alerts={al} other_reasons={(r['why'] or '')[:160]}")
        print("== the 09:00 double tick: distinct scan_time_et in 09:00:00-09:00:59 per day (last 15 days)")
        for r in await c.fetch(f"""SELECT scan_date, count(DISTINCT scan_time_et) n FROM mi_ep_shortlist_shadow
                   WHERE scan_date > current_date - 15 AND (scan_time_et {ET})::time BETWEEN '09:00' AND '09:00:59'
                   GROUP BY 1 ORDER BY 1"""):
            print("  ", dict(r))
        print("== ep alerts today")
        for r in await c.fetch("SELECT ticker, ep_score, score_tier, (created_at AT TIME ZONE 'America/New_York')::time::text t FROM mi_ep_alerts WHERE alert_date=(now() AT TIME ZONE 'America/New_York')::date ORDER BY created_at"):
            print("  ", dict(r))


asyncio.run(main())
