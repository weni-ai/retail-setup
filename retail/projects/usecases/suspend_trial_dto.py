from dataclasses import dataclass


@dataclass(frozen=True)
class SuspendTrialProjectDTO:
    project_uuid: str
    conversation_limit: int
