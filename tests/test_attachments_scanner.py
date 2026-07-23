"""Increment 4 Group D — the injectable, fail-closed scanner seam."""

from unittest.mock import MagicMock

from office_connect.core.attachments.scanner import (
    ClamAVScanner,
    NullScanner,
    get_scanner,
)
from office_connect.core.config import Settings


def test_null_scanner_fail_closed_in_production():
    result = NullScanner(Settings(app_env="production")).scan(b"anything")
    assert result.status == "error"
    assert result.scanner_name == "null-prod"


def test_null_scanner_passes_in_dev():
    result = NullScanner(Settings(app_env="local")).scan(b"anything")
    assert result.status == "clean"
    assert result.scanner_name == "null-dev"


def test_get_scanner_selection():
    assert get_scanner(Settings()).name == "null"  # no clamav_host
    assert get_scanner(Settings(clamav_host="clamav")).name == "clamav"
    # Explicit override wins.
    assert get_scanner(Settings(attachment_scanner="null", clamav_host="clamav")).name == "null"


def test_clamav_scanner_found(monkeypatch):
    scanner = ClamAVScanner(Settings(clamav_host="clamav"))
    fake = MagicMock()
    fake.instream.return_value = {"stream": ("FOUND", "Eicar-Test-Signature")}
    monkeypatch.setattr(
        "clamd.ClamdNetworkSocket", MagicMock(return_value=fake)
    )
    result = scanner.scan(b"eicar")
    assert result.status == "infected"
    assert result.signature == "Eicar-Test-Signature"


def test_clamav_scanner_ok(monkeypatch):
    scanner = ClamAVScanner(Settings(clamav_host="clamav"))
    fake = MagicMock()
    fake.instream.return_value = {"stream": ("OK", None)}
    monkeypatch.setattr("clamd.ClamdNetworkSocket", MagicMock(return_value=fake))
    assert scanner.scan(b"clean").status == "clean"


def test_clamav_scanner_socket_error_is_fail_closed(monkeypatch):
    scanner = ClamAVScanner(Settings(clamav_host="clamav"))
    fake = MagicMock()
    fake.instream.side_effect = ConnectionRefusedError("no daemon")
    monkeypatch.setattr("clamd.ClamdNetworkSocket", MagicMock(return_value=fake))
    result = scanner.scan(b"x")
    assert result.status == "error"
