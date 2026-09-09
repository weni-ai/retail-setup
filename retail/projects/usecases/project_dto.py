from dataclasses import dataclass
from typing import Optional


@dataclass
class ProjectCreationDTO:
    uuid: str
    name: str
    organization_uuid: str
    authorizations: list = None
    vtex_account: str = None
    language: str = None
    is_live_desk_copilot: bool = False
    parent_project_uuid: Optional[str] = None


@dataclass(frozen=True)
class ProjectVtexConfigDTO:
    account: str
    store_type: str
