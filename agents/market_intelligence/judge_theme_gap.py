"""Judge → narrative-radar feed for the theme-detection coverage gap (#322).

THE GAP (JBL 6/17, ADR 0011 addendum): the Holistic Grade Judge inferred an AI-infra
theme for JBL that NEITHER theme lane tracked:
  • Lane 1 (price-action clustering, theme_engine.py) needs price/RS CORRELATION with
    an EXISTING cluster — a diversified name whose AI-infra exposure is one line of
    business among several never correlates strongly enough to join a cluster.
  • Lane 2 (narrative tracking) has TWO sub-lanes, and BOTH structurally require a
    MULTI-TICKER cohort the same day/window: `discover_narrative_themes` (#167 same-
    day co-gap, theme_engine.py) drops any story shared by fewer than 2 of the day's
    alerts (`len(cand) < 2` skips the whole pass; a kept theme needs `len(tks) >= 2`);
    `run_theme_synthesis` (#240 cross-ticker RS-slope, theme_synthesis.py) requires
    `_MIN_MEMBERS = 3` coordinated movers before it will propose a cohort at all.
  • The S2/S3 coverage_probe (2026-07-13, coverage_probe.py) DOES probe single-name
    blind spots, but its confirmation bar needs a P1 NAMED-ENTITY hit (a peer
    company's name literally appearing in the alert's own grounded_text) AND P3
    co-movement AND cross-session persistence — it independently RE-DISCOVERS a
    cohort, by design never reading the judge's fire_axes as anything but a
    read-only calibration column. A judge inference that names no peer at all (a
    pure world-knowledge company classification — "Jabil assembles AI server
    racks") scores P1=0 and never confirms there either.

So a SINGLE name whose thematic tie is a semantic/world-knowledge classification,
with no co-occurring peer that day and no pre-existing price-correlated cluster, is
invisible to every existing lane. Only the judge — reading the grounded catalyst text
with open-ended reasoning, explicitly instructed to weigh theme as the #1 Pradeep
catalyst axis (`ep_grade_judge._RUBRIC`) — can make that leap. Today the judge's
`fire_axes` records ONLY *that* a theme/narrative axis lit, never WHICH theme or WHY:
the actual theme name lives only in the free-text `judge_rationale`, parsed by
nothing, surfaced only on the alert's "judge-inferred (not a tracked cohort)" display
line (ADR 0011 addendum). It never becomes a trackable candidate, so the SAME company
hits the SAME blind spot forever, and the next JBL never benefits from this one.

THE FEED (this module): when the judge lights `fire_axes` on theme/narrative for a
ticker BOTH lanes structurally missed (`in_active_theme=False` AND
`in_narrative_cohort=False` — the exact two booleans the judge itself was fed),
write a stub candidate into the SAME `mi_theme_candidates_shadow` table the
narrative radar reads, tagged `source='judge_inferred'`. Same-sector/same-day fires
merge (ticker-set union, `db.upsert_judge_theme_gap_candidate`) into one cohort —
so if 2+ judge-flagged names share a sector on the SAME DAY, they land as a single
multi-member candidate. A single judge fire writes a ONE-member row: below
`theme_engine._PROMOTE_MIN_MEMBERS` (3), the same floor `promote_shadow_themes` AND
the operator's own `/promotetheme` enforce (`too_few` status) — so a lone
JBL-class row is visible + reviewable immediately but NOT `/promotetheme`-able.

NO CROSS-DAY ACCRUAL (unlike coverage_probe, which anchors its stub name on a
STABLE persistence-window anchor date): `build_gap_name` embeds the ALERT date
itself, so `ON CONFLICT (run_date, name)` can only merge fires on the exact SAME
calendar day — a repeat judge fire on the SAME ticker/sector on a LATER day writes
a SEPARATE 1-member row under a different name, it never unions into the earlier
one. A lone judge inference is therefore a PERMANENT reviewable 1-member row for
the operator's own judgment (manually build/rename a cohort, or just watch it
recur) — not something that "accrues toward" the promote bar on its own. Only a
same-day, same-sector CLUSTER of 3+ judge fires promotes without operator help.

KNOWN COARSE-PROXY LIMITATION: `is_theme_gap` checks the two MEMBERSHIP BOOLEANS
(`in_active_theme`, `in_narrative_cohort`), not "does either lane track the
STORY at all." A judge NEW-JOINER fire — matching an ALREADY-active Lane-2
narrative the ticker isn't a listed member of yet (the RCAT 5/28 class documented
in `ep_grade_judge.assemble_judge_inputs`'s `active_narratives` docstring) — also
has `in_narrative_cohort=False` and will write a `judge_inferred` row here even
though Lane 2 already has the story. That's an acceptable over-capture for a
surface-only, non-auto-promoted shadow feed (worst case: a redundant reviewable
row, never a live-theme or judge-input mutation) — not attempted to disambiguate
here (would need re-fetching + fuzzy-matching `active_narratives`, a heavier
lift than this feed's scope).

ANTI-CIRCULARITY (mirrors coverage_probe's walls — the judge must never be able to
corroborate itself):
  • Source wall — `source='judge_inferred'` is NOT in `db.AUTO_PROMOTE_THEME_SOURCES`
    (the nightly auto-promote can never graduate it into live `mi_themes`) and is NOT
    matched by `get_narrative_theme_candidates`'s source filter, so it can NEVER
    re-enter the judge's own `active_narratives` input on a future call — a judge
    inference must never become the judge's own corroborating evidence. It surfaces
    ONLY via the full-lane reader (`get_shadow_theme_candidates(include_probe=True)`
    — /themes, /promotetheme), exactly like coverage_probe.
  • No new grade authority — this module is pure record-keeping. It runs AFTER the
    judge's DB write has already succeeded (ep_detector.py::_judge_shadow), touches
    no grade/tier/alert field, and any failure is swallowed to an audit event — it
    can never disturb the judge write or the alert path (SHADOW invariant).
  • Deterministic naming — the stub name is built from data already on the alert row
    (sector + alert date), never parsed out of the judge's free-text rationale, so a
    malformed/hallucinated theme name can never reach the shared candidate table.
    The rationale itself (where "AI-infra" actually lives) is preserved verbatim as
    the thesis — the one place that prose is kept instead of discarded.
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.db import log_audit_event, upsert_judge_theme_gap_candidate

logger = logging.getLogger(__name__)

_MAX_NAME_LEN = 80
_MAX_THESIS_LEN = 400
_LIT_AXES = ("theme", "narrative")


def is_theme_gap(
    fire_axes: "list[str] | None", in_active_theme: bool, in_narrative_cohort: bool,
) -> bool:
    """True when the judge lit the theme/narrative axis for a ticker NEITHER lane
    tracks — the exact JBL-class gap (#322). `fire_axes=None` (the judge omitted it,
    or the call fell back/failed-open) never counts as a gap — only an EXPLICIT
    theme/narrative fire is real signal, never an absence. Already-tracked tickers
    (either lane True) are excluded too: that's a credit question (#328/#329), not a
    detection gap — this module is detection-coverage-only. COARSE PROXY (see the
    module docstring's "KNOWN COARSE-PROXY LIMITATION"): checks the membership
    BOOLEANS, not whether either lane tracks the underlying STORY — a new-joiner
    fire on an already-active Lane-2 narrative also reads as a gap here. Acceptable
    for a surface-only, never-auto-promoted shadow feed."""
    if not fire_axes:
        return False
    if in_active_theme or in_narrative_cohort:
        return False
    return any(a in _LIT_AXES for a in fire_axes)


def build_gap_name(sector: "str | None", alert_date: Any) -> str:
    """Deterministic stub name — sector + alert date, never parsed from the judge's
    free-text rationale (mirrors coverage_probe.build_stub_name's discipline). Two
    same-sector fires on the SAME calendar day collapse to the SAME name, so the DB
    upsert's ticker-set union merges them into one multi-member candidate (fires on
    a LATER day get a different name — no cross-day merge, see the module docstring's
    "NO CROSS-DAY ACCRUAL"). CAVEAT: an unknown/missing sector falls back to the
    generic "Uncovered" label, so two UNRELATED same-day judge fires with no sector
    data would merge into one meaningless "Uncovered" cohort — accepted (mirrors
    coverage_probe's own unknown-sector fallback), surfaced for operator awareness,
    not fixed here."""
    label = (sector or "Uncovered").strip() or "Uncovered"
    ad = alert_date.isoformat() if hasattr(alert_date, "isoformat") else str(alert_date)
    return f"Judge: {label} {ad}"[:_MAX_NAME_LEN]


def build_gap_thesis(ticker: str, rationale: "str | None") -> str:
    """Thesis = the judge's OWN rationale verbatim (truncated) — the one place the
    actual theme story ("AI-infra") is preserved rather than discarded — prefixed
    with the subject ticker for standalone readability in /themes."""
    r = (rationale or "").strip() or "(no rationale recorded)"
    return f"Judge-inferred theme gap ({ticker}): {r}"[:_MAX_THESIS_LEN]


async def feed_judge_theme_gap(
    conn: Any,
    ticker: "str | None",
    alert_date: Any,
    *,
    sector: "str | None",
    fire_axes: "list[str] | None",
    in_active_theme: bool,
    in_narrative_cohort: bool,
    rationale: "str | None",
) -> "str | None":
    """Write ONE judge-inferred candidate row when `is_theme_gap` fires. Returns the
    candidate name written, or None when the predicate doesn't fire (not a gap) or
    `ticker`/`alert_date` is missing. The caller (ep_detector.py::_judge_shadow) wraps
    this in its own try/except — a feed failure must never disturb the judge write or
    the alert path (SHADOW invariant, same discipline as coverage_probe)."""
    if not ticker or alert_date is None:
        return None
    if not is_theme_gap(fire_axes, in_active_theme, in_narrative_cohort):
        return None
    tk = ticker.upper()
    name = build_gap_name(sector, alert_date)
    thesis = build_gap_thesis(tk, rationale)
    await upsert_judge_theme_gap_candidate(conn, alert_date, name, [tk], thesis)
    await log_audit_event(
        "judge_theme_gap_candidate_written",
        f"{name}: {tk} — judge fire_axes={fire_axes}, neither lane tracked "
        f"(surface-only; source='judge_inferred'; visible now via /themes; "
        f"needs 3+ merged members before /promotetheme will accept it)",
    )
    return name
