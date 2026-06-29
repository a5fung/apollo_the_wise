"""Cross-ticker emerging-theme SYNTHESIS pass (#240 North Star advisory feed).

The gap (memory project_cross_ticker_narrative_synthesis_gap, operator 2026-05-30):
dev-session Claude can spot an RS-slope cohort recovering together (OKTA +
CRWD/DDOG/TWLO on "SaaS ships AI"), infer the narrative, and name the emerging
theme — but NO production tool does that reasoning. Lane 1 clusters bottom-up by
correlation+sector (blind to cross-sector narrative rotations); Lane 2 (#167)
catches same-day co-GAPS only (blind to slow-burn multi-week recoveries).

This pass is the top-down half: take the two coordinated-RS-slope surfaces that
already exist (get_rs_velocity = sustained acceleration; get_rs_turners =
weak→strengthening turn), feed the combined candidate list + sector/description
context to ONE Sonnet call, and let it propose 0–3 emerging cross-ticker
narrative cohorts. Grounded by construction: members MUST come from the RS
candidate list (mechanical subset check — the proto-#212 lesson: mechanical
grounding > LLM-on-LLM skepticism), and cohorts that just restate one live
mi_theme are dropped (not "emerging").

ADVISORY, augment-not-automate (Pradeep: themes emerge from price action + the
operator's read): proposals land in mi_theme_candidates_shadow under
source='rs_slope_synthesis' — NEVER live mi_themes — where the operator reviews
them (/themes) AND the judge's narrative axis reads them as active_narratives
context (get_narrative_theme_candidates). Telegram pings only when something
was proposed; silent runs are audit-only (feedback_alert_vs_audit).
"""
from __future__ import annotations

import json
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Mechanical validation bounds (the grounded part — never LLM-judged).
_MIN_MEMBERS = 3
_MAX_MEMBERS = 12
_MAX_COHORTS = 3
_MAX_NAME_LEN = 80
# Drop a proposal when this fraction of members already sits in ONE live theme —
# that's a restatement of an existing theme, not an emerging one.
_LIVE_OVERLAP_DROP = 0.6

_SYNTHESIS_TOOL = {
    "name": "propose_emerging_cohorts",
    "description": (
        "Propose 0-3 EMERGING cross-ticker narrative cohorts from the supplied "
        "RS-acceleration candidates. Reason in the scratchpad FIRST."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "Think step by step BEFORE proposing: which candidates are "
                    "moving for a SHARED narrative reason (not just same "
                    "sector)? What is the story? Is it already a known live "
                    "theme? Prefer proposing NOTHING over a forced grouping."
                ),
            },
            "cohorts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "thesis": {
                            "type": "string",
                            "description": "1-2 sentences: the shared narrative driving the cohort.",
                        },
                        "tickers": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["name", "thesis", "tickers", "confidence"],
                },
            },
        },
        "required": ["analysis_scratchpad", "cohorts"],
    },
}

_PROMPT = """You are a momentum PM doing a nightly cross-ticker scan (Qullamaggie/Pradeep \
methodology: themes emerge from price action). Below are stocks showing COORDINATED \
relative-strength moves today — sustained accelerators and weak-to-strong turners.

Your ONE job: spot groups of 3+ names moving for a SHARED NARRATIVE reason and name the \
emerging theme. Cross-sector groupings are the prize (a drone-defense cohort spanning \
industrials+tech; a "SaaS ships AI" re-rating spanning software names) — sector-clustering \
alone is NOT a narrative. Exposure counts, not classification: a fund or supplier whose \
description ties it to the narrative belongs with its theme.

Rules:
- Members MUST come from the candidate list below (no outside names).
- 3-12 members per cohort, at most {max_cohorts} cohorts.
- Do NOT restate the EXISTING live themes listed at the bottom — only EMERGING stories.
- Proposing ZERO cohorts is a correct, common output. Never force a grouping.

CANDIDATES (signal | ticker | sector | RS now | 4w RS path | description):
{candidates}

EXISTING LIVE THEMES (do not restate):
{live_themes}
"""


def validate_cohorts(
    cohorts: list[dict],
    candidate_tickers: set[str],
    live_theme_members: dict[str, set[str]],
) -> tuple[list[dict], list[str]]:
    """Mechanical post-filter (pure, unit-tested) — the grounding layer.

    Keeps a proposal only if: members are a subset of the candidate list,
    member count in [_MIN_MEMBERS, _MAX_MEMBERS], name fits, and the cohort is
    not just a restatement of one live theme (>= _LIVE_OVERLAP_DROP of members
    inside a single live theme). Returns (kept, drop_reasons)."""
    kept: list[dict] = []
    dropped: list[str] = []
    for c in (cohorts or [])[:_MAX_COHORTS]:
        name = (c.get("name") or "").strip()
        tickers = [t.strip().upper() for t in (c.get("tickers") or []) if t and t.strip()]
        tickers = list(dict.fromkeys(tickers))  # dedupe, keep order
        if not name or len(name) > _MAX_NAME_LEN:
            dropped.append(f"{name or '<unnamed>'}: bad name")
            continue
        outside = [t for t in tickers if t not in candidate_tickers]
        if outside:
            dropped.append(f"{name}: members outside candidate list {outside}")
            continue
        if not (_MIN_MEMBERS <= len(tickers) <= _MAX_MEMBERS):
            dropped.append(f"{name}: {len(tickers)} members (need {_MIN_MEMBERS}-{_MAX_MEMBERS})")
            continue
        overlap_theme = None
        for theme_name, members in live_theme_members.items():
            if len(set(tickers) & members) / len(tickers) >= _LIVE_OVERLAP_DROP:
                overlap_theme = theme_name
                break
        if overlap_theme:
            dropped.append(f"{name}: restates live theme '{overlap_theme}'")
            continue
        kept.append({
            "name": name,
            "thesis": (c.get("thesis") or "").strip()[:400],
            "tickers": tickers,
            "confidence": c.get("confidence") or "low",
        })
    return kept, dropped


def _candidate_line(signal: str, r: dict, desc: str | None) -> str:
    rs_now = r.get("rs_now") if r.get("rs_now") is not None else r.get("rs_composite")
    path = "→".join(
        f"{r[k]:.0f}" for k in ("rs_28d", "rs_21d", "rs_14d", "rs_7d")
        if r.get(k) is not None
    )
    return (
        f"{signal} | {r['ticker']} | {r.get('sector') or 'Unknown'} | "
        f"RS {rs_now:.0f} | {path or 'n/a'} | {(desc or '')[:120]}"
    )


def format_synthesis_digest(kept: list[dict]) -> str:
    """Operator Telegram digest for the kept cohorts. #121 HTML surface:
    name/thesis are LLM-generated prose — esc()'d via the helpers so a stray
    & or < can never 400 the digest."""
    from shared.telegram_format import b, code, esc, i

    lines = ["🔭 <b>Emerging-theme synthesis</b> (advisory — operator read required)"]
    for c in kept:
        lines.append(
            f"\n{b(c['name'])} ({esc(c['confidence'])})\n"
            f"{code(' '.join(c['tickers']))}\n{i(c['thesis'])}"
        )
    lines.append(
        "\n<i>RS-slope cohorts, cross-sector. Already feeds the judge's narrative axis (advisory).</i>"
    )
    lines.append(
        "▶ To promote one to a live theme (your judgment): <code>/promotetheme &lt;name&gt;</code> "
        "— it then behaves like any other theme (re-discovered while the cohort co-moves)."
    )
    return "\n".join(lines)


async def run_theme_synthesis(run_date: "date | None" = None) -> dict:
    """Nightly synthesis pass. Returns a summary dict (n_candidates, n_proposed,
    n_kept, dropped). Errors audit as theme_synthesis_error; an empty proposal
    set is a normal, audit-only outcome."""
    from agents.market_intelligence.collector import et_today, last_trading_day
    from agents.market_intelligence.db import (
        get_active_themes, get_descriptions_batch, get_rs_turners,
        get_rs_velocity, log_audit_event, persist_synthesis_theme_candidates,
    )
    from agents.market_intelligence.theme_engine import _get_anthropic_client
    from shared.llm_models import SYNTHESIS_MODEL

    rd = run_date or et_today()
    d = last_trading_day()

    velocity = await get_rs_velocity(d, limit=30)
    turners = await get_rs_turners(d, limit=40)
    by_ticker: dict[str, tuple[str, dict]] = {}
    for r in velocity:
        by_ticker[r["ticker"]] = ("ACCEL", r)
    for r in turners:
        by_ticker.setdefault(r["ticker"], ("TURNER", r))

    if len(by_ticker) < _MIN_MEMBERS * 2:
        await log_audit_event(
            "theme_synthesis_run",
            f"skip — only {len(by_ticker)} RS candidates",
            json.dumps({"run_date": str(rd), "n_candidates": len(by_ticker)}),
        )
        return {"n_candidates": len(by_ticker), "n_proposed": 0, "n_kept": 0, "dropped": []}

    # Cached descriptions only (mi_ticker_overrides) — no new Haiku calls on
    # this path; missing descriptions just give the LLM less context.
    descs = await get_descriptions_batch(list(by_ticker))

    live = await get_active_themes()
    live_theme_members = {
        t["name"]: {tk.upper() for tk in (t.get("tickers") or [])} for t in live
    }
    live_names = "\n".join(f"- {t['name']}" for t in live) or "(none)"

    cand_lines = "\n".join(
        _candidate_line(sig, r, descs.get(tk)) for tk, (sig, r) in sorted(by_ticker.items())
    )
    prompt = _PROMPT.format(
        max_cohorts=_MAX_COHORTS, candidates=cand_lines, live_themes=live_names,
    )

    try:
        client = _get_anthropic_client()
        resp = await client.messages.create(
            model=SYNTHESIS_MODEL,
            # 4000 (was 2000): match the #325 theme-DISCOVERY bump. A forced tool call whose
            # cohorts JSON exceeds the cap truncates (stop_reason='max_tokens') and silently
            # yields an empty/partial `cohorts` — indistinguishable from a genuine "no cohorts"
            # unless we record the stop_reason. Discovery proposed 0 for 3 days straight
            # (6/22-24) with no way to tell which; that silent ambiguity is the bug.
            max_tokens=4000,
            tools=[_SYNTHESIS_TOOL],
            tool_choice={"type": "tool", "name": "propose_emerging_cohorts"},
            messages=[{"role": "user", "content": prompt}],
        )
        try:  # #377 cost meter — additive, never alters synthesis output
            from agents.market_intelligence.spend_tracker import log_anthropic_call
            await log_anthropic_call(model=SYNTHESIS_MODEL, caller="theme_synthesis",
                                     usage=getattr(resp, "usage", None))
        except Exception:
            pass
        stop_reason = getattr(resp, "stop_reason", None)
        tool_input = next(
            (b.input for b in resp.content if getattr(b, "type", "") == "tool_use"), {},
        )
        proposed = tool_input.get("cohorts") or []
    except Exception as e:
        # #376: credit exhaustion silently yields no cohorts — alert it (deduped).
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("theme synthesis", e)
        logger.exception("theme synthesis LLM call failed")
        await log_audit_event(
            "theme_synthesis_error", f"LLM call failed: {e}",
            json.dumps({"run_date": str(rd), "n_candidates": len(by_ticker)}),
        )
        return {"n_candidates": len(by_ticker), "n_proposed": 0, "n_kept": 0,
                "dropped": [f"error: {e}"]}

    kept, dropped = validate_cohorts(proposed, set(by_ticker), live_theme_members)
    n_written = await persist_synthesis_theme_candidates(rd, kept)

    await log_audit_event(
        "theme_synthesis_run",
        f"{len(by_ticker)} candidates → {len(proposed)} proposed → {len(kept)} kept",
        json.dumps({
            "run_date": str(rd), "n_candidates": len(by_ticker),
            "n_proposed": len(proposed), "n_kept": len(kept),
            # 'max_tokens' => truncated, raise the cap; 'tool_use'/'end_turn' + 0 proposed
            # => the model genuinely found no emerging cohorts (a prompt/candidate-quality
            # question, not a silent failure).
            "stop_reason": stop_reason,
            "kept": [{"name": c["name"], "tickers": c["tickers"],
                      "confidence": c["confidence"]} for c in kept],
            "dropped": dropped,
        }),
    )

    if kept:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(format_synthesis_digest(kept), parse_mode="HTML")

    return {"n_candidates": len(by_ticker), "n_proposed": len(proposed),
            "n_kept": len(kept), "dropped": dropped, "written": n_written}
