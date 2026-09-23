"""Every operator-facing pending review must carry a predicate that CAN be evaluated.

WHY (2026-09-09). `scripts/operator_asks.py` shipped 09-08 printing "NOT an ask until its own
predicate says READY" for every pending review — without ever running a predicate. When it was
made to actually run them, FOUR reviews had been ready (one since 2026-07-29) and one,
`gap_near_miss_tradeable_miss_rate_617`, had been UNRUNNABLE since it was written: its SQL
referenced a column `reached_4r` that does not exist on `mi_gap_near_miss_replays`.

A gate that cannot fire is indistinguishable from a gate that says "not yet" — that is the
defect class of the week, and it had lodged inside the fix for it. CI has no database, so this
test cannot execute the SQL. It pins what IS decidable offline: the predicate exists, is a
string, and is not obviously inert. The execution half is covered at OPEN, where
`operator_asks.py` now runs each predicate and reports UNKNOWN (never "not ready") on failure.
"""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent


def _operator_facing_pending():
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    return [r for r in d.get("reviews", [])
            if r.get("status") == "pending"
            and "operator" in str(r.get("action_when_ready", "")).lower()]


def test_every_pending_operator_review_can_become_ready_somehow():
    """Data-gated reviews need a predicate; `kind: cadence` reviews are DATE-gated by design and
    correctly carry none — they need an earliest_review_date instead. What is forbidden is a
    review with NEITHER, which can never become ready and will sit pending forever."""
    bad = []
    for r in _operator_facing_pending():
        sql = r.get("predicate_sql")
        has_sql = isinstance(sql, str) and bool(sql.strip())
        is_dated_cadence = (str(r.get("kind", "")).lower() == "cadence"
                            and r.get("earliest_review_date") is not None)
        if not has_sql and not is_dated_cadence:
            bad.append(f"{r['review_id']}: no predicate_sql and no dated cadence — it can never "
                       f"become ready on its own, so it will sit pending forever")
    assert not bad, (
        "gated reviews that cannot be evaluated:\n  " + "\n  ".join(bad))


def test_predicates_are_scalar_shaped_and_have_a_threshold():
    """A predicate must SELECT something and pair with a numeric threshold, or the
    ready-vs-accruing comparison has nothing to compare."""
    bad = []
    for r in _operator_facing_pending():
        sql = r.get("predicate_sql")
        if not (isinstance(sql, str) and sql.strip()):
            continue                      # dated cadence review — covered by the test above
        if "select" not in sql.lower():
            bad.append(f"{r['review_id']}: predicate has no SELECT")
        if not isinstance(r.get("threshold"), (int, float)):
            bad.append(f"{r['review_id']}: threshold is {r.get('threshold')!r}, not a number")
    assert not bad, "unusable gated-review predicates:\n  " + "\n  ".join(bad)


def test_617_does_not_reference_the_column_that_never_existed():
    """The specific regression: `reached_4r` is not a column on mi_gap_near_miss_replays.
    Its rule is 'a name that reached >= 4R', which is `realized_r >= 4`."""
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    r = [x for x in d["reviews"] if x["review_id"] == "gap_near_miss_tradeable_miss_rate_617"]
    assert r, "the 617 review disappeared — if it was closed, delete this test with it"
    assert "reached_4r" not in r[0]["predicate_sql"], (
        "617's predicate is back to the phantom column; it errors on prod and the gate goes dark")


# ── #633 (2026-09-09): the eleven zero-since-eligible gates, and what was decidable offline ──
#
# Every dead gate found this week was dead for a DIFFERENT reason: a phantom column (617), an
# audit event no code emits (harvest, phase5), a proxy column that is written but can never be
# true for the table in question (failed_break), a writer job that is unregistered (anticipation
# x2), and a rolling window shorter than the interval between reads (entry_order — READY for two
# weeks, unread, then back to 0). The tests below pin the parts of those that a database-less CI
# can decide. The execution half stays with operator_asks.py at OPEN.

import re

_AGENTS = REPO / "agents"


def _pending_with_sql():
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    return [r for r in d.get("reviews", [])
            if r.get("status") == "pending"
            and isinstance(r.get("predicate_sql"), str) and r["predicate_sql"].strip()]


def _registry(rid):
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    return next(r for r in d["reviews"] if r.get("review_id") == rid)


def _agents_source():
    return "\n".join(p.read_text(errors="ignore") for p in _AGENTS.rglob("*.py"))


# Audit event names built at runtime from a prefix — a literal check cannot see them. Each entry
# names the code that builds the name, so the allowance is checkable, not a blanket pass.
_DYNAMIC_EVENT_PREFIXES = {
    "api_failure_": "llm_health.py: event_type = f'api_failure_{provider}'",
}

# Pending reviews KNOWN to key on an event nothing emits yet — a visible backlog, not a clean
# bill. Each carries the dated reason and the owner. Do NOT add to this to silence the test;
# repoint the predicate or close the review instead (that is what #633 did for the others).
_KNOWN_WRITERLESS_EVENT_REVIEWS = {
    "phase6_meta_rubric_gating": "2026-09-09 #633: 'meta_rubric_score_advisory' — what the "
        "composite emits once #335 flips it is #335's decision; predicate moves in that commit.",
    "catalyst_rubric_quarterly": "2026-09-09 #633: same event as phase6; earliest 2026-12-29.",
    "trade_stream_stop_placement_without_orders_row": "2026-09-09 #633: "
        "'stop_placement_failed_after_partial' has no emitter in agents/ — flagged in the #633 "
        "report for the caller to route; outside the eleven ruled that day.",
}


def _sql_sans_comments(sql: str) -> str:
    """The predicates carry `-- why` comments that legitimately NAME the thing they refuse to
    filter on; only the executable text is checked."""
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in sql.splitlines())


def _event_names_in(sql: str) -> set[str]:
    names = set(re.findall(r"event_type\s*=\s*'([A-Za-z0-9_]+)'", sql))
    for grp in re.findall(r"event_type\s+IN\s*\(([^)]*)\)", sql, re.I):
        names |= set(re.findall(r"'([A-Za-z0-9_]+)'", grp))
    return names


def test_every_audit_event_a_pending_predicate_counts_has_an_emitter():
    """A predicate that counts `event_type = 'x'` is WHERE FALSE unless some code emits 'x'.
    phase5_meta_rubric_calibration counted two names nothing has ever written (0 rows all-time,
    flagged 08-15, still pending 09-09); harvest_rule_effectiveness keyed on a third. Decidable
    offline: the literal must appear in agents/, or match a declared dynamic prefix."""
    code = _agents_source()
    bad, stale_exempt = [], []
    for r in _pending_with_sql():
        rid = r["review_id"]
        missing = [n for n in sorted(_event_names_in(r["predicate_sql"]))
                   if f'"{n}"' not in code and f"'{n}'" not in code
                   and not any(n.startswith(pfx) for pfx in _DYNAMIC_EVENT_PREFIXES)]
        if rid in _KNOWN_WRITERLESS_EVENT_REVIEWS:
            if not missing:
                stale_exempt.append(rid)     # the exemption outlived the defect — drop it
            continue
        if missing:
            bad.append(f"{rid}: no code in agents/ emits {missing}")
    assert not bad, (
        "pending reviews counting an audit event nothing emits (the gate can never fire):\n  "
        + "\n  ".join(bad))
    assert not stale_exempt, (
        f"exemption no longer needed — remove from _KNOWN_WRITERLESS_EVENT_REVIEWS: {stale_exempt}")


@pytest.mark.parametrize("rid", ["intraday_undercut_rally_signal_n10",
                                 "intraday_failed_break_signal_n10"])
def test_intraday_signal_reviews_do_not_gate_on_the_parent_flags_invalidation(rid):
    """`parent_invalidated_eod` is written nightly, but it is the parent FLAG's close-based
    verdict (close below SMA20 / the base's lowest close), not the detector's own. Prod
    2026-09-09: TRUE on 6 of 6 U&Rs ever (every reclaim that HELD was excluded) and on 0 of 167
    breaks ever (a same-day break cannot close under the base's lowest close). Either way the
    review counted nothing. Each now keys on its own event: the U&R's stop held into the close;
    the break closed back under base_high."""
    sql = _sql_sans_comments(_registry(rid)["predicate_sql"])
    assert "parent_invalidated_eod" not in sql, (
        f"{rid} is back on the parent flag's invalidation — a proxy proven empty by construction")
    assert "mi_daily_closes" in sql and "OFFSET 9" in sql, (
        f"{rid} must read the day-0 close and require a settled 10-session forward close")


def test_undercut_review_keys_on_the_undercut_low_stop():
    sql = _registry("intraday_undercut_rally_signal_n10")["predicate_sql"]
    assert "d0.close > u.undercut_low" in sql, (
        "the U&R's own invalidation is its stop (docs/setups/undercut_rally.md: undercut_low)")


def test_failed_break_review_counts_a_close_back_under_base_high():
    sql = _registry("intraday_failed_break_signal_n10")["predicate_sql"]
    assert "d0.close < b.base_high" in sql, (
        "the review's stated mechanic is 'closes back BELOW base_high before EOD'")
    assert "INTERVAL '90 days'" not in sql, "cumulative — a window that forgets hid entry_order"


def test_entry_order_rejections_review_does_not_forget_what_it_counted():
    """Three rejections (07-22, 08-06, 08-07) made the old rolling 30-day window read 3 >= 3
    from 08-07 to 08-21 — READY, unread — then roll back to 0 by 09-09. A tripwire whose memory
    is shorter than the interval between reads cannot be trusted to hold a reading."""
    sql = _registry("entry_order_rejections_systematic")["predicate_sql"]
    assert "NOW() - INTERVAL" not in sql and "INTERVAL '30 days'" not in sql, (
        "rolling window is back — it fired and forgot once already")
    assert "created_at >= DATE '2026-07-15'" in sql, "cumulative since the #475 telemetry shipped"


def test_no_pending_review_reads_the_lifecycle_table_while_its_writer_job_is_unregistered():
    """mi_anticipation_lifecycle is written ONLY by _anticipation_readiness_job / _anticipation_3b_job.
    Both were un-registered 2026-06-16 (ADR-0013; scheduler.py, the commented add_job pair) and the
    table has been frozen since. A pending review gated on it is a gate whose writer does not run.
    If #297 re-registers the pair, this test says so (the registration is live) and a fresh gate
    may be filed; until then any such review must be closed, not pending."""
    sched = (REPO / "agents/market_intelligence/scheduler.py").read_text()
    live_registration = re.search(
        r"^\s*_scheduler\.add_job\(\s*\n\s*audit_wrap\(_anticipation_3b_job", sched, re.M)
    if live_registration:
        pytest.skip("the 3b job is registered again — the lifecycle table has a writer")
    offenders = [r["review_id"] for r in _pending_with_sql()
                 if "mi_anticipation_lifecycle" in r["predicate_sql"]]
    assert not offenders, (
        f"pending reviews gated on a table whose writer job is unregistered: {offenders}")


_ISO_VERDICT = re.compile(r"^\d{4}-\d{2}-\d{2} WAITING — .{20,}")


def test_zero_verdicts_are_dated_and_only_ever_say_waiting():
    """`zero_verdict:` is the ONLY verdict that leaves a gate pending at zero. IMPOSSIBLE gets
    fixed and OBSOLETE gets closed — neither is written here. It must carry the date it was
    ruled, so a stale ruling can be seen to be stale."""
    d = yaml.safe_load((REPO / "data_gated_reviews.yaml").read_text())
    bad = []
    for r in d.get("reviews", []):
        v = r.get("zero_verdict")
        if v is None:
            continue
        if r.get("status") != "pending":
            bad.append(f"{r['review_id']}: zero_verdict on a non-pending review is dead text")
        if not _ISO_VERDICT.match(str(v)):
            bad.append(f"{r['review_id']}: zero_verdict must read '<YYYY-MM-DD> WAITING — <why>', "
                       f"got {str(v)[:60]!r}")
    assert not bad, "\n  ".join(bad)


def test_operator_asks_prints_the_ruling_instead_of_re_asking_for_it():
    import importlib.util
    spec = importlib.util.spec_from_file_location("operator_asks", REPO / "scripts/operator_asks.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    ruled = mod._zero_line("x", {"zero_verdict": "2026-09-09 WAITING — proof here"}, 0, 1, "2026-09-01", 8)
    raw = mod._zero_line("y", {}, 0, 1, "2026-09-01", 8)
    assert "RULED 2026-09-09 WAITING — proof here" in ruled and "⚠" not in ruled
    assert "nobody has ruled why" in raw and "zero_verdict" in raw and "⚠" in raw
