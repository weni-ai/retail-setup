from celery import shared_task

from typing import List

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_management.usecases.validate_templates import (
    ValidatePreApprovedTemplatesUseCase,
)


@shared_task
def validate_pre_approved_templates(agents_ids: List[str]) -> None:
    agents = Agent.objects.filter(uuid__in=agents_ids)
    use_case = ValidatePreApprovedTemplatesUseCase()

    for agent in agents:
        use_case.execute(agent)
