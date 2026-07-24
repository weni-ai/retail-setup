"""Sentry metadata helpers for VTEX IO proxy routes."""

import re
from typing import Any, Dict, List, Optional

_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_LONG_NUMERIC_ID_PATTERN = re.compile(r"/\d{10,}(?:-\d+)?")


def normalize_proxy_path(path: str, *, max_segments: int = 4) -> str:
    """Return a stable route key for Sentry grouping.

    Dynamic segments (UUIDs, order IDs, long numeric IDs) are collapsed so
    failures on the same VTEX API route group together instead of one issue
    per document ID.
    """
    path_only = path.split("?", 1)[0].strip()
    if not path_only:
        return "/"

    normalized = _UUID_PATTERN.sub("{uuid}", path_only)
    normalized = _LONG_NUMERIC_ID_PATTERN.sub("/{id}", normalized)
    segments = [segment for segment in normalized.strip("/").split("/") if segment]
    if not segments:
        return "/"

    return "/" + "/".join(segments[:max_segments])


def build_vtex_io_proxy_sentry_metadata(
    *,
    service: str,
    vtex_account: str,
    method: str,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Sentry tags and fingerprint prefix for VTEX IO proxy calls."""
    normalized_path = normalize_proxy_path(path) if path else None

    fingerprint_prefix: List[str] = [service, method.upper()]
    if normalized_path:
        fingerprint_prefix.append(normalized_path)
    fingerprint_prefix.append(vtex_account)

    tags: Dict[str, Any] = {
        "service": service,
        "error_type": f"{service}_error",
        "vtex_account": vtex_account,
        "http_method": method.upper(),
    }
    if normalized_path:
        tags["proxy_path"] = normalized_path

    return {
        "sentry_tags": tags,
        "sentry_fingerprint_prefix": fingerprint_prefix,
    }
