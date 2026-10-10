"""#598 render fix (wk1010) - sample render of every changed surface for ONE real current candidate.

READ-ONLY and offline: the rows are the prod SELECT already captured in
q1_short_base_candidates.out (mi_flag_candidates, TIGHTENING/COILED, last 30 days, captured once);
nothing here touches the database.

  AFTER  = the code in this worktree.
  BEFORE = the same surfaces from a saved copy of HEAD (`git show HEAD:<path>`), so the contrast is
           produced by the old code itself, not retyped.

Run from the repo root:
    python scripts/probes/_wk1010_598/render_sample.py <flag_detector_head.py> <agent_head.py>
"""
from __future__ import annotations

import asyncio
import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

Q1 = Path(__file__).with_name("q1_short_base_candidates.out")


def _num(v):
    return None if v in ("", None) else float(v)


def load_rows():
    lines = [ln for ln in Q1.read_text().splitlines() if ln and not ln.startswith("(")]
    out = []
    for r in csv.DictReader(lines, delimiter="\t"):
        out.append({
            "scan_date": date.fromisoformat(r["scan_date"]), "ticker": r["ticker"], "stage": r["stage"],
            "base_age": int(r["base_age"]), "runup_pct": _num(r["runup_pct"]),
            "pivot_high_price": _num(r["pivot_high_price"]),
            "range_contraction_ratio": _num(r["range_contraction_ratio"]),
            "vol_contraction_ratio": _num(r["vol_contraction_ratio"]),
            "fresh_tight_fires": {"t": True, "f": False}.get(r["fresh_tight_fires"]),
            "fresh_2bar_tr_pct": _num(r["fresh_2bar_tr_pct"]), "atr14_pct": _num(r["atr14_pct"]),
            "held_from_stage": r["held_from_stage"] or None, "reason": r["reason"] or None,
        })
    return out


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def board(*rows):
    b = {s: [] for s in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH", "INVALIDATED", "unqualified")}
    for r in rows:
        b[r["stage"]].append(r)
    return b


def flags_reply(agent_mod, rows, history=None, task="/flags", scan_date=None):
    from agents.market_intelligence import db
    from shared.models import AgentRequest

    class _Conn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def fetchval(self, *a, **kw):
            return scan_date or max((r["scan_date"] for r in rows), default=date.today())  # tz-ok: offline probe, scripts/ is outside the hygiene gate

    class _Pool:
        def acquire(self):
            return _Conn()

    async def _window(query_date, stages=None):
        return rows

    async def _history(ticker, days=14):
        return history or []

    db.get_flag_candidates_window = _window
    db.get_ticker_flag_history = _history
    db.get_pool = AsyncMock(return_value=_Pool())
    db.get_htf_breakout_shadow_summary = AsyncMock(return_value={})
    res = asyncio.run(agent_mod.MarketIntelligenceAgent()._handle_flag_query(
        AgentRequest(task=task, user_id=1, conversation_id="sample")))
    return res.result or ""


def main(head_fd_path, head_agent_path):
    from agents.market_intelligence import agent as new_agent
    from agents.market_intelligence import flag_detector as new_fd
    from shared import telegram_format as tf

    old_fd = load_module("flag_detector_head", head_fd_path)
    old_agent = load_module("agent_head", head_agent_path)

    rows = load_rows()
    latest = max(r["scan_date"] for r in rows)
    kod = sorted((r for r in rows if r["ticker"] == "KOD"), key=lambda r: r["scan_date"])
    kod_entered, kod_now = kod[0], kod[-1]                      # 2026-10-08 (entered), 2026-10-09 (latest)
    long_ref = next(r for r in rows if r["ticker"] == "HTFL" and r["base_age"] > 5)   # unchanged reference
    cur = [r for r in rows if r["scan_date"] == latest]

    out = []

    def section(title, before, after):
        out.append(f"{'=' * 100}\n{title}\n{'=' * 100}")
        out.append("--- BEFORE (HEAD) ---\n" + before.rstrip())
        out.append("--- AFTER (this change) ---\n" + after.rstrip() + "\n")

    def digest(mod, row):
        b = board(row)
        return tf.to_plain(mod.build_flag_digest(b, row["scan_date"], mod.stage_transitions(b, {})) or "(no digest)")

    out.append(
        "Sample render, #598 short-base tightness (wk1010, 2026-10-10). READ-ONLY, offline: rows are the\n"
        "prod SELECT in q1_short_base_candidates.out. Current candidate = KOD (the only TIGHTENING/COILED name\n"
        f"on the latest scan, {latest}): COILED, base 5d, stored range 1.0 / volume 1.0, fresh path NOT firing\n"
        "(held COILED from WATCH), last two bars 6.64% vs ATR 10.53%. Its 2026-10-08 row (base 4d, fresh path\n"
        "firing) is the day it entered COILED - the row the NEW TODAY block rendered. Plain text below is the\n"
        "digest HTML run through tf.to_plain; /flags is the raw Markdown the handler returns.\n")

    section(f"1. 17:25 digest, NEW TODAY block - KOD entered COILED {kod_entered['scan_date']} (base {kod_entered['base_age']}d, fresh path firing)",
            digest(old_fd, kod_entered), digest(new_fd, kod_entered))
    section(f"2. 17:25 digest, standing COILED roster - KOD still coiled {kod_now['scan_date']} (base {kod_now['base_age']}d, fresh path not firing)",
            old_fd._fmt_coiled(kod_now), new_fd._fmt_coiled(kod_now))
    section(f"3. /flags board - latest scan {latest} ({len(cur)} TIGHTENING/COILED row)",
            flags_reply(old_agent, cur), flags_reply(new_agent, cur))
    hist = sorted(kod, key=lambda r: r["scan_date"], reverse=True)
    section("4. /flags KOD - 14-day stage history (rows available from the capture: its TIGHTENING/COILED days)",
            flags_reply(old_agent, [], history=hist, task="/flags KOD"),
            flags_reply(new_agent, [], history=hist, task="/flags KOD"))
    section(f"5. UNCHANGED reference - {long_ref['ticker']} {long_ref['scan_date']} base {long_ref['base_age']}d (longer than 5 sessions, ratios mean something)",
            digest(old_fd, long_ref) + "\n" + flags_reply(old_agent, [long_ref]),
            digest(new_fd, long_ref) + "\n" + flags_reply(new_agent, [long_ref]))

    same5 = (digest(old_fd, long_ref) == digest(new_fd, long_ref)
             and flags_reply(old_agent, [long_ref]) == flags_reply(new_agent, [long_ref]))
    out.append(f"Section 5 byte-identical before/after: {same5}")
    n_short = sum(1 for r in rows if r["base_age"] <= 5)
    out.append(f"Capture facts: {len(rows)} TIGHTENING/COILED rows in 30 days; {n_short} with base_age <= 5 "
               f"({', '.join(sorted({r['ticker'] + ' ' + str(r['scan_date']) for r in rows if r['base_age'] <= 5}))}); "
               f"min base_age = {min(r['base_age'] for r in rows)} - no base <= 3 row, so 'n/a' is test-covered only.")
    text = "\n".join(out)
    Path(__file__).with_name("sample_render.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
