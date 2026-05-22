"""URL normalization helpers for WhatsApp template URL buttons.

Pure stateless utilities shared by:

- The push-path ``ButtonTransformer``
  (``retail/templates/adapters/template_library_to_custom_adapter.py``),
  which maps Meta's library-catalog buttons to the Integrations Engine
  template-translation payload at push time.
- The fetch-path Direct Send adapter
  (``retail/templates/usecases/_meta_library_template_fetch.py``),
  which normalizes Meta's library-catalog buttons into the local
  ``Template.metadata.buttons`` canonical shape at agent-assignment
  time.

Both paths MUST agree on a single normalization heuristic so
``metadata.buttons[*].url`` stores one canonical shape regardless of
upstream variance (FR-003f). Keeping the helpers in their own module
preserves that single source of truth without coupling either consumer
to the other's class layout.
"""


PLACEHOLDER_PATTERN = "{{1}}"


def ensure_protocol(url: str) -> str:
    """Add ``https://`` prefix when ``url`` lacks an HTTP scheme.

    Empty / ``None`` values pass through unchanged so callers can use
    the helper as a no-op on absent inputs.
    """
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def append_placeholder_if_needed(url: str) -> str:
    """Append ``{{1}}`` to ``url`` when it carries no placeholder yet.

    Collapses the nested ``{base_url, url_suffix_example}`` upstream
    shape and a flat URL that already contains ``{{1}}`` onto the same
    canonical flat-string form (FR-003f).
    """
    if PLACEHOLDER_PATTERN in url:
        return url
    return url + PLACEHOLDER_PATTERN


def looks_like_url(value: str) -> bool:
    """Return True when ``value`` resembles an HTTP URL.

    Heuristic: an explicit ``http(s)://`` scheme OR a string containing
    both a ``.`` and a ``/`` (domain + path indicator). Used to decide
    whether ``ensure_protocol`` should fire on an example/suffix value
    that may be a plain identifier rather than a real URL.
    """
    if not value:
        return False
    if value.startswith(("http://", "https://")):
        return True
    return "." in value and "/" in value


def normalize_url_if_needed(value: str) -> str:
    """Apply ``ensure_protocol`` only when ``value`` resembles a URL.

    Lets push-path examples like ``"123"`` pass through unchanged (they
    are not URLs) while still prepending ``https://`` to genuine URLs
    that are missing the scheme.
    """
    if looks_like_url(value):
        return ensure_protocol(value)
    return value
