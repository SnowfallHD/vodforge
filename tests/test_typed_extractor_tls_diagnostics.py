"""Classify upstream TLS types without message tokens or network requests."""

import json

import pytest
from yt_dlp.networking.exceptions import CertificateVerifyError, SSLError
from yt_dlp.utils import ExtractorError

from yt_downloader.failure_diagnostics import capture_failure


@pytest.mark.parametrize("link", ["cause", "__cause__", "__context__", "exc_info"])
def test_nested_typed_certificate_keeps_code_without_private_text(link):
    inner = CertificateVerifyError("private diagnostic marker")
    outer = ExtractorError("synthetic wrapper")
    setattr(outer, link, (type(inner), inner, None) if link == "exc_info" else inner)
    payload = capture_failure(outer, stage="analysis").payload()
    assert payload["failure_code"] == "tls_certificate"
    assert payload["reason"] == "network"
    assert "private diagnostic marker" not in json.dumps(payload)


def test_typed_generic_tls_is_not_certificate_failure():
    payload = capture_failure(SSLError("synthetic")).payload()
    assert payload["failure_code"] == "tls_handshake"
    assert payload["reason"] == "network"


def test_certificate_subclass_and_cyclic_wrapper_are_bounded():
    class SpecializedCertificateError(CertificateVerifyError):
        pass

    inner = SpecializedCertificateError("synthetic")
    outer = RuntimeError("synthetic wrapper")
    outer.__cause__ = inner
    inner.__cause__ = outer
    assert capture_failure(outer).payload()["failure_code"] == "tls_certificate"


def test_unrelated_same_name_and_unknown_remain_unknown():
    unrelated = type("CertificateVerifyError", (Exception,), {})
    for error in (unrelated("synthetic"), RuntimeError("synthetic")):
        payload = capture_failure(error).payload()
        assert payload["reason"] == "unknown"
        assert "failure_code" not in payload
