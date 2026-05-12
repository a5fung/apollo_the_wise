"""
Shared prose markers used by EP catalyst downgrade and weekly loser-post-mortem
grading. Each consumer extends this base with site-specific phrases (e.g.
system_review adds litigation terms for retrospective grading).

Keep this list conservative: a marker added here fires in BOTH the live
catalyst gate AND the post-mortem flag, so it should be a phrase that
unambiguously signals "no fresh catalyst" in either context.
"""
from __future__ import annotations

NEGATIVE_CATALYST_MARKERS_BASE: tuple[str, ...] = (
    "no gap up catalyst identified",
    "no fresh company-specific news",
    "no fresh headlines",
    "no specific catalyst",
)
