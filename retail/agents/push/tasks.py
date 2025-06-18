from celery import shared_task

from typing import List

from retail.agents.push.models import Agent
from retail.agents.push.usecases import ValidatePreApprovedTemplatesUseCase


@shared_task
def validate_pre_approved_templates(agents_ids: List[str]):
    agents = Agent.objects.filter(uuid__in=agents_ids)
    use_case = ValidatePreApprovedTemplatesUseCase()

    for agent in agents:
        use_case.execute(agent)
