"""The SSoT router is complete, and every owner carries its own findings.

WHY THIS EXISTS
Operator, 2026-08-29: "what is the Single source of truth then? We need a SoT, and prevent
things diverting from it or it getting out of date or things fragmented. We built SoT for that
purpose, but for whatever reason, it didn't work, we need to stop this goose chase all the time."

Measured that day, which is the diagnosis this test encodes:
  - an index existed for SETUPS only; architecture, methodology and process had none
  - 99 files used the word "SSoT", including analysis docs declaring themselves one
  - the owners did not carry their findings: magna53_ep.md linked 22 analyses and worked;
    exit_discipline.md linked 2 of 6, htf.md 1 of 3, flag_continuation.md and undercut_rally.md
    linked none

So the discipline held exactly where attention was and nowhere else, because nothing checked it.
Every other rule in this repo that mattered had to become a gate before it stuck - the burndown,
verify-live, PLAN.md's single-SoT rule, the report format. This is that gate for the SSoT.

TWO ARMS:
  1. ROUTER COMPLETE - every setup and architecture doc is registered in docs/SSoT.md, and every
     path the router names exists. Catches a new SSoT that nobody registered, and a router entry
     left behind by a rename.
  2. FINDINGS LINKED - for topics with a declared finding-pattern, an analysis or design document
     matching that pattern must be referenced from its owner. Catches the orphan class directly.

WHAT IT DOES NOT CHECK: whether an owner's summary of a finding is ACCURATE, or whether the
owner's content is current. Neither is decidable from text. This guarantees reachability, never
correctness - and reachability is the failure the operator actually hit.

Arm 2 is deliberately opt-in per topic rather than universal: a pattern that fires on unrelated
documents is how a guard gets switched off. Topics are added as their debt is paid, and
_FINDING_DEBT below is the honest record of what has not been.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_ROUTER = _REPO / "docs" / "SSoT.md"

# Directories whose every document must be registered in the router.
_MUST_REGISTER = ("docs/setups", "docs/architecture")

# Files in those directories that are not topic owners.
_NOT_OWNERS = {"README.md", "CHANGE_PROCESS.md"}

# Topics whose findings must be linked from their owner: owner -> filename patterns.
# Add a topic here once its existing findings are linked; the debt list below tracks the rest.
_FINDINGS_REQUIRED: dict[str, tuple[str, ...]] = {
    "docs/setups/delayed_ep_reentry.md": (
        r"delayed_e", r"pivot_ladder", r"pivot_proximity", r"mnts_delayed",
        r"conversion_rehearsal",
    ),
}

# Topics NOT yet under arm 2, with the count owed. This is a visible debt record, not an
# exemption: paying it means linking the findings and moving the topic into _FINDINGS_REQUIRED.
_FINDING_DEBT = {
    "docs/setups/exit_discipline.md": "links 2 of ~6 analyses (measured 2026-08-29)",
    "docs/setups/htf.md": "links 1 of ~3",
    "docs/setups/flag_continuation.md": "links 0 of ~1 (setup is RETIRED; low value)",
    "docs/setups/undercut_rally.md": "links 0 of ~1",
}

_SCANNED = ("docs/analysis", "docs/design")


def _router_text() -> str:
    assert _ROUTER.is_file(), (
        "docs/SSoT.md is missing. It is the router - the one file that says which document owns "
        "which topic. Without it every topic is a search."
    )
    return _ROUTER.read_text(encoding="utf-8")


def test_every_owner_is_registered_in_the_router() -> None:
    text = _router_text()
    missing = []
    for rel in _MUST_REGISTER:
        d = _REPO / rel
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            if path.name in _NOT_OWNERS:
                continue
            if f"{rel}/{path.name}" not in text:
                missing.append(f"{rel}/{path.name}")
    assert not missing, (
        "SSoT document(s) not registered in docs/SSoT.md:\n  " + "\n  ".join(missing)
        + "\n\nAdd a row naming the topic it owns. An unregistered SSoT is invisible - it is "
          "found only by someone who already knows it exists, which is the failure the router "
          "was built to end (operator 2026-08-29: \"stop this goose chase all the time\")."
    )


def test_every_router_entry_points_at_a_real_file() -> None:
    """A rename must not leave the router pointing into space."""
    text = _router_text()
    broken = [
        p for p in sorted(set(re.findall(r"`(docs/[A-Za-z0-9_./-]+\.md)`", text)))
        if not (_REPO / p).is_file()
    ]
    assert not broken, (
        "docs/SSoT.md points at file(s) that do not exist:\n  " + "\n  ".join(broken)
        + "\n\nA router that lies is worse than no router. Fix the path or drop the row."
    )


def test_declared_topics_carry_their_findings() -> None:
    """Arm 2: an analysis about a topic must be reachable from that topic's owner."""
    problems: list[str] = []
    for owner_rel, patterns in _FINDINGS_REQUIRED.items():
        owner = _REPO / owner_rel
        assert owner.is_file(), f"{owner_rel} is declared in _FINDINGS_REQUIRED but missing"
        owner_text = owner.read_text(encoding="utf-8")
        compiled = [re.compile(p, re.I) for p in patterns]
        for rel in _SCANNED:
            d = _REPO / rel
            if not d.is_dir():
                continue
            for doc in sorted(d.iterdir()):
                if doc.suffix.lower() not in {".md", ".txt"}:
                    continue
                if any(c.search(doc.name) for c in compiled) and doc.name not in owner_text:
                    problems.append(f"{rel}/{doc.name}  ->  not linked from {owner_rel}")
    assert not problems, (
        "finding(s) orphaned from their SSoT:\n  " + "\n  ".join(problems)
        + "\n\nAdd a row to the owner saying what the document ESTABLISHED - not what it was "
          "about. An orphaned finding gets re-derived; that is exactly what happened to the "
          "pivot-proximity result, which sat unread from 2026-08-16 to 08-29 and holds the "
          "central tension of the whole delayed-entry ladder."
    )


# Rulings that kept getting re-derived, and the owner that must still carry each. These are
# the operator's own words; losing one costs a conversation we have already had.
_PINNED_RULINGS = {
    "docs/methodology/ANALYSIS_CARD_PREAMBLE.md": [
        ("Win rate is a SELECTION measure",
         "2026-08-30: win rate belongs to filters/ranking/admission - which names you take - and "
         "NOT to entry/stop/management/re-entry, which cannot move it. My blanket 'never rank by "
         "win rate' was wrong for selection work; his correction is the load-bearing half."),
        ("RECALL",
         "the ranking order starts with recall - how many REAL EPs does it catch at all (P1). "
         "Dropping this is how an analysis ends up optimising a metric nobody asked for."),
        ("4R",
         "THE GOAL's arithmetic: at a ~20% win rate the average winner must exceed 4R just to "
         "break even, so win rate and reward are ONE target."),
        ("INVISIBLE",
         "P14's asymmetry - under-admission leaves no trace, so every instinct pulls toward "
         "tightening. Report recall AND cost together."),
    ],
    "docs/setups/delayed_ep_reentry.md": [
        ('NEAR" IS A BEHAVIOUR',
         "2026-08-29: 'near' is deceleration/cessation/consolidation/turn, per stock, per "
         "instance - NOT a percentage. It replaces the +/-0.5xADR proximity test."),
        ("THE PIVOT IS THE FILTER",
         "2026-08-29: the behaviour triggers, the pivot only qualifies. A tool alone is "
         "worthless - measured, 620-ANY +0.04R vs 620@EPC +0.21R."),
        ("day-1 construct",
         "2026-08-29: an opening range does not transfer to a delayed entry."),
        ("character",
         "2026-06-11: the right pivot differs per stock; a global pullback-MA parameter erases "
         "the principle."),
    ],
}


def test_pinned_operator_rulings_survive() -> None:
    """A ruling he has already made must not have to be made twice."""
    for owner_rel, rulings in _PINNED_RULINGS.items():
        owner = _REPO / owner_rel
        assert owner.is_file(), f"{owner_rel} is missing but carries pinned rulings"
        text = owner.read_text(encoding="utf-8")
        for phrase, why in rulings:
            assert phrase in text, (
                f"{owner_rel} lost an operator ruling: {why}\n"
                f"Restore it. These are his own words and re-deriving one costs a conversation "
                f"already had."
            )


def test_the_finding_debt_is_declared_not_hidden() -> None:
    """Debt must name real files, so it cannot quietly become fiction."""
    for rel, note in _FINDING_DEBT.items():
        assert (_REPO / rel).is_file(), f"_FINDING_DEBT names a missing file: {rel}"
        assert note.strip(), f"_FINDING_DEBT entry for {rel} has no note"
        assert rel not in _FINDINGS_REQUIRED, (
            f"{rel} is in BOTH _FINDING_DEBT and _FINDINGS_REQUIRED - once the findings are "
            f"linked, remove the debt entry rather than leaving both."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
