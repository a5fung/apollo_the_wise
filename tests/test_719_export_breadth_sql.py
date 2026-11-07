"""#719 — the Market Breadth snapshot export (scripts/export_breadth_snapshot.sql) and its guarded nightly run.

Two halves:
  1. STATIC checks on the SQL, in the test_706 pattern: one read-only SELECT, every JSON key the page reads, and the
     rules the SSoT pins (docs/architecture/market_breadth_snapshot.md) — the 3,000-row session guard, the > 0 high /
     low guard, the 252 / 245 window, the stage thresholds and session offsets, the active-theme rule, and the theme
     export's usable_score_date rule copied verbatim.
  2. The SHELL: scripts/auto_export_snapshots.sh is RUN against a fake `docker` on PATH and a real local git remote,
     so "a failing breadth export never blocks the other three" is checked by behaviour, not by reading the script.

Nothing here executes the SQL: no database in the unit suite. The run on a real (embedded) Postgres against a synthetic
fixture, with an independent Python recompute of every number, is scripts/probes/_719_export_breadth_1104/ (its
captured output sits beside the script).
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SQL_PATH = REPO / "scripts" / "export_breadth_snapshot.sql"
THEME_SQL_PATH = REPO / "scripts" / "export_theme_snapshot.sql"
SHELL_PATH = REPO / "scripts" / "auto_export_snapshots.sh"
SSOT_PATH = REPO / "docs" / "architecture" / "market_breadth_snapshot.md"

THREE = ("apollo_themes_snapshot.json", "apollo_trades_paper.json", "apollo_funnel_snapshot.json")
BREADTH = "apollo_breadth_snapshot.json"


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


@functools.cache
def _code() -> str:
    """The SQL with every `--` comment removed."""
    return _strip_comments(SQL_PATH.read_text())


def _code_no_literals() -> str:
    """Comments AND string literals removed — the definitions text is prose, and a word like 'set' in it is not SQL."""
    return re.sub(r"'(?:[^']|'')*'", "''", _code())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _cte(name: str) -> str:
    """The body of one CTE: from `name AS (` to the next top-level `),` / `)\nSELECT`."""
    code = _code()
    m = re.search(rf"\b{name} AS \(\n(.*?)\n\)(?:,|\nSELECT)", code, re.S)
    assert m, f"CTE `{name}` not found in the export"
    return m.group(1)


# ----------------------------------------------------------------------------------------------- read-only, one statement

def test_is_one_read_only_statement():
    code = _code_no_literals().strip()
    assert re.match(r"(?is)(WITH|SELECT)\b", code), "the export must open with SELECT (or a WITH feeding it)"
    assert code.endswith(";") and code.count(";") == 1, "exactly one statement"
    banned = re.findall(
        r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|MERGE|CALL|SET|VACUUM|LOCK)\b", code)
    assert not banned, f"a read-only export may not contain {sorted(set(banned))}"


def test_no_comment_marker_inside_a_string_literal():
    """The static checks strip `--` comments with a regex; a `--` inside a definitions string would be cut there."""
    for lit in re.findall(r"'(?:[^']|'')*'", _code()):
        assert "--" not in lit, f"`--` inside a string literal breaks comment stripping: {lit[:60]}"


def test_no_session_means_no_row_not_an_all_null_file():
    """The definitions text alone is > 200 bytes, so an all-null object would pass the nightly size floor. With no
    session the statement must return ZERO rows instead (psql then prints nothing and the guard rejects it)."""
    assert re.search(r"\)\s*FROM k\s+WHERE k\.as_of IS NOT NULL;\s*$", _code())


def test_dates_come_from_the_data_never_the_clock():
    """The cron also runs Saturday and Sunday: as_of is the newest 3,000-row session, never the calendar date."""
    code = _code()
    assert not re.search(r"(?i)\bcurrent_date\b", code), "as_of / windows must never read the clock"
    # now() twice: generated_at, and a CEILING on the newest stored date (review 2026-11-04: one stray
    # future-dated row must not move the calendar window). Neither picks as_of — the data does.
    assert len(re.findall(r"(?i)\bnow\(\)", code)) == 2, "now() is for generated_at and the future-date ceiling only"
    assert re.search(r"(?i)WHERE trade_date <= \(now\(\) AT TIME ZONE 'America/New_York'\)::date", code)
    assert re.search(r"(?i)'generated_at',\s*to_char\(now\(\) AT TIME ZONE 'America/New_York'", code)
    # review 2026-11-07: the ceiling also caps the calendar itself, not only where its window starts —
    # a future-dated day with 3,000+ rows must never become as_of.
    assert re.search(r"(?i)AND c\.trade_date <= \(SELECT d FROM latest\)", code)


def test_a_nan_price_never_enters_the_universe_or_a_high_low_test():
    """Postgres orders NaN ABOVE every number, so `close >= 1.00` and `high_price > 0` are TRUE for NaN. A NaN close
    would join the universe yet fall in none of advances / declines / unchanged / no_prior (their sum would miss the
    universe); a NaN high would always read as a new high. Review 2026-11-07."""
    code = _code()
    assert re.search(r"(?i)d\.close >= 1\.00 AND d\.close <> 'NaN'", code), "universe"
    for col in ("high_price", "low_price"):
        guarded = re.findall(rf"(?i)d\.{col} > 0 AND d\.{col} <> 'NaN'", code)
        assert len(guarded) == 2, f"{col}: the as_of value and the 252-session extreme both need the NaN guard"
    assert re.search(r"(?i)AND d\.high_price <> 'NaN' AND d\.low_price <> 'NaN'\)\s+AS n_hl_252", code), "n_hl_252"


# ----------------------------------------------------------------------------------------------------- the JSON contract

TOP_KEYS = ("version", "generated_at", "as_of", "prev_session", "prior_year_end", "score_date", "theme_membership",
            "universe", "highs_lows", "adv_dec", "stages", "themes", "stocks", "definitions")
NESTED_KEYS = ("n", "eligible_n", "new_highs", "new_lows", "advances", "declines", "unchanged", "no_prior",
               "1", "2", "3", "4", "unstaged")
THEME_KEYS = ("idx", "name", "stage", "e_code", "theme_date", "n_members", "members",
              "ret_1d", "n_1d", "ret_5d", "n_5d", "ret_21d", "n_21d", "ret_ytd", "n_ytd")
DEFINITION_KEYS = ("session", "as_of", "universe", "new_highs_lows", "advances_declines", "stage", "themes",
                   "theme_returns", "theme_membership", "stocks", "not_claimed")


@pytest.mark.parametrize("key", TOP_KEYS + NESTED_KEYS + THEME_KEYS + DEFINITION_KEYS)
def test_emits_every_contract_key(key):
    assert re.search(rf"'{re.escape(key)}',", _code()), f"the export no longer emits `{key}`"


@pytest.mark.parametrize("key", TOP_KEYS + THEME_KEYS)
def test_every_contract_key_is_documented_in_the_ssot(key):
    assert f"`{key}`" in SSOT_PATH.read_text(), f"`{key}` is emitted but not in the SSoT's JSON contract"


def test_membership_is_labelled_today():
    assert re.search(r"'theme_membership',\s*'today'", _code())


def test_stocks_entry_is_stage_rank_theme_indexes():
    assert re.search(r"json_build_array\(\s*s\.stage,\s*r\.rs_rank,\s*COALESCE\(to_json\(mo\.idxs\), '\[\]'::json\)",
                     _code())


# ------------------------------------------------------------------------------------------- sessions, as_of, universe

def test_a_session_is_a_3000_row_cs_adrc_date():
    cal = _cte("cal")
    assert "JOIN mi_security_types t ON t.ticker = c.ticker" in cal
    assert "t.security_type IN ('CS', 'ADRC')" in cal
    assert re.search(r"HAVING count\(\*\) >= 3000\b", cal)
    # bounded read: the calendar never scans the whole 13.6M-row table
    assert re.search(r"c\.trade_date >= \(SELECT d FROM latest\) - 500\b", cal)


def test_as_of_is_session_zero_and_windows_count_sessions():
    assert re.search(r"row_number\(\) OVER \(ORDER BY trade_date DESC\) - 1\)::int AS idx", _cte("sess"))
    k = _cte("k")
    assert "(SELECT trade_date FROM sess WHERE idx = 0) AS as_of" in k
    assert "(SELECT trade_date FROM sess WHERE idx = 1) AS prev_session" in k
    assert re.search(r"WHERE idx <= 272\b", _cte("win")), "as_of + 272 prior sessions"


def test_universe_is_cs_adrc_at_one_dollar_on_as_of():
    u = _cte("universe")
    assert "d.trade_date = (SELECT as_of FROM k)" in u
    assert "t.security_type IN ('CS', 'ADRC')" in u
    assert "d.close >= 1.00" in u


def test_price_window_is_bounded_on_trade_date():
    px = _cte("px")
    assert "JOIN win w ON w.trade_date = d.trade_date" in px
    assert "d.trade_date BETWEEN k.win_start AND k.as_of" in px
    assert "d.close > 0" in px
    assert "d.ticker IN (SELECT ticker FROM interest)" in px


# --------------------------------------------------------------------------------------------------- highs and lows

def test_every_high_and_low_read_is_guarded_above_zero():
    """Missing OHLC must never count: every aggregate over high_price / low_price filters it > 0."""
    px = _cte("px")
    reads = re.findall(r"(?:max|min|count)\((?:d\.(?:high|low)_price|\*)\)\s*FILTER \(WHERE ([^)]*?)\)\s+AS (\w+)",
                       px, re.S)
    by_alias = {alias: cond for cond, alias in reads}
    for alias, col in (("h0", "high"), ("l0", "low"), ("hmax_252", "high"), ("lmin_252", "low")):
        assert alias in by_alias, f"{alias} missing"
        assert f"d.{col}_price > 0" in by_alias[alias], f"{alias} reads {col}_price without the > 0 guard"
    assert "d.high_price > 0 AND d.low_price > 0" in _norm(by_alias["n_hl_252"])
    for line in px.splitlines():
        if re.search(r"d\.(high|low)_price", line) and "FILTER" in line:
            assert "_price > 0" in line, f"unguarded high/low read: {line.strip()}"


def test_the_252_session_lookback_excludes_as_of_and_needs_245_bars():
    px = _norm(_cte("px"))
    assert px.count("w.idx BETWEEN 1 AND 252") == 3, "hmax, lmin and the eligibility count all read idx 1..252"
    assert "max(d.high_price) FILTER (WHERE w.idx = 0 AND d.high_price > 0 AND d.high_price <> 'NaN') AS h0" in px
    assert "max(d.low_price) FILTER (WHERE w.idx = 0 AND d.low_price > 0 AND d.low_price <> 'NaN') AS l0" in px
    st = _norm(_cte("st"))
    assert "(p.h0 IS NOT NULL AND p.l0 IS NOT NULL AND p.n_hl_252 >= 245) AS hl_eligible" in st
    code = _norm(_code())
    assert "'new_highs', count(*) FILTER (WHERE hl_eligible AND h0 >= hmax_252)" in code
    assert "'new_lows', count(*) FILTER (WHERE hl_eligible AND l0 <= lmin_252)" in code


def test_advances_declines_compare_with_the_previous_session():
    code = _norm(_code())
    assert "max(d.close) FILTER (WHERE w.idx = 1) AS c1" in _norm(_cte("px"))
    for key, cmp in (("advances", "c0 > c1"), ("declines", "c0 < c1"), ("unchanged", "c0 = c1")):
        assert f"'{key}', count(*) FILTER (WHERE c1 IS NOT NULL AND {cmp})" in code
    assert "'no_prior', count(*) FILTER (WHERE c1 IS NULL)" in code


# ----------------------------------------------------------------------------------------------------------- stages

def test_stage_smas_use_the_pinned_session_offsets():
    px = _norm(_cte("px"))
    assert "avg(d.close) FILTER (WHERE w.idx BETWEEN 0 AND 149) AS sma_now" in px
    assert "avg(d.close) FILTER (WHERE w.idx BETWEEN 20 AND 169) AS sma_20" in px
    assert "avg(d.close) FILTER (WHERE w.idx BETWEEN 60 AND 209) AS sma_60" in px
    assert "count(*) FILTER (WHERE w.idx BETWEEN 0 AND 209) AS n_210" in px


def test_stage_thresholds_and_mapping():
    st = _norm(_cte("st"))
    assert "WHEN p.c0 IS NULL OR p.n_210 < 203 OR NULLIF(p.sma_20, 0) IS NULL THEN NULL" in st
    assert "WHEN p.sma_now / p.sma_20 - 1 > 0.01 THEN CASE WHEN p.c0 >= p.sma_now THEN 2 ELSE 3 END" in st
    assert "WHEN p.sma_now / p.sma_20 - 1 < -0.01 THEN CASE WHEN p.c0 <= p.sma_now THEN 4 ELSE 1 END" in st
    assert "WHEN p.sma_now > p.sma_60 THEN 3 ELSE 1 END AS stage" in st


def test_stage_counts_partition_the_universe():
    """1 + 2 + 3 + 4 + unstaged == universe.n — all five are counted over `uni`, and `unstaged` is stage IS NULL."""
    code = _norm(_code())
    m = re.search(r"'stages', \( SELECT json_build_object\((.*?)\) FROM uni\)", code)
    assert m, "stages must be counted over uni (the universe), nothing else"
    body = m.group(1)
    for s in "1234":
        assert f"'{s}', count(*) FILTER (WHERE stage = {s})" in body
    assert "'unstaged', count(*) FILTER (WHERE stage IS NULL)" in body
    assert "'universe', json_build_object('n', (SELECT count(*) FROM uni))" in code


# ----------------------------------------------------------------------------------------------------------- themes

def test_active_themes_take_the_latest_row_first_then_drop_retired():
    """get_active_themes' shape: Retired is dropped AFTER the DISTINCT ON, or a fresh retirement resurrects (#214)."""
    latest = _norm(_cte("theme_latest"))
    assert "SELECT DISTINCT ON (name)" in latest
    assert "WHERE theme_date >= (SELECT as_of FROM k) - 7" in latest
    assert "ORDER BY name, theme_date DESC, id DESC" in latest
    assert "Retired" not in latest, "filtering Retired inside the DISTINCT ON resurrects freshly retired themes"
    assert "WHERE l.stage <> 'Retired'" in _cte("themes_idx")


def test_one_theme_ordering_feeds_both_the_array_and_the_stock_indexes():
    assert "(row_number() OVER (ORDER BY l.name) - 1)::int AS idx" in _norm(_cte("themes_idx"))
    assert "FROM themes_idx ti" in _cte("members")
    code = _norm(_code())
    assert ") ORDER BY ti.idx), '[]'::json) FROM themes_idx ti" in code
    assert "array_agg(idx ORDER BY idx) AS idxs FROM members" in _norm(_cte("member_of"))


def test_e_code_uses_the_theme_exports_join():
    assert "LEFT JOIN mi_theme_ecosystems e ON e.theme_name = l.name" in _cte("themes_idx")


@pytest.mark.parametrize("window,base", [("1d", "c1"), ("5d", "c5"), ("21d", "c21"), ("ytd", "c_ytd")])
def test_theme_returns_are_equal_weighted_with_their_count(window, base):
    tr = _norm(_cte("theme_ret"))
    assert re.search(rf"round\(avg\(\(p\.c0 / p\.{base} *- 1\) \* 100\)::numeric, 2\) AS ret_{window}\b", tr)
    assert re.search(rf"count\(p\.c0 / p\.{base}\) *AS n_{window}\b", tr)


def test_return_bases_sit_on_the_pinned_sessions():
    px = _norm(_cte("px"))
    for n in (0, 1, 5, 21):
        assert f"max(d.close) FILTER (WHERE w.idx = {n}) AS c{n}" in px
    assert "(array_agg(d.close ORDER BY w.idx) FILTER (WHERE w.idx >= k.pye_idx))[1] AS c_ytd" in px
    k = _norm(_cte("k"))
    assert k.count("make_date(extract(year FROM (SELECT trade_date FROM sess WHERE idx = 0))::int, 1, 1)") == 2


def test_usable_score_date_is_the_theme_exports_rule_verbatim():
    """rs_rank reads the same 'newest full RS run' day as the theme export; a drift would let the two pages disagree."""
    def body(sql: str) -> str:
        m = re.search(r"usable_score_date AS \((.*?)\n\)", _strip_comments(sql), re.S)
        assert m
        return _norm(m.group(1))
    assert body(SQL_PATH.read_text()) == body(THEME_SQL_PATH.read_text())


# ------------------------------------------------------------------------------------------- the shell: behaviour
# Both the guard and the untracked-file detection were seen to FAIL these tests when mutated (an unguarded breadth
# line under `set -e`; `git diff --quiet` in place of `git status --porcelain`) before the real script was restored.

_FAKE_DOCKER = r"""#!/bin/sh
# Fake `docker exec ... psql -f -`: the SQL arrives on stdin. Breadth behaviour is set by FAKE_BREADTH.
sql="$(cat)"
case "$sql" in
  *export_breadth_snapshot*)
    echo "breadth: $*" >> "$FAKE_DOCKER_LOG"
    case "${FAKE_BREADTH:-ok}" in
      fail)  echo "ERROR:  relation does not exist" >&2; exit 3 ;;
      short) printf '{}\n'; exit 0 ;;
      ok)    printf '{"breadth": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0; exit 0 ;;
    esac ;;
  *export_theme_snapshot*)
    if [ "${FAKE_THEMES:-ok}" = fail ]; then echo "ERROR: boom" >&2; exit 2; fi
    printf '{"themes": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0 ;;
  *)
    printf '{"other": "%s", "pad": "%0250d"}\n' "${FAKE_NONCE:-n}" 0 ;;
esac
"""


def _git(cwd: Path, *args: str, env: dict) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def rig(tmp_path):
    """A bare 'portfolio-app2' remote holding the three snapshots, a clone the script works in, a fake docker."""
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("needs git and bash")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    remote, seed, dest, bin_dir = (tmp_path / n for n in ("remote.git", "seed", "dest", "bin"))
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote), env=env)
    _git(tmp_path, "clone", "-q", str(remote), str(seed), env=env)
    for f in THREE:
        (seed / f).write_text('{"seed": true}\n')
    _git(seed, "add", *THREE, env=env)
    _git(seed, "commit", "-q", "-m", "seed", env=env)
    _git(seed, "push", "-q", "origin", "HEAD:main", env=env)
    _git(tmp_path, "clone", "-q", str(remote), str(dest), env=env)
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(_FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    env.update(PATH=f"{bin_dir}{os.pathsep}{env['PATH']}", APOLLO_DIR=str(REPO), EXPORT_DIR=str(dest),
               FAKE_DOCKER_LOG=str(tmp_path / "docker.log"))

    def run(**fake):
        e = {**env, **fake}
        return subprocess.run(["bash", str(SHELL_PATH)], env=e, capture_output=True, text=True)

    def published(name: str) -> str | None:
        r = subprocess.run(["git", "show", f"main:{name}"], cwd=remote, env=env, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def seed_breadth(text: str):
        (seed / BREADTH).write_text(text)
        _git(seed, "pull", "-q", "--rebase", "origin", "main", env=env)
        _git(seed, "add", BREADTH, env=env)
        _git(seed, "commit", "-q", "-m", "seed breadth", env=env)
        _git(seed, "push", "-q", "origin", "HEAD:main", env=env)

    return run, published, seed_breadth, dest


def test_a_new_breadth_file_alone_is_a_change(rig):
    """The three unchanged + breadth published for the first time: only an UNTRACKED file differs. `git diff --quiet`
    would report 'no change' here and the breadth page would never get its first file."""
    run, published, _, _ = rig
    assert run(FAKE_NONCE="g", FAKE_BREADTH="fail").returncode == 0      # the three land, breadth does not
    assert published(BREADTH) is None
    r = run(FAKE_NONCE="g", FAKE_BREADTH="ok")                            # same three, breadth now succeeds
    assert r.returncode == 0, r.stderr
    assert "no snapshot change" not in r.stdout
    assert '"breadth": "g"' in (published(BREADTH) or "")


def test_a_failing_breadth_export_never_blocks_the_three(rig):
    run, published, seed_breadth, dest = rig
    seed_breadth('{"breadth": "OLD"}\n')
    r = run(FAKE_NONCE="b", FAKE_BREADTH="fail")
    assert r.returncode == 0, r.stderr
    assert "breadth export FAILED" in r.stderr
    for f in THREE:
        assert '"b"' in published(f), f"{f} was not refreshed because breadth failed"
    assert published(BREADTH) == '{"breadth": "OLD"}\n', "a failed run must leave the published breadth file alone"
    assert not (dest / f"{BREADTH}.tmp").exists()


def test_breadth_psql_stops_on_a_sql_error_and_carries_a_statement_timeout(rig, tmp_path):
    """Without ON_ERROR_STOP, psql exits 0 on a SQL error with empty output; the flag makes the failure an exit code.
    The statement timeout makes a hung breadth query end (non-zero exit, handled by the guard) instead of holding up
    the other three snapshots, which commit after it (review 2026-11-04: a lock on mi_daily_closes hung it)."""
    run, _, _, _ = rig
    assert run(FAKE_NONCE="h").returncode == 0
    calls = (tmp_path / "docker.log").read_text().splitlines()
    assert calls, "the breadth export was never called"
    for c in calls:
        assert "-v ON_ERROR_STOP=1" in c, c
        assert "statement_timeout=" in c, c


def test_a_truncated_breadth_export_is_not_published(rig):
    run, published, _, dest = rig
    r = run(FAKE_NONCE="c", FAKE_BREADTH="short")
    assert r.returncode == 0, r.stderr
    assert "truncated" in r.stderr
    for f in THREE:
        assert '"c"' in published(f)
    assert published(BREADTH) is None, "a 3-byte breadth file must never be published"
    assert not (dest / BREADTH).exists() and not (dest / f"{BREADTH}.tmp").exists()


def test_the_three_still_abort_all_or_nothing(rig):
    """Unchanged behaviour: one of the three failing exits non-zero and pushes nothing (breadth included)."""
    run, published, _, _ = rig
    r = run(FAKE_NONCE="d", FAKE_THEMES="fail", FAKE_BREADTH="ok")
    assert r.returncode != 0
    assert published(THREE[0]) == '{"seed": true}\n'
    assert published(BREADTH) is None


def test_an_unchanged_night_pushes_nothing(rig):
    run, published, _, _ = rig
    assert run(FAKE_NONCE="e").returncode == 0
    r = run(FAKE_NONCE="e")
    assert r.returncode == 0, r.stderr
    assert "no snapshot change" in r.stdout
