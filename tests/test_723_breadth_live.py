"""#723 — live market breadth (the Today view): the nightly REFERENCE export, the intraday job, the host pusher.

Invented data, no network, no database. What each block proves:
  reference SQL   one read-only statement; the nightly's session / universe / NaN / usable-bar rules are copies
                  (the shared CTE bodies are byte-identical to export_breadth_snapshot.sql); the window is the 252
                  sessions ENDING at as_of (idx 0..251) with the 245-bar eligibility; the contract keys.
  shell           auto_export_snapshots.sh RUN against a fake docker + a real local git remote: the reference is its
                  own GUARDED step that runs FIRST and is NOT published — it lands in the host copy the intraday
                  job reads even when the fetch / the snapshots fail, and when it fails or truncates the snapshots
                  still publish and the old copy is left alone.
  arithmetic      compute_live vs a hand-worked fixture — highs/lows, advances/declines, group + theme returns.
  missing         a name Alpaca did not return, returned with a bar from an EARLIER day, or without a close is
                  counted missing — never unchanged, never a return.
  coverage        a refresh that lost ANY batch or read under 85% of the universe (2% coverage; every bar dated
                  yesterday on a mis-recognised holiday) raises and writes NOTHING — a counted failure.
  stale reference refresh_once raises and writes NOTHING; run_scheduled audits it and pages ONLY at the third
                  straight failure of the day; a success resets the streak. A file left unpublished for three
                  straight refreshes pages the same way.
  fetch           the job's own one-thread executor; a refresh skips (a counted failure) while the previous call is
                  still in flight; the collector's default path (EP Pass-2) is unchanged; the fetch stops after 3
                  lost chunks in a row only when asked to.
  schedule        the window rule (09:45..the session close: 16:00, 13:00 on Fri 2026-11-27), the registration
                  (hour 9-16, */15, mon-fri), the intelligence partition entry, the non-trading-day no-op.
  pusher          push_breadth_live.sh RUN against a local bare remote: one orphan single-file commit on
                  live-breadth, replaced in place on a change, nothing pushed when unchanged, the default branch
                  untouched (even with BREADTH_LIVE_BRANCH=main in the environment — the branch is hard-coded), a
                  failed push recorded, one run at a time (flock), its own bare repo (the nightly's clone gains no
                  object and no ref); the script never names the default branch.
  collector       daily_bar_high / daily_bar_low are additive keys.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import breadth_live as bl
from tests._sql_static import assert_one_read_only, strip_comments, strip_literals

REPO = Path(__file__).resolve().parents[1]
REF_SQL = REPO / "scripts" / "export_breadth_reference.sql"
NIGHTLY_SQL = REPO / "scripts" / "export_breadth_snapshot.sql"
EXPORT_SH = REPO / "scripts" / "auto_export_snapshots.sh"
PUSH_SH = REPO / "scripts" / "push_breadth_live.sh"
SSOT = REPO / "docs" / "architecture" / "market_breadth_snapshot.md"

_ET = ZoneInfo("America/New_York")
TODAY = date(2026, 11, 10)           # a Tuesday
PREV = date(2026, 11, 9)             # the Monday before it
NOW = datetime(2026, 11, 10, 11, 45, 3, tzinfo=_ET)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _cte(sql_text: str, name: str) -> str:
    code = strip_comments(sql_text)
    m = re.search(rf"\b{name} AS \(\n(.*?)\n\)(?:,|\nSELECT)", code, re.S)
    assert m, f"CTE `{name}` not found"
    return m.group(1)


# ═══════════════════════════════════════════════════════════════════════════ the reference SQL (static)

def test_reference_is_one_read_only_statement():
    assert_one_read_only(strip_literals(strip_comments(REF_SQL.read_text())))


def test_reference_returns_no_row_without_a_session():
    assert re.search(r"\)\s*FROM k\s+WHERE k\.as_of IS NOT NULL;\s*$", strip_comments(REF_SQL.read_text()))


@pytest.mark.parametrize("name", ["latest", "cal", "sess", "universe", "theme_latest", "themes_idx", "members",
                                  "interest", "member_of", "eco_names", "eco_themes"])
def test_reference_copies_the_nightly_rules_verbatim(name):
    """Session (3,000 rows, the future-date ceiling), universe (CS/ADRC, >= $1, not NaN), active themes (latest row
    first, Retired dropped after), members, groups and the ecosystem names: the same CTE body as the nightly's, so
    the two files cannot disagree on who is counted. (eco_names == theme_ecosystems.yaml is pinned by test_719.)"""
    assert _norm(_cte(REF_SQL.read_text(), name)) == _norm(_cte(NIGHTLY_SQL.read_text(), name))


def test_reference_window_is_the_252_sessions_ending_at_as_of():
    """The live job tests TODAY's bar (not in the table) against the 252 sessions ending at the last close — idx
    0..251 — where the nightly tests the as_of bar against idx 1..252. Eligibility is the nightly's 245 of 252."""
    px = _norm(_cte(REF_SQL.read_text(), "px"))
    assert px.count("w.idx BETWEEN 0 AND 251") == 3, "hmax, lmin and the eligibility count all read idx 0..251"
    assert "1 AND 252" not in px
    assert "WHERE idx <= 251" in _norm(_cte(REF_SQL.read_text(), "win"))
    assert "max(d.close) FILTER (WHERE w.idx = 0) AS c0" in px
    assert "COALESCE(p.n_hl_252 >= 245, false)" in _norm(strip_comments(REF_SQL.read_text()))


def test_reference_carries_the_nan_and_usable_bar_guards():
    code = strip_comments(REF_SQL.read_text())
    assert re.search(r"d\.close >= 1\.00 AND d\.close <> 'NaN'", code)
    for col in ("high_price", "low_price"):
        assert len(re.findall(rf"d\.{col} > 0 AND d\.{col} <> 'NaN'", code)) == 1, col
    assert re.search(r"AND d\.high_price <> 'NaN' AND d\.low_price <> 'NaN'\)\s+AS n_hl_252", code)
    assert "d.close > 0 AND d.close <> 'NaN'" in _norm(_cte(REF_SQL.read_text(), "px"))
    assert len(re.findall(r"(?i)\bnow\(\)", code)) == 2, "generated_at + the future-date ceiling only"
    assert not re.search(r"(?i)\bcurrent_date\b", code)


@pytest.mark.parametrize("key", ["version", "generated_at", "as_of", "universe", "themes", "ecosystems", "stocks",
                                 "definitions", "idx", "name", "e_code", "code", "theme_idx",
                                 "hi252_lo252", "hl_eligible", "in_universe", "not_claimed"])
def test_reference_emits_every_contract_key(key):
    assert re.search(rf"'{re.escape(key)}',", strip_comments(REF_SQL.read_text())), key


def test_reference_stock_row_shape_is_documented():
    code = _norm(strip_comments(REF_SQL.read_text()))
    assert ("json_build_array( p.c0, p.hmax_252, p.lmin_252, COALESCE(p.n_hl_252 >= 245, false), "
            "(u.ticker IS NOT NULL), COALESCE(to_json(mo.idxs), '[]'::json) )") in code
    text = SSOT.read_text()
    for needle in ("apollo_breadth_reference.json", "apollo_breadth_live.json", "live-breadth",
                   "push_breadth_live.sh", "[prev_close, hi252, lo252, hl_eligible, in_universe"):
        assert needle in text, f"SSoT does not mention {needle}"


def test_the_nightly_snapshot_sql_was_not_touched_by_the_reference():
    """The reference is a SECOND file; the nightly keeps its own window (idx 1..252) and every key test_719 pins."""
    nightly = _norm(_cte(NIGHTLY_SQL.read_text(), "px"))
    assert nightly.count("w.idx BETWEEN 1 AND 252") == 3
    assert "WHERE idx <= 272" in _norm(_cte(NIGHTLY_SQL.read_text(), "win"))


# ═══════════════════════════════════════════════════════════════════════════ the shell (behaviour)

_FAKE_DOCKER = r"""#!/bin/sh
sql="$(cat)"
case "$sql" in
  *export_breadth_reference*)
    echo "reference: $*" >> "$FAKE_DOCKER_LOG"
    case "${FAKE_REFERENCE:-ok}" in
      fail)  echo "ERROR:  relation does not exist" >&2; exit 3 ;;
      short) printf '{}\n'; exit 0 ;;
      ok)    printf '{"reference": "%s", "as_of": "2026-11-09", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0; exit 0 ;;
    esac ;;
  *export_breadth_snapshot*)
    printf '{"breadth": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0 ;;
  *)
    printf '{"other": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0 ;;
esac
"""
THREE = ("apollo_themes_snapshot.json", "apollo_trades_paper.json", "apollo_funnel_snapshot.json")
REFERENCE = "apollo_breadth_reference.json"


def _git(cwd: Path, *args: str, env: dict) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return env


@pytest.fixture
def remote_rig(tmp_path):
    """A bare portfolio-app2 remote seeded with the three snapshots on its default branch, and a clone."""
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("needs git and bash")
    env = _git_env()
    remote, seed, dest = (tmp_path / n for n in ("remote.git", "seed", "dest"))
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote), env=env)
    _git(tmp_path, "clone", "-q", str(remote), str(seed), env=env)
    for f in THREE:
        (seed / f).write_text('{"seed": true}\n')
    _git(seed, "add", *THREE, env=env)
    _git(seed, "commit", "-q", "-m", "seed", env=env)
    _git(seed, "push", "-q", "origin", "HEAD:main", env=env)
    _git(tmp_path, "clone", "-q", str(remote), str(dest), env=env)
    return NS(env=env, remote=remote, seed=seed, dest=dest, tmp=tmp_path)


@pytest.fixture
def export_rig(remote_rig):
    r = remote_rig
    bin_dir = r.tmp / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(_FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    copy = r.tmp / "hostlogs" / REFERENCE
    env = {**r.env, "PATH": f"{bin_dir}{os.pathsep}{r.env['PATH']}", "APOLLO_DIR": str(REPO),
           "EXPORT_DIR": str(r.dest), "BREADTH_REFERENCE_COPY": str(copy),
           "FAKE_DOCKER_LOG": str(r.tmp / "docker.log")}

    def run(**fake):
        return subprocess.run(["bash", str(EXPORT_SH)], env={**env, **fake}, capture_output=True, text=True)

    def published(name: str) -> str | None:
        p = subprocess.run(["git", "show", f"main:{name}"], cwd=r.remote, env=r.env, capture_output=True, text=True)
        return p.stdout if p.returncode == 0 else None

    return NS(run=run, published=published, copy=copy, dest=r.dest, log=r.tmp / "docker.log")


def test_reference_lands_in_the_host_copy_and_is_not_published(export_rig):
    """The reference is what the intraday job reads, not a dashboard file: it goes to the host copy only. (Publishing
    it committed ~5,000 tickers to portfolio-app2 every night for a page that never read it — review 2026-11-10.)"""
    r = export_rig.run(FAKE_NONCE="a")
    assert r.returncode == 0, r.stderr
    assert export_rig.copy.exists() and '"reference": "a"' in export_rig.copy.read_text()
    assert export_rig.published(REFERENCE) is None, "the reference must not be committed to the dashboard repo"
    assert not (export_rig.dest / REFERENCE).exists() and not (export_rig.dest / f"{REFERENCE}.tmp").exists()
    assert '"breadth": "a"' in export_rig.published("apollo_breadth_snapshot.json")
    assert not export_rig.copy.with_name(export_rig.copy.name + ".tmp").exists()


def test_reference_is_placed_even_when_the_dashboard_push_cannot_happen(export_rig):
    """The next session's live job depends on the reference alone, so it runs FIRST — before the fetch/reset and the
    all-or-nothing snapshot loop. A GitHub outage at export time (the clone's origin unreachable) aborts the
    snapshots under set -e and still leaves a fresh reference."""
    subprocess.run(["git", "remote", "set-url", "origin", "/nonexistent/remote.git"], cwd=export_rig.dest, check=True)
    r = export_rig.run(FAKE_NONCE="z")
    assert r.returncode != 0, "the snapshot push must fail when the remote is unreachable"
    assert export_rig.copy.exists() and '"reference": "z"' in export_rig.copy.read_text()
    assert export_rig.published(THREE[0]) == '{"seed": true}\n'          # nothing else moved


def test_a_failing_reference_export_blocks_nothing_and_keeps_the_old_copy(export_rig):
    assert export_rig.run(FAKE_NONCE="b").returncode == 0
    r = export_rig.run(FAKE_NONCE="c", FAKE_REFERENCE="fail")
    assert r.returncode == 0, r.stderr
    assert "REFERENCE export FAILED" in r.stderr
    for f in THREE + ("apollo_breadth_snapshot.json",):
        assert '"c"' in export_rig.published(f), f"{f} was not refreshed because the reference failed"
    assert '"reference": "b"' in export_rig.copy.read_text(), "the host copy the intraday job reads must be left as it was"
    assert not export_rig.copy.with_name(export_rig.copy.name + ".tmp").exists()


def test_a_truncated_reference_is_not_published_or_copied(export_rig):
    r = export_rig.run(FAKE_NONCE="d", FAKE_REFERENCE="short")
    assert r.returncode == 0, r.stderr
    assert "REFERENCE export FAILED or truncated" in r.stderr
    assert not export_rig.copy.exists() and not export_rig.copy.with_name(export_rig.copy.name + ".tmp").exists()
    assert '"d"' in export_rig.published(THREE[0])


def test_reference_psql_call_is_guarded_like_the_breadth_one(export_rig):
    """What psql was CALLED with: ON_ERROR_STOP (a SQL error is an exit code, not empty output) and a statement
    timeout (a hung reference query ends instead of holding up the other snapshots). The size floor is the
    truncated-reference test above."""
    assert export_rig.run(FAKE_NONCE="g").returncode == 0
    calls = [c for c in export_rig.log.read_text().splitlines() if c.startswith("reference: ")]
    assert len(calls) == 1, calls
    assert "-v ON_ERROR_STOP=1" in calls[0] and "statement_timeout=" in calls[0]


# ═══════════════════════════════════════════════════════════════════════════ the arithmetic (hand-worked)

def _bar_ts(d: date) -> datetime:
    """Alpaca stamps a daily bar at 00:00 ET of its day (05:00Z in November)."""
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=_ET).astimezone(ZoneInfo("UTC"))


def _snap(close, high=None, low=None, day: date = TODAY):
    return {"daily_bar_close": close, "daily_bar_high": high if high is not None else close,
            "daily_bar_low": low if low is not None else close, "daily_bar_ts": _bar_ts(day),
            "price": close, "prev_close": 999.0}      # Alpaca's own prev_close is a decoy: never used


def _reference() -> dict:
    """Twelve names. Row = [prev_close, hi252, lo252, hl_eligible, in_universe, theme idxs].
    Themes: 0 'Alpha' (E-A: AAA, BBB, CCC), 1 'Beta' (E-A: CCC, DDD, OUT), 2 'Gamma' (no group: EEE).
    Groups: E-A = {AAA, BBB, CCC, DDD, OUT} (CCC once), E-UNASSIGNED = {EEE}."""
    return {
        "version": 1, "as_of": PREV.isoformat(),
        "themes": [{"idx": 0, "name": "Alpha", "e_code": "E-A"}, {"idx": 1, "name": "Beta", "e_code": "E-A"},
                   {"idx": 2, "name": "Gamma", "e_code": None}],
        "ecosystems": [{"code": "E-A", "name": "Group A", "theme_idx": [0, 1]},
                       {"code": "E-UNASSIGNED", "name": "Other", "theme_idx": [2]}],
        "stocks": {
            "AAA": [10.0, 12.0, 8.0, True, True, [0]],        # +10%: new high (12.0 >= 12.0), advance
            "BBB": [20.0, 30.0, 15.0, True, True, [0]],       # -5%: new low (14.0 <= 15.0), decline
            "CCC": [50.0, 60.0, 40.0, True, True, [0, 1]],    # unchanged, no high/low; in two themes of one group
            "DDD": [8.0, 9.0, 7.0, False, True, [1]],         # +25% but NOT eligible: no high counted
            "EEE": [4.0, 5.0, 3.0, True, True, [2]],          # -50%, usable bar, low 2.0 <= 3.0 new low
            "FFF": [None, 7.0, 6.0, True, True, []],          # no prev close: no_prior, not in adv/dec
            "GGG": [3.0, 4.0, 2.0, True, True, []],           # absent from Alpaca: missing
            "HHH": [6.0, 7.0, 5.0, True, True, []],           # bar dated YESTERDAY: missing, never unchanged
            "III": [9.0, 11.0, 8.0, True, True, []],          # bar without a close: missing
            "JJJ": [2.0, 3.0, 1.5, True, True, []],           # eligible but today's low is 0 (unusable): advance only
            "KKK": [15.0, 20.0, 10.0, False, True, []],       # hi/lo nulls in the reference (<245 bars): advance only
            "OUT": [100.0, 120.0, 80.0, True, False, [1]],    # theme member OUTSIDE the universe: return only
        },
    }


def _snaps() -> dict:
    return {
        "AAA": _snap(11.0, high=12.0, low=10.5),
        "BBB": _snap(19.0, high=19.5, low=14.0),
        "CCC": _snap(50.0, high=51.0, low=49.0),
        "DDD": _snap(10.0, high=10.0, low=9.5),
        "EEE": _snap(2.0, high=4.0, low=2.0),
        "FFF": _snap(6.5),
        "HHH": _snap(6.0, day=PREV),
        "III": {"daily_bar_close": None, "daily_bar_high": 10.0, "daily_bar_low": 9.0, "daily_bar_ts": _bar_ts(TODAY)},
        "JJJ": _snap(2.2, high=2.5, low=0.0),
        "KKK": _snap(16.0, high=16.5, low=15.5),
        "OUT": _snap(110.0),
    }


def test_compute_live_matches_the_hand_worked_fixture():
    out = bl.compute_live(_reference(), _snaps(), TODAY)
    assert out["universe_n"] == 11 and out["read_n"] == 8 and out["missing_n"] == 3
    # eligible = AAA BBB CCC EEE JJJ? no (low 0 unusable) -> AAA BBB CCC EEE = 4; FFF has a usable bar too (6.5/6.5) = 5
    assert out["highs_lows"] == {"eligible_n": 5, "new_highs": 1, "new_lows": 2}
    assert out["adv_dec"] == {"advances": 4, "declines": 2, "unchanged": 1, "no_prior": 1, "missing": 3}
    assert out["adv_dec"]["advances"] + out["adv_dec"]["declines"] + out["adv_dec"]["unchanged"] \
        + out["adv_dec"]["no_prior"] + out["adv_dec"]["missing"] == out["universe_n"]
    themes = {t["name"]: t for t in out["themes_1d"]}
    # Alpha: AAA +10, BBB -5, CCC 0 -> mean 1.67 over 3
    assert themes["Alpha"] == {"idx": 0, "name": "Alpha", "n_members": 3, "ret_1d": 1.67, "n_1d": 3}
    # Beta: CCC 0, DDD +25, OUT +10 -> 11.67 over 3 (OUT counts: a member outside the universe still returns)
    assert themes["Beta"] == {"idx": 1, "name": "Beta", "n_members": 3, "ret_1d": 11.67, "n_1d": 3}
    assert themes["Gamma"] == {"idx": 2, "name": "Gamma", "n_members": 1, "ret_1d": -50.0, "n_1d": 1}
    groups = {g["code"]: g for g in out["ecosystems_1d"]}
    # E-A unique members AAA BBB CCC DDD OUT: +10 -5 0 +25 +10 -> 8.0 over 5, up 3 (CCC counted ONCE)
    assert groups["E-A"] == {"code": "E-A", "name": "Group A", "n_members": 5, "ret_1d": 8.0, "n_1d": 5, "up_1d": 3}
    assert groups["E-UNASSIGNED"] == {"code": "E-UNASSIGNED", "name": "Other", "n_members": 1,
                                      "ret_1d": -50.0, "n_1d": 1, "up_1d": 0}


def test_missing_names_are_counted_never_guessed():
    """Absent, stale-dated or close-less names: missing. MUTATION: dropping the daily_bar_ts == today check makes HHH
    (yesterday's bar at exactly its prev close) read as 'unchanged' — this test reddens."""
    out = bl.compute_live(_reference(), _snaps(), TODAY)
    assert out["adv_dec"]["unchanged"] == 1            # CCC only; HHH's stale 6.0 == 6.0 bar must not count
    assert out["missing_n"] == 3                        # GGG absent, HHH stale, III no close
    # none of the three contributes a return anywhere
    ref = _reference()
    ref["stocks"]["HHH"][5] = [2]
    out2 = bl.compute_live(ref, _snaps(), TODAY)
    assert {t["name"]: t["n_1d"] for t in out2["themes_1d"]}["Gamma"] == 1


def test_alpacas_own_prev_close_is_never_the_base():
    ref = _reference()
    snaps = {"AAA": {**_snap(11.0, high=11.0, low=11.0), "prev_close": 11.0}}   # Alpaca says unchanged
    out = bl.compute_live({**ref, "stocks": {"AAA": ref["stocks"]["AAA"]}}, snaps, TODAY)
    assert out["adv_dec"]["advances"] == 1 and out["adv_dec"]["unchanged"] == 0


def test_a_nan_or_zero_live_value_never_enters_a_test():
    ref = {"as_of": PREV.isoformat(), "themes": [], "ecosystems": [],
           "stocks": {"AAA": [10.0, 12.0, 8.0, True, True, []], "BBB": [10.0, 12.0, 8.0, True, True, []]}}
    snaps = {"AAA": _snap(float("nan"), high=99.0, low=1.0), "BBB": _snap(11.0, high=float("nan"), low=1.0)}
    out = bl.compute_live(ref, snaps, TODAY)
    assert out["missing_n"] == 1                                  # AAA: a NaN close is no close
    assert out["highs_lows"] == {"eligible_n": 0, "new_highs": 0, "new_lows": 0}   # BBB: NaN high = unusable bar
    assert out["adv_dec"]["advances"] == 1


# ═══════════════════════════════════════════════════════════════════════════ stale reference + the page rule

class _Audit:
    def __init__(self):
        self.rows: list[tuple[str, str]] = []

    async def __call__(self, event_type, summary, detail="", **kw):
        self.rows.append((event_type, summary))
        return True


@pytest.fixture
def paths(tmp_path, monkeypatch):
    out_dir = tmp_path / "live"
    ref_path = tmp_path / "ref.json"
    monkeypatch.setenv(bl.ENV_LIVE_DIR, str(out_dir))
    monkeypatch.setenv(bl.ENV_REFERENCE_PATH, str(ref_path))
    audit = _Audit()
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", audit)
    bl._streak_reset(None)
    return NS(out_dir=out_dir, ref_path=ref_path, audit=audit)


PAD = [f"P{i:02d}" for i in range(40)]      # 40 plain names, read fine, unchanged, not hl-eligible


def _live_reference() -> dict:
    """The hand-worked twelve plus forty padding names: 48 of 51 universe names read (94%) — a healthy refresh
    clears the 85% coverage floor the way prod does (the 11-09 probe read ~96%). The twelve alone read 8 of 11
    (73%), which the floor rightly refuses."""
    ref = _reference()
    for t in PAD:
        ref["stocks"][t] = [10.0, None, None, False, True, []]
    return ref


def _snaps_live() -> dict:
    return {**_snaps(), **{t: _snap(10.0) for t in PAD}}


async def _fetch_ok(tickers):
    return {t: s for t, s in _snaps_live().items() if t in tickers}, {"batches_total": 1, "batches_failed": 0}


def test_stale_reference_writes_nothing(paths):
    ref = _live_reference()
    ref["as_of"] = "2026-11-06"                        # Friday: the previous trading day before Tue 11-10 is Mon 11-09
    paths.ref_path.write_text(json.dumps(ref))
    with pytest.raises(bl.StaleReference, match="2026-11-06.*2026-11-09"):
        asyncio.run(bl.refresh_once(NOW, TODAY, fetch=_fetch_ok, ref_path=paths.ref_path, out_dir=paths.out_dir))
    assert not (paths.out_dir / bl.LIVE_NAME).exists()
    assert paths.audit.rows == []                      # the audit row for the refusal is run_scheduled's


def test_a_missing_reference_is_stale(paths):
    with pytest.raises(bl.StaleReference, match="missing"):
        asyncio.run(bl.refresh_once(NOW, TODAY, fetch=_fetch_ok, ref_path=paths.ref_path, out_dir=paths.out_dir))


def test_the_previous_trading_day_skips_weekends_and_holidays():
    from agents.market_intelligence.trading_calendar import previous_trading_day
    assert previous_trading_day(date(2026, 11, 9)) == date(2026, 11, 6)     # Monday -> Friday
    assert previous_trading_day(date(2026, 11, 10)) == date(2026, 11, 9)
    assert previous_trading_day(date(2026, 11, 27)) == date(2026, 11, 25)   # Fri after Thanksgiving -> Wed
    assert previous_trading_day(date(2026, 1, 20)) == date(2026, 1, 16)     # Tue after MLK Day -> the Friday before
    ref = {"as_of": "2026-11-25", "stocks": {}}
    assert bl.reference_staleness(ref, date(2026, 11, 27)) is None
    assert "2026-11-25" in bl.reference_staleness({"as_of": "2026-11-24", "stocks": {}}, date(2026, 11, 27))


def test_a_good_refresh_writes_the_contract_and_one_audit_row(paths):
    paths.ref_path.write_text(json.dumps(_live_reference()))
    res = asyncio.run(bl.refresh_once(NOW, TODAY, fetch=_fetch_ok, ref_path=paths.ref_path, out_dir=paths.out_dir))
    live = json.loads((paths.out_dir / bl.LIVE_NAME).read_text())
    assert set(live) == {"version", "as_of", "reference_as_of", "universe_n", "read_n", "missing_n", "highs_lows",
                         "adv_dec", "ecosystems_1d", "themes_1d"}
    assert live["as_of"] == "2026-11-10T11:45:03 ET" and live["reference_as_of"] == "2026-11-09"
    assert live["highs_lows"] == {"eligible_n": 5, "new_highs": 1, "new_lows": 2}
    assert live["universe_n"] == 51 and live["read_n"] == 48 and live["missing_n"] == 3
    assert res["read_n"] == 48 and res["push_problem"] is None
    assert [r[0] for r in paths.audit.rows] == [bl.EVT_REFRESH]
    assert "highs 1 lows 2 of 5" in paths.audit.rows[0][1] and "missing 3" in paths.audit.rows[0][1]
    assert not (paths.out_dir / f"{bl.LIVE_NAME}.tmp").exists()


def test_an_empty_fetch_is_a_failure_not_a_zero_market(paths):
    paths.ref_path.write_text(json.dumps(_live_reference()))

    async def nothing(tickers):
        return {}, {"batches_total": 1, "batches_failed": 1}
    with pytest.raises(bl.BreadthLiveError, match="no snapshots"):
        asyncio.run(bl.refresh_once(NOW, TODAY, fetch=nothing, ref_path=paths.ref_path, out_dir=paths.out_dir))
    assert not (paths.out_dir / bl.LIVE_NAME).exists()


# ═══════════════════════════════════════════════════════════════════════════ coverage (review 2026-11-10, blocking 1)

def test_a_partial_read_writes_nothing(paths):
    """49 of 50 batches lost: 100 names of 5,000 come back. Before the floor this published 100 advances / 0 declines /
    4,900 missing under a fresh stamp (the reviewer's partial.py repro). Now: raises, nothing written, counted."""
    stocks = {f"T{i:04d}": [10.0, 12.0, 8.0, True, True, []] for i in range(5000)}
    paths.ref_path.write_text(json.dumps({"as_of": PREV.isoformat(), "stocks": stocks, "themes": [], "ecosystems": []}))

    async def one_batch_of_fifty(tickers):
        return ({t: _snap(11.0, high=11.5, low=10.5) for t in tickers[:100]}, {"batches_total": 50, "batches_failed": 49})
    with pytest.raises(bl.BreadthLiveError, match="49 of 50 Alpaca batches failed"):
        asyncio.run(bl.refresh_once(NOW, TODAY, fetch=one_batch_of_fifty, ref_path=paths.ref_path, out_dir=paths.out_dir))
    assert not (paths.out_dir / bl.LIVE_NAME).exists() and not (paths.out_dir / f"{bl.LIVE_NAME}.tmp").exists()
    assert paths.audit.rows == []                      # the failure row is run_scheduled's


def test_low_coverage_with_no_lost_batch_writes_nothing(paths):
    """Every batch 'succeeded' yet only 2% of the universe carries today's bar (Alpaca symbology thinned out, or the
    bars not rolled): under the 85% floor => refused. The 11-09 probe read ~96%, ten points above the floor."""
    stocks = {f"T{i:04d}": [10.0, 12.0, 8.0, True, True, []] for i in range(1000)}
    paths.ref_path.write_text(json.dumps({"as_of": PREV.isoformat(), "stocks": stocks, "themes": [], "ecosystems": []}))

    async def two_percent(tickers):
        return {t: _snap(11.0) for t in tickers[:20]}, {"batches_total": 10, "batches_failed": 0}
    with pytest.raises(bl.BreadthLiveError, match=r"read 20 of 1000 universe names \(2%\) — under the 85% floor"):
        asyncio.run(bl.refresh_once(NOW, TODAY, fetch=two_percent, ref_path=paths.ref_path, out_dir=paths.out_dir))
    assert not (paths.out_dir / bl.LIVE_NAME).exists()


def test_an_all_zero_read_on_a_misrecognised_holiday_writes_nothing(paths):
    """The calendar fails open on a holiday: every daily bar Alpaca returns is dated the previous session, so read_n is
    0 — an all-zero market that must never go out as live."""
    paths.ref_path.write_text(json.dumps(_live_reference()))

    async def yesterdays_bars(tickers):
        return {t: _snap(10.0, day=PREV) for t in tickers}, {"batches_total": 1, "batches_failed": 0}
    with pytest.raises(bl.BreadthLiveError, match=r"read 0 of 51.*\(0%\).*dated before today"):
        asyncio.run(bl.refresh_once(NOW, TODAY, fetch=yesterdays_bars, ref_path=paths.ref_path, out_dir=paths.out_dir))
    assert not (paths.out_dir / bl.LIVE_NAME).exists()


def test_coverage_problem_is_pure_and_the_floor_is_85_percent():
    assert bl.COVERAGE_FLOOR == 0.85
    ok = {"universe_n": 100, "read_n": 85}
    assert bl.coverage_problem(ok, {"batches_total": 1, "batches_failed": 0}, 100) is None
    assert "under the 85% floor" in bl.coverage_problem({"universe_n": 100, "read_n": 84}, {"batches_failed": 0}, 100)
    assert "1 of 1 Alpaca batches failed" in bl.coverage_problem(ok, {"batches_total": 1, "batches_failed": 1}, 100)
    assert "no universe" in bl.coverage_problem({"universe_n": 0, "read_n": 0}, {}, 0)
    assert bl.coverage_problem(ok, {}, 100) is None                 # an injected fetch may return sparse stats


def test_a_partial_read_counts_toward_the_page(paths, monkeypatch):
    _trading(monkeypatch)
    paths.ref_path.write_text(json.dumps(_live_reference()))

    async def lossy(tickers):
        return {t: s for t, s in _snaps_live().items() if t in tickers}, {"batches_total": 1, "batches_failed": 1}
    kw = dict(fetch=lossy, ref_path=paths.ref_path, out_dir=paths.out_dir)
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 0
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 0
    with pytest.raises(bl.BreadthLiveError, match="3 straight"):
        asyncio.run(bl.run_scheduled(NOW, **kw))
    assert [r[0] for r in paths.audit.rows] == [bl.EVT_REFRESH_FAILED] * 3
    assert "batches failed" in paths.audit.rows[0][1]
    assert not (paths.out_dir / bl.LIVE_NAME).exists()


def _trading(monkeypatch, is_day=True):
    monkeypatch.setattr("agents.market_intelligence.trading_calendar.get_market_status",
                        lambda d: NS(is_trading_day=is_day, reason="test"))
    monkeypatch.setattr("shared.dates.et_today", lambda: TODAY)


def test_run_scheduled_pages_only_on_the_third_straight_failure(paths, monkeypatch):
    """Stale all morning: audited every run, ONE raise at the third (audit_wrap's record_job_failure is the page),
    silent again after it; a success resets the streak so a later outage pages afresh."""
    _trading(monkeypatch)
    stale = _live_reference()
    stale["as_of"] = "2026-11-06"
    paths.ref_path.write_text(json.dumps(stale))
    kw = dict(fetch=_fetch_ok, ref_path=paths.ref_path, out_dir=paths.out_dir)
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 0
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 0
    with pytest.raises(bl.BreadthLiveError, match="3 straight"):
        asyncio.run(bl.run_scheduled(NOW, **kw))
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 0          # the 4th does not page again
    assert [r[0] for r in paths.audit.rows] == [bl.EVT_REFERENCE_STALE] * 4
    assert "(1 straight)" in paths.audit.rows[0][1] and "(4 straight)" in paths.audit.rows[3][1]
    assert not (paths.out_dir / bl.LIVE_NAME).exists()
    # the export catches up: a success resets the streak
    paths.ref_path.write_text(json.dumps(_live_reference()))
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 48
    assert bl._streak["n"] == 0
    paths.ref_path.write_text(json.dumps(stale))
    for _ in range(2):
        assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 0
    with pytest.raises(bl.BreadthLiveError):
        asyncio.run(bl.run_scheduled(NOW, **kw))


def test_a_fetch_failure_is_audited_under_its_own_event(paths, monkeypatch):
    _trading(monkeypatch)
    paths.ref_path.write_text(json.dumps(_live_reference()))

    async def boom(tickers):
        raise RuntimeError("alpaca down")
    assert asyncio.run(bl.run_scheduled(NOW, fetch=boom, ref_path=paths.ref_path, out_dir=paths.out_dir)) == 0
    assert paths.audit.rows[0][0] == bl.EVT_REFRESH_FAILED and "alpaca down" in paths.audit.rows[0][1]


# ═══════════════════════════════════════════════════════════════════════════ the schedule

@pytest.mark.parametrize("hm,inside", [((9, 30), False), ((9, 44), False), ((9, 45), True), ((10, 0), True),
                                       ((12, 15), True), ((15, 45), True), ((16, 0), True), ((16, 15), False),
                                       ((16, 45), False), ((9, 0), False)])
def test_refresh_window_is_0945_to_1600_et(hm, inside):
    assert bl.in_refresh_window(datetime(2026, 11, 10, *hm, tzinfo=_ET)) is inside


@pytest.mark.parametrize("hm,inside", [((9, 44), False), ((9, 45), True), ((12, 45), True), ((13, 0), True),
                                       ((13, 15), False), ((15, 45), False), ((16, 0), False)])
def test_refresh_window_ends_at_the_early_close_on_a_half_day(hm, inside):
    """Fri 2026-11-27 (the day after Thanksgiving) closes at 13:00: the last refresh is 13:00, so the stamp stops moving
    when the market shuts. Before this the window ran to a fixed 16:00 and the page would have shown 'Live · as of
    15:45' over numbers frozen at 13:00 (review 2026-11-10, blocking 3; the PLAN's 'a number older than its stamp')."""
    assert bl.window_end(date(2026, 11, 27)) == (13, 0) and bl.window_end(date(2026, 11, 10)) == (16, 0)
    assert bl.in_refresh_window(datetime(2026, 11, 27, *hm, tzinfo=_ET)) is inside


def test_session_close_time_falls_open_to_1600(monkeypatch):
    from agents.market_intelligence import trading_calendar as tc
    assert tc.session_close_time(date(2026, 12, 24)) == dt_time(13, 0)
    assert tc.session_close_time(date(2026, 11, 10)) == dt_time(16, 0)

    def boom():
        raise RuntimeError("no calendar")
    monkeypatch.setattr(tc, "_get_nyse_calendar", boom)
    assert tc.session_close_time(date(2026, 11, 27)) == dt_time(16, 0)     # a broken calendar lengthens, never shortens


def test_outside_the_window_or_on_a_non_trading_day_nothing_is_fetched(paths, monkeypatch):
    paths.ref_path.write_text(json.dumps(_live_reference()))
    calls = []

    async def spy(tickers):
        calls.append(len(tickers))
        return await _fetch_ok(tickers)
    _trading(monkeypatch, is_day=True)
    assert asyncio.run(bl.run_scheduled(datetime(2026, 11, 10, 9, 30, tzinfo=_ET), fetch=spy,
                                        ref_path=paths.ref_path, out_dir=paths.out_dir)) == 0
    _trading(monkeypatch, is_day=False)                     # a holiday that falls on a weekday
    assert asyncio.run(bl.run_scheduled(NOW, fetch=spy, ref_path=paths.ref_path, out_dir=paths.out_dir)) == 0
    assert calls == [] and paths.audit.rows == []
    _trading(monkeypatch, is_day=True)
    assert asyncio.run(bl.run_scheduled(NOW, fetch=spy, ref_path=paths.ref_path, out_dir=paths.out_dir)) == 48
    assert calls == [52]


def test_run_scheduled_checks_the_trading_day_before_the_window(paths, monkeypatch):
    """On a weekday market holiday session_close_time logs 'session close unreadable' on every call; the trading-day
    check comes first so the window (and its close-time lookup) is never consulted."""
    seen = []
    monkeypatch.setattr("agents.market_intelligence.trading_calendar.session_close_time",
                        lambda d: seen.append(d) or None)
    _trading(monkeypatch, is_day=False)
    assert asyncio.run(bl.run_scheduled(NOW, ref_path=paths.ref_path, out_dir=paths.out_dir)) == 0
    assert seen == [], "session_close_time must not be asked about a non-trading day"


def test_registration_every_15_min_hour_9_to_16_weekdays_intelligence_owned():
    from scripts.check_job_date_sources import Module, registrations
    from agents.market_intelligence import scheduler as sched
    regs = [r for r in registrations(Module(REPO / "agents" / "market_intelligence" / "scheduler.py"))
            if r["job_id"] == bl.JOB_ID]
    assert len(regs) == 1, regs
    assert regs[0]["cron"] == {"hour": "9-16", "minute": "*/15", "day_of_week": "mon-fri", "timezone": "America/New_York"}
    assert regs[0]["func"] == "_breadth_live_refresh_job" and not regs[0]["paused"]
    assert bl.JOB_ID in sched.INTELLIGENCE_OWNED_JOB_IDS and bl.JOB_ID not in sched.EXECUTION_OWNED_JOB_IDS


def test_the_cron_slot_covers_every_refresh_in_the_window():
    """A CronTrigger hour 9-16 / */15 on weekdays fires at exactly the 26 quarter-hours 09:45..16:00 inside the window
    (and the window guard drops the 09:00/09:15/09:30/16:15/16:30/16:45 fires)."""
    from apscheduler.triggers.cron import CronTrigger
    trig = CronTrigger(hour="9-16", minute="*/15", day_of_week="mon-fri", timezone="America/New_York")
    t = datetime(2026, 11, 9, 23, 0, tzinfo=_ET)      # Monday night
    fires = []
    while True:
        t = trig.get_next_fire_time(None, t + timedelta(seconds=1))
        if t.date() != date(2026, 11, 10):
            break
        fires.append(t)
    inside = [f for f in fires if bl.in_refresh_window(f)]
    assert [(f.hour, f.minute) for f in inside][:3] == [(9, 45), (10, 0), (10, 15)]
    assert (inside[-1].hour, inside[-1].minute) == (16, 0) and len(inside) == 26
    sat = trig.get_next_fire_time(None, datetime(2026, 11, 14, 0, 0, tzinfo=_ET))   # Saturday
    assert sat.weekday() == 0, "weekends never fire"
    # the half day: 14 refreshes, 09:45..13:00
    t = datetime(2026, 11, 26, 23, 0, tzinfo=_ET)
    half = []
    while True:
        t = trig.get_next_fire_time(None, t + timedelta(seconds=1))
        if t.date() != date(2026, 11, 27):
            break
        half.append(t)
    half_inside = [f for f in half if bl.in_refresh_window(f)]
    assert len(half_inside) == 14 and (half_inside[-1].hour, half_inside[-1].minute) == (13, 0)


# ═══════════════════════════════════════════════════════════════════════════ the push status (job side)

def test_push_problem_reads_the_host_status(tmp_path):
    d = tmp_path
    assert bl.push_problem(d) is None                                   # nothing written yet
    live = d / bl.LIVE_NAME
    live.write_bytes(b'{"x": 1}\n')
    now = time.time()
    assert bl.push_problem(d, now_ts=now) is None                        # too fresh to judge
    old = now + bl.PUSH_LAG_TOLERANCE_S + 1
    assert "no push has ever been recorded" in bl.push_problem(d, now_ts=old)
    sha = bl.blob_sha(live.read_bytes())
    (d / bl.STATUS_NAME).write_text(json.dumps({"ok": True, "blob": sha, "at": "t"}))
    assert bl.push_problem(d, now_ts=old) is None
    (d / bl.STATUS_NAME).write_text(json.dumps({"ok": True, "blob": "0" * 40, "at": "t", "error": ""}))
    assert "earlier file" in bl.push_problem(d, now_ts=old)
    (d / bl.STATUS_NAME).write_text(json.dumps({"ok": False, "blob": sha, "at": "t", "error": "denied"}))
    assert "FAILED: denied" in bl.push_problem(d, now_ts=old)


def test_blob_sha_is_gits_blob_id():
    if not shutil.which("git"):
        pytest.skip("needs git")
    data = b'{"as_of": "x"}\n'
    want = subprocess.run(["git", "hash-object", "--stdin"], input=data, capture_output=True, check=True).stdout.decode().strip()
    assert bl.blob_sha(data) == want


def test_a_lagging_push_is_audited_at_the_next_refresh(paths):
    paths.ref_path.write_text(json.dumps(_live_reference()))
    paths.out_dir.mkdir()
    live = paths.out_dir / bl.LIVE_NAME
    live.write_text('{"old": true}\n')
    old = time.time() - bl.PUSH_LAG_TOLERANCE_S - 60
    os.utime(live, (old, old))
    res = asyncio.run(bl.refresh_once(NOW, TODAY, fetch=_fetch_ok, ref_path=paths.ref_path, out_dir=paths.out_dir))
    assert [r[0] for r in paths.audit.rows] == [bl.EVT_PUSH_LAGGING, bl.EVT_REFRESH]
    assert "push_breadth_live.sh" in paths.audit.rows[0][1]
    assert "no push has ever been recorded" in res["push_problem"]


def _age_the_live_file(out_dir: Path) -> None:
    live = out_dir / bl.LIVE_NAME
    old = time.time() - bl.PUSH_LAG_TOLERANCE_S - 60
    os.utime(live, (old, old))


def test_a_file_left_unpublished_pages_at_the_third_straight_refresh(paths, monkeypatch):
    """A host cron never installed (or a push failing every minute) used to be an audit row nobody reads until Friday
    (review 2026-11-10, item 9). Now: the third straight refresh that finds the previous file unpublished raises once
    — the page — after writing its own file; the fourth is silent; a landed push resets it."""
    _trading(monkeypatch)
    paths.ref_path.write_text(json.dumps(_live_reference()))
    kw = dict(fetch=_fetch_ok, ref_path=paths.ref_path, out_dir=paths.out_dir)
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 48          # the first file; nothing to judge yet
    for _ in range(2):
        _age_the_live_file(paths.out_dir)
        assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 48
    _age_the_live_file(paths.out_dir)
    with pytest.raises(bl.BreadthLiveError, match="NOT PUBLISHED for 3 straight refreshes"):
        asyncio.run(bl.run_scheduled(NOW, **kw))
    assert json.loads((paths.out_dir / bl.LIVE_NAME).read_text())["read_n"] == 48, "the refresh itself still writes"
    _age_the_live_file(paths.out_dir)
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 48          # the 4th does not page again
    assert [r[0] for r in paths.audit.rows].count(bl.EVT_PUSH_LAGGING) == 4
    # the host cron catches up: a recorded push of the current file resets the streak
    live = paths.out_dir / bl.LIVE_NAME
    (paths.out_dir / bl.STATUS_NAME).write_text(json.dumps({"ok": True, "blob": bl.blob_sha(live.read_bytes()), "at": "t"}))
    _age_the_live_file(paths.out_dir)
    assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 48
    assert bl._push_streak["n"] == 0
    # the cron dies again (its status vanishes with a wiped host dir): three more lagging reads page afresh
    (paths.out_dir / bl.STATUS_NAME).unlink()
    for _ in range(2):
        _age_the_live_file(paths.out_dir)
        assert asyncio.run(bl.run_scheduled(NOW, **kw)) == 48
    _age_the_live_file(paths.out_dir)
    with pytest.raises(bl.BreadthLiveError, match="NOT PUBLISHED"):
        asyncio.run(bl.run_scheduled(NOW, **kw))


# ═══════════════════════════════════════════════════════════════════════════ the fetch (review 2026-11-10, blocking 2)

def test_the_fetch_runs_on_the_jobs_own_one_thread_executor(monkeypatch):
    """breadth_live hands the collector ITS executor (one thread, never the loop's shared default pool) plus the
    6 s budget and the 3-lost-chunks stop; the collector's defaults are untouched for the EP callers."""
    from agents.market_intelligence import collector
    seen = {}

    async def fake(tickers, **kw):
        seen.update(kw)
        kw["stats"].update({"batches_total": 1, "batches_failed": 0})
        return {t: _snap(1.0) for t in tickers}
    monkeypatch.setattr(collector, "get_alpaca_snapshots_batch", fake)
    snaps, stats = asyncio.run(bl._fetch_snapshots(["AAA", "BBB"]))
    assert set(snaps) == {"AAA", "BBB"} and stats == {"batches_total": 1, "batches_failed": 0}
    assert seen["executor"] is bl._FETCH_EXECUTOR and isinstance(bl._FETCH_EXECUTOR, bl._OneThread)
    assert bl._FETCH_EXECUTOR._max_workers == 1
    assert seen["timeout_s"] == 6.0 and seen["concurrency"] == 1 and seen["max_consecutive_failures"] == 3


def test_a_refresh_skips_while_a_hung_alpaca_call_holds_the_thread(monkeypatch):
    """Re-review 2026-11-09: a HUNG alpaca-py call (no HTTP timeout) with real wait_for timeouts firing. The collector
    keeps submitting after the hang; those calls queue behind it and each timeout CANCELS its queued call, so a
    last-call-only guard read 'idle' while the thread was still stuck. busy() must stay true until the hung call
    itself returns, the second refresh must SKIP (the client is never called again), and it clears on release."""
    import threading
    import time as _time
    release, calls = threading.Event(), []

    class Hung:
        def __init__(self, **kw):
            pass

        def get_stock_snapshot(self, req):
            calls.append(_time.monotonic())
            release.wait(timeout=30)                          # hangs like an alpaca-py call with no HTTP timeout
            return {}
    from tests.test_490_collector_rt import _FakeSnapReq, _env
    _env(monkeypatch)
    monkeypatch.setattr(bl, "FETCH_TIMEOUT_S", 0.2)
    own = bl._OneThread()
    monkeypatch.setattr(bl, "_FETCH_EXECUTOR", own)
    tickers = [f"T{i}" for i in range(5000)]
    try:
        with patch("alpaca.data.historical.StockHistoricalDataClient", Hung), \
                patch("alpaca.data.requests.StockSnapshotRequest", _FakeSnapReq):
            snaps, stats = asyncio.run(bl._fetch_snapshots(tickers))   # real wait_for timeouts fire; nothing read
            assert snaps == {} and stats == {"batches_total": 50, "batches_failed": 50}, stats  # refresh_once refuses this
            assert len(calls) == 1, "one call reached the thread; the rest queued, timed out and were cancelled"
            assert bl.fetch_in_flight(), "the hung call still holds the thread — busy() must say so"
            with pytest.raises(bl.BreadthLiveError, match="still running"):
                asyncio.run(bl._fetch_snapshots(tickers))              # the second refresh SKIPS
            assert len(calls) == 1, "the skipped refresh must not touch the client"
    finally:
        release.set()
        own.shutdown(wait=True)
    assert not bl.fetch_in_flight(), "clears by itself once the thread returns"


def test_busy_ignores_a_cancelled_queued_call_but_not_the_running_one():
    import threading
    own = bl._OneThread()
    gate = threading.Event()
    running = own.submit(gate.wait)
    queued = own.submit(lambda: None)
    try:
        assert queued.cancel() and queued.cancelled()
        assert own.busy(), "the running call keeps it busy though the LAST call submitted is cancelled"
    finally:
        gate.set()
        running.result(timeout=5)
        own.shutdown(wait=True)
    assert not own.busy() and own._pending == set()


def _collector_rig(monkeypatch, fail: bool):
    from tests.test_490_collector_rt import _FakeClient, _FakeSnapReq, _env
    _env(monkeypatch)
    _FakeClient.calls, _FakeClient.fail = 0, fail
    return _FakeClient, patch("alpaca.data.historical.StockHistoricalDataClient", _FakeClient), \
        patch("alpaca.data.requests.StockSnapshotRequest", _FakeSnapReq)


def test_collector_default_path_uses_the_loops_default_pool_and_tries_every_chunk(monkeypatch):
    """EP Pass-2 / Pass-0 byte-identical: no executor passed => run_in_executor(None, ...); no stop => every one of
    the 10 chunks is attempted twice even when all fail, and stats carry exactly the two keys they always did."""
    from agents.market_intelligence import collector
    executors = []
    real = asyncio.BaseEventLoop.run_in_executor

    def spy(self, executor, fn, *args):
        executors.append(executor)
        return real(self, executor, fn, *args)
    monkeypatch.setattr(asyncio.BaseEventLoop, "run_in_executor", spy)
    client, p1, p2 = _collector_rig(monkeypatch, fail=True)
    stats: dict = {}
    with p1, p2:
        out = asyncio.run(collector.get_alpaca_snapshots_batch([f"T{i}" for i in range(1000)], stats=stats))
    assert out == {} and stats == {"batches_total": 10, "batches_failed": 10}
    assert client.calls == 20 and len(executors) == 20 and set(executors) == {None}


def test_collector_runs_on_the_given_executor_and_stops_after_three_lost_chunks(monkeypatch):
    from agents.market_intelligence import collector
    executors = []
    real = asyncio.BaseEventLoop.run_in_executor

    def spy(self, executor, fn, *args):
        executors.append(executor)
        return real(self, executor, fn, *args)
    monkeypatch.setattr(asyncio.BaseEventLoop, "run_in_executor", spy)
    own = bl._OneThread()
    client, p1, p2 = _collector_rig(monkeypatch, fail=True)
    stats: dict = {}
    with p1, p2:
        out = asyncio.run(collector.get_alpaca_snapshots_batch([f"T{i}" for i in range(1000)], stats=stats,
                                                                executor=own, max_consecutive_failures=3))
    assert out == {} and stats == {"batches_total": 10, "batches_failed": 10}     # the 7 unattempted count as failed
    assert client.calls == 6, "3 chunks × 2 attempts, then the rest are not attempted"
    assert len(executors) == 6 and set(executors) == {own}
    # a success in between resets the run: 2 fail, 1 ok, 2 fail, 1 ok ... never reaches 3 => every chunk attempted
    class Flaky(client):
        n = 0

        def get_stock_snapshot(self, req):
            Flaky.n += 1
            if Flaky.n % 3:
                raise RuntimeError("boom")
            return super().get_stock_snapshot(req)
    stats2: dict = {}
    client.fail = False
    with patch("alpaca.data.historical.StockHistoricalDataClient", Flaky), p2:
        out2 = asyncio.run(collector.get_alpaca_snapshots_batch([f"T{i}" for i in range(500)], stats=stats2,
                                                                 executor=own, max_consecutive_failures=3))
    # attempts: chunk1 (fail, fail) chunk2 (ok) chunk3 (fail, fail) chunk4 (ok) chunk5 (fail, fail): 2 of 5 read
    assert stats2 == {"batches_total": 5, "batches_failed": 3} and len(out2) == 200
    own.shutdown(wait=True)


# ═══════════════════════════════════════════════════════════════════════════ the pusher (behaviour)

@pytest.fixture
def push_rig(remote_rig):
    r = remote_rig
    live_dir = r.tmp / "breadth_live"
    live_dir.mkdir()
    env = {**r.env, "APOLLO_DIR": str(REPO), "EXPORT_DIR": str(r.dest), "BREADTH_LIVE_DIR": str(live_dir)}

    def run(**extra):
        return subprocess.run(["bash", str(PUSH_SH)], env={**env, **extra}, capture_output=True, text=True)

    def remote(*args):
        p = subprocess.run(["git", *args], cwd=r.remote, env=r.env, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None

    main_before = remote("rev-parse", "main")
    return NS(run=run, remote=remote, live=live_dir / bl.LIVE_NAME, status=live_dir / bl.STATUS_NAME,
              main_before=main_before, dest=r.dest)


def test_pusher_publishes_one_orphan_single_file_commit(push_rig):
    assert push_rig.run().returncode == 0 and push_rig.remote("rev-parse", "--verify", "-q", "live-breadth") is None
    push_rig.live.write_text('{"as_of": "2026-11-10T09:45:00 ET"}\n')
    r = push_rig.run()
    assert r.returncode == 0, r.stderr
    sha = push_rig.remote("rev-parse", "live-breadth")
    assert sha
    assert push_rig.remote("rev-list", "--count", "live-breadth") == "1"
    assert "parent" not in push_rig.remote("cat-file", "-p", sha), "the commit must be an orphan"
    tree = push_rig.remote("ls-tree", "--name-only", "live-breadth")
    assert tree == bl.LIVE_NAME, f"the branch must hold exactly one file, got {tree!r}"
    assert push_rig.remote("show", f"live-breadth:{bl.LIVE_NAME}") == '{"as_of": "2026-11-10T09:45:00 ET"}'
    assert push_rig.remote("rev-parse", "main") == push_rig.main_before, "the default branch must not move"
    st = json.loads(push_rig.status.read_text())
    assert st["ok"] is True and st["commit"] == sha and st["blob"] == bl.blob_sha(push_rig.live.read_bytes())
    # the clone the nightly export works in is untouched: clean tree, same HEAD
    assert subprocess.run(["git", "status", "--porcelain"], cwd=push_rig.dest, capture_output=True, text=True).stdout == ""


def test_pusher_publishes_on_a_host_with_no_git_identity(push_rig):
    """11-10 09:45 ET, the first live refresh: the prod host has no git user.name/email, so commit-tree died
    ('unable to auto-detect email address') and nothing published. The rig sets GIT_AUTHOR_*/GIT_COMMITTER_*,
    which hid it. WOULD-FAIL-IF the script relies on an ambient identity: with none in env or config, no push."""
    push_rig.live.write_text('{"as_of": "2026-11-10T10:00:00 ET"}\n')
    # user.useConfigOnly forbids git's hostname guess — a Mac guesses an email that passes; the Linux host cannot.
    env_no_id = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(["bash", str(PUSH_SH)], capture_output=True, text=True, env={
        **env_no_id, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(push_rig.dest.parent),
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.useConfigOnly", "GIT_CONFIG_VALUE_0": "true",
        "EMAIL": "", "APOLLO_DIR": str(REPO), "EXPORT_DIR": str(push_rig.dest),
        "BREADTH_LIVE_DIR": str(push_rig.live.parent)})
    assert r.returncode == 0, r.stderr
    assert push_rig.remote("show", f"live-breadth:{bl.LIVE_NAME}") == '{"as_of": "2026-11-10T10:00:00 ET"}'


def test_pusher_replaces_in_place_and_skips_an_unchanged_file(push_rig):
    push_rig.live.write_text('{"n": 1}\n')
    assert push_rig.run().returncode == 0
    first = push_rig.remote("rev-parse", "live-breadth")
    r = push_rig.run()                                                    # same bytes: nothing to do
    assert r.returncode == 0 and r.stdout == "" and push_rig.remote("rev-parse", "live-breadth") == first
    push_rig.live.write_text('{"n": 2}\n')
    assert push_rig.run().returncode == 0
    second = push_rig.remote("rev-parse", "live-breadth")
    assert second != first
    assert push_rig.remote("rev-list", "--count", "live-breadth") == "1", "history must not grow"
    assert "parent" not in push_rig.remote("cat-file", "-p", second)
    assert push_rig.remote("show", f"live-breadth:{bl.LIVE_NAME}") == '{"n": 2}'
    assert push_rig.remote("rev-parse", "main") == push_rig.main_before


def test_a_failed_push_is_recorded_and_retried_next_tick(push_rig):
    push_rig.live.write_text('{"n": 3}\n')
    r = push_rig.run(BREADTH_LIVE_REMOTE="/nonexistent/remote.git")
    assert r.returncode != 0 and "push FAILED" in r.stderr
    st = json.loads(push_rig.status.read_text())
    assert st["ok"] is False and st["error"] and st["blob"] == bl.blob_sha(push_rig.live.read_bytes())
    assert push_rig.remote("rev-parse", "--verify", "-q", "live-breadth") is None
    assert bl.push_problem(push_rig.live.parent, now_ts=time.time() + bl.PUSH_LAG_TOLERANCE_S + 1).startswith("last push at")
    r2 = push_rig.run()                                                    # the next cron tick, remote back
    assert r2.returncode == 0 and push_rig.remote("rev-list", "--count", "live-breadth") == "1"
    assert json.loads(push_rig.status.read_text())["ok"] is True


def test_pusher_ignores_a_branch_override_in_its_environment(push_rig):
    """BREADTH_LIVE_BRANCH=main in the cron environment used to force-push the orphan commit over the dashboard's
    default branch (review item 4). The branch is hard-coded now: the push still lands on live-breadth."""
    push_rig.live.write_text('{"n": 9}\n')
    r = push_rig.run(BREADTH_LIVE_BRANCH="main")
    assert r.returncode == 0, r.stderr
    assert push_rig.remote("rev-parse", "main") == push_rig.main_before, "the default branch must not move"
    assert push_rig.remote("show", f"live-breadth:{bl.LIVE_NAME}") == '{"n": 9}'


def test_pusher_works_in_its_own_bare_repo_never_the_nightlys_clone(push_rig):
    """The nightly export's clone gains no object and no ref from a push (review item 5: a pusher retry during the
    nightly's `git fetch` contended for a refs/remotes lock and, under set -e, cost all four snapshots)."""
    def dest_state():
        objs = subprocess.run(["git", "count-objects"], cwd=push_rig.dest, capture_output=True, text=True).stdout
        refs = subprocess.run(["git", "for-each-ref"], cwd=push_rig.dest, capture_output=True, text=True).stdout
        return objs, refs
    before = dest_state()
    push_rig.live.write_text('{"n": 10}\n')
    assert push_rig.run().returncode == 0
    push_rig.live.write_text('{"n": 11}\n')
    assert push_rig.run().returncode == 0
    assert dest_state() == before, "the nightly's clone must be untouched: no objects written, no tracking ref"
    own = push_rig.live.parent / ".push.git"
    assert (own / "HEAD").exists() and (own / "objects").is_dir(), "the pusher's own bare repo"
    assert push_rig.remote("show", f"live-breadth:{bl.LIVE_NAME}") == '{"n": 11}'
    # pruned after the push: the bare repo keeps nothing (its objects are on the remote)
    loose = subprocess.run(["git", "count-objects"], cwd=own, capture_output=True, text=True).stdout
    assert loose.startswith("0 objects"), loose


def test_pusher_runs_one_at_a_time(push_rig):
    """A second run while one is in progress exits 0 at once and pushes nothing (a hung ssh push no longer piles one
    more process onto the host every minute). flock is util-linux: present on the prod host, absent on macOS."""
    if not shutil.which("flock"):
        pytest.skip("flock not available on this platform (prod Linux has it)")
    push_rig.live.write_text('{"n": 12}\n')
    lock = push_rig.live.parent / ".push.lock"
    # -o: the lock fd is closed in `sleep`, so terminating the holder releases the lock at once (without it the
    # orphaned `sleep` kept the lock ~4.5 s and the follow-up run below exited quietly — CI 2026-11-09).
    holder = subprocess.Popen(["flock", "-o", str(lock), "sleep", "5"])
    try:
        time.sleep(0.5)
        r = push_rig.run()
        assert r.returncode == 0 and r.stdout == "" and not push_rig.status.exists()
        assert push_rig.remote("rev-parse", "--verify", "-q", "live-breadth") is None
    finally:
        holder.terminate()
        holder.wait()
    assert push_rig.run().returncode == 0 and push_rig.remote("rev-list", "--count", "live-breadth") == "1"


# ═══════════════════════════════════════════════════════════════════════════ the collector (additive)

def test_snapshot_batch_exposes_the_daily_bar_high_and_low(monkeypatch):
    from agents.market_intelligence import collector
    from tests.test_490_collector_rt import _FakeClient, _FakeSnapReq, _env, _fake_snapshot

    def with_hl():
        sn = _fake_snapshot()
        sn.daily_bar.high, sn.daily_bar.low = 12.25, 10.75
        return sn
    _env(monkeypatch)
    _FakeClient.calls, _FakeClient.fail = 0, False
    with patch("alpaca.data.historical.StockHistoricalDataClient", _FakeClient), \
         patch("alpaca.data.requests.StockSnapshotRequest", _FakeSnapReq), \
         patch("tests.test_490_collector_rt._fake_snapshot", with_hl):
        out = asyncio.run(collector.get_alpaca_snapshots_batch(["AAA"]))
    sn = out["AAA"]
    assert sn["daily_bar_high"] == 12.25 and sn["daily_bar_low"] == 10.75
    assert sn["daily_bar_close"] == 11.5 and sn["price"] == 12.0        # pre-#723 keys unchanged
