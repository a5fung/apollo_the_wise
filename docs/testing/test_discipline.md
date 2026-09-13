# Test discipline — new file vs. extend existing, and source pins

SSoT for two related test-suite-hygiene rules. Registered in `docs/SSoT.md`.

## 1. New test file vs. extend an existing one

**Measured 2026-09-12: 79 of 481 test files are named for a single task number**
(`test_508_*.py`, `test_545_*.py`, ...). The working pattern has been **"new task, new file,"**
never **"does this already have coverage."** That is why the suite tripled in five months
(112 functions on 2026-04-01 → 5,881 by 2026-09-12) without becoming easier to navigate: a
behavior can end up spread across three or four task-numbered files instead of living in one
place next to the code it tests.

**The rule: default is to EXTEND the existing file for the module/behavior under test.**
Before creating a new test file, run one grep:

```
grep -l '<module_or_function_name>' tests/test_*.py
```

If a file already exercises that module — add to it. A new task touching an existing module is
new *test functions* in an existing *file*, not a new file.

**A new file is justified only for one of these (closed list):**

1. **The module/behavior genuinely has no test file yet.** First coverage of `foo.py` is
   `test_foo.py` (or the behavior it implements, if the module is a grab-bag) — not
   `test_612_foo_thing.py`.
2. **New, free-standing test infrastructure** — a gate's own regression tests (this file's own
   companion, `tests/test_check_test_source_pins.py`, is an example: it tests a new script, not
   an existing one).
3. **A deliberate topical split of an existing file that has grown past being navigable** — rare,
   and done as its own reviewed step, never as a side effect of an unrelated task.

**Not a reason:** "this is task #NNN." The task number is where the change came from, not what
it tests — it belongs in the docstring and the commit message, never the filename. Naming a file
for a task number is *exactly* how the same behavior ends up checked in four different places
and none of them gets extended, because nobody thought to look there.

**Naming going forward:** name the file for the module or behavior it covers
(`test_entry_pipeline_dedup.py`, `test_theme_engine_retirement.py`), not the task that produced
the change. If a task genuinely needs its own scratch file for something with no natural home
yet (reason 1 above), name it for what it tests, not for the ticket.

## 2. Source pins are a last resort, not a default

`scripts/check_test_source_pins.py` (pre-commit Gate 7, `.githooks/pre-commit`) blocks any NEW or
EDITED test that asserts on the literal SOURCE TEXT of a module under `agents/ scripts/ channels/
core/ shared/` — `inspect.getsource(...)`, `<path>.read_text()`, `open("agents/...")` — instead
of on what the code *does*. Measured 2026-09-12: 285 of 5,881 test functions did this, and 32
broke the same day against a refactor that changed no behavior at all (a bare Markdown send
becoming `send_telegram_message(md_to_html(text), parse_mode="HTML")`). A test that blocks a safe
refactor and still misses a real defect (see #649 the same week: 20 green tests, dead repair
code) is paying twice for nothing.

**Prefer, in this order:**

1. **Call the function and assert on its return value / side effect** (a DB row written, a
   Telegram payload shape, a raised exception). This is the only kind of test that catches a real
   behavioral regression AND survives a refactor that doesn't change behavior.
2. **If the thing you actually need to check is that a correct function is CALLED from a specific
   place** (a scheduler wiring, a slash-command registration, a sender migrated to a new call
   shape) — a source pin can be the right tool. This repo has been burned by the opposite failure
   too: a correct helper nobody called. A wiring check is not automatically wrong.
3. If you do write one, mark it reviewed: `# source-pin-ok: <why behaviour cannot be exercised
   here>`. The reason is the point — it is what turns "we didn't think about it" into "we decided
   this, and here is why."

The existing 285 are a surfaced backlog, not a wall — the gate only judges what a commit adds or
edits. Reducing the backlog is real work when someone picks it up, never a tax on an unrelated
commit that happens to touch the same file.
