from dataclasses import dataclass


@dataclass
class ProjectCreationDTO:
    uuid: str
    name: str
    organization_uuid: str
    authorizations: list = None
    vtex_account: str
