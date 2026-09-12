"""Day-99 follow-up: a shadow layer must not be able to lose the whole day.

THE DEFECT. The day-99 merge added `openai`, `socksio`,
`adapters.deepseek_adapter` and `factor_inputs` to `runtime_check.REQUIRED`.
`morning.sh` exits 1 the moment `runtime_check` returns non-zero, BEFORE
acquisition — so on any host whose `.venv` predated that merge there would have
been no board, no ledger row and no email at all, because an unadopted research
module's SDK was missing. `brief.compute` already wraps the DeepSeek read in a
recorded-error path and degrades to UNAVAILABLE; the import gate made that
degradation unreachable.

The fix is not to stop checking. It is to separate what the report CANNOT run
without from what it is designed to degrade around, and to keep counting and
naming the optional failures (house rule 1) instead of blocking on them.

THE OTHER DEFECT, same merge. `prepare_deepseek.py` writes the snapshot the
09:46 path reads, and NOTHING ran it — RUNBOOK said preparation "may" run it
and no unit did. `load_prepared` is a pure reader, so the factor section would
have read "Assessment unavailable" every morning while looking installed. Same
shape as the intraday cache that was staged only by an ignored ExecStartPre.
"""
import datetime as dt
import os
import re
import subprocess

import runtime_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(ROOT, "deploy")


def unit(name):
    return open(os.path.join(DEPLOY, name)).read()


def directives(name):
    """Unit directives only — a grep over the whole file fires on its comments."""
    return "\n".join(l for l in unit(name).splitlines()
                     if not l.lstrip().startswith("#"))


# ── the import gate ────────────────────────────────────────────────────────

def test_the_factor_layer_is_not_a_required_import():
    """Every one of these is reachable only through code that already degrades."""
    for module in ('openai', 'socksio', 'adapters.deepseek_adapter', 'factor_inputs'):
        assert module not in runtime_check.REQUIRED, \
            f"{module} blocks the 09:46 report on an unadopted shadow layer"
        assert module in runtime_check.OPTIONAL


def test_the_report_still_cannot_run_without_its_real_dependencies():
    """The gate must not have been loosened into uselessness."""
    for module in ('pandas', 'numpy', 'brief', 'pandas_market_calendars'):
        assert module in runtime_check.REQUIRED


def test_a_missing_optional_module_is_ready_but_degraded(monkeypatch):
    def fake(name):
        if name in runtime_check.OPTIONAL:
            raise ModuleNotFoundError(name)
        return None
    monkeypatch.setattr(runtime_check.importlib, 'import_module', fake)
    result = runtime_check.check()
    assert result['status'] == 'READY'
    assert result['degraded'] is True
    assert not result['failures']
    assert {f['module'] for f in result['optional_failures']} == set(runtime_check.OPTIONAL)


def test_an_optional_failure_is_named_not_swallowed(monkeypatch):
    """House rule 1. Degrading is allowed; going quiet about it is not."""
    monkeypatch.setattr(runtime_check.importlib, 'import_module',
                        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name))
                        if name == 'openai' else None)
    result = runtime_check.check()
    failure = [f for f in result['optional_failures'] if f['module'] == 'openai']
    assert len(failure) == 1
    assert failure[0]['error'] == 'ModuleNotFoundError'
    assert failure[0]['degrades'], "a named failure with no consequence stated"


def test_a_missing_required_module_still_fails_the_host(monkeypatch):
    monkeypatch.setattr(runtime_check.importlib, 'import_module',
                        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name))
                        if name == 'pandas' else None)
    result = runtime_check.check()
    assert result['status'] == 'NOT READY'
    assert runtime_check.exit_code(result) == 2


def test_degraded_exits_zero():
    """THE RULE morning.sh reads. A non-zero here costs the day's record."""
    assert runtime_check.exit_code({'status': 'READY', 'degraded': True}) == 0
    assert runtime_check.exit_code({'status': 'NOT READY', 'degraded': True}) == 2


def test_the_real_check_on_this_checkout_does_not_block(tmp_path):
    """End to end, as morning.sh runs it: required imports resolve here, so the
    process must exit 0 whatever the optional ones do."""
    done = subprocess.run(['python', os.path.join(ROOT, 'runtime_check.py')],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert '"status": "READY"' in done.stdout


# ── morning.sh must act on the distinction ─────────────────────────────────

def morning_code():
    out = []
    for line in open(os.path.join(ROOT, "morning.sh")).read().splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        out.append(line)
    return "\n".join(out)


def test_the_wrapper_reports_degradation_and_keeps_going():
    code = morning_code()
    assert '"degraded": true' in code, "the wrapper never looks at the degraded flag"
    branch = code[code.index('"degraded": true'):]
    branch = branch[:branch.index('\nfi')]
    assert 'exit' not in branch, \
        "morning.sh exits on a DEGRADED runtime; that is the bug being fixed"
    assert 'RUNTIME DEGRADED' in branch, "degradation must reach the cron mail"


def test_the_wrapper_still_stops_on_a_required_import_failure():
    code = morning_code()
    i = code.index('runtime imports failed before report acquisition')
    assert 'exit 1' in code[i:i + 120]


# ── something must actually stage the snapshot ─────────────────────────────

def test_a_unit_actually_prepares_the_deepseek_snapshot():
    owners = [n for n in os.listdir(DEPLOY)
              if n.endswith(".service") and "prepare_deepseek.py" in directives(n)]
    assert owners == ["rb-deepseek.service"], owners


def test_preparation_is_staged_inside_the_window_load_prepared_accepts():
    """`deepseek_factors.load_prepared` rejects a snapshot prepared at or after
    09:30 and one older than MAX_SNAPSHOT_AGE_HOURS. A timer outside that
    window writes a file the report is guaranteed to throw away."""
    import deepseek_policy as P
    m = re.search(r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit("rb-deepseek.timer"))
    start = dt.time(*(int(g) for g in m.groups()))
    assert start < dt.time(9, 30), f"snapshot prepared at {start} is rejected on read"
    prepare = dt.time(*(int(g) for g in re.search(
        r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit("rb-prepare.timer")).groups()))
    assert prepare < start, "staged technicals must exist before the prompt describes them"
    report = dt.time(*(int(g) for g in re.search(
        r"OnCalendar=.*?(\d{2}):(\d{2}):(\d{2})", unit("rb-report.timer")).groups()))
    age_hours = ((dt.datetime.combine(dt.date(2026, 1, 1), report) -
                  dt.datetime.combine(dt.date(2026, 1, 1), start)).total_seconds() / 3600)
    assert age_hours <= P.MAX_SNAPSHOT_AGE_HOURS, \
        f"snapshot is {age_hours:.1f}h old at report time; the reader caps it"


def test_the_preparation_unit_carries_no_credential():
    s = unit("rb-deepseek.service")
    assert "EnvironmentFile" in s
    assert "DEEPSEEK_API_KEY=" not in s
    assert not re.search(r"sk-[A-Za-z0-9]{8,}", s)


def test_the_preparation_unit_does_not_hide_a_failed_preparation():
    """prepare_deepseek exits 2 on PARTIAL/UNAVAILABLE. A `-` prefix here would
    be the rb-biotech mistake again: a shadow section that reports nothing
    while its unit shows green."""
    for line in directives("rb-deepseek.service").splitlines():
        if line.startswith(("ExecStart=", "ExecStartPre=")):
            assert not line.split("=", 1)[1].lstrip().startswith("-"), line


def test_the_installer_manages_the_new_timer():
    """An installed-but-unlisted timer is never enabled and never verified."""
    s = open(os.path.join(DEPLOY, "install.sh")).read()
    assert "rb-deepseek" in s
    assert re.search(r"^TIMERS=\(.*rb-deepseek.*\)$", s, re.M)


def test_the_installer_proves_the_venv_can_import_not_merely_exist():
    """The venv outlives merges of requirements.txt; `-x` on the interpreter
    says nothing about whether the day-99 dependencies were ever installed."""
    s = open(os.path.join(DEPLOY, "install.sh")).read()
    assert "runtime_check.py" in s
    assert "requirements.txt" in s


def test_the_runbook_schedules_the_preparation_step():
    book = open(os.path.join(ROOT, "RUNBOOK.md")).read()
    assert "rb-deepseek.timer" in book
    row = [l for l in book.splitlines() if "rb-deepseek.timer" in l and l.startswith("|")]
    assert row, "the operating calendar does not list the step"
