import subprocess
from pathlib import Path

from scripts.write_build_revision import source_revision


def test_revision_requires_exact_clean_source(tmp_path: Path):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    assert source_revision(tmp_path) == "unknown"
    git("init", "--quiet")
    git("config", "user.email", "qa@example.invalid")
    git("config", "user.name", "Isolated provenance QA")
    tracked = tmp_path / "source.py"
    tracked.write_text("print(1)")
    git("add", "source.py")
    git("commit", "--quiet", "-m", "fixture")
    expected = git("rev-parse", "HEAD")
    assert source_revision(tmp_path) == expected
    tracked.write_text("print(2)")
    assert source_revision(tmp_path) == "unknown"
    git("checkout", "--", "source.py")
    (tmp_path / "untracked.py").write_text("new code")
    assert source_revision(tmp_path) == "unknown"
