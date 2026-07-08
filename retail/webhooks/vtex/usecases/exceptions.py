class ProjectNotFoundError(Exception):
    """Raised when no project exists for the given VTEX account."""


class IntegrationNotConfiguredError(Exception):
    """Raised when abandoned cart integration is not configured for the project."""


class InvalidIntegratedAgentError(Exception):
    """Raised when the integrated agent cannot process abandoned cart notifications."""
