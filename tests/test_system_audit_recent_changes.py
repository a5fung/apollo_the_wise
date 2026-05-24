"""Regression test for `_recent_changes_context` (#112, 2026-05-24).

The original `_CLAUDEMD_HEADER_RE` regex looked for "## Changes Made
YYYY-MM-DD" but the actual CLAUDE.md format is "### YYYY-MM-DD (Day)
— title". Returned [] always; Sonnet hypothesis call got empty
context silently. Fixed in commit a82d822.

These tests guard against silent regression — assert the function
extracts at least one header from the live CLAUDE.md, AND assert
the regex matches both the new (with em-dash title) and old (header-
only) formats.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_recent_changes_extracts_at_least_one_header():
    """Smoke-test against the live CLAUDE.md — must return ≥1 entry."""
    from agents.market_intelligence.system_audit import _recent_changes_context

    result = _recent_changes_context(limit=5)
    assert len(result) >= 1, (
        "_recent_changes_context returned 0 entries — regex likely failed "
        "to match CLAUDE.md header format. Was the file format changed?"
    )
    for entry in result:
        # Each entry is "YYYY-MM-DD: <title fragment>"
        assert ":" in entry, f"malformed entry: {entry!r}"
        date_part = entry.split(":", 1)[0]
        assert len(date_part) == 10, f"date not YYYY-MM-DD: {date_part!r}"
        assert date_part[4] == "-" and date_part[7] == "-"


def test_regex_matches_new_emdash_format(tmp_path):
    """Verify the regex matches `### YYYY-MM-DD (Day) — title` format."""
    from agents.market_intelligence.system_audit import _recent_changes_context

    md_path = tmp_path / "CLAUDE.md"
    md_path.write_text(
        "## Changes Made — Recent\n\n"
        "### 2026-05-24 (Sun) — Test entry shipped\n\n"
        "Body text here.\n\n"
        "### 2026-05-23 (Sat) — Earlier entry\n\n"
        "More body.\n",
        encoding="utf-8",
    )
    result = _recent_changes_context(repo_root=tmp_path, limit=5)
    assert len(result) == 2
    assert result[0].startswith("2026-05-24:")
    assert "Test entry shipped" in result[0]
    assert result[1].startswith("2026-05-23:")
    assert "Earlier entry" in result[1]


def test_regex_matches_header_only_format(tmp_path):
    """Verify the regex falls back to body line for entries without em-dash title."""
    from agents.market_intelligence.system_audit import _recent_changes_context

    md_path = tmp_path / "CLAUDE.md"
    md_path.write_text(
        "## Changes Made — Recent\n\n"
        "### 2026-05-24\n\n"
        "Body first line is the title.\n"
        "Body second line ignored.\n",
        encoding="utf-8",
    )
    result = _recent_changes_context(repo_root=tmp_path, limit=5)
    assert len(result) == 1
    assert result[0].startswith("2026-05-24:")
    assert "Body first line is the title" in result[0]


def test_drift_matcher_first_token_priority():
    """`_match_drift_to_recent_changes` should match on first-token (subsystem
    prefix) priority — not on any-token (which produces false positives on
    common words like 'entry' or 'rate')."""
    from agents.market_intelligence.system_review import _match_drift_to_recent_changes

    # First-token match: "cooldown" appears in change → hit
    changes = ["2026-05-24: Cooldown classifier improved cadence"]
    assert _match_drift_to_recent_changes("cooldowns_per_day", changes) is not None

    # NO first-token match, NO 2+ tokens: common word "entry" alone shouldn't hit
    changes = ["2026-05-23: New entry-pipeline retry logic"]
    # tokens of "ep_entry_rate" with len>=4: ['entry', 'rate']
    # 'entry' matches but 'rate' doesn't → only 1 token, NOT first ('entry' IS first)
    # so this WILL match because 'entry' is the first 4+ char token
    assert _match_drift_to_recent_changes("ep_entry_rate", changes) is not None

    # NO match — neither first-token nor 2+ tokens
    changes = ["2026-05-23: Pipeline retry logic added"]
    # tokens of "cooldowns_per_day": ['cooldowns'] (first), no others
    # No match on 'cooldowns', no fallback (only 1 token total)
    assert _match_drift_to_recent_changes("cooldowns_per_day", changes) is None
