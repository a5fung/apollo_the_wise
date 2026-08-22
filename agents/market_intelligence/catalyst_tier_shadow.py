"""#533 Change 6 — catalyst-tier SHADOW grader (2026-08-22). SHADOW ONLY — THE LINE.

The live catalyst grade (`catalyst_quality`), the tier definitions, `_score_ep`, every
threshold and every floor are UNTOUCHED. This module OBSERVES the live grade after it is
computed and records, per (scan_date, ticker), what a surprise-anchored re-tiering would
have said — into `mi_catalyst_tier_shadow`. Nothing here is read by any grading / entry /
sizing / ordering / safeguard path. Promotion to live is a criterion change: CHANGE_PROCESS
+ operator sign-off.

$0 AT RUNTIME — deterministic, no LLM call anywhere in this module. The only news-magnitude
estimate it consumes is the live grade itself; every other input is a mechanical derivation
(`classify_expectedness` — the #568 expectedness axes, already live in alert_rank_shadow)
or a regex over text the scan already holds.

WHY (evidence: docs/analysis/catalyst_tier_shadow_533_2026-08-22.md +
score_redesign_proposal_533_2026-08-22.md Change 6): the live top tier goes to 42-44% of
ordinary alerts (last-60d live) while at most 1-2 of the 7 graded labelled real EPs got it;
MRNA 2026-08-19 — the operator's canonical textbook EP — graded `strong` and was killed at
score 21.6 on its 10%-gap tick. The prompt anchors the top tier on catalyst FORM ("massive
beat", "FDA approval"), which is near-modal in earnings season, and rule 4 demotes
sector-wide moves — mis-grading the sector-repricing class of real EP.

DESIGN — the two operator corrections (2026-08-22, via coordinator) are load-bearing:

1. CALENDAR IS ONE INPUT, NEVER THE VERDICT. `expct_scheduled` says the DATE was known,
   not that the CONTENT was. A scheduled earnings call with unexpected content is the PEG
   (power earnings gap) class — the operator's own named family — and must NOT be demoted
   for being on the calendar. For a scheduled event, content-surprise evidence =
   beat-vs-consensus language (`expct_beat`) AND forward-changing content
   (`expct_combined_class == 'forward'`, e.g. a guidance change). Both observable at $0.

2. SURPRISE MUST NOT COLLAPSE INTO A PROXY FOR THE SUBJECT'S OWN GAP OR PRICE REACTION —
   that would rebuild the measured failure (gap runs BACKWARDS on real EPs, AUC 0.34).
   `shadow_retier` takes no gap, score or price argument BY CONSTRUCTION (a test pins
   this). The one market-derived input is sector follow-through — OTHER names of the same
   sector on the day's board, i.e. the group's reaction, never the subject's own — and it
   is ⚠ BETA-CONFOUNDED on sector-flood days (on 07-30's 86-name board 42% of names pass
   the confirm; the instrument cannot tell the cause from a passenger). It is therefore
   used ONLY to gate the single promotion lane (already narrowed by unscheduled+forward),
   and its raw inputs (n_same / board_n / share) are recorded per row so any variant can
   be replayed against outcomes later without new data.

3. PRICED-IN RESIDUAL (operator, 2026-08-22: "how much is priced in the moment market
   opens is the question and alpha"): the right frame is news magnitude RELATIVE to the
   move already made. NOT SCORED here — our only news-magnitude estimator is the live
   3-level grade, which is the broken instrument under repair, and n=7 graded real EPs
   cannot calibrate a residual. The table records the residual's raw inputs instead
   (gap at first/last tick, ADV$, rel_volume, projected multiple, both grades) so the
   estimate becomes computable once an honest magnitude axis exists.

THE LATTICE (one-step moves only; missing data can keep a tier, only counter-evidence
moves one — with the single deliberate asymmetry that the TOP tier is a positive claim
and unverifiable content-surprise keeps a scheduled/unscheduled name at `strong`, which
still alerts and keeps its conviction floors; it is a 10-point haircut, not a skip):

  mna           -> mna   (hard filter untouched, out of scope: QURE question is #533-flagged)
  game_changer  -> kept only with content-surprise evidence:
                     scheduled:   beat AND forward   (the PEG signature)
                     unscheduled: forward            (a concrete forward event)
                     unknown calendar: KEPT (fail-open — no lane to judge in)
                   else demoted ONE step to strong.
  strong        -> promoted to game_changer only on unscheduled + forward + sector-confirm
                   (the MRNA class: own concrete unscheduled forward event AND the group
                   repriced with it). Never demoted.
  routine       -> promoted ONE step to strong when the live analysis shows the prompt's
                   sector-momentum demotion fired (rule-4 markers) AND a concrete company
                   event is present in the corpus. Never reaches game_changer directly.

INTRADAY REGRADE: recomputed every scan tick from current inputs (the live re-poll (#347)
updating the cached grade, a corpus change, or the board's sector composition shifting all
flow through); the row upsert keeps first/last verdicts and counts changes
(`regrade_count`) — the MRNA 07:05 grade-pinning failure made observable.

Fail-open: every entry point swallows its own errors (log only) — telemetry must never
jeopardize the scan (same contract as tape_quality / vol_profile annotators).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Module-level for test patchability (the alert_rank_shadow convention — tests patch
# `cts.get_pool` / `cts.get_sectors_batch` directly).
from agents.market_intelligence.db import get_pool, get_sectors_batch  # noqa: E402

SHADOW_TIERS = ("game_changer", "strong", "routine", "mna")

# Rule-4 demotion markers — the live prompt's own vocabulary ("Broad SECTOR-MOMENTUM,
# SHORT-SQUEEZE, or non-company-specific technical moves with no concrete company event
# = routine") as it surfaces in `claude_analysis` prose.
_DEMOTION_MARKER_RE = re.compile(
    r"sector[- ]wide|sector momentum|sector[- ]driven|in sympathy|sympathy (?:move|rally|gap)"
    r"|short[- ]squeeze|no (?:company[- ]specific|specific (?:\w|\s){0,20}(?:catalyst|news))"
    r"|broader (?:sector|market|industry)|rising with (?:the |its )?(?:sector|peers|group)"
    r"|not (?:a )?company[- ]specific|technical (?:move|momentum)",
    re.I)

# Concrete-company-event evidence — a dated SEC stamp in the grounded corpus, or
# event-class words in the analysis/corpus. Deliberately the same vocabulary family the
# #568 keyword axes use; kept separate because this asks a weaker question ("is there ANY
# concrete company event") than _FWD_KW ("is it forward-changing").
_CONCRETE_EVENT_RE = re.compile(
    r"\[SEC (?:8-K|6-K|10-Q|10-K)|\[Benzinga \d{4}-\d{2}-\d{2}\]"
    r"|earnings|quarterly results|guidance|contract|approval|phase (?:1|2|3|i{1,3})"
    r"|trial|acquisition|order (?:worth|valued|of \$)|agreement|partnership|launch",
    re.I)

# Sector-confirm thresholds (declared, round numbers — not fitted): at least 4 OTHER
# same-sector names on the day's crossed board AND at least 30% of the board.
SECTOR_CONFIRM_MIN_N = 4
SECTOR_CONFIRM_MIN_SHARE = 0.30


def detect_demotion_marker(claude_analysis: Optional[str], catalyst: Optional[str]) -> bool:
    """True when the live grade's own prose carries the rule-4 sector/sympathy/no-event
    vocabulary — the observable trace that the prompt's auto-demotion (or the grader's
    no-catalyst skepticism) drove the routine verdict."""
    text = " ".join(t for t in (claude_analysis, catalyst) if t)
    return bool(text) and bool(_DEMOTION_MARKER_RE.search(text))


def detect_concrete_event(claude_analysis: Optional[str], grounded_text: Optional[str]) -> bool:
    """True when the corpus/analysis shows a concrete company event (dated wire/SEC stamp
    or an event-class word) — the counter-evidence that rule 4's 'no concrete company
    event' premise was wrong for this name."""
    text = " ".join(t for t in (claude_analysis, grounded_text) if t)
    return bool(text) and bool(_CONCRETE_EVENT_RE.search(text))


def sector_follow_through(
    sector_by_ticker: dict[str, Optional[str]], ticker: str,
) -> dict[str, Any]:
    """Group-reaction reading for `ticker` against the day's crossed board.

    `sector_by_ticker`: every ticker on today's board (floor-crossers, i.e. the
    candidates list) -> sector string or None. Returns raw counts + the confirm bool.
    Missing sector (either the subject's or sparse board coverage) -> confirm False,
    counts recorded as far as knowable. ⚠ Beta-confounded on sector-flood days — see
    module docstring; consumers must treat `confirm` as corroboration, never proof."""
    sector = sector_by_ticker.get(ticker) or None
    board_n = len(sector_by_ticker)
    if not sector or board_n < 2:
        return {"sector": sector, "sector_n": None, "board_n": board_n,
                "sector_share": None, "sector_confirm": False}
    n_same = sum(1 for t, s in sector_by_ticker.items() if s == sector and t != ticker)
    share = n_same / (board_n - 1)
    return {
        "sector": sector, "sector_n": n_same, "board_n": board_n,
        "sector_share": round(share, 4),
        "sector_confirm": n_same >= SECTOR_CONFIRM_MIN_N and share >= SECTOR_CONFIRM_MIN_SHARE,
    }


def shadow_retier(
    live_quality: str,
    sched: str,
    combined: str,
    beat: bool,
    demotion_marker: bool,
    concrete_event: bool,
    sector_confirm: bool,
) -> tuple[str, str]:
    """The lattice. Returns (shadow_tier, rule_name).

    ⚠ BY CONSTRUCTION this takes no gap / price / score argument — surprise must never
    collapse into a proxy for the subject's own price reaction (operator correction 2,
    2026-08-22; pinned by test_shadow_retier_takes_no_price_input)."""
    if live_quality == "mna":
        return "mna", "mna_passthrough"
    if live_quality == "game_changer":
        if sched == "scheduled":
            if beat and combined == "forward":
                return "game_changer", "gc_kept_scheduled_content_delta"
            return "strong", "gc_demoted_scheduled_no_content_delta"
        if sched == "unscheduled":
            if combined == "forward":
                return "game_changer", "gc_kept_unscheduled_forward"
            return "strong", "gc_demoted_unscheduled_no_forward"
        return "game_changer", "gc_kept_unknown_failopen"
    if live_quality == "strong":
        if sched == "unscheduled" and combined == "forward" and sector_confirm:
            return "game_changer", "strong_promoted_group_repricing"
        return "strong", "strong_unchanged"
    if live_quality == "routine":
        if demotion_marker and concrete_event:
            return "strong", "routine_promoted_demotion_corrective"
        return "routine", "routine_unchanged"
    # Unknown live grade string (defensive): pass through unchanged, visibly.
    return live_quality, "unknown_live_grade_passthrough"


def compute_shadow_verdict(
    *,
    ticker: str,
    live_quality: str,
    claude_analysis: Optional[str],
    grounded_text: Optional[str],
    news_summary: Optional[str],
    sector_by_ticker: dict[str, Optional[str]],
) -> dict[str, Any]:
    """One candidate's full shadow computation: #568 expectedness axes + markers +
    sector follow-through + the lattice. Pure except for the imported classifier
    (itself pure). Returns every input alongside the verdict — the table records the
    inputs so rule variants stay replayable (operator correction 3)."""
    from agents.market_intelligence.alert_rank_shadow import (
        classify_expectedness, combined_expectedness_class)

    cls = classify_expectedness(
        news_summary, None, None, grounded_text, None)
    combined = combined_expectedness_class(cls["looking"])
    demotion = detect_demotion_marker(claude_analysis, news_summary)
    concrete = detect_concrete_event(claude_analysis, grounded_text)
    sect = sector_follow_through(sector_by_ticker, ticker)
    tier, rule = shadow_retier(
        live_quality, cls["sched"], combined, bool(cls["beat"]),
        demotion, concrete, sect["sector_confirm"])
    return {
        "shadow_tier": tier, "rule": rule,
        "expct_sched": cls["sched"], "expct_sched_src": cls["sched_src"],
        "expct_looking": cls["looking"], "expct_combined": combined,
        "expct_beat": bool(cls["beat"]), "expct_growth_yoy": cls["growth"],
        "demotion_marker": demotion, "concrete_event": concrete,
        **sect,
    }


async def record_catalyst_tier_shadow(
    inputs: list[dict[str, Any]],
    board_tickers: list[str],
    scan_date: date,
    now_et: datetime,
) -> int:
    """Batch writer — called fire-and-forget after the scan loop (next to the scan-log
    batch write, same contract: never raises, never blocks the scan). One sector fetch
    for the whole board (mi_ticker_overrides persistent cache via get_sectors_batch),
    then one upsert per graded candidate. Returns rows written (0 on any failure)."""
    if not inputs:
        return 0
    try:
        sector_by_ticker: dict[str, Optional[str]] = {t: None for t in board_tickers}
        try:
            sector_by_ticker.update(await get_sectors_batch(board_tickers) or {})
        except Exception as e:  # sector coverage is best-effort — confirm just reads False
            logger.debug(f"tier shadow: sector batch fetch failed — {e}")
        pool = await get_pool()
        written = 0
        async with pool.acquire() as conn:
            for item in inputs:
                try:
                    v = compute_shadow_verdict(
                        ticker=item["ticker"],
                        live_quality=item["live_quality"],
                        claude_analysis=item.get("claude_analysis"),
                        grounded_text=item.get("grounded_text"),
                        news_summary=item.get("news_summary"),
                        sector_by_ticker=sector_by_ticker,
                    )
                    await conn.execute(
                        _UPSERT_SQL,
                        scan_date, item["ticker"], now_et,
                        item["live_quality"], v["shadow_tier"], v["rule"],
                        v["expct_sched"], v["expct_sched_src"], v["expct_looking"],
                        v["expct_combined"], v["expct_beat"], v["expct_growth_yoy"],
                        v["demotion_marker"], v["concrete_event"],
                        v["sector"], v["sector_n"], v["board_n"], v["sector_share"],
                        v["sector_confirm"],
                        item.get("gap_pct"), item.get("adv_dollar"),
                        item.get("rel_volume"), item.get("projected_vol_multiple"),
                        item.get("ep_score"), item.get("live_tier"),
                        len(item.get("grounded_text") or ""),
                    )
                    written += 1
                except Exception as e:
                    logger.warning(f"tier shadow: row failed for {item.get('ticker')}: {e}")
        return written
    except Exception as e:
        logger.warning(f"tier shadow: batch write failed — {e}")
        return 0


# first_* columns are written once (INSERT); last_* refresh every tick; regrade_count
# increments only when the shadow tier actually changes — the grade-pinning failure
# (MRNA 07:05) made countable.
_UPSERT_SQL = """
    INSERT INTO mi_catalyst_tier_shadow (
        scan_date, ticker, first_seen_et, last_seen_et,
        live_quality_first, live_quality_last,
        shadow_tier_first, shadow_tier_last, rule_first, rule_last, regrade_count,
        expct_sched, expct_sched_src, expct_looking, expct_combined,
        expct_beat, expct_growth_yoy, demotion_marker, concrete_event,
        sector, sector_n, board_n, sector_share, sector_confirm,
        gap_pct_first, gap_pct_last, adv_dollar, rel_volume,
        projected_vol_multiple, live_ep_score, live_tier, grounded_len
    ) VALUES (
        $1,$2,$3,$3, $4,$4, $5,$5,$6,$6, 0,
        $7,$8,$9,$10, $11,$12,$13,$14,
        $15,$16,$17,$18,$19,
        $20,$20,$21,$22,$23,$24,$25,$26
    )
    ON CONFLICT (scan_date, ticker) DO UPDATE SET
        last_seen_et       = EXCLUDED.last_seen_et,
        live_quality_last  = EXCLUDED.live_quality_last,
        shadow_tier_last   = EXCLUDED.shadow_tier_last,
        rule_last          = EXCLUDED.rule_last,
        regrade_count      = mi_catalyst_tier_shadow.regrade_count
                             + CASE WHEN mi_catalyst_tier_shadow.shadow_tier_last
                                         IS DISTINCT FROM EXCLUDED.shadow_tier_last
                                    THEN 1 ELSE 0 END,
        expct_sched        = EXCLUDED.expct_sched,
        expct_sched_src    = EXCLUDED.expct_sched_src,
        expct_looking      = EXCLUDED.expct_looking,
        expct_combined     = EXCLUDED.expct_combined,
        expct_beat         = EXCLUDED.expct_beat,
        expct_growth_yoy   = EXCLUDED.expct_growth_yoy,
        demotion_marker    = EXCLUDED.demotion_marker,
        concrete_event     = EXCLUDED.concrete_event,
        sector             = EXCLUDED.sector,
        sector_n           = EXCLUDED.sector_n,
        board_n            = EXCLUDED.board_n,
        sector_share       = EXCLUDED.sector_share,
        sector_confirm     = EXCLUDED.sector_confirm,
        gap_pct_last       = EXCLUDED.gap_pct_last,
        adv_dollar         = EXCLUDED.adv_dollar,
        rel_volume         = EXCLUDED.rel_volume,
        projected_vol_multiple = EXCLUDED.projected_vol_multiple,
        live_ep_score      = EXCLUDED.live_ep_score,
        live_tier          = EXCLUDED.live_tier,
        grounded_len       = EXCLUDED.grounded_len
"""
