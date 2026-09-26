"""#668 — split the post-swap alpha-capture shortfall into (a) carryforward-not-firing vs
(c) names-do-not-base-under-the-sourced-HTF-spec, plus the residual neither explains.

Reads ONLY the files _668_pull.py captured (no prod access). Replays the flag detector as it ran
inside the measured window — the file at commit 0f82018f (2026-08-06; the last change to
compute_flag_metrics before 2026-08-27 — later commits add #592's pivot-walk rule and telemetry
columns only) — over the stored daily bars, with 380 CALENDAR days of history as that era's
get_recent_daily_history sliced it.

Outputs (scripts/probes/_668_out/):
  summary.txt          every table the write-up quotes, with its n
  per_name.csv         one row per uncaptured post-swap alpha name: what the board stored, what
                       the replay says, the furthest gate reached, the modal blocking gate
  rule_audit.csv       per scan day: R3 admissions expected under the path's own rule vs actual
  replay_vs_stored.csv agreement check, replay vs the board's stored verdict, same ticker-day

Run: python scripts/probes/_668_analyze.py
"""
from __future__ import annotations

import collections
import csv
import gzip
import importlib.util
import io
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "scripts/probes/_668_out"
sys.path.insert(0, str(REPO))

ERA_COMMIT = "0f82018f"
SWAP_DATE = date(2026, 6, 26)          # #356, commit 932dc066 — the flag-criteria era boundary
FIX_FIRST_SCAN = date(2026, 8, 12)     # 93dcd212 committed 08-11 08:47 ET; first scan under it
DARK_FROM = date(2026, 6, 22)          # MAGNA53 went live; path (c) blind to live rows from here
POST_LO, POST_HI = date(2026, 6, 26), date(2026, 8, 27)   # the 20.3% baseline's alert_date bounds
PRE_HI = date(2026, 6, 24)
FLAG_STAGES = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
R3_LOOKBACK_DAYS = 7
HISTORY_CALENDAR_DAYS = 380


# ── era detector ──────────────────────────────────────────────────────────────
def load_era_detector():
    """Extract the era detector OUTSIDE the repo tree. It must never land under scripts/: the
    2026-08-06 file still carries two hand-rolled env comparisons that #681 has since routed
    through env_is_true, and tests/test_681_one_reader_per_env_flag.py rglobs scripts/ — an
    on-disk copy (even gitignored) fails the suite the pre-push hook runs."""
    src = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{ERA_COMMIT}:agents/market_intelligence/flag_detector.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    path = Path(tempfile.mkdtemp(prefix="apollo_668_era_")) / "flag_detector_era.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location("flag_detector_era", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── loaders ───────────────────────────────────────────────────────────────────
def d(s: str) -> date:
    return date.fromisoformat(s[:10])


def load_csv(name: str) -> list[dict]:
    return list(csv.DictReader((OUT / name).open()))


def load_bars() -> dict[str, list[dict]]:
    with gzip.open(OUT / "bars.csv.gz", "rt") as fh:
        rows = list(csv.DictReader(fh))
    by: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by[r["ticker"]].append({
            "trade_date": d(r["trade_date"]),
            "open_price": float(r["open_price"]) if r["open_price"] else None,
            "high_price": float(r["high_price"]) if r["high_price"] else None,
            "low_price": float(r["low_price"]) if r["low_price"] else None,
            "close": float(r["close"]) if r["close"] else None,
            "volume": float(r["volume"]) if r["volume"] else 0.0,
        })
    for t in by:
        by[t].sort(key=lambda b: b["trade_date"])
    return by


# ── cohort definitions (identical to the 2026-09-16 read) ─────────────────────
FAIL_CLASSES = {"LOST_DAY1", "NO_ENTRY", "SKIPPED", "NO_TRADE_ROW"}


def is_alpha(r: dict) -> bool:
    return bool(r["d0_open"] and r["max_high_21d"]
                and float(r["max_high_21d"]) / float(r["d0_open"]) - 1 > 0.05)


def legs(r: dict) -> dict[str, bool]:
    return {
        "flag": bool(r["next_flag_date_incl_tightening"]),
        "later_ep": bool(r["next_ep_date"]),
        "ninem_ep": bool(r["next_9m_ep_date"]),
        "ninem_day2": bool(r["next_day2_date"]),
    }


def captured(r: dict, with_9m: bool = True) -> bool:
    L = legs(r)
    return L["flag"] or L["later_ep"] or (with_9m and (L["ninem_ep"] or L["ninem_day2"]))


def era_of(r: dict) -> str:
    a = d(r["alert_date"])
    if a <= PRE_HI:
        return "PRE"
    if POST_LO <= a <= POST_HI:
        return "POST"
    return "OTHER"


# ── gate classification (order = the order compute_flag_metrics evaluates them) ─
GATE_ORDER = [
    "liquidity", "no_pivot", "base_too_young", "pole_under_90pct", "pole_quality",
    "base_too_old", "broke_base_low", "below_sma20", "below_sma50", "ma_stack",
    "not_near_52w_high", "below_sma200", "depth_over_25pct", "mna_filter",
    "WATCH", "TIGHTENING", "COILED", "TRIGGERED",
]
GATE_RANK = {g: i for i, g in enumerate(GATE_ORDER)}


def gate_of(stage: str, reason: str | None) -> str:
    if stage in FLAG_STAGES:
        return stage
    s = reason or ""
    if s.startswith("adv_") or s.startswith("adr_"):
        return "liquidity"
    if s.startswith("no_pivot") or s.startswith("no_rows") or s.startswith("missing_ohlcv"):
        return "no_pivot"
    if s.startswith("base_age_") and "_below_" in s:
        return "base_too_young"
    if s.startswith("runup_") and "below_90" in s:
        return "pole_under_90pct"
    if s.startswith("flagpole_"):
        return "pole_quality"
    if s.startswith("base_age_") and "_over_" in s:
        return "base_too_old"
    if "below_base_low_close" in s:
        return "broke_base_low"
    if "below_sma20" in s:
        return "below_sma20"
    if "below_sma50" in s:
        return "below_sma50"
    if s.startswith("ma_stack_not_stage2"):
        return "ma_stack"
    if s.startswith("pole_") and "52w_high" in s:
        return "not_near_52w_high"
    if "below_sma200" in s:
        return "below_sma200"
    if s.startswith("flag_low_"):
        return "depth_over_25pct"
    if s.startswith("mna_filter"):
        return "mna_filter"
    if s.startswith("runup_window") or s.startswith("runup_low"):
        return "no_pivot"
    return f"other:{s[:30]}"


# ── replay ────────────────────────────────────────────────────────────────────
def replay_window(mod, ticker: str, bars: list[dict], days: list[date]) -> list[dict]:
    """Chain the era detector across `days` (ascending) as if the ticker were in the
    universe every one of them: yesterday_stage / recent_stages / prior pivot carried
    from the previous replayed day, exactly as run_flag_scan threads them from stored rows."""
    out = []
    prev_stage = None
    recent: list[str] = []
    prior_pivot = (None, None)
    for D in days:
        lo = D - timedelta(days=HISTORY_CALENDAR_DAYS)
        hist = [b for b in bars if lo <= b["trade_date"] <= D]
        if len(hist) < 60 or hist[-1]["trade_date"] != D:
            out.append({"scan_date": D, "stage": None, "reason": "no_bar_or_short_history"})
            continue
        m = mod.compute_flag_metrics(
            hist, ticker=ticker, yesterday_stage=prev_stage, recent_stages=list(recent),
            prior_pivot_date=prior_pivot[0], prior_pivot_high=prior_pivot[1],
        )
        out.append({"scan_date": D, "stage": m["stage"], "reason": m["reason"],
                    "base_age": m.get("base_age"), "runup_pct": m.get("runup_pct"),
                    "pivot_high_date": m.get("pivot_high_date")})
        prev_stage = m["stage"]
        recent = (recent + [m["stage"]])[-5:]
        if m.get("pivot_high_date") is not None:
            prior_pivot = (m["pivot_high_date"], m["pivot_high_price"])
    return out


def main() -> None:
    mod = load_era_detector()
    cohort = load_csv("cohort.csv")
    r3_rows = load_csv("r3_rows.csv")
    r3_flag = load_csv("r3_flag_rows.csv")
    census = load_csv("scan_census.csv")
    stored = load_csv("cohort_flag_rows.csv")
    bars = load_bars()
    S = io.StringIO()

    def P(*a):
        print(*a)
        print(*a, file=S)

    # ── 1. the baseline, reproduced (never blended across the swap) ───────────
    P("## 1. Baseline reproduction — alpha capture, split at the 2026-06-26 swap")
    P("flag leg = any of WATCH/TIGHTENING/COILED/TRIGGERED (the 09-16 read's definition;")
    P("the shipped ep_delayed_capture_audit.py omits TIGHTENING — noted, both shown)")
    era_rows: dict[str, list[dict]] = collections.defaultdict(list)
    for r in cohort:
        if r["day1_class"] in FAIL_CLASSES:
            era_rows[era_of(r)].append(r)
    for e in ("PRE", "POST"):
        failed = era_rows[e]
        alpha = [r for r in failed if is_alpha(r)]
        cap_all = sum(captured(r) for r in alpha)
        cap_no9m = sum(captured(r, with_9m=False) for r in alpha)
        cap_script = sum(bool(r["next_flag_date"] or r["next_ep_date"] or r["next_9m_ep_date"]
                              or r["next_day2_date"]) for r in alpha)
        leg_ct = collections.Counter()
        for r in alpha:
            for k, v in legs(r).items():
                leg_ct[k] += int(v)
            L = legs(r)
            if L["flag"] and not (L["later_ep"] or L["ninem_ep"] or L["ninem_day2"]):
                leg_ct["flag_only"] += 1
            if (L["ninem_ep"] or L["ninem_day2"]) and not (L["flag"] or L["later_ep"]):
                leg_ct["ninem_only"] += 1
        P(f"{e}: failed-Day-1 n={len(failed)}, alpha n={len(alpha)}, captured {cap_all} "
          f"({cap_all/len(alpha)*100:.1f}%), without the two 9M legs {cap_no9m} "
          f"({cap_no9m/len(alpha)*100:.1f}%), script-definition (no TIGHTENING) {cap_script}; "
          f"legs {dict(leg_ct)}")
    post_alpha = [r for r in era_rows["POST"] if is_alpha(r)]
    unc = [r for r in post_alpha if not captured(r)]
    P(f"POST uncaptured n={len(unc)}; day1_class mix {dict(collections.Counter(r['day1_class'] for r in unc))}")
    P(f"POST alpha day1_class mix {dict(collections.Counter(r['day1_class'] for r in post_alpha))}")
    P(f"POST uncaptured with an R3 row (the carryforward's ONLY trigger): "
      f"{[(r['ticker'], r['alert_date']) for r in unc if int(r['r3_rows']) > 0]}")
    P("")

    # ── 2. (a) the carryforward against its own rule, every scan day ──────────
    P("## 2. (a) carryforward path — expected admissions under its own rule vs actual")
    r3_by_alert: list[tuple[date, str, str]] = [(d(r["alert_date"]), r["ticker"], r["account_mode"]) for r in r3_rows]
    actual: dict[date, set[str]] = collections.defaultdict(set)
    for r in r3_flag:
        actual[d(r["scan_date"])].add(r["ticker"])
    scan_days = [d(c["scan_date"]) for c in census if int(c["rows_total"]) >= 200]
    audit_rows = []
    buckets = collections.defaultdict(lambda: {"scan_days": 0, "expected_td": 0, "actual_td": 0,
                                               "missed_td": 0, "missed_tickers": set(), "expected_tickers": set()})
    for D in scan_days:
        exp = {t for (a, t, _m) in r3_by_alert if D - timedelta(days=R3_LOOKBACK_DAYS) <= a < D}
        act = actual.get(D, set())
        if D < DARK_FROM:
            b = "paper_era_<06-22"
        elif D < FIX_FIRST_SCAN:
            b = "dark_06-22..08-11"
        else:
            b = "post_fix_>=08-12"
        B = buckets[b]
        B["scan_days"] += 1
        B["expected_td"] += len(exp)
        B["actual_td"] += len(act & exp)
        B["missed_td"] += len(exp - act)
        B["missed_tickers"] |= (exp - act)
        B["expected_tickers"] |= exp
        extra = act - exp
        audit_rows.append({"scan_date": D, "bucket": b, "expected": " ".join(sorted(exp)),
                           "actual": " ".join(sorted(act)), "missed": " ".join(sorted(exp - act)),
                           "unexpected": " ".join(sorted(extra))})
    with (OUT / "rule_audit.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(audit_rows[0].keys()))
        w.writeheader()
        w.writerows(audit_rows)
    for b, B in buckets.items():
        P(f"{b}: scan days {B['scan_days']}, expected ticker-days {B['expected_td']}, fired {B['actual_td']}, "
          f"missed {B['missed_td']}; expected tickers {len(B['expected_tickers'])}, "
          f"missed tickers {len(B['missed_tickers'])} {sorted(B['missed_tickers'])}")
    unexpected = [a for a in audit_rows if a["unexpected"]]
    P(f"admissions NOT explained by the rule: {len(unexpected)} {[(a['scan_date'], a['unexpected']) for a in unexpected][:5]}")
    live_r3 = [(a, t) for (a, t, m) in r3_by_alert if m == "live"]
    P(f"live R3 events total {len(live_r3)} from {min(a for a, _ in live_r3)} to {max(a for a, _ in live_r3)} "
      f"= {len(live_r3) / ((max(a for a, _ in live_r3) - min(a for a, _ in live_r3)).days / 7):.1f}/week")
    P("")

    # ── 3. replay the 55 under the era detector, every window day ─────────────
    P("## 3. (c) the uncaptured names under the sourced HTF spec — stored verdicts + replay")
    stored_by: dict[tuple[str, str], dict[date, dict]] = collections.defaultdict(dict)
    for s in stored:
        stored_by[(s["ticker"], s["alert_date"])][d(s["scan_date"])] = s
    scan_day_set = set(scan_days) | {d(c["scan_date"]) for c in census}
    per_name = []
    agree_rows = []
    for r in unc:
        t, a = r["ticker"], d(r["alert_date"])
        tb = bars.get(t, [])
        win_days = [b["trade_date"] for b in tb if a < b["trade_date"] <= a + timedelta(days=21)]
        rep = replay_window(mod, t, tb, win_days)
        st = stored_by.get((t, r["alert_date"]), {})
        # stored verdicts
        st_gates = [gate_of(v["stage"], v["reason"]) for v in st.values()]
        st_best = max(st_gates, key=lambda g: GATE_RANK.get(g, -1)) if st_gates else None
        # replay verdicts
        rp_gates = [gate_of(x["stage"], x["reason"]) for x in rep if x["stage"] is not None]
        rp_best = max(rp_gates, key=lambda g: GATE_RANK.get(g, -1)) if rp_gates else None
        rp_modal = collections.Counter(rp_gates).most_common(1)[0][0] if rp_gates else None
        rp_promoted_days = [x["scan_date"] for x in rep if x["stage"] in FLAG_STAGES]
        # promoted in replay on a day the board did NOT evaluate the name = a universe gap
        gap_days = [D for D in rp_promoted_days if D not in st]
        in_universe_days = sorted(st.keys())
        # R3 admission window the carryforward WOULD cover: (alert, alert+7]
        r3_days = [D for D in win_days if D <= a + timedelta(days=R3_LOOKBACK_DAYS)]
        r3_uncovered = [D for D in r3_days if D not in st]
        r3_would_promote = [D for D in r3_uncovered if any(x["scan_date"] == D and x["stage"] in FLAG_STAGES for x in rep)]
        max_runup = max((x["runup_pct"] for x in rep if x.get("runup_pct") is not None), default=None)
        per_name.append({
            "ticker": t, "alert_date": r["alert_date"], "day1_class": r["day1_class"],
            "d1_skip_reason": (r["d1_skip_reason"] or "")[:60], "has_r3_row": int(r["r3_rows"]) > 0,
            "mfe_21d_pct": round((float(r["max_high_21d"]) / float(r["d0_open"]) - 1) * 100, 1),
            "window_trading_days": len(win_days), "days_board_evaluated": len(in_universe_days),
            "board_first_eval": in_universe_days[0].isoformat() if in_universe_days else "",
            "board_best_gate": st_best or "never_in_universe",
            "replay_best_gate": rp_best, "replay_modal_gate": rp_modal,
            "replay_max_pole_ratio": round(1 + max_runup, 2) if max_runup is not None else None,
            "replay_promoted_days": len(rp_promoted_days),
            "replay_promoted_on_unevaluated_day": len(gap_days),
            "r3_window_days_uncovered_by_board": len(r3_uncovered),
            "r3_window_replay_promotes_on_uncovered_day": len(r3_would_promote),
        })
        for D, v in st.items():
            x = next((y for y in rep if y["scan_date"] == D), None)
            if x is None or x["stage"] is None:
                continue
            agree_rows.append({"ticker": t, "alert_date": r["alert_date"], "scan_date": D,
                               "stored_stage": v["stage"], "stored_gate": gate_of(v["stage"], v["reason"]),
                               "replay_stage": x["stage"], "replay_gate": gate_of(x["stage"], x["reason"]),
                               "stored_reason": (v["reason"] or "")[:60], "replay_reason": (x["reason"] or "")[:60]})
    with (OUT / "per_name.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_name[0].keys()))
        w.writeheader()
        w.writerows(per_name)
    with (OUT / "replay_vs_stored.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(agree_rows[0].keys()))
        w.writeheader()
        w.writerows(agree_rows)

    n = len(per_name)
    never_eval = [p for p in per_name if p["days_board_evaluated"] == 0]
    P(f"uncaptured n={n}; board evaluated {n - len(never_eval)} of them on >=1 window day "
      f"(median days evaluated {sorted(p['days_board_evaluated'] for p in per_name)[n // 2]} of a "
      f"median {sorted(p['window_trading_days'] for p in per_name)[n // 2]}-day window); never evaluated: "
      f"{[p['ticker'] for p in never_eval]}")
    P("board's furthest gate reached (stored rows):")
    for g, c in sorted(collections.Counter(p["board_best_gate"] for p in per_name).items(),
                       key=lambda kv: -GATE_RANK.get(kv[0], -1)):
        P(f"   {g}: {c}")
    P("replay (era detector, name in the universe EVERY window day) — furthest gate reached:")
    for g, c in sorted(collections.Counter(p["replay_best_gate"] for p in per_name).items(),
                       key=lambda kv: -GATE_RANK.get(kv[0], -1)):
        P(f"   {g}: {c}")
    P("replay — modal blocking gate per name:")
    for g, c in collections.Counter(p["replay_modal_gate"] for p in per_name).most_common():
        P(f"   {g}: {c}")
    poles = [p["replay_max_pole_ratio"] for p in per_name if p["replay_max_pole_ratio"] is not None]
    P(f"best pole ratio (pivot_high / 40d low) seen in-window per name: n={len(poles)}, "
      f"median {sorted(poles)[len(poles)//2]:.2f}, >=1.90 on {sum(1 for x in poles if x >= 1.9)} names, "
      f">=1.50 (the retired n=1 bar) on {sum(1 for x in poles if x >= 1.5)} names")
    rp_prom = [p for p in per_name if p["replay_promoted_days"] > 0]
    P(f"replay promotes (WATCH+) on >=1 window day: {len(rp_prom)} of {n}: "
      f"{[(p['ticker'], p['alert_date'], p['replay_best_gate']) for p in rp_prom]}")
    gap = [p for p in per_name if p["replay_promoted_on_unevaluated_day"] > 0]
    P(f"  ...of which promoted on a day the board did NOT evaluate the name (universe gap): {len(gap)}: "
      f"{[(p['ticker'], p['alert_date']) for p in gap]}")
    agree = sum(1 for x in agree_rows if x["stored_gate"] == x["replay_gate"])
    agree_stage = sum(1 for x in agree_rows if x["stored_stage"] == x["replay_stage"])
    P(f"replay-vs-stored agreement on the same ticker-day: gate {agree}/{len(agree_rows)}, stage {agree_stage}/{len(agree_rows)}")
    dis = collections.Counter((x["stored_gate"], x["replay_gate"]) for x in agree_rows if x["stored_gate"] != x["replay_gate"])
    P(f"  disagreements (stored -> replay): {dis.most_common(8)}")
    P("")

    # ── 4. (a) against the 55 ─────────────────────────────────────────────────
    P("## 4. (a) against the 55 — what the carryforward would have added if it had fired as written")
    r3n = [p for p in per_name if p["has_r3_row"]]
    P(f"names the rule applies to (R3-stopped): {len(r3n)} of {n}")
    for p in r3n:
        P(f"   {p['ticker']} {p['alert_date']}: board evaluated {p['days_board_evaluated']} window days "
          f"(first {p['board_first_eval']}), 7-day admission window uncovered by the board on "
          f"{p['r3_window_days_uncovered_by_board']} days, replay promotes on those: "
          f"{p['r3_window_replay_promotes_on_uncovered_day']}; board best {p['board_best_gate']}, replay best {p['replay_best_gate']}")
    would_add = sum(1 for p in r3n if p["r3_window_replay_promotes_on_uncovered_day"] > 0)
    P(f"(a) captures the carryforward would have ADDED: {would_add} of {n}  (upper bound if every R3 name based: {len(r3n)} of {n})")
    P("")

    # ── 5. the residual ───────────────────────────────────────────────────────
    P("## 5. residual — uncaptured names neither (a) nor (c) explains")
    resid = [p for p in gap if not p["has_r3_row"]]
    P(f"replay promotes on a day the board never evaluated AND no R3 row (so no lane owned admission): {len(resid)} "
      f"{[(p['ticker'], p['alert_date'], p['day1_class']) for p in resid]}")
    c_names = [p for p in per_name if p["replay_promoted_days"] == 0]
    P(f"(c) names that never form a qualifying base under the spec on ANY window day, universe or not: {len(c_names)} of {n}")
    P(f"names the board DID evaluate and rejected every day, and the replay agrees never promotes: "
      f"{sum(1 for p in per_name if p['days_board_evaluated'] > 0 and p['replay_promoted_days'] == 0)} of {n}")
    (OUT / "summary.txt").write_text(S.getvalue())


if __name__ == "__main__":
    main()
