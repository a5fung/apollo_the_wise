"""Output-token ceilings (`max_tokens`) for every LLM call site — ONE registry.

WHY THIS EXISTS (2026-08-09, follow-up to #543). Two callers (`postmortem`,
`system_review_weekly`) silently truncated the first time their auto-tracked role
moved to claude-sonnet-5 — every prior sonnet-4-6 call had completed cleanly. The
root class: ~24 hardcoded `max_tokens` numbers scattered across agents/, core/ and
channels/, each sized against whatever model the role ran when the number was
typed, none of them revisited when the model resolver (opt-all-in, 2026-07-31)
moved the role. A ceiling does not fail loudly when it rots — the response is cut
mid-JSON and reads downstream as an empty result.

WHY THE VALUES ARE STILL HAND-SET, NOT AUTO-DERIVED (measured 2026-08-09 against
prod `api_usage`, 6,634 rows; capture in the 08-09 session commit):

  * Auto-derivation ("trailing percentile of completed outputs x headroom") was
    the design intent and the DATA REFUSED IT. Truncated samples are censored AT
    the cap: for every (caller, model) pair that actually needed a new number,
    100% of the new-model samples were at-cap (postmortem 2/2 @800,
    system_review 1/1 @1200, theme_discovery 8/8 @4000, theme_advisor 149/151
    @600) — the completed-output percentile is undefined on zero completed
    samples, exactly when it is needed.
  * No headroom multiple is derivable either. Cross-model growth of completed
    outputs is caller-shaped: ~1.0x for forced-tool/schema-bounded callers
    (judge_divergence 464->475, mgmt_judge 194->202, theme_validation 293->272)
    but >=2.7x for freeform-prose callers (catalyst_metrics_extractor p50
    557->1484, and its true growth is UNKNOWN because the samples were censored
    again at the old 2000 cap). Even the 2.5x patch rule would have re-truncated
    that caller (2.5 x 720 = 1800 < 2000). Any single multiple is picked, not
    derived — the event that invalidates a ceiling (model change) is precisely
    the event after which no completed data exists yet.

  So the durable fix is DETECTION wired to the invalidating event, with the
  numbers auditable in one place:
    1. this registry — every ceiling with the model it was sized on + evidence;
    2. spend_tracker fires a LIVE alarm the moment any logged response reports
       stop_reason='max_tokens' (detection latency: seconds, was next-nightly);
    3. model_resolution's boot recorder names the callers whose ceilings were
       sized on the outgoing model whenever a role's model changes;
    4. cost_board's nightly check adds a NEAR-CEILING arm (completed output >=
       NEAR_CEILING_FRACTION of the registry cap) so drift is seen before the
       first cut;
    5. a build gate (tests/test_output_ceilings.py) refuses new hardcoded
       max_tokens literals in agents/ core/ channels/ — new callers register.

COST OF GENEROSITY: max_tokens bills only tokens actually generated — an
over-provisioned ceiling on a completing caller costs $0. The worst case is a
runaway single call: cap x output-price (8000 on sonnet-5 = ~$0.12; the cost
watchdog catches repetition). Hence caps here err high, bounded by HARD_CAP.

Update discipline: change a value HERE (same commit as any evidence), never at
the call site. `sized_on` = the model id the number was sized against; when the
role's model changes, the boot recorder will flag the entry until re-evidenced.
"""
from __future__ import annotations

from typing import NamedTuple


class OutputCeiling(NamedTuple):
    max_tokens: int
    role: str | None   # shared.llm_models role constant name (None = untracked model)
    sized_on: str      # model id the number was sized against
    evidence: str      # one-line provenance (api_usage measurement, date)


# Ceiling on the ceiling: above ~16K output the SDK requires streaming to avoid
# HTTP timeouts (a technical boundary, not a taste) — nothing here may exceed it.
HARD_CAP = 16000

# Near-ceiling nightly threshold (cost_board). Derived from the 2026-08-09
# measurement: every currently-HEALTHY caller's max completed output sits at
# <=86% of its cap (orchestrator 3517/4096), while every caller later caught
# truncating passed through >=95% first. 0.90 sits strictly above all healthy
# traffic (cannot cry wolf on day one) and below the observed pre-failure zone.
NEAR_CEILING_FRACTION = 0.90

# Callers whose truncation is DELIBERATE — liveness pings that request a tiny
# max_tokens and discard the text. Consumed by cost_board's nightly check AND
# spend_tracker's live alarm. Keep SHORT and justified per entry.
TRUNCATION_BY_DESIGN = frozenset({
    "healthcheck",        # orchestrator Anthropic liveness ping: max_tokens=5, text unused
    "perplexity_health",  # collector Perplexity liveness ping: max_tokens=5, text unused
})


_ADVISOR = OutputCeiling(
    1500, "THEME_ADVISOR_MODEL", "claude-opus-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
    "RAISED 2026-08-09 from 600: 149/151 opus-4-8 calls censored at exactly 600 "
    "(silently truncating since June); largest genuinely completed 599 -> 2.5x ~ 1500. "
    "No completed opus-5 sample yet — PROVISIONAL.",
)

# One shared judge-transport ceiling: ep_grade_judge.grade_holistic passes it, and
# judge_divergence + the robustness eval ride grade_holistic with a model swap only.
_JUDGE = OutputCeiling(
    1500, "JUDGE_MODEL", "claude-opus-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
    "2026-08-07 raise from transport-default 500 (#543): 79/404 opus-4-8 and 7/49 "
    "opus-5 calls censored at 500; two truncated verdicts had promoted to HIGH.",
)

CEILINGS: dict[str, OutputCeiling] = {
    # ── graders / judges (pre-open path — registry is a static import, no DB read) ──
    "ep_catalyst_grade": OutputCeiling(
        1500, "GROUNDED_GRADE_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-07 raise from 300 (#543): 38/78 sonnet-5 calls censored at 300."),
    "ep_grade_judge": _JUDGE,
    "judge_divergence": _JUDGE._replace(
        role="JUDGE_DIVERGENCE_MODEL",
        evidence="Rides ep_grade_judge.grade_holistic (model-swapped twin); max completed "
                 "475 on sonnet-5 — the old 500 default left a 5% margin."),
    "judge_robustness_eval": _JUDGE._replace(
        evidence="scripts/evals harness — rides grade_holistic. ⚠ The 2026-08-03 opus-5 "
                 "eval ran pre-raise: all 144 calls at exactly 500 (censored)."),
    "mgmt_judge": OutputCeiling(
        500, "JUDGE_MODEL", "claude-opus-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "Max completed 202 on opus-5, 194 on opus-4-8 (40% of cap); ~1.0x model growth."),

    # ── catalyst pipeline ──
    "catalyst_materiality": OutputCeiling(
        200, "MATERIALITY_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "n=1 sonnet-5 completed at 68 (34% of cap); JSON-only contract."),
    "catalyst_type_classifier": OutputCeiling(
        220, "CATALYST_TYPE_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "100 haiku calls, max completed 164 (75% of cap)."),
    "catalyst_metrics_extractor": OutputCeiling(
        8000, "METRICS_EXTRACTION_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-07 raise from 2000 (PLAN #542): sonnet-5 p50 1484 vs 557 on 4-6 "
        "(>=2.7x model growth), 3 calls censored at 2000. No post-raise sample yet."),

    # ── theme engine ──
    # 2026-08-10: the four truncating theme callers were fixed by BOUNDING THE
    # OUTPUT BY CONSTRUCTION (input batching / forced-tool transport), not by
    # raising these values — the 08-07 raises pegged again within days, proving
    # the caps were never the constraint. Derivations + diagnosis per caller:
    # theme_engine.py at _ASSIGN_LLM_BATCH_SIZE / _DISCOVERY_LLM_BATCH_STOCKS /
    # _LANE2_NARRATIVE_TOOL, and docs/architecture/theme_engine.md 2026-08-10.
    # Do NOT raise theme_assignment / theme_discovery / theme_split /
    # narrative_theme_discovery again for at-cap pressure — fix the demand.
    "narrative_theme_discovery": OutputCeiling(
        1500, "THEME_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "WATCH: sonnet-5 max completed 1249 (83% of cap) vs 355 on 4-6 — 3.5x model "
        "growth; the near-ceiling arm is expected to fire here first."),
    "theme_descriptions": OutputCeiling(
        500, "DESCRIPTION_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "136 haiku calls, max completed 308 (62% of cap)."),
    "theme_validation": OutputCeiling(
        400, "THEME_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "Max completed 272 on sonnet-5, 293 on 4-6 (~70% of cap); ~1.0x model growth."),
    "theme_assignment": OutputCeiling(
        8000, "THEME_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-07 raise after 10 days dead at 4000 (#543 — every call censored). "
        "Demand >= 4000 on sonnet-5; no post-raise sample yet."),
    "theme_discovery": OutputCeiling(
        8000, "THEME_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-07 raise from 4000: 8/8 sonnet-5 calls censored at 4000; "
        "no post-raise sample yet."),
    "theme_synthesis": OutputCeiling(
        8000, "SYNTHESIS_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-07 raise from 4000: 22/29 sonnet-4-6 calls censored at 4000."),
    "theme_split": OutputCeiling(
        1750, "THEME_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "RAISED 2026-08-09 from 800: the only sonnet-5 call censored at exactly 800; "
        "2.5x the 4-6 max completed (691) ~ 1750. PROVISIONAL."),
    "theme_merge_adjudication": OutputCeiling(
        700, None, "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "107 haiku calls, max completed 457 (65% of cap). Model passed per-call "
        "(default HAIKU tier constant, no tracked role)."),
    "theme_ecosystem_assignment": OutputCeiling(
        1000, "ECOSYSTEM_ASSIGN_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "240 haiku calls, max completed 757 (76% of cap)."),
    # theme_advisor's spend rows are phase-suffixed (theme_advisor_{discovery,split,
    # assignment}) but ONE call site serves all three — identical ceiling by construction.
    "theme_advisor_discovery": _ADVISOR,
    "theme_advisor_split": _ADVISOR,
    "theme_advisor_assignment": _ADVISOR,

    # ── operator-facing analysis ──
    "postmortem": OutputCeiling(
        1500, "POSTMORTEM_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-08 raise from 800: both sonnet-5 calls censored at 800; 1500 = 2.5x "
        "the 4-6 max completed (563). No completed sonnet-5 sample yet — PROVISIONAL."),
    "system_review_weekly": OutputCeiling(
        2800, "SYSTEM_REVIEW_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "2026-08-08 raise from 1200: the only sonnet-5 run censored at 1200; 2800 = "
        "2.5x the largest completed 4-6 run (1103-1120; 10/15 4-6 runs were themselves "
        "at-cap). PROVISIONAL."),
    "description_backfill": OutputCeiling(
        2000, "DESCRIPTION_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "35 haiku calls, max completed 724 (36% of cap)."),
    "market_agent_general": OutputCeiling(
        1024, "MARKET_AGENT_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "n=1 completed at 213 (21% of cap)."),

    # ── orchestrator container ──
    "orchestrator": OutputCeiling(
        4096, "ORCHESTRATOR_MODEL", "claude-sonnet-5",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "Tool-use loop; 232 calls on 4-6, p99 1754, max completed 3517 (86%), zero "
        "truncations in 6 months."),
    "context_compression": OutputCeiling(
        2500, "COMPRESSION_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "RAISED 2026-08-09 from 1024: 5/78 haiku calls censored at exactly 1024 "
        "(silently lossy compression); 2.5x the largest completed (993) ~ 2500."),
    "healthcheck": OutputCeiling(
        5, "HEALTHCHECK_MODEL", "claude-haiku-4-5-20251001",  # model-ok: provenance only — records which model this ceiling was MEASURED on, never selects one
        "Liveness ping — truncation BY DESIGN, response text discarded."),
    "perplexity_health": OutputCeiling(
        5, None, "sonar-pro",
        "Perplexity liveness ping — truncation BY DESIGN, response text discarded."),
}


def max_tokens_for(caller: str) -> int:
    """The registered output ceiling for a spend-tracker caller name.

    KeyError on an unknown caller is DELIBERATE — call sites bind at import, so a
    typo or an unregistered new caller fails at boot/test time, never silently."""
    return CEILINGS[caller].max_tokens


def callers_for_role(role: str) -> tuple[str, ...]:
    """Callers whose ceiling was sized against the model of `role` — the set the
    boot recorder flags when that role's resolved model changes."""
    return tuple(sorted(c for c, e in CEILINGS.items() if e.role == role))
