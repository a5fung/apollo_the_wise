#!/usr/bin/env python3
"""#212 Tier-1 dialogic-loop PROTOTYPE (throwaway, READ-ONLY; no DB write, no scheduler).

Tests ONE hypothesis: does a skeptical ADVISOR-PASS (stronger model, full context)
over a tool-grounded INVESTIGATOR's catalyst dossier ADD VALUE — catch confabulations,
flip wrong verdicts — vs the investigator alone? (project_cross_ticker_narrative_
synthesis_gap; the production version of the advisor() pattern.)

DESIGN (advisor-reviewed 2026-06-06):
  - Cohort = the real UNKNOWN / coverage-gap EP rows (where sourcing already failed) —
    the right HARD set. ~6 names, most recent.
  - Evidence pack = POINT-IN-TIME stored fields (mi_ep_alerts.catalyst / claude_analysis
    — no lookahead) + the PRIMARY SEC filing near the alert date (re-fetched 8-K/6-K).
    The investigator sees ONLY this retrieved text.
  - Grounding is enforced TWO ways: (1) every claim must carry a VERBATIM QUOTE from a
    named source; (2) a MECHANICAL substring check verifies the quote actually appears
    in that source — confabulation becomes detectable without trusting an LLM. Both the
    advisor and the reader use this.
  - Loop = linear investigate(v1, Sonnet) -> critique(Opus, skeptical PM) -> revise(v2,
    Sonnet). NOT a free debate. The agentic "fetch cohort co-movers" round is deferred to
    v2-of-the-prototype, only if this shows the advisor-pass moves verdicts.
  - OUTPUT = v1 dossier, the critique, v2 dossier, and the DIFF (verdict change? claims
    dropped/flagged ungrounded?). The DELTA is the result — without it you can't tell if
    the advisor caught anything or was ceremony.

ADJUDICATION (the RUM lesson): a confident `catalyst_confirmed` is exactly what a
confabulation looks like. Eyeball the quoted spans against the actual filing before
believing any dossier's own verdict.

Run (server, read-only):  docker exec apollo-market python scripts/proto_dialogic_dossier.py [N]
"""
import asyncio
import html
import json
import os
import re
import sys
from datetime import timedelta

import anthropic

INVESTIGATOR_MODEL = "claude-sonnet-4-6"
ADVISOR_MODEL = "claude-opus-4-8"

NON_FIRE = ("unknown", "pre_catalyst_anticipation", "no_fire_confirmed", "real_unknown")

# Fold typographic quotes/dashes to ASCII so a verbatim quote matches the source
# regardless of entity (&#8220;) vs rendered (U+201C) vs ASCII form — the RUM bug
# where a real $270M quote false-FAILED the grounding check on SEC HTML entities.
_TYPO_FOLD = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
})


def _norm(s: str) -> str:
    s = html.unescape(s or "").translate(_TYPO_FOLD)
    return re.sub(r"\s+", " ", s).strip().lower()


def _quote_grounded(quote: str, sources: dict) -> str | None:
    """Return the source_id whose text contains `quote` (whitespace-normalized
    substring), else None. The mechanical anti-confabulation check."""
    q = _norm(quote)
    if len(q) < 8:  # too short to be meaningful evidence
        return None
    for sid, text in sources.items():
        if q in _norm(text):
            return sid
    return None


def _extract_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, depth = raw.find("{"), 0
    for i in range(start, len(raw)):
        if raw[i] == "{": depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])
    return json.loads(raw[start:])


async def _llm(client, model, system, prompt, max_tokens=1800):
    resp = await client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return (getattr(resp.content[0], "text", "") or "").strip()


async def _llm_json(client, model, system, prompt, max_tokens=1800) -> dict:
    """LLM call + tolerant JSON parse with ONE reformat-retry. The revise step
    occasionally emitted truncated/malformed JSON ('Unterminated string' /
    'Expecting property name') and the loop silently fell back to v1 — which
    DESTROYS the measured signal (did v2 honor the PM?). Instead, re-ask the
    model once to re-emit valid JSON before giving up."""
    raw = await _llm(client, model, system, prompt, max_tokens)
    try:
        return _extract_json(raw)
    except Exception:
        fixed = await _llm(
            client, model,
            "You repair malformed JSON. Output ONLY one valid JSON object, no prose, no code fence.",
            f"Re-emit the following as a single valid JSON object only:\n\n{raw}",
            max_tokens,
        )
        return _extract_json(fixed)


async def _build_evidence(row) -> dict:
    """Point-in-time stored text + the primary SEC filing near the alert date."""
    from agents.market_intelligence.collector import get_sec_recent_filings, et_today
    sources: dict[str, str] = {}
    if row.get("catalyst"):
        sources["stored_catalyst"] = row["catalyst"]
    if row.get("claude_analysis"):
        sources["stored_analysis"] = row["claude_analysis"]
    # Re-fetch SEC filings spanning back to the alert date, keep those near it.
    try:
        adate = row["alert_date"]
        lb = (et_today() - adate).days + 3
        filings = await get_sec_recent_filings(
            row["ticker"], forms=("8-K", "6-K"), lookback_days=max(lb, 4),
            max_filings=12, want_text=True,
        )
        for f in filings:
            try:
                from datetime import date
                fd = date.fromisoformat(f["filed"])
            except Exception:
                continue
            if adate - timedelta(days=10) <= fd <= adate + timedelta(days=2) and f.get("text"):
                sources[f"sec_{f['form']}_{f['filed']}"] = f["text"]
    except Exception as e:
        sources["_sec_error"] = f"(SEC fetch failed: {e})"
    return sources


def _evidence_block(sources: dict) -> str:
    return "\n\n".join(f"[SOURCE {sid}]\n{text[:3500]}" for sid, text in sources.items())


_INV_SYS = "You are a grounded equity catalyst investigator. You may ONLY use the provided SOURCES. Respond with valid JSON only."

_INV_PROMPT = """Ticker {ticker} gapped {gap:+.1f}% on {date}, but our pipeline could NOT confirm a catalyst
(flags: type={ctype}, fire={fire}). Re-investigate using ONLY the sources below. Do NOT use outside
knowledge — if a fact is not in a source, you cannot claim it.

{evidence}

Return JSON:
{{"verdict": "catalyst_confirmed" | "unconfirmed" | "no_real_catalyst",
  "direction": "bullish" | "bearish" | "neutral",
  "catalyst": "<one line: the specific catalyst, or 'none found'>",
  "claims": [{{"claim": "<a factual statement>", "source": "<SOURCE id>", "quote": "<VERBATIM span copied from that source that proves the claim>"}}]}}

Rules: every claim MUST have a quote copied EXACTLY from the named source (we machine-check it).
PRESENCE IS NOT DIRECTION: `verdict` is whether a real catalyst exists; `direction` is its SIGN for
the stock. A confirmed-but-BEARISH event (e.g. a Phase-3 readout that hit efficacy but disclosed a
safety/malignancy signal and sold the stock off) is verdict=catalyst_confirmed + direction=bearish —
NOT "no_real_catalyst" and NOT "unconfirmed". Weigh ALL sources, not only the favorable lines.
"no_real_catalyst" is a valid answer ONLY for a gap with only boilerplate/registration text.
Do not invent a counterparty, dollar figure, or deal that isn't quoted in a source."""

_ADV_SYS = "You are a skeptical portfolio manager reviewing a junior analyst's catalyst dossier. Be rigorous about grounding. Respond with valid JSON only."

_ADV_PROMPT = """The analyst investigated {ticker} ({date}). Below: the SOURCES, the analyst's DOSSIER, and a
MECHANICAL GROUNDING CHECK (whether each claim's quote literally appears in a source).

SOURCES:
{evidence}

ANALYST DOSSIER (v1):
{dossier}

MECHANICAL GROUNDING CHECK:
{grounding}

Critique as a skeptical PM. A quote that fails the mechanical check is a CONFABULATION — the analyst
invented it. A quote that passes but is MISREAD (says something the source doesn't) is also wrong.
Decide the correct verdict. Remember: the safe, often-correct answer for this cohort is "no_real_catalyst".

A confirmed-but-BEARISH catalyst (efficacy hit but a safety/malignancy signal that sold the stock off)
is verdict_should_be=catalyst_confirmed + direction_should_be=bearish — do NOT collapse a directional
miss into "unconfirmed"/"no_real_catalyst"; that conflates catalyst-PRESENCE with catalyst-SIGN.

Return JSON:
{{"confabulated_claims": ["<claim text that is ungrounded or misread>"],
  "verdict_should_be": "catalyst_confirmed" | "unconfirmed" | "no_real_catalyst",
  "direction_should_be": "bullish" | "bearish" | "neutral",
  "guidance": "<2-3 sentences telling the analyst exactly what to fix>"}}"""

_REV_PROMPT = """Revise your {ticker} dossier given the PM's critique. Same JSON schema as before
(verdict, direction, catalyst, claims with verbatim quotes). DROP any claim you cannot ground with an
exact quote. Honor the PM's verdict AND direction unless a quoted source proves otherwise. Remember:
a confirmed-but-bearish event stays verdict=catalyst_confirmed with direction=bearish.

PM CRITIQUE:
{critique}

YOUR v1:
{dossier}

SOURCES:
{evidence}"""


def _check_grounding(dossier: dict, sources: dict) -> list[dict]:
    out = []
    for c in dossier.get("claims", []) or []:
        sid = _quote_grounded(c.get("quote", ""), sources)
        out.append({"claim": c.get("claim", "")[:120], "named": c.get("source"),
                    "grounded_in": sid, "ok": sid is not None})
    return out


async def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    from agents.market_intelligence.db import get_pool
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    pool = await get_pool()
    nf = ",".join(f"'{v}'" for v in NON_FIRE)
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT ticker, alert_date, gap_pct, catalyst_quality, catalyst_type,
                   fire_status, catalyst, claude_analysis
            FROM mi_ep_alerts
            WHERE catalyst_type='unknown' OR fire_status IN ({nf})
               OR catalyst ILIKE '%no clear%catalyst%' OR catalyst ILIKE '%not clearly identified%'
            ORDER BY alert_date DESC LIMIT {limit}
        """)
    rows = [dict(r) for r in rows]
    print(f"#212 dialogic prototype — {len(rows)} unknown/coverage-gap names\n" + "=" * 78)

    summary = []
    for row in rows:
        tk, dt = row["ticker"], str(row["alert_date"])
        sources = await _build_evidence(row)
        ev = _evidence_block(sources)
        ctx = dict(ticker=tk, gap=row["gap_pct"] or 0, date=dt,
                   ctype=row["catalyst_type"], fire=row["fire_status"], evidence=ev)

        # v1 — investigator
        try:
            v1 = await _llm_json(client, INVESTIGATOR_MODEL, _INV_SYS, _INV_PROMPT.format(**ctx))
        except Exception as e:
            print(f"\n### {tk} {dt} — investigator v1 ERROR: {e}"); continue
        g1 = _check_grounding(v1, sources)

        # critique — advisor pass (Opus)
        try:
            crit = await _llm_json(client, ADVISOR_MODEL, _ADV_SYS, _ADV_PROMPT.format(
                ticker=tk, date=dt, evidence=ev, dossier=json.dumps(v1, indent=2),
                grounding=json.dumps(g1, indent=2)))
        except Exception as e:
            print(f"\n### {tk} {dt} — advisor ERROR: {e}"); crit = {}

        # v2 — investigator revises
        try:
            v2 = await _llm_json(client, INVESTIGATOR_MODEL, _INV_SYS, _REV_PROMPT.format(
                ticker=tk, critique=json.dumps(crit, indent=2),
                dossier=json.dumps(v1, indent=2), evidence=ev))
        except Exception as e:
            print(f"\n### {tk} {dt} — revise ERROR: {e}"); v2 = v1
        g2 = _check_grounding(v2, sources)

        verdict_changed = v1.get("verdict") != v2.get("verdict")
        ungrounded_v1 = sum(1 for g in g1 if not g["ok"])
        ungrounded_v2 = sum(1 for g in g2 if not g["ok"])
        print(f"\n### {tk} {dt}  gap={row['gap_pct']:+.1f}%  sources={list(sources)}")
        print(f"  v1 verdict: {str(v1.get('verdict')):16s} dir={str(v1.get('direction','?')):8s} catalyst: {v1.get('catalyst','')[:70]}")
        print(f"     claims={len(v1.get('claims',[]))} ungrounded={ungrounded_v1}")
        print(f"  PM confab-flags: {crit.get('confabulated_claims', [])}")
        print(f"     PM verdict: {crit.get('verdict_should_be')} dir={crit.get('direction_should_be','?')}")
        print(f"  v2 verdict: {str(v2.get('verdict')):16s} dir={str(v2.get('direction','?')):8s} catalyst: {v2.get('catalyst','')[:70]}")
        print(f"     claims={len(v2.get('claims',[]))} ungrounded={ungrounded_v2}")
        print(f"  >>> DELTA: verdict_changed={verdict_changed}  "
              f"ungrounded {ungrounded_v1}->{ungrounded_v2}  confab_caught={len(crit.get('confabulated_claims',[]))}")
        # ── ADJUDICATION DUMP (the RUM lesson — eyeball quotes vs source) ──────
        print("  -- v1 claims (quote → grounded_in) --")
        for c, g in zip(v1.get("claims", []) or [], g1):
            print(f"     [{'OK ' if g['ok'] else 'UNGROUNDED'}] {c.get('claim','')[:100]}")
            print(f"        quote: \"{(c.get('quote','') or '')[:160]}\"  (named={g['named']} grounded_in={g['grounded_in']})")
        print(f"  -- PM critique --\n     confab: {crit.get('confabulated_claims', [])}")
        print(f"     guidance: {(crit.get('guidance','') or '')[:300]}")
        if v2 is not v1:
            print("  -- v2 claims --")
            for c, g in zip(v2.get("claims", []) or [], g2):
                print(f"     [{'OK ' if g['ok'] else 'UNGROUNDED'}] {c.get('claim','')[:100]}")
        summary.append(dict(ticker=tk, date=dt, v1=v1.get("verdict"), pm=crit.get("verdict_should_be"),
                            v2=v2.get("verdict"), verdict_changed=verdict_changed,
                            ungrounded_v1=ungrounded_v1, ungrounded_v2=ungrounded_v2,
                            confab_caught=len(crit.get("confabulated_claims", []))))

    print("\n" + "=" * 78 + "\nSUMMARY — did the advisor-pass add value?")
    nchg = sum(1 for s in summary if s["verdict_changed"])
    ncab = sum(s["confab_caught"] for s in summary)
    ungr = sum(s["ungrounded_v1"] for s in summary)
    print(f"  names={len(summary)}  verdicts_flipped_by_PM={nchg}  "
          f"confabulations_caught={ncab}  ungrounded_claims_v1={ungr}")
    print("  Advisor-pass EARNS its place IF it flipped verdicts or caught confabulations.")
    print("  If 0/0, the investigator alone suffices on this cohort (Tier-0, drop the pass).")
    out = "/tmp/dialogic_dossiers.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  summary -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
