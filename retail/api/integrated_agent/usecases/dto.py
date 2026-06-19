from dataclasses import dataclass, field
from typing import List
from uuid import UUID


@dataclass(frozen=True)
class SendTestTemplateDTO:
    """Data needed to send a test template via WhatsApp broadcast."""

    integrated_agent_uuid: UUID
    contact_urns: List[str]
    agent: str
    variables: List[str] = field(default_factory=list)
