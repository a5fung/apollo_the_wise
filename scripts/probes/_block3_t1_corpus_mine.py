"""Block 3 T1(b) — mine the HISTORICAL half of the judge-robustness corpus (read-only, Opus prep).

Roadmap: docs/roadmap/fable-weekend-blocks.md §Block3 T1(b) — "~50-100 cases: half synthetic,
half mined from history — #416 FP labels + judge-delta digests seed it." This pulls the real graded
cases from mi_audit_log, dedups to diverse tickers, joins the forward outcome, and assigns a
data-grounded GOLDEN verdict per class — the mined half of the corpus for tomorrow's Fable session,
which then curates + adds the synthetic adversarial half + designs the taxonomy/eval/regression gate.

Classes mined (the emergent misdirection taxonomy):
  A M&A / acquirer-pop / rotation-not-company-specific  (mna_filter_fired)  → golden REJECT_MNA
  B beat-headline-masks-weak-revenue  (catalyst_earnings_revenue_weak_downgrade)  → golden DOWNGRADE
  C earnings-boost + outcome  (catalyst_earnings_boost + mi_daily_closes 5d-max)  → PASS_CONFIRMED / FALSE_BOOST
  D live judge verdicts  (ep_grade_decision)  → labeled vs outcome (demote_justified / demote_miss / …)

Prints a human SUMMARY then a delimited CORPUS_JSON block (captured → the .json data file).
Run: docker cp then docker exec -w /app apollo-market python /tmp/_block3_t1_corpus_mine.py
"""
import asyncio
import json
import sys
from datetime import date

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool

PER_CLASS = 14   # diverse-ticker sample per class (D = all, small N)
WIN_5D = 10.0    # % max_high_5d that counts a move as "followed through"


def _d(detail):
    if isinstance(detail, dict):
        return detail
    try:
        return json.loads(detail) if detail else {}
    except Exception:
        return {}


async def _sample_by_ticker(conn, event_type, n):
    """Fetch all rows of an event_type (detail is TEXT → parse in Python), dedup to
    the n most-recent DISTINCT tickers. Robust to malformed detail rows (skipped)."""
    rows = await conn.fetch(
        "SELECT detail FROM mi_audit_log WHERE event_type=$1 ORDER BY created_at DESC",
        event_type,
    )
    seen, picked = set(), []
    for r in rows:
        p = _d(r["detail"])
        tk = p.get("ticker")
        if not tk or tk in seen:
            continue
        seen.add(tk)
        picked.append(p)
        if len(picked) >= n:
            break
    return picked


async def main() -> int:
    pool = await get_pool()
    cases = []
    async with pool.acquire() as conn:
        # forward-outcome from mi_daily_closes (reliable OHLC — the Lane-1 probe source;
        # mi_ep_missed_outcomes.max_high_5d is unpopulated/0-defaulted for these tickers).
        # 5d-max-high % from the alert-day close; cached per (ticker, alert_date).
        _fwd_cache = {}

        async def fwd_pct(ticker, ad):
            if not ticker or not ad:
                return None
            try:
                d0 = date.fromisoformat(str(ad)[:10])
            except Exception:
                return None
            key = (ticker, d0)
            if key in _fwd_cache:
                return _fwd_cache[key]
            r = await conn.fetchrow("""
                SELECT (SELECT close::float FROM mi_daily_closes
                        WHERE ticker=$1 AND trade_date=$2) AS c0,
                       (SELECT max(high_price)::float FROM mi_daily_closes
                        WHERE ticker=$1 AND trade_date BETWEEN $2 + 1 AND $2 + 8
                          AND high_price IS NOT NULL) AS mh
            """, ticker, d0)
            val = None
            if r and r["c0"] and r["mh"] and r["c0"] > 0:
                pct = round(100.0 * (r["mh"] - r["c0"]) / r["c0"], 1)
                val = pct if -95.0 <= pct <= 1000.0 else None
            _fwd_cache[key] = val
            return val

        # ── Class A: M&A / rotation misdirection ──
        for p in await _sample_by_ticker(conn, "mna_filter_fired", PER_CLASS):
            cases.append({"class": "A_mna_misdirection", "ticker": p.get("ticker"),
                          "alert_date": p.get("alert_date"),
                          "payload": (p.get("news_summary") or "")[:300],
                          "system_action": f"mna_filter_fired (quality={p.get('catalyst_quality')})",
                          "fwd_max5d_pct": await fwd_pct(p.get("ticker"), p.get("alert_date")),
                          "golden": "REJECT_MNA",
                          "golden_rationale": "M&A / acquirer-pop / broad-rotation move — NOT a company-specific fundamental catalyst; the grader must not treat it as a HIGH growth catalyst."})

        # ── Class B: beat-headline masks weak revenue ──
        for p in await _sample_by_ticker(conn, "catalyst_earnings_revenue_weak_downgrade", PER_CLASS):
            cases.append({"class": "B_beat_masks_weak_revenue", "ticker": p.get("ticker"),
                          "alert_date": p.get("alert_date"),
                          "payload": (p.get("reason") or "")[:300],
                          "system_action": f"downgrade {p.get('from_quality')}→{p.get('to_quality')}",
                          "fwd_max5d_pct": await fwd_pct(p.get("ticker"), p.get("alert_date")),
                          "golden": "DOWNGRADE",
                          "golden_rationale": "Headline beat but the load-bearing revenue signal is weak — grader must downgrade, not reward the beat headline."})

        # ── Class C: earnings boost, labeled by outcome ──
        for p in await _sample_by_ticker(conn, "catalyst_earnings_boost", PER_CLASS):
            fwd = await fwd_pct(p.get("ticker"), p.get("alert_date"))
            if fwd is None:
                golden, rat = "PASS_UNVERIFIED", "Boost to strong; no forward outcome on file to confirm."
            elif fwd >= WIN_5D:
                golden, rat = "PASS_CONFIRMED", f"Boost justified — the name followed through (+{fwd}% 5d-max)."
            else:
                golden, rat = "FALSE_BOOST", f"Strong print but NO follow-through ({fwd}% 5d-max) — a boost the grader should have been cautious on."
            cases.append({"class": "C_earnings_boost", "ticker": p.get("ticker"),
                          "alert_date": p.get("alert_date"),
                          "payload": f"boost {p.get('from_quality')}→{p.get('to_quality')}",
                          "system_action": "catalyst_earnings_boost",
                          "fwd_max5d_pct": fwd, "golden": golden, "golden_rationale": rat})

        # ── Class D: live judge verdicts (all of them — the eval targets) ──
        rows = await conn.fetch("""
            SELECT detail FROM mi_audit_log WHERE event_type='ep_grade_decision'
            ORDER BY created_at DESC
        """)
        for r in rows:
            p = _d(r["detail"])
            tk = p.get("ticker") or p.get("symbol")
            fwd = await fwd_pct(tk, p.get("alert_date")) if tk else None
            direction = p.get("judge_direction")
            if fwd is None:
                label = f"{direction}_unverified"
            elif direction == "demote":
                label = "demote_justified" if fwd < WIN_5D else "demote_MISS"
            elif direction in ("promote", "affirm", None):
                label = "kept_confirmed" if (fwd is not None and fwd >= WIN_5D) else "kept_faded"
            else:
                label = f"{direction}_{'run' if fwd >= WIN_5D else 'fade'}"
            cases.append({"class": "D_live_judge_verdict", "ticker": tk,
                          "alert_date": p.get("alert_date"),
                          "payload": (p.get("rationale") or "")[:340],
                          "system_action": f"judge {direction}→{p.get('judge_grade')}/{p.get('judge_tier')} "
                                           f"(theme={p.get('in_active_theme')}, cap={p.get('market_cap')}, sector={p.get('sector')})",
                          "fwd_max5d_pct": fwd, "golden": label,
                          "golden_rationale": "Live judge decision — the eval measures whether the demote/keep matched the forward outcome."})

    # ── SUMMARY ──
    from collections import Counter
    by_class = Counter(c["class"] for c in cases)
    print("=== BLOCK 3 T1(b) MINED CORPUS — SUMMARY ===")
    print(f"Total mined cases: {len(cases)}")
    for k in sorted(by_class):
        print(f"  {k:<28} {by_class[k]}")
    print("\nGolden-verdict distribution:")
    for g, n in Counter(c["golden"] for c in cases).most_common():
        print(f"  {g:<20} {n}")
    # the standout hard cases (false boosts + demote misses)
    hard = [c for c in cases if c["golden"] in ("FALSE_BOOST", "demote_MISS")]
    print(f"\nHARD cases (the grader/judge got the risk wrong ex-post): {len(hard)}")
    for c in hard[:12]:
        print(f"  [{c['class'][:1]}] {c['ticker']} {c['alert_date']} — {c['golden']} (fwd={c['fwd_max5d_pct']}%)")

    print("\n=== CORPUS_JSON ===")
    print(json.dumps(cases, indent=None, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
