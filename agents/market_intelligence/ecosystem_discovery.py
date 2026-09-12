"""Ecosystem auto-discovery lane — ADR 0032 Phase 3 (D1), PLAN #471.

`E-UNASSIGNED` is the discovery substrate: themes that map to no curated bucket
accumulate there. Once a week this lane clusters them and, when a cluster is
coherent AND sustained, proposes a NEW primary ecosystem which auto-promotes
after a grace window unless the operator vetoes (the operator's 2026-07-14
refinement: promotion is auto with a one-tap opt-out, never a request that
needs a reply).

    weekly pass (Sun 09:30 ET)                  hourly sweep (:12) + boot
    ┌───────────────────────────────┐            ┌──────────────────────┐
    │ substrate = active themes     │            │ pending AND grace    │
    │   mapped E-UNASSIGNED         │            │   ended → LIVE       │
    │ → deterministic pre-cluster   │            │ dynamic bucket row   │
    │   (shared ticker OR name stem)│            │ member themes remap  │
    │ → components ≥3 themes        │            │ E-UNASSIGNED → E-new │
    │ → 1st sighting: `sighted`     │            └──────────────────────┘
    │ → 2nd sighting ≥7d later AND  │
    │   cluster age ≥14d: ONE       │   /vetoecosystem [E-CODE]
    │   Sonnet proposal → `pending` │   pending → `vetoed` (30d cooldown; a
    │   + veto alert (48h grace)    │   re-sighted vetoed cluster is skipped)
    └───────────────────────────────┘   live auto bucket → `retired` (themes
                                        back to E-UNASSIGNED, same cooldown)

Design SoT: docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md §2
(F-8 pre-cluster + single Sonnet proposal, F-9 two-sighting sustain rule,
F-10 DB-backed taxonomy extension, F-11 one veto command for both phases,
F-12 48h / 30d defaults). Two documented deviations from §2, both cost-side:
the Sonnet call runs only when a cluster is ELIGIBLE to go pending (its
second qualifying sighting), not on every sighting; and `fits_existing`,
early re-surfacing of a strengthened vetoed cluster, and the 28d
`sighted → expired` hygiene are not built (named in the #471 commit).

THE LINE: ecosystems are theme STRUCTURE. This module never touches a
detection criterion, threshold, sizing, safeguard, exit rule or trade state,
and it changes no theme's membership — a promotion re-points mapping rows in
`mi_theme_ecosystems` and nothing else. Every taxonomy mutation is audited
(`mi_audit_log`) and reversible (`/vetoecosystem <live auto code>` soft-
retires the bucket and returns its themes to E-UNASSIGNED; rows are never
deleted).

All datetimes are tz-aware ET; every entry point takes `now` so the state
machine is replayable in tests without touching the clock.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from shared import llm_thinking
from shared.output_ceilings import max_tokens_for

from agents.market_intelligence.audit_events import (
    ECOSYSTEM_AUTO_PROMOTED, ECOSYSTEM_CLUSTER_SIGHTED, ECOSYSTEM_COOLDOWN_SKIP,
    ECOSYSTEM_DISCOVERY_RAN, ECOSYSTEM_PROMOTION_ERROR, ECOSYSTEM_PROPOSED_PENDING,
    ECOSYSTEM_RETIRED, ECOSYSTEM_VETOED,
)
from agents.market_intelligence.theme_ecosystems import (
    E_UNASSIGNED, get_ecosystems, refresh_dynamic_taxonomy,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# ── Operator-tunable defaults (ADR 0032 D1 · design §2.2 / F-9 / F-12) ─────
GRACE_HOURS = 48              # pending → live unless vetoed (spans 2 briefs)
COOLDOWN_DAYS = 30            # vetoed / retired cluster is not re-proposed
MIN_CLUSTER_THEMES = 3        # ADR: "≥3 themes"
SUSTAIN_MIN_AGE_DAYS = 14     # ADR: "sustained ≥2 weeks" — oldest member's assigned_at
RESIGHT_MIN_DAYS = 7          # F-9: two sightings ≥7d apart
RESIGHT_MIN_OVERLAP = 0.5     # ≥50% of the earlier sighting's themes still present
MAX_LLM_CLUSTERS_PER_RUN = 2  # cost cap — ONE Sonnet call per eligible cluster
NAME_TOKEN_MIN_LEN = 5        # name-stem edge: shared token of ≥5 chars
# Tokens too generic to link two theme NAMES on their own.
_NAME_STOPWORDS = frozenset({
    "theme", "themes", "stocks", "stock", "sector", "sectors", "growth",
    "leaders", "leader", "plays", "platforms", "platform", "companies",
    "company", "market", "markets", "global", "emerging", "select", "names",
    "small", "large", "index", "equity", "equities", "capital", "services",
    "solutions", "technology", "technologies", "industry", "industrial",
    "industrials", "infrastructure", "systems", "group", "holdings",
})
E_CODE_RE = re.compile(r"^E-[A-Z0-9]{2,8}$")
VETO_COMMAND = "/vetoecosystem"


# ═════════════════════════════════════════════════════════════════════════
# 1. Deterministic pre-cluster — PURE, no I/O
# ═════════════════════════════════════════════════════════════════════════

def _name_tokens(name: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", (name or "").lower())
        if len(t) >= NAME_TOKEN_MIN_LEN and t not in _NAME_STOPWORDS
    }


def cluster_unassigned_themes(themes: list[dict]) -> list[list[dict]]:
    """Connected components of the substrate graph: an edge joins two themes
    iff they share ≥1 ticker OR ≥1 name token (≥5 chars, not a stopword).
    Only components of ≥ MIN_CLUSTER_THEMES themes are returned — nothing
    smaller ever reaches the LLM (the ADR-0025 Stage-A-proposes idiom).
    Deterministic: members sorted by name, components by size desc then name.
    """
    n = len(themes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    tick = [{str(t).upper() for t in (th.get("tickers") or [])} for th in themes]
    toks = [_name_tokens(th.get("name") or "") for th in themes]
    for i in range(n):
        for j in range(i + 1, n):
            if (tick[i] & tick[j]) or (toks[i] & toks[j]):
                union(i, j)

    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(themes[i])
    out = [sorted(g, key=lambda t: t.get("name") or "")
           for g in groups.values() if len(g) >= MIN_CLUSTER_THEMES]
    out.sort(key=lambda g: (-len(g), g[0].get("name") or ""))
    return out


def cluster_age_days(cluster: list[dict], now: datetime) -> int:
    """Age = days since the EARLIEST `assigned_at` among members (design §2.1
    step 3). A member with no mapping row contributes no age."""
    stamps = [t.get("assigned_at") for t in cluster if t.get("assigned_at")]
    if not stamps:
        return 0
    return max(0, (now - min(stamps)).days)


def _overlap(cluster_names: set[str], stored: list[str] | None) -> float:
    """Fraction of the STORED sighting's themes still present in the cluster."""
    s = set(stored or [])
    if not s:
        return 0.0
    return len(cluster_names & s) / len(s)


def _best_match(cluster_names: set[str], rows: list[dict]) -> dict | None:
    best, best_ov = None, 0.0
    for r in rows:
        ov = _overlap(cluster_names, r.get("member_themes"))
        if ov >= RESIGHT_MIN_OVERLAP and ov > best_ov:
            best, best_ov = r, ov
    return best


# ═════════════════════════════════════════════════════════════════════════
# 2. The single LLM proposal (Sonnet, forced tool, scratchpad-first)
# ═════════════════════════════════════════════════════════════════════════

_PROPOSE_TOOL = {
    "name": "propose_ecosystem",
    "description": (
        "Decide whether a cluster of currently-unassigned stock-market themes "
        "forms ONE coherent new primary ecosystem, and if so propose it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "REQUIRED FIRST. Reason before deciding: (1) what single "
                    "narrative, if any, unites these themes' theses and members; "
                    "(2) whether an EXISTING ecosystem already covers it (then "
                    "abstain); (3) the decision."
                ),
            },
            "decision": {"type": "string", "enum": ["propose", "abstain"]},
            "e_code": {"type": "string",
                       "description": "New code, format E-XXXX (2-8 uppercase "
                                      "letters/digits), not an existing code."},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "keyword_stems": {"type": "array", "items": {"type": "string"},
                              "description": "≥3 lowercase substrings that "
                                             "identify this ecosystem's theses."},
            "exemplars": {"type": "array", "items": {"type": "string"},
                          "description": "Anchor tickers, drawn from the members."},
            "member_themes": {"type": "array", "items": {"type": "string"},
                              "description": "The cluster themes (exact names) "
                                             "that belong — ≥3."},
            "evidence": {"type": "string",
                         "description": "1-2 lines: why this is ONE narrative."},
        },
        "required": ["analysis_scratchpad", "decision"],
    },
}


def _build_proposal_prompt(cluster: list[dict], taxonomy: list[dict]) -> str:
    tax_lines = [f"- {e['e_code']} — {e.get('name', '')}: {e.get('description', '')}"
                 for e in taxonomy if e.get("e_code") != E_UNASSIGNED]
    theme_lines = []
    for t in cluster:
        members = ", ".join(list(t.get("tickers") or [])[:15])
        theme_lines.append(
            f"- {t.get('name', '')} [{t.get('stage', '?')}]: "
            f"{(t.get('description') or '')[:300]}\n    members: {members}")
    return f"""You maintain a FIXED taxonomy of primary stock-market ecosystems. A cluster of
themes has accumulated OUTSIDE every existing bucket. Decide whether they form ONE
coherent NEW primary ecosystem.

EXISTING TAXONOMY (a proposal must not duplicate any of these):
{chr(10).join(tax_lines)}

UNASSIGNED THEME CLUSTER:
{chr(10).join(theme_lines)}

Rules:
- Propose ONLY if the themes share one narrative that no existing bucket covers.
- If most of them really belong in an existing bucket, ABSTAIN.
- A proposal needs: a new e_code (E-XXXX), a name, a one-line description,
  ≥3 keyword_stems, exemplar tickers from the members, the member_themes (≥3,
  exact names from the cluster), and 1-2 lines of evidence.

Call `propose_ecosystem` with your reasoning in `analysis_scratchpad` first."""


def validate_proposal(data: dict, cluster: list[dict], taxonomy: list[dict]) -> dict | None:
    """Pure validation of a tool result. None = abstain / unusable (the caller
    treats both the same: no state change, heartbeat only)."""
    if (data or {}).get("decision") != "propose":
        return None
    code = str(data.get("e_code") or "").strip().upper()
    if not E_CODE_RE.match(code) or code == E_UNASSIGNED:
        return None
    existing = {e.get("e_code") for e in taxonomy}
    if code in existing:
        return None   # collision with the effective taxonomy (YAML ∪ dynamic)
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    cluster_names = {t.get("name") for t in cluster}
    members = [str(m).strip() for m in (data.get("member_themes") or [])]
    members = [m for m in dict.fromkeys(members) if m in cluster_names]
    if len(members) < MIN_CLUSTER_THEMES:
        return None
    stems = [str(s).strip().lower() for s in (data.get("keyword_stems") or []) if str(s).strip()]
    if len(stems) < 3:
        return None
    union = {str(tk).upper() for t in cluster for tk in (t.get("tickers") or [])}
    exemplars = [str(x).strip().upper() for x in (data.get("exemplars") or [])]
    exemplars = [x for x in dict.fromkeys(exemplars) if x in union][:12]
    return {
        "e_code": code,
        "name": name[:80],
        "description": str(data.get("description") or "").strip()[:400],
        "keyword_stems": stems[:12],
        "exemplars": exemplars,
        "member_themes": members,
        "evidence": str(data.get("evidence") or "").strip()[:400],
    }


async def propose_ecosystem_via_llm(cluster: list[dict], taxonomy: list[dict]) -> dict | None:
    """ONE forced-tool Sonnet call per eligible cluster. Returns a validated
    proposal or None (abstain / no tool call / invalid). Raises on transport
    errors — the weekly pass catches and audits."""
    from agents.market_intelligence.theme_engine import _get_anthropic_client
    from shared.llm_models import SYNTHESIS_MODEL

    client = _get_anthropic_client()
    resp = await client.messages.create(
        model=SYNTHESIS_MODEL,
        max_tokens=max_tokens_for("ecosystem_discovery_proposal"),
        thinking=llm_thinking.DISABLED,   # forced tool + scratchpad = the reasoning surface
        tools=[_PROPOSE_TOOL],
        tool_choice={"type": "tool", "name": "propose_ecosystem"},
        messages=[{"role": "user", "content": _build_proposal_prompt(cluster, taxonomy)}],
    )
    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    await log_anthropic_call_safe(model=SYNTHESIS_MODEL,
                                  caller="ecosystem_discovery_proposal", response=resp)
    block = next((b for b in (getattr(resp, "content", None) or [])
                  if getattr(b, "type", "") == "tool_use"), None)
    data = dict(getattr(block, "input", None) or {}) if block is not None else {}
    return validate_proposal(data, cluster, taxonomy)


# ═════════════════════════════════════════════════════════════════════════
# 3. Operator surfaces — the veto alert + the confirm
# ═════════════════════════════════════════════════════════════════════════

def format_veto_alert(p: dict, grace_ends_at: datetime, n_pending: int) -> str:
    """The decision alert (HTML). Carries the action: a bare leading
    `/vetoecosystem` is tappable in Telegram and vetoes the ONE pending
    proposal — the true one-tap (`/promotetheme` idiom, ADR 0032 D1)."""
    from shared.telegram_format import b, code, esc, i

    themes = " · ".join(p.get("member_themes") or [])
    hours = GRACE_HOURS
    ends = grace_ends_at.astimezone(_ET).strftime("%a %H:%M ET")
    tap = (f"▶ Tap {VETO_COMMAND} to veto"
           if n_pending <= 1 else
           f"▶ Veto: {code(VETO_COMMAND + ' ' + p['e_code'])} ({n_pending} pending)")
    lines = [
        f"🆕 {b(f'New ecosystem auto-promoting in {hours}h')}: "
        f"{esc(p['e_code'])} — {esc(p.get('name') or '')}",
        f"Themes: {i(themes)}",
    ]
    if p.get("evidence"):
        lines.append(i(p["evidence"]))
    lines.append(tap)
    lines.append(f"No action → live {esc(ends)}. {COOLDOWN_DAYS}d cooldown on veto.")
    return "\n".join(lines)


def format_promoted_confirm(p: dict, n_remapped: int) -> str:
    from shared.telegram_format import b, code, esc, i
    themes = " · ".join(p.get("member_themes") or [])
    return (f"✅ {b('Ecosystem live')}: {esc(p['e_code'])} — {esc(p.get('name') or '')}\n"
            f"{n_remapped} theme(s) remapped: {i(themes)}\n"
            f"Retire later with {code(VETO_COMMAND + ' ' + p['e_code'])}.")


async def _send_html(text: str) -> bool:
    from agents.market_intelligence.briefing import send_telegram_message
    return bool(await send_telegram_message(text, parse_mode="HTML"))


# ═════════════════════════════════════════════════════════════════════════
# 4. The weekly pass
# ═════════════════════════════════════════════════════════════════════════

Proposer = Callable[[list[dict], list[dict]], Awaitable[dict | None]]


async def run_ecosystem_discovery(
    *, now: datetime | None = None, use_llm: bool = True,
    proposer: Proposer | None = None,
) -> dict[str, Any]:
    """Weekly ecosystem discovery (Sun 09:30 ET). Never raises; every run
    writes the `ecosystem_discovery_ran` heartbeat (G8: the common early
    outcome is an idle run on a <3-theme substrate, and an idle run that
    leaves no trace is indistinguishable from a dead job)."""
    from agents.market_intelligence import db as _db

    now = now or datetime.now(_ET)
    out: dict[str, Any] = {"substrate_n": 0, "clusters": 0, "sighted": [],
                           "pending": [], "cooldown_skips": [], "abstained": [],
                           "errors": []}
    await refresh_dynamic_taxonomy()
    try:
        themes = await _db.get_active_themes()
        rows = await _db.get_theme_ecosystem_rows()
        proposals = await _db.get_ecosystem_proposals(
            ["sighted", "pending", "vetoed", "retired"])
    except Exception as e:
        logger.error(f"[ecosystem discovery] substrate read failed: {e}", exc_info=True)
        out["errors"].append(f"substrate: {type(e).__name__}: {e}")
        await _db.log_audit_event(ECOSYSTEM_DISCOVERY_RAN,
                                  "ecosystem discovery: substrate read FAILED",
                                  json.dumps(out, default=str))
        return out

    mapping = {r["theme_name"]: r for r in rows}
    substrate: list[dict] = []
    for t in themes:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        r = mapping.get(name)
        if r is None or r.get("e_code") == E_UNASSIGNED:
            substrate.append({**t, "name": name,
                              "assigned_at": r.get("assigned_at") if r else None})
    out["substrate_n"] = len(substrate)
    clusters = (cluster_unassigned_themes(substrate)
                if len(substrate) >= MIN_CLUSTER_THEMES else [])
    out["clusters"] = len(clusters)

    llm_budget = MAX_LLM_CLUSTERS_PER_RUN if use_llm else 0
    propose = proposer or propose_ecosystem_via_llm
    n_pending_now = sum(1 for r in proposals if r["status"] == "pending")

    for cluster in clusters:
        names = {t["name"] for t in cluster}
        label = " · ".join(sorted(names))[:200]

        # (a) cooldown — a vetoed / retired cluster is NOT re-proposed (the
        #     second half of the DoD's WOULD-FAIL-IF: without this a vetoed
        #     cluster is re-sighted next Sunday and promotes 48h later).
        cd_rows = [r for r in proposals
                   if r["status"] in ("vetoed", "retired")
                   and r.get("cooldown_until") and r["cooldown_until"] > now]
        m = _best_match(names, cd_rows)
        if m is not None:
            out["cooldown_skips"].append(m.get("e_code") or m["id"])
            await _db.log_audit_event(
                ECOSYSTEM_COOLDOWN_SKIP,
                f"cluster matches {m['status']} proposal #{m['id']} "
                f"{m.get('e_code') or ''} — cooldown until {m['cooldown_until']:%Y-%m-%d}",
                label)
            continue

        # (b) already in grace — nothing to do until the sweep / a veto.
        if _best_match(names, [r for r in proposals if r["status"] == "pending"]):
            continue

        # (c) sighted lineage.
        m = _best_match(names, [r for r in proposals if r["status"] == "sighted"])
        age = cluster_age_days(cluster, now)
        if m is None:
            try:
                pid = await _db.insert_ecosystem_proposal(
                    e_code=None, name=None, description=None, keyword_stems=[],
                    exemplars=[], member_themes=sorted(names), evidence=None,
                    status="sighted", sighted_at=now)
            except Exception as e:
                # LOUD: a sighting that fails to persist would make the lane read
                # as "idle" forever while its heartbeat still fires (the #644 class).
                logger.error(f"[ecosystem discovery] sighting insert failed: {e}",
                             exc_info=True)
                out["errors"].append(f"insert: {type(e).__name__}: {e}")
                await _db.log_audit_event(ECOSYSTEM_PROMOTION_ERROR,
                                          f"sighting insert FAILED for cluster: {label}",
                                          f"{type(e).__name__}: {e}"[:300])
                continue
            out["sighted"].append(pid)
            await _db.log_audit_event(
                ECOSYSTEM_CLUSTER_SIGHTED,
                f"first sighting #{pid}: {len(names)} unassigned theme(s), age {age}d",
                label)
            continue

        since_first = (now - m["first_sighted_at"]).days
        qualifies = since_first >= RESIGHT_MIN_DAYS and age >= SUSTAIN_MIN_AGE_DAYS
        if not qualifies or llm_budget <= 0:
            await _db.touch_ecosystem_proposal_sighting(m["id"], sorted(names), now)
            continue

        llm_budget -= 1
        try:
            prop = await propose(cluster, get_ecosystems())
        except Exception as e:
            logger.warning(f"[ecosystem discovery] proposal call failed: {e}")
            out["errors"].append(f"llm: {type(e).__name__}: {e}")
            await _db.log_audit_event(ECOSYSTEM_PROMOTION_ERROR,
                                      f"proposal LLM call failed for #{m['id']}",
                                      f"{type(e).__name__}: {e}"[:300])
            continue
        if not prop:
            out["abstained"].append(m["id"])
            await _db.touch_ecosystem_proposal_sighting(m["id"], sorted(names), now)
            continue

        grace_ends = now + timedelta(hours=GRACE_HOURS)
        ok = await _db.mark_ecosystem_proposal_pending(
            m["id"], e_code=prop["e_code"], name=prop["name"],
            description=prop["description"], keyword_stems=prop["keyword_stems"],
            exemplars=prop["exemplars"], member_themes=prop["member_themes"],
            evidence=prop["evidence"], pending_at=now, grace_ends_at=grace_ends)
        if not ok:
            continue   # a concurrent pass got there first
        n_pending_now += 1
        out["pending"].append(prop["e_code"])
        await _db.log_audit_event(
            ECOSYSTEM_PROPOSED_PENDING,
            f"#{m['id']} {prop['e_code']} — {prop['name']}: auto-promotes "
            f"{grace_ends.astimezone(_ET):%Y-%m-%d %H:%M ET} unless vetoed",
            json.dumps({"member_themes": prop["member_themes"],
                        "exemplars": prop["exemplars"], "evidence": prop["evidence"]}))
        # THE ALERT — the veto surface. A pending row nobody was told about is
        # a promotion with no opt-out, so a failed send is audited loudly.
        try:
            sent = await _send_html(format_veto_alert(prop, grace_ends, n_pending_now))
        except Exception as e:
            sent = False
            logger.error(f"[ecosystem discovery] veto alert send raised: {e}")
        if not sent:
            await _db.log_audit_event(
                ECOSYSTEM_PROMOTION_ERROR,
                f"veto alert NOT delivered for #{m['id']} {prop['e_code']} — "
                f"grace still ends {grace_ends.astimezone(_ET):%Y-%m-%d %H:%M ET}",
                "send_telegram_message returned False / raised")

    await _db.log_audit_event(
        ECOSYSTEM_DISCOVERY_RAN,
        f"ecosystem discovery: substrate={out['substrate_n']} clusters={out['clusters']} "
        f"sighted={len(out['sighted'])} pending={len(out['pending'])} "
        f"cooldown_skips={len(out['cooldown_skips'])} errors={len(out['errors'])}",
        json.dumps(out, default=str))
    return out


# ═════════════════════════════════════════════════════════════════════════
# 5. The grace sweep — pending → live
# ═════════════════════════════════════════════════════════════════════════

async def sweep_ecosystem_grace(*, now: datetime | None = None) -> dict[str, Any]:
    """Hourly (+ once at boot). Claims every pending proposal whose grace has
    ended (status-guarded UPDATE — a double sweep promotes once), then per
    row: dynamic bucket row → remap member themes → refresh the loader →
    audit → Telegram confirm. A vetoed row is never claimed: the claim reads
    `status='pending'` only."""
    from agents.market_intelligence import db as _db

    now = now or datetime.now(_ET)
    out: dict[str, Any] = {"promoted": [], "errors": []}
    try:
        due = await _db.claim_due_ecosystem_proposals(now)
    except Exception as e:
        logger.error(f"[ecosystem sweep] claim failed: {e}", exc_info=True)
        out["errors"].append(f"claim: {type(e).__name__}: {e}")
        return out
    for r in due:
        try:
            await _db.insert_dynamic_ecosystem(
                e_code=r["e_code"], name=r.get("name") or r["e_code"],
                description=r.get("description"),
                keyword_stems=list(r.get("keyword_stems") or []),
                exemplars=list(r.get("exemplars") or []), source="auto",
                proposal_id=r["id"], created_at=now)
            n = await _db.remap_theme_ecosystems(
                list(r.get("member_themes") or []), r["e_code"], "ecosystem_discovery")
            await refresh_dynamic_taxonomy()
            out["promoted"].append(r["e_code"])
            await _db.log_audit_event(
                ECOSYSTEM_AUTO_PROMOTED,
                f"#{r['id']} {r['e_code']} — {r.get('name') or ''} LIVE "
                f"(grace ended, no veto); {n} theme(s) remapped",
                json.dumps({"member_themes": list(r.get("member_themes") or []),
                            "remapped": n}, default=str))
            try:
                await _send_html(format_promoted_confirm(r, n))
            except Exception as e:   # the promotion stands; only the confirm failed
                logger.warning(f"[ecosystem sweep] confirm send failed: {e}")
        except Exception as e:
            logger.error(f"[ecosystem sweep] promote failed for #{r.get('id')}: {e}",
                         exc_info=True)
            out["errors"].append(f"#{r.get('id')}: {type(e).__name__}: {e}")
            await _db.log_audit_event(
                ECOSYSTEM_PROMOTION_ERROR,
                f"promote FAILED for #{r.get('id')} {r.get('e_code')} — row is 'live' "
                f"but the bucket/remap may be partial; operator check",
                f"{type(e).__name__}: {e}"[:300])
    return out


# ═════════════════════════════════════════════════════════════════════════
# 6. The veto — `/vetoecosystem [E-CODE]`
# ═════════════════════════════════════════════════════════════════════════

async def veto_ecosystem(arg: str | None, *, now: datetime | None = None) -> dict[str, Any]:
    """The one veto command, two phases (F-11):
      bare            → exactly ONE pending → veto it (the one-tap); 0 → usage;
                        >1 → list.
      `E-CODE`        → a pending proposal → veto (30d cooldown);
                        else a LIVE auto bucket → retro-retire (soft-delete,
                        themes back to E-UNASSIGNED, same cooldown);
                        a YAML bucket → refused (operator edits the YAML).
    Returns a status dict; `render_veto_result` turns it into operator text."""
    from agents.market_intelligence import db as _db
    from agents.market_intelligence.theme_ecosystems import _load_taxonomy

    now = now or datetime.now(_ET)
    code = (arg or "").strip().upper() or None
    pending = await _db.get_ecosystem_proposals(["pending"])
    dyn = await _db.get_dynamic_ecosystems(active_only=True)
    live_codes = [d["e_code"] for d in dyn]

    if code is None:
        if len(pending) == 1:
            target = pending[0]
        elif not pending:
            return {"status": "none_pending", "live_auto": live_codes}
        else:
            return {"status": "ambiguous", "pending": [p["e_code"] for p in pending]}
    else:
        if code in {e.get("e_code") for e in _load_taxonomy()}:
            return {"status": "yaml_refused", "e_code": code}
        target = next((p for p in pending if p.get("e_code") == code), None)
        if target is None:
            d = next((d for d in dyn if d["e_code"] == code), None)
            if d is not None:
                return await _retro_retire(d, now)
            return {"status": "not_found", "e_code": code,
                    "pending": [p["e_code"] for p in pending], "live_auto": live_codes}

    cooldown_until = now + timedelta(days=COOLDOWN_DAYS)
    snapshot = {"member_theme_count": len(target.get("member_themes") or []),
                "member_themes": list(target.get("member_themes") or []),
                "vetoed_at": now.isoformat()}
    ok = await _db.mark_ecosystem_proposal_vetoed(
        target["id"], now=now, cooldown_until=cooldown_until, snapshot=snapshot)
    if not ok:
        return {"status": "raced", "e_code": target.get("e_code")}
    await _db.log_audit_event(
        ECOSYSTEM_VETOED,
        f"#{target['id']} {target.get('e_code')} — {target.get('name') or ''} VETOED; "
        f"themes stay E-UNASSIGNED; cooldown until {cooldown_until:%Y-%m-%d}",
        json.dumps(snapshot))
    return {"status": "vetoed", "e_code": target.get("e_code"),
            "name": target.get("name"), "cooldown_until": cooldown_until,
            "member_themes": list(target.get("member_themes") or [])}


async def _retro_retire(d: dict, now: datetime) -> dict[str, Any]:
    """Reversibility: soft-retire a LIVE auto bucket, return its themes to
    E-UNASSIGNED, cool the lineage down. Never deletes a row."""
    from agents.market_intelligence import db as _db

    code = d["e_code"]
    if not await _db.retire_dynamic_ecosystem(code, now):
        return {"status": "not_found", "e_code": code, "pending": [], "live_auto": []}
    names = await _db.get_theme_names_in_ecosystem(code)
    n = await _db.remap_theme_ecosystems(names, E_UNASSIGNED, "ecosystem_retired")
    cooldown_until = now + timedelta(days=COOLDOWN_DAYS)
    if d.get("proposal_id"):
        await _db.mark_ecosystem_proposal_vetoed(
            d["proposal_id"], now=now, cooldown_until=cooldown_until,
            snapshot={"member_theme_count": len(names), "member_themes": names,
                      "retired_at": now.isoformat()},
            new_status="retired")
    await refresh_dynamic_taxonomy()
    await _db.log_audit_event(
        ECOSYSTEM_RETIRED,
        f"{code} — {d.get('name') or ''} RETIRED by operator; {n} theme(s) back to "
        f"E-UNASSIGNED; cooldown until {cooldown_until:%Y-%m-%d}",
        json.dumps({"themes": names}))
    return {"status": "retired", "e_code": code, "name": d.get("name"),
            "n_remapped": n, "cooldown_until": cooldown_until}


def render_veto_result(res: dict) -> str:
    """Operator text (legacy Markdown, the /promotetheme surface's mode)."""
    st = res.get("status")
    if st == "vetoed":
        themes = ", ".join(res.get("member_themes") or []) or "—"
        return (f"🚫 Vetoed *{res.get('e_code')}* — {res.get('name') or ''}.\n"
                f"Themes stay unassigned: {themes}\n"
                f"Not re-proposed before {res['cooldown_until']:%Y-%m-%d}.")
    if st == "retired":
        return (f"🗑 Retired *{res.get('e_code')}* — {res.get('name') or ''}. "
                f"{res.get('n_remapped', 0)} theme(s) back to E-UNASSIGNED; "
                f"not re-proposed before {res['cooldown_until']:%Y-%m-%d}.")
    if st == "none_pending":
        live = res.get("live_auto") or []
        tail = ("\nLive auto ecosystems (retire with `/vetoecosystem <code>`): "
                + ", ".join(live)) if live else "\nNo auto-promoted ecosystems are live."
        return "Nothing is pending a veto." + tail
    if st == "ambiguous":
        return ("Several proposals are pending — name one:\n"
                + "\n".join(f"  • `/vetoecosystem {c}`" for c in res.get("pending") or []))
    if st == "yaml_refused":
        return (f"*{res.get('e_code')}* is a curated bucket (theme_ecosystems.yaml) — "
                f"only auto-promoted ecosystems can be vetoed/retired here.")
    if st == "raced":
        return (f"*{res.get('e_code')}* already went live before the veto landed — "
                f"retire it with `/vetoecosystem {res.get('e_code')}`.")
    pend = res.get("pending") or []
    live = res.get("live_auto") or []
    parts = [f"No pending proposal or live auto ecosystem matches `{res.get('e_code')}`."]
    if pend:
        parts.append("Pending: " + ", ".join(pend))
    if live:
        parts.append("Live auto: " + ", ".join(live))
    return "\n".join(parts)
