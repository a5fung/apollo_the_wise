"""COT snapshot export (scripts/export_cot_snapshot.sql) and its guarded nightly run. STATIC SQL checks (no database in
the unit suite) + the shell against a fake `docker` and a real local git remote. SSoT: docs/architecture/cot_snapshot.md."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from agents.market_intelligence import cot_family
from tests._sql_static import assert_one_read_only, strip_comments, strip_literals

REPO = Path(__file__).resolve().parents[1]
SQL_PATH = REPO / "scripts" / "export_cot_snapshot.sql"
SHELL_PATH = REPO / "scripts" / "auto_export_snapshots.sh"
SSOT_PATH = REPO / "docs" / "architecture" / "cot_snapshot.md"
COT = "apollo_cot_snapshot.json"
BASE = ("apollo_themes_snapshot.json", "apollo_trades_paper.json", "apollo_funnel_snapshot.json")
CODE = strip_comments(SQL_PATH.read_text())


def test_is_one_read_only_statement():
    assert_one_read_only(strip_literals(CODE))


def test_no_week_means_no_row():
    assert re.search(r"\) IS NOT NULL;\s*$", CODE)


def test_weeks_are_ranked_report_dates_not_calendar():
    assert "dense_rank() OVER (ORDER BY report_date DESC)" in CODE
    assert not re.search(r"(?i)\bcurrent_date\b", CODE)
    assert "w.rk <= 13" in CODE and "h.rk BETWEEN 2 AND 13" in CODE


def test_last_60_alerts_newest_first():
    assert "ORDER BY a.alert_date DESC, a.id DESC LIMIT 60" in CODE


def test_meta_values_mirror_cot_family_markets():
    got = dict((m, (n, s)) for m, n, s in re.findall(r"\('(\w+)', '([^']+)', '(\w+)'\)", CODE))
    want = {k: (v[0], v[4]) for k, v in cot_family.MARKETS.items()}
    assert got == want


def test_peerdef_mirrors_cot_family_peers():
    body = CODE.split("peerdef(market, peer_list) AS (", 1)[1].split("),\nix AS", 1)[0]
    got = {m: lst.split(",") for m, lst in re.findall(r"\('(\w+)', '([\w,\-]+)'\)", body)}
    want = {m: [("-" if sg < 0 else "") + p for p, sg in v] for m, v in cot_family.PEERS.items()}
    assert got == want


def test_double_encoded_detail_is_unwrapped_not_fatal():
    assert "jsonb_typeof(a.detail) = 'string'" in CODE and "(a.detail #>> '{}')::jsonb" in CODE
    assert "left(a.detail #>> '{}', 1) = '{'" in CODE      # a non-object string reads as no detail, never an abort


def test_old_alert_keys_are_unchanged():
    for k in ("alert_date", "market", "direction", "kind", "level", "report_date", "events", "entry_price",
              "stop_price", "first_minute", "first_minute_big", "news_class"):
        assert re.search(rf"'{k}', a\.", CODE), k


KEYS = ("version", "generated_at", "report_date", "known_from", "markets", "alerts", "definitions", "market", "name",
        "sector", "comm", "lspec", "sspec", "setup", "close_setup", "prev", "history", "alert_date", "direction", "kind",
        "level", "events", "entry_price", "stop_price", "first_minute", "first_minute_big", "news_class", "z", "peer_z",
        "entry_note", "stop_rule", "failure_day", "atr", "news", "peers", "inverse")


@pytest.mark.parametrize("key", KEYS)
def test_contract_key_emitted_and_documented(key):
    assert re.search(rf"'{key}',", CODE), key
    assert f"`{key}`" in SSOT_PATH.read_text(), key


_FAKE_DOCKER = r"""#!/bin/sh
sql="$(cat)"
case "$sql" in
  *export_cot*|*"COT FAMILY"*)
    echo "cot: $*" >> "$FAKE_DOCKER_LOG"
    case "${FAKE_COT:-ok}" in
      fail)  echo "ERROR: boom" >&2; exit 3 ;;
      short) printf '{}\n'; exit 0 ;;
      ok)    printf '{"cot": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0; exit 0 ;;
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
    assert '"cot": "a"' in (published(COT) or "")


def test_a_failing_export_never_blocks_the_others(rig):
    run, published, _ = rig
    r = run(FAKE_NONCE="b", FAKE_COT="fail")
    assert r.returncode == 0, r.stderr
    assert "COT export FAILED" in r.stderr
    for f in BASE:
        assert '"b"' in published(f)
    assert published(COT) is None


def test_a_truncated_export_is_not_published(rig):
    run, published, _ = rig
    r = run(FAKE_NONCE="c", FAKE_COT="short")
    assert r.returncode == 0, r.stderr
    assert "truncated" in r.stderr
    assert published(COT) is None
