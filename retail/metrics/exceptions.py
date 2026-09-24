"""Domain exceptions for product metric events."""


class ProductMetricError(Exception):
    """Base class for product metric domain errors."""


class ProjectNotFoundError(ProductMetricError):
    """Raised when no single active project can be resolved for the account."""


class ProductMetricPublishError(ProductMetricError):
    """Raised when the datalake rejects the event."""
