"""#651 — the judge names groups our theme engine does not have; capture them, then measure
how LATE the engine is.

THE OBSERVATION (operator 2026-09-12): *"on EP alerts, the judge will say it may have spotted a
theme which isn't in our theme list."* Confirmed in the data — of 150 alerts with a stored
rationale since 2026-07-01, 105 mention a theme, and they name real things: SEI 09-08 *"AI
data-center power buildout"*, SNOW 09-03 *"the live AI infrastructure theme"*, AGX 09-03 *"ag
re-rating"* and *"LNG export cohorts"* while saying no active theme matched. The judge's
structured verdict has no field for any of this; it survives only as prose in
`mi_ep_alerts.judge_rationale`, parsed by nothing. (#322's feed writes a sector+date STUB for
the fire, deliberately never the name — see judge_theme_gap.py. This module captures the NAME.)

THE GOAL is not a list of names. The whole theme north-star is EARLINESS (subtle RS -> early
theme -> mature -> own the leaders before mainstream), and there is no number for how late the
engine is. The mechanism: where a judge-named group RECURS across two or more tickers before the
engine creates a matching theme, the gap between those dates IS the lateness, in days.

WHY RECURRENCE IS THE FILTER (load-bearing, no tuned threshold): one mention is a story, not a
theme. Two names moving under one story is the definition of a theme, so recurrence drops the
noise without a score. `recurring_groups` requires >= 2 DISTINCT TICKERS, never 2 mentions.

WHY A MODEL PASS, NOT A REGEX: a conservative pattern pass over the same rationales returned 200
matches, mostly sentence fragments ("and there is no active", "aligns with a hot"). A heuristic
extractor would bury the real candidates in junk. Haiku 4.5 at ~300 in / ~60 out tokens per
alert priced the whole historical pass at ~$0.07 and the forward flow at pennies a month —
operator-approved 2026-09-12.

THE SURFACE (second half, 2026-09-12 — measured first: of 45 groups over 144 alerts, 7 recurred
across >=2 tickers and 2 were named 8-11 days BEFORE the engine had the theme; 2 more matched
nothing we ever had). A silent list is the same trap as a fill that quietly stops — nobody reads
it, nothing happens. `surface_new_candidates` (nightly, after the sweep) fires when a group
reaches its SECOND distinct ticker and matches no theme the engine EVER held (same
`lead_time_report` rule the operator already read): it SEEDS a shadow candidate
(`db.persist_judge_named_seed`, source 'judge_named' — the `persist_reactivation_seed` shape)
and pages ONCE with the EXISTING one-tap promote button (`theme_synthesis.build_synthesis_keyboard`
-> `tpromo:` -> `/promotetheme_id` -> `theme_engine.promote_candidate_by_name`). No creation path
is invented; the engine's own `_PROMOTE_MIN_MEMBERS` bar applies at the tap. ~one page a month.
  - The trigger is at 2 tickers, the promote bar is 3: the alert says how many names it has;
    while the judge keeps naming the group the seed is re-written nightly with the CURRENT
    ticker set (`SEED_REFRESH_DAYS`), so the original alert's button goes live when a third
    name lands — the button resolves the name against the newest candidate row.
  - Dedupe is per group key, FOREVER (`db.get_judge_named_surfaced_keys`): a 3rd/4th ticker
    never re-pages. The dedupe row is written only AFTER a successful send — a lost page
    retries next night (a duplicate is loud; a silent loss is the failure this exists to end).
  - LIVENESS: every evaluation writes a `judge_named_theme_candidates_evaluated` audit row
    with counts and, per recurring group, which theme suppressed it. A month with no page
    reads the SAME whether the trigger works or died; that row is what tells them apart.

THE LINE (never crossed here): a ZERO-AUTHORITY post-process over text the judge already wrote.
  - Does NOT touch the judge's prompt or call path, so it cannot move a grade.
  - Writes ONLY `mi_judge_named_themes`, a SHADOW CANDIDATE row (never `mi_themes`) and audit
    rows. Creates no theme, moves no membership, reaches no grade / entry / exit / size.
    Nothing here promotes — the tap is HIS; the seed is a candidate, not a theme.
  - Anti-circularity as #322: the judge's own inputs (`db.get_narrative_theme_candidates`,
    `ep_grade_judge.assemble_judge_inputs`) never select from this table, and the
    'judge_named' seed source is outside AUTO_PROMOTE_THEME_SOURCES, the judge's narrative
    feed AND the #491 assignment-pool exemption (SEEDED_ASSIGN_SOURCES, an operator-ruled
    scope) — pinned by tests/test_651_judge_named_themes.py — so a judge inference can never
    become the judge's own future corroborating evidence.
  - Off the alert hot path by construction: the NIGHTLY sweep (`extract_pending`, scheduler
    job `judge_named_themes_extract`) does the work; the 5-minute scan never waits on it.

COST DISCIPLINE (CLAUDE.md): capture ONCE, read many. `extract_pending` appends every raw model
output to a JSONL capture file BEFORE the DB write; the report reads from the table OR the
capture, so a paid pass is never re-run to re-read it. A sentinel row (`NONE_KEY`) marks an
alert whose rationale named nothing, so the sweep never re-bills it; a FAILED extraction writes
nothing and is retried the next night.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from agents.market_intelligence.db import (
    JUDGE_NAMED_CANDIDATE_EVENT, JUDGE_NAMED_EVALUATED_EVENT, JUDGE_NAMED_SEED_SOURCE,
    get_judge_named_surfaced_keys, get_judge_named_theme_rows, get_judge_named_themes_pending,
    get_pool, get_theme_name_history, get_theme_rename_edges, insert_judge_named_theme_row,
    log_audit_event, persist_judge_named_seed, resolve_theme_aliases,
)
from shared.llm_models import JUDGE_NAMED_THEMES_MODEL, pricing_for
from shared.llm_response import is_truncated, usage_tokens
from shared.output_ceilings import max_tokens_for

logger = logging.getLogger(__name__)

# Sentinel canonical_key for "extracted, the rationale named no group". A ROW, not an absence,
# so the pending query can tell "never looked" from "looked, nothing there".
NONE_KEY = "(none)"
MAX_EVIDENCE_LEN = 300
MAX_GROUPS_PER_ALERT = 5
# The first alert with a judge rationale worth reading (the grounded-judge era).
DEFAULT_SINCE = date(2026, 7, 1)

_SEM = asyncio.Semaphore(4)
_client = None


# ═══════════════════════════════════════════════════════════════════════════════════
# Extraction — the one paid call, structured by a forced tool (no string parsing)

EXTRACT_TOOL: dict[str, Any] = {
    "name": "record_named_groups",
    "description": (
        "Record every GROUP / THEME / COHORT the judge's rationale says this stock trades "
        "under. A group is a story shared by several companies (e.g. 'AI data-center power "
        "buildout', 'LNG export', 'bitcoin miners', 'GLP-1'), NOT the company itself, NOT the "
        "catalyst type (an earnings beat, a contract), NOT a bare sector word unless the "
        "rationale frames it as the story the stock is moving with. Zero groups is a valid "
        "and common answer — record nothing rather than invent a group."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "maxItems": MAX_GROUPS_PER_ALERT,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The group in the judge's own words, short (2-6 words).",
                        },
                        "canonical_key": {
                            "type": "string",
                            "description": (
                                "A 2-4 word lowercase hyphenated label for the SAME group that "
                                "another alert would also produce for it — e.g. "
                                "'ai-data-center-power', 'lng-export', 'bitcoin-miner'. Drop "
                                "filler like 'theme', 'cohort', 'live', 'the'."
                            ),
                        },
                        "evidence": {
                            "type": "string",
                            "description": (
                                "The judge's own sentence (verbatim, <=300 chars) that names "
                                "this group."
                            ),
                        },
                        "judge_says_untracked": {
                            "type": "boolean",
                            "description": (
                                "true if the rationale states that NO active/tracked theme "
                                "matched this group; false if it says the group IS a tracked "
                                "theme; omit if it does not say."
                            ),
                        },
                    },
                    "required": ["name", "canonical_key", "evidence"],
                },
            },
        },
        "required": ["groups"],
    },
}

_SYSTEM = (
    "You are a precise extractor reading a trading judge's written rationale for one stock's "
    "gap-up. Your ONLY job is to record the market GROUP(S) the rationale says the stock is "
    "moving with — the shared story several companies trade under. Quote the judge; never "
    "infer a group the text does not name. If the text names none, return an empty list."
)


def build_prompt(ticker: str, alert_date: Any, rationale: str) -> str:
    ad = alert_date.isoformat() if hasattr(alert_date, "isoformat") else str(alert_date)
    return (
        f"Ticker: {ticker}\nAlert date: {ad}\n\nJudge rationale:\n\"\"\"\n{rationale}\n\"\"\"\n\n"
        "Record every group/theme/cohort this rationale names the stock as trading under. "
        "Empty is fine."
    )


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _client


def _coerce_groups(raw: Any) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    seen: set[str] = set()
    for item in raw[:MAX_GROUPS_PER_ALERT]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:120]
        key = normalize_key(str(item.get("canonical_key") or "") or name)
        if not key or key in seen:
            continue
        seen.add(key)
        untracked = item.get("judge_says_untracked")
        out.append({
            "name": name or key,
            "canonical_key": key,
            "evidence": str(item.get("evidence") or "").strip()[:MAX_EVIDENCE_LEN],
            "judge_says_untracked": bool(untracked) if isinstance(untracked, bool) else None,
        })
    return out


async def extract_named_themes(ticker: str, alert_date: Any, rationale: "str | None") -> "dict | None":
    """ONE Haiku call over one stored rationale. Returns
    {"groups": [...], "input_tokens", "output_tokens", "model"} — an EMPTY groups list is the
    common, valid answer (nothing named) and costs nothing when the rationale is blank.
    Returns None on ANY failure (client error, truncation, no tool block): fail-open, never
    raises, and the caller leaves the alert pending so the next night retries it."""
    text = (rationale or "").strip()
    if not text:
        return {"groups": [], "input_tokens": 0, "output_tokens": 0, "model": None}
    prompt = build_prompt(ticker, alert_date, text)
    try:
        import anthropic
        async with _SEM:
            resp = None
            for attempt in range(2):
                try:
                    resp = await _get_client().messages.create(
                        model=JUDGE_NAMED_THEMES_MODEL,
                        max_tokens=max_tokens_for("judge_named_themes"),
                        system=_SYSTEM,
                        tools=[EXTRACT_TOOL],
                        tool_choice={"type": "tool", "name": EXTRACT_TOOL["name"]},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt == 1:
                        raise
                    await asyncio.sleep(2 + attempt)
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=JUDGE_NAMED_THEMES_MODEL, caller="judge_named_themes",
                                      response=resp)
        if is_truncated(resp):
            logger.warning(f"judge_named_themes: {ticker} {alert_date} response TRUNCATED at "
                           f"max_tokens={max_tokens_for('judge_named_themes')} — discarded")
            return None
        block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if block is None:
            logger.warning(f"judge_named_themes: {ticker} {alert_date} no tool_use block")
            return None
        usage = usage_tokens(resp) or {}
        return {
            "groups": _coerce_groups((block.input or {}).get("groups")),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "model": JUDGE_NAMED_THEMES_MODEL,
        }
    except Exception as e:
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("judge named-theme extractor", e)
        logger.warning(f"judge_named_themes: extraction failed for {ticker} {alert_date}: "
                       f"{type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════════
# The nightly sweep / historical pass — capture first, then record

def _cost_usd(model: "str | None", input_tokens: int, output_tokens: int) -> float:
    price = pricing_for(model) if model else pricing_for(JUDGE_NAMED_THEMES_MODEL)
    return input_tokens * price["input"] / 1e6 + output_tokens * price["output"] / 1e6


def _append_capture(path: "Path | str | None", record: dict) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


async def extract_pending(
    *, limit: int = 40, since: date = DEFAULT_SINCE, capture_path: "Path | str | None" = None,
    commit: bool = True,
) -> dict:
    """Extract every alert still owed a row (bounded by `limit`), oldest first.

    Per alert: call -> append the raw result to `capture_path` (JSONL, BEFORE any DB write —
    the paid output is durable even if the insert dies) -> write one row per group, or the
    NONE_KEY sentinel when nothing was named. A None result (failure) writes NOTHING, so the
    alert stays pending for the next run. `commit=False` = dry run: counts the pending
    population and spends nothing. Never raises past its own per-alert handling."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        pending = await get_judge_named_themes_pending(conn, since, limit)
    out = {"n_pending": len(pending), "n_alerts": 0, "n_rows_written": 0, "n_failed": 0,
           "n_named": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0.0,
           "commit": commit}
    if not commit or not pending:
        out["n_alerts"] = len(pending) if not commit else 0
        return out

    for row in pending:
        ticker, alert_date = row["ticker"], row["alert_date"]
        out["n_alerts"] += 1
        res = await extract_named_themes(ticker, alert_date, row.get("judge_rationale"))
        if res is None:
            out["n_failed"] += 1
            continue
        out["input_tokens"] += res["input_tokens"]
        out["output_tokens"] += res["output_tokens"]
        _append_capture(capture_path, {
            "ticker": ticker, "alert_date": alert_date, "alert_id": row.get("id"),
            "model": res["model"], "input_tokens": res["input_tokens"],
            "output_tokens": res["output_tokens"], "groups": res["groups"],
        })
        try:
            async with pool.acquire() as conn:
                rows = res["groups"] or [{"name": NONE_KEY, "canonical_key": NONE_KEY,
                                          "evidence": None, "judge_says_untracked": None}]
                for g in rows:
                    await insert_judge_named_theme_row(
                        conn, ticker, alert_date, row.get("id"), g["name"], g["canonical_key"],
                        g.get("evidence"), g.get("judge_says_untracked"), res["model"],
                    )
                    out["n_rows_written"] += 1
                if res["groups"]:
                    out["n_named"] += 1
        except Exception as e:
            out["n_failed"] += 1
            logger.warning(f"judge_named_themes: write failed for {ticker} {alert_date}: {e}")
    out["est_cost_usd"] = _cost_usd(JUDGE_NAMED_THEMES_MODEL, out["input_tokens"], out["output_tokens"])
    if out["n_alerts"]:
        await log_audit_event(
            "judge_named_themes_extracted",
            f"{out['n_alerts']} alert(s): {out['n_named']} named a group, "
            f"{out['n_rows_written']} row(s) written, {out['n_failed']} failed "
            f"(retry next run), ~${out['est_cost_usd']:.4f}",
        )
    return out


# ═══════════════════════════════════════════════════════════════════════════════════
# The READ that answers the goal — pure functions over recorded rows + the engine's timeline

_STOP = frozenset({
    "the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "via", "vs",
    "theme", "themes", "cohort", "cohorts", "stock", "stocks", "name", "names", "play",
    "plays", "trade", "trades", "group", "groups", "story", "narrative", "narratives",
    "live", "active", "hot", "basket", "baskets", "tracked", "current",
})


def _singular(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def normalize_key(text: "str | None") -> str:
    """Lowercase, punctuation -> spaces, filler words dropped, crude singular, hyphen-joined.
    'the live AI infrastructure theme' == 'AI-Infrastructure' == 'ai-infrastructure'.
    Deterministic and untuned: it collapses PHRASINGS of one label, it does not judge
    whether two different labels mean the same group — that is what the model's
    canonical_key is for, and what the operator's eye is for after that."""
    if not text:
        return ""
    toks = [_singular(t) for t in re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split()
            if t not in _STOP]
    return "-".join(t for t in toks if t)


def _tokens(key: str) -> frozenset[str]:
    return frozenset(t for t in key.split("-") if t)


def recurring_groups(rows: list[dict]) -> list[dict]:
    """Group recorded rows by normalised canonical_key; keep those seen on >= 2 DISTINCT
    tickers. Recurrence is the filter (see the module docstring) — no score, no threshold.
    Sentinel rows never count. Sorted by first mention, oldest first."""
    by_key: dict[str, dict] = {}
    for r in rows:
        raw = r.get("canonical_key") or ""
        if raw == NONE_KEY:
            continue
        key = normalize_key(raw)
        if not key:
            continue
        g = by_key.setdefault(key, {"key": key, "variants": {}, "mentions": [], "evidence": []})
        variant = str(r.get("group_name") or raw)
        g["variants"][variant] = g["variants"].get(variant, 0) + 1
        g["mentions"].append((r["alert_date"], str(r["ticker"]).upper()))
        if r.get("evidence"):
            g["evidence"].append((r["alert_date"], str(r["ticker"]).upper(), r["evidence"]))
        if r.get("judge_says_untracked") is not None:
            g.setdefault("untracked_votes", []).append(bool(r["judge_says_untracked"]))
    out = []
    for g in by_key.values():
        tickers = sorted({t for _, t in g["mentions"]})
        if len(tickers) < 2:
            continue
        mentions = sorted(g["mentions"])
        out.append({
            "key": g["key"],
            "variants": sorted(g["variants"]),
            "variant_counts": dict(g["variants"]),   # phrasing -> mentions; the seed name picks the modal one
            "tickers": tickers,
            "n_tickers": len(tickers),
            "n_alerts": len(mentions),
            "first_named_date": mentions[0][0],
            "last_named_date": mentions[-1][0],
            "mentions": mentions,
            "evidence": sorted(g["evidence"])[:6],
            "judge_untracked_share": (
                sum(g["untracked_votes"]) / len(g["untracked_votes"])
                if g.get("untracked_votes") else None),
        })
    out.sort(key=lambda g: (g["first_named_date"], g["key"]))
    return out


def theme_first_seen(theme_history: list[dict], rename_edges=()) -> dict[str, date]:
    """name -> the EARLIEST theme_date across the name's whole rename lineage."""
    first: dict[str, date] = {}
    for r in theme_history:
        n, d = r.get("name"), r.get("theme_date")
        if not n or d is None:
            continue
        if n not in first or d < first[n]:
            first[n] = d
    aliases = resolve_theme_aliases(list(rename_edges)) if rename_edges else {}
    out: dict[str, date] = {}
    for n, d in first.items():
        fam = aliases.get(n, frozenset({n}))
        out[n] = min(first[m] for m in fam if m in first)
    return out


def match_theme(group: dict, first_seen: dict[str, date]) -> tuple["dict | None", list[dict]]:
    """Deterministic name match — the ONE rule, stated so the operator can check it:
    tokens of the judge's key (or any recorded variant) vs tokens of the theme name;
    a MATCH is Jaccard >= 0.5 OR full containment of a >=2-token side. A single shared
    token ('ai') is never a match. Returns (best match or None, up to 5 near-misses that
    share >= 1 token) — the near-misses are printed beside every verdict precisely so a
    wrong 'never matched' is visible to the eye rather than buried."""
    cands = {group["key"]} | {normalize_key(v) for v in group.get("variants", [])}
    cand_toks = [_tokens(c) for c in cands if c]
    best, near = None, []
    for name, d in first_seen.items():
        tt = _tokens(normalize_key(name))
        if not tt:
            continue
        score, contained = 0.0, False
        for ct in cand_toks:
            inter = len(ct & tt)
            if not inter:
                continue
            score = max(score, inter / len(ct | tt))
            small, big = (ct, tt) if len(ct) <= len(tt) else (tt, ct)
            if len(small) >= 2 and small <= big:
                contained = True
        if score == 0.0:
            continue
        entry = {"theme_name": name, "theme_first_date": d, "jaccard": round(score, 3),
                 "contained": contained}
        if score >= 0.5 or contained:
            if best is None or (score, contained) > (best["jaccard"], best["contained"]):
                best = entry
        else:
            near.append(entry)
    near.sort(key=lambda m: (-m["jaccard"], m["theme_name"]))
    return best, near[:5]


def lead_time_report(rows: list[dict], theme_history: list[dict], rename_edges=()) -> dict:
    """THE measurement. For every recurring judge-named group: did mi_themes ever hold a
    matching name, and when? lead_days = theme_first_date - first_named_date (POSITIVE =
    the judge named it that many days before the engine had it). Verdicts:
    judge_earlier / already_existed / never_matched. Every count carries its n."""
    alerts = {(str(r["ticker"]).upper(), r["alert_date"]) for r in rows}
    real = [r for r in rows if r.get("canonical_key") != NONE_KEY and normalize_key(r.get("canonical_key"))]
    naming = {(str(r["ticker"]).upper(), r["alert_date"]) for r in real}
    keys = {normalize_key(r["canonical_key"]) for r in real}
    groups = recurring_groups(rows)
    first_seen = theme_first_seen(theme_history, rename_edges)
    for g in groups:
        best, near = match_theme(g, first_seen)
        g["match"], g["near_misses"] = best, near
        if best is None:
            g["lead_days"], g["verdict"] = None, "never_matched"
        else:
            g["lead_days"] = (best["theme_first_date"] - g["first_named_date"]).days
            g["verdict"] = "judge_earlier" if g["lead_days"] > 0 else "already_existed"
    return {
        "n_alerts_extracted": len(alerts),
        "n_alerts_naming_a_group": len(naming),
        "n_distinct_keys": len(keys),
        "n_recurring": len(groups),
        "n_singletons": len(keys) - len(groups),
        "n_judge_earlier": sum(g["verdict"] == "judge_earlier" for g in groups),
        "n_already_existed": sum(g["verdict"] == "already_existed" for g in groups),
        "n_never_matched": sum(g["verdict"] == "never_matched" for g in groups),
        "n_theme_names_in_history": len(first_seen),
        "theme_history_span": (
            f"{min(first_seen.values())} -> "
            f"{max(r['theme_date'] for r in theme_history if r.get('theme_date'))}"
            if first_seen else None),
        "groups": groups,
    }


def format_report(rep: dict) -> str:
    """Plain text; FIRST LINE = THE ANSWER."""
    groups = rep["groups"]
    earlier = [g for g in groups if g["verdict"] == "judge_earlier"]
    never = [g for g in groups if g["verdict"] == "never_matched"]
    if earlier:
        leads = ", ".join(f"{g['lead_days']}d ({g['key']} -> '{g['match']['theme_name']}', "
                          f"n={g['n_tickers']} tickers)" for g in earlier)
        head = (f"MEASURED — {len(earlier)} group{'s' if len(earlier) != 1 else ''} named by the "
                f"judge BEFORE the engine had a matching theme (of {rep['n_recurring']} recurring); "
                f"lead: {leads}")
    elif never:
        head = (f"CANDIDATES, NO LEAD TIME YET — {len(never)} recurring group"
                f"{'s' if len(never) != 1 else ''} the engine has never had "
                f"({', '.join(g['key'] for g in never)}); lead time is undefined until the engine "
                f"creates one, and {rep['n_already_existed']} recurring group(s) already existed")
    else:
        head = (f"NULL — no judge-named group recurs across two or more tickers ahead of the engine "
                f"({rep['n_recurring']} recurring, all already existed; {rep['n_singletons']} "
                f"single-ticker names; {rep['n_alerts_naming_a_group']} of {rep['n_alerts_extracted']} "
                f"alerts named a group)")
    lines = [head, ""]
    lines.append(f"alerts extracted: {rep['n_alerts_extracted']} · naming >=1 group: "
                 f"{rep['n_alerts_naming_a_group']} · distinct keys: {rep['n_distinct_keys']} · "
                 f"recurring (>=2 tickers): {rep['n_recurring']} · single-ticker: {rep['n_singletons']}")
    lines.append(f"recurring verdicts — judge earlier: {rep['n_judge_earlier']} · already existed: "
                 f"{rep['n_already_existed']} · never matched: {rep['n_never_matched']} "
                 f"(theme history: {rep['n_theme_names_in_history']} names, span {rep['theme_history_span']})")
    for g in groups:
        lines.append("")
        lines.append(f"[{g['verdict']}] {g['key']}  first named {g['first_named_date']}  "
                     f"n={g['n_tickers']} tickers / {g['n_alerts']} alerts: {', '.join(g['tickers'])}")
        lines.append(f"   variants: {' | '.join(g['variants'])}")
        if g["match"]:
            m = g["match"]
            lines.append(f"   matched theme: '{m['theme_name']}' first seen {m['theme_first_date']} "
                         f"(jaccard {m['jaccard']}, contained={m['contained']}) -> lead {g['lead_days']} days")
        if g["near_misses"]:
            lines.append("   near-misses (for the eye): " + "; ".join(
                f"'{m['theme_name']}' {m['theme_first_date']} j={m['jaccard']}" for m in g["near_misses"]))
        for d, t, ev in g["evidence"][:3]:
            lines.append(f"   {d} {t}: \"{ev}\"")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════════
# The SURFACE — seed a shadow candidate, page ONCE with the existing one-tap promote button

# The candidate name is what the operator sees in /themes for the life of the theme — capped
# to the synthesis lane's own name limit (theme_synthesis._MAX_NAME_LEN), no prefix.
MAX_SEED_NAME_LEN = 80
# Re-seed a surfaced-but-unpromoted group while its LAST naming is within this many days —
# the shadow window promote_candidate_by_name / the button read (get_shadow_theme_candidates
# days=7), so the button keeps resolving to a row carrying the current ticker set.
SEED_REFRESH_DAYS = 7


def seed_name_for(group: dict) -> str:
    """The judge's MOST FREQUENT phrasing of the group; ties -> shortest, then alphabetical
    (deterministic). Falls back to the slug only if no phrasing was recorded."""
    counts = group.get("variant_counts") or {}
    if not counts:
        return (group.get("key") or "")[:MAX_SEED_NAME_LEN]
    best = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]
    best = best.strip()
    if len(best) > MAX_SEED_NAME_LEN:
        best = best[:MAX_SEED_NAME_LEN - 1].rstrip() + "…"
    return best


def find_new_candidates(report: dict, surfaced: set[str]) -> list[dict]:
    """Recurring (>= 2 distinct tickers, the definition of a theme) AND matched no theme the
    engine EVER held (`lead_time_report`'s `never_matched`, the same deterministic rule the
    operator's report prints) AND never paged before. Oldest first, like the report."""
    return [g for g in report["groups"]
            if g["verdict"] == "never_matched" and g["key"] not in surfaced]


def _thesis_for(group: dict) -> str:
    """The candidate's thesis = the judge's own sentences, one per ticker, dated — what
    /themes shows beside the cohort and what a promoted theme's description starts from."""
    parts = [f"Judge-named on {group['n_tickers']} EP alerts "
             f"({group['first_named_date']} -> {group['last_named_date']}); "
             f"no theme of ours matched (#651)."]
    for d, t, ev in group.get("evidence", [])[:3]:
        parts.append(f"{d} {t}: {ev}")
    return " ".join(parts)[:400]


def format_candidate_alert(group: dict, name: str, promote_min: int) -> str:
    """The page. HTML (#121 layer) — the judge's prose carries '&' and '<', esc() is total.
    Carries: the group name, the tickers it was named on, the judge's own words, that we have
    no theme for it (plus the closest names we ever had, for the eye), and — plainly — how
    many names it has against the promote bar, so a tap that must fail is never offered as
    if it would succeed."""
    from shared.telegram_format import b, code, esc, i

    n = group["n_tickers"]
    lines = [
        f"🧭 {b('Judge-named group — no theme of ours matches')}",
        b(name),   # b() escapes internally — never esc() twice (a '&' would render '&amp;amp;')
        f"Named on {n} tickers: {code(' '.join(group['tickers']))}  "
        f"({esc(str(group['first_named_date']))} → {esc(str(group['last_named_date']))})",
        "",
        i("The judge's words:"),
    ]
    for d, t, ev in group.get("evidence", [])[:3]:
        lines.append(f"• {esc(str(d))} {esc(t)}: “{esc(ev)}”")
    near = group.get("near_misses") or []
    if near:
        closest = ", ".join(f"{esc(m['theme_name'])} ({esc(str(m['theme_first_date']))})"
                            for m in near[:3])
        lines.append("")
        lines.append(f"Closest names we ever had (none matched): {closest}")
    lines.append("")
    if n < promote_min:
        lines.append(
            f"{n} names so far — the promote bar is {promote_min}. The button below goes live "
            f"when the judge names a third; the candidate refreshes on each new naming. "
            f"Nothing is created until you tap.")
    else:
        lines.append(
            f"Tap below to create it as a live theme ({n} members). "
            f"Nothing is created until you tap.")
    return "\n".join(lines)


async def surface_new_candidates(*, today: "date | None" = None, dry_run: bool = False) -> dict:
    """The nightly trigger. Reads the recorded rows + the engine's full theme timeline, runs
    THE SAME `lead_time_report` the operator's report uses, and for every recurring group the
    engine never had that has not been paged before: SEED (so the button has a target) ->
    SEND (with the existing tpromo: promote button) -> DEDUPE ROW (only if the send landed).
    Already-paged unmatched groups still being named are re-seeded silently (see
    SEED_REFRESH_DAYS). ALWAYS ends with the liveness audit row — even on a quiet night.
    `dry_run` reads everything and writes/sends nothing (the $0 preview). Raises on a read
    failure on purpose: audit_wrap records the job failed and #501 pages — a trigger that
    dies quietly is the failure this surface exists to end."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await get_judge_named_theme_rows(conn)
        hist = await get_theme_name_history(conn)
        edges = await get_theme_rename_edges(conn)
        surfaced = await get_judge_named_surfaced_keys(conn)
    rep = lead_time_report(rows, hist, rename_edges=edges)
    groups = rep["groups"]
    unmatched = [g for g in groups if g["verdict"] == "never_matched"]
    new = find_new_candidates(rep, surfaced)
    refresh = [g for g in unmatched
               if g["key"] in surfaced and (today - g["last_named_date"]).days <= SEED_REFRESH_DAYS]
    out = {
        "today": today.isoformat(), "dry_run": dry_run,
        "n_recurring": len(groups), "n_matched": len(groups) - len(unmatched),
        "n_unmatched": len(unmatched), "n_already_surfaced": len(unmatched) - len(new),
        "n_refreshed": 0, "n_fired": 0, "n_send_failed": 0, "n_seed_failed": 0,
        "would_fire": [{"key": g["key"], "name": seed_name_for(g), "tickers": g["tickers"]} for g in new],
        "fired": [],
    }
    if dry_run:
        return out

    from agents.market_intelligence.theme_engine import _PROMOTE_MIN_MEMBERS
    from agents.market_intelligence.theme_synthesis import build_synthesis_keyboard
    from agents.market_intelligence.briefing import send_telegram_message

    # Silent refresh: the seed is the button's target; keep it current while the judge keeps
    # naming the group (a third name is what makes the tap clear the promote bar).
    for g in refresh:
        try:
            async with pool.acquire() as conn:
                await persist_judge_named_seed(conn, today, seed_name_for(g), g["tickers"], _thesis_for(g))
            out["n_refreshed"] += 1
        except Exception as e:
            out["n_seed_failed"] += 1
            logger.warning(f"judge_named_themes: seed refresh failed for {g['key']}: {e}")

    for g in new:
        name = seed_name_for(g)
        seeded = True
        try:
            async with pool.acquire() as conn:
                await persist_judge_named_seed(conn, today, name, g["tickers"], _thesis_for(g))
        except Exception as e:
            # The finding still reaches him; only the button is lost (it would resolve nothing).
            seeded = False
            out["n_seed_failed"] += 1
            logger.warning(f"judge_named_themes: seed write failed for {g['key']}: {e}")
        text = format_candidate_alert(g, name, _PROMOTE_MIN_MEMBERS)
        if not seeded:
            text += "\n\n⚠ The candidate could not be seeded tonight — the button will not resolve; /themes tomorrow."
        markup = build_synthesis_keyboard([{"name": name}]) if seeded else None
        ok = await send_telegram_message(text, parse_mode="HTML", reply_markup=markup)
        if not ok:
            out["n_send_failed"] += 1
            logger.warning(f"judge_named_themes: page for {g['key']} did not send — retries next night")
            continue
        await log_audit_event(
            JUDGE_NAMED_CANDIDATE_EVENT,
            f"{g['key']}: '{name}' named on {g['n_tickers']} tickers "
            f"({', '.join(g['tickers'])}) {g['first_named_date']} -> {g['last_named_date']}; "
            f"no theme ever matched; seeded source={JUDGE_NAMED_SEED_SOURCE}"
            + ("" if seeded else " (SEED FAILED)"),
            detail=str({k: v for k, v in g.items() if k != "mentions"}),
        )
        out["n_fired"] += 1
        out["fired"].append({"key": g["key"], "name": name, "tickers": g["tickers"], "seeded": seeded})

    # LIVENESS — the positive observable. Per group: which theme suppressed it, so a wrong
    # match is visible in the audit log rather than silently swallowing a real candidate.
    per_group = "; ".join(
        f"{g['key']}[{g['n_tickers']}t] -> "
        + (f"matched '{g['match']['theme_name']}' ({g['match']['theme_first_date']}, lead {g['lead_days']}d)"
           if g["match"] else
           ("paged tonight" if any(f["key"] == g["key"] for f in out["fired"])
            else ("already surfaced" if g["key"] in surfaced else "unmatched, page did not send")))
        for g in groups)
    await log_audit_event(
        JUDGE_NAMED_EVALUATED_EVENT,
        f"{out['n_recurring']} recurring group(s): {out['n_matched']} matched a theme, "
        f"{out['n_unmatched']} unmatched ({out['n_already_surfaced']} already surfaced, "
        f"{out['n_refreshed']} re-seeded), {out['n_fired']} fired"
        + (f", {out['n_send_failed']} send failed" if out["n_send_failed"] else "")
        + (f", {out['n_seed_failed']} seed failed" if out["n_seed_failed"] else ""),
        detail=per_group or "no recurring groups yet",
    )
    return out
