from typing import TypedDict, Optional

from uuid import UUID

from datetime import date

from rest_framework.exceptions import NotFound, ValidationError

from django.db.models import Prefetch

from retail.agents.models import IntegratedAgent
from retail.templates.models import Template


class RetrieveIntegratedAgentQueryParams(TypedDict):
    show_all: bool
    start: Optional[date]
    end: Optional[date]


class RetrieveIntegratedAgentUseCase:
    def _prefetch_templates(
        self, query_params: RetrieveIntegratedAgentQueryParams
    ) -> Prefetch:
        show_all = query_params.get("show_all", False)
        start = query_params.get("start", None)
        end = query_params.get("end", None)

        if (start and not end) or (end and not start):
            raise ValidationError(
                detail={"start_end": "Both start and end must be provided together."}
            )

        if start and end and not show_all:
            raise ValidationError(
                detail={
                    "show_all": "show_all must be True if start and end are provided."
                }
            )

        if not show_all:
            queryset = Template.objects.filter(is_active=True)
            return Prefetch("templates", queryset=queryset)

        queryset = Template.objects.all()

        if start and end:
            queryset = queryset.exclude(deleted_at__date__range=[start, end])

        return Prefetch("templates", queryset=queryset)

    def _get_integrated_agent(
        self, pk: UUID, query_params: RetrieveIntegratedAgentQueryParams
    ) -> IntegratedAgent:
        try:
            templates_prefetch = self._prefetch_templates(query_params)

            return IntegratedAgent.objects.prefetch_related(templates_prefetch).get(
                uuid=pk, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent not found: {pk}")

    def execute(
        self, pk: UUID, query_params: RetrieveIntegratedAgentQueryParams
    ) -> IntegratedAgent:
        return self._get_integrated_agent(pk, query_params)
