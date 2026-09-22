"""Native child arguments and process-local macOS initialization."""

import json
import subprocess
import sys

import pytest
from quality_harness.native_process import native_python_command


@pytest.mark.parametrize("value", ["plain", "folder with spaces", "-looks-like-option"])
def test_native_child_preserves_data_argument_and_starts(value):
    script = "import json,sys; print(json.dumps({'value':sys.argv[1]}))"
    if sys.platform == "darwin":
        script = (
            "import json,sys; from Foundation import NSUserDefaults; "
            "defaults=NSUserDefaults.standardUserDefaults(); "
            "assert defaults.boolForKey_('ApplePersistenceIgnoreState'); "
            "assert not defaults.boolForKey_('NSQuitAlwaysKeepsWindows'); "
            "print(json.dumps({'value':sys.argv[1]}))"
        )
    result = subprocess.run(
        native_python_command(script, [value]),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["value"] == value
