from dataclasses import dataclass


@dataclass(frozen=True)
class ActivateWebchatDTO:
    """Data needed to publish the webchat loader script."""

    app_uuid: str
    account_id: str


@dataclass(frozen=True)
class ActivateWppCloudDTO:
    """Data needed to activate the WPP Cloud abandoned cart agent."""

    project_uuid: str
    percentage: int
