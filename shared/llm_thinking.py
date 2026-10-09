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
(adaptive) is the only lever the CALL SITES choose between.

claude-sonnet-5-5 (#693, 2026-10-02) rejects `{"type": "disabled"}` and offers its own off
switch, `{"type": "between_tools"}` (no other field; a 400 at effort xhigh/max). Call sites keep
writing `DISABLED`; `shared/llm_client.py` translates it for the model: `between_tools` with
`max_tokens` untouched where the model offers it, else (claude-opus-5-5) the param is dropped and
`max_tokens` gets `thinking_headroom`. Before #693 5.5 got the drop too, so every job listed
below thought in full there — the registry said "off", the wire said "adaptive".

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

# 2026-09-29: theme_assignment (and the EP theme-fit check that shares it), theme_split and
# theme_rename LEFT this list. Their analysis_scratchpad was removed because claude-sonnet-5-5
# refuses to write reasoning out, so thinking is now the only place they reason; their ceilings
# carry thinking headroom (output_ceilings.py).
#
# 2026-10-09: theme_validation LEFT this list (#693, his "yes"). A replay of Monday 10-05's 151 calls
# (docs/analysis/693_validator_thinking_replay_2026-10-09.md, $0.49): with thinking cut it removed 26
# members live and 33 on a re-run that agreed with live on only 16; with thinking on, 5 — all also
# removed live. The cut setting was the noisy one, for $0.07 a night less. Its ceiling carries
# thinking headroom (output_ceilings.py).
#
# Callers where thinking is explicitly DISABLED (pass `thinking=DISABLED` at the
# call site). Every name here must also be a key in shared/output_ceilings.py —
# pinned by tests/test_llm_thinking.py.
THINKING_DISABLED = frozenset({
    "narrative_theme_discovery",   # forced tool from turn 1 (report_narrative_themes), no advisor branch
    "theme_synthesis",             # forced tool from turn 1 (propose_emerging_cohorts), single-shot, no advisor branch
    "theme_parent_adjudication",   # #505 containment adjudicator (Sonnet): forced tool, terse
                                    # verdict + one-sentence reason + brief notes AFTER them (#693) —
                                    # same schema-bounded shape as theme_merge_adjudication (Haiku,
                                    # untouched, has no thinking lever to begin with).
})
