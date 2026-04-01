from django.test import TestCase

from unittest.mock import MagicMock, patch

from uuid import uuid4

from rest_framework.exceptions import NotFound, ValidationError

from retail.api.integrated_agent.usecases.dto import SendTestTemplateDTO
from retail.api.integrated_agent.usecases.send_test_template import (
    SendTestTemplateUseCase,
)


class SendTestTemplateUseCaseTest(TestCase):
    def setUp(self):
        self.mock_flows_service = MagicMock()
        self.use_case = SendTestTemplateUseCase(
            flows_service=self.mock_flows_service,
        )

        self.integrated_agent_uuid = uuid4()
        self.project_uuid = uuid4()
        self.channel_uuid = uuid4()

        self.dto = SendTestTemplateDTO(
            integrated_agent_uuid=self.integrated_agent_uuid,
            contact_urns=["whatsapp:5584999999999"],
            agent="abandoned_cart",
            variables=["var1", "var2"],
        )

    def _create_mock_integrated_agent(self, channel_uuid=None):
        mock_agent = MagicMock()
        mock_agent.uuid = self.integrated_agent_uuid
        mock_agent.channel_uuid = channel_uuid or self.channel_uuid
        mock_agent.project.uuid = self.project_uuid
        mock_agent.is_active = True
        return mock_agent

    def _create_mock_template(self, template_name="test_template_v1", language=None):
        mock_template = MagicMock()
        mock_template.current_version.template_name = template_name
        mock_template.current_version.status = "APPROVED"
        mock_template.metadata = {"language": language} if language else {}
        return mock_template

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_success(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        self.mock_flows_service.send_whatsapp_broadcast.assert_called_once()
        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]

        self.assertEqual(call_args["project"], str(self.project_uuid))
        self.assertEqual(call_args["urns"], ["whatsapp:5584999999999"])
        self.assertEqual(call_args["channel"], str(self.channel_uuid))
        self.assertEqual(call_args["msg"]["template"]["name"], "test_template_v1")
        self.assertEqual(call_args["msg"]["template"]["variables"], ["var1", "var2"])

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_success_without_variables(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        dto = SendTestTemplateDTO(
            integrated_agent_uuid=self.integrated_agent_uuid,
            contact_urns=["whatsapp:5584999999999"],
            agent="abandoned_cart",
            variables=[],
        )

        self.use_case.execute(dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertNotIn("variables", call_args["msg"]["template"])

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_success_with_language(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template(language="pt_BR")
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertEqual(call_args["msg"]["template"]["locale"], "pt-BR")

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_success_with_multiple_urns(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        dto = SendTestTemplateDTO(
            integrated_agent_uuid=self.integrated_agent_uuid,
            contact_urns=["whatsapp:5584999999999", "whatsapp:5584888888888"],
            agent="abandoned_cart",
            variables=["var1"],
        )

        self.use_case.execute(dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertEqual(len(call_args["urns"]), 2)

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_raises_not_found_when_agent_not_exists(self, mock_objects):
        from retail.agents.domains.agent_integration.models import IntegratedAgent

        mock_objects.select_related.return_value.get.side_effect = (
            IntegratedAgent.DoesNotExist
        )

        with self.assertRaises(NotFound):
            self.use_case.execute(self.dto)

        self.mock_flows_service.send_whatsapp_broadcast.assert_not_called()

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_raises_validation_error_when_no_active_template(
        self, mock_objects
    ):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = None
        mock_agent.templates.filter.return_value = mock_filter

        with self.assertRaises(ValidationError):
            self.use_case.execute(self.dto)

        self.mock_flows_service.send_whatsapp_broadcast.assert_not_called()

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_raises_validation_error_when_no_channel(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent(channel_uuid=None)
        mock_agent.channel_uuid = None
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        with self.assertRaises(ValidationError):
            self.use_case.execute(self.dto)

        self.mock_flows_service.send_whatsapp_broadcast.assert_not_called()

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_without_language_in_metadata(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = {}
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertNotIn("locale", call_args["msg"]["template"])

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_with_none_metadata(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = None
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertNotIn("locale", call_args["msg"]["template"])

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_get_active_template_filters_correctly(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        mock_agent.templates.filter.assert_called_once_with(
            is_active=True,
            current_version__isnull=False,
            current_version__status="APPROVED",
        )

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_includes_image_attachment_when_template_has_image_header(
        self, mock_objects
    ):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = {
            "header": {"header_type": "IMAGE", "text": "some_s3_key.png"}
        }
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertIn("attachments", call_args["msg"])
        self.assertEqual(len(call_args["msg"]["attachments"]), 1)
        self.assertTrue(call_args["msg"]["attachments"][0].startswith("image/png:"))

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_no_attachment_when_template_has_no_image_header(
        self, mock_objects
    ):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = {"body": "some text"}
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertNotIn("attachments", call_args["msg"])

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_no_attachment_when_header_type_is_text(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = {"header": {"header_type": "TEXT", "text": "Hello"}}
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertNotIn("attachments", call_args["msg"])

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_includes_test_button_when_template_has_url_button(
        self, mock_objects
    ):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = {
            "buttons": [{"type": "URL", "text": "Finalizar Pedido"}]
        }
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertIn("buttons", call_args["msg"])
        self.assertEqual(call_args["msg"]["buttons"][0]["sub_type"], "url")
        self.assertEqual(
            call_args["msg"]["buttons"][0]["parameters"][0]["text"],
            "example123",
        )

    @patch(
        "retail.api.integrated_agent.usecases.send_test_template.IntegratedAgent.objects"
    )
    def test_execute_no_button_when_template_has_no_url_button(self, mock_objects):
        mock_agent = self._create_mock_integrated_agent()
        mock_objects.select_related.return_value.get.return_value = mock_agent

        mock_template = self._create_mock_template()
        mock_template.metadata = {}
        mock_filter = MagicMock()
        mock_filter.select_related.return_value.first.return_value = mock_template
        mock_agent.templates.filter.return_value = mock_filter

        self.use_case.execute(self.dto)

        call_args = self.mock_flows_service.send_whatsapp_broadcast.call_args[0][0]
        self.assertNotIn("buttons", call_args["msg"])
