from uuid import UUID

from django.db.models import QuerySet

from retail.agents.models import IntegratedAgent


class ListIntegratedAgentUseCase:
    def _get_queryset(self, project_uuid: UUID) -> QuerySet[IntegratedAgent]:
        return IntegratedAgent.objects.filter(
            project__uuid=project_uuid, is_active=True
        )

    def execute(self, project_uuid: UUID) -> QuerySet[IntegratedAgent]:
        return self._get_queryset(project_uuid)
