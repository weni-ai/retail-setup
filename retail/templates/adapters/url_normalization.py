"""URL normalization helpers for WhatsApp template URL buttons.

Single source of truth shared by the push-path ``ButtonTransformer``
and the fetch-path Direct Send adapter; both paths agree on a single
heuristic so ``metadata.buttons[*].url`` stores one canonical shape.
Anchor: FR-003f.
"""


PLACEHOLDER_PATTERN = "{{1}}"


def ensure_protocol(url: str) -> str:
    """Add ``https://`` prefix when ``url`` lacks an HTTP scheme.

    Empty values pass through unchanged so callers can use the helper
    as a no-op on absent inputs.
    """
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def append_placeholder_if_needed(url: str) -> str:
    """Append ``{{1}}`` to ``url`` when it carries no placeholder yet."""
    if PLACEHOLDER_PATTERN in url:
        return url
    return url + PLACEHOLDER_PATTERN


def looks_like_url(value: str) -> bool:
    """Return True when ``value`` resembles an HTTP URL.

    Heuristic: explicit ``http(s)://`` scheme OR a string carrying both
    a ``.`` and a ``/``. Lets push-path identifier examples like
    ``"123"`` pass through ``normalize_url_if_needed`` unchanged.
    """
    if not value:
        return False
    if value.startswith(("http://", "https://")):
        return True
    return "." in value and "/" in value


def normalize_url_if_needed(value: str) -> str:
    """Apply ``ensure_protocol`` only when ``value`` resembles a URL."""
    if looks_like_url(value):
        return ensure_protocol(value)
    return value
