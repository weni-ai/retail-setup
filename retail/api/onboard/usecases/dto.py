from dataclasses import dataclass


@dataclass(frozen=True)
class ActivateWebchatDTO:
    """Data needed to publish the webchat loader script."""

    app_uuid: str
    account_id: str
