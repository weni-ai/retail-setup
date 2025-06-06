from django.db.models import QuerySet, Q

from typing import Optional

from retail.agents.models import Agent


class ListAgentsUseCase:
    @staticmethod
    def execute(project_uuid: Optional[str]) -> QuerySet[Agent]:
        return Agent.objects.filter(Q(project__uuid=project_uuid) | Q(is_oficial=True))
