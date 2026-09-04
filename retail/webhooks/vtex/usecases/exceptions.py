class ProjectNotFoundError(Exception):
    """Raised when no project exists for the given VTEX account."""


class IntegrationNotConfiguredError(Exception):
    """Raised when abandoned cart integration is not configured for the project."""


class InvalidIntegratedAgentError(Exception):
    """Raised when the integrated agent cannot process abandoned cart notifications."""


class BackInStockSendNotReadyError(Exception):
    """Raised when the WhatsApp send did not complete.

    The HTTP webhook already answered 200. This error fails the Celery
    job so the send can be inspected or retried by retail, not by IO.
    """
