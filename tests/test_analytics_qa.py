import json
import uuid

import pytest

from yt_downloader.analytics_qa import validate_qa_receipt


def prepare(tmp_path, monkeypatch):
    label = str(uuid.uuid4())
    monkeypatch.setenv("VODFORGE_POSTHOG_QA_RUN", label)
    monkeypatch.setenv("VODFORGE_POSTHOG_QA_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    (tmp_path / ".vodforge-analytics-qa.json").write_text(
        json.dumps({"qa_run_id": label, "fictional_profile": True})
    )
    return tmp_path / "receipt.json"


def test_qualification_requires_exact_attested_isolated_profile(tmp_path, monkeypatch):
    receipt = prepare(tmp_path, monkeypatch)
    assert validate_qa_receipt(receipt) == receipt
    assert not receipt.exists()  # Validation grants no consent and writes nothing.
    assert not (tmp_path / "settings.json").exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("HOME", "/ordinary-profile"),
        ("LOCALAPPDATA", "/ordinary-profile"),
        ("VODFORGE_POSTHOG_QA_RUN", "private-text"),
        ("QT_QPA_PLATFORM", "cocoa"),
        ("VODFORGE_POSTHOG_QA_HOME", ""),
    ],
)
def test_qualification_refuses_foreground_or_mismatched_context(
    tmp_path, monkeypatch, key, value
):
    receipt = prepare(tmp_path, monkeypatch)
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        validate_qa_receipt(receipt)
    assert not receipt.exists()


def test_qualification_never_overwrites_receipt_or_accepts_redirect(
    tmp_path, monkeypatch
):
    receipt = prepare(tmp_path, monkeypatch)
    receipt.write_text("retained")
    with pytest.raises(ValueError):
        validate_qa_receipt(receipt)
    assert receipt.read_text() == "retained"
    receipt.unlink()
    receipt.symlink_to(tmp_path / "other.json")
    with pytest.raises(ValueError):
        validate_qa_receipt(receipt)
