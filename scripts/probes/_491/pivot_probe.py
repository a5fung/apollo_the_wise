"""#491 pivot-migration probe — where the eight ex-miner / AI-compute names stand on the tape tonight,
which gate decides each of them under TODAY's engine, and what the PROPOSED re-homing pass would do.

READ-ONLY, $0, NO model calls. Run INSIDE the market container (the app's own DB pool; every query
runs in a READ ONLY transaction, so the server rejects any write):

    docker exec -i apollo-market python - < scripts/probes/_491/pivot_probe.py \
        > scripts/probes/_491/pivot_probe_out.jsonl 2> scripts/probes/_491/pivot_probe_summary.txt

    # hand cases only, no DB (also runnable on a laptop):
    python3 scripts/probes/_491/pivot_probe.py --selftest

stdout: one JSON line per record (kind = toggles | board_theme | name | tie | verdict | audit |
sweep | pricing). stderr: the plain-words summary.

WHAT IT ANSWERS (design doc: docs/analysis/491_pivot_migration_proposal_2026-10-03.md)
  1. For each of the 8 names (CIFR, HUT, CRWV, IREN, WULF, CORZ, CLSK, APLD): tonight's home(s),
     RS / rank / sector, the last theme it sat in and when (orphan age), whether a #491 M2 seed
     names it inside the Lane-2 window, live cooldowns / exclusions / operator protection, and the
     mi_audit_log trail of the last 45 days grouped by event type — the "which path removed it"
     question.
  2. Market-adjusted co-movement (the engine's OWN maths, imported — market_adjusted_correlation +
     theme_engine._comove_verdict, never re-derived) of each name with:
       - the AI-compute theme's current members (the proposed destination),
       - the pivot / crypto theme's current members (expected `thin_basket` tonight: 2 members ->
         leave-one-out basket of 1 -> the engine itself cannot judge it; reported AS-IS),
       - every live theme's basket (top 3),
       - labelled SUPPLEMENTARY references that are NOT the engine's test: the 8-name cohort
         leave-one-out, E-CRYPTO exemplars, E-AIINFRA exemplars (taxonomy, min_members=1).
  3. The verdict each name gets under the recommendation (`rehome_verdict`, PURE — tested), with the
     deciding gate named, next to what today's engine does with it (`today_path`).
  4. GENERALIZE: every live (or retired <= 30d) theme whose NAME or DESCRIPTION carries a pivot stem
     (PIVOT_STEMS below — declared here, not tuned after seeing results), the live non-Fading theme
     its members tie to best, and the members that tie >= the bar to it — a CANDIDATE list, not a
     ruling.
  5. The recommendation's incremental cost, priced from the model the THEME_MODEL role resolves to
     in prod (mi_model_resolution, else the in-process effective_model) × tonight's candidate count
     ÷ the 18-stock assignment batch, with the measured output fit (theme_engine.py ~4027-4043).

NOT MODELLED (stated): the assignment LLM's verdict (no model calls — the probe stops at "offered to
the judgement"); F4 post-assignment validation; same-run ordering effects (the two-pass deferral);
the `get_rs_leaders` liquidity/sector filters behind the 600 ceiling (rs_rank is the UNIVERSE rank
and is reported as an approximation of the leaders-fetch rank, as the 2026-08-05 design corrected).
APPROXIMATION: "covered" and every tie are read off the LAST SAVED board (the get_active_themes
read), not tonight's post-rescore `updated_themes` — a name the next run's prune/validation releases
still reads covered here. Close enough to judge the design; not an exact replay of an engine night.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

# ── the 8 names the main session read off the 2026-10-02 board ──────────────────────────────
COHORT: tuple[str, ...] = ("CIFR", "HUT", "CRWV", "IREN", "WULF", "CORZ", "CLSK", "APLD")
AI_TARGET_HINT = "Emerging AI Compute & Cloud Infrastructure Platforms"   # tonight's destination
PIVOT_THEME_HINT = "Bitcoin Miners Pivoting to AI/HPC Data Center Hosting"  # tonight's legacy home
CRYPTO_NAME_STEMS = ("bitcoin", "crypto", "miner", "mining")

# ── engine constants, cross-checked against the running module at run time ──────────────────
COMOVE_BAR = 0.35            # theme_engine.ASSIGN_COMOVE_BAR (the signed per-pair bar)
G2_MARGIN = 0.20             # #655 G2 "misfiled": other >= bar AND other >= own + 0.20
POOL_FLOOR = 70.0            # theme_engine.ASSIGN_POOL_RS_FLOOR
POOL_CEILING = 600           # theme_engine.ASSIGN_POOL_CEILING (leaders-fetch rank; rs_rank approximates)
LANE2_WINDOW_TRADING_DAYS = 10
ORPHAN_WINDOW_DAYS = 14      # proposed orphan reach (D2) — the cooldown / canonicalize window
BOARD_STALE_DAYS = 7         # get_active_themes(stale_after_days=7)
AUDIT_LOOKBACK_DAYS = 45
SWEEP_RETIRED_DAYS = 30
ASSIGN_BATCH = 18            # theme_engine._ASSIGN_LLM_BATCH_SIZE
OUT_FIT = (274.0, 73.4)      # output_tokens ~ 274 + 73.4 x pool_size (sonnet-4-6 fit, theme_engine.py)
OUT_GROWTH_SONNET5 = 3.5     # measured cross-model growth the batch size was derived with
PREFIX_TOKENS_PER_THEME = 45 # the shared prefix renders every theme; ~45 tokens/theme (estimate, labelled)
FIT_CALL_TOKENS = (1200, 250)  # ep_theme_belonging's measured fit call: ~1.2k in / ~250 out
# Declared BEFORE the run: the stems that mark a theme as naming a business pivot.
PIVOT_STEMS: tuple[str, ...] = ("pivot", "transition", "repurpos", "convert", "conversion", "diversif")
PAYING_STAGES = ("Accelerating", "Mainstream")   # ep_theme_belonging.THEME_BONUS_STAGES


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def emit(kind: str, **rec: Any) -> None:
    print(json.dumps({"kind": kind, **rec}, default=str), flush=True)


# ═══════════════════════════════════ PURE PARTS (unit-tested) ═══════════════════════════════════

def pivot_stems_in(text: str | None) -> list[str]:
    """The declared pivot stems present in `text` (case-insensitive), in PIVOT_STEMS order."""
    low = (text or "").lower()
    return [s for s in PIVOT_STEMS if s in low]


def latest_per_name(rows: list[dict], today: date, stale_days: int = BOARD_STALE_DAYS) -> list[dict]:
    """get_active_themes' idiom over plain rows: the LATEST row per name inside the window, then
    drop names whose latest row is Retired. A Retired latest row never resurrects an older
    non-Retired snapshot (the 2026-06-09 retired-gap fix)."""
    cutoff = today - timedelta(days=stale_days)
    best: dict[str, dict] = {}
    for r in rows:
        if r["theme_date"] < cutoff:
            continue
        cur = best.get(r["name"])
        if cur is None or r["theme_date"] > cur["theme_date"]:
            best[r["name"]] = r
    return [r for r in best.values() if r["stage"] != "Retired"]


def in_pool(rs_composite: float | None, rs_rank: int | None) -> tuple[bool | None, str]:
    """The RS-floor assignment pool (`_build_theme_pools`): RS >= 70 within the top-600 leaders
    fetch. rs_rank is the UNIVERSE rank — an approximation of the leaders-fetch rank (stated).
    None RS -> unknown (never a silent yes)."""
    if rs_composite is None:
        return None, "no score row"
    if rs_composite < POOL_FLOOR:
        return False, f"RS {rs_composite:.0f} < floor {POOL_FLOOR:.0f}"
    if rs_rank is not None and rs_rank > POOL_CEILING:
        return False, f"RS {rs_composite:.0f} clears the floor but rank {rs_rank} > {POOL_CEILING} (approx)"
    return True, f"RS {rs_composite:.0f} >= {POOL_FLOOR:.0f}" + (f", rank {rs_rank}" if rs_rank is not None else "")


def orphan_age_days(last_member_date: date | None, today: date) -> int | None:
    """Days since the name last sat in any theme row (None = never themed)."""
    if last_member_date is None:
        return None
    return (today - last_member_date).days


def g2_trigger(own_corr: float | None, own_reason: str | None,
               best_other_corr: float | None) -> tuple[bool, str]:
    """The LEAVE trigger for a covered member, on #655 G2's signed shape.
    judgeable arm:   own < bar AND other >= bar AND other >= own + G2_MARGIN
    unjudgeable arm: own theme cannot be read (thin_basket / no_history / no context — the
                     2-member pivot theme tonight) AND other >= bar   <- its own fork (D3)
    Returns (fires, arm)."""
    if best_other_corr is None or best_other_corr < COMOVE_BAR:
        return False, "other_below_bar" if best_other_corr is not None else "other_unjudgeable"
    if own_corr is None:
        return True, f"own_unjudgeable:{own_reason or 'unknown'}"
    if own_corr < COMOVE_BAR and best_other_corr >= own_corr + G2_MARGIN:
        return True, "g2_misfiled"
    if own_corr >= COMOVE_BAR:
        return False, "own_at_or_above_bar"
    return False, "margin_not_met"


@dataclass(frozen=True)
class Verdict:
    verdict: str          # OFFER | FALLBACK_SECTOR | REJECT
    gate: str             # the deciding gate, in plain words
    ticket: str | None    # how the name reached the funnel: covered_g2 | seeded | orphan | pool | None


def rehome_verdict(*, covered: bool, source_theme: str | None, target_theme: str | None,
                   target_stage: str | None, target_corr: float | None, target_reason: str | None,
                   own_corr: float | None, own_reason: str | None,
                   excluded: bool, protected_at_source: bool, cooldown_to_target: bool,
                   seeded_in_window: bool, orphan_age: int | None,
                   pool_ok: bool | None) -> Verdict:
    """THE recommendation's gate order, pure. One (name, proposed target) pair in; the verdict and
    the deciding gate out. Order (first hit decides):
      1 operator exclusion on the target        -> REJECT
      2 operator protection on the current home -> REJECT (a /bypass ruling is permanent)
      3 target is Fading                        -> REJECT (never migrate INTO Fading, design §4.4)
      4 live pair cooldown (name, target)       -> REJECT
      5 the admission ticket:
           covered  -> the LEAVE trigger (g2_trigger) must fire
           uncovered-> seeded (M2, today's rule) | orphan <= ORPHAN_WINDOW_DAYS (proposed D2) | pool
      6 the tape on the proposed pair: >= bar -> OFFER to the assignment judgement;
         unjudgeable -> FALLBACK_SECTOR (today's fail-safe); below bar -> REJECT."""
    if target_theme is None:
        return Verdict("REJECT", "no live non-Fading theme reads >= bar for this name", None)
    if excluded:
        return Verdict("REJECT", f"operator exclusion: {target_theme}", None)
    if covered and protected_at_source:
        return Verdict("REJECT", f"operator protection on current home: {source_theme}", None)
    if target_stage == "Fading":
        return Verdict("REJECT", f"never into a Fading theme: {target_theme}", None)
    if cooldown_to_target:
        return Verdict("REJECT", f"pair cooldown live: ({target_theme})", None)
    ticket: str | None
    if covered:
        fires, arm = g2_trigger(own_corr, own_reason, target_corr)
        if not fires:
            return Verdict("REJECT", f"covered by {source_theme}; leave trigger did not fire ({arm})", None)
        ticket = f"covered_g2[{arm}]"
    else:
        if seeded_in_window:
            ticket = "seeded"
        elif orphan_age is not None and orphan_age <= ORPHAN_WINDOW_DAYS:
            ticket = f"orphan[{orphan_age}d]"
        elif pool_ok:
            ticket = "pool"
        else:
            return Verdict("REJECT", "no admission ticket: not in the RS pool, not seeded, not a recent orphan",
                           None)
    if target_corr is None:
        return Verdict("FALLBACK_SECTOR", f"tape cannot judge the pair ({target_reason or 'unknown'})", ticket)
    if target_corr < COMOVE_BAR:
        return Verdict("REJECT", f"tape {target_corr:.2f} < {COMOVE_BAR} to {target_theme}", ticket)
    return Verdict("OFFER", f"tape {target_corr:.2f} >= {COMOVE_BAR} to {target_theme}; the assignment "
                            f"judgement decides", ticket)


def today_path(*, covered: bool, source_themes: list[str], seeded_in_window: bool,
               pool_ok: bool | None) -> str:
    """What TODAY's engine does with the name (no proposal applied)."""
    if covered:
        return (f"stays in {', '.join(source_themes)} — covered-exclusivity: never offered to another "
                f"theme (theme_engine.py:8760-8768, 6995-7005, 7064-7069)")
    if seeded_in_window:
        return "uncovered + seeded (#491 M2): enters the assignment pool past the RS floor tonight"
    if pool_ok:
        return "uncovered + RS pool: offered to the assignment judgement tonight"
    return ("unreachable tonight: under the RS-70 floor / outside the 600 fetch, no Lane-2 seed in "
            "the 10-trading-day window — waits for an EP alert or RS >= 70")


def price_candidates(n_candidates: int, in_price_per_mtok: float, out_price_per_mtok: float,
                     n_themes_on_board: int, growth: float = OUT_GROWTH_SONNET5) -> dict:
    """Incremental nightly cost of offering `n_candidates` extra names through the assignment
    funnel: ceil(n/18) extra batches; per batch input ~ prefix (every theme rendered) + 18 lines,
    output ~ growth x (274 + 73.4 x N). $ from pricing_for's per-MTok rates. Labelled estimate."""
    if n_candidates <= 0:
        return {"candidates": 0, "batches": 0, "usd_per_night": 0.0}
    batches = math.ceil(n_candidates / ASSIGN_BATCH)
    in_tokens = batches * (PREFIX_TOKENS_PER_THEME * n_themes_on_board + 60 * ASSIGN_BATCH)
    out_tokens = sum(growth * (OUT_FIT[0] + OUT_FIT[1] * min(ASSIGN_BATCH, n_candidates - i * ASSIGN_BATCH))
                     for i in range(batches))
    usd = in_tokens / 1e6 * in_price_per_mtok + out_tokens / 1e6 * out_price_per_mtok
    return {"candidates": n_candidates, "batches": batches, "in_tokens": int(in_tokens),
            "out_tokens": int(out_tokens), "usd_per_night": round(usd, 4)}


def price_fit_preview(n_names: int, in_price_per_mtok: float, out_price_per_mtok: float) -> float:
    """One-off paid preview: one `judge_theme_fit`-shaped call per name (~1.2k in / ~250 out)."""
    return round(n_names * (FIT_CALL_TOKENS[0] / 1e6 * in_price_per_mtok
                            + FIT_CALL_TOKENS[1] / 1e6 * out_price_per_mtok), 4)


def best_other_theme(ties: dict[str, tuple[float | None, str, str]], own_names: set[str],
                     exclude_fading: bool = True) -> tuple[str | None, float | None, str | None]:
    """ties: theme -> (corr | None, reason, stage). The best-reading theme that is not one of the
    name's own homes (and not Fading when exclude_fading). Returns (name, corr, stage)."""
    best: tuple[str | None, float | None, str | None] = (None, None, None)
    for name, (corr, _reason, stage) in ties.items():
        if name in own_names or corr is None:
            continue
        if exclude_fading and stage == "Fading":
            continue
        if best[1] is None or corr > best[1]:
            best = (name, corr, stage)
    return best


def word_regex(ticker: str) -> str:
    """A Postgres regex matching the ticker as a WHOLE word (HUT must not match 'shut')."""
    return r"\m" + re.escape(ticker) + r"\M"


# ═══════════════════════════════════ SELF-TEST (no DB) ═══════════════════════════════════════════

def selftest() -> int:
    fails: list[str] = []

    def check(label: str, got: Any, want: Any) -> None:
        ok = got == want
        print(f"  {'ok ' if ok else 'FAIL'} {label}: got {got!r} want {want!r}")
        if not ok:
            fails.append(label)

    print("pivot stems")
    check("pivoting name", pivot_stems_in("Bitcoin Miners Pivoting to AI/HPC Data Center Hosting"), ["pivot"])
    check("diversifying", pivot_stems_in("Emerging Bitcoin Miners Diversifying into AI/HPC Hosting"), ["diversif"])
    check("none", pivot_stems_in("Crude & Product Tanker Shipping"), [])
    print("leave trigger (g2)")
    check("own thin, other 0.60 -> fires on the unjudgeable arm",
          g2_trigger(None, "thin_basket", 0.60), (True, "own_unjudgeable:thin_basket"))
    check("own 0.20, other 0.60 -> g2 misfiled", g2_trigger(0.20, "comoves", 0.60), (True, "g2_misfiled"))
    check("own 0.20, other 0.38 -> margin not met", g2_trigger(0.20, "below_bar", 0.38), (False, "margin_not_met"))
    check("own 0.80, other 0.60 -> stays", g2_trigger(0.80, "comoves", 0.60), (False, "own_at_or_above_bar"))
    check("other 0.30 -> never", g2_trigger(None, "thin_basket", 0.30), (False, "other_below_bar"))
    print("admission pool")
    check("70.0 passes", in_pool(70.0, 300)[0], True)
    check("69.9 fails", in_pool(69.9, 10)[0], False)
    check("rank 601 fails", in_pool(90.0, 601)[0], False)
    check("no row -> unknown", in_pool(None, None)[0], None)
    print("verdict order")
    base = dict(covered=False, source_theme=None, target_theme="T", target_stage="Mainstream",
                target_corr=0.6, target_reason="comoves", own_corr=None, own_reason=None,
                excluded=False, protected_at_source=False, cooldown_to_target=False,
                seeded_in_window=False, orphan_age=3, pool_ok=False)
    check("orphan 3d -> OFFER", rehome_verdict(**base).verdict, "OFFER")
    check("orphan 15d, no pool, no seed -> REJECT no ticket",
          rehome_verdict(**{**base, "orphan_age": 15}).verdict, "REJECT")
    check("Fading target -> REJECT", rehome_verdict(**{**base, "target_stage": "Fading"}).verdict, "REJECT")
    check("exclusion beats everything", rehome_verdict(**{**base, "excluded": True}).gate.startswith("operator exclusion"), True)
    check("covered, own thin, other 0.6 -> OFFER via covered_g2",
          rehome_verdict(**{**base, "covered": True, "source_theme": "P", "own_reason": "thin_basket"}).ticket,
          "covered_g2[own_unjudgeable:thin_basket]")
    check("covered, own 0.8 -> REJECT (trigger did not fire)",
          rehome_verdict(**{**base, "covered": True, "source_theme": "P", "own_corr": 0.8}).verdict, "REJECT")
    check("thin target -> FALLBACK_SECTOR",
          rehome_verdict(**{**base, "target_corr": None, "target_reason": "thin_basket"}).verdict, "FALLBACK_SECTOR")
    print("board idiom")
    rows = [{"name": "A", "theme_date": date(2026, 10, 1), "stage": "Fading"},
            {"name": "A", "theme_date": date(2026, 10, 2), "stage": "Retired"},
            {"name": "B", "theme_date": date(2026, 9, 20), "stage": "Mainstream"},
            {"name": "C", "theme_date": date(2026, 10, 2), "stage": "Nascent"}]
    check("retired latest drops A; stale B drops; C stays",
          [r["name"] for r in latest_per_name(rows, date(2026, 10, 3))], ["C"])
    print("pricing")
    p = price_candidates(20, 3.0, 15.0, 120)
    check("20 candidates -> 2 batches", p["batches"], 2)
    check("zero -> zero", price_candidates(0, 3.0, 15.0, 120)["usd_per_night"], 0.0)
    check("fit preview 8 names at $3/$15", price_fit_preview(8, 3.0, 15.0), round(8 * (0.0036 + 0.00375), 4))
    print(f"\nselftest: {'PASS' if not fails else 'FAIL'} ({len(fails)} failed)")
    return 1 if fails else 0


# ═══════════════════════════════════ THE PROBE (DB, read-only) ═══════════════════════════════════

def _tie(ticker: str, members: list[str], ctx: Any, comove_verdict) -> tuple[float | None, str, int]:
    """One pair through the engine's own `_comove_verdict`. Returns (corr, reason, basket_n)."""
    cv = comove_verdict(ticker, members, ctx)
    if cv is None:
        return None, "no_context", 0
    return cv.corr, cv.reason, cv.basket_n


def _reference_tie(vec, members: list[str], excess: dict, mac, exclude: str) -> tuple[float | None, int]:
    """SUPPLEMENTARY read against a reference basket with min_members=1 (a reference is a driver
    series, not a candidate group) — NOT the engine's test; labelled as such wherever printed."""
    others = [m for m in members if m != exclude]
    baskets = mac.build_baskets([{"name": "_ref", "stage": "_ref", "tickers": others}], excess,
                                stages=("_ref",), min_members=1)
    if not baskets:
        return None, 0
    corr, _overlap, used = mac.correlate(vec, baskets[0], exclude=exclude, min_members=1)
    return (round(corr, 4) if corr is not None else None), used


async def main() -> int:
    import os
    os.environ.setdefault("APOLLO_CALL_ORIGIN", "probe")   # inside main(), never at import (test_505 lesson)
    from agents.market_intelligence import ep_theme_belonging as etb
    from agents.market_intelligence import market_adjusted_correlation as mac
    from agents.market_intelligence.collector import et_today, prev_trading_days
    from agents.market_intelligence.db import SEEDED_ASSIGN_SOURCES, get_pool, latest_complete_score_date_sql
    from agents.market_intelligence.theme_ecosystems import get_ecosystem_map
    from agents.market_intelligence import theme_engine as te

    # cross-check the probe's constants against the running engine — a drift is a loud stop
    drift = []
    if te.ASSIGN_COMOVE_BAR != COMOVE_BAR:
        drift.append(f"ASSIGN_COMOVE_BAR {te.ASSIGN_COMOVE_BAR}")
    if te.ASSIGN_POOL_RS_FLOOR != POOL_FLOOR or te.ASSIGN_POOL_CEILING != POOL_CEILING:
        drift.append(f"pool {te.ASSIGN_POOL_RS_FLOOR}/{te.ASSIGN_POOL_CEILING}")
    if te.LANE2_WINDOW_TRADING_DAYS != LANE2_WINDOW_TRADING_DAYS:
        drift.append(f"LANE2_WINDOW_TRADING_DAYS {te.LANE2_WINDOW_TRADING_DAYS}")
    if te._ASSIGN_LLM_BATCH_SIZE != ASSIGN_BATCH:
        drift.append(f"_ASSIGN_LLM_BATCH_SIZE {te._ASSIGN_LLM_BATCH_SIZE}")
    if tuple(etb.THEME_BONUS_STAGES) != PAYING_STAGES:
        drift.append(f"THEME_BONUS_STAGES {etb.THEME_BONUS_STAGES}")
    if drift:
        log(f"STOP — probe constants drifted from the running engine: {drift}")
        return 2
    log("constants cross-checked against the running theme_engine / ep_theme_belonging: OK")

    today = et_today()
    before_date = today                     # sessions STRICTLY before today — the engine's own frame
    window_start = te._lane2_window_start(today)   # the engine's own window, not re-derived
    assert window_start == prev_trading_days(LANE2_WINDOW_TRADING_DAYS, from_date=today)[-1]
    eco_map = get_ecosystem_map()
    crypto_ref = list(eco_map.get("E-CRYPTO", {}).get("exemplars") or [])
    aiinfra_ref = list(eco_map.get("E-AIINFRA", {}).get("exemplars") or [])

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            toggles = {(r["safeguard"], r["account_mode"]): r["state"] for r in await conn.fetch("""
                SELECT safeguard, account_mode, state FROM mi_safeguard_state
                WHERE safeguard IN ('theme_birth_gate', 'theme_assign_comove', 'theme_parent_pass',
                                    'lane2_grouping_v2', 'ep_theme_belonging', 'theme_subtheme_arm')""")}
            board_rows = [dict(r) for r in await conn.fetch("""
                SELECT theme_date, name, stage, score, rs_avg, description, tickers, source, parent_theme
                FROM mi_themes WHERE theme_date >= $1 ORDER BY name, theme_date""",
                today - timedelta(days=BOARD_STALE_DAYS))]
            eco_rows = {r["theme_name"]: r["e_code"] for r in await conn.fetch(
                "SELECT theme_name, e_code FROM mi_theme_ecosystems")}
            # every row that ever held a cohort name (last 120 days) — the orphan / churn trail
            member_hist = [dict(r) for r in await conn.fetch("""
                SELECT theme_date, name, stage, source, tickers FROM mi_themes
                WHERE theme_date >= $1 AND tickers && $2::text[] ORDER BY theme_date""",
                today - timedelta(days=120), list(COHORT))]
            retired_recent = [dict(r) for r in await conn.fetch("""
                SELECT DISTINCT ON (name) name, theme_date, stage, description, tickers FROM mi_themes
                WHERE theme_date >= $1 ORDER BY name, theme_date DESC""",
                today - timedelta(days=SWEEP_RETIRED_DAYS))]
            score_rows = {r["ticker"]: dict(r) for r in await conn.fetch(f"""
                SELECT ticker, score_date, rs_composite, rs_1m, rs_3m, rs_6m, rs_rank, sector, close, sma_20
                FROM mi_stock_scores WHERE ticker = ANY($1) AND score_date = {latest_complete_score_date_sql()}""",
                list(COHORT))}
            cached_sectors = {r["ticker"]: r["sector"] for r in await conn.fetch(
                "SELECT ticker, sector FROM mi_ticker_overrides WHERE ticker = ANY($1) AND sector IS NOT NULL",
                list(COHORT))}
            cooldowns = {(r["ticker"], r["theme_name"]) for r in await conn.fetch(
                "SELECT ticker, theme_name FROM mi_validation_cooldowns WHERE NOT bypassed AND cooldown_until > NOW()")}
            protected = {(r["ticker"], r["theme_name"]) for r in await conn.fetch(
                "SELECT ticker, theme_name FROM mi_validation_cooldowns WHERE bypassed")}
            exclusions = {(r["ticker"], r["theme_name"]) for r in await conn.fetch(
                "SELECT ticker, theme_name FROM mi_theme_exclusions")}
            seeded_rows = [dict(r) for r in await conn.fetch("""
                SELECT run_date, source, name, tickers FROM mi_theme_candidates_shadow
                WHERE source = ANY($1::text[]) AND run_date >= $2 AND run_date < $3
                  AND tickers && $4::text[] ORDER BY run_date DESC""",
                list(SEEDED_ASSIGN_SOURCES), window_start, today, list(COHORT))]
            lane_rows_30d = [dict(r) for r in await conn.fetch("""
                SELECT run_date, source, name, tickers FROM mi_theme_candidates_shadow
                WHERE run_date >= $1 AND tickers && $2::text[] ORDER BY run_date DESC""",
                today - timedelta(days=30), list(COHORT))]
            cluster_rows = [dict(r) for r in await conn.fetch("""
                SELECT cluster_date, ticker, member_count, mean_corr FROM mi_correlation_clusters
                WHERE cluster_date >= $1 AND ticker = ANY($2) ORDER BY cluster_date DESC""",
                today - timedelta(days=30), list(COHORT))]
            audit: dict[str, list[dict]] = {}
            audit_since = _utc_now() - timedelta(days=AUDIT_LOOKBACK_DAYS)
            for tk in COHORT:
                audit[tk] = [dict(r) for r in await conn.fetch("""
                    SELECT created_at, event_type, summary FROM mi_audit_log
                    WHERE created_at >= $1 AND (summary ~ $2 OR detail ~ $2)
                    ORDER BY created_at DESC LIMIT 400""", audit_since, word_regex(tk))]
            # the sweep reads retired pivot-worded themes too; a Retired row is a tombstone
            # (tickers=[]), so fetch each such name's last POPULATED row for members + thesis
            live_names_now = {r["name"] for r in latest_per_name(board_rows, today)}
            retired_names = [r["name"] for r in retired_recent
                             if r["stage"] == "Retired" and r["name"] not in live_names_now]
            retired_populated = {r["name"]: dict(r) for r in await conn.fetch("""
                SELECT DISTINCT ON (name) name, theme_date, stage, description, tickers FROM mi_themes
                WHERE name = ANY($1) AND cardinality(tickers) > 0 AND theme_date >= $2
                ORDER BY name, theme_date DESC""", retired_names, today - timedelta(days=90))}
            alerts = [dict(r) for r in await conn.fetch("""
                SELECT alert_date, ticker, ep_score, score_tier, in_active_theme, catalyst
                FROM mi_ep_alerts WHERE alert_date >= $1 AND ticker = ANY($2) ORDER BY alert_date DESC""",
                today - timedelta(days=90), list(COHORT))]
            model_row = await conn.fetchrow("""
                SELECT model, resolved_at FROM mi_model_resolution WHERE role = 'THEME_MODEL'
                ORDER BY resolved_at DESC LIMIT 1""")
            # closes for the co-movement context: board members + cohort + references + SPY
            board = latest_per_name(board_rows, today)
            universe = {tk for t in board for tk in (t["tickers"] or [])} | set(COHORT) \
                | set(crypto_ref) | set(aiinfra_ref) | {mac.MARKET_TICKER}
            closes_rows = await conn.fetch(etb._CLOSES_SQL, sorted(universe),
                                           before_date - timedelta(days=mac.CALENDAR_DAYS_FOR_LOOKBACK),
                                           before_date)

    # ── context, the engine's own construction ─────────────────────────────────────────────────
    closes: dict[str, dict[date, float]] = {}
    for r in closes_rows:
        closes.setdefault(r["ticker"], {})[r["trade_date"]] = float(r["close"])
    sessions = mac.session_index(closes.get(mac.MARKET_TICKER, {}), before_date, mac.BELONGING_LOOKBACK_SESSIONS)
    market = mac.log_returns(closes.get(mac.MARKET_TICKER, {}), sessions)
    excess = mac.excess_returns(closes, sessions, market)
    ctx = te.ComoveContext(before_date=before_date, excess=excess, n_sessions=len(sessions) - 1,
                           n_rows=len(closes_rows))
    log(f"context: {len(excess)} tickers with returns over {ctx.n_sessions} sessions before {before_date} "
        f"({ctx.n_rows} close rows); window {window_start}..{today} for Lane-2 seeds")

    for (sg, mode), state in sorted(toggles.items()):
        emit("toggles", safeguard=sg, account_mode=mode, state=state)
    log("toggles: " + (", ".join(f"{sg}[{m}]={st}" for (sg, m), st in sorted(toggles.items())) or "none stored"))

    by_name = {t["name"]: t for t in board}
    for t in board:
        emit("board_theme", name=t["name"], stage=t["stage"], source=t["source"], n=len(t["tickers"] or []),
             theme_date=t["theme_date"], e_code=eco_rows.get(t["name"]),
             holds_cohort=sorted(set(t["tickers"] or []) & set(COHORT)))
    ai_target = next((n for n in by_name if n == AI_TARGET_HINT), None) or \
        next((n for n in by_name if "ai compute" in n.lower()), None)
    pivot_theme = next((n for n in by_name if n == PIVOT_THEME_HINT), None) or \
        next((n for n in by_name if pivot_stems_in(n) and any(s in n.lower() for s in CRYPTO_NAME_STEMS)), None)
    log(f"board: {len(board)} live themes; AI target = {ai_target!r} "
        f"[{by_name[ai_target]['stage'] if ai_target else '-'}, {len(by_name[ai_target]['tickers'] or []) if ai_target else 0}]; "
        f"pivot/crypto theme = {pivot_theme!r} [{by_name[pivot_theme]['stage'] if pivot_theme else '-'}, "
        f"{len(by_name[pivot_theme]['tickers'] or []) if pivot_theme else 0}]")

    # ── per-name reads ─────────────────────────────────────────────────────────────────────────
    homes = {tk: sorted(t["name"] for t in board if tk in (t["tickers"] or [])) for tk in COHORT}
    seeded_by = defaultdict(list)
    for r in seeded_rows:
        for tk in r["tickers"] or []:
            if tk in COHORT:
                seeded_by[tk].append(f"{r['run_date']} {r['source']} '{r['name']}'")
    last_member: dict[str, tuple[date, str, str] | None] = {}
    for tk in COHORT:
        rows_tk = [r for r in member_hist if tk in (r["tickers"] or []) and r["stage"] != "Retired"]
        last_member[tk] = (rows_tk[-1]["theme_date"], rows_tk[-1]["name"], rows_tk[-1]["stage"]) if rows_tk else None

    n_candidates = 0
    verdicts: list[dict] = []
    for tk in COHORT:
        sc = score_rows.get(tk) or {}
        rs, rank = sc.get("rs_composite"), sc.get("rs_rank")
        sector = sc.get("sector") or cached_sectors.get(tk) or "Unknown"
        pool_ok, pool_why = in_pool(rs, rank)
        covered = bool(homes[tk])
        lm = last_member[tk]
        orphan = None if covered else orphan_age_days(lm[0] if lm else None, today)
        # ties to every live theme through the engine's own verdict (leave-one-out when a member)
        ties: dict[str, tuple[float | None, str, str]] = {}
        for t in board:
            corr, reason, _n = _tie(tk, list(t["tickers"] or []), ctx, te._comove_verdict)
            ties[t["name"]] = (corr, reason, t["stage"])
        own = [(n, ties[n]) for n in homes[tk]]
        own_corr = max((c for n, (c, _r, _s) in own if c is not None), default=None) if own else None
        own_reason = (own[0][1][1] if own else "uncovered")
        if ai_target:
            target_name = ai_target
            target_corr, target_reason, target_stage = ties[ai_target]
        else:
            target_name = target_corr = target_reason = target_stage = None
        pivot_tie = ties.get(pivot_theme) if pivot_theme else None
        best_name, best_corr, best_stage = best_other_theme(ties, set(homes[tk]))
        top3 = sorted(((n, c) for n, (c, _r, _s) in ties.items() if c is not None),
                      key=lambda x: -x[1])[:3]
        vec = excess.get(tk)
        cohort_tie = _reference_tie(vec, list(COHORT), excess, mac, tk) if vec is not None else (None, 0)
        crypto_tie = _reference_tie(vec, crypto_ref, excess, mac, tk) if vec is not None else (None, 0)
        ai_ref_tie = _reference_tie(vec, aiinfra_ref, excess, mac, tk) if vec is not None else (None, 0)
        emit("tie", ticker=tk, ai_target=target_name, ai_target_stage=target_stage, ai_target_corr=target_corr,
             ai_target_reason=target_reason, pivot_theme=pivot_theme,
             pivot_corr=pivot_tie[0] if pivot_tie else None, pivot_reason=pivot_tie[1] if pivot_tie else None,
             own_homes=homes[tk], own_corr=own_corr, own_reason=own_reason,
             best_other=best_name, best_other_corr=best_corr, best_other_stage=best_stage, top3=top3,
             supplementary={"cohort_loo": cohort_tie, "E-CRYPTO_exemplars": crypto_tie,
                            "E-AIINFRA_exemplars": ai_ref_tie,
                            "note": "references use min_members=1 — NOT the engine's test"})
        v = rehome_verdict(
            covered=covered, source_theme=", ".join(homes[tk]) or None, target_theme=target_name,
            target_stage=target_stage, target_corr=target_corr, target_reason=target_reason,
            own_corr=own_corr, own_reason=own_reason,
            excluded=any((tk, h) in exclusions for h in ([target_name] if target_name else [])),
            protected_at_source=any((tk, h) in protected for h in homes[tk]),
            cooldown_to_target=bool(target_name) and (tk, target_name) in cooldowns,
            seeded_in_window=bool(seeded_by.get(tk)), orphan_age=orphan, pool_ok=pool_ok)
        if v.verdict in ("OFFER", "FALLBACK_SECTOR"):
            n_candidates += 1
        tp = today_path(covered=covered, source_themes=homes[tk], seeded_in_window=bool(seeded_by.get(tk)),
                        pool_ok=pool_ok)
        ev = Counter(r["event_type"] for r in audit[tk])
        newest = defaultdict(list)
        for r in audit[tk]:
            if len(newest[r["event_type"]]) < 3:
                newest[r["event_type"]].append(f"{r['created_at']:%m-%d} {r['summary'][:140]}")
        emit("name", ticker=tk, homes=homes[tk], covered=covered, rs_composite=rs, rs_rank=rank, sector=sector,
             score_date=sc.get("score_date"), pool=pool_ok, pool_why=pool_why,
             last_theme=lm, orphan_age_days=orphan, seeded_in_window=seeded_by.get(tk, []),
             lane_rows_30d=[f"{r['run_date']} {r['source']} '{r['name']}'" for r in lane_rows_30d
                            if tk in (r["tickers"] or [])][:8],
             clusters_30d=sum(1 for r in cluster_rows if r["ticker"] == tk),
             cooldowns=sorted(th for (t2, th) in cooldowns if t2 == tk),
             protected=sorted(th for (t2, th) in protected if t2 == tk),
             exclusions=sorted(th for (t2, th) in exclusions if t2 == tk),
             alerts_90d=[(a["alert_date"], a["score_tier"], a["in_active_theme"]) for a in alerts if a["ticker"] == tk][:6])
        emit("audit", ticker=tk, days=AUDIT_LOOKBACK_DAYS, by_event=dict(ev), newest=dict(newest))
        emit("verdict", ticker=tk, today=tp, proposed=v.verdict, gate=v.gate, ticket=v.ticket,
             target=target_name)
        verdicts.append({"ticker": tk, "today": tp, "proposed": v.verdict, "gate": v.gate})
        log(f"{tk:5} homes={homes[tk] or '-'} RS={rs if rs is not None else '-'} rank={rank if rank is not None else '-'} "
            f"sector={sector} pool={pool_ok} seeded={bool(seeded_by.get(tk))} orphan={orphan}d "
            f"| AI target {target_corr if target_corr is not None else target_reason} "
            f"| pivot {pivot_tie[0] if pivot_tie and pivot_tie[0] is not None else (pivot_tie[1] if pivot_tie else '-')} "
            f"| best other {best_name} {best_corr} | cohort-loo {cohort_tie[0]} crypto-ref {crypto_tie[0]} ai-ref {ai_ref_tie[0]}")
        log(f"      today: {tp}")
        log(f"      proposed: {v.verdict} — {v.gate}" + (f" [ticket {v.ticket}]" if v.ticket else ""))
        if ev:
            log(f"      audit {AUDIT_LOOKBACK_DAYS}d: " + ", ".join(f"{k}={n}" for k, n in ev.most_common(8)))

    # ── churn trail: every theme that held a cohort name, 120 days ───────────────────────────
    churn = defaultdict(lambda: {"first": None, "last": None, "stages": Counter(), "members": set()})
    for r in member_hist:
        c = churn[r["name"]]
        c["first"] = c["first"] or r["theme_date"]
        c["last"] = r["theme_date"]
        c["stages"][r["stage"]] += 1
        c["members"] |= set(r["tickers"] or []) & set(COHORT)
    for name, c in sorted(churn.items(), key=lambda kv: kv[1]["first"]):
        emit("churn", name=name, first=c["first"], last=c["last"], stages=dict(c["stages"]),
             cohort_members=sorted(c["members"]), live_tonight=name in by_name)
    log(f"churn: {len(churn)} distinct theme names held a cohort member in the last 120 days "
        f"({sum(1 for n in churn if n in by_name)} live tonight)")

    # ── GENERALIZE: pivot-worded themes and where their members' tape points ─────────────────
    sweep_themes = {t["name"]: t for t in board}
    for name in retired_names:
        last = retired_populated.get(name)
        if last and name not in sweep_themes:
            sweep_themes[name] = {**last, "stage": "Retired"}   # members + thesis from the last populated row
    n_sweep = 0
    for name, t in sweep_themes.items():
        stems = sorted(set(pivot_stems_in(name)) | set(pivot_stems_in(t.get("description"))))
        if not stems:
            continue
        members = list(t.get("tickers") or [])
        per_target: dict[str, list[float]] = defaultdict(list)
        above: dict[str, list[str]] = defaultdict(list)
        for m in members:
            for t2 in board:
                if t2["name"] == name or t2["stage"] == "Fading":
                    continue
                corr, _reason, _n = _tie(m, list(t2["tickers"] or []), ctx, te._comove_verdict)
                if corr is None:
                    continue
                per_target[t2["name"]].append(corr)
                if corr >= COMOVE_BAR:
                    above[t2["name"]].append(m)
        best_t = max(per_target.items(), key=lambda kv: (sum(kv[1]) / len(kv[1]), len(kv[1])), default=None)
        n_sweep += 1
        emit("sweep", theme=name, stage=t.get("stage"), stems=stems, n_members=len(members),
             best_target=best_t[0] if best_t else None,
             best_target_median=(sorted(best_t[1])[len(best_t[1]) // 2] if best_t else None),
             members_at_or_above_bar_to_best=sorted(above[best_t[0]]) if best_t else [],
             description=(t.get("description") or "")[:200])
        log(f"sweep: '{name}' [{t.get('stage')}] stems={stems} n={len(members)} -> best live non-Fading target "
            f"{best_t[0] if best_t else None} ({sorted(above[best_t[0]]) if best_t else []} at/above {COMOVE_BAR})")
    log(f"sweep: {n_sweep} theme(s) carry a pivot stem ({', '.join(PIVOT_STEMS)}) in name or thesis "
        f"(live board + themes retired <= {SWEEP_RETIRED_DAYS}d)")

    # ── pricing from the model prod actually resolves ────────────────────────────────────────
    from shared.llm_models import effective_model, pricing_for
    model_id = (model_row["model"] if model_row else None) or effective_model("THEME_MODEL")
    price = pricing_for(model_id)
    nightly = price_candidates(n_candidates, price["input"], price["output"], len(board))
    preview = price_fit_preview(len(COHORT), price["input"], price["output"])
    emit("pricing", model=model_id, model_source="mi_model_resolution" if model_row else "effective_model",
         per_mtok=price, nightly_incremental=nightly, one_off_fit_preview_usd=preview,
         note="estimate: 18-stock batches, prefix ~45 tok/theme, output 3.5x(274+73.4N)")
    log(f"pricing: THEME_MODEL resolves to {model_id} (${price['input']}/{price['output']} per MTok) — "
        f"{n_candidates} candidate(s) tonight -> {nightly['batches']} extra batch(es) ≈ ${nightly['usd_per_night']}/night; "
        f"one-off fit preview for the 8 names ≈ ${preview}")
    log("stdout: one JSON line per toggle / board theme / name / tie / audit / verdict / churn / sweep / pricing.")
    return 0


def _utc_now() -> datetime:
    """tz-aware now for the TIMESTAMPTZ audit bound (never a naive clock value)."""
    from datetime import timezone
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    import asyncio
    sys.exit(asyncio.run(main()))
