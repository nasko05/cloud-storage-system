"""Optional malware scanning via ClamAV.

When ``DRIVE_CLAMAV_ENABLED`` is set, uploaded files are scanned on finalize so
that infected content never lands in storage (and therefore never in backups).
When disabled (the default), scanning is a no-op that reports every file clean,
so the feature adds zero overhead unless explicitly turned on.
"""

from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger("antivirus")


class ScanError(RuntimeError):
    """Raised when scanning is enabled but the scanner is unreachable."""


def scan_file(path) -> tuple[bool, str | None]:
    """Return ``(is_clean, signature)``. ``signature`` names the threat if found."""
    if not settings.clamav_enabled:
        return True, None

    try:
        import clamd
    except ImportError as exc:  # pragma: no cover - only if dep missing
        raise ScanError("clamav is enabled but the 'clamd' package is not installed") from exc

    try:
        client = clamd.ClamdNetworkSocket(host=settings.clamav_host, port=settings.clamav_port)
        with open(path, "rb") as handle:
            result = client.instream(handle)
    except Exception as exc:  # noqa: BLE001 - network/daemon failure
        raise ScanError(f"virus scan failed: {exc}") from exc

    status, signature = result.get("stream", ("ERROR", None))
    if status == "FOUND":
        logger.warning("infected upload rejected: %s", signature)
        return False, signature
    if status == "OK":
        return True, None
    raise ScanError(f"unexpected scan result: {result}")
