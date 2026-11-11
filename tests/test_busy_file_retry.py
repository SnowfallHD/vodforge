"""Saved files survive another thread reading them at the same moment.

Windows refuses to replace a file, or to open one being replaced, while another
handle has it open. A CI run caught it: saving installation.json failed while
the telemetry sender read it on another thread, so the installation link never
opened. The concurrent tests below use real threads and files; on Windows they
failed before the retry (over a third of saves in a two-second trial).
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from yt_downloader import private_files
from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    update_onboarding,
)
from yt_downloader.settings_store import load_settings, save_settings


def test_busy_file_is_retried_on_windows(monkeypatch):
    monkeypatch.setattr(private_files, "_ON_WINDOWS", True)
    attempts = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError(13, "in use")
        return "saved"

    assert private_files.retry_while_file_is_busy(operation) == "saved"
    assert len(attempts) == 3


def test_lasting_denial_still_fails_after_the_retry_window(monkeypatch):
    monkeypatch.setattr(private_files, "_ON_WINDOWS", True)
    monkeypatch.setattr(private_files, "BUSY_FILE_RETRY_SECONDS", 0.05)
    started = time.monotonic()

    def denied():
        raise PermissionError(13, "denied")

    with pytest.raises(PermissionError):
        private_files.retry_while_file_is_busy(denied)
    assert time.monotonic() - started < 1


def test_other_errors_and_other_systems_fail_at_once(monkeypatch):
    calls = []

    def fail(exc):
        def operation():
            calls.append(1)
            raise exc

        return operation

    monkeypatch.setattr(private_files, "_ON_WINDOWS", True)
    with pytest.raises(FileNotFoundError):
        private_files.retry_while_file_is_busy(fail(FileNotFoundError(2, "gone")))
    monkeypatch.setattr(private_files, "_ON_WINDOWS", False)
    with pytest.raises(PermissionError):
        private_files.retry_while_file_is_busy(fail(PermissionError(13, "in use")))
    assert len(calls) == 2


def run_together(save, read, seconds=1.0):
    """Save in this thread while another thread reads; collect every error."""
    stop = time.monotonic() + seconds
    errors: list[BaseException] = []
    reads = 0

    def reader():
        nonlocal reads
        while time.monotonic() < stop:
            try:
                read()
                reads += 1
            except Exception as exc:  # noqa: BLE001 - the test reports them all
                errors.append(exc)

    thread = threading.Thread(target=reader)
    thread.start()
    saves = 0
    try:
        while time.monotonic() < stop:
            try:
                save(saves)
                saves += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
    finally:
        thread.join()
    assert not errors, f"{len(errors)} errors, first: {errors[0]!r}"
    assert saves > 10 and reads > 10


def test_installation_state_saves_while_another_thread_reads(tmp_path):
    path = tmp_path / "installation.json"
    install_id = load_or_create_installation_state(path).install_id

    def save(n):
        update_onboarding(path, browser_eligible=n % 2 == 0)

    def read():
        assert load_or_create_installation_state(path).install_id == install_id

    run_together(save, read)


def test_private_documents_save_while_another_thread_reads(tmp_path):
    path = tmp_path / "progress.json"
    private_files.write_private_bytes(path, b'{"n": 0}')

    def save(n):
        private_files.write_private_bytes(path, json.dumps({"n": n}).encode())

    run_together(save, lambda: json.loads(private_files.read_text(path)))


def test_settings_save_while_another_thread_reads(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, {"theme": "violet"})
    run_together(
        lambda n: save_settings(path, {"theme": f"violet-{n}"}),
        lambda: load_settings(path)["theme"],
    )


# safe_output commits media with its own checks; private_files imports it, so it
# can't route through the helper without a circular import.
REPLACE_ALLOWED = {"private_files.py", "safe_output.py"}


def test_app_code_replaces_files_only_through_the_retry_helper():
    """Every other file replace goes through private_files.replace_file.

    A direct os.replace or Path.replace works on macOS and Linux and fails on
    Windows whenever something has the destination open, so this catches the
    pattern where it is written rather than waiting for a rare CI failure.
    """
    import ast
    from pathlib import Path

    package = Path(private_files.__file__).parent
    direct = []
    for source in sorted(package.rglob("*.py")):
        if source.name in REPLACE_ALLOWED:
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "replace"
            ):
                continue
            receiver = node.func.value
            os_replace = isinstance(receiver, ast.Name) and receiver.id == "os"
            # str.replace takes two arguments; Path.replace takes one.
            path_replace = (
                len(node.args) == 1
                and not node.keywords
                and not isinstance(node.args[0], ast.Constant)
            )
            if os_replace or path_replace:
                relative = source.relative_to(package.parent)
                direct.append(f"{relative}:{node.lineno}: {ast.unparse(node)}")
    assert not direct, "use private_files.replace_file:\n" + "\n".join(direct)


def test_background_threads_wait_longer_than_the_ui_thread(monkeypatch):
    """Antivirus held a new file for over a second on Windows CI, past the 1 s
    retry; a background save can wait longer, the UI thread can't."""
    monkeypatch.setattr(private_files, "_ON_WINDOWS", True)
    monkeypatch.setattr(private_files, "BUSY_FILE_RETRY_SECONDS", 0.05)
    monkeypatch.setattr(private_files, "BACKGROUND_BUSY_FILE_RETRY_SECONDS", 1.0)
    gave_up_before = private_files.BUSY_RETRY_GAVE_UP["held.json"]

    def locked_for(seconds):
        until = time.monotonic() + seconds

        def operation():
            if time.monotonic() < until:
                raise PermissionError(13, "Access is denied")
            return "saved"

        return operation

    with pytest.raises(PermissionError):
        private_files.retry_while_file_is_busy(locked_for(0.3), "held.json")
    assert private_files.BUSY_RETRY_GAVE_UP["held.json"] == gave_up_before + 1

    result = []
    worker = threading.Thread(
        target=lambda: result.append(
            private_files.retry_while_file_is_busy(locked_for(0.3), "held.json")
        )
    )
    worker.start()
    worker.join(5)
    assert result == ["saved"]
