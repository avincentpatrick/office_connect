"""Malware scanner seam — injectable and fail-closed.

The pipeline never trusts a file until a scanner returns ``clean``. Three
concretions, selected like the email driver factory:
- ``NullScanner`` — the fail-safe when no ClamAV is configured: it returns
  ``error`` in production (no verdict = untrusted → download stays denied) and
  ``clean`` in dev/test (so the pipeline round-trips without a 3 GB daemon).
- ``ClamAVScanner`` — streams the bytes to a ClamAV daemon (``clamd`` is
  lazy-imported); FOUND → ``infected(signature)``, OK → ``clean``, socket error →
  ``error``.
- ``get_scanner`` — ``clamav`` when ``clamav_host`` is set (or ``ATTACHMENT_SCANNER``
  forces it), else ``null``.

ClamAV joins the compose stack behind a profile; the QA gate proves the
fail-closed path by injecting an infected scanner, no live daemon needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from office_connect.core.attachments.errors import AttachmentError
from office_connect.core.config import Settings, get_settings


@dataclass(frozen=True)
class ScanResult:
    status: str  # 'clean' | 'infected' | 'error'
    signature: str | None
    scanner_name: str


class Scanner(ABC):
    name: str = "base"

    @abstractmethod
    def scan(self, data: bytes) -> ScanResult:
        ...


class NullScanner(Scanner):
    """No real scanner configured. Fail-closed: untrusted in production."""

    name = "null"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def scan(self, data: bytes) -> ScanResult:
        if self._settings.app_env == "production":
            return ScanResult("error", "no-scanner-configured", "null-prod")
        return ScanResult("clean", None, "null-dev")


class ClamAVScanner(Scanner):
    """Streams bytes to a ClamAV daemon via INSTREAM. clamd is lazy-imported."""

    name = "clamav"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.clamav_host:
            raise AttachmentError("clamav_host is not configured")
        self._host = settings.clamav_host
        self._port = settings.clamav_port

    def scan(self, data: bytes) -> ScanResult:
        import clamd  # lazy — pure-Python, only needed when ClamAV is enabled

        try:
            client = clamd.ClamdNetworkSocket(host=self._host, port=self._port)
            verdict = client.instream(_bytes_io(data))["stream"]
        except Exception as exc:  # socket/daemon failure → fail-closed 'error'
            return ScanResult("error", f"scan-failed: {exc}", "clamav")
        status, signature = verdict[0], verdict[1]
        if status == "OK":
            return ScanResult("clean", None, "clamav")
        if status == "FOUND":
            return ScanResult("infected", signature, "clamav")
        return ScanResult("error", f"unexpected verdict {status}", "clamav")


def _bytes_io(data: bytes):
    from io import BytesIO

    return BytesIO(data)


def get_scanner(settings: Settings | None = None) -> Scanner:
    settings = settings or get_settings()
    name = (
        settings.attachment_scanner
        or ("clamav" if settings.clamav_host else "null")
    ).lower()
    if name == "clamav":
        return ClamAVScanner(settings)
    if name == "null":
        return NullScanner(settings)
    raise AttachmentError(f"unknown attachment_scanner {settings.attachment_scanner!r}")
