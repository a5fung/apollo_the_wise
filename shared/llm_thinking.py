"""Extended-thinking on/off registry for sonnet-5 (and opus-5) call sites — companion
to `shared/output_ceilings.py` (#575, 2026-08-21).

WHY THIS EXISTS. On sonnet-5 the extended-thinking block is NOT free: left unset, the
SDK defaults to adaptive thinking, and that thinking shares `max_tokens` with the
text/tool output — it is not a separate budget. Every ceiling in output_ceilings.py
was derived as a TEXT budget against a budget that was actually shared with an
invisible, uncapped-by-us consumer, which is why three separate threshold raises
(theme_discovery batch 37->22, theme_assignment/theme_split/narrative_theme_discovery
4000->8000, theme_split 800->1750) all re-pegged within days. The decisive row:
2026-08-19 `theme_validation` consumed 1000/1000 output tokens and came back with
`blocks=['thinking']` — zero text, the entire cap spent on a hidden reasoning pass.

`budget_tokens` is REJECTED by the API on sonnet-5 (verified in-container, #575) —
there is no partial setting. `{"type": "disabled"}` vs leaving `thinking` unset
(adaptive) is the only lever; there is no third option to build here.

WHO IS IN `THINKING_DISABLED`: callers whose entire output is a small, fixed
JSON/tool shape, where the model already has an explicit `analysis_scratchpad`
field (or an equally small JSON contract) to reason IN. For those, extended
thinking is a second, hidden, budget-eating copy of the same reasoning the schema
already captures — no upside proven, all of the truncation risk.

WHO IS DELIBERATELY LEFT OFF THIS LIST (thinking stays on the model default):
genuinely open-ended prose/deliberation callers — `theme_discovery`'s first
(tool_choice=auto) attempt, `system_review_weekly`'s weekly digest synthesis, and
the theme-clustering advisor's judgment calls. Thinking MAY be earning its keep
there and there is no measurement either way (the registry evidence is all
token counts, never verdict quality) — so those three are made RECOVERABLE
instead (retry / fall back once truncation is detected) rather than disabled
outright. See each call site for the specific handling.

Trade-off, stated plainly: disabling thinking on the five callers below removes
a hidden reasoning pass that MAY have been improving cluster/split/cohort
judgment quality — that is not measured either. The asymmetry that justifies it:
a truncated call returns ZERO output (and per the 2026-08-10 theme_split comments,
a truncated response once parsed as an affirmative "already coherent" LIE), while
a less-deliberated call still returns a usable one.
"""
from __future__ import annotations

# The `thinking=` kwarg value that turns extended thinking off entirely.
DISABLED = {"type": "disabled"}

# Callers where thinking is explicitly DISABLED (pass `thinking=DISABLED` at the
# call site). Every name here must also be a key in shared/output_ceilings.py —
# pinned by tests/test_llm_thinking.py.
THINKING_DISABLED = frozenset({
    "theme_validation",           # plain JSON {"remove": [...]}, no scratchpad at all
    "theme_rename",                # forced report_themes for ONE cohort; terse scratchpad
    "theme_assignment",           # forced tool (tool_choice=any) + analysis_scratchpad
    "theme_split",                 # forced tool (tool_choice=any) + analysis_scratchpad
    "narrative_theme_discovery",   # forced tool from turn 1 (report_narrative_themes), no advisor branch
    "theme_synthesis",             # forced tool from turn 1 (propose_emerging_cohorts), single-shot, no advisor branch
})
