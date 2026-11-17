"""RS Leaders snapshot export (scripts/export_rs_leaders_snapshot.sql) and its guarded nightly run.

STATIC checks on the SQL (no database in the unit suite; the real-Postgres run with an independent recompute is
recorded in the SSoT) + the SHELL behaviour against a fake `docker` and a real local git remote, in the test_719
pattern. SSoT: docs/architecture/rs_leaders_snapshot.md.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._sql_static import assert_one_read_only, strip_comments, strip_literals

REPO = Path(__file__).resolve().parents[1]
SQL_PATH = REPO / "scripts" / "export_rs_leaders_snapshot.sql"
SHELL_PATH = REPO / "scripts" / "auto_export_snapshots.sh"
SSOT_PATH = REPO / "docs" / "architecture" / "rs_leaders_snapshot.md"
RSL = "apollo_rs_leaders_snapshot.json"
BASE = ("apollo_themes_snapshot.json", "apollo_trades_paper.json", "apollo_funnel_snapshot.json")

CODE = strip_comments(SQL_PATH.read_text())


def test_is_one_read_only_statement():
    assert_one_read_only(strip_literals(CODE))


def test_no_session_means_no_row():
    assert re.search(r"\)\s*FROM k\s+WHERE k\.as_of IS NOT NULL;\s*$", CODE)


def test_dates_come_from_the_data_never_the_clock():
    assert not re.search(r"(?i)\bcurrent_date\b", CODE)
    assert len(re.findall(r"(?i)\bnow\(\)", CODE)) == 2  # generated_at + the future-date ceiling
    assert re.search(r"HAVING count\(\*\) >= 3000\b", CODE)
    assert "t.security_type IN ('CS', 'ADRC')" in CODE


def test_universe_and_nan_guards():
    assert re.search(r"d\.close >= 1\.00 AND d\.close <> 'NaN'", CODE)
    assert "d.high_price <> 'NaN'" in CODE and "d.low_price <> 'NaN'" in CODE


def test_liquidity_floor_is_a_20_session_median_of_5m():
    assert re.search(r"percentile_cont\(0\.5\) WITHIN GROUP \(ORDER BY d\.close \* d\.volume\)", CODE)
    assert "p.n_dv >= 15 AND p.dv20 >= 5000000" in CODE
    assert "'min_dollar_volume', 5000000" in CODE


@pytest.mark.parametrize("period,n", [("1w", 5), ("1m", 21), ("3m", 63), ("6m", 126)])
def test_period_offsets_are_session_indexes(period, n):
    assert f"'{period}', {n}," in CODE
    assert f"w.idx = {n}" in CODE


def test_top_50_ranked_high_to_low():
    assert "WHERE rnk <= 50" in CODE
    assert "ORDER BY (l.c0 / v.base) DESC, l.ticker" in CODE


def test_active_themes_latest_row_first_then_drop_retired():
    assert re.search(r"DISTINCT ON \(name\).*?ORDER BY name, theme_date DESC, id DESC", CODE, re.S)
    assert "l.stage <> 'Retired'" in CODE
    assert "theme_date >= (SELECT as_of FROM k) - 7" in CODE


KEYS = ("rank", "ticker", "name", "close", "ret", "pct_from_high", "adr20", "dollar_volume", "sector", "themes",
        "version", "generated_at", "as_of", "universe", "n_liquid", "periods", "sessions", "n_ranked", "rows",
        "definitions", "n_deal_pinned", "deal_pinned")


@pytest.mark.parametrize("key", KEYS)
def test_contract_key_emitted_and_documented(key):
    assert re.search(rf"'{key}',", CODE), key
    assert f"`{key}`" in SSOT_PATH.read_text(), key


def test_deal_pinned_names_leave_the_board():
    """BRZE 11-16: the same two legs as db.get_deal_pinned_tickers, applied before ranking."""
    assert "bool_and((high_price - low_price) / NULLIF(close, 0) < 0.02)" in CODE
    assert "HAVING count(*) = 4" in CODE
    assert "pct >= 15 AND rvol >= 10" in CODE
    assert "ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING" in CODE
    assert "k.as_of - 180" in CODE
    assert "p.ticker NOT IN (SELECT ticker FROM deal_pinned)" in CODE


# ------------------------------------------------------------------------------------------- the shell: behaviour
_FAKE_DOCKER = r"""#!/bin/sh
sql="$(cat)"
case "$sql" in
  *export_rs_leaders*)
    echo "rsl: $*" >> "$FAKE_DOCKER_LOG"
    case "${FAKE_RSL:-ok}" in
      fail)  echo "ERROR: boom" >&2; exit 3 ;;
      short) printf '{}\n'; exit 0 ;;
      ok)    printf '{"rsl": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0; exit 0 ;;
    esac ;;
  *)  printf '{"other": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0 ;;
esac
"""


def _git(cwd, *a, env):
    return subprocess.run(["git", *a], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def rig(tmp_path):
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("needs git and bash")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    remote, seed, dest, bin_dir = (tmp_path / n for n in ("remote.git", "seed", "dest", "bin"))
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote), env=env)
    _git(tmp_path, "clone", "-q", str(remote), str(seed), env=env)
    for f in BASE:
        (seed / f).write_text('{"seed": true}\n')
    _git(seed, "add", *BASE, env=env)
    _git(seed, "commit", "-q", "-m", "seed", env=env)
    _git(seed, "push", "-q", "origin", "HEAD:main", env=env)
    _git(tmp_path, "clone", "-q", str(remote), str(dest), env=env)
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(_FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    env.update(PATH=f"{bin_dir}{os.pathsep}{env['PATH']}", APOLLO_DIR=str(REPO), EXPORT_DIR=str(dest),
               FAKE_DOCKER_LOG=str(tmp_path / "docker.log"),
               BREADTH_REFERENCE_COPY=str(tmp_path / "hostlogs" / "apollo_breadth_reference.json"))

    def run(**fake):
        return subprocess.run(["bash", str(SHELL_PATH)], env={**env, **fake}, capture_output=True, text=True)

    def published(name):
        r = subprocess.run(["git", "show", f"main:{name}"], cwd=remote, env=env, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    return run, published, tmp_path


def test_the_file_is_published_when_the_export_succeeds(rig):
    run, published, _ = rig
    r = run(FAKE_NONCE="a")
    assert r.returncode == 0, r.stderr
    assert '"rsl": "a"' in (published(RSL) or "")


def test_a_failing_export_never_blocks_the_others(rig):
    run, published, _ = rig
    r = run(FAKE_NONCE="b", FAKE_RSL="fail")
    assert r.returncode == 0, r.stderr
    assert "RS leaders export FAILED" in r.stderr
    for f in BASE:
        assert '"b"' in published(f)
    assert published(RSL) is None


def test_a_truncated_export_is_not_published(rig):
    run, published, _ = rig
    r = run(FAKE_NONCE="c", FAKE_RSL="short")
    assert r.returncode == 0, r.stderr
    assert "truncated" in r.stderr
    assert published(RSL) is None


def test_psql_stops_on_error_and_has_a_timeout(rig):
    run, _, tmp = rig
    assert run(FAKE_NONCE="d").returncode == 0
    calls = (tmp / "docker.log").read_text().splitlines()
    assert calls and all("-v ON_ERROR_STOP=1" in c and "statement_timeout=" in c for c in calls)
