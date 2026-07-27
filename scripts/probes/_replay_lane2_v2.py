"""#167 Lane-2 grouping v2 — REGISTRY-mode forward-era REPLAY driver
(operator-run, read-only by default).

Replays the v2 REGISTRY behavior (operator reframe 2026-07-27: incremental
state-carrying — today's alerts + compact ACTIVE-narrative roster + watch-list
seeds, instead of the superseded re-read-a-10-day-pool draft) over the
forward-era alert history by calling the REAL
`theme_engine.discover_narrative_themes` with the `lane2_grouping_v2` flag
forced ON **in-process only** (the DB toggle is never touched) and
`persist=False` (ZERO writes).

REGISTRY CHAINING: in production the roster is the lane's own persisted rows;
with persist=False nothing is written, so this driver chains an IN-MEMORY
registry across days — `db.get_lane2_active_narratives` /
`db.get_lane2_pending_seeds` are patched to serve it (mirroring the SQL's
latest-per-name / latest-per-ticker windowed semantics exactly), and it is
updated after each day from the run's own `proposals` / `new_seeds` output —
precisely the rows the persist path would have written. All roster HYGIENE
(seed consumption, today-supersedes-seed, LANE2_ROSTER_MAX) lives in
theme_engine and is therefore exercised for real, not simulated.

The v1 baseline for comparison is production's actual history — v1 already ran
live over these dates, so it is not re-run. The prior POOL-mode replay results
(23 proposals, 18 near-duplicates of one narrative) are the operator's
/tmp/lane2_replay.json.

Modes
-----
--no-llm            Deterministic leg only: per-day gate decision, today-pool
                    composition, roster state, prompt size. No API call, no
                    key needed. SAFE ANYWHERE. Approximates registry growth
                    (every unplaced qualifying alert becomes a seed, story =
                    head of its evidence) so roster-bearing prompt sizes are
                    estimable — joins/births need the model, so narrative
                    counts from this leg are NOT meaningful.
--offline FILE      Serve today-alerts from a JSON pull (query below) instead
                    of the live DB — lets the replay run off-box. Without it,
                    the script reads the DB via db.get_today_ep_alerts
                    (SELECT only; intended for the market-agent container).
--persist-backfill  OPERATOR-ONLY: persist replay proposals under the
                    SEGREGATED source 'narrative_cogap_backfill' (the #167
                    hindsight-segregation lane) so
                    `theme_engine.evaluate_narrative_themes(days=60,
                    include_backfill=True)` can score them. Watch-list seeds
                    are NEVER persisted on backfill runs (engine-enforced) —
                    hindsight seeds must not enter the forward watch list.
                    Default is persist=False — no writes at all.

The LLM leg uses the production model (shared.llm_models.THEME_MODEL =
claude-sonnet-4-6) at max_tokens=1500 — identical to live. Requires
ANTHROPIC_API_KEY. Registry mode sends only TODAY's documents + a compact
roster (vs the pool draft's ~25-35k input tokens/night); the driver prints
measured usage per night and a total.

Offline data pull (prod, SELECT only):
  ssh apollo@87.99.134.162 "docker exec apollo-postgres psql -U apollo -d apollo -tA -c \"
    SELECT COALESCE(json_agg(row_to_json(t)), '[]') FROM (
      SELECT DISTINCT ON (a.ticker, a.alert_date)
             a.alert_date, a.ticker, a.ep_score, a.gap_pct,
             a.catalyst, a.claude_analysis, a.grounded_text
      FROM mi_ep_alerts a
      WHERE a.alert_date BETWEEN '2026-05-20' AND '2026-07-24'
        AND COALESCE(a.source, 'live') = 'live'
      ORDER BY a.ticker, a.alert_date, a.ep_score DESC) t;\"" > lane2_alerts.json

Run:  python scripts/probes/_replay_lane2_v2.py --offline lane2_alerts.json \
          --start 2026-06-08 --end 2026-07-24 [--no-llm] [--out replay.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence import theme_engine  # noqa: E402
from agents.market_intelligence.theme_engine import (  # noqa: E402
    LANE2_ROSTER_MAX, LANE2_SEED_STORY_BUDGET, LANE2_WINDOW_TRADING_DAYS,
    _build_lane2_registry_prompt, _lane2_input_text, _lane2_qualifies,
    _lane2_window_start, discover_narrative_themes,
)


def _load_offline(path: str) -> list[dict]:
    rows = json.loads(Path(path).read_text())
    for r in rows:
        r["alert_date"] = date.fromisoformat(r["alert_date"])
    return rows


def _trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


class _MemRegistry:
    """In-memory stand-in for the lane's own persisted rows (persist=False ⇒
    nothing hits the DB). `active`/`pending` mirror the patched readers' SQL:
    latest row per name / per ticker, window_start <= run_date < before,
    ordered most-recently-touched first."""

    def __init__(self) -> None:
        self.narrative_rows: list[dict] = []  # {run_date, name, tickers, thesis}
        self.seed_rows: list[dict] = []       # {run_date, ticker, story}

    @staticmethod
    def _latest(rows: list[dict], key: str, window_start: date, before: date) -> list[dict]:
        best: dict[str, dict] = {}
        for r in rows:
            if window_start <= r["run_date"] < before:
                cur = best.get(r[key])
                if cur is None or r["run_date"] > cur["run_date"]:
                    best[r[key]] = r
        out = sorted(best.values(), key=lambda r: r[key])
        out.sort(key=lambda r: r["run_date"], reverse=True)  # stable: run_date DESC, key ASC
        return out

    def active(self, window_start: date, before: date) -> list[dict]:
        return [dict(r) for r in self._latest(self.narrative_rows, "name", window_start, before)]

    def pending(self, window_start: date, before: date) -> list[dict]:
        return [dict(r) for r in self._latest(self.seed_rows, "ticker", window_start, before)]

    def apply_day(self, scan_d: date, proposals: list[dict], new_seeds: list[dict]) -> None:
        for p in proposals or []:
            self.narrative_rows.append({"run_date": scan_d, "name": p["name"],
                                        "tickers": list(p["tickers"]),
                                        "thesis": p.get("thesis")})
        for s in new_seeds or []:
            self.seed_rows.append({"run_date": scan_d, "ticker": s["ticker"],
                                   "story": s["story"]})


async def _replay_one(scan_d: date, reg: _MemRegistry, rows_offline, *, no_llm: bool,
                      persist_backfill: bool) -> dict:
    """One replay day through the REAL discover_narrative_themes (flag forced ON
    in-process; DB toggle untouched; registry served from memory)."""
    async def fake_flag():
        return True

    async def fake_today(d):
        dd = d if isinstance(d, date) else date.fromisoformat(str(d))
        day = [r for r in rows_offline if r["alert_date"] == dd]
        return sorted(day, key=lambda r: r.get("ep_score") or 0, reverse=True)

    async def fake_active(window_start, before):
        return reg.active(window_start, before)

    async def fake_pending(window_start, before):
        return reg.pending(window_start, before)

    async def _noop_audit(*a, **k):
        return None

    async def _noop_spend(**k):
        return None

    patches = [
        patch("agents.market_intelligence.db.get_lane2_grouping_v2_enabled", fake_flag),
        patch("agents.market_intelligence.db.get_lane2_active_narratives", fake_active),
        patch("agents.market_intelligence.db.get_lane2_pending_seeds", fake_pending),
        patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", _noop_spend),
        # audit rows are prod telemetry — a replay must not write them even on-box
        patch("agents.market_intelligence.db.log_audit_event", _noop_audit),
    ]
    if rows_offline is not None:
        patches.append(patch("agents.market_intelligence.db.get_today_ep_alerts", fake_today))

    started = [p.start() for p in patches]  # noqa: F841
    try:
        if no_llm:
            # Deterministic leg — replicates the exact pre-LLM path of
            # _discover_lane2_registry using the same helpers the live code
            # calls, then APPROXIMATES state growth (all-seed) for sizing.
            from agents.market_intelligence.db import get_today_ep_alerts
            alerts = await get_today_ep_alerts(scan_d) if rows_offline is not None else []
            cand = [a for a in alerts if _lane2_qualifies(a)]
            ws = _lane2_window_start(scan_d)
            active = reg.active(ws, scan_d)
            seeds = reg.pending(ws, scan_d)
            member_set = {tk for n in active for tk in (n.get("tickers") or [])}
            today_set = {a["ticker"] for a in cand}
            seeds = [s for s in seeds
                     if s["ticker"] not in member_set and s["ticker"] not in today_set]
            active, seeds = active[:LANE2_ROSTER_MAX], seeds[:LANE2_ROSTER_MAX]
            src = {"grounded": 0, "analysis": 0, "catalyst": 0, "none": 0}
            for a in cand:
                src[_lane2_input_text(a)[1]] += 1
            prompt = _build_lane2_registry_prompt(cand, active, seeds) if cand else ""
            # sizing approximation: every qualifying name seeds (no model → no joins)
            approx = [{"ticker": a["ticker"],
                       "story": _lane2_input_text(a)[0][:LANE2_SEED_STORY_BUDGET]}
                      for a in cand]
            reg.apply_day(scan_d, [], approx)
            return {"date": str(scan_d), "gated": bool(cand),
                    "today": sorted(today_set),
                    "roster_active": len(active), "roster_seeds": len(seeds),
                    "input_sources": src, "prompt_chars": len(prompt),
                    "est_input_tokens": len(prompt) // 4}
        out = await discover_narrative_themes(
            scan_d, persist=persist_backfill, backfilled=True)
        if not out.get("error"):
            reg.apply_day(scan_d, out.get("proposals") or [], out.get("new_seeds") or [])
        return {"date": str(scan_d), **{k: v for k, v in out.items() if k != "date"}}
    finally:
        for p in patches:
            p.stop()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="JSON alert pull (see module docstring)")
    ap.add_argument("--start", default="2026-06-08")
    ap.add_argument("--end", default="2026-07-24")
    ap.add_argument("--no-llm", action="store_true",
                    help="deterministic gate/roster/prompt replay only — no API call")
    ap.add_argument("--persist-backfill", action="store_true",
                    help="OPERATOR-ONLY: write proposals under narrative_cogap_backfill")
    ap.add_argument("--out", help="write per-day results JSON here")
    args = ap.parse_args()

    rows = _load_offline(args.offline) if args.offline else None
    if args.persist_backfill and args.no_llm:
        ap.error("--persist-backfill requires the LLM leg")

    reg = _MemRegistry()
    results = []
    for scan_d in _trading_days(date.fromisoformat(args.start), date.fromisoformat(args.end)):
        r = await _replay_one(scan_d, reg, rows, no_llm=args.no_llm,
                              persist_backfill=args.persist_backfill)
        results.append(r)
        if args.no_llm:
            flag = "GATED" if r["gated"] else "  -  "
            src = r["input_sources"]
            print(f"{r['date']}  {flag}  today={len(r['today']):2d} "
                  f"roster={r['roster_active']:2d}A/{r['roster_seeds']:2d}S "
                  f"g/a/c={src['grounded']}/{src['analysis']}/{src['catalyst']} "
                  f"~{r['est_input_tokens']:5d} tok  today:{','.join(r['today'])}")
        else:
            u = r.get("usage") or {}
            regs = r.get("registry") or {}
            print(f"{r['date']}  roster={regs.get('active', 0):2d}A/{regs.get('seeds', 0):2d}S  "
                  f"join={r.get('joined', [])} new={r.get('born', [])} "
                  f"seeds+={len(r.get('new_seeds') or [])} "
                  f"tok_in={u.get('input_tokens', '?')}"
                  f"{'  ERR:' + str(r['error'])[:80] if r.get('error') else ''}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1))
        print(f"\nwrote {args.out}")

    if args.no_llm:
        n_gated = sum(1 for r in results if r.get("gated"))
        toks = [r["est_input_tokens"] for r in results if r.get("gated")]
        print(f"\n{len(results)} weekdays replayed · memory={LANE2_WINDOW_TRADING_DAYS}td "
              f"· {n_gated} evaluated day(s) · est input tok/night "
              f"min/med/max = {min(toks)}/{sorted(toks)[len(toks)//2]}/{max(toks)}"
              if toks else "\nno gated days")
    else:
        joins = sum(len(r.get("joined") or []) for r in results)
        births = sum(len(r.get("born") or []) for r in results)
        final = reg.active(date.fromisoformat(args.start) - timedelta(days=1),
                           date.fromisoformat(args.end) + timedelta(days=1))
        toks = [r["usage"]["input_tokens"] for r in results
                if r.get("usage", {}).get("input_tokens") is not None]
        print(f"\n{len(results)} weekdays replayed · {births} narrative(s) born · "
              f"{joins} join event(s) · {len(final)} distinct narrative(s) all-era")
        for nrow in final:
            print(f"  [{nrow['run_date']}] {nrow['name']}: {','.join(nrow['tickers'])}")
        if toks:
            print(f"input tokens/night min/med/max/total = "
                  f"{min(toks)}/{sorted(toks)[len(toks)//2]}/{max(toks)}/{sum(toks)}")


if __name__ == "__main__":
    asyncio.run(main())
