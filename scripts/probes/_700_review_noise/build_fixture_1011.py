"""#700 — build tests/fixtures/weekly_review_1011.json from the one-time prod capture (read-only,
local files; no DB, no send).

The fixture is the stored 2026-10-11 review row trimmed to the keys the renderer reads, the
2026-10-04 row's comparison inputs (what `prior` is on the 10-18 first run: raw metrics, NO snapshot),
and the render-time inputs the 10-11 run computed live (cohort, setup row, theme rows, spend) rebuilt
from `q3_render_inputs.out` + the #486/#313 captures, so `tests/test_weekly_review_noise_700.py`
renders the REAL 10-11 content through `_assemble_report` and counts the characters.

`before` (the 10-11 fold length and checked-line phrases under the PRE-#700 renderer) is merged in by
`capture_before.py`, run ONCE against origin/main code before the renderer was changed; this script
keeps whatever `before` block the existing fixture already has.

    python scripts/probes/_700_review_noise/build_fixture_1011.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "tests" / "fixtures" / "weekly_review_1011.json"

# Keys of the stored `metrics` the renderer (or the settle rule's ticker walk) reads.
KEEP = ["regime", "pending_reviews", "audit_errors", "strategy_promotions", "loser_breakdown",
        "mfe_capture", "judge_weekly", "missed_opportunities", "crypto", "anomalies", "drift_check",
        "postmortem_best", "postmortem_worst", "cooldowns", "theme_churn", "window"]


def _stored() -> dict:
    rows = [json.loads(l) for l in (HERE / "q1_reviews.out").read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("{")]
    return {r["review_date"]: r for r in rows}


def _sections() -> dict:
    sec, cur = {}, None
    for raw in (HERE / "q3_render_inputs.out").read_text(encoding="utf-8").splitlines():
        if raw.startswith("=== "):
            cur = raw[4:].strip()
            sec[cur] = []
            continue
        if cur and raw and not raw.startswith("(") and "\t" in raw:
            sec[cur].append(raw.split("\t"))
    return sec


def _trim_postmortem(p):
    if not p:
        return p
    return {k: (v if k != "narrative" else v[:200]) for k, v in p.items()}


def _live_closed(sec: dict) -> list[dict]:
    out = []
    for r in sec["LIVE_CLOSED"][1:]:
        _id, ticker, ad, sig, pnl, risk_actual, shares, entry, stop, exit_reason, _closed = r
        risk = float(risk_actual) if risk_actual else float(shares) * (float(entry) - float(stop))
        out.append({"ticker": ticker, "alert_date": ad, "signal_type": sig, "exit_reason": exit_reason,
                    "r": float(pnl) / risk})
    return out


def _theme_rows() -> dict:
    """Synthetic clean-read rows reproducing the 10-11 #486 readout: this week n=6 (both 2, judge-only 1,
    engine-only 1, neither 2), last 30 days n=14 (both 4, judge-only 2, engine-only 1, neither 7), the two
    judge-only names AAOI 10-09 (theme known, excluded - Nascent) and AKAM 09-25 (no theme row), and 22
    judge-graded alerts in all (8 left out of the clean read)."""
    def row(t, d, eng, jdg, name=None, stage=None):
        return {"ticker": t, "alert_date": d, "engine_theme": eng, "judge_theme": jdg,
                "theme_name_7d": name, "theme_stage_7d": stage}
    rows = [
        row("AAOI", "2026-10-09", False, True, "Optical", "Nascent"),    # judge only (this week)
        row("W1", "2026-10-08", True, True, "Cloud", "Mainstream"),      # both (this week)
        row("W2", "2026-10-07", True, True, "Cloud", "Mainstream"),      # both (this week)
        row("W3", "2026-10-06", True, False, "Cloud", "Mainstream"),     # engine only (this week)
        row("W4", "2026-10-05", False, False),                           # neither (this week)
        row("W5", "2026-10-05", False, False),                           # neither (this week)
        row("AKAM", "2026-09-25", False, True),                          # judge only (30d)
        row("T1", "2026-09-24", True, True, "Cloud", "Mainstream"),      # both (30d)
        row("T2", "2026-09-23", True, True, "Cloud", "Mainstream"),      # both (30d)
    ] + [row(f"N{i}", f"2026-09-{12 + i:02d}", False, False) for i in range(5)]   # neither (30d)
    return {"clean": rows, "left_out": 8, "left_out_judge_themed": 1}


def main() -> None:
    by, sec = _stored(), _sections()
    cur, prev = by["2026-10-11"], by["2026-10-04"]
    m, p = cur["metrics"], prev["metrics"]
    metrics = {k: m[k] for k in KEEP if k in m}
    metrics["postmortem_best"] = _trim_postmortem(metrics.get("postmortem_best"))
    metrics["postmortem_worst"] = _trim_postmortem(metrics.get("postmortem_worst"))
    pr = metrics["pending_reviews"]
    metrics["pending_reviews"] = {"ready": pr["ready"], "errored": pr.get("errored") or [],
                                  "pending_count": pr["pending_count"]}
    prior_metrics = {
        "crypto": p["crypto"], "mfe_capture": p["mfe_capture"],
        "strategy_promotions": {"checks": p["strategy_promotions"]["checks"]},
        "missed_opportunities": {"gaps": p["missed_opportunities"]["gaps"],
                                 "source_gap_summary": p["missed_opportunities"]["source_gap_summary"]},
    }
    prior_1004_errors = {"audit_errors": p["audit_errors"], "losers": p["loser_breakdown"],
                         "top_winners": p["missed_opportunities"].get("top_winners") or [],
                         "cooldowns": p.get("cooldowns"), "theme_churn": p.get("theme_churn"),
                         "anomalies": p.get("anomalies"), "postmortem_best": _trim_postmortem(p.get("postmortem_best"))}
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    fixture = {
        "review": {"review_date": cur["review_date"], "summary": cur["summary"],
                   "suggestions": cur["suggestions"], "metrics": metrics},
        "prior": {"review_date": prev["review_date"], "window_days": 7, "metrics": prior_metrics},
        "review_1004": {"summary": prev["summary"], "suggestions": prev["suggestions"],
                        "metrics": {**prior_1004_errors, "window": p.get("window")}},
        "render_inputs": {
            "live_closed": _live_closed(sec),
            "open_live": [{"ticker": r[0], "hold_days": int(r[1])} for r in sec["OPEN_LIVE"][1:]],
            "setup_row": {"signal_type": "magna53", "account_mode": "live", "n": 31, "wins": 9,
                          "total_pnl": 2.41, "top_exit": "stop_hit", "n_stop_hit": 25,
                          "med_peak_r": 1.2721, "med_realized_r": -0.9993, "ran_then_lost": 5,
                          "med_stop_per_adr": 0.8466, "blind_peaks": 5, "phase": "live"},
            "second_opinion": "\U0001F50D *Judge 2nd-opinion (#301, claude-sonnet-5-5):* 0/5 disagreed (0%) "
                              "with the HIGH-tier judge verdict this week",
            "spend_envelope": {"text": "\U0001F4B5 *Cost envelope (MTD)*\nLLM: $13.66 / $150 (9%) ✓ · "
                                       "2032 calls\n  theme assignment: $2.81\n  chart axis pilot: $2.12\n"
                                       "  perplexity news search: $1.83\n_+ fixed infra/data subs (server · "
                                       "Polygon · FMP) not metered here — see the cost-envelope doc._",
                               "cost": 13.662, "budget": 150.0},
            "theme": _theme_rows(),
            "spend_callers": [
                {"caller": "eval_519_option_a", "spend": 9.22, "calls": 40},
                {"caller": "perplexity_news_search", "spend": 8.09, "calls": 2400},
                {"caller": "theme_assignment", "spend": 7.21, "calls": 800},
                {"caller": "judge_robustness_eval", "spend": 0.90, "calls": 30},
                {"caller": "ep_grade_judge", "spend": 0.71, "calls": 60},
                {"caller": "mgmt_judge", "spend": 0.42, "calls": 20},
                {"caller": "judge_divergence", "spend": 0.56, "calls": 40},
                {"caller": "other_lane_a", "spend": 6.07, "calls": 800},
                {"caller": "other_lane_b", "spend": 6.07, "calls": 700},
                {"caller": "other_lane_c", "spend": 6.08, "calls": 733},
            ],
            "live_book": {"account_mode": "live", "n": 6, "wins": 3, "total_pnl": 17.0},
        },
    }
    if "before" in old:
        fixture["before"] = old["before"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {OUT.stat().st_size} bytes; today={date(2026, 10, 11)}")


if __name__ == "__main__":
    main()
