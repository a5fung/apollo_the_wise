"""Monthly methodology backward-check sweep (#62 + #77 regime-monitor).

2026-05-20 originally shipped as quarterly. 2026-05-22 converted to
monthly cadence after the Pradeep-quote backward check (#77) made the
regime-change framing explicit: backward checks are regime-shift
monitors, NOT methodology-tuning loops. Monthly gives faster signal
without inviting frequent tuning (sample-size discipline still applies
before any methodology ship).

Per user_quarterly_rule_review.md: rules-as-SSoT, anti-overfit; batch
N≥30 evidence, not single-case reactions. Monthly cadence + per-band
WR drift is the right "regime check" granularity.

Module name retained as `quarterly_review` for caller-compat; the
cadence moved monthly per the 2026-05-22 ship.

Scripts run: see `QUARTERLY_BACKWARD_CHECK_SCRIPTS` below — that list is
the SSoT (don't maintain a duplicate roster in this docstring; it drifts).

Add scripts there as new backward checks / methodology findings ship —
EVERY load-bearing finding gets an entry or it silently goes stale
unmeasured (feedback_methodology_insights_need_periodic_revalidation).
Each registered script MUST be re-runnable via `python -m <module>` with
no required args, output to stdout, and return a clean exit code — AND print a
VERDICT line the digest classifier recognises (a phrase listed in `_NEEDS_YOU` /
`_CONCLUDED` / `_WAITING` below), in every branch it can reach. A script that prints
only a table lands in "review" and asks the operator to open a report with nothing to
act on (#691). `tests/test_691_monthly_sweep_cleanup.py` runs each script's real
formatting on synthetic input, branch by branch, and fails on any "review" or on a
registered script it has no scenario for.

Each check's last output is stored (one `backward_check_output` audit row per check per
run) so `/audit <check>` can show it later — see `store_sweep_outputs` /
`render_sweep_topic`. The `<check>` name is the module tail (`check_topic`).
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# Each entry: (display_label, module, extra_args).
# extra_args is appended to `python -m <module>` invocation.
# Monthly cadence as regime-check; methodology ship still requires
# per-script backward-check + sample-size discipline.
QUARTERLY_BACKWARD_CHECK_SCRIPTS = [
    ("Revenue-stage threshold (#50)",
     "scripts._b50_revenue_stage_threshold_backward_check", []),
    ("ATR-normalized gap scoring (#53)",
     "scripts._b53_atr_normalized_gap_backward_check", []),
    # 9M Day 2 stop/ATR distribution (#54) — RETIRED from this sweep 2026-10-03 (#691), the
    # same way #223 was below. It measures the 9M setup, which the operator ruled GONE
    # (docs/setups/ninem.md owns it): its cohort is `signal_type = '9m_day2'` trades, a setup
    # we no longer take, so a monthly re-run re-reads a cohort that cannot grow — a periodic
    # re-measurement of a dead cohort, the staleness this sweep exists to prevent. The SCRIPT
    # is kept and stays runnable by hand:
    #     python -m scripts._b54_9m_day2_stop_atr_distribution
    # Pradeep "rallying-into-catalyst" bands (#77, added 2026-05-22).
    # Regime-shift monitor: which pre-20d-return bands have highest WR?
    # Pradeep claims sideways-into-catalyst (RKLB-class) is highest WR;
    # our 60d cohort shows the OPPOSITE for late-cycle bull regime.
    # Monthly cadence will catch the inversion if regime shifts.
    ("Pradeep rally bands (#77)",
     "scripts._b77_pradeep_neglect_backward_check", []),
    # Flag detector graduation evidence (#92, added 2026-05-23).
    # First evaluation 2026-05-23 showed inverted forward returns by
    # stage — WATCH < TIGHTENING < COILED < TRIGGERED with returns
    # DECREASING as stage advances. TRIGGERED N=5 settled 10d showed
    # 0% WR, -4.51% avg. Anti-graduation evidence; continue shadow.
    # Monthly re-run tracks evolution toward N>=30 settled TRIGGERED.
    # TIGHTENING bright-spot (+1.14% 10d / 24.4% WR) flagged for
    # separate alert-class surface consideration if cohort grows.
    ("Flag detector graduation (#92)",
     "scripts._b92_flag_detector_graduation_evidence", []),
    # M&A filter Path B FP-rate drift detection (#88, added 2026-05-23).
    # 2026-05-23 ship validated 2/2 TPs kept, 8/10 FPs blocked vs 13
    # historical cases. Monthly re-evaluation classifies post-ship
    # events to detect TP regression (Polygon insights API changes)
    # or new FP patterns (sympathy-merger reasoning bleed, direction-
    # blindness via descriptions per #90).
    ("M&A filter Path B FP-rate (#88)",
     "scripts._b88_mna_filter_path_b_fp_rate", []),
    # M&A filter ACCURACY review (#284/#285, graduated 2026-06-20). Distinct from
    # the #88 Path-B FP-rate check above: this surfaces BOTH error directions for
    # operator judgment — over-fire (suppressed names that then ran >= +20% =
    # MATERIAL-MISS CANDIDATEs, the ONDS/SUNE class) AND under-fire (#284
    # acquirer-passes that might have been genuine targets). SURFACES, never
    # classifies (HARD-gate rules #3/#4). Graduated from the Sunday-review-when-ripe
    # data-gated surfacing into the monthly sweep per
    # feedback_methodology_insights_need_periodic_revalidation. 35d monthly window.
    ("M&A filter accuracy review (#284/#285)",
     "scripts.mna_filter_accuracy_review", []),
    # Intraday flag-break detector evidence (#94, added 2026-05-23).
    # Shadow-phase monthly re-evaluation. Tracks signal sustainment for
    # decision-gate at N>=10 settled breaks. Graduation to Phase 2
    # (operator-confirm entry) requires N>=10 + avg ret_10d >+3% +
    # WR>=35%. Per feedback_methodology_insights_need_periodic_revalidation.
    ("Intraday flag-break evidence (#94)",
     "scripts._b94_intraday_flag_break_evidence", []),
    # Decliner-band bounce signal deep-dive (#78, added 2026-05-23).
    # Sub-band analysis (-5/-10/-20 splits) + catalyst-quality breakdown.
    # 2026-05-23 first run: -10 to -20% sub-band is sweet spot (83% WR
    # N=6, +12.42% avg); deep -20%+ band is capitulation regime (no
    # bounce). Auto-refresh tracks signal strength as cohort grows
    # toward the N≥30 settled decision gate.
    ("Decliner band bounce signal (#78)",
     "scripts._b78_decliner_band_bounce_signal", []),
    # News source quality (2026-05-21 #71/#72 trigger) — 90d view of
    # per-source coverage/density/attribution + drift detection. Surfaces
    # silent degradation in news sources (Polygon, Alpaca, yfinance,
    # Perplexity, Claude analysis). Loud-not-silent discipline.
    ("News source quality (90d)",
     "agents.market_intelligence.news_source_quality", ["quarterly"]),
    # SIP-replay R cohort (#223) — RETIRED from this sweep 2026-08-11, operator-ruled.
    # It measured how much the IEX feed's adverse selection was costing us, as
    # Gate-3 evidence for the live cutover. BOTH of its premises have since expired:
    # the cutover happened (MAGNA53 live 2026-06-22) and prod now runs
    # ALPACA_DATA_FEED=sip, so the feed question it answers is closed. Worse, both of
    # its cohorts pin account_mode='paper', so it had been re-measuring a book frozen
    # at 06-22 (paper 25 closed + 28 cancelled, static; live 17 + 12 and growing,
    # invisible to it) — a periodic re-measurement of a dead cohort, which is exactly
    # the staleness this sweep exists to prevent, wearing the sweep's own clothes.
    # The SCRIPT is kept: it is the evidence behind the cutover decision
    # (docs/analysis/sip_replay_gate3_2026-06-06.md) and stays runnable by hand.
    # Repointing it at the live/SIP era was the alternative and was rejected — that
    # is a different measurement answering a question nobody asked.
    # ORB bar-1 wick-outlier backward check (#122, registered 2026-06-06).
    # Was orphaned — a load-bearing backward check that prints N + a
    # ship/insufficient verdict, accruing toward the N>=10 ship gate
    # (data-gated review orb_bar1_wick_outlier_persistence_filter, earliest
    # 2026-08-15). Monthly re-run tracks the cohort toward that gate so the
    # finding doesn't go stale unmeasured (same discipline as the rest).
    ("ORB bar-1 wick-outlier (#122)",
     "scripts.orb_wick_outlier_backwardcheck", []),
    # #197 cap+1 (game_changer) slot-admission SHADOW (registered 2026-06-06).
    # Observe-only tracker of policy (a): would a cap+1 admission of a
    # game_changer blocked by max_positions have paid? Accrues toward the N>=30
    # promotion gate. Read-only; live cap+1 needs sign-off + CHANGE_PROCESS.
    ("#197 cap+1 game_changer slot shadow",
     "scripts.shadow_cap_plus_one_197", []),
]


def _extract_summary_section(stdout: str, max_lines: int = 25) -> str:
    """Pull the band-level summary table out of a backward-check stdout.

    Each script prints a banner table around line ~50 with the per-band
    counts + win rates. We extract the table region by looking for
    'BAND' header or 'win rate' / 'WR' keywords and grab the surrounding
    block.
    """
    lines = stdout.splitlines()
    # Find the start of any 'BAND' table
    band_idx = None
    for i, line in enumerate(lines):
        if "BAND" in line and ("avg_5d" in line or "win" in line.lower()):
            band_idx = i
            break
    if band_idx is None:
        # Fallback: return first 25 non-empty lines
        out = [ln for ln in lines if ln.strip()][:max_lines]
        return "\n".join(out)
    # Grab from header + max_lines after
    end = min(band_idx + max_lines, len(lines))
    return "\n".join(lines[band_idx - 1 : end])


# ── #513 — DECISION-FIRST digest ──────────────────────────────────────────────────────────────
# Operator 2026-08-01, reading the 8/01 sweep: *"it contains so much info, not all formatted well,
# and I have no idea what to do with it. with so much text, it becomes overwhelming, drown with
# data, so only option is paste it here."*
#
# The defect was RENDERING, not content: 13 scripts each pasted a raw table, and the two items that
# actually needed him were buried mid-message (4 M&A-suppressed movers incl. CLRO +358%, and 2 judge
# demotions that then ran). Every script still runs and still writes its audit row — nothing stops
# being measured. Full tables move to `/audit <topic>`.
#
# Classification is MARKER-BASED on the scripts' own output, deliberately: the scripts already
# announce their verdicts, so re-deriving them here would be a second source of truth that drifts.
# Unrecognised output degrades to "review" rather than being silently called green — a digest that
# reports "all clear" because it failed to parse is the failure mode this rewrite exists to remove.
#
# #691 (2026-10-03): the markers below are each registered script's OWN verdict phrases — one
# group per script, in the roster's order. They were written for the 5 scripts that already
# announced a verdict; seven others (#50 #53 #54 #77 #78 #88 #94) printed a verdict nobody taught
# this list to read — or none at all — and landed in "review" every month: *"Any action from
# this?"* (operator 2026-10-01). Every phrase is a literal that its script prints, in the branch
# named beside it. `tests/test_691_monthly_sweep_cleanup.py` runs each script's real formatting,
# branch by branch, and fails if any branch lands in "review" — so a reworded verdict goes RED
# here instead of silently asking him to open a report again.
#
# ⚠ MATCHING IS CASE-SENSITIVE SUBSTRING over the script's WHOLE stdout (not the 25-line summary —
# #88's and #94's verdicts sit after 40+ lines of tables and never reached the classifier). A marker
# must therefore not occur in a script's always-printed boilerplate (Caveats / Cross-references).
_NEEDS_YOU = [
    # M&A accuracy review (#284/#285). The "HARD-gate" banner is printed on EVERY run, so this
    # check always lands here — deliberately: the HARD-gate filter list is his to judge, and an
    # empty month ("(none)") is indistinguishable from a broken audit feed (the absence trap).
    ("MATERIAL-MISS CANDIDATE", "suppressed names that then ran — verify false positive"),
    ("For OPERATOR labeling",   "label the judge's calls right/wrong"),
    ("HARD-gate",               "filter list needs your judgement (agent may not classify)"),
    # #50 revenue bands — its own decision matrix (N>=10 and the $0-$5M band stopped paying).
    ("no longer positive-edge", "the $0-$5M revenue band stopped paying — re-open the $5M threshold question"),
    # #88 M&A Path B — enough polygon_news fires to need a manual true/false-positive scoring.
    ("OPERATOR ACTION REQUIRED", "score the sampled M&A fires true/false positive"),
    # #78 decliner bounce — cleared N>=30, WR>=55%, avg>=+5%.
    ("PROMOTE to methodology review", "decliner-bounce signal cleared its bar — your call"),
    # #94 flag-break — N>=10 with a clear verdict either way.
    ("PROMOTE to Phase 2",      "flag-break signal cleared its bar — your call"),
    ("SIGNAL WEAK at N>=10",    "flag-break signal is weak — revise the detector or drop it"),
    # #122 ORB wick outlier — N>=10 entries: enough to design the filter.
    ("Cohort sufficient to design", "enough wick-outlier entries to design a filter — your call"),
    # #197 cap+1 shadow — settled sample reached.
    ("READY for sign-off review", "cap+1 shadow reached its sample — sign-off review"),
    # News source quality — a source's coverage/attribution moved >= 40pp.
    ("DRIFT detected",          "a news source's quality shifted — check the source vs the cohort"),
]
_WAITING = [
    ("INSUFFICIENT for ship", "accruing"),                       # #122 N<10
    ("ACCRUING",              "accruing"),                       # #197, #50, #53, #77
    ("< 10.",                 "accruing"),
    ("data-gated",            "accruing"),
    ("KEEP OBSERVING",        "accruing — under 30 settled"),    # #78 N<30
    ("MARGINAL",              "marginal — keep observing"),      # #78 / #94 between the bars
    ("CONTINUE OBSERVING",    "accruing — under 10 settled"),    # #94 N<10
    ("No settled outcomes yet",  "accruing — nothing settled yet"),        # #78
    ("No settled 10d window data yet", "accruing — nothing settled yet"),  # #94
    ("Check again next month", "nothing to evaluate yet"),       # #88 no events / no polygon fires
    # (the script wraps this sentence mid-phrase: "N too small for drift\n  detection" — a marker
    # may not span the break, so it stops at the end of the first line)
    ("N too small for drift", "accruing — too few fires"),                  # #88 <5 fires
]
_CONCLUDED = [
    ("STRUCTURAL NO-GO", "no-go — structural, not tuning"),     # #92
    ("NO-SHIP",          "no-ship, its own rule decided"),      # #50 positive-edge arm
    ("No drift events",  "clean"),                              # news source quality
    ("VERDICT: GO",      "go-supportive"),
    ("CLOSE the investigation", "signal was noise — investigation closed"),   # #78 WR<50%
    # #53 / #77: table-only monitors the operator already ruled on — see their verdict lines.
    ("VERDICT: INFORMATIONAL", "table only — the standing ruling is unchanged"),
]


def _classify(stdout: str) -> "tuple[str, str]":
    """(bucket, one-line note). Buckets: 'you' | 'waiting' | 'done' | 'review'."""
    if not stdout.strip():
        return "review", "no output"
    for marker, note in _NEEDS_YOU:
        if marker in stdout:
            return "you", note
    for marker, note in _CONCLUDED:
        if marker in stdout:
            return "done", note
    for marker, note in _WAITING:
        if marker in stdout:
            return "waiting", note
    return "review", "output not auto-classified — open /audit"


# ── #691 — `/audit <check>`: every check's last output is stored, and reachable from Telegram ───
# Until #691 the digest said "Full tables: /audit <topic>" and printed `/audit <module tail>` under
# each call — but nothing stored a check's output (the sweep kept a 25-line summary in memory,
# Telegrammed a digest, and discarded it) and `system_audit.run_topic_audit` only knew its own
# metric topics, so EVERY pointer answered "Unknown audit topic" (operator 2026-10-01).
#
# The store is one `mi_audit_log` row per check per run (`backward_check_output`): summary =
# "<topic> | exit=<code> | <bucket>", detail = the script's stdout (plain text, so a long table
# survives the 32k detail budget as a clean head-cut, never as unparseable JSON). It is written by
# `run_quarterly_sweep`, so a hand-run `python -m agents.market_intelligence.quarterly_review` (which
# does not Telegram) stores too. `/audit <check>` only READS it — it never re-runs a script.
#
# Named `*_output`, NOT `*_failed` / `*_error`: the nightly silent-error sweep and `show errors`
# match on those suffixes, and a stored table is not an incident.
SWEEP_OUTPUT_EVENT = "backward_check_output"
_STORE_STDOUT_CAP = 24_000          # chars; mi_audit_log's detail budget is 32,000
_SEP = " | "                          # summary field separator (the reader splits on it)


def check_topic(module: str) -> str:
    """The `/audit` topic for a registered check = its module tail, lower-cased."""
    return module.rsplit(".", 1)[-1].lower()


def sweep_topics() -> "dict[str, tuple[str, str]]":
    """{topic: (label, module)} DERIVED from the roster, so a new registered script is reachable
    from `/audit` the moment it is registered — there is no second list to forget."""
    return {check_topic(e[1]): (e[0], e[1]) for e in QUARTERLY_BACKWARD_CHECK_SCRIPTS}


def _classify_input(r: dict) -> str:
    """What the classifier reads for one result: the script's FULL stdout when the sweep kept it
    (#88's and #94's verdicts sit after 40+ lines and never reached the 25-line summary), else the
    summary (results built by hand in tests carry only that)."""
    return r.get("stdout_full") or r.get("stdout_summary") or ""


async def store_sweep_outputs(results: list) -> int:
    """Write one `backward_check_output` audit row per check. Never raises (a failed audit write
    must not cost the operator the digest). Returns the number of rows attempted."""
    n = 0
    try:
        from agents.market_intelligence.db import log_audit_event
        for r in results:
            text = _classify_input(r) or "(no output)"
            if len(text) > _STORE_STDOUT_CAP:
                text = (text[:_STORE_STDOUT_CAP]
                        + f"\n… [truncated: {len(text) - _STORE_STDOUT_CAP} more characters]")
            code = r.get("exit_code")
            if code != 0:
                # A broken run is stored too: `/audit x` after a failure must show THIS month's
                # failure, not last month's table.
                bucket = "failed"
                text += f"\n--- stderr (tail) ---\n{r.get('stderr_tail') or '(none)'}"
            else:
                bucket = _classify(_classify_input(r))[0]
            await log_audit_event(
                SWEEP_OUTPUT_EVENT,
                _SEP.join((check_topic(r["module"]), f"exit={code}", bucket)),
                text,
            )
            n += 1
    except Exception as e:  # noqa: BLE001 — storage is best-effort; the digest still goes out
        logger.warning(f"Sweep output storage failed after {n} row(s): {e}")
    return n


async def fetch_stored_check(topic: str) -> "dict | None":
    """The newest stored row for one check, or None. One read on the event_type index; never
    runs a script. SQL is inline on purpose: a db.py helper would put db.py (loaded by
    apollo-execution) in the change and force a second, execution-service deploy for a read that
    only the market agent makes."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire(timeout=5.0) as conn:
        row = await conn.fetchrow(
            "SELECT created_at, summary, detail FROM mi_audit_log "
            "WHERE event_type = $1 AND split_part(summary, $2, 1) = $3 "
            "ORDER BY created_at DESC LIMIT 1",
            SWEEP_OUTPUT_EVENT, _SEP, topic, timeout=5.0)
    return dict(row) if row else None


def next_sweep_date(now_et: datetime) -> str:
    """ISO date of the next monthly sweep: the 1st of a month at 18:00 ET
    (scheduler.py `monthly_backward_check_sweep`)."""
    if now_et.day == 1 and now_et.hour < 18:
        return now_et.date().isoformat()
    year, month = (now_et.year + 1, 1) if now_et.month == 12 else (now_et.year, now_et.month + 1)
    return f"{year:04d}-{month:02d}-01"


def render_stored_check(topic: str, row: "dict | None", *, now_et: "datetime | None" = None) -> str:
    """Telegram text for `/audit <check>`: the stored table in a code block (monospace, so columns
    line up and the underscores in `ret_5d` survive), or an honest 'not stored yet'."""
    label, module = sweep_topics()[topic]
    if row is None:
        now = now_et or datetime.now(ZoneInfo("America/New_York"))
        return (f"No stored run of {label} yet. The monthly sweep (1st of the month, 18:00 ET) "
                f"stores every check's output; the first run after this shipped is "
                f"{next_sweep_date(now)}. To see it sooner, run `python -m {module}` on the box.")
    fields = (row.get("summary") or "").split(_SEP)
    code = fields[1].removeprefix("exit=") if len(fields) > 1 else "?"
    bucket = fields[2] if len(fields) > 2 else "?"
    when = row["created_at"].astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M PT")
    state = "FAILED TO RUN" if bucket == "failed" else f"filed as {bucket}"
    # A fence inside the table (the news check prints its own) would close ours early.
    body = (row.get("detail") or "(empty)").replace("```", "'''")
    return f"📋 {label} — last sweep {when} (exit {code}, {state})\n```\n{body}\n```"


async def render_sweep_topic(topic: str) -> str:
    """`/audit <check>` body for a registered check."""
    return render_stored_check(topic, await fetch_stored_check(topic))


def _money_line(results: list) -> "str | None":
    """The one number worth surfacing, lifted from whichever script printed it."""
    for r in results:
        for ln in (r.get("stdout_summary") or "").splitlines():
            if "total P&L" in ln or "Realized (alerts that became trades)" in ln:
                return ln.strip().lstrip("💵").strip()
    return None


def _render_digest(results: list, started_at, elapsed: float) -> str:
    """Decisions → money → one line per check. Never a raw table."""
    you, waiting, done, review, failed = [], [], [], [], []
    for r in results:
        if r["exit_code"] != 0:
            failed.append(r)
            continue
        bucket, note = _classify(_classify_input(r))
        {"you": you, "waiting": waiting, "done": done, "review": review}[bucket].append((r, note))

    L = ["📊 *Monthly backward-check sweep*",
         f"_{started_at.strftime('%Y-%m-%d')} · {len(results)} checks · {elapsed:.0f}s_", ""]

    if you:
        L.append("*⚖️ NEEDS YOUR CALL*")
        for r, note in you:
            L.append(f"• {r['label']} — {note}")
            L.append(f"    `/audit {check_topic(r['module'])}`")
        L.append("")
    else:
        L.append("*⚖️ NEEDS YOUR CALL* — none")
        L.append("")

    money = _money_line(results)
    if money:
        L += [f"*💵 {money}*", ""]

    if failed:
        L.append("*🔴 FAILED TO RUN*")
        for r in failed:
            L.append(f"• {r['label']} — {(r['stderr_tail'] or '')[:80]}")
            L.append(f"    `/audit {check_topic(r['module'])}`")
        L.append("")

    L.append("*Everything else*")
    for r, note in done:
        L.append(f"✅ {r['label']} — {note}")
    for r, note in waiting:
        L.append(f"⏳ {r['label']} — {note}")
    for r, note in review:
        # "open /audit" is only an instruction if the pointer is on the line (#691).
        L.append(f"👀 {r['label']} — {note}  `/audit {check_topic(r['module'])}`")
    # No `/audit <placeholder>` here: every `/audit X` this digest prints is a real, working topic
    # (tests/test_691_monthly_sweep_cleanup.py sends each through the real handler).
    L += ["", "_Full table of any check: `/audit` plus its name, printed under each call above — a "
              "wrong name lists every valid one. Each check's last output is kept for it._"]
    return "\n".join(L)


async def run_quarterly_sweep() -> dict:
    """Execute every registered backward-check script. Returns a dict
    with per-script outcome + an aggregated message ready for Telegram.

    Each script runs in a subprocess so a single failure doesn't abort
    the whole sweep. Output captured + truncated.
    """
    started_at = datetime.now(timezone.utc)
    results: list[dict] = []

    for entry in QUARTERLY_BACKWARD_CHECK_SCRIPTS:
        # Tuple shape: (label, module, extra_args). Pre-2026-05-21 entries
        # were 2-tuples; back-compat to 3rd element default to empty list.
        if len(entry) == 3:
            label, module, extra_args = entry
        else:
            label, module = entry
            extra_args = []
        logger.info(f"Quarterly sweep: running {module} {extra_args} ({label})")
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["python", "-m", module, *extra_args],
                capture_output=True,
                text=True,
                timeout=600,  # 10 min per script
            )
            results.append({
                "label": label,
                "module": module,
                "exit_code": proc.returncode,
                "stdout_summary": _extract_summary_section(proc.stdout),
                # The WHOLE stdout: classification reads it (a verdict can sit past the 25-line
                # summary) and `store_sweep_outputs` keeps it for `/audit <check>` (#691).
                "stdout_full": proc.stdout or "",
                "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            })
        except Exception as e:
            results.append({
                "label": label,
                "module": module,
                "exit_code": -1,
                "stdout_summary": "",
                "stdout_full": "",
                "stderr_tail": f"FAILED: {type(e).__name__}: {str(e)[:300]}",
            })

    # Keep every check's output for `/audit <check>` (#691). Best-effort: never costs the digest.
    await store_sweep_outputs(results)

    # Aggregate into ONE decision-first digest (#513) — see _render_digest.
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    return {
        "started_at": started_at.isoformat(),
        "elapsed_sec": elapsed,
        "results": results,
        "digest_message": _render_digest(results, started_at, elapsed),
    }


async def quarterly_backward_check_sweep_job():
    """Scheduler entry point — quarterly cron. Runs the sweep + sends
    digest. Wired in scheduler.py at quarter boundaries (1st of Feb,
    May, Aug, Nov, 8:00 AM ET).
    """
    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.db import log_audit_event

    logger.info("Quarterly backward-check sweep starting...")
    try:
        result = await run_quarterly_sweep()
        await log_audit_event(
            "quarterly_backward_check_sweep",
            f"Completed in {result['elapsed_sec']:.0f}s · "
            f"{len(result['results'])} scripts",
        )
        from shared.telegram_format import md_to_html
        # #647: HTML layer — the digest carries script/module identifiers (2026-09-01 fell back).
        await send_telegram_message(md_to_html(result["digest_message"]), parse_mode="HTML")
        logger.info("Quarterly sweep digest sent")
    except Exception as e:
        logger.exception(f"Quarterly sweep failed: {e}")
        from core.notifications import notify_job_failure
        await notify_job_failure("quarterly_backward_check_sweep", str(e))

    # #337 — monthly judge-judgment review, folded into this job (reuse, not a new job).
    # NB: despite the "quarterly_" name + docstring, this job is registered on a MONTHLY cron
    # (scheduler.py: CronTrigger(day=1) id="monthly_backward_check_sweep", converted 2026-05-22).
    # The judge review intentionally rides that MONTHLY cadence — do NOT "fix" the name to quarterly
    # without also re-homing this review, or it silently goes quarterly.
    # INDEPENDENTLY guarded: a review failure must never break the backward-check sweep above.
    try:
        from agents.market_intelligence.judge_review import run as _run_judge_review
        await _run_judge_review(days=30, send=True)
        logger.info("Monthly judge review sent")
    except Exception as e:
        logger.exception(f"Monthly judge review failed (non-critical): {e}")


if __name__ == "__main__":
    # Direct invocation: run + print digest. Doesn't Telegram.
    result = asyncio.run(run_quarterly_sweep())
    print(result["digest_message"])
