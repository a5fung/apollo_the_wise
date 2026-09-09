"""#631 (2026-09-09) — ONE exit-counterfactual recorder with N arms, and ONE read.

Operator, verbatim: *"aren't we logging all entry and exit rules together and reviewing them
together. Multiple entries and exits. Why are you doing this one off analysis"* … *"stop one
off, consolidate."* Said after a one-off offline replay had to be retracted the same day:
its 28-trade baseline had 27 trades under the exit rule replaced on 2026-09-06.

What this file pins, so the consolidation cannot silently unwind:
  1. THE ARM SET — the twelve arms of `live_fill_counterfactuals.ARMS`, their kinds and
     trail rules, and the ONE deliberate omission (the giveback lock, ruled out 2026-08-11).
  2. THE COVERAGE CLAIM — each folded review is status=done with an outcome naming the ONE
     read AND the arm that answers it; each kept review is still pending and says why it is
     a different instrument; no review id was deleted.
  3. THE ERA PIN — the ONE read's predicate, and the two kept exit_tune predicates, carry
     the LATEST exit-switch date from rule_eras.py. The retraction happened because a count
     predicate outlived a rule flip; a prose "bump in the same commit" comment failed on
     09-06. This is the mechanical version: the next flip goes red here.
  4. THE OLD TABLES — pivot/giveback jobs unregistered, tables + rows kept (never dropped,
     never deleted), exit_path_shadow still running (it is a path record, not an arm table).
  5. THE RUNNING READ — the nightly digest reads the ONE table, every arm, current era only.
  6. THE WALK — the trail arms exit where their trail says, on the same engine; a missing
     profile is a recorded abstain, never a silent fall-back to the SMA trail.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db
from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence import rule_eras
from agents.market_intelligence import sell_discipline as sd

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent
_REGISTRY = _REPO / "data_gated_reviews.yaml"
_SSOT = _REPO / "docs" / "setups" / "exit_discipline.md"
_ROUTER = _REPO / "docs" / "SSoT.md"
_SCHEDULER_SRC = (_REPO / "agents" / "market_intelligence" / "scheduler.py").read_text()
_DB_SRC = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()

ONE_READ = "live_fill_counterfactuals_first_read_482"

# review_id -> the arm(s) / column the ONE read answers it with (must appear in its outcome)
FOLDED: dict[str, tuple[str, ...]] = {
    "pivot_stop_shadow_review": ("trail_pivot_swing", "trail_character_ma"),
    "exit_path_shadow_first_read": ("stop_orb_low", "stop_orb_3r"),
    "stop_2r_running_comparison": ("stop_orb_low",),
    "harvest_rule_effectiveness": ("harvest_legacy_2r",),
    "exit_regime_interaction_review": ("regime",),
    "regime_conditional_exit_grid_parked": ("regime",),
}
CLOSED_BY_RULING = "giveback_shadow_review"
KEPT: tuple[str, ...] = (
    "exit_tune_cohort_review", "exit_tune_bull_regime_read",      # the wide-grid offline forensic
    "runner_rule_sweep_recut",                                     # a backtest population (Run-U)
    "bracket_geometry_variants_parked",                            # ENTRY geometry
    "delayed_entry_adr_stop_variant_616",                          # a different signal's recorder
    "delayed_entry_adr_stop_variant_025_545",
)


def _registry() -> dict:
    return {r["review_id"]: r for r in yaml.safe_load(_REGISTRY.read_text())["reviews"]}


def _latest_exit_switch() -> date:
    """The newest dated exit/geometry switch in rule_eras — every module-level `*_DATE`
    constant there is one (ADMISSION_SWITCHES is a tuple, not a date)."""
    dates = [v for k, v in vars(rule_eras).items() if k.endswith("_DATE") and isinstance(v, date)]
    assert dates
    return max(dates)


# ── 1. the arm set ─────────────────────────────────────────────────────────────────────


def test_the_twelve_arms_and_their_one_omission():
    assert lfc.ARM_NAMES == (
        "live_actual", "live_replay",
        "stop_orb_low", "stop_adr_050", "stop_adr_075",
        "harvest_no_breakeven", "harvest_trail_only", "harvest_t3", "harvest_legacy_2r",
        "stop_orb_3r", "trail_pivot_swing", "trail_character_ma",
    )
    by = {a[0]: a for a in lfc.ARMS}
    assert all(len(a) == 6 for a in lfc.ARMS)
    assert by["trail_pivot_swing"][1:5] == ("trail", "live", "live_ladder", "pivot_swing")
    assert by["trail_character_ma"][1:5] == ("trail", "live", "live_ladder", "character_ma")
    assert by["stop_orb_3r"][1:5] == ("stop", "orb_3r", "live_ladder", "sma")
    # the trail arms vary ONE thing against the live stop + live ladder, so they follow the
    # live partial/breakeven levels like the stop arms do (#545 follows_live_rule)
    assert by["trail_pivot_swing"][5] is True and by["trail_character_ma"][5] is True
    assert all(a[4] == "sma" for a in lfc.ARMS if a[0] not in ("trail_pivot_swing", "trail_character_ma"))
    assert set(a[4] for a in lfc.ARMS) <= set(lfc.TRAIL_RULES)
    assert set(a[2] for a in lfc.ARMS) <= set(lfc.STOP_RULES)
    # the giveback lock is NOT an arm — operator 2026-08-11 — and the recorder says so
    assert not any("giveback" in n for n in lfc.ARM_NAMES)
    assert "giveback_peak_lock" in lfc.RULED_OUT_ARMS
    assert "2026-08-11" in lfc.RULED_OUT_ARMS["giveback_peak_lock"]
    assert "we let winners run" in _SSOT.read_text()       # the ruling is on the SSoT


def test_trail_rule_is_a_column_on_every_row():
    assert "trail_rule" in db.LIVE_FILL_CF_COLS
    block = re.search(r"CREATE TABLE IF NOT EXISTS mi_live_fill_counterfactuals \((.*?)\n\s*\);",
                      _DB_SRC, re.S).group(1)
    assert re.search(r"^\s*trail_rule\s+TEXT", block, re.M)
    assert "ADD COLUMN IF NOT EXISTS trail_rule TEXT" in _DB_SRC     # additive on a live table
    assert "trail_rule" in db.LIVE_FILL_CF_INSERT_SQL


# ── 2. the coverage claim ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("review_id", sorted(FOLDED))
def test_each_folded_review_points_at_the_one_read_and_its_arm(review_id):
    e = _registry()[review_id]
    assert e["status"] == "done", f"{review_id} must be closed with a pointer, not left open"
    assert e["closed_on"] == date(2026, 9, 9)
    assert ONE_READ in e["outcome"]
    assert "FOLDED INTO" in e["outcome"]
    for arm in FOLDED[review_id]:
        assert arm in e["outcome"], f"{review_id}'s outcome does not name the answering arm {arm}"
    # the question and predicate stay for the audit trail — a fold is not a delete
    assert e.get("question") and (e.get("predicate_sql") or e.get("evidence_predicate"))


def test_giveback_review_is_closed_by_the_ruling_not_folded():
    e = _registry()[CLOSED_BY_RULING]
    assert e["status"] == "done" and e["closed_on"] == date(2026, 9, 9)
    assert "2026-08-11" in e["outcome"] and "we let winners run" in e["outcome"]
    assert "FOLDED INTO" not in e["outcome"]
    assert "RULING" in e["outcome"]


@pytest.mark.parametrize("review_id", KEPT)
def test_each_kept_review_is_still_pending(review_id):
    e = _registry()[review_id]
    assert e["status"] == "pending", f"{review_id} is a different instrument or population — it stays"


def test_the_kept_forensic_names_the_one_read_as_primary_evidence():
    e = _registry()["exit_tune_cohort_review"]
    assert ONE_READ in e["notes"] and "different instrument" in e["notes"]


def test_no_review_id_was_deleted():
    reg = _registry()
    for rid in (*FOLDED, CLOSED_BY_RULING, *KEPT, ONE_READ):
        assert rid in reg, f"{rid} disappeared from the registry"


def test_the_one_read_lists_every_absorbed_review_in_its_cross_refs():
    e = _registry()[ONE_READ]
    refs = " ".join(str(x) for x in e["cross_refs"])
    for rid in (*FOLDED, CLOSED_BY_RULING):
        assert rid in refs, f"{rid} not cross-referenced from the ONE read"
    assert "exit_tune_cohort_review" in refs


# ── 3. the era pin — mechanical, because the prose version failed on 09-06 ────────────


def test_the_one_read_predicate_is_scoped_to_the_current_exit_era():
    e = _registry()[ONE_READ]
    sql = e["predicate_sql"]
    latest = _latest_exit_switch()
    assert latest == rule_eras.PARTIAL_8R_DATE == date(2026, 9, 6)   # the fact as of this commit
    assert f"alert_date >= DATE '{latest.isoformat()}'" in sql, (
        "the ONE read must count fills from the LATEST exit switch — move this literal in the "
        "same commit as the next exit-rule change")
    label = rule_eras.exit_era_label(latest, "magna53")
    assert f"exit_era = '{label}'" in sql
    assert label == rule_eras.exit_era_label(datetime.now(_ET).date(), "magna53")
    # never a raw count: the control PAIR gates it, live money, MAGNA53 only
    assert "arm IN ('live_actual', 'live_replay')" in sql and "HAVING COUNT(DISTINCT arm) = 2" in sql
    assert "account_mode = 'live'" in sql and "signal_type = 'magna53'" in sql
    assert e["threshold"] == 20 and e["status"] == "pending" and e["kind"] == "accrual"
    assert "mi_live_fill_counterfactuals.signal_type" in e["discriminates_on"]
    assert "mi_live_fill_counterfactuals.exit_era" in e["discriminates_on"]


@pytest.mark.parametrize("review_id", ("exit_tune_cohort_review", "exit_tune_bull_regime_read"))
def test_the_kept_exit_tune_predicates_track_the_latest_exit_switch(review_id):
    """Both carried `created_at >= DATE '2026-08-16'` three days after the 09-06 flip, with a
    comment demanding the bump. The comment is now this test."""
    sql = _registry()[review_id]["predicate_sql"]
    latest = _latest_exit_switch().isoformat()
    assert f"DATE '{latest}'" in sql, f"{review_id} still counts trades from a replaced exit era"
    older = [d for d in re.findall(r"DATE '(\d{4}-\d{2}-\d{2})'", sql) if d != latest]
    assert not older, f"{review_id} carries an older era literal: {older}"


# ── 4. the old tables: jobs off, rows kept, exit_path still running ───────────────────


def test_pivot_and_giveback_jobs_are_unregistered_and_their_tables_kept():
    from agents.market_intelligence import scheduler as sched
    for job in ("pivot_stop_shadow", "giveback_shadow"):
        assert job not in sched.INTELLIGENCE_OWNED_JOB_IDS and job not in sched.EXECUTION_OWNED_JOB_IDS
        assert not re.search(rf'id="{job}"', _SCHEDULER_SRC), f"{job} is still registered"
    # the ONE recorder and the path record keep running
    for job in ("live_fill_counterfactuals", "exit_path_shadow", "sell_discipline_recorder"):
        assert job in sched.INTELLIGENCE_OWNED_JOB_IDS
        assert re.search(rf'id="{job}"', _SCHEDULER_SRC), f"{job} lost its registration"
    # tables stay (read-only history), rows stay — never dropped, never deleted
    for table in ("mi_pivot_stop_shadow", "mi_giveback_shadow", "mi_exit_path_shadow"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in _DB_SRC
    for py in list((_REPO / "agents").rglob("*.py")) + list((_REPO / "scripts").glob("*.py")):
        src = py.read_text()
        for table in ("mi_pivot_stop_shadow", "mi_giveback_shadow", "mi_live_fill_counterfactuals"):
            assert not re.search(rf"(DROP TABLE|DELETE FROM|TRUNCATE)\s+(IF EXISTS\s+)?{table}\b", src), (
                f"{py.relative_to(_REPO)} destroys {table}")
    # the modules stay importable (their tests, and the read-only history, still resolve)
    import agents.market_intelligence.pivot_stop_shadow  # noqa: F401
    import agents.market_intelligence.giveback_shadow    # noqa: F401


# ── 4b. a later-added arm joins a fill at the fill's OWN live rule ────────────────────


@pytest.mark.asyncio
async def test_a_new_arm_backfilled_onto_an_older_fill_uses_that_fills_levels_not_todays(monkeypatch):
    """The defect caught in review before the first nightly run: the three #631 arms would
    have landed on the seven era-C fills at today's +8R / +3R beside live_actual /
    live_replay rows at +2R / none. With the fill's nine rows already written at 2R/none,
    the new arms must walk 2R/none too — whatever mi_strategies says today."""
    import test_live_fill_counterfactuals as T
    nine = tuple(a for a in lfc.ARM_NAMES
                 if a not in ("stop_orb_3r", "trail_pivot_swing", "trail_character_ma"))
    todays_rule = [{"signal_type": "magna53", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0}]
    _, inserts, _, _ = T._wire(monkeypatch, trade=T._trade_row(), written=nine, overrides=todays_rule)
    out = await lfc.run_live_fill_counterfactuals(T._TODAY, now_et=T._NOW)
    assert out["errors"] == 0 and {r["arm"] for r in inserts} == {
        "stop_orb_3r", "trail_pivot_swing", "trail_character_ma"}
    for r in inserts:
        assert r["target_r"] == 2.0 and r["breakeven_arm_r"] is None, r["arm"]
        assert r["target_price"] == pytest.approx(T.TARGET)          # the fill's own +2R, not +8R


@pytest.mark.asyncio
async def test_a_brand_new_fill_is_framed_by_todays_rule(monkeypatch):
    """No follows-live row yet -> today's mi_strategies levels, byte-identical to #545."""
    import test_live_fill_counterfactuals as T
    todays_rule = [{"signal_type": "magna53", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0}]
    _, inserts, _, _ = T._wire(monkeypatch, trade=T._trade_row(), overrides=todays_rule)
    await lfc.run_live_fill_counterfactuals(T._TODAY, now_et=T._NOW)
    by = {r["arm"]: r for r in inserts}
    assert by["live_replay"]["target_r"] == 8.0 and by["live_replay"]["breakeven_arm_r"] == 3.0
    assert by["trail_pivot_swing"]["target_r"] == 8.0 and by["stop_orb_3r"]["breakeven_arm_r"] == 3.0
    assert by["harvest_legacy_2r"]["target_r"] == 2.0                  # the fixed arms never move


# ── 5. the running read (the digest) ──────────────────────────────────────────────────


def test_the_digest_reads_the_one_table_every_arm_current_era_only():
    src = (_REPO / "agents" / "market_intelligence" / "sell_discipline.py").read_text()
    # no live SQL against the retired tables (the docstring may still name them as history)
    assert "FROM mi_pivot_stop_shadow" not in src and "FROM mi_giveback_shadow" not in src
    assert "FROM mi_live_fill_counterfactuals" in sd._EXIT_CF_RUNNING_READ_SQL
    assert "exit_era = $1" in sd._EXIT_CF_RUNNING_READ_SQL
    # every arm but the baseline has a plain-words label, in ARMS order
    assert tuple(sd._CF_ARM_LABELS) == tuple(a for a in lfc.ARM_NAMES if a != "live_actual")
    for label in sd._CF_ARM_LABELS.values():
        assert "_" not in label and not re.search(r"\bp[12]\b", label)
    # the recorder MODULE is not imported by the digest (only its table is read)
    assert not re.search(r"^\s*(from|import)\s+[\w.]*live_fill_counterfactuals\b", src, re.M)


def test_the_digest_renders_every_arm_with_the_changed_count_load_bearing():
    data = {"shadow": {"exit_cf": {"n": 3, "era": "era_d", "arms": [
        {"arm": "stop_orb_low", "n": 3, "unscoreable": 0, "delta_pct": -1.25, "changed": 2},
        {"arm": "trail_pivot_swing", "n": 3, "unscoreable": 0, "delta_pct": 0.0, "changed": 0},
        {"arm": "trail_character_ma", "n": 0, "unscoreable": 3, "delta_pct": None, "changed": 0},
    ]}}}
    data["shadow"]["exit_cf"]["arms"].insert(
        0, {"arm": "live_replay", "n": 3, "unscoreable": 0, "delta_pct": 0.4, "changed": 1})
    out = sd.format_sell_discipline_section(data)
    assert "WOULD A DIFFERENT EXIT HAVE KEPT MORE" in out
    assert "3 fills with a settled result" in out
    # the fidelity line counts DISAGREEMENT with the real result, never "changed vs itself"
    assert "our own rule replayed, as a check: +0.4% (off by over a quarter R on 1 of 3 fills)" in out
    assert "stop at the opening-range low: -1.2% (changed 2 of 3 fills)" in out
    assert "swing-stop rule: +0.0% (changed 0 of 3 fills)" in out
    assert "character-based rule: no history for 3 fills" in out
    assert "|" not in out and "n=" not in out


def test_the_digest_shows_nothing_until_one_fill_has_a_settled_result():
    assert sd.format_sell_discipline_section({"shadow": {"exit_cf": None}}) == ""
    assert sd.format_sell_discipline_section({"shadow": {"exit_cf": {"n": 0, "arms": []}}}) == ""


# ── 6. the walk: the trail arms on the same engine ────────────────────────────────────

ENTRY, STOP, FAR_TARGET = 10.0, 9.0, 40.0
FILL_DAY = date(2026, 9, 8)


def _sessions(spec):
    """(low, close) per session; each session OPENS at the prior close (no gaps — a gap
    below a resting stop fills at the open, which is the other branch, not this test's)."""
    d = FILL_DAY
    out = []
    prev = ENTRY
    for lo, cl in spec:
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append((d, {"o": prev, "h": max(cl, prev), "l": lo, "c": cl}))
        prev = cl
    return out


DAY0 = [{"m": datetime(2026, 9, 8, 9, 31, tzinfo=_ET), "o": 9.98, "h": 10.05, "l": 9.95, "c": 10.02},
        {"m": datetime(2026, 9, 8, 15, 59, tzinfo=_ET), "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0}]


def _walk(trail_mode, sessions, *, prior=(), horizon=8, **kw):
    return lfc.walk_arm(entry=ENTRY, stop=STOP, target=FAR_TARGET, day0_bars=DAY0, fill_idx=0,
                        sessions=sessions, prior_closes=list(prior), harvest="live_ladder",
                        fill_day=FILL_DAY, horizon=horizon, trail_mode=trail_mode, **kw)


def test_pivot_swing_arm_exits_at_the_confirmed_swing_low_where_the_sma_arm_holds():
    """lows [9.7, 9.6, 9.4, 9.5, 9.6, 9.8, 9.3]: the 9.4 low at index 2 is a fractal low
    (below both neighbours either side) CONFIRMED two sessions later (index 4). From then
    the pivot is the trail line; the raise-only resting-stop overlay every arm gets makes
    it the resting stop, so session 7's 9.3 low fills it at 9.4 — the same overlay a live
    pivot stop would have at the broker. The SMA arm, with no prior closes, has no trail
    line yet and is still open at the horizon."""
    sess = _sessions([(9.7, 9.9), (9.6, 9.8), (9.4, 9.7), (9.5, 9.9), (9.6, 10.2), (9.8, 10.5),
                      (9.3, 9.35), (9.4, 9.5)])
    stops = lfc.pivot_stops_for_sessions(sess)
    assert stops[:4] == [None] * 4 and stops[4] == 9.4 and stops[-1] == 9.4
    pivot = _walk("pivot_swing", sess, pivot_stops=stops)
    assert pivot["status"] == "settled" and pivot["final_reason"] == "stop_hit"
    assert pivot["exit_session"] == 7
    assert pivot["pnl_per_share"] == pytest.approx(9.4 - ENTRY)
    sma = _walk("sma", sess)
    assert sma["status"] == "horizon" and sma["pnl_per_share"] is None


def test_character_ma_arm_trails_the_stocks_own_ma_with_its_undercut():
    """home = SMA3, undercut 2%, prior closes [10, 10, 10]: after S1 (close 9.9) the line is
    (10 + 10 + 9.9) / 3 × 0.98 = 9.7673, which becomes the resting stop; S2's 9.5 low fills
    it there. The SMA10/20 arm has three closes of history — no line — and holds."""
    sess = _sessions([(9.85, 9.9), (9.5, 9.6), (9.7, 9.8)])
    profile = {"home_window": 3, "home_kind": "sma", "undercut_p80": 0.02}
    ch = _walk("character_ma", sess, prior=[10.0, 10.0, 10.0], character=profile)
    line = (10.0 + 10.0 + 9.9) / 3 * 0.98
    assert ch["status"] == "settled" and ch["final_reason"] == "stop_hit"
    assert ch["exit_session"] == 2
    assert ch["pnl_per_share"] == pytest.approx(line - ENTRY)
    sma = _walk("sma", sess, prior=[10.0, 10.0, 10.0])
    assert sma["status"] in ("pending", "horizon") and sma["pnl_per_share"] is None


def test_trail_arms_fail_loud_never_fall_back_to_the_sma_trail():
    sess = _sessions([(9.8, 9.9)])
    with pytest.raises(ValueError):
        _walk("character_ma", sess)                       # no profile → never a silent SMA walk
    with pytest.raises(ValueError):
        _walk("pivot_swing", sess)                        # no annotated pivots
    with pytest.raises(ValueError):
        _walk("ema_10_20", sess)                          # not one of this recorder's trails


def test_pivot_annotation_stops_at_the_first_missing_session():
    sess = _sessions([(9.7, 9.9), (9.6, 9.8), (9.4, 9.7), (9.5, 9.9), (9.6, 10.2)])
    sess[3] = (sess[3][0], None)                          # a data gap at session 4
    stops = lfc.pivot_stops_for_sessions(sess)
    assert len(stops) == 5 and stops == [None] * 5       # nothing confirmed across a hole


def test_character_profile_abstains_below_sixty_sessions():
    rows = [{"trade_date": FILL_DAY - timedelta(days=i), "close": 10.0, "low_price": 9.8,
             "high_price": 10.2} for i in range(1, 30)]
    assert lfc.character_profile_for(rows) is None


def test_orb_3r_stop_price_and_its_own_unit():
    assert lfc.arm_stop_price("orb_3r", entry=10.0, orb_low=9.5, live_stop=9.0, adr_dollar=None) == pytest.approx(8.5)
    assert lfc.arm_stop_price("orb_3r", entry=10.0, orb_low=10.5, live_stop=9.0, adr_dollar=None) is None
    assert lfc.arm_stop_price("orb_3r", entry=None, orb_low=9.5, live_stop=9.0, adr_dollar=None) is None


# ── the SSoT carries it ───────────────────────────────────────────────────────────────


def test_the_ssot_owns_the_one_recorder_and_the_router_points_at_it():
    ssot = _SSOT.read_text()
    assert "## Exit counterfactuals — ONE recorder, ONE read" in ssot
    for rid in (*FOLDED, CLOSED_BY_RULING, ONE_READ):
        assert rid in ssot, f"exit_discipline.md does not name {rid}"
    assert "508_exit_regime_interaction_n28_2026-09-09.md" in ssot    # the retraction, linked
    assert "trail_pivot_swing" in ssot and "stop_orb_3r" in ssot
    router = _ROUTER.read_text()
    assert "Exit counterfactuals" in router and "exit_discipline.md" in router
