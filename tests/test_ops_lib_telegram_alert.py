"""#121 — the host-cron shell sender (`infra/ops_lib.sh::telegram_alert`) is on the HTML layer.

THE HOLE THIS CLOSES. The #121 census walked `agents/ core/ channels/ shared/` (Python) and declared
the migration done while `infra/ops_lib.sh` was still POSTing `parse_mode=Markdown` through curl.
That one function carries every host-side page the operator gets when the box itself is in trouble:
`backup failed`, `secrets backup failed`, `gdrive OAuth expired`, `Service DOWN / STILL DOWN /
recovered`, `Disk space HIGH / CRITICAL`, `restore-check FAILED` (scripts/backup.sh,
infra/service_watchdog.sh, infra/staging_restore_check.sh). Raw psql / docker error text carries
`_`, `*`, `<`, `&` - the exact bytes that 400 the legacy parser.

These tests run the REAL `ops_lib.sh` under bash with a fake `curl` on PATH that records the argv it
was called with (NUL-separated: the `text=` element has embedded newlines), so they assert on what
would have gone over the wire - the parse mode, the escaped text, the plain-text retry - not on a
re-implementation. `test_the_real_watchdog_down_page_...` goes one level up and drives the real
`service_watchdog.sh` into its DOWN branch.

MUTATIONS (each run RED by hand 2026-10-01): `parse_mode=HTML` -> `parse_mode=Markdown` in
`telegram_alert` fails the parse-mode and escaping tests; deleting the `_tg_escape` pass fails the
escaping test; deleting the second curl (the plain retry) fails the retry test.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_service_watchdog_532 import (
    FAKE_DOCKER,
    FAKE_FLOCK,
    FAKE_TIMEOUT,
    OPS_LIB_SRC,
    SVC,
    WATCHDOG_SRC,
    _make_app_dir,
    _run,
    _write_exec,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_CURL_CAPTURE = r"""#!/usr/bin/env bash
# Fake `curl` for test_ops_lib_telegram_alert.py: record argv (NUL-separated, one record per
# call), then exit with the Nth code of FAKE_CURL_RCS (the last one repeats). A non-zero exit
# prints curl's own -f message on stderr, like the real thing on an HTTP 400.
printf '%s\0' "$@" >> "$FAKE_CURL_CAPTURE"
printf '===CALL===\0' >> "$FAKE_CURL_CAPTURE"
n=0
[ -f "$FAKE_CURL_COUNTER" ] && n=$(cat "$FAKE_CURL_COUNTER")
n=$((n + 1))
echo "$n" > "$FAKE_CURL_COUNTER"
rcs="${FAKE_CURL_RCS:-0}"
rc=$(echo "$rcs" | cut -d, -f"$n")
[ -z "$rc" ] && rc=$(echo "$rcs" | awk -F, '{print $NF}')
if [ "$rc" != "0" ]; then
    echo "curl: (22) The requested URL returned error: 400" >&2
fi
exit "$rc"
"""


@pytest.fixture
def curl_env(tmp_path):
    """(fake_bin, capture_file, counter_file): fake docker/timeout/flock plus the recording curl."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "docker", FAKE_DOCKER)
    _write_exec(bin_dir / "timeout", FAKE_TIMEOUT)
    _write_exec(bin_dir / "flock", FAKE_FLOCK)
    _write_exec(bin_dir / "curl", FAKE_CURL_CAPTURE)
    return bin_dir, tmp_path / "curl_calls.bin", tmp_path / "curl_counter"


def _env(curl_env, rcs: str = "0", *, creds: bool = True) -> dict:
    bin_dir, capture, counter = curl_env
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": os.environ.get("HOME", "/tmp"),
        "FAKE_CURL_CAPTURE": str(capture),
        "FAKE_CURL_COUNTER": str(counter),
        "FAKE_CURL_RCS": rcs,
        "LOG_FILE": str(capture.parent / "ops.log"),
    }
    if creds:
        env["TELEGRAM_BOT_TOKEN"] = "123:FAKE"
        env["TELEGRAM_ALLOWED_USER_IDS"] = "42,43"
    return env


def _calls(capture: Path) -> list[dict]:
    """Every curl invocation as {"url": ..., "fields": {k: v of each --data-urlencode}}."""
    if not capture.exists():
        return []
    out = []
    for rec in capture.read_bytes().split(b"===CALL===\x00"):
        args = [a.decode("utf-8") for a in rec.split(b"\x00")][:-1] if rec else []
        if not args:
            continue
        fields = {}
        for i, a in enumerate(args):
            if a == "--data-urlencode":
                k, _, v = args[i + 1].partition("=")
                fields[k] = v
        out.append({"url": next(a for a in args if a.startswith("https://")), "fields": fields})
    return out


def _alert(curl_env, msg: str, rcs: str = "0", *, creds: bool = True) -> subprocess.CompletedProcess:
    """Source the REAL ops_lib.sh and call telegram_alert "$1"."""
    script = f'source "{OPS_LIB_SRC}"; telegram_alert "$1"'
    return subprocess.run(["bash", "-c", script, "_", msg], env=_env(curl_env, rcs, creds=creds),
                          capture_output=True, text=True, timeout=30)


# The shape every real caller sends: a bold title, a fenced block of dynamic text, a footer.
DOWN_MSG = ("🔴 *Service DOWN: apollo-market*" + "\n```\n"
            + "docker state: exited (psql: relation \"mi_audit_log\" <missing> & dashboard_ro *denied*)"
            + "\n```\n" + "Watchdog re-alerts every 6h while down; recovery is announced.")


# ── 1. the parse mode and the escaping ───────────────────────────────────────────────────────

def test_telegram_alert_posts_html_with_the_text_escaped_and_the_markup_converted(curl_env):
    """MUTATION: `parse_mode=Markdown` back in `telegram_alert` (the pre-fix state) fails the
    parse_mode assertion; removing the `_tg_escape` pass fails the `&lt;` / `&amp;` assertions."""
    r = _alert(curl_env, DOWN_MSG)
    assert r.returncode == 0, r.stderr
    (call,) = _calls(curl_env[1])
    assert call["url"] == "https://api.telegram.org/bot123:FAKE/sendMessage"
    f = call["fields"]
    assert f["parse_mode"] == "HTML"                       # NOT Markdown
    assert f["chat_id"] == "42"                            # first allowed id
    assert f["text"] == (
        "🔴 <b>Service DOWN: apollo-market</b>\n"
        "<pre>docker state: exited (psql: relation \"mi_audit_log\" &lt;missing&gt; "
        "&amp; dashboard_ro *denied*)</pre>\n"
        "Watchdog re-alerts every 6h while down; recovery is announced.")


def test_a_fences_content_is_never_markup_parsed(curl_env):
    """`$prune_out` / psql text carries `*` and backticks; inside the fence they must stay
    literal characters (md_to_html's rule too), outside it they become tags."""
    _alert(curl_env, "*T*\n```\nrows `x` and *y*\n```\nsee `docs/ops.md`")
    (call,) = _calls(curl_env[1])
    assert call["fields"]["text"] == "<b>T</b>\n<pre>rows `x` and *y*</pre>\nsee <code>docs/ops.md</code>"


def test_no_credentials_means_no_send(curl_env):
    r = _alert(curl_env, DOWN_MSG, creds=False)
    assert r.returncode == 0 and _calls(curl_env[1]) == []


# ── 2. the plain-text retry ──────────────────────────────────────────────────────────────────

def test_a_rejected_html_send_is_retried_as_plain_words_with_identifiers_intact(curl_env):
    """MUTATION: deleting the second curl (no retry) leaves ONE call and fails this."""
    r = _alert(curl_env, DOWN_MSG, rcs="22,0")
    assert r.returncode == 0, r.stderr
    first, second = _calls(curl_env[1])
    assert first["fields"]["parse_mode"] == "HTML"
    assert "parse_mode" not in second["fields"]
    assert second["fields"]["chat_id"] == "42"
    assert second["fields"]["text"] == (
        "🔴 Service DOWN: apollo-market\n"
        "docker state: exited (psql: relation \"mi_audit_log\" <missing> & dashboard_ro *denied*)\n"
        "Watchdog re-alerts every 6h while down; recovery is announced.")
    log = Path(curl_env[1].parent / "ops.log").read_text()
    assert "HTML send rejected" in log and "retrying as plain text" in log


def test_when_both_sends_fail_the_failure_is_logged_not_swallowed(curl_env):
    r = _alert(curl_env, "🚨 *Apollo backup FAILED*", rcs="22")
    assert r.returncode == 0                                # never kills a backup script
    assert len(_calls(curl_env[1])) == 2
    log = Path(curl_env[1].parent / "ops.log").read_text()
    assert "telegram_alert send FAILED" in log and "Apollo backup FAILED" in log


# ── 3. every real caller's message converts to well-formed Telegram HTML ─────────────────────

_CALL_RE = re.compile(r'telegram_alert\s+"((?:[^"\\]|\\.)*)"')
_CALLER_FILES = ("scripts/backup.sh", "infra/service_watchdog.sh", "infra/staging_restore_check.sh")


def _caller_messages() -> list[tuple[str, str]]:
    out = []
    for rel in _CALLER_FILES:
        for m in _CALL_RE.finditer((REPO_ROOT / rel).read_text()):
            msg = re.sub(r"\\(.)", r"\1", m.group(1))           # bash \` and \" -> ` and "
            msg = re.sub(r"\$\{?\w+\}?", "x", msg)              # ${svc} etc. -> a stand-in
            out.append((rel, msg))
    return out


def _convert(msg: str) -> str:
    script = f'source "{OPS_LIB_SRC}"; _tg_md_to_html "$1"'
    r = subprocess.run(["bash", "-c", script, "_", msg], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_the_census_of_callers_is_not_vacuous():
    msgs = _caller_messages()
    assert {rel for rel, _ in msgs} == set(_CALLER_FILES), "a caller file has no telegram_alert call"
    assert len(msgs) >= 15, f"only {len(msgs)} call sites found - the extractor went blind"


@pytest.mark.parametrize("rel,msg", _caller_messages(), ids=lambda v: v[:40] if isinstance(v, str) else v)
def test_every_real_caller_message_converts_to_well_formed_html(rel, msg):
    """READ-EVERY-CALLER guard: each message the three host scripts send (first literal; the
    fenced dynamic part is covered above) must come out with balanced tags, no `*`/backtick
    marker left over outside a <pre>, and the same words (tags removed == the original text
    minus its markers)."""
    html = _convert(msg)
    stack = []
    for m in re.finditer(r"<(/?)(b|code|pre)>", html):
        if m.group(1):
            assert stack and stack.pop() == m.group(2), (rel, html)
        else:
            stack.append(m.group(2))
    assert not stack, (rel, html)
    outside = re.sub(r"<pre>.*?</pre>", "", html, flags=re.DOTALL)
    assert "*" not in outside and "`" not in outside, (rel, html)
    assert "<b>" in html, f"{rel}: lost its bold title - {html!r}"
    words = re.sub(r"<[^>]+>", "", html).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    assert words == msg.replace("*", "").replace("`", ""), (rel, words)


# ── 4. one level up: the real watchdog drives the real function ──────────────────────────────

def test_the_real_watchdog_down_page_goes_out_as_html(tmp_path, curl_env):
    """service_watchdog.sh -> telegram_alert -> curl. MUTATION: `parse_mode=Markdown` in ops_lib
    fails `parse_mode`; a caller that stopped fencing its reason fails the <pre> assertion."""
    bin_dir, capture, _counter = curl_env
    app_dir = _make_app_dir(tmp_path)
    env = {k: v for k, v in _env(curl_env).items() if k != "LOG_FILE"}
    _run(WATCHDOG_SRC, bin_dir, app_dir, tmp_path / "state", tmp_path / "watchdog.log",
         {**env, "FAKE_DOCKER_STATUS": "exited"})
    (call,) = _calls(capture)
    assert call["fields"]["parse_mode"] == "HTML"
    text = call["fields"]["text"]
    assert text.startswith(f"🔴 <b>Service DOWN: {SVC}</b>\n<pre>")
    assert "</pre>\nWatchdog re-alerts every 6h while down; recovery is announced." in text
