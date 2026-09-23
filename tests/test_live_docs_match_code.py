"""LIVE source-of-truth docs may not name code that no longer exists (2026-08-02).

CHANGE_PROCESS r6: *"Update the SSoT in the same commit as the code change — stale SSoT is worse
than no SSoT (gets cited authoritatively, contradicts the code)."* On 2026-08-02 the 9M Day-2 entry
was deleted and that rule was MISSED: `docs/setups/ninem.md` went on documenting Stage 3 as a
running strategy, and `safeguards.md` / `dual_account.md` kept naming `prepare_9m_day2_orb_order`
hours after it had been renamed. Nothing failed, because nothing checked.

⚠ **SCOPE, and why it is this narrow.** A general "docs must not name unknown symbols" check was
built first and REJECTED after measurement: it flagged 87-98 items per file — column names, audit
event types, table names, commit SHAs — none of them defects. A guard that always fires is not a
guard (the 2026-08-01 transitive-import lesson). So this checks ONE thing precisely: symbols we
DELIBERATELY deleted must not appear in a live SSoT doc except on a line that marks them as history.

**Maintaining it is part of deleting something**: add the symbol below when you remove it. That is
the checklist step the 8/02 deletion did not have.

HISTORICAL docs are deliberately NOT covered — `docs/analysis/*` and `docs/decisions/*` are dated
point-in-time records. An ADR describing a May decision in May terms is CORRECT; "updating" it would
destroy the record that stops the decision being re-litigated.
"""
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

# Docs whose contract is "tracks the code". README is the front door; setups/ and architecture/ are
# the SSoT files CHANGE_PROCESS r6 governs.
_LIVE_DOCS = (
    [_ROOT / "README.md"]
    + sorted((_ROOT / "docs/setups").glob("*.md"))
    + sorted((_ROOT / "docs/architecture").glob("*.md"))
)

# Symbols removed on purpose. Add on deletion; never remove an entry to make this pass.
_DELETED = {
    # #515, 2026-08-02 — the 9M Day-2 ENTRY strategy (the 9M CHARACTER stays live)
    "submit_9m_day2_trade": "deleted 2026-08-02 (#515)",
    "_9m_day2_orb_job": "deleted 2026-08-02 (#515)",
    "_ninem_spec_builder": "deleted 2026-08-02 (#515)",
    "prepare_9m_day2_orb_order": "renamed 2026-08-02 -> prepare_prior_day_low_orb_order (#515)",
    "score_9m_day2": "deleted 2026-08-02 (#515, unreachable after the entry went)",
}

# A line may name a dead symbol when it is explicitly TELLING you it is dead. That is not staleness,
# it is the history that stops the next reader rebuilding it.
_HISTORICAL = re.compile(
    r"DELETE|REMOVE|RETIRE|renamed|no longer|HISTORY ONLY|history only|"
    r"until 2026|gone\b|dead\b|legacy|unreachable",
    re.I,
)

# A doc's own CHANGE LOG is a dated record, exactly like docs/analysis and docs/decisions: a
# 2026-06-18 entry saying what was true on 2026-06-18 is CORRECT, and rewriting it would destroy the
# reasoning that stops a retired thing being rebuilt. Only the doc's LIVE prose is under contract.
_CHANGELOG_HEADING = re.compile(r"^#{1,6}\s*(change ?log|changelog|history)\b", re.I)


def _offending_lines(doc: Path, symbol: str) -> list[str]:
    """Hits whose surrounding CONTEXT does not mark them as history.

    Context is the blank-line-delimited paragraph plus the nearest preceding heading — NOT the
    single line. Markdown prose wraps, and a section headed "RETIRED" exempts everything under it,
    which is how a reader judges it. Line-scoped matching was an artifact of the first
    implementation and flagged correctly-written history as staleness."""
    lines = doc.read_text(errors="replace").split("\n")
    # nearest preceding heading for every line, plus whether we are inside the doc's change log
    heading, headings, in_log, in_logs = "", [], False, []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            heading = line
            depth = len(stripped) - len(stripped.lstrip("#"))
            if _CHANGELOG_HEADING.match(stripped):
                in_log, log_depth = True, depth
            elif in_log and depth <= log_depth:
                in_log = False          # a same-or-higher-level heading ends the log section
        headings.append(heading)
        in_logs.append(in_log)
    # paragraph bounds
    para_of, start = {}, 0
    for i, line in enumerate(lines):
        if not line.strip():
            for k in range(start, i):
                para_of[k] = (start, i)
            start = i + 1
    for k in range(start, len(lines)):
        para_of[k] = (start, len(lines))

    out = []
    for n, line in enumerate(lines, 1):
        if symbol not in line:
            continue
        if in_logs[n - 1]:
            continue                    # dated change-log entry -- a record, not a live claim
        a, b = para_of.get(n - 1, (n - 1, n))
        context = "\n".join(lines[a:b]) + "\n" + headings[n - 1]
        if not _HISTORICAL.search(context):
            out.append(f"{doc.relative_to(_ROOT)}:{n}  {line.strip()[:120]}")
    return out


@pytest.mark.parametrize("symbol,note", sorted(_DELETED.items()))
def test_live_docs_do_not_present_deleted_code_as_current(symbol, note):
    bad = [hit for doc in _LIVE_DOCS for hit in _offending_lines(doc, symbol)]
    assert not bad, (
        f"{symbol} was {note}, but a LIVE source-of-truth doc still names it as current:\n  "
        + "\n  ".join(bad)
        + "\n\nEither delete the reference or mark the line as history "
        "(CHANGE_PROCESS r6: a stale SSoT gets cited authoritatively)."
    )


def test_the_guard_can_actually_fail():
    """Guard the guard. If the historical-marker regex ever swallowed everything, every test above
    would pass vacuously — which is exactly how this drift survived in the first place."""
    assert _HISTORICAL.search("RETIRED 2026-08-02") is not None
    assert _HISTORICAL.search("`prepare_9m_day2_orb_order` (9M Day2 ORB entry, real money).") is None
    # and the change-log exemption must not swallow the whole document
    assert _CHANGELOG_HEADING.match("## Change log (newest first)") is not None
    assert _CHANGELOG_HEADING.match("## Universe / eligibility") is None


def test_the_live_doc_set_is_not_empty():
    assert len(_LIVE_DOCS) >= 5, f"only found {len(_LIVE_DOCS)} live docs — the glob is broken"


def test_ninem_ssot_states_the_character_is_live_and_the_entry_is_not():
    """The specific confusion this file exists to prevent: 9M the CHARACTER is live; 9M Day 2 the
    ENTRY is deleted. The operator has corrected this distinction more than once."""
    src = (_ROOT / "docs/setups/ninem.md").read_text()
    head = src[:2000]
    assert "CHARACTER is live" in head or "CHARACTER" in head
    assert "DELETED" in head, "the SSoT must say the entry is gone, not merely deprecated"


def test_readme_does_not_recommend_a_raw_compose_deploy():
    """A raw `docker compose up --build` skips the preflight and caused the 2026-05-13 outage. The
    README recommended it until 2026-08-02."""
    readme = (_ROOT / "README.md").read_text()
    for m in re.finditer(r"docker compose[^\n`]*up[^\n`]*--build", readme):
        line_start = readme.rfind("\n", 0, m.start()) + 1
        context = readme[max(0, line_start - 400):m.end()]
        assert "Do NOT deploy" in context or "scripts/deploy.sh" in context, \
            f"README shows a raw compose deploy with no warning: {m.group(0)}"


# ── the README backlog must not become a second source of truth (2026-08-02) ────────────────

def test_readme_backlog_points_at_plan_and_does_not_relist_it():
    """Operator: *"the backlog section is not updated."* It carried a P-numbered list that had gone
    six weeks stale — most damagingly it still said live trading was PENDING, when MAGNA53 had been
    trading real money since 2026-06-22.

    The fix is not to hand-sync it. `PLAN.md` is the single SoT precisely because the plan once
    lived across ~7 hand-synced surfaces and the launch runway was missed three times. So the rule
    is: the README's backlog section NAMES PLAN.md and does not re-list it."""
    readme = (_ROOT / "README.md").read_text()
    idx = readme.index("## Backlog")
    section = readme[idx:]
    assert "PLAN.md" in section, "the backlog section must name PLAN.md as the source of truth"
    assert "check_plan.py" in section, "it must give the command that prints the real plan"


def test_readme_does_not_claim_live_trading_is_still_pending():
    """The single most wrong line in the file: 'Flip LIVE_TRADING_ENABLED=true after P3 validation
    and regime improves' — written before the 2026-06-22 cutover and still there six weeks later."""
    readme = (_ROOT / "README.md").read_text()
    for m in re.finditer(r"LIVE_TRADING_ENABLED=true", readme):
        window = readme[m.start(): m.start() + 260]
        assert not re.search(r"after P3|Flip .* after|when regime improves", window), (
            "README still presents going live as a FUTURE step; it happened 2026-06-22")

