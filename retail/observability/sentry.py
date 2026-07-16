"""Sentry enrichment helpers.

Centralises how the project attaches searchable tags, structured
context and stable grouping fingerprints to Sentry events.

Why this exists
---------------
Sentry's default ``LoggingIntegration`` turns every ``logger.error`` /
``logger.exception`` call into an event and groups it by the rendered
log message. Because the project builds messages with f-strings that
embed dynamic values (``cart_uuid``, ``vtex_account``, error text),
distinct failures either explode into thousands of issues or collapse
under one misleading title.

Setting an explicit *fingerprint* makes Sentry group by error *type*
and *tenant* (``vtex_account``), while *tags* enable drill-down by
``project_uuid`` / ``cart_uuid`` and *context* keeps the full detail
for debugging.

The context manager forks the current scope, so enrichment is local to
the ``with`` block and never leaks into unrelated events.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import sentry_sdk

logger = logging.getLogger(__name__)

# Sentry rejects tag values longer than 200 chars; truncate defensively.
_MAX_TAG_LENGTH = 200


@contextmanager
def sentry_error_scope(
    *,
    fingerprint: List[str],
    tags: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    context_name: str = "error_details",
) -> Iterator[None]:
    """Enrich Sentry events emitted inside the ``with`` block.

    Args:
        fingerprint: Stable parts that define the issue group. Include
            ``vtex_account`` (via :func:`fingerprint_with_vtex_account`)
            so per-tenant error counts stay visible without grouping by
            dynamic IDs like ``cart_uuid``.
        tags: Searchable key/value pairs (e.g. ``vtex_account``,
            ``project_uuid``, ``http_status``). ``None`` values are
            skipped so callers don't have to filter them out.
        context: Structured, non-searchable details shown in the event
            body for debugging.
        context_name: Section name used for ``context`` in the Sentry UI.

    The block always runs, even when Sentry is disabled (no DSN) or the
    enrichment itself fails: scope mutations are best-effort and never
    propagate, so observability code can't break business flow.
    """
    with sentry_sdk.new_scope() as scope:
        try:
            scope.fingerprint = fingerprint
            for key, value in (tags or {}).items():
                if value is None:
                    continue
                scope.set_tag(key, _normalize_tag(value))
            if context:
                scope.set_context(context_name, context)
        except Exception:  # pragma: no cover - enrichment must never break flow
            logger.warning("Failed to enrich Sentry scope", exc_info=True)
        yield


def fingerprint_with_vtex_account(
    fingerprint: List[str],
    tags: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Append ``vtex_account`` to a fingerprint when present in tags.

    Keeps issue counts per VTEX tenant in the Sentry Issues list while
    still grouping by error category (HTTP status, route, exception type)
    instead of per-request dynamic IDs.
    """
    vtex_account = (tags or {}).get("vtex_account")
    if not vtex_account:
        return fingerprint

    account = str(vtex_account)
    if account in fingerprint:
        return fingerprint

    return [*fingerprint, account]


def _normalize_tag(value: Any) -> str:
    """Coerce a tag value to a Sentry-safe, length-bounded string."""
    text = str(value)
    if len(text) > _MAX_TAG_LENGTH:
        return f"{text[: _MAX_TAG_LENGTH - 1]}…"
    return text
