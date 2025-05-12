from celery import shared_task

from typing import List

from retail.agents.models import Agent
from retail.agents.usecases import ValidatePreApprovedTemplatesUseCase


@shared_task
def validate_pre_approved_templates(agents_ids: List[str]):
    agents = Agent.objects.filter(uuid__in=agents_ids)
    use_case = ValidatePreApprovedTemplatesUseCase()

    for agent in agents:
        use_case.execute(agent)
