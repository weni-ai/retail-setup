import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.assign import AssignAgentUseCase
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
    VtexLocaleInfo,
)
from retail.projects.models import Project

ABANDONED_CART_AGENT_UUID = str(uuid.uuid4())


@override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
class AssignAbandonedCartButtonUrlTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.fetch_locale_info.return_value = VtexLocaleInfo(
            country_phone_code="55",
            meta_language="pt_BR",
            vtex_locale="pt-BR",
        )
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Test Project",
            vtex_account="teststore",
            config={"vtex_host_store": "https://www.realstore.com.br/"},
        )
        self.integrated_agent = MagicMock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.config = {"initial_template_language": "pt_BR"}

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_uses_vtex_host_store_for_button_base_url(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "data:image/png;base64,abc"
        mock_converter_cls.return_value = mock_converter
        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        self.use_case._create_default_abandoned_cart_template(
            integrated_agent=self.integrated_agent,
            project=self.project,
            project_uuid=self.project.uuid,
            app_uuid=uuid.uuid4(),
        )

        payload = mock_template_usecase.execute.call_args[0][0]
        button = payload["template_translation"]["template_button"][0]
        self.assertEqual(
            button["url"]["base_url"],
            "https://www.realstore.com.br/checkout?orderFormId=",
        )

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateCustomTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.ImageUrlToBase64Converter"
    )
    @override_settings(
        ABANDONED_CART_DEFAULT_IMAGE_URL="https://placehold.co/1200x628/png?text=Test"
    )
    def test_falls_back_to_vtexcommercestable_when_host_store_missing(
        self, mock_converter_cls, mock_custom_template_cls
    ):
        self.project.config = {}
        self.project.save(update_fields=["config"])

        mock_converter = MagicMock()
        mock_converter.convert.return_value = "data:image/png;base64,abc"
        mock_converter_cls.return_value = mock_converter
        mock_template_usecase = MagicMock()
        mock_custom_template_cls.return_value = mock_template_usecase

        self.use_case._create_default_abandoned_cart_template(
            integrated_agent=self.integrated_agent,
            project=self.project,
            project_uuid=self.project.uuid,
            app_uuid=uuid.uuid4(),
        )

        payload = mock_template_usecase.execute.call_args[0][0]
        button = payload["template_translation"]["template_button"][0]
        self.assertEqual(
            button["url"]["base_url"],
            "https://teststore.vtexcommercestable.com.br/checkout?orderFormId=",
        )
