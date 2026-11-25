"""FAST's blocking static checks run on every push and before every release build.

The 0.3.0 release candidate passed every test but failed FAST on formatting and
a scanner warning, because FAST was first run after the draft was signed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _script():
    spec = importlib.util.spec_from_file_location(
        "fast_static_checks", ROOT / "scripts/fast_static_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_runs_every_fast_blocking_command_except_ci_pytest_groups():
    sys.path.insert(0, str(ROOT / "engineering-quality"))
    from quality_harness.release_gate import FAST_REQUIRED_COMMANDS
    from quality_harness.static_analysis import tool_commands

    script = _script()
    names = [name for name, _ in script.selected_commands("python")]
    assert set(names) == set(FAST_REQUIRED_COMMANDS) - set(script.PYTEST_GROUPS)
    # Exactly FAST's own invocations, not a separately maintained copy.
    fast = {name: cmd for name, cmd, _ in tool_commands("python")}
    for name, command in script.selected_commands("python"):
        assert command == fast[name]


def _workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def _runs_script(job):
    return any(
        "scripts/fast_static_checks.py" in str(step.get("run", ""))
        for step in job["steps"]
    )


def test_tests_workflow_runs_fast_static_checks_on_every_push():
    jobs = _workflow("tests.yml")["jobs"]
    assert _runs_script(jobs["fast-static"])
    assert "if" not in jobs["fast-static"]


def test_release_builds_wait_for_fast_static_checks():
    jobs = _workflow("release.yml")["jobs"]
    assert _runs_script(jobs["fast-static"])
    for name in ("windows", "macos"):
        assert jobs[name]["needs"] == "fast-static"
        # A failed check stops the build; only QA artifact builds skip it.
        assert "needs.fast-static.result != 'failure'" in jobs[name]["if"]
    assert jobs["fast-static"]["if"] == "${{ !inputs.artifacts_only }}"
