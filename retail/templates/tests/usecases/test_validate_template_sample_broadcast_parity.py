"""Lockstep parity tests for sample validation / Direct Send broadcast (T019 / US2).

Pins SC-004: a UTILITY-classifying sample submission produces local
template state that ``Broadcast.build_direct_send_message`` renders
on the very next dispatch attempt with dispatch-time variables
substituted into the NEW content.

There is no cache lag and no asynchronous convergence window —
``Template.current_version`` is advanced in-line by the sample
endpoint, and the dispatcher reads the new
``current_version.template_name`` plus ``Template.metadata`` directly
on its next call. A regression that broke this lockstep guarantee
(asynchronous Integrations push, write-behind cache, divergence
between the sample-time and dispatch-time renderers) would let the
operator believe the broadcast carries the new content while it
still carries the prior one.

The test exercises the REAL ``ValidateTemplateSampleUseCase`` against
a database-backed Template + Version stack and the REAL
``Broadcast`` renderer. Only the external boundaries are mocked
(MetaService, IntegrationsService, S3 metadata handler) per
Constitution Principle III.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleDTO,
    ValidateTemplateSampleUseCase,
)


_DEFAULT_APP_UUID = "33333333-3333-3333-3333-333333333333"
_WABA_ID = "555111222"
_TASK_CREATE_TEMPLATE_PATH = (
    "retail.templates.strategies.update_template_strategies.task_create_template"
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "validate-template-sample-broadcast-parity-tests",
        }
    },
    USE_S3=False,
    USE_META=False,
    META_API_URL="http://test-meta.local",
    META_SYSTEM_USER_ACCESS_TOKEN="test-token",
)
class ValidateSampleBroadcastParityTest(TestCase):
    """Pin the lockstep guarantee from spec.md US2 / SC-004.

    Setup mirrors a Direct Send-eligible IntegratedAgent + Template +
    initial APPROVED Version (the shape ``AssignAgentUseCase``
    outputs at integration time). Action: submit a UTILITY-mocked
    sample with body + TEXT header + footer + CTA URL button edits,
    then invoke ``Broadcast.build_direct_send_message`` against the
    refreshed template and assert the rendered wire payload reflects
    the NEW content with dispatch-time ``template_variables``
    substituted in (not the sample-time ``template_body_params``).
    """

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(uuid=uuid4(), name="Lockstep Project")
        self.agent = Agent.objects.create(
            project=self.project,
            name="OrderStatus",
            slug="order-status",
            description="desc",
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            uuid=uuid4(),
            channel_uuid=uuid4(),
            config={"direct_send": True},
        )
        self.template = Template.objects.create(
            uuid=uuid4(),
            name="order_invoiced",
            integrated_agent=self.integrated_agent,
            metadata={
                "category": "UTILITY",
                "body": "Original body {{1}}",
                "language": "pt_BR",
            },
        )
        self.initial_version = Version.objects.create(
            template=self.template,
            template_name="weni_order_invoiced_initial",
            integrations_app_uuid=_DEFAULT_APP_UUID,
            project=self.project,
            status="APPROVED",
        )
        self.template.current_version = self.initial_version
        self.template.save(update_fields=["current_version"])

        self.meta_service = MagicMock()
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        self.metadata_handler = MagicMock()
        self.metadata_handler._upload_header_image.return_value = (
            "https://bucket.s3.amazonaws.com/uploaded.png"
        )
        self.integrations_service = MagicMock(spec=IntegrationsServiceInterface)
        self.integrations_service.get_channel_app.return_value = {
            "config": {"waba": {"id": _WABA_ID}}
        }
        self.use_case = ValidateTemplateSampleUseCase(
            meta_service=self.meta_service,
            metadata_handler=self.metadata_handler,
            integrations_service=self.integrations_service,
        )

    def _build_dto(self, **overrides) -> ValidateTemplateSampleDTO:
        defaults = dict(
            template_uuid=str(self.template.uuid),
            template_body="Olá {{1}}, seu pedido {{2}} foi pago.",
            template_header="Pagamento confirmado",
            template_footer="Equipe da loja",
            template_button=[
                {
                    "type": "URL",
                    "text": "Acompanhar pedido",
                    "url": {
                        "base_url": "https://loja.com/track/",
                        "url_suffix_example": "abc123",
                    },
                }
            ],
            template_body_params=["Maria", "12345"],
            app_uuid=_DEFAULT_APP_UUID,
            project_uuid=str(self.project.uuid),
            parameters=None,
            language="pt_BR",
        )
        defaults.update(overrides)
        return ValidateTemplateSampleDTO(**defaults)

    @patch(_TASK_CREATE_TEMPLATE_PATH)
    def test_utility_sample_renders_through_direct_send_broadcast(
        self, _mock_task_create_template
    ):
        dto = self._build_dto()

        self.use_case.execute(dto)
        self.template.refresh_from_db()

        broadcast_data = {
            "template_variables": {"1": "Carlos", "2": "98765"},
            "contact_urn": "whatsapp:5598123456789",
        }
        rendered = Broadcast().build_direct_send_message(
            data=broadcast_data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.project.uuid),
            template=self.template,
            integrated_agent=self.integrated_agent,
        )

        self.assertIsNotNone(rendered)
        self._assert_dispatches_new_version_name(rendered)
        self._assert_body_uses_dispatch_time_variables(rendered)
        self._assert_header_carries_new_text(rendered)
        self._assert_footer_carries_new_text(rendered)
        self._assert_cta_message_substitutes_url_placeholder(rendered)
        self._assert_quick_replies_absent(rendered)

    @patch(_TASK_CREATE_TEMPLATE_PATH)
    def test_quick_reply_sample_renders_quick_replies_on_broadcast(
        self, _mock_task_create_template
    ):
        dto = self._build_dto(
            template_button=[
                {"type": "QUICK_REPLY", "text": "Confirmar"},
                {"type": "QUICK_REPLY", "text": "Cancelar"},
            ],
        )

        self.use_case.execute(dto)
        self.template.refresh_from_db()

        broadcast_data = {
            "template_variables": {"1": "Carlos", "2": "98765"},
            "contact_urn": "whatsapp:5598123456789",
        }
        rendered = Broadcast().build_direct_send_message(
            data=broadcast_data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.project.uuid),
            template=self.template,
            integrated_agent=self.integrated_agent,
        )

        self.assertIsNotNone(rendered)
        self.assertEqual(rendered["msg"]["quick_replies"], ["Confirmar", "Cancelar"])
        self.assertNotIn("cta_message", rendered["msg"])
        self.assertNotIn("interaction_type", rendered["msg"])

    def _assert_dispatches_new_version_name(self, rendered):
        new_template_name = self.template.current_version.template_name
        self.assertEqual(
            rendered["msg"]["direct_send_template_name"], new_template_name
        )
        self.assertNotEqual(new_template_name, "weni_order_invoiced_initial")

    def _assert_body_uses_dispatch_time_variables(self, rendered):
        self.assertEqual(
            rendered["msg"]["text"],
            "Olá Carlos, seu pedido 98765 foi pago.",
        )

    def _assert_header_carries_new_text(self, rendered):
        self.assertEqual(
            rendered["msg"]["header"],
            {"type": "text", "text": "Pagamento confirmado"},
        )

    def _assert_footer_carries_new_text(self, rendered):
        self.assertEqual(rendered["msg"]["footer"], "Equipe da loja")

    def _assert_cta_message_substitutes_url_placeholder(self, rendered):
        self.assertEqual(rendered["msg"]["interaction_type"], "cta_url")
        self.assertEqual(
            rendered["msg"]["cta_message"],
            {
                "display_text": "Acompanhar pedido",
                "url": "https://loja.com/track/Carlos",
            },
        )

    def _assert_quick_replies_absent(self, rendered):
        self.assertNotIn("quick_replies", rendered["msg"])
