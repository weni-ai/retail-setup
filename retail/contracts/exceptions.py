"""Domain exceptions for the contract acceptance flow."""


class ContractError(Exception):
    """Base class for contract domain errors."""


class ProjectNotFoundError(ContractError):
    """Raised when no Project matches the given vtex_account."""


class ContractTemplateNotFoundError(ContractError):
    """Raised when no active ContractTemplate matches the requested version."""


class ContractAcceptanceImmutableError(ContractError):
    """Raised on any attempt to update or delete a ContractAcceptance.

    Contract acceptances are an append-only legal record; mutating an
    existing row is forbidden both at the application layer and at the
    database layer (see the immutability triggers migration).
    """
