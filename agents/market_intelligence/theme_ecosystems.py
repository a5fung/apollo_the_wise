"""Theme ecosystems — ADR 0032 Phase 1 (read-model only).

Two-level surface borrowed from Marios Stamatoudis: ECOSYSTEM (E-*) over
sub-THEMES (T-* = the existing `mi_themes` rows). Themes stay the unit of
discovery/validation/lifecycle; this module is an AGGREGATE on top:

  1. Taxonomy loader — `theme_ecosystems.yaml` at repo root (operator-signed
     SSoT, 20 buckets + reserved E-UNASSIGNED). Mirrors data_gated_reviews.py:
     module-cached, fail-safe (parse failure -> log + empty list, never raise).
  2. Theme -> ecosystem assignment — Haiku (analysis_scratchpad-first tool),
     deterministic keyword_stems + exemplar-overlap fallback, else E-UNASSIGNED.
     Persisted in `mi_theme_ecosystems` (db.py accessors) + audited.
  3. D3 ecosystem score — `compute_ecosystem_scores`, a PURE function:
     member-union breadth-weighted with capped depth boost + thin-floor.
     Uses member `rs_composite` directly, NEVER the stored `score` column
     (verified scale landmine: promoted rows write score=rs_avg 0-100 while
     native themes cap at 80).
  4. `/themes` v2 render — `format_ecosystem_board`: ecosystems ranked by
     boosted score, sub-themes nested with global theme rank, Fading shown
     struck-through INSIDE its ecosystem, stage as a per-line tag. Falls back
     to a flat comp-ranked list when the mapping table is empty (pre-backfill)
     so /themes never breaks.

NO MONEY PATH: themes feed briefs + the shadow-judge theme-axis only. This
module never touches trade state, discovery/validation/lifecycle logic, or
the parent_theme machinery (re-granularization is Phase 2).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from agents.market_intelligence.constants import trimmed_mean
from agents.market_intelligence.audit_events import THEME_ECOSYSTEM_ASSIGNED

logger = logging.getLogger(__name__)

# Repo-root SSoT (same layout as data_gated_reviews.yaml — see that loader).
_PATH = Path(__file__).resolve().parents[2] / "theme_ecosystems.yaml"

E_UNASSIGNED = "E-UNASSIGNED"

# ── D3 score constants (ADR 0032 — illustrative pins; CHANGE_PROCESS N>=10
#    backtest before any of these gates a live decision. They gate NOTHING
#    live today: the score is a read-model for /themes + briefs.) ───────────
STRONG_RS_MIN = 80.0          # member counts as "strong" at rs_composite >= 80
DEPTH_COMP_MIN = 85.0         # sub-theme must post trimmed-mean comp >= 85
ELITE_PAIR_MIN_RS = 90.0      # 2-member sub-theme qualifies only if both >= 90
STRONG_FLOOR = 5              # strong(E) < 5 -> boost 0 (thin-ecosystem floor)
BOOST_CAP = 0.30
BOOST_DEPTH_COEF = 0.04
BOOST_STRONG_COEF = 0.015
# Depth near-dup dedup (implementation refinement of D3, documented deviation):
# the literal "count qualifying sub-themes" is gameable by re-listing the same
# cohort under N near-identical names (raw/strong are union-safe; depth alone
# was not). Two qualifying sub-themes whose member sets overlap at Jaccard >=
# this threshold count ONCE (highest-comp survivor). Genuine sub-structure —
# disjoint clusters, or PARENT_CHILD subsets like a 3-member vuln-mgmt child
# inside a 12-member parent (Jaccard 0.25) — still counts fully, which is the
# Marios "inherited from Themes" pop the depth term exists for.
DEPTH_NEAR_DUP_JACCARD = 0.6

# Keyword-fallback weights (deterministic classifier, used when Haiku
# abstains/errors). The theme NAME is the thesis — a stem hit there is strong
# signal; the description is long LLM prose full of incidental words ("credit",
# "power" inside "empowering"...) so it gets a fractional weight. Exemplar
# membership is strong evidence. Calibrated on a read-only dry run over the 65
# live active themes (2026-07-14): equal weighting mis-bucketed 3 REIT/insurance
# themes on description noise; name-weighted resolved all three.
_NAME_STEM_WEIGHT = 2.0
_DESC_STEM_WEIGHT = 0.5
_EXEMPLAR_WEIGHT = 2.0
# Minimum score to assign at all: at least ONE name-stem hit or ONE exemplar
# member. Mappings are sticky (ensure_theme_ecosystems never re-assigns), so a
# description-noise-only match must land in the E-UNASSIGNED triage lane rather
# than stick a wrong bucket (dry run: "Life Science Tools..." scored 0.5 on
# E-CYBR via an incidental description word).
_KEYWORD_MIN_SCORE = 2.0

# Cost hygiene: cap Haiku assignment calls per engine run. Steady state is
# ~1-5 births/night; the cap only bites on a cold backfill, where the
# remainder falls to the deterministic keyword path (and the nightly hook
# retries unmapped names next run). The backfill script raises this.
_MAX_HAIKU_PER_RUN = 25


# ═════════════════════════════════════════════════════════════════════════
# 1. Taxonomy loader (mirrors data_gated_reviews._load_registry + cache)
# ═════════════════════════════════════════════════════════════════════════

_TAXONOMY_CACHE: list[dict[str, Any]] | None = None


def _load_taxonomy() -> list[dict[str, Any]]:
    """Load + cache the ordered ecosystem list from theme_ecosystems.yaml.

    Fail-safe: missing file / parse error / wrong shape -> log + empty list,
    never raise (a broken taxonomy must degrade /themes to the flat list,
    not crash it). Parse failures are NOT cached so a fixed file heals on
    the next call; a successful (possibly empty) load is cached.
    """
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is not None:
        return _TAXONOMY_CACHE
    if not _PATH.exists():
        logger.warning(f"theme_ecosystems.yaml not found at {_PATH} — ecosystem layer disabled")
        return []
    try:
        raw = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        logger.exception("theme_ecosystems.yaml parse failed — ecosystem layer disabled")
        return []
    if not isinstance(raw, dict):
        logger.error(f"theme_ecosystems.yaml top level is {type(raw).__name__}, expected mapping")
        return []
    entries = [e for e in (raw.get("ecosystems") or [])
               if isinstance(e, dict) and e.get("e_code")]
    _TAXONOMY_CACHE = entries
    return entries


def reset_taxonomy_cache() -> None:
    """Test hook — drop the module cache so a monkeypatched _PATH reloads."""
    global _TAXONOMY_CACHE
    _TAXONOMY_CACHE = None


def get_ecosystems() -> list[dict[str, Any]]:
    """The ordered ecosystem list, exactly as in the YAML (order = display tiebreak)."""
    return _load_taxonomy()


def get_ecosystem_map() -> dict[str, dict[str, Any]]:
    """e_code -> taxonomy entry lookup."""
    return {e["e_code"]: e for e in _load_taxonomy()}


def get_ecosystem_codes() -> list[str]:
    """Ordered e_codes (YAML order)."""
    return [e["e_code"] for e in _load_taxonomy()]


# ═════════════════════════════════════════════════════════════════════════
# 2. D3 ecosystem score — PURE function
# ═════════════════════════════════════════════════════════════════════════

def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compute_ecosystem_scores(
    ecosystem_to_themes: dict[str, list[dict]],
    theme_rs_data: dict[str, dict],
) -> dict[str, dict]:
    """D3 (ADR 0032) — per-ecosystem score aggregate. PURE: no I/O.

    Inputs:
      ecosystem_to_themes: e_code -> theme dicts (need "name", "tickers",
        "stage"; Fading/Retired themes may be included — they are excluded
        from members/depth here).
      theme_rs_data: ticker -> {"rs_composite": float, ...} (the
        get_rs_for_tickers shape). The stored mi_themes `score` column is
        deliberately ignored (mixed-scale landmine).

    Returns e_code -> {raw, strong, depth, boost, boosted, member_union,
    n_scored, n_active_themes}.

      members(E) = dedup union of tickers across active non-Fading sub-themes
      raw(E)     = trimmed_mean(rs_composite of members(E))
      strong(E)  = |{m : rs_composite >= 80}|
      depth(E)   = |{T : (>=3 members OR elite pair) AND comp >= 85}|,
                   near-duplicate member-sets (Jaccard >= 0.6) counted once
      boost(E)   = 0 if strong < 5 else min(0.30, 0.04*depth + 0.015*strong)
      boosted(E) = raw * (1 + boost)

    Anti-fragmentation: the union base means splitting a cohort into N
    near-dups changes neither raw nor strong, and the depth near-dup dedup
    means it doesn't inflate depth either — the same members score the same
    whether they live in 1 sub-theme or 8 near-copies. Genuinely distinct
    sub-clusters DO raise depth (the intended Marios boost).
    """
    def _rs(tk: str) -> float | None:
        d = theme_rs_data.get(tk) or {}
        return d.get("rs_composite")

    out: dict[str, dict] = {}
    for e_code, themes in ecosystem_to_themes.items():
        active = [t for t in (themes or [])
                  if t.get("stage") not in ("Fading", "Retired")]

        union: set[str] = set()
        for t in active:
            union.update(t.get("tickers") or [])
        member_union = sorted(union)

        rs_vals = [v for v in (_rs(tk) for tk in member_union) if v is not None]
        raw = trimmed_mean(rs_vals) if rs_vals else 0.0
        strong = sum(1 for v in rs_vals if v >= STRONG_RS_MIN)

        # depth — qualifying sub-themes, near-dup member-sets counted once
        qualifying: list[tuple[float, str, frozenset]] = []
        for t in active:
            tks = list(t.get("tickers") or [])
            t_rs = [v for v in (_rs(tk) for tk in tks) if v is not None]
            if not t_rs:
                continue
            comp = trimmed_mean(t_rs)
            if comp < DEPTH_COMP_MIN:
                continue
            is_elite_pair = (len(tks) == 2 and len(t_rs) == 2
                             and min(t_rs) >= ELITE_PAIR_MIN_RS)
            if len(tks) >= 3 or is_elite_pair:
                qualifying.append((comp, t.get("name") or "", frozenset(tks)))
        qualifying.sort(key=lambda q: (-q[0], q[1]))   # deterministic survivor order
        counted: list[frozenset] = []
        for _comp, _name, tkset in qualifying:
            if any(_jaccard(tkset, prev) >= DEPTH_NEAR_DUP_JACCARD for prev in counted):
                continue
            counted.append(tkset)
        depth = len(counted)

        boost = 0.0 if strong < STRONG_FLOOR else min(
            BOOST_CAP, BOOST_DEPTH_COEF * depth + BOOST_STRONG_COEF * strong)
        out[e_code] = {
            "raw": raw,
            "strong": strong,
            "depth": depth,
            "boost": boost,
            "boosted": raw * (1.0 + boost),
            "member_union": member_union,
            "n_scored": len(rs_vals),
            "n_active_themes": len(active),
        }
    return out


# ═════════════════════════════════════════════════════════════════════════
# 3. Theme -> ecosystem assignment (Haiku primary, keyword fallback)
# ═════════════════════════════════════════════════════════════════════════

_ECOSYSTEM_ASSIGN_TOOL = {
    "name": "assign_theme_ecosystem",
    "description": (
        "Assign one stock-market theme to exactly one primary ecosystem "
        "bucket from the fixed taxonomy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            # analysis_scratchpad FIRST — house discipline: reason before the JSON.
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "REQUIRED. Reason step-by-step BEFORE deciding: (1) the theme's "
                    "core thesis from its name/description/members, (2) the 1-2 "
                    "candidate ecosystems and why, (3) the decision. This is how "
                    "you avoid a forced bad fit — E-UNASSIGNED is a valid answer."
                ),
            },
            "e_code": {
                "type": "string",
                "description": (
                    "The chosen ecosystem code, EXACTLY as listed in the taxonomy. "
                    "Use E-UNASSIGNED when no bucket clearly fits."
                ),
            },
        },
        "required": ["analysis_scratchpad", "e_code"],
    },
}


async def _assign_via_haiku(
    theme: dict, ecosystems: list[dict], sectors: dict[str, str]
) -> str | None:
    """One forced-tool Haiku call. Returns a validated e_code, or None on
    abstain (E-UNASSIGNED) / unknown code / no tool call — caller falls back.
    Raises on transport errors (caller catches + falls back)."""
    # Reuse the theme engine's client — do NOT hand-roll a new anthropic client.
    from agents.market_intelligence.theme_engine import _get_anthropic_client
    from shared.llm_models import ECOSYSTEM_ASSIGN_MODEL

    valid_codes = {e["e_code"] for e in ecosystems} | {E_UNASSIGNED}
    taxonomy_lines = [
        f"- {e['e_code']} — {e.get('name', '')}: {e.get('description', '')}"
        for e in ecosystems
    ]
    members = list(theme.get("tickers") or [])[:30]
    member_lines = [
        f"- {tk}" + (f" ({sectors[tk]})" if sectors.get(tk) else "")
        for tk in members
    ] or ["(no members listed)"]

    prompt = f"""You are classifying a stock-market theme into a FIXED taxonomy of primary ecosystems.

ECOSYSTEM TAXONOMY (choose exactly one e_code):
{chr(10).join(taxonomy_lines)}
- {E_UNASSIGNED} — Unassigned: use when NO bucket clearly fits the theme's core thesis.

THEME TO CLASSIFY:
Name: {theme.get('name', '')}
Description: {(theme.get('description') or '')[:400]}
Members (with sector where known):
{chr(10).join(member_lines)}

Rules:
- Classify by the theme's CORE thesis, not by an incidental member.
- Pick the MOST SPECIFIC bucket (e.g. AI-native security -> E-CYBR, not E-SAAS;
  AI silicon -> E-AISEMI, not E-AIINFRA).
- When genuinely torn between two buckets or nothing fits, answer {E_UNASSIGNED} —
  that is a correct answer, not a failure.

Call `assign_theme_ecosystem` with your reasoning in `analysis_scratchpad` first,
then the single chosen `e_code`."""

    client = _get_anthropic_client()
    resp = await client.messages.create(
        model=ECOSYSTEM_ASSIGN_MODEL,
        max_tokens=1000,
        tools=[_ECOSYSTEM_ASSIGN_TOOL],
        tool_choice={"type": "tool", "name": "assign_theme_ecosystem"},
        messages=[{"role": "user", "content": prompt}],
    )
    # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    await log_anthropic_call_safe(model=ECOSYSTEM_ASSIGN_MODEL,
                                  caller="theme_ecosystem_assignment",
                                  usage=getattr(resp, "usage", None))

    tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
    if not tool_uses:
        logger.warning(
            f"[theme ecosystems] Haiku returned no tool call for '{theme.get('name')}'")
        return None
    e_code = str((tool_uses[0].input or {}).get("e_code") or "").strip().upper()
    if e_code not in valid_codes:
        logger.warning(
            f"[theme ecosystems] Haiku returned unknown e_code {e_code!r} "
            f"for '{theme.get('name')}' — falling back")
        return None
    if e_code == E_UNASSIGNED:   # explicit abstain → keyword fallback decides
        return None
    return e_code


def keyword_fallback_ecosystem(
    name: str,
    description: str,
    tickers: list[str] | None,
    ecosystems: list[dict] | None = None,
) -> tuple[str, float]:
    """Deterministic fallback classifier: keyword_stems substring hits — in the
    theme NAME (+2 each, the thesis) or the description (+0.5 each, noisy
    prose) — plus exemplar-ticker overlap (+2 each). Best score >=
    _KEYWORD_MIN_SCORE wins (at least one name-stem hit or exemplar member —
    mappings are sticky, so description-noise-only matches go to triage);
    ties keep the first bucket in taxonomy order.
    Returns (e_code, score) — (E-UNASSIGNED, best sub-threshold score) when
    nothing matches strongly enough."""
    if ecosystems is None:
        ecosystems = get_ecosystems()
    name_l = (name or "").lower()
    desc_l = (description or "").lower()
    members = {str(t).upper() for t in (tickers or [])}

    best_code, best_score = E_UNASSIGNED, 0.0
    for e in ecosystems:
        code = e.get("e_code")
        if not code or code == E_UNASSIGNED:
            continue
        score = 0.0
        for stem in (e.get("keyword_stems") or []):
            s = str(stem).lower() if stem else ""
            if not s:
                continue
            if s in name_l:
                score += _NAME_STEM_WEIGHT
            elif s in desc_l:
                score += _DESC_STEM_WEIGHT
        exemplars = {str(x).upper() for x in (e.get("exemplars") or [])}
        score += _EXEMPLAR_WEIGHT * len(members & exemplars)
        if score > best_score:
            best_code, best_score = code, score
    if best_score < _KEYWORD_MIN_SCORE:
        return E_UNASSIGNED, best_score
    return best_code, best_score


async def assign_theme_to_ecosystem(
    theme: dict,
    *,
    sectors: dict[str, str] | None = None,
    use_llm: bool = True,
) -> dict:
    """Classify ONE theme into the fixed E-* taxonomy.

    Primary: Haiku (analysis_scratchpad-first forced tool). Fallback on
    abstain/error: keyword_stems + exemplar overlap. Else E-UNASSIGNED.
    Classification only — persistence + audit live in ensure_theme_ecosystems.

    Returns {"e_code", "method": haiku|keyword|unassigned, "llm_attempted",
    "detail"}. Never raises.
    """
    name = (theme.get("name") or "").strip()
    ecosystems = get_ecosystems()
    if not ecosystems or not name:
        return {"e_code": E_UNASSIGNED, "method": "unassigned",
                "llm_attempted": False,
                "detail": "empty taxonomy" if not ecosystems else "unnamed theme"}

    llm_attempted = False
    if use_llm:
        llm_attempted = True
        try:
            e_code = await _assign_via_haiku(theme, ecosystems, sectors or {})
            if e_code:   # validated, non-abstain
                return {"e_code": e_code, "method": "haiku",
                        "llm_attempted": True, "detail": ""}
            logger.info(
                f"[theme ecosystems] Haiku abstained on '{name}' — keyword fallback")
        except Exception as e:
            logger.warning(
                f"[theme ecosystems] Haiku assignment failed for '{name}' — "
                f"keyword fallback: {type(e).__name__}: {e}")

    e_code, score = keyword_fallback_ecosystem(
        name, theme.get("description") or "", theme.get("tickers") or [], ecosystems)
    if e_code != E_UNASSIGNED:
        return {"e_code": e_code, "method": "keyword",
                "llm_attempted": llm_attempted,
                "detail": f"keyword score {score:g}"}
    return {"e_code": E_UNASSIGNED, "method": "unassigned",
            "llm_attempted": llm_attempted,
            "detail": "no keyword/exemplar match"}


async def ensure_theme_ecosystems(
    themes: list[dict],
    *,
    dry_run: bool = False,
    use_llm: bool = True,
    max_llm_calls: int = _MAX_HAIKU_PER_RUN,
) -> list[dict]:
    """Assign every UNMAPPED (no mi_theme_ecosystems row) non-Retired theme in
    `themes` to an ecosystem; upsert + audit each unless dry_run.

    Called from run_theme_engine after _save_themes (births get mapped at
    birth; renames self-heal next run) and from the backfill script. Already
    mapped names are never re-assigned (the mapping is stable — re-mapping is
    an operator action via the backfill script / SQL).

    Returns the assignment records (used by the backfill script's report).
    DB errors propagate — the run_theme_engine hook wraps this call.
    """
    from agents.market_intelligence import db as _db

    if not themes:
        return []
    existing = await _db.get_all_theme_ecosystems()
    todo = [t for t in themes
            if (t.get("name") or "").strip()
            and t["name"] not in existing
            and t.get("stage") != "Retired"]
    # Same-run duplicates (shouldn't happen post-save-dedup, but cheap to guard)
    seen: set[str] = set()
    deduped: list[dict] = []
    for t in todo:
        if t["name"] not in seen:
            seen.add(t["name"])
            deduped.append(t)
    todo = deduped
    if not todo:
        return []

    # Sector context for the Haiku prompt — best-effort, advisory input only.
    sectors: dict[str, str] = {}
    try:
        all_members = sorted({tk for t in todo for tk in (t.get("tickers") or [])})
        if all_members:
            sectors = await _db.get_sectors_batch(all_members)
    except Exception as e:
        logger.warning(
            f"[theme ecosystems] sector fetch failed — assigning without sectors: {e}")

    results: list[dict] = []
    llm_budget = max_llm_calls if use_llm else 0
    for t in todo:
        res = await assign_theme_to_ecosystem(t, sectors=sectors,
                                              use_llm=llm_budget > 0)
        if res.get("llm_attempted"):
            llm_budget -= 1
        record = {"theme_name": t["name"], **res, "dry_run": dry_run}
        results.append(record)
        if dry_run:
            continue
        await _db.upsert_theme_ecosystem(t["name"], res["e_code"], res["method"])
        await _db.log_audit_event(
            THEME_ECOSYSTEM_ASSIGNED,
            summary=f"'{t['name']}' → {res['e_code']} ({res['method']})",
            detail=(f"members={', '.join((t.get('tickers') or [])[:20])} | "
                    f"{res.get('detail', '')}"),
        )
    n_llm = sum(1 for r in results if r["method"] == "haiku")
    n_un = sum(1 for r in results if r["e_code"] == E_UNASSIGNED)
    logger.info(
        f"[theme ecosystems] assigned {len(results)} theme(s) "
        f"(haiku={n_llm}, unassigned={n_un}, dry_run={dry_run})")
    return results


async def load_ecosystem_assignments() -> dict[str, str]:
    """Fail-safe fetch of the theme_name -> e_code mapping for render surfaces.
    Any DB failure degrades to {} (flat /themes fallback) — never raises."""
    try:
        from agents.market_intelligence.db import get_all_theme_ecosystems
        return await get_all_theme_ecosystems()
    except Exception as e:
        logger.warning(
            f"[theme ecosystems] mapping unavailable — flat render fallback: {e}")
        return {}


# ═════════════════════════════════════════════════════════════════════════
# 4. /themes v2 render (pure formatting — Telegram Markdown lines)
# ═════════════════════════════════════════════════════════════════════════

def _strike(text: str) -> str:
    """Unicode combining strikethrough — parse-mode independent (legacy
    Telegram Markdown has no strike entity; MarkdownV2 migration not worth
    the escaping blast radius for one decoration)."""
    return "".join(ch + "\u0336" for ch in text)


def _member_preview(tickers: list[str], theme_rs_data: dict[str, dict],
                    top_n: int = 5) -> str:
    """Top members by RS (RS>=50 filter, same as the v1 render)."""
    pairs = [
        (tk, theme_rs_data[tk]["rs_composite"])
        for tk in tickers
        if theme_rs_data.get(tk, {}).get("rs_composite") is not None
        and theme_rs_data[tk]["rs_composite"] >= 50
    ]
    pairs.sort(key=lambda x: -x[1])
    return " · ".join(f"{tk} {int(rs)}" for tk, rs in pairs[:top_n])


def _theme_line(st: dict, rank: int | None, theme_rs_data: dict[str, dict],
                indent: str = "  ") -> list[str]:
    """One rendered sub-theme (or flat-list) entry: rank + name + stage tag +
    RS + delta, then a member preview line."""
    from agents.market_intelligence.briefing import STAGE_EMOJI, _conviction_suffix
    stage = st.get("stage", "?")
    emoji = STAGE_EMOJI.get(stage, "")
    delta_str = f"  Δ{st['delta']:+.1f}" if st.get("delta") is not None else ""
    rank_str = f"#{rank} " if rank is not None else ""
    lines = [
        f"{indent}{rank_str}{emoji}*{st['name']}*{_conviction_suffix(st)}"
        f"  _[{stage}]_  RS {int(st['comp'])}{delta_str}"
    ]
    preview = _member_preview(st.get("tickers") or [], theme_rs_data)
    if preview:
        lines.append(f"{indent}    {preview}")
    return lines


def format_ecosystem_board(
    scored_themes: list[dict],
    fading: list[dict],
    theme_rs_data: dict[str, dict],
    eco_map: dict[str, str],
) -> list[str]:
    """The /themes v2 body (list of Telegram Markdown lines, no header).

    With a mapping: ecosystems ranked by boosted D3 score, header per
    ecosystem, sub-themes nested with their GLOBAL theme rank, Fading
    sub-themes struck-through inside their ecosystem, stage as a per-line
    tag, E-UNASSIGNED last. Without a mapping (pre-backfill / DB down):
    flat list ranked by comp — which already fixes the Mainstream-buried-
    below-Nascent stage-order bug (the old render grouped
    Accelerating -> Nascent -> Mainstream).

    `scored_themes` is _compute_scored_themes output (comp-desc sorted);
    `fading` is the raw Fading theme dicts it set aside.
    """
    lines: list[str] = []

    if not eco_map:
        # ── Flat fallback — ranked by comp, stage as a tag ────────────────
        for rank, st in enumerate(scored_themes, 1):
            lines.append("")
            lines.extend(_theme_line(st, rank, theme_rs_data, indent=""))
        if fading:
            fading_names = " · ".join(t.get("name", "?") for t in fading[:5])
            lines.append(f"\n🔻 _Fading: {fading_names}_")
        return lines

    # ── Ecosystem view ────────────────────────────────────────────────────
    global_rank = {st["name"]: i for i, st in enumerate(scored_themes, 1)}

    # Group active + fading per ecosystem (unmapped -> E-UNASSIGNED).
    active_by_eco: dict[str, list[dict]] = {}
    for st in scored_themes:
        active_by_eco.setdefault(eco_map.get(st["name"], E_UNASSIGNED), []).append(st)
    fading_by_eco: dict[str, list[dict]] = {}
    for t in fading:
        fading_by_eco.setdefault(eco_map.get(t.get("name"), E_UNASSIGNED), []).append(t)

    # Score input: every theme (compute filters Fading itself).
    eco_to_all: dict[str, list[dict]] = {}
    for code in set(active_by_eco) | set(fading_by_eco):
        eco_to_all[code] = (
            [{"name": st["name"], "tickers": st.get("tickers") or [],
              "stage": st.get("stage", "")} for st in active_by_eco.get(code, [])]
            + [{"name": t.get("name"), "tickers": t.get("tickers") or [],
                "stage": "Fading"} for t in fading_by_eco.get(code, [])]
        )
    scores = compute_ecosystem_scores(eco_to_all, theme_rs_data)

    tax = get_ecosystem_map()
    tax_order = {code: i for i, code in enumerate(get_ecosystem_codes())}

    def _sort_key(code: str):
        # E-UNASSIGNED pinned last; else boosted desc, taxonomy order tiebreak.
        if code == E_UNASSIGNED:
            return (1, 0.0, 0, code)
        s = scores.get(code) or {}
        return (0, -s.get("boosted", 0.0), tax_order.get(code, 999), code)

    for code in sorted(eco_to_all, key=_sort_key):
        s = scores.get(code) or {}
        disp = (tax.get(code) or {}).get("name") or ""
        title = f"*{code}{' ' + disp if disp else ''}*"
        group_active = active_by_eco.get(code, [])
        group_fading = fading_by_eco.get(code, [])

        if code == E_UNASSIGNED:
            n = len(group_active) + len(group_fading)
            lines.append(f"\n❔ {title} — {n} theme(s) awaiting mapping")
        elif not s.get("member_union"):
            lines.append(f"\n{title} — all sub-themes Fading")
        else:
            raw_i = round(s["raw"])
            boosted_i = round(s["boosted"])
            stat = (f"raw {raw_i} → boosted {boosted_i} (Δ+{boosted_i - raw_i})"
                    if s.get("boost", 0) > 0 else f"raw {raw_i}")
            lines.append(
                f"\n{title} — {stat} · {len(s['member_union'])} names "
                f"· {s['strong']} RS80+")

        for st in group_active:   # already comp-desc within the group
            lines.extend(_theme_line(st, global_rank.get(st["name"]), theme_rs_data))
        for t in group_fading:    # struck-through INSIDE the ecosystem
            lines.append(f"  🔻 {_strike(t.get('name') or '?')} _(Fading)_")

    return lines
