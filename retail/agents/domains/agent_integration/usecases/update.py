from typing import TypedDict, Optional

from rest_framework.exceptions import NotFound, ValidationError

from uuid import UUID

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.services.global_rule import GlobalRule


class UpdateIntegratedAgentData(TypedDict):
    contact_percentage: Optional[int]
    global_rule: Optional[str]


class UpdateIntegratedAgentUseCase:
    def __init__(self, global_rule: Optional[GlobalRule] = None):
        self.global_rule = global_rule or GlobalRule()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found {integrated_agent_uuid}")

    def _is_valid_percentage(self, percentage: int) -> bool:
        return 0 <= percentage <= 100

    def execute(
        self, integrated_agent: IntegratedAgent, data: UpdateIntegratedAgentData
    ) -> IntegratedAgent:

        if "contact_percentage" in data:
            contact_percentage = data.get("contact_percentage")

            if not self._is_valid_percentage(contact_percentage):
                raise ValidationError({"contact_percentage": "Invalid percentage"})

            integrated_agent.contact_percentage = contact_percentage

        if "global_rule" in data:
            global_rule = data.get("global_rule")

            if global_rule is None or global_rule == "":
                global_rule_code = None
                global_rule_prompt = None
            else:
                global_rule_code = (
                    self.global_rule.generate(integrated_agent, global_rule)
                    .validate()
                    .get_global_rule()
                )
                global_rule_prompt = global_rule

            integrated_agent.global_rule_code = global_rule_code
            integrated_agent.global_rule_prompt = global_rule_prompt

        integrated_agent.save()
        return integrated_agent
