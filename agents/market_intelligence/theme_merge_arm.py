"""ADR 0025 Arm B (#274) — thesis-coherence theme-merge arm: the toggle, Stage A
(deterministic candidate pairing) and Stage B (LLM thesis adjudication).

EVERYTHING here is behind the `THEME_MERGE_ARM` runtime toggle (default OFF — the
go-live flip is an operator decision gated on the T2b golden corpus:
`scripts/evals/theme_merge_corpus_v1.json`, hard pairs 100% / others ≥85%, run via
`scripts/evals/run_theme_merge_corpus_eval.py`).

Provenance: the Stage-A family stems + anchor-pairing and the Stage-B prompt anchors
are THE logic the 2026-07-11 replay validated (operator sign-off artifact:
`docs/analysis/274_merge_replay_table_2026-07-11.md`). The replay probe
`scripts/probes/_274_merge_replay.py` imports from this module — ONE copy, no drift.

Stage A is a PURE function (no I/O): callers supply themes, the merge_distinct
cooldown pair-set and (optionally) a ticker→sector map. Stage B is the Haiku
adjudicator hardened per the C4 caveat: temperature=0, forced tool_choice, the
scratchpad-first tool schema, retry-once on parse failure, validation-style 429
backoff. The mechanical merge executor lives in theme_engine._run_thesis_merge_pass
(it needs the engine's validator + audit plumbing).

Non-money surface: themes feed only the shadow judge theme-axis (#328) + briefs.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import re
from collections import Counter

import anthropic

from shared.llm_models import HAIKU

logger = logging.getLogger(__name__)

# ── The toggle (ADR 0025 §4) ─────────────────────────────────────────────────
THEME_MERGE_ARM_ENV = "THEME_MERGE_ARM"
_TRUTHY = {"1", "true", "on", "yes", "enabled"}


def merge_arm_enabled() -> bool:
    """Read the THEME_MERGE_ARM toggle at CALL time (container env; default OFF).

    Default-off is load-bearing: with the toggle off every theme pass is
    byte-identical to pre-ADR-0025 behavior. Flip = operator decision AFTER the
    golden corpus passes (see module docstring) — never flip it in code."""
    return os.environ.get(THEME_MERGE_ARM_ENV, "").strip().lower() in _TRUTHY


# ── Rails (ADR 0025 §2 Arm B) ────────────────────────────────────────────────
MAX_PAIRS_PER_NIGHT = 8          # Stage-A adjudication cap (cost + blast radius)
MAX_MERGES_PER_NIGHT = 3         # Stage-B executed-merge cap (churn rail)
MERGE_DISTINCT_COOLDOWN_DAYS = 30  # DISTINCT verdict → pair not re-adjudicated

# ── Stage A — curated narrative stems (replay-validated 2026-07-11) ──────────
# Stage A only PROPOSES; precision lives in Stage B. Moved verbatim from
# scripts/probes/_274_merge_replay.py (which now imports them from here).
FAMILIES = [
    ("insurance", r"insurance|underwrit|mortgage insurance"),
    ("reit", r"\bREIT\b|apartment|self-storage|residential rental"),
    ("quantum", r"quantum"),
    ("bank", r"\bbank\b|commercial banks"),
    ("semiconductor", r"semiconductor|silicon|wafer|chip|foundry"),
    ("payments_fintech", r"fintech|payment|digital financial|digital credit|digital banking|expense management|wealth management|brokerage platforms"),
    ("oncology", r"oncology|cancer|tumor"),
    ("autoimmune", r"autoimmune|inflammatory|immunolog"),
    ("gene_cell_therapy", r"gene therapy|cell therapy|genome editing|synthetic dna|genomic"),
    ("diagnostics", r"diagnostic|biopsy|molecular|early detection"),
    ("defense_aero", r"defense|aerospace|drone|unmanned|satellite"),
    ("freight", r"freight|truckload|logistics|carriers"),
    ("energy_downstream", r"refining|petroleum|midstream|pipeline|pressure pumping|oilfield"),
]


def family_of(name: str) -> str | None:
    """Stem-family of a theme NAME (replay-exact; first match wins)."""
    for fam, pat in FAMILIES:
        if re.search(pat, name or "", re.I):
            return fam
    return None


def pair_key(name_a: str, name_b: str) -> tuple[str, str]:
    """Normalized (sorted) pair key — the merge_distinct cooldown identity.
    Must match db.add_merge_distinct_cooldown's normalization."""
    return tuple(sorted((name_a, name_b)))  # type: ignore[return-value]


def _majority_sector_family(theme: dict, sectors_by_ticker: dict[str, str]) -> str | None:
    """ADR §2 Stage-A gate 1 OR-branch: dominant sector-family via majority-member
    sector. Requires a STRICT majority of ALL members to share one known sector —
    half-unknown memberships never form a sector family (fail-quiet)."""
    tickers = list(theme.get("tickers") or [])
    if len(tickers) < 2:
        return None
    known = [sectors_by_ticker.get(tk) for tk in tickers]
    known = [s for s in known if s and s != "Unknown"]
    if not known:
        return None
    sector, count = Counter(known).most_common(1)[0]
    if count * 2 > len(tickers):
        return f"sector::{sector}"
    return None


def group_families(
    themes: list[dict],
    sectors_by_ticker: dict[str, str] | None = None,
) -> dict[str, list[dict]]:
    """Stage-A family assignment. Name-stem families are primary (replay-exact);
    the majority-sector family is a FALLBACK for stem-less themes only, so the
    replay-validated stem clusters can never be diluted by broad FMP sectors."""
    fams: dict[str, list[dict]] = {}
    for t in themes:
        fam = family_of(t.get("name") or "")
        if fam is None and sectors_by_ticker:
            fam = _majority_sector_family(t, sectors_by_ticker)
        if fam:
            fams.setdefault(fam, []).append(t)
    return fams


def propose_merge_pairs(
    themes: list[dict],
    *,
    cooldown_pairs: "set[tuple[str, str]] | frozenset" = frozenset(),
    sectors_by_ticker: dict[str, str] | None = None,
    max_pairs: int | None = MAX_PAIRS_PER_NIGHT,
) -> list[tuple[dict, dict]]:
    """Stage A (PURE, deterministic) — ADR 0025 §2 Arm B candidate pairing.

    Within each family holding ≥2 themes, pair every theme against the family
    ANCHOR (largest by member count; name-asc tiebreak) — bounds pairs to
    ~(n−1)/family and always includes the legit-kill anchor pairs. Gates:
      2. one side <4 members OR the family holds ≥3 themes (two established
         ≥4-member themes in a 2-theme family are NEVER auto-paired);
      3. neither theme is the other's sub-theme; no live merge_distinct cooldown.
    Stem families consume the pair budget BEFORE sector-fallback families.
    Returns [(anchor, other), ...] capped at max_pairs (None = uncapped, replay mode).
    """
    fams = group_families(themes, sectors_by_ticker)
    pairs: list[tuple[dict, dict]] = []
    # stems first (replay-validated surface gets budget priority), then sector::
    for fam, members in sorted(fams.items(), key=lambda kv: (kv[0].startswith("sector::"), kv[0])):
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda x: (-len(x.get("tickers") or []), x.get("name") or ""))
        anchor, others = members[0], members[1:]
        for o in others:
            n_o = len(o.get("tickers") or [])
            # ADR gate 2 (replay-exact: anchor is the largest, so "one side <4" ≡ other <4)
            if not (n_o < 4 or len(members) >= 3):
                continue
            # ADR gate 3a: parent/sub coexistence stays — never pair parent with its child
            if o.get("parent_theme") == anchor.get("name") or anchor.get("parent_theme") == o.get("name"):
                continue
            # ADR gate 3b: live DISTINCT cooldown → not re-adjudicated (idempotence + cost)
            if pair_key(anchor.get("name") or "", o.get("name") or "") in cooldown_pairs:
                continue
            pairs.append((anchor, o))
    return pairs if max_pairs is None else pairs[:max_pairs]


# ── Stage B — the thesis adjudicator (Haiku, temp=0, scratchpad-first tool) ──
MERGE_VERDICTS = frozenset({"MERGE", "DISTINCT", "PARENT_CHILD"})

# Prompt anchors are LOAD-BEARING (ADR 0025 §2): the negative exemplars + the
# merge-on-shared-DRIVER instruction are verbatim from the signed 7/11 replay.
# Any edit here invalidates the corpus pass — re-run the corpus eval.
ADJUDICATION_PROMPT_VERSION = "v2-2026-07-12-slice-merge"  # v2 (operator-ruled 7/12, rulings-pack R3):
# identical-driver slice → MERGE; PARENT_CHILD requires a DISTINCT sub-driver. v1 answered
# PARENT_CHILD to pure slices (corpus M03/04/05), which keeps both themes and leaves the
# fragmentation (#274's whole purpose) unfixed.
ADJUDICATION_PROMPT = """You adjudicate whether two stock-market THEMES should MERGE. The bar is a shared
DRIVER / catalyst — NOT a shared sector label. Two themes in the same sector with DIFFERENT
demand drivers stay DISTINCT.

NEGATIVE EXEMPLARS (these are DISTINCT, never merge):
- "P&C insurance underwriters" vs "specialty-catastrophe property underwriters" = DISTINCT
  (broad multi-line pricing cycle vs a cat-exposed reinsurance-linked driver).
- "Office REITs" vs "multifamily/apartment REITs" = DISTINCT (return-to-office recovery vs
  housing-shortage rental demand — opposite drivers).

Member overlap alone is NEVER sufficient to merge: the same companies can carry two
different theses (different catalysts, different winners). The DIRECTIONAL driver decides —
a long-beneficiary theme and its collateral-damage complement are DISTINCT even when the
headline narrative is shared.

Verdicts:
- MERGE: one thesis, one driver — the two are the same trade in two names. This INCLUDES the
  slice case: when the drivers are IDENTICAL and the narrower theme adds only a slice
  qualifier — geography, purity/pure-play, modality, cap-size — with NO distinct catalyst of
  its own, the verdict is MERGE. A slice of the same trade is the same trade; keeping it
  separate is fragmentation, the exact failure this adjudication exists to fix.
- DISTINCT: genuine sub-industries with different drivers.
- PARENT_CHILD: the narrower theme has a genuinely DISTINCT sub-driver — a catalyst of its
  own that can move independently of the parent's (e.g. zero-trust/SASE architecture adoption
  inside the broader security-spend cycle). TEST: name the child's sub-driver; if it is just
  the parent's driver restated on a subset, the verdict is MERGE, not PARENT_CHILD.

THEME A: {a_name}
{a_members}  {a_desc}

THEME B: {b_name}
{b_members}  {b_desc}

Adjudicate with the tool. Fill analysis_scratchpad FIRST: name each theme's demand driver,
then decide. For MERGE, propose merged_name (keep the better-established name unless both
are sub-optimal and a cleaner family name exists). For PARENT_CHILD, set child to the
narrower theme."""

MERGE_ADJUDICATION_TOOL = {
    "name": "adjudicate_theme_merge",
    "description": "Record the merge adjudication for the two themes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": "Reason FIRST: what is each theme's demand driver/catalyst? "
                               "Same directional driver, or different?",
            },
            "verdict": {"type": "string", "enum": ["MERGE", "DISTINCT", "PARENT_CHILD"]},
            "driver_a": {"type": "string", "description": "Theme A's driver, ≤6 words"},
            "driver_b": {"type": "string", "description": "Theme B's driver, ≤6 words"},
            "reason": {"type": "string", "description": "≤25 words"},
            "merged_name": {
                "type": "string",
                "description": "MERGE only: the name for the merged theme (F1: adjudicator-proposed).",
            },
            "child": {
                "type": "string", "enum": ["A", "B"],
                "description": "PARENT_CHILD only: which theme is the narrower child.",
            },
        },
        "required": ["analysis_scratchpad", "verdict", "driver_a", "driver_b", "reason"],
    },
}

# anthropic may be stubbed in CI (conftest _MockModule) — resolve real exception
# classes once so isinstance never TypeErrors (theme_engine #246 pattern).
_RATELIMIT_EXC = tuple(
    c for c in (getattr(anthropic, "RateLimitError", None),) if isinstance(c, type)
)


def _member_line(theme: dict, sectors_by_ticker: dict[str, str] | None) -> str:
    """'  Members: NVDA (Technology), AMD, …' — omitted when the theme carries no
    tickers (the corpus pairs are name+description only)."""
    tickers = list(theme.get("tickers") or [])
    if not tickers:
        return ""
    parts = []
    for tk in tickers[:20]:
        sec = (sectors_by_ticker or {}).get(tk)
        parts.append(f"{tk} ({sec})" if sec and sec != "Unknown" else tk)
    return "  Members: " + ", ".join(parts) + "\n"


def build_adjudication_prompt(
    theme_a: dict, theme_b: dict,
    sectors_by_ticker: dict[str, str] | None = None,
) -> str:
    return ADJUDICATION_PROMPT.format(
        a_name=theme_a.get("name") or "",
        a_desc=(theme_a.get("description") or "")[:280],
        a_members=_member_line(theme_a, sectors_by_ticker),
        b_name=theme_b.get("name") or "",
        b_desc=(theme_b.get("description") or "")[:280],
        b_members=_member_line(theme_b, sectors_by_ticker),
    )


async def _create_with_backoff(client, prompt: str, model: str, semaphore) -> "anthropic.types.Message":
    """messages.create with the validation-style 429 backoff (3 attempts)."""
    backoffs = [(30, 15), (60, 30)]
    for attempt in range(len(backoffs) + 1):
        try:
            async with (semaphore if semaphore is not None else contextlib.nullcontext()):
                return await client.messages.create(
                    model=model,
                    max_tokens=700,
                    temperature=0.0,  # C4 caveat: determinize before any flip
                    tools=[MERGE_ADJUDICATION_TOOL],
                    tool_choice={"type": "tool", "name": MERGE_ADJUDICATION_TOOL["name"]},
                    messages=[{"role": "user", "content": prompt}],
                )
        except Exception as e:
            is_429 = (_RATELIMIT_EXC and isinstance(e, _RATELIMIT_EXC)) \
                or type(e).__name__ == "RateLimitError"
            if is_429 and attempt < len(backoffs):
                base, jitter = backoffs[attempt]
                wait = base + random.random() * jitter
                logger.warning(f"[merge arm] adjudication rate-limited — retry {attempt + 1} in {wait:.0f}s")
                await asyncio.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")  # pragma: no cover


async def adjudicate_merge_pair(
    theme_a: dict,
    theme_b: dict,
    *,
    client,
    model: str = HAIKU,
    semaphore=None,
    sectors_by_ticker: dict[str, str] | None = None,
    log_spend: bool = False,
) -> dict:
    """Stage B — one adjudication call per pair (ADR 0025 §2 Arm B).

    Hardened per the C4 caveat: temperature=0, forced tool_choice, retry ONCE on a
    missing/invalid tool result (a VALID verdict is never re-rolled), validation-style
    429 backoff inside _create_with_backoff. Never raises for a bad verdict — returns
    {"verdict": "ERROR", "reason": ...} so the nightly pass fail-opens per pair.
    """
    prompt = build_adjudication_prompt(theme_a, theme_b, sectors_by_ticker)
    last_err = ""
    for parse_attempt in range(2):
        try:
            resp = await _create_with_backoff(client, prompt, model, semaphore)
        except Exception as e:
            logger.warning(
                f"[merge arm] adjudication call failed for "
                f"'{theme_a.get('name')}' × '{theme_b.get('name')}': {e}"
            )
            return {"verdict": "ERROR", "reason": f"{type(e).__name__}: {e}"[:300]}
        if log_spend:
            try:
                from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
                await log_anthropic_call_safe(model=model, caller="theme_merge_adjudication",
                                              usage=getattr(resp, "usage", None))
            except Exception as e:  # spend telemetry must never break the arm
                logger.debug(f"[merge arm] spend telemetry failed (non-fatal): {e}")
        block = next(
            (b for b in (getattr(resp, "content", None) or [])
             if getattr(b, "type", "") == "tool_use"),
            None,
        )
        data = dict(getattr(block, "input", None) or {}) if block is not None else {}
        verdict = data.get("verdict")
        if verdict in MERGE_VERDICTS:
            data["prompt_version"] = ADJUDICATION_PROMPT_VERSION
            return data
        last_err = f"invalid/missing verdict {verdict!r} (attempt {parse_attempt + 1})"
        logger.warning(f"[merge arm] {last_err} for '{theme_a.get('name')}' × '{theme_b.get('name')}'")
    return {"verdict": "ERROR", "reason": last_err[:300]}
