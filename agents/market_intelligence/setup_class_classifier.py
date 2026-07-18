"""C1 — the deterministic setup-class classifier (#332, ADR 0028 §2).

PURPOSE (P0 — TAG VISIBILITY ONLY, ZERO GRADE MUTATION — THE LINE). Tags each scored EP
candidate with ONE of 4 classes so every downstream readout (the judge DecisionContext, the
weekly review, a future P1 calibration replay) becomes class-splittable immediately:

  `classify_setup_class(candidate) ->
      'pradeep_explosive' | 'mature_leader' | 'episodic_neglect' | 'unclassified'`

THE CLOSED SPEC (operator-signed 2026-07-18 — build EXACTLY this; ADR 0028 §2 pinned the
2 previously-open predicates the same day, see the ADR's §7 F4 resolution):
  - `pradeep_explosive`: mcap < $2B AND (RVOL >= 3 OR 9M-print same-day OR sugar-baby cohort)
  - `mature_leader`:     mcap >= $10B OR (Stage-2 AND price >= 0.75*52w_high AND
                         ADV_20_dollar >= $100M)   — ADV-large = $100M/day dollar volume
  - `episodic_neglect`:  $2B <= mcap < $10B AND price < 0.70*52w_high AND upgrades_30d == 0
                         — low-coverage = "no recent upgrade" (upgrade RECENCY, not analyst
                         coverage BREADTH — the ADR's F4 fork named this ambiguity explicitly)
  - `unclassified`:      anything else / missing fields -> uniform baseline, never penalized

This module owns ONLY the pure classifier (`classify_setup_class`, zero I/O, testable in
total isolation) + the async field-assembler (`compute_setup_class_fields`, the ONE place that
gathers the extra as-of DB lookups the pure function needs). It reads `r`/`conn` READ-ONLY and
returns plain values — it never writes anything itself (the caller in `ep_detector.py` persists
the returned tag via `db.update_ep_alert_setup_class`), never mutates a grade/tier column, and
never imports anything from the live judge-prompt-building path. Mirrors the axis-shadow
modules' discipline (`structure_axis_shadow.py` / `theme_axis_shadow.py`) even though this is
not a shadow table — same "pure compute, as-of, never guess" shape.

Field provenance (lookahead honesty, ADR 0028 §2): every field this classifies on is either
already threaded onto the candidate row `r` at DETECTION time (`market_cap`, `rel_volume`,
`current_price`, `week52_high`, `upgrades_30d` — see `ep_detector.py`'s `result` dict) or
computed AS-OF strictly prior to `alert_date` here (`stage2` via `get_daily_bars_asof` /
`compute_structure_features`; `adv_20_dollar` via a ticker-scoped, strictly-prior median query).
The caller persists ONLY the resulting class string onto `mi_ep_alerts.setup_class` — a future
P1 calibration replay reads that stored string directly, never re-derives it from re-fetched
current data. A historical row with `setup_class IS NULL` (pre-C1, or a classify failure) reads
as `unclassified` by definition — never backfilled.

Class-overlap tie-break (documented v1 implementation call, not silently invented — mirrors
`structure_axis_shadow.py`'s own disclosure style for its near-miss band): `mature_leader`'s
2nd path (`Stage-2 AND ...`) carries NO market-cap floor of its own, so a sub-$2B name could in
principle satisfy BOTH `pradeep_explosive`'s OR-condition AND that path in the same tick (e.g.
a small, heavily-traded Stage-2 name near its highs that also gaps hard same-day). The ADR §2
table lists the classes in this exact order — `pradeep_explosive`, `mature_leader`,
`episodic_neglect` — and this function evaluates them in that literal order, first-match-wins
(the same convention `agent.py::execute_task`'s routing cascade already uses for its own
first-match-wins ambiguity). No other overlap is possible: the mcap cuts for
`pradeep_explosive` (`< $2B`), `episodic_neglect` (`$2B..$10B`), and `mature_leader`'s 1st path
(`>= $10B`) already partition the mcap axis cleanly, and `mature_leader`'s 2nd path requires
`price >= 0.75*52w_high` while `episodic_neglect` requires `price < 0.70*52w_high` — mutually
exclusive on price, so those two never collide.
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.db import (
    get_9m_alert_same_day,
    get_adv_20_dollar_asof,
    get_daily_bars_asof,
    get_sugar_baby_cohort_member_asof,
)
from agents.market_intelligence.structure_axis_shadow import compute_structure_features

logger = logging.getLogger(__name__)

# ── Thresholds — operator-signed 2026-07-18 (ADR 0028 §2, F4-resolved) ──────────────────────
MCAP_PRADEEP_MAX = 2_000_000_000        # pradeep_explosive: mcap < $2B
MCAP_MATURE_MIN = 10_000_000_000        # mature_leader path 1: mcap >= $10B
RVOL_EXPLOSIVE_MIN = 3.0                # pradeep_explosive: RVOL >= 3x
MATURE_NEAR_HIGH_MIN = 0.75             # mature_leader path 2: price >= 75% of 52w high
MATURE_ADV_DOLLAR_MIN = 100_000_000     # ADV-large = ADV_20_dollar >= $100M/day
NEGLECT_MAX_PCT_OF_HIGH = 0.70          # episodic_neglect: price < 70% of 52w high
NEGLECT_MAX_UPGRADES = 0                # low-coverage = upgrades_30d == 0 (exact)

CLASS_PRADEEP_EXPLOSIVE = "pradeep_explosive"
CLASS_MATURE_LEADER = "mature_leader"
CLASS_EPISODIC_NEGLECT = "episodic_neglect"
CLASS_UNCLASSIFIED = "unclassified"

ALL_CLASSES = (
    CLASS_PRADEEP_EXPLOSIVE, CLASS_MATURE_LEADER, CLASS_EPISODIC_NEGLECT, CLASS_UNCLASSIFIED,
)


def classify_setup_class(candidate: dict[str, Any]) -> str:
    """Pure, deterministic, zero I/O. `candidate` keys read (all optional — any missing/None
    value simply fails to match the class(es) that need it, never raises, never guesses):
      market_cap, rvol, is_9m_same_day, is_sugar_baby_cohort, stage2, price, week52_high,
      adv_20_dollar, upgrades_30d.

    `market_cap is None` short-circuits straight to 'unclassified' — every one of the 3 named
    classes needs it (either directly, or via the OR-branch that skips it needs it as the outer
    gate), so an unclassifiable candidate is never partially/spuriously matched."""
    mcap = candidate.get("market_cap")
    if mcap is None:
        return CLASS_UNCLASSIFIED

    price = candidate.get("price")
    week52_high = candidate.get("week52_high")

    # ── pradeep_explosive: mcap < $2B AND (RVOL>=3 OR 9M-same-day OR sugar-baby cohort) ─────
    if mcap < MCAP_PRADEEP_MAX:
        rvol = candidate.get("rvol")
        rvol_hit = rvol is not None and rvol >= RVOL_EXPLOSIVE_MIN
        if rvol_hit or candidate.get("is_9m_same_day") or candidate.get("is_sugar_baby_cohort"):
            return CLASS_PRADEEP_EXPLOSIVE

    # ── mature_leader: mcap >= $10B OR (Stage-2 AND price>=75%*52w_high AND ADV>=$100M) ─────
    if mcap >= MCAP_MATURE_MIN:
        return CLASS_MATURE_LEADER
    adv_20_dollar = candidate.get("adv_20_dollar")
    if (
        candidate.get("stage2") is True
        and price is not None and week52_high is not None and week52_high > 0
        and price >= MATURE_NEAR_HIGH_MIN * week52_high
        and adv_20_dollar is not None and adv_20_dollar >= MATURE_ADV_DOLLAR_MIN
    ):
        return CLASS_MATURE_LEADER

    # ── episodic_neglect: $2B<=mcap<$10B AND price<70%*52w_high AND upgrades_30d==0 ─────────
    upgrades_30d = candidate.get("upgrades_30d")
    if (
        MCAP_PRADEEP_MAX <= mcap < MCAP_MATURE_MIN
        and price is not None and week52_high is not None and week52_high > 0
        and price < NEGLECT_MAX_PCT_OF_HIGH * week52_high
        and upgrades_30d is not None and upgrades_30d == NEGLECT_MAX_UPGRADES
    ):
        return CLASS_EPISODIC_NEGLECT

    return CLASS_UNCLASSIFIED


async def compute_setup_class_fields(conn: Any, r: dict[str, Any]) -> dict[str, Any]:
    """Assemble the field dict `classify_setup_class` needs, from `r` (already threaded at
    detection: `market_cap`, `rel_volume`, `current_price`, `week52_high`, `upgrades_30d` — see
    `ep_detector.py`'s `result` dict) plus 3 as-of DB lookups this module owns: Stage-2 (REUSED
    from `structure_axis_shadow.compute_structure_features` — never reimplemented), same-day 9M
    print, and as-of sugar-baby cohort membership, plus the ticker-scoped ADV-dollar primitive.

    Each DB lookup is INDEPENDENTLY try/except-guarded: one lookup failing (e.g. a transient
    sugar-baby query hiccup) must never blank the fields a DIFFERENT lookup — or a field
    already resolved on `r` — already answered (e.g. mcap alone can decide `mature_leader`'s
    `>= $10B` path regardless of whether the 9M/sugar-baby lookups succeeded). Read-only;
    never mutates `r` or any grade column (THE LINE)."""
    fields: dict[str, Any] = {
        "market_cap": r.get("market_cap"),
        "rvol": r.get("rel_volume"),
        "price": r.get("current_price"),
        "week52_high": r.get("week52_high"),
        "upgrades_30d": r.get("upgrades_30d"),
        "stage2": None,
        "is_9m_same_day": False,
        "is_sugar_baby_cohort": False,
        "adv_20_dollar": None,
    }
    ticker = r.get("ticker")
    alert_date = r.get("alert_date")
    if not ticker or not alert_date:
        return fields

    try:
        bars = await get_daily_bars_asof(conn, ticker, alert_date)
        fields["stage2"] = compute_structure_features(bars, alert_date)["stage2"]
    except Exception as e:
        logger.debug(f"setup_class stage2 lookup failed for {ticker}: {e}")

    try:
        fields["is_9m_same_day"] = await get_9m_alert_same_day(conn, ticker, alert_date)
    except Exception as e:
        logger.debug(f"setup_class 9m-same-day lookup failed for {ticker}: {e}")

    try:
        fields["is_sugar_baby_cohort"] = await get_sugar_baby_cohort_member_asof(
            conn, ticker, alert_date)
    except Exception as e:
        logger.debug(f"setup_class sugar-baby lookup failed for {ticker}: {e}")

    try:
        price = fields["price"]
        if price:
            fields["adv_20_dollar"] = await get_adv_20_dollar_asof(conn, ticker, alert_date, price)
    except Exception as e:
        logger.debug(f"setup_class adv_20 lookup failed for {ticker}: {e}")

    return fields
